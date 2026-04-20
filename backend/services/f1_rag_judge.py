"""F1 RAG 판정 — 임베딩 → Pinecone 병렬 검색 → OpenAI JSON 판정.

호출 규약:
    RagJudgement = await f1_rag_judge.run(payload)
    → 예외 던지지 않음. 실패 시 rag_verdict="error" 반환.
    → run_feature1_with_rag(Phase 4-B)에서 conflict_status="rag_unavailable"로 매핑.

호출 조건 (Phase 4-B 책임):
    - Step 0(forbidden_hits) 적중 시 RAG 미호출 (금지원료 절대 우선)
    - Step 0 미적중 시에만 run() 호출

환경변수:
    F1_OPENAI_API_KEY, F1_OPENAI_EMBED_MODEL, F1_OPENAI_CHAT_MODEL
    F1_PINECONE_API_KEY, F1_PINECONE_INDEX
    F1_RAG_TOP_K       (기본: 5, namespace당 top-k. 통합 후 상위 2K만 컨텍스트 사용)

payload 스키마:
    {
        "product_name": str | None,
        "ingredients":  list[str] | list[{"name": str, ...}],
        "food_type":    str | None,
    }

참고: 계획/f1_RAG도입계획_백엔드.md §3.3
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from models.f1_law_citation import LawCitation, RagJudgement
from services import f1_openai_client, f1_pinecone_client

DEFAULT_NAMESPACES = [
    "food_code_text",
    "additive_code_text",
    "functional_labeling",
    "temporary_standard",
    "health_food_text",
]

# ============================================================
# Phase 4-B-3d 에서 few-shot 프롬프트 채택.
# 실험 비교용으로 zero-shot 원본(pre-3d) 도 상수로 보존.
# env `F1_PROMPT_MODE=zero|few` (default: few) 로 전환 가능.
# ============================================================

SYSTEM_PROMPT_ZERO = """당신은 식품 수입 판정 전문가입니다. 사용자가 제공한 제품 정보와 아래 법령 청크를 근거로 다음을 JSON으로 응답하세요.

응답 스키마 (반드시 JSON):
{
  "rag_verdict": "permitted" | "restricted" | "prohibited" | "unidentified",
  "rag_reasoning": "한국어 2~4문장",
  "cited_chunk_ids": ["id1", "id2"]
}

원칙:
- 법령 청크에 직접 근거가 있는 경우만 verdict를 결정하세요.
- 청크 컨텍스트로 판단 불가 시 verdict="unidentified".
- 학습 데이터에 의존한 추측 금지.
- cited_chunk_ids는 reasoning에 실제 인용한 청크 id만 포함.
"""

SYSTEM_PROMPT_FEW = """당신은 식품 수입 판정 전문가입니다. 사용자가 제공한 제품 정보와 아래 법령 청크를 근거로 다음을 JSON으로 응답하세요.

응답 스키마 (반드시 JSON):
{
  "rag_verdict": "permitted" | "restricted" | "prohibited" | "unidentified",
  "rag_reasoning": "한국어 2~4문장",
  "cited_chunk_ids": ["id1", "id2"]
}

판정 원칙:
1. 청크가 해당 원료명을 **명시하거나 속한 카테고리**(예: "당류가공품", "유가공품", "건강기능식품 일반원료")를 기술하면 → 해당 verdict 적용. 카테고리 언급도 유효한 근거.
2. 일반 식품 원료(설탕, 포도당, 유산균, 에탄올 등)가 식품공전/첨가물공전 청크에 카테고리로 등장 → **permitted**. 엄격한 직접 명시 요구 금지.
3. 청크가 사용 조건·부위·함량 제한(예: "1일 섭취량 관리", "카페인 기준", 별표2 등재) → **restricted**.
4. 청크가 원료를 "식품원료 부적합", "사용 금지", "마약류" 등으로 명시 → **prohibited**.
5. "원유 100%에 다른 물질 혼합 불가" 같은 **포장·표시 규정**을 원료 자체의 prohibited로 오해 금지. 이는 "우유"는 permitted 원료임을 오히려 시사.
6. 청크에 해당 원료도, 속한 카테고리도, 관련 법령도 전혀 없으면 → **unidentified**. (가상·실존하지 않는 원료 포함)

판정 예시:
[예시 1] 제품: 설탕(당류가공품). 청크: "당류가공품은 포도당, 설탕 등을 주원료로 가공한 것"
→ {"rag_verdict":"permitted","rag_reasoning":"당류가공품 카테고리에 설탕이 주원료로 명시됨. 식품공전 허용 원료.","cited_chunk_ids":["..."]}

[예시 2] 제품: 과라나(음료류). 청크: "별표2: 과라나는 카페인 함유 원료로 1일 섭취량 기준 관리"
→ {"rag_verdict":"restricted","rag_reasoning":"별표2에 카페인 관리 조건부로 등재. 함량 조건 준수 필요.","cited_chunk_ids":["..."]}

[예시 3] 제품: 유산균(유가공품). 청크: "유가공품은 원유 또는 유가공품을 주원료로 하여 가공한 것"
→ {"rag_verdict":"permitted","rag_reasoning":"유가공품 카테고리의 일반 원료로 식품공전상 허용.","cited_chunk_ids":["..."]}

[예시 4] 제품: 가상명 XYZ. 청크: "(다른 원료 설명만)"
→ {"rag_verdict":"unidentified","rag_reasoning":"법령 청크에 해당 원료 및 속한 카테고리 언급이 없음.","cited_chunk_ids":[]}

