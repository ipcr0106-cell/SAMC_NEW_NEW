"""
F3 Step 4 — 식품공전 / 식품첨가물공전 HWPX 파서.

리뷰 반영:
  - HWPX <hp:t> 추출이 토큰 단위로 흩어지는 이슈 → 페이지/문단 단위로 재조립
  - 정규식 여러 패턴 시도 (table cell 기반 + 줄 기반)
  - MD 파일 업로드도 선택적 지원 (식약처가 MD 배포 시)
  - 명칭 검증: 숫자/특수문자만, 너무 긴/짧은 것 거부
  - 추출 결과 수가 기대치 (예: 식품공전 >500) 대비 적으면 경고

입력: .hwpx 또는 .md (식품공전 / 식품첨가물공전)
출력: f3_plant_based_patterns 행 JSON
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


# ──────────────────────────────────────────────
# HWPX / MD 텍스트 추출
# ──────────────────────────────────────────────

_HWPX_SECTION_RE = re.compile(r"Contents/section\d+\.xml")
_HWPX_SECTION_NUM_RE = re.compile(r"\d+")
_HWPX_T_FALLBACK_RE = re.compile(r"<(?:[^:]+:)?t[^>]*>([^<]+)</")


def _extract_hwpx(hwpx_path: Path) -> str:
    """HWPX 전체 텍스트. <hp:p> (문단) 단위로 합쳐서 <hp:t> 토큰이 흩어지지 않도록.

    개선: section/paragraph 구조를 존중해서 한 문단 내 <t> 들을 공백 없이 붙임.
    """
    if not zipfile.is_zipfile(hwpx_path):
        raise ValueError(f"유효한 HWPX 파일이 아닙니다: {hwpx_path}")

    paragraphs: list[str] = []
    with zipfile.ZipFile(hwpx_path, "r") as z:
        section_files = sorted(
            [f for f in z.namelist() if _HWPX_SECTION_RE.match(f)],
            key=lambda x: int(_HWPX_SECTION_NUM_RE.search(x).group()),
        )
        if not section_files:
            raise ValueError(f"HWPX 내 section 파일 없음: {hwpx_path}")

        for name in section_files:
            raw = z.read(name)
            try:
                root = ET.fromstring(raw)
                # <p> 또는 <hp:p> 문단 단위로 <t> 수집
                for p in root.iter():
                    tag = p.tag.split("}")[-1] if "}" in p.tag else p.tag
                    if tag != "p":
                        continue
                    texts: list[str] = []
                    for t in p.iter():
                        ttag = t.tag.split("}")[-1] if "}" in t.tag else t.tag
                        if ttag == "t" and t.text:
                            texts.append(t.text)
                    if texts:
                        paragraphs.append("".join(texts))
            except ET.ParseError:
                # XML 깨진 경우 — 단순 regex 로 <t> 모두 긁어오기
                matches = _HWPX_T_FALLBACK_RE.findall(
                    raw.decode("utf-8", errors="ignore")
                )
                paragraphs.extend(matches)
    return "\n".join(paragraphs)


def _extract_text_auto(file_path: Path) -> str:
    """확장자 자동 분기."""
    ext = file_path.suffix.lower()
    if ext == ".hwpx":
        return _extract_hwpx(file_path)
    if ext == ".md":
        return file_path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError(f"지원하지 않는 확장자: {ext} (.hwpx 또는 .md)")


# ──────────────────────────────────────────────
# 별표1 원료 목록 (식품공전)
# ──────────────────────────────────────────────

# 고유번호: A가/A나/... + 6자리 숫자 (기존 seed 파일 기준 A가XXXXXX)
_UNIQUE_ID = r"A[가나다라마바사아자차][\dA-Z]{6}"
_UNIQUE_ID_RE = re.compile(_UNIQUE_ID)

# 패턴 1: "A가000100 | 가는가래 | ..."  (MD 테이블)
_MD_TABLE_RE = re.compile(
    rf"\|\s*({_UNIQUE_ID})\s*\|\s*([가-힣A-Za-z][가-힣A-Za-z·()\-\s]{{1,40}}?)\s*\|"
)

# 패턴 2: "A가000100 가는가래 ..." (HWPX 추출 결과)
_INLINE_RE = re.compile(
    rf"({_UNIQUE_ID})\s+([가-힣A-Za-z][가-힣A-Za-z·()\-]{{1,40}})"
)


def _extract_byeolpyo1_from_foodcode(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(unique_id: str, name_raw: str):
        name = name_raw.strip()
        # 공백 · 특수문자 정리
        name = re.sub(r"\s+", "", name)
        # 명칭 검증
        if len(name) < 2 or len(name) > 30:
            return
        if not re.search(r"[가-힣A-Za-z]", name):
            return
        if name in seen:
            return
        seen.add(name)
        rows.append({
            "pattern": name,
            "category": "원료",
            "source": "식품공전 별표1",
            "reference": unique_id,
            "notes": "HWPX/MD 자동 추출 — 검역관 검토 필요",
        })

    # 1. MD 테이블 패턴 시도
    for m in _MD_TABLE_RE.finditer(text):
        _add(m.group(1), m.group(2))

    # 2. 인라인 패턴 (HWPX 추출 결과)
    if not rows:
        for m in _INLINE_RE.finditer(text):
            _add(m.group(1), m.group(2))

    # 3. 줄 기반 fallback (고유번호가 줄 맨 앞에 있는 경우)
    if not rows:
        for line in text.split("\n"):
            line = line.strip()
            m = _UNIQUE_ID_RE.match(line)
            if not m:
                continue
            unique_id = m.group(0)
            rest = line[m.end():].strip()
            name_match = re.match(r"([가-힣A-Za-z][가-힣A-Za-z·()\-]*)", rest)
            if not name_match:
                continue
            _add(unique_id, name_match.group(1))

    return rows


# ──────────────────────────────────────────────
# 별표1 향료 목록 (식품첨가물공전)
# ──────────────────────────────────────────────

# "1. 아세트알데하이드 (Acetaldehyde)" 형식
_NUMBERED_FRAGRANCE_RE = re.compile(
    r"^\s*(\d+)\.\s*([가-힣A-Za-z][가-힣A-Za-z0-9·()\-, ]{2,50})\s*$",
    re.MULTILINE,
)

# MD 테이블 형식: "| 1 | 아세트알데하이드 | Acetaldehyde | ... |"
_MD_FRAGRANCE_RE = re.compile(
    r"\|\s*\d+\s*\|\s*([가-힣][가-힣A-Za-z0-9·()\-, ]{2,50})\s*\|"
)


def _extract_byeolpyo1_from_additive(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(name_raw: str):
        name_full = name_raw.strip()
        # 괄호 앞까지만 (한글 명칭) 사용
        name = re.split(r"[(\[]", name_full, 1)[0].strip()
        if len(name) < 2 or len(name) > 40:
            return
        if not re.search(r"[가-힣A-Za-z]{2,}", name):
            return
        if name in seen:
            return
        seen.add(name)
        rows.append({
            "pattern": name,
            "category": "향료",
            "source": "식품첨가물공전",
            "reference": None,
            "notes": "HWPX/MD 자동 추출 — 정확도 제한적, 검역관 검토 필수",
        })

    # 1. MD 테이블 패턴
    for m in _MD_FRAGRANCE_RE.finditer(text):
        _add(m.group(1))

    # 2. 번호 매김 패턴
    if len(rows) < 10:
        for m in _NUMBERED_FRAGRANCE_RE.finditer(text):
            _add(m.group(2))

    return rows


# ──────────────────────────────────────────────
# 메인 파서
# ──────────────────────────────────────────────

# 예상 최소 추출 건수 (미달 시 경고)
_MIN_EXPECTED_FOODCODE = 300   # 식품공전 별표1 은 수천 건
_MIN_EXPECTED_ADDITIVE = 50    # 향료 목록은 수백 건


def parse(file_path: Path, law_name: str) -> dict:
    suffix = file_path.suffix.lower()
    if suffix not in (".hwpx", ".md"):
        raise ValueError(
            f"HWPX 또는 MD 파일만 지원합니다 (현재: {suffix}). "
            f"식품공전/첨가물공전은 한글 원본(.hwpx) 또는 변환된 MD 로 업로드하세요."
        )

    text = _extract_text_auto(file_path)
    if not text.strip():
        raise ValueError(f"텍스트 추출 결과 비어있음: {file_path.name}")

    warnings: list[str] = []

    if "식품첨가물공전" in law_name:
        rows = _extract_byeolpyo1_from_additive(text)
        if len(rows) < _MIN_EXPECTED_ADDITIVE:
            warnings.append(
                f"⚠️ 추출된 향료 {len(rows)}건 — 예상치({_MIN_EXPECTED_ADDITIVE}+) 대비 적습니다. "
                "업로드 파일이 별표1 향료목록이 맞는지 확인하세요."
            )
        warnings.append(
            f"식품첨가물공전 향료 목록에서 {len(rows)}건 추출. "
            "번호 체계가 다양해 일부 누락 가능 — 프리뷰에서 이상 항목 체크 해제하세요."
        )
    else:
        rows = _extract_byeolpyo1_from_foodcode(text)
        if len(rows) < _MIN_EXPECTED_FOODCODE:
            warnings.append(
                f"⚠️ 추출된 원료 {len(rows)}건 — 예상치({_MIN_EXPECTED_FOODCODE}+) 대비 적습니다. "
                "HWPX 구조가 다르거나 파일이 별표1 부분을 포함하지 않을 수 있습니다. "
                "반영 전 반드시 전수 확인하세요."
            )
        warnings.append(
            f"식품공전 별표1 원료목록에서 고유번호(A가XXXXXX) 기준으로 {len(rows)}건 추출."
        )
        warnings.append(
            "⚠️ 제5장 식품유형별 플래그(축산/반추/돼지) 자동 추출은 LLM 통합 이후 제공 예정. "
            "현재 업로드는 f3_food_type_categories 에는 영향을 주지 않습니다."
        )

    if not rows:
        raise ValueError(
            "추출된 행이 0건. HWPX 구조가 다르거나 본문에 패턴이 없을 수 있습니다. "
            "공전 원본 파일(또는 MD 변환본)인지 확인해주세요."
        )

    return {
        "tables": {
            "f3_plant_based_patterns": {
                "new_rows": rows,
                "pk_column": "pattern",
                # 소스별로 범위 제한 — 다른 source ('업계통용명' 등) 는 유지
                "scope_filter": {
                    "source": "식품첨가물공전" if "식품첨가물공전" in law_name else "식품공전 별표1"
                },
                "warnings": warnings,
            }
        },
        "warnings": warnings + [
            "⚠️ HWPX 파싱은 휴리스틱 기반으로 완벽하지 않습니다. 전수 검토하세요.",
        ],
        "pinecone_touched": False,
    }
