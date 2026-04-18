# F4 성은 — 수출국 표시사항 검토 담당자 문서

> 작성일: 2026-04-17
> 담당: 성은 (기능4 — 수출국 표시사항 검토)

---

## 1. 담당 파일 목록

| 구분 | 파일 경로 |
|------|----------|
| 백엔드 라우터 | `backend/routers/feature4.py` |
| 프론트엔드 페이지 | `frontend/app/cases/[id]/f4/page.tsx` |
| 프론트엔드 훅 | `frontend/features/feature4/hooks/useForeignLabelCheck.ts` |
| 프론트엔드 타입 | `frontend/features/feature4/types.ts` |
| 프론트엔드 상수 | `frontend/features/feature4/constants.ts` |
| DB 스키마 | `backend/db/feature4/schema.sql` |
| 전처리: 법령 임베딩 | `backend/db/feature4/preprocess_laws.py` |
| 전처리: 금지 키워드 추출 | `backend/db/feature4/extract_prohibited_keywords.py` |
| 전처리: 이미지 위반 유형 추출 | `backend/db/feature4/extract_image_violation_types.py` |
| 전처리: 이미지 위반 유형 시드 | `backend/db/feature4/seed_image_violation_types.py` |

---

## 2. F4 전용 Supabase 테이블

### 2-1. `f4_law_documents` — 법령 문서 메타데이터

| 컬럼명 | 타입 | Nullable | 설명 | 예시 |
|--------|------|----------|------|------|
| `id` | UUID (PK, auto) | NO | 자동 생성 기본키 | `a1b2c3d4-...` |
| `law_name` | text | NO | 법령명 | `"식품등의 부당한 표시 또는 광고의 내용 기준"` |
| `고시번호` | text | YES | 고시번호 | `"제2025-79호"` |
| `시행일` | date | YES | 시행일 | `2025-12-04` |
| `source_file` | text | NO | 원본 파일명 | `"부당표시광고_기준.pdf"` |
| `법령_tier` | integer | NO (default 4) | 법령 계층 (1=법률 2=시행령 3=시행규칙 4=고시) | `4` |
| `total_chunks` | integer | YES (default 0) | Pinecone에 적재된 청크 수 | `230` |
| `prohibition_hint_patterns` | text[] | YES (default '{}') | 법령 고유 금지 마커 어구 (AI 자동 추출) | `{"혈당","암 예방"}` |
| `is_updating` | boolean | NO (default FALSE) | 법령 업데이트 진행 중 플래그 (TRUE이면 F4 분석 차단) | `false` |
| `created_at` | timestamptz | YES (default NOW()) | 생성 시각 | |

**코드에서 사용하는 쿼리 패턴:**
- SELECT: `id, total_chunks, prohibition_hint_patterns` — 법령별 Pinecone 적재 상태 확인
- SELECT: `law_name` WHERE `is_updating = TRUE` — 분석 요청 시 업데이트 중 법령 체크
- FILTER: `law_name = {법령명}`
- UPDATE: 법령 전처리(`preprocess_laws.py`) 시 메타데이터 덮어쓰기 (행 삭제 X → FK 보존)
- UPDATE: `is_updating = TRUE/FALSE` — 업데이트 시작/완료 플래그

**법령 개정 처리 방식 (삭제 → 재삽입):**
1. `is_updating = TRUE` 설정 → F4 분석 차단
2. Pinecone 기존 벡터 전부 삭제
3. 새 PDF 처리 → 새 벡터 삽입
4. Supabase `f4_law_documents` UPDATE (행 삭제 X → FK 보존)
5. `f4_prohibited_expressions` 해당 법령 키워드 DELETE → 재추출
6. `f4_image_violation_types` 해당 법령 auto 유형 DELETE → 재추출
7. `is_updating = FALSE` 해제 (try-finally로 크래시 시에도 해제)
8. 고시번호/시행일은 PDF 본문에서 자동 파싱 (수동 입력 불필요)

---

### 2-2. `f4_prohibited_expressions` — 금지 표현 키워드 목록

> 1차 빠른 필터용: AI 분석 전 Supabase에서 먼저 매칭해 명백한 위반 감지

