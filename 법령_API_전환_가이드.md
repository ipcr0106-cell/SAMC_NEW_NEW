## 1차 팀원 브랜치 병합 로그
# SAMC 병합 개발 로그

## 병합 순서
F0(경아) → F4(성은) → F1(병찬) → F2(아람) → F3(유빈) → F5(세연)

---

## 1차: F0 + F4 병합 (기반 구축)

### 진행 사항
- F0(경아)의 프론트엔드/백엔드를 기반 구조로 채택
- F4(성은)의 수출국 표시사항 검토 기능 병합
- 파이프라인 구조 설계: `pipeline_steps` 테이블로 기능 간 데이터 교환
- 각 기능별 env prefix 규칙 확립 (`F4_PINECONE_API_KEY` 등)

### 주요 결정
- 프론트엔드 레이아웃: 경아의 f0 디자인(top nav, 다크테마)을 기준으로 통일
- DB 테이블: 기능별 `f{N}_` prefix로 분리
- Pinecone: 기능별 별도 인덱스 사용

---

## 2차: F1 병합 (수입판정)

### 진행 사항
- `f1_이병찬/backend/routers/features.py` → `backend/routers/feature1.py`로 이름 변경 복사
- F1 핵심 로직 복사: `feature1.py`, `step1_ingredients_check.py`, `step3_standards.py`, `law_extractor.py`
- 유틸/상수 복사: `chunker.py`, `cleaner.py`, `unit_converter.py`, `condition_patterns.py`, `gmo.py`, `thresholds_config.py`
- DB 관련: `connection.py` 복사 + `DATABASE_URL` → `F1_DATABASE_URL`로 변경
- DB migrations/seed SQL 복사, `bootstrap_f1_db.py`, `apply_migrations.py` 복사
- `db_manager.py` 라우터 복사 (관리자 DB CRUD)
- 프론트엔드: `features/feature1/` 폴더 통째로 복사, f0 레이아웃 적용

### 발견된 문제
- F1이 다른 기능(F4)의 코드를 포함하고 있었음 → F4 관련 파일 제외하고 복사
- `ANTHROPIC_API_KEY` → `F1_ANTHROPIC_API_KEY`로 리네임 필요
- F1만 asyncpg 직접 연결 사용 (다른 기능은 supabase-py SDK) → DB 비밀번호 필요
- F1의 Supabase 프로젝트가 다른 기능과 다름 (`fhnlknegbzfobnmyeceh` vs `bnfgbwwibnljynwgkgpt`)

### f0→F1 데이터 파이프라인 연결
- `pipeline_steps(step_key='0')`에서 f0 파싱 결과 자동 조회
- ingredients, process_codes를 F1 입력으로 변환
- process_codes → `is_heated`, `is_fermented`, `is_distilled` 변환 로직 구현

### 주요 결정
- F1 담당자에게 asyncpg → supabase-py 변경 요청 (f1_수정_요청_사항.md)
- F1 담당자에게 공통 Supabase 프로젝트로 병합 요청
- DB 마이그레이션은 F1 담당자(병찬)가 직접 실행

---

## 3차: F2 병합 (식품유형 분류)

### 진행 사항
- `f2_이아람/backend/services/feature2.py` → `backend/services/feature2.py`
- `f2_이아람/backend/routers/food_classify.py` → `backend/routers/feature2.py`로 이름 변경
- `feature3.py`(F3 stub) → `f2_required_docs.py`로 이름 변경 (F3와 혼동 방지)
- 프론트엔드: `features/feature2/` 분리, f0 레이아웃 적용
- preprocessing 폴더에서 F4 관련 파일 제외하고 복사

### 발견된 문제
- F2가 `feature3.py`라는 이름으로 간이 필요서류 조회 라우터를 만들어놓음 → F3와 혼동 → `f2_required_docs.py`로 리네임
- `documents.py`는 f0의 upload.py와 중복 → 복사 불필요
- preprocessing이 Node.js 스크립트 (Python이 아님) → Python 통합 필요
- F2 프론트에 파일 업로드 UI가 있음 → f0에서 이미 처리하므로 제거 필요

### f0+F1→F2 데이터 파이프라인 연결
- f0에서: product_name, ingredients, process_codes, export_country
- F1에서: 원재료 판정 상태 (is_allowed 등)
- F2 출력: food_type, category, is_alcohol, alcohol_percentage

