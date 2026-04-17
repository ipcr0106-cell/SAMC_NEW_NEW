# F1 RAG 도입 — Phase 진행 계획

> 총괄: [f1_RAG도입계획_총괄.md](f1_RAG도입계획_총괄.md)
> 백엔드: [f1_RAG도입계획_백엔드.md](f1_RAG도입계획_백엔드.md)
> 프론트: [f1_RAG도입계획_프론트.md](f1_RAG도입계획_프론트.md)
> 전처리: [f1_RAG도입계획_전처리.md](f1_RAG도입계획_전처리.md)
>
> 개정 (2026-04-17): critic 검토 반영 — Phase 4 분할(4-A/4-B), admin_law_update 작업 추가, 골든셋 30건 확대, S2(HITL) 결정 반영
>
> **진행 상태 (2026-04-17)**: ✅ Phase 1~4-A · ✅ 4-B-1~3d · ✅ **Phase 4-B-3e: 100건 골든셋 + 5모델 비교 + Step 0 버그 수정 → gpt-5.4-mini+few v2 채택 (76.0%)** · ⏳ **Phase 5 대기**
> Pinecone samc-law-f1: 2148건 적재 완료. Phase 4-A integration 테스트 11/11 PASSED (실제 Pinecone + OpenAI). 세션 이어받기 시 `memory/project_f1_rag.md` 먼저 확인.

## Phase 의존 관계

```
Phase 1 (인프라) ──┬──> Phase 2 (복제)  ──┐
                   └──> Phase 3 (신규)  ──┴──> Phase 4-A (판정 모듈) ──> Phase 4-B (통합) ──> Phase 5 (프론트+검증)
```

Phase 2와 3은 병렬 가능. Phase 4-A와 Phase 5의 컴포넌트 작성은 일부 병렬 가능 (타입 정의 후).

---

## Phase 1 — 인프라 + 클라이언트

**목표**: Pinecone 인덱스 + env + 클라이언트 모듈 + 미러 테이블 준비.

### 작업 목록

- [ ] **1-1.** `backend/scripts/f1_create_pinecone_index.py` 작성 (`pinecone>=8.0.0` API 검증)
- [ ] **1-2.** 인덱스 생성 실행 + `describe_index_stats` 검증
- [ ] **1-3.** `backend/.env.example` 갱신 (F1_OPENAI_*, F1_PINECONE_*, F1_RAG_TOP_K 추가, F1_ANTHROPIC_API_KEY 제거)
- [ ] **1-4.** `backend/requirements.txt` — `tiktoken>=0.7.0` 1줄 추가만 (다른 패키지 이미 존재)
- [ ] **1-5.** `backend/services/f1_openai_client.py` 작성 (JSON mode 적용)
- [ ] **1-6.** `backend/services/f1_pinecone_client.py` 작성 (asyncio 병렬 search_multi)
- [ ] **1-7.** `backend/db/migrations/010_f1_law_chunks.sql` 작성
- [ ] **1-8.** Supabase SQL Editor에 010 마이그레이션 적용
- [ ] **1-9.** 단위 테스트: 클라이언트 mock 호출 (실 Pinecone/OpenAI 호출 없이)
- [ ] **1-10.** 커밋: `feat(F1-rag): Phase 1 — Pinecone 인덱스 + 클라이언트 + 미러 테이블`

### 산출물

| 항목 | 위치 |
|---|---|
| 인덱스 생성 스크립트 | `backend/scripts/f1_create_pinecone_index.py` |
| OpenAI 클라이언트 | `backend/services/f1_openai_client.py` |
| Pinecone 클라이언트 | `backend/services/f1_pinecone_client.py` |
| 마이그레이션 SQL | `backend/db/migrations/010_f1_law_chunks.sql` |
| env 예제 | `backend/.env.example` |
| requirements | `backend/requirements.txt` (tiktoken 추가) |

### 검증 기준

- [ ] `pc.list_indexes()` 호출 시 `samc-law-f1` 포함
- [ ] 인덱스 차원 1536, 메트릭 cosine 확인
- [ ] Supabase에 `f1_law_chunks` 테이블 + 3개 인덱스 + RLS 정책 존재
- [ ] 클라이언트 모듈 단위 테스트 통과

### 예상 일정 (1.5일)

| 작업 | 시간 |
|---|---|
| 스크립트 작성 + 인덱스 생성 + v8 API 검증 | 0.5일 |
| 클라이언트 모듈 + 테스트 | 0.5일 |
| 마이그레이션 작성 + 적용 | 0.5일 |

