"""단위 변환 엔진 — 텍스트 레벨 + 수치 레벨 + F1 공통 단위 정규화.

출처:
    - newsamc src/lib/translation/unit-converter.ts (텍스트 레벨)
    - 계획/기능1_참고자료/05_단위변환_엔진.md (수치 레벨)
    - 계획/f1 재설계 계획/11_단위_정규화_모듈_설계.md (F1 공통 단위 정규화)

용도:
    A. 텍스트 레벨: 라벨 OCR 결과 "16 oz" → "453.59g (16 oz)" 정규화
    B. 수치 레벨: 사용자 입력 "0.05%" vs 기준치 "0.6 g/kg" 단위 통일 후 비교
    C. F1 공통 단위 정규화: 15116583 UNIT_NM 혼재 단위 → "mg/kg" 기준 통일
       (normalize_to_common_unit, parse_numeric_spec, parse_non_numeric_spec,
        SpecEvaluation, UnitIncompatibleError)

에지 케이스 (§7):
    - 복합 단위 ("mg/kg (건조물 기준)") — 접미 주석 무시, mg/kg 추출
    - 한글 단위 ("퍼센트" → "%", "피피엠" → "ppm") — 매핑 테이블 적용
    - 부등호 범위 ("85.0이상", "0.1이하", "0.01~0.1") — 정규식 파서
    - null/빈 단위 — parse_non_numeric_spec 위임
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
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
            except ValueError:  # pragma: no cover  — 정규식이 숫자만 캡처하므로 도달 불가
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
    except ValueError:  # pragma: no cover  — 정규식이 숫자만 캡처하므로 도달 불가
        return None


# ============================================================
# C. F1 공통 단위 정규화 (11_단위_정규화_모듈_설계.md §2~§5)
# ============================================================

# TODO Wave 2: UnitIncompatibleError 를 backend/exceptions.py F1PipelineError
#              계층으로 이관하여 에러 계층 통일 검토.
class UnitIncompatibleError(Exception):
    """변환 불가 단위 조합 — 예: IU/kg (국제단위, mg/kg 수치 대응 없음).

    Wave 2에서 exceptions.py 계층(F1PipelineError 하위)으로 이관 검토.
    """

    def __init__(self, unit: str, message: str = "") -> None:
        self.unit = unit
        super().__init__(message or f"Unit '{unit}' cannot be converted to mg/kg")


@dataclass
class SpecEvaluation:
    """비수치 기준값 평가 결과 (11_단위_정규화_모듈_설계.md §4).

    Attributes:
        kind: 분류
            - "numeric"     : 수치 비교 가능 (min_val/max_val 참조)
            - "non_detect"  : 불검출/음성 — 측정값 > 0 이면 fail
            - "qualitative" : 적합/적정량 — 담당자 판단 필요 (requires_hitl=True)
            - "unknown"     : 파싱 실패 — HITL 에스컬레이션 필요
        value: numeric kind에서 단일 수치 (범위가 아닌 경우)
        label: 원문 텍스트 ("적합", "불검출" 등)
        requires_hitl: True이면 자동 판정 불가, 담당자 개입 필요
    """

    kind: Literal["numeric", "non_detect", "qualitative", "unknown"]
    value: Optional[float] = None
    label: Optional[str] = None
    requires_hitl: bool = False


# 한글 단위 → 표준 영문 단위 매핑
_HANGUL_UNIT_MAP: dict[str, str] = {
    "퍼센트": "%",
    "피피엠": "ppm",
    "마이크로그램퍼킬로그램": "μg/kg",
    "그램퍼킬로그램": "g/kg",
    "밀리그램퍼킬로그램": "mg/kg",
    "그램퍼리터": "g/L",
    "밀리그램퍼리터": "mg/L",
    "아이유퍼킬로그램": "IU/kg",
    # 축약 형태
    "퍼센": "%",
    "피피엠(ppm)": "ppm",
    # 추가 한글 형태
    "밀리그램퍼킬로": "mg/kg",
    "마이크로그램": "μg/kg",
    "피피비": "ppb",
    "엠엘퍼지": "mL/g",
    "밀리리터퍼그램": "mL/g",
}

# 복합 단위 접미 주석 제거 패턴 — "mg/kg (건조물 기준)" → "mg/kg"
_UNIT_SUFFIX_COMMENT_RE = re.compile(r"\s*\([^)]*\)\s*$")

# 정규화된 단위 문자열 → 변환 배율 (결과 단위: mg/kg)
# g/L, mg/L 는 density 의존이라 별도 처리
_UNIT_TO_MGKG: dict[str, float] = {
    "mg/kg": 1.0,
    "ppm": 1.0,          # ppm ≡ mg/kg (고체 기준)
    "g/kg": 1_000.0,
    "μg/kg": 0.001,
    "ug/kg": 0.001,      # μ 대신 u 표기 허용
    "mcg/kg": 0.001,     # mcg (micrograms) 표기 허용
    "ppb": 0.001,        # ppb ≡ μg/kg
    "%": 10_000.0,       # 1% = 10,000 mg/kg
    "mg/g": 1_000.0,     # mg/g = g/kg 동일
    "μg/g": 1.0,         # μg/g = mg/kg 동일
    "ug/g": 1.0,         # μg/g 대체 표기
    "mcg/g": 1.0,        # mcg/g 대체 표기
    "g/g": 1_000_000.0,  # g/g = 10^6 mg/kg
}

# 변환 불가 단위 (UnitIncompatibleError)
_INCOMPATIBLE_UNITS: frozenset[str] = frozenset({"IU/kg", "iu/kg"})

# 비수치 SPEC_VAL 매핑
# non_detect 계열: 불검출/음성/미검출/검출되지 않음 → 측정값 > 0 이면 fail 대상
# qualitative 계열: 적합/적정량 → 담당자 판단 필요 (requires_hitl=True)
_NON_DETECT_LABELS = (
    "불검출",
    "음성",
    "미검출",
    "검출되지 않음",
    "검출안됨",
    "n.d.",
    "nd",
    "not detected",
    "undetected",
)
_QUALITATIVE_LABELS = (
    "적합",
    "적정량",
    "기준적합",
    "적합함",
    "적정",
    "이상없음",
)

# 부분 포함 검사용 qualitative 키워드 — 오탐 위험이 낮은 명확한 표현만 포함
# ("이상없음" 은 "이상없음(특수표현)" 등 오탐 가능 → 정확 매핑(_NON_NUMERIC_MAP)에서만 처리)
_QUALITATIVE_PARTIAL_KEYWORDS = (
    "기준적합",
    "적합함",
    "적합여부",
)

_NON_NUMERIC_MAP: dict[str, SpecEvaluation] = {
    **{
        label: SpecEvaluation(kind="non_detect", label=label, requires_hitl=False)
        for label in _NON_DETECT_LABELS
    },
    **{
        label: SpecEvaluation(kind="qualitative", label=label, requires_hitl=True)
        for label in _QUALITATIVE_LABELS
    },
}

# 한자 ↔ 한글 비교 표현 정규화
# "以下" → "이하", "以上" → "이상", "未滿" → "미만"
_HANJA_NORMALIZE: dict[str, str] = {
    "以下": "이하",
    "以上": "이상",
    "未滿": "미만",
    "超過": "초과",
    "이하이상": "이상",  # 혼용 방어
}

_HANJA_RE = re.compile("|".join(re.escape(k) for k in _HANJA_NORMALIZE))


def _normalize_spec_text(text: str) -> str:
    """SPEC_VAL 원문 텍스트 전처리.

    처리:
        1. 한자 비교 표현 → 한글 정규화 ("以下" → "이하")
        2. μ/u 혼용 허용 — 파서 호출 전 정규식 전처리 불필요 (파서가 양쪽 패턴 인식)
        3. 앞뒤 공백 제거
    """
    s = text.strip()
    s = _HANJA_RE.sub(lambda m: _HANJA_NORMALIZE[m.group(0)], s)
    return s


# parse_numeric_spec 정규식 패턴 (T2 보강)
# 지원:
#   "85.0이상"         → (85.0, None)
#   "0.1이하"          → (None, 0.1)
#   "0.01~0.1"         → (0.01, 0.1)      공백 없음
#   "0.01 ~ 0.1"       → (0.01, 0.1)      공백 포함
#   "0.01~ 0.1"        → (0.01, 0.1)      비대칭 공백
#   "5.0"              → (5.0, 5.0)
#   "3.0초과"          → (3.0, None)
#   "1.0미만"          → (None, 1.0)
#   "以下 0.5"         → 한자 정규화 후 처리 (_normalize_spec_text 선행)
#   단위 포함 "0.1 mg/kg 이하" → 숫자+비교어 부분만 추출 (전처리 후)
_NUMERIC_RANGE_RE = re.compile(
    r"^\s*"
    r"(?P<lo>\d+(?:\.\d+)?)"                        # 첫 번째 수
    r"\s*"
    r"(?:"
    r"(?P<tilde>[~～])\s*(?P<hi>\d+(?:\.\d+)?)"     # ~hi (범위), 공백 허용
    r"|(?P<gte>이상)"                                # 이상 (≥)
    r"|(?P<lte>이하)"                                # 이하 (≤)
    r"|(?P<gt>초과)"                                 # 초과 (>)
    r"|(?P<lt>미만)"                                 # 미만 (<)
    r")?\s*$"
)

# 단위 포함 SPEC_VAL 파싱용 패턴: "0.1 mg/kg 이하", "10 μg/kg 이하" 등
# 숫자 + 선택적 단위 + 비교어 구조
_SPEC_WITH_UNIT_RE = re.compile(
    r"^\s*"
    r"(?P<lo>\d+(?:\.\d+)?)"                        # 숫자
    r"\s*"
    r"(?P<unit>[a-zA-Zμμ/·%]+(?:/[a-zA-Zμ]+)?)?"   # 단위 (옵션)
    r"\s*"
    r"(?:"
    r"(?P<tilde>[~～])\s*(?P<hi>\d+(?:\.\d+)?)"
    r"\s*(?P<unit2>[a-zA-Zμ/·%]+(?:/[a-zA-Zμ]+)?)?"
    r"|(?P<gte>이상|以上)"
    r"|(?P<lte>이하|以下)"
    r"|(?P<gt>초과|超過)"
    r"|(?P<lt>미만|未滿)"
    r")?\s*$"
)

# 복합 기준 분리 패턴: "총 X는 0.1 이하, Y는 0.5 이하" → 첫 번째 기준만 채택
# 구분자: ",", "및", "또한", "；" 등
_COMPOUND_SPEC_SPLIT_RE = re.compile(r"[,，；]\s*|(?:및|또한|그리고)\s+")


def _normalize_unit_str(unit: str) -> str:
    """단위 문자열을 정규화.

    처리 순서:
        1. 한글 단위 매핑 (퍼센트 → %)
        2. 복합 단위 접미 주석 제거 (mg/kg (건조물 기준) → mg/kg)
        3. μ/u/mcg 혼용 정규화 (ug/kg → μg/kg, mcg/kg → μg/kg 를 _UNIT_TO_MGKG에서 직접 처리)
        4. strip
    """
    stripped = unit.strip()
    # 한글 매핑 먼저
    if stripped in _HANGUL_UNIT_MAP:
        return _HANGUL_UNIT_MAP[stripped]
    # 복합 단위 주석 제거
    cleaned = _UNIT_SUFFIX_COMMENT_RE.sub("", stripped).strip()
    return cleaned


def normalize_to_common_unit(
    value: float,
    from_unit: str,
    *,
    density: float = 1.0,
) -> tuple[float, str]:
    """혼재 단위를 mg/kg 기준으로 정규화 (11_단위_정규화_모듈_설계.md §2~§3).

    Args:
        value: 원본 수치
        from_unit: 원본 단위 문자열 (한글·복합 단위 포함)
        density: 액체 단위(g/L, mg/L) 변환 시 사용하는 비중 [g/mL].
                 기본값 1.0 (물 기준). backend/constants/density.py 참조.

    Returns:
        (정규화된 값, "mg/kg")

    Raises:
        UnitIncompatibleError: IU/kg 등 mg/kg 으로 변환 불가능한 단위
        ValueError: 인식 불가능한 단위 (unknown unit)

    에지 케이스:
        - "mg/kg (건조물 기준)" → 접미 주석 무시, mg/kg 처리
        - "퍼센트" → % → 10,000 배
        - "피피엠" → ppm → 1배
        - density=0 이면 ZeroDivisionError (호출자 책임)
    """
    normalized_unit = _normalize_unit_str(from_unit)

    # 변환 불가 단위 체크
    if normalized_unit in _INCOMPATIBLE_UNITS or normalized_unit.lower() in _INCOMPATIBLE_UNITS:
        raise UnitIncompatibleError(from_unit)

    # 고정 배율 변환
    if normalized_unit in _UNIT_TO_MGKG:
        return float(value) * _UNIT_TO_MGKG[normalized_unit], "mg/kg"

    # 소문자 시도 (대소문자 혼용 방어)
    lower = normalized_unit.lower()
    if lower in _UNIT_TO_MGKG:
        return float(value) * _UNIT_TO_MGKG[lower], "mg/kg"

    # 액체 단위 — density 필요
    if normalized_unit in ("g/L", "g/l"):
        # g/L × (1000 mg/g) / (density g/mL × 1000 mL/L) = mg/kg
        # 단순화: g/L ÷ density × 1000 = mg/kg  (density in g/mL)
        return float(value) * 1_000.0 / density, "mg/kg"

    if normalized_unit in ("mg/L", "mg/l"):
        # mg/L ÷ density = mg/kg
        return float(value) / density, "mg/kg"

    raise ValueError(f"Unknown unit: '{from_unit}' (normalized: '{normalized_unit}')")


def parse_numeric_spec(spec: str) -> tuple[Optional[float], Optional[float]]:
    """SPEC_VAL 수치 표현 파싱 (11_단위_정규화_모듈_설계.md §5).

    지원 패턴 (T2 보강):
        "85.0이상"         → (85.0, None)   # min=85, max 없음
        "0.1이하"          → (None, 0.1)    # min 없음, max=0.1
        "0.01~0.1"         → (0.01, 0.1)   # 범위 (공백 없음)
        "0.01 ~ 0.1"       → (0.01, 0.1)   # 범위 (공백 포함)
        "0.01~ 0.1"        → (0.01, 0.1)   # 범위 (비대칭 공백)
        "5.0"              → (5.0, 5.0)    # 단일 값 (등호)
        "3.0초과"          → (3.0, None)   # 초과 (> 방향, min 근사)
        "1.0미만"          → (None, 1.0)   # 미만 (< 방향, max 근사)
        "以下"↔"이하" 등 한자 혼용 → _normalize_spec_text 선행 처리
        "총 X는 0.1 이하, Y는 0.5 이하" → 첫 번째 기준만 채택 (복합 기준)
        "0.1 mg/kg 이하" → 단위 포함 표현도 파싱 (_SPEC_WITH_UNIT_RE 시도)

    Returns:
        (min_val, max_val). 한쪽만 존재하면 나머지는 None.
        파싱 실패 시 (None, None).

    Note:
        "이상"/"초과" 는 의미론적 차이(≥ vs >) 가 있으나 수치 비교 목적상
        동일 반환 구조를 사용한다. 호출자가 context 를 보고 판단.
        복합 기준은 첫 번째 항목만 채택하고 나머지는 무시한다.
    """
    if not spec or not spec.strip():
        return None, None

    # 한자 정규화 + 공백 제거
    normalized = _normalize_spec_text(spec)
    if not normalized:
        return None, None

    # 복합 기준 처리: 구분자로 분리 후 첫 번째만 사용
    parts = _COMPOUND_SPEC_SPLIT_RE.split(normalized, maxsplit=1)
    candidate = parts[0].strip() if parts else normalized

    # 1차 시도: 순수 수치 범위 정규식
    m = _NUMERIC_RANGE_RE.match(candidate)
    if m:
        return _extract_min_max_from_match(m)

    # 2차 시도: 단위 포함 표현 ("0.1 mg/kg 이하" 등)
    m2 = _SPEC_WITH_UNIT_RE.match(candidate)
    if m2:
        return _extract_min_max_from_match(m2)

    return None, None


def _extract_min_max_from_match(m: re.Match) -> tuple[Optional[float], Optional[float]]:
    """정규식 매치 결과에서 (min, max) 추출 (공통 헬퍼)."""
    lo = float(m.group("lo"))

    if m.group("tilde") is not None:
        hi_str = m.group("hi")
        if hi_str is not None:
            hi = float(hi_str)
            return lo, hi
    if m.group("gte") is not None or m.group("gt") is not None:
        return lo, None
    if m.group("lte") is not None or m.group("lt") is not None:
        return None, lo
    # 단일 값
    return lo, lo


def parse_non_numeric_spec(spec: str) -> SpecEvaluation:
    """비수치 SPEC_VAL 파싱 (11_단위_정규화_모듈_설계.md §4).

    Args:
        spec: SPEC_VAL 원문 (예: "적합", "불검출", "음성", "적정량", "미검출",
              "검출되지 않음", "적합함" 등 T2 보강 패턴 포함)

    Returns:
        SpecEvaluation — kind/label/requires_hitl 설정됨.
        인식 불가 텍스트는 kind="unknown", requires_hitl=True.

    Note:
        수치 표현("85.0이상" 등)도 입력될 수 있으나 이 함수의 책임 범위 外.
        호출자는 parse_numeric_spec 를 먼저 시도하고 실패 시 이 함수를 호출한다.
        소문자/대문자 혼용, 앞뒤 공백은 정규화 후 매핑 시도한다.
    """
    if not spec:
        return SpecEvaluation(kind="unknown", label=spec, requires_hitl=True)

    stripped = spec.strip()

    # 1차: 정확 매핑
    if stripped in _NON_NUMERIC_MAP:
        return _NON_NUMERIC_MAP[stripped]

    # 2차: 소문자 정규화 후 매핑 (영문 표기 대소문자 허용)
    lower = stripped.lower()
    for label, evaluation in _NON_NUMERIC_MAP.items():
        if label.lower() == lower:
            return SpecEvaluation(
                kind=evaluation.kind,
                label=stripped,
                requires_hitl=evaluation.requires_hitl,
            )

    # 3차: non_detect 부분 포함 검사 ("검출되지 않음 (LOD 0.01)" 등 접미사 허용)
    # 짧은 라벨(≤2자, "nd" 등) 은 오탐 위험 — startswith만 허용, 부분포함은 3자 이상만
    for label in _NON_DETECT_LABELS:
        if stripped.startswith(label) or (len(label) >= 3 and label in stripped):
            return SpecEvaluation(kind="non_detect", label=stripped, requires_hitl=False)

    # 4차: qualitative 부분 포함 검사
    # 오탐 방지: 다른 표현의 부분 문자열이 될 수 있는 짧은 키워드("이상없음" 등) 제외.
    # "기준적합", "적합함" 은 "적합"보다 구체적이어서 오탐 위험 낮음.
    for label in _QUALITATIVE_PARTIAL_KEYWORDS:
        if label in stripped:
            return SpecEvaluation(kind="qualitative", label=stripped, requires_hitl=True)

    # 5차: 수치 패턴이면 numeric으로 분류 (방어적 처리)
    min_val, max_val = parse_numeric_spec(stripped)
    if min_val is not None or max_val is not None:
        return SpecEvaluation(
            kind="numeric",
            value=min_val if min_val == max_val else None,
            label=stripped,
            requires_hitl=False,
        )

    return SpecEvaluation(kind="unknown", label=stripped, requires_hitl=True)
