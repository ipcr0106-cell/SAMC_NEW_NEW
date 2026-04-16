"""Supabase PostgreSQL 직접 연결 헬퍼 (asyncpg).

용도:
    - 기능1 서비스 레이어의 DB 쿼리 (CRUD + RPC 호출)
    - 마이그레이션·시드 자동 적용 스크립트

주의:
    - SUPABASE_SERVICE_KEY 가 아니라 DATABASE_URL (비밀번호 포함) 필요
    - 서버 전용. 프론트/브라우저에서 절대 사용 금지
    - 팀컨벤션 §9: .env 커밋 금지

환경변수:
    F1_DATABASE_URL - postgresql://postgres:<pwd>@db.<ref>.supabase.co:5432/postgres

사용 예:
    from backend.db.connection import init_pool, close_pool, get_conn

    await init_pool()
    async with get_conn() as conn:
        row = await conn.fetchrow("SELECT 1")
    await close_pool()
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import asyncpg

_pool: Optional[asyncpg.Pool] = None


class DatabaseNotInitializedError(RuntimeError):
    """init_pool() 호출 전에 get_conn() 사용 시 발생."""


async def init_pool(
    dsn: str | None = None, *, min_size: int = 2, max_size: int = 10
) -> asyncpg.Pool:
    """전역 커넥션 풀 초기화.

    Args:
        dsn: PostgreSQL connection string. None이면 환경변수 DATABASE_URL 사용.
        min_size: 최소 유지 커넥션 수
        max_size: 최대 커넥션 수

    Returns:
        초기화된 asyncpg.Pool

    Raises:
        RuntimeError: DATABASE_URL 환경변수 미설정
    """
    global _pool
    if _pool is not None:
        return _pool

    connection_dsn = dsn or os.environ.get("F1_DATABASE_URL")
    if not connection_dsn:
        raise RuntimeError(
            "F1_DATABASE_URL 환경변수가 설정되지 않았습니다. "
            "backend/.env 파일에 Supabase Connection String을 추가하세요."
        )

    _pool = await asyncpg.create_pool(
        connection_dsn,
        min_size=min_size,
        max_size=max_size,
        # Supabase 권장 기본값
        command_timeout=60,
        # Supabase Transaction pooler (pgbouncer transaction 모드) 호환용.
        # prepared statement 캐시 비활성화. 성능 약간 희생하지만 호환성 우선.
        statement_cache_size=0,
    )
    return _pool


async def close_pool() -> None:
    """서버 종료 시 커넥션 풀 정리."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """현재 초기화된 풀 반환. 미초기화 시 예외."""
    if _pool is None:
        raise DatabaseNotInitializedError(
            "init_pool()을 먼저 호출하세요. FastAPI lifespan 훅에서 초기화 권장."
        )
    return _pool


@asynccontextmanager
async def get_conn() -> AsyncIterator[asyncpg.Connection]:
    """커넥션 획득 컨텍스트 매니저.

    사용 예:
        async with get_conn() as conn:
            rows = await conn.fetch("SELECT * FROM ingredient_list LIMIT 10")
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        yield conn


# ============================================================
# FastAPI Depends 용 (선택)
# ============================================================
async def get_conn_dep() -> AsyncIterator[asyncpg.Connection]:
    """FastAPI Depends 로 주입할 때 사용.

    사용 예:
        from fastapi import Depends

        @router.get("/ingredients")
        async def list_ingredients(db: asyncpg.Connection = Depends(get_conn_dep)):
            return await db.fetch("SELECT * FROM ingredient_list")
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        yield conn
