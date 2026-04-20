"""Step B — 원재료 허용여부 + 성분코드 + GMO 서비스 (W2-B 본체).

본 파일의 `run_step_b` 시그니처는 **Wave 2 Day 0에 동결**되었다.
W2-B 트랙이 본체를 구현하되 Day 0 시그니처는 유지한다.

구현 범위 (02번 §2~§11):
    1. `normalize_name()`                  — strip + 다중공백 단일화 + `·` → `,`
    2. 3 API 병렬 호출 (asyncio.gather)   — 15111777 / 15094202 / 15111913
    3. `resolve_verdict()`                 — prohibited > restricted > allowed 안전측 채택
    4. 이름 매칭 4 전략                    — exact / alias / scientific / Levenshtein fallback
    5. 15094202 성분코드                   — KOR_NM strip + 식품원료/첨가물 우선 + 사용가능 우선
    6. 15111913 GMO                        — 정확 일치만 (퍼지 금지)
    7. sub_ingredients 평탄화              — flatten 후 매칭
    8. 조기 종료 시그널                    — prohibited 검출 시 `StepBResult.stopped=True` (확장 필드)
    9. Levenshtein fallback 자동 확정 금지 — unidentified → HITL-1
   10. 합성향료 자동 감지                  — `is_synthetic_flavor()` → unidentified

참조:
    - 계획/f1 재설계 계획/02_Step_B_원재료_매칭_설계.md ⭐
    - 계획/f1 재설계 계획/06_API_클라이언트_설계.md (15111777/15094202/15111913)
    - calling: backend/services/feature1.py `run_feature1_v2`
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Iterable, List, Literal, Optional, Tuple

from constants.thresholds_config import is_synthetic_flavor
from exceptions import DataGoKrError
from models.f1_types import DataGoKrEndpoint, StepBResult
from models.judgment import Ingredient
from services.data_go_kr import DataGoKrClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# synonym 조회 (f1_ingredient_synonyms 테이블)
# ---------------------------------------------------------------------------


def _lookup_synonym(name_variant: str) -> Optional[str]:
    """f1_ingredient_synonyms 테이블에서 name_variant → name_standard 변환.

    Supabase ilike 쿼리로 대소문자 무관 일치 검색.
    hit 이면 name_standard 반환, miss/오류 이면 None 반환.

    인자:
        name_variant: 정규화된 원재료명 입력값 (normalize_name 적용 후)

    반환:
        name_standard (str) — DB hit 시 표준명
        None              — miss 또는 Supabase 오류 (graceful fallback)
    """
    if not name_variant:
        return None
    try:
        from db.supabase_client import get_supabase  # lazy import (테스트 격리)

        supabase = get_supabase()
        result = (
            supabase.table("f1_ingredient_synonyms")
            .select("name_standard")
            .ilike("name_variant", name_variant)
            .limit(1)
            .execute()
        )
        rows = result.data if result and hasattr(result, "data") else []
        if rows:
            standard = (rows[0].get("name_standard") or "").strip()
            if standard:
                logger.info(
                    "Step B synonym hit: '%s' → '%s'",
                    name_variant,
                    standard,
                )
                return standard
        logger.debug("Step B synonym miss: '%s'", name_variant)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Step B synonym lookup failed for '%s': %s — falling back to next strategy",
            name_variant,
            exc,
        )
        return None


# ---------------------------------------------------------------------------
# 정규화 & 평탄화
# ---------------------------------------------------------------------------

_MULTI_WS_RE = re.compile(r"\s+")


def normalize_name(raw: Optional[str]) -> str:
    """원재료명 정규화 (02번 §3-1).

    - `None`/빈 문자열 → `""`
    - strip + 다중공백 단일화 + `·` → `,` 통일
    """
    if not raw:
        return ""
    name = raw.strip()
    name = _MULTI_WS_RE.sub(" ", name)
    name = name.replace("·", ",")
    return name


def flatten_ingredients(ingredients: Iterable[Ingredient]) -> List[Ingredient]:
    """`sub_ingredients` 를 깊이 우선으로 평탄화 (02번 §8).

    동일 인스턴스가 여러 경로로 등장해도 중복 원재료는 제거하지 않는다(동명이인 보존).
    상위 원재료도 결과에 포함된다 (Step B 매칭 대상).
    """
    flat: List[Ingredient] = []
    for ing in ingredients:
        if ing is None:
            continue
        flat.append(ing)
        if ing.sub_ingredients:
            flat.extend(flatten_ingredients(ing.sub_ingredients))
    return flat


# ---------------------------------------------------------------------------
# Levenshtein (fallback, 자동 확정 금지용)
# ---------------------------------------------------------------------------


def _levenshtein(a: str, b: str) -> int:
    """편집거리 (DP). 빈 문자열 안전 처리. 짧은 이름은 호출자가 threshold 조정."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    # b(더 짧은 쪽)를 내부 루프에
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(
                prev[j] + 1,          # deletion
                curr[j - 1] + 1,      # insertion
                prev[j - 1] + cost,   # substitution
            )
        prev = curr
    return prev[-1]


