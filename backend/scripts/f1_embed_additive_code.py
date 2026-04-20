"""식품첨가물공전 마크다운 파일 6개 → 청킹 → OpenAI 임베딩 → samc-law-f1/additive_code_text.

입력:
    --files <md1> <md2> ... 또는 --dir <디렉토리>
    파일명 규칙(regulation_id 추출): "_{N}__<label>.md"

출력:
    - Pinecone samc-law-f1 namespace=additive_code_text 에 upsert
    - Supabase f1_law_chunks 미러 INSERT

환경변수:
    F1_OPENAI_API_KEY, F1_PINECONE_API_KEY, F1_PINECONE_INDEX=samc-law-f1,
    SUPABASE_URL, SUPABASE_SERVICE_KEY

실행:
    F1_OPENAI_API_KEY=... F1_PINECONE_API_KEY=... SUPABASE_URL=... SUPABASE_SERVICE_KEY=... \
        python -m backend.scripts.f1_embed_additive_code --dir "C:/Users/user/Desktop/식품공전_마크다운_전체_7/식품첨가물공전"

    # dry-run (청크 수/토큰 분포만 출력, 임베딩·upsert 안 함)
    ... python -m backend.scripts.f1_embed_additive_code --dir ... --dry-run

참고: 계획/f1_RAG도입계획_전처리.md §5
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Optional

from supabase import create_client

from backend.services import f1_chunking, f1_openai_client, f1_pinecone_client

NAMESPACE = "additive_code_text"
EMBED_BATCH = 100
UPSERT_BATCH = 100


_REG_LABELS = {
    "1": "식품첨가물공전 I-III",
    "2": "식품첨가물공전 IV 품목별 성분규격",
    "3": "식품첨가물공전 V-VII",
    "4": "식품첨가물공전 별표1 향료",
    "5": "식품첨가물공전 별표2-4",
    "6": "식품첨가물공전 일람표",
}

_ID_PREFIXES = {
    "1": "additive_general",
    "2": "additive_spec",
    "3": "additive_testmethod",
    "4": "additive_flavor",
    "5": "additive_misc",
    "6": "additive_history",
}


def _file_idx(filename: str) -> Optional[str]:
    m = re.match(r"^_(\d+)__(.+)$", Path(filename).stem)
    return m.group(1) if m else None


def _regulation_id_from_filename(filename: str) -> str:
    idx = _file_idx(filename)
    return _REG_LABELS.get(idx or "", f"식품첨가물공전 {Path(filename).stem}")


def _id_prefix_from_filename(filename: str) -> str:
    """Pinecone ASCII-only 제약 → 파일별 ASCII prefix."""
    idx = _file_idx(filename)
    return _ID_PREFIXES.get(idx or "", "additive_misc_other")


def _load_files(files: list[str], dir_path: str | None) -> list[Path]:
    if dir_path:
        p = Path(dir_path)
        md_files = sorted(p.glob("*.md"))
        return md_files
    return [Path(f) for f in files]


def _run(files: list[Path], dry_run: bool) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    # 1. 파일별 청킹
    per_file_chunks: list[tuple[Path, list[dict]]] = []
    total_chunks = 0
    for f in files:
        if not f.exists():
            print(f"[warn] {f} 파일 없음 — 건너뜀")
            continue
        md = f.read_text(encoding="utf-8")
        regulation_id = _regulation_id_from_filename(f.name)
        id_prefix = _id_prefix_from_filename(f.name)
        chunks = f1_chunking.chunk_markdown(md, regulation_id, NAMESPACE, id_prefix=id_prefix)
        per_file_chunks.append((f, chunks))
        print(
            f"[chunk] {f.name}: {len(chunks)}개 "
            f"(regulation_id={regulation_id!r}, id_prefix={id_prefix!r})"
        )
        total_chunks += len(chunks)

    print(f"\n=== 총 {total_chunks}개 청크 ===")

    if dry_run:
        print("\n=== dry-run: 토큰 분포 ===")
        from statistics import mean, median
        all_tokens = []
        for _, chunks in per_file_chunks:
            all_tokens.extend(c["metadata"]["token_count"] for c in chunks)
        if all_tokens:
            print(f"min={min(all_tokens)} max={max(all_tokens)} "
                  f"mean={mean(all_tokens):.0f} median={median(all_tokens):.0f}")
            oversize = sum(1 for t in all_tokens if t > f1_chunking.MAX_CHUNK_TOKENS)
            undersize = sum(1 for t in all_tokens if t < f1_chunking.MIN_CHUNK_TOKENS)
            print(f"oversize (>{f1_chunking.MAX_CHUNK_TOKENS}): {oversize}")
            print(f"undersize (<{f1_chunking.MIN_CHUNK_TOKENS}): {undersize}")
        return

    # 2. 임베딩 + Pinecone upsert (배치)
    api_key = os.environ.get("F1_OPENAI_API_KEY")
    pc_key = os.environ.get("F1_PINECONE_API_KEY")
    sb_url = os.environ.get("SUPABASE_URL")
    sb_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not all([api_key, pc_key, sb_url, sb_key]):
        raise SystemExit("[error] F1_OPENAI_API_KEY / F1_PINECONE_API_KEY / SUPABASE_URL / SUPABASE_SERVICE_KEY 필요")

    idx = f1_pinecone_client.get_index()
    sb = create_client(sb_url, sb_key)

    # 2-1. 파일별 임베딩 + upsert
    for path, chunks in per_file_chunks:
        print(f"\n[{path.name}] 임베딩 시작 ({len(chunks)}개)")
        vectors: list[dict] = []
        for i in range(0, len(chunks), EMBED_BATCH):
            batch = chunks[i : i + EMBED_BATCH]
            embs = f1_openai_client.embed([c["text"] for c in batch])
            for c, e in zip(batch, embs):
                vectors.append({
                    "id": c["vector_id"],
                    "values": e,
                    "metadata": {**c["metadata"], "text": c["text"][:4000]},
                })
            print(f"  embed {i + len(batch)}/{len(chunks)}")

        # Pinecone upsert
        for i in range(0, len(vectors), UPSERT_BATCH):
            idx.upsert(
                vectors=vectors[i : i + UPSERT_BATCH],
                namespace=NAMESPACE,
            )
        print(f"  [pinecone] {len(vectors)}개 upsert 완료")

        # 미러 INSERT
        mirror_rows = [{
            "vector_id": v["id"],
            "regulation_id": v["metadata"]["regulation_id"],
            "pinecone_namespace": NAMESPACE,
            "section_path": v["metadata"].get("section_path"),
            "text": v["metadata"].get("text", "")[:16000],
            "token_count": v["metadata"].get("token_count"),
            "chunk_index": v["metadata"].get("chunk_index"),
            "total_chunks": v["metadata"].get("total_chunks"),
        } for v in vectors]
        for i in range(0, len(mirror_rows), UPSERT_BATCH):
            sb.table("f1_law_chunks").upsert(
                mirror_rows[i : i + UPSERT_BATCH], on_conflict="vector_id",
            ).execute()
        print(f"  [supabase] {len(mirror_rows)}행 upsert 완료")

    print(f"\n=== 완료: {total_chunks}개 청크 적재 ===")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", nargs="+", help="개별 md 파일 경로")
    parser.add_argument("--dir", help="디렉토리 (내부 *.md 모두 수집)")
    parser.add_argument("--dry-run", action="store_true", help="토큰 분포만 출력")
    args = parser.parse_args()

    if not args.files and not args.dir:
        parser.error("--files 또는 --dir 필수")

    files = _load_files(args.files or [], args.dir)
    if not files:
        raise SystemExit("[error] 처리할 파일이 없음")
    _run(files, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
