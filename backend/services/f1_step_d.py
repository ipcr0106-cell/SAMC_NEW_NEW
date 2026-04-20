"""Step D — 법령 인용 (W2-D 본체, 2026-04-20 P7 관련도 가드).

P7 (2026-04-20) — 관련도 가드 도입:
    - stopword 필터 ({"제품","식품","원료","물","염",...}) + 최소길이 (한글 2/영문 3)
    - 가중치: food_type ×3, ingredient_name ×2, 기타 ×1
    - namespace 라우팅: 일반식품 기본 food_code_text, ingredient_codes 시 첨가물,
      food_type "건강기능"·"기능성" 힌트 또는 profile_flags 로 opt-in
    - score < 0.2 (가중 매칭 20%) 컷
    - tie-break: 점수 DESC → 본문 length DESC (의미 있는 본문 우선)

설계 변경 (P6 계승):
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

from common.result import Result
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

# ─────────────────────────────────────────────────────────────
# P7 (2026-04-20) — 법령 인용 관련도 가드
#
# 배경:
#   P6 까지 ILIKE 부분문자열 매칭 + namespace 별 PARTITION top_k 로
#   "밀가루" 쿼리에 건기식/한시기준 별표가 섞여 반환되는 회귀 발생.
#   stopword·가중치·threshold·tie-break·namespace routing 을 한꺼번에
#   도입해 무관 인용을 차단한다.
# ─────────────────────────────────────────────────────────────

# 너무 일반적이어서 거의 모든 법령 본문에 히트하는 토큰 (noise 키워드 제거)
_STOPWORDS: frozenset[str] = frozenset({
    "제품", "식품", "원료", "물", "염", "분말", "혼합물",
    "기타", "일반", "성분", "첨가물", "가공", "제조", "함유", "사용",
})

# 의미 있는 매칭 보장: 한글은 2자, 영문/숫자 혼합은 3자 이상
_MIN_LEN_HANGUL = 2
_MIN_LEN_LATIN = 3

# 키워드 가중치 — food_type (핵심 분류) > ingredient_name > 기타
_W_FOOD_TYPE = 3
_W_INGREDIENT_NAME = 2
_W_DEFAULT = 1

# 일반식품 기본 namespace — food_type/ingredient_codes/profile_flags 로 확장
_NAMESPACE_DEFAULT: list[str] = ["food_code_text"]


def _has_hangul(s: str) -> bool:
    return any("\uac00" <= c <= "\ud7a3" for c in s)


def _is_valid_keyword(kw: str) -> bool:
    """stopword 제외, 최소길이 필터."""
    kw = kw.strip()
    if not kw or kw in _STOPWORDS:
        return False
    min_len = _MIN_LEN_HANGUL if _has_hangul(kw) else _MIN_LEN_LATIN
    return len(kw) >= min_len


def _select_namespaces(ctx: "QueryContext") -> list[str]:
    """product profile 기반 검색 대상 namespace 선별.

    - 기본: food_code_text
    - ingredient_codes 있으면: additive_code_text 추가 (첨가물 공전)
    - food_type 에 "건강기능"/"건강보조": health_food_text
    - food_type 에 "기능성"/"기능성표시": functional_labeling
    - profile_flags 로 명시 opt-in 시: health_food / functional_labeling / temporary_standard

    순서 유지 + dedup.
    """
    selected: list[str] = list(_NAMESPACE_DEFAULT)
    if getattr(ctx, "ingredient_codes", None):
        selected.append("additive_code_text")

    ft = (ctx.food_type or "")
    if "건강기능" in ft or "건강보조" in ft:
        selected.append("health_food_text")
    if "기능성" in ft:
        selected.append("functional_labeling")

    for flag in (getattr(ctx, "profile_flags", None) or []):
        if flag == "health_food":
            selected.append("health_food_text")
        elif flag == "functional_labeling":
            selected.append("functional_labeling")
        elif flag == "temporary_standard":
            selected.append("temporary_standard")

    seen: set[str] = set()
    out: list[str] = []
    for ns in selected:
        if ns in _NAMESPACES and ns not in seen:
            seen.add(ns)
            out.append(ns)
    return out or list(_NAMESPACE_DEFAULT)


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


def _extract_keywords(ctx: QueryContext) -> list[tuple[str, int]]:
    """QueryContext → (키워드, 가중치) 리스트.

    P7 (2026-04-20):
        - stopword 제거 + 최소길이 (한글 2 / 영문·숫자 3) 필터
        - food_type × 3, ingredient_name × 2, 기타 × 1 가중치
        - 중복 키워드는 최대 가중치로 dedup

    P6 (2026-04-20):
        - ingredient_names / ingredient_codes 추가 (원재료명·코드 직접 매칭)
        - failed_standards "name:test" 형태는 ':' 로 분해
    """
    food_type = (ctx.food_type or "").strip()
    ingredient_names: set[str] = {
        n.strip() for n in (getattr(ctx, "ingredient_names", []) or []) if n
    }

    raw: list[str] = []
    if food_type:
        raw.append(food_type)
    raw.extend(ingredient_names)
    raw.extend(c for c in (getattr(ctx, "ingredient_codes", []) or []) if c)
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

    weighted: dict[str, int] = {}
    for k in raw:
        k = k.strip()
        if not _is_valid_keyword(k):
            continue
        if food_type and k == food_type:
            w = _W_FOOD_TYPE
        elif k in ingredient_names:
            w = _W_INGREDIENT_NAME
        else:
            w = _W_DEFAULT
        # 같은 키워드가 여러 역할로 들어오면 최대 가중치 유지
        if w > weighted.get(k, 0):
            weighted[k] = w

    return list(weighted.items())


def _build_search_sql(weights: list[int], top_k_per_ns: int) -> str:
    """동적 SQL — 키워드 K개 + 가중치 → ILIKE OR + 가중 합산.

    PARTITION BY namespace 로 namespace 별 top_k_per_ns 보장.
    tie-break: 가중 매칭합 DESC → 본문 length DESC (P7: 의미 있는 본문 우선).
    """
    placeholders = " OR ".join(f"a.text ILIKE ${i+2}" for i in range(len(weights)))
    weighted_sum = " + ".join(
        f"(CASE WHEN a.text ILIKE ${i+2} THEN {w} ELSE 0 END)"
        for i, w in enumerate(weights)
    )
    return f"""
    SELECT * FROM (
        SELECT
            c.namespace,
            c.law_name,
            a.id::text         AS chunk_id,
            a.article_label,
            a.text,
            ({weighted_sum})::int AS m,
            ROW_NUMBER() OVER (
                PARTITION BY c.namespace
                ORDER BY ({weighted_sum}) DESC, length(a.text) DESC
            ) AS rn
        FROM f1_law_articles a
        JOIN f1_law_cache c ON c.id = a.law_cache_id
        WHERE c.namespace = ANY($1)
          AND ({placeholders})
    ) sub
    WHERE sub.rn <= {top_k_per_ns}
    ORDER BY sub.m DESC, length(sub.text) DESC
    """


async def _search(
    kw_weights: list[tuple[str, int]],
    namespaces: list[str],
    top_k: int,
) -> list[dict]:
    """가중 키워드 ILIKE 매칭 — 키워드 0개 또는 namespace 0개면 빈 리스트.

    fallback (각 namespace 첫 1건) 은 무관 article 을 반환하므로 P6 에서 제거.
    namespace 선별은 호출자 (`_select_namespaces`) 책임.
    """
    if not kw_weights or not namespaces:
        return []

    dsn = _dsn()
    if not dsn:
        logger.warning("Step D: DATABASE_URL 미설정 — citations=[]")
        return []

    keywords = [k for k, _ in kw_weights]
    weights = [w for _, w in kw_weights]

    conn = await asyncpg.connect(dsn, statement_cache_size=0, command_timeout=15)
    try:
        sql = _build_search_sql(weights, top_k_per_ns=top_k)
        patterns = [f"%{k}%" for k in keywords]
        rows = await conn.fetch(sql, namespaces, *patterns)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def run_step_d(
    query_context: QueryContext,
    top_k: int | None = None,
) -> "Result[StepDResult]":
    """f1_law_articles 키워드 매칭 → 점수 상위 top_k 인용 반환.

    Args:
        query_context: Step A/B/C 결정론적 결과 요약.
        top_k: 최종 반환 건수. None 이면 F1_STEP_D_TOP_K_GLOBAL 환경변수(기본 3) 사용.

    Returns:
        Result[StepDResult] — ok 시 citations (LawCitation 리스트). 판정 주도 없음.
        DB 장애 시 Result.err 반환.
    """
    if top_k is None:
        top_k = int(os.getenv("F1_STEP_D_TOP_K_GLOBAL", "3"))

    min_score = float(os.getenv("F1_STEP_D_MIN_SCORE", "0.4"))

    kw_weights = _extract_keywords(query_context)
    namespaces = _select_namespaces(query_context)
    query_text = build_query(query_context)
    logger.debug(
        "Step D 쿼리: %s (keywords=%s, namespaces=%s)",
        query_text, kw_weights, namespaces,
    )

    try:
        rows = await _search(kw_weights, namespaces, top_k=top_k)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Step D 검색 실패 (%s: %s) — citations=[], 파이프라인 계속",
            type(exc).__name__,
            exc,
        )
        return Result.err(f"Step D 검색 실패: {type(exc).__name__}: {exc}")

    if not rows:
        return Result.ok(StepDResult(citations=[]))

    total_weight = sum(w for _, w in kw_weights) or 1
    citations: list[LawCitation] = []
    for r in rows:
        score = float(r["m"]) / total_weight
        # P7: min_score 컷 — 가중 매칭 비율이 min_score 미만이면 무관 인용으로 간주해 제거
        if score < min_score:
            continue
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

    # dedup: 동일 (law_name, article_no) 조합은 score 높은 것 1건만 유지
    seen_keys: set[tuple] = set()
    deduped: list[LawCitation] = []
    for c in sorted(citations, key=lambda x: x.score, reverse=True):
        key = (c.law_name, c.article_no)
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(c)
    citations = deduped

    citations.sort(key=lambda c: (c.score, len(c.text)), reverse=True)
    citations = citations[:top_k]

    logger.debug("Step D 완료: %d건 (threshold=%.2f)", len(citations), min_score)
    return Result.ok(StepDResult(citations=citations))
