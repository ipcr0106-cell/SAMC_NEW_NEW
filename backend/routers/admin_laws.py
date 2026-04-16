"""
관리자용 법령 업데이트 API

POST /admin/laws/upload
  - PDF 파일 + 메타데이터를 받아 해당 법령만 단독으로 재전처리
  - Pinecone upsert (결정적 ID) + Supabase 갱신

GET /admin/laws
  - 현재 등록된 법령 목록 반환 (Supabase law_documents 조회)
"""

import os
import tempfile
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

load_dotenv()  # backend/.env 통합 사용

router = APIRouter(prefix="/admin/laws", tags=["admin-laws"])

# 지연 초기화 (앱 첫 요청 시 1회 로드)
_clients: dict = {}


def _get_clients() -> dict:
    """Pinecone / Supabase / SentenceTransformer / OpenAI 클라이언트 싱글톤."""
    if _clients:
        return _clients

    from openai import OpenAI
    from pinecone import Pinecone
    from sentence_transformers import SentenceTransformer
    from supabase import create_client

    pinecone_key  = os.getenv("F4_PINECONE_API_KEY")
    pinecone_host = os.getenv("F4_PINECONE_HOST")
    supabase_url  = os.getenv("SUPABASE_URL")
    supabase_key  = os.getenv("SUPABASE_SERVICE_KEY")
    openai_key = os.getenv("F4_OPENAI_API_KEY")

    if not all([pinecone_key, pinecone_host, supabase_url, supabase_key]):
        raise RuntimeError(
            "환경변수 미설정: PINECONE_API_KEY, PINECONE_HOST, SUPABASE_URL, SUPABASE_SERVICE_KEY"
        )

    pc = Pinecone(api_key=pinecone_key)
    _clients["index"]    = pc.Index(host=pinecone_host)
    _clients["supabase"] = create_client(supabase_url, supabase_key)
    _clients["model"]    = SentenceTransformer("intfloat/multilingual-e5-large")
    _clients["claude"]   = OpenAI(api_key=openai_key)
    return _clients


# 법령 계층 상수 (프론트에서 문자열로 받아 숫자로 변환)
_TIER_MAP = {"법률": 1, "시행령": 2, "시행규칙": 3, "고시": 4}


