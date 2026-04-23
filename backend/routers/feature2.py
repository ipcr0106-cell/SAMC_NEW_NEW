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


async def _classify_and_infer(sb, case_id: str, parsed_text: str) -> tuple[str | None, dict]:
    """F0 원재료의 food_class를 태깅하고 대분류를 추론.

    Returns:
        (inferred_major_category, food_class_result)
    """
    from services.f2_food_class import classify_ingredients_batch, compute_food_class_summary

    # F0 원재료 가져오기
    f0 = _fetch_pipeline_result(sb, case_id, "0")
    if not f0:
        return None, {}

    ingredients = f0.get("ingredients") or []
    names = [
        (ing.get("ingredient_code_name") or ing.get("name", "")).strip()
        for ing in ingredients
        if ing.get("name")
    ]

    # LLM으로 food_class 태깅
    await classify_ingredients_batch(names)

    # 카테고리별 합산 + 대분류 추론
    result = compute_food_class_summary(ingredients)

    # 코드 로직으로 추론된 대분류가 있으면 사용
    inferred = result.get("inferred_major")

    # 제품 형태 기반 추론 (코드 추론 실패 시)
    if not inferred:
        inferred = _infer_major_category(parsed_text)

    return inferred, result


def _infer_major_category(parsed_text: str) -> str | None:
    """제품 정보에서 대분류(식품군)를 코드 로직으로 추론.

    Returns:
        대분류 카테고리명 또는 None (추론 불가 시 전체 후보 사용)
    """
    text_lower = parsed_text.lower()

    # ② 주류 판단
    ALCOHOL_KEYWORDS = [
        "에탄올", "주정", "증류", "맥아", "홉",
        "위스키", "소주", "보드카", "럼", "브랜디",
        "맥주", "와인", "청주", "막걸리", "탁주", "약주", "과실주",
        "알코올", "alcohol", "whisky", "whiskey", "vodka", "rum", "wine", "beer",
    ]
    if any(kw in text_lower for kw in ALCOHOL_KEYWORDS):
        return "주 류"

    # ⑥ 용도별 — 제품 형태/이름으로 대분류 추론
    BEVERAGE_KEYWORDS = [
        "drink", "beverage", "juice", "milk", "tea", "coffee", "water",
        "음료", "주스", "밀크", "차", "커피", "워터", "우유",
        "rtd", "ready to drink", "음용",
    ]
    if any(kw in text_lower for kw in BEVERAGE_KEYWORDS):
        return "음료류"

    # 유가공품
    DAIRY_KEYWORDS = ["우유", "유고형분", "유지방", "cheese", "butter", "yogurt", "milk powder"]
    if any(kw in text_lower for kw in DAIRY_KEYWORDS):
        return "유가공품류"

    # 식육가공품 (식육 50% 이상)
    MEAT_KEYWORDS = ["소고기", "돼지고기", "닭고기", "식육", "beef", "pork", "chicken", "ham", "sausage"]
    if any(kw in text_lower for kw in MEAT_KEYWORDS):
        return "식육가공품류 및 포장육"

    return None  # 추론 불가 → 전체 후보


