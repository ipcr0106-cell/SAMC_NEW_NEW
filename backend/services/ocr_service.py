"""
SAMC 수입식품 검역 AI — OCR / 텍스트 추출 서비스

파일 유형별 텍스트 추출 전략:
  - PDF       → PyMuPDF(fitz) 텍스트 추출 + fallback: 이미지 페이지는 Vision OCR
  - 이미지     → base64 인코딩 후 Vision API로 텍스트 인식
  - HWP/HWPX → parser-service (kordoc, Node.js) HTTP 호출
  - Excel     → openpyxl로 셀 데이터 읽기

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  임시 전환 안내 (TEMPORARY — 개발/테스트용):
    Vision OCR은 현재 OpenAI(gpt-4o)를 사용합니다.
    최종 통합 단계에서는 반드시 Claude Vision으로 롤백할 것.
    (검색 키워드: "# >>> OPENAI TEMP")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from __future__ import annotations

import base64
import io
import logging
import os
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

PARSER_SERVICE_URL = os.getenv("F0_PARSER_SERVICE_URL", "http://localhost:3001")
PARSER_SERVICE_TOKEN = os.getenv("F0_PARSER_SERVICE_TOKEN", "")


async def extract_text_from_file(
    file_bytes: bytes,
    file_name: str,
    mime_type: str,
    doc_type: str = "",
) -> str:
    """파일 바이트에서 Raw 텍스트를 추출하는 디스패처.

    Args:
        file_bytes: 파일 바이너리 데이터
        file_name: 원본 파일명 (확장자 판별용)
        mime_type: MIME 타입
        doc_type: 문서 유형 ('process', 'ingredients', 'msds', 'label' 등)
                  'process'이면 제조공정 흐름도 전용 OCR 프롬프트 사용

    Returns:
        추출된 Raw 텍스트 문자열
    """
    ext = Path(file_name).suffix.lower()
    logger.info(f"텍스트 추출 시작: {file_name} (ext={ext}, mime={mime_type}, doc_type={doc_type}, size={len(file_bytes)}bytes)")

    text = ""
    if ext == ".pdf":
        text = await _extract_from_pdf(file_bytes, doc_type=doc_type)
    elif ext in (".hwp", ".hwpx"):
        text = await _extract_from_hwp(file_bytes, file_name)
    elif ext in (".xlsx", ".xls"):
        text = _extract_from_excel(file_bytes)
    elif ext == ".docx":
        text = _extract_from_docx(file_bytes)
    elif ext in (".png", ".jpg", ".jpeg", ".webp"):
        text = await _extract_from_image(file_bytes, mime_type, doc_type=doc_type)
    else:
        logger.warning(f"지원하지 않는 파일 형식: {ext} ({file_name})")
        return ""

    if text:
        logger.info(f"텍스트 추출 성공: {file_name} → {len(text)}자")
    else:
        logger.warning(f"텍스트 추출 결과 없음: {file_name}")

    return text


# ─────────────────────────────────────────────
# PDF 추출 (PyMuPDF)
# ─────────────────────────────────────────────

async def _extract_from_pdf(file_bytes: bytes, doc_type: str = "") -> str:
    """PyMuPDF로 텍스트 추출. 텍스트 레이어가 없는 스캔 PDF는 이미지 fallback.

    제조공정도(doc_type='process')는 텍스트 레이어가 있어도 흐름도 구조를
    파악하기 어려우므로, 텍스트가 너무 짧으면 Vision OCR로 재처리한다.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error("PyMuPDF(fitz)가 설치되지 않았습니다. pip install PyMuPDF")
        return ""

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages_text: list[str] = []
    image_pages: list[int] = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text").strip()

        # 제조공정도: 텍스트가 있어도 흐름도 구조가 누락될 수 있음
        # → 텍스트가 300자 미만이면 Vision OCR로 재처리
        # 라벨: 이미지 위주이므로 텍스트 레이어가 있어도 Vision OCR 우선 사용
        if doc_type == "process" and text and len(text) < 300:
            logger.info(f"공정도 페이지 {page_num+1}: 텍스트 레이어({len(text)}자) 너무 짧음 → Vision OCR 재처리")
            image_pages.append(page_num)
        elif doc_type == "label" and text and len(text) < 500:
            logger.info(f"라벨 페이지 {page_num+1}: 텍스트 레이어({len(text)}자) 부족 → Vision OCR 재처리")
            image_pages.append(page_num)
        elif text:
            pages_text.append(f"--- 페이지 {page_num + 1} ---\n{text}")
        else:
            # 텍스트 레이어 없음 → 이미지로 변환하여 OCR 대기열에 추가
            image_pages.append(page_num)

    # 이미지 페이지 Vision OCR
    for page_num in image_pages:
        page = doc[page_num]
        pix = page.get_pixmap(dpi=300)
        img_bytes = pix.tobytes("png")
        ocr_text = await _extract_from_image(img_bytes, "image/png", doc_type=doc_type)
        if ocr_text:
            pages_text.append(f"--- 페이지 {page_num + 1} (OCR) ---\n{ocr_text}")

    doc.close()
    return "\n\n".join(pages_text)


