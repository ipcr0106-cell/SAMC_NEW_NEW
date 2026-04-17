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

SYSTEM_PROMPT = """당신은 식품 수입 판정 전문가입니다. 사용자가 제공한 제품 정보와 아래 법령 청크를 근거로 다음을 JSON으로 응답하세요.

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
