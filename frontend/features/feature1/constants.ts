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
} as const;

// 판정 표시 라벨
export const VERDICT_LABEL = {
  수입가능: "수입 가능",
  수입불가: "수입 불가",
} as const;

export const VERDICT_COLOR = {
  수입가능: "text-green-600",
  수입불가: "text-red-600",
} as const;

// 원재료 상태 라벨
export const INGREDIENT_STATUS_LABEL = {
  allowed: "허용",
  not_found: "확인 필요",
  synthetic_flavor_warning: "합성향료 - 하위원료 확인",
} as const;

export const INGREDIENT_STATUS_COLOR = {
  allowed: "text-green-600 bg-green-50",
  not_found: "text-red-600 bg-red-50",
  synthetic_flavor_warning: "text-yellow-700 bg-yellow-50",
} as const;

// 기준규격 상태 라벨
export const STANDARDS_STATUS_LABEL = {
  pass: "적합",
  fail: "초과",
  no_threshold: "기준 미등록",
} as const;

export const STANDARDS_STATUS_COLOR = {
  pass: "text-green-600",
  fail: "text-red-600 font-semibold",
  no_threshold: "text-gray-500",
} as const;
