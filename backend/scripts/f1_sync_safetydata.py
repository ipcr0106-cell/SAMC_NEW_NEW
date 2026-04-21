"""safetydata.go.kr DSSP-IF 공전 3종 전수 스냅샷 동기화 스크립트.

실행:
    cd backend
    python -m scripts.f1_sync_safetydata                # 3개 API 전부 동기화
    python -m scripts.f1_sync_safetydata --only food_code
    python -m scripts.f1_sync_safetydata --dry-run      # API만 호출, DB 쓰기 X

배경:
    data.go.kr 15111777/15116583의 서버측 필터가 미작동하여 원재료 판정 실패.
    safetydata.go.kr는 필터 기능이 없는 벌크 API이므로 전수 다운로드 후
    Postgres trgm 인덱스로 클라이언트 검색.

테이블: migrations/019_f1_safetydata_snapshot.sql 참조
    - f1_safetydata_food_code          (DSSP-IF-20140 식품공전)
    - f1_safetydata_food_additive      (DSSP-IF-20138 식품첨가물공전)
    - f1_safetydata_health_functional_food (DSSP-IF-20137 건강기능식품공전)
    - f1_safetydata_sync_log           (실행 이력)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import asyncpg
import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("f1_sync_safetydata")


BASE_URL = "https://www.safetydata.go.kr/V2/api"
PAGE_SIZE = 1000  # 서버 상한 — 1000 초과 요청해도 1000만 반환됨


@dataclass(frozen=True)
class Endpoint:
    key: str                 # short name (e.g., "food_code")
    service_id: str          # "DSSP-IF-20140"
    env_var: str             # env 변수 이름
    table: str               # Supabase 테이블
    column_map: dict[str, str]  # API field → DB column


ENDPOINTS: list[Endpoint] = [
    Endpoint(
        key="food_code",
        service_id="DSSP-IF-20140",
        env_var="F1_LAW_FOOD_CODE_API_KEY",
        table="f1_safetydata_food_code",
        column_map={
            "ITEM_NM": "item_nm",
            "TEST_ARTCL": "test_artcl",
            "SPCS_ARTCL": "spcs_artcl",
            "ITEM_ARTCL_ATRB": "item_artcl_atrb",
            "CRTR_SPCFCT_VL": "crtr_spcfct_vl",
            "SPCFCT_VL_SMRY": "spcfct_vl_smry",
            "JGMT_FRM": "jgmt_frm",
            "MAX_VL": "max_vl",
            "MIN_VL": "min_vl",
            "BLW_BELO": "blw_belo",
            "MOTH_EXCS": "moth_excs",
            "SPCS_STBLT": "spcs_stblt",
            "ICPT": "icpt",
            "HZR_YN": "hzr_yn",
            "UNIT_NM": "unit_nm",
            "VLD_STRT_YMD": "vld_strt_ymd",
            "VLD_END_YMD": "vld_end_ymd",
        },
    ),
    Endpoint(
        key="food_additive",
        service_id="DSSP-IF-20138",
        env_var="F1_LAW_FOOD_ADDITIVE_API_KEY",
        table="f1_safetydata_food_additive",
        column_map={
            "ITEM_CD": "item_cd",
            "ITEM_KORN_NM": "item_korn_nm",
            "TEST_ARTCL_CD": "test_artcl_cd",
            "TEST_ARTCL_KORN_NM": "test_artcl_korn_nm",
            "SPCS_ARTCL_NM": "spcs_artcl_nm",
            "CRTR_SPCFCT_VL": "crtr_spcfct_vl",
            "CRTR_SPCFCT_VL_SMRY": "crtr_spcfct_vl_smry",
            "MIN_VL": "min_vl",
            "MAX_VL": "max_vl",
            "UNIT_NM": "unit_nm",
            "HZR_YN": "hzr_yn",
            "SRC": "src",
            "VLD_STRT_YMD": "vld_strt_ymd",
            "VLD_END_YMD": "vld_end_ymd",
        },
    ),
    Endpoint(
        key="health_functional_food",
        service_id="DSSP-IF-20137",
        env_var="F1_LAW_HEALTH_FUNCTIONAL_FOOD_API_KEY",
        table="f1_safetydata_health_functional_food",
        column_map={
            "ITEM_CD": "item_cd",
            "ITEM_KORN_NM": "item_korn_nm",
            "TEST_ARTCL_CD": "test_artcl_cd",
            "TEST_ARTCL_KORN_NM": "test_artcl_korn_nm",
            "SPCS_ARTCL_NM": "spcs_artcl_nm",
            "CRTR_SPCFCT_VL": "crtr_spcfct_vl",
            "CRTR_SPCFCT_VL_SMRY": "crtr_spcfct_vl_smry",
            "MIN_VL": "min_vl",
            "MAX_VL": "max_vl",
            "UNIT_NM": "unit_nm",
            "HZR_YN": "hzr_yn",
            "SRC": "src",
            "VLD_STRT_YMD": "vld_strt_ymd",
            "VLD_END_YMD": "vld_end_ymd",
        },
    ),
]


async def fetch_page(
    client: httpx.AsyncClient,
    service_id: str,
    api_key: str,
    page_no: int,
) -> dict[str, Any]:
    url = f"{BASE_URL}/{service_id}"
    params = {
        "serviceKey": api_key,
        "returnType": "json",
        "pageNo": str(page_no),
        "numOfRows": str(PAGE_SIZE),
    }
    r = await client.get(url, params=params, timeout=60.0)
    r.raise_for_status()
    return r.json()


async def fetch_all(ep: Endpoint, api_key: str) -> tuple[int, list[dict]]:
    """페이지 순회로 전수 다운로드."""
    async with httpx.AsyncClient() as client:
        first = await fetch_page(client, ep.service_id, api_key, 1)
        total_count = int(first.get("totalCount") or 0)
        if total_count == 0:
            logger.warning("[%s] totalCount=0 — skip", ep.key)
            return 0, []

        pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE
        logger.info("[%s] total=%d pages=%d", ep.key, total_count, pages)

        all_items: list[dict] = list(first.get("body") or [])
        for page in range(2, pages + 1):
            body = await fetch_page(client, ep.service_id, api_key, page)
            items = body.get("body") or []
            all_items.extend(items)
            if page % 10 == 0 or page == pages:
                logger.info(
                    "[%s] page %d/%d received=%d cumulative=%d",
                    ep.key, page, pages, len(items), len(all_items),
                )
        return total_count, all_items


def to_rows(items: Iterable[dict], column_map: dict[str, str]) -> list[dict]:
    rows: list[dict] = []
    for it in items:
        row = {db_col: (it.get(api_fld) if isinstance(it, dict) else None)
               for api_fld, db_col in column_map.items()}
        rows.append(row)
    return rows


def _get_dsn() -> str:
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("F1_DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL/F1_DATABASE_URL 환경변수가 필요합니다.")
    return dsn


async def write_asyncpg(table: str, rows: list[dict], columns: list[str]) -> int:
    """TRUNCATE + COPY 사용. PostgREST 캐시와 무관."""
    if not rows:
        return 0
    dsn = _get_dsn()
    conn = await asyncpg.connect(dsn, statement_cache_size=0, command_timeout=120)
    try:
        await conn.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY")
        records = [tuple(r.get(c) for c in columns) for r in rows]
        await conn.copy_records_to_table(table, records=records, columns=columns)
        return len(records)
    finally:
        await conn.close()


async def log_sync(endpoint_id: str, total: int, inserted: int, duration_s: int, error: str | None) -> None:
    try:
        dsn = _get_dsn()
        conn = await asyncpg.connect(dsn, statement_cache_size=0, command_timeout=30)
        try:
            await conn.execute(
                "INSERT INTO f1_safetydata_sync_log "
                "(endpoint_id, total_count, inserted_count, duration_s, error) "
                "VALUES ($1, $2, $3, $4, $5)",
                endpoint_id, total, inserted, duration_s, error,
            )
        finally:
            await conn.close()
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("sync_log insert failed: %s", exc)


async def sync_one(ep: Endpoint, *, dry_run: bool) -> None:
    api_key = os.environ.get(ep.env_var, "")
    if not api_key:
        logger.error("[%s] missing env %s", ep.key, ep.env_var)
        return

    start = time.perf_counter()
    error: str | None = None
    total = 0
    inserted = 0
    try:
        total, items = await fetch_all(ep, api_key)
        if dry_run:
            logger.info("[%s] dry-run — received %d items, skipping DB", ep.key, len(items))
            return
        rows = to_rows(items, ep.column_map)
        columns = list(ep.column_map.values())
        inserted = await write_asyncpg(ep.table, rows, columns)
        logger.info("[%s] inserted=%d (total_count=%d)", ep.key, inserted, total)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        logger.exception("[%s] sync failed: %s", ep.key, error)
    finally:
        duration_s = int(time.perf_counter() - start)
        if not dry_run:
            await log_sync(ep.service_id, total, inserted, duration_s, error)


async def main_async(only: str | None, dry_run: bool) -> None:
    targets = [ep for ep in ENDPOINTS if only is None or ep.key == only]
    if not targets:
        logger.error("unknown --only key: %s", only)
        sys.exit(2)
    for ep in targets:
        await sync_one(ep, dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="safetydata.go.kr 공전 3종 전수 동기화")
    parser.add_argument("--only", choices=[ep.key for ep in ENDPOINTS], default=None,
                        help="특정 API 하나만 동기화")
    parser.add_argument("--dry-run", action="store_true", help="API만 호출, DB 쓰기 생략")
    args = parser.parse_args()
    asyncio.run(main_async(args.only, args.dry_run))


if __name__ == "__main__":
    main()
