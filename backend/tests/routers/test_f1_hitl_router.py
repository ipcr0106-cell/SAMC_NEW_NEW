"""W3-BE: F1 HITL 라우터 통합 테스트 (FastAPI TestClient).

커버리지 목표: 85%+

테스트 시나리오 (05번 §9 전수 HTTP 매핑):
    1. PATCH /feature/0 정상 → 200 + F0EditResponse
    2. PATCH /feature/0 locked 상태 → 403
    3. PATCH /feature/0 스텝 없음 → 404
    4. POST /feature/0/approve 정상 → 200 + F0ApproveResponse
    5. POST /feature/0/approve 상태 불일치 → 400
    6. POST /feature/0/approve 스텝 없음 → 404
    7. POST /feature/1/hitl1-decisions 전체 ack → 200 + waiting_review
    8. POST /feature/1/hitl1-decisions 일부 ack → 200 + needs_review
    9. POST /feature/1/hitl1-decisions 스텝 없음 → 404
    10. POST /feature/1/confirm waiting_review → 200 + confirmed
    11. POST /feature/1/confirm 미해결 에스컬레이션 → 400
    12. POST /feature/1/confirm 잘못된 상태 → 400
    13. POST /feature/1/confirm 스텝 없음 → 404
    14. POST /feature/1/run F1_REQUIRE_HITL0_APPROVAL=true + status!=approved → 400 F0_NOT_APPROVED
    15. POST /feature/1/run F1_REQUIRE_HITL0_APPROVAL=false → 게이트 통과 (기존 동작)

실행:
    cd backend
    pytest tests/routers/test_f1_hitl_router.py -v --cov=routers.feature1
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "f1_hitl"


def load_fixture(filename: str) -> dict:
    with open(FIXTURES_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# 앱 + TestClient 설정
# ============================================================


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient — Supabase 연결 없이 동작하도록 환경변수 설정."""
    import os
    os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
    os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")

    from main import app
    return TestClient(app)


# ============================================================
# Mock 헬퍼
# ============================================================


def _make_service_response(data: dict) -> MagicMock:
    """서비스 함수가 반환할 Pydantic 모델 mock."""
    mock = MagicMock()
    mock.model_dump.return_value = data
    # dict 변환 지원
    for k, v in data.items():
        setattr(mock, k, v)
    return mock


# ============================================================
# PATCH /api/v1/cases/{case_id}/pipeline/feature/0
# ============================================================


