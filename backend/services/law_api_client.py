"""
국가법령정보센터 Open API 클라이언트 — F4 법령 자동 업데이트용

[지원 API]
  - 현행법령(시행일) 목록 조회  : lawSearch  target=eflaw
  - 현행법령(시행일) 본문 조회  : lawService target=eflaw
  - 행정규칙 목록 조회          : lawSearch  target=admrul
  - 행정규칙 본문 조회          : lawService target=admrul

[F4 법령 7개]
  법령 3개 (조/항/호/목 분리) :
    1. 식품 등의 표시ㆍ광고에 관한 법률         MST=269957  ID=013094
    2. 식품 등의 표시ㆍ광고에 관한 법률 시행령    MST=273545  ID=013453
    3. 식품 등의 표시ㆍ광고에 관한 법률 시행규칙  MST=267855  ID=013475
  고시 4개 (조문내용 통째로) :
    4. 식품등의 표시기준                          LID=36814
    5. 식품등의 부당한 표시 또는 광고의 내용 기준  LID=69549
    6. 부당한 표시 또는 광고로 보지 아니하는
       식품등의 기능성 표시 또는 광고에 관한 규정  LID=75449
    7. 식품등의 한시적 기준 및 규격 인정 기준      LID=37975
"""

import os
import re
import logging
from xml.etree import ElementTree as ET
from typing import Optional

import httpx
from dotenv import load_dotenv

# chunk_by_article 재사용을 위해 preprocess_laws에서 임포트
from backend.db.feature4.preprocess_laws import (
    chunk_by_article,
    _make_chunk,
    MAX_CHUNK_TOKENS,
)

load_dotenv()
logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════
# 상수
# ════════════════════════════════════════════════════════════

LAW_API_BASE = "http://www.law.go.kr/DRF"
LAW_API_OC = os.getenv("LAW_API_OC", "Ipcr0618")

# 법령 계층 (preprocess_laws.py와 동일)
TIER_법률    = 1
TIER_시행령  = 2
TIER_시행규칙 = 3
TIER_고시    = 4

# F4 법령 7개 — ID 레지스트리
F4_LAW_REGISTRY = [
    # ── 법령 3개 (target=eflaw, ID로 현행 본문 조회) ──
    {
        "law_name": "식품 등의 표시·광고에 관한 법률",
        "api_type": "eflaw",
        "api_id":   "013094",       # 법령ID → 항상 현행 본문 반환
        "api_mst":  "269957",       # MST (법령일련번호)
        "tier":     TIER_법률,
    },
    {
        "law_name": "식품 등의 표시·광고에 관한 법률 시행령",
        "api_type": "eflaw",
        "api_id":   "013453",
        "api_mst":  "273545",
        "tier":     TIER_시행령,
    },
    {
        "law_name": "식품 등의 표시·광고에 관한 법률 시행규칙",
        "api_type": "eflaw",
        "api_id":   "013475",
        "api_mst":  "267855",
        "tier":     TIER_시행규칙,
    },
    # ── 고시 4개 (target=admrul, LID로 조회) ──
    {
        "law_name": "식품등의 표시기준",
        "api_type": "admrul",
        "api_id":   "36814",        # 행정규칙ID (LID)
        "tier":     TIER_고시,
    },
    {
        "law_name": "식품등의 부당한 표시 또는 광고의 내용 기준",
        "api_type": "admrul",
        "api_id":   "69549",
        "tier":     TIER_고시,
    },
    {
        "law_name": "부당한 표시 또는 광고로 보지 아니하는 식품등의 기능성 표시 또는 광고에 관한 규정",
        "api_type": "admrul",
        "api_id":   "75449",
        "tier":     TIER_고시,
    },
    {
        "law_name": "식품등의 한시적 기준 및 규격 인정 기준",
        "api_type": "admrul",
        "api_id":   "37975",
        "tier":     TIER_고시,
    },
]


# ════════════════════════════════════════════════════════════
# HTTP 헬퍼
# ════════════════════════════════════════════════════════════

def _fetch_xml(url: str, params: dict, timeout: float = 30.0) -> ET.Element:
    """API 호출 → XML Element 반환."""
    params["OC"] = LAW_API_OC
    params["type"] = "XML"
    resp = httpx.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return ET.fromstring(resp.content)


# ════════════════════════════════════════════════════════════
# 법령 (eflaw) — 조/항/호/목 분리 파싱
# ════════════════════════════════════════════════════════════

