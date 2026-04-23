"""F3 일본 도·현 분기 테스트.

스펙: f3_작업/F3_F0_일본도현_전달스펙.md

3가지 케이스:
  1. 13 그룹 (후쿠시마)   → 검사성적서 doc 매칭 기대
  2. 34 그룹 (일본34개도부현) → 생산지증명 doc 매칭 기대
  3. 미선택               → 경고만 발생, prefecture-specific docs 없어야 함
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(env_path):
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# LLM 포섭 판정은 이 테스트와 무관하므로 비활성화 (속도 + 비용)
os.environ["F3_LLM_SUBSUMPTION"] = "0"

from models.f3_schemas import ProductInfo
from services.f3_required_docs import match_required_docs


# 실제 DB 확인된 문서 ID
DOC_13_PREFECTURE = "g6-3-sub"  # 13개 도·현 검사성적서 (hasattr check below)
DOC_34_PREFECTURE = "g6-3"       # 일본 34개 도·부·현 비오염 생산지 증명서


def find_doc_by_keyword(all_docs, keyword_substr: str):
    """doc_name에 특정 문자열 포함된 문서 찾기."""
    for d in all_docs:
        if keyword_substr in d.doc_name:
            return d
    return None


def run_scenario(title: str, info: ProductInfo, expect: dict) -> int:
    print("\n" + "=" * 70)
    print(f"시나리오: {title}")
    print(f"  product_keywords: {info.product_keywords}")
    print("=" * 70)

    result = match_required_docs(info)
    all_docs = result.submit_docs + result.keep_docs

    # 매칭된 문서 전체 출력
    print(f"\n매칭된 문서 ({len(all_docs)}건):")
    for d in all_docs:
        print(f"  - [{d.id}] {d.doc_name[:50]}")

    print(f"\n경고 ({len(result.warnings)}건):")
    for w in result.warnings:
        print(f"  ⚠ {w[:120]}")

    # 검증
    fail = 0
    doc_13 = find_doc_by_keyword(all_docs, "13개 도·현")
    doc_34 = find_doc_by_keyword(all_docs, "34개 도·부·현")

    if expect.get("doc_13") is True:
        if doc_13 is None:
            print("❌ FAIL — 13개 도·현 검사성적서 누락")
            fail += 1
        else:
            print(f"✅ 13개 도·현 문서 매칭됨: {doc_13.id}")
    elif expect.get("doc_13") is False:
        if doc_13 is not None:
            print(f"❌ FAIL — 13개 도·현 문서가 불필요하게 매칭됨: {doc_13.id}")
            fail += 1
        else:
            print("✅ 13개 도·현 문서 제외됨 (정상)")

    if expect.get("doc_34") is True:
        if doc_34 is None:
            print("❌ FAIL — 34개 도·부·현 생산지증명 누락")
            fail += 1
        else:
            print(f"✅ 34개 도·부·현 문서 매칭됨: {doc_34.id}")
    elif expect.get("doc_34") is False:
        if doc_34 is not None:
            print(f"❌ FAIL — 34개 도·부·현 문서가 불필요하게 매칭됨: {doc_34.id}")
            fail += 1
        else:
            print("✅ 34개 도·부·현 문서 제외됨 (정상)")

    if expect.get("warning_no_prefecture"):
        has_warning = any("도·현" in w or "생산 도" in w for w in result.warnings)
        if not has_warning:
            print("❌ FAIL — '도·현 확인' 경고 누락")
            fail += 1
        else:
            print("✅ 도·현 확인 경고 발생 (정상)")

    return 0 if fail == 0 else 1


def main():
    # 공통 재료: 일본산 가공식품
    base_ingredients = [
        {"code": "A1000774000001", "name_ko": "마늘가루", "ocr_name": "마늘가루"},
    ]

    results = []

    # Case 1: 후쿠시마 (13 그룹)
    results.append(run_scenario(
        "일본산 + 후쿠시마 (13 그룹)",
        ProductInfo(
            food_type="소스류",
            food_large_category="조미식품",
            food_mid_category="소스",
            origin_country="일본",
            product_keywords=["마늘가루", "A1000774000001", "후쿠시마"],
            product_ingredients=base_ingredients,
        ),
        expect={"doc_13": True, "doc_34": False},
    ))

    # Case 2: 일본34개도부현 리터럴 (34 그룹)
    results.append(run_scenario(
        "일본산 + '일본34개도부현' 리터럴 (34 그룹)",
        ProductInfo(
            food_type="소스류",
            food_large_category="조미식품",
            food_mid_category="소스",
            origin_country="일본",
            product_keywords=["마늘가루", "A1000774000001", "일본34개도부현"],
            product_ingredients=base_ingredients,
        ),
        expect={"doc_13": False, "doc_34": True},
    ))

    # Case 3: 도·현 미선택 (경고만)
    results.append(run_scenario(
        "일본산 + 도·현 미선택",
        ProductInfo(
            food_type="소스류",
            food_large_category="조미식품",
            food_mid_category="소스",
            origin_country="일본",
            product_keywords=["마늘가루", "A1000774000001"],
            product_ingredients=base_ingredients,
        ),
        expect={"doc_13": False, "doc_34": False, "warning_no_prefecture": True},
    ))

    # Case 4: 도쿄 (13 그룹, 도쿄도는 "도" 구분) — 엣지케이스
    results.append(run_scenario(
        "일본산 + 도쿄 (13 그룹, 도쿄도)",
        ProductInfo(
            food_type="소스류",
            food_large_category="조미식품",
            food_mid_category="소스",
            origin_country="일본",
            product_keywords=["마늘가루", "A1000774000001", "도쿄"],
            product_ingredients=base_ingredients,
        ),
        expect={"doc_13": True, "doc_34": False},
    ))

    passed = sum(1 for r in results if r == 0)
    print("\n" + "=" * 70)
    print(f"종합: {passed}/{len(results)} PASS")
    print("=" * 70)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
