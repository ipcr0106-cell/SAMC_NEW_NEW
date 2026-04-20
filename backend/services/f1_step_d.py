"""Step D — 법령 인용 (W2-D 본체, 2026-04-20 P6 재작성).

설계 변경:
    이전: Pinecone 5 namespace 임베딩 검색 (OpenAI embed + search_multi)
    현재: law.go.kr DRF 본문을 Postgres f1_law_articles 에 캐시 적재 후
          pg_trgm/ILIKE 다중 키워드 매칭

배경:
    Pinecone 검색이 밀가루 같은 쿼리에 무관 결과(세균수/냉동식품/두부 등)를
    score 0.42~0.44 로 반환하는 품질 문제 발생 → 법제처 공식 본문을 직접
    적재하고 결정론적 키워드 매칭으로 교체.

설계 철학 (04번 §2 동결):
    - RAG = **검색기만** — 판정 주도 X
    - LLM 해석 금지, 원문 인용만
    - `rag_verdict` / `rag_reasoning` / `RagConflictPanel` 없음

5 namespace (Day 0 동결):
    food_code_text       — 식품의 기준 및 규격
    additive_code_text   — 식품첨가물의 기준 및 규격
    health_food_text     — 건강기능식품의 기준 및 규격
    temporary_standard   — 식품등의 한시적 기준 및 규격 인정 기준
    functional_labeling  — 부당한 표시...기능성 표시 또는 광고에 관한 규정

점수:
    score = (article 에 매칭된 키워드 수) / (전체 쿼리 키워드 수) ∈ [0, 1]
    키워드 0개 (정상 비어있음) → 각 namespace 첫 1건만 score=0 으로 반환.

에지 케이스:
    - DB 장애: citations=[] + 경고 로그 (파이프라인 계속)
    - 키워드 0개: 5종 첫 1건씩 (총 5건) score=0 반환
    - 매칭 0건: citations=[]

참조:
    계획/f1 재설계 계획/04_Step_D_법령인용_설계.md
    법령_API_전환_가이드.md
    memory/feedback_f1_db_untrusted.md
    데이터 적재: backend/scripts/f1_sync_laws.py + backend/db/migrations/020_f1_law_cache.sql

호출처:
    backend/services/feature1.py `run_feature1_v2`
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import asyncpg

from models.f1_types import LawCitation, QueryContext, StepDResult

logger = logging.getLogger(__name__)

# 04번 §5 + 14번 §11-3 결정 10 (A': functional_labeling 유지) — Day 0 동결
_NAMESPACES: list[str] = [
    "additive_code_text",
    "food_code_text",
    "health_food_text",
    "temporary_standard",
    "functional_labeling",
]


def _dsn() -> Optional[str]:
    return os.environ.get("DATABASE_URL") or os.environ.get("F1_DATABASE_URL")


def build_query(ctx: QueryContext) -> str:
    """디버깅·로깅용 사람-친화 한 줄 요약.

    실제 검색은 `_extract_keywords` 의 키워드 리스트로 수행.
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


