/**
 * 기능1: 수입 가능 여부 판정 — 상태 관리 훅
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import type { Feature1Result, HITL1DecisionsRequest, HITL2ConfirmRequest } from "@/types/pipeline";
import type { Feature1UiState, Feature1Response } from "../types";
import {
  getImportCheckResult,
  updateImportCheckResult,
  confirmImportCheckResult,
  runImportCheck,
  downloadReport,
  editF0Result,
  approveF0Result,
  submitHitl1Decisions,
  confirmHitl2,
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
  // Wave 4 P2: HITL-2 확장 필드
  hitl2FinalReason: "",
  hitl2SignerId: "",
  hitl2SelectedCitations: new Set<string>(),
  // Wave 4 P2: HITL-1 decisions 임시 상태
  hitl1Decisions: null,
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

  // HITL 결정 핸들러 (Wave 3: HITL-1/2 패널에서 호출)
  // 기존 updateImportCheckResult (PATCH /feature/1) 재사용.
  const submitHITLDecision = useCallback(
    async (verdict: Feature1Result["verdict"], reason: string) => {
      if (!state.editedResult) return;
      setState((prev) => ({ ...prev, isSaving: true, errorMessage: null }));
      try {
        const next: Feature1Result = {
          ...state.editedResult,
          verdict,
          import_possible: verdict === "수입가능",
        };
        await updateImportCheckResult(caseId, {
          final_result: next,
          edit_reason: reason,
        });
        // 저장 후 재조회 (needs_review → waiting_review 로 status 전환 반영)
        await fetchResult();
      } catch {
        setState((prev) => ({
          ...prev,
          isSaving: false,
          errorMessage: "HITL 결정 저장에 실패했습니다.",
        }));
      }
    },
    [caseId, state.editedResult, fetchResult],
  );

  // ── Wave 4 P2: HITL-0 편집 저장 (PATCH /pipeline/feature/0) ──
  const editF0 = useCallback(
    async (finalResult: Record<string, unknown>, editReason: string) => {
      setState((prev) => ({ ...prev, isSaving: true, errorMessage: null }));
      try {
        await editF0Result(caseId, { final_result: finalResult, edit_reason: editReason });
        await fetchResult();
      } catch {
        setState((prev) => ({
          ...prev,
          isSaving: false,
          errorMessage: "F0 편집 저장에 실패했습니다.",
        }));
      }
    },
    [caseId, fetchResult]
  );

  // ── Wave 4 P2: HITL-0 승인 (POST /pipeline/feature/0/approve) ──
  const approveF0 = useCallback(
    async (approverId: string, signature?: string) => {
      setState((prev) => ({ ...prev, isSaving: true, errorMessage: null }));
      try {
        await approveF0Result(caseId, {
          approver_id: approverId,
          approved_at: new Date().toISOString(),
          signature,
        });
        await fetchResult();
      } catch {
        setState((prev) => ({
          ...prev,
          isSaving: false,
          errorMessage: "F0 승인에 실패했습니다.",
        }));
      }
    },
    [caseId, fetchResult]
  );

  // ── Wave 4 P2: HITL-1 decisions 제출 (POST /hitl1-decisions) ──
  const submitHitl1 = useCallback(
    async (req: HITL1DecisionsRequest) => {
      setState((prev) => ({ ...prev, isSaving: true, errorMessage: null }));
      try {
        await submitHitl1Decisions(caseId, req);
        await fetchResult();
      } catch {
        setState((prev) => ({
          ...prev,
          isSaving: false,
          errorMessage: "HITL-1 결정 제출에 실패했습니다.",
        }));
      }
    },
    [caseId, fetchResult]
  );

  // ── Wave 4 P2: HITL-2 최종 판정 확정 (POST /confirm with body) ──
  const confirmHitl2Result = useCallback(
    async (req: HITL2ConfirmRequest) => {
      setState((prev) => ({ ...prev, isConfirming: true, errorMessage: null }));
      try {
        await confirmHitl2(caseId, req);
        await fetchResult();
      } catch {
        setState((prev) => ({
          ...prev,
          isConfirming: false,
          errorMessage: "최종 판정 확정에 실패했습니다.",
        }));
      } finally {
        setState((prev) => ({ ...prev, isConfirming: false }));
      }
    },
    [caseId, fetchResult]
  );

  // ── Wave 4 P2: HITL-2 UI 상태 setter ──
  const setHitl2FinalReason = useCallback((v: string) => {
    setState((prev) => ({ ...prev, hitl2FinalReason: v }));
  }, []);

  const setHitl2SignerId = useCallback((v: string) => {
    setState((prev) => ({ ...prev, hitl2SignerId: v }));
  }, []);

  const toggleHitl2Citation = useCallback((chunkId: string) => {
    setState((prev) => {
      const next = new Set(prev.hitl2SelectedCitations);
      if (next.has(chunkId)) next.delete(chunkId);
      else next.add(chunkId);
      return { ...prev, hitl2SelectedCitations: next };
    });
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

  // PDF report download
  const handleDownloadPdf = useCallback(async () => {
    try {
      await downloadReport(caseId);
    } catch {
      setState((prev) => ({
        ...prev,
        errorMessage: "PDF 다운로드에 실패했습니다.",
      }));
    }
  }, [caseId]);

  return {
    state,
    toggleLawRef,
    setUserVerdict,
    setEditReason,
    saveEdit,
    confirm,
    handleDownloadPdf,
    submitHITLDecision,
    runWithPayload,
    editF0,
    approveF0,
    submitHitl1,
    confirmHitl2Result,
    setHitl2FinalReason,
    setHitl2SignerId,
    toggleHitl2Citation,
  };
}
