"""
Pinecone 법령 검색 (RAG)
Pinecone f5-law-chunks 인덱스 검색 → 관련 법령 청크 반환

제공 함수:
  - search_and_format(query, match_count)           : 레거시 호환 (문자열만 반환)
  - search_and_format_with_status(query, match_count): 문자열 + 성공 플래그 반환
  - search_law_chunks(query, match_count)           : 기본 검색 (metadata 필터 없음)
  - search_law_chunks_extended(query, ...)          : 주변 청크 확장 + metadata 필터
"""

import os
from collections import defaultdict

import voyageai
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

_voyage_client = None
_pinecone_index = None

INDEX_NAME = os.getenv("F5_PINECONE_INDEX", "f5-law-chunks")


# ════════════════════════════════════════════════════════════
# 인덱스에 존재하는 법령 목록 (Hybrid 검색용)
#
# 검색 품질 향상을 위해 law_name_hint 에 따라 이 목록에서
# 해당 법령만 골라 metadata 필터로 사용.
#
# 법령 추가/제거 시 이 상수와 LAW_NAME_KEYWORDS 를 업데이트.
# (f5_list_law_names.py 스크립트로 최신 목록 확인 가능)
# ════════════════════════════════════════════════════════════

KNOWN_LAW_NAMES: list[str] = [
    "식품등의 표시기준(식품의약품안전처고시)(제2025-60호)(20250829)",
    "식품등의 한시적 기준 및 규격 인정 기준(식품의약품안전처고시)(제2025-75호)(20251202)",
    "식품 등의 표시ㆍ광고에 관한 법률 시행규칙(총리령)(제02004호)(20260101)",
    "식품 등의 표시ㆍ광고에 관한 법률(법률)(제20826호)(20250919)",
    "식품 등의 표시ㆍ광고에 관한 법률 시행령(대통령령)(제35734호)(20250919)",
    "부당한 표시 또는 광고로 보지 아니하는 식품등의 기능성 표시  또는 광고에 관한 규정(식품의약품안전처고시)(제2024-62호)(20250101)",
    "식품등의 부당한 표시 또는 광고의 내용 기준(식품의약품안전처 고시)(제2025-79호)(20251204)",
    "유전자변형식품등의 표시기준(식품의약품안전처고시)(제2019-98 호)(20191028)",
    "OEM 기구용기 영업자 안내서★",
]

# law_name_hint → 매칭 대상 법령의 식별 키워드 매핑
#
# 힌트가 여러 법령에 매칭될 수 있음:
#   "표시기준" → "식품등의 표시기준" + "유전자변형식품등의 표시기준"
#   "시행규칙" → "... 표시ㆍ광고에 관한 법률 시행규칙"
#
# Hint 매칭은 소문자 + 공백 무시 단순 substring 으로 체크.
LAW_NAME_KEYWORDS: dict[str, list[str]] = {
    # 키: 힌트 (소문자, 공백 제거)
    # 값: 해당 힌트로 매칭해야 할 법령명의 부분 문자열 (KNOWN_LAW_NAMES 와 같은 형태)
    "표시기준":     ["표시기준"],
    "표시ㆍ광고":   ["표시ㆍ광고"],
    "표시광고":     ["표시ㆍ광고"],  # 가운뎃점 없이 써도 매칭
    "시행규칙":     ["시행규칙"],
    "시행령":       ["시행령"],
    "한시적":       ["한시적"],
    "기능성":       ["기능성"],
    "부당한":       ["부당한"],
    "유전자변형":   ["유전자변형"],
    "GMO":         ["유전자변형"],
    "gmo":         ["유전자변형"],
    "OEM":         ["OEM"],
    "oem":         ["OEM"],
    "기구용기":     ["기구용기"],
}


def _get_voyage():
    global _voyage_client
    if _voyage_client is None:
        api_key = os.getenv("F5_VOYAGE_API_KEY")
        if not api_key:
            raise RuntimeError("F5_VOYAGE_API_KEY 환경변수 미설정")
        _voyage_client = voyageai.Client(api_key=api_key)
    return _voyage_client


def _get_pinecone_index():
    global _pinecone_index
    if _pinecone_index is None:
        api_key = os.getenv("F5_PINECONE_API_KEY")
        if not api_key:
            raise RuntimeError("F5_PINECONE_API_KEY 환경변수 미설정")
        _pinecone_index = Pinecone(api_key=api_key).Index(INDEX_NAME)
    return _pinecone_index


def embed_query(text: str) -> list[float]:
    """텍스트 → Voyage-3 임베딩 벡터"""
    result = _get_voyage().embed([text], model="voyage-3")
    return result.embeddings[0]


