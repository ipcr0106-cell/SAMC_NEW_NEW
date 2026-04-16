/**
 * 기능1: 수입 가능 여부 판정 — 전용 타입
 *
 * 공통 타입(types/pipeline.ts)의 Feature1Result를 기반으로
 * UI 내부 상태 타입을 정의.
 */

import type { Feature1Result } from "@/types/pipeline";

// 백엔드 응답 래퍼 (ai_result + final_result + status)
export interface Feature1Response {
  case_id: string;
  status: "pending" | "running" | "waiting_review" | "completed" | "error";
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
}

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
