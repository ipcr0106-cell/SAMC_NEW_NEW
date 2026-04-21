"""F2 원재료 상위분류(food_class) 태깅 서비스.

f0_ingredient_codes의 원재료를 식품 카테고리로 분류한다.
LLM으로 태깅하고 로컬 캐시에 저장하여 재사용.

분류 체계 (식품공전 기반):
  과일류, 채소류, 곡류, 두류, 서류, 견과종실류, 버섯류, 해조류,
  식육류, 어류, 갑각류, 패류, 유류, 알류,
  당류, 유지류, 향신료, 미생물, 음료베이스, 기타
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 캐시 파일 경로
_CACHE_PATH = Path(__file__).parent.parent / "data" / "food_class_cache.json"
_cache: dict[str, str] = {}
_cache_loaded = False


def _load_cache() -> None:
    global _cache, _cache_loaded
    if _cache_loaded:
        return
    if _CACHE_PATH.exists():
        try:
            _cache = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            _cache = {}
    _cache_loaded = True


def _save_cache() -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(_cache, ensure_ascii=False, indent=2), encoding="utf-8")


def get_food_class(name_ko: str) -> Optional[str]:
    """캐시에서 원재료의 식품 카테고리를 조회."""
    _load_cache()
    return _cache.get(name_ko)


async def classify_ingredients_batch(names: list[str]) -> dict[str, str]:
    """LLM으로 원재료 목록의 식품 카테고리를 일괄 분류.

    Returns:
        {name_ko: food_class} 매핑
    """
    _load_cache()

    # 이미 캐시된 것 제외
    uncached = [n for n in names if n and n not in _cache]
    if not uncached:
        return {n: _cache.get(n, "기타") for n in names}

    api_key = os.getenv("F0_OPENAI_API_KEY", "")
    if not api_key:
        return {n: _cache.get(n, "기타") for n in names}

    # LLM 배치 호출 (최대 50개씩)
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key)

    for i in range(0, len(uncached), 50):
        batch = uncached[i:i + 50]
        try:
            resp = await client.chat.completions.create(
                model=os.getenv("F0_OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0,
                max_tokens=2000,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "원재료명을 아래 식품 카테고리 중 하나로 분류하세요.\n"
                            "카테고리: 과일류, 채소류, 곡류, 두류, 서류, 견과종실류, "
                            "버섯류, 해조류, 식육류, 어류, 갑각류, 패류, 유류, 알류, "
                            "당류, 유지류, 향신료, 미생물, 기타\n\n"
                            "규칙:\n"
                            "- 과일에서 추출한 즙/워터/밀크/퓨레/농축액 → 과일류\n"
                            "- 채소에서 추출한 즙/분말 → 채소류\n"
                            "- 정제수/물 → 기타\n"
                            "- 설탕/포도당/과당 → 당류\n"
                            "- 식품첨가물(유화제, 안정제, 산화방지제 등) → 기타\n\n"
                            "한 줄에 하나씩, '원재료명:카테고리' 형식으로만 출력하세요."
                        ),
                    },
                    {
                        "role": "user",
                        "content": "\n".join(batch),
                    },
                ],
            )
            text = (resp.choices[0].message.content or "").strip()
            for line in text.splitlines():
                line = line.strip()
                if ":" in line:
                    parts = line.split(":", 1)
                    name = parts[0].strip()
                    cls = parts[1].strip()
                    # 캐시에서 가장 가까운 이름 찾기
                    if name in batch:
                        _cache[name] = cls
                    else:
                        # 부분 매칭
                        for b in batch:
                            if b in name or name in b:
                                _cache[b] = cls
                                break
        except Exception as exc:
            logger.warning(f"F2 food_class 태깅 실패: {exc}")

    # 태깅 안 된 것은 "기타"
    for n in uncached:
        if n not in _cache:
            _cache[n] = "기타"

    _save_cache()
    return {n: _cache.get(n, "기타") for n in names}


def compute_food_class_summary(
    ingredients: list[dict],
) -> dict:
    """원재료 목록에서 식품 카테고리별 배합비율 합산.

    Returns:
        {
            "items": [{"name": ..., "pct": ..., "food_class": ...}, ...],
            "summary": {"과일류": 71.0, "기타": 28.1, ...},
            "fruit_veg_pct": 71.0,
            "is_beverage": True,
            "inferred_major": "음료류",
        }
    """
    _load_cache()

    items = []
    summary: dict[str, float] = {}
    total_excl_water = 0.0

    for ing in ingredients:
        matched = ing.get("ingredient_code_name") or ing.get("name", "")
        pct = float(ing.get("ratio", 0) or 0)
        food_class = _cache.get(matched, "기타")
        items.append({"name": matched, "pct": pct, "food_class": food_class})
        # 정제수 제외
        if matched in ("정제수", "물", "정제수(물)"):
            continue
        summary[food_class] = summary.get(food_class, 0) + pct
        total_excl_water += pct

    fruit_veg_pct = summary.get("과일류", 0) + summary.get("채소류", 0)

    # 대분류 추론
    inferred = None
    # 식육 50% 이상 → 식육가공품
    if summary.get("식육류", 0) >= 50:
        inferred = "식육가공품류 및 포장육"
    # 유류 주원료 → 유가공품
    elif summary.get("유류", 0) >= 30:
        inferred = "유가공품류"
    # 알류 주원료 → 알가공품
    elif summary.get("알류", 0) >= 50:
        inferred = "알가공품류"

    return {
        "items": items,
        "summary": summary,
        "fruit_veg_pct": fruit_veg_pct,
        "inferred_major": inferred,
    }
