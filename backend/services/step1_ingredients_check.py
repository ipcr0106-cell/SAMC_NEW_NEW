"""기능1 Step 0/1/1-A/1-B — 수입 가능 여부 판정.

담당: 병찬
참고: 계획/기능1_참고자료/02_매칭체인_5단계.md, 03_복합원재료_조건부판정.md
테이블: f1_allowed_ingredients, f1_forbidden_ingredients (+ search_f1_ingredients_trgm RPC)

단계:
    Step 0: f1_forbidden_ingredients 게이트 → 적중 시 즉시 종료
    Step 1: 5단계 매칭 체인 (정확명 → INS → CAS → 학명 → 퍼지)
    Step 1-A: 복합원재료 재귀 검증 (sub_ingredients)
    Step 1-B: 조건부(restricted) 평가
"""

from __future__ import annotations

from typing import Optional

import asyncpg

from constants.condition_patterns import (classify_condition_type,
                                                  validate_part_restriction)
from constants.thresholds_config import (EXACT_MATCH_CONFIDENCE,
                                                 FUZZY_MATCH_CONFIDENCE,
                                                 FUZZY_SIMILARITY_THRESHOLD,
                                                 is_synthetic_flavor)
from models.judgment import (AggregationResult, ConditionalEvaluation,
                                     ForbiddenHit, Ingredient,
                                     IngredientMatchResult, IngredientVerdict)

# allowed_status → IngredientVerdict 매핑
_VERDICT_MAP: dict[str, IngredientVerdict] = {
    "permitted": "permitted",
    "restricted": "restricted",
    "prohibited": "prohibited",
}


# ============================================================
# Step 0: forbidden 게이트
# ============================================================


async def check_forbidden_first(
    db: asyncpg.Connection, ingredients: list[Ingredient]
) -> list[ForbiddenHit]:
    """원재료 이름 중 하나라도 f1_forbidden_ingredients 에 매칭되면 hit 반환."""
    names = [ing.name.strip() for ing in ingredients if ing.name]
    if not names:
        return []

    rows = await db.fetch(
        """
        SELECT DISTINCT name_ko, category, law_source, reason
          FROM f1_forbidden_ingredients
         WHERE is_verified = true
           AND (
                name_ko = ANY($1::text[])
                OR EXISTS (
                    SELECT 1 FROM unnest(aliases) a
                     WHERE a = ANY($1::text[])
                )
           )
        """,
        names,
    )
    return [
        ForbiddenHit(
            name_ko=r["name_ko"],
            category=r["category"],
            law_source=r["law_source"],
            reason=r["reason"],
        )
        for r in rows
    ]


# ============================================================
# Step 1: 5단계 매칭
# ============================================================


def _build_result(
    ing: Ingredient,
    row: asyncpg.Record,
    method: str,
    confidence: float,
) -> IngredientMatchResult:
    status = (
        row.get("allowed_status", "permitted")
        if hasattr(row, "get")
        else row["allowed_status"]
    )
    return IngredientMatchResult(
        ingredient=ing,
        verdict=_VERDICT_MAP.get(status, "unidentified"),
        match_method=method,  # type: ignore[arg-type]
        matched_db_id=str(row["id"]),
        confidence=confidence,
        conditions=row["conditions"] if "conditions" in row else None,
        matched_name_ko=row["name_ko"],
        law_source=row["law_source"] if "law_source" in row else None,
    )


def _unidentified(ing: Ingredient) -> IngredientMatchResult:
    return IngredientMatchResult(
        ingredient=ing,
        verdict="unidentified",
        match_method=None,
        matched_db_id=None,
        confidence=0.0,
    )


async def match_ingredient(
    db: asyncpg.Connection, ing: Ingredient
) -> IngredientMatchResult:
    """5단계 순차 매칭 체인."""
    name = (ing.name or "").strip()
    if not name:
        return _unidentified(ing)

    # ── 1단계: 정확 이름 매칭 ─────────────────────────────
    row = await db.fetchrow(
        """
        SELECT id, name_ko, allowed_status, conditions, law_source
          FROM f1_allowed_ingredients
         WHERE name_ko = $1
         LIMIT 1
        """,
        name,
    )
    if row:
        return _build_result(ing, row, "exact_name", EXACT_MATCH_CONFIDENCE)

    # ── 2단계: INS 번호 매칭 ──────────────────────────────
    if ing.ins:
        row = await db.fetchrow(
            """
            SELECT id, name_ko, allowed_status, conditions, law_source
              FROM f1_allowed_ingredients
             WHERE ins_number = $1
             LIMIT 1
            """,
            ing.ins,
        )
        if row:
            return _build_result(ing, row, "ins_number", EXACT_MATCH_CONFIDENCE)

    # ── 3단계: CAS 번호 매칭 ──────────────────────────────
    if ing.cas:
        row = await db.fetchrow(
            """
            SELECT id, name_ko, allowed_status, conditions, law_source
              FROM f1_allowed_ingredients
             WHERE cas_number = $1
             LIMIT 1
            """,
            ing.cas,
        )
        if row:
            return _build_result(ing, row, "cas_number", EXACT_MATCH_CONFIDENCE)

    # ── 4단계: 학명 매칭 (H10: 4자 이상일 때만 부분매칭, 짧은 한글 오탐 방지) ──
    if len(name) >= 4:
        row = await db.fetchrow(
            """
            SELECT id, name_ko, allowed_status, conditions, law_source
              FROM f1_allowed_ingredients
             WHERE scientific_name ILIKE $1
             LIMIT 1
            """,
            f"%{name}%",
        )
        if row:
            return _build_result(ing, row, "scientific_name", EXACT_MATCH_CONFIDENCE)

    # ── 5단계: 퍼지 (trgm RPC) ────────────────────────────
    row = await db.fetchrow(
        "SELECT * FROM search_f1_ingredients_trgm($1, 1)",
        name,
    )
    if row and float(row["similarity"]) >= FUZZY_SIMILARITY_THRESHOLD:
        return _build_result(ing, row, "fuzzy", FUZZY_MATCH_CONFIDENCE)

    return _unidentified(ing)


