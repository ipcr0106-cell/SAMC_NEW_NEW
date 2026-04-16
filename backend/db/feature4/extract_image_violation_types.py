"""
기능4: 법령 조문에서 이미지 위반 유형 자동 추출 → f4_image_violation_types 저장

[자동화 흐름]
  법령 업로드 (admin_laws.py)
    → 1단계: AI가 법령 조문에서 이미지 위반 후보 추출
    → 2단계: AI가 4가지 기준으로 자동 검증
        ① 이미지·시각 요소로만 식별되는 위반인가?
        ② 실제 한국 법령 조문 근거가 명확한가?
        ③ 기존 등록 유형과 실질적으로 다른가?
        ④ AI 이미지 분석으로 감지 가능할 만큼 세부 기준이 구체적인가?
    → 4가지 모두 통과(confidence >= 0.8) → is_active=TRUE 자동 활성화
    → 하나라도 불통과 → is_active=FALSE + 사유 기록 (추후 수동 검토 가능)
    → 기존 유형 보완 항목 → sub_items에 내용 추가

[수동 실행]
  python extract_image_violation_types.py           # 전체 법령 (Supabase 등록 기준)
  python extract_image_violation_types.py "법령명"  # 특정 법령만
"""

import json
import os
import re
import sys

from openai import OpenAI
from dotenv import load_dotenv
from pinecone import Pinecone
from supabase import create_client

load_dotenv()

PINECONE_FETCH_BATCH = 100
AUTO_ACTIVATE_THRESHOLD = 0.8  # 이 이상이면 관리자 검토 없이 자동 활성화

_AD_RESTRICTION_MARKERS = re.compile(
    r"표시|광고|이미지|그림|사진|도안|마크|심볼|허위|과장|오인|금지|하여서는\s*아니\s*된다|하지\s*못한다"
)


# =============================================================
# Pinecone에서 청크 수집
# =============================================================

def _make_vector_id(law_name: str, chunk_index: int) -> str:
    """preprocess_laws.py와 동일한 결정적 벡터 ID 생성."""
    import hashlib
    raw = f"{law_name}|{chunk_index:05d}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _fetch_chunks(index, law_name: str, total_chunks: int) -> list[str]:
    all_ids = [_make_vector_id(law_name, i) for i in range(total_chunks)]
    texts = []
    for i in range(0, len(all_ids), PINECONE_FETCH_BATCH):
        batch = all_ids[i : i + PINECONE_FETCH_BATCH]
        result = index.fetch(ids=batch)
        for vid in batch:
            vec = result.vectors.get(vid)
            if vec and vec.metadata and vec.metadata.get("text"):
                texts.append(vec.metadata["text"])
    return texts


def _filter_ad_chunks(chunks: list[str]) -> list[str]:
    return [c for c in chunks if _AD_RESTRICTION_MARKERS.search(c)]


# =============================================================
# 1단계: 후보 추출 프롬프트
# =============================================================

_EXTRACT_FALLBACK_PROMPT = """\
아래는 식품 관련 법령 전문입니다.

이 법령에서 식품 라벨의 이미지·그림·도안·마크·심볼 요소에 적용되는 위반 유형을 추출해주세요.

[주의]
- 법령이 "허용 조건 나열" 방식이면, 조건 미충족 시 이미지로 나타낼 수 없는 표현을 추출하세요.
- 텍스트 표현이 아닌 이미지·시각 요소로 식별 가능한 위반만 추출하세요.
- 추출 결과가 없으면 빈 배열 []을 반환하세요.

[기존 등록 유형 목록]
{existing_types}

[법령명]
{law_name}

[법령 조문 전문]
{law_text}

반드시 아래 JSON 배열 형식으로만 응답하세요. 새로운 것이 없으면 빈 배열 []을 반환하세요.
[
  {{
    "type": "신규|기존_보완",
    "type_name": "유형명 (기존_보완이면 기존 유형명 그대로 사용)",
    "sub_items": "세부 탐지 기준 1,세부 탐지 기준 2,...",
    "default_severity": "must_fix|review_needed",
    "severity_condition": "조건부 severity 설명 (없으면 빈 문자열)",
    "law_ref": "근거 조문 번호"
  }}
]
"""


