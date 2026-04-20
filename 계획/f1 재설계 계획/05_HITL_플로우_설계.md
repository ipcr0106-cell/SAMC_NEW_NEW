# 05. HITL 플로우 설계 (HITL-0 / HITL-1 / HITL-2)

> 의존: [F1F2_재설계_명세.md §7 리스크](./F1F2_재설계_명세.md), [07_데이터_모델_변경_설계](./07_데이터_모델_변경_설계.md)
> 산출물: 백엔드 API + 프론트 컴포넌트

---

## 1. 목적

담당자 판단이 반드시 개입해야 하는 3개 지점을 시스템적으로 강제한다.

---

## 2. HITL 포인트 전체도

```
F0 파싱 완료
   ↓
[HITL-0] F0 결과 승인 (신규)  ←── 구조적 오입력 최대 방어선
   ↓
F2 실행 (식품유형 분류)
   ↓
F1 Step A → Step B → Step C → Step D
   ↓
[HITL-1] 불확실 원재료 / 자동 판정 불가 항목 검토
   ↓
[HITL-2] 최종 판정 확정 (항상 필수)
   ↓
파이프라인 완료 (F3, F4 진행 가능)
```

---

## 3. HITL-0: F0 파싱 결과 승인

### 3-1. 트리거
F0 `/parse` 완료 직후. `pipeline_steps('0').status = "completed"`.

### 3-2. 담당자 UI

| 섹션 | 내용 |
|------|------|
| 기본정보 | 제품명·수출국·OEM/최초수입/유기·주류도수 (편집 가능) |
| 원재료 목록 | 이름·비율·INS·CAS·부위·하위성분 (행 단위 편집) |
| 공정 정보 | process_codes 리스트 (추가/삭제) |
| 서류별 원본 텍스트 | OCR 원문 토글 (검증용) |
| 불일치 경고 배너 | doc_type 키워드 부족 / 제품명 문서 간 상이 등 |

### 3-3. 백엔드 API

```
PATCH /api/v1/cases/{case_id}/pipeline/feature/0
  Body: {
    final_result: ParsedResult,
    edit_reason: str
  }
  → pipeline_steps.final_result 저장, status 변경 없음

POST /api/v1/cases/{case_id}/pipeline/feature/0/approve
  Body: { approver_id, approved_at, signature? }
  → pipeline_steps.status = "approved"
  → 이후 F1/F2/F3 실행 가능
```

### 3-4. 게이트 규칙

- `status="completed"` 상태에서 F1/F2/F3 실행 시 **차단** (`F0_NOT_APPROVED` 에러)
- `status="approved"` 이후만 진행 가능
- 담당자가 편집 후 재승인 필요 (편집이 있으면 자동 `completed`로 강등)

### 3-5. 현실적 타협

- 운영 과도기: feature flag `F1_REQUIRE_HITL0_APPROVAL`로 단계적 도입
- off 상태에서는 `completed`도 허용 (기존 동작 유지)
- on 상태로 전환 시 전 담당자 교육 후 배포

---

## 4. HITL-1: 불확실 원재료 / 자동 판정 불가 항목

### 4-1. 트리거
Step B / Step C / Step D 에서 다음 중 하나 발생:
- `unidentified[]` 1건 이상
- `allow_verdict == "restricted"` (조건부) 1건 이상
- `conditional_evaluations[]` 존재 (사용조건 평가 필요)
- `overall_status == "review_needed"` (비수치 기준·단위 정규화 실패 등)
- `escalations[]` 존재 (API 장애 등)

### 4-2. 담당자 UI

| 섹션 | 내용 | 담당자 액션 |
|------|------|------------|
| 미확인 원재료 | 이름 + API 조회 결과 없음 표시 | 허용 / 금지 / 삭제 / 대체명 입력 |
| 조건부 원재료 | `restriction_condition` 표시 | 현 제품이 조건에 부합하는지 판단 |
| 자동 판정 불가 기준 | 비수치 기준값 표시 ("적합", "불검출") | 판정 입력 |
| 에스컬레이션 사유 | API 장애·키워드 누락 등 | 인지 확인 체크박스 |

### 4-3. 백엔드 API

```
POST /api/v1/cases/{case_id}/pipeline/feature/1/hitl1-decisions
  Body: {
    ingredient_decisions: list[{ name: str, decision: "allow"|"deny"|"skip" }],
    conditional_resolutions: list[...],
    qualitative_resolutions: list[...],
    escalation_acknowledgements: list[str]
  }
  → pipeline_steps.final_result 에 병합 저장
```

담당자가 모든 에스컬레이션에 응답해야 HITL-2로 진행 가능.

