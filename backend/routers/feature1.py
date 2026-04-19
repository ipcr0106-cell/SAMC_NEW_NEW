"""기능1 파이프라인 엔드포인트.

담당: 병찬
경로: /api/v1/cases/{case_id}/pipeline/feature/1/...

엔드포인트:
    GET    /.../feature/1           결과 조회 (pipeline_steps.ai_result 또는 final_result)
    POST   /.../feature/1/run       기능1 실행 (DB 쿼리 → 판정)
    PATCH  /.../feature/1           담당자 수정 (final_result + edit_reason)
    POST   /.../feature/1/confirm   담당자 확인 완료 → 다음 단계 진행

참고:
    - 공통 테이블 cases/pipeline_steps 는 팀컨벤션 §2-4 공유 파일
    - 이 라우터는 조회·업데이트만 수행, 스키마 변경은 별도 PR
    - 입력 원재료 목록은 documents.parsed_md 에서 추출 (추후 연결)
"""

from __future__ import annotations

import asyncio
import io
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from fpdf import FPDF
from pydantic import BaseModel

from config.feature_flags import F1_REQUIRE_HITL0_APPROVAL, should_use_new_pipeline
from db.supabase_client import get_supabase
from models.f1_hitl import (
    F0ApproveRequest,
    F0ApproveResponse,
    F0EditRequest,
    F0EditResponse,
    HITL1DecisionsRequest,
    HITL1DecisionsResponse,
    HITL2ConfirmRequest,
    HITL2ConfirmResponse,
)
from models.f1_law_citation import RagJudgement
from models.f1_types import F1Output
from models.judgment import (Feature1Input, Feature1Output, Ingredient,
                                     ProcessConditions)
from services.feature1 import run_feature1, run_feature1_with_rag, run_feature1_v2
from services.f1_hitl_service import (
    apply_f0_edit,
    approve_f0,
    confirm_hitl2,
    submit_hitl1_decisions,
)

router = APIRouter(
    prefix="/api/v1/cases",
    tags=["feature1"],
)


# ============================================================
# 공통 헬퍼
# ============================================================


def _fetch_pipeline_step(
    case_id: str, step_key: str = "1"
) -> Optional[dict]:
    supabase = get_supabase()
    result = supabase.table("pipeline_steps") \
        .select(
            "id, case_id, step_key, step_name, status, "
            "ai_result, final_result, edit_reason, "
            "law_references, created_at, updated_at"
        ) \
        .eq("case_id", case_id) \
        .eq("step_key", step_key) \
        .limit(1) \
        .execute()
    return result.data[0] if result.data else None


def _upsert_pipeline_step(
    case_id: str,
    status: str,
    ai_result: dict,
) -> None:
    supabase = get_supabase()
    supabase.table("pipeline_steps").upsert(
        {
            "case_id": case_id,
            "step_key": "1",
            "step_name": "import_check",
            "status": status,
            "ai_result": ai_result,  # supabase-py가 dict를 JSONB로 자동 직렬화
        },
        on_conflict="case_id,step_key"
    ).execute()


