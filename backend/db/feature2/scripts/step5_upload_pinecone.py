"""
[4단계] Pinecone 업로드
3단계에서 만든 청크 JSON 파일을 임베딩 후 Pinecone에 올립니다.

실행:
    python backend/scripts/step5_upload_pinecone.py

※ 반드시 step3_chunk.py 실행 및 청크 내용 확인 후 실행하세요.
"""

import hashlib
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec

load_dotenv("backend/.env")

openai_client = OpenAI(api_key=os.getenv("F2_OPENAI_API_KEY"))
pc = Pinecone(api_key=os.getenv("F2_PINECONE_API_KEY"))
INDEX_NAME = os.getenv("F2_PINECONE_INDEX", "samc-a")
CHUNK_DIR = Path("preprocessing/chunks")

DIMENSION = 1024  # Anthropic 임베딩 차원


def get_embedding_openai(text: str) -> list[float]:
    """OpenAI 임베딩 (text-embedding-3-small, 1536차원)"""
    response = openai_client.embeddings.create(
        input=text,
        model="text-embedding-3-small",
    )
    return response.data[0].embedding


def ensure_index_exists():
    """Pinecone 인덱스가 없으면 생성"""
    existing = [idx.name for idx in pc.list_indexes()]
    if INDEX_NAME not in existing:
        print(f"  인덱스 '{INDEX_NAME}' 생성 중...")
        pc.create_index(
            name=INDEX_NAME,
            dimension=1536,  # text-embedding-3-small 기준
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        print("  인덱스 생성 완료")
    else:
        print(f"  인덱스 '{INDEX_NAME}' 이미 존재")


def upload_chunks(json_path: Path, batch_size: int = 50):
    """청크 JSON → 임베딩 → Pinecone upsert"""
    with open(json_path, encoding="utf-8") as f:
        chunks = json.load(f)

    index = pc.Index(INDEX_NAME)
    total = len(chunks)
    success = 0

    print(f"  {json_path.name}: 총 {total}개 청크 업로드 시작")

    for i in range(0, total, batch_size):
        batch = chunks[i : i + batch_size]
        vectors = []

        for chunk in batch:
            embedding = get_embedding_openai(chunk["text"])
            # Pinecone ID는 ASCII만 허용 → 파일명 포함한 MD5 해시로 변환 (파일 간 중복 방지)
            ascii_id = hashlib.md5(
                f"{json_path.stem}::{chunk['id']}".encode()
            ).hexdigest()
            vectors.append(
                {
                    "id": ascii_id,
                    "values": embedding,
                    "metadata": {
                        **chunk["metadata"],
                        "text": chunk["text"][
                            :1000
                        ],  # 메타데이터 미리보기용 (1000자 제한)
                    },
                }
            )
            time.sleep(0.05)  # API 속도 제한 방지

        index.upsert(vectors=vectors)
        success += len(batch)
        print(f"  → {success}/{total} 완료")

    print(f"  {json_path.name} 업로드 완료")


if __name__ == "__main__":
    print("=" * 50)
    print("  5단계: Pinecone 업로드")
    print("=" * 50)

    ensure_index_exists()

    json_files = list(CHUNK_DIR.glob("*.json"))
    if not json_files:
        print("\n청크 파일이 없습니다. step3_chunk.py를 먼저 실행하세요.")
    else:
        print(f"\n총 {len(json_files)}개 파일 업로드 시작\n")
        for json_path in sorted(json_files):
            print(f"\n처리 중: {json_path.name}")
            upload_chunks(json_path)

    print("\n" + "=" * 50)
    print("  완료!")
    print("  Pinecone 대시보드에서 인덱스를 확인하세요.")
    print("=" * 50)
