"""safetydata.go.kr 공전 스냅샷 조회 클라이언트.

scripts/f1_sync_safetydata.py 가 적재한 Postgres 스냅샷 테이블에서
원재료명 기반 검색을 수행한다. data.go.kr 15116583 의 서버측 필터가 미작동하여
클라이언트 필터링 방식으로 대체.

조회 테이블:
    - f1_safetydata_food_code                   (식품공전 DSSP-IF-20140)
    - f1_safetydata_food_additive               (식품첨가물공전 DSSP-IF-20138)
    - f1_safetydata_health_functional_food      (건강기능식품공전 DSSP-IF-20137)

검색 전략:
    1. `item_nm ILIKE '%{name}%'` — trgm gin 인덱스 활용
    2. 결과가 너무 넓으면 정확일치 우선 필터
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import asyncpg

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


def _dsn() -> str:
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("F1_DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL/F1_DATABASE_URL 환경변수가 필요합니다.")
    return dsn


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(_dsn(), statement_cache_size=0, command_timeout=30)


async def lookup_food_code(
    name: str,
    *,
    exact_first: bool = True,
    limit: int = 200,
) -> list[FoodCodeStandard]:
    """식품공전에서 원재료명 부분일치 조회.

    Args:
        name: 원재료명 (예: "밀가루").
        exact_first: True 이면 정확일치만 우선, 없을 때 부분일치로 폴백.
        limit: 최대 반환 건수.

    Returns:
        FoodCodeStandard 리스트. 같은 품목의 여러 시험항목이 각각 1 row.
    """
    name = (name or "").strip()
    if not name:
        return []

    conn = await _connect()
    try:
        if exact_first:
            rows = await conn.fetch(
                "SELECT item_nm, test_artcl, spcs_artcl, item_artcl_atrb, "
                "crtr_spcfct_vl, spcfct_vl_smry, jgmt_frm, max_vl, min_vl, "
                "blw_belo, moth_excs, hzr_yn, unit_nm, vld_strt_ymd, vld_end_ymd "
                "FROM f1_safetydata_food_code WHERE item_nm = $1 LIMIT $2",
                name, limit,
            )
            if rows:
                return [FoodCodeStandard(**dict(r)) for r in rows]

        rows = await conn.fetch(
            "SELECT item_nm, test_artcl, spcs_artcl, item_artcl_atrb, "
            "crtr_spcfct_vl, spcfct_vl_smry, jgmt_frm, max_vl, min_vl, "
            "blw_belo, moth_excs, hzr_yn, unit_nm, vld_strt_ymd, vld_end_ymd "
            "FROM f1_safetydata_food_code WHERE item_nm ILIKE $1 LIMIT $2",
            f"%{name}%", limit,
        )
        return [FoodCodeStandard(**dict(r)) for r in rows]
    finally:
        await conn.close()


async def lookup_food_additive(
    name: str,
    *,
    exact_first: bool = True,
    limit: int = 200,
) -> list[FoodAdditiveStandard]:
    """식품첨가물공전에서 첨가물명 부분일치 조회.

    첨가물로 구분되는 원재료(예: 벤조산, 소르빈산 등)를 조회할 때 사용.
    """
    name = (name or "").strip()
    if not name:
        return []

    conn = await _connect()
    try:
        if exact_first:
            rows = await conn.fetch(
                "SELECT item_korn_nm, test_artcl_korn_nm, spcs_artcl_nm, "
                "crtr_spcfct_vl, crtr_spcfct_vl_smry, max_vl, min_vl, "
                "unit_nm, hzr_yn, src "
                "FROM f1_safetydata_food_additive WHERE item_korn_nm = $1 LIMIT $2",
                name, limit,
            )
            if rows:
                return [FoodAdditiveStandard(**dict(r)) for r in rows]

        rows = await conn.fetch(
            "SELECT item_korn_nm, test_artcl_korn_nm, spcs_artcl_nm, "
            "crtr_spcfct_vl, crtr_spcfct_vl_smry, max_vl, min_vl, "
            "unit_nm, hzr_yn, src "
            "FROM f1_safetydata_food_additive WHERE item_korn_nm ILIKE $1 LIMIT $2",
            f"%{name}%", limit,
        )
        return [FoodAdditiveStandard(**dict(r)) for r in rows]
    finally:
        await conn.close()


async def lookup_combined(
    name: str,
    *,
    limit: int = 200,
) -> dict[str, list]:
    """식품공전 + 식품첨가물공전을 병합 조회.

    Returns:
        {"food_code": [...], "food_additive": [...]} 형태.
    """
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