def _find_text(el: ET.Element, tag: str, default: str = "") -> str:
    """태그명으로 텍스트를 찾되, CDATA 등 공백 정리."""
    node = el.find(tag)
    if node is None or node.text is None:
        return default
    return node.text.strip()


def fetch_eflaw_meta(law_id: str) -> dict:
    """
    법령 목록 조회로 메타데이터(공포일자, 시행일자 등) 가져오기.
    법령ID(LID)로 검색하면 정확히 1건 반환.
    """
    root = _fetch_xml(
        f"{LAW_API_BASE}/lawSearch.do",
        {"target": "eflaw", "LID": law_id},
    )
    law_el = root.find(".//law")
    if law_el is None:
        raise ValueError(f"법령 ID={law_id} 검색 결과 없음")
    return {
        "법령명":     _find_text(law_el, "법령명한글"),
        "법령ID":     _find_text(law_el, "법령ID"),
        "법령일련번호": _find_text(law_el, "법령일련번호"),
        "공포일자":   _find_text(law_el, "공포일자"),
        "시행일자":   _find_text(law_el, "시행일자"),
        "제개정구분명": _find_text(law_el, "제개정구분명"),
    }


def fetch_eflaw_body(law_id: str) -> dict:
    """
    현행법령 본문 조회 → 조문 + 별표 파싱.

    반환:
      {
        "meta": { 법령명, 공포일자, 시행일자, ... },
        "articles": [
          { "조문번호": "1", "조문제목": "목적", "조문내용": "...",
            "항": [ { "항번호": "①", "항내용": "...",
                      "호": [ { "호번호": "1.", "호내용": "...",
                                "목": [ { "목번호": "가.", "목내용": "..." } ] } ] } ] }
        ],
        "별표": [
          { "별표번호": 1, "별표제목": "...", "별표내용": "...",
            "별표서식파일링크": "..." }
        ],
      }
    """
    root = _fetch_xml(
        f"{LAW_API_BASE}/lawService.do",
        {"target": "eflaw", "ID": law_id},
        timeout=60.0,
    )

    # ── 기본정보 ──
    info = root.find("기본정보")
    meta = {}
    if info is not None:
        meta = {
            "법령명":   _find_text(info, "법령명_한글"),
            "법령ID":   _find_text(info, "법령ID"),
            "공포일자": _find_text(info, "공포일자"),
            "시행일자": _find_text(info, "시행일자"),
            "제개정구분": _find_text(info, "제개정구분"),
        }

    # ── 조문 파싱 ──
    articles = []
    for jo in root.iter("조문단위"):
        article = {
            "조문번호":     _find_text(jo, "조문번호"),
            "조문가지번호": _find_text(jo, "조문가지번호"),
            "조문제목":     _find_text(jo, "조문제목"),
            "조문내용":     _find_text(jo, "조문내용"),
            "조문시행일자": _find_text(jo, "조문시행일자"),
            "조문변경여부": _find_text(jo, "조문변경여부"),
            "항": [],
        }
        for hang in jo.findall("항"):
            hang_data = {
                "항번호": _find_text(hang, "항번호"),
                "항내용": _find_text(hang, "항내용"),
                "호": [],
            }
            for ho in hang.findall("호"):
                ho_data = {
                    "호번호": _find_text(ho, "호번호"),
                    "호내용": _find_text(ho, "호내용"),
                    "목": [],
                }
                for mok in ho.findall("목"):
                    mok_data = {
                        "목번호": _find_text(mok, "목번호"),
                        "목내용": _find_text(mok, "목내용"),
                    }
                    ho_data["목"].append(mok_data)
                hang_data["호"].append(ho_data)
            article["항"].append(hang_data)
        articles.append(article)

    # ── 별표 파싱 ──
    별표_list = []
    for bt in root.iter("별표단위"):
        별표_list.append({
            "별표번호":       _find_text(bt, "별표번호"),
            "별표가지번호":   _find_text(bt, "별표가지번호"),
            "별표제목":       _find_text(bt, "별표제목"),
            "별표내용":       _find_text(bt, "별표내용"),
            "별표서식파일링크": _find_text(bt, "별표서식파일링크"),
        })

    return {"meta": meta, "articles": articles, "별표": 별표_list}


