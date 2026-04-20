"""P2-BE: F1 v2 라우터 와이어링 테스트.

테스트 시나리오:
    1. flag off  → run_feature1_with_rag 호출 (레거시 경로)
    2. flag on + Canary miss → 레거시 경로
    3. flag on + Canary hit  → run_feature1_v2 호출 + F1Output → pipeline_result 변환
    4. F1_REQUIRE_HITL0_APPROVAL=true + F0 != approved → 400 F0_NOT_APPROVED
    5. F1Output → pipeline_result 어댑터 스냅샷 (verdict 한글 변환, fail_reasons 추출 등)

실행:
    cd backend
    pytest tests/routers/test_feature1_v2_wiring.py -v --cov=routers.feature1
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from models.f1_types import F1Output


# ============================================================
# 공통 픽스처
# ============================================================


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient — Supabase 연결 없이 동작."""
    import os
    os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
    os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")

    from main import app
    return TestClient(app)


def _make_f1output(verdict: str = "permitted") -> F1Output:
    """테스트용 F1Output 팩토리."""
    return F1Output(
        verdict=verdict,
        confidence=0.90,
        evidence_laws=[],
        evidence_external_data=[
            {
                "step": "A",
                "source": "f1_forbidden_ingredients + 15111777",
                "forbidden_hits": [],
            },
            {
                "step": "B",
                "source": "15111777 + 15094202 + 15111913",
                "enriched_summary": [
                    {
                        "name": "구연산",
                        "allow_verdict": "allowed",
                        "component_code": "CA001",
                        "is_gmo": False,
                    }
                ],
                "unidentified": [],
                "conditional": [],
                "gmo_ingredients": [],
            },
            {
                "step": "C",
                "source": "15116583",
                "overall_status": "pass",
                "checks": [
                    {
                        "ingredient_name": "구연산",
                        "test_category": "함량",
                        "spec_raw": "99.0이상",
                        "actual_value": "99.5",
                        "unit_original": "%",
                        "unit_normalized": "%",
                        "threshold_value": 99.0,
                        "is_dangerous": False,
                        "status": "pass",
                        "law_ref": "식품첨가물공전 IV",
                    }
                ],
                "review_reasons": [],
            },
        ],
        unit_conversions=[],
        warnings=[],
        gmo_ingredients=[],
        api_call_stats={"15111777": 1},
        data_source_versions={},
    )


def _mock_supabase_upsert() -> MagicMock:
    """upsert 체인 mock."""
    mock_sb = MagicMock()
    mock_sb.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    return mock_sb


BASE_URL = "/api/v1/cases/{case_id}/pipeline/feature/1/run"

# case_id 가 MD5 해시 기준으로 Canary miss/hit 되는 값 미리 계산
# hash("canary-hit-case") % 100 < 100  → 항상 hit (CANARY_PERCENTAGE=100)
# hash("canary-miss-case") % 100 >= 10 → miss (CANARY_PERCENTAGE=10)
# 실제 hash 값에 의존하지 않고 should_use_new_pipeline 을 직접 mock 함

_INGREDIENTS_BODY = {
    "ingredients": [{"name": "구연산", "percentage": 0.5}],
    "food_type": "음료류",
}


# ============================================================
# 시나리오 1: flag off → 레거시 경로
# ============================================================


