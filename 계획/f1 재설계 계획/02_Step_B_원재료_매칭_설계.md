# 02. Step B — 원재료 허용여부 매칭 + 성분코드 + GMO 설계 ⭐

> 의존: [06_API_클라이언트_설계](./06_API_클라이언트_설계.md), [07_데이터_모델_변경_설계](./07_데이터_모델_변경_설계.md), [08_에러_처리_설계](./08_에러_처리_설계.md)
> 산출물: `backend/services/f1_step_b.py`

---

## 1. 목적

원재료별로 다음 3가지를 확정:
1. **허용 여부** (허용 / 조건부 / 금지 / 미확인) — 15111777 기반
2. **성분코드** (UI 표시 요구) — 15094202 기반
3. **GMO 여부** (F3 전달용) — 15111913 기반

---

## 2. 입출력 계약

```python
async def run_step_b(
    ingredients: list[Ingredient],
) -> StepBResult:
    """3개 API 병렬 호출 → 원재료별 집계."""


@dataclass
class StepBResult:
    enriched_ingredients: list[Ingredient]   # allow_verdict, component_code, is_gmo, ... 채움
    unidentified: list[str]                  # API에서 찾지 못한 원재료명
    conditional: list[Ingredient]            # restricted 원재료 (HITL-1 표시)
    gmo_ingredients: list[str]               # GMO=Y 원재료명 (F3 전달)
    api_call_stats: dict[str, int]
```

---

## 3. 매칭 파이프라인

### 3-1. 이름 정규화 (선행 처리)

```python
def normalize_name(raw: str) -> str:
    name = raw.strip()
    name = re.sub(r"\s+", " ", name)       # 다중 공백 단일화
    name = name.replace("·", ",")          # 구분자 통일
    return name
```

### 3-2. 3개 API 병렬 호출

```python
results = await asyncio.gather(
    *(lookup_ingredient(normalize_name(i.name)) for i in ingredients),    # 15111777
    *(lookup_component_code(normalize_name(i.name)) for i in ingredients),# 15094202
    *(lookup_gmo_flag(normalize_name(i.name)) for i in ingredients),      # 15111913
    return_exceptions=True,
)
```

### 3-3. 원재료별 집계

각 원재료에 대해:

```python
for ing in ingredients:
    allow_hits = await lookup_ingredient(ing.name)   # list[IngredientInfo]
    comp_hit = await lookup_component_code(ing.name) # Optional[ComponentInfo]
    gmo = await lookup_gmo_flag(ing.name)            # Optional[bool]

    ing.allow_verdict = resolve_verdict(allow_hits)
    ing.restriction_condition = primary_condition(allow_hits)
    ing.edible_parts = primary_parts(allow_hits)
    ing.component_code = comp_hit.CPNT_CD if comp_hit else None
    ing.is_gmo = gmo
    ing.source_api = "15111777,15094202,15111913"
```

---

## 4. `allow_verdict` 판정 규칙

```python
def resolve_verdict(hits: list[IngredientInfo]) -> Literal["allowed","restricted","prohibited","unidentified"]:
    if not hits:
        return "unidentified"

    # 다건 매칭 시: 가장 제한적인 결과 채택 (prohibited > restricted > allowed)
    has_prohibited = any(h.EDIBLE_INFO == "불가" or h.EDIBLE_N == "o" for h in hits)
    if has_prohibited:
        return "prohibited"

    has_condition = any((h.CHRTR_INFO_CONT or "").strip() for h in hits)
    if has_condition:
        return "restricted"

    has_allowed = any(h.EDIBLE_INFO == "가능" or h.EDIBLE_Y == "o" for h in hits)
    if has_allowed:
        return "allowed"

    return "unidentified"
```

**우선순위 근거:** 안전성 우선. 동명이인 중 한 쪽이라도 제한이면 제한으로 취급 → HITL-1 검토.

---

## 5. 이름 매칭 전략

15111777 API에 검색 파라미터가 제공되면 그대로 사용. 제공되지 않으면 **전체 스캔은 금지**, 대신:

