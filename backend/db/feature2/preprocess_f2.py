"""
F2 전처리 — 단일 법령 파일(PDF/HWPX) 진입점.

`/admin/law-update` UI에서 F2 관련 법령 업로드 시 호출되는 단일 진입점.
F4 선례(`backend/db/feature4/preprocess_laws.py:preprocess_single_law`)의 구조를 차용.

Phase 3 Sprint 2 구현 (2026-04-17):
    - run_f2_preprocess: 텍스트 추출 → 청킹 → OpenAI 임베딩 → Pinecone(samc-a) upsert
    - upload_f2_food_type_classification: 식품공전 제5장 전용 Supabase 배치 insert
    - upload_foodtype_chunks: f2_food_types 테이블 → Pinecone 소분류 재임베딩 (관리 전용)

Node → Python 이관 출처:
    - backend/db/feature2/preprocessing/upload_foodcode5_full.js (Supabase 부분)
    - backend/db/feature2/preprocessing/upload_foodtype_chunks.js

Python 참조 패턴:
    - backend/db/feature2/scripts/step1_extract.py (pdfplumber)
    - backend/db/feature2/scripts/step3_chunk.py (조문/크기 청킹)
    - backend/db/feature2/scripts/step5_upload_pinecone.py (MD5 ID, 배치 upsert)

참조 문서: .omc/research/f2_node_to_py_map.md
"""

import asyncio
import hashlib
import re
import zipfile
from pathlib import Path
from typing import Any, Callable, Optional
from xml.etree import ElementTree as ET

import pdfplumber


# ── 상수 ────────────────────────────────────────────────────
EMBED_MODEL = "text-embedding-3-small"
EMBED_BATCH = 100
UPSERT_BATCH = 100
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
MIN_ARTICLE_CHARS = 100
MIN_FALLBACK_CHARS = 50
ARTICLE_FALLBACK_THRESHOLD = 5  # 조문 청크 수가 이 미만이면 크기 기준으로 전환


# law_name → Pinecone metadata.category
# F1 router의 _search_pinecone가 metadata.category 필터링에 의존하므로
# 기존 Node 업로드와 동일한 값을 사용해야 함 (step3_chunk.py의 PINECONE_FILES 참조).
_CATEGORY_MAP = {
    "식품공전": "food_standard",
    "식품첨가물공전": "additive",
    "식품유형 분류원칙": "food_type",
    "주세법 시행령": "alcohol",
    "기구및용기포장공전": "container",
    "건강기능식품공전": "health_food",
}


# ──────────────────────────────────────────────────────────
# 텍스트 추출
# ──────────────────────────────────────────────────────────

def _extract_text_auto(file_path: Path) -> str:
    """PDF/HWPX 자동 분기 텍스트 추출."""
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        return _extract_pdf(file_path)
    if ext == ".hwpx":
        return _extract_hwpx(file_path)
    raise ValueError(f"지원하지 않는 형식: {ext} (지원: .pdf, .hwpx)")


def _extract_pdf(pdf_path: Path) -> str:
    """pdfplumber로 본문 + 표 추출 (step1_extract.py 패턴)."""
    parts: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                parts.append(text)
            for table in page.extract_tables() or []:
                for row in table:
                    cleaned = [str(cell).strip() if cell else "" for cell in row]
                    parts.append("\t".join(cleaned))
    return "\n".join(parts)


_HWPX_SECTION_RE = re.compile(r"Contents/section\d+\.xml")
_HWPX_SECTION_NUM_RE = re.compile(r"\d+")
_HWPX_T_FALLBACK_RE = re.compile(r"<(?:[^:]+:)?t[^>]*>([^<]+)</")


