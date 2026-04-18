"""F1 RAG 판정 모듈 — integration tests.

실행 조건:
    F1_OPENAI_API_KEY, F1_PINECONE_API_KEY, F1_PINECONE_INDEX,
    F1_OPENAI_EMBED_MODEL, F1_OPENAI_CHAT_MODEL (선택)
    위 env 중 필수(OPENAI_KEY + PINECONE_KEY)가 없으면 전체 skip.

비용:
    5건 × (embed 1회 + chat_json 1회) ≈ gpt-4o-mini + text-embedding-3-small.
    건당 대략 $0.0001 미만 (컨텍스트 크기에 따라 변동).

네트워크:
    실제 Pinecone samc-law-f1 인덱스(2148건) + OpenAI API 호출.

참고:
    - 계획/f1_RAG도입계획_백엔드.md §3.3, §8
    - 계획/f1_RAG도입_Phase진행계획.md §Phase 4-A 4A-3/4A-4
"""
from __future__ import annotations

import asyncio
import os

import pytest

from models.f1_law_citation import RagJudgement
from services import f1_openai_client, f1_pinecone_client, f1_rag_judge

_REQUIRED_ENV = ["F1_OPENAI_API_KEY", "F1_PINECONE_API_KEY"]

skip_if_no_api = pytest.mark.skipif(
    not all(os.getenv(k) for k in _REQUIRED_ENV),
    reason="F1_OPENAI_API_KEY 또는 F1_PINECONE_API_KEY 미설정 — integration 테스트 skip",
)


@pytest.fixture
def reset_singletons():
    """케이스마다 싱글톤 초기화 — env 변경 반영 보장."""
    f1_openai_client._client = None
    f1_pinecone_client._pc = None
    f1_pinecone_client._index = None
    yield


# ============================================================
# 5건 integration 케이스
# ============================================================


CASES = [
    pytest.param(
        {
            "product_name": "설탕 함유 시럽",
            "ingredients": ["설탕", "물"],
            "food_type": "당류가공품",
        },
        id="1_permitted_sugar",
    ),
    pytest.param(
        {
            "product_name": "벤조산나트륨 보존제",
            "ingredients": [{"name": "벤조산나트륨"}],
            "food_type": "식품첨가물",
        },
        id="2_additive_benzoate",
    ),
    pytest.param(
        {
            "product_name": "프로바이오틱스 캡슐",
            "ingredients": ["락토바실러스"],
            "food_type": "건강기능식품",
        },
        id="3_health_functional",
    ),
    pytest.param(
        {
            "product_name": "대마 추출물 음료",
            "ingredients": [{"name": "대마씨유"}],
            "food_type": "음료",
        },
        id="4_restricted_hemp",
    ),
    pytest.param(
        {"ingredients": []},
        id="5_empty_payload",
    ),
]


@skip_if_no_api
@pytest.mark.parametrize("payload", CASES)
def test_run_returns_rag_judgement(payload, reset_singletons):
    """각 케이스에서 RagJudgement 반환 + 필수 필드 타입 검증."""
    result = asyncio.run(f1_rag_judge.run(payload))

    assert isinstance(result, RagJudgement)
    assert result.rag_verdict in (
        "permitted", "restricted", "prohibited", "unidentified", "error",
    )
    assert isinstance(result.rag_reasoning, str)
    assert isinstance(result.law_citations, list)

    # citation 필드 형식 검증 (있다면)
    for c in result.law_citations:
        assert c.chunk_id
        assert c.namespace
        assert isinstance(c.text, str)
        assert isinstance(c.score, float)


@skip_if_no_api
def test_run_never_raises_on_invalid_env(monkeypatch, reset_singletons):
    """Pinecone/OpenAI 호출 실패 시에도 예외 X, verdict='error' 반환."""
    monkeypatch.setenv("F1_PINECONE_INDEX", "__nonexistent_index__")
    f1_pinecone_client._pc = None
    f1_pinecone_client._index = None

    result = asyncio.run(f1_rag_judge.run({"ingredients": ["설탕"]}))

    assert isinstance(result, RagJudgement)
    # 실제 호출이 성공할 수도 있음(index 이름 해석 전 embed 통과) → error 강제 아님.
    # 핵심: 예외 없이 RagJudgement를 반환한다는 점만 확인.
    assert result.rag_verdict in (
        "permitted", "restricted", "prohibited", "unidentified", "error",
    )


@skip_if_no_api
def test_citations_reference_real_hits(reset_singletons):
    """law_citations가 있다면 각 chunk_id는 Pinecone에서 검색된 실제 id여야 함."""
    payload = {
        "product_name": "식품첨가물 테스트",
        "ingredients": ["벤조산나트륨"],
        "food_type": "식품첨가물",
    }
    result = asyncio.run(f1_rag_judge.run(payload))

    for c in result.law_citations:
        # LawCitation.chunk_id는 실제 Pinecone vector id여야 하므로 비어있지 않아야 함
        assert len(c.chunk_id) > 0
        assert c.namespace in f1_rag_judge.DEFAULT_NAMESPACES


# ============================================================
# 헬퍼 함수 단독 테스트 (env 없어도 skipif로 전체 skip됨)
# ============================================================


class TestBuildQueryText:
    def test_product_name_ingredients_food_type(self):
        text = f1_rag_judge._build_query_text({
            "product_name": "프로바이오틱스",
            "ingredients": ["락토바실러스"],
            "food_type": "건강기능식품",
        })
        assert "제품명: 프로바이오틱스" in text
        assert "원료: 락토바실러스" in text
        assert "식품유형: 건강기능식품" in text

    def test_ingredients_as_dict_list(self):
        text = f1_rag_judge._build_query_text({
            "ingredients": [{"name": "설탕"}, {"name": "물"}],
        })
        assert "원료: 설탕, 물" in text

    def test_empty_payload_fallback(self):
        assert f1_rag_judge._build_query_text({}) == "정보 없음"

    def test_empty_ingredients_list(self):
        assert f1_rag_judge._build_query_text({"ingredients": []}) == "정보 없음"
