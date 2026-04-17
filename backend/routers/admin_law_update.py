"""
통합 법령 업데이트 API — 법령 종류별 파일 업로드 → 관련 기능 전처리 병렬 호출

POST /admin/law-update/upload
  - 여러 법령 파일을 한번에 받아 관련 기능 전처리를 병렬 실행
  - SSE(Server-Sent Events)로 진행도 스트리밍

GET  /admin/law-update/laws
  - 업데이트 가능한 법령 목록 + 매핑 정보 반환

설계 원칙:
  - LAW_FEATURE_MAP / FEATURE_PROCESSORS 만 수정하면 새 기능 연결 완료
  - 기능 병합 시 dict에 행 추가만 하면 됨
"""

import asyncio
import json
import os
import tempfile
import traceback
from datetime import date
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

load_dotenv()

router = APIRouter(prefix="/admin/law-update", tags=["admin-law-update"])

# ════════════════════════════════════════════════════════════
# 법령 ↔ 기능 매핑 테이블
# 기능 병합 시 features 리스트에 기능 코드만 추가하면 됨
# ════════════════════════════════════════════════════════════

LAW_FEATURE_MAP = {
    # ── F1 전용 ──
    "식품공전": {
        "features": ["F1", "F2"],
        "tier": "고시",
        "description": "식품의 기준 및 규격 (별표1~3 포함)",
    },
    "식품첨가물공전": {
        "features": ["F1", "F2"],
        "tier": "고시",
        "description": "식품첨가물의 기준 및 규격",
        # F3 병합 시 → ["F1", "F2", "F3"]
    },
    "건강기능식품공전": {
        "features": ["F1"],
        "tier": "고시",
        "description": "건강기능식품의 기준 및 규격",
        # F2에서 아직 미사용 — 아람 확인 후 F2 추가 가능
    },
    "식품유형 분류원칙": {
        "features": ["F2"],
        "tier": "고시",
        "description": "식품공전 식품유형 분류원칙 (대/중/소분류 기준)",
    },
    "주세법 시행령": {
        "features": ["F2"],
        "tier": "시행령",
        "description": "주류 분류 기준 (별표1, 별표3)",
    },
    "기구및용기포장공전": {
        "features": ["F2"],
        "tier": "고시",
        "description": "기구 및 용기·포장의 기준 및 규격",
    },

    # ── F3 전용 ──
    "수입식품안전관리 특별법 시행규칙": {
        "features": ["F3"],
        "tier": "시행규칙",
        "description": "제27조·별표9·별표10 (수입신고 구비서류)",
    },
    "수입신고 구비서류 목록": {
        "features": ["F3"],
        "tier": "행정데이터",
        "description": "식약처 공식 엑셀 (제출 19 + 보관 14 항목)",
    },
    "OEM 수입식품 관리 안내서": {
        "features": ["F3"],
        "tier": "가이드라인",
        "description": "주문자상표부착 수입식품 관리 안내",
    },
    "동등성인정 협정문": {
        "features": ["F3"],
        "tier": "조약",
        "description": "한·미, 한·EU, 한·캐나다 유기가공식품 동등성인정 협정문",
    },

    # ── F1 + F4 공통 ──
    "식품등의 한시적 기준 및 규격 인정 기준": {
        "features": ["F1", "F4", "F5"],
        "tier": "고시",
        "description": "한시적 기준 및 규격 인정 기준",
    },

    # ── F4 + F5 ──
    "식품 등의 표시·광고에 관한 법률": {
        "features": ["F4"],
        "tier": "법률",
        "description": "표시·광고에 관한 법률",
    },
    "식품 등의 표시·광고에 관한 법률 시행령": {
        "features": ["F4"],
        "tier": "시행령",
        "description": "표시·광고법 시행령",
    },
    "식품 등의 표시·광고에 관한 법률 시행규칙": {
        "features": ["F4"],
        "tier": "시행규칙",
        "description": "표시·광고법 시행규칙",
    },
    "식품등의 표시기준": {
        "features": ["F4", "F5"],
        "tier": "고시",
        "description": "식품등의 표시기준 고시",
    },
    "식품등의 부당한 표시 또는 광고의 내용 기준": {
        "features": ["F4", "F5"],
        "tier": "고시",
        "description": "부당한 표시·광고 내용 기준",
    },
    "부당한 표시 또는 광고로 보지 아니하는 식품등의 기능성 표시 또는 광고에 관한 규정": {
        "features": ["F4", "F5"],
        "tier": "고시",
        "description": "기능성 표시·광고 허용 규정",
    },
}