class TestF0EditEndpoint:
    """HITL-0 편집 엔드포인트 테스트."""

    BASE = "/api/v1/cases/{case_id}/pipeline/feature/0"

    def test_정상_편집_200(self, client: TestClient) -> None:
        """정상 편집 → 200 + F0EditResponse."""
        from models.f1_hitl import F0EditResponse

        case_id = "00000000-0000-0000-0000-000000000001"
        mock_resp = F0EditResponse(
            case_id=case_id,
            status="completed",
            updated_at=datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc),
            audit_log_id=1,
        )

        with patch("routers.feature1.apply_f0_edit", return_value=mock_resp):
            response = client.patch(
                self.BASE.format(case_id=case_id),
                json={
                    "final_result": {"basic_info": {"product_name": "수정제품"}},
                    "edit_reason": "원재료 수정",
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "completed"
        assert body["audit_log_id"] == 1

    def test_locked_상태_403(self, client: TestClient) -> None:
        """locked 상태에서 편집 시 403."""
        case_id = "00000000-0000-0000-0000-000000000001"

        with patch(
            "routers.feature1.apply_f0_edit",
            side_effect=PermissionError("status='locked' 상태에서는 편집할 수 없습니다."),
        ):
            response = client.patch(
                self.BASE.format(case_id=case_id),
                json={"final_result": {}, "edit_reason": "강제 편집"},
            )

        assert response.status_code == 403
        assert response.json()["detail"]["error"] == "F0_LOCKED"

    def test_스텝_없음_404(self, client: TestClient) -> None:
        """F0 스텝 없으면 404."""
        case_id = "nonexistent-case"

        with patch(
            "routers.feature1.apply_f0_edit",
            side_effect=ValueError("F0 파이프라인 스텝이 존재하지 않습니다."),
        ):
            response = client.patch(
                self.BASE.format(case_id=case_id),
                json={"final_result": {}, "edit_reason": "없는 케이스"},
            )

        assert response.status_code == 404
        assert response.json()["detail"]["error"] == "F0_STEP_NOT_FOUND"

    def test_edit_reason_필수(self, client: TestClient) -> None:
        """edit_reason 누락 시 422 Unprocessable Entity."""
        case_id = "00000000-0000-0000-0000-000000000001"
        response = client.patch(
            self.BASE.format(case_id=case_id),
            json={"final_result": {}},  # edit_reason 없음
        )
        assert response.status_code == 422


# ============================================================
# POST /api/v1/cases/{case_id}/pipeline/feature/0/approve
# ============================================================


class TestF0ApproveEndpoint:
    """HITL-0 승인 엔드포인트 테스트."""

    BASE = "/api/v1/cases/{case_id}/pipeline/feature/0/approve"

    def test_정상_승인_200(self, client: TestClient) -> None:
        """정상 승인 → 200 + F0ApproveResponse."""
        from models.f1_hitl import F0ApproveResponse

        case_id = "00000000-0000-0000-0000-000000000001"
        approved_at = datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)
        mock_resp = F0ApproveResponse(
            case_id=case_id,
            status="approved",
            approved_at=approved_at,
            audit_log_id=5,
        )

        with patch("routers.feature1.approve_f0", return_value=mock_resp):
            response = client.post(
                self.BASE.format(case_id=case_id),
                json={
                    "approver_id": "user-001",
                    "approved_at": approved_at.isoformat(),
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "approved"
        assert body["audit_log_id"] == 5

    def test_상태_불일치_400(self, client: TestClient) -> None:
        """잘못된 상태에서 승인 시 400."""
        case_id = "00000000-0000-0000-0000-000000000002"

        with patch(
            "routers.feature1.approve_f0",
            side_effect=ValueError("F0 승인은 status='completed' 상태에서만 가능합니다."),
        ):
            response = client.post(
                self.BASE.format(case_id=case_id),
                json={
                    "approver_id": "user-001",
                    "approved_at": "2026-04-20T12:00:00+00:00",
                },
            )

        assert response.status_code == 400
        assert response.json()["detail"]["error"] == "F0_APPROVE_FAILED"

    def test_스텝_없음_404(self, client: TestClient) -> None:
        """F0 스텝 없으면 404."""
        case_id = "nonexistent"

        with patch(
            "routers.feature1.approve_f0",
            side_effect=ValueError("F0 파이프라인 스텝이 존재하지 않습니다."),
        ):
            response = client.post(
                self.BASE.format(case_id=case_id),
                json={
                    "approver_id": "user-001",
                    "approved_at": "2026-04-20T12:00:00+00:00",
                },
            )

        assert response.status_code == 404

    def test_approver_id_필수(self, client: TestClient) -> None:
        """approver_id 누락 시 422."""
        case_id = "00000000-0000-0000-0000-000000000001"
        response = client.post(
            self.BASE.format(case_id=case_id),
            json={"approved_at": "2026-04-20T12:00:00+00:00"},
        )
        assert response.status_code == 422


# ============================================================
# POST /api/v1/cases/{case_id}/pipeline/feature/1/hitl1-decisions
# ============================================================


class TestHitl1DecisionsEndpoint:
    """HITL-1 결정 엔드포인트 테스트."""

    BASE = "/api/v1/cases/{case_id}/pipeline/feature/1/hitl1-decisions"

    def test_전체_ack_waiting_review_200(self, client: TestClient) -> None:
        """모든 에스컬레이션 ack → 200 + waiting_review."""
        from models.f1_hitl import HITL1DecisionsResponse

        case_id = "00000000-0000-0000-0000-000000000003"
        mock_resp = HITL1DecisionsResponse(
            case_id=case_id,
            status="waiting_review",
            unresolved_escalations=[],
            audit_log_id=20,
        )

        with patch("routers.feature1.submit_hitl1_decisions", return_value=mock_resp):
            response = client.post(
                self.BASE.format(case_id=case_id),
                json={
                    "ingredient_decisions": [],
                    "conditional_resolutions": [],
                    "qualitative_resolutions": [],
                    "escalation_acknowledgements": ["api_failure"],
                    "reviewer_id": "reviewer-001",
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "waiting_review"
        assert body["unresolved_escalations"] == []

    def test_일부_ack_needs_review_200(self, client: TestClient) -> None:
        """일부 ack → 200 + needs_review + unresolved 반환."""
        from models.f1_hitl import HITL1DecisionsResponse

        case_id = "00000000-0000-0000-0000-000000000004"
        mock_resp = HITL1DecisionsResponse(
            case_id=case_id,
            status="needs_review",
            unresolved_escalations=["unidentified"],
            audit_log_id=21,
        )

        with patch("routers.feature1.submit_hitl1_decisions", return_value=mock_resp):
            response = client.post(
                self.BASE.format(case_id=case_id),
                json={
                    "ingredient_decisions": [],
                    "escalation_acknowledgements": ["api_failure"],
                    "reviewer_id": "reviewer-002",
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "needs_review"
        assert "unidentified" in body["unresolved_escalations"]

    def test_스텝_없음_404(self, client: TestClient) -> None:
        """F1 스텝 없으면 404."""
        case_id = "nonexistent"

        with patch(
            "routers.feature1.submit_hitl1_decisions",
            side_effect=ValueError("F1 파이프라인 스텝이 존재하지 않습니다."),
        ):
            response = client.post(
                self.BASE.format(case_id=case_id),
                json={
                    "ingredient_decisions": [],
                    "escalation_acknowledgements": [],
                    "reviewer_id": "r1",
                },
            )

        assert response.status_code == 404
        assert response.json()["detail"]["error"] == "F1_STEP_NOT_FOUND"

    def test_reviewer_id_필수(self, client: TestClient) -> None:
        """reviewer_id 누락 시 422."""
        case_id = "00000000-0000-0000-0000-000000000003"
        response = client.post(
            self.BASE.format(case_id=case_id),
            json={"ingredient_decisions": [], "escalation_acknowledgements": []},
        )
        assert response.status_code == 422


# ============================================================
# POST /api/v1/cases/{case_id}/pipeline/feature/1/confirm
# ============================================================


class TestHitl2ConfirmEndpoint:
    """HITL-2 최종 판정 엔드포인트 테스트."""

    BASE = "/api/v1/cases/{case_id}/pipeline/feature/1/confirm"

    def _confirm_body(
        self,
        verdict: str = "수입가능",
        reason: str = "모든 원재료가 허용 기준 이내입니다",
    ) -> dict:
        return {
            "user_verdict": verdict,
            "final_reason": reason,
            "selected_citations": [],
            "signer_id": "signer-001",
            "signed_at": "2026-04-20T15:00:00+00:00",
        }

    def test_정상_확정_200(self, client: TestClient) -> None:
        """waiting_review → 200 + confirmed."""
        from models.f1_hitl import HITL2ConfirmResponse

        case_id = "00000000-0000-0000-0000-000000000003"
        mock_resp = HITL2ConfirmResponse(
            case_id=case_id,
            status="confirmed",
            final_verdict="수입가능",
            signed_at=datetime(2026, 4, 20, 15, 0, 0, tzinfo=timezone.utc),
            audit_log_id=30,
        )

        with patch("routers.feature1.confirm_hitl2", return_value=mock_resp):
            response = client.post(
                self.BASE.format(case_id=case_id),
                json=self._confirm_body(),
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "confirmed"
        assert body["final_verdict"] == "수입가능"
        assert body["audit_log_id"] == 30

    def test_미해결_에스컬레이션_400(self, client: TestClient) -> None:
        """미해결 에스컬레이션 있으면 400."""
        case_id = "00000000-0000-0000-0000-000000000004"

        with patch(
            "routers.feature1.confirm_hitl2",
            side_effect=ValueError("미해결 에스컬레이션(['unidentified'])이 있습니다."),
        ):
            response = client.post(
                self.BASE.format(case_id=case_id),
                json=self._confirm_body(),
            )

        assert response.status_code == 400
        assert response.json()["detail"]["error"] == "HITL2_CONFIRM_FAILED"

    def test_잘못된_상태_400(self, client: TestClient) -> None:
        """running 상태에서 confirm → 400."""
        case_id = "00000000-0000-0000-0000-000000000004"

        with patch(
            "routers.feature1.confirm_hitl2",
            side_effect=ValueError("HITL-2 확정은 status='waiting_review' 상태에서만 가능합니다."),
        ):
            response = client.post(
                self.BASE.format(case_id=case_id),
                json=self._confirm_body(),
            )

        assert response.status_code == 400

    def test_스텝_없음_404(self, client: TestClient) -> None:
        """F1 스텝 없으면 404."""
        case_id = "nonexistent"

        with patch(
            "routers.feature1.confirm_hitl2",
            side_effect=ValueError("F1 파이프라인 스텝이 존재하지 않습니다."),
        ):
            response = client.post(
                self.BASE.format(case_id=case_id),
                json=self._confirm_body(),
            )

        assert response.status_code == 404

    def test_final_reason_최소_10자(self, client: TestClient) -> None:
        """final_reason 10자 미만 시 422 (Pydantic min_length=10)."""
        case_id = "00000000-0000-0000-0000-000000000003"
        body = self._confirm_body(reason="짧음")  # 3자
        response = client.post(self.BASE.format(case_id=case_id), json=body)
        assert response.status_code == 422

    def test_수입불가_판정_200(self, client: TestClient) -> None:
        """수입불가 판정도 200 처리."""
        from models.f1_hitl import HITL2ConfirmResponse

        case_id = "00000000-0000-0000-0000-000000000003"
        mock_resp = HITL2ConfirmResponse(
            case_id=case_id,
            status="confirmed",
            final_verdict="수입불가",
            signed_at=datetime(2026, 4, 20, 15, 0, 0, tzinfo=timezone.utc),
            audit_log_id=31,
        )

        with patch("routers.feature1.confirm_hitl2", return_value=mock_resp):
            response = client.post(
                self.BASE.format(case_id=case_id),
                json=self._confirm_body(
                    verdict="수입불가",
                    reason="소르빈산 기준치 초과로 수입이 불가합니다",
                ),
            )

        assert response.status_code == 200
        assert response.json()["final_verdict"] == "수입불가"


# ============================================================
# POST /feature/1/run — HITL-0 게이트 테스트
# ============================================================


class TestF1RunHitl0Gate:
    """F1_REQUIRE_HITL0_APPROVAL feature flag 게이트 테스트."""

    BASE = "/api/v1/cases/{case_id}/pipeline/feature/1/run"

    def test_flag_on_미승인_400_F0_NOT_APPROVED(self, client: TestClient) -> None:
        """F1_REQUIRE_HITL0_APPROVAL=True + F0 status!=approved → 400 F0_NOT_APPROVED."""
        case_id = "00000000-0000-0000-0000-000000000001"

        mock_sb = MagicMock()
        f0_select = MagicMock()
        f0_select.data = [{"status": "completed"}]  # approved 아님
        (
            mock_sb.table.return_value
            .select.return_value
            .eq.return_value
            .eq.return_value
            .limit.return_value
            .execute.return_value
        ) = f0_select

        with (
            patch("routers.feature1.F1_REQUIRE_HITL0_APPROVAL", True),
            patch("routers.feature1.get_supabase", return_value=mock_sb),
        ):
            response = client.post(
                self.BASE.format(case_id=case_id),
                json={"ingredients": None},
            )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["error"] == "F0_NOT_APPROVED"

    def test_flag_on_승인완료_게이트_통과(self, client: TestClient) -> None:
        """F1_REQUIRE_HITL0_APPROVAL=True + F0 status='approved' → 게이트 통과."""
        case_id = "00000000-0000-0000-0000-000000000002"

        mock_sb = MagicMock()
        f0_select = MagicMock()
        f0_select.data = [{"status": "approved"}]
        (
            mock_sb.table.return_value
            .select.return_value
            .eq.return_value
            .eq.return_value
            .limit.return_value
            .execute.return_value
        ) = f0_select

        # run_feature1_with_rag 는 별도 mock — 게이트 통과 여부만 확인
        with (
            patch("routers.feature1.F1_REQUIRE_HITL0_APPROVAL", True),
            patch("routers.feature1.get_supabase", return_value=mock_sb),
            patch(
                "routers.feature1._fetch_f0_parsed_result",
                return_value={
                    "ingredients": [{"name": "구연산", "ratio": "0.05"}],
                    "process_info": {"process_codes": []},
                },
            ),
            patch(
                "routers.feature1.asyncio.run",
                return_value=(
                    MagicMock(
                        forbidden_hits=[],
                        aggregation=None,
                        conditional_evaluations=[],
                        synthetic_flavor_ingredients=[],
                        standards_check=None,
                        escalations=[],
                        law_refs=[],
                        import_possible=True,
                    ),
                    None,
                    "rag_skipped",
                ),
            ),
            patch("routers.feature1._upsert_pipeline_step"),
        ):
            response = client.post(
                self.BASE.format(case_id=case_id),
                json={},
            )

        # 400 F0_NOT_APPROVED 가 아닌 다른 응답이면 게이트 통과
        assert response.status_code != 400 or (
            response.json().get("detail", {}).get("error") != "F0_NOT_APPROVED"
        )

    def test_flag_off_게이트_스킵(self, client: TestClient) -> None:
        """F1_REQUIRE_HITL0_APPROVAL=False → HITL-0 게이트 스킵."""
        case_id = "00000000-0000-0000-0000-000000000001"

        with patch("routers.feature1.F1_REQUIRE_HITL0_APPROVAL", False):
            # F0 상태 조회 없이 다음 단계(f0 parsed result 조회)로 넘어감
            with patch(
                "routers.feature1._fetch_f0_parsed_result",
                return_value=None,  # f0 not completed
            ):
                response = client.post(
                    self.BASE.format(case_id=case_id),
                    json={},
                )

        # F0_NOT_COMPLETED 에러가 나야 함 (F0_NOT_APPROVED 가 아님)
        assert response.status_code == 400
        assert response.json()["detail"]["error"] == "F0_NOT_COMPLETED"