_EXTRACT_PROMPT = """\
아래 식품 관련 법령 조문에서 식품 라벨의 이미지·그림·도안 요소에 적용되는
위반 유형 후보를 추출해주세요.

[추출 기준]
- 텍스트 표현이 아닌 이미지·그림·마크·심볼·도안으로 나타낼 수 있는 위반만 추출합니다.
- 아래 [기존 등록 유형 목록]에 이미 있는 유형과 완전히 동일한 것은 제외하세요.
- 기존 유형의 세부 항목을 보완할 수 있는 내용은 "기존_보완" 타입으로 반환하세요.
- 기존에 없는 완전히 새로운 유형은 "신규" 타입으로 반환하세요.

[기존 등록 유형 목록]
{existing_types}

[법령명]
{law_name}

[법령 조문 원문]
{law_text}

반드시 아래 JSON 배열 형식으로만 응답하세요. 새로운 것이 없으면 빈 배열 []을 반환하세요.
[
  {{
    "type": "신규|기존_보완",
    "type_name": "유형명 (기존_보완이면 기존 유형명 그대로 사용)",
    "sub_items": "세부 탐지 기준 1,세부 탐지 기준 2,...",
    "default_severity": "must_fix|review_needed",
    "severity_condition": "조건부 severity 설명 (없으면 빈 문자열)",
    "law_ref": "근거 조문 번호"
  }}
]
"""


# =============================================================
# 2단계: 자동 검증 프롬프트 (관리자 검토 대체)
# =============================================================

_VALIDATE_PROMPT = """\
아래 식품 라벨 이미지 위반 유형 후보를 3가지 기준으로 검증해주세요.
(AI가 이미지에서 실제로 감지할 수 있는지는 여기서 판단하지 않습니다.
 법령상 유효한 유형이면 포함하고, 분석 시 AI가 불확실하면 사용자에게 직접 확인을 요청합니다.)

[자동 활성화 기준 — 3가지 모두 충족해야 confidence 0.8 이상]
① 이미지 전용성: 텍스트가 아닌 이미지·그림·마크·심볼·도안으로 나타날 수 있는 위반인가?
   (예: "주사기 이미지" → ○, "주사기라고 쓴 텍스트" → ×)
② 법령 근거 명확성: 명시된 한국 식품 법령 조문이 실제로 이미지 요소를 금지하는 조항인가?
③ 기존 유형 차별성: 아래 기존 유형들과 실질적으로 다른 새로운 위반인가?
   (유사 유형이 있으면 신규 유형 대신 기존 유형 보완으로 처리하는 것이 맞음)

[기존 등록 유형 목록]
{existing_types}

[검증 대상]
유형명: {type_name}
세부 탐지 기준: {sub_items}
근거 조문: {law_ref}

반드시 아래 JSON으로만 응답하세요.
{{
  "pass_image_specific": true | false,
  "pass_law_reference":  true | false,
  "pass_distinct":       true | false,
  "confidence":          0.0 ~ 1.0,
  "auto_activate":       true | false,
  "reason":              "판단 근거 한 문장 (불통과 항목 위주로 설명)"
}}
"""


