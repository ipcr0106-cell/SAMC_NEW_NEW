# SAMC 병합 가이드

> 기능별 병합 시 **건들면 안 되는 파일**과 **각 기능의 소유 범위**를 기록합니다.
> 병합할 때마다 이 문서를 업데이트합니다.

---

## 병합 순서

경아(f0 입력+OCR) → 병찬(F1) → 아람(F2) → 유빈(F3) → 성은(F4) → 세연(F5)

---

## 현재 병합 상태

| 기능 | 담당 | 상태 | 병합일 |
|------|------|------|--------|
| f0 입력+OCR+로그인 | 경아 | **병합 완료** | 2026-04-15 |
| F1 수입판정 | 병찬 | **병합 완료** | 2026-04-16 |
| F2 유형분류 | 아람 | **병합 완료** | 2026-04-16 |
| F3 필요서류 | 유빈 | **병합 완료** | 2026-04-16 |
| F4 라벨검토 | 성은 | **병합 완료** | 2026-04-15 |
| F5 한글시안 | 세연 | **병합 완료** | 2026-04-16 |

---

## f0 (경아) — 입력 + OCR + 로그인 + UX

### 소유 파일 (다른 기능이 수정 금지)

**백엔드:**
- `backend/routers/upload.py` — 업로드/파싱/문서관리/내보내기/라벨이미지 조회
- `backend/routers/cases.py` — 케이스 CRUD
- `backend/services/ocr_service.py` — 텍스트 추출 (PDF, 이미지, HWP, Excel)
- `backend/services/parsing_service.py` — Claude LLM 구조화 파싱
- `backend/services/label_image_service.py` — 라벨 이미지 크롭/OCR (Vision AI)
- `backend/services/export_service.py` — DOCX/PDF 내보내기
- `backend/schemas/upload.py` — Pydantic 스키마 (DocType, ParsedResult 등)

**프론트엔드:**
- `frontend/app/auth/login/page.tsx` — 로그인 페이지
- `frontend/app/dashboard/page.tsx` — 대시보드 (케이스 목록/생성)
- `frontend/app/cases/[id]/upload/page.tsx` — 업로드+OCR 메인 페이지
- `frontend/app/cases/[id]/layout.tsx` — 케이스 레이아웃 (상단바, 인증)
- `frontend/components/ocr/OcrResultEditor.tsx` — OCR 결과 편집기
- `frontend/components/ocr/BasicInfoCard.tsx` — 기본 정보 카드
- `frontend/components/ocr/IngredientTable.tsx` — 원재료 테이블
- `frontend/components/ocr/ProcessCodeCard.tsx` — 공정 코드 카드
- `frontend/components/ocr/LabelInfoCard.tsx` — 라벨 정보 카드
- `frontend/components/upload/DocumentUploadGrid.tsx` — 업로드 그리드
- `frontend/components/upload/FileDropzone.tsx` — 드래그앤드롭
- `frontend/components/upload/LabelImageCard.tsx` — 라벨 이미지 미리보기

### f0 API 엔드포인트 (수정 금지)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/v1/cases` | 케이스 생성 |
| GET | `/api/v1/cases` | 케이스 목록 |
| GET | `/api/v1/cases/{id}` | 케이스 상세 |
| PUT | `/api/v1/cases/{id}` | 케이스 수정 |
| DELETE | `/api/v1/cases/{id}` | 케이스 삭제 |
| POST | `/api/v1/cases/{id}/upload` | 파일 업로드 |
| POST | `/api/v1/cases/{id}/parse` | OCR+AI 파싱 |
| GET | `/api/v1/cases/{id}/documents` | 문서 목록 |
| DELETE | `/api/v1/documents/{doc_id}` | 문서 삭제 |
| GET | `/api/v1/documents/{doc_id}/view` | 문서 Signed URL |
| PUT | `/api/v1/cases/{id}/parsed-result` | 파싱 결과 저장 |
| GET | `/api/v1/cases/{id}/parsed-result` | 파싱 결과 조회 |
| GET | `/api/v1/cases/{id}/parsed-result/export.{docx\|pdf}` | 내보내기 |
| GET | `/api/v1/cases/{id}/label-images` | 라벨 이미지 목록 |
| GET | `/api/v1/cases/{id}/label-images/{img_id}/view` | 라벨 이미지 URL |

### f0 DB 테이블

- `cases` — 케이스 기본 정보
- `documents` — 업로드 파일 메타데이터
- `pipeline_steps` (step_key='0') — OCR 파싱 결과 저장
- `case_label_images` — 크롭된 라벨 이미지 + OCR 메타

### 다른 기능이 f0에서 데이터를 가져오는 방법

- `pipeline_steps` 테이블에서 `step_key='0'`의 `ai_result` 조회
- `case_label_images` 테이블에서 라벨 이미지/OCR 텍스트 조회
- `/api/v1/cases/{id}/parsed-result` API로 파싱 결과 가져오기
- `/api/v1/cases/{id}/label-images` API로 라벨 이미지 가져오기

---

## 공통/공유 파일 (수정 시 팀 전체 확인 필요)

**수정하려면 반드시 팀원 확인 후 진행:**

