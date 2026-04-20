"""
기능4: 수출국 표시사항 검토 — API 라우터

엔드포인트:
  POST   /api/v1/cases/{case_id}/pipeline/feature/4/analyze   ← 분석 실행 (테스트용)
  GET    /api/v1/cases/{case_id}/pipeline/feature/4           ← 결과 조회
  POST   /api/v1/cases/{case_id}/pipeline/feature/4/validate  ← 선택 항목 법령 정합성 검토
  PATCH  /api/v1/cases/{case_id}/pipeline/feature/4           ← final_result 저장
  POST   /api/v1/cases/{case_id}/pipeline/feature/4/confirm   ← 확인 완료

[처리 흐름]
  analyze → (사용자 체크) → validate → (사용자 확인) → PATCH → confirm

[테스트 모드]
  - case_id: 임의 UUID 사용 가능 (DB에 없어도 동작)
  - label_text: 라벨 텍스트 직접 입력 (OCR 없이 테스트)
  - food_type / ingredients: F1·F2 완성 전 mock 값 입력
"""

import io
import json
import os
import platform
import re
import sys
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fpdf import FPDF
from pinecone import Pinecone
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from supabase import create_client

# db/feature4 경로를 모듈로 사용 (preprocess_laws.check_any_law_updating)
_DB_F4_DIR = str(Path(__file__).parent.parent / "db" / "feature4")
if _DB_F4_DIR not in sys.path:
    sys.path.insert(0, _DB_F4_DIR)

try:
    from preprocess_laws import check_any_law_updating as _check_any_law_updating
except ImportError:
    _check_any_law_updating = None  # 모듈 없으면 무시

load_dotenv()  # backend/.env 통합 사용

router = APIRouter(prefix="/api/v1/cases/{case_id}/pipeline/feature/4", tags=["feature4"])

# =============================================================
# OCR 연동 — f0의 pipeline_steps(step_key='0') ai_result에서 조회
#
# f0 스키마 (schemas/upload.py ParsedResult):
#   basic_info:   { product_name, export_country, ... }
#   ingredients:  [{ name, ratio, origin, ins_number, cas_number }]
#   label_info:   { label_texts: [...], export_country, warnings: [...] }
#   process_info: { process_codes, ... }
# =============================================================

# 라벨 이미지 메타 테이블 (크롭된 제품 이미지)
_LABEL_IMAGES_TABLE = "case_label_images"
_LABEL_IMAGES_COLUMNS = {
    "case_id":              "case_id",
    "source_document_id":   "source_document_id",
    "cropped_storage_path": "cropped_storage_path",
    "image_id":             "id",
}

# Supabase Storage 버킷 (크롭 이미지 다운로드용)
_STORAGE_BUCKET = "documents"


# =============================================================
# 클라이언트 싱글톤
# =============================================================

_clients: dict = {}


