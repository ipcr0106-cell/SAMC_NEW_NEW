"""
전처리 결과 검증 스크립트 — 실행 후 삭제해도 됨
확인 항목: 조문 청킹, 줄넘김/페이지넘김, 표, 이미지
"""
import re
import sys
from pathlib import Path

# UTF-8 파일 출력으로 변경 (Windows cp949 터미널 인코딩 우회)
_out_path = Path(__file__).parent / "verify_result.txt"
sys.stdout = open(_out_path, "w", encoding="utf-8")

import pdfplumber

BASE_DIR = Path(__file__).parent.parent.parent.parent
LAW_DIR  = BASE_DIR / "DB_최신" / "5_행정규칙"

LAW_FILES = [
    "식품등의 표시기준(식품의약품안전처고시)(제2025-60호)(20250829).pdf",
    "식품등의 한시적 기준 및 규격 인정 기준(식품의약품안전처고시)(제2025-75호)(20251202).pdf",
    "식품등의 부당한 표시 또는 광고의 내용 기준(식품의약품안전처고시)(제2025-79호)(20251204).pdf",
    "부당한 표시 또는 광고로 보지 아니하는 식품등의 기능성 표시 또는 광고에 관한 규정(식품의약품안전처고시)(제2024-62호)(20250101).pdf",
]

_HEADER_RE = re.compile(
    r"^- \d+ -$|^\d+$|^식품의약품안전처$|^식품의약품안전처 고시.*$"
    r"|^「.*」.*고시전문$|^\[시행 \d{{4}}\. \d+\. \d+\.\].*$|^법제처 \d+ 국가법령정보센터$",
    re.MULTILINE
)
_INLINE_REF_RE = re.compile(
    r"^제\d+조(?:의\d+)?(?:제\d+항)?(?:제\d+호)?[,\.\s과와및ㆍ]*$"
)
_ARTICLE_RE = re.compile(r"^(제\d+조(?:의\d+)?(?:\([^)]+\))?)", re.MULTILINE)

SEP = "=" * 60


def _merge_orphaned_refs(text: str) -> str:
    lines = text.split("\n")
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        is_inline = (
            stripped and _INLINE_REF_RE.match(stripped)
            and ("항" in stripped or "호" in stripped
                 or (stripped and stripped[-1] in (",", ".", "과", "와", "및")))
        )
        if result and is_inline:
            result[-1] = result[-1].rstrip() + " " + stripped
        else:
            result.append(line)
    return "\n".join(result)


def extract_raw(pdf_path):
    pages_text, tables_found, images_found = [], [], []
    seen_lines: set[str] = set()
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            raw = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            lines = []
            for l in raw.splitlines():
                l = l.strip()
                if not l or _HEADER_RE.match(l):
                    continue
                if l in seen_lines and len(l) > 10:
                    continue
                seen_lines.add(l)
                lines.append(l)
            pages_text.append((i + 1, "\n".join(lines)))

            tables = page.extract_tables()
            if tables:
                tables_found.append((i + 1, tables))

            if page.images:
                images_found.append((i + 1, len(page.images)))

    return pages_text, tables_found, images_found, total_pages


def clean_text(raw: str) -> str:
    text = _merge_orphaned_refs(raw)
    text = re.sub(r"(?<!\n)(제\d+조(?:의\d+)?\([^)]+\))", r"\n\n\1", text)
    text = re.sub(r"(?<!\n)(①|②|③|④|⑤)", r"\n\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def count_chunks(text: str) -> int:
    parts = _ARTICLE_RE.split(text)
    return max(1, (len(parts) - 1) // 2)


for fname in LAW_FILES:
    path = LAW_DIR / fname
    short = fname[:30] + "..."
    print(f"\n{SEP}")
    print(f"파일: {fname[:50]}")
    print(SEP)

    if not path.exists():
        print("  [오류] 파일 없음")
        continue

    pages_text, tables_found, images_found, total_pages = extract_raw(path)
    print(f"  총 페이지: {total_pages}")

    # ── 1. 조문 청킹 ──────────────────────────────────────
    full_raw   = "\n".join(t for _, t in pages_text)
    full_clean = clean_text(full_raw)
    chunk_cnt  = count_chunks(full_clean)

    articles = _ARTICLE_RE.findall(full_clean)
    print(f"\n[1] 조문 청킹")
    print(f"  인식된 조문 수: {len(articles)}개  →  예상 청크: {chunk_cnt}개")
    if articles:
        print(f"  첫 조문: {articles[0]}  /  마지막 조문: {articles[-1]}")

    # ── 2. 줄넘김·페이지 넘김 샘플 ───────────────────────
    print(f"\n[2] 페이지 경계 샘플 (p.1 끝 ~ p.2 시작)")
    if len(pages_text) >= 2:
        p1_tail = pages_text[0][1].strip().splitlines()[-3:]
        p2_head = pages_text[1][1].strip().splitlines()[:3]
        print("  < 1페이지 끝 >")
        for l in p1_tail:
            print(f"    {l}")
        print("  < 2페이지 시작 >")
        for l in p2_head:
            print(f"    {l}")

    # 정제 후 같은 구간 확인 (단어 잘림 복원됐는지)
    print(f"\n  < 정제 후 조문 경계 샘플 >")
    sample = full_clean[:600].strip()
    print("  " + sample.replace("\n", "\n  "))

    # ── 3. 표 처리 ────────────────────────────────────────
    print(f"\n[3] 표(Table) 감지")
    if tables_found:
        print(f"  표 발견: {len(tables_found)}개 페이지에서 총 {sum(len(t) for _,t in tables_found)}개")
        # 첫 번째 표 미리보기
        first_page, first_tables = tables_found[0]
        t = first_tables[0]
        print(f"  ▶ {first_page}페이지 첫 번째 표 (최대 3행 미리보기):")
        for row in t[:3]:
            cells = [str(c).strip() if c else "" for c in row]
            print(f"    {' | '.join(cells[:5])}")
    else:
        print("  표 없음 (또는 이미지로 삽입된 표라 감지 불가)")

    # ── 4. 이미지 처리 ────────────────────────────────────
    print(f"\n[4] 이미지 감지")
    if images_found:
        total_imgs = sum(cnt for _, cnt in images_found)
        print(f"  이미지 발견: {total_imgs}개 (페이지: {[p for p,_ in images_found]})")
        print(f"  ※ 현재 스크립트는 이미지를 텍스트로 변환하지 않음 → 해당 내용 누락됨")
        print(f"     → 법령 이미지는 대부분 장식용이므로 실무 영향 낮음")
        print(f"     → 만약 이미지 안에 표/조문이 있다면 Claude Vision 후처리 필요")
    else:
        print("  이미지 없음")

print(f"\n{SEP}")
print("검증 완료")
