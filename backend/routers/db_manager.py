"""DB 직접 관리 — 사용자가 추가한 항목 한정 CRUD.

담당: 병찬
참고: 개발계획서 §3-5 "DB 직접 관리 (사용자가 추가한 항목 한정 CRUD)"

원칙:
    - 모든 수정/삭제는 `created_by = 현재 로그인 사용자`인 항목만 가능
    - 시스템 초기 데이터(created_by IS NULL) 또는 다른 사용자 항목 → 조회만

대상 테이블 (기능1):
    - f1_allowed_ingredients
    - f1_thresholds (= f1_additive_limits + f1_safety_standards 통합 뷰)
    - f1_forbidden_ingredients

경로:
    GET    /api/v1/admin/db/{table}           목록 조회
    POST   /api/v1/admin/db/{table}           신규 추가
    PATCH  /api/v1/admin/db/{table}/{id}      수정 (본인 항목만)
    DELETE /api/v1/admin/db/{table}/{id}      삭제 (본인 항목만)

인증:
    X-User-Id 헤더로 Supabase Auth 사용자 UUID 전달 (미들웨어 미구현 시 임시).
    실제 운영에서는 FastAPI Depends + Supabase JWT 검증으로 교체.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase

router = APIRouter(
    prefix="/api/v1/admin/db",
    tags=["db-manager"],
)


# ============================================================
# 테이블 허용 목록 + 허용 컬럼 화이트리스트
# ============================================================

_ALLOWED_TABLES = {
    "f1_allowed_ingredients": {
        "columns": [
            "name_ko",
            "name_en",
            "scientific_name",
            "ins_number",
            "cas_number",
            "allowed_status",
            "conditions",
            "law_source",
            "is_verified",
        ],
        "list_columns": (
            "id, name_ko, name_en, scientific_name, ins_number, cas_number, "
            "allowed_status, conditions, law_source, is_verified, created_by, "
            "created_at, updated_at"
        ),
        "order_by": "name_ko",
    },
    "f1_additive_limits": {
        "columns": [
            "food_type",
            "additive_name",
            "ins_number",
            "max_ppm",
            "combined_group",
            "combined_max",
            "conversion_factor",
            "colorant_category",
            "condition_text",
            "regulation_ref",
            "is_verified",
        ],
        "list_columns": (
            "id, food_type, additive_name, max_ppm, combined_group, combined_max, "
            "conversion_factor, colorant_category, condition_text, regulation_ref, "
            "is_verified, created_by, created_at, updated_at"
        ),
        "order_by": "food_type, additive_name",
    },
    "f1_safety_standards": {
        "columns": [
            "food_type",
            "standard_type",
            "target_name",
            "max_limit",
            "regulation_ref",
            "condition_text",
            "is_verified",
        ],
        "list_columns": (
            "id, food_type, standard_type, target_name, max_limit, "
            "regulation_ref, condition_text, is_verified, created_by, "
            "created_at, updated_at"
        ),
        "order_by": "food_type, target_name",
    },
    "f1_forbidden_ingredients": {
        "columns": [
            "name_ko",
            "name_en",
            "aliases",
            "category",
            "law_source",
            "reason",
            "is_verified",
        ],
        "list_columns": (
            "id, name_ko, name_en, aliases, category, law_source, reason, "
            "is_verified, created_by, created_at, updated_at"
        ),
        "order_by": "name_ko",
    },
}

TableName = Literal[
    "f1_allowed_ingredients",
    "f1_additive_limits",
    "f1_safety_standards",
    "f1_forbidden_ingredients",
]


# ============================================================
# 헬퍼
# ============================================================


def _require_table(table: str) -> dict:
    meta = _ALLOWED_TABLES.get(table)
    if not meta:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "UNKNOWN_TABLE",
                "message": f"허용되지 않은 테이블: {table}",
                "feature": 1,
            },
        )
    return meta


def _filter_columns(payload: dict, allowed: list[str]) -> dict:
    return {k: v for k, v in payload.items() if k in allowed}


def _user_id(x_user_id: Optional[str]) -> Optional[UUID]:
    if not x_user_id:
        return None
    try:
        return UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_USER_ID",
                "message": "X-User-Id 헤더는 UUID 형식이어야 합니다.",
                "feature": 1,
            },
        )


def _parse_uuid(row_id: str) -> UUID:
    """C-NEW-3 가드: row_id 가 UUID 형식이 아니면 500 대신 400 반환."""
    try:
        return UUID(row_id)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_ID",
                "message": "row_id 는 UUID 형식이어야 합니다.",
                "feature": 1,
            },
        )


def _check_ownership(table: str, row_id: str, user_uuid: UUID) -> None:
    row_uuid = _parse_uuid(row_id)
    supabase = get_supabase()
    result = supabase.table(table) \
        .select("created_by") \
        .eq("id", str(row_uuid)) \
        .limit(1).execute()
    if not result.data:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "NOT_FOUND",
                "message": "해당 항목이 존재하지 않습니다.",
                "feature": 1,
            },
        )
    created_by = result.data[0].get("created_by")
    # supabase-py는 UUID를 str로 반환 → str(user_uuid)로 비교
    if created_by is None or created_by != str(user_uuid):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "FORBIDDEN",
                "message": "본인이 추가한 항목만 수정/삭제할 수 있습니다.",
                "feature": 1,
            },
        )


# ============================================================
# GET /admin/db/{table}
# ============================================================


@router.get("/{table}")
def list_rows(
    table: TableName,
    only_mine: bool = Query(False, description="본인 추가 항목만"),
    only_unverified: bool = Query(False, description="is_verified=false 만"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
) -> dict:
    meta = _require_table(table)
    user_uuid = _user_id(x_user_id)
    supabase = get_supabase()

    # count="exact" 로 전체 건수 포함 쿼리
    query = supabase.table(table).select(meta["list_columns"], count="exact")

    if only_mine:
        if not user_uuid:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "USER_ID_REQUIRED",
                    "message": "only_mine=true 에는 X-User-Id 헤더가 필요합니다.",
                    "feature": 1,
                },
            )
        query = query.eq("created_by", str(user_uuid))
    if only_unverified:
        query = query.eq("is_verified", False)

    # 정렬 + 페이지네이션
    order_cols = [c.strip() for c in meta["order_by"].split(",")]
    for col in order_cols:
        query = query.order(col)

    result = query.range(offset, offset + limit - 1).execute()

    return {
        "table": table,
        "total": result.count,
        "limit": limit,
        "offset": offset,
        "items": result.data,
    }


# ============================================================
# POST /admin/db/{table}
# ============================================================


class CreateRequest(BaseModel):
    data: dict


@router.post("/{table}")
def create_row(
    table: TableName,
    body: CreateRequest,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
) -> dict:
    meta = _require_table(table)
    user_uuid = _user_id(x_user_id)
    if not user_uuid:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "USER_ID_REQUIRED",
                "message": "새 항목 추가에는 X-User-Id 헤더가 필요합니다.",
                "feature": 1,
            },
        )

    data = _filter_columns(body.data, meta["columns"])
    if not data:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "NO_ALLOWED_FIELDS",
                "message": f"허용된 컬럼 없음. 가능: {meta['columns']}",
                "feature": 1,
            },
        )

    data["created_by"] = str(user_uuid)

    supabase = get_supabase()
    result = supabase.table(table).insert(data).execute()
    new_id = result.data[0]["id"]
    return {"table": table, "id": str(new_id)}


# ============================================================
# PATCH /admin/db/{table}/{id}
# ============================================================


class UpdateRequest(BaseModel):
    data: dict


@router.patch("/{table}/{row_id}")
def update_row(
    table: TableName,
    row_id: str,
    body: UpdateRequest,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
) -> dict:
    meta = _require_table(table)
    user_uuid = _user_id(x_user_id)
    if not user_uuid:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "USER_ID_REQUIRED",
                "message": "X-User-Id 필요",
                "feature": 1,
            },
        )
    _check_ownership(table, row_id, user_uuid)

    patch = _filter_columns(body.data, meta["columns"])
    if not patch:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "NO_ALLOWED_FIELDS",
                "message": f"허용된 컬럼 없음. 가능: {meta['columns']}",
                "feature": 1,
            },
        )

    supabase = get_supabase()
    supabase.table(table).update(patch).eq("id", row_id).execute()
    return {"table": table, "id": row_id, "updated": True}


# ============================================================
# DELETE /admin/db/{table}/{id}
# ============================================================


@router.delete("/{table}/{row_id}")
def delete_row(
    table: TableName,
    row_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
) -> dict:
    _require_table(table)
    user_uuid = _user_id(x_user_id)
    if not user_uuid:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "USER_ID_REQUIRED",
                "message": "X-User-Id 필요",
                "feature": 1,
            },
        )
    _check_ownership(table, row_id, user_uuid)

    supabase = get_supabase()
    supabase.table(table).delete().eq("id", row_id).execute()
    return {"table": table, "id": row_id, "deleted": True}


# ============================================================
# POST /admin/db/{table}/{id}/verify  — 검수 완료 표시
# ============================================================


@router.post("/{table}/{row_id}/verify")
def mark_verified(
    table: TableName,
    row_id: str,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
) -> dict:
    _require_table(table)
    user_uuid = _user_id(x_user_id)
    if not user_uuid:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "USER_ID_REQUIRED",
                "message": "X-User-Id 필요",
                "feature": 1,
            },
        )
    row_uuid = _parse_uuid(row_id)
    now_iso = datetime.now(timezone.utc).isoformat()

    supabase = get_supabase()
    # verified_by 컬럼이 있는 테이블만 (thresholds 계열)
    if table in ("f1_additive_limits", "f1_safety_standards"):
        supabase.table(table).update({
            "is_verified": True,
            "verified_by": str(user_uuid),
            "verified_at": now_iso,
        }).eq("id", str(row_uuid)).execute()
    else:
        supabase.table(table).update({
            "is_verified": True,
        }).eq("id", str(row_uuid)).execute()

    return {"table": table, "id": row_id, "is_verified": True}
