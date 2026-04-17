# F2 아람 — 식품유형 분류 담당자 문서

> 작성일: 2026-04-17
> 담당: 아람 (기능2 — 식품유형 분류)

---

## 1. 담당 파일 목록

| 구분 | 파일 경로 |
|------|----------|
| 백엔드 라우터 | `backend/routers/feature2.py` |
| 프론트엔드 컴포넌트 | `frontend/features/feature2/FoodClassificationPage.tsx` |
| 프론트엔드 페이지 | `frontend/app/cases/[id]/f2/page.tsx` |
| 전처리 스크립트 | `backend/db/feature2/preprocessing/upload_foodcode5_full.js` |
| 전처리 스크립트 | `backend/db/feature2/preprocessing/upload_required_docs_f2.js` |
| 시드 데이터 | `backend/db/feature2/preprocessing/structured/required_documents_아람.csv` |

---

## 2. F2 전용 Supabase 테이블

### 2-1. `f2_food_type_classification` — 식품유형 분류 데이터

> 현재 상태: **235행 적재 완료** ✅

| 컬럼명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| `id` | integer (PK, auto) | 자동 증가 기본키 | 1 |
| `category_no` | text | 식품공전 대분류 번호 | `"1"`, `"15"` |
| `category_name` | text | 대분류명 (식품군) | `"과자류, 빵류 또는 떡류"` |
| `type_name` | text | 소분류명 (식품유형) | `"과자"`, `"위스키"` |
| `definition` | text | 해당 유형 정의 (최대 2000자) | `"곡분 등을 주원료로..."` |
| `category_definition` | text | 대분류 정의 (최대 2000자) | `"과자류, 빵류 또는 떡류라 함은..."` |
| `law_source` | text | 데이터 출처 | `"식품공전 제5장"` |

**코드에서 사용하는 쿼리 필드:**
- SELECT: `category_no, category_name, type_name, definition`
- ORDER BY: `id`
- FILTER: `category_no = '15'` 또는 `category_name ilike '%주류%'` (주류 판별 시)
- LIMIT: 60 (일반), 무제한 (주류)

---

### 2-2. `f2_required_documents` — 식품유형별 필요서류

> 현재 상태: **70행 적재 완료** ✅

| 컬럼명 | 타입 | Nullable | 설명 | 예시 |
|--------|------|----------|------|------|
| `id` | integer (PK, auto) | NO | 자동 증가 기본키 | 1 |
| `food_type` | text | YES | 식품유형명. NULL이면 모든 유형에 공통 적용 | `"위스키"`, `null` |
| `condition` | text | YES | 추가 조건 | `"주류"`, `null` |
| `doc_name` | text | NO | 서류명 (필수값) | `"주류 제조 기준 확인서"` |
| `doc_description` | text | YES | 서류 설명 | `"1년 이상 나무통 저장 필수..."` |
| `is_mandatory` | boolean | NO | 필수 여부 | `true` |
| `law_source` | text | YES | 법령 출처 | `"주세법 시행령 별표3"` |

**코드에서 사용하는 쿼리 필드:**
- SELECT: `doc_name, condition, is_mandatory, law_source, food_type`
- FILTER: `food_type = {분류결과}` (특정 유형) + `food_type IS NULL` (공통)

> ⚠️ **주의**: `doc_description` 컬럼이 DB에 존재하지만 현재 `feature2.py`의 `_get_required_docs()`가 SELECT하지 않음. 프론트엔드에서 서류 설명을 보여주려면 SELECT에 추가 필요.

---

## 3. Pinecone 인덱스

> 현재 상태: **1,340벡터, Ready** ✅

| 항목 | 값 |
|------|----|
| 인덱스명 | `samc-a` |
| 차원 | 1,536 (text-embedding-3-small) |
| 메트릭 | cosine |
| 총 벡터 수 | 1,340개 |
| 상태 | Ready ✅ |
| Host | `samc-a-bobg9xh.svc.aped-4627-b74a.pinecone.io` |
| 클라우드 | AWS us-east-1 (serverless) |

**벡터 메타데이터 구조:**

| 필드명 | 설명 |
|--------|------|
| `text` | 청크 본문 (최대 1,000자) |
| `food_group` | 대분류명 = `category_name` |
| `type_name` | 소분류명 |
| `category_no` | 대분류 번호 |
| `law` | `"식품공전"` |
| `category` | `"food_type"` |
| `effective_date` | `"2024-01-01"` |
| `law_number` | `"식품의약품안전처 고시"` |
| `char_count` | 텍스트 길이 |
| `chunk_index` | 순번 |

**코드에서 사용하는 메타데이터 필드:**
- `text` (RAG 컨텍스트)
- `food_group` (LLM 프롬프트 구성)
- `type_name` (LLM 프롬프트 구성)
- `score` (Pinecone 유사도 점수, 상위 5개 사용)

---

## 4. F2가 다른 테이블에서 필요한 정보

> F2 소유 테이블이 아니므로 직접 수정 금지. 조회만 가능.

### `pipeline_steps` (공용)

F2가 **저장**하는 필드 (step_key = `'2'`):

