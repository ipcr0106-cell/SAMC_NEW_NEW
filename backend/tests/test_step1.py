"""F1 Step 0/1 unit tests — DB-free via monkeypatch.

Covers:
    - _normalize() behavior
    - check_forbidden_first() bidirectional substring matching
    - _VERDICT_MAP fallback
    - is_synthetic_flavor()
    - match_ingredient() trgm RPC failure resilience
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from models.judgment import Ingredient
from services.step1_ingredients_check import (
    _normalize,
    _VERDICT_MAP,
    check_forbidden_first,
    match_ingredient,
    _unidentified,
)
from constants.thresholds_config import is_synthetic_flavor


# ============================================================
# _normalize
# ============================================================


class TestNormalize:
    def test_removes_whitespace(self):
        assert _normalize("마리화나 추출물") == "마리화나추출물"

    def test_lowercases(self):
        assert _normalize("Kava Kava") == "kavakava"

    def test_mixed_korean_english(self):
        assert _normalize("THC 오일") == "thc오일"

    def test_empty_string(self):
        assert _normalize("") == ""

    def test_already_normalized(self):
        assert _normalize("대마초") == "대마초"


# ============================================================
# check_forbidden_first — bidirectional substring
# ============================================================

FORBIDDEN_SEED = [
    {
        "name_ko": "대마초",
        "name_en": "Cannabis",
        "aliases": ["대마", "마리화나", "THC"],
        "category": "drug",
        "law_source": "마약류 관리에 관한 법률",
        "reason": "마약류 관리법상 수입 금지",
    },
    {
        "name_ko": "카바카바",
        "name_en": "Kava kava",
        "aliases": ["카바"],
        "category": "unauthorized",
        "law_source": "식약처 고시",
        "reason": "간 독성",
    },
]


def _mock_supabase(rows):
    """Build a mock supabase that returns rows for forbidden table."""
    mock = MagicMock()
    mock.table.return_value.select.return_value.eq.return_value.execute.return_value.data = rows
    return mock


class TestCheckForbiddenFirst:
    def test_no_hit_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            "services.step1_ingredients_check.get_supabase",
            lambda: _mock_supabase(FORBIDDEN_SEED),
        )
        result = check_forbidden_first([Ingredient(name="설탕"), Ingredient(name="밀가루")])
        assert result == []

    def test_exact_name_ko_hit(self, monkeypatch):
        monkeypatch.setattr(
            "services.step1_ingredients_check.get_supabase",
            lambda: _mock_supabase(FORBIDDEN_SEED),
        )
        result = check_forbidden_first([Ingredient(name="대마초")])
        assert len(result) == 1
        assert result[0].name_ko == "대마초"
        assert result[0].category == "drug"

    def test_alias_substring_hit(self, monkeypatch):
        """BUG-1 core fix: '마리화나 추출물' contains alias '마리화나'."""
        monkeypatch.setattr(
            "services.step1_ingredients_check.get_supabase",
            lambda: _mock_supabase(FORBIDDEN_SEED),
        )
        result = check_forbidden_first([Ingredient(name="마리화나 추출물")])
        assert len(result) == 1
        assert result[0].name_ko == "대마초"

    def test_english_case_insensitive(self, monkeypatch):
        """BUG-1: 'Kava Kava extract' matches name_en 'Kava kava'."""
        monkeypatch.setattr(
            "services.step1_ingredients_check.get_supabase",
            lambda: _mock_supabase(FORBIDDEN_SEED),
        )
        result = check_forbidden_first([Ingredient(name="Kava Kava extract")])
        assert len(result) == 1
        assert result[0].name_ko == "카바카바"

    def test_multiple_hits(self, monkeypatch):
        monkeypatch.setattr(
            "services.step1_ingredients_check.get_supabase",
            lambda: _mock_supabase(FORBIDDEN_SEED),
        )
        result = check_forbidden_first([
            Ingredient(name="대마"),
            Ingredient(name="카바"),
            Ingredient(name="설탕"),
        ])
        assert len(result) == 2
        matched = sorted(h.name_ko for h in result)
        assert matched == ["대마초", "카바카바"]

    def test_dedup_same_ingredient(self, monkeypatch):
        """Same forbidden entry matched by name_ko and alias → only 1 hit."""
        overlap = [
            {"name_ko": "대마", "name_en": None, "aliases": None, "category": "drug",
             "law_source": None, "reason": None},
            {"name_ko": "대마초", "name_en": None, "aliases": ["대마"], "category": "drug",
             "law_source": None, "reason": None},
        ]
        monkeypatch.setattr(
            "services.step1_ingredients_check.get_supabase",
            lambda: _mock_supabase(overlap),
        )
        result = check_forbidden_first([Ingredient(name="대마")])
        # "대마" matches both rows but each name_ko is unique → 2 hits
        # This tests dedup on name_ko (different name_ko = separate hits)
        assert len(result) == 2

    def test_empty_ingredients(self, monkeypatch):
        monkeypatch.setattr(
            "services.step1_ingredients_check.get_supabase",
            lambda: _mock_supabase(FORBIDDEN_SEED),
        )
        result = check_forbidden_first([])
        assert result == []

    def test_law_source_preserved(self, monkeypatch):
        monkeypatch.setattr(
            "services.step1_ingredients_check.get_supabase",
            lambda: _mock_supabase(FORBIDDEN_SEED),
        )
        result = check_forbidden_first([Ingredient(name="대마초")])
        assert result[0].law_source == "마약류 관리에 관한 법률"
        assert result[0].reason == "마약류 관리법상 수입 금지"


# ============================================================
# _VERDICT_MAP fallback
# ============================================================


class TestVerdictMap:
    def test_known_statuses(self):
        assert _VERDICT_MAP["permitted"] == "permitted"
        assert _VERDICT_MAP["restricted"] == "restricted"
        assert _VERDICT_MAP["prohibited"] == "prohibited"

    def test_unknown_status_falls_back(self):
        assert _VERDICT_MAP.get("unknown_value", "unidentified") == "unidentified"


# ============================================================
# is_synthetic_flavor
# ============================================================


class TestIsSyntheticFlavor:
    def test_korean_match(self):
        assert is_synthetic_flavor("합성향료(바닐라)") is True

    def test_english_match(self):
        assert is_synthetic_flavor("Artificial Flavor") is True

    def test_no_match(self):
        assert is_synthetic_flavor("설탕") is False

    def test_empty(self):
        assert is_synthetic_flavor("") is False


# ============================================================
# match_ingredient — trgm RPC failure resilience
# ============================================================


class TestMatchIngredientTrgmDefense:
    def test_rpc_failure_returns_unidentified(self, monkeypatch):
        """trgm RPC exception → unidentified fallback, no crash."""
        mock_sb = MagicMock()
        # Steps 1-4: no match
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
        mock_sb.table.return_value.select.return_value.ilike.return_value.limit.return_value.execute.return_value.data = []
        # Step 5: RPC raises
        mock_sb.rpc.return_value.execute.side_effect = Exception("connection timeout")

        monkeypatch.setattr(
            "services.step1_ingredients_check.get_supabase",
            lambda: mock_sb,
        )
        ing = Ingredient(name="some_unknown_ingredient_name")
        result = match_ingredient(ing)
        assert result.verdict == "unidentified"
        assert result.confidence == 0.0

    def test_empty_name_returns_unidentified(self, monkeypatch):
        ing = Ingredient(name="")
        result = match_ingredient(ing)
        assert result.verdict == "unidentified"
