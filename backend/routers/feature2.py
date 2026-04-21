"""
기능2 — 식품유형 분류

POST  /cases/{case_id}/pipeline/feature/2/run    : AI 분류 실행
GET   /cases/{case_id}/pipeline/feature/2        : 결과 조회
PATCH /cases/{case_id}/pipeline/feature/2        : 담당자 결과 수정
"""

import json
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cases", tags=["feature2-food-type"])

STEP_KEY  = "2"
STEP_NAME = "food_type"


# ─────────────────────────────────────────────────────────────
# P7 (2026-04-20) — law_ref 환각 차단
# LLM 이 RAG 밖 법령을 지어내는 회귀를 막기 위해 2단 검증:
#   1) RAG chunks 를 score >= _RAG_MIN_SCORE 로 필터 후 프롬프트 주입
#   2) 분류 후 law_ref 에 _F2_LAW_WHITELIST 또는 RAG 원문에 있는 법령명이
#      포함돼 있는지 확인 — 없으면 빈 문자열로 치환
# ─────────────────────────────────────────────────────────────
_RAG_MIN_SCORE = 0.35

_F2_LAW_WHITELIST: frozenset[str] = frozenset({
    "식품위생법",
    "식품의 기준 및 규격",
    "식품첨가물의 기준 및 규격",
    "건강기능식품에 관한 법률",
    "건강기능식품의 기준 및 규격",
    "수입식품안전관리 특별법",
    "주세법",
    "축산물 위생관리법",
    "축산물의 가공기준 및 성분규격",
    "식품등의 표시·광고에 관한 법률",
    "식품등의 표시광고에 관한 법률",
})


def _filter_rag_chunks(chunks: list[dict], min_score: float = _RAG_MIN_SCORE) -> list[dict]:
    """score threshold 미만 RAG 청크 제거 — bi-encoder 유사도가 낮으면 noise."""
    return [c for c in chunks if float(c.get("score") or 0) >= min_score]


def _validate_law_ref(law_ref: str, rag_chunks: list[dict]) -> str:
    """law_ref 가 whitelist 또는 RAG 원문의 법령을 포함하는지 검증.

    둘 다 아니면 빈 문자열 반환 + 경고 로그. 프롬프트에 넣은 RAG 밖 법령을
    LLM 이 지어냈을 가능성이 높으므로 UI 에 노출하지 않는다.
    """
    if not law_ref:
        return ""
    text = law_ref.strip()

    for law in _F2_LAW_WHITELIST:
        if law in text:
            return text

    rag_text = " ".join(c.get("text", "") for c in rag_chunks)
    # RAG 원문에서 "「법령명」" 패턴 추출 — 한국 법령 표기 관례
    rag_laws = set(re.findall(r"[「『](.+?)[」』]", rag_text))
    for law in rag_laws:
        if law and law in text:
            return text

    logger.warning("F2 law_ref 환각 차단: %r", text[:160])
    return ""


# ── 지연 초기화 클라이언트 ────────────────────────────────────────────
_clients: dict = {}


def _get_clients() -> dict:
    if _clients:
        return _clients

    from openai import OpenAI
    from pinecone import Pinecone
    from supabase import create_client

    _clients["openai"]   = OpenAI(api_key=os.getenv("F2_OPENAI_API_KEY"))
    _clients["pinecone"] = Pinecone(api_key=os.getenv("F2_PINECONE_API_KEY"))
    _clients["supabase"] = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_KEY"),
    )
    return _clients


# ── 헬퍼 함수 ───────────────────────────────────────────────────────

def _embed(text: str, client) -> list[float]:
    """OpenAI text-embedding-3-small 임베딩."""
    res = client.embeddings.create(model="text-embedding-3-small", input=text[:8000])
    return res.data[0].embedding


def _search_pinecone(query_vec: list[float], clients: dict, top_k: int = 8) -> list[dict]:
    """Pinecone에서 관련 식품유형 청크 검색."""
    index_name = os.getenv("F2_PINECONE_INDEX", "samc-a")
    index = clients["pinecone"].Index(index_name)
    result = index.query(vector=query_vec, top_k=top_k, include_metadata=True)
    return [
        {
            "text":       m.metadata.get("text", ""),
            "food_group": m.metadata.get("food_group", ""),
            "type_name":  m.metadata.get("type_name", ""),
            "score":      round(m.score, 4),
        }
        for m in result.matches
    ]


