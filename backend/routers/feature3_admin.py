"""
F3 법령 자동 업데이트 — admin 전용 API (F3 소유 파일).

3-phase 플로우:
  1. POST /api/v1/admin/f3/preview   — 파일 업로드 → 파싱 → diff 반환 (DB 무변경)
  2. POST /api/v1/admin/f3/apply     — 검역관 편집본으로 Snapshot + Replace
  3. POST /api/v1/admin/f3/rollback  — 특정 version 으로 복원
  4. GET  /api/v1/admin/f3/history   — 업데이트 이력

보안 (리뷰 반영):
  - X-Admin-Token 헤더 검사 (env F3_ADMIN_TOKEN)
  - X-Admin-User 헤더 → 감사로그 (created_by/rolled_back_by)
  - 파일 크기 제한 (기본 50MB, env F3_MAX_UPLOAD_MB 로 조정)
  - HWPX 업로드 시 ZIP bomb 검사 (압축해제 크기 상한)
  - 에러 응답에 traceback 포함하지 않음 (서버 로그만)
"""
from __future__ import annotations

import asyncio
import importlib
import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from db.f3_supabase_client import reload_cache
from services.f3_preprocess import snapshot as snap
from services.f3_preprocess.dispatcher import SUPPORTED_LAWS, get_parser_module


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/f3", tags=["f3-admin-law-update"])


# ══════════════════════════════════════════════════════════════
# 설정 (env)
# ══════════════════════════════════════════════════════════════

def _max_upload_bytes() -> int:
    mb = int(os.getenv("F3_MAX_UPLOAD_MB", "50"))
    return mb * 1024 * 1024


# HWPX/ZIP 압축 해제 후 최대 허용 크기 (ZIP bomb 방지)
MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024  # 300MB


# ══════════════════════════════════════════════════════════════
# 인증/인가
# ══════════════════════════════════════════════════════════════

def require_admin(
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
    x_admin_user: Optional[str] = Header(default=None, alias="X-Admin-User"),
) -> dict:
    """간단한 토큰 인증. env F3_ADMIN_TOKEN 과 일치해야 허용.

    env 에 토큰이 설정 안 돼 있으면:
      - F3_ADMIN_ALLOW_UNSAFE=true 일 때만 인증 생략 (로컬 개발용)
      - 그 외에는 500 반환 (미설정 상태로 프로덕션 열리는 것 방지)
    """
    expected = os.getenv("F3_ADMIN_TOKEN")
    if not expected:
        if os.getenv("F3_ADMIN_ALLOW_UNSAFE") == "true":
            return {"user": x_admin_user or "local-dev"}
        raise HTTPException(
            status_code=500,
            detail={
                "error": "ADMIN_TOKEN_NOT_CONFIGURED",
                "message": (
                    "F3_ADMIN_TOKEN 환경변수 미설정. 관리자 API 를 사용하려면 "
                    ".env 에 F3_ADMIN_TOKEN 설정 필요 (로컬 테스트는 "
                    "F3_ADMIN_ALLOW_UNSAFE=true 로 우회 가능)."
                ),
            },
        )
    if not x_admin_token or x_admin_token != expected:
        raise HTTPException(
            status_code=401,
            detail={"error": "UNAUTHORIZED", "message": "X-Admin-Token 누락 또는 불일치."},
        )
    return {"user": x_admin_user or "admin"}


# ══════════════════════════════════════════════════════════════
# 요청/응답 스키마
# ══════════════════════════════════════════════════════════════

class PreviewResponse(BaseModel):
    law_name: str
    source_filename: str
    feature_label: str = "수입필요서류 안내"
    affected_tables: list[str]
    tables: dict[str, dict]
    # 각 테이블의 scope_filter (부분 교체 범위) — 클라이언트는 그대로 apply 에 전달
    scope_filters: dict[str, Optional[dict]] = {}
    # Pinecone 청크 (Step 2/3 만 사용). 서버에서 apply 시 재임베딩.
    # 프론트는 이 값을 저장했다가 apply 요청에 그대로 포함.
    pinecone_chunks: list[dict[str, Any]] = []
    warnings: list[str] = []
    pinecone_touched: bool = False


class ApplyTableSpec(BaseModel):
    new_rows: list[dict[str, Any]]
    pk_column: str
    scope_filter: Optional[dict[str, Any]] = None
    force_empty: bool = False


class ApplyRequest(BaseModel):
    law_name: str
    source_filename: Optional[str] = None
    tables: dict[str, ApplyTableSpec]
    # Pinecone 재임베딩 대상 청크 (Step 2/3 의 preview 응답에서 받은 그대로 전달)
    pinecone_chunks: list[dict[str, Any]] = []
    pinecone_touched: bool = False


class RollbackRequest(BaseModel):
    version: int
    cascade: bool = False


