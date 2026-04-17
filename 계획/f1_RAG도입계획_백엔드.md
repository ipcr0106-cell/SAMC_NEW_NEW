# F1 RAG 도입 계획 — 백엔드

> 총괄 문서: [f1_RAG도입계획_총괄.md](f1_RAG도입계획_총괄.md)
> 개정 (2026-04-17): critic 검토 반영 — 실제 `feature1.py`/`routers/feature1.py`/`admin_law_update.py` 시그니처와 HITL 통합 반영

## 0. 실제 파일 기준 참조점

수정 시 항상 다음 실제 코드를 기준으로 한다 (계획서 코드는 의사코드일 뿐):

| 파일 | 핵심 사항 |
|---|---|
| [backend/services/feature1.py:29](../backend/services/feature1.py) | `run_feature1(ingredients: list[Ingredient], food_type, process_conditions) -> Feature1Output` |
| [backend/routers/feature1.py:80](../backend/routers/feature1.py) | `_to_pipeline_result(out: Feature1Output) -> dict` (RAG 통합 지점) |
| [backend/routers/feature1.py:207](../backend/routers/feature1.py) | `Feature1GetResponse {case_id, status, ai_result, final_result, edit_reason, law_references, updated_at}` |
| [backend/routers/admin_law_update.py:294](../backend/routers/admin_law_update.py) | `_run_f1_preprocess` (Claude → RAG 교체 대상) |
| [backend/routers/admin_law_update.py:170](../backend/routers/admin_law_update.py) | `_get_f1_clients` (env 키 교체 대상) |
| [backend/requirements.txt:5,19](../backend/requirements.txt) | `anthropic==0.43.0` (유지), `pinecone>=8.0.0` (유지), `openai==1.57.0` (유지) |

## 1. 환경 변수

`backend/.env.example` 변경:

```diff
- F1_ANTHROPIC_API_KEY=sk-ant-...
+ F1_OPENAI_API_KEY=sk-proj-...
+ F1_OPENAI_CHAT_MODEL=gpt-4o-mini
+ F1_OPENAI_EMBED_MODEL=text-embedding-3-small
+ F1_PINECONE_API_KEY=pcsk_...
+ F1_PINECONE_INDEX=samc-law-f1
+ F1_RAG_TOP_K=5
```

`MERGE_GUIDE.md`의 env 표(733~767줄 부근)도 동일하게 수정.

## 2. requirements.txt

이미 설치된 패키지를 활용하므로 추가는 `tiktoken` 1줄만.

```diff
+ # F1: 청킹 토큰 카운팅
+ tiktoken>=0.7.0
```

**유지 (제거 금지)**:
- `anthropic==0.43.0` — 다른 기능에서 사용 가능성 (확인 필요하나 신중을 위해 유지)
- `pinecone>=8.0.0` — F2~F5 + F1 공용
- `openai==1.57.0` — 이미 설치됨, F1도 사용

## 3. 신규 모듈

### 3.1 `backend/services/f1_openai_client.py`

```python
"""F1 전용 OpenAI 클라이언트 — 임베딩 + Chat (JSON mode)"""
from __future__ import annotations
import os
from openai import OpenAI

_client: OpenAI | None = None

def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["F1_OPENAI_API_KEY"])
    return _client

def embed(texts: list[str]) -> list[list[float]]:
    """배치 임베딩 (최대 100개)"""
    model = os.environ.get("F1_OPENAI_EMBED_MODEL", "text-embedding-3-small")
    resp = get_client().embeddings.create(model=model, input=texts)
    return [d.embedding for d in resp.data]

def chat_json(system: str, user: str, model: str | None = None) -> dict:
    """Chat Completions — JSON 모드 강제 + 파싱"""
    import json
    model = model or os.environ.get("F1_OPENAI_CHAT_MODEL", "gpt-4o-mini")
    resp = get_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},  # JSON 강제
    )
    raw = resp.choices[0].message.content or "{}"
    return json.loads(raw)
```

> **주의**: `gpt-4o-mini`는 JSON mode 지원. 시스템 프롬프트에 "JSON으로 응답"이라는 단어가 포함되어야 작동.

### 3.2 `backend/services/f1_pinecone_client.py`

