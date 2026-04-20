# SAMC — 수입식품 검역 AI 플랫폼

수입식품 통관 검역 업무를 자동화하는 AI 기반 풀스택 웹 애플리케이션입니다.  
서류 업로드 → OCR 파싱 → 수입 판정 → 유형 분류 → 필요서류 안내 → 표시사항 검토 → 한글 시안 제작 까지 6단계 파이프라인을 지원합니다.

> **최종 업데이트**: 2026-04-18 · **Supabase**: `bnfgbwwibnljynwgkgpt` · **브랜치**: `main`

---

## 주요 기능

| 단계 | 기능 | 담당 | 설명 |
|------|------|------|------|
| f0 | 서류 입력 + OCR | 경아 | PDF/이미지/HWP/Excel 업로드, Claude LLM 파싱, 라벨 이미지 크롭 |
| F1 | 수입 가능 판정 | 병찬 | 원재료 허용/금지 판정, 기준치 비교, Pinecone RAG + GPT 법령 판정, HITL 충돌 결정 |
| F2 | 식품유형 분류 | 아람 | GPT-4o + Pinecone RAG로 식품유형 자동 분류 |
| F3 | 필요서류 안내 | 유빈 | 5축 AND 매칭 엔진 + Pinecone 법령 시맨틱 검색 |
| F4 | 수출국 표시사항 검토 | 성은 | 라벨 텍스트/이미지 분석, 법령 위반 여부 AI 판정 |
| F5 | 한글 표시사항 시안 | 세연 | 2단계 교차검증 + Claude Sonnet SSE 스트리밍, Pinecone 법령 원문 검색, 시안 직접 편집, DOCX/PDF 검토내역서 다운로드 |

---

## 기술 스택

### 백엔드
- **프레임워크**: FastAPI 0.115 + Uvicorn
- **AI/LLM**: Anthropic Claude (f0, F5), OpenAI GPT (F1: gpt-5.4-mini, F2: gpt-4o, F3, F4)
- **벡터 DB**: Pinecone (F1: samc-law-f1, F2: samc-a, F3: samc-law-f3, F4: samc-feature4-laws, F5: f5-law-chunks)
- **임베딩**: OpenAI text-embedding-3-small (F1, F2), multilingual-e5-large (F3, F4), Voyage-3 (F5)
- **DB**: Supabase (PostgreSQL) + supabase-py SDK (전 기능 통일)
- **파일 처리**: PyMuPDF, Pillow, python-docx, openpyxl
- **내보내기**: reportlab (PDF), python-docx (DOCX), fpdf2 (F4 리포트)

### 프론트엔드
- **프레임워크**: Next.js 14 (App Router) + TypeScript
- **스타일**: Tailwind CSS
- **인증**: Supabase SSR
- **HTTP 클라이언트**: axios (JWT 자동 첨부)
- **아이콘**: lucide-react

---

## 프로젝트 구조

```
SAMC_NEW_NEW/
├── backend/
│   ├── main.py                    # FastAPI 앱 진입점, 라우터 등록
│   ├── requirements.txt
│   ├── .env.example               # 환경변수 템플릿
│   ├── routers/
│   │   ├── upload.py              # f0: 업로드/OCR/파싱/내보내기
│   │   ├── cases.py               # f0: 케이스 CRUD
│   │   ├── feature1.py            # F1: 수입판정
│   │   ├── feature2.py            # F2: 식품유형 분류
│   │   ├── feature3.py            # F3: 필요서류
│   │   ├── feature4.py            # F4: 수출국 표시사항
│   │   ├── feature5.py            # F5: 한글 시안
│   │   ├── admin_laws.py          # F4: 법령 관리 어드민
│   │   ├── admin_law_update.py    # 통합 법령 업데이트 (SSE)
│   │   └── db_manager.py          # F1: DB 직접 관리 CRUD
│   ├── services/                  # 기능별 비즈니스 로직
│   ├── schemas/                   # Pydantic 스키마
│   ├── models/                    # F1 Pydantic 모델
│   ├── db/
│   │   ├── supabase_client.py     # 공통 Supabase 클라이언트
│   │   ├── pinecone_client.py     # 공통 Pinecone 클라이언트
│   │   ├── migrations/            # SQL 마이그레이션 (001~014)
│   │   ├── seed/                  # F1 초기 데이터 (01~07)
│   │   ├── feature2/              # F2 전처리 스크립트
│   │   └── feature4/              # F4 전처리 스크립트
│   ├── constants/                 # 상수 (GMO, 조건부 원료, 기준치)
│   └── utils/                     # 공통 유틸리티
│
├── frontend/
│   ├── app/
│   │   ├── auth/login/            # 로그인 페이지
│   │   ├── dashboard/             # 케이스 목록 대시보드
│   │   ├── cases/[id]/
│   │   │   ├── upload/            # f0: 업로드+OCR
│   │   │   ├── f1/                # F1: 수입판정
│   │   │   ├── f2/                # F2: 식품유형 분류
│   │   │   ├── f3/                # F3: 필요서류
│   │   │   ├── f4/                # F4: 수출국 표시사항
│   │   │   └── f5/                # F5: 한글 시안
│   │   └── admin/
│   │       ├── laws/              # F4 법령 관리
│   │       └── law-update/        # 통합 법령 업데이트
│   ├── features/
│   │   ├── feature1/              # F1 컴포넌트/훅/API
│   │   ├── feature2/              # F2 컴포넌트
│   │   ├── feature3/              # F3 컴포넌트/lib
│   │   ├── feature4/              # F4 컴포넌트/훅/API
│   │   └── feature5/              # F5 컴포넌트
│   ├── components/
│   │   ├── ocr/                   # f0 OCR 결과 편집기
│   │   ├── upload/                # f0 업로드 UI
│   │   ├── layout/                # 공통 레이아웃 (StepNavigation, CaseSummaryPanel)
│   │   └── ui/                    # 공통 UI (Badge, Button, Card 등)
│   ├── lib/
│   │   ├── api.ts                 # 기능별 API 함수 모음
│   │   └── supabase.ts            # Supabase 인증 클라이언트
│   ├── services/
│   │   └── apiClient.ts           # axios 기반 공통 API 클라이언트
│   └── types/
│       ├── api.ts                 # 공통 응답 타입
│       ├── case.ts                # 케이스 타입
│       └── pipeline.ts            # 기능별 파이프라인 결과 타입
│
└── MERGE_GUIDE.md                 # 팀 병합 가이드
```

