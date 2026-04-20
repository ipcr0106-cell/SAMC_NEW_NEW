"""W2-C Step C (기준규격 수치 비교) 단위 테스트.

커버 시나리오 (03번 §10 테스트 포인트):
    - L-아스코르브산 + 87% → pass (기준 85% 이상)
    - L-아스코르브산 + 80% → fail
    - 성상/확인시험 행 → 출력 제외 (중간재 메타데이터 판정 범위 밖)
    - g/L 기준 + 비중 주입 → mg/kg 변환 정확
    - VALD_END_DT="99991231" → 적용
    - VALD_END_DT 오늘보다 과거 → 제외
    - 기준 row 0건 → no_data
    - INJRY_YN="Y" → is_dangerous 플래그 + 경고

실행:
    cd backend
    pytest tests/services/test_f1_step_c.py -v
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.f1_types import MeasuredValue, StepCResult
from models.judgment import Ingredient
from services.data_go_kr import AdditiveSpec
from services.f1_step_c import (
    _decide_overall_status,
    _evaluate_non_numeric,
    _evaluate_numeric,
    _extract_min_max,
    _is_active,
    _is_applicable,
    _pick_latest,
    _resolve_density,
    _safe_normalize,
    run_step_c,
)


# ============================================================
# 헬퍼
# ============================================================

FIXTURES = Path(__file__).parent.parent / "fixtures" / "f1_step_c"


def load_fixture(name: str) -> Dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def fixture_items(name: str) -> List[Dict[str, Any]]:
    """fixture raw → data_go_kr client 고수준 반환 포맷으로 변환 (items + total)."""
    raw = load_fixture(name)
    body = raw["response"]["body"]
    return list(body.get("items") or [])


def make_client_for_fixture(name: str, *, total_count: int | None = None) -> MagicMock:
    """get_additive_standard 가 fixture items 를 반환하도록 mock DataGoKrClient."""
    items = fixture_items(name)
    total = total_count if total_count is not None else len(items)
    client = MagicMock()
    client.get_additive_standard = AsyncMock(
        return_value={"items": items, "total_count": total, "raw": {}}
    )
    client.call = AsyncMock(return_value=load_fixture(name))  # pagination 미사용
    client.aclose = AsyncMock()
    return client


def make_client_multi(mapping: Dict[str, str]) -> MagicMock:
    """원재료명 → fixture 파일명 매핑."""
    client = MagicMock()

    async def _fetch(name: str) -> Dict[str, Any]:
        fixture = mapping.get(name)
        if fixture is None:
            return {"items": [], "total_count": 0, "raw": {}}
        items = fixture_items(fixture)
        return {"items": items, "total_count": len(items), "raw": {}}

    client.get_additive_standard = AsyncMock(side_effect=_fetch)
    client.call = AsyncMock(return_value={"response": {"body": {"items": []}}})
    client.aclose = AsyncMock()
    return client


def make_ingredient(name: str, allow: str = "allowed") -> Ingredient:
    return Ingredient(name=name, allow_verdict=allow)


@dataclass
class _FoodTypeStub:
    """Step C 가 Any 로 받는 food_type_hierarchy 의 미니 스텁."""

    food_type: str


# ============================================================
# 순수 함수 단위 테스트
# ============================================================


class TestHelpers:
    def test_resolve_density_default(self) -> None:
        assert _resolve_density(None) == 1.0

    def test_resolve_density_lookup(self) -> None:
        assert _resolve_density(_FoodTypeStub(food_type="음료류")) == 1.02

    def test_resolve_density_unknown_food_type(self) -> None:
        assert _resolve_density(_FoodTypeStub(food_type="우주식품")) == 1.0

    def test_resolve_density_dict(self) -> None:
        assert _resolve_density({"food_type": "간장"}) == 1.10

    def test_is_active_infinite(self) -> None:
        spec = AdditiveSpec(PC_KOR_NM="x", VALD_END_DT="99991231")
        assert _is_active(spec, date(2026, 4, 20)) is True

    def test_is_active_future(self) -> None:
        spec = AdditiveSpec(PC_KOR_NM="x", VALD_END_DT="20990101")
        assert _is_active(spec, date(2026, 4, 20)) is True

    def test_is_active_past(self) -> None:
        spec = AdditiveSpec(PC_KOR_NM="x", VALD_END_DT="20200101")
        assert _is_active(spec, date(2026, 4, 20)) is False

    def test_is_active_today(self) -> None:
        spec = AdditiveSpec(PC_KOR_NM="x", VALD_END_DT="20260420")
        assert _is_active(spec, date(2026, 4, 20)) is True

    def test_is_active_invalid_format_defaults_true(self) -> None:
        spec = AdditiveSpec(PC_KOR_NM="x", VALD_END_DT="not-a-date")
        assert _is_active(spec, date(2026, 4, 20)) is True

    def test_is_active_empty_end(self) -> None:
        spec = AdditiveSpec(PC_KOR_NM="x", VALD_END_DT="")
        assert _is_active(spec, date(2026, 4, 20)) is True

    def test_pick_latest_single(self) -> None:
        s = AdditiveSpec(PC_KOR_NM="x", LAST_UPDT_DTM="2020-01-01 00:00:00")
        assert _pick_latest([s]) is s

    def test_pick_latest_multiple(self) -> None:
        old = AdditiveSpec(PC_KOR_NM="x", LAST_UPDT_DTM="2015-01-01 00:00:00")
        new = AdditiveSpec(PC_KOR_NM="x", LAST_UPDT_DTM="2023-06-01 00:00:00")
        assert _pick_latest([old, new]) is new

    def test_is_applicable_no_summary_is_common(self) -> None:
        spec = AdditiveSpec(PC_KOR_NM="x")
        assert _is_applicable(spec, "음료류") is True

    def test_is_applicable_matches_food_type(self) -> None:
        spec = AdditiveSpec(
            PC_KOR_NM="x", SPEC_VAL_SUMUP="음료류의 함량은 0.1g/kg 이하"
        )
        assert _is_applicable(spec, "음료류") is True

    def test_is_applicable_mismatch(self) -> None:
        spec = AdditiveSpec(
            PC_KOR_NM="x", SPEC_VAL_SUMUP="유가공품의 함량은 0.1g/kg 이하"
        )
        assert _is_applicable(spec, "음료류") is False

    def test_is_applicable_generic_keyword(self) -> None:
        spec = AdditiveSpec(
            PC_KOR_NM="x", SPEC_VAL_SUMUP="일반 기준 적용"
        )
        assert _is_applicable(spec, "음료류") is True

    def test_extract_min_max_from_mimm_mxmm(self) -> None:
        spec = AdditiveSpec(PC_KOR_NM="x", MIMM_VAL="85.0", MXMM_VAL=None)
        assert _extract_min_max(spec) == (85.0, None)

    def test_extract_min_max_from_spec_val_parse(self) -> None:
        spec = AdditiveSpec(PC_KOR_NM="x", SPEC_VAL="0.01~0.1")
        assert _extract_min_max(spec) == (0.01, 0.1)

    def test_safe_normalize_percent(self) -> None:
        v, u, err = _safe_normalize(87.0, "%", density=1.0)
        assert err is None and u == "mg/kg" and v == 87.0 * 10_000

    def test_safe_normalize_gl_with_density(self) -> None:
        v, u, err = _safe_normalize(5.0, "g/L", density=1.02)
        assert err is None and u == "mg/kg"
        assert abs(v - (5.0 * 1000 / 1.02)) < 1e-6

    def test_safe_normalize_incompatible(self) -> None:
        v, u, err = _safe_normalize(1.0, "IU/kg", density=1.0)
        assert v is None and err is not None and "unit_incompatible" in err

    def test_safe_normalize_missing_unit(self) -> None:
        v, u, err = _safe_normalize(1.0, "", density=1.0)
        assert v is None and err == "unit_missing"

    def test_decide_overall_status_empty(self) -> None:
        assert _decide_overall_status([]) == "no_data"

    def test_decide_overall_status_fail_wins(self) -> None:
        from models.f1_types import StandardCheck

        checks = [
            StandardCheck(ingredient_name="a", status="pass"),
            StandardCheck(ingredient_name="a", status="fail"),
            StandardCheck(ingredient_name="a", status="review_needed"),
        ]
        assert _decide_overall_status(checks) == "fail"

    def test_decide_overall_status_review_beats_pass(self) -> None:
        from models.f1_types import StandardCheck

        checks = [
            StandardCheck(ingredient_name="a", status="pass"),
            StandardCheck(ingredient_name="a", status="review_needed"),
        ]
        assert _decide_overall_status(checks) == "review_needed"

    def test_decide_overall_status_all_pass(self) -> None:
        from models.f1_types import StandardCheck

        checks = [StandardCheck(ingredient_name="a", status="pass")]
        assert _decide_overall_status(checks) == "pass"


# ============================================================
# _evaluate_numeric / _evaluate_non_numeric
# ============================================================


class TestEvaluateNumeric:
    def test_ascorbic_acid_pass_at_87_percent(self) -> None:
        spec = AdditiveSpec(
            PC_KOR_NM="L-아스코르브산",
            T_KOR_NM="함량",
            SPEC_VAL="85.0이상",
            MIMM_VAL="85.0",
            UNIT_NM="%",
            INJRY_YN="N",
        )
        measured = MeasuredValue(value=87.0, unit="%", source="hitl_input")
        check = _evaluate_numeric(
            spec, measured, density=1.0, ingredient_name="L-아스코르브산"
        )
        assert check.status == "pass"
        assert check.unit_normalized == "mg/kg"
        assert check.threshold_value == 85.0 * 10_000
        assert check.is_dangerous is False

    def test_ascorbic_acid_fail_at_80_percent(self) -> None:
        spec = AdditiveSpec(
            PC_KOR_NM="L-아스코르브산",
            T_KOR_NM="함량",
            SPEC_VAL="85.0이상",
            MIMM_VAL="85.0",
            UNIT_NM="%",
            INJRY_YN="N",
        )
        measured = MeasuredValue(value=80.0, unit="%", source="hitl_input")
        check = _evaluate_numeric(
            spec, measured, density=1.0, ingredient_name="L-아스코르브산"
        )
        assert check.status == "fail"

    def test_no_measured_value_returns_no_data(self) -> None:
        spec = AdditiveSpec(
            PC_KOR_NM="L-아스코르브산",
            T_KOR_NM="함량",
            MIMM_VAL="85.0",
            UNIT_NM="%",
        )
        check = _evaluate_numeric(spec, None, density=1.0, ingredient_name="L-아스코르브산")
        assert check.status == "no_data"
        assert check.actual_value is None

    def test_gl_measured_with_density(self) -> None:
        """5 g/L (음료, density=1.02) → mg/kg ≈ 4902. 기준 0.6 g/L → max ≈ 588 mg/kg → fail."""
        spec = AdditiveSpec(
            PC_KOR_NM="액상첨가물",
            T_KOR_NM="함량",
            SPEC_VAL="0.6이하",
            MXMM_VAL="0.6",
            UNIT_NM="g/L",
            INJRY_YN="N",
        )
        measured = MeasuredValue(value=5.0, unit="g/L", source="hitl_input")
        check = _evaluate_numeric(
            spec, measured, density=1.02, ingredient_name="액상첨가물"
        )
        assert check.status == "fail"
        # 기준 0.6 g/L 정규화
        assert check.unit_normalized == "mg/kg"
        assert abs(check.threshold_value - (0.6 * 1000 / 1.02)) < 1e-6

    def test_gl_measured_under_threshold(self) -> None:
        """0.0005 g/L (매우 낮음) → mg/kg < 588 → pass."""
        spec = AdditiveSpec(
            PC_KOR_NM="액상첨가물",
            T_KOR_NM="함량",
            MXMM_VAL="0.6",
            UNIT_NM="g/L",
            INJRY_YN="N",
        )
        measured = MeasuredValue(value=0.0005, unit="g/L", source="hitl_input")
        check = _evaluate_numeric(
            spec, measured, density=1.02, ingredient_name="액상첨가물"
        )
        assert check.status == "pass"

    def test_incompatible_unit_review(self) -> None:
        spec = AdditiveSpec(
            PC_KOR_NM="x",
            T_KOR_NM="함량",
            MIMM_VAL="10",
            UNIT_NM="IU/kg",
        )
        measured = MeasuredValue(value=100.0, unit="IU/kg", source="hitl_input")
        check = _evaluate_numeric(spec, measured, density=1.0, ingredient_name="x")
        assert check.status == "review_needed"

    def test_dangerous_flag(self) -> None:
        spec = AdditiveSpec(
            PC_KOR_NM="x",
            T_KOR_NM="함량",
            MXMM_VAL="0.1",
            UNIT_NM="mg/kg",
            INJRY_YN="Y",
        )
        measured = MeasuredValue(value=0.05, unit="mg/kg", source="hitl_input")
        check = _evaluate_numeric(spec, measured, density=1.0, ingredient_name="x")
        assert check.is_dangerous is True
        assert check.status == "pass"


class TestEvaluateNonNumeric:
    def test_qualitative_spec(self) -> None:
        spec = AdditiveSpec(
            PC_KOR_NM="x",
            T_KOR_NM="성상",
            SPEC_VAL="이 품목은 백색의 결정이다",
        )
        check = _evaluate_non_numeric(spec, ingredient_name="x")
        assert check.status == "review_needed"

    def test_confirmation_spec_suitable(self) -> None:
        spec = AdditiveSpec(
            PC_KOR_NM="x",
            T_KOR_NM="확인시험",
            SPEC_VAL="적합",
        )
        check = _evaluate_non_numeric(spec, ingredient_name="x")
        assert check.status == "review_needed"

    def test_non_detect(self) -> None:
        spec = AdditiveSpec(
            PC_KOR_NM="x",
            T_KOR_NM="순도시험",
            SPEC_VAL="불검출",
        )
        check = _evaluate_non_numeric(spec, ingredient_name="x")
        assert check.status == "review_needed"


# ============================================================
# run_step_c 통합 시나리오
# ============================================================


@pytest.mark.asyncio
class TestRunStepC:
    async def test_ascorbic_acid_pass_scenario(self) -> None:
        client = make_client_for_fixture("ascorbic_acid.json")
        result: StepCResult = await run_step_c(
            ingredients=[make_ingredient("L-아스코르브산")],
            food_type_hierarchy=None,
            measured_values={
                "L-아스코르브산": MeasuredValue(value=87.0, unit="%", source="hitl_input")
            },
            client=client,
            today=date(2026, 4, 20),
        )
        # 함량 pass 1건만 출력 (성상/확인시험은 중간재 메타데이터로 제외)
        assert len(result.checks) == 1
        statuses = {c.test_category: c.status for c in result.checks}
        assert statuses["함량"] == "pass"
        assert "성상" not in statuses
        assert "확인시험" not in statuses
        assert result.overall_status == "pass"

    async def test_ascorbic_acid_fail_scenario(self) -> None:
        client = make_client_for_fixture("ascorbic_acid.json")
        result = await run_step_c(
            ingredients=[make_ingredient("L-아스코르브산")],
            food_type_hierarchy=None,
            measured_values={
                "L-아스코르브산": MeasuredValue(value=80.0, unit="%", source="hitl_input")
            },
            client=client,
            today=date(2026, 4, 20),
        )
        # 함량 fail 이 overall 지배
        assert result.overall_status == "fail"

    async def test_empty_standards_no_data(self) -> None:
        client = make_client_for_fixture("empty.json", total_count=0)
        result = await run_step_c(
            ingredients=[make_ingredient("존재하지않는물질")],
            food_type_hierarchy=None,
            measured_values=None,
            client=client,
            today=date(2026, 4, 20),
        )
        assert result.checks == []
        assert result.overall_status == "no_data"

    async def test_expired_standard_filtered_out(self) -> None:
        """구기준(20150101 종료) + 신기준(99991231) 공존 → 신기준만 채택."""
        client = make_client_for_fixture("expired_standard.json")
        result = await run_step_c(
            ingredients=[make_ingredient("구기준물질")],
            food_type_hierarchy=None,
            measured_values={
                "구기준물질": MeasuredValue(value=70.0, unit="%", source="hitl_input")
            },
            client=client,
            today=date(2026, 4, 20),
        )
        # 구기준(50% 이상) 은 만료 → 신기준(80% 이상) 채택 → 70% → fail
        assert result.overall_status == "fail"
        # check 는 함량 1건 (신기준, LAST_UPDT_DTM 최신)
        hit = [c for c in result.checks if c.test_category == "함량"]
        assert len(hit) == 1
        assert hit[0].spec_raw == "80.0이상"

    async def test_gl_liquid_fail_with_density(self) -> None:
        """음료류(density 1.02) + 기준 0.6 g/L + 실측 5 g/L → fail."""
        client = make_client_for_fixture("liquid_gl.json")
        result = await run_step_c(
            ingredients=[make_ingredient("액상첨가물")],
            food_type_hierarchy=_FoodTypeStub(food_type="음료류"),
            measured_values={
                "액상첨가물": MeasuredValue(value=5.0, unit="g/L", source="hitl_input")
            },
            client=client,
            today=date(2026, 4, 20),
        )
        assert result.overall_status == "fail"

    async def test_dangerous_injry_yn_flags_review(self) -> None:
        client = make_client_for_fixture("dangerous_item.json")
        result = await run_step_c(
            ingredients=[make_ingredient("유해주의물질")],
            food_type_hierarchy=None,
            measured_values={
                "유해주의물질": MeasuredValue(
                    value=0.05, unit="mg/kg", source="hitl_input"
                )
            },
            client=client,
            today=date(2026, 4, 20),
        )
        assert result.overall_status == "pass"
        assert len(result.checks) == 1
        assert result.checks[0].is_dangerous is True
        # review_reasons 에 위험 항목 경고 누적
        assert any("dangerous_item" in r for r in result.review_reasons)

    async def test_prohibited_ingredient_skipped(self) -> None:
        """allow_verdict=prohibited 는 Step C 에서 조회 제외."""
        client = make_client_for_fixture("empty.json", total_count=0)
        result = await run_step_c(
            ingredients=[make_ingredient("금지물질", allow="prohibited")],
            food_type_hierarchy=None,
            measured_values=None,
            client=client,
            today=date(2026, 4, 20),
        )
        assert result.overall_status == "no_data"
        # API 호출 자체가 일어나지 않음 (target 없음)
        client.get_additive_standard.assert_not_called()

    async def test_measured_values_none_leaves_threshold_only(self) -> None:
        client = make_client_for_fixture("ascorbic_acid.json")
        result = await run_step_c(
            ingredients=[make_ingredient("L-아스코르브산")],
            food_type_hierarchy=None,
            measured_values=None,
            client=client,
            today=date(2026, 4, 20),
        )
        # 실측값 없음 + 성상/확인시험은 제외 → 함량만 no_data
        assert len(result.checks) == 1
        quant = result.checks[0]
        assert quant.test_category == "함량"
        assert quant.status == "no_data"
        assert quant.actual_value is None
        assert quant.threshold_value == 85.0 * 10_000
        # 함량만 no_data → overall no_data
        assert result.overall_status == "no_data"

    async def test_api_error_propagates_to_review_reasons(self) -> None:
        """data.go.kr 장애 → api_error:{name} 사유 누적 + checks 비어있음."""
        from exceptions import DataGoKrTimeoutError

        client = MagicMock()
        client.get_additive_standard = AsyncMock(
            side_effect=DataGoKrTimeoutError(
                "timeout", endpoint="15116583", timeout_s=1.0
            )
        )
        client.call = AsyncMock()
        client.aclose = AsyncMock()
        result = await run_step_c(
            ingredients=[make_ingredient("L-아스코르브산")],
            food_type_hierarchy=None,
            measured_values=None,
            client=client,
            today=date(2026, 4, 20),
        )
        assert result.overall_status == "no_data"
        assert any(r.startswith("api_error:") for r in result.review_reasons)

    async def test_no_env_api_key_returns_no_data(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """client 주입 없고 환경변수 key 도 없으면 no_data."""
        monkeypatch.delenv("F1_DATA_GO_KR_API_KEY", raising=False)
        result = await run_step_c(
            ingredients=[make_ingredient("L-아스코르브산")],
            food_type_hierarchy=None,
            measured_values=None,
            client=None,
            today=date(2026, 4, 20),
        )
        assert result.overall_status == "no_data"
        assert "data_go_kr_api_key_missing" in result.review_reasons

    async def test_no_target_ingredients_prohibited_only(self) -> None:
        result = await run_step_c(
            ingredients=[make_ingredient("금지물질", allow="prohibited")],
            food_type_hierarchy=None,
            measured_values=None,
            client=MagicMock(aclose=AsyncMock()),
            today=date(2026, 4, 20),
        )
        # target 0 → no_data + no_target_ingredients 사유
        assert result.overall_status == "no_data"
        assert "no_target_ingredients" in result.review_reasons

    async def test_food_type_filter_excludes_non_matching(self) -> None:
        """SPEC_VAL_SUMUP 에 다른 식품유형 명시 → 현재 food_type 에 해당 없음 → no_data."""
        items = [
            {
                "PC_KOR_NM": "x",
                "T_KOR_NM": "함량",
                "SPEC_VAL": "0.1이하",
                "MXMM_VAL": "0.1",
                "UNIT_NM": "mg/kg",
                "SPEC_VAL_SUMUP": "유가공품에 한하여 0.1 mg/kg 이하",
                "INJRY_YN": "N",
                "VALD_END_DT": "99991231",
                "LAST_UPDT_DTM": "2020-12-04 10:46:20",
            }
        ]
        client = MagicMock()
        client.get_additive_standard = AsyncMock(
            return_value={"items": items, "total_count": 1, "raw": {}}
        )
        client.call = AsyncMock()
        client.aclose = AsyncMock()
        result = await run_step_c(
            ingredients=[make_ingredient("x")],
            food_type_hierarchy=_FoodTypeStub(food_type="음료류"),
            measured_values=None,
            client=client,
            today=date(2026, 4, 20),
        )
        assert result.overall_status == "no_data"
        assert result.checks == []

    async def test_pagination_fetches_subsequent_pages(self) -> None:
        """총 건수가 첫 페이지를 넘으면 pageNo=2 호출해야 한다."""
        page1_items = [
            {
                "PC_KOR_NM": "big",
                "T_KOR_NM": "함량",
                "SPEC_VAL": f"{i}.0이상",
                "MIMM_VAL": f"{i}.0",
                "UNIT_NM": "%",
                "INJRY_YN": "N",
                "VALD_END_DT": "99991231",
                "LAST_UPDT_DTM": "2020-01-01 00:00:00",
            }
            for i in range(50)
        ]
        page2_raw = {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "pageNo": 2,
                    "numOfRows": 50,
                    "totalCount": 51,
                    "items": [
                        {
                            "PC_KOR_NM": "big",
                            "T_KOR_NM": "순도시험",
                            "SPEC_VAL": "적합",
                            "UNIT_NM": None,
                            "INJRY_YN": "N",
                            "VALD_END_DT": "99991231",
                            "LAST_UPDT_DTM": "2020-01-01 00:00:00",
                        }
                    ],
                },
            }
        }
        client = MagicMock()
        client.get_additive_standard = AsyncMock(
            return_value={"items": page1_items, "total_count": 51, "raw": {}}
        )
        client.call = AsyncMock(return_value=page2_raw)
        client.aclose = AsyncMock()
        result = await run_step_c(
            ingredients=[make_ingredient("big")],
            food_type_hierarchy=None,
            measured_values=None,
            client=client,
            today=date(2026, 4, 20),
        )
        # pagination 호출됐는지 확인
        client.call.assert_called_once()
        # 순도시험은 중간재 메타데이터로 제외 → 함량(page1 최신 1건)만 남음
        categories = {c.test_category for c in result.checks}
        assert "순도시험" not in categories
        assert "함량" in categories


# ============================================================
# T2 신규: 식품유형 매칭 fallback edge case 5건
# ============================================================


class TestFoodTypeMatchingFallback:
    """T2 — _is_applicable 식품유형 매칭 fallback edge case."""

    # F-01: 상위 카테고리 fallback — 탁주 → 주류 매칭
    def test_f01_parent_category_fallback(self) -> None:
        """탁주(food_type)가 '주류'만 언급하는 기준에 fallback 매칭."""
        spec = AdditiveSpec(
            PC_KOR_NM="x",
            SPEC_VAL_SUMUP="주류의 함량은 0.1 mg/kg 이하",
        )
        # 탁주 → 상위 카테고리 주류로 fallback
        assert _is_applicable(spec, "탁주") is True

    # F-02: 하위 카테고리가 상위와 다른 경우 미매칭
    def test_f02_unrelated_category_miss(self) -> None:
        """음료류 기준에 유가공품을 매칭 시도 → False (fallback 없음)."""
        spec = AdditiveSpec(
            PC_KOR_NM="x",
            SPEC_VAL_SUMUP="음료류에 한하여 적용",
        )
        assert _is_applicable(spec, "유가공품") is False

    # F-03: 공통 키워드 "공통" 추가 인식
    def test_f03_generic_keyword_gongtoong(self) -> None:
        """'공통 기준 적용' → 공통 취급 (True)."""
        spec = AdditiveSpec(
            PC_KOR_NM="x",
            SPEC_VAL_SUMUP="공통 기준 적용",
        )
        assert _is_applicable(spec, "음료류") is True

    # F-04: 공통 키워드 "식품일반" 인식
    def test_f04_generic_keyword_sikpum_general(self) -> None:
        """'식품일반에 적용' → 공통 취급 (True)."""
        spec = AdditiveSpec(
            PC_KOR_NM="x",
            FNPRT_ITM_NM="식품일반",
        )
        assert _is_applicable(spec, "탁주") is True

    # F-05: food_type=None 일 때 모두 통과
    def test_f05_none_food_type_passes_all(self) -> None:
        """food_type=None 이면 한정 표현이 있어도 True (필터 없음)."""
        spec = AdditiveSpec(
            PC_KOR_NM="x",
            SPEC_VAL_SUMUP="유가공품에만 적용",
        )
        assert _is_applicable(spec, None) is True


class TestExtractItemsFromRaw:
    def test_empty_response(self) -> None:
        from services.f1_step_c import _extract_items_from_raw

        assert _extract_items_from_raw(None) == []
        assert _extract_items_from_raw({}) == []
        assert _extract_items_from_raw({"response": {"body": {"items": None}}}) == []

    def test_items_as_list(self) -> None:
        from services.f1_step_c import _extract_items_from_raw

        body = {"response": {"body": {"items": [{"a": 1}, {"b": 2}]}}}
        assert _extract_items_from_raw(body) == [{"a": 1}, {"b": 2}]

    def test_items_as_dict_with_item_list(self) -> None:
        from services.f1_step_c import _extract_items_from_raw

        body = {"response": {"body": {"items": {"item": [{"a": 1}]}}}}
        assert _extract_items_from_raw(body) == [{"a": 1}]

    def test_items_as_dict_with_single_item(self) -> None:
        from services.f1_step_c import _extract_items_from_raw

        body = {"response": {"body": {"items": {"item": {"a": 1}}}}}
        assert _extract_items_from_raw(body) == [{"a": 1}]