| 컬럼명 | 타입 | Nullable | 설명 | 예시 |
|--------|------|----------|------|------|
| `id` | UUID (PK, auto) | NO | 자동 생성 기본키 | |
| `keyword` | text | NO | 금지 키워드 | `"혈당 낮춤"`, `"암 예방"` |
| `category` | text | NO | 위반 카테고리 (동적 확장 가능) | `"질병치료"`, `"허위과장"`, `"의약품오인"`, `"기능성"` |
| `severity` | text | NO | `'must_fix'` 또는 `'review_needed'` | `"must_fix"` |
| `law_ref` | text | NO | 근거 조문 | `"제3조제1항제1호"` |
| `law_document_id` | UUID (FK) | YES | f4_law_documents 참조 | |
| `example` | text | YES | 실제 위반 사례 문구 | `"이 제품을 드시면 혈당이 낮아집니다"` |
| `created_at` | timestamptz | YES (default NOW()) | 생성 시각 | |

**인덱스:**
- `idx_prohibited_keyword` → `keyword`
- `idx_prohibited_category` → `category`
- `idx_prohibited_severity` → `severity`

**코드에서 사용하는 쿼리 패턴:**
- SELECT: `keyword, category, severity, law_ref` — 전체 키워드 목록 조회 (프롬프트 구성용, 상위 80건)
- SELECT: `category` — 전체 카테고리 목록 조회 (동적 카테고리 확장용)
- DELETE → INSERT: 법령 개정 시 해당 `law_document_id`의 키워드 전부 삭제 후 재추출 (`extract_prohibited_keywords.py`)

---

### 2-3. `f4_image_violation_types` — 이미지 위반 유형 목록

> 26개 시드 유형 + 법령 개정 시 자동 추출된 유형

| 컬럼명 | 타입 | Nullable | 설명 | 예시 |
|--------|------|----------|------|------|
| `id` | UUID (PK, auto) | NO | 자동 생성 기본키 | |
| `type_name` | text (UNIQUE) | NO | 위반 유형명 | `"질병 치료·예방 암시"` |
| `sub_items` | text | NO (default '') | 세부 항목 (쉼표 구분) | `"심장·간·혈관 치료 그림, X레이 이미지..."` |
| `default_severity` | text | NO (default 'review_needed') | 기본 심각도 (`'must_fix'` / `'review_needed'`) | `"must_fix"` |
| `severity_condition` | text | NO (default '') | 심각도 판단 조건 | `"수치/비교 명시 시 must_fix"` |
| `law_ref` | text | NO (default '') | 근거 조문 | `"제2025-79호 제3조제1항제1호"` |
| `source` | text | NO (default 'auto') | 출처 (`'seed'` / `'auto'`) | `"seed"` |
| `source_law_name` | text | YES | 자동 추출 시 출처 법령명 | `"식품등의 부당한 표시..."` |
| `is_active` | boolean | NO (default TRUE) | 활성 여부 (auto: confidence>=0.8이면 TRUE) | `true` |
| `review_note` | text | NO (default '') | 검토 메모 | `"AI 판단 불확실 — 직접 확인 권고"` |
| `created_at` | timestamptz | YES (default NOW()) | 생성 시각 | |
| `updated_at` | timestamptz | YES (default NOW()) | 수정 시각 | |

**인덱스:**
- `idx_image_violation_type_name` → `type_name`
- `idx_image_violation_source` → `source`
- `idx_image_violation_source_law` → `source_law_name`
- `idx_image_violation_is_active` → `is_active`

**코드에서 사용하는 쿼리 패턴:**
- SELECT: `type_name, sub_items, default_severity, severity_condition, law_ref, is_active` — 이미지 분석 프롬프트 동적 생성용
- ORDER BY: `created_at`
- INSERT: 시드 데이터(`seed_image_violation_types.py`)
- DELETE → INSERT: 법령 개정 시 해당 `source_law_name`의 auto 유형 삭제 후 재추출 (seed 유형은 유지)

---

### 2-4. `f4_results` — F4 분석 결과 저장

> ⚠️ `schema.sql`에 정의되지 않음 — Supabase 대시보드에서 직접 생성된 것으로 추정

