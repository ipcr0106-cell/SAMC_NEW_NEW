# F1 RAG 도입 계획 — 전처리

> 총괄 문서: [f1_RAG도입계획_총괄.md](f1_RAG도입계획_총괄.md)
> 개정 (2026-04-17): critic 검토 반영 — 기존 `utils.chunker.pdf_to_markdown` 재사용, `pinecone>=8.0.0` API 정합

전처리 = 인덱스 생성 + 청킹 알고리즘 포팅 + 데이터 적재(복제 + 신규 임베딩) + 미러 테이블.

## 0. 사실 정정 (이전 버전 오류)

| 항목 | 이전 안 | 정정 |
|---|---|---|
| Pinecone 패키지 | `pinecone-client>=4.0.0` | **`pinecone>=8.0.0` 이미 설치됨** ([requirements.txt:19](../backend/requirements.txt)). 추가 설치 불필요 |
| PDF→markdown 함수 | `pymupdf4llm` 신규 도입 | **`backend/utils/chunker.py`의 `pdf_to_markdown` 함수 재사용** (`admin_law_update._run_f1_preprocess`도 이걸 사용 중) |
| OpenAI 패키지 | 신규 추가 | **`openai==1.57.0` 이미 설치됨** |
| `NEWSAMC_PINECONE_API_KEY` env | 별도 키처럼 표현 | **회사 공용 Pinecone 키 = newsamc 키** (조사 확인). `F1_PINECONE_API_KEY` 1개로 source/target 모두 접근 |

## 1. Pinecone 인덱스 자동 생성

### 1.1 스크립트: `backend/scripts/f1_create_pinecone_index.py`

```python
"""Pinecone에 samc-law-f1 인덱스 생성 (idempotent, pinecone v8 API)"""
from __future__ import annotations
import os
from pinecone import Pinecone, ServerlessSpec

INDEX_NAME = "samc-law-f1"
DIMENSION = 1536
METRIC = "cosine"
CLOUD = "aws"
REGION = "us-east-1"

def main() -> None:
    pc = Pinecone(api_key=os.environ["F1_PINECONE_API_KEY"])
    # v8 API: list_indexes() returns IndexList object with .names() or iterable .indexes attr
    existing = {idx["name"] for idx in pc.list_indexes()}
    if INDEX_NAME in existing:
        print(f"[skip] {INDEX_NAME} already exists")
        return
    pc.create_index(
        name=INDEX_NAME,
        dimension=DIMENSION,
        metric=METRIC,
        spec=ServerlessSpec(cloud=CLOUD, region=REGION),
    )
    print(f"[created] {INDEX_NAME} dim={DIMENSION} metric={METRIC}")

if __name__ == "__main__":
    main()
```

> **검증 권장**: `pinecone>=8.0.0`의 `list_indexes()` 반환 형태를 코드 작성 시 한 번 확인. 위 코드는 사전 가정으로, 실제 v8 API에 맞춰 미세 조정 필요.

실행:
```bash
python -m backend.scripts.f1_create_pinecone_index
```

### 1.2 검증

```python
# backend/scripts/f1_verify_pinecone.py
from pinecone import Pinecone
import os
pc = Pinecone(api_key=os.environ["F1_PINECONE_API_KEY"])
idx = pc.Index("samc-law-f1")
print(idx.describe_index_stats())
```

기대 출력 (Phase 1 직후):
```json
{ "namespaces": {}, "dimension": 1536, "totalRecordCount": 0 }
```

## 2. Postgres 미러 테이블

### 2.1 마이그레이션 `010_f1_law_chunks.sql`

```sql
CREATE TABLE IF NOT EXISTS f1_law_chunks (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  vector_id       text NOT NULL UNIQUE,
  regulation_id   text NOT NULL,
  pinecone_namespace text NOT NULL,
  section_path    text,
  text            text NOT NULL,
  token_count     int,
  chunk_index     int,
  total_chunks    int,
  embedded_at     timestamptz NOT NULL DEFAULT now(),
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_f1_law_chunks_namespace
  ON f1_law_chunks(pinecone_namespace);
CREATE INDEX IF NOT EXISTS idx_f1_law_chunks_regulation
  ON f1_law_chunks(regulation_id);
CREATE INDEX IF NOT EXISTS idx_f1_law_chunks_vector_id
  ON f1_law_chunks(vector_id);

-- RLS
ALTER TABLE f1_law_chunks ENABLE ROW LEVEL SECURITY;
CREATE POLICY f1_law_chunks_read ON f1_law_chunks
  FOR SELECT USING (auth.role() = 'authenticated' OR auth.role() = 'service_role');
CREATE POLICY f1_law_chunks_write ON f1_law_chunks
  FOR ALL USING (auth.role() = 'service_role');
```