# ════════════════════════════════════════════════════════════
# 기능별 전처리 프로세서 레지스트리
# 기능 병합 시 여기에 항목 추가
# ════════════════════════════════════════════════════════════

_TIER_MAP = {"법률": 1, "시행령": 2, "시행규칙": 3, "고시": 4}

# 기능별 클라이언트 싱글톤 캐시
_feature_clients: dict[str, dict] = {}


def _get_f4_clients() -> dict:
    """F4 전처리용 클라이언트 (Pinecone + Supabase + SentenceTransformer + OpenAI)."""
    if "F4" in _feature_clients:
        return _feature_clients["F4"]

    from openai import OpenAI
    from pinecone import Pinecone
    from sentence_transformers import SentenceTransformer
    from supabase import create_client

    clients = {
        "index": Pinecone(api_key=os.getenv("F4_PINECONE_API_KEY")).Index(
            host=os.getenv("F4_PINECONE_HOST")
        ),
        "supabase": create_client(
            os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY")
        ),
        "model": SentenceTransformer("intfloat/multilingual-e5-large"),
        "claude": OpenAI(api_key=os.getenv("F4_OPENAI_API_KEY")),
    }
    _feature_clients["F4"] = clients
    return clients


def _get_f1_clients() -> dict:
    """F1 전처리용 클라이언트 — RAG 임베딩 (OpenAI + Pinecone + Supabase).

    Phase 4-B 전환: 기존 Claude 기준치 추출 → OpenAI/Pinecone RAG 임베딩.
    """
    if "F1" in _feature_clients:
        return _feature_clients["F1"]

    from openai import OpenAI
    from pinecone import Pinecone
    from supabase import create_client

    api_key = os.getenv("F1_OPENAI_API_KEY")
    pinecone_key = os.getenv("F1_PINECONE_API_KEY")
    sb_url = os.getenv("SUPABASE_URL")
    sb_key = os.getenv("SUPABASE_SERVICE_KEY")
    if not all([api_key, pinecone_key, sb_url, sb_key]):
        raise RuntimeError(
            "F1 환경변수 누락: F1_OPENAI_API_KEY / F1_PINECONE_API_KEY / "
            "SUPABASE_URL / SUPABASE_SERVICE_KEY 모두 필요"
        )

    clients = {
        "openai": OpenAI(api_key=api_key),
        "index": Pinecone(api_key=pinecone_key).Index(
            os.getenv("F1_PINECONE_INDEX", "samc-law-f1")
        ),
        "supabase": create_client(sb_url, sb_key),
    }
    _feature_clients["F1"] = clients
    return clients


def _get_f2_clients() -> dict:
    """F2 전처리용 클라이언트 (Pinecone + Supabase + OpenAI)."""
    if "F2" in _feature_clients:
        return _feature_clients["F2"]

    from openai import OpenAI
    from pinecone import Pinecone
    from supabase import create_client

    clients = {
        "index": Pinecone(api_key=os.getenv("F2_PINECONE_API_KEY")).Index(
            os.getenv("F2_PINECONE_INDEX", "samc-a")
        ),
        "supabase": create_client(
            os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY")
        ),
        "openai": OpenAI(api_key=os.getenv("F2_OPENAI_API_KEY")),
    }
    _feature_clients["F2"] = clients
    return clients


