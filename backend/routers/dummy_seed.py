"""
더미 데이터 시드 — 파이프라인 테스트용

POST /api/v1/cases/{case_id}/pipeline/seed-dummy
  → F0~F4 더미 결과를 pipeline_steps + f4_results에 삽입
  → 각 Feature 페이지에서 이전 단계 결과를 바로 확인 가능

DELETE /api/v1/cases/{case_id}/pipeline/seed-dummy
  → 더미 데이터 제거
"""

from fastapi import APIRouter, HTTPException
from db.supabase_client import get_supabase

router = APIRouter(prefix="/cases/{case_id}/pipeline", tags=["dev-seed"])


# ── 더미 데이터 정의 ─────────────────────────────────────

DUMMY_F0 = {
    "basic_info": {
        "product_name": "Scottish Highland Whisky",
        "export_country": "영국",
        "is_first_import": False,
        "is_organic": False,
        "is_oem": False,
    },
    "ingredients": [
        {"id": "ing-1", "name": "보리", "ratio": "51%", "origin": "영국", "ins_number": "", "cas_number": ""},
        {"id": "ing-2", "name": "맥아", "ratio": "30%", "origin": "영국", "ins_number": "", "cas_number": ""},
        {"id": "ing-3", "name": "정제수", "ratio": "19%", "origin": "", "ins_number": "", "cas_number": ""},
    ],
    "process_info": {
        "process_codes": ["35", "14", "15", "45"],
        "process_code_reasons": [
            {"code": "35", "reason": "곡류를 원료로 발효"},
            {"code": "14", "reason": "증류 공정"},
            {"code": "15", "reason": "숙성(오크통)"},
            {"code": "45", "reason": "병입 및 포장"},
        ],
        "process_code_candidates": [],
        "raw_process_text": "맥아를 분쇄하고 물과 섞어 발효시킨 후 구리 증류기에서 2회 증류. 오크통에서 최소 3년 숙성 후 병입.",
    },
    "label_info": {
        "export_country": "영국",
        "is_oem": False,
        "label_texts": [
            "Scottish Highland Single Malt Whisky",
            "Aged 12 Years",
            "700ml / 40% vol",
            "Product of Scotland",
        ],
        "design_description": "짙은 갈색 유리병, 금색 라벨, 사슴 문양 엠블럼",
        "warnings": ["DRINK RESPONSIBLY"],
    },
}

DUMMY_F1 = {
    "import_possible": True,
    "verdict": "수입가능",
    "ingredients": [
        {"name": "보리", "percentage": 51.0, "status": "allowed", "law_ref": "식품공전 별표1"},
        {"name": "맥아", "percentage": 30.0, "status": "allowed", "law_ref": "식품공전 별표1"},
        {"name": "정제수", "percentage": 19.0, "status": "allowed", "law_ref": ""},
    ],
    "fail_reasons": [],
    "standards_check": [
        {
            "ingredient_name": "메탄올",
            "actual_value": None,
            "unit": "mg/mL",
            "threshold_value": 1.0,
            "threshold_text": "1.0 mg/mL 이하",
            "status": "no_data",
            "law_ref": "식품공전 제5장 15. 주류",
        },
    ],
    "_internal": {
        "aggregation": {
            "total": 3,
            "permitted": 3,
            "restricted": 0,
            "prohibited": 0,
            "unidentified": 0,
            "results": [],
            "escalations": [],
        },
        "conditional_evaluations": [],
        "forbidden_hits": [],
        "escalations": [],
        "law_refs": [{"law_source": "식품공전", "law_article": "별표1 식품에 사용할 수 있는 원료"}],
    },
}

DUMMY_F2 = {
    "category_name": "주류",
    "category_no": "15",
    "subcategory_name": "증류주류",
    "food_type": "위스키",
    "law_ref": "식품공전 제5장 15. 주류",
    "reason": "맥아를 원료로 발효·증류 후 오크통 숙성 과정을 거친 제품으로, 식품공전 '위스키' 정의에 부합합니다.",
    "is_alcohol": True,
    "required_docs": [
        {"doc_name": "수입신고서", "condition": None, "is_mandatory": True, "law_source": "수입식품안전관리특별법 제20조", "food_type": None},
        {"doc_name": "주류수입면허 사본", "condition": "주류에 한함", "is_mandatory": True, "law_source": "주세법 제8조", "food_type": "위스키"},
        {"doc_name": "위생증명서 (원본)", "condition": None, "is_mandatory": True, "law_source": "수입식품안전관리특별법 제21조", "food_type": None},
        {"doc_name": "자가품질검사 성적서", "condition": None, "is_mandatory": True, "law_source": "식품위생법 제31조", "food_type": None},
    ],
    "source_doc": "원재료배합비율표.pdf",
}