def _extract_keywords(ctx: QueryContext) -> list[str]:
    """QueryContext → ILIKE 매칭용 키워드 리스트.

    P6 (2026-04-20):
        - ingredient_names / ingredient_codes 추가 (밀가루 같은 원재료명·코드 직접 매칭)
        - failed_standards "name:test" 형태는 ':' 로 분해해 양쪽 토큰 모두 키워드화

    중복 제거, 길이 < 2 토큰 제외 (의미 있는 매칭 보장).
    """
    raw: list[str] = []
    if ctx.food_type:
        raw.append(ctx.food_type)
    raw.extend(getattr(ctx, "ingredient_names", []) or [])
    raw.extend(getattr(ctx, "ingredient_codes", []) or [])
    for h in ctx.forbidden_hits:
        if h.ingredient_name:
            raw.append(h.ingredient_name)
    raw.extend(r for r in ctx.restricted_ingredients if r)
    for s in ctx.failed_standards:
        if not s:
            continue
        if ":" in s:
            raw.extend(part for part in s.split(":") if part)
        else:
            raw.append(s)

    seen: set[str] = set()
    out: list[str] = []
    for k in raw:
        k = k.strip()
        if len(k) < 2 or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def _build_search_sql(num_keywords: int, top_k_per_ns: int) -> str:
    """동적 SQL — 키워드 K개 → ILIKE OR + match-count 합산.

    PARTITION BY namespace 로 namespace 별 top_k_per_ns 보장.
    """
    placeholders = " OR ".join(f"a.text ILIKE ${i+2}" for i in range(num_keywords))
    match_sum = " + ".join(
        f"(CASE WHEN a.text ILIKE ${i+2} THEN 1 ELSE 0 END)"
        for i in range(num_keywords)
    )
    return f"""
    SELECT * FROM (
        SELECT
            c.namespace,
            c.law_name,
            a.id::text         AS chunk_id,
            a.article_label,
            a.text,
            ({match_sum})::int AS m,
            ROW_NUMBER() OVER (
                PARTITION BY c.namespace
                ORDER BY ({match_sum}) DESC, length(a.text) ASC
            ) AS rn
        FROM f1_law_articles a
        JOIN f1_law_cache c ON c.id = a.law_cache_id
        WHERE c.namespace = ANY($1)
          AND ({placeholders})
    ) sub
    WHERE sub.rn <= {top_k_per_ns}
    ORDER BY sub.m DESC, length(sub.text) ASC
    """


async def _search(keywords: list[str], top_k: int) -> list[dict]:
    """키워드 ILIKE 매칭 — 키워드 0개면 빈 리스트 (P6: fallback 제거).

    fallback (각 namespace 첫 1건) 은 무관 article 을 반환해 사용자에게
    혼란을 주므로 제거했다. 키워드가 비어 있으면 정직하게 인용 없음.
    """
    if not keywords:
        return []

    dsn = _dsn()
    if not dsn:
        logger.warning("Step D: DATABASE_URL 미설정 — citations=[]")
        return []

    conn = await asyncpg.connect(dsn, statement_cache_size=0, command_timeout=15)
    try:
        sql = _build_search_sql(len(keywords), top_k_per_ns=top_k)
        patterns = [f"%{k}%" for k in keywords]
        rows = await conn.fetch(sql, _NAMESPACES, *patterns)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def run_step_d(
    query_context: QueryContext,
    top_k: int = 5,
) -> StepDResult:
    """f1_law_articles 키워드 매칭 → 점수 상위 top_k 인용 반환.

    Args:
        query_context: Step A/B/C 결정론적 결과 요약.
        top_k: 최종 반환 건수. namespace 별 top_k 씩 가져온 뒤 점수 정렬.

    Returns:
        StepDResult — citations (LawCitation 리스트). 판정 주도 없음.
    """
    keywords = _extract_keywords(query_context)
    query_text = build_query(query_context)
    logger.debug("Step D 쿼리: %s (keywords=%s)", query_text, keywords)

    try:
        rows = await _search(keywords, top_k=top_k)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Step D 검색 실패 (%s: %s) — citations=[], 파이프라인 계속",
            type(exc).__name__,
            exc,
        )
        return StepDResult(citations=[])

    if not rows:
        return StepDResult(citations=[])

    n_kw = max(len(keywords), 1)
    citations: list[LawCitation] = []
    for r in rows:
        score = float(r["m"]) / n_kw if keywords else 0.0
        citations.append(
            LawCitation(
                chunk_id=r["chunk_id"],
                law_name=r["law_name"],
                article_no=r["article_label"],
                text=r["text"],
                score=score,
                namespace=r["namespace"],
            )
        )

    citations.sort(key=lambda c: c.score, reverse=True)
    citations = citations[:top_k]

    logger.debug("Step D 완료: %d건 반환", len(citations))
    return StepDResult(citations=citations)