def _get_candidate_types(parsed_text: str, clients: dict) -> list[dict]:
    """
    파싱된 텍스트에서 키워드를 추출해 f2_food_type_classification 테이블 검색.
    주류 키워드가 있으면 주류 카테고리를 우선 포함.
    """
    ALCOHOL_KEYWORDS = [
        "에탄올", "주정", "발효", "증류", "맥아", "홉", "효모",
        "위스키", "소주", "보드카", "럼", "진", "브랜디",
        "맥주", "와인", "청주", "막걸리", "탁주", "약주", "과실주",
        "알코올", "alcohol", "whisky", "whiskey", "vodka", "rum",
    ]
    is_alcohol = any(kw in parsed_text.lower() for kw in ALCOHOL_KEYWORDS)

    sb = clients["supabase"]

    if is_alcohol:
        # 주류 카테고리(15번) 우선 조회
        res = (
            sb.table("f2_food_type_classification")
            .select("category_no, category_name, type_name, definition")
            .or_("category_no.eq.15,category_name.ilike.%주류%")
            .execute()
        )
    else:
        # 전체 식품유형 조회 (id 순 상위 60개 — 프롬프트 토큰 절약)
        res = (
            sb.table("f2_food_type_classification")
            .select("category_no, category_name, type_name, definition")
            .order("id")
            .limit(60)
            .execute()
        )

    return res.data or []


def _classify_with_llm(
    parsed_text: str,
    rag_chunks: list[dict],
    candidate_types: list[dict],
    clients: dict,
) -> dict:
    """
    OpenAI GPT-4o 로 식품유형 분류.
    반환 형식: {food_type, category_name, category_no, law_ref, reason, is_alcohol}

    P7 (2026-04-20):
        - RAG 청크는 호출자가 score threshold 필터 후 전달 (환각 억제).
        - 프롬프트에 "RAG 밖 법령 금지 / 확신 없으면 빈 문자열" 강제.
    """
    # RAG 컨텍스트 구성 (상위 5개 — 이미 threshold 필터 완료된 결과 기대)
    rag_text = "\n".join(
        f"[{c['food_group']} / {c['type_name']}] {c['text'][:300]}"
        for c in rag_chunks[:5]
    ) or "(관련도 높은 RAG 결과 없음 — law_ref 는 반드시 빈 문자열)"

    # 후보 식품유형 목록 구성
    candidate_text = "\n".join(
        f"- [{r['category_no']}] {r['category_name']} > {r['type_name']}: "
        f"{(r.get('definition') or '')[:150]}"
        for r in candidate_types
    )

    system_prompt = (
        "당신은 한국 식품 수입 검역 전문가입니다. "
        "주어진 원재료 배합비 또는 제조공정 텍스트를 분석하여 "
        "한국 식품공전 및 주세법 기준으로 식품유형을 분류합니다.\n\n"
        "식품유형 분류는 3단계로 이루어집니다:\n"
        "  - 대분류(식품군): 식품공전 제5장의 상위 카테고리 (예: '주류', '과자류, 빵류 또는 떡류')\n"
        "  - 중분류(식품종): 대분류 안의 중간 분류 (예: '증류주류', '발효주류'). "
        "    명시적인 중분류가 없는 경우 대분류명을 그대로 사용하세요. 절대 null을 반환하지 마세요.\n"
        "  - 소분류(식품유형): 최종 식품유형 (예: '위스키', '과자')\n\n"
        "【law_ref 엄격 규칙 — 반드시 준수】\n"
        "  1. 아래 '관련 법령 검색 결과 (RAG)' 에 실제로 등장한 법령명만 인용하세요.\n"
        "  2. 또는 다음 공식 법령 화이트리스트 중 하나에서만 선택:\n"
        "     식품위생법 / 식품의 기준 및 규격 / 식품첨가물의 기준 및 규격 /\n"
        "     건강기능식품에 관한 법률 / 건강기능식품의 기준 및 규격 /\n"
        "     수입식품안전관리 특별법 / 주세법 / 축산물 위생관리법 /\n"
        "     축산물의 가공기준 및 성분규격 / 식품등의 표시·광고에 관한 법률\n"
        "  3. 확신이 없거나 RAG/화이트리스트에 없으면 반드시 빈 문자열 \"\" 을 반환.\n"
        "     임의 법령명·조항·고시번호를 절대 지어내지 마세요.\n\n"
        "반드시 아래 JSON 형식으로만 응답하세요:\n"
        "{\n"
        '  "category_name": "대분류명=식품군 (예: 주류)",\n'
        '  "category_no": "대분류 번호 (예: 15)",\n'
        '  "subcategory_name": "중분류명=식품종 (예: 증류주류) 또는 null",\n'
        '  "food_type": "소분류명=식품유형 (예: 위스키)",\n'
        '  "law_ref": "근거 법령명 + 조항 (위 규칙 준수, 없으면 \\"\\")",\n'
        '  "reason": "분류 근거 2~3줄 설명",\n'
        '  "is_alcohol": true 또는 false\n'
        "}"
    )

    user_prompt = (
        f"## 원재료 / 제조공정 정보\n{parsed_text[:3000]}\n\n"
        f"## 관련 법령 검색 결과 (RAG — score≥{_RAG_MIN_SCORE} 필터됨)\n{rag_text}\n\n"
        f"## 후보 식품유형 목록\n{candidate_text}\n\n"
        "위 정보를 바탕으로 이 제품의 식품유형을 분류하세요. "
        "가장 적합한 소분류 식품유형 하나를 결정하고 JSON으로 반환하세요."
    )

    openai_client = clients["openai"]
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    return json.loads(raw)