def _get_clients() -> dict:
    if _clients:
        return _clients

    required = ["F4_PINECONE_API_KEY", "F4_PINECONE_HOST", "SUPABASE_URL", "SUPABASE_SERVICE_KEY", "F4_OPENAI_API_KEY"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise RuntimeError(f".env 누락: {missing}")

    pc = Pinecone(api_key=os.getenv("F4_PINECONE_API_KEY"))
    _clients["index"]    = pc.Index(host=os.getenv("F4_PINECONE_HOST"))
    _clients["supabase"] = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
    _clients["model"]    = SentenceTransformer("intfloat/multilingual-e5-large")
    _clients["claude"]   = OpenAI(api_key=os.getenv("F4_OPENAI_API_KEY"))
    return _clients


# =============================================================
# OCR 연동: DB에서 서류 정보 / 라벨 이미지 자동 조회
# =============================================================

def _fetch_f0_parsed(supabase, case_id: str) -> dict | None:
    """f0의 OCR 파싱 결과를 pipeline_steps(step_key='0')에서 조회."""
    try:
        res = (
            supabase.table("pipeline_steps")
            .select("ai_result")
            .eq("case_id", case_id)
            .eq("step_key", "0")
            .limit(1)
            .execute()
        )
        if res.data and res.data[0].get("ai_result"):
            return res.data[0]["ai_result"]
    except Exception:
        pass
    return None


def _fetch_doc_ocr(supabase, case_id: str) -> dict:
    """회사 제출 서류 OCR 결과 → f0 pipeline_steps에서 추출.

    f0 ParsedResult 구조:
      basic_info.product_name, ingredients[].name, ingredients[].origin 등
    """
    parsed = _fetch_f0_parsed(supabase, case_id)
    if not parsed:
        return {}

    basic = parsed.get("basic_info", {})
    ingredients_list = parsed.get("ingredients", [])

    # 원재료: 이름 목록을 콤마 구분 문자열로 변환
    ingredient_names = ", ".join(
        item.get("name", "") for item in ingredients_list if item.get("name")
    )
    # 원산지: 첫 번째 원재료의 origin 또는 basic_info의 export_country
    origin = ""
    for item in ingredients_list:
        if item.get("origin"):
            origin = item["origin"]
            break
    if not origin:
        origin = basic.get("export_country", "")

    return {
        "product_name":   basic.get("product_name", ""),
        "ingredients":    ingredient_names,
        "content_volume": "",  # f0 ParsedResult에 내용량 필드 없음 — 추후 확장
        "origin":         origin,
        "manufacturer":   "",  # f0 ParsedResult에 제조사 필드 없음 — 추후 확장
    }


def _fetch_label_ocr(supabase, case_id: str) -> dict:
    """라벨 이미지 OCR 텍스트 → f0 pipeline_steps + case_label_images에서 추출.

    1차: pipeline_steps(step_key='0')의 label_info에서 텍스트 추출
    2차: case_label_images 테이블의 Vision 텍스트 추출 결과 보충
         (xlsx 등에서 추출된 이미지별 텍스트가 여기에 저장됨)
    """
    parsed = _fetch_f0_parsed(supabase, case_id)

    label_text = ""
    product_name = ""
    ingredient_names = ""
    content_volume = ""
    origin = ""
    manufacturer = ""

    if parsed:
        label = parsed.get("label_info", {})
        basic = parsed.get("basic_info", {})
        ingredients_list = parsed.get("ingredients", [])

        label_texts = label.get("label_texts", [])
        label_text = "\n".join(label_texts) if label_texts else ""

        product_name = basic.get("product_name", "")
        ingredient_names = ", ".join(
            item.get("name", "") for item in ingredients_list if item.get("name")
        )
        origin = label.get("export_country", "") or basic.get("export_country", "")

    # case_label_images에서 Vision 텍스트 추출 결과 보충
    # (xlsx 라벨 파일의 이미지별 텍스트가 여기에 저장됨)
    try:
        res = (
            supabase.table(_LABEL_IMAGES_TABLE)
            .select("label_product_name,label_ingredients,label_content_volume,label_origin,label_manufacturer,extracted_texts")
            .eq("case_id", case_id)
            .order("image_index")
            .execute()
        )
        if res.data:
            label_image_texts = []
            for row in res.data:
                # 각 이미지의 추출 텍스트를 label_text에 합산
                et = row.get("extracted_texts") or {}
                parts = []
                for field in ["product_name", "ingredients", "content_volume", "origin", "manufacturer", "certification_marks"]:
                    val = et.get(field, "")
                    if val:
                        parts.append(f"{field}: {val}")
                if parts:
                    label_image_texts.append("\n".join(parts))

                # 비어있는 필드 보충
                if not product_name and row.get("label_product_name"):
                    product_name = row["label_product_name"]
                if not ingredient_names and row.get("label_ingredients"):
                    ingredient_names = row["label_ingredients"]
                if not content_volume and row.get("label_content_volume"):
                    content_volume = row["label_content_volume"]
                if not origin and row.get("label_origin"):
                    origin = row["label_origin"]
                if not manufacturer and row.get("label_manufacturer"):
                    manufacturer = row["label_manufacturer"]

            # pipeline_steps에 label_text가 없으면 이미지 Vision 결과로 대체
            if not label_text and label_image_texts:
                label_text = "\n\n---\n\n".join(label_image_texts)
    except Exception:
        pass

    return {
        "label_text":     label_text,
        "product_name":   product_name,
        "ingredients":    ingredient_names,
        "content_volume": content_volume,
        "origin":         origin,
        "manufacturer":   manufacturer,
    }


def _fetch_label_images(supabase, case_id: str) -> list[dict]:
    """
    라벨 이미지 목록을 DB에서 조회.
    동일 파일(source_hash + image_index)에서 추출된 이미지를 모두 반환.
    source_hash 기준 dedup: 같은 파일이 재업로드된 경우만 최신 것 유지.

    각 항목에 full_page_path 포함: 크롭 전 전체 이미지 (인증마크·성분표·디자인 분석용).
    """
    try:
        cols = _LABEL_IMAGES_COLUMNS
        res = (
            supabase.table(_LABEL_IMAGES_TABLE)
            .select(f"{cols['image_id']},{cols['source_document_id']},{cols['cropped_storage_path']},full_page_storage_path,source_hash,image_index")
            .eq(cols["case_id"], case_id)
            .order("created_at", desc=True)
            .execute()
        )
        if not res.data:
            return []

        # source_hash + image_index 기준 dedup (같은 파일의 같은 이미지만 중복 제거)
        seen_keys: set = set()
        deduped: list[dict] = []
        for row in res.data:
            source_hash = row.get("source_hash", "")
            image_index = row.get("image_index", 0)
            dedup_key = f"{source_hash}:{image_index}" if source_hash else ""
            if dedup_key and dedup_key in seen_keys:
                continue
            if dedup_key:
                seen_keys.add(dedup_key)

            deduped.append({
                "image_id":       row.get(cols["image_id"]),
                "storage_path":   row.get(cols["cropped_storage_path"]) or "",
                "full_page_path": row.get("full_page_storage_path") or "",
            })
        return deduped
    except Exception:
        return []


def _download_image_bytes(supabase, storage_path: str) -> bytes | None:
    """Supabase Storage에서 이미지 바이트 다운로드."""
    try:
        return supabase.storage.from_(_STORAGE_BUCKET).download(storage_path)
    except Exception:
        return None


def _create_signed_url(supabase, storage_path: str, expires_in: int = 3600) -> str | None:
    """Supabase Storage에서 Signed URL 생성 (Vision API 전달용)."""
    try:
        result = supabase.storage.from_(_STORAGE_BUCKET).create_signed_url(storage_path, expires_in)
        return result.get("signedURL") or result.get("signedUrl")
    except Exception:
        return None


# =============================================================
# 요청 / 응답 스키마
# =============================================================

class AnalyzeRequest(BaseModel):
    label_text: str = ""                   # 비어있으면 f0 OCR에서 자동 조회
    food_type: str = "미분류"              # 비어있으면 F2에서 자동 조회
    ingredients: list[str] = []           # 비어있으면 F1에서 자동 조회
    label_image_url: str | None = None    # 비어있으면 case_label_images에서 자동 조회
    doc_product_name: str = ""
    doc_content_volume: str = ""
    doc_origin: str = ""
    doc_manufacturer: str = ""
    doc_ingredients: str = ""


class ValidateRequest(BaseModel):
    selected_issues: list[dict]            # 사용자가 체크한 텍스트 위반 항목
    selected_image_issues: list[dict] = [] # 사용자가 체크한 이미지 위반 항목


class UpdateRequest(BaseModel):
    final_result: dict                     # 사용자가 체크한 항목만 담긴 Feature4Result
    edit_reason: str = ""


# =============================================================
# 분석 로직
# =============================================================

_ANALYSIS_PROMPT = """\
당신은 한국 식품 표시·광고 법령 전문가입니다.
아래 정보를 바탕으로 수출국 라벨의 법령 위반 여부를 분석해 주세요.

[식품 유형]
{food_type}

[원재료 목록]
{ingredients}

[앞선 파이프라인(F0~F3) 검증 결과 — 이미 확인된 사실]
{pipeline_context}

[라벨 전체 텍스트]
{label_text}

[라벨 이미지에서 감지된 시각 요소]
{detected_visual_elements}

[참고 법령 조문]
{law_chunks}

[금지 표현 키워드 목록]
{prohibited_keywords}

[핵심 판정 원칙]
1. **증거 우선**: 라벨 텍스트 또는 감지된 시각 요소에서 **직접 확인된 것만** 위반으로 판정하세요.
   - "~일 수 있다", "~가능성이 있다", "뒷면에 있을 수 있다"는 위반 근거가 아닙니다.
   - 제공된 자료에 없는 것은 판정 대상이 아닙니다.
   - 위반 요소가 하나도 확인되지 않으면 반드시 overall을 "pass"로 설정하세요.
2. **severity 기준**:
   - "must_fix": 라벨에서 금지 표현/이미지가 **명확히 확인됨** + 해당 법령 조항과 직접 매칭됨
   - "review_needed": 위반 요소는 **실제로 검출**됐으나 맥락 해석이 필요함
   - 확신이 없으면 must_fix가 아니라 review_needed. 검출된 증거가 없으면 아예 보고하지 마세요.
3. [앞선 파이프라인 검증 결과]에 이미 확인된 정보는 사실로 간주하세요.
4. **위반이 아닌 것**:
   - 법령에서 의무적으로 표시하도록 요구하는 문구(음주 경고문, 알레르기 경고문, "19세 미만 판매 금지" 등)는 위반이 아닙니다. 이런 의무 경고문을 "질병 치료 효능 오인"이나 "부당 표시"로 판정하지 마세요.
   - 수출국 법령에 따른 정상적인 규격 표기(NOM, CRT, D.O.P. 등 원산지 인증 코드)는 허위 인증이 아닙니다.
   - 제품의 일반적 외형(병 모양, 뚜껑, 내용물 색상)은 위반 요소가 아닙니다.

[분석 범위]
- 라벨 텍스트에서 금지 표현 키워드 또는 법령상 금지된 유사 표현 검출
- 감지된 시각 요소(인증 마크, 의료 그래픽 등)와 법령 조항 매칭
- category: {categories}

[law_excerpt 작성 규칙]
- [참고 법령 조문]에서 해당 위반의 **구체적인 규정 내용**(~해야 한다, ~하여서는 아니 된다)을 원문 그대로 인용하세요.
- 절대 수정·요약·의역하지 마세요.
- "가. 제품명" 같은 목차/제목만 인용하지 마세요.
- [참고 법령 조문]에 해당 내용이 없으면 빈 문자열로 두세요.

[reason 작성 규칙]
- "확인이 필요합니다", "판단이 불가능합니다" 같은 표현 금지.
- 형식: "[문제점] ~이 ~에 위반됩니다. [해결방법] ~를 ~로 수정/삭제하세요."

반드시 아래 JSON 형식으로만 응답하세요.
{{
  "overall": "pass" | "fail" | "review_needed",
  "issues": [
    {{
      "text": "라벨에서 검출된 문제 표현 원문 또는 시각 요소 설명",
      "evidence": "이 판정의 근거가 된 실제 증거 (라벨 텍스트 원문 또는 감지된 시각 요소명)",
      "location": "라벨 상 위치",
      "reason": "무엇이 문제이고 어떻게 해결해야 하는지",
      "law_ref": "근거 법령 조문명",
      "law_excerpt": "참고 법령 조문 원문 인용 (없으면 빈 문자열)",
      "severity": "must_fix | review_needed"
    }}
  ]
}}
"""

_CROSS_CHECK_PROMPT = """\
라벨에 표기된 내용과 회사 제출 서류의 내용을 비교하여 불일치 항목을 찾아주세요.

[라벨 텍스트]
{label_text}

[회사 제출 서류 정보]
- 제품명: {doc_product_name}
- 내용량: {doc_content_volume}
- 원산지: {doc_origin}
- 제조사: {doc_manufacturer}
- 원재료: {doc_ingredients}

반드시 아래 JSON 배열 형식으로만 응답하세요.
[
  {{
    "field": "product_name" | "ingredients" | "content_volume" | "origin" | "manufacturer",
    "label_value": "라벨에 표기된 값 (없으면 빈 문자열)",
    "doc_value": "서류의 값 (없으면 빈 문자열)",
    "match": true | false,
    "note": "불일치 설명 (일치하면 빈 문자열)"
  }}
]
"""


_IMAGE_ANALYSIS_PROMPT = """\
당신은 식품 라벨 이미지에서 시각 요소를 추출하는 분석기입니다.
아래 이미지에서 **실제로 보이는** 시각 요소만 객관적으로 보고하세요.

[핵심 원칙]
1. **이미지에서 직접 보이는 것만 보고하세요.** 보이지 않는 것을 추측하거나 만들어내지 마세요.
2. **"~처럼 보인다", "~연상된다", "~가능성이 있다"는 보고 대상이 아닙니다.** 명확히 식별된 요소만 보고하세요.
3. **이미지에 없는 요소로 판정하지 마세요.** "뒷면에 뭐가 있을 수 있다", "다른 면에서 확인 필요"는 보고 대상이 아닙니다.
4. **제품 자체의 일반적 외형(병, 캔, 뚜껑, 내용물 색상)은 위반 요소가 아닙니다.**
5. 아무 문제도 없으면 반드시 **빈 배열 []** 을 반환하세요. 없는 문제를 만들어내지 마세요.

[추출 대상 — 이미지에서 아래 요소가 **명확히** 보이는 경우에만 보고]
- 인증·수상·허가 마크/로고 (텍스트 포함): KOSHER, HALAL, USDA Organic, HACCP, FDA, ISO 등
- 의료·과학 관련 그래픽: 주사기, 수액백, 청진기, X-ray, 세포 이미지, 임상 그래프 등
- 건강 효능 암시 그래픽: 비포/애프터 비교, 신체 부위 치료/회복 도안, 영양소 수치 그래프 등
- 국기·원산지 관련 심볼: 국기 이미지, 랜드마크, "Made in ~" 표기와 불일치하는 이미지

반드시 아래 JSON 배열 형식으로만 응답하세요.
[
  {{
    "element": "이미지에서 실제로 보이는 요소 (예: 'KOSHER PARVE 원형 녹색 마크', '주사기 일러스트')",
    "location": "라벨 상 위치 (예: 우측 상단, 중앙 하단)",
    "element_type": "mark|medical_graphic|health_claim_graphic|origin_symbol|other",
    "text_in_element": "요소 안에 읽을 수 있는 텍스트 (없으면 빈 문자열)",
    "confidence": "high|medium (high: 명확히 식별됨, medium: 해상도/각도 등으로 부분적 식별)"
  }}
]
"""


# 이미지 분석 프롬프트 캐시 (법령 업데이트 시 _invalidate_prompt_cache()로 무효화)
_prompt_cache: dict = {}


def _invalidate_prompt_cache() -> None:
    """법령 업데이트 후 admin_laws.py에서 호출하여 프롬프트 캐시 무효화."""
    _prompt_cache.clear()


def _build_image_prompt(supabase) -> str:
    """
    f4_image_violation_types에서 활성(is_active=True) + 검토 보류(is_active=False) 유형을
    모두 읽어 단일 프롬프트 생성.

    - 활성 유형: 정상 분석 → review_level="confirmed"
    - 검토 보류 유형: 낮은 신뢰도 분석 → review_level="suggested"
      (AI가 확실히 판단 못 하면 reasoning에 "직접 확인 필요"로 표시)
    DB에 유형이 전혀 없으면 하드코딩 _IMAGE_ANALYSIS_PROMPT로 폴백.
    """
    if "prompt" in _prompt_cache:
        return _prompt_cache["prompt"]

    res = (
        supabase.table("f4_image_violation_types")
        .select("type_name, sub_items, default_severity, severity_condition, law_ref, is_active")
        .order("created_at")
        .execute()
    )

    if not res.data:
        _prompt_cache["prompt"] = _IMAGE_ANALYSIS_PROMPT
        return _IMAGE_ANALYSIS_PROMPT

    circled = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚"

    confirmed_lines = []
    suggested_lines = []

    for i, t in enumerate(res.data):
        num = circled[i] if i < len(circled) else f"({i+1})"
        sev_note = f" [기본 severity: {t['default_severity']}]"
        if t.get("severity_condition"):
            sev_note += f" → {t['severity_condition']}"
        sub = "\n         ".join(s.strip() for s in t["sub_items"].split(",") if s.strip())
        line = (
            f"{num} {t['type_name']}{sev_note}\n"
            f"   세부: {sub}\n"
            f"   근거: {t['law_ref']}"
        )
        if t["is_active"]:
            confirmed_lines.append(line)
        else:
            suggested_lines.append(line)

    last_num = circled[len(res.data) - 1] if len(res.data) <= len(circled) else f"({len(res.data)})"
    confirmed_block = "\n\n".join(confirmed_lines) if confirmed_lines else "없음"
    suggested_block = "\n\n".join(suggested_lines) if suggested_lines else ""

    suggested_section = ""
    if suggested_block:
        suggested_section = f"""
[검토 권고 유형 — 낮은 신뢰도 (법령 개정으로 추가된 미검증 유형)]
아래 유형들은 법령상 유효하나 자동 검증 신뢰도가 낮아 사용자 확인이 필요합니다.
이미지에서 해당 요소가 보이면 review_level="suggested"로 보고하고,
reasoning에 "AI 판단 불확실 — 직접 확인 권고"를 포함하세요.
명확히 판단 불가 시 보고하지 않아도 됩니다.

{suggested_block}
"""

    prompt = f"""\
당신은 식품 라벨 이미지에서 시각 요소를 추출하는 분석기입니다.
아래 이미지에서 **실제로 보이는** 시각 요소만 객관적으로 보고하세요.

[핵심 원칙]
1. **이미지에서 직접 보이는 것만 보고하세요.** 보이지 않는 것을 추측하거나 만들어내지 마세요.
2. **"~처럼 보인다", "~연상된다", "~가능성이 있다"는 보고 대상이 아닙니다.** 명확히 식별된 요소만 보고하세요.
3. **이미지에 없는 요소로 판정하지 마세요.** "뒷면에 뭐가 있을 수 있다"는 보고 대상이 아닙니다.
4. **제품 자체의 일반적 외형(병, 캔, 뚜껑, 내용물 색상)은 보고 대상이 아닙니다.**
5. 아무것도 감지되지 않으면 반드시 **빈 배열 []** 을 반환하세요.

[추출 대상 — 아래 유형에 해당하는 요소가 **명확히** 보이는 경우에만 보고]
{confirmed_block}
{suggested_section}

반드시 아래 JSON 배열 형식으로만 응답하세요.
[
  {{{{
    "element": "이미지에서 실제로 보이는 요소 설명",
    "location": "라벨 상 위치 (예: 우측 상단, 중앙 하단)",
    "element_type": "mark|medical_graphic|health_claim_graphic|origin_symbol|other",
    "matched_violation_type": "위 목록 중 해당 유형 번호와 이름 (해당 없으면 빈 문자열)",
    "text_in_element": "요소 안에 읽을 수 있는 텍스트 (없으면 빈 문자열)",
    "confidence": "high|medium"
  }}}}
]
"""
    _prompt_cache["prompt"] = prompt
    return prompt


def _extract_pdf_texts(supabase, case_id: str) -> list[str]:
    """documents 테이블에서 PDF 원본을 다운받아 텍스트 추출. OCR보다 정확."""
    try:
        import pdfplumber
        import tempfile

        docs = (
            supabase.table("documents")
            .select("id, doc_type, file_name, storage_path")
            .eq("case_id", case_id)
            .execute()
        )
        if not docs.data:
            return []

        texts = []
        for doc in docs.data:
            path = doc.get("storage_path", "")
            fname = doc.get("file_name", "")
            # PDF 파일만 처리
            if not (fname.lower().endswith(".pdf") or path.lower().endswith(".pdf")):
                continue
            try:
                # Supabase Storage에서 다운로드
                bucket = "documents"
                file_bytes = supabase.storage.from_(bucket).download(path)
                if not file_bytes:
                    continue
                # 임시 파일에 저장 후 pdfplumber로 텍스트 추출
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(file_bytes)
                    tmp_path = tmp.name
                with pdfplumber.open(tmp_path) as pdf:
                    page_texts = []
                    for page in pdf.pages:
                        t = page.extract_text()
                        if t and t.strip():
                            page_texts.append(t.strip())
                    if page_texts:
                        doc_label = f"[{doc.get('doc_type', 'document')}: {fname}]"
                        texts.append(f"{doc_label}\n" + "\n".join(page_texts))
                import os
                os.unlink(tmp_path)
            except Exception as e:
                print(f"[경고] PDF 텍스트 추출 실패 ({fname}): {e}")
                continue
        return texts
    except Exception as e:
        print(f"[경고] PDF 텍스트 추출 전체 실패: {e}")
        return []


def _ocr_label_image(claude: OpenAI, image_url: str) -> str:
    """OpenAI Vision으로 라벨 이미지의 모든 텍스트를 추출 (PDF 없을 때 보조 수단)."""
    try:
        resp = claude.chat.completions.create(
            model="gpt-5.4",  # OCR은 정확도가 중요하므로 full 모델 사용
            max_completion_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url},
                    },
                    {
                        "type": "text",
                        "text": (
                            "이 식품 라벨 이미지에 있는 모든 텍스트를 빠짐없이 읽어서 그대로 출력하세요.\n"
                            "- 한글, 영문, 독일어, 베트남어 등 모든 언어의 텍스트를 포함하세요.\n"
                            "- 제품명, 원재료명, 영양정보, 원산지, 제조사, 경고문, 인증마크 텍스트 등 모두 포함하세요.\n"
                            "- 줄바꿈을 유지하세요.\n"
                            "- 텍스트 외의 설명(예: '이 라벨에는...')은 쓰지 마세요. 읽은 텍스트만 출력하세요.\n"
                            "- 글자가 흐리거나 읽기 어려우면 [?]로 표시하세요. 절대 추측하지 마세요.\n"
                            "- '신장', '치료', '효능' 같은 단어가 보이면 정확히 읽었는지 재확인하세요. "
                            "'산화방지제'를 '신화'로, '원산지'를 '신장'으로 잘못 읽는 경우가 흔합니다."
                        ),
                    },
                ],
            }],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[경고] 라벨 OCR 오류: {e}")
        return ""


