"""data.go.kr 공공 API 통합 클라이언트 — W1-A 트랙 본체 구현.

본 파일의 `DataGoKrClient` 클래스 **생성자 + 4개 공개 메서드 시그니처**는 Wave 1
Day 0 에 동결되었다 (부모 세션 5d00068 커밋). W1-A 는 시그니처를 **유지**한 채
본체를 구현한다.

핵심 흐름:
    1. `call(endpoint, params)` → 캐시 키 생성 → 캐시 HIT 체크
    2. MISS 시 `CircuitBreaker.allow()` 통과 확인
    3. httpx.AsyncClient 로 GET 호출 (재시도 policy 적용)
    4. `response.header.resultCode` 검증 → `Invalid` 시 `DataGoKrInvalidResponseError`
    5. 응답 본문을 캐시에 저장 + 호출 로그 기록(Supabase `f1_data_go_kr_call_log`)
    6. `response.body.items` 를 list[dict] 로 정규화하여 반환

예외 매핑 (08 §3):
    - 429 → `DataGoKrRateLimitError(retry_after)`
    - 500/503 → 재시도 후 실패 시 `DataGoKrError(transient=True)`
    - Timeout → `DataGoKrTimeoutError(timeout_s)`
    - resultCode != "00" → `DataGoKrInvalidResponseError(result_code)`
    - Circuit Breaker OPEN → `CircuitBreakerOpenError`

참조:
    - 계획/f1 재설계 계획/06_API_클라이언트_설계.md §3, §5, §7, §8
    - 계획/f1 재설계 계획/08_에러_처리_설계.md §3, §5
    - backend/exceptions.py (Day 0 동결)
    - backend/models/f1_types.py `DataGoKrEndpoint`
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Dict, List, Optional

import httpx

from exceptions import (
    CircuitBreakerOpenError,
    DataGoKrError,
    DataGoKrInvalidResponseError,
    DataGoKrRateLimitError,
    DataGoKrTimeoutError,
)
from models.f1_types import DataGoKrEndpoint
from services.data_go_kr.cache import (
    InMemoryResponseCache,
    ResponseCache,
    build_cache_key,
)
from services.data_go_kr.circuit_breaker import CircuitBreakerLike, NoOpBreaker
from services.data_go_kr.endpoints import Endpoint, get_endpoint
from services.data_go_kr.models import (
    AdditiveSpec,
    ComponentInfo,
    IngredientInfo,
    RawMaterialInfo,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 재시도 정책 상수 (06 §8 기준)
# ---------------------------------------------------------------------------

# HTTP status → backoff 계수(초). 실제 대기 = coefficient * 2**(retry_idx) + jitter
_RETRY_BACKOFF_429 = [2.0, 4.0, 8.0]
_RETRY_BACKOFF_5XX = [1.0, 2.0, 4.0]
_RETRY_BACKOFF_NETWORK = 1.0  # 고정 1s
_MAX_JITTER_S = 0.25


class DataGoKrClient:
    """data.go.kr 4종 엔드포인트 통합 클라이언트 (Day 0 시그니처 유지)."""

    def __init__(
        self,
        api_key: str,
        *,
        timeout_s: float = 15.0,
        max_retries: int = 3,
        cache: Optional[ResponseCache] = None,
        breaker: Optional[CircuitBreakerLike] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        call_logger: Optional["CallLogger"] = None,
    ) -> None:
        """Day 0 동결 생성자.

        Args:
            api_key: F1_DATA_GO_KR_API_KEY (환경변수). 4 엔드포인트 공용.
            timeout_s: HTTP 요청 타임아웃 (초). 기본 15초.
            max_retries: 재시도 횟수. 기본 3회.
            cache: 응답 캐시 구현체. None 이면 InMemory fallback.
            breaker: Circuit Breaker. None 이면 NoOp (W1-C 통합 전 기본값).
            http_client: 외부 주입 httpx.AsyncClient (단위테스트에서 respx 주입).
            call_logger: 호출 로그 기록기 (Supabase `f1_data_go_kr_call_log`).
        """
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self._cache: ResponseCache = cache or InMemoryResponseCache()
        self._breaker: CircuitBreakerLike = breaker or NoOpBreaker()
        self._external_http_client = http_client
        self._owned_client: Optional[httpx.AsyncClient] = None
        self._call_logger = call_logger

    # ------------------------------------------------------------------
    # Life-cycle (HIGH-1 fix: AsyncClient 재사용으로 커넥션 풀 누수 방지)
    # ------------------------------------------------------------------

    async def aclose(self) -> None:
        """내부 소유 AsyncClient를 정리. 외부 주입 client는 호출자가 관리."""
        if self._owned_client is not None:
            await self._owned_client.aclose()
            self._owned_client = None

    async def __aenter__(self) -> "DataGoKrClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # HIGH-2 fix: api_key 마스킹 헬퍼
    # ------------------------------------------------------------------

    def _sanitize(self, text: str) -> str:
        """예외 메시지·로그로 유출될 수 있는 serviceKey 값을 마스킹."""
        if not text or not self.api_key:
            return text
        return text.replace(self.api_key, "***")

    # ------------------------------------------------------------------
    # 공개 메서드 (Day 0 시그니처 유지)
    # ------------------------------------------------------------------

    async def get_food_raw_material(
        self, name: str
    ) -> dict[str, Any]:
        """15111913 FoodRwmtInfo — 식품 원재료 정보 + GMO 플래그 조회.

        Step B(GMO 확인)·Step A(금지원료 교차 확인)에서 사용.
        반환: `{"items": [RawMaterialInfo...], "total_count": int, "raw": {...}}`
        """
        endpoint = get_endpoint(DataGoKrEndpoint.FOOD_RAW_MATERIAL)
        return await self._lookup(
            endpoint,
            search_value=name,
            model_cls=RawMaterialInfo,
        )

    async def get_import_food_ingredient(
        self, name: str
    ) -> dict[str, Any]:
        """15111777 IprtFoodIngdInfoService — 수입식품 원료 허용여부·조건 조회.

        Step B(원재료 매칭) 기본 경로. `EDIBLE_INFO`, `CHRTR_INFO_CONT` 반환.
        """
        endpoint = get_endpoint(DataGoKrEndpoint.IMPORT_FOOD_INGREDIENT)
        return await self._lookup(
            endpoint,
            search_value=name,
            model_cls=IngredientInfo,
        )

    async def get_additive_standard(
        self, name: str
    ) -> dict[str, Any]:
        """15116583 FoodWStndStusService — 식품첨가물 기준규격 조회.

        Step C(기준규격 평가)에서 `T_KOR_NM`별 함량/성상/순도 기준 수집.
        """
        endpoint = get_endpoint(DataGoKrEndpoint.ADDITIVE_STANDARD)
        return await self._lookup(
            endpoint,
            search_value=name,
            model_cls=AdditiveSpec,
        )

    async def get_import_food_component(
        self, name: str
    ) -> dict[str, Any]:
        """15094202 IprtFoodCpntCdInfoFoodService — 수입식품 성분코드 조회.

        Step B(성분코드 보강). 한/영/이명 → `CPNT_CD` 1건 매칭.
        `KOR_NM` 앞 공백은 자동 strip.
        """
        endpoint = get_endpoint(DataGoKrEndpoint.IMPORT_FOOD_COMPONENT)
        result = await self._lookup(
            endpoint,
            search_value=name,
            model_cls=ComponentInfo,
        )
        # KOR_NM 앞 공백 strip (탐색보고서 §2-2 주의사항)
        for item in result.get("items", []):
            if isinstance(item, dict) and isinstance(item.get("KOR_NM"), str):
                item["KOR_NM"] = item["KOR_NM"].strip()
            else:
                kor = getattr(item, "kor_nm", None)
                if isinstance(kor, str):
                    item.kor_nm = kor.strip()
        return result

    # ------------------------------------------------------------------
    # 내부 공통 핵심: call → lookup
    # ------------------------------------------------------------------

    async def call(
        self,
        endpoint: DataGoKrEndpoint | Endpoint,
        params: Optional[Dict[str, Any]] = None,
        *,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """공통 호출 — 캐시 확인 → HTTP GET → 재시도 → 파싱 → 캐시 저장.

        Args:
            endpoint: `DataGoKrEndpoint` Enum 또는 `Endpoint` dataclass.
            params: 엔드포인트별 search 파라미터 (serviceKey·type 은 자동 주입).
            use_cache: False 면 캐시 SKIP (강제 새로 조회).

        Returns:
            raw response body (dict). `response.body.items` 를 `items` 로 평탄화.
        """
        ep = endpoint if isinstance(endpoint, Endpoint) else get_endpoint(endpoint)
        request_params: Dict[str, Any] = {**ep.default_params, **(params or {})}

        cache_key = build_cache_key(ep.id, request_params)

        # 1. 캐시 HIT
        if use_cache:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                await self._log_call(
                    endpoint_id=ep.id,
                    cache_hit=True,
                    status_code=None,
                    duration_ms=0,
                )
                return cached

        # 2. Circuit Breaker check
        self._breaker.allow(ep.id)

        # 3. HTTP call (재시도 포함)
        start = time.perf_counter()
        try:
            body = await self._http_call_with_retry(ep, request_params)
        except DataGoKrError as exc:
            # 실패도 호출 로그에 기록
            duration_ms = int((time.perf_counter() - start) * 1000)
            await self._log_call(
                endpoint_id=ep.id,
                cache_hit=False,
                status_code=exc.status_code,
                duration_ms=duration_ms,
            )
            self._breaker.record_failure(ep.id)
            raise

        duration_ms = int((time.perf_counter() - start) * 1000)
        self._breaker.record_success(ep.id)

        # 4. 캐시 저장
        if use_cache:
            await self._cache.put(
                cache_key,
                endpoint_id=ep.id,
                request_params=request_params,
                response_body=body,
                ttl_seconds=ep.cache_ttl_seconds,
            )

        await self._log_call(
            endpoint_id=ep.id,
            cache_hit=False,
            status_code=200,
            duration_ms=duration_ms,
        )
        return body

    async def _lookup(
        self,
        endpoint: Endpoint,
        *,
        search_value: str,
        model_cls: type,
    ) -> Dict[str, Any]:
        """search_param 이 세팅된 단순 조회. 응답을 `items` list 로 평탄화.

        각 item 은 raw dict 와 model 인스턴스의 하이브리드로 저장되지 않고, raw dict
        만 반환한다 (caller 가 `model_cls.model_validate(item)` 로 변환).
        """
        params: Dict[str, Any] = {}
        if endpoint.search_param and search_value:
            params[endpoint.search_param] = search_value
        body = await self.call(endpoint, params)
        items = self._extract_items(body)
        total_count = self._extract_total_count(body)
        # 모델 검증 — 스키마 위반 있으면 DataGoKrInvalidResponseError
        validated: List[Dict[str, Any]] = []
        for item in items:
            try:
                model_cls.model_validate(item)
            except Exception as exc:
                raise DataGoKrInvalidResponseError(
                    f"Response item schema mismatch for {endpoint.id}: {exc}",
                    endpoint=endpoint.id,
                ) from exc
            validated.append(item)
        return {"items": validated, "total_count": total_count, "raw": body}

    # ------------------------------------------------------------------
    # HTTP + 재시도
    # ------------------------------------------------------------------

    async def _http_call_with_retry(
        self,
        endpoint: Endpoint,
        request_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """재시도 정책 포함 HTTP GET.

        data.go.kr 공식 파라미터 이름은 `serviceKey` (인코딩은 httpx 자동처리).
        """
        full_params = {"serviceKey": self.api_key, **request_params}

        attempt = 0
        last_exc: Optional[BaseException] = None
        while attempt <= self.max_retries:
            try:
                return await self._do_http_get(endpoint, full_params)
            except DataGoKrRateLimitError as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise
                backoff = self._pick_backoff(_RETRY_BACKOFF_429, attempt)
                # Retry-After 헤더 우선
                if exc.retry_after and exc.retry_after > 0:
                    backoff = float(exc.retry_after)
                logger.warning(
                    "data.go.kr 429 — backoff %.2fs (attempt %d/%d) endpoint=%s",
                    backoff,
                    attempt + 1,
                    self.max_retries,
                    endpoint.id,
                )
                await asyncio.sleep(backoff)
            except DataGoKrError as exc:
                last_exc = exc
                # transient 하지 않은 에러(Invalid response·4xx 등)는 즉시 raise
                if not exc.transient:
                    raise
                if attempt >= self.max_retries:
                    raise
                backoff = self._pick_backoff(_RETRY_BACKOFF_5XX, attempt)
                logger.warning(
                    "data.go.kr %s — backoff %.2fs (attempt %d/%d) endpoint=%s",
                    exc.code,
                    backoff,
                    attempt + 1,
                    self.max_retries,
                    endpoint.id,
                )
                await asyncio.sleep(backoff)
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise DataGoKrTimeoutError(
                        f"timeout after {self.max_retries + 1} attempts: "
                        f"{self._sanitize(str(exc))}",
                        endpoint=endpoint.id,
                        timeout_s=self.timeout_s,
                    ) from exc
                await asyncio.sleep(_RETRY_BACKOFF_NETWORK)
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise DataGoKrError(
                        f"network error after {self.max_retries + 1} attempts: "
                        f"{self._sanitize(str(exc))}",
                        endpoint=endpoint.id,
                    ) from exc
                await asyncio.sleep(_RETRY_BACKOFF_NETWORK)
            attempt += 1

        # 정상 루프에서 여기로 올 일은 없음 (안전망)
        if isinstance(last_exc, DataGoKrError):
            raise last_exc
        raise DataGoKrError(
            f"Exhausted retries on {endpoint.id}",
            endpoint=endpoint.id,
        )

    async def _do_http_get(
        self,
        endpoint: Endpoint,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """단일 HTTP GET. 응답 상태·resultCode 검증 후 dict 반환.

        HIGH-1 fix: 외부 주입 client가 없으면 `self._owned_client` 를 1회 생성하여
        재사용 — 매 호출마다 새 AsyncClient 생성하던 커넥션 풀 누수 방지.
        """
        client = self._external_http_client
        if client is None:
            if self._owned_client is None:
                self._owned_client = httpx.AsyncClient(timeout=self.timeout_s)
            client = self._owned_client

        resp = await client.get(endpoint.url, params=params)

        status = resp.status_code
        if status == 429:
            retry_after_raw = resp.headers.get("Retry-After")
            retry_after: Optional[int]
            try:
                retry_after = int(retry_after_raw) if retry_after_raw else None
            except ValueError:
                retry_after = None
            raise DataGoKrRateLimitError(
                "data.go.kr rate limit exceeded",
                endpoint=endpoint.id,
                retry_after=retry_after,
            )
        if status in (500, 502, 503, 504):
            raise DataGoKrError(
                f"data.go.kr upstream {status}",
                endpoint=endpoint.id,
                status_code=status,
            )
        if status == 404:
            raise DataGoKrInvalidResponseError(
                f"endpoint not found (404): {endpoint.url}",
                endpoint=endpoint.id,
                status_code=404,
            )
        if status >= 400:
            # HIGH-2 fix: 응답 본문에 serviceKey 가 echo 될 가능성 차단
            raise DataGoKrError(
                f"data.go.kr HTTP {status}: {self._sanitize(resp.text[:200])}",
                endpoint=endpoint.id,
                status_code=status,
            )

        # 2xx — JSON 파싱
        try:
            body = resp.json()
        except Exception as exc:
            raise DataGoKrInvalidResponseError(
                f"JSON decode failed: {self._sanitize(str(exc))}",
                endpoint=endpoint.id,
                status_code=status,
            ) from exc

        result_code = self._extract_result_code(body)
        if result_code not in ("00", "0", None):
            # None 허용 — 일부 엔드포인트는 header 누락 가능. "00"/"0" 외는 에러
            raise DataGoKrInvalidResponseError(
                f"resultCode={result_code}: {self._extract_result_msg(body)}",
                endpoint=endpoint.id,
                result_code=str(result_code) if result_code is not None else None,
                status_code=status,
            )
        return body

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pick_backoff(table: List[float], attempt: int) -> float:
        base = table[min(attempt, len(table) - 1)]
        return base + random.uniform(0, _MAX_JITTER_S)

    @staticmethod
    def _extract_result_code(body: Dict[str, Any]) -> Optional[str]:
        """`response.header.resultCode` 추출. 없으면 None."""
        if not isinstance(body, dict):
            return None
        # 표준 구조
        header = (
            body.get("response", {}).get("header")
            if isinstance(body.get("response"), dict)
            else None
        )
        if isinstance(header, dict) and header.get("resultCode") is not None:
            return str(header.get("resultCode"))
        # 일부 엔드포인트는 최상위 resultCode 반환
        if "resultCode" in body:
            return str(body["resultCode"])
        return None

    @staticmethod
    def _extract_result_msg(body: Dict[str, Any]) -> str:
        if not isinstance(body, dict):
            return ""
        header = (
            body.get("response", {}).get("header")
            if isinstance(body.get("response"), dict)
            else None
        )
        if isinstance(header, dict):
            return str(header.get("resultMsg", ""))
        return str(body.get("resultMsg", ""))

    @staticmethod
    def _extract_items(body: Dict[str, Any]) -> List[Dict[str, Any]]:
        """`response.body.items` 를 list[dict] 로 평탄화.

        data.go.kr 는 items 가 `[]`·`None`·`{"item": [...]}`·`{"item": {...}}` 등
        다양하게 직렬화되므로 방어적으로 처리.
        """
        if not isinstance(body, dict):
            return []
        body_dict = (
            body.get("response", {}).get("body")
            if isinstance(body.get("response"), dict)
            else body.get("body")
        )
        if not isinstance(body_dict, dict):
            return []
        items = body_dict.get("items")
        if items is None or items == "":
            return []
        if isinstance(items, list):
            return [x for x in items if isinstance(x, dict)]
        if isinstance(items, dict):
            item = items.get("item")
            if item is None:
                return []
            if isinstance(item, list):
                return [x for x in item if isinstance(x, dict)]
            if isinstance(item, dict):
                return [item]
        return []

    @staticmethod
    def _extract_total_count(body: Dict[str, Any]) -> int:
        if not isinstance(body, dict):
            return 0
        body_dict = (
            body.get("response", {}).get("body")
            if isinstance(body.get("response"), dict)
            else body.get("body")
        )
        if isinstance(body_dict, dict):
            raw = body_dict.get("totalCount")
            try:
                return int(raw) if raw is not None else 0
            except (ValueError, TypeError):
                return 0
        return 0

    async def _log_call(
        self,
        *,
        endpoint_id: str,
        cache_hit: bool,
        status_code: Optional[int],
        duration_ms: int,
    ) -> None:
        if self._call_logger is None:
            return
        try:
            await self._call_logger.record(
                endpoint_id=endpoint_id,
                cache_hit=cache_hit,
                status_code=status_code,
                duration_ms=duration_ms,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("call logger failed: %s", exc)


# ---------------------------------------------------------------------------
# CallLogger — f1_data_go_kr_call_log 기록 (선택적 주입)
# ---------------------------------------------------------------------------


class CallLogger:
    """Supabase `f1_data_go_kr_call_log` 기록기. 생성자에 client 주입 가능."""

    TABLE = "f1_data_go_kr_call_log"

    def __init__(self, client: Optional[Any] = None) -> None:
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        from db.supabase_client import get_supabase

        self._client = get_supabase()
        return self._client

    async def record(
        self,
        *,
        endpoint_id: str,
        cache_hit: bool,
        status_code: Optional[int],
        duration_ms: int,
        case_id: Optional[str] = None,
    ) -> None:
        def _insert() -> None:
            client = self._get_client()
            try:
                (
                    client.table(self.TABLE)
                    .insert(
                        {
                            "endpoint_id": endpoint_id,
                            "cache_hit": cache_hit,
                            "status_code": status_code,
                            "duration_ms": duration_ms,
                            "case_id": case_id,
                        }
                    )
                    .execute()
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("call_log insert failed: %s", exc)

        await asyncio.to_thread(_insert)


__all__ = ["DataGoKrClient", "CallLogger"]
