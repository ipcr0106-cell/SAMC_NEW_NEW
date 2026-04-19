"""Step A — 금지원료 체크 서비스 (Day 0 스켈레톤).

본 파일의 `run_step_a` 시그니처는 **Wave 2 Day 0에 동결**되었다.
W2-A 트랙이 본체를 구현하되 시그니처는 유지한다.

참조:
    - 계획/f1 재설계 계획/01_Step_A_금지원료_설계.md
    - 계획/f1 재설계 계획/06_API_클라이언트_설계.md (15111777)
    - calling: backend/services/feature1.py `run_feature1_v2`
"""

from __future__ import annotations

from models.f1_types import StepAResult
from models.judgment import Ingredient


async def run_step_a(ingredients: list[Ingredient]) -> StepAResult:
    """2중 안전망: Supabase `f1_forbidden_ingredients` + data.go.kr 15111777 교차.

    Args:
        ingredients: F0 원재료 목록 (sub_ingredients 포함).

    Returns:
        StepAResult — forbidden_hits 1건 이상이면 stopped=True.

    Day 0 스켈레톤: W2-A 트랙이 다음을 구현한다:
        - DB 조회 (원재료명 strip + lowercase 정규화)
        - 15111777 `lookup_ingredient` 병렬 호출
        - `EDIBLE_INFO == "불가"` / `EDIBLE_N == "o"` 필터
        - DB/API 합집합 중복 제거 (name 기준, source="db" 우선)
        - API 장애 시 api_errors 누적, DB 결과로만 판정
        - sub_ingredients 평탄화 검사
    """
    raise NotImplementedError("W2-A 트랙이 구현")