```python
"""F1 전용 Pinecone 클라이언트 — samc-law-f1, 비동기 병렬 검색"""
from __future__ import annotations
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from pinecone import Pinecone

_client: Pinecone | None = None
_index = None
_executor = ThreadPoolExecutor(max_workers=8)

def get_index():
    global _client, _index
    if _index is None:
        _client = Pinecone(api_key=os.environ["F1_PINECONE_API_KEY"])
        _index = _client.Index(os.environ.get("F1_PINECONE_INDEX", "samc-law-f1"))
    return _index

def search_sync(query_vector: list[float], namespace: str, top_k: int) -> list[dict]:
    res = get_index().query(
        vector=query_vector,
        top_k=top_k,
        namespace=namespace,
        include_metadata=True,
    )
    return [
        {
            "id": m.id,
            "score": m.score,
            "text": m.metadata.get("text", ""),
            "regulation_id": m.metadata.get("regulation_id"),
            "section_path": m.metadata.get("section_path"),
            "namespace": namespace,
        }
        for m in res.matches
    ]

async def search_multi(
    query_vector: list[float],
    namespaces: list[str],
    top_k_per_ns: int = 5,
) -> list[dict]:
    """여러 namespace 병렬 검색 → 점수 기준 통합 정렬"""
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(_executor, search_sync, query_vector, ns, top_k_per_ns)
        for ns in namespaces
    ]
    results = await asyncio.gather(*tasks)
    flat = [hit for sub in results for hit in sub]
    flat.sort(key=lambda h: h["score"], reverse=True)
    return flat
```

### 3.3 `backend/services/f1_rag_judge.py`

```python
"""F1 RAG 판정 — 임베딩 → Pinecone(병렬) → OpenAI(JSON mode)

run_feature1()의 Step 0이 미적중일 때만 호출되어야 함 (호출처 책임).
실패 시 `RagJudgement(rag_verdict="error", ...)` 반환 — 호출처가 HITL 충돌 처리.
"""
from __future__ import annotations
import os
from backend.services import f1_openai_client, f1_pinecone_client
from backend.models.f1_law_citation import LawCitation, RagJudgement

DEFAULT_NAMESPACES = [
    "food_code_text",
    "additive_code_text",
    "functional_labeling",
    "temporary_standard",
    "health_food_text",
]

SYSTEM_PROMPT = """\
당신은 식품 수입 판정 전문가입니다. 사용자가 제공한 제품 정보와 아래 법령 청크를
근거로 다음을 JSON으로 응답하세요.

응답 스키마:
{
  "rag_verdict": "permitted" | "restricted" | "prohibited" | "unidentified",
  "rag_reasoning": "한국어 2~4문장",
  "cited_chunk_ids": ["id1", "id2"]
}

원칙:
- 법령 청크에 직접 근거가 있는 경우만 verdict를 결정하세요.
- 청크 컨텍스트로 판단 불가 시 verdict="unidentified".
- 학습 데이터에 의존한 추측 금지.
- cited_chunk_ids는 reasoning에 실제 인용한 청크 id만 포함.
"""

def _build_query_text(payload: dict) -> str:
    parts = []
    if name := payload.get("product_name"):
        parts.append(f"제품명: {name}")
    if ings := payload.get("ingredients"):
        names = [i.get("name", "") for i in ings] if isinstance(ings[0], dict) else ings
        parts.append(f"원료: {', '.join(names)}")
    if ftype := payload.get("food_type"):
        parts.append(f"식품유형: {ftype}")
    return "\n".join(parts) or "정보 없음"

async def run(payload: dict) -> RagJudgement:
    """실패 시 verdict='error'로 반환 (예외 던지지 않음)"""
    try:
        query_text = _build_query_text(payload)
        [vector] = f1_openai_client.embed([query_text])

        top_k = int(os.environ.get("F1_RAG_TOP_K", "5"))
        hits = await f1_pinecone_client.search_multi(
            vector, DEFAULT_NAMESPACES, top_k_per_ns=top_k,
        )
        hits = hits[: top_k * 2]  # 통합 후 상위 2K

        context = "\n\n".join(
            f"[id={h['id']}] [{h['namespace']} / {h['section_path']}]\n{h['text']}"
            for h in hits
        )
        user_msg = f"=== 제품 정보 ===\n{query_text}\n\n=== 법령 청크 ===\n{context}"

        parsed = f1_openai_client.chat_json(SYSTEM_PROMPT, user_msg)
        cited_ids = set(parsed.get("cited_chunk_ids") or [])
        citations = [
            LawCitation(
                chunk_id=h["id"],
                namespace=h["namespace"],
                regulation_id=h["regulation_id"],
                section_path=h["section_path"],
                text=h["text"],
                score=h["score"],
            )
            for h in hits if h["id"] in cited_ids
        ]
        return RagJudgement(
            rag_verdict=parsed.get("rag_verdict") or "unidentified",
            rag_reasoning=parsed.get("rag_reasoning") or "",
            law_citations=citations,
        )
    except Exception as exc:  # noqa: BLE001
        return RagJudgement(
            rag_verdict="error",
            rag_reasoning=f"RAG 호출 실패: {exc}",
            law_citations=[],
        )
```

