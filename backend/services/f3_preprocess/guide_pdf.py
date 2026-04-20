"""
F3 Step 3 — OEM 안내서 / 동등성인정 협정문 PDF 파서.

Step 2(rule_pdf) 와 동일한 패턴, 청킹 세부만 다름:
  - 별표 구조 없음 (일반 문단 기반 청킹)
  - topic 구분: "OEM" / "동등성인정"

Pinecone 재임베딩은 apply 단계에서 feature3_admin 이 수행.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz

from .pinecone_embed import chunk_id as _chunk_id


# multilingual-e5-large 512 토큰 한도 대응 (rule_pdf 와 동일 기준).
_MIN_CHUNK_CHARS = 80
_MAX_CHUNK_CHARS = 1000
_OVERLAP = 150


def _topic_from_law_name(law_name: str) -> str:
    if "OEM" in law_name:
        return "OEM"
    if "동등성" in law_name:
        return "동등성인정"
    return "기타"


def _extract_text(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    try:
        return "\n\n".join(p.get_text("text") or "" for p in doc)
    finally:
        doc.close()


def _chunk_by_paragraph(text: str) -> list[str]:
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for part in parts:
        if len(part) < _MIN_CHUNK_CHARS:
            buf += ("\n\n" + part) if buf else part
            continue
        if buf:
            if len(buf) >= _MIN_CHUNK_CHARS:
                chunks.append(buf)
            buf = ""
        if len(part) > _MAX_CHUNK_CHARS:
            start = 0
            while start < len(part):
                end = min(start + _MAX_CHUNK_CHARS, len(part))
                chunks.append(part[start:end])
                if end == len(part):
                    break
                start = end - _OVERLAP
        else:
            chunks.append(part)
    if buf and len(buf) >= _MIN_CHUNK_CHARS:
        chunks.append(buf)
    return chunks


def parse(file_path: Path, law_name: str) -> dict:
    text = _extract_text(file_path)
    if not text.strip():
        raise ValueError(f"PDF 텍스트 추출 결과 비어있음: {file_path.name}")

    topic = _topic_from_law_name(law_name)
    chunks = _chunk_by_paragraph(text)
    if not chunks:
        raise ValueError(
            f"PDF 청킹 결과 0: {file_path.name}. "
            f"PDF 가 이미지 스캔본일 수 있습니다."
        )

    new_citations: list[dict[str, Any]] = []
    pinecone_chunks: list[dict[str, Any]] = []

    for i, c in enumerate(chunks):
        article = f"{topic}_section_{i}"
        pid = _chunk_id(law_name, article, i)
        new_citations.append({
            "id": f"{law_name}_{i}",
            "pinecone_chunk_id": pid,
            "law_name": law_name,
            "article": article,
            "excerpt": c[:500],
            "source_file": file_path.name,
            "chunk_index": i,
            "topic": topic,
        })
        pinecone_chunks.append({
            "pinecone_chunk_id": pid,
            "law_name": law_name,
            "article": article,
            "chunk_index": i,
            "text": c,
            "topic": topic,
        })

    return {
        "tables": {
            "f3_document_law_citations": {
                "new_rows": new_citations,
                "pk_column": "id",
                "scope_filter": {"law_name": law_name},
                "warnings": [f"{topic} 문서에서 {len(chunks)}개 청크 추출."],
            }
        },
        "pinecone_chunks": pinecone_chunks,
        "warnings": [
            f"{law_name} 에서 {len(chunks)}개 청크 추출.",
            "🔄 반영 시 citations + Pinecone 재임베딩 모두 진행됩니다.",
        ],
        "pinecone_touched": True,
    }
