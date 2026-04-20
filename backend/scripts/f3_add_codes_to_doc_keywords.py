"""f3_required_documents.product_keywords에 f0_ingredient_codes의 성분코드 병기.

목적:
  OCR 언어 다양성(한/영/혼합)에도 강건하게 매칭하기 위해
  문서 키워드 배열에 원재료 키워드에 해당하는 성분코드를 추가로 삽입.

동작:
  - 원재료성 키워드만 매핑 (지역·규제·포장 카테고리는 스킵)
  - 정확매칭(name_ko/name_en = keyword) 우선, 없으면 ILIKE 부분매칭
  - 키워드당 코드 상한 20개 (너무 일반적인 키워드 폭주 방지)
  - 이미 배열에 있는 코드는 중복 추가 안 함 (멱등성)

사용:
  python scripts/f3_add_codes_to_doc_keywords.py --dry-run
  python scripts/f3_add_codes_to_doc_keywords.py --apply
  python scripts/f3_add_codes_to_doc_keywords.py --verify
"""
import os
import sys
import json
import argparse
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# ─────────────────────────────────────────────
# 환경 설정
# ─────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://bnfgbwwibnljynwgkgpt.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
if not SUPABASE_KEY:
    # fallback: read from backend/.env
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("SUPABASE_SERVICE_KEY="):
                    SUPABASE_KEY = line.split("=", 1)[1].strip()
                    break

assert SUPABASE_KEY, "SUPABASE_SERVICE_KEY 필요"

MAX_CODES_PER_KEYWORD = 20

# ─────────────────────────────────────────────
# 원재료 키워드 allowlist
#   f3_required_documents.product_keywords 에 실제 등장하는 값 중
#   성분코드 매칭 가능한 것만 추려냄.
# ─────────────────────────────────────────────
INGREDIENT_KEYWORDS = {
    # 축산물 유래
    "우지가공품", "우피젤라틴", "우피콜라겐",
    "소뼈젤라틴", "소뼈콜라겐",
    "젤라틴",
    # 수산물
    "복어", "쥐치포", "조미쥐치포", "남극크릴",
    # 꿀류
    "꿀", "소밀",
    # 소금류
    "천일염", "벌크천일염",
    "죽염", "구운소금", "태움·용융소금", "가공소금",
    # 콩/씨앗류
    "대두레시틴", "soy lecithin", "soybean lecithin",
    "대마씨", "hemp", "Cannabis sativa", "삼씨(껍질제거)",
    "아마씨",
    "파피씨드", "Poppy seed",
    # 식물 추출/허브
    "프로폴리스추출물",
    "석창포",
    "가는잎미선콩", "블루루핀",
    "다진마늘",
    # 기능성/건강기능
    "스피루리나", "코엔자임Q10", "EPA및DHA함유유지", "가르시니아캄보지아",
    "MSM", "엠에스엠",
    "유산균", "유산균배양분말",
    # 첨가물
    "제2인산칼슘",
}

# 스킵: 지역·규제·포장·제품유형 (성분코드 무관)
SKIP_KEYWORDS = {
    # 지역
    "일본34개도부현", "후쿠시마", "이바라키", "토치키", "군마",
    "사이타마", "치바", "미야기", "가나가와", "도쿄",
    "나가노", "야마가타", "니이가타", "시즈오카",
    # 규제·제품유형
    "축산물원료", "열처리가능",
    "PET기구", "PET용기",
    "선박벌크농산물",
    "학명정해진농임산물", "학명정해진수산물",
    "학명정해진농임산물(보관)",
    "조류", "미세조류", "생녹용",
    "LED완구캔디결합",
    "기능성표시일반식품", "기능성표시일반식품(보관)",
    "금속분쇄기분말제품",
    "혼합제제(가스형태)",
    "탈염해양심층수혼합음료",
}


def http_get(path: str) -> list:
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    req = Request(url, headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    })
    with urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def http_patch(path: str, body: dict) -> None:
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    req = Request(url, method="PATCH", data=json.dumps(body).encode("utf-8"), headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    })
    with urlopen(req, timeout=15) as r:
        r.read()


def search_codes_for_keyword(keyword: str) -> list[str]:
    """f0_ingredient_codes에서 keyword에 정확 매칭되는 코드 목록 반환.

    정확 매칭 전용 (ILIKE 미사용).
      - name_ko = keyword OR name_en = keyword (대소문자 무시)
      - ILIKE는 '꿀' → '꿀풀/합성꿀향' 같은 오매칭 위험으로 제외
    매칭 실패 시 빈 리스트 반환 (해당 doc은 기존 텍스트 키워드만 유지).
    """
    kw_encoded = quote(keyword, safe="")
    # 대소문자 구분 없이 정확 매칭: ilike 사용하되 와일드카드 없이
    q = f"f0_ingredient_codes?or=(name_ko.ilike.{kw_encoded},name_en.ilike.{kw_encoded})&select=code,name_ko,name_en&limit={MAX_CODES_PER_KEYWORD}"
    rows = http_get(q)
    return [r["code"] for r in rows] if rows else []


