"""기능1 판정 결과 타입 정의 (Pydantic v2).

출처:
    - newsamc src/types/judgment.ts
    - newsamc src/types/review-context.ts (Ingredient)
    - 계획/기능1_참고자료/02_매칭체인_5단계.md §2

네이밍:
    개발계획서 + 팀컨벤션 §5 준수 (snake_case).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ============================================================
# 타입 별칭
# ============================================================

IngredientVerdict = Literal["permitted", "restricted", "prohibited", "unidentified"]
MatchMethod = Literal[
    "exact_name",
    "ins_number",
    "cas_number",
    "scientific_name",
    "fuzzy",
    "llm_normalize",
]
ConditionType = Literal[
    "usage_purpose",
    "part_restriction",
    "quantity_limit",
    "natural_synthetic",
    "irradiation",
    "ambiguous",
]
LimitCheckStatus = Literal["pass", "fail", "warning", "no_data"]
LimitCategory = Literal[
    "additive", "heavy_metal", "microbe", "pesticide", "alcohol", "contaminant"
]
# F1 재설계 allow_verdict 값 집합 (07번 §2-1, W1-B 추가).
# 주의: 기존 IngredientVerdict ("permitted"|"restricted"|"prohibited"|"unidentified") 와
#        allow_verdict ("allowed"|"restricted"|"prohibited"|"unidentified") 는 의미상 동일하나
#        네이밍이 다르다. "permitted" ↔ "allowed" 매핑이 필요한 경우
#        Step B(W2-B)에서 변환하여 채운다. 이 파일에서는 07번 사양 그대로 snake_case 유지.
AllowVerdict = Literal["allowed", "restricted", "prohibited", "unidentified"]


# ============================================================
# 입력 타입
# ============================================================


class Ingredient(BaseModel):
    """원재료 입력 단위 — W1-B 신규 필드 6종 추가 (07번 §2-1)."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="원재료명(한국어 또는 학명/영문)")
    name_original: Optional[str] = Field(None, description="원문 원재료명 (번역 전) — 현재 미사용, LLM 정규화 원본 추적용으로 예약")
    percentage: Optional[float] = Field(None, description="함량 비율 (%)")
    ins: Optional[str] = Field(None, description="INS 번호")
    cas: Optional[str] = Field(None, description="CAS 번호")
    chemical_name: Optional[str] = Field(None, description="화학성분명 — 현재 미사용, DB 매칭 실패 시 화학명 재검색용으로 예약")
    part: Optional[str] = Field(None, description="사용 부위 (잎, 뿌리 등)")
    is_allergen: Optional[bool] = Field(None, description="라벨상 알레르겐 표시 여부 — 현재 미사용, F3 연동용으로 예약")
    sub_ingredients: Optional[list["Ingredient"]] = Field(
        None, description="복합원재료 하위 성분"
    )

    # ── W1-B 신규 필드 (07번 §2-1) ──────────────────────────────
    component_code: Optional[str] = Field(
        None,
        description="15094202 성분코드 CPNT_CD (UI 표시·감사 추적용)",
    )
    allow_verdict: Optional[AllowVerdict] = Field(
        None,
        description=(
            "Step B 매칭 결과 판정값. "
            "매핑: 'allowed'=허용, 'restricted'=조건부, 'prohibited'=금지, 'unidentified'=미확인. "
            "기존 IngredientVerdict의 'permitted'는 'allowed'에 대응 (Step B에서 변환)."
        ),
    )
    restriction_condition: Optional[str] = Field(
        None,
        description="조건부 허용 조건 텍스트 (CHRTR_INFO_CONT, HITL-1 표시용)",
    )
    edible_parts: Optional[str] = Field(
        None,
        description="식용 가능 부위 (EDIBLE_USE_CONT)",
    )
    is_gmo: Optional[bool] = Field(
        None,
        description="GMO 여부 (15111913 GMO_YN 조회 결과, True=GMO, False=non-GMO, None=미조회)",
    )
    source_api: Optional[str] = Field(
        None,
        description="매칭된 API endpoint_id (감사 추적, DataGoKrEndpoint 값 또는 'db')",
    )

    # ── P6 추가 (2026-04-20) — 원재료 매칭 상세 컬럼 채움용 ───────────
    matched_name_ko: Optional[str] = Field(
        None,
        description="F0 성분코드 조회로 도출된 한글 표준명 (IngredientItem.ingredient_code_name)",
    )
    ingredient_code_f0: Optional[str] = Field(
        None,
        description="F0 식약처 성분코드 (IngredientItem.ingredient_code, 예: A1000911320001)",
    )
    match_method: Optional[str] = Field(
        None,
        description="F0 매칭 방법 추론: 'exact_name' | 'code_normalize' | None(=미매칭)",
    )
    law_source: Optional[str] = Field(
        None,
        description="Step B verdict 도출 근거 법령 (예: '식품의 기준 및 규격 [별표 3]')",
    )