def _levenshtein_threshold(name: str) -> int:
    """02번 §5 — 짧은 이름(≤4자)은 ≤1, 그 외 ≤2."""
    return 1 if len(name) <= 4 else 2


# ---------------------------------------------------------------------------
# 15111777 — 원재료 허용여부 매칭 + verdict 판정
# ---------------------------------------------------------------------------


Verdict = Literal["allowed", "restricted", "prohibited", "unidentified"]


def _split_aliases(raw: Optional[str]) -> List[str]:
    """`NKNM_NM` (콤마·슬래시 혼재) 를 alias 리스트로 분리."""
    if not raw:
        return []
    # 콤마 또는 슬래시 구분자
    parts = re.split(r"[,/]", raw)
    return [p.strip() for p in parts if p and p.strip()]


def _match_ingredient_hits(
    normalized: str,
    raw_items: List[dict],
) -> Tuple[List[dict], str]:
    """15111777 응답 items 에서 `normalized` 와 매칭되는 후보를 추려 반환.

    Returns:
        (matched_items, match_strategy)
            - `match_strategy` ∈ {"exact", "alias", "scientific", "fuzzy", "none"}
    """
    if not normalized or not raw_items:
        return [], "none"

    # 1차: INGD_NM 정확 일치
    exacts = [it for it in raw_items if (it.get("INGD_NM") or "").strip() == normalized]
    if exacts:
        return exacts, "exact"

    # 2차: NKNM_NM 이명 (콤마 분리) 중 하나와 정확 일치
    alias_hits = [
        it
        for it in raw_items
        if normalized in _split_aliases(it.get("NKNM_NM"))
    ]
    if alias_hits:
        return alias_hits, "alias"

    # 3차: 학명 부분 일치 (SCNNM_NM)
    if len(normalized) >= 3:
        sci_hits = [
            it
            for it in raw_items
            if normalized.lower() in (it.get("SCNNM_NM") or "").lower()
        ]
        if sci_hits:
            return sci_hits, "scientific"

    # 4차: Levenshtein fallback — 자동 확정 금지 (caller 가 unidentified 처리)
    threshold = _levenshtein_threshold(normalized)
    fuzzy_hits = [
        it
        for it in raw_items
        if (it.get("INGD_NM") or "").strip()
        and _levenshtein((it.get("INGD_NM") or "").strip(), normalized) <= threshold
    ]
    if fuzzy_hits:
        return fuzzy_hits, "fuzzy"

    return [], "none"


