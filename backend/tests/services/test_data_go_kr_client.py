"""W1-A DataGoKrClient 단위 테스트.

목표:
    - 4 엔드포인트 각각 mock 응답 → 정상 파싱
    - 캐시 HIT/MISS 분기
    - 429 → backoff → 재시도 성공
    - resultCode != "00" → DataGoKrInvalidResponseError
    - 5xx → DataGoKrError(transient=True), max_retries 초과 시 raise
    - Circuit Breaker OPEN → CircuitBreakerOpenError
    - KOR_NM 앞 공백 strip
    - ComponentInfo 모델 검증

실행:
    cd backend
    pytest tests/services/test_data_go_kr_client.py -v
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from exceptions import (
    CircuitBreakerOpenError,
    DataGoKrError,
    DataGoKrInvalidResponseError,
    DataGoKrRateLimitError,
    DataGoKrTimeoutError,
)
from models.f1_types import DataGoKrEndpoint
from services.data_go_kr import (
    AdditiveSpec,
    ComponentInfo,
    DataGoKrClient,
    ENDPOINTS,
    Endpoint,
    FOOD_RAW_MATERIAL,
    IMPORT_FOOD_COMPONENT,
    IMPORT_FOOD_INGREDIENT,
    ADDITIVE_STANDARD,
    InMemoryResponseCache,
    IngredientInfo,
    NoOpBreaker,
    RawMaterialInfo,
    build_cache_key,
    get_endpoint,
)
from services.data_go_kr.circuit_breaker import CircuitBreakerLike


# ============================================================
# 공통 픽스처
# ============================================================

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "data_go_kr"


def load_fixture(filename: str) -> Dict[str, Any]:
    path = FIXTURES_DIR / filename
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def api_key() -> str:
    return "test-api-key-dummy"


@pytest.fixture
def cache() -> InMemoryResponseCache:
    return InMemoryResponseCache()


@pytest.fixture
def client(api_key: str, cache: InMemoryResponseCache) -> DataGoKrClient:
    # 테스트 속도 위해 max_retries=1, timeout 짧게
    return DataGoKrClient(
        api_key=api_key,
        timeout_s=2.0,
        max_retries=2,
        cache=cache,
        breaker=NoOpBreaker(),
    )


# ============================================================
# 엔드포인트 정의 검증
# ============================================================


class TestEndpoints:
    def test_four_endpoints_present(self) -> None:
        assert set(ENDPOINTS.keys()) == {
            DataGoKrEndpoint.FOOD_RAW_MATERIAL,
            DataGoKrEndpoint.IMPORT_FOOD_INGREDIENT,
            DataGoKrEndpoint.ADDITIVE_STANDARD,
            DataGoKrEndpoint.IMPORT_FOOD_COMPONENT,
        }

    def test_ids_match_spec(self) -> None:
        assert FOOD_RAW_MATERIAL.id == "15111913"
        assert IMPORT_FOOD_INGREDIENT.id == "15111777"
        assert ADDITIVE_STANDARD.id == "15116583"
        assert IMPORT_FOOD_COMPONENT.id == "15094202"

    def test_additive_has_longer_ttl(self) -> None:
        # 06 §6 — 15116583 만 7일
        assert ADDITIVE_STANDARD.cache_ttl_seconds == 7 * 24 * 60 * 60
        assert FOOD_RAW_MATERIAL.cache_ttl_seconds == 24 * 60 * 60

    def test_get_endpoint_by_enum(self) -> None:
        ep = get_endpoint(DataGoKrEndpoint.ADDITIVE_STANDARD)
        assert ep.id == "15116583"


# ============================================================
# 캐시 키 생성
# ============================================================


class TestCacheKey:
    def test_deterministic(self) -> None:
        k1 = build_cache_key("15111777", {"INGD_NM": "대두", "type": "json"})
        k2 = build_cache_key("15111777", {"type": "json", "INGD_NM": "대두"})
        assert k1 == k2  # 키 순서 독립

    def test_different_params_different_key(self) -> None:
        k1 = build_cache_key("15111777", {"INGD_NM": "대두"})
        k2 = build_cache_key("15111777", {"INGD_NM": "옥수수"})
        assert k1 != k2

    def test_different_endpoint_different_key(self) -> None:
        k1 = build_cache_key("15111777", {"name": "x"})
        k2 = build_cache_key("15111913", {"name": "x"})
        assert k1 != k2


# ============================================================
# InMemoryResponseCache
# ============================================================


@pytest.mark.asyncio
class TestInMemoryCache:
    async def test_put_get_roundtrip(self) -> None:
        cache = InMemoryResponseCache()
        await cache.put(
            "k1",
            endpoint_id="15111777",
            request_params={"INGD_NM": "대두"},
            response_body={"response": {"body": {"items": []}}},
            ttl_seconds=60,
        )
        got = await cache.get("k1")
        assert got == {"response": {"body": {"items": []}}}

    async def test_miss_returns_none(self) -> None:
        cache = InMemoryResponseCache()
        assert await cache.get("missing") is None

    async def test_expired_returns_none(self) -> None:
        cache = InMemoryResponseCache()
        await cache.put(
            "k1",
            endpoint_id="15111777",
            request_params={},
            response_body={"a": 1},
            ttl_seconds=-1,  # 이미 만료
        )
        assert await cache.get("k1") is None

    async def test_invalidate_specific_key(self) -> None:
        cache = InMemoryResponseCache()
        await cache.put("k1", endpoint_id="15111777", request_params={}, response_body={}, ttl_seconds=60)
        await cache.put("k2", endpoint_id="15111777", request_params={}, response_body={}, ttl_seconds=60)
        deleted = await cache.invalidate("k1")
        assert deleted == 1
        assert await cache.get("k1") is None
        assert await cache.get("k2") is not None

    async def test_invalidate_all(self) -> None:
        cache = InMemoryResponseCache()
        await cache.put("k1", endpoint_id="15111777", request_params={}, response_body={}, ttl_seconds=60)
        await cache.put("k2", endpoint_id="15111777", request_params={}, response_body={}, ttl_seconds=60)
        deleted = await cache.invalidate()
        assert deleted == 2


# ============================================================
# Client 생성자 검증
# ============================================================


class TestClientConstructor:
    def test_missing_api_key_raises(self) -> None:
        with pytest.raises(ValueError):
            DataGoKrClient(api_key="")

    def test_defaults(self) -> None:
        c = DataGoKrClient(api_key="x")
        assert c.timeout_s == 15.0
        assert c.max_retries == 3

    def test_kwargs(self) -> None:
        c = DataGoKrClient(api_key="x", timeout_s=5.0, max_retries=7)
        assert c.timeout_s == 5.0
        assert c.max_retries == 7


# ============================================================
# 4 엔드포인트 mock 응답
# ============================================================


@pytest.mark.asyncio
class TestEndpointCalls:
    async def test_get_food_raw_material_soybean(self, client: DataGoKrClient) -> None:
        fixture = load_fixture("15111913_soybean.json")
        with respx.mock(assert_all_called=False) as rx:
            rx.get(FOOD_RAW_MATERIAL.url).mock(
                return_value=httpx.Response(200, json=fixture)
            )
            result = await client.get_food_raw_material("대두")
        assert result["total_count"] == 2
        assert len(result["items"]) == 2
        first = RawMaterialInfo.model_validate(result["items"][0])
        assert first.orm_std_nm == "대두"
        assert first.gmo_yn == "Y"
        second = RawMaterialInfo.model_validate(result["items"][1])
        assert second.gmo_yn == "N"

    async def test_get_import_food_ingredient(self, client: DataGoKrClient) -> None:
        fixture = load_fixture("15111777_garicrestle.json")
        with respx.mock(assert_all_called=False) as rx:
            rx.get(IMPORT_FOOD_INGREDIENT.url).mock(
                return_value=httpx.Response(200, json=fixture)
            )
            result = await client.get_import_food_ingredient("가는가래")
        assert result["total_count"] == 1
        info = IngredientInfo.model_validate(result["items"][0])
        assert info.ingd_nm == "가는가래"
        assert info.edible_info == "가능"
        assert info.chrtr_info_cont is None

    async def test_get_import_food_component_strips_kor_nm(
        self, client: DataGoKrClient
    ) -> None:
        fixture = load_fixture("15094202_chicken.json")
        with respx.mock(assert_all_called=False) as rx:
            rx.get(IMPORT_FOOD_COMPONENT.url).mock(
                return_value=httpx.Response(200, json=fixture)
            )
            result = await client.get_import_food_component("닭고기단백분말")
        item = result["items"][0]
        # 탐색보고서 §2-2 — KOR_NM 앞 공백 제거 필수
        assert item["KOR_NM"] == "닭고기단백분말"
        info = ComponentInfo.model_validate(item)
        assert info.cpnt_cd == "A2000049070045"

    async def test_get_additive_standard(self, client: DataGoKrClient) -> None:
        fixture = load_fixture("15116583_geramyl.json")
        with respx.mock(assert_all_called=False) as rx:
            rx.get(ADDITIVE_STANDARD.url).mock(
                return_value=httpx.Response(200, json=fixture)
            )
            result = await client.get_additive_standard("개미산게라닐")
        assert result["total_count"] == 4
        # T_KOR_NM 4종 분리 — 07 §2-4 기대
        categories = {
            AdditiveSpec.model_validate(it).t_kor_nm for it in result["items"]
        }
        assert categories == {"함량", "성상", "순도시험", "확인시험"}


# ============================================================
# 캐시 동작
# ============================================================


@pytest.mark.asyncio
class TestCaching:
    async def test_second_call_hits_cache(
        self, client: DataGoKrClient
    ) -> None:
        fixture = load_fixture("15111777_garicrestle.json")
        with respx.mock(assert_all_called=False) as rx:
            route = rx.get(IMPORT_FOOD_INGREDIENT.url).mock(
                return_value=httpx.Response(200, json=fixture)
            )
            await client.get_import_food_ingredient("가는가래")
            await client.get_import_food_ingredient("가는가래")
            await client.get_import_food_ingredient("가는가래")
        assert route.call_count == 1  # 나머지는 캐시 HIT

    async def test_different_names_bypass_cache(
        self, client: DataGoKrClient
    ) -> None:
        fixture = load_fixture("15111913_soybean.json")
        with respx.mock(assert_all_called=False) as rx:
            route = rx.get(FOOD_RAW_MATERIAL.url).mock(
                return_value=httpx.Response(200, json=fixture)
            )
            await client.get_food_raw_material("대두")
            await client.get_food_raw_material("옥수수")
        assert route.call_count == 2

    async def test_use_cache_false_bypasses(
        self, client: DataGoKrClient
    ) -> None:
        fixture = load_fixture("15111777_garicrestle.json")
        with respx.mock(assert_all_called=False) as rx:
            route = rx.get(IMPORT_FOOD_INGREDIENT.url).mock(
                return_value=httpx.Response(200, json=fixture)
            )
            await client.call(
                DataGoKrEndpoint.IMPORT_FOOD_INGREDIENT,
                {"INGD_NM": "가는가래"},
            )
            await client.call(
                DataGoKrEndpoint.IMPORT_FOOD_INGREDIENT,
                {"INGD_NM": "가는가래"},
                use_cache=False,
            )
        assert route.call_count == 2


# ============================================================
# 에러 매핑
# ============================================================


@pytest.mark.asyncio
class TestErrorMapping:
    async def test_invalid_result_code(self, client: DataGoKrClient) -> None:
        err_fixture = load_fixture("error_invalid_key.json")
        with respx.mock(assert_all_called=False) as rx:
            rx.get(IMPORT_FOOD_INGREDIENT.url).mock(
                return_value=httpx.Response(200, json=err_fixture)
            )
            with pytest.raises(DataGoKrInvalidResponseError) as exc:
                await client.get_import_food_ingredient("가는가래")
        assert exc.value.endpoint == "15111777"
        assert exc.value.result_code == "30"

    async def test_rate_limit_raises_after_retries_exhausted(
        self, client: DataGoKrClient
    ) -> None:
        with respx.mock(assert_all_called=False) as rx:
            # client 는 max_retries=2 → 총 3회(1 + 2 재시도)
            rx.get(FOOD_RAW_MATERIAL.url).mock(
                return_value=httpx.Response(
                    429, headers={"Retry-After": "0"}, json={}
                )
            )
            with pytest.raises(DataGoKrRateLimitError) as exc:
                await client.get_food_raw_material("대두")
        assert exc.value.status_code == 429
        assert exc.value.retry_after == 0

    async def test_rate_limit_then_success_retries(
        self, api_key: str, cache: InMemoryResponseCache
    ) -> None:
        # Retry-After: 0 이면 즉시 재시도
        fixture = load_fixture("15111913_soybean.json")
        responses = [
            httpx.Response(429, headers={"Retry-After": "0"}, json={}),
            httpx.Response(200, json=fixture),
        ]
        client = DataGoKrClient(
            api_key=api_key,
            timeout_s=2.0,
            max_retries=2,
            cache=cache,
            breaker=NoOpBreaker(),
        )
        with respx.mock(assert_all_called=False) as rx:
            route = rx.get(FOOD_RAW_MATERIAL.url).mock(side_effect=responses)
            result = await client.get_food_raw_material("대두")
        assert route.call_count == 2
        assert result["total_count"] == 2

    async def test_500_retries_then_succeeds(
        self, api_key: str, cache: InMemoryResponseCache
    ) -> None:
        fixture = load_fixture("15111777_garicrestle.json")
        responses = [
            httpx.Response(500, json={}),
            httpx.Response(503, json={}),
            httpx.Response(200, json=fixture),
        ]
        client = DataGoKrClient(
            api_key=api_key,
            timeout_s=2.0,
            max_retries=3,
            cache=cache,
            breaker=NoOpBreaker(),
        )
        with respx.mock(assert_all_called=False) as rx:
            route = rx.get(IMPORT_FOOD_INGREDIENT.url).mock(side_effect=responses)
            # 테스트 속도를 위해 sleep monkeypatch
            import services.data_go_kr.client as client_mod

            orig_sleep = asyncio.sleep

            async def _fast(_s: float) -> None:
                await orig_sleep(0)

            client_mod.asyncio.sleep = _fast  # type: ignore[attr-defined]
            try:
                result = await client.get_import_food_ingredient("가는가래")
            finally:
                client_mod.asyncio.sleep = orig_sleep  # type: ignore[attr-defined]
        assert route.call_count == 3
        assert result["total_count"] == 1

    async def test_500_exhausts_retries_raises_transient(
        self, api_key: str, cache: InMemoryResponseCache
    ) -> None:
        client = DataGoKrClient(
            api_key=api_key,
            timeout_s=2.0,
            max_retries=1,
            cache=cache,
            breaker=NoOpBreaker(),
        )
        with respx.mock(assert_all_called=False) as rx:
            rx.get(IMPORT_FOOD_INGREDIENT.url).mock(
                return_value=httpx.Response(503, json={})
            )
            import services.data_go_kr.client as client_mod

            client_mod.asyncio.sleep = AsyncMock(return_value=None)  # type: ignore[attr-defined]
            try:
                with pytest.raises(DataGoKrError) as exc:
                    await client.get_import_food_ingredient("가는가래")
            finally:
                # Reset
                client_mod.asyncio.sleep = asyncio.sleep  # type: ignore[attr-defined]
        assert exc.value.status_code == 503
        assert exc.value.transient is True

    async def test_404_raises_invalid_response(
        self, client: DataGoKrClient
    ) -> None:
        with respx.mock(assert_all_called=False) as rx:
            rx.get(IMPORT_FOOD_INGREDIENT.url).mock(
                return_value=httpx.Response(404, text="not found")
            )
            with pytest.raises(DataGoKrInvalidResponseError) as exc:
                await client.get_import_food_ingredient("x")
        assert exc.value.status_code == 404

    async def test_timeout_raises_timeout_error(
        self, api_key: str, cache: InMemoryResponseCache
    ) -> None:
        client = DataGoKrClient(
            api_key=api_key,
            timeout_s=0.5,
            max_retries=1,
            cache=cache,
            breaker=NoOpBreaker(),
        )
        with respx.mock(assert_all_called=False) as rx:
            rx.get(FOOD_RAW_MATERIAL.url).mock(
                side_effect=httpx.TimeoutException("timed out")
            )
            import services.data_go_kr.client as client_mod

            client_mod.asyncio.sleep = AsyncMock(return_value=None)  # type: ignore[attr-defined]
            try:
                with pytest.raises(DataGoKrTimeoutError) as exc:
                    await client.get_food_raw_material("대두")
            finally:
                client_mod.asyncio.sleep = asyncio.sleep  # type: ignore[attr-defined]
        assert exc.value.endpoint == "15111913"
        assert exc.value.timeout_s == 0.5


# ============================================================
# Circuit Breaker 통합
# ============================================================


class _AlwaysOpenBreaker:
    """`allow` 에서 바로 CircuitBreakerOpenError raise 하는 테스트용 breaker."""

    def allow(self, endpoint: str) -> None:
        raise CircuitBreakerOpenError(
            f"forced open for {endpoint}", endpoint=endpoint
        )

    def record_success(self, endpoint: str) -> None:
        pass

    def record_failure(self, endpoint: str) -> None:
        pass


class _CountingBreaker:
    """성공·실패 카운터만 기록."""

    def __init__(self) -> None:
        self.success = 0
        self.failure = 0
        self.allowed = 0

    def allow(self, endpoint: str) -> None:  # noqa: ARG002
        self.allowed += 1

    def record_success(self, endpoint: str) -> None:  # noqa: ARG002
        self.success += 1

    def record_failure(self, endpoint: str) -> None:  # noqa: ARG002
        self.failure += 1


@pytest.mark.asyncio
class TestCircuitBreakerIntegration:
    async def test_open_breaker_blocks_call(
        self, api_key: str, cache: InMemoryResponseCache
    ) -> None:
        client = DataGoKrClient(
            api_key=api_key,
            cache=cache,
            breaker=_AlwaysOpenBreaker(),
        )
        with respx.mock(assert_all_called=False):  # no HTTP expected
            with pytest.raises(CircuitBreakerOpenError):
                await client.get_food_raw_material("대두")

    async def test_success_records_success(
        self, api_key: str, cache: InMemoryResponseCache
    ) -> None:
        fixture = load_fixture("15111913_soybean.json")
        breaker = _CountingBreaker()
        client = DataGoKrClient(
            api_key=api_key,
            cache=cache,
            breaker=breaker,
        )
        with respx.mock(assert_all_called=False) as rx:
            rx.get(FOOD_RAW_MATERIAL.url).mock(
                return_value=httpx.Response(200, json=fixture)
            )
            await client.get_food_raw_material("대두")
        assert breaker.allowed == 1
        assert breaker.success == 1
        assert breaker.failure == 0

    async def test_failure_records_failure(
        self, api_key: str, cache: InMemoryResponseCache
    ) -> None:
        breaker = _CountingBreaker()
        client = DataGoKrClient(
            api_key=api_key,
            cache=cache,
            breaker=breaker,
            max_retries=1,
        )
        with respx.mock(assert_all_called=False) as rx:
            rx.get(IMPORT_FOOD_INGREDIENT.url).mock(
                return_value=httpx.Response(500, json={})
            )
            import services.data_go_kr.client as client_mod

            client_mod.asyncio.sleep = AsyncMock(return_value=None)  # type: ignore[attr-defined]
            try:
                with pytest.raises(DataGoKrError):
                    await client.get_import_food_ingredient("x")
            finally:
                client_mod.asyncio.sleep = asyncio.sleep  # type: ignore[attr-defined]
        assert breaker.failure == 1
        assert breaker.success == 0


# ============================================================
# Response parsing edge cases
# ============================================================


@pytest.mark.asyncio
class TestResponseParsing:
    async def test_empty_items_list(self, client: DataGoKrClient) -> None:
        empty = {
            "response": {
                "header": {"resultCode": "00", "resultMsg": "OK"},
                "body": {"pageNo": 1, "numOfRows": 10, "totalCount": 0, "items": []},
            }
        }
        with respx.mock(assert_all_called=False) as rx:
            rx.get(FOOD_RAW_MATERIAL.url).mock(
                return_value=httpx.Response(200, json=empty)
            )
            result = await client.get_food_raw_material("없는원재료")
        assert result["items"] == []
        assert result["total_count"] == 0

    async def test_items_as_dict_wrapper(self, client: DataGoKrClient) -> None:
        # 일부 엔드포인트는 items = {"item": [...]} 구조
        wrapped = {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "totalCount": 1,
                    "items": {
                        "item": [{"ORM_STD_NM": "대두", "GMO_YN": "Y"}]
                    },
                },
            }
        }
        with respx.mock(assert_all_called=False) as rx:
            rx.get(FOOD_RAW_MATERIAL.url).mock(
                return_value=httpx.Response(200, json=wrapped)
            )
            result = await client.get_food_raw_material("대두")
        assert len(result["items"]) == 1
        assert result["items"][0]["ORM_STD_NM"] == "대두"

    async def test_items_as_single_item_dict(
        self, client: DataGoKrClient
    ) -> None:
        single = {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "totalCount": 1,
                    "items": {"item": {"ORM_STD_NM": "대두", "GMO_YN": "Y"}},
                },
            }
        }
        with respx.mock(assert_all_called=False) as rx:
            rx.get(FOOD_RAW_MATERIAL.url).mock(
                return_value=httpx.Response(200, json=single)
            )
            result = await client.get_food_raw_material("대두")
        assert len(result["items"]) == 1

    async def test_invalid_json_raises(self, client: DataGoKrClient) -> None:
        with respx.mock(assert_all_called=False) as rx:
            rx.get(IMPORT_FOOD_INGREDIENT.url).mock(
                return_value=httpx.Response(200, text="not json")
            )
            with pytest.raises(DataGoKrInvalidResponseError):
                await client.get_import_food_ingredient("x")

    async def test_400_other_raises_data_go_kr_error(
        self, client: DataGoKrClient
    ) -> None:
        with respx.mock(assert_all_called=False) as rx:
            rx.get(IMPORT_FOOD_INGREDIENT.url).mock(
                return_value=httpx.Response(401, text="unauthorized")
            )
            with pytest.raises(DataGoKrError) as exc:
                await client.get_import_food_ingredient("x")
        assert exc.value.status_code == 401

    async def test_top_level_result_code_detected(
        self, client: DataGoKrClient
    ) -> None:
        # 일부 엔드포인트가 최상위 resultCode 를 반환하는 경우
        body = {"resultCode": "22", "resultMsg": "LIMIT"}
        with respx.mock(assert_all_called=False) as rx:
            rx.get(IMPORT_FOOD_INGREDIENT.url).mock(
                return_value=httpx.Response(200, json=body)
            )
            with pytest.raises(DataGoKrInvalidResponseError) as exc:
                await client.get_import_food_ingredient("x")
        assert exc.value.result_code == "22"

    async def test_result_code_numeric_zero_accepted(
        self, client: DataGoKrClient
    ) -> None:
        # 일부 엔드포인트는 resultCode=0 (int) 반환 가능
        body = {
            "resultCode": 0,
            "response": {
                "header": {"resultCode": "0"},
                "body": {"totalCount": 0, "items": []},
            },
        }
        with respx.mock(assert_all_called=False) as rx:
            rx.get(IMPORT_FOOD_INGREDIENT.url).mock(
                return_value=httpx.Response(200, json=body)
            )
            result = await client.get_import_food_ingredient("x")
        assert result["total_count"] == 0

    async def test_result_msg_fallback_top_level(self) -> None:
        client = DataGoKrClient(api_key="x")
        assert client._extract_result_msg({"resultMsg": "MSG"}) == "MSG"
        assert client._extract_result_msg("not a dict") == ""  # type: ignore[arg-type]

    async def test_extract_items_edge_cases(self) -> None:
        client = DataGoKrClient(api_key="x")
        # 비dict body
        assert client._extract_items("oops") == []  # type: ignore[arg-type]
        # body 필드 자체가 없는 경우
        assert client._extract_items({"response": {}}) == []
        # items=None
        body = {"response": {"body": {"items": None}}}
        assert client._extract_items(body) == []
        # items="" (빈 문자열도 흔함)
        assert client._extract_items({"response": {"body": {"items": ""}}}) == []
        # items={"item": None}
        assert (
            client._extract_items({"response": {"body": {"items": {"item": None}}}})
            == []
        )

    async def test_extract_total_count_edge_cases(self) -> None:
        client = DataGoKrClient(api_key="x")
        assert client._extract_total_count("oops") == 0  # type: ignore[arg-type]
        assert client._extract_total_count({"response": {}}) == 0
        # totalCount string → int 변환
        body = {"response": {"body": {"totalCount": "5"}}}
        assert client._extract_total_count(body) == 5
        # 잘못된 값
        body = {"response": {"body": {"totalCount": "abc"}}}
        assert client._extract_total_count(body) == 0


# ============================================================
# Schema 검증 실패
# ============================================================


@pytest.mark.asyncio
class TestSchemaValidation:
    async def test_missing_required_field_raises_invalid(
        self, client: DataGoKrClient
    ) -> None:
        # RawMaterialInfo 는 ORM_STD_NM 이 필수
        bad = {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "totalCount": 1,
                    "items": [{"GMO_YN": "Y"}],  # ORM_STD_NM 누락
                },
            }
        }
        with respx.mock(assert_all_called=False) as rx:
            rx.get(FOOD_RAW_MATERIAL.url).mock(
                return_value=httpx.Response(200, json=bad)
            )
            with pytest.raises(DataGoKrInvalidResponseError):
                await client.get_food_raw_material("대두")


# ============================================================
# CallLogger
# ============================================================


@pytest.mark.asyncio
class TestCallLogger:
    async def test_logger_called_on_success(
        self, api_key: str, cache: InMemoryResponseCache
    ) -> None:
        fixture = load_fixture("15111913_soybean.json")

        class _Logger:
            def __init__(self) -> None:
                self.records: list[dict[str, Any]] = []

            async def record(self, **kwargs: Any) -> None:
                self.records.append(kwargs)

        logger = _Logger()
        client = DataGoKrClient(
            api_key=api_key,
            cache=cache,
            breaker=NoOpBreaker(),
            call_logger=logger,
        )
        with respx.mock(assert_all_called=False) as rx:
            rx.get(FOOD_RAW_MATERIAL.url).mock(
                return_value=httpx.Response(200, json=fixture)
            )
            await client.get_food_raw_material("대두")
        assert len(logger.records) == 1
        assert logger.records[0]["endpoint_id"] == "15111913"
        assert logger.records[0]["cache_hit"] is False
        assert logger.records[0]["status_code"] == 200

    async def test_logger_records_cache_hit(
        self, api_key: str, cache: InMemoryResponseCache
    ) -> None:
        fixture = load_fixture("15111913_soybean.json")

        class _Logger:
            def __init__(self) -> None:
                self.records: list[dict[str, Any]] = []

            async def record(self, **kwargs: Any) -> None:
                self.records.append(kwargs)

        logger = _Logger()
        client = DataGoKrClient(
            api_key=api_key,
            cache=cache,
            breaker=NoOpBreaker(),
            call_logger=logger,
        )
        with respx.mock(assert_all_called=False) as rx:
            rx.get(FOOD_RAW_MATERIAL.url).mock(
                return_value=httpx.Response(200, json=fixture)
            )
            await client.get_food_raw_material("대두")
            await client.get_food_raw_material("대두")  # cache hit
        assert len(logger.records) == 2
        assert logger.records[1]["cache_hit"] is True

    async def test_logger_called_on_failure(
        self, api_key: str, cache: InMemoryResponseCache
    ) -> None:
        class _Logger:
            def __init__(self) -> None:
                self.records: list[dict[str, Any]] = []

            async def record(self, **kwargs: Any) -> None:
                self.records.append(kwargs)

        logger = _Logger()
        client = DataGoKrClient(
            api_key=api_key,
            cache=cache,
            breaker=NoOpBreaker(),
            call_logger=logger,
            max_retries=0,
        )
        with respx.mock(assert_all_called=False) as rx:
            rx.get(IMPORT_FOOD_INGREDIENT.url).mock(
                return_value=httpx.Response(503, json={})
            )
            with pytest.raises(DataGoKrError):
                await client.get_import_food_ingredient("x")
        assert len(logger.records) == 1
        assert logger.records[0]["status_code"] == 503


# ============================================================
# SupabaseResponseCache (모의 client)
# ============================================================


@pytest.mark.asyncio
class TestSupabaseResponseCache:
    async def test_get_hit(self) -> None:
        from services.data_go_kr.cache import SupabaseResponseCache

        class _MockResp:
            def __init__(self, data: list[dict[str, Any]]) -> None:
                self.data = data

        class _MockQuery:
            def __init__(self, resp: _MockResp) -> None:
                self._resp = resp

            def select(self, *_a: Any, **_kw: Any) -> "_MockQuery":
                return self

            def eq(self, *_a: Any, **_kw: Any) -> "_MockQuery":
                return self

            def limit(self, *_a: Any, **_kw: Any) -> "_MockQuery":
                return self

            def execute(self) -> _MockResp:
                return self._resp

        class _MockClient:
            def __init__(self, resp: _MockResp) -> None:
                self._resp = resp

            def table(self, _name: str) -> _MockQuery:
                return _MockQuery(self._resp)

        # 미래 만료 시각
        future = "2999-12-31T00:00:00+00:00"
        rows = [{"response_body": {"a": 1}, "expires_at": future}]
        cache = SupabaseResponseCache(client=_MockClient(_MockResp(rows)))
        got = await cache.get("k1")
        assert got == {"a": 1}

    async def test_get_expired(self) -> None:
        from services.data_go_kr.cache import SupabaseResponseCache

        class _MockResp:
            def __init__(self) -> None:
                self.data = [
                    {
                        "response_body": {"a": 1},
                        "expires_at": "2000-01-01T00:00:00+00:00",
                    }
                ]

        class _MockClient:
            def table(self, _name: str) -> Any:
                class _Q:
                    def select(self, *_a: Any, **_kw: Any) -> "_Q":
                        return self

                    def eq(self, *_a: Any, **_kw: Any) -> "_Q":
                        return self

                    def limit(self, *_a: Any, **_kw: Any) -> "_Q":
                        return self

                    def execute(self) -> _MockResp:
                        return _MockResp()

                return _Q()

        cache = SupabaseResponseCache(client=_MockClient())
        assert await cache.get("k1") is None

    async def test_get_miss(self) -> None:
        from services.data_go_kr.cache import SupabaseResponseCache

        class _EmptyResp:
            data: list[Any] = []

        class _MockClient:
            def table(self, _name: str) -> Any:
                class _Q:
                    def select(self, *_a: Any, **_kw: Any) -> "_Q":
                        return self

                    def eq(self, *_a: Any, **_kw: Any) -> "_Q":
                        return self

                    def limit(self, *_a: Any, **_kw: Any) -> "_Q":
                        return self

                    def execute(self) -> _EmptyResp:
                        return _EmptyResp()

                return _Q()

        cache = SupabaseResponseCache(client=_MockClient())
        assert await cache.get("k1") is None

    async def test_put(self) -> None:
        from services.data_go_kr.cache import SupabaseResponseCache

        captured: dict[str, Any] = {}

        class _Q:
            def upsert(self, payload: dict[str, Any]) -> "_Q":
                captured["payload"] = payload
                return self

            def execute(self) -> Any:
                class _R:
                    data: list[Any] = []
                return _R()

        class _MockClient:
            def table(self, _name: str) -> _Q:
                return _Q()

        cache = SupabaseResponseCache(client=_MockClient())
        await cache.put(
            "k1",
            endpoint_id="15111777",
            request_params={"INGD_NM": "x"},
            response_body={"a": 1},
            ttl_seconds=60,
        )
        payload = captured["payload"]
        assert payload["cache_key"] == "k1"
        assert payload["endpoint_id"] == "15111777"
        assert payload["response_body"] == {"a": 1}

    async def test_invalidate_specific(self) -> None:
        from services.data_go_kr.cache import SupabaseResponseCache

        class _Q:
            def delete(self) -> "_Q":
                return self

            def eq(self, *_a: Any, **_kw: Any) -> "_Q":
                return self

            def neq(self, *_a: Any, **_kw: Any) -> "_Q":
                return self

            def execute(self) -> Any:
                class _R:
                    data = [{"cache_key": "k1"}]
                return _R()

        class _MockClient:
            def table(self, _name: str) -> _Q:
                return _Q()

        cache = SupabaseResponseCache(client=_MockClient())
        assert await cache.invalidate("k1") == 1
        assert await cache.invalidate() == 1  # full wipe path

    async def test_json_string_body_decoded(self) -> None:
        from services.data_go_kr.cache import SupabaseResponseCache

        class _Resp:
            data = [
                {
                    "response_body": '{"a":1}',
                    "expires_at": "2999-12-31T00:00:00+00:00",
                }
            ]

        class _Q:
            def select(self, *_a: Any, **_kw: Any) -> "_Q":
                return self

            def eq(self, *_a: Any, **_kw: Any) -> "_Q":
                return self

            def limit(self, *_a: Any, **_kw: Any) -> "_Q":
                return self

            def execute(self) -> _Resp:
                return _Resp()

        class _MockClient:
            def table(self, _n: str) -> _Q:
                return _Q()

        cache = SupabaseResponseCache(client=_MockClient())
        got = await cache.get("k1")
        assert got == {"a": 1}
