"""F3 LLM 포섭 판정 통합 테스트.

3가지 케이스:
  1. Positive — 중국산 '간마늘' (공식명) → g6-4e 매칭 기대 (LLM 포섭)
  2. Negative — 중국산 '통마늘' → g6-4e 제외 기대 (LLM 거부)
  3. Direct  — '다진마늘' 텍스트 직접 입력 → LLM 없이 매칭

실행: python scripts/f3_test_subsumption.py
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

from models.f3_schemas import ProductInfo
from services.f3_required_docs import match_required_docs


def run_scenario(title: str, info: ProductInfo, expect_g64e: bool) -> int:
    print("\n" + "=" * 70)
    print(f"시나리오: {title}")
    print(f"기대: g6-4e {'매칭 성공' if expect_g64e else '매칭 실패'}")
    print("=" * 70)
    print(f"  product_ingredients: {info.product_ingredients}")

    result = match_required_docs(info)
    all_docs = result.submit_docs + result.keep_docs
    g64e = next((d for d in all_docs if d.id == "g6-4e"), None)

    if expect_g64e:
        if g64e is None:
            print("❌ FAIL — g6-4e 가 결과에 없음")
            return 1
        print("✅ PASS — g6-4e 매칭됨")
        if g64e.subsumption:
            s = g64e.subsumption
            print(f"  subsumed: {s.get('subsumed')}, confidence: {s.get('confidence')}, source: {s.get('source')}")
            print(f"  matched: {s.get('matched_ingredient')} / {s.get('matched_code')}")
            print(f"  reasoning: {(s.get('reasoning') or '')[:200]}")
        else:
            print("  (직접 키워드 매칭으로 통과 — LLM 호출 안 됨)")
    else:
        if g64e is not None:
            print("❌ FAIL — g6-4e 가 매칭됨 (기대: 제외)")
            if g64e.subsumption:
                print(f"  잘못된 포섭 판정: {(g64e.subsumption.get('reasoning') or '')[:200]}")
            return 1
        print("✅ PASS — g6-4e 제외됨 (정상)")
    return 0


def main():
    results = []

    # Case 1 (Positive): 중국산 간마늘 → g6-4e 매칭 기대
    results.append(run_scenario(
        "중국산 '간마늘' (다진마늘 계열)",
        ProductInfo(
            food_type="절임식품",
            food_large_category="조미식품",
            food_mid_category="절임류",
            origin_country="중국",
            product_keywords=["간마늘", "A1000774002300"],
            product_ingredients=[
                {"code": "A1000774002300", "name_ko": "간마늘", "ocr_name": "간 마늘"},
            ],
        ),
        expect_g64e=True,
    ))

    # Case 2 (Negative): 중국산 통마늘 → g6-4e 제외 기대
    results.append(run_scenario(
        "중국산 '통마늘' (다진마늘 아님)",
        ProductInfo(
            food_type="절임식품",
            food_large_category="조미식품",
            food_mid_category="절임류",
            origin_country="중국",
            product_keywords=["마늘", "A1000774000000"],
            product_ingredients=[
                {"code": "A1000774000000", "name_ko": "마늘", "ocr_name": "통마늘"},
            ],
        ),
        expect_g64e=False,
    ))

    # Case 3 (Direct match): "다진마늘" 텍스트 직접 매칭 → LLM 호출 불필요
    results.append(run_scenario(
        "'다진마늘' 텍스트 직접 매칭 (LLM 불필요)",
        ProductInfo(
            food_type="절임식품",
            food_large_category="조미식품",
            food_mid_category="절임류",
            origin_country="중국",
            product_keywords=["다진마늘"],
            product_ingredients=[
                {"code": "", "name_ko": "", "ocr_name": "다진마늘"},
            ],
        ),
        expect_g64e=True,
    ))

    passed = sum(1 for r in results if r == 0)
    print("\n" + "=" * 70)
    print(f"종합: {passed}/{len(results)} PASS")
    print("=" * 70)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
