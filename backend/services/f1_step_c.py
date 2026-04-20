"""Step C — 기준규격 수치 비교 서비스 (W2-C 본체).

Wave 2 W2-C 트랙 구현. `run_step_c` 시그니처는 Day 0 스켈레톤(4c5471e) 동결.

동작 요약:
    1. 원재료당 15116583 `get_additive_standard` 병렬 조회 (pageNo 순회).
    2. `AdditiveSpec` 로 모델 검증 후 T_KOR_NM 으로 집계.
    3. 유효기간 필터 (VALD_END_DT): "99991231" 무기한, YYYYMMDD 오늘 이후만.
    4. 동일 T_KOR_NM 내 복수 유효 기준은 LAST_UPDT_DTM 최신 채택.
    5. 식품유형 필터: SPEC_VAL_SUMUP/FNPRT_ITM_NM 에 식품유형 한정 표현 있으면
       일치하는 행만 채택. 한정 표현 없으면 공통 기준으로 간주.
    6. 수치 비교: MIMM_VAL/MXMM_VAL 우선, 없으면 parse_numeric_spec(SPEC_VAL).
       unit_converter.normalize_to_common_unit 으로 mg/kg 정규화.
       density 는 food_type_hierarchy.food_type → DENSITY_BY_FOOD_TYPE.
    7. 시험항목 분기: "함량" 수치 비교, "성상"/"확인시험"/"순도시험" 비수치 review_needed.
    8. INJRY_YN=="Y" → is_dangerous=True 플래그 + review_reasons 경고.
    9. overall_status: 모두 pass → pass, 하나라도 fail → fail,
       review_needed 존재 → review_needed, 기준 0건 → no_data.

참조:
    - 계획/f1 재설계 계획/03_Step_C_기준규격_설계.md ⭐
    - 계획/f1 재설계 계획/11_단위_정규화_모듈_설계.md (W1-D unit_converter)
    - 계획/f1 재설계 계획/06_API_클라이언트_설계.md §5 (15116583)
    - calling: backend/services/feature1.py `run_feature1_v2`
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from datetime import date
from typing import Any, Optional

from constants.density import DEFAULT_DENSITY, DENSITY_BY_FOOD_TYPE
from exceptions import DataGoKrError
from models.f1_types import MeasuredValue, StandardCheck, StepCResult
from models.judgment import Ingredient
from services.data_go_kr import AdditiveSpec, DataGoKrClient
from utils.unit_converter import (
    SpecEvaluation,
    UnitIncompatibleError,
    normalize_to_common_unit,
    parse_non_numeric_spec,
    parse_numeric_spec,
)

logger = logging.getLogger(__name__)


# ============================================================
# 상수
# ============================================================

_VALD_END_NEVER = "99991231"
_NUMERIC_TEST_CATEGORY = "함량"
_QUALITATIVE_TEST_CATEGORY = "성상"
_HITL_TEST_CATEGORIES = frozenset({"확인시험", "순도시험"})
_PAGE_SIZE = 50
_MAX_PAGES = 5  # numOfRows=50 × 5 = 250 → 한 품목 실제 건수 충분히 커버

# 식품유형 매칭 일반 키워드 — 한정 표현이어도 "일반"이면 공통 취급
_GENERIC_FOOD_TYPE_TOKENS = ("일반", "모든 식품", "전체")


# ============================================================
# 내부 헬퍼
# ============================================================


def _resolve_density(food_type_hierarchy: Any) -> float:
    """food_type_hierarchy.food_type → DENSITY_BY_FOOD_TYPE 조회.

    food_type_hierarchy 는 F2 소관이라 구체 타입을 가정하지 않는다 (Any).
    속성/딕셔너리 어느 쪽이든 `food_type` 키를 안전 추출하고,
    매핑 없으면 `DEFAULT_DENSITY=1.0` 반환.
    """
    if food_type_hierarchy is None:
        return DEFAULT_DENSITY
    food_type: Optional[str] = None
    # dataclass/BaseModel 속성
    if hasattr(food_type_hierarchy, "food_type"):
        food_type = getattr(food_type_hierarchy, "food_type", None)
    # dict 매핑
    elif isinstance(food_type_hierarchy, dict):
        food_type = food_type_hierarchy.get("food_type")
    if not food_type:
        return DEFAULT_DENSITY
    return DENSITY_BY_FOOD_TYPE.get(food_type, DEFAULT_DENSITY)


def _get_food_type(food_type_hierarchy: Any) -> Optional[str]:
    """food_type_hierarchy 에서 food_type 문자열만 추출 (식품유형 매칭용)."""
    if food_type_hierarchy is None:
        return None
    if hasattr(food_type_hierarchy, "food_type"):
        return getattr(food_type_hierarchy, "food_type", None)
    if isinstance(food_type_hierarchy, dict):
        return food_type_hierarchy.get("food_type")
    return None


def _parse_end_date(vald_end_dt: Optional[str]) -> Optional[date]:
    """VALD_END_DT (YYYYMMDD) → date. "99991231" 또는 파싱 실패는 None."""
    if not vald_end_dt or vald_end_dt == _VALD_END_NEVER:
        return None
    try:
        return date(int(vald_end_dt[0:4]), int(vald_end_dt[4:6]), int(vald_end_dt[6:8]))
    except (ValueError, IndexError):
        return None


def _is_active(spec: AdditiveSpec, ref_date: Optional[date] = None) -> bool:
    """기준이 참조일 기준 유효한지 여부 (03번 §3-4).

    VALD_END_DT == "99991231" → 무기한 유효.
    YYYYMMDD → 참조일보다 같거나 이후면 유효.
    """
    end = spec.vald_end_dt
    if end is None or end == "" or end == _VALD_END_NEVER:
        return True
    end_date = _parse_end_date(end)
    if end_date is None:
        # 파싱 실패 시 안전측으로 유효 간주 + 로그 경고
        logger.warning("Step C: VALD_END_DT parse failed pc=%s value=%s", spec.pc_kor_nm, end)
        return True
    ref = ref_date or date.today()
    return end_date >= ref


def _pick_latest(specs: list[AdditiveSpec]) -> AdditiveSpec:
    """동일 T_KOR_NM 내 여러 spec 이면 LAST_UPDT_DTM 최신 1건 채택.

    LAST_UPDT_DTM 은 "YYYY-MM-DD HH:MM:SS" 문자열. 문자열 정렬만으로 시간 순서
    보존되므로 그대로 max() 사용.
    """
    if len(specs) == 1:
        return specs[0]
    return max(specs, key=lambda s: s.last_updt_dtm or "")


def _is_applicable(spec: AdditiveSpec, food_type: Optional[str]) -> bool:
    """식품유형 매칭 (03번 §7).

    SPEC_VAL_SUMUP / FNPRT_ITM_NM 에 식품유형 한정 표현이 있으면
    - 해당 food_type 이 포함된 경우에만 채택
    - 한정 표현이 없거나 "일반/모든 식품" 류면 공통으로 채택
    food_type 이 None 이면 필터 없음 (모두 공통으로 간주).
    """
    summary_parts = [spec.spec_val_sumup or "", spec.fnprt_itm_nm or ""]
    summary = " ".join(p for p in summary_parts if p).strip()
    if not summary:
        return True
    # 일반 키워드 매칭 → 공통 취급
    for token in _GENERIC_FOOD_TYPE_TOKENS:
        if token in summary:
            return True
    # food_type 미지정이면 공통 간주 (보수적)
    if not food_type:
        return True
    return food_type in summary


def _coerce_float(value: Any) -> Optional[float]:
    """API 응답의 문자열 수치를 float 로. 공백/빈값/비수치는 None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _extract_min_max(spec: AdditiveSpec) -> tuple[Optional[float], Optional[float]]:
    """MIMM_VAL/MXMM_VAL 우선, 없으면 SPEC_VAL 파싱 (03번 §4, 11번 §5)."""
    mi = _coerce_float(spec.mimm_val)
    mx = _coerce_float(spec.mxmm_val)
    if mi is not None or mx is not None:
        return mi, mx
    if spec.spec_val:
        return parse_numeric_spec(spec.spec_val)
    return None, None


