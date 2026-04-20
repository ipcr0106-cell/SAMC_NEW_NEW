"""W2-D Step D 단위 테스트.

목표:
    - build_query: 컨텍스트 조합별 쿼리 합성 검증
    - 5 namespace 병렬 검색 → 상위 top_k merge
    - Pinecone 장애 → citations=[], 파이프라인 계속
    - 빈 결과 → citations=[]
    - 임베딩 장애 → citations=[], 파이프라인 계속
    - RAG 판정 주도 로직 없음 확인 (rag_verdict / rag_reasoning 필드 미생성)
    - LawCitation 정규화 (chunk_id / law_name / article_no / text / score / namespace)
    - functional_labeling namespace 쿼리 경로 유지 (14번 §11-3 A')

실행:
    cd backend
    pytest tests/services/test_f1_step_d.py -v
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.f1_types import ForbiddenHit, LawCitation, QueryContext, StepDResult
from services.f1_step_d import _NAMESPACES, _normalize_hit, build_query, run_step_d

# ────────────────────────────────────────────────────────────
# 픽스처 로더
# ────────────────────────────────────────────────────────────

_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "f1_step_d"


def _load_fixture(name: str) -> Any:
    return json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))


# ────────────────────────────────────────────────────────────
# build_query 테스트
# ────────────────────────────────────────────────────────────


class TestBuildQuery:
    """04번 §4 쿼리 합성 검증."""

    def test_empty_context_returns_default(self):
        """빈 컨텍스트 → '수입식품 일반'."""
        fixture = _load_fixture("empty_context.json")
        ctx = QueryContext(**fixture["query_context"])
        result = build_query(ctx)
        assert result == fixture["expected_query"]

    def test_food_type_only(self):
        """food_type 만 있을 때 포함 여부."""
        ctx = QueryContext(food_type="음료류")
        result = build_query(ctx)
        assert "식품유형 음료류" in result

    def test_forbidden_hits_included(self):
        """forbidden_hits → '수입 금지 원료' 포함."""
        fixture = _load_fixture("forbidden_hits_context.json")
        ctx = QueryContext(**fixture["query_context"])
        result = build_query(ctx)
        for expected in fixture["expected_query_contains"]:
            assert expected in result, f"'{expected}' not in query: {result!r}"

    def test_restricted_ingredients_included(self):
        """restricted_ingredients 포함."""
        ctx = QueryContext(restricted_ingredients=["카페인", "은행"])
        result = build_query(ctx)
        assert "사용 제한 원료" in result
        assert "카페인" in result
        assert "은행" in result

    def test_failed_standards_included(self):
        """failed_standards 포함."""
        ctx = QueryContext(failed_standards=["소르빈산 기준 초과"])
        result = build_query(ctx)
        assert "기준규격 초과" in result
        assert "소르빈산 기준 초과" in result

    def test_all_fields_combined(self):
        """모든 필드 조합 — ' / ' 구분자."""
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
        result = build_query(ctx)
        assert " / " in result
        assert "식품유형 빵류" in result
        assert "마황" in result
        assert "과라나" in result
        assert "수분 함량 초과" in result


# ────────────────────────────────────────────────────────────
# _normalize_hit 테스트
# ────────────────────────────────────────────────────────────


class TestNormalizeHit:
    """LawCitation 정규화 단위 검증."""

    def test_normal_hit(self):
        """정상 hit → LawCitation 필드 매핑."""
        hits = _load_fixture("multi_namespace_hits.json")
        hit = hits[0]  # additive_code_text
        result = _normalize_hit(hit, "additive_code_text")
        assert result is not None
        assert result.chunk_id == "additive_code_001"
        assert result.namespace == "additive_code_text"
        assert result.score == pytest.approx(0.92)
        assert result.article_no == "제2조/제1항"
        assert "소브산" in result.text
        assert result.law_name == "식품첨가물의 기준 및 규격"

    def test_functional_labeling_hit(self):
        """functional_labeling namespace → 기능성표시 법령명 매핑."""
        hits = _load_fixture("multi_namespace_hits.json")
        hit = next(h for h in hits if h["namespace"] == "functional_labeling")
        result = _normalize_hit(hit, "functional_labeling")
        assert result is not None
        assert "기능성 표시" in result.law_name
        assert result.namespace == "functional_labeling"

    def test_missing_id_returns_none(self):
        """chunk_id 없으면 None 반환."""
        result = _normalize_hit({"score": 0.9, "text": "test"}, "food_code_text")
        assert result is None

    def test_text_preserved_verbatim(self):
        """text 원문 그대로 (편집 없음)."""
        original_text = "원문 그대로 보존해야 함 — 편집 금지"
        hit = {"id": "test_001", "score": 0.85, "text": original_text}
        result = _normalize_hit(hit, "food_code_text")
        assert result is not None
        assert result.text == original_text


# ────────────────────────────────────────────────────────────
# run_step_d 통합 단위테스트 (Pinecone + OpenAI mock)
# ────────────────────────────────────────────────────────────


def _make_fake_vector() -> list[float]:
    return [0.1] * 1536


class TestRunStepD:
    """run_step_d 비동기 단위테스트."""

    @pytest.mark.asyncio
    async def test_5_namespace_parallel_search_merge(self):
        """5 namespace 병렬 검색 → score 상위 top_k=5 merge."""
        hits = _load_fixture("multi_namespace_hits.json")

        with (
            patch("services.f1_step_d.f1_openai_client") as mock_oai,
            patch("services.f1_step_d.f1_pinecone_client") as mock_pc,
        ):
            mock_oai.embed.return_value = [_make_fake_vector()]
            mock_pc.search_multi = AsyncMock(return_value=hits)

            ctx = QueryContext(food_type="빵류")
            result = await run_step_d(ctx, top_k=5)

        assert isinstance(result, StepDResult)
        assert len(result.citations) == 5
        # score 내림차순 확인
        scores = [c.score for c in result.citations]
        assert scores == sorted(scores, reverse=True)
        # 모든 5 namespace 포함 확인
        namespaces = {c.namespace for c in result.citations}
        assert namespaces == {
            "additive_code_text",
            "food_code_text",
            "health_food_text",
            "temporary_standard",
            "functional_labeling",
        }

    @pytest.mark.asyncio
    async def test_functional_labeling_namespace_included(self):
        """functional_labeling 쿼리 경로 유지 (14번 §11-3 A')."""
        assert "functional_labeling" in _NAMESPACES

        hits = _load_fixture("multi_namespace_hits.json")
        with (
            patch("services.f1_step_d.f1_openai_client") as mock_oai,
            patch("services.f1_step_d.f1_pinecone_client") as mock_pc,
        ):
            mock_oai.embed.return_value = [_make_fake_vector()]
            mock_pc.search_multi = AsyncMock(return_value=hits)

            ctx = QueryContext(food_type="건강기능식품")
            result = await run_step_d(ctx, top_k=5)

        func_citations = [c for c in result.citations if c.namespace == "functional_labeling"]
        assert len(func_citations) >= 1

    @pytest.mark.asyncio
    async def test_pinecone_failure_returns_empty_citations(self):
        """Pinecone 장애 → citations=[], 예외 전파 없음 (파이프라인 계속)."""
        with (
            patch("services.f1_step_d.f1_openai_client") as mock_oai,
            patch("services.f1_step_d.f1_pinecone_client") as mock_pc,
        ):
            mock_oai.embed.return_value = [_make_fake_vector()]
            mock_pc.search_multi = AsyncMock(side_effect=RuntimeError("Pinecone 연결 실패"))

            ctx = QueryContext(food_type="음료류")
            result = await run_step_d(ctx, top_k=5)

        assert isinstance(result, StepDResult)
        assert result.citations == []

    @pytest.mark.asyncio
    async def test_embedding_failure_returns_empty_citations(self):
        """임베딩 실패 → citations=[], 예외 전파 없음."""
        with (
            patch("services.f1_step_d.f1_openai_client") as mock_oai,
        ):
            mock_oai.embed.side_effect = RuntimeError("OpenAI API 오류")

            ctx = QueryContext(food_type="과자류")
            result = await run_step_d(ctx, top_k=5)

        assert isinstance(result, StepDResult)
        assert result.citations == []

    @pytest.mark.asyncio
    async def test_empty_pinecone_results(self):
        """Pinecone 결과 0건 → citations=[]."""
        with (
            patch("services.f1_step_d.f1_openai_client") as mock_oai,
            patch("services.f1_step_d.f1_pinecone_client") as mock_pc,
        ):
            mock_oai.embed.return_value = [_make_fake_vector()]
            mock_pc.search_multi = AsyncMock(return_value=[])

            ctx = QueryContext()
            result = await run_step_d(ctx, top_k=5)

        assert isinstance(result, StepDResult)
        assert result.citations == []

    @pytest.mark.asyncio
    async def test_empty_context_uses_default_query(self):
        """빈 컨텍스트 → '수입식품 일반' 쿼리 사용."""
        captured_embed_args: list[list[str]] = []

        def fake_embed(texts: list[str]) -> list[list[float]]:
            captured_embed_args.append(texts)
            return [_make_fake_vector()]

        with (
            patch("services.f1_step_d.f1_openai_client") as mock_oai,
            patch("services.f1_step_d.f1_pinecone_client") as mock_pc,
        ):
            mock_oai.embed.side_effect = fake_embed
            mock_pc.search_multi = AsyncMock(return_value=[])

            ctx = QueryContext()
            await run_step_d(ctx, top_k=5)

        assert captured_embed_args
        assert captured_embed_args[0][0] == "수입식품 일반"

    @pytest.mark.asyncio
    async def test_top_k_limits_citations(self):
        """top_k=3 → 최대 3건 반환."""
        hits = _load_fixture("multi_namespace_hits.json")  # 5건

        with (
            patch("services.f1_step_d.f1_openai_client") as mock_oai,
            patch("services.f1_step_d.f1_pinecone_client") as mock_pc,
        ):
            mock_oai.embed.return_value = [_make_fake_vector()]
            mock_pc.search_multi = AsyncMock(return_value=hits)

            ctx = QueryContext(food_type="유제품")
            result = await run_step_d(ctx, top_k=3)

        assert len(result.citations) <= 3

    @pytest.mark.asyncio
    async def test_no_rag_verdict_in_result(self):
        """StepDResult에 rag_verdict / rag_reasoning 필드 없음 확인."""
        with (
            patch("services.f1_step_d.f1_openai_client") as mock_oai,
            patch("services.f1_step_d.f1_pinecone_client") as mock_pc,
        ):
            mock_oai.embed.return_value = [_make_fake_vector()]
            mock_pc.search_multi = AsyncMock(return_value=[])

            ctx = QueryContext(food_type="과자류")
            result = await run_step_d(ctx, top_k=5)

        assert not hasattr(result, "rag_verdict")
        assert not hasattr(result, "rag_reasoning")
        assert not hasattr(result, "conflict_status")

    @pytest.mark.asyncio
    async def test_search_multi_called_with_all_5_namespaces(self):
        """search_multi 호출 시 5개 namespace 모두 전달 확인."""
        with (
            patch("services.f1_step_d.f1_openai_client") as mock_oai,
            patch("services.f1_step_d.f1_pinecone_client") as mock_pc,
        ):
            mock_oai.embed.return_value = [_make_fake_vector()]
            mock_pc.search_multi = AsyncMock(return_value=[])

            await run_step_d(QueryContext(food_type="빵류"), top_k=5)

        call_kwargs = mock_pc.search_multi.call_args
        called_namespaces = call_kwargs[1].get("namespaces") or call_kwargs[0][1]
        assert set(called_namespaces) == {
            "additive_code_text",
            "food_code_text",
            "health_food_text",
            "temporary_standard",
            "functional_labeling",
        }

    @pytest.mark.asyncio
    async def test_law_citation_fields_complete(self):
        """반환 LawCitation 필드 완결성 검증."""
        hits = _load_fixture("multi_namespace_hits.json")[:1]

        with (
            patch("services.f1_step_d.f1_openai_client") as mock_oai,
            patch("services.f1_step_d.f1_pinecone_client") as mock_pc,
        ):
            mock_oai.embed.return_value = [_make_fake_vector()]
            mock_pc.search_multi = AsyncMock(return_value=hits)

            result = await run_step_d(QueryContext(food_type="빵류"), top_k=5)

        assert len(result.citations) == 1
        c = result.citations[0]
        assert c.chunk_id
        assert c.law_name
        assert c.text
        assert 0.0 <= c.score <= 1.0
        assert c.namespace in _NAMESPACES
