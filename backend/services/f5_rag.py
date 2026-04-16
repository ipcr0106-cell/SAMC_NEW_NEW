"""
Pinecone 법령 검색 (RAG)
Pinecone f5-law-chunks 인덱스 검색 → 관련 법령 청크 반환
"""

import os

import voyageai
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

_voyage_client = None
_pinecone_index = None

INDEX_NAME = os.getenv("F5_PINECONE_INDEX", "f5-law-chunks")


def _get_voyage():
    global _voyage_client
    if _voyage_client is None:
        api_key = os.getenv("F5_VOYAGE_API_KEY")
        if not api_key:
            raise RuntimeError("F5_VOYAGE_API_KEY 환경변수 미설정")
        _voyage_client = voyageai.Client(api_key=api_key)
    return _voyage_client


def _get_pinecone_index():
    global _pinecone_index
    if _pinecone_index is None:
        api_key = os.getenv("F5_PINECONE_API_KEY")
        if not api_key:
            raise RuntimeError("F5_PINECONE_API_KEY 환경변수 미설정")
        _pinecone_index = Pinecone(api_key=api_key).Index(INDEX_NAME)
    return _pinecone_index


def embed_query(text: str) -> list[float]:
    """텍스트 → Voyage-3 임베딩 벡터"""
    result = _get_voyage().embed([text], model="voyage-3")
    return result.embeddings[0]


def search_and_format(query: str, match_count: int = 5) -> str:
    """
    쿼리와 관련된 법령 청크를 검색하고 프롬프트에 삽입할 문자열로 반환.
    Pinecone f5-law-chunks 인덱스 사용.
    """
    try:
        vector = embed_query(query)

        res = _get_pinecone_index().query(
            vector=vector,
            top_k=match_count,
            include_metadata=True,
        )
        matches = res.get("matches") or []
    except Exception:
        # RAG 실패 시 빈 컨텍스트로 진행 (시안 생성은 계속)
        return ""

    if not matches:
        return ""

    lines = ["[관련 법령 근거]"]
    for m in matches:
        meta = m.get("metadata") or {}
        law     = meta.get("law_name", "")
        content = meta.get("content", "")
        lines.append(f"\n## {law}\n{content}")

    return "\n".join(lines)