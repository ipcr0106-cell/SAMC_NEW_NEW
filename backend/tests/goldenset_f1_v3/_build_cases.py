"""골든셋 v3 케이스 디렉토리 빌더.

v2 JSON 100건에서 57건을 선별하여 v3 디렉토리 구조로 변환.
실행: cd backend && python tests/goldenset_f1_v3/_build_cases.py
"""
from __future__ import annotations

import json
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent.parent
V2_PATH = BACKEND / "tests" / "goldenset_f1_v2.json"
V3_DIR  = Path(__file__).resolve().parent / "cases"

# v3 선별 케이스 (v2 case_id → v3 디렉토리명)
SELECTED: list[tuple[str, str]] = [
    # permitted_db (10건)
    ("g001", "case_001_rice_permitted"),
    ("g002", "case_002_apple_permitted"),
    ("g003", "case_003_milk_permitted"),
    ("g031", "case_004_pork_permitted"),
    ("g033", "case_005_salmon_permitted"),
    ("g036", "case_006_sesame_permitted"),
    ("g037", "case_007_almond_permitted"),
    ("g039", "case_008_greentea_permitted"),
    ("g040", "case_009_redginseng_permitted"),
    ("g005", "case_010_ginseng_permitted"),
    # permitted_additive (6건)
    ("g008", "case_011_citric_acid_additive"),
    ("g009", "case_012_ascorbic_acid_additive"),
    ("g041", "case_013_carrageenan_additive"),
    ("g043", "case_014_steviol_additive"),
    ("g044", "case_015_sucralose_additive"),
    ("g045", "case_016_aspartame_additive"),
    # forbidden_drug (4건)
    ("g011", "case_017_cannabis_forbidden"),
    ("g012", "case_018_poppy_forbidden"),
    ("g013", "case_019_coca_leaf_forbidden"),
    ("g014", "case_020_thc_alias_forbidden"),
    # forbidden_endangered (3건)
    ("g046", "case_021_tiger_bone_forbidden"),
    ("g047", "case_022_pangolin_forbidden"),
    ("g048", "case_023_rhino_horn_forbidden"),
    # forbidden_unauthorized (4건)
    ("g049", "case_024_ephedra_forbidden"),
    ("g050", "case_025_senna_leaf_forbidden"),
    ("g052", "case_026_dmaa_forbidden"),
    ("g015", "case_027_kavakava_forbidden"),
    # forbidden_toxin (3건)
    ("g054", "case_028_comfrey_forbidden"),
    ("g055", "case_029_borage_forbidden"),
    ("g056", "case_030_aristolochia_forbidden"),
    # conditional_restricted_db (6건)
    ("g016", "case_031_guarana_restricted"),
    ("g057", "case_032_ginkgo_restricted"),
    ("g059", "case_033_wasabi_restricted"),
    ("g060", "case_034_senna_restricted"),
    ("g063", "case_035_licorice_restricted"),
    ("g065", "case_036_polygonum_restricted"),
    # conditional_heated (5건)
    ("g017", "case_037_sorbic_acid_heated_T"),
    ("g018", "case_038_sorbic_acid_heated_F"),
    ("g066", "case_039_benzoic_acid_heated_T"),
    ("g067", "case_040_benzoic_acid_heated_F"),
    ("g069", "case_041_propionic_acid_heated"),
    # conditional_fermented (5건)
    ("g021", "case_042_lactobacillus_fermented_T"),
    ("g022", "case_043_lactobacillus_fermented_F"),
    ("g072", "case_044_lacidophilus_fermented"),
    ("g074", "case_045_saccharomyces_fermented"),
    ("g075", "case_046_yeast_bread_fermented"),
    # conditional_alcohol (3건)
    ("g025", "case_047_ethanol_15pct"),
    ("g027", "case_048_ethanol_25pct"),
    ("g079", "case_049_ethanol_40pct"),
    # multi_ingredient_combo (5건)
    ("g080", "case_050_strawberry_jam_sub"),
    ("g085", "case_051_kimchi_composite"),
    ("g089", "case_052_hidden_cannabis_sub"),
    ("g097", "case_053_cannabis_sugar_mix"),
    ("g094", "case_054_honey_lemon_water"),
    # unidentified_virtual (3건)
    ("g028", "case_055_virtual_xenostin"),
    ("g029", "case_056_virtual_criovela"),
    ("g100", "case_057_virtual_bernium"),
]

# v3 verdict 매핑 (F1Output.verdict 형식)
VERDICT_MAP: dict[str, str] = {
    "permitted":   "permitted",
    "restricted":  "restricted",
    "prohibited":  "prohibited",
    "unidentified":"needs_review",
}

# Step C overall_status 기본값
STANDARDS_STATUS_MAP: dict[str, str] = {
    "permitted":   "pass",
    "restricted":  "review_needed",
    "prohibited":  "no_data",
    "unidentified":"no_data",
}