class TestFlagOff:
    """F1_USE_DATA_GO_KR_API=false → run_feature1_with_rag 경로 유지."""

    def test_flag_off_calls_legacy(self, client: TestClient) -> None:
        from models.judgment import Feature1Output as LegacyOutput

        mock_legacy_out = MagicMock(spec=LegacyOutput)
        mock_legacy_out.import_possible = True
        mock_legacy_out.forbidden_hits = []
        mock_legacy_out.aggregation = None
        mock_legacy_out.conditional_evaluations = []
        mock_legacy_out.standards_check = None
        mock_legacy_out.synthetic_flavor_ingredients = []
        mock_legacy_out.escalations = []
        mock_legacy_out.law_refs = []

        mock_sb = _mock_supabase_upsert()
        # F0 approved 체크 없음 (REQUIRE_HITL0_APPROVAL=False 기본)

        with (
            patch("routers.feature1.should_use_new_pipeline", return_value=False),
            patch("routers.feature1.F1_REQUIRE_HITL0_APPROVAL", False),
            patch(
                "routers.feature1._fetch_f0_parsed_result",
                return_value=None,
            ),
        ):
            # ingredients 직접 제공 → f0 조회 없이 진행
            with (
                patch("routers.feature1.asyncio.run",
                      return_value=(mock_legacy_out, None, "rag_skipped")) as mock_run,
                patch("routers.feature1.get_supabase", return_value=mock_sb),
            ):
                response = client.post(
                    BASE_URL.format(case_id="test-case-flag-off"),
                    json=_INGREDIENTS_BODY,
                )

        # asyncio.run 이 호출되었고, 반환값으로 run_feature1_with_rag 경로임을 확인
        mock_run.assert_called_once()
        # 응답 성공
        assert response.status_code == 200
        body = response.json()
        assert "ai_result" in body
        # v1 경로이므로 _internal.pipeline_version 이 없어야 함
        assert body["ai_result"].get("_internal", {}).get("pipeline_version") != "v2"


# ============================================================
# 시나리오 2: flag on + Canary miss → 레거시 경로
# ============================================================


class TestFlagOnCanaryMiss:
    """should_use_new_pipeline=False (Canary miss) → 레거시 경로."""

    def test_canary_miss_calls_legacy(self, client: TestClient) -> None:
        from models.judgment import Feature1Output as LegacyOutput

        mock_legacy_out = MagicMock(spec=LegacyOutput)
        mock_legacy_out.import_possible = True
        mock_legacy_out.forbidden_hits = []
        mock_legacy_out.aggregation = None
        mock_legacy_out.conditional_evaluations = []
        mock_legacy_out.standards_check = None
        mock_legacy_out.synthetic_flavor_ingredients = []
        mock_legacy_out.escalations = []
        mock_legacy_out.law_refs = []

        mock_sb = _mock_supabase_upsert()

        with (
            patch("routers.feature1.should_use_new_pipeline", return_value=False),
            patch("routers.feature1.F1_REQUIRE_HITL0_APPROVAL", False),
            patch("routers.feature1.asyncio.run",
                  return_value=(mock_legacy_out, None, "rag_skipped")) as mock_run,
            patch("routers.feature1.get_supabase", return_value=mock_sb),
        ):
            response = client.post(
                BASE_URL.format(case_id="test-case-canary-miss"),
                json=_INGREDIENTS_BODY,
            )

        mock_run.assert_called_once()
        assert response.status_code == 200
        # v2 pipeline_version 없음
        assert response.json()["ai_result"].get("_internal", {}).get("pipeline_version") != "v2"


# ============================================================
# 시나리오 3: flag on + Canary hit → v2 경로
# ============================================================


