"""
기능5 한글표시사항 시안 생성 / 조회 / 확정 / 리포트 / 법령 검색
POST  /api/v1/cases/{case_id}/pipeline/feature/5/run
GET   /api/v1/cases/{case_id}/pipeline/feature/5
PATCH /api/v1/cases/{case_id}/pipeline/feature/5
GET   /api/v1/cases/{case_id}/pipeline/feature/5/report?format=docx|pdf
POST  /api/v1/cases/{case_id}/pipeline/feature/5/law-search
"""

import json
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from db.supabase_client import get_supabase
from services.step6_label import generate_label, generate_label_stream
from services.f5_report import generate_docx, generate_pdf
from services.f5_rag import search_law_chunks_extended

router = APIRouter(prefix="/cases/{case_id}/pipeline/feature/5", tags=["pipeline"])

STEP_KEY = "5"
STEP_NAME = "한글표시사항"


class RunRequest(BaseModel):
    food_type: Optional[str] = None
    draft_label: Optional[str] = None
    stream: bool = False


class ConfirmRequest(BaseModel):
    confirmed_by: str
    draft: Optional[Dict[str, Any]] = None


class LawSearchRequest(BaseModel):
    query: str
    match_count: int = 3
    # 주변 청크 확장 범위 (앞뒤 각각 몇 개 청크를 추가로 가져올지)
    # 기본 1 — PDF 청킹으로 잘린 원문을 주변 청크로 복원
    context_window: int = 1


def _get_documents(case_id: str) -> list:
    sb = get_supabase()

    try:
        res = (
            sb.table("documents")
            .select("parsed_md, file_name")
            .eq("case_id", case_id)
            .execute()
        )
        docs = [
            d for d in (res.data or [])
            if d.get("parsed_md")
        ]
        if docs:
            return docs
    except Exception:
        pass

    f0 = _fetch_pipeline_result(case_id, "0")
    if f0:
        return [{
            "file_name": "[f0 OCR parsed result]",
            "parsed_md": json.dumps(f0, ensure_ascii=False, indent=2),
        }]

    return []


# ════════════════════════════════════════════════════════════
# f0 ~ F4 → F5 파이프라인 자동 연결 (PM 임의 구현)
# ════════════════════════════════════════════════════════════

def _fetch_pipeline_result(case_id: str, step_key: str) -> dict | None:
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
    if body_food_type:
        return body_food_type
    f2 = _fetch_pipeline_result(case_id, "2")
    if f2:
        return f2.get("food_type")
    return None


def _build_context_from_pipeline(case_id: str) -> str:
    parts = []

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

    f1 = _fetch_pipeline_result(case_id, "1")
    if f1:
        parts.append(f"F1 수입판정: {f1.get('verdict', '')}")

    f2 = _fetch_pipeline_result(case_id, "2")
    if f2:
        parts.append(f"식품유형: {f2.get('food_type', '')}")
        if f2.get("is_alcohol"):
            parts.append("주류 제품")

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
    docs = _get_documents(case_id)
    if not docs:
        raise HTTPException(status_code=400, detail="업로드된 서류가 없습니다. 먼저 서류 업로드 및 파싱을 실행하세요.")

    body.food_type = _enrich_food_type(case_id, body.food_type)

    pipeline_context = _build_context_from_pipeline(case_id)
    if pipeline_context:
        docs.append({"file_name": "[파이프라인 이전 기능 결과]", "parsed_md": pipeline_context})

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
    try:
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
        ai_result = ai_result or {}

        final_result: Dict[str, Any] = {**ai_result}

        if body.draft is not None:
            phase2 = dict(ai_result.get("phase2") or {})
            phase2["draft"] = body.draft
            final_result["phase2"] = phase2

        final_result["confirmed_by"] = body.confirmed_by

        res = (
            get_supabase()
            .table("pipeline_steps")
            .upsert(
                {
                    "case_id": case_id,
                    "step_key": STEP_KEY,
                    "step_name": STEP_NAME,
                    "status": "completed",
                    "final_result": final_result,
                },
                on_conflict="case_id,step_key",
            )
            .execute()
        )
        return res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report")
def download_report(
    case_id: str,
    format: str = Query(default="docx", pattern="^(docx|pdf)$"),
):
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
        record = res.data
    except Exception:
        raise HTTPException(status_code=404, detail="시안 데이터를 찾을 수 없습니다.")

    if not record:
        raise HTTPException(status_code=404, detail="시안 데이터를 찾을 수 없습니다.")

    status = record.get("status")
    final_result = record.get("final_result")
    if status != "completed" or not final_result:
        raise HTTPException(
            status_code=400,
            detail="확정된 시안만 다운로드할 수 있습니다. '확정' 버튼을 먼저 눌러주세요.",
        )

    try:
        if format == "docx":
            content, filename = generate_docx(record)
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            content, filename = generate_pdf(record)
            media_type = "application/pdf"
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"리포트 생성 실패: {e}")

    quoted_name = quote(filename, safe="")
    headers = {
        "Content-Disposition": (
            f"attachment; filename=\"report.{format}\"; "
            f"filename*=UTF-8''{quoted_name}"
        )
    }
    return Response(content=content, media_type=media_type, headers=headers)


@router.post("/law-search")
def search_laws(case_id: str, body: LawSearchRequest):
    """
    법령 원문 시맨틱 검색 + 주변 청크 확장.

    Pinecone f5-law-chunks 에서 쿼리와 유사한 청크를 찾은 후,
    각 매칭의 chunk_index ± context_window 범위를 추가로 가져와
    이어붙인 "확장된 원문" 반환. PDF 청킹으로 인해 조문이 잘리는 문제를 완화.

    case_id 는 prefix 요구사항 때문에 받지만 실제 검색에는 사용하지 않음.
    """
    query = (body.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="검색 쿼리가 비어있습니다.")

    match_count = max(1, min(10, body.match_count))
    context_window = max(0, min(5, body.context_window))

    try:
        results = search_law_chunks_extended(
            query=query,
            match_count=match_count,
            context_window=context_window,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"법령 검색 실패: {e}")

    return {
        "query": query,
        "results": results,
        "count": len(results),
        "context_window": context_window,
    }