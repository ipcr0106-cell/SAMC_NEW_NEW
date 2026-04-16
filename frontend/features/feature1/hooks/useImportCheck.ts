/**
 * 기능1: 수입 가능 여부 판정 — 상태 관리 훅
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import type { Feature1Result } from "@/types/pipeline";
import type { Feature1UiState, Feature1Response } from "../types";
import {
  getImportCheckResult,
  updateImportCheckResult,
  confirmImportCheckResult,
  runImportCheck,
  type RunPayload,
} from "../api/importCheck";

const initialState: Feature1UiState = {
  fetchStatus: "idle",
  data: null,
  editedResult: null,
  editReason: "",
  selectedLawRefs: new Set<string>(),
  userVerdict: null,
  isSaving: false,
  isConfirming: false,
  errorMessage: null,
};

export function useImportCheck(caseId: string) {
  const [state, setState] = useState<Feature1UiState>(initialState);

  const applyResponse = useCallback((data: Feature1Response) => {
    const source = data.final_result ?? data.ai_result;
    setState((prev) => ({
      ...prev,
      fetchStatus: "done",
      data,
      editedResult: source
        ? ({
            ingredients: source.ingredients,
            verdict: source.verdict,
            import_possible: source.import_possible,
            fail_reasons: source.fail_reasons,
            standards_check: source.standards_check,
          } as Feature1Result)
        : null,
      userVerdict: source?.verdict ?? null,
      // 법령 근거 모두 기본 체크
      selectedLawRefs: new Set(
        source?._internal?.law_refs?.map((r) => r.law_source) ?? []
      ),
    }));
  }, []);

  // 최초 로드
  const fetchResult = useCallback(async () => {
    setState((prev) => ({ ...prev, fetchStatus: "loading", errorMessage: null }));
    try {
      const data = await getImportCheckResult(caseId);
      applyResponse(data);
    } catch (err) {
      const message =
        (err as { response?: { status?: number } })?.response?.status === 404
          ? "기능1이 아직 실행되지 않았습니다. [기능1 실행] 버튼을 눌러주세요."
          : "결과를 불러오는 데 실패했습니다.";
      setState((prev) => ({
        ...prev,
        fetchStatus: "error",
        errorMessage: message,
      }));
    }
  }, [caseId, applyResponse]);

  useEffect(() => {
    fetchResult();
  }, [fetchResult]);

  // 기능1 실행 (데모/재실행용)
  const runWithPayload = useCallback(
    async (payload: RunPayload) => {
      setState((prev) => ({ ...prev, fetchStatus: "loading", errorMessage: null }));
      try {
        const data = await runImportCheck(caseId, payload);
        applyResponse(data);
      } catch {
        setState((prev) => ({
          ...prev,
          fetchStatus: "error",
          errorMessage: "기능1 실행 중 오류가 발생했습니다.",
        }));
      }
    },
    [caseId, applyResponse]
  );

  // 법령 근거 체크박스 토글
  const toggleLawRef = useCallback((lawSource: string) => {
    setState((prev) => {
      const next = new Set(prev.selectedLawRefs);
      if (next.has(lawSource)) next.delete(lawSource);
      else next.add(lawSource);
      return { ...prev, selectedLawRefs: next };
    });
  }, []);

  // 판정 라디오
  const setUserVerdict = useCallback(
    (verdict: "수입가능" | "수입불가" | "보류") => {
      setState((prev) => ({ ...prev, userVerdict: verdict }));
    },
    []
  );

  // 수정 사유
  const setEditReason = useCallback((reason: string) => {
    setState((prev) => ({ ...prev, editReason: reason }));
  }, []);

  // 수정 저장 (PATCH)
  const saveEdit = useCallback(async () => {
    if (!state.editedResult) return;
    setState((prev) => ({ ...prev, isSaving: true }));
    try {
      const next: Feature1Result = {
        ...state.editedResult,
        verdict:
          state.userVerdict === "보류"
            ? state.editedResult.verdict
            : state.userVerdict ?? state.editedResult.verdict,
        import_possible:
          state.userVerdict === "수입가능"
            ? true
            : state.userVerdict === "수입불가"
              ? false
              : state.editedResult.import_possible,
      };
      await updateImportCheckResult(caseId, {
        final_result: next,
        edit_reason: state.editReason,
      });
      setState((prev) => ({
        ...prev,
        isSaving: false,
        editedResult: next,
      }));
    } catch {
      setState((prev) => ({
        ...prev,
        isSaving: false,
        errorMessage: "저장에 실패했습니다.",
      }));
    }
  }, [caseId, state.editedResult, state.editReason, state.userVerdict]);

  // 확인 완료 (POST /confirm)
  const confirm = useCallback(async () => {
    setState((prev) => ({ ...prev, isConfirming: true }));
    try {
      await confirmImportCheckResult(caseId);
      await fetchResult();
    } catch {
      setState((prev) => ({
        ...prev,
        isConfirming: false,
        errorMessage: "확인 처리에 실패했습니다.",
      }));
    } finally {
      setState((prev) => ({ ...prev, isConfirming: false }));
    }
  }, [caseId, fetchResult]);

  return {
    state,
    fetchResult,
    runWithPayload,
    toggleLawRef,
    setUserVerdict,
    setEditReason,
    saveEdit,
    confirm,
  };
}