def _filter_laws_by_hint(hint: str | None) -> list[str] | None:
    """
    law_name_hint 로 KNOWN_LAW_NAMES 에서 매칭되는 법령만 반환.

    Returns:
        - None : 힌트가 없거나 빈 문자열 (필터 미적용)
        - []   : 힌트는 있지만 매칭되는 법령이 없음 (검색 결과도 없을 것)
        - list : 매칭된 법령명 리스트
    """
    if not hint or not hint.strip():
        return None

    # 정규화: 공백 제거 + 소문자
    normalized_hint = hint.strip().replace(" ", "").lower()

    # LAW_NAME_KEYWORDS 에서 힌트 키 찾기
    # 먼저 정확 매칭 시도
    keywords = None
    for key, vals in LAW_NAME_KEYWORDS.items():
        if key.replace(" ", "").lower() == normalized_hint:
            keywords = vals
            break

    # 정확 매칭 실패 시 부분 매칭 (힌트가 키를 포함 or 키가 힌트를 포함)
    if keywords is None:
        for key, vals in LAW_NAME_KEYWORDS.items():
            key_normalized = key.replace(" ", "").lower()
            if key_normalized in normalized_hint or normalized_hint in key_normalized:
                keywords = vals
                break

    # 여전히 매칭 실패 시 힌트 자체를 키워드로 사용
    if keywords is None:
        keywords = [hint.strip()]

    # KNOWN_LAW_NAMES 에서 키워드 포함하는 법령 필터링
    matched = []
    for law_name in KNOWN_LAW_NAMES:
        law_lower = law_name.replace(" ", "").lower()
        for kw in keywords:
            kw_lower = kw.replace(" ", "").lower()
            if kw_lower in law_lower:
                matched.append(law_name)
                break  # 이 법령은 매칭됐으니 다음 법령으로

    return matched


def search_and_format_with_status(
    query: str,
    match_count: int = 5,
) -> tuple[str, bool]:
    """쿼리와 관련된 법령 청크를 검색하고 (프롬프트 문자열, 성공여부) 반환."""
    try:
        vector = embed_query(query)

        res = _get_pinecone_index().query(
            vector=vector,
            top_k=match_count,
            include_metadata=True,
        )
        matches = res.get("matches") or []
    except Exception as e:
        print(f"[F5 RAG] search_and_format_with_status 실패: {e}")
        return "", False

    if not matches:
        print(f"[F5 RAG] 검색 결과 없음: query={query[:60]}...")
        return "", False

    lines = ["[관련 법령 근거]"]
    for m in matches:
        meta = m.get("metadata") or {}
        law     = meta.get("law_name", "")
        content = meta.get("content", "")
        lines.append(f"\n## {law}\n{content}")

    return "\n".join(lines), True


def search_and_format(query: str, match_count: int = 5) -> str:
    """레거시 호환용."""
    context, _ = search_and_format_with_status(query, match_count)
    return context


def search_law_chunks(query: str, match_count: int = 3) -> list[dict]:
    """기본 시맨틱 검색 (metadata 필터 없음)."""
    vector = embed_query(query)

    res = _get_pinecone_index().query(
        vector=vector,
        top_k=match_count,
        include_metadata=True,
    )
    matches = res.get("matches") or []

    results = []
    for m in matches:
        meta = m.get("metadata") or {}
        results.append({
            "law_name":    meta.get("law_name", ""),
            "chunk_index": meta.get("chunk_index"),
            "content":     meta.get("content", ""),
            "score":       float(m.get("score", 0)),
            "extended":    False,
            "chunk_range": None,
        })

    return results


# ════════════════════════════════════════════════════════════
# 확장 검색 (주변 청크 이어붙이기 + Hybrid 필터)
# ════════════════════════════════════════════════════════════

