"""Wave 2 통합 테스트 — run_feature1_v2 오케스트레이션 검증 (09번 §4-2 I-02~I-07).

Step A/B/C/D 를 mock 으로 주입하여 부모 세션이 작성한 orchestrator 의 분기·
조기 종료·F1Output 합성 로직을 검증한다. 실 API 통합은 Wave 3 W3-QA 범위.

I-01 (F0 미완료 → 400) 은 라우터 의존이므로 Wave 3 이월.
I-08 (HITL-2 locked) 은 pipeline_steps.status 의존이므로 Wave 3 이월.
"""

from __future__ import annotations

import pytest

from models.f1_types import (
    ForbiddenHit,
    LawCitation,
    StandardCheck,
    StepAResult,
    StepBResult,
    StepCResult,
    StepDResult,
)
from models.judgment import Ingredient
from services import feature1


@pytest.fixture
def ingredients_simple() -> list[Ingredient]:
    return [Ingredient(name="대두", percentage=50.0)]


@pytest.fixture
def patch_steps(monkeypatch):
    """Step A/B/C/D 를 AsyncMock 유사 함수로 교체하는 헬퍼."""

    from services import f1_step_a, f1_step_b, f1_step_c, f1_step_d

    state: dict = {}

    def _install(
        a_result: StepAResult,
        b_result: StepBResult,
        c_result: StepCResult,
        d_result: StepDResult,
    ) -> None:
        async def _a(_ings, *, client=None):
            state["a_called"] = True
            return a_result

        async def _b(_ings):
            state["b_called"] = True
            return b_result

        async def _c(_ings, food_type_hierarchy=None, measured_values=None, **_kw):
            state["c_called"] = True
            return c_result

        async def _d(_ctx, top_k=5):
            state["d_called"] = True
            return d_result

        monkeypatch.setattr(f1_step_a, "run_step_a", _a)
        monkeypatch.setattr(f1_step_b, "run_step_b", _b)
        monkeypatch.setattr(f1_step_c, "run_step_c", _c)
        monkeypatch.setattr(f1_step_d, "run_step_d", _d)

    return _install, state


# ============================================================
# I-02: 정상 대두 제품 — 전 Step pass → permitted
# ============================================================


class TestI02NormalDaedu:
    @pytest.mark.asyncio
    async def test_permitted_when_all_clean(
        self, ingredients_simple, patch_steps
    ) -> None:
        install, state = patch_steps
        install(
            a_result=StepAResult(forbidden_hits=[], stopped=False),
            b_result=StepBResult(
                enriched_ingredients=[
                    Ingredient(
                        name="대두", percentage=50.0, allow_verdict="allowed"
                    )
                ],
                unidentified=[],
                conditional=[],
                gmo_ingredients=[],
                api_call_stats={"15111777": 1, "15094202": 1, "15111913": 1},
            ),
            c_result=StepCResult(checks=[], overall_status="pass"),
            d_result=StepDResult(
                citations=[
                    LawCitation(
                        chunk_id="c1",
                        law_name="식품공전",
                        article_no="제3조",
                        text="원재료 일반",
                        score=0.8,
                        namespace="food_code_text",
                    )
                ]
            ),
        )

        out = await feature1.run_feature1_v2(ingredients_simple)

        assert out.verdict == "permitted"
        assert out.confidence == 0.90
        assert state["a_called"] and state["b_called"]
        assert state["c_called"] and state["d_called"]
        assert len(out.evidence_laws) == 1


# ============================================================
# I-03: 금지원료(아편) → Step A 조기 종료
# ============================================================


class TestI03ForbiddenEarlyStop:
    @pytest.mark.asyncio
    async def test_step_a_forbidden_skips_b_c(
        self, patch_steps
    ) -> None:
        install, state = patch_steps
        install(
            a_result=StepAResult(
                forbidden_hits=[
                    ForbiddenHit(
                        ingredient_name="아편",
                        matched_name="아편",
                        source="db",
                        reason="마약류관리법 제2조",
                        law_ref="law-001",
                    )
                ],
                stopped=True,
            ),
            b_result=StepBResult(),  # 호출 안 되어야 함
            c_result=StepCResult(),
            d_result=StepDResult(
                citations=[
                    LawCitation(
                        chunk_id="c2",
                        law_name="마약류관리에 관한 법률",
                        article_no="제2조",
                        text="아편 제조·수입 금지",
                        score=0.95,
                        namespace="food_code_text",
                    )
                ]
            ),
        )

        out = await feature1.run_feature1_v2(
            [Ingredient(name="아편", percentage=10.0)]
        )

        assert out.verdict == "prohibited"
        assert out.confidence == 0.95
        assert state.get("a_called")
        assert "b_called" not in state, "Step A stopped 시 Step B skip 되어야 함"
        assert "c_called" not in state, "Step A stopped 시 Step C skip 되어야 함"
        assert state.get("d_called"), "Step D 는 법령 인용용으로 실행되어야 함"
        assert len(out.evidence_external_data) >= 1
        assert out.evidence_external_data[0]["step"] == "A"


# ============================================================
# I-04: 조건부 원재료(인삼) → restricted + HITL-1 대기
# ============================================================


class TestI04ConditionalIngredient:
    @pytest.mark.asyncio
    async def test_restricted_proceeds_to_c(self, patch_steps) -> None:
        install, state = patch_steps
        ginseng = Ingredient(
            name="인삼",
            percentage=5.0,
            allow_verdict="restricted",
            restriction_condition="뿌리만 사용",
        )
        install(
            a_result=StepAResult(forbidden_hits=[], stopped=False),
            b_result=StepBResult(
                enriched_ingredients=[ginseng],
                unidentified=[],
                conditional=[ginseng],
                gmo_ingredients=[],
                api_call_stats={"15111777": 1},
            ),
            c_result=StepCResult(checks=[], overall_status="pass"),
            d_result=StepDResult(citations=[]),
        )

        out = await feature1.run_feature1_v2(
            [Ingredient(name="인삼", percentage=5.0)]
        )

        assert out.verdict == "restricted"
        assert 0.7 <= out.confidence <= 0.9
        assert state.get("c_called"), "restricted 라도 Step C 계속 진행"
        # conditional 정보가 evidence 에 포함되어야 함
        step_b_data = next(
            e for e in out.evidence_external_data if e["step"] == "B"
        )
        assert "인삼" in step_b_data["conditional"]


# ============================================================
# I-05: GMO=Y 원재료 포함 → gmo_ingredients 채워짐 + F3 전달 준비
# ============================================================


class TestI05GMOPropagation:
    @pytest.mark.asyncio
    async def test_gmo_ingredients_forwarded(self, patch_steps) -> None:
        install, _ = patch_steps
        corn = Ingredient(
            name="옥수수", percentage=30.0, allow_verdict="allowed", is_gmo=True
        )
        install(
            a_result=StepAResult(forbidden_hits=[], stopped=False),
            b_result=StepBResult(
                enriched_ingredients=[corn],
                unidentified=[],
                conditional=[],
                gmo_ingredients=["옥수수"],
                api_call_stats={"15111913": 1},
            ),
            c_result=StepCResult(checks=[], overall_status="pass"),
            d_result=StepDResult(citations=[]),
        )

        out = await feature1.run_feature1_v2(
            [Ingredient(name="옥수수", percentage=30.0)]
        )

        assert out.gmo_ingredients == ["옥수수"]
        assert out.verdict == "permitted"  # GMO=Y 자체는 금지 사유 아님
        assert out.api_call_stats.get("15111913") == 1


# ============================================================
# I-06: Step C fail (기준규격 초과) → prohibited
# ============================================================


class TestI06StandardsFail:
    @pytest.mark.asyncio
    async def test_step_c_fail_yields_prohibited(self, patch_steps) -> None:
        install, _ = patch_steps
        ing = Ingredient(
            name="L-아스코르브산", percentage=5.0, allow_verdict="allowed"
        )
        install(
            a_result=StepAResult(forbidden_hits=[], stopped=False),
            b_result=StepBResult(
                enriched_ingredients=[ing],
                unidentified=[],
                conditional=[],
                gmo_ingredients=[],
            ),
            c_result=StepCResult(
                checks=[
                    StandardCheck(
                        ingredient_name="L-아스코르브산",
                        test_category="함량",
                        spec_raw="85.0이상",
                        actual_value="80",
                        unit_original="%",
                        unit_normalized="mg/kg",
                        threshold_value=850000.0,
                        status="fail",
                    )
                ],
                overall_status="fail",
            ),
            d_result=StepDResult(citations=[]),
        )

        out = await feature1.run_feature1_v2(
            [Ingredient(name="L-아스코르브산", percentage=5.0)]
        )

        assert out.verdict == "prohibited"
        assert out.confidence == 0.90
        assert len(out.unit_conversions) == 1
        assert out.unit_conversions[0]["status"] == "fail"


# ============================================================
# I-07: API 장애 → escalations/warnings 기록, DB 결과만으로 계속
# ============================================================


class TestI07ApiFailurePropagation:
    @pytest.mark.asyncio
    async def test_step_a_api_errors_recorded_as_warnings(
        self, patch_steps
    ) -> None:
        install, _ = patch_steps
        install(
            a_result=StepAResult(
                forbidden_hits=[],
                stopped=False,
                api_errors=["대두: DATA_GO_KR_TIMEOUT"],
            ),
            b_result=StepBResult(
                enriched_ingredients=[
                    Ingredient(
                        name="대두", percentage=50.0, allow_verdict="unidentified"
                    )
                ],
                unidentified=["대두"],
                conditional=[],
                gmo_ingredients=[],
            ),
            c_result=StepCResult(checks=[], overall_status="no_data"),
            d_result=StepDResult(citations=[]),
        )

        out = await feature1.run_feature1_v2(
            [Ingredient(name="대두", percentage=50.0)]
        )

        # warnings 에 step_a_api_error 와 step_b_unidentified 접두어 모두 누적
        assert any(w.startswith("step_a_api_error:") for w in out.warnings)
        assert any(w.startswith("step_b_unidentified:") for w in out.warnings)
        # unidentified 존재 → needs_review
        assert out.verdict == "needs_review"


# ============================================================
# Additional: Step B 에서 prohibited verdict → Step C skip
# ============================================================


class TestStepBProhibitedSkipsC:
    @pytest.mark.asyncio
    async def test_b_prohibited_skips_c(self, patch_steps) -> None:
        install, state = patch_steps
        bad = Ingredient(
            name="알 수 없는 독성 원료",
            percentage=10.0,
            allow_verdict="prohibited",
        )
        install(
            a_result=StepAResult(forbidden_hits=[], stopped=False),
            b_result=StepBResult(
                enriched_ingredients=[bad],
                unidentified=[],
                conditional=[],
                gmo_ingredients=[],
                stopped=True,  # 🟡-4 fix: Step B prohibited 조기 종료 시그널
            ),
            c_result=StepCResult(),  # 호출되지 않아야 함
            d_result=StepDResult(citations=[]),
        )

        out = await feature1.run_feature1_v2(
            [Ingredient(name="알 수 없는 독성 원료", percentage=10.0)]
        )

        assert out.verdict == "prohibited"
        assert out.confidence == 0.85
        assert "c_called" not in state, "Step B prohibited 시 Step C skip"
        assert state.get("d_called"), "Step D 는 법령 인용용으로 실행"
