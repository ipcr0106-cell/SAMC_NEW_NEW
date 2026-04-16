"""
기능4: 수출국표시사항 검토 — 법령 DB 구축 전처리 스크립트

[처리 대상 법령 — DB_최신/5_행정규칙/]
  1. 식품등의 표시기준 (제2025-60호, 2025-08-29)
  2. 식품등의 한시적 기준 및 규격 인정 기준 (제2025-75호, 2025-12-02)
  3. 식품등의 부당한 표시 또는 광고의 내용 기준 (제2025-79호, 2025-12-04)
  4. 부당한 표시 또는 광고로 보지 아니하는 식품등의 기능성 표시 또는 광고에 관한 규정 (제2024-62호, 2025-01-01)

[처리 흐름]
  PDF 파싱 (pdfplumber)
    → 텍스트 정제 (머리글·쪽번호 제거, 줄바꿈 복원)
    → 조문 단위 청킹
    → multilingual-e5-large 임베딩
    → Pinecone 적재 (벡터 + 메타데이터)
    → Supabase law_documents 메타데이터 저장

[실행 방법]
  pip install -r requirements.txt
  .env 파일에 아래 키 설정 후 실행:
    PINECONE_API_KEY=...
    SUPABASE_URL=...
    SUPABASE_SERVICE_KEY=...    ← 대시보드 Settings > API > service_role 키
  python preprocess_laws.py
"""

import base64
import hashlib
import os
import re
import zipfile
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

import fitz  # pymupdf — 표 병합 셀 처리 + 이미지 페이지 렌더링
import pdfplumber
from openai import OpenAI
from dotenv import load_dotenv
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer
from supabase import create_client
from tqdm import tqdm

load_dotenv()

# =============================================================
# 설정
# =============================================================

BASE_DIR = Path(__file__).parent.parent.parent.parent  # 프로젝트 루트
LAW_DIR  = BASE_DIR / "DB_최신" / "5_행정규칙"

# 법령 계층 상수 (tier가 낮을수록 상위법 — RAG 우선순위에 활용)
TIER_법률    = 1
TIER_시행령  = 2
TIER_시행규칙 = 3
TIER_고시    = 4

LAW_FILES = [
    # ── 상위법 ──────────────────────────────────────────────────
    {
        "dir":      "1_법률",
        "file":     "식품 등의 표시ㆍ광고에 관한 법률(법률)(제20826호)(20250919).pdf",
        "law_name": "식품 등의 표시·광고에 관한 법률",
        "고시번호": "제20826호",
        "시행일":   date(2025, 9, 19),
        "category": "법률",
        "tier":     TIER_법률,
    },
    {
        "dir":      "2_시행령",
        "file":     "식품 등의 표시ㆍ광고에 관한 법률 시행령(대통령령)(제35734호)(20250919).pdf",
        "law_name": "식품 등의 표시·광고에 관한 법률 시행령",
        "고시번호": "제35734호",
        "시행일":   date(2025, 9, 19),
        "category": "시행령",
        "tier":     TIER_시행령,
    },
    {
        "dir":      "3_시행규칙",
        "file":     "식품 등의 표시ㆍ광고에 관한 법률 시행규칙(총리령)(제02004호)(20260101).pdf",
        "law_name": "식품 등의 표시·광고에 관한 법률 시행규칙",
        "고시번호": "제02004호",
        "시행일":   date(2026, 1, 1),
        "category": "시행규칙",
        "tier":     TIER_시행규칙,
    },
    # ── 고시 ────────────────────────────────────────────────────
    {
        "dir":      "5_행정규칙",
        "file":     "식품등의 표시기준(식품의약품안전처고시)(제2025-60호)(20250829).pdf",
        "law_name": "식품등의 표시기준",
        "고시번호": "제2025-60호",
        "시행일":   date(2025, 8, 29),
        "category": "표시기준",
        "tier":     TIER_고시,
    },
    {
        "dir":      "5_행정규칙",
        "file":     "식품등의 한시적 기준 및 규격 인정 기준(식품의약품안전처고시)(제2025-75호)(20251202).pdf",
        "law_name": "식품등의 한시적 기준 및 규격 인정 기준",
        "고시번호": "제2025-75호",
        "시행일":   date(2025, 12, 2),
        "category": "한시기준",
        "tier":     TIER_고시,
    },
    {
        "dir":      "5_행정규칙",
        "file":     "식품등의 부당한 표시 또는 광고의 내용 기준(식품의약품안전처고시)(제2025-79호)(20251204).pdf",
        "law_name": "식품등의 부당한 표시 또는 광고의 내용 기준",
        "고시번호": "제2025-79호",
        "시행일":   date(2025, 12, 4),
        "category": "부당광고",
        "tier":     TIER_고시,
    },
    {
        "dir":      "5_행정규칙",
        "file":     "부당한 표시 또는 광고로 보지 아니하는 식품등의 기능성 표시 또는 광고에 관한 규정(식품의약품안전처고시)(제2024-62호)(20250101).pdf",
        "law_name": "부당한 표시 또는 광고로 보지 아니하는 식품등의 기능성 표시 또는 광고에 관한 규정",
        "고시번호": "제2024-62호",
        "시행일":   date(2025, 1, 1),
        "category": "기능성허용",
        "tier":     TIER_고시,
    },
]

PINECONE_INDEX   = "samc-feature4-laws"
PINECONE_DIM     = 1024        # multilingual-e5-large 출력 차원
PINECONE_METRIC  = "cosine"
PINECONE_CLOUD   = "aws"
PINECONE_REGION  = "us-east-1"

EMBED_MODEL      = "intfloat/multilingual-e5-large"
EMBED_BATCH      = 32          # 한 번에 임베딩할 청크 수
UPSERT_BATCH     = 100         # Pinecone upsert 배치 크기

