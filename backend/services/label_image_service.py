"""
SAMC — 수출국 라벨 이미지 처리 서비스.

흐름:
  1) 업로드된 라벨 파일(doc_type='label') 바이트를 받음
  2) 파일 형식 정규화 (이미지: PIL 정규화, PDF: PyMuPDF 페이지별 렌더링)
  3) 중복 감지: MD5 해시로 동일 케이스 내 재업로드 스킵
  4) Vision AI(OpenAI gpt-4o)로 2가지 작업 동시 수행:
       a) 제품 사진 영역 bbox 검출
       b) 라벨 텍스트 추출 (제품명/원재료/내용량/원산지/제조사/케이스넘버)
  5) PIL로 bbox 크롭 → PNG 저장
  6) Supabase Storage + case_label_images 테이블에 기록

⚠️  임시: Vision은 OpenAI 사용. 최종 통합 시 Claude Vision으로 교체.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)

STORAGE_BUCKET = "documents"


# ─────────────────────────────────────────────
# Vision 프롬프트 — bbox + 텍스트 추출 한 번에
# ─────────────────────────────────────────────

_COMBINED_PROMPT = """이 수출국 라벨 이미지를 분석해서 아래 두 가지를 JSON으로 반환하세요.

반드시 아래 JSON 형식만 반환하세요 (다른 텍스트 없이):
{
  "bbox": {
    "found": true,
    "x1": 0, "y1": 0, "x2": 0, "y2": 0
  },
  "texts": {
    "product_name": "",
    "ingredients": "",
    "content_volume": "",
    "origin": "",
    "manufacturer": "",
    "case_number": ""
  }
}

[bbox 규칙]
- 실제 제품 사진(포토그래픽 이미지) 영역의 절대 픽셀 좌표
- 로고/텍스트/배경/영양성분표 제외. 없으면 "found": false, x1~x2 모두 0
- 여러 개면 가장 큰 것 하나. 약간 여유(padding)를 둬서 잘리지 않게.

