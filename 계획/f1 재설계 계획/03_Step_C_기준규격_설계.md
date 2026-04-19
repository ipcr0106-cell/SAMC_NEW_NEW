# 03. Step C — 기준규격 수치 비교 설계 ⭐

> 의존: [06_API_클라이언트_설계](./06_API_클라이언트_설계.md), [11_단위_정규화_모듈_설계](./11_단위_정규화_모듈_설계.md), [08_에러_처리_설계](./08_에러_처리_설계.md)
> 산출물: `backend/services/f1_step_c.py`

---

## 1. 목적

원재료 + 식품유형 조합으로 15116583 (식품첨가물 기준규격 현황) API를 조회하여, 실측값과 기준규격을 비교한다. 기존 `f1_additive_limits`, `f1_safety_standards` 테이블을 완전 대체.

---

## 2. 입출력 계약

```python
async def run_step_c(
    ingredients: list[Ingredient],          # Step B 결과 반영된 상태
    food_type_hierarchy: FoodTypeHierarchy,
    measured_values: Optional[dict[str, MeasuredValue]] = None,
) -> StepCResult:
    """원재료당 기준규격 조회·비교. 실측값 없으면 비교만 스킵 (규격만 표시)."""


@dataclass
class MeasuredValue:
    value: float
    unit: str             # 원본 단위 (보통 F4 라벨 OCR 또는 HITL-0 입력)
    source: str           # "label_ocr" / "hitl_input" / ...


@dataclass
class StepCResult:
    checks: list[StandardCheck]            # 원재료 × 시험항목 조합별 결과
    overall_status: Literal["pass","fail","review_needed","no_data"]
    review_reasons: list[str]              # review_needed 사유
```

---

## 3. 처리 흐름

### 3-1. 기준규격 조회 (원재료당)

```python
for ing in ingredients:
    if ing.allow_verdict == "prohibited":
        continue  # Step A/B에서 이미 종료됐어야 함
    standards = await lookup_additive_standards(ing.name)
    # standards: list[AdditiveSpec]  — T_KOR_NM 별로 분리된 여러 row
```

### 3-2. `T_KOR_NM`별 집계

한 품목당 row가 여러 개 (함량/성상/확인시험/순도시험 등):

```python
grouped: dict[str, list[AdditiveSpec]] = defaultdict(list)
for spec in standards:
    grouped[spec.T_KOR_NM].append(spec)
```

### 3-3. 시험항목별 판정

```python
for test_category, specs in grouped.items():
    if test_category == "함량":
        result = evaluate_quantitative(specs, measured_values.get(ing.name))
    elif test_category == "성상":
        result = evaluate_qualitative(specs)   # 자동 판정 불가 → review_needed
    elif test_category in ("확인시험", "순도시험"):
        result = SpecEvaluation(kind="qualitative", requires_hitl=True)
    ...
```

### 3-4. 유효기간 필터

```python
def is_active(spec: AdditiveSpec, ref_date: date = date.today()) -> bool:
    end = spec.VALD_END_DT
    if end == "99991231":
        return True  # 무기한
    return date.fromisoformat(f"{end[:4]}-{end[4:6]}-{end[6:8]}") >= ref_date
```

최신 기준만 채택. 동일 `T_KOR_NM` 내 복수 유효 기준 있으면 `LAST_UPDT_DTM` 최신 선택.

---

## 4. 단위 정규화 & 수치 비교

```python
from utils.unit_converter import normalize_to_common_unit, parse_numeric_spec

# 기준값 파싱
if spec.MIMM_VAL is not None or spec.MXMM_VAL is not None:
    min_val, max_val = float(spec.MIMM_VAL or 0), float(spec.MXMM_VAL) if spec.MXMM_VAL else None
else:
    min_val, max_val = parse_numeric_spec(spec.SPEC_VAL)

# 단위 정규화 (기준측)
if min_val is not None:
    min_val, _ = normalize_to_common_unit(min_val, spec.UNIT_NM, density=...)
# 실측값 단위 정규화
measured_norm, _ = normalize_to_common_unit(measured.value, measured.unit, density=...)

# 비교
if min_val is not None and measured_norm < min_val:
    status = "fail"
elif max_val is not None and measured_norm > max_val:
    status = "fail"
else:
    status = "pass"
```

