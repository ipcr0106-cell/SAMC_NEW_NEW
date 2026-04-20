"""
F3 Step 2 — 수입식품안전관리 특별법 시행규칙 PDF 파서.

입력: 시행규칙 PDF (별표9, 별표10 포함)
출력:
  - tables:         f3_document_law_citations 업데이트 (Supabase)
  - pinecone_chunks: Pinecone 재임베딩 대상 청크 목록

처리 흐름:
  1. pymupdf 로 PDF 텍스트 추출
  2. "제N조", "별표 N" 기준으로 청킹 (너무 크면 sliding window)
  3. 결정적 chunk_id (MD5) — 재업로드 시 자동 덮어쓰기
  4. feature3_admin.apply 에서:
     a. citations 테이블 snapshot+replace
     b. 성공 시 Pinecone delete-by-law-name + upsert
     c. pinecone_touched=True 로 history 기록
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import fitz

from .pinecone_embed import chunk_id as _chunk_id


# ──────────────────────────────────────────────
# PDF 텍스트 추출
# ──────────────────────────────────────────────

def _extract_text(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    try:
        return "\n\n".join(p.get_text("text") or "" for p in doc)
    finally:
        doc.close()


# ──────────────────────────────────────────────
# 청킹
# ──────────────────────────────────────────────

_ARTICLE_RE = re.compile(r"(?=제\s*\d+\s*조(?:의\s*\d+)?\s)")
_BYEOLPYO_RE = re.compile(r"(?=별표\s*\d+)")

# multilingual-e5-large 는 512 토큰 한도 (한국어 ~1000자).
# 초과 시 뒷부분 조용히 잘림 → 검색 품질 저하. 1000자로 축소.
_MIN_CHUNK_CHARS = 80
_MAX_CHUNK_CHARS = 1000
_OVERLAP = 150


def _sliding(text: str, size: int = _MAX_CHUNK_CHARS, overlap: int = _OVERLAP) -> list[str]:
    if len(text) <= size:
        return [text]
    out = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        out.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return out


def _chunk_text(text: str) -> list[dict[str, str]]:
    """조문 + 별표 단위 청킹."""
    chunks: list[dict[str, str]] = []

    byeolpyo_parts = _BYEOLPYO_RE.split(text)
    body = byeolpyo_parts[0]
    byeolpyo_sections = byeolpyo_parts[1:]

    article_parts = _ARTICLE_RE.split(body)
    for part in article_parts:
        part = part.strip()
        if len(part) < _MIN_CHUNK_CHARS:
            continue
        m = re.match(r"제\s*(\d+)\s*조(?:의\s*(\d+))?", part)
        article = (
            f"제{m.group(1)}조" + (f"의{m.group(2)}" if m.group(2) else "")
            if m else "본문"
        )
        for sub in _sliding(part):
            chunks.append({"article": article, "text": sub})

    for sec in byeolpyo_sections:
        sec = sec.strip()
        if len(sec) < _MIN_CHUNK_CHARS:
            continue
        m = re.match(r"별표\s*(\d+)", sec)
        article = f"별표{m.group(1)}" if m else "별표"
        for sub in _sliding(sec):
            chunks.append({"article": article, "text": sub})

    return chunks


# ──────────────────────────────────────────────
# 메인 파서
# ──────────────────────────────────────────────

def parse(file_path: Path, law_name: str) -> dict:
    """시행규칙 PDF → citations 행 + Pinecone 청크."""
    text = _extract_text(file_path)
    if not text.strip():
        raise ValueError(f"PDF 텍스트 추출 결과 비어있음: {file_path.name}")

    chunks = _chunk_text(text)
    if not chunks:
        raise ValueError(
            f"PDF 청킹 결과 0: {file_path.name}. "
            f"PDF 가 이미지 스캔본이거나 조문/별표 패턴이 없을 수 있습니다."
        )

    new_citations: list[dict[str, Any]] = []
    pinecone_chunks: list[dict[str, Any]] = []

    for i, c in enumerate(chunks):
        pid = _chunk_id(law_name, c["article"], i)
        new_citations.append({
            "id": f"{law_name}_{c['article']}_{i}",
            "pinecone_chunk_id": pid,
            "law_name": law_name,
            "article": c["article"],
            "excerpt": c["text"][:500],
            "source_file": file_path.name,
            "chunk_index": i,
        })
        pinecone_chunks.append({
            "pinecone_chunk_id": pid,
            "law_name": law_name,
            "article": c["article"],
            "chunk_index": i,
            "text": c["text"],
            "topic": "시행규칙",
        })

    return {
        "tables": {
            "f3_document_law_citations": {
                "new_rows": new_citations,
                "pk_column": "id",
                "scope_filter": {"law_name": law_name},  # 해당 법령 citations 만 교체
                "warnings": [f"{len(chunks)}개 청크 추출 (조문 + 별표)."],
            }
        },
        "pinecone_chunks": pinecone_chunks,
        "warnings": [
            f"시행규칙 PDF 에서 {len(chunks)}개 청크 추출.",
            "🔄 반영 시 Supabase citations 갱신 + Pinecone 벡터 재임베딩 진행됩니다.",
            "⚠️ Pinecone 재임베딩은 네트워크 지연이 있을 수 있으니 '반영' 버튼 이후 "
            "완료까지 수십 초 걸릴 수 있습니다.",
        ],
        "pinecone_touched": True,
    }