def _safe_normalize(
    value: float, unit: str, *, density: float
) -> tuple[Optional[float], str, Optional[str]]:
    """normalize_to_common_unit 래퍼 — 실패 시 (None, 원단위, 실패 사유) 반환.

    Returns:
        (normalized_value, target_unit, error_reason).
        성공 시 error_reason=None. error_reason 이 있으면 수치 비교 스킵 대상.
    """
    if not unit:
        return None, unit or "", "unit_missing"
    try:
        norm_value, norm_unit = normalize_to_common_unit(value, unit, density=density)
    except UnitIncompatibleError as exc:
        return None, unit, f"unit_incompatible:{exc.unit}"
    except ValueError as exc:
        return None, unit, f"unit_unknown:{exc}"
    except ZeroDivisionError:
        return None, unit, "density_zero"
    return norm_value, norm_unit, None


def _evaluate_numeric(
    spec: AdditiveSpec,
    measured: Optional[MeasuredValue],
    *,
    density: float,
    ingredient_name: str,
) -> StandardCheck:
    """수치 비교 (T_KOR_NM='함량' 기본).

    - MIMM_VAL/MXMM_VAL 또는 SPEC_VAL 파싱으로 (min, max) 확보
    - (min/max) 중 적어도 하나 존재해야 비교 가능
    - 실측값 없으면 기준만 표시, status="no_data"
    - 단위 불일치 / 변환 불가 시 review_needed + 사유 기록
    """
    unit_original = spec.unit_nm
    min_raw, max_raw = _extract_min_max(spec)
    is_dangerous = (spec.injry_yn == "Y") if spec.injry_yn else None

    # 기준이 수치로 잡히지 않으면 비수치 위임
    if min_raw is None and max_raw is None:
        return _evaluate_non_numeric(
            spec, ingredient_name=ingredient_name, is_dangerous=is_dangerous
        )

    # 기준 수치 정규화 (단위 필요)
    threshold_min_norm: Optional[float] = None
    threshold_max_norm: Optional[float] = None
    unit_normalized: Optional[str] = None
    norm_error: Optional[str] = None

    if unit_original:
        if min_raw is not None:
            n, u, err = _safe_normalize(min_raw, unit_original, density=density)
            if err:
                norm_error = err
            else:
                threshold_min_norm = n
                unit_normalized = u
        if max_raw is not None and norm_error is None:
            n, u, err = _safe_normalize(max_raw, unit_original, density=density)
            if err:
                norm_error = err
            else:
                threshold_max_norm = n
                unit_normalized = u
    else:
        # 단위 없는 수치 기준 (예: 굴절률 1.454~1.461) → 단위 없는 절대값 비교
        threshold_min_norm = min_raw
        threshold_max_norm = max_raw
        unit_normalized = None

    # 기준치 요약 (unit_converter 미적용 단일 값 필드)
    threshold_value = threshold_max_norm if threshold_max_norm is not None else threshold_min_norm

    base_check = StandardCheck(
        ingredient_name=ingredient_name,
        test_category=spec.t_kor_nm,
        spec_raw=spec.spec_val,
        spec_summary=spec.spec_val_sumup,
        actual_value=None,
        unit_original=unit_original,
        unit_normalized=unit_normalized,
        threshold_value=threshold_value,
        is_dangerous=is_dangerous,
        status="no_data",
        law_ref=_law_ref_of(spec),
    )

    # 단위 정규화 실패 → review_needed
    if norm_error:
        return base_check.model_copy(
            update={"status": "review_needed"}
        )

    # 실측값 없음 → 기준만 표시
    if measured is None:
        return base_check

    # 실측값 정규화
    if unit_original:
        measured_norm, _unit, m_err = _safe_normalize(
            measured.value, measured.unit, density=density
        )
        if m_err:
            return base_check.model_copy(
                update={
                    "actual_value": f"{measured.value} {measured.unit}",
                    "status": "review_needed",
                }
            )
    else:
        # 단위 없는 수치 기준: 실측값도 단위 없는 값으로 처리
        measured_norm = float(measured.value)

    # 비교
    status: str = "pass"
    if threshold_min_norm is not None and measured_norm < threshold_min_norm:
        status = "fail"
    elif threshold_max_norm is not None and measured_norm > threshold_max_norm:
        status = "fail"

    return base_check.model_copy(
        update={
            "actual_value": f"{measured.value} {measured.unit}",
            "status": status,
        }
    )