# ============================================================
# Step 1 집계 + 에스컬레이션
# ============================================================


async def run_ingredient_match_chain(
    db: asyncpg.Connection, ingredients: list[Ingredient]
) -> AggregationResult:
    results: list[IngredientMatchResult] = []
    escalations: list[dict] = []

    for ing in ingredients:
        # 합성향료 예외처리
        if is_synthetic_flavor(ing.name):
            results.append(_unidentified(ing))
            escalations.append(
                {
                    "module_id": "F1",
                    "trigger_type": "synthetic_flavor",
                    "reason": f'합성향료 하위원료 확인 필요: "{ing.name}"',
                }
            )
            continue

        r = await match_ingredient(db, ing)
        results.append(r)

        if r.verdict == "prohibited":
            escalations.append(
                {
                    "module_id": "F1",
                    "trigger_type": "prohibited_detected",
                    "confidence_score": r.confidence,
                    "reason": f'금지 원료 감지: "{ing.name}"',
                }
            )
        elif r.verdict == "unidentified":
            escalations.append(
                {
                    "module_id": "F1",
                    "trigger_type": "low_confidence",
                    "confidence_score": 0.0,
                    "reason": f'미확인 원료: "{ing.name}" — DB 매칭 실패',
                }
            )

    return AggregationResult(
        total=len(results),
        permitted=sum(1 for r in results if r.verdict == "permitted"),
        restricted=sum(1 for r in results if r.verdict == "restricted"),
        prohibited=sum(1 for r in results if r.verdict == "prohibited"),
        unidentified=sum(1 for r in results if r.verdict == "unidentified"),
        results=results,
        escalations=escalations,
    )


# ============================================================
# Step 1-A: 복합원재료 재귀
# ============================================================


async def evaluate_compound_ingredients(
    db: asyncpg.Connection, ingredients: list[Ingredient]
) -> tuple[list[IngredientMatchResult], list[dict]]:
    """sub_ingredients가 있는 원재료들을 재귀적으로 매칭 (다단계 중첩 지원).

    H9 수정: 2단계 이상 중첩된 복합원재료도 평가.
    C-NEW-1 주석: 중복 매칭 방지 설계 명시.

    실행 모델:
        입력 [과일혼합[딸기[정제수]]] 인 경우:
        - 과일혼합 자체는 run_ingredient_match_chain 에서 이미 1회 매칭됨
          (이 함수에 들어올 때는 상위 매칭이 끝난 상태)
        - 과일혼합.sub_ingredients = [딸기] 에 대해 run_ingredient_match_chain 1회 → 딸기 매칭
        - 재귀 evaluate_compound_ingredients([딸기]) 호출 시:
            - 딸기 자체는 매칭 X (위에서 이미 함)
            - 딸기.sub_ingredients = [정제수] 에 대해 매칭 1회 → 정제수 매칭
        - 결과: 딸기 1회, 정제수 1회 — 중복 없음

    핵심: 각 레벨의 sub 는 "부모가 호출한 run_ingredient_match_chain" 에서 1회만 매칭됨.
          이 함수는 "sub 의 sub" 를 찾아 더 깊이 내려가는 역할.
    """
    all_sub_results: list[IngredientMatchResult] = []
    escalations: list[dict] = []

    for ing in ingredients:
        if not ing.sub_ingredients:
            continue
        # 1단계: 이 ing 의 직계 sub_ingredients 매칭
        # (ing 자체는 호출부에서 이미 매칭 완료 상태)
        sub_agg = await run_ingredient_match_chain(db, ing.sub_ingredients)
        all_sub_results.extend(sub_agg.results)
        escalations.extend(sub_agg.escalations)

        if sub_agg.prohibited > 0:
            escalations.append(
                {
                    "module_id": "F1",
                    "trigger_type": "compound_prohibited",
                    "reason": (
                        f'복합원재료 "{ing.name}"의 하위 성분 중 '
                        f"금지 원료 {sub_agg.prohibited}건 감지"
                    ),
                }
            )

        # 2단계+: 재귀로 "sub 의 sub" 처리
        # ing.sub_ingredients 를 인자로 넘기지만, 재귀 함수 내부에서
        # `if not sub.sub_ingredients: continue` 로 단일 원료는 걸러지므로
        # 이미 1단계에서 매칭한 것이 다시 매칭되지 않음.
        deeper_results, deeper_escalations = await evaluate_compound_ingredients(
            db, ing.sub_ingredients
        )
        all_sub_results.extend(deeper_results)
        escalations.extend(deeper_escalations)

    return all_sub_results, escalations