def _analyze_image(claude: OpenAI, image_url: str, supabase=None) -> list[dict]:
    """OpenAI Vision으로 라벨 이미지의 그림 요소 위반 분석."""
    prompt = _build_image_prompt(supabase) if supabase else _IMAGE_ANALYSIS_PROMPT
    try:
        resp = claude.chat.completions.create(
            model="gpt-5.4-mini",
            max_completion_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url},
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }],
        )
        raw = resp.choices[0].message.content.strip()
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            return []
        return json.loads(match.group())
    except Exception as e:
        print(f"[경고] 이미지 분석 오류: {e}")
        return []


_DEFAULT_CATEGORIES = ["질병치료", "허위과장", "의약품오인", "기능성"]


def _fetch_categories(supabase) -> str:
    """
    DB에서 현재 등록된 전체 카테고리 목록을 조회해 파이프 구분 문자열로 반환.
    기본 4개 + 법령 처리 과정에서 자동 추가된 카테고리 포함.
    """
    try:
        res = supabase.table("f4_prohibited_expressions").select("category").execute()
        db_cats = {row["category"] for row in (res.data or []) if row.get("category")}
        all_cats = sorted(set(_DEFAULT_CATEGORIES) | db_cats)
        return " | ".join(all_cats)
    except Exception:
        return " | ".join(_DEFAULT_CATEGORIES)


def _fetch_prohibited_keywords(supabase) -> list[dict]:
    """f4_prohibited_expressions에서 전체 키워드 목록 조회."""
    res = supabase.table("f4_prohibited_expressions").select(
        "keyword, category, severity, law_ref"
    ).execute()
    return res.data or []


