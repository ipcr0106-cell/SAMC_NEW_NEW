"""
기능5 한글표시사항 시안 생성 / 조회 / 확정
POST  /api/v1/cases/{case_id}/pipeline/feature/5/run
GET   /api/v1/cases/{case_id}/pipeline/feature/5
PATCH /api/v1/cases/{case_id}/pipeline/feature/5
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from db.supabase_client import get_supabase
from services.step6_label import generate_label, generate_label_stream

router = APIRouter(prefix="/cases/{case_id}/pipeline/feature/5", tags=["pipeline"])

STEP_KEY = "5"
STEP_NAME = "한글표시사항"


class RunRequest(BaseModel):
    food_type: Optional[str] = None   # 없으면 AI가 서류에서 파악
    draft_label: Optional[str] = None # 한글 가안 (없으면 AI 자동 생성)
    stream: bool = False


class ConfirmRequest(BaseModel):
    confirmed_by: str


def _get_documents(case_id: str) -> list:
    res = (
        get_supabase()
        .table("documents")
        .select("parsed_md, file_name")
        .eq("case_id", case_id)
        .execute()
    )
    return res.data or []


# ════════════════════════════════════════════════════════════
# f0 ~ F4 → F5 파이프라인 자동 연결 (PM 임의 구현)
# 수정/삭제하고 싶으면 이 섹션만 변경하면 됩니다.
# ════════════════════════════════════════════════════════════

def _fetch_pipeline_result(case_id: str, step_key: str) -> dict | None:
    """pipeline_steps에서 특정 단계 결과 조회."""
    try:
        res = (
            get_supabase()
            .table("pipeline_steps")
            .select("ai_result, final_result")
            .eq("case_id", case_id)
            .eq("step_key", step_key)
            .execute()
        )
        if res.data:
            return res.data[0].get("final_result") or res.data[0].get("ai_result")
    except Exception:
        pass
    return None


def _fetch_f4_result(case_id: str) -> dict | None:
    """f4_results 테이블에서 F4 분석 결과 조회. (F4는 pipeline_steps를 쓰지 않음)"""
    try:
        res = (
            get_supabase()
            .table("f4_results")
            .select("ai_result, final_result")
            .eq("case_id", case_id)
            .execute()
        )
        if res.data:
            return res.data[0].get("final_result") or res.data[0].get("ai_result")
    except Exception:
        pass
    return None


def _enrich_food_type(case_id: str, body_food_type: str | None) -> str | None:
    """food_type이 없으면 F2 결과에서 자동 가져오기."""
    if body_food_type:
        return body_food_type
    f2 = _fetch_pipeline_result(case_id, "2")
    if f2:
        return f2.get("food_type")
    return None


def _build_context_from_pipeline(case_id: str) -> str:
    """f0 + F1 + F2 + F4 결과를 합쳐서 F5 프롬프트 보충 컨텍스트 생성."""
    parts = []

    # f0 결과
    f0 = _fetch_pipeline_result(case_id, "0")
    if f0:
        basic = f0.get("basic_info") or {}
        if basic.get("product_name"):
            parts.append(f"제품명: {basic['product_name']}")
        if basic.get("export_country"):
            parts.append(f"원산지: {basic['export_country']}")
        if basic.get("is_oem"):
            parts.append("OEM 수입식품")
        ingredients = f0.get("ingredients") or []
        if ingredients:
            names = [i.get("name", "") for i in ingredients if i.get("name")]
            parts.append(f"원재료: {', '.join(names)}")

    # F1 결과
    f1 = _fetch_pipeline_result(case_id, "1")
    if f1:
        parts.append(f"F1 수입판정: {f1.get('verdict', '')}")

    # F2 결과
    f2 = _fetch_pipeline_result(case_id, "2")
    if f2:
        parts.append(f"식품유형: {f2.get('food_type', '')}")
        if f2.get("is_alcohol"):
            parts.append("주류 제품")

    # F4 결과 — f4_results 테이블에서 직접 조회 (F4는 pipeline_steps를 쓰지 않음)
    f4 = _fetch_f4_result(case_id)
    if f4:
        issues = f4.get("issues") or []
        image_issues = f4.get("image_issues") or []
        all_issues = []
        for iss in issues:
            all_issues.append(f"- [텍스트] {iss.get('text', '')}: {iss.get('reason', '')} ({iss.get('law_ref', '')})")
        for iss in image_issues:
            all_issues.append(f"- [이미지] {iss.get('description', '')}: {iss.get('reasoning', '')} ({iss.get('law_ref', '')})")
        if all_issues:
            parts.append("F4 라벨 검토 확정 지적사항:\n" + "\n".join(all_issues))

    return "\n".join(parts) if parts else ""


@router.post("/run")
def run_pipeline(case_id: str, body: RunRequest):
    """한글표시사항 시안 생성 (stream=true 면 SSE 스트리밍)"""
    docs = _get_documents(case_id)
    if not docs:
        raise HTTPException(status_code=400, detail="업로드된 서류가 없습니다. 먼저 서류 업로드 및 파싱을 실행하세요.")

    # F2에서 food_type 자동 보충
    body.food_type = _enrich_food_type(case_id, body.food_type)

    # 파이프라인 컨텍스트를 documents에 추가 (AI가 이전 기능 결과를 참고하도록)
    pipeline_context = _build_context_from_pipeline(case_id)
    if pipeline_context:
        docs.append({"file_name": "[파이프라인 이전 기능 결과]", "parsed_md": pipeline_context})

    # pipeline_steps upsert — running 상태로 전환
    try:
        get_supabase().table("pipeline_steps").upsert(
            {
                "case_id": case_id,
                "step_key": STEP_KEY,
                "step_name": STEP_NAME,
                "status": "running",
            },
            on_conflict="case_id,step_key",
        ).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if body.stream:
        return StreamingResponse(
            generate_label_stream(
                case_id=case_id,
                documents=docs,
                food_type=body.food_type,
                draft_label=body.draft_label,
            ),
            media_type="text/event-stream",
        )

    # 비스트리밍
    try:
        result = generate_label(
            case_id=case_id,
            documents=docs,
            food_type=body.food_type,
            draft_label=body.draft_label,
        )
    except Exception as e:
        get_supabase().table("pipeline_steps").upsert(
            {"case_id": case_id, "step_key": STEP_KEY, "status": "error"},
            on_conflict="case_id,step_key",
        ).execute()
        raise HTTPException(status_code=502, detail=str(e))

    # 결과 저장
    try:
        get_supabase().table("pipeline_steps").upsert(
            {
                "case_id": case_id,
                "step_key": STEP_KEY,
                "step_name": STEP_NAME,
                "status": "waiting_review",
                "ai_result": result,
            },
            on_conflict="case_id,step_key",
        ).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return result


@router.get("")
def get_label(case_id: str):
    """최신 시안 조회"""
    try:
        res = (
            get_supabase()
            .table("pipeline_steps")
            .select("*")
            .eq("case_id", case_id)
            .eq("step_key", STEP_KEY)
            .single()
            .execute()
        )
        return res.data
    except Exception:
        raise HTTPException(status_code=404, detail="시안이 없습니다. 먼저 생성해주세요.")


@router.patch("")
def confirm_label(case_id: str, body: ConfirmRequest):
    """담당자 최종 확정"""
    try:
        # 현재 ai_result를 final_result로 복사 + 확정자 기록
        step = (
            get_supabase()
            .table("pipeline_steps")
            .select("ai_result")
            .eq("case_id", case_id)
            .eq("step_key", STEP_KEY)
            .single()
            .execute()
        )
        ai_result = step.data.get("ai_result") if step.data else {}

        res = (
            get_supabase()
            .table("pipeline_steps")
            .upsert(
                {
                    "case_id": case_id,
                    "step_key": STEP_KEY,
                    "step_name": STEP_NAME,
                    "status": "completed",
                    "final_result": {**(ai_result or {}), "confirmed_by": body.confirmed_by},
                },
                on_conflict="case_id,step_key",
            )
            .execute()
        )
        return res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
