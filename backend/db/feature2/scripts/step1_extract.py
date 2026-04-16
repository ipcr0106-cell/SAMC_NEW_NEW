"""
[1단계] 텍스트 추출
DB_최신 폴더의 PDF/HWP/XLS 파일에서 텍스트를 꺼내
preprocessing/extracted/ 폴더에 .txt 파일로 저장합니다.

실행:
    python backend/scripts/step1_extract.py

결과:
    preprocessing/extracted/*.txt  (사람이 내용 확인 가능)
"""

import os
from pathlib import Path

import httpx
import pandas as pd
import pdfplumber
from dotenv import load_dotenv

load_dotenv("backend/.env")

DB_DIR = Path("DB_최신")
OUTPUT_DIR = Path("preprocessing/extracted")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────
# 추출 함수
# ─────────────────────────────────────────


def extract_pdf(file_path: Path) -> str:
    texts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            # 일반 텍스트 추출
            text = page.extract_text()
            if text:
                texts.append(text)

            # 표(table)가 있는 페이지는 별도로 추출
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    cleaned = [str(cell).strip() if cell else "" for cell in row]
                    texts.append("\t".join(cleaned))

    return "\n".join(texts)


def extract_hwp(file_path: Path) -> str:
    """parser-service(Node.js)에 파일을 보내 텍스트 받기"""
    url = os.getenv("PARSER_SERVICE_URL", "http://localhost:3001")
    token = os.getenv("PARSER_SERVICE_TOKEN", "")

    with open(file_path, "rb") as f:
        response = httpx.post(
            f"{url}/parse",
            files={"file": (file_path.name, f)},
            headers={"Authorization": f"Bearer {token}"},
            timeout=120.0,
        )
    response.raise_for_status()
    return response.json()["text"]


def extract_xlsx(file_path: Path) -> str:
    """엑셀의 모든 시트를 텍스트로 변환"""
    sheets = pd.read_excel(file_path, sheet_name=None)
    lines = []
    for sheet_name, df in sheets.items():
        lines.append(f"=== 시트: {sheet_name} ===")
        lines.append(df.to_csv(index=False, encoding="utf-8"))
    return "\n".join(lines)


def save_txt(content: str, output_name: str):
    out_path = OUTPUT_DIR / f"{output_name}.txt"
    out_path.write_text(content, encoding="utf-8")
    print(f"  → 저장: {out_path}  ({len(content):,}자)")


# ─────────────────────────────────────────
# Supabase 대상 파일 추출 (병찬 담당)
# ─────────────────────────────────────────

SUPABASE_FILES = {
    # ingredient_list 대상
    "1._식품첨가물_품목별_리스트(일반식품첨가물).pdf": ("pdf", "additive_01_일반"),
    "2._식품첨가물_품목별_리스트(가공보조제).pdf": ("pdf", "additive_02_가공보조제"),
    "3._식품첨가물_품목별_리스트(영양강화제).pdf": ("pdf", "additive_03_영양강화제"),
    "4._식품첨가물_품목별_리스트(혼합제제류).pdf": ("pdf", "additive_04_혼합제제류"),
    "5._식품첨가물_품목별_리스트(기구등의_살균소독제).pdf": (
        "pdf",
        "additive_05_살균소독제",
    ),
    "(5)_별표_1_별표_3_원료목록.hwpx": ("hwp", "ingredient_원료목록"),
    "(4)_별표_1_향료에_사용할_수_있는_물질_목록.hwpx": ("hwp", "ingredient_향료목록"),
    "(5)_별표_2_기구등의_살균소독제_목록_별표_3_식품첨가물_개정신청_사항_별표_4_식품첨가물_천연유래_인정_규정_등.hwpx": (
        "hwp",
        "ingredient_살균소독제목록",
    ),
    "(6)_일람표.hwpx": ("hwp", "additive_일람표"),
    # thresholds 대상
    "(참고자료)_농약_잔류허용기준_엑셀정리_화일_비규제_분리.xlsx": (
        "xlsx",
        "threshold_농약기준_엑셀",
    ),
    "(6)_별표_4_농약잔류허용기준_개정.hwpx": ("hwp", "threshold_농약기준"),
    "(7)_별표_5_동물용의약품_잔류허용기준.hwpx": ("hwp", "threshold_동물용의약품"),
    "(8)_별표_6_식품_중_농약_및_동물용의약품의_잔류허용기준_설정이_필요없는_물질.hwp": (
        "hwp",
        "threshold_기준불필요",
    ),
}

