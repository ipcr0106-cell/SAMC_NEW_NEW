"""단위 변환 엔진 — 텍스트 레벨 + 수치 레벨.

출처:
    - newsamc src/lib/translation/unit-converter.ts (텍스트 레벨)
    - 계획/기능1_참고자료/05_단위변환_엔진.md (수치 레벨)

용도:
    A. 텍스트 레벨: 라벨 OCR 결과 "16 oz" → "453.59g (16 oz)" 정규화
    B. 수치 레벨: 사용자 입력 "0.05%" vs 기준치 "0.6 g/kg" 단위 통일 후 비교
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel

ConversionType = Literal["weight", "volume", "temperature"]


# ============================================================
# 변환 상수
# ============================================================
OZ_TO_G = 28.3495
LB_TO_G = 453.592
FL_OZ_TO_ML = 29.5735
GAL_TO_ML = 3785.41
DECIMAL_PLACES = 2


def _r2(v: float) -> float:
    """소수점 2자리 반올림."""
    return round(v, DECIMAL_PLACES)


# ============================================================
# 텍스트 레벨 변환 (A)
# ============================================================


class UnitConversion(BaseModel):
    """변환 기록 (텍스트 레벨)."""

    original: str
    converted: str
    type: ConversionType


# (정규식, 타입, 변환 함수)
_TEXT_RULES: list[tuple[re.Pattern[str], ConversionType, callable]] = [
    (
        re.compile(r"(\d+(?:\.\d+)?)\s*oz\b", re.IGNORECASE),
        "weight",
        lambda v: f"{_r2(v * OZ_TO_G)}g",
    ),
    (
        re.compile(r"(\d+(?:\.\d+)?)\s*lb[s]?\b", re.IGNORECASE),
        "weight",
        lambda v: f"{_r2(v * LB_TO_G)}g",
    ),
    (
        re.compile(r"(\d+(?:\.\d+)?)\s*fl\.?\s*oz\b", re.IGNORECASE),
        "volume",
        lambda v: f"{_r2(v * FL_OZ_TO_ML)}ml",
    ),
    (
        re.compile(r"(\d+(?:\.\d+)?)\s*gal(?:lon)?[s]?\b", re.IGNORECASE),
        "volume",
        lambda v: f"{_r2(v * GAL_TO_ML)}ml",
    ),
    (
        re.compile(r"(\d+(?:\.\d+)?)\s*°F\b", re.IGNORECASE),
        "temperature",
        lambda v: f"{_r2((v - 32) * 5 / 9)}°C",
    ),
]


def convert_units_in_text(text: str) -> tuple[str, list[UnitConversion]]:
    """텍스트 내 영미 단위를 한국 표준으로 변환.

    Returns:
        (변환된 텍스트, 변환 기록 리스트)
    """
    conversions: list[UnitConversion] = []
    converted = text

    for pattern, ctype, fn in _TEXT_RULES:

        def _sub(m: re.Match[str], _fn=fn, _type=ctype) -> str:
            try:
                num = float(m.group(1))
            except ValueError:
                return m.group(0)
            replacement = _fn(num)
            original = m.group(0).strip()
            conversions.append(
                UnitConversion(original=original, converted=replacement, type=_type)
            )
            return f"{replacement} ({original})"

        converted = pattern.sub(_sub, converted)

    return converted, conversions


# ============================================================
# 수치 레벨 변환 (B) — 기준치 비교용
# ============================================================


def _normalize_unit(u: str) -> str:
    """단위 문자열을 정규화된 소문자로."""
    return u.strip().lower().replace(" ", "")


def convert_unit(
    value: float,
    source_unit: str,
    target_unit: str,
    factor: Optional[float] = None,
) -> float:
    """수치 단위 변환. factor가 있으면 먼저 적용 (염→산 환산 등).

    지원 변환:
        - 동일 단위 (source == target)
        - % ↔ g/kg ↔ mg/kg ↔ ppm
        - ppm == mg/kg 동일 취급
        - factor: DB의 conversion_factor (예: 안식향산나트륨 0.847)

    Raises:
        ValueError: 미지원 단위 쌍
    """
    if value is None:
        raise ValueError("value is None")

    # H-NEW-3 가드: conversion_factor 는 양수만 유효. 0·음수면 ValueError.
    # (DB CHECK 제약으로 1차 방어되지만 코드 수준 2차 방어)
    # 추가: asyncpg 가 PostgreSQL NUMERIC 을 Decimal 로 반환하므로 float 강제 변환.
    if factor is not None:
        try:
            factor_f = float(factor)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"conversion_factor cast failed: {exc}") from exc
        if factor_f <= 0:
            raise ValueError(f"conversion_factor must be > 0, got {factor}")
        v = float(value) * factor_f
    else:
        v = float(value)

    s = _normalize_unit(source_unit)
    t = _normalize_unit(target_unit)

    # 동일 단위
    if s == t:
        return v

    # ppm ↔ mg/kg 동일 취급
    if s == "ppm":
        s = "mg/kg"
    if t == "ppm":
        t = "mg/kg"
    if s == t:
        return v

    # % → g/kg → mg/kg
    if s == "%":
        base = v * 10.0  # %를 g/kg로
        if t == "g/kg":
            return base
        if t == "mg/kg":
            return base * 1000.0
    if s == "g/kg":
        if t == "mg/kg":
            return v * 1000.0
        if t == "%":
            return v / 10.0
    if s == "mg/kg":
        if t == "g/kg":
            return v / 1000.0
        if t == "%":
            return v / 10000.0

    raise ValueError(f"Unsupported conversion: {source_unit} -> {target_unit}")


def parse_numeric_limit(limit_text: str) -> Optional[tuple[float, str]]:
    """'0.6 g/kg' 같은 문자열 기준치를 (값, 단위) 튜플로 파싱.

    비수치 기준 ('불검출', '음성' 등)은 None 반환.

    Returns:
        (값, 단위) 또는 None
    """
    if not limit_text:
        return None
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(.+?)\s*$", limit_text)
    if not m:
        return None
    try:
        return float(m.group(1)), m.group(2)
    except ValueError:
        return None
