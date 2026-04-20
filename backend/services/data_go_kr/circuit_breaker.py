"""Circuit Breaker — data.go.kr 엔드포인트별 in-memory 상태 관리.

08_에러_처리_설계.md §5 기준:
    - CLOSED / OPEN / HALF_OPEN 3상태
    - 5분 window 내 연속 실패 20회 OR 실패율 > 80% → OPEN
    - OPEN 30분 경과 → HALF_OPEN
    - HALF_OPEN에서 1건 테스트 → 성공 시 CLOSED, 실패 시 OPEN 유지
    - in-memory (프로세스 단위), 엔드포인트별 독립 인스턴스
    - pybreaker 사용 금지 (자체 구현)

공개 인터페이스:
    async def call(self, endpoint_id: str, coro: Awaitable) -> Any
        OPEN 이면 CircuitBreakerOpenError raise.
        아니면 coro 실행 후 성공/실패를 상태 머신에 기록.

팩토리:
    get_circuit_breaker(endpoint_id: str) -> CircuitBreaker
        엔드포인트별 싱글턴 반환.

W1-A stub 보존:
    NoOpBreaker, CircuitBreakerLike 는 W1-A DataGoKrClient 통합용으로 유지.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Awaitable, Deque, Dict, Optional, Protocol, TypeVar, runtime_checkable

from exceptions import CircuitBreakerOpenError

logger = logging.getLogger("f1.circuit_breaker")

T = TypeVar("T")


# ============================================================
# W1-A stub 보존 (변경 금지)
# ============================================================


@runtime_checkable
class CircuitBreakerLike(Protocol):
    """Circuit Breaker 최소 Protocol."""

    def allow(self, endpoint: str) -> None: ...
    def record_success(self, endpoint: str) -> None: ...
    def record_failure(self, endpoint: str) -> None: ...


class NoOpBreaker:
    """아무 것도 차단하지 않는 가짜 Breaker (W1-A 통합용 stub).

    W1-C 본체 구현 이전 기본값. 호출 허용·기록만 수행하고 상태 전이 없음.
    """

    def allow(self, endpoint: str) -> None:  # noqa: ARG002 - stub
        return None

    def record_success(self, endpoint: str) -> None:  # noqa: ARG002 - stub
        return None

    def record_failure(self, endpoint: str) -> None:  # noqa: ARG002 - stub
        return None


# ============================================================
# 상태 정의
# ============================================================


class CBState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


# ============================================================
# 설정 상수 (08번 §5 기준)
# ============================================================

_FAILURE_WINDOW_S: float = 300.0       # 5분 슬라이딩 윈도우
_CONSECUTIVE_FAIL_THRESHOLD: int = 20  # 연속 실패 임계
_FAILURE_RATE_THRESHOLD: float = 0.80  # 실패율 80% 임계
_OPEN_DURATION_S: float = 1800.0       # OPEN 유지 30분
_MIN_CALLS_FOR_RATE: int = 5           # 실패율 계산 최소 호출 수


# ============================================================
# CircuitBreaker 클래스 (W1-C 본체)
# ============================================================


@dataclass
class CircuitBreaker:
    """엔드포인트 하나에 대응하는 Circuit Breaker 인스턴스.

    Args:
        endpoint_id: data.go.kr 엔드포인트 식별자 (예: "15111777").
        failure_window_s: 슬라이딩 윈도우 크기(초). 기본 5분.
        consecutive_fail_threshold: 연속 실패 임계값. 기본 20회.
        failure_rate_threshold: 실패율 임계값(0~1). 기본 0.80.
        open_duration_s: OPEN 상태 유지 시간(초). 기본 30분.
        min_calls_for_rate: 실패율 계산 최소 호출 수. 기본 5.
    """

    endpoint_id: str
    failure_window_s: float = _FAILURE_WINDOW_S
    consecutive_fail_threshold: int = _CONSECUTIVE_FAIL_THRESHOLD
    failure_rate_threshold: float = _FAILURE_RATE_THRESHOLD
    open_duration_s: float = _OPEN_DURATION_S
    min_calls_for_rate: int = _MIN_CALLS_FOR_RATE

    # 내부 상태 (직접 접근 금지)
    _state: CBState = field(default=CBState.CLOSED, init=False, repr=False)
    _consecutive_failures: int = field(default=0, init=False, repr=False)
    _call_timestamps: Deque[float] = field(
        default_factory=deque, init=False, repr=False
    )
    _failure_timestamps: Deque[float] = field(
        default_factory=deque, init=False, repr=False
    )
    _opened_at: Optional[float] = field(default=None, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    # --------------------------------------------------------
    # 공개 프로퍼티
    # --------------------------------------------------------

    @property
    def state(self) -> CBState:
        return self._state

    # --------------------------------------------------------
    # 핵심 공개 메서드
    # --------------------------------------------------------

    async def call(
        self,
        endpoint_id: str,
        coro: Awaitable[T],
    ) -> T:
        """coro 를 실행하고 결과·실패를 상태 머신에 기록한다.

        Args:
            endpoint_id: 호출 대상 엔드포인트 id (로깅에 사용).
            coro: 실행할 코루틴.

        Returns:
            coro 의 반환값.

        Raises:
            CircuitBreakerOpenError: OPEN 상태일 때.
            Exception: coro 자체에서 발생한 예외 (기록 후 재raise).
        """
        async with self._lock:
            self._maybe_transition_to_half_open()
            current_state = self._state

        if current_state == CBState.OPEN:
            # coroutine 객체가 전달된 경우 close() 로 정리하여 ResourceWarning 방지
            if hasattr(coro, "close"):
                coro.close()  # type: ignore[union-attr]
            reopen_at = self._reopen_at_datetime()
            raise CircuitBreakerOpenError(
                f"Circuit breaker OPEN for endpoint {endpoint_id}",
                endpoint=endpoint_id,
                reopen_at=reopen_at,
            )

        try:
            result = await coro
        except Exception:
            async with self._lock:
                self._record_failure()
                logger.warning(
                    "CircuitBreaker recorded failure for %s (state=%s, consecutive=%d)",
                    endpoint_id,
                    self._state.value,
                    self._consecutive_failures,
                )
            raise

        async with self._lock:
            self._record_success(current_state)

        return result

    # --------------------------------------------------------
    # 상태 전이 내부 메서드
    # --------------------------------------------------------

    def _maybe_transition_to_half_open(self) -> None:
        """OPEN 상태에서 30분 경과 시 HALF_OPEN 으로 전이.

        _lock 보유 중에 호출해야 한다.
        """
        if self._state == CBState.OPEN and self._opened_at is not None:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.open_duration_s:
                self._state = CBState.HALF_OPEN
                logger.info(
                    "CircuitBreaker HALF_OPEN for %s (elapsed=%.0fs)",
                    self.endpoint_id,
                    elapsed,
                )

    def _record_success(self, prev_state: CBState) -> None:
        """성공 기록. HALF_OPEN 이었으면 CLOSED 로 전이.

        _lock 보유 중에 호출해야 한다.
        """
        now = time.monotonic()
        self._purge_old_records(now)
        self._call_timestamps.append(now)
        self._consecutive_failures = 0

        if prev_state == CBState.HALF_OPEN:
            self._state = CBState.CLOSED
            self._opened_at = None
            logger.info(
                "CircuitBreaker CLOSED for %s (recovered from HALF_OPEN)",
                self.endpoint_id,
            )

    def _record_failure(self) -> None:
        """실패 기록. 임계 초과 시 OPEN 으로 전이.

        _lock 보유 중에 호출해야 한다.
        """
        now = time.monotonic()
        self._purge_old_records(now)
        self._call_timestamps.append(now)
        self._failure_timestamps.append(now)
        self._consecutive_failures += 1

        if self._state == CBState.HALF_OPEN:
            # HALF_OPEN 실패 → OPEN 유지 (타이머 리셋)
            self._state = CBState.OPEN
            self._opened_at = now
            self._consecutive_failures = 0
            logger.warning(
                "CircuitBreaker back to OPEN for %s (HALF_OPEN test failed)",
                self.endpoint_id,
            )
            return

        if self._should_open():
            self._state = CBState.OPEN
            self._opened_at = now
            logger.error(
                "CircuitBreaker OPEN for %s "
                "(consecutive=%d, failure_rate=%.2f)",
                self.endpoint_id,
                self._consecutive_failures,
                self._current_failure_rate(),
            )

    def _should_open(self) -> bool:
        """CLOSED 상태에서 OPEN 전이 조건 판단."""
        if self._consecutive_failures >= self.consecutive_fail_threshold:
            return True
        if self._current_failure_rate() > self.failure_rate_threshold:
            return True
        return False

    def _current_failure_rate(self) -> float:
        """슬라이딩 윈도우 내 실패율(0~1) 반환."""
        total = len(self._call_timestamps)
        if total < self.min_calls_for_rate:
            return 0.0
        failures = len(self._failure_timestamps)
        return failures / total

    def _purge_old_records(self, now: float) -> None:
        """슬라이딩 윈도우 바깥 기록 제거."""
        cutoff = now - self.failure_window_s
        while self._call_timestamps and self._call_timestamps[0] < cutoff:
            self._call_timestamps.popleft()
        while self._failure_timestamps and self._failure_timestamps[0] < cutoff:
            self._failure_timestamps.popleft()

    def _reopen_at_datetime(self) -> Optional[datetime]:
        """OPEN 상태에서 HALF_OPEN 진입 예정 datetime(UTC) 반환."""
        if self._opened_at is None:
            return None
        now_mono = time.monotonic()
        now_wall = datetime.now(tz=timezone.utc)
        delta_s = self.open_duration_s - (now_mono - self._opened_at)
        if delta_s < 0:
            delta_s = 0.0
        return now_wall + timedelta(seconds=delta_s)

    # --------------------------------------------------------
    # 테스트 지원 (상태 강제 설정)
    # --------------------------------------------------------

    def _force_state(
        self,
        state: CBState,
        *,
        consecutive_failures: int = 0,
        opened_at: Optional[float] = None,
    ) -> None:
        """테스트 전용 — 상태를 강제로 지정한다."""
        self._state = state
        self._consecutive_failures = consecutive_failures
        self._opened_at = opened_at


# ============================================================
# 팩토리 (엔드포인트별 싱글턴)
# ============================================================

_registry: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(endpoint_id: str) -> CircuitBreaker:
    """endpoint_id 별 CircuitBreaker 싱글턴을 반환한다.

    같은 endpoint_id 에 대해 항상 동일 인스턴스를 반환한다.
    인스턴스가 없으면 기본 설정으로 새로 생성한다.

    Args:
        endpoint_id: data.go.kr 엔드포인트 식별자 (예: "15111777").

    Returns:
        해당 엔드포인트의 CircuitBreaker 인스턴스.
    """
    if endpoint_id not in _registry:
        _registry[endpoint_id] = CircuitBreaker(endpoint_id=endpoint_id)
    return _registry[endpoint_id]


def reset_all_breakers() -> None:
    """테스트 전용 — 모든 Circuit Breaker 등록을 초기화한다."""
    _registry.clear()


__all__ = [
    "CBState",
    "CircuitBreaker",
    "CircuitBreakerLike",
    "NoOpBreaker",
    "get_circuit_breaker",
    "reset_all_breakers",
]
