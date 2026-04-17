# F1 RAG Phase 4-B 골든셋 평가 리포트

> **작성**: 2026-04-17
> **Phase**: 4-B-3c (골든셋 실행 + OPEN-2 결정)
> **담당**: 병찬
> **상태**: ✅ 1차 실행 완료 (gpt-4o-mini) — 일치율 70.0% → OPEN-2 **gpt-4o-mini 채택**

---

## 1. 실행 환경

| 항목 | 값 |
|---|---|
| 골든셋 | [`backend/tests/goldenset_f1_v1.json`](../backend/tests/goldenset_f1_v1.json) (v1, 30건) |
| 러너 | [`backend/scripts/f1_run_goldenset.py`](../backend/scripts/f1_run_goldenset.py) |
| OpenAI Chat 모델 | `gpt-4o-mini` (1차) → OPEN-2 게이트 시 `gpt-4o` |
| OpenAI Embedding 모델 | `text-embedding-3-small` |
| Pinecone 인덱스 | `samc-law-f1` (2148건, 5 namespace) |
| top_k per namespace | 5 (상위 2×top_k=10건 컨텍스트 사용) |
| Supabase 프로젝트 | `bnfgbwwibnljynwgkgpt` — f1_* 110건 시드 |
| 실행일 | 2026-04-17 |

### 인덱스 스냅샷

| Namespace | 건수 | 출처 |
|---|---|---|
| additive_code_text | 1664 | 식품첨가물공전 md 6개 임베딩 (Phase 3) |
| food_code_text | 140 | newsamc 복제 (Phase 2) |
| health_food_text | 252 | newsamc 복제 (Phase 2) |
| temporary_standard | 74 | newsamc 복제 (Phase 2) |
| functional_labeling | 18 | newsamc 복제 (Phase 2) |
| **합계** | **2148** | — |

---

## 2. 골든셋 구성

### 2.1 전체 분포 (계획)

| conflict_status | 건수 | 비율 |
|---|---|---|
| agreed | 9 | 30% |
| rag_supplemented | 16 | 53% |
| rag_skipped | 5 | 17% |
| conflict | 0 (런타임 관측) | — |
| rag_unavailable | 0 (런타임 관측) | — |
| **총** | **30** | 100% |

### 2.2 카테고리별

| 카테고리 | case_id 범위 | 건수 | 주요 conflict 예측 |
|---|---|---|---|
| 허용 (DB 매칭) | g001~g005 | 5 | agreed |
| 허용 (첨가물, RAG 보완) | g006~g010 | 5 | rag_supplemented |
| 금지 (Step 0) | g011~g015 | 5 | rag_skipped |
| 조건부 — 기타 (DB restricted) | g016 | 1 | agreed |
| 조건부 — 가열 (소브산/소브산칼륨 × T/F) | g017~g020 | 4 | rag_supplemented |
| 조건부 — 발효 (유산균/Bacillus × T/F) | g021~g024 | 4 | rag_supplemented |
| 조건부 — 도수 (에탄올 15/19/25%) | g025~g027 | 3 | rag_supplemented |
| 미등록 (가상명) | g028~g030 | 3 | agreed |

### 2.3 조건부 비율

**12/30 = 40.0% ✅** (요구사항: ≥ 40%)

---

## 3. 1차 실행 결과 — gpt-4o-mini

> **실행**: 2026-04-17 / 출력 [`backend/tests/goldenset_run_result_mini.json`](../backend/tests/goldenset_run_result_mini.json)

### 3.1 전체 요약

| 지표 | 값 | 평가 |
|---|---|---|
| 성공 건수 | 30 / 30 | ✅ |
| 에러 건수 | 0 | ✅ |
| **conflict 일치율** | **70.0% (21/30)** | 🟡 60~80% (프롬프트 튜닝 여지) |
| exact 일치율 | 96.7% (29/30) | ✅ step1 정확 |
| rag 일치율 | 66.7% (20/30) | 🟡 RAG 보수성 |
| 레이턴시 p50 | 4,156 ms | ✅ |
| 레이턴시 p95 | 9,170 ms | 🔴 > 5s 목표 초과 → OPEN-4 캐싱 시그널 |
| 비용 추정 | ~$0.0414 | ✅ |

### 3.2 분기별 conflict 일치율

| 예측 분기 | 일치 / 총 | 비율 | 평가 |
|---|---|---|---|
| agreed | 5 / 9 | **55.6%** | 🔴 가장 취약 |
| rag_supplemented | 11 / 16 | 68.8% | 🟡 |
| rag_skipped | 5 / 5 | **100.0%** | ✅ Step 0 게이트 완벽 |

### 3.3 actual conflict 분포

