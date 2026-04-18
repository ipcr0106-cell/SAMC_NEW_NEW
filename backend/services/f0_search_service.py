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

# ── 클라이언트 싱글톤 (요청마다 재생성 방지) ──────────────────────────────
_supabase_client: Optional[Any] = None
_pinecone_index_client: Optional[Any] = None
_openai_embed_client: Optional[Any] = None

try:
    from typing import Any
except ImportError:
    pass


def _is_cas_number(query: str) -> bool:
    """입력값이 CAS 번호 형식인지 판별."""
    return bool(_CAS_PATTERN.match(query.strip()))


def _get_supabase():
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


def _get_pinecone_index():
    global _pinecone_index_client
    if _pinecone_index_client is None:
        from pinecone import Pinecone
        pc = Pinecone(api_key=PINECONE_API_KEY)
        _pinecone_index_client = pc.Index(PINECONE_INDEX)
    return _pinecone_index_client


def _embed_query(text: str) -> list[float]:
    """검색어를 OpenAI 임베딩 벡터로 변환 (클라이언트 재사용)."""
    global _openai_embed_client
    if _openai_embed_client is None:
        from openai import OpenAI
        _openai_embed_client = OpenAI(api_key=OPENAI_API_KEY)
    resp = _openai_embed_client.embeddings.create(model=EMBED_MODEL, input=[text])
    return resp.data[0].embedding


# ─────────────────────────────────────────────
# Supabase 정확/유사 매칭
# ─────────────────────────────────────────────

def _search_supabase_exact(query: str, top_k: int) -> list[IngredientSearchItem]:
    """Supabase f0_ingredient_codes에서 검색.

    전략: 완전일치(eq) 우선 → 없으면 ilike 포함 검색.
    "물" 검색 시 "열매추출물" 등 포함 일치가 먼저 걸리는 문제 방지.
    """
    sb = _get_supabase()

    def _to_items(rows: list, score: float, match_type: str) -> list[IngredientSearchItem]:
        return [
            IngredientSearchItem(
                code=r["code"],
                name_ko=r.get("name_ko", ""),
                name_en=r.get("name_en", ""),
                category=r.get("category", ""),
                code_prefix=r.get("code_prefix", ""),
                score=score,
                match_type=match_type,
            )
            for r in rows
        ]

    try:
        # 1단계: 완전일치 (name_ko 또는 code 가 query와 동일)
        eq_result = (
            sb.table("f0_ingredient_codes")
            .select("code, name_ko, name_en, category, code_prefix")
            .or_(f"name_ko.eq.{query},code.eq.{query}")
            .limit(top_k)
            .execute()
        )
        eq_rows = eq_result.data or []
        if eq_rows:
            return _to_items(eq_rows, 1.0, "exact")

        # 2단계: ilike 포함 검색 (완전일치 결과 없을 때만)
        pattern = f"%{query}%"
        like_result = (
            sb.table("f0_ingredient_codes")
            .select("code, name_ko, name_en, category, code_prefix")
            .or_(f"name_ko.ilike.{pattern},name_en.ilike.{pattern},code.ilike.{pattern}")
            .limit(top_k)
            .execute()
        )
        like_rows = like_result.data or []
        return _to_items(like_rows, 0.8, "exact")

    except Exception as e:
        logger.error(f"Supabase 성분 검색 실패: {e}")
        return []


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
