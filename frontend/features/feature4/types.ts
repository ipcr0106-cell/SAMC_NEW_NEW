/**
 * 기능4: 수출국표시사항 검토 — 전용 타입
 *
 * 공통 타입(types/pipeline.ts)의 Feature4Result를 기반으로
 * UI 상태, 폼 입력 등 기능4 내부에서만 쓰는 타입 정의.
 */

import type { Feature4Result, LabelIssue } from "@/types/pipeline";

// 라벨 이미지 업로드 상태
export type UploadStatus = "idle" | "uploading" | "uploaded" | "error";

export interface LabelUploadState {
  file: File | null;
  previewUrl: string | null;
  uploadStatus: UploadStatus;
  uploadedPath?: string;    // Supabase Storage 경로 (업로드 완료 시)
  errorMessage?: string;
}

// 분석 실행 상태
export type AnalysisStatus = "idle" | "running" | "done" | "error";

export interface Feature4State {
  uploadState: LabelUploadState;
  analysisStatus: AnalysisStatus;
  result: Feature4Result | null;
  isConfirmed: boolean;             // 담당자 확인 완료 여부
  editedResult: Feature4Result | null;  // 담당자가 수정한 결과
  editReason: string;               // 수정 사유 (식약처 소명용)
}

// 이슈 심각도 라벨 (UI 표시용)
export const SEVERITY_LABEL: Record<LabelIssue["severity"], string> = {
  must_fix: "삭제/수정 필수",
  review_needed: "검토 필요",
};

// 교차 검증 항목 한국어 라벨
export const CROSS_CHECK_FIELD_LABEL = {
  product_name: "제품명",
  ingredients: "원재료",
  content_volume: "내용량",
  origin: "원산지",
  manufacturer: "제조사",
} as const;
