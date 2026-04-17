"""
F2 전처리 — 단일 법령 파일(PDF/HWPX) 진입점.

`/admin/law-update` UI에서 F2 관련 법령 업로드 시 호출되는 단일 진입점.
F4 선례(`backend/db/feature4/preprocess_laws.py:preprocess_single_law`)의 구조를 차용.

Phase 3 Sprint 1 상태 (2026-04-17):
    스켈레톤만 존재. 실제 구현은 Sprint 2에서.

Sprint 2 구현 계획 (참조: .omc/research/f2_node_to_py_map.md):
    1. 텍스트 추출 — PDF(pdfplumber) / HWPX(parser-service)
       근거: `scripts/step1_extract.py` 로직 재사용
    2. 청킹 — 조문 단위 → fallback 800자 sliding window
       근거: `scripts/step3_chunk.py` 로직 재사용
    3. Pinecone 업로드 — text-embedding-3-small → upsert
       근거: `scripts/step5_upload_pinecone.py` 로직 재사용
    4. Supabase 업로드 — 식품공전 제5장인 경우 `f2_food_type_classification` 배치 insert
       근거: Node `upload_foodcode5_full.js`의 Supabase 부분 이관
    5. Pinecone 업로드 — 식품공전인 경우 `f2_food_types` → 소분류 청크 upsert
       근거: Node `upload_foodtype_chunks.js` 이관
"""

from pathlib import Path
from typing import Any, Callable, Optional


async def run_f2_preprocess(
    file_path: Path,
    law_name: str,
    index: Any,
    supabase_client: Any,
    openai_client: Any,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """
    F2 전처리 단일 진입점.

    Args:
        file_path: 업로드된 법령 파일 (PDF 또는 HWPX)
        law_name: 법령 공식 명칭 (LAW_FEATURE_MAP의 key)
        index: Pinecone Index 객체 (samc-a)
        supabase_client: Supabase client
        openai_client: OpenAI client (임베딩용)
        progress_callback: async (feature, law_name, stage, percent) → None

    Returns:
        dict: {
            "feature": "F2",
            "law_name": str,
            "status": "success",
            "total_chunks": int,
            "supabase_rows_inserted": int,  # 식품공전일 때만 > 0
        }

    Raises:
        NotImplementedError: Sprint 2 구현 전까지
        ValueError: 지원하지 않는 파일 확장자
    """
    if progress_callback:
        await progress_callback("F2", law_name, "extracting", 10)

    # TODO(Sprint 2): 텍스트 추출
    # - PDF: pdfplumber로 페이지별 추출
    # - HWPX: parser-service POST /parse
    # 참조: backend/db/feature2/scripts/step1_extract.py

    if progress_callback:
        await progress_callback("F2", law_name, "chunking", 40)

    # TODO(Sprint 2): 청킹
    # - 조문 단위(제X조, ○, ①~⑩) 우선
    # - 5개 미만이면 800자 sliding window(100자 overlap)로 fallback
    # 참조: backend/db/feature2/scripts/step3_chunk.py

    if progress_callback:
        await progress_callback("F2", law_name, "pinecone_upload", 70)

    # TODO(Sprint 2): Pinecone upsert
    # - openai_client.embeddings.create(model="text-embedding-3-small")
    # - id: md5(f"{law_name}_{law_name}_{idx:04d}") — ASCII 안전
    # - metadata: {law, category, chunk_index, char_count, text[:1000]}
    # 참조: backend/db/feature2/scripts/step5_upload_pinecone.py

    if progress_callback:
        await progress_callback("F2", law_name, "supabase_upload", 90)

    # TODO(Sprint 2): Supabase f2_food_type_classification 배치 insert
    # - law_name == "식품공전"인 경우만 (제5장 파싱 결과)
    # - 파싱 로직은 Node `upload_foodcode5_full.js`에서 이관
    #   parseCategoryFromFilename, extractCategoryDefinition,
    #   extractFoodTypeSections, parseTypesFromSection 4개 함수 이식 필요

    # TODO(Sprint 2): f2_food_types → Pinecone 청크 upsert (별도 함수)
    # - Node `upload_foodtype_chunks.js` 이관
    # - law_name에 상관없이 기존 f2_food_types 테이블 전체 재임베딩 기능
    # - 별도 관리 엔드포인트에서 호출 권장 (업로드 플로우와 분리)

    if progress_callback:
        await progress_callback("F2", law_name, "done", 100)

    raise NotImplementedError(
        "F2 전처리는 Phase 3 Sprint 2에서 구현 예정입니다. "
        f"현재는 스켈레톤 단계 (file={file_path.name}, law_name={law_name})."
    )