### 3.4 `backend/services/f1_chunking.py`

newsamc `chunking-service.ts` Python 포팅. 핵심 함수만 명시 (구현은 Phase 3-1).

| 함수 | 입력 | 출력 |
|---|---|---|
| `split_by_article(markdown)` | `str` | `list[dict]` (text, section_path) |
| `count_tokens(text)` | `str` | `int` (`tiktoken cl100k_base`) |
| `merge_small_chunks(chunks)` | `list` | `list` (200~1500 정규화) |
| `split_large_chunk(chunk)` | `dict` | `list` (`①②③` 분할 또는 슬라이딩) |
| `attach_metadata(chunks, regulation_id, namespace)` | ... | `list[dict]` (vector_id 부여) |

상수:
```python
MIN_CHUNK_TOKENS = 200
MAX_CHUNK_TOKENS = 1500
OVERLAP_TOKENS = 200
EMBED_BATCH_SIZE = 100
PINECONE_BATCH_SIZE = 100
```

### 3.5 `backend/models/f1_law_citation.py`

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel

RagVerdict = Literal["permitted", "restricted", "prohibited", "unidentified", "error"]
ConflictStatus = Literal["agreed", "conflict", "rag_supplemented", "rag_unavailable", "rag_skipped"]

class LawCitation(BaseModel):
    chunk_id: str
    namespace: str
    regulation_id: str | None = None
    section_path: str | None = None
    text: str
    score: float

class RagJudgement(BaseModel):
    rag_verdict: RagVerdict
    rag_reasoning: str
    law_citations: list[LawCitation]
```

## 4. 수정 파일

### 4.1 `backend/services/feature1.py` — 시그니처 확장

**원칙**: 기존 `run_feature1()` 시그니처와 `Feature1Output` 모델은 유지. RAG 결과는 별도 반환값으로 분리.

```python
from __future__ import annotations
from typing import Optional
from models.judgment import (Feature1Output, Ingredient, LawReference,
                             ProcessConditions)
from services.step1_ingredients_check import run_step1
from services.step3_standards import run_step3
from services import f1_rag_judge  # 신규
from models.f1_law_citation import RagJudgement, ConflictStatus  # 신규

# 기존 run_feature1 그대로 유지 (별도 변경 없음)
def run_feature1(
    ingredients: list[Ingredient],
    food_type: Optional[str] = None,
    process_conditions: Optional[ProcessConditions] = None,
) -> Feature1Output:
    # ... 기존 코드 그대로 ...
    pass

# 신규: RAG 통합 entry
async def run_feature1_with_rag(
    ingredients: list[Ingredient],
    food_type: Optional[str] = None,
    process_conditions: Optional[ProcessConditions] = None,
    payload_for_rag: dict | None = None,  # 라우터가 원본 payload 전달
) -> tuple[Feature1Output, RagJudgement | None, ConflictStatus]:
    """기존 run_feature1 + RAG + HITL 비교"""
    out = run_feature1(ingredients, food_type, process_conditions)

    # Step 0 적중 시 RAG 미호출 (금지원료 절대 우선)
    if out.forbidden_hits:
        return out, None, "rag_skipped"

    # RAG 호출 (실패해도 예외 안 던짐)
    rag = await f1_rag_judge.run(payload_for_rag or {
        "ingredients": [i.name for i in ingredients],
        "food_type": food_type,
    })

    if rag.rag_verdict == "error":
        return out, rag, "rag_unavailable"

    # exact_verdict 추출 (Feature1Output에서 도출)
    exact_verdict = _derive_exact_verdict(out)

    # HITL 비교
    if exact_verdict == "unidentified" and rag.rag_verdict in ("permitted", "restricted", "prohibited"):
        conflict = "rag_supplemented"
    elif exact_verdict == rag.rag_verdict:
        conflict = "agreed"
    else:
        conflict = "conflict"

    return out, rag, conflict


