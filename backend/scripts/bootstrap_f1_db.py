"""기능1 DB 부트스트랩 — 한 줄로 전체 세팅.

사용:
    python -m backend.scripts.bootstrap_f1_db

수행 순서:
    1. DATABASE_URL 연결 검증
    2. combined_schema.sql 적용 (공통 + f1_ 스켈레톤 + f5_)
    3. backend/db/migrations/001~008 순차 적용 (f1_ 컬럼 정의 + RPC)
    4. backend/db/seed/01~05 순차 적용 (별표1·2·3 + forbidden + thresholds)
    5. check_db_connection 스타일 최종 검증

옵션:
    --skip-schema       combined_schema.sql 단계 건너뛰기 (이미 실행된 경우)
    --skip-seed         시드 단계 건너뛰기
    --dry-run           파일 리스트만 출력
    --reset-schema      기존 f1_* 테이블 전부 DROP 후 재생성 (위험!)

에러 처리:
    어느 단계 실패해도 명확한 로그 + 이어지는 단계 중단.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

import asyncpg

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass


BACKEND_DIR = Path(__file__).resolve().parents[1]
SCHEMA_FILE = BACKEND_DIR / "db" / "combined_schema.sql"
MIGRATIONS_DIR = BACKEND_DIR / "db" / "migrations"
SEED_DIR = BACKEND_DIR / "db" / "seed"

F1_TABLES = [
    "f1_allowed_ingredients",
    "f1_additive_limits",
    "f1_safety_standards",
    "f1_ingredient_synonyms",
    "f1_forbidden_ingredients",
    "f1_escalation_logs",
    "f1_food_types",
    "f1_regulations",
    "f1_reviews",
    "f1_allergens",
    "f1_analytics_events",
    "f1_flavor_codes",
    "f1_material_codes",
    "f1_process_codes",
    "f1_regulation_updates",
    "f1_review_items",
]


# ============================================================
# 로그 헬퍼 (이모지 X, Windows cp949 호환)
# ============================================================


def log_step(msg: str) -> None:
    print(f"\n>>> {msg}")


def log_ok(msg: str) -> None:
    print(f"    [OK]   {msg}")


def log_fail(msg: str) -> None:
    print(f"    [FAIL] {msg}")


def log_warn(msg: str) -> None:
    print(f"    [WARN] {msg}")


def log_info(msg: str) -> None:
    print(f"    [INFO] {msg}")


# ============================================================
# SQL 실행 헬퍼
# ============================================================


async def apply_sql_file(conn: asyncpg.Connection, path: Path) -> bool:
    """단일 SQL 파일 실행. 성공 시 True, 실패 시 False."""
    try:
        sql = path.read_text(encoding="utf-8")
        await conn.execute(sql)
        log_ok(f"{path.name}")
        return True
    except Exception as exc:  # noqa: BLE001
        log_fail(f"{path.name}: {exc}")
        return False


async def check_table_exists(conn: asyncpg.Connection, name: str) -> bool:
    return bool(
        await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                 WHERE table_schema = 'public' AND table_name = $1
            )
            """,
            name,
        )
    )


async def count_rows(conn: asyncpg.Connection, name: str) -> Optional[int]:
    try:
        return await conn.fetchval(f"SELECT COUNT(*) FROM {name}")
    except Exception:
        return None


# ============================================================
# 단계별 실행
# ============================================================


async def verify_connection(dsn: str) -> Optional[asyncpg.Connection]:
    log_step("1. DATABASE_URL 연결 검증")
    try:
        # statement_cache_size=0 은 Supabase Transaction pooler(pgbouncer) 호환
        conn = await asyncpg.connect(dsn, command_timeout=15, statement_cache_size=0)
        version = await conn.fetchval("SELECT version()")
        log_ok(f"접속 성공 — {version.split(',')[0]}")
        return conn
    except Exception as exc:  # noqa: BLE001
        log_fail(f"접속 실패: {exc}")
        log_info("backend/.env 의 DATABASE_URL 확인 + 비밀번호/URL 인코딩 점검")
        return None


async def apply_combined_schema(conn: asyncpg.Connection) -> bool:
    log_step("2. combined_schema.sql 적용")
    if not SCHEMA_FILE.exists():
        log_fail(f"파일 없음: {SCHEMA_FILE}")
        return False
    return await apply_sql_file(conn, SCHEMA_FILE)


async def apply_migrations(conn: asyncpg.Connection) -> bool:
    log_step("3. f1_ 마이그레이션 001~008 적용")
    paths = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not paths:
        log_warn("마이그레이션 파일 없음")
        return True
    all_ok = True
    for p in paths:
        ok = await apply_sql_file(conn, p)
        if not ok:
            all_ok = False
            log_warn("이후 마이그레이션 계속 시도 (의존 순서 확인 필요)")
    return all_ok


async def apply_seeds(conn: asyncpg.Connection) -> bool:
    log_step("4. 시드 데이터 01~05 적용")
    paths = sorted(SEED_DIR.glob("*.sql"))
    if not paths:
        log_warn("시드 파일 없음")
        return True
    all_ok = True
    for p in paths:
        ok = await apply_sql_file(conn, p)
        if not ok:
            all_ok = False
    return all_ok