class TestFlagOnCanaryHit:
    """should_use_new_pipeline=True → run_feature1_v2 + F1Output → pipeline_result."""

    def test_canary_hit_calls_v2(self, client: TestClient) -> None:
        f1_out = _make_f1output("permitted")
        mock_sb = _mock_supabase_upsert()

        with (
            patch("routers.feature1.should_use_new_pipeline", return_value=True),
            patch("routers.feature1.F1_REQUIRE_HITL0_APPROVAL", False),
            patch("routers.feature1.asyncio.run", return_value=f1_out) as mock_run,
            patch("routers.feature1.get_supabase", return_value=mock_sb),
        ):
            response = client.post(
                BASE_URL.format(case_id="test-case-canary-hit"),
                json=_INGREDIENTS_BODY,
            )

        mock_run.assert_called_once()
        assert response.status_code == 200
        body = response.json()
        ai = body["ai_result"]
        # v2 경로 확인
        assert ai["_internal"]["pipeline_version"] == "v2"
        # verdict 한글 변환
        assert ai["verdict"] == "수입가능"
        assert ai["import_possible"] is True

    def test_canary_hit_prohibited_verdict(self, client: TestClient) -> None:
        """prohibited verdict → 수입불가 + import_possible=False."""
        f1_out = _make_f1output("prohibited")
        mock_sb = _mock_supabase_upsert()

        with (
            patch("routers.feature1.should_use_new_pipeline", return_value=True),
            patch("routers.feature1.F1_REQUIRE_HITL0_APPROVAL", False),
            patch("routers.feature1.asyncio.run", return_value=f1_out),
            patch("routers.feature1.get_supabase", return_value=mock_sb),
        ):
            response = client.post(
                BASE_URL.format(case_id="test-case-prohibited"),
                json=_INGREDIENTS_BODY,
            )

        assert response.status_code == 200
        ai = response.json()["ai_result"]
        assert ai["verdict"] == "수입불가"
        assert ai["import_possible"] is False
        # prohibited → needs_review status
        assert response.json()["status"] == "needs_review"

    def test_canary_hit_needs_review_verdict(self, client: TestClient) -> None:
        """needs_review verdict → 검토 필요 + needs_review status."""
        f1_out = _make_f1output("needs_review")
        mock_sb = _mock_supabase_upsert()

        with (
            patch("routers.feature1.should_use_new_pipeline", return_value=True),
            patch("routers.feature1.F1_REQUIRE_HITL0_APPROVAL", False),
            patch("routers.feature1.asyncio.run", return_value=f1_out),
            patch("routers.feature1.get_supabase", return_value=mock_sb),
        ):
            response = client.post(
                BASE_URL.format(case_id="test-case-needs-review"),
                json=_INGREDIENTS_BODY,
            )

        assert response.status_code == 200
        ai = response.json()["ai_result"]
        assert ai["verdict"] == "검토 필요"
        assert ai["import_possible"] is False


# ============================================================
# 시나리오 4: F1_REQUIRE_HITL0_APPROVAL=true + F0 != approved → 400
# ============================================================


class TestHitl0Gate:
    """HITL-0 게이트 — F0 approved 상태 검증."""

    def test_hitl0_flag_on_not_approved_400(self, client: TestClient) -> None:
        """F1_REQUIRE_HITL0_APPROVAL=true + F0 status=completed → 400 F0_NOT_APPROVED."""
        case_id = "test-hitl0-gate-case"
        mock_sb = MagicMock()
        f0_select = MagicMock()
        f0_select.data = [{"status": "completed"}]
        (
            mock_sb.table.return_value
            .select.return_value
            .eq.return_value
            .eq.return_value
            .limit.return_value
            .execute.return_value
        ) = f0_select

        with (
            patch("routers.feature1.F1_REQUIRE_HITL0_APPROVAL", True),
            patch("routers.feature1.get_supabase", return_value=mock_sb),
        ):
            response = client.post(
                BASE_URL.format(case_id=case_id),
                json=_INGREDIENTS_BODY,
            )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["error"] == "F0_NOT_APPROVED"
        assert detail["f0_status"] == "completed"

    def test_hitl0_flag_on_f0_none_400(self, client: TestClient) -> None:
        """F1_REQUIRE_HITL0_APPROVAL=true + F0 스텝 없음 → 400 F0_NOT_APPROVED."""
        case_id = "test-hitl0-gate-none"
        mock_sb = MagicMock()
        f0_select = MagicMock()
        f0_select.data = []  # F0 스텝 없음
        (
            mock_sb.table.return_value
            .select.return_value
            .eq.return_value
            .eq.return_value
            .limit.return_value
            .execute.return_value
        ) = f0_select

        with (
            patch("routers.feature1.F1_REQUIRE_HITL0_APPROVAL", True),
            patch("routers.feature1.get_supabase", return_value=mock_sb),
        ):
            response = client.post(
                BASE_URL.format(case_id=case_id),
                json=_INGREDIENTS_BODY,
            )

        assert response.status_code == 400
        assert response.json()["detail"]["error"] == "F0_NOT_APPROVED"

    def test_hitl0_flag_off_gate_skipped(self, client: TestClient) -> None:
        """F1_REQUIRE_HITL0_APPROVAL=false → HITL-0 게이트 완전 스킵."""
        case_id = "test-hitl0-flag-off"

        with (
            patch("routers.feature1.F1_REQUIRE_HITL0_APPROVAL", False),
            patch("routers.feature1.should_use_new_pipeline", return_value=False),
            patch(
                "routers.feature1._fetch_f0_parsed_result",
                return_value=None,
            ),
        ):
            response = client.post(
                BASE_URL.format(case_id=case_id),
                json={},  # ingredients 없음 → f0 조회로 넘어감
            )

        # F0_NOT_APPROVED 가 아닌 F0_NOT_COMPLETED 에러가 나야 함
        assert response.status_code == 400
        assert response.json()["detail"]["error"] == "F0_NOT_COMPLETED"


