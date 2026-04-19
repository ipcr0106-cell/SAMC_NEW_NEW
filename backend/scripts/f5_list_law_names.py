"""
Pinecone f5-law-chunks 인덱스에 저장된 모든 고유 law_name 을 조회.
사용: python scripts/list_law_names.py

이 스크립트는 인덱스 내 법령 종류를 파악하기 위한 디버깅 용도.
"""

import os
import sys
from collections import Counter

# 백엔드 모듈 import 를 위해 경로 추가 (backend/ 에서 실행 시)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.f5_rag import _get_pinecone_index


def main():
    print("=" * 70)
    print("Pinecone f5-law-chunks 인덱스 법령 목록 조회")
    print("=" * 70)

    index = _get_pinecone_index()

    # 인덱스 stats 조회
    stats = index.describe_index_stats()
    total_vectors = stats.get("total_vector_count", 0)
    print(f"\n[인덱스 정보]")
    print(f"  - 전체 벡터 수: {total_vectors}")
    print(f"  - 네임스페이스: {list(stats.get('namespaces', {}).keys())}")

    # 모든 청크를 조회하기 위해 더미 0 벡터로 top_k=500 query
    # (Voyage-3 는 1024차원)
    print(f"\n[법령 스캔 중...]")
    dummy_vector = [0.0] * 1024

    res = index.query(
        vector=dummy_vector,
        top_k=500,   # 인덱스보다 크게 잡아서 최대한 많이 가져옴
        include_metadata=True,
    )
    matches = res.get("matches") or []
    print(f"  - 조회된 벡터 수: {len(matches)} / {total_vectors}")

    # law_name 별로 카운트
    law_counter: Counter = Counter()
    for m in matches:
        meta = m.get("metadata") or {}
        law_name = meta.get("law_name", "(법령명 없음)")
        law_counter[law_name] += 1

    # 정렬해서 출력
    print(f"\n[발견된 고유 법령: {len(law_counter)}개]\n")

    sorted_laws = sorted(law_counter.items(), key=lambda x: -x[1])
    for i, (law_name, count) in enumerate(sorted_laws, 1):
        # 법령명이 길면 잘라서 표시
        display_name = law_name if len(law_name) <= 80 else law_name[:77] + "..."
        print(f"  {i:3d}. [{count:4d} 청크] {display_name}")

    # 특정 법령 존재 확인
    print(f"\n[관심 법령 확인]")
    target_keywords = [
        "식품등의 표시기준",
        "식품 등의 표시기준",
        "식품등의 한시적 기준",
        "식품 등의 표시·광고",
        "식품 위생법",
        "식품위생법",
        "건강기능식품",
        "수입식품안전관리",
    ]
    for keyword in target_keywords:
        found = [name for name in law_counter.keys() if keyword in name]
        if found:
            print(f"  [OK] '{keyword}' 포함 법령 {len(found)}개:")
            for name in found[:3]:
                display = name if len(name) <= 70 else name[:67] + "..."
                print(f"         - [{law_counter[name]:4d} 청크] {display}")
        else:
            print(f"  [없음] '{keyword}' 관련 법령이 발견되지 않음")

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()