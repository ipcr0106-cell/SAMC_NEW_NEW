"""Step C — 기준규격 수치 비교 서비스 (Day 0 스켈레톤).

본 파일의 `run_step_c` 시그니처는 **Wave 2 Day 0에 동결**되었다.
W2-C 트랙(opus)이 본체를 구현하되 시그니처는 유지한다.

참조:
    - 계획/f1 재설계 계획/03_Step_C_기준규격_설계.md ⭐
    - 계획/f1 재설계 계획/06_API_클라이언트_설계.md (15116583)
    - 계획/f1 재설계 계획/11_단위_정규화_모듈_설계.md (W1-D unit_converter)
    - calling: backend/services/feature1.py `run_feature1_v2`
"""

from __future__ import annotations

from typing import Any, Optional

from models.f1_types import MeasuredValue, StepCResult
from models.judgment import Ingredient


async def run_step_c(
    ingredients: list[Ingredient],
    food_type_hierarchy: Any = None,
    measured_values: Optional[dict[str, MeasuredValue]] = None,
) -> StepCResult:
    """원재료당 15116583 기준규격 조회 → T_KOR_NM별 집계 → 수치 비교.

    Args:
        ingredients: Step B 통과한 원재료 목록 (allow_verdict 반영).
        food_type_hierarchy: F2 확정 식품유형 계층 (Any — F2 타입 의존성 회피).
            없으면 Step C 는 식품유형 한정 기준을 공통으로 간주.
        measured_values: 원재료명 → 실측값. None 이면 비교 스킵하고 기준만 표시.

    Returns:
        StepCResult — overall_status + StandardCheck 리스트.

    Day 0 스켈레톤: W2-C 트랙이 다음을 구현한다:
        - 원재료당 15116583 API 호출 (병렬, numOfRows=50 + pageNo 순회)
        - `T_KOR_NM` 기준 `defaultdict[list[AdditiveSpec]]` 집계
        - `VALD_END_DT` 유효기간 필터 (99991231 = 무기한)
        - `MIMM_VAL`/`MXMM_VAL` 우선, 실패 시 `SPEC_VAL` 파싱
        - W1-D `unit_converter.normalize_to_common_unit` 통합 (비중 참조)
        - `SPEC_VAL_SUMUP`/`FNPRT_ITM_NM` 식품유형 매칭
        - `overall_status` 규칙: pass/fail/review_needed/no_data
        - INJRY_YN=Y 경고 플래그
    """
    raise NotImplementedError("W2-C 트랙이 구현")
