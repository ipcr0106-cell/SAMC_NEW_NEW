"""조건부(restricted) 원료의 usage_condition 텍스트 분류 패턴.

출처:
    - newsamc src/constants/condition-patterns.ts
    - 계획/기능1_참고자료/03_복합원재료_조건부판정.md §2

우선순위:
    정의된 순서대로 매칭. 첫 번째로 매칭되는 패턴이 채택됨.
"""

import re
from typing import Literal

ConditionType = Literal[
    "usage_purpose",
    "part_restriction",
    "quantity_limit",
    "natural_synthetic",
    "irradiation",
    "ambiguous",
]


# (정규식, 조건유형) 튜플의 리스트. 순서가 우선순위.
CONDITION_PATTERNS: list[tuple[re.Pattern[str], ConditionType]] = [
    (re.compile(r"용도|목적|사용\s*용도", re.IGNORECASE), "usage_purpose"),
    (re.compile(r"부위|뿌리|잎|줄기|종자|열매", re.IGNORECASE), "part_restriction"),
    (re.compile(r"함량|%|이하|이상|mg|g/kg|ppm", re.IGNORECASE), "quantity_limit"),
    (re.compile(r"천연|합성|자연", re.IGNORECASE), "natural_synthetic"),
    (re.compile(r"조사|방사선|irradiat", re.IGNORECASE), "irradiation"),
]


def classify_condition_type(conditions: str | None) -> ConditionType:
    """조건 텍스트를 패턴에 따라 ConditionType으로 분류한다.

    Args:
        conditions: ingredient_list.usage_condition 값 또는 None

    Returns:
        첫 번째로 매칭되는 패턴의 type. 매칭 없으면 'ambiguous'.
    """
    if not conditions:
        return "ambiguous"
    for pattern, ctype in CONDITION_PATTERNS:
        if pattern.search(conditions):
            return ctype
    return "ambiguous"


def validate_part_restriction(conditions: str, part: str) -> bool:
    """부위 제한 자동 검증. 원재료의 신고 부위가 조건 텍스트에 포함되는지.

    Args:
        conditions: "사용부위: 종실(볶은 것)" 같은 조건 텍스트
        part: 원재료의 신고 부위 ("종실", "잎" 등)

    Returns:
        True=부위 적합, False=부위 불적합
    """
    if not conditions or not part:
        return False
    return part.lower() in conditions.lower()
