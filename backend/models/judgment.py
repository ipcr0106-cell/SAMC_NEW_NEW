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


# ============================================================
# 입력 타입
# ============================================================


class Ingredient(BaseModel):
    """원재료 입력 단위."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="원재료명(한국어 또는 학명/영문)")
    name_original: Optional[str] = Field(None, description="원문 원재료명 (번역 전)")
    percentage: Optional[float] = Field(None, description="함량 비율 (%)")
    ins: Optional[str] = Field(None, description="INS 번호")
    cas: Optional[str] = Field(None, description="CAS 번호")
    chemical_name: Optional[str] = Field(None, description="화학성분명")
    part: Optional[str] = Field(None, description="사용 부위 (잎, 뿌리 등)")
    is_allergen: Optional[bool] = Field(None, description="라벨상 알레르겐 표시 여부")
    sub_ingredients: Optional[list["Ingredient"]] = Field(
        None, description="복합원재료 하위 성분"
    )


class ProcessConditions(BaseModel):
    """제조공정 조건."""

    model_config = ConfigDict(extra="ignore")

    is_heated: Optional[bool] = None
    is_fermented: Optional[bool] = None
    is_distilled: Optional[bool] = None
    alcohol_percentage: Optional[float] = None
    ph_value: Optional[float] = None


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

    import_possible: bool
    verdict: str = Field(..., description="수입가능/수입불가 + 한국어 사유")
    aggregation: Optional[AggregationResult] = None
    conditional_evaluations: list[ConditionalEvaluation] = Field(default_factory=list)
    standards_check: Optional[StandardsCheckResult] = None
    forbidden_hits: list[ForbiddenHit] = Field(default_factory=list)
    # H-NEW-1: 합성향료 원재료 이름 리스트. features.py 가 status=synthetic_flavor_warning 매핑에 사용.
    synthetic_flavor_ingredients: list[str] = Field(default_factory=list)
    escalations: list[dict] = Field(default_factory=list)
    law_refs: list[LawReference] = Field(default_factory=list)


Ingredient.model_rebuild()
