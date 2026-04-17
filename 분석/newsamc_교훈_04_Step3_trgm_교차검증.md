# newsamc -> F1 추가 교훈: Step 3, trgm, 교차검증, 부위사전

> 출처: C:\GITHUB\newsamc 2차 탐색
> 분석일: 2026-04-16
> 대상: F1 Step 3(기준치), trgm RPC, 부위 검증

---

## 1. trgm 후보 선별 패턴 (fetch-trgm-candidates)

F1의 `match_ingredient()`에서 trgm RPC를 직접 호출하는 방식에 적용 가능.

### newsamc 설계 핵심

```typescript
// Supabase 클라이언트 주입 가능 → 테스트 친화
export async function fetchTrgmCandidatesFor(
  query: string,
  options: { supabaseClient?: SupabaseClient, k?: number, minSimilarity?: number }
)
```

**방어적 처리 패턴 6가지:**

| # | 패턴 | 현재 F1 |
|---|---|---|
| 1 | 빈/공백 문자열 → 빈 배열, RPC 호출 안 함 | `if not name: return _unidentified()` (부분 구현) |
| 2 | **RPC 오류 → 빈 배열 + warn (전체 중단 방지)** | **없음 — 예외 시 전체 실패** |
| 3 | data가 배열이 아닌 경우(null 등) → 빈 배열 | 없음 |
| 4 | minSimilarity 필터 (후보 품질 컷오프) | `FUZZY_SIMILARITY_THRESHOLD` 있음 |
| 5 | trim 처리 (앞뒤 공백 제거 후 RPC) | `(ing.name or "").strip()` 있음 |
| 6 | **unknown allowed_status → permitted 폴백** | `_VERDICT_MAP.get(status, "unidentified")` — **다르게 동작** |

### F1에 적용할 교훈

**#2 RPC 오류 방어**: 현재 F1의 `match_ingredient()`에서 `supabase.rpc().execute()`가 실패하면
함수 전체가 예외로 중단됨. newsamc처럼 개별 성분 RPC 실패를 빈 배열로 폴백하면
한 성분의 trgm 오류가 전체 판정을 막지 않음.

**#6 unknown status 폴백 차이**:
- newsamc: unknown → `permitted` (안전 쪽으로 폴백)
- 현재 F1: unknown → `unidentified` (불확실 쪽으로 폴백)
- F1의 현재 방식이 더 보수적이므로 **변경 불필요** — 단, 이 차이를 인지해야 함.

### 테스트 시나리오 (fetch-trgm-candidates.test.ts에서)

| # | 시나리오 | 기대 |
|---|---|---|
| T-1 | 정상 응답 → 엔트리 배열 반환 | id, name_ko, similarity 보존 |
| T-2 | 빈/공백 문자열 → 빈 배열 + RPC 호출 X | `[]`, 호출 0회 |
| T-3 | **RPC 오류 → 빈 배열 (throw 안 함)** | `[]` + warn 로그 |
| T-4 | data가 null → 빈 배열 | `[]` |
| T-5 | minSimilarity 필터 | 미달 항목 제거 |
| T-6 | k 옵션이 RPC 인자로 전달 | 호출 검증 |
| T-7 | allowed_status 정규화 (unknown → permitted) | 폴백 동작 |
| T-8 | trim 처리 후 RPC 호출 | "  쌀  " → "쌀" |

### 배치 조회 테스트 시나리오 (fetchCandidatesByName)

| # | 시나리오 | 기대 |
|---|---|---|
| T-9 | **중복 성분명 → 1번만 RPC 호출** (dedupe) | 호출 횟수 = 고유 이름 수 |
| T-10 | 빈 이름 건너뜀 | "" / "   " 제외 |
| T-11 | **한 성분 RPC 실패해도 나머지 채워짐** | bad→[], 나머지 정상 |
| T-12 | 빈 ingredients → 빈 Map + 호출 X | size=0, 호출 0회 |
| T-13 | k/minSimilarity 옵션 전파 | 각 호출에 적용 |

---

## 2. Step 3 기준치 검사 패턴 (general-limits)

F1의 `step3_standards.py`에 직접 대응.

### 매핑 함수 테스트 패턴

#### mapAdditiveLimitRow (첨가물 기준치 행 변환)

| # | 입력 | 기대 |
|---|---|---|
| S3-1 | max_ppm=1000 | max_limit="1000 ppm", category="additive" |
| S3-2 | **max_ppm=null** | max_limit="사용불가" |
| S3-3 | regulation_ref=null | undefined로 변환 |

#### mapSafetyStandardRow (안전기준 행 변환)

