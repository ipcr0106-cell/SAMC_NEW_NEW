/**
 * 기능1: 수입 가능 여부 판정 — API 호출 함수
 *
 * apiClient(services/apiClient.ts)를 통해서만 호출.
 * 직접 fetch() 사용 금지 (팀컨벤션 §6).
 */

import { apiClient } from "@/services/apiClient";
import type { Feature1Result, HITL1DecisionsRequest, HITL2ConfirmRequest } from "@/types/pipeline";
import type { Feature1Response } from "../types";
import { API_PATHS } from "../constants";

// 기능1 결과 조회
export const getImportCheckResult = async (
  caseId: string
): Promise<Feature1Response> => {
  const res = await apiClient.get(API_PATHS.getResult(caseId));
  return res.data;
};

// 기능1 실행 (원재료 목록 + 식품유형 + 공정조건 전달)
export interface RunPayload {
  ingredients: {
    name: string;
    percentage?: number;
    ins?: string;
    cas?: string;
    chemical_name?: string;
    part?: string;
    sub_ingredients?: RunPayload["ingredients"];
  }[];
  food_type?: string;
  process_conditions?: {
    is_heated?: boolean;
    is_fermented?: boolean;
    is_distilled?: boolean;
    alcohol_percentage?: number;
  };
}

export const runImportCheck = async (
  caseId: string,
  payload: RunPayload
): Promise<Feature1Response> => {
  const res = await apiClient.post(API_PATHS.runResult(caseId), payload);
  return res.data;
};

// 담당자 결과 수정
export const updateImportCheckResult = async (
  caseId: string,
  payload: { final_result: Feature1Result; edit_reason: string }
): Promise<void> => {
  await apiClient.patch(API_PATHS.updateResult(caseId), payload);
};

// 담당자 확인 완료 → 다음 단계 진행
export const confirmImportCheckResult = async (
  caseId: string
): Promise<void> => {
  await apiClient.post(API_PATHS.confirm(caseId));
};

// 레포트 PDF 다운로드
export const downloadReport = async (caseId: string): Promise<void> => {
  const res = await apiClient.get(API_PATHS.report(caseId), {
    responseType: "blob",
  });
  const blob = new Blob([res.data], { type: "application/pdf" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `F1_report_${caseId}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};

// ── HITL-0: F0 파싱 결과 편집 (PATCH /pipeline/feature/0) ──
export const editF0Result = async (
  caseId: string,
  payload: { final_result: Record<string, unknown>; edit_reason: string }
): Promise<void> => {
  await apiClient.patch(API_PATHS.f0Edit(caseId), payload);
};

// ── HITL-0: F0 결과 승인 (POST /pipeline/feature/0/approve) ──
export const approveF0Result = async (
  caseId: string,
  payload: { approver_id: string; approved_at: string; signature?: string }
): Promise<void> => {
  await apiClient.post(API_PATHS.f0Approve(caseId), payload);
};

// ── HITL-1: 불확실 원재료 결정 제출 (POST /hitl1-decisions) ──
export const submitHitl1Decisions = async (
  caseId: string,
  payload: HITL1DecisionsRequest
): Promise<void> => {
  await apiClient.post(API_PATHS.hitl1Decisions(caseId), payload);
};

// ── HITL-2: 최종 판정 확정 (POST /confirm with body) ──
export const confirmHitl2 = async (
  caseId: string,
  payload: HITL2ConfirmRequest
): Promise<void> => {
  await apiClient.post(API_PATHS.confirm(caseId), payload);
};