def resolve_verdict(
    hits: List[dict],
    comp_items: Optional[List[dict]] = None,
    gmo_items: Optional[List[dict]] = None,
    normalized: str = "",
) -> Verdict:
    """3개 API 결과를 합산해 verdict 를 **안전측**으로 산출.

    우선순위: prohibited > restricted > allowed > unidentified.

    prohibited:  15111777 EDIBLE_INFO="불가" 또는 EDIBLE_N="o"
    restricted:  15111777 CHRTR_INFO_CONT 존재
    allowed:     15111777 "가능" OR
                 15094202 USE_DIVS_CD_NM="사용가능" (가공품 커버) OR
                 15111913 ORM_STD_NM 정확 일치 레코드 존재 (식약처 등재 사실만으로 인정)
    unidentified: 위 어느 조건도 미충족

    prohibited·restricted 는 15111777만 — 안전측 판정 소스는 단일하게 유지.
    allowed 확장은 15094202/15111913 으로 커버 (가공품·파생품 누락 보완).
    """
    # ── prohibited (15111777만, 안전측 소스 단일 유지) ─────────────────
    has_prohibited = any(
        (h.get("EDIBLE_INFO") == "불가")
        or ((h.get("EDIBLE_N") or "").lower() == "o")
        for h in hits
    )
    if has_prohibited:
        return "prohibited"

    # ── restricted (15111777만) ─────────────────────────────────────────
    has_condition = any((h.get("CHRTR_INFO_CONT") or "").strip() for h in hits)
    if has_condition:
        return "restricted"

    # ── allowed (3 API 합집합) ──────────────────────────────────────────
    # 1) 15111777: 명시적 가능 판정
    has_allowed_1777 = any(
        (h.get("EDIBLE_INFO") == "가능")
        or ((h.get("EDIBLE_Y") or "").lower() == "o")
        for h in hits
    )
    # 2) 15094202: 식약처 성분코드 DB에 "사용가능"으로 등재 (가공품 커버)
    has_allowed_94202 = any(
        (it.get("USE_DIVS_CD_NM") or "").strip() == "사용가능"
        and (it.get("KOR_NM") or "").strip() == normalized
        for it in (comp_items or [])
    )
    # 3) 15111913: 식약처 원재료 DB에 ORM_STD_NM 정확 등재 (등재 사실만으로 인정)
    has_allowed_1913 = any(
        (it.get("ORM_STD_NM") or "").strip() == normalized
        for it in (gmo_items or [])
    )
    if has_allowed_1777 or has_allowed_94202 or has_allowed_1913:
        return "allowed"

    return "unidentified"


def _primary_condition(hits: List[dict]) -> Optional[str]:
    """restricted 원재료의 대표 조건 텍스트."""
    for h in hits:
        txt = (h.get("CHRTR_INFO_CONT") or "").strip()
        if txt:
            return txt
    return None


def _primary_edible_parts(hits: List[dict]) -> Optional[str]:
    """첫 번째 `EDIBLE_USE_CONT` (식용 가능 부위)."""
    for h in hits:
        txt = (h.get("EDIBLE_USE_CONT") or "").strip()
        if txt:
            return txt
    return None


# ---------------------------------------------------------------------------
# 15094202 — 성분코드 매칭
# ---------------------------------------------------------------------------

# CPNT_LCLS_CD_NM 우선순위 — 식품원료 > 식품첨가물 > 기타 (02번 §6)
_COMPONENT_CATEGORY_PRIORITY = {
    "식품원료": 0,
    "식품첨가물": 1,
}


def _pick_component_code(
    normalized: str, raw_items: List[dict]
) -> Optional[str]:
    """15094202 응답에서 최적 `CPNT_CD` 1건 선택.

    선택 규칙 (02번 §6):
        1. `KOR_NM` 앞 공백 strip 후 `normalized` 와 정확 일치 (클라이언트가 strip
           처리하지만 방어적 재확인)
        2. `USE_DIVS_CD_NM == "사용가능"` 우선
        3. `CPNT_LCLS_CD_NM` 우선순위: 식품원료 > 식품첨가물 > 기타
    """
    if not normalized or not raw_items:
        return None

    # KOR_NM 정확 일치 후보 (방어적 strip)
    candidates = [
        it for it in raw_items if (it.get("KOR_NM") or "").strip() == normalized
    ]
    # ENG_NM / NKNM_INFO_CONT 보조 매칭 — 한글명 매칭이 없을 때만
    if not candidates:
        for it in raw_items:
            eng = (it.get("ENG_NM") or "").strip().lower()
            if eng and eng == normalized.lower():
                candidates.append(it)
        if not candidates:
            for it in raw_items:
                aliases = _split_aliases(it.get("NKNM_INFO_CONT"))
                if normalized in aliases or normalized.lower() in [
                    a.lower() for a in aliases
                ]:
                    candidates.append(it)
    if not candidates:
        return None

    def sort_key(item: dict) -> Tuple[int, int]:
        use = (item.get("USE_DIVS_CD_NM") or "").strip()
        cls = (item.get("CPNT_LCLS_CD_NM") or "").strip()
        use_rank = 0 if use == "사용가능" else 1
        cls_rank = _COMPONENT_CATEGORY_PRIORITY.get(cls, 9)
        return (use_rank, cls_rank)

    best = sorted(candidates, key=sort_key)[0]
    cpnt_cd = (best.get("CPNT_CD") or "").strip()
    return cpnt_cd or None