def _to_pipeline_result(
    out: Feature1Output,
    rag: Optional[RagJudgement] = None,
    conflict_status: str = "rag_skipped",
) -> dict:
    """백엔드 Feature1Output 을 팀 약속 Feature1Result (types/pipeline.ts) 형식으로 변환.

    약속 필드:
        ingredients[], verdict, import_possible, fail_reasons[], standards_check[]
    추가로 _internal 키에 상세 결과 포함 (프론트에서 선택 활용).

    Phase 4-B (RAG + HITL):
        rag, conflict_status default 유지로 기존 호출자(`run_feature1` 단독)는 후방 호환.
    """
    verdict_to_status = {
        "permitted": "allowed",
        "restricted": "allowed",
        "prohibited": "not_found",
        "unidentified": "not_found",
    }

    # H-NEW-1: 합성향료 원재료는 status=synthetic_flavor_warning 으로 override
    synthetic_set = set(out.synthetic_flavor_ingredients or [])

    ingredients_slim: list[dict] = []
    if out.aggregation:
        for r in out.aggregation.results:
            status: str
            if r.ingredient.name in synthetic_set:
                status = "synthetic_flavor_warning"
            else:
                status = verdict_to_status.get(r.verdict, "not_found")
            ingredients_slim.append(
                {
                    "name": r.ingredient.name,
                    "percentage": r.ingredient.percentage,
                    "status": status,
                    "law_ref": r.law_source,
                }
            )
    for h in out.forbidden_hits:
        ingredients_slim.append(
            {
                "name": h.name_ko,
                "percentage": None,
                "status": "not_found",
                "law_ref": h.law_source,
                "message": h.reason,
            }
        )

    fail_reasons: list[str] = []
    if out.forbidden_hits:
        fail_reasons.append(
            "절대 금지 원료: " + ", ".join(h.name_ko for h in out.forbidden_hits)
        )
    if out.aggregation and out.aggregation.prohibited > 0:
        fail_reasons.append(f"별표3 원료 {out.aggregation.prohibited}건 포함")
    if out.standards_check:
        for v in out.standards_check.violations:
            fail_reasons.append(f"{v.item_name} 기준치 초과")
        for cg in out.standards_check.compound_results:
            if cg.status == "fail":
                fail_reasons.append(f"{cg.group} 합산 {cg.total}>{cg.limit} {cg.unit}")

    standards_slim: list[dict] = []
    if out.standards_check:
        for c in out.standards_check.checks:
            # H8 수정: no_data는 actual=null 명시, 실측 0과 구분
            actual: Optional[float] = None
            if c.actual_value:
                try:
                    actual = float(c.actual_value.split()[0])
                except (ValueError, IndexError):
                    actual = None

            threshold: Optional[float] = None
            unit = ""
            if c.max_limit:
                try:
                    parts = c.max_limit.split()
                    threshold = float(parts[0])
                    unit = parts[1] if len(parts) > 1 else ""
                except (ValueError, IndexError):
                    # "불검출" 등 비수치는 threshold=None + unit=원문 보존 안 함
                    threshold = None
                    unit = ""
            status_map = {
                "pass": "pass",
                "fail": "fail",
                "no_data": "no_threshold",
                "warning": "no_threshold",
            }
            standards_slim.append(
                {
                    "ingredient_name": c.item_name,
                    "actual_value": actual,  # None(null) 허용
                    "unit": unit,
                    "threshold_value": threshold,
                    "threshold_text": c.max_limit,  # "불검출" 등 원문 보존
                    "status": status_map.get(c.status, "no_threshold"),
                    "law_ref": c.regulation_ref,
                }
            )

    return {
        "ingredients": ingredients_slim,
        "verdict": "수입가능" if out.import_possible else "수입불가",
        "import_possible": out.import_possible,
        "fail_reasons": fail_reasons,
        "standards_check": standards_slim,
        # 팀 약속 외 확장 정보 (프론트에서 선택 활용)
        "_internal": {
            "aggregation": out.aggregation.model_dump() if out.aggregation else None,
            "conditional_evaluations": [
                e.model_dump() for e in out.conditional_evaluations
            ],
            "forbidden_hits": [h.model_dump() for h in out.forbidden_hits],
            "escalations": out.escalations,
            "law_refs": [r.model_dump() for r in out.law_refs],
            # ── Phase 4-B: RAG + HITL ──
            "rag_verdict": rag.rag_verdict if rag else None,
            "rag_reasoning": rag.rag_reasoning if rag else None,
            "law_citations": (
                [c.model_dump() for c in rag.law_citations] if rag else []
            ),
            "conflict_status": conflict_status,
        },
    }


