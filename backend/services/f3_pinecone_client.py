"""
Pinecone 법령 청크 RAG 검색.

인덱스: samc-law-f3 (85 청크)
  - law 22: 시행규칙 제27조·별표9·별표10 등
  - official_excel 33: 식약처 엑셀 제출 19 + 보관 14 row별 청크
  - guideline 10: OEM 안내서·소개
  - treaty 20: 4개국 동등성인정 협정문·서신

각 청크 metadata:
  related_doc_ids: ["c1","g2-1",...]   ← Supabase 서류 id 와 양방향 연결
  law_name, article, clause, item, topic, effective_date 등
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pinecone import Pinecone


_pc: Optional[Pinecone] = None
_index = None


def _ensure_index():
    """Pinecone 클라이언트 + 인덱스 싱글톤 초기화."""
    global _pc, _index
    if _index is not None:
        return _index
    api_key = os.getenv("F3_PINECONE_API_KEY")
    if not api_key:
        raise RuntimeError("F3_PINECONE_API_KEY 환경변수가 없습니다.")
    _pc = Pinecone(api_key=api_key)
    _index = _pc.Index(os.getenv("F3_PINECONE_INDEX_NAME", "samc-law-f3"))
    return _index


def _embed_query(text: str) -> list[float]:
    """Pinecone inference API 로 쿼리 임베딩 생성 (OpenAI 키 불필요)."""
    global _pc
    if _pc is None:
        _ensure_index()
    emb = _pc.inference.embed(
        model="multilingual-e5-large",
        inputs=[text],
        parameters={"input_type": "query"},
    )
    # Pinecone SDK 버전에 따라 두 가지 반환 형태 지원
    e = emb[0]
    if isinstance(e, dict):
        return e.get("values") or e["data"][0]["values"]
    return e.values


def search_law_chunks(
    query: str,
    top_k: int = 5,
    filter_doc_ids: Optional[list[str]] = None,
) -> list[dict]:
    """법령 청크 시맨틱 검색.

    Args:
        query: 자연어 질의. 예: "ASF 발생국에서 돼지 수입 시 필요 서류"
        top_k: 상위 N개
        filter_doc_ids: 특정 서류 id 와 연결된 청크만 (예: ["g6-6"])

    Returns:
        [
          {"id": "excel-submit-14", "score": 0.89,
           "text": "...", "metadata": {...}},
          ...
        ]
    """
    index = _ensure_index()
    vector = _embed_query(query)

    kwargs: dict = {"vector": vector, "top_k": top_k, "include_metadata": True}
    if filter_doc_ids:
        kwargs["filter"] = {"related_doc_ids": {"$in": filter_doc_ids}}

    res = index.query(**kwargs)
    matches = res.matches if hasattr(res, "matches") else res.get("matches", [])

    out: list[dict] = []
    for m in matches:
        md = dict(m.metadata) if hasattr(m, "metadata") else dict(m.get("metadata", {}))
        text = md.pop("text", "")
        out.append(
            {
                "id": m.id if hasattr(m, "id") else m["id"],
                "score": float(m.score if hasattr(m, "score") else m["score"]),
                "text": text,
                "metadata": md,
            }
        )
    return out
