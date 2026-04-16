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
import re
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
    """라벨 이미지 OCR 텍스트 → f0 pipeline_steps의 label_info에서 추출."""
    parsed = _fetch_f0_parsed(supabase, case_id)
    if not parsed:
        return {}

    label = parsed.get("label_info", {})
    basic = parsed.get("basic_info", {})
    ingredients_list = parsed.get("ingredients", [])

    # label_texts 배열을 하나의 텍스트로 합침
    label_texts = label.get("label_texts", [])
    label_text = "\n".join(label_texts) if label_texts else ""

    ingredient_names = ", ".join(
        item.get("name", "") for item in ingredients_list if item.get("name")
    )

    return {
        "label_text":     label_text,
        "product_name":   basic.get("product_name", ""),
        "ingredients":    ingredient_names,
        "content_volume": "",
        "origin":         label.get("export_country", "") or basic.get("export_country", ""),
        "manufacturer":   "",
    }


def _fetch_label_images(supabase, case_id: str) -> list[dict]:
    """
    크롭된 라벨 제품 이미지 목록을 DB에서 조회.
    source_document_id 기준으로 dedup하여 가장 최근 것만 반환.
    """
    try:
        cols = _LABEL_IMAGES_COLUMNS
        res = (
            supabase.table(_LABEL_IMAGES_TABLE)
            .select(f"{cols['image_id']},{cols['source_document_id']},{cols['cropped_storage_path']}")
            .eq(cols["case_id"], case_id)
            .order("created_at", desc=True)
            .execute()
        )
        if not res.data:
            return []

        # source_document_id 기준 dedup (최신 것만 유지)
        seen_doc_ids: set = set()
        deduped: list[dict] = []
        for row in res.data:
            doc_id = row.get(cols["source_document_id"])
            if doc_id and doc_id in seen_doc_ids:
                continue
            if doc_id:
                seen_doc_ids.add(doc_id)
            deduped.append({
                "image_id":     row.get(cols["image_id"]),
                "storage_path": row.get(cols["cropped_storage_path"]),
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
    label_text: str                        # 라벨 전체 텍스트 (OCR 결과 or 직접 입력)
    food_type: str = "미분류"              # F2 출력값 (테스트용 mock 가능)
    ingredients: list[str] = []           # F1 출력값 (테스트용 mock 가능)
    # 라벨 이미지 URL — 실서비스에서는 OCR 단계에서 넘어옴. 현재는 테스트용 직접 입력.
    label_image_url: str | None = None
    # 라벨 ↔ 서류 교차검증용 (테스트용 mock 가능)
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

[라벨 전체 텍스트]
{label_text}

[참고 법령 조문]
{law_chunks}

[금지 표현 키워드 목록]
{prohibited_keywords}

분석 기준:
1. 라벨 텍스트에서 금지 표현 키워드 또는 법령상 금지된 유사 표현을 찾아내세요.
2. 각 문제 표현에 대해 위반 카테고리와 severity를 판단하세요.
   - category: {categories}
   - severity: "must_fix" (명시적 금지) | "review_needed" (맥락에 따라 문제)
3. 발견된 문제가 없으면 overall을 "pass"로 설정하세요.

반드시 아래 JSON 형식으로만 응답하세요. 다른 설명은 생략하세요.
{{
  "overall": "pass" | "fail" | "review_needed",
  "issues": [
    {{
      "text": "문제 표현 원문",
      "location": "라벨 상 위치 (예: 상단 문구, 성분표 하단)",
      "reason": "삭제/수정이 필요한 이유",
      "law_ref": "근거 법령 조문 (예: 제3조제1항제1호)",
      "severity": "must_fix" | "review_needed"
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
당신은 한국 식품 표시·광고 법령 전문가입니다.
아래 식품 라벨 이미지를 분석하여 이미지·그림 요소 중 법령 위반이 의심되는 항목을 모두 찾아주세요.

[분석 원칙]
- 확신이 없어도 누락하지 말고 severity를 "review_needed"로 포함하세요.
- 여러 유형에 동시 해당하면 각각 별도 항목으로 보고하세요.
- 각 항목의 reasoning은 사용자가 이해할 수 있도록 법령 조항과 함께 구체적으로 설명하세요.
- [severity 기본 원칙]: 허위 인증·마크 사용(③⑤⑦⑱)은 반드시 must_fix.
  질병·치료 직접 암시(①⑮)는 반드시 must_fix.
  그 외 유형은 맥락에 따라 must_fix 또는 review_needed로 판단.

[적용 법령]
- 식품 등의 표시·광고에 관한 법률 (제20826호) 제8조·제10조
- 식품등의 부당한 표시 또는 광고의 내용 기준 (제2025-79호) 제3조
- 식품등의 표시기준 (제2025-60호)
- 부당한 표시·광고로 보지 아니하는 기능성 표시·광고에 관한 규정 (제2024-62호)
- 농수산물의 원산지 표시에 관한 법률
- 친환경농어업 육성 및 유기식품 등의 관리·지원에 관한 법률
- 식품위생법 제12조의2 (소비자 기만 금지)

[이미지 위반 유형 전체 목록]

① 질병 치료·예방 암시 [기본 severity: must_fix]
   세부: 심장·간·혈관·뇌·신장·관절 등 특정 신체 부위의 치료·회복·개선을 나타내는 그림,
         질병명(암·당뇨·고혈압 등)과 함께 식품 이미지를 배치하여 치료 효과 암시,
         신체 비포/애프터 비교(복부·피부·혈관 등), X레이·MRI 이미지와 식품 조합
   근거: 제2025-79호 제3조제1항제1호, 식품표시광고법 제8조제1항

② 의약품·의료기기 오인 [기본 severity: must_fix]
   세부: 주사기·수액백·알약·캡슐·정제·청진기·혈압계 등 의료 기구 이미지,
         흰 가운(백의) 입은 의사·약사·연구원 이미지,
         병원·약국·수술실·임상 환경을 연상케 하는 배경,
         처방전·의약품 포장 유사 디자인
   근거: 제2025-79호 제3조제1항제2호

③ 건강기능식품 마크 무단 사용 [기본 severity: must_fix]
   세부: 식약처 공식 건강기능식품 마크(파란 방패+사람 모양)를 허가 없이 사용,
         공식 마크와 유사한 색상·형태·문구의 자체 제작 마크,
         "건강기능식품" 문구와 유사 마크의 동시 사용으로 인증받은 것처럼 오인 유도
   근거: 식품표시광고법 제10조, 건강기능식품법 제17조

④ 효능·효과 과장 이미지 [기본 severity: review_needed → 수치/비교 명시 시 must_fix]
   세부: 체중감량 비포/애프터(수치·사이즈 표시 포함), 근육 성장 전후 비교,
         피부 개선·미백·주름 제거 전후 비교, "N주 만에 ~kg 감량" 등 수치 강조 그래프,
         경쟁 제품 대비 효능이 월등히 높음을 나타내는 막대그래프·파이차트
   근거: 제2025-79호 제3조제1항제4호

⑤ 유기·친환경 인증 마크 무단 사용 [기본 severity: must_fix]
   세부: 국립농산물품질관리원 유기농 인증(녹색 잎사귀+글자) 마크 미허가 사용,
         "USDA Organic" 등 외국 유기 인증 마크를 국내 인증인 것처럼 오용,
         인증 없이 녹색 잎사귀·자연 심볼로 유기농 이미지 연상,
         "무농약", "자연산", "천연" 등 문구와 결합된 자연 이미지
   근거: 식품표시광고법 제8조제2항, 친환경농어업법 제23조

⑥ 원산지 오인 이미지 [기본 severity: must_fix]
   세부: 실제 원산지와 다른 국기·국가 지도·랜드마크(에펠탑·자유의여신상 등) 이미지,
         "Made in ~" 표기와 다른 나라 이미지 혼용, 외국 언어 포장 이미지로 수입품 오인,
         특정 지역 특산물처럼 보이게 하는 지역 상징 이미지
   근거: 농수산물 원산지표시법 제5조, 제2025-79호 제3조제1항제3호

⑦ 수상·인증·허가 마크 허위·오용 [기본 severity: must_fix]
   세부: 받지 않은 국내외 수상(대상·금상 등) 마크, "FDA Approved" 등 허위 외국 인증,
         ISO·GMP·HACCP 인증을 받지 않았거나 만료된 경우의 마크 사용,
         소비자 선정 등 임의 어워드 마크를 공인 인증처럼 표시,
         소고기·돼지고기 등 축산물 등급 마크(1++·1+·1·2등급 등)를 실제 판정 등급보다
         높게 표시하거나 등급 판정을 받지 않은 제품에 사용,
         전통식품 품질인증(농림축산식품부 발급) 마크 미인증 제품에 사용,
         어린이 기호식품 품질인증(식약처 발급) 마크 미인증 제품에 사용
   근거: 제2025-79호 제3조제1항제3호, 식품표시광고법 제8조제1항,
         축산물위생관리법 제6조 (등급 표시), 전통식품산업의 육성 및 지원에 관한 법률 제22조

⑧ 인체 내부 작용 과장 이미지 [기본 severity: review_needed]
   세부: 장내세균·프로바이오틱스 효과를 과장한 장(腸) 단면 이미지,
         DNA·세포·미토콘드리아 이미지로 유전자 수준 효과 암시,
         혈관 속 성분 흐름, 뇌 활성화 이미지 등 과학적 효능 과장
   근거: 제2025-79호 제3조제1항제4호

⑨ 경쟁제품 비방·근거 없는 비교 이미지 [기본 severity: must_fix]
   세부: 경쟁사 제품을 열위로 표현하는 비교 이미지(색상·크기·형태로 암시 포함),
         "타사 제품"이라는 표기 없이 유사 패키지를 형편없이 묘사,
         근거 없이 "업계 1위", "유일한 제품" 등을 나타내는 시각 요소
   근거: 제2025-79호 제3조제1항제5호

⑩ 어린이·취약계층 현혹 이미지 [기본 severity: review_needed]
   세부: 어린이 캐릭터·만화를 활용하여 건강 효능(키 성장·지능 향상 등) 과장,
         임산부·노인 이미지와 건강 효능을 연결하는 그림,
         건강 취약계층(환자·고령자)을 대상으로 한 치료 효과 암시 이미지
   근거: 식품표시광고법 제8조제1항, 제2025-79호 제3조제1항

⑪ 실제 제품·원재료와 상이한 이미지 [기본 severity: review_needed → 명백한 허위 시 must_fix]
   세부: 실제 내용물과 다른 색상·형태·크기의 제품 이미지,
         원재료 비율과 다르게 고급 재료를 과도하게 강조한 이미지(딸기가 소량인데 딸기 가득),
         실제 식품과 다른 조리·완성 이미지로 기대치 오인 유도
   근거: 제2025-79호 제3조제1항제3호, 제2025-60호

⑫ 영양성분·함량 과장 이미지 [기본 severity: must_fix]
   세부: 실제 함량과 달리 특정 영양소(비타민·미네랄·단백질 등)가 풍부한 것처럼 표현한 그래프,
         "100배 더 많은 비타민C" 등 근거 없는 수치 시각화,
         영양성분표 수치와 불일치하는 인포그래픽
   근거: 제2025-79호 제3조제1항제4호, 제2025-60호 제5조

⑬ 자연성·순수성 허위 이미지 [기본 severity: review_needed]
   세부: 합성 첨가물이 들어간 제품에 산·숲·계곡·들판 등 자연 배경 과도 사용으로 천연 오인,
         "100% Natural" 문구와 자연 이미지 결합으로 무첨가·천연 착각 유도,
         인공 색소·향료가 포함된 제품에 과일·채소 원물 이미지만 강조
   근거: 제2025-79호 제3조제1항제3호

⑭ 임상·과학 데이터 과장 이미지 [기본 severity: must_fix]
   세부: 실제 해당 제품을 대상으로 하지 않은 논문·임상 결과를 제품에 연결하는 이미지,
         논문 표지·의학저널·연구 그래프를 배경에 배치하여 임상 효과 과장,
         연구자 수·피험자 수·효과 수치를 왜곡·과장한 인포그래픽
   근거: 제2025-79호 제3조제1항제4호

⑮ 질병 진단·검진 장비 이미지 [기본 severity: must_fix]
   세부: 혈당측정기·체지방측정기·혈압계 이미지와 수치를 식품과 조합하여 진단 효과 암시,
         "드시고 혈당을 재보세요" 등 문구와 진단 기기 이미지 결합,
         정상 수치로 바뀌는 검사 결과지 이미지
   근거: 제2025-79호 제3조제1항제1호 (질병 진단·치료 암시)

⑯ 특정 연령층 타겟 과장 이미지 (어린이 외) [기본 severity: review_needed]
   세부: 노인 대상 기억력·관절·심혈관 효과를 암시하는 이미지,
         임산부·수유부 대상 태아 발달·모유 성분 개선 효과 암시 이미지,
         청소년 대상 성장·집중력 향상 과장 이미지
   근거: 제2025-79호 제3조제1항제1호·제4호

⑰ 제조·가공 과정 허위 이미지 [기본 severity: review_needed]
   세부: 전통 수제·수작업 방식이 아닌데 장인이 직접 만드는 것처럼 표현,
         대규모 공장 생산이지만 소규모 전통 방식 이미지 사용,
         살균·방부 처리 과정을 "무가공"으로 오인하게 하는 이미지
   근거: 제2025-79호 제3조제1항제3호 (소비자 기만)

⑱ 국제·외국 기관 공인 허위 이미지 [기본 severity: must_fix]
   세부: WHO·FAO 등 국제 기관 로고·마크를 허가 없이 사용,
         해외 유명 기관(Mayo Clinic, Harvard 등) 추천·인정 표시 허위 사용,
         외국어 공인 문구("Clinically Proven", "Doctor Recommended")를 이미지로 강조
   근거: 제2025-79호 제3조제1항제3호, 식품표시광고법 제8조제1항

⑲ 체험담·후기 사진 허위 이미지 [기본 severity: must_fix]
   세부: 실제 소비자가 아닌 모델·배우 사진을 "실제 사용 후 변화"처럼 표현한 비포/애프터 이미지,
         "OO님 후기"라며 조작·연출된 체험 사진 삽입,
         제품 효과와 무관한 외모 개선 사진을 제품 사용 결과물로 암시,
         체중·피부·체형 변화를 과장하여 보여주는 편집 사진
   근거: 제2025-79호 제3조제1항제4호, 식품표시광고법 제8조제1항 (허위·과장 광고)

⑳ 포장 용량 과장 이미지 [기본 severity: review_needed → 명백한 불일치 시 must_fix]
   세부: 실제 내용량보다 포장재를 훨씬 크게 제작하여 많아 보이게 연출한 패키지 이미지,
         포장 내부 공간(과도한 에어 패키징)을 가득 찬 것처럼 라벨 이미지로 표현,
         동일 용량이지만 다른 제품보다 훨씬 커 보이도록 포장 비율을 왜곡한 이미지,
         묶음 제품을 낱개 수보다 많아 보이도록 배치한 제품 사진
   근거: 제2025-79호 제3조제1항제3호, 식품표시광고법 제8조제1항 (소비자 기만)

㉑ 알레르기 유발물질 오인·은폐 이미지 [기본 severity: must_fix]
   세부: 알레르기 유발물질(대두·밀·달걀·견과류 등)이 포함된 제품에 해당 원료가 없는 것처럼
         묘사한 원재료 이미지(예: 견과류 無 아이콘, 글루텐프리 심볼 허위 사용),
         알레르기 경고 문구가 시각적으로 강조된 이미지 요소에 가려지거나 묻혀 인식 불가,
         "무(無)○○" 표시와 함께 해당 성분이 없는 것처럼 오인하게 하는 그래픽 배치,
         이미지 디자인으로 법정 알레르기 표시 위치·색상 대비가 기준에 미달하여 식별 불가
   근거: 식품표시광고법 제4조제1항, 제2025-60호 제6조 (알레르기 유발물질 표시 기준)

㉒ 할랄·코셔 등 종교 인증 마크 허위 사용 [기본 severity: must_fix]
   세부: 이슬람 할랄(حلال) 공인 인증 마크를 허가 없이 사용하거나 유사 문양으로 인증받은 것처럼 표시,
         유대교 코셔(Kosher / OU·KOF-K 등) 인증 마크 무단 사용,
         인증 없이 "Halal-Friendly", "돼지고기 無" 이미지를 공식 종교 인증인 것처럼 오인 유도,
         인증 취소·만료된 마크를 계속 라벨에 유지
   근거: 제2025-79호 제3조제1항제3호 (소비자 기만), 식품표시광고법 제8조제1항

㉓ 유전자변형(GMO) 관련 허위 이미지 [기본 severity: must_fix]
   세부: GMO 원재료가 함유된 제품에 "Non-GMO", "GMO-Free" 배지·아이콘 허위 사용,
         유전자변형 표시 의무 원재료를 사용했음에도 자연·유기농 이미지만 강조하여 무함유 오인 유도,
         비GMO 인증을 받지 않았음에도 관련 심볼(나뭇잎+체크마크·씨앗 이미지 등) 사용,
         "자연 그대로" 등 문구와 자연 이미지 결합으로 GMO 미사용 착각 유도
   근거: 식품위생법 제12조의2, 농림축산식품부 유전자변형식품 표시기준 제4조

㉔ 기능성 인정 범위 초과 이미지 [기본 severity: must_fix]
   세부: 건강기능식품으로 허가받은 기능(예: 기억력 개선)을 넘어서는 효능을 이미지로 암시
         (예: 기억력 개선 허가 제품에 치매 예방·뇌 질환 치료 암시 그림),
         허가된 기능성 등급·문구 범위를 초과하는 효능 인포그래픽,
         허가받은 원료의 기능성 외 다른 효과를 이미지로 연상하게 하는 구성,
         기능성 허가 제품임을 표시했지만 실제 허가 내용과 다른 이미지로 소비자 오인 유도
   근거: 건강기능식품법 제18조, 부당한 표시·광고로 보지 아니하는 기능성 표시·광고에 관한 규정
         (제2024-62호) 제3조 (허가 범위 내에서만 허용)

㉕ 주류 라벨 음주 조장·미화 이미지 [기본 severity: must_fix]
   세부: 음주가 건강·체력·활력에 도움이 된다는 것을 암시하는 이미지,
         청소년이 음주하거나 즐거워하는 장면·캐릭터 사용,
         음주운전·과음을 미화하거나 문제없는 것처럼 표현한 이미지,
         주류임을 인식하기 어렵게 탄산음료·주스로 오인하게 하는 음료 이미지,
         알코올 도수나 음주 경고 문구를 시각적 요소로 가리거나 축소시키는 디자인
   근거: 국민건강증진법 제8조 (절주 조장 이미지 금지), 청소년 보호법 제26조,
         식품표시광고법 제8조제1항

㉖ 조제분유·영유아식품 모유 대체 오인 이미지 [기본 severity: must_fix]
   세부: 조제분유·조제식(영아용·성장기용)이 모유와 동등하거나 우월하다고 암시하는 이미지,
         수유 중인 모습이나 아기의 건강·성장을 분유와 직접 연결하는 그림,
         모유수유를 불편하거나 열등한 것처럼 표현하는 이미지,
         특수의료용도식품(환자식·고령친화식품 등)이 일반 식품과 같이 자유롭게 섭취 가능한
         것처럼 오인하게 하는 이미지 (의사 상담 없이 사용 가능한 것처럼 암시)
   근거: 모유대체식품의 판매촉진 등의 규제에 관한 법률 제4조,
         식품의 기준 및 규격 (영유아식 표시기준), 식품표시광고법 제8조제1항

문제가 없으면 빈 배열을 반환하세요.

반드시 아래 JSON 배열 형식으로만 응답하세요.
[
  {{
    "description": "이미지 요소 설명 (구체적으로)",
    "location": "라벨 상 위치 (예: 우측 상단, 중앙 하단)",
    "violation_type": "①~㉖ 중 해당 유형 번호와 이름",
    "law_ref": "근거 조문 (법령명 + 조문 번호)",
    "reasoning": "왜 이 이미지가 문제인지 — 어떤 법령 조항에 따라 무엇이 금지되는지, 이 이미지의 어떤 요소가 구체적으로 해당 조항에 위반되는지 사용자가 이해할 수 있도록 설명",
    "severity": "must_fix|review_needed",
    "recommendation": "어떻게 수정하거나 삭제해야 하는지 구체적 권고"
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
당신은 한국 식품 표시·광고 법령 전문가입니다.
아래 식품 라벨 이미지를 분석하여 이미지·그림 요소 중 법령 위반이 의심되는 항목을 모두 찾아주세요.

[분석 원칙]
- 확신이 없어도 누락하지 말고 severity를 "review_needed"로 포함하세요.
- 여러 유형에 동시 해당하면 각각 별도 항목으로 보고하세요.
- 각 항목의 reasoning은 법령 조항과 함께 사용자가 이해할 수 있도록 설명하세요.
- [severity 기본 원칙]: 각 유형 옆에 표시된 기본 severity를 따르세요.

[확정 위반 유형]
{confirmed_block}
{suggested_section}
문제가 없으면 빈 배열을 반환하세요.

반드시 아래 JSON 배열 형식으로만 응답하세요.
[
  {{{{
    "description": "이미지 요소 설명 (구체적으로)",
    "location": "라벨 상 위치 (예: 우측 상단, 중앙 하단)",
    "violation_type": "①~{last_num} 중 해당 유형 번호와 이름",
    "law_ref": "근거 조문 (법령명 + 조문 번호)",
    "reasoning": "왜 이 이미지가 문제인지 설명. AI가 불확실하면 '직접 확인 권고' 포함.",
    "severity": "must_fix|review_needed",
    "recommendation": "수정·삭제 권고 내용",
    "review_level": "confirmed|suggested"
  }}}}
]
"""
    _prompt_cache["prompt"] = prompt
    return prompt


def _analyze_image(claude: OpenAI, image_url: str, supabase=None) -> list[dict]:
    """OpenAI Vision으로 라벨 이미지의 그림 요소 위반 분석."""
    prompt = _build_image_prompt(supabase) if supabase else _IMAGE_ANALYSIS_PROMPT
    try:
        resp = claude.chat.completions.create(
            model="gpt-5.4-nano",
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


def _search_law_chunks(index, model, query: str, top_k: int = 5) -> list[str]:
    """Pinecone에서 관련 법령 조문 검색."""
    query_vec = model.encode(f"query: {query}").tolist()
    results = index.query(vector=query_vec, top_k=top_k, include_metadata=True)
    chunks = []
    for match in results.matches:
        if match.metadata and match.metadata.get("text"):
            chunks.append(match.metadata["text"])
    return chunks


def _call_ai(claude, prompt: str) -> dict | list:
    """AI 호출 후 JSON 파싱."""
    resp = claude.chat.completions.create(
        model="gpt-5.4-nano",
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

    if case_id:
        # ── F2 → food_type 자동 보충 (PM 임의 연결) ──
        if req.food_type == "미분류":
            f2 = _fetch_f2_result(sb, case_id)
            if f2 and f2.get("food_type"):
                req.food_type = f2["food_type"]

        # ── F1 → ingredients 자동 보충 (PM 임의 연결) ──
        if not req.ingredients:
            f1 = _fetch_f1_result(sb, case_id)
            if f1:
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

    if not label_text:
        raise ValueError("label_text가 비어 있습니다. 직접 입력하거나 OCR 결과가 DB에 있어야 합니다.")

    # 1. 금지 키워드 목록 조회
    prohibited = _fetch_prohibited_keywords(sb)
    keyword_summary = "\n".join(
        f"- [{kw['category']} / {kw['severity']}] {kw['keyword']} ({kw['law_ref']})"
        for kw in prohibited[:80]  # 프롬프트 길이 제한
    )

    # 2. 관련 법령 조문 검색 (RAG)
    law_chunks = _search_law_chunks(clients["index"], clients["model"], label_text)
    law_text = "\n\n".join(law_chunks) if law_chunks else "관련 조문 없음"

    # 3. 부적절 표현 감지
    analysis_prompt = _ANALYSIS_PROMPT.format(
        food_type=req.food_type,
        ingredients=", ".join(req.ingredients) if req.ingredients else "없음",
        label_text=label_text,
        law_chunks=law_text,
        prohibited_keywords=keyword_summary,
        categories=_fetch_categories(sb),
    )
    analysis_result = _call_ai(clients["claude"], analysis_prompt)

    # 4. 라벨 ↔ 서류 교차검증 (서류 정보가 하나라도 있을 때만)
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

    # 5. 이미지 분석 — 다중 이미지 지원
    image_issues = []

    # 5-a. request에 직접 전달된 이미지 URL (기존 호환)
    if req.label_image_url:
        image_issues.extend(
            _analyze_image(clients["claude"], req.label_image_url, sb)
        )

    # 5-b. DB에서 크롭된 라벨 이미지 조회 (dedup 적용)
    if case_id:
        label_images = _fetch_label_images(sb, case_id)
        for img in label_images:
            signed_url = _create_signed_url(sb, img["storage_path"])
            if signed_url:
                per_image_issues = _analyze_image(clients["claude"], signed_url, sb)
                for issue in per_image_issues:
                    issue["source_image_id"] = img["image_id"]
                image_issues.extend(per_image_issues)

    # overall 판정: 텍스트·이미지 중 하나라도 must_fix가 있으면 fail
    text_issues = analysis_result.get("issues", [])
    all_issues = text_issues + image_issues
    if any(i.get("severity") == "must_fix" for i in all_issues):
        overall = "fail"
    elif all_issues:
        overall = "review_needed"
    else:
        overall = analysis_result.get("overall", "pass")

    return {
        "overall":      overall,
        "issues":       text_issues,
        "image_issues": image_issues,
        "cross_check":  cross_check,
    }


# =============================================================
# 엔드포인트
# =============================================================

@router.post("/analyze")
async def analyze(case_id: str, req: AnalyzeRequest):
    """
    라벨 텍스트를 분석하여 ai_result를 생성하고 f4_results에 저장.

    [테스트 방법]
    POST /api/v1/cases/test-001/pipeline/feature/4/analyze
    {
      "label_text": "이 제품은 혈당을 낮춰주고 암을 예방합니다.",
      "food_type": "건강기능식품",
      "ingredients": ["포도당", "비타민C"]
    }
    """
    try:
        clients = _get_clients()
        ai_result = _run_analysis(req, clients, case_id=case_id)

        # f4_results 저장 (이미 있으면 갱신)
        existing = clients["supabase"].table("f4_results").select("id").eq("case_id", case_id).execute()
        if existing.data:
            clients["supabase"].table("f4_results").update({
                "ai_result": ai_result,
                "status": "waiting_review",
            }).eq("case_id", case_id).execute()
        else:
            clients["supabase"].table("f4_results").insert({
                "case_id":   case_id,
                "ai_result": ai_result,
                "status":    "waiting_review",
            }).execute()

        return {"case_id": case_id, "ai_result": ai_result}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate")
async def validate_selection(case_id: str, req: ValidateRequest):
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
async def get_result(case_id: str):
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
async def update_result(case_id: str, req: UpdateRequest):
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
async def confirm_result(case_id: str):
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

_FONT_PATH = "C:/Windows/Fonts/malgun.ttf"
_FONT_BOLD_PATH = "C:/Windows/Fonts/malgunbd.ttf"

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
async def download_report(case_id: str):
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
