# SAMC 실행 가이드

---

## 사전 요구사항

- Python 3.11+
- Node.js 18+
- Supabase 프로젝트 (팀 공용 계정)
- 각 기능별 API 키 (아래 환경변수 섹션 참고)

---

## 1. 환경변수 설정

### 백엔드 (`backend/.env`)

```bash
cp backend/.env.example backend/.env
```

`.env` 파일을 열어 아래 키를 채웁니다.

```env
# ── 공통: Supabase (전 기능 동일 값) ──
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SERVICE_KEY=<service_role_key>

# ── F0 (입력 + OCR + 라벨처리) ──
F0_OPENAI_API_KEY=
F0_OPENAI_MODEL=gpt-4o
F0_ANTHROPIC_API_KEY=
F0_PINECONE_API_KEY=
F0_PINECONE_INDEX=samc-law-index
F0_PARSER_SERVICE_URL=http://localhost:3001
F0_PARSER_SERVICE_TOKEN=

# ── F1 (수입 가능 판정) ──
F1_DATABASE_URL=postgresql://postgres:<비밀번호>@db.<ref>.supabase.co:5432/postgres
F1_ANTHROPIC_API_KEY=

# ── F2 (식품유형 분류) ──
F2_OPENAI_API_KEY=
F2_PINECONE_API_KEY=
F2_PINECONE_INDEX=samc-a

# ── F3 (수입 필요서류 안내) ──
F3_PINECONE_API_KEY=
F3_PINECONE_INDEX_NAME=samc-law-f3
F3_OPENAI_API_KEY=

# ── F4 (수출국 표시사항 검토) ──
F4_OPENAI_API_KEY=
F4_PINECONE_API_KEY=
F4_PINECONE_HOST=https://samc-feature4-laws-xxxxx.pinecone.io
F4_DEEPL_API_KEY=

# ── F5 (한글표시사항 시안) ──
F5_ANTHROPIC_API_KEY=
F5_PINECONE_API_KEY=
F5_PINECONE_INDEX=f5-law-chunks
F5_VOYAGE_API_KEY=
```

### 프론트엔드 (`frontend/.env.local`)

```bash
cp frontend/.env.local.example frontend/.env.local   # 예시 파일이 있는 경우
```

또는 직접 생성:

```env
NEXT_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon_key>
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

---

## 2. DB 마이그레이션 (최초 1회)

Supabase SQL Editor에서 아래 파일을 **순서대로** 실행합니다.

### F1 테이블 생성

```
backend/db/migrations/001_pg_trgm_extension.sql
backend/db/migrations/002_f1_allowed_ingredients.sql
backend/db/migrations/003_f1_additive_limits.sql
backend/db/migrations/004_f1_safety_standards.sql
backend/db/migrations/005_f1_ingredient_synonyms.sql
backend/db/migrations/006_f1_forbidden_ingredients.sql
backend/db/migrations/007_f1_escalation_logs.sql
backend/db/migrations/008_f1_trgm_indexes_rpc.sql
backend/db/migrations/009_f1_rls_policies.sql
```

### F1 시드 데이터 (마이그레이션 후)

```
backend/db/seed/01_f1_ingredients_permitted.sql
backend/db/seed/02_f1_ingredients_restricted.sql
backend/db/seed/03_f1_ingredients_prohibited.sql
backend/db/seed/04_f1_forbidden_ingredients.sql
backend/db/seed/05_f1_thresholds_core.sql
```

또는 일괄 적용 스크립트:

```bash
cd backend
python -m scripts.bootstrap_f1_db
```

---

## 3. 백엔드 실행

```bash
cd backend

# 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 서버 실행
uvicorn main:app --reload --port 8000
```

서버가 정상 기동되면:
- API 문서: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 4. 프론트엔드 실행

```bash
cd frontend

# 의존성 설치
npm install

# 개발 서버 실행
npm run dev
```

브라우저에서 http://localhost:3000 접속

---

## 5. 병합 후 클린 빌드

기능 병합 후 TypeScript 에러가 발생하면 `.next` 캐시를 삭제하고 재빌드합니다.

```bash
cd frontend
rm -rf .next
npm run build
```

---

## 6. 주요 Pinecone 인덱스

| 인덱스명 | 차원 | 임베딩 | 사용 기능 |
|----------|------|--------|-----------|
| `samc-a` | 1536 | OpenAI text-embedding-3-small | F2 식품유형 분류 |
| `samc-law-f3` | 1024 | multilingual-e5-large (Pinecone inference) | F3 필요서류 |
| `samc-feature4-laws` | 1024 | multilingual-e5-large | F4 법령 검색 |
| `f5-law-chunks` | 1024 | Voyage-3 | F5 한글 시안 |

---

## 7. 법령 DB 업데이트

대시보드 → 검역관리 → 법령 DB 관리 → `/admin/law-update`

또는 API 직접 호출:

```bash
# 업데이트 가능 법령 목록 조회
GET http://localhost:8000/admin/law-update/laws

# 법령 PDF 업로드 (SSE 스트리밍 진행도)
POST http://localhost:8000/admin/law-update/upload
```

---

## 8. 트러블슈팅

### Windows UnicodeEncodeError

Python `print()`에 한글이 포함되면 서버가 시작되지 않습니다.

```python
# 잘못된 예
print("[lifespan] F1_DATABASE_URL missing — F1 DB 기능 비활성화")

# 올바른 예
print("[lifespan] F1_DATABASE_URL missing - F1 DB disabled")
```

### F1 DB 연결 실패

`F1_DATABASE_URL`이 팀 공용 Supabase 프로젝트를 가리키는지 확인합니다.  
별도 Supabase 프로젝트 URL이 설정되어 있으면 f0 데이터를 읽지 못합니다.

### CORS 오류

`backend/main.py`의 `allow_origins`에 프론트 URL이 포함되어 있는지 확인합니다.

### 포트 충돌

| 서비스 | 기본 포트 |
|--------|---------|
| FastAPI 백엔드 | 8000 |
| Next.js 프론트엔드 | 3000 |
| F0 Parser 서비스 | 3001 |