def _derive_exact_verdict(out: Feature1Output) -> str:
    """Feature1Output에서 단일 verdict 도출 (HITL 비교용)"""
    if out.forbidden_hits:
        return "prohibited"
    agg = out.aggregation
    if agg is None:
        return "unidentified"
    if agg.prohibited > 0:
        return "prohibited"
    if agg.unidentified > 0 and agg.permitted == 0:
        return "unidentified"
    if agg.restricted > 0:
        return "restricted"
    if agg.permitted > 0:
        return "permitted"
    return "unidentified"
```

### 4.2 `backend/routers/feature1.py` — `_to_pipeline_result` 수정 + run 엔드포인트 통합

#### 4.2.1 `_to_pipeline_result()` 시그니처 확장

```python
def _to_pipeline_result(
    out: Feature1Output,
    rag: RagJudgement | None = None,
    conflict_status: str = "rag_skipped",
) -> dict:
    # ... 기존 ingredients_slim, fail_reasons, standards_slim 빌드 (변경 없음) ...

    base = {
        "ingredients": ingredients_slim,
        "verdict": "수입가능" if out.import_possible else "수입불가",
        "import_possible": out.import_possible,
        "fail_reasons": fail_reasons,
        "standards_check": standards_slim,
        "_internal": {
            # 기존 필드 유지
            "aggregation": out.aggregation.model_dump() if out.aggregation else None,
            "conditional_evaluations": [e.model_dump() for e in out.conditional_evaluations],
            "forbidden_hits": [h.model_dump() for h in out.forbidden_hits],
            "escalations": out.escalations,
            "law_refs": [r.model_dump() for r in out.law_refs],
            # ─── 신규 RAG 필드 ───
            "rag_verdict": rag.rag_verdict if rag else None,
            "rag_reasoning": rag.rag_reasoning if rag else None,
            "law_citations": [c.model_dump() for c in rag.law_citations] if rag else [],
            "conflict_status": conflict_status,
        },
    }
    return base