# ════════════════════════════════════════════════════════════
# 행정규칙 (admrul) — 고시 본문 조회
# ════════════════════════════════════════════════════════════

def fetch_admrul_meta(lid: str) -> dict:
    """
    행정규칙 목록 조회로 메타데이터 가져오기.
    LID(행정규칙ID)로 직접 본문 조회한 뒤 기본정보에서 추출.
    """
    root = _fetch_xml(
        f"{LAW_API_BASE}/lawService.do",
        {"target": "admrul", "LID": lid},
        timeout=60.0,
    )
    info = root.find("행정규칙기본정보")
    if info is None:
        raise ValueError(f"행정규칙 LID={lid} 조회 실패")
    return {
        "행정규칙명":     _find_text(info, "행정규칙명"),
        "행정규칙ID":     _find_text(info, "행정규칙ID"),
        "행정규칙일련번호": _find_text(info, "행정규칙일련번호"),
        "발령일자":       _find_text(info, "발령일자"),
        "발령번호":       _find_text(info, "발령번호"),
        "시행일자":       _find_text(info, "시행일자"),
        "제개정구분명":   _find_text(info, "제개정구분명"),
        "조문형식여부":   _find_text(info, "조문형식여부"),
        "현행여부":       _find_text(info, "현행여부"),
    }


def fetch_admrul_body(lid: str) -> dict:
    """
    행정규칙 본문 조회 → 조문내용 + 별표 파싱.

    반환:
      {
        "meta": { 행정규칙명, 발령일자, 발령번호, 시행일자, ... },
        "조문내용_list": [ "제1조(목적) ...", "제2조(정의) ...", ... ],
        "별표": [
          { "별표번호": 1, "별표제목": "...", "별표내용": "...",
            "별표서식파일링크": "..." }
        ],
      }
    """
    root = _fetch_xml(
        f"{LAW_API_BASE}/lawService.do",
        {"target": "admrul", "LID": lid},
        timeout=60.0,
    )

    # ── 기본정보 ──
    info = root.find("행정규칙기본정보")
    meta = {}
    if info is not None:
        meta = {
            "행정규칙명":     _find_text(info, "행정규칙명"),
            "행정규칙ID":     _find_text(info, "행정규칙ID"),
            "행정규칙일련번호": _find_text(info, "행정규칙일련번호"),
            "발령일자":       _find_text(info, "발령일자"),
            "발령번호":       _find_text(info, "발령번호"),
            "시행일자":       _find_text(info, "시행일자"),
            "조문형식여부":   _find_text(info, "조문형식여부"),
        }

    # ── 조문내용 (여러 <조문내용> 태그) ──
    조문_list = []
    for el in root.findall("조문내용"):
        text = (el.text or "").strip()
        if text:
            조문_list.append(text)

    # ── 별표 파싱 ──
    별표_list = []
    for bt in root.iter("별표단위"):
        별표_list.append({
            "별표번호":       _find_text(bt, "별표번호"),
            "별표가지번호":   _find_text(bt, "별표가지번호"),
            "별표제목":       _find_text(bt, "별표제목"),
            "별표내용":       _find_text(bt, "별표내용"),
            "별표서식파일링크": _find_text(bt, "별표서식파일링크"),
        })

    return {"meta": meta, "조문내용_list": 조문_list, "별표": 별표_list}


# ════════════════════════════════════════════════════════════
# 행정규칙 LID fallback — 이름으로 재검색
# ════════════════════════════════════════════════════════════

def search_admrul_by_name(name: str) -> Optional[dict]:
    """
    행정규칙명으로 검색하여 현행 고시의 메타정보 반환.
    LID가 개정으로 변경된 경우 fallback으로 사용.
    """
    root = _fetch_xml(
        f"{LAW_API_BASE}/lawSearch.do",
        {"target": "admrul", "query": name, "nw": "1", "knd": "3"},
    )
    for admrul in root.iter("admrul"):
        found_name = _find_text(admrul, "행정규칙명")
        if found_name == name:
            return {
                "행정규칙명":     found_name,
                "행정규칙ID":     _find_text(admrul, "행정규칙ID"),
                "행정규칙일련번호": _find_text(admrul, "행정규칙일련번호"),
                "발령일자":       _find_text(admrul, "발령일자"),
                "발령번호":       _find_text(admrul, "발령번호"),
                "시행일자":       _find_text(admrul, "시행일자"),
            }
    return None