def _search_law_chunks_multi(
    index, model,
    food_type: str = "",
    ingredients: list[str] = None,
    prohibited_hits: list[str] = None,
    visual_elements: list[str] = None,
    top_k_per_query: int = 5,
) -> list[str]:
    """
    구조화된 필드별로 Pinecone 검색 후 병합.

    쿼리 분리:
      ① 식품유형 + 의무표시사항 → 해당 유형 표시규정 검색
      ② 금지 키워드 + 부당 표시 금지 → 금지 조항 검색
      ③ 감지된 시각 요소(인증마크 등) + 인증 표시 → 관련 규정 검색
      ④ 원재료 + 알레르기 표시 → 알레르기 규정 검색 (조건부)
    """
    queries = []
    ft = food_type or ""

    # ═══════════════════════════════════════════
    # 공통 기본 쿼리 — 모든 식품에 항상 적용
    # ═══════════════════════════════════════════

    # 의무 표시사항 (제품명, 내용량, 원재료명, 영업소, 소비기한 등)
    queries.append("식품 표시 의무 제품명 내용량 원재료명 영업소 소비기한 표시기준")
    # 표시방법 (한글 표시, 글자 크기, 표시 위치 등)
    queries.append("식품등의 표시방법 한글 표시 글자 크기 표시 위치 주표시면")
    # 부당 표시·광고 금지 (질병 치료, 의약품 오인, 허위 과장 등)
    queries.append("부당한 표시 또는 광고 금지 질병 예방 치료 효능 의약품 오인 소비자 기만")
    # 영양 표시 (열량, 나트륨, 당류, 포화지방 등)
    queries.append("영양성분 표시 열량 나트륨 당류 포화지방 트랜스지방 표시기준")

    # ═══════════════════════════════════════════
    # 식품유형 특화 쿼리 — 해당할 때만 추가
    # ═══════════════════════════════════════════

    if ft and ft != "미분류":
        # 해당 식품유형으로 직접 검색 (어떤 유형이든)
        queries.append(f"{ft} 표시사항 표시기준 표시방법")

        # 주류
        if any(kw in ft for kw in ["주류", "증류주", "맥주", "와인", "탁주", "약주", "소주", "리큐르", "청주", "과실주"]):
            queries.append("주류 표시기준 알코올 도수 경고 문구 음주 표시 의무")
        # 건강기능식품
        if any(kw in ft for kw in ["건강기능식품", "건강기능", "기능성"]):
            queries.append("건강기능식품 표시기준 기능성 내용 섭취량 섭취방법 주의사항 의약품 아님 표시")
        # 식품첨가물
        if any(kw in ft for kw in ["식품첨가물", "첨가물", "착색료", "보존료", "감미료", "산화방지제"]):
            queries.append("식품첨가물 표시기준 용도 명칭 표시 의무")
        # 기구 및 용기·포장
        if any(kw in ft for kw in ["용기", "포장", "기구", "용기포장"]):
            queries.append("기구 용기 포장 표시기준 재질 표시 사용상 주의사항")
        # 영유아·특수용도식품
        if any(kw in ft for kw in ["영아", "영유아", "조제분유", "조제식", "이유식", "특수의료"]):
            queries.append("영유아 식품 표시기준 조제분유 조제식 특수의료용도식품 모유 대체")
        # 축산물
        if any(kw in ft for kw in ["축산", "식육", "가공육", "소시지", "햄", "유가공"]):
            queries.append("축산물 표시기준 식육 등급 원산지 표시 의무")

    # ═══════════════════════════════════════════
    # 조건부 쿼리 — 원재료/시각 요소에 따라 추가
    # ═══════════════════════════════════════════

    # 감지된 시각 요소 (인증마크 등)
    if visual_elements:
        for el in visual_elements[:3]:
            queries.append(f"{el} 인증 마크 표시 규정")

    # 알레르기 유발물질
    if ingredients and len(ingredients) > 0:
        allergen_keywords = ["대두", "밀", "달걀", "우유", "땅콩", "견과", "새우", "게", "조개", "메밀", "아황산", "호두", "잣", "아몬드"]
        if any(any(ak in ing for ak in allergen_keywords) for ing in ingredients):
            queries.append("알레르기 유발물질 표시 의무 표시기준")

    # GMO 관련
    if ingredients and len(ingredients) > 0:
        gmo_keywords = ["대두", "옥수수", "면실", "카놀라", "사탕무", "감자", "알팔파"]
        if any(any(gk in ing for gk in gmo_keywords) for ing in ingredients):
            queries.append("유전자변형식품 GMO 표시 의무 표시기준")

    # 병렬 검색 후 중복 제거
    seen_texts = set()
    all_chunks = []
    for q in queries:
        query_vec = model.encode(f"query: {q}").tolist()
        results = index.query(vector=query_vec, top_k=top_k_per_query, include_metadata=True)
        for match in (results.matches or []):
            if match.metadata and match.metadata.get("text"):
                text = match.metadata["text"]
                # 중복 제거 (앞 100자로 판별)
                key = text[:100]
                if key not in seen_texts:
                    seen_texts.add(key)
                    all_chunks.append(text)

    return all_chunks


def _search_law_chunks(index, model, query: str, top_k: int = 5) -> list[str]:
    """Pinecone에서 관련 법령 조문 검색. (레거시 호환용)"""
    query_vec = model.encode(f"query: {query}").tolist()
    results = index.query(vector=query_vec, top_k=top_k, include_metadata=True)
    chunks = []
    for match in results.matches:
        if match.metadata and match.metadata.get("text"):
            chunks.append(match.metadata["text"])
    return chunks


def _truncate_at_sentence(text: str, max_len: int = 2000) -> str:
    """문장 단위로 잘라서 중간 끊김 방지. 마지막 온전한 문장까지만 반환."""
    if len(text) <= max_len:
        return text
    # max_len 이내에서 마지막 문장 종결 위치 찾기
    truncated = text[:max_len]
    # 한국어/일반 문장 종결: 다. 요. 함. 됨. 임. 등 + 마침표/물음표/느낌표
    last_end = -1
    for end_char in ["다.", "요.", "함.", "됨.", "임.", "음.", "라.", "자.", "며,", "고,"]:
        pos = truncated.rfind(end_char)
        if pos > last_end:
            last_end = pos + len(end_char)
    # 일반 마침표
    for ch in [". ", ".\n"]:
        pos = truncated.rfind(ch)
        if pos > last_end:
            last_end = pos + 1
    if last_end > max_len // 2:
        return truncated[:last_end].strip()
    return truncated.strip() + "…"


def _extract_relevant_lines(body: str, context: str, max_lines: int = 12) -> str:
    """
    긴 법령 본문에서 context(위반 사유)와 관련된 핵심 구절만 추출.
    항/호/목 단위로 줄을 나누고, 관련성 높은 줄을 선택.
    """
    if not context:
        return body

    lines = [l.strip() for l in body.split("\n") if l.strip()]
    if len(lines) <= max_lines:
        return "\n".join(lines)

    # context에서 키워드 추출 (조사/어미 제외한 2글자 이상 단어)
    context_lower = context.lower()
    keywords = [w for w in re.findall(r"[가-힣a-zA-Z]{2,}", context_lower)]

    # 각 줄의 관련성 점수 계산
    scored = []
    for i, line in enumerate(lines):
        line_lower = line.lower()
        score = sum(1 for kw in keywords if kw in line_lower)
        # 항 시작(①②③) 또는 호 시작(1. 2. 가. 나.)은 구조적으로 중요
        if re.match(r"^[①-⑳]|^\d+\.\s|^[가-힣]\.\s", line):
            score += 0.5
        scored.append((i, line, score))

    # 점수 높은 줄 선택 + 주변 문맥 포함
    scored.sort(key=lambda x: x[2], reverse=True)
    selected_indices = set()
    for idx, _, sc in scored:
        if sc <= 0 and len(selected_indices) >= max_lines // 2:
            break
        # 해당 줄 + 앞뒤 1줄씩 포함 (문맥 유지)
        for j in range(max(0, idx - 1), min(len(lines), idx + 2)):
            selected_indices.add(j)
        if len(selected_indices) >= max_lines:
            break

    if not selected_indices:
        # 관련 줄이 없으면 앞부분만
        return "\n".join(lines[:max_lines])

    # 원래 순서 유지, 생략 구간에 ... 표시
    result = []
    prev_idx = -2
    for idx in sorted(selected_indices):
        if idx > prev_idx + 1 and prev_idx >= 0:
            result.append("  (...)")
        result.append(lines[idx])
        prev_idx = idx

    return "\n".join(result)


def _lookup_law_excerpt(index, model, law_ref: str, context: str = "") -> str:
    """Pinecone에서 법령 원문 조회 → 관련 구절만 추출.

    law_ref + context로 검색 → 본문에서 판단에 필요한 부분만 반환.
    """
    if not law_ref:
        return ""
    try:
        query = f"{law_ref} {context[:100]}" if context else law_ref
        query_vec = model.encode(f"query: {query}").tolist()
        results = index.query(vector=query_vec, top_k=15, include_metadata=True)

        for match in results.matches:
            if not match.metadata:
                continue
            text = match.metadata.get("text", "")
            if len(text) < 50:
                continue
            # 제목 부분([...]) 추출 + 본문 분리
            title_match = re.match(r"^\[(.+?)\]\s*", text)
            title = title_match.group(1) if title_match else ""
            body = text[title_match.end():].strip() if title_match else text.strip()
            if not body or len(body) < 30:
                continue
            # 관련 구절만 추출
            relevant = _extract_relevant_lines(body, context)
            excerpt = f"[{title}]\n{relevant}" if title else relevant
            return excerpt
    except Exception:
        pass
    return ""


