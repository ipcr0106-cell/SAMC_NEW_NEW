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

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.supabase_client import get_supabase
from models.judgment import (Feature1Input, Feature1Output, Ingredient,
                                     ProcessConditions)
from services.feature1 import run_feature1

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


def _to_pipeline_result(out: Feature1Output) -> dict:
    """백엔드 Feature1Output 을 팀 약속 Feature1Result (types/pipeline.ts) 형식으로 변환.

    약속 필드:
        ingredients[], verdict, import_possible, fail_reasons[], standards_check[]
    추가로 _internal 키에 상세 결과 포함 (프론트에서 선택 활용).
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
async def get_feature1(case_id: str) -> Feature1GetResponse:
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
async def run_feature1_endpoint(
    case_id: str,
    body: Feature1RunRequest,
) -> dict:
    ingredients = body.ingredients
    process_conditions = body.process_conditions

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
        out = run_feature1(
            ingredients=ingredients,
            food_type=body.food_type,
            process_conditions=process_conditions or ProcessConditions(),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={
                "error": "FEATURE1_RUN_FAILED",
                "message": f"기능1 실행 실패: {exc}",
                "feature": 1,
            },
        )

    ai_result = _to_pipeline_result(out)
    _upsert_pipeline_step(case_id, "waiting_review", ai_result)

    return {
        "case_id": case_id,
        "status": "waiting_review",
        "ai_result": ai_result,
    }


# ============================================================
# PATCH /feature/1 — 담당자 수정
# ============================================================


class Feature1UpdateRequest(BaseModel):
    final_result: dict  # Feature1Result (types/pipeline.ts 약속)
    edit_reason: Optional[str] = None


@router.patch("/{case_id}/pipeline/feature/1")
async def update_feature1(
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
# POST /feature/1/confirm — 담당자 확인 완료
# ============================================================


@router.post("/{case_id}/pipeline/feature/1/confirm")
async def confirm_feature1(case_id: str) -> dict:
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
