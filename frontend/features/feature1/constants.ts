/**
 * 기능1: 수입 가능 여부 판정 — 전용 상수
 */

// API 경로 (feature4 패턴 준수)
export const API_PATHS = {
  getResult: (caseId: string) =>
    `/cases/${caseId}/pipeline/feature/1`,
  runResult: (caseId: string) =>
    `/cases/${caseId}/pipeline/feature/1/run`,
  updateResult: (caseId: string) =>
    `/cases/${caseId}/pipeline/feature/1`,
  confirm: (caseId: string) =>
    `/cases/${caseId}/pipeline/feature/1/confirm`,
  report: (caseId: string) =>
    `/cases/${caseId}/pipeline/feature/1/report`,
  // ── HITL-0 (F0 파싱 결과 편집·승인) ──
  f0Edit: (caseId: string) =>
    `/cases/${caseId}/pipeline/feature/0`,
  f0Approve: (caseId: string) =>
    `/cases/${caseId}/pipeline/feature/0/approve`,
  // ── HITL-1 (불확실 원재료 결정) ──
  hitl1Decisions: (caseId: string) =>
    `/cases/${caseId}/pipeline/feature/1/hitl1-decisions`,
} as const;

// 판정 표시 라벨
export const VERDICT_LABEL: Record<string, string> = {
  수입가능: "수입 가능",
  수입불가: "수입 불가",
  검토필요: "검토 필요",
};

export const VERDICT_COLOR: Record<string, string> = {
  수입가능: "text-green-600",
  수입불가: "text-red-600",
  검토필요: "text-amber-600",
};

// 원재료 상태 라벨
export const INGREDIENT_STATUS_LABEL = {
  allowed: "허용",
  not_found: "확인 필요",
  synthetic_flavor_warning: "합성향료 - 하위원료 확인",
} as const;

export const INGREDIENT_STATUS_COLOR = {
  allowed: "text-green-600 bg-green-50",
  not_found: "text-red-600 bg-red-50",
  synthetic_flavor_warning: "text-yellow-600 bg-yellow-50",
} as const;

// 기준규격 검사 상태 라벨
export const STANDARDS_STATUS_LABEL = {
  pass: "적합",
  fail: "부적합",
  review_needed: "검토 필요",
  no_data: "데이터 없음",
  no_threshold: "기준치 없음",
} as const;

// 기준규격 검사 상태 색상
export const STANDARDS_STATUS_COLOR = {
  pass: "text-green-600 bg-green-50",
  fail: "text-red-600 bg-red-50",
  review_needed: "text-yellow-600 bg-yellow-50",
  no_data: "text-gray-500 bg-gray-50",
  no_threshold: "text-gray-400 bg-gray-50",
} as const;
