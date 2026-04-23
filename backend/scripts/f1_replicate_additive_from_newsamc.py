"""newsamc additive_limits (964) → f1_additive_limits 매핑 복제.

전제:
    - newsamc.food_type_id(UUID) → newsamc.food_types.name 으로 lookup → f1.food_type(text)
    - newsamc 이관은 is_verified=false (팀 룰: F1 Step 3 는 is_verified=true 만 사용)
    - dedup key: (food_type, additive_name, combined_group)

실행:
    python -m scripts.f1_replicate_additive_from_newsamc --dry-run
    python -m scripts.f1_replicate_additive_from_newsamc --execute

참고: 계획/f1_RAG도입_Phase진행계획.md §Stage 2
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv
from supabase import create_client

NEWSAMC_ENV = "C:/GITHUB/newsamc/.env"
BACKEND_ENV = ".env"
BATCH_SIZE = 100
ALLOWED_COLORANT = {"tar", "non-tar", "natural"}


def _load_newsamc():
    load_dotenv(NEWSAMC_ENV, override=True)
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])


def _load_f1():
    load_dotenv(BACKEND_ENV, override=True)
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _fetch_all(sb, table: str, columns: str = "*") -> list[dict]:
    rows: list[dict] = []
    page_size = 1000
    offset = 0
    while True:
        res = sb.table(table).select(columns).range(offset, offset + page_size - 1).execute()
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
        offset += page_size


def _convert(row: dict, food_type_map: dict[str, str]) -> dict | None:
    fti = row.get("food_type_id")
    food_type = food_type_map.get(fti) if fti else "전체"
    if fti and not food_type:
        return None
    colorant = row.get("colorant_category")
    if colorant and colorant not in ALLOWED_COLORANT:
        return None
    return {
        "food_type": food_type,
        "additive_name": row["additive_name"],
        "ins_number": row.get("ins_number"),
        "max_ppm": row.get("max_ppm"),
        "combined_group": row.get("combined_group"),
        "combined_max": row.get("combined_max"),
        "conversion_factor": row.get("conversion_factor"),
        "colorant_category": colorant,
        "color_group": row.get("color_group"),
        "total_tar_limit": row.get("total_tar_limit"),
        "condition_text": None,
        "regulation_ref": row.get("regulation_ref"),
        "is_verified": False,
    }


def _key(row: dict) -> tuple:
    return (row["food_type"], row["additive_name"], row.get("combined_group"))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", dest="dry_run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    src = _load_newsamc()
    food_types = _fetch_all(src, "food_types", "id,name")
    food_type_map = {r["id"]: r["name"] for r in food_types}
    additives = _fetch_all(src, "additive_limits")
    print(f"[newsamc] food_types={len(food_types)} additive_limits={len(additives)}")

    tgt = _load_f1()
    existing = _fetch_all(tgt, "f1_additive_limits", "food_type,additive_name,combined_group")
    existing_keys = {_key(r) for r in existing}
    print(f"[f1] existing={len(existing)} unique_keys={len(existing_keys)}")

    converted: list[dict] = []
    skip_food = 0
    skip_colorant = 0
    for row in additives:
        c = _convert(row, food_type_map)
        if c is None:
            if not food_type_map.get(row["food_type_id"]):
                skip_food += 1
            else:
                skip_colorant += 1
            continue
        converted.append(c)
    print(f"[convert] ok={len(converted)} skip_food_type={skip_food} skip_colorant={skip_colorant}")

    seen = set(existing_keys)
    to_insert: list[dict] = []
    dup_existing = 0
    dup_internal = 0
    for r in converted:
        k = _key(r)
        if k in existing_keys:
            dup_existing += 1
            continue
        if k in seen:
            dup_internal += 1
            continue
        seen.add(k)
        to_insert.append(r)
    print(f"[dedup] new={len(to_insert)} dup_with_existing={dup_existing} dup_internal={dup_internal}")

    if args.limit:
        to_insert = to_insert[: args.limit]
        print(f"[limit] trimmed to {len(to_insert)}")

    print("\nsamples (first 5):")
    for r in to_insert[:5]:
        print(f"  {r}")

    if args.dry_run:
        print("\n[dry-run] no insert performed.")
        return

    inserted = 0
    for i in range(0, len(to_insert), BATCH_SIZE):
        chunk = to_insert[i : i + BATCH_SIZE]
        res = tgt.table("f1_additive_limits").insert(chunk).execute()
        inserted += len(res.data or [])
        print(f"[insert] batch {i // BATCH_SIZE + 1}: +{len(chunk)} (total {inserted})")

    total = tgt.table("f1_additive_limits").select("*", count="exact").execute().count
    verified = tgt.table("f1_additive_limits").select("*", count="exact").eq("is_verified", True).execute().count
    print(f"[verify] total={total} is_verified_true={verified} is_verified_false={total - verified}")


if __name__ == "__main__":
    main()
