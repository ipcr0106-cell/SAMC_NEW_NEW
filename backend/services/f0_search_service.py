"""
SAMC 수입식품 검역 AI — f0 성분 코드 검색 서비스

성분명(한글/영문) 또는 CAS 번호로 식약처 성분 코드를 검색합니다.

검색 전략 (2-Stage):
  1단계) Supabase 정확 매칭 (ilike)  — code, name_ko, name_en
  2단계) Pinecone 유사 검색 (semantic) — 1단계 결과 부족 시 fallback

환경변수 (backend/.env):
    SUPABASE_URL             Supabase URL (공용)
    SUPABASE_SERVICE_KEY     Supabase 서비스 키 (공용)
    F0_PINECONE_API_KEY      Pinecone API 키
    F0_PINECONE_INDEX_NAME   Pinecone 인덱스명 (기본값: samc-f0-codes)
    F0_OPENAI_API_KEY        임베딩용 OpenAI API 키
"""

from __future__ import annotations

import logging
import os
import re

from schemas.upload import IngredientSearchItem, IngredientSearchResponse

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

PINECONE_API_KEY = os.getenv("F0_PINECONE_API_KEY", "")
PINECONE_INDEX   = os.getenv("F0_PINECONE_INDEX_NAME", "samc-f0-codes")
OPENAI_API_KEY   = os.getenv("F0_OPENAI_API_KEY", "")
EMBED_MODEL      = "text-embedding-3-small"

# CAS 번호 패턴: 숫자-숫자-숫자 (예: 64-17-5, 9005-25-8)
_CAS_PATTERN = re.compile(r"^\d{2,7}-\d{2}-\d$")


def _is_cas_number(query: str) -> bool:
    """입력값이 CAS 번호 형식인지 판별."""
    return bool(_CAS_PATTERN.match(query.strip()))


def _get_supabase():
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _get_pinecone_index():
    from pinecone import Pinecone
    pc = Pinecone(api_key=PINECONE_API_KEY)
    return pc.Index(PINECONE_INDEX)


def _embed_query(text: str) -> list[float]:
    """검색어를 OpenAI 임베딩 벡터로 변환."""
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.embeddings.create(model=EMBED_MODEL, input=[text])
    return resp.data[0].embedding


# ─────────────────────────────────────────────
# Supabase 정확/유사 매칭
# ─────────────────────────────────────────────

def _search_supabase_exact(query: str, top_k: int) -> list[IngredientSearchItem]:
    """Supabase f0_ingredient_codes에서 정확 매칭 (ilike).

    name_ko, name_en, code 컬럼에서 검색.
    """
    sb = _get_supabase()
    pattern = f"%{query}%"

    try:
        result = (
            sb.table("f0_ingredient_codes")
            .select("code, name_ko, name_en, category, code_prefix")
            .or_(f"name_ko.ilike.{pattern},name_en.ilike.{pattern},code.ilike.{pattern}")
            .limit(top_k)
            .execute()
        )
        rows = result.data or []
    except Exception as e:
        logger.error(f"Supabase 성분 검색 실패: {e}")
        return []

    return [
        IngredientSearchItem(
            code=r["code"],
            name_ko=r.get("name_ko", ""),
            name_en=r.get("name_en", ""),
            category=r.get("category", ""),
            code_prefix=r.get("code_prefix", ""),
            score=1.0,
            match_type="exact",
        )
        for r in rows
    ]


# ─────────────────────────────────────────────
# Pinecone 유사 검색
# ─────────────────────────────────────────────

def _search_pinecone_semantic(query: str, top_k: int) -> list[IngredientSearchItem]:
    """Pinecone ingredients 네임스페이스에서 유사도 검색."""
    if not PINECONE_API_KEY or not OPENAI_API_KEY:
        logger.warning("Pinecone 또는 OpenAI 환경변수 미설정 — 유사 검색 스킵")
        return []

    try:
        vector = _embed_query(query)
        index = _get_pinecone_index()
        results = index.query(
            vector=vector,
            top_k=top_k,
            namespace="ingredients",
            include_metadata=True,
        )
    except Exception as e:
        logger.error(f"Pinecone 유사 검색 실패: {e}")
        return []

    items = []
    for match in results.get("matches", []):
        meta = match.get("metadata", {})
        items.append(IngredientSearchItem(
            code=meta.get("code", match.get("id", "")),
            name_ko=meta.get("name_ko", ""),
            name_en=meta.get("name_en", ""),
            category=meta.get("category", ""),
            code_prefix=meta.get("code_prefix", ""),
            score=round(float(match.get("score", 0.0)), 4),
            match_type="semantic",
        ))
    return items


# ─────────────────────────────────────────────
# 메인 검색 함수
# ─────────────────────────────────────────────

async def search_ingredient_codes(
    query: str,
    top_k: int = 5,
    search_mode: str = "auto",
) -> IngredientSearchResponse:
    """성분명 또는 CAS 번호로 식약처 성분 코드 검색.

    Args:
        query:       검색어 (성분명 한글/영문 또는 CAS 번호)
        top_k:       반환할 최대 결과 수
        search_mode: 'auto' | 'exact' | 'fuzzy'
            - auto:  CAS 번호이면 exact, 아니면 exact 후 부족하면 semantic fallback
            - exact: Supabase ilike만 사용
            - fuzzy: Pinecone semantic만 사용

    Returns:
        IngredientSearchResponse (results 유사도 내림차순 정렬)
    """
    query = query.strip()
    is_cas = _is_cas_number(query)

    results: list[IngredientSearchItem] = []
    mode_used = "exact"

    if search_mode == "exact" or (search_mode == "auto" and is_cas):
        # 정확 매칭만
        results = _search_supabase_exact(query, top_k)
        mode_used = "exact"

    elif search_mode == "fuzzy":
        # 유사 검색만
        results = _search_pinecone_semantic(query, top_k)
        mode_used = "semantic"

    else:
        # auto + 비-CAS: 정확 매칭 우선, 부족하면 semantic fallback
        exact = _search_supabase_exact(query, top_k)
        if len(exact) >= top_k:
            results = exact
            mode_used = "exact"
        else:
            # 정확 매칭 결과 코드 집합 (중복 제거용)
            exact_codes = {r.code for r in exact}
            semantic = _search_pinecone_semantic(query, top_k)
            # semantic 결과 중 exact에 없는 것만 추가
            merged = list(exact)
            for item in semantic:
                if item.code not in exact_codes:
                    merged.append(item)
            results = merged[:top_k]
            mode_used = "both" if exact else "semantic"

    # score 내림차순 정렬
    results.sort(key=lambda x: x.score, reverse=True)

    logger.info(f"성분 코드 검색: query='{query}', mode={mode_used}, results={len(results)}건")

    return IngredientSearchResponse(
        results=results,
        query=query,
        total=len(results),
        search_mode_used=mode_used,
    )