def _f1output_to_pipeline_result(out: F1Output) -> dict:
    """F1Output (신규 v2 파이프라인) → 팀 약속 Feature1Result (types/pipeline.ts) 형식 변환.

    verdict 한글 변환:
        permitted  → 수입가능
        restricted → 수입가능 (조건부)
        prohibited → 수입불가
        needs_review, 기타 → 검토 필요

    import_possible: verdict in ("permitted", "restricted") → True, 나머지 False.

    ingredients[]: evidence_external_data step=B enriched_summary 에서 추출.
    fail_reasons[]: warnings + step=A forbidden_hits.
    standards_check[]: evidence_external_data step=C checks.
    _internal: v2 전용 필드 + pipeline_version="v2".
    """
    _VERDICT_KO = {
        "permitted": "수입가능",
        "restricted": "수입가능 (조건부)",
        "prohibited": "수입불가",
        "needs_review": "검토 필요",
    }
    verdict_ko = _VERDICT_KO.get(out.verdict, "검토 필요")
    import_possible = out.verdict in ("permitted", "restricted")

    # ── ingredients: step=B enriched_summary ──────────────────
    ingredients_slim: list[dict] = []
    step_b_data: Optional[dict] = None
    step_a_data: Optional[dict] = None
    step_c_data: Optional[dict] = None
    for ev in out.evidence_external_data:
        if ev.get("step") == "B":
            step_b_data = ev
        elif ev.get("step") == "A":
            step_a_data = ev
        elif ev.get("step") == "C":
            step_c_data = ev

    if step_b_data:
        for item in step_b_data.get("enriched_summary", []):
            allow_v = item.get("allow_verdict", "unidentified")
            # allow_verdict: "allowed"→"허용", "restricted"→"조건부", "prohibited"→"금지", "unidentified"→"미확인"
            status_map = {
                "allowed": "allowed",
                "restricted": "allowed",
                "prohibited": "not_found",
                "unidentified": "not_found",
            }
            ingredients_slim.append(
                {
                    "name": item.get("name", ""),
                    "percentage": None,
                    "status": status_map.get(allow_v, "not_found"),
                    "law_ref": None,
                }
            )

    # ── fail_reasons: warnings + step A forbidden_hits ────────
    fail_reasons: list[str] = []
    for w in out.warnings:
        fail_reasons.append(w)
    if step_a_data:
        for h in step_a_data.get("forbidden_hits", []):
            reason = h.get("reason") or h.get("matched_name", "")
            if reason:
                fail_reasons.append(f"금지원료: {h.get('ingredient_name', '')} — {reason}")

    # ── standards_check: step=C checks ────────────────────────
    standards_slim: list[dict] = []
    if step_c_data:
        for ch in step_c_data.get("checks", []):
            actual: Optional[float] = None
            actual_raw = ch.get("actual_value")
            if actual_raw:
                try:
                    actual = float(str(actual_raw).split()[0])
                except (ValueError, IndexError):
                    actual = None

            threshold: Optional[float] = ch.get("threshold_value")
            unit = ch.get("unit_normalized") or ch.get("unit_original") or ""
            spec_raw = ch.get("spec_raw") or ""

            status_raw = ch.get("status", "no_data")
            status_map_c = {
                "pass": "pass",
                "fail": "fail",
                "review_needed": "no_threshold",
                "no_data": "no_threshold",
            }
            standards_slim.append(
                {
                    "ingredient_name": ch.get("ingredient_name", ""),
                    "actual_value": actual,
                    "unit": unit,
                    "threshold_value": threshold,
                    "threshold_text": spec_raw,
                    "status": status_map_c.get(status_raw, "no_threshold"),
                    "law_ref": ch.get("law_ref"),
                }
            )

    return {
        "ingredients": ingredients_slim,
        "verdict": verdict_ko,
        "import_possible": import_possible,
        "fail_reasons": fail_reasons,
        "standards_check": standards_slim,
        "_internal": {
            "evidence_laws": out.evidence_laws,
            "gmo_ingredients": out.gmo_ingredients,
            "api_call_stats": out.api_call_stats,
            "unit_conversions": out.unit_conversions,
            "pipeline_version": "v2",
        },
    }


def _record_to_json(row: dict, field: str) -> Any:
    """supabase-py는 JSONB를 dict로 자동 반환."""
    return row.get(field)


# ============================================================
# GET /feature/1 — 결과 조회
# ============================================================


class Feature1GetResponse(BaseModel):
    case_id: str
    status: str
    ai_result: Optional[dict] = None
    final_result: Optional[dict] = None
    edit_reason: Optional[str] = None
    law_references: Optional[Any] = None
    updated_at: Optional[str] = None


@router.get("/{case_id}/pipeline/feature/1", response_model=Feature1GetResponse)
def get_feature1(case_id: str) -> Feature1GetResponse:
    row = _fetch_pipeline_step(case_id, "1")
    if not row:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "FEATURE1_NOT_RUN",
                "message": "기능1이 아직 실행되지 않았습니다.",
                "feature": 1,
            },
        )
    return Feature1GetResponse(
        case_id=str(row["case_id"]),
        status=row["status"],
        ai_result=_record_to_json(row, "ai_result"),
        final_result=_record_to_json(row, "final_result"),
        edit_reason=row.get("edit_reason"),
        law_references=_record_to_json(row, "law_references"),
        # supabase-py는 timestamp를 str로 반환 → .isoformat() 불필요
        updated_at=row.get("updated_at"),
    )


