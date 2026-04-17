# F1 RAG 도입 계획 — 총괄

## 작성 메타

| 항목 | 값 |
|---|---|
| 작성일 | 2026-04-17 |
| 개정 | 2026-04-17 — critic 검토 반영 (실제 파일 검증 + HITL 결정) |
| 작성자 | 병찬 (F1) |
| 상태 | 계획 단계 — 구현 전 검토용 |
| 브랜치 (예정) | `f1-rag` |
| 의존 문서 | [MERGE_GUIDE.md](../MERGE_GUIDE.md), [계획/팀_컨벤션_룰.md](팀_컨벤션_룰.md), [f1_수정_요청_사항.md](../f1_수정_요청_사항.md) |
| 선행 작업 | F1 asyncpg → supabase-py 전환 완료 (커밋 `1db0ddc` 직전) |

## 1. 배경

### 1.1 현재 F1 구조 (RAG 미사용)

```
PDF/HWP 법령
  → utils.chunker.pdf_to_markdown + chunk_law_markdown
  → law_extractor.extract_thresholds_bulk()  (Claude LLM, 자동 임계값 추출)
  → 구조화 JSON
  → Supabase f1_* 테이블 (allowed/forbidden/additive_limits/safety_standards)

판정:
  run_feature1(ingredients, food_type, process_conditions) -> Feature1Output
    ├─ Step 0: check_forbidden_first → 금지원료 적중 시 즉시 종료
    ├─ Step 1 + 1-A + 1-B: run_step1(ingredients) → 정확매칭 + 조건평가
    └─ Step 3: run_step3(ingredients, food_type, process) → 기준치 검증
```

[backend/services/feature1.py:29-128](../backend/services/feature1.py), [MERGE_GUIDE.md:324](../MERGE_GUIDE.md).

### 1.2 한계

| 한계 | 영향 |
|---|---|
| f1_* 시드 110건 외 원료는 "미등록"(`unidentified`) → 사람 수기 검토 | 운영 부담 |
| 별칭·오타·영문명 매칭 불가 | 사용자 입력 다양성 대응 X |
| 판정 근거로 법령 원문 인용 불가 | 신뢰성 부족 |
| Claude API 사용 불가 (조직 정책) | `law_extractor` 모듈 운용 중단 필요 |
| `admin_law_update._run_f1_preprocess`가 Claude 의존 | admin 법령 업로드 흐름 자체가 막힘 |

### 1.3 도입 결정 사유

1. **Claude API 사용 불가** → `law_extractor` + `admin_law_update.F1` 흐름 폐기 결정
2. **newsamc(`C:\GITHUB\newsamc`) 자산 활용** → 검증된 청킹 알고리즘 + Pinecone `samc-law` 인덱스(942건) 보유
3. **팀 컨벤션 일관성** → F2/F3/F4/F5 모두 Pinecone 사용, F1만 미사용 → 통일

### 1.4 핵심 변화

| 영역 | Before | After |
|---|---|---|
| 메인 판정 엔진 | f1_* 테이블 정확매칭 (Step 0/1/3) | **정확매칭 + RAG 병행 → HITL 비교** |
| 보정/판단 LLM | Claude (law_extractor 내부) | OpenAI Chat Completions |
| 임계값 자동 추출 | `law_extractor.extract_thresholds_bulk()` | **폐기** |
| 임계값 데이터 입력 | 자동 + 시드 | 시드 110건 유지, 추가 임계값은 admin UI 수동 (별도 PR) |
| 판정 근거 | `law_refs[]` (단순 문자열) | `law_citations[]` (청크 인용 + 점수) |
| f1_* 테이블 | 메인 판정 데이터 | **유지** — 시드 110건 보조 매칭용 |
| 충돌 처리 | N/A | **HITL** — exact ≠ RAG일 때 `needs_review` 상태로 사람 결정 위임 |
| `admin_law_update.F1` 경로 | Claude 기준치 추출 | RAG 임베딩 (`samc-law-f1` 적재) |

## 2. 결정사항 종합

### 2.1 Pinecone 인덱스

