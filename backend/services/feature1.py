"""기능1 통합 엔트리 — Step 0 + Step 1 + Step 3 오케스트레이션.

담당: 병찬
참고: 계획/기능1_구현계획/00_마스터_로드맵.md §2 DAG

흐름:
    run_feature1(db, ingredients, food_type?, process_conditions)
      ├── check_forbidden_first (Step 0)
      │     └── hit → 즉시 종료
      ├── run_step1 (Step 1 + 1-A + 1-B)
      │     └── prohibited / 조건 불충족 → 종료
      └── run_step3 (일반+주류 기준치)

호출 컨텍스트:
    - 공통 인프라 담당의 routers/pipeline.py 에서 호출
    - pipeline_steps.ai_result JSONB 로 저장
"""

from __future__ import annotations

from typing import Optional

import asyncpg

from models.judgment import (Feature1Output, Ingredient, LawReference,
                                     ProcessConditions)
from services.step1_ingredients_check import run_step1
from services.step3_standards import run_step3


async def run_feature1(
    db: asyncpg.Connection,
    ingredients: list[Ingredient],
    food_type: Optional[str] = None,
    process_conditions: Optional[ProcessConditions] = None,
) -> Feature1Output:
    """기능1 통합 실행.

    Args:
        db: asyncpg 커넥션
        ingredients: 원재료 목록 (정보입력 단계 출력)
        food_type: 기능2(아람) 확정 식품유형 — None이면 Step 3 review_needed 처리
        process_conditions: 가열·발효·증류·도수 플래그

    Returns:
        Feature1Output — pipeline_steps.ai_result 에 저장될 최종 결과
    """
    process = process_conditions or ProcessConditions()

    # ── Step 0 + 1 + 1-A + 1-B ────────────────────────────
    step1_result = await run_step1(db, ingredients)

    # Step 0 적중 → 즉시 종료
    if step1_result.get("stopped_at") == "step0":
        return Feature1Output(
            import_possible=False,
            verdict=step1_result["verdict"],
            forbidden_hits=[
                h
                for h in [
                    __to_forbidden_hit(x)
                    for x in step1_result.get("forbidden_hits", [])
                ]
                if h
            ],
            synthetic_flavor_ingredients=step1_result.get(
                "synthetic_flavor_ingredients", []
            ),
            escalations=step1_result.get("escalations", []),
            law_refs=_collect_law_refs_from_forbidden(step1_result),
        )

    # Step 1/1-B 조기 종료 (prohibited 또는 조건 불충족)
    if step1_result.get("stopped_at") in ("step1", "step1b"):
        return Feature1Output(
            import_possible=False,
            verdict=step1_result["verdict"],
            aggregation=step1_result.get("aggregation"),
            conditional_evaluations=step1_result.get("conditional_evaluations", []),
            synthetic_flavor_ingredients=step1_result.get(
                "synthetic_flavor_ingredients", []
            ),
            escalations=step1_result.get("escalations", []),
            law_refs=_collect_law_refs_from_aggregation(step1_result),
        )

    # ── Step 3 ────────────────────────────────────────────
    standards = await run_step3(db, ingredients, food_type, process)

    # 최종 판정
    escalations = list(step1_result.get("escalations", [])) + list(
        standards.escalations
    )
    law_refs = _collect_law_refs_from_aggregation(step1_result)
    law_refs.extend(_collect_law_refs_from_checks(standards))

    synthetic_names = step1_result.get("synthetic_flavor_ingredients", [])

    if standards.overall_status == "fail":
        return Feature1Output(
            import_possible=False,
            verdict="수입불가 — 기준치 초과",
            aggregation=step1_result.get("aggregation"),
            conditional_evaluations=step1_result.get("conditional_evaluations", []),
            synthetic_flavor_ingredients=synthetic_names,
            standards_check=standards,
            escalations=escalations,
            law_refs=_dedup_law_refs(law_refs),
        )

    if standards.overall_status == "review_needed":
        return Feature1Output(
            import_possible=False,  # 자동 통과 금지
            verdict="검토 필요 — 기준치 데이터 부족 또는 경계치",
            aggregation=step1_result.get("aggregation"),
            conditional_evaluations=step1_result.get("conditional_evaluations", []),
            synthetic_flavor_ingredients=synthetic_names,
            standards_check=standards,
            escalations=escalations,
            law_refs=_dedup_law_refs(law_refs),
        )

    return Feature1Output(
        import_possible=True,
        verdict="수입 가능",
        aggregation=step1_result.get("aggregation"),
        conditional_evaluations=step1_result.get("conditional_evaluations", []),
        synthetic_flavor_ingredients=synthetic_names,
        standards_check=standards,
        escalations=escalations,
        law_refs=_dedup_law_refs(law_refs),
    )


# ============================================================
# 내부 헬퍼
# ============================================================


def __to_forbidden_hit(d: dict):
    try:
        from models.judgment import ForbiddenHit

        return ForbiddenHit(**d)
    except Exception:
        return None


def _collect_law_refs_from_forbidden(step1_result: dict) -> list[LawReference]:
    refs: list[LawReference] = []
    for h in step1_result.get("forbidden_hits") or []:
        if h.get("law_source"):
            refs.append(LawReference(law_source=h["law_source"]))
    return refs


def _collect_law_refs_from_aggregation(step1_result: dict) -> list[LawReference]:
    refs: list[LawReference] = []
    agg = step1_result.get("aggregation") or {}
    for r in agg.get("results", []):
        ls = r.get("law_source")
        if ls:
            refs.append(LawReference(law_source=ls))
    return refs


def _collect_law_refs_from_checks(standards) -> list[LawReference]:
    refs: list[LawReference] = []
    for c in standards.checks:
        if c.regulation_ref:
            # "식품첨가물공전 IV. 품목별 성분규격" 같은 문자열을 law_source 로만 저장
            refs.append(LawReference(law_source=c.regulation_ref))
    for cg in standards.compound_results:
        if cg.law_ref:
            refs.append(LawReference(law_source=cg.law_ref))
    return refs


def _dedup_law_refs(refs: list[LawReference]) -> list[LawReference]:
    seen: set[tuple[str, Optional[str]]] = set()
    out: list[LawReference] = []
    for r in refs:
        key = (r.law_source, r.law_article)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out
