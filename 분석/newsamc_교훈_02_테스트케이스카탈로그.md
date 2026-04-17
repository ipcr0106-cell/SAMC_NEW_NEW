# newsamc -> F1 테스트 케이스 카탈로그

> 출처: C:\GITHUB\newsamc 테스트 파일들
> 분석일: 2026-04-16
> 용도: F1 pytest 작성 시 시나리오 체크리스트

---

## A. 금지원료 게이트 (check_forbidden_first)

출처: `src/lib/eligibility/__tests__/evaluator.test.ts` (9개)

| # | 시나리오 | 기대 결과 | F1 현재 |
|---|---|---|---|
| A-1 | 차단 사유 없는 일반 원료 | eligible=true, blocked=[] | 미검증 |
| A-2 | 정본명(name_ko) 직접 일치 | blocked에 해당 원료 포함 | 미검증 |
| A-3 | **alias 일치** ("마리화나" → "대마초") | blocked, matched="대마초" | **버그: 부분매칭 미지원** |
| A-4 | **영문 alias 대소문자/공백 무시** ("Kava Kava extract") | blocked, matched="카바카바" | **버그: normalize 없음** |
| A-5 | 다중 차단 누적 (대마 + 카바) | blocked 2건 | 미검증 |
| A-6 | **동일 원재료 중복 매칭 방지** (DB에 "대마"와 "대마초" 모두 있을 때) | blocked 1건만 | 구현됨(seen set), 미검증 |
| A-7 | 빈 입력 (ingredients=[]) | eligible=true | 미검증 |
| A-8 | 룰 0개 (게이트 미설정) | 통과 | 해당 없음 (단일 룰) |
| A-9 | source_law/reason이 BlockReason에 보존됨 | law_source, reason 필드 존재 | 미검증 |

### 테스트 데이터 (newsamc에서 사용)

```python
FORBIDDEN_SEED = [
    {"name_ko": "대마초", "name_en": "Cannabis",
     "aliases": ["대마", "마리화나", "THC"],
     "category": "drug", "law_source": "마약류 관리에 관한 법률",
     "reason": "마약류 관리법상 수입 금지"},
    {"name_ko": "카바카바", "name_en": "Kava kava",
     "aliases": ["카바"],
     "category": "unauthorized", "law_source": "식약처 고시",
     "reason": "간 독성"},
]
```

---

## B. 5단계 매칭 체인 (match_ingredient / run_ingredient_match_chain)

출처: `src/lib/judgment/m4-1/__tests__/match-chain.test.ts` (11개)

| # | 시나리오 | 기대 결과 | F1 함수 |
|---|---|---|---|
| B-1 | 정확 매칭 성공 → permitted | verdict="permitted", confidence=1.0, method="exact_name" | `match_ingredient()` |
| B-2 | 정확 매칭 → restricted + conditions 보존 | verdict="restricted", conditions="150mg 이하" | `match_ingredient()` |
| B-3 | 정확 매칭 → prohibited → 에스컬레이션 생성 | escalations에 module_id="F1" 포함 | `run_ingredient_match_chain()` |
| B-4 | 정확 실패 → 퍼지 매칭 성공 | confidence=0.7, method="fuzzy" | `match_ingredient()` |
| B-5 | 정확+퍼지 모두 실패 → unidentified | verdict="unidentified", confidence=0, method=None | `match_ingredient()` |
| B-6 | 미확인 원료 → 에스컬레이션 생성 | escalations에 "미확인 원료" reason 포함 | `run_ingredient_match_chain()` |
| B-7 | 빈 배열 → 카운트 전부 0 | total=0, permitted=0, escalations=[] | `run_ingredient_match_chain()` |
| B-8 | 혼합 결과 집계 (permitted+prohibited+unidentified) | permitted=1, prohibited=1, unidentified=1, escalations=2건 | `run_ingredient_match_chain()` |
| B-9 | **DB의 알 수 없는 allowed_status → unidentified 매핑** | verdict="unidentified" (fallback) | `_VERDICT_MAP` |
| B-10 | 합성향료 → unidentified + synthetic_flavor 에스컬레이션 | trigger_type="synthetic_flavor" | `run_ingredient_match_chain()` |
| B-11 | 빈 이름("") → unidentified | verdict="unidentified" | `match_ingredient()` |

---

## C. 복합원재료 재귀 검증 (evaluate_compound_ingredients)

출처: `src/lib/judgment/m4-1/__tests__/compound-evaluator.test.ts` (5개)

| # | 시나리오 | 기대 결과 |
|---|---|---|
| C-1 | sub_ingredients 없는 단순 성분 | subResults=[], escalations=[] |
| C-2 | 빈 배열 | subResults=[] |
| C-3 | 하위 성분 정상 매칭 | subResults에 하위 결과 포함 |
| C-4 | **하위 금지 성분 → 추가 에스컬레이션** | reason에 "복합원재료 X의 하위 성분" 포함 |
| C-5 | 복수 복합원재료 → 각각 매칭 체인 호출 | 호출 횟수 = 복합원재료 수 |

---