| 컬럼 | 값 |
|------|----|
| `case_id` | 케이스 UUID |
| `step_key` | `"2"` |
| `step_name` | `"food_type"` |
| `status` | `"running"` → `"waiting_review"` → `"completed"` → `"error"` |
| `ai_result` | 아래 JSON 구조 |
| `final_result` | 담당자 수정 결과 (PATCH 시) |
| `edit_reason` | 수정 사유 (PATCH 시) |

`ai_result` JSON 구조:
```json
{
  "category_name":    "대분류명 (식품군)",
  "category_no":      "대분류 번호",
  "subcategory_name": "중분류명 (없으면 null)",
  "food_type":        "소분류명 (식품유형)",
  "law_ref":          "근거 법령",
  "reason":           "분류 근거 2~3줄",
  "is_alcohol":       true / false,
  "required_docs":    [ { "doc_name": ..., "condition": ..., "is_mandatory": ..., "law_source": ..., "food_type": ... } ],
  "source_doc":       "분류에 사용된 서류 파일명"
}
```

F2가 **읽는** 데이터 (다른 담당자 소유):

- **f0 결과** (step_key = `'0'`): `ai_result` 안의 `basic_info.product_name`, `basic_info.export_country`, `ingredients[].name`, `ingredients[].ratio`, `process_info.process_codes[]`, `process_info.raw_process_text`
- **F1 결과** (step_key = `'1'`): `ai_result` 안의 `verdict`, `import_possible`, `ingredients[].name`, `ingredients[].status`, `ingredients[].law_ref`, `fail_reasons[]`

### `documents` (공용, f0 소유)

F2에서는 `doc_type = 'ingredients'`이고 `parsed_md`가 있는 문서의 **OCR 텍스트**가 필요합니다. (f0 결과가 없을 때 fallback으로 사용)

| 필드 | F2 사용 목적 |
|------|-------------|
| `parsed_md` | LLM 입력 텍스트 (fallback) |
| `doc_type` | `'ingredients'` 필터 |
| `file_name` | `ai_result.source_doc`에 기록 |

### `cases` (공용, f0 소유)

F2에서는 **케이스 존재 여부 확인**에만 사용합니다.

| 필드 | F2 사용 목적 |
|------|-------------|
| `id` | 케이스 UUID (존재 확인) |
| `product_name` | 케이스 조회 확인용 |

---

## 5. 환경변수

| 키 | 설명 | 상태 |
|----|------|------|
| `SUPABASE_URL` | Supabase 프로젝트 URL (공용) | ✅ 설정 완료 |
| `SUPABASE_SERVICE_KEY` | Supabase 서비스 키 (공용) | ✅ 설정 완료 |
| `F2_OPENAI_API_KEY` | GPT-4o + text-embedding-3-small | ✅ 설정 완료 |
| `F2_PINECONE_API_KEY` | Pinecone samc-a 인덱스 | ✅ 설정 완료 |
| `F2_PINECONE_INDEX` | 인덱스명 (기본값: `samc-a`) | ✅ 설정 완료 |

---

## 6. 남은 코드 수정 작업

### 필수

| # | 파일 | 내용 |
|---|------|------|
| 1 | `frontend/features/feature2/FoodClassificationPage.tsx` | API 경로 변경: `/step2`, `/step2-verdict`, `/step3` → `runFeature2(caseId)` / `getFeature2(caseId)` |
| 2 | `frontend/features/feature2/FoodClassificationPage.tsx` | 파일 업로드 UI(STEP1) 제거 — f0에서 처리됨 |
| 3 | `frontend/features/feature2/FoodClassificationPage.tsx` | `useParams()`로 `caseId` 주입 |
| 4 | `frontend/features/feature2/FoodClassificationPage.tsx` | 커스텀 CSS 클래스 → Tailwind 교체, f0 레이아웃 구조 적용 |
| 5 | `backend/routers/feature2.py` | `async def run_feature2` → `def` 변경 (동기 블로킹 I/O 해결) |
| 6 | `backend/routers/feature2.py` | line 367: `selected_doc` None 가드 추가 |
| 7 | `backend/requirements.txt` | `pinecone-client>=5.0.0` → `pinecone>=5.0.0` |

### 선택 (기능 개선)

| # | 파일 | 내용 |
|---|------|------|
| 8 | `backend/routers/feature2.py` | `_get_required_docs()` SELECT에 `doc_description` 추가 — 현재 DB에 있지만 코드에서 누락 |

---

## 7. 현재 인프라 상태 체크리스트

| 항목 | 상태 | 비고 |
|------|------|------|
| Supabase `f2_food_type_classification` | ✅ 235행 | 식품공전 제5장 기준 |
| Supabase `f2_required_documents` | ✅ 70행 | required_documents_아람.csv 기준 |
| Pinecone `samc-a` | ✅ 1,340벡터 / Ready | dim=1536, cosine, AWS us-east-1 |
| `backend/.env` | ✅ 전체 설정 완료 | SUPABASE / F2_OPENAI / F2_PINECONE |
| `pipeline_steps` 테이블 | ✅ 존재 | 34행 (테스트 데이터 포함) |
