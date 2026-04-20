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
    7. 시험항목 분기: "함량"만 수치 비교, "성상"/"확인시험"/"순도시험" 등 비수치
       메타데이터는 중간재 판정 범위 밖으로 출력에서 제외.
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
_GENERIC_FOOD_TYPE_TOKENS = ("일반", "모든 식품", "전체", "식품일반", "모든식품", "공통")

# 식품유형 상위 카테고리 매핑 (fallback용)
# 현재 food_type 이 하위 카테고리일 때 상위 카테고리로 재매칭 시도
_FOOD_TYPE_PARENT_MAP: dict[str, tuple[str, ...]] = {
    # 주류 계열
    "탁주": ("주류",),
    "청주": ("주류",),
    "맥주": ("주류",),
    "과실주": ("주류",),
    "소주": ("주류",),
    "위스키": ("주류", "증류주"),
    "브랜디": ("주류", "증류주"),
    "일반증류주": ("주류", "증류주"),
    # 유제품 계열
    "우유": ("유가공품", "유류"),
    "발효유": ("유가공품",),
    "치즈": ("유가공품",),
    "버터": ("유가공품",),
    "분유": ("유가공품",),
    # 음료 계열
    "탄산음료": ("음료류",),
    "과채음료": ("음료류",),
    "혼합음료": ("음료류",),
    "인삼음료": ("음료류",),
    # 과자류 계열
    "과자": ("과자류",),
    "캔디류": ("과자류",),
    "빙과류": ("과자류",),
    "초콜릿류": ("과자류",),
    # 면류 계열
    "국수": ("면류",),
    "냉면": ("면류",),
    "당면": ("면류",),
    # 식용유지 계열
    "대두유": ("식용유지류", "식용유지"),
    "옥수수유": ("식용유지류", "식용유지"),
    "올리브유": ("식용유지류", "식용유지"),
    "해바라기유": ("식용유지류", "식용유지"),
    # 수산물 계열
    "어류": ("수산물", "수산가공품"),
    "패류": ("수산물", "수산가공품"),
    "갑각류": ("수산물", "수산가공품"),
}


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
    """식품유형 매칭 (03번 §7, T2 fallback 보강).

    SPEC_VAL_SUMUP / FNPRT_ITM_NM 에 식품유형 한정 표현이 있으면
    - 해당 food_type 이 포함된 경우에만 채택
    - 한정 표현이 없거나 "일반/모든 식품" 류면 공통으로 채택
    - 직접 매칭 실패 시 상위 카테고리로 재매칭 시도 (fallback a)
    - 상위 카테고리도 miss 시 review_needed 처리를 위해 False 반환 (fallback b)
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
    # 직접 매칭
    if food_type in summary:
        return True
    # fallback (a): 상위 카테고리로 재매칭 시도
    parent_types = _FOOD_TYPE_PARENT_MAP.get(food_type, ())
    for parent in parent_types:
        if parent in summary:
            return True
    # fallback (b): 매칭 실패 → False (호출자가 review_needed 처리)
    return False


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
) -> Optional[StandardCheck]:
    """T_KOR_NM 1건 분기.

    - '함량' → 수치 비교
    - '성상' / '확인시험' / '순도시험' → None (중간재 메타데이터는 판정 범위 외)
    - 기타: MIMM/MXMM 값이 있으면 수치 비교, 없으면 None
    """
    # 비수치 메타데이터는 판정 대상 아님 (중간재 물성 검증은 F1 범위 밖)
    if test_category == _QUALITATIVE_TEST_CATEGORY:
        return None
    if test_category in _HITL_TEST_CATEGORIES:
        return None

    # 유효 + 단일 채택
    latest = _pick_latest(specs)

    if test_category == _NUMERIC_TEST_CATEGORY:
        return _evaluate_numeric(
            latest, measured, density=density, ingredient_name=ingredient_name
        )

    # 알 수 없는 test_category — 수치 값 있으면 평가, 없으면 스킵
    min_raw, max_raw = _extract_min_max(latest)
    if min_raw is not None or max_raw is not None:
        return _evaluate_numeric(
            latest, measured, density=density, ingredient_name=ingredient_name
        )
    return None


# ============================================================
# API 조회
# ============================================================


async def _fetch_all_specs_for_ingredient(
    client: DataGoKrClient,
    name: str,
) -> tuple[list[AdditiveSpec], Optional[str]]:
    """safetydata.go.kr 식품공전 스냅샷(f1_safetydata_food_code)에서 조회.

    배경: data.go.kr 15116583 `PC_KOR_NM` 필터가 서버측에서 미작동하여
    엉뚱한 기준치가 반환되는 버그를 회피. safetydata.go.kr 전수 스냅샷을
    Supabase에 적재 후 ILIKE/trgm 검색.

    `client` 인자는 시그니처 호환을 위해 유지하지만 실제로 사용하지 않음.

    Returns:
        (specs, error_reason). error_reason 이 있으면 조회 장애 (no_data).

    참조:
        .omc/research/f1_api_15111777_filter_issue.md
        backend/scripts/f1_sync_safetydata.py
    """
    from services.safetydata_client import lookup_food_additive

    # 결함 #1 수정: Silent masking 제거 — 예외를 catch하지 않고 전파.
    # 호출부(run_step_c)의 asyncio.gather 가 return_exceptions=True 로 수집하여
    # api_error 사유로 처리한다.
    # 식품첨가물공전(f1_safetydata_food_additive)만 조회 — 식품공전 전체
    # (f1_safetydata_food_code)를 조회하면 쌀·사과 등 일반 원료에도 기준치가
    # 반환되어 전부 review_needed 오판되는 Bug 1 회귀를 유발한다.
    records = await lookup_food_additive(name)

    aggregated: list[AdditiveSpec] = []
    for r in records:
        raw = {
            "PC_KOR_NM": r.item_korn_nm,
            "T_KOR_NM": r.test_artcl_korn_nm,
            "FNPRT_ITM_NM": r.spcs_artcl_nm,
            "SPEC_VAL": r.crtr_spcfct_vl,
            "SPEC_VAL_SUMUP": r.crtr_spcfct_vl_smry,
            "MIMM_VAL": r.min_vl,
            "MXMM_VAL": r.max_vl,
            "UNIT_NM": r.unit_nm,
            "INJRY_YN": r.hzr_yn,
            "VALD_BEGN_DT": None,
            "VALD_END_DT": None,
            "SORC": r.src or "식품첨가물공전",
        }
        try:
            aggregated.append(AdditiveSpec.model_validate(raw))
        except Exception:  # pragma: no cover - defensive
            logger.warning("Step C: AdditiveSpec adapter validate failed raw=%s", raw)
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
    # Step C = 식품첨가물 기준규격 조회:
    #   - restricted / unidentified → 항상 포함 (조건 또는 미지 원료)
    #   - allowed + 식품첨가물 출처 → 포함 (사용량 기준 확인 필요)
    #   - allowed + 식품원료(별표1)/db_fallback → 제외 (첨가물 기준 없음)
    #   - prohibited / permitted → 제외
    target_ingredients: list[Ingredient] = [
        ing for ing in ingredients
        if getattr(ing, "allow_verdict", None) in ("restricted", "unidentified")
        or (
            getattr(ing, "allow_verdict", None) == "allowed"
            and "식품첨가물" in (getattr(ing, "law_source", None) or "")
        )
    ]

    if not target_ingredients:
        return StepCResult(
            checks=[], overall_status="no_data", review_reasons=["no_target_ingredients"]
        )

    density = _resolve_density(food_type_hierarchy)
    food_type = _get_food_type(food_type_hierarchy)
    ref_date = today or date.today()

    # 클라이언트 준비 — Step C는 safetydata.go.kr 로컬 DB를 사용하므로
    # data.go.kr API 키가 없어도 정상 동작한다.
    owns_client = False
    if client is None:
        api_key = os.environ.get("F1_DATA_GO_KR_API_KEY", "")
        if api_key:
            client = DataGoKrClient(api_key=api_key)
            owns_client = True
        # API 키 없어도 safetydata 조회로 계속 진행

    try:
        # 1) 원재료당 병렬 조회
        # 결함 #6 수정: 전체 gather 에 60초 타임아웃 적용.
        # 결함 #1 수정: return_exceptions=True 로 개별 예외를 값으로 수집하여
        #   Silent masking 없이 api_error 사유로 처리.
        async def _fetch_with_fallback_names(client, ing):
            """여러 이름 변형으로 시도: matched_name_ko → 원본명 → 괄호제거명."""
            names_to_try = []
            matched = (ing.matched_name_ko or "").strip()
            if matched:
                names_to_try.append(matched)
            raw = (ing.name or "").strip()
            if raw and raw != matched:
                names_to_try.append(raw)
            # 괄호 이전 한글명 (예: "이산화황(산화방지제)" → "이산화황")
            paren = raw.find("(") if raw else -1
            if paren > 0:
                short = raw[:paren].strip()
                if short and short not in names_to_try:
                    names_to_try.append(short)

            for name in names_to_try:
                result = await _fetch_all_specs_for_ingredient(client, name)
                if result[0]:  # specs가 있으면 반환
                    return result
            return ([], None)

        fetch_tasks = [
            _fetch_with_fallback_names(client, ing)
            for ing in target_ingredients
        ]
        fetch_results = await asyncio.wait_for(
            asyncio.gather(*fetch_tasks, return_exceptions=True),
            timeout=60.0,
        )
    finally:
        if owns_client:
            try:
                await client.aclose()
            except Exception:  # pragma: no cover - defensive
                pass

    # 2) 원재료별 처리
    all_checks: list[StandardCheck] = []
    review_reasons: list[str] = []

    for ing, fetch_result in zip(target_ingredients, fetch_results):
        # return_exceptions=True 이므로 예외 인스턴스가 올 수 있음
        if isinstance(fetch_result, BaseException):
            logger.exception(
                "Step C: fetch failed for %s: %s",
                ing.name,
                fetch_result,
                exc_info=fetch_result,
            )
            review_reasons.append(
                f"api_error:{ing.name}:{fetch_result.__class__.__name__}"
            )
            continue
        specs, err = fetch_result
        if err is not None:
            review_reasons.append(f"api_error:{ing.name}:{err}")
            continue
        if not specs:
            # API 0건 — 기준규격 자체가 없는 물질 (전체 no_data 로 처리)
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
        ing_checks_before = len(all_checks)
        for test_category, group_specs in grouped.items():
            tc = None if test_category == "__unknown__" else test_category
            check = _evaluate_specs_for_test_category(
                tc,
                group_specs,
                measured=measured,
                density=density,
                ingredient_name=ing.name,
            )
            if check is None:
                continue
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

        # 결함 #12 수정: applicable_specs 는 있으나 평가 가능한 시험항목이 전혀 없는
        # 원재료("기준 있음, 수치 비교 불가")를 checks 에 no_data 로 명시적 기록.
        # — UI 까지 "기준 없음" 상태가 전달될 수 있도록 한다 (03번 §5).
        if len(all_checks) == ing_checks_before:
            all_checks.append(
                StandardCheck(
                    ingredient_name=ing.name,
                    test_category=None,
                    spec_raw=None,
                    spec_summary=None,
                    actual_value=None,
                    unit_original=None,
                    unit_normalized=None,
                    threshold_value=None,
                    is_dangerous=None,
                    status="no_data",  # type: ignore[arg-type]
                    law_ref=None,
                )
            )

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
