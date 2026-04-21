# SAMC — 수입식품 검역 AI 플랫폼

수입식품의 통관 검역 업무를 자동화하는 AI 기반 웹 애플리케이션입니다.

서류를 업로드하면, AI가 원재료를 분석하고 수입 가능 여부를 판정하고, 식품유형을 분류하고, 필요서류를 안내하고, 라벨을 검토하고, 한글 표시사항 시안까지 자동 생성합니다.

> **최종 업데이트**: 2026-04-21

---

## 서비스 흐름

사용자가 서류를 업로드하면, 아래 6단계가 순차적으로 자동 실행됩니다.

```
서류 업로드 (F0)
  → 수입 판정 (F1)
    → 식품유형 분류 (F2)
      → 필요서류 안내 (F3)
        → 라벨 검토 (F4)
          → 한글 표시사항 시안 (F5)
```

각 단계의 결과를 검토하고 수정할 수 있으며, 수정하면 이후 단계가 자동으로 다시 실행됩니다.

---

## 6단계 파이프라인 상세

### F0 — 서류 업로드 + OCR 파싱

**역할**: 수입식품 관련 서류(원재료 배합비율표, 제조공정도, 라벨 이미지 등)를 업로드하면 AI가 텍스트를 추출하고 구조화합니다.

**핵심 기능**:
- PDF, 이미지, HWP, Excel 파일 업로드
- OpenAI GPT-4o 기반 OCR + LLM 파싱
- 원재료별 **식약처 성분코드 자동 매칭** (12,263건 DB + LLM 동의어 추천)
- 성분코드 후보 목록 제시 → 사용자가 선택 가능
- 라벨 이미지 자동 크롭 및 정보 추출

**출력**: 제품명, 수출국, 원재료 목록(성분코드 포함), 배합비율, 제조공정 정보

---

### F1 — 수입 가능 여부 판정

**역할**: 원재료가 한국 식품 법규에 적합한지 판정하고, 수입 가능 여부를 결정합니다.

**핵심 기능**:
- **Step A**: 금지원료 DB 체크 (f1_forbidden_ingredients)
- **Step B**: 원재료 허용여부 판정 (F0 성분코드 기반 — A=식품원료, B=식품첨가물, C=건강기능식품)
- **Step C**: 기준규격 수치 비교 (첨가물공전 기준치 vs 실제 함량)
- **Step D**: 관련 법령 검색 (f1_law_chunks 2,148건)
- **LLM 판정**: 법령 + 원재료 배합비율을 종합하여 수입가능/수입불가 결정

**출력**: 원재료별 매칭 결과, 기준규격 비교표, 관련 법령 인용, 최종 수입 판정

---

### F2 — 식품유형 분류

**역할**: 식품공전에 따라 제품의 식품유형(대분류 > 중분류 > 소분류)을 분류합니다.

**핵심 기능**:
- **food_class 태깅**: 각 원재료를 식품 카테고리(과일류, 채소류, 곡류, 유류 등)로 자동 분류
- **코드 기반 대분류 확정**: 제품명 + 원재료 카테고리 비율로 대분류(음료류, 과자류 등) 추론
- **LLM 소분류 결정**: 확정된 대분류 내에서 소분류 선택 (DB 235개 유형 중에서만)
- **코드 보정**: LLM 할루시네이션 방지 (예: 과일+채소 71%인데 "과자"로 분류 → "과·채음료"로 보정)
- **후보 3개 제시**: 1순위 자동 선택 + 2~3순위 대안을 라디오 버튼으로 표시
- **법령 원문 표시**: Supabase f2_food_type_classification에서 해당 유형의 정의 + 근거 법령

**출력**: 3단계 분류(대/중/소), 판정 근거(원재료별 카테고리 분석), 관련 법령 원문

---

### F3 — 수입 필요서류 안내

**역할**: 식품유형, 수출국, 원재료 등을 기반으로 수입 시 필요한 서류 목록을 안내합니다.

**핵심 기능**:
- 5축 AND 매칭 엔진 (식품유형, 수출국, OEM 여부, 제조공정, 조건)
- F0 성분코드 + F2 식품유형을 활용한 자동 매칭
- Pinecone 법령 시맨틱 검색 (samc-law-f3)

**출력**: 제출 서류 목록, 보관 서류 목록, 각 서류의 법적 근거

---

### F4 — 수출국 표시사항 검토

**역할**: 수출국 라벨의 텍스트/이미지를 분석하여 한국 식품 표시 법규 위반 여부를 검토합니다.

**핵심 기능**:
- 라벨 텍스트 분석 (의무 표시사항 누락, 부당 표시/광고)
- 라벨 이미지 분석 (인증마크, 로고, 경고 표시)
- 라벨 ↔ 서류 교차검증
- 법령 정합성 검증
- Pinecone RAG (samc-feature4-laws)