# ============================================================
# f0 → F1 자동 연결: pipeline_steps(step_key='0')에서 입력 추출
# ============================================================

# 가열 관련 공정 코드
_HEAT_CODES = {"01", "02", "03", "04", "06", "07", "08", "09", "49", "91", "92"}
# 증류 관련 공정 코드
_DISTILL_CODES = {"35", "41", "42"}
# 발효 관련 공정 코드
_FERMENT_CODES = {"10", "16", "17", "18"}


def _fetch_f0_parsed_result(case_id: str) -> Optional[dict]:
    """f0(step_key='0')의 ai_result에서 ParsedResult를 가져온다."""
    supabase = get_supabase()
    result = supabase.table("pipeline_steps") \
        .select("ai_result") \
        .eq("case_id", case_id) \
        .eq("step_key", "0") \
        .eq("status", "completed") \
        .limit(1) \
        .execute()
    if not result.data:
        return None
    # supabase-py가 JSONB를 dict로 자동 파싱
    return result.data[0].get("ai_result")


def _convert_f0_to_f1_ingredients(parsed: dict) -> list[Ingredient]:
    """f0 ParsedResult.ingredients → F1 Ingredient 리스트 변환."""
    f0_ingredients = parsed.get("ingredients") or []
    result = []
    for item in f0_ingredients:
        # ratio: str → percentage: float 변환
        pct = None
        ratio_str = item.get("ratio", "")
        if ratio_str:
            try:
                pct = float(ratio_str)
            except (ValueError, TypeError):
                pass

        result.append(Ingredient(
            name=item.get("name", ""),
            percentage=pct,
            ins=item.get("ins_number") or None,
            cas=item.get("cas_number") or None,
        ))
    return result


def _convert_f0_to_process_conditions(parsed: dict) -> ProcessConditions:
    """f0 process_info.process_codes → F1 ProcessConditions 변환."""
    proc = parsed.get("process_info") or {}
    codes = set(proc.get("process_codes") or [])

    return ProcessConditions(
        is_heated=bool(codes & _HEAT_CODES) if codes else None,
        is_distilled=bool(codes & _DISTILL_CODES) if codes else None,
        is_fermented=bool(codes & _FERMENT_CODES) if codes else None,
    )


# ============================================================
# POST /feature/1/run — 실행
# ============================================================


class Feature1RunRequest(BaseModel):
    """기능1 실행 요청.

    - ingredients가 비어있거나 생략하면 → f0 파싱 결과에서 자동 추출
    - ingredients를 직접 보내면 → 그대로 사용 (테스트/오버라이드용)
    """

    ingredients: Optional[list[Ingredient]] = None
    food_type: Optional[str] = None
    process_conditions: Optional[ProcessConditions] = None


