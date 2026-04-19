"""Step D — 법령 인용 서비스 (W2-D 본체 구현).

본 파일의 `run_step_d` 시그니처는 **Wave 2 Day 0에 동결**되었다.
W2-D 트랙이 본체를 구현하되 시그니처는 유지한다.

설계 철학:
    - RAG = **검색기만** — 판정 주도 X
    - LLM 해석 금지, 원문 인용만
    - `rag_verdict` / `rag_reasoning` / `RagConflictPanel` 로직 제거

5 namespace 병렬 검색:
    additive_code_text  (1664건) — 식품첨가물공전
    food_code_text      (140건)  — 식품공전
    health_food_text    (252건)  — 건강기능식품공전
    temporary_standard  (74건)   — 한시적 기준·규격
    functional_labeling (18건)   — 기능성표시 고시 (14번 §11-3 A')

점수 정규화:
    각 namespace 는 독립 Pinecone 쿼리로 top_k 건 반환.
    전체 합집합(최대 5*top_k)에서 score 기준 내림차순 정렬 후 상위 top_k 반환.
    Pinecone 반환 score 는 이미 코사인 유사도(0~1) 이므로 namespace 간 비교 직접 사용.

에지 케이스:
    - Pinecone 장애: citations=[] + warnings 누적, 파이프라인 계속
    - 검색 결과 0건: citations=[] (Step A/B/C 결정론적 결과로 충분)
    - 빈 컨텍스트: "수입식품 일반" 쿼리

참조:
    - 계획/f1 재설계 계획/04_Step_D_법령인용_설계.md
    - 계획/f1 재설계 계획/14_병렬실행_계획.md §11-3 결정 10 (functional_labeling A')
    - backend/services/f1_pinecone_client.py (search_multi 재사용)
    - backend/services/f1_openai_client.py (embed 재사용)
    - calling: backend/services/feature1.py `run_feature1_v2`
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from models.f1_types import ForbiddenHit, LawCitation, QueryContext, StepDResult
from services import f1_openai_client, f1_pinecone_client

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────
# 5 namespace — 설계 §5 + 14번 §11-3 결정 10 (A': functional_labeling 유지)
# ────────────────────────────────────────────────────────────
_NAMESPACES = [
    "additive_code_text",
    "food_code_text",
    "health_food_text",
    "temporary_standard",
    "functional_labeling",  # A': 쿼리 경로 유지 (18건 실데이터)
]

# namespace → 법령명 표시용 매핑 (LawCitation.law_name 추론)
_NAMESPACE_TO_LAW_NAME: dict[str, str] = {
    "additive_code_text": "식품첨가물의 기준 및 규격",
    "food_code_text": "식품의 기준 및 규격",
    "health_food_text": "건강기능식품의 기준 및 규격",
    "temporary_standard": "식품등의 한시적 기준 및 규격 인정 기준",
    "functional_labeling": "부당한 표시 또는 광고로 보지 아니하는 식품등의 기능성 표시 또는 광고에 관한 규정",
}


def build_query(ctx: QueryContext) -> str:
    """QueryContext → Pinecone 임베딩용 쿼리 문자열 합성 (04번 §4).

    Args:
        ctx: Step A/B/C 결과 요약.

    Returns:
        쿼리 문자열. 컨텍스트가 모두 비어 있으면 "수입식품 일반" 반환.
    """
    parts: list[str] = []

    if ctx.food_type:
        parts.append(f"식품유형 {ctx.food_type}")

    if ctx.forbidden_hits:
        names = ", ".join(h.ingredient_name for h in ctx.forbidden_hits)
        parts.append(f"수입 금지 원료: {names}")

    if ctx.restricted_ingredients:
        parts.append(f"사용 제한 원료: {', '.join(ctx.restricted_ingredients)}")

    if ctx.failed_standards:
        parts.append(f"기준규격 초과: {', '.join(ctx.failed_standards)}")

    return " / ".join(parts) or "수입식품 일반"


def _normalize_hit(hit: dict, namespace: str) -> Optional[LawCitation]:
    """Pinecone 히트 dict → LawCitation (필드 정규화).

    Pinecone metadata 에서 section_path 를 article_no 로, regulation_id / text 를
    그대로 사용. law_name 은 namespace 에서 추론.
    원문 편집 금지 — text 는 원본 그대로.
    """
    try:
        chunk_id: str = hit.get("id") or ""
        if not chunk_id:
            return None

        text: str = hit.get("text") or ""
        score: float = float(hit.get("score") or 0.0)

        # section_path 를 article_no 로 재활용 (예: "제3조/제1항")
        article_no: Optional[str] = hit.get("section_path") or None

        law_name: str = _NAMESPACE_TO_LAW_NAME.get(
            namespace, namespace
        )

        return LawCitation(
            chunk_id=chunk_id,
            law_name=law_name,
            article_no=article_no,
            text=text,
            score=score,
            namespace=namespace,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("LawCitation 정규화 실패 (chunk_id=%s): %s", hit.get("id"), exc)
        return None


async def run_step_d(
    query_context: QueryContext,
    top_k: int = 5,
) -> StepDResult:
    """Pinecone 5 namespace 병렬 검색 → 점수 상위 top_k 건 반환.

    Args:
        query_context: Step A/B/C 결과 요약 (식품유형·금지·제한·실패 기준).
        top_k: 최종 반환 건수. 각 namespace 에서 top_k 씩 조회 후 merge 상위 top_k.

    Returns:
        StepDResult — citations (LawCitation 리스트). 판정 주도 없음.

    설계 (04번 §3~§5):
        1. build_query(ctx) 로 쿼리 문자열 합성
        2. f1_openai_client.embed 로 벡터화
        3. 5 namespace 병렬 검색 (각 top_k 건)
        4. 전체 합집합 score 내림차순 → 상위 top_k 반환
        5. Pinecone 장애 → citations=[] + 경고 로그 (파이프라인 계속)
    """
    # ── 1. 쿼리 합성 ──────────────────────────────────────────
    query_text = build_query(query_context)
    logger.debug("Step D 쿼리: %s", query_text)

    # ── 2. 임베딩 ────────────────────────────────────────────
    # code-review 🔴-1 fix: `get_event_loop()` 은 Python 3.14+ 에서 제거 예정.
    # `get_running_loop()` 이 async 함수 내부에서 정확·안전.
    try:
        loop = asyncio.get_running_loop()
        vectors = await loop.run_in_executor(
            None, f1_openai_client.embed, [query_text]
        )
        if not vectors:
            logger.warning("Step D 임베딩 결과 비어 있음 — citations=[]")
            return StepDResult(citations=[])
        query_vector: list[float] = vectors[0]

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Step D 임베딩 실패 (%s: %s) — citations=[], 파이프라인 계속",
            type(exc).__name__,
            exc,
        )
        return StepDResult(citations=[])

    # ── 3. 5 namespace 병렬 검색 ─────────────────────────────
    try:
        hits: list[dict] = await f1_pinecone_client.search_multi(
            query_vector=query_vector,
            namespaces=_NAMESPACES,
            top_k_per_ns=top_k,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Step D Pinecone 검색 실패 (%s: %s) — citations=[], 파이프라인 계속",
            type(exc).__name__,
            exc,
        )
        return StepDResult(citations=[])

    # ── 4. LawCitation 정규화 + 상위 top_k merge ─────────────
    citations: list[LawCitation] = []
    for hit in hits:
        ns = hit.get("namespace") or ""
        citation = _normalize_hit(hit, ns)
        if citation is not None:
            citations.append(citation)

    # search_multi 는 이미 score 내림차순이므로 상위 top_k 슬라이싱
    citations = citations[:top_k]

    logger.debug(
        "Step D 완료: %d건 반환 (5 namespace × top_k=%d 후 merge)",
        len(citations),
        top_k,
    )
    return StepDResult(citations=citations)
