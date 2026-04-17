"""Pinecone에 samc-law-f1 인덱스 생성 (idempotent, pinecone v8 API).

실행:
    F1_PINECONE_API_KEY=pcsk_... python -m backend.scripts.f1_create_pinecone_index

스펙:
    - 인덱스명: samc-law-f1
    - 차원: 1536 (OpenAI text-embedding-3-small)
    - 메트릭: cosine
    - 클라우드/리전: aws / us-east-1 (회사 공용 Pinecone 계정의 다른 인덱스들과 동일)
    - 타입: dense, serverless

참고:
    계획/f1_RAG도입계획_전처리.md §1
"""
from __future__ import annotations

import os

from pinecone import Pinecone, ServerlessSpec

INDEX_NAME = "samc-law-f1"
DIMENSION = 1536
METRIC = "cosine"
CLOUD = "aws"
REGION = "us-east-1"


def main() -> None:
    api_key = os.environ.get("F1_PINECONE_API_KEY")
    if not api_key:
        raise SystemExit("[error] F1_PINECONE_API_KEY 미설정")

    pc = Pinecone(api_key=api_key)
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
    print(
        f"[created] {INDEX_NAME} "
        f"dim={DIMENSION} metric={METRIC} cloud={CLOUD} region={REGION}"
    )


if __name__ == "__main__":
    main()
