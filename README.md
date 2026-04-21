# SAMC — 수입식품 검역 AI 플랫폼

수입식품 통관 검역 업무를 자동화하는 AI 파이프라인 시스템입니다.
서류 OCR 파싱부터 수입 가능 판정, 필요서류 안내, 라벨 검토, 한글 시안 생성까지 6단계 워크플로우를 제공합니다.

---

## 파이프라인 구조

| 단계 | 명칭 | 기능 |
|------|------|------|
| F0 | 입력 / OCR | 서류 업로드, 이미지 OCR 파싱, 라벨 이미지 크롭 |
| F1 | 수입 가능 판정 | 금지원료 확인 → 원재료 매칭 → 기준규격 확인 → 법령 인용 |
| F2 | 식품유형 분류 | 제품 식품유형 자동 분류 |
| F3 | 필요서류 안내 | 국가·제품 유형별 필요 서류 목록 제공 |
| F4 | 수출국 표시사항 검토 | 외국어 라벨 법령 위반 항목 탐지 |
| F5 | 한글표시사항 시안 | 한글 라벨 초안 자동 생성 |

---

## 기술 스택

### Backend
- **Python 3.12** (3.14 불가 — voyageai 패키지 미지원)
- FastAPI 0.115.6 + Uvicorn 0.34.0
- Supabase (PostgreSQL + Storage)
- Pinecone ≥ 8.0.0 (벡터 검색)
- OpenAI API (GPT-4o) / Anthropic API (Claude) / Voyage AI
- sentence-transformers (multilingual-e5-large, F4 전용)
- DeepL API (F4 번역)

### Frontend
- Next.js 14 + React 18 + TypeScript
- Tailwind CSS
- @supabase/supabase-js 2.x

---

## 디렉터리 구조

```
SAMC_NEW_NEW/
├── backend/
│   ├── main.py                  # FastAPI 진입점
│   ├── requirements.txt
│   ├── .env                     # 환경변수 (gitignore 됨)
│   ├── routers/
│   │   ├── upload.py            # F0 파일 업로드
│   │   ├── cases.py             # 케이스 CRUD
│   │   ├── feature1.py          # F1 수입 가능 판정
│   │   ├── feature2.py          # F2 식품유형 분류
│   │   ├── feature3.py          # F3 필요서류 안내
│   │   ├── feature3_admin.py    # F3 어드민
│   │   ├── feature4.py          # F4 라벨 검토
│   │   ├── feature5.py          # F5 한글 시안
│   │   ├── admin_laws.py        # F4 법령 관리
│   │   └── admin_law_update.py  # 법령 업데이트
│   ├── services/
│   │   ├── parsing_service.py   # F0 OCR 파싱
│   │   ├── feature1.py          # F1 비즈니스 로직
│   │   ├── f1_step_a~d.py       # F1 4단계 로직
│   │   ├── f3_required_docs.py  # F3 서류 판단
│   │   ├── f5_rag.py            # F5 RAG 검색
│   │   ├── law_api_client.py    # 국가법령정보센터 API
│   │   └── data_go_kr/          # 공공데이터 API
│   ├── db/
│   │   ├── migrations/          # 001~021 순차 마이그레이션
│   │   ├── seed/                # F1 원재료 시드 데이터
│   │   └── feature4/            # F4 전처리 스크립트·SQL
│   ├── scripts/
│   │   ├── f4_sync_laws.py      # F4 법령 자동 동기화
│   │   ├── f5_embed_laws.py     # F5 법령 임베딩
│   │   └── f1_sync_laws.py      # F1 법령 동기화
│   └── tests/                   # pytest 테스트 + 골든셋
├── frontend/
│   ├── app/
│   │   ├── dashboard/page.tsx   # 메인 대시보드
│   │   ├── auth/login/page.tsx  # 로그인
│   │   └── cases/page.tsx       # 케이스 목록
│   ├── features/
│   │   ├── feature1/            # F1 UI
│   │   ├── feature2/            # F2 UI
│   │   ├── feature3/            # F3 UI + 어드민
│   │   ├── feature4/            # F4 UI
│   │   └── feature5/            # F5 UI
│   ├── components/
│   │   ├── layout/              # CaseSummaryPanel, StepNavigation
│   │   ├── ui/                  # Button, Badge, Card, Input 등
│   │   ├── ocr/                 # OCR 결과 표시 컴포넌트
│   │   └── upload/              # 파일 드롭존
│   └── lib/
│       ├── api.ts               # 백엔드 API 클라이언트
│       └── supabase.ts          # Supabase 클라이언트
├── .env.example                 # 환경변수 템플릿
├── run.md                       # 실행 가이드 (상세)
└── 법령_API_전환_가이드.md      # F4 법령 API 전환 문서
```

