"""data.go.kr 공공 API 통합 클라이언트 — Day 0 인터페이스 스켈레톤.

본 파일의 `DataGoKrClient` 클래스 시그니처(생성자 + 4개 공개 메서드)는 **Wave 1
Day 0에 동결**되었다. W1-A 트랙이 본체를 구현하되 **시그니처는 유지**한다. 변경이
필요하면 부모 세션 재협상 후 4 트랙 전원 동의 필요.

참조:
    - 계획/f1 재설계 계획/06_API_클라이언트_설계.md §3, §5
    - backend/models/f1_types.py `DataGoKrEndpoint`
"""

from __future__ import annotations

from typing import Any, Optional


class DataGoKrClient:
    """data.go.kr 4종 엔드포인트 통합 클라이언트.

    Day 0에는 생성자와 4개 공개 메서드의 시그니처만 정의한다. W1-A가 다음을
    채운다:
      - 캐시 레이어 (Supabase `f1_data_go_kr_cache`)
      - 재시도 정책 (exponential backoff, 429/500/503)
      - Circuit Breaker 통합 (W1-C 구현 import)
      - 응답 정규화 + `DataGoKrError` 계열 예외 매핑
    """

    def __init__(
        self,
        api_key: str,
        *,
        timeout_s: float = 15.0,
        max_retries: int = 3,
    ) -> None:
        """Day 0 동결 생성자.

        Args:
            api_key: F1_DATA_GO_KR_API_KEY (환경변수). 4 엔드포인트 공용.
            timeout_s: HTTP 요청 타임아웃 (초). 기본 15초.
            max_retries: 재시도 횟수. 기본 3회 (backoff 정책은 W1-A 확정).
        """
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.max_retries = max_retries

    async def get_food_raw_material(self, name: str) -> dict[str, Any]:
        """15111913 FoodRwmtInfo — 식품 원재료 정보 + GMO 플래그 조회.

        Step B(GMO 확인)·Step A(금지원료 교차 확인)에서 사용.
        """
        raise NotImplementedError("W1-A 트랙이 구현")

    async def get_import_food_ingredient(self, name: str) -> dict[str, Any]:
        """15111777 IprtFoodIngdInfoService — 수입식품 원료 허용여부·조건 조회.

        Step B(원재료 매칭) 기본 경로. `EDIBLE_INFO`, `CHRTR_INFO_CONT` 반환.
        """
        raise NotImplementedError("W1-A 트랙이 구현")

    async def get_additive_standard(self, name: str) -> dict[str, Any]:
        """15116583 FoodWStndStusService — 식품첨가물 기준규격 조회.

        Step C(기준규격 평가)에서 `T_KOR_NM`별 함량/성상/순도 기준 수집.
        """
        raise NotImplementedError("W1-A 트랙이 구현")

    async def get_import_food_component(self, name: str) -> dict[str, Any]:
        """15094202 IprtFoodCpntCdInfoFoodService — 수입식품 성분코드 조회.

        Step B(성분코드 보강). 한/영/이명 → `CPNT_CD` 1건 매칭.
        """
        raise NotImplementedError("W1-A 트랙이 구현")