### 주요 결정
- F2 담당자에게 Node.js 전처리 → Python 통합 요청
- step2/step3 네이밍 혼란 → 담당자 확인 요청
- 건강기능식품공전 법령 DB 추가 요청

---

## 4차: F3 병합 (필요서류 안내)

### 진행 사항
- `feature_3/` 폴더 구조에서 필요한 파일 추출
- `backend/services/f3_required_docs.py`, `f3_pinecone_client.py` 복사
- `backend/models/f3_schemas.py`, `backend/db/f3_supabase_client.py` 복사
- API Route: `ai-cross-check/route.ts`, `explain-docs/route.ts` 복사 (유용한 기능)
- `analyze-ingredients`, `parse-document`, `query-docs` → f0/백엔드와 중복으로 제외
- 프론트엔드: `features/feature3/` 분리, f0 레이아웃 적용
- Pinecone env prefix: `F3_PINECONE_API_KEY`, `F3_PINECONE_INDEX_NAME`

### 발견된 문제
- F3가 독립 FastAPI 서버(`main.py`)로 만들어져 있었음 → 우리 main.py에 통합
- `pinecone.ts` (프론트 Pinecone 클라이언트)가 API Route에서 사용 → 복사 필요
- F3 원본에 테스트용 직접 입력 UI가 있었음 → 파이프라인 자동 연결로 대체

### f0+F1+F2→F3 데이터 파이프라인 연결
- f0에서: product_name, export_country, is_first_import
- F1에서: is_allowed (수입 허용 여부)
- F2에서: food_type, category, is_alcohol
- F3 출력: required_documents[], ai_cross_check_result

### 주요 결정
- F2의 `f2_required_docs.py`는 F3 본격 구현으로 대체 → 삭제
- ingredient-synonym-map은 F3 담당자 확인 후 연동

---

## 5차: F5 병합 (한글표시사항 시안)

### 진행 사항
- `f5_박세연/backend/services/step6_label.py` → `backend/services/step6_label.py`
- `f5_박세연/backend/services/rag.py` → `backend/services/f5_rag.py`
- `f5_박세연/backend/scripts/embed_laws.py` → `backend/scripts/f5_embed_laws.py`
- `f5_박세연/backend/routers/pipeline.py` → `backend/routers/feature5.py`
- Pinecone env: `F5_PINECONE_API_KEY`, `F5_PINECONE_INDEX_NAME`
- Voyage AI: `F5_VOYAGE_API_KEY` (임베딩용)
- 프론트엔드: `features/feature5/` 분리, f0 레이아웃 적용

### 발견된 문제
- F5가 upload.py, cases.py를 자체 구현 → f0 것 사용
- Pinecone 인덱스명이 하드코딩 → env로 분리
- F4 지적사항을 "상위 5개만" 가져오는 로직 → 사용자 확정 지적사항 전체로 변경

### f0+F1+F2+F4→F5 데이터 파이프라인 연결
- f0에서: product_name, export_country, is_oem, ingredients
- F1에서: verdict (수입판정 결과)
- F2에서: food_type, is_alcohol
- F4에서: 확정된 지적사항 전체 (사용자 체크 확정분)
- F5 출력: label_draft (한글표시사항 시안 텍스트)

### 주요 결정
- Anthropic API 토큰 소진 상태 → 실행 시 에러 발생 가능 (토큰 충전 필요)
- F5_VOYAGE_API_KEY도 별도 가입/발급 필요

---

## 공통 시스템 구축

### 법령 업데이트 시스템
- `backend/routers/admin_law_update.py` 신규 생성
- 법령↔기능 매핑 테이블 (`LAW_FEATURE_MAP`) — 기능 병합 시 행 추가만으로 확장
- 기능별 전처리 함수 레지스트리 (`FEATURE_PROCESSORS`)
- 프론트: `/admin/law-update` 페이지 — 법령별 업로드 박스 + 진행도 팝업
- 네비게이션: 검역관리 드롭다운에 "법령 DB 관리" 항목 추가

