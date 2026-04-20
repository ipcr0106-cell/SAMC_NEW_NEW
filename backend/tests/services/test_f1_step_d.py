"""W2-D Step D 단위 테스트 (2026-04-20 P7 리라이트).

P7 관련도 가드 검증:
    - stopword/minlen 필터
    - 키워드 가중치 (food_type×3, ingredient_name×2, 기본×1)
    - namespace 라우팅 (food_type 힌트, ingredient_codes, profile_flags)
    - min_score 컷 (0.2 미만 제거)
    - length DESC tie-break (의미 있는 본문 우선)
    - 통합 top_k 정렬

P7 이전 Pinecone mock 테스트는 P6 의 asyncpg 전환 이후 이미 broken 상태였음 —
이 파일로 전면 재작성.

실행:
    cd backend
    pytest tests/services/test_f1_step_d.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from models.f1_types import ForbiddenHit, QueryContext, StepDResult
from services.f1_step_d import (
    _MIN_SCORE,
    _NAMESPACES,
    _extract_keywords,
    _is_valid_keyword,
    _select_namespaces,
    build_query,
    run_step_d,
)

# ────────────────────────────────────────────────────────────
# build_query (P6 에서 유지된 동작 — regression 방지)
# ────────────────────────────────────────────────────────────


class TestBuildQuery:
    def test_empty_context_returns_default(self):
        assert build_query(QueryContext()) == "수입식품 일반"

    def test_food_type_only(self):
        assert "식품유형 음료류" in build_query(QueryContext(food_type="음료류"))

    def test_all_fields_combined(self):
        ctx = QueryContext(
            food_type="빵류",
            forbidden_hits=[
                ForbiddenHit(
                    ingredient_name="마황",
                    matched_name="마황",
                    source="db",
                    reason="금지",
                    law_ref=None,
                )
            ],
            restricted_ingredients=["과라나"],
            failed_standards=["수분 함량 초과"],
        )
        q = build_query(ctx)
        assert " / " in q
        assert "빵류" in q and "마황" in q and "과라나" in q


# ────────────────────────────────────────────────────────────
# _is_valid_keyword — stopword / 최소길이
# ────────────────────────────────────────────────────────────


class TestIsValidKeyword:
    @pytest.mark.parametrize(
        "kw",
        ["제품", "식품", "원료", "물", "염", "분말", "혼합물", "기타", "일반"],
    )
    def test_stopwords_rejected(self, kw):
        assert _is_valid_keyword(kw) is False

    def test_short_hangul_rejected(self):
        assert _is_valid_keyword("가") is False

    def test_hangul_2char_accepted(self):
        assert _is_valid_keyword("밀가") is True

    def test_latin_2char_rejected(self):
        assert _is_valid_keyword("AB") is False

    def test_latin_3char_accepted(self):
        assert _is_valid_keyword("ABC") is True

    def test_whitespace_stripped(self):
        assert _is_valid_keyword("  빵류  ") is True


# ────────────────────────────────────────────────────────────
# _extract_keywords — 가중치 + stopword 제거 + dedup
# ────────────────────────────────────────────────────────────


class TestExtractKeywords:
    def test_food_type_weight_is_3(self):
        ctx = QueryContext(food_type="빵류")
        kws = dict(_extract_keywords(ctx))
        assert kws["빵류"] == 3

    def test_ingredient_name_weight_is_2(self):
        ctx = QueryContext(
            food_type="빵류",
            ingredient_names=["밀가루"],
        )
        kws = dict(_extract_keywords(ctx))
        assert kws["밀가루"] == 2

    def test_restricted_and_failed_default_weight_1(self):
        ctx = QueryContext(
            restricted_ingredients=["카페인"],
            failed_standards=["소르빈산:보존료"],
        )
        kws = dict(_extract_keywords(ctx))
        assert kws["카페인"] == 1
        assert kws["소르빈산"] == 1
        assert kws["보존료"] == 1

    def test_stopwords_removed_from_extraction(self):
        ctx = QueryContext(
            ingredient_names=["제품", "식품", "밀가루"],
        )
        kws = dict(_extract_keywords(ctx))
        assert "제품" not in kws
        assert "식품" not in kws
        assert "밀가루" in kws

    def test_duplicate_keyword_takes_max_weight(self):
        # 같은 이름이 food_type 과 ingredient_name 양쪽에 있으면 max(3,2)=3
        ctx = QueryContext(
            food_type="밀가루",
            ingredient_names=["밀가루"],
        )
        kws = dict(_extract_keywords(ctx))
        assert kws["밀가루"] == 3

    def test_forbidden_hits_contribute_keywords(self):
        ctx = QueryContext(
            forbidden_hits=[
                ForbiddenHit(
                    ingredient_name="마황",
                    matched_name="마황",
                    source="db",
                    reason="금지",
                    law_ref=None,
                )
            ],
        )
        kws = dict(_extract_keywords(ctx))
        assert "마황" in kws


# ────────────────────────────────────────────────────────────
# _select_namespaces — routing
# ────────────────────────────────────────────────────────────


class TestSelectNamespaces:
    def test_default_is_food_code_only(self):
        ns = _select_namespaces(QueryContext(food_type="빵류"))
        assert ns == ["food_code_text"]

    def test_ingredient_codes_adds_additive(self):
        ns = _select_namespaces(QueryContext(
            food_type="빵류",
            ingredient_codes=["ABC123"],
        ))
        assert "additive_code_text" in ns
        assert "food_code_text" in ns

    def test_health_food_type_adds_health_food_ns(self):
        ns = _select_namespaces(QueryContext(food_type="건강기능식품"))
        assert "health_food_text" in ns

    def test_functional_keyword_adds_functional_labeling(self):
        ns = _select_namespaces(QueryContext(food_type="기능성표시 일반식품"))
        assert "functional_labeling" in ns

    def test_profile_flag_opt_in(self):
        ns = _select_namespaces(QueryContext(
            food_type="빵류",
            profile_flags=["temporary_standard"],
        ))
        assert "temporary_standard" in ns

    def test_temporary_standard_not_included_by_default(self):
        ns = _select_namespaces(QueryContext(food_type="빵류"))
        assert "temporary_standard" not in ns

    def test_all_selected_are_valid_namespaces(self):
        ns = _select_namespaces(QueryContext(
            food_type="건강기능식품 기능성표시",
            ingredient_codes=["X"],
            profile_flags=["temporary_standard"],
        ))
        assert set(ns) <= set(_NAMESPACES)
        # 중복 없음
        assert len(ns) == len(set(ns))


# ────────────────────────────────────────────────────────────
# run_step_d — _search mock 으로 score 계산/threshold/정렬 검증
# ────────────────────────────────────────────────────────────


def _mock_row(ns: str, m: int, text_len: int, chunk_id: str = "c1") -> dict:
    """_search 가 반환하는 dict 형태 모사."""
    return {
        "namespace": ns,
        "law_name": "식품의 기준 및 규격",
        "chunk_id": chunk_id,
        "article_label": "제1조",
        "text": "가" * text_len,
        "m": m,
    }


class TestRunStepD:
    @pytest.mark.asyncio
    async def test_empty_keywords_returns_empty(self):
        """키워드가 모두 stopword/짧아서 제거되면 citations=[]."""
        with patch("services.f1_step_d._search", new=AsyncMock(return_value=[])) as mock_s:
            result = await run_step_d(QueryContext(food_type="물"), top_k=5)
        assert isinstance(result, StepDResult)
        assert result.citations == []
        # 키워드 0개 → _search 는 호출되지만 빈 리스트 반환
        mock_s.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_db_failure_returns_empty(self):
        with patch("services.f1_step_d._search", new=AsyncMock(side_effect=RuntimeError("db down"))):
            result = await run_step_d(QueryContext(food_type="빵류"), top_k=5)
        assert result.citations == []

    @pytest.mark.asyncio
    async def test_min_score_cut(self):
        """min_score=0.2 미만 row 는 제거된다."""
        # food_type=빵류 (weight=3) 만 있으면 total_weight=3.
        # m=1 → score=1/3≈0.33 ≥ 0.2 통과
        # m=0 은 SQL WHERE 에서 제외되지만 혹시 row 로 오더라도 컷해야 한다.
        rows = [
            _mock_row("food_code_text", m=3, text_len=200, chunk_id="hi"),   # 1.00
            _mock_row("food_code_text", m=1, text_len=150, chunk_id="mid"),  # 0.33
            _mock_row("food_code_text", m=0, text_len=100, chunk_id="lo"),   # 0.00 < 0.2
        ]
        with patch("services.f1_step_d._search", new=AsyncMock(return_value=rows)):
            result = await run_step_d(QueryContext(food_type="빵류"), top_k=5)

        ids = [c.chunk_id for c in result.citations]
        assert "hi" in ids
        assert "mid" in ids
        assert "lo" not in ids, f"score<{_MIN_SCORE} row 가 남아있음"

    @pytest.mark.asyncio
    async def test_length_desc_tiebreak(self):
        """같은 score 면 본문이 긴 쪽이 먼저 온다 (P7)."""
        rows = [
            _mock_row("food_code_text", m=3, text_len=100, chunk_id="short"),
            _mock_row("food_code_text", m=3, text_len=500, chunk_id="long"),
        ]
        with patch("services.f1_step_d._search", new=AsyncMock(return_value=rows)):
            result = await run_step_d(QueryContext(food_type="빵류"), top_k=5)

        assert [c.chunk_id for c in result.citations] == ["long", "short"]

    @pytest.mark.asyncio
    async def test_score_computed_against_total_weight(self):
        """가중 합 / total_weight 로 score 가 [0,1] 범위."""
        # food_type=빵류 (3) + ingredient=밀가루 (2) → total_weight=5
        # 한 rule (m=5) 매칭 → score=1.0
        ctx = QueryContext(food_type="빵류", ingredient_names=["밀가루"])
        rows = [_mock_row("food_code_text", m=5, text_len=300)]
        with patch("services.f1_step_d._search", new=AsyncMock(return_value=rows)):
            result = await run_step_d(ctx, top_k=5)

        assert len(result.citations) == 1
        assert result.citations[0].score == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_top_k_limits_after_merge(self):
        """여러 namespace row 들을 merge 한 뒤 top_k 컷."""
        rows = [
            _mock_row("food_code_text",     m=3, text_len=400, chunk_id="a"),
            _mock_row("additive_code_text", m=2, text_len=300, chunk_id="b"),
            _mock_row("food_code_text",     m=1, text_len=200, chunk_id="c"),
        ]
        ctx = QueryContext(food_type="빵류", ingredient_codes=["X1"])
        with patch("services.f1_step_d._search", new=AsyncMock(return_value=rows)):
            result = await run_step_d(ctx, top_k=2)

        assert len(result.citations) == 2
        # score DESC 정렬
        scores = [c.score for c in result.citations]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_namespace_routing_passed_to_search(self):
        """food_type='빵류' 면 _search 에 food_code_text 만 전달."""
        captured: dict = {}

        async def fake_search(kw_weights, namespaces, top_k):
            captured["namespaces"] = namespaces
            return []

        with patch("services.f1_step_d._search", new=fake_search):
            await run_step_d(QueryContext(food_type="빵류"), top_k=5)

        assert captured["namespaces"] == ["food_code_text"]