| 항목 | 값 | 비고 |
|---|---|---|
| 인덱스명 | `samc-law-f1` | F1 전용 신규 |
| 차원 | 1536 | newsamc 동일 |
| 메트릭 | cosine | newsamc 동일 |
| 임베딩 모델 | `text-embedding-3-small` (OpenAI) | newsamc 동일 |
| 클라우드/리전 | aws / us-east-1 | newsamc 인덱스들과 동일 |
| 타입 | dense, serverless | |

### 2.2 Namespace 구성 (5개)

| namespace | 법령 | 데이터 출처 | 예상 건수 |
|---|---|---|---|
| `food_code_text` | 식품공전 | newsamc 복제 | 140 |
| `additive_code_text` | 식품첨가물공전 | **신규 PDF 임베딩** | 미정 |
| `functional_labeling` | 건강기능 표시기준 | newsamc 복제 | 18 |
| `temporary_standard` | 식품등의 한시적 기준 및 규격 | newsamc 복제 | 74 |
| `health_food_text` | 건강기능식품공전 본문 | newsamc 복제 | 252 |

→ 복제 합계 484건 + 식품첨가물공전 신규.

### 2.3 데이터 이전 전략

newsamc `samc-law` 인덱스 → `samc-law-f1`로 fetch+upsert 복제. **Pinecone 계정 동일 확인** (조사 결과: newsamc PINECONE_API_KEY = 회사 공용 계정). 차원 동일(1536)이므로 벡터 그대로 재사용. 식품첨가물공전만 별도 PDF 임베딩.

### 2.4 RAG 흐름 (HITL 통합)

```
사용자 입력 (제품/원료 정보)
   ↓
run_feature1() — 기존 파이프라인 그대로
   ├─ Step 0: 금지원료 매칭
   ├─ Step 1: 정확매칭 (f1_* 테이블, 110건)
   └─ Step 3: 기준치 검증
   ↓
Feature1Output (기존 모델, exact_match 결과)
   ↓
신규: f1_rag_judge.run() — Step 0 비적중 시에만 호출 (금지원료 즉시종료 보존)
   ├─ 임베딩 (OpenAI text-embedding-3-small)
   ├─ Pinecone 검색 (samc-law-f1, 5 namespace 병렬, top_k=5)
   └─ OpenAI Chat (gpt-4o-mini, JSON mode, 청크 컨텍스트 + 규칙)
   ↓
RagJudgement { rag_verdict, rag_reasoning, law_citations[] }
   ↓
HITL 비교 (services/feature1.py 또는 routers/feature1.py)
   ├─ exact_verdict == rag_verdict → conflict_status="agreed", status="waiting_review"
   ├─ exact_verdict != rag_verdict → conflict_status="conflict", status="needs_review"
   └─ rag 호출 실패 → conflict_status="rag_unavailable", status="waiting_review"
   ↓
ai_result = _to_pipeline_result(Feature1Output, rag_judgement)
   ↓
pipeline_steps에 저장
   ↓
프론트 UI: 판정 카드 + 인용 카드 + (충돌 시) 사람 결정 패널
   ↓
사람이 PATCH로 final_result 확정 → POST /confirm으로 다음 단계 진행
```

### 2.5 Postgres 미러 테이블

| 항목 | 값 |
|---|---|
| 테이블명 | `f1_law_chunks` |
| 마이그레이션 | `backend/db/migrations/010_f1_law_chunks.sql` |
| 용도 | admin UI 목록 조회, 재임베딩, 삭제, 메타 검색 |
| 주요 컬럼 | `id`, `vector_id`, `regulation_id`, `pinecone_namespace`, `section_path`, `text`, `token_count`, `chunk_index`, `total_chunks`, `embedded_at`, `created_at` |

### 2.6 환경 변수 (F1_ prefix 컨벤션)

| 키 | 용도 | 값 예시 |
|---|---|---|
| `F1_OPENAI_API_KEY` | 임베딩 + Chat Completions | `sk-proj-...` |
| `F1_OPENAI_CHAT_MODEL` | 판정 LLM 모델명 | `gpt-4o-mini` (기본) |
| `F1_OPENAI_EMBED_MODEL` | 임베딩 모델명 | `text-embedding-3-small` |
| `F1_PINECONE_API_KEY` | Pinecone 접근 (회사 공용 계정) | `pcsk_...` |
| `F1_PINECONE_INDEX` | 인덱스명 | `samc-law-f1` |
| `F1_RAG_TOP_K` | 검색 상위 K | `5` (기본) |
| ~~`F1_ANTHROPIC_API_KEY`~~ | ~~Claude (law_extractor)~~ | **삭제** (admin_law_update의 검증 코드도 제거) |