def _validate_candidate(
    claude: OpenAI,
    candidate: dict,
    existing_types: list[dict],
) -> dict:
    """
    추출된 후보 유형을 4가지 기준으로 자동 검증.
    confidence >= AUTO_ACTIVATE_THRESHOLD 이고 auto_activate=true 이면 자동 활성화.
    """
    existing_summary = "\n".join(
        f"- {t['type_name']}: {t['sub_items'][:60]}..."
        for t in existing_types
    ) if existing_types else "없음"

    prompt = _VALIDATE_PROMPT.format(
        existing_types=existing_summary,
        type_name=candidate.get("type_name", ""),
        sub_items=candidate.get("sub_items", ""),
        law_ref=candidate.get("law_ref", ""),
    )

    try:
        resp = claude.chat.completions.create(
            model="gpt-5.4-nano",
            max_completion_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.choices[0].message.content.strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return {"auto_activate": False, "confidence": 0.0, "reason": "응답 파싱 실패"}
        return json.loads(match.group())
    except Exception as e:
        return {"auto_activate": False, "confidence": 0.0, "reason": f"검증 오류: {e}"}


# =============================================================
# 추출 + 검증 통합
# =============================================================

def _extract_with_ai(
    claude: OpenAI,
    chunks: list[str],
    law_name: str,
    existing_types: list[dict],
) -> list[dict]:
    existing_summary = "\n".join(
        f"- {t['type_name']}: {t['sub_items'][:80]}..."
        for t in existing_types
    ) if existing_types else "없음"

    combined = "\n\n".join(chunks)
    if len(combined) > 6000:
        combined = combined[:6000] + "\n...(이하 생략)"

    prompt = _EXTRACT_PROMPT.format(
        existing_types=existing_summary,
        law_name=law_name,
        law_text=combined,
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
            return []
        return json.loads(match.group())
    except Exception as e:
        print(f"    [경고] 추출 오류: {e}")
        return []


# =============================================================
# Supabase 저장
# =============================================================

def _get_existing_types(supabase) -> list[dict]:
    res = (
        supabase.table("f4_image_violation_types")
        .select("type_name, sub_items, source")
        .execute()
    )
    return res.data or []


def _upsert_types(
    supabase,
    items: list[dict],
    law_name: str,
    claude: OpenAI,
    existing_types: list[dict],
) -> dict:
    """
    추출 후보를 검증 후 저장.
    - 신규: 2단계 검증 통과 시 is_active=TRUE 자동 활성화
            미통과 시 is_active=FALSE + 사유 기록
    - 기존_보완: 검증 없이 sub_items 병합 (기존 유형 확장은 위험도 낮음)
    """
    added_active   = 0
    added_pending  = 0
    supplemented   = 0

    for item in items:
        type_name = item.get("type_name", "").strip()
        if not type_name:
            continue

        existing_row = (
            supabase.table("f4_image_violation_types")
            .select("id, sub_items, source")
            .eq("type_name", type_name)
            .execute()
        )

        # ── 기존 유형 보완 ──
        if item.get("type") == "기존_보완" and existing_row.data:
            row = existing_row.data[0]
            new_sub = item.get("sub_items", "").strip()
            if new_sub and new_sub not in row["sub_items"]:
                merged = row["sub_items"] + ",\n" + new_sub + f" (출처: {law_name} 개정)"
                supabase.table("f4_image_violation_types").update({
                    "sub_items":  merged,
                    "updated_at": "now()",
                }).eq("id", row["id"]).execute()
                supplemented += 1
            continue

        # ── 신규 유형 — 이미 존재하면 스킵 ──
        if existing_row.data:
            continue

        # 2단계 자동 검증
        print(f"    검증 중: {type_name}...", end=" ")
        validation = _validate_candidate(claude, item, existing_types)
        confidence  = validation.get("confidence", 0.0)
        auto_ok     = validation.get("auto_activate", False)
        reason      = validation.get("reason", "")

        should_activate = auto_ok and confidence >= AUTO_ACTIVATE_THRESHOLD

        supabase.table("f4_image_violation_types").insert({
            "type_name":          type_name,
            "sub_items":          item.get("sub_items", ""),
            "default_severity":   item.get("default_severity", "review_needed"),
            "severity_condition": item.get("severity_condition", ""),
            "law_ref":            item.get("law_ref", ""),
            "source":             "auto",
            "source_law_name":    law_name,
            "is_active":          should_activate,
            "review_note": (
                f"자동 활성화 (confidence={confidence:.2f}). {reason}"
                if should_activate else
                f"검토 필요 (confidence={confidence:.2f}). {reason}"
            ),
        }).execute()

        if should_activate:
            added_active += 1
            print(f"✓ 자동 활성화 (confidence={confidence:.2f})")
        else:
            added_pending += 1
            print(f"⚠ 보류 (confidence={confidence:.2f}): {reason}")

    return {
        "added_active":  added_active,
        "added_pending": added_pending,
        "supplemented":  supplemented,
    }


# =============================================================
# 핵심 함수 — admin_laws.py에서 호출
# =============================================================

def extract_image_types_for_law(
    law_name: str,
    index,
    supabase,
    claude: OpenAI,
) -> dict:
    """
    특정 법령 업데이트 시 이미지 위반 유형을 추출·검증·저장.
    반환: {"added_active": N, "added_pending": M, "supplemented": K}
    """
    print(f"\n[이미지 위반 유형 추출] {law_name}")

    doc = (
        supabase.table("f4_law_documents")
        .select("id, total_chunks")
        .eq("law_name", law_name)
        .execute()
    )
    if not doc.data:
        print(f"  [스킵] f4_law_documents에 '{law_name}' 없음")
        return {"added_active": 0, "added_pending": 0, "supplemented": 0}

    law_doc_id   = doc.data[0]["id"]
    total_chunks = doc.data[0]["total_chunks"]

    # 해당 법령에서 추출된 기존 유형 삭제 — 개정으로 폐지된 위반 유형 제거
    del_res = (
        supabase.table("f4_image_violation_types")
        .delete()
        .eq("source_law_name", law_name)
        .eq("source", "auto")
        .execute()
    )
    deleted_count = len(del_res.data) if del_res.data else 0
    if deleted_count:
        print(f"  → 기존 이미지 위반 유형 {deleted_count}개 삭제 (재추출 준비)")

    chunks    = _fetch_chunks(index, law_name, total_chunks)
    ad_chunks = _filter_ad_chunks(chunks)
    print(f"  → 전체 {len(chunks)}개 청크 중 광고·표시 관련 {len(ad_chunks)}개 선별")

    existing = _get_existing_types(supabase)

    # 1단계: 후보 추출
    if ad_chunks:
        candidates = _extract_with_ai(claude, ad_chunks, law_name, existing)
    else:
        # 광고·표시 마커 0개: 허용 조건 나열 또는 구조 미지원 법령 → 전체 청크 fallback
        print(f"  → 관련 조문 미탐지 — 전체 조문 AI 직접 분석 (fallback)")
        existing_summary = "\n".join(
            f"- {t['type_name']}: {t['sub_items'][:60]}..."
            for t in existing
        ) if existing else "없음"
        combined = "\n\n".join(chunks)
        if len(combined) > 8000:
            combined = combined[:8000] + "\n...(이하 생략)"
        prompt = _EXTRACT_FALLBACK_PROMPT.format(
            existing_types=existing_summary,
            law_name=law_name,
            law_text=combined,
        )
        try:
            resp = claude.chat.completions.create(
                model="gpt-5.4-nano",
                max_completion_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.choices[0].message.content.strip()
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            candidates = json.loads(match.group()) if match else []
            print(f"  → fallback 추출: {len(candidates)}개 후보")
        except Exception as e:
            print(f"  [경고] fallback 오류: {e}")
            candidates = []
    print(f"  → 1단계 추출: {len(candidates)}개 후보")

    if not candidates:
        return {"added_active": 0, "added_pending": 0, "supplemented": 0}

    # 2단계: 자동 검증 + 저장 (신규만 검증, 보완은 즉시 저장)
    result = _upsert_types(supabase, candidates, law_name, claude, existing)
    print(
        f"  → 자동 활성화: {result['added_active']}개 | "
        f"검토 보류: {result['added_pending']}개 | "
        f"기존 보완: {result['supplemented']}개"
    )
    return result


# =============================================================
# 메인 (수동 실행)
# =============================================================

def main():
    pc       = Pinecone(api_key=os.getenv("F4_PINECONE_API_KEY"))
    index    = pc.Index(host=os.getenv("F4_PINECONE_HOST"))
    supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
    claude   = OpenAI(api_key=os.getenv("F4_OPENAI_API_KEY"))

    target = sys.argv[1] if len(sys.argv) > 1 else None
    if target:
        laws = [target]
    else:
        all_docs = supabase.table("f4_law_documents").select("law_name").execute()
        laws = [row["law_name"] for row in all_docs.data] if all_docs.data else []
        print(f"처리할 법령 ({len(laws)}개): {laws}")

    total = {"added_active": 0, "added_pending": 0, "supplemented": 0}
    for law_name in laws:
        r = extract_image_types_for_law(law_name, index, supabase, claude)
        for k in total:
            total[k] += r[k]

    print(
        f"\n전체 완료 — "
        f"자동 활성화: {total['added_active']}개 | "
        f"검토 보류: {total['added_pending']}개 | "
        f"기존 보완: {total['supplemented']}개"
    )


if __name__ == "__main__":
    main()