### 데이터 파이프라인
```
f0 (서류 업로드 + OCR)
├─→ F1 : ingredients, process_codes
├─→ F2 : f0 + F1 결과
├─→ F4 : 제품명, 원재료, 라벨
└─→ F5 : 제품명, 원산지, OEM, 원재료

F1 → F2 : 원재료 판정 상태
F1 → F5 : 수입판정 결과

F2 → F3 : food_type, category
F2 → F4 : food_type
F2 → F5 : food_type, 주류 여부

F4 → F5 : 라벨 검토 확정 지적사항 전체
```

### 환경변수 정리
- `.env.example` 생성 (전체 키 목록 + 설명)
- `.gitignore`에 `.env`, `병합완료된_원본/` 추가
- `requirements.txt` 전기능 통합

---

## 실행 시 발견된 이슈

### CORS
- main.py에 `localhost:3001` 추가 필요 (프론트 dev 서버)
- 백엔드 재시작 후에야 CORS 설정 반영됨

### F1 DB 연결
- F1만 asyncpg 직접 연결 사용 → `F1_DATABASE_URL` 필요
- Supabase IPv6 전용 → Shared Pooler(IPv4) 주소 사용 필요
  - `db.xxx.supabase.co:5432` → `aws-1-ap-northeast-2.pooler.supabase.com:6543`
  - user: `postgres` → `postgres.프로젝트ref`
- F1의 Supabase 프로젝트가 다른 기능과 다름 → 데이터 불일치 발생
  - f0는 `bnfgbwwibnljynwgkgpt`에 저장, F1은 `fhnlknegbzfobnmyeceh`에서 조회
  - → F1 담당자에게 공통 프로젝트 통합 요청

### 한글 인코딩 (Windows cp949)
- Python 파일에 한글 주석이 있으면 `UnicodeDecodeError` 발생
- 해결: `.py` 파일 상단에 `# -*- coding: utf-8 -*-` 또는 파일을 UTF-8로 저장
- main.py lifespan에서 에러 메시지 한글 → 영어로 변경

### dashboard.tsx button nesting
- `<button>` 안에 `<button>` → React hydration warning
- 심각하지 않지만 수정 필요 (f0 담당자)

---

## 파일 정리

### 삭제된 폴더
- `DB_API/` — 빈 폴더
- `DB_최신/` — 로컬 참고용 PDF (DB에 이미 올라감)
- `frontend_backup_20260414_190345/` — 이전 백업 (병합완료된_원본에 원본 있음)
- `frontend/candidate1/` — 초기 개발 시도 (구버전)
- `대화내용_정리/` — 참고용 1개 파일

### gitignore 추가
- `병합완료된_원본/` — git에 올리지 않음 (로컬 보관용)

---

## 산출물 목록

| 파일 | 용도 |
|------|------|
| `MERGE_GUIDE.md` | 병합 가이드 + 코드 소유권 + 작업 범위 |
| `계획/팀_컨벤션_룰.md` | 팀 컨벤션 규칙 (MERGE_GUIDE 우선) |
| `f0_수정_요청_사항.md` | f0 담당자(경아) 확인 사항 |
| `f1_수정_요청_사항.md` | F1 담당자(병찬) 확인 사항 |
| `f2_수정_요청_사항.md` | F2 담당자(아람) 확인 사항 |
| `f3_수정_요청_사항.md` | F3 담당자(유빈) 확인 사항 |
| `f4_수정_요청_사항.md` | F4 담당자(성은) 확인 사항 |
| `f5_수정_요청_사항.md` | F5 담당자(세연) 확인 사항 |
| `backend/.env.example` | 환경변수 템플릿 |
| `backend/requirements.txt` | Python 패키지 통합 |


# 법령 DB 업데이트 — API 자동화 전환 가이드

## 배경

기존에는 법령 파일(PDF/HWPX)을 직접 다운받아 Admin UI에서 업로드하는 **반자동** 방식이었습니다.
F4에서 먼저 **국가법령정보센터 Open API**를 활용한 자동 업데이트로 전환했고, 다른 기능도 같은 방식으로 전환할 수 있습니다.

---

## F4 전환 요약

### 변경된 것