MAX_CHUNK_TOKENS = 400         # 청크 최대 토큰 수 (대략 글자 수로 환산 시 ×1.5)
OVERLAP_CHARS    = 100         # 청크 간 겹치는 문자 수 (문맥 연속성 유지)


# =============================================================
# PDF 텍스트 추출
# =============================================================

# 한국 정부 PDF에 반복되는 머리글·꼬리글 패턴
_HEADER_FOOTER_PATTERNS = [
    r"^- \d+ -$",                            # 페이지 번호  — ex) "- 12 -"
    r"^\d+$",                                # 단독 숫자
    r"^식품의약품안전처$",
    r"^식품의약품안전처 고시.*$",
    r"^「.*」.*고시전문$",
    r"^\[시행 \d{4}\. \d+\. \d+\.\].*$",    # 시행일 라인 (매 페이지 반복)
    r"^법제처 \d+ 국가법령정보센터$",          # 법제처 꼬리글
]
_HEADER_RE = re.compile("|".join(_HEADER_FOOTER_PATTERNS), re.MULTILINE)


def _clean_line(line: str) -> str:
    """줄 앞뒤 공백 제거."""
    return line.strip()


# PDF 하이퍼링크로 분리된 인라인 법령 참조 패턴
# ex) "제7조제2항,"  "제9조제1호"  "제5조제4항과"
_INLINE_REF_RE = re.compile(
    r"^제\d+조(?:의\d+)?"      # 제N조(의N)?
    r"(?:제\d+항)?"             # (제N항)?
    r"(?:제\d+호)?"             # (제N호)?
    r"[,\.\s과와및ㆍ]*$"        # 뒤에 구분자/접속사만 있음
)


def _merge_orphaned_refs(text: str) -> str:
    """
    PDF 하이퍼링크 추출로 인해 별도 줄로 분리된 인라인 법령 참조를 이전 줄에 병합.

    분리 패턴 예시:
      이 기준은 「식품위생법」        ← 본문
      제7조제2항,                    ← 하이퍼링크 텍스트가 별도 줄로 추출됨
      제9조제2항,                    ← 동일

    조건: 항(제N항) 또는 호(제N호) 참조가 있거나 구분자로 끝나는 경우만 병합
          (단독 제N조는 실제 조문 헤더일 수 있으므로 제외)
    """
    lines = text.split("\n")
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        is_inline = (
            stripped
            and _INLINE_REF_RE.match(stripped)
            and ("항" in stripped or "호" in stripped
                 or stripped[-1] in (",", ".", "과", "와", "및"))
        )
        if result and is_inline:
            result[-1] = result[-1].rstrip() + " " + stripped
        else:
            result.append(line)
    return "\n".join(result)


def _fix_line_breaks(text: str) -> str:
    """
    조문 경계 줄바꿈 정리:
    - 제목이 있는 조문(제N조(제목)) 앞에만 빈 줄 삽입
    - 제목 없는 단독 제N조는 이미 줄 시작에 있으면 그대로 유지
    - 항 번호(①②) 앞에 줄바꿈 보장
    """
    # 제N조(제목) 형태 — 실제 조문 헤더 → 앞에 빈 줄
    text = re.sub(r"(?<!\n)(제\d+조(?:의\d+)?\([^)]+\))", r"\n\n\1", text)
    # 항 번호 앞 줄바꿈
    text = re.sub(r"(?<!\n)(①|②|③|④|⑤|⑥|⑦|⑧|⑨|⑩)", r"\n\1", text)
    # 3개 이상 연속 줄바꿈 → 2개로 정리
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# =============================================================
# HWPX 파싱 공통 유틸
# =============================================================

def _local(elem) -> str:
    """네임스페이스를 제거하고 로컬 태그명만 반환. ex) {ns}tbl → tbl"""
    return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag


def _hwpx_sections(hwpx_path: Path) -> list[bytes]:
    """HWPX ZIP에서 section*.xml 파일들을 번호 순으로 읽어 반환."""
    if not zipfile.is_zipfile(hwpx_path):
        raise ValueError(f"유효한 HWPX 파일이 아닙니다: {hwpx_path}")
    with zipfile.ZipFile(hwpx_path, "r") as z:
        names = sorted(
            [f for f in z.namelist() if re.match(r"Contents/section\d+\.xml", f)],
            key=lambda x: int(re.search(r"\d+", x).group()),
        )
        if not names:
            raise ValueError(f"HWPX 내 section 파일 없음: {hwpx_path}")
        return [z.read(n) for n in names]


# =============================================================
# HWPX 텍스트 추출
# =============================================================

def extract_text_from_hwpx(hwpx_path: Path) -> str:
    """
    HWPX 본문 텍스트 추출.
    <hp:t> 노드를 수집 후 PDF와 동일한 정제 함수 적용.
    표 내부 텍스트도 포함됨 (별도 마크다운 표 변환은 extract_tables_hwpx에서).
    """
    pages_text: list[str] = []
    seen_lines: set[str] = set()

    for raw_xml in _hwpx_sections(hwpx_path):
        try:
            root = ET.fromstring(raw_xml)
        except ET.ParseError:
            raw = re.findall(
                r"<(?:[^:]+:)?t[^>]*>([^<]+)</", raw_xml.decode("utf-8", errors="ignore")
            )
            pages_text.append("\n".join(raw))
            continue

        para_lines: list[str] = []
        for elem in root.iter():
            if _local(elem) == "t" and elem.text:
                para_lines.append(elem.text)

        cleaned: list[str] = []
        for line in "\n".join(para_lines).splitlines():
            line = _clean_line(line)
            if not line or _HEADER_RE.match(line):
                continue
            if line in seen_lines and len(line) > 10:
                continue
            seen_lines.add(line)
            cleaned.append(line)

        pages_text.append("\n".join(cleaned))

    full_text = "\n".join(pages_text)
    full_text = _merge_orphaned_refs(full_text)
    full_text = _fix_line_breaks(full_text)
    return full_text


