"""데이터go.kr 3종 API 에서 "밀가루" 응답 확인 — Step B unidentified 원인 조사용.

실행:
    cd backend
    python -m scripts.debug_mil_garu_api

출력:
    - 콘솔: 각 API item 수 + 주요 필드 샘플
    - 파일: .omc/research/mil_garu_api_response.json (전체 raw 응답)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from services.data_go_kr import DataGoKrClient  # noqa: E402
from services.data_go_kr.endpoints import get_endpoint  # noqa: E402
from models.f1_types import DataGoKrEndpoint  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TARGET = "밀가루"
OUT_PATH = Path(__file__).parent.parent.parent / ".omc" / "research" / "mil_garu_api_response.json"


def _summarize_15111777(items: list[dict]) -> None:
    print(f"\n-- 15111777 (수입식품 원료정보) : {len(items)}건 --")
    for i, it in enumerate(items[:10], 1):
        print(
            f"  [{i}] INGD_NM={it.get('INGD_NM')!r} "
            f"EDIBLE_INFO={it.get('EDIBLE_INFO')!r} "
            f"EDIBLE_Y={it.get('EDIBLE_Y')!r} EDIBLE_N={it.get('EDIBLE_N')!r} "
            f"CHRTR_INFO_CONT={(it.get('CHRTR_INFO_CONT') or '')[:40]!r}"
        )


def _summarize_15094202(items: list[dict]) -> None:
    print(f"\n-- 15094202 (수입식품 성분코드) : {len(items)}건 --")
    for i, it in enumerate(items[:10], 1):
        print(
            f"  [{i}] KOR_NM={it.get('KOR_NM')!r} "
            f"CPNT_CD={it.get('CPNT_CD')!r} "
            f"CPNT_LCLS_CD_NM={it.get('CPNT_LCLS_CD_NM')!r} "
            f"USE_DIVS_CD_NM={it.get('USE_DIVS_CD_NM')!r}"
        )


def _summarize_15111913(items: list[dict]) -> None:
    print(f"\n-- 15111913 (식품 원재료) : {len(items)}건 --")
    for i, it in enumerate(items[:10], 1):
        print(
            f"  [{i}] ORM_STD_NM={it.get('ORM_STD_NM')!r} "
            f"GMO_YN={it.get('GMO_YN')!r}"
        )


async def main() -> None:
    api_key = os.environ.get("F1_DATA_GO_KR_API_KEY", "")
    if not api_key:
        raise RuntimeError("F1_DATA_GO_KR_API_KEY not set in backend/.env")

    client = DataGoKrClient(api_key=api_key)
    try:
        print(f"▶ 조회 대상: {TARGET!r}")
        r_ingd = await client.get_import_food_ingredient(TARGET)
        r_comp = await client.get_import_food_component(TARGET)
        r_raw = await client.get_food_raw_material(TARGET)

        items_ingd = r_ingd.get("items", [])
        items_comp = r_comp.get("items", [])
        items_raw = r_raw.get("items", [])

        _summarize_15111777(items_ingd)
        _summarize_15094202(items_comp)
        _summarize_15111913(items_raw)

        # 현재 Step B 로직과 동일한 매칭 시도
        print("\n-- Step B 매칭 시뮬레이션 --")
        exact_1777 = [it for it in items_ingd if (it.get("INGD_NM") or "").strip() == TARGET]
        exact_94202 = [it for it in items_comp if (it.get("KOR_NM") or "").strip() == TARGET]
        exact_1913 = [it for it in items_raw if (it.get("ORM_STD_NM") or "").strip() == TARGET]
        print(f"  15111777 INGD_NM 정확일치: {len(exact_1777)}건")
        print(f"  15094202 KOR_NM 정확일치: {len(exact_94202)}건")
        print(f"  15111913 ORM_STD_NM 정확일치: {len(exact_1913)}건")

        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "query": TARGET,
                    "15111777": {
                        "total_count": r_ingd.get("total_count"),
                        "items": items_ingd,
                    },
                    "15094202": {
                        "total_count": r_comp.get("total_count"),
                        "items": items_comp,
                    },
                    "15111913": {
                        "total_count": r_raw.get("total_count"),
                        "items": items_raw,
                    },
                },
                f,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        print(f"\n✅ 전체 응답 저장: {OUT_PATH}")

        # ------------------------------------------------------------------
        # 추가 검증: 15111777 에 "밀가루" 가 실제로 있는지 (numOfRows=6000 재호출)
        # ------------------------------------------------------------------
        print("\n-- 15111777 전수 조회 (numOfRows=6000) --")
        ep = get_endpoint(DataGoKrEndpoint.IMPORT_FOOD_INGREDIENT)
        body_big = await client.call(ep, {"INGD_NM": TARGET, "numOfRows": "6000", "pageNo": "1"}, use_cache=False)
        big_items = DataGoKrClient._extract_items(body_big)
        big_total = DataGoKrClient._extract_total_count(body_big)

        exact = [it for it in big_items if (it.get("INGD_NM") or "").strip() == TARGET]
        contains = [it for it in big_items if TARGET in (it.get("INGD_NM") or "")]
        print(f"  totalCount(서버보고): {big_total}")
        print(f"  수신 item 수: {len(big_items)}")
        print(f"  INGD_NM == '밀가루' 정확일치: {len(exact)}")
        print(f"  INGD_NM에 '밀가루' 포함: {len(contains)}")
        if contains:
            print("  포함 레코드 최대 10건:")
            for it in contains[:10]:
                print(
                    f"    INGD_NM={it.get('INGD_NM')!r} "
                    f"EDIBLE_INFO={it.get('EDIBLE_INFO')!r} "
                    f"EDIBLE_Y={it.get('EDIBLE_Y')!r} EDIBLE_N={it.get('EDIBLE_N')!r}"
                )
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