def build_keyword_to_codes_map() -> dict[str, list[str]]:
    """INGREDIENT_KEYWORDS의 각 키워드에 대해 매칭된 코드 dict."""
    result: dict[str, list[str]] = {}
    for kw in sorted(INGREDIENT_KEYWORDS):
        codes = search_codes_for_keyword(kw)
        result[kw] = codes
        status = "OK" if codes else "MISS"
        print(f"  [{status}] {kw!r:40} → {len(codes)} codes")
    return result


def load_all_docs() -> list[dict]:
    return http_get("f3_required_documents?select=id,doc_name,product_keywords&order=id")


def compute_updates(docs: list[dict], kw_to_codes: dict[str, list[str]]) -> list[dict]:
    """각 doc에 대해 기존 keywords + 매칭 코드를 합친 새 배열 계산.

    반환: [{"id", "doc_name", "old", "new", "added_codes"}]
    """
    updates = []
    for doc in docs:
        old = doc.get("product_keywords") or []
        if not old:
            continue
        new = list(old)
        added_codes: list[str] = []
        for kw in old:
            if kw in SKIP_KEYWORDS:
                continue
            codes = kw_to_codes.get(kw, [])
            for c in codes:
                if c not in new:
                    new.append(c)
                    added_codes.append(c)
        if added_codes:
            updates.append({
                "id": doc["id"],
                "doc_name": doc["doc_name"],
                "old": old,
                "new": new,
                "added_codes": added_codes,
            })
    return updates


def apply_updates(updates: list[dict]) -> None:
    for u in updates:
        doc_id = u["id"]
        new_keywords = u["new"]
        http_patch(
            f"f3_required_documents?id=eq.{quote(doc_id, safe='')}",
            {"product_keywords": new_keywords},
        )
        print(f"  [APPLIED] id={doc_id:10} +{len(u['added_codes'])} codes")


def verify_updates(updates: list[dict]) -> bool:
    """DB 재조회해서 의도한 대로 들어갔는지 확인."""
    all_ok = True
    for u in updates:
        doc_id = u["id"]
        rows = http_get(
            f"f3_required_documents?id=eq.{quote(doc_id, safe='')}&select=id,product_keywords"
        )
        if not rows:
            print(f"  [FAIL] id={doc_id}: not found")
            all_ok = False
            continue
        actual = rows[0].get("product_keywords") or []
        expected = u["new"]
        if set(actual) == set(expected):
            print(f"  [OK]   id={doc_id:10} verified ({len(actual)} keywords)")
        else:
            missing = set(expected) - set(actual)
            extra = set(actual) - set(expected)
            print(f"  [FAIL] id={doc_id}: missing={missing}, extra={extra}")
            all_ok = False
    return all_ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    if not (args.dry_run or args.apply or args.verify):
        ap.error("--dry-run, --apply, --verify 중 하나 필수")

    print("─" * 70)
    print("STEP 1: keyword → code 매핑 구축")
    print("─" * 70)
    kw_to_codes = build_keyword_to_codes_map()

    matched = sum(1 for v in kw_to_codes.values() if v)
    missed = sum(1 for v in kw_to_codes.values() if not v)
    print(f"\n총 {len(kw_to_codes)}개 키워드: 매칭 {matched}, 미매칭 {missed}")

    print("\n" + "─" * 70)
    print("STEP 2: 문서별 변경사항 계산")
    print("─" * 70)
    docs = load_all_docs()
    updates = compute_updates(docs, kw_to_codes)
    print(f"변경 대상 문서: {len(updates)}건")

    for u in updates:
        print(f"\n  id={u['id']} [{u['doc_name'][:40]}]")
        print(f"    old ({len(u['old'])}): {u['old']}")
        print(f"    +codes ({len(u['added_codes'])}): {u['added_codes'][:5]}{'...' if len(u['added_codes']) > 5 else ''}")

    if args.dry_run:
        print("\n[DRY-RUN] 변경 없이 종료")
        return

    if args.apply:
        print("\n" + "─" * 70)
        print("STEP 3: UPDATE 실행")
        print("─" * 70)
        apply_updates(updates)

        print("\n" + "─" * 70)
        print("STEP 4: 검증")
        print("─" * 70)
        ok = verify_updates(updates)
        print(f"\n검증 결과: {'ALL OK' if ok else 'FAILURES'}")
        sys.exit(0 if ok else 1)

    if args.verify:
        print("\n" + "─" * 70)
        print("STEP 3: 검증만 수행")
        print("─" * 70)
        ok = verify_updates(updates)
        print(f"\n검증 결과: {'ALL OK' if ok else 'FAILURES'}")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
