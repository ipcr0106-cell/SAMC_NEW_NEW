"""F1 match_ingredient() 5-step chain + run_ingredient_match_chain() tests.

Mock strategy:
    - Steps 1~3 use .table().select().eq().limit().execute() → shared eq chain
    - Step 4 uses .table().select().ilike().limit().execute() → separate ilike chain
    - Step 5 uses .rpc().execute() → separate rpc chain
    Sequential .eq() calls use side_effect to return different results per call.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from models.judgment import Ingredient
from services.step1_ingredients_check import (
    match_ingredient,
    run_ingredient_match_chain,
)

# ============================================================
# Fixtures: DB row templates
# ============================================================

DB_PERMITTED = {
    "id": "db-1",
    "name_ko": "비타민C",
    "allowed_status": "permitted",
    "conditions": None,
    "law_source": "식품공전 별표1",
}

DB_RESTRICTED = {
    "id": "db-2",
    "name_ko": "카페인",
    "allowed_status": "restricted",
    "conditions": "150mg 이하",
    "law_source": "식품첨가물공전",
}

DB_PROHIBITED = {
    "id": "db-3",
    "name_ko": "에페드린",
    "allowed_status": "prohibited",
    "conditions": None,
    "law_source": None,
}

DB_FUZZY = {
    "id": "db-4",
    "name_ko": "비타민 C",
    "allowed_status": "permitted",
    "conditions": None,
    "law_source": None,
    "similarity": 0.85,
}

DB_FUZZY_LOW = {
    "id": "db-5",
    "name_ko": "비타민 D",
    "allowed_status": "permitted",
    "conditions": None,
    "law_source": None,
    "similarity": 0.1,
}


# ============================================================
# Mock builder
# ============================================================


def _build_mock(
    eq_results: list[list[dict]] | None = None,
    ilike_result: list[dict] | None = None,
    rpc_result: list[dict] | None = None,
    rpc_error: Exception | None = None,
):
    """Build a Supabase mock with separate chains for eq/ilike/rpc.

    Args:
        eq_results: Sequential results for .eq().limit().execute() calls (steps 1,2,3).
                    Each element is the .data list for that call.
        ilike_result: Result for .ilike().limit().execute() (step 4).
        rpc_result: Result for .rpc().execute() (step 5).
        rpc_error: If set, .rpc().execute() raises this exception.
    """
    mock = MagicMock()

    # eq chain (steps 1, 2, 3)
    eq_exec = MagicMock()
    if eq_results:
        eq_exec.side_effect = [MagicMock(data=r) for r in eq_results]
    else:
        eq_exec.return_value = MagicMock(data=[])
    chain = mock.table.return_value.select.return_value
    chain.eq.return_value.limit.return_value.execute = eq_exec

    # ilike chain (step 4)
    ilike_exec = MagicMock()
    ilike_exec.return_value = MagicMock(data=ilike_result or [])
    chain.ilike.return_value.limit.return_value.execute = ilike_exec

    # rpc chain (step 5)
    if rpc_error:
        mock.rpc.return_value.execute.side_effect = rpc_error
    else:
        mock.rpc.return_value.execute.return_value = MagicMock(
            data=rpc_result or []
        )

    return mock


def _patch(monkeypatch, mock):
    monkeypatch.setattr(
        "services.step1_ingredients_check.get_supabase", lambda: mock
    )


# ============================================================
# Step 1: exact name match
# ============================================================


class TestStep1ExactName:
    def test_exact_hit_permitted(self, monkeypatch):
        sb = _build_mock(eq_results=[[DB_PERMITTED]])
        _patch(monkeypatch, sb)
        r = match_ingredient(Ingredient(name="비타민C"))
        assert r.verdict == "permitted"
        assert r.match_method == "exact_name"
        assert r.confidence == 1.0
        assert r.matched_name_ko == "비타민C"

    def test_exact_hit_restricted_with_conditions(self, monkeypatch):
        sb = _build_mock(eq_results=[[DB_RESTRICTED]])
        _patch(monkeypatch, sb)
        r = match_ingredient(Ingredient(name="카페인"))
        assert r.verdict == "restricted"
        assert r.conditions == "150mg 이하"

    def test_exact_hit_prohibited(self, monkeypatch):
        sb = _build_mock(eq_results=[[DB_PROHIBITED]])
        _patch(monkeypatch, sb)
        r = match_ingredient(Ingredient(name="에페드린"))
        assert r.verdict == "prohibited"

    def test_exact_miss_continues_to_next_step(self, monkeypatch):
        """No exact match, no INS/CAS, short name → skips to step 5 (rpc)."""
        sb = _build_mock(eq_results=[[]])  # step 1 miss
        _patch(monkeypatch, sb)
        r = match_ingredient(Ingredient(name="XX"))  # 2 chars → step 4 skipped
        assert r.verdict == "unidentified"

    def test_law_source_preserved(self, monkeypatch):
        sb = _build_mock(eq_results=[[DB_PERMITTED]])
        _patch(monkeypatch, sb)
        r = match_ingredient(Ingredient(name="비타민C"))
        assert r.law_source == "식품공전 별표1"

    def test_matched_db_id_preserved(self, monkeypatch):
        sb = _build_mock(eq_results=[[DB_PERMITTED]])
        _patch(monkeypatch, sb)
        r = match_ingredient(Ingredient(name="비타민C"))
        assert r.matched_db_id == "db-1"


# ============================================================
# Step 2: INS number match
# ============================================================


class TestStep2INS:
    def test_ins_hit_after_exact_miss(self, monkeypatch):
        sb = _build_mock(eq_results=[[], [DB_PERMITTED]])  # step1 miss, step2 hit
        _patch(monkeypatch, sb)
        r = match_ingredient(Ingredient(name="E300", ins="300"))
        assert r.verdict == "permitted"
        assert r.match_method == "ins_number"
        assert r.confidence == 1.0

    def test_ins_not_tried_when_absent(self, monkeypatch):
        """No ins field → step 2 skipped, only 1 eq call (step 1)."""
        sb = _build_mock(eq_results=[[]])
        _patch(monkeypatch, sb)
        r = match_ingredient(Ingredient(name="XX"))
        # eq should be called once (step 1 only)
        eq_exec = sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute
        assert eq_exec.call_count == 1


# ============================================================
# Step 3: CAS number match
# ============================================================


class TestStep3CAS:
    def test_cas_hit_after_exact_and_ins_miss(self, monkeypatch):
        sb = _build_mock(eq_results=[[], [], [DB_PERMITTED]])  # step1,2 miss, step3 hit
        _patch(monkeypatch, sb)
        r = match_ingredient(Ingredient(name="XY", ins="999", cas="50-81-7"))
        assert r.verdict == "permitted"
        assert r.match_method == "cas_number"

    def test_cas_not_tried_when_absent(self, monkeypatch):
        sb = _build_mock(eq_results=[[], []])  # step1 miss, step2 miss (ins given)
        _patch(monkeypatch, sb)
        r = match_ingredient(Ingredient(name="XX", ins="999"))
        # 2 eq calls: step1 + step2. No step3 (no cas).
        eq_exec = sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute
        assert eq_exec.call_count == 2


# ============================================================
# Step 4: scientific name (ilike)
# ============================================================


class TestStep4ScientificName:
    def test_scientific_hit(self, monkeypatch):
        sb = _build_mock(eq_results=[[]], ilike_result=[DB_PERMITTED])
        _patch(monkeypatch, sb)
        # name >= 4 chars triggers step 4
        r = match_ingredient(Ingredient(name="Oryza sativa"))
        assert r.verdict == "permitted"
        assert r.match_method == "scientific_name"
        assert r.confidence == 1.0

    def test_skipped_when_name_short(self, monkeypatch):
        """Names < 4 chars skip step 4 to avoid false positives."""
        sb = _build_mock(eq_results=[[]], ilike_result=[DB_PERMITTED])
        _patch(monkeypatch, sb)
        r = match_ingredient(Ingredient(name="ABC"))  # 3 chars
        # ilike should NOT be called
        ilike_exec = sb.table.return_value.select.return_value.ilike.return_value.limit.return_value.execute
        assert ilike_exec.call_count == 0
        assert r.verdict == "unidentified"

    def test_scientific_miss_continues_to_fuzzy(self, monkeypatch):
        sb = _build_mock(eq_results=[[]], ilike_result=[], rpc_result=[DB_FUZZY])
        _patch(monkeypatch, sb)
        r = match_ingredient(Ingredient(name="비타민씨정제"))  # >= 4 chars
        assert r.verdict == "permitted"
        assert r.match_method == "fuzzy"


# ============================================================
# Step 5: fuzzy (trgm)
# ============================================================


class TestStep5Fuzzy:
    def test_fuzzy_hit_above_threshold(self, monkeypatch):
        sb = _build_mock(eq_results=[[]], rpc_result=[DB_FUZZY])
        _patch(monkeypatch, sb)
        r = match_ingredient(Ingredient(name="XX"))
        assert r.verdict == "permitted"
        assert r.match_method == "fuzzy"
        assert r.confidence == 0.7

    def test_fuzzy_below_threshold_returns_unidentified(self, monkeypatch):
        sb = _build_mock(eq_results=[[]], rpc_result=[DB_FUZZY_LOW])
        _patch(monkeypatch, sb)
        r = match_ingredient(Ingredient(name="XX"))
        assert r.verdict == "unidentified"
        assert r.confidence == 0.0

    def test_fuzzy_no_results(self, monkeypatch):
        sb = _build_mock(eq_results=[[]], rpc_result=[])
        _patch(monkeypatch, sb)
        r = match_ingredient(Ingredient(name="XX"))
        assert r.verdict == "unidentified"

    def test_fuzzy_rpc_failure_graceful(self, monkeypatch):
        sb = _build_mock(eq_results=[[]], rpc_error=Exception("timeout"))
        _patch(monkeypatch, sb)
        r = match_ingredient(Ingredient(name="XX"))
        assert r.verdict == "unidentified"


# ============================================================
# Verdict map fallback
# ============================================================


class TestVerdictMapInChain:
    def test_unknown_allowed_status_maps_to_unidentified(self, monkeypatch):
        row = {**DB_PERMITTED, "allowed_status": "unknown_value"}
        sb = _build_mock(eq_results=[[row]])
        _patch(monkeypatch, sb)
        r = match_ingredient(Ingredient(name="비타민C"))
        assert r.verdict == "unidentified"


# ============================================================
# run_ingredient_match_chain — aggregation + escalation
# ============================================================


class TestRunIngredientMatchChain:
    def test_empty_list(self, monkeypatch):
        sb = _build_mock()
        _patch(monkeypatch, sb)
        agg = run_ingredient_match_chain([])
        assert agg.total == 0
        assert agg.permitted == 0
        assert agg.escalations == []

    def test_all_permitted(self, monkeypatch):
        sb = _build_mock(eq_results=[[DB_PERMITTED]])
        _patch(monkeypatch, sb)
        agg = run_ingredient_match_chain([Ingredient(name="비타민C")])
        assert agg.total == 1
        assert agg.permitted == 1
        assert agg.escalations == []

    def test_prohibited_generates_escalation(self, monkeypatch):
        sb = _build_mock(eq_results=[[DB_PROHIBITED]])
        _patch(monkeypatch, sb)
        agg = run_ingredient_match_chain([Ingredient(name="에페드린")])
        assert agg.prohibited == 1
        assert len(agg.escalations) == 1
        assert agg.escalations[0]["trigger_type"] == "prohibited_detected"
        assert "에페드린" in agg.escalations[0]["reason"]

    def test_unidentified_generates_escalation(self, monkeypatch):
        sb = _build_mock(eq_results=[[]])
        _patch(monkeypatch, sb)
        agg = run_ingredient_match_chain([Ingredient(name="XX")])
        assert agg.unidentified == 1
        assert len(agg.escalations) == 1
        assert agg.escalations[0]["trigger_type"] == "low_confidence"

    def test_mixed_results_aggregation(self, monkeypatch):
        """permitted + prohibited + unidentified → correct counts + 2 escalations."""
        # Each call to match_ingredient creates a fresh supabase via get_supabase()
        # So we need the mock factory to return fresh mocks per call
        call_count = 0
        responses = [
            _build_mock(eq_results=[[DB_PERMITTED]]),     # ing 1: permitted
            _build_mock(eq_results=[[DB_PROHIBITED]]),    # ing 2: prohibited
            _build_mock(eq_results=[[]]),                  # ing 3: unidentified
        ]

        def mock_factory():
            nonlocal call_count
            m = responses[call_count]
            call_count += 1
            return m

        monkeypatch.setattr(
            "services.step1_ingredients_check.get_supabase", mock_factory
        )
        agg = run_ingredient_match_chain([
            Ingredient(name="비타민C"),
            Ingredient(name="에페드린"),
            Ingredient(name="미지성분"),
        ])
        assert agg.total == 3
        assert agg.permitted == 1
        assert agg.prohibited == 1
        assert agg.unidentified == 1
        assert len(agg.escalations) == 2

    def test_synthetic_flavor_skips_matching(self, monkeypatch):
        sb = _build_mock()
        _patch(monkeypatch, sb)
        agg = run_ingredient_match_chain([Ingredient(name="합성향료(바닐라)")])
        assert agg.unidentified == 1
        assert len(agg.escalations) == 1
        assert agg.escalations[0]["trigger_type"] == "synthetic_flavor"
        # DB should not be called for synthetic flavors
        assert sb.table.call_count == 0
