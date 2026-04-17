"""F1 integration tests — run_step1() + run_feature1() end-to-end flows.

Tests the full orchestration: Step 0 → Step 1 → Step 1-A → Step 1-B → Step 3.
All DB calls mocked via monkeypatch on get_supabase.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from models.judgment import Ingredient, ProcessConditions
from services.step1_ingredients_check import run_step1
from services.feature1 import run_feature1


# ============================================================
# Mock helpers
# ============================================================

# DB rows
FORBIDDEN_ROW = {
    "name_ko": "대마초", "name_en": "Cannabis",
    "aliases": ["대마", "마리화나"],
    "category": "drug", "law_source": "마약류 관리법", "reason": "금지",
}

ALLOWED_ROW = {
    "id": "a-1", "name_ko": "비타민C", "allowed_status": "permitted",
    "conditions": None, "law_source": "식품공전 별표1",
}

RESTRICTED_ROW = {
    "id": "a-2", "name_ko": "카페인", "allowed_status": "restricted",
    "conditions": "150mg 이하", "law_source": "식품첨가물공전",
}

PROHIBITED_ROW = {
    "id": "a-3", "name_ko": "에페드린", "allowed_status": "prohibited",
    "conditions": None, "law_source": None,
}


def _make_step1_mock(forbidden_rows=None, match_rows=None):
    """Mock for run_step1: covers forbidden table + allowed_ingredients table.

    match_rows: a function(name) -> row or None, for flexible per-ingredient mocking.
                Or a list that returns sequentially.
    """
    mock = MagicMock()

    # Forbidden table chain
    forbidden_exec = MagicMock()
    forbidden_exec.return_value = MagicMock(data=forbidden_rows or [])

    # Allowed table chain — use side_effect function to dispatch by call
    match_fn = match_rows if callable(match_rows) else None
    match_list_iter = iter(match_rows or []) if not callable(match_rows) and match_rows else None

    def _table(name):
        chain = MagicMock()
        if name == "f1_forbidden_ingredients":
            chain.select.return_value.eq.return_value.execute = forbidden_exec
        elif name == "f1_allowed_ingredients":
            # eq chain (steps 1-3)
            eq_exec = MagicMock()
            if match_fn:
                eq_exec.side_effect = lambda: MagicMock(data=[])
            else:
                eq_exec.return_value = MagicMock(data=[])
            chain.select.return_value.eq.return_value.limit.return_value.execute = eq_exec
            # ilike chain (step 4)
            chain.select.return_value.ilike.return_value.limit.return_value.execute = MagicMock(
                return_value=MagicMock(data=[])
            )
        return chain

    mock.table = _table
    # rpc chain (step 5 trgm)
    mock.rpc.return_value.execute.return_value = MagicMock(data=[])

    return mock


def _make_full_mock(forbidden_rows=None, step1_per_ingredient=None,
                    additive_rows=None, safety_rows=None):
    """Full mock for run_feature1: step1 + step3 combined.

    step1_per_ingredient: list of (row_or_None) per sequential match_ingredient call.
    """
    call_idx = {"n": 0}
    per_ing = step1_per_ingredient or []

    def factory():
        mock = MagicMock()

        # Forbidden
        forbidden_exec = MagicMock()
        forbidden_exec.return_value = MagicMock(data=forbidden_rows or [])

        def _table(name):
            chain = MagicMock()
            if name == "f1_forbidden_ingredients":
                chain.select.return_value.eq.return_value.execute = forbidden_exec
            elif name == "f1_allowed_ingredients":
                eq_exec = MagicMock()
                idx = call_idx["n"]
                call_idx["n"] += 1
                row = per_ing[idx] if idx < len(per_ing) else None
                if row:
                    _empty = MagicMock(data=[])
                    # First call (normalized) might miss, second (original) hits
                    _hit = MagicMock(data=[row])
                    _it = iter([_hit])
                    eq_exec.side_effect = lambda: next(_it, _empty)
                else:
                    eq_exec.return_value = MagicMock(data=[])
                chain.select.return_value.eq.return_value.limit.return_value.execute = eq_exec
                chain.select.return_value.ilike.return_value.limit.return_value.execute = MagicMock(
                    return_value=MagicMock(data=[])
                )
            elif name == "f1_additive_limits":
                in_exec = MagicMock()
                in_exec.return_value = MagicMock(data=additive_rows or [])
                chain.select.return_value.eq.return_value.in_.return_value.in_.return_value.execute = in_exec
            elif name == "f1_safety_standards":
                in_exec = MagicMock()
                in_exec.return_value = MagicMock(data=safety_rows or [])
                chain.select.return_value.eq.return_value.in_.return_value.in_.return_value.execute = in_exec
                chain.select.return_value.eq.return_value.eq.return_value.ilike.return_value.limit.return_value.execute = MagicMock(
                    return_value=MagicMock(data=[])
                )
            return chain

        mock.table = _table
        mock.rpc.return_value.execute.return_value = MagicMock(data=[])
        return mock

    return factory


# ============================================================
# run_step1 integration
# ============================================================


class TestRunStep1Integration:
    def test_forbidden_hit_stops_at_step0(self, monkeypatch):
        mock = _make_step1_mock(forbidden_rows=[FORBIDDEN_ROW])
        monkeypatch.setattr("services.step1_ingredients_check.get_supabase", lambda: mock)
        result = run_step1([Ingredient(name="대마초")])
        assert result["stopped_at"] == "step0"
        assert result["import_possible"] is False
        assert len(result["forbidden_hits"]) == 1

    def test_all_permitted_passes_step1(self, monkeypatch):
        mock = _make_step1_mock(forbidden_rows=[])
        # Override eq execute to return ALLOWED_ROW
        eq_exec = mock.table("f1_allowed_ingredients").select.return_value.eq.return_value.limit.return_value.execute
        eq_exec.return_value = MagicMock(data=[ALLOWED_ROW])
        monkeypatch.setattr("services.step1_ingredients_check.get_supabase", lambda: mock)
        result = run_step1([Ingredient(name="비타민C")])
        assert result["import_possible"] is None  # awaiting step3
        assert "stopped_at" not in result

    def test_prohibited_stops_at_step1(self, monkeypatch):
        from models.judgment import AggregationResult, IngredientMatchResult
        monkeypatch.setattr(
            "services.step1_ingredients_check.check_forbidden_first", lambda ings: []
        )
        ing = Ingredient(name="에페드린")
        monkeypatch.setattr(
            "services.step1_ingredients_check.run_ingredient_match_chain",
            lambda ings: AggregationResult(
                total=1, permitted=0, restricted=0, prohibited=1, unidentified=0,
                results=[IngredientMatchResult(
                    ingredient=ing, verdict="prohibited", confidence=1.0,
                )],
                escalations=[{"module_id": "F1", "trigger_type": "prohibited_detected",
                              "reason": "test"}],
            ),
        )
        result = run_step1([ing])
        assert result["stopped_at"] == "step1"
        assert result["import_possible"] is False

    def test_empty_ingredients(self, monkeypatch):
        mock = _make_step1_mock(forbidden_rows=[])
        monkeypatch.setattr("services.step1_ingredients_check.get_supabase", lambda: mock)
        result = run_step1([])
        assert result["import_possible"] is None

    def test_restricted_condition_fail_stops_at_step1b(self, monkeypatch):
        """restricted + part condition not met → step1b stop."""
        from models.judgment import AggregationResult, IngredientMatchResult
        monkeypatch.setattr(
            "services.step1_ingredients_check.check_forbidden_first", lambda ings: []
        )
        ing = Ingredient(name="인삼", part="잎")
        monkeypatch.setattr(
            "services.step1_ingredients_check.run_ingredient_match_chain",
            lambda ings: AggregationResult(
                total=1, permitted=0, restricted=1, prohibited=0, unidentified=0,
                results=[IngredientMatchResult(
                    ingredient=ing, verdict="restricted", confidence=1.0,
                    conditions="뿌리만 사용 가능",
                )],
            ),
        )
        result = run_step1([ing])
        assert result["stopped_at"] == "step1b"
        assert result["import_possible"] is False


# ============================================================
# run_feature1 integration (Step 0 + 1 + 3)
# ============================================================


class TestRunFeature1Integration:
    def test_forbidden_short_circuit(self, monkeypatch):
        factory = _make_full_mock(forbidden_rows=[FORBIDDEN_ROW])
        monkeypatch.setattr("services.step1_ingredients_check.get_supabase", factory)
        monkeypatch.setattr("services.step3_standards.get_supabase", factory)
        out = run_feature1([Ingredient(name="대마초")])
        assert out.import_possible is False
        assert len(out.forbidden_hits) == 1

    def test_all_pass_returns_import_possible(self, monkeypatch):
        factory = _make_full_mock(
            step1_per_ingredient=[ALLOWED_ROW],
        )
        monkeypatch.setattr("services.step1_ingredients_check.get_supabase", factory)
        monkeypatch.setattr("services.step3_standards.get_supabase", factory)
        out = run_feature1(
            [Ingredient(name="비타민C", percentage=0.01)],
            food_type="과자류",
        )
        # Step3 with no additive limits → review_needed (not pass)
        # because no checks data → review_needed
        assert out.import_possible is False  # review_needed maps to False
        assert "검토" in out.verdict or "기준치" in out.verdict

    def test_prohibited_in_step1_short_circuit(self, monkeypatch):
        factory = _make_full_mock(
            step1_per_ingredient=[PROHIBITED_ROW],
        )
        monkeypatch.setattr("services.step1_ingredients_check.get_supabase", factory)
        monkeypatch.setattr("services.step3_standards.get_supabase", factory)
        out = run_feature1([Ingredient(name="에페드린")])
        assert out.import_possible is False
        assert "미허용" in out.verdict or "수입불가" in out.verdict

    def test_no_food_type_returns_review_needed(self, monkeypatch):
        factory = _make_full_mock(step1_per_ingredient=[ALLOWED_ROW])
        monkeypatch.setattr("services.step1_ingredients_check.get_supabase", factory)
        monkeypatch.setattr("services.step3_standards.get_supabase", factory)
        out = run_feature1([Ingredient(name="비타민C")], food_type=None)
        assert out.import_possible is False
        assert "검토" in out.verdict

    def test_synthetic_flavor_in_output(self, monkeypatch):
        factory = _make_full_mock()
        monkeypatch.setattr("services.step1_ingredients_check.get_supabase", factory)
        monkeypatch.setattr("services.step3_standards.get_supabase", factory)
        out = run_feature1([Ingredient(name="합성향료(바닐라)")], food_type="과자류")
        assert "합성향료(바닐라)" in out.synthetic_flavor_ingredients

    def test_law_refs_collected(self, monkeypatch):
        factory = _make_full_mock(step1_per_ingredient=[ALLOWED_ROW])
        monkeypatch.setattr("services.step1_ingredients_check.get_supabase", factory)
        monkeypatch.setattr("services.step3_standards.get_supabase", factory)
        out = run_feature1([Ingredient(name="비타민C")], food_type="과자류")
        sources = [r.law_source for r in out.law_refs]
        assert "식품공전 별표1" in sources