[예시 5] 제품: 은행(과자류, 부위=종실). 청크: "별표2: 은행 — 사용부위: 종실(볶은 것)"
→ {"rag_verdict":"restricted","rag_reasoning":"별표2에 은행은 종실(볶은 것) 사용부위 제한 조건부로 등재. 조건 준수 필요.","cited_chunk_ids":["..."]}

[예시 6] 제품: Bacillus subtilis (건강기능식품). 청크: "유용한 미생물 원료는 건강기능식품 고시에 등재된 균주에 한해 사용 가능"
→ {"rag_verdict":"permitted","rag_reasoning":"건강기능식품 고시에 등재된 미생물 원료 균주 범주에 속함. 식품공전 허용.","cited_chunk_ids":["..."]}

[예시 7] 제품: 딸기잼(잼류, sub_ingredients=[딸기[정제수], 설탕]). 청크: "딸기는 식품공전 별표1 과일류 등록 허용 원료"
→ {"rag_verdict":"permitted","rag_reasoning":"복합원재료의 주원료(딸기)가 별표1 허용. 하위 정제수/설탕도 일반 식품 원료로 허용.","cited_chunk_ids":["..."]}

[예시 8] 제품: 소브산(빵류, INS 200, is_heated=True). 청크: "빵류 — 소르빈산(INS 200): 1000 ppm 이하"
→ {"rag_verdict":"permitted","rag_reasoning":"빵류에서 소르빈산 1000ppm 이하 허용. 가열 공정 기준에 영향 없음.","cited_chunk_ids":["..."]}

- cited_chunk_ids는 reasoning에 실제 인용한 청크 id만 포함.
- 학습 데이터만으로 추측 금지(청크 기반 판단 필수).
- 복합원재료는 하위(sub) 원료 중 permitted 가 1건이라도 있으면 aggregation.permitted>0 → permitted 우세.
- INS/CAS 번호가 제공되면 해당 첨가물이 첨가물공전에 등재된 합법 원료임을 강한 근거로 삼을 것.
"""

SYSTEM_PROMPT = (
    SYSTEM_PROMPT_ZERO
    if os.environ.get("F1_PROMPT_MODE", "few").lower() == "zero"
    else SYSTEM_PROMPT_FEW
)


def _build_query_text(payload: dict[str, Any]) -> str:
    """payload → 임베딩/프롬프트용 쿼리 문자열."""
    parts: list[str] = []

    name = payload.get("product_name")
    if name:
        parts.append(f"제품명: {name}")

    ings = payload.get("ingredients")
    if ings:
        if isinstance(ings[0], dict):
            names = [str(i.get("name", "")).strip() for i in ings if i.get("name")]
        else:
            names = [str(i).strip() for i in ings if i]
        if names:
            parts.append(f"원료: {', '.join(names)}")

    ftype = payload.get("food_type")
    if ftype:
        parts.append(f"식품유형: {ftype}")

    return "\n".join(parts) if parts else "정보 없음"


def _build_context(hits: list[dict[str, Any]]) -> str:
    """Pinecone 히트 → chat 프롬프트 컨텍스트."""
    lines: list[str] = []
    for h in hits:
        section = h.get("section_path") or "(section 없음)"
        ns = h.get("namespace") or "(ns 없음)"
        text = h.get("text") or ""
        lines.append(f"[id={h['id']}] [{ns} / {section}]\n{text}")
    return "\n\n".join(lines) if lines else "(검색 결과 없음)"


async def run(payload: dict[str, Any]) -> RagJudgement:
    """payload → RagJudgement. 실패 시 verdict='error'로 반환 (예외 X)."""
    try:
        query_text = _build_query_text(payload)

        loop = asyncio.get_event_loop()
        vectors = await loop.run_in_executor(
            None, f1_openai_client.embed, [query_text]
        )
        if not vectors:
            return RagJudgement(
                rag_verdict="error",
                rag_reasoning="임베딩 결과가 비어 있습니다.",
                law_citations=[],
            )
        query_vector = vectors[0]

        top_k = int(os.environ.get("F1_RAG_TOP_K", "5"))
        hits = await f1_pinecone_client.search_multi(
            query_vector, DEFAULT_NAMESPACES, top_k_per_ns=top_k,
        )
        hits = hits[: top_k * 2]

        context = _build_context(hits)
        user_msg = (
            f"=== 제품 정보 ===\n{query_text}\n\n"
            f"=== 법령 청크 ===\n{context}"
        )

        parsed = await loop.run_in_executor(
            None, f1_openai_client.chat_json, SYSTEM_PROMPT, user_msg,
        )

        raw_verdict = parsed.get("rag_verdict") or "unidentified"
        if raw_verdict not in ("permitted", "restricted", "prohibited", "unidentified"):
            raw_verdict = "unidentified"

        cited_ids = set(parsed.get("cited_chunk_ids") or [])
        citations = [
            LawCitation(
                chunk_id=h["id"],
                namespace=h.get("namespace") or "",
                regulation_id=h.get("regulation_id"),
                section_path=h.get("section_path"),
                text=h.get("text") or "",
                score=float(h.get("score") or 0.0),
            )
            for h in hits
            if h["id"] in cited_ids
        ]

        return RagJudgement(
            rag_verdict=raw_verdict,
            rag_reasoning=parsed.get("rag_reasoning") or "",
            law_citations=citations,
        )
    except Exception as exc:  # noqa: BLE001
        return RagJudgement(
            rag_verdict="error",
            rag_reasoning=f"RAG 호출 실패: {type(exc).__name__}: {exc}",
            law_citations=[],
        )
