"""F1 재설계 신규 타입 정의 (Pydantic v2) — Day 0 인터페이스 스켈레톤.

본 파일의 `Feature1Output` 핵심 필드와 `DataGoKrEndpoint` Enum은 **Wave 1 Day 0에
동결**되었다. W1-A/B/C/D 4 트랙이 공통 참조한다. 필드 추가는 허용되나 **기존 필드
이름/타입 변경은 금지**한다.

참조:
    - 계획/f1 재설계 계획/06_API_클라이언트_설계.md §4
    - 계획/f1 재설계 계획/07_데이터_모델_변경_설계.md §2-3
"""

from __future__ import annotations

from enum import Enum
from typing import Any

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


class Feature1Output(BaseModel):
    """F1 (수입판정) 최종 출력 — Day 0 핵심 필드 동결.

    W1-B 트랙이 07번 문서 §2-3에 따라 `gmo_ingredients`, `api_call_stats`,
    `data_source_versions` 등 확장 필드를 추가한다. 본 스켈레톤의 6개 핵심 필드는
    **이름·타입 유지**가 강제된다.
    """

    model_config = ConfigDict(extra="allow")

    verdict: str = Field(..., description="판정 결과: permitted|restricted|prohibited|needs_review")
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