def _normalize_chunk_index(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _fetch_chunks_by_indices(law_name: str, indices: list[int]) -> dict[int, dict]:
    """특정 law_name 의 chunk_index in indices 청크들을 조회."""
    if not indices:
        return {}

    try:
        dummy_vector = [0.0] * 1024

        res = _get_pinecone_index().query(
            vector=dummy_vector,
            top_k=len(indices) + 5,
            include_metadata=True,
            filter={
                "law_name": {"$eq": law_name},
                "chunk_index": {"$in": indices},
            },
        )
        matches = res.get("matches") or []
    except Exception:
        return {}

    result: dict[int, dict] = {}
    for m in matches:
        meta = m.get("metadata") or {}
        idx = _normalize_chunk_index(meta.get("chunk_index"))
        if idx is None:
            continue
        result[idx] = {
            "law_name": meta.get("law_name", law_name),
            "content":  meta.get("content", ""),
            "chunk_index": idx,
        }
    return result


def search_law_chunks_extended(
    query: str,
    match_count: int = 3,
    context_window: int = 1,
    law_name_hint: str | None = None,
) -> list[dict]:
    """
    법령 원문 미리보기용 확장 검색 (Hybrid: metadata 필터 + 시맨틱).

    1. law_name_hint 가 있으면 해당 키워드와 매칭되는 법령만 metadata 필터로 제한
    2. 제한된 법령 내에서 시맨틱 top_k 매칭
    3. 각 매칭의 chunk_index ± context_window 로 확장 범위 계산
    4. 같은 law_name 내 겹치는 범위는 합집합으로 병합
    5. metadata 필터로 확장 청크 조회
    6. chunk_index 순 정렬 + content 이어붙이기

    Args:
        query: 검색 쿼리
        match_count: 시맨틱 검색 top_k (기본 3)
        context_window: 앞뒤로 몇 개 청크를 추가로 가져올지 (기본 1)
        law_name_hint: 법령명 힌트 (예: "표시기준", "시행규칙"). None 이면 전체 검색.

    Returns:
        각 결과 dict 에 "extended", "chunk_range" 포함.
    """
    # 1) Hybrid 필터 - law_name_hint 로 검색 범위 제한
    filtered_law_names = _filter_laws_by_hint(law_name_hint)

    pinecone_filter = None
    if filtered_law_names is not None:
        if not filtered_law_names:
            # 힌트는 있는데 매칭되는 법령이 하나도 없는 경우
            print(f"[F5 RAG] law_name_hint '{law_name_hint}' 매칭 법령 없음")
            return []
        pinecone_filter = {"law_name": {"$in": filtered_law_names}}
        print(f"[F5 RAG] hint='{law_name_hint}' → {len(filtered_law_names)}개 법령으로 필터")

    # 2) 시맨틱 검색 (필터 적용)
    vector = embed_query(query)

    query_kwargs: dict = {
        "vector": vector,
        "top_k": match_count,
        "include_metadata": True,
    }
    if pinecone_filter:
        query_kwargs["filter"] = pinecone_filter

    res = _get_pinecone_index().query(**query_kwargs)
    top_matches = res.get("matches") or []

    if not top_matches:
        return []

    # 3) law_name 별 대표 매칭 (점수 가장 높은 것)
    primary_by_law: dict[str, dict] = {}
    for m in top_matches:
        meta = m.get("metadata") or {}
        law_name = meta.get("law_name", "")
        idx = _normalize_chunk_index(meta.get("chunk_index"))
        score = float(m.get("score", 0))
        if not law_name or idx is None:
            continue

        existing = primary_by_law.get(law_name)
        if existing is None or score > existing["score"]:
            primary_by_law[law_name] = {
                "law_name": law_name,
                "chunk_index": idx,
                "score": score,
            }

    # 확장 범위 합집합
    ranges_by_law: dict[str, set[int]] = defaultdict(set)
    for m in top_matches:
        meta = m.get("metadata") or {}
        law_name = meta.get("law_name", "")
        idx = _normalize_chunk_index(meta.get("chunk_index"))
        if not law_name or idx is None:
            continue

        for i in range(
            max(0, idx - context_window),
            idx + context_window + 1,
        ):
            ranges_by_law[law_name].add(i)

    # 4) 확장 청크 조회
    chunks_by_law: dict[str, dict[int, dict]] = {}
    for law_name, idx_set in ranges_by_law.items():
        chunks_by_law[law_name] = _fetch_chunks_by_indices(
            law_name=law_name,
            indices=sorted(idx_set),
        )

    # 5) 결과 빌드
    results: list[dict] = []
    for m in top_matches:
        meta = m.get("metadata") or {}
        law_name = meta.get("law_name", "")
        idx = _normalize_chunk_index(meta.get("chunk_index"))
        score = float(m.get("score", 0))

        if not law_name or idx is None:
            results.append({
                "law_name": law_name,
                "chunk_index": idx,
                "content": meta.get("content", ""),
                "score": score,
                "extended": False,
                "chunk_range": None,
            })
            continue

        primary = primary_by_law.get(law_name)
        if primary is None or primary["chunk_index"] != idx:
            continue

        available = chunks_by_law.get(law_name, {})

        sorted_indices = sorted(available.keys())
        if not sorted_indices:
            results.append({
                "law_name": law_name,
                "chunk_index": idx,
                "content": meta.get("content", ""),
                "score": score,
                "extended": False,
                "chunk_range": None,
            })
            continue

        left = idx
        right = idx
        while (left - 1) in available:
            left -= 1
        while (right + 1) in available:
            right += 1

        merged_parts = []
        for i in range(left, right + 1):
            chunk_data = available.get(i)
            if chunk_data:
                merged_parts.append(chunk_data.get("content", ""))

        merged_content = "\n\n".join(p for p in merged_parts if p)

        results.append({
            "law_name": law_name,
            "chunk_index": idx,
            "content": merged_content or meta.get("content", ""),
            "score": score,
            "extended": len(merged_parts) > 1,
            "chunk_range": [left, right] if merged_parts else None,
        })

    return results