def _attach_law_excerpts(issues: list[dict], index, model) -> None:
    """텍스트/이미지 위반 항목에 Pinecone DB에서 조회한 법령 원문을 첨부."""
    for issue in issues:
        law_ref = issue.get("law_ref", "")
        if law_ref and not issue.get("law_excerpt"):
            context = issue.get("reason", "") or issue.get("reasoning", "")
            issue["law_excerpt"] = _lookup_law_excerpt(index, model, law_ref, context)


def _apply_evidence_gate(issues: list[dict]) -> list[dict]:
    """
    후처리 게이트: 증거 없는 위반을 자동 기각.

    규칙:
    1. evidence 필드가 비어있으면 drop
    2. reason에 "확인되지 않", "판단이 어려", "불충분", "확인 불가" 포함 시 drop
    3. severity가 must_fix인데 law_excerpt가 비어있으면 review_needed로 강등
    """
    filtered = []
    for issue in issues:
        evidence = (issue.get("evidence") or "").strip()
        reason = issue.get("reason", "")
        law_excerpt = (issue.get("law_excerpt") or "").strip()

        # 1. evidence 없으면 기각
        if not evidence:
            continue

        # 2. 불확실성 표현이 reason의 핵심이면 기각
        uncertain_markers = ["확인되지 않", "판단이 어려", "불충분", "확인 불가", "확정이 어려", "판단이 불가"]
        if any(marker in reason for marker in uncertain_markers):
            # reason 전체가 불확실성이면 기각, 일부만이면 유지
            if not any(kw in reason for kw in ["위반됩니다", "삭제하세요", "수정하세요"]):
                continue

        # 3. must_fix인데 law_excerpt 없으면 강등
        if issue.get("severity") == "must_fix" and not law_excerpt:
            issue["severity"] = "review_needed"

        filtered.append(issue)

    return filtered


def _check_mandatory_labeling(
    cross_check: list[dict],
    label_text: str,
    law_chunks: list[str],
    food_type: str = "",
) -> list[dict]:
    """
    의무 표시사항 누락 검사.
    교차검증에서 label_value가 비어있는 항목 중
    법적 의무 표시사항에 해당하면 위반으로 생성.

    법령 근거는 RAG에서 가져온 law_chunks에서 동적으로 검색.
    """
    # 필드 → 표시사항명 + 검색 키워드
    FIELD_INFO = {
        "product_name":    {"name": "제품명",               "search": ["제품명", "명칭"]},
        "ingredients":     {"name": "원재료명",             "search": ["원재료명", "원료명", "원재료"]},
        "content_volume":  {"name": "내용량",               "search": ["내용량"]},
        "origin":          {"name": "원산지",               "search": ["원산지", "원산지 표시"]},
        "manufacturer":    {"name": "영업소 명칭 및 소재지", "search": ["영업소", "소재지", "제조사"]},
    }

    def _find_law_chunk(search_keywords: list[str]) -> tuple[str, str]:
        """law_chunks에서 관련 법령 근거를 찾아 (law_ref, law_excerpt) 반환."""
        best_chunk = ""
        best_score = 0
        for chunk in law_chunks:
            score = sum(1 for kw in search_keywords if kw in chunk)
            # "표시하여야 한다", "표시기준" 등이 함께 있으면 가점
            if "표시하여야" in chunk or "표시사항" in chunk:
                score += 2
            if score > best_score:
                best_score = score
                best_chunk = chunk

        if not best_chunk:
            return ("", "")

        # 제목 추출 ([법령명 조문번호] 형태)
        title_match = re.match(r"^\[(.+?)\]\s*", best_chunk)
        law_ref = title_match.group(1) if title_match else ""
        # 본문에서 관련 부분 발췌 (최대 300자)
        body = best_chunk[title_match.end():].strip() if title_match else best_chunk
        excerpt = body[:300]
        return (law_ref, excerpt)

    missing_issues = []
    for cc in cross_check:
        field = cc.get("field", "")
        label_val = (cc.get("label_value") or "").strip()
        match = cc.get("match", True)

        # label_value가 비어있고, 서류에는 있는 경우 → 누락
        if not label_val and not match and field in FIELD_INFO:
            info = FIELD_INFO[field]
            law_ref, law_excerpt = _find_law_chunk(info["search"])

            missing_issues.append({
                "text": f"의무 표시사항 누락: {info['name']}",
                "evidence": f"라벨에 {info['name']} 표기가 없음 (서류에는 '{cc.get('doc_value', '')[:60]}' 기재)",
                "location": "라벨 전체",
                "reason": f"{info['name']}은(는) 의무 표시사항입니다. 라벨에 {info['name']}을(를) 추가하세요.",
                "law_ref": law_ref,
                "law_excerpt": law_excerpt,
                "severity": "must_fix",
            })

    return missing_issues


