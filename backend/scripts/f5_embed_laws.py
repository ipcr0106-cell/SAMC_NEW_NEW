"""
법령 PDF → Pinecone f5-law-chunks 임베딩 스크립트

사용법:
  python scripts/embed_laws.py            # 임베딩 실행
  python scripts/embed_laws.py --dry-run  # 대상 PDF 목록만 출력
  python scripts/embed_laws.py --check    # 저장된 청크 수 확인
  python scripts/embed_laws.py --reset    # 기존 청크 삭제 후 재임베딩
"""

import argparse
import os
import sys
import hashlib
from pathlib import Path

import pdfplumber
import voyageai
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

# backend/ 기준으로 경로 설정
ROOT = Path(__file__).parent.parent.parent  # SAMC_NEW/
DB_DIR = ROOT / "DB_최신"

load_dotenv(Path(__file__).parent.parent / ".env")

# RAG 대상 PDF (run.md 기준 9개)
TARGET_DIRS = [
    DB_DIR / "1_법률",
    DB_DIR / "2_시행령",
    DB_DIR / "3_시행규칙",
    DB_DIR / "5_행정규칙",
    DB_DIR / "6_가이드라인" / "OEM수입식품관리",
]

CHUNK_SIZE = 800    # 청크당 글자 수
CHUNK_OVERLAP = 100

INDEX_NAME = "f5-law-chunks"   # Pinecone 인덱스 이름
DIMENSION  = 1024              # voyage-3 임베딩 차원
METRIC     = "cosine"


# ── Pinecone 클라이언트 ─────────────────────────────────────────────────────

def get_pinecone_index():
    api_key = os.getenv("F5_PINECONE_API_KEY")
    if not api_key:
        raise RuntimeError("F5_PINECONE_API_KEY 환경변수 미설정")

    pc = Pinecone(api_key=api_key)

    # 인덱스가 없으면 자동 생성
    existing = [idx.name for idx in pc.list_indexes()]
    if INDEX_NAME not in existing:
        print(f"  Pinecone 인덱스 '{INDEX_NAME}' 생성 중...")
        pc.create_index(
            name=INDEX_NAME,
            dimension=DIMENSION,
            metric=METRIC,
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        print(f"  → 인덱스 생성 완료")

    return pc.Index(INDEX_NAME)


# ── Voyage 클라이언트 ──────────────────────────────────────────────────────

def get_voyage():
    api_key = os.getenv("F5_VOYAGE_API_KEY")
    if not api_key:
        raise RuntimeError("F5_VOYAGE_API_KEY 환경변수 미설정")
    return voyageai.Client(api_key=api_key)


# ── PDF 처리 ───────────────────────────────────────────────────────────────

def collect_pdfs() -> list[Path]:
    pdfs = []
    for d in TARGET_DIRS:
        if d.exists():
            pdfs.extend(d.glob("*.pdf"))
    return sorted(pdfs)


def extract_text(pdf_path: Path) -> str:
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
    return "\n".join(text_parts)


def chunk_text(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


# ── 임베딩 & Pinecone 저장 ─────────────────────────────────────────────────

def embed_and_save(pdfs: list[Path], index, voyage):
    for pdf_path in pdfs:
        print(f"  처리 중: {pdf_path.name}")
        text = extract_text(pdf_path)
        if not text.strip():
            print(f"  → 텍스트 추출 실패, 건너뜀")
            continue

        chunks = chunk_text(text)
        print(f"  → {len(chunks)}개 청크 생성")

        # 임베딩 (최대 128개씩 배치)
        batch_size = 128
        vectors = []

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            result = voyage.embed(batch, model="voyage-3")

            for j, (chunk_text_val, embedding) in enumerate(zip(batch, result.embeddings)):
                chunk_index = i + j
                vectors.append(
                    {
                        # Pinecone id: 법령명_청크번호 (중복 방지)
                        "id": hashlib.md5(f"{pdf_path.stem}__{chunk_index}".encode()).hexdigest(),
                        "values": embedding,
                        "metadata": {
                            "law_name":    pdf_path.stem,
                            "content":     chunk_text_val,
                            "chunk_index": chunk_index,
                        },
                    }
                )

        # Pinecone upsert (최대 100개씩)
        upsert_batch = 100
        for i in range(0, len(vectors), upsert_batch):
            index.upsert(vectors=vectors[i : i + upsert_batch])

        print(f"  → {len(vectors)}개 청크 저장 완료")


# ── 메인 ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="법령 PDF 임베딩 스크립트 (Pinecone)")
    parser.add_argument("--dry-run", action="store_true", help="대상 PDF 목록만 출력")
    parser.add_argument("--check",   action="store_true", help="저장된 청크 수 확인")
    parser.add_argument("--reset",   action="store_true", help="기존 청크 삭제 후 재임베딩")
    args = parser.parse_args()

    pdfs = collect_pdfs()

    if args.dry_run:
        print(f"대상 PDF ({len(pdfs)}개):")
        for p in pdfs:
            print(f"  {p}")
        return

    index = get_pinecone_index()

    if args.check:
        stats = index.describe_index_stats()
        print(f"저장된 청크 수: {stats.total_vector_count}")
        return

    if args.reset:
        print("기존 청크 삭제 중... (인덱스 전체 초기화)")
        index.delete(delete_all=True)
        print("삭제 완료")

    voyage = get_voyage()
    print(f"\n임베딩 시작 ({len(pdfs)}개 PDF)\n")
    embed_and_save(pdfs, index, voyage)
    print("\n완료!")


if __name__ == "__main__":
    main()