def _evaluate_non_numeric(
    spec: AdditiveSpec,
    *,
    ingredient_name: str,
    is_dangerous: Optional[bool] = None,
) -> StandardCheck:
    """비수치 기준 ("적합" / "불검출" / "음성" / "성상" 등) 처리.

    - non_detect kind: 실측값 0 이 아닌 경우 fail 이지만 Step C 는 보수적으로
      review_needed 처리 (담당자 불검출 확인 필요).
    - qualitative kind: requires_hitl=True → review_needed.
    - unknown kind: review_needed.
    """
    if is_dangerous is None:
        is_dangerous = (spec.injry_yn == "Y") if spec.injry_yn else None
    spec_text = spec.spec_val or ""
    eval_: SpecEvaluation = parse_non_numeric_spec(spec_text)
    status = "review_needed"
    # non_detect 계열은 자동 판정 불가 (실측값 측정 여부·검출한계 의존)
    if eval_.kind == "non_detect":
        status = "review_needed"
    elif eval_.kind == "qualitative":
        status = "review_needed"
    elif eval_.kind == "unknown":
        status = "review_needed"
    elif eval_.kind == "numeric":
        # parse_non_numeric_spec 가 방어적으로 numeric 으로 분류했으나 단위 불명
        status = "review_needed"

    return StandardCheck(
        ingredient_name=ingredient_name,
        test_category=spec.t_kor_nm,
        spec_raw=spec.spec_val,
        spec_summary=spec.spec_val_sumup,
        actual_value=None,
        unit_original=spec.unit_nm,
        unit_normalized=None,
        threshold_value=None,
        is_dangerous=is_dangerous,
        status=status,  # type: ignore[arg-type]
        law_ref=_law_ref_of(spec),
    )


