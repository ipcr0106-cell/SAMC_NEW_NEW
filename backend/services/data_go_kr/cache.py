"""data.go.kr 응답 캐시 — W1-A 트랙 구현.

Supabase `f1_data_go_kr_cache` 테이블을 backend 로 하는 `ResponseCache` 추상화.
단위테스트·개발 환경에서는 Supabase 없이 in-memory `InMemoryResponseCache` 로
대체 가능하도록 Protocol 기반으로 설계했다.

캐시 키:
    sha256(endpoint_id + "|" + json(sorted(params)))

참조:
    - 계획/f1 재설계 계획/06_API_클라이언트_설계.md §6
    - 계획/f1 재설계 계획/07_데이터_모델_변경_설계.md §3-2
    - backend/db/migrations/016_f1_data_go_kr_infra.sql
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 캐시 키 helper
# ---------------------------------------------------------------------------


def build_cache_key(endpoint_id: str, params: Dict[str, Any]) -> str:
    """endpoint_id + 정렬된 params 로 SHA256 캐시 키를 생성한다.

    api_key 값은 캐시 키 계산 전에 호출자가 반드시 제거해야 한다
    (동일 파라미터라도 키가 달라 캐시 파편화 발생).
    """
    # param value 는 str·int·float·bool·None 만 지원 (data.go.kr 쿼리 파라미터 특성)
    normalized = {k: ("" if v is None else str(v)) for k, v in sorted(params.items())}
    payload = f"{endpoint_id}|{json.dumps(normalized, ensure_ascii=False, sort_keys=True)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class CacheEntry:
    """캐시 저장 단위."""

    cache_key: str
    endpoint_id: str
    request_params: Dict[str, Any]
    response_body: Dict[str, Any]
    expires_at: datetime


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ResponseCache(Protocol):
    """캐시 백엔드 Protocol. Supabase/InMemory 모두 이 인터페이스 준수."""

    async def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """캐시 조회. HIT 시 response_body 반환, MISS/만료 시 None."""
        ...

    async def put(
        self,
        cache_key: str,
        *,
        endpoint_id: str,
        request_params: Dict[str, Any],
        response_body: Dict[str, Any],
        ttl_seconds: int,
    ) -> None:
        """캐시 저장. TTL 초 단위."""
        ...

    async def invalidate(self, cache_key: Optional[str] = None) -> int:
        """캐시 무효화. key 미지정 시 전체 초기화. 삭제된 row 수 반환."""
        ...


# ---------------------------------------------------------------------------
# InMemory 구현 (단위테스트·개발용)
# ---------------------------------------------------------------------------


class InMemoryResponseCache:
    """프로세스 로컬 dict 기반 캐시. 단위테스트·Supabase 미설정 환경 fallback."""

    def __init__(self) -> None:
        self._store: Dict[str, CacheEntry] = {}

    async def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        entry = self._store.get(cache_key)
        if entry is None:
            return None
        if entry.expires_at <= datetime.now(timezone.utc):
            # 만료 → 제거 후 MISS
            self._store.pop(cache_key, None)
            return None
        return entry.response_body

    async def put(
        self,
        cache_key: str,
        *,
        endpoint_id: str,
        request_params: Dict[str, Any],
        response_body: Dict[str, Any],
        ttl_seconds: int,
    ) -> None:
        self._store[cache_key] = CacheEntry(
            cache_key=cache_key,
            endpoint_id=endpoint_id,
            request_params=request_params,
            response_body=response_body,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
        )

    async def invalidate(self, cache_key: Optional[str] = None) -> int:
        if cache_key is None:
            deleted = len(self._store)
            self._store.clear()
            return deleted
        return 1 if self._store.pop(cache_key, None) is not None else 0


# ---------------------------------------------------------------------------
# Supabase 구현
# ---------------------------------------------------------------------------


class SupabaseResponseCache:
    """Supabase `f1_data_go_kr_cache` 테이블 기반 캐시.

    supabase-py 동기 API 를 `asyncio.to_thread` 로 감싸 비동기 호출 인터페이스를
    유지한다. Supabase 장애·미설정 시 `RuntimeError` 를 올리므로, 호출자는 필요 시
    `InMemoryResponseCache` 로 graceful fallback 할 수 있다.
    """

    TABLE = "f1_data_go_kr_cache"

    def __init__(self, client: Optional[Any] = None) -> None:
        self._client = client  # supabase.Client 또는 MagicMock (테스트)

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        # lazy import — supabase 미설치 환경 허용 (단위테스트)
        from db.supabase_client import get_supabase

        self._client = get_supabase()
        return self._client

    async def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        import asyncio

        def _fetch() -> Optional[Dict[str, Any]]:
            client = self._get_client()
            try:
                resp = (
                    client.table(self.TABLE)
                    .select("response_body, expires_at")
                    .eq("cache_key", cache_key)
                    .limit(1)
                    .execute()
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Supabase cache get failed: %s", exc)
                return None
            data = getattr(resp, "data", None) or []
            if not data:
                return None
            row = data[0]
            expires_raw = row.get("expires_at")
            if expires_raw:
                try:
                    # Supabase timestamptz → ISO 8601
                    expires_at = datetime.fromisoformat(
                        str(expires_raw).replace("Z", "+00:00")
                    )
                except ValueError:
                    expires_at = None
                if expires_at and expires_at <= datetime.now(timezone.utc):
                    return None
            body = row.get("response_body")
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except json.JSONDecodeError:
                    return None
            return body

        return await asyncio.to_thread(_fetch)

    async def put(
        self,
        cache_key: str,
        *,
        endpoint_id: str,
        request_params: Dict[str, Any],
        response_body: Dict[str, Any],
        ttl_seconds: int,
    ) -> None:
        import asyncio

        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        ).isoformat()

        def _upsert() -> None:
            client = self._get_client()
            try:
                (
                    client.table(self.TABLE)
                    .upsert(
                        {
                            "cache_key": cache_key,
                            "endpoint_id": endpoint_id,
                            "request_params": request_params,
                            "response_body": response_body,
                            "expires_at": expires_at,
                        }
                    )
                    .execute()
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Supabase cache put failed: %s", exc)

        await asyncio.to_thread(_upsert)

    async def invalidate(self, cache_key: Optional[str] = None) -> int:
        import asyncio

        def _delete() -> int:
            client = self._get_client()
            try:
                query = client.table(self.TABLE).delete()
                if cache_key is None:
                    # supabase-py delete 는 최소 1개 filter 요구 → neq
                    query = query.neq("cache_key", "__never_match__")
                else:
                    query = query.eq("cache_key", cache_key)
                resp = query.execute()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Supabase cache invalidate failed: %s", exc)
                return 0
            return len(getattr(resp, "data", None) or [])

        return await asyncio.to_thread(_delete)


__all__ = [
    "build_cache_key",
    "CacheEntry",
    "ResponseCache",
    "InMemoryResponseCache",
    "SupabaseResponseCache",
]
