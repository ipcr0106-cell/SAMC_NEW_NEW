"""F1 재설계 신규 타입 정의 (Pydantic v2) — Wave 1 W1-B 확장.

본 파일의 `F1Output` 핵심 필드와 `DataGoKrEndpoint` Enum은 **Wave 1 Day 0에
동결**되었다. W1-A/B/C/D 4 트랙이 공통 참조한다. 필드 추가는 허용되나 **기존 필드
이름/타입 변경은 금지**한다.

⚠️  네이밍 이관 (code-review MEDIUM-5): Day 0 클래스명은 `Feature1Output` 이었으나
`models/judgment.py` 의 레거시 `Feature1Output` 과 **이름 충돌** 발생. Wave 1 내에서
`F1Output` 으로 rename 하고 하위 호환을 위해 `Feature1Output = F1Output` alias 를
유지한다. Wave 2 이후 alias 제거 예정.

W1-B 확장 (Wave 1):
    - `StandardCheck` 신규 모델 (07번 §2-4)
    - `F1Output` 확장 필드 3종 (07번 §2-3)
    - `Ingredient` 신규 필드 6종 → judgment.py 에 추가됨 (본 파일 미포함)

참조:
    - 계획/f1 재설계 계획/06_API_클라이언트_설계.md §4
    - 계획/f1 재설계 계획/07_데이터_모델_변경_설계.md §2-3, §2-4
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class DataGoKrEndpoint(str, Enum):
    """data.go.kr 4종 엔드포인트 식별자 (Day 0 동결).

    값은 data.go.kr 포털의 데이터셋 id이며, URL·파라미터 세부는
    `backend/services/data_go_kr/endpoints.py`에 정의한다.
    """

    FOOD_RAW_MATERIAL = "15111913"       # FoodRwmtInfo/getFoodRwmtInfo — 식품 원재료 + GMO
    IMPORT_FOOD_INGREDIENT = "15111777"  # IprtFoodIngdInfoService — 수입식품 원료 허용여부
    ADDITIVE_STANDARD = "15116583"       # FoodWStndStusService — 식품첨가물 기준규격
    IMPORT_FOOD_COMPONENT = "15094202"   # IprtFoodCpntCdInfoFoodService — 수입식품 성분코드


class StandardCheck(BaseModel):
    """Step C 기준규격 검사 결과 단위 — 07번 §2-4 필드 정비 적용.

    `test_category`는 data.go.kr `T_KOR_NM` 값 그대로 수록.
    `spec_raw` / `spec_summary` 는 각각 `SPEC_VAL` / `SPEC_VAL_SUMUP` 원본.
    `unit_original` / `unit_normalized` 는 W1-D `unit_converter` 가 분리 채운다.
    """

    model_config = ConfigDict(extra="ignore")

    ingredient_name: str = Field(..., description="원재료명 (T_KOR_NM 기준)")
    test_category: Optional[str] = Field(
        None,
        description="검사 항목 분류 (T_KOR_NM 값: '함량', '성상', '확인시험', '순도시험' 등)",
    )
    spec_raw: Optional[str] = Field(None, description="기준·규격 원본 텍스트 (SPEC_VAL)")
    spec_summary: Optional[str] = Field(
        None,
        description="기준·규격 요약 (SPEC_VAL_SUMUP, 식품유형 필터 시 사용)",
    )
    actual_value: Optional[str] = Field(
        None, description="실제 측정값 (문자열, 단위 포함 가능)"
    )
    unit_original: Optional[str] = Field(None, description="원본 단위 (예: 'mg/kg')")
    unit_normalized: Optional[str] = Field(
        None, description="정규화 단위 (W1-D unit_converter 출력)"
    )
    threshold_value: Optional[float] = Field(
        None, description="기준치 수치 (정규화 단위 기준, None=규격 없음)"
    )
    is_dangerous: Optional[bool] = Field(
        None, description="위해 여부 (INJRY_YN='Y' → True, 'N' → False, 미확인 → None)"
    )
    status: Literal["pass", "fail", "review_needed", "no_data"] = Field(
        "no_data", description="검사 결과 상태"
    )
    law_ref: Optional[str] = Field(None, description="근거 법령 참조")


class F1Output(BaseModel):
    """F1 (수입판정) 최종 출력 — Day 0 핵심 필드 동결 + W1-B 확장 필드.

    Day 0 동결 필드 6종 (이름·타입 변경 금지):
        verdict, confidence, evidence_laws, evidence_external_data,
        unit_conversions, warnings

    W1-B 추가 필드 3종 (07번 §2-3):
        gmo_ingredients, api_call_stats, data_source_versions

    네임 이관: Day 0 클래스명 `Feature1Output` 에서 rename (judgment.py 레거시와
    충돌 회피). 아래 `Feature1Output = F1Output` alias 로 하위 호환 유지.
    """

    model_config = ConfigDict(extra="allow")

    # ── Day 0 동결 필드 (변경 금지) ──────────────────────────────
    verdict: str = Field(
        ..., description="판정 결과: permitted|restricted|prohibited|needs_review"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="판정 신뢰도 0~1")
    evidence_laws: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Step D 법령 인용 결과 (네임스페이스·문서·점수)",
    )
    evidence_external_data: list[dict[str, Any]] = Field(
        default_factory=list,
        description="data.go.kr 4 API 응답 요약 (endpoint_id별)",
    )
    unit_conversions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Step C 단위 정규화 이력 (원본/정규화 단위·값)",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="HITL-1 에스컬레이션 사유 누적 (escalations)",
    )

    # ── W1-B 확장 필드 (07번 §2-3) ──────────────────────────────
    gmo_ingredients: list[str] = Field(
        default_factory=list,
        description="GMO=Y 판정 원재료명 리스트 (F3 전달용)",
    )
    api_call_stats: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "endpoint_id별 API 호출 건수 (감사 추적). "
            "예: {'15111777': 3, '15094202': 1}"
        ),
    )
    data_source_versions: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "각 API의 최신 스냅샷 메타 (감사 대비). "
            "예: {'15111777': '2024-03-01'}. "
            "값은 LAST_UPDT_DTM 또는 해시"
        ),
    )


# ------------------------------------------------------------------
# Deprecated alias — Day 0 호환 유지 (code-review MEDIUM-5 대응)
# Wave 2 이후 제거 예정. 신규 코드는 `F1Output` 을 사용할 것.
# `models.judgment.Feature1Output` (레거시) 와 이름이 충돌하므로 본 alias 를
# import 해 사용하는 경로는 `from models.f1_types import Feature1Output` 로
# 명시적 경로를 쓸 때만 유효.
# ------------------------------------------------------------------
Feature1Output = F1Output


# ==================================================================
# Wave 2 Day 0 — Step A/B/C/D 결과 타입 (시그니처 동결)
# 설계 참조: 계획/f1 재설계 계획/01~04_Step_*_설계.md
# W2-A/B/C/D 각 트랙은 아래 Result 타입의 **필드 이름/타입을 유지**한 채
# 본체만 구현한다. 필드 추가는 허용, 이름·타입 변경 금지.
# ==================================================================


class ForbiddenHit(BaseModel):
    """Step A 금지원료 매칭 결과 1건 (01번 §2)."""

    model_config = ConfigDict(extra="ignore")

    ingredient_name: str = Field(..., description="F0 입력 원재료명")
    matched_name: str = Field(..., description="DB/API 상의 금지원료명")
    source: Literal["db", "api"] = Field(..., description="매칭 출처")
    reason: str = Field(..., description="금지 사유 (법령·조문 요약)")
    law_ref: Optional[str] = Field(None, description="근거 법령 식별자")


class StepAResult(BaseModel):
    """Step A 금지원료 체크 결과 (01번 §2)."""

    model_config = ConfigDict(extra="ignore")

    forbidden_hits: list[ForbiddenHit] = Field(
        default_factory=list,
        description="매칭된 금지원료 (DB + API 합집합)",
    )
    stopped: bool = Field(
        False,
        description="True → 파이프라인 즉시 종료 (Step B/C/D skip)",
    )
    law_refs: list[str] = Field(
        default_factory=list,
        description="금지 근거 법령 식별자 목록",
    )
    api_errors: list[str] = Field(
        default_factory=list,
        description="15111777 API 호출 실패 기록 (차단 없음)",
    )


class StepBResult(BaseModel):
    """Step B 원재료 허용여부 + 성분코드 + GMO 결과 (02번 §2).

    `enriched_ingredients` 는 `models.judgment.Ingredient` 인스턴스 리스트.
    순환 import 회피를 위해 `arbitrary_types_allowed=True` 로 선언한다.
    """

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=True)

    enriched_ingredients: list[Any] = Field(
        default_factory=list,
        description="allow_verdict·component_code·is_gmo 가 채워진 Ingredient 목록",
    )
    unidentified: list[str] = Field(
        default_factory=list,
        description="API 매칭 실패 원재료명 (HITL-1 대상)",
    )
    conditional: list[Any] = Field(
        default_factory=list,
        description="restricted 원재료 (HITL-1 표시)",
    )
    gmo_ingredients: list[str] = Field(
        default_factory=list,
        description="GMO=Y 판정 원재료명 (F3 전달)",
    )
    api_call_stats: dict[str, int] = Field(
        default_factory=dict,
        description="endpoint_id별 호출 건수 (감사)",
    )


class MeasuredValue(BaseModel):
    """Step C 실측값 입력 단위 (03번 §2).

    F4 라벨 OCR 또는 HITL-0 담당자 입력에서 채워진다.
    """

    model_config = ConfigDict(extra="ignore")

    value: float = Field(..., description="원본 수치")
    unit: str = Field(..., description="원본 단위 (예: '%', 'mg/kg')")
    source: str = Field(
        ...,
        description="입력 경로: 'label_ocr' / 'hitl_input' / 'manual' 등",
    )


class StepCResult(BaseModel):
    """Step C 기준규격 수치 비교 결과 (03번 §2)."""

    model_config = ConfigDict(extra="ignore")

    checks: list[StandardCheck] = Field(
        default_factory=list,
        description="원재료 × 시험항목 조합별 StandardCheck 목록",
    )
    overall_status: Literal["pass", "fail", "review_needed", "no_data"] = Field(
        "no_data",
        description="전체 Step C 판정: 모든 pass → pass, 하나라도 fail → fail",
    )
    review_reasons: list[str] = Field(
        default_factory=list,
        description="review_needed 사유 (qualitative·자동 판정 불가 등)",
    )


class LawCitation(BaseModel):
    """Step D 법령 인용 1건 (04번 §3).

    원문 인용만 — LLM 해석·판정 주도 금지.
    """

    model_config = ConfigDict(extra="ignore")

    chunk_id: str = Field(..., description="Pinecone 청크 id")
    law_name: str = Field(..., description="법령명 (예: 식품위생법)")
    article_no: Optional[str] = Field(None, description="조·항 번호 (예: 제27조)")
    text: str = Field(..., description="원문 텍스트 (편집 금지)")
    score: float = Field(..., description="Pinecone 유사도 점수 0~1")
    namespace: str = Field(
        ...,
        description=(
            "Pinecone namespace: additive_code_text / food_code_text / "
            "health_food_text / temporary_standard / functional_labeling"
        ),
    )


class QueryContext(BaseModel):
    """Step D Pinecone 검색 쿼리 컨텍스트 (04번 §4)."""

    model_config = ConfigDict(extra="ignore")

    food_type: Optional[str] = Field(None, description="F2 확정 식품유형")
    forbidden_hits: list[ForbiddenHit] = Field(
        default_factory=list,
        description="Step A 결과",
    )
    restricted_ingredients: list[str] = Field(
        default_factory=list,
        description="Step B restricted 원재료명",
    )
    failed_standards: list[str] = Field(
        default_factory=list,
        description="Step C fail 항목 (원재료명 + 시험항목)",
    )


class StepDResult(BaseModel):
    """Step D 법령 인용 결과 (04번 §3).

    판정 주도 없음 — 프론트 `LawCitationList` 에 표시 전용.
    """

    model_config = ConfigDict(extra="ignore")

    citations: list[LawCitation] = Field(
        default_factory=list,
        description="점수 상위 5건 법령 청크 (5 namespace 병렬 검색 후 merge)",
    )
