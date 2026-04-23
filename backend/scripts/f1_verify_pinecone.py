"""samc-law-f1 Pinecone 인덱스 상태 검증.

실행:
    F1_PINECONE_API_KEY=pcsk_... python -m backend.scripts.f1_verify_pinecone

출력:
    인덱스 메타 (dim, metric, region) + namespace별 vector count.

참고: 계획/f1_RAG도입계획_전처리.md §1.2
"""
from __future__ import annotations

import os
import sys

from pinecone import Pinecone


def main() -> None:
    # Windows cp949 방지
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    api_key = os.environ.get("F1_PINECONE_API_KEY")
    if not api_key:
        raise SystemExit("[error] F1_PINECONE_API_KEY 미설정")

    index_name = os.environ.get("F1_PINECONE_INDEX", "samc-law-f1")
    pc = Pinecone(api_key=api_key)
    idx = pc.Index(index_name)
    stats = idx.describe_index_stats()

    print(f"=== {index_name} ===")
    print(f"dimension       : {stats.get('dimension')}")
    print(f"metric          : {stats.get('metric', 'n/a')}")
    print(f"total_vectors   : {stats.get('total_vector_count', 0)}")
    print(f"index_fullness  : {stats.get('index_fullness', 0.0)}")

    namespaces = stats.get("namespaces") or {}
    if not namespaces:
        print("\n(namespace 없음 - 아직 데이터 적재 전)")
    else:
        print("\n=== namespaces ===")
        for ns, info in sorted(namespaces.items()):
            count = info.get("vector_count", info.get("recordCount", 0))
            print(f"  {ns:30s} {count:>6d}")


if __name__ == "__main__":
    main()