def _get_required_docs(food_type: str, clients: dict) -> list[dict]:
    """분류된 식품유형에 맞는 필요서류 조회.
    - 해당 food_type에 해당하는 서류
    - food_type이 NULL인 공통 서류
    두 결과를 합쳐서 반환.
    """
    sb = clients["supabase"]

    # 특정 식품유형 서류
    specific = (
        sb.table("f2_required_documents")
        .select("doc_name, doc_description, condition, is_mandatory, law_source, food_type")
        .eq("food_type", food_type)
        .execute()
    )

    # 공통 서류 (food_type IS NULL)
    common = (
        sb.table("f2_required_documents")
        .select("doc_name, doc_description, condition, is_mandatory, law_source, food_type")
        .is_("food_type", "null")
        .execute()
    )

    return (specific.data or []) + (common.data or [])


# ── 요청 스키마 ──────────────────────────────────────────────────────

class PatchFeature2Request(BaseModel):
    final_result: dict
    edit_reason:  str = ""


# ── 엔드포인트 ───────────────────────────────────────────────────────

def _fetch_pipeline_result(sb, case_id: str, step_key: str) -> dict | None:
    """pipeline_steps에서 특정 단계의 결과를 가져온다."""
    res = (
        sb.table("pipeline_steps")
        .select("ai_result, final_result, status")
        .eq("case_id", case_id)
        .eq("step_key", step_key)
        .execute()
    )
    if not res.data:
        return None
    row = res.data[0]
    # final_result 우선, 없으면 ai_result
    result = row.get("final_result") or row.get("ai_result")
    if isinstance(result, str):
        return json.loads(result)
    return result