# ─────────────────────────────────────────────
# HWP/HWPX 추출 (parser-service 경유)
# ─────────────────────────────────────────────

async def _extract_from_hwp(file_bytes: bytes, file_name: str) -> str:
    """parser-service (Node.js + kordoc)에 HTTP 요청하여 HWP 텍스트 추출."""
    url = f"{PARSER_SERVICE_URL}/parse"
    headers = {}
    if PARSER_SERVICE_TOKEN:
        headers["Authorization"] = f"Bearer {PARSER_SERVICE_TOKEN}"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {"file": (file_name, io.BytesIO(file_bytes), "application/octet-stream")}
            response = await client.post(url, files=files, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get("text", "")
    except httpx.HTTPStatusError as e:
        logger.error(f"parser-service 응답 오류: {e.response.status_code}")
        return ""
    except httpx.ConnectError:
        logger.error(f"parser-service 연결 실패: {PARSER_SERVICE_URL}")
        return ""


# ─────────────────────────────────────────────
# Excel 추출 (openpyxl)
# ─────────────────────────────────────────────

def _extract_from_excel(file_bytes: bytes) -> str:
    """openpyxl로 엑셀 전체 시트를 텍스트로 변환."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        logger.error("openpyxl이 설치되지 않았습니다. pip install openpyxl")
        return ""

    wb = load_workbook(filename=io.BytesIO(file_bytes), read_only=True, data_only=True)
    all_text: list[str] = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows: list[str] = [f"[시트: {sheet_name}]"]
        for row in ws.iter_rows(values_only=True):
            cells = [str(cell) if cell is not None else "" for cell in row]
            if any(cells):
                rows.append(" | ".join(cells))
        all_text.append("\n".join(rows))

    wb.close()
    return "\n\n".join(all_text)


# ─────────────────────────────────────────────
# DOCX 추출 (python-docx)
# ─────────────────────────────────────────────

def _extract_from_docx(file_bytes: bytes) -> str:
    """python-docx로 Word 문서의 본문 + 표 텍스트 추출."""
    try:
        from docx import Document
    except ImportError:
        logger.error("python-docx가 설치되지 않았습니다. pip install python-docx")
        return ""

    try:
        doc = Document(io.BytesIO(file_bytes))
    except Exception as e:
        logger.error(f"DOCX 파일 열기 실패: {e}")
        return ""

    parts: list[str] = []

    # 본문 단락
    for para in doc.paragraphs:
        txt = (para.text or "").strip()
        if txt:
            parts.append(txt)

    # 표
    for t_idx, table in enumerate(doc.tables, start=1):
        parts.append(f"[표 {t_idx}]")
        for row in table.rows:
            cells = [(cell.text or "").strip() for cell in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))

    return "\n".join(parts)


# ─────────────────────────────────────────────
# 이미지 OCR (Vision API)
# ─────────────────────────────────────────────

_OCR_PROMPT = (
    "이 이미지에 포함된 모든 텍스트를 빠짐없이 정확하게 추출해주세요.\n\n"
    "【중요 지침】\n"
    "1. 글씨가 작거나 밀집되어 있어도 반드시 모든 항목을 추출하세요. 절대 생략하지 마세요.\n"
    "2. 제조공정도나 흐름도(Flow Chart)의 경우: 박스·화살표·단계 번호를 포함한 "
    "모든 공정 단계를 순서대로 나열하세요. 몇 개인지 세어서 전부 추출했는지 확인하세요.\n"
    "3. 표(Table)가 있다면 Markdown 표 형태로 변환하고, 셀 내용을 하나도 빠뜨리지 마세요.\n"
    "4. 다단 레이아웃(2단, 3단)은 왼쪽→오른쪽 순서로 읽으세요.\n"
    "5. 읽기 어려운 부분은 [불명확]으로 표시하되, 주변 맥락으로 유추 가능하면 괄호 안에 유추 내용을 함께 적으세요.\n"
    "6. 언어는 원문 그대로 유지하세요 (한국어·영어·중국어 등 혼용 그대로).\n"
    "7. 이미지 장식 요소(로고, 테두리 선 등)는 무시하고 텍스트만 추출하세요."
)

# 수출국 라벨 전용 OCR 프롬프트
_LABEL_OCR_PROMPT = (
    "이 이미지는 수출국 식품 라벨(Label / Etiqueta)입니다.\n\n"
    "【필수 추출 항목 — 빠짐없이 모두 추출하세요】\n"
    "1. 제품명 (Product Name / Nombre del Producto)\n"
    "2. 제조사/브랜드명 (Manufacturer / Marca)\n"
    "3. 수출국·원산지 (Country of Origin / País de Origen)\n"
    "4. 내용량 (Net Weight / Contenido Neto) — 예: 500mL, 750ml, 1kg\n"
    "5. 알코올 도수 (Alcohol % / ALC. BY VOL.) — 주류인 경우\n"
    "6. 원재료 목록 (Ingredients / Ingredientes) — 표기된 원재료 전부 나열\n"
    "7. 영양 성분 표 (Nutrition Facts / Información Nutricional) — 표 전체 텍스트\n"
    "8. 경고 문구 / 주의 사항 (Warnings / Advertencias) — 예: 임산부 주의, 알레르기 정보\n"
    "9. 유통기한·제조일자 (Best Before / Fecha de Caducidad) — 날짜 형식 그대로\n"
    "10. 바코드·인증 마크 옆 텍스트 (Kosher, Organic, EU Organic 등)\n"
    "11. 그 외 라벨에 인쇄된 모든 텍스트 (소문자, 작은 글씨도 포함)\n\n"
    "【추출 형식】\n"
    "- 각 항목을 '항목명: 내용' 형식으로 줄별로 정리하세요.\n"
    "- 다국어(스페인어·영어·일본어 등) 표기는 원문 그대로 유지하세요.\n"
    "- 읽기 어려운 부분은 [불명확]으로 표시하되, 맥락으로 유추 가능하면 괄호 안에 추가하세요.\n"
    "- 라벨 뒷면·옆면이 보이면 앞면과 구분하여 '=== 뒷면 ===' 처럼 구분 표시하세요."
)

# 제조공정도 전용 OCR 프롬프트
_PROCESS_DIAGRAM_OCR_PROMPT = (
    "이 이미지는 식품 제조공정 흐름도(Flow Chart / Diagrama de flujo)입니다.\n\n"
    "【필수 추출 항목 — 하나도 빠짐없이】\n"
    "1. 번호가 붙은 공정 박스를 모두 찾아 번호 순서대로 나열하세요.\n"
    "   - 형식: '번호. 공정명 (번역: 한국어명)'\n"
    "   - 예: '1. Reception MP (번역: 원료 수령)', '2. Bake (번역: 굽기)'\n"
    "   - 마지막 번호까지 전부 포함하세요. 중간에 절대 생략하지 마세요.\n"
    "2. 각 공정 단계에 투입되는 원재료·보조재료(화살표로 연결된 옆 박스)도 기재하세요.\n"
    "   - 형식: '   → 투입: Water(물), Yeast(효모)'\n"
    "3. 각 공정에서 나오는 부산물/폐기물(옆으로 빠지는 화살표)도 기재하세요.\n"
    "   - 형식: '   → 배출: Bagasse(바가스)'\n"
    "4. 분기 조건(Diamond 모양 결정 박스)도 포함하세요.\n"
    "   - 형식: '   → 분기: Barrel maturation? Yes→8번, No→다음'\n"
    "5. 스페인어·영어 등 외국어는 원문 + 한국어 번역을 병기하세요.\n\n"
    "【최종 점검】\n"
    "- 추출 완료 후 '총 N개 공정 추출'을 마지막 줄에 명시하세요.\n"
    "- 이미지에서 세어본 공정 박스 수와 추출 수가 일치해야 합니다.\n"
    "- 이미지 장식 요소(로고, 테두리, 범례)는 무시하고 공정 내용만 추출하세요."
)


async def _extract_from_image(image_bytes: bytes, mime_type: str, doc_type: str = "") -> str:
    """이미지 Vision OCR 디스패처.

    doc_type='process'이면 제조공정 흐름도 전용 프롬프트(_PROCESS_DIAGRAM_OCR_PROMPT) 사용.

    ⚠️ 현재(임시): OpenAI gpt-4o Vision 사용
    ⚠️ 최종(복원): Claude Vision (_extract_from_image_claude) 로 교체
    """
    # 지원 MIME 타입 보정
    media_type = mime_type
    if media_type not in ("image/png", "image/jpeg", "image/webp", "image/gif"):
        media_type = "image/png"

    # doc_type에 따라 전용 프롬프트 선택
    if doc_type == "process":
        prompt = _PROCESS_DIAGRAM_OCR_PROMPT
    elif doc_type == "label":
        prompt = _LABEL_OCR_PROMPT
    else:
        prompt = _OCR_PROMPT

    # >>> OPENAI TEMP — 최종 통합 시 _extract_from_image_claude 로 교체
    return await _extract_from_image_openai(image_bytes, media_type, prompt=prompt)
    # return await _extract_from_image_claude(image_bytes, media_type, prompt=prompt)
    # <<< OPENAI TEMP


# ─────────────────────────────────────────────
# >>> OPENAI TEMP — 최종 통합 시 제거 가능
# ─────────────────────────────────────────────

async def _extract_from_image_openai(image_bytes: bytes, media_type: str, prompt: str = "") -> str:
    """OpenAI gpt-4o Vision으로 이미지 텍스트 추출 — 개발/테스트용 임시 구현."""
    openai_api_key = os.getenv("F0_OPENAI_API_KEY", "")
    if not openai_api_key:
        logger.error("F0_OPENAI_API_KEY가 설정되지 않았습니다.")
        return ""

    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.error("openai 패키지가 설치되지 않았습니다. pip install openai")
        return ""

    b64_data = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{media_type};base64,{b64_data}"
    model = os.getenv("F0_OPENAI_MODEL", "gpt-4o")
    ocr_prompt = prompt or _OCR_PROMPT

    try:
        client = AsyncOpenAI(api_key=openai_api_key)
        completion = await client.chat.completions.create(
            model=model,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": ocr_prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
        )
        return completion.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"OpenAI Vision OCR 실패: {e}")
        return ""

# <<< OPENAI TEMP END


# ─────────────────────────────────────────────
# --- CLAUDE ORIGINAL (최종 통합 시 사용) ---
# ─────────────────────────────────────────────

async def _extract_from_image_claude(image_bytes: bytes, media_type: str, prompt: str = "") -> str:
    """Claude Vision으로 이미지 텍스트 추출 — 최종 프로덕션용."""
    anthropic_api_key = os.getenv("F0_ANTHROPIC_API_KEY", "")
    if not anthropic_api_key:
        logger.error("F0_ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        return ""

    b64_data = base64.b64encode(image_bytes).decode("utf-8")
    ocr_prompt = prompt or _OCR_PROMPT

    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=anthropic_api_key)
        message = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64_data,
                            },
                        },
                        {"type": "text", "text": ocr_prompt},
                    ],
                }
            ],
        )
        return message.content[0].text
    except Exception as e:
        logger.error(f"Claude Vision OCR 실패: {e}")
        return ""