# ─────────────────────────────────────────
# Pinecone 대상 파일 추출 (아람 담당)
# ─────────────────────────────────────────

PINECONE_FILES = {
    "★식품유형분류원칙_최종.pdf": ("pdf", "foodtype_분류원칙"),
    "[별표 1] 주류에 혼합하거나 첨가할 수 있는 주류 또는 재료(제3조제1항 관련)(주세법 시행령).pdf": (
        "pdf",
        "alcohol_별표1",
    ),
    "[별표 3] 주류를 제조할 때의 주류 제조 원료의 사용량 및 여과방법 등(제3조제3항 관련)(주세법 시행령).pdf": (
        "pdf",
        "alcohol_별표3",
    ),
    "(1)_제1제5_개정.hwpx": ("hwp", "foodcode_제1~5장"),
    "(3-1)_제8.일반시험법_1__3.hwp": ("hwp", "foodcode_시험법1~3"),
    "(3-2)_제8.일반시험법_4._미생물시험법.hwp": ("hwp", "foodcode_시험법4"),
    "(3-3)_제8.일반시험법_5__6_개정.hwp": ("hwp", "foodcode_시험법5~6"),
    "(3-4)_제8._7._식품중_잔류농약_시험법_개정.hwpx": ("hwp", "foodcode_시험법7"),
    "(3-5)_제8._8._식품중_잔류동물용의약품_시험법.hwpx": ("hwp", "foodcode_시험법8"),
    "(3-7)_제8.일반시험법_10__12_개정.hwp": ("hwp", "foodcode_시험법10~12"),
    "(4)_제9._재검토기한.hwp": ("hwp", "foodcode_재검토기한"),
    "(9)_일람표_부칙(시행일_등)_개정.hwp": ("hwp", "foodcode_부칙"),
    "「기구및용기포장의기준및규격」고시전문(고시제2026-24호2026.3.27.)_최종.pdf": (
        "pdf",
        "container_기구용기기준",
    ),
    "(1)_I.총칙_II.일반_기준_및_규격_III.품목별_사용기준.hwpx": (
        "hwp",
        "additivecode_I~III",
    ),
    "(2)_IV.품목별_성분규격.hwpx": ("hwp", "additivecode_IV"),
    "(3)_V.일반시험법_VI.시약시액등_VII.재검토기한.hwpx": ("hwp", "additivecode_V~VII"),
}


# ─────────────────────────────────────────
# 실행
# ─────────────────────────────────────────


def run(target: str = "all"):
    """
    target: "supabase" | "pinecone" | "all"
    """
    files_to_process = {}

    if target in ("supabase", "all"):
        files_to_process.update(SUPABASE_FILES)
    if target in ("pinecone", "all"):
        files_to_process.update(PINECONE_FILES)

    print(f"총 {len(files_to_process)}개 파일 추출 시작\n")

    for filename, (file_type, output_name) in files_to_process.items():
        file_path = DB_DIR / filename
        if not file_path.exists():
            print(f"  [없음] {filename}")
            continue

        print(f"처리 중: {filename}")
        try:
            if file_type == "pdf":
                text = extract_pdf(file_path)
            elif file_type == "hwp":
                text = extract_hwp(file_path)
            elif file_type == "xlsx":
                text = extract_xlsx(file_path)
            else:
                print(f"  [건너뜀] 알 수 없는 형식: {file_type}")
                continue

            save_txt(text, output_name)

        except Exception as e:
            print(f"  [오류] {filename}: {e}")

    print(f"\n완료! preprocessing/extracted/ 폴더를 확인하세요.")
    print("텍스트가 제대로 추출됐는지 눈으로 확인한 후 2단계로 넘어가세요.")


if __name__ == "__main__":
    run("all")