async def _run_f4_preprocess(
    tmp_path: Path,
    law_name: str,
    고시번호: str,
    시행일: date,
    tier: str,
    category: str,
    progress_callback=None,
) -> dict:
    """F4 전처리: PDF → 청킹 → 임베딩 → Pinecone + Supabase + 후처리."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "db" / "feature4"))

    clients = _get_f4_clients()
    tier_int = _TIER_MAP.get(tier, 4)

    if progress_callback:
        await progress_callback("F4", law_name, "chunking", 10)

    from preprocess_laws import preprocess_single_law

    result = preprocess_single_law(
        pdf_path=tmp_path,
        law_name=law_name,
        고시번호=고시번호,
        시행일=시행일,
        tier=tier_int,
        category=category,
        index=clients["index"],
        supabase_client=clients["supabase"],
        model=clients["model"],
        claude_client=clients["claude"],
    )

    if progress_callback:
        await progress_callback("F4", law_name, "post_processing", 70)

    # 후처리: 금지 표현 추출
    from extract_prohibited_keywords import extract_for_law
    keyword_count = 0
    try:
        keyword_count = extract_for_law(
            law_name=law_name,
            index=clients["index"],
            supabase=clients["supabase"],
            claude=clients["claude"],
        )
    except Exception as e:
        print(f"[경고] 금지 표현 추출 실패: {e}")

    if progress_callback:
        await progress_callback("F4", law_name, "image_types", 85)

    # 후처리: 이미지 위반 유형 추출
    from extract_image_violation_types import extract_image_types_for_law
    img_types_added = 0
    try:
        img_result = extract_image_types_for_law(
            law_name=law_name,
            index=clients["index"],
            supabase=clients["supabase"],
            claude=clients["claude"],
        )
        img_types_added = img_result.get("added_active", 0)
    except Exception as e:
        print(f"[경고] 이미지 위반 유형 추출 실패: {e}")

    # 프롬프트 캐시 무효화
    try:
        from routers.feature4 import _invalidate_prompt_cache
        _invalidate_prompt_cache()
    except Exception:
        pass

    if progress_callback:
        await progress_callback("F4", law_name, "done", 100)

    return {
        "feature": "F4",
        "law_name": law_name,
        "status": "success",
        "total_chunks": result.get("total_chunks", 0),
        "keywords_extracted": keyword_count,
        "image_types_pending": img_types_added,
    }


# F1 법령 → Pinecone namespace 매핑
# LAW_FEATURE_MAP의 F1 법령과 일치해야 함.
_F1_LAW_NAME_TO_NAMESPACE = {
    "식품공전": "food_code_text",
    "식품첨가물공전": "additive_code_text",
    "건강기능식품공전": "health_food_text",
    "식품등의 한시적 기준 및 규격 인정 기준": "temporary_standard",
}

# namespace별 ASCII-only vector_id prefix (Pinecone 제약)
_F1_NAMESPACE_TO_ID_PREFIX = {
    "food_code_text": "food_code",
    "additive_code_text": "additive_code",
    "health_food_text": "health_food",
    "temporary_standard": "temporary_std",
}

_F1_EMBED_BATCH = 100
_F1_UPSERT_BATCH = 100


def _law_name_to_namespace(law_name: str) -> str:
    """LAW_FEATURE_MAP F1 법령명 → Pinecone namespace."""
    if law_name not in _F1_LAW_NAME_TO_NAMESPACE:
        raise RuntimeError(f"F1 namespace 매핑 없음: {law_name}")
    return _F1_LAW_NAME_TO_NAMESPACE[law_name]


def _f1_pdf_to_text(pdf_path: Path) -> str:
    """PyMuPDF로 PDF → 단순 텍스트 추출.

    f1_chunking.chunk_markdown()은 `### 제N조` 헤딩 미존재 시 빈 줄 분할 폴백을
    지원하므로, 여기서는 페이지별 텍스트를 두 번 개행(\\n\\n)으로 이어 붙여 반환.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    try:
        pages = [p.get_text("text") for p in doc]
    finally:
        doc.close()
    return "\n\n".join(pages)


