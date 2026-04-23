"""
F3 법령 업데이트 디스패처.

admin_law_update.py 가 호출하는 단일 진입점.
law_name 에 따라 적절한 F3 파서로 라우팅.

법령 → 파서 매핑:
  - "수입신고 구비서류 목록"                → excel_required_docs
  - "수입식품안전관리 특별법 시행규칙"       → rule_pdf
  - "OEM 수입식품 관리 안내서"              → guide_pdf (OEM)
  - "동등성인정 협정문"                     → guide_pdf (동등성)
  - "식품공전"                              → foodcode_hwpx (별표1 + 제5장)
  - "식품첨가물공전"                        → foodcode_hwpx (착향료)

현재 admin_law_update.upload 엔드포인트는 "업로드 즉시 DB 교체" 패턴이지만,
F3 는 미리보기 단계를 거쳐야 하므로 이 디스패처는 **파싱 결과만 반환**하고
실제 DB 교체는 feature3_admin 의 /apply 엔드포인트에서 수행한다.

따라서 이 함수는 실질적으로 "parse_only" 역할.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional


# 지원하는 법령명 목록 (admin_law_update.LAW_FEATURE_MAP 과 동기화 필요)
SUPPORTED_LAWS = {
    "수입신고 구비서류 목록",
    "수입식품안전관리 특별법 시행규칙",
    "OEM 수입식품 관리 안내서",
    "동등성인정 협정문",
    "식품공전",
    "식품첨가물공전",
}


async def run_f3_preprocess(
    tmp_path: Path,
    law_name: str,
    progress_callback: Optional[Callable] = None,
) -> dict:
    """
    F3 전처리 진입점 (admin_law_update 에서 호출).

    MVP 동작: 파싱만 수행, DB 교체는 안 함.
    대신 결과에 "requires_preview": True 플래그 + 파싱 결과를 담아
    프론트에서 /api/v1/admin/f3/preview 로 다시 요청하게 유도.

    Args:
        tmp_path: 업로드된 임시 파일 경로
        law_name: LAW_FEATURE_MAP 의 key
        progress_callback: async (feature, law_name, stage, percent) 진행도 콜백

    Returns:
        {
            "feature": "F3",
            "law_name": str,
            "status": "preview_ready",
            "requires_preview": True,
            "message": "미리보기로 이동하세요",
        }

    Note: 이 함수는 `admin_law_update.py` 의 `FEATURE_PROCESSORS["F3"]` 에 등록된다.
          실제 파싱은 `/api/v1/admin/f3/preview` 엔드포인트에서 수행되며,
          여기서는 파일 저장과 안내 메시지만 제공한다.

          이유: admin_law_update.upload 는 SSE 스트리밍 + 즉시 적용 플로우라
                검역관 확정 없이 진행됨. F3 는 이 플로우 대신 별도 엔드포인트로
                preview → edit → confirm → apply 단계를 거친다.
    """
    if law_name not in SUPPORTED_LAWS:
        raise ValueError(
            f"F3 지원 법령 목록 밖: {law_name}. "
            f"지원 법령: {', '.join(sorted(SUPPORTED_LAWS))}"
        )

    if progress_callback:
        await progress_callback("F3", law_name, "preview_redirect", 100)

    return {
        "feature": "F3",
        "law_name": law_name,
        "status": "preview_ready",
        "requires_preview": True,
        "message": (
            "F3 법령 업데이트는 안전을 위해 미리보기 단계를 거칩니다. "
            "'수입필요서류 안내' 탭의 법령 업데이트 페이지에서 미리보기 및 확정을 진행하세요."
        ),
    }


# ──────────────────────────────────────────────
# preview/apply 단계에서 사용하는 법령 → 파서 매핑
# (feature3_admin.py 에서 import)
# ──────────────────────────────────────────────

def get_parser_module(law_name: str) -> str:
    """law_name → 파서 모듈명. feature3_admin 이 동적 import 할 때 사용."""
    mapping = {
        "수입신고 구비서류 목록": "excel_required_docs",
        "수입식품안전관리 특별법 시행규칙": "rule_pdf",
        "OEM 수입식품 관리 안내서": "guide_pdf",
        "동등성인정 협정문": "guide_pdf",
        "식품공전": "foodcode_hwpx",
        "식품첨가물공전": "foodcode_hwpx",
    }
    if law_name not in mapping:
        raise ValueError(f"F3 파서 매핑 없음: {law_name}")
    return mapping[law_name]
