"""data.go.kr 4종 엔드포인트 정의 — W1-A 트랙 구현.

본 모듈은 `DataGoKrClient` 가 호출하는 4개 엔드포인트 메타데이터를 제공한다.
`DataGoKrEndpoint` Enum(Day 0 동결, `backend/models/f1_types.py`)을 key로 각
엔드포인트의 URL·기본 파라미터·기본 캐시 TTL·기본 search 파라미터 이름을 조회한다.

참조:
    - 계획/f1 재설계 계획/06_API_클라이언트_설계.md §4
    - 계획/f1 재설계 계획/F1_공공데이터_API_탐색보고서.md §2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from models.f1_types import DataGoKrEndpoint


@dataclass(frozen=True)
class Endpoint:
    """data.go.kr 엔드포인트 메타데이터.

    Attributes:
        id: 포털 데이터셋 id (예: "15111913")
        name: 사람이 읽기 쉬운 이름
        url: 전체 HTTP URL
        default_params: 공통 쿼리 파라미터 (type·numOfRows 등)
        cache_ttl_seconds: 캐시 TTL. 15116583(첨가물 기준)은 7일, 그 외 24시간
        search_param: 단순 조회용 primary 검색 파라미터 이름
                      (예: 15111777 → INGD_NM, 15094202 → KOR_NM)
    """

    id: str
    name: str
    url: str
    default_params: Dict[str, str] = field(default_factory=dict)
    cache_ttl_seconds: int = 24 * 60 * 60  # 24h default
    search_param: str = ""


# ---------------------------------------------------------------------------
# 4 endpoints — 탐색보고서 §2 기반
# ---------------------------------------------------------------------------

# 15111913 — 식품 원재료 정보 조회 (GMO)
FOOD_RAW_MATERIAL = Endpoint(
    id=DataGoKrEndpoint.FOOD_RAW_MATERIAL.value,
    name="식품 원재료 정보 조회",
    url=(
        "https://apis.data.go.kr/1471000/FoodRwmtInfo/getFoodRwmtInfo"
    ),
    default_params={"type": "json", "numOfRows": "10", "pageNo": "1"},
    cache_ttl_seconds=24 * 60 * 60,
    search_param="ORM_STD_NM",
)

# 15111777 — 수입식품 원료정보
IMPORT_FOOD_INGREDIENT = Endpoint(
    id=DataGoKrEndpoint.IMPORT_FOOD_INGREDIENT.value,
    name="수입식품 원료정보",
    url=(
        "https://apis.data.go.kr/1471000/IprtFoodIngdInfoService/"
        "getIprtFoodIngdInfoService"
    ),
    default_params={"type": "json", "numOfRows": "10", "pageNo": "1"},
    cache_ttl_seconds=24 * 60 * 60,
    search_param="INGD_NM",
)

# 15116583 — 식품첨가물 기준규격 현황
ADDITIVE_STANDARD = Endpoint(
    id=DataGoKrEndpoint.ADDITIVE_STANDARD.value,
    name="식품첨가물 기준규격 현황",
    url=(
        "https://apis.data.go.kr/1471000/FoodWStndStusService/"
        "getFoodWStndStusList"
    ),
    # T_KOR_NM 별 여러 row 분리되므로 numOfRows 크게
    default_params={"type": "json", "numOfRows": "50", "pageNo": "1"},
    cache_ttl_seconds=7 * 24 * 60 * 60,  # 7d — 거의 안 바뀜
    search_param="PC_KOR_NM",
)

# 15094202 — 수입식품 성분코드 정보
IMPORT_FOOD_COMPONENT = Endpoint(
    id=DataGoKrEndpoint.IMPORT_FOOD_COMPONENT.value,
    name="수입식품 성분코드 정보",
    url=(
        "https://apis.data.go.kr/1471000/IprtFoodCpntCdInfoFoodService/"
        "getIprtFoodCpntCdInfoFoodInq"
    ),
    default_params={"type": "json", "numOfRows": "10", "pageNo": "1"},
    cache_ttl_seconds=24 * 60 * 60,
    search_param="KOR_NM",
)


ENDPOINTS: Dict[DataGoKrEndpoint, Endpoint] = {
    DataGoKrEndpoint.FOOD_RAW_MATERIAL: FOOD_RAW_MATERIAL,
    DataGoKrEndpoint.IMPORT_FOOD_INGREDIENT: IMPORT_FOOD_INGREDIENT,
    DataGoKrEndpoint.ADDITIVE_STANDARD: ADDITIVE_STANDARD,
    DataGoKrEndpoint.IMPORT_FOOD_COMPONENT: IMPORT_FOOD_COMPONENT,
}


def get_endpoint(endpoint: DataGoKrEndpoint) -> Endpoint:
    """Enum → Endpoint 메타데이터 조회."""
    return ENDPOINTS[endpoint]


__all__ = [
    "Endpoint",
    "ENDPOINTS",
    "FOOD_RAW_MATERIAL",
    "IMPORT_FOOD_INGREDIENT",
    "ADDITIVE_STANDARD",
    "IMPORT_FOOD_COMPONENT",
    "get_endpoint",
]