DUMMY_F3 = {
    "food_type": "위스키",
    "origin_country": "영국",
    "is_first_import": False,
    "submit_docs": [
        {
            "id": "doc-1",
            "food_type": None,
            "condition": None,
            "target_country": None,
            "product_keywords": None,
            "doc_name": "수입신고서",
            "doc_description": "수입식품 등의 수입신고 시 제출하는 기본 서류",
            "is_mandatory": True,
            "submission_type": "submit",
            "submission_timing": "every",
            "law_source": "수입식품안전관리특별법 제20조",
            "effective_from": None,
            "effective_until": None,
            "match_reason": "모든 수입식품 공통 필수",
            "decision_axis": "common",
        },
        {
            "id": "doc-2",
            "food_type": "위스키",
            "condition": "주류에 한함",
            "target_country": None,
            "product_keywords": None,
            "doc_name": "주류수입면허 사본",
            "doc_description": "주류 수입 시 국세청 발급 면허증 사본",
            "is_mandatory": True,
            "submission_type": "submit",
            "submission_timing": "every",
            "law_source": "주세법 제8조",
            "effective_from": None,
            "effective_until": None,
            "match_reason": "식품유형 '위스키' → 주류 해당",
            "decision_axis": "food_type",
        },
        {
            "id": "doc-3",
            "food_type": None,
            "condition": None,
            "target_country": None,
            "product_keywords": None,
            "doc_name": "위생증명서 (원본)",
            "doc_description": "수출국 정부기관 발행 위생증명서 원본",
            "is_mandatory": True,
            "submission_type": "submit",
            "submission_timing": "every",
            "law_source": "수입식품안전관리특별법 제21조",
            "effective_from": None,
            "effective_until": None,
            "match_reason": "모든 수입식품 공통 필수",
            "decision_axis": "common",
        },
    ],
    "keep_docs": [
        {
            "id": "doc-4",
            "food_type": None,
            "condition": None,
            "target_country": None,
            "product_keywords": None,
            "doc_name": "자가품질검사 성적서",
            "doc_description": "식품위생법에 따른 자가품질검사 결과 보관",
            "is_mandatory": True,
            "submission_type": "keep",
            "submission_timing": "every",
            "law_source": "식품위생법 제31조",
            "effective_from": None,
            "effective_until": None,
            "match_reason": "모든 수입식품 보관 필수",
            "decision_axis": "common",
        },
    ],
    "total_submit": 3,
    "total_keep": 1,
    "warnings": [],
    "match_confidence": "high",
}

DUMMY_F4 = {
    "overall": "review_needed",
    "issues": [
        {
            "text": "Aged 12 Years",
            "location": "전면 라벨 중앙",
            "reason": "연수 표시는 숙성 기간의 정확성 확인 필요. '12년산'으로 한글 표기 시 실제 숙성 기간과 일치해야 함.",
            "law_ref": "주류의 표시기준 제4조 제3항",
            "severity": "review_needed",
            "category": "숙성연수",
        },
        {
            "text": "DRINK RESPONSIBLY",
            "location": "후면 라벨 하단",
            "reason": "한국 주류 경고문구 기준과 다름. '경고: 지나친 음주는 간경화나 간암을 일으키며...' 문구로 교체 필요.",
            "law_ref": "국민건강증진법 제8조",
            "severity": "must_fix",
            "category": "경고문구",
        },
    ],
    "image_issues": [
        {
            "description": "사슴 문양 엠블럼에 왕관이 포함되어 있어 '왕실 인증' 오인 가능성",
            "location": "전면 라벨 상단 엠블럼",
            "violation_type": "허위·과대 표시",
            "law_ref": "식품 등의 표시·광고에 관한 법률 제8조 제1항",
            "reasoning": "왕실·정부기관 인증을 암시하는 표현으로 오인될 수 있음",
            "severity": "review_needed",
            "recommendation": "왕관 제거 또는 '장식용 디자인' 명시 권장",
            "source_image_id": None,
            "review_level": "suggested",
        },
    ],
    "cross_check": [
        {"field": "product_name", "label_value": "Scottish Highland Whisky", "doc_value": "Scottish Highland Whisky", "match": True, "note": "일치"},
        {"field": "content_volume", "label_value": "700ml", "doc_value": "700ml", "match": True, "note": "일치"},
        {"field": "origin", "label_value": "Product of Scotland", "doc_value": "영국", "match": True, "note": "Scotland = 영국(UK) — 일치"},
    ],
}


# ── 엔드포인트 ──────────────────────────────────────────

SEED_STEPS = [
    {"step_key": "0", "step_name": "입력 및 OCR 파싱", "data": DUMMY_F0},
    {"step_key": "1", "step_name": "import_check",     "data": DUMMY_F1},
    {"step_key": "2", "step_name": "food_type",         "data": DUMMY_F2},
    {"step_key": "3", "step_name": "required_docs",     "data": DUMMY_F3},
]


@router.post("/seed-dummy")
async def seed_dummy(case_id: str):
    """F0~F4 더미 데이터를 pipeline_steps + f4_results에 삽입."""
    sb = get_supabase()

    # 케이스 존재 확인
    case_res = sb.table("cases").select("id").eq("id", case_id).execute()
    if not case_res.data:
        raise HTTPException(404, detail="케이스를 찾을 수 없습니다.")

    # pipeline_steps: F0~F3
    for step in SEED_STEPS:
        sb.table("pipeline_steps").upsert(
            {
                "case_id": case_id,
                "step_key": step["step_key"],
                "step_name": step["step_name"],
                "status": "completed",
                "ai_result": step["data"],
            },
            on_conflict="case_id,step_key",
        ).execute()

    # f4_results: F4 (별도 테이블 — unique constraint 없으므로 delete+insert)
    sb.table("f4_results").delete().eq("case_id", case_id).execute()
    sb.table("f4_results").insert(
        {
            "case_id": case_id,
            "status": "completed",
            "ai_result": DUMMY_F4,
        },
    ).execute()

    return {
        "status": "seeded",
        "case_id": case_id,
        "steps_seeded": ["F0", "F1", "F2", "F3", "F4"],
        "message": "더미 데이터가 삽입되었습니다. 각 Feature 페이지에서 이전 단계 결과를 확인할 수 있습니다.",
    }


@router.delete("/seed-dummy")
async def clear_dummy(case_id: str):
    """더미 데이터 제거."""
    sb = get_supabase()

    for step_key in ["0", "1", "2", "3"]:
        sb.table("pipeline_steps").delete().eq("case_id", case_id).eq("step_key", step_key).execute()

    sb.table("f4_results").delete().eq("case_id", case_id).execute()

    return {"status": "cleared", "case_id": case_id}
