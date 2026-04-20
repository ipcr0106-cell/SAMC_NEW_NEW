"""
F3 법령 업데이트 — Pinecone 재임베딩 유틸.

Step 2 (시행규칙 PDF) / Step 3 (OEM·동등성 PDF) 에서 공용.

설계:
  - 결정적 chunk_id (MD5 of law_name + article + chunk_index)
    → 재업로드 시 자동 덮어쓰기
  - multilingual-e5-large (Pinecone inference API)
    → OpenAI 키 불필요, 1024 차원
  - 배치 처리 (default 50개씩)
  - 기존 chunk 삭제 후 재삽입 (법령명 기준 filter)
"""
from __future__ import annotations

import hashlib
import os
from typing import Optional

from pinecone import Pinecone


EMBED_BATCH = 50      # Pinecone inference API 배치
UPSERT_BATCH = 100


def _pinecone_client() -> Pinecone:
    api_key = os.getenv("F3_PINECONE_API_KEY")
    if not api_key:
        raise RuntimeError("F3_PINECONE_API_KEY 환경변수가 없습니다.")
    return Pinecone(api_key=api_key)


def _index(pc: Pinecone):
    return pc.Index(os.getenv("F3_PINECONE_INDEX_NAME", "samc-law-f3"))


def chunk_id(law_name: str, article: str, chunk_index: int) -> str:
    """결정적 chunk_id — 재업로드 시 자동 덮어쓰기."""
    raw = f"{law_name}|{article}|{chunk_index:04d}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def embed_texts(pc: Pinecone, texts: list[str]) -> list[list[float]]:
    """multilingual-e5-large 배치 임베딩. Pinecone inference API 직접 호출.

    Pinecone SDK 버전에 따라 응답 구조가 다름 — 두 형태 모두 지원.
    """
    out: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i : i + EMBED_BATCH]
        emb = pc.inference.embed(
            model="multilingual-e5-large",
            inputs=batch,
            parameters={"input_type": "passage"},
        )
        for e in emb:
            if isinstance(e, dict):
                vec = e.get("values") or e["data"][0]["values"]
            else:
                vec = e.values
            out.append(vec)
    return out


def delete_by_law(law_name: str) -> int:
    """해당 법령명을 가진 기존 Pinecone 벡터 전체 삭제.

    Pinecone 의 metadata filter delete 지원. 삭제된 수는 정확히 반환 불가
    (Pinecone 응답 제약) — 시도만 기록.
    """
    pc = _pinecone_client()
    idx = _index(pc)
    try:
        idx.delete(filter={"law_name": {"$eq": law_name}})
        return 1  # best-effort signal
    except Exception as e:
        # 인덱스 비어있거나 filter delete 미지원 등. 무시.
        import logging
        logging.warning("[F3 Pinecone] delete_by_law 실패: %s", e)
        return 0


def upsert_chunks(chunks: list[dict]) -> int:
    """청크 리스트 → Pinecone 임베딩 + upsert.

    Args:
        chunks: [
            {
                "pinecone_chunk_id": "...",  # 없으면 자동 생성
                "law_name": "...",
                "article": "...",
                "chunk_index": int,
                "text": "...",
                "related_doc_ids": [...] (optional),
                "topic": "..." (optional),
                ...
            }
        ]

    Returns: upsert 성공한 벡터 수
    """
    if not chunks:
        return 0

    pc = _pinecone_client()
    idx = _index(pc)

    # 1. 임베딩
    texts = [c["text"] for c in chunks]
    vectors = embed_texts(pc, texts)

    # 2. records 생성
    records = []
    for c, v in zip(chunks, vectors):
        cid = c.get("pinecone_chunk_id") or chunk_id(
            c["law_name"], c.get("article", "unknown"), c.get("chunk_index", 0)
        )
        metadata = {
            "law_name": c["law_name"],
            "article": c.get("article", ""),
            "chunk_index": c.get("chunk_index", 0),
            "text": c["text"][:1000],  # metadata 용량 제약
        }
        if c.get("related_doc_ids"):
            metadata["related_doc_ids"] = c["related_doc_ids"]
        if c.get("topic"):
            metadata["topic"] = c["topic"]

        records.append({
            "id": cid,
            "values": v,
            "metadata": metadata,
        })

    # 3. 배치 upsert
    total = 0
    for i in range(0, len(records), UPSERT_BATCH):
        batch = records[i : i + UPSERT_BATCH]
        idx.upsert(vectors=batch)
        total += len(batch)
    return total