- `backend/main.py` — 라우터 등록 (기능 추가 시에만 수정)
- `backend/db/supabase_client.py` — Supabase 클라이언트
- `backend/db/pinecone_client.py` — Pinecone 클라이언트
- `frontend/lib/api.ts` — API 함수 모음 (각 기능 섹션만 자기가 수정)
- `frontend/lib/supabase.ts` — Supabase 인증 클라이언트
- `frontend/components/layout/StepNavigation.tsx` — 단계 네비게이션
- `frontend/components/layout/CaseSummaryPanel.tsx` — 케이스 요약 패널
- `frontend/components/ui/*` — 공통 UI 컴포넌트 (Badge, Button, Card, Input, Select, Toggle)
- `frontend/app/layout.tsx` — 전역 레이아웃
- `frontend/app/page.tsx` — 루트 리다이렉트
- `frontend/types/pipeline.ts` — 기능별 결과 타입 (F4 병합 시 추가, 각 기능 담당자가 자기 섹션만 수정)
- `frontend/types/api.ts` — API 공통 응답 타입
- `frontend/types/case.ts` — 케이스 공통 타입
- `frontend/services/apiClient.ts` — axios 기반 공통 API 클라이언트 (JWT 자동 첨부)

---

## F4 (성은) — 수출국 표시사항 검토

### 소유 파일 (다른 기능이 수정 금지)

**백엔드:**
- `backend/routers/feature4.py` — F4 메인 라우터 (분석/검증/확인/리포트)
- `backend/routers/admin_laws.py` — 법령 관리 어드민 API
- `backend/db/feature4/` 폴더 전체:
  - `schema.sql` — F4 전용 테이블 정의
  - `preprocess_laws.py` — 법령 PDF → Pinecone 전처리
  - `extract_prohibited_keywords.py` — 금지 표현 추출
  - `extract_image_violation_types.py` — 이미지 위반 유형 추출
  - `seed_image_violation_types.py` — 초기 위반 유형 시드
  - `verify_preprocessing.py`, `check_ids.py`, `check_pinecone.py` — 검증 스크립트
  - `clear_index.py`, `dump_chunks.py` — 유틸리티
  - `.env` — F4 전용 환경변수 (Pinecone/Supabase/OpenAI 키)
  - `requirements.txt` — F4 전용 의존성

**프론트엔드:**
- `frontend/features/feature4/` 폴더 전체:
  - `ForeignLabelPage.tsx` — F4 메인 컴포넌트
  - `hooks/useForeignLabelCheck.ts` — 상태 관리 훅
  - `api/foreignLabel.ts` — F4 전용 API 함수
  - `components/LabelUploader.tsx` — 라벨 업로드 UI
  - `components/LawUploader.tsx` — 법령 업로드 UI
  - `components/AnalysisResult.tsx` — 판정 결과 배지
  - `components/IssueList.tsx` — 위반 목록
  - `components/CrossCheckTable.tsx` — 교차검증 테이블
  - `components/ConfirmPanel.tsx` — 확인 패널
  - `types.ts` — F4 전용 타입
  - `constants.ts` — F4 전용 상수/API 경로
- `frontend/app/cases/[id]/f4/page.tsx` — F4 페이지 라우트
- `frontend/app/admin/laws/page.tsx` — 법령 관리 어드민 페이지

### F4 API 엔드포인트 (수정 금지)

