"""기능1 매칭/검증 임계값·상수.

출처:
    - newsamc src/constants/thresholds.ts (LIQUOR_BOUNDARY_THRESHOLDS, GENERAL_LIMIT_TEXT)
    - newsamc src/lib/judgment/m4-1/match-chain.ts (CONFIDENCE 상수)
    - newsamc src/lib/judgment/m4-3/liquor-safety.ts (LIQUOR_CHECK_ITEMS)
    - 계획/기능1_참고자료/02_매칭체인_5단계.md, 04_기준치검증_일반_및_주류.md
"""

# ============================================================
# 매칭 신뢰도 상수
# ============================================================
EXACT_MATCH_CONFIDENCE: float = 1.0
FUZZY_MATCH_CONFIDENCE: float = 0.7
LLM_NORMALIZE_CONFIDENCE: float = 0.5

# 퍼지 매칭 유사도 컷오프 (이 값 미만이면 unidentified 처리)
FUZZY_SIMILARITY_THRESHOLD: float = 0.3


# ============================================================
# 주류 안전기준 - 알코올 도수 경계
# ============================================================
LIQUOR_BOUNDARY_THRESHOLDS: dict[str, float] = {
    # 이 값 미만은 비알코올로 간주 (검사 대상 아님)
    "non_alcohol_max": 0.5,
    # 이 값 미만은 주류/비주류 경계치 → 에스컬레이션
    "boundary_max": 1.0,
}


# ============================================================
# 주류 4대 검사 항목
# ============================================================
LIQUOR_CHECK_ITEMS: list[dict[str, str]] = [
    {"name": "메탄올", "standard_type": "contaminant"},
    {"name": "알데히드", "standard_type": "contaminant"},
    {"name": "퓨젤유", "standard_type": "contaminant"},
    {"name": "에탄올(주정도)", "standard_type": "contaminant"},
]


# ============================================================
# 일반식품 기준치 - 기본 텍스트
# ============================================================
GENERAL_LIMIT_TEXT: dict[str, str] = {
    "not_registered": "기준 미등록",
    "not_usable": "사용불가",
}


# ============================================================
# 합성향료 키워드 (개발계획서 §4-1 고유 예외처리)
# ============================================================
SYNTHETIC_FLAVOR_KEYWORDS: list[str] = [
    "합성향료",
    "인공향료",
    "synthetic flavor",
    "artificial flavoring",
    "artificial flavor",
]


def is_synthetic_flavor(name: str) -> bool:
    """원재료명이 합성향료에 해당하는지 판정."""
    if not name:
        return False
    lowered = name.lower()
    return any(kw.lower() in lowered for kw in SYNTHETIC_FLAVOR_KEYWORDS)


def is_alcohol_boundary(percentage: float | None) -> bool:
    """알코올 도수가 주류/비주류 경계치인지 판정.

    - None → False
    - 0 ≤ pct < non_alcohol_max(0.5) → False (비알코올)
    - non_alcohol_max ≤ pct < boundary_max(1.0) → True (경계치, 에스컬레이션)
    - boundary_max ≤ pct → False (확실한 주류)
    """
    if percentage is None:
        return False
    return (
        LIQUOR_BOUNDARY_THRESHOLDS["non_alcohol_max"]
        <= percentage
        < LIQUOR_BOUNDARY_THRESHOLDS["boundary_max"]
    )