---

## 5. HITL-2: 최종 판정 확정 (항상 필수)

### 5-1. 트리거
Step A~D + HITL-1 완료 후 항상.

### 5-2. 담당자 UI

| 섹션 | 내용 |
|------|------|
| AI 제공 정보 요약 | `verdict` 추천 (수입가능/불가), Step별 근거 집계 |
| 법령 인용 체크박스 | Step D citations 중 판정 근거로 채택할 것 선택 |
| 최종 판정 입력 | `user_verdict`: 수입가능 / 수입불가 / 보류 |
| 사유 작성 | `final_reason` (필수, 최소 10자) |
| 전자서명 | `signer_id`, `signed_at`, 선택: 서명 이미지 |

### 5-3. 백엔드 API

```
POST /api/v1/cases/{case_id}/pipeline/feature/1/confirm
  Body: {
    user_verdict: "수입가능" | "수입불가" | "보류",
    final_reason: str,
    selected_citations: list[str],      # chunk_id 목록
    signer_id: str,
  }
  → pipeline_steps.status = "completed"
  → feature3 실행 가능
```

### 5-4. 규칙

- `user_verdict` 필수
- AI의 `verdict`와 `user_verdict`가 다르면 `final_reason` 필수
- `selected_citations`는 0개 허용 (참고만 하고 미인용 가능)
- 확정 후 수정 불가. 수정 필요 시 `/unlock` 별도 절차 (관리자 승인)

---

## 6. 상태 전이 다이어그램

```
[F0]
  completed → (HITL-0) → approved
                                ↓
[F1]
  pending → running → (HITL-1 ?) → waiting_review → (HITL-2) → completed
                                                              ↑
                                                          판정 확정
```

**pipeline_steps.status 값 확장:**

| 값 | 의미 |
|----|------|
| `pending` | 미시작 |
| `running` | 처리 중 |
| `completed` | AI 처리 완료 (단, 담당자 승인 전) |
| `approved` | HITL-0 승인 (F0 전용) |
| `waiting_review` | HITL-1 대기 |
| `needs_review` | HITL-1 필요 (에스컬레이션 있음) |
| `confirmed` | HITL-2 완료 (별칭: completed + user_verdict 존재) |
| `locked` | 확정 후 잠김 |

---

## 7. 감사 로그

모든 HITL 액션은 `f1_audit_log` 테이블에 기록:

```sql
CREATE TABLE f1_audit_log (
  id BIGSERIAL PK,
  case_id UUID,
  step TEXT,              -- 'f0' | 'f1.hitl1' | 'f1.hitl2'
  action TEXT,            -- 'approve' | 'edit' | 'confirm'
  actor_id UUID,
  before JSONB,
  after JSONB,
  reason TEXT,
  signed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

PDF 보고서 생성 시 감사 로그 첨부 → 사후 검증 가능.

---

## 8. 프론트 컴포넌트 맵

| HITL | 컴포넌트 (신규 또는 재사용) |
|------|---------------------------|
| HITL-0 | `F0ApprovalPanel` (신규), `IngredientEditor`, `BasicInfoEditor` |
| HITL-1 | `UnidentifiedIngredientReview` (기존 확장), `ConditionalResolutionPanel`, `EscalationAckList` |
| HITL-2 | `VerdictPanel`, `LawRefCheckbox`, `ConfirmActions` (기존 재사용) |

기존 `RagConflictPanel`은 Step D 역할 축소에 따라 **삭제**.

---

## 9. 테스트 포인트

- [ ] HITL-0 미승인 상태에서 F1 `/run` 호출 → 400 `F0_NOT_APPROVED`
- [ ] HITL-0 승인 후 F0 편집 → 자동 `completed`로 강등
- [ ] HITL-1 에스컬레이션 일부만 처리 → HITL-2 진행 차단
- [ ] HITL-2 `user_verdict != ai_verdict` + `final_reason` 없음 → 400
- [ ] HITL-2 confirm 후 PATCH → 403 (`locked`)
- [ ] 모든 액션이 `f1_audit_log`에 기록됨

---

## 10. 남은 결정사항

- 🟡 전자서명 형식 (담당자 ID + 타임스탬프 vs 서명 이미지 업로드)
- 🟡 HITL-0 도입 시점 (P3 vs P5) — 기존 케이스 영향 범위에 따라
- 🟡 `locked` 상태 해제 정책 (관리자 권한? 감사 기록 필수?)
- 🟡 HITL-1 "에스컬레이션 인지" UI 마찰 허용 범위 (간단 체크 vs 사유 입력 필수)