def _get_candidate_types(parsed_text: str, clients: dict) -> list[dict]:
    """대분류를 먼저 추론하고, 해당 대분류의 유형만 후보로 반환.

    대분류 추론 실패 시 전체 유형 반환.
    """
    sb = clients["supabase"]
    major = _infer_major_category(parsed_text)

    if major:
        # 해당 대분류의 유형만 조회
        res = (
            sb.table("f2_food_type_classification")
            .select("category_no, category_name, type_name, definition")
            .ilike("category_name", f"%{major}%")
            .execute()
        )
        candidates = res.data or []
        if candidates:
            logger.info(f"F2 대분류 추론: '{major}' → {len(candidates)}개 후보")
            return candidates

    # 추론 실패 또는 매칭 없음 → 전체 유형
    res = (
        sb.table("f2_food_type_classification")
        .select("category_no, category_name, type_name, definition")
        .order("id")
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
        "당신은 한국 식약처 식품유형 분류 전문가입니다.\n"
        "아래 '식품유형 분류 원칙'의 10단계 순서에 따라 제품을 분류하세요.\n\n"
        "=== 식품유형 분류 원칙 (순서대로 적용, 해당 유형 나오면 확정) ===\n"
        "① 자연산물 → 벌꿀류, 천일염 등\n"
        "② 타 법령 식품 → 식육가공품(식육50%↑), 유가공품, 주류(주세법)\n"
        "③ 특수용도식품 → 영유아식, 환자용식품\n"
        "④ 단일 자연산물 단순가공 → 고춧가루, 밀가루 등\n"
        "⑤ 기본 원료성 식품 → 전분류, 당류, 식용유지류, 어육가공품\n"
        "⑥ 용도별 분류 (대부분의 식품이 여기서 결정):\n"
        "  간편식류: 시리얼→면류→만두류→즉석식품류\n"
        "  간식류: 코코아가공품→빙과→초콜릿→과자류(떡→빵→과자)\n"
        "  음료류: 커피→인삼홍삼음료→다류→탄산음료→두유류→과·채음료→발효음료→기타음료\n"
        "  조미식품: 식초→식염→장류→소스류\n"
        "  반찬류: 젓갈류→두부묵류→김치류→건포류\n"
        "⑦ 특정원료 → 견과류가공품, 곤충가공식품\n"
        "⑧ 특정제조방법 → 추출가공식품, 절임류, 조림류\n"
        "⑨ 주원료별 → 과채가공품, 곡류가공품 등\n"
        "⑩ 어디에도 해당 없으면 → 기타가공품\n\n"
        "=== 분류 판단 핵심 규칙 ===\n"
        "【1단계: 각 원재료의 식품 카테고리 판단】\n"
        "각 원재료가 아래 중 어디에 해당하는지 먼저 판단하세요:\n"
        "  과일류: 사과, 포도, 오렌지, 코코넛, 망고, 바나나, 복숭아, 딸기, 레몬 등\n"
        "    → 과일의 즙/워터/밀크/퓨레도 과일류에 포함 (예: 코코넛워터=과일즙, 코코넛밀크=과일즙)\n"
        "  채소류: 당근, 토마토, 양배추, 시금치 등\n"
        "  유제품: 우유, 크림, 치즈, 버터 등\n"
        "  곡물류: 쌀, 밀, 옥수수, 보리 등\n"
        "  식육류: 소고기, 돼지고기, 닭고기 등\n"
        "  기타: 설탕, 소금, 정제수, 식품첨가물 등\n\n"
        "【2단계: 과일+채소 비율 합산】\n"
        "정제수를 제외하고 과일류+채소류의 배합비율을 합산하세요.\n\n"
        "【3단계: 분류 결정】\n"
        "- 제품이 액체이고 음용 목적이면 → 음료류\n"
        "- 음료류 중 과일+채소 비율 10% 이상 → 과·채음료\n"
        "- 음료류 중 커피 → 커피, 차 → 다류, 탄산 → 탄산음료, 두유 → 두유류\n"
        "- 음료류 중 위 어디에도 해당 안 되면 → 혼합음료\n"
        "- 두 유형에 모두 적합하면 분류순서가 앞선 유형 적용\n\n"
        "=== 출력 규칙 ===\n"
        "- food_type은 반드시 후보 목록의 type_name 중에서만 선택\n"
        "- 목록에 없는 유형을 만들지 마세요\n"
        "- law_ref는 반드시 '식품의 기준 및 규격' 또는 해당 법령명을 적으세요\n\n"
        "반드시 아래 JSON으로만 응답:\n"
        "{\n"
        '  "category_name": "대분류(식품군)",\n'
        '  "category_no": "번호",\n'
        '  "subcategory_name": "중분류(식품종)",\n'
        '  "food_type": "소분류 — 후보 목록에서 선택",\n'
        '  "law_ref": "식품의 기준 및 규격",\n'
        '  "reason": "구체적으로 어떤 원재료가 어떤 카테고리(과일류/채소류 등)에 해당하고, 배합비율이 얼마이며, 어떤 분류 기준에 따라 이 유형이 선택되었는지 설명",\n'
        '  "is_alcohol": true/false\n'
        "}"
    )

    user_prompt = (
        f"## 원재료 / 제조공정 정보\n{parsed_text[:4000]}\n\n"
        f"## 관련 법령 검색 결과 (RAG)\n{rag_text}\n\n"
        f"## 후보 식품유형 목록\n{candidate_text}\n\n"
        "위 정보를 바탕으로 이 제품의 식품유형을 분류하세요.\n"
        "【중요】\n"
        "- food_type은 반드시 후보 목록의 type_name에서만 선택\n"
        "- 【원재료 식품 카테고리 분석 결과】가 있으면 그 분석을 반드시 따르세요\n"
        "- 과일+채소 비율이 10% 이상이라고 분석되었으면 과·채음료입니다\n"
        "- 가장 적합한 1개를 결정하고 JSON으로 반환하세요."
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

        # 원재료 목록 (코드 카테고리 포함)
        ingredients = f0.get("ingredients") or []
        if ingredients:
            ing_lines = []
            a_total = 0.0  # 식품원료 합산
            b_total = 0.0  # 식품첨가물 합산
            p_total = 0.0  # 식품유형(설탕,정제수 등) 합산
            for item in ingredients:
                name = item.get("name", "")
                matched = item.get("ingredient_code_name") or name
                code = item.get("ingredient_code", "")
                ratio = item.get("ratio", "")
                prefix = code[0].upper() if code else "?"
                cat_label = {"A": "식품원료", "B": "식품첨가물", "P": "식품유형", "C": "건강기능식품"}.get(prefix, "미분류")
                pct = float(ratio) if ratio else 0
                if prefix == "A": a_total += pct
                elif prefix == "B": b_total += pct
                elif prefix == "P": p_total += pct
                line = f"  - {matched} {pct}% [{cat_label}]"
                if matched != name:
                    line += f" (원본: {name})"
                ing_lines.append(line)
            parts.append("원재료 목록:\n" + "\n".join(ing_lines))
            # 정제수 제외한 주원료 합산 (분류 원칙: 정제수 제외하고 가장 많이 사용된 원료 기준)
            main_ingredient_pct = a_total + p_total  # A+P = 원료성 재료
            parts.append(
                f"원재료 카테고리 합산 (정제수 제외): "
                f"식품원료(A) {a_total:.1f}%, 기타원료(P,정제수제외) {p_total:.1f}%, 식품첨가물(B) {b_total:.1f}%"
            )
            if basic.get("content_volume"):
                parts.append(f"내용량: {basic['content_volume']}")
            # 제품 형태 힌트
            product_name = (basic.get("product_name") or "").lower()
            if any(kw in product_name for kw in ["drink", "beverage", "milk", "juice", "tea", "coffee", "water", "음료", "주스", "우유", "차"]):
                parts.append("제품 형태 추정: 액체 음료 (음용 목적)")
            elif any(kw in product_name for kw in ["cookie", "cracker", "chip", "candy", "과자", "빵", "떡", "스낵"]):
                parts.append("제품 형태 추정: 고체 간식")

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
        # 3-a. 원재료 food_class 태깅 + 대분류 추론
        import asyncio
        inferred_major, fc_result = asyncio.run(_classify_and_infer(sb, case_id, parsed_text))
        if fc_result:
            # food_class 분석 결과를 parsed_text에 추가
            fc_items = fc_result.get("items", [])
            fc_summary = fc_result.get("summary", {})
            fv_pct = fc_result.get("fruit_veg_pct", 0)
            fc_lines = [f"  - {it['name']} {it['pct']}% → {it['food_class']}" for it in fc_items]
            parsed_text += (
                "\n\n【원재료 식품 카테고리 분석 결과】\n"
                + "\n".join(fc_lines)
                + f"\n카테고리별 합산: {fc_summary}"
                + f"\n과일+채소 비율: {fv_pct:.1f}%"
                + (f"\n→ 과일+채소 10% 이상이므로 과·채음료 해당" if fv_pct >= 10 else "")
            )
            if inferred_major:
                parsed_text += f"\n【코드 기반 대분류 추론: {inferred_major}】"

        # 4. Pinecone RAG 검색 + P7 threshold 필터 (환각 억제)
        query_vec      = _embed(parsed_text[:2000], clients["openai"])
        raw_rag_chunks = _search_pinecone(query_vec, clients, top_k=8)
        rag_chunks     = _filter_rag_chunks(raw_rag_chunks, min_score=_RAG_MIN_SCORE)

        # 5. DB 후보 식품유형 조회 (대분류 추론 결과로 필터링)
        if inferred_major:
            # 추론된 대분류의 유형만 후보
            res = sb.table("f2_food_type_classification") \
                .select("category_no, category_name, type_name, definition") \
                .ilike("category_name", f"%{inferred_major}%") \
                .execute()
            candidate_types = res.data or []
            if not candidate_types:
                # 매칭 안 되면 전체
                candidate_types = _get_candidate_types(parsed_text, clients)
            else:
                logger.info(f"F2 대분류 확정: '{inferred_major}' → {len(candidate_types)}개 후보")
        else:
            candidate_types = _get_candidate_types(parsed_text, clients)

        # 6. LLM 분류
        classification = _classify_with_llm(parsed_text, rag_chunks, candidate_types, clients)

        # 6-a. food_class 기반 분류 보정 — LLM 할루시네이션 방지
        if fc_result:
            fv_pct = fc_result.get("fruit_veg_pct", 0)
            fc_summary = fc_result.get("summary", {})

            # 음료류 대분류 + 과일+채소 10% 이상 → 과·채음료 강제
            if inferred_major and "음료" in inferred_major and fv_pct >= 10:
                # DB에 "과·채음료" 또는 "과･채음료" 유형이 있는지 확인
                fv_type = None
                for ct in candidate_types:
                    tn = ct.get("type_name", "")
                    if "과" in tn and "음료" in tn:
                        fv_type = ct
                        break
                if fv_type and classification.get("food_type") != fv_type["type_name"]:
                    logger.info(
                        f"F2 분류 보정: '{classification.get('food_type')}' → '{fv_type['type_name']}' "
                        f"(과일+채소 {fv_pct:.1f}% ≥ 10%)"
                    )
                    classification["food_type"] = fv_type["type_name"]
                    classification["category_name"] = fv_type.get("category_name", classification.get("category_name"))
                    classification["subcategory_name"] = fv_type["type_name"]

            # 식육 50% 이상인데 음료로 분류된 경우 보정
            elif fc_summary.get("식육류", 0) >= 50:
                for ct in candidate_types:
                    if "식육" in ct.get("category_name", ""):
                        classification["category_name"] = ct["category_name"]
                        classification["food_type"] = ct["type_name"]
                        break

            # 유류 주원료인데 다른 유형으로 분류된 경우 보정
            elif fc_summary.get("유류", 0) >= 30 and "유가공" not in (classification.get("category_name") or ""):
                for ct in candidate_types:
                    if "유가공" in ct.get("category_name", ""):
                        classification["category_name"] = ct["category_name"]
                        classification["food_type"] = ct["type_name"]
                        break

        # 6-b. P7 law_ref 환각 차단
        classification["law_ref"] = _validate_law_ref(
            classification.get("law_ref") or "",
            rag_chunks,
        )

        # 7. 분류된 식품유형에 맞는 필요서류 조회
        required_docs  = _get_required_docs(classification.get("food_type", ""), clients)

        # Supabase f2_food_type_classification에서 식품유형 정의 + 근거 법령 가져오기
        law_excerpts = []
        food_type_str = classification.get("food_type", "")
        if food_type_str:
            try:
                # 1) 정확 매칭
                rows = sb.table("f2_food_type_classification") \
                    .select("type_name, definition, law_source, category_name") \
                    .eq("type_name", food_type_str).limit(1).execute().data
                # 2) 부분 매칭 fallback
                if not rows:
                    rows = sb.table("f2_food_type_classification") \
                        .select("type_name, definition, law_source, category_name") \
                        .ilike("type_name", f"%{food_type_str}%").limit(1).execute().data
                # 3) 카테고리명(대분류)으로 검색
                if not rows and classification.get("category_name"):
                    rows = sb.table("f2_food_type_classification") \
                        .select("type_name, definition, law_source, category_name") \
                        .eq("category_name", classification["category_name"]).limit(3).execute().data

                for row in (rows or []):
                    defn = row.get("definition", "")
                    law_src = row.get("law_source", "")
                    if defn:
                        law_excerpts.append({
                            "law_name": law_src or "식품의 기준 및 규격",
                            "text": f"【{row.get('type_name', '')}】{defn}",
                            "score": 1.0,
                        })
            except Exception as _e:
                logger.warning(f"F2 식품유형 정의 조회 실패: {_e}")

        # food_class 기반 구체적 판정 근거 생성
        detailed_reason = classification.get("reason", "")
        if fc_result and fc_result.get("items"):
            fc_items = fc_result["items"]
            fc_summary = fc_result.get("summary", {})
            fv_pct = fc_result.get("fruit_veg_pct", 0)
            # 원재료별 카테고리 설명
            reason_parts = []
            for it in fc_items:
                if it["pct"] > 0 and it["food_class"] != "기타":
                    reason_parts.append(f"{it['name']}({it['food_class']}, {it['pct']}%)")
            if reason_parts:
                detailed_reason = "원재료 분석: " + ", ".join(reason_parts) + ". "
            # 카테고리별 합산
            summary_parts = [f"{k} {v:.1f}%" for k, v in sorted(fc_summary.items(), key=lambda x: -x[1]) if v > 0]
            if summary_parts:
                detailed_reason += "카테고리별 합산: " + ", ".join(summary_parts) + ". "
            # 분류 근거
            food_type_str = classification.get("food_type", "")
            if fv_pct >= 10 and "과" in food_type_str:
                detailed_reason += f"과일류+채소류 비율 {fv_pct:.1f}%로 10% 이상이므로 과·채음료로 분류."
            elif inferred_major:
                detailed_reason += f"제품 형태 및 원재료 구성에 따라 {inferred_major} > {food_type_str}로 분류."

        # law_ref 보정 (빈 문자열이면 기본값)
        law_ref = classification.get("law_ref", "")
        if not law_ref or law_ref == "—":
            law_ref = "식품의 기준 및 규격"

        # 후보 3개 생성: 1순위(확정) + 2~3순위(대안)
        primary_type = classification.get("food_type", "")
        candidates = []
        # 1순위: 현재 분류 결과
        candidates.append({
            "food_type": primary_type,
            "category_name": classification.get("category_name", ""),
            "definition": "",
            "reason": detailed_reason,
            "selected": True,
        })
        # 2~3순위: 같은 대분류의 다른 유형 (정의 포함)
        for ct in candidate_types:
            tn = ct.get("type_name", "")
            if tn != primary_type and len(candidates) < 3:
                defn = ct.get("definition", "") or ""
                candidates.append({
                    "food_type": tn,
                    "category_name": ct.get("category_name", ""),
                    "definition": defn[:200],
                    "reason": "",
                    "selected": False,
                })

        ai_result = {
            "category_name":    classification.get("category_name"),
            "category_no":      classification.get("category_no"),
            "subcategory_name": classification.get("subcategory_name"),
            "food_type":        primary_type,
            "law_ref":          law_ref,
            "reason":           detailed_reason,
            "is_alcohol":       classification.get("is_alcohol"),
            "required_docs":    [],
            "source_doc":       selected_doc.get("file_name", ""),
            "law_excerpts":     law_excerpts,
            "food_class_analysis": fc_result if fc_result else None,
            "inferred_major":   inferred_major,
            "candidates":       candidates,
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
            "required_docs":    [],
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
    """담당자 결과 수정 + 사유 저장 → pipeline_steps.final_result 업데이트.
    기존 row가 없으면 새로 생성 (수동 식품분류 입력 시나리오 지원).
    """
    clients = _get_clients()
    sb      = clients["supabase"]

    # 기존 스텝 확인
    existing = (
        sb.table("pipeline_steps")
        .select("id")
        .eq("case_id", case_id)
        .eq("step_key", STEP_KEY)
        .execute()
    )

    if existing.data:
        # 기존 row 업데이트
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
    else:
        # 새로 생성 (수동 식품분류 직접 입력)
        res = (
            sb.table("pipeline_steps")
            .insert(
                {
                    "case_id":      case_id,
                    "step_key":     STEP_KEY,
                    "step_name":    "food_type",
                    "final_result": body.final_result,
                    "edit_reason":  body.edit_reason or "사용자 직접 입력",
                    "status":       "completed",
                }
            )
            .execute()
        )

    return {"message": "수정 완료", "updated": res.data}