# =============================================================
# HWPX 표 추출
# =============================================================

def _hwpx_cell_text(tc_elem) -> str:
    """
    <hp:tc> 셀 내 텍스트 수집.
    직계 자식 중 중첩 <hp:tbl>은 건너뜀 (별도 표로 처리됨).
    """
    parts: list[str] = []
    for child in tc_elem:
        if _local(child) == "tbl":
            continue  # 중첩 표 내용은 별도 표로 추출
        for t in child.iter():
            if _local(t) == "t" and t.text:
                parts.append(t.text)
    return " ".join(parts).strip()


def _hwpx_tbl_to_markdown(tbl_elem) -> str:
    """
    <hp:tbl> 요소를 마크다운 표로 변환.
    병합 셀(colspan/rowspan)은 빈 칸으로 처리.
    """
    rows_data: list[list[str]] = []
    for child in tbl_elem:
        if _local(child) != "tr":
            continue
        cells = [_hwpx_cell_text(tc) for tc in child if _local(tc) == "tc"]
        if cells:
            rows_data.append(cells)

    if not rows_data:
        return ""

    max_cols = max(len(r) for r in rows_data)
    lines: list[str] = []
    for i, row in enumerate(rows_data):
        padded = row + [""] * (max_cols - len(row))
        lines.append("| " + " | ".join(padded) + " |")
        if i == 0:
            lines.append("|" + "---|" * max_cols)

    return "\n".join(lines)


def extract_tables_hwpx(hwpx_path: Path) -> list[str]:
    """
    HWPX에서 표를 추출하여 마크다운 형식으로 반환.

    처리 방식:
      section*.xml → <hp:tbl> 요소 탐색 → 행/셀 순서대로 마크다운 변환
      중첩 표는 각각 별도 표로 추출.
      상위 표에서 이미 처리된 하위 요소는 중복 처리하지 않음.
    """
    table_texts: list[str] = []

    for raw_xml in _hwpx_sections(hwpx_path):
        try:
            root = ET.fromstring(raw_xml)
        except ET.ParseError:
            continue

        processed_ids: set[int] = set()
        for elem in root.iter():
            if id(elem) in processed_ids or _local(elem) != "tbl":
                continue
            # 이 표의 모든 하위 요소를 처리된 것으로 표시 (중복 방지)
            for desc in elem.iter():
                processed_ids.add(id(desc))

            md = _hwpx_tbl_to_markdown(elem)
            if md and len(md.strip()) > 30:
                table_texts.append(md.strip())

    return table_texts


# =============================================================
# HWPX 이미지 추출 (AI Vision)
# =============================================================

# BinData/ 폴더 내 처리할 이미지 확장자와 최소 파일 크기
_HWPX_IMG_EXTS    = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff"}
_HWPX_IMG_MIN_SIZE = 50_000   # 50KB 미만 → 장식용 아이콘으로 간주, 건너뜀

_HWPX_MEDIA_TYPE: dict[str, str] = {
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".bmp":  "image/bmp",
    ".gif":  "image/gif",
    ".tif":  "image/tiff",
    ".tiff": "image/tiff",
}


def extract_image_pages_ai_hwpx(hwpx_path: Path, client: OpenAI) -> list[str]:
    """
    HWPX BinData/ 폴더의 이미지를 OpenAI Vision으로 텍스트 추출.

    선택 기준: 50KB 이상 이미지만 처리 (작은 로고·아이콘 제외).
    PDF 버전(extract_image_pages_claude)과 동일한 프롬프트 사용.
    """
    extracted: list[str] = []

    if not zipfile.is_zipfile(hwpx_path):
        return extracted

    with zipfile.ZipFile(hwpx_path, "r") as z:
        img_entries = [
            f for f in z.namelist()
            if f.startswith("BinData/")
            and Path(f).suffix.lower() in _HWPX_IMG_EXTS
            and z.getinfo(f).file_size >= _HWPX_IMG_MIN_SIZE
        ]

        for entry in img_entries:
            img_data   = z.read(entry)
            ext        = Path(entry).suffix.lower()
            media_type = _HWPX_MEDIA_TYPE.get(ext, "image/png")
            img_b64    = base64.b64encode(img_data).decode()

            try:
                response = client.chat.completions.create(
                    model="gpt-5.4-nano",
                    max_completion_tokens=1500,
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{media_type};base64,{img_b64}"},
                            },
                            {
                                "type": "text",
                                "text": (
                                    "이 한국 식품 법령 문서의 이미지에서 내용을 텍스트로 추출해주세요.\n"
                                    "- 표가 있으면 '항목 | 값' 형식으로 각 행을 표현\n"
                                    "- 도안/그림의 라벨 텍스트는 그대로 추출\n"
                                    "- 마크다운 없이 순수 텍스트로만 답해주세요"
                                ),
                            },
                        ],
                    }],
                )
                page_text = response.choices[0].message.content.strip()
                if page_text:
                    extracted.append(f"[{Path(entry).name} 이미지 추출]\n{page_text}")
            except Exception as e:
                print(f"  [경고] {entry} Vision 처리 실패: {e}")

    return extracted


# =============================================================
# 형식 자동 분기 dispatcher
# =============================================================

