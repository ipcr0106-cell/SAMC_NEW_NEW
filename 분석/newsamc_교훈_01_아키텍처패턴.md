# newsamc -> F1 아키텍처 교훈

> 출처: C:\GITHUB\newsamc (TypeScript/Next.js 리라이트)
> 분석일: 2026-04-16
> 대상: SAMC_NEW_NEW/backend F1 (Python/FastAPI)

---

## 1. Loader/Adapter 패턴 (영향도: 최고)

### newsamc 설계

```
ForbiddenIngredientLoader (interface)
  ├── SupabaseForbiddenLoader  (운영: Supabase에서 조회)
  └── inMemoryLoader           (테스트: 배열을 그대로 반환)
```

**핵심**: 룰 코드(`forbidden-ingredient-rule.ts`)는 데이터 소스를 모름.
`loader.loadAll()` 만 호출 -> 테스트에서 DB 없이 `inMemoryLoader([...])` 주입.

### 현재 F1 문제점

`step1_ingredients_check.py`의 `check_forbidden_first()`:
```python
# 함수 안에서 직접 Supabase 호출 -> DB 없이 테스트 불가능
supabase = get_supabase()
rows = supabase.table("f1_forbidden_ingredients").select(...).execute().data
```

### 적용 방안

```python
# 1) 프로토콜(인터페이스) 정의
class ForbiddenLoader(Protocol):
    def load_all(self) -> list[dict]: ...

# 2) 운영용 구현
class SupabaseForbiddenLoader:
    def load_all(self):
        return get_supabase().table("f1_forbidden_ingredients")...

# 3) 테스트용 구현
class InMemoryForbiddenLoader:
    def __init__(self, rows): self._rows = rows
    def load_all(self): return self._rows

# 4) 기존 함수에 loader 주입
def check_forbidden_first(ingredients, loader: ForbiddenLoader = None):
    loader = loader or SupabaseForbiddenLoader()
    rows = loader.load_all()
    ...
```

**동일 패턴을 `match_ingredient()`에도 적용 가능** -> AllowedIngredientLoader

---

## 2. Rule-based Evaluator 패턴

### newsamc 설계

```typescript
interface EligibilityRule {
  id: string;
  name: string;
  evaluate(input: EligibilityInput): Promise<RuleResult>;
}

// 평가기: 룰 배열을 받아 병렬 실행 -> 집계
async function evaluate(rules: EligibilityRule[], input): Promise<EligibilityResult> {
  const results = await Promise.all(rules.map(r => r.evaluate(input)));
  const blocked = results.flatMap(r => r.blocked);
  return { eligible: blocked.length === 0, blocked, rule_results: results };
}
```

**장점**: 룰 추가 시 코드 수정 없이 배열에 추가만 하면 됨.
현재 F1의 `run_step1()`은 모든 로직이 한 함수에 직접 코딩됨.

### 적용 시점

현재 F1은 forbidden 게이트 1개뿐이므로 즉시 적용은 과도할 수 있음.
**원산지 제한, OEM 제한** 등 룰이 추가될 때 도입 권장.

---

## 3. 에스컬레이션 모듈 분리

### newsamc 설계 (3-layer)

```
thresholds.ts          -> 상수만 (M4-1: 0.8, M4-2: 0.75, M6: maxRetries 3)
escalation-messages.ts -> 메시지 템플릿
evaluate.ts            -> 판정 로직 (shouldEscalate + trigger_type + reason)
```

**특수 트리거**: 신뢰도와 무관하게 강제 에스컬레이션
- `health_functional_suspect` (건강기능식품 의심)
- `dual_listed_ingredient` (허용/금지 양쪽에 등재)
- `unknown_functional_ingredient` (미확인 기능성 원료)

### 현재 F1 문제점

에스컬레이션이 `run_ingredient_match_chain()` 안에서 인라인 dict 생성:
```python
escalations.append({
    "module_id": "F1",
    "trigger_type": "prohibited_detected",
    "reason": f'금지 원료 감지: "{ing.name}"',
})
```

임계값이 코드에 흩어져 있고, 특수 트리거 개념이 없음.

### 적용 방안

```python
# escalation_config.py
THRESHOLDS = {
    "F1": {"confidence": 0.8},
}
SPECIAL_TRIGGERS = {"health_functional_suspect", "dual_listed_ingredient"}

# escalation_evaluate.py
def evaluate_f1(confidence, special_trigger=None):
    if special_trigger in SPECIAL_TRIGGERS:
        return {"should_escalate": True, "trigger_type": special_trigger, ...}
    if confidence < THRESHOLDS["F1"]["confidence"]:
        return {"should_escalate": True, "trigger_type": "low_confidence", ...}
    return {"should_escalate": False}
```

