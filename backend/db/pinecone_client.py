"""
SAMC — Pinecone 벡터 DB 클라이언트 (공유 파일: 기능 1·4·5 의존)

사용법:
    from db.pinecone_client import get_pinecone_index
    index = get_pinecone_index()
    results = index.query(vector=[...], top_k=5)
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

PINECONE_API_KEY = os.getenv("F0_PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.getenv("F0_PINECONE_INDEX", "samc-law-index")


@lru_cache(maxsize=1)
def get_pinecone_index():
    """Pinecone 인덱스 객체 싱글톤."""
    if not PINECONE_API_KEY:
        raise RuntimeError(
            "PINECONE_API_KEY가 .env에 설정되지 않았습니다."
        )

    try:
        from pinecone import Pinecone

        pc = Pinecone(api_key=PINECONE_API_KEY)
        return pc.Index(PINECONE_INDEX_NAME)
    except ImportError:
        raise RuntimeError(
            "pinecone 패키지가 설치되지 않았습니다. pip install pinecone"
        )
