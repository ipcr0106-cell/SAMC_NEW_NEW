# Wave 4 P4 보완 계획서

> 작성일: 2026-04-20
> 범위: Wave 4 P4-a 실행 결과에서 드러난 기술적 갭 3건 보완 + P4-d 담당자 QA 진입 준비
> 선행 문서:
> - `계획/f1 재설계 계획/14_병렬실행_계획.md` §7 Wave 4 배포
> - `backend/tests/goldenset_f1_v3/WAVE4_P4A_REPORT.md` (골든셋 full 실행 지표)
> - `MEMORY.md > project_f1_redesign_wave.md` (Wave 5 BE 이식 계획 — T1 과의 관계)

---

## 1. 목적

Wave 4 P4-a 골든셋 full(57건) 실행 결과 verdict 일치율 63.2% / 기준규격 정확도 23.3% / Recall 87.5% 로 P4 게이트(80%+ / 90%+ / 100%) 미달. WAVE4_P4A_REPORT 가 진단한 "기술 결함이 아니라 골든셋 라벨 vs 실 데이터 불일치" 중 **개발자 단독 처리가 가능한 3 트랙**을 먼저 보완하고, 담당자 QA(P4-d) 가 진입 가능한 상태로 만드는 것이 본 계획의 목표.

부수 목표: f1f2 병합(PR #28) 후 F1 페이지에서 F2 를 실행할 UI 경로가 끊긴 상태이므로, Wave 5 BE 이식 전이라도 **임시 실행 트리거**를 복구하여 전체 플로우 QA 를 가능하게 한다.

---

## 2. 스코프 요약

| 트랙 | 제목 | 근거 | 담당 |
|:---:|------|------|------|
| **T1** | FE F2 실행 트리거 복구 | f1f2 병합 후 UI 갭 / Wave 5 BE 이식 전 대체 | `executor` sonnet |
| **T2** | Step C `SPEC_VAL` 파싱 보강 | WAVE4_P4A_REPORT §🔴 기준규격 23.3% | `executor` sonnet |
| **T3** | 원재료명 alias 매핑 확장 | WAVE4_P4A_REPORT §🔴 `permitted_db` 0% / `conditional_restricted_db` 0% | `executor` + 담당자 |

스코프 **밖**:
- samcbc `step0_food_type` BE 이식 (Wave 5 범위)
- P3 인증 연동 (Wave 4 P7+ 이월)
- P5 Shadow 인프라 (별도 계획)

---

## 3. T1 — FE F2 실행 트리거 복구

### 3-1. 현재 상태

- `/cases/{id}/f2` → `/cases/{id}/f1#food-type` 리다이렉트 (PR #28)
- `FoodTypeSection.tsx` 는 결과가 없을 때 안내 문구만 표시하고 실행 버튼 없음
- 기존 `runFeature2` / `getFeature2` API 는 `lib/api.ts` 에 살아있음 (deprecated 주석만 붙음)
- 결과: F2 를 실행할 UI 경로 부재 → F1 후속 플로우 QA 불가

### 3-2. 변경 범위

| 파일 | 변경 내용 | 편집 허용 |
|------|----------|:---:|
| `frontend/features/feature1/components/FoodTypeSection.tsx` | `hierarchy === null` 분기에 "AI 분류 실행" 버튼 + loading/error state 추가 | ✅ |
| `frontend/features/feature1/ImportCheckPage.tsx` | `runF2Handler` 콜백 추가, `FoodTypeSection` 에 prop 전달 | ✅ |
| `frontend/features/feature1/components/__tests__/FoodTypeSection.test.tsx` | 버튼 노출 · 클릭 · loading 상태 테스트 3건 | ✅ |
| `frontend/lib/api.ts` | `runFeature2` deprecated 주석만 완화 (삭제 금지) | ⚠️ 주석만 |

### 3-3. 인터페이스 시그니처 (구현 가이드)

```tsx
// FoodTypeSection props 확장
interface FoodTypeSectionProps {
  hierarchy: FoodTypeHierarchy | null;
  onEdit: () => void;
  onRun?: () => Promise<void>;     // 신규
  isRunning?: boolean;              // 신규
  runError?: string | null;         // 신규
  isEditable: boolean;
}
```

```tsx
// ImportCheckPage 내부 콜백 (신규)
const [isRunningF2, setIsRunningF2] = useLocalState(false);
const [f2RunError, setF2RunError]   = useLocalState<string | null>(null);

const handleRunF2 = useCallback(async () => {
  setIsRunningF2(true); setF2RunError(null);
  try {
    await runFeature2(caseId);
    const row = await getFeature2(caseId);
    const picked = row.final_result ?? row.ai_result;
    if (picked) setFoodTypeHierarchy(picked);
  } catch (e) {
    setF2RunError(e instanceof Error ? e.message : "F2 실행 실패");
  } finally {
    setIsRunningF2(false);
  }
}, [caseId]);
```

### 3-4. 테스트 계획

- 유닛: `FoodTypeSection.test.tsx`
  - `hierarchy=null` 일 때 "AI 분류 실행" 버튼 노출
  - 버튼 클릭 → `onRun` 호출
  - `isRunning=true` → 버튼 비활성 + 로딩 표시
  - `runError` 존재 시 에러 메시지 노출
- 통합: 기존 E-01 flow 에 F2 실행 스텝 삽입 (선택사항, 시간 남으면)

### 3-5. 위험 / 롤백

- 위험: `runFeature2` 가 Wave 5 BE 이식 후 deprecate 될 예정 → **T1 은 "임시" 마킹 주석 필수**. `// TODO(Wave 5): samcbc step0_food_type 이식 후 제거`
- 롤백: `FoodTypeSection` 한 파일 revert 로 복원 가능

### 3-6. 완료 기준

- [ ] FE 3 파일 수정 + 신규 테스트 3건 pass
- [ ] F1 페이지에서 F2 미실행 상태 → 버튼 클릭 → 결과 표시 수동 확인 완료
- [ ] deprecated 주석에 Wave 5 이식 TODO 명시

---

## 4. T2 — Step C `SPEC_VAL` 파싱 보강

### 4-1. 현재 상태

- WAVE4_P4A_REPORT §🔴: 기준규격 정확도 **23.3%** (목표 90%)
- 원인 추정: `SPEC_VAL` 텍스트 포맷 다양성 (예: "납 0.1 mg/kg 이하", "총 아플라톡신 10 μg/kg 이하" 등 혼재) + `SPEC_VAL_SUMUP` 식품유형 매칭 실패
- Step C 구현체: `backend/services/step_c_standards.py` (Wave 2 완료)

### 4-2. 변경 범위

| 파일 | 변경 내용 |
|------|----------|
| `backend/tests/fixtures/spec_val_samples.json` (신규) | 실 API 응답 스니펫 20건 수집 (성공 10 + 실패 10) |
| `backend/services/step_c_standards.py` | 파서 정규식 확장 + 단위 표기 변형 처리 + `SPEC_VAL_SUMUP` 매칭 fallback |
| `backend/tests/unit/test_step_c_parsing.py` | edge case 파싱 테스트 20건 |
| `backend/scripts/f1_collect_spec_val.py` (신규) | 실 API 응답 수집 스크립트 (골든셋 57건 재실행) |

### 4-3. 작업 순서

1. **관찰** — `f1_collect_spec_val.py` 로 실 API 응답 20건 수집 (개발 단계 한정)
2. **분류** — 성공 / 실패 패턴 라벨링 (`spec_val_samples.json`)
3. **파서 개선** — 실패 패턴별 정규식 추가 (단위 약어 · 한자 혼용 · 복합 기준 등)
4. **회귀 검증** — Step C 유닛 + 골든셋 full 재실행

### 4-4. 완료 기준

- [ ] 파싱 edge case 테스트 20건 pass
- [ ] 골든셋 full 기준규격 정확도 ≥ 90%
- [ ] Step C 전체 테스트 회귀 없음

---

## 5. T3 — 원재료명 alias 매핑 확장

### 5-1. 현재 상태

- WAVE4_P4A_REPORT §🔴: `permitted_db` 0/10, `conditional_restricted_db` 0/6, `multi_ingredient_combo` 0/3
- 원인: data.go.kr 15111777 응답 원재료명 vs 골든셋 원재료명 불일치 → `unidentified` 로 빠짐 → verdict 오판
- 현재 alias 테이블: (미존재) 또는 분산된 상태

### 5-2. 변경 범위

| 파일 | 변경 내용 |
|------|----------|
| `supabase/migrations/019_ingredient_alias.sql` (신규) | `f1_ingredient_alias` 테이블 생성 (canonical_name / alias / source / confidence) |
| `supabase/seed/06_ingredient_alias.sql` (신규) | 19 실패 케이스 기반 초기 alias 50~100건 |
| `backend/services/step_b_ingredient_matching.py` | alias 조회 로직 추가 (canonical 매칭 실패 시 alias lookup) |
| `backend/tests/unit/test_alias_matching.py` | alias 경로 커버리지 테스트 |

### 5-3. 담당자 협업 포인트

- T3 는 **담당자 실 API 응답 확인 필요** → P4-d 와 부분 병행
- 개발자: 테이블 스키마 + 매칭 로직 + 시드 10건
- 담당자: 나머지 40~90건 alias 입력 (별도 시트 템플릿으로 전달)

### 5-4. F1 규약 준수 체크 (7번 §7 DB변경규칙)

- [x] `f1_` prefix 준수
- [x] 신규 테이블이므로 breaking change 없음
- [x] `law_source` + `is_verified` 컬럼 포함 예정
- [ ] 팀 sign-off 확보 (migration 019 제출 전)

### 5-5. 완료 기준

- [ ] migration 019 + seed 06 Supabase 적용
- [ ] alias 매칭 유닛 테스트 pass
- [ ] 골든셋 full `permitted_db` + `conditional_restricted_db` 카테고리 ≥ 80%

---

## 6. 트랙 의존관계 / 실행 순서

```
T1 (단독 시작 가능, 1일)
  ├─ FE 버튼 추가
  └─ 수동 QA 확인
T2 (단독 시작 가능, 2일)
  ├─ 실 API 수집
  ├─ 파서 개선
  └─ 유닛 회귀
T3 (담당자 협업, 2~3일)
  ├─ 스키마 + 시드 10건 (개발자)
  ├─ 담당자 40~90건 입력 대기
  └─ 매칭 로직 반영
───────────────────────────
통합 게이트: 골든셋 full 재실행
```

- T1 / T2 는 **한 메시지 Agent() 병렬** 가능 (파일 경계 겹치지 않음)
- T3 는 담당자 일정 의존 → 백그라운드 진행

---

## 7. 전체 완료 게이트

| 지표 | P4-a 실측 | 목표 | 본 보완 후 예상 |
|------|:---:|:---:|:---:|
| verdict 일치율 | 63.2% | ≥80% | 85%+ (T3 효과 주도) |
| 금지원료 Recall | 87.5% | 100% | 100% (forbidden_drug alias) |
| 오탐률 | 0.0% | ≤5% | 0.0% 유지 |
| 기준규격 정확도 | 23.3% | ≥90% | 90%+ (T2 효과 주도) |
| HITL-1 전환율 | 75.4% | ≤30% | 30%± (T3 부수효과) |

통합 게이트: **위 4 지표 동시 통과 → P4-d 담당자 QA 단축 가능 / 미통과 시 P4-d 담당자 QA 로 나머지 보완**.

---

## 8. P4-d 담당자 QA 인계 준비

본 보완 완료 후 담당자 QA 가 바로 시작 가능하도록 다음 산출물을 준비:

| 산출물 | 경로 (예정) | 담당 |
|------|------------|------|
| QA 가이드 | `계획/f1 재설계 계획/WAVE4_P4D_담당자QA_가이드.md` | `writer` |
| 19 케이스 재라벨 시트 | `backend/tests/goldenset_f1_v3/P4D_relabel_sheet.csv` | `test-engineer` |
| alias 입력 템플릿 | `backend/tests/goldenset_f1_v3/P4D_alias_template.csv` | `test-engineer` |
| SPEC_VAL 포맷 사례집 | `backend/tests/fixtures/spec_val_samples.json` (T2 산출물 재사용) | T2 |

---

## 9. 리스크 · 롤백

| 리스크 | 완화 |
|------|------|
| T1 에 Wave 5 이식 전 임시 코드가 남음 | TODO 주석 + 이식 완료 시 제거 명시 |
| T2 파서 개선이 다른 케이스 회귀 유발 | 골든셋 full 재실행으로 회귀 감시 |
| T3 담당자 입력 지연 | 개발자 시드 10건으로 최소 검증 후 점진 확장 |
| migration 019 실패 | rollback SQL 함께 제출, Supabase Studio 에서 수동 적용 |

롤백 단위: 트랙별 PR 단독 revert 가능. T1 / T2 / T3 파일 경계가 겹치지 않음.

---

## 10. 체크리스트

### T1 — FE F2 실행 트리거
- [ ] `FoodTypeSection.tsx` 버튼 + loading/error UI 추가
- [ ] `ImportCheckPage.tsx` `handleRunF2` 콜백 + prop 전달
- [ ] `FoodTypeSection.test.tsx` 테스트 3건 추가 + pass
- [ ] 수동 E2E: F2 미실행 → 버튼 클릭 → 결과 표시 확인
- [ ] Wave 5 이식 TODO 주석 삽입

### T2 — SPEC_VAL 파싱
- [ ] `f1_collect_spec_val.py` 실행 → 20건 수집
- [ ] `spec_val_samples.json` 라벨링
- [ ] `step_c_standards.py` 파서 개선
- [ ] `test_step_c_parsing.py` edge case 20건 pass
- [ ] 골든셋 full 기준규격 ≥ 90%

### T3 — alias 매핑
- [ ] migration 019 작성 + Supabase 적용
- [ ] seed 06 작성 + 적용 (개발자 10건)
- [ ] `step_b_ingredient_matching.py` alias 조회 경로
- [ ] `test_alias_matching.py` pass
- [ ] 담당자 alias 입력 템플릿 전달
- [ ] 담당자 입력 반영 후 골든셋 full `permitted_db` ≥ 80%

### 통합
- [ ] 골든셋 full 재실행 지표 4건 동시 통과
- [ ] P4-d 가이드 + 시트 + 템플릿 3종 준비
- [ ] PR 발행 (트랙별 분리 OR 통합 — §6 의존 관계 확인 후 결정)

---

## 11. 이후 단계 연계

- 본 보완 완료 → **P4-d 담당자 QA 호출** → 게이트 통과 → **P5 Shadow 준비** (별도 계획서)
- T1 은 Wave 5 BE 이식 착수 시 **제거 대상** 으로 추적 (MEMORY.md 업데이트)
