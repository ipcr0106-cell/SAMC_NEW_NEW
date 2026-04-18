"""
f0 성분코드 + 공정코드 Pinecone 임베딩 배치 스크립트

실행:
    cd backend
    python -m scripts.f0_embed_codes              # 전체 실행
    python -m scripts.f0_embed_codes --only ingredients  # 성분코드만
    python -m scripts.f0_embed_codes --only process      # 공정코드만

환경변수 (backend/.env):
    F0_PINECONE_API_KEY      Pinecone API 키
    F0_PINECONE_INDEX_NAME   인덱스명 (기본값: samc-f0-codes)
    F0_OPENAI_API_KEY        임베딩용 OpenAI API 키
    SUPABASE_URL             Supabase URL (공용)
    SUPABASE_SERVICE_KEY     Supabase 서비스 키 (공용)

Pinecone 인덱스 구조:
    - 차원: 1536 (text-embedding-3-small)
    - namespace:
        'ingredients'  성분코드 12,263개
        'process'      공정코드 211개
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────

PINECONE_API_KEY   = os.getenv("F0_PINECONE_API_KEY", "")
PINECONE_INDEX     = os.getenv("F0_PINECONE_INDEX_NAME", "samc-f0-codes")
OPENAI_API_KEY     = os.getenv("F0_OPENAI_API_KEY", "")
SUPABASE_URL       = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY       = os.getenv("SUPABASE_SERVICE_KEY", "")

EMBED_MODEL        = "text-embedding-3-small"
EMBED_DIM          = 1536
BATCH_SIZE         = 100   # OpenAI 임베딩 배치 크기
UPSERT_BATCH_SIZE  = 100   # Pinecone upsert 배치 크기


# ─────────────────────────────────────────────
# 임베딩 생성
# ─────────────────────────────────────────────

def embed_texts(texts: list[str]) -> list[list[float]]:
    """OpenAI API로 텍스트 목록 임베딩. BATCH_SIZE 단위로 처리."""
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

    all_embeddings = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
        all_embeddings.extend([r.embedding for r in resp.data])
        logger.info(f"  임베딩 진행: {min(i + BATCH_SIZE, len(texts))}/{len(texts)}")
        time.sleep(0.3)  # rate limit 방지

    return all_embeddings


# ─────────────────────────────────────────────
# Pinecone upsert
# ─────────────────────────────────────────────

def upsert_to_pinecone(index, vectors: list[dict], namespace: str) -> None:
    """vectors를 UPSERT_BATCH_SIZE 단위로 Pinecone에 업로드."""
    for i in range(0, len(vectors), UPSERT_BATCH_SIZE):
        batch = vectors[i:i + UPSERT_BATCH_SIZE]
        index.upsert(vectors=batch, namespace=namespace)
        logger.info(f"  Pinecone upsert: {min(i + UPSERT_BATCH_SIZE, len(vectors))}/{len(vectors)} ({namespace})")
        time.sleep(0.1)


# ─────────────────────────────────────────────
# 성분코드 처리
# ─────────────────────────────────────────────

def run_ingredients(index) -> None:
    """Supabase f0_ingredient_codes → 임베딩 → Pinecone ingredients 네임스페이스."""
    logger.info("=== 성분코드 임베딩 시작 ===")

    from supabase import create_client
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Supabase에서 전체 조회 (1000개씩 페이지네이션)
    all_rows = []
    page = 0
    while True:
        result = (
            sb.table("f0_ingredient_codes")
            .select("code, name_ko, name_en, category, code_prefix")
            .range(page * 1000, (page + 1) * 1000 - 1)
            .execute()
        )
        batch = result.data or []
        all_rows.extend(batch)
        logger.info(f"  Supabase 조회: {len(all_rows)}건 로드됨")
        if len(batch) < 1000:
            break
        page += 1

    if not all_rows:
        logger.warning("성분코드 데이터 없음. Supabase에 011_f0_ingredient_codes.sql 먼저 실행하세요.")
        return

    logger.info(f"총 {len(all_rows)}건 임베딩 시작...")

    # 임베딩용 텍스트: 한글명 + 영문명 + 성분구분
    texts = [
        f"{r['name_ko']} {r.get('name_en', '')} {r.get('category', '')}".strip()
        for r in all_rows
    ]
    embeddings = embed_texts(texts)

    # Pinecone 벡터 구성
    vectors = [
        {
            "id": row["code"],
            "values": emb,
            "metadata": {
                "code":        row["code"],
                "name_ko":     row["name_ko"],
                "name_en":     row.get("name_en", ""),
                "category":    row.get("category", ""),
                "code_prefix": row.get("code_prefix", ""),
            },
        }
        for row, emb in zip(all_rows, embeddings)
    ]

    upsert_to_pinecone(index, vectors, namespace="ingredients")
    logger.info(f"=== 성분코드 임베딩 완료: {len(vectors)}건 ===")


# ─────────────────────────────────────────────
# 공정코드 처리
# ─────────────────────────────────────────────

def run_process(index) -> None:
    """Supabase f0_process_codes → 임베딩 → Pinecone process 네임스페이스."""
    logger.info("=== 공정코드 임베딩 시작 ===")

    from supabase import create_client
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    result = sb.table("f0_process_codes").select("code, name_ko, code_type").execute()
    rows = result.data or []

    if not rows:
        logger.warning("공정코드 데이터 없음. Supabase에 010_f0_process_codes.sql 먼저 실행하세요.")
        return

    logger.info(f"총 {len(rows)}건 임베딩 시작...")

    # 임베딩용 텍스트: 공정명 (짧지만 한국어 의미로 매칭)
    texts = [r["name_ko"] for r in rows]
    embeddings = embed_texts(texts)

    vectors = [
        {
            "id": f"proc_{row['code']}",  # 성분코드 id와 충돌 방지
            "values": emb,
            "metadata": {
                "code":      row["code"],
                "name_ko":   row["name_ko"],
                "code_type": row.get("code_type", ""),
            },
        }
        for row, emb in zip(rows, embeddings)
    ]

    upsert_to_pinecone(index, vectors, namespace="process")
    logger.info(f"=== 공정코드 임베딩 완료: {len(vectors)}건 ===")


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="f0 성분/공정코드 Pinecone 임베딩 스크립트")
    parser.add_argument(
        "--only",
        choices=["ingredients", "process"],
        help="특정 타입만 실행 (미지정 시 둘 다 실행)",
    )
    args = parser.parse_args()

    # 환경변수 확인
    missing = [k for k, v in {
        "F0_PINECONE_API_KEY": PINECONE_API_KEY,
        "F0_OPENAI_API_KEY": OPENAI_API_KEY,
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_SERVICE_KEY": SUPABASE_KEY,
    }.items() if not v]
    if missing:
        logger.error(f"환경변수 누락: {missing}")
        sys.exit(1)

    # Pinecone 인덱스 연결
    try:
        from pinecone import Pinecone
        pc = Pinecone(api_key=PINECONE_API_KEY)

        # 인덱스 없으면 생성
        existing = [idx.name for idx in pc.list_indexes()]
        if PINECONE_INDEX not in existing:
            logger.info(f"Pinecone 인덱스 생성 중: {PINECONE_INDEX} (dim={EMBED_DIM})")
            pc.create_index(
                name=PINECONE_INDEX,
                dimension=EMBED_DIM,
                metric="cosine",
                spec={"serverless": {"cloud": "aws", "region": "us-east-1"}},
            )
            time.sleep(5)  # 인덱스 준비 대기

        index = pc.Index(PINECONE_INDEX)
        logger.info(f"Pinecone 인덱스 연결: {PINECONE_INDEX}")
    except Exception as e:
        logger.error(f"Pinecone 연결 실패: {e}")
        sys.exit(1)

    # 실행
    if args.only == "ingredients":
        run_ingredients(index)
    elif args.only == "process":
        run_process(index)
    else:
        run_ingredients(index)
        run_process(index)

    logger.info("모든 임베딩 작업 완료.")


if __name__ == "__main__":
    main()
