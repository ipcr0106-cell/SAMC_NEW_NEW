"""F1 Step D 법령 캐시 적재용 클라이언트.

5종 namespace 의 본문 출처가 둘로 갈린다:
    - admrul (law.go.kr DRF) : 한시기준, 기능성표시
    - safetydata snapshot     : 식품공전, 식품첨가물공전, 건강기능식품공전
      (law.go.kr lawService 에서 본문 미제공 — placeholder 1건만 응답)

backend/services/law_api_client.py 의 fetch_admrul_body / fetch_admrul_meta 와
backend/services/safetydata_client.py 의 적재 결과 테이블 (f1_safetydata_*) 을
공용 article 포맷으로 통합한다.

레지스트리는 Pinecone 시대의 5 namespace 와 1:1 대응 (Step D 호환).

참조:
    backend/services/law_api_client.py
    backend/services/safetydata_client.py
    backend/db/migrations/019_f1_safetydata_snapshot.sql
    법령_API_전환_가이드.md
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

import asyncpg

from backend.services.law_api_client import fetch_admrul_body, fetch_admrul_meta

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class F1LawEntry:
    """F1 Step D 가 인용하는 법령 1건.

    source 가 'admrul' 이면 api_id (LID) 사용, 'safetydata' 이면
    safetydata_table 에서 row 를 article 로 변환.
    """

    namespace: str          # Pinecone 시대의 5 namespace 와 동일
    law_name: str
    source: str             # 'admrul' | 'safetydata'
    api_id: Optional[str] = None
    safetydata_table: Optional[str] = None


# 5종 본문 소스 — 2026-04-20 검증.
# law.go.kr lawService 가 식품공전류는 본문 미제공이므로 safetydata 로 대체.
F1_LAW_REGISTRY: list[F1LawEntry] = [
    F1LawEntry(
        namespace="food_code_text",
        law_name="식품의 기준 및 규격",
        source="safetydata",
        safetydata_table="f1_safetydata_food_code",
    ),
    F1LawEntry(
        namespace="additive_code_text",
        law_name="식품첨가물의 기준 및 규격",
        source="safetydata",
        safetydata_table="f1_safetydata_food_additive",
    ),
    F1LawEntry(
        namespace="health_food_text",
        law_name="건강기능식품의 기준 및 규격",
        source="safetydata",
        safetydata_table="f1_safetydata_health_functional_food",
    ),
    F1LawEntry(
        namespace="temporary_standard",
        law_name="식품등의 한시적 기준 및 규격 인정 기준",
        source="admrul",
        api_id="37975",
    ),
    F1LawEntry(
        namespace="functional_labeling",
        law_name="부당한 표시 또는 광고로 보지 아니하는 식품등의 기능성 표시 또는 광고에 관한 규정",
        source="admrul",
        api_id="75449",
    ),
]


_ARTICLE_HEAD_RE = re.compile(r"^제\s*[0-9]+\s*조(?:의\s*[0-9]+)?(?:\s*\([^)]*\))?")


def _split_article_label(text: str) -> str:
    """admrul 조문내용에서 '제N조(...)' 헤더만 추출.

    매치 실패 시 첫 60자 (개행 전까지) 를 라벨로 사용.
    """
    text = text.strip()
    m = _ARTICLE_HEAD_RE.match(text)
    if m:
        return m.group(0).strip()
    return text.split("\n", 1)[0][:60]


# 법령_API_전환_가이드.md §주의 1: 별표 중 서식·도안·신청서·별지 는 RAG 노이즈
# (의약품 오인 검색 → 신청서 양식 등) → 본문 적재에서 제외.
_FORM_NOISE_KEYWORDS = ("별지", "서식", "신청서", "도안")


def _is_form_or_template(title: str, content: str) -> bool:
    sample = (title + " " + content[:300])
    return any(kw in sample for kw in _FORM_NOISE_KEYWORDS)


def _format_byeolpyo_label(bt: dict) -> str:
    raw_num = (bt.get("별표번호") or "").lstrip("0") or "0"
    raw_gaji = (bt.get("별표가지번호") or "").lstrip("0")
    title = (bt.get("별표제목") or "").strip()
    if raw_num and raw_num != "0":
        label = f"별표 {raw_num}"
        if raw_gaji and raw_gaji != "0":
            label += f"의{raw_gaji}"
    else:
        label = "별표"
    if title:
        label += f"({title})"
    return label


def fetch_articles_admrul(entry: F1LawEntry) -> tuple[str, list[dict]]:
    """admrul 소스 — law.go.kr lawService 본문 → (api_공포일자, articles).

    articles: [{"article_label": str, "text": str, "article_type": "article"|"byeolpyo"}, ...]
    조문 + 별표 모두 포함, 서식/도안/별지/신청서 별표는 제외.
    """
    if not entry.api_id:
        raise ValueError(f"{entry.namespace}: admrul source requires api_id")

    body = fetch_admrul_body(entry.api_id)
    meta = body.get("meta") or {}
    api_date = meta.get("발령일자") or ""

    articles: list[dict] = []

    for raw in body.get("조문내용_list") or []:
        text = (raw or "").strip()
        if not text or len(text) < 10:
            continue
        articles.append({
            "article_label": _split_article_label(text),
            "text": text,
            "article_type": "article",
        })

    for bt in body.get("별표") or []:
        title = (bt.get("별표제목") or "").strip()
        content = (bt.get("별표내용") or "").strip()
        if not content or len(content) < 20:
            continue
        if _is_form_or_template(title, content):
            logger.debug("[%s] 별표 서식 제외: %s", entry.namespace, title[:40])
            continue
        articles.append({
            "article_label": _format_byeolpyo_label(bt),
            "text": content,
            "article_type": "byeolpyo",
        })

    return api_date, articles


def _build_safetydata_article(law_name: str, item: str, fields: dict) -> Optional[dict]:
    """safetydata row 1건 → article dict.

    article_label : "[품목명] 시험항목"
    text          : "[법령명 — 품목명] 시험항목: ... / 기준규격: ... / ..."
    """
    item = (item or "").strip()
    if not item:
        return None

    label_parts = [f"[{item}]"]
    test = (fields.get("test") or "").strip()
    if test:
        label_parts.append(test)
    article_label = " ".join(label_parts)[:200]

    text_parts = [f"[{law_name} — {item}]"]
    field_order = [
        ("품목코드", fields.get("item_cd")),
        ("시험항목", fields.get("test")),
        ("세부항목", fields.get("spcs")),
        ("기준규격", fields.get("crtr")),
        ("규격요약", fields.get("smry")),
        ("판정형식", fields.get("jgmt")),
        ("최대값",   fields.get("max")),
        ("최소값",   fields.get("min")),
        ("단위",     fields.get("unit")),
        ("출처",     fields.get("src")),
    ]
    seen_values: set[str] = set()
    for k, v in field_order:
        v = (v or "").strip()
        if not v or v in seen_values:
            continue
        seen_values.add(v)
        text_parts.append(f"{k}: {v}")
    text = " / ".join(text_parts)
    if len(text) < 20:
        return None
    return {
        "article_label": article_label,
        "text": text,
        "article_type": "safetydata",
    }


async def fetch_articles_safetydata(
    entry: F1LawEntry, conn: asyncpg.Connection
) -> tuple[str, list[dict]]:
    """safetydata snapshot row → (api_공포일자=MAX(synced_at), articles).

    f1_safetydata_food_code        : 식품공전 17 fields
    f1_safetydata_food_additive    : 첨가물공전 14 fields (item_korn_nm 등)
    f1_safetydata_health_functional_food : 건기식공전 14 fields (동일 스키마)
    """
    table = entry.safetydata_table
    if not table:
        raise ValueError(f"{entry.namespace}: safetydata source requires safetydata_table")

    if table == "f1_safetydata_food_code":
        rows = await conn.fetch(
            "SELECT item_nm, test_artcl, spcs_artcl, crtr_spcfct_vl, "
            "spcfct_vl_smry, unit_nm, jgmt_frm, max_vl, min_vl "
            f"FROM {table} ORDER BY id"
        )
        articles: list[dict] = []
        for r in rows:
            art = _build_safetydata_article(
                entry.law_name,
                r["item_nm"],
                {
                    "test": r["test_artcl"],
                    "spcs": r["spcs_artcl"],
                    "crtr": r["crtr_spcfct_vl"],
                    "smry": r["spcfct_vl_smry"],
                    "jgmt": r["jgmt_frm"],
                    "max":  r["max_vl"],
                    "min":  r["min_vl"],
                    "unit": r["unit_nm"],
                },
            )
            if art:
                articles.append(art)
    elif table in (
        "f1_safetydata_food_additive",
        "f1_safetydata_health_functional_food",
    ):
        # P6 (B안): item_cd 를 article 텍스트에 포함 → Step D 가 component_code
        # 키워드로 직접 매칭 가능 (첨가물 정확도 향상). 식품공전엔 컬럼 없음.
        rows = await conn.fetch(
            "SELECT item_cd, item_korn_nm, test_artcl_korn_nm, spcs_artcl_nm, "
            "crtr_spcfct_vl, crtr_spcfct_vl_smry, unit_nm, src, max_vl, min_vl "
            f"FROM {table} ORDER BY id"
        )
        articles = []
        for r in rows:
            art = _build_safetydata_article(
                entry.law_name,
                r["item_korn_nm"],
                {
                    "item_cd": r["item_cd"],
                    "test": r["test_artcl_korn_nm"],
                    "spcs": r["spcs_artcl_nm"],
                    "crtr": r["crtr_spcfct_vl"],
                    "smry": r["crtr_spcfct_vl_smry"],
                    "max":  r["max_vl"],
                    "min":  r["min_vl"],
                    "unit": r["unit_nm"],
                    "src":  r["src"],
                },
            )
            if art:
                articles.append(art)
    else:
        raise ValueError(f"unknown safetydata_table: {table}")

    api_date_raw = await conn.fetchval(
        f"SELECT MAX(synced_at) FROM {table}"
    )
    api_date = api_date_raw.strftime("%Y%m%d") if api_date_raw else ""
    return api_date, articles


def fetch_meta_for_entry(entry: F1LawEntry) -> dict:
    if entry.source != "admrul" or not entry.api_id:
        raise ValueError(f"{entry.namespace}: meta only for admrul source")
    return fetch_admrul_meta(entry.api_id)


__all__ = [
    "F1LawEntry",
    "F1_LAW_REGISTRY",
    "fetch_articles_admrul",
    "fetch_articles_safetydata",
    "fetch_meta_for_entry",
]
