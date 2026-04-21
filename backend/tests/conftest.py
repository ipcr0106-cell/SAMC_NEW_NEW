"""공유 pytest fixture — Wave A Phase 0 산출물.

후속 Phase 에이전트 (α, β, γ, ε, ζ) 가 공통으로 import 하여 사용.

fixture 목록:
    mock_supabase           — supabase-py client mock (.select().eq().execute() 체인)
    fake_data_go_kr_client  — DataGoKrClient mock (응답 데이터 주입 가능)
    fake_law_go_kr_articles — f1_law_articles 샘플 3~5건 리스트
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


# ============================================================
# mock_supabase
# ============================================================


class _SupabaseMockBuilder:
    """select().eq().execute() 체인을 지원하는 fluent mock 빌더."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def _execute_result(self) -> MagicMock:
        result = MagicMock()
        result.data = list(self._rows)
        return result

    def build(self) -> MagicMock:
        execute_mock = MagicMock(side_effect=lambda: self._execute_result())

        # 체인 빌더: 메서드를 호출할 때마다 자신을 반환하고 마지막에 execute() 호출
        builder = MagicMock()
        builder.execute = execute_mock

        # select / eq / neq / limit / order 등 체이너블 메서드 등록
        for method_name in ("select", "eq", "neq", "gte", "lte", "in_", "order", "limit", "single"):
            getattr(builder, method_name).return_value = builder

        client = MagicMock()
        client.table.return_value = builder
        client.rpc.return_value = builder
        return client


@pytest.fixture
def mock_supabase() -> MagicMock:
    """기본 빈 응답(rows=[])을 반환하는 Supabase client mock.

    테스트에서 특정 테이블 응답을 주입하려면:

        mock_supabase.table.return_value.select.return_value.execute.return_value.data = [
            {"name_ko": "아편", "reason": "금지원료"},
        ]
    """
    return _SupabaseMockBuilder(rows=[]).build()


# ============================================================
# fake_data_go_kr_client
# ============================================================


class _FakeDataGoKrClient:
    """DataGoKrClient 경량 mock — 응답 데이터를 딕셔너리로 사전 주입.

    사용 예:
        client = fake_data_go_kr_client
        client.set_response("15094202", [{"IMGRD_NM": "밀가루", ...}])
        result = await client.fetch_ingredient_info("밀가루")
    """

    def __init__(self) -> None:
        self._responses: dict[str, list[dict]] = {}
        self._default: list[dict] = []

    def set_response(self, endpoint_key: str, data: list[dict]) -> None:
        """엔드포인트별 응답을 사전 등록."""
        self._responses[endpoint_key] = data

    def set_default(self, data: list[dict]) -> None:
        """미등록 엔드포인트 기본 응답."""
        self._default = data

    async def fetch_ingredient_info(
        self, ingredient_name: str, endpoint: str = "15094202", **_kwargs: Any
    ) -> list[dict]:
        return self._responses.get(endpoint, self._default)

    async def fetch_additive_info(
        self, ingredient_name: str, **_kwargs: Any
    ) -> list[dict]:
        return self._responses.get("additives", self._default)

    async def __aenter__(self) -> "_FakeDataGoKrClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        pass


@pytest.fixture
def fake_data_go_kr_client() -> _FakeDataGoKrClient:
    """DataGoKrClient mock — 응답 데이터를 테스트마다 주입 가능한 구조.

    사용 예:
        async def test_something(fake_data_go_kr_client):
            fake_data_go_kr_client.set_response("15094202", [
                {"IMGRD_NM": "아편", "EDIBLE_INFO": "불가", ...}
            ])
    """
    return _FakeDataGoKrClient()


# ============================================================
# fake_law_go_kr_articles
# ============================================================


@pytest.fixture
def fake_law_go_kr_articles() -> list[dict]:
    """f1_law_articles 테이블 샘플 데이터 5건.

    필드 구성: id, law_cache_id, article_label, text, namespace (law_name 은 JOIN)
    실제 DB 스키마(020_f1_law_cache.sql)와 컬럼명 일치.
    """
    return [
        {
            "id": 1,
            "law_cache_id": 101,
            "law_name": "식품의 기준 및 규격",
            "article_label": "제2조",
            "text": "밀가루는 소맥을 제분하여 얻은 것으로 수분 14.0% 이하이어야 한다.",
            "namespace": "food_code_text",
        },
        {
            "id": 2,
            "law_cache_id": 101,
            "law_name": "식품의 기준 및 규격",
            "article_label": "제5조",
            "text": "식품에 사용할 수 있는 원료는 별표 1에 따른다.",
            "namespace": "food_code_text",
        },
        {
            "id": 3,
            "law_cache_id": 102,
            "law_name": "식품첨가물의 기준 및 규격",
            "article_label": "제3조",
            "text": "아스파탐(Aspartame)의 사용 기준: 청량음료류 0.6 g/kg 이하.",
            "namespace": "additive_code_text",
        },
        {
            "id": 4,
            "law_cache_id": 103,
            "law_name": "건강기능식품의 기준 및 규격",
            "article_label": "제7조",
            "text": "홍삼 제품의 기능성분은 진세노사이드 Rg1+Rb1+Rg3 합계 0.8~34 mg/g이어야 한다.",
            "namespace": "health_food_text",
        },
        {
            "id": 5,
            "law_cache_id": 104,
            "law_name": "식품등의 한시적 기준 및 규격 인정 기준",
            "article_label": "제1조",
            "text": "한시적 기준·규격 인정 신청 시 제출 자료는 별표 2에 따른다.",
            "namespace": "temporary_standard",
        },
    ]
