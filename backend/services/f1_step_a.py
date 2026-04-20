"""Step A — 금지원료 체크 서비스.

P6-b (2026-04-20): 15111777 호출 제거.
    실측 결과 15111777 은 이름 필터가 작동하지 않고(전체 5,312건 dump 만 반환)
    화학첨가물도 미수록이라 호출 기여가 없음. Step A 는 로컬
    `f1_forbidden_ingredients` DB 조회 단일 소스로 판정.

판정 흐름:
    1. sub_ingredients 재귀 평탄화
    2. Supabase `f1_forbidden_ingredients` 전체 조회 (소규모 DB)
    3. strip+lowercase 정규화 후 정확 매칭
    4. 하나라도 hit → `stopped=True`

참조:
    - 계획/f1 재설계 계획/01_Step_A_금지원료_설계.md
    - calling: backend/services/feature1.py `run_feature1_v2`
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from db.supabase_client import get_supabase
from models.f1_types import ForbiddenHit, StepAResult
from models.judgment import Ingredient
from services.data_go_kr import DataGoKrClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


def _normalize(s: str) -> str:
    """공백 제거 + 소문자 변환 (DB 매칭 정규화)."""
    return s.strip().lower()


def _flatten_ingredients(ingredients: list[Ingredient]) -> list[Ingredient]:
    """sub_ingredients 를 재귀적으로 평탄화하여 최하위 성분까지 1차원 리스트로 반환.

    부모 원재료도 포함 (모든 계층 검사).
    """
    result: list[Ingredient] = []

    def _collect(ings: list[Ingredient]) -> None:
        for ing in ings:
            result.append(ing)
            if ing.sub_ingredients:
                _collect(ing.sub_ingredients)

    _collect(ingredients)
    return result


# ---------------------------------------------------------------------------
# DB 조회
# ---------------------------------------------------------------------------


def _query_db_forbidden(
    names_normalized: list[str],
) -> list[dict]:
    """Supabase `f1_forbidden_ingredients` 테이블에서 금지 원료 조회.

    name_ko 컬럼과 정규화(strip + lowercase) 후 비교.
    테이블 크기가 소규모(<200행)이므로 전체 조회 후 Python 필터.
    """
    supabase = get_supabase()
    rows = (
        supabase.table("f1_forbidden_ingredients")
        .select("name_ko, reason, law_source")
        .execute()
        .data
    )
    if not rows:
        return []

    names_set = set(names_normalized)
    hits: list[dict] = []
    seen: set[str] = set()

    for row in rows:
        db_name_ko: str = row.get("name_ko", "") or ""
        db_norm = _normalize(db_name_ko)
        if db_norm and db_norm in names_set and db_name_ko not in seen:
            seen.add(db_name_ko)
            hits.append(row)

    return hits


# ---------------------------------------------------------------------------
# 레거시 헬퍼 (P6-b 이후 미사용, 테스트 하위 호환용)
# ---------------------------------------------------------------------------


def _merge_hits(
    db_hits: list[ForbiddenHit],
    api_hits: list[ForbiddenHit],
) -> list[ForbiddenHit]:
    """DB + API 합집합. P6-b 이후 API 경로 제거로 api_hits 는 항상 빈 리스트.

    기존 호환을 위해 시그니처 유지 — 테스트에서만 호출될 수 있음.
    """
    merged: dict[str, ForbiddenHit] = {}
    for hit in db_hits:
        merged[hit.ingredient_name] = hit
    for hit in api_hits:
        if hit.ingredient_name not in merged:
            reason = hit.reason
            if "DB 미등록" not in reason:
                reason = f"DB 미등록 — 최신 API 기준 금지 ({reason})"
            merged[hit.ingredient_name] = ForbiddenHit(
                ingredient_name=hit.ingredient_name,
                matched_name=hit.matched_name,
                source="api",
                reason=reason,
                law_ref=hit.law_ref,
            )
    return list(merged.values())


# ---------------------------------------------------------------------------
# 공개 인터페이스
# ---------------------------------------------------------------------------


async def run_step_a(
    ingredients: list[Ingredient],
    *,
    client: Optional[DataGoKrClient] = None,
) -> StepAResult:
    """Supabase `f1_forbidden_ingredients` DB 기반 금지원료 판정.

    P6-b (2026-04-20): 15111777 API 교차검증 제거 (이름 필터 미작동 확인).

    Args:
        ingredients: F0 원재료 목록 (sub_ingredients 포함).
        client: (Deprecated) 하위 호환용 파라미터, 실제로는 사용하지 않음.

    Returns:
        StepAResult — forbidden_hits 1건 이상이면 stopped=True.

    Day 0 시그니처 유지:
        - 필수 인자 `ingredients: list[Ingredient]` 위치·이름 변경 없음.
        - `client` 는 keyword-only + default=None (no-op 으로 보존).
    """
    if not ingredients:
        return StepAResult(
            forbidden_hits=[], stopped=False, law_refs=[], api_errors=[], warnings=[]
        )

    # ── 1. sub_ingredients 평탄화 ──────────────────────────────────────
    flat: list[Ingredient] = _flatten_ingredients(ingredients)
    names_normalized = [_normalize(ing.name) for ing in flat if ing.name.strip()]

    # ── 2. DB 조회 (동기 Supabase → asyncio.to_thread 로 블록 해제) ────
    db_rows: list[dict] = await asyncio.to_thread(_query_db_forbidden, names_normalized)

    # DB 결과를 ForbiddenHit 로 변환 (normalized → 원본 name 매핑)
    norm_to_original: dict[str, str] = {}
    for ing in flat:
        if ing.name.strip():
            norm_to_original[_normalize(ing.name)] = ing.name.strip()

    db_hits: list[ForbiddenHit] = []
    for row in db_rows:
        db_name_ko: str = row.get("name_ko", "") or ""
        db_norm = _normalize(db_name_ko)
        ingredient_name = norm_to_original.get(db_norm, db_name_ko)
        db_hits.append(
            ForbiddenHit(
                ingredient_name=ingredient_name,
                matched_name=db_name_ko,
                source="db",
                reason=row.get("reason") or "금지원료 DB 등재",
                law_ref=row.get("law_source"),
            )
        )

    # ── 3. law_refs 수집 ────────────────────────────────────────────
    law_refs = list({hit.law_ref for hit in db_hits if hit.law_ref})

    # ── 4. stopped 판정 ──────────────────────────────────────────────
    stopped = len(db_hits) > 0

    return StepAResult(
        forbidden_hits=db_hits,
        stopped=stopped,
        law_refs=law_refs,
        api_errors=[],
        warnings=[],
    )