---

## 데이터 파이프라인

```
f0 (서류 업로드 + OCR)
├─→ F1 (수입판정)    : 원재료 목록, 공정 코드
├─→ F2 (유형분류)    : f0 + F1 결과 통합
├─→ F3 (필요서류)    : origin_country, is_oem, food_type 등
├─→ F4 (라벨검토)    : 제품명, 원재료, 라벨텍스트, 라벨이미지
└─→ F5 (한글시안)    : f0 + F1 + F2 + F4 결과 통합

F1 → F2, F4, F5     F2 → F3, F4, F5     F4 → F5
```

각 기능은 `pipeline_steps` 테이블의 `ai_result` JSON을 통해 데이터를 주고받습니다.

---

## DB 테이블 구조

| Prefix | 기능 | 주요 테이블 |
|--------|------|------------|
| (없음) | 공통 | `cases`, `documents`, `pipeline_steps`, `case_label_images` |
| `f1_` | F1 수입판정 | `f1_allowed_ingredients`, `f1_forbidden_ingredients`, `f1_additive_limits`, `f1_safety_standards`, `f1_ingredient_synonyms`, `f1_law_chunks`, `f1_escalation_logs` |
| `f2_` | F2 유형분류 | `f2_food_type_classification`, `f2_required_documents` |
| `f3_` | F3 필요서류 | `f3_required_documents`, `f3_country_groups`, `f3_keyword_synonyms` |
| `f4_` | F4 라벨검토 | `f4_law_documents`, `f4_prohibited_expressions`, `f4_image_violation_types` |

---

## API 구조

| 경로 접두사 | 대상 |
|-----------|------|
| `/api/v1/cases/{id}/...` | f0 케이스/업로드/OCR |
| `/api/v1/cases/{id}/pipeline/feature/1/...` | F1 수입판정 |
| `/api/v1/cases/{id}/pipeline/feature/2/...` | F2 유형분류 |
| `/api/v1/cases/{id}/pipeline/feature/3/...` | F3 필요서류 |
| `/api/v1/cases/{id}/pipeline/feature/4/...` | F4 라벨검토 |
| `/api/v1/cases/{id}/pipeline/feature/5/...` | F5 한글시안 |
| `/admin/laws/...` | F4 법령 관리 |
| `/admin/law-update/...` | 통합 법령 업데이트 |
| `/api/v1/admin/db/...` | F1 DB 관리 |

---

## 팀 병합 현황

| 기능 | 담당 | 상태 |
|------|------|------|
| f0 입력+OCR+로그인 | 경아 | 병합 완료 |
| F1 수입판정 | 병찬 | 병합 완료 |
| F2 유형분류 | 아람 | 병합 완료 |
| F3 필요서류 | 유빈 | 병합 완료 |
| F4 라벨검토 | 성은 | 병합 완료 |
| F5 한글시안 | 세연 | 병합 완료 |

> 자세한 병합 규칙 및 파일 소유권은 [MERGE_GUIDE.md](MERGE_GUIDE.md)를 참고하세요.