| 전략 | 설명 |
|------|------|
| **1차 정확 일치** | `INGD_NM == normalized_name` |
| **2차 이명 일치** | `NKNM_NM` (콤마 분리) 중 하나와 일치 |
| **3차 학명 일치** | `SCNNM_NM` 부분 일치 (`food_ingredient.scientific_name` 이 F0에서 제공될 때만) |
| **fallback** | Levenshtein 거리 ≤ 2 (짧은 이름은 ≤ 1) — 후보 다건이면 모두 검토 후 안전측 채택 |

> ⚠️ **퍼지 매칭 오남용 금지:** 4차 fallback은 편집거리 측정만 하고 **자동 확정 금지**. 후보가 하나라도 있으면 HITL-1로 올려서 담당자가 고르게 함.

---

## 6. 15094202 성분코드 매칭

- `KOR_NM` 앞 공백 `.strip()` 필수
- 1건 초과 매칭 시: `CPNT_LCLS_CD_NM` 우선순위 `식품원료 > 식품첨가물 > 기타`
- `USE_DIVS_CD_NM == "사용가능"` 우선
- 찾지 못하면 `component_code = None` → UI에 `-` 표시

---

## 7. 15111913 GMO 조회

- `ORM_STD_NM == normalized_name` 정확 일치만 (1,143,598건 대용량이므로 퍼지 금지)
- `GMO_YN == "Y"` → `is_gmo=True`
- `GMO_YN == "N"` → `is_gmo=False`
- 미등록 / API 장애 → `is_gmo=None`

**F3 전달 로직 (이후 F1 결과 합치기):**
```python
gmo_ingredients = [ing.name for ing in enriched_ingredients if ing.is_gmo]
```

---

## 8. 에지 케이스

| 케이스 | 처리 |
|--------|------|
| 원재료 `sub_ingredients` 포함 | 하위 성분도 Step B에 투입 (flatten) |
| 합성향료 명시 (`"합성향료"`, `"synthetic flavor"`) | 자동 판정 금지 → HITL-1 |
| 원재료명이 "기타첨가물" 등 포괄 표현 | `unidentified` 처리 → HITL-1 |
| INS 번호만 주어짐 (이름 없음) | 15094202 `CPNT_CD` 역조회 (`CPNT_CD` 검색 파라미터) |
| 동일 이름 다건 매칭 (동명이인) | 안전측 채택 + HITL-1 경고 |

---

## 9. 조기 종료 조건

```python
if any(ing.allow_verdict == "prohibited" for ing in ingredients):
    # → 파이프라인 Step C/D skip, 즉시 "수입불가" 결과 저장
```

---

## 10. 테스트 포인트

- [ ] "대두" 입력 → allow_verdict="allowed", is_gmo 값 채워짐
- [ ] "아편" 입력 → allow_verdict="prohibited", 조기 종료
- [ ] "인삼" 입력 (사용 부위 제한 있는 경우) → allow_verdict="restricted", restriction_condition 채워짐
- [ ] `sub_ingredients` 안의 원료도 평탄화돼 검사됨
- [ ] 동명이인 원재료 → 가장 제한적 verdict 채택
- [ ] 15094202 `KOR_NM` 앞 공백 자동 제거
- [ ] 15111913 미등록 원재료 → `is_gmo=None`, 파이프라인 진행 계속

---

## 11. 성능

- 평균 원재료 수 10건 기준:
  - 병렬 호출 총 30 request → 캐시 히트율 70% 가정 시 실제 HTTP 10~15건
  - 평균 지연 목표: < 5초

- 원재료 > 20건 케이스: 배치 분할 (10건씩) + 순차 처리 → 진행률 표시

---

## 12. 남은 결정사항

- 🟡 Levenshtein 임계치 (2 vs 3)
- 🟡 "합성향료" 자동 감지 키워드 셋 (`constants/synthetic_flavors.py`로 분리?)
- 🟡 동명이인 원재료 다건 매칭 시 UI 표시 방식 (모두 표시? 하나만?)
