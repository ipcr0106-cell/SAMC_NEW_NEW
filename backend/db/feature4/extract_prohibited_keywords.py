"""
기능4: 금지 표현 키워드 추출 → f4_prohibited_expressions 적재

[변경 사항]
  - PDF 재파싱 제거 → Pinecone에 이미 저장된 청크 텍스트 재사용
  - 2단계 하이브리드: 규칙 기반 1차 추출 → AI 교차검증
  - extract_for_law(law_name) 함수로 모듈화 → admin_laws.py에서 자동 호출

[처리 흐름]
  Supabase에서 law_doc_id + total_chunks 조회
    → Pinecone fetch로 청크 텍스트 수집
    → 규칙 기반: 금지 조문 패턴 추출
    → AI 교차검증: 누락/오분류 보정
    → Supabase upsert

[실행 방법 (수동)]
  cd backend/db/feature4
  python extract_prohibited_keywords.py [law_name]  # 특정 법령만
  python extract_prohibited_keywords.py             # 전체 법령 (Supabase 등록 기준)
"""

import json
import os
import re
import sys
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv
from pinecone import Pinecone
from supabase import create_client

load_dotenv()

# =============================================================
# 설정
# =============================================================

# 기본 카테고리 시드 — 실제 사용 카테고리는 DB에서 동적 로드 (_load_categories)
_DEFAULT_CATEGORIES = ["질병치료", "허위과장", "의약품오인", "기능성"]
VALID_SEVERITIES = {"must_fix", "review_needed"}


def _load_categories(supabase) -> list[str]:
    """
    DB에서 현재 등록된 전체 카테고리 목록 반환.
    기본 4개 + 이전 법령 처리에서 자동 추가된 카테고리를 합산.
    새 법령 처리 시 AI가 새 카테고리를 제안하면 자동으로 DB에 축적됨.
    """
    try:
        res = supabase.table("f4_prohibited_expressions").select("category").execute()
        db_cats = {row["category"] for row in (res.data or []) if row.get("category")}
        return sorted(set(_DEFAULT_CATEGORIES) | db_cats)
    except Exception:
        return list(_DEFAULT_CATEGORIES)

PINECONE_FETCH_BATCH = 100  # Pinecone fetch 배치 크기


# =============================================================
# Pinecone에서 청크 텍스트 수집 (PDF 재파싱 불필요)
# =============================================================

def _make_vector_id(law_name: str, chunk_index: int) -> str:
    """preprocess_laws.py와 동일한 결정적 벡터 ID 생성."""
    import hashlib
    raw = f"{law_name}|{chunk_index:05d}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def fetch_chunks_from_pinecone(index, law_name: str, total_chunks: int) -> list[str]:
    """
    Pinecone에서 해당 법령의 청크 텍스트를 ID 기반으로 직접 가져옴.
    ID 형식: md5("{law_name}|{chunk_index:05d}")  (preprocess_laws.py 규칙과 동일)
    """
    all_ids = [_make_vector_id(law_name, i) for i in range(total_chunks)]
    texts = []

    for i in range(0, len(all_ids), PINECONE_FETCH_BATCH):
        batch_ids = all_ids[i : i + PINECONE_FETCH_BATCH]
        result = index.fetch(ids=batch_ids)
        for vid in batch_ids:
            vec = result.vectors.get(vid)
            if vec and vec.metadata and vec.metadata.get("text"):
                texts.append(vec.metadata["text"])

    return texts


# =============================================================
# 1단계: 규칙 기반 금지 조문 추출
# =============================================================