---

## Phase 2 — 데이터 이전 (newsamc → samc-law-f1)

**목표**: newsamc `samc-law` 인덱스에서 F1 관련 4개 namespace 484건을 `samc-law-f1`으로 복제 + Postgres 미러.

### 작업 목록

- [ ] **2-1.** `backend/scripts/f1_replicate_from_newsamc.py` 작성
- [ ] **2-2.** dry-run 모드로 1개 namespace (예: temporary_standard 74건) 우선 복제 → Pinecone + 미러 테이블 검증
- [ ] **2-3.** 나머지 3개 namespace 전체 복제 실행 (food_code_text 140 + functional_labeling 18 + health_food_text 252)
- [ ] **2-4.** `f1_verify_replication.py` 작성 + 실행 (건수/샘플 텍스트 일치 검증)
- [ ] **2-5.** 미러 테이블 건수 확인 (`SELECT pinecone_namespace, COUNT(*) FROM f1_law_chunks GROUP BY 1`)
- [ ] **2-6.** 검증 리포트 작성 (`계획/f1_RAG_Phase2_검증리포트.md`)
- [ ] **2-7.** 커밋: `feat(F1-rag): Phase 2 — newsamc 484건 복제`

### 산출물

| 항목 | 위치 |
|---|---|
| 복제 스크립트 | `backend/scripts/f1_replicate_from_newsamc.py` |
| 검증 스크립트 | `backend/scripts/f1_verify_replication.py` |
| 검증 리포트 | `계획/f1_RAG_Phase2_검증리포트.md` |

### 검증 기준

| namespace | 기대 건수 | Pinecone 실측 | Postgres 미러 |
|---|---|---|---|
| food_code_text | 140 | TBD | TBD |
| functional_labeling | 18 | TBD | TBD |
| temporary_standard | 74 | TBD | TBD |
| health_food_text | 252 | TBD | TBD |
| **합계** | **484** | **TBD** | **TBD** |

- [ ] 모든 namespace 건수 일치
- [ ] 랜덤 샘플 5개씩 (총 20개) text 메타 100% 일치
- [ ] dry-run 검증 통과 후에만 전체 실행

### 예상 일정 (1.3일)

| 작업 | 시간 |
|---|---|
| 스크립트 작성 + dry-run | 0.5일 |
| 전체 복제 실행 (네트워크 대기 포함) | 0.3일 |
| 검증 + 리포트 | 0.5일 |

### 리스크

- newsamc samc-law의 metadata 구조가 newsamc 코드와 다를 가능성 → dry-run에서 검증
- Pinecone API rate limit → 배치 100 + 슬립 100ms 적용 (필요 시)

---

## Phase 3 — 식품첨가물공전 신규 임베딩

**목표**: 식품첨가물공전 PDF → 청킹 → 임베딩 → `samc-law-f1/additive_code_text`.

### 작업 목록

- [ ] **3-1.** `backend/services/f1_chunking.py` 작성 (newsamc TS 포팅, tiktoken 정확 카운팅)
- [ ] **3-2.** 청킹 단위 테스트 5건 작성 + 통과
- [ ] **3-3.** 식품첨가물공전 PDF 파일 확보 (운영팀/공식 사이트)
- [ ] **3-4.** 기존 `backend/utils/chunker.pdf_to_markdown` 사용 시도 → 출력 품질 시각 검수
- [ ] **3-5.** (조건부) PDF 변환 품질 부족 시 별도 라이브러리(`pymupdf4llm`) 검토 → requirements 추가
- [ ] **3-6.** `backend/scripts/f1_embed_additive_code.py` 작성
- [ ] **3-7.** 샘플 10페이지 dry-run → 청크 품질 시각 검수
- [ ] **3-8.** 전체 임베딩 + Pinecone upsert + Postgres 미러
- [ ] **3-9.** 검증 (총 청크 수, 샘플 검색 — 키워드 "벤조산나트륨", "사용 기준" 등으로)
- [ ] **3-10.** 커밋: `feat(F1-rag): Phase 3 — 식품첨가물공전 임베딩`

### 산출물

| 항목 | 위치 |
|---|---|
| 청킹 모듈 | `backend/services/f1_chunking.py` |
| 임베딩 스크립트 | `backend/scripts/f1_embed_additive_code.py` |
| PDF 원본 | `data/laws/식품첨가물공전.pdf` (또는 Supabase Storage) |
| 청킹 테스트 | `backend/tests/services/test_f1_chunking.py` |