# ============================================================
# Step 1-B: 조건부(restricted) 평가
# ============================================================


def evaluate_condition(
    ingredient_name: str,
    conditions: str,
    ingredient: Ingredient,
) -> ConditionalEvaluation:
    """단건 조건 평가."""
    ctype = classify_condition_type(conditions)

    # 부위 제한: 자동 검증
    if ctype == "part_restriction" and ingredient.part:
        satisfied = validate_part_restriction(conditions, ingredient.part)
        return ConditionalEvaluation(
            ingredient_name=ingredient_name,
            condition_type=ctype,
            condition_description=conditions,
            is_satisfied=satisfied,
            evidence=f"신고 부위: {ingredient.part}",
        )

    # 함량 제한: Step 3(기준치)으로 위임 → evidence만 기록
    if ctype == "quantity_limit" and ingredient.percentage is not None:
        return ConditionalEvaluation(
            ingredient_name=ingredient_name,
            condition_type=ctype,
            condition_description=conditions,
            is_satisfied=None,
            evidence=f"신고 함량: {ingredient.percentage}%",
        )

    # 나머지: 담당자 확인 필요
    return ConditionalEvaluation(
        ingredient_name=ingredient_name,
        condition_type=ctype,
        condition_description=conditions,
        is_satisfied=None,
    )


def evaluate_conditional_ingredients(
    match_results: list[IngredientMatchResult],
    ingredients: list[Ingredient],
) -> list[ConditionalEvaluation]:
    """restricted 결과들을 일괄 조건 평가."""
    evals: list[ConditionalEvaluation] = []
    name_to_ing = {i.name: i for i in ingredients}

    for r in match_results:
        if r.verdict != "restricted" or not r.conditions:
            continue
        ing = name_to_ing.get(r.ingredient.name, r.ingredient)
        evals.append(evaluate_condition(r.ingredient.name, r.conditions, ing))
    return evals


# ============================================================
# 통합 엔트리 포인트 — Step 0 + 1 + 1-A + 1-B
# ============================================================


async def run_step1(
    db: asyncpg.Connection,
    ingredients: list[Ingredient],
) -> dict:
    """Step 0/1/1-A/1-B 통합 실행. Step 3(기준치)는 step3_standards 에서 별도."""
    # Step 0
    forbidden_hits = await check_forbidden_first(db, ingredients)
    if forbidden_hits:
        return {
            "import_possible": False,
            "verdict": "수입불가 — 절대 금지 원료 포함",
            "forbidden_hits": [h.model_dump() for h in forbidden_hits],
            "stopped_at": "step0",
        }

    # Step 1
    aggregation = await run_ingredient_match_chain(db, ingredients)

    # Step 1-A: 복합원재료
    sub_results, sub_escalations = await evaluate_compound_ingredients(db, ingredients)

    # Step 1-B: 조건부 평가
    conditional_evals = evaluate_conditional_ingredients(
        aggregation.results + sub_results, ingredients
    )

    # H-NEW-1: 합성향료 원재료 이름 수집 (features.py 에서 status override 용)
    synthetic_flavor_names: list[str] = [
        ing.name for ing in ingredients if is_synthetic_flavor(ing.name)
    ]

    escalations = list(aggregation.escalations) + sub_escalations

    # 별표3 적중 시 수입불가 조기 확정
    if aggregation.prohibited > 0:
        return {
            "import_possible": False,
            "verdict": "수입불가 — 미허용 원료 포함",
            "aggregation": aggregation.model_dump(),
            "conditional_evaluations": [e.model_dump() for e in conditional_evals],
            "synthetic_flavor_ingredients": synthetic_flavor_names,
            "escalations": escalations,
            "stopped_at": "step1",
        }

    # restricted 조건 불충족 시도 수입불가
    failed_conditions = [e for e in conditional_evals if e.is_satisfied is False]
    if failed_conditions:
        return {
            "import_possible": False,
            "verdict": "수입불가 — 조건부 원료 조건 불충족",
            "aggregation": aggregation.model_dump(),
            "conditional_evaluations": [e.model_dump() for e in conditional_evals],
            "synthetic_flavor_ingredients": synthetic_flavor_names,
            "escalations": escalations,
            "stopped_at": "step1b",
        }

    return {
        "import_possible": None,  # Step 3 (기준치) 검증 대기
        "verdict": "원재료 매칭·조건부 통과 — 기준치 검증 필요",
        "aggregation": aggregation.model_dump(),
        "conditional_evaluations": [e.model_dump() for e in conditional_evals],
        "synthetic_flavor_ingredients": synthetic_flavor_names,
        "escalations": escalations,
    }