# ════════════════════════════════════════════════════════════
# 통합 인터페이스 — 법령 유형에 관계없이 본문 가져오기
# ════════════════════════════════════════════════════════════

def fetch_law_body(registry_entry: dict) -> dict:
    """
    F4_LAW_REGISTRY의 항목 하나를 받아 본문을 가져온다.
    api_type에 따라 eflaw/admrul 분기.
    """
    api_type = registry_entry["api_type"]
    api_id = registry_entry["api_id"]

    if api_type == "eflaw":
        return fetch_eflaw_body(api_id)
    elif api_type == "admrul":
        try:
            return fetch_admrul_body(api_id)
        except Exception as e:
            # LID 실패 시 이름으로 fallback
            logger.warning(
                "LID=%s 조회 실패 (%s), 이름으로 재검색", api_id, e
            )
            info = search_admrul_by_name(registry_entry["law_name"])
            if info is None:
                raise ValueError(
                    f"행정규칙 '{registry_entry['law_name']}' 이름 검색도 실패"
                ) from e
            new_lid = info["행정규칙ID"]
            logger.info("새 LID=%s 로 재시도", new_lid)
            return fetch_admrul_body(new_lid)
    else:
        raise ValueError(f"알 수 없는 api_type: {api_type}")


def fetch_law_meta(registry_entry: dict) -> dict:
    """
    F4_LAW_REGISTRY의 항목 하나를 받아 메타정보를 가져온다.
    변경 감지(공포일자/발령일자 비교)에 사용.
    """
    api_type = registry_entry["api_type"]
    api_id = registry_entry["api_id"]

    if api_type == "eflaw":
        return fetch_eflaw_meta(api_id)
    elif api_type == "admrul":
        try:
            return fetch_admrul_meta(api_id)
        except Exception as e:
            logger.warning(
                "LID=%s 메타 조회 실패 (%s), 이름으로 재검색", api_id, e
            )
            info = search_admrul_by_name(registry_entry["law_name"])
            if info is None:
                raise ValueError(
                    f"행정규칙 '{registry_entry['law_name']}' 이름 검색도 실패"
                ) from e
            return fetch_admrul_meta(info["행정규칙ID"])
    else:
        raise ValueError(f"알 수 없는 api_type: {api_type}")


# ════════════════════════════════════════════════════════════
# XML → 청크 변환 (기존 _make_chunk 포맷 호환)
# ════════════════════════════════════════════════════════════

def _eflaw_articles_to_chunks(
    body: dict, law_name: str, 고시번호: str, tier: int
) -> list[dict]:
    """
    법령(eflaw) API 응답의 조/항/호/목 구조를 청크로 변환.
    조문 단위로 텍스트를 조합하고, 길면 항 단위로 분할.
    """
    chunks = []

    for article in body["articles"]:
        조번호 = article["조문번호"]
        가지 = article["조문가지번호"]
        제목 = article["조문제목"]

        # "제N조" 또는 "제N조의M" 형태
        if 가지 and 가지 != "0":
            article_label = f"제{조번호}조의{가지}"
        else:
            article_label = f"제{조번호}조"
        if 제목:
            article_label += f"({제목})"

        # 항이 없으면 조문내용 그대로
        if not article["항"]:
            text = article["조문내용"]
            if text:
                chunks.append(_make_chunk(text, article_label, law_name, 고시번호, tier))
            continue

        # 항이 있으면 항별로 텍스트 조합
        full_text_parts = []
        hang_chunks = []

        for hang in article["항"]:
            hang_text = hang["항내용"]
            # 호/목 내용도 항 아래에 붙이기
            for ho in hang.get("호", []):
                hang_text += f"\n  {ho['호내용']}"
                for mok in ho.get("목", []):
                    hang_text += f"\n    {mok['목내용']}"

            full_text_parts.append(hang_text)
            hang_chunks.append((hang["항번호"].strip(), hang_text))

        # 전체 조문이 MAX_CHUNK_TOKENS 이내면 하나의 청크
        full_text = "\n".join(full_text_parts)
        if len(full_text) <= MAX_CHUNK_TOKENS * 1.5:
            chunks.append(_make_chunk(full_text, article_label, law_name, 고시번호, tier))
        else:
            # 항 단위로 분할
            for hang_num, hang_text in hang_chunks:
                label = f"{article_label}{hang_num}"
                chunks.append(_make_chunk(hang_text, label, law_name, 고시번호, tier))

    return chunks


