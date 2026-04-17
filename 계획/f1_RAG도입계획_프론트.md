# F1 RAG 도입 계획 — 프론트엔드

> 총괄 문서: [f1_RAG도입계획_총괄.md](f1_RAG도입계획_총괄.md)
> 개정 (2026-04-17): critic 검토 반영 — 기존 `Feature1Response` 인터페이스 보존 + `Feature1Internal` 확장 방식

## 0. 핵심 원칙

기존 [frontend/features/feature1/types.ts:11-18](../frontend/features/feature1/types.ts) `Feature1Response` 구조는 **그대로 유지**. RAG 필드는 `Feature1Internal`에 통합한다.

```typescript
// 기존 (변경 없음):
export interface Feature1Response {
  case_id: string;
  status: "pending" | "running" | "waiting_review" | "completed" | "error";  // ← "needs_review" 추가
  ai_result: (Feature1Result & { _internal?: Feature1Internal }) | null;
  final_result: (Feature1Result & { _internal?: Feature1Internal }) | null;
  edit_reason?: string | null;
  updated_at?: string | null;
}
```

→ 백엔드 응답 구조 변경 최소. 신규 RAG 필드는 모두 `_internal` 안.

## 1. 변경 범위

| 영역 | 변경 |
|---|---|
| `Feature1Response.status` Union | `"needs_review"` 추가 |
| `Feature1Internal` | RAG 필드 추가 (rag_verdict, rag_reasoning, law_citations, conflict_status) |
| 신규 타입 | `LawCitation`, `RagVerdict`, `ConflictStatus` |
| 결과 화면 | 인용 섹션 + 충돌 결정 패널 (`needs_review` 상태일 때만) |
| 인용 카드 컴포넌트 | 신규 |
| 충돌 결정 패널 | 신규 |
| 페이지 라우트 | 변경 없음 (`/cases/[id]/f1`) |

## 2. 수정 파일

| 파일 | 변경 |
|---|---|
| `frontend/features/feature1/types.ts` | `Feature1Internal`에 RAG 필드 추가, `status` Union에 `needs_review` 추가, `LawCitation` 등 신규 타입 |
| `frontend/features/feature1/api/importCheck.ts` | (호환 — 변경 최소) |
| `frontend/features/feature1/ImportCheckPage.tsx` | 인용 섹션 + 충돌 결정 패널 통합 |
| `frontend/features/feature1/components/LawCitationCard.tsx` (신규) | 단일 인용 카드 |
| `frontend/features/feature1/components/LawCitationList.tsx` (신규) | 인용 카드 목록 + 빈 상태 |
| `frontend/features/feature1/components/RagConflictPanel.tsx` (신규) | exact vs RAG 양쪽 결과 + 결정 버튼 |

## 3. 타입 정의

`frontend/features/feature1/types.ts`에 추가/수정:

```typescript
import type { Feature1Result } from "@/types/pipeline";

// ─────── 기존 (수정만) ───────
export interface Feature1Response {
  case_id: string;
  // "needs_review" 추가
  status: "pending" | "running" | "waiting_review" | "needs_review" | "completed" | "error";
  ai_result: (Feature1Result & { _internal?: Feature1Internal }) | null;
  final_result: (Feature1Result & { _internal?: Feature1Internal }) | null;
  edit_reason?: string | null;
  updated_at?: string | null;
}

// ─────── 기존 Feature1Internal에 필드 추가 ───────
export interface Feature1Internal {
  // 기존 필드 (변경 없음)
  aggregation: { /* ... */ } | null;
  conditional_evaluations: ConditionalEvaluationDetail[];
  forbidden_hits: ForbiddenHitDetail[];
  escalations: EscalationDetail[];
  law_refs: { law_source: string; law_article?: string | null }[];
  // ─── 신규 RAG 필드 ───
  rag_verdict?: RagVerdict | null;
  rag_reasoning?: string | null;
  law_citations?: LawCitation[];
  conflict_status?: ConflictStatus;
}

// ─────── 신규 타입 ───────
export type RagVerdict =
  | "permitted"
  | "restricted"
  | "prohibited"
  | "unidentified"
  | "error";

export type ConflictStatus =
  | "agreed"            // exact == rag → 자동 통과
  | "conflict"          // exact != rag → needs_review
  | "rag_supplemented"  // exact=unidentified, rag가 채움 → needs_review
  | "rag_unavailable"   // RAG 호출 실패 → degraded mode
  | "rag_skipped";      // 금지원료 적중으로 RAG 미호출

export type CitationNamespace =
  | "food_code_text"
  | "additive_code_text"
  | "functional_labeling"
  | "temporary_standard"
  | "health_food_text";

export interface LawCitation {
  chunk_id: string;
  namespace: CitationNamespace;
  regulation_id: string | null;
  section_path: string | null;
  text: string;
  score: number;
}
```

## 4. 컴포넌트 설계

### 4.1 `LawCitationCard.tsx`

| Prop | 타입 | 설명 |
|---|---|---|
| `citation` | `LawCitation` | 단일 인용 |
| `defaultExpanded?` | `boolean` | 초기 펼침 여부 (기본 false) |

**렌더링**:
- 헤더: `NAMESPACE_LABEL[namespace]` + `section_path`
- 본문: `text` (4줄 클램프, "더 보기" 토글)
- 메타: score (소수 2자리), regulation_id 칩

### 4.2 `LawCitationList.tsx`

