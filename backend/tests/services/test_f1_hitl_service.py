"""W3-BE: F1 HITL 서비스 단위 테스트.

커버리지 목표: 85%+

테스트 시나리오 (05번 §9 전수):
    1. apply_f0_edit: 정상 편집 → status='completed' 강등 + audit_log 기록
    2. apply_f0_edit: status='locked' → PermissionError
    3. apply_f0_edit: status='confirmed' → PermissionError
    4. apply_f0_edit: F0 스텝 없음 → ValueError
    5. approve_f0: 정상 승인 (completed → approved)
    6. approve_f0: 재승인 허용 (approved → approved)
    7. approve_f0: 잘못된 상태 → ValueError
    8. approve_f0: F0 스텝 없음 → ValueError
    9. submit_hitl1_decisions: 전체 ack → status='waiting_review'
    10. submit_hitl1_decisions: 일부 ack → status='needs_review' + unresolved 반환
    11. submit_hitl1_decisions: 에스컬레이션 없는 케이스 → waiting_review
    12. submit_hitl1_decisions: F1 스텝 없음 → ValueError
    13. confirm_hitl2: waiting_review 상태에서 정상 확정
    14. confirm_hitl2: needs_review + 미해결 에스컬레이션 → ValueError
    15. confirm_hitl2: needs_review + 전체 ack (에스컬 없는 실질) → 확정 성공
    16. confirm_hitl2: 잘못된 상태 → ValueError
    17. confirm_hitl2: F1 스텝 없음 → ValueError
    18. 모든 액션이 f1_audit_log 에 기록됨 (audit_log_id 반환 확인)

실행:
    cd backend
    pytest tests/services/test_f1_hitl_service.py -v --cov=services.f1_hitl_service
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from models.f1_hitl import (
    F0ApproveRequest,
    F0EditRequest,
    HITL1DecisionsRequest,
    HITL2ConfirmRequest,
    IngredientDecision,
)
from services.f1_hitl_service import (
    apply_f0_edit,
    approve_f0,
    confirm_hitl2,
    submit_hitl1_decisions,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "f1_hitl"


def load_fixture(filename: str) -> dict:
    with open(FIXTURES_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# Mock 헬퍼
# ============================================================


def _make_supabase_mock(
    fetch_row: dict | None = None,
    audit_insert_id: int = 1,
) -> MagicMock:
    """Supabase 클라이언트 mock — fetch/update/insert 공통 패턴."""
    mock = MagicMock()

    # select chain → execute()
    select_result = MagicMock()
    select_result.data = [fetch_row] if fetch_row is not None else []
    (
        mock.table.return_value
        .select.return_value
        .eq.return_value
        .eq.return_value
        .limit.return_value
        .execute.return_value
    ) = select_result

    # update chain
    (
        mock.table.return_value
        .update.return_value
        .eq.return_value
        .eq.return_value
        .execute.return_value
    ) = MagicMock()

    # insert chain → execute() returns audit log id
    insert_result = MagicMock()
    insert_result.data = [{"id": audit_insert_id}]
    mock.table.return_value.insert.return_value.execute.return_value = insert_result

    return mock


# ============================================================
# apply_f0_edit 테스트
# ============================================================


class TestApplyF0Edit:
    """HITL-0 편집 기능 테스트."""

    def test_정상_편집_status_completed_강등(self) -> None:
        """편집 성공: status='approved' → 'completed' 강등, audit_log_id 반환."""
        row = load_fixture("f0_step_approved.json")
        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=42)

        req = F0EditRequest(
            final_result={"basic_info": {"product_name": "수정제품"}},
            edit_reason="제품명 오류 수정",
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            resp = apply_f0_edit(row["case_id"], req)

        assert resp.status == "completed"
        assert resp.audit_log_id == 42
        assert resp.case_id == row["case_id"]

    def test_completed_상태_편집_가능(self) -> None:
        """status='completed' 상태에서도 편집 가능 (approved → completed 는 이미 completed)."""
        row = load_fixture("f0_step_completed.json")
        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=10)

        req = F0EditRequest(
            final_result={"basic_info": {"product_name": "편집된제품"}},
            edit_reason="원재료 비율 수정",
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            resp = apply_f0_edit(row["case_id"], req)

        assert resp.status == "completed"
        assert resp.audit_log_id == 10

    def test_locked_상태_편집_불가(self) -> None:
        """status='locked' 상태에서 편집 시 PermissionError."""
        row = {**load_fixture("f0_step_approved.json"), "status": "locked"}
        mock_sb = _make_supabase_mock(fetch_row=row)

        req = F0EditRequest(
            final_result={},
            edit_reason="강제 편집",
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            with pytest.raises(PermissionError, match="locked"):
                apply_f0_edit(row["case_id"], req)

    def test_confirmed_상태_편집_불가(self) -> None:
        """status='confirmed' 상태에서 편집 시 PermissionError."""
        row = {**load_fixture("f0_step_approved.json"), "status": "confirmed"}
        mock_sb = _make_supabase_mock(fetch_row=row)

        req = F0EditRequest(
            final_result={},
            edit_reason="강제 편집",
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            with pytest.raises(PermissionError, match="confirmed"):
                apply_f0_edit(row["case_id"], req)

    def test_f0_스텝_없음_ValueError(self) -> None:
        """F0 스텝이 존재하지 않으면 ValueError."""
        mock_sb = _make_supabase_mock(fetch_row=None)

        req = F0EditRequest(final_result={}, edit_reason="사유")

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            with pytest.raises(ValueError, match="존재하지 않습니다"):
                apply_f0_edit("nonexistent-case-id", req)

    def test_audit_log_기록됨(self) -> None:
        """편집 시 f1_audit_log insert 가 호출됨."""
        row = load_fixture("f0_step_completed.json")
        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=99)

        req = F0EditRequest(
            final_result={"modified": True},
            edit_reason="감사 로그 테스트",
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            resp = apply_f0_edit(row["case_id"], req)

        # insert 가 호출되었는지 확인
        assert mock_sb.table.return_value.insert.called
        insert_payload = mock_sb.table.return_value.insert.call_args[0][0]
        assert insert_payload["step"] == "f0"
        assert insert_payload["action"] == "edit"
        assert insert_payload["reason"] == "감사 로그 테스트"
        assert resp.audit_log_id == 99


# ============================================================
# approve_f0 테스트
# ============================================================


class TestApproveF0:
    """HITL-0 승인 기능 테스트."""

    def test_정상_승인_completed_to_approved(self) -> None:
        """status='completed' → 'approved' 전이."""
        row = load_fixture("f0_step_completed.json")
        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=5)

        req = F0ApproveRequest(
            approver_id="user-001",
            approved_at=datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc),
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            resp = approve_f0(row["case_id"], req)

        assert resp.status == "approved"
        assert resp.audit_log_id == 5
        assert resp.approved_at == req.approved_at

    def test_재승인_허용_approved_to_approved(self) -> None:
        """이미 approved 상태에서 재승인 허용."""
        row = load_fixture("f0_step_approved.json")
        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=6)

        req = F0ApproveRequest(
            approver_id="user-002",
            approved_at=datetime(2026, 4, 20, 13, 0, 0, tzinfo=timezone.utc),
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            resp = approve_f0(row["case_id"], req)

        assert resp.status == "approved"

    def test_잘못된_상태_ValueError(self) -> None:
        """status='pending' 에서 승인 시 ValueError."""
        row = {**load_fixture("f0_step_completed.json"), "status": "pending"}
        mock_sb = _make_supabase_mock(fetch_row=row)

        req = F0ApproveRequest(
            approver_id="user-001",
            approved_at=datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc),
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            with pytest.raises(ValueError, match="completed"):
                approve_f0(row["case_id"], req)

    def test_f0_스텝_없음_ValueError(self) -> None:
        """F0 스텝 없으면 ValueError."""
        mock_sb = _make_supabase_mock(fetch_row=None)

        req = F0ApproveRequest(
            approver_id="user-001",
            approved_at=datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc),
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            with pytest.raises(ValueError, match="존재하지 않습니다"):
                approve_f0("nonexistent", req)

    def test_audit_log_기록됨(self) -> None:
        """승인 시 f1_audit_log insert 가 호출됨."""
        row = load_fixture("f0_step_completed.json")
        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=7)

        req = F0ApproveRequest(
            approver_id="approver-xyz",
            approved_at=datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc),
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            approve_f0(row["case_id"], req)

        insert_payload = mock_sb.table.return_value.insert.call_args[0][0]
        assert insert_payload["step"] == "f0"
        assert insert_payload["action"] == "approve"
        assert insert_payload["actor_id"] == "approver-xyz"

    def test_signature_포함_승인(self) -> None:
        """signature 필드 포함 승인 (선택 필드 — None 이외)."""
        row = load_fixture("f0_step_completed.json")
        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=8)

        req = F0ApproveRequest(
            approver_id="user-sig",
            approved_at=datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc),
            signature="base64encodedimagedata==",
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            resp = approve_f0(row["case_id"], req)

        assert resp.status == "approved"


# ============================================================
# submit_hitl1_decisions 테스트
# ============================================================


class TestSubmitHitl1Decisions:
    """HITL-1 결정 처리 테스트."""

    def test_전체_ack_waiting_review(self) -> None:
        """모든 에스컬레이션 ack → status='waiting_review'."""
        row = load_fixture("f1_step_needs_review.json")
        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=20)

        req = HITL1DecisionsRequest(
            ingredient_decisions=[],
            escalation_acknowledgements=["api_failure", "unidentified"],
            reviewer_id="reviewer-001",
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            resp = submit_hitl1_decisions(row["case_id"], req)

        assert resp.status == "waiting_review"
        assert resp.unresolved_escalations == []
        assert resp.audit_log_id == 20

    def test_일부_ack_needs_review(self) -> None:
        """일부만 ack → status='needs_review', unresolved_escalations 반환."""
        row = load_fixture("f1_step_needs_review.json")
        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=21)

        req = HITL1DecisionsRequest(
            ingredient_decisions=[],
            escalation_acknowledgements=["api_failure"],  # unidentified 미처리
            reviewer_id="reviewer-002",
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            resp = submit_hitl1_decisions(row["case_id"], req)

        assert resp.status == "needs_review"
        assert "unidentified" in resp.unresolved_escalations

    def test_에스컬레이션_없는_케이스_waiting_review(self) -> None:
        """에스컬레이션 없는 케이스 → 빈 ack 목록이어도 waiting_review."""
        row = load_fixture("f1_step_waiting_review.json")
        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=22)

        req = HITL1DecisionsRequest(
            ingredient_decisions=[
                IngredientDecision(name="미확인원재료A", decision="allow")
            ],
            escalation_acknowledgements=[],
            reviewer_id="reviewer-003",
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            resp = submit_hitl1_decisions(row["case_id"], req)

        assert resp.status == "waiting_review"
        assert resp.unresolved_escalations == []

    def test_f1_스텝_없음_ValueError(self) -> None:
        """F1 스텝 없으면 ValueError."""
        mock_sb = _make_supabase_mock(fetch_row=None)

        req = HITL1DecisionsRequest(
            ingredient_decisions=[],
            escalation_acknowledgements=[],
            reviewer_id="reviewer-x",
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            with pytest.raises(ValueError, match="존재하지 않습니다"):
                submit_hitl1_decisions("nonexistent", req)

    def test_audit_log_기록됨(self) -> None:
        """HITL-1 결정 시 f1_audit_log insert 호출 확인."""
        row = load_fixture("f1_step_needs_review.json")
        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=23)

        req = HITL1DecisionsRequest(
            ingredient_decisions=[],
            escalation_acknowledgements=["api_failure", "unidentified"],
            reviewer_id="audit-test-reviewer",
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            submit_hitl1_decisions(row["case_id"], req)

        insert_payload = mock_sb.table.return_value.insert.call_args[0][0]
        assert insert_payload["step"] == "f1.hitl1"
        assert insert_payload["action"] == "hitl1_decisions"
        assert insert_payload["actor_id"] == "audit-test-reviewer"

    def test_ingredient_decisions_병합_저장(self) -> None:
        """ingredient_decisions 이 final_result._hitl1 에 병합됨."""
        row = load_fixture("f1_step_waiting_review.json")
        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=24)

        req = HITL1DecisionsRequest(
            ingredient_decisions=[
                IngredientDecision(name="원재료A", decision="deny"),
                IngredientDecision(name="원재료B", decision="allow"),
            ],
            escalation_acknowledgements=[],
            reviewer_id="reviewer-merge",
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            resp = submit_hitl1_decisions(row["case_id"], req)

        # update 호출 인자에서 final_result._hitl1 확인
        update_payload = mock_sb.table.return_value.update.call_args[0][0]
        hitl1_data = update_payload["final_result"]["_hitl1"]
        assert len(hitl1_data["ingredient_decisions"]) == 2
        assert hitl1_data["ingredient_decisions"][0]["name"] == "원재료A"
        assert hitl1_data["ingredient_decisions"][0]["decision"] == "deny"


# ============================================================
# confirm_hitl2 테스트
# ============================================================


class TestConfirmHitl2:
    """HITL-2 최종 판정 확정 테스트."""

    def _make_confirm_request(
        self,
        verdict: str = "수입가능",
        reason: str = "모든 원재료가 허용 기준 이내입니다",
    ) -> HITL2ConfirmRequest:
        return HITL2ConfirmRequest(
            user_verdict=verdict,
            final_reason=reason,
            selected_citations=[],
            signer_id="signer-001",
            signed_at=datetime(2026, 4, 20, 15, 0, 0, tzinfo=timezone.utc),
        )

    def test_waiting_review_정상_확정(self) -> None:
        """status='waiting_review' → 'confirmed' 전이."""
        row = load_fixture("f1_step_waiting_review.json")
        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=30)

        req = self._make_confirm_request()

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            resp = confirm_hitl2(row["case_id"], req)

        assert resp.status == "confirmed"
        assert resp.final_verdict == "수입가능"
        assert resp.audit_log_id == 30

    def test_needs_review_미해결_에스컬레이션_차단(self) -> None:
        """needs_review + 미해결 에스컬레이션 → ValueError."""
        row = load_fixture("f1_step_needs_review.json")
        # final_result 에 _hitl1 없음 = ack 0건
        mock_sb = _make_supabase_mock(fetch_row=row)

        req = self._make_confirm_request()

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            with pytest.raises(ValueError, match="미해결 에스컬레이션"):
                confirm_hitl2(row["case_id"], req)

    def test_needs_review_전체_ack_후_확정_성공(self) -> None:
        """needs_review 이지만 final_result._hitl1 에 모든 ack 있으면 확정 가능."""
        row = {
            **load_fixture("f1_step_needs_review.json"),
            "final_result": {
                "_hitl1": {
                    "escalation_acknowledgements": ["api_failure", "unidentified"]
                }
            },
        }
        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=31)

        req = self._make_confirm_request()

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            resp = confirm_hitl2(row["case_id"], req)

        assert resp.status == "confirmed"

    def test_잘못된_상태_ValueError(self) -> None:
        """status='running' 에서 confirm → ValueError."""
        row = {**load_fixture("f1_step_waiting_review.json"), "status": "running"}
        mock_sb = _make_supabase_mock(fetch_row=row)

        req = self._make_confirm_request()

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            with pytest.raises(ValueError, match="waiting_review"):
                confirm_hitl2(row["case_id"], req)

    def test_f1_스텝_없음_ValueError(self) -> None:
        """F1 스텝 없으면 ValueError."""
        mock_sb = _make_supabase_mock(fetch_row=None)

        req = self._make_confirm_request()

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            with pytest.raises(ValueError, match="존재하지 않습니다"):
                confirm_hitl2("nonexistent", req)

    def test_수입불가_판정_확정(self) -> None:
        """'수입불가' 판정도 정상 처리."""
        row = load_fixture("f1_step_waiting_review.json")
        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=32)

        req = self._make_confirm_request(
            verdict="수입불가",
            reason="소르빈산 허용 기준치를 초과하였습니다",
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            resp = confirm_hitl2(row["case_id"], req)

        assert resp.final_verdict == "수입불가"

    def test_보류_판정_확정(self) -> None:
        """'보류' 판정도 정상 처리."""
        row = load_fixture("f1_step_waiting_review.json")
        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=33)

        req = self._make_confirm_request(
            verdict="보류",
            reason="추가 서류 제출 후 재검토가 필요합니다",
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            resp = confirm_hitl2(row["case_id"], req)

        assert resp.final_verdict == "보류"

    def test_audit_log_기록됨(self) -> None:
        """확정 시 f1_audit_log insert 호출 확인."""
        row = load_fixture("f1_step_waiting_review.json")
        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=34)

        req = self._make_confirm_request()

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            confirm_hitl2(row["case_id"], req)

        insert_payload = mock_sb.table.return_value.insert.call_args[0][0]
        assert insert_payload["step"] == "f1.hitl2"
        assert insert_payload["action"] == "confirm"
        assert insert_payload["actor_id"] == "signer-001"
        assert insert_payload["reason"] == req.final_reason

    def test_selected_citations_저장(self) -> None:
        """selected_citations 이 final_result._hitl2 에 저장됨."""
        row = load_fixture("f1_step_waiting_review.json")
        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=35)

        req = HITL2ConfirmRequest(
            user_verdict="수입가능",
            final_reason="법령 인용 포함하여 판정합니다",
            selected_citations=["chunk-001", "chunk-002"],
            signer_id="signer-cite",
            signed_at=datetime(2026, 4, 20, 16, 0, 0, tzinfo=timezone.utc),
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            confirm_hitl2(row["case_id"], req)

        update_payload = mock_sb.table.return_value.update.call_args[0][0]
        hitl2_data = update_payload["final_result"]["_hitl2"]
        assert hitl2_data["selected_citations"] == ["chunk-001", "chunk-002"]
        assert hitl2_data["user_verdict"] == "수입가능"


# ============================================================
# 교차 검증: 상태 전이 전수
# ============================================================


class TestStatusTransitionMatrix:
    """05번 §6 상태 전이 다이어그램 전수 검증."""

    def test_f0_completed_to_approved(self) -> None:
        """F0: completed → approve() → approved."""
        row = load_fixture("f0_step_completed.json")
        assert row["status"] == "completed"

        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=100)
        req = F0ApproveRequest(
            approver_id="u1",
            approved_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            resp = approve_f0(row["case_id"], req)

        assert resp.status == "approved"

    def test_f0_approved_edit_demotes_to_completed(self) -> None:
        """F0: approved → edit() → completed (자동 강등)."""
        row = load_fixture("f0_step_approved.json")
        assert row["status"] == "approved"

        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=101)
        req = F0EditRequest(final_result={}, edit_reason="강등 테스트")

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            resp = apply_f0_edit(row["case_id"], req)

        assert resp.status == "completed"

    def test_f1_needs_review_full_ack_to_waiting_review(self) -> None:
        """F1: needs_review → hitl1_decisions(전체 ack) → waiting_review."""
        row = load_fixture("f1_step_needs_review.json")
        assert row["status"] == "needs_review"

        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=102)
        req = HITL1DecisionsRequest(
            ingredient_decisions=[],
            escalation_acknowledgements=["api_failure", "unidentified"],
            reviewer_id="r1",
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            resp = submit_hitl1_decisions(row["case_id"], req)

        assert resp.status == "waiting_review"

    def test_f1_waiting_review_to_confirmed(self) -> None:
        """F1: waiting_review → confirm_hitl2() → confirmed."""
        row = load_fixture("f1_step_waiting_review.json")
        assert row["status"] == "waiting_review"

        mock_sb = _make_supabase_mock(fetch_row=row, audit_insert_id=103)
        req = HITL2ConfirmRequest(
            user_verdict="수입가능",
            final_reason="판정 근거가 명확합니다",
            selected_citations=[],
            signer_id="s1",
            signed_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
        )

        with patch("services.f1_hitl_service.get_supabase", return_value=mock_sb):
            resp = confirm_hitl2(row["case_id"], req)

        assert resp.status == "confirmed"
