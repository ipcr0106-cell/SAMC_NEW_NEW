/**
 * 기능4: 수출국표시사항 검토 — 전용 상수
 */

// 허용 업로드 파일 형식
export const ALLOWED_LABEL_MIME_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
  "application/pdf",
] as const;

export const ALLOWED_LABEL_EXTENSIONS = ".jpg, .jpeg, .png, .webp, .pdf";

// 파일 크기 제한 (10MB)
export const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024;

// API 경로
export const API_PATHS = {
  analyze: (caseId: string) =>
    `/cases/${caseId}/pipeline/feature/4/analyze`,
  validate: (caseId: string) =>
    `/cases/${caseId}/pipeline/feature/4/validate`,
  uploadLabel: (caseId: string) =>
    `/cases/${caseId}/pipeline/feature/4/upload`,
  getResult: (caseId: string) =>
    `/cases/${caseId}/pipeline/feature/4`,
  updateResult: (caseId: string) =>
    `/cases/${caseId}/pipeline/feature/4`,
  confirm: (caseId: string) =>
    `/cases/${caseId}/pipeline/feature/4/confirm`,
  report: (caseId: string) =>
    `/cases/${caseId}/pipeline/feature/4/report`,
} as const;

// 전반 판정 라벨
export const OVERALL_LABEL = {
  pass: "이상 없음",
  fail: "문제 발견 — 수정 필요",
  review_needed: "추가 검토 필요",
} as const;

export const OVERALL_COLOR = {
  pass: "text-green-600",
  fail: "text-red-600",
  review_needed: "text-yellow-600",
} as const;

// 교차검증 필드 한글 라벨
export const CROSS_CHECK_FIELD_LABEL: Record<string, string> = {
  product_name: "제품명",
  ingredients: "원재료",
  content_volume: "내용량",
  origin: "원산지",
  manufacturer: "제조사",
};