| # | 입력 | 기대 |
|---|---|---|
| S3-4 | standard_type="heavy_metal" | category="heavy_metal" |
| S3-5 | **unknown category** | heavy_metal 폴백 |
| S3-6 | standard_type="pesticide" | category="pesticide" |
| S3-7 | **max_limit=null** | "기준 미등록" |

#### checkGeneralFoodLimits (통합)

| # | 시나리오 | 기대 |
|---|---|---|
| S3-8 | 첨가물·안전기준 모두 없음 | overall_status="review_needed" |
| S3-9 | **Supabase가 null 반환** | 빈 배열로 처리 (에러 아님) |
| S3-10 | 데이터 없으면 에스컬레이션 없음 | escalations=[] |
| S3-11 | 실측값 미제공 → status="no_data" | 모든 checks가 no_data |
| S3-12 | no_data 상태 → violations=[] | violations은 fail만 포함 |
| S3-13 | 첨가물+안전기준 합산 | checks.length = 첨가물 수 + 안전기준 수 |

---

## 3. 주류 안전기준 (liquor-safety)

F1의 `step3_standards.py` 주류 부분에 대응.

### 알코올 도수 경계값 상수

```typescript
LIQUOR_BOUNDARY_THRESHOLDS = {
  nonAlcoholMax: 0.5,  // 이 미만 = 비알코올 (검사 불필요)
  boundaryMax: 1.0,    // 이 미만 = 경계치 → 에스컬레이션
}
```

### isAlcoholBoundary() 경계값 테스트 (10개)

| # | 도수 | 기대 | 의미 |
|---|---|---|---|
| L-1 | undefined | false | 미제공 |
| L-2 | null | false | 미제공 |
| L-3 | 0 | false | 비알코올 |
| L-4 | 0.4 | false | nonAlcoholMax 미만 |
| L-5 | **0.5** | **true** | 경계 하한 (포함) |
| L-6 | 0.7 | true | 경계 중간 |
| L-7 | 0.99 | true | 경계 상한 미만 |
| L-8 | **1.0** | **false** | boundaryMax (미포함) |
| L-9 | 5.0 | false | 확실한 주류 |

### checkLiquorSafety 테스트 (9개)

| # | 시나리오 | 기대 |
|---|---|---|
| L-10 | 4대 항목 검사 (메탄올/알데히드/퓨젤유/에탄올) | checks.length=4 |
| L-11 | 기준 미등록 시 max_limit | "기준 미등록" |
| L-12 | 위반 없음 → overall_status | review_needed |
| L-13 | 도수 미제공 → 에스컬레이션 없음 | escalations=[] |
| L-14 | 도수 0% → 에스컬레이션 없음 | escalations=[] |
| L-15 | 도수 0.5% (경계) → 에스컬레이션 | reason에 "경계치" |
| L-16 | 도수 1.0% (초과) → 에스컬레이션 없음 | escalations=[] |
| L-17 | alcohol_percentage 결과에 포함 | 값 보존 |
| L-18 | **module_id 버그 검증** | M4-3 (이전 M4-1 버그) |

### F1 현재 대비

현재 `step3_standards.py`에 주류 기준치 로직이 있지만, 알코올 도수 **경계값 처리**가
newsamc만큼 정교한지 확인 필요. 특히 0.5~1.0% 구간의 에스컬레이션 로직.

---

## 4. 교차검증 패턴 (cross-verify)

현재 F1에는 없는 모듈이지만, **정규화 매칭 + 심각도 분류** 패턴은 범용적.

### 정규화 매칭 (valuesMatch)

```typescript
// 공백/쉼표/대소문자 무시 + 양방향 포함
valuesMatch("사과 주스", "사과주스")          // true (공백)
valuesMatch("사과,물,설탕", "사과 물 설탕")   // true (쉼표)
valuesMatch("ABC Corp", "abc corp")          // true (대소문자)
valuesMatch("사과", "국산 사과주스(농축)")    // true (포함)
valuesMatch("프리미엄 사과 주스", "사과주스") // true (역포함)
```

### 심각도 분류

| 필드 | 심각도 | 에스컬레이션 |
|---|---|---|
| product_name | critical | O |
| ingredients | critical | O |
| country_of_origin | warning | X |
| net_weight | warning | X |
| manufacturer | warning | X |

**교훈**: critical + warning 동시 불일치 시 **에스컬레이션은 critical만** 생성.
→ 에스컬레이션 노이즈 방지 패턴.

### module_id 버그 수정 검증 패턴

