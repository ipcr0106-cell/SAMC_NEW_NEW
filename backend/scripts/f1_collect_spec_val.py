"""SPEC_VAL 수집 스크립트 skeleton — data.go.kr 15116583 호출 + SPEC_VAL 필드 덤프.

사용법:
    cd backend
    F1_DATA_GO_KR_API_KEY=<키> python scripts/f1_collect_spec_val.py \\
        --output tests/fixtures/spec_val_collected.json \\
        [--limit 100]

주의:
    - 실 API 호출은 담당자/개발자가 별도 실행 (크리덴셜 필요).
    - 본 Agent 는 skeleton 만 제공하며 실행하지 않는다.
    - 결과 JSON 포맷은 tests/fixtures/spec_val_samples.json 과 동일.

출력 예시:
    [
      {
        "spec_val": "0.1이하",
        "unit_nm": "mg/kg",
        "spec_val_sumup": "음료류의 함량은 0.1mg/kg 이하",
        "fnprt_itm_nm": "음료류",
        "pc_kor_nm": "안식향산",
        "t_kor_nm": "함량"
      },
      ...
    ]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


async def collect_spec_vals(
    api_key: str,
    *,
    limit: int = 100,
    page_size: int = 50,
) -> list[dict]:
    """data.go.kr 15116583 에서 SPEC_VAL 필드 수집.

    Args:
        api_key: data.go.kr 서비스 키
        limit: 수집 최대 건수
        page_size: 페이지당 건수 (최대 100)

    Returns:
        SPEC_VAL 관련 필드만 추출한 딕셔너리 목록

    Note:
        실제 DataGoKrClient 를 사용하여 ADDITIVE_STANDARD 엔드포인트를 호출.
        pageNo 순회로 limit 건수까지 수집.
    """
    # 실 호출 시 활성화할 코드 (skeleton — 담당자 실행 시 주석 해제)
    # from services.data_go_kr import ADDITIVE_STANDARD, DataGoKrClient
    #
    # client = DataGoKrClient(api_key=api_key)
    # results: list[dict] = []
    # page = 1
    # try:
    #     while len(results) < limit:
    #         body = await client.call(
    #             ADDITIVE_STANDARD,
    #             {"pageNo": str(page), "numOfRows": str(page_size)},
    #         )
    #         items = _extract_items(body)
    #         if not items:
    #             break
    #         for item in items:
    #             if len(results) >= limit:
    #                 break
    #             results.append({
    #                 "spec_val": item.get("SPEC_VAL"),
    #                 "unit_nm": item.get("UNIT_NM"),
    #                 "spec_val_sumup": item.get("SPEC_VAL_SUMUP"),
    #                 "fnprt_itm_nm": item.get("FNPRT_ITM_NM"),
    #                 "pc_kor_nm": item.get("PC_KOR_NM"),
    #                 "t_kor_nm": item.get("T_KOR_NM"),
    #             })
    #         page += 1
    # finally:
    #     await client.aclose()
    # return results

    # skeleton 모드: 실행하지 않고 안내 메시지만 반환
    logger.warning(
        "collect_spec_vals: skeleton 모드. 실 API 호출하려면 코드 주석 해제 후 실행하세요."
    )
    return []


def _extract_items(body: dict) -> list[dict]:
    """raw API 응답에서 items 추출."""
    try:
        return body["response"]["body"]["items"] or []
    except (KeyError, TypeError):
        return []


def main() -> None:
    parser = argparse.ArgumentParser(
        description="data.go.kr 15116583 SPEC_VAL 수집 (skeleton — 실 실행은 담당자)"
    )
    parser.add_argument(
        "--output",
        default="tests/fixtures/spec_val_collected.json",
        help="출력 JSON 파일 경로 (기본: tests/fixtures/spec_val_collected.json)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="수집 최대 건수 (기본: 100)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("F1_DATA_GO_KR_API_KEY", "")
    if not api_key:
        print(
            "ERROR: F1_DATA_GO_KR_API_KEY 환경변수가 설정되지 않았습니다.\n"
            "  export F1_DATA_GO_KR_API_KEY=<서비스키>\n"
            "  python scripts/f1_collect_spec_val.py --output <경로>",
            file=sys.stderr,
        )
        sys.exit(1)

    logging.basicConfig(level=logging.INFO)

    results = asyncio.run(collect_spec_vals(api_key, limit=args.limit))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"수집 완료: {len(results)}건 → {output_path}")


if __name__ == "__main__":
    main()
