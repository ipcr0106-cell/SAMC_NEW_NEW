# PM 공지: Python 버전 및 requirements.txt 통합 조정

> 작성일: 2026-04-19
> 작성자: PM (성은 조사 기반)
> 대상: 전체 팀 (경아, 병찬, 아람, 유빈, 성은, 세연)

---

## 1. 현재 문제

현재 로컬 개발 환경이 **Python 3.14**인데, 아래 두 가지 문제가 발생합니다.

| 문제 | 원인 | 영향 |
|------|------|------|
| `voyageai>=0.3.0` 설치 불가 | voyageai가 `Requires-Python: >=3.9, <3.14` — 3.14 명시 차단 | F5 기능 불가 |
| `pydantic-core` 빌드 실패 | `--ignore-requires-python` 사용 시 Rust 빌드 충돌 | 전체 서버 실행 불가 |

**배포 환경에서도 동일 문제 발생 예정이므로, 지금 맞춰야 합니다.**

---

## 2. Python 버전 — 3.12로 통일

전체 패키지 호환성 조사 결과:

| 패키지 | 용도 | 3.9 | 3.10 | 3.11 | 3.12 | 3.13 | 3.14 |
|--------|------|:---:|:----:|:----:|:----:|:----:|:----:|
| pinecone 8.x | F1~F5 벡터 검색 | X | O | O | O | O | O |
| voyageai 0.3.7 | F5 Voyage-3 임베딩 | O | O | O | O | O | **X** |
| pydantic 2.10.4 | 전체 (FastAPI) | O | O | O | O | O | ? |
| fastapi 0.115.6 | 전체 | O | O | O | O | O | ? |
| sentence-transformers 3.3.1 | F4 임베딩 | O | O | O | O | ? | ? |
| supabase 2.11.0 | 전체 DB | O | O | O | O | O | ? |

**안전한 교집합: Python 3.10 ~ 3.13**

**권장: Python 3.12** (모든 패키지가 공식 classifier에 명시한 가장 높은 안정 버전)

### 각자 해야 할 것

```bash
# 1. Python 3.12 설치 (이미 있으면 스킵)
#    https://www.python.org/downloads/release/python-3120/

# 2. 가상환경 재생성
cd backend
python3.12 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. 패키지 재설치
pip install -r requirements.txt
```

---

## 3. requirements.txt 변경사항

### 3-1. F4 전용 requirements.txt 제거

`backend/db/feature4/requirements.txt`의 내용을 공용 `backend/requirements.txt`에 합쳤습니다.
**F4 전용 파일은 더 이상 사용하지 않습니다.**

### 3-2. 공용 requirements.txt 변경 내역

| 패키지 | 이전 | 이후 | 사유 |
|--------|------|------|------|
| `pinecone-client>=5.0.0` | 있었음 | **삭제** | deprecated 패키지 (5.1.0부터 `pinecone`으로 통합) |
| `pinecone` | 없었음 | **`>=8.0.0`** | 정식 패키지명으로 교체 + 최신 버전 |
| `sentence-transformers` | `>=2.2.0` | **`>=3.3.0`** | F4가 3.3.1 사용 |
| `fpdf2` | `>=2.7.0` | **`>=2.8.1`** | F4가 더 높은 버전 요구 |
| `pdfplumber` | 없었음 | **`==0.11.4`** | F4/F5 법령 PDF 텍스트 추출 |
| `tqdm` | 없었음 | **`>=4.66.0`** | F4 전처리 진행도 표시 |
| `tiktoken` | 없었음 | **`>=0.7.0`** | F1 청킹 토큰 카운팅 |

### 3-3. pinecone 업그레이드 (5.0.1 → 8.x) 영향

F4 코드 전체 + 다른 기능에서 사용하는 Pinecone API를 조사한 결과:

| 사용 패턴 | v5 | v8 | 코드 수정 필요 |
|-----------|:--:|:--:|:-----------:|
| `from pinecone import Pinecone` | O | O | 불필요 |
| `Pinecone(api_key=...)` | O | O | 불필요 |
| `pc.Index("name")` / `pc.Index(host=...)` | O | O | 불필요 |
| `index.query(vector=..., top_k=...)` | O | O | 불필요 |
| `index.upsert(vectors=[...])` | O | O | 불필요 |
| `index.delete(ids=[...])` | O | O | 불필요 |
| `index.fetch(ids=[...])` | O | O | 불필요 |

**결론: 전 기능 코드 수정 없이 pinecone 8.x 사용 가능**

단, 업그레이드 후 아래 deprecated 플러그인이 남아있으면 에러가 발생합니다:
```bash
# 이 에러가 나면:
# DeprecatedPluginError: The `pinecone-plugin-inference` package has been deprecated.

# 해결:
pip uninstall pinecone-plugin-inference -y
```

---

## 4. 기능별 확인 요청

| 담당 | 확인사항 |
|------|---------|
| **경아 (f0)** | Python 3.12 전환 후 OCR/파싱 정상 동작 확인 |
| **병찬 (F1)** | pinecone 8.x + tiktoken 설치 후 수입판정 정상 확인 |
| **아람 (F2)** | pinecone 8.x 전환 후 식품유형 분류 정상 확인 |
| **유빈 (F3)** | pinecone 8.x 전환 후 필요서류 RAG 정상 확인 |
| **성은 (F4)** | 확인 완료 — pinecone 8.1.2 + 코드 수정 없이 정상 |
| **세연 (F5)** | Python 3.12 전환 후 voyageai 설치 + 한글시안 정상 확인 |

---

## 5. 최종 requirements.txt (현재 상태)

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
python-multipart==0.0.18
pydantic==2.10.4
anthropic==0.43.0
openai==1.57.0
httpx==0.28.1
PyMuPDF==1.25.1
openpyxl==3.1.5
Pillow==12.1.0
python-docx==1.1.2
reportlab==4.2.5
python-dotenv==1.0.1
supabase==2.11.0
pinecone>=8.0.0
tiktoken>=0.7.0
sentence-transformers>=3.3.0
fpdf2>=2.8.1
pdfplumber==0.11.4
tqdm>=4.66.0
voyageai>=0.3.0
```
