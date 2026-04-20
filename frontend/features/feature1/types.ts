/**
 * 기능1: 수입 가능 여부 판정 — 전용 타입
 *
 * 공통 타입(types/pipeline.ts)의 Feature1Result를 기반으로
 * UI 내부 상태 타입을 정의.
 */

import type { Feature1Result, PipelineStepStatus, HITL1DecisionsRequest } from "@/types/pipeline";

// 백엔드 응답 래퍼 (ai_result + final_result + status)
//
// Wave 3 HITL:
//   - "needs_review" 는 HITL-1 에스컬레이션 발생 시 부여.
//   - "waiting_review" 는 HITL-1 처리 후 HITL-2 대기 시 부여.
//   - 담당자가 HITL-2 confirm 후 "confirmed" / "locked" 로 전이.
export interface Feature1Response {
  case_id: string;
  /** code-review MEDIUM-6: PipelineStepStatus 로 교체 (Wave 4 P2) */
  status: PipelineStepStatus;
  ai_result: (Feature1Result & { _internal?: Feature1Internal }) | null;
  final_result: (Feature1Result & { _internal?: Feature1Internal }) | null;
  edit_reason?: string | null;
  updated_at?: string | null;
}

// _internal 상세 정보 (백엔드 Feature1Output 확장 필드)
export interface Feature1Internal {
  aggregation: {
    total: number;
    permitted: number;
    restricted: number;
    prohibited: number;
    unidentified: number;
    results: IngredientMatchDetail[];
  } | null;
  conditional_evaluations: ConditionalEvaluationDetail[];
  forbidden_hits: ForbiddenHitDetail[];
  escalations: EscalationDetail[];
  law_refs: { law_source: string; law_article?: string | null }[];
  // ── Phase 4-B: RAG + HITL (backend/routers/feature1.py:_to_pipeline_result) ──
  rag_verdict: RagVerdict | null;
  rag_reasoning: string | null;
  law_citations: LawCitation[];
  conflict_status: ConflictStatus;
  // ── Wave 4 P2-BE: 파이프라인 버전 분기 (optional) ──
  pipeline_version?: "v1" | "v2" | null;
}

// ── RAG 판정 결과 (backend/models/f1_law_citation.py 1:1 미러링) ──
export type RagVerdict =
  | "permitted"
  | "restricted"
  | "prohibited"
  | "unidentified"
  | "error";

export type ConflictStatus =
  | "agreed"
  | "conflict"
  | "rag_supplemented"
  | "rag_unavailable"
  | "rag_skipped";

export interface LawCitation {
  chunk_id: string;
  namespace: string;
  regulation_id: string | null;
  section_path: string | null;
  text: string;
  score: number;
}

export interface IngredientMatchDetail {
  ingredient: {
    name: string;
    percentage?: number | null;
    ins?: string | null;
    cas?: string | null;
    part?: string | null;
  };
  verdict: "permitted" | "restricted" | "prohibited" | "unidentified";
  match_method:
    | "exact_name"
    | "ins_number"
    | "cas_number"
    | "scientific_name"
    | "fuzzy"
    | "llm_normalize"
    | null;
  matched_db_id: string | null;
  confidence: number;
  conditions?: string | null;
  matched_name_ko?: string | null;
  law_source?: string | null;
}

export interface ConditionalEvaluationDetail {
  ingredient_name: string;
  condition_type:
    | "usage_purpose"
    | "part_restriction"
    | "quantity_limit"
    | "natural_synthetic"
    | "irradiation"
    | "ambiguous";
  condition_description: string;
  is_satisfied: boolean | null;
  evidence?: string | null;
}

export interface ForbiddenHitDetail {
  name_ko: string;
  category: "drug" | "endangered" | "unauthorized" | "toxin" | "other";
  law_source?: string | null;
  reason?: string | null;
}

export interface EscalationDetail {
  module_id: string;
  trigger_type?: string;
  confidence_score?: number;
  reason: string;
}

// UI 상태
export type FetchStatus = "idle" | "loading" | "done" | "error";

export interface Feature1UiState {
  fetchStatus: FetchStatus;
  data: Feature1Response | null;
  editedResult: Feature1Result | null;
  editReason: string;
  selectedLawRefs: Set<string>; // 체크박스로 선택된 법령 근거
  userVerdict: "수입가능" | "수입불가" | "보류" | null;
  isSaving: boolean;
  isConfirming: boolean;
  errorMessage: string | null;
  // ── Wave 4 P2: HITL-2 확장 필드 ──
  hitl2FinalReason: string;
  hitl2SignerId: string;
  hitl2SelectedCitations: Set<string>;
  // ── Wave 4 P2: HITL-1 decisions 임시 상태 ──
  hitl1Decisions: HITL1DecisionsRequest | null;
}

// HITL-1/2 완료 상태 판별 헬퍼
export const isConfirmedStatus = (status: PipelineStepStatus | undefined): boolean =>
  status === "completed" || status === "confirmed" || status === "locked";

// 금지 카테고리 라벨
export const FORBIDDEN_CATEGORY_LABEL: Record<ForbiddenHitDetail["category"], string> = {
  drug: "마약류",
  endangered: "멸종위기종(CITES)",
  unauthorized: "식약처 미허가",
  toxin: "독성물질",
  other: "기타 금지",
};

// 조건 유형 라벨
export const CONDITION_TYPE_LABEL: Record<
  ConditionalEvaluationDetail["condition_type"],
  string
> = {
  usage_purpose: "용도 제한",
  part_restriction: "부위 제한",
  quantity_limit: "함량 제한",
  natural_synthetic: "천연/합성 구분",
  irradiation: "방사선 조사",
  ambiguous: "불명확 (담당자 확인 필요)",
};

// RAG conflict 상태 라벨 (UI 배지/패널용)
export const CONFLICT_STATUS_LABEL: Record<ConflictStatus, string> = {
  agreed: "DB·RAG 일치",
  conflict: "DB·RAG 충돌",
  rag_supplemented: "RAG 보완 판정",
  rag_unavailable: "RAG 호출 실패",
  rag_skipped: "RAG 미호출",
};

// RAG 판정 라벨
export const RAG_VERDICT_LABEL: Record<RagVerdict, string> = {
  permitted: "허용",
  restricted: "조건부 허용",
  prohibited: "금지",
  unidentified: "불명확",
  error: "판정 오류",
};

// Pinecone namespace → 한국어 라벨 (법령 종류)
export const NAMESPACE_LABEL: Record<string, string> = {
  additive_code_text: "식품첨가물공전",
  food_code_text: "식품공전",
  health_food_text: "건강기능식품공전",
  temporary_standard: "한시적 기준·규격",
  functional_labeling: "기능성표시 고시",
};