def derive_category(
    v2_exact: str,
    notes: str,
    ingredients: list[dict],
    process_conditions: dict,
    dir_name: str,
) -> str:
    has_sub = any("sub_ingredients" in i for i in ingredients)
    multi = len(ingredients) > 1
    notes_lower = notes.lower()

    if v2_exact == "prohibited":
        if any(k in notes for k in ["drug", "마약", "대마", "양귀비", "코카", "THC"]):
            return "forbidden_drug"
        if any(k in notes for k in ["endangered", "CITES", "야생"]):
            return "forbidden_endangered"
        if any(k in notes for k in ["toxin", "독성", "PA 알칼로이드"]):
            return "forbidden_toxin"
        return "forbidden_unauthorized"

    if v2_exact == "permitted":
        if has_sub or multi:
            return "multi_ingredient_combo"
        return "permitted_db"

    if v2_exact == "restricted":
        if has_sub or multi:
            return "multi_ingredient_combo"
        return "conditional_restricted_db"

    # unidentified — process_conditions 및 dir_name 기반 분기
    if "가상" in notes:
        return "unidentified_virtual"
    if has_sub or multi:
        return "multi_ingredient_combo"

    # dir_name 접미사 우선 (가장 명확한 신호)
    if "fermented" in dir_name:
        return "conditional_fermented"
    if "pct" in dir_name:
        return "conditional_alcohol"
    if "_heated_" in dir_name:
        return "conditional_heated"

    # process_conditions 실제 값 기반 분기
    if process_conditions.get("is_fermented") is True:
        return "conditional_fermented"
    if process_conditions.get("is_distilled") is not None or "alcohol_percentage" in process_conditions:
        return "conditional_alcohol"

    # 첨가물 케이스: is_heated=True 여도 additive가 핵심인 경우
    # notes에 "additive" / "첨가물" / "ppm" / "INS" 언급이 있으면 permitted_additive
    if any(k in notes for k in ["ppm", "additive", "첨가물", "INS", "f1_additive"]):
        return "permitted_additive"

    if process_conditions.get("is_heated") is True:
        return "conditional_heated"

    return "permitted_additive"


def expand_ingredient(ing: dict) -> dict:
    out: dict = {
        "name": ing["name"],
        "percentage": ing.get("percentage"),
    }
    for optional in ("part", "ins", "cas"):
        if ing.get(optional) is not None:
            out[optional] = ing[optional]
    if "sub_ingredients" in ing:
        out["sub_ingredients"] = [expand_ingredient(s) for s in ing["sub_ingredients"]]
    return out


def build() -> None:
    with open(V2_PATH, encoding="utf-8") as fh:
        v2 = json.load(fh)
    v2_map = {c["case_id"]: c for c in v2["cases"]}

    created = 0
    skipped = 0
    category_counter: dict[str, int] = {}

    for case_id, dir_name in SELECTED:
        if case_id not in v2_map:
            print(f"[WARN] {case_id} not in v2 — skip")
            skipped += 1
            continue

        c = v2_map[case_id]
        case_dir = V3_DIR / dir_name
        case_dir.mkdir(parents=True, exist_ok=True)

        v2_exact: str = c["expected_exact_verdict"]
        v3_verdict = VERDICT_MAP.get(v2_exact, "needs_review")
        notes: str = c.get("notes", "")
        ingredients: list[dict] = c["ingredients"]
        category = derive_category(
            v2_exact,
            notes,
            ingredients,
            c.get("process_conditions", {}),
            dir_name,
        )
        category_counter[category] = category_counter.get(category, 0) + 1

        # ── input_f0.json ──────────────────────────────────────
        input_f0 = {
            "_comment": (
                "F0 파싱 결과 고정 픽스처. "
                "HITL-0 승인 후 run_feature1_v2 에 전달되는 형태."
            ),
            "v3_case_id": f"v3_{dir_name}",
            "v2_source_id": case_id,
            "food_type": c.get("food_type"),
            "process_conditions": c.get("process_conditions", {}),
            "ingredients": [expand_ingredient(i) for i in ingredients],
            "doc_types": ["원재료_명세서", "성분_분석표"],
            "hitl0_approved": True,
        }

        # ── expected_verdict.json ──────────────────────────────
        is_forbidden = v2_exact == "prohibited"
        hitl1_required = v2_exact in ("restricted", "unidentified")

        expected_verdict = {
            "_comment": (
                "담당자 최종 판정 정답 라벨. "
                "v2 라벨 기반 v3 F1Output.verdict 형식으로 변환."
            ),
            "verdict": v3_verdict,
            "v2_exact_verdict": v2_exact,
            "v2_conflict_status": c.get("expected_conflict_status"),
            "is_forbidden_ingredient": is_forbidden,
            "hitl1_required": hitl1_required,
            "gmo_ingredients": [],
            "category": category,
            "notes": notes,
        }

        # ── expected_standards.json ────────────────────────────
        overall_status = STANDARDS_STATUS_MAP.get(v2_exact, "no_data")
        # 가열 조건 첨가물: review_needed 우선
        if v2_exact == "unidentified" and c.get("process_conditions", {}).get("is_heated"):
            overall_status = "review_needed"

        expected_standards = {
            "_comment": (
                "Step C 기준규격 기대값. "
                "실 API 연동 전 mock 비교 전용. "
                "Wave 4 P4 통합 검증 시 checks[] 를 실 API 결과로 채울 것."
            ),
            "overall_status": overall_status,
            "checks": [],
            "review_reasons": (
                ["비수치 기준 또는 식품유형 미매칭 가능"]
                if overall_status == "review_needed"
                else []
            ),
        }

        for fname, obj in [
            ("input_f0.json", input_f0),
            ("expected_verdict.json", expected_verdict),
            ("expected_standards.json", expected_standards),
        ]:
            with open(case_dir / fname, "w", encoding="utf-8") as fh:
                json.dump(obj, fh, ensure_ascii=False, indent=2)

        created += 1
        print(f"  [{created:02d}] {dir_name}  verdict={v3_verdict}  cat={category}")

    print()
    print(f"완료: {created}건 생성, {skipped}건 스킵")
    print("카테고리 분포:")
    for cat, cnt in sorted(category_counter.items()):
        print(f"  {cat:<32} {cnt}건")


if __name__ == "__main__":
    build()