@router.post("/{case_id}/pipeline/feature/1/run")
def run_feature1_endpoint(
    case_id: str,
    body: Feature1RunRequest,
) -> dict:
    ingredients = body.ingredients
    process_conditions = body.process_conditions

    # HITL-0 게이트: F1_REQUIRE_HITL0_APPROVAL=true 시 F0 approved 상태 필수
    if F1_REQUIRE_HITL0_APPROVAL:
        supabase = get_supabase()
        f0_row = (
            supabase.table("pipeline_steps")
            .select("status")
            .eq("case_id", case_id)
            .eq("step_key", "0")
            .limit(1)
            .execute()
        )
        f0_status = f0_row.data[0]["status"] if f0_row.data else None
        if f0_status != "approved":
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "F0_NOT_APPROVED",
                    "message": (
                        "F0 파싱 결과가 담당자 승인을 받지 않았습니다. "
                        "먼저 /pipeline/feature/0/approve 를 호출하세요."
                    ),
                    "feature": 1,
                    "f0_status": f0_status,
                },
            )

    # ingredients가 없으면 f0 파싱 결과에서 자동 추출
    if not ingredients:
        parsed = _fetch_f0_parsed_result(case_id)
        if not parsed:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "F0_NOT_COMPLETED",
                    "message": "f0 파싱이 완료되지 않았습니다. 먼저 서류 업로드 및 파싱을 실행하세요.",
                    "feature": 1,
                },
            )
        ingredients = _convert_f0_to_f1_ingredients(parsed)
        if not ingredients:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "NO_INGREDIENTS",
                    "message": "f0 파싱 결과에 원재료가 없습니다.",
                    "feature": 1,
                },
            )
        # process_conditions도 없으면 f0에서 추출
        if not process_conditions:
            process_conditions = _convert_f0_to_process_conditions(parsed)

    try:
        # 옵션 B: f1_수정_요청_사항 §7 "async def 엔드포인트 금지" 룰 준수.
        # 엔드포인트는 sync 로 유지하고, async 서비스는 asyncio.run() 으로 호출.
        if should_use_new_pipeline(case_id):
            # ── 신규 v2 파이프라인 경로 ──────────────────────────────
            v2_out: F1Output = asyncio.run(
                run_feature1_v2(
                    ingredients=ingredients,
                    food_type=body.food_type,
                    food_type_hierarchy=None,
                    process_conditions=process_conditions or ProcessConditions(),
                )
            )
            ai_result = _f1output_to_pipeline_result(v2_out)
            # v2 verdict 기반 HITL status 결정
            new_status = (
                "needs_review"
                if v2_out.verdict in ("needs_review", "prohibited")
                else "waiting_review"
            )
        else:
            # ── 레거시 RAG 경로 (기본) ────────────────────────────────
            out, rag, conflict_status = asyncio.run(
                run_feature1_with_rag(
                    ingredients=ingredients,
                    food_type=body.food_type,
                    process_conditions=process_conditions or ProcessConditions(),
                    payload_for_rag={
                        "ingredients": [i.name for i in ingredients],
                        "food_type": body.food_type,
                    },
                )
            )
            ai_result = _to_pipeline_result(out, rag, conflict_status)
            # HITL status 결정 (총괄 §2.7 엄격)
            #   - conflict / rag_supplemented → needs_review (사람 결정 필요)
            #   - agreed / rag_unavailable / rag_skipped → waiting_review (기존 흐름)
            new_status = (
                "needs_review"
                if conflict_status in ("conflict", "rag_supplemented")
                else "waiting_review"
            )
    except HTTPException:
        # code-review MEDIUM-1: HITL-0 400 등 의미 있는 HTTPException 은 원본 그대로 전파.
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={
                "error": "FEATURE1_RUN_FAILED",
                "message": f"기능1 실행 실패: {exc}",
                "feature": 1,
            },
        )

    _upsert_pipeline_step(case_id, new_status, ai_result)

    return {
        "case_id": case_id,
        "status": new_status,
        "ai_result": ai_result,
    }


# ============================================================
# PATCH /feature/1 — 담당자 수정
# ============================================================


class Feature1UpdateRequest(BaseModel):
    final_result: dict  # Feature1Result (types/pipeline.ts 약속)
    edit_reason: Optional[str] = None


@router.patch("/{case_id}/pipeline/feature/1")
def update_feature1(
    case_id: str,
    body: Feature1UpdateRequest,
) -> dict:
    row = _fetch_pipeline_step(case_id, "1")
    if not row:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "FEATURE1_NOT_RUN",
                "message": "먼저 /run 으로 기능1을 실행해주세요.",
                "feature": 1,
            },
        )
    supabase = get_supabase()
    supabase.table("pipeline_steps").update({
        "final_result": body.final_result,   # dict → JSONB 자동 처리
        "edit_reason": body.edit_reason,
    }).eq("case_id", case_id).eq("step_key", "1").execute()
    return {"case_id": case_id, "updated": True}


# ============================================================
# POST /feature/1/confirm — 담당자 확인 완료 (레거시 + HITL-2 통합)
#
# Wave 3 W3-BE: HITL2ConfirmRequest Body가 있으면 HITL-2 서비스로 위임.
# Body 없는 레거시 호출(Body=None)은 기존 동작(status='completed') 유지.
# ============================================================