| 항목 | 기존 (반자동) | 변경 (API 자동) |
|------|-------------|----------------|
| 데이터 소스 | PDF/HWPX 파일 직접 다운로드 | 국가법령정보센터 API |
| 업데이트 방식 | Admin UI에서 수동 업로드 | 스크립트 실행 (cron 가능) |
| 텍스트 파싱 | pdfplumber, pymupdf, Vision API | API가 조/항/호/목 분리해서 제공 |
| 청킹 | chunk_by_article() 직접 분할 | 법령: API 구조 활용 / 고시: 기존 로직 재사용 |
| 변경 감지 | 사람이 판단 | 공포일자/발령일자 자동 비교 |
| 별표/서식 | PDF에서 표 추출 + 이미지 Vision API | API가 별표 텍스트로 제공 + 파일링크 |

### 추가된 파일

| 파일 | 역할 |
|------|------|
| `backend/services/law_api_client.py` | API 클라이언트 + 청크 변환 + 변경 감지 + 전처리 |
| `backend/scripts/f4_sync_laws.py` | cron용 동기화 스크립트 |
| `backend/db/feature4/migrate_f4_law_api.sql` | Supabase 컬럼 추가 (api_id, api_type 등) |

### 사용법

```bash
# 변경된 법령만 업데이트
python -m backend.scripts.f4_sync_laws

# 전체 강제 재적재 (초기 또는 문제 발생 시)
python -m backend.scripts.f4_sync_laws --force
```

### admin_law_update.py 변경사항

`LAW_FEATURE_MAP`에서 F4 법령 7개의 features 리스트에서 `"F4"`를 제거했습니다.
F5 등 다른 기능이 같은 법령을 사용하는 경우 해당 기능 코드는 유지됩니다.
기존 파일 업로드 방식은 **다른 기능용으로 그대로 동작**합니다.

---

## 다른 기능에서 API 전환하려면

### 1단계: 사용하는 법령의 API 유형 확인

| 법령 유형 | API target | 조문 구조 |
|-----------|-----------|-----------|
| 법률, 시행령, 시행규칙 | `eflaw` | 조/항/호/목 분리됨 |
| 고시 (행정규칙) | `admrul` | 조문내용 통째로 옴 |

### 2단계: 법령 ID 확보

**법령 (법률/시행령/시행규칙)**
```
검색: http://www.law.go.kr/DRF/lawSearch.do?OC=Ipcr0618&target=eflaw&type=XML&query=법령명&nw=3
→ 응답에서 <법령ID> 확보 (이 ID로 항상 현행 본문 조회 가능)
```

**고시 (행정규칙)**
```
검색: http://www.law.go.kr/DRF/lawSearch.do?OC=Ipcr0618&target=admrul&type=XML&query=고시명&nw=1&knd=3
→ 응답에서 <행정규칙ID> 확보 (LID)
```

> API 인증키: `Ipcr0618` (공용)
> .env 변수: `LAW_API_OC`

### 3단계: API 클라이언트 재사용

`law_api_client.py`의 함수들을 그대로 사용할 수 있습니다:

```python
from backend.services.law_api_client import fetch_eflaw_body, fetch_admrul_body

# 법령 본문 가져오기 (조/항/호/목 분리됨)
body = fetch_eflaw_body("법령ID")
# body["articles"] → 조문 리스트
# body["별표"] → 별표 리스트

# 고시 본문 가져오기 (조문내용 통째로)
body = fetch_admrul_body("행정규칙ID(LID)")
# body["조문내용_list"] → 조문 텍스트 리스트
# body["별표"] → 별표 리스트
```

### 주의: API 별표 데이터 전처리 시 필수 처리 사항

**1. 서식/도안/별지/신청서 필터링**

API 응답의 별표에는 실제 법령 규정뿐만 아니라 **행정 양식(신청서, 서식, 도안, 별지)** 이 포함되어 있습니다.
이것들을 Pinecone에 그대로 넣으면 RAG 검색 시 엉뚱한 결과가 나옵니다.

- 예: "의약품 오인" 검색 → "기능성 표시 서식 도안(신청서 양식)" 이 반환됨
- 별표 제목/내용에 `별지`, `서식`, `신청서`, `도안` 키워드가 포함된 청크는 **반드시 제외**해야 합니다.

F4에서는 `law_api_client.py`의 `_is_form_or_template()` 함수로 필터링하고 있습니다.

**2. 별표번호 zero-padding 정리**

