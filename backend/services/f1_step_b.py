"""Step B — 원재료 허용여부 + 성분코드 + GMO 서비스 (Day 0 스켈레톤).

본 파일의 `run_step_b` 시그니처는 **Wave 2 Day 0에 동결**되었다.
W2-B 트랙(opus)이 본체를 구현하되 시그니처는 유지한다.

참조:
    - 계획/f1 재설계 계획/02_Step_B_원재료_매칭_설계.md ⭐
    - 계획/f1 재설계 계획/06_API_클라이언트_설계.md (15111777/15094202/15111913)
    - calling: backend/services/feature1.py `run_feature1_v2`
"""

from __future__ import annotations

from models.f1_types import StepBResult
from models.judgment import Ingredient


async def run_step_b(ingredients: list[Ingredient]) -> StepBResult:
    """3개 API 병렬 호출 → 원재료별 allow_verdict·component_code·is_gmo 집계.

    Args:
        ingredients: Step A 통과한 원재료 목록 (sub_ingredients 평탄화 상태).

    Returns:
        StepBResult — enriched_ingredients 에 채워진 Ingredient 인스턴스 반환.
        prohibited 발견 시 호출자(`run_feature1_v2`) 가 조기 종료.

    Day 0 스켈레톤: W2-B 트랙이 다음을 구현한다:
        - `normalize_name(raw)` 공백/구분자 정규화
        - 15111777·15094202·15111913 `asyncio.gather` 병렬
        - `resolve_verdict()` prohibited > restricted > allowed 안전측 채택
        - 15094202 `KOR_NM` 앞 공백 strip + 첨가물/식품원료 우선순위
        - 15111913 GMO 정확 일치만 (퍼지 금지)
        - Levenshtein fallback 자동 확정 금지 → unidentified → HITL-1
        - `prohibited` 검출 시 조기 종료 시그널 (호출자가 Step C/D skip)
    """
    raise NotImplementedError("W2-B 트랙이 구현")