async def _run_f1_preprocess(
    tmp_path: Path,
    law_name: str,
    progress_callback=None,
) -> dict:
    """F1 전처리: PDF → 텍스트 → 청킹 → OpenAI 임베딩 → Pinecone + Supabase 미러.

    Phase 4-B 전환: 기존 Claude 기준치 추출 → RAG 임베딩.
    계획: f1_RAG도입계획_백엔드.md §4.3
    """
    import time
    from services import f1_chunking, f1_openai_client

    clients = _get_f1_clients()
    namespace = _law_name_to_namespace(law_name)
    id_prefix_base = _F1_NAMESPACE_TO_ID_PREFIX.get(namespace, "f1_law")

    if progress_callback:
        await progress_callback("F1", law_name, "chunking", 10)

    md_text = _f1_pdf_to_text(tmp_path)
    regulation_id = f"{law_name}_{int(time.time())}"
    # ASCII prefix + 타임스탬프 (중복 방지 + Pinecone ID 안전)
    id_prefix = f"{id_prefix_base}_{int(time.time())}"
    chunks = f1_chunking.chunk_markdown(
        md_text, regulation_id, namespace, id_prefix=id_prefix,
    )

    if not chunks:
        return {
            "feature": "F1",
            "law_name": law_name,
            "status": "success",
            "embedded_count": 0,
            "namespace": namespace,
            "message": "청크 생성 0 — PDF 추출 결과가 비어 있을 수 있음",
        }

    if progress_callback:
        await progress_callback("F1", law_name, "embedding", 30)

    # 배치 임베딩
    vectors: list[dict] = []
    for i in range(0, len(chunks), _F1_EMBED_BATCH):
        batch = chunks[i : i + _F1_EMBED_BATCH]
        embeds = f1_openai_client.embed([c["text"] for c in batch])
        for c, e in zip(batch, embeds):
            vectors.append({
                "id": c["vector_id"],
                "values": e,
                "metadata": {**c["metadata"], "text": c["text"][:4000]},
            })
        if progress_callback:
            pct = 30 + int(50 * (i + len(batch)) / len(chunks))
            await progress_callback("F1", law_name, "embedding", pct)

    # Pinecone upsert
    for i in range(0, len(vectors), _F1_UPSERT_BATCH):
        clients["index"].upsert(
            vectors=vectors[i : i + _F1_UPSERT_BATCH],
            namespace=namespace,
        )

    if progress_callback:
        await progress_callback("F1", law_name, "mirroring", 85)

    # Supabase 미러 upsert
    mirror_rows = [{
        "vector_id": v["id"],
        "regulation_id": v["metadata"]["regulation_id"],
        "pinecone_namespace": namespace,
        "section_path": v["metadata"].get("section_path"),
        "text": (v["metadata"].get("text", "") or "")[:16000],
        "token_count": v["metadata"].get("token_count"),
        "chunk_index": v["metadata"].get("chunk_index"),
        "total_chunks": v["metadata"].get("total_chunks"),
    } for v in vectors]
    for i in range(0, len(mirror_rows), _F1_UPSERT_BATCH):
        clients["supabase"].table("f1_law_chunks").upsert(
            mirror_rows[i : i + _F1_UPSERT_BATCH],
            on_conflict="vector_id",
        ).execute()

    if progress_callback:
        await progress_callback("F1", law_name, "done", 100)

    return {
        "feature": "F1",
        "law_name": law_name,
        "status": "success",
        "embedded_count": len(vectors),
        "namespace": namespace,
        "regulation_id": regulation_id,
    }


