"""F1 Phase 4-B-3 — 골든셋 평가 러너.

개요:
    goldenset_f1_v1.json 의 각 케이스에 대해 run_feature1_with_rag() 실행,
    expected vs actual 비교 + 분기별 일치율 + p50/p95 레이턴시 + 비용 추정.

실행:
    cd backend
    export F1_OPENAI_API_KEY=...
    export F1_PINECONE_API_KEY=...
    export F1_PINECONE_INDEX=samc-law-f1
    export F1_OPENAI_CHAT_MODEL=gpt-4o-mini
    export F1_OPENAI_EMBED_MODEL=text-embedding-3-small
    export F1_RAG_TOP_K=5
    export SUPABASE_URL=...
    export SUPABASE_SERVICE_KEY=...
    python scripts/f1_run_goldenset.py

옵션:
    --goldenset PATH   기본: tests/goldenset_f1_v1.json
    --output PATH      기본: tests/goldenset_run_result.json
    --limit N          첫 N건만 실행 (디버깅용)

비용 추정:
    embed (text-embedding-3-small): $0.02/1M token, 평균 건당 ~50 token  ≈ $0.000001
    chat (gpt-4o-mini): input $0.15/1M + output $0.60/1M, 평균 건당 ~8K/300 token ≈ $0.0014
    → 30건 총합 ≈ $0.04 내외 (gpt-4o-mini 기준)
    → gpt-4o 격상 시 약 10배 ≈ $0.4

참고:
    - backend/services/feature1.py:run_feature1_with_rag (Phase 4-B-1)
    - backend/tests/goldenset_f1_v1.json (Phase 4-B-3a/3b)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Windows cp949 회피
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# backend/ 를 sys.path 에 추가 (scripts/ 하위 실행 대비)
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.f1_law_citation import ConflictStatus, RagJudgement  # noqa: E402
from models.judgment import Feature1Output, Ingredient, ProcessConditions  # noqa: E402
from services.feature1 import (_derive_exact_verdict,  # noqa: E402
                               run_feature1_with_rag)

DEFAULT_GOLDENSET = BACKEND_DIR / "tests" / "goldenset_f1_v1.json"
DEFAULT_OUTPUT = BACKEND_DIR / "tests" / "goldenset_run_result.json"


# ============================================================
# 비용 추정 상수 (2026-04 기준 USD/1M token)
# 출처: OpenAI API pricing 2026-04
# ============================================================

PRICE_EMBED = 0.02  # text-embedding-3-small

# (input, output) per 1M tokens
PRICE_TABLE: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5": (1.25, 10.00),
}

AVG_EMBED_TOKENS = 50
AVG_CHAT_INPUT_TOKENS = 8000  # 컨텍스트 ~8K (top_k=5 × 2 × ~4000자 / 4token per char)
AVG_CHAT_OUTPUT_TOKENS = 300  # JSON 응답


def estimate_cost_per_case(model: str) -> float:
    """건당 예상 비용 (USD). 매칭 실패 시 gpt-4o 가격으로 fallback."""
    m = model.lower().strip()
    # 정확 매칭 우선, 없으면 접두 매칭으로 fallback
    chat_input, chat_output = PRICE_TABLE.get(
        m, PRICE_TABLE["gpt-4o"]
    )
    if m not in PRICE_TABLE:
        for key, price in PRICE_TABLE.items():
            if m.startswith(key):
                chat_input, chat_output = price
                break
    embed_cost = AVG_EMBED_TOKENS * PRICE_EMBED / 1_000_000
    chat_cost = (
        AVG_CHAT_INPUT_TOKENS * chat_input / 1_000_000
        + AVG_CHAT_OUTPUT_TOKENS * chat_output / 1_000_000
    )
    return embed_cost + chat_cost


# ============================================================
# 케이스 직렬화
# ============================================================


def parse_ingredients(raw: list[dict[str, Any]]) -> list[Ingredient]:
    return [Ingredient(**r) for r in raw]


def parse_process(raw: dict[str, Any]) -> ProcessConditions:
    return ProcessConditions(**(raw or {}))


def rag_to_dict(rag: Optional[RagJudgement]) -> Optional[dict[str, Any]]:
    if rag is None:
        return None
    return {
        "rag_verdict": rag.rag_verdict,
        "rag_reasoning": rag.rag_reasoning,
        "law_citations": [
            {
                "chunk_id": c.chunk_id,
                "namespace": c.namespace,
                "regulation_id": c.regulation_id,
                "section_path": c.section_path,
                "score": c.score,
                "text_preview": (c.text[:200] + "...") if len(c.text) > 200 else c.text,
            }
            for c in rag.law_citations
        ],
    }


def feature1_to_dict(out: Feature1Output) -> dict[str, Any]:
    return {
        "import_possible": out.import_possible,
        "verdict": out.verdict,
        "aggregation": (
            {
                "total": out.aggregation.total,
                "permitted": out.aggregation.permitted,
                "restricted": out.aggregation.restricted,
                "prohibited": out.aggregation.prohibited,
                "unidentified": out.aggregation.unidentified,
            }
            if out.aggregation
            else None
        ),
        "forbidden_hits_count": len(out.forbidden_hits),
    }


# ============================================================
# 케이스 실행
# ============================================================


async def run_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id = case["case_id"]
    ings = parse_ingredients(case["ingredients"])
    food_type = case.get("food_type")
    process = parse_process(case.get("process_conditions") or {})

    expected = {
        "exact_verdict": case["expected_exact_verdict"],
        "rag_verdict": case["expected_rag_verdict"],
        "conflict_status": case["expected_conflict_status"],
    }

    t0 = time.monotonic()
    try:
        out, rag, conflict = await run_feature1_with_rag(
            ingredients=ings,
            food_type=food_type,
            process_conditions=process,
        )
        latency_ms = (time.monotonic() - t0) * 1000.0
        actual_exact = _derive_exact_verdict(out)
        actual_rag = rag.rag_verdict if rag else None
        actual = {
            "exact_verdict": actual_exact,
            "rag_verdict": actual_rag,
            "conflict_status": conflict,
            "feature1_output": feature1_to_dict(out),
            "rag_judgement": rag_to_dict(rag),
            "latency_ms": round(latency_ms, 1),
        }
        match = {
            "exact_match": actual_exact == expected["exact_verdict"],
            "rag_match": actual_rag == expected["rag_verdict"],
            "conflict_match": conflict == expected["conflict_status"],
        }
        return {
            "case_id": case_id,
            "description": case["description"],
            "expected": expected,
            "actual": actual,
            "match": match,
            "error": None,
        }
    except Exception as exc:
        latency_ms = (time.monotonic() - t0) * 1000.0
        return {
            "case_id": case_id,
            "description": case["description"],
            "expected": expected,
            "actual": None,
            "match": {
                "exact_match": False,
                "rag_match": False,
                "conflict_match": False,
            },
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "latency_ms": round(latency_ms, 1),
            },
        }


# ============================================================
# 통계 집계
# ============================================================


def summarize(results: list[dict[str, Any]], model: str) -> dict[str, Any]:
    total = len(results)
    ok = [r for r in results if r["error"] is None]

    exact_match = sum(1 for r in ok if r["match"]["exact_match"])
    rag_match = sum(1 for r in ok if r["match"]["rag_match"])
    conflict_match = sum(1 for r in ok if r["match"]["conflict_match"])

    latencies = [r["actual"]["latency_ms"] for r in ok]
    latency_p50 = statistics.median(latencies) if latencies else None
    if len(latencies) >= 2:
        latency_p95 = statistics.quantiles(latencies, n=20)[18]
    else:
        latency_p95 = latencies[0] if latencies else None

    conflict_actual = Counter(r["actual"]["conflict_status"] for r in ok)
    exact_actual = Counter(r["actual"]["exact_verdict"] for r in ok)

    per_branch: dict[str, dict[str, int]] = {}
    for r in ok:
        expected_branch = r["expected"]["conflict_status"]
        per_branch.setdefault(
            expected_branch, {"total": 0, "conflict_match": 0}
        )
        per_branch[expected_branch]["total"] += 1
        if r["match"]["conflict_match"]:
            per_branch[expected_branch]["conflict_match"] += 1

    return {
        "total": total,
        "success": len(ok),
        "errors": total - len(ok),
        "exact_accuracy": round(exact_match / len(ok), 4) if ok else 0.0,
        "rag_accuracy": round(rag_match / len(ok), 4) if ok else 0.0,
        "conflict_accuracy": round(conflict_match / len(ok), 4) if ok else 0.0,
        "conflict_distribution_actual": dict(conflict_actual),
        "exact_distribution_actual": dict(exact_actual),
        "per_branch_conflict_accuracy": {
            k: {
                **v,
                "accuracy": round(v["conflict_match"] / v["total"], 4) if v["total"] else 0.0,
            }
            for k, v in per_branch.items()
        },
        "latency_p50_ms": round(latency_p50, 1) if latency_p50 is not None else None,
        "latency_p95_ms": round(latency_p95, 1) if latency_p95 is not None else None,
        "cost_estimate_usd": round(estimate_cost_per_case(model) * len(ok), 4),
    }


# ============================================================
# main
# ============================================================


async def async_main(
    goldenset_path: Path, output_path: Path, limit: Optional[int]
) -> int:
    model = os.environ.get("F1_OPENAI_CHAT_MODEL", "gpt-4o-mini")
    top_k = int(os.environ.get("F1_RAG_TOP_K", "5"))
    index_name = os.environ.get("F1_PINECONE_INDEX", "samc-law-f1")

    required_env = ["F1_OPENAI_API_KEY", "F1_PINECONE_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_KEY"]
    missing = [k for k in required_env if not os.environ.get(k)]
    if missing:
        print(f"[ERROR] 필수 env 미설정: {missing}", file=sys.stderr)
        return 2

    with open(goldenset_path, "r", encoding="utf-8") as f:
        goldenset = json.load(f)
    cases = goldenset["cases"]
    if limit is not None:
        cases = cases[:limit]

    print(f"[info] goldenset: {goldenset_path}")
    print(f"[info] cases: {len(cases)}")
    print(f"[info] model: {model} / top_k={top_k} / index={index_name}")
    print(f"[info] output: {output_path}")
    print()

    started_at = datetime.now(timezone.utc)
    t0 = time.monotonic()
    results: list[dict[str, Any]] = []
    for i, case in enumerate(cases, 1):
        case_id = case["case_id"]
        print(f"[{i:3d}/{len(cases)}] {case_id} {case['description'][:50]} ... ", end="", flush=True)
        r = await run_case(case)
        results.append(r)
        if r["error"]:
            print(f"ERROR {r['error']['type']}")
        else:
            m = r["match"]
            tag = "✓" if m["conflict_match"] else "✗"
            print(
                f"{tag} conflict={r['actual']['conflict_status']} ({r['actual']['latency_ms']:.0f}ms)"
            )

    finished_at = datetime.now(timezone.utc)
    total_ms = (time.monotonic() - t0) * 1000.0

    summary = summarize(results, model)

    output = {
        "run_meta": {
            "model": model,
            "top_k": top_k,
            "index": index_name,
            "goldenset_version": goldenset.get("version", "unknown"),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "total_ms": round(total_ms, 1),
            "total_cases": len(cases),
        },
        "summary": summary,
        "results": results,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 60)
    print(f"총 {summary['total']}건 / 성공 {summary['success']} / 실패 {summary['errors']}")
    print(f"conflict 일치율: {summary['conflict_accuracy']*100:.1f}%")
    print(f"exact   일치율: {summary['exact_accuracy']*100:.1f}%")
    print(f"rag     일치율: {summary['rag_accuracy']*100:.1f}%")
    print(f"레이턴시 p50={summary['latency_p50_ms']}ms / p95={summary['latency_p95_ms']}ms")
    print(f"비용 추정: ~${summary['cost_estimate_usd']}")
    print(f"분기별 일치율:")
    for branch, stat in summary["per_branch_conflict_accuracy"].items():
        print(f"  {branch:<18} {stat['conflict_match']}/{stat['total']} ({stat['accuracy']*100:.1f}%)")
    print(f"저장: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="F1 골든셋 평가 러너")
    parser.add_argument("--goldenset", type=Path, default=DEFAULT_GOLDENSET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=None, help="첫 N건만 실행 (디버깅)")
    args = parser.parse_args()
    return asyncio.run(async_main(args.goldenset, args.output, args.limit))


if __name__ == "__main__":
    raise SystemExit(main())
