# F1 Phase 5 프론트 QA 계획

- 작성일: 2026-04-18
- 대상 커밋: `0c381c4` (Phase 5 — 프론트 인용 UI + HITL 패널 + PDF 레포트)
- 사전 컨텍스트: `memory/project_f1_rag.md` 의 Stage 3 완료 블록, `계획/f1_RAG도입_Phase진행계획.md §Phase 5`

## 배경

Phase 5 는 커밋 `0c381c4` 로 머지되었으나, 검증은 다음 수준에 머물러 있음.

| 구분 | 상태 |
|---|---|
| pytest 121 passed, 7 skipped | ✅ |
| Vitest 17 케이스 (컴포넌트 단위) | ✅ |
| Playwright e2e 4 케이스 | ❌ **이월** (별도 PR) |
| HITL UX 실사용/브라우저 검증 | ❌ 미실시 |
| PDF §6 RAG 법령 인용 육안 검증 | ❌ 미실시 (pytest 만 통과) |
| 5 개 conflict_status 분기별 UI 육안 검증 | ❌ 미실시 |

"화면에서 실제로 어떻게 보이는지" 검증이 전무한 상태 → 본 QA 의 목적.

## A. Playwright e2e 4 시나리오 (명시 이월분)

| ID | 시나리오 | `conflict_status` | 기대 UI | 비고 |
|---|---|---|---|---|
| E1 | agreed | `agreed` | LawCitationList 표시, RagConflictPanel **숨김**, `status=waiting_review` | 해피패스 |
| E2 | conflict | `conflict` | RagConflictPanel **노출** + HITL 버튼 2 개, `status=needs_review` | HITL 필수 |
| E3 | rag_supplemented | `rag_supplemented` | citation + "RAG 보완" 배지, `status=needs_review` | exact=unidentified & RAG=판정 |
| E4 | rag_unavailable | `rag_unavailable` | citation 없음, 경고 배너, `status=waiting_review` | timeout / 키 없음 |

**픽스처 전략**: `run_feature1_with_rag` 실 호출 대신 MSW 또는 FastAPI 테스트 서버 고정 응답 사용. 현재 MSW 미설치 — 도입부터 0.2 일.

## B. HITL UX 수동 QA — `RagConflictPanel`

| 체크 | 확인 포인트 |
|---|---|
| B1 | "RAG 수용" 클릭 → `PATCH /feature/1` 페이로드에 `hitl_decision.accepted_source="rag"` 포함 |
| B2 | "Exact 유지" 클릭 → `accepted_source="exact"` + 원본 verdict 보존 |
| B3 | 낙관적 UI (pending / loading disabled) 중복 클릭 방지 |
| B4 | 네트워크 에러 시 롤백 + 토스트/배너 에러 메시지 |
| B5 | 결정 직후 `status` 가 `needs_review` → `waiting_review` 갱신 & 패널 사라짐 |
| B6 | 새로고침 후에도 HITL 결과 영속 (DB 반영) |

참고: HITL 전용 엔드포인트 없음 — 기존 `updateImportCheckResult` (PATCH `/feature/1`) 재사용.

## C. `LawCitationList` / `LawCitationCard` 렌더 QA

