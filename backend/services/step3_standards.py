"""기능1 Step 3 — 기준치 수치 비교 (일반식품 + 주류).

담당: 병찬
참고: 계획/기능1_참고자료/04_기준치검증_일반_및_주류.md
테이블: f1_additive_limits, f1_safety_standards

원칙:
    - LLM이 수치 계산 안 함. DB 조회 + Python 비교.
    - is_verified=true 만 판정에 사용 (리스크 3 대응).
"""

from __future__ import annotations

import asyncio
from typing import Optional

import asyncpg

from constants.thresholds_config import (GENERAL_LIMIT_TEXT,
                                                 LIQUOR_CHECK_ITEMS,
                                                 is_alcohol_boundary)
from models.judgment import (CompoundGroupResult, Ingredient,
                                     LimitCheckResult, ProcessConditions,
                                     StandardsCheckResult)
from utils.unit_converter import convert_unit, parse_numeric_limit

# 주류 식품유형 키워드
_LIQUOR_FOOD_TYPES = {"증류주", "발효주", "기타주류", "주류", "혼성주"}


def _is_alcohol_food(food_type: Optional[str], process: ProcessConditions) -> bool:
    """식품유형 또는 process_conditions로 주류 여부 판정."""
    if food_type and any(kw in food_type for kw in _LIQUOR_FOOD_TYPES):
        return True
    if process.is_distilled:
        return True
    if process.alcohol_percentage is not None and process.alcohol_percentage >= 1.0:
        return True
    return False


# ============================================================
# 첨가물 기준치 (f1_additive_limits)
# ============================================================


async def _fetch_additive_limits(
    db: asyncpg.Connection, food_type: str, additive_names: list[str]
) -> list[asyncpg.Record]:
    """해당 식품유형 + 원재료명에 대응하는 additive_limits 행 조회."""
    if not additive_names:
        return []
    return await db.fetch(
        """
        SELECT additive_name, food_type, max_ppm, combined_group, combined_max,
               conversion_factor, colorant_category, total_tar_limit,
               condition_text, regulation_ref
          FROM f1_additive_limits
         WHERE is_verified = true
           AND food_type IN ($1, '전체')
           AND additive_name = ANY($2::text[])
        """,
        food_type,
        additive_names,
    )


def _check_additive_single(
    ing: Ingredient,
    row: asyncpg.Record,
    process: ProcessConditions,
) -> LimitCheckResult:
    """개별 첨가물 허용량 검증."""
    cond = row["condition_text"] or ""
    ref = row["regulation_ref"]

    # 조건: 가열제품 한정
    if "가열" in cond and not process.is_heated:
        return LimitCheckResult(
            item_name=ing.name,
            category="additive",
            max_limit=(
                f"{row['max_ppm']} ppm"
                if row["max_ppm"]
                else GENERAL_LIMIT_TEXT["not_usable"]
            ),
            status="no_data",
            regulation_ref=ref,
        )

    # 실측값(함량 %) 제공 여부
    if ing.percentage is None:
        return LimitCheckResult(
            item_name=ing.name,
            category="additive",
            max_limit=(
                f"{row['max_ppm']} ppm"
                if row["max_ppm"]
                else GENERAL_LIMIT_TEXT["not_usable"]
            ),
            status="no_data",
            regulation_ref=ref,
        )

    # max_ppm NULL = 사용 금지
    if row["max_ppm"] is None:
        return LimitCheckResult(
            item_name=ing.name,
            category="additive",
            max_limit=GENERAL_LIMIT_TEXT["not_usable"],
            actual_value=f"{ing.percentage}%",
            status="fail",
            regulation_ref=ref,
        )

    # 단위 변환: % → mg/kg (== ppm) with optional factor
    try:
        actual_ppm = convert_unit(
            ing.percentage, "%", "mg/kg", factor=row["conversion_factor"]
        )
    except ValueError:
        return LimitCheckResult(
            item_name=ing.name,
            category="additive",
            max_limit=f"{row['max_ppm']} ppm",
            actual_value=f"{ing.percentage}%",
            status="no_data",
            regulation_ref=ref,
        )

    limit_ppm = float(row["max_ppm"])
    status = "fail" if actual_ppm > limit_ppm else "pass"

    return LimitCheckResult(
        item_name=ing.name,
        category="additive",
        max_limit=f"{limit_ppm} ppm",
        actual_value=f"{round(actual_ppm, 4)} ppm",
        status=status,
        regulation_ref=ref,
    )


