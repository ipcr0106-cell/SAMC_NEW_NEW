"""Supabase PostgreSQL에 backend/db/migrations/*.sql 을 순차 적용.

용도:
    - 개발 초기: 빈 DB에 기능1 마이그레이션 5종 일괄 적용
    - 재실행 안전: 모든 DDL이 IF NOT EXISTS / OR REPLACE 사용

사용법:
    # 1. .env 파일에 DATABASE_URL 설정
    # 2. 루트에서 실행
    python -m backend.scripts.apply_migrations

    # 특정 파일만
    python -m backend.scripts.apply_migrations --only 003_forbidden_ingredients.sql

    # 시드까지 함께
    python -m backend.scripts.apply_migrations --with-seed

주의:
    - 개발계획서 §2의 기본 schema.sql 이 먼저 실행되어 있어야 함
    - 팀컨벤션 §8: DB 변경 시 전원 합의 필수. 이 스크립트는 합의 후 실행용.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import asyncpg

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    # python-dotenv 미설치 시 OS 환경변수만 사용
    pass


BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = BACKEND_DIR / "db" / "migrations"
SEED_DIR = BACKEND_DIR / "db" / "seed"


async def apply_sql_file(conn: asyncpg.Connection, path: Path) -> None:
    """단일 .sql 파일을 읽어 실행. 실패 시 예외 전파 + 파일명 포함."""
    print(f"  ▶ {path.name} ... ", end="", flush=True)
    try:
        sql = path.read_text(encoding="utf-8")
        await conn.execute(sql)
        print("✅")
    except Exception as exc:  # noqa: BLE001
        print(f"❌\n    에러: {exc}")
        raise


async def run(only: str | None, with_seed: bool, dry_run: bool) -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("❌ DATABASE_URL 환경변수가 없습니다. backend/.env 에 추가하세요.")
        return 1

    if not MIGRATIONS_DIR.exists():
        print(f"❌ 마이그레이션 폴더 없음: {MIGRATIONS_DIR}")
        return 1

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if only:
        migration_files = [p for p in migration_files if p.name == only]
        if not migration_files:
            print(f"❌ --only {only} 해당 파일 없음")
            return 1

    print(f"📋 마이그레이션 {len(migration_files)}개 대상:")
    for p in migration_files:
        print(f"    - {p.name}")

    if with_seed:
        seed_files = sorted(SEED_DIR.glob("*.sql")) if SEED_DIR.exists() else []
        print(f"📋 시드 {len(seed_files)}개 대상:")
        for p in seed_files:
            print(f"    - {p.name}")

    if dry_run:
        print("\n(--dry-run: 실제 실행 없이 종료)")
        return 0

    print("\n🔌 Supabase 접속 중...")
    # statement_cache_size=0: Supabase Transaction pooler(pgbouncer) 호환
    conn = await asyncpg.connect(dsn, command_timeout=60, statement_cache_size=0)
    try:
        version = await conn.fetchval("SELECT version()")
        print(f"  접속됨: {version[:60]}...\n")

        print("🔧 마이그레이션 적용:")
        for path in migration_files:
            await apply_sql_file(conn, path)

        if with_seed:
            print("\n🌱 시드 적용:")
            for path in sorted(SEED_DIR.glob("*.sql")):
                await apply_sql_file(conn, path)

        print("\n✅ 전체 완료")
        return 0
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply SAMC migrations to Supabase")
    parser.add_argument(
        "--only", help="특정 파일만 (예: 003_forbidden_ingredients.sql)"
    )
    parser.add_argument("--with-seed", action="store_true", help="시드까지 함께 적용")
    parser.add_argument(
        "--dry-run", action="store_true", help="파일 리스트만 보고 종료"
    )
    args = parser.parse_args()

    try:
        return asyncio.run(run(args.only, args.with_seed, args.dry_run))
    except KeyboardInterrupt:
        print("\n⚠️ 사용자 중단")
        return 130


if __name__ == "__main__":
    sys.exit(main())