def _extract_hwpx(hwpx_path: Path) -> str:
    """
    HWPX → 텍스트 (ZIP + XML <hp:t> 수집).

    F2 RAG 용도에 충분한 간이 추출. F4의 preprocess_laws는 torch/sentence_transformers
    의존성 때문에 import 비용이 커서 여기서는 재사용하지 않음.
    """
    if not zipfile.is_zipfile(hwpx_path):
        raise ValueError(f"유효한 HWPX 파일이 아닙니다: {hwpx_path}")

    lines: list[str] = []
    with zipfile.ZipFile(hwpx_path, "r") as z:
        section_files = sorted(
            [f for f in z.namelist() if _HWPX_SECTION_RE.match(f)],
            key=lambda x: int(_HWPX_SECTION_NUM_RE.search(x).group()),
        )
        if not section_files:
            raise ValueError(f"HWPX 내 section 파일 없음: {hwpx_path}")

        for name in section_files:
            raw = z.read(name)
            try:
                root = ET.fromstring(raw)
                for elem in root.iter():
                    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                    if tag == "t" and elem.text:
                        lines.append(elem.text)
            except ET.ParseError:
                lines.extend(_HWPX_T_FALLBACK_RE.findall(
                    raw.decode("utf-8", errors="ignore")
                ))

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────
# 청킹 (step3_chunk.py 패턴 포팅)
# ──────────────────────────────────────────────────────────

_ARTICLE_SPLIT_RE = re.compile(
    "|".join([
        r"(?=제\s*\d+\s*조)",
        r"(?=\d+\.\s+[가-힣])",
        r"(?=○\s)",
        r"(?=◆\s)",
        r"(?=■\s)",
        r"(?=[①②③④⑤⑥⑦⑧⑨⑩])",
    ])
)


def _chunk_by_article(text: str, law_name: str, category: str) -> list[dict]:
    """조문/항목 단위 청킹. 100자 미만 조각은 이전 청크에 병합."""
    parts = _ARTICLE_SPLIT_RE.split(text)

    chunks: list[dict] = []
    for i, part in enumerate(parts):
        part = part.strip()
        if len(part) < MIN_ARTICLE_CHARS:
            if chunks:
                chunks[-1]["text"] += " " + part
            continue
        chunks.append(_make_chunk_dict(law_name, category, i, part))
    return chunks


