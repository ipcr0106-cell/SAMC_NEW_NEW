/**
 * 기능1: 수입 가능 여부 판정 — API 호출 함수
 *
 * apiClient(services/apiClient.ts)를 통해서만 호출.
 * 직접 fetch() 사용 금지 (팀컨벤션 §6).
 */

import { apiClient } from "@/services/apiClient";
import type { Feature1Result } from "@/types/pipeline";
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
