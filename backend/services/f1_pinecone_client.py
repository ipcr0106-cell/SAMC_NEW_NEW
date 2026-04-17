"""F1 전용 Pinecone 클라이언트 — samc-law-f1, 비동기 병렬 검색.

5개 namespace에 법령 청크 저장:
    - food_code_text       (식품공전)
    - additive_code_text   (식품첨가물공전)
    - functional_labeling  (건강기능 표시기준)
    - temporary_standard   (한시적 기준)
    - health_food_text     (건강기능식품공전)

환경변수:
    F1_PINECONE_API_KEY    (필수)
    F1_PINECONE_INDEX      (기본: samc-law-f1)

참고: 계획/f1_RAG도입계획_백엔드.md §3.2
"""
from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from pinecone import Pinecone

_pc: Optional[Pinecone] = None
_index = None
_executor = ThreadPoolExecutor(max_workers=8)


def get_index():
    """싱글톤 Pinecone 클라이언트 + 인덱스."""
    global _pc, _index
    if _index is not None:
        return _index
    api_key = os.getenv("F1_PINECONE_API_KEY")
    if not api_key:
        raise RuntimeError("F1_PINECONE_API_KEY 환경변수가 없습니다.")
    _pc = Pinecone(api_key=api_key)
    _index = _pc.Index(os.getenv("F1_PINECONE_INDEX", "samc-law-f1"))
    return _index


def search_sync(
    query_vector: list[float],
    namespace: str,
    top_k: int,
) -> list[dict]:
    """단일 namespace 동기 검색."""
    res = get_index().query(
        vector=query_vector,
        top_k=top_k,
        namespace=namespace,
        include_metadata=True,
    )
    hits: list[dict] = []
    for m in res.matches:
        meta = m.metadata or {}
        hits.append({
            "id": m.id,
            "score": m.score,
            "text": meta.get("text", ""),
            "regulation_id": meta.get("regulation_id"),
            "section_path": meta.get("section_path"),
            "namespace": namespace,
        })
    return hits


async def search_multi(
    query_vector: list[float],
    namespaces: list[str],
    top_k_per_ns: int = 5,
) -> list[dict]:
    """여러 namespace 병렬 검색 → score 기준 내림차순 통합."""
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(
            _executor, search_sync, query_vector, ns, top_k_per_ns,
        )
        for ns in namespaces
    ]
    results = await asyncio.gather(*tasks)
    flat = [hit for sub in results for hit in sub]
    flat.sort(key=lambda h: h["score"], reverse=True)
    return flat