### 2.2 적용

```bash
# Supabase SQL Editor에 010_f1_law_chunks.sql 실행
# 또는
python -m backend.scripts.bootstrap_f1_db --only 010
```

## 3. 청킹 알고리즘 포팅 (TS → Python)

### 3.1 `backend/services/f1_chunking.py`

newsamc `chunking-service.ts` 1:1 포팅. 핵심 함수:

| 함수 | 입력 | 출력 |
|---|---|---|
| `split_by_article(markdown)` | str | list[dict{text, section_path}] |
| `count_tokens(text)` | str | int (`tiktoken cl100k_base`) |
| `merge_small_chunks(chunks)` | list | list (200~1500 정규화) |
| `split_large_chunk(chunk)` | dict | list (`①②③` 분할 또는 슬라이딩) |
| `attach_metadata(chunks, regulation_id, namespace)` | ... | list[dict{vector_id, text, metadata{...}}] |

상수:
```python
MIN_CHUNK_TOKENS = 200
MAX_CHUNK_TOKENS = 1500
OVERLAP_TOKENS = 200
EMBED_BATCH_SIZE = 100
PINECONE_BATCH_SIZE = 100
```

vector_id 규칙: `{regulation_id}_{chunk_index}` (newsamc 동일).

### 3.2 토큰 카운팅

```python
import tiktoken
_ENC = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(_ENC.encode(text))
```

이유: OpenAI text-embedding-3-small 토큰 한도 8191. 정확 카운팅으로 1500 상한 안전 보장.

### 3.3 단위 테스트 케이스

| 테스트 | 입력 | 기대 |
|---|---|---|
| 조항 분할 | `### 제1조` + `### 제2조` 마크다운 | 2개 청크 |
| 소형 병합 | 150 토큰 청크 2개 연속 | 1개로 병합 |
| 대형 분할 | 2000 토큰 단일 청크 | 1500 이하 N개 |
| 항/호 분할 | `①②③` 포함 대형 청크 | ①, ②, ③ 분할 |
| 폴백 슬라이딩 | 항 없는 5000 토큰 | 200 오버랩 윈도우 |

## 4. 데이터 이전 (Phase 2)

### 4.1 newsamc → samc-law-f1 복제 스크립트

`backend/scripts/f1_replicate_from_newsamc.py`:

```python
"""samc-law (newsamc) → samc-law-f1 복제

전제 (조사 확인됨):
- newsamc PINECONE_API_KEY = SAMC 회사 공용 Pinecone 계정과 동일
- 차원 동일 1536
- F1 관련 namespace 4개만 복제 (additive_code_text는 Phase 3 신규 임베딩)
"""
from __future__ import annotations
import os
from pinecone import Pinecone
from supabase import create_client

SOURCE_INDEX = "samc-law"
TARGET_INDEX = "samc-law-f1"
F1_NAMESPACES = [
    "food_code_text",
    "functional_labeling",
    "temporary_standard",
    "health_food_text",
]
BATCH_SIZE = 100

def replicate_namespace(src, dst, ns: str, sb_client) -> int:
    """단일 namespace 전체 fetch → upsert + Postgres 미러 INSERT"""
    # 1. 전체 vector_id 수집 (v8 list 페이지네이션)
    ids = []
    for page in src.list(namespace=ns):
        ids.extend(page)
    print(f"[{ns}] 수집 ID {len(ids)}개")

    # 2. 배치 fetch + upsert + mirror
    for i in range(0, len(ids), BATCH_SIZE):
        batch_ids = ids[i:i + BATCH_SIZE]
        fetched = src.fetch(ids=batch_ids, namespace=ns)

        upsert_vectors = []
        mirror_rows = []
        for vid, vec in fetched.vectors.items():
            upsert_vectors.append({
                "id": vid,
                "values": vec.values,
                "metadata": vec.metadata,
            })
            mirror_rows.append({
                "vector_id": vid,
                "regulation_id": vec.metadata.get("regulation_id", "unknown"),
                "pinecone_namespace": ns,
                "section_path": vec.metadata.get("section_path"),
                "text": vec.metadata.get("text", ""),
                "token_count": vec.metadata.get("token_count"),
                "chunk_index": vec.metadata.get("chunk_index"),
                "total_chunks": vec.metadata.get("total_chunks"),
            })

        dst.upsert(vectors=upsert_vectors, namespace=ns)
        sb_client.table("f1_law_chunks").upsert(
            mirror_rows, on_conflict="vector_id"
        ).execute()
        print(f"[{ns}] {i+len(batch_ids)}/{len(ids)} 완료")

    return len(ids)


def main() -> None:
    api_key = os.environ["F1_PINECONE_API_KEY"]  # source/target 동일 키
    pc = Pinecone(api_key=api_key)
    src = pc.Index(SOURCE_INDEX)
    dst = pc.Index(TARGET_INDEX)
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    total = 0
    for ns in F1_NAMESPACES:
        total += replicate_namespace(src, dst, ns, sb)
    print(f"\n=== 총 {total}건 복제 완료 ===")


if __name__ == "__main__":
    main()
```