### 검증 기준

- [ ] 청크 토큰 분포: 모든 청크가 200~1500 범위 (또는 슬라이딩 윈도우 케이스만 예외)
- [ ] Pinecone `additive_code_text` namespace에 임베딩 적재
- [ ] 미러 테이블 `f1_law_chunks` 건수 일치
- [ ] 임의 키워드 검색 → top-5에 관련 청크 노출

### 예상 일정 (2.3일)

| 작업 | 시간 |
|---|---|
| 청킹 포팅 + 테스트 | 1일 |
| PDF 변환 품질 검증 | 0.5일 |
| 임베딩 스크립트 + 실행 | 0.5일 |
| 검증 | 0.3일 |

### 리스크

- PDF 텍스트 추출 품질 (스캔 PDF면 OCR 필요)
- 청킹 결과 너무 잘게 쪼개지면 컨텍스트 손실 → 병합 임계 조정 가능

---

## Phase 4-A — 판정 모듈 (RAG 단독)

**목표**: RAG 판정 모듈 + Pydantic 모델 작성. 통합은 Phase 4-B.

### 작업 목록

- [ ] **4A-1.** `backend/models/f1_law_citation.py` 작성 (`LawCitation`, `RagJudgement`, `ConflictStatus`)
- [ ] **4A-2.** `backend/services/f1_rag_judge.py` 작성
  - `_build_query_text()`
  - `run(payload) -> RagJudgement` (실패 시 verdict="error" 반환, 예외 던지지 않음)
- [ ] **4A-3.** Integration 테스트: 실제 Pinecone + OpenAI 호출 (테스트 인덱스 또는 실 인덱스, 5건 케이스)
- [ ] **4A-4.** `chat_json()` JSON mode 검증 (응답이 항상 valid JSON인지)
- [ ] **4A-5.** 커밋: `feat(F1-rag): Phase 4-A — RAG 판정 모듈`

### 산출물

| 항목 | 위치 |
|---|---|
| Pydantic 모델 | `backend/models/f1_law_citation.py` |
| 판정 모듈 | `backend/services/f1_rag_judge.py` |
| 통합 테스트 | `backend/tests/services/test_f1_rag_judge.py` |

### 검증 기준

- [ ] `pytest backend/tests/services/test_f1_rag_judge.py` 통과
- [ ] 5건 케이스에서 모두 `RagJudgement` 반환 (verdict="error" 포함)
- [ ] JSON 파싱 실패 시에도 예외 없이 verdict="error" 반환 확인
- [ ] search_multi 비동기 호출 → 단일 호출 대비 레이턴시 단축 측정

### 예상 일정 (1일)

---

## Phase 4-B — 통합 + law_extractor 제거

**목표**: F1 service에 RAG+HITL 결합, 응답에 RAG 필드 추가, `law_extractor` + `admin_law_update.F1` 폐기.

### 작업 목록

- [ ] **4B-1.** `backend/services/feature1.py`에 `run_feature1_with_rag()` async 함수 추가 (기존 `run_feature1` 유지)
  - HITL 비교 로직: `_derive_exact_verdict(out)` + conflict 판정
- [ ] **4B-2.** `backend/routers/feature1.py:_to_pipeline_result()` 시그니처 확장 (rag, conflict_status 파라미터, default 후방 호환)
- [ ] **4B-3.** `backend/routers/feature1.py:run_feature1_endpoint` async로 변경 + HITL status 결정 로직
- [ ] **4B-4.** `backend/routers/admin_law_update.py:_get_f1_clients()` 교체 (Anthropic → OpenAI+Pinecone+Supabase)
- [ ] **4B-5.** `backend/routers/admin_law_update.py:_run_f1_preprocess()` 교체 (RAG 임베딩 흐름으로)
- [ ] **4B-6.** `_law_name_to_namespace` 매핑 함수 추가
- [ ] **4B-7.** `backend/utils/chunker.py:14` 주석 정리
- [ ] **4B-8.** `backend/services/law_extractor.py` 삭제
- [ ] **4B-9.** 관련 테스트 (`tests/services/test_law_extractor*.py`) 삭제
- [ ] **4B-10.** `F1_ANTHROPIC_API_KEY` 모든 흔적 제거 (`grep -ri "F1_ANTHROPIC\|law_extractor" backend/` 결과 0건)
- [ ] **4B-11.** 골든셋 작성: **30건+, 조건부 케이스 비율 ≥ 40%**
  - 허용 원료 케이스 (10건)
  - 금지 원료 케이스 (5건)
  - 조건부 원료 (가열/발효/도수) 케이스 (12건)
  - 미등록 원료 케이스 (3건)