```

#### 4.2.2 run 엔드포인트 — HITL status 결정

```python
@router.post("/{case_id}/pipeline/feature/1/run")
async def run_feature1_endpoint(
    case_id: str,
    body: Feature1RunRequest,
) -> dict:
    # ... 기존 ingredients/process_conditions 추출 (변경 없음) ...

    try:
        out, rag, conflict = await run_feature1_with_rag(
            ingredients=ingredients,
            food_type=body.food_type,
            process_conditions=process_conditions or ProcessConditions(),
            payload_for_rag={
                "ingredients": [i.name for i in ingredients],
                "food_type": body.food_type,
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail={
            "error": "FEATURE1_RUN_FAILED",
            "message": f"기능1 실행 실패: {exc}",
            "feature": 1,
        })

    ai_result = _to_pipeline_result(out, rag, conflict)

    # HITL: 충돌 또는 RAG 보강이면 needs_review, 그 외 waiting_review
    new_status = "needs_review" if conflict in ("conflict", "rag_supplemented") else "waiting_review"
    _upsert_pipeline_step(case_id, new_status, ai_result)

    return {
        "case_id": case_id,
        "status": new_status,
        "ai_result": ai_result,
    }
```

> **참고**: 라우터 함수가 `async def`로 변경됨 (`run_feature1_with_rag`가 코루틴). FastAPI가 자동 처리. 다른 엔드포인트(GET, PATCH, confirm, report)는 sync 유지 가능.

### 4.3 `backend/routers/admin_law_update.py` — F1 전처리 교체

#### 4.3.1 `_get_f1_clients()` 교체

```python
def _get_f1_clients() -> dict:
    """F1 전처리용 클라이언트 (RAG: OpenAI + Pinecone + Supabase)."""
    if "F1" in _feature_clients:
        return _feature_clients["F1"]

    from openai import OpenAI
    from pinecone import Pinecone
    from supabase import create_client

    api_key = os.getenv("F1_OPENAI_API_KEY")
    pinecone_key = os.getenv("F1_PINECONE_API_KEY")
    if not api_key or not pinecone_key:
        raise RuntimeError("F1_OPENAI_API_KEY 또는 F1_PINECONE_API_KEY 미설정")

    clients = {
        "openai": OpenAI(api_key=api_key),
        "index": Pinecone(api_key=pinecone_key).Index(
            os.getenv("F1_PINECONE_INDEX", "samc-law-f1")
        ),
        "supabase": create_client(
            os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY")
        ),
    }
    _feature_clients["F1"] = clients
    return clients
```

#### 4.3.2 `_run_f1_preprocess()` 교체 — Claude 추출 → RAG 임베딩

```python
async def _run_f1_preprocess(
    tmp_path: Path,
    law_name: str,
    progress_callback=None,
) -> dict:
    """F1 전처리: PDF → markdown → 청킹 → OpenAI 임베딩 → Pinecone + 미러"""
    clients = _get_f1_clients()

    if progress_callback:
        await progress_callback("F1", law_name, "chunking", 10)

    # 청크 생성 — utils.chunker 재사용 (이미 PDF→markdown 함수 존재)
    from utils.chunker import pdf_to_markdown
    from services.f1_chunking import (
        split_by_article, merge_small_chunks, attach_metadata,
    )
    md_text = pdf_to_markdown(str(tmp_path))
    raw = split_by_article(md_text)
    normalized = merge_small_chunks(raw)
    namespace = _law_name_to_namespace(law_name)
    regulation_id = f"{namespace}_{law_name}_{int(__import__('time').time())}"
    chunks = attach_metadata(normalized, regulation_id, namespace)

    if progress_callback:
        await progress_callback("F1", law_name, "embedding", 30)

    # 임베딩 + upsert + 미러
    from services.f1_openai_client import embed
    vectors = []
    for i in range(0, len(chunks), 100):
        batch = chunks[i:i+100]
        embeds = embed([c["text"] for c in batch])
        for c, e in zip(batch, embeds):
            vectors.append({
                "id": c["vector_id"],
                "values": e,
                "metadata": {**c["metadata"], "text": c["text"][:4000]},
            })
        if progress_callback:
            pct = 30 + int(50 * (i + len(batch)) / len(chunks))
            await progress_callback("F1", law_name, "embedding", pct)

    for i in range(0, len(vectors), 100):
        clients["index"].upsert(vectors=vectors[i:i+100], namespace=namespace)

    rows = [{
        "vector_id": v["id"],
        "regulation_id": regulation_id,
        "pinecone_namespace": namespace,
        "section_path": v["metadata"].get("section_path"),
        "text": v["metadata"].get("text", ""),
        "token_count": v["metadata"].get("token_count"),
        "chunk_index": v["metadata"].get("chunk_index"),
        "total_chunks": v["metadata"].get("total_chunks"),
    } for v in vectors]
    clients["supabase"].table("f1_law_chunks").upsert(rows, on_conflict="vector_id").execute()

    if progress_callback:
        await progress_callback("F1", law_name, "done", 100)

    return {
        "feature": "F1",
        "law_name": law_name,
        "status": "success",
        "embedded_count": len(vectors),
        "namespace": namespace,
    }


_LAW_NAME_TO_NAMESPACE = {
    "식품공전": "food_code_text",
    "식품첨가물공전": "additive_code_text",
    "건강기능식품공전": "health_food_text",
    "식품등의 한시적 기준 및 규격 인정 기준": "temporary_standard",
}

def _law_name_to_namespace(law_name: str) -> str:
    if law_name not in _LAW_NAME_TO_NAMESPACE:
        raise RuntimeError(f"F1 namespace 매핑 없음: {law_name}")
    return _LAW_NAME_TO_NAMESPACE[law_name]
```

#### 4.3.3 `LAW_FEATURE_MAP` — F1 매핑은 그대로 유지

식품공전, 식품첨가물공전, 건강기능식품공전, 한시적 기준의 `features`에 "F1" 유지. 함수 내부만 RAG로 교체되었으므로 매핑 테이블 변경 불필요.

### 4.4 `backend/utils/chunker.py:14` — 주석 정리

```diff
- # ... law_extractor 참조 주석 ...
+ # F1 RAG 도입(2026-04): chunker 자체는 유지되나 law_extractor 호출은 제거됨
```

### 4.5 폐기

| 항목 | 처리 |
|---|---|
| `backend/services/law_extractor.py` | `git rm` |
| `extract_thresholds_bulk` 호출처 | grep 후 모두 제거 (현재는 `admin_law_update._run_f1_preprocess` 1곳만 확인됨, 위 4.3.2에서 교체) |
| `F1_ANTHROPIC_API_KEY` | `.env.example`, `MERGE_GUIDE.md`, `admin_law_update._get_f1_clients`에서 모두 제거 |
| 관련 테스트 (`tests/services/test_law_extractor*.py` 등) | 삭제 |

## 5. API 엔드포인트 (변경 없음, 응답 구조만 확장)

| Method | Path | 변경 |
|---|---|---|
| POST | `/api/v1/cases/{case_id}/pipeline/feature/1/run` | 응답 `ai_result._internal`에 RAG 필드 추가, `status`가 `needs_review` 가능 |
| GET | `/api/v1/cases/{case_id}/pipeline/feature/1` | 응답 ai_result 동일 구조 |
| PATCH | `/api/v1/cases/{case_id}/pipeline/feature/1` | 변경 없음 — 사람이 final_result 결정 시 사용 |
| POST | `/api/v1/cases/{case_id}/pipeline/feature/1/confirm` | 변경 없음 |
| GET | `/api/v1/cases/{case_id}/pipeline/feature/1/report` | PDF에 RAG 인용 섹션 추가 (Phase 5에서) |

## 6. 에러 처리

| 케이스 | 처리 |
|---|---|
| Pinecone 호출 실패 | `f1_rag_judge.run()` 내부에서 catch → `RagJudgement(verdict="error")` 반환 → conflict_status="rag_unavailable", status="waiting_review" (degraded) |
| OpenAI 호출 실패 | 동일 |
| OpenAI JSON 파싱 실패 | `chat_json()` 내 `json.loads` 실패 → 동일 처리 (try/except 추가) |
| 임베딩 빈 입력 | `_build_query_text` 폴백 "정보 없음" |
| Pinecone 결과 0건 | RAG가 unidentified로 응답 → conflict_status는 일치/불일치 따라 분기 |

## 7. 캐싱 (Phase 5 후 검토)

| 옵션 | 설명 |
|---|---|
| 없음 | 매번 호출 (default, 안전) |
| 임베딩만 캐싱 | `(query_hash) → vector` Redis/in-mem |
| 전체 캐싱 | `(payload_hash) → response` Redis 1시간 TTL |

## 8. 테스트 전략

| 레벨 | 대상 |
|---|---|
| Unit | `f1_chunking.py` (병합/분할 경계), `f1_pinecone_client` (mock) |
| Integration | `f1_rag_judge.run()` (실제 Pinecone + OpenAI, 테스트 인덱스) |
| Golden | **30건+** 사전 결정된 케이스, 조건부 케이스 비율 ≥ 40% — Claude 시절 결과 vs OpenAI 결과 일치율 측정 |
| 성능 | p50/p95 응답 시간, OpenAI 비용/요청, search_multi 병렬 효과 측정 |

## 9. 컨벤션 체크

- [x] `F1_` prefix env
- [x] `f1_*` 테이블만 신설 (`f1_law_chunks`)
- [x] `samc-law-f1` 자기 인덱스만
- [x] 기존 `Feature1Output` 시그니처 유지 (별도 entry로 RAG 통합)
- [x] 기존 `_to_pipeline_result()` 함수에 파라미터 추가 (default로 후방 호환)
- [x] `admin_law_update.LAW_FEATURE_MAP` 매핑 유지 (운영 흐름 보존)
- [x] Supabase 공용 키 사용
