"""Generic Result[T] — ok / partial / err 세 상태를 표현하는 경량 결과 타입.

Phase 0 공통 계약 (Wave A):
    - ok(value)           : 정상 완료, value 존재
    - partial(value, reason) : 부분 성공, value 있지만 이유 포함
    - err(reason)         : 실패, value 없음

설계 선택:
    dataclass(frozen=True) 방식 채택.
    __slots__ 보다 불변성 보장 + @dataclass 어노테이션 자동 제공이 Pythonic.
    Generic[T] 로 타입 안전성 유지.

사용 예:
    r = Result.ok([1, 2, 3])
    r.is_ok()           # True
    r.unwrap_or([])     # [1, 2, 3]

    r2 = Result.err("DB 연결 실패")
    r2.is_err()         # True
    r2.unwrap_or([])    # []
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, Optional, TypeVar

T = TypeVar("T")
U = TypeVar("U")

_STATE_OK = "ok"
_STATE_PARTIAL = "partial"
_STATE_ERR = "err"


@dataclass(frozen=True)
class Result(Generic[T]):
    """불변 결과 컨테이너.

    직접 생성 대신 클래스메서드 ok / partial / err 을 사용하세요.
    """

    _value: Optional[T]
    _reason: Optional[str]
    _state: str  # "ok" | "partial" | "err"

    # ------------------------------------------------------------------
    # 생성자 (클래스메서드 팩토리)
    # ------------------------------------------------------------------

    @classmethod
    def ok(cls, value: T) -> "Result[T]":
        """정상 결과."""
        return cls(_value=value, _reason=None, _state=_STATE_OK)

    @classmethod
    def partial(cls, value: T, reason: str) -> "Result[T]":
        """부분 성공 — value 는 존재하지만 완전하지 않음."""
        return cls(_value=value, _reason=reason, _state=_STATE_PARTIAL)

    @classmethod
    def err(cls, reason: str) -> "Result[T]":
        """실패 — value 없음."""
        return cls(_value=None, _reason=reason, _state=_STATE_ERR)

    # ------------------------------------------------------------------
    # 판별 메서드
    # ------------------------------------------------------------------

    def is_ok(self) -> bool:
        return self._state == _STATE_OK

    def is_partial(self) -> bool:
        return self._state == _STATE_PARTIAL

    def is_err(self) -> bool:
        return self._state == _STATE_ERR

    # ------------------------------------------------------------------
    # 헬퍼
    # ------------------------------------------------------------------

    def unwrap_or(self, default: T) -> T:
        """값이 있으면 반환, 없으면 default."""
        return self._value if self._value is not None else default

    def map(self, fn: Callable[[T], U]) -> "Result[U]":
        """ok/partial 시 fn 을 value 에 적용, err 시 reason 보존."""
        if self._value is None:
            return Result(_value=None, _reason=self._reason, _state=self._state)
        return Result(
            _value=fn(self._value),
            _reason=self._reason,
            _state=self._state,
        )

    # ------------------------------------------------------------------
    # 접근자 (읽기)
    # ------------------------------------------------------------------

    @property
    def value(self) -> Optional[T]:
        """내부 값. err 상태이면 None."""
        return self._value

    @property
    def reason(self) -> Optional[str]:
        """실패/부분성공 사유. ok 상태이면 None."""
        return self._reason

    @property
    def state(self) -> str:
        """상태 문자열: 'ok' | 'partial' | 'err'."""
        return self._state

    # ------------------------------------------------------------------
    # repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        if self._state == _STATE_OK:
            return f"Result.ok({self._value!r})"
        if self._state == _STATE_PARTIAL:
            return f"Result.partial({self._value!r}, reason={self._reason!r})"
        return f"Result.err({self._reason!r})"
