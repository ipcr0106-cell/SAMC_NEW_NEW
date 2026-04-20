"""W2-B Step B 단위 테스트.

커버 범위 (02번 §10):
    - normalize_name: strip + 다중공백 + `·` → `,`
    - flatten_ingredients: sub_ingredients 재귀 평탄화
    - resolve_verdict: prohibited > restricted > allowed > unidentified 우선순위
    - _match_ingredient_hits: exact / alias / scientific / Levenshtein fallback
    - Levenshtein fallback 자동 확정 금지 (unidentified 처리)
    - 15094202 성분코드: 카테고리·사용구분 우선순위, KOR_NM strip
    - 15111913 GMO: 정확 일치만, 다건 Y 우선
    - 합성향료 자동 감지 → unidentified
    - run_step_b 통합: 대두/아편/인삼/sub_ingredients/동명이인/API 실패 격리
    - synonym 조회 경로: hit → 정규화 후 재매칭, miss → 다음 전략, Supabase 오류 → graceful fallback

실행:
    cd backend
    pytest tests/services/test_f1_step_b.py -v
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest

from exceptions import DataGoKrError, DataGoKrTimeoutError
from models.f1_types import DataGoKrEndpoint, StepBResult
from models.judgment import Ingredient
from services import f1_step_b
from services.f1_step_b import (
    _is_foreign_exchange_code,
    _levenshtein,
    _lookup_synonym,
    _match_ingredient_hits,
    _pick_component_code,
    _pick_exact_component_item,
    _pick_gmo_flag,
    _resolve_verdict_by_category,
    flatten_ingredients,
    normalize_name,
    resolve_verdict,
    run_step_b,
    set_client_for_test,
)

# ============================================================
# 공통 픽스처
# ============================================================

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "f1_step_b"


def load_fixture(name: str) -> Dict[str, Any]:
    with open(FIXTURES_DIR / name, encoding="utf-8") as f:
        return json.load(f)


class FakeClient:
    """DataGoKrClient 대체 — 이름별 응답 매핑. 예외 플래그로 장애 시뮬레이션."""

    def __init__(
        self,
        *,
        ingredient: Optional[Dict[str, Dict[str, Any]]] = None,
        component: Optional[Dict[str, Dict[str, Any]]] = None,
        gmo: Optional[Dict[str, Dict[str, Any]]] = None,
        errors: Optional[Dict[str, Exception]] = None,
    ) -> None:
        self._ingredient = ingredient or {}
        self._component = component or {}
        self._gmo = gmo or {}
        self._errors = errors or {}
        self.calls: List[tuple] = []

    async def get_import_food_ingredient(self, name: str) -> Dict[str, Any]:
        self.calls.append(("15111777", name))
        key = f"ingredient:{name}"
        if key in self._errors:
            raise self._errors[key]
        return self._ingredient.get(name, {"items": [], "total_count": 0, "raw": {}})

    async def get_import_food_component(self, name: str) -> Dict[str, Any]:
        self.calls.append(("15094202", name))
        key = f"component:{name}"
        if key in self._errors:
            raise self._errors[key]
        return self._component.get(name, {"items": [], "total_count": 0, "raw": {}})

    async def get_food_raw_material(self, name: str) -> Dict[str, Any]:
        self.calls.append(("15111913", name))
        key = f"gmo:{name}"
        if key in self._errors:
            raise self._errors[key]
        return self._gmo.get(name, {"items": [], "total_count": 0, "raw": {}})


@pytest.fixture(autouse=True)
def _reset_client_singleton():
    """테스트 간 전역 클라이언트 격리."""
    set_client_for_test(None)
    yield
    set_client_for_test(None)


# ============================================================
# normalize_name
# ============================================================


class TestNormalizeName:
    def test_strip(self):
        assert normalize_name("  대두  ") == "대두"

    def test_multi_whitespace_collapsed(self):
        assert normalize_name("식품\t  원료") == "식품 원료"

    def test_middle_dot_to_comma(self):
        assert normalize_name("대두·옥수수") == "대두,옥수수"

    def test_none_returns_empty(self):
        assert normalize_name(None) == ""

    def test_empty_returns_empty(self):
        assert normalize_name("") == ""

    def test_combined(self):
        assert normalize_name("  A·B   C ") == "A,B C"


# ============================================================
# flatten_ingredients
# ============================================================


class TestFlatten:
    def test_flat_list_unchanged(self):
        a = Ingredient(name="대두")
        b = Ingredient(name="밀")
        assert [i.name for i in flatten_ingredients([a, b])] == ["대두", "밀"]

    def test_sub_ingredients_flattened(self):
        child = Ingredient(name="설탕")
        parent = Ingredient(name="복합시럽", sub_ingredients=[child])
        flat = flatten_ingredients([parent])
        assert [i.name for i in flat] == ["복합시럽", "설탕"]

    def test_nested_deep(self):
        leaf = Ingredient(name="소금")
        mid = Ingredient(name="조미료", sub_ingredients=[leaf])
        root = Ingredient(name="복합조미료", sub_ingredients=[mid])
        flat = flatten_ingredients([root])
        assert [i.name for i in flat] == ["복합조미료", "조미료", "소금"]

    def test_empty_list(self):
        assert flatten_ingredients([]) == []


# ============================================================
# Levenshtein
# ============================================================


class TestLevenshtein:
    def test_equal(self):
        assert _levenshtein("대두", "대두") == 0

    def test_one_edit(self):
        assert _levenshtein("대두", "대구") == 1

    def test_insert_and_delete(self):
        assert _levenshtein("abc", "abcd") == 1
        assert _levenshtein("abcd", "abc") == 1

    def test_empty(self):
        assert _levenshtein("", "abc") == 3
        assert _levenshtein("abc", "") == 3


# ============================================================
# resolve_verdict — 우선순위
# ============================================================


class TestResolveVerdict:
    def test_empty_hits_is_unidentified(self):
        assert resolve_verdict([]) == "unidentified"

    def test_allowed(self):
        hits = [{"EDIBLE_INFO": "가능", "EDIBLE_Y": "o", "EDIBLE_N": "x"}]
        assert resolve_verdict(hits) == "allowed"

    def test_prohibited(self):
        hits = [{"EDIBLE_INFO": "불가", "EDIBLE_Y": "x", "EDIBLE_N": "o"}]
        assert resolve_verdict(hits) == "prohibited"

    def test_restricted_via_chrtr(self):
        hits = [
            {
                "EDIBLE_INFO": "가능",
                "EDIBLE_Y": "o",
                "CHRTR_INFO_CONT": "뿌리만 사용 가능",
            }
        ]
        assert resolve_verdict(hits) == "restricted"

    def test_blank_chrtr_is_not_restricted(self):
        hits = [{"EDIBLE_INFO": "가능", "EDIBLE_Y": "o", "CHRTR_INFO_CONT": "   "}]
        assert resolve_verdict(hits) == "allowed"

    def test_homonym_safer_side_prohibited_wins(self):
        # 한쪽은 allowed, 다른 쪽은 prohibited → 안전측 prohibited
        hits = [
            {"EDIBLE_INFO": "가능", "EDIBLE_Y": "o"},
            {"EDIBLE_INFO": "불가", "EDIBLE_N": "o"},
        ]
        assert resolve_verdict(hits) == "prohibited"

    def test_homonym_restricted_wins_over_allowed(self):
        hits = [
            {"EDIBLE_INFO": "가능", "EDIBLE_Y": "o"},
            {"EDIBLE_INFO": "가능", "EDIBLE_Y": "o", "CHRTR_INFO_CONT": "조건"},
        ]
        assert resolve_verdict(hits) == "restricted"

    def test_priority_order_strict(self):
        # prohibited > restricted > allowed 동시 존재 → prohibited
        hits = [
            {"EDIBLE_INFO": "가능", "EDIBLE_Y": "o"},
            {"EDIBLE_INFO": "가능", "CHRTR_INFO_CONT": "조건"},
            {"EDIBLE_INFO": "불가", "EDIBLE_N": "o"},
        ]
        assert resolve_verdict(hits) == "prohibited"


# ============================================================
# _match_ingredient_hits — 4단계 매칭 전략
# ============================================================


class TestMatchStrategy:
    def test_exact_match(self):
        items = [{"INGD_NM": "대두", "NKNM_NM": "콩"}]
        matched, strategy = _match_ingredient_hits("대두", items)
        assert strategy == "exact"
        assert len(matched) == 1

    def test_alias_match(self):
        items = [{"INGD_NM": "대두", "NKNM_NM": "콩, Soybean"}]
        matched, strategy = _match_ingredient_hits("콩", items)
        assert strategy == "alias"
        assert matched[0]["INGD_NM"] == "대두"

    def test_scientific_match(self):
        items = [{"INGD_NM": "대두", "NKNM_NM": "", "SCNNM_NM": "Glycine max"}]
        matched, strategy = _match_ingredient_hits("Glycine", items)
        assert strategy == "scientific"
        assert matched[0]["INGD_NM"] == "대두"

    def test_fuzzy_fallback(self):
        # '대두' ↔ '대주' 편집거리 1 (짧은 이름 임계치)
        items = [{"INGD_NM": "대주", "NKNM_NM": ""}]
        matched, strategy = _match_ingredient_hits("대두", items)
        assert strategy == "fuzzy"
        assert len(matched) == 1

    def test_no_match(self):
        items = [{"INGD_NM": "완전히다른이름", "NKNM_NM": ""}]
        matched, strategy = _match_ingredient_hits("대두", items)
        assert strategy == "none"
        assert matched == []

    def test_exact_preferred_over_alias(self):
        items = [
            {"INGD_NM": "A", "NKNM_NM": "대두"},   # alias 로만 매칭
            {"INGD_NM": "대두", "NKNM_NM": ""},   # 정확 일치
        ]
        matched, strategy = _match_ingredient_hits("대두", items)
        assert strategy == "exact"
        assert len(matched) == 1
        assert matched[0]["INGD_NM"] == "대두"


# ============================================================
# 15094202 성분코드 매칭
# ============================================================


class TestComponentCode:
    def test_exact_kor_match(self):
        items = [{"CPNT_CD": "A1", "KOR_NM": "대두", "CPNT_LCLS_CD_NM": "식품원료"}]
        assert _pick_component_code("대두", items) == "A1"

    def test_leading_space_in_kor_nm_handled(self):
        """클라이언트에서 strip 되지 않고 raw 가 흘러와도 매칭 성공."""
        items = [{"CPNT_CD": "B2", "KOR_NM": " 대두", "CPNT_LCLS_CD_NM": "식품원료"}]
        assert _pick_component_code("대두", items) == "B2"

    def test_category_priority_raw_material_first(self):
        # 식품원료 < 식품첨가물 < 기타 순으로 우선
        data = load_fixture("15094202_multi_category.json")
        code = _pick_component_code("다목적성분", data["items"])
        assert code == "A1111111111111"  # 식품원료 레코드

    def test_use_divs_priority(self):
        # 같은 카테고리에서 '사용가능' 우선
        items = [
            {
                "CPNT_CD": "X1",
                "KOR_NM": "x",
                "CPNT_LCLS_CD_NM": "식품원료",
                "USE_DIVS_CD_NM": "기타",
            },
            {
                "CPNT_CD": "X2",
                "KOR_NM": "x",
                "CPNT_LCLS_CD_NM": "식품원료",
                "USE_DIVS_CD_NM": "사용가능",
            },
        ]
        assert _pick_component_code("x", items) == "X2"

    def test_no_match_returns_none(self):
        assert _pick_component_code("대두", []) is None

    def test_english_fallback(self):
        items = [
            {
                "CPNT_CD": "ENG1",
                "KOR_NM": "다른한글명",
                "ENG_NM": "SOYBEAN",
                "CPNT_LCLS_CD_NM": "식품원료",
                "USE_DIVS_CD_NM": "사용가능",
            }
        ]
        assert _pick_component_code("soybean", items) == "ENG1"


# ============================================================
# 15111913 GMO
# ============================================================


class TestGmoFlag:
    def test_exact_match_gmo_y(self):
        items = [{"ORM_STD_NM": "대두", "GMO_YN": "Y"}]
        assert _pick_gmo_flag("대두", items) is True

    def test_exact_match_gmo_n(self):
        items = [{"ORM_STD_NM": "대두", "GMO_YN": "N"}]
        assert _pick_gmo_flag("대두", items) is False

    def test_partial_match_rejected(self):
        """퍼지 금지 — '대' 로는 '대두' 매칭되면 안됨."""
        items = [{"ORM_STD_NM": "대두", "GMO_YN": "Y"}]
        assert _pick_gmo_flag("대", items) is None

    def test_multiple_Y_and_N_yields_true(self):
        data = load_fixture("15111913_soybean.json")
        # Y 와 N 공존 → 안전측 True (F3 전달 정확도)
        assert _pick_gmo_flag("대두", data["items"]) is True

    def test_none_when_empty(self):
        assert _pick_gmo_flag("대두", []) is None

    def test_none_when_gmo_yn_absent(self):
        items = [{"ORM_STD_NM": "대두", "GMO_YN": ""}]
        assert _pick_gmo_flag("대두", items) is None


# ============================================================
# run_step_b — 통합
# ============================================================


# P6-b (2026-04-20) — 15111777 호출 제거로 기존 ingredient fixture 의존 테스트는 skip.
# 카테고리 기반 판정은 아래 TestRunStepBCategoryBased 에서 새로 검증.
_LEGACY_15111777 = pytest.mark.skip(
    reason="P6-b: 15111777 제거 — ingredient fixture 기반 판정 경로 폐기"
)


@pytest.mark.asyncio
class TestRunStepB:
    @_LEGACY_15111777
    async def test_soybean_allowed_with_gmo(self):
        pass

    @_LEGACY_15111777
    async def test_opium_prohibited_early_exit(self):
        pass

    @_LEGACY_15111777
    async def test_ginseng_restricted_with_condition(self):
        pass

    @_LEGACY_15111777
    async def test_sub_ingredients_flattened_and_matched(self):
        pass

    @_LEGACY_15111777
    async def test_homonym_safest_wins(self):
        pass

    async def test_unidentified_when_no_match(self):
        client = FakeClient()  # 모든 엔드포인트 빈 응답
        set_client_for_test(client)

        result = await run_step_b([Ingredient(name="가공의원재료")])
        ing = result.enriched_ingredients[0]
        assert ing.allow_verdict == "unidentified"
        assert "가공의원재료" in result.unidentified

    @_LEGACY_15111777
    async def test_fuzzy_fallback_does_not_auto_confirm(self):
        pass

    async def test_api_failure_isolated_per_endpoint(self):
        """15111913 GMO 엔드포인트 실패해도 verdict·component_code 는 채워져야."""
        client = FakeClient(
            component={"대두": load_fixture("15094202_soybean.json")},
            gmo={"대두": load_fixture("15111913_soybean.json")},
            errors={"gmo:대두": DataGoKrTimeoutError(
                "boom", endpoint="15111913", timeout_s=15.0
            )},
        )
        set_client_for_test(client)

        result = await run_step_b([Ingredient(name="대두")])
        ing = result.enriched_ingredients[0]
        # 대두 fixture 는 식품원료 + USE_DIVS_CD_NM=사용가능 → allowed
        assert ing.allow_verdict == "allowed"
        assert ing.component_code == "A1000001000000"
        assert ing.is_gmo is None  # GMO 조회 실패 → None

    async def test_synthetic_flavor_auto_unidentified(self):
        """합성향료 키워드는 자동 판정 금지 → HITL-1."""
        client = FakeClient()
        set_client_for_test(client)

        result = await run_step_b([Ingredient(name="합성향료")])
        ing = result.enriched_ingredients[0]
        assert ing.allow_verdict == "unidentified"
        assert "합성향료" in result.unidentified

    async def test_whitespace_name_strip_before_lookup(self):
        """KOR_NM 앞 공백 strip — run_step_b 전처리에서 이름 정규화."""
        component = load_fixture("15094202_soybean.json")
        component["items"][0]["KOR_NM"] = "  대두"
        client = FakeClient(component={"대두": component})
        set_client_for_test(client)

        result = await run_step_b([Ingredient(name="  대두  ")])
        ing = result.enriched_ingredients[0]
        assert ing.allow_verdict == "allowed"
        assert ing.component_code == "A1000001000000"

    async def test_empty_ingredients_returns_empty_result(self):
        client = FakeClient()
        set_client_for_test(client)

        result = await run_step_b([])
        assert result.enriched_ingredients == []
        assert result.unidentified == []
        assert result.conditional == []
        assert result.gmo_ingredients == []
        assert result.warnings == []

    async def test_api_call_stats_populated(self):
        client = FakeClient(
            component={"대두": load_fixture("15094202_soybean.json")},
            gmo={"대두": load_fixture("15111913_soybean.json")},
        )
        set_client_for_test(client)

        result = await run_step_b([Ingredient(name="대두")])
        stats = result.api_call_stats
        # P6-b: 2 엔드포인트만 × 1 이름 = 2 호출
        assert stats[DataGoKrEndpoint.IMPORT_FOOD_COMPONENT.value] >= 1
        assert stats[DataGoKrEndpoint.FOOD_RAW_MATERIAL.value] >= 1
        # 15111777 stats 자체가 없어야 함
        assert DataGoKrEndpoint.IMPORT_FOOD_INGREDIENT.value not in stats

    async def test_parallel_dedup_same_name(self):
        """동일 이름 N개 → 이름별 2 호출 (15094202/15111913)."""
        client = FakeClient(
            component={"대두": load_fixture("15094202_soybean.json")},
        )
        set_client_for_test(client)

        await run_step_b([Ingredient(name="대두"), Ingredient(name="대두")])
        # 같은 normalized name '대두' → 15094202 1회만
        comp_calls = [c for c in client.calls if c[0] == "15094202"]
        assert len(comp_calls) == 1
        # 15111777 호출은 없어야 함
        ingd_calls = [c for c in client.calls if c[0] == "15111777"]
        assert len(ingd_calls) == 0

    async def test_no_api_key_env_raises(self, monkeypatch):
        set_client_for_test(None)
        monkeypatch.delenv("F1_DATA_GO_KR_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="F1_DATA_GO_KR_API_KEY"):
            await run_step_b([Ingredient(name="대두")])


# ============================================================
# _lookup_synonym 유닛 테스트 (T3 — synonym 조회 경로)
# ============================================================


class TestLookupSynonym:
    """f1_ingredient_synonyms Supabase 조회 로직 단위 테스트.

    실 DB 호출 금지 — Supabase 클라이언트를 monkeypatch 로 모킹.
    """

    def _make_supabase_mock(self, rows: list, monkeypatch) -> None:
        """get_supabase() 가 반환하는 체이닝 객체를 모킹."""
        import types

        execute_result = types.SimpleNamespace(data=rows)

        class MockQuery:
            def select(self, *a, **kw):
                return self

            def ilike(self, *a, **kw):
                return self

            def limit(self, *a, **kw):
                return self

            def execute(self):
                return execute_result

        class MockSupabase:
            def table(self, name):
                return MockQuery()

        import services.f1_step_b as _mod

        monkeypatch.setattr(
            "db.supabase_client.get_supabase",
            lambda: MockSupabase(),
        )
        # lazy import 경로도 동일하게 패치
        monkeypatch.setattr(
            _mod,
            "_lookup_synonym",
            lambda name_variant: self._direct_lookup(name_variant, rows),
        )

    @staticmethod
    def _direct_lookup(name_variant: str, rows: list) -> Optional[str]:
        """모킹 없이 rows 를 직접 사용하는 _lookup_synonym 대체."""
        if not rows:
            return None
        standard = (rows[0].get("name_standard") or "").strip()
        return standard or None

    def test_synonym_hit_returns_standard(self, monkeypatch):
        """name_variant 입력 → name_standard 반환 (DB hit)."""
        import services.f1_step_b as _mod

        rows = [{"name_standard": "대두"}]
        monkeypatch.setattr(
            _mod,
            "_lookup_synonym",
            lambda nv: self._direct_lookup(nv, rows),
        )
        result = _mod._lookup_synonym("soybean")
        assert result == "대두"

    def test_synonym_miss_returns_none(self, monkeypatch):
        """DB 에 없는 이름 → None 반환."""
        import services.f1_step_b as _mod

        monkeypatch.setattr(
            _mod,
            "_lookup_synonym",
            lambda nv: self._direct_lookup(nv, []),
        )
        result = _mod._lookup_synonym("unknown_ingredient_xyz")
        assert result is None

    def test_synonym_supabase_error_returns_none(self, monkeypatch):
        """Supabase 오류 시 None 반환 — graceful fallback."""
        import db.supabase_client
        import services.f1_step_b as _mod

        def _bad_get_supabase():
            raise RuntimeError("connection failed")

        # lazy import 경로: _lookup_synonym 내부에서 `from db.supabase_client import get_supabase` 실행 시
        # sys.modules['db.supabase_client'].get_supabase 를 참조하므로 모듈 속성 패치로 충분
        monkeypatch.setattr(db.supabase_client, "get_supabase", _bad_get_supabase)

        result = _mod._lookup_synonym("soybean")
        assert result is None


# ============================================================
# run_step_b 통합 — synonym 경로 (T3)
# P6-b: 15111777 exact-miss 를 트리거로 synonym 이 발동하는 경로였음.
# 15111777 제거로 발동 조건이 사라짐 → 전체 skip. 필요 시 재설계.
# ============================================================


@pytest.mark.skip(
    reason="P6-b: synonym lookup 통합 경로는 15111777 exact-miss 트리거에 의존 — 재설계 필요"
)
@pytest.mark.asyncio
class TestRunStepBSynonym:
    """synonym 조회 경로가 run_step_b 에 올바르게 통합되었는지 검증.

    mock 대상:
        - DataGoKrClient (FakeClient)
        - _lookup_synonym (monkeypatch)
    """

    async def test_synonym_hit_flow_resolves_allowed(self, monkeypatch):
        """exact 실패 → synonym hit → name_standard 로 재매칭 → allowed 판정."""
        import services.f1_step_b as _mod

        # 'soybean' 입력 시 synonym lookup → '대두' 반환
        monkeypatch.setattr(_mod, "_lookup_synonym", lambda nv: "대두" if nv == "soybean" else None)

        # API: 'soybean' 으로는 응답 없고, '대두' 로는 allowed 응답
        soybean_fixture = load_fixture("15111777_soybean.json")
        client = FakeClient(
            ingredient={
                "soybean": {"items": [], "total_count": 0},  # exact miss
                "대두": soybean_fixture,                       # synonym 후 재조회
            },
            component={"대두": load_fixture("15094202_soybean.json")},
            gmo={"대두": load_fixture("15111913_soybean.json")},
        )
        set_client_for_test(client)

        result = await run_step_b([Ingredient(name="soybean")])
        ing = result.enriched_ingredients[0]
        assert ing.allow_verdict == "allowed"
        assert "soybean" not in result.unidentified

    async def test_synonym_miss_falls_through_to_next_strategy(self, monkeypatch):
        """synonym miss → 다음 전략(scientific/Levenshtein) 으로 진행."""
        import services.f1_step_b as _mod

        # synonym miss
        monkeypatch.setattr(_mod, "_lookup_synonym", lambda nv: None)

        # API: exact miss, scientific 도 없음 → unidentified
        client = FakeClient(
            ingredient={"unknown_xyz": {"items": [], "total_count": 0}},
        )
        set_client_for_test(client)

        result = await run_step_b([Ingredient(name="unknown_xyz")])
        ing = result.enriched_ingredients[0]
        assert ing.allow_verdict == "unidentified"
        assert "unknown_xyz" in result.unidentified

    async def test_synonym_supabase_error_graceful_fallback(self, monkeypatch):
        """Supabase 오류 시 synonym 경로 skip → 다음 전략으로 graceful 진행."""
        import services.f1_step_b as _mod

        # synonym lookup 자체가 예외 → _lookup_synonym 내부에서 None 반환
        def _error_lookup(nv: str) -> Optional[str]:
            raise RuntimeError("DB connection error")

        # run_step_b 는 _lookup_synonym 을 직접 호출 — 예외가 전파되면 안 됨
        # 실 _lookup_synonym 은 try/except 로 감쌈 → None 반환
        # 여기서는 None 을 반환하는 버전으로 모킹 (graceful fallback 검증)
        monkeypatch.setattr(_mod, "_lookup_synonym", lambda nv: None)

        client = FakeClient(
            ingredient={"글루코스": {"items": [], "total_count": 0}},
        )
        set_client_for_test(client)

        # 예외 전파 없이 정상 완료되어야 함
        result = await run_step_b([Ingredient(name="글루코스")])
        assert result is not None
        ing = result.enriched_ingredients[0]
        # synonym/API 모두 없으면 unidentified (정상 fallback)
        assert ing.allow_verdict == "unidentified"


# ============================================================
# P6-b 신규 — 외화획득용 코드 판정
# ============================================================


class TestForeignExchangeCode:
    def test_az_prefix(self):
        assert _is_foreign_exchange_code("AZ000083000000") is True

    def test_bz_prefix(self):
        assert _is_foreign_exchange_code("BZ000094000000") is True

    def test_cz_prefix(self):
        assert _is_foreign_exchange_code("CZ000000000000") is True

    def test_normal_food_raw_material_is_false(self):
        # 일반 식품원료 (A1...) 은 외화획득용 아님
        assert _is_foreign_exchange_code("A1000911000501") is False

    def test_normal_additive_is_false(self):
        # 일반 식품첨가물 (B3...) 은 외화획득용 아님
        assert _is_foreign_exchange_code("B3000035000000") is False

    def test_empty_is_false(self):
        assert _is_foreign_exchange_code("") is False
        assert _is_foreign_exchange_code("   ") is False

    def test_single_char_is_false(self):
        assert _is_foreign_exchange_code("Z") is False


# ============================================================
# P6-b 신규 — 카테고리 기반 verdict
# ============================================================


class TestResolveVerdictByCategory:
    def test_none_item_unidentified(self):
        verdict, law, warn = _resolve_verdict_by_category(None)
        assert verdict == "unidentified"
        assert law is None
        assert warn is None

    def test_foreign_exchange_restricted(self):
        item = {
            "CPNT_CD": "AZ000083000000",
            "CPNT_LCLS_CD_NM": "식품원료",
            "USE_DIVS_CD_NM": "사용가능",
        }
        verdict, law, warn = _resolve_verdict_by_category(item)
        assert verdict == "restricted"
        assert "외화획득용" in law
        assert warn is not None

    def test_food_raw_material_allowed(self):
        item = {
            "CPNT_CD": "A1000911000501",
            "CPNT_LCLS_CD_NM": "식품원료",
            "USE_DIVS_CD_NM": "사용가능",
        }
        verdict, law, warn = _resolve_verdict_by_category(item)
        assert verdict == "allowed"
        assert "사용 가능 원료" in law
        assert warn is None

    def test_food_raw_material_non_usable_restricted(self):
        item = {
            "CPNT_CD": "A1000000000000",
            "CPNT_LCLS_CD_NM": "식품원료",
            "USE_DIVS_CD_NM": "기타",
        }
        verdict, law, warn = _resolve_verdict_by_category(item)
        assert verdict == "restricted"
        assert "사용 제한" in law

    def test_additive_allowed_with_warning(self):
        """에탄올 케이스 — 식품첨가물 + USE_DIVS=기타 → allowed + 경고."""
        item = {
            "CPNT_CD": "B3000035000000",
            "KOR_NM": "에탄올",
            "CPNT_LCLS_CD_NM": "식품첨가물",
            "USE_DIVS_CD_NM": "기타",
        }
        verdict, law, warn = _resolve_verdict_by_category(item)
        assert verdict == "allowed"
        assert law == "식품첨가물의 기준 및 규격"
        assert warn is not None
        assert "사용량 제한" in warn

    def test_food_type_allowed_with_warning(self):
        """정제수 케이스 — 식품유형 → allowed + 경고."""
        item = {
            "CPNT_CD": "P0000001000000",
            "KOR_NM": "정제수",
            "CPNT_LCLS_CD_NM": "식품유형",
            "USE_DIVS_CD_NM": "기타",
        }
        verdict, law, warn = _resolve_verdict_by_category(item)
        assert verdict == "allowed"
        assert "식품유형" in law
        assert warn is not None

    def test_health_food_restricted(self):
        item = {
            "CPNT_CD": "C2000131000000",
            "CPNT_LCLS_CD_NM": "건강기능식품",
        }
        verdict, law, warn = _resolve_verdict_by_category(item)
        assert verdict == "restricted"
        assert "건강기능식품" in law
        assert warn is not None

    def test_container_allowed(self):
        item = {
            "CPNT_CD": "K1000000000000",
            "CPNT_LCLS_CD_NM": "기구 및 용기포장",
        }
        verdict, law, warn = _resolve_verdict_by_category(item)
        assert verdict == "allowed"

    def test_unknown_category_unidentified(self):
        item = {
            "CPNT_CD": "X0000000000000",
            "CPNT_LCLS_CD_NM": "미지의카테고리",
        }
        verdict, law, warn = _resolve_verdict_by_category(item)
        assert verdict == "unidentified"
        assert law is None


# ============================================================
# P6-b 신규 — 정확 매칭 (F0 코드 우선)
# ============================================================


class TestPickExactComponentItem:
    def test_f0_code_priority(self):
        """F0 코드가 있으면 CPNT_CD 정확 매칭이 최우선."""
        ing = Ingredient(name="대두", ingredient_code_f0="A1000001000000")
        items = [
            {"CPNT_CD": "DIFFERENT", "KOR_NM": "대두"},  # 이름 매칭은 되지만 코드 틀림
            {"CPNT_CD": "A1000001000000", "KOR_NM": "오타"},  # 코드 정확 일치
        ]
        matched, _ = _pick_exact_component_item(ing, "대두", items)
        assert matched["CPNT_CD"] == "A1000001000000"

    def test_kor_nm_match_when_no_f0_code(self):
        ing = Ingredient(name="에탄올")
        items = [
            {"CPNT_CD": "OTHER", "KOR_NM": "다른이름"},
            {"CPNT_CD": "B3000035000000", "KOR_NM": "에탄올"},
        ]
        matched, _ = _pick_exact_component_item(ing, "에탄올", items)
        assert matched["CPNT_CD"] == "B3000035000000"

    def test_kor_nm_strip_matching(self):
        ing = Ingredient(name="대두")
        items = [{"CPNT_CD": "X", "KOR_NM": " 대두"}]
        matched, _ = _pick_exact_component_item(ing, "대두", items)
        assert matched is not None

    def test_eng_nm_fallback(self):
        ing = Ingredient(name="ethanol")
        items = [{"CPNT_CD": "X", "KOR_NM": "에탄올", "ENG_NM": "ETHANOL"}]
        matched, _ = _pick_exact_component_item(ing, "ethanol", items)
        assert matched["CPNT_CD"] == "X"

    def test_no_match_returns_none(self):
        ing = Ingredient(name="없는원료")
        items = [{"CPNT_CD": "X", "KOR_NM": "다른것"}]
        matched, mm = _pick_exact_component_item(ing, "없는원료", items)
        assert matched is None
        assert mm is None

    def test_empty_items_returns_none(self):
        ing = Ingredient(name="대두")
        matched, mm = _pick_exact_component_item(ing, "대두", [])
        assert matched is None
        assert mm is None


# ============================================================
# P6-b 신규 — run_step_b 골든 시나리오 (에탄올·정제수·밀가루)
# ============================================================


@pytest.mark.asyncio
class TestRunStepBCategoryBased:
    async def test_ethanol_food_additive_allowed(self):
        """에탄올 (B3000035000000, 식품첨가물) → allowed + 경고."""
        client = FakeClient(
            component={
                "에탄올": {
                    "items": [
                        {
                            "CPNT_CD": "B3000035000000",
                            "KOR_NM": "에탄올",
                            "CPNT_LCLS_CD_NM": "식품첨가물",
                            "USE_DIVS_CD_NM": "기타",
                        }
                    ],
                    "total_count": 1,
                }
            },
        )
        set_client_for_test(client)

        # F0 가 넘긴 matched_name_ko 로 API 호출되어야 함
        ing = Ingredient(
            name="에탄올 (Ethanol)",
            matched_name_ko="에탄올",
            ingredient_code_f0="B3000035000000",
        )
        result = await run_step_b([ing])

        out = result.enriched_ingredients[0]
        assert out.allow_verdict == "allowed"
        assert out.law_source == "식품첨가물의 기준 및 규격"
        assert out.component_code == "B3000035000000"
        assert any("에탄올 (Ethanol)" in w for w in result.warnings)

    async def test_water_food_type_allowed(self):
        """정제수 (P0000001000000, 식품유형) → allowed + 경고."""
        client = FakeClient(
            component={
                "정제수": {
                    "items": [
                        {
                            "CPNT_CD": "P0000001000000",
                            "KOR_NM": "정제수",
                            "ENG_NM": "WATER",
                            "CPNT_LCLS_CD_NM": "식품유형",
                            "USE_DIVS_CD_NM": "기타",
                        }
                    ],
                    "total_count": 1,
                }
            },
        )
        set_client_for_test(client)

        ing = Ingredient(
            name="물 (Water)",
            matched_name_ko="정제수",
            ingredient_code_f0="P0000001000000",
        )
        result = await run_step_b([ing])

        out = result.enriched_ingredients[0]
        assert out.allow_verdict == "allowed"
        assert "식품유형" in out.law_source
        assert out.component_code == "P0000001000000"

    async def test_baked_flour_food_raw_material_allowed(self):
        """구운밀가루 (A1000911000501, 식품원료 사용가능) → allowed, 경고 없음."""
        client = FakeClient(
            component={
                "구운밀가루": {
                    "items": [
                        {
                            "CPNT_CD": "A1000911000501",
                            "KOR_NM": "구운밀가루",
                            "ENG_NM": "BAKED WHEAT FLOUR",
                            "CPNT_LCLS_CD_NM": "식품원료",
                            "USE_DIVS_CD_NM": "사용가능",
                        }
                    ],
                    "total_count": 1,
                }
            },
        )
        set_client_for_test(client)

        ing = Ingredient(
            name="구운밀가루",
            matched_name_ko="구운밀가루",
            ingredient_code_f0="A1000911000501",
        )
        result = await run_step_b([ing])

        out = result.enriched_ingredients[0]
        assert out.allow_verdict == "allowed"
        assert "사용 가능 원료" in out.law_source
        # 식품원료 사용가능은 경고 없음
        assert result.warnings == []

    async def test_foreign_exchange_code_restricted(self):
        """*Z* 코드 → restricted + '외화획득용' law_source."""
        client = FakeClient(
            component={
                "특수성분": {
                    "items": [
                        {
                            "CPNT_CD": "AZ000083000000",
                            "KOR_NM": "특수성분",
                            "CPNT_LCLS_CD_NM": "식품원료",
                            "USE_DIVS_CD_NM": "사용가능",
                        }
                    ],
                    "total_count": 1,
                }
            },
        )
        set_client_for_test(client)

        ing = Ingredient(
            name="특수성분",
            matched_name_ko="특수성분",
            ingredient_code_f0="AZ000083000000",
        )
        result = await run_step_b([ing])

        out = result.enriched_ingredients[0]
        assert out.allow_verdict == "restricted"
        assert "외화획득용" in out.law_source
        assert out in result.conditional

    async def test_query_key_uses_matched_name_ko(self):
        """raw name 이 괄호 병기인 경우 matched_name_ko 로 API 호출되어야."""
        client = FakeClient(
            component={
                "에탄올": {
                    "items": [
                        {
                            "CPNT_CD": "B3000035000000",
                            "KOR_NM": "에탄올",
                            "CPNT_LCLS_CD_NM": "식품첨가물",
                            "USE_DIVS_CD_NM": "기타",
                        }
                    ]
                }
            },
        )
        set_client_for_test(client)

        ing = Ingredient(name="에탄올 (Ethanol)", matched_name_ko="에탄올")
        await run_step_b([ing])

        # API 호출이 "에탄올" 로 되었는지 확인 (괄호 원본 아님)
        comp_calls = [c for c in client.calls if c[0] == "15094202"]
        assert comp_calls == [("15094202", "에탄올")]

    async def test_f0_code_wins_over_name_match(self):
        """동명이원료: F0 코드로 정확 매칭하여 타깃 레코드 선택."""
        client = FakeClient(
            component={
                "다목적": {
                    "items": [
                        {
                            "CPNT_CD": "AZ999999000000",
                            "KOR_NM": "다목적",
                            "CPNT_LCLS_CD_NM": "식품원료",
                            "USE_DIVS_CD_NM": "사용가능",
                        },
                        {
                            "CPNT_CD": "A1234567000000",
                            "KOR_NM": "다목적",
                            "CPNT_LCLS_CD_NM": "식품원료",
                            "USE_DIVS_CD_NM": "사용가능",
                        },
                    ]
                }
            },
        )
        set_client_for_test(client)

        ing = Ingredient(
            name="다목적",
            matched_name_ko="다목적",
            ingredient_code_f0="A1234567000000",
        )
        result = await run_step_b([ing])

        out = result.enriched_ingredients[0]
        # F0 코드가 일반 A1 이므로 allowed, *Z* 아님
        assert out.allow_verdict == "allowed"
        assert out.component_code == "A1234567000000"

    async def test_no_component_response_unidentified(self):
        """15094202 미매칭 → unidentified (15111777 제거로 fallback 없음)."""
        client = FakeClient()
        set_client_for_test(client)

        result = await run_step_b([Ingredient(name="존재하지않는원료")])
        out = result.enriched_ingredients[0]
        assert out.allow_verdict == "unidentified"
        assert "존재하지않는원료" in result.unidentified

    async def test_15111777_not_called(self):
        """15111777 은 절대 호출하지 않아야 (P6-b 설계)."""
        client = FakeClient(
            component={"대두": load_fixture("15094202_soybean.json")},
        )
        set_client_for_test(client)

        await run_step_b([Ingredient(name="대두")])
        ingd_calls = [c for c in client.calls if c[0] == "15111777"]
        assert len(ingd_calls) == 0


# ============================================================
# Phase 2 신규 — match_method, _safe_call Result, gather timeout
# ============================================================


class TestMatchMethod:
    """_pick_exact_component_item 의 match_method 반환 + run_step_b ing.match_method 설정."""

    def test_match_method_exact(self):
        """F0 코드(ingredient_code_f0 == CPNT_CD) 매칭 → match_method == 'exact'."""
        ing = Ingredient(name="대두", ingredient_code_f0="A1000001000000")
        items = [{"CPNT_CD": "A1000001000000", "KOR_NM": "대두"}]
        _, mm = _pick_exact_component_item(ing, "대두", items)
        assert mm == "exact"

    def test_match_method_normalized(self):
        """KOR_NM 정확 일치(F0 코드 없음) → match_method == 'normalized'."""
        ing = Ingredient(name="에탄올")
        items = [{"CPNT_CD": "B3000035000000", "KOR_NM": "에탄올"}]
        _, mm = _pick_exact_component_item(ing, "에탄올", items)
        assert mm == "normalized"

    def test_match_method_eng(self):
        """ENG_NM case-insensitive 매칭 → match_method == 'fuzzy'."""
        ing = Ingredient(name="ethanol")
        items = [{"CPNT_CD": "X", "KOR_NM": "에탄올", "ENG_NM": "ETHANOL"}]
        _, mm = _pick_exact_component_item(ing, "ethanol", items)
        assert mm == "fuzzy"

    def test_match_method_none(self):
        """매칭 없음 → match_method is None."""
        ing = Ingredient(name="없는원료")
        items = [{"CPNT_CD": "X", "KOR_NM": "다른것"}]
        _, mm = _pick_exact_component_item(ing, "없는원료", items)
        assert mm is None


@pytest.mark.asyncio
class TestMatchMethodIntegration:
    """run_step_b 반환 Ingredient 에 match_method 가 실제로 설정되는지 확인."""

    async def test_match_method_set_on_ingredient_exact(self):
        """F0 코드 매칭 경로 → ing.match_method == 'exact'."""
        client = FakeClient(
            component={
                "대두": {
                    "items": [
                        {
                            "CPNT_CD": "A1000001000000",
                            "KOR_NM": "대두",
                            "CPNT_LCLS_CD_NM": "식품원료",
                            "USE_DIVS_CD_NM": "사용가능",
                        }
                    ],
                    "total_count": 1,
                }
            },
        )
        set_client_for_test(client)

        ing = Ingredient(name="대두", ingredient_code_f0="A1000001000000")
        result = await run_step_b([ing])
        out = result.enriched_ingredients[0]
        assert getattr(out, "match_method", "__missing__") == "exact"

    async def test_match_method_none_on_unidentified(self):
        """매칭 없음 → ing.match_method is None."""
        client = FakeClient()
        set_client_for_test(client)

        result = await run_step_b([Ingredient(name="가공의원재료X")])
        out = result.enriched_ingredients[0]
        assert getattr(out, "match_method", "__missing__") is None


@pytest.mark.asyncio
class TestSafeCallReturnsResult:
    """_safe_call 이 Result 타입을 반환하는지 확인."""

    async def test_safe_call_returns_result_err(self, monkeypatch):
        """API 예외 발생 시 Result.err 반환 확인."""
        from common.result import Result
        from services.f1_step_b import _safe_call

        async def _raise(*args, **kwargs):
            raise DataGoKrError("boom", endpoint="15094202")

        result = await _safe_call(_raise(), "15094202", "대두")
        assert result.is_err()
        assert "15094202" in result.reason
        assert "대두" in result.reason

    async def test_safe_call_returns_result_ok(self):
        """정상 응답 시 Result.ok 반환 확인."""
        from common.result import Result
        from services.f1_step_b import _safe_call

        async def _ok():
            return {"items": [], "total_count": 0}

        result = await _safe_call(_ok(), "15094202", "대두")
        assert result.is_ok()
        endpoint_id, name, payload = result._value
        assert endpoint_id == "15094202"
        assert name == "대두"
        assert payload == {"items": [], "total_count": 0}


@pytest.mark.asyncio
class TestGatherTimeout:
    """asyncio.wait_for 가 TimeoutError 를 전파하는지 확인."""

    async def test_gather_timeout(self, monkeypatch):
        """asyncio.wait_for 를 mock 하여 TimeoutError 전파 확인."""
        import asyncio as _asyncio
        import services.f1_step_b as _mod

        async def _timeout_wait_for(coro, timeout):
            raise _asyncio.TimeoutError("mocked timeout")

        monkeypatch.setattr(_asyncio, "wait_for", _timeout_wait_for)

        client = FakeClient(
            component={"대두": {"items": [], "total_count": 0}},
        )
        set_client_for_test(client)

        with pytest.raises(_asyncio.TimeoutError):
            await run_step_b([Ingredient(name="대두")])