**feature4.py 라우터** (prefix: `/api/v1/cases/{case_id}/pipeline/feature/4`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `.../analyze` | AI 분석 실행 (텍스트+이미지+교차검증) |
| POST | `.../validate` | 선택 항목 법령 정합성 검토 |
| GET | `.../` | 현재 결과 조회 |
| PATCH | `.../` | final_result 저장 (담당자 교정) |
| POST | `.../confirm` | 확인 완료 → F5로 진행 |
| GET | `.../report` | PDF 레포트 다운로드 |

**admin_laws.py 라우터** (prefix: `/admin/laws`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/admin/laws/upload` | 법령 PDF 업로드 + 재전처리 |
| GET | `/admin/laws` | 등록된 법령 목록 |
| GET | `/admin/laws/image-violation-types` | 이미지 위반 유형 목록 |
| PATCH | `/admin/laws/image-violation-types/{type_id}/activate` | 위반 유형 활성화/비활성화 |

### F4 main.py 등록 (필수)

```python
# main.py에 추가해야 할 import + 등록
from routers.feature4 import router as feature4_router
from routers.admin_laws import router as admin_laws_router

app.include_router(feature4_router)
app.include_router(admin_laws_router)
```

### F4 DB 테이블 (f4_ prefix)

- `f4_law_documents` — 법령 메타데이터 + 청크 수
- `f4_prohibited_expressions` — 금지 표현 키워드 (빠른 필터용)
- `f4_image_violation_types` — 18가지 이미지 위반 유형 라이브러리

### F4 외부 의존성 (requirements.txt에 추가 필요)

- `fpdf` — PDF 레포트 생성
- `sentence-transformers` — multilingual-e5-large 임베딩
- `pinecone` — Pinecone 벡터 검색 (f4 전용 인덱스: `samc-feature4-laws`)

### F4가 f0에서 가져오는 데이터 (연동 완료)

- `pipeline_steps` 테이블 (step_key='0') → `ai_result` JSON에서:
  - `basic_info.product_name` → 제품명
  - `ingredients[].name` → 원재료 목록
  - `basic_info.export_country` → 원산지
  - `label_info.label_texts` → 라벨 텍스트 (배열 → 합쳐서 사용)
- `case_label_images` 테이블 → 크롭된 라벨 이미지 (Vision AI 분석용)
- ~~`document_ocr_results`~~ → 삭제됨 (f0이 이 테이블을 사용하지 않음)
- ~~`label_ocr_results`~~ → 삭제됨 (f0이 이 테이블을 사용하지 않음)

> `content_volume`(내용량)과 `manufacturer`(제조사)는 f0 ParsedResult에 아직 없음. 추후 f0에 필드 추가 시 연동 예정.

---

## 데이터 파이프라인 연결 현황

### 전체 흐름도

```
f0 (서류 업로드 + OCR)
├─→ F1 (수입판정)    : ingredients, process_codes 자동 추출
├─→ F2 (유형분류)    : f0 + F1 결과 합쳐서 전달
├─→ F4 (라벨검토)    : 제품명, 원재료, 라벨텍스트, 라벨이미지

F1 (수입판정 결과)
├─→ F2              : 원재료 판정 상태, 수입 가능 여부
└─→ F4              : ingredients 목록 자동 보충

F2 (식품유형 분류 결과)
├─→ F3 stub         : food_type, is_alcohol → 필요서류 조회
└─→ F4              : food_type 자동 보충
```

### 연결 완료

| 출발 | 도착 | 데이터 | 경로 | 구현 시점 |
|------|------|--------|------|-----------|
| f0 | F1 | 원재료 목록 | `pipeline_steps(step_key='0').ingredients[]` → 자동 변환 | F1 병합 시 |
| f0 | F1 | 공정 코드 → is_heated/distilled/fermented | `process_info.process_codes` → 자동 변환 | F1 병합 시 |
| f0 | F2 | 제품명, 원재료, 공정 정보 | `_build_enriched_text()` | F2 병합 시 |
| f0 | F4 | 제품명 | `_fetch_doc_ocr()` | F4 원본 |
| f0 | F4 | 원재료 목록 | `_fetch_doc_ocr()` | F4 원본 |
| f0 | F4 | 원산지/수출국 | `_fetch_doc_ocr()` | F4 원본 |
| f0 | F4 | 라벨 텍스트 | `_fetch_label_ocr()` | F4 원본 |
| f0 | F4 | 라벨 이미지 | `case_label_images` 테이블 | F4 원본 |
| F1 | F2 | 수입판정 결과, 원재료 상태 | `_build_enriched_text()` | F2 병합 시 |
| F1 | F4 | 원재료 이름 목록 | `_fetch_f1_result()` → `req.ingredients` 자동 보충 | F4 파이프라인 추가 |
| F2 | F4 | food_type | `_fetch_f2_result()` → `req.food_type` 자동 보충 | F4 파이프라인 추가 |
| f0 | F3 | origin_country, is_oem, is_first_import, is_organic | `_build_product_info_from_pipeline()` | F3 병합 시 |
| F1 | F3 | ingredients[].name → product_keywords | `_build_product_info_from_pipeline()` | F3 병합 시 |
| F2 | F3 | food_type, category_name, subcategory_name | `_build_product_info_from_pipeline()` | F3 병합 시 |
| f0 | F5 | 제품명, 원산지, OEM, 원재료 | `_build_context_from_pipeline()` | F5 병합 시 |
| F1 | F5 | 수입판정 결과 | `_build_context_from_pipeline()` | F5 병합 시 |
| F2 | F5 | food_type 자동 보충, 주류 여부 | `_enrich_food_type()` + context | F5 병합 시 |
| F4 | F5 | 라벨 검토 지적사항 | `_build_context_from_pipeline()` | F5 병합 시 |

### 미연결 — 요청 필요

| 출발 | 도착 | 데이터 | 요청 대상 | 상세 |
|------|------|--------|-----------|------|
| f0 | F4 | 내용량 (content_volume) | **경아 (f0)** | `f0_수정_요청_사항.md` 참조 |
| f0 | F4 | 제조사 (manufacturer) | **경아 (f0)** | `f0_수정_요청_사항.md` 참조 |
| f0 | F1 | 사용 부위 (part) | **경아 (f0)** | `f0_수정_요청_사항.md` 참조 |
| f0 | F1 | 복합원재료 (sub_ingredients) | **경아 (f0)** | `f0_수정_요청_사항.md` 참조 |
| f0 | F1 | 알코올 도수 (alcohol_percentage) | **경아 (f0)** | `f0_수정_요청_사항.md` 참조 |

> 각 담당자별 수정 요청 상세는 `f{N}_수정_요청_사항.md` 파일 참조

---

### F4 Pinecone 인덱스

- 인덱스명: `samc-feature4-laws`
- 차원: 1024 (multilingual-e5-large)
- 용도: 법령 조문 시맨틱 검색

---

## 통합 법령 업데이트 시스템

> f0 레벨에서 관리. 기능 병합 시마다 매핑 테이블만 수정하면 자동 연결.

### 구조

```
사용자: 대시보드 → 검역관리▼ → 법령 DB 관리 → /admin/law-update
         ↓
   법령 종류별 카드에 PDF/HWPX 드래그앤드롭
         ↓
   "선택한 법령 업데이트" 클릭
         ↓
백엔드: LAW_FEATURE_MAP에서 법령 → 관련 기능 조회
         ↓
   관련 기능 전처리 함수 병렬 실행 (SSE로 진행도 스트리밍)
         ↓
프론트: 팝업에서 법령×기능별 진행도 실시간 표시
```

### 소유 파일

- `backend/routers/admin_law_update.py` — 통합 법령 업데이트 라우터
- `frontend/app/admin/law-update/page.tsx` — 법령 업데이트 페이지
- `frontend/app/dashboard/page.tsx` — 검역관리 드롭다운에 "법령 DB 관리" 항목 포함

### API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/admin/law-update/laws` | 업데이트 가능 법령 목록 + 기능 매핑 |
| POST | `/admin/law-update/upload` | 다건 법령 업로드 → SSE 진행도 스트리밍 |

### 법령 ↔ 기능 매핑 테이블 (`LAW_FEATURE_MAP`)

| 법령명 | 관련 기능 | 비고 |
|--------|-----------|------|
| 식품공전 | F1, F2 | |
| 식품첨가물공전 | F1, F2 | F3 병합 시 → [F1, F2, F3] |
| 건강기능식품공전 | F1 | F2에서 아직 미사용, 아람 확인 후 F2 추가 가능 |
| 식품유형 분류원칙 | F2 | 식품공전 식품유형 분류원칙 |
| 주세법 시행령 | F2 | 주류 분류 기준 (별표1, 별표3) |
| 기구및용기포장공전 | F2 | 기구 및 용기·포장의 기준 및 규격 |
| 식품등의 한시적 기준 및 규격 인정 기준 | F1, F4 | 업로드 시 두 기능 동시 전처리 |
| 식품 등의 표시·광고에 관한 법률 | F4 | |
| 식품 등의 표시·광고에 관한 법률 시행령 | F4 | |
| 식품 등의 표시·광고에 관한 법률 시행규칙 | F4 | |
| 식품등의 표시기준 | F4 | |
| 식품등의 부당한 표시 또는 광고의 내용 기준 | F4 | |
| 기능성 표시·광고 허용 규정 | F4 | |

### 기능별 전처리 방식 차이

| 기능 | 전처리 함수 | 방식 | 저장소 |
|------|------------|------|--------|
| F1 | `law_extractor.extract_thresholds_bulk()` | Claude LLM → 구조화 기준치 | Supabase (f1_ 테이블) |
| F4 | `preprocess_laws.preprocess_single_law()` | 임베딩 → 벡터 upsert | Pinecone + Supabase (f4_ 테이블) |

### 기능 병합 시 법령 업데이트 추가 방법

`backend/routers/admin_law_update.py`에서 **2곳만 수정**:

```python
# 1. LAW_FEATURE_MAP — features 리스트에 기능 코드 추가
"식품공전": { "features": ["F1", "F2"], ... }  # ← "F2" 추가

# 2. FEATURE_PROCESSORS — 전처리 함수 등록
FEATURE_PROCESSORS = {
    "F1": _run_f1_preprocess,
    "F4": _run_f4_preprocess,
    "F2": _run_f2_preprocess,  # ← 추가
}
```

프론트엔드는 법령 목록을 API에서 받아오므로 **수정 불필요**.

---

## F1 (병찬) — 수입 가능 판정 (**병합 완료**)

### 소유 파일 (다른 기능이 수정 금지)

**백엔드:**
- `backend/routers/feature1.py` — F1 파이프라인 API (GET/POST/PATCH/confirm)
- `backend/routers/db_manager.py` — F1 DB 직접 관리 CRUD
- `backend/services/feature1.py` — F1 통합 오케스트레이션 (Step 0+1+3)
- `backend/services/step1_ingredients_check.py` — 원재료 허용/금지 판정
- `backend/services/step3_standards.py` — 기준치 수치 비교 (일반+주류)
- `backend/services/law_extractor.py` — 법령→기준치 Claude 추출
- `backend/models/judgment.py` — F1 Pydantic 모델
- `backend/utils/chunker.py` — 법령 마크다운 청킹
- `backend/utils/cleaner.py` — kordoc 변환 후 마크다운 정제
- `backend/utils/unit_converter.py` — 단위 변환 엔진
- `backend/constants/condition_patterns.py` — 조건부 원료 분류 패턴
- `backend/constants/gmo.py` — GMO 위험 원료 상수
- `backend/constants/thresholds_config.py` — F1 매칭/검증 임계값
- `backend/db/connection.py` — asyncpg 커넥션 풀 (F1 DB 쿼리용)
- `backend/db/migrations/001~009*.sql` — F1 테이블 마이그레이션
- `backend/db/seed/01~05*.sql` — F1 초기 데이터
- `backend/scripts/bootstrap_f1_db.py` — F1 DB 부트스트랩
- `backend/scripts/apply_migrations.py` — 마이그레이션 자동 적용

**프론트엔드:**
- `frontend/features/feature1/` 폴더 전체:
  - `ImportCheckPage.tsx` — F1 메인 컴포넌트
  - `hooks/useImportCheck.ts` — 상태 관리 훅
  - `api/importCheck.ts` — F1 전용 API 함수
  - `components/AggregationSummary.tsx` — 판정 요약
  - `components/ConfirmActions.tsx` — 확인 버튼
  - `components/ForbiddenAlert.tsx` — 금지 알림
  - `components/IngredientMatchTable.tsx` — 원재료 매칭 테이블
  - `components/LawRefCheckbox.tsx` — 법령 참고 체크박스
  - `components/StandardsSummary.tsx` — 기준치 요약
  - `components/VerdictPanel.tsx` — 최종 판정 패널
  - `types.ts`, `constants.ts` — F1 전용 타입/상수
- `frontend/app/cases/[id]/f1/page.tsx` — F1 페이지 라우트 (f0 레이아웃 유지)

### F1 API 엔드포인트 (수정 금지)

**feature1.py 라우터** (prefix: `/api/v1/cases/{case_id}/pipeline/feature/1`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `.../feature/1` | F1 결과 조회 |
| POST | `.../feature/1/run` | F1 실행 (DB 쿼리 → 판정) |
| PATCH | `.../feature/1` | 담당자 수정 (final_result) |
| POST | `.../feature/1/confirm` | 확인 완료 → 다음 단계 |

**db_manager.py 라우터** (prefix: `/api/v1/admin/db`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/v1/admin/db/{table}` | F1 테이블 목록 조회 |
| POST | `/api/v1/admin/db/{table}` | 신규 항목 추가 |
| PATCH | `/api/v1/admin/db/{table}/{id}` | 수정 (본인 항목만) |
| DELETE | `/api/v1/admin/db/{table}/{id}` | 삭제 (본인 항목만) |

### F1 main.py 등록 (완료)

```python
from routers.feature1 import router as feature1_router
from routers.db_manager import router as db_manager_router

app.include_router(feature1_router)
app.include_router(db_manager_router)
```

lifespan 훅에서 `F1_DATABASE_URL`로 asyncpg 커넥션 풀 초기화 추가됨.

### F1 DB 테이블 (f1_ prefix)

- `f1_allowed_ingredients` — 허용 원료 (식품공전 별표1)
- `f1_forbidden_ingredients` — 금지 원료 (식품공전 별표3)
- `f1_additive_limits` — 첨가물 기준치
- `f1_safety_standards` — 중금속/미생물/주류 안전기준
- `f1_ingredient_synonyms` — 원료 동의어
- `f1_escalation_logs` — 에스컬레이션 로그

### ⚠️ F1 DB 마이그레이션 — 병찬님 필수 작업

> **코드 병합은 완료되었으나, Supabase에 F1 테이블이 아직 생성되지 않았습니다.**
> F1이 정상 작동하려면 아래 SQL을 Supabase SQL Editor에서 순서대로 실행해야 합니다.

**실행 순서:**
1. `backend/db/migrations/001_pg_trgm_extension.sql` — pg_trgm 확장
2. `backend/db/migrations/002_f1_allowed_ingredients.sql`
3. `backend/db/migrations/003_f1_additive_limits.sql`
4. `backend/db/migrations/004_f1_safety_standards.sql`
5. `backend/db/migrations/005_f1_ingredient_synonyms.sql`
6. `backend/db/migrations/006_f1_forbidden_ingredients.sql`
7. `backend/db/migrations/007_f1_escalation_logs.sql`
8. `backend/db/migrations/008_f1_trgm_indexes_rpc.sql` — 텍스트 검색 인덱스
9. `backend/db/migrations/009_f1_rls_policies.sql` — 행 수준 보안

**시드 데이터 (마이그레이션 후):**
1. `backend/db/seed/01_f1_ingredients_permitted.sql` — 허용 원료 85건
2. `backend/db/seed/02_f1_ingredients_restricted.sql` — 조건부 원료
3. `backend/db/seed/03_f1_ingredients_prohibited.sql` — 금지 원료
4. `backend/db/seed/04_f1_forbidden_ingredients.sql` — 금지 원료 확장
5. `backend/db/seed/05_f1_thresholds_core.sql` — 기준치 코어

또는 `python -m scripts.bootstrap_f1_db` 로 일괄 적용 가능.

### F1 env 키

| 키 이름 | 용도 | 사용 기능 |
|---------|------|-----------|
| `F1_DATABASE_URL` | asyncpg 직접 연결 | F1 (connection.py) |
| `F1_ANTHROPIC_API_KEY` | Claude 기준치 추출 | F1 (law_extractor.py) |

---

## F2 (아람) — 식품 유형 분류 (**병합 완료**)

### 소유 파일 (다른 기능이 수정 금지)

**백엔드:**
- `backend/routers/feature2.py` — F2 식품유형 분류 API (run/get/patch)
- ~~`backend/routers/f2_required_docs.py`~~ — F3 병합 시 삭제됨. F3의 `feature3.py`가 대체
- `backend/db/feature2/preprocessing/` — 전처리 데이터 + Node.js 스크립트
- `backend/db/feature2/scripts/` — Python 전처리 스크립트

**프론트엔드:**
- `frontend/features/feature2/FoodClassificationPage.tsx` — F2 메인 컴포넌트
- `frontend/app/cases/[id]/f2/page.tsx` — F2 페이지 라우트 (f0 레이아웃 유지)

### F2 API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/cases/{case_id}/pipeline/feature/2/run` | AI 식품유형 분류 실행 |
| GET | `/cases/{case_id}/pipeline/feature/2` | F2 결과 조회 |
| PATCH | `/cases/{case_id}/pipeline/feature/2` | 담당자 수정 |
| GET | `/cases/{case_id}/pipeline/feature/3` | F2 기반 필요서류 조회 (stub) |
| PATCH | `/cases/{case_id}/pipeline/feature/3` | 필요서류 확인 완료 (stub) |

### F2 DB 테이블 (f2_ prefix)

- `f2_food_type_classification` — 식품유형 분류 데이터 (대/중/소분류)
- `f2_required_documents` — 식품유형별 필요서류 매핑

### F2 Pinecone 인덱스

- 인덱스명: `samc-a`
- 차원: 1536 (OpenAI text-embedding-3-small)
- 용도: 식품유형 분류 RAG 검색

### F2 env 키

| 키 이름 | 용도 |
|---------|------|
| `F2_OPENAI_API_KEY` | GPT-4o 식품유형 분류 |
| `F2_PINECONE_API_KEY` | Pinecone samc-a 인덱스 |
| `F2_PINECONE_INDEX` | 인덱스명 (기본값: samc-a) |

---

## F3 (유빈) — 필요서류 안내 (**병합 완료**)

### 소유 파일

**백엔드:**
- `backend/routers/feature3.py` — F3 파이프라인 API (run/get) + RAG + 캐시 리로드
- `backend/services/f3_required_docs.py` — 5축 AND 매칭 엔진
- `backend/services/f3_pinecone_client.py` — Pinecone RAG 검색
- `backend/db/f3_supabase_client.py` — PostgREST HTTP 클라이언트 + 캐시
- `backend/models/f3_schemas.py` — ProductInfo, RequiredDoc, RequiredDocsResponse

**프론트엔드:**
- `frontend/features/feature3/RequiredDocsPage.tsx` — F3 메인 컴포넌트 (법령 팝업 포함)
- `frontend/features/feature3/lib/` — law-texts, cross-check, ui-helpers, ingredient-synonym-map, pinecone
- `frontend/app/cases/[id]/f3/page.tsx` — F3 페이지 라우트 (f0 레이아웃 유지)
- `frontend/app/api/ai-cross-check/route.ts` — AI 교차검증 API Route
- `frontend/app/api/explain-docs/route.ts` — 서류 설명 생성 API Route

### F3 API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/cases/{case_id}/pipeline/feature/3/run` | f0+F1+F2 자동 연결 → 서류 매칭 |
| GET | `/cases/{case_id}/pipeline/feature/3` | F3 결과 조회 |
| POST | `/api/v1/required-docs/rag` | 법령 시맨틱 검색 |
| POST | `/api/v1/required-docs/reload` | 캐시 리로드 |

### F3 DB 테이블 (f3_ prefix)

- `f3_required_documents` (52건) — 서류 매칭 규칙
- `f3_country_groups` (181건) — 국가 그룹 매핑
- `f3_keyword_synonyms` (38건) — 원재료 동의어

### F3 Pinecone 인덱스

- 인덱스명: `samc-law-f3`
- 차원: 1024 (multilingual-e5-large, Pinecone inference API)
- 청크: 85개 (법령 22 + 엑셀 33 + 가이드 10 + 협정문 20)

### F3 env 키

| 키 이름 | 용도 |
|---------|------|
| `F3_PINECONE_API_KEY` | Pinecone samc-law-f3 인덱스 |
| `F3_PINECONE_INDEX_NAME` | 인덱스명 (기본값: samc-law-f3) |
| `F3_OPENAI_API_KEY` | AI 교차검증/설명 (프론트 API Route) |

---

## F5 (세연) — 한글표시사항 검토 및 시안 제작 (**병합 완료**)

### 소유 파일

**백엔드:**
- `backend/routers/feature5.py` — F5 파이프라인 API (run/get/patch, SSE 스트리밍)
- `backend/services/step6_label.py` — 2단계 교차검증 + 시안 생성 (Claude Sonnet 4)
- `backend/services/f5_rag.py` — Pinecone f5-law-chunks RAG 검색 (Voyage-3)
- `backend/scripts/f5_embed_laws.py` — 법령 PDF 임베딩 스크립트

**프론트엔드:**
- `frontend/features/feature5/LabelDraftPage.tsx` — F5 메인 컴포넌트 (2단계 진행 UI + SSE 스트리밍)
- `frontend/app/cases/[id]/f5/page.tsx` — F5 페이지 라우트 (f0 레이아웃 유지)

### F5 API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/v1/cases/{case_id}/pipeline/feature/5/run` | 시안 생성 (stream=true 시 SSE) |
| GET | `/api/v1/cases/{case_id}/pipeline/feature/5` | 시안 조회 |
| PATCH | `/api/v1/cases/{case_id}/pipeline/feature/5` | 담당자 확정 |

### F5 Pinecone 인덱스

- 인덱스명: `f5-law-chunks`
- 차원: 1024 (Voyage-3)
- 용도: 한글표시사항 법령 RAG 검색

### F5 env 키

| 키 이름 | 용도 |
|---------|------|
| `F5_ANTHROPIC_API_KEY` | Claude Sonnet 4 (Phase 1/2) |
| `F5_PINECONE_API_KEY` | Pinecone f5-law-chunks |
| `F5_VOYAGE_API_KEY` | Voyage-3 임베딩 |

---

## 코드 소유권 규칙 (반드시 준수)

> 병합 과정에서 **모든 담당자가 다른 기능의 영역을 침범한 사례**가 발견되었습니다.
> 아래 규칙을 지키지 않으면 병합 시 충돌이 발생하고, 다른 사람의 작업이 덮어씌워질 수 있습니다.

### 1. 자기 기능만 건드릴 것

| 내가 F2 담당이면 | 건들 수 있는 것 | 절대 건들면 안 되는 것 |
|---|---|---|
| 백엔드 | `backend/routers/feature2.py`, `backend/db/feature2/` | `backend/routers/feature1.py`, `feature3.py`, `feature4.py`, `feature5.py`, `upload.py`, `cases.py` |
| 프론트 | `frontend/features/feature2/`, `frontend/app/cases/[id]/f2/` | `frontend/features/feature1/`, `feature3/`, `feature4/`, `feature5/`, `frontend/app/dashboard/`, `frontend/components/` |
| DB | `f2_` prefix 테이블만 | `f1_`, `f3_`, `f4_`, `f5_` prefix 테이블, `cases`, `documents`, `pipeline_steps` 스키마 |

### 2. 공유 파일 수정 시 반드시 팀 확인

다음 파일은 **모든 기능이 공유**합니다. 수정하면 다른 기능이 깨질 수 있으므로 반드시 팀 확인 후 진행:

| 파일 | 왜 위험한가 |
|------|-----------|
| `backend/main.py` | 라우터 등록. 잘못 건드리면 다른 기능 API가 사라짐 |
| `backend/db/supabase_client.py` | 모든 기능의 DB 접속. 변경하면 전부 깨짐 |
| `frontend/lib/api.ts` | 모든 기능의 API 호출. 수정하면 전부 영향 |
| `frontend/services/apiClient.ts` | axios 인스턴스. baseURL 바꾸면 전부 죽음 |
| `frontend/types/pipeline.ts` | 기능별 결과 타입. 자기 섹션만 수정할 것 |
| `frontend/components/layout/*` | StepNavigation, CaseSummaryPanel 등 공통 UI |
| `frontend/app/layout.tsx` | 전역 레이아웃 |
| `.env.example` | 키 이름 안내 |

### 3. 병합 과정에서 발견된 실제 위반 사례

| 위반 | 누가 | 무슨 문제 |
|------|------|----------|
| 다른 프로젝트의 Supabase DB 사용 | F1 | `F1_DATABASE_URL`이 팀 공용 프로젝트가 아닌 별도 프로젝트를 가리킴 → f0 데이터를 읽지 못함 |
| F4 코드를 자기 폴더에 복사 | F1, F2, F3, F5 | `backend/db/feature4/`, `frontend/features/feature4/`를 자기 작업 환경에 복사해둠 → 병합 시 충돌 |
| 공유 파일을 자기 방식으로 수정 | F2, F5 | `main.py`, `upload.py`, `cases.py`를 자체 구현 → 병합 시 덮어쓰기 위험 |
| env 키에 prefix 미적용 | F2, F3, F5 | `OPENAI_API_KEY`, `PINECONE_API_KEY` → 다른 기능과 키 충돌 |
| 프론트에서 자체 레이아웃 사용 | F2, F3, F5 | f0의 StepNavigation/CaseSummaryPanel 미사용 → 디자인 불일치 |
| 다른 기능의 라우터를 만듦 | F2 | `feature3.py`를 자기가 만들어놓음 → F3 담당자와 충돌 |

### 4. 다른 기능의 데이터가 필요할 때

다른 기능의 결과가 필요하면 **직접 코드를 수정하지 말고** `pipeline_steps` 테이블에서 조회하세요:

```python
# 올바른 방법: pipeline_steps에서 읽기
result = supabase.table("pipeline_steps").select("ai_result").eq("case_id", case_id).eq("step_key", "2").execute()

# 잘못된 방법: 다른 기능의 코드를 import하거나 수정
from services.feature2 import run_feature2  # ← 절대 금지
```

### 5. 새 파일 추가 시 네이밍 규칙

| 구분 | 패턴 | 예시 |
|------|------|------|
| 백엔드 라우터 | `backend/routers/feature{N}.py` | `feature2.py` |
| 백엔드 서비스 | `backend/services/f{N}_*.py` 또는 `step{N}_*.py` | `f3_required_docs.py` |
| 백엔드 DB 스크립트 | `backend/db/feature{N}/` | `backend/db/feature2/` |
| 프론트 기능 폴더 | `frontend/features/feature{N}/` | `frontend/features/feature3/` |
| 프론트 페이지 | `frontend/app/cases/[id]/f{N}/page.tsx` | f2/page.tsx |
| Supabase 테이블 | `f{N}_` prefix | `f3_required_documents` |
| env 키 | `F{N}_` prefix | `F2_OPENAI_API_KEY` |
| Pinecone 인덱스 | 기능별 별도 | `samc-feature4-laws`, `samc-law-f3` |

---

## 병합 시 주의사항

### API 경로 규칙
- f0: `/api/v1/cases/{id}/upload`, `/parse`, `/documents`, `/parsed-result`, `/label-images`
- F1~F5: `/api/v1/cases/{id}/pipeline/feature/{번호}/...`
- 어드민: `/admin/...`

### DB 테이블 규칙
- 공용 테이블: prefix 없음 (`cases`, `documents`, `pipeline_steps`, `case_label_images`)
- 기능별 테이블: `f1_`, `f2_`, `f3_`, `f4_`, `f5_` prefix 사용

### 프론트엔드 구조 규칙
- 기능별 컴포넌트: `frontend/features/feature{N}/` 폴더에 격리
- 페이지 라우트: `frontend/app/cases/[id]/f{N}/page.tsx`
- 공통 컴포넌트: `frontend/components/ui/`, `frontend/components/layout/`
- API 함수: 기능별로 `features/feature{N}/api/`에 작성 (공통은 `lib/api.ts`)

### main.py 라우터 등록
서버 시작 시 자동 실행됨. 기능 추가 시 한 줄씩 추가:
```python
from routers.feature4 import router as feature4_router
app.include_router(feature4_router)
```

### Python 코드에서 한글/특수문자 print 금지 (Windows 인코딩 이슈)

Windows 환경에서 `print()` 안에 한글이나 특수문자(`—`, `·` 등)를 쓰면 `UnicodeEncodeError: 'cp949'` 에러가 발생하여 **서버가 시작조차 안 됩니다.**

```python
# ❌ 이렇게 쓰면 Windows에서 서버 죽음
print("[lifespan] F1_DATABASE_URL missing — F1 DB 기능 비활성화")

# ✅ 영문 또는 ASCII만 사용
print("[lifespan] F1_DATABASE_URL missing - F1 DB disabled")
```

**규칙:**
- `print()`, `raise RuntimeError()` 등 콘솔 출력 메시지는 **영문 또는 ASCII**만 사용
- 한글은 API 응답 JSON, 프롬프트 문자열, 주석에서만 사용 (이들은 UTF-8로 처리되므로 문제없음)
- `logging` 모듈 사용 시에도 동일 (핸들러가 cp949로 출력할 수 있음)

### 프론트엔드 병합 후 반드시 할 것 — .next 캐시 삭제

기능 병합 후 TypeScript 에러가 나면 `.next/` 캐시가 원인일 가능성이 높습니다.

```bash
cd frontend
rm -rf .next
npx next build    # 또는 npm run build
```

- `.next/`는 Next.js가 빌드/dev 시 자동생성하는 캐시 폴더 (`.gitignore`에 포함)
- 이전 빌드의 타입 정의가 남아 있으면 새로 추가한 페이지와 충돌하는 에러가 발생할 수 있음
- **병합 후 처음 빌드할 때는 항상 `.next/` 삭제 후 클린 빌드 권장**

### 기능별 수정 요청 문서

병합 가이드가 길어지는 것을 방지하기 위해, 각 담당자에게 전달할 수정/확인 요청은 별도 파일로 관리합니다.

| 파일 | 대상 | 내용 |
|------|------|------|
| `f0_수정_요청_사항.md` | 경아 (f0) | OCR 필드 추가 요청 (part, sub_ingredients, alcohol_percentage 등) |
| `f1_수정_요청_사항.md` | 병찬 (F1) | DB 마이그레이션, env 키, 미사용 필드 확인, PM 임의 파이프라인 연결 수정 가이드 |
| `f2_수정_요청_사항.md` | 아람 (F2) | Supabase 테이블 확인, env 키, 건강기능식품공전 추가, Node→Python 변환, 프론트 API 경로 수정 |
| `f3_수정_요청_사항.md` | 유빈 (F3) | Supabase/Pinecone 확인, env 키, category 매핑, 프론트 API 수정, 미복사 API Route |
| `f4_수정_요청_사항.md` | 성은 (F4) | PM 임의 F1/F2→F4 파이프라인 연결 검토, 수정/삭제 가이드 |
| `f5_수정_요청_사항.md` | 세연 (F5) | Pinecone 확인, env 키, PDF 업로드 UI 중복, PM 임의 파이프라인 연결 |

> 기능 병합 시마다 `f{N}_수정_요청_사항.md`를 생성하여 해당 담당자에게 전달합니다.

---

## .env 키 네이밍 규칙 (필수)

### 원칙
- **SUPABASE_URL, SUPABASE_SERVICE_KEY** → prefix 없이 공유 (전 기능 동일 DB)
- **그 외 모든 키** → `F{N}_` prefix 필수 (OPENAI, PINECONE, ANTHROPIC 등)
- 이유: 같은 키 이름인데 값이 다르면 마지막 로딩이 덮어써서 한쪽이 깨짐

### 병합 시 체크리스트
1. 새 기능의 코드에서 `os.getenv("OPENAI_API_KEY")` 같은 prefix 없는 키가 있으면 → `F{N}_OPENAI_API_KEY`로 변경
2. 새 기능의 `.env` 파일에서도 키 이름을 같이 변경
3. `backend/.env.example`에 새 기능의 키 목록 추가

### 현재 키 맵

| 키 이름 | 용도 | 사용 기능 |
|---------|------|-----------|
| `SUPABASE_URL` | DB 접속 | 공통 (prefix 없음) |
| `SUPABASE_SERVICE_KEY` | DB 접속 | 공통 (prefix 없음) |
| `F0_OPENAI_API_KEY` | OCR Vision, 파싱 | f0 |
| `F0_OPENAI_MODEL` | OpenAI 모델명 | f0 |
| `F0_ANTHROPIC_API_KEY` | Claude 파싱 | f0 |
| `F0_PINECONE_API_KEY` | 벡터 검색 | f0 |
| `F0_PINECONE_INDEX` | 인덱스명 | f0 |
| `F0_PARSER_SERVICE_URL` | 파서 서비스 | f0 |
| `F0_PARSER_SERVICE_TOKEN` | 파서 인증 | f0 |
| `F4_OPENAI_API_KEY` | AI 분석 | f4 |
| `F4_PINECONE_API_KEY` | 법령 검색 | f4 |
| `F4_PINECONE_HOST` | 인덱스 호스트 | f4 |
| `F4_DEEPL_API_KEY` | 번역 (선택) | f4 |
| `F1_DATABASE_URL` | asyncpg 직접 연결 | F1 |
| `F1_ANTHROPIC_API_KEY` | Claude 기준치 추출 | F1 |
| `F2_OPENAI_API_KEY` | GPT-4o 식품유형 분류 | F2 |
| `F2_PINECONE_API_KEY` | Pinecone samc-a | F2 |
| `F2_PINECONE_INDEX` | 인덱스명 (samc-a) | F2 |
| `F3_PINECONE_API_KEY` | Pinecone samc-law-f3 | F3 |
| `F3_PINECONE_INDEX_NAME` | 인덱스명 (samc-law-f3) | F3 |
| `F3_OPENAI_API_KEY` | AI 교차검증/설명 | F3 (프론트 API Route) |
| `F5_ANTHROPIC_API_KEY` | Claude Sonnet 4 | F5 |
| `F5_PINECONE_API_KEY` | Pinecone f5-law-chunks | F5 |
| `F5_VOYAGE_API_KEY` | Voyage-3 임베딩 | F5 |

### .env 파일 위치 (총 2개)

| 파일 | 대상 | git 추적 |
|------|------|----------|
| `backend/.env` | **백엔드 전체** (공통 + f0 + f4 + ...) | .gitignore (추적 안 함) |
| `backend/.env.example` | 키 이름 안내 템플릿 | 추적함 |
| `frontend/.env.local` | 프론트 환경변수 | .gitignore (추적 안 함) |
| `frontend/.env.local.example` | 키 이름 안내 | 추적함 |

> `backend/db/feature4/.env`는 삭제됨. 모든 백엔드 키는 `backend/.env` 하나로 통합.

### 나중에 전체 병합 완료 후
값이 동일한 키들(예: 같은 OpenAI 계정을 쓰게 된 경우)은 그때 prefix를 제거하고 하나로 통합 가능.