_BOX_DRAWING_RE = re.compile(
    r"[\u2500-\u257F\u2580-\u259F\u2550-\u256C"  # box-drawing, block elements
    r"\u250C\u2510\u2514\u2518\u252C\u2534\u251C\u2524\u253C"  # corners, tees
    r"]"
)
_BOX_LINE_RE = re.compile(
    r"^[\s\u2500-\u257F\u2550-\u256C─━═┈┉┄┅\-|│┃]*$"
)


def _clean_table_text(text: str) -> str:
    """
    별표 텍스트에서 표 형식을 정리.
    API 응답의 유니코드 box-drawing 테이블을 읽기 좋은 형태로 변환.
    """
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # 빈 줄 스킵
        if not stripped:
            continue
        # 순수 구분선 (box-drawing 문자 + 공백만으로 구성) 제거
        if _BOX_LINE_RE.fullmatch(stripped):
            continue
        # box-drawing 수직선(│┃|) → 제거 후 셀 분리
        if _BOX_DRAWING_RE.search(line) or "│" in line or "┃" in line:
            # 수직선/box문자를 |로 통일
            cell_text = _BOX_DRAWING_RE.sub("|", line)
            cell_text = cell_text.replace("│", "|").replace("┃", "|")
            cells = [c.strip() for c in cell_text.split("|") if c.strip()]
            if cells:
                line = " | ".join(cells)
            else:
                continue
        # 과도한 연속 공백 정리
        line = re.sub(r"[ 　]{3,}", "  ", line)
        if line.strip():
            cleaned.append(line.strip())
    return "\n".join(cleaned)


# 서식/도안/별지/신청서 — 행정 양식이므로 RAG 검색 노이즈를 유발
_FORM_NOISE_KEYWORDS = ["별지", "서식", "신청서", "도안"]


def _is_form_or_template(title: str, content: str) -> bool:
    """별표가 행정 양식(서식/도안/신청서)인지 판단."""
    check_text = (title + " " + content[:300]).lower()
    return any(kw in check_text for kw in _FORM_NOISE_KEYWORDS)


def _별표_to_chunks(
    별표_list: list[dict], law_name: str, 고시번호: str, tier: int
) -> list[dict]:
    """별표 텍스트를 청크로 변환. 서식/도안/신청서는 제외."""
    chunks = []
    for bt in 별표_list:
        content = _clean_table_text(bt.get("별표내용", "").strip())
        title = bt.get("별표제목", "").strip()
        if not content or len(content) < 20:
            continue

        # 서식/도안/신청서 필터링 — RAG 노이즈 방지
        if _is_form_or_template(title, content):
            logger.debug("별표 서식 제외: %s — %s", law_name, title[:50])
            continue

        # 별표번호: "0001" → "1", 가지번호: "00" → 무시, "02" → "의2"
        raw_num = (bt.get("별표번호") or "").lstrip("0") or "0"
        raw_gaji = (bt.get("별표가지번호") or "").lstrip("0")
        if raw_num and raw_num != "0":
            label = f"별표 {raw_num}"
            if raw_gaji and raw_gaji != "0":
                label += f"의{raw_gaji}"
        else:
            label = "별표"

        # 별표제목이 있으면 라벨에 포함 (참고 법령 표시에 유용)
        if title:
            label += f"({title})"

        # 별표 내용이 길면 단락별로 분할
        if len(content) <= MAX_CHUNK_TOKENS * 1.5:
            chunks.append(_make_chunk(content, label, law_name, 고시번호, tier))
        else:
            # 큰 단위(번호 패턴)로 분할 시도
            parts = re.split(r"\n\s*(?=\d+\.)", content)
            current = ""
            part_idx = 0
            for part in parts:
                if len(current) + len(part) > MAX_CHUNK_TOKENS * 1.5 and current:
                    part_idx += 1
                    chunks.append(
                        _make_chunk(current.strip(), f"{label} 중 {part_idx}", law_name, 고시번호, tier)
                    )
                    current = part
                else:
                    current += "\n" + part if current else part
            if current.strip():
                part_idx += 1
                chunks.append(
                    _make_chunk(current.strip(), f"{label} 중 {part_idx}", law_name, 고시번호, tier)
                )

    return chunks


