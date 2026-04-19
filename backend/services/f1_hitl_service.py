"""F1 HITL 서비스 계층 — HITL-0 / HITL-1 / HITL-2 상태 전이 처리.

pipeline_steps 테이블과 f1_audit_log 테이블을 직접 갱신한다.
Day 0 동결 Pydantic 모델(backend/models/f1_hitl.py)을 소비하여
모든 HITL 액션에 대한 감사 로그를 남긴다.

상태 전이 규칙 (05번 §6):
    F0: completed → (PATCH edit) → completed (강등)
        completed → (POST approve) → approved
    F1: any → (HITL-1 decisions, all ack) → waiting_review
        any → (HITL-1 decisions, partial ack) → needs_review
        waiting_review → (HITL-2 confirm) → confirmed

참조:
    계획/f1 재설계 계획/05_HITL_플로우_설계.md §3-4, §4, §5, §7
    backend/models/f1_hitl.py (Day 0 동결 — import 전용)
    backend/db/migrations/017_pipeline_steps_status_expansion.sql
    backend/db/migrations/018_f1_audit_log.sql
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from db.supabase_client import get_supabase
from models.f1_hitl import (
    F0ApproveRequest,
    F0ApproveResponse,
    F0EditRequest,
    F0EditResponse,
    HITL1DecisionsRequest,
    HITL1DecisionsResponse,
    HITL2ConfirmRequest,
    HITL2ConfirmResponse,
)


# ============================================================
# 내부 헬퍼
# ============================================================


def _fetch_step(case_id: str, step_key: str) -> Optional[dict]:
    """pipeline_steps 에서 단일 행을 조회한다."""
    supabase = get_supabase()
    result = (
        supabase.table("pipeline_steps")
        .select(
            "id, case_id, step_key, status, ai_result, final_result, "
            "edit_reason, created_at, updated_at"
        )
        .eq("case_id", case_id)
        .eq("step_key", step_key)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _update_step(case_id: str, step_key: str, patch: dict) -> None:
    """pipeline_steps 행을 부분 갱신한다."""
    supabase = get_supabase()
    (
        supabase.table("pipeline_steps")
        .update(patch)
        .eq("case_id", case_id)
        .eq("step_key", step_key)
        .execute()
    )


def _insert_audit_log(
    *,
    case_id: str,
    step: str,
    action: str,
    actor_id: str,
    before: Optional[Any] = None,
    after: Optional[Any] = None,
    reason: Optional[str] = None,
    signed_at: Optional[datetime] = None,
) -> int:
    """f1_audit_log 에 레코드를 삽입하고 생성된 id 를 반환한다.

    step   허용값: 'f0' | 'f1.hitl1' | 'f1.hitl2'
    action 허용값: 'edit' | 'approve' | 'hitl1_decisions' | 'confirm' | 'unlock'
    """
    supabase = get_supabase()
    payload: dict[str, Any] = {
        "case_id": case_id,
        "step": step,
        "action": action,
        "actor_id": actor_id,
    }
    if before is not None:
        payload["before"] = before
    if after is not None:
        payload["after"] = after
    if reason is not None:
        payload["reason"] = reason
    if signed_at is not None:
        # Supabase-py 는 datetime → ISO 8601 string 자동 처리
        payload["signed_at"] = signed_at.isoformat()

    result = supabase.table("f1_audit_log").insert(payload).execute()
    return result.data[0]["id"]


# ============================================================
# HITL-0: F0 편집 (PATCH /pipeline/feature/0)
# ============================================================


def apply_f0_edit(case_id: str, request: F0EditRequest) -> F0EditResponse:
    """F0 파싱 결과를 담당자가 편집한다.

    - pipeline_steps(step_key='0').final_result 를 갱신한다.
    - 편집이 있으면 status 를 'completed' 로 강등 (approved → completed).
    - f1_audit_log 에 'edit' 액션을 기록한다.

    Args:
        case_id:  케이스 UUID 문자열
        request:  F0EditRequest (final_result + edit_reason)

    Returns:
        F0EditResponse (status='completed' 고정)

    Raises:
        ValueError: step_key='0' 행이 존재하지 않을 때
        ValueError: 현재 status='locked' 또는 'confirmed' 일 때 편집 불가
    """
    row = _fetch_step(case_id, "0")
    if row is None:
        raise ValueError(f"case_id={case_id} 의 F0 파이프라인 스텝이 존재하지 않습니다.")

    current_status = row.get("status", "")
    if current_status in ("locked", "confirmed"):
        raise PermissionError(
            f"status='{current_status}' 상태에서는 편집할 수 없습니다. (locked/confirmed)"
        )

    before_snapshot = {
        "status": current_status,
        "final_result": row.get("final_result"),
    }
    after_snapshot = {
        "status": "completed",
        "final_result": request.final_result,
    }

    # 1) pipeline_steps 갱신: final_result 저장, status 강등
    _update_step(
        case_id,
        "0",
        {
            "final_result": request.final_result,
            "edit_reason": request.edit_reason,
            "status": "completed",
        },
    )

    # 2) 감사 로그 기록
    audit_id = _insert_audit_log(
        case_id=case_id,
        step="f0",
        action="edit",
        actor_id="system",  # 편집자 ID는 라우터에서 주입 (현재 HITL-0 편집에는 actor 없음)
        before=before_snapshot,
        after=after_snapshot,
        reason=request.edit_reason,
    )

    return F0EditResponse(
        case_id=case_id,
        status="completed",
        updated_at=datetime.now(tz=timezone.utc),
        audit_log_id=audit_id,
    )


# ============================================================
# HITL-0: F0 승인 (POST /pipeline/feature/0/approve)
# ============================================================


def approve_f0(case_id: str, request: F0ApproveRequest) -> F0ApproveResponse:
    """F0 파싱 결과를 담당자가 승인한다.

    - pipeline_steps(step_key='0').status = 'approved' 로 전이.
    - f1_audit_log 에 'approve' 액션을 기록한다.

    Args:
        case_id:  케이스 UUID 문자열
        request:  F0ApproveRequest (approver_id + approved_at + signature?)

    Returns:
        F0ApproveResponse (status='approved', audit_log_id)

    Raises:
        ValueError: step_key='0' 행이 존재하지 않을 때
        ValueError: 현재 status 가 'completed' 가 아닐 때 (편집 후 재승인 필요 상태 아님)
    """
    row = _fetch_step(case_id, "0")
    if row is None:
        raise ValueError(f"case_id={case_id} 의 F0 파이프라인 스텝이 존재하지 않습니다.")

    current_status = row.get("status", "")
    # 승인 가능한 상태: completed (또는 이미 approved 였지만 재승인 허용)
    if current_status not in ("completed", "approved"):
        raise ValueError(
            f"F0 승인은 status='completed' 상태에서만 가능합니다. 현재: '{current_status}'"
        )

    before_snapshot = {"status": current_status}
    after_snapshot = {"status": "approved"}

    # 1) pipeline_steps 갱신
    _update_step(case_id, "0", {"status": "approved"})

    # 2) 감사 로그 기록
    audit_id = _insert_audit_log(
        case_id=case_id,
        step="f0",
        action="approve",
        actor_id=request.approver_id,
        before=before_snapshot,
        after=after_snapshot,
        signed_at=request.approved_at,
    )

    return F0ApproveResponse(
        case_id=case_id,
        status="approved",
        approved_at=request.approved_at,
        audit_log_id=audit_id,
    )


# ============================================================
# HITL-1: 불확실 원재료 / 자동 판정 불가 처리
# (POST /pipeline/feature/1/hitl1-decisions)
# ============================================================


def submit_hitl1_decisions(
    case_id: str, request: HITL1DecisionsRequest
) -> HITL1DecisionsResponse:
    """HITL-1 담당자 결정을 F1 파이프라인 스텝에 병합 저장한다.

    모든 에스컬레이션에 응답(ack)했으면 status='waiting_review' 로 전이.
    일부만 처리했으면 status='needs_review' 유지.

    에스컬레이션 체크 방법:
        ai_result._internal.escalations 목록의 trigger_type 을 기준으로
        escalation_acknowledgements 와 대조한다.

    Args:
        case_id:  케이스 UUID 문자열
        request:  HITL1DecisionsRequest

    Returns:
        HITL1DecisionsResponse (status, unresolved_escalations, audit_log_id)

    Raises:
        ValueError: step_key='1' 행이 존재하지 않을 때
    """
    row = _fetch_step(case_id, "1")
    if row is None:
        raise ValueError(f"case_id={case_id} 의 F1 파이프라인 스텝이 존재하지 않습니다.")

    # 기존 ai_result 에서 에스컬레이션 목록 추출
    ai_result: dict = row.get("ai_result") or {}
    internal: dict = ai_result.get("_internal") or {}
    escalations: list = internal.get("escalations") or []

    # trigger_type 기준으로 미해결 에스컬레이션 계산
    all_escalation_types = [
        esc.get("trigger_type", "") for esc in escalations if esc.get("trigger_type")
    ]
    acked_set = set(request.escalation_acknowledgements)
    unresolved = [t for t in all_escalation_types if t not in acked_set]

    new_status = "waiting_review" if not unresolved else "needs_review"

    # 기존 final_result 에 HITL-1 결정 병합
    existing_final: dict = dict(row.get("final_result") or ai_result or {})
    hitl1_patch: dict[str, Any] = {
        "ingredient_decisions": [d.model_dump() for d in request.ingredient_decisions],
        "conditional_resolutions": [r.model_dump() for r in request.conditional_resolutions],
        "qualitative_resolutions": [r.model_dump() for r in request.qualitative_resolutions],
        "escalation_acknowledgements": list(request.escalation_acknowledgements),
    }
    # _hitl1 키에 병합 저장 (기존 ai_result 필드 보존)
    existing_final["_hitl1"] = hitl1_patch

    before_snapshot = {"status": row.get("status")}
    after_snapshot = {
        "status": new_status,
        "hitl1_decisions_count": len(request.ingredient_decisions),
        "unresolved_escalations": unresolved,
    }

    # 1) pipeline_steps 갱신
    _update_step(
        case_id,
        "1",
        {
            "final_result": existing_final,
            "status": new_status,
        },
    )

    # 2) 감사 로그 기록
    audit_id = _insert_audit_log(
        case_id=case_id,
        step="f1.hitl1",
        action="hitl1_decisions",
        actor_id=request.reviewer_id,
        before=before_snapshot,
        after=after_snapshot,
    )

    return HITL1DecisionsResponse(
        case_id=case_id,
        status=new_status,
        unresolved_escalations=unresolved,
        audit_log_id=audit_id,
    )


# ============================================================
# HITL-2: 최종 판정 확정 (POST /pipeline/feature/1/confirm)
# ============================================================


def confirm_hitl2(case_id: str, request: HITL2ConfirmRequest) -> HITL2ConfirmResponse:
    """HITL-2 최종 판정을 확정한다.

    - unresolved_escalations > 0 이면 400 (호출자가 검증 후 호출해야 함).
    - pipeline_steps(step_key='1').status = 'confirmed' 로 전이.
    - f1_audit_log 에 'confirm' 액션을 기록한다.
    - Wave 4 P7 이후 'locked' 로 전이 예정 (현재는 'confirmed' 유지).

    Args:
        case_id:  케이스 UUID 문자열
        request:  HITL2ConfirmRequest (user_verdict + final_reason + signer_id + signed_at)

    Returns:
        HITL2ConfirmResponse (status='confirmed', final_verdict, audit_log_id)

    Raises:
        ValueError: step_key='1' 행이 존재하지 않을 때
        ValueError: status='waiting_review' 가 아닐 때 (HITL-1 미완료)
        ValueError: unresolved_escalations 가 남아 있을 때
    """
    row = _fetch_step(case_id, "1")
    if row is None:
        raise ValueError(f"case_id={case_id} 의 F1 파이프라인 스텝이 존재하지 않습니다.")

    current_status = row.get("status", "")

    # HITL-1 미완료 차단 (needs_review = 미해결 에스컬레이션 있음)
    if current_status == "needs_review":
        # final_result 에서 unresolved_escalations 확인
        final: dict = row.get("final_result") or {}
        hitl1: dict = final.get("_hitl1") or {}
        acked_set = set(hitl1.get("escalation_acknowledgements") or [])

        ai_result: dict = row.get("ai_result") or {}
        internal: dict = ai_result.get("_internal") or {}
        escalations: list = internal.get("escalations") or []
        all_types = [
            esc.get("trigger_type", "") for esc in escalations if esc.get("trigger_type")
        ]
        unresolved = [t for t in all_types if t not in acked_set]
        if unresolved:
            raise ValueError(
                f"미해결 에스컬레이션({unresolved})이 있습니다. HITL-1을 먼저 완료하세요."
            )

    # waiting_review 또는 needs_review(에스컬 없는 경우)만 confirm 가능
    if current_status not in ("waiting_review", "needs_review"):
        raise ValueError(
            f"HITL-2 확정은 status='waiting_review' 상태에서만 가능합니다. 현재: '{current_status}'"
        )

    before_snapshot = {
        "status": current_status,
        "final_result": row.get("final_result"),
    }

    # HITL-2 결정 내용을 final_result 에 병합
    existing_final: dict = dict(row.get("final_result") or row.get("ai_result") or {})
    existing_final["_hitl2"] = {
        "user_verdict": request.user_verdict,
        "final_reason": request.final_reason,
        "selected_citations": request.selected_citations,
        "signer_id": request.signer_id,
        "signed_at": request.signed_at.isoformat(),
    }

    after_snapshot = {
        "status": "confirmed",
        "user_verdict": request.user_verdict,
    }

    # 1) pipeline_steps 갱신
    _update_step(
        case_id,
        "1",
        {
            "final_result": existing_final,
            "status": "confirmed",
        },
    )

    # 2) 감사 로그 기록
    audit_id = _insert_audit_log(
        case_id=case_id,
        step="f1.hitl2",
        action="confirm",
        actor_id=request.signer_id,
        before=before_snapshot,
        after=after_snapshot,
        reason=request.final_reason,
        signed_at=request.signed_at,
    )

    return HITL2ConfirmResponse(
        case_id=case_id,
        status="confirmed",
        final_verdict=request.user_verdict,
        signed_at=request.signed_at,
        audit_log_id=audit_id,
    )