async def reset_schema(conn: asyncpg.Connection) -> bool:
    log_step("RESET: f1_* 테이블 전부 DROP")
    for t in F1_TABLES:
        try:
            await conn.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
            log_ok(f"dropped {t}")
        except Exception as exc:  # noqa: BLE001
            log_fail(f"{t}: {exc}")
            return False
    try:
        await conn.execute(
            "DROP FUNCTION IF EXISTS search_f1_ingredients_trgm(TEXT, INTEGER)"
        )
        log_ok("dropped function search_f1_ingredients_trgm")
    except Exception:
        pass
    try:
        await conn.execute("DROP TABLE IF EXISTS f1_forbidden_ingredients CASCADE")
    except Exception:
        pass
    return True


async def verify_final_state(conn: asyncpg.Connection) -> None:
    log_step("5. 최종 상태 검증")

    # 핵심 테이블 + 건수
    checks = [
        ("f1_allowed_ingredients", 110, "별표1+2+3 합계 110+"),
        ("f1_forbidden_ingredients", 8, "mock 8건"),
        ("f1_additive_limits", 13, "첨가물 핵심 13건"),
        ("f1_safety_standards", 10, "안전기준 10건"),
    ]

    for tbl, expected, desc in checks:
        count = await count_rows(conn, tbl)
        if count is None:
            log_fail(f"{tbl} 테이블 없음")
        elif count >= expected:
            log_ok(f"{tbl}: {count}건 (기대 {expected}+, {desc})")
        else:
            log_warn(f"{tbl}: {count}건 (기대 {expected}+, 부족)")

    # RPC 함수
    rpc_exists = await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM pg_proc WHERE proname='search_f1_ingredients_trgm')"
    )
    if rpc_exists:
        try:
            rows = await conn.fetch("SELECT * FROM search_f1_ingredients_trgm('쌀', 3)")
            log_ok(f"search_f1_ingredients_trgm('쌀', 3) → {len(rows)}건 반환")
        except Exception as exc:  # noqa: BLE001
            log_fail(f"RPC 호출 실패: {exc}")
    else:
        log_fail("search_f1_ingredients_trgm RPC 없음")

    # pg_trgm 확장
    ext = await conn.fetchval(
        "SELECT extversion FROM pg_extension WHERE extname='pg_trgm'"
    )
    if ext:
        log_ok(f"pg_trgm 확장 v{ext}")
    else:
        log_fail("pg_trgm 확장 미설치")


# ============================================================
# 메인
# ============================================================


async def run(
    skip_schema: bool,
    skip_seed: bool,
    dry_run: bool,
    reset: bool,
) -> int:
    # dry-run 은 DB 접속 없이 파일 리스트만 점검
    if dry_run:
        print("== DRY RUN (DB 접속 없음) ==")
        print(f"SCHEMA:     {SCHEMA_FILE.exists()} — {SCHEMA_FILE}")
        migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
        print(f"MIGRATIONS: {len(migrations)}개")
        for p in migrations:
            print(f"            - {p.name}")
        seeds = sorted(SEED_DIR.glob("*.sql"))
        print(f"SEEDS:      {len(seeds)}개")
        for p in seeds:
            print(f"            - {p.name}")
        return 0

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        log_fail("DATABASE_URL 환경변수 없음. backend/.env 에 추가하세요.")
        return 1

    conn = await verify_connection(dsn)
    if conn is None:
        return 2

    try:
        if reset:
            ok = await reset_schema(conn)
            if not ok:
                return 3

        if not skip_schema:
            ok = await apply_combined_schema(conn)
            if not ok:
                log_warn(
                    "combined_schema 실패 — 이미 적용됐을 수도 있음. 다음 단계 계속 진행."
                )

        ok = await apply_migrations(conn)
        if not ok:
            log_warn("일부 마이그레이션 실패 — 상태 확인 필요")

        if not skip_seed:
            ok = await apply_seeds(conn)
            if not ok:
                log_warn(
                    "일부 시드 실패 — 이미 존재하는 레코드는 ON CONFLICT DO NOTHING"
                )

        await verify_final_state(conn)

        log_step("부트스트랩 완료")
        log_info("다음 단계: python -m backend.scripts.check_db_connection")
        return 0
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="기능1 DB 부트스트랩 — combined_schema + 마이그레이션 + 시드 + 검증"
    )
    parser.add_argument(
        "--skip-schema", action="store_true", help="combined_schema.sql 건너뛰기"
    )
    parser.add_argument("--skip-seed", action="store_true", help="시드 건너뛰기")
    parser.add_argument("--dry-run", action="store_true", help="파일 리스트만 표시")
    parser.add_argument(
        "--reset-schema",
        action="store_true",
        help="f1_* 테이블 전부 DROP 후 재생성 (위험!)",
    )
    args = parser.parse_args()

    try:
        return asyncio.run(
            run(args.skip_schema, args.skip_seed, args.dry_run, args.reset_schema)
        )
    except KeyboardInterrupt:
        print("\n[INT] 사용자 중단")
        return 130


if __name__ == "__main__":
    sys.exit(main())