## D. 조건부(restricted) 평가 (evaluate_conditional_ingredients)

출처: `compound-evaluator.test.ts` 중 조건 평가 부분 (11개)

| # | 시나리오 | 기대 결과 |
|---|---|---|
| D-1 | restricted + conditions → 조건 평가 생성 | evals 1건, condition_type 정확 |
| D-2 | conditions 없는 restricted → 평가 제외 | evals 0건 |
| D-3 | permitted → 조건 평가 없음 | evals 0건 |
| D-4 | prohibited → 조건 평가 없음 | evals 0건 |
| D-5 | **부위 조건 + part 일치** ("뿌리만 사용" + part="뿌리") | is_satisfied=true |
| D-6 | **부위 조건 + part 불일치** ("뿌리만 사용" + part="잎") | is_satisfied=false |
| D-7 | **함량 조건 + percentage 있음** → null (Step 3 위임) | is_satisfied=null, evidence 포함 |
| D-8 | 천연/합성 조건 → natural_synthetic 유형 | condition_type="natural_synthetic" |
| D-9 | 방사선 조사 조건 → irradiation 유형 | condition_type="irradiation" |
| D-10 | 패턴 미일치 → ambiguous 유형 | condition_type="ambiguous", is_satisfied=null |
| D-11 | ingredients에 해당 성분 없을 때 → 기본값 사용 | 에러 없이 처리 |

---

## E. 조건 유형 분류 (classify_condition_type)

출처: `compound-evaluator.test.ts` 중 classifyConditionType (7개)

| # | 입력 | 기대 유형 |
|---|---|---|
| E-1 | "식품 첨가물 용도로만 사용" | usage_purpose |
| E-2 | "뿌리만 사용 가능" / "잎 부위 제한" | part_restriction |
| E-3 | "150mg 이하" / "5% 미만" / "함량 제한 있음" | quantity_limit |
| E-4 | "천연향료만 허용" | natural_synthetic |
| E-5 | "방사선 조사 금지" / "irradiation prohibited" | irradiation |
| E-6 | "특수 승인 필요" | ambiguous |
| E-7 | "" (빈 문자열) | ambiguous |

---

## F. 부위 제한 검증 (validate_part_restriction)

출처: `compound-evaluator.test.ts` 중 validatePartRestriction (4개)

| # | conditions | part | 기대 |
|---|---|---|---|
| F-1 | "뿌리만 사용" | "뿌리" | true |
| F-2 | "뿌리만 사용" | "잎" | false |
| F-3 | "Root only" | "root" / "ROOT" | true (대소문자 무시) |
| F-4 | "뿌리" | "" | true (빈 문자열은 모든 곳에 포함) |

---

## G. 에스컬레이션 판정 (evaluateM4_1 등)

출처: `src/lib/escalation/__tests__/evaluate.test.ts` (18개)

### G-1. M4-1 성분 매칭 (7개)

| # | 조건 | 기대 |
|---|---|---|
| G-1a | 신뢰도 0.9 (>= 0.8) | shouldEscalate=false |
| G-1b | 신뢰도 0.8 (정확히 임계값) | shouldEscalate=false |
| G-1c | 신뢰도 0.79 (< 0.8) | shouldEscalate=true, trigger="low_confidence" |
| G-1d | **특수: health_functional_suspect** (신뢰도 0.99) | shouldEscalate=true (무조건) |
| G-1e | **특수: dual_listed_ingredient** | shouldEscalate=true |
| G-1f | **특수: unknown_functional_ingredient** | shouldEscalate=true |
| G-1g | 특수 트리거 + 낮은 신뢰도 → 특수가 우선 | trigger_type=특수 트리거 |

### G-2. M4-2 식품유형 분류 (7개)

| # | 조건 | 기대 |
|---|---|---|
| G-2a | 정상 (결과 5건, 신뢰도 0.9, 비동점) | shouldEscalate=false |
| G-2b | 결과 0건 | trigger="no_match" |
| G-2c | 신뢰도 0.74 (< 0.75) | trigger="low_confidence" |
| G-2d | 신뢰도 0.75 (정확히 임계값) | shouldEscalate=false |
| G-2e | 동점 | trigger="low_confidence", reason에 "동점" |
| G-2f | 결과 0건 + 낮은 신뢰도 → no_match 우선 | trigger="no_match" |
| G-2g | 결과 1건 (최소 충족) | shouldEscalate=false |

### G-3. M5-1 표시검증 (4개)

| G-3a | 트리거 없음 | false |
| G-3b | uncertain | true |
| G-3c | alcohol_boundary | true, reason에 "알코올" |
| G-3d | 관계없는 트리거(low_confidence) | false |

---

## H. 후처리: GMO / 알레르겐 / 필수서류

출처: `src/lib/judgment/m4-1/__tests__/post-processing.test.ts` (18개)

### H-1. GMO 대상 식별 (9개)

