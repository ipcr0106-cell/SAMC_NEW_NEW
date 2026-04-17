"""F1 Phase 4-B — run_feature1_with_rag 통합 분기 테스트 (DB/네트워크 차단).

대상:
    services.feature1.run_feature1_with_rag
    services.feature1._derive_exact_verdict

원칙:
    - 실제 Pinecone/OpenAI 호출 금지 (f1_rag_judge.run 을 monkeypatch).
    - 실제 DB 조회 금지 (run_feature1 호출을 monkeypatch).
    - conflict_status 5개 분기 모두 커버.
    - pytest-asyncio 미사용 환경 → asyncio.run() 패턴.
"""

from __future__ import annotations

import asyncio

import pytest

from models.f1_law_citation import LawCitation, RagJudgement
from models.judgment import (AggregationResult, Feature1Output, ForbiddenHit,
                             Ingredient)
from services import feature1 as feature1_module
from services.feature1 import _derive_exact_verdict, run_feature1_with_rag


# ============================================================
# 헬퍼
# ============================================================


def _mk_output(
    forbidden: list[ForbiddenHit] | None = None,
    agg: AggregationResult | None = None,
    import_possible: bool = True,
) -> Feature1Output:
    return Feature1Output(
        import_possible=import_possible,
        verdict="test",
        aggregation=agg,
        forbidden_hits=forbidden or [],
    )


def _mk_agg(permitted=0, restricted=0, prohibited=0, unidentified=0) -> AggregationResult:
    return AggregationResult(
        total=permitted + restricted + prohibited + unidentified,
        permitted=permitted,
        restricted=restricted,
        prohibited=prohibited,
        unidentified=unidentified,
        results=[],
    )


def _install_run_feature1(
    monkeypatch: pytest.MonkeyPatch, result: Feature1Output
) -> None:
    """run_feature1 호출을 고정 Feature1Output 으로 치환."""
    monkeypatch.setattr(feature1_module, "run_feature1", lambda *_, **__: result)


def _install_rag(
    monkeypatch: pytest.MonkeyPatch, judgement: RagJudgement
) -> None:
    """f1_rag_judge.run 코루틴을 고정 값으로 치환."""

    async def _fake_run(_payload):
        return judgement

    monkeypatch.setattr(feature1_module.f1_rag_judge, "run", _fake_run)


# ============================================================
# _derive_exact_verdict
# ============================================================


class TestDeriveExactVerdict:
    def test_forbidden_first(self):
        out = _mk_output(
            forbidden=[ForbiddenHit(name_ko="대마초", category="drug")],
            agg=_mk_agg(permitted=5),
        )
        assert _derive_exact_verdict(out) == "prohibited"

    def test_no_aggregation_unidentified(self):
        out = _mk_output(agg=None)
        assert _derive_exact_verdict(out) == "unidentified"

    def test_prohibited_in_agg(self):
        out = _mk_output(agg=_mk_agg(permitted=3, prohibited=1))
        assert _derive_exact_verdict(out) == "prohibited"

    def test_unidentified_dominant_when_no_permitted(self):
        out = _mk_output(agg=_mk_agg(unidentified=2, permitted=0))
        assert _derive_exact_verdict(out) == "unidentified"

    def test_restricted(self):
        out = _mk_output(agg=_mk_agg(permitted=2, restricted=1))
        assert _derive_exact_verdict(out) == "restricted"

    def test_permitted(self):
        out = _mk_output(agg=_mk_agg(permitted=3))
        assert _derive_exact_verdict(out) == "permitted"

    def test_empty_agg(self):
        out = _mk_output(agg=_mk_agg())
        assert _derive_exact_verdict(out) == "unidentified"


# ============================================================
# run_feature1_with_rag — 분기별
# ============================================================


def test_step0_forbidden_skips_rag(monkeypatch):
    """Step 0 적중 → RAG 미호출, conflict_status=rag_skipped."""
    called = {"n": 0}

    async def _should_not_call(_payload):
        called["n"] += 1
        return RagJudgement(
            rag_verdict="permitted", rag_reasoning="", law_citations=[]
        )

    out = _mk_output(
        forbidden=[ForbiddenHit(name_ko="대마초", category="drug")],
        import_possible=False,
    )
    _install_run_feature1(monkeypatch, out)
    monkeypatch.setattr(feature1_module.f1_rag_judge, "run", _should_not_call)

    result_out, rag, status = asyncio.run(
        run_feature1_with_rag(ingredients=[Ingredient(name="대마초")])
    )
    assert result_out is out
    assert rag is None
    assert status == "rag_skipped"
    assert called["n"] == 0


def test_rag_error_returns_unavailable(monkeypatch):
    _install_run_feature1(monkeypatch, _mk_output(agg=_mk_agg(permitted=1)))
    _install_rag(
        monkeypatch,
        RagJudgement(rag_verdict="error", rag_reasoning="boom", law_citations=[]),
    )
    _, rag, status = asyncio.run(
        run_feature1_with_rag(ingredients=[Ingredient(name="설탕")])
    )
    assert status == "rag_unavailable"
    assert rag is not None and rag.rag_verdict == "error"


def test_agreed(monkeypatch):
    _install_run_feature1(monkeypatch, _mk_output(agg=_mk_agg(permitted=1)))
    _install_rag(
        monkeypatch,
        RagJudgement(rag_verdict="permitted", rag_reasoning="ok", law_citations=[]),
    )
    _, _, status = asyncio.run(
        run_feature1_with_rag(ingredients=[Ingredient(name="설탕")])
    )
    assert status == "agreed"


def test_rag_supplemented(monkeypatch):
    _install_run_feature1(monkeypatch, _mk_output(agg=_mk_agg(unidentified=1)))
    _install_rag(
        monkeypatch,
        RagJudgement(
            rag_verdict="permitted",
            rag_reasoning="법령에 허용 명시",
            law_citations=[
                LawCitation(
                    chunk_id="c1",
                    namespace="food_code_text",
                    regulation_id=None,
                    section_path=None,
                    text="...",
                    score=0.8,
                )
            ],
        ),
    )
    _, rag, status = asyncio.run(
        run_feature1_with_rag(ingredients=[Ingredient(name="무명원료")])
    )
    assert status == "rag_supplemented"
    assert rag is not None and len(rag.law_citations) == 1


def test_conflict(monkeypatch):
    _install_run_feature1(monkeypatch, _mk_output(agg=_mk_agg(permitted=1)))
    _install_rag(
        monkeypatch,
        RagJudgement(
            rag_verdict="prohibited", rag_reasoning="...", law_citations=[]
        ),
    )
    _, _, status = asyncio.run(
        run_feature1_with_rag(ingredients=[Ingredient(name="설탕")])
    )
    assert status == "conflict"