---

## 환경변수 설정

`backend/.env` 파일을 아래 항목에 맞게 작성합니다. (`.env.example` 참고)

```env
# 공통 (전 기능)
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>

# F0 — OCR/파싱
F0_OPENAI_API_KEY=sk-...
F0_OPENAI_MODEL=gpt-4o

# F1 — 수입판정
F1_ANTHROPIC_API_KEY=sk-ant-...

# F2 — 식품유형
F2_OPENAI_API_KEY=sk-...
F2_PINECONE_API_KEY=pcsk_...
F2_PINECONE_INDEX=samc-a

# F3 — 필요서류
F3_OPENAI_API_KEY=sk-...
F3_PINECONE_API_KEY=pcsk_...
F3_PINECONE_INDEX_NAME=samc-law-f3

# F4 — 라벨검토
F4_OPENAI_API_KEY=sk-...
F4_PINECONE_API_KEY=pcsk_...
F4_PINECONE_HOST=https://samc-feature4-laws-xxxxx.pinecone.io
F4_DEEPL_API_KEY=<deepl-key>:fx
LAW_API_OC=Ipcr0618

# F5 — 한글시안
F5_ANTHROPIC_API_KEY=sk-ant-...
F5_PINECONE_API_KEY=pcsk_...
F5_PINECONE_INDEX=f5-law-chunks
F5_VOYAGE_API_KEY=pa-...
```

`frontend/.env.local`:
```env
NEXT_PUBLIC_SUPABASE_URL=https://<project>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon-key>
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 실행 방법

### Backend

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

> API 문서: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

> 앱: http://localhost:3000

---

## 데이터베이스 마이그레이션

Supabase SQL Editor에서 순서대로 실행합니다.

```
backend/db/migrations/001_pg_trgm_extension.sql
backend/db/migrations/002_f1_allowed_ingredients.sql
... (003 ~ 021 순서대로)
backend/db/feature4/migrate_f4_law_api.sql
backend/db/migrate_label_images_v4.sql
```

### F4 법령 초기 동기화

```bash
# 초기 전체 적재
python -m backend.scripts.f4_sync_laws --force

# 변경분만 업데이트 (이후 cron 등록 가능)
python -m backend.scripts.f4_sync_laws
```

---

## 주요 기능 상세

### F1 수입 가능 판정 (4단계)

| 단계 | 파일 | 역할 |
|------|------|------|
| Step A | `services/f1_step_a.py` | 금지원료 DB 조회 |
| Step B | `services/f1_step_b.py` | 원재료명 매칭 + 함량 |
| Step C | `services/f1_step_c.py` | 식품 기준규격 확인 |
| Step D | `services/f1_step_d.py` | 법령 인용 생성 |

### F4 법령 자동 동기화

국가법령정보센터 Open API를 통해 법령 개정 시 자동 감지·업데이트합니다.
- 법령(eflaw): 조/항/호/목 분리 구조
- 고시(admrul): 조문 통째 제공
- 상세: `법령_API_전환_가이드.md`

---

## 테스트

```bash
cd backend
pytest tests/ -v

# F1 골든셋 테스트
python -m backend.scripts.f1_run_goldenset_v3
```

---

## 주의사항

- **Python 3.12 필수** — 3.14는 `voyageai` 미지원 (`Requires-Python: >=3.9, <3.14`)
- **pinecone >= 8.0.0** — 구버전 `pinecone-client` 패키지 제거 필요
- `.env` 변경 후 반드시 uvicorn 서버 재시작 필요 (`--reload`는 .env 변경 미반영)
- Pinecone 인덱스는 기능별로 분리 유지 (임베딩 모델·차원 상이)

---

## 팀 구성

| 담당 | 기능 |
|------|------|
| F0/F1 | 입력·OCR, 수입판정 |
| F2 | 식품유형 분류 |
| F3 | 필요서류 안내 |
| F4 | 수출국 라벨검토 |
| F5 | 한글표시사항 시안 |