| actual 분기 | 건수 | expected 대비 증감 |
|---|---|---|
| agreed | 12 | +3 (9 → 12) |
| rag_supplemented | 10 | -6 (16 → 10) |
| rag_skipped | 5 | 0 (5 → 5) |
| **conflict** | **3** | **신규 발생** (g003 우유, g004 꿀, g016 과라나) |
| rag_unavailable | 0 | 네트워크 안정 |

### 3.4 실패 케이스 상세 (9건)

| case_id | description | exp_conflict | act_conflict | 원인 유형 | 원인 상세 |
|---|---|---|---|---|---|
| g003 | 우유 | agreed | **conflict** | B. RAG 오판 | RAG가 "우유류는 일체의 다른 물질 혼합 불가" 를 prohibited로 과잉 해석. citation score 0.530 낮음. |
| g004 | 꿀 | agreed | **conflict** | A. RAG 보수성 | exact=permitted인데 RAG=unidentified (청크 0건). 식품공전에 꿀 기준 있으나 retrieve 실패 |
| g006 | 설탕 | rag_supplemented | agreed | A. RAG 보수성 | 법령 청크로 "고춧가루"만 retrieve됨 → unidentified. 의미적 일치 실패 |
| g007 | 포도당 | rag_supplemented | agreed | **C. step1 예측 오차** | expected_exact=unidentified 였으나 실제 `permitted` (trgm fuzzy '포도'→'포도당' 추정) |
| g008 | 구연산 | rag_supplemented | agreed | A. RAG 보수성 | INS 330 제공했으나 RAG는 unidentified. 첨가물공전 청크 매칭 실패 |
| g016 | 과라나 | agreed | **conflict** | A. RAG 보수성 | exact=restricted(DB 별표2)인데 RAG=unidentified. 별표2 청크 retrieve 실패 |
| g021 | 유산균(fermented) | rag_supplemented | agreed | A. RAG 보수성 | 청크 0건, unidentified |
| g022 | 유산균(non-fermented) | rag_supplemented | agreed | A. RAG 보수성 | 청크 0건, unidentified |
| g029 | 크리오벨라(가상) | agreed | rag_supplemented | B. RAG 오판 | 가상 원료를 "건강기능식품 원료" 로 permitted 오판. score 0.432 낮은 citation에 끌림 |

### 3.5 원인 유형별 집계

| 유형 | 건수 | 비중 | 특징 | 대응 우선순위 |
|---|---|---|---|---|
| A. RAG 보수성 (unidentified 남발) | 6 | 67% | citation 0건, "직접 근거 없음" 판단 과잉 | **높음** — 프롬프트 튜닝 |
| B. RAG 오판 (false positive) | 2 | 22% | 낮은 score(0.4~0.5) citation을 신뢰 | 중간 — score threshold 도입 |
| C. step1 fuzzy 매칭 예측 오차 | 1 | 11% | 골든셋 expected 수정 대상 | 낮음 — 다음 revision |

### 3.6 rag_reasoning 패턴 분석

실패 6건 중 A 유형 공통 문구: *"~에 대한 명확한 규정이 없습니다 / 구체적인 기준이 명시되어 있지 않습니다"*. 시스템 프롬프트의 `"법령 청크에 직접 근거가 있는 경우만 verdict를 결정하세요"` 원칙이 **과잉 적용**되는 경향.

---

## 4. OPEN-2 게이트 결정