def _law_ref_of(spec: AdditiveSpec) -> Optional[str]:
    """근거 법령 문자열 생성. SORC 없으면 기본 '식품첨가물공전'."""
    return spec.sorc or "식품첨가물공전"


def _evaluate_specs_for_test_category(
    test_category: Optional[str],
    specs: list[AdditiveSpec],
    *,
    measured: Optional[MeasuredValue],
    density: float,
    ingredient_name: str,
) -> StandardCheck:
    """T_KOR_NM 1건 분기.

    - '함량' → 수치 비교
    - '성상' / '확인시험' / '순도시험' / 기타 → 비수치 (review_needed)
    """
    # 유효 + 단일 채택
    latest = _pick_latest(specs)

    if test_category == _NUMERIC_TEST_CATEGORY:
        return _evaluate_numeric(
            latest, measured, density=density, ingredient_name=ingredient_name
        )
    if test_category == _QUALITATIVE_TEST_CATEGORY:
        return _evaluate_non_numeric(latest, ingredient_name=ingredient_name)
    if test_category in _HITL_TEST_CATEGORIES:
        return _evaluate_non_numeric(latest, ingredient_name=ingredient_name)

    # 알 수 없는 test_category — 수치로 시도해보고 실패하면 비수치
    min_raw, max_raw = _extract_min_max(latest)
    if min_raw is not None or max_raw is not None:
        return _evaluate_numeric(
            latest, measured, density=density, ingredient_name=ingredient_name
        )
    return _evaluate_non_numeric(latest, ingredient_name=ingredient_name)


# ============================================================
# API 조회
# ============================================================


