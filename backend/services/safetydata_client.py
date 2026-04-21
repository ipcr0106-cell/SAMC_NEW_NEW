"""safetydata.go.kr 공전 스냅샷 조회 클라이언트.

scripts/f1_sync_safetydata.py 가 적재한 Supabase 스냅샷 테이블에서
원재료명 기반 검색을 수행한다. data.go.kr 15116583 의 서버측 필터가 미작동하여
클라이언트 필터링 방식으로 대체.

조회 테이블:
    - f1_safetydata_food_code                   (식품공전 DSSP-IF-20140)
    - f1_safetydata_food_additive               (식품첨가물공전 DSSP-IF-20138)
    - f1_safetydata_health_functional_food      (건강기능식품공전 DSSP-IF-20137)

검색 전략:
    1. 정확일치 (eq) 우선
    2. 부분일치 (ilike) 폴백
    Supabase REST API 사용 (DATABASE_URL 불필요)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FoodCodeStandard:
    """f1_safetydata_food_code row (식품공전 기준규격)."""

    item_nm: str
    test_artcl: Optional[str]
    spcs_artcl: Optional[str]
    item_artcl_atrb: Optional[str]
    crtr_spcfct_vl: Optional[str]
    spcfct_vl_smry: Optional[str]
    jgmt_frm: Optional[str]
    max_vl: Optional[str]
    min_vl: Optional[str]
    blw_belo: Optional[str]
    moth_excs: Optional[str]
    hzr_yn: Optional[str]
    unit_nm: Optional[str]
    vld_strt_ymd: Optional[str]
    vld_end_ymd: Optional[str]


@dataclass(frozen=True)
class FoodAdditiveStandard:
    """f1_safetydata_food_additive row (식품첨가물공전 기준)."""

    item_korn_nm: str
    test_artcl_korn_nm: Optional[str]
    spcs_artcl_nm: Optional[str]
    crtr_spcfct_vl: Optional[str]
    crtr_spcfct_vl_smry: Optional[str]
    max_vl: Optional[str]
    min_vl: Optional[str]
    unit_nm: Optional[str]
    hzr_yn: Optional[str]
    src: Optional[str]


_FOOD_CODE_COLS = (
    "item_nm, test_artcl, spcs_artcl, item_artcl_atrb, "
    "crtr_spcfct_vl, spcfct_vl_smry, jgmt_frm, max_vl, min_vl, "
    "blw_belo, moth_excs, hzr_yn, unit_nm, vld_strt_ymd, vld_end_ymd"
)

_ADDITIVE_COLS = (
    "item_korn_nm, test_artcl_korn_nm, spcs_artcl_nm, "
    "crtr_spcfct_vl, crtr_spcfct_vl_smry, max_vl, min_vl, "
    "unit_nm, hzr_yn, src"
)


def _query_sync(table: str, cols: str, column: str, name: str, exact: bool, limit: int) -> list[dict]:
    """Supabase REST API로 동기 조회."""
    sb = get_supabase()
    if exact:
        result = sb.table(table).select(cols).eq(column, name).limit(limit).execute()
    else:
        result = sb.table(table).select(cols).ilike(column, f"%{name}%").limit(limit).execute()
    return result.data or []


async def lookup_food_code(
    name: str,
    *,
    exact_first: bool = True,
    limit: int = 200,
) -> list[FoodCodeStandard]:
    """식품공전에서 원재료명 부분일치 조회."""
    name = (name or "").strip()
    if not name:
        return []

    if exact_first:
        rows = await asyncio.to_thread(
            _query_sync, "f1_safetydata_food_code", _FOOD_CODE_COLS, "item_nm", name, True, limit
        )
        if rows:
            return [FoodCodeStandard(**r) for r in rows]

    rows = await asyncio.to_thread(
        _query_sync, "f1_safetydata_food_code", _FOOD_CODE_COLS, "item_nm", name, False, limit
    )
    return [FoodCodeStandard(**r) for r in rows]


async def lookup_food_additive(
    name: str,
    *,
    exact_first: bool = True,
    limit: int = 200,
) -> list[FoodAdditiveStandard]:
    """식품첨가물공전에서 첨가물명 부분일치 조회."""
    name = (name or "").strip()
    if not name:
        return []

    try:
        if exact_first:
            rows = await asyncio.to_thread(
                _query_sync, "f1_safetydata_food_additive", _ADDITIVE_COLS, "item_korn_nm", name, True, limit
            )
            if rows:
                return [FoodAdditiveStandard(**r) for r in rows]

        rows = await asyncio.to_thread(
            _query_sync, "f1_safetydata_food_additive", _ADDITIVE_COLS, "item_korn_nm", name, False, limit
        )
        return [FoodAdditiveStandard(**r) for r in rows]
    except Exception:
        # f1_safetydata_food_additive 테이블 미존재 시 f1_additive_limits fallback
        logger.info("f1_safetydata_food_additive 미존재 — f1_additive_limits fallback")
        rows = await asyncio.to_thread(
            _query_sync, "f1_additive_limits",
            "additive_name, regulation_ref, condition_text, max_ppm, food_type",
            "additive_name", name, False, limit
        )
        return [
            FoodAdditiveStandard(
                item_korn_nm=r.get("additive_name", ""),
                test_artcl_korn_nm="함량",
                spcs_artcl_nm=None,
                crtr_spcfct_vl=f"{r.get('max_ppm', '')} ppm" if r.get("max_ppm") else None,
                crtr_spcfct_vl_smry=r.get("condition_text"),
                max_vl=str(r["max_ppm"]) if r.get("max_ppm") else None,
                min_vl=None,
                unit_nm="ppm" if r.get("max_ppm") else None,
                hzr_yn=None,
                src=r.get("regulation_ref"),
            )
            for r in rows
        ]


async def lookup_combined(
    name: str,
    *,
    limit: int = 200,
) -> dict[str, list]:
    """식품공전 + 식품첨가물공전을 병합 조회."""
    fc = await lookup_food_code(name, limit=limit)
    fa = await lookup_food_additive(name, limit=limit)
    return {"food_code": fc, "food_additive": fa}


__all__ = [
    "FoodCodeStandard",
    "FoodAdditiveStandard",
    "lookup_food_code",
    "lookup_food_additive",
    "lookup_combined",
]