**게이트 기준** ([계획/f1_RAG도입_Phase진행계획.md §결정 게이트](./f1_RAG도입_Phase진행계획.md#결정-게이트)):
- conflict 일치율 ≥ 80% → **통과** (gpt-4o-mini 유지)
- 60% ≤ 일치율 < 80% → 프롬프트 튜닝 (SYSTEM_PROMPT few-shot 추가) 검토
- 일치율 < 60% → **gpt-4o 격상** + 재실행

### 4.1 1차 결과 (gpt-4o-mini)

- **conflict 일치율: 70.0% (21/30)**
- 60% ≤ 70% < 80% → **중간 구간** (gpt-4o 격상 불필요, 프롬프트 튜닝 여지)

### 4.2 2차 결과 (gpt-4o, 해당 시)

> **해당 없음** — 1차 일치율 70% ≥ 60% 이므로 자동 격상 미발동.
> 향후 일치율 80% 달성 필요 시 별도 세션에서 재검토.

### 4.3 최종 결정

✅ **gpt-4o-mini 채택** (환경변수 `F1_OPENAI_CHAT_MODEL=gpt-4o-mini` 유지)

**후속 튜닝 옵션** (Phase 5 이후 별도 작업):

1. **SYSTEM_PROMPT few-shot 추가** — 청크 간접 언급도 근거로 활용하는 예시 2~3건 주입
2. **citation score threshold** — score < 0.5 citation 무시하는 필터 도입 (g029 오판 방지)
3. **namespace 선별** — 원료명 포함 keyword 기반으로 namespace 우선순위 조정
4. **골든셋 v2** — g007 등 expected 수정, fuzzy 매칭 고려

튜닝 후 재실행 시 일치율 목표: **≥ 80%**.

---

## 5. OPEN-1 (top_K 재검토)

현재 설정: `F1_RAG_TOP_K=5` (namespace당 5건, 상위 2×5=10건 컨텍스트 사용).

### 5.1 검토 방식

1차 실행 후 **실패 케이스가 집중된 카테고리**(예: 첨가물 허용 · 발효 조건부)에서 top_k를 {3, 10}으로 부분 재실행 비교.

### 5.2 결과

**결정**: **top_k=5 유지 (부분 재실행 보류)**

이유:
- 실패 원인 중 **67%(6/9)가 "청크 0건" A 유형** — top_k 증가로 개선될 여지가 있으나, 현재 6건 중 대부분은 재정렬 문제가 아니라 **의미 기반 매칭 실패** (예: "고춧가루"만 retrieve되는 g006 설탕 케이스).
- top_k를 10으로 늘리면 컨텍스트 크기 2배 → 비용/레이턴시 2배 부담. 현재 p95=9s를 5s 이하로 줄여야 하는 상황에서 역방향.
- 재실행 비용(~$0.08 추가) 대비 기대 개선 효과 낮음.

**향후 조치**: 프롬프트 튜닝 후에도 일치율 80% 미달 시 top_k {3, 10} 재실행 재검토.

---

## 6. 레이턴시 분석

### 6.1 30건 분포

| 지표 | 값 |
|---|---|
| p50 | 4,156 ms |
| p95 | **9,170 ms** |
| 최소 | 32 ms (g015 카바카바, Step 0 미호출 경로) |
| 최대 | 9,625 ms (g002 사과) |
| rag_skipped 평균 | ~50 ms (5건 모두 < 80ms) |
| rag 호출 평균 | ~5,400 ms (25건) |

### 6.2 캐싱 도입 여부 (OPEN-4)

🔴 **p95 = 9,170 ms → 5초 목표 초과** → Phase 5 e2e 후 **Redis 캐싱 도입 권고**.

우선순위:
1. **임베딩 캐싱** (`query_hash → vector`) — 동일 제품 반복 조회 시 embed 비용 0, 레이턴시 감소
2. **전체 응답 캐싱** (`payload_hash → response`, 1시간 TTL) — 완전 동일 입력 반복 시 효과 최대

단, 실 운영 환경에서 payload hash 적중률 측정 후 도입 여부 확정.

---

## 7. 다음 단계

### 7.1 Phase 4-B 완료 조건 체크리스트

- [x] gpt-4o-mini 30건 실행 완료 (30/30 성공, 0 에러)
- [x] conflict 일치율 리포트 기재 (70.0%)
- [x] OPEN-2 게이트 결정 기록 (**gpt-4o-mini 채택**, 튜닝 메모)
- [x] OPEN-1 top_k 검토 결과 기록 (top_k=5 유지)
- [x] 레이턴시 p50/p95 기록 (4156ms / 9170ms, OPEN-4 캐싱 시그널)
- [ ] (이월) admin UI 실 PDF 업로드 엔드투엔드 검증 → **Phase 5 초반**
- [ ] (이월) SYSTEM_PROMPT few-shot 튜닝 + 재실행 → 별도 작업

### 7.2 Phase 5 이월

- **admin upload 실 PDF 엔드투엔드 검증** — Phase 4-B-2에서 코드 교체만 완료. 실 파일 업로드 → Pinecone namespace 적재 테스트는 Phase 5 초반에 수행.
- **프론트 법령 인용 UI + RagConflictPanel** — Phase 5 주요 산출물 (예상 2.7일).

### 7.3 문서 갱신

- `MERGE_GUIDE.md` F1 섹션 env 표/인덱스 표 갱신 (Phase 5에서)
- 다음 세션 인계 메모: `memory/project_f1_rag.md` 업데이트

---

## 부록 A. 상세 케이스 목록 (30건)

> 전체 케이스는 [`backend/tests/goldenset_f1_v1.json`](../backend/tests/goldenset_f1_v1.json) 의 `cases` 배열 참조.

---

## 부록 B. 1차 실행 로그 snapshot

```
[info] goldenset: backend/tests/goldenset_f1_v1.json
[info] cases: 30
[info] model: gpt-4o-mini / top_k=5 / index=samc-law-f1

[  1/30] g001 허용 원료 — 쌀 단일 ................ ✓ conflict=agreed (7844ms)
[  2/30] g002 허용 원료 — 사과 단일 ............... ✓ conflict=agreed (9625ms)
[  3/30] g003 허용 원료 — 우유 ................... ✗ conflict=conflict (6187ms)
[  4/30] g004 허용 원료 — 꿀 ..................... ✗ conflict=conflict (8016ms)
[  5/30] g005 허용 원료 — 인삼 ................... ✓ conflict=agreed (2812ms)
[  6/30] g006 첨가물 허용 — 설탕 .................. ✗ conflict=agreed (3157ms)
[  7/30] g007 첨가물 허용 — 포도당 ................ ✗ conflict=agreed (3296ms)
[  8/30] g008 첨가물 허용 — 구연산 ................ ✗ conflict=agreed (3032ms)
[  9/30] g009 첨가물 허용 — 아스코르브산 ........... ✓ conflict=rag_supplemented (7453ms)
[ 10/30] g010 첨가물 허용 — 글리세린 .............. ✓ conflict=rag_supplemented (6594ms)
[ 11/30] g011 금지 — 대마초 ...................... ✓ conflict=rag_skipped (78ms)
[ 12/30] g012 금지 — 양귀비 ...................... ✓ conflict=rag_skipped (47ms)
[ 13/30] g013 금지 — 코카잎 ...................... ✓ conflict=rag_skipped (46ms)
[ 14/30] g014 금지 — THC (alias) ................ ✓ conflict=rag_skipped (47ms)
[ 15/30] g015 금지 — 카바카바 .................... ✓ conflict=rag_skipped (32ms)
[ 16/30] g016 조건부 — 과라나 .................... ✗ conflict=conflict (7625ms)
[ 17/30] g017 가열 — 소브산 T .................... ✓ conflict=rag_supplemented (7187ms)
[ 18/30] g018 가열 — 소브산 F .................... ✓ conflict=rag_supplemented (7016ms)
[ 19/30] g019 가열 — 소브산칼륨 T ................. ✓ conflict=rag_supplemented (4593ms)
[ 20/30] g020 가열 — 소브산칼륨 F ................. ✓ conflict=rag_supplemented (5344ms)
[ 21/30] g021 발효 — 유산균 T .................... ✗ conflict=agreed (6594ms)
[ 22/30] g022 발효 — 유산균 F .................... ✗ conflict=agreed (2937ms)
[ 23/30] g023 발효 — Bacillus T .................. ✓ conflict=rag_supplemented (3407ms)
[ 24/30] g024 발효 — Bacillus F .................. ✓ conflict=rag_supplemented (3718ms)
[ 25/30] g025 도수 — 에탄올 15% ................... ✓ conflict=rag_supplemented (4610ms)
[ 26/30] g026 도수 — 에탄올 19% ................... ✓ conflict=rag_supplemented (2672ms)
[ 27/30] g027 도수 — 에탄올 25% ................... ✓ conflict=rag_supplemented (3234ms)
[ 28/30] g028 미등록 — 제노스틴 ................... ✓ conflict=agreed (3297ms)
[ 29/30] g029 미등록 — 크리오벨라 .................. ✗ conflict=rag_supplemented (5969ms)
[ 30/30] g030 미등록 — 루미얀 ..................... ✓ conflict=agreed (8797ms)

============================================================
총 30건 / 성공 30 / 실패 0
conflict 일치율: 70.0%
exact   일치율: 96.7%
rag     일치율: 66.7%
레이턴시 p50=4155.5ms / p95=9169.6ms
비용 추정: ~$0.0414
분기별 일치율:
  agreed             5/9 (55.6%)
  rag_supplemented   11/16 (68.8%)
  rag_skipped        5/5 (100.0%)
```

---

## 부록 C. 참고 링크

- 총괄 계획서: [계획/f1_RAG도입계획_총괄.md](./f1_RAG도입계획_총괄.md) (§2.7 HITL 매트릭스)
- 백엔드 계획서: [계획/f1_RAG도입계획_백엔드.md](./f1_RAG도입계획_백엔드.md) (§3.3, §8)
- Phase 진행 계획: [계획/f1_RAG도입_Phase진행계획.md](./f1_RAG도입_Phase진행계획.md) (§Phase 4-B)
- Phase 4-A integration 테스트: [backend/tests/test_f1_rag_judge.py](../backend/tests/test_f1_rag_judge.py)
- Phase 4-B-1 integration 테스트: [backend/tests/test_feature1_rag_integration.py](../backend/tests/test_feature1_rag_integration.py)
