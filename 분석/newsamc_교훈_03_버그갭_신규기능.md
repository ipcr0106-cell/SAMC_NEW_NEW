# newsamc -> F1 버그/갭 + 신규 기능 후보

> 출처: C:\GITHUB\newsamc vs C:\GITHUB\SAMC_NEW_NEW 비교
> 분석일: 2026-04-16

---

## Part 1: 버그 (현재 F1에서 잘못 동작하는 것)

### BUG-1: 금지원료 부분매칭 누락 (심각도: 높음)

**위치**: `backend/services/step1_ingredients_check.py` L52-64

**현상**:
```python
names_set = set(names)  # {"마리화나 추출물"}
hits = [r for r in rows
        if r["name_ko"] in names_set           # "대마초" in {"마리화나 추출물"} → False
        or any(a in names_set for a in aliases)] # "마리화나" in {"마리화나 추출물"} → False
```

`in` 연산자는 set 멤버십(정확 일치)만 체크.
"마리화나 추출물"은 "마리화나"와 정확 일치하지 않으므로 **탈출**.

**newsamc 대응**: normalize + 양방향 substring
```typescript
const hit = candidates.some(c => ingNorm.includes(c) || c.includes(ingNorm));
```

**영향**: 별명이 포함된 이름의 금지원료가 게이트를 통과할 수 있음.
예: "THC 오일", "마리화나 추출물", "Kava kava extract" 등.

**수정 방향**:
```python
def _normalize(s: str) -> str:
    return re.sub(r'\s+', '', s).lower()

def _is_match(input_name: str, db_candidates: list[str]) -> bool:
    inp = _normalize(input_name)
    return any(
        inp in _normalize(c) or _normalize(c) in inp
        for c in db_candidates if c
    )
```

---

### BUG-2: 영문 alias 대소문자/공백 미처리 (심각도: 중간)

**위치**: 동일 함수

**현상**: aliases가 "Kava kava"이고 입력이 "KAVA KAVA EXTRACT"일 때,
현재 코드는 정확 일치만 하므로 대소문자가 다르면 매칭 실패.

**수정**: BUG-1의 normalize 함수로 동시 해결.

---

## Part 2: 갭 (newsamc에 있지만 F1에 없는 것)

### GAP-1: 테스트 인프라 전무 (영향도: 최고)

**현황**: `backend/tests/` 디렉토리에 `__init__.py`만 존재. pytest 파일 0개.

**newsamc 대비**: 36개 테스트 파일, 100+ 시나리오.

**영향**: 코드 수정 시 회귀 검증 불가. 금지원료 게이트 같은 핵심 보안 로직도 미검증.

---

### GAP-2: GMO 대상 식별 모듈 부재

**newsamc 구현**: `post-processing.ts`의 `identifyGmoTargets()`

```
GMO 고위험: 대두, 옥수수, 카놀라, 면실, 사탕무, 알팔파, 파파야
            → requires_documentation=true
GMO 중위험: 감자, 사과, 연어
            → requires_documentation=false
```

**현재 F1**: GMO 관련 로직 없음.

**필요성**: 수입식품에 GMO 고위험 원료 포함 시 "GMO 비의도적 혼입치 증명서" 필요.
현재 이 판단을 사람이 수동으로 해야 함.

**구현 난이도**: 낮음 (키워드 매칭, DB 불필요)

---

### GAP-3: 알레르겐 교차검사 모듈 부재

**newsamc 구현**: `post-processing.ts`의 `checkAllergens()`

원재료 목록 vs allergens DB 교차검사 → 미표시 법정 알레르겐 식별.
미표시 의무 알레르겐 발견 시:
- 에스컬레이션 생성
- "알레르겐 표시 보완 자료" 필수서류 추가

**현재 F1**: 알레르겐 관련 로직 없음.

**필요성**: 식품위생법상 알레르겐 표시 의무. 자동 교차검사로 누락 방지.

**구현 난이도**: 중간 (allergens 테이블 필요)

---

### GAP-4: 필수서류 자동 취합

**newsamc 구현**: `collectRequiredDocuments()`

조건별 필수서류 자동 결정:
- `health_functional_food` → 건강기능식품 수입신고서
- GMO 고위험 → GMO 비의도적 혼입치 증명서
- 미표시 알레르겐 → 알레르겐 표시 보완 자료

**현재 F1**: 없음. `Feature1Output`에 `law_refs`는 있지만 필수서류 목록은 없음.

