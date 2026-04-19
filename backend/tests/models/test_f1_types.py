"""W1-B 단위 테스트 — f1_types.py + judgment.py F1 영역.

커버리지 목표: 85%+
케이스 구성:
    - DataGoKrEndpoint Enum 불변성 (4개 값)
    - StandardCheck valid/invalid
    - Feature1Output Day 0 동결 필드 + W1-B 확장 필드
    - Ingredient W1-B 신규 필드 6종 (optional None 허용)
    - pipeline_steps.ai_result 역호환 (신규 필드 없이 파싱 가능)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.f1_types import DataGoKrEndpoint, Feature1Output, StandardCheck
from models.judgment import AllowVerdict, Ingredient


# ============================================================
# DataGoKrEndpoint — 4개 값 불변성 확인
# ============================================================


class TestDataGoKrEndpoint:
    def test_four_members_exist(self):
        members = list(DataGoKrEndpoint)
        assert len(members) == 4, f"Enum 멤버 수 변경 금지: {members}"

    def test_values_are_frozen(self):
        assert DataGoKrEndpoint.FOOD_RAW_MATERIAL == "15111913"
        assert DataGoKrEndpoint.IMPORT_FOOD_INGREDIENT == "15111777"
        assert DataGoKrEndpoint.ADDITIVE_STANDARD == "15116583"
        assert DataGoKrEndpoint.IMPORT_FOOD_COMPONENT == "15094202"

    def test_is_str_subclass(self):
        """str Enum이므로 문자열 비교 직접 가능해야 함."""
        assert DataGoKrEndpoint.FOOD_RAW_MATERIAL == "15111913"
        assert isinstance(DataGoKrEndpoint.FOOD_RAW_MATERIAL, str)

    def test_from_string(self):
        ep = DataGoKrEndpoint("15094202")
        assert ep is DataGoKrEndpoint.IMPORT_FOOD_COMPONENT

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            DataGoKrEndpoint("99999999")


# ============================================================
# StandardCheck — 신규 모델 (07번 §2-4)
# ============================================================


class TestStandardCheck:
    def _valid_payload(self, **kwargs) -> dict:
        base = {"ingredient_name": "소르빈산"}
        base.update(kwargs)
        return base

    def test_minimal_valid(self):
        sc = StandardCheck(**self._valid_payload())
        assert sc.ingredient_name == "소르빈산"
        assert sc.status == "no_data"  # 기본값
        assert sc.test_category is None
        assert sc.spec_raw is None
        assert sc.is_dangerous is None
        assert sc.unit_original is None
        assert sc.unit_normalized is None

    def test_full_valid(self):
        sc = StandardCheck(
            ingredient_name="소르빈산",
            test_category="함량",
            spec_raw="0.6 g/kg 이하",
            spec_summary="보존료로 사용 시",
            actual_value="0.4 g/kg",
            unit_original="g/kg",
            unit_normalized="mg/kg",
            threshold_value=600.0,
            is_dangerous=False,
            status="pass",
            law_ref="식품첨가물공전 §3",
        )
        assert sc.status == "pass"
        assert sc.threshold_value == 600.0
        assert sc.is_dangerous is False
        assert sc.unit_normalized == "mg/kg"

    def test_status_choices(self):
        for s in ("pass", "fail", "review_needed", "no_data"):
            sc = StandardCheck(ingredient_name="x", status=s)
            assert sc.status == s

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationError):
            StandardCheck(ingredient_name="x", status="unknown")

    def test_ingredient_name_required(self):
        with pytest.raises(ValidationError):
            StandardCheck()  # type: ignore[call-arg]

    def test_extra_fields_ignored(self):
        """extra='ignore' — 알 수 없는 필드는 무시."""
        sc = StandardCheck(ingredient_name="x", unknown_field="y")
        assert not hasattr(sc, "unknown_field")

    def test_is_dangerous_none_allowed(self):
        sc = StandardCheck(ingredient_name="x", is_dangerous=None)
        assert sc.is_dangerous is None

    def test_is_dangerous_true(self):
        sc = StandardCheck(ingredient_name="x", is_dangerous=True)
        assert sc.is_dangerous is True


# ============================================================
# Feature1Output — Day 0 필드 + W1-B 확장 필드
# ============================================================


class TestFeature1Output:
    def _minimal(self, **kwargs) -> dict:
        base = {"verdict": "permitted", "confidence": 0.9}
        base.update(kwargs)
        return base

    def test_minimal_valid(self):
        out = Feature1Output(**self._minimal())
        assert out.verdict == "permitted"
        assert out.confidence == 0.9
        # Day 0 필드 기본값
        assert out.evidence_laws == []
        assert out.evidence_external_data == []
        assert out.unit_conversions == []
        assert out.warnings == []
        # W1-B 확장 필드 기본값
        assert out.gmo_ingredients == []
        assert out.api_call_stats == {}
        assert out.data_source_versions == {}

    def test_day0_fields_present(self):
        """Day 0 동결 6개 필드가 모두 존재해야 함."""
        out = Feature1Output(**self._minimal())
        frozen_fields = {
            "verdict", "confidence", "evidence_laws",
            "evidence_external_data", "unit_conversions", "warnings",
        }
        for f in frozen_fields:
            assert hasattr(out, f), f"Day 0 필드 누락: {f}"

    def test_w1b_extension_fields_present(self):
        """W1-B 확장 3개 필드가 모두 존재해야 함."""
        out = Feature1Output(**self._minimal())
        for f in ("gmo_ingredients", "api_call_stats", "data_source_versions"):
            assert hasattr(out, f), f"W1-B 확장 필드 누락: {f}"

    def test_confidence_range_valid(self):
        Feature1Output(**self._minimal(confidence=0.0))
        Feature1Output(**self._minimal(confidence=1.0))

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            Feature1Output(**self._minimal(confidence=1.1))
        with pytest.raises(ValidationError):
            Feature1Output(**self._minimal(confidence=-0.1))

    def test_verdict_required(self):
        with pytest.raises(ValidationError):
            Feature1Output(confidence=0.5)  # type: ignore[call-arg]

    def test_gmo_ingredients_populated(self):
        out = Feature1Output(**self._minimal(gmo_ingredients=["대두", "옥수수"]))
        assert out.gmo_ingredients == ["대두", "옥수수"]

    def test_api_call_stats_populated(self):
        stats = {"15111777": 3, "15094202": 1}
        out = Feature1Output(**self._minimal(api_call_stats=stats))
        assert out.api_call_stats["15111777"] == 3

    def test_data_source_versions_populated(self):
        versions = {"15111777": "2024-03-01", "15116583": "2024-02-15"}
        out = Feature1Output(**self._minimal(data_source_versions=versions))
        assert out.data_source_versions["15116583"] == "2024-02-15"

    def test_evidence_laws_list(self):
        laws = [{"namespace": "samc-law-f1", "score": 0.87, "text": "..."}]
        out = Feature1Output(**self._minimal(evidence_laws=laws))
        assert out.evidence_laws[0]["namespace"] == "samc-law-f1"

    def test_extra_allow_does_not_raise(self):
        """extra='allow' — 추가 필드는 그대로 보존."""
        out = Feature1Output(**self._minimal(future_field="wave3_value"))
        assert out.future_field == "wave3_value"  # type: ignore[attr-defined]

    def test_legacy_pipeline_steps_compat(self):
        """기존 pipeline_steps.ai_result 형식 (W1-B 확장 필드 없음) 역호환."""
        legacy_payload = {
            "verdict": "needs_review",
            "confidence": 0.6,
            # gmo_ingredients, api_call_stats, data_source_versions 누락
        }
        out = Feature1Output(**legacy_payload)
        # 신규 필드가 기본값으로 채워져야 함 (파싱 실패 금지)
        assert out.gmo_ingredients == []
        assert out.api_call_stats == {}
        assert out.data_source_versions == {}


# ============================================================
# Ingredient — W1-B 신규 필드 6종
# ============================================================


class TestIngredientW1BFields:
    def test_new_fields_all_none_by_default(self):
        ing = Ingredient(name="대두")
        assert ing.component_code is None
        assert ing.allow_verdict is None
        assert ing.restriction_condition is None
        assert ing.edible_parts is None
        assert ing.is_gmo is None
        assert ing.source_api is None

    def test_existing_fields_unaffected(self):
        """기존 필드가 여전히 동작해야 함 (breaking change 금지)."""
        ing = Ingredient(
            name="소르빈산",
            percentage=0.06,
            ins="200",
            cas="110-44-1",
            part="열매",
        )
        assert ing.name == "소르빈산"
        assert ing.percentage == 0.06
        assert ing.ins == "200"
        assert ing.part == "열매"

    def test_allow_verdict_valid_values(self):
        for v in ("allowed", "restricted", "prohibited", "unidentified"):
            ing = Ingredient(name="x", allow_verdict=v)
            assert ing.allow_verdict == v

    def test_allow_verdict_invalid_raises(self):
        with pytest.raises(ValidationError):
            Ingredient(name="x", allow_verdict="permitted")  # 레거시 값 — 신규 모델에서 허용 안 됨

    def test_allow_verdict_none_allowed(self):
        ing = Ingredient(name="x", allow_verdict=None)
        assert ing.allow_verdict is None

    def test_component_code_str(self):
        ing = Ingredient(name="x", component_code="A001234")
        assert ing.component_code == "A001234"

    def test_restriction_condition_str(self):
        ing = Ingredient(name="x", restriction_condition="가열제품에 한하여 사용 가능")
        assert ing.restriction_condition == "가열제품에 한하여 사용 가능"

    def test_edible_parts_str(self):
        ing = Ingredient(name="알로에베라", edible_parts="잎(껍질 제거)")
        assert ing.edible_parts == "잎(껍질 제거)"

    def test_is_gmo_bool(self):
        ing_true = Ingredient(name="대두", is_gmo=True)
        ing_false = Ingredient(name="옥수수", is_gmo=False)
        assert ing_true.is_gmo is True
        assert ing_false.is_gmo is False

    def test_source_api_endpoint_id(self):
        ing = Ingredient(name="x", source_api="15094202")
        assert ing.source_api == "15094202"

    def test_source_api_db_value(self):
        ing = Ingredient(name="x", source_api="db")
        assert ing.source_api == "db"

    def test_sub_ingredients_still_works(self):
        """복합원재료 재귀 구조 유지 확인."""
        sub = Ingredient(name="옥수수전분", is_gmo=True)
        parent = Ingredient(name="변성전분", sub_ingredients=[sub])
        assert parent.sub_ingredients[0].is_gmo is True

    def test_full_w1b_ingredient(self):
        ing = Ingredient(
            name="소르빈산칼륨",
            percentage=0.05,
            component_code="CPNT_0042",
            allow_verdict="restricted",
            restriction_condition="보존료로만 사용 가능",
            edible_parts=None,
            is_gmo=False,
            source_api="15094202",
        )
        assert ing.allow_verdict == "restricted"
        assert ing.is_gmo is False
        assert ing.source_api == "15094202"


# ============================================================
# AllowVerdict — 타입 별칭 노출 확인
# ============================================================


class TestAllowVerdict:
    def test_allowed_values(self):
        """AllowVerdict 가 모듈 레벨에서 임포트 가능해야 함."""
        # Literal 타입이므로 런타임 값 자체는 str — 임포트 성공 확인만
        assert AllowVerdict is not None

    def test_permitted_is_not_in_allow_verdict(self):
        """'permitted' 는 AllowVerdict 에 포함되지 않는다 (의도적 분리)."""
        # Pydantic Ingredient 를 통해 간접 검증
        with pytest.raises(ValidationError):
            Ingredient(name="x", allow_verdict="permitted")
