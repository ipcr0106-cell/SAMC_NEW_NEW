"""
SAMC 수입식품 검역 AI — 파일 업로드 및 파싱 라우터

엔드포인트:
  POST /api/v1/cases/{case_id}/upload   → 파일 업로드
  POST /api/v1/cases/{case_id}/parse    → OCR + LLM 파싱 실행
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from urllib.parse import quote

from db.supabase_client import get_supabase
from schemas.upload import (
    DocType,
    ErrorResponse,
    ParseResponse,
    ParseStatus,
    UploadResponse,
)
from services.ocr_service import extract_text_from_file
from services.parsing_service import parse_raw_texts_to_structured
from services.label_image_service import process_label_image
from services.export_service import build_docx, build_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["upload"])


# ─────────────────────────────────────────────
# GET /cases/{case_id}/parsed-result/export.{fmt}
#   OCR 분석 결과를 docx / pdf 파일로 내려줌
# ─────────────────────────────────────────────

def _fetch_parsed_for_export(case_id: str) -> tuple[dict, str]:
    """pipeline_steps(step_key='0').ai_result → dict. (parsed, product_name)"""
    sb = get_supabase()

    case_check = sb.table("cases").select("id, product_name").eq("id", case_id).execute()
    if not case_check.data:
        raise HTTPException(
            status_code=404,
            detail={"error": "CASE_NOT_FOUND", "message": "해당 건이 존재하지 않습니다."},
        )
    product_name = case_check.data[0].get("product_name", "") or ""

    ps = (
        sb.table("pipeline_steps")
        .select("ai_result")
        .eq("case_id", case_id)
        .eq("step_key", "0")
        .execute()
    )
    if not ps.data or not ps.data[0].get("ai_result"):
        raise HTTPException(
            status_code=404,
            detail={
                "error": "NO_PARSED_RESULT",
                "message": "분석 결과가 없습니다. 먼저 OCR 분석을 실행해주세요.",
            },
        )
    return ps.data[0]["ai_result"], product_name


def _fetch_label_images_for_export(
    case_id: str,
    selected_ids: set[str] | None = None,
) -> list[dict]:
    """case_label_images에서 이미지 바이트 + 텍스트 필드 조합해서 반환.

    selected_ids: 포함할 이미지 ID set. None이면 전체 반환.

    반환 리스트 각 항목:
      bytes, image_index, label_product_name, label_ingredients,
      label_content_volume, label_origin, label_manufacturer, label_case_number
    """
    sb = get_supabase()
    try:
        query = (
            sb.table("case_label_images")
            .select(
                "id, image_index, cropped_storage_path, "
                "label_product_name, label_ingredients, label_content_volume, "
                "label_origin, label_manufacturer, label_case_number"
            )
            .eq("case_id", case_id)
            .order("source_document_id", desc=False)
            .order("image_index", desc=False)
        )
        # 선택된 ID가 있으면 필터 적용
        if selected_ids:
            query = query.in_("id", list(selected_ids))
        rows = query.execute()
    except Exception as e:
        logger.warning(f"라벨 이미지 조회 실패 (export 스킵): {e}")
        return []

    result = []
    for row in (rows.data or []):
        path = row.get("cropped_storage_path")
        if not path:
            continue
        try:
            img_bytes = sb.storage.from_(STORAGE_BUCKET).download(path)
            if not img_bytes:
                continue
        except Exception as e:
            logger.warning(f"라벨 이미지 다운로드 실패 (스킵): {path} — {e}")
            continue

        result.append({
            "bytes": img_bytes,
            "image_index": row.get("image_index", 0),
            "label_product_name":   row.get("label_product_name"),
            "label_ingredients":    row.get("label_ingredients"),
            "label_content_volume": row.get("label_content_volume"),
            "label_origin":         row.get("label_origin"),
            "label_manufacturer":   row.get("label_manufacturer"),
            "label_case_number":    row.get("label_case_number"),
        })
    return result


def _content_disposition(filename: str) -> str:
    """한글 파일명 안전 처리 (RFC 5987)."""
    ascii_safe = filename.encode("ascii", "ignore").decode("ascii") or "result"
    return f"attachment; filename=\"{ascii_safe}\"; filename*=UTF-8''{quote(filename)}"


def _export_filename(product_name: str, case_id: str, ext: str) -> str:
    """파일명: OCR분석결과_제품명_YYYYMMDD.ext
    - 제품명이 없으면 case_id 앞 8자리로 대체
    - 파일명에 쓸 수 없는 특수문자 제거 (/ \\ : * ? " < > |)
    """
    import re
    date_str = datetime.now().strftime("%Y%m%d")
    name = (product_name or case_id[:8]).strip()
    # 파일명 금지 문자 제거
    name = re.sub(r'[/\\:*?"<>|]', "", name)
    # 연속 공백/언더바 정리
    name = re.sub(r"[\s_]+", "_", name).strip("_")
    return f"OCR분석결과_{name}_{date_str}.{ext}"


@router.get(
    "/cases/{case_id}/parsed-result/export.docx",
    summary="OCR 분석 결과 DOCX 다운로드",
)
async def export_parsed_docx(
    case_id: str,
    selected_image_ids: str | None = Query(
        default=None,
        description="쉼표로 구분된 선택 이미지 ID. 미전달 시 전체 이미지 포함.",
    ),
):
    parsed, product_name = _fetch_parsed_for_export(case_id)
    sel_ids = set(selected_image_ids.split(",")) if selected_image_ids else None
    label_images = _fetch_label_images_for_export(case_id, selected_ids=sel_ids)
    try:
        data = build_docx(parsed, product_name=product_name, case_id=case_id, label_images=label_images)
    except ImportError as e:
        raise HTTPException(status_code=500, detail={
            "error": "DOCX_DEP_MISSING",
            "message": f"python-docx 미설치: {e}. 'pip install python-docx'",
        })
    except Exception as e:
        logger.error(f"DOCX 생성 실패: {e}")
        raise HTTPException(status_code=500, detail={
            "error": "DOCX_BUILD_FAILED", "message": f"DOCX 생성 실패: {e}",
        })

    fname = _export_filename(product_name, case_id, "docx")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": _content_disposition(fname)},
    )


@router.get(
    "/cases/{case_id}/parsed-result/export.pdf",
    summary="OCR 분석 결과 PDF 다운로드",
)
async def export_parsed_pdf(
    case_id: str,
    selected_image_ids: str | None = Query(
        default=None,
        description="쉼표로 구분된 선택 이미지 ID. 미전달 시 전체 이미지 포함.",
    ),
):
    parsed, product_name = _fetch_parsed_for_export(case_id)
    sel_ids = set(selected_image_ids.split(",")) if selected_image_ids else None
    label_images = _fetch_label_images_for_export(case_id, selected_ids=sel_ids)
    try:
        data = build_pdf(parsed, product_name=product_name, case_id=case_id, label_images=label_images)
    except ImportError as e:
        raise HTTPException(status_code=500, detail={
            "error": "PDF_DEP_MISSING",
            "message": f"reportlab 미설치: {e}. 'pip install reportlab'",
        })
    except Exception as e:
        logger.error(f"PDF 생성 실패: {e}")
        raise HTTPException(status_code=500, detail={
            "error": "PDF_BUILD_FAILED", "message": f"PDF 생성 실패: {e}",
        })

    fname = _export_filename(product_name, case_id, "pdf")
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition(fname)},
    )


# ─────────────────────────────────────────────
# GET /cases/{case_id}/label-images — f4 연동용
#   업로드된 라벨 이미지에서 자동 크롭된 '제품 사진' 목록 조회
# ─────────────────────────────────────────────

@router.get(
    "/cases/{case_id}/label-images",
    summary="[f4 연동] 케이스의 추출된 제품 라벨 이미지 목록",
    description=(
        "수출국 라벨(doc_type='label')로 업로드된 이미지에서 Vision AI가 "
        "자동 크롭한 제품 사진 메타데이터를 반환합니다. "
        "f4(수출국표시사항 검토) 기능에서 라벨 이미지를 조회할 때 사용하세요.\n\n"
        "- cropped_storage_path: Supabase Storage의 'documents' 버킷 내 크롭 이미지 경로\n"
        "- original_storage_path: 업로드된 원본 라벨 이미지 경로\n"
        "- bbox: 원본 이미지 내 크롭 좌표 {x1, y1, x2, y2}"
    ),
)
async def list_case_label_images(case_id: str):
    sb = get_supabase()

    case_check = sb.table("cases").select("id").eq("id", case_id).execute()
    if not case_check.data:
        raise HTTPException(
            status_code=404,
            detail={"error": "CASE_NOT_FOUND", "message": "해당 건이 존재하지 않습니다."},
        )

    result = (
        sb.table("case_label_images")
        .select("*")
        .eq("case_id", case_id)
        .order("source_document_id", desc=False)  # 문서별 그룹
        .order("image_index", desc=False)          # 문서 내 순번
        .execute()
    )

    label_images = result.data or []

    # 각 이미지에 signed URL 포함 (프론트에서 별도 API 호출 불필요)
    for img in label_images:
        path = img.get("cropped_storage_path")
        if path:
            try:
                signed = sb.storage.from_(STORAGE_BUCKET).create_signed_url(path, expires_in=3600)
                img["signed_url"] = (
                    signed.get("signedURL")
                    or signed.get("signedUrl")
                    or signed.get("signed_url")
                    or ""
                )
            except Exception as e:
                logger.warning(f"라벨 이미지 signed URL 실패: {path} — {e}")
                img["signed_url"] = ""
        else:
            img["signed_url"] = ""

    return {"case_id": case_id, "label_images": label_images}


# ─────────────────────────────────────────────
# GET /cases/{case_id}/label-images/{image_id}/view — 크롭 이미지 Signed URL
# ─────────────────────────────────────────────

@router.get(
    "/cases/{case_id}/label-images/{image_id}/view",
    summary="크롭된 라벨 제품 이미지 Signed URL 발급",
)
async def get_label_image_view_url(case_id: str, image_id: str, expires_in: int = 3600):
    sb = get_supabase()

    row = (
        sb.table("case_label_images")
        .select("id, case_id, cropped_storage_path")
        .eq("id", image_id)
        .eq("case_id", case_id)
        .execute()
    )
    if not row.data:
        raise HTTPException(
            status_code=404,
            detail={"error": "IMAGE_NOT_FOUND", "message": "이미지가 존재하지 않습니다."},
        )

    storage_path = row.data[0].get("cropped_storage_path")
    if not storage_path:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_STORAGE_PATH", "message": "저장 경로가 없습니다."},
        )

    try:
        signed = sb.storage.from_(STORAGE_BUCKET).create_signed_url(
            storage_path, expires_in=expires_in
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "SIGNED_URL_FAILED", "message": f"URL 발급 실패: {e}"},
        )

    url = signed.get("signedURL") or signed.get("signed_url") or signed.get("signedUrl")
    if not url:
        raise HTTPException(
            status_code=500,
            detail={"error": "SIGNED_URL_EMPTY", "message": "URL 추출 실패"},
        )

    return {"image_id": image_id, "url": url, "expires_in": expires_in}


# ─────────────────────────────────────────────
# GET /documents/{doc_id}/view — 업로드된 문서 열기 (Signed URL)
# ─────────────────────────────────────────────

@router.get(
    "/documents/{doc_id}/view",
    summary="업로드된 문서 보기용 Signed URL 발급",
    description="Storage가 private이므로 짧은 유효시간의 signed URL을 생성해 반환합니다.",
)
async def get_document_view_url(doc_id: str, expires_in: int = 3600):
    sb = get_supabase()

    doc_result = sb.table("documents").select("*").eq("id", doc_id).execute()
    if not doc_result.data:
        raise HTTPException(
            status_code=404,
            detail={"error": "DOC_NOT_FOUND", "message": "해당 문서가 존재하지 않습니다."},
        )
    doc = doc_result.data[0]
    storage_path = doc.get("storage_path")
    if not storage_path:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_STORAGE_PATH", "message": "저장 경로가 없습니다."},
        )

    try:
        signed = sb.storage.from_(STORAGE_BUCKET).create_signed_url(
            storage_path, expires_in=expires_in
        )
    except Exception as e:
        logger.error(f"Signed URL 발급 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "SIGNED_URL_FAILED", "message": f"URL 발급 실패: {e}"},
        )

    url = signed.get("signedURL") or signed.get("signed_url") or signed.get("signedUrl")
    if not url:
        raise HTTPException(
            status_code=500,
            detail={"error": "SIGNED_URL_EMPTY", "message": "URL 추출 실패", "raw": signed},
        )

    return {
        "doc_id": doc_id,
        "file_name": doc.get("file_name"),
        "mime_type": doc.get("mime_type"),
        "url": url,
        "expires_in": expires_in,
    }


# ─────────────────────────────────────────────
# DELETE /documents/{doc_id} — 업로드된 문서 개별 삭제
# ─────────────────────────────────────────────

@router.delete(
    "/documents/{doc_id}",
    summary="업로드된 문서 삭제",
    description="documents 테이블 레코드 + Supabase Storage 파일을 함께 제거합니다.",
)
async def delete_document(doc_id: str):
    sb = get_supabase()

    doc_result = sb.table("documents").select("*").eq("id", doc_id).execute()
    if not doc_result.data:
        raise HTTPException(
            status_code=404,
            detail={"error": "DOC_NOT_FOUND", "message": "해당 문서가 존재하지 않습니다."},
        )
    doc = doc_result.data[0]
    storage_path = doc.get("storage_path")

    # Storage 파일 제거 (실패해도 DB는 정리)
    if storage_path:
        try:
            sb.storage.from_(STORAGE_BUCKET).remove([storage_path])
        except Exception as e:
            logger.warning(f"Storage 파일 삭제 실패(무시): {storage_path} — {e}")

    try:
        sb.table("documents").delete().eq("id", doc_id).execute()
    except Exception as e:
        logger.error(f"documents DELETE 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "DB_DELETE_FAILED", "message": f"문서 삭제 실패: {e}"},
        )

    logger.info(f"문서 삭제 완료: doc_id={doc_id}")
    return {"deleted": True, "doc_id": doc_id}


# ─────────────────────────────────────────────
# GET /cases/{case_id}/documents — 업로드된 문서 목록 조회
# ─────────────────────────────────────────────

@router.get(
    "/cases/{case_id}/documents",
    summary="업로드된 문서 목록 조회",
    description="해당 건에 업로드된 모든 서류 목록을 반환합니다 (페이지 재진입 시 상태 복원용).",
)
async def list_documents(case_id: str):
    """documents 테이블에서 case_id로 조회하여 업로드된 문서 목록 반환."""
    sb = get_supabase()

    case_check = sb.table("cases").select("id").eq("id", case_id).execute()
    if not case_check.data:
        raise HTTPException(
            status_code=404,
            detail={"error": "CASE_NOT_FOUND", "message": "해당 건이 존재하지 않습니다."},
        )

    docs_result = (
        sb.table("documents")
        .select("id, case_id, doc_type, file_name, mime_type, created_at")
        .eq("case_id", case_id)
        .order("created_at", desc=False)
        .execute()
    )

    return {"case_id": case_id, "documents": docs_result.data or []}

# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "application/vnd.hancom.hwp",
    "application/vnd.hancom.hwpx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/octet-stream",  # HWP fallback
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

STORAGE_BUCKET = "documents"


# ─────────────────────────────────────────────
# POST /cases/{case_id}/upload
# ─────────────────────────────────────────────

@router.post(
    "/cases/{case_id}/upload",
    response_model=UploadResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
    },
    summary="서류 파일 업로드",
    description="검역 건에 필수 서류(원재료배합비율표, 제조공정도, MSDS, 라벨)를 업로드합니다.",
)
async def upload_document(
    case_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    doc_type: DocType = Form(...),
):
    """파일을 받아 Supabase Storage에 저장하고 documents 테이블에 기록."""

    sb = get_supabase()

    # 1) case_id 유효성 확인
    case_check = sb.table("cases").select("id").eq("id", case_id).execute()
    if not case_check.data:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "CASE_NOT_FOUND",
                "message": "해당 건이 존재하지 않습니다.",
                "feature": 0,
            },
        )

    # 2) 파일 크기 검증
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail={
                "error": "FILE_TOO_LARGE",
                "message": f"파일 크기가 {MAX_FILE_SIZE // (1024*1024)}MB를 초과합니다.",
                "feature": 0,
            },
        )

    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "FILE_EMPTY",
                "message": "빈 파일은 업로드할 수 없습니다.",
                "feature": 0,
            },
        )

    # 3) MIME 타입 정규화 — 확장자 기반으로 보정 (Windows가 octet-stream으로 보내는 경우 대비)
    EXT_TO_MIME = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "hwp": "application/vnd.hancom.hwp",
        "hwpx": "application/vnd.hancom.hwpx",
    }
    file_ext = (
        file.filename.rsplit(".", 1)[-1].lower()
        if "." in (file.filename or "") else "bin"
    )
    mime_type = EXT_TO_MIME.get(file_ext, file.content_type or "application/octet-stream")

    # 4) 저장 경로 생성
    doc_id = str(uuid.uuid4())
    storage_path = f"cases/{case_id}/documents/{doc_id}.{file_ext}"

    logger.info(
        f"Storage 업로드 시도: path={storage_path}, mime={mime_type}, size={len(file_bytes)} bytes"
    )

    # 5) Supabase Storage에 업로드
    try:
        sb.storage.from_(STORAGE_BUCKET).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": mime_type},
        )
    except Exception as e:
        # Supabase Storage 에러를 좀 더 자세히 로깅
        err_str = str(e)
        logger.error(
            f"Storage 업로드 실패: file={file.filename}, ext={file_ext}, "
            f"mime={mime_type}, size={len(file_bytes)}, err={err_str!r}"
        )
        # 자주 발생하는 케이스 친절 메시지
        hint = ""
        if "mime" in err_str.lower() or "content-type" in err_str.lower():
            hint = " (버킷의 Allowed MIME types 설정을 확인하세요.)"
        elif "size" in err_str.lower() or "exceed" in err_str.lower():
            hint = " (버킷의 File size limit 설정을 확인하세요.)"
        elif "not found" in err_str.lower() or "bucket" in err_str.lower():
            hint = " (Supabase에 'documents' 버킷이 있는지 확인하세요.)"
        raise HTTPException(
            status_code=500,
            detail={
                "error": "STORAGE_UPLOAD_FAILED",
                "message": f"파일 저장에 실패했습니다: {err_str}{hint}",
                "feature": 0,
            },
        )

    # 6) documents 테이블에 레코드 삽입
    try:
        sb.table("documents").insert({
            "id": doc_id,
            "case_id": case_id,
            "doc_type": doc_type.value,
            "file_name": file.filename or "unknown",
            "storage_path": storage_path,
            "mime_type": mime_type,
        }).execute()
    except Exception as e:
        logger.error(f"documents 테이블 INSERT 실패: {e}")
        # Storage에 올라간 파일 정리 시도
        try:
            sb.storage.from_(STORAGE_BUCKET).remove([storage_path])
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail={
                "error": "DB_INSERT_FAILED",
                "message": f"문서 정보 저장에 실패했습니다: {str(e)}",
                "feature": 0,
            },
        )

    logger.info(f"파일 업로드 완료: case={case_id}, doc_type={doc_type.value}, file={file.filename}")

    # ─── 라벨 이미지 자동 처리 (f4 연동) ───
    # doc_type='label' 이면 이미지(png/jpg/jpeg/webp/gif/bmp/tiff) 또는 PDF를
    # 백그라운드에서 페이지별로 Vision 분석 + 제품 사진 크롭.
    # 실패해도 업로드 응답에는 영향 없음. 결과는 case_label_images 테이블에 저장됨.
    _LABEL_PROCESSABLE = (
        mime_type.startswith("image/")
        or mime_type in {"application/pdf", "application/x-pdf"}
        or mime_type in {
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
        }
        or file_ext in {"png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff", "pdf", "xlsx", "xls", "xlsm"}
    )
    if doc_type == DocType.LABEL and _LABEL_PROCESSABLE:
        # FastAPI BackgroundTasks: 응답 전송 후 안전하게 실행됨
        # (asyncio.create_task 보다 안정적 — 예외도 서버 로그에 기록됨)
        _label_bytes_copy = bytes(file_bytes)  # 클로저 캡처용 복사본
        _label_filename = file.filename or ""

        async def _run_label_processing():
            try:
                await process_label_image(
                    case_id=case_id,
                    source_document_id=doc_id,
                    image_bytes=_label_bytes_copy,
                    mime_type=mime_type,
                    original_storage_path=storage_path,
                    sb=sb,
                    filename=_label_filename,
                )
            except Exception as e:
                logger.warning(f"라벨 자동 처리 실패(무시): {e}")

        background_tasks.add_task(_run_label_processing)

    return UploadResponse(
        doc_id=doc_id,
        file_name=file.filename or "unknown",
        storage_path=storage_path,
        doc_type=doc_type,
        mime_type=mime_type,
        created_at=datetime.now(timezone.utc),
    )


# ─────────────────────────────────────────────
# POST /cases/{case_id}/parse
# ─────────────────────────────────────────────

@router.post(
    "/cases/{case_id}/parse",
    response_model=ParseResponse,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    summary="업로드 서류 OCR + AI 파싱",
    description="해당 건의 모든 업로드 서류를 OCR로 텍스트 추출한 뒤, Claude AI로 구조화된 데이터를 생성합니다.",
)
async def parse_documents(case_id: str, background_tasks: BackgroundTasks):
    """업로드된 서류를 OCR → LLM 파싱하여 구조화된 JSON을 반환."""

    sb = get_supabase()

    # 1) 건 존재 확인
    case_result = sb.table("cases").select("*").eq("id", case_id).execute()
    if not case_result.data:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "CASE_NOT_FOUND",
                "message": "해당 건이 존재하지 않습니다.",
            },
        )
    case_row = case_result.data[0]
    product_name_hint = case_row.get("product_name", "")

    # 2) 업로드된 문서 목록 조회
    docs_result = sb.table("documents").select("*").eq("case_id", case_id).execute()
    documents = docs_result.data or []

    if not documents:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "NO_DOCUMENTS",
                "message": "업로드된 서류가 없습니다. 먼저 파일을 업로드해주세요.",
                "feature": 0,
            },
        )

    # 3) doc_type별 OCR 텍스트 추출
    raw_texts: dict[str, str] = {}
    extraction_errors: list[str] = []

    for doc in documents:
        doc_type = doc["doc_type"]
        file_name = doc["file_name"]
        mime_type = doc.get("mime_type", "application/octet-stream")
        storage_path = doc["storage_path"]

        # Supabase Storage에서 파일 다운로드
        try:
            file_bytes = sb.storage.from_(STORAGE_BUCKET).download(storage_path)
        except Exception as e:
            err_msg = f"{file_name}: Storage 다운로드 실패 — {e}"
            logger.warning(err_msg)
            extraction_errors.append(err_msg)
            continue

        if not file_bytes:
            err_msg = f"{file_name}: 파일 바이트 없음"
            logger.warning(err_msg)
            extraction_errors.append(err_msg)
            continue

        logger.info(f"파일 다운로드 완료: {file_name} ({len(file_bytes)} bytes)")

        try:
            text = await extract_text_from_file(file_bytes, file_name, mime_type)
        except Exception as e:
            err_msg = f"{file_name}: 텍스트 추출 실패 — {e}"
            logger.warning(err_msg)
            extraction_errors.append(err_msg)
            continue

        if text:
            # 같은 doc_type의 여러 파일이 있을 경우 텍스트 병합
            if doc_type in raw_texts:
                raw_texts[doc_type] += f"\n\n---\n\n{text}"
            else:
                raw_texts[doc_type] = text
        else:
            extraction_errors.append(f"{file_name}: 추출된 텍스트 없음")

    if not raw_texts:
        error_details = "\n".join(extraction_errors) if extraction_errors else "원인 불명"
        return ParseResponse(
            case_id=case_id,
            status=ParseStatus.ERROR,
            error_message=f"모든 서류의 텍스트 추출에 실패했습니다.\n{error_details}",
        )

    # 4) Claude LLM 파싱
    try:
        parsed_result = await parse_raw_texts_to_structured(
            raw_texts=raw_texts,
            product_name_hint=product_name_hint,
        )
    except ValueError as e:
        logger.error(f"LLM 파싱 실패: {e}")
        return ParseResponse(
            case_id=case_id,
            status=ParseStatus.ERROR,
            error_message=str(e),
        )
    except Exception as e:
        logger.error(f"LLM 파싱 중 예기치 않은 오류: {e}")
        return ParseResponse(
            case_id=case_id,
            status=ParseStatus.ERROR,
            error_message=f"AI 파싱 중 오류가 발생했습니다: {str(e)}",
        )

    # 5) 파싱 결과를 documents 테이블의 parsed_md에 저장
    for doc in documents:
        doc_type = doc["doc_type"]
        if doc_type in raw_texts:
            try:
                sb.table("documents") \
                    .update({"parsed_md": raw_texts[doc_type]}) \
                    .eq("id", doc["id"]).execute()
            except Exception as e:
                logger.warning(f"parsed_md 업데이트 실패: doc_id={doc['id']} — {e}")

    # 6) pipeline_steps에 AI 결과 저장 (step_key='0')
    try:
        sb.table("pipeline_steps").upsert({
            "case_id": case_id,
            "step_key": "0",
            "step_name": "입력 및 OCR 파싱",
            "status": "completed",
            "ai_result": parsed_result.model_dump(),
        }, on_conflict="case_id,step_key").execute()
    except Exception as e:
        logger.warning(f"pipeline_steps 저장 실패: {e}")

    # 7) cases 테이블의 current_step을 '0'(파싱 완료)으로 업데이트
    try:
        sb.table("cases") \
            .update({"current_step": "0"}) \
            .eq("id", case_id).execute()
    except Exception as e:
        logger.warning(f"cases current_step 업데이트 실패: {e}")

    logger.info(f"파싱 완료: case={case_id}, 성분 {len(parsed_result.ingredients)}개 추출")

    # 8) 라벨 이미지 강제 재처리 (parse 호출 = 재분석 의도 → 기존 기록 삭제 후 다시 추출)
    label_docs = [d for d in documents if d.get("doc_type") == "label"]
    if label_docs:
        # 기존 case_label_images 기록 삭제 (dedup 해시 포함) → 새로 처리
        try:
            sb.table("case_label_images").delete().eq("case_id", case_id).execute()
            logger.info(f"라벨 이미지 기존 기록 삭제 완료: case={case_id}")
        except Exception as e:
            logger.warning(f"라벨 이미지 기록 삭제 실패(무시): {e}")

        for label_doc in label_docs:
            _ldoc = label_doc  # 클로저 캡처

            async def _reprocess_label(doc=_ldoc):
                try:
                    doc_bytes = sb.storage.from_(STORAGE_BUCKET).download(doc["storage_path"])
                    if not doc_bytes:
                        return
                    await process_label_image(
                        case_id=case_id,
                        source_document_id=doc["id"],
                        image_bytes=doc_bytes,
                        mime_type=doc.get("mime_type", "application/octet-stream"),
                        original_storage_path=doc["storage_path"],
                        sb=sb,
                        filename=doc.get("file_name", ""),
                    )
                    logger.info(f"라벨 이미지 재처리 완료: doc={doc['id']}")
                except Exception as e:
                    logger.warning(f"라벨 이미지 재처리 실패(무시): doc={doc.get('id')} — {e}")

            background_tasks.add_task(_reprocess_label)

    return ParseResponse(
        case_id=case_id,
        status=ParseStatus.COMPLETED,
        parsed_result=parsed_result,
        raw_texts=raw_texts,
        extraction_errors=extraction_errors,
        parsed_at=datetime.now(timezone.utc),
    )