@router.post("/upload")
async def upload_law(
    file: UploadFile = File(..., description="법령 PDF 파일"),
    law_name: str    = Form(..., description="법령명 (예: 식품등의 표시기준)"),
    고시번호: str    = Form(..., description="고시번호 (예: 제2025-60호)"),
    시행일: str      = Form(..., description="시행일 (YYYY-MM-DD)"),
    tier: str        = Form("고시", description="법령 계층: 법률 | 시행령 | 시행규칙 | 고시"),
    category: str    = Form("표시기준", description="카테고리 (자유 입력)"),
):
    """
    새 법령 PDF를 업로드하면 해당 법령만 재전처리.
    기존 법령과 law_name이 같으면 Pinecone·Supabase 모두 덮어씀.
    """
    # 유효성 검사
    allowed_ext = {".pdf", ".hwpx"}
    if not file.filename or Path(file.filename).suffix.lower() not in allowed_ext:
        raise HTTPException(status_code=400, detail="PDF 또는 HWPX 파일만 업로드 가능합니다.")

    tier_int = _TIER_MAP.get(tier)
    if tier_int is None:
        raise HTTPException(status_code=400, detail=f"tier는 {list(_TIER_MAP)} 중 하나여야 합니다.")

    try:
        enforce_date = date.fromisoformat(시행일)
    except ValueError:
        raise HTTPException(status_code=400, detail="시행일 형식이 올바르지 않습니다 (YYYY-MM-DD).")

    # PDF를 임시 파일에 저장
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        clients = _get_clients()

        # preprocess_laws 모듈 import (상대 경로)
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "db" / "feature4"))
        from preprocess_laws import preprocess_single_law

        result = preprocess_single_law(
            pdf_path       = tmp_path,
            law_name       = law_name,
            고시번호       = 고시번호,
            시행일         = enforce_date,
            tier           = tier_int,
            category       = category,
            index          = clients["index"],
            supabase_client= clients["supabase"],
            model          = clients["model"],
            claude_client  = clients["claude"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"전처리 실패: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)

    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "db" / "feature4"))
    from extract_prohibited_keywords import extract_for_law
    from extract_image_violation_types import extract_image_types_for_law

    # 법령 업데이트 시 이미지 분석 프롬프트 캐시 무효화
    from routers.feature4 import _invalidate_prompt_cache
    _invalidate_prompt_cache()

    keyword_count = 0
    img_types_added = 0
    img_types_supplemented = 0

    # 금지 표현 키워드 추출 (업로드된 모든 법령 대상)
    try:
        print(f"[자동 트리거] '{law_name}' 금지 표현 추출 시작...")
        keyword_count = extract_for_law(
            law_name = law_name,
            index    = clients["index"],
            supabase = clients["supabase"],
            claude   = clients["claude"],
        )
    except Exception as e:
        print(f"[경고] 금지 표현 추출 실패 (법령 전처리는 완료됨): {e}")

    # 이미지 위반 유형 추출 (신규·보완 항목 → is_active=False로 저장, 관리자 검토 대기)
    try:
        print(f"[자동 트리거] '{law_name}' 이미지 위반 유형 추출 시작...")
        img_result = extract_image_types_for_law(
            law_name = law_name,
            index    = clients["index"],
            supabase = clients["supabase"],
            claude   = clients["claude"],
        )
        img_types_added        = img_result["added_active"]
        img_types_supplemented = img_result["supplemented"]
    except Exception as e:
        print(f"[경고] 이미지 위반 유형 추출 실패 (법령 전처리는 완료됨): {e}")

    return JSONResponse({
        "message":                  f"'{law_name}' 전처리 완료",
        "law_doc_id":               result["law_doc_id"],
        "total_chunks":             result["total_chunks"],
        "article_cnt":              result["article_cnt"],
        "table_cnt":                result["table_cnt"],
        "image_cnt":                result["image_cnt"],
        "keywords_extracted":       keyword_count,
        "image_types_pending":      img_types_added,       # 관리자 검토 대기 중인 신규 유형 수
        "image_types_supplemented": img_types_supplemented, # 기존 유형에 세부항목 보완된 수
    })


@router.get("")
async def list_laws():
    """현재 등록된 법령 목록을 반환 (Supabase law_documents 조회)."""
    try:
        clients = _get_clients()
        res = (
            clients["supabase"]
            .table("f4_law_documents")
            .select("id, law_name, 고시번호, 시행일, 법령_tier, total_chunks, created_at")
            .order("법령_tier")
            .execute()
        )
        return {"laws": res.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"조회 실패: {e}")


@router.get("/image-violation-types")
async def list_image_violation_types(active_only: bool = False):
    """
    이미지 위반 유형 목록 반환.
    - active_only=false (기본): 전체 반환 (활성 + 검토 보류)
    - active_only=true: 활성(is_active=True) 유형만 반환
    """
    try:
        clients = _get_clients()
        query = (
            clients["supabase"]
            .table("f4_image_violation_types")
            .select("id, type_name, sub_items, default_severity, law_ref, source, is_active, review_note, created_at")
            .order("created_at")
        )
        if active_only:
            query = query.eq("is_active", True)
        res = query.execute()

        data  = res.data or []
        total    = len(data)
        active   = sum(1 for r in data if r["is_active"])
        pending  = total - active

        return {
            "total":   total,
            "active":  active,
            "pending": pending,
            "types":   data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"조회 실패: {e}")


@router.patch("/image-violation-types/{type_id}/activate")
async def activate_image_violation_type(type_id: str):
    """검토 보류(is_active=False) 유형을 수동으로 활성화."""
    try:
        clients = _get_clients()
        res = (
            clients["supabase"]
            .table("f4_image_violation_types")
            .update({"is_active": True, "review_note": "관리자 수동 활성화", "updated_at": "now()"})
            .eq("id", type_id)
            .execute()
        )
        if not res.data:
            raise HTTPException(status_code=404, detail="해당 유형을 찾을 수 없습니다.")

        # 프롬프트 캐시 무효화 (활성화된 유형이 즉시 반영되도록)
        from routers.feature4 import _invalidate_prompt_cache
        _invalidate_prompt_cache()

        return {"message": "활성화 완료", "type": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"활성화 실패: {e}")