| 컬럼명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| `id` | (PK) | 기본키 | |
| `case_id` | text | 케이스 UUID | `"abc-123..."` |
| `status` | text | 처리 상태 | `"waiting_review"`, `"completed"` |
| `ai_result` | jsonb | AI 분석 결과 (전체) | 아래 JSON 구조 참고 |
| `final_result` | jsonb | 담당자가 선택한 최종 결과 | ai_result와 동일 구조 |
| `validation_result` | jsonb | 법령 정합성 검증 결과 (임시) | 아래 JSON 구조 참고 |
| `edit_reason` | text | 수정 사유 (식약처 소명용) | `"기능성 허가 제품으로 확인"` |
| `created_at` | timestamptz | 생성 시각 | |

**코드에서 사용하는 쿼리 패턴:**
- SELECT: `id` — 기존 결과 존재 여부 확인 (upsert)
- SELECT: `*` — 결과 조회 (GET 엔드포인트, 레포트 생성)
- INSERT: `case_id, ai_result, status` — 최초 분석 결과 저장
- UPDATE: `ai_result, status` — 재분석 시 갱신
- UPDATE: `final_result, edit_reason, status` — 담당자 수정 저장
- UPDATE: `validation_result` — 법령 검증 결과 임시 저장
- UPDATE: `status = "completed"` — 확인 완료
- FILTER: `case_id = {케이스ID}`

**`ai_result` JSON 구조:**
```json
{
  "overall": "pass" | "fail" | "review_needed",
  "issues": [
    {
      "text": "문제 표현 원문",
      "location": "라벨 상 위치",
      "reason": "위반 사유",
      "law_ref": "근거 법령 조문",
      "severity": "must_fix" | "review_needed"
    }
  ],
  "image_issues": [
    {
      "description": "이미지 요소 설명",
      "location": "라벨 상 위치",
      "violation_type": "①~㉖ 중 해당 유형",
      "law_ref": "근거 조문",
      "reasoning": "판단 근거",
      "severity": "must_fix" | "review_needed",
      "recommendation": "수정 권고",
      "review_level": "confirmed" | "suggested",
      "source_image_id": "<image_id>"
    }
  ],
  "cross_check": [
    {
      "field": "product_name" | "ingredients" | "content_volume" | "origin" | "manufacturer",
      "label_value": "라벨에 표기된 값",
      "doc_value": "서류의 값",
      "match": true | false,
      "note": "불일치 설명"
    }
  ]
}
```

**`validation_result` JSON 구조:**
```json
{
  "is_valid": true | false,
  "conflicts": [
    {
      "law_refs": ["관련 조문1", "관련 조문2"],
      "description": "충돌 내용 요약",
      "reasoning": "판단 근거 설명",
      "recommendation": "권고 처리 방법"
    }
  ],
  "dependencies": [
    {
      "selected_law_ref": "선택된 조문",
      "required_law_ref": "함께 처리해야 하는 조문",
      "description": "의존 관계 요약",
      "reasoning": "함께 필요한 이유"
    }
  ],
  "applied_principles": "적용한 법령 해석 원칙 요약",
  "summary": "전체 검토 결과 한 줄 요약"
}
```

---

## 3. Pinecone 인덱스

| 항목 | 값 |
|------|----|
| 인덱스명 | `samc-feature4-laws` |
| 차원 | 1,024 (multilingual-e5-large) |
| 메트릭 | cosine |
| 벡터 ID 형식 | MD5("{law_name}\|{chunk_index:05d}") — 결정적, 법령명 기준 (고시번호 제외) |

**벡터 메타데이터 구조:**

| 필드명 | 설명 |
|--------|------|
| `text` | 청크 본문 (최대 1,000자) |
| `law_name` | 법령명 |
| `고시번호` | 고시번호 |
| `조문번호` | 조문번호 (예: 제3조제1항제1호) |
| `법령_tier` | 법령 계층 (1~4) |
| `law_doc_id` | f4_law_documents UUID |

**코드에서 사용하는 쿼리 패턴:**
- Query: `query: {label_text}` → top-5 유사도 검색 (RAG 컨텍스트)
- Fetch: ID 기반 청크 텍스트 수집 (100개 배치)
- 법령 개정 시: Delete(해당 법령 전체 벡터 삭제) → Insert(새 벡터 전체 삽입) — 100개 배치 단위

---

## 4. F4가 다른 테이블에서 필요한 정보

> F4 소유 테이블이 아니므로 직접 수정 금지. 조회만 가능.

### `pipeline_steps` (공용)

F4가 **읽는** 데이터:

