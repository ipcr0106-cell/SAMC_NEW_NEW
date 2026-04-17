# newsamc -> F1 유틸리티 패턴 (최종)

> 출처: C:\GITHUB\newsamc 3차 탐색
> 분석일: 2026-04-16

---

## 1. withRetry — RPC/외부 호출 재시도 유틸

F1의 Supabase RPC 호출(`search_f1_ingredients_trgm` 등)에 적용 가능.
현재 F1은 RPC 오류 시 전체 실패하며 재시도 메커니즘이 없음.

### 설계

```typescript
async function withRetry<T>(
  fn: () => Promise<T>,
  options: {
    maxRetries?: number;      // 기본 3
    baseDelayMs?: number;     // 지수 백오프 기준
    isNonRetryable?: (err: Error) => boolean;  // 즉시 실패 조건
  }
): Promise<T>
```

### 테스트 시나리오 (10개)

| # | 시나리오 | 기대 |
|---|---|---|
| R-1 | 성공하는 함수 → 즉시 반환, 1회 호출 | result="success", calls=1 |
| R-2 | 1회 실패 후 성공 → 최종 결과 반환 | result="ok", calls=2 |
| R-3 | maxRetries만큼 재시도 (3) | calls=4 (첫 시도+재시도 3) |
| R-4 | 초과 시 마지막 에러 throw | "영구 오류" |
| R-5 | maxRetries=0 → 재시도 없이 즉시 실패 | calls=1 |
| R-6 | **isNonRetryable 해당 → 즉시 실패** | "치명적 오류", calls=1 |
| R-7 | isNonRetryable 미해당 → 정상 재시도 | calls=2 |
| R-8 | 기본 옵션(maxRetries:3) 적용 | calls=4 |
| R-9 | Error 아닌 값 throw → Error로 래핑 | "문자열 에러" |
| R-10 | 성공 시 반환값 타입 유지 | {id:1, name:"테스트"} |

### F1 적용 포인트

```python
# 현재 F1 (재시도 없음, 오류 시 전체 중단):
result = supabase.rpc("search_f1_ingredients_trgm", {"q": name, "k": 1}).execute()

# 적용 후:
result = with_retry(
    lambda: supabase.rpc("search_f1_ingredients_trgm", {"q": name, "k": 1}).execute(),
    max_retries=2,
    is_non_retryable=lambda e: "invalid input" in str(e)  # 입력 오류는 재시도 무의미
)
```

---

## 2. normalizeForComparison — 비교용 정규화 (교차검증/금지원료 공통)

F1의 BUG-1(금지원료 부분매칭)과 향후 교차검증 모듈에 적용.

### newsamc 정규화 규칙

```typescript
function normalizeForComparison(s: string): string {
  // 1. 쉼표, 중점(·), 하이픈, 괄호(반각/전각) 제거
  // 2. 모든 공백 제거
  // 3. 영문 소문자
}
```

### 테스트 시나리오 (5개)

| # | 입력 | 기대 출력 |
|---|---|---|
| N-1 | "사과 주스" | "사과주스" |
| N-2 | "사과,물·설탕-(첨가)" | "사과물설탕첨가" |
| N-3 | "사과（농축）" (전각 괄호) | "사과농축" |
| N-4 | "ABC Corp" | "abccorp" |
| N-5 | "" | "" |

### 현재 F1 BUG-1 수정에 활용

현재 `check_forbidden_first()`의 문제:
```python
names_set = set(names)  # 정확 일치만
```

newsamc 스타일 적용:
```python
def normalize_for_comparison(s: str) -> str:
    import re
    s = re.sub(r'[,·\-()（）\[\]{}]', '', s)
    s = re.sub(r'\s+', '', s)
    return s.lower()
```

---

## 3. NFC 정규화 — 한글 자모 조합 엣지 케이스

### 문제

OCR이나 외부 시스템에서 한글이 **자모 분리 상태**(NFD)로 들어올 수 있음:
- NFD: `ㅅ + ㅔ + ㅊ` (3바이트)
- NFC: `세척` (완성형, 1바이트)

정규화 없이 비교하면 동일 한글이 불일치로 판정됨.

### newsamc 처리

```typescript
function normalizeProcessName(s: string): string {
  // ... 공백/제어문자 정리 후
  return result.normalize('NFC');  // 한글 완성형으로 통일
}
```

### F1 적용

```python
import unicodedata
def normalize_korean(s: str) -> str:
    return unicodedata.normalize('NFC', s)
```

F1의 모든 문자열 비교 전에 NFC 정규화를 넣으면 안전.
특히 `check_forbidden_first()`, `match_ingredient()`.

---

## 4. 에스컬레이션 메시지 테스트

### 패턴

에스컬레이션 메시지가 필수 정보를 포함하는지 검증:

```typescript
it('lowConfidence: 점수 + 임계값 포함 (소수점 2자리)', () => {
  const msg = ESCALATION_MESSAGES.M4_1.lowConfidence(0.7234, 0.8);
  expect(msg).toContain('0.72');  // 점수
  expect(msg).toContain('0.8');   // 임계값
});
```

**교훈**: 에스컬레이션 메시지를 템플릿 함수로 만들고,
생성된 메시지에 디버깅용 수치가 포함되는지 테스트.
현재 F1은 f-string으로 인라인 생성하므로 오타나 누락 검증 불가.

---

## 탐색 종료 선언

**이 파일로 newsamc의 F1 적용 가능 교훈 탐색을 종료합니다.**

### 미탐색 영역과 제외 사유

| 영역 | 파일 | 제외 사유 |
|---|---|---|
| 식품유형 추천 | `verification/m4-2/` | 기능2(아람) 담당 |
| 첨가물 추천 | `verification/m4-3/` | F1 범위 밖 |
| 이미지/텍스트 위반 | `verification/m5-1/` | 별도 기능 |
| 제조공정 검증 | `verification/m5-2/` | 별도 기능 |
| 라벨 생성/검증 | `verification/m6/` | 별도 기능 |
| 위자드 로직 | `wizard/` | 프론트엔드 |
| Auth/Role | `auth/` | 공통 인프라 |
| 업로드 서비스 | `upload/` | 공통 인프라 |

**이들 영역에서 F1에 충분한 효용이 있는 추가 교훈은 없습니다.**

### 최종 누적 통계

| 파일 | 시나리오 수 |
|---|---|
| 01_아키텍처패턴 | 8가지 패턴 |
| 02_테스트케이스카탈로그 | 100 시나리오 |
| 03_버그갭_신규기능 | 2 버그 + 6 갭 |
| 04_Step3_trgm_교차검증 | 83 시나리오 |
| 05_유틸리티패턴 (이 파일) | 15 시나리오 + 2 패턴 |
| **합계** | **198 시나리오, 10 패턴, 2 버그, 6 갭** |