def _call_ai(claude, prompt: str) -> dict | list:
    """AI 호출 후 JSON 파싱."""
    resp = claude.chat.completions.create(
        model="gpt-5.4-mini",
        max_completion_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.choices[0].message.content.strip()
    match = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
    if not match:
        raise ValueError(f"JSON 파싱 실패: {raw[:200]}")
    return json.loads(match.group())


_VALIDATE_PROMPT = """\
당신은 한국 식품 표시·광고 법령 전문가입니다.
사용자가 아래 위반 항목들을 선택했습니다. 이 선택에 대해 검토해 주세요.

[적용 법령 계층 구조 — 해석 우선순위]
Tier 1 (최상위): 식품 등의 표시·광고에 관한 법률 (제20826호) — 금지 원칙 규정
Tier 2: 식품 등의 표시·광고에 관한 법률 시행령 (제35734호) — 법률 위임사항 구체화
Tier 3: 식품 등의 표시·광고에 관한 법률 시행규칙 (제02004호) — 표시 방법·서식 세부기준
Tier 4 (고시):
  - 식품등의 표시기준 (제2025-60호) — 표시 항목·방법 상세 기준
  - 식품등의 한시적 기준 및 규격 인정 기준 (제2025-75호) — 임시 허용 원료
  - 식품등의 부당한 표시 또는 광고의 내용 기준 (제2025-79호) — 금지 표현 핵심
  - 부당한 표시·광고로 보지 아니하는 기능성 표시·광고에 관한 규정 (제2024-62호) — 허용 예외

[핵심 해석 원칙]
- 상위 Tier가 하위 Tier보다 우선합니다.
- 제2025-79호(금지기준)와 제2024-62호(허용예외)는 자주 충돌합니다.
  같은 표현이 79호에서 금지되더라도 62호의 조건을 충족하면 허용될 수 있습니다.
- 고시(Tier 4) 위반을 지적할 때는 근거가 되는 상위법(Tier 1~3) 조문도 함께 명시해야
  법적 효력이 생깁니다.
- 한시적 기준(제2025-75호) 해당 원료는 일반 표시기준과 별도로 판단해야 합니다.

[선택된 위반 항목]
{selected_issues}

검토 사항:
1. **충돌(conflict)**: 선택 항목들 중 서로 상충하는 조문 조합
2. **의존(dependency)**: 선택 항목 처리 시 반드시 함께 적용해야 하는 미선택 조문
3. **판단 근거(reasoning)**: 각 결과에 대해 사용자가 이해할 수 있도록
   어떤 법령 계층 원칙을 적용했는지 평이한 언어로 설명

문제가 없으면 conflicts와 dependencies를 빈 배열로 반환하세요.

반드시 아래 JSON 형식으로만 응답하세요.
{{
  "is_valid": true | false,
  "conflicts": [
    {{
      "law_refs": ["관련 조문1", "관련 조문2"],
      "description": "충돌 내용 요약",
      "reasoning": "왜 이 두 조문이 충돌하는지, 어떤 법령 계층 원칙에 따라 판단했는지 사용자가 이해할 수 있도록 설명 (예: '제2025-79호는 해당 표현을 금지하지만, 제2024-62호 제3조는 기능성 표시 허가를 받은 경우 동일 표현을 조건부 허용합니다. 허가 여부를 먼저 확인해야 합니다.')",
      "recommendation": "권고 처리 방법"
    }}
  ],
  "dependencies": [
    {{
      "selected_law_ref": "선택된 조문",
      "required_law_ref": "함께 처리해야 하는 조문",
      "description": "의존 관계 요약",
      "reasoning": "왜 이 조문이 함께 필요한지 사용자가 이해할 수 있도록 설명 (예: '고시(Tier 4) 위반만 지적하면 법적 효력이 약합니다. 상위법인 식품표시광고법 제8조제1항도 함께 명시해야 행정처분 근거가 완성됩니다.')"
    }}
  ],
  "applied_principles": "이번 검토에서 적용한 법령 해석 원칙 요약 (사용자에게 판단 배경 설명용)",
  "summary": "전체 검토 결과 한 줄 요약"
}}
"""


def _validate_selection(
    selected_issues: list[dict],
    selected_image_issues: list[dict],
    clients: dict,
) -> dict:
    """
    선택된 텍스트·이미지 위반 항목들의 법령 충돌·의존 관계 통합 검증.
    """
    all_selected = selected_issues + selected_image_issues
    if not all_selected:
        return {
            "is_valid": True,
            "conflicts": [],
            "dependencies": [],
            "summary": "선택된 항목이 없습니다.",
        }

    issues_text = "\n".join(
        f"{i+1}. [{'이미지' if item.get('description') else '텍스트'} / {item.get('severity', '')}] "
        f"{item.get('text') or item.get('description', '')} — "
        f"{item.get('law_ref', '')} ({item.get('reason') or item.get('reasoning', '')[:40]})"
        for i, item in enumerate(all_selected)
    )

    prompt = _VALIDATE_PROMPT.format(selected_issues=issues_text)
    try:
        result = _call_ai(clients["claude"], prompt)
        return result if isinstance(result, dict) else {
            "is_valid": True, "conflicts": [], "dependencies": [], "summary": ""
        }
    except Exception as e:
        return {
            "is_valid": True,
            "conflicts": [],
            "dependencies": [],
            "summary": f"검증 중 오류 발생: {e}",
        }


def _fetch_f1_result(supabase, case_id: str) -> dict | None:
    """F1 수입판정 결과를 pipeline_steps(step_key='1')에서 조회.

    PM이 임의로 추가한 파이프라인 연결입니다.
    수정/삭제하고 싶으면 이 함수와 _run_analysis 내 호출부를 제거하면 됩니다.
    """
    try:
        res = (
            supabase.table("pipeline_steps")
            .select("ai_result, final_result")
            .eq("case_id", case_id)
            .eq("step_key", "1")
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0].get("final_result") or res.data[0].get("ai_result")
    except Exception:
        pass
    return None


def _fetch_f2_result(supabase, case_id: str) -> dict | None:
    """F2 식품유형 분류 결과를 pipeline_steps(step_key='2')에서 조회.

    PM이 임의로 추가한 파이프라인 연결입니다.
    수정/삭제하고 싶으면 이 함수와 _run_analysis 내 호출부를 제거하면 됩니다.
    """
    try:
        res = (
            supabase.table("pipeline_steps")
            .select("ai_result, final_result")
            .eq("case_id", case_id)
            .eq("step_key", "2")
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0].get("final_result") or res.data[0].get("ai_result")
    except Exception:
        pass
    return None


def _build_pipeline_context(sb, case_id: str, f0_parsed: dict | None, f1: dict | None, f2: dict | None) -> str:
    """F0~F3 결과를 종합하여 F4 분석 프롬프트에 넣을 컨텍스트 문자열을 생성."""
    lines = []

    # F0: OCR 기본정보 (제품명, 원산지, 제조사, 내용량)
    if f0_parsed:
        basic = f0_parsed.get("basic_info", {})
        if basic.get("product_name"):
            lines.append(f"- 제품명: {basic['product_name']}")
        if basic.get("export_country"):
            lines.append(f"- 수출국(원산지): {basic['export_country']}")
        label = f0_parsed.get("label_info", {})
        if label.get("export_country"):
            lines.append(f"- 라벨 표기 원산지: {label['export_country']}")

    # F1: 수입판정 결과
    if f1:
        verdict = f1.get("verdict", "")
        if verdict:
            lines.append(f"- F1 수입판정: {verdict}")
        fail_reasons = f1.get("fail_reasons", [])
        if fail_reasons:
            lines.append(f"- F1 수입불가 사유: {', '.join(fail_reasons)}")
        # 원재료별 허용 여부 요약
        ingredients = f1.get("ingredients", [])
        if ingredients:
            summaries = []
            for ing in ingredients[:20]:
                name = ing.get("name", "")
                status = ing.get("status", "")
                law = ing.get("law_ref", "")
                if name:
                    s = f"{name}({status})"
                    if law:
                        s += f" 근거:{law}"
                    summaries.append(s)
            if summaries:
                lines.append(f"- F1 원재료 판정: {'; '.join(summaries)}")

    # F2: 식품유형 분류 상세
    if f2:
        food_type = f2.get("food_type", "")
        sub_type = f2.get("sub_type", "")
        if food_type:
            type_str = food_type
            if sub_type:
                type_str += f" ({sub_type})"
            lines.append(f"- F2 식품유형: {type_str}")
        if f2.get("is_alcohol") is not None:
            lines.append(f"- 주류 여부: {'주류' if f2['is_alcohol'] else '비주류'}")
        if f2.get("law_ref"):
            lines.append(f"- F2 분류 근거: {f2['law_ref']}")
        if f2.get("reasoning"):
            lines.append(f"- F2 분류 판단: {f2['reasoning'][:200]}")

    # F3: 필요서류 (있으면)
    try:
        f3_res = (
            sb.table("pipeline_steps")
            .select("ai_result, final_result")
            .eq("case_id", case_id)
            .eq("step_key", "3")
            .limit(1)
            .execute()
        )
        if f3_res.data:
            f3 = f3_res.data[0].get("final_result") or f3_res.data[0].get("ai_result")
            if f3:
                docs = f3.get("documents", [])
                if docs:
                    doc_names = [d.get("doc_name", "") for d in docs if d.get("is_mandatory")]
                    if doc_names:
                        lines.append(f"- F3 필수서류: {', '.join(doc_names[:10])}")
    except Exception:
        pass

    if not lines:
        return "앞선 파이프라인 결과 없음"
    return "\n".join(lines)


def _run_analysis(req: AnalyzeRequest, clients: dict, case_id: str = "") -> dict:
    """핵심 분석 로직: 금지 표현 감지 + 라벨·서류 교차검증 + 다중 이미지 분석."""

    sb = clients["supabase"]

    # 0. DB에서 OCR 결과 자동 조회 (req에 값이 없으면 DB fallback)
    doc_product_name   = req.doc_product_name
    doc_content_volume = req.doc_content_volume
    doc_origin         = req.doc_origin
    doc_manufacturer   = req.doc_manufacturer
    doc_ingredients    = req.doc_ingredients
    label_text         = req.label_text

    f0_parsed = None
    f1 = None
    f2 = None

    if case_id:
        # F0 파싱 결과 조회
        f0_parsed = _fetch_f0_parsed(sb, case_id)

        # ── F2 → food_type 자동 보충 ──
        f2 = _fetch_f2_result(sb, case_id)
        if req.food_type == "미분류" and f2 and f2.get("food_type"):
            req.food_type = f2["food_type"]

        # ── F1 → ingredients 자동 보충 ──
        f1 = _fetch_f1_result(sb, case_id)
        if not req.ingredients and f1:
            f1_ingredients = f1.get("ingredients") or []
            req.ingredients = [
                ing.get("name", "") for ing in f1_ingredients if ing.get("name")
            ]

        # 회사 제출 서류 OCR → 교차검증용 서류 정보 보충
        if not any([doc_product_name, doc_content_volume, doc_origin, doc_manufacturer, doc_ingredients]):
            doc_ocr = _fetch_doc_ocr(sb, case_id)
            if doc_ocr:
                doc_product_name   = doc_product_name   or doc_ocr.get("product_name", "")
                doc_content_volume = doc_content_volume or doc_ocr.get("content_volume", "")
                doc_origin         = doc_origin         or doc_ocr.get("origin", "")
                doc_manufacturer   = doc_manufacturer   or doc_ocr.get("manufacturer", "")
                doc_ingredients    = doc_ingredients    or doc_ocr.get("ingredients", "")

        # 라벨 OCR → label_text가 비어있으면 DB에서 보충
        if not label_text:
            label_ocr = _fetch_label_ocr(sb, case_id)
            if label_ocr:
                label_text = label_ocr.get("label_text", "")

    # 1.5 F4 텍스트 보충 — 2단계 전략
    #   1순위: 업로드된 PDF 원본에서 텍스트 추출 (OCR 불필요, 정확도 높음)
    #   2순위: PDF가 없으면 라벨 이미지 OCR (보조 수단)
    label_images = []
    if case_id:
        # 1순위: PDF 텍스트 추출
        pdf_texts = _extract_pdf_texts(sb, case_id)
        if pdf_texts:
            pdf_combined = "\n\n".join(pdf_texts)
            if label_text:
                label_text = label_text + "\n\n[원본 서류 텍스트]\n" + pdf_combined
            else:
                label_text = pdf_combined

        # 2순위: PDF에서 텍스트를 못 뽑았으면 이미지 OCR
        label_images = _fetch_label_images(sb, case_id)
        if not pdf_texts:
            f4_ocr_texts = []
            for img in label_images:
                signed_url = None
                if img.get("full_page_path"):
                    signed_url = _create_signed_url(sb, img["full_page_path"])
                if not signed_url:
                    signed_url = _create_signed_url(sb, img["storage_path"])
                if signed_url:
                    ocr_text = _ocr_label_image(clients["claude"], signed_url)
                    if ocr_text:
                        f4_ocr_texts.append(ocr_text)
            if f4_ocr_texts:
                f4_ocr_combined = "\n\n".join(f4_ocr_texts)
                if label_text:
                    label_text = label_text + "\n\n[F4 이미지 OCR 보충]\n" + f4_ocr_combined
                else:
                    label_text = f4_ocr_combined

    if not label_text:
        raise ValueError("label_text가 비어 있습니다. 직접 입력하거나 OCR 결과가 DB에 있어야 합니다.")

    # 파이프라인 컨텍스트 생성 (F0~F3 결과 종합)
    pipeline_context = _build_pipeline_context(sb, case_id, f0_parsed, f1, f2) if case_id else "앞선 파이프라인 결과 없음"

    # 1. 금지 키워드 목록 조회
    prohibited = _fetch_prohibited_keywords(sb)
    keyword_summary = "\n".join(
        f"- [{kw['category']} / {kw['severity']}] {kw['keyword']} ({kw['law_ref']})"
        for kw in prohibited[:80]  # 프롬프트 길이 제한
    )

    # 2. 이미지 시각 요소 추출 (판정 아닌 추출 — 텍스트 판정에 활용)
    detected_visual_elements = []

    # 2-a. request에 직접 전달된 이미지 URL (기존 호환)
    if req.label_image_url:
        detected_visual_elements.extend(
            _analyze_image(clients["claude"], req.label_image_url, sb)
        )

    # 2-b. DB 라벨 이미지로 시각 요소 추출 (label_images는 위에서 이미 조회됨)
    if case_id:
        for img in label_images:
            signed_url = None
            if img.get("full_page_path"):
                signed_url = _create_signed_url(sb, img["full_page_path"])
            if not signed_url:
                signed_url = _create_signed_url(sb, img["storage_path"])
            if signed_url:
                per_elements = _analyze_image(clients["claude"], signed_url, sb)
                for el in per_elements:
                    el["source_image_id"] = img["image_id"]
                detected_visual_elements.extend(per_elements)

    # 이미지 추출 결과 필터링 + 텍스트 정리
    # health_claim_graphic/medical_graphic은 confidence "high"만 허용
    # 곡면 병 라벨에서 일반 표시사항(원재료명 등)을 건강/치료 문구로 오독하는 문제 방지
    filtered_visual = [
        el for el in detected_visual_elements
        if not (
            el.get("element_type") in ("health_claim_graphic", "medical_graphic")
            and el.get("confidence") != "high"
        )
    ]
    if filtered_visual:
        visual_summary = "\n".join(
            f"- [{el.get('element_type', 'other')}] {el.get('element', '')} "
            f"(위치: {el.get('location', '')}, 텍스트: {el.get('text_in_element', '')}, "
            f"신뢰도: {el.get('confidence', '')})"
            for el in filtered_visual
        )
    else:
        visual_summary = "감지된 시각 요소 없음"

    # 3. 관련 법령 조문 검색 (RAG — 구조화된 필드별 쿼리)
    visual_element_names = [
        el.get("text_in_element") or el.get("element", "")
        for el in detected_visual_elements
        if el.get("confidence") == "high"
    ]
    law_chunks = _search_law_chunks_multi(
        clients["index"], clients["model"],
        food_type=req.food_type,
        ingredients=req.ingredients,
        prohibited_hits=[kw["keyword"] for kw in prohibited[:10]],
        visual_elements=visual_element_names,
    )
    law_text = "\n\n".join(law_chunks) if law_chunks else "관련 조문 없음"

    # 4. 통합 분석 — 라벨 텍스트 + 이미지 추출 결과 + 법령 청크 → AI 판정
    analysis_prompt = _ANALYSIS_PROMPT.format(
        food_type=req.food_type,
        ingredients=", ".join(req.ingredients) if req.ingredients else "없음",
        pipeline_context=pipeline_context,
        label_text=label_text,
        detected_visual_elements=visual_summary,
        law_chunks=law_text,
        prohibited_keywords=keyword_summary,
        categories=_fetch_categories(sb),
    )
    analysis_result = _call_ai(clients["claude"], analysis_prompt)

    # 5. 라벨 ↔ 서류 교차검증 (서류 정보가 하나라도 있을 때만)
    has_doc_info = any([doc_product_name, doc_content_volume, doc_origin, doc_manufacturer, doc_ingredients])
    cross_check = []
    if has_doc_info:
        cross_prompt = _CROSS_CHECK_PROMPT.format(
            label_text=label_text,
            doc_product_name=doc_product_name or "정보 없음",
            doc_content_volume=doc_content_volume or "정보 없음",
            doc_origin=doc_origin or "정보 없음",
            doc_manufacturer=doc_manufacturer or "정보 없음",
            doc_ingredients=doc_ingredients or "정보 없음",
        )
        cross_check = _call_ai(clients["claude"], cross_prompt)

    # 6. 후처리 게이트 — evidence 없는 위반 자동 기각
    text_issues = analysis_result.get("issues", [])
    text_issues = _apply_evidence_gate(text_issues)

    # 7. 의무 표시사항 누락 검사 — 교차검증에서 라벨에 없는 항목을 위반으로 추가
    #    법령 근거는 RAG에서 가져온 law_chunks에서 동적 검색
    if cross_check:
        missing_issues = _check_mandatory_labeling(cross_check, label_text, law_chunks, req.food_type)
        text_issues.extend(missing_issues)

    # overall 판정
    if any(i.get("severity") == "must_fix" for i in text_issues):
        overall = "fail"
    elif text_issues:
        overall = "review_needed"
    else:
        overall = "pass"

    return {
        "overall":                  overall,
        "issues":                   text_issues,
        "image_issues":             [],  # 이미지 판정은 텍스트 분석에 통합됨
        "detected_visual_elements": detected_visual_elements,  # 추출된 시각 요소 (참고용)
        "cross_check":              cross_check,
    }


# =============================================================
# 엔드포인트
# =============================================================

@router.post("/analyze")
def analyze(case_id: str, req: AnalyzeRequest):
    """
    라벨 텍스트를 분석하여 ai_result를 생성하고 f4_results에 저장.
    내부에서 동기 I/O(OpenAI, Pinecone, SentenceTransformer)를 사용하므로
    def(동기)로 선언하여 FastAPI가 자동으로 threadpool에서 실행합니다.
    """
    try:
        clients = _get_clients()

        # 법령 업데이트 중 체크 — 업데이트 진행 중이면 분석 차단
        if _check_any_law_updating:
            try:
                updating_laws = _check_any_law_updating(clients["supabase"])
                if updating_laws:
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "error": "LAW_DB_UPDATING",
                            "message": "Law DB is currently being updated. Please try again shortly.",
                            "updating_laws": updating_laws,
                        },
                    )
            except HTTPException:
                raise
            except Exception:
                pass  # check failed — allow analysis to proceed

        ai_result = _run_analysis(req, clients, case_id=case_id)

        # f4_results upsert (case_id 기준 — 중복 행 방지)
        clients["supabase"].table("f4_results").upsert(
            {
                "case_id":   case_id,
                "ai_result": ai_result,
                "status":    "waiting_review",
            },
            on_conflict="case_id",
        ).execute()

        return {"case_id": case_id, "ai_result": ai_result}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate")