### 2.7 충돌 해결 — HITL 원칙

| 시나리오 | exact 결과 | RAG 결과 | 처리 |
|---|---|---|---|
| ① 금지원료 적중 | Step 0 stopped, `verdict=...prohibited` | (RAG 미호출) | 즉시 `import_possible=false`, `status=waiting_review` |
| ② 일치 | allowed | allowed | `conflict_status=agreed`, `status=waiting_review` (기존 흐름) |
| ③ 일치 | prohibited | prohibited | 동일 |
| ④ 충돌 | allowed | prohibited | `conflict_status=conflict`, `status=needs_review`, 프론트가 양쪽 결과 + 인용 표시 → 사람이 PATCH로 결정 |
| ⑤ 충돌 | prohibited | allowed | 동일 (사람 결정) |
| ⑥ 미등록 | unidentified | allowed/prohibited | `conflict_status=rag_supplemented`, `status=needs_review` (사람 확인 권장) |
| ⑦ RAG 호출 실패 | (정상) | error | `conflict_status=rag_unavailable`, `status=waiting_review` (degraded mode) |

→ 자동 결정 금지. 모든 비-일치 케이스는 `needs_review`로 표시, 운영자가 결정.

## 3. 시스템 아키텍처

```
[Frontend F1 — ImportCheckPage.tsx]
        │ POST /api/v1/cases/{id}/pipeline/feature/1/run
        ▼
[Backend routers/feature1.py — run_feature1_endpoint]
        │
        ├─ run_feature1(ingredients, food_type, process_conditions) → Feature1Output  [기존]
        │     ├─ Step 0/1/3 (변경 없음)
        │     └─ f1_* 테이블 → exact_match 결과
        │
        ├─ Step 0 미적중이면: f1_rag_judge.run(payload) → RagJudgement  [신규]
        │     ├─ f1_openai_client.embed() ──→ [OpenAI API]
        │     ├─ f1_pinecone_client.search_multi() ──→ [Pinecone samc-law-f1]
        │     └─ f1_openai_client.chat(JSON mode) ──→ [OpenAI API]
        │
        ├─ HITL 비교 → conflict_status, status 결정  [신규]
        │
        └─ _to_pipeline_result(Feature1Output, RagJudgement) → ai_result(dict)  [수정]
              │ (기존 ingredients[], verdict, ... + _internal에 RAG 필드 통합)
              ▼
        pipeline_steps.upsert (status, ai_result)
              │
              ▼
[Response: { case_id, status, ai_result }]
              │
              ▼
[Frontend: 판정 카드 + 인용 카드 + (충돌 시) 결정 패널]
```

## 4. 영향 범위

### 4.1 신규 파일

| 파일 | 역할 |
|---|---|
| `backend/services/f1_pinecone_client.py` | Pinecone 검색 클라이언트 |
| `backend/services/f1_rag_judge.py` | RAG + OpenAI 판정 통합 |
| `backend/services/f1_chunking.py` | 조항 기반 청킹 (newsamc 포팅) |
| `backend/services/f1_openai_client.py` | OpenAI 임베딩/Chat 래퍼 (JSON mode) |
| `backend/scripts/f1_create_pinecone_index.py` | 인덱스 자동 생성 |
| `backend/scripts/f1_replicate_from_newsamc.py` | samc-law → samc-law-f1 복제 |
| `backend/scripts/f1_embed_additive_code.py` | 식품첨가물공전 신규 임베딩 |
| `backend/db/migrations/010_f1_law_chunks.sql` | 미러 테이블 |
| `backend/models/f1_law_citation.py` | RagJudgement / LawCitation Pydantic |

### 4.2 수정 파일

