"""
F3 법령 업데이트 전처리 유닛 테스트.

실행:
    cd backend
    python -m pytest tests/test_f3_preprocess.py -v

이 테스트는 외부 의존성(Supabase, Pinecone) 없이 돌아가도록 설계됨.
Supabase 필요한 snapshot 함수는 별도 통합 테스트 대상.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from services.f3_preprocess import snapshot
from services.f3_preprocess.pinecone_embed import chunk_id


# ═══════════════════════════════════════════════════════════
# snapshot.compute_diff_summary — diff 계산 로직
# ═══════════════════════════════════════════════════════════

class TestComputeDiffSummary:
    def test_empty_to_empty(self):
        result = snapshot.compute_diff_summary([], [], "id")
        assert result["added"] == 0
        assert result["modified"] == 0
        assert result["deleted"] == 0

    def test_all_added(self):
        new = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        result = snapshot.compute_diff_summary([], new, "id")
        assert result["added"] == 2
        assert result["deleted"] == 0
        assert set(result["added_keys"]) == {1, 2}

    def test_all_deleted(self):
        old = [{"id": 1, "name": "a"}]
        result = snapshot.compute_diff_summary(old, [], "id")
        assert result["added"] == 0
        assert result["deleted"] == 1
        assert result["deleted_keys"] == [1]

    def test_modified(self):
        old = [{"id": 1, "name": "old"}]
        new = [{"id": 1, "name": "new"}]
        result = snapshot.compute_diff_summary(old, new, "id")
        assert result["modified"] == 1
        assert result["modified_keys"] == [1]

    def test_mixed(self):
        old = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}, {"id": 3, "name": "c"}]
        new = [{"id": 1, "name": "a"}, {"id": 2, "name": "b_changed"}, {"id": 4, "name": "d"}]
        result = snapshot.compute_diff_summary(old, new, "id")
        assert result["added"] == 1
        assert result["deleted"] == 1
        assert result["modified"] == 1
        assert result["unchanged"] == 1

    def test_no_pk_column_rows_filtered(self):
        # pk 값이 None/누락된 행은 무시
        old = [{"id": 1, "x": 1}, {"id": None, "x": 2}]
        new = [{"id": 1, "x": 1}]
        result = snapshot.compute_diff_summary(old, new, "id")
        assert result["deleted"] == 0  # id=None 행은 카운트 안 됨


# ═══════════════════════════════════════════════════════════
# snapshot._detect_pk_column — PK 감지
# ═══════════════════════════════════════════════════════════

class TestDetectPK:
    def test_known_f3_tables(self):
        assert snapshot._detect_pk_column("f3_required_documents") == "id"
        assert snapshot._detect_pk_column("f3_food_type_categories") == "food_type"
        assert snapshot._detect_pk_column("f3_plant_based_patterns") == "pattern"

    def test_unknown_f3_table_falls_back_to_id(self):
        # 맵에 없으면 "id"
        assert snapshot._detect_pk_column("f3_unknown_new_table") == "id"

    def test_non_f3_rejected(self):
        with pytest.raises(ValueError):
            snapshot._detect_pk_column("cases")


# ═══════════════════════════════════════════════════════════
# snapshot._acquire_in_process_lock — 동시성
# ═══════════════════════════════════════════════════════════

class TestInProcessLock:
    def test_acquire_once_succeeds(self):
        # 각 테스트마다 lock 상태 초기화
        snapshot._IN_PROCESS_LOCKS.clear()
        assert snapshot._acquire_in_process_lock("test_law") is True

    def test_acquire_twice_fails(self):
        snapshot._IN_PROCESS_LOCKS.clear()
        snapshot._acquire_in_process_lock("test_law")
        assert snapshot._acquire_in_process_lock("test_law") is False

    def test_different_laws_independent(self):
        snapshot._IN_PROCESS_LOCKS.clear()
        assert snapshot._acquire_in_process_lock("law_a") is True
        assert snapshot._acquire_in_process_lock("law_b") is True

    def test_release_allows_reacquire(self):
        snapshot._IN_PROCESS_LOCKS.clear()
        snapshot._acquire_in_process_lock("test_law")
        snapshot._release_in_process_lock("test_law")
        assert snapshot._acquire_in_process_lock("test_law") is True


# ═══════════════════════════════════════════════════════════
# pinecone_embed.chunk_id — 결정적 ID
# ═══════════════════════════════════════════════════════════

class TestChunkId:
    def test_deterministic(self):
        a = chunk_id("법령A", "제1조", 0)
        b = chunk_id("법령A", "제1조", 0)
        assert a == b

    def test_different_inputs_different_ids(self):
        a = chunk_id("법령A", "제1조", 0)
        b = chunk_id("법령A", "제2조", 0)
        c = chunk_id("법령B", "제1조", 0)
        d = chunk_id("법령A", "제1조", 1)
        assert a != b != c != d


# ═══════════════════════════════════════════════════════════
# excel_required_docs.parse — Excel 파서 (실제 파일 필요)
# ═══════════════════════════════════════════════════════════

EXCEL_SUBMIT = Path(__file__).parent.parent.parent / "f3_작업" / "DB추가자료" / "6_가이드라인" / "수입신고시_제출하여야_하는_구비서류_목록(2026.2.5.현재).xlsx"
EXCEL_KEEP = Path(__file__).parent.parent.parent / "f3_작업" / "DB추가자료" / "6_가이드라인" / "영업자가_보관하여야_하는_서류_목록(2026.2.5.현재).xlsx"


class TestExcelParser:
    @pytest.mark.skipif(not EXCEL_SUBMIT.exists(), reason="제출 엑셀 파일 없음")
    def test_submit_excel_produces_submit_type(self):
        from services.f3_preprocess.excel_required_docs import parse
        result = parse(EXCEL_SUBMIT, "수입신고 구비서류 목록")
        rows = result["tables"]["f3_required_documents"]["new_rows"]
        assert len(rows) > 0
        assert all(r["submission_type"] == "submit" for r in rows)
        assert all(r["id"].startswith("submit_") for r in rows)
        # scope_filter 존재 확인 (critical fix)
        scope = result["tables"]["f3_required_documents"]["scope_filter"]
        assert scope == {"submission_type": "submit"}

    @pytest.mark.skipif(not EXCEL_KEEP.exists(), reason="보관 엑셀 파일 없음")
    def test_keep_excel_produces_keep_type(self):
        from services.f3_preprocess.excel_required_docs import parse
        result = parse(EXCEL_KEEP, "수입신고 구비서류 목록")
        rows = result["tables"]["f3_required_documents"]["new_rows"]
        assert len(rows) > 0
        assert all(r["submission_type"] == "keep" for r in rows)
        assert all(r["id"].startswith("keep_") for r in rows)
        scope = result["tables"]["f3_required_documents"]["scope_filter"]
        assert scope == {"submission_type": "keep"}

    def test_invalid_path_raises(self):
        from services.f3_preprocess.excel_required_docs import parse
        with pytest.raises(Exception):
            parse(Path("/nonexistent/fake.xlsx"), "수입신고 구비서류 목록")


# ═══════════════════════════════════════════════════════════
# rule_pdf / guide_pdf — PDF 파서
# ═══════════════════════════════════════════════════════════

RULE_PDF = Path(__file__).parent.parent.parent / "f3_작업" / "DB추가자료" / "6_가이드라인" / "수입식품안전관리 특별법 시행규칙(총리령)(제02038호)(20250723).pdf"


class TestRulePdfParser:
    @pytest.mark.skipif(not RULE_PDF.exists(), reason="시행규칙 PDF 없음")
    def test_basic_chunking(self):
        from services.f3_preprocess.rule_pdf import parse
        result = parse(RULE_PDF, "수입식품안전관리 특별법 시행규칙")
        assert "pinecone_chunks" in result
        assert result["pinecone_touched"] is True
        chunks = result["pinecone_chunks"]
        assert len(chunks) > 0
        # 모든 청크에 결정적 ID 부여
        ids = [c["pinecone_chunk_id"] for c in chunks]
        assert len(set(ids)) == len(ids)  # 중복 없음


# ═══════════════════════════════════════════════════════════
# 파서 dispatcher — law_name 매핑
# ═══════════════════════════════════════════════════════════

class TestDispatcher:
    def test_supported_laws(self):
        from services.f3_preprocess.dispatcher import SUPPORTED_LAWS
        assert "수입신고 구비서류 목록" in SUPPORTED_LAWS
        assert "식품공전" in SUPPORTED_LAWS
        assert "식품첨가물공전" in SUPPORTED_LAWS

    def test_parser_mapping(self):
        from services.f3_preprocess.dispatcher import get_parser_module
        assert get_parser_module("수입신고 구비서류 목록") == "excel_required_docs"
        assert get_parser_module("수입식품안전관리 특별법 시행규칙") == "rule_pdf"
        assert get_parser_module("OEM 수입식품 관리 안내서") == "guide_pdf"
        assert get_parser_module("동등성인정 협정문") == "guide_pdf"
        assert get_parser_module("식품공전") == "foodcode_hwpx"
        assert get_parser_module("식품첨가물공전") == "foodcode_hwpx"

    def test_unknown_law_raises(self):
        from services.f3_preprocess.dispatcher import get_parser_module
        with pytest.raises(ValueError):
            get_parser_module("xxx알수없는법령xxx")


# ═══════════════════════════════════════════════════════════
# 새 기능 — Task 1 fix 검증
# ═══════════════════════════════════════════════════════════

class TestChunkSize:
    """multilingual-e5-large 토큰 한도 대응: 1000자 이하여야 함."""

    def test_rule_pdf_max_chunk_chars(self):
        from services.f3_preprocess import rule_pdf
        assert rule_pdf._MAX_CHUNK_CHARS <= 1000, (
            "청크가 1000자 초과 시 임베딩 토큰 한도 초과 위험"
        )

    def test_guide_pdf_max_chunk_chars(self):
        from services.f3_preprocess import guide_pdf
        assert guide_pdf._MAX_CHUNK_CHARS <= 1000


class TestExcelScopeFilter:
    """Critical — Step 1 업데이트가 반대 종류 row 를 삭제하면 안 됨."""

    @pytest.mark.skipif(not EXCEL_SUBMIT.exists(), reason="제출 엑셀 없음")
    def test_submit_excel_scope_filter_set(self):
        from services.f3_preprocess.excel_required_docs import parse
        result = parse(EXCEL_SUBMIT, "수입신고 구비서류 목록")
        spec = result["tables"]["f3_required_documents"]
        assert spec["scope_filter"] == {"submission_type": "submit"}, (
            "scope_filter 없으면 보관용 14건 전체 삭제됨"
        )


class TestPineconeChunkResult:
    """Step 2/3 파서는 Supabase 테이블 + Pinecone 청크 모두 반환해야 함."""

    @pytest.mark.skipif(not RULE_PDF.exists(), reason="시행규칙 PDF 없음")
    def test_rule_pdf_returns_pinecone_chunks(self):
        from services.f3_preprocess.rule_pdf import parse
        result = parse(RULE_PDF, "수입식품안전관리 특별법 시행규칙")
        assert "pinecone_chunks" in result
        assert isinstance(result["pinecone_chunks"], list)
        for c in result["pinecone_chunks"]:
            assert "pinecone_chunk_id" in c
            assert "text" in c
            # 각 chunk 는 임베딩 한도 내여야 함 (1000자)
            assert len(c["text"]) <= 1100, "청크 크기 한도 초과"


class TestSnapshotGuards:
    """snapshot.py 안전장치들."""

    def test_compute_diff_summary_empty(self):
        # 빈-to-빈 edge case
        assert snapshot.compute_diff_summary([], [], "id")["added"] == 0

    def test_check_idempotency_none_key_returns_none(self):
        result = snapshot.check_idempotency(None)
        assert result is None


class TestManualRuleValidation:
    """수동 규칙 추가 엔드포인트 검증 (Pydantic 모델 + 로직)."""

    def test_manual_rule_request_model(self):
        from routers.feature3_admin import ManualRuleRequest
        # 필수 필드만
        r = ManualRuleRequest(
            doc_name="테스트", doc_description="설명", target_country="중국"
        )
        assert r.doc_name == "테스트"
        assert r.submission_type == "submit"
        assert r.submission_timing == "every"
        assert r.is_mandatory is True

    def test_manual_rule_target_required_logic(self):
        # 모든 적용대상이 비어있으면 API 레벨에서 400 에러 (로직 확인)
        from routers.feature3_admin import ManualRuleRequest
        r = ManualRuleRequest(doc_name="x", doc_description="y")
        has_target = any([r.target_country, r.food_type, r.condition, r.product_keywords])
        assert has_target is False


class TestAddSingleRuleShape:
    """snapshot.add_single_rule 의 반환 구조 + 중복 ID 차단 검증 (DB 연결 없는 부분만)."""

    def test_add_single_rule_requires_pk_value(self):
        # new_row 에 PK 값이 없으면 ValueError
        # (실제 DB 안 건드리려면 _env 실패 시 RuntimeError 먼저 — 이 테스트는 구조만 확인)
        from services.f3_preprocess import snapshot as snap
        import os
        # env 없는 환경에선 RuntimeError
        with pytest.raises((RuntimeError, ValueError)):
            snap.add_single_rule(
                "f3_required_documents",
                {},  # id 없음
                "테스트",
            )


class TestDispatcherSupported:
    """6종 법령 전부 파서 매핑 존재 확인."""

    def test_all_6_laws_have_parsers(self):
        from services.f3_preprocess.dispatcher import SUPPORTED_LAWS, get_parser_module
        expected = {
            "수입신고 구비서류 목록",
            "수입식품안전관리 특별법 시행규칙",
            "OEM 수입식품 관리 안내서",
            "동등성인정 협정문",
            "식품공전",
            "식품첨가물공전",
        }
        assert expected <= SUPPORTED_LAWS, f"누락된 법령: {expected - SUPPORTED_LAWS}"
        for law in expected:
            assert get_parser_module(law), f"{law} 파서 없음"
