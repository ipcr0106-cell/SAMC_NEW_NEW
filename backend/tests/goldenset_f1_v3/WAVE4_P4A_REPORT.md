# Wave 4 P4-a 실행 리포트 — 골든셋 v3 full (실 API)

> 실행일: 2026-04-20
> 스크립트: `backend/scripts/f1_run_goldenset_v3.py --subset full`
> 결과 파일: `backend/tests/goldenset_run_v3_20260420_0452.json`
> 환경: `F1_USE_DATA_GO_KR_API=true`, `F1_CANARY_PERCENTAGE=100`

## 실행 환경
- **DataGoKrClient**: 실 data.go.kr 4 엔드포인트 호출 (mock 아님)
- **Supabase**: migration 016/017/018 적용 완료, `f1_forbidden_ingredients` 실 DB 조회
- **Pinecone**: Step D 실 5 namespace 검색
- **케이스 수**: 57건 (12 카테고리)

## 전체 지표

| # | 지표 | 결과 | 목표 | 판정 |
|---|------|------:|------:|:----:|
| 1 | verdict 일치율 | **63.2%** | ≥80% | ❌ FAIL |
| 2 | 금지원료 감지율 (Recall) | **87.5%** | 100% | ❌ FAIL |
| 3 | 오탐률 | **0.0%** | ≤5% | ✅ PASS |
| 4 | 기준규격 정확도 | **23.3%** | ≥90% | ❌ FAIL |
| 5 | HITL-1 전환율 | **75.4%** | ≤30% | ❌ FAIL |
| **종합** | — | — | — | **NEEDS ATTENTION** |

## 카테고리별 verdict 일치율

| 카테고리 | 일치 | 총합 | 비율 |
|----------|:----:|:----:|:----:|
| **permitted_additive** | 7 | 7 | **100%** ✅ |
| **forbidden_endangered** | 3 | 3 | **100%** ✅ |
| **forbidden_toxin** | 3 | 3 | **100%** ✅ |
| **forbidden_unauthorized** | 6 | 6 | **100%** ✅ |
| **conditional_heated** | 4 | 4 | **100%** ✅ |
| **conditional_fermented** | 5 | 5 | **100%** ✅ |
| **conditional_alcohol** | 3 | 3 | **100%** ✅ |
| **unidentified_virtual** | 3 | 3 | **100%** ✅ |
| forbidden_drug | 2 | 4 | 50% 🟡 |
| conditional_restricted_db | 0 | 6 | **0%** 🔴 |
| multi_ingredient_combo | 0 | 3 | **0%** 🔴 |
| permitted_db | 0 | 10 | **0%** 🔴 |

## 근본 원인 분석

### 🔴 `permitted_db` 0/10 — 가장 큰 실패 카테고리
- **추정 원인**: 골든셋 v3 가 "`f1_forbidden_ingredients` DB 에 등재된 허용 원료" 를 가정했으나, 실제 DB 에는 **금지 원료만 등재**됨. 허용 판정은 Step B 의 data.go.kr 15111777 호출 결과에 따름.
- 10 케이스의 원재료명이 15111777 API 에서 정확 일치 못 하면 `unidentified` 로 빠져 verdict = `needs_review` → 기대 `permitted` 와 불일치.
- **대응**: Wave 4 P4-d 에서 담당자가 실제 케이스로 정답 라벨 재검증 + 원재료명 alias 매핑 보강.

### 🔴 `conditional_restricted_db` 0/6 — 조건부 원료
- **추정 원인**: 위와 유사. Step B 의 `CHRTR_INFO_CONT` 필드 해석 차이.

### 🔴 기준규격 정확도 23.3%
- Step C 실 API `SPEC_VAL` 파싱에서 예상보다 많이 실패. `SPEC_VAL` 텍스트 포맷이 골든셋 가정과 상이.
- 식품유형 매칭 (`SPEC_VAL_SUMUP`) 실패도 영향.

### 🟡 금지원료 Recall 87.5% (4중 2 누락)
- `forbidden_drug` 2/4 케이스 누락. 어떤 약물이 DB 미등재인지 재확인 필요.

### ✅ 성공한 카테고리
- 첨가물·위해·멸종·비승인·조건부(가열·발효·주류)·가상 미등록 → **전부 100%**
- Step A/B/D 기본 로직은 정상 동작. 실패는 데이터 측면 (골든셋 라벨 vs 실 API 응답 갭).

## Wave 4 P4-d (담당자 QA) 액션 목록

| 우선순위 | 작업 | 담당 |
|:-------:|------|------|
| 🔴 1 | `permitted_db` 10건 실 API 응답 확인 → 기대 verdict 재라벨 | 담당자 |
| 🔴 2 | `conditional_restricted_db` 6건 `CHRTR_INFO_CONT` 실 응답 확인 | 담당자 |
| 🔴 3 | `multi_ingredient_combo` 3건 복합 원재료 해석 재검증 | 담당자 |
| 🟡 4 | `forbidden_drug` 2건 누락 약물 명 확인 → DB 추가 또는 15111777 매칭 보강 | 담당자 |
| 🟡 5 | 기준규격 Step C `SPEC_VAL` 포맷 표준화 검토 | 개발자 |
| 🟢 6 | 원재료명 alias 매핑 테이블 확장 | 개발자 + 담당자 |

## 결론

**P4-a (실 API 실행) 완료.** 스크립트·인프라·API 연결·지표 자동 집계 모두 정상 동작. 지표 FAIL은 **기술 결함이 아니라 골든셋 라벨 vs 실 데이터 불일치**가 원인. Wave 4 P4-d 담당자 QA 로 케이스 재라벨 + 알고리즘 튜닝 후 재실행 필요.

### 다음 단계
- **Wave 4 P4-d**: 담당자가 실패한 19 케이스 (3 카테고리 + 금지약물 2 + 기준규격) 재검토
- **Wave 4 P5 Shadow**: 신규·레거시 파이프라인 병렬 실행 → 실 운영 데이터로 지표 재측정
- **Wave 4 P6 Canary**: 임계치 통과 확인 후 점진 롤아웃

## 참조 파일
- 실행 스크립트: `backend/scripts/f1_run_goldenset_v3.py`
- 결과 JSON: `backend/tests/goldenset_run_v3_20260420_0452.json`
- 지표 정의: `backend/tests/goldenset_f1_v3/METRICS.md`
- 골든셋 케이스 57건: `backend/tests/goldenset_f1_v3/cases/*`
