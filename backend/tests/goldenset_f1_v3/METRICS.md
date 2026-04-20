# F1 골든셋 v3 메트릭 대시보드 스펙

담당자 인수인계용. 측정 항목·임계치·측정 주기 정리.

---

## 1. 지표 정의 및 임계치

| # | 지표명 | 정의 | 임계치 | 측정 대상 케이스 |
|---|--------|------|--------|-----------------|
| M1 | **verdict 일치율** | AI 추천 verdict vs 담당자 최종 판정 일치 비율 | **≥ 80%** | 전체 57건 |
| M2 | **금지원료 감지율 (Recall)** | is_forbidden=True 케이스에서 actual=prohibited 비율 | **100%** | 금지 카테고리 14건 |
| M3 | **오탐률 (FPR)** | permitted 케이스인데 prohibited/restricted 오분류 비율 | **≤ 5%** | permitted_db 10건 + permitted_additive 6건 |
| M4 | **기준규격 정확도** | Step C overall_status 일치 비율 (no_data 제외) | **≥ 90%** | standards 비교 가능 케이스 |
| M5 | **HITL-1 전환율** | needs_review/restricted 판정 비율 | **≤ 30%** | 전체 57건 |

---

## 2. 카테고리별 케이스 분포 (v3 57건)

| 카테고리 | 건수 | 비율 | 핵심 검증 항목 |
|----------|------|------|----------------|
| `permitted_db` | 10 | 17.5% | M3 오탐률 (이 케이스가 오탐되면 안 됨) |
| `permitted_additive` | 6 | 10.5% | M3 오탐률 + Step B unidentified 처리 |
| `forbidden_drug` | 4 | 7.0% | M2 Recall (마약류, alias 포함) |
| `forbidden_endangered` | 3 | 5.3% | M2 Recall (멸종위기종) |
| `forbidden_unauthorized` | 6 | 10.5% | M2 Recall (비승인 성분, 복합 hidden 포함) |
| `forbidden_toxin` | 3 | 5.3% | M2 Recall (PA 알칼로이드) |
| `conditional_restricted_db` | 6 | 10.5% | M1 restricted 판정 정확도 |
| `conditional_heated` | 4 | 7.0% | M1 가열 조건 분기 처리 |
| `conditional_fermented` | 5 | 8.8% | M1 발효 조건 분기 처리 |
| `conditional_alcohol` | 3 | 5.3% | M1 도수 조건 분기 처리 |
| `multi_ingredient_combo` | 5 | 8.8% | M1 sub_ingredients 재귀 평탄화 + Step A 금지 hidden |
| `unidentified_virtual` | 3 | 5.3% | HITL-1 전환 (가상 원료 → needs_review) |
| **합계** | **57** | **100%** | |

---

## 3. 측정 주기

| 주기 | 방식 | 대상 |
|------|------|------|
| **매 PR** | CI 자동 (`goldenset-mini` job) | mini 5건, mock 모드 — 실행 가능성 검증 |
| **매 release** | CI 자동 (`goldenset-full` job) | 전체 57건, 실 API — 임계치 PASS 여부 게이트 |
| **분기별** | 수동 실행 | 전체 57건 + 담당자 판정 업데이트 반영 |
| **Wave 4 P4** | 수동 실행 | 실 API + 실측값 checks[] 채운 expected_standards로 M4 측정 |

---

## 4. 결과 파일 보관 정책

```
backend/tests/
├── goldenset_run_v3_{YYYYMMDD_HHmm}.json   # 실행 시마다 누적 저장
└── goldenset_f1_v3/
    └── cases/
        └── case_NNN_*/
            ├── input_f0.json               # 고정 (변경 금지)
            ├── expected_verdict.json       # 담당자 판정 업데이트 허용
            └── expected_standards.json     # Wave 4 실 API 연동 후 채움
```

결과 파일은 `.gitignore`에 추가하지 말고 **git에 커밋**하여 추세 추적.

---

## 5. 지표 해석 가이드

### M2 금지원료 Recall < 100%
- **즉시 조치 필요** — 금지원료 미탐지는 수입 허용 오류로 직결
- Step A DB + 15111777 API 양쪽 확인
- `f1_forbidden_ingredients` 테이블 시드 업데이트 여부 확인

### M3 오탐률 > 5%
- permitted 원료가 restricted/prohibited로 잘못 분류됨
- Step B `resolve_verdict()` 로직 및 Levenshtein fallback 확인
- `f1_allowed_ingredients` DB 커버리지 확인

### M1 verdict 일치율 < 80%
- 전반적 파이프라인 성능 저하
- 카테고리별 accuracy 분석 → 특정 카테고리 집중 디버깅
- `goldenset_run_v3_*.json`의 `category_accuracy` 섹션 참조

### M5 HITL-1 전환율 > 30%
- 담당자 업무 부담 과다
- Step B `unidentified` 증가 원인 분석 (API 장애 vs 원료명 정규화 실패)
- DB 커버리지 보강 또는 Levenshtein threshold 조정 검토

---

## 6. expected_verdict.json 업데이트 절차

담당자 판정이 변경된 경우:

1. 해당 케이스 `expected_verdict.json`의 `verdict` 필드 수정
2. `notes` 필드에 변경 이유 추가
3. PR 생성 후 팀 리뷰 (골든셋 정답 변경이므로 신중히)
4. 머지 후 `goldenset-full` 재실행하여 정확도 재측정

---

## 7. Wave 4 P4 통합 검증 추가 작업

현재 `expected_standards.json`의 `checks: []`는 비어 있습니다.
Wave 4 P4 통합 검증 시점에 아래 작업이 필요합니다:

- [ ] 각 케이스에 대해 `run_feature1_v2` 실행 후 Step C 결과 수집
- [ ] `expected_standards.json`의 `checks[]`를 실 API 결과로 채움
- [ ] M4 기준규격 정확도 측정 가능 상태 전환
- [ ] 필요시 `overall_status` 정답 레이블 재검토 (담당자 확인)

담당 subagent: `verifier` (Wave 4 P4)

---

*최종 업데이트: 2026-04-20 (Wave 3 W3-QA)*
