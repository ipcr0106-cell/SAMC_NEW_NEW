"""
기능 3: 수입 필요서류 안내 — 매칭 엔진.

입력 (ProductInfo): 기능 1·2에서 확정된 제품 정보
처리:
  - Supabase f3_required_documents (52건) 에서 서류 룰 로드
  - f3_country_groups 에서 BSE_36·ASF_73·SEAFOOD_TREATY 등 국가 그룹 로드
  - f3_keyword_synonyms 에서 OCR/영문 정규화 룰 로드
  - 5축(effective_date·food_type·condition·country·keyword) AND 매칭
  - 통과한 서류의 합집합 반환 + 결정 축 라벨 + 매칭 근거 + 스마트 경고
출력: RequiredDocsResponse

법령 근거: 수입식품안전관리 특별법 시행규칙 제27조 + 별표9 + 별표10
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import HTTPException

from db.f3_supabase_client import (
    load_country_groups,
    load_keyword_synonyms,
    load_required_documents,
)
from models.f3_schemas import ProductInfo, RequiredDoc, RequiredDocsResponse


# ──────────────────────────────────────────────
# 식품공전 중분류 기반 판별 상수
# ──────────────────────────────────────────────

# 중분류가 이 값이면 → 소(반추동물) 원유 기반 확정 → BSE 서류 자동 발동
RUMINANT_MID_CATEGORIES: set[str] = {"유가공품", "유가공품류"}

# 중분류가 이 값이면 → 축산물(동물성 식품) 확정 → 위생증명서 자동 발동
LIVESTOCK_MID_CATEGORIES: set[str] = {
    "식육가공품", "식육가공품류",
    "유가공품", "유가공품류",
    "알가공품", "알가공품류",
}


# ──────────────────────────────────────────────
# 식품유형 직접 판별용 상수
# ──────────────────────────────────────────────

PORK_FOOD_TYPES: set[str] = {"식용돈지", "돈지", "생햄"}

RUMINANT_FOOD_TYPES: set[str] = {
    "쇠고기", "소고기",
    "원료우지", "우지",
    "양고기", "사슴고기", "생녹용",
    "원유", "우유", "가공유", "저지방우유", "탈지우유", "유당분해우유", "유음료",
    "발효유", "농후발효유", "크림발효유", "발효버터유", "발효유분말", "농후크림발효유",
    "유크림", "가공유크림", "버터", "가공버터", "버터오일", "버터유",
    "자연치즈", "가공치즈", "치즈",
    "분유", "전지분유", "탈지분유", "가당분유", "혼합분유",
    "조제분유", "성장기용조제분유", "영아용조제식", "영아용조제우유",
    "성장기용조제우유", "영유아용이유식",
    "영아용 조제유", "성장기용 조제유",
    "농축유", "연유", "가당연유", "가당탈지연유", "가공연유",
    "유청", "유청분말", "유당", "유단백가수분해식품", "유청단백분말",
    "아이스크림", "아이스크림류", "아이스밀크", "샤베트", "아이스크림분말",
    "아이스크림믹스", "비유지방아이스크림", "아이스밀크믹스",
}

LIVESTOCK_FOOD_TYPES: set[str] = {
    # 대분류
    "식육", "식육가공품", "유가공품", "알가공품", "축산물", "육류", "가금류", "가금육",
    # 식육가공품 세부
    "햄", "햄류", "생햄", "프레스햄", "소시지", "소시지류", "베이컨", "베이컨류",
    "건조저장육", "건조저장육류", "양념육", "양념육류", "분쇄가공육", "분쇄가공육제품",
    "갈비가공품", "식육추출가공품", "식육함유가공품", "포장육", "혼합소시지",
    "발효소시지", "천연케이싱", "식육케이싱",
    # 유가공품 전체 (RUMINANT_FOOD_TYPES 와 중복되는 것들 포함)
    "원유", "우유", "가공유", "저지방우유", "탈지우유", "유음료",
    "발효유", "농후발효유", "크림발효유", "발효버터유", "발효유분말",
    "농후크림발효유", "유당분해우유",
    "유크림", "가공유크림", "버터", "가공버터", "버터오일", "버터유",
    "자연치즈", "가공치즈", "치즈",
    "분유", "전지분유", "탈지분유", "가당분유", "혼합분유",
    "조제분유", "성장기용조제분유", "영아용조제식", "영아용조제우유",
    "성장기용조제우유", "영유아용이유식",
    "영아용 조제유", "성장기용 조제유",
    "농축유", "연유", "가당연유", "가당탈지연유", "가공연유",
    "유청", "유청분말", "유당", "유단백가수분해식품", "유청단백분말",
    # 알가공품 세부
    "알류", "난황", "난백", "전란분", "난황분", "난백분", "전란액", "난황액", "난백액",
    "피단", "달걀(알)", "알가열제품",
    # 지방
    "식용돈지", "원료우지", "우지", "돈지",
    # 일반 축산 원료
    "닭고기", "오리고기", "쇠고기", "돼지고기", "양고기",
    # 아이스크림류
    "아이스크림", "아이스크림류", "아이스밀크", "샤베트", "아이스크림분말",
    "아이스크림믹스", "비유지방아이스크림", "아이스밀크믹스",
}

# 식약처 복합 명칭 패턴 (예: "돼지고기(냉동,정육...)")
LIVESTOCK_FOOD_TYPE_PREFIXES: tuple[str, ...] = (
    "돼지고기(", "소고기(", "닭고기(", "양고기(", "염소고기(",
    "오리고기(", "칠면조고기(",
)


# ──────────────────────────────────────────────
# 식품유형 판별 헬퍼
# ──────────────────────────────────────────────

def is_pork_food_type(food_type: str) -> bool:
    """food_type 이 돼지 유래임을 확정할 수 있는지 판별."""
    if not food_type:
        return False
    if food_type in PORK_FOOD_TYPES:
        return True
    if food_type.startswith("돼지고기("):
        return True
    return False


def is_ruminant_food_type(food_type: str) -> bool:
    """food_type 이 반추동물(소·양·사슴) 유래임을 확정할 수 있는지 판별."""
    if not food_type:
        return False
    if food_type in RUMINANT_FOOD_TYPES:
        return True
    if food_type.startswith(("소고기(", "쇠고기(", "양고기(")):
        return True
    return False


def is_livestock_food_type(food_type: str) -> bool:
    """축산물 식품유형 판별 — 정확 매칭 + 복합 명칭 prefix."""
    if not food_type:
        return False
    if food_type in LIVESTOCK_FOOD_TYPES:
        return True
    if any(food_type.startswith(p) for p in LIVESTOCK_FOOD_TYPE_PREFIXES):
        return True
    return False


# ──────────────────────────────────────────────
# 국가 매칭
# ──────────────────────────────────────────────

def _normalize_country_for_equivalence(origin: str) -> str:
    """EU 회원국 이름을 'EU' 로 정규화 (동등성인정 매칭용)."""
    groups = load_country_groups()
    eu_members = groups.get("EU_27") or groups.get("EU_MEMBERS") or set()
    return "EU" if origin in eu_members else origin


def _match_country(db_target: Optional[str], origin: Optional[str]) -> bool:
    """DB의 target_country 태그와 실제 수출국이 매칭되는지 판단.

    target_country 특수 태그:
      NULL                        → 모든 국가 해당
      '일본'·'중국' 등 단일 국가  → 정확 일치
      'BSE관련36개국'              → BSE_36 그룹
      '모든국가(BSE36개국제외)'    → BSE_36 외
      'ASF발생73개국'              → ASF_73 그룹
      'EU'                         → EU + EU_27 회원국
      '중국,대만,베트남,태국' 등   → 콤마 구분 다국가
    """
    if db_target is None:
        return True
    if origin is None:
        return False

    groups = load_country_groups()
    bse_36 = groups.get("BSE_36", set())
    asf_73 = groups.get("ASF_73", set())
    eu_members = groups.get("EU_27") or groups.get("EU_MEMBERS") or set()

    if db_target == "BSE관련36개국":
        return origin in bse_36
    if db_target == "모든국가(BSE36개국제외)":
        return origin not in bse_36
    if db_target == "ASF발생73개국":
        return origin in asf_73
    if db_target == "EU":
        return origin == "EU" or origin in eu_members
    if "," in db_target:
        countries = {c.strip() for c in db_target.split(",")}
        return origin in countries
    return db_target == origin


def _match_keyword(
    db_keywords: Optional[list[str]],
    product_keywords: list[str],
) -> bool:
    """DB 키워드 배열과 사용자 키워드 배열의 교집합 존재 여부."""
    if db_keywords is None or len(db_keywords) == 0:
        return True
    if not product_keywords:
        return False
    return bool(set(db_keywords) & set(product_keywords))


# ──────────────────────────────────────────────
# 키워드 힌트 → DB 키워드 자동 보강
# ──────────────────────────────────────────────

def _enrich_keywords(product_keywords: list[str], origin_country: str) -> list[str]:
    """사용자 입력 키워드를 DB 키워드로 보강.

    f3_keyword_synonyms (38건) 기반:
      'pork', '햄', '소시지' → '돼지원료' 추가
      'sea salt', 'solar salt' → '천일염' 추가
      ...

    food_type 과 origin_country 연관 보강도 수행:
      PET 재질 기구 + 중국/대만/베트남/태국 → 'PET기구' 추가 (호출부에서)
    """
    enriched: set[str] = set(product_keywords)

    synonyms = load_keyword_synonyms()
    # hint → db_keyword 그룹핑
    hint_map: dict[str, list[tuple[str, Optional[str]]]] = {}
    for row in synonyms:
        hint = (row.get("hint_keyword") or "").lower()
        db_kw = row.get("db_keyword")
        country_cond = row.get("country_cond")
        if hint and db_kw:
            hint_map.setdefault(hint, []).append((db_kw, country_cond))

    for user_kw in product_keywords:
        ukl = user_kw.lower()
        for hint, targets in hint_map.items():
            if hint in ukl or ukl in hint:
                for db_kw, country_cond in targets:
                    if country_cond and country_cond != origin_country:
                        continue
                    enriched.add(db_kw)

    return list(enriched)


# ──────────────────────────────────────────────
# 결정 축 라벨링
# ──────────────────────────────────────────────

def _derive_decision_axis(doc: dict, info: ProductInfo) -> str:
    """이 서류가 왜 매칭됐는지 결정 차원을 라벨링."""
    has_food_type = bool(doc.get("food_type"))
    has_condition = bool(doc.get("condition"))
    has_country = bool(doc.get("target_country"))
    has_keyword = bool(doc.get("product_keywords"))

    # 공통: 모든 조건 null
    if not has_food_type and not has_condition and not has_country and not has_keyword:
        return "공통"

    # 협약체결국 수산물은 "식품유형+국가" (수산물 식품유형 × 협약국)
    if doc.get("condition") == "협약체결국수산물":
        return "식품유형+국가"

    # 조건만 있는 경우
    if has_condition and not has_country and not has_keyword:
        if doc.get("condition") in ("축산물또는동물성식품", "반추동물원료포함", "돼지원료포함"):
            return "식품유형"
        return "조건"

    # 식품유형만
    if has_food_type and not has_country and not has_keyword:
        return "식품유형"

    # 국가+키워드
    if has_country and has_keyword:
        return "원재료+국가"
    # 국가만
    if has_country and not has_keyword:
        return "국가"
    # 키워드만
    if has_keyword and not has_country:
        return "원재료"

    return "원재료"  # fallback


# ──────────────────────────────────────────────
# 매칭 근거 설명 (match_reason)
# ──────────────────────────────────────────────

def _build_match_reason(doc: dict, info: ProductInfo) -> str:
    """이 서류가 이 제품에 왜 필요한지 한 문장으로 요약."""
    # 공통
    if not doc.get("condition") and not doc.get("target_country") and not doc.get("product_keywords"):
        return "모든 수입식품에 공통으로 적용되는 서류입니다."

    clauses: list[str] = []
    cond = doc.get("condition")
    name = doc.get("doc_name") or ""

    if cond == "OEM":
        clauses.append("주문자상표부착(OEM) 수입식품에 해당")
    if cond == "동등성인정":
        clauses.append(
            f"{info.origin_country}산 유기인증 가공식품(한국과 유기가공식품 동등성인정 체결국)"
        )
    if cond == "축산물또는동물성식품":
        clauses.append(f"식품유형이 축산물/동물성 식품({info.food_type})")
    if cond == "GMO":
        clauses.append("GMO 표시대상 원료를 함유")
    if cond == "협약체결국수산물":
        clauses.append(
            f"수산물({info.food_type}) + 증명서 첨부 협약체결국({info.origin_country})"
        )

    is_asf = "ASF" in name
    is_bse = (
        "BSE" in name
        or doc.get("target_country") == "모든국가(BSE36개국제외)"
        or doc.get("target_country") == "BSE관련36개국"
    )
    if is_asf:
        clauses.append(
            f"ASF(아프리카돼지열병) 발생국인 {info.origin_country}에서 돼지 유래 원료를 사용"
        )
    elif is_bse:
        if doc.get("target_country") == "BSE관련36개국":
            clauses.append(
                f"BSE 발생 36개국({info.origin_country})에서 반추동물 유래 원료를 사용"
            )
        else:
            clauses.append("반추동물(소/양/사슴) 유래 원료를 함유")
    else:
        tc = doc.get("target_country")
        if tc and tc != "EU":
            clauses.append(f"제조국이 {info.origin_country}(해당 국가 특수 서류 대상)")
        elif tc == "EU":
            clauses.append(f"제조국이 EU 회원국({info.origin_country})")

    if doc.get("submission_timing") == "first" and info.is_first_import:
        clauses.append("**최초 수입 건**에 해당 (동일 제조사 재수입 시 생략 가능)")

    if doc.get("effective_from"):
        clauses.append(
            f"{doc['effective_from'].replace('-', '.')} 선적분부터 제출 의무"
        )
    if doc.get("effective_until"):
        clauses.append(
            f"{doc['effective_until'].replace('-', '.')} 전까지 보관(이후 제출로 전환)"
        )

    if doc.get("submission_type") == "keep":
        clauses.append("**제출 대신 보관** 대상 (식약처 요청 시 제시)")

    if "대마씨" in name or "THC" in name:
        clauses.append(
            "대마씨앗은 THC 5ppm·CBD 10ppm 이하, 대마씨유는 THC 10ppm·CBD 20ppm 이하 기준 적용"
        )

    return (". ".join(clauses) + ".") if clauses else ""


# ──────────────────────────────────────────────
# 스마트 경고 생성
# ──────────────────────────────────────────────

def _build_warnings(
    info: ProductInfo,
    enriched_kws: list[str],
    submit_docs: list[RequiredDoc],
    keep_docs: list[RequiredDoc],
) -> list[str]:
    """원본 입력 기반 스마트 경고. 이미 매칭된 서류의 주제는 제거."""
    warnings: list[str] = []
    kws_raw = set(info.product_keywords)
    origin = info.origin_country

    groups = load_country_groups()
    bse_36 = groups.get("BSE_36", set())
    asf_73 = groups.get("ASF_73", set())
    eu_members = groups.get("EU_27") or groups.get("EU_MEMBERS") or set()
    equivalence = groups.get("EQUIVALENCE", set())

    # 1. 일본산 + 도현 미지정
    if origin == "일본" and not any(
        t in info.food_type for t in ("기구", "용기", "포장")
    ):
        japan_prefectures = {
            "후쿠시마", "이바라키", "토치키", "군마", "사이타마", "치바",
            "미야기", "가나가와", "도쿄", "나가노", "야마가타", "니이가타", "시즈오카",
        }
        if not (set(info.product_keywords) & japan_prefectures):
            warnings.append(
                "일본산 식품입니다. 생산 도·현에 따라 방사성 물질 검사성적서가 "
                "추가로 필요할 수 있습니다. 13개 도·현(후쿠시마 등) 해당 여부를 확인하세요."
            )

    # 2. 축산물 식품유형 + 키워드 미명시
    if is_livestock_food_type(info.food_type) and "축산물또는동물성식품" not in kws_raw:
        warnings.append(
            f"식품유형({info.food_type})이 축산물/동물성 식품에 해당합니다. "
            "수출국 정부기관 발급 수출 위생증명서가 필요할 수 있습니다."
        )

    # 3. GMO 힌트
    gmo_hints = {
        "콩", "대두", "soy", "옥수수", "corn", "카놀라", "canola", "면실",
        "사탕무", "알팔파", "감자", "potato", "corn syrup", "hfcs",
        "high fructose corn syrup", "cornstarch", "corn starch", "corn oil",
        "corn flour", "dextrose", "maltodextrin", "maize", "soybean",
        "soy protein", "soy lecithin", "대두유", "대두분말", "콩기름",
    }
    found = [k for k in info.product_keywords if k.lower() in gmo_hints]
    if found and "GMO" not in kws_raw:
        warnings.append(
            f"GMO 표시대상 원료({', '.join(found)})가 포함되어 있습니다. "
            "GMO 관련 증명서류 해당 여부를 확인하세요."
        )

    # 4. 젤라틴 + BSE 36국
    if "젤라틴" in kws_raw and origin in bse_36:
        warnings.append(
            "BSE 관련 36개국에서 젤라틴 원료 수입 시, 원료 유래(우피/소뼈)에 따라 "
            "추가 정부증명서가 필요합니다. 유래 구분을 확인하세요."
        )

    # 5. ASF 돼지 힌트 — g6-6 미매칭 시만
    already_matched_asf = any(d.id == "g6-6" for d in submit_docs)
    if not already_matched_asf and origin in asf_73:
        pork_hints = {"돼지고기", "pork", "햄", "베이컨", "소시지", "족발", "삼겹살"}
        if any(
            any(h in k.lower() for h in pork_hints) for k in info.product_keywords
        ):
            warnings.append(
                f"ASF 발생국({origin})에서 돼지 유래 원료가 포함된 것으로 보입니다. "
                "돼지원료 해당 시 ASF 관련 서류가 필요합니다."
            )

    # 6. 유기 + 동등성인정 미체크
    organic_hints = {"유기", "유기농", "organic", "오가닉"}
    if (
        any(any(h in k.lower() for h in organic_hints) for k in info.product_keywords)
        and not info.has_organic_cert
    ):
        normalized = _normalize_country_for_equivalence(origin)
        if normalized in equivalence:
            warnings.append(
                "유기(Organic) 관련 원료가 포함된 것으로 보입니다. 유기인증 제품이면 "
                "NAQS 수입증명서(동등성인정)가 필요합니다. 유기인증 여부를 확인하세요."
            )

    # 7. 반추동물 힌트
    ruminant_hints = {"소고기", "쇠고기", "beef", "양고기", "lamb", "사슴고기", "venison"}
    if any(k.lower() in ruminant_hints for k in info.product_keywords) and not (
        kws_raw & {"반추동물", "소", "사슴", "양"}
    ):
        warnings.append(
            "반추동물(소/양/사슴) 유래 원료가 포함된 것으로 보입니다. "
            "BSE 관련 서류 해당 여부를 확인하세요."
        )

    # 8. 소금류 제품 힌트
    salt_food_types = ("소금", "천일염", "식염", "소금류", "조미소금")
    if any(st in info.food_type for st in salt_food_types):
        if not (kws_raw & {"죽염", "구운소금", "벌크천일염", "천일염"}):
            warnings.append(
                "소금류 제품입니다. 소금 종류(죽염/구운소금/천일염/벌크천일염)에 따라 "
                "추가 서류가 필요할 수 있습니다."
            )

    # 9. 뉴질랜드 + 꿀 힌트
    if origin == "뉴질랜드":
        honey_hints = {"honey", "벌꿀", "마누카", "manuka"}
        if (
            any(k.lower() in honey_hints for k in info.product_keywords)
            and not (kws_raw & {"꿀", "소밀"})
        ):
            warnings.append(
                "뉴질랜드산 꿀 제품은 수출국 정부증명서가 필요합니다. "
                "꿀 또는 소밀 해당 여부를 확인하세요."
            )

    # 10. 대마씨·Hemp 힌트
    hemp_hints = {"헴프", "hemp seed", "삼씨", "hempseed"}
    if (
        any(k.lower() in hemp_hints for k in info.product_keywords)
        and not (kws_raw & {"대마씨", "hemp", "Cannabis sativa"})
    ):
        warnings.append(
            "대마(Hemp) 관련 원료가 포함된 것으로 보입니다. "
            "THC/CBD 검사성적서 해당 여부를 확인하세요."
        )

    # 11. 양봉제품 → 농림축산검역본부 별도 확인
    apiary_hints = {
        "꿀", "honey", "마누카", "manuka", "로열젤리", "royal jelly",
        "프로폴리스", "propolis", "벌꿀", "비폴렌", "bee pollen",
    }
    if any(k.lower() in apiary_hints for k in info.product_keywords):
        warnings.append(
            "양봉제품(꿀·로열젤리·프로폴리스 등)은 수입식품 서류 외에 "
            "농림축산검역본부(054-912-1000) 동물검역 대상 여부를 별도로 확인해야 합니다."
        )

    # 이미 매칭된 서류의 경고는 제거
    all_doc_names = [d.doc_name for d in submit_docs + keep_docs]
    filtered: list[str] = []
    for w in warnings:
        if "ASF" in w and any("ASF" in n for n in all_doc_names):
            continue
        if "축산물" in w and any("위생증명서" in n for n in all_doc_names):
            continue
        if "반추동물" in w and any("BSE" in n for n in all_doc_names):
            continue
        filtered.append(w)
    return filtered


# ──────────────────────────────────────────────
# 메인 매칭 함수
# ──────────────────────────────────────────────

def match_required_docs(info: ProductInfo) -> RequiredDocsResponse:
    """5축 AND 매칭 후 통과 서류의 합집합을 반환.

    축:
      0. effective_from/until 날짜 필터
      1. food_type 매칭
      2. condition (OEM, GMO, 동등성인정, 축산물, 협약수산물, BSE, ASF, 정밀검사)
      3. target_country (국가 그룹 태그 해석)
      4. product_keywords (키워드 교집합)
      5. submission_timing (first 는 is_first_import=true 만)
    """
    rows = load_required_documents()
    if not rows:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "REQUIRED_DOCS_EMPTY",
                "message": "f3_required_documents 테이블이 비어 있습니다.",
                "feature": 3,
            },
        )

    # 키워드 보강
    enriched_kws = _enrich_keywords(info.product_keywords, info.origin_country)

    # PET4 보정 (중국/대만/베트남/태국 + PET 식품유형 → PET기구 키워드 추가)
    groups = load_country_groups()
    pet4 = groups.get("PET_4", set())
    if info.origin_country in pet4:
        pet_food_types = ("폴리에틸렌테레프탈레이트", "PET", "polyethylene terephthalate")
        if any(t in info.food_type or t == info.food_type for t in pet_food_types):
            if "PET기구" not in enriched_kws:
                enriched_kws.append("PET기구")

    enriched_info = info.model_copy(update={"product_keywords": enriched_kws})

    # 기준 일자
    today = info.reference_date or date.today().isoformat()

    submit_docs: list[RequiredDoc] = []
    keep_docs: list[RequiredDoc] = []

    equivalence = groups.get("EQUIVALENCE", set())
    ruminant_mid = RUMINANT_MID_CATEGORIES
    livestock_mid = LIVESTOCK_MID_CATEGORIES
    seafood_treaty = groups.get("SEAFOOD_TREATY", set())

    for doc in rows:
        # 축 0: 시행 일자 필터
        if doc.get("effective_from") and today < doc["effective_from"]:
            continue
        if doc.get("effective_until") and today >= doc["effective_until"]:
            continue

        # c2 특수 면제 (시행규칙 제27조 제1항 제1의2호 단서)
        # 외화획득용·OEM(자사제품제조용원료)·연구조사용은 수입식품 사진 제외.
        # NOTE: OEM 완제품까지 이 단서에 포함되는지 법령 해석 이슈 — 실무 확인 필요.
        if doc["id"] == "c2":
            is_exempt = (
                enriched_info.is_oem
                or "외화획득용" in enriched_kws
                or "외화획득용원료" in enriched_kws
                or "연구조사용" in enriched_kws
            )
            if is_exempt:
                continue

        # 축 1: food_type
        if doc.get("food_type") and doc["food_type"] != enriched_info.food_type:
            continue

        # 축 2: condition
        cond = doc.get("condition")
        if cond:
            if cond == "OEM" and not enriched_info.is_oem:
                continue
            if cond == "동등성인정":
                normalized = _normalize_country_for_equivalence(enriched_info.origin_country)
                if not (enriched_info.has_organic_cert and normalized in equivalence):
                    continue
            if cond == "정밀검사대상":
                is_seoryu_exempt = (
                    enriched_info.is_oem
                    or "외화획득용" in enriched_kws
                    or "외화획득용원료" in enriched_kws
                    or "연구조사용" in enriched_kws
                    or "정부수입" in enriched_kws
                    or "식용향료" in enriched_kws
                    or "박람회전시용" in enriched_kws
                    or "선천성대사이상질환자용" in enriched_kws
                    or "재가공기구용기포장" in enriched_kws
                    or "구매대행" in enriched_kws
                )
                is_precise = (
                    enriched_info.is_first_import
                    or "정밀검사대상" in enriched_kws
                    or "위해정보제기" in enriched_kws
                )
                if not is_precise or is_seoryu_exempt:
                    continue
            if cond == "외화획득용" and "외화획득용" not in enriched_kws:
                continue
            if cond == "외화획득용원료" and "외화획득용원료" not in enriched_kws:
                continue
            if cond == "돼지원료포함":
                is_pork_by_type = (
                    (enriched_info.category == "축산물" or is_livestock_food_type(enriched_info.food_type))
                    and is_pork_food_type(enriched_info.food_type)
                )
                is_pork_by_keyword = "돼지원료" in enriched_kws
                if not is_pork_by_type and not is_pork_by_keyword:
                    continue
            if cond == "반추동물원료포함":
                is_ruminant_by_mid = (enriched_info.food_mid_category or "") in ruminant_mid
                is_ruminant_by_type = (
                    not is_ruminant_by_mid
                    and (enriched_info.category == "축산물" or is_livestock_food_type(enriched_info.food_type))
                    and is_ruminant_food_type(enriched_info.food_type)
                )
                is_ruminant_by_keyword = bool(
                    set(enriched_kws) & {"반추동물", "소", "양", "사슴", "반추동물부산물"}
                )
                if not (is_ruminant_by_mid or is_ruminant_by_type or is_ruminant_by_keyword):
                    continue
            if cond == "협약체결국수산물":
                is_aquatic = enriched_info.category == "수산물"
                is_treaty_country = enriched_info.origin_country in seafood_treaty
                has_keyword = "협약체결국수산물" in enriched_kws
                if not (is_aquatic and is_treaty_country) and not has_keyword:
                    continue
            if cond == "축산물또는동물성식품":
                is_livestock = (
                    enriched_info.category == "축산물"
                    or (enriched_info.food_mid_category or "") in livestock_mid
                    or is_livestock_food_type(enriched_info.food_type)
                    or "축산물또는동물성식품" in enriched_kws
                )
                if not is_livestock:
                    continue
            if cond == "GMO" and "GMO" not in enriched_kws:
                continue

        # 축 3: target_country
        if not _match_country(doc.get("target_country"), enriched_info.origin_country):
            continue

        # 축 4: product_keywords
        if not _match_keyword(doc.get("product_keywords"), enriched_kws):
            continue

        # 축 5: submission_timing
        if doc.get("submission_timing") == "first" and not enriched_info.is_first_import:
            continue

        # 통과 → 이유·결정축 부착 후 수집
        required_doc = RequiredDoc(
            id=doc["id"],
            food_type=doc.get("food_type"),
            condition=doc.get("condition"),
            target_country=doc.get("target_country"),
            product_keywords=doc.get("product_keywords"),
            doc_name=doc["doc_name"],
            doc_description=doc.get("doc_description", ""),
            is_mandatory=doc.get("is_mandatory", True),
            submission_type=doc["submission_type"],
            submission_timing=doc["submission_timing"],
            law_source=doc.get("law_source", ""),
            effective_from=doc.get("effective_from"),
            effective_until=doc.get("effective_until"),
            match_reason=_build_match_reason(doc, enriched_info),
            decision_axis=_derive_decision_axis(doc, enriched_info),
        )

        if required_doc.submission_type == "keep":
            keep_docs.append(required_doc)
        else:
            submit_docs.append(required_doc)

    # 경고 생성
    warnings = _build_warnings(info, enriched_kws, submit_docs, keep_docs)

    # 입력 정보 충분도
    has_keywords = len(info.product_keywords) > 0
    has_country = bool(info.origin_country.strip())
    confidence = "high" if (has_keywords and has_country) else "needs_review"
    if not has_keywords:
        warnings.insert(
            0,
            "원재료 키워드가 입력되지 않았습니다. 특수 조건(젤라틴, 대마씨, 반추동물 원료 등) "
            "해당 여부를 확인할 수 없어 조건부 서류가 누락될 수 있습니다.",
        )

    return RequiredDocsResponse(
        food_type=info.food_type,
        origin_country=info.origin_country,
        is_first_import=info.is_first_import,
        submit_docs=submit_docs,
        keep_docs=keep_docs,
        total_submit=len(submit_docs),
        total_keep=len(keep_docs),
        warnings=warnings,
        match_confidence=confidence,
    )