newsamc에서 발생했던 버그: 교차검증 에스컬레이션의 `module_id`가 `M4-1`로 잘못 설정됨.
수정 후 **전용 테스트 추가**로 회귀 방지:
```typescript
it('escalation의 module_id는 M4-4 (이전 버그: M4-1)', () => {
  expect(result.escalations[0]!.module_id).toBe('M4-4');
});
```
→ **F1에서도 에스컬레이션 module_id 일관성 테스트 권장**.

---

## 5. 부위 사전 교차검증 (parts-dictionary)

F1의 `evaluate_condition()` + `validate_part_restriction()`에 직접 대응.

### 부위 사전 매칭 테스트 (matchPartKeyword, 10개)

| # | 시나리오 | 기대 |
|---|---|---|
| P-1 | 사전에 없는 원재료 (밀가루) | found=false |
| P-2 | found=false이면 allowedParts 없음 | undefined |
| P-3 | 사전에 있고 부위 미기재 (인삼) | found=true, match=false |
| P-4 | 부위 미기재 시 허용 부위 목록 반환 | allowedParts.length > 0 |
| P-5 | 인삼 + 뿌리 → match=true | 일치 |
| P-6 | 녹차 + 잎 → match=true | 일치 |
| P-7 | 인삼 + 껍질 → match=false | 불일치 |
| P-8 | 결명자 + 뿌리 → match=false | 종자/씨만 허용 |
| P-9 | 불일치에도 allowedParts 반환 | 사용자에게 힌트 |
| P-10 | **부분 문자열 매칭** ("뿌리줄기" → "뿌리" 포함 → true) | 유연 매칭 |

### crossValidateParts 테스트 (8개)

| # | 시나리오 | 기대 |
|---|---|---|
| P-11 | 빈 성분 목록 | escalations=[] |
| P-12 | 사전에 없는 원재료 | 에스컬레이션 없음 |
| P-13 | 사전에 있고 부위 일치 | 에스컬레이션 없음 |
| P-14 | 사전에 있고 부위 불일치 | 에스컬레이션 1건 |
| P-15 | 에스컬레이션 module_id=M4-1 | 정확한 모듈 |
| P-16 | reason에 원재료명+부위명 포함 | 디버깅 용이 |
| P-17 | **부위 미기재 → "미기재" 에스컬레이션** | 데이터 누락 감지 |
| P-18 | 복수 성분 중 불일치만 에스컬레이션 | 선별적 |

### F1 현재 대비

`validate_part_restriction()`은 단순 `conditions.includes(part)` 로직.
newsamc의 **부위 사전 방식**은 더 정교:
- 원재료별 허용 부위 목록을 사전으로 관리
- 부위 미기재도 감지 (현재 F1에서는 그냥 통과)
- 허용 부위 목록을 사용자에게 힌트로 반환

---

## 6. 상수 중앙화 패턴

### newsamc의 condition-patterns.ts

```typescript
export const CONDITION_PATTERNS: ConditionPattern[] = [
  { pattern: /용도|목적|사용\s*용도/i, type: 'usage_purpose' },
  { pattern: /부위|뿌리|잎|줄기|종자|열매/i, type: 'part_restriction' },
  { pattern: /함량|%|이하|이상|mg|g\/kg|ppm/i, type: 'quantity_limit' },
  { pattern: /천연|합성|자연/i, type: 'natural_synthetic' },
  { pattern: /조사|방사선|irradiat/i, type: 'irradiation' },
];
```

### F1 대비 차이점

F1의 `constants/condition_patterns.py` 패턴을 newsamc와 대조:
- newsamc는 `줄기|종자|열매` 키워드 추가 → 더 넓은 커버리지
- newsamc는 `g/kg|ppm` 추가 → 단위 기반 함량 감지
- 영문 `irradiat` 포함 → 영문 조건문 처리

**이것은 기존 파일에 기록된 E-1~E-7 테스트 케이스와 겹치므로 별도 저장 불필요.**
다만 F1의 패턴 정규식이 이 키워드들을 누락했는지 비교 확인 권장.

---

## 추가 시나리오 수 (이 파일 분)

| 영역 | 시나리오 수 | F1 적용 가능 |
|---|---|---|
| trgm 후보 선별 | 13 | 13 |
| Step 3 기준치 | 13 | 13 |
| 주류 안전기준 | 19 | 19 |
| 교차검증 | 20 | 패턴 참고 (모듈 없음) |
| 부위 사전 | 18 | 18 (기존 로직 보강) |
| **합계** | **83** | **63** (교차검증 제외) |

**이전 파일 포함 누적: 100 + 83 = 183 시나리오 (F1 적용 가능: 89 + 63 = 152)**