| 체크 | 확인 포인트 |
|---|---|
| C1 | citation=0 빈 상태 ("관련 법령 인용 없음" 등) |
| C2 | citation ≥ 5 레이아웃 (카드 스택 / 스크롤) |
| C3 | `namespace` 한글 라벨 매핑 (`additive_code_text` → "식품첨가물공전" 등) |
| C4 | `section_path` / `regulation_id` **null 안전** (Phase 4-A 메모 #4 경고) |
| C5 | `score` 소수점 자리수 일관 (0.5xx) |
| C6 | `reasoning` 긴 텍스트 줄바꿈 / overflow |
| C7 | 한글 폰트 깨짐 없음 |

## D. `ImportCheckPage` 통합 QA

| 체크 | 확인 포인트 |
|---|---|
| D1 | 5 개 `conflict_status` 분기별 섹션 조건부 배치 (`agreed` / `conflict` / `rag_supplemented` / `rag_unavailable` / `rag_skipped`) |
| D2 | 기존 결과 카드와 신규 섹션 시각적 겹침 / 간격 |
| D3 | Tailwind v3 + lucide-react 외 의존성 들어가지 않았는지 (디자인 시스템 준수) |

## E. PDF 레포트 §6 RAG 법령 인용 섹션 (pytest 통과 ≠ 육안 통과)

| 체크 | 확인 포인트 |
|---|---|
| E1 | 한글 폰트 렌더링 (PyMuPDF 한글 깨짐 주의 — 커밋 `85e8d4f` 가 같은 부류 문제) |
| E2 | `namespace` 그룹 헤더 정상 구획 |
| E3 | 400 자 truncate "…" 표시 및 경계 어색함 |
| E4 | `conflict_status` / `rag_verdict` / `rag_reasoning` 3 개 라벨 번역 / 정렬 |
| E5 | citation=0 일 때 섹션 자체 생략 vs 빈 섹션 |

위치: `backend/routers/feature1.py:_build_report_pdf` 의 "6. RAG 법령 인용" 섹션.

## F. 회귀 (Non-Phase 5 영향)

| 체크 | 확인 포인트 |
|---|---|
| F1 | HITL 이전 구 임포트 건 열람 시 신규 섹션 안전 숨김 (`Feature1Internal` flat 필드 `undefined` 대응) |
| F2 | `types.ts` `Feature1Response.status` Union 확장이 타 화면에서 미처리 warning 없음 (vitest typecheck) |
| F3 | `updateImportCheckResult` 재사용으로 기존 승인 / 반려 플로우 회귀 없음 |

## 실행 전 선결 과제 (QA 착수 블로커)

1. **MSW 또는 FastAPI 로컬 목** — 현재 미설치. Playwright 진입 전 0.2~0.5 일 필요
2. **Playwright 자체 미설치** — `@playwright/test` 설치 + config + CI 제외 결정 필요
3. **실 RAG 호출 키** — 수동 E 카테고리 PDF 생성 시 `F1_OPENAI_API_KEY` + `F1_PINECONE_API_KEY` 필요

## 우선순위 제안

| 순위 | 범위 | 예상 소요 | 인프라 블로커 |
|---|---|---|---|
| **1 순위** | **B (HITL UX) + E (PDF 육안)** | 반나절 | 없음 — 바로 가능 |
| 2 순위 | A (Playwright e2e) | 1 일 | MSW + Playwright 도입 포함 |
| 3 순위 | C · D | 부수 검증 | 1 / 2 순위와 병행 |
| 후순위 | F (회귀) | 최종 머지 전 스윕 | — |

## 성공 기준

- B 모든 체크 PASS + 스크린샷 또는 녹화 첨부
- E 모든 체크 PASS + 실제 PDF 파일 첨부
- A 4 케이스 전부 GREEN + CI 통합 여부 별도 결정
- 발견 버그는 이슈 또는 별도 PR 로 분리 (본 PR 긁어쓰지 말 것)

## 잔여 기술 부채 (본 QA 범위 외)

- 골든셋 v3 100 건 확장 + g007 / g016 재평가 (Stage 4 선결)
- admin `law_update` 실 PDF 업로드 E2E (Phase 4-B-2 이월)
- Shadow mode 파일럿 1~2 주 (Stage 4 트리거)
- F1 수입판정 응답 p95 > 10s 해결 (Redis 캐싱, OPEN-4)

---

## QA 발견 이슈 (2026-04-18)

### P0 — `pipeline_steps.status` CHECK 제약 누락 (migration 014 로 해결)

- **증상**: `conflict` / `rag_supplemented` 케이스 실행 시 500 (`postgrest.exceptions.APIError`, code 23514)
- **위치**: `backend/db/combined_schema.sql:91` CHECK 에 `needs_review` 미포함
- **원인**: Phase 5 커밋 `0c381c4` 에서 [routers/feature1.py:400](../backend/routers/feature1.py:400) 가 `status="needs_review"` 로 설정하나 DB 제약이 Phase 5 이전 상태
- **해결**: `backend/db/migrations/014_pipeline_steps_needs_review.sql` 작성 완료 — Supabase Studio(bnfgbwwibnljynwgkgpt) SQL Editor 에서 수동 실행 필요
- **QA 영향**: `rag_supplemented` / `conflict` 분기 전부 블로커. migration 014 적용 전 B·E 수행 불가
- **재현 데이터** (2026-04-18 QA):
  - payload: `backend/tests/qa_payload_supplemented.json` (설탕 50%, 당류가공품)
  - 응답: 500, `Internal Server Error` + postgrest API error

### P1 — verdict 로직 불일치 (별도 추적)

- **증상**: `aggregation.permitted=1`, `fail_reasons=[]`, `conflict_status="agreed"` 임에도 `verdict="수입불가"`, `import_possible=false`
- **재현 케이스**: agreed (쌀 99%, 곡류) — `backend/tests/qa_payload_agreed.json`
- **의심**: `standards_check` 의 `status="no_threshold"` 항목이 `verdict` 계산에 반영돼 "수입불가" 로 세팅
- **범위**: Phase 5 아님 (기존 F1 verdict 판정 로직)
- **조치**: 별도 티켓 발행 — 본 QA 에서는 기록만

### QA 진행 로그

| 일시 | 케이스 | HTTP | conflict_status | 비고 |
|---|---|---|---|---|
| 2026-04-18 00:36 | agreed (쌀) | 200 (14.6s) | `agreed` | `rag_verdict=permitted`, `law_citations=[]`, verdict 로직 P1 이슈 감지 |
| 2026-04-18 00:37 | rag_skipped (대마초) | 200 (0.22s) | `rag_skipped` | Step 0 차단 정상, `waiting_review` |
| 2026-04-18 00:37 | rag_supplemented (설탕) | **500 (8.1s)** | — | P0 DB CHECK 위반 — migration 014 필요 |

---

*본 문서는 실행 계획 + QA 진행 기록을 담고 있으며, 실제 QA 착수는 별도 지시로 진행.*
