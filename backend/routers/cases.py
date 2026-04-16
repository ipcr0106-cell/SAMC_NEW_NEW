"""
SAMC 수입식품 검역 AI — 케이스(Case) CRUD 라우터

엔드포인트:
  POST   /api/v1/cases              → 새 검역 건 생성
  GET    /api/v1/cases              → 건 목록 조회
  GET    /api/v1/cases/{case_id}    → 단일 건 상세 조회
  PUT    /api/v1/cases/{case_id}    → 건 정보 수정 (product_name 등)
  PUT    /api/v1/cases/{case_id}/parsed-result  → OCR 파싱 결과 사용자 수정 저장
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from db.supabase_client import get_supabase
from schemas.upload import ParsedResult, ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["cases"])


# ─────────────────────────────────────────────
# 요청/응답 스키마
# ─────────────────────────────────────────────

class CaseCreateRequest(BaseModel):
    product_name: str = Field(description="제품명")
    importer_name: str = Field(default="", description="수입자명")


class CaseUpdateRequest(BaseModel):
    product_name: Optional[str] = None
    importer_name: Optional[str] = None
    status: Optional[str] = None
    current_step: Optional[str] = None


class CaseResponse(BaseModel):
    id: str
    product_name: str
    importer_name: str
    status: str
    current_step: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CaseListResponse(BaseModel):
    cases: list[CaseResponse]
    total: int


# ─────────────────────────────────────────────
# POST /cases — 새 건 생성
# ─────────────────────────────────────────────

@router.post(
    "/cases",
    response_model=CaseResponse,
    responses={500: {"model": ErrorResponse}},
    summary="새 검역 건 생성",
)
async def create_case(body: CaseCreateRequest):
    """새 검역 건을 생성하고 cases 테이블에 INSERT."""
    try:
        sb = get_supabase()
        result = sb.table("cases").insert({
            "product_name": body.product_name,
            "importer_name": body.importer_name or "",
            "status": "processing",
            "current_step": "0",
        }).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail={
                "error": "INSERT_FAILED",
                "message": "케이스 생성에 실패했습니다.",
            })

        row = result.data[0]
        logger.info(f"케이스 생성: id={row['id']}, product={body.product_name}")

        return CaseResponse(
            id=row["id"],
            product_name=row["product_name"],
            importer_name=row["importer_name"],
            status=row["status"],
            current_step=row.get("current_step"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"케이스 생성 실패: {e}")
        raise HTTPException(status_code=500, detail={
            "error": "INTERNAL_ERROR",
            "message": f"케이스 생성 중 오류: {str(e)}",
        })


# ─────────────────────────────────────────────
# GET /cases — 건 목록 조회
# ─────────────────────────────────────────────

@router.get(
    "/cases",
    response_model=CaseListResponse,
    summary="검역 건 목록 조회",
)
async def list_cases(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """케이스 목록을 최신순으로 조회."""
    try:
        sb = get_supabase()
        query = sb.table("cases").select("*", count="exact")

        if status:
            query = query.eq("status", status)

        query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
        result = query.execute()

        cases = [
            CaseResponse(
                id=row["id"],
                product_name=row["product_name"],
                importer_name=row["importer_name"],
                status=row["status"],
                current_step=row.get("current_step"),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
            )
            for row in (result.data or [])
        ]

        return CaseListResponse(cases=cases, total=result.count or len(cases))
    except Exception as e:
        logger.error(f"케이스 목록 조회 실패: {e}")
        raise HTTPException(status_code=500, detail={
            "error": "INTERNAL_ERROR",
            "message": f"목록 조회 중 오류: {str(e)}",
        })


# ─────────────────────────────────────────────
# GET /cases/{case_id} — 단일 건 상세 조회
# ─────────────────────────────────────────────

@router.get(
    "/cases/{case_id}",
    response_model=CaseResponse,
    responses={404: {"model": ErrorResponse}},
    summary="검역 건 상세 조회",
)
async def get_case(case_id: str):
    """단일 케이스의 상세 정보를 반환."""
    try:
        sb = get_supabase()
        result = sb.table("cases").select("*").eq("id", case_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail={
                "error": "CASE_NOT_FOUND",
                "message": "해당 건이 존재하지 않습니다.",
            })

        row = result.data[0]
        return CaseResponse(
            id=row["id"],
            product_name=row["product_name"],
            importer_name=row["importer_name"],
            status=row["status"],
            current_step=row.get("current_step"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"케이스 조회 실패: {e}")
        raise HTTPException(status_code=500, detail={
            "error": "INTERNAL_ERROR",
            "message": f"조회 중 오류: {str(e)}",
        })


# ─────────────────────────────────────────────
# PUT /cases/{case_id} — 건 정보 수정
# ─────────────────────────────────────────────

@router.put(
    "/cases/{case_id}",
    response_model=CaseResponse,
    responses={404: {"model": ErrorResponse}},
    summary="검역 건 정보 수정",
)
async def update_case(case_id: str, body: CaseUpdateRequest):
    """케이스의 product_name, status 등을 수정."""
    try:
        sb = get_supabase()

        # 존재 확인
        check = sb.table("cases").select("id").eq("id", case_id).execute()
        if not check.data:
            raise HTTPException(status_code=404, detail={
                "error": "CASE_NOT_FOUND",
                "message": "해당 건이 존재하지 않습니다.",
            })

        update_data = {k: v for k, v in body.model_dump().items() if v is not None}
        if not update_data:
            raise HTTPException(status_code=400, detail={
                "error": "NO_UPDATE_FIELDS",
                "message": "수정할 필드가 없습니다.",
            })

        result = sb.table("cases").update(update_data).eq("id", case_id).execute()
        row = result.data[0]

        return CaseResponse(
            id=row["id"],
            product_name=row["product_name"],
            importer_name=row["importer_name"],
            status=row["status"],
            current_step=row.get("current_step"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"케이스 수정 실패: {e}")
        raise HTTPException(status_code=500, detail={
            "error": "INTERNAL_ERROR",
            "message": f"수정 중 오류: {str(e)}",
        })


# ─────────────────────────────────────────────
# DELETE /cases/{case_id} — 검역 건 삭제
# ─────────────────────────────────────────────

STORAGE_BUCKET = "documents"

@router.delete(
    "/cases/{case_id}",
    responses={404: {"model": ErrorResponse}},
    summary="검역 건 삭제",
    description="검역 건과 관련된 문서, 파이프라인 데이터, Storage 파일을 모두 삭제합니다.",
)
async def delete_case(case_id: str):
    """케이스와 관련된 모든 데이터를 삭제."""
    try:
        sb = get_supabase()

        # 1) 존재 확인
        check = sb.table("cases").select("id").eq("id", case_id).execute()
        if not check.data:
            raise HTTPException(status_code=404, detail={
                "error": "CASE_NOT_FOUND",
                "message": "해당 건이 존재하지 않습니다.",
            })

        # 2) Storage 파일 삭제 (documents 테이블에서 storage_path 조회)
        docs = sb.table("documents").select("storage_path").eq("case_id", case_id).execute()
        if docs.data:
            paths = [d["storage_path"] for d in docs.data if d.get("storage_path")]
            if paths:
                try:
                    sb.storage.from_(STORAGE_BUCKET).remove(paths)
                except Exception as e:
                    logger.warning(f"Storage 파일 삭제 실패 (진행): {e}")

        # 3) pipeline_steps 삭제
        try:
            sb.table("pipeline_steps").delete().eq("case_id", case_id).execute()
        except Exception as e:
            logger.warning(f"pipeline_steps 삭제 실패: {e}")

        # 4) documents 삭제
        try:
            sb.table("documents").delete().eq("case_id", case_id).execute()
        except Exception as e:
            logger.warning(f"documents 삭제 실패: {e}")

        # 5) cases 삭제
        sb.table("cases").delete().eq("id", case_id).execute()

        logger.info(f"케이스 삭제 완료: id={case_id}")

        return {"success": True, "case_id": case_id, "message": "검역 건이 삭제되었습니다."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"케이스 삭제 실패: {e}")
        raise HTTPException(status_code=500, detail={
            "error": "INTERNAL_ERROR",
            "message": f"삭제 중 오류: {str(e)}",
        })


# ─────────────────────────────────────────────
# PUT /cases/{case_id}/parsed-result — 사용자 수정 파싱 결과 저장
# ─────────────────────────────────────────────

@router.put(
    "/cases/{case_id}/parsed-result",
    summary="OCR 파싱 결과 사용자 수정 저장",
    description="사용자가 OcrResultEditor에서 수정한 파싱 결과를 pipeline_steps에 저장합니다.",
)
async def save_parsed_result(case_id: str, body: ParsedResult):
    """사용자가 수정한 파싱 결과를 pipeline_steps 테이블에 저장.
    step_key='0' (입력/파싱 단계)으로 저장하여 F1~F5에서 참조.
    """
    try:
        sb = get_supabase()

        # 케이스 존재 확인
        check = sb.table("cases").select("id").eq("id", case_id).execute()
        if not check.data:
            raise HTTPException(status_code=404, detail={
                "error": "CASE_NOT_FOUND",
                "message": "해당 건이 존재하지 않습니다.",
            })

        # pipeline_steps에 upsert (step_key='0'은 입력/파싱 단계)
        step_data = {
            "case_id": case_id,
            "step_key": "0",
            "step_name": "입력 및 OCR 파싱",
            "status": "completed",
            "final_result": body.model_dump(),
        }

        # UPSERT: (case_id, step_key) 유니크 제약조건 활용
        result = sb.table("pipeline_steps").upsert(
            step_data,
            on_conflict="case_id,step_key",
        ).execute()

        logger.info(f"파싱 결과 저장: case={case_id}, 성분 {len(body.ingredients)}개")

        return {
            "success": True,
            "case_id": case_id,
            "message": "파싱 결과가 저장되었습니다.",
            "ingredient_count": len(body.ingredients),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"파싱 결과 저장 실패: {e}")
        raise HTTPException(status_code=500, detail={
            "error": "INTERNAL_ERROR",
            "message": f"저장 중 오류: {str(e)}",
        })


# ─────────────────────────────────────────────
# GET /cases/{case_id}/parsed-result — 저장된 파싱 결과 조회
# ─────────────────────────────────────────────

@router.get(
    "/cases/{case_id}/parsed-result",
    summary="저장된 파싱 결과 조회",
)
async def get_parsed_result(case_id: str):
    """pipeline_steps에서 step_key='0'의 final_result를 조회."""
    try:
        sb = get_supabase()
        result = sb.table("pipeline_steps") \
            .select("*") \
            .eq("case_id", case_id) \
            .eq("step_key", "0") \
            .execute()

        if not result.data:
            return {"case_id": case_id, "parsed_result": None, "status": "pending"}

        row = result.data[0]
        return {
            "case_id": case_id,
            "status": row["status"],
            "parsed_result": row.get("final_result") or row.get("ai_result"),
            "updated_at": row.get("updated_at"),
        }
    except Exception as e:
        logger.error(f"파싱 결과 조회 실패: {e}")
        raise HTTPException(status_code=500, detail={
            "error": "INTERNAL_ERROR",
            "message": f"조회 중 오류: {str(e)}",
        })