> **참고**: 별도 `NEWSAMC_PINECONE_API_KEY` env 불필요. 회사 공용 Pinecone 계정에서 두 인덱스 모두 접근.

### 4.2 검증 스크립트 `f1_verify_replication.py`

```python
"""복제 후 source vs target 건수/샘플 비교"""
from __future__ import annotations
import os
from pinecone import Pinecone

api_key = os.environ["F1_PINECONE_API_KEY"]
pc = Pinecone(api_key=api_key)
src = pc.Index("samc-law")
dst = pc.Index("samc-law-f1")

src_stats = src.describe_index_stats()
dst_stats = dst.describe_index_stats()

print("=== 건수 비교 ===")
for ns in ["food_code_text", "functional_labeling", "temporary_standard", "health_food_text"]:
    s = src_stats.namespaces.get(ns, {}).get("recordCount", 0) if hasattr(src_stats, 'namespaces') else 0
    d = dst_stats.namespaces.get(ns, {}).get("recordCount", 0) if hasattr(dst_stats, 'namespaces') else 0
    status = "OK" if s == d else "MISMATCH"
    print(f"[{status}] {ns}: src={s} dst={d}")

# TODO: 랜덤 샘플 5개씩 fetch + metadata.text 일치 검증
```

기대: 484건 일치 (140 + 18 + 74 + 252).

## 5. 식품첨가물공전 신규 임베딩 (Phase 3)

### 5.1 입력 자료

식품첨가물공전 PDF/HWPX 원본 파일. 위치는 운영팀 확인. 후보:
- `data/laws/식품첨가물공전.pdf` (신규 디렉토리)
- 또는 Supabase Storage `documents` 버킷 업로드 후 다운로드

### 5.2 PDF→markdown 변환 — 기존 함수 재사용

`backend/utils/chunker.py`의 `pdf_to_markdown(file_path: str) -> str` 함수를 그대로 사용. `admin_law_update.py:307`에서도 이미 사용 중이므로 이미 검증됨.

추가 라이브러리 설치 불필요 (`PyMuPDF==1.25.1` 이미 설치).

> **만약** `pdf_to_markdown` 품질이 식품첨가물공전 PDF에 부족하면 그때 별도 라이브러리(`pymupdf4llm`) 검토 — 이는 Phase 3-4 작업으로 분리.

### 5.3 스크립트 `backend/scripts/f1_embed_additive_code.py`