async def _fetch_all_specs_for_ingredient(
    client: DataGoKrClient,
    name: str,
) -> tuple[list[AdditiveSpec], Optional[str]]:
    """한 원재료의 모든 페이지 조회 → AdditiveSpec 리스트.

    첫 페이지는 `get_additive_standard(name)` (Day 0 고수준 API 사용).
    후속 페이지는 `client.call(ADDITIVE_STANDARD, {"PC_KOR_NM": name,
    "pageNo": n})` 로 명시 순회. 결과는 response body (raw) 로 돌아오므로
    `response.body.items` 평탄화 필요.

    Returns:
        (specs, error_reason). error_reason 이 있으면 API 장애 (no_data).
    """
    # 지연 import — 순환 회피 및 테스트 단순화
    from services.data_go_kr import ADDITIVE_STANDARD

    aggregated: list[AdditiveSpec] = []
    try:
        # 1페이지: 고수준 API — items 리스트 + total_count 반환
        first = await client.get_additive_standard(name)
        first_items = first.get("items") or []
        total = int(first.get("total_count") or 0)
        for item in first_items:
            try:
                aggregated.append(AdditiveSpec.model_validate(item))
            except Exception:  # pragma: no cover - defensive
                logger.warning("Step C: AdditiveSpec validate failed item=%s", item)

        # 2페이지 이상 필요 여부: total > 첫페이지 items 수
        if total > len(first_items) and len(first_items) >= _PAGE_SIZE:
            for page_no in range(2, _MAX_PAGES + 1):
                body = await client.call(
                    ADDITIVE_STANDARD,
                    {"PC_KOR_NM": name, "pageNo": str(page_no)},
                )
                items = _extract_items_from_raw(body)
                if not items:
                    break
                for item in items:
                    try:
                        aggregated.append(AdditiveSpec.model_validate(item))
                    except Exception:  # pragma: no cover - defensive
                        logger.warning(
                            "Step C: AdditiveSpec validate failed item=%s", item
                        )
                if len(items) < _PAGE_SIZE or len(aggregated) >= total:
                    break
    except DataGoKrError as exc:
        logger.warning("Step C: data.go.kr error for %s: %s", name, exc)
        return aggregated, f"api_error:{exc.__class__.__name__}"
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Step C: unexpected error for %s", name)
        return aggregated, f"unexpected:{exc.__class__.__name__}"
    return aggregated, None


def _extract_items_from_raw(body: Any) -> list[dict[str, Any]]:
    """client.call() 반환 raw dict 에서 items 평탄화.

    data.go.kr 응답: {"response": {"header": {...}, "body": {"items": [...]}}}
    """
    if not isinstance(body, dict):
        return []
    resp = body.get("response")
    if not isinstance(resp, dict):
        return []
    body_dict = resp.get("body")
    if not isinstance(body_dict, dict):
        return []
    items = body_dict.get("items")
    if items in (None, "", []):
        return []
    if isinstance(items, list):
        return [x for x in items if isinstance(x, dict)]
    if isinstance(items, dict):
        inner = items.get("item")
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
        if isinstance(inner, dict):
            return [inner]
    return []


# ============================================================
# 공개 API
# ============================================================