async def _evaluate_compound_groups(
    db: asyncpg.Connection,
    food_type: str,
    per_item_results: list[LimitCheckResult],
    ingredients: list[Ingredient],
    add_rows_by_name: Optional[dict[str, asyncpg.Record]] = None,
) -> list[CompoundGroupResult]:
    """combined_group 합산 판정.

    H6 수정: add_rows_by_name 을 외부에서 주입받아 N+1 쿼리 제거.
    """
    groups: dict[str, dict] = {}
    # H-NEW-5: 같은 첨가물이 여러 번 입력되면 합산. 덮어쓰기 방지.
    name_to_pct: dict[str, float] = {}
    for i in ingredients:
        if i.percentage is not None:
            name_to_pct[i.name] = name_to_pct.get(i.name, 0.0) + float(i.percentage)

    # 각 결과별 group 매핑 + 합산
    for r in per_item_results:
        if r.status not in ("pass", "fail"):
            continue
        # 사전에 로드한 딕셔너리 우선 사용, 없으면 개별 조회 (하위 호환)
        row = add_rows_by_name.get(r.item_name) if add_rows_by_name else None
        if row is None:
            row = await db.fetchrow(
                """
                SELECT combined_group, combined_max, conversion_factor,
                       regulation_ref, total_tar_limit
                  FROM f1_additive_limits
                 WHERE is_verified = true
                   AND food_type IN ($1, '전체')
                   AND additive_name = $2
                 LIMIT 1
                """,
                food_type,
                r.item_name,
            )
        if not row or not row["combined_group"]:
            continue

        grp = row["combined_group"]
        pct = name_to_pct.get(r.item_name)
        if pct is None:
            continue
        try:
            actual_ppm = convert_unit(
                pct, "%", "mg/kg", factor=row["conversion_factor"]
            )
        except ValueError:
            continue

        g = groups.setdefault(
            grp,
            {
                "sum": 0.0,
                "members": [],
                "limit": float(row["combined_max"]) if row["combined_max"] else None,
                "law_ref": row["regulation_ref"],
            },
        )
        g["sum"] += actual_ppm
        g["members"].append(r.item_name)

    results: list[CompoundGroupResult] = []
    for name, g in groups.items():
        if g["limit"] is None:
            continue
        status = "fail" if g["sum"] > g["limit"] else "pass"
        results.append(
            CompoundGroupResult(
                group=name,
                members=g["members"],
                total=round(g["sum"], 4),
                limit=g["limit"],
                unit="ppm",
                status=status,
                law_ref=g["law_ref"],
            )
        )
    return results


# ============================================================
# 안전기준 (f1_safety_standards) — 중금속/미생물/주류
# ============================================================


async def _fetch_safety_standards(
    db: asyncpg.Connection, food_type: str, standard_types: list[str]
) -> list[asyncpg.Record]:
    return await db.fetch(
        """
        SELECT food_type, standard_type, target_name, max_limit, regulation_ref
          FROM f1_safety_standards
         WHERE is_verified = true
           AND food_type IN ($1, '전체')
           AND standard_type = ANY($2::text[])
        """,
        food_type,
        standard_types,
    )


def _safety_to_check(row: asyncpg.Record) -> LimitCheckResult:
    """safety_standards 행을 LimitCheckResult로 변환 (실측 없으므로 no_data)."""
    category_map = {
        "heavy_metal": "heavy_metal",
        "microbe": "microbe",
        "pesticide": "pesticide",
        "alcohol": "alcohol",
        "contaminant": "contaminant",
    }
    cat = category_map.get(row["standard_type"], "contaminant")
    return LimitCheckResult(
        item_name=row["target_name"],
        category=cat,  # type: ignore[arg-type]
        max_limit=row["max_limit"],
        status="no_data",
        regulation_ref=row["regulation_ref"],
    )


# ============================================================
# 주류 안전기준 검증
# ============================================================


async def check_liquor_safety(
    db: asyncpg.Connection,
    food_type: str,
    alcohol_percentage: Optional[float],
) -> tuple[list[LimitCheckResult], list[dict]]:
    escalations: list[dict] = []

    # 주류 4대 항목 병렬 조회
    async def _fetch_item(name: str) -> LimitCheckResult:
        row = await db.fetchrow(
            """
            SELECT target_name, max_limit, regulation_ref, standard_type
              FROM f1_safety_standards
             WHERE is_verified = true
               AND standard_type = 'alcohol'
               AND target_name ILIKE '%' || $1 || '%'
             LIMIT 1
            """,
            name,
        )
        if row:
            return _safety_to_check(row)
        return LimitCheckResult(
            item_name=name,
            category="alcohol",
            max_limit=GENERAL_LIMIT_TEXT["not_registered"],
            status="no_data",
        )

    checks = await asyncio.gather(
        *[_fetch_item(item["name"]) for item in LIQUOR_CHECK_ITEMS]
    )

    # 도수 경계치 에스컬레이션
    if is_alcohol_boundary(alcohol_percentage):
        escalations.append(
            {
                "module_id": "F1",
                "trigger_type": "alcohol_boundary",
                "reason": (
                    f"알코올 도수 {alcohol_percentage}% — 주류/비주류 경계치. 수동 확인 필요"
                ),
            }
        )

    return list(checks), escalations