| 파일 | 변경 내용 |
|---|---|
| `backend/services/feature1.py` | RAG 호출 + HITL 비교 추가, **시그니처 유지** (반환 타입을 `Feature1Output`에서 `tuple[Feature1Output, RagJudgement \| None]`로 확장 OR 모듈 분리 — 백엔드 문서 참조) |
| `backend/routers/feature1.py` | `_to_pipeline_result()` 함수에 RAG 필드 통합, run 엔드포인트에서 conflict_status로 status 결정 |
| `backend/routers/admin_law_update.py` | `_run_f1_preprocess` 교체 (Claude → RAG 임베딩), `_get_f1_clients` 교체 (`F1_OPENAI_API_KEY`+`F1_PINECONE_API_KEY` 검증), `LAW_FEATURE_MAP`은 그대로 (F1 유지) |
| `backend/utils/chunker.py:14` | 주석에 law_extractor 참조 정리 |
| `backend/main.py` | (변동 없음 — lifespan 이미 정리) |
| `backend/.env.example` | F1_OPENAI_*, F1_PINECONE_* 추가, F1_ANTHROPIC_API_KEY 제거 |
| `backend/requirements.txt` | `tiktoken` 추가만 (`pinecone>=8.0.0`, `openai==1.57.0` 이미 존재, `anthropic` 유지 — F4의 `claude_client`가 사용) |
| `frontend/features/feature1/types.ts` | 기존 `Feature1Response` 보존, `Feature1Internal`에 RAG 필드 + `LawCitation` 타입 추가 |
| `frontend/features/feature1/api/importCheck.ts` | (응답 구조 호환 — 변경 최소) |
| `frontend/features/feature1/ImportCheckPage.tsx` | 인용 영역 + 충돌 결정 패널 |
| `MERGE_GUIDE.md` | F1 섹션 갱신, env 표 갱신, 인덱스 표 추가 |
| `f1_수정_요청_사항.md` | RAG 도입 후속 사항 반영 |

### 4.3 폐기 파일

| 파일 | 처리 |
|---|---|
| `backend/services/law_extractor.py` | **삭제** |
| 관련 테스트 (`tests/services/test_law_extractor*.py` 등) | 삭제 |
| `F1_ANTHROPIC_API_KEY` 환경 변수 | `.env.example`, `MERGE_GUIDE.md`, `admin_law_update._get_f1_clients`에서 제거 |

### 4.4 유지 (오해 정리)

| 항목 | 이유 |
|---|---|
| `anthropic` 패키지 (`requirements.txt`) | F4의 `_get_f4_clients`가 `OpenAI(api_key=os.getenv("F4_OPENAI_API_KEY"))` 변수명을 `claude` 로 사용하나 실제 OpenAI. 단 `F0_ANTHROPIC_API_KEY` 등 다른 기능 가능성 있어 **유지** |
| `f1_* 테이블 + 시드 110건` | 정확매칭 보조용 유지 |
| `_run_f1_preprocess` 함수명 + `LAW_FEATURE_MAP["F1"]` | 함수 시그니처/이름 유지, 내부 구현만 RAG 임베딩으로 교체 |

### 4.5 DB 변경

- 신규 마이그레이션: `010_f1_law_chunks.sql`
- 기존 `f1_*` 시드 (110건): **유지**
- RLS 정책: `f1_law_chunks`에 추가 (admin 쓰기, 인증 사용자 읽기)
- `pipeline_steps.ai_result` JSONB는 기존 그대로, 내부 구조에 `_internal.rag_*`, `_internal.law_citations` 추가 (스키마 변경 없음)

### 4.6 외부 인프라

| 자원 | 작업 |
|---|---|
| Pinecone `samc-law-f1` | 신규 생성 (Python 자동 스크립트) |
| OpenAI API | 비용 모니터링 추가 (임베딩 + Chat) |

## 5. Phase 개요

| Phase | 명칭 | 산출물 | 의존 |
|---|---|---|---|
| 1 | 인프라 + 클라이언트 | 인덱스, env, `f1_pinecone_client.py`, `f1_openai_client.py`, `f1_law_chunks` 테이블 | — |
| 2 | 데이터 이전 | samc-law → samc-law-f1 484건 복제 + 검증 리포트 | Phase 1 |
| 3 | 식품첨가물공전 임베딩 | `f1_embed_additive_code.py`, `additive_code_text` 적재 | Phase 1 |
| 4-A | 판정 모듈 | `f1_rag_judge.py`, `f1_chunking.py`, Pydantic 모델 | Phase 2~3 |
| 4-B | 통합 + law_extractor 제거 | `feature1.py` 시그니처 확장, `_to_pipeline_result()` 수정, `admin_law_update._run_f1_preprocess` 교체, 폐기 파일 정리, 골든셋 30건 평가 | Phase 4-A |
| 5 | 프론트 + 검증 | 인용 UI + HITL 결정 패널, e2e, MERGE_GUIDE 갱신 | Phase 4-B |