---

### GAP-5: 특수 에스컬레이션 트리거

**newsamc**: 신뢰도와 무관하게 강제 에스컬레이션하는 3가지 특수 케이스:

| 트리거 | 의미 | 현재 F1 |
|---|---|---|
| `health_functional_suspect` | 건강기능식품으로 의심되는 일반식품 | 없음 |
| `dual_listed_ingredient` | 허용/금지 양쪽에 등재된 원료 | 없음 |
| `unknown_functional_ingredient` | 기능성 원료인데 DB에 없는 경우 | 없음 |

**영향**: 이 3가지는 신뢰도가 높아도 사람이 반드시 확인해야 하는 위험 케이스.
현재 F1은 신뢰도 기반 에스컬레이션만 있어 이런 케이스를 놓칠 수 있음.

---

### GAP-6: LLM 추천 + Sanitize 패턴 (unidentified 원료용)

**newsamc**: `recommend-ingredient.ts`

unidentified 원료에 대해:
1. trgm 유사 후보 풀 구성
2. LLM(GPT-4o)에 배치 추천 요청
3. **Sanitize**: 교차 오염 id 필터 + DB 정본 강제

**현재 F1**: unidentified 원료는 에스컬레이션만 생성, 추천 없음.

**구현 난이도**: 높음 (LLM 연동 + sanitize 로직)
**우선순위**: 낮음 (에스컬레이션으로 당장은 커버 가능)

---

## Part 3: 테스트 픽스처 (JSON)

### newsamc에서 사용하는 실제 제품 데이터

#### milk-thistle.json (밀크씨슬)
```json
{
  "productName": "Milk Thistle Extract 500mg",
  "jurisdiction": "health_functional_food",
  "ingredients": [
    {"name": "엉겅퀴추출물", "name_original": "Milk Thistle Extract (Silymarin 80%)", "percentage": 75},
    {"name": "결정셀룰로오스", "percentage": 15},
    {"name": "HPMC", "percentage": 5},
    {"name": "스테아린산마그네슘", "percentage": 3},
    {"name": "이산화규소", "percentage": 2}
  ]
}
```
→ health_functional_suspect 에스컬레이션 트리거 대상

#### kadayif (카다이프) — E2E 테스트용
- 식품유형: 과자(1-1)
- 실물 PDF 포함 (원재료배합비율표 + 제조공정도)
- 전체 파이프라인(OCR→판정) 통과 검증용

#### mixed-nuts (혼합견과) — HITL Phase 2
- 복합원재료 테스트 대상

---

## Part 4: 우선순위 정리

| 항목 | 유형 | 난이도 | 우선순위 |
|---|---|---|---|
| BUG-1: 부분매칭 누락 | 버그 수정 | 낮음 | **P0** |
| BUG-2: 대소문자/공백 | 버그 수정 | 낮음 | P0 (BUG-1과 동시) |
| GAP-1: 테스트 인프라 | 기반 | 중간 | **P1** |
| GAP-2: GMO 식별 | 신규 기능 | 낮음 | P2 |
| GAP-3: 알레르겐 교차검사 | 신규 기능 | 중간 | P2 |
| GAP-4: 필수서류 취합 | 신규 기능 | 낮음 | P2 (GAP-2,3 이후) |
| GAP-5: 특수 트리거 | 기능 보강 | 낮음 | P2 |
| GAP-6: LLM 추천 | 신규 기능 | 높음 | P3 |

---

## Part 5: 추가 교훈이 제한적인 영역

다음 영역은 newsamc에 있지만 F1에 **직접 적용하기 어렵거나 효용이 낮은** 것들:

| 영역 | 이유 |
|---|---|
| OCR normalize | F0(파싱) 단계 담당. F1은 파싱된 결과를 받음 |
| 언어 감지 (detectLanguage) | F0 영역 |
| 번역 (DeepL) | F0 영역 |
| ReviewContext 생성 | F0 영역 |
| M4-2 식품유형 분류 | 기능2(아람) 담당 |
| M4-3 일반 기준치 | F1 Step 3에 이미 구현됨 |
| M5-1/M5-2 표시/공정 검증 | 별도 기능 영역 |
| M6 라벨 생성/검증 | 별도 기능 영역 |
| Wizard validate-submission | 프론트엔드 영역 |
| Auth/Role/Session | 공통 인프라 |
