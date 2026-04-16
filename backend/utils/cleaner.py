"""kordoc 변환 후 마크다운 정제.

담당: 병찬
참고:
    - 개발계획서 §4-0 문제 A (줄 앞이 잘린 텍스트)
    - 계획/기능1_구현계획/03_백엔드_구현_계획.md T8

주요 기능:
    1. 규칙 기반 줄 병합 — 2단 레이아웃 등으로 앞이 잘린 줄을 직전 줄에 병합
    2. 이상 문자 제거 — 비인쇄 제어문자, 잘못된 공백
    3. (선택) Claude API 기반 섹션별 정제 — future work
"""

from __future__ import annotations

import re
import unicodedata

# ============================================================
# 정규식 상수
# ============================================================

# 조문 시작 패턴 — 제N조, N.1, 가., ※, |(표), # (헤더)
_ARTICLE_HEAD_PATTERNS = [
    r"^#",
    r"^\|",
    r"^※",
    r"^제\s*\d+",
    r"^\d+[\.\-]",
    r"^[가-힣]\.",
    r"^-\s",
]
_ARTICLE_HEAD_RE = re.compile("|".join(_ARTICLE_HEAD_PATTERNS))

# 완결 문장 어미 — 병합 금지 조건
_SENTENCE_ENDING_RE = re.compile(r"(?:다\.|한다\.|된다\.|있다\.|\.|\?|\!)\s*$")

# 비인쇄 제어문자 (탭·개행 제외)
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# 여러 공백을 하나로
_MULTIPLE_SPACES_RE = re.compile(r"[ \t]{2,}")


def _is_new_article_line(line: str) -> bool:
    """해당 줄이 새 조문·표·헤더·불릿 시작인지."""
    stripped = line.lstrip()
    if not stripped:
        return False
    return bool(_ARTICLE_HEAD_RE.match(stripped))


def _prev_is_complete(prev_line: str) -> bool:
    """직전 줄이 완결 문장으로 끝나는지."""
    return bool(_SENTENCE_ENDING_RE.search(prev_line))


def merge_broken_lines(markdown_text: str) -> str:
    """앞이 잘린 줄을 직전 줄에 병합.

    규칙:
        - 빈 줄은 그대로 유지
        - 현재 줄이 새 조문·표·헤더·불릿 시작이면 병합 X
        - 직전 줄이 완결 문장이면 병합 X
        - 그 외 → 직전 줄에 공백 없이 붙임
    """
    if not markdown_text:
        return ""
    lines = markdown_text.split("\n")
    merged: list[str] = []
    for line in lines:
        if not line.strip():
            merged.append(line)
            continue
        if not merged:
            merged.append(line)
            continue
        if _is_new_article_line(line):
            merged.append(line)
            continue
        if _prev_is_complete(merged[-1]):
            merged.append(line)
            continue
        # 병합: 직전 줄에 공백 없이 이어붙임
        merged[-1] = merged[-1].rstrip() + line.lstrip()
    return "\n".join(merged)


def strip_control_chars(text: str) -> str:
    """비인쇄 제어문자 제거 + 유니코드 정규화."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFC", text)
    return _CTRL_RE.sub("", normalized)


def normalize_whitespace(text: str) -> str:
    """연속 공백을 단일 공백으로 + 줄 끝 공백 제거."""
    if not text:
        return ""
    lines = [_MULTIPLE_SPACES_RE.sub(" ", ln.rstrip()) for ln in text.split("\n")]
    return "\n".join(lines)


def clean_law_markdown(raw_markdown: str) -> str:
    """메인 진입점 — 모든 정제 단계를 순차 적용.

    Args:
        raw_markdown: kordoc 등으로 변환된 원본 마크다운

    Returns:
        정제된 마크다운
    """
    if not raw_markdown:
        return ""
    stripped = strip_control_chars(raw_markdown)
    merged = merge_broken_lines(stripped)
    normalized = normalize_whitespace(merged)
    return normalized
