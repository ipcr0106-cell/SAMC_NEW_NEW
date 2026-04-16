"""
기능 3 FastAPI 라우터 — 수입 필요서류 안내.

엔드포인트:
  POST /cases/{case_id}/pipeline/feature/3/run  — f0+F1+F2 결과 자동 조회 → 서류 매칭
  GET  /cases/{case_id}/pipeline/feature/3      — 결과 조회
  POST /api/v1/required-docs/rag               — 법령 본문 시맨틱 검색 (선택)
  POST /api/v1/required-docs/reload            — 캐시 리로드
"""
import os

from fastapi import APIRouter, HTTPException

from db.f3_supabase_client import reload_cache, save_pipeline_step
from models.f3_schemas import ProductInfo, RequiredDocsResponse
from services.f3_pinecone_client import search_law_chunks
from services.f3_required_docs import match_required_docs


router = APIRouter(tags=["feature-3"])


# ════════════════════════════════════════════════════════════
# f0 + F1 + F2 → F3 파이프라인 자동 연결 (PM 임의 구현)
# 수정/삭제하고 싶으면 이 섹션만 변경하면 됩니다.
# ════════════════════════════════════════════════════════════

def _fetch_pipeline(case_id: str, step_key: str) -> dict | None:
    """pipeline_steps에서 특정 단계 결과를 Supabase PostgREST로 조회."""
    import httpx
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    try:
        r = httpx.get(
            f"{url}/rest/v1/pipeline_steps?case_id=eq.{case_id}&step_key=eq.{step_key}&select=ai_result,final_result",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=10.0,
        )
        r.raise_for_status()
        rows = r.json()
        if rows:
            return rows[0].get("final_result") or rows[0].get("ai_result")
    except Exception:
        pass
    return None


def _build_product_info_from_pipeline(case_id: str) -> ProductInfo:
    """f0 + F1 + F2 결과를 합쳐서 F3 입력(ProductInfo)을 자동 생성.

    PM이 임의로 구현한 파이프라인 연결입니다.
    수정하고 싶으면 이 함수만 변경하면 됩니다.
    """
    # f0 결과
    f0 = _fetch_pipeline(case_id, "0") or {}
    basic = f0.get("basic_info") or {}

    # F1 결과 → product_keywords (원재료 이름 목록)
    f1 = _fetch_pipeline(case_id, "1") or {}
    f1_ingredients = f1.get("ingredients") or []
    product_keywords = [ing.get("name", "") for ing in f1_ingredients if ing.get("name")]

    # F2 결과 → food_type, category 등
    f2 = _fetch_pipeline(case_id, "2") or {}

    food_type = f2.get("food_type", "")
    if not food_type:
        raise HTTPException(400, detail={
            "error": "F2_NOT_COMPLETED",
            "message": "기능2(식품유형 분류)가 완료되지 않았습니다. 먼저 기능2를 실행하세요.",
            "feature": 3,
        })

    origin_country = basic.get("export_country", "")
    if not origin_country:
        raise HTTPException(400, detail={
            "error": "NO_ORIGIN_COUNTRY",
            "message": "수출국 정보가 없습니다. f0 파싱 결과를 확인하세요.",
            "feature": 3,
        })

    return ProductInfo(
        food_type=food_type,
        food_large_category=f2.get("category_name"),
        food_mid_category=f2.get("subcategory_name"),
        origin_country=origin_country,
        is_oem=basic.get("is_oem", False),
        is_first_import=basic.get("is_first_import", False),
        has_organic_cert=basic.get("is_organic", False),
        product_keywords=product_keywords,
    )


@router.post("/cases/{case_id}/pipeline/feature/3/run")
async def run_feature3(case_id: str):
    """F3 실행: f0+F1+F2 결과 자동 조회 → 5축 서류 매칭 → pipeline_steps 저장."""
    info = _build_product_info_from_pipeline(case_id)
    result = match_required_docs(info)

    # pipeline_steps에 저장
    save_pipeline_step(case_id, "3", result.model_dump())

    return {
        "case_id": case_id,
        "status": "waiting_review",
        "food_type": result.food_type,
        "origin_country": result.origin_country,
        "total_submit": result.total_submit,
        "total_keep": result.total_keep,
        "warnings": result.warnings,
    }


@router.get("/cases/{case_id}/pipeline/feature/3")
async def get_feature3(case_id: str):
    """F3 결과 조회."""
    result = _fetch_pipeline(case_id, "3")
    if not result:
        raise HTTPException(404, detail="기능3 결과가 없습니다. 먼저 /run을 실행하세요.")
    return result


# ════════════════════════════════════════════════════════════
# 유틸 엔드포인트 (법령 검색, 캐시 리로드)
# ════════════════════════════════════════════════════════════

@router.post("/required-docs/rag")
async def search_law_context(payload: dict) -> list[dict]:
    """법령 청크 시맨틱 검색 (AI 교차검증·설명 생성용)."""
    query = (payload or {}).get("query", "").strip()
    if not query:
        raise HTTPException(400, detail={"error": "QUERY_REQUIRED", "message": "query 필요", "feature": 3})
    return search_law_chunks(
        query=query,
        top_k=int((payload or {}).get("top_k", 5)),
        filter_doc_ids=(payload or {}).get("filter_doc_ids"),
    )


@router.post("/required-docs/reload")
async def reload_data_cache() -> dict:
    """Supabase 데이터 캐시 리로드 (법령 개정 반영)."""
    reload_cache()
    return {"status": "reloaded", "feature": 3}
