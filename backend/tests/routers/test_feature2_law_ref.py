"""F2 router — P7 law_ref 환각 차단 / RAG threshold 단위 테스트.

검증:
    - _filter_rag_chunks: score < threshold 제거
    - _validate_law_ref: whitelist / RAG-mention / 환각 시 빈 문자열
    - _F2_LAW_WHITELIST 규모 sanity

실행:
    cd backend
    pytest tests/routers/test_feature2_law_ref.py -v
"""

from __future__ import annotations

import pytest

from routers.feature2 import (
    _F2_LAW_WHITELIST,
    _RAG_MIN_SCORE,
    _filter_rag_chunks,
    _validate_law_ref,
)


# ────────────────────────────────────────────────────────────
# _filter_rag_chunks
# ────────────────────────────────────────────────────────────


class TestFilterRagChunks:
    def test_threshold_applied(self):
        chunks = [
            {"text": "a", "score": 0.10},
            {"text": "b", "score": 0.40},
            {"text": "c", "score": 0.35},
            {"text": "d", "score": 0.20},
        ]
        kept = _filter_rag_chunks(chunks)
        texts = [c["text"] for c in kept]
        assert texts == ["b", "c"]

    def test_missing_score_treated_as_zero(self):
        chunks = [{"text": "x"}]
        assert _filter_rag_chunks(chunks) == []

    def test_custom_threshold(self):
        chunks = [{"text": "a", "score": 0.4}, {"text": "b", "score": 0.6}]
        kept = _filter_rag_chunks(chunks, min_score=0.5)
        assert [c["text"] for c in kept] == ["b"]

    def test_default_threshold_is_exported_constant(self):
        # 문서화된 값과 구현이 일치해야 한다
        assert _RAG_MIN_SCORE == 0.35


# ────────────────────────────────────────────────────────────
# _validate_law_ref
# ────────────────────────────────────────────────────────────


class TestValidateLawRef:
    def test_whitelist_law_passes(self):
        out = _validate_law_ref("식품위생법 제7조", [])
        assert out == "식품위생법 제7조"

    def test_food_code_law_passes(self):
        out = _validate_law_ref("식품의 기준 및 규격 제5장 2-1", [])
        assert out.startswith("식품의 기준 및 규격")

    def test_alcohol_law_passes(self):
        out = _validate_law_ref("주세법 제5조 제1항", [])
        assert "주세법" in out

    def test_empty_input_returns_empty(self):
        assert _validate_law_ref("", []) == ""
        assert _validate_law_ref(None or "", []) == ""

    def test_hallucinated_law_returns_empty(self):
        """화이트리스트/RAG 에 없는 법령 → 빈 문자열."""
        out = _validate_law_ref("한국수입식품안전법 시행규칙 제99조", [])
        assert out == ""

    def test_hallucinated_law_with_partial_hit_still_rejected(self):
        """부분 단어만 겹치는 경우도 거부 — 완전 일치 법령명이 있어야 함."""
        # "식품" 만으로는 통과 안 됨
        out = _validate_law_ref("식품 임시고시 2020-123호", [])
        assert out == ""

    def test_rag_mentioned_law_passes(self):
        """RAG 원문에 「법령명」 표기로 등장하면 통과."""
        rag_chunks = [
            {"text": "「수산물품질관리법」 제5조에 의거하여 ..."}
        ]
        out = _validate_law_ref("수산물품질관리법 제5조", rag_chunks)
        assert out == "수산물품질관리법 제5조"

    def test_rag_mentioned_but_different_law_rejected(self):
        rag_chunks = [{"text": "「수산물품질관리법」 제5조 ..."}]
        out = _validate_law_ref("농수산물유통법 제99조", rag_chunks)
        assert out == ""


# ────────────────────────────────────────────────────────────
# whitelist sanity
# ────────────────────────────────────────────────────────────


class TestWhitelist:
    def test_whitelist_contains_core_laws(self):
        required = {
            "식품위생법",
            "주세법",
            "식품의 기준 및 규격",
            "수입식품안전관리 특별법",
        }
        assert required <= _F2_LAW_WHITELIST

    def test_whitelist_is_frozen(self):
        with pytest.raises(AttributeError):
            _F2_LAW_WHITELIST.add("dummy")  # type: ignore[attr-defined]