# ============================================================
# 시나리오 5: _f1output_to_pipeline_result 어댑터 스냅샷 테스트
# ============================================================


class TestF1OutputAdapterUnit:
    """_f1output_to_pipeline_result 어댑터 단위 테스트."""

    def _call_adapter(self, out: F1Output) -> dict:
        from routers.feature1 import _f1output_to_pipeline_result
        return _f1output_to_pipeline_result(out)

    def test_verdict_permitted_한글_변환(self) -> None:
        out = _make_f1output("permitted")
        result = self._call_adapter(out)
        assert result["verdict"] == "수입가능"
        assert result["import_possible"] is True

    def test_verdict_restricted_한글_변환(self) -> None:
        out = _make_f1output("restricted")
        result = self._call_adapter(out)
        assert result["verdict"] == "수입가능 (조건부)"
        assert result["import_possible"] is True

    def test_verdict_prohibited_한글_변환(self) -> None:
        out = _make_f1output("prohibited")
        result = self._call_adapter(out)
        assert result["verdict"] == "수입불가"
        assert result["import_possible"] is False

    def test_verdict_needs_review_한글_변환(self) -> None:
        out = _make_f1output("needs_review")
        result = self._call_adapter(out)
        assert result["verdict"] == "검토 필요"
        assert result["import_possible"] is False

    def test_ingredients_step_b_에서_추출(self) -> None:
        out = _make_f1output("permitted")
        result = self._call_adapter(out)
        ingredients = result["ingredients"]
        assert len(ingredients) == 1
        assert ingredients[0]["name"] == "구연산"
        assert ingredients[0]["status"] == "allowed"

    def test_standards_check_step_c_에서_추출(self) -> None:
        out = _make_f1output("permitted")
        result = self._call_adapter(out)
        standards = result["standards_check"]
        assert len(standards) == 1
        sc = standards[0]
        assert sc["ingredient_name"] == "구연산"
        assert sc["status"] == "pass"
        assert sc["threshold_value"] == 99.0
        assert sc["actual_value"] == 99.5

    def test_fail_reasons_warnings_포함(self) -> None:
        out = _make_f1output("prohibited")
        out.warnings = ["step_b_unidentified:아편", "step_a_api_error:timeout"]
        result = self._call_adapter(out)
        assert "step_b_unidentified:아편" in result["fail_reasons"]
        assert "step_a_api_error:timeout" in result["fail_reasons"]

    def test_fail_reasons_step_a_forbidden_hits_포함(self) -> None:
        out = _make_f1output("prohibited")
        # step A에 forbidden_hits 추가
        out.evidence_external_data[0]["forbidden_hits"] = [
            {
                "ingredient_name": "아편",
                "matched_name": "아편",
                "source": "db",
                "reason": "마약류관리법 제2조",
                "law_ref": "law-001",
            }
        ]
        result = self._call_adapter(out)
        assert any("아편" in r for r in result["fail_reasons"])

    def test_internal_pipeline_version_v2(self) -> None:
        out = _make_f1output("permitted")
        result = self._call_adapter(out)
        assert result["_internal"]["pipeline_version"] == "v2"

    def test_internal_evidence_laws_전달(self) -> None:
        out = _make_f1output("permitted")
        out.evidence_laws = [{"chunk_id": "c1", "law_name": "식품공전", "score": 0.9}]
        result = self._call_adapter(out)
        assert result["_internal"]["evidence_laws"] == out.evidence_laws

    def test_internal_gmo_ingredients_전달(self) -> None:
        out = _make_f1output("permitted")
        out.gmo_ingredients = ["옥수수"]
        result = self._call_adapter(out)
        assert result["_internal"]["gmo_ingredients"] == ["옥수수"]

    def test_internal_api_call_stats_전달(self) -> None:
        out = _make_f1output("permitted")
        out.api_call_stats = {"15111777": 3, "15094202": 1}
        result = self._call_adapter(out)
        assert result["_internal"]["api_call_stats"] == {"15111777": 3, "15094202": 1}

    def test_evidence_external_data_없을때_빈_리스트(self) -> None:
        """evidence_external_data가 없어도 크래시 없이 빈 값 반환."""
        out = F1Output(
            verdict="permitted",
            confidence=0.9,
            evidence_laws=[],
            evidence_external_data=[],
            unit_conversions=[],
            warnings=[],
            gmo_ingredients=[],
            api_call_stats={},
            data_source_versions={},
        )
        result = self._call_adapter(out)
        assert result["ingredients"] == []
        assert result["standards_check"] == []
        assert result["fail_reasons"] == []
        assert result["_internal"]["pipeline_version"] == "v2"


