"""F1 Pinecone + OpenAI 클라이언트 unit tests — mock 기반.

실제 외부 API 호출 없이 파라미터/싱글톤/반환 형태 검증.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from services import f1_openai_client, f1_pinecone_client


# ============================================================
# f1_openai_client
# ============================================================


@pytest.fixture(autouse=True)
def reset_openai_singleton(monkeypatch):
    monkeypatch.setenv("F1_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("F1_PINECONE_API_KEY", "pcsk-test")
    f1_openai_client._client = None
    f1_pinecone_client._pc = None
    f1_pinecone_client._index = None
    yield


class TestEmbed:
    def test_empty_input_returns_empty(self):
        assert f1_openai_client.embed([]) == []

    def test_batch_call(self, monkeypatch):
        fake_client = MagicMock()
        fake_client.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1, 0.2]), MagicMock(embedding=[0.3, 0.4])]
        )
        monkeypatch.setattr(f1_openai_client, "_client", fake_client)

        result = f1_openai_client.embed(["a", "b"])

        assert result == [[0.1, 0.2], [0.3, 0.4]]
        fake_client.embeddings.create.assert_called_once()
        call_kwargs = fake_client.embeddings.create.call_args.kwargs
        assert call_kwargs["model"] == "text-embedding-3-small"
        assert call_kwargs["input"] == ["a", "b"]


class TestChatJson:
    def test_json_mode_applied(self, monkeypatch):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"verdict": "permitted"}'))]
        )
        monkeypatch.setattr(f1_openai_client, "_client", fake_client)

        result = f1_openai_client.chat_json("sys prompt with JSON", "user msg")

        assert result == {"verdict": "permitted"}
        call_kwargs = fake_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}
        assert call_kwargs["temperature"] == 0.0

    def test_invalid_json_raises(self, monkeypatch):
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="not json"))]
        )
        monkeypatch.setattr(f1_openai_client, "_client", fake_client)

        with pytest.raises(Exception):  # json.JSONDecodeError
            f1_openai_client.chat_json("sys", "user")


class TestGetClientMissingEnv:
    def test_raises_on_missing_key(self, monkeypatch):
        monkeypatch.delenv("F1_OPENAI_API_KEY", raising=False)
        f1_openai_client._client = None
        with pytest.raises(RuntimeError, match="F1_OPENAI_API_KEY"):
            f1_openai_client.get_client()


# ============================================================
# f1_pinecone_client
# ============================================================


class TestSearchSync:
    def test_returns_hit_list(self, monkeypatch):
        fake_index = MagicMock()
        fake_match = MagicMock(
            id="chunk_1",
            score=0.92,
            metadata={
                "text": "제3조 ...",
                "regulation_id": "food_code_2024",
                "section_path": "제3조",
            },
        )
        fake_index.query.return_value = MagicMock(matches=[fake_match])
        monkeypatch.setattr(f1_pinecone_client, "_index", fake_index)

        hits = f1_pinecone_client.search_sync([0.1] * 1536, "food_code_text", 5)

        assert len(hits) == 1
        assert hits[0]["id"] == "chunk_1"
        assert hits[0]["namespace"] == "food_code_text"
        assert hits[0]["score"] == 0.92
        fake_index.query.assert_called_once()


class TestSearchMulti:
    def test_aggregates_and_sorts_by_score(self, monkeypatch):
        def fake_search(v, ns, k):
            return [{"id": f"{ns}_0", "score": 0.5 if ns == "a" else 0.9,
                     "text": "", "regulation_id": None, "section_path": None,
                     "namespace": ns}]

        monkeypatch.setattr(f1_pinecone_client, "search_sync", fake_search)

        hits = asyncio.run(
            f1_pinecone_client.search_multi([0.1] * 1536, ["a", "b"], top_k_per_ns=1)
        )

        assert len(hits) == 2
        assert hits[0]["score"] == 0.9  # 내림차순 정렬
        assert hits[0]["namespace"] == "b"


class TestGetIndexMissingEnv:
    def test_raises_on_missing_key(self, monkeypatch):
        monkeypatch.delenv("F1_PINECONE_API_KEY", raising=False)
        f1_pinecone_client._pc = None
        f1_pinecone_client._index = None
        with pytest.raises(RuntimeError, match="F1_PINECONE_API_KEY"):
            f1_pinecone_client.get_index()
