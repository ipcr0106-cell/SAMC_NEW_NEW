"""Step B — 원재료 허용여부 + 성분코드 + GMO 서비스.

P6-b (2026-04-20): 15111777 제거 + 15094202 카테고리 기반 판정으로 재설계.

재설계 배경 (API 실측, 2026-04-20):
    - 15111777 은 이름 필터가 작동하지 않음 (어떤 파라미터 보내도 전체 5,312건
      dump 만 반환) → 원재료별 호출이 의미 없음
    - 15111777 응답에 식약처 성분코드 필드도 없음 (INGD_SN 은 단순 일련번호)
    - 에탄올·정제수 등 화학첨가물은 15111777 에 애초에 없고 15094202 에 있음
    - 따라서 판정은 15094202 의 CPNT_LCLS_CD_NM (식품원료/식품첨가물/식품유형/
      건강기능식품) + CPNT_CD prefix (*Z* = 외화획득용) 조합으로 수행

구현 범위:
    1. `normalize_name()`                  — strip + 다중공백 단일화 + `·` → `,`
    2. 2 API 병렬 호출 (asyncio.gather)   — 15094202 / 15111913
    3. 쿼리 키 전략                         — F0 `matched_name_ko` 우선, 없으면 원본 이름
    4. 15094202 정확 매칭                  — CPNT_CD(F0 코드) 우선, 다음 KOR_NM 정확 일치
    5. 카테고리 기반 verdict               — `_resolve_verdict_by_category`
    6. 법령 출처 + 경고 매핑               — `_LAW_SOURCE_BY_CATEGORY`/`_WARNING_BY_CATEGORY`
    7. 15111913 GMO                        — 정확 일치만 (퍼지 금지)
    8. sub_ingredients 평탄화              — flatten 후 매칭
    9. 합성향료 자동 감지                  — `is_synthetic_flavor()` → unidentified
   10. 조기 종료 시그널                    — `*Z*` restricted 일괄, prohibited 는 Step A 전담

참조:
    - 계획/f1 재설계 계획/02_Step_B_원재료_매칭_설계.md (P6-b 재설계)
    - calling: backend/services/feature1.py `run_feature1_v2`
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Iterable, List, Literal, Optional, Tuple

from common.match_method import MatchMethod
from common.result import Result
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


# ---------------------------------------------------------------------------
# P6-b (2026-04-20) — 카테고리 기반 verdict 매핑 상수
# ---------------------------------------------------------------------------

# 15094202 CPNT_LCLS_CD_NM → 법령 출처 (프론트 "법령 출처" 컬럼 표시용)
_LAW_SOURCE_BY_CATEGORY: dict[str, str] = {
    "식품원료": "식품의 기준 및 규격 (별표 1 사용 가능 원료)",
    "식품첨가물": "식품첨가물의 기준 및 규격",
    "식품유형": "식품의 기준 및 규격 (식품유형)",
    "건강기능식품": "건강기능식품의 기준 및 규격",
    "기구 및 용기포장": "기구 및 용기·포장의 기준 및 규격",
}

# 15094202 CPNT_LCLS_CD_NM → 사용자 경고 템플릿
# `{name}` 은 ing.name 으로 format() 된다.
_WARNING_BY_CATEGORY: dict[str, str] = {
    "식품첨가물": "{name}: 식품첨가물 기준규격(사용량 제한) 준수 필수",
    "식품유형": "{name}: 식품유형 분류 — 가공 용도로 사용 가능",
    "건강기능식품": "{name}: 개별 인정형 — 건강기능식품 기능성 원료 확인 필요",
}

# *Z* 접미는 외화획득용 성분코드 (일반 수입 제한)
_FOREIGN_EXCHANGE_LAW_SOURCE = "외화획득용 한정 (일반 수입 불가)"
_FOREIGN_EXCHANGE_WARNING_TEMPLATE = "{name}: 외화획득용 한정 — 일반 수입 불가"


def _is_foreign_exchange_code(cpnt_cd: str) -> bool:
    """CPNT_CD 앞 2자리가 `*Z*` 형태면 외화획득용 성분.

    예: `AZ000083000000`, `BZ000094000000`, `CZ...`
    """
    prefix = (cpnt_cd or "").strip()[:2].upper()
    return len(prefix) == 2 and prefix[1] == "Z"


def _pick_exact_component_item(
    ing: Ingredient,
    normalized: str,
    comp_items: List[dict],
) -> Tuple[Optional[dict], Optional[MatchMethod]]:
    """15094202 응답에서 정확 매칭 1건 선택.

    우선순위 (P6-b + 영문명 보강):
        1. F0 성분코드(`ingredient_code_f0`) == `CPNT_CD` (정확 매칭) → "exact"
        2. `KOR_NM.strip()` == `normalized`                            → "normalized"
        3. `ENG_NM.strip().lower()` == 원본 영문명.lower()             → "fuzzy"
        4. synonym 테이블 조회 후 재매칭                                → "synonym"

    Returns:
        (매칭된 아이템 또는 None, MatchMethod 또는 None).
    """
    if not comp_items:
        return None, None

    code_f0 = (ing.ingredient_code_f0 or "").strip()
    if code_f0:
        for it in comp_items:
            if (it.get("CPNT_CD") or "").strip() == code_f0:
                return it, "exact"

    norm_lower = normalized.lower()
    for it in comp_items:
        if (it.get("KOR_NM") or "").strip() == normalized:
            return it, "normalized"

    # 영문명 매칭: 원본 이름의 괄호 안 영문명으로 ENG_NM 비교
    eng_from_input = _extract_english_name(ing.name).lower()
    if eng_from_input:
        for it in comp_items:
            eng_nm = (it.get("ENG_NM") or "").strip().lower()
            if eng_nm and eng_nm == eng_from_input:
                return it, "fuzzy"

    # 기존 fallback: normalized(한글명)으로 ENG_NM 비교 (동일 표기 원료용)
    for it in comp_items:
        if (it.get("ENG_NM") or "").strip().lower() == norm_lower and norm_lower:
            return it, "fuzzy"
    return None, None


def _resolve_verdict_by_category(
    item: Optional[dict],
) -> tuple[Verdict, Optional[str], Optional[str]]:
    """15094202 정확 매칭 아이템에서 verdict / law_source / warning_template 결정.

    판정 규칙 (P6-b):
        - `CPNT_CD` 에 *Z* 접미(외화획득용) → `restricted`
        - `CPNT_LCLS_CD_NM`:
            * "식품원료"      + `USE_DIVS_CD_NM="사용가능"` → `allowed`
            * "식품원료"      + 그 외                     → `restricted` (사용 제한)
            * "식품첨가물"                                → `allowed` (사용량 제한 경고)
            * "식품유형"                                  → `allowed` (가공 용도 경고)
            * "건강기능식품"                              → `restricted` (개별 인정 경고)
            * "기구 및 용기포장"                          → `allowed` (무경고)
        - 매칭 없음 / 미지의 카테고리 → `unidentified`

    Returns:
        (verdict, law_source, warning_template)
            warning_template 은 `{name}` placeholder 를 가진 미포맷 문자열.
    """
    if not item:
        return "unidentified", None, None

    cpnt_cd = (item.get("CPNT_CD") or "").strip()
    lcls = (item.get("CPNT_LCLS_CD_NM") or "").strip()
    use = (item.get("USE_DIVS_CD_NM") or "").strip()

    if _is_foreign_exchange_code(cpnt_cd):
        return (
            "restricted",
            _FOREIGN_EXCHANGE_LAW_SOURCE,
            _FOREIGN_EXCHANGE_WARNING_TEMPLATE,
        )

    if lcls == "식품원료":
        if use == "사용가능":
            return "allowed", _LAW_SOURCE_BY_CATEGORY[lcls], None
        return "restricted", "식품의 기준 및 규격 (사용 제한 — 담당자 확인 필요)", None

    if lcls in ("식품첨가물", "식품유형", "건강기능식품", "기구 및 용기포장"):
        verdict: Verdict = (
            "restricted" if lcls == "건강기능식품" else "allowed"
        )
        return (
            verdict,
            _LAW_SOURCE_BY_CATEGORY[lcls],
            _WARNING_BY_CATEGORY.get(lcls),
        )

    return "unidentified", None, None


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


def _check_part_compatibility(
    ing_part: Optional[str], edible_parts: Optional[str]
) -> bool:
    """라벨 사용 부위(`ing_part`) 가 식용 가능 부위(`edible_parts`) 에 포함되는지.

    비교 규칙 (관대하게):
        - 둘 중 하나라도 비어있으면 True (검증 불가 → 통과)
        - 부분 문자열 매칭 (예: ing_part='뿌리' / edible='뿌리,줄기' → True)
        - 양쪽 strip 후 비교

    Returns:
        True 면 호환 (또는 검증 불가), False 면 명시적 불일치.
    """
    if not ing_part or not edible_parts:
        return True
    return ing_part.strip() in edible_parts


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
# DB 폴백 — f1_allowed_ingredients (API unidentified 시 보조 판정)
# ---------------------------------------------------------------------------


def _query_db_allowed_fallback(
    normalized: str,
) -> tuple[Verdict, Optional[str], Optional[str]]:
    """API가 unidentified를 반환했을 때 f1_allowed_ingredients 테이블을 보조 조회.

    name_ko 정규화 비교(strip + 소문자)로 exact match. 폴백 소스이므로
    miss/오류 시 ("unidentified", None, None) 반환.

    Returns:
        (verdict, law_source, conditions)
    """
    if not normalized:
        return "unidentified", None, None
    try:
        from db.supabase_client import get_supabase  # lazy import

        supabase = get_supabase()
        rows = (
            supabase.table("f1_allowed_ingredients")
            .select("name_ko, allowed_status, conditions, law_source")
            .execute()
            .data
        )
        if not rows:
            return "unidentified", None, None

        norm_lower = normalized.strip().lower()
        for row in rows:
            db_name = (row.get("name_ko") or "").strip().lower()
            if db_name == norm_lower:
                status = (row.get("allowed_status") or "").strip()
                law = row.get("law_source") or None
                conditions = row.get("conditions") or None
                if status == "permitted":
                    return "allowed", law, None
                if status == "restricted":
                    return "restricted", law, conditions
        return "unidentified", None, None
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Step B DB fallback failed for '%s': %s — returning unidentified",
            normalized,
            exc,
        )
        return "unidentified", None, None


# ---------------------------------------------------------------------------
# DataGoKrClient 팩토리 (테스트에서 monkeypatch 가능)
# ---------------------------------------------------------------------------

_CLIENT_SINGLETON: Optional[DataGoKrClient] = None


def _get_client() -> Optional[DataGoKrClient]:
    """DataGoKrClient 싱글톤. API 키 없으면 None 반환 (F0 성분코드 fallback 사용)."""
    global _CLIENT_SINGLETON
    if _CLIENT_SINGLETON is None:
        api_key = os.environ.get("F1_DATA_GO_KR_API_KEY", "")
        if not api_key:
            logger.warning("F1_DATA_GO_KR_API_KEY 미설정 — F0 성분코드 기반 판정으로 전환")
            return None
        _CLIENT_SINGLETON = DataGoKrClient(api_key=api_key)
    return _CLIENT_SINGLETON


def _resolve_verdict_by_f0_code(ing: Ingredient) -> tuple[Verdict, Optional[str], Optional[str]]:
    """F0에서 매칭된 ingredient_code_f0의 접두어로 verdict를 결정한다.

    성분코드 체계:
        A = 식품원료 → allowed
        B = 식품첨가물 → allowed (사용량 제한 경고)
        C = 건강기능식품 → restricted (개별 인정 확인 필요)
        P = 식품유형 → allowed
        그 외/없음 → unidentified
    """
    code = (ing.ingredient_code_f0 or "").strip()
    if not code:
        return "unidentified", None, None

    prefix = code[0].upper() if code else ""
    if prefix == "A":
        return "allowed", "식품의 기준 및 규격 (별표 1 사용 가능 원료)", None
    elif prefix == "B":
        return "allowed", "식품첨가물의 기준 및 규격", "{name}: 식품첨가물 기준규격(사용량 제한) 준수 필수"
    elif prefix == "C":
        return "restricted", "건강기능식품의 기준 및 규격", "{name}: 개별 인정형 — 건강기능식품 기능성 원료 확인 필요"
    elif prefix == "P":
        return "allowed", "식품의 기준 및 규격 (식품유형)", None
    else:
        return "unidentified", None, None


def set_client_for_test(client: Optional[DataGoKrClient]) -> None:
    """테스트 헬퍼 — 전역 싱글톤을 외부에서 주입/해제."""
    global _CLIENT_SINGLETON
    _CLIENT_SINGLETON = client


# ---------------------------------------------------------------------------
# 3 API 병렬 호출
# ---------------------------------------------------------------------------


async def _safe_call(
    coro: Any, endpoint_id: str, name: str
) -> "Result[Tuple[str, str, Any]]":
    """개별 API 호출 래퍼. Result 타입 반환으로 예외를 명시적으로 표현."""
    try:
        payload = await coro
        return Result.ok((endpoint_id, name, payload))
    except DataGoKrError as exc:
        logger.warning(
            "Step B %s lookup failed (endpoint=%s, name=%s): %s",
            endpoint_id,
            exc.endpoint,
            name,
            exc,
        )
        return Result.err(f"{endpoint_id}:{name}:{exc}")
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Step B %s unexpected error on %s", endpoint_id, name)
        return Result.err(f"{endpoint_id}:{name}:{exc}")


async def _fetch_all(
    client: DataGoKrClient,
    normalized_names: List[str],
) -> dict[Tuple[str, str], Any]:
    """2 엔드포인트 × N 이름 병렬 호출.

    P6-b (2026-04-20): 15111777 제거 — 이름 필터 미작동 + 첨가물 미수록으로
    기여 없음. 15094202 (성분코드) + 15111913 (GMO) 만 병렬 호출.

    Returns:
        {(endpoint_id, name): response | Exception}.
    """
    tasks: List[Any] = []
    for n in normalized_names:
        if not n:
            continue
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
    results = await asyncio.wait_for(
        asyncio.gather(*tasks, return_exceptions=True), timeout=60.0
    )
    out: dict[Tuple[str, str], Any] = {}
    for result in results:
        if isinstance(result, BaseException):
            # _safe_call 외부에서 발생한 예외 — 방어적으로 skip
            continue
        if result.is_err():
            logger.warning("Step B API call failed: %s", result.reason)
            continue
        endpoint_id, name, payload = result._value
        out[(endpoint_id, name)] = payload
    return out


# ---------------------------------------------------------------------------
# 메인 엔트리 — run_step_b (Day 0 시그니처 유지)
# ---------------------------------------------------------------------------


def _extract_korean_name(raw: str) -> str:
    """괄호 이전의 한글명만 추출. 'ㅇ산화황 (Sulphur dioxide)' → '이산화황'."""
    if not raw:
        return ""
    paren_idx = raw.find("(")
    if paren_idx > 0:
        return raw[:paren_idx].strip()
    return raw.strip()


def _extract_english_name(raw: str) -> str:
    """괄호 안의 영문명 추출. '이산화황 (Sulphur dioxide)' → 'Sulphur dioxide'."""
    if not raw:
        return ""
    start = raw.find("(")
    end = raw.rfind(")")
    if start >= 0 and end > start:
        return raw[start + 1:end].strip()
    return ""


def _query_key(ing: Ingredient) -> str:
    """API 쿼리 키 선택 — F0 표준명 우선, 없으면 괄호 이전 한글명 추출.

    우선순위:
        1. F0 매칭 표준명 (matched_name_ko) — 가장 정확
        2. 원본 이름에서 괄호 이전 한글명 추출 — fallback
        3. 원본 이름 그대로 — 최후 수단
    """
    standard = (ing.matched_name_ko or "").strip() if ing.matched_name_ko else ""
    if standard:
        return normalize_name(standard)
    # 괄호+영문 포함된 원본에서 한글명만 추출
    korean = _extract_korean_name(ing.name)
    if korean:
        return normalize_name(korean)
    return normalize_name(ing.name)


async def run_step_b(ingredients: list[Ingredient]) -> StepBResult:
    """2 API 병렬 호출 → 원재료별 allow_verdict·component_code·is_gmo 집계.

    Day 0 시그니처 유지. P6-b 로 내부 로직 재설계.

    Args:
        ingredients: Step A 통과한 원재료 목록. `sub_ingredients` 는 내부에서 평탄화.

    Returns:
        `StepBResult` — `enriched_ingredients` 에 verdict·component_code·is_gmo 채워진
        `Ingredient` 목록. `warnings` 에 카테고리별 사용자 경고 누적.
    """
    flat = flatten_ingredients(ingredients)
    empty_stats = {
        DataGoKrEndpoint.IMPORT_FOOD_COMPONENT.value: 0,
        DataGoKrEndpoint.FOOD_RAW_MATERIAL.value: 0,
    }
    if not flat:
        return StepBResult(
            enriched_ingredients=[],
            unidentified=[],
            conditional=[],
            gmo_ingredients=[],
            api_call_stats=empty_stats,
            warnings=[],
        )

    # 원재료별 쿼리 키 (matched_name_ko 우선) — 중복 dedup 하되 순서는 보존
    normalized_map: dict[int, str] = {id(ing): _query_key(ing) for ing in flat}
    unique_names: List[str] = []
    seen: set = set()
    for n in normalized_map.values():
        if n and n not in seen:
            seen.add(n)
            unique_names.append(n)

    # 2 API 병렬 호출 (15094202 / 15111913) — API 키 없으면 F0 코드 fallback
    client = _get_client()
    responses: dict = {}
    if client is not None:
        responses = await _fetch_all(client, unique_names)

    # 집계
    enriched: List[Ingredient] = []
    unidentified: List[str] = []
    conditional: List[Ingredient] = []
    gmo_ingredients: List[str] = []
    warnings: List[str] = []

    api_stats: dict[str, int] = dict(empty_stats)
    for (endpoint_id, _n), _payload in responses.items():
        if endpoint_id in api_stats:
            api_stats[endpoint_id] += 1

    for ing in flat:
        normalized = normalized_map[id(ing)]
        if not normalized:
            unidentified.append(ing.name or "")
            ing.allow_verdict = "unidentified"
            ing.source_api = None
            setattr(ing, "match_method", None)
            enriched.append(ing)
            continue

        # 합성향료 자동 감지 — 자동 판정 금지 (02번 §8)
        if is_synthetic_flavor(normalized):
            ing.allow_verdict = "unidentified"
            ing.source_api = None
            setattr(ing, "match_method", None)
            if ing.name not in unidentified:
                unidentified.append(ing.name)
            enriched.append(ing)
            continue

        comp_payload = responses.get(
            (DataGoKrEndpoint.IMPORT_FOOD_COMPONENT.value, normalized)
        )
        gmo_payload = responses.get(
            (DataGoKrEndpoint.FOOD_RAW_MATERIAL.value, normalized)
        )

        comp_items: List[dict] = []
        if isinstance(comp_payload, dict):
            comp_items = [
                it for it in comp_payload.get("items", []) if isinstance(it, dict)
            ]

        gmo_items: List[dict] = []
        if isinstance(gmo_payload, dict):
            gmo_items = [
                it for it in gmo_payload.get("items", []) if isinstance(it, dict)
            ]

        # ── 15094202 정확 매칭 + 카테고리 기반 verdict ────────────
        exact_item, match_method = _pick_exact_component_item(ing, normalized, comp_items)
        setattr(ing, "match_method", match_method)
        verdict, law_source, warning_template = _resolve_verdict_by_category(exact_item)

        ing.law_source = law_source

        if verdict == "unidentified":
            # API miss → f1_allowed_ingredients DB 폴백
            db_verdict, db_law, db_cond = await asyncio.to_thread(
                _query_db_allowed_fallback, normalized
            )
            if db_verdict != "unidentified":
                verdict = db_verdict
                law_source = db_law
                warning_template = (
                    f"{{name}}: {db_cond}" if db_cond and db_verdict == "restricted" else None
                )
                ing.law_source = law_source
                logger.info(
                    "Step B DB fallback hit: '%s' → %s (source: f1_allowed_ingredients)",
                    normalized,
                    verdict,
                )
            else:
                # DB도 miss → F0 성분코드 기반 판정 (2차 fallback)
                f0_verdict, f0_law, f0_warn = _resolve_verdict_by_f0_code(ing)
                if f0_verdict != "unidentified":
                    verdict = f0_verdict
                    law_source = f0_law
                    warning_template = f0_warn
                    ing.law_source = law_source
                    setattr(ing, "match_method", "f0_code")
                    logger.info(
                        "Step B F0 code fallback: '%s' → %s (code: %s)",
                        ing.name, verdict, ing.ingredient_code_f0,
                    )
        elif verdict == "allowed":
            # API → allowed 이지만 DB에 restricted 등재 시 사용 제한 우선 적용.
            # 사례: 과라나·은행·하수오 등 15094202가 "사용가능"으로 반환하나
            #       식품공전 [별표2]에 조건부 제한이 있는 원료.
            db_verdict, db_law, db_cond = await asyncio.to_thread(
                _query_db_allowed_fallback, normalized
            )
            if db_verdict == "restricted":
                verdict = "restricted"
                law_source = db_law or law_source
                warning_template = f"{{name}}: {db_cond}" if db_cond else None
                ing.law_source = law_source
                logger.info(
                    "Step B DB restriction upgrade: '%s' allowed→restricted (별표2)",
                    normalized,
                )

        ing.allow_verdict = verdict

        if verdict in ("allowed", "restricted"):
            ing.source_api = (
                DataGoKrEndpoint.IMPORT_FOOD_COMPONENT.value
                if exact_item is not None
                else "db_fallback"
            )
            if warning_template:
                warnings.append(warning_template.format(name=ing.name))
            if verdict == "restricted":
                conditional.append(ing)
        else:  # unidentified
            ing.source_api = None
            if ing.name not in unidentified:
                unidentified.append(ing.name)

        # 감사용 성분코드 — 정확 매칭 결과 우선, 없으면 레거시 카테고리 기반
        if exact_item is not None:
            ing.component_code = (exact_item.get("CPNT_CD") or "").strip() or None
        else:
            ing.component_code = _pick_component_code(normalized, comp_items)

        # ── 15111913 GMO 플래그 ─────────────────────────────────
        ing.is_gmo = _pick_gmo_flag(normalized, gmo_items)
        if ing.is_gmo is True and ing.name not in gmo_ingredients:
            gmo_ingredients.append(ing.name)

        enriched.append(ing)

    # P6-b: prohibited 판정은 Step A 전담이므로 Step B 에서는 stopped=False 기본.
    # (restricted 만 있으면 Step C 로 계속 진행)
    return StepBResult(
        enriched_ingredients=enriched,
        unidentified=unidentified,
        conditional=conditional,
        gmo_ingredients=gmo_ingredients,
        api_call_stats=api_stats,
        warnings=warnings,
        stopped=False,
    )


__all__ = [
    "run_step_b",
    "normalize_name",
    "flatten_ingredients",
    "resolve_verdict",
    "set_client_for_test",
    # P6-b 신규 공개
    "_pick_exact_component_item",
    "_resolve_verdict_by_category",
    "_is_foreign_exchange_code",
]