async def run_step_c(
    ingredients: list[Ingredient],
    food_type_hierarchy: Any = None,
    measured_values: Optional[dict[str, MeasuredValue]] = None,
    *,
    client: Optional[DataGoKrClient] = None,
    today: Optional[date] = None,
) -> StepCResult:
    """원재료당 15116583 기준규격 조회 → T_KOR_NM별 집계 → 수치 비교.

    Args:
        ingredients: Step B 통과한 원재료 목록 (allow_verdict 반영).
        food_type_hierarchy: F2 확정 식품유형 계층 (Any — F2 타입 의존성 회피).
            food_type 속성/키로 food_type 추출하여 density · 식품유형 필터 주입.
        measured_values: 원재료명(Ingredient.name) → MeasuredValue 매핑.
            None 이면 비교 스킵하고 기준만 표시 (status="no_data").
        client: 테스트 주입용 DataGoKrClient. None 이면 env key 로 신규 생성.
        today: 테스트 주입용 참조일. None 이면 date.today().

    Returns:
        StepCResult — checks · overall_status · review_reasons.
    """
    # ingredients 사전 필터: prohibited 는 Step A/B 종료 흐름에서 제외됐어야 하나
    # 방어적으로 skip (03번 §3-1)
    target_ingredients: list[Ingredient] = [
        ing for ing in ingredients if (getattr(ing, "allow_verdict", None) != "prohibited")
    ]

    if not target_ingredients:
        return StepCResult(
            checks=[], overall_status="no_data", review_reasons=["no_target_ingredients"]
        )

    density = _resolve_density(food_type_hierarchy)
    food_type = _get_food_type(food_type_hierarchy)
    ref_date = today or date.today()

    # 클라이언트 준비
    owns_client = False
    if client is None:
        api_key = os.environ.get("F1_DATA_GO_KR_API_KEY", "")
        if not api_key:
            # 키 없으면 API 호출 자체 불가 → no_data
            return StepCResult(
                checks=[],
                overall_status="no_data",
                review_reasons=["data_go_kr_api_key_missing"],
            )
        client = DataGoKrClient(api_key=api_key)
        owns_client = True

    try:
        # 1) 원재료당 병렬 조회
        fetch_tasks = [
            _fetch_all_specs_for_ingredient(client, ing.name)
            for ing in target_ingredients
        ]
        fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=False)
    finally:
        if owns_client:
            try:
                await client.aclose()
            except Exception:  # pragma: no cover - defensive
                pass

    # 2) 원재료별 처리
    all_checks: list[StandardCheck] = []
    review_reasons: list[str] = []

    for ing, (specs, err) in zip(target_ingredients, fetch_results):
        if err is not None:
            review_reasons.append(f"api_error:{ing.name}:{err}")
            continue
        if not specs:
            # 기준 0건 — 이 원재료는 checks 에 기록하지 않음 (overall_status 계산에서 제외)
            # review_reasons 에 누적하지 않음 (03번 §5: no_data 는 담당자 확인이지 review 는 아님)
            continue

        # 3) 유효기간 필터
        active_specs = [s for s in specs if _is_active(s, ref_date)]
        if not active_specs:
            continue

        # 4) 식품유형 필터
        applicable_specs = [s for s in active_specs if _is_applicable(s, food_type)]
        if not applicable_specs:
            # 식품유형 한정된 기준만 있고 현재 food_type 에 해당 없음 → no_data
            continue

        # 5) T_KOR_NM 으로 집계
        grouped: dict[str, list[AdditiveSpec]] = defaultdict(list)
        for s in applicable_specs:
            key = s.t_kor_nm or "__unknown__"
            grouped[key].append(s)

        # 6) 시험항목별 평가
        measured = (measured_values or {}).get(ing.name)
        for test_category, group_specs in grouped.items():
            tc = None if test_category == "__unknown__" else test_category
            check = _evaluate_specs_for_test_category(
                tc,
                group_specs,
                measured=measured,
                density=density,
                ingredient_name=ing.name,
            )
            # INJRY_YN=Y 경고 누적
            if check.is_dangerous:
                review_reasons.append(
                    f"dangerous_item:{ing.name}:{tc or 'unknown'}"
                )
            if check.status == "review_needed":
                reason = f"review_needed:{ing.name}:{tc or 'unknown'}"
                if reason not in review_reasons:
                    review_reasons.append(reason)
            all_checks.append(check)

    # 7) overall_status 결정
    overall_status = _decide_overall_status(all_checks)

    return StepCResult(
        checks=all_checks,
        overall_status=overall_status,  # type: ignore[arg-type]
        review_reasons=review_reasons,
    )


def _decide_overall_status(checks: list[StandardCheck]) -> str:
    """overall_status 결정 (03번 §5).

    우선순위:
        1. checks 비어있음 → "no_data"
        2. 하나라도 "fail" → "fail"
        3. 하나라도 "review_needed" → "review_needed"
        4. 모든 pass (혹은 pass + no_data 섞임) → pass 가 1개 이상이면 "pass"
        5. 전부 no_data → "no_data"
    """
    if not checks:
        return "no_data"
    has_fail = any(c.status == "fail" for c in checks)
    if has_fail:
        return "fail"
    has_review = any(c.status == "review_needed" for c in checks)
    if has_review:
        return "review_needed"
    has_pass = any(c.status == "pass" for c in checks)
    if has_pass:
        return "pass"
    return "no_data"


__all__ = ["run_step_c"]