# ============================================================
# 통합 엔트리
# ============================================================


async def run_step3(
    db: asyncpg.Connection,
    ingredients: list[Ingredient],
    food_type: Optional[str],
    process: Optional[ProcessConditions] = None,
) -> StandardsCheckResult:
    """Step 3 — 일반식품 + 주류 기준치 검증."""
    process = process or ProcessConditions()
    escalations: list[dict] = []

    if not food_type:
        return StandardsCheckResult(
            food_type=None,
            overall_status="review_needed",
            escalations=[
                {
                    "module_id": "F1",
                    "trigger_type": "no_data",
                    "reason": "food_type 미확정 — 기능2 결과 필요",
                }
            ],
        )

    # 첨가물 기준치 검증
    add_rows = await _fetch_additive_limits(
        db, food_type, [i.name for i in ingredients]
    )
    add_rows_by_name = {r["additive_name"]: r for r in add_rows}

    # C-NEW-2 가드: 첨가물 후보 (INS/CAS 있거나 이름이 DB 매치된 것) 중
    # f1_additive_limits 에 행이 없으면 silent pass 위험 → 경고 추가.
    additive_checks: list[LimitCheckResult] = []
    for ing in ingredients:
        row = add_rows_by_name.get(ing.name)
        if row:
            additive_checks.append(_check_additive_single(ing, row, process))
        elif ing.ins or ing.cas:
            # INS/CAS 번호가 있다는 건 첨가물이라는 강한 신호.
            # DB에 기준치 없으면 silent pass 대신 review_needed 로 경보.
            additive_checks.append(
                LimitCheckResult(
                    item_name=ing.name,
                    category="additive",
                    max_limit=GENERAL_LIMIT_TEXT["not_registered"],
                    actual_value=(
                        f"{ing.percentage}%" if ing.percentage is not None else None
                    ),
                    status="no_data",
                    regulation_ref=None,
                )
            )
            escalations.append(
                {
                    "module_id": "F1",
                    "trigger_type": "limit_missing",
                    "reason": (
                        f'첨가물 "{ing.name}" (INS {ing.ins or "-"}, CAS {ing.cas or "-"}) '
                        f"기준치가 {food_type}에 미등록 — 담당자 확인 필요"
                    ),
                }
            )
        # 일반 원료 (INS/CAS 없음)는 첨가물 아님 → skip (의도된 동작)

    # 복합 합산 (H6: 이미 로드한 add_rows_by_name 재사용으로 N+1 제거)
    compound_results = await _evaluate_compound_groups(
        db, food_type, additive_checks, ingredients, add_rows_by_name
    )

    # 안전기준 조회 (중금속 + 미생물)
    safety_rows = await _fetch_safety_standards(
        db, food_type, ["heavy_metal", "microbe", "pesticide", "contaminant"]
    )
    safety_checks = [_safety_to_check(r) for r in safety_rows]

    all_checks = additive_checks + safety_checks

    # 주류 분기
    if _is_alcohol_food(food_type, process):
        liquor_checks, liquor_escalations = await check_liquor_safety(
            db, food_type, process.alcohol_percentage
        )
        all_checks.extend(liquor_checks)
        escalations.extend(liquor_escalations)

    # 위반 수집
    violations = [c for c in all_checks if c.status == "fail"]
    violations_compound = [c for c in compound_results if c.status == "fail"]

    if violations:
        escalations.append(
            {
                "module_id": "F1",
                "trigger_type": "standards_violation",
                "reason": f"기준치 초과 {len(violations)}건: "
                + ", ".join(v.item_name for v in violations),
            }
        )

    # overall (H5 수정: 데드코드 제거 + 빈 리스트 review_needed 오판 해결)
    if violations or violations_compound:
        overall = "fail"
    elif not all_checks and not compound_results:
        # 검사 대상 자체가 없음 → 담당자 확인 필요
        overall = "review_needed"
    elif all_checks and all(c.status == "no_data" for c in all_checks):
        # 검사 대상은 있으나 실측 없음
        overall = "review_needed"
    else:
        overall = "pass"

    return StandardsCheckResult(
        food_type=food_type,
        overall_status=overall,  # type: ignore[arg-type]
        checks=all_checks,
        compound_results=compound_results,
        violations=violations,
        escalations=escalations,
    )
