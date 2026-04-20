"""Circuit Breaker 단위 테스트.

상태 전이 전수 커버리지:
    - CLOSED → 20회 연속 실패 → OPEN 전이
    - OPEN → 30분 대기 (time.monotonic mock) → HALF_OPEN 전이
    - HALF_OPEN → 성공 → CLOSED 전이
    - HALF_OPEN → 실패 → OPEN 유지 (타이머 리셋)
    - OPEN 상태에서 call() → CircuitBreakerOpenError raise
    - get_circuit_breaker() 싱글턴 확인
    - reset_all_breakers() 초기화 확인
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch, AsyncMock

import pytest

from exceptions import CircuitBreakerOpenError
from services.data_go_kr.circuit_breaker import (
    CBState,
    CircuitBreaker,
    get_circuit_breaker,
    reset_all_breakers,
)


# ============================================================
# 픽스처
# ============================================================


@pytest.fixture(autouse=True)
def clean_registry():
    """각 테스트 전후 싱글턴 레지스트리 초기화."""
    reset_all_breakers()
    yield
    reset_all_breakers()


@pytest.fixture
def breaker() -> CircuitBreaker:
    """테스트용 CircuitBreaker.

    연속 실패 임계(20회)만으로 OPEN을 제어한다.
    실패율 임계는 비활성화(1.0 = 도달 불가)하여 테스트 격리.
    """
    return CircuitBreaker(
        endpoint_id="TEST_EP",
        failure_window_s=300.0,
        consecutive_fail_threshold=20,
        failure_rate_threshold=1.0,   # 실패율 임계 비활성화 (연속 실패만 사용)
        open_duration_s=1800.0,
        min_calls_for_rate=5,
    )


async def _success_coro():
    return "ok"


async def _failure_coro():
    raise RuntimeError("simulated failure")


# ============================================================
# CLOSED 상태 기본 동작
# ============================================================


class TestClosedState:
    @pytest.mark.asyncio
    async def test_initial_state_is_closed(self, breaker: CircuitBreaker):
        assert breaker.state == CBState.CLOSED

    @pytest.mark.asyncio
    async def test_success_stays_closed(self, breaker: CircuitBreaker):
        result = await breaker.call("TEST_EP", _success_coro())
        assert result == "ok"
        assert breaker.state == CBState.CLOSED

    @pytest.mark.asyncio
    async def test_failure_coro_re_raises(self, breaker: CircuitBreaker):
        with pytest.raises(RuntimeError, match="simulated failure"):
            await breaker.call("TEST_EP", _failure_coro())

    @pytest.mark.asyncio
    async def test_single_failure_stays_closed(self, breaker: CircuitBreaker):
        with pytest.raises(RuntimeError):
            await breaker.call("TEST_EP", _failure_coro())
        assert breaker.state == CBState.CLOSED


# ============================================================
# CLOSED → OPEN: 20회 연속 실패
# ============================================================


class TestClosedToOpen:
    @pytest.mark.asyncio
    async def test_20_consecutive_failures_open(self, breaker: CircuitBreaker):
        """정확히 20회 연속 실패 시 OPEN으로 전이."""
        for i in range(19):
            with pytest.raises(RuntimeError):
                await breaker.call("TEST_EP", _failure_coro())
            assert breaker.state == CBState.CLOSED, f"Should stay CLOSED after {i+1} failures"

        # 20번째 실패에서 OPEN 전이
        with pytest.raises(RuntimeError):
            await breaker.call("TEST_EP", _failure_coro())
        assert breaker.state == CBState.OPEN

    @pytest.mark.asyncio
    async def test_open_sets_opened_at(self, breaker: CircuitBreaker):
        """OPEN 전이 시 _opened_at 이 기록된다."""
        for _ in range(20):
            with pytest.raises(RuntimeError):
                await breaker.call("TEST_EP", _failure_coro())
        assert breaker._opened_at is not None

    @pytest.mark.asyncio
    async def test_consecutive_reset_after_success(self, breaker: CircuitBreaker):
        """성공 후 연속 실패 카운터가 0으로 리셋된다."""
        for _ in range(5):
            with pytest.raises(RuntimeError):
                await breaker.call("TEST_EP", _failure_coro())
        await breaker.call("TEST_EP", _success_coro())
        assert breaker._consecutive_failures == 0
        assert breaker.state == CBState.CLOSED


# ============================================================
# OPEN 상태 — call() 즉시 차단
# ============================================================


class TestOpenState:
    @pytest.mark.asyncio
    async def test_open_raises_circuit_breaker_error(self, breaker: CircuitBreaker):
        """OPEN 상태에서 call() 은 CircuitBreakerOpenError 를 raise.

        call() 내부에서 coroutine 을 close() 하므로 ResourceWarning 없음.
        """
        breaker._force_state(CBState.OPEN, opened_at=time.monotonic())
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            await breaker.call("TEST_EP", _success_coro())
        assert exc_info.value.endpoint == "TEST_EP"
        assert exc_info.value.code == "CIRCUIT_BREAKER_OPEN"

    @pytest.mark.asyncio
    async def test_open_consecutive_calls_all_blocked(self, breaker: CircuitBreaker):
        """OPEN 상태에서 연속 호출 모두 CircuitBreakerOpenError 를 raise 한다."""
        breaker._force_state(CBState.OPEN, opened_at=time.monotonic())

        for _ in range(3):
            with pytest.raises(CircuitBreakerOpenError):
                await breaker.call("TEST_EP", _success_coro())

        # 상태는 여전히 OPEN (30분 미경과)
        assert breaker.state == CBState.OPEN

    @pytest.mark.asyncio
    async def test_open_includes_reopen_at(self, breaker: CircuitBreaker):
        """CircuitBreakerOpenError 에 reopen_at 필드가 포함된다."""
        breaker._force_state(CBState.OPEN, opened_at=time.monotonic())
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            await breaker.call("TEST_EP", _success_coro())  # call() 내부에서 close() 처리
        assert exc_info.value.reopen_at is not None


# ============================================================
# OPEN → HALF_OPEN: 30분 경과 (time mock)
# ============================================================


class TestOpenToHalfOpen:
    @pytest.mark.asyncio
    async def test_30_minutes_elapsed_transitions_to_half_open(self, breaker: CircuitBreaker):
        """OPEN 상태에서 30분 경과 시 HALF_OPEN으로 전이."""
        opened_at = 0.0
        breaker._force_state(CBState.OPEN, opened_at=opened_at)

        elapsed = breaker.open_duration_s + 1.0
        with patch("services.data_go_kr.circuit_breaker.time") as mock_time:
            mock_time.monotonic.return_value = opened_at + elapsed
            breaker._maybe_transition_to_half_open()

        assert breaker.state == CBState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_29_minutes_stays_open(self, breaker: CircuitBreaker):
        """29분 경과 시에는 OPEN 유지."""
        opened_at = time.monotonic()
        breaker._force_state(CBState.OPEN, opened_at=opened_at)

        elapsed = breaker.open_duration_s - 60.0  # 30분 - 1분
        with patch("services.data_go_kr.circuit_breaker.time") as mock_time:
            mock_time.monotonic.return_value = opened_at + elapsed
            breaker._maybe_transition_to_half_open()

        assert breaker.state == CBState.OPEN

    @pytest.mark.asyncio
    async def test_open_call_after_30_min_transitions_to_half_open_then_tests(
        self, breaker: CircuitBreaker
    ):
        """call() 호출 시 30분 경과 체크 후 HALF_OPEN 상태로 coro 실행."""
        opened_at = 0.0
        breaker._force_state(CBState.OPEN, opened_at=opened_at)

        with patch("services.data_go_kr.circuit_breaker.time") as mock_time:
            mock_time.monotonic.return_value = opened_at + breaker.open_duration_s + 1.0
            # HALF_OPEN 진입 후 성공 → CLOSED
            result = await breaker.call("TEST_EP", _success_coro())

        assert result == "ok"
        assert breaker.state == CBState.CLOSED


# ============================================================
# HALF_OPEN → CLOSED: 성공
# ============================================================


class TestHalfOpenToClosedOnSuccess:
    @pytest.mark.asyncio
    async def test_success_in_half_open_closes(self, breaker: CircuitBreaker):
        """HALF_OPEN 에서 성공 시 CLOSED 전이."""
        breaker._force_state(CBState.HALF_OPEN)
        result = await breaker.call("TEST_EP", _success_coro())
        assert result == "ok"
        assert breaker.state == CBState.CLOSED

    @pytest.mark.asyncio
    async def test_closed_after_half_open_clears_opened_at(self, breaker: CircuitBreaker):
        """HALF_OPEN → CLOSED 전이 시 _opened_at 이 None 으로 초기화된다."""
        breaker._force_state(
            CBState.HALF_OPEN,
            opened_at=time.monotonic() - breaker.open_duration_s - 1,
        )
        await breaker.call("TEST_EP", _success_coro())
        assert breaker._opened_at is None


# ============================================================
# HALF_OPEN → OPEN 유지: 실패
# ============================================================


class TestHalfOpenToOpenOnFailure:
    @pytest.mark.asyncio
    async def test_failure_in_half_open_reopens(self, breaker: CircuitBreaker):
        """HALF_OPEN 에서 실패 시 OPEN 유지 (타이머 리셋)."""
        old_opened_at = time.monotonic() - breaker.open_duration_s - 5
        breaker._force_state(CBState.HALF_OPEN, opened_at=old_opened_at)

        with pytest.raises(RuntimeError):
            await breaker.call("TEST_EP", _failure_coro())

        assert breaker.state == CBState.OPEN
        # 타이머가 리셋되어 _opened_at 이 갱신되어야 한다
        assert breaker._opened_at is not None
        assert breaker._opened_at > old_opened_at

    @pytest.mark.asyncio
    async def test_half_open_failure_resets_consecutive_count(self, breaker: CircuitBreaker):
        """HALF_OPEN → OPEN 재진입 시 연속 실패 카운터가 0 으로 리셋된다."""
        breaker._force_state(CBState.HALF_OPEN)
        with pytest.raises(RuntimeError):
            await breaker.call("TEST_EP", _failure_coro())
        # OPEN 재진입 시 consecutive_failures 리셋 확인
        assert breaker._consecutive_failures == 0


# ============================================================
# 팩토리 — get_circuit_breaker(), reset_all_breakers()
# ============================================================


class TestFactory:
    def test_get_returns_same_instance(self):
        cb1 = get_circuit_breaker("15111777")
        cb2 = get_circuit_breaker("15111777")
        assert cb1 is cb2

    def test_different_endpoints_different_instances(self):
        cb_a = get_circuit_breaker("15111777")
        cb_b = get_circuit_breaker("15094202")
        assert cb_a is not cb_b

    def test_reset_all_clears_registry(self):
        get_circuit_breaker("15111777")
        reset_all_breakers()
        cb_new = get_circuit_breaker("15111777")
        # 새 인스턴스여야 한다 (다른 id 가 아닌 CLOSED 초기 상태 확인)
        assert cb_new.state == CBState.CLOSED

    def test_endpoint_id_stored(self):
        cb = get_circuit_breaker("15116583")
        assert cb.endpoint_id == "15116583"


# ============================================================
# 실패율 임계 → OPEN (80%)
# ============================================================


class TestFailureRateThreshold:
    @pytest.mark.asyncio
    async def test_high_failure_rate_opens_breaker(self):
        """실패율 > 80% 에서 OPEN 전이 (연속 20회 미만이더라도).

        성공 5 + 실패 21 = 총 26 → 실패율 21/26 ≈ 0.808 > 0.80 → OPEN.
        consecutive_fail_threshold=100 으로 높여 연속 실패 경로를 비활성화.
        """
        breaker = CircuitBreaker(
            endpoint_id="RATE_TEST",
            consecutive_fail_threshold=100,  # 연속 실패 임계 비활성화
            failure_rate_threshold=0.80,
            min_calls_for_rate=5,
            failure_window_s=300.0,
            open_duration_s=1800.0,
        )

        # 성공 5회 — 실패율 계산 분모 확보 (min_calls_for_rate=5 충족)
        for _ in range(5):
            await breaker.call("RATE_TEST", _success_coro())

        # 실패 21회 → 누적 26회 중 21회 실패 = 80.77% > 80% → OPEN
        # (정확히 80%인 20회 실패 = 20/25=0.80 은 초과 아님 — >, not >=)
        for _ in range(21):
            if breaker.state == CBState.OPEN:
                break
            with pytest.raises(RuntimeError):
                await breaker.call("RATE_TEST", _failure_coro())

        assert breaker.state == CBState.OPEN