[texts 규칙]
- product_name: 제품명 (브랜드명 포함)
- ingredients: 원재료 목록 (쉼표 구분 원문 그대로)
- content_volume: 내용량 (예: "500ml", "1kg")
- origin: 원산지 / 제조국
- manufacturer: 제조사명
- case_number: 케이스 번호 / 품목 코드 (없으면 빈 문자열)
- 해당 항목이 라벨에 없으면 빈 문자열 ""로 반환
"""


async def _analyze_label(image_bytes: bytes) -> dict[str, Any]:
    """Vision API로 bbox 검출 + 텍스트 추출 동시 수행."""
    api_key = os.getenv("F0_OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("F0_OPENAI_API_KEY 없음 — 라벨 분석 스킵")
        return {"bbox": {"found": False}, "texts": {}}

    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.error("openai 패키지 미설치")
        return {"bbox": {"found": False}, "texts": {}}

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:image/png;base64,{b64}"
    model = os.getenv("F0_OPENAI_MODEL", "gpt-4o")

    client = AsyncOpenAI(api_key=api_key)
    try:
        completion = await client.chat.completions.create(
            model=model,
            max_tokens=512,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": _COMBINED_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }],
        )
        raw = completion.choices[0].message.content or "{}"
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"라벨 Vision 분석 실패: {e}")
        return {"bbox": {"found": False}, "texts": {}}


# ─────────────────────────────────────────────
# PIL 크롭
# ─────────────────────────────────────────────

def _crop(image_bytes: bytes, bbox: dict) -> tuple[bytes, int, int]:
    """PIL로 크롭. (cropped_png_bytes, width, height) 반환."""
    try:
        from PIL import Image
    except ImportError:
        logger.error("Pillow 미설치")
        return b"", 0, 0

    img = Image.open(io.BytesIO(image_bytes))
    iw, ih = img.size
    try:
        x1 = max(0, int(bbox.get("x1", 0)))
        y1 = max(0, int(bbox.get("y1", 0)))
        x2 = min(iw, int(bbox.get("x2", iw)))
        y2 = min(ih, int(bbox.get("y2", ih)))
    except Exception:
        return b"", 0, 0

    if x2 <= x1 or y2 <= y1:
        logger.warning(f"유효하지 않은 bbox: {bbox}")
        return b"", 0, 0

    cropped = img.crop((x1, y1, x2, y2)).convert("RGB")
    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    return buf.getvalue(), cropped.width, cropped.height


# ─────────────────────────────────────────────
# 파일 형식 정규화
# ─────────────────────────────────────────────

_VISION_IMAGE_MIMES = {
    "image/png", "image/jpeg", "image/jpg", "image/webp",
    "image/gif", "image/bmp", "image/tiff",
}
_PDF_MIMES = {"application/pdf", "application/x-pdf"}
_EXCEL_MIMES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}
_EXCEL_EXTS = {"xlsx", "xls", "xlsm"}


def _normalize_image_for_vision(image_bytes: bytes) -> bytes:
    """PIL로 PNG 정규화."""
    try:
        from PIL import Image
    except ImportError:
        return image_bytes
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"이미지 정규화 실패: {e}")
        return image_bytes


def _pdf_pages_to_pngs(pdf_bytes: bytes, *, dpi: int = 200, max_pages: int = 10) -> list[bytes]:
    """PDF 페이지별 PNG 변환 (PyMuPDF)."""
    try:
        import fitz
    except ImportError:
        logger.error("PyMuPDF 미설치 — pip install PyMuPDF")
        return []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        logger.warning(f"PDF 열기 실패: {e}")
        return []

    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    out: list[bytes] = []
    try:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            try:
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                out.append(pix.tobytes("png"))
            except Exception as e:
                logger.warning(f"PDF 페이지 {i} 렌더링 실패: {e}")
    finally:
        doc.close()
    return out


def _excel_embedded_images(excel_bytes: bytes) -> list[bytes]:
    """Excel 파일 안에 embed된 이미지 바이트 리스트 추출 (openpyxl).

    xlsx 워크시트에 삽입된 이미지(Insert > Picture)를 모두 뽑아
    PNG로 정규화해서 반환합니다.
    """
    try:
        import openpyxl
    except ImportError:
        logger.error("openpyxl 미설치 — pip install openpyxl")
        return []

    try:
        wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), data_only=True)
    except Exception as e:
        logger.warning(f"Excel 열기 실패: {e}")
        return []

    images: list[bytes] = []
    for ws in wb.worksheets:
        ws_images = getattr(ws, "_images", [])
        for img_obj in ws_images:
            try:
                raw = img_obj._data()  # 원본 이미지 바이트 (PNG/JPEG 등)
                if not raw:
                    continue
                norm = _normalize_image_for_vision(raw)
                if norm:
                    images.append(norm)
            except Exception as e:
                logger.warning(f"Excel 이미지 추출 실패: {e}")

    logger.info(f"Excel에서 이미지 {len(images)}개 추출")
    return images


def _file_to_page_images(file_bytes: bytes, mime_type: str, filename: str = "") -> list[bytes]:
    """파일 → 페이지별 PNG 리스트."""
    mime = (mime_type or "").lower()
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if mime in _VISION_IMAGE_MIMES or mime.startswith("image/") or ext in {
        "png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff",
    }:
        norm = _normalize_image_for_vision(file_bytes)
        return [norm] if norm else []

    if mime in _PDF_MIMES or ext == "pdf":
        pages = _pdf_pages_to_pngs(file_bytes)
        if not pages:
            logger.info("PDF 페이지 없음")
        return pages

    if mime in _EXCEL_MIMES or ext in _EXCEL_EXTS:
        imgs = _excel_embedded_images(file_bytes)
        if not imgs:
            logger.info("Excel에 embed 이미지 없음")
        return imgs

    logger.info(f"라벨 처리 스킵: 지원하지 않는 형식 (mime={mime}, ext={ext})")
    return []


# ─────────────────────────────────────────────
# 중복 감지
# ─────────────────────────────────────────────

def _compute_hash(file_bytes: bytes) -> str:
    """원본 파일 MD5 해시 (dedup용)."""
    return hashlib.md5(file_bytes).hexdigest()


def _is_duplicate(sb, case_id: str, source_hash: str) -> bool:
    """같은 케이스에 동일 파일이 이미 처리됐는지 확인."""
    try:
        result = (
            sb.table("case_label_images")
            .select("id")
            .eq("case_id", case_id)
            .eq("source_hash", source_hash)
            .limit(1)
            .execute()
        )
        return bool(result.data)
    except Exception as e:
        logger.warning(f"dedup 체크 실패 (무시): {e}")
        return False


# ─────────────────────────────────────────────
# DB 저장
# ─────────────────────────────────────────────

async def _save_crop_record(
    *,
    sb,
    case_id: str,
    source_document_id: str,
    original_storage_path: str,
    source_hash: str,
    image_index: int,          # 동일 파일 내 몇 번째 이미지 (0-based)
    cropped_bytes: bytes,
    bbox: dict,
    width: int,
    height: int,
    texts: dict,
) -> Optional[str]:
    """크롭 PNG Storage 업로드 + case_label_images INSERT.

    image_index: 동일 source_hash(파일) 내 순번. 여러 장 저장 시 충돌 방지.
    """
    new_id = str(uuid.uuid4())
    cropped_path = f"cases/{case_id}/label_products/{new_id}.png"

    try:
        sb.storage.from_(STORAGE_BUCKET).upload(
            path=cropped_path,
            file=cropped_bytes,
            file_options={"content-type": "image/png"},
        )
    except Exception as e:
        logger.error(f"크롭 이미지 Storage 업로드 실패: {e}")
        return None

    record: dict = {
        "id": new_id,
        "case_id": case_id,
        "source_document_id": source_document_id,
        "cropped_storage_path": cropped_path,
        "original_storage_path": original_storage_path,
        "source_hash": source_hash,
        "image_index": image_index,   # 파일 내 순번 (정렬·dedup용)
        "bbox": bbox or None,         # page 정보는 bbox JSONB에서 제거 (image_index로 대체)
        "width": width,
        "height": height,
        # 텍스트 추출 결과
        "label_product_name":   texts.get("product_name") or None,
        "label_ingredients":    texts.get("ingredients") or None,
        "label_content_volume": texts.get("content_volume") or None,
        "label_origin":         texts.get("origin") or None,
        "label_manufacturer":   texts.get("manufacturer") or None,
        "label_case_number":    texts.get("case_number") or None,
        "extracted_texts":      texts if texts else None,
    }

    try:
        sb.table("case_label_images").insert(record).execute()
    except Exception as e:
        logger.error(f"case_label_images INSERT 실패 (image_index={image_index}): {e}")
        return cropped_path  # Storage 파일은 남아있음

    logger.info(
        f"라벨 이미지 저장: case={case_id}, idx={image_index}, "
        f"size={width}x{height}, product={texts.get('product_name', '-')}"
    )
    return cropped_path


# ─────────────────────────────────────────────
# 엔트리 포인트
# ─────────────────────────────────────────────

async def process_label_image(
    *,
    case_id: str,
    source_document_id: str,
    image_bytes: bytes,
    mime_type: str,
    original_storage_path: str,
    sb,
    filename: str = "",
) -> Optional[list[str]]:
    """라벨 파일 업로드 후 자동 호출.

    지원 형식: png, jpg, jpeg, webp, gif, bmp, tiff, pdf
    - 중복 파일 재업로드 시 스킵 (MD5 기반 dedup)
    - 페이지별로 Vision 분석 → 제품 사진 크롭 + 텍스트 추출
    - 결과: case_label_images 테이블에 저장 (이미지당 1행)

    Returns:
        저장된 크롭 경로 리스트. 중복이거나 처리 실패면 None.
    """
    # 1) 중복 감지
    source_hash = _compute_hash(image_bytes)
    if _is_duplicate(sb, case_id, source_hash):
        logger.info(f"중복 라벨 스킵: case={case_id}, hash={source_hash[:8]}...")
        return None

    # 2) 파일 → 페이지 이미지 리스트
    pages = _file_to_page_images(image_bytes, mime_type, filename)
    if not pages:
        return None

    saved_paths: list[str] = []
    image_index = 0  # 이 파일 내에서 실제로 저장된 이미지 순번

    for idx, page_bytes in enumerate(pages):
        # 3) Vision 분석 (bbox + 텍스트 한 번에)
        try:
            analysis = await _analyze_label(page_bytes)
        except Exception as e:
            logger.warning(f"image {idx}: Vision 분석 예외 — {e}")
            analysis = {"bbox": {"found": False}, "texts": {}}

        bbox_info = analysis.get("bbox", {})
        texts = analysis.get("texts", {}) or {}

        has_bbox = bbox_info.get("found") and any(
            bbox_info.get(k, 0) != 0 for k in ["x2", "y2"]
        )

        if has_bbox:
            bbox = {k: bbox_info[k] for k in ["x1", "y1", "x2", "y2"] if k in bbox_info}
            cropped_bytes, cw, ch = _crop(page_bytes, bbox)
        else:
            # bbox 없으면 원본 전체 이미지로 저장
            # → Vision 실패/API키 없어도 사용자가 직접 확인 가능
            logger.info(f"image {idx}: bbox 없음 — 원본 이미지 저장")
            cropped_bytes = page_bytes
            try:
                from PIL import Image
                img = Image.open(io.BytesIO(page_bytes))
                cw, ch = img.size
            except Exception:
                cw, ch = 0, 0
            bbox = {}

        if not cropped_bytes:
            logger.warning(f"image {idx}: 저장할 이미지 바이트 없음 — 스킵")
            continue

        # 4) 저장 — image_index로 동일 파일 내 순번 기록
        path = await _save_crop_record(
            sb=sb,
            case_id=case_id,
            source_document_id=source_document_id,
            original_storage_path=original_storage_path,
            source_hash=source_hash,
            image_index=image_index,
            cropped_bytes=cropped_bytes,
            bbox=bbox,
            width=cw,
            height=ch,
            texts=texts,
        )
        if path:
            saved_paths.append(path)
            image_index += 1  # 성공한 것만 카운트

    if not saved_paths:
        logger.info(f"라벨 {source_document_id}: 저장된 이미지 없음")
        return None

    return saved_paths