@router.post("/{case_id}/pipeline/feature/1/confirm", response_model=None)
def confirm_feature1(
    case_id: str,
    body: Optional[HITL2ConfirmRequest] = None,
) -> dict:
    # HITL-2 Body 있으면 Wave 3 서비스로 위임
    # code-review CRITICAL-1 fix: HITL2ConfirmResponse(BaseModel) 를 dict 로
    # 직렬화하여 legacy dict 분기와 응답 shape 일관성 확보.
    if body is not None:
        try:
            return confirm_hitl2(case_id, body).model_dump(mode="json")
        except ValueError as exc:
            error_msg = str(exc)
            if "존재하지 않습니다" in error_msg:
                raise HTTPException(
                    status_code=404,
                    detail={"error": "F1_STEP_NOT_FOUND", "message": error_msg},
                )
            raise HTTPException(
                status_code=400,
                detail={"error": "HITL2_CONFIRM_FAILED", "message": error_msg},
            )

    # 레거시: Body 없는 단순 확인 완료
    row = _fetch_pipeline_step(case_id, "1")
    if not row:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "FEATURE1_NOT_RUN",
                "message": "먼저 /run 으로 기능1을 실행해주세요.",
                "feature": 1,
            },
        )

    # COALESCE 대체: Python에서 처리 (final_result 없으면 ai_result 사용)
    final = row.get("final_result") or row.get("ai_result")

    supabase = get_supabase()
    supabase.table("pipeline_steps").update({
        "status": "completed",
        "final_result": final,
    }).eq("case_id", case_id).eq("step_key", "1").execute()

    return {"case_id": case_id, "status": "completed"}


# ============================================================
# GET /feature/1/report — PDF report download
# ============================================================

_FONT_PATH = "C:/Windows/Fonts/malgun.ttf"
_FONT_BOLD_PATH = "C:/Windows/Fonts/malgunbd.ttf"

_VERDICT_LABEL_KO = {
    "permitted": "허용",
    "restricted": "조건부",
    "prohibited": "금지",
    "unidentified": "미확인",
}

_STATUS_LABEL_KO = {
    "allowed": "허용",
    "not_found": "미확인/금지",
    "synthetic_flavor_warning": "합성향료",
}

_STD_STATUS_LABEL = {
    "pass": "적합",
    "fail": "부적합",
    "no_threshold": "기준 없음",
}


class _F1ReportPDF(FPDF):
    """F1 import check report PDF — mirrors F4 _ReportPDF pattern."""

    def __init__(self):
        super().__init__()
        self.add_font("malgun", "", _FONT_PATH, uni=True)
        self.add_font("malgun", "B", _FONT_BOLD_PATH, uni=True)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        self.set_font("malgun", "B", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, "SAMC AI — F1 수입 가능 판정 레포트", align="C")
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
        self.multi_cell(0, 6, str(text))
        self.ln(2)

    def badge(self, label: str, color: tuple):
        self.set_font("malgun", "B", 10)
        self.set_fill_color(*color)
        self.set_text_color(255, 255, 255)
        w = self.get_string_width(label) + 10
        self.cell(w, 8, label, fill=True, align="C")
        self.set_text_color(30, 30, 30)
        self.ln(10)

    def kv_row(self, key: str, value):
        self.set_font("malgun", "B", 10)
        self.cell(40, 7, key)
        self.set_font("malgun", "", 10)
        self.multi_cell(0, 7, str(value or "-"))
        self.ln(1)


