"""F1 골든셋 v3 평가 러너.

개요:
    goldenset_f1_v3/cases/ 의 각 케이스에 대해 run_feature1_v2() 를 실행하고
    expected_verdict.json 과 비교하여 5개 집계 지표를 산출한다.

지표 (09번 §6-2):
    1. verdict 일치율     — 목표 ≥ 80%
    2. 금지원료 감지율    — 목표 100% Recall (is_forbidden_ingredient 케이스)
    3. 오탐률             — 목표 ≤ 5%   (permitted → prohibited/restricted 오분류)
    4. 기준규격 정확도   — 목표 ≥ 90%   (expected_standards.overall_status 일치)
    5. HITL-1 전환율     — 목표 ≤ 30%   (hitl1_required=True 케이스 비율)

실행:
    cd backend
    python scripts/f1_run_goldenset_v3.py --subset mini
    python scripts/f1_run_goldenset_v3.py --subset full

환경변수:
    F1_DATA_GO_KR_API_KEY  (data.go.kr 디코딩키)
    SUPABASE_URL
    SUPABASE_SERVICE_KEY
    MOCK_API=1             (실 API 미사용, mock 경로 — 단위 CI용)

캐시:
    data.go.kr 실 API 호출 결과는 Supabase f1_data_go_kr_cache 테이블에
    저장되므로 재실행 시 중복 호출 없음 (월 한도 절약).

출력:
    tests/goldenset_run_v3_{YYYYMMDD_HHmm}.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Windows cp949 우회
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

V3_DIR = BACKEND_DIR / "tests" / "goldenset_f1_v3" / "cases"

# ------------------------------------------------------------------
# mini 서브셋 케이스 ID 목록 (5건: 카테고리 대표)
# - case_001: permitted_db
# - case_017: forbidden_drug  (금지원료 감지율 검증)
# - case_031: conditional_restricted_db
# - case_037: conditional_heated
# - case_055: unidentified_virtual
# ------------------------------------------------------------------
MINI_CASES = [
    "case_001_rice_permitted",
    "case_017_cannabis_forbidden",
    "case_031_guarana_restricted",
    "case_037_sorbic_acid_heated_T",
    "case_055_virtual_xenostin",
]


# ==================================================================
# 케이스 로드
# ==================================================================


def load_case(case_dir: Path) -> Optional[dict[str, Any]]:
    """케이스 디렉토리에서 3개 JSON 파일 로드."""
    try:
        with open(case_dir / "input_f0.json", encoding="utf-8") as f:
            input_f0 = json.load(f)
        with open(case_dir / "expected_verdict.json", encoding="utf-8") as f:
            expected_verdict = json.load(f)
        with open(case_dir / "expected_standards.json", encoding="utf-8") as f:
            expected_standards = json.load(f)
        return {
            "case_dir": str(case_dir),
            "case_name": case_dir.name,
            "input_f0": input_f0,
            "expected_verdict": expected_verdict,
            "expected_standards": expected_standards,
        }
    except Exception as exc:
        print(f"[WARN] {case_dir.name} 로드 실패: {exc}", file=sys.stderr)
        return None


def load_all_cases(subset: str) -> list[dict[str, Any]]:
    """subset='mini'|'full' 에 따라 케이스 목록 반환."""
    if not V3_DIR.exists():
        raise FileNotFoundError(f"goldenset_f1_v3/cases 디렉토리 없음: {V3_DIR}")

    all_dirs = sorted(d for d in V3_DIR.iterdir() if d.is_dir())

    if subset == "mini":
        selected = [d for d in all_dirs if d.name in MINI_CASES]
        if not selected:
            # 디렉토리 이름이 없으면 첫 5건 fallback
            selected = all_dirs[:5]
    else:
        selected = all_dirs

    cases = []
    for d in selected:
        c = load_case(d)
        if c is not None:
            cases.append(c)
    return cases


# ==================================================================
# Mock 클라이언트 (MOCK_API=1 환경)
# ==================================================================


class _MockDataGoKrClient:
    """실 API 미사용 mock — CI 단위 테스트 전용.

    DataGoKrClient 의 실제 메서드명과 일치해야 한다:
        get_import_food_ingredient  (15111777)
        get_additive_standard       (15116583)
        get_import_food_component   (15094202)
        get_food_raw_material       (15111913)
        call()                      (통합 디스패처)
    """

    _KNOWN_RESTRICTED = frozenset({
        "과라나", "은행", "와사비", "감초", "하수오", "결명자",
        "당귀", "허니부시", "마황", "센나",
    })
    _KNOWN_ALLOWED = frozenset({
        "쌀", "사과", "우유", "인삼", "돼지고기", "연어", "참깨",
        "아몬드", "녹차", "홍삼", "꿀", "레몬", "계란",
        "배추", "고추", "마늘", "딸기", "귀리", "카카오",
    })

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    @staticmethod
    def _wrap(items: list[dict]) -> dict:
        """실제 DataGoKrClient._lookup 반환 형식 모방: {"items": [...], "total": N}."""
        return {"items": items, "total": len(items)}

    async def get_import_food_ingredient(self, name: str, **kwargs) -> dict:
        """15111777: 수입식품 원료 허용여부 mock."""
        n = name.strip()
        if n in self._KNOWN_RESTRICTED:
            items = [{"INGD_NM": n, "EDIBLE_INFO": "조건부", "CHRTR_INFO_CONT": "조건 있음",
                      "EDIBLE_N": None}]
        elif n in self._KNOWN_ALLOWED:
            items = [{"INGD_NM": n, "EDIBLE_INFO": "가능", "CHRTR_INFO_CONT": None,
                      "EDIBLE_N": None}]
        else:
            items = []
        return self._wrap(items)

    async def get_additive_standard(self, name: str, **kwargs) -> dict:
        """15116583: 식품첨가물 기준규격 mock — 빈 응답으로 Step C no_data 유도."""
        return self._wrap([])

    async def get_import_food_component(self, name: str, **kwargs) -> dict:
        """15094202: 수입식품 성분코드 mock."""
        return self._wrap([])

    async def get_food_raw_material(self, name: str, **kwargs) -> dict:
        """15111913: 식품 원재료+GMO mock."""
        return self._wrap([])

    async def call(self, endpoint_id: str, name: str, **kwargs) -> dict:
        """통합 디스패처 mock."""
        dispatch = {
            "15111777": self.get_import_food_ingredient,
            "15116583": self.get_additive_standard,
            "15094202": self.get_import_food_component,
            "15111913": self.get_food_raw_material,
        }
        fn = dispatch.get(str(endpoint_id))
        if fn:
            return await fn(name, **kwargs)
        return self._wrap([])


# ==================================================================
# 케이스 실행
# ==================================================================


# KNOWN 금지원료 목록 (mock DB 조회용)
_MOCK_FORBIDDEN_DB: dict[str, str] = {
    "대마초": "마약류 관리법 제2조",
    "cannabis": "마약류 관리법 제2조",
    "thc": "마약류 관리법 제2조",
    "양귀비": "마약류 관리법 제2조",
    "코카잎": "마약류 관리법 제2조",
    "코카": "마약류 관리법 제2조",
    "카바카바": "식약처 고시 제2020-90호",
    "에페드라": "식약처 고시 (의약품 원료)",
    "마황": "식약처 고시 (의약품 원료)",
    "에페드린": "식약처 고시 (의약품 원료)",
    "센나잎": "식약처 고시 (하제 성분)",
    "센나": "식약처 고시 (하제 성분)",
    "요힘베": "식약처 고시 (심혈관계)",
    "dmaa": "식약처 고시 (스포츠보충제)",
    "bmpea": "식약처 고시 (스포츠보충제)",
    "컴프리": "식품위생법 (PA 알칼로이드)",
    "보라지": "식품위생법 (PA 알칼로이드)",
    "아리스토로키아": "식품위생법 (신장독성)",
    "호랑이 뼈": "야생생물법 (CITES Appendix I)",
    "천산갑 비늘": "야생생물법",
    "코뿔소 뿔": "야생생물법 (CITES Appendix I)",
    "서각": "야생생물법 (CITES Appendix I)",
}


def _mock_query_db_forbidden(names_normalized: list[str]) -> list[dict]:
    """mock DB 조회 — 실제 Supabase 연결 없이 금지원료 반환."""
    hits = []
    seen: set[str] = set()
    for name in names_normalized:
        if name in _MOCK_FORBIDDEN_DB and name not in seen:
            hits.append({
                "name_ko": name,
                "reason": _MOCK_FORBIDDEN_DB[name],
                "law_ref": "mock_law_ref",
            })
            seen.add(name)
    return hits


async def run_one_case(
    case: dict[str, Any],
    use_mock: bool,
) -> dict[str, Any]:
    """단일 케이스 실행 후 결과 반환."""
    from models.judgment import Ingredient, ProcessConditions
    from models.f1_types import MeasuredValue
    from services.feature1 import run_feature1_v2

    case_name = case["case_name"]
    f0 = case["input_f0"]
    ev = case["expected_verdict"]
    es = case["expected_standards"]

    expected_verdict_str: str = ev["verdict"]
    expected_overall_status: str = es["overall_status"]
    is_forbidden: bool = ev.get("is_forbidden_ingredient", False)
    hitl1_required: bool = ev.get("hitl1_required", False)
    is_permitted_class: bool = ev["v2_exact_verdict"] == "permitted"

    # F0 데이터 → Pydantic 변환
    def _make_ingredient(raw: dict) -> Ingredient:
        sub = raw.get("sub_ingredients")
        return Ingredient(
            name=raw["name"],
            percentage=raw.get("percentage"),
            part=raw.get("part"),
            ins=raw.get("ins"),
            cas=raw.get("cas"),
            sub_ingredients=[_make_ingredient(s) for s in sub] if sub else [],
        )

    ingredients = [_make_ingredient(i) for i in f0.get("ingredients", [])]
    process_raw = f0.get("process_conditions", {})
    process_conditions = ProcessConditions(**process_raw) if process_raw else ProcessConditions()
    food_type: Optional[str] = f0.get("food_type")

    client = _MockDataGoKrClient() if use_mock else None

    t0 = time.monotonic()
    error_info = None
    actual_output = None
    try:
        if use_mock:
            # mock 모드: Supabase DB 조회를 패치하여 실 연결 없이 실행
            import services.f1_step_a as _step_a_mod
            import services.f1_step_b as _step_b_mod
            import services.f1_step_c as _step_c_mod
            import services.f1_step_d as _step_d_mod
            _orig_query_db = _step_a_mod._query_db_forbidden

            async def _mock_pinecone_search(*args, **kwargs):
                return []

            # Step D Pinecone 패치
            _orig_step_d_run = _step_d_mod.run_step_d

            async def _mock_step_d(*args, **kwargs):
                from models.f1_types import StepDResult
                return StepDResult(citations=[])

            _step_a_mod._query_db_forbidden = _mock_query_db_forbidden
            _step_d_mod.run_step_d = _mock_step_d
            try:
                actual_output = await run_feature1_v2(
                    ingredients=ingredients,
                    food_type=food_type,
                    process_conditions=process_conditions,
                    client=client,
                )
            finally:
                _step_a_mod._query_db_forbidden = _orig_query_db
                _step_d_mod.run_step_d = _orig_step_d_run
        else:
            actual_output = await run_feature1_v2(
                ingredients=ingredients,
                food_type=food_type,
                process_conditions=process_conditions,
                client=client,
            )
    except Exception as exc:
        error_info = {"type": type(exc).__name__, "message": str(exc)}

    latency_ms = round((time.monotonic() - t0) * 1000, 1)

    if error_info:
        return {
            "case_name": case_name,
            "category": ev.get("category", "unknown"),
            "expected": {
                "verdict": expected_verdict_str,
                "overall_status": expected_overall_status,
                "is_forbidden": is_forbidden,
                "hitl1_required": hitl1_required,
            },
            "actual": None,
            "verdict_match": False,
            "standards_match": False,
            "forbidden_detected": False if is_forbidden else None,
            "false_positive": False,
            "hitl1_triggered": hitl1_required,
            "latency_ms": latency_ms,
            "error": error_info,
        }

    actual_verdict: str = actual_output.verdict
    # Step C overall_status — evidence_external_data 에서 추출
    # run_feature1_v2 는 {"source": "step_c", "overall_status": ...} 형태로 저장
    actual_standards_status: str = "no_data"
    for ev_item in actual_output.evidence_external_data:
        if isinstance(ev_item, dict) and ev_item.get("step") == "C":
            actual_standards_status = ev_item.get("overall_status", "no_data")
            break

    verdict_match = actual_verdict == expected_verdict_str

    # standards 일치: no_data 는 양쪽 모두 no_data일 때만 일치
    standards_match = actual_standards_status == expected_overall_status

    # 금지원료 감지율: is_forbidden=True 케이스에서 actual=prohibited 여야 Recall 충족
    forbidden_detected: Optional[bool] = (
        (actual_verdict == "prohibited") if is_forbidden else None
    )

    # 오탐: permitted 클래스인데 prohibited 또는 restricted 로 판정된 경우
    false_positive = is_permitted_class and actual_verdict in ("prohibited", "restricted")

    # HITL-1 전환: needs_review 또는 restricted 판정이면 HITL-1 전환 대상
    hitl1_triggered = actual_verdict in ("needs_review", "restricted")

    return {
        "case_name": case_name,
        "category": ev.get("category", "unknown"),
        "expected": {
            "verdict": expected_verdict_str,
            "overall_status": expected_overall_status,
            "is_forbidden": is_forbidden,
            "hitl1_required": hitl1_required,
        },
        "actual": {
            "verdict": actual_verdict,
            "overall_status": actual_standards_status,
            "gmo_ingredients": actual_output.gmo_ingredients,
            "warnings_count": len(actual_output.warnings),
            "confidence": actual_output.confidence,
        },
        "verdict_match": verdict_match,
        "standards_match": standards_match,
        "forbidden_detected": forbidden_detected,
        "false_positive": false_positive,
        "hitl1_triggered": hitl1_triggered,
        "latency_ms": latency_ms,
        "error": None,
    }


# ==================================================================
# 집계
# ==================================================================


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """5개 지표 집계."""
    total = len(results)
    ok = [r for r in results if r["error"] is None]
    errors = total - len(ok)

    # 1. verdict 일치율
    verdict_matches = sum(1 for r in ok if r["verdict_match"])
    verdict_accuracy = verdict_matches / len(ok) if ok else 0.0

    # 2. 금지원료 감지율 (Recall)
    forbidden_cases = [r for r in ok if r["forbidden_detected"] is not None]
    forbidden_detected_cnt = sum(1 for r in forbidden_cases if r["forbidden_detected"])
    forbidden_recall = (
        forbidden_detected_cnt / len(forbidden_cases) if forbidden_cases else None
    )

    # 3. 오탐률
    permitted_cases = [r for r in ok if r["expected"]["is_forbidden"] is False
                       and r["expected"]["verdict"] == "permitted"]
    false_positives = sum(1 for r in permitted_cases if r["false_positive"])
    false_positive_rate = false_positives / len(permitted_cases) if permitted_cases else 0.0

    # 4. 기준규격 정확도 (no_data 케이스 제외)
    std_cases = [
        r for r in ok
        if r["expected"]["overall_status"] != "no_data"
        or (r["actual"] and r["actual"]["overall_status"] != "no_data")
    ]
    std_matches = sum(1 for r in std_cases if r["standards_match"])
    standards_accuracy = std_matches / len(std_cases) if std_cases else None

    # 5. HITL-1 전환율
    hitl1_triggered_cnt = sum(1 for r in ok if r["hitl1_triggered"])
    hitl1_rate = hitl1_triggered_cnt / len(ok) if ok else 0.0

    # 카테고리별 verdict 일치율
    cat_stats: dict[str, dict[str, int]] = {}
    for r in ok:
        cat = r["category"]
        cat_stats.setdefault(cat, {"total": 0, "match": 0})
        cat_stats[cat]["total"] += 1
        if r["verdict_match"]:
            cat_stats[cat]["match"] += 1

    # 임계치 통과 여부
    thresholds = {
        "verdict_accuracy_pass":    verdict_accuracy >= 0.80,
        "forbidden_recall_pass":    (forbidden_recall is None) or (forbidden_recall >= 1.0),
        "false_positive_rate_pass": false_positive_rate <= 0.05,
        "standards_accuracy_pass":  (standards_accuracy is None) or (standards_accuracy >= 0.90),
        "hitl1_rate_pass":          hitl1_rate <= 0.30,
    }

    return {
        "total": total,
        "success": len(ok),
        "errors": errors,
        "metrics": {
            "verdict_accuracy": round(verdict_accuracy, 4),
            "forbidden_recall": round(forbidden_recall, 4) if forbidden_recall is not None else None,
            "false_positive_rate": round(false_positive_rate, 4),
            "standards_accuracy": round(standards_accuracy, 4) if standards_accuracy is not None else None,
            "hitl1_rate": round(hitl1_rate, 4),
        },
        "thresholds": thresholds,
        "all_thresholds_pass": all(thresholds.values()),
        "category_accuracy": {
            cat: {
                "total": s["total"],
                "match": s["match"],
                "accuracy": round(s["match"] / s["total"], 4) if s["total"] else 0.0,
            }
            for cat, s in sorted(cat_stats.items())
        },
    }


# ==================================================================
# 출력 포맷
# ==================================================================


def _symbol(val: Optional[bool]) -> str:
    if val is None:
        return "N/A"
    return "PASS" if val else "FAIL"


def print_summary(summary: dict[str, Any]) -> None:
    m = summary["metrics"]
    t = summary["thresholds"]
    print()
    print("=" * 62)
    print(f"  총 {summary['total']}건  성공 {summary['success']}  실패 {summary['errors']}")
    print("-" * 62)
    print(
        f"  1. verdict 일치율       {m['verdict_accuracy']*100:5.1f}%  "
        f"(목표 ≥80%)   [{_symbol(t['verdict_accuracy_pass'])}]"
    )
    fr = f"{m['forbidden_recall']*100:.1f}%" if m["forbidden_recall"] is not None else "  N/A "
    print(
        f"  2. 금지원료 감지율(Recall) {fr}  "
        f"(목표 100%)  [{_symbol(t['forbidden_recall_pass'])}]"
    )
    print(
        f"  3. 오탐률               {m['false_positive_rate']*100:5.1f}%  "
        f"(목표 ≤ 5%)   [{_symbol(t['false_positive_rate_pass'])}]"
    )
    sa = f"{m['standards_accuracy']*100:.1f}%" if m["standards_accuracy"] is not None else "  N/A "
    print(
        f"  4. 기준규격 정확도      {sa}  "
        f"(목표 ≥90%)   [{_symbol(t['standards_accuracy_pass'])}]"
    )
    print(
        f"  5. HITL-1 전환율        {m['hitl1_rate']*100:5.1f}%  "
        f"(목표 ≤30%)   [{_symbol(t['hitl1_rate_pass'])}]"
    )
    print("-" * 62)
    overall = "ALL PASS" if summary["all_thresholds_pass"] else "NEEDS ATTENTION"
    print(f"  종합: {overall}")
    print("=" * 62)
    print()
    print("  카테고리별 verdict 일치율:")
    for cat, s in summary["category_accuracy"].items():
        bar = "#" * s["match"] + "." * (s["total"] - s["match"])
        print(f"    {cat:<36} {s['match']}/{s['total']}  [{bar}]")
    print()


# ==================================================================
# main
# ==================================================================


async def async_main(subset: str, output_path: Path, use_mock: bool) -> int:
    use_mock_env = os.environ.get("MOCK_API", "") == "1"
    effective_mock = use_mock or use_mock_env

    if not effective_mock:
        required = ["F1_DATA_GO_KR_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_KEY"]
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            print(f"[ERROR] 필수 env 미설정: {missing}", file=sys.stderr)
            print("[INFO]  mock 모드로 실행하려면 MOCK_API=1 을 설정하세요.", file=sys.stderr)
            return 2

    print(f"[INFO] subset={subset}  mock={'yes' if effective_mock else 'no'}")
    cases = load_all_cases(subset)
    print(f"[INFO] 케이스 {len(cases)}건 로드")
    print(f"[INFO] 출력: {output_path}")
    print()

    started_at = datetime.now(timezone.utc)
    t0 = time.monotonic()

    results: list[dict[str, Any]] = []
    for i, case in enumerate(cases, 1):
        name = case["case_name"]
        print(f"  [{i:02d}/{len(cases)}] {name:<44} ", end="", flush=True)
        r = await run_one_case(case, effective_mock)
        results.append(r)
        if r["error"]:
            print(f"ERROR  {r['error']['type']}: {r['error']['message'][:40]}")
        else:
            verdict_ok = "v:OK" if r["verdict_match"] else "v:NG"
            std_ok = "s:OK" if r["standards_match"] else "s:NG"
            fp = " FP!" if r["false_positive"] else ""
            print(f"{verdict_ok} {std_ok}{fp}  ({r['latency_ms']:.0f}ms)")

    total_ms = round((time.monotonic() - t0) * 1000, 1)
    finished_at = datetime.now(timezone.utc)

    summary = aggregate(results)
    print_summary(summary)

    output = {
        "run_meta": {
            "goldenset_version": "v3",
            "subset": subset,
            "mock": effective_mock,
            "total_cases": len(cases),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "total_ms": total_ms,
        },
        "summary": summary,
        "results": results,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False, indent=2)
    print(f"[INFO] 결과 저장: {output_path}")
    return 0 if summary["all_thresholds_pass"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="F1 골든셋 v3 평가 러너")
    parser.add_argument(
        "--subset",
        choices=["mini", "full"],
        default="mini",
        help="mini=5건(PR용) / full=전체(release용)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="결과 JSON 경로 (기본: tests/goldenset_run_v3_{datetime}.json)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="data.go.kr 실 API 미사용 mock 모드 (CI 단위 테스트용)",
    )
    args = parser.parse_args()

    if args.output is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        args.output = BACKEND_DIR / "tests" / f"goldenset_run_v3_{ts}.json"

    return asyncio.run(async_main(args.subset, args.output, args.mock))


if __name__ == "__main__":
    raise SystemExit(main())
