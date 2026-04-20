"""F1 Step D 법령 캐시 동기화 — law.go.kr 5종 본문을 f1_law_* 테이블에 적재.

실행:
    cd backend
    python -m scripts.f1_sync_laws                  # 5종 모두 갱신
    python -m scripts.f1_sync_laws --only food_code_text
    python -m scripts.f1_sync_laws --dry-run        # API 만 호출, DB 쓰기 X

테이블: backend/db/migrations/020_f1_law_cache.sql
배경: Pinecone 검색이 무관 결과를 반환하는 품질 문제 → 법제처 공식 본문 직접 적재.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# `backend.services.f1_law_client` import 를 위해 프로젝트 루트를 path 에 추가.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.f1_law_client import (  # noqa: E402
    F1_LAW_REGISTRY,
    F1LawEntry,
    fetch_articles_admrul,
    fetch_articles_safetydata,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("f1_sync_laws")


def _dsn() -> str:
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("F1_DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL/F1_DATABASE_URL 환경변수가 필요합니다.")
    return dsn


async def _load_articles(
    entry: F1LawEntry, conn: asyncpg.Connection
) -> tuple[str, list[dict], str, str]:
    """source 별로 articles 적재 + (api_date, articles, api_type, api_id) 반환."""
    if entry.source == "admrul":
        api_date, articles = fetch_articles_admrul(entry)
        return api_date, articles, "admrul", entry.api_id or ""
    if entry.source == "safetydata":
        api_date, articles = await fetch_articles_safetydata(entry, conn)
        return api_date, articles, "safetydata", entry.safetydata_table or ""
    raise ValueError(f"unknown source: {entry.source}")


async def sync_one(entry: F1LawEntry, *, dry_run: bool) -> None:
    logger.info(
        "[%s] %s source=%s 본문 조회 중...",
        entry.namespace, entry.law_name, entry.source,
    )

    conn = await asyncpg.connect(_dsn(), statement_cache_size=0, command_timeout=120)
    try:
        api_date, articles, api_type, api_id = await _load_articles(entry, conn)
        logger.info(
            "[%s] articles=%d 발령일자=%s",
            entry.namespace, len(articles), api_date,
        )

        if dry_run:
            for a in articles[:3]:
                logger.info(
                    "  [dry] %s — %d chars",
                    a["article_label"], len(a["text"]),
                )
            return

        if not articles:
            logger.warning("[%s] 본문 0건 — 적재 생략", entry.namespace)
            return

        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO f1_law_cache
                    (namespace, law_name, api_type, api_id, api_공포일자, last_sync_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (namespace) DO UPDATE SET
                    law_name      = EXCLUDED.law_name,
                    api_type      = EXCLUDED.api_type,
                    api_id        = EXCLUDED.api_id,
                    api_공포일자  = EXCLUDED.api_공포일자,
                    last_sync_at  = NOW()
                RETURNING id
                """,
                entry.namespace, entry.law_name, api_type, api_id, api_date,
            )
            cache_id = row["id"]

            await conn.execute(
                "DELETE FROM f1_law_articles WHERE law_cache_id = $1",
                cache_id,
            )

            records = [
                (cache_id, a["article_label"], a["text"], a["article_type"])
                for a in articles
            ]
            await conn.copy_records_to_table(
                "f1_law_articles",
                records=records,
                columns=["law_cache_id", "article_label", "text", "article_type"],
            )

        logger.info(
            "[%s] 완료: cache_id=%d articles=%d",
            entry.namespace, cache_id, len(articles),
        )
    finally:
        await conn.close()


async def main_async(only: str | None, dry_run: bool) -> None:
    targets = [e for e in F1_LAW_REGISTRY if only is None or e.namespace == only]
    if not targets:
        logger.error("unknown --only namespace: %s", only)
        sys.exit(2)
    for entry in targets:
        try:
            await sync_one(entry, dry_run=dry_run)
        except Exception as exc:
            logger.exception("[%s] 동기화 실패: %s", entry.namespace, exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="F1 Step D 법령 캐시 동기화")
    parser.add_argument(
        "--only", default=None,
        help="특정 namespace 만 (예: food_code_text)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="API 만 호출, DB 쓰기 생략",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args.only, args.dry_run))


if __name__ == "__main__":
    main()
