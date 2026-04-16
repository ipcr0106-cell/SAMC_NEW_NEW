"""
[2단계] 청킹 (Pinecone용)
1단계에서 추출한 .txt 파일을 조항 단위로 잘게 자르고
preprocessing/chunks/ 폴더에 .json 파일로 저장합니다.

실행:
    python backend/scripts/step3_chunk.py

결과:
    preprocessing/chunks/foodtype_분류원칙.json
    preprocessing/chunks/alcohol_별표1.json
    ...

※ json 파일을 열어 청킹이 제대로 됐는지 확인 후 4단계로 진행하세요.
"""

import json
import re
from pathlib import Path

EXTRACT_DIR = Path("preprocessing/extracted")
CHUNK_DIR = Path("preprocessing/chunks")
CHUNK_DIR.mkdir(parents=True, exist_ok=True)

# Pinecone에 올라갈 파일 목록
PINECONE_FILES = [
    # (txt_name,                  law_name,              category)
    ("foodtype_분류원칙", "식품공전", "food_type"),
    ("alcohol_별표1", "주세법 시행령", "alcohol"),
    ("alcohol_별표3", "주세법 시행령", "alcohol"),
    ("foodcode_제1~5장", "식품공전", "food_standard"),
    ("foodcode_시험법1~3", "식품공전", "test_method"),
    ("foodcode_시험법4", "식품공전", "test_method"),
    ("foodcode_시험법5~6", "식품공전", "test_method"),
    ("foodcode_시험법7", "식품공전", "test_method"),
    ("foodcode_시험법8", "식품공전", "test_method"),
    ("foodcode_시험법10~12", "식품공전", "test_method"),
    ("foodcode_재검토기한", "식품공전", "food_standard"),
    ("foodcode_부칙", "식품공전", "food_standard"),
    ("container_기구용기기준", "기구및용기포장공전", "container"),
    ("additivecode_I~III", "식품첨가물공전", "additive"),
    ("additivecode_IV", "식품첨가물공전", "additive"),
    ("additivecode_V~VII", "식품첨가물공전", "additive"),
]


# ─────────────────────────────────────────
# 청킹 로직
# ─────────────────────────────────────────


def chunk_by_article(text: str, law_name: str, category: str) -> list[dict]:
    """
    조문(제X조) 또는 항목(○, ◆, ■ 등) 단위로 텍스트를 자름.
    각 조각은 최소 100자 이상만 유지.
    """
    # 조문 단위 분리 패턴 (제X조, 1., ○ 등)
    patterns = [
        r"(?=제\s*\d+\s*조)",  # 제1조, 제12조
        r"(?=\d+\.\s+[가-힣])",  # 1. 가나다
        r"(?=○\s)",  # ○ 항목
        r"(?=◆\s)",  # ◆ 항목
        r"(?=■\s)",  # ■ 항목
        r"(?=[①②③④⑤⑥⑦⑧⑨⑩])",  # 원형 숫자
    ]

    combined = "|".join(patterns)
    parts = re.split(combined, text)

    chunks = []
    for i, part in enumerate(parts):
        part = part.strip()
        if len(part) < 100:
            # 너무 짧으면 다음 조각에 합치기
            if chunks:
                chunks[-1]["text"] += " " + part
            continue

        chunks.append(
            {
                "id": f"{law_name}_{i:04d}",
                "text": part,
                "metadata": {
                    "law": law_name,
                    "category": category,
                    "chunk_index": i,
                    "char_count": len(part),
                },
            }
        )

    return chunks


def chunk_by_size(
    text: str, law_name: str, category: str, size: int = 800, overlap: int = 100
) -> list[dict]:
    """
    조문 구분이 어려운 경우 글자 수 기준으로 자름.
    overlap: 앞 조각과 겹치는 글자 수 (문맥 유지용)
    """
    chunks = []
    start = 0
    index = 0

    while start < len(text):
        end = min(start + size, len(text))
        part = text[start:end].strip()

        if len(part) >= 50:
            chunks.append(
                {
                    "id": f"{law_name}_{index:04d}",
                    "text": part,
                    "metadata": {
                        "law": law_name,
                        "category": category,
                        "chunk_index": index,
                        "char_count": len(part),
                    },
                }
            )
            index += 1

        start += size - overlap  # 다음 시작점 (overlap만큼 겹침)

    return chunks


def save_chunks(chunks: list[dict], output_name: str):
    out_path = CHUNK_DIR / f"{output_name}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    print(f"  → {len(chunks)}개 청크 저장: {out_path.name}")


# ─────────────────────────────────────────
# 실행
# ─────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("  3단계: 청킹 시작 (Pinecone용)")
    print("=" * 50)

    total_chunks = 0

    for txt_name, law_name, category in PINECONE_FILES:
        txt_path = EXTRACT_DIR / f"{txt_name}.txt"

        if not txt_path.exists():
            print(f"\n  [없음] {txt_name}.txt — 1단계 추출을 먼저 실행하세요")
            continue

        print(f"\n  처리 중: {txt_name}")
        text = txt_path.read_text(encoding="utf-8")

        # 조문 단위로 먼저 시도, 결과가 너무 적으면 크기 기준으로
        chunks = chunk_by_article(text, law_name, category)
        if len(chunks) < 5:
            print(f"    조문 구분 어려움 → 크기 기준(800자)으로 전환")
            chunks = chunk_by_size(text, law_name, category)

        save_chunks(chunks, txt_name)
        total_chunks += len(chunks)

    print("\n" + "=" * 50)
    print(f"  완료! 총 {total_chunks}개 청크 생성")
    print()
    print("  다음 할 일:")
    print("  1. preprocessing/chunks/ 폴더 열기")
    print("  2. .json 파일을 열어 청킹이 자연스럽게 됐는지 확인")
    print("  3. 이상 없으면 step4_upload_pinecone.py 실행")
    print("=" * 50)