**출력**: 위반 항목(수정 필수/검토 필요), 교차검증 결과, 참고 법령

---

### F5 — 한글 표시사항 시안

**역할**: F0~F4 결과를 종합하여 한글 표시사항 시안을 자동 생성합니다.

**핵심 기능**:
- 2단계 교차검증 (1차 항목별 검토 + 2차 AI 재검증)
- 12개 항목 자동 생성 (제품명, 식품유형, 원재료명, 내용량, 소비기한, 보관방법, 제조사, 수입자, 알레르기, GMO, 영양성분, 원산지)
- 시안 직접 편집 가능
- DOCX/PDF 검토내역서 다운로드
- Pinecone RAG (f5-law-chunks) + Voyage-3 임베딩

**출력**: 한글 표시사항 시안, 교차검증 결과, 추가 이슈 목록

---

## 기술 스택

### 백엔드
| 기술 | 용도 |
|------|------|
| **FastAPI** | REST API 서버 |
| **OpenAI GPT-4o / GPT-4o-mini** | OCR 파싱, 식품유형 분류, 법령 판정, 성분코드 매칭 |
| **Supabase (PostgreSQL)** | 메인 DB — 케이스, 파이프라인 결과, 원재료 코드, 법령 데이터 |
| **Pinecone** | 벡터 검색 — 법령 시맨틱 검색 (F1~F5 각각 별도 인덱스) |
| **Python 3.14** | 백엔드 런타임 |

### 프론트엔드
| 기술 | 용도 |
|------|------|
| **Next.js 14** | React 프레임워크 (App Router) |
| **TypeScript** | 타입 안전성 |
| **Tailwind CSS** | 스타일링 |
| **Lucide React** | 아이콘 |

### 인프라
| 서비스 | 용도 |
|--------|------|
| **Vercel** | 프론트엔드 배포 |
| **Railway** | 백엔드 배포 |
| **Supabase** | DB + Storage + Auth |
| **Pinecone** | 벡터 DB |

---

## 데이터베이스 구조

### Supabase 주요 테이블

#### 공통
| 테이블 | 행 수 | 설명 |
|--------|-------|------|
| `cases` | - | 검역 케이스 (제품 1건 = 1 케이스) |
| `documents` | - | 업로드된 서류 파일 메타데이터 |
| `pipeline_steps` | - | F0~F5 각 단계의 실행 결과 (ai_result, final_result) |

#### F0 (서류 입력)
| 테이블 | 행 수 | 설명 |
|--------|-------|------|
| `f0_ingredient_codes` | 12,263건 | 식약처 성분코드 DB (코드, 한글명, 영문명, 카테고리) |

#### F1 (수입 판정)
| 테이블 | 행 수 | 설명 |
|--------|-------|------|
| `f1_forbidden_ingredients` | ~200건 | 금지원료 DB |
| `f1_allowed_ingredients` | 110건 | 허용원료 DB (v1 레거시) |
| `f1_additive_limits` | 893건 | 첨가물 사용기준 DB |
| `f1_law_chunks` | 2,148건 | 법령 텍스트 청크 (4개 공전 + 기능성표시 규정) |

#### F2 (식품유형 분류)
| 테이블 | 행 수 | 설명 |
|--------|-------|------|
| `f2_food_type_classification` | 235건 | 식품유형 정의 (대분류 > 소분류 + 정의 + 근거법령) |

#### F3 (필요서류)
| 테이블 | 행 수 | 설명 |
|--------|-------|------|
| `f3_required_documents` | ~70건 | 수입 필요서류 매칭 규칙 |

#### F4 (라벨 검토)
| 테이블 | 행 수 | 설명 |
|--------|-------|------|
| `f4_results` | - | F4 분석 결과 (별도 테이블) |
| `f4_law_documents` | - | F4 법령 메타데이터 |

### Pinecone 인덱스

| 인덱스 | 기능 | 임베딩 모델 |
|--------|------|-------------|
| `samc-law-f1` | F1 법령 검색 | text-embedding-3-small |
| `samc-a` | F2 식품유형 분류 RAG | text-embedding-3-small |
| `samc-law-f3` | F3 법령 검색 | multilingual-e5-large |
| `samc-feature4-laws` | F4 표시 법규 검색 | multilingual-e5-large |
| `f5-law-chunks` | F5 한글 표시 법규 검색 | Voyage-3 |

---

## 프로젝트 구조

