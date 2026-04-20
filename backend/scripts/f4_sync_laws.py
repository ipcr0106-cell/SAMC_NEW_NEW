"""
F4 법령 API 자동 동기화 스크립트

국가법령정보센터 API에서 F4 관련 법령 7개의 최신 본문을 가져와
변경된 법령만 Pinecone + Supabase에 재적재.

[사용법]
  # 변경된 법령만 업데이트
  python -m backend.scripts.f4_sync_laws

  # 전체 강제 재적재 (초기 마이그레이션)
  python -m backend.scripts.f4_sync_laws --force

[cron 예시 — 매주 월요일 새벽 3시]
  0 3 * * 1 cd /path/to/project && python -m backend.scripts.f4_sync_laws

[필요 환경변수]
  LAW_API_OC             — 국가법령정보센터 API 인증키
  F4_PINECONE_API_KEY    — Pinecone API 키
  F4_PINECONE_HOST       — Pinecone 호스트
  SUPABASE_URL           — Supabase URL
  SUPABASE_SERVICE_KEY   — Supabase 서비스 키
  F4_OPENAI_API_KEY      — OpenAI API 키 (금지 마커 추출용)
"""

import argparse
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("f4_sync_laws")


def main():
    parser = argparse.ArgumentParser(description="F4 법령 API 동기화")
    parser.add_argument(
        "--force", action="store_true",
        help="변경 여부 무시, 전체 7개 법령 강제 재처리",
    )
    args = parser.parse_args()

    # 환경변수 확인
    required = [
        "F4_PINECONE_API_KEY", "F4_PINECONE_HOST",
        "SUPABASE_URL", "SUPABASE_SERVICE_KEY",
        "F4_OPENAI_API_KEY",
    ]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        logger.error("환경변수 누락: %s", missing)
        sys.exit(1)

    # 클라이언트 초기화
    from openai import OpenAI
    from pinecone import Pinecone
    from sentence_transformers import SentenceTransformer
    from supabase import create_client

    logger.info("클라이언트 초기화 중...")
    pc = Pinecone(api_key=os.getenv("F4_PINECONE_API_KEY"))
    index = pc.Index(host=os.getenv("F4_PINECONE_HOST"))
    supabase_client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
    model = SentenceTransformer("intfloat/multilingual-e5-large")
    claude_client = OpenAI(api_key=os.getenv("F4_OPENAI_API_KEY"))

    # 동기화 실행
    from backend.services.law_api_client import sync_all_f4_laws

    logger.info("=" * 60)
    logger.info("F4 법령 API 동기화 시작 (force=%s)", args.force)
    logger.info("=" * 60)

    results = sync_all_f4_laws(
        index=index,
        supabase_client=supabase_client,
        model=model,
        claude_client=claude_client,
        force=args.force,
    )

    # 결과 출력
    logger.info("=" * 60)
    logger.info("동기화 결과:")
    for r in results:
        status = r["status"]
        name = r["law_name"]
        if status == "updated":
            logger.info("  [갱신] %s — %d 청크", name, r.get("total_chunks", 0))
        elif status == "skipped":
            logger.info("  [건너뜀] %s — 변경 없음", name)
        else:
            logger.error("  [오류] %s — %s", name, r.get("error", "unknown"))

    updated = sum(1 for r in results if r["status"] == "updated")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    errors = sum(1 for r in results if r["status"] == "error")
    logger.info("완료: 갱신=%d, 건너뜀=%d, 오류=%d", updated, skipped, errors)

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