def _chunk_by_size(
    text: str,
    law_name: str,
    category: str,
    size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[dict]:
    """크기 기준 sliding window 청킹 (조문 분할 실패 시 fallback)."""
    chunks: list[dict] = []
    start = 0
    index = 0
    while start < len(text):
        end = min(start + size, len(text))
        part = text[start:end].strip()
        if len(part) >= MIN_FALLBACK_CHARS:
            chunks.append(_make_chunk_dict(law_name, category, index, part))
            index += 1
        start += size - overlap
    return chunks


def _make_chunk_dict(law_name: str, category: str, idx: int, text: str) -> dict:
    return {
        "id": f"{law_name}_{idx:04d}",
        "text": text,
        "metadata": {
            "law": law_name,
            "category": category,
            "chunk_index": idx,
            "char_count": len(text),
        },
    }


# ──────────────────────────────────────────────────────────
# 식품공전 제5장 파싱 (Node upload_foodcode5_full.js 포팅)
# 파일명 패턴 "N. 분류명.pdf" (예: "1. 과자류, 빵류 또는 떡류.pdf")
# ──────────────────────────────────────────────────────────

_CATEGORY_FILENAME_RE = re.compile(r"^(\d+)\.\s+(.+)$")
_CATEGORY_DEF_RE = re.compile(
    r"1\)\s*정의\s*([\s\S]*?)(?=\s*2\)\s*원료|\s*3\)\s*제조)"
)
_FOOD_TYPE_SECTION_RE = re.compile(
    r"4\)\s*식품유형\s*([\s\S]*?)"
    r"(?=\s*5\)\s*규격|\s*5\.\s*규격|\s*\d+-\d+\s|\s*\d+\.\s+\S|$)"
)
_TYPE_SPLIT_RE = re.compile(r"\n\s*\((\d+)\)\s+")
_TYPE_NAME_COLON_RE = re.compile(r"[∶:]")

_INVALID_TYPE_KEYWORDS = (
    "보존료", "검출", "g/kg", "v/v", "w/w", "클로스트리디움",
    "장출혈성", "살모넬라", "대장균", "에탄올(v/v%)", "황색포도상구균",
)


def _parse_category_from_filename(filename: str) -> Optional[dict]:
    base = Path(filename).stem
    m = _CATEGORY_FILENAME_RE.match(base)
    if not m:
        return None
    return {"no": m.group(1).strip(), "name": m.group(2).strip()}


def _extract_category_definition(text: str) -> str:
    m = _CATEGORY_DEF_RE.search(text)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip()[:2000]


def _extract_food_type_sections(text: str) -> list[str]:
    return [m.group(1) for m in _FOOD_TYPE_SECTION_RE.finditer(text)]


def _parse_types_from_section(section_text: str) -> list[dict]:
    """
    Node parseTypesFromSection 포팅:
    \\n 프리픽스 + "(N) " 구분자로 split → 홀수 인덱스는 번호, 다음 인덱스는 내용.
    """
    parts = _TYPE_SPLIT_RE.split("\n" + section_text)
    types: list[dict] = []

    for idx in range(1, len(parts), 2):
        content = parts[idx + 1] if idx + 1 < len(parts) else ""
        nl = content.find("\n")
        type_name = (content[:nl] if nl >= 0 else content).strip()
        definition = content[nl + 1:] if nl >= 0 else ""
        definition = re.sub(r"\s+", " ", definition).strip()[:2000]

        # 콜론(∶/:) 이전까지만 type_name으로 사용
        colon = _TYPE_NAME_COLON_RE.search(type_name)
        if colon and colon.start() > 0:
            type_name = type_name[:colon.start()].strip()

        if not type_name or len(type_name) < 2 or len(type_name) > 30:
            continue
        if any(kw in type_name for kw in _INVALID_TYPE_KEYWORDS):
            continue

        types.append({"type_name": type_name, "definition": definition})
    return types


def _parse_foodcode5_file(file_path: Path) -> list[dict]:
    """
    식품공전 제5장 단일 PDF → f2_food_type_classification 행 목록.

    파일명이 "N. 이름.pdf" 패턴이 아니면 빈 리스트 반환 (전체본 업로드 등).
    """
    cat = _parse_category_from_filename(file_path.name)
    if not cat:
        return []

    text = _extract_pdf(file_path)
    category_def = _extract_category_definition(text)
    sections = _extract_food_type_sections(text)

    all_types: list[dict] = []
    for sec in sections:
        all_types.extend(_parse_types_from_section(sec))

    base = {
        "category_no": cat["no"],
        "category_name": cat["name"],
        "category_definition": category_def,
        "law_source": "식품공전 제5장",
    }

    if not all_types:
        return [{**base, "type_name": cat["name"], "definition": category_def}]

    return [
        {**base, "type_name": t["type_name"], "definition": t["definition"]}
        for t in all_types
    ]


# ──────────────────────────────────────────────────────────
# Pinecone 업로드 공통
# ──────────────────────────────────────────────────────────

def _make_ascii_id(prefix: str, chunk_id: str) -> str:
    """Pinecone ID는 ASCII 제약 → MD5 해시로 변환 (step5_upload_pinecone 패턴)."""
    return hashlib.md5(f"{prefix}::{chunk_id}".encode("utf-8")).hexdigest()


def _embed_batch(openai_client, texts: list[str]) -> list[list[float]]:
    """OpenAI text-embedding-3-small 배치 임베딩."""
    resp = openai_client.embeddings.create(
        model=EMBED_MODEL,
        input=[t[:8000] for t in texts],
    )
    return [d.embedding for d in resp.data]


def _upsert_chunks_to_pinecone(
    chunks: list[dict],
    id_prefix: str,
    index,
    openai_client,
) -> int:
    """청크 목록 → 배치 임베딩 → Pinecone upsert. 업로드된 벡터 수 반환."""
    uploaded = 0
    for i in range(0, len(chunks), EMBED_BATCH):
        batch = chunks[i : i + EMBED_BATCH]
        vectors_raw = _embed_batch(openai_client, [c["text"] for c in batch])
        records = [
            {
                "id": _make_ascii_id(id_prefix, c["id"]),
                "values": vec,
                "metadata": {**c["metadata"], "text": c["text"][:1000]},
            }
            for c, vec in zip(batch, vectors_raw)
        ]
        for j in range(0, len(records), UPSERT_BATCH):
            index.upsert(vectors=records[j : j + UPSERT_BATCH])
        uploaded += len(records)
    return uploaded


# ──────────────────────────────────────────────────────────
# Supabase 업로드 (식품공전 전용)
# ──────────────────────────────────────────────────────────

def upload_f2_food_type_classification(
    file_path: Path,
    supabase_client,
) -> int:
    """
    식품공전 제5장 단일 PDF → f2_food_type_classification 배치 insert.

    Node `upload_foodcode5_full.js`의 Supabase 업로드 부분 이관.
    파일명이 "N. 이름.pdf" 패턴이 아니면 0 반환 (에러 아님 — 모든 업로드가 제5장인 건 아님).

    Args:
        file_path: 업로드된 PDF 파일
        supabase_client: Supabase client

    Returns:
        insert된 행 수 (파싱 실패 시 0)
    """
    rows = _parse_foodcode5_file(file_path)
    if not rows:
        return 0

    BATCH = 50
    inserted = 0
    for i in range(0, len(rows), BATCH):
        batch = rows[i : i + BATCH]
        supabase_client.table("f2_food_type_classification").insert(batch).execute()
        inserted += len(batch)
    return inserted


# ──────────────────────────────────────────────────────────
# 메인 진입점
# ──────────────────────────────────────────────────────────

async def run_f2_preprocess(
    file_path: Path,
    law_name: str,
    index: Any,
    supabase_client: Any,
    openai_client: Any,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """
    F2 전처리 단일 진입점.

    Args:
        file_path: 업로드된 법령 파일 (PDF 또는 HWPX)
        law_name: 법령 공식 명칭 (LAW_FEATURE_MAP의 key)
        index: Pinecone Index 객체 (samc-a)
        supabase_client: Supabase client
        openai_client: OpenAI client (임베딩용)
        progress_callback: async (feature, law_name, stage, percent) → None

    Returns:
        {
            "feature": "F2",
            "law_name": str,
            "status": "success",
            "total_chunks": int,
            "supabase_rows_inserted": int,  # 식품공전 제5장 개별 파일일 때만 > 0
        }

    Raises:
        ValueError: 지원하지 않는 확장자 / 텍스트 추출 실패 / 청킹 결과 0
    """
    category = _CATEGORY_MAP.get(law_name, "general")

    # 1. 텍스트 추출
    if progress_callback:
        await progress_callback("F2", law_name, "extracting", 10)
    text = await asyncio.to_thread(_extract_text_auto, file_path)
    if not text.strip():
        raise ValueError(f"텍스트 추출 결과 비어 있음: {file_path.name}")

    # 2. 청킹 (조문 우선, 5개 미만이면 크기 기준 fallback)
    if progress_callback:
        await progress_callback("F2", law_name, "chunking", 40)
    chunks = _chunk_by_article(text, law_name, category)
    if len(chunks) < ARTICLE_FALLBACK_THRESHOLD:
        chunks = _chunk_by_size(text, law_name, category)
    if not chunks:
        raise ValueError(f"청킹 결과 0: {file_path.name}")

    # 3. Pinecone upsert (blocking I/O → 이벤트 루프 양보)
    if progress_callback:
        await progress_callback("F2", law_name, "pinecone_upload", 70)
    id_prefix = f"{law_name}::{file_path.stem}"
    total_chunks = await asyncio.to_thread(
        _upsert_chunks_to_pinecone, chunks, id_prefix, index, openai_client
    )

    # 4. 식품공전일 때만 Supabase f2_food_type_classification insert
    supabase_rows = 0
    if law_name == "식품공전":
        if progress_callback:
            await progress_callback("F2", law_name, "supabase_upload", 90)
        try:
            supabase_rows = await asyncio.to_thread(
                upload_f2_food_type_classification, file_path, supabase_client
            )
        except Exception as e:
            # Pinecone은 이미 성공했으므로 Supabase 실패는 경고만 — 전체 실패 처리하지 않음
            print(f"[WARN] f2_food_type_classification insert failed ({law_name}): {e}")

    if progress_callback:
        await progress_callback("F2", law_name, "done", 100)

    return {
        "feature": "F2",
        "law_name": law_name,
        "status": "success",
        "total_chunks": total_chunks,
        "supabase_rows_inserted": supabase_rows,
    }


# ──────────────────────────────────────────────────────────
# f2_food_types → Pinecone 재임베딩 (관리 전용, 업로드 플로우와 독립)
# Node upload_foodtype_chunks.js 이관
# ──────────────────────────────────────────────────────────

def _build_foodtype_chunk_text(row: dict) -> str:
    """f2_food_types 1행 → Pinecone 청크 텍스트."""
    lines = [
        f"식품유형: {row.get('type_name', '')}",
        f"분류: {row.get('category_name', '')}",
    ]
    if row.get("definition"):
        lines.append(f"정의: {row['definition'][:800]}")
    if row.get("category_definition"):
        lines.append(f"카테고리 설명: {row['category_definition'][:400]}")
    return "\n".join(lines)


def upload_foodtype_chunks(
    supabase_client,
    openai_client,
    index,
) -> int:
    """
    f2_food_types 테이블 전체 → 소분류 청크 생성 → Pinecone upsert.

    Node `upload_foodtype_chunks.js` 이관. 관리 전용 — 업로드 플로우와 독립.
    별도 관리 엔드포인트에서 수동 트리거해야 함 (Sprint 2에서는 엔드포인트 미등록).

    ID 규칙은 Node와 동일: md5(f"f2_food_type::{category_no}::{type_name}")
    → 재실행 시 같은 ID로 upsert되어 자동 덮어쓰기.

    Returns:
        Pinecone에 upsert된 벡터 수
    """
    res = (
        supabase_client.table("f2_food_types")
        .select("*")
        .order("category_no")
        .execute()
    )
    rows = res.data or []
    if not rows:
        return 0

    uploaded = 0
    for i in range(0, len(rows), EMBED_BATCH):
        batch = rows[i : i + EMBED_BATCH]
        texts = [_build_foodtype_chunk_text(r) for r in batch]
        vectors_raw = _embed_batch(openai_client, texts)

        records = []
        for row, text, vec in zip(batch, texts, vectors_raw):
            raw_id = f"f2_food_type::{row.get('category_no', '')}::{row.get('type_name', '')}"
            records.append({
                "id": hashlib.md5(raw_id.encode("utf-8")).hexdigest(),
                "values": vec,
                "metadata": {
                    "law": "식품공전",
                    "category": "food_type",
                    "category_no": str(row.get("category_no", "")),
                    "category_name": row.get("category_name", "") or "",
                    "food_group": row.get("category_name", "") or "",
                    "type_name": row.get("type_name", "") or "",
                    "type_code": row.get("type_code", "") or "",
                    "source": row.get("source", "") or "식품공전 제5장",
                    "text": text[:1000],
                },
            })

        for j in range(0, len(records), UPSERT_BATCH):
            index.upsert(vectors=records[j : j + UPSERT_BATCH])
        uploaded += len(records)

    return uploaded