```
SAMC_NEW_NEW/
├── backend/
│   ├── main.py                    # FastAPI 진입점
│   ├── .env                       # 환경변수 (API 키 등)
│   ├── routers/
│   │   ├── upload.py              # F0: 서류 업로드 + OCR
│   │   ├── feature1.py            # F1: 수입 판정
│   │   ├── feature2.py            # F2: 식품유형 분류
│   │   ├── feature3.py            # F3: 필요서류
│   │   ├── feature4.py            # F4: 라벨 검토
│   │   └── feature5.py            # F5: 한글 시안
│   ├── services/
│   │   ├── feature1.py            # F1 오케스트레이터
│   │   ├── f1_step_a.py           # Step A: 금지원료
│   │   ├── f1_step_b.py           # Step B: 원재료 매칭
│   │   ├── f1_step_c.py           # Step C: 기준규격
│   │   ├── f1_step_d.py           # Step D: 법령 인용
│   │   ├── f2_food_class.py       # F2: 원재료 카테고리 태깅
│   │   ├── f3_required_docs.py    # F3: 5축 매칭 엔진
│   │   ├── step6_label.py         # F5: 한글 시안 생성
│   │   ├── f5_rag.py              # F5: 법령 RAG
│   │   ├── safetydata_client.py   # 공전 데이터 조회
│   │   └── export_service.py      # DOCX/PDF 생성
│   ├── models/                    # Pydantic 모델
│   ├── db/                        # DB 마이그레이션, 시드 데이터
│   └── scripts/                   # 동기화 스크립트
│
├── frontend/
│   ├── app/
│   │   ├── dashboard/             # 대시보드
│   │   └── cases/[id]/
│   │       ├── upload/page.tsx    # 메인 페이지 (업로드 + 결과 뷰)
│   │       ├── f1/page.tsx        # F1 수입 판정
│   │       ├── f2/page.tsx        # F2 식품유형 분류
│   │       ├── f3/page.tsx        # F3 필요서류
│   │       ├── f4/page.tsx        # F4 라벨 검토
│   │       └── f5/page.tsx        # F5 한글 시안
│   ├── features/
│   │   ├── feature1/              # F1 컴포넌트
│   │   ├── feature2/              # F2 컴포넌트
│   │   ├── feature3/              # F3 컴포넌트
│   │   ├── feature4/              # F4 컴포넌트
│   │   └── feature5/              # F5 컴포넌트
│   └── components/
│       ├── ocr/                   # OCR 결과 편집기
│       ├── upload/                # 파일 업로드
│       └── layout/                # 레이아웃 (StepNavigation 등)
│
└── docs/                          # 설계 문서
```

---

## 환경변수

### 백엔드 (.env)

```env
# 공통: Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=xxx
SUPABASE_ANON_KEY=xxx

# F0 (OCR)
F0_OPENAI_API_KEY=xxx
F0_OPENAI_MODEL=gpt-4o

# F1 (수입 판정)
F1_OPENAI_API_KEY=xxx
F1_OPENAI_CHAT_MODEL=gpt-5.4-mini
F1_PINECONE_API_KEY=xxx
F1_PINECONE_INDEX=samc-law-f1
F1_USE_DATA_GO_KR_API=true
F1_CANARY_PERCENTAGE=100
F1_STEP_D_MIN_SCORE=0.05

# F2 (식품유형 분류)
F2_OPENAI_API_KEY=xxx
F2_PINECONE_API_KEY=xxx
F2_PINECONE_INDEX=samc-a

# F3 (필요서류)
F3_PINECONE_API_KEY=xxx
F3_PINECONE_INDEX_NAME=samc-law-f3
F3_OPENAI_API_KEY=xxx

# F4 (라벨 검토)
F4_OPENAI_API_KEY=xxx
F4_PINECONE_API_KEY=xxx
F4_PINECONE_HOST=xxx
F4_DEEPL_API_KEY=xxx
LAW_API_OC=xxx

# F5 (한글 시안)
F5_OPENAI_API_KEY=xxx
F5_PINECONE_API_KEY=xxx
F5_VOYAGE_API_KEY=xxx
F5_PINECONE_INDEX=f5-law-chunks
```

### 프론트엔드 (.env.local)

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=xxx
```

---

## 실행 방법

### 백엔드

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 프론트엔드

```bash
cd frontend
npm install
npm run dev
```

---

## 사용자 워크플로우

1. **대시보드**에서 새 검역 건 생성
2. **서류 업로드** — 원재료배합비율표, 제조공정도, 라벨 이미지 등 업로드
3. **OCR 분석 시작** — AI가 서류를 파싱하고 원재료를 식별
4. **검역 분석 시작** — F1~F5가 순차 자동 실행
5. **결과 확인** — 각 단계별 결과 확인 및 수정
6. **수정 확정** — 수정 시 후속 단계 자동 재실행
7. **DOCX/PDF 다운로드** — 검토내역서 다운로드

---

## 라이선스

비공개 프로젝트
