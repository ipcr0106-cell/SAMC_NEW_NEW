"""
[2단계] 구조화 (Supabase용) — LLM 없이 규칙 기반 파싱
1단계에서 추출한 .txt 파일을 규칙으로 읽어
테이블 형식의 .csv 파일로 정리합니다.

실행:
    python backend/scripts/step2_structure.py

결과:
    preprocessing/structured/ingredient_list.csv
    preprocessing/structured/thresholds.csv
"""

import re
from pathlib import Path

import pandas as pd

EXTRACT_DIR = Path("preprocessing/extracted")
STRUCT_DIR = Path("preprocessing/structured")
STRUCT_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────
# ingredient_list 파싱
# 형식:
#   한국어명
#   번호
#   (영문명)
# ─────────────────────────────────────────


def parse_additive_txt(txt_name: str, law_source: str) -> list[dict]:
    txt_path = EXTRACT_DIR / f"{txt_name}.txt"
    if not txt_path.exists():
        print(f"  [없음] {txt_path.name}")
        return []

    lines = [l.strip() for l in txt_path.read_text(encoding="utf-8").splitlines()]

    rows = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # 번호 줄 건너뜀 (숫자만 있는 줄)
        if re.fullmatch(r"\d+", line):
            i += 1
            continue

        # 헤더 줄 건너뜀
        if line in ("No. 품목명", "No.", "품목명", ""):
            i += 1
            continue

        # 영문명 줄 건너뜀 (괄호로 시작)
        if line.startswith("(") and line.endswith(")"):
            i += 1
            continue

        # 한국어 원료명으로 판단
        name_ko = line

        # 다음 줄에서 번호·영문명 찾기
        name_en = None
        j = i + 1
        while j < len(lines) and j < i + 4:
            nxt = lines[j]
            if nxt.startswith("(") and nxt.endswith(")"):
                name_en = nxt[1:-1].strip()  # 괄호 제거
                break
            j += 1

        if name_ko and len(name_ko) > 1:
            rows.append(
                {
                    "name_ko": name_ko,
                    "name_en": name_en,
                    "name_scientific": None,
                    "ins_number": None,
                    "cas_number": None,
                    "aliases": "",
                    "usage_condition": None,
                    "is_allowed": True,
                    "law_source": law_source,
                }
            )

        i += 1

    # 중복 제거
    seen = set()
    unique = []
    for r in rows:
        if r["name_ko"] not in seen:
            seen.add(r["name_ko"])
            unique.append(r)

    return unique


# ─────────────────────────────────────────
# thresholds 파싱 (엑셀 → CSV 형태)
# 형식: 농약명(한글),농약명(영어),식품명,잔류허용기준(mg/kg)
# ─────────────────────────────────────────


def parse_threshold_xlsx_txt(txt_name: str, law_source: str) -> list[dict]:
    txt_path = EXTRACT_DIR / f"{txt_name}.txt"
    if not txt_path.exists():
        print(f"  [없음] {txt_path.name}")
        return []

    lines = txt_path.read_text(encoding="utf-8").splitlines()

    # 헤더 행 찾기
    header_idx = None
    for i, line in enumerate(lines):
        if "농약명(한글)" in line:
            header_idx = i
            break

    if header_idx is None:
        print("  [경고] 헤더 행을 찾지 못했습니다.")
        return []

    rows = []
    for line in lines[header_idx + 1 :]:
        parts = line.split(",")
        if len(parts) < 4:
            continue

        name_ko = parts[0].strip().strip('"')
        food = parts[2].strip().strip('"')
        val_str = parts[3].strip().strip('"')

        if not name_ko or not val_str:
            continue
        try:
            value = float(val_str)
        except ValueError:
            continue

        rows.append(
            {
                "ingredient_name": name_ko,
                "food_type": food if food else "전체",
                "threshold_value": value,
                "unit": "mg/kg",
                "condition_text": None,
                "law_source": law_source,
                "is_verified": False,
            }
        )

    return rows


# ─────────────────────────────────────────
# CSV 저장
# ─────────────────────────────────────────


def save_to_csv(rows: list[dict], csv_path: Path):
    if not rows:
        print("  → 추출된 데이터 없음")
        return

    df_new = pd.DataFrame(rows)

    if csv_path.exists():
        df_old = pd.read_csv(csv_path, encoding="utf-8-sig")
        df = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df = df_new

    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"  → {len(rows)}개 행 추가  (누적 {len(df)}행)")


# ─────────────────────────────────────────
# 실행
# ─────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("  2단계: 구조화 시작 (규칙 기반)")
    print("=" * 50)

    ingredient_csv = STRUCT_DIR / "ingredient_list.csv"
    threshold_csv = STRUCT_DIR / "thresholds.csv"

    # ── ingredient_list ──────────────────
    print("\n[ingredient_list 구조화]")

    additive_files = [
        ("additive_01_일반", "식품첨가물공전"),
        ("additive_02_가공보조제", "식품첨가물공전"),
        ("additive_03_영양강화제", "식품첨가물공전"),
        ("additive_04_혼합제제류", "식품첨가물공전"),
        ("additive_05_살균소독제", "식품첨가물공전"),
    ]
    for txt_name, law_source in additive_files:
        print(f"\n  처리 중: {txt_name}")
        rows = parse_additive_txt(txt_name, law_source)
        print(f"  파싱된 항목 수: {len(rows)}개")
        save_to_csv(rows, ingredient_csv)

    # ── thresholds ───────────────────────
    print("\n[thresholds 구조화]")

    print("\n  처리 중: threshold_농약기준_엑셀")
    rows = parse_threshold_xlsx_txt("threshold_농약기준_엑셀", "식품공전 별표4")
    print(f"  파싱된 항목 수: {len(rows)}개")
    save_to_csv(rows, threshold_csv)

    print("\n" + "=" * 50)
    print("  완료!")
    print(f"  ingredient_list.csv : {ingredient_csv}")
    print(f"  thresholds.csv      : {threshold_csv}")
    print("=" * 50)