| step_key | 출처 | 읽는 필드 | F4 사용 목적 |
|----------|------|-----------|-------------|
| `'0'` (F0) | ai_result | `basic_info.product_name`, `basic_info.export_country`, `ingredients[].name`, `ingredients[].origin`, `label_info.label_texts[]`, `label_info.export_country` | **교차검증** (라벨↔서류 비교) + 라벨 OCR 텍스트 |
| `'1'` (F1) | ai_result / final_result | `ingredients[].name` | 금지 표현 분석 프롬프트용 원재료 참고 (교차검증 X) |
| `'2'` (F2) | ai_result / final_result | `food_type` | 금지 표현 분석 프롬프트용 식품유형 참고 (교차검증 X) |

> **교차검증과 F1/F2의 차이:** 교차검증(라벨↔서류 일치 비교)은 **f0의 원본 OCR 데이터**만 사용합니다. F1/F2 데이터는 이미 한국어로 번역/가공된 상태이므로, 원문 비교가 아닌 AI 분석 프롬프트의 맥락 보충용으로만 사용됩니다.
>
> ⚠️ F1·F2 연동은 PM이 임의로 추가한 파이프라인 연결입니다. `_fetch_f1_result()`, `_fetch_f2_result()` 함수와 `_run_analysis` 내 호출부를 제거하면 해제됩니다.

### `case_label_images` (공용, F0 소유)

F4에서 크롭된 라벨 이미지를 조회하여 Vision API로 분석합니다.

| 필드 | F4 사용 목적 |
|------|-------------|
| `id` | 이미지 식별자 → `image_issues[].source_image_id`에 기록 |
| `case_id` | 케이스별 이미지 필터 |
| `source_document_id` | dedup 기준 (최신 것만 유지) |
| `cropped_storage_path` | Supabase Storage에서 이미지 다운로드 / Signed URL 생성 |

**쿼리 패턴:**
- SELECT: `id, source_document_id, cropped_storage_path`
- FILTER: `case_id = {케이스ID}`
- ORDER BY: `created_at DESC`
- Dedup: `source_document_id` 기준 최신 1개만
- LIMIT: 없음 — 코드상 이미지 수 상한 없이 전부 분석

**이미지 처리 수량:**
- 코드에 이미지 수 제한 없음. `case_label_images`에 있는 만큼 전부 가져와서 개별 Vision API 호출
- 단, `source_document_id` 기준 dedup 적용 → **문서당 최신 1장만** 분석
- 예: 문서A에서 크롭 3장 + 문서B에서 크롭 2장 → 총 2장 분석 (문서당 1장)

### `cases` (공용, F0 소유)

F4에서는 **케이스 존재 여부 확인**에만 사용합니다.

---

## 5. 환경변수

| 키 | 설명 | 상태 |
|----|------|------|
| `SUPABASE_URL` | Supabase 프로젝트 URL (공용) | ✅ 설정 완료 |
| `SUPABASE_SERVICE_KEY` | Supabase 서비스 키 (공용) | ✅ 설정 완료 |
| `F4_OPENAI_API_KEY` | GPT-5.4-nano + Vision API | ✅ 설정 완료 |
| `F4_PINECONE_API_KEY` | Pinecone samc-feature4-laws 인덱스 | ✅ 설정 완료 |
| `F4_PINECONE_HOST` | Pinecone 호스트 URL (인덱스명이 아닌 host) | ✅ 설정 완료 |
| `F4_DEEPL_API_KEY` | DeepL 번역 (현재 코드에서 미사용) | ✅ 설정 완료 |

---

## 6. API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/v1/cases/{case_id}/pipeline/feature/4/analyze` | 분석 실행 |
| GET | `/api/v1/cases/{case_id}/pipeline/feature/4` | 결과 조회 |
| POST | `/api/v1/cases/{case_id}/pipeline/feature/4/validate` | 선택 항목 법령 정합성 검토 |
| PATCH | `/api/v1/cases/{case_id}/pipeline/feature/4` | final_result 저장 |
| POST | `/api/v1/cases/{case_id}/pipeline/feature/4/confirm` | 확인 완료 |
| GET | `/api/v1/cases/{case_id}/pipeline/feature/4/report` | PDF 레포트 다운로드 |

