"""error_handler.py 단위 테스트.

FastAPI TestClient 로 각 에러 → HTTP 매핑을 검증한다.

커버리지:
    - F0NotCompletedError / F0NotApprovedError / NoIngredientsError
      / FoodTypeMissingError → 400
    - ConfigError → 500
    - DataGoKrError(transient=True) → 503 + retry_after_s
    - DataGoKrError(transient=False) → 200 + status="needs_review"
    - DataGoKrRateLimitError(transient=False) → 200 + status="needs_review"
    - CircuitBreakerOpenError → 503
    - add_escalation() 누적 유틸
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from exceptions import (
    F0NotCompletedError,
    F0NotApprovedError,
    NoIngredientsError,
    FoodTypeMissingError,
    ConfigError,
    DataGoKrError,
    DataGoKrRateLimitError,
    CircuitBreakerOpenError,
)
from middleware.error_handler import register_error_handlers, add_escalation


# ============================================================
# 테스트 앱 픽스처
# ============================================================


def _make_app() -> FastAPI:
    """각 에러를 raise 하는 엔드포인트를 포함한 테스트 앱."""
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/raise/f0-not-completed/{case_id}")
    async def raise_f0_not_completed(case_id: str):
        raise F0NotCompletedError("F0 단계가 완료되지 않았습니다.")

    @app.get("/raise/f0-not-approved/{case_id}")
    async def raise_f0_not_approved(case_id: str):
        raise F0NotApprovedError("F0 승인이 필요합니다.")

    @app.get("/raise/no-ingredients/{case_id}")
    async def raise_no_ingredients(case_id: str):
        raise NoIngredientsError("원재료 목록이 비어 있습니다.")

    @app.get("/raise/food-type-missing/{case_id}")
    async def raise_food_type_missing(case_id: str):
        raise FoodTypeMissingError("식품유형 정보가 없습니다.")

    @app.get("/raise/config-error")
    async def raise_config_error():
        raise ConfigError("API 키가 설정되지 않았습니다.")

    @app.get("/raise/data-go-kr-transient")
    async def raise_data_go_kr_transient():
        raise DataGoKrError(
            "일시적 장애",
            endpoint="15111777",
            status_code=500,
        )

    @app.get("/raise/data-go-kr-non-transient")
    async def raise_data_go_kr_non_transient():
        raise DataGoKrRateLimitError(
            "일일 한도 초과",
            endpoint="15111777",
            retry_after=3600,
        )

    @app.get("/raise/circuit-breaker")
    async def raise_circuit_breaker():
        raise CircuitBreakerOpenError(
            "차단 중",
            endpoint="15111777",
        )

    return app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(_make_app(), raise_server_exceptions=False)


# ============================================================
# ① 차단성 에러 → 400
# ============================================================


class TestBlockingErrors400:
    def test_f0_not_completed_returns_400(self, client: TestClient):
        resp = client.get("/raise/f0-not-completed/case-001")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"] == "F0_NOT_COMPLETED"
        assert body["feature"] == 1

    def test_f0_not_approved_returns_400(self, client: TestClient):
        resp = client.get("/raise/f0-not-approved/case-001")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"] == "F0_NOT_APPROVED"
        assert body["feature"] == 1

    def test_no_ingredients_returns_400(self, client: TestClient):
        resp = client.get("/raise/no-ingredients/case-001")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"] == "NO_INGREDIENTS"
        assert body["feature"] == 1

    def test_food_type_missing_returns_400(self, client: TestClient):
        resp = client.get("/raise/food-type-missing/case-001")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"] == "FOOD_TYPE_MISSING"
        assert body["feature"] == 1


# ============================================================
# ConfigError → 500
# ============================================================


class TestConfigError500:
    def test_config_error_returns_500(self, client: TestClient):
        resp = client.get("/raise/config-error")
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"] == "CONFIG_ERROR"


# ============================================================
# ② 복구 가능 에러 — transient=True → 503
# ============================================================


class TestDataGoKrTransient503:
    def test_transient_error_returns_503(self, client: TestClient):
        resp = client.get("/raise/data-go-kr-transient")
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"] == "DATA_GO_KR_ERROR"
        assert "retry_after_s" in body
        assert isinstance(body["retry_after_s"], int)


# ============================================================
# ② 복구 가능 에러 — transient=False → 200 + needs_review
# ============================================================


class TestDataGoKrNonTransient200:
    def test_non_transient_error_returns_200_needs_review(self, client: TestClient):
        resp = client.get("/raise/data-go-kr-non-transient")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "needs_review"
        assert body["error"] == "DATA_GO_KR_RATE_LIMIT"


# ============================================================
# CircuitBreakerOpenError → 503
# ============================================================


class TestCircuitBreaker503:
    def test_circuit_breaker_returns_503(self, client: TestClient):
        resp = client.get("/raise/circuit-breaker")
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"] == "CIRCUIT_BREAKER_OPEN"


# ============================================================
# add_escalation() 유틸
# ============================================================


class TestAddEscalation:
    def test_adds_reason(self):
        esc: list[str] = []
        add_escalation(esc, "ingredient_unidentified")
        assert esc == ["ingredient_unidentified"]

    def test_dedup_true_skips_duplicate(self):
        esc = ["ingredient_unidentified"]
        add_escalation(esc, "ingredient_unidentified", dedup=True)
        assert esc == ["ingredient_unidentified"]

    def test_dedup_false_allows_duplicate(self):
        esc = ["ingredient_unidentified"]
        add_escalation(esc, "ingredient_unidentified", dedup=False)
        assert esc == ["ingredient_unidentified", "ingredient_unidentified"]

    def test_multiple_different_reasons(self):
        esc: list[str] = []
        add_escalation(esc, "ingredient_unidentified")
        add_escalation(esc, "spec_value_non_numeric")
        add_escalation(esc, "unit_normalization_failed")
        assert len(esc) == 3
        assert "spec_value_non_numeric" in esc
