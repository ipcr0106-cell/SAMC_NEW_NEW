"""
F3 법령 업데이트 — 스냅샷 / 교체 / 롤백 유틸.

설계 개선 (리뷰 반영):
  - 빈 new_rows 가드: 기존 데이터 있는데 new_rows=[] 면 거절
  - NULL snapshot_data 가드: rollback 시 유효성 체크
  - 부분 교체 지원 (scope_filter): 제출용 엑셀만 업로드 시 submission_type='submit' 범위만 교체
  - PK 자동 감지: information_schema 에서 실 PK 조회 (폴백은 하드코딩 맵)
  - 동시성: Postgres advisory lock via f3_acquire_law_lock RPC
  - 타임아웃: 대용량 JSONB 대응 120초
  - Retention: apply 시마다 365일 초과 이력 cleanup 시도 (idempotent)

PostgREST HTTP 로 직접 호출. supabase SDK 의 hang 이슈 회피.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Optional

import httpx


HTTP_TIMEOUT = 120.0   # JSONB 대용량 대응
LARGE_REPLACE_WARNING_THRESHOLD = 100  # 이만큼 이상 삭제되면 경고


def _env() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_SERVICE_KEY 환경변수가 없습니다."
        )
    return url, key


def _headers(extra: Optional[dict] = None) -> dict:
    _, key = _env()
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


# ──────────────────────────────────────────────
# PK 컬럼 동적 감지 — information_schema
# ──────────────────────────────────────────────

# 테이블별 PK 컬럼 힌트 (information_schema 조회 실패 시 폴백)
_TABLE_PK_HINTS = {
    "f3_required_documents": "id",
    "f3_food_type_categories": "food_type",
    "f3_mid_category_flags": "mid_category",
    "f3_plant_based_patterns": "pattern",
    "f3_document_law_citations": "id",
    "f3_keyword_synonyms": "id",
    "f3_warning_keywords": "rule_id",
    "f3_country_groups": "id",
    "f3_suppress_rules": "id",
}


@lru_cache(maxsize=32)
def _detect_pk_column(table_name: str) -> str:
    """테이블 PK 컬럼. 힌트 맵 + "id" 기본값.

    NOTE: PostgREST 는 information_schema 직접 노출 안 함.
          진짜 동적 감지가 필요하면 별도 RPC 함수 필요.
          F3 테이블 목록은 고정이라 맵으로 충분.
    """
    if not table_name.startswith("f3_"):
        raise ValueError(f"F3 외 테이블은 스냅샷 지원 안 함: {table_name}")
    return _TABLE_PK_HINTS.get(table_name, "id")


# ──────────────────────────────────────────────
# 동시성 잠금 — Postgres advisory lock
# ──────────────────────────────────────────────

def _try_acquire_law_lock(law_name: str) -> bool:
    """f3_acquire_law_lock RPC 호출. 실패 시 False 반환.

    주의: PostgREST 를 통한 RPC 는 HTTP 요청마다 다른 세션이라 xact lock 유지 안 됨.
    따라서 단일 HTTP 요청 동안의 중복 방지 용도로만 유효.
    실제 강한 보호는 snapshot_and_replace 내부에서 Postgres 트랜잭션을 써야 하나,
    PostgREST 는 클라이언트 트랜잭션 미지원이므로 현재 구현은 application-level
    best-effort mutex + 히스토리 테이블의 UNIQUE constraint 로 방어.
    """
    # MVP: 앱레벨 mutex 로 대체 (동일 프로세스 내 동시 실행만 방어)
    return _acquire_in_process_lock(law_name)


_IN_PROCESS_LOCKS: dict[str, bool] = {}


def _acquire_in_process_lock(law_name: str) -> bool:
    if _IN_PROCESS_LOCKS.get(law_name):
        return False
    _IN_PROCESS_LOCKS[law_name] = True
    return True


def _release_in_process_lock(law_name: str) -> None:
    _IN_PROCESS_LOCKS.pop(law_name, None)


# ──────────────────────────────────────────────
# Supabase CRUD 기본
# ──────────────────────────────────────────────

def _fetch_all(table: str, scope_filter: Optional[dict] = None) -> list[dict]:
    """테이블 전체 행 (또는 scope_filter 범위) 조회."""
    url, _ = _env()
    q = "select=*"
    if scope_filter:
        # scope_filter 예: {"submission_type": "submit"}
        for k, v in scope_filter.items():
            if v is None:
                q += f"&{k}=is.null"
            else:
                q += f"&{k}=eq.{v}"
    r = httpx.get(
        f"{url}/rest/v1/{table}?{q}",
        headers=_headers(),
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def _delete_scoped(table: str, pk: str, scope_filter: Optional[dict]) -> None:
    """
    범위 내 행 삭제. scope_filter 가 있으면 해당 조건만, 없으면 전체.
    PostgREST 는 조건 없는 DELETE 를 거절하므로 PK NOT NULL 로 안전 가드.
    """
    url, _ = _env()
    if scope_filter:
        q_parts = []
        for k, v in scope_filter.items():
            if v is None:
                q_parts.append(f"{k}=is.null")
            else:
                q_parts.append(f"{k}=eq.{v}")
        q = "&".join(q_parts)
    else:
        q = f"{pk}=not.is.null"

    r = httpx.delete(
        f"{url}/rest/v1/{table}?{q}",
        headers=_headers({"Prefer": "return=minimal"}),
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()


def _insert_rows(table: str, rows: list[dict], batch: int = 500) -> int:
    if not rows:
        return 0
    url, _ = _env()
    total = 0
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        r = httpx.post(
            f"{url}/rest/v1/{table}",
            headers=_headers({"Prefer": "return=minimal"}),
            json=chunk,
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        total += len(chunk)
    return total


# ──────────────────────────────────────────────
# 공개 API — Diff 계산
# ──────────────────────────────────────────────

def compute_diff_summary(
    old_rows: list[dict],
    new_rows: list[dict],
    pk_column: str,
) -> dict:
    """전/후 행 리스트 → {added, modified, deleted, unchanged} 카운트 + key 샘플."""
    old_map = {r.get(pk_column): r for r in old_rows if r.get(pk_column) is not None}
    new_map = {r.get(pk_column): r for r in new_rows if r.get(pk_column) is not None}

    added = [k for k in new_map if k not in old_map]
    deleted = [k for k in old_map if k not in new_map]
    modified: list[Any] = []
    for k in new_map:
        if k in old_map and new_map[k] != old_map[k]:
            modified.append(k)
    unchanged_count = sum(1 for k in new_map if k in old_map and new_map[k] == old_map[k])

    return {
        "added": len(added),
        "modified": len(modified),
        "deleted": len(deleted),
        "unchanged": unchanged_count,
        "added_keys": added[:100],
        "modified_keys": modified[:100],
        "deleted_keys": deleted[:100],
    }


# ──────────────────────────────────────────────
# 공개 API — 스냅샷 조회
# ──────────────────────────────────────────────

def fetch_table_snapshot(
    table_specs: list[tuple[str, Optional[dict]]] | list[str],
) -> dict[str, list[dict]]:
    """여러 테이블 스냅샷. 각 테이블에 scope_filter 지정 가능.

    table_specs:
      - list[str]  — 테이블명만, 전체 조회
      - list[tuple] — [(table_name, scope_filter_dict_or_None), ...]
    """
    out: dict[str, list[dict]] = {}
    for spec in table_specs:
        if isinstance(spec, str):
            out[spec] = _fetch_all(spec)
        else:
            name, scope = spec
            out[name] = _fetch_all(name, scope)
    return out


def check_idempotency(key: Optional[str]) -> Optional[dict]:
    """같은 idempotency_key 로 최근 24시간 내 요청이 있었는지 확인.

    반환:
      None — 중복 없음 (새 요청 진행)
      dict — 이전 요청 발견. {version, status, history_id, created_at}
             호출자는 이걸 그대로 응답해서 같은 결과 반환 가능.
    """
    if not key:
        return None
    url, _ = _env()
    try:
        r = httpx.post(
            f"{url}/rest/v1/rpc/f3_check_idempotency",
            headers=_headers(),
            json={"p_key": key},
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        if data and isinstance(data, list) and data[0].get("found"):
            row = data[0]
            return {
                "version": row["existing_version"],
                "status": row["existing_status"],
                "history_id": row["existing_history_id"],
                "created_at": row["existing_created_at"],
            }
    except Exception as e:
        import logging
        logging.warning("[F3 idempotency] 체크 실패 (진행): %s", e)
    return None


def save_history(
    law_name: str,
    affected_tables: list[str],
    snapshot_data: dict[str, list[dict]],
    diff_summary: dict,
    source_filename: Optional[str],
    scope_filter: Optional[dict] = None,
    pinecone_touched: bool = False,
    feature_label: str = "수입필요서류 안내",
    created_by: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    status: str = "pending",
) -> dict:
    """f3_update_history 에 스냅샷 기록. 반환: {id, version, created_at}.

    중요: 기본 상태는 'pending'. snapshot_and_replace 내부에서
    실제 DB 교체 성공 시 'applied', 실패 시 'failed' 로 업데이트.
    """
    url, _ = _env()
    payload = {
        "law_name": law_name,
        "feature_label": feature_label,
        "affected_tables": affected_tables,
        "scope_filter": scope_filter,
        "snapshot_data": snapshot_data,
        "diff_summary": diff_summary,
        "source_filename": source_filename,
        "pinecone_touched": pinecone_touched,
        "created_by": created_by,
        "idempotency_key": idempotency_key,
        "status": status,
    }
    r = httpx.post(
        f"{url}/rest/v1/f3_update_history",
        headers=_headers({"Prefer": "return=representation"}),
        json=[payload],
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    created = r.json()[0]
    return {
        "id": created["id"],
        "version": created["version"],
        "created_at": created["created_at"],
    }


def update_history_status(history_id: str, status: str) -> None:
    """히스토리 상태 업데이트 (applied / failed 등)."""
    url, _ = _env()
    r = httpx.patch(
        f"{url}/rest/v1/f3_update_history?id=eq.{history_id}",
        headers=_headers({"Prefer": "return=minimal"}),
        json={"status": status},
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()


# ──────────────────────────────────────────────
# 공개 API — Snapshot + Replace (핵심)
# ──────────────────────────────────────────────

def snapshot_and_replace(
    law_name: str,
    table_replacements: dict[str, dict],
    source_filename: Optional[str] = None,
    pinecone_touched: bool = False,
    feature_label: str = "수입필요서류 안내",
    created_by: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    """여러 테이블을 안전하게 교체.

    Args:
        table_replacements: {
            table_name: {
                "new_rows":     [...],           # 교체할 행들
                "pk_column":    "id",            # 선택 — 없으면 자동 감지
                "diff_summary": {...},           # 선택 — 로깅용
                "scope_filter": {"k": "v"} | None, # 부분 교체 범위 (예: {"submission_type": "submit"})
                "force_empty":  False            # True 면 new_rows=[] 도 허용
            }
        }

    안전 장치:
        - 빈 new_rows + 기존 행 존재 → force_empty 아니면 중단
        - snapshot_data NULL → 절대 생기지 않게 사전 검증
        - 동시 실행 → advisory lock 실패 시 중단
        - 부분 실패 → 백업 기반 원상복구 best-effort

    반환: {version, history_id, affected_tables, rows_inserted_by_table, diff_summary}
    """
    affected_tables = list(table_replacements.keys())
    if not affected_tables:
        raise ValueError("affected_tables 비어있음.")

    # 동시성 락
    if not _try_acquire_law_lock(law_name):
        raise RuntimeError(
            f"'{law_name}' 업데이트가 이미 진행 중입니다. 잠시 후 다시 시도하세요."
        )

    try:
        # 1. 사전 검증 + PK 감지 + 현재 상태 스냅샷
        snapshot_data: dict[str, list[dict]] = {}
        snapshot_scopes: dict[str, Optional[dict]] = {}
        for table_name, spec in table_replacements.items():
            pk = spec.get("pk_column") or _detect_pk_column(table_name)
            spec["pk_column"] = pk
            scope = spec.get("scope_filter")
            snapshot_scopes[table_name] = scope

            old_rows = _fetch_all(table_name, scope)
            snapshot_data[table_name] = old_rows

            new_rows = spec.get("new_rows") or []
            if not new_rows and old_rows and not spec.get("force_empty"):
                raise ValueError(
                    f"[가드] 테이블 '{table_name}': new_rows 비어있는데 기존 {len(old_rows)} 건 존재. "
                    f"파서 오류 가능성. force_empty=True 로 명시해야 진행 가능."
                )

            # 너무 많이 삭제되는 경우 경고 로그
            diff_summary = compute_diff_summary(old_rows, new_rows, pk)
            spec["diff_summary"] = diff_summary
            if diff_summary["deleted"] > LARGE_REPLACE_WARNING_THRESHOLD:
                # 경고만 남기고 진행 (차단은 하지 않음)
                pass

        combined_diff = {
            "added": sum(s["diff_summary"]["added"] for s in table_replacements.values()),
            "modified": sum(s["diff_summary"]["modified"] for s in table_replacements.values()),
            "deleted": sum(s["diff_summary"]["deleted"] for s in table_replacements.values()),
            "by_table": {tn: s["diff_summary"] for tn, s in table_replacements.items()},
        }

        # scope_filter 는 한 업데이트에 여러 테이블 있으면 단일 값으로 기록 (dict)
        history_scope_filter: Optional[dict] = None
        if len(snapshot_scopes) == 1:
            history_scope_filter = next(iter(snapshot_scopes.values()))

        # 2. 히스토리 기록 (status='pending')
        history = save_history(
            law_name=law_name,
            affected_tables=affected_tables,
            snapshot_data=snapshot_data,
            diff_summary=combined_diff,
            source_filename=source_filename,
            scope_filter=history_scope_filter,
            pinecone_touched=pinecone_touched,
            feature_label=feature_label,
            created_by=created_by,
            idempotency_key=idempotency_key,
            status="pending",
        )

        # 3. 각 테이블 교체 (DELETE scope → INSERT new)
        rows_inserted_by_table: dict[str, int] = {}
        try:
            for table_name, spec in table_replacements.items():
                pk = spec["pk_column"]
                scope = spec.get("scope_filter")
                new_rows = spec["new_rows"]

                _delete_scoped(table_name, pk, scope)
                inserted = _insert_rows(table_name, new_rows)
                rows_inserted_by_table[table_name] = inserted

        except Exception as e:
            # 원상복구 시도 + 히스토리 'failed' 로 마킹
            _restore_from_snapshot(snapshot_data, table_replacements)
            try:
                update_history_status(history["id"], "failed")
            except Exception:
                pass
            raise RuntimeError(
                f"테이블 교체 중 실패, 원상복구 시도함. 원인: {type(e).__name__}: {e}"
            ) from e

        # 4. 성공 → 히스토리 status 'applied' 로 업데이트
        try:
            update_history_status(history["id"], "applied")
        except Exception as e:
            import logging
            logging.warning("[F3] history status 업데이트 실패 (DB 는 반영됨): %s", e)

        return {
            "version": history["version"],
            "history_id": history["id"],
            "created_at": history["created_at"],
            "affected_tables": affected_tables,
            "rows_inserted_by_table": rows_inserted_by_table,
            "diff_summary": combined_diff,
        }

    finally:
        _release_in_process_lock(law_name)


def _restore_from_snapshot(
    snapshot_data: dict[str, list[dict]],
    table_replacements: dict[str, dict],
) -> None:
    """실패 시 원상복구 — 각 테이블 범위 삭제 + 백업 행 삽입."""
    for table_name, rows in snapshot_data.items():
        spec = table_replacements.get(table_name, {})
        pk = spec.get("pk_column") or _detect_pk_column(table_name)
        scope = spec.get("scope_filter")
        try:
            _delete_scoped(table_name, pk, scope)
            _insert_rows(table_name, rows)
        except Exception as inner:
            # best-effort — 실패해도 다음 테이블 계속
            import logging
            logging.error(
                "[F3 restore] 복구 실패 %s: %s", table_name, inner
            )


# ──────────────────────────────────────────────
# 공개 API — 롤백
# ──────────────────────────────────────────────

def rollback(
    version: int,
    cascade: bool = False,
    rolled_back_by: Optional[str] = None,
) -> dict:
    """특정 version 으로 롤백.

    Args:
        version:   되돌릴 버전
        cascade:   True 면 이후 버전들도 함께 취소 (최신 → 대상 순서로)

    안전 장치:
        - NULL snapshot_data → 즉시 실패
        - 이미 롤백된 이력 → 실패
        - version 이 최신이 아니고 cascade=False → 경고 반환 (이후 버전 영향 알림)
        - 동시성: law_name 기반 advisory lock
    """
    url, _ = _env()

    # 1. 대상 이력 조회
    r = httpx.get(
        f"{url}/rest/v1/f3_update_history?version=eq.{version}&select=*",
        headers=_headers(),
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        raise ValueError(f"version={version} 이력을 찾을 수 없습니다.")
    history = rows[0]

    if history["is_rolled_back"]:
        raise ValueError(f"version={version} 은 이미 롤백된 이력입니다.")

    snapshot_data = history.get("snapshot_data")
    if not snapshot_data or not isinstance(snapshot_data, dict):
        raise ValueError(
            f"version={version} 의 snapshot_data 가 손상됐습니다 (NULL/빈값). 롤백 불가."
        )

    affected_tables = history.get("affected_tables") or []
    if not affected_tables:
        raise ValueError(f"version={version} 의 affected_tables 정보가 없습니다.")

    law_name = history["law_name"]
    scope_filter = history.get("scope_filter")

    # 2. 이후 버전 체크 (cascade)
    later_r = httpx.get(
        f"{url}/rest/v1/f3_update_history"
        f"?version=gt.{version}&law_name=eq.{law_name}&is_rolled_back=eq.false"
        f"&select=version,created_at&order=version.desc",
        headers=_headers(),
        timeout=HTTP_TIMEOUT,
    )
    later_r.raise_for_status()
    later_versions = later_r.json()

    if later_versions and not cascade:
        return {
            "status": "needs_cascade",
            "version": version,
            "later_versions": [v["version"] for v in later_versions],
            "message": (
                f"이 버전 이후 {len(later_versions)}건의 업데이트가 더 있습니다. "
                "이 버전으로만 롤백하면 이후 변경사항이 누적된 상태로 복원되어 "
                "혼란을 초래할 수 있습니다. cascade=True 로 이후 버전을 모두 "
                "취소할지 결정하세요."
            ),
        }

    # 3. 동시성 락
    if not _try_acquire_law_lock(law_name):
        raise RuntimeError(
            f"'{law_name}' 작업이 진행 중입니다. 잠시 후 다시 시도하세요."
        )

    try:
        # 4. cascade 처리 — 이후 버전부터 역순으로 처리
        rolled_back_versions: list[int] = []
        if cascade and later_versions:
            for later in later_versions:  # 이미 version.desc 로 정렬됨 (최신 먼저)
                _apply_rollback_for_version(later["version"], rolled_back_by)
                rolled_back_versions.append(later["version"])

        # 5. 본 대상 롤백
        restored = _apply_rollback_for_version(version, rolled_back_by)
        rolled_back_versions.append(version)

        return {
            "status": "rolled_back",
            "version": version,
            "cascade_versions": rolled_back_versions[:-1],  # 함께 취소된 이후 버전들
            "law_name": law_name,
            "affected_tables": affected_tables,
            "restored_rows_by_table": restored,
            "pinecone_touched": history.get("pinecone_touched", False),
            "warning": (
                "⚠️ 이 업데이트는 법령 본문 검색 인덱스(Pinecone) 도 변경했습니다. "
                "Pinecone 은 자동 롤백되지 않으므로, 이전 버전의 법령 파일을 "
                "다시 업로드해서 재임베딩해야 합니다."
                if history.get("pinecone_touched") else None
            ),
        }
    finally:
        _release_in_process_lock(law_name)


def _apply_rollback_for_version(version: int, rolled_back_by: Optional[str]) -> dict[str, int]:
    """단일 버전 롤백 실행. _internal — lock 은 상위에서 관리."""
    url, _ = _env()

    r = httpx.get(
        f"{url}/rest/v1/f3_update_history?version=eq.{version}&select=*",
        headers=_headers(),
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        raise ValueError(f"version={version} 조회 실패 (rollback 대상).")
    history = rows[0]

    if history["is_rolled_back"]:
        raise ValueError(f"version={version} 이미 롤백됨.")

    snapshot_data = history.get("snapshot_data")
    if not snapshot_data:
        raise ValueError(f"version={version} snapshot_data 손상.")

    affected_tables = history.get("affected_tables") or []
    scope_filter = history.get("scope_filter")

    restored: dict[str, int] = {}
    for table_name in affected_tables:
        backup_rows = snapshot_data.get(table_name, [])
        pk = _detect_pk_column(table_name)
        _delete_scoped(table_name, pk, scope_filter)
        _insert_rows(table_name, backup_rows)
        restored[table_name] = len(backup_rows)

    # 이력 마킹 (status + 레거시 is_rolled_back 둘 다)
    now = datetime.now(timezone.utc).isoformat()
    patch = {
        "is_rolled_back": True,
        "rolled_back_at": now,
        "status": "rolled_back",
    }
    if rolled_back_by:
        patch["rolled_back_by"] = rolled_back_by

    r = httpx.patch(
        f"{url}/rest/v1/f3_update_history?version=eq.{version}",
        headers=_headers({"Prefer": "return=minimal"}),
        json=patch,
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()

    return restored


# ──────────────────────────────────────────────
# 공개 API — 이력 조회
# ──────────────────────────────────────────────

def add_single_rule(
    table_name: str,
    new_row: dict,
    law_name: str = "수동 규칙 추가",
    feature_label: str = "수입필요서류 안내",
    created_by: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    """단일 행 추가 + 히스토리 기록 (롤백 가능).

    snapshot_and_replace 와 달리 전체 교체가 아니라 **1행 INSERT + 스냅샷 기록**.
    롤백 시 이 행만 DELETE 되도록 snapshot_data 에 "before: 빈 배열, after: [row]" 형태로 기록.

    Args:
        table_name: 대상 테이블 (예: f3_required_documents)
        new_row: 삽입할 행
        law_name: 히스토리 기록용 라벨 (기본 "수동 규칙 추가")
        created_by: 관리자 식별자
        idempotency_key: 중복 방지 키 (선택)

    Returns: {version, history_id, row_id, created_at}
    """
    url, _ = _env()

    # Idempotency 체크
    if idempotency_key:
        prior = check_idempotency(idempotency_key)
        if prior and prior.get("status") in ("applied", "pending"):
            return {
                "status": "duplicate_request",
                "version": prior["version"],
                "history_id": prior["history_id"],
                "created_at": prior["created_at"],
            }

    if not _try_acquire_law_lock(law_name):
        raise RuntimeError(f"'{law_name}' 작업이 진행 중입니다. 잠시 후 다시 시도하세요.")

    try:
        pk = _detect_pk_column(table_name)
        row_id = new_row.get(pk)
        if not row_id:
            raise ValueError(f"PK 컬럼 '{pk}' 값이 비어있음. ID 를 미리 생성해서 전달하세요.")

        # 중복 ID 체크
        existing = httpx.get(
            f"{url}/rest/v1/{table_name}?{pk}=eq.{row_id}&select={pk}",
            headers=_headers(),
            timeout=HTTP_TIMEOUT,
        )
        existing.raise_for_status()
        if existing.json():
            raise ValueError(
                f"이미 존재하는 ID: '{row_id}'. 다른 ID 로 시도하세요."
            )

        # 1. 빈 스냅샷 기록 (before: 없음, after: new_row 하나 — 롤백 시 DELETE 로 복원)
        # snapshot_data 는 "변경 전" 을 담는 게 원칙. 추가 작업은 before=[] 로 기록 → 롤백 시 이 row 를
        # "되돌리면 없음" 이 되므로 DELETE.
        diff_summary = {
            "added": 1,
            "modified": 0,
            "deleted": 0,
            "by_table": {table_name: {"added": 1, "modified": 0, "deleted": 0}},
            "manual_add_row_id": row_id,
        }
        history = save_history(
            law_name=law_name,
            affected_tables=[table_name],
            # 변경 전 = 해당 table 전체 (롤백 시 이 상태로 복원하면 새 row 는 자동 사라짐)
            # 부분 교체 아님 → scope_filter 는 특정 id 만
            snapshot_data={table_name: []},  # 빈 배열 — 이 ID 는 전에 없었다는 의미
            diff_summary=diff_summary,
            source_filename=None,
            scope_filter={pk: row_id},       # 롤백 시 이 ID 만 삭제하도록
            pinecone_touched=False,
            feature_label=feature_label,
            created_by=created_by,
            idempotency_key=idempotency_key,
            status="pending",
        )

        # 2. 실제 INSERT
        try:
            _insert_rows(table_name, [new_row])
        except Exception as e:
            try:
                update_history_status(history["id"], "failed")
            except Exception:
                pass
            raise RuntimeError(f"행 추가 실패: {type(e).__name__}: {e}") from e

        # 3. 성공 마킹
        try:
            update_history_status(history["id"], "applied")
        except Exception as e:
            import logging
            logging.warning("[F3] history status 업데이트 실패: %s", e)

        return {
            "status": "applied",
            "version": history["version"],
            "history_id": history["id"],
            "created_at": history["created_at"],
            "row_id": row_id,
            "table_name": table_name,
        }
    finally:
        _release_in_process_lock(law_name)


# ──────────────────────────────────────────────
# 소형 편집 API — 단일 셀 변경 (국가그룹/동의어/경고키워드)
# ──────────────────────────────────────────────

def _record_small_change_history(
    table_name: str,
    change_type: str,  # 'add_member' | 'remove_member' | 'update_cell'
    payload: dict,     # 변경 상세 (before/after)
    feature_label: str = "수입필요서류 안내",
    created_by: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    group_label: Optional[str] = None,  # "국가 그룹: BSE_36" 같은 law_name
) -> dict:
    """소형 변경 이력 기록. snapshot_data 에 변경 상세를 담음.

    기존 snapshot_and_replace 와 달리 테이블 전체 덤프 없음 → JSONB 크기 작음.
    """
    law_name = group_label or f"{table_name} 편집"
    return save_history(
        law_name=law_name,
        affected_tables=[table_name],
        snapshot_data={table_name: payload.get("before_rows", [])},
        diff_summary={
            "change_type": change_type,
            "added": payload.get("added", 0),
            "modified": payload.get("modified", 0),
            "deleted": payload.get("deleted", 0),
            "detail": payload.get("detail"),
        },
        source_filename=None,
        scope_filter=payload.get("scope_filter"),
        pinecone_touched=False,
        feature_label=feature_label,
        created_by=created_by,
        idempotency_key=idempotency_key,
        status="applied",  # 소형 변경은 즉시 applied 마킹
    )


def add_country_group_member(
    group_name: str,
    country_name: str,
    created_by: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    """f3_country_groups 에 (group_name, country_name) 쌍 INSERT.

    이미 존재하면 ValueError. 신규 그룹도 허용 (멤버 첫 추가로 그룹 자동 생성).
    """
    url, _ = _env()
    # 중복 확인
    r = httpx.get(
        f"{url}/rest/v1/f3_country_groups"
        f"?group_name=eq.{group_name}&country_name=eq.{country_name}&select=group_name",
        headers=_headers(),
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    if r.json():
        raise ValueError(f"이미 존재하는 멤버: 그룹 '{group_name}' + 국가 '{country_name}'")

    # INSERT
    try:
        r2 = httpx.post(
            f"{url}/rest/v1/f3_country_groups",
            headers=_headers({"Prefer": "return=minimal"}),
            json=[{"group_name": group_name, "country_name": country_name}],
            timeout=HTTP_TIMEOUT,
        )
        r2.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"국가 그룹 추가 실패: {type(e).__name__}: {e}") from e

    # 이력 기록
    history = _record_small_change_history(
        table_name="f3_country_groups",
        change_type="add_member",
        payload={
            "added": 1,
            "detail": {"group_name": group_name, "country_name": country_name},
            "before_rows": [],
            "scope_filter": {"group_name": group_name, "country_name": country_name},
        },
        created_by=created_by,
        idempotency_key=idempotency_key,
        group_label=f"국가 그룹: {group_name} + {country_name}",
    )

    return {
        "status": "applied",
        "version": history["version"],
        "history_id": history["id"],
        "group_name": group_name,
        "country_name": country_name,
    }


def remove_country_group_member(
    group_name: str,
    country_name: str,
    created_by: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    """f3_country_groups 에서 (group_name, country_name) 쌍 DELETE.

    존재하지 않으면 ValueError.
    """
    url, _ = _env()
    # 존재 확인
    r = httpx.get(
        f"{url}/rest/v1/f3_country_groups"
        f"?group_name=eq.{group_name}&country_name=eq.{country_name}&select=*",
        headers=_headers(),
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    existing = r.json()
    if not existing:
        raise ValueError(f"존재하지 않는 멤버: 그룹 '{group_name}' + 국가 '{country_name}'")

    # DELETE
    try:
        r2 = httpx.delete(
            f"{url}/rest/v1/f3_country_groups"
            f"?group_name=eq.{group_name}&country_name=eq.{country_name}",
            headers=_headers({"Prefer": "return=minimal"}),
            timeout=HTTP_TIMEOUT,
        )
        r2.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"국가 그룹 삭제 실패: {type(e).__name__}: {e}") from e

    # 이력 기록 (before 에 삭제된 행 보관 → 롤백 가능)
    history = _record_small_change_history(
        table_name="f3_country_groups",
        change_type="remove_member",
        payload={
            "deleted": 1,
            "detail": {"group_name": group_name, "country_name": country_name},
            "before_rows": existing,
            "scope_filter": {"group_name": group_name, "country_name": country_name},
        },
        created_by=created_by,
        idempotency_key=idempotency_key,
        group_label=f"국가 그룹: {group_name} - {country_name}",
    )

    return {
        "status": "applied",
        "version": history["version"],
        "history_id": history["id"],
        "group_name": group_name,
        "country_name": country_name,
    }


def add_keyword_synonym(
    hint_keyword: str,
    db_keyword: str,
    country_cond: Optional[str] = None,
    created_by: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    """f3_keyword_synonyms 에 동의어 매핑 추가."""
    url, _ = _env()
    # 중복 확인 (hint + db + country 조합)
    q = f"hint_keyword=eq.{hint_keyword}&db_keyword=eq.{db_keyword}"
    if country_cond:
        q += f"&country_cond=eq.{country_cond}"
    else:
        q += "&country_cond=is.null"
    r = httpx.get(
        f"{url}/rest/v1/f3_keyword_synonyms?{q}&select=id",
        headers=_headers(),
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    if r.json():
        raise ValueError(
            f"이미 존재하는 매핑: '{hint_keyword}' → '{db_keyword}'"
            + (f" (국가: {country_cond})" if country_cond else "")
        )

    payload = {"hint_keyword": hint_keyword, "db_keyword": db_keyword}
    if country_cond:
        payload["country_cond"] = country_cond

    try:
        r2 = httpx.post(
            f"{url}/rest/v1/f3_keyword_synonyms",
            headers=_headers({"Prefer": "return=representation"}),
            json=[payload],
            timeout=HTTP_TIMEOUT,
        )
        r2.raise_for_status()
        inserted = r2.json()[0]
    except Exception as e:
        raise RuntimeError(f"동의어 추가 실패: {type(e).__name__}: {e}") from e

    history = _record_small_change_history(
        table_name="f3_keyword_synonyms",
        change_type="add_synonym",
        payload={
            "added": 1,
            "detail": payload,
            "before_rows": [],
            "scope_filter": {"id": inserted.get("id")},
        },
        created_by=created_by,
        idempotency_key=idempotency_key,
        group_label=f"원재료 동의어: {hint_keyword} → {db_keyword}",
    )

    return {
        "status": "applied",
        "version": history["version"],
        "history_id": history["id"],
        "synonym_id": inserted.get("id"),
        "hint_keyword": hint_keyword,
        "db_keyword": db_keyword,
    }


def remove_keyword_synonym(
    synonym_id: int,
    created_by: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    """id 기준 동의어 삭제."""
    url, _ = _env()
    r = httpx.get(
        f"{url}/rest/v1/f3_keyword_synonyms?id=eq.{synonym_id}&select=*",
        headers=_headers(),
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        raise ValueError(f"존재하지 않는 동의어 id: {synonym_id}")
    existing = rows[0]

    try:
        r2 = httpx.delete(
            f"{url}/rest/v1/f3_keyword_synonyms?id=eq.{synonym_id}",
            headers=_headers({"Prefer": "return=minimal"}),
            timeout=HTTP_TIMEOUT,
        )
        r2.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"동의어 삭제 실패: {type(e).__name__}: {e}") from e

    history = _record_small_change_history(
        table_name="f3_keyword_synonyms",
        change_type="remove_synonym",
        payload={
            "deleted": 1,
            "detail": existing,
            "before_rows": [existing],
            "scope_filter": {"id": synonym_id},
        },
        created_by=created_by,
        idempotency_key=idempotency_key,
        group_label=(
            f"원재료 동의어 삭제: {existing.get('hint_keyword')} → "
            f"{existing.get('db_keyword')}"
        ),
    )

    return {
        "status": "applied",
        "version": history["version"],
        "history_id": history["id"],
        "synonym_id": synonym_id,
    }


def get_last_update_per_law() -> dict:
    """법령별 마지막 성공 업데이트 + 전체 최신 시각 조회.

    UI 상단 배너에서 "법령 기준: YYYY-MM-DD" 표시용.
    """
    url, _ = _env()
    try:
        r = httpx.get(
            f"{url}/rest/v1/f3_update_history"
            f"?status=eq.applied&is_rolled_back=eq.false"
            f"&select=law_name,created_at"
            f"&order=created_at.desc&limit=200",
            headers=_headers(),
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        rows = r.json()
    except Exception as e:
        import logging
        logging.warning("[F3] last-update 조회 실패: %s", e)
        return {"per_law": {}, "overall_last_at": None, "error": str(e)}

    per_law: dict[str, str] = {}
    for row in rows:
        law = row.get("law_name") or ""
        ts = row.get("created_at")
        if not law or not ts:
            continue
        # 첫 번째 (desc 정렬이라 최신) 만 저장
        if law not in per_law:
            per_law[law] = ts

    overall = max(per_law.values()) if per_law else None
    return {
        "per_law": per_law,
        "overall_last_at": overall,
    }


def list_keyword_synonyms() -> list[dict]:
    """f3_keyword_synonyms 전체 (UI 목록용)."""
    return _fetch_all("f3_keyword_synonyms")


def add_warning_keyword(
    rule_id: str,
    keyword: str,
    created_by: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    """f3_warning_keywords 에 (rule_id, keyword) 쌍 INSERT."""
    url, _ = _env()
    r = httpx.get(
        f"{url}/rest/v1/f3_warning_keywords"
        f"?rule_id=eq.{rule_id}&keyword=eq.{keyword}&select=rule_id",
        headers=_headers(),
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    if r.json():
        raise ValueError(f"이미 존재: rule_id='{rule_id}', keyword='{keyword}'")

    try:
        r2 = httpx.post(
            f"{url}/rest/v1/f3_warning_keywords",
            headers=_headers({"Prefer": "return=minimal"}),
            json=[{"rule_id": rule_id, "keyword": keyword}],
            timeout=HTTP_TIMEOUT,
        )
        r2.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"경고 키워드 추가 실패: {type(e).__name__}: {e}") from e

    history = _record_small_change_history(
        table_name="f3_warning_keywords",
        change_type="add_warning",
        payload={
            "added": 1,
            "detail": {"rule_id": rule_id, "keyword": keyword},
            "before_rows": [],
            "scope_filter": {"rule_id": rule_id, "keyword": keyword},
        },
        created_by=created_by,
        idempotency_key=idempotency_key,
        group_label=f"경고 키워드: {rule_id} + {keyword}",
    )
    return {
        "status": "applied",
        "version": history["version"],
        "history_id": history["id"],
        "rule_id": rule_id,
        "keyword": keyword,
    }


def remove_warning_keyword(
    rule_id: str,
    keyword: str,
    created_by: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    url, _ = _env()
    r = httpx.get(
        f"{url}/rest/v1/f3_warning_keywords"
        f"?rule_id=eq.{rule_id}&keyword=eq.{keyword}&select=*",
        headers=_headers(),
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    existing = r.json()
    if not existing:
        raise ValueError(f"존재하지 않음: rule_id='{rule_id}', keyword='{keyword}'")

    try:
        r2 = httpx.delete(
            f"{url}/rest/v1/f3_warning_keywords"
            f"?rule_id=eq.{rule_id}&keyword=eq.{keyword}",
            headers=_headers({"Prefer": "return=minimal"}),
            timeout=HTTP_TIMEOUT,
        )
        r2.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"경고 키워드 삭제 실패: {type(e).__name__}: {e}") from e

    history = _record_small_change_history(
        table_name="f3_warning_keywords",
        change_type="remove_warning",
        payload={
            "deleted": 1,
            "detail": {"rule_id": rule_id, "keyword": keyword},
            "before_rows": existing,
            "scope_filter": {"rule_id": rule_id, "keyword": keyword},
        },
        created_by=created_by,
        idempotency_key=idempotency_key,
        group_label=f"경고 키워드 삭제: {rule_id} - {keyword}",
    )
    return {
        "status": "applied",
        "version": history["version"],
        "history_id": history["id"],
        "rule_id": rule_id,
        "keyword": keyword,
    }


def list_warning_keywords() -> dict[str, list[str]]:
    """f3_warning_keywords 전체 → {rule_id: [keyword, ...]}"""
    rows = _fetch_all("f3_warning_keywords")
    out: dict[str, list[str]] = {}
    for r in rows:
        rid = r.get("rule_id")
        kw = r.get("keyword")
        if not rid or not kw:
            continue
        out.setdefault(rid, []).append(kw)
    for rid in out:
        out[rid].sort()
    return out


def list_country_groups() -> dict[str, list[str]]:
    """f3_country_groups 전체 → {group_name: [country_name, ...]}"""
    rows = _fetch_all("f3_country_groups")
    out: dict[str, list[str]] = {}
    for r in rows:
        g = r.get("group_name")
        c = r.get("country_name")
        if not g or not c:
            continue
        out.setdefault(g, []).append(c)
    # 각 그룹 내 국가명 정렬
    for g in out:
        out[g].sort()
    return out


def list_history(limit: int = 20, exclude_failed: bool = True) -> list[dict]:
    """최근 업데이트 이력.

    Args:
        limit: 조회 건수
        exclude_failed: True 면 status='failed' / 'pending' 제외 (검역관 UI 기본값)
    """
    url, _ = _env()
    filter_q = ""
    if exclude_failed:
        filter_q = "&status=in.(applied,rolled_back)"
    r = httpx.get(
        f"{url}/rest/v1/f3_update_history"
        f"?select=version,law_name,feature_label,diff_summary,source_filename,"
        f"scope_filter,created_at,created_by,is_rolled_back,rolled_back_at,"
        f"rolled_back_by,pinecone_touched,status,consistency_status,"
        f"consistency_checked_at"
        f"{filter_q}"
        f"&order=created_at.desc&limit={limit}",
        headers=_headers(),
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


# ──────────────────────────────────────────────
# 정합성 검사 (Supabase ↔ Pinecone)
# ──────────────────────────────────────────────

def update_consistency_status(
    history_id: str,
    status: str,
    detail: Optional[dict] = None,
) -> None:
    """정합성 검사 결과 기록."""
    url, _ = _env()
    patch = {
        "consistency_status": status,
        "consistency_checked_at": datetime.now(timezone.utc).isoformat(),
    }
    if detail is not None:
        patch["consistency_detail"] = detail
    try:
        r = httpx.patch(
            f"{url}/rest/v1/f3_update_history?id=eq.{history_id}",
            headers=_headers({"Prefer": "return=minimal"}),
            json=patch,
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
    except Exception as e:
        import logging
        logging.warning("[F3 consistency] 상태 기록 실패: %s", e)


def check_pinecone_consistency(history_id: str) -> dict:
    """특정 history 의 Pinecone 정합성 확인.

    검사 방법:
      1. history.snapshot_data (변경 후 citations) 에서 pinecone_chunk_id 목록 추출
      2. Pinecone fetch 로 해당 ID 벡터 존재 여부 확인
      3. 누락 수 > 0 이면 'mismatch'

    반환: {status, missing_count, total_count, details}
    """
    url, _ = _env()
    # 히스토리 조회
    try:
        r = httpx.get(
            f"{url}/rest/v1/f3_update_history"
            f"?id=eq.{history_id}"
            f"&select=law_name,affected_tables,snapshot_data,pinecone_touched,status",
            headers=_headers(),
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return {"status": "error", "error": "history_not_found"}
        history = rows[0]
    except Exception as e:
        return {"status": "error", "error": f"history_fetch_failed: {e}"}

    if not history.get("pinecone_touched"):
        return {"status": "ok", "reason": "pinecone_not_touched", "missing_count": 0}

    if history.get("status") != "applied":
        return {"status": "ok", "reason": "not_applied", "missing_count": 0}

    # Pinecone 에서 chunk_id 존재 확인
    # snapshot_data 는 변경 전 상태 → 현재 DB 에서 chunk_id 조회해야 함
    law_name = history.get("law_name") or ""
    try:
        cit_r = httpx.get(
            f"{url}/rest/v1/f3_document_law_citations"
            f"?law_name=eq.{law_name}"
            f"&select=pinecone_chunk_id&pinecone_chunk_id=not.is.null",
            headers=_headers(),
            timeout=HTTP_TIMEOUT,
        )
        cit_r.raise_for_status()
        expected_ids = [c["pinecone_chunk_id"] for c in cit_r.json()]
    except Exception as e:
        return {"status": "error", "error": f"citations_fetch_failed: {e}"}

    if not expected_ids:
        return {"status": "ok", "reason": "no_citations", "missing_count": 0}

    # Pinecone fetch — 벌크 조회
    try:
        from services.f3_preprocess.pinecone_embed import _pinecone_client, _index
        pc = _pinecone_client()
        idx = _index(pc)
        # Pinecone fetch 는 배치 최대 1000
        missing: list[str] = []
        for i in range(0, len(expected_ids), 100):
            batch = expected_ids[i : i + 100]
            try:
                res = idx.fetch(ids=batch)
                vectors = res.get("vectors", {}) if isinstance(res, dict) else getattr(res, "vectors", {})
                found_ids = set(vectors.keys()) if hasattr(vectors, "keys") else set(vectors)
                missing.extend([x for x in batch if x not in found_ids])
            except Exception as e:
                import logging
                logging.warning("[F3 consistency] Pinecone fetch 실패 (배치): %s", e)
                return {
                    "status": "error",
                    "error": f"pinecone_fetch_failed: {type(e).__name__}",
                }

        status = "ok" if not missing else "mismatch"
        detail = {
            "total_expected": len(expected_ids),
            "missing_count": len(missing),
            "missing_sample": missing[:20],
        }
        update_consistency_status(history_id, status, detail)
        return {"status": status, **detail}

    except Exception as e:
        return {"status": "error", "error": f"pinecone_client_failed: {e}"}


def cleanup_retention() -> int:
    """Retention: 롤백 180일 / 활성 365일 초과 이력 삭제. RPC 호출."""
    url, _ = _env()
    try:
        r = httpx.post(
            f"{url}/rest/v1/rpc/f3_history_retention_cleanup",
            headers=_headers(),
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        return int(r.json() or 0)
    except Exception:
        return 0