상세 일정/태스크는 [f1_RAG도입_Phase진행계획.md](f1_RAG도입_Phase진행계획.md) 참조.

## 6. 컨벤션 준수 체크

- [x] env 키 F1_ prefix 일관 적용
- [x] 자기 기능 인덱스만 사용 (`samc-law-f1`)
- [x] 자기 기능 테이블만 (`f1_law_chunks`)
- [x] API 경로: `/api/v1/cases/{id}/pipeline/feature/1/...` (변경 없음)
- [x] 다른 기능 코드/스키마/env에 영향 없음 (admin_law_update의 F1 섹션만 수정)
- [x] Supabase 공용 키 사용
- [x] PR 단위 Phase별 분리, Phase 4는 4-A/4-B 분할

## 7. 리스크 & 미결 사항

| 구분 | 내용 | 우선순위 | 대응 |
|---|---|---|---|
| 리스크 | Claude → OpenAI 전환 시 판정 품질 차이 | 높음 | Phase 4-B 골든셋 **30건+** (조건부 케이스 비율 ≥ 40%) 비교 평가 |
| 리스크 | 942건 중 484건만 복제 시 namespace 매핑 오류 | 중 | Phase 2 검증 리포트에서 namespace별 sample 청크 검수 |
| 리스크 | OpenAI 비용 (요청당 임베딩+Chat) | 중 | gpt-4o-mini 기본, 캐싱 적용(Phase 5 후 검토), 모니터링 대시보드 |
| 리스크 | newsamc Pinecone 키 = 회사 공용 키 (확인됨) | 낮음 | 1회성 마이그레이션 후 동일 키로 통합 운영 |
| 리스크 | search_multi 순차 호출 시 레이턴시 누적 | 중 | `asyncio.gather` 또는 `ThreadPoolExecutor` 병렬화 (백엔드 문서 §3.2) |
| 리스크 | OpenAI JSON 파싱 실패 | 중 | `response_format={"type":"json_object"}` 적용 + try/except 시 unknown 폴백 |
| 결정 완료 (S2) | exact ≠ RAG 충돌 시 → **HITL** (`needs_review` 상태) | 높음 | §2.7 표 참조 |
| 미결 (OPEN-1) | top-K 값 (3 / 5 / 10) | 낮음 | Phase 4-B 평가 후 결정 |
| 미결 (OPEN-2) | OpenAI 모델 (gpt-4o-mini vs gpt-4o) | 중 | Phase 4-B 골든셋 비교에서 비용/품질 |
| 미결 (OPEN-3) | 임계값 자동 추출 폐기 → 수동 admin UI 필요성 | 중 | Phase 5 후 운영팀 확인, 별도 PR |
| 미결 (OPEN-4) | f1_* 시드 110건 향후 갱신 방식 | 중 | Phase 4-B 후 (수동 SQL vs admin UI) |

## 8. 관련 자료

- newsamc 청킹: `C:\GITHUB\newsamc\src\lib\regulations\chunking-service.ts`
- newsamc 구현계획: `C:\GITHUB\newsamc\docs\설계\구현계획\07_M7-2_청킹_임베딩_Pinecone.md`
- newsamc 적재 통계 (2026-04-17 조사): 942건 — food_code_text 140 / health_food_text 252 / packaging_text 352 / labeling_standard 93 / temporary_standard 74 / functional_labeling 18 / unfair_labeling 13
- F2 반영 계획 (참조 패턴): `계획/f2_반영계획_*.md`, `계획/f2_반영_Phase진행계획.md`
- F5 RAG 구현 (참조): `backend/services/f5_rag.py`, `backend/scripts/f5_embed_laws.py`
- 실제 코드 검증 기준: [feature1.py](../backend/services/feature1.py), [routers/feature1.py](../backend/routers/feature1.py), [admin_law_update.py](../backend/routers/admin_law_update.py), [types.ts](../frontend/features/feature1/types.ts), [requirements.txt](../backend/requirements.txt)