# ---------------------------------------------------------------------------
# 15111913 — GMO 조회
# ---------------------------------------------------------------------------


def _pick_gmo_flag(normalized: str, raw_items: List[dict]) -> Optional[bool]:
    """15111913 응답에서 `GMO_YN` 추출.

    규칙 (02번 §7):
        - `ORM_STD_NM == normalized` 정확 일치만 (대용량이므로 퍼지 금지)
        - `GMO_YN == "Y"` → True, `"N"` → False
        - 미등록 또는 빈 값 → None
        - 다건 매칭 시: 하나라도 `Y` 이면 True (안전측 + F3 전달 정확도)
    """
    if not normalized or not raw_items:
        return None

    exact_hits = [
        it for it in raw_items if (it.get("ORM_STD_NM") or "").strip() == normalized
    ]
    if not exact_hits:
        return None

    flags = {(h.get("GMO_YN") or "").strip().upper() for h in exact_hits}
    if "Y" in flags:
        return True
    if "N" in flags:
        return False
    return None


# ---------------------------------------------------------------------------
# DataGoKrClient 팩토리 (테스트에서 monkeypatch 가능)
# ---------------------------------------------------------------------------

_CLIENT_SINGLETON: Optional[DataGoKrClient] = None


def _get_client() -> DataGoKrClient:
    """DataGoKrClient 싱글톤. 테스트는 `_CLIENT_SINGLETON` 직접 주입."""
    global _CLIENT_SINGLETON
    if _CLIENT_SINGLETON is None:
        api_key = os.environ.get("F1_DATA_GO_KR_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "F1_DATA_GO_KR_API_KEY not configured — required for Step B"
            )
        _CLIENT_SINGLETON = DataGoKrClient(api_key=api_key)
    return _CLIENT_SINGLETON


def set_client_for_test(client: Optional[DataGoKrClient]) -> None:
    """테스트 헬퍼 — 전역 싱글톤을 외부에서 주입/해제."""
    global _CLIENT_SINGLETON
    _CLIENT_SINGLETON = client


# ---------------------------------------------------------------------------
# 3 API 병렬 호출
# ---------------------------------------------------------------------------


async def _safe_call(
    coro: Any, endpoint_id: str, name: str
) -> Tuple[str, str, Any]:
    """개별 API 호출 래퍼. 예외 격리 (return_exceptions=True 와 함께 사용)."""
    try:
        result = await coro
        return (endpoint_id, name, result)
    except DataGoKrError as exc:
        logger.warning(
            "Step B %s lookup failed (endpoint=%s, name=%s): %s",
            endpoint_id,
            exc.endpoint,
            name,
            exc,
        )
        return (endpoint_id, name, exc)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Step B %s unexpected error on %s", endpoint_id, name)
        return (endpoint_id, name, exc)


async def _fetch_all(
    client: DataGoKrClient,
    normalized_names: List[str],
) -> dict[Tuple[str, str], Any]:
    """3 엔드포인트 × N 이름 병렬 호출.

    Returns:
        {(endpoint_id, name): response | Exception}.
    """
    tasks: List[Any] = []
    for n in normalized_names:
        if not n:
            continue
        tasks.append(
            _safe_call(
                client.get_import_food_ingredient(n),
                DataGoKrEndpoint.IMPORT_FOOD_INGREDIENT.value,
                n,
            )
        )
        tasks.append(
            _safe_call(
                client.get_import_food_component(n),
                DataGoKrEndpoint.IMPORT_FOOD_COMPONENT.value,
                n,
            )
        )
        tasks.append(
            _safe_call(
                client.get_food_raw_material(n),
                DataGoKrEndpoint.FOOD_RAW_MATERIAL.value,
                n,
            )
        )
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out: dict[Tuple[str, str], Any] = {}
    for item in results:
        if isinstance(item, BaseException):
            # gather 가 return_exceptions=True 인데 _safe_call 자체가 예외를 감쌌다
            # 는 것은 None 은 아님. 방어적으로 continue.
            continue
        endpoint_id, name, payload = item
        out[(endpoint_id, name)] = payload
    return out


