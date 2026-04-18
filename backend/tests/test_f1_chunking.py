"""F1 청킹 모듈 unit tests — newsamc 패턴 검증.

커버:
    - split_by_article: 조항 분할 + 폴백 빈 줄 분할
    - normalize_chunks: 소형 병합, 대형 분할
    - attach_metadata: vector_id + token_count
    - chunk_markdown: 엔드투엔드
"""
from __future__ import annotations

import pytest

from services.f1_chunking import (
    MAX_CHUNK_TOKENS, MIN_CHUNK_TOKENS,
    attach_metadata, chunk_markdown, count_tokens,
    normalize_chunks, split_by_article,
)


class TestSplitByArticle:
    def test_article_heading_split(self):
        md = "### 제1조 (목적)\n본문1\n\n### 제2조 (정의)\n본문2"
        chunks = split_by_article(md)
        assert len(chunks) == 2
        assert chunks[0]["section_path"].startswith("제1조")
        assert chunks[1]["section_path"].startswith("제2조")

    def test_fallback_blank_line_split(self):
        md = "단락 A\n\n단락 B\n\n단락 C"
        chunks = split_by_article(md)
        assert len(chunks) == 3
        assert all(c["section_path"].startswith("section_") for c in chunks)

    def test_single_paragraph_no_blanks(self):
        md = "짧은 본문 한 줄"
        chunks = split_by_article(md)
        assert len(chunks) == 1


class TestNormalizeChunks:
    def test_merges_small_consecutive_chunks(self):
        small = "가".ljust(10)  # 매우 작은 청크
        chunks = [
            {"text": small, "section_path": "section_0"},
            {"text": small, "section_path": "section_1"},
        ]
        normalized = normalize_chunks(chunks)
        assert len(normalized) == 1  # 병합됨
        assert small in normalized[0]["text"]

    def test_splits_large_chunk_by_sub_boundary(self):
        # MAX 초과 + ①②③ 경계 있는 텍스트
        body = "일반 설명 " * 200  # 토큰 많이
        text = f"{body}\n① 첫째 " + "가 " * 300 + "\n② 둘째 " + "나 " * 300
        chunks = [{"text": text, "section_path": "제1조"}]
        normalized = normalize_chunks(chunks)
        assert count_tokens(text) > MAX_CHUNK_TOKENS
        # 항/호 기준으로 분할되어야 함
        assert len(normalized) >= 2
        assert any("part" in c["section_path"] for c in normalized)

    def test_splits_large_chunk_sliding_window(self):
        # 경계 없는 긴 텍스트 → 슬라이딩
        text = "연속된 긴 텍스트 " * 3000
        chunks = [{"text": text, "section_path": "제1조"}]
        normalized = normalize_chunks(chunks)
        assert count_tokens(text) > MAX_CHUNK_TOKENS
        assert len(normalized) >= 2
        assert all(c["section_path"].startswith("제1조_window") for c in normalized)


class TestAttachMetadata:
    def test_vector_id_format_and_metadata(self):
        chunks = [
            {"text": "첫번째", "section_path": "제1조"},
            {"text": "두번째", "section_path": "제2조"},
        ]
        out = attach_metadata(chunks, "additive_code_2024", "additive_code_text")
        assert len(out) == 2
        assert out[0]["vector_id"] == "additive_code_2024_0000"
        assert out[1]["vector_id"] == "additive_code_2024_0001"
        assert out[0]["metadata"]["chunk_index"] == 0
        assert out[0]["metadata"]["total_chunks"] == 2
        assert out[0]["metadata"]["pinecone_namespace"] == "additive_code_text"
        assert out[0]["metadata"]["token_count"] > 0


class TestEndToEnd:
    def test_chunk_markdown_integration(self):
        md = "### 제1조 (목적)\n목적 조항 본문.\n\n### 제2조 (정의)\n정의 조항 본문."
        result = chunk_markdown(md, "test_reg", "food_code_text")
        assert len(result) >= 1
        assert all("vector_id" in c for c in result)
        assert all(c["metadata"]["regulation_id"] == "test_reg" for c in result)
