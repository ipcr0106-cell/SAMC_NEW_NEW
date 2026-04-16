/**
 * API 공통 응답 타입
 */

export interface ApiError {
  error: string;      // 영어 에러 코드 (예: "CASE_NOT_FOUND")
  message: string;    // 한국어 설명
  feature?: number;   // 관련 기능 번호
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
}

// SSE 이벤트 타입
export type SSEEvent =
  | { event: "feature_start"; feature: number; name: string }
  | { event: "feature_progress"; feature: number; message: string }
  | { event: "feature_result"; feature: number; result: unknown }
  | { event: "feature_waiting"; feature: number; message: string }
  | { event: "feature_confirmed"; feature: number }
  | { event: "feature_error"; feature: number; error: string; retryable: boolean }
  | { event: "pipeline_complete"; case_id: string }
  | { event: "error"; message: string };
