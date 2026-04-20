"""T2 파서 edge case 테스트 — 20건 (성공 10 + 실패/경계 10).

WAVE4_P4A_REPORT §기준규격 23.3% 원인 분석 기반:
    - 단위 약어 변형 (μg/kg ↔ ug/kg ↔ mcg/kg, ppm, ppb, mg/g 등)
    - μ/u/mcg 혼용 허용
    - 공백 포함 범위 ("0.01 ~ 0.1", "0.01~ 0.1", "0.01 ~0.1")
    - 한자/한글 혼용 (以下↔이하, 以上↔이상, 未滿↔미만)
    - non-numeric 확장 (미검출, 검출되지 않음, 적합함, 기준적합 등)
    - 복합 기준 첫 번째 채택 ("총 X는 0.1 이하, Y는 0.5 이하")
    - 단위 포함 SPEC_VAL ("0.1 mg/kg 이하", "10 μg/kg 이하")

실행:
    cd backend
    pytest tests/utils/test_unit_converter_parsing.py -v
"""

from __future__ import annotations

import pytest

from utils.unit_converter import (
    SpecEvaluation,
    UnitIncompatibleError,
    normalize_to_common_unit,
    parse_non_numeric_spec,
    parse_numeric_spec,
)


# ============================================================
# 성공 케이스 10건 (정상 파싱 기대)
# ============================================================


class TestSuccessCases:
    """edge case 성공 케이스 10건."""

    # S-01: 단위 약어 ug/kg (μ 대신 u)
    def test_s01_ug_kg_unit_alias(self) -> None:
        """ug/kg → mg/kg (μ 대신 u 표기 허용)."""
        val, unit = normalize_to_common_unit(1000.0, "ug/kg")
        assert unit == "mg/kg"
        assert val == pytest.approx(1.0)

    # S-02: mcg/kg 표기 (mcg = micrograms)
    def test_s02_mcg_kg_unit_alias(self) -> None:
        """mcg/kg → mg/kg (mcg 표기 허용)."""
        val, unit = normalize_to_common_unit(500.0, "mcg/kg")
        assert unit == "mg/kg"
        assert val == pytest.approx(0.5)

    # S-03: ppb 단위 (ppb ≡ μg/kg ≡ 0.001 mg/kg)
    def test_s03_ppb_unit(self) -> None:
        """ppb → mg/kg (ppb ≡ μg/kg)."""
        val, unit = normalize_to_common_unit(100.0, "ppb")
        assert unit == "mg/kg"
        assert val == pytest.approx(0.1)

    # S-04: 공백 포함 범위 "0.01 ~ 0.1"
    def test_s04_range_with_spaces(self) -> None:
        """'0.01 ~ 0.1' → (0.01, 0.1) (공백 포함 범위)."""
        lo, hi = parse_numeric_spec("0.01 ~ 0.1")
        assert lo == pytest.approx(0.01)
        assert hi == pytest.approx(0.1)

    # S-05: 비대칭 공백 범위 "0.01~ 0.1"
    def test_s05_range_asymmetric_spaces(self) -> None:
        """'0.01~ 0.1' → (0.01, 0.1) (비대칭 공백)."""
        lo, hi = parse_numeric_spec("0.01~ 0.1")
        assert lo == pytest.approx(0.01)
        assert hi == pytest.approx(0.1)

    # S-06: 한자 以下 → 이하
    def test_s06_hanja_ika_below(self) -> None:
        """'0.5以下' → (None, 0.5) (한자 이하)."""
        lo, hi = parse_numeric_spec("0.5以下")
        assert lo is None
        assert hi == pytest.approx(0.5)

    # S-07: 한자 以上 → 이상
    def test_s07_hanja_ika_above(self) -> None:
        """'85.0以上' → (85.0, None) (한자 이상)."""
        lo, hi = parse_numeric_spec("85.0以上")
        assert lo == pytest.approx(85.0)
        assert hi is None

    # S-08: non-numeric "미검출" 확장
    def test_s08_non_numeric_migeomchul(self) -> None:
        """'미검출' → kind=non_detect (T2 추가 패턴)."""
        result = parse_non_numeric_spec("미검출")
        assert result.kind == "non_detect"
        assert result.requires_hitl is False

    # S-09: non-numeric "검출되지 않음"
    def test_s09_non_numeric_not_detected(self) -> None:
        """'검출되지 않음' → kind=non_detect."""
        result = parse_non_numeric_spec("검출되지 않음")
        assert result.kind == "non_detect"
        assert result.requires_hitl is False

    # S-10: 복합 기준 첫 번째만 채택
    def test_s10_compound_spec_first_only(self) -> None:
        """'0.1이하, 0.5이하' → (None, 0.1) (첫 번째 기준만)."""
        lo, hi = parse_numeric_spec("0.1이하, 0.5이하")
        assert lo is None
        assert hi == pytest.approx(0.1)