- [ ] **4B-12.** 골든셋 평가: Claude 시절 결과 vs OpenAI 결과 일치율 측정
- [ ] **4B-13.** 미결사항 결정 (top-K, 모델, exact vs RAG 우선순위 미세 조정)
- [ ] **4B-14.** 커밋: `feat(F1-rag): Phase 4-B — HITL 통합 + law_extractor 제거`

### 산출물

| 항목 | 위치 |
|---|---|
| 통합 함수 | `backend/services/feature1.py:run_feature1_with_rag` |
| 라우터 통합 | `backend/routers/feature1.py` 수정 |
| admin 흐름 교체 | `backend/routers/admin_law_update.py` 수정 |
| 폐기 | `backend/services/law_extractor.py` 삭제 |
| 골든셋 평가 리포트 | `계획/f1_RAG_Phase4B_평가리포트.md` |

### 검증 기준

- [ ] `pytest backend/tests/` 전체 통과
- [ ] `/api/v1/cases/{id}/pipeline/feature/1/run` 응답 `_internal`에 `rag_verdict`, `rag_reasoning`, `law_citations`, `conflict_status` 포함
- [ ] HITL 충돌 시 응답 `status === "needs_review"` 확인
- [ ] 응답 시간 p95 < 5초 (gpt-4o-mini 기준)
- [ ] 골든셋 일치율 ≥ 80% (목표, 실제 결과 보고 결정)
- [ ] `grep -ri "law_extractor\|F1_ANTHROPIC_API_KEY" backend/` 결과 0건
- [ ] admin UI에서 F1 법령 업로드 → RAG 임베딩 정상 적재 확인

### 예상 일정 (3일)

| 작업 | 시간 |
|---|---|
| feature1.py 통합 + 라우터 갱신 | 0.5일 |
| admin_law_update 교체 | 0.5일 |
| law_extractor 제거 + 정리 | 0.5일 |
| 골든셋 작성 (30건+) | 0.5일 |
| 골든셋 평가 + 리포트 | 1일 |

### 리스크

- OpenAI 판정 품질이 Claude 대비 저하 → 프롬프트 튜닝 + few-shot 추가, 안 되면 gpt-4o로 격상
- HITL 결정 화면이 미완성 상태에서 needs_review 케이스가 계속 쌓일 가능성 → Phase 5와 짧은 간격으로 배포

---

## Phase 5 — 프론트 + 검증

**목표**: F1 결과 화면에 법령 인용 + HITL 충돌 결정 패널 추가, e2e 검증, 문서 갱신.

### 작업 목록

- [ ] **5-1.** `frontend/features/feature1/types.ts` 갱신 (status Union에 needs_review 추가, Feature1Internal에 RAG 필드, LawCitation/RagVerdict/ConflictStatus 타입)
- [ ] **5-2.** `frontend/features/feature1/api/importCheck.ts` 응답 타입 적용 확인 (호환)
- [ ] **5-3.** `LawCitationCard.tsx` 컴포넌트 작성
- [ ] **5-4.** `LawCitationList.tsx` 컴포넌트 작성
- [ ] **5-5.** `RagConflictPanel.tsx` 컴포넌트 작성 (PATCH 호출 포함)
- [ ] **5-6.** `ImportCheckPage.tsx`에 인용 섹션 + 충돌 패널 통합
- [ ] **5-7.** Vitest 단위 테스트 (3개 컴포넌트)
- [ ] **5-8.** Playwright e2e: 4가지 conflict_status 케이스 (agreed/conflict/rag_supplemented/rag_unavailable)
- [ ] **5-9.** PDF 레포트(`/feature/1/report`)에 RAG 인용 섹션 추가 (`_build_report_pdf` 수정)
- [ ] **5-10.** `MERGE_GUIDE.md` 갱신 (F1 섹션, env 표, 인덱스 표)
- [ ] **5-11.** `f1_수정_요청_사항.md` 갱신 (RAG 도입 후속 사항 반영)
- [ ] **5-12.** 커밋: `feat(F1-rag): Phase 5 — 프론트 인용 UI + HITL 결정 패널 + 문서 갱신`