def _build_enriched_text(sb, case_id: str, fallback_parsed_md: str) -> str:
    """f0 + F1 결과를 합쳐서 F2 LLM에 전달할 구조화된 텍스트를 생성한다.

    PM이 임의로 구현한 파이프라인 연결입니다.
    수정하고 싶으면 이 함수만 변경하면 됩니다.
    """
    parts = []

    # ── f0 결과 (step_key='0') ──
    f0 = _fetch_pipeline_result(sb, case_id, "0")
    if f0:
        # 기본 정보
        basic = f0.get("basic_info") or {}
        if basic.get("product_name"):
            parts.append(f"제품명: {basic['product_name']}")
        if basic.get("export_country"):
            parts.append(f"수출국: {basic['export_country']}")

        # 원재료 목록 (구조화)
        ingredients = f0.get("ingredients") or []
        if ingredients:
            ing_lines = []
            for item in ingredients:
                name = item.get("name", "")
                ratio = item.get("ratio", "")
                line = f"  - {name}" + (f" ({ratio}%)" if ratio else "")
                ing_lines.append(line)
            parts.append("원재료 목록:\n" + "\n".join(ing_lines))

        # 공정 정보
        proc = f0.get("process_info") or {}
        codes = proc.get("process_codes") or []
        raw_text = proc.get("raw_process_text") or ""
        if codes:
            parts.append(f"공정 코드: {', '.join(codes)}")
        if raw_text:
            parts.append(f"공정 원문: {raw_text[:500]}")
    else:
        # f0 결과 없으면 원본 OCR 텍스트 사용 (fallback)
        parts.append(f"OCR 원문:\n{fallback_parsed_md[:3000]}")

    # ── F1 결과 (step_key='1') ──
    f1 = _fetch_pipeline_result(sb, case_id, "1")
    if f1:
        verdict = f1.get("verdict", "")
        import_possible = f1.get("import_possible")
        if verdict:
            parts.append(f"F1 수입판정: {verdict} ({'수입가능' if import_possible else '수입불가'})")

        # F1 원재료별 판정 상태
        f1_ingredients = f1.get("ingredients") or []
        if f1_ingredients:
            status_lines = []
            for ing in f1_ingredients:
                name = ing.get("name", "")
                status = ing.get("status", "")
                law_ref = ing.get("law_ref", "")
                status_lines.append(f"  - {name}: {status}" + (f" ({law_ref})" if law_ref else ""))
            parts.append("F1 원재료 판정:\n" + "\n".join(status_lines[:20]))

        # 수입불가 사유
        fail_reasons = f1.get("fail_reasons") or []
        if fail_reasons:
            parts.append("수입불가 사유: " + "; ".join(fail_reasons))

    return "\n\n".join(parts)


@router.post("/{case_id}/pipeline/feature/2/run")
def run_feature2(case_id: str):
    """
    기능2 실행: f0/F1 결과 + OCR 텍스트 → 식품유형 AI 분류 → pipeline_steps 저장
    """
    clients = _get_clients()
    sb      = clients["supabase"]

    # 1. 케이스 존재 확인
    case_res = sb.table("cases").select("id, product_name").eq("id", case_id).single().execute()
    if not case_res.data:
        raise HTTPException(
            status_code=404,
            detail={
                "error":   "CASE_NOT_FOUND",
                "message": "케이스를 찾을 수 없습니다.",
                "feature": 2,
            },
        )

    # 2. 파싱된 원재료 문서 조회 (fallback용)
    docs_res = (
        sb.table("documents")
        .select("parsed_md, doc_type, file_name")
        .eq("case_id", case_id)
        .execute()
    )
    docs = docs_res.data or []

    ingredient_docs = [d for d in docs if d["doc_type"] == "ingredients" and d.get("parsed_md")]
    selected_doc = (
        ingredient_docs[0]
        if ingredient_docs
        else next((d for d in docs if d.get("parsed_md")), None)
    ) or {}

    fallback_md = selected_doc.get("parsed_md", "")

    # 3. f0 + F1 결과를 합쳐서 구조화된 텍스트 생성
    parsed_text = _build_enriched_text(sb, case_id, fallback_md)

    if not parsed_text.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "error":   "EMPTY_INPUT",
                "message": "분류에 사용할 데이터가 없습니다. 먼저 서류 업로드 및 파싱을 실행하세요.",
                "feature": 2,
            },
        )

    # 3. pipeline_steps 상태를 'running'으로 업데이트
    sb.table("pipeline_steps").upsert(
        {
            "case_id":   case_id,
            "step_key":  STEP_KEY,
            "step_name": STEP_NAME,
            "status":    "running",
        },
        on_conflict="case_id,step_key",
    ).execute()

    try:
        # 4. Pinecone RAG 검색 + P7 threshold 필터 (환각 억제)
        query_vec      = _embed(parsed_text[:2000], clients["openai"])
        raw_rag_chunks = _search_pinecone(query_vec, clients, top_k=8)
        rag_chunks     = _filter_rag_chunks(raw_rag_chunks, min_score=_RAG_MIN_SCORE)

        # 5. DB 후보 식품유형 조회
        candidate_types = _get_candidate_types(parsed_text, clients)

        # 6. LLM 분류
        classification = _classify_with_llm(parsed_text, rag_chunks, candidate_types, clients)

        # 6-a. P7 law_ref 환각 차단 — RAG/whitelist 에 없는 법령은 빈 문자열로 치환
        classification["law_ref"] = _validate_law_ref(
            classification.get("law_ref") or "",
            rag_chunks,
        )

        # 7. 분류된 식품유형에 맞는 필요서류 조회
        required_docs  = _get_required_docs(classification.get("food_type", ""), clients)

        # RAG 원문에서 법령 구절 추출 (상위 3개)
        law_excerpts = [
            {
                "law_name": c.get("metadata", {}).get("law_name", c.get("law_name", "")),
                "text": c.get("metadata", {}).get("text", c.get("text", "")),
                "score": round(c.get("score", 0), 3),
            }
            for c in rag_chunks[:3]
            if c.get("metadata", {}).get("text") or c.get("text")
        ]

        ai_result = {
            # 대/중/소 3단계 분류
            "category_name":    classification.get("category_name"),    # 대분류
            "category_no":      classification.get("category_no"),
            "subcategory_name": classification.get("subcategory_name"),  # 중분류 (없으면 null)
            "food_type":        classification.get("food_type"),          # 소분류
            # 부가 정보
            "law_ref":          classification.get("law_ref"),
            "reason":           classification.get("reason"),
            "is_alcohol":       classification.get("is_alcohol"),
            "required_docs":    required_docs,
            "source_doc":       selected_doc.get("file_name", ""),
            "law_excerpts":     law_excerpts,
        }

        # 8. pipeline_steps 저장 (waiting_review)
        sb.table("pipeline_steps").upsert(
            {
                "case_id":    case_id,
                "step_key":   STEP_KEY,
                "step_name":  STEP_NAME,
                "status":     "waiting_review",
                "ai_result":  ai_result,
            },
            on_conflict="case_id,step_key",
        ).execute()

        return {
            "case_id":          case_id,
            "status":           "waiting_review",
            "category_name":    classification.get("category_name"),    # 대분류
            "subcategory_name": classification.get("subcategory_name"),  # 중분류
            "food_type":        classification.get("food_type"),          # 소분류
            "is_alcohol":       classification.get("is_alcohol"),
            "reason":           classification.get("reason"),
            "required_docs":    required_docs,
        }

    except Exception as exc:
        sb.table("pipeline_steps").upsert(
            {
                "case_id":   case_id,
                "step_key":  STEP_KEY,
                "step_name": STEP_NAME,
                "status":    "error",
                "ai_result": {"error": str(exc)},
            },
            on_conflict="case_id,step_key",
        ).execute()
        raise HTTPException(
            status_code=500,
            detail={
                "error":   "CLASSIFICATION_FAILED",
                "message": f"분류 실패: {exc}",
                "feature": 2,
            },
        )