```python
"""식품첨가물공전 PDF → 청킹 → 임베딩 → samc-law-f1/additive_code_text"""
from __future__ import annotations
import os
import sys
import time
from supabase import create_client

from backend.services import f1_openai_client, f1_pinecone_client
from backend.services.f1_chunking import (
    split_by_article, merge_small_chunks, attach_metadata,
)
from backend.utils.chunker import pdf_to_markdown  # ← 재사용

NAMESPACE = "additive_code_text"

def main(pdf_path: str) -> None:
    regulation_id = f"additive_code_{int(time.time())}"

    # 1. PDF → markdown (기존 함수)
    print("[1/4] PDF→markdown 변환")
    markdown = pdf_to_markdown(pdf_path)

    # 2. 청킹
    print("[2/4] 청킹")
    raw = split_by_article(markdown)
    normalized = merge_small_chunks(raw)
    chunks = attach_metadata(normalized, regulation_id, NAMESPACE)
    print(f"  → 청크 {len(chunks)}개")

    # 3. 배치 임베딩 + Pinecone upsert
    print("[3/4] 임베딩 + Pinecone upsert")
    idx = f1_pinecone_client.get_index()
    vectors = []
    for i in range(0, len(chunks), 100):
        batch = chunks[i:i+100]
        embeds = f1_openai_client.embed([c["text"] for c in batch])
        for c, e in zip(batch, embeds):
            vectors.append({
                "id": c["vector_id"],
                "values": e,
                "metadata": {**c["metadata"], "text": c["text"][:4000]},
            })
        idx.upsert(vectors=vectors[-len(batch):], namespace=NAMESPACE)
        print(f"  → {i+len(batch)}/{len(chunks)}")

    # 4. Postgres 미러
    print("[4/4] Postgres 미러")
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    rows = [{
        "vector_id": v["id"],
        "regulation_id": regulation_id,
        "pinecone_namespace": NAMESPACE,
        "section_path": v["metadata"].get("section_path"),
        "text": v["metadata"].get("text", ""),
        "token_count": v["metadata"].get("token_count"),
        "chunk_index": v["metadata"].get("chunk_index"),
        "total_chunks": v["metadata"].get("total_chunks"),
    } for v in vectors]
    sb.table("f1_law_chunks").upsert(rows, on_conflict="vector_id").execute()

    print(f"\n=== 완료: {len(vectors)}건 적재 (regulation_id={regulation_id}) ===")


if __name__ == "__main__":
    main(sys.argv[1])
```

### 5.4 재시도 + 체크포인트

newsamc 패턴 채용:
- 임베딩/upsert 모두 재시도 3회 + 지수 백오프 (Phase 3 구현)
- 체크포인트 파일: `.omc/state/f1_embed_checkpoint_{regulation_id}.json`
- 실패 청크 로그: `logs/f1_embed_failures_{date}.jsonl`

## 6. 운영 스크립트 모음

| 스크립트 | 역할 | 실행 빈도 |
|---|---|---|
| `f1_create_pinecone_index.py` | 인덱스 1회 생성 | 1회 |
| `f1_verify_pinecone.py` | stats 조회 | 수시 |
| `f1_replicate_from_newsamc.py` | newsamc 복제 | 1회 (Phase 2) |
| `f1_verify_replication.py` | 복제 검증 | Phase 2 직후 |
| `f1_embed_additive_code.py` | 식품첨가물공전 임베딩 | 1회 + 개정 시 |

추가로 admin UI 흐름은 `admin_law_update._run_f1_preprocess()` (Phase 4-B에서 RAG 임베딩으로 교체) — 운영팀이 PDF 업로드 시 자동 실행됨.

## 7. 비용 추정 (1회성)

| 항목 | 단가 (2026-04 기준 추정) | 추정량 | 비용 |
|---|---|---|---|
| 식품첨가물공전 임베딩 | $0.02 / 1M tokens | ~500K tokens | **~$0.01** |
| 복제 (벡터 fetch+upsert) | Pinecone 호출 비용만 | 484건 | < $0.01 |
| 운영 시 임베딩 (요청당) | $0.02 / 1M tokens | ~200 tokens | **~$0.000004 / req** |
| 운영 시 Chat (gpt-4o-mini) | $0.15 / 1M in, $0.6 / 1M out | ~3K in / 500 out | **~$0.0008 / req** |

→ 일 1000 요청 기준 약 **$0.8/일 = $24/월** (gpt-4o-mini 사용 시).

## 8. 컨벤션 체크

- [x] `f1_*` 테이블만 신설
- [x] `samc-law-f1` 자기 인덱스만
- [x] `F1_` prefix env (NEWSAMC env는 사용 안 함, 동일 키)
- [x] 다른 기능 영향 없음
- [x] 기존 `utils.chunker.pdf_to_markdown` 재사용 (라이브러리 추가 없음)
