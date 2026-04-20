"""매칭 방법 타입 정의 — Wave A 공통 계약.

MatchMethod: Literal 타입으로 허용 값을 정적으로 제한.
MATCH_METHODS: frozenset — 런타임 유효성 검증용.

사용 예:
    from backend.common.match_method import MatchMethod, MATCH_METHODS

    def set_match(method: MatchMethod) -> None:
        assert method in MATCH_METHODS
"""

from __future__ import annotations

from typing import Literal

# 정적 타입 어노테이션용
MatchMethod = Literal["exact", "normalized", "fuzzy", "synonym"]

# 런타임 검증용 상수 (Literal 값과 반드시 동일하게 유지)
MATCH_METHODS: frozenset[str] = frozenset({"exact", "normalized", "fuzzy", "synonym"})
