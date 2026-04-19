"""Step D — 법령 인용 서비스 (Day 0 스켈레톤).

본 파일의 `run_step_d` 시그니처는 **Wave 2 Day 0에 동결**되었다.
W2-D 트랙이 본체를 구현하되 시그니처는 유지한다.

⚠️ Step D는 **검색 전용** — RAG 판정 주도 역할 완전 제거. LLM 해석 금지.

참조:
    - 계획/f1 재설계 계획/04_Step_D_법령인용_설계.md
    - 기존 backend/services/f1_pinecone_client.py / f1_rag_judge.py (부분 재사용)
    - 계획/f1 재설계 계획/14_병렬실행_계획.md §11-3 결정 10 (functional_labeling A')
    - calling: backend/services/feature1.py `run_feature1_v2`
"""

from __future__ import annotations

from models.f1_types import QueryContext, StepDResult


async def run_step_d(
    query_context: QueryContext,
    top_k: int = 5,
) -> StepDResult:
    """Pinecone 5 namespace 병렬 검색 → 점수 상위 top_k 건 반환.

    Args:
        query_context: Step A/B/C 결과 요약 (식품유형·금지·제한·실패 기준).
        top_k: 최종 반환 건수. 각 namespace 에서 top_k 씩 조회 후 merge 상위 top_k.

    Returns:
        StepDResult — citations (LawCitation 리스트). 판정 주도 없음.

    Day 0 스켈레톤: W2-D 트랙이 다음을 구현한다:
        - `build_query(ctx)` 쿼리 문자열 합성 (04번 §4)
        - 5 namespace 병렬 검색: additive_code_text / food_code_text /
          health_food_text / temporary_standard / functional_labeling (A')
        - 각 namespace 에서 top_k 조회 → 전체 5*top_k → score 상위 top_k merge
        - `LawCitation` 정규화 (chunk_id, law_name, article_no, text, score, namespace)
        - Pinecone 장애 시 `citations=[]` + escalations 누적, 파이프라인 계속
        - `rag_verdict` / `rag_reasoning` / `RagConflictPanel` 로직 **제거**
        - `functional_labeling` 쿼리 경로 유지 (14번 §11-3 A')
    """
    raise NotImplementedError("W2-D 트랙이 구현")