**처리 흐름:**
```
analyze → (사용자 체크) → validate → (사용자 확인) → PATCH → confirm
```

**분석 차단 조건:**
- `/analyze` 요청 시 `f4_law_documents`에 `is_updating = TRUE`인 법령이 있으면 → 503 `LAW_DB_UPDATING` 반환
- 프론트엔드: 노란색 배너 "현재 법령 DB가 업데이트 중입니다. 잠시 후 다시 시도해주세요."

---

## 7. 외부 API 호출

### OpenAI (GPT-5.4-nano)

| 용도 | 프롬프트 | 입력 | 출력 |
|------|---------|------|------|
| 텍스트 위반 분석 | `_ANALYSIS_PROMPT` | food_type, ingredients, label_text, law_chunks(RAG), prohibited_keywords | `{ overall, issues[] }` |
| 라벨↔서류 교차검증 | `_CROSS_CHECK_PROMPT` | label_text, doc_product_name/volume/origin/manufacturer/ingredients | `cross_check[]` |
| 이미지 위반 분석 | `_IMAGE_ANALYSIS_PROMPT` (동적 생성 가능) | 라벨 이미지 Signed URL + 26개 위반 유형 | `image_issues[]` |
| 법령 정합성 검증 | `_VALIDATE_PROMPT` | 선택된 위반 항목들 | `{ is_valid, conflicts[], dependencies[] }` |

### Pinecone (multilingual-e5-large)

- 벡터 유사도 검색: `label_text` → top-5 관련 법령 조문 (RAG 컨텍스트)

### Supabase Storage

- 이미지 다운로드: `documents` 버킷에서 크롭된 라벨 이미지
- Signed URL 생성: Vision API에 전달할 임시 URL (유효시간 1시간)

---

## 8. 현재 인프라 상태 체크리스트

| 항목 | 상태 | 비고 |
|------|------|------|
| Supabase `f4_law_documents` | ✅ | 6개 핵심 법령 메타데이터 + `is_updating` 플래그 |
| Supabase `f4_prohibited_expressions` | ✅ | 2단계 추출 (규칙 + AI 교차검증), 개정 시 DELETE→재삽입 |
| Supabase `f4_image_violation_types` | ✅ | 26개 시드 유형 (전체 active), 개정 시 auto 유형 DELETE→재삽입 |
| Supabase `f4_results` | ✅ | 분석 결과 저장 (schema.sql 미포함) |
| Pinecone `samc-feature4-laws` | ✅ | dim=1024, cosine, multilingual-e5-large, 개정 시 DELETE→재삽입 |
| `backend/.env` | ✅ 전체 설정 완료 | SUPABASE / F4_OPENAI / F4_PINECONE |

---

## 9. 법령 개정 업데이트 흐름

```
[법령 DB 관리 페이지] 관리자가 법령 카드에 개정 PDF 업로드
  → "선택한 법령 업데이트" 클릭
  → 관련 기능 전처리 병렬 실행 (F4, F1, F5 등 — LAW_FEATURE_MAP 기준)

[F4 전처리 흐름]
  1. is_updating = TRUE 설정 → F4 /analyze 503 차단
  2. Pinecone: 해당 법령 기존 벡터 전부 삭제
  3. 새 PDF 텍스트 추출 → 고시번호/시행일 자동 파싱
  4. 조문 청킹 + 표/이미지 추출 → 임베딩 → Pinecone 삽입
  5. Supabase f4_law_documents UPDATE (고시번호, 시행일, total_chunks 등)
  6. f4_prohibited_expressions: 해당 법령 키워드 DELETE → 재추출
  7. f4_image_violation_types: 해당 법령 auto 유형 DELETE → 재추출 (seed 유지)
  8. 프롬프트 캐시 무효화
  9. is_updating = FALSE 해제 (try-finally — 크래시 시에도 해제)

[크래시 발생 시]
  → is_updating 자동 해제 (try-finally)
  → 관리자 화면에 빨간 배너: "법령 업데이트 중 오류 발생"
  → 복구 안내: "파일을 다시 업로드하여 재시도해주세요"
  → 기존 데이터는 초기화 상태 → 재업로드 필수

[F4 분석 사용자 입장]
  → 업데이트 중 분석 요청 시: 노란 배너 "법령 DB 업데이트 중입니다. 잠시 후 다시 시도해주세요."
```
