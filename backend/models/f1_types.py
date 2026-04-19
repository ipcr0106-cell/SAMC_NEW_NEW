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
