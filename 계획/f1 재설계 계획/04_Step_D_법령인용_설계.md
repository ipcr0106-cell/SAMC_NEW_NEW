# 04. Step D — 법령 인용 설계 (RAG 역할 축소)

> 의존: 기존 Pinecone 인프라
> 산출물: `backend/services/f1_step_d.py` (기존 `f1_rag_judge.py` 재구성)

---

## 1. 목적

판정 근거 법령을 담당자에게 **표시 전용**으로 제공. 기존 RAG 판정 주도 역할 완전 제거.

---

## 2. 설계 철학 변경

### 기존 (문제)
- RAG가 `verdict` 생성에 관여 → 환각·오판 리스크
- LLM이 법령을 해석하여 "이 제품은 수입 가능/불가" 판단

### 신규 (재설계)
- RAG는 **검색기만** — 관련 법령 청크 N개 반환
- **판정 주도는 Step A/B/C의 결정론적 로직** + HITL-2 담당자 최종 확정
- LLM 해석 금지, 원문 인용만

---

## 3. 입출력 계약

```python
async def run_step_d(
    query_context: QueryContext,
    top_k: int = 5,
) -> StepDResult:
    """Pinecone 법령 청크 검색. 판정 생성 없음."""


@dataclass
class QueryContext:
    food_type: Optional[str]
    forbidden_hits: list[ForbiddenHit]
    restricted_ingredients: list[str]
    failed_standards: list[str]            # Step C fail 항목


@dataclass
class StepDResult:
    citations: list[LawCitation]


@dataclass
class LawCitation:
    chunk_id: str
    law_name: str           # "식품위생법", "수입식품안전관리 특별법" 등
    article_no: Optional[str]   # "제27조"
    text: str               # 원문 인용 (편집 금지)
    score: float            # Pinecone similarity
    namespace: str          # 출처 namespace (additive_code_text, food_code_text 등)
```

---

## 4. 검색 쿼리 구성

```python
def build_query(ctx: QueryContext) -> str:
    parts = []
    if ctx.food_type:
        parts.append(f"식품유형 {ctx.food_type}")
    if ctx.forbidden_hits:
        parts.append("수입 금지 원료: " + ", ".join(h.ingredient_name for h in ctx.forbidden_hits))
    if ctx.restricted_ingredients:
        parts.append("사용 제한 원료: " + ", ".join(ctx.restricted_ingredients))
    if ctx.failed_standards:
        parts.append("기준규격 초과: " + ", ".join(ctx.failed_standards))
    return " / ".join(parts) or "수입식품 일반"
```

---

## 5. 사용할 Pinecone 네임스페이스

| 네임스페이스 | 용도 | 실측 건수 (2026-04-18) | 유지 |
|-------------|------|-----------------------:|------|
| `additive_code_text` | 식품첨가물공전 | 1664 | ✅ |
| `food_code_text` | 식품공전 | 140 | ✅ |
| `health_food_text` | 건강기능식품공전 | 252 | ✅ |
| `temporary_standard` | 한시적 기준·규격 | 74 | ✅ |
| `functional_labeling` | 기능성표시 고시 (본문 11 + 별표1 6 + 별표2 1) | 18 | ✅ |

검색은 **5개 namespace 병렬 후 merge**. `top_k=5`씩 조회 → 총 25건 → 점수 상위 5건 반환.

**`functional_labeling` 처리 (14번 §11-3 결정 10, A')**: 쿼리 경로는 유지하되 `backend/routers/admin_law_update.py`의 `_F1_LAW_NAME_TO_NAMESPACE` 매핑에 기능성표시 법령명을 추가하여 향후 재인덱싱 경로까지 확보한다. 현재 Pinecone 18건은 2026-04-17 newsamc로부터 정식 복제된 실데이터이며 건강기능식품 심사 컨텍스트 제공에 유효.

---

## 6. 화면 표시 규칙

프론트 `LawCitationList` 컴포넌트에서:

- 법령명 · 조 번호 · 원문 텍스트 그대로 노출
- 검색 점수 하단에 작게 표시 (기술적 debugging 용)
- 담당자가 체크박스로 "판정 근거로 채택할 것"을 선택 → HITL-2 최종 결과에 포함
- 자동 verdict 연동 **금지** (체크박스와 verdict 분리)

---

## 7. RAG 판정 주도 기능 제거 목록

다음 기능은 **전면 삭제**:

| 대상 | 조치 |
|------|------|
| `f1_rag_judge.run_feature1_with_rag` | 로직 축소 (검색만 수행) |
| RAG-DB 상충 판정 로직 (`conflict_status`) | **삭제** (판정 주도 안 함) |
| `rag_verdict`, `rag_reasoning` 필드 | 유지 (참조용 표시만) |
| `RagConflictPanel` UI | **삭제** (판정 주도 아닌 단순 인용은 충돌 개념 불필요) |

---

## 8. 에지 케이스

| 케이스 | 처리 |
|--------|------|
| Pinecone 장애 | `citations=[]` + 경고 배너 ("법령 인용 조회 실패") — 판정은 진행 |
| 검색 결과 0건 | `citations=[]` — Step A/B/C 결정론적 결과로 충분 |
| 쿼리 컨텍스트 비어있음 (정상 케이스) | "수입식품 일반" 쿼리로 기본 법령 5건 인용 |

---

## 9. 테스트 포인트

- [ ] Step A forbidden_hits 존재 → 해당 금지원료 관련 법령 우선 반환
- [ ] Step C fail → 해당 기준규격 조항 인용
- [ ] Pinecone mock 장애 → `citations=[]`, 파이프라인 진행 계속
- [ ] RAG 결과가 verdict 변경을 유발하지 않음 (단위 테스트로 검증)

---

## 10. 남은 결정사항

- 🟡 기존 `rag_verdict`, `rag_reasoning` 필드 유지 vs 삭제 (유지 시 프론트에서 "AI 참고 의견"으로 명시)
- 🟡 `RagConflictPanel` 컴포넌트 제거 후 대안 UI (없어도 충분?)
- 🟡 Pinecone top_k=5 충분한지, 너무 많이 나오지는 않는지 (담당자 UX)