class ManualRuleRequest(BaseModel):
    """수동 서류 규칙 1건 추가. 검역관이 엑셀 없이 긴급 공지 대응 시 사용."""
    doc_name: str
    doc_description: str
    is_mandatory: bool = True
    submission_type: str = "submit"           # 'submit' | 'keep'
    submission_timing: str = "every"          # 'every' | 'first'
    law_source: Optional[str] = None

    # 적용 대상 — 최소 1개 필수 (아래 중 하나라도 값 있어야 함)
    target_country: Optional[str] = None
    food_type: Optional[str] = None
    condition: Optional[str] = None
    product_keywords: Optional[list[str]] = None

    # 날짜 (선택)
    effective_from: Optional[str] = None
    effective_until: Optional[str] = None

    # 메모 (선택)
    notes: Optional[str] = None


# ══════════════════════════════════════════════════════════════
# related_doc_ids 보존 헬퍼
# ══════════════════════════════════════════════════════════════

def _backfill_related_doc_ids(
    law_name: str,
    pinecone_chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """기존 citations 테이블에서 `pinecone_chunk_id → doc_id` 매핑을 읽어,
    새 청크 메타데이터에 `related_doc_ids` 를 복원.

    법령 본문 → 서류 양방향 링크 유지를 위해 필수.
    기존 청크와 새 청크의 chunk_id 가 다를 경우 (결정적 MD5 라 내용 같으면 동일),
    `article` 매칭으로 fallback.
    """
    from services.f3_preprocess.snapshot import _fetch_all

    try:
        existing = _fetch_all(
            "f3_document_law_citations",
            scope_filter=None,
        )
    except Exception as e:
        logger.warning("[F3 backfill] citations 조회 실패: %s", e)
        return pinecone_chunks

    # pinecone_chunk_id → [doc_id ...] 맵 구성
    chunk_to_docs: dict[str, list[str]] = {}
    # article → [doc_id ...] fallback
    article_to_docs: dict[str, list[str]] = {}

    for row in existing:
        pid = row.get("pinecone_chunk_id")
        art = row.get("article")
        # doc_id 컬럼명이 seed 따라 다를 수 있음 — id 또는 doc_id 시도
        doc_id = row.get("doc_id") or row.get("id")
        if not doc_id:
            continue
        if pid:
            chunk_to_docs.setdefault(pid, []).append(doc_id)
        if art:
            article_to_docs.setdefault(art, []).append(doc_id)

    # 새 청크에 주입
    for ch in pinecone_chunks:
        pid = ch.get("pinecone_chunk_id")
        existing_related = ch.get("related_doc_ids") or []
        if isinstance(existing_related, list) and existing_related:
            continue  # 이미 있으면 보존
        # 1차: 같은 chunk_id 존재
        if pid in chunk_to_docs:
            ch["related_doc_ids"] = chunk_to_docs[pid]
        else:
            # 2차: 같은 article
            art = ch.get("article")
            if art and art in article_to_docs:
                ch["related_doc_ids"] = article_to_docs[art]

    return pinecone_chunks


# ══════════════════════════════════════════════════════════════
# 헬퍼
# ══════════════════════════════════════════════════════════════

def _parser_for(law_name: str):
    """law_name → 파서 모듈의 parse(path, law_name) 함수."""
    module_name = get_parser_module(law_name)
    mod = importlib.import_module(f"services.f3_preprocess.{module_name}")
    if not hasattr(mod, "parse"):
        raise HTTPException(
            status_code=501,
            detail={
                "error": "PARSER_NOT_IMPLEMENTED",
                "message": f"{law_name} 파서 ({module_name}.parse) 미구현",
            },
        )
    return mod.parse


def _check_zip_bomb(file_path: Path) -> None:
    """HWPX 등 ZIP 형식 파일의 압축해제 후 크기 검사."""
    if not zipfile.is_zipfile(file_path):
        return  # ZIP 아님, 검사 불필요
    total_uncompressed = 0
    with zipfile.ZipFile(file_path, "r") as z:
        for info in z.infolist():
            total_uncompressed += info.file_size
            if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "ZIP_BOMB_DETECTED",
                        "message": (
                            f"압축 해제 크기가 한도({MAX_UNCOMPRESSED_BYTES // (1024*1024)}MB) "
                            f"를 초과합니다. 파일이 손상됐거나 악의적일 수 있습니다."
                        ),
                    },
                )


def _safe_error(exc: Exception, status: int, error_code: str, message: str) -> HTTPException:
    """traceback 은 서버 로그에만 기록, 클라이언트에는 간단한 메시지만."""
    logger.exception("%s: %s", error_code, exc)
    return HTTPException(
        status_code=status,
        detail={
            "error": error_code,
            "message": message,
            "error_type": type(exc).__name__,
        },
    )


# ══════════════════════════════════════════════════════════════
# 엔드포인트
# ══════════════════════════════════════════════════════════════

