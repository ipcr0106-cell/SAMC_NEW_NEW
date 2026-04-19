"""Step A — 금지원료 체크 서비스 (W2-A 본체 구현).

2중 안전망:
    1차: Supabase `f1_forbidden_ingredients` DB 조회 (name_ko strip+lowercase 매칭)
    2차: data.go.kr 15111777 `get_import_food_ingredient` 병렬 호출
         → EDIBLE_INFO == "불가" 또는 EDIBLE_N == "o" 항목 필터
    합집합 중복 제거 (name 기준, source="db" 우선)

sub_ingredients 재귀 평탄화로 복합원재료 하위 성분까지 모두 검사.
API 장애 시 api_errors 에 기록하고 DB 결과로만 판정 (파이프라인 차단 없음).

참조:
    - 계획/f1 재설계 계획/01_Step_A_금지원료_설계.md
    - 계획/f1 재설계 계획/06_API_클라이언트_설계.md §5 (15111777)
    - calling: backend/services/feature1.py `run_feature1_v2`
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from db.supabase_client import get_supabase
from exceptions import DataGoKrError
from models.f1_types import ForbiddenHit, StepAResult
from models.judgment import Ingredient
from services.data_go_kr import DataGoKrClient, IngredientInfo

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


def _build_client() -> DataGoKrClient:
    """환경변수에서 DataGoKrClient 생성 (기본 생성 경로)."""
    api_key = os.environ.get("F1_DATA_GO_KR_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "F1_DATA_GO_KR_API_KEY 환경변수가 설정되지 않았습니다."
        )
    return DataGoKrClient(api_key=api_key)


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
# API 교차확인
# ---------------------------------------------------------------------------


async def _query_api_forbidden_single(
    ing: Ingredient,
    client: DataGoKrClient,
) -> tuple[list[ForbiddenHit], str | None]:
    """원재료 1건에 대해 15111777 호출 후 EDIBLE_INFO/EDIBLE_N 필터 적용.

    Returns:
        (hits, error_str) — 정상 시 (hits, None), 장애 시 ([], "에러 메시지")
    """
    name = ing.name.strip()
    try:
        result = await client.get_import_food_ingredient(name)
    except DataGoKrError as exc:
        return [], f"{name}: {exc.code}"
    except Exception as exc:
        return [], f"{name}: {exc!s}"

    hits: list[ForbiddenHit] = []
    for raw_item in result.get("items", []):
        try:
            item = IngredientInfo.model_validate(raw_item)
        except Exception:
            continue

        edible_info = (item.edible_info or "").strip()
        edible_n = (item.edible_n or "").strip().lower()

        if edible_info == "불가" or edible_n == "o":
            matched_name = (item.ingd_nm or name).strip()
            reason = "DB 미등록 — 최신 API 기준 금지"
            if edible_info == "불가":
                reason = "식품원료 사용 불가 (EDIBLE_INFO=불가)"
            elif edible_n == "o":
                reason = "수입 불가 원료 (EDIBLE_N=o)"

            hits.append(
                ForbiddenHit(
                    ingredient_name=name,
                    matched_name=matched_name,
                    source="api",
                    reason=reason,
                    law_ref=None,
                )
            )

    return hits, None


async def _query_api_forbidden(
    flat_ingredients: list[Ingredient],
    client: DataGoKrClient,
) -> tuple[list[ForbiddenHit], list[str]]:
    """모든 원재료를 asyncio.gather 병렬 호출하여 API 금지 원료 수집.

    Returns:
        (api_hits, api_errors)
    """
    tasks = [
        _query_api_forbidden_single(ing, client)
        for ing in flat_ingredients
        if ing.name.strip()
    ]
    if not tasks:
        return [], []

    results = await asyncio.gather(*tasks)

    all_hits: list[ForbiddenHit] = []
    all_errors: list[str] = []
    for hits, err in results:
        all_hits.extend(hits)
        if err:
            all_errors.append(err)

    return all_hits, all_errors


# ---------------------------------------------------------------------------
# 합집합 중복 제거
# ---------------------------------------------------------------------------


def _merge_hits(
    db_hits: list[ForbiddenHit],
    api_hits: list[ForbiddenHit],
) -> list[ForbiddenHit]:
    """DB + API 합집합. ingredient_name 기준 중복 제거 (source="db" 우선).

    동일 원재료명이 DB/API 양쪽에서 hit 된 경우 DB 결과를 유지.
    API only hit 는 "DB 미등록" 경고 문구를 reason 에 포함.
    """
    merged: dict[str, ForbiddenHit] = {}

    # 1. DB hit 먼저 등록 (우선순위)
    for hit in db_hits:
        merged[hit.ingredient_name] = hit

    # 2. API hit 는 DB에 없는 경우만 추가
    for hit in api_hits:
        if hit.ingredient_name not in merged:
            # DB 미등록 경고 접두어
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
    """2중 안전망: Supabase `f1_forbidden_ingredients` + data.go.kr 15111777 교차.

    Args:
        ingredients: F0 원재료 목록 (sub_ingredients 포함).
        client: 테스트 주입용 DataGoKrClient. None 이면 환경변수에서 자동 생성.

    Returns:
        StepAResult — forbidden_hits 1건 이상이면 stopped=True.

    Day 0 시그니처 유지:
        - 필수 인자 `ingredients: list[Ingredient]` 위치·이름 변경 없음.
        - `client` 는 keyword-only + default=None 으로만 추가.
    """
    if not ingredients:
        return StepAResult(forbidden_hits=[], stopped=False, law_refs=[], api_errors=[])

    # ── 1. sub_ingredients 평탄화 ──────────────────────────────────────
    flat: list[Ingredient] = _flatten_ingredients(ingredients)
    names_normalized = [_normalize(ing.name) for ing in flat if ing.name.strip()]

    # ── 2. DB 조회 (동기 Supabase → asyncio.to_thread 로 블록 해제) ────
    db_rows: list[dict] = await asyncio.to_thread(_query_db_forbidden, names_normalized)

    # DB 결과를 ForbiddenHit 로 변환
    # name 역조회: normalized → 원본 name 매핑
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
                law_ref=row.get("law_source"),  # DB 실제 컬럼명: law_source
            )
        )

    # ── 3. API 교차확인 (병렬) ────────────────────────────────────────
    _owned_client: Optional[DataGoKrClient] = None
    api_hits: list[ForbiddenHit] = []
    api_errors: list[str] = []

    try:
        if client is None:
            try:
                _owned_client = _build_client()
                active_client = _owned_client
            except RuntimeError as exc:
                # API 키 미설정 → api_errors 에 기록, DB 결과로만 판정
                api_errors.append(f"API 클라이언트 초기화 실패: {exc}")
                active_client = None
        else:
            active_client = client

        if active_client is not None:
            api_hits, api_errors_from_call = await _query_api_forbidden(flat, active_client)
            api_errors.extend(api_errors_from_call)
    finally:
        if _owned_client is not None:
            await _owned_client.aclose()

    # ── 4. 합집합 중복 제거 ───────────────────────────────────────────
    all_hits = _merge_hits(db_hits, api_hits)

    # ── 5. law_refs 수집 ─────────────────────────────────────────────
    law_refs = list(
        {hit.law_ref for hit in all_hits if hit.law_ref}
    )

    # ── 6. stopped 판정 ──────────────────────────────────────────────
    stopped = len(all_hits) > 0

    return StepAResult(
        forbidden_hits=all_hits,
        stopped=stopped,
        law_refs=law_refs,
        api_errors=api_errors,
    )
