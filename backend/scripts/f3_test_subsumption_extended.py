"""F3 LLM 포섭 판정 확장 테스트.

4가지 광의↔협의 케이스 (각 문서의 product_keywords 가 수동 매핑 불가한 형태):

  Case 1 (유산균배양분말): 명백한 포섭
    - doc k2 ['유산균','유산균배양분말']
    - F0: Lactobacillus acidophilus분말 (A5000047000001)
    - 기대: subsumed=true, high

  Case 2 (조미쥐치포): 명백한 비포섭
    - doc g6-4c ['쥐치포','조미쥐치포']
    - F0: 쥐치 (원어, A3000669000000) — 가공 이전 상태
    - 기대: subsumed=false (쥐치포≠쥐치)

  Case 3 (소뼈젤라틴 BSE): 가공 부위 차이
    - doc g5-3 ['소뼈젤라틴','소뼈콜라겐']
    - F0: 젤라틴 (B2000051000000, name_en=GELATIN(BEEF CARTILAGE))
    - 연골(cartilage) vs 뼈(bone) 차이. LLM 판단.

  Case 4 (우피젤라틴 BSE): 가수분해 콜라겐 형태
    - doc g5-2 ['우피젤라틴','우피콜라겐']
    - F0: 가수분해콜라겐(소) (A6001455000200)
    - 우피(hide) 명시 없음. 소 유래는 맞음. LLM 판단.
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


def run_case(title: str, info: ProductInfo, doc_id: str, expect_match: bool, note: str = "") -> int:
    print("\n" + "=" * 70)
    print(f"[{doc_id}] {title}")
    if note:
        print(f"  {note}")
    print(f"  country={info.origin_country}, food_type={info.food_type}")
    print(f"  ingredients={info.product_ingredients}")
    print("=" * 70)

    result = match_required_docs(info)
    all_docs = result.submit_docs + result.keep_docs
    target = next((d for d in all_docs if d.id == doc_id), None)

    if expect_match:
        if target is None:
            print(f"❌ FAIL — {doc_id} 미매칭 (기대: 매칭)")
            return 1
        print(f"✅ {doc_id} 매칭")
    else:
        if target is not None:
            print(f"❌ FAIL — {doc_id} 매칭됨 (기대: 제외)")
            if target.subsumption:
                print(f"   잘못된 reasoning: {(target.subsumption.get('reasoning') or '')[:200]}")
            return 1
        print(f"✅ {doc_id} 제외")
        return 0

    if target.subsumption:
        s = target.subsumption
        print(f"\n  subsumed: {s.get('subsumed')}")
        print(f"  confidence: {s.get('confidence')}")
        print(f"  source: {s.get('source')}")
        print(f"  matched_ingredient: {s.get('matched_ingredient')}")
        print(f"  matched_code: {s.get('matched_code')}")
        print(f"  reasoning: {(s.get('reasoning') or '')[:300]}")
    else:
        print("  (직접 매칭으로 통과 — LLM 호출 안 됨)")
    return 0


def main():
    results = []

    # ── Case 1: 유산균배양분말 ← Lactobacillus acidophilus분말 ──────────
    results.append(run_case(
        "유산균배양분말 ← Lactobacillus acidophilus분말",
        ProductInfo(
            food_type="건강기능식품",
            food_large_category="건강기능식품",
            food_mid_category=None,
            origin_country="미국",
            product_keywords=["Lactobacillus acidophilus분말", "A5000047000001"],
            product_ingredients=[{
                "code": "A5000047000001",
                "name_ko": "Lactobacillus acidophilus분말",
                "ocr_name": "유산균 분말",
            }],
        ),
        doc_id="k2",
        expect_match=True,
        note="유산균 + 분말 → 유산균배양분말 카테고리 포섭 기대",
    ))

    # ── Case 2: 조미쥐치포 ← 쥐치 (원어) (NEGATIVE) ─────────────────────
    results.append(run_case(
        "조미쥐치포 ← 쥐치(원어, 가공 전)",
        ProductInfo(
            food_type="수산물가공품",
            food_large_category="수산물",
            food_mid_category=None,
            origin_country="베트남",
            product_keywords=["쥐치", "A3000669000000"],
            product_ingredients=[{
                "code": "A3000669000000",
                "name_ko": "쥐치",
                "ocr_name": "쥐치",
            }],
        ),
        doc_id="g6-4c",
        expect_match=False,
        note="쥐치포(건조·조미 가공품) vs 쥐치(원어) — 가공 상태 다름. LLM이 거부해야 정상",
    ))

    # ── Case 3: 소뼈젤라틴 ← 젤라틴(BEEF CARTILAGE) ─────────────────────
    # 주의: g5-3는 food_type=null, target_country=BSE관련36개국
    # 영국은 BSE 36국에 포함
    results.append(run_case(
        "소뼈젤라틴 ← 젤라틴(BEEF CARTILAGE)",
        ProductInfo(
            food_type="식육가공품",
            food_large_category="식육가공품",
            food_mid_category=None,
            origin_country="영국",
            product_keywords=["젤라틴", "B2000051000000"],
            product_ingredients=[{
                "code": "B2000051000000",
                "name_ko": "젤라틴",
                "ocr_name": "gelatin",
            }],
        ),
        doc_id="g5-3",
        expect_match=True,  # BSE 리스크상 소 유래면 포섭 기대
        note="연골(cartilage)과 뼈(bone) 차이 있으나 동일 소 유래. BSE 규제 관점 판단",
    ))

    # ── Case 4: 우피콜라겐 ← 가수분해콜라겐(소) (NEGATIVE: LLM 보수적 거부) ──
    # 법령 원문이 "우피(소가죽) 유래" 로 명시 한정 → 일반 "소" 유래는 거부해야 정상
    results.append(run_case(
        "우피콜라겐 ← 가수분해콜라겐(소) [보수적 거부 기대]",
        ProductInfo(
            food_type="건강기능식품",
            food_large_category="건강기능식품",
            food_mid_category=None,
            origin_country="영국",
            product_keywords=["가수분해콜라겐(소)", "A6001455000200"],
            product_ingredients=[{
                "code": "A6001455000200",
                "name_ko": "가수분해콜라겐(소)",
                "ocr_name": "hydrolyzed collagen",
            }],
        ),
        doc_id="g5-2",
        expect_match=False,
        note="법령이 '우피(소가죽)' 한정 → 일반 '소' 유래만으론 포섭 안 되어야 정상",
    ))

    passed = sum(1 for r in results if r == 0)
    print("\n" + "=" * 70)
    print(f"종합: {passed}/{len(results)} PASS")
    print("=" * 70)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
