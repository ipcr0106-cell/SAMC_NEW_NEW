"""W2-A Step A 금지원료 체크 단위 테스트.

커버리지 목표: 85%+

테스트 시나리오:
    1. DB hit 단독 → stopped=True, API 호출 없음
    2. API hit 단독 (EDIBLE_INFO="불가") → stopped=True, "DB 미등록" 경고 포함
    3. API hit 단독 (EDIBLE_N="o") → stopped=True
    4. DB + API 동일 원재료 → 중복 제거 (source="db" 우선)
    5. API 장애 → api_errors 기록, DB 결과로만 판정
    6. 원재료명 공백/대소문자 무관 매칭
    7. sub_ingredients 하위 성분 검사 (재귀 평탄화)
    8. 금지 원료 없음 → stopped=False, forbidden_hits=[]
    9. 빈 ingredients → stopped=False
    10. law_refs 수집 확인

실행:
    cd backend
    pytest tests/services/test_f1_step_a.py -v --cov=services.f1_step_a
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.f1_types import ForbiddenHit, StepAResult
from models.judgment import Ingredient
from services.f1_step_a import (
    _flatten_ingredients,
    _merge_hits,
    _normalize,
    _query_db_forbidden,
    run_step_a,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "f1_step_a"


def load_fixture(filename: str) -> Any:
    with open(FIXTURES_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# 내부 헬퍼 단위테스트
# ============================================================


class TestNormalize:
    def test_strips_whitespace(self) -> None:
        assert _normalize("  아편  ") == "아편"

    def test_lowercases(self) -> None:
        assert _normalize("Cannabis") == "cannabis"

    def test_strips_and_lowercases(self) -> None:
        assert _normalize("  Cannabis Extract  ") == "cannabis extract"


class TestFlattenIngredients:
    def test_flat_list(self) -> None:
        ings = [Ingredient(name="A"), Ingredient(name="B")]
        result = _flatten_ingredients(ings)
        assert len(result) == 2
        assert result[0].name == "A"

    def test_single_level_sub(self) -> None:
        ings = [
            Ingredient(name="복합원료", sub_ingredients=[Ingredient(name="하위A")])
        ]
        result = _flatten_ingredients(ings)
        assert len(result) == 2
        names = [i.name for i in result]
        assert "복합원료" in names
        assert "하위A" in names

    def test_two_level_sub(self) -> None:
        ings = [
            Ingredient(
                name="최상위",
                sub_ingredients=[
                    Ingredient(
                        name="중간",
                        sub_ingredients=[Ingredient(name="최하위")],
                    )
                ],
            )
        ]
        result = _flatten_ingredients(ings)
        assert len(result) == 3
        names = [i.name for i in result]
        assert "최상위" in names
        assert "중간" in names
        assert "최하위" in names

    def test_empty(self) -> None:
        assert _flatten_ingredients([]) == []


class TestMergeHits:
    def _make_hit(self, name: str, source: str, law_ref: str | None = None) -> ForbiddenHit:
        return ForbiddenHit(
            ingredient_name=name,
            matched_name=name,
            source=source,  # type: ignore[arg-type]
            reason="test",
            law_ref=law_ref,
        )

    def test_db_only(self) -> None:
        db = [self._make_hit("아편", "db", "law-001")]
        result = _merge_hits(db, [])
        assert len(result) == 1
        assert result[0].source == "db"

    def test_api_only(self) -> None:
        api = [self._make_hit("금지A", "api")]
        result = _merge_hits([], api)
        assert len(result) == 1
        assert result[0].source == "api"
        # DB 미등록 경고 포함
        assert "DB 미등록" in result[0].reason

    def test_db_priority_on_duplicate(self) -> None:
        db = [self._make_hit("아편", "db", "law-001")]
        api = [self._make_hit("아편", "api")]
        result = _merge_hits(db, api)
        assert len(result) == 1
        assert result[0].source == "db"
        assert result[0].law_ref == "law-001"

    def test_both_different_names(self) -> None:
        db = [self._make_hit("아편", "db")]
        api = [self._make_hit("대마초", "api")]
        result = _merge_hits(db, api)
        assert len(result) == 2


# ============================================================
# run_step_a 통합 테스트 (Supabase + DataGoKrClient mock)
# ============================================================


def _make_mock_client(
    items: list[Dict[str, Any]] | None = None,
    raise_exc: Exception | None = None,
) -> MagicMock:
    """DataGoKrClient mock 생성 헬퍼."""
    mock = MagicMock()
    if raise_exc is not None:
        mock.get_import_food_ingredient = AsyncMock(side_effect=raise_exc)
    else:
        mock.get_import_food_ingredient = AsyncMock(
            return_value={"items": items or [], "total_count": len(items or []), "raw": {}}
        )
    mock.aclose = AsyncMock()
    return mock


def _patch_supabase(rows: list[Dict[str, Any]]):
    """Supabase get_supabase() 전체 체인 mock 패치 컨텍스트."""
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.execute.return_value.data = rows
    return patch("services.f1_step_a.get_supabase", return_value=mock_sb)


class TestRunStepA:
    # ------------------------------------------------------------------
    # 시나리오 1: DB hit 단독 → stopped=True
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_db_hit_only_stops(self) -> None:
        db_rows = [{"name_ko": "아편", "reason": "마약류관리법", "law_ref": "law-001"}]
        mock_client = _make_mock_client(items=[])

        with _patch_supabase(db_rows):
            result = await run_step_a(
                [Ingredient(name="아편")],
                client=mock_client,
            )

        assert result.stopped is True
        assert len(result.forbidden_hits) == 1
        assert result.forbidden_hits[0].source == "db"
        assert result.forbidden_hits[0].ingredient_name == "아편"
        assert "law-001" in result.law_refs
        assert result.api_errors == []

    # ------------------------------------------------------------------
    # 시나리오 2: API hit (EDIBLE_INFO="불가") → stopped=True
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_api_hit_edible_info_stops(self) -> None:
        api_item = {
            "INGD_SN": "99999",
            "INGD_NM": "금지원료A",
            "EDIBLE_INFO": "불가",
            "EDIBLE_N": None,
        }
        mock_client = _make_mock_client(items=[api_item])

        with _patch_supabase([]):  # DB 미등록
            result = await run_step_a(
                [Ingredient(name="금지원료A")],
                client=mock_client,
            )

        assert result.stopped is True
        assert len(result.forbidden_hits) == 1
        assert result.forbidden_hits[0].source == "api"
        assert "DB 미등록" in result.forbidden_hits[0].reason
        assert result.api_errors == []

    # ------------------------------------------------------------------
    # 시나리오 3: API hit (EDIBLE_N="o") → stopped=True
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_api_hit_edible_n_stops(self) -> None:
        api_item = {
            "INGD_SN": "88888",
            "INGD_NM": "금지원료B",
            "EDIBLE_INFO": None,
            "EDIBLE_N": "o",
        }
        mock_client = _make_mock_client(items=[api_item])

        with _patch_supabase([]):
            result = await run_step_a(
                [Ingredient(name="금지원료B")],
                client=mock_client,
            )

        assert result.stopped is True
        assert result.forbidden_hits[0].source == "api"

    # ------------------------------------------------------------------
    # 시나리오 4: DB + API 동일 원재료 → 중복 제거, source="db" 우선
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_db_and_api_both_hit_deduplication(self) -> None:
        db_rows = [{"name_ko": "아편", "reason": "마약류관리법", "law_ref": "law-001"}]
        api_item = {
            "INGD_SN": "99999",
            "INGD_NM": "아편",
            "EDIBLE_INFO": "불가",
            "EDIBLE_N": None,
        }
        mock_client = _make_mock_client(items=[api_item])

        with _patch_supabase(db_rows):
            result = await run_step_a(
                [Ingredient(name="아편")],
                client=mock_client,
            )

        assert result.stopped is True
        # 중복 제거 — 1건만
        assert len(result.forbidden_hits) == 1
        assert result.forbidden_hits[0].source == "db"
        assert result.forbidden_hits[0].law_ref == "law-001"

    # ------------------------------------------------------------------
    # 시나리오 5: API 장애 → api_errors 기록, DB 결과로만 판정
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_api_error_falls_back_to_db(self) -> None:
        from exceptions import DataGoKrError

        db_rows = [{"name_ko": "아편", "reason": "마약류관리법", "law_ref": "law-001"}]
        mock_client = _make_mock_client(
            raise_exc=DataGoKrError("timeout", endpoint="15111777")
        )

        with _patch_supabase(db_rows):
            result = await run_step_a(
                [Ingredient(name="아편")],
                client=mock_client,
            )

        assert result.stopped is True  # DB 결과로 판정
        assert len(result.forbidden_hits) == 1
        assert result.forbidden_hits[0].source == "db"
        assert len(result.api_errors) == 1
        assert "아편" in result.api_errors[0]

    @pytest.mark.asyncio
    async def test_api_error_no_db_hit_not_stopped(self) -> None:
        from exceptions import DataGoKrError

        mock_client = _make_mock_client(
            raise_exc=DataGoKrError("timeout", endpoint="15111777")
        )

        with _patch_supabase([]):  # DB도 clean
            result = await run_step_a(
                [Ingredient(name="정상원료")],
                client=mock_client,
            )

        assert result.stopped is False
        assert result.forbidden_hits == []
        assert len(result.api_errors) == 1

    # ------------------------------------------------------------------
    # 시나리오 6: 공백/대소문자 무관 매칭
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_whitespace_normalization(self) -> None:
        # DB에 "아편" 등록, 입력에 " 아편 " (앞뒤 공백)
        db_rows = [{"name_ko": "아편", "reason": "마약류관리법", "law_ref": "law-001"}]
        mock_client = _make_mock_client(items=[])

        with _patch_supabase(db_rows):
            result = await run_step_a(
                [Ingredient(name="  아편  ")],
                client=mock_client,
            )

        assert result.stopped is True
        assert len(result.forbidden_hits) == 1

    @pytest.mark.asyncio
    async def test_case_insensitive_matching(self) -> None:
        # DB에 "cannabis" 소문자 등록, 입력에 "Cannabis" 대문자
        db_rows = [{"name_ko": "cannabis", "reason": "마약류관리법", "law_ref": None}]
        mock_client = _make_mock_client(items=[])

        with _patch_supabase(db_rows):
            result = await run_step_a(
                [Ingredient(name="Cannabis")],
                client=mock_client,
            )

        assert result.stopped is True

    # ------------------------------------------------------------------
    # 시나리오 7: sub_ingredients 하위 성분 검사
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_sub_ingredients_flat_checked(self) -> None:
        # 상위 원재료는 안전, 하위에 금지원료 포함
        db_rows = [{"name_ko": "아편", "reason": "마약류관리법", "law_ref": "law-001"}]
        mock_client = _make_mock_client(items=[])

        compound = Ingredient(
            name="복합원료",
            sub_ingredients=[Ingredient(name="아편")],
        )

        with _patch_supabase(db_rows):
            result = await run_step_a([compound], client=mock_client)

        assert result.stopped is True
        assert any(h.ingredient_name == "아편" for h in result.forbidden_hits)

    @pytest.mark.asyncio
    async def test_sub_ingredients_two_level(self) -> None:
        # 2단계 중첩
        db_rows = [{"name_ko": "대마초", "reason": "마약류관리법", "law_ref": "law-002"}]
        mock_client = _make_mock_client(items=[])

        deep = Ingredient(
            name="최상위",
            sub_ingredients=[
                Ingredient(
                    name="중간",
                    sub_ingredients=[Ingredient(name="대마초")],
                )
            ],
        )

        with _patch_supabase(db_rows):
            result = await run_step_a([deep], client=mock_client)

        assert result.stopped is True
        assert any(h.ingredient_name == "대마초" for h in result.forbidden_hits)

    # ------------------------------------------------------------------
    # 시나리오 8: 금지 원료 없음 → stopped=False
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_no_forbidden_ingredients(self) -> None:
        mock_client = _make_mock_client(items=[])

        with _patch_supabase([]):
            result = await run_step_a(
                [Ingredient(name="대두"), Ingredient(name="밀")],
                client=mock_client,
            )

        assert result.stopped is False
        assert result.forbidden_hits == []
        assert result.api_errors == []

    # ------------------------------------------------------------------
    # 시나리오 9: 빈 ingredients → 즉시 반환
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_empty_ingredients(self) -> None:
        with _patch_supabase([]):
            result = await run_step_a([], client=None)

        # API·DB 호출 없이 즉시 반환
        assert result.stopped is False
        assert result.forbidden_hits == []

    # ------------------------------------------------------------------
    # 시나리오 10: law_refs 수집
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_law_refs_collected(self) -> None:
        db_rows = [
            {"name_ko": "아편", "reason": "마약류관리법", "law_ref": "law-001"},
            {"name_ko": "대마초", "reason": "마약류관리법", "law_ref": "law-002"},
        ]
        mock_client = _make_mock_client(items=[])

        with _patch_supabase(db_rows):
            result = await run_step_a(
                [Ingredient(name="아편"), Ingredient(name="대마초")],
                client=mock_client,
            )

        assert "law-001" in result.law_refs
        assert "law-002" in result.law_refs
        assert result.stopped is True

    # ------------------------------------------------------------------
    # Day 0 시그니처 유지 확인
    # ------------------------------------------------------------------
    def test_signature_positional_ingredients(self) -> None:
        """run_step_a의 첫 번째 인자가 ingredients 임을 확인."""
        import inspect
        sig = inspect.signature(run_step_a)
        params = list(sig.parameters.keys())
        assert params[0] == "ingredients"

    def test_signature_client_keyword_only(self) -> None:
        """client 파라미터가 keyword-only 이고 default=None 임을 확인."""
        import inspect
        sig = inspect.signature(run_step_a)
        client_param = sig.parameters["client"]
        assert client_param.kind == inspect.Parameter.KEYWORD_ONLY
        assert client_param.default is None

    # ------------------------------------------------------------------
    # StepAResult 타입 검증
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_result_type(self) -> None:
        mock_client = _make_mock_client(items=[])
        with _patch_supabase([]):
            result = await run_step_a(
                [Ingredient(name="대두")],
                client=mock_client,
            )
        assert isinstance(result, StepAResult)
        assert isinstance(result.forbidden_hits, list)
        assert isinstance(result.stopped, bool)
        assert isinstance(result.law_refs, list)
        assert isinstance(result.api_errors, list)

    # ------------------------------------------------------------------
    # 여러 원재료 중 일부만 금지 — 다건 처리
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_multiple_ingredients_one_forbidden(self) -> None:
        db_rows = [{"name_ko": "아편", "reason": "마약류관리법", "law_ref": "law-001"}]
        mock_client = _make_mock_client(items=[])

        with _patch_supabase(db_rows):
            result = await run_step_a(
                [Ingredient(name="대두"), Ingredient(name="아편"), Ingredient(name="밀")],
                client=mock_client,
            )

        assert result.stopped is True
        assert len(result.forbidden_hits) == 1
        assert result.forbidden_hits[0].ingredient_name == "아편"

    # ------------------------------------------------------------------
    # API 응답에 여러 건 — 하나라도 불가면 hit
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_api_multiple_items_one_forbidden(self) -> None:
        api_items = [
            {
                "INGD_SN": "11111",
                "INGD_NM": "원료X",
                "EDIBLE_INFO": "가능",
                "EDIBLE_N": None,
            },
            {
                "INGD_SN": "22222",
                "INGD_NM": "원료X",
                "EDIBLE_INFO": "불가",
                "EDIBLE_N": None,
            },
        ]
        mock_client = _make_mock_client(items=api_items)

        with _patch_supabase([]):
            result = await run_step_a(
                [Ingredient(name="원료X")],
                client=mock_client,
            )

        assert result.stopped is True