def _extract_text_auto(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext == ".hwpx":
        return extract_text_from_hwpx(file_path)
    raise ValueError(f"지원하지 않는 형식: {ext}  (지원: .pdf, .hwpx)")


def _extract_tables_auto(file_path: Path) -> list[str]:
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        return extract_tables_pymupdf(file_path)
    elif ext == ".hwpx":
        return extract_tables_hwpx(file_path)
    return []


def _extract_images_auto(file_path: Path, client: OpenAI) -> list[str]:
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        return extract_image_pages_ai(file_path, client)
    elif ext == ".hwpx":
        return extract_image_pages_ai_hwpx(file_path, client)
    return []


def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    pdfplumber로 본문 텍스트 추출 (조문 단위 청킹용).
    표는 pymupdf로 별도 처리하므로 여기서는 텍스트만 반환.
    """
    pages_text: list[str] = []
    seen_lines: set[str] = set()

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            raw = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            cleaned: list[str] = []

            for line in raw.splitlines():
                line = _clean_line(line)
                if not line or _HEADER_RE.match(line):
                    continue
                if line in seen_lines and len(line) > 10:
                    continue
                seen_lines.add(line)
                cleaned.append(line)

            pages_text.append("\n".join(cleaned))

    full_text = "\n".join(pages_text)
    full_text = _merge_orphaned_refs(full_text)
    full_text = _fix_line_breaks(full_text)
    return full_text


def _merge_cross_page_tables(table_infos: list[tuple[int, str]]) -> list[str]:
    """
    연속 페이지에 걸쳐 끊긴 표 파편을 병합.

    pymupdf는 페이지 단위로 표를 인식하므로, 페이지를 넘기는 표는
    두 개의 파편으로 추출됨:
      - 1페이지 파편: 헤더 + 일부 데이터 행  (정상)
      - 2페이지 파편: 실제 헤더 없음 → pymupdf가 첫 번째 데이터 행을 헤더로 오인

    병합 조건:
      - 연속 페이지(page_num 차이 = 1)
      - N페이지의 마지막 표와 N+1페이지의 첫 번째 표의 컬럼 수가 같음
    """
    if not table_infos:
        return []

    def parse(md: str) -> tuple[list[str], list[list[str]]]:
        """마크다운 표 → (헤더 목록, 데이터 행 목록)"""
        lines = [l.strip() for l in md.splitlines() if l.strip()]
        if len(lines) < 2:
            return [], []
        headers = [h.strip() for h in lines[0].strip("|").split("|") if h.strip()]
        data_rows = [
            [c.strip() for c in l.strip("|").split("|")]
            for l in lines[1:]
            if not _SEP_LINE_RE.match(l)
        ]
        return headers, data_rows

    def to_markdown(headers: list[str], data_rows: list[list[str]]) -> str:
        col = len(headers)
        lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * col]
        for row in data_rows:
            padded = (row + [""] * col)[:col]
            lines.append("| " + " | ".join(padded) + " |")
        return "\n".join(lines)

    result: list[str] = []
    i = 0
    while i < len(table_infos):
        page_num, md = table_infos[i]
        headers, data_rows = parse(md)

        # 연속 페이지의 첫 번째 표가 같은 컬럼 수이면 병합
        while (
            i + 1 < len(table_infos)
            and table_infos[i + 1][0] == page_num + 1  # 바로 다음 페이지
        ):
            next_page, next_md = table_infos[i + 1]
            next_headers, next_data = parse(next_md)
            if len(next_headers) != len(headers):
                break  # 컬럼 수 다름 → 별개 표
            # next_headers는 실제로는 첫 번째 데이터 행
            data_rows.append(next_headers)
            data_rows.extend(next_data)
            page_num = next_page
            i += 1

        if headers:
            result.append(to_markdown(headers, data_rows))
        else:
            result.append(md)  # 파싱 실패 시 원본 유지
        i += 1

    return result


def extract_tables_pymupdf(pdf_path: Path) -> list[str]:
    """
    pymupdf로 표 추출 — pdfplumber 대비 병합 셀(rowSpan/colSpan) 처리 정확.
    페이지 넘김으로 끊긴 표는 _merge_cross_page_tables()로 병합.
    """
    table_infos: list[tuple[int, str]] = []  # (page_num, markdown)
    doc = fitz.open(str(pdf_path))

    for page_num, page in enumerate(doc):
        try:
            tabs = page.find_tables()
            for tab in tabs:
                md = tab.to_markdown()
                if md and len(md.strip()) > 30:
                    table_infos.append((page_num, md.strip()))
        except Exception:
            pass  # 표 인식 실패 페이지는 건너뜀

    doc.close()
    return _merge_cross_page_tables(table_infos)


# 이미지 페이지 판단 기준: 이미지 N개 이상 & 텍스트 M자 미만
_IMAGE_PAGE_MIN_IMAGES = 3
_IMAGE_PAGE_MAX_TEXT   = 150


def extract_image_pages_ai(pdf_path: Path, client: OpenAI) -> list[str]:
    """
    이미지가 주를 이루는 페이지(도안, 서식 예시 등)를 OpenAI Vision으로 텍스트 추출.

    조건: 이미지 3개 이상 AND 텍스트 150자 미만인 페이지만 처리
    (텍스트가 충분한 페이지는 pdfplumber 결과로 충분)
    """
    extracted: list[str] = []
    doc = fitz.open(str(pdf_path))

    for page_num, page in enumerate(doc):
        images = page.get_images()
        text   = page.get_text().strip()

        if len(images) < _IMAGE_PAGE_MIN_IMAGES or len(text) > _IMAGE_PAGE_MAX_TEXT:
            continue

        # 페이지를 PNG로 렌더링 (2배 해상도)
        pix    = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_b64 = base64.b64encode(pix.tobytes("png")).decode()

        try:
            response = client.chat.completions.create(
                model="gpt-5.4-nano",
                max_completion_tokens=1500,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                        },
                        {
                            "type": "text",
                            "text": (
                                "이 한국 식품 법령 PDF 페이지의 내용을 텍스트로 추출해주세요.\n"
                                "- 표가 있으면 '항목 | 값' 형식으로 각 행을 표현\n"
                                "- 도안/그림의 라벨 텍스트는 그대로 추출\n"
                                "- 마크다운 없이 순수 텍스트로만 답해주세요"
                            ),
                        },
                    ],
                }],
            )
            page_text = response.choices[0].message.content.strip()
            if page_text:
                extracted.append(f"[p.{page_num + 1} 이미지 추출]\n{page_text}")
        except Exception as e:
            print(f"  [경고] p.{page_num + 1} Vision 처리 실패: {e}")

    doc.close()
    return extracted


# =============================================================
# 표 row 단위 직렬화
# =============================================================

_SEP_LINE_RE = re.compile(r"^\|[-| ]+\|$")  # |---|---| 구분선 감지


def _table_to_row_texts(markdown_table: str) -> list[str]:
    """
    마크다운 표를 row 단위 'col: val | col: val' 텍스트 목록으로 변환.

    목적: 표 전체를 단일 청크로 저장하면 컬럼-값 관계가 소실됨.
         row마다 컬럼 헤더를 붙여 저장해야 "공심환 → 공진단의 유사명칭" 같은
         관계가 retrieval/keyword 추출 시 보존됨.

    반환:
      - 헤더 파싱 성공 + 데이터 row 2개 이상: row별 텍스트 목록
      - 그 외(단일 row / 파싱 실패): [원본 markdown_table] — 손실 없이 원본 유지
    """
    lines = [l.strip() for l in markdown_table.splitlines() if l.strip()]
    if len(lines) < 3:  # 헤더 + 구분선 + 데이터 1행 최소
        return [markdown_table]

    # 헤더 추출 (첫 번째 줄)
    headers = [h.strip() for h in lines[0].strip("|").split("|")]
    headers = [h for h in headers if h]  # 빈 헤더 제거
    if not headers:
        return [markdown_table]

    # 데이터 행 (구분선 제외)
    data_lines = [l for l in lines[1:] if not _SEP_LINE_RE.match(l)]
    if not data_lines:
        return [markdown_table]

    row_texts: list[str] = []
    for line in data_lines:
        cells = [c.strip() for c in line.strip("|").split("|")]
        pairs = [
            f"{headers[i]}: {cells[i]}"
            for i in range(min(len(headers), len(cells)))
            if cells[i] and cells[i] not in ("-", "&amp;#45;") and headers[i]
        ]
        if pairs:
            row_texts.append(" | ".join(pairs))

    # row가 1개 이하면 원본 그대로 (단일 행 표는 쪼갤 필요 없음)
    return row_texts if len(row_texts) > 1 else [markdown_table]


def _add_table_chunks(
    chunks: list[dict],
    table_texts: list[str],
    law_name: str,
    고시번호: str,
    tier: int,
) -> None:
    """표 마크다운 목록을 row 단위로 변환해 chunks에 추가."""
    for t in table_texts:
        row_texts = _table_to_row_texts(t)
        for row_text in row_texts:
            chunks.append(_make_chunk(row_text, "별표/표", law_name, 고시번호, tier))


# =============================================================
# 조문 단위 청킹
# =============================================================

# 줄 맨 앞에서만 조문 번호 인식 (^ + MULTILINE)
# → 본문 중간의 인라인 참조(제7조제2항 등)는 청크 경계로 잡지 않음
_ARTICLE_RE = re.compile(r"^(제\d+조(?:의\d+)?(?:\([^)]+\))?)", re.MULTILINE)


def chunk_by_article(text: str, law_name: str, 고시번호: str, tier: int = TIER_고시) -> list[dict]:
    """
    조문(제N조) 단위로 청킹.
    조문이 MAX_CHUNK_TOKENS보다 길면 항(①②) 단위로 재분할.

    반환: [{"text": str, "조문번호": str, "law_name": str, "고시번호": str}, ...]
    """
    chunks: list[dict] = []
    parts = _ARTICLE_RE.split(text)

    # parts 구조: [앞부분, "제1조", 내용, "제2조", 내용, ...]
    # 짝수 인덱스 = 본문, 홀수 인덱스 = 조문번호
    i = 0
    current_article = "전문"  # 제1조 이전 전문(前文)

    while i < len(parts):
        if _ARTICLE_RE.fullmatch(parts[i].strip()):
            current_article = parts[i].strip()
            i += 1
            if i < len(parts):
                body = parts[i].strip()
                sub_chunks = _split_if_long(body, current_article, law_name, 고시번호, tier)
                chunks.extend(sub_chunks)
        else:
            body = parts[i].strip()
            if body:
                chunks.append(_make_chunk(body, current_article, law_name, 고시번호, tier))
        i += 1

    return [c for c in chunks if len(c["text"]) > 20]  # 너무 짧은 잔여 청크 제거


def _split_if_long(body: str, article: str, law_name: str, 고시번호: str, tier: int = TIER_고시) -> list[dict]:
    """조문 내용이 길면 항(①②③) 단위로 재분할."""
    # 대략적인 토큰 수 추정 (한국어 글자 1개 ≈ 1.5 토큰)
    if len(body) <= MAX_CHUNK_TOKENS * 1.5:
        return [_make_chunk(body, article, law_name, 고시번호, tier)]

    _PARA_RE = re.compile(r"(①|②|③|④|⑤|⑥|⑦|⑧|⑨|⑩)")
    parts = _PARA_RE.split(body)

    sub_chunks: list[dict] = []
    current_para = ""
    current_num  = ""

    for part in parts:
        if _PARA_RE.fullmatch(part):
            if current_para:
                label = f"{article}{current_num}"
                sub_chunks.append(_make_chunk(current_para.strip(), label, law_name, 고시번호, tier))
            current_num  = part
            current_para = part
        else:
            current_para += part

    if current_para:
        label = f"{article}{current_num}"
        sub_chunks.append(_make_chunk(current_para.strip(), label, law_name, 고시번호, tier))

    return sub_chunks if sub_chunks else [_make_chunk(body, article, law_name, 고시번호, tier)]


def _make_chunk(text: str, 조문번호: str, law_name: str, 고시번호: str, tier: int = TIER_고시) -> dict:
    return {
        "text":    f"[{law_name} {조문번호}]\n{text}",
        "조문번호": 조문번호,
        "law_name": law_name,
        "고시번호":  고시번호,
        "tier":     tier,
    }


# =============================================================
# 임베딩
# =============================================================

def embed_chunks(model: SentenceTransformer, chunks: list[dict]) -> list[list[float]]:
    """
    multilingual-e5-large 임베딩.
    문서(passage)에는 'passage: ' prefix 필수 (모델 명세).
    """
    texts = [f"passage: {c['text']}" for c in chunks]
    vectors: list[list[float]] = []

    for i in tqdm(range(0, len(texts), EMBED_BATCH), desc="  임베딩", leave=False):
        batch = texts[i : i + EMBED_BATCH]
        vecs = model.encode(batch, normalize_embeddings=True).tolist()
        vectors.extend(vecs)

    return vectors


# =============================================================
# Pinecone 적재
# =============================================================

def _make_vector_id(law_name: str, chunk_index: int) -> str:
    """
    법령명 + 청크 순서로 결정적(deterministic) 벡터 ID 생성.

    법령명만 사용하고 고시번호는 제외:
    → 법령 개정(고시번호 변경) 시 같은 ID로 upsert → 자동 덮어쓰기
    → 인덱스 삭제/재생성 없이 preprocess_laws.py 재실행으로 갱신 완료
    """
    raw = f"{law_name}|{chunk_index:05d}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def upsert_to_pinecone(
    index,
    chunks: list[dict],
    vectors: list[list[float]],
    law_doc_id: str,
) -> None:
    """청크 + 벡터를 Pinecone에 적재 (결정적 ID → 재실행 시 자동 갱신)."""
    records = []
    for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
        records.append({
            "id":     _make_vector_id(chunk["law_name"], i),
            "values": vec,
            "metadata": {
                "law_name":   chunk["law_name"],
                "고시번호":   chunk["고시번호"],
                "조문번호":   chunk["조문번호"],
                "법령_tier":  chunk["tier"],      # 1=법률 2=시행령 3=시행규칙 4=고시
                "law_doc_id": law_doc_id,
                "text":       chunk["text"][:1000],
            },
        })

    for i in tqdm(range(0, len(records), UPSERT_BATCH), desc="  Pinecone 적재", leave=False):
        index.upsert(vectors=records[i : i + UPSERT_BATCH])


# =============================================================
# 법령 고유 금지 마커 자동 추출 (extract_prohibited_keywords 동적 로드용)
# =============================================================

# 범용 금지 마커 — extract_prohibited_keywords._BASE_PROHIBITION_MARKERS와 동일한 패턴
# unmatched 청크 선별(②단계)에 사용. 두 파일이 분리되어 있으므로 여기서도 선언.
_BASE_PROHIBITION_MARKERS_FOR_HINTS = re.compile(
    r"하여서는\s*아니\s*된다|사용해서는\s*아니\s*된다|하지\s*못한다"
    r"|금지한다|금지된다|사용할\s*수\s*없다"
    r"|인식할\s*우려가\s*있는|의약품으로\s*인식"
    r"|부당한\s*표시\s*또는\s*광고|에\s*해당하는\s*표시"
    r"|거짓[ㆍ·]\s*과장|과장.*표시|허위.*표시"
    r"|소비자를\s*기만|오인[ㆍ·]\s*혼동|비방하는\s*표시|사행심을\s*조장"
    r"|사용하지\s*못하도록\s*정한|없거나\s*사용하지\s*않았다|한약의\s*처방명"
    r"|마약|대마|양귀비|아편|코카인|헤로인|모르핀|코데인|메스암페타민"
    r"|이온수|이온음료|생명수"
)


_HINT_EXTRACT_PROMPT = """\
아래 법령 조문에서 "금지 조문"을 탐지하기 위한 이 법령 고유의 키워드/어구를 추출해주세요.
추출된 어구는 금지 관련 청크를 필터링하는 데 사용됩니다.

[제외 — 이미 범용 필터에 포함됨]
- "아니 된다", "하지 못한다", "금지한다", "사용할 수 없다", "인식할 우려가 있는",
  "부당한 표시 또는 광고", "거짓·과장", "소비자를 기만", "오인·혼동", "비방하는 표시"

[추출 대상]
- 이 법령에만 있는 특수 용어, 물질명, 처방명, 금지 행위 묘사 어구
- 금지 동사 없이 명칭만 나열된 별표·목록 청크도 포함됩니다 (예: 마약류 명칭 목록)
  → 이런 경우 목록 항목 자체를 패턴으로 추출하세요
- 예) 마약류 명칭 법령 → ["마약", "대마", "양귀비", "아편", "코카인"]
- 예) 이온수 금지 법령 → ["이온수", "이온음료", "생명수"]
- 예) 한약 처방명 법령 → ["한약의 처방명"]
- 없으면 빈 배열 []