# ---------------------------------------------------------------------------
# 메인 엔트리 — run_step_b (Day 0 시그니처 유지)
# ---------------------------------------------------------------------------


async def run_step_b(ingredients: list[Ingredient]) -> StepBResult:
    """3개 API 병렬 호출 → 원재료별 allow_verdict·component_code·is_gmo 집계.

    Day 0 시그니처 유지. 본체는 W2-B 트랙이 구현.

    Args:
        ingredients: Step A 통과한 원재료 목록. `sub_ingredients` 는 내부에서 평탄화.

    Returns:
        `StepBResult` — `enriched_ingredients` 에 verdict·component_code·is_gmo 채워진
        `Ingredient` 목록. `stopped=True` (확장 필드) 시 호출자(`run_feature1_v2`) 가
        Step C/D 를 skip.
    """
    flat = flatten_ingredients(ingredients)
    if not flat:
        return StepBResult(
            enriched_ingredients=[],
            unidentified=[],
            conditional=[],
            gmo_ingredients=[],
            api_call_stats={
                DataGoKrEndpoint.IMPORT_FOOD_INGREDIENT.value: 0,
                DataGoKrEndpoint.IMPORT_FOOD_COMPONENT.value: 0,
                DataGoKrEndpoint.FOOD_RAW_MATERIAL.value: 0,
            },
        )

    # 원재료명 정규화 (중복 dedup 하되 순서는 보존)
    normalized_map: dict[int, str] = {id(ing): normalize_name(ing.name) for ing in flat}
    unique_names: List[str] = []
    seen: set = set()
    for n in normalized_map.values():
        if n and n not in seen:
            seen.add(n)
            unique_names.append(n)

    # 3 API 병렬 호출
    client = _get_client()
    responses = await _fetch_all(client, unique_names)

    # 집계
    enriched: List[Ingredient] = []
    unidentified: List[str] = []
    conditional: List[Ingredient] = []
    gmo_ingredients: List[str] = []
    stopped = False

    api_stats: dict[str, int] = {
        DataGoKrEndpoint.IMPORT_FOOD_INGREDIENT.value: 0,
        DataGoKrEndpoint.IMPORT_FOOD_COMPONENT.value: 0,
        DataGoKrEndpoint.FOOD_RAW_MATERIAL.value: 0,
    }
    for (endpoint_id, _n), payload in responses.items():
        if endpoint_id in api_stats:
            # Exception 도 호출 1건으로 카운트 (감사 추적)
            api_stats[endpoint_id] += 1

    for ing in flat:
        normalized = normalized_map[id(ing)]
        if not normalized:
            unidentified.append(ing.name or "")
            ing.allow_verdict = "unidentified"
            ing.source_api = None
            enriched.append(ing)
            continue

        # 합성향료 자동 감지 — 자동 판정 금지 (02번 §8)
        if is_synthetic_flavor(normalized):
            ing.allow_verdict = "unidentified"
            ing.source_api = None
            if normalized not in unidentified:
                unidentified.append(ing.name)
            enriched.append(ing)
            continue

        ingd_payload = responses.get(
            (DataGoKrEndpoint.IMPORT_FOOD_INGREDIENT.value, normalized)
        )
        comp_payload = responses.get(
            (DataGoKrEndpoint.IMPORT_FOOD_COMPONENT.value, normalized)
        )
        gmo_payload = responses.get(
            (DataGoKrEndpoint.FOOD_RAW_MATERIAL.value, normalized)
        )

        # ── 15094202/15111913 items 선추출 (resolve_verdict 에 전달) ────
        comp_items: List[dict] = []
        if isinstance(comp_payload, dict):
            comp_items = [it for it in comp_payload.get("items", []) if isinstance(it, dict)]

        gmo_items: List[dict] = []
        if isinstance(gmo_payload, dict):
            gmo_items = [it for it in gmo_payload.get("items", []) if isinstance(it, dict)]

        # ── 15111777: verdict 판정 ─────────────────────────────
        ingd_items: List[dict] = []
        if isinstance(ingd_payload, dict):
            ingd_items = [it for it in ingd_payload.get("items", []) if isinstance(it, dict)]

        matched, strategy = _match_ingredient_hits(normalized, ingd_items)

        # ── synonym lookup (exact/alias 실패 시) ──────────────
        # 전략 순서: exact → alias → synonym lookup → scientific → Levenshtein fallback
        # exact 또는 alias 로 매칭되지 않은 경우 f1_ingredient_synonyms 조회
        if strategy in ("scientific", "fuzzy", "none"):
            synonym_standard = _lookup_synonym(normalized)
            if synonym_standard and synonym_standard != normalized:
                # name_standard 로 재조회 (캐시된 responses 에 없으면 신규 API 호출)
                synonym_payload = responses.get(
                    (DataGoKrEndpoint.IMPORT_FOOD_INGREDIENT.value, synonym_standard)
                )
                if synonym_payload is None:
                    # 캐시 미스 — 동기 블로킹 없이 새 비동기 호출
                    try:
                        synonym_payload = await _get_client().get_import_food_ingredient(
                            synonym_standard
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "Step B synonym API call failed for '%s': %s",
                            synonym_standard,
                            exc,
                        )
                        synonym_payload = None

                if isinstance(synonym_payload, dict):
                    synonym_items = [
                        it
                        for it in synonym_payload.get("items", [])
                        if isinstance(it, dict)
                    ]
                    syn_matched, syn_strategy = _match_ingredient_hits(
                        synonym_standard, synonym_items
                    )
                    if syn_strategy not in ("fuzzy", "none"):
                        # synonym 경로로 유효 매칭 성공
                        matched, strategy = syn_matched, f"synonym:{syn_strategy}"
                        logger.info(
                            "Step B synonym match: '%s' → '%s' (strategy=%s)",
                            normalized,
                            synonym_standard,
                            strategy,
                        )

        if strategy.startswith("fuzzy"):
            # Levenshtein fallback — 자동 확정 금지
            ing.allow_verdict = "unidentified"
            ing.source_api = None
            if ing.name not in unidentified:
                unidentified.append(ing.name)
        else:
            verdict = resolve_verdict(matched, comp_items=comp_items, gmo_items=gmo_items, normalized=normalized)
            ing.allow_verdict = verdict
            if verdict != "unidentified":
                ing.source_api = ",".join(
                    [
                        DataGoKrEndpoint.IMPORT_FOOD_INGREDIENT.value,
                        DataGoKrEndpoint.IMPORT_FOOD_COMPONENT.value,
                        DataGoKrEndpoint.FOOD_RAW_MATERIAL.value,
                    ]
                )

            if verdict == "restricted":
                ing.restriction_condition = _primary_condition(matched)
                ing.edible_parts = _primary_edible_parts(matched)
                conditional.append(ing)
            elif verdict == "allowed":
                ing.edible_parts = _primary_edible_parts(matched)
            elif verdict == "prohibited":
                stopped = True
            elif verdict == "unidentified":
                if ing.name not in unidentified:
                    unidentified.append(ing.name)

        # ── 15094202: 성분코드 ────────────────────────────────
        ing.component_code = _pick_component_code(normalized, comp_items)

        # ── 15111913: GMO 플래그 ──────────────────────────────
        ing.is_gmo = _pick_gmo_flag(normalized, gmo_items)
        if ing.is_gmo is True and ing.name not in gmo_ingredients:
            gmo_ingredients.append(ing.name)

        enriched.append(ing)

    # code-review 🟡-4 fix: `StepBResult.stopped` 필드로 prohibited 조기 종료
    # 여부를 명시 반환 (02번 §9). 호출자는 재계산 없이 `result.stopped` 로 판정.
    return StepBResult(
        enriched_ingredients=enriched,
        unidentified=unidentified,
        conditional=conditional,
        gmo_ingredients=gmo_ingredients,
        api_call_stats=api_stats,
        stopped=stopped,
    )


__all__ = [
    "run_step_b",
    "normalize_name",
    "flatten_ingredients",
    "resolve_verdict",
    "set_client_for_test",
]
