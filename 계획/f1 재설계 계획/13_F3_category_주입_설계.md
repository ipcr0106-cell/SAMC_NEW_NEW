# 13. F3 category 필드 주입 설계

> 작성일: 2026-04-20
> 의존 문서: [F1F2_재설계_명세.md §3-3](./F1F2_재설계_명세.md), [07_데이터_모델_변경_설계.md](./07_데이터_모델_변경_설계.md)
> 산출물: `backend/routers/feature3.py` 수정
> **적용 시점: F1 재설계(P1~P7) 완료 후 별도 팀 승인 필요**

---

## 1. 목적

현재 `feature3.py`의 `_build_product_info_from_pipeline()`은 `ProductInfo.category`를 전달하지 않아 항상 `None`으로 설정된다. 이로 인해 `f3_required_docs.py`에서 `category` 직접 비교 조건이 발동하지 않아 수산물 케이스에서 `협약체결국수산물` 서류가 누락되는 버그가 존재한다.

본 문서는 F1 결과(또는 F2 결과)로부터 `category`(7대 구분)를 역추론하여 `ProductInfo`에 주입하는 로직을 설계한다.

---

## 2. 현황 분석

### 2-1. 현재 버그 위치

`backend/routers/feature3.py:84-93` — `ProductInfo()` 생성 시 `category` 미전달:

```python
return ProductInfo(
    food_type=food_type,
    food_large_category=f2.get("category_name"),
    food_mid_category=f2.get("subcategory_name"),
    origin_country=origin_country,
    ...
    # category 없음 → None
)
```

### 2-2. category가 None일 때 영향받는 조건 (`f3_required_docs.py`)

| 라인 | 조건 | category=None 영향 | 심각도 |
|------|------|-------------------|--------|
| 807 | `돼지원료포함` | `is_livestock_food_type()` fallback 있음 | 낮음 |
| 815-817 | `반추동물원료포함` | `is_ruminant_food_type()` fallback 있음 | 낮음 |
| **826** | **`협약체결국수산물`** | **`is_aquatic=False` → 서류 항상 누락** | **높음** |
| 831-833 | `축산물또는동물성식품` | `is_livestock_food_type()` fallback 있음 | 낮음 |

---

## 3. 세부 로직

### 3-1. 신규 헬퍼 `_infer_category()`

`feature3.py`에 추가:

```python
from models.f3_schemas import FoodCategory
from services.f3_required_docs import is_livestock_food_type

def _infer_category(
    food_large_category: str | None,
    food_type: str | None,
) -> FoodCategory | None:
    """F2 category_name + food_type으로 FoodCategory 7대 구분을 역추론."""
    # 1순위: F2 category_name이 FoodCategory Literal과 정확히 일치
    valid: set[str] = set(FoodCategory.__args__)  # type: ignore[attr-defined]
    if food_large_category and food_large_category in valid:
        return food_large_category  # type: ignore[return-value]

    # 2순위: food_type이 축산물 판정 가능
    if food_type and is_livestock_food_type(food_type):
        return "축산물"

    # 판단 불가
    return None
```

> 수산물은 `is_livestock_food_type()` 대응 함수가 없으므로 1순위(F2 category_name 매칭)에 의존한다.
> F2가 `category_name="수산물"`을 정확히 반환하는 경우에만 수산물 버그가 해소된다.

### 3-2. `_build_product_info_from_pipeline()` 수정

```python
return ProductInfo(
    food_type=food_type,
    food_large_category=f2.get("category_name"),
    food_mid_category=f2.get("subcategory_name"),
    origin_country=origin_country,
    is_oem=basic.get("is_oem", False),
    is_first_import=basic.get("is_first_import", False),
    has_organic_cert=basic.get("is_organic", False),
    product_keywords=product_keywords,
    category=_infer_category(          # 🆕 추가
        f2.get("category_name"),
        food_type,
    ),
)
```

---

## 4. 에지 케이스

| 케이스 | 동작 |
|--------|------|
| F2 `category_name=None` + food_type이 축산물 | `"축산물"` 반환 |
| F2 `category_name="수산물"` | `"수산물"` 반환 → `협약체결국수산물` 버그 해소 |
| F2 `category_name`이 FoodCategory 외 문자열 (예: `"기타"`) | `None` 반환 (축산물 fallback 시도) |
| F2 결과 없음 (`f2={}`) | `None` 반환, 기존 동작 유지 |
| `food_type`이 PET/포장재 등 비식품 | `is_livestock_food_type()` False → `None` 반환 |

---

## 5. 테스트 포인트

- [ ] `_infer_category("수산물", "연어")` → `"수산물"`
- [ ] `_infer_category(None, "프레스햄")` → `"축산물"` (is_livestock_food_type 커버)
- [ ] `_infer_category("기타", "과자류")` → `None`
- [ ] `_infer_category(None, None)` → `None`
- [ ] 수산물 케이스 E2E: F3 run → `협약체결국수산물` 서류 포함 확인
- [ ] 기존 케이스 회귀 없음: 축산물·일반가공식품 결과 변동 없음

---

## 6. 변경 파일 요약

| 파일 | 변경 종류 | 내용 |
|------|-----------|------|
| `backend/routers/feature3.py` | 🆕 함수 추가 | `_infer_category()` |
| `backend/routers/feature3.py` | 🔄 수정 | `_build_product_info_from_pipeline()` — `category` 주입 |
| `backend/routers/feature3.py` | 🔄 import 추가 | `FoodCategory`, `is_livestock_food_type` |

---

## 7. 남은 결정사항

- 🟡 수산물 `is_aquatic_food_type()` 함수 신규 추가 여부 — F2 `category_name` 의존 제거용 (옵션)
- 🟡 적용 시점 — F1 재설계 P7(레거시 제거) 완료 후 vs P3(HITL UI) 이후 독립 PR
- 🟡 팀 리뷰 담당자 확정