def _build_report_pdf(case_id: str, result: dict, row: dict) -> bytes:
    """Build F1 report PDF bytes from pipeline_steps row."""
    status = row.get("status", "pending")
    ingredients = result.get("ingredients", [])
    verdict = result.get("verdict", "-")
    import_possible = result.get("import_possible")
    fail_reasons = result.get("fail_reasons", [])
    standards = result.get("standards_check", [])
    internal = result.get("_internal", {})
    law_refs = internal.get("law_refs", [])
    escalations = internal.get("escalations", [])
    forbidden = internal.get("forbidden_hits", [])

    pdf = _F1ReportPDF()
    pdf.add_page()

    # ── 1. Overview ──
    pdf.section_title("1. 판정 개요")
    pdf.kv_row("케이스 ID", case_id)
    pdf.kv_row("검토 상태", {"pending": "대기", "waiting_review": "검토 대기",
                          "completed": "완료"}.get(status, status))
    pdf.kv_row("레포트 생성", datetime.now().strftime("%Y-%m-%d %H:%M"))
    pdf.ln(2)

    pdf.sub_title("종합 판정")
    if import_possible is True:
        pdf.badge("수입 가능", (34, 139, 34))
    elif import_possible is False:
        pdf.badge("수입 불가", (200, 30, 30))
    else:
        pdf.badge("검토 필요", (210, 150, 0))

    pdf.kv_row("판정 사유", verdict)
    if row.get("edit_reason"):
        pdf.kv_row("수정 사유", row["edit_reason"])
    if fail_reasons:
        pdf.kv_row("불가 사유", "; ".join(fail_reasons))
    pdf.ln(2)

    # ── 2. Forbidden hits ──
    if forbidden:
        pdf.section_title("2. 절대 금지 원료")
        for i, h in enumerate(forbidden, 1):
            pdf.sub_title(f"  {i}. {h.get('name_ko', '-')}")
            pdf.kv_row("분류", h.get("category", "-"))
            pdf.kv_row("법령", h.get("law_source", "-"))
            pdf.kv_row("사유", h.get("reason", "-"))
            pdf.ln(2)

    # ── 3. Ingredients ──
    section_num = 3 if forbidden else 2
    pdf.section_title(f"{section_num}. 원재료 판정")
    if not ingredients:
        pdf.body_text("원재료 데이터가 없습니다.")
    else:
        for ing in ingredients:
            name = ing.get("name", "-")
            pct = ing.get("percentage")
            pct_str = f"{pct}%" if pct is not None else "-"
            status_label = _STATUS_LABEL_KO.get(ing.get("status", ""), ing.get("status", ""))
            law = ing.get("law_ref") or "-"
            pdf.kv_row(f"{name} ({pct_str})", f"{status_label} | {law}")
        pdf.ln(2)

    # ── 4. Standards check ──
    section_num += 1
    pdf.section_title(f"{section_num}. 기준치 검사")
    if not standards:
        pdf.body_text("기준치 검사 데이터가 없습니다.")
    else:
        for s in standards:
            name = s.get("ingredient_name", "-")
            actual = s.get("actual_value")
            threshold = s.get("threshold_text") or s.get("threshold_value") or "-"
            unit = s.get("unit", "")
            std_status = _STD_STATUS_LABEL.get(s.get("status", ""), s.get("status", ""))
            actual_str = f"{actual} {unit}".strip() if actual is not None else "미제공"
            pdf.kv_row(name, f"{actual_str} / 기준 {threshold} [{std_status}]")
        pdf.ln(2)

    # ── 5. Law references ──
    section_num += 1
    pdf.section_title(f"{section_num}. 적용 법령")
    if not law_refs:
        pdf.body_text("적용 법령이 없습니다.")
    else:
        for ref in law_refs:
            source = ref.get("law_source", "-")
            article = ref.get("law_article") or ""
            pdf.body_text(f"  - {source} {article}".strip())
    pdf.ln(2)

    # ── 6. RAG 법령 인용 (Phase 4-B) ──
    # rag_verdict 또는 law_citations 가 있으면 렌더 (rag_skipped 는 생략).
    rag_verdict = internal.get("rag_verdict")
    rag_reasoning = internal.get("rag_reasoning")
    law_citations = internal.get("law_citations", [])
    conflict_status = internal.get("conflict_status", "rag_skipped")

    _CONFLICT_LABEL = {
        "agreed": "DB·RAG 일치",
        "conflict": "DB·RAG 충돌 (담당자 결정)",
        "rag_supplemented": "RAG 보완 판정",
        "rag_unavailable": "RAG 호출 실패",
        "rag_skipped": "RAG 미호출",
    }
    _RAG_VERDICT_LABEL = {
        "permitted": "허용",
        "restricted": "조건부 허용",
        "prohibited": "금지",
        "unidentified": "불명확",
        "error": "판정 오류",
    }
    _NS_LABEL = {
        "additive_code_text": "식품첨가물공전",
        "food_code_text": "식품공전",
        "health_food_text": "건강기능식품공전",
        "temporary_standard": "한시적 기준·규격",
        "functional_labeling": "기능성표시 고시",
    }

    if rag_verdict or law_citations:
        section_num += 1
        pdf.section_title(f"{section_num}. RAG 법령 인용 (AI 판정 근거)")
        pdf.kv_row(
            "충돌 상태",
            _CONFLICT_LABEL.get(conflict_status, conflict_status),
        )
        if rag_verdict:
            pdf.kv_row(
                "RAG 판정",
                _RAG_VERDICT_LABEL.get(rag_verdict, rag_verdict),
            )
        if rag_reasoning:
            pdf.kv_row("RAG 근거", rag_reasoning)

        if law_citations:
            pdf.ln(1)
            pdf.sub_title(f"인용 청크 ({len(law_citations)}건)")
            for i, c in enumerate(law_citations, 1):
                ns = _NS_LABEL.get(c.get("namespace", ""), c.get("namespace", ""))
                reg = c.get("regulation_id") or ""
                sec = c.get("section_path") or ""
                header = f"  [{i}] {ns}"
                if reg:
                    header += f" {reg}"
                if sec:
                    header += f" · {sec}"
                pdf.body_text(header)
                text = c.get("text", "")
                # PDF 내 과도한 길이 방지 — 400자 이후 truncate
                if len(text) > 400:
                    text = text[:400] + "..."
                pdf.body_text(f"     {text}")
                score = c.get("score")
                if isinstance(score, (int, float)):
                    pdf.body_text(f"     (score: {score:.3f})")
                pdf.ln(1)
        pdf.ln(2)

    # ── 7. Escalations ──
    if escalations:
        section_num += 1
        pdf.section_title(f"{section_num}. 에스컬레이션")
        for esc in escalations:
            pdf.kv_row(esc.get("trigger_type", "-"), esc.get("reason", "-"))
        pdf.ln(2)

    return pdf.output()


