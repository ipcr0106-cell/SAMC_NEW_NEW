"""samc-law → samc-law-f1 복제 검증 + Pinecone vs Supabase 미러 일관성 확인.

실행:
    F1_PINECONE_API_KEY=... SUPABASE_URL=... SUPABASE_SERVICE_KEY=... \
        python -m backend.scripts.f1_verify_replication

출력:
    - source(samc-law) vs target(samc-law-f1) namespace별 건수 비교
    - Supabase f1_law_chunks 미러 건수 비교
    - 랜덤 샘플 3건 fetch → 메타 일치 확인

참고: 계획/f1_RAG도입_Phase진행계획.md §Phase 2 검증
"""
from __future__ import annotations

import os
import random
import sys

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


def _ns_count(stats, ns: str) -> int:
    namespaces = stats.get("namespaces") or {}
    info = namespaces.get(ns) or {}
    return info.get("vector_count", info.get("recordCount", 0))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    api_key = os.environ.get("F1_PINECONE_API_KEY")
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not api_key:
        raise SystemExit("[error] F1_PINECONE_API_KEY 미설정")

    pc = Pinecone(api_key=api_key)
    src = pc.Index(SOURCE_INDEX)
    dst = pc.Index(TARGET_INDEX)
    src_stats = src.describe_index_stats()
    dst_stats = dst.describe_index_stats()

    print("=== 건수 비교 (source → target) ===")
    total_src = total_dst = 0
    for ns in F1_NAMESPACES:
        s = _ns_count(src_stats, ns)
        d = _ns_count(dst_stats, ns)
        total_src += s
        total_dst += d
        status = "OK" if s == d else "MISMATCH"
        print(f"  [{status:8s}] {ns:25s} src={s:>4d}  dst={d:>4d}")
    print(f"  합계                                src={total_src:>4d}  dst={total_dst:>4d}")

    if not supabase_url or not supabase_key:
        print("\n[skip] SUPABASE_URL/SUPABASE_SERVICE_KEY 미설정 — 미러 검증 생략")
        return

    sb = create_client(supabase_url, supabase_key)
    print("\n=== Supabase f1_law_chunks 미러 ===")
    total_mirror = sb.table("f1_law_chunks").select("*", count="exact", head=True).execute().count
    print(f"  total: {total_mirror} (Pinecone dst={total_dst})")
    for ns in F1_NAMESPACES:
        cnt = sb.table("f1_law_chunks").select("*", count="exact", head=True).eq(
            "pinecone_namespace", ns,
        ).execute().count
        d = _ns_count(dst_stats, ns)
        status = "OK" if cnt == d else "MISMATCH"
        print(f"  [{status:8s}] {ns:25s} mirror={cnt:>4d}  pinecone={d:>4d}")

    print("\n=== 샘플 3건 메타 매핑 ===")
    ids_per_ns = {}
    for ns in F1_NAMESPACES:
        rows = sb.table("f1_law_chunks").select("vector_id").eq(
            "pinecone_namespace", ns,
        ).limit(1).execute().data
        if rows:
            ids_per_ns[ns] = rows[0]["vector_id"]
    sample_ids = random.sample(list(ids_per_ns.items()), min(3, len(ids_per_ns)))
    for ns, vid in sample_ids:
        src_vec = src.fetch(ids=[vid], namespace=ns).vectors.get(vid)
        dst_vec = dst.fetch(ids=[vid], namespace=ns).vectors.get(vid)
        mirror = sb.table("f1_law_chunks").select("*").eq("vector_id", vid).execute().data
        src_text = (src_vec.metadata or {}).get("text", "") if src_vec else ""
        dst_text = (dst_vec.metadata or {}).get("text", "") if dst_vec else ""
        mir_text = mirror[0]["text"] if mirror else ""
        ok = src_text == dst_text and mir_text.startswith(src_text[:100])
        status = "OK" if ok else "MISMATCH"
        print(f"  [{status:8s}] {vid} (ns={ns}) src_text[:50]={src_text[:50]!r}")


if __name__ == "__main__":
    main()
