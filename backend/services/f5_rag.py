"""
Pinecone 법령 검색 (RAG)
Pinecone f5-law-chunks 인덱스 검색 → 관련 법령 청크 반환

제공 함수:
  - search_and_format(query, match_count) : F5 시안 생성용 프롬프트 문자열 반환
  - search_law_chunks(query, match_count) : 법령 원문 미리보기용 기본 검색 (단일 청크)
  - search_law_chunks_extended(query, match_count, context_window)
      : 매칭 청크 ± context_window 개까지 확장해서 이어붙인 결과 반환.
        PDF 청킹 때문에 원문이 잘리는 문제를 보완.
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


def search_and_format(query: str, match_count: int = 5) -> str:
    """
    쿼리와 관련된 법령 청크를 검색하고 프롬프트에 삽입할 문자열로 반환.
    Pinecone f5-law-chunks 인덱스 사용.
    """
    try:
        vector = embed_query(query)

        res = _get_pinecone_index().query(
            vector=vector,
            top_k=match_count,
            include_metadata=True,
        )
        matches = res.get("matches") or []
    except Exception:
        return ""

    if not matches:
        return ""

    lines = ["[관련 법령 근거]"]
    for m in matches:
        meta = m.get("metadata") or {}
        law     = meta.get("law_name", "")
        content = meta.get("content", "")
        lines.append(f"\n## {law}\n{content}")

    return "\n".join(lines)


def search_law_chunks(query: str, match_count: int = 3) -> list[dict]:
    """
    기본 시맨틱 검색 — 매칭된 청크 그대로 반환 (확장 없음).
    레거시 용도로 유지. 원문 미리보기는 search_law_chunks_extended 사용 권장.
    """
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


# ────────────────────────────────────────────────────────────
# 확장 검색 (주변 청크 이어붙이기)
# ────────────────────────────────────────────────────────────

def _normalize_chunk_index(value) -> int | None:
    """
    chunk_index 가 int / str / float 등으로 저장되어 있을 수 있어 int 로 정규화.
    변환 불가 시 None 반환.
    """
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _fetch_chunks_by_indices(law_name: str, indices: list[int]) -> dict[int, dict]:
    """
    특정 law_name 의 chunk_index 가 indices 안에 포함된 청크들을 Pinecone 에서 조회.
    Returns: { chunk_index: {content, law_name} }

    Pinecone metadata 필터를 사용 — chunk_index 가 metadata 에 저장되어 있어야 함.
    벡터 없이 metadata 만 조회하기 위해 더미 벡터(0 벡터)로 query.
    """
    if not indices:
        return {}

    try:
        # Voyage-3 는 1024 차원 - 더미 0 벡터
        dummy_vector = [0.0] * 1024

        res = _get_pinecone_index().query(
            vector=dummy_vector,
            top_k=len(indices) + 5,  # 여유분 (스코어 낮아도 filter 내에서 다 잡히도록)
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
) -> list[dict]:
    """
    법령 원문 미리보기용 확장 검색.

    Steps:
      1. 시맨틱 검색으로 top_k 매칭 청크 확보
      2. 각 매칭의 chunk_index ± context_window 로 확장 범위 계산
      3. 같은 law_name 내 겹치는 범위는 합집합으로 병합
      4. metadata 필터로 확장 청크 조회
      5. chunk_index 순 정렬 + content 이어붙이기

    Args:
        query: 검색 쿼리
        match_count: 시맨틱 검색 top_k (기본 3)
        context_window: 앞뒤로 몇 개 청크를 추가로 가져올지 (기본 1)

    Returns:
        [
          {
            "law_name": str,
            "chunk_index": int,        # 대표 청크 (시맨틱 매칭 기준)
            "content": str,            # 확장된 이어붙인 원문
            "score": float,            # 대표 청크의 유사도
            "extended": bool,          # 확장 성공 여부
            "chunk_range": [int, int], # 포함된 청크 범위 [min, max]
          },
          ...
        ]
    """
    # 1) 시맨틱 검색
    vector = embed_query(query)

    res = _get_pinecone_index().query(
        vector=vector,
        top_k=match_count,
        include_metadata=True,
    )
    top_matches = res.get("matches") or []

    if not top_matches:
        return []

    # 2) 대표 청크 정리 (law_name 별로 가장 점수 높은 매칭을 "대표"로)
    #    같은 law_name 이 여러 번 매칭될 수 있음 — 점수 높은 것 하나만 대표로 두고 나머지는
    #    같은 법령의 확장 범위에 흡수.
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

    # 각 법령별로 확장 범위 계산 (여러 매칭이 한 법령에 있으면 합집합)
    ranges_by_law: dict[str, set[int]] = defaultdict(set)
    for m in top_matches:
        meta = m.get("metadata") or {}
        law_name = meta.get("law_name", "")
        idx = _normalize_chunk_index(meta.get("chunk_index"))
        if not law_name or idx is None:
            continue

        # chunk_index - context_window ~ chunk_index + context_window 범위
        for i in range(
            max(0, idx - context_window),
            idx + context_window + 1,
        ):
            ranges_by_law[law_name].add(i)

    # 3) 각 법령별로 확장 청크 조회
    chunks_by_law: dict[str, dict[int, dict]] = {}
    for law_name, idx_set in ranges_by_law.items():
        chunks_by_law[law_name] = _fetch_chunks_by_indices(
            law_name=law_name,
            indices=sorted(idx_set),
        )

    # 4) 결과 빌드 — 각 "대표" 매칭에 대해 이어붙인 content 만들기
    results: list[dict] = []
    for m in top_matches:
        meta = m.get("metadata") or {}
        law_name = meta.get("law_name", "")
        idx = _normalize_chunk_index(meta.get("chunk_index"))
        score = float(m.get("score", 0))

        if not law_name or idx is None:
            # 이상한 데이터는 기본 방식으로 처리
            results.append({
                "law_name": law_name,
                "chunk_index": idx,
                "content": meta.get("content", ""),
                "score": score,
                "extended": False,
                "chunk_range": None,
            })
            continue

        # 이 대표 청크가 law_name 내에서 최고 점수가 아니면 건너뛰기
        # (같은 법령은 한 번만 대표로 보여줌)
        primary = primary_by_law.get(law_name)
        if primary is None or primary["chunk_index"] != idx:
            continue

        # 해당 법령의 확장 청크들 조회
        available = chunks_by_law.get(law_name, {})

        # idx 주변 ±context_window 범위에서 연속된 청크만 이어붙이기
        # (중간이 비어있으면 거기까지만)
        sorted_indices = sorted(available.keys())
        if not sorted_indices:
            # 확장 실패 — 대표 청크만 반환
            results.append({
                "law_name": law_name,
                "chunk_index": idx,
                "content": meta.get("content", ""),
                "score": score,
                "extended": False,
                "chunk_range": None,
            })
            continue

        # idx 를 포함하는 연속된 블록 찾기
        # 예: indices=[38,39,41,42], idx=39 → 연속된 블록 [38,39]
        #     indices=[38,39,40,41,42], idx=39 → 연속된 블록 [38,39,40,41,42]
        left = idx
        right = idx
        # 왼쪽으로 확장
        while (left - 1) in available:
            left -= 1
        # 오른쪽으로 확장
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