# 기본 범용 금지 마커 패턴 — 어느 식품 법령에나 공통 적용
# 법령 고유 패턴은 f4_law_documents.prohibition_hint_patterns에 저장되어 동적으로 합산됨
_BASE_PROHIBITION_MARKERS = re.compile(
    r"하여서는\s*아니\s*된다"
    r"|사용해서는\s*아니\s*된다"          # 제4조③, 5조③, 6조③ 등 사용 금지
    r"|하지\s*못한다"
    r"|금지한다|금지된다"
    r"|사용할\s*수\s*없다"
    r"|인식할\s*우려가\s*있는"            # 시행령 별표1, 1번 법령 각호
    r"|의약품으로\s*인식"                # 시행령 별표1 직접 패턴
    r"|부당한\s*표시\s*또는\s*광고"
    r"|에\s*해당하는\s*표시"
    r"|거짓[ㆍ·]\s*과장|거짓[ㆍ·]誇張|과장.*표시|허위.*표시"
    r"|소비자를\s*기만"                  # 제8조①제5호, 2번 법령 제2조
    r"|오인[ㆍ·]\s*혼동"                 # 제8조①제9호
    r"|비방하는\s*표시"                  # 제8조①제6호
    r"|사행심을\s*조장"                  # 제8조①제8호
    r"|사용하지\s*못하도록\s*정한"        # 2번 법령 제2조3호가
    r"|없거나\s*사용하지\s*않았다"        # 2번 법령 무첨가 허위 표시
    r"|한약의\s*처방명"                  # 2번 법령 의약품 오인 유형
    r"|마약류\s*명칭|마약[ㆍ·]대마"      # 시행규칙 제8조의3: 마약류 명칭 금지 (목록 앞 청크)
    r"|마약|대마|대마초|양귀비|아편|코카인" # 시행규칙 제8조의3: 금지 마약류 명칭 목록 청크
    r"|헤로인|모르핀|코데인|메스암페타민" # 시행규칙 제8조의3: 금지 마약류 명칭 목록 청크
    r"|이온수|이온음료|생명수"            # 시행규칙 제8조의2: 허위 표시 금지 용어
)


def _build_markers(supabase, law_name: str):
    """
    기본 범용 마커 + f4_law_documents.prohibition_hint_patterns(법령별 고유 패턴)를 합쳐
    동적 regex를 반환.

    법령 업로드 시 preprocess_laws.py가 AI로 hint_patterns를 추출해 DB에 저장하므로
    새 법령 추가 시 이 파일을 수동으로 수정할 필요가 없음.
    """
    try:
        res = (
            supabase.table("f4_law_documents")
            .select("prohibition_hint_patterns")
            .eq("law_name", law_name)
            .execute()
        )
        hints = []
        if res.data and res.data[0].get("prohibition_hint_patterns"):
            hints = [h for h in res.data[0]["prohibition_hint_patterns"] if h and h.strip()]

        if not hints:
            return _BASE_PROHIBITION_MARKERS

        extra = "|".join(re.escape(h) for h in hints)
        return re.compile(_BASE_PROHIBITION_MARKERS.pattern + "|" + extra)
    except Exception:
        return _BASE_PROHIBITION_MARKERS

# 조문 번호 패턴 (제N조, ①②③ 항 등)
_ARTICLE_START = re.compile(r"^(제\d+조(?:의\d+)?|[①②③④⑤⑥⑦⑧⑨⑩]|\d+\.)", re.MULTILINE)


_KEYWORD_HINTS = [
    # 질병치료 유형
    (r"질병.{0,10}(예방|치료|완화|개선|치유)", "질병치료"),
    (r"(암|당뇨|고혈압|심장|간|신장|관절).{0,10}(좋|도움|효과|개선|치료)", "질병치료"),
    # 의약품 오인 유형
    (r"(의약품|의료기기|처방|치료제).{0,10}(같|유사|효과)", "의약품오인"),
    (r"의약품으로\s*인식", "의약품오인"),              # 시행령 별표1
    (r"한약.{0,5}처방명", "의약품오인"),              # 2번 법령 별표1: 한약 처방명 사용 금지
    (r"마약|대마|대마초|양귀비|아편|코카인|헤로인|모르핀|코데인|메스암페타민", "의약품오인"),
                                                    # 시행규칙 제8조의3: 마약류 명칭 사용 금지
    # 허위과장 유형
    (r"(다이어트|지방분해|체지방|살빠|살이 빠)", "허위과장"),
    (r"거짓[ㆍ·].{0,5}과장", "허위과장"),             # 제8조①제4호
    (r"소비자를\s*기만", "허위과장"),                 # 제8조①제5호
    (r"오인[ㆍ·].{0,5}혼동", "허위과장"),             # 제8조①제9호
    (r"비방하는\s*표시", "허위과장"),                 # 제8조①제6호
    (r"사행심", "허위과장"),                         # 제8조①제8호
    (r"없거나\s*사용하지\s*않", "허위과장"),           # 무첨가 허위 표시
    (r"이온수|이온음료|생명수", "허위과장"),           # 시행규칙 제8조의2: 허위 표시 금지 용어
    # 기능성 유형
    (r"(기능성|건강기능식품).{0,20}(허가|인정).{0,10}(없|아니)", "기능성"),
]


def _rule_based_extract(text: str) -> list[dict]:
    """키워드 힌트 패턴으로 금지 표현 후보를 1차 추출."""
    results = []
    for pattern, category in _KEYWORD_HINTS:
        for m in re.finditer(pattern, text):
            start = max(0, m.start() - 20)
            end   = min(len(text), m.end() + 20)
            results.append({
                "keyword":  text[m.start():m.end()].strip(),
                "category": category,
                "severity": "review_needed",  # Claude가 must_fix로 상향 판단
                "law_ref":  "",
                "example":  text[start:end].strip(),
                "source":   "rule_based",
            })
    return results


def extract_prohibition_articles(chunks: list[str]) -> list[str]:
    """
    청크 중 금지 마커가 포함된 조문 단위 텍스트만 추출.
    → Claude에 넘길 범위를 좁혀 정확도 향상 + 비용 절감
    (법령별 동적 패턴 없이 기본 마커만 사용. extract_for_law에선 _build_markers 사용.)
    """
    return [c for c in chunks if _BASE_PROHIBITION_MARKERS.search(c)]


# =============================================================
# 2단계: AI 교차검증
# =============================================================

_FALLBACK_PROMPT = """\
아래는 식품 관련 법령 전문입니다.

이 법령에서 식품 광고·표시 시 금지되거나 위반이 되는 표현·키워드를 추출해주세요.

[주의]
- 법령이 "허용 조건 나열" 방식이면, 해당 조건을 충족하지 못할 때 위반이 되는 표현을 추출하세요.
  예) "~한 경우에만 표시 가능" → 해당 조건 없이 표시하는 행위가 금지 표현
- 법령이 별표·표 형식으로 금지 성분·처방명을 나열하는 경우, 각 항목을 개별 키워드로 추출하세요.
- 추출 결과가 없으면 빈 배열 []을 반환하세요.

[법령명]
{law_name}

[법령 조문 전문]
{text}

반드시 아래 JSON 배열 형식으로만 응답하세요.
category는 아래 목록 중 하나를 사용하고, 해당하는 것이 없으면 새 카테고리명을 직접 작성하세요.
[현재 카테고리 목록: {categories}]
[
  {{
    "keyword": "금지 표현 또는 금지 키워드",
    "category": "위 목록 중 하나 또는 새 카테고리명",
    "severity": "must_fix|review_needed",
    "law_ref": "근거 조문 번호",
    "example": "위반 사례 예시",
    "ai_confidence": "high|medium|low",
    "ai_note": "추출 근거 또는 허용 조건 역방향 해석 설명",
    "source": "claude_added"
  }}
]
"""