@router.get("/{case_id}/pipeline/feature/1/report")
def download_feature1_report(case_id: str):
    """F1 판정 결과를 PDF 레포트로 다운로드."""
    row = _fetch_pipeline_step(case_id, "1")
    if not row:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "FEATURE1_NOT_RUN",
                "message": "기능1이 아직 실행되지 않았습니다.",
                "feature": 1,
            },
        )
    result = _record_to_json(row, "final_result") or _record_to_json(row, "ai_result") or {}
    pdf_bytes = _build_report_pdf(case_id, result, row)
    filename = f"F1_report_{case_id}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ============================================================
# HITL 엔드포인트 (Wave 3 W3-BE 추가)
# 05_HITL_플로우_설계.md §3-3, §4-3, §5-3
# 기존 F1 엔드포인트는 건드리지 않음.
# ============================================================


@router.patch(
    "/{case_id}/pipeline/feature/0",
    response_model=F0EditResponse,
    summary="HITL-0: F0 파싱 결과 편집",
)
def patch_f0_edit(case_id: str, body: F0EditRequest) -> F0EditResponse:
    """F0 파싱 결과를 담당자가 편집한다.

    - final_result 를 갱신하고 status 를 'completed' 로 강등한다.
    - 편집 후에는 /approve 를 다시 호출해야 F1 실행 가능(flag on 기준).
    - status='locked' 또는 'confirmed' 에서는 403 반환.
    """
    try:
        return apply_f0_edit(case_id, body)
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "F0_LOCKED",
                "message": str(exc),
            },
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "F0_STEP_NOT_FOUND",
                "message": str(exc),
            },
        )


@router.post(
    "/{case_id}/pipeline/feature/0/approve",
    response_model=F0ApproveResponse,
    summary="HITL-0: F0 파싱 결과 승인",
)
def post_f0_approve(case_id: str, body: F0ApproveRequest) -> F0ApproveResponse:
    """F0 파싱 결과를 담당자가 승인한다.

    - pipeline_steps(step_key='0').status = 'approved' 로 전이.
    - 이후 F1/F2/F3 실행 가능(F1_REQUIRE_HITL0_APPROVAL=true 기준).
    """
    try:
        return approve_f0(case_id, body)
    except ValueError as exc:
        status_code = 404 if "존재하지 않습니다" in str(exc) else 400
        raise HTTPException(
            status_code=status_code,
            detail={
                "error": "F0_APPROVE_FAILED",
                "message": str(exc),
            },
        )


@router.post(
    "/{case_id}/pipeline/feature/1/hitl1-decisions",
    response_model=HITL1DecisionsResponse,
    summary="HITL-1: 불확실 원재료 / 자동 판정 불가 처리",
)
def post_hitl1_decisions(
    case_id: str, body: HITL1DecisionsRequest
) -> HITL1DecisionsResponse:
    """HITL-1 담당자 결정을 제출한다.

    - 모든 에스컬레이션에 ack 하면 status='waiting_review'.
    - 일부만 ack 하면 status='needs_review' 유지.
    - 모든 에스컬레이션 ack 후에만 HITL-2 confirm 가능.
    """
    try:
        return submit_hitl1_decisions(case_id, body)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "F1_STEP_NOT_FOUND",
                "message": str(exc),
            },
        )


# NOTE: HITL-2 POST /feature/1/confirm 은 위 confirm_feature1 내부에서 처리됨.
# (HITL2ConfirmRequest Body 존재 여부로 레거시/HITL-2 분기)
