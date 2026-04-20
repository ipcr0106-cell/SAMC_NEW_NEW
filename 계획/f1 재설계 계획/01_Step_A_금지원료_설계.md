# 01. Step A — 금지원료 체크 설계

> 의존: [06_API_클라이언트_설계](./06_API_클라이언트_설계.md), [07_데이터_모델_변경_설계](./07_데이터_모델_변경_설계.md), [08_에러_처리_설계](./08_에러_처리_설계.md)
> 산출물: `backend/services/f1_step_a.py`

---

## 1. 목적

원재료 리스트에 **한국에서 수입 금지된 원료**가 하나라도 포함되면 즉시 수입불가 처리. 다른 Step보다 먼저 실행되어 불필요한 하위 처리를 차단.

---

## 2. 입출력 계약

```python
async def run_step_a(
    ingredients: list[Ingredient],
) -> StepAResult:
    """2중 안전망: Supabase DB + data.go.kr API 교차 확인."""


@dataclass
class StepAResult:
    forbidden_hits: list[ForbiddenHit]     # 매칭된 금지원료 (원재료명 + 사유 + 근거)
    stopped: bool                           # True → 즉시 파이프라인 종료
    law_refs: list[str]                    # 금지 근거 법령 식별자
    api_errors: list[str]                  # 교차확인 시 API 장애 기록 (차단 X)


@dataclass
class ForbiddenHit:
    ingredient_name: str
    matched_name: str         # DB 또는 API 상의 원료명
    source: Literal["db", "api"]
    reason: str               # "식품원료 사용 불가", "유독성분 포함" 등
    law_ref: Optional[str]
```

---

## 3. 2중 안전망 로직

### 3-1. DB 조회 (`f1_forbidden_ingredients`)

```python
# 1차: 기존 Supabase DB
hits_db = sb.table("f1_forbidden_ingredients")\
    .select("*")\
    .in_("name_ko", [i.name.strip() for i in ingredients])\
    .execute().data
```

### 3-2. API 교차확인 (15111777)

```python
# 2차: data.go.kr 수입식품 원료정보 API
#   EDIBLE_INFO == "불가" 또는 EDIBLE_N == "o" 항목 필터
for ing in ingredients:
    api_hits = await lookup_ingredient(ing.name)
    for r in api_hits:
        if r.EDIBLE_INFO == "불가" or r.EDIBLE_N == "o":
            ...
```

### 3-3. 합집합 → 한 건이라도 hit 시 stop

```python
all_hits = hits_db + hits_api
if all_hits:
    return StepAResult(forbidden_hits=all_hits, stopped=True, law_refs=..., api_errors=[])
```

---

## 4. 우선순위 규칙

| 시나리오 | 결과 |
|---------|------|
| DB만 hit | `source="db"` — API는 참고만 |
| API만 hit | `source="api"` + 경고 배너 ("DB 미등록 — 최신 API 기준 금지") |
| 둘 다 hit | 동일 항목 중복 제거 (name 기준), `source="db"` 우선 |
| API 장애 + DB만 조회 | `api_errors`에 기록, DB 결과만 반환 (stop 여부는 DB 기준) |

---

## 5. 에지 케이스

| 케이스 | 처리 |
|--------|------|
| 원재료명 앞뒤 공백 | `.strip()` 필수 |
| 대소문자 / 한영 혼용 | DB: lowercase 비교 / API: `NKNM_NM` 콤마 분리 후 OR 매칭 |
| 복합 원재료 (`sub_ingredients`) | 하위 원료도 평탄화하여 검사 |
| API 응답이 동명이인 다건 | 모두 확인 → 하나라도 "불가"면 hit |
| `f1_forbidden_ingredients` 미등록이지만 관련 법령 업데이트 | API 결과 우선 (단 HITL-1 경고) |

---

## 6. 결과 저장 포맷

`Feature1Output` 확장:

```python
{
  "forbidden_hits": [
    {
      "ingredient_name": "아편씨",
      "matched_name": "아편",
      "source": "db",
      "reason": "마약류관리에 관한 법률 제2조",
      "law_ref": "law-001"
    }
  ],
  "stopped_at_step_a": true
}
```

프론트 `ForbiddenAlert` 컴포넌트에 그대로 노출 (기존 컴포넌트 재사용).

---

## 7. 테스트 포인트

- [ ] DB hit 단독 → 즉시 stop, API 호출 없음 (빠른 경로)
- [ ] API hit 단독 → "DB 미등록" 경고 포함
- [ ] 동일 항목 DB+API hit → 중복 제거
- [ ] API 장애 → `api_errors` 기록, DB 결과로만 판정
- [ ] 원재료명 공백/대소문자 무관 매칭
- [ ] 복합 원재료 하위 성분도 검사

---

## 8. 성능

- Step A는 **가장 먼저 실행**, 금지원료 hit 시 Step B/C/D 전체 skip
- DB 조회 1회 + API 병렬 호출 N건 (원재료 수)
- 평균 소요 목표: < 2초 (캐시 히트 가정)

---

## 9. 남은 결정사항

- 🟡 API 결과와 DB 결과 상충 시 (API=가능, DB=금지) 어느 쪽 신뢰? → 기본 DB 우선 + HITL 경고
- 🟡 `f1_forbidden_ingredients` 최초 seed 재검증 필요 (기존 운영 데이터 잔재 여부)
