"""F1 전용 조항 기반 청킹 — newsamc chunking-service.ts Python 포팅.

흐름:
    split_by_article(md)        # `### 제N조` 헤딩 또는 빈 줄 폴백 분할
    → normalize_chunks(chunks)  # 소형 병합 + 대형 세분화
    → attach_metadata(chunks, regulation_id, namespace)
    → 결과는 f1_embed_*.py에서 임베딩 + upsert

상수:
    MIN_CHUNK_TOKENS = 200
    MAX_CHUNK_TOKENS = 1500
    OVERLAP_TOKENS   = 200

tiktoken `cl100k_base` 인코더 사용 (OpenAI text-embedding-3-small 호환).
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

import tiktoken

MIN_CHUNK_TOKENS = 200
MAX_CHUNK_TOKENS = 1500
OVERLAP_TOKENS = 200

_ARTICLE_HEADING_RE = re.compile(r"^###\s+(제\d+조(?:의\d+)?\s*.*)", re.MULTILINE)
_SUB_BOUNDARY_RE = re.compile(r"(?=^[①②③④⑤⑥⑦⑧⑨⑩]|^\d+\.\s)", re.MULTILINE)


@lru_cache(maxsize=1)
def _encoder():
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """cl100k_base 정확 카운팅."""
    return len(_encoder().encode(text))


def split_by_article(markdown: str) -> list[dict]:
    """`### 제N조` 헤딩 분할 → 미존재 시 빈 줄(\\n\\n) 폴백."""
    matches = list(_ARTICLE_HEADING_RE.finditer(markdown))

    if not matches:
        # 헤딩 없음 → 빈 줄 기준 분할
        parts = re.split(r"\n{2,}", markdown)
        return [
            {"text": p.strip(), "section_path": f"section_{i}"}
            for i, p in enumerate(parts)
            if p.strip()
        ]

    chunks = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        text = markdown[start:end].strip()
        section_path = (m.group(1) or f"article_{i}").strip()
        chunks.append({"text": text, "section_path": section_path})
    return chunks


def _sliding_window(text: str, section: str) -> list[dict]:
    """토큰 슬라이딩 윈도우 (MAX 크기 + OVERLAP 오버랩)."""
    enc = _encoder()
    token_ids = enc.encode(text)
    windows = []
    start = 0
    step = MAX_CHUNK_TOKENS - OVERLAP_TOKENS
    idx = 0
    while start < len(token_ids):
        window = token_ids[start : start + MAX_CHUNK_TOKENS]
        windows.append({
            "text": enc.decode(window),
            "section_path": f"{section}_window{idx}",
        })
        start += step
        idx += 1
    return windows


def _split_large_chunk(chunk: dict) -> list[dict]:
    """대형 청크 세분화. 항/호 경계 분할 후 각 part가 여전히 MAX 초과면 재귀/슬라이딩.

    항/호 경계(①②③ 또는 1.)가 없거나 분할 후에도 크면 토큰 슬라이딩 윈도우로 폴백.
    """
    text = chunk["text"]
    section = chunk["section_path"]

    parts = _SUB_BOUNDARY_RE.split(text)
    parts = [p.strip() for p in parts if p.strip()]

    if len(parts) > 1:
        result: list[dict] = []
        for i, p in enumerate(parts):
            sub_section = f"{section}_part{i}"
            if count_tokens(p) > MAX_CHUNK_TOKENS:
                # 항/호 분할 후에도 큰 경우 → 슬라이딩 폴백
                result.extend(_sliding_window(p, sub_section))
            else:
                result.append({"text": p, "section_path": sub_section})
        return result

    # 경계 없음 → 슬라이딩
    return _sliding_window(text, section)


def normalize_chunks(raw: list[dict]) -> list[dict]:
    """소형 병합 + 대형 세분화. 모든 청크를 [MIN, MAX] 범위로 정규화."""
    result: list[dict] = []

    for chunk in raw:
        tokens = count_tokens(chunk["text"])

        # 소형 → 이전 청크에 병합 (합산이 MAX 초과하면 단독)
        if tokens < MIN_CHUNK_TOKENS and result:
            prev = result[-1]
            merged_tokens = count_tokens(prev["text"]) + tokens
            if merged_tokens <= MAX_CHUNK_TOKENS:
                prev["text"] = prev["text"] + "\n\n" + chunk["text"]
                # section_path는 이전 것 유지 (가독성)
                continue

        # 대형 → 세분화
        if tokens > MAX_CHUNK_TOKENS:
            result.extend(_split_large_chunk(chunk))
        else:
            result.append(chunk)

    return result


def attach_metadata(
    chunks: list[dict],
    regulation_id: str,
    namespace: str,
    id_prefix: Optional[str] = None,
) -> list[dict]:
    """vector_id = `{id_prefix or regulation_id}_{chunk_index:04d}`.

    Pinecone vector ID는 ASCII-only 제약. regulation_id가 비-ASCII면
    반드시 `id_prefix`를 ASCII로 지정.
    """
    total = len(chunks)
    prefix = id_prefix if id_prefix is not None else regulation_id
    out = []
    for i, c in enumerate(chunks):
        out.append({
            "vector_id": f"{prefix}_{i:04d}",
            "text": c["text"],
            "metadata": {
                "regulation_id": regulation_id,
                "section_path": c.get("section_path"),
                "pinecone_namespace": namespace,
                "token_count": count_tokens(c["text"]),
                "chunk_index": i,
                "total_chunks": total,
            },
        })
    return out


def chunk_markdown(
    markdown: str,
    regulation_id: str,
    namespace: str,
    id_prefix: Optional[str] = None,
) -> list[dict]:
    """엔드투엔드 — split_by_article → normalize → attach_metadata."""
    raw = split_by_article(markdown)
    normalized = normalize_chunks(raw)
    return attach_metadata(normalized, regulation_id, namespace, id_prefix=id_prefix)