async def _run_f2_preprocess(
    tmp_path: Path,
    law_name: str,
    progress_callback=None,
) -> dict:
    """F2 전처리: 단일 법령 PDF/HWPX → 청킹 → Pinecone + Supabase 업로드.

    Phase 3 Sprint 1(2026-04-17) 스켈레톤 상태. 실제 구현은 Sprint 2.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "db" / "feature2"))

    clients = _get_f2_clients()

    from preprocess_f2 import run_f2_preprocess  # noqa: PLC0415

    return await run_f2_preprocess(
        file_path=tmp_path,
        law_name=law_name,
        index=clients["index"],
        supabase_client=clients["supabase"],
        openai_client=clients["openai"],
        progress_callback=progress_callback,
    )


# 기능별 전처리 함수 레지스트리
# 기능 병합 시 여기에 항목 추가
FEATURE_PROCESSORS = {
    "F1": _run_f1_preprocess,
    "F2": _run_f2_preprocess,
    "F4": _run_f4_preprocess,
    # F3 병합 시 → "F3": _run_f3_preprocess,
    # F5 병합 시 → "F5": _run_f5_preprocess,
}


# ════════════════════════════════════════════════════════════
# API 엔드포인트
# ════════════════════════════════════════════════════════════


@router.get("/laws")
async def list_updatable_laws():
    """업데이트 가능한 법령 목록 + 어떤 기능에 영향을 주는지 반환."""
    laws = []
    for law_name, info in LAW_FEATURE_MAP.items():
        laws.append({
            "law_name": law_name,
            "tier": info["tier"],
            "description": info["description"],
            "features": info["features"],
        })
    return {"laws": laws}


@router.post("/upload")
async def upload_and_update(
    files: list[UploadFile] = File(..., description="법령 PDF/HWPX 파일들"),
    law_names: str = Form(..., description='JSON 배열: ["식품공전", "표시기준", ...]'),
    고시번호들: str = Form("[]", description='JSON 배열: ["제2025-60호", ...]'),
    시행일들: str = Form("[]", description='JSON 배열: ["2025-08-29", ...]'),
):
    """
    법령 파일 다건 업로드 → 관련 기능 전처리 병렬 실행.
    SSE로 진행도 스트리밍.
    """
    # JSON 파싱
    try:
        names = json.loads(law_names)
    except json.JSONDecodeError:
        raise HTTPException(400, "law_names JSON 파싱 실패")

    try:
        notices = json.loads(고시번호들) if 고시번호들 != "[]" else [""] * len(names)
    except json.JSONDecodeError:
        notices = [""] * len(names)

    try:
        dates_raw = json.loads(시행일들) if 시행일들 != "[]" else [""] * len(names)
    except json.JSONDecodeError:
        dates_raw = [""] * len(names)

    if len(files) != len(names):
        raise HTTPException(400, f"파일 수({len(files)})와 법령명 수({len(names)})가 불일치")

    # 파일 확장자 검증
    allowed_ext = {".pdf", ".hwpx"}
    for f in files:
        if not f.filename or Path(f.filename).suffix.lower() not in allowed_ext:
            raise HTTPException(400, f"허용되지 않는 파일: {f.filename} (PDF/HWPX만 가능)")

    # 법령명 유효성 검증
    for name in names:
        if name not in LAW_FEATURE_MAP:
            raise HTTPException(400, f"알 수 없는 법령: {name}")

    # 임시 파일 저장
    tmp_paths: list[Path] = []
    for f in files:
        suffix = Path(f.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await f.read()
            tmp.write(content)
            tmp_paths.append(Path(tmp.name))

    # 진행도 이벤트 큐
    progress_queue: asyncio.Queue = asyncio.Queue()

    async def progress_callback(feature: str, law_name: str, stage: str, percent: int):
        await progress_queue.put({
            "type": "progress",
            "feature": feature,
            "law_name": law_name,
            "stage": stage,
            "percent": percent,
        })

    async def run_all_tasks():
        """모든 법령 × 기능 전처리를 병렬 실행."""
        tasks = []

        for i, law_name in enumerate(names):
            info = LAW_FEATURE_MAP[law_name]
            고시번호 = notices[i] if i < len(notices) else ""
            시행일_str = dates_raw[i] if i < len(dates_raw) else ""

            try:
                시행일 = date.fromisoformat(시행일_str) if 시행일_str else date.today()
            except ValueError:
                시행일 = date.today()

            for feature in info["features"]:
                processor = FEATURE_PROCESSORS.get(feature)
                if not processor:
                    await progress_queue.put({
                        "type": "error",
                        "feature": feature,
                        "law_name": law_name,
                        "message": f"{feature} 프로세서 미등록 (아직 병합되지 않은 기능)",
                    })
                    continue

                if feature == "F4":
                    tasks.append(
                        processor(
                            tmp_path=tmp_paths[i],
                            law_name=law_name,
                            고시번호=고시번호,
                            시행일=시행일,
                            tier=info["tier"],
                            category=info.get("description", ""),
                            progress_callback=progress_callback,
                        )
                    )
                elif feature in ("F1", "F2"):
                    tasks.append(
                        processor(
                            tmp_path=tmp_paths[i],
                            law_name=law_name,
                            progress_callback=progress_callback,
                        )
                    )

        # 병렬 실행
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 결과 전송
        for r in results:
            if isinstance(r, Exception):
                await progress_queue.put({
                    "type": "error",
                    "message": str(r),
                    "traceback": traceback.format_exception(r),
                })
            else:
                await progress_queue.put({"type": "result", **r})

        # 완료 신호
        await progress_queue.put({"type": "complete"})

        # 임시 파일 정리
        for p in tmp_paths:
            p.unlink(missing_ok=True)

    async def event_generator():
        """SSE 이벤트 스트림 생성 (text/event-stream)."""
        # 백그라운드에서 전처리 시작
        task = asyncio.create_task(run_all_tasks())

        while True:
            event = await progress_queue.get()
            data = json.dumps(event, ensure_ascii=False)
            yield f"event: {event['type']}\ndata: {data}\n\n"
            if event["type"] == "complete":
                break

        await task  # 예외 전파

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
