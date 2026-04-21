# SAMC 실행 가이드

> 최초 셋업부터 로컬 실행까지 순서대로 따라하면 됩니다.

---

## 사전 요구사항

| 항목 | 버전 | 비고 |
|------|------|------|
| Python | **3.12.x** | 3.14 불가 — `voyageai` 미지원 |
| Node.js | 18 이상 | |
| npm | 9 이상 | |
| Git | 최신 | |

---

## 1. 환경변수 설정

### 1-1. 백엔드

`backend/.env` 파일을 생성합니다. (`.env.example` 참고)

```env
# ── 공통 (전 기능) ──
SUPABASE_URL=https://<project-id>.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>

# ── F0 (OCR / 파싱) ──
F0_OPENAI_API_KEY=sk-...
F0_OPENAI_MODEL=gpt-4o

# ── F1 (수입 가능 판정) ──
F1_OPENAI_API_KEY=sk-...
F1_OPENAI_CHAT_MODEL=gpt-4o-mini
F1_OPENAI_EMBED_MODEL=text-embedding-3-small
F1_PINECONE_API_KEY=pcsk_...
F1_PINECONE_INDEX=samc-law-f1
F1_RAG_TOP_K=5

# ── F2 (식품유형 분류) ──
F2_OPENAI_API_KEY=sk-...
F2_PINECONE_API_KEY=pcsk_...
F2_PINECONE_INDEX=samc-a

# ── F3 (필요서류 안내) ──
F3_OPENAI_API_KEY=sk-...
F3_PINECONE_API_KEY=pcsk_...
F3_PINECONE_INDEX_NAME=samc-law-f3

# ── F4 (수출국 라벨 검토) ──
F4_OPENAI_API_KEY=sk-...
F4_PINECONE_API_KEY=pcsk_...
F4_PINECONE_HOST=https://samc-feature4-laws-xxxxx.pinecone.io   # 필수
F4_DEEPL_API_KEY=<key>:fx
LAW_API_OC=Ipcr0618

# ── F5 (한글표시사항 시안) ──
F5_ANTHROPIC_API_KEY=sk-ant-...
F5_PINECONE_API_KEY=pcsk_...
F5_PINECONE_INDEX=f5-law-chunks
F5_VOYAGE_API_KEY=pa-...
```

> `.env` 수정 후에는 반드시 uvicorn 서버를 재시작해야 반영됩니다 (`--reload`는 .env 변경을 감지하지 않습니다).

### 1-2. 프론트엔드

`frontend/.env.local` 파일을 생성합니다.

```env
NEXT_PUBLIC_SUPABASE_URL=https://<project-id>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon-key>
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 2. 데이터베이스 초기화 (Supabase)

Supabase 대시보드 → **SQL Editor** 에서 아래 파일을 순서대로 실행합니다.

### 2-1. 공통 스키마

```
backend/db/combined_schema.sql
```

### 2-2. 마이그레이션 (001 → 021 순서)

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
backend/db/migrations/010_f0_process_codes.sql
backend/db/migrations/010_f1_law_chunks.sql
backend/db/migrations/011_f0_ingredient_codes.sql
backend/db/migrations/011_f1_forbidden_seed_backfill.sql
backend/db/migrations/012_f1_additive_limits_backfill.sql
backend/db/migrations/013_f1_safety_standards_backfill.sql
backend/db/migrations/014_pipeline_steps_needs_review.sql
backend/db/migrations/015_f3_update_history.sql
backend/db/migrations/016_f1_data_go_kr_infra.sql
backend/db/migrations/017_pipeline_steps_status_expansion.sql
backend/db/migrations/018_f1_audit_log.sql
backend/db/migrations/019_f1_safetydata_snapshot.sql
backend/db/migrations/019_f3_update_history_status.sql
backend/db/migrations/020_f1_law_cache.sql
backend/db/migrations/021_f1_forbidden_aliases_patch.sql
```

### 2-3. F4 전용 마이그레이션

```
backend/db/feature4/schema.sql
backend/db/feature4/migrate_f4_law_api.sql
backend/db/feature4/migrate_f4_results_unique.sql
backend/db/migrate_label_images_v4.sql
```

### 2-4. 시드 데이터 (F1 원재료 DB)