---

## 5. `overall_status` 규칙

| 조건 | 결과 |
|------|------|
| 모든 checks `pass` | `pass` |
| 하나라도 `fail` | `fail` (조기 종료 가능) |
| 자동 판정 불가 항목 존재 (`review_needed`) | `review_needed` |
| 기준규격 API에서 결과 없음 | `no_data` — 기준 없음으로 간주 (pass 아님, 담당자 확인) |

---

## 6. 비수치 기준 처리

- `UNIT_NM == null` + `SPEC_VAL == "적합"` / `"음성"` / `"불검출"` 등
- → `parse_non_numeric_spec()` (11번 문서 참조) 호출
- `requires_hitl=True` 결과는 `review_needed`로 누적, 담당자 판단으로 넘김

---

## 7. 식품유형 매칭

API 자체가 식품유형으로 필터하지 않음. 원재료명 기반 조회 후, 결과 내 `SPEC_VAL_SUMUP` 또는 `FNPRT_ITM_NM`에 식품유형 명시가 있으면 **해당 행만 채택**.

```python
# 예: SPEC_VAL_SUMUP 에 "유가공품의 함량은 ..." 형식
def is_applicable(spec: AdditiveSpec, food_type: str) -> bool:
    summary = (spec.SPEC_VAL_SUMUP or "") + " " + (spec.FNPRT_ITM_NM or "")
    return food_type in summary or "일반" in summary or not summary.strip()
```

식품유형 한정 표현이 없으면 **공통 기준**으로 간주 (적용).

---

## 8. 에지 케이스

| 케이스 | 처리 |
|--------|------|
| 실측값 없음 (`measured_values=None`) | 기준만 표시, `status="no_threshold"` |
| 기준 row 0건 | `StandardCheck` 생성하지 않음, `overall_status` 계산에서 제외 |
| 동일 품목 여러 식품유형 기준 | `food_type_hierarchy.food_type`으로 필터, 불명확 시 HITL |
| INJRY_YN="Y" 항목 | 결과에 경고 플래그 추가 |
| API 타임아웃 | `escalations` 누적 + Step C 결과 `no_data` |

---

## 9. 결과 포맷 예시

```python
StandardCheck(
    ingredient_name="L-아스코르브산",
    test_category="함량",
    spec_raw="85.0이상",
    spec_summary="이 품목은 ... 85.0% 이상을 함유한다",
    min_val=85.0,
    max_val=None,
    unit_original="%",
    unit_normalized="mg/kg",
    measured_value=870000,   # 87%
    measured_unit_normalized="mg/kg",
    status="pass",
    is_dangerous=False,
    law_ref="식품첨가물공전 제3장",
    vald_begin="20140101",
    vald_end="99991231",
)
```

---

## 10. 테스트 포인트

- [ ] "L-아스코르브산" + 87% 실측 → `pass` (기준 85% 이상)
- [ ] "L-아스코르브산" + 80% 실측 → `fail`
- [ ] "개미산게라닐" `"성상"` 행 → `review_needed` (자동 판정 불가)
- [ ] 실측값 `5 g/L` (음료, 비중 1.02) → `mg/kg` 변환 정확
- [ ] `VALD_END_DT="99991231"` → 기준 적용
- [ ] `VALD_END_DT`가 오늘보다 과거 → 제외
- [ ] 기준 row 0건 → `no_data`

---

## 11. 성능

- 원재료당 API 호출 1회, 병렬 가능
- `numOfRows=50` 로 한 품목의 모든 시험항목 수신 시도
- 50건 초과 시 `pageNo` 증가 순회 (실제론 한 품목당 20건 이내 예상)
- 평균 소요 목표: < 4초 (캐시 HIT 기준)

---

## 12. 남은 결정사항

- 🟡 실측값(`measured_values`) 입력 경로 → HITL-0 에서 담당자 입력? F4 라벨 OCR 자동 추출?
- 🟡 식품유형 매칭 규칙 — `SPEC_VAL_SUMUP` 자연어 파싱은 불확실, LLM 보조 여부 검토
- 🟡 `no_data` 를 최종 `overall_status`에 어떻게 반영할지 (fail로 치부 X, pass로도 X)