def validate_selection(case_id: str, req: ValidateRequest):
    """
    사용자가 체크한 위반 항목들의 법령 정합성을 검토.

    - conflicts: 선택 항목 간 법령 충돌 (함께 처리할 수 없는 경우)
    - dependencies: 선택 항목과 반드시 같이 가져가야 하는 미선택 법령

    [예시 응답]
    {
      "is_valid": false,
      "conflicts": [
        {
          "law_refs": ["제2025-79호 제3조제1항", "제2024-62호 제5조"],
          "description": "동일 표현이 79호에서 금지되지만 62호에서 조건부 허용됩니다.",
          "reasoning": "제2025-79호는 '피로회복에 도움'이라는 표현을 금지하지만, 제2024-62호 제5조는 기능성 표시 허가를 받은 제품에 한해 동일 표현을 허용합니다. 해당 제품의 기능성 허가 여부를 먼저 확인해야 합니다.",
          "recommendation": "기능성 허가 여부 확인 후 적용 조문 결정"
        }
      ],
      "dependencies": [
        {
          "selected_law_ref": "제2025-79호 제3조",
          "required_law_ref": "식품표시광고법 제8조제1항",
          "description": "고시 조문만 지적 시 법적 효력 부족",
          "reasoning": "고시(Tier 4)인 제2025-79호만 단독 인용하면 행정처분 근거가 약합니다. 상위법(Tier 1)인 식품 등의 표시·광고에 관한 법률 제8조제1항도 함께 명시해야 처분 근거가 완성됩니다."
        }
      ],
      "applied_principles": "상위법 우선 원칙(Tier 1>4) 및 제2025-79호와 제2024-62호 간 금지·허용 예외 관계 검토",
      "summary": "충돌 1건(기능성 허가 여부 확인 필요), 상위법 추가 인용 필요 1건"
    }
    """
    try:
        clients = _get_clients()
        validation = _validate_selection(req.selected_issues, req.selected_image_issues, clients)

        # 검증 결과를 DB에 임시 저장 (PATCH 전 참고용)
        clients["supabase"].table("f4_results").update({
            "validation_result": validation,
        }).eq("case_id", case_id).execute()

        return validation
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
def get_result(case_id: str):
    """저장된 분석 결과 조회."""
    try:
        clients = _get_clients()
        res = clients["supabase"].table("f4_results").select("*").eq("case_id", case_id).execute()
        if not res.data:
            return {"status": "pending", "ai_result": None, "final_result": None}
        row = res.data[0]
        return {
            "status":       row["status"],
            "ai_result":    row["ai_result"],
            "final_result": row["final_result"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("")
def update_result(case_id: str, req: UpdateRequest):
    """사용자가 체크한 항목만 final_result로 저장."""
    try:
        clients = _get_clients()
        clients["supabase"].table("f4_results").update({
            "final_result": req.final_result,
            "edit_reason":  req.edit_reason,
            "status":       "waiting_review",
        }).eq("case_id", case_id).execute()
        return {"message": "저장 완료"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/confirm")
def confirm_result(case_id: str):
    """담당자 확인 완료 — 상태를 completed로 변경."""
    try:
        clients = _get_clients()
        clients["supabase"].table("f4_results").update({
            "status": "completed",
        }).eq("case_id", case_id).execute()
        return {"message": "확인 완료"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================
# PDF 레포트 생성
# =============================================================

def _resolve_font_paths() -> tuple[str, str]:
    """OS에 따라 맑은고딕 폰트 경로를 반환. 프로젝트 번들 > 시스템 순으로 탐색."""
    # 1) 프로젝트에 번들된 폰트 (배포 환경용)
    bundled = Path(__file__).parent.parent / "fonts"
    if (bundled / "malgun.ttf").exists():
        return str(bundled / "malgun.ttf"), str(bundled / "malgunbd.ttf")

    # 2) OS별 시스템 폰트
    _os = platform.system()
    if _os == "Windows":
        return "C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/malgunbd.ttf"
    elif _os == "Darwin":  # macOS
        return "/System/Library/Fonts/AppleSDGothicNeo.ttc", "/System/Library/Fonts/AppleSDGothicNeo.ttc"
    else:  # Linux
        candidates = [
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/usr/share/fonts/nanum/NanumGothic.ttf",
        ]
        for c in candidates:
            if Path(c).exists():
                return c, c
        # 폴백 — 폰트 없으면 런타임에 에러 발생
        return str(bundled / "malgun.ttf"), str(bundled / "malgunbd.ttf")


_FONT_PATH, _FONT_BOLD_PATH = _resolve_font_paths()

_SEVERITY_LABEL = {"must_fix": "시정 필수", "review_needed": "검토 필요"}
_OVERALL_LABEL = {"pass": "적합", "fail": "부적합", "review_needed": "검토 필요"}


class _ReportPDF(FPDF):
    """F4 수출국 표시사항 검토 레포트 PDF."""

    def __init__(self):
        super().__init__()
        self.add_font("malgun", "", _FONT_PATH, uni=True)
        self.add_font("malgun", "B", _FONT_BOLD_PATH, uni=True)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        self.set_font("malgun", "B", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, "SAMC 수입식품 검역 AI — F4 수출국 표시사항 검토 레포트", align="C")
        self.ln(4)
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("malgun", "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"- {self.page_no()} -", align="C")

    def section_title(self, title: str):
        self.set_font("malgun", "B", 13)
        self.set_text_color(30, 40, 80)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(30, 40, 80)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def sub_title(self, title: str):
        self.set_font("malgun", "B", 11)
        self.set_text_color(50, 50, 50)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def body_text(self, text: str):
        self.set_font("malgun", "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 6, text)
        self.ln(2)

    def badge(self, label: str, color: tuple):
        self.set_font("malgun", "B", 10)
        self.set_fill_color(*color)
        self.set_text_color(255, 255, 255)
        w = self.get_string_width(label) + 10
        self.cell(w, 8, label, fill=True, align="C")
        self.set_text_color(30, 30, 30)
        self.ln(10)

    def kv_row(self, key: str, value: str):
        self.set_font("malgun", "B", 10)
        self.cell(35, 7, key)
        self.set_font("malgun", "", 10)
        self.multi_cell(0, 7, value or "-")
        self.ln(1)


def _build_report_pdf(case_id: str, row: dict) -> bytes:
    """f4_results row 데이터를 기반으로 PDF 바이트 생성."""

    # final_result 우선, 없으면 ai_result 사용
    result = row.get("final_result") or row.get("ai_result") or {}
    validation = row.get("validation_result") or {}
    status = row.get("status", "pending")
    overall = result.get("overall", "pending")
    issues = result.get("issues", [])
    image_issues = result.get("image_issues", [])
    cross_check = result.get("cross_check", [])

    pdf = _ReportPDF()
    pdf.add_page()

    # ── 1. 개요 ──
    pdf.section_title("1. 검토 개요")

    pdf.kv_row("케이스 ID", case_id)
    pdf.kv_row("검토 상태", {"pending": "대기", "waiting_review": "검토 대기",
                          "completed": "완료"}.get(status, status))
    pdf.kv_row("생성일시", row.get("created_at", "-"))
    pdf.kv_row("레포트 생성", datetime.now().strftime("%Y-%m-%d %H:%M"))
    pdf.ln(2)

    # 종합 판정 배지
    pdf.sub_title("종합 판정")
    overall_label = _OVERALL_LABEL.get(overall, overall)
    color_map = {"pass": (34, 139, 34), "fail": (200, 30, 30), "review_needed": (210, 150, 0)}
    pdf.badge(overall_label, color_map.get(overall, (100, 100, 100)))
    pdf.ln(2)

    if row.get("edit_reason"):
        pdf.kv_row("수정 사유", row["edit_reason"])
        pdf.ln(2)

    # ── 2. 텍스트 위반 항목 ──
    pdf.section_title("2. 텍스트 위반 항목")

    if not issues:
        pdf.body_text("발견된 텍스트 위반 항목이 없습니다.")
    else:
        for i, issue in enumerate(issues, 1):
            severity = _SEVERITY_LABEL.get(issue.get("severity", ""), issue.get("severity", ""))
            pdf.sub_title(f"  {i}. [{severity}] {issue.get('text', '')[:60]}")
            pdf.kv_row("문제 표현", issue.get("text", ""))
            pdf.kv_row("위치", issue.get("location", "-"))
            pdf.kv_row("사유", issue.get("reason", "-"))
            pdf.kv_row("근거 법령", issue.get("law_ref", "-"))
            pdf.ln(3)

    # ── 3. 이미지 위반 항목 ──
    pdf.section_title("3. 이미지 위반 항목")

    if not image_issues:
        pdf.body_text("발견된 이미지 위반 항목이 없습니다.")
    else:
        for i, issue in enumerate(image_issues, 1):
            severity = _SEVERITY_LABEL.get(issue.get("severity", ""), issue.get("severity", ""))
            pdf.sub_title(f"  {i}. [{severity}] {issue.get('violation_type', '')[:50]}")
            pdf.kv_row("설명", issue.get("description", ""))
            pdf.kv_row("위치", issue.get("location", "-"))
            pdf.kv_row("위반 유형", issue.get("violation_type", "-"))
            pdf.kv_row("근거 법령", issue.get("law_ref", "-"))
            pdf.kv_row("판단 근거", issue.get("reasoning", "-"))
            pdf.kv_row("권고 사항", issue.get("recommendation", "-"))
            pdf.ln(3)

    # ── 4. 교차검증 결과 ──
    pdf.section_title("4. 라벨 ↔ 서류 교차검증")

    if not cross_check:
        pdf.body_text("교차검증 데이터가 없습니다.")
    else:
        field_label = {
            "product_name": "제품명", "ingredients": "원재료",
            "content_volume": "내용량", "origin": "원산지",
            "manufacturer": "제조사",
        }
        for item in cross_check:
            field = field_label.get(item.get("field", ""), item.get("field", ""))
            match = item.get("match", True)
            icon = "일치" if match else "불일치"
            pdf.sub_title(f"  {field}: {icon}")
            pdf.kv_row("라벨 표기", item.get("label_value", "-"))
            pdf.kv_row("서류 정보", item.get("doc_value", "-"))
            if not match and item.get("note"):
                pdf.kv_row("비고", item["note"])
            pdf.ln(2)

    # ── 5. 법령 정합성 검증 ──
    if validation:
        pdf.section_title("5. 법령 정합성 검증")

        conflicts = validation.get("conflicts", [])
        dependencies = validation.get("dependencies", [])

        if conflicts:
            pdf.sub_title("충돌 사항")
            for c in conflicts:
                refs = ", ".join(c.get("law_refs", []))
                pdf.kv_row("관련 법령", refs)
                pdf.kv_row("내용", c.get("description", ""))
                pdf.kv_row("분석", c.get("reasoning", ""))
                pdf.kv_row("권고", c.get("recommendation", ""))
                pdf.ln(2)

        if dependencies:
            pdf.sub_title("추가 인용 필요 법령")
            for d in dependencies:
                pdf.kv_row("선택 법령", d.get("selected_law_ref", ""))
                pdf.kv_row("필요 법령", d.get("required_law_ref", ""))
                pdf.kv_row("사유", d.get("reasoning", ""))
                pdf.ln(2)

        if validation.get("summary"):
            pdf.sub_title("검증 요약")
            pdf.body_text(validation["summary"])

    # PDF 바이트 출력
    return pdf.output()


@router.get("/report")
def download_report(case_id: str):
    """
    F4 검토 결과를 PDF 레포트로 다운로드.

    final_result가 있으면 그 기준, 없으면 ai_result 기준으로 생성.
    """
    try:
        clients = _get_clients()
        res = (
            clients["supabase"]
            .table("f4_results")
            .select("*")
            .eq("case_id", case_id)
            .execute()
        )
        if not res.data:
            raise HTTPException(status_code=404, detail="해당 케이스의 분석 결과가 없습니다.")

        row = res.data[0]
        pdf_bytes = _build_report_pdf(case_id, row)

        filename = f"F4_report_{case_id}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
