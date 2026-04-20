/**
 * 기능4: 수출국표시사항 검토 — 전용 타입
 *
 * 공통 타입(types/pipeline.ts)의 Feature4Result를 기반으로
 * UI 상태 등 기능4 내부에서만 쓰는 타입 정의.
 */

import type { Feature4Result } from "@/types/pipeline";

// 라벨 이미지 업로드 상태 (F0에서 처리되지만 State 구조 유지)
export type UploadStatus = "idle" | "uploading" | "uploaded" | "error";

export interface LabelUploadState {
  file: File | null;
  previewUrl: string | null;
  uploadStatus: UploadStatus;
  uploadedPath?: string;
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
