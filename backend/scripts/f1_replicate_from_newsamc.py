"""samc-law (newsamc) → samc-law-f1 복제 + Supabase f1_law_chunks 미러.

전제 (조사 확인됨 2026-04-17):
    - newsamc PINECONE_API_KEY = SAMC 회사 공용 Pinecone 계정과 동일 → F1_PINECONE_API_KEY 1개로 접근
    - 차원 동일 1536 (둘 다 text-embedding-3-small) → 벡터 그대로 재사용
    - F1 관련 namespace 4개만 복제 (additive_code_text는 Phase 3 신규 임베딩)

환경변수:
    F1_PINECONE_API_KEY     Pinecone (source + target 공용)
    SUPABASE_URL            SAMC 회사 공용 프로젝트
    SUPABASE_SERVICE_KEY    service role key (미러 테이블 INSERT)

실행:
    # dry-run (단일 namespace, upsert 안 함)
    python -m backend.scripts.f1_replicate_from_newsamc --dry-run --namespace temporary_standard

    # 단일 namespace 실제 복제
    python -m backend.scripts.f1_replicate_from_newsamc --namespace temporary_standard

    # 전체 4개 namespace 복제
    python -m backend.scripts.f1_replicate_from_newsamc --all

참고: 계획/f1_RAG도입계획_전처리.md §4
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Optional

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


def _parse_chunk_index(vid: str) -> Optional[int]:
    """vector_id에서 끝자리 숫자 추출. `{ns}_0004` 또는 `fct-1` 형식 대응."""
    for sep in ("_", "-"):
        tail = vid.rsplit(sep, 1)[-1]
        if tail.isdigit():
            return int(tail)
    return None


def _build_mirror_row(vid: str, meta: dict, namespace: str, text: str) -> dict:
    """newsamc metadata → f1_law_chunks 행 매핑.

    newsamc 스키마는 namespace별로 약간 다름:
      - food_code_text: namespace, section, source, text
      - 나머지: heading, label, source, text, tokens, type
    """
    regulation_id = (
        meta.get("label") or meta.get("source") or meta.get("section") or "unknown"
    )
    section_path = meta.get("heading") or meta.get("section") or None
    token_count: Optional[int] = None
    if meta.get("tokens") is not None:
        try:
            token_count = int(meta["tokens"])
        except (TypeError, ValueError):
            token_count = None
    return {
        "vector_id": vid,
        "regulation_id": regulation_id,
        "pinecone_namespace": namespace,
        "section_path": section_path,
        "text": text[:16000],
        "token_count": token_count,
        "chunk_index": _parse_chunk_index(vid),
        "total_chunks": None,
    }


def _collect_ids(src, namespace: str) -> list[str]:
    """v8 idx.list(namespace=...) 페이지네이션 제너레이터 소진."""
    ids: list[str] = []
    for page in src.list(namespace=namespace):
        # page may be list[str] or list[dict]
        if isinstance(page, list):
            for item in page:
                if isinstance(item, str):
                    ids.append(item)
                elif isinstance(item, dict) and "id" in item:
                    ids.append(item["id"])
        else:
            ids.append(str(page))
    return ids


def replicate_namespace(
    src,
    dst,
    sb_client,
    namespace: str,
    dry_run: bool = False,
) -> int:
    """단일 namespace 전체 fetch → target upsert + Postgres 미러 upsert."""
    print(f"\n=== [{namespace}] 수집 시작 ===")
    ids = _collect_ids(src, namespace)
    total = len(ids)
    print(f"[{namespace}] 수집된 vector_id 수: {total}")

    if total == 0:
        print(f"[{namespace}] 건너뜀 (빈 namespace)")
        return 0

    if dry_run:
        # 첫 5개만 fetch해서 metadata 구조 확인
        sample_ids = ids[:5]
        fetched = src.fetch(ids=sample_ids, namespace=namespace)
        print(f"[{namespace}] dry-run 샘플 {len(sample_ids)}개 메타 키:")
        for vid, vec in fetched.vectors.items():
            print(f"  - {vid}: keys={list((vec.metadata or {}).keys())}")
        return total

    done = 0
    for i in range(0, total, BATCH_SIZE):
        batch_ids = ids[i : i + BATCH_SIZE]
        fetched = src.fetch(ids=batch_ids, namespace=namespace)

        upsert_vectors = []
        mirror_rows = []
        for vid, vec in fetched.vectors.items():
            meta = vec.metadata or {}
            upsert_vectors.append({
                "id": vid,
                "values": vec.values,
                "metadata": meta,
            })
            mirror_rows.append(
                _build_mirror_row(vid, meta, namespace, meta.get("text") or "")
            )

        dst.upsert(vectors=upsert_vectors, namespace=namespace)
        sb_client.table("f1_law_chunks").upsert(
            mirror_rows, on_conflict="vector_id"
        ).execute()
        done += len(batch_ids)
        print(f"[{namespace}] {done}/{total} 복제 완료")
        time.sleep(0.1)  # 가벼운 throttling

    return done


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", help="단일 namespace 지정")
    parser.add_argument("--all", action="store_true", help="전체 4개 namespace")
    parser.add_argument("--dry-run", action="store_true", help="샘플 조회만")
    args = parser.parse_args()

    if not args.all and not args.namespace:
        parser.error("--namespace 또는 --all 필수")

    api_key = os.environ.get("F1_PINECONE_API_KEY")
    if not api_key:
        raise SystemExit("[error] F1_PINECONE_API_KEY 미설정")
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not args.dry_run and (not supabase_url or not supabase_key):
        raise SystemExit("[error] SUPABASE_URL/SUPABASE_SERVICE_KEY 미설정")

    pc = Pinecone(api_key=api_key)
    src = pc.Index(SOURCE_INDEX)
    dst = pc.Index(TARGET_INDEX)
    sb = create_client(supabase_url, supabase_key) if not args.dry_run else None

    target_namespaces = F1_NAMESPACES if args.all else [args.namespace]
    for ns in target_namespaces:
        if ns not in F1_NAMESPACES:
            print(f"[warn] {ns}는 F1 대상 namespace가 아님 — 건너뜀")
            continue

    grand_total = 0
    for ns in target_namespaces:
        if ns in F1_NAMESPACES:
            grand_total += replicate_namespace(src, dst, sb, ns, dry_run=args.dry_run)

    print(f"\n=== 총 {grand_total}건 처리 완료 (dry_run={args.dry_run}) ===")


if __name__ == "__main__":
    main()