# ============================================================
# 경계/실패 케이스 10건 (파싱 불가 또는 특수 동작 기대)
# ============================================================


class TestBoundaryCases:
    """edge case 경계/실패 케이스 10건."""

    # B-01: 단위 포함 SPEC_VAL "0.1 mg/kg 이하" → 수치 추출
    def test_b01_spec_with_unit_string(self) -> None:
        """'0.1 mg/kg 이하' → (None, 0.1) (단위 포함 파싱)."""
        lo, hi = parse_numeric_spec("0.1 mg/kg 이하")
        # 단위 포함 표현: _SPEC_WITH_UNIT_RE 로 파싱
        assert lo is None
        assert hi == pytest.approx(0.1)

    # B-02: "10 μg/kg 이하" → (None, 10.0)
    def test_b02_spec_ugkg_with_unit(self) -> None:
        """'10 μg/kg 이하' → (None, 10.0)."""
        lo, hi = parse_numeric_spec("10 μg/kg 이하")
        assert lo is None
        assert hi == pytest.approx(10.0)

    # B-03: 완전히 파싱 불가 텍스트
    def test_b03_unparseable_complex_text(self) -> None:
        """'납 및 카드뮴 기준' 같은 복잡한 한글 텍스트 → (None, None)."""
        lo, hi = parse_numeric_spec("납 및 카드뮴 기준")
        assert lo is None
        assert hi is None

    # B-04: non-numeric "적합함" (qualitative 확장)
    def test_b04_non_numeric_suitable(self) -> None:
        """'적합함' → kind=qualitative, requires_hitl=True."""
        result = parse_non_numeric_spec("적합함")
        assert result.kind == "qualitative"
        assert result.requires_hitl is True

    # B-05: non-numeric "기준적합" (qualitative 확장)
    def test_b05_non_numeric_qualified(self) -> None:
        """'기준적합' → kind=qualitative."""
        result = parse_non_numeric_spec("기준적합")
        assert result.kind == "qualitative"
        assert result.requires_hitl is True

    # B-06: 완전 인식 불가 텍스트 → unknown
    def test_b06_unknown_text(self) -> None:
        """'해당없음(특수표현)' → kind=unknown, requires_hitl=True."""
        result = parse_non_numeric_spec("해당없음(특수표현)")
        assert result.kind == "unknown"
        assert result.requires_hitl is True

    # B-07: 未滿 한자 (미만)
    def test_b07_hanja_miman(self) -> None:
        """'1.0未滿' → (None, 1.0) (한자 미만)."""
        lo, hi = parse_numeric_spec("1.0未滿")
        assert lo is None
        assert hi == pytest.approx(1.0)

    # B-08: μg/g 단위 (mg/kg 동일)
    def test_b08_ug_per_g_unit(self) -> None:
        """μg/g → mg/kg (μg/g ≡ mg/kg)."""
        val, unit = normalize_to_common_unit(5.0, "μg/g")
        assert unit == "mg/kg"
        assert val == pytest.approx(5.0)

    # B-09: mg/g 단위 (g/kg 동일)
    def test_b09_mg_per_g_unit(self) -> None:
        """mg/g → mg/kg (mg/g = g/kg = 1000 mg/kg)."""
        val, unit = normalize_to_common_unit(2.0, "mg/g")
        assert unit == "mg/kg"
        assert val == pytest.approx(2000.0)

    # B-10: 빈 문자열 → (None, None)
    def test_b10_empty_string_returns_none(self) -> None:
        """빈 문자열 → (None, None)."""
        lo, hi = parse_numeric_spec("")
        assert lo is None
        assert hi is None
        # non-numeric도 unknown
        result = parse_non_numeric_spec("")
        assert result.kind == "unknown"
        assert result.requires_hitl is True
