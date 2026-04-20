"""F1 HITL API 계약 — Wave 3 Day 0 인터페이스 스켈레톤.

본 파일의 Pydantic 모델은 **Wave 3 Day 0에 동결**되었다.
W3-BE (백엔드 엔드포인트) + W3-FE (프론트 폼 타입) + W3-QA (E2E) 가 공통 참조한다.
필드 추가는 허용되나 **이름·타입 변경은 금지**한다.

참조:
    - 계획/f1 재설계 계획/05_HITL_플로우_설계.md §3-3, §4-3, §5-3
    - 계획/f1 재설계 계획/10_마이그레이션_계획.md §4-2 (status 확장)

엔드포인트 매핑:
    PATCH  /api/v1/cases/{case_id}/pipeline/feature/0                 → F0EditRequest/Response
    POST   /api/v1/cases/{case_id}/pipeline/feature/0/approve         → F0ApproveRequest/Response
    POST   /api/v1/cases/{case_id}/pipeline/feature/1/hitl1-decisions → HITL1DecisionsRequest/Response
    POST   /api/v1/cases/{case_id}/pipeline/feature/1/confirm         → HITL2ConfirmRequest/Response
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# pipeline_steps.status (migration 017 확장)
# ============================================================

PipelineStepStatus = Literal[
    "pending",
    "running",
    "completed",
    "approved",         # HITL-0 승인 (F0 전용)
    "waiting_review",
    "needs_review",     # HITL-1 필요 (에스컬레이션 있음)
    "confirmed",        # HITL-2 완료
    "locked",           # 확정 후 잠김
]


# ============================================================
# HITL-0: F0 결과 편집·승인 (05번 §3)
# ============================================================


class F0EditRequest(BaseModel):
    """PATCH /api/v1/cases/{case_id}/pipeline/feature/0"""

    model_config = ConfigDict(extra="ignore")

    final_result: dict[str, Any] = Field(
        ...,
        description="편집된 ParsedResult 전체 (basic_info + ingredients + process_codes)",
    )
    edit_reason: str = Field(..., min_length=1, description="편집 사유 (감사 기록)")


class F0EditResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    case_id: str
    status: PipelineStepStatus = Field(..., description="편집 후 강등되어 'completed'")
    updated_at: datetime
    audit_log_id: Optional[int] = None


class F0ApproveRequest(BaseModel):
    """POST /api/v1/cases/{case_id}/pipeline/feature/0/approve"""

    model_config = ConfigDict(extra="ignore")

    approver_id: str = Field(..., description="승인자 사용자 id")
    approved_at: datetime = Field(..., description="담당자 클라이언트 시각 (UTC)")
    signature: Optional[str] = Field(
        None, description="전자서명 (base64 이미지 또는 해시)"
    )


class F0ApproveResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    case_id: str
    status: PipelineStepStatus = Field(
        ..., description="'approved' 로 전이 (feature flag on 기준)"
    )
    approved_at: datetime
    audit_log_id: int


# ============================================================
# HITL-1: 불확실 원재료 / 자동 판정 불가 항목 (05번 §4)
# ============================================================


class IngredientDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="원재료명 (unidentified 리스트에서)")
    decision: Literal["allow", "deny", "skip"] = Field(
        ..., description="담당자 판정"
    )
    alternative_name: Optional[str] = Field(
        None, description="대체명 제안 (skip 시 재조회 key)"
    )
    note: Optional[str] = Field(None, description="담당자 메모")


class ConditionalResolution(BaseModel):
    """조건부 원재료의 사용 조건 평가 결과."""

    model_config = ConfigDict(extra="ignore")

    ingredient_name: str
    meets_condition: bool = Field(
        ..., description="True → 조건 부합으로 허용, False → 조건 불충족으로 금지"
    )
    reasoning: str = Field(..., min_length=1, description="조건 부합/불충족 사유")


class QualitativeResolution(BaseModel):
    """비수치 기준값(성상·확인시험 등) 담당자 판정."""

    model_config = ConfigDict(extra="ignore")

    ingredient_name: str
    test_category: str = Field(..., description="T_KOR_NM 값")
    resolution: Literal["pass", "fail", "unknown"]
    note: Optional[str] = None


class HITL1DecisionsRequest(BaseModel):
    """POST /api/v1/cases/{case_id}/pipeline/feature/1/hitl1-decisions"""

    model_config = ConfigDict(extra="ignore")

    ingredient_decisions: list[IngredientDecision] = Field(default_factory=list)
    conditional_resolutions: list[ConditionalResolution] = Field(
        default_factory=list
    )
    qualitative_resolutions: list[QualitativeResolution] = Field(
        default_factory=list
    )
    escalation_acknowledgements: list[str] = Field(
        default_factory=list,
        description="에스컬레이션 사유 코드 목록 (모든 사유 ack 해야 HITL-2 진행 가능)",
    )
    reviewer_id: str


class HITL1DecisionsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    case_id: str
    status: PipelineStepStatus = Field(
        ..., description="모든 에스컬레이션 ack 시 'waiting_review', 미완 시 'needs_review' 유지"
    )
    unresolved_escalations: list[str] = Field(
        default_factory=list, description="ack 되지 않은 사유 목록"
    )
    audit_log_id: int


# ============================================================
# HITL-2: 최종 판정 확정 (05번 §5)
# ============================================================


UserVerdict = Literal["수입가능", "수입불가", "보류"]


class HITL2ConfirmRequest(BaseModel):
    """POST /api/v1/cases/{case_id}/pipeline/feature/1/confirm"""

    model_config = ConfigDict(extra="ignore")

    user_verdict: UserVerdict
    final_reason: str = Field(..., min_length=10, description="판정 사유 (최소 10자)")
    selected_citations: list[str] = Field(
        default_factory=list,
        description="Step D chunk_id 중 판정 근거로 채택할 것 (0건 허용)",
    )
    signer_id: str
    signed_at: datetime


class HITL2ConfirmResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    case_id: str
    status: PipelineStepStatus = Field(..., description="'confirmed' 또는 'locked'")
    final_verdict: UserVerdict
    signed_at: datetime
    audit_log_id: int