@router.get("/{case_id}/pipeline/feature/2")
def get_feature2(case_id: str):
    """기능2 결과 조회."""
    clients = _get_clients()
    sb      = clients["supabase"]

    res = (
        sb.table("pipeline_steps")
        .select("*")
        .eq("case_id", case_id)
        .eq("step_key", STEP_KEY)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(
            status_code=404,
            detail={
                "error":   "F2_RESULT_NOT_FOUND",
                "message": "기능2 결과가 없습니다. 먼저 /run을 실행하세요.",
                "feature": 2,
            },
        )
    return res.data


@router.patch("/{case_id}/pipeline/feature/2")
def patch_feature2(case_id: str, body: PatchFeature2Request):
    """담당자 결과 수정 + 사유 저장 → pipeline_steps.final_result 업데이트."""
    clients = _get_clients()
    sb      = clients["supabase"]

    # 기존 스텝 확인
    existing = (
        sb.table("pipeline_steps")
        .select("id")
        .eq("case_id", case_id)
        .eq("step_key", STEP_KEY)
        .single()
        .execute()
    )
    if not existing.data:
        raise HTTPException(
            status_code=404,
            detail={
                "error":   "F2_RESULT_NOT_FOUND",
                "message": "기능2 결과가 없습니다.",
                "feature": 2,
            },
        )

    res = (
        sb.table("pipeline_steps")
        .update(
            {
                "final_result": body.final_result,
                "edit_reason":  body.edit_reason,
                "status":       "completed",
            }
        )
        .eq("case_id", case_id)
        .eq("step_key", STEP_KEY)
        .execute()
    )
    return {"message": "수정 완료", "updated": res.data}