```typescript
interface Props {
  citations: LawCitation[];
}

export function LawCitationList({ citations }: Props) {
  if (!citations || citations.length === 0) {
    return (
      <div className="text-sm text-slate-500">
        판정 근거가 된 법령 인용이 없습니다.
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <h3 className="text-base font-semibold">법령 인용 ({citations.length})</h3>
      {citations.map((c) => (
        <LawCitationCard key={c.chunk_id} citation={c} />
      ))}
    </div>
  );
}
```

### 4.3 `RagConflictPanel.tsx` (신규)

`status === "needs_review"`일 때만 렌더링.

| Prop | 타입 | 설명 |
|---|---|---|
| `caseId` | `string` | 케이스 ID (PATCH 호출용) |
| `aiResult` | `Feature1Result & {_internal: Feature1Internal}` | 전체 AI 결과 |
| `onResolved` | `() => void` | 결정 후 콜백 (재조회 트리거) |

**렌더링 영역**:
1. **충돌 사유 배너** — `conflict_status` 한국어 라벨
2. **2열 비교 테이블**:
   - 좌: 정확매칭 (`verdict`, `import_possible`, `aggregation` 요약)
   - 우: RAG (`rag_verdict`, `rag_reasoning`)
3. **법령 인용 영역** (`LawCitationList`)
4. **결정 버튼**: "정확매칭 채택" / "RAG 채택" / "수동 수정"
5. **사유 입력** (`edit_reason`)
6. **저장 버튼** → `PATCH /api/v1/cases/{caseId}/pipeline/feature/1` 호출

```typescript
// 의사코드
async function handleAccept(side: "exact" | "rag") {
  const finalResult = side === "exact"
    ? aiResult  // 그대로
    : { ...aiResult, verdict: aiResult._internal?.rag_verdict, ... };  // RAG로 덮어쓰기
  await api.patch(`/cases/${caseId}/pipeline/feature/1`, {
    final_result: finalResult,
    edit_reason: `HITL: ${side === "exact" ? "정확매칭" : "RAG"} 채택`,
  });
  onResolved();
}
```

### 4.4 namespace 한국어 라벨

```typescript
export const NAMESPACE_LABEL: Record<CitationNamespace, string> = {
  food_code_text: "식품공전",
  additive_code_text: "식품첨가물공전",
  functional_labeling: "건강기능 표시기준",
  temporary_standard: "한시적 기준",
  health_food_text: "건강기능식품공전",
};

export const CONFLICT_LABEL: Record<ConflictStatus, string> = {
  agreed: "정확매칭과 RAG 결과 일치",
  conflict: "정확매칭과 RAG 결과 불일치 — 사람 결정 필요",
  rag_supplemented: "정확매칭 미등록 → RAG가 보강 — 사람 확인 권장",
  rag_unavailable: "RAG 호출 실패 — 정확매칭 결과만 사용",
  rag_skipped: "금지원료 적중 — RAG 호출 생략",
};
```

## 5. ImportCheckPage 통합 위치

```
[제품 정보 영역]
[정확 매칭 결과 영역] (기존)
[판정 카드] (기존, verdict + import_possible)

{status === "needs_review" && <RagConflictPanel />}  ← 신규, 조건부

[법령 인용 영역 — LawCitationList citations={ai_result._internal.law_citations} ]  ← 신규, 항상 (빈 상태 처리)

[기존 액션: 수정 / 확인 버튼 (기존 유지)]
```

## 6. 빈 상태 / 에러 상태

| 상태 | UI |
|---|---|
| `law_citations` 비어있음 | "법령 인용 없음" 메시지 |
| `conflict_status === "rag_unavailable"` | 알림 배너: "RAG 일시 장애 — 정확매칭만 표시" |
| `conflict_status === "rag_skipped"` | 정보 배너: "금지원료 적중으로 RAG 생략" (인용 영역 숨김) |
| `rag_verdict === "error"` | RagConflictPanel 미표시, 위 배너로 대체 |

## 7. 테스트

| 항목 | 도구 |
|---|---|
| 컴포넌트 단위 (`LawCitationCard`, `RagConflictPanel`) | Vitest + Testing Library |
| 페이지 통합 | Playwright e2e (백엔드 mock으로 4가지 conflict_status 케이스 시뮬레이션) |
| 타입 체크 | `tsc --noEmit` (CI 통과 필수) |

## 8. 접근성 / UX

- 카드 헤더는 `<h4>` 시멘틱
- "더 보기" 버튼 `aria-expanded`
- score는 시각 보조 정보 (스크린리더 우선순위 낮춤)
- RagConflictPanel 결정 버튼은 키보드 탐색 가능
- 충돌 사유 배너는 `role="alert"` (검토 주의 환기)

## 9. 디자인 토큰

f0/F2와 동일 Tailwind 사용:
- 컨테이너 `bg-white` / `dark:bg-slate-900`
- 카드 `border border-slate-200 rounded-lg p-4`
- 강조 `text-blue-700`, 보조 `text-slate-500`
- 충돌 배너 `bg-amber-50 text-amber-900 border-amber-300`
- RAG 영역 `bg-violet-50 border-violet-200` (정확매칭과 시각적 구분)

## 10. 영향 받지 않는 영역

- f0 입력 화면
- 다른 기능(F2/F3/F4/F5) 페이지/컴포넌트
- 공용 레이아웃, 라우트 정의
- `Feature1Result`(types/pipeline.ts) 공용 타입 — 기존 필드 그대로 사용
