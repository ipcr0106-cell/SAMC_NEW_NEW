"""
F3 Step 1 — 수입신고 구비서류 목록 Excel 파서.

입력: 식약처 공식 엑셀 2종 (제출용 / 보관용) 중 하나
출력: f3_required_documents 행 JSON

엑셀 스키마 (2026.2.5.현재 기준 — 헤더 3행에 위치):
  제출용: 연번 / 대상국가 / 대상제품 / 증명내용 / 제출서류 구분 / 기타   (27행)
  보관용: 연번 / 대상국가 / 대상제품 / 증명내용 / 기타                      (14행)

매핑 전략:
  doc_name          — 대상제품 앞부분 + 증명내용 요약
  doc_description   — 증명내용 전체
  target_country    — 대상국가 (태그 정규화 — 모든국가/EU 등)
  submission_type   — "submit" (제출용) / "keep" (보관용) — 파일명으로 판별
  submission_timing — "first" (최초 수입 시) / "every"
  is_mandatory      — True
  law_source        — 별표9 (제출) / 별표10 (보관)
  id                — 파일 종류 + 연번 기반 결정적 ID (e.g. "submit_1", "keep_3")

사용자 수동 커스텀 규칙(GMO, 대마씨 등)은 이 파서가 출력하지 않는다.
UI 프리뷰에서 "deleted" 로 표시되지만 검역관이 체크 해제하면 유지됨 (smart merge).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import polars as pl
except ImportError:
    pl = None  # type: ignore


# ──────────────────────────────────────────────
# 대상국가 태그 정규화 — f3_required_docs._match_country 와 호환
# ──────────────────────────────────────────────

_COUNTRY_NORMALIZE = {
    "모든국가": None,                                   # NULL = 전체
    "모든 국가": None,
    "모든국가(BSE관련 36개국 제외)": "모든국가(BSE36개국제외)",
    "모든 국가(BSE관련 36개국 제외)": "모든국가(BSE36개국제외)",
    "BSE관련 36개국": "BSE관련36개국",
    "ASF 발생 73개국": "ASF발생73개국",
    "ASF발생 73개국": "ASF발생73개국",
    "EU": "EU",
}


def _normalize_country(raw: str | None) -> str | None:
    """엑셀의 '대상국가' → DB target_country 태그."""
    if raw is None:
        return None
    s = str(raw).strip().replace("\n", " ")
    s = re.sub(r"\s+", " ", s)
    if s in _COUNTRY_NORMALIZE:
        return _COUNTRY_NORMALIZE[s]
    # "모든국가" 포함 변형
    if "모든국가" in s or "모든 국가" in s:
        if "BSE" in s and "제외" in s:
            return "모든국가(BSE36개국제외)"
        return None
    if "BSE" in s and "36개국" in s:
        return "BSE관련36개국"
    if "ASF" in s and "73개국" in s:
        return "ASF발생73개국"
    return s  # 그대로 사용 (단일 국가명 등)


# ──────────────────────────────────────────────
# 제출 타이밍 추정
# ──────────────────────────────────────────────

_FIRST_IMPORT_HINTS = (
    "최초 수입",
    "최초수입",
    "최초 1회",
    "한 번만",
)


def _infer_timing(description: str) -> str:
    low = description.replace(" ", "").replace("\n", "")
    for hint in _FIRST_IMPORT_HINTS:
        if hint.replace(" ", "") in low:
            return "first"
    return "every"


# ──────────────────────────────────────────────
# 파일 종류 판별 — 파일명 우선, 시트 이름 보조
# ──────────────────────────────────────────────

def _detect_file_kind(file_path: Path) -> str:
    """return 'submit' or 'keep'."""
    name = file_path.name
    if "제출" in name:
        return "submit"
    if "보관" in name:
        return "keep"
    # 파일명 불명확 → 내용으로 판별
    return "submit"


# ──────────────────────────────────────────────
# doc_name 축약
# ──────────────────────────────────────────────

_DOC_NAME_MAX = 60


def _make_doc_name(product: str, description: str) -> str:
    """대상제품 + 증명내용 합쳐서 doc_name 생성 (최대 60자)."""
    product = (product or "").strip().replace("\n", " ")
    description = (description or "").strip().replace("\n", " ")

    # 1안: 증명내용 첫 줄
    if description:
        first = description.split(".")[0].strip()
        if len(first) <= _DOC_NAME_MAX:
            return first
        return description[:_DOC_NAME_MAX].rstrip() + "..."

    # 2안: 대상제품
    if product:
        return (product[:_DOC_NAME_MAX] + "...") if len(product) > _DOC_NAME_MAX else product

    return "서류"


# ──────────────────────────────────────────────
# 메인 파서
# ──────────────────────────────────────────────

def parse(file_path: Path, law_name: str) -> dict:
    """
    엑셀 파싱 결과를 feature3_admin.preview 가 기대하는 형식으로 반환.

    반환:
      {
        "tables": {
          "f3_required_documents": {
            "new_rows": [...],
            "pk_column": "id",
            "warnings": [...],
          }
        },
        "warnings": [...],
        "pinecone_touched": False,
      }
    """
    if pl is None:
        raise RuntimeError("polars 미설치. `pip install polars` 필요")

    kind = _detect_file_kind(file_path)
    submission_type = "submit" if kind == "submit" else "keep"
    law_source = (
        "수입식품안전관리 특별법 시행규칙 제27조제1항제1호(별표9)"
        if kind == "submit"
        else "수입식품안전관리 특별법 시행규칙 제27조제2항(별표10)"
    )

    # 헤더 행 자동 탐지 (0~4 시도)
    df = None
    for h in range(6):
        try:
            candidate = pl.read_excel(file_path, read_options={"header_row": h})
            cols = candidate.columns
            # "연번" 컬럼 찾으면 성공
            if any("연번" in c for c in cols[:3]):
                df = candidate
                break
        except Exception:
            continue

    if df is None:
        raise ValueError(
            f"엑셀에서 '연번' 컬럼을 찾을 수 없습니다: {file_path.name}. "
            f"헤더 행이 다르거나 포맷이 바뀌었을 수 있습니다."
        )

    # 컬럼명 정규화
    col_map = {}
    for c in df.columns:
        if "연번" in c: col_map["연번"] = c
        elif "대상국가" in c: col_map["대상국가"] = c
        elif "대상제품" in c: col_map["대상제품"] = c
        elif "증명내용" in c: col_map["증명내용"] = c

    required = {"연번", "대상국가", "대상제품", "증명내용"}
    missing = required - col_map.keys()
    if missing:
        raise ValueError(
            f"필수 컬럼 누락: {missing}. "
            f"발견된 컬럼: {list(df.columns)}"
        )

    new_rows: list[dict[str, Any]] = []
    warnings: list[str] = []

    for i, row in enumerate(df.iter_rows(named=True)):
        seq = row.get(col_map["연번"])
        if seq is None:
            continue
        try:
            seq_int = int(seq)
        except (ValueError, TypeError):
            warnings.append(f"행 {i+1}: 연번이 숫자가 아님 ({seq!r}) — 건너뜀")
            continue

        country_raw = row.get(col_map["대상국가"])
        product_raw = row.get(col_map["대상제품"])
        desc_raw = row.get(col_map["증명내용"])

        description = str(desc_raw or "").strip()
        product = str(product_raw or "").strip()

        if not description:
            warnings.append(f"행 {seq_int}: 증명내용 비어있음 — 건너뜀")
            continue

        doc_id = f"{submission_type}_{seq_int}"
        timing = _infer_timing(description)
        target_country = _normalize_country(country_raw)

        new_rows.append({
            "id": doc_id,
            "doc_name": _make_doc_name(product, description),
            "doc_description": description,
            "is_mandatory": True,
            "submission_type": submission_type,
            "submission_timing": timing,
            "law_source": law_source,
            "condition": None,       # 검역관이 프리뷰에서 수동 보강
            "target_country": target_country,
            "food_type": None,       # 수동 보강
            "product_keywords": None,  # 수동 보강
            "effective_from": None,
            "effective_until": None,
            "is_verified": True,
            # 원본 엑셀 참조용 (검역관이 나중에 대조 가능하게)
            "source_product": product[:500] if product else None,
            "source_seq": seq_int,
        })

    if not new_rows:
        raise ValueError("엑셀에서 유효한 행을 하나도 추출하지 못했습니다.")

    # 중요: scope_filter 로 submission_type 범위만 교체.
    # 이렇게 하면 제출용 엑셀을 올려도 보관용 14건 + 수동 커스텀 규칙(c1, c2 등)은
    # 영향을 받지 않음. snapshot.snapshot_and_replace 가 scope_filter 를 존중해서
    # DELETE 와 INSERT 범위를 제한한다.
    #
    # 다만 주의: id PK 기반 커스텀 규칙 (예: 하드코딩된 c1, c2) 이 같은 submission_type 이면
    # 여전히 삭제됨. 프리뷰 UI 에서 삭제 체크 해제로 보존 가능.
    scope_filter = {"submission_type": submission_type}

    return {
        "tables": {
            "f3_required_documents": {
                "new_rows": new_rows,
                "pk_column": "id",
                "scope_filter": scope_filter,
                "warnings": warnings,
            }
        },
        "warnings": [
            f"엑셀에서 {len(new_rows)}건 파싱 완료 ({submission_type} 유형).",
            f"⚠️ 이 업데이트는 f3_required_documents 중 submission_type='{submission_type}' "
            f"범위만 교체합니다. 다른 종류(반대 엑셀 및 식품공전 기반 서류)는 유지됩니다.",
            "⚠️ 같은 범위 내 기존 수동 규칙(예: GMO, 대마씨)이 '삭제'로 표시될 수 있습니다. "
            "유지하려면 프리뷰에서 해당 '삭제' 항목 체크박스를 해제하세요.",
            "⚠️ condition / food_type / product_keywords 는 엑셀에 직접 표현되지 않아 null 로 출력됩니다. "
            "필요시 프리뷰의 인라인 편집으로 보강하세요.",
        ] + warnings,
        "pinecone_touched": False,
    }
