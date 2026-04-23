# SAMC — 수입식품 검역 AI 플랫폼

> **수입식품 통관의 복잡한 법규 검토를 AI가 수분 만에 자동화합니다**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-black?logo=next.js)](https://nextjs.org)
[![OpenAI](https://img.shields.io/badge/GPT--4o-Vision-412991?logo=openai)](https://openai.com)
[![Pinecone](https://img.shields.io/badge/Pinecone-RAG-00B4FF)](https://pinecone.io)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?logo=supabase)](https://supabase.com)
[![Deploy](https://img.shields.io/badge/배포-Railway%20%2B%20Vercel-blueviolet)](https://railway.app)

---

## 해결하는 문제

### 수입식품 검역 담당자가 겪는 현실

한국으로 수입되는 식품은 **식품공전, 식품첨가물공전, 건강기능식품 법령, 식품표시법** 4개 공전에 걸쳐 수백 개의 규정을 통과해야 합니다. 하나의 제품을 검역하려면:

| 작업 | 기존 방식 | 소요 시간 |
|------|-----------|-----------|
| 원재료 성분코드 매칭 | 식약처 DB 수동 검색 | 1~3시간 |
| 수입 가능 여부 판정 | 법령 직접 검토 | 반나절~1일 |
| 식품유형 분류 | 식품공전 열람 | 1~2시간 |
| 필요서류 확인 | 규정집 참조 | 30분~1시간 |
| 라벨 법규 검토 | 조항별 수동 대조 | 1~2시간 |
| 한글 표시사항 작성 | 직접 작성 | 1~2시간 |

> 숙련 검역사도 제품 1건에 **평균 1~2일**이 소요됩니다.
> 연간 수입 건수가 증가하는 상황에서, 인력 확충만으로는 한계에 도달했습니다.

### SAMC의 답

서류를 업로드하면 **6단계 AI 파이프라인**이 자동으로 실행됩니다. 전 과정이 **수분 이내**에 완료되며, 각 단계를 사람이 검토·수정할 수 있습니다.

---

## 서비스 한눈에 보기

```
📄 서류 업로드 (F0)         — PDF / 이미지 / HWP / Excel
      ↓  GPT-4o Vision OCR + 성분코드 자동 매칭
⚖️  수입 가능 여부 판정 (F1)  — 금지원료·첨가물 기준치·법령 RAG
      ↓
🍱  식품유형 분류 (F2)       — 식품공전 10단계 분류 + 할루시네이션 보정
      ↓
📋  필요서류 안내 (F3)       — 5축 AND 매칭 + 법령 시맨틱 검색
      ↓
🏷️  라벨 검토 (F4)           — 텍스트·이미지 교차검증 + 위반 등급 분류
      ↓
📝  한글 표시사항 시안 (F5)  — 12개 항목 자동 생성 + 2단계 AI 교차검증
```

각 단계 결과를 **직접 수정**할 수 있으며, 수정하면 **이후 단계가 자동으로 재실행**됩니다.

---

## 기술 구현 — AI 파이프라인 상세

### F0 — 서류 업로드 + OCR 파싱

**처리 흐름**
```
서류 업로드 (PDF/이미지/HWP/Excel)
  → GPT-4o Vision OCR
    → LLM 구조화 파싱 (원재료·배합비율·제조공정 추출)
      → 성분코드 자동 매칭 (12,263건 DB)
```

**성분코드 매칭 — 3단계 폴백 전략**
```
1. Supabase f0_ingredient_codes (12,263건) 정확 매칭
2. 한글명 실패 → 영문명으로 재시도
3. 영문명도 실패 → LLM에게 식약처 공식 성분명 추천 요청
   예) "이산화황" → LLM → "무수아황산" → DB 매칭 성공
4. 매칭 후보 목록을 드롭다운으로 사용자에게 제시
```

**출력**: 제품명, 수출국, 원재료 목록(성분코드 포함), 배합비율, 제조공정

---

### F1 — 수입 가능 여부 판정

**처리 흐름 — 4단계 순차 필터**
```
Step A: 금지원료 체크
  → 금지원료 발견 시 즉시 "수입불가" 확정
  ↓ (통과)
Step B: 원재료 허용 여부
  → 성분코드 접두어 기반 판정
    A: 식품원료 → 허용
    B: 식품첨가물 → 허용 + 경고
    C: 건강기능식품 성분 → 조건부
  ↓
Step C: 기준규격 수치 비교 (첨가물공전 DB — 893건)
  → 기준 초과 시 즉시 "수입불가"
  ↓
Step D: 관련 법령 RAG 검색
  → f1_law_chunks (2,148건) 키워드 검색
  → LLM 종합 판정 (법령 원문 + 배합비율 → 최종 판정)
```

**판정 우선순위 & Confidence**
| 순위 | 조건 | 판정 | Confidence |
|------|------|------|-----------|
| 1 | 기준규격 초과 | 수입불가 | 0.90 |
| 2 | 미확인 원재료 존재 | 수입불가 | 0.60 |
| 3 | 조건부 원재료 | 조건부 가능 | 0.75 |
| 4 | 모두 통과 | LLM 판정 결과 적용 | — |

---

### F2 — 식품유형 분류

**식약처 10단계 분류 원칙 반영**
```
① 자연산물 → ② 타법령(주류·축산물) → ③ 특수용도식품
→ ④ 단순가공 → ⑤ 기본원료(전분/당/유지)
→ ⑥ 용도별(간편식/간식/음료/조미/반찬)
→ ⑦ 특정원료 → ⑧ 특정제조방법 → ⑨ 주원료별 → ⑩ 기타가공품
```

**5단계 처리 파이프라인**
```
1단계: 원재료 카테고리 태깅 (LLM + 결과 캐시)
2단계: 코드 기반 대분류 확정 (제품명 키워드 + 원재료 비율)
3단계: LLM 소분류 결정 (DB에 있는 type_name 중에서만 선택)
4단계: 코드 보정 — 할루시네이션 방지
  예) 과일+채소 비율 10%↑인데 "기타음료" 선택 → "과·채음료" 강제 보정
5단계: 후보 3개 제시 (1순위 AI 추천 + 2·3순위 대안, 사용자 변경 가능)
```

---

### F3 — 수입 필요서류 안내

**5축 AND 매칭 엔진**
```
축1: 식품유형 (예: 과·채음료)
축2: 수출국 (예: 베트남)
축3: OEM 여부
축4: 제조공정 특성
축5: 특별 조건 (유기인증, 최초수입 등)
  → 매칭 서류 목록 (제출 서류 + 보관 서류)
  → Pinecone 법령 시맨틱 검색으로 법적 근거 보강
```

---

### F4 — 수출국 표시사항 검토

**3축 교차검증 구조**
```
텍스트 분석: 의무 표시사항 누락·부당 표시·광고 검출
이미지 분석: 인증마크·건강 관련 표현·경고 문구 (GPT-4o Vision)
교차검증:   라벨 내용 ↔ 원재료 서류 불일치 검출
  → Pinecone RAG로 관련 법령 원문 첨부
```

**위반 등급**
- `must_fix` — 반드시 수정해야 통관 가능
- `review_needed` — 검토 후 판단 필요

---

### F5 — 한글 표시사항 시안 자동 생성

**2단계 AI 검증 구조**
```
F0(원재료) + F1(수입판정) + F2(식품유형) + F4(라벨검토)
  → 1단계: 12개 항목 자동 생성
      제품명 / 식품유형 / 원재료명 / 내용량 / 소비기한
      보관방법 / 제조사 / 수입자 / 알레르기 / GMO / 영양성분 / 원산지
  → 2단계: AI 교차검증 (1차 결과를 AI가 재검증, 서류 불일치 항목 표시)
  → 시안 직접 편집 + DOCX/PDF 검토내역서 다운로드
```

RAG: Pinecone `f5-law-chunks` + **Voyage-3** 임베딩 (다국어 법령에 최적화)

---

## 기술 스택

### AI / 데이터

| 기술 | 역할 |
|------|------|
| **GPT-4o / GPT-4o Vision** | OCR 파싱, 법령 판정, 분류, 시안 생성 |
| **Pinecone (5개 인덱스)** | F1~F5 법령·유형 시맨틱 검색 |
| **Voyage-3** | F5 법령 임베딩 (다국어 최적화) |
| **multilingual-e5-large** | F3·F4 법령 임베딩 |
| **text-embedding-3-small** | F1·F2 법령 임베딩 |

### Pinecone 인덱스 구성

| 인덱스 | 기능 | 임베딩 모델 | 청크 수 |
|--------|------|-------------|---------|
| `samc-law-f1` | 수입 판정 법령 검색 | text-embedding-3-small | 2,148건 |
| `samc-a` | 식품유형 분류 RAG | text-embedding-3-small | — |
| `samc-law-f3` | 필요서류 법령 검색 | multilingual-e5-large | — |
| `samc-feature4-laws` | 표시 법규 검색 | multilingual-e5-large | — |
| `f5-law-chunks` | 한글 표시 법규 검색 | Voyage-3 | — |

### 백엔드 / 인프라

| 기술 | 역할 |
|------|------|
| **FastAPI** | REST API 서버 |
| **Supabase (PostgreSQL)** | 케이스·파이프라인 결과·원재료 코드·법령 데이터 |
| **Railway** | 백엔드 배포 |
| **Vercel** | 프론트엔드 배포 |

### 프론트엔드

| 기술 | 역할 |
|------|------|
| **Next.js 14 (App Router)** | React 프레임워크 |
| **TypeScript** | 타입 안전성 |
| **Tailwind CSS** | 스타일링 |

---

## 데이터베이스 — 법령 및 기준 데이터

### Supabase 주요 테이블

| 테이블 | 데이터 규모 | 설명 |
|--------|------------|------|
| `f0_ingredient_codes` | **12,263건** | 식약처 성분코드 DB (코드·한글명·영문명·카테고리) |
| `f1_forbidden_ingredients` | ~200건 | 금지원료 DB |
| `f1_additive_limits` | **893건** | 첨가물 사용기준 DB (기준치 수치 포함) |
| `f1_law_chunks` | **2,148건** | 법령 텍스트 청크 (4개 공전 + 기능성표시 규정) |
| `f2_food_type_classification` | 235건 | 식품유형 정의 (대·중·소분류 + 근거법령) |
| `f3_required_documents` | ~70건 | 수입 필요서류 매칭 규칙 |
| `cases` | — | 검역 케이스 (제품 1건 = 1 케이스) |
| `pipeline_steps` | — | F0~F5 단계별 실행 결과 (ai_result / final_result) |

---

## 경쟁 우위 및 차별성

| 항목 | 기존 방식 | SAMC |
|------|-----------|------|
| **처리 시간** | 1~2일 | 수분 이내 |
| **성분코드 매칭** | 수동 검색 | LLM 폴백 3단계 자동 매칭 |
| **법령 판정 근거** | 담당자 기억·참조 | 법령 원문 RAG 자동 인용 |
| **식품유형 분류** | 식품공전 직접 열람 | 10단계 원칙 + 할루시네이션 보정 |
| **라벨 검토** | 조항별 수동 대조 | 텍스트·이미지 3축 교차검증 |
| **결과물** | 수작업 문서 | DOCX/PDF 자동 생성 |
| **수정 시** | 처음부터 재검토 | 해당 단계부터 자동 재실행 |

### 향후 확장 가능성

- **다국가 확장**: 법령 DB 교체만으로 EU·미국·일본 기준 적용 가능
- **API 서비스화**: 관세사·수입업체 대상 B2B SaaS 전환
- **자동 신고서 생성**: 식약처 통관 신고서 초안 자동 완성
- **실시간 법령 업데이트**: 식약처 법령 RSS 연동으로 DB 자동 갱신

---

## 프로젝트 구조

```
SAMC_NEW_NEW/
├── backend/
│   ├── main.py                    # FastAPI 진입점
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
│   │   ├── f1_step_b.py           # Step B: 원재료 허용 매칭
│   │   ├── f1_step_c.py           # Step C: 기준규격 수치 비교
│   │   ├── f1_step_d.py           # Step D: 법령 RAG 인용
│   │   ├── f2_food_class.py       # F2: 원재료 카테고리 태깅
│   │   ├── f3_required_docs.py    # F3: 5축 AND 매칭 엔진
│   │   ├── step6_label.py         # F5: 한글 시안 생성
│   │   ├── f5_rag.py              # F5: 법령 RAG (Voyage-3)
│   │   └── export_service.py      # DOCX/PDF 생성
│   ├── models/                    # Pydantic 스키마
│   ├── db/                        # 마이그레이션·시드 데이터
│   └── scripts/                   # 법령 DB 동기화 스크립트
│
├── frontend/
│   ├── app/
│   │   ├── dashboard/             # 케이스 목록 대시보드
│   │   └── cases/[id]/
│   │       ├── upload/page.tsx    # F0: 서류 업로드 + OCR 결과
│   │       ├── f1/page.tsx        # F1: 수입 판정 결과
│   │       ├── f2/page.tsx        # F2: 식품유형 분류
│   │       ├── f3/page.tsx        # F3: 필요서류 목록
│   │       ├── f4/page.tsx        # F4: 라벨 검토 결과
│   │       └── f5/page.tsx        # F5: 한글 표시사항 시안
│   ├── features/                  # F1~F5 단계별 컴포넌트
│   └── components/
│       ├── ocr/                   # OCR 결과 편집기
│       ├── upload/                # 파일 업로드
│       └── layout/                # StepNavigation 등
│
└── docs/                          # 설계 문서
```

---

## 실행 방법

### 1. 환경변수 설정

```bash
cp .env.example backend/.env
# 각 항목에 API 키 입력
```

### 2. 백엔드

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 3. 프론트엔드

```bash
cd frontend
npm install
npm run dev
# http://localhost:3000
```

---

## 환경변수

### 백엔드 (`backend/.env`)

```env
# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=xxx
SUPABASE_ANON_KEY=xxx

# F0 (OCR)
F0_OPENAI_API_KEY=xxx
F0_OPENAI_MODEL=gpt-4o

# F1 (수입 판정)
F1_OPENAI_API_KEY=xxx
F1_PINECONE_API_KEY=xxx
F1_PINECONE_INDEX=samc-law-f1

# F2 (식품유형 분류)
F2_OPENAI_API_KEY=xxx
F2_PINECONE_API_KEY=xxx
F2_PINECONE_INDEX=samc-a

# F3 (필요서류)
F3_OPENAI_API_KEY=xxx
F3_PINECONE_API_KEY=xxx
F3_PINECONE_INDEX_NAME=samc-law-f3

# F4 (라벨 검토)
F4_OPENAI_API_KEY=xxx
F4_PINECONE_API_KEY=xxx
F4_DEEPL_API_KEY=xxx

# F5 (한글 시안)
F5_OPENAI_API_KEY=xxx
F5_PINECONE_API_KEY=xxx
F5_VOYAGE_API_KEY=xxx
F5_PINECONE_INDEX=f5-law-chunks
```

### 프론트엔드 (`frontend/.env.local`)

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=xxx
```

---

## 사용자 워크플로우

1. **대시보드** — 새 검역 건 생성
2. **서류 업로드** — 원재료배합비율표·제조공정도·라벨 이미지 업로드
3. **OCR 분석** — AI가 서류를 파싱하고 원재료·성분코드를 식별
4. **검역 분석 시작** — F1~F5가 순차 자동 실행
5. **결과 확인 및 수정** — 각 단계별 결과를 검토하고 필요 시 수정
6. **자동 재실행** — 수정 확정 시 이후 단계 자동 재실행
7. **문서 다운로드** — DOCX/PDF 검토내역서 다운로드

---

> 최종 업데이트: 2026-04-23 | 비공개 프로젝트