# ============================================================
# should_use_new_pipeline 단위 테스트
# ============================================================


class TestShouldUseNewPipeline:
    """feature_flags.should_use_new_pipeline 로직 검증."""

    def test_flag_off_무조건_false(self) -> None:
        with (
            patch("config.feature_flags.F1_USE_DATA_GO_KR_API", False),
            patch("config.feature_flags.F1_CANARY_PERCENTAGE", 100),
        ):
            from config.feature_flags import should_use_new_pipeline
            assert should_use_new_pipeline("any-case-id") is False

    def test_flag_on_canary_100_항상_true(self) -> None:
        with (
            patch("config.feature_flags.F1_USE_DATA_GO_KR_API", True),
            patch("config.feature_flags.F1_CANARY_PERCENTAGE", 100),
        ):
            from config.feature_flags import should_use_new_pipeline
            assert should_use_new_pipeline("any-case-id") is True

    def test_flag_on_canary_0_항상_false(self) -> None:
        with (
            patch("config.feature_flags.F1_USE_DATA_GO_KR_API", True),
            patch("config.feature_flags.F1_CANARY_PERCENTAGE", 0),
        ):
            from config.feature_flags import should_use_new_pipeline
            assert should_use_new_pipeline("any-case-id") is False

    def test_flag_on_canary_결정론적(self) -> None:
        """동일 case_id → 항상 동일 결과 (결정론적)."""
        with (
            patch("config.feature_flags.F1_USE_DATA_GO_KR_API", True),
            patch("config.feature_flags.F1_CANARY_PERCENTAGE", 50),
        ):
            from config.feature_flags import should_use_new_pipeline
            case_id = "deterministic-test-case"
            result_1 = should_use_new_pipeline(case_id)
            result_2 = should_use_new_pipeline(case_id)
            assert result_1 == result_2

    def test_flag_on_canary_md5_기반_분기(self) -> None:
        """MD5 hash % 100 < percentage 로직 직접 검증."""
        import hashlib
        case_id = "test-hash-case"
        h = int(hashlib.md5(case_id.encode()).hexdigest(), 16) % 100

        with (
            patch("config.feature_flags.F1_USE_DATA_GO_KR_API", True),
            patch("config.feature_flags.F1_CANARY_PERCENTAGE", h + 1),
        ):
            from config.feature_flags import should_use_new_pipeline
            assert should_use_new_pipeline(case_id) is True

        with (
            patch("config.feature_flags.F1_USE_DATA_GO_KR_API", True),
            patch("config.feature_flags.F1_CANARY_PERCENTAGE", h),
        ):
            from config.feature_flags import should_use_new_pipeline
            assert should_use_new_pipeline(case_id) is False
