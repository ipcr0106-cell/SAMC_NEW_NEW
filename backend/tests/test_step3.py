"""F1 Step 3 unit tests — standards check (additive limits + safety + liquor).

Mock strategy:
    - _fetch_additive_limits / _fetch_safety_standards / check_liquor_safety
      all call get_supabase() internally. We monkeypatch get_supabase to
      return mocks with different .table()/.rpc() chains.
    - Pure functions (_is_alcohol_food, _check_additive_single, _safety_to_check)
      tested directly without DB.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from models.judgment import Ingredient, LimitCheckResult, ProcessConditions
from services.step3_standards import (
    _is_alcohol_food,
    _check_additive_single,
    _safety_to_check,
    run_step3,
    check_liquor_safety,
)
from constants.thresholds_config import is_alcohol_boundary


# ============================================================
# _is_alcohol_food (pure)
# ============================================================


class TestIsAlcoholFood:
    def test_liquor_food_type(self):
        assert _is_alcohol_food("증류주", ProcessConditions()) is True

    def test_liquor_keyword_in_compound(self):
        assert _is_alcohol_food("기타주류(리큐르)", ProcessConditions()) is True

    def test_distilled_process(self):
        assert _is_alcohol_food("과자", ProcessConditions(is_distilled=True)) is True

    def test_high_alcohol(self):
        pc = ProcessConditions(alcohol_percentage=5.0)
        assert _is_alcohol_food("음료", pc) is True

    def test_low_alcohol_not_liquor(self):
        pc = ProcessConditions(alcohol_percentage=0.3)
        assert _is_alcohol_food("음료", pc) is False

    def test_normal_food(self):
        assert _is_alcohol_food("과자", ProcessConditions()) is False

    def test_none_food_type(self):
        assert _is_alcohol_food(None, ProcessConditions()) is False


# ============================================================
# _check_additive_single (pure — no DB, tests unit conversion logic)
# ============================================================

ADD_ROW = {
    "additive_name": "소르빈산",
    "max_ppm": 1000,
    "condition_text": None,
    "regulation_ref": "식품첨가물공전",
    "conversion_factor": None,
}


class TestCheckAdditiveSingle:
    def test_pass_within_limit(self):
        ing = Ingredient(name="소르빈산", percentage=0.05)
        r = _check_additive_single(ing, ADD_ROW, ProcessConditions())
        assert r.status == "pass"
        assert r.category == "additive"
        assert "ppm" in r.max_limit

    def test_fail_exceeds_limit(self):
        ing = Ingredient(name="소르빈산", percentage=0.2)  # 2000 ppm > 1000
        r = _check_additive_single(ing, ADD_ROW, ProcessConditions())
        assert r.status == "fail"

    def test_no_percentage_returns_no_data(self):
        ing = Ingredient(name="소르빈산", percentage=None)
        r = _check_additive_single(ing, ADD_ROW, ProcessConditions())
        assert r.status == "no_data"

    def test_max_ppm_null_means_banned(self):
        row = {**ADD_ROW, "max_ppm": None}
        ing = Ingredient(name="금지첨가물", percentage=0.01)
        r = _check_additive_single(ing, row, ProcessConditions())
        assert r.status == "fail"
        assert r.max_limit == "사용불가"

    def test_heat_condition_skipped_when_not_heated(self):
        row = {**ADD_ROW, "condition_text": "가열제품 한정"}
        ing = Ingredient(name="소르빈산", percentage=0.05)
        r = _check_additive_single(ing, row, ProcessConditions(is_heated=False))
        assert r.status == "no_data"

    def test_heat_condition_applied_when_heated(self):
        row = {**ADD_ROW, "condition_text": "가열제품 한정"}
        ing = Ingredient(name="소르빈산", percentage=0.05)
        r = _check_additive_single(ing, row, ProcessConditions(is_heated=True))
        assert r.status == "pass"

    def test_regulation_ref_preserved(self):
        ing = Ingredient(name="소르빈산", percentage=0.05)
        r = _check_additive_single(ing, ADD_ROW, ProcessConditions())
        assert r.regulation_ref == "식품첨가물공전"


# ============================================================
# _safety_to_check (pure)
# ============================================================


class TestSafetyToCheck:
    def test_heavy_metal(self):
        row = {"target_name": "납", "standard_type": "heavy_metal",
               "max_limit": "0.1 mg/kg", "regulation_ref": "식품공전"}
        r = _safety_to_check(row)
        assert r.item_name == "납"
        assert r.category == "heavy_metal"
        assert r.max_limit == "0.1 mg/kg"
        assert r.status == "no_data"

    def test_microbe(self):
        row = {"target_name": "대장균", "standard_type": "microbe",
               "max_limit": "음성", "regulation_ref": None}
        r = _safety_to_check(row)
        assert r.category == "microbe"

    def test_unknown_type_fallback(self):
        row = {"target_name": "미지물", "standard_type": "unknown_xyz",
               "max_limit": "1.0", "regulation_ref": None}
        r = _safety_to_check(row)
        assert r.category == "contaminant"


# ============================================================
# is_alcohol_boundary (pure — from thresholds_config)
# ============================================================


class TestIsAlcoholBoundary:
    def test_none(self):
        assert is_alcohol_boundary(None) is False

    def test_zero(self):
        assert is_alcohol_boundary(0) is False

    def test_below_non_alcohol(self):
        assert is_alcohol_boundary(0.4) is False

    def test_boundary_lower(self):
        assert is_alcohol_boundary(0.5) is True

    def test_boundary_mid(self):
        assert is_alcohol_boundary(0.7) is True

    def test_boundary_upper_exclusive(self):
        assert is_alcohol_boundary(1.0) is False

    def test_clearly_alcohol(self):
        assert is_alcohol_boundary(5.0) is False


# ============================================================
# run_step3 — integration with mocked DB
# ============================================================


def _mock_supabase_step3(additive_rows=None, safety_rows=None, liquor_rows=None):
    """Build a supabase mock for step3.

    step3 calls:
    1. _fetch_additive_limits → .table("f1_additive_limits").select().eq().in_().in_().execute()
    2. _fetch_safety_standards → .table("f1_safety_standards").select().eq().in_().in_().execute()
    3. check_liquor_safety → .table("f1_safety_standards").select().eq().eq().ilike().limit().execute() x4
    """
    mock = MagicMock()

    call_count = {"n": 0}
    all_results = [additive_rows or [], safety_rows or []]

    def _table_chain(*args, **kwargs):
        chain = MagicMock()
        # For _fetch_additive_limits and _fetch_safety_standards (in_ chain)
        in_exec = MagicMock()
        idx = call_count["n"]
        call_count["n"] += 1
        if idx < len(all_results):
            in_exec.return_value = MagicMock(data=all_results[idx])
        else:
            in_exec.return_value = MagicMock(data=[])
        chain.select.return_value.eq.return_value.in_.return_value.in_.return_value.execute = in_exec

        # For check_liquor_safety (ilike chain)
        ilike_exec = MagicMock()
        ilike_exec.return_value = MagicMock(data=liquor_rows or [])
        chain.select.return_value.eq.return_value.eq.return_value.ilike.return_value.limit.return_value.execute = ilike_exec

        return chain

    mock.table = _table_chain
    return mock


class TestRunStep3:
    def test_no_food_type_returns_review_needed(self, monkeypatch):
        """food_type=None → review_needed + escalation."""
        result = run_step3([], None)
        assert result.overall_status == "review_needed"
        assert any(e["trigger_type"] == "no_data" for e in result.escalations)

    def test_empty_ingredients_no_additive_data(self, monkeypatch):
        sb = _mock_supabase_step3([], [])
        monkeypatch.setattr("services.step3_standards.get_supabase", lambda: sb)
        result = run_step3([], "과자류")
        assert result.overall_status == "review_needed"
        assert result.checks == []

    def test_additive_pass(self, monkeypatch):
        add_rows = [{
            "additive_name": "소르빈산", "food_type": "과자류",
            "max_ppm": 1000, "combined_group": None, "combined_max": None,
            "conversion_factor": None, "colorant_category": None,
            "total_tar_limit": None, "condition_text": None,
            "regulation_ref": "식품첨가물공전",
        }]
        sb = _mock_supabase_step3(add_rows, [])
        monkeypatch.setattr("services.step3_standards.get_supabase", lambda: sb)
        ingredients = [Ingredient(name="소르빈산", percentage=0.05)]
        result = run_step3(ingredients, "과자류")
        assert any(c.item_name == "소르빈산" and c.status == "pass" for c in result.checks)
        assert result.overall_status == "pass"

    def test_additive_fail_triggers_violation(self, monkeypatch):
        add_rows = [{
            "additive_name": "소르빈산", "food_type": "과자류",
            "max_ppm": 1000, "combined_group": None, "combined_max": None,
            "conversion_factor": None, "colorant_category": None,
            "total_tar_limit": None, "condition_text": None,
            "regulation_ref": None,
        }]
        sb = _mock_supabase_step3(add_rows, [])
        monkeypatch.setattr("services.step3_standards.get_supabase", lambda: sb)
        ingredients = [Ingredient(name="소르빈산", percentage=0.2)]  # 2000ppm > 1000
        result = run_step3(ingredients, "과자류")
        assert result.overall_status == "fail"
        assert len(result.violations) == 1
        assert any(e["trigger_type"] == "standards_violation" for e in result.escalations)

    def test_safety_standards_included(self, monkeypatch):
        safety_rows = [{
            "target_name": "납", "standard_type": "heavy_metal",
            "max_limit": "0.1 mg/kg", "regulation_ref": "식품공전",
            "food_type": "과자류",
        }]
        # No ingredients → _fetch_additive_limits returns early (no DB call)
        # So safety_rows is the FIRST DB call
        sb = _mock_supabase_step3(safety_rows, [])
        monkeypatch.setattr("services.step3_standards.get_supabase", lambda: sb)
        result = run_step3([], "과자류")
        assert any(c.item_name == "납" for c in result.checks)

    def test_all_no_data_returns_review_needed(self, monkeypatch):
        add_rows = [{
            "additive_name": "소르빈산", "food_type": "과자류",
            "max_ppm": 1000, "combined_group": None, "combined_max": None,
            "conversion_factor": None, "colorant_category": None,
            "total_tar_limit": None, "condition_text": None,
            "regulation_ref": None,
        }]
        sb = _mock_supabase_step3(add_rows, [])
        monkeypatch.setattr("services.step3_standards.get_supabase", lambda: sb)
        # No percentage → no_data
        ingredients = [Ingredient(name="소르빈산", percentage=None)]
        result = run_step3(ingredients, "과자류")
        assert result.overall_status == "review_needed"

    def test_liquor_food_type_adds_liquor_checks(self, monkeypatch):
        sb = _mock_supabase_step3([], [])
        monkeypatch.setattr("services.step3_standards.get_supabase", lambda: sb)
        result = run_step3([], "증류주", ProcessConditions())
        # 4 liquor check items (메탄올, 알데히드, 퓨젤유, 에탄올)
        liquor_items = [c for c in result.checks if c.category == "alcohol"]
        assert len(liquor_items) == 4

    def test_liquor_boundary_escalation(self, monkeypatch):
        sb = _mock_supabase_step3([], [])
        monkeypatch.setattr("services.step3_standards.get_supabase", lambda: sb)
        pc = ProcessConditions(alcohol_percentage=0.7)
        result = run_step3([], "증류주", pc)
        assert any(e["trigger_type"] == "alcohol_boundary" for e in result.escalations)

    def test_ins_without_limit_triggers_limit_missing(self, monkeypatch):
        """INS number present but no additive limit row → limit_missing escalation."""
        sb = _mock_supabase_step3([], [])  # no additive rows returned
        monkeypatch.setattr("services.step3_standards.get_supabase", lambda: sb)
        ingredients = [Ingredient(name="E211", ins="211")]
        result = run_step3(ingredients, "과자류")
        assert any(e["trigger_type"] == "limit_missing" for e in result.escalations)