---

## 4. LLM 추천 결과 Sanitize 패턴 (recommend-ingredient)

### newsamc 핵심 설계

LLM에게 원재료 매칭 추천을 받되, **3단계 방어**:

1. **후보 풀 제한**: 성분별로 trgm 유사도 상위 후보만 프롬프트에 제공
2. **응답 파싱 방어**: JSON 파싱 실패/성분 누락 시 `no_match_likely` 패딩
3. **Sanitize**: LLM 응답의 `id`가 해당 성분 후보 풀에 있는지 검증 -> 교차 오염 필터 + DB 정본으로 `name_ko/allowed_status/conditions` 강제 교체

```typescript
// LLM이 "쌀" 후보에 "설탕" 풀의 id를 반환하면 -> 필터됨
// LLM이 name_ko를 잘못 말하면 -> DB 정본으로 교체
```

### 현재 F1 대응

F1은 현재 LLM 추천을 사용하지 않지만, `unidentified` 원료에 대해 도입 시 이 패턴 필수.
**핵심 원칙**: LLM 출력을 절대 그대로 신뢰하지 않고, DB 정본으로 검증/교체.

---

## 5. 금지원료 Normalize + 양방향 Substring

### newsamc 매칭 로직

```typescript
function normalize(s: string): string {
  return s.replace(/\s+/g, '').toLowerCase();
}

// 양방향 substring: 입력이 DB를 포함하거나, DB가 입력을 포함하면 hit
const hit = candidates.some(c => ingNorm.includes(c) || c.includes(ingNorm));
```

**예시**: 입력 "마리화나 추출물" → normalize → "마리화나추출물"
DB alias "마리화나" → normalize → "마리화나"
→ "마리화나추출물".includes("마리화나") = true -> **차단**

### 현재 F1 매칭 로직

```python
names_set = set(names)
hits = [r for r in rows
        if r["name_ko"] in names_set
        or any(a in names_set for a in (r["aliases"] or []))]
```

**정확 일치만** → "마리화나 추출물"은 alias "마리화나"와 일치하지 않아 **탈출**.

---

## 6. 조건 유형 분류 (Condition Patterns)

### newsamc 분류 체계 (6가지)

| 유형 | 키워드 패턴 | 예시 |
|---|---|---|
| `quantity_limit` | 함량, %, mg, 이하 | "150mg 이하" |
| `part_restriction` | 부위, 뿌리, 잎, 만 | "뿌리만 사용 가능" |
| `usage_purpose` | 용도 | "식품 첨가물 용도로만" |
| `natural_synthetic` | 천연, 합성 | "천연향료만 허용" |
| `irradiation` | 방사선, 조사, irradiation | "방사선 조사 금지" |
| `ambiguous` | 위 미해당 | "특수 승인 필요" |

### 현재 F1 대응

`constants/condition_patterns.py`의 `classify_condition_type()` — 유사 구현 있음.
테스트만 없는 상태. newsamc 테스트 케이스를 그대로 포트 가능.

---

## 7. OCR 텍스트 정규화

### newsamc normalizeText 규칙

1. CRLF → LF
2. 제어문자 제거 (\x00~\x08, \x0B, \x0C, \x0E~\x1F)
3. 탭 → 공백
4. 연속 공백 축소 (2+ → 1)
5. 3줄+ 연속 줄바꿈 → 2줄
6. 앞뒤 trim

### 현재 F1 대응

F0(파싱) 단계에서 처리할 가능성 높음. F1은 파싱된 원재료명을 받으므로
직접 적용보다는 **F0 담당자에게 공유**하는 것이 적절.

---

## 8. 단위 변환 (Unit Converter)

### newsamc 지원 변환

| 원본 | 변환 | 예시 |
|---|---|---|
| oz → g | 28.3495 | "12 oz" → "340.19g (12 oz)" |
| lb/lbs → g | 453.592 | "2 lb" → "907.18g" |
| fl oz → ml | 29.5735 | "8 fl oz" → "236.59ml" |
| gal/gallon → ml | 3785.41 | "1 gal" → "3785.41ml" |
| °F → °C | (F-32)*5/9 | "212 °F" → "100°C" |

### 현재 F1 대응

`backend/utils/unit_converter.py` 존재 (F3 feature용).
F1의 Step 3(기준치 비교) 시 단위 불일치 문제에 활용 가능.