| # | 원료 | 기대 |
|---|---|---|
| H-1a | 대두박 | high, requires_documentation=true |
| H-1b | 옥수수전분 | high |
| H-1c | 카놀라유 | requires_documentation=true |
| H-1d | 감자전분 | medium, requires_documentation=false |
| H-1e | 사과농축액 | medium, requires_documentation=false |
| H-1f | 설탕, 소금 (GMO 무관) | 결과 0건 |
| H-1g | 대두유+밀가루+사탕무 | 대두(high)+사탕무(high), 밀가루 제외 |
| H-1h | 빈 배열 | 결과 0건 |
| H-1i | ingredient_name은 원래 성분명 보존 | "면실유" 그대로 |

### H-2. 필수서류 취합 (9개)

| # | 조건 | 기대 서류 |
|---|---|---|
| H-2a | jurisdiction=health_functional_food | "건강기능식품 수입신고서" |
| H-2b | GMO 고위험 원료 있음 | "GMO 비의도적 혼입치 증명서" |
| H-2c | GMO 중위험(서류 불필요)만 | GMO 증명서 없음 |
| H-2d | 미표시 법정 알레르겐 | "알레르겐 표시 보완 자료" |
| H-2e | 알레르겐 이미 표시됨 | 보완 자료 없음 |
| H-2f | 비의무 알레르겐 미표시 | 보완 자료 없음 |
| H-2g | 일반 식품, 조건 없음 | 빈 배열 |
| H-2h | 보완 자료 reason에 알레르겐명 포함 | reason에 "밀" 포함 |
| H-2i | 모든 서류의 is_provided=false | 초기값 검증 |

---

## I. LLM 추천 결과 Sanitize (recommend-ingredient)

출처: `src/lib/verification/m4-1/__tests__/recommend-ingredient.test.ts`

### I-1. 프롬프트 빌더 (6개)

| # | 시나리오 | 검증 포인트 |
|---|---|---|
| I-1a | topN 포함 | 프롬프트에 N값 명시 |
| I-1b | JSON 스키마 + reasoning 명시 | 구조화 출력 요구 |
| I-1c | "후보 풀 외 id 생성 금지" 절대 규칙 | 프롬프트에 명시 |
| I-1d | allowed_status는 선택 기준 아님 명시 | 프롬프트에 명시 |
| I-1e | name_original이 다르면 원문 표시 | "원문: SUGAR" |
| I-1f | 후보 풀 없을 때 "후보 없음" | 안전 처리 |

### I-2. 응답 파서 (6개)

| # | 시나리오 | 기대 |
|---|---|---|
| I-2a | 정상 응답 | 파싱 성공, 기대 개수 일치 |
| I-2b | null/잘못된 JSON | 기대 개수만큼 빈 항목 패딩 |
| I-2c | recommendations 누락 | 패딩 |
| I-2d | LLM이 일부만 반환 | 나머지 no_match_likely |
| I-2e | candidates에 잘못된 item 섞임 | 필터 후 유효한 것만 |
| I-2f | candidates 0개 | no_match_likely 강제 true |

### I-3. Sanitize (4개)

| # | 시나리오 | 기대 |
|---|---|---|
| I-3a | **교차 오염 id** (다른 성분 풀의 id) | 필터됨 |
| I-3b | **name_ko/status/conditions DB 정본 강제** | LLM 출력 무시, DB 값 사용 |
| I-3c | confidence 내림차순 정렬 | 정렬 검증 |
| I-3d | 모두 필터됨 → no_match_likely=true | 안전 처리 |

---

## J. E2E 파이프라인 테스트

출처: `tests/e2e/pipeline.e2e.test.ts`

PDF 실물 파일 기반 전체 흐름:
1. **OCR**: PDF → 텍스트 추출 + 정규화 + 언어감지
2. **번역**: DeepL EN→KO
3. **ReviewContext**: LLM(gpt-4o) 파싱 → 제품명/성분/알레르겐
4. **M4-1**: 복합원재료 평가
5. **M4-2**: 식품유형 분류
6. **M4-3**: 일반 기준치
7. **M4-4**: 서류 vs 라벨 교차검증
8. **M5-1**: 이미지 위반 감지 (GPT-4o Vision) + 텍스트 위반 감지
9. **M5-2**: 제조공정 검증
10. **M6**: 라벨 초안 생성 + 필수항목 최종 검증

**현재 F1에 적용 가능한 E2E 범위**: Step 0(금지) → Step 1(매칭) → Step 1-A(복합) → Step 1-B(조건부) → Step 3(기준치)

---

## 총 시나리오 수

| 영역 | 시나리오 수 | F1 적용 가능 |
|---|---|---|
| A. 금지원료 게이트 | 9 | 9 (2개 버그 수정 필요) |
| B. 매칭 체인 | 11 | 11 |
| C. 복합원재료 | 5 | 5 |
| D. 조건부 평가 | 11 | 11 |
| E. 조건 유형 분류 | 7 | 7 |
| F. 부위 제한 검증 | 4 | 4 |
| G. 에스컬레이션 | 18 | 7 (F1 해당분만) |
| H. GMO/알레르겐/서류 | 18 | 18 (신규 모듈) |
| I. LLM Sanitize | 16 | 16 (향후 도입 시) |
| J. E2E | 1 파이프라인 | 1 |
| **합계** | **100** | **89** |