API 응답의 `별표번호`가 `"0001"`, `별표가지번호`가 `"00"` 형태로 옵니다.
그대로 사용하면 `별표 0001의00-2` 같은 읽기 어려운 라벨이 생깁니다.

- `"0001"` → `"1"`, `"00"` → 무시
- `별표 1(제목)` 형태로 가독성 있게 변환해야 합니다.

### 4단계: 청킹/임베딩은 각 기능 파이프라인 그대로

> **중요: Pinecone 인덱스는 기능별로 분리 유지해야 합니다.**

이유:
- 임베딩 모델이 다름 (F0/F1/F2: OpenAI 1536dim / F4: e5-large 1024dim / F5: voyage-3 1024dim)
- 메타데이터 구조가 다름 (F1: namespace 기반, F4: tier 기반, F3: related_doc_ids 등)
- 전처리/검색 로직이 다름

**공유 가능한 것**: API에서 텍스트 가져오는 부분만
**각자 해야 하는 것**: 청킹 → 임베딩 → Pinecone 저장 → Supabase 저장

### 5단계: 변경 감지 + 스케줄러

F4와 동일한 패턴으로:
1. API에서 공포일자/발령일자 조회
2. DB에 저장된 값과 비교
3. 변경 시에만 전처리 실행

---

## API 응답 구조 요약

### 법령 (eflaw) — 조/항/호/목 분리됨

```xml
<조문단위>
  <조문번호>8</조문번호>
  <조문제목>부당한 표시 또는 광고행위의 금지</조문제목>
  <조문내용>제8조(부당한 표시 또는 광고행위의 금지)</조문내용>
  <조문변경여부>N</조문변경여부>   ← 개정 감지에 활용
  <항>
    <항번호>①</항번호>
    <항내용>① 누구든지 ...</항내용>
    <호>
      <호번호>1.</호번호>
      <호내용>1. 질병의 예방ㆍ치료에 ...</호내용>
    </호>
  </항>
</조문단위>

<별표단위>
  <별표제목>부당한 표시 또는 광고의 내용</별표제목>
  <별표내용>텍스트로 제공됨 (수천~수만 자)</별표내용>
  <별표서식파일링크>/LSW/flDownload.do?flSeq=...</별표서식파일링크>
</별표단위>
```

### 행정규칙 (admrul) — 조문내용 통째로

```xml
<조문형식여부>Y</조문형식여부>   ← Y이면 조문 형식
<조문내용>제1조(목적) 이 고시는 ...</조문내용>
<조문내용>제2조(정의) ...</조문내용>

<별표단위>
  <별표제목>한약재 처방명 및 이와 유사한 명칭</별표제목>
  <별표내용>텍스트로 제공됨</별표내용>
</별표단위>
```

---

## F4 법령 7개 ID 레지스트리 (참고용)

### 법령 3개 (target=eflaw)

| 법령명 | 법령ID | MST | 비고 |
|--------|--------|-----|------|
| 식품 등의 표시ㆍ광고에 관한 법률 | 013094 | 269957 | 법률 |
| 식품 등의 표시ㆍ광고에 관한 법률 시행령 | 013453 | 273545 | 대통령령 |
| 식품 등의 표시ㆍ광고에 관한 법률 시행규칙 | 013475 | 267855 | 총리령 |

### 고시 4개 (target=admrul)

| 고시명 | 행정규칙ID(LID) | 비고 |
|--------|----------------|------|
| 식품등의 표시기준 | 36814 | 제2025-60호 |
| 식품등의 부당한 표시 또는 광고의 내용 기준 | 69549 | 제2025-79호 |
| 부당한 표시 또는 광고로 보지 아니하는 식품등의 기능성 표시 또는 광고에 관한 규정 | 75449 | 제2024-62호 |
| 식품등의 한시적 기준 및 규격 인정 기준 | 37975 | 제2025-75호 |

---

## 참고

- 국가법령정보센터 API 문서: https://www.law.go.kr/LSO/openApi.do
- 법령 개정 시 법령ID/MST는 유지됨 (법령)
- 고시 행정규칙ID(LID)는 개정 시 변경될 수 있음 → 이름 기반 fallback 로직 구현되어 있음
- API 응답은 최신 법령 반영 (법제처 공식 시스템)