async def _stream_to_tmp(upload: UploadFile, suffix: str, max_bytes: int) -> Path:
    """UploadFile 을 디스크로 스트리밍 저장 + 크기 한도 감시.

    메모리에 전체 올리지 않음 (DoS 방지). 한도 초과 시 즉시 중단 + 파일 삭제.
    """
    tmp_fd, tmp_name = tempfile.mkstemp(suffix=suffix)
    tmp_path = Path(tmp_name)
    size = 0
    try:
        with os.fdopen(tmp_fd, "wb") as out:
            while True:
                chunk = await upload.read(64 * 1024)  # 64KB 단위
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail={
                            "error": "FILE_TOO_LARGE",
                            "message": f"파일 크기 한도({max_bytes // (1024*1024)}MB) 초과.",
                        },
                    )
                out.write(chunk)
        return tmp_path
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


@router.post("/preview", response_model=PreviewResponse)
async def preview_update(
    file: UploadFile = File(..., description="법령 파일 (PDF/HWPX/XLSX)"),
    law_name: str = Form(..., description="LAW_FEATURE_MAP 의 key"),
    auth: dict = Depends(require_admin),
) -> PreviewResponse:
    """법령 파일 → 파싱 → 현재 DB 와 diff → 미리보기.

    **DB 는 건드리지 않음.** 검역관이 편집/확인 후 /apply 호출해야 반영.
    """
    if law_name not in SUPPORTED_LAWS:
        raise HTTPException(400, detail={
            "error": "UNSUPPORTED_LAW",
            "message": f"지원하지 않는 법령: {law_name}",
            "supported": sorted(SUPPORTED_LAWS),
        })

    # 1. 파일 스트리밍 저장 + 크기 한도 (메모리 로드 안 함)
    suffix = Path(file.filename or "").suffix.lower() or ".bin"
    max_bytes = _max_upload_bytes()
    tmp_path = await _stream_to_tmp(file, suffix, max_bytes)

    try:
        # 2. ZIP bomb 검사
        _check_zip_bomb(tmp_path)

        # 3. 파싱 + DB 조회 — 모두 sync httpx 사용하므로 스레드에서 실행 (이벤트 루프 비블록)
        def _do_preview_work() -> dict:
            parser = _parser_for(law_name)
            parse_result = parser(tmp_path, law_name)

            tables_output: dict[str, dict] = {}
            scope_filters: dict[str, Optional[dict]] = {}
            combined_warnings: list[str] = list(parse_result.get("warnings", []))
            pinecone_touched = bool(parse_result.get("pinecone_touched", False))
            pinecone_chunks = list(parse_result.get("pinecone_chunks") or [])

            # Pinecone 관련 청크면 related_doc_ids 복원 시도
            if pinecone_touched and pinecone_chunks:
                pinecone_chunks = _backfill_related_doc_ids(law_name, pinecone_chunks)

            per_table = parse_result.get("tables") or {}
            for table_name, spec in per_table.items():
                new_rows = spec.get("new_rows", [])
                pk = spec.get("pk_column") or snap._detect_pk_column(table_name)
                scope = spec.get("scope_filter")
                scope_filters[table_name] = scope

                old_rows = snap._fetch_all(table_name, scope)
                diff = snap.compute_diff_summary(old_rows, new_rows, pk)

                tables_output[table_name] = {
                    "new_rows": new_rows,
                    "old_rows": old_rows,
                    "pk_column": pk,
                    "scope_filter": scope,
                    "diff": diff,
                }
                combined_warnings.extend(spec.get("warnings", []))

            return {
                "tables_output": tables_output,
                "scope_filters": scope_filters,
                "pinecone_chunks": pinecone_chunks,
                "combined_warnings": combined_warnings,
                "pinecone_touched": pinecone_touched,
                "per_table_keys": list(per_table.keys()),
            }

        work = await asyncio.to_thread(_do_preview_work)

        return PreviewResponse(
            law_name=law_name,
            source_filename=file.filename or "",
            affected_tables=work["per_table_keys"],
            tables=work["tables_output"],
            scope_filters=work["scope_filters"],
            pinecone_chunks=work["pinecone_chunks"],
            warnings=work["combined_warnings"],
            pinecone_touched=work["pinecone_touched"],
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise _safe_error(
            exc, 500, "PARSE_FAILED",
            f"파싱 실패: {type(exc).__name__}. 파일 포맷/내용을 확인하세요.",
        )
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/apply")
async def apply_update(
    body: ApplyRequest,
    background_tasks: BackgroundTasks,
    auth: dict = Depends(require_admin),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    """검역관 편집본 최종 반영. Snapshot + Replace 트랜잭션 + 정합성 감시 백그라운드."""
    if body.law_name not in SUPPORTED_LAWS:
        raise HTTPException(400, detail={
            "error": "UNSUPPORTED_LAW",
            "message": f"지원하지 않는 법령: {body.law_name}",
        })

    if not body.tables:
        raise HTTPException(400, detail={
            "error": "EMPTY_TABLES",
            "message": "적용할 테이블이 비어있습니다.",
        })

    # 1. Idempotency 체크 (같은 키로 24시간 내 재요청이면 이전 결과 반환)
    if idempotency_key:
        try:
            prior = await asyncio.to_thread(snap.check_idempotency, idempotency_key)
        except Exception as e:
            logger.warning("idempotency 체크 실패 (계속 진행): %s", e)
            prior = None
        if prior and prior.get("status") in ("applied", "pending"):
            return {
                "status": "duplicate_request",
                "version": prior["version"],
                "history_id": prior["history_id"],
                "created_at": prior["created_at"],
                "message": (
                    "같은 요청이 이미 처리됐습니다. 이전 결과를 반환합니다. "
                    "새로운 업데이트를 원하시면 페이지를 새로고침 후 다시 업로드하세요."
                ),
            }

    # 2. 메인 작업 — sync 호출이라 스레드에서 실행
    def _do_apply() -> dict:
        replacements: dict[str, dict] = {}
        for table_name, spec in body.tables.items():
            new_rows = spec.new_rows
            pk = spec.pk_column
            scope = spec.scope_filter

            # apply 시점 기준 최신 old_rows 로 diff 재계산
            old_rows = snap._fetch_all(table_name, scope)
            diff = snap.compute_diff_summary(old_rows, new_rows, pk)

            replacements[table_name] = {
                "new_rows": new_rows,
                "pk_column": pk,
                "scope_filter": scope,
                "diff_summary": diff,
                "force_empty": spec.force_empty,
            }

        return snap.snapshot_and_replace(
            law_name=body.law_name,
            table_replacements=replacements,
            source_filename=body.source_filename,
            pinecone_touched=body.pinecone_touched,
            created_by=auth.get("user"),
            idempotency_key=idempotency_key,
        )

    try:
        result = await asyncio.to_thread(_do_apply)
    except ValueError as ve:
        raise HTTPException(
            status_code=400,
            detail={"error": "APPLY_BLOCKED", "message": str(ve)},
        )
    except Exception as exc:
        raise _safe_error(
            exc, 500, "APPLY_FAILED",
            f"DB 반영 실패: {type(exc).__name__}. 자동 복구 시도됨, 현재 상태를 확인하세요.",
        )

    # 3. Pinecone 재임베딩 (스레드)
    pinecone_result: dict[str, Any] = {"touched": False}
    if body.pinecone_touched and body.pinecone_chunks:
        def _do_pinecone() -> dict:
            from services.f3_preprocess.pinecone_embed import (
                delete_by_law,
                upsert_chunks,
            )
            # apply 전에 related_doc_ids 재주입 (파이프라인 안전)
            chunks = _backfill_related_doc_ids(body.law_name, body.pinecone_chunks)
            delete_by_law(body.law_name)
            upserted = upsert_chunks(chunks)
            return {"upserted": upserted, "deleted": "best-effort"}

        try:
            pinecone_result = {
                "touched": True,
                **(await asyncio.to_thread(_do_pinecone)),
            }
        except Exception as e:
            logger.exception("Pinecone 재임베딩 실패")
            pinecone_result = {
                "touched": True,
                "error": f"{type(e).__name__}: {e}",
                "message": (
                    "자료는 반영됐지만 검색 인덱스(Pinecone) 재임베딩이 실패했습니다. "
                    "검색 결과가 구버전일 수 있으니 관리자에게 재시도 요청하세요."
                ),
            }

    # 4. 캐시 리로드 + retention (비동기 스레드)
    async def _post_apply_cleanup():
        await asyncio.to_thread(lambda: (
            reload_cache() if True else None,
            snap.cleanup_retention() if True else None,
        ))

    try:
        await _post_apply_cleanup()
    except Exception as e:
        logger.warning("post-apply cleanup 실패: %s", e)

    # 5. 백그라운드 정합성 감시 (10초 뒤 Pinecone 체크)
    if body.pinecone_touched and result.get("history_id"):
        history_id = result["history_id"]

        async def _deferred_consistency_check():
            await asyncio.sleep(10)
            try:
                await asyncio.to_thread(snap.check_pinecone_consistency, history_id)
            except Exception as e:
                logger.warning("[F3 consistency] 백그라운드 검사 실패: %s", e)

        background_tasks.add_task(asyncio.create_task, _deferred_consistency_check())

    return {"status": "applied", "pinecone": pinecone_result, **result}


@router.post("/rollback")
async def rollback_update(
    body: RollbackRequest,
    auth: dict = Depends(require_admin),
) -> dict:
    """version 으로 롤백. cascade=True 면 이후 버전 모두 함께 취소."""
    try:
        result = await asyncio.to_thread(
            snap.rollback,
            body.version,
            body.cascade,
            auth.get("user"),
        )
    except ValueError as ve:
        raise HTTPException(400, detail={
            "error": "ROLLBACK_BLOCKED", "message": str(ve),
        })
    except Exception as exc:
        raise _safe_error(
            exc, 500, "ROLLBACK_FAILED",
            f"롤백 실패: {type(exc).__name__}",
        )

    try:
        await asyncio.to_thread(reload_cache)
    except Exception:
        pass

    return result


class CountryGroupMemberRequest(BaseModel):
    group_name: str
    country_name: str


@router.get("/country-groups")
async def get_country_groups(auth: dict = Depends(require_admin)) -> dict:
    """f3_country_groups 전체 목록. 관리 UI 용."""
    groups = await asyncio.to_thread(snap.list_country_groups)
    return {"groups": groups}


@router.post("/country-groups/members")
async def add_country_group_member(
    body: CountryGroupMemberRequest,
    auth: dict = Depends(require_admin),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    """그룹에 국가 추가. 새 그룹이면 자동 생성."""
    group = body.group_name.strip()
    country = body.country_name.strip()
    if not group or not country:
        raise HTTPException(400, detail={
            "error": "EMPTY_FIELD",
            "message": "그룹명과 국가명을 모두 입력해주세요.",
        })

    try:
        result = await asyncio.to_thread(
            snap.add_country_group_member,
            group,
            country,
            auth.get("user"),
            idempotency_key,
        )
    except ValueError as ve:
        raise HTTPException(400, detail={"error": "ADD_BLOCKED", "message": str(ve)})
    except Exception as exc:
        raise _safe_error(exc, 500, "ADD_FAILED", f"{type(exc).__name__}")

    try:
        await asyncio.to_thread(reload_cache)
    except Exception:
        pass
    return result


@router.delete("/country-groups/members")
async def delete_country_group_member(
    group_name: str,
    country_name: str,
    auth: dict = Depends(require_admin),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    """그룹에서 국가 제거."""
    try:
        result = await asyncio.to_thread(
            snap.remove_country_group_member,
            group_name,
            country_name,
            auth.get("user"),
            idempotency_key,
        )
    except ValueError as ve:
        raise HTTPException(400, detail={"error": "REMOVE_BLOCKED", "message": str(ve)})
    except Exception as exc:
        raise _safe_error(exc, 500, "REMOVE_FAILED", f"{type(exc).__name__}")

    try:
        await asyncio.to_thread(reload_cache)
    except Exception:
        pass
    return result


class SynonymAddRequest(BaseModel):
    hint_keyword: str
    db_keyword: str
    country_cond: Optional[str] = None


@router.get("/synonyms")
async def get_synonyms(auth: dict = Depends(require_admin)) -> dict:
    rows = await asyncio.to_thread(snap.list_keyword_synonyms)
    return {"synonyms": rows}


@router.post("/synonyms")
async def add_synonym(
    body: SynonymAddRequest,
    auth: dict = Depends(require_admin),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    hint = body.hint_keyword.strip()
    db = body.db_keyword.strip()
    if not hint or not db:
        raise HTTPException(400, detail={
            "error": "EMPTY_FIELD",
            "message": "hint_keyword 와 db_keyword 모두 입력해주세요.",
        })
    if len(hint) < 2:
        raise HTTPException(400, detail={
            "error": "HINT_TOO_SHORT",
            "message": "hint_keyword 는 2글자 이상이어야 합니다 (한글 1글자 매핑 방지).",
        })

    try:
        result = await asyncio.to_thread(
            snap.add_keyword_synonym,
            hint, db, body.country_cond, auth.get("user"), idempotency_key,
        )
    except ValueError as ve:
        raise HTTPException(400, detail={"error": "ADD_BLOCKED", "message": str(ve)})
    except Exception as exc:
        raise _safe_error(exc, 500, "ADD_FAILED", f"{type(exc).__name__}")

    try:
        await asyncio.to_thread(reload_cache)
    except Exception:
        pass
    return result


@router.delete("/synonyms/{synonym_id}")
async def delete_synonym(
    synonym_id: int,
    auth: dict = Depends(require_admin),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    try:
        result = await asyncio.to_thread(
            snap.remove_keyword_synonym,
            synonym_id, auth.get("user"), idempotency_key,
        )
    except ValueError as ve:
        raise HTTPException(400, detail={"error": "REMOVE_BLOCKED", "message": str(ve)})
    except Exception as exc:
        raise _safe_error(exc, 500, "REMOVE_FAILED", f"{type(exc).__name__}")

    try:
        await asyncio.to_thread(reload_cache)
    except Exception:
        pass
    return result


class WarningKeywordRequest(BaseModel):
    rule_id: str
    keyword: str


@router.get("/warning-keywords")
async def get_warning_keywords(auth: dict = Depends(require_admin)) -> dict:
    data = await asyncio.to_thread(snap.list_warning_keywords)
    return {"rules": data}


@router.post("/warning-keywords")
async def add_warning_keyword(
    body: WarningKeywordRequest,
    auth: dict = Depends(require_admin),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    rid = body.rule_id.strip()
    kw = body.keyword.strip()
    if not rid or not kw:
        raise HTTPException(400, detail={"error": "EMPTY_FIELD", "message": "둘 다 입력"})

    try:
        result = await asyncio.to_thread(
            snap.add_warning_keyword, rid, kw, auth.get("user"), idempotency_key,
        )
    except ValueError as ve:
        raise HTTPException(400, detail={"error": "ADD_BLOCKED", "message": str(ve)})
    except Exception as exc:
        raise _safe_error(exc, 500, "ADD_FAILED", f"{type(exc).__name__}")

    try:
        await asyncio.to_thread(reload_cache)
    except Exception:
        pass
    return result


@router.delete("/warning-keywords")
async def delete_warning_keyword(
    rule_id: str,
    keyword: str,
    auth: dict = Depends(require_admin),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    try:
        result = await asyncio.to_thread(
            snap.remove_warning_keyword, rule_id, keyword, auth.get("user"), idempotency_key,
        )
    except ValueError as ve:
        raise HTTPException(400, detail={"error": "REMOVE_BLOCKED", "message": str(ve)})
    except Exception as exc:
        raise _safe_error(exc, 500, "REMOVE_FAILED", f"{type(exc).__name__}")

    try:
        await asyncio.to_thread(reload_cache)
    except Exception:
        pass
    return result


@router.post("/rules")
async def add_manual_rule(
    body: ManualRuleRequest,
    auth: dict = Depends(require_admin),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    """수동 서류 규칙 1건 추가 (f3_required_documents 에 INSERT).

    검역관 사용 시나리오:
      - 긴급 공지·임시 지침 등 엑셀에 없는 규칙을 즉시 반영
      - ID 는 서버가 'manual_{timestamp}' 형태로 자동 생성 (충돌 방지)
      - 롤백 가능 (f3_update_history 에 기록)

    유효성:
      - target_country, food_type, condition, product_keywords 중 최소 1개 필수.
        전부 NULL 이면 어떤 제품에도 매칭 안 돼서 의미 없음.
    """
    # 1. 적용 대상 최소 1개 필수
    has_target = any([
        body.target_country,
        body.food_type,
        body.condition,
        body.product_keywords,
    ])
    if not has_target:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "TARGET_REQUIRED",
                "message": (
                    "적용 대상 (국가·식품유형·조건·원재료 키워드) 중 "
                    "최소 1개는 반드시 입력해야 합니다. 모두 비어있으면 "
                    "어떤 제품에도 매칭되지 않아 의미 없는 규칙이 됩니다."
                ),
            },
        )

    # 2. 간단 검증
    if body.submission_type not in ("submit", "keep"):
        raise HTTPException(400, detail={
            "error": "INVALID_SUBMISSION_TYPE",
            "message": "submission_type 은 'submit' 또는 'keep' 이어야 합니다.",
        })
    if body.submission_timing not in ("every", "first"):
        raise HTTPException(400, detail={
            "error": "INVALID_SUBMISSION_TIMING",
            "message": "submission_timing 은 'every' 또는 'first' 이어야 합니다.",
        })

    # 3. ID 자동 생성 (timestamp 기반, 충돌 방지)
    import time
    row_id = f"manual_{int(time.time() * 1000)}"

    # 4. new_row 구성
    new_row: dict[str, Any] = {
        "id": row_id,
        "doc_name": body.doc_name.strip(),
        "doc_description": body.doc_description.strip(),
        "is_mandatory": body.is_mandatory,
        "submission_type": body.submission_type,
        "submission_timing": body.submission_timing,
        "law_source": body.law_source or "수동 추가 규칙",
        "target_country": body.target_country,
        "food_type": body.food_type,
        "condition": body.condition,
        "product_keywords": body.product_keywords,
        "effective_from": body.effective_from,
        "effective_until": body.effective_until,
        "is_verified": True,
    }
    # 추가 메타 필드 (notes) 는 별도 컬럼 없으면 source_product 에 덧붙임
    if body.notes:
        new_row["source_product"] = f"[수동] {body.notes}"[:500]

    # 5. snapshot.add_single_rule 호출 (스레드)
    try:
        result = await asyncio.to_thread(
            snap.add_single_rule,
            "f3_required_documents",
            new_row,
            "수동 규칙 추가",
            "수입필요서류 안내",
            auth.get("user"),
            idempotency_key,
        )
    except ValueError as ve:
        raise HTTPException(400, detail={
            "error": "RULE_ADD_BLOCKED",
            "message": str(ve),
        })
    except Exception as exc:
        raise _safe_error(
            exc, 500, "RULE_ADD_FAILED",
            f"규칙 추가 실패: {type(exc).__name__}",
        )

    # 6. 캐시 리로드
    try:
        await asyncio.to_thread(reload_cache)
    except Exception as e:
        logger.warning("reload_cache 실패: %s", e)

    return result


@router.get("/health")
async def get_health() -> dict:
    """F3 건강 상태 — 검역관 대시보드용 (인증 불필요, 결과는 단순).

    체크 항목:
      - Supabase 연결 (f3_required_documents 1행 read)
      - Pinecone 연결 (index describe_index_stats)
      - OpenAI API 키 (validation, 호출 없이 존재만 확인)
      - 정합성 감시 결과 (최근 7일 mismatch 건수)
    """
    import time
    import httpx as _httpx

    results: dict[str, dict] = {}
    overall_status = "ok"

    # 1. Supabase
    start = time.time()
    try:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise RuntimeError("env 미설정")
        r = _httpx.get(
            f"{url}/rest/v1/f3_required_documents?select=id&limit=1",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=3.0,
        )
        r.raise_for_status()
        count_hdr = r.headers.get("content-range", "")
        results["database"] = {
            "status": "ok",
            "label": "데이터베이스",
            "latency_ms": int((time.time() - start) * 1000),
            "detail": f"연결됨 (content-range: {count_hdr})" if count_hdr else "연결됨",
        }
    except Exception as e:
        results["database"] = {
            "status": "error",
            "label": "데이터베이스",
            "latency_ms": int((time.time() - start) * 1000),
            "detail": f"{type(e).__name__}: {str(e)[:120]}",
        }
        overall_status = "error"

    # 2. 서류 매칭 엔진 — DB 통해 테이블 존재 + 최소 1행 확인
    try:
        required = await asyncio.to_thread(snap._fetch_all, "f3_required_documents")
        count = len(required)
        results["matching_engine"] = {
            "status": "ok" if count > 0 else "warning",
            "label": "서류 매칭 엔진",
            "detail": f"서류 규칙 {count} 건 로드됨",
        }
        if count == 0:
            overall_status = "warning" if overall_status == "ok" else overall_status
    except Exception as e:
        results["matching_engine"] = {
            "status": "error",
            "label": "서류 매칭 엔진",
            "detail": f"{type(e).__name__}",
        }
        overall_status = "error"

    # 3. Pinecone (법령 본문 검색)
    start = time.time()
    try:
        from services.f3_preprocess.pinecone_embed import _pinecone_client, _index
        def _check_pinecone():
            pc = _pinecone_client()
            idx = _index(pc)
            stats = idx.describe_index_stats()
            total = 0
            if hasattr(stats, "total_vector_count"):
                total = stats.total_vector_count
            elif isinstance(stats, dict):
                total = stats.get("total_vector_count", 0)
            return total
        total_vec = await asyncio.to_thread(_check_pinecone)
        results["pinecone_search"] = {
            "status": "ok",
            "label": "법령 본문 검색",
            "latency_ms": int((time.time() - start) * 1000),
            "detail": f"벡터 {total_vec:,} 건",
        }
    except Exception as e:
        results["pinecone_search"] = {
            "status": "warning",  # Pinecone 없어도 핵심 판정은 동작
            "label": "법령 본문 검색",
            "latency_ms": int((time.time() - start) * 1000),
            "detail": f"비활성화 또는 오류: {type(e).__name__}",
        }
        if overall_status == "ok":
            overall_status = "warning"

    # 4. OpenAI (AI 해설)
    openai_key = os.getenv("F3_OPENAI_API_KEY")
    if openai_key:
        results["ai_explanation"] = {
            "status": "ok",
            "label": "AI 법령 해설",
            "detail": "API 키 설정됨 (실호출은 요청 시)",
        }
    else:
        results["ai_explanation"] = {
            "status": "warning",
            "label": "AI 법령 해설",
            "detail": "F3_OPENAI_API_KEY 미설정 (해설 기능 비활성)",
        }
        if overall_status == "ok":
            overall_status = "warning"

    # 5. 최근 7일 정합성 mismatch 건수
    try:
        from datetime import datetime, timedelta, timezone
        seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        r = _httpx.get(
            f"{url}/rest/v1/f3_update_history"
            f"?consistency_status=eq.mismatch"
            f"&created_at=gte.{seven_days_ago}"
            f"&select=id&limit=100",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=3.0,
        )
        mismatch_count = len(r.json()) if r.status_code == 200 else 0
        results["consistency"] = {
            "status": "ok" if mismatch_count == 0 else "warning",
            "label": "데이터 정합성 (지난 7일)",
            "detail": (
                "모든 업데이트 정상"
                if mismatch_count == 0
                else f"{mismatch_count}건 불일치 감지 — 관리자 확인 필요"
            ),
        }
        if mismatch_count > 0 and overall_status == "ok":
            overall_status = "warning"
    except Exception as e:
        results["consistency"] = {
            "status": "unknown",
            "label": "데이터 정합성",
            "detail": f"확인 실패: {type(e).__name__}",
        }

    return {
        "overall_status": overall_status,
        "checks": results,
    }


F3_EXPORT_TABLES = [
    "f3_required_documents",
    "f3_country_groups",
    "f3_keyword_synonyms",
    "f3_food_type_categories",
    "f3_mid_category_flags",
    "f3_plant_based_patterns",
    "f3_warning_keywords",
    "f3_document_law_citations",
    "f3_suppress_rules",
    "f3_strong_animal_keywords",
]


@router.get("/export")
async def export_all(auth: dict = Depends(require_admin)):
    """F3 전체 자료 Excel ZIP 다운로드. 시스템 이관/백업/감사 대응용.

    반환: multipart streaming response (.zip)
      내용:
        - f3_*.xlsx (테이블별 시트)
        - manifest.json (메타: 내보낸 시각, 행 수, 스키마 힌트)
        - README.txt (복원 안내)
    """
    import io
    import json
    import zipfile
    from datetime import datetime, timezone
    from fastapi.responses import StreamingResponse

    try:
        from openpyxl import Workbook
    except ImportError:
        raise HTTPException(500, detail={
            "error": "OPENPYXL_MISSING",
            "message": "서버에 openpyxl 미설치. 관리자 문의.",
        })

    def _do_export() -> bytes:
        # 1. 각 테이블 조회
        table_data: dict[str, list[dict]] = {}
        for t in F3_EXPORT_TABLES:
            try:
                table_data[t] = snap._fetch_all(t)
            except Exception as e:
                logger.warning("[F3 export] %s 조회 실패: %s", t, e)
                table_data[t] = []

        # 2. Excel 생성 — 테이블당 시트 하나
        wb = Workbook()
        # 기본 "Sheet" 제거
        default_sheet = wb.active
        if default_sheet is not None:
            wb.remove(default_sheet)

        for t, rows in table_data.items():
            # 시트명은 Excel 제약상 31자 이내
            sheet_name = t[:31]
            ws = wb.create_sheet(title=sheet_name)
            if rows:
                headers = list(rows[0].keys())
                ws.append(headers)
                for r in rows:
                    ws.append([
                        (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
                        for v in (r.get(h) for h in headers)
                    ])
            else:
                ws.append(["(empty)"])

        xlsx_buf = io.BytesIO()
        wb.save(xlsx_buf)
        xlsx_bytes = xlsx_buf.getvalue()

        # 3. Manifest
        manifest = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "exported_by": auth.get("user"),
            "tables": {t: len(rows) for t, rows in table_data.items()},
            "total_rows": sum(len(rows) for rows in table_data.values()),
            "feature": "F3 — 수입필요서류 안내",
            "note": (
                "이 파일은 F3 시스템 전체 자료 백업입니다. "
                "복원이 필요하면 각 테이블을 Supabase 에 INSERT 하거나 "
                "관리자 업로드 UI 의 'rollback' 기능을 사용하세요."
            ),
        }

        readme = f"""# F3 자료 백업 — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}

내려받은 파일 안내:
  - f3_tables.xlsx: 각 시트 = 하나의 테이블 (전체 {manifest['total_rows']} 행)
  - manifest.json: 메타 정보 (시점·행 수·작성자)
  - README.txt: 이 파일

복원 안내:
  - 엑셀 그대로 검역 업무에 참고 자료로 쓸 수 있음
  - 시스템 장애 시 이 파일만으로도 수작업 대응 가능
  - 전체 시스템 복원이 필요하면 IT 담당자 문의

감사 추적:
  - 내려받은 사용자: {auth.get('user') or '(알 수 없음)'}
  - 내려받은 시각: {manifest['exported_at']}

테이블별 행 수:
"""
        for t, n in manifest["tables"].items():
            readme += f"  - {t}: {n}\n"

        # 4. ZIP 패키징
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("f3_tables.xlsx", xlsx_bytes)
            zf.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2),
            )
            zf.writestr("README.txt", readme)

        return zip_buf.getvalue()

    zip_bytes = await asyncio.to_thread(_do_export)

    ts = __import__("time").strftime("%Y%m%d_%H%M%S")
    filename = f"f3_export_{ts}.zip"
    return StreamingResponse(
        iter([zip_bytes]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/last-update")
async def get_last_update() -> dict:
    """법령 기준일 배너용. 인증 불필요 — 검역관 일반 화면에서 사용.

    반환: {per_law: {law_name: timestamp}, overall_last_at: timestamp | null}
    """
    data = await asyncio.to_thread(snap.get_last_update_per_law)
    return data


@router.get("/history")
async def get_history(
    limit: int = 20,
    include_failed: bool = False,
    auth: dict = Depends(require_admin),
) -> dict:
    """최근 업데이트 이력.

    Args:
        limit: 상한 (서버 측 max 100)
        include_failed: True 면 status='failed'/'pending' 도 포함 (디버깅용)
    """
    # 과도한 limit 방지
    limit = min(max(1, limit), 100)
    items = await asyncio.to_thread(
        snap.list_history,
        limit,
        not include_failed,  # exclude_failed
    )
    return {"items": items}
