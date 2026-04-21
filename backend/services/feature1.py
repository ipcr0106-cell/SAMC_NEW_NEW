"""기능1 통합 엔트리 — Step 0 + Step 1 + Step 3 오케스트레이션.

담당: 병찬
참고: 계획/기능1_구현계획/00_마스터_로드맵.md §2 DAG

흐름:
    run_feature1(ingredients, food_type?, process_conditions)
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

import logging
import os
from typing import Any, Optional

from common.result import Result
from models.f1_law_citation import ConflictStatus, RagJudgement
from models.f1_types import F1Output, MeasuredValue, QueryContext, StepDResult
from models.judgment import (Feature1Output, Ingredient, LawReference,
                                     ProcessConditions)
from services import f1_rag_judge
from services.step1_ingredients_check import run_step1
from services.step3_standards import run_step3

logger = logging.getLogger(__name__)


def run_feature1(
    ingredients: list[Ingredient],
    food_type: Optional[str] = None,
    process_conditions: Optional[ProcessConditions] = None,
) -> Feature1Output:
    """기능1 통합 실행.

    Args:
        ingredients: 원재료 목록 (정보입력 단계 출력)
        food_type: 기능2(아람) 확정 식품유형 — None이면 Step 3 review_needed 처리
        process_conditions: 가열·발효·증류·도수 플래그

    Returns:
        Feature1Output — pipeline_steps.ai_result 에 저장될 최종 결과
    """
    process = process_conditions or ProcessConditions()

    # ── Step 0 + 1 + 1-A + 1-B ────────────────────────────
    step1_result = run_step1(ingredients)

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
    standards = run_step3(ingredients, food_type, process)

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
            import_possible=None,  # 자동 통과 금지, 수입불가도 아님 → 담당자 검토
            verdict="검토필요",
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


# ============================================================
# RAG + HITL 통합 entry (Phase 4-B)
# ============================================================


async def _llm_judge_with_law(
    step_d, enriched, food_type, content_volume: str = "",
) -> tuple["StepDResult", str, float]:
    """LLM이 법령 + 원재료 매칭 결과를 종합하여 수입 가능 여부를 판정.

    Returns:
        (StepDResult(요약된 법령 인용), verdict, confidence)
    """
    api_key = os.environ.get("F0_OPENAI_API_KEY", "")
    if not api_key or not step_d.citations:
        return step_d, "permitted", 0.7

    # 원재료 정보 (매칭명 + 배합비율)
    ingredient_info = []
    for i in enriched:
        name = (getattr(i, "matched_name_ko", "") or "").strip() or getattr(i, "name", "")
        pct = getattr(i, "percentage", None)
        law_src = getattr(i, "law_source", "") or ""
        ingredient_info.append(f"- {name}: 배합비율 {pct}%" + (f" (분류: {law_src})" if law_src else ""))

    # 법령 원문 합치기
    raw_texts = "\n\n".join(
        f"[{c.law_name} / {c.article_no}]\n{c.text}"
        for c in step_d.citations
    )

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model=os.environ.get("F0_OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0,
            max_tokens=2000,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 한국 식품 수입 검역 전문가입니다.\n\n"
                        "아래 정보를 바탕으로 수입 가능 여부를 판정하세요:\n"
                        "1. 각 원재료의 법령 사용기준을 찾아 정리\n"
                        "2. 배합비율 × 총 용량으로 실제 함량을 계산\n"
                        "3. 실제 함량이 법령 기준을 초과하는지 판단\n"
                        "4. 병용 제한이 있는 경우 합계도 확인\n\n"
                        "규칙:\n"
                        "- 'II. 2. 1)의 규정에 따라 사용하여야 한다' = 사용량 제한 없음\n"
                        "- 식품원료(A코드)는 사용량 제한 없음\n"
                        "- 기준 초과 원재료가 하나라도 있으면 '수입불가'\n"
                        "- 모든 원재료가 기준 이내이면 '수입가능'\n\n"
                        "아래 형식으로 작성하세요:\n"
                        "===원재료별 판정===\n"
                        "【원재료명】기준: X / 실제: Y → 적합 또는 부적합 (근거)\n"
                        "...\n"
                        "===최종 판정===\n"
                        "수입가능 또는 수입불가 (사유)\n"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"식품유형: {food_type or '미정'}\n"
                        f"총 용량: {content_volume or '미상'}\n\n"
                        f"원재료 목록:\n" + "\n".join(ingredient_info) + "\n\n"
                        f"관련 법령:\n{raw_texts[:4000]}"
                    ),
                },
            ],
        )
        result_text = (resp.choices[0].message.content or "").strip()
        if result_text:
            # 최종 판정 추출
            verdict = "permitted"
            confidence = 0.85
            if "수입불가" in result_text:
                verdict = "prohibited"
                confidence = 0.80
            elif "수입가능" in result_text:
                verdict = "permitted"
                confidence = 0.85

            from models.f1_types import LawCitation
            new_step_d = StepDResult(citations=[
                LawCitation(
                    chunk_id="llm_judgment",
                    law_name="AI 수입 판정 분석",
                    article_no="법령 기반 판정",
                    text=result_text,
                    score=1.0,
                    namespace="llm_summary",
                )
            ])
            return new_step_d, verdict, confidence
    except Exception as exc:
        logger.warning("LLM 판정 실패: %s — 기본 판정 유지", exc)

    return step_d, "permitted", 0.7


def _enrich_step_c_from_law_citations(step_c, step_d, enriched) -> None:
    """Step D 법령에서 찾은 기준값으로 Step C checks를 보강한다.

    법령 텍스트에서 "원재료명: Xg/kg" 패턴을 추출하여,
    Step C에서 "기준치 없음"인 원재료의 기준값을 채운다.
    """
    import re

    # Step C에서 기준치 없는 원재료 목록
    no_threshold_names = {
        ch.ingredient_name for ch in step_c.checks
        if ch.threshold_value is None and ch.status in ("no_data", "pass")
    }
    if not no_threshold_names:
        return

    # 법령 텍스트에서 기준값 추출
    extracted: dict[str, tuple[str, str]] = {}  # name → (value, law_ref)
    for citation in step_d.citations:
        text = citation.text
        # "원재료명 | ... | Xg/kg이하" 또는 "원재료명: Xg/kg" 패턴
        for name in no_threshold_names:
            if name.lower() not in text.lower():
                continue
            # "Xg/kg이하" 또는 "X mg/kg" 패턴 찾기
            # 해당 원재료명 근처에서 수치 추출
            name_idx = text.lower().find(name.lower())
            if name_idx < 0:
                continue
            context = text[name_idx:name_idx + 300]
            # 수치+단위 패턴 매칭
            match = re.search(
                r"(\d+(?:\.\d+)?)\s*(g/kg|mg/kg|ppm|g/L|mg/L|%)\s*(?:이하|이상)?",
                context,
            )
            if match:
                value_str = f"{match.group(1)} {match.group(2)}"
                extracted[name] = (value_str, citation.law_name)

    # Step C checks 업데이트
    for check in step_c.checks:
        if check.ingredient_name in extracted:
            value_str, law_ref = extracted[check.ingredient_name]
            check.spec_raw = value_str
            check.spec_summary = value_str
            check.law_ref = law_ref
            check.status = "review_needed"  # 기준값은 있으나 실측값 비교 필요


def _derive_exact_verdict(out: Feature1Output) -> str:
    """Feature1Output → 단일 verdict 도출 (RAG 비교용).

    우선순위: forbidden > aggregation.prohibited > unidentified(미등록 우세) >
               restricted > permitted > unidentified(폴백).
    """
    if out.forbidden_hits:
        return "prohibited"
    agg = out.aggregation
    if agg is None:
        return "unidentified"
    if agg.prohibited > 0:
        return "prohibited"
    if agg.unidentified > 0 and agg.permitted == 0:
        return "unidentified"
    if agg.restricted > 0:
        return "restricted"
    if agg.permitted > 0:
        return "permitted"
    return "unidentified"


async def run_feature1_with_rag(
    ingredients: list[Ingredient],
    food_type: Optional[str] = None,
    process_conditions: Optional[ProcessConditions] = None,
    payload_for_rag: Optional[dict[str, Any]] = None,
) -> tuple[Feature1Output, Optional[RagJudgement], ConflictStatus]:
    """기능1 + RAG + HITL 비교 통합 entry.

    기존 `run_feature1`을 재사용하고, Step 0(forbidden) 미적중 시에만 RAG를 호출.

    Returns:
        (Feature1Output, RagJudgement | None, conflict_status)

    conflict_status 규약 (총괄 §2.7):
        - rag_skipped      : Step 0(forbidden) 적중 → RAG 미호출
        - rag_unavailable  : RAG 호출 실패 (rag.rag_verdict == "error")
        - agreed           : exact_verdict == rag_verdict
        - rag_supplemented : exact_verdict=="unidentified" && rag_verdict in {permitted, restricted, prohibited}
        - conflict         : 그 외 불일치
    """
    out = run_feature1(ingredients, food_type, process_conditions)

    # Step 0 적중 시 RAG 미호출 (금지원료 절대 우선)
    if out.forbidden_hits:
        return out, None, "rag_skipped"

    payload = payload_for_rag or {
        "ingredients": [i.name for i in ingredients],
        "food_type": food_type,
    }

    rag = await f1_rag_judge.run(payload)

    if rag.rag_verdict == "error":
        return out, rag, "rag_unavailable"

    exact_verdict = _derive_exact_verdict(out)

    if (
        exact_verdict == "unidentified"
        and rag.rag_verdict in ("permitted", "restricted", "prohibited")
    ):
        conflict: ConflictStatus = "rag_supplemented"
    elif exact_verdict == rag.rag_verdict:
        conflict = "agreed"
    else:
        conflict = "conflict"

    return out, rag, conflict


# ============================================================
# Wave 2 Day 0 — F1 재설계 v2 orchestrator (골격)
# feature flag `F1_USE_DATA_GO_KR_API` 도입 후 `run_feature1_with_rag`
# 분기 경로로 연결된다. Day 0 시점에는 Step A/B/C/D 가 NotImplementedError
# 를 raise 하므로, 호출 시 feature flag가 off 여야 정상.
# 본 골격은 **부모 세션이 배타 관리** (14번 §5-3). W2-A/B/C/D 서브에이전트는
# 각자 `f1_step_*.py` 만 구현하고 본 함수는 건드리지 않는다.
# ============================================================


async def run_feature1_v2(
    ingredients: list[Ingredient],
    food_type: Optional[str] = None,
    food_type_hierarchy: Any = None,
    process_conditions: Optional[ProcessConditions] = None,
    measured_values: Optional[dict[str, MeasuredValue]] = None,
    *,
    client: Any = None,
) -> F1Output:
    """F1 재설계 파이프라인 v2 (Wave 2 실본체).

    흐름 (설계 문서 01~04):
        1. Step A: f1_forbidden_ingredients + 15111777 2중 안전망
           └ forbidden hit → 즉시 종료 (Step B/C skip), Step D 만 법령 인용용 실행
        2. Step B: 15111777 + 15094202 + 15111913 병렬 → allow_verdict·GMO
           └ prohibited → Step C skip, Step D 법령 인용 후 verdict=prohibited
           └ restricted → HITL-1 대상 누적 후 Step C 진행
        3. Step C: 15116583 원재료당 조회 → T_KOR_NM별 집계 + 수치 비교
           └ fail → verdict=prohibited (Step D 계속)
           └ review_needed → verdict=needs_review
        4. Step D: Pinecone 5 namespace 검색 → 법령 인용 (판정 주도 없음)
        5. F1Output 합성 → pipeline_steps.ai_result 저장

    Args:
        ingredients: F0 원재료 목록 (sub_ingredients 포함).
        food_type: F2 확정 식품유형 문자열.
        food_type_hierarchy: F2 계층 객체 (Any — 속성/dict 양쪽 허용).
        process_conditions: 가열·발효·증류·도수 플래그 (현재 v2 로직에서 미사용,
            Wave 3 HITL-1 에스컬레이션 규칙 확정 후 통합 예정).
        measured_values: 원재료명 → MeasuredValue 매핑. None 이면 Step C 수치 비교 스킵.
        client: 테스트 주입용 DataGoKrClient. None 이면 env 키로 Step A/C 내부 생성.

    Returns:
        F1Output — Day 0 동결 6 필드 + W1-B 확장 3 필드.

    Verdict 매핑:
        - prohibited:
            · Step A forbidden hit (confidence 0.95)
            · Step B prohibited verdict (0.85)
            · Step C overall_status=fail (0.90)
        - needs_review:
            · Step C overall_status=review_needed (0.40)
            · Step B unidentified + 다른 이슈 (0.40)
            · Step C no_data + 제한·금지 없음 (0.50)
        - restricted:
            · Step B 에 restricted 원재료 있고 Step C pass/no_data (0.70~0.75)
        - permitted:
            · 모두 clean + Step C pass (0.90)
    """
    from services import f1_step_a, f1_step_b, f1_step_c, f1_step_d
    from services.data_go_kr import DataGoKrClient

    warnings: list[str] = []
    evidence_external_data: list[dict[str, Any]] = []
    unit_conversions: list[dict[str, Any]] = []
    gmo_ingredients: list[str] = []
    api_call_stats: dict[str, int] = {}

    # DataGoKrClient 1회 생성 — Step A/C 공유 (Wave 1 HIGH-1 커넥션 풀 재사용)
    owned_client = False
    if client is None:
        api_key = os.environ.get("F1_DATA_GO_KR_API_KEY", "")
        if api_key:
            client = DataGoKrClient(api_key=api_key)
            owned_client = True

    try:
        # ── Step A ────────────────────────────────────────────
        step_a = await f1_step_a.run_step_a(ingredients, client=client)
        if step_a.api_errors:
            warnings.extend(f"step_a_api_error:{e}" for e in step_a.api_errors)
        if getattr(step_a, "warnings", None):
            warnings.extend(step_a.warnings)
        if step_a.forbidden_hits:
            evidence_external_data.append(
                {
                    "step": "A",
                    "source": "f1_forbidden_ingredients (DB)",
                    "forbidden_hits": [h.model_dump() for h in step_a.forbidden_hits],
                }
            )

        # Step A forbidden → 조기 종료 (Step D 만 실행하여 법령 인용)
        if step_a.stopped:
            query_ctx = QueryContext(
                food_type=food_type,
                forbidden_hits=step_a.forbidden_hits,
                ingredient_names=[
                    (getattr(i, "matched_name_ko", "") or "").strip()
                    or getattr(i, "name", "")
                    for i in ingredients
                    if getattr(i, "name", "")
                ],
            )
            _step_d_result = await f1_step_d.run_step_d(query_ctx)
            step_d = _step_d_result.unwrap_or(StepDResult(citations=[]))
            if _step_d_result.is_err():
                logger.warning("Step D 실패 — citations=[]: %s", _step_d_result._reason)
                warnings.append("pipeline_status:partial")
            else:
                warnings.append("pipeline_status:ok")
            return F1Output(
                verdict="prohibited",
                confidence=0.95,
                evidence_laws=[c.model_dump() for c in step_d.citations],
                evidence_external_data=evidence_external_data,
                unit_conversions=[],
                warnings=warnings,
                gmo_ingredients=[],
                api_call_stats={},
                data_source_versions={},
            )

        # ── Step B ────────────────────────────────────────────
        step_b = await f1_step_b.run_step_b(ingredients)
        gmo_ingredients = list(step_b.gmo_ingredients)
        api_call_stats = dict(step_b.api_call_stats)
        if step_b.unidentified:
            warnings.extend(f"step_b_unidentified:{n}" for n in step_b.unidentified)
        if getattr(step_b, "warnings", None):
            warnings.extend(step_b.warnings)

        enriched = step_b.enriched_ingredients or list(ingredients)

        # code-review 🟡-4 fix: `StepBResult.stopped` 필드를 직접 사용 (02번 §9).
        # 과거에는 enriched 를 순회하며 재계산 — Step B 구현과의 drift 제거.
        has_prohibited = step_b.stopped
        restricted_names = [
            getattr(i, "name", "")
            for i in enriched
            if getattr(i, "allow_verdict", None) == "restricted"
        ]

        evidence_external_data.append(
            {
                "step": "B",
                "source": "15094202 + 15111913 (P6-b: 15111777 제거)",
                "enriched_summary": [
                    {
                        "name": getattr(i, "name", ""),
                        "allow_verdict": getattr(i, "allow_verdict", None),
                        "component_code": getattr(i, "component_code", None),
                        "is_gmo": getattr(i, "is_gmo", None),
                        # P6 추가 — 원재료 매칭 상세 컬럼 채움용
                        "matched_name_ko": getattr(i, "matched_name_ko", None),
                        "ingredient_code_f0": getattr(i, "ingredient_code_f0", None),
                        "match_method": getattr(i, "match_method", None),
                        "law_source": getattr(i, "law_source", None),
                        "percentage": getattr(i, "percentage", None),
                    }
                    for i in enriched
                ],
                "unidentified": list(step_b.unidentified),
                "conditional": [
                    getattr(i, "name", "") for i in step_b.conditional
                ],
                "gmo_ingredients": list(step_b.gmo_ingredients),
            }
        )

        if has_prohibited:
            query_ctx = QueryContext(
                food_type=food_type,
                forbidden_hits=step_a.forbidden_hits,
                restricted_ingredients=restricted_names,
                ingredient_names=[
                    (getattr(i, "matched_name_ko", "") or "").strip()
                    or getattr(i, "name", "")
                    for i in enriched
                    if getattr(i, "name", "")
                ],
                ingredient_codes=[
                    getattr(i, "component_code", "") or "" for i in enriched
                    if getattr(i, "component_code", None)
                ],
            )
            _step_d_result = await f1_step_d.run_step_d(query_ctx)
            step_d = _step_d_result.unwrap_or(StepDResult(citations=[]))
            if _step_d_result.is_err():
                logger.warning("Step D 실패 — citations=[]: %s", _step_d_result._reason)
                warnings.append("pipeline_status:partial")
            else:
                warnings.append("pipeline_status:ok")
            return F1Output(
                verdict="prohibited",
                confidence=0.85,
                evidence_laws=[c.model_dump() for c in step_d.citations],
                evidence_external_data=evidence_external_data,
                unit_conversions=[],
                warnings=warnings,
                gmo_ingredients=gmo_ingredients,
                api_call_stats=api_call_stats,
                data_source_versions={},
            )

        # ── Step C ────────────────────────────────────────────
        step_c = await f1_step_c.run_step_c(
            enriched,
            food_type_hierarchy=food_type_hierarchy,
            measured_values=measured_values,
            client=client,
        )
        warnings.extend(f"step_c_review:{r}" for r in step_c.review_reasons)

        for ch in step_c.checks:
            if ch.unit_original or ch.unit_normalized:
                unit_conversions.append(
                    {
                        "ingredient": ch.ingredient_name,
                        "test_category": ch.test_category,
                        "unit_original": ch.unit_original,
                        "unit_normalized": ch.unit_normalized,
                        "actual_value": ch.actual_value,
                        "threshold_value": ch.threshold_value,
                        "status": ch.status,
                    }
                )
        evidence_external_data.append(
            {
                "step": "C",
                "source": "15116583",
                "overall_status": step_c.overall_status,
                "checks": [ch.model_dump() for ch in step_c.checks],
                "review_reasons": list(step_c.review_reasons),
            }
        )

        failed_standards = [
            f"{ch.ingredient_name}:{ch.test_category}"
            for ch in step_c.checks
            if ch.status == "fail"
        ]

        # ── Step D (항상 실행, 법령 인용용) ────────────────────
        query_ctx = QueryContext(
            food_type=food_type,
            forbidden_hits=[],
            restricted_ingredients=restricted_names,
            failed_standards=failed_standards,
            ingredient_names=[
                # matched_name_ko 우선 (F0 표준명), 없으면 원본명
                (getattr(i, "matched_name_ko", "") or "").strip()
                or getattr(i, "name", "")
                for i in enriched
                if getattr(i, "name", "")
            ],
            ingredient_codes=[
                getattr(i, "component_code", "") or "" for i in enriched
                if getattr(i, "component_code", None)
            ],
        )
        _step_d_result = await f1_step_d.run_step_d(query_ctx)
        step_d = _step_d_result.unwrap_or(StepDResult(citations=[]))
        if _step_d_result.is_err():
            logger.warning("Step D 실패 — citations=[]: %s", _step_d_result._reason)

        # ── Step C 보강: Step D 법령에서 기준값 추출 → Step C checks 업데이트 ──
        if step_d.citations and step_c.checks:
            _enrich_step_c_from_law_citations(step_c, step_d, enriched)

        # ── LLM 법령 기반 판정 ──────────────────────────────────
        if step_d.citations:
            step_d, llm_verdict, llm_confidence = await _llm_judge_with_law(
                step_d, enriched, food_type, ""
            )
        else:
            llm_verdict, llm_confidence = "permitted", 0.7

        # LLM 판정 후 evidence_laws 설정
        evidence_laws = [c.model_dump() for c in step_d.citations]

        # ── pipeline_status 결정 ──────────────────────────────
        if _step_d_result.is_err() or step_b.unidentified:
            warnings.append("pipeline_status:partial")
        else:
            warnings.append("pipeline_status:ok")

        # ── Verdict 결정: LLM 판정 우선, Step B/C 결과로 보강 ──
        if step_c.overall_status == "fail":
            verdict, confidence = "prohibited", 0.90
        elif step_b.unidentified:
            verdict, confidence = "prohibited", 0.60
        elif restricted_names:
            verdict, confidence = "restricted", 0.75
        else:
            # LLM 판정 사용
            verdict, confidence = llm_verdict, llm_confidence

        return F1Output(
            verdict=verdict,
            confidence=confidence,
            evidence_laws=evidence_laws,
            evidence_external_data=evidence_external_data,
            unit_conversions=unit_conversions,
            warnings=warnings,
            gmo_ingredients=gmo_ingredients,
            api_call_stats=api_call_stats,
            data_source_versions={},
        )
    finally:
        if owned_client and client is not None:
            try:
                await client.aclose()
            except Exception as exc:  # noqa: BLE001
                logger.warning("DataGoKrClient aclose 실패: %s", exc)