```
backend/db/seed/01_f1_ingredients_permitted.sql
backend/db/seed/02_f1_ingredients_restricted.sql
backend/db/seed/03_f1_ingredients_prohibited.sql
backend/db/seed/04_f1_forbidden_ingredients.sql
backend/db/seed/05_f1_thresholds_core.sql
backend/db/seed/06_f1_additive_limits_expanded.sql
backend/db/seed/07_f1_safety_standards_expanded.sql
backend/db/seed/08_f1_ingredient_synonyms_seed.sql
```

---

## 3. 백엔드 실행

```bash
cd backend

# 가상환경 생성 (최초 1회)
python -m venv .venv

# 가상환경 활성화
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# 서버 실행
uvicorn main:app --reload --port 8000
```

실행 후 확인:
- API 문서: http://localhost:8000/docs
- 헬스체크: http://localhost:8000/health

---

## 4. 프론트엔드 실행

```bash
cd frontend

# 의존성 설치 (최초 1회)
npm install

# 개발 서버 실행
npm run dev
```

실행 후 확인:
- 앱: http://localhost:3000

> `npm run dev` 실행 시 디자인 토큰 CSS가 자동 생성됩니다 (`predev` 스크립트).

---

## 5. F4 법령 초기 동기화

F4(수출국 라벨 검토) 기능은 국가법령정보센터 API에서 법령 데이터를 가져옵니다.
DB와 Pinecone 인덱스가 비어있으면 검색 결과가 나오지 않으므로 최초 1회 실행합니다.

```bash
# 전체 강제 재적재 (최초 셋업 또는 인덱스 초기화 후)
python -m backend.scripts.f4_sync_laws --force

# 변경분만 업데이트 (이후 주기적 실행 또는 cron 등록)
python -m backend.scripts.f4_sync_laws
```

---

## 6. 화면 구조

```
/                     → 랜딩 (로그인으로 리다이렉트)
/auth/login           → 로그인
/dashboard            → 대시보드 (검역 건 목록 + 새 건 등록)
/cases/[id]/upload    → F0 서류 업로드
/cases/[id]/f1        → F1 수입 가능 판정
/cases/[id]/f2        → F2 식품유형 분류
/cases/[id]/f3        → F3 필요서류 안내
/cases/[id]/f4        → F4 수출국 라벨 검토
/cases/[id]/f5        → F5 한글표시사항 시안
/admin/laws           → 법령 관리 (어드민)
```

---

## 7. 트러블슈팅

### Python 버전 오류 (`voyageai` 설치 실패)
```
ERROR: Package 'voyageai' requires a different Python: 3.14.x not in '>=3.9, <3.14'
```
→ Python 3.12.x 로 다운그레이드 후 재시도

### Pinecone 패키지 오류
```
ModuleNotFoundError: No module named 'pinecone.client'
```
→ 구버전 제거 후 재설치
```bash
pip uninstall pinecone-client pinecone
pip install "pinecone>=8.0.0"
```

### F4 500 오류 (`_get_clients` 실패)
```
RuntimeError: .env 누락: ['F4_PINECONE_API_KEY', 'F4_PINECONE_HOST']
```
→ `backend/.env`에 `F4_PINECONE_API_KEY`와 `F4_PINECONE_HOST` 추가 후 서버 재시작

### F0 "OPENAI_API_KEY가 설정되지 않았습니다"
→ `backend/.env`에 `F0_OPENAI_API_KEY=sk-...` 추가 후 서버 재시작
(`.env` 변경은 `--reload`로 반영되지 않음 — 반드시 서버 재시작 필요)

### F1 RAG 검색 결과 없음
→ F1 Pinecone 인덱스가 비어있는 경우
```bash
python -m backend.scripts.f1_sync_laws
```

### F5 임베딩 오류
→ F5 Pinecone 인덱스 초기화 필요
```bash
python -m backend.scripts.f5_embed_laws
```

### `.env` 변경 후 반영 안 됨
→ uvicorn `--reload`는 Python 파일 변경만 감지합니다. `.env` 수정 시 서버를 직접 재시작하세요.
```bash
# Ctrl+C로 서버 종료 후
uvicorn main:app --reload --port 8000
```
