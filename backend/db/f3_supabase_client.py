"""
Supabase 데이터 로더 — PostgREST HTTP 직접 호출.

`supabase` 파이썬 SDK 대신 HTTP 를 쓰는 이유:
  - SDK 가 간헐적으로 hang 되는 이슈 있음 (Windows + cygwin 환경)
  - timeout 명시 가능
  - 의존성 가벼움 (httpx 하나면 끝)

캐시:
  최초 1회 호출 시 메모리에 로드. 법령 개정 시 `reload_cache()` 호출.
"""
from __future__ import annotations

import os
from functools import lru_cache

import httpx


HTTP_TIMEOUT = 15.0


# ──────────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────────

def _env() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL 또는 SUPABASE_SERVICE_KEY 환경변수가 없습니다. .env 확인 필요."
        )
    return url, key


def _fetch(table: str, query: str = "select=*") -> list[dict]:
    """PostgREST 에서 테이블 데이터 조회.

    Args:
        table: 테이블명
        query: PostgREST 쿼리스트링 (예: "select=*&is_verified=eq.true")
    """
    url, key = _env()
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    r = httpx.get(
        f"{url}/rest/v1/{table}?{query}",
        headers=headers,
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def _upsert(table: str, payload: list[dict] | dict, on_conflict: str = "id") -> None:
    """PostgREST upsert (pipeline_steps 저장 등에 사용)."""
    url, key = _env()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": f"resolution=merge-duplicates,return=minimal",
    }
    r = httpx.post(
        f"{url}/rest/v1/{table}?on_conflict={on_conflict}",
        headers=headers,
        json=payload if isinstance(payload, list) else [payload],
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()


# ──────────────────────────────────────────────
# 공개 API (캐시)
# ──────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_required_documents() -> list[dict]:
    """f3_required_documents 52건 — is_verified=true 만."""
    return _fetch("f3_required_documents", "select=*&is_verified=eq.true")


@lru_cache(maxsize=1)
def load_country_groups() -> dict[str, set[str]]:
    """f3_country_groups 181건 → {group_name: set[country_name]}."""
    rows = _fetch("f3_country_groups", "select=group_name,country_name")
    groups: dict[str, set[str]] = {}
    for row in rows:
        groups.setdefault(row["group_name"], set()).add(row["country_name"])
    return groups


@lru_cache(maxsize=1)
def load_keyword_synonyms() -> list[dict]:
    """f3_keyword_synonyms 38건 (OCR/영문 → DB 키워드 매핑)."""
    return _fetch("f3_keyword_synonyms", "select=hint_keyword,db_keyword,country_cond")


@lru_cache(maxsize=1)
def load_food_type_categories() -> dict[str, dict]:
    """f3_food_type_categories → {food_type: {is_livestock, is_ruminant, is_pork, is_prefix}}."""
    rows = _fetch("f3_food_type_categories",
                  "select=food_type,is_livestock,is_ruminant,is_pork,is_prefix")
    out: dict[str, dict] = {}
    for row in rows:
        out[row["food_type"]] = {
            "is_livestock": bool(row.get("is_livestock")),
            "is_ruminant":  bool(row.get("is_ruminant")),
            "is_pork":      bool(row.get("is_pork")),
            "is_prefix":    bool(row.get("is_prefix")),
        }
    return out


@lru_cache(maxsize=1)
def load_mid_category_flags() -> dict[str, dict]:
    """f3_mid_category_flags → {mid_category: {is_livestock, is_ruminant}}."""
    rows = _fetch("f3_mid_category_flags",
                  "select=mid_category,is_livestock,is_ruminant")
    out: dict[str, dict] = {}
    for row in rows:
        out[row["mid_category"]] = {
            "is_livestock": bool(row.get("is_livestock")),
            "is_ruminant":  bool(row.get("is_ruminant")),
        }
    return out


@lru_cache(maxsize=1)
def load_warning_keywords() -> dict[str, list[str]]:
    """f3_warning_keywords → {rule_id: [keyword, ...]}."""
    rows = _fetch("f3_warning_keywords", "select=rule_id,keyword")
    out: dict[str, list[str]] = {}
    for row in rows:
        out.setdefault(row["rule_id"], []).append(row["keyword"])
    return out


@lru_cache(maxsize=1)
def load_plant_based_patterns() -> tuple[str, ...]:
    """f3_plant_based_patterns → 식물성 유래 원재료명 패턴 tuple.

    근거: 식품공전 별표1 (원료) + 식품공전 제5 7-1/8/9-5 (식품유형) + 업계통용명.
    """
    rows = _fetch("f3_plant_based_patterns", "select=pattern")
    return tuple(row["pattern"] for row in rows if row.get("pattern"))


@lru_cache(maxsize=1)
def load_suppress_rules() -> set[str]:
    """f3_suppress_rules → 식물성 감지 시 매핑 억제할 db_keyword set."""
    rows = _fetch("f3_suppress_rules",
                  "select=db_keyword&suppress_when=eq.plant_based_source")
    return {row["db_keyword"] for row in rows if row.get("db_keyword")}


@lru_cache(maxsize=1)
def load_strong_animal_keywords() -> tuple[str, ...]:
    """f3_strong_animal_keywords → plant 판정 override 용 명확한 동물성 키워드.

    예: '탈지우유', '생크림', '돼지고기' — 이 키워드가 원재료에 포함되면
        '딸기' stem 이 같이 있어도 plant 로 판정하지 않음 (False Negative 방지).
    """
    rows = _fetch("f3_strong_animal_keywords", "select=keyword")
    return tuple(row["keyword"] for row in rows if row.get("keyword"))


@lru_cache(maxsize=1)
def load_document_law_citations() -> dict[str, list[dict]]:
    """f3_document_law_citations → {doc_id: [citation_dict, ...]}.

    각 citation_dict:
      pinecone_chunk_id, chunk_type, priority ('primary'/'secondary'),
      law_name, law_source, article, clause, item, topic,
      agreement, country_code, effective_date, excerpt
    반환 dict 는 priority='primary' 가 앞에 오도록 정렬.
    """
    rows = _fetch(
        "f3_document_law_citations",
        "select=doc_id,pinecone_chunk_id,chunk_type,priority,law_name,law_source,"
        "article,clause,item,topic,agreement,country_code,effective_date,excerpt"
    )
    out: dict[str, list[dict]] = {}
    for row in rows:
        out.setdefault(row["doc_id"], []).append(row)
    # priority 정렬: primary 먼저
    for did in out:
        out[did].sort(key=lambda c: (0 if c.get("priority") == "primary" else 1))
    return out


def save_pipeline_step(case_id: str, step_key: str, ai_result: dict) -> None:
    """pipeline_steps 에 기능 3 결과 저장 (팀 통합용, 선택)."""
    payload = {
        "case_id": case_id,
        "step_key": step_key,
        "step_name": "required_docs",
        "status": "waiting_review",
        "ai_result": ai_result,
    }
    _upsert("pipeline_steps", payload, on_conflict="case_id,step_key")


def reload_cache() -> None:
    """법령 개정·데이터 갱신 시 캐시 강제 리로드."""
    load_required_documents.cache_clear()
    load_country_groups.cache_clear()
    load_keyword_synonyms.cache_clear()
    load_food_type_categories.cache_clear()
    load_mid_category_flags.cache_clear()
    load_warning_keywords.cache_clear()
    load_plant_based_patterns.cache_clear()
    load_suppress_rules.cache_clear()
    load_strong_animal_keywords.cache_clear()
    load_document_law_citations.cache_clear()