def _admrul_to_chunks(
    body: dict, law_name: str, 고시번호: str, tier: int
) -> list[dict]:
    """
    행정규칙(admrul) API 응답의 조문내용(통째) → 기존 chunk_by_article() 재사용.
    """
    full_text = "\n\n".join(body["조문내용_list"])
    return chunk_by_article(full_text, law_name, 고시번호, tier)


def api_body_to_chunks(
    registry_entry: dict, body: dict
) -> list[dict]:
    """
    API 본문 응답 → 기존 파이프라인 호환 청크 리스트 반환.

    반환 포맷 (기존 _make_chunk와 동일):
      [{"text": "[법령명 제N조]\n...", "조문번호": "제N조", "law_name": "...", "고시번호": "...", "tier": N}, ...]
    """
    law_name = registry_entry["law_name"]
    tier = registry_entry["tier"]
    api_type = registry_entry["api_type"]

    # 고시번호 추출
    if api_type == "eflaw":
        meta = body.get("meta", {})
        공포번호 = meta.get("공포일자", "")
        고시번호 = f"법률 제{meta.get('공포번호', '')}호" if meta.get("공포번호") else ""
    else:
        meta = body.get("meta", {})
        고시번호 = f"제{meta.get('발령번호', '')}호" if meta.get("발령번호") else ""

    chunks = []

    # 조문 청킹
    if api_type == "eflaw":
        chunks.extend(_eflaw_articles_to_chunks(body, law_name, 고시번호, tier))
    else:
        chunks.extend(_admrul_to_chunks(body, law_name, 고시번호, tier))

    # 별표 청킹
    별표 = body.get("별표", [])
    if 별표:
        chunks.extend(_별표_to_chunks(별표, law_name, 고시번호, tier))

    return [c for c in chunks if len(c["text"]) > 20]


# ════════════════════════════════════════════════════════════
# Phase 3: 변경 감지
# ════════════════════════════════════════════════════════════

def get_api_공포일자(registry_entry: dict) -> str:
    """API에서 공포일자(법령) 또는 발령일자(고시) 가져오기."""
    meta = fetch_law_meta(registry_entry)
    if registry_entry["api_type"] == "eflaw":
        return meta.get("공포일자", "")
    else:
        return meta.get("발령일자", "")


def check_law_changed(registry_entry: dict, supabase_client) -> bool:
    """
    API의 공포일자/발령일자와 DB의 api_공포일자를 비교하여 변경 여부 반환.
    DB에 레코드가 없거나 api_공포일자가 없으면 변경으로 간주.
    """
    law_name = registry_entry["law_name"]

    # DB에서 기존 값 조회
    existing = (
        supabase_client.table("f4_law_documents")
        .select("api_공포일자")
        .eq("law_name", law_name)
        .execute()
    )

    if not existing.data:
        logger.info("[%s] DB에 레코드 없음 → 신규", law_name)
        return True

    db_date = existing.data[0].get("api_공포일자", "")
    if not db_date:
        logger.info("[%s] DB에 api_공포일자 없음 → 변경으로 간주", law_name)
        return True

    # API에서 최신 값 조회
    api_date = get_api_공포일자(registry_entry)
    changed = str(db_date) != str(api_date)
    if changed:
        logger.info("[%s] 변경 감지: DB=%s → API=%s", law_name, db_date, api_date)
    else:
        logger.info("[%s] 변경 없음 (공포일자=%s)", law_name, api_date)
    return changed


# ════════════════════════════════════════════════════════════
# Phase 4: F4 전용 API 파이프라인
# ════════════════════════════════════════════════════════════