### 산출물

| 항목 | 위치 |
|---|---|
| 카드 컴포넌트 | `frontend/features/feature1/components/LawCitationCard.tsx` |
| 목록 컴포넌트 | `frontend/features/feature1/components/LawCitationList.tsx` |
| 충돌 패널 | `frontend/features/feature1/components/RagConflictPanel.tsx` |
| 타입 | `frontend/features/feature1/types.ts` |
| MERGE_GUIDE 갱신 | `MERGE_GUIDE.md` |
| F1 PDF 레포트 갱신 | `backend/routers/feature1.py:_build_report_pdf` |

### 검증 기준

- [ ] `npm run typecheck` 통과
- [ ] `npm test` 통과 (Vitest)
- [ ] e2e: 4가지 conflict 케이스 모두 정상 표시 + 결정 PATCH 동작
- [ ] PDF 레포트에 인용 섹션 표시
- [ ] MERGE_GUIDE.md F1 Pinecone 인덱스 표 업데이트
- [ ] 다른 기능 회귀 테스트 통과

### 예상 일정 (2.7일)

| 작업 | 시간 |
|---|---|
| 타입 + API | 0.3일 |
| 컴포넌트 3개 + 통합 | 1.2일 |
| 테스트 | 0.5일 |
| PDF 레포트 갱신 | 0.2일 |
| 문서 갱신 | 0.5일 |

---

## 전체 일정 요약

| Phase | 일수 | 누적 | 비고 |
|---|---|---|---|
| 1 | 1.5 | 1.5 | 인프라 |
| 2 + 3 (병렬) | max(1.3, 2.3) = 2.3 | 3.8 | 데이터 |
| 4-A | 1.0 | 4.8 | RAG 모듈 |
| 4-B | 3.0 | 7.8 | 통합 + 골든셋 |
| 5 | 2.7 | **10.5일** | 프론트 + 검증 |

→ 약 **2~2.5주** (영업일 기준, 1인 기준).

## PR 분할 전략

| PR | 포함 Phase | 검토자 |
|---|---|---|
| PR #1 | Phase 1 | F1 담당 + 인프라 검토 |
| PR #2 | Phase 2 + 3 | F1 담당 |
| PR #3 | Phase 4-A | F1 담당 |
| PR #4 | Phase 4-B | F1 담당 + PM (골든셋 평가 동석) |
| PR #5 | Phase 5 | F1 담당 + 디자인 검토 |

## 결정 게이트

다음 시점에서 전체 진행 여부 재검토:

| 시점 | 판단 기준 |
|---|---|
| Phase 2 완료 후 | 복제 실패율 > 5% → 재임베딩 전략 검토 |
| Phase 3 완료 후 | 청킹 품질 불만족 → 청킹 파라미터 조정 |
| Phase 4-A 완료 후 | RAG 모듈 단독 정상 동작 확인 → 4-B 진행 |
| Phase 4-B 골든셋 후 | 일치율 < 60% → OpenAI 모델 격상(gpt-4o) 또는 프롬프트 재설계 |
| Phase 5 e2e 후 | 응답 시간 p95 > 8초 → 캐싱 도입 |

## 미결 사항 추적

| ID | 사항 | 결정 시점 |
|---|---|---|
| OPEN-1 | top-K 값 (3 / 5 / 10) | Phase 4-B 중 |
| OPEN-2 | OpenAI 모델 (gpt-4o-mini vs gpt-4o) | Phase 4-B 골든셋 후 |
| OPEN-3 | 임계값 수동 입력 admin UI 필요성 | Phase 5 후 별도 PR |
| OPEN-4 | 캐싱 도입 여부 | Phase 5 e2e 후 |
| OPEN-5 | f1_* 시드 110건 향후 갱신 방식 | Phase 4-B 후 |
| ~~OPEN-6 (S2)~~ | ~~exact vs RAG 충돌 우선순위~~ | **결정 완료: HITL** (총괄 §2.7) |

## 결정 완료 사항 (이전 미결 → 확정)

| ID | 결정 |
|---|---|
| S1 | 통합 위치: Step 0 미적중 시에만 RAG 호출, `run_feature1_with_rag()` 별도 entry, 결과는 `_to_pipeline_result()`에서 통합 |
| S2 | 충돌 처리: HITL — exact ≠ RAG 시 `status="needs_review"`, 사람이 PATCH로 결정 |