_VALIDATE_PROMPT = """\
아래는 규칙 기반으로 추출된 금지 표현 목록과, 해당 표현이 등장한 법령 조문입니다.

[중요 원칙]
- 규칙 기반 추출 결과를 절대 삭제하지 마세요.
- 의심스럽거나 맥락상 문제가 있더라도 항목을 유지하고, ai_note에 의견을 적으세요.
- 목록에 누락된 금지 표현이 있으면 추가하세요 (source: "claude_added").

각 항목에 대해:
1. category / severity 가 맞는지 검토하고 수정이 필요하면 수정하세요.
2. ai_confidence: "high" | "medium" | "low" — 이 표현이 실제로 금지 표현인지 확신 정도
3. ai_note: 우려 사항, 단서 조항, 허용 예외 여부 등 (없으면 빈 문자열)

[규칙 기반 추출 결과]
{rule_based_items}

[해당 법령 조문 원문]
{law_name}: {text}

반드시 아래 JSON 배열 형식으로만 응답하세요.
category는 아래 목록 중 하나를 사용하고, 해당하는 것이 없으면 새 카테고리명을 직접 작성하세요.
[현재 카테고리 목록: {categories}]
[
  {{
    "keyword": "금지 표현",
    "category": "위 목록 중 하나 또는 새 카테고리명",
    "severity": "must_fix|review_needed",
    "law_ref": "조문 번호",
    "example": "위반 사례 예시",
    "ai_confidence": "high|medium|low",
    "ai_note": "AI 의견 (없으면 빈 문자열)",
    "source": "rule_based|claude_added"
  }}
]
"""