class ProcessConditions(BaseModel):
    """제조공정 조건."""

    model_config = ConfigDict(extra="ignore")

    is_heated: Optional[bool] = None
    is_fermented: Optional[bool] = None  # 현재 미사용 — 발효식품 전용 기준치 분기 예약
    is_distilled: Optional[bool] = None
    alcohol_percentage: Optional[float] = None
    ph_value: Optional[float] = None  # 현재 미사용 — pH 기반 기준치 분기 예약 (예: 산성식품 pH 4.6 이하)


class Feature1Input(BaseModel):
    """기능1 입력 페이로드."""

    model_config = ConfigDict(extra="ignore")

    case_id: Optional[str] = None
    ingredients: list[Ingredient]
    food_type: Optional[str] = Field(None, description="기능2(아람) 확정 식품유형")
    process_conditions: ProcessConditions = Field(default_factory=ProcessConditions)


# ============================================================
# 매칭 체인 결과
# ============================================================


class IngredientMatchResult(BaseModel):
    """개별 원재료 매칭 결과."""

    ingredient: Ingredient
    verdict: IngredientVerdict
    match_method: Optional[MatchMethod] = None
    matched_db_id: Optional[str] = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    conditions: Optional[str] = Field(None, description="restricted 시 조건 텍스트")
    matched_name_ko: Optional[str] = Field(None, description="DB 상 공식 한국어명")
    law_source: Optional[str] = None


class AggregationResult(BaseModel):
    """Step 1 집계 결과."""

    total: int
    permitted: int
    restricted: int
    prohibited: int
    unidentified: int
    results: list[IngredientMatchResult]
    escalations: list[dict] = Field(default_factory=list)


# ============================================================
# 조건부(restricted) 평가
# ============================================================


class ConditionalEvaluation(BaseModel):
    """restricted 원료의 조건 평가 결과."""

    ingredient_name: str
    condition_type: ConditionType
    condition_description: str
    is_satisfied: Optional[bool] = Field(None, description="None=담당자 확인 필요")
    evidence: Optional[str] = None


# ============================================================
# 기준치 검증 (Step 3)
# ============================================================


class LimitCheckResult(BaseModel):
    """개별 기준치 검증 결과."""

    item_name: str
    category: LimitCategory
    max_limit: str = Field(..., description='"0.6 g/kg" 또는 "불검출" 등 TEXT')
    actual_value: Optional[str] = None
    status: LimitCheckStatus
    regulation_ref: Optional[str] = None


class CompoundGroupResult(BaseModel):
    """복합 합산 그룹 검증 결과."""

    group: str
    members: list[str]
    total: float
    limit: float
    unit: str
    status: LimitCheckStatus
    law_ref: Optional[str] = None


class StandardsCheckResult(BaseModel):
    """기준치 검증 통합."""

    food_type: Optional[str] = None
    overall_status: Literal["pass", "fail", "review_needed"]
    checks: list[LimitCheckResult] = Field(default_factory=list)
    compound_results: list[CompoundGroupResult] = Field(default_factory=list)
    violations: list[LimitCheckResult] = Field(default_factory=list)
    escalations: list[dict] = Field(default_factory=list)


# ============================================================
# 기능1 최종 출력
# ============================================================


class ForbiddenHit(BaseModel):
    """Step 0 금지원료 적중."""

    name_ko: str
    category: Literal["drug", "endangered", "unauthorized", "toxin", "other"]
    law_source: Optional[str] = None
    reason: Optional[str] = None


class LawReference(BaseModel):
    law_source: str
    law_article: Optional[str] = None


class Feature1Output(BaseModel):
    """기능1 최종 결과 — pipeline_steps.ai_result JSONB 저장 대상."""

    model_config = ConfigDict(extra="ignore")

    import_possible: Optional[bool] = None
    verdict: str = Field(..., description="수입가능/수입불가/검토필요 + 한국어 사유")
    aggregation: Optional[AggregationResult] = None
    conditional_evaluations: list[ConditionalEvaluation] = Field(default_factory=list)
    standards_check: Optional[StandardsCheckResult] = None
    forbidden_hits: list[ForbiddenHit] = Field(default_factory=list)
    # H-NEW-1: 합성향료 원재료 이름 리스트. features.py 가 status=synthetic_flavor_warning 매핑에 사용.
    synthetic_flavor_ingredients: list[str] = Field(default_factory=list)
    escalations: list[dict] = Field(default_factory=list)
    law_refs: list[LawReference] = Field(default_factory=list)


Ingredient.model_rebuild()