def preprocess_single_law_from_api(
    registry_entry: dict,
    index,
    supabase_client,
    model,
    claude_client,
) -> dict:
    """
    단일 법령을 API에서 가져와 전처리 → Pinecone + Supabase 적재.
    기존 preprocess_single_law()의 API 버전.

    [처리 흐름]
      1. API에서 본문 가져오기
      2. 청크 변환 (조/항/호/목 또는 chunk_by_article)
      3. 기존 Pinecone 벡터 삭제
      4. 임베딩
      5. 금지 마커 힌트 추출
      6. Supabase 저장 (기존 필드 + api 추가 컬럼)
      7. Pinecone 적재

    반환: {"law_doc_id": str, "total_chunks": int}
    """
    from backend.db.feature4.preprocess_laws import (
        set_law_updating,
        save_law_document,
        embed_chunks,
        delete_law_vectors,
        upsert_to_pinecone,
        _extract_prohibition_hints,
    )
    from datetime import date as date_cls

    law_name = registry_entry["law_name"]
    tier = registry_entry["tier"]
    api_type = registry_entry["api_type"]

    set_law_updating(supabase_client, law_name, True)
    try:
        # 1. API에서 본문 가져오기
        logger.info("[%s] API에서 본문 가져오는 중...", law_name)
        body = fetch_law_body(registry_entry)

        # 2. 청크 변환
        chunks = api_body_to_chunks(registry_entry, body)
        logger.info("[%s] 청크 %d개 생성", law_name, len(chunks))

        # 3. 기존 Pinecone 벡터 삭제
        old_doc = (
            supabase_client.table("f4_law_documents")
            .select("total_chunks")
            .eq("law_name", law_name)
            .execute()
        )
        old_total = old_doc.data[0]["total_chunks"] if old_doc.data else 0
        if old_total > 0:
            deleted = delete_law_vectors(index, law_name, old_total)
            logger.info("[%s] 기존 벡터 %d개 삭제", law_name, deleted)

        # 4. 임베딩
        vectors = embed_chunks(model, chunks)

        # 5. 금지 마커 힌트 추출
        logger.info("[%s] 금지 마커 힌트 추출 중...", law_name)
        hint_patterns = _extract_prohibition_hints(chunks, law_name, claude_client)
        logger.info("[%s] 힌트 패턴 %d개", law_name, len(hint_patterns))

        # 6. Supabase 저장
        # 메타 정보 추출
        meta = body.get("meta", {})
        if api_type == "eflaw":
            고시번호 = f"법률 제{meta.get('공포번호', '')}호" if meta.get("공포번호") else ""
            시행일_str = meta.get("시행일자", "")
            공포일자 = meta.get("공포일자", "")
        else:
            고시번호 = f"제{meta.get('발령번호', '')}호" if meta.get("발령번호") else ""
            시행일_str = meta.get("시행일자", "")
            공포일자 = meta.get("발령일자", "")

        # 시행일 파싱
        시행일 = date_cls.today()
        if 시행일_str and len(시행일_str) == 8:
            try:
                시행일 = date_cls(int(시행일_str[:4]), int(시행일_str[4:6]), int(시행일_str[6:8]))
            except ValueError:
                pass

        law_info = {
            "law_name": law_name,
            "고시번호": 고시번호,
            "시행일":   시행일,
            "file":     f"api://{api_type}/{registry_entry['api_id']}",
            "tier":     tier,
        }
        law_doc_id = save_law_document(supabase_client, law_info, len(chunks), hint_patterns)

        # API 추가 컬럼 업데이트
        supabase_client.table("f4_law_documents").update({
            "api_id":          registry_entry["api_id"],
            "api_type":        api_type,
            "api_공포일자":     공포일자,
            "last_api_sync_at": "now()",
        }).eq("id", law_doc_id).execute()

        # 7. Pinecone 적재
        upsert_to_pinecone(index, chunks, vectors, law_doc_id)

        logger.info("[%s] 완료: %d 청크 적재", law_name, len(chunks))
        return {
            "law_doc_id":   law_doc_id,
            "total_chunks": len(chunks),
        }
    finally:
        set_law_updating(supabase_client, law_name, False)


def sync_all_f4_laws(
    index,
    supabase_client,
    model,
    claude_client,
    force: bool = False,
) -> list[dict]:
    """
    F4 법령 7개를 API에서 가져와 변경된 것만 전처리.

    Args:
        force: True이면 변경 여부와 무관하게 전체 재처리 (초기 마이그레이션용)
    반환: [{"law_name": str, "status": "updated"|"skipped"|"error", ...}, ...]
    """
    results = []
    for entry in F4_LAW_REGISTRY:
        law_name = entry["law_name"]
        try:
            if not force and not check_law_changed(entry, supabase_client):
                results.append({"law_name": law_name, "status": "skipped"})
                continue

            result = preprocess_single_law_from_api(
                entry, index, supabase_client, model, claude_client
            )
            result["law_name"] = law_name
            result["status"] = "updated"
            results.append(result)
        except Exception as e:
            logger.error("[%s] 처리 실패: %s", law_name, e, exc_info=True)
            results.append({"law_name": law_name, "status": "error", "error": str(e)})
    return results