def validate_with_ai(
    claude: OpenAI,
    chunk: str,
    law_name: str,
    rule_based_items: list[dict],
    categories: list[str] | None = None,
) -> list[dict]:
    """
    규칙 기반 결과를 Claude가 검증·보완.
    - 규칙 기반 항목은 절대 삭제하지 않음
    - AI 의견은 ai_note 필드로 추가
    - Claude가 발견한 추가 항목은 source: "claude_added"로 구분
    - categories: DB에서 로드한 현재 카테고리 목록 (없으면 기본값 사용)
    """
    categories_str = " | ".join(categories) if categories else " | ".join(_DEFAULT_CATEGORIES)
    rule_based_text = "\n".join(
        f"- {item.get('keyword', '')} [{item.get('category', '')} / {item.get('severity', '')}] {item.get('law_ref', '')}"
        for item in rule_based_items
    ) if rule_based_items else "없음"

    prompt = _VALIDATE_PROMPT.format(
        rule_based_items=rule_based_text,
        law_name=law_name,
        text=chunk,
        categories=categories_str,
    )
    try:
        resp = claude.chat.completions.create(
            model="gpt-5.4-nano",
            max_completion_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.choices[0].message.content.strip()
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            # 응답 파싱 실패 시 규칙 기반 결과 그대로 반환 (항목 손실 방지)
            print(f"    [경고] AI 응답 파싱 실패 — 규칙 기반 결과 유지")
            return [{**item, "source": "rule_based", "ai_confidence": "high", "ai_note": ""} for item in rule_based_items]

        items = json.loads(match.group())
        validated = [
            item for item in items
            if isinstance(item, dict)
            and item.get("keyword")
            and item.get("category")          # 비어있지 않으면 수락 (새 카테고리 자동 허용)
            and item.get("severity") in VALID_SEVERITIES
            and item.get("law_ref")
        ]

        # 규칙 기반 항목 누락 여부 확인 — Claude가 빠뜨린 항목 복구
        validated_keywords = {(i["keyword"], i["category"]) for i in validated}
        for item in rule_based_items:
            key = (item.get("keyword", ""), item.get("category", ""))
            if key not in validated_keywords:
                validated.append({
                    **item,
                    "source":         "rule_based",
                    "ai_confidence":  "high",
                    "ai_note":        "AI 응답에서 누락됨 — 규칙 기반 결과 복구",
                })

        return validated

    except Exception as e:
        print(f"    [경고] AI 오류: {e} — 규칙 기반 결과 유지")
        return [{**item, "source": "rule_based", "ai_confidence": "high", "ai_note": ""} for item in rule_based_items]


# =============================================================
# Supabase 저장
# =============================================================

def get_law_doc_info(supabase, law_name: str) -> dict | None:
    """f4_law_documents에서 law_doc_id와 total_chunks 조회."""
    res = (
        supabase.table("f4_law_documents")
        .select("id, total_chunks")
        .eq("law_name", law_name)
        .execute()
    )
    return res.data[0] if res.data else None


def upsert_keywords(supabase, keywords: list[dict], law_doc_id: str | None) -> int:
    """keyword + category 기준으로 upsert."""
    if not keywords:
        return 0
    saved = 0
    for kw in keywords:
        existing = (
            supabase.table("f4_prohibited_expressions")
            .select("id")
            .eq("keyword", kw["keyword"])
            .eq("category", kw["category"])
            .execute()
        )
        payload = {
            "keyword":         kw["keyword"],
            "category":        kw["category"],
            "severity":        kw["severity"],
            "law_ref":         kw.get("law_ref", ""),
            "example":         kw.get("example"),
            "law_document_id": law_doc_id,
        }
        if existing.data:
            supabase.table("f4_prohibited_expressions").update(payload).eq("id", existing.data[0]["id"]).execute()
        else:
            supabase.table("f4_prohibited_expressions").insert(payload).execute()
        saved += 1
    return saved


# =============================================================
# 핵심 함수 — admin_laws.py에서도 호출
# =============================================================

def extract_for_law(
    law_name: str,
    index,
    supabase,
    claude: OpenAI,
) -> int:
    """
    특정 법령의 금지 표현을 추출해 DB에 저장. 저장된 키워드 수 반환.
    admin_laws.py에서 법령 업로드 후 자동 호출됨.
    """
    print(f"\n[처리중] {law_name}")

    # 1. Supabase에서 law_doc_id, total_chunks 조회
    doc_info = get_law_doc_info(supabase, law_name)
    if not doc_info:
        print(f"  [스킵] f4_law_documents에 '{law_name}' 없음")
        return 0

    law_doc_id   = doc_info["id"]
    total_chunks = doc_info["total_chunks"]

    # 2. 기존 키워드 전체 삭제 — 개정으로 폐지된 금지 조문 키워드 제거
    #    (같은 키워드가 다른 법령에도 있으면 그 법령 기준 항목은 유지됨)
    del_res = (
        supabase.table("f4_prohibited_expressions")
        .delete()
        .eq("law_document_id", law_doc_id)
        .execute()
    )
    deleted_count = len(del_res.data) if del_res.data else 0
    if deleted_count:
        print(f"  → 기존 키워드 {deleted_count}개 삭제 (재적재 준비)")

    print(f"  → Pinecone에서 {total_chunks}개 청크 수집 중...")

    # 3. Pinecone에서 청크 텍스트 수집 (PDF 재파싱 없음)
    chunks = fetch_chunks_from_pinecone(index, law_name, total_chunks)
    if not chunks:
        print(f"  [경고] Pinecone에서 청크를 가져오지 못함")
        return 0
    print(f"  → {len(chunks)}개 청크 수집 완료")

    # 4. 현재 카테고리 목록 로드 (기본 4개 + DB에 축적된 신규 카테고리)
    categories = _load_categories(supabase)
    categories_str = " | ".join(categories)
    print(f"  → 카테고리 목록: {categories_str}")

    # 5. 규칙 기반: 금지 조문만 선별 (기본 마커 + 법령별 DB 저장 힌트 패턴)
    markers = _build_markers(supabase, law_name)
    prohibition_chunks = [c for c in chunks if markers.search(c)]
    print(f"  → 금지 조문 포함 청크: {len(prohibition_chunks)}개 (전체 {len(chunks)}개 중)")

    # 6. AI 교차검증 (규칙 기반 결과를 함께 넘겨 항목 손실 방지)
    all_keywords: list[dict] = []

    if prohibition_chunks:
        # 금지 마커 히트: 기존 경로 (규칙 기반 → AI 교차검증)
        for i, chunk in enumerate(prohibition_chunks):
            print(f"  AI 검증 {i+1}/{len(prohibition_chunks)}...", end="\r")
            rule_items = _rule_based_extract(chunk)
            kws = validate_with_ai(claude, chunk, law_name, rule_items, categories)
            all_keywords.extend(kws)
    else:
        # 금지 마커 0개: 허용 조건 나열 또는 구조 미지원 법령 → 전체 청크 fallback
        print(f"  → 금지 마커 미탐지 — 전체 조문 AI 직접 분석 (fallback)")
        combined = "\n\n".join(chunks)
        if len(combined) > 8000:
            combined = combined[:8000] + "\n...(이하 생략)"
        prompt = _FALLBACK_PROMPT.format(law_name=law_name, text=combined, categories=categories_str)
        try:
            resp = claude.chat.completions.create(
                model="gpt-5.4-nano",
                max_completion_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.choices[0].message.content.strip()
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                items = json.loads(match.group())
                all_keywords = [
                    item for item in items
                    if isinstance(item, dict)
                    and item.get("keyword")
                    and item.get("category")       # 새 카테고리 자동 수락
                    and item.get("severity") in VALID_SEVERITIES
                ]
                print(f"  → fallback 추출: {len(all_keywords)}개")
            else:
                print(f"  [경고] fallback AI 응답 파싱 실패")
        except Exception as e:
            print(f"  [경고] fallback AI 오류: {e}")

    # 5. 중복 제거
    seen: set[tuple] = set()
    deduped = []
    for kw in all_keywords:
        key = (kw["keyword"], kw["category"])
        if key not in seen:
            seen.add(key)
            deduped.append(kw)
    print(f"\n  → 추출: {len(all_keywords)}개 / 중복 제거 후: {len(deduped)}개")

    # 7. Supabase 저장
    saved = upsert_keywords(supabase, deduped, law_doc_id)
    print(f"  → 저장 완료: {saved}개")
    return saved


# =============================================================
# 메인 (수동 실행용)
# =============================================================

def main():
    pinecone_key  = os.getenv("F4_PINECONE_API_KEY")
    pinecone_host = os.getenv("F4_PINECONE_HOST")
    supabase_url  = os.getenv("SUPABASE_URL")
    supabase_key  = os.getenv("SUPABASE_SERVICE_KEY")
    openai_key = os.getenv("F4_OPENAI_API_KEY")

    if not all([pinecone_key, pinecone_host, supabase_url, supabase_key, openai_key]):
        raise RuntimeError(".env에 PINECONE_API_KEY, PINECONE_HOST, SUPABASE_URL, SUPABASE_SERVICE_KEY, OPENAI_API_KEY 필요")

    pc       = Pinecone(api_key=pinecone_key)
    index    = pc.Index(host=pinecone_host)
    supabase = create_client(supabase_url, supabase_key)
    claude   = OpenAI(api_key=openai_key)

    # 인자로 특정 법령명 지정 가능: python extract_prohibited_keywords.py "식품등의 부당한..."
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if target:
        laws = [target]
    else:
        # Supabase에 등록된 모든 법령 동적 조회 (하드코딩 목록 대신)
        all_docs = supabase.table("f4_law_documents").select("law_name").execute()
        laws = [row["law_name"] for row in all_docs.data] if all_docs.data else []
        print(f"처리할 법령 ({len(laws)}개): {laws}")

    total = 0
    for law_name in laws:
        total += extract_for_law(law_name, index, supabase, claude)

    print(f"\n전체 완료: {total}개 키워드 적재")


if __name__ == "__main__":
    main()