[법령명]
{law_name}

[법령 조문 샘플 — 전체 균등 분포 + 범용 패턴 미탐지 청크 우선 포함]
{text_sample}

JSON 배열로만 응답하세요: ["어구1", "어구2", ...]
"""


def _extract_prohibition_hints(
    chunks: list[dict],
    law_name: str,
    claude_client: OpenAI,
) -> list[str]:
    """
    법령 청크에서 이 법령 고유의 금지 마커 키워드를 AI로 추출.
    결과는 f4_law_documents.prohibition_hint_patterns에 저장되어
    extract_prohibited_keywords.py가 동적으로 로드해 사용함.

    누락 방지 3단계:
      ① 균등 분포 샘플링 — 앞/중간/뒤 골고루 (앞부분만 보고 뒤쪽 별표 놓치는 문제 방지)
      ② unmatched 청크 추가 샘플링 — 기본 마커에 안 걸리는 청크 집중 탐색
      ③ 히트 검증 — 추출된 패턴이 실제 청크에 존재하는지 확인 후 미히트 제거
    """
    import json as _json
    import re as _re

    if not chunks:
        return []

    # ① 전체 균등 분포 샘플 (최대 20개)
    step = max(1, len(chunks) // 20)
    uniform_chunks = chunks[::step][:20]

    # ② 기본 마커에 안 걸리는 청크 추가 샘플 (최대 10개) — 법령 고유 패턴 집중 탐색
    #    이쪽 청크들이 힌트가 없으면 fallback에서도 놓칠 수 있는 영역
    unmatched = [c for c in chunks if not _BASE_PROHIBITION_MARKERS_FOR_HINTS.search(c["text"])]
    step_u = max(1, len(unmatched) // 10)
    extra_chunks = unmatched[::step_u][:10]

    # 중복 제거 (id 기준이 없으므로 text 기준)
    seen: set[str] = set()
    combined: list[dict] = []
    for c in uniform_chunks + extra_chunks:
        if c["text"] not in seen:
            seen.add(c["text"])
            combined.append(c)

    sample = "\n\n".join(c["text"] for c in combined)[:6000]
    prompt = _HINT_EXTRACT_PROMPT.format(law_name=law_name, text_sample=sample)

    try:
        resp = claude_client.chat.completions.create(
            model="gpt-5.4-nano",
            max_completion_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.choices[0].message.content.strip()
        match = _re.search(r"\[.*\]", raw, _re.DOTALL)
        if not match:
            return []
        raw_hints = [h for h in _json.loads(match.group()) if isinstance(h, str) and h.strip()]

        # ③ 히트 검증 — 추출된 패턴이 실제 청크 어딘가에 존재하는지 확인
        all_text = " ".join(c["text"] for c in chunks)
        verified = [h for h in raw_hints if h in all_text]
        removed = len(raw_hints) - len(verified)
        if removed:
            print(f"  → 힌트 검증: {removed}개 미히트 패턴 제거 ({len(verified)}개 유지)")

        return verified

    except Exception as e:
        print(f"  [경고] 금지 마커 힌트 추출 실패: {e}")
        return []


# =============================================================
# Supabase 저장
# =============================================================

def save_law_document(supabase_client, law_info: dict, total_chunks: int, prohibition_hint_patterns: list[str] | None = None) -> str:
    """
    law_documents 테이블에 메타데이터 저장 후 UUID 반환.
    같은 law_name이 이미 있으면 갱신(upsert) — 재실행 시 중복 삽입 방지.
    """
    # 기존 레코드 조회
    existing = (
        supabase_client.table("f4_law_documents")
        .select("id")
        .eq("law_name", law_info["law_name"])
        .execute()
    )

    payload = {
        "law_name":     law_info["law_name"],
        "고시번호":     law_info["고시번호"],
        "시행일":       law_info["시행일"].isoformat(),
        "source_file":  law_info["file"],
        "법령_tier":    law_info["tier"],
        "total_chunks": total_chunks,
    }
    if prohibition_hint_patterns is not None:
        payload["prohibition_hint_patterns"] = prohibition_hint_patterns

    if existing.data:
        doc_id = existing.data[0]["id"]
        supabase_client.table("f4_law_documents").update(payload).eq("id", doc_id).execute()
        return doc_id
    else:
        res = supabase_client.table("f4_law_documents").insert(payload).execute()
        return res.data[0]["id"]


# =============================================================
# 단일 법령 처리 (업로드 API에서 호출)
# =============================================================

def preprocess_single_law(
    pdf_path: Path,
    law_name: str,
    고시번호: str,
    시행일: date,
    tier: int,
    category: str,
    index,
    supabase_client,
    model: SentenceTransformer,
    claude_client: OpenAI,
) -> dict:
    """
    단일 법령 파일(PDF 또는 HWPX)을 전처리하여 Pinecone + Supabase에 적재.
    관리자 업로드 API에서 호출됨.

    반환: {"law_doc_id": str, "total_chunks": int, "article_cnt": int, "table_cnt": int, "image_cnt": int}
    """
    law_info = {
        "law_name": law_name,
        "고시번호": 고시번호,
        "시행일":   시행일,
        "file":     pdf_path.name,
        "tier":     tier,
        "category": category,
    }

    # 1. 본문 텍스트 추출 (PDF/HWPX 자동 분기)
    text = _extract_text_auto(pdf_path)

    # 2. 조문 단위 청킹
    chunks = chunk_by_article(text, law_name, 고시번호, tier)
    article_cnt = len(chunks)

    # 3. 표 추출 (PDF: pymupdf / HWPX: XML <hp:tbl> 파싱)
    table_texts = _extract_tables_auto(pdf_path)
    _add_table_chunks(chunks, table_texts, law_name, 고시번호, tier)

    # 4. 이미지 추출 (PDF: pymupdf 렌더링 / HWPX: BinData/ 추출)
    image_texts = _extract_images_auto(pdf_path, claude_client)
    for t in image_texts:
        chunks.append(_make_chunk(t, "별표/도안", law_name, 고시번호, tier))

    # 5. 기존 청크 수 조회 (Pinecone 고아 벡터 삭제용)
    old_doc = (
        supabase_client.table("f4_law_documents")
        .select("total_chunks")
        .eq("law_name", law_name)
        .execute()
    )
    old_total = old_doc.data[0]["total_chunks"] if old_doc.data else 0

    # 6. 임베딩
    vectors = embed_chunks(model, chunks)

    # 7. 법령 고유 금지 마커 힌트 추출 (extract_prohibited_keywords에서 동적 로드용)
    print(f"  → 법령 고유 금지 마커 힌트 추출 중...")
    hint_patterns = _extract_prohibition_hints(chunks, law_name, claude_client)
    print(f"  → 힌트 패턴 {len(hint_patterns)}개: {hint_patterns}")

    # 8. Supabase 저장 (기존 법령이면 덮어씀)
    law_doc_id = save_law_document(supabase_client, law_info, len(chunks), hint_patterns)

    # 9. Pinecone 적재 (결정적 ID → 자동 덮어쓰기)
    upsert_to_pinecone(index, chunks, vectors, law_doc_id)

    # 10. 고아 벡터 삭제 — 개정으로 청크 수가 줄었을 때 이전 벡터 제거
    new_total = len(chunks)
    if old_total > new_total:
        orphan_ids = [_make_vector_id(law_name, i) for i in range(new_total, old_total)]
        for i in range(0, len(orphan_ids), 1000):
            index.delete(ids=orphan_ids[i : i + 1000])
        print(f"  → 고아 벡터 {len(orphan_ids)}개 삭제 (청크 {old_total} → {new_total})")

    return {
        "law_doc_id":   law_doc_id,
        "total_chunks": len(chunks),
        "article_cnt":  article_cnt,
        "table_cnt":    len(table_texts),
        "image_cnt":    len(image_texts),
    }


# =============================================================
# 메인 실행
# =============================================================

def main() -> None:
    # --- 환경변수 확인 ---
    pinecone_key  = os.getenv("F4_PINECONE_API_KEY")
    pinecone_host = os.getenv("F4_PINECONE_HOST")
    supabase_url  = os.getenv("SUPABASE_URL")
    supabase_key  = os.getenv("SUPABASE_SERVICE_KEY")

    if not all([pinecone_key, pinecone_host, supabase_url, supabase_key]):
        raise EnvironmentError(
            ".env 파일에 PINECONE_API_KEY, PINECONE_HOST, SUPABASE_URL, SUPABASE_SERVICE_KEY 가 모두 필요합니다."
        )

    # --- 클라이언트 초기화 ---
    print("▶ 클라이언트 초기화 중...")
    pc            = Pinecone(api_key=pinecone_key)
    supabase      = create_client(supabase_url, supabase_key)
    model         = SentenceTransformer(EMBED_MODEL)
    claude_client = OpenAI(api_key=os.getenv("F4_OPENAI_API_KEY"))

    # 인덱스는 대시보드에서 이미 생성됨 — host로 직접 연결
    index = pc.Index(host=pinecone_host)

    # --- 법령별 처리 ---
    for law_info in LAW_FILES:
        file_path = BASE_DIR / "DB_최신" / law_info["dir"] / law_info["file"]
        print(f"\n{'='*60}")
        print(f"▶ 처리 중: {law_info['law_name']}  [{file_path.suffix.upper()}]")

        if not file_path.exists():
            print(f"  [오류] 파일 없음: {file_path}")
            continue

        # 1. 본문 텍스트 추출 (PDF/HWPX 자동 분기)
        print("  1) 본문 텍스트 추출...")
        text = _extract_text_auto(file_path)

        # 2. 조문 단위 청킹
        print("  2) 조문 단위 청킹...")
        tier = law_info["tier"]
        chunks = chunk_by_article(text, law_info["law_name"], law_info["고시번호"], tier)
        article_cnt = len(chunks)

        # 3. 표 추출 (PDF: pymupdf / HWPX: XML <hp:tbl> 파싱)
        print("  3) 표 추출...")
        table_texts = _extract_tables_auto(file_path)
        _add_table_chunks(chunks, table_texts, law_info["law_name"], law_info["고시번호"], tier)

        # 4. 이미지 추출 (PDF: pymupdf 렌더링 / HWPX: BinData/ 추출)
        print("  4) 이미지 추출 (AI Vision)...")
        image_texts = _extract_images_auto(file_path, claude_client)
        for t in image_texts:
            chunks.append(_make_chunk(t, "별표/도안", law_info["law_name"], law_info["고시번호"], tier))

        print(f"     → 조문 {article_cnt}개 + 표 {len(table_texts)}개 + 이미지 {len(image_texts)}개 = 총 {len(chunks)}개 청크")

        # 5. 임베딩
        print("  5) 임베딩 생성...")
        vectors = embed_chunks(model, chunks)

        # 6. 법령 고유 금지 마커 힌트 추출
        print("  6) 금지 마커 힌트 추출 (AI)...")
        hint_patterns = _extract_prohibition_hints(chunks, law_info["law_name"], claude_client)
        print(f"     → 힌트 패턴 {len(hint_patterns)}개: {hint_patterns}")

        # 7. Supabase 메타데이터 저장
        print("  7) Supabase 저장...")
        law_doc_id = save_law_document(supabase, law_info, len(chunks), hint_patterns)

        # 8. Pinecone 적재
        print("  8) Pinecone 적재...")
        upsert_to_pinecone(index, chunks, vectors, law_doc_id)

        print(f"  ✓ 완료 (law_doc_id: {law_doc_id})")

    print(f"\n{'='*60}")
    print("✓ 전체 법령 DB 구축 완료")
    print(f"  Pinecone 인덱스: {PINECONE_INDEX}")
    print(f"  Supabase 테이블: f4_law_documents, f4_prohibited_expressions")


if __name__ == "__main__":
    main()
