"""법령 마크다운 청킹 — 조문+표 컨텍스트 보존.

담당: 병찬
참고: 계획/기능1_구현계획/03_백엔드_구현_계획.md T7
      개발계획서 §4-0 청킹 규칙

규칙:
    1. 조문(제N조, N., 가.) 경계에서 분할
    2. 단서 조항("단, ...")은 직전 조문에 병합 (자르지 않음)
    3. 표(| 시작 줄)는 앞 2문장 + 표 전체 + 각주(※)를 **하나의 청크**로 묶음
    4. 청크 메타데이터:
         - type: "text" | "table"
         - article: 가장 가까운 상위 조문명
         - has_numbers: 숫자 포함 여부 (law_extractor 우선순위용)
"""

from __future__ import annotations

import re
from typing import Literal, TypedDict

ChunkType = Literal["text", "table"]


class Chunk(TypedDict):
    text: str
    article: str
    type: ChunkType
    has_numbers: bool


# 조문 패턴
_ARTICLE_PATTERN = re.compile(
    r"^(제\s*\d+조(?:\s*제\s*\d+항)?|\d+[\.\-]\s|[가-힣]\.\s)"
)
_TABLE_LINE_RE = re.compile(r"^\s*\|")
_FOOTNOTE_RE = re.compile(r"^\s*※")
_DANSEO_RE = re.compile(r"^\s*단\s*[,。]")
_NUMBER_RE = re.compile(r"\d")


def _match_article(line: str) -> str | None:
    stripped = line.lstrip()
    m = _ARTICLE_PATTERN.match(stripped)
    return m.group(1).strip() if m else None


def _is_table(line: str) -> bool:
    return bool(_TABLE_LINE_RE.match(line))


def _is_footnote(line: str) -> bool:
    return bool(_FOOTNOTE_RE.match(line))


def _is_danseo(line: str) -> bool:
    return bool(_DANSEO_RE.match(line.lstrip()))


def _has_numbers(text: str) -> bool:
    return bool(_NUMBER_RE.search(text))


def _flush_chunk(
    chunks: list[Chunk],
    buffer: list[str],
    article: str,
    ctype: ChunkType,
) -> None:
    if not buffer:
        return
    text = "\n".join(buffer).strip()
    if not text:
        return
    chunks.append(
        Chunk(
            text=text,
            article=article,
            type=ctype,
            has_numbers=_has_numbers(text),
        )
    )


def chunk_law_markdown(markdown_text: str) -> list[Chunk]:
    """법령 마크다운을 조문+표 단위 청크 배열로 변환.

    Args:
        markdown_text: cleaner로 정제된 마크다운

    Returns:
        Chunk 배열
    """
    if not markdown_text:
        return []

    chunks: list[Chunk] = []
    lines = markdown_text.split("\n")

    buf: list[str] = []
    pre_table_buf: list[str] = []  # 표 앞 2줄 컨텍스트 버퍼
    in_table = False
    current_article = ""

    for line in lines:
        # ── 표 시작 감지 ───────────────────────────
        if _is_table(line) and not in_table:
            in_table = True
            # 현재 텍스트 버퍼의 뒤쪽 2줄을 표 컨텍스트로 이동
            context = buf[-2:]
            prev_body = buf[:-2]
            if prev_body:
                _flush_chunk(chunks, prev_body, current_article, "text")
            buf = list(context)
            buf.append(line)
            continue

        # ── 표 종료 감지 ───────────────────────────
        if in_table and not _is_table(line):
            if _is_footnote(line):
                buf.append(line)
                continue
            # 표 블록 flush
            _flush_chunk(chunks, buf, current_article, "table")
            buf = []
            in_table = False
            # 지금 줄을 새 텍스트 버퍼에 담기 (조문 매칭도 별도로)

        # ── 조문 경계 감지 (표 안에서는 비활성) ────
        if not in_table:
            article = _match_article(line)
            if article:
                # 단서("단, ...") 는 직전 조문에 계속 붙임
                if _is_danseo(line):
                    buf.append(line)
                    continue
                # 기존 버퍼 flush 후 새 조문 시작
                if buf:
                    _flush_chunk(chunks, buf, current_article, "text")
                    buf = []
                current_article = article

        buf.append(line)

    # ── 마지막 버퍼 flush ───────────────────────────
    if buf:
        _flush_chunk(chunks, buf, current_article, "table" if in_table else "text")

    # 빈 아티클은 "상위없음" 명시
    for c in chunks:
        if not c["article"]:
            c["article"] = "(상위 조문 없음)"

    return chunks
