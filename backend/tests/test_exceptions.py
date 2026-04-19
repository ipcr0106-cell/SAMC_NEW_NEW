"""exceptions.py 단위 테스트.

커버리지:
    - 각 Exception 인스턴스화 + code / transient 속성 검증
    - Day 0 스켈레톤 시그니처 유지 증빙
      (DataGoKrError 생성자 kwargs = {endpoint, status_code})
    - W1-C 추가 차단성 에러 5개 검증
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from exceptions import (
    F1PipelineError,
    DataGoKrError,
    DataGoKrTimeoutError,
    DataGoKrRateLimitError,
    DataGoKrInvalidResponseError,
    CircuitBreakerOpenError,
    F0NotCompletedError,
    F0NotApprovedError,
    NoIngredientsError,
    FoodTypeMissingError,
    ConfigError,
)


# ============================================================
# Day 0 스켈레톤 — 시그니처 유지 증빙
# ============================================================


class TestDay0SkeletonSignatures:
    """Day 0에 동결된 클래스들의 생성자 kwarg 검증."""

    def test_f1_pipeline_error_base(self):
        exc = F1PipelineError("base error")
        assert exc.code == "F1_PIPELINE_ERROR"
        assert exc.transient is False

    def test_data_go_kr_error_kwargs(self):
        """DataGoKrError 생성자 kwargs = {endpoint, status_code} — Day 0 동결."""
        exc = DataGoKrError(
            "API failed",
            endpoint="15111777",
            status_code=500,
        )
        assert exc.endpoint == "15111777"
        assert exc.status_code == 500
        assert exc.code == "DATA_GO_KR_ERROR"
        assert exc.transient is True

    def test_data_go_kr_error_status_code_optional(self):
        """status_code 는 Optional — None 허용."""
        exc = DataGoKrError("timeout", endpoint="15094202")
        assert exc.status_code is None

    def test_data_go_kr_timeout_error(self):
        exc = DataGoKrTimeoutError(
            "timed out",
            endpoint="15111777",
            timeout_s=30.0,
        )
        assert exc.code == "DATA_GO_KR_TIMEOUT"
        assert exc.transient is True
        assert exc.endpoint == "15111777"
        assert exc.timeout_s == 30.0
        assert exc.status_code is None  # TimeoutError는 항상 None

    def test_data_go_kr_rate_limit_error(self):
        exc = DataGoKrRateLimitError(
            "rate limit exceeded",
            endpoint="15116583",
            retry_after=3600,
        )
        assert exc.code == "DATA_GO_KR_RATE_LIMIT"
        assert exc.transient is False  # 일일 한도는 즉시 복구 불가
        assert exc.endpoint == "15116583"
        assert exc.status_code == 429
        assert exc.retry_after == 3600

    def test_data_go_kr_rate_limit_retry_after_optional(self):
        exc = DataGoKrRateLimitError("limit", endpoint="15111913")
        assert exc.retry_after is None

    def test_data_go_kr_invalid_response_error(self):
        exc = DataGoKrInvalidResponseError(
            "invalid response",
            endpoint="15111777",
            result_code="99",
            status_code=200,
        )
        assert exc.code == "DATA_GO_KR_INVALID_RESPONSE"
        assert exc.transient is False
        assert exc.result_code == "99"
        assert exc.status_code == 200

    def test_circuit_breaker_open_error(self):
        reopen_at = datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)
        exc = CircuitBreakerOpenError(
            "breaker open",
            endpoint="15111777",
            reopen_at=reopen_at,
        )
        assert exc.code == "CIRCUIT_BREAKER_OPEN"
        assert exc.transient is True
        assert exc.endpoint == "15111777"
        assert exc.reopen_at == reopen_at

    def test_circuit_breaker_open_error_reopen_at_optional(self):
        exc = CircuitBreakerOpenError("open", endpoint="15111777")
        assert exc.reopen_at is None


# ============================================================
# Day 0 계층 구조 검증
# ============================================================


class TestDay0Hierarchy:
    """Day 0 클래스들의 상속 관계 검증."""

    def test_data_go_kr_error_is_f1_pipeline_error(self):
        exc = DataGoKrError("err", endpoint="X")
        assert isinstance(exc, F1PipelineError)

    def test_timeout_is_data_go_kr_error(self):
        exc = DataGoKrTimeoutError("t", endpoint="X", timeout_s=5.0)
        assert isinstance(exc, DataGoKrError)
        assert isinstance(exc, F1PipelineError)

    def test_rate_limit_is_data_go_kr_error(self):
        exc = DataGoKrRateLimitError("r", endpoint="X")
        assert isinstance(exc, DataGoKrError)

    def test_invalid_response_is_data_go_kr_error(self):
        exc = DataGoKrInvalidResponseError("i", endpoint="X")
        assert isinstance(exc, DataGoKrError)

    def test_circuit_breaker_is_f1_pipeline_error(self):
        exc = CircuitBreakerOpenError("c", endpoint="X")
        assert isinstance(exc, F1PipelineError)


# ============================================================
# W1-C 추가: 차단성 에러 5개
# ============================================================


class TestBlockingErrors:
    """W1-C 추가 차단성 에러 검증."""

    def test_f0_not_completed_error(self):
        exc = F0NotCompletedError("F0 not done")
        assert exc.code == "F0_NOT_COMPLETED"
        assert exc.transient is False
        assert isinstance(exc, F1PipelineError)
        assert str(exc) == "F0 not done"

    def test_f0_not_approved_error(self):
        exc = F0NotApprovedError("F0 not approved")
        assert exc.code == "F0_NOT_APPROVED"
        assert exc.transient is False
        assert isinstance(exc, F1PipelineError)

    def test_no_ingredients_error(self):
        exc = NoIngredientsError("no ingredients")
        assert exc.code == "NO_INGREDIENTS"
        assert exc.transient is False
        assert isinstance(exc, F1PipelineError)

    def test_food_type_missing_error(self):
        exc = FoodTypeMissingError("food type missing")
        assert exc.code == "FOOD_TYPE_MISSING"
        assert exc.transient is False
        assert isinstance(exc, F1PipelineError)

    def test_config_error(self):
        exc = ConfigError("missing API key")
        assert exc.code == "CONFIG_ERROR"
        assert exc.transient is False
        assert isinstance(exc, F1PipelineError)

    def test_blocking_errors_are_not_transient(self):
        """차단성 에러는 모두 transient=False 여야 한다."""
        blocking = [
            F0NotCompletedError("x"),
            F0NotApprovedError("x"),
            NoIngredientsError("x"),
            FoodTypeMissingError("x"),
            ConfigError("x"),
        ]
        for exc in blocking:
            assert exc.transient is False, f"{type(exc).__name__} should be transient=False"

    def test_blocking_errors_catchable_as_f1_pipeline_error(self):
        """차단성 에러는 F1PipelineError 로 일괄 캐치 가능해야 한다."""
        for exc_cls in (F0NotCompletedError, F0NotApprovedError, NoIngredientsError, FoodTypeMissingError, ConfigError):
            with pytest.raises(F1PipelineError):
                raise exc_cls("test")
