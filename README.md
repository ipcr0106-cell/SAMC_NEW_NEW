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

**역할**: 수입식품 관련 서류를 업로드하면 AI가 텍스트를 추출하고 구조화합니다.

**처리 흐름**:
```
서류 업로드 (PDF/이미지/HWP/Excel)
  → OpenAI GPT-4o Vision OCR
    → LLM 구조화 파싱 (원재료, 배합비율, 제조공정 추출)
      → 성분코드 자동 매칭
```

**성분코드 매칭 로직**:
```
1. Supabase f0_ingredient_codes (12,263건)에서 정확 매칭 시도
2. 한글명 실패 → 영문명으로 재시도
3. 영문명도 실패 → LLM에게 식약처 공식 성분명 추천 요청
   예: "이산화황" → LLM → "무수아황산" → DB 매칭 성공
4. 매칭된 후보 목록을 사용자에게 드롭다운으로 제시
5. 사용자가 선택하면 DB에 저장
```

**출력**: 제품명, 수출국, 원재료 목록(성분코드 포함), 배합비율, 제조공정 정보

---

### F1 — 수입 가능 여부 판정

**역할**: 원재료가 한국 식품 법규에 적합한지 판정하고, 수입 가능 여부를 결정합니다.

**처리 흐름**:
```
Step A: 금지원료 체크
  → 금지원료 발견 시 즉시 "수입불가" 확정
  ↓ (통과)
Step B: 원재료 허용여부 판정
  → F0 성분코드 접두어로 판정 (A=식품원료→허용, B=첨가물→허용+경고, C=건강기능식품→조건부)
  → 미확인 원재료 있으면 "수입불가"
  ↓ (모두 허용)
Step C: 기준규격 수치 비교
  → 첨가물공전 기준치 vs 실제 함량 비교
  → 기준 초과 시 "수입불가"
  ↓
Step D: 관련 법령 검색
  → f1_law_chunks (2,148건)에서 키워드 검색
  ↓
LLM 종합 판정
  → 법령 텍스트 + 원재료 배합비율을 GPT에게 전달
  → 각 원재료별 "기준: X / 실제: Y → 적합/부적합" 판정
  → 모두 적합 → "수입가능" / 하나라도 부적합 → "수입불가"
```

**판정 우선순위**:
1. Step C 기준치 초과 → 수입불가 (confidence 0.90)
2. 미확인 원재료 → 수입불가 (confidence 0.60)
3. 조건부 원재료 → 조건부 수입가능 (confidence 0.75)
4. 모두 통과 → LLM 판정 결과 적용

**출력**: 원재료별 매칭 결과, 기준규격 비교표, LLM 법령 분석, 최종 수입 판정

---

### F2 — 식품유형 분류

**역할**: 식품공전에 따라 제품의 식품유형(대분류 > 중분류 > 소분류)을 분류합니다.

**처리 흐름**:
```
1단계: 원재료 카테고리 태깅 (LLM, 결과 캐시)
  → 각 원재료를 과일류/채소류/곡류/유류/식육류/당류/기타로 분류
  → 예: 코코넛워터 → 과일류, 설탕 → 당류, 카제인나트륨 → 기타

2단계: 코드 기반 대분류 확정
  → 제품명 키워드: "milk", "drink" → 음료류
  → 원재료 카테고리: 식육 50%↑ → 식육가공품, 유류 30%↑ → 유가공품
  → 확정된 대분류의 유형만 LLM 후보로 전달

3단계: LLM 소분류 결정
  → 대분류 내 유형만 후보 (예: 음료류 15개)
  → DB에 있는 type_name 중에서만 선택 (임의 유형 생성 금지)

4단계: 코드 보정 (LLM 할루시네이션 방지)
  → 과일+채소 비율 10%↑인데 "기타음료" 선택 → "과·채음료"로 강제 보정
  → 식육 50%↑인데 음료로 분류 → 식육가공품으로 보정

5단계: 후보 3개 제시
  → 1순위(AI 추천) + 2~3순위(대안) 라디오 버튼
  → 사용자가 변경 가능
```

**식품유형 분류 원칙 (식약처 10단계)**:
```
① 자연산물 → ② 타법령(주류/축산물) → ③ 특수용도식품
→ ④ 단순가공 → ⑤ 기본원료(전분/당/유지)
→ ⑥ 용도별(간편식/간식/음료/조미/반찬)
→ ⑦ 특정원료 → ⑧ 특정제조방법 → ⑨ 주원료별 → ⑩ 기타가공품
```

**출력**: 3단계 분류(대/중/소), 판정 근거(원재료별 카테고리 분석), 관련 법령 원문, 후보 3개

---

### F3 — 수입 필요서류 안내

**역할**: 식품유형, 수출국, 원재료 등을 기반으로 수입 시 필요한 서류 목록을 안내합니다.

**처리 흐름**:
```
F0 성분코드 + F2 식품유형 + F0 수출국
  → 5축 AND 매칭 엔진
    축1: 식품유형 (예: 과·채음료)
    축2: 수출국 (예: 베트남)
    축3: OEM 여부
    축4: 제조공정
    축5: 특별 조건 (유기인증, 최초수입 등)
  → 매칭된 서류 목록 (제출 서류 + 보관 서류)
  → Pinecone 법령 시맨틱 검색으로 법적 근거 보강
```

**출력**: 제출 서류 목록, 보관 서류 목록, 각 서류의 법적 근거

---

### F4 — 수출국 표시사항 검토

**역할**: 수출국 라벨의 텍스트/이미지를 분석하여 한국 식품 표시 법규 위반 여부를 검토합니다.

**처리 흐름**:
```
F0 라벨 텍스트 + 라벨 이미지
  → 텍스트 분석: 의무 표시사항 누락, 부당 표시/광고 검출
  → 이미지 분석: 인증마크, 건강 관련 표현, 경고 문구
  → 교차검증: 라벨 내용 vs 서류 내용 일치 여부
  → 법령 정합성: 선택 항목 간 충돌/의존 관계 검토
  → Pinecone RAG로 관련 법령 원문 첨부
```

**위반 등급**:
- `must_fix`: 반드시 수정해야 통관 가능
- `review_needed`: 검토 후 판단 필요

**출력**: 위반 항목(수정 필수/검토 필요), 교차검증 결과, 참고 법령

---

### F5 — 한글 표시사항 시안

**역할**: F0~F4 결과를 종합하여 한글 표시사항 시안을 자동 생성합니다.

**처리 흐름**:
```
F0(원재료) + F1(수입판정) + F2(식품유형) + F4(라벨검토)
  → 1단계: 12개 항목 자동 생성
    (제품명, 식품유형, 원재료명, 내용량, 소비기한, 보관방법,
     제조사, 수입자, 알레르기, GMO, 영양성분, 원산지)
  → 2단계: AI 교차검증
    (1차 결과를 AI가 재검증, 서류와 불일치 항목 표시)
  → 시안 직접 편집 가능
  → DOCX/PDF 검토내역서 다운로드
```

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
