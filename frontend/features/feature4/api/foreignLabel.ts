/**
 * 기능4: 수출국표시사항 검토 — API 호출 함수
 *
 * apiClient(services/apiClient.ts)를 통해서만 호출.
 * 직접 fetch() 사용 금지.
 */

import { apiClient } from "@/services/apiClient";
import type { Feature4Result, ImageIssue, LabelIssue, ValidationResult } from "@/types/pipeline";
import { API_PATHS } from "../constants";

// 라벨 분석 실행 (POST /analyze)
export const analyzeForeignLabel = async (
  caseId: string,
  payload: {
    label_text: string;
    food_type?: string;
    ingredients?: string[];
    label_image_url?: string;
    doc_product_name?: string;
    doc_content_volume?: string;
    doc_origin?: string;
    doc_manufacturer?: string;
    doc_ingredients?: string;
  }
): Promise<{ case_id: string; ai_result: Feature4Result }> => {
  const res = await apiClient.post(API_PATHS.analyze(caseId), payload);
  return res.data;
};

// 선택 항목 법령 정합성 검토 (POST /validate)
export const validateSelection = async (
  caseId: string,
  payload: {
    selected_issues: LabelIssue[];
    selected_image_issues?: ImageIssue[];
  }
): Promise<ValidationResult> => {
  const res = await apiClient.post(API_PATHS.validate(caseId), payload);
  return res.data;
};

// 라벨 이미지 업로드
export const uploadLabelImage = async (
  caseId: string,
  file: File
): Promise<{ uploaded_path: string; file_name: string }> => {
  const formData = new FormData();
  formData.append("file", file);

  const res = await apiClient.post(API_PATHS.uploadLabel(caseId), formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
};

// 기능4 결과 조회
export const getForeignLabelResult = async (
  caseId: string
): Promise<{ status: string; ai_result: Feature4Result | null; final_result: Feature4Result | null }> => {
  const res = await apiClient.get(API_PATHS.getResult(caseId));
  return res.data;
};

// 기능4 결과 수정 (담당자 교정)
export const updateForeignLabelResult = async (
  caseId: string,
  payload: { final_result: Feature4Result; edit_reason: string }
): Promise<void> => {
  await apiClient.patch(API_PATHS.updateResult(caseId), payload);
};

// 담당자 확인 완료 → 기능5로 진행
export const confirmForeignLabelResult = async (
  caseId: string
): Promise<void> => {
  await apiClient.post(API_PATHS.confirm(caseId));
};

// PDF 레포트 다운로드
export const downloadReport = async (caseId: string): Promise<void> => {
  const res = await apiClient.get(API_PATHS.report(caseId), {
    responseType: "blob",
  });
  const blob = new Blob([res.data], { type: "application/pdf" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `F4_report_${caseId}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};
