/**
 * 기능4: 수출국표시사항 검토 — 상태 관리 훅
 *
 * [흐름]
 *  페이지 진입 → fetchResult(기존 결과 조회)
 *  handleAnalyze(F0/F1/F2 데이터 기반 자동 분석) → (사용자 항목 선택) → handleValidate → handleSaveSelected → handleConfirm
 */

"use client";

import { useState, useCallback } from "react";
import type { Feature4Result, ImageIssue, LabelIssue, ValidationResult } from "@/types/pipeline";
import type { Feature4State } from "../types";
import {
  analyzeForeignLabel,
  validateSelection,
  getForeignLabelResult,
  updateForeignLabelResult,
  confirmForeignLabelResult,
  downloadReport,
} from "../api/foreignLabel";

const initialState: Feature4State = {
  uploadState: { file: null, previewUrl: null, uploadStatus: "idle" },
  analysisStatus: "idle",
  result: null,
  isConfirmed: false,
  editedResult: null,
  editReason: "",
};

export function useForeignLabelCheck(caseId: string) {
  const [state, setState] = useState<Feature4State>(initialState);
  const [error, setError] = useState<string | null>(null);

  // 체크된 텍스트·이미지 위반 항목 (인덱스 기반)
  const [selectedIssueIdxs, setSelectedIssueIdxs] = useState<Set<number>>(new Set());
  const [selectedImageIssueIdxs, setSelectedImageIssueIdxs] = useState<Set<number>>(new Set());

  // 법령 정합성 검증 결과
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [validateStatus, setValidateStatus] = useState<"idle" | "running" | "done" | "error">("idle");

  // ── 분석 실행 (F0/F1/F2에서 자동 조회) ─────────────────

  const handleAnalyze = useCallback(async () => {
    setError(null);
    setState((prev) => ({ ...prev, analysisStatus: "running" }));
    setSelectedIssueIdxs(new Set());
    setSelectedImageIssueIdxs(new Set());
    setValidationResult(null);
    setValidateStatus("idle");

    try {
      const { ai_result } = await analyzeForeignLabel(caseId, {});
      setState((prev) => ({
        ...prev,
        analysisStatus: "done",
        result: ai_result,
        editedResult: ai_result,
      }));
    } catch (e: unknown) {
      setState((prev) => ({ ...prev, analysisStatus: "error" }));

      // 법령 DB 업데이트 중 (503) → 전용 안내 메시지
      if (
        e &&
        typeof e === "object" &&
        "response" in e &&
        (e as { response?: { status?: number } }).response?.status === 503
      ) {
        setError("현재 법령 DB가 업데이트 중입니다. 잠시 후 다시 시도해주세요.");
      } else {
        setError("분석에 실패했습니다. 서버 연결을 확인해주세요.");
      }
      console.error(e);
    }
  }, [caseId]);

  // ── 항목 선택 토글 ─────────────────────────────────

  const handleToggleIssue = useCallback((idx: number) => {
    setSelectedIssueIdxs((prev) => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
    setValidationResult(null);
    setValidateStatus("idle");
  }, []);

  const handleToggleImageIssue = useCallback((idx: number) => {
    setSelectedImageIssueIdxs((prev) => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
    setValidationResult(null);
    setValidateStatus("idle");
  }, []);

  const handleSelectAllIssues = useCallback(() => {
    const issues = state.result?.issues ?? [];
    setSelectedIssueIdxs(new Set(issues.map((_, i) => i)));
  }, [state.result]);

  const handleSelectAllImageIssues = useCallback(() => {
    const imageIssues = state.result?.image_issues ?? [];
    setSelectedImageIssueIdxs(new Set(imageIssues.map((_, i) => i)));
  }, [state.result]);

  // ── 법령 정합성 검증 ─────────────────────────────────

  const handleValidate = useCallback(async () => {
    const issues = state.result?.issues ?? [];
    const imageIssues = state.result?.image_issues ?? [];

    const selectedIssues = issues.filter((_, i) => selectedIssueIdxs.has(i));
    const selectedImageIssues = imageIssues.filter((_, i) => selectedImageIssueIdxs.has(i));

    if (selectedIssues.length === 0 && selectedImageIssues.length === 0) {
      setError("검증할 항목을 1개 이상 선택해주세요.");
      return;
    }

    setError(null);
    setValidateStatus("running");

    try {
      const result = await validateSelection(caseId, {
        selected_issues: selectedIssues,
        selected_image_issues: selectedImageIssues,
      });
      setValidationResult(result);
      setValidateStatus("done");
    } catch (e) {
      setValidateStatus("error");
      setError("법령 검증에 실패했습니다.");
      console.error(e);
    }
  }, [caseId, state.result, selectedIssueIdxs, selectedImageIssueIdxs]);

  // ── 결과 조회 (페이지 진입 시) ─────────────────────────

  const fetchResult = useCallback(async () => {
    try {
      const data = await getForeignLabelResult(caseId);
      if (data.status === "pending" && !data.ai_result) {
        // 아직 분석 결과 없음 — idle 상태 유지
        return;
      }
      const result = data.final_result ?? data.ai_result;
      setState((prev) => ({
        ...prev,
        analysisStatus: "done",
        result,
        editedResult: result,
        isConfirmed: data.status === "completed",
      }));
    } catch {
      // 결과 없으면 무시 (첫 진입)
    }
  }, [caseId]);

  // ── 확인 완료 ─────────────────────────────────────

  const handleConfirm = useCallback(async () => {
    try {
      await confirmForeignLabelResult(caseId);
      setState((prev) => ({ ...prev, isConfirmed: true }));
    } catch {
      setError("확인 처리에 실패했습니다.");
    }
  }, [caseId]);

  // ── PDF 레포트 다운로드 ─────────────────────────────

  const [downloadStatus, setDownloadStatus] = useState<"idle" | "downloading">("idle");

  const handleDownloadReport = useCallback(async () => {
    setDownloadStatus("downloading");
    setError(null);
    try {
      await downloadReport(caseId);
    } catch {
      setError("레포트 다운로드에 실패했습니다. 분석 결과가 저장되어 있는지 확인해주세요.");
    } finally {
      setDownloadStatus("idle");
    }
  }, [caseId]);

  // 선택된 항목으로 editedResult 구성
  const buildSelectedResult = useCallback((): Feature4Result | null => {
    if (!state.result) return null;
    const issues = state.result.issues.filter((_, i) => selectedIssueIdxs.has(i));
    const image_issues = (state.result.image_issues ?? []).filter((_, i) => selectedImageIssueIdxs.has(i));
    const hasError = [...issues, ...image_issues].some(
      (it) => (it as LabelIssue & ImageIssue).severity === "must_fix"
    );
    return {
      ...state.result,
      issues,
      image_issues,
      overall: hasError ? "fail" : issues.length + image_issues.length > 0 ? "review_needed" : "pass",
    };
  }, [state.result, selectedIssueIdxs, selectedImageIssueIdxs]);

  // 선택된 항목만 바로 저장
  const handleSaveSelected = useCallback(async (editReason: string = "") => {
    const selected = buildSelectedResult();
    if (!selected) return;
    try {
      await updateForeignLabelResult(caseId, {
        final_result: selected,
        edit_reason: editReason,
      });
      setState((prev) => ({ ...prev, editedResult: selected }));
    } catch {
      setError("저장에 실패했습니다.");
    }
  }, [caseId, buildSelectedResult]);

  return {
    state,
    error,
    selectedIssueIdxs,
    selectedImageIssueIdxs,
    validationResult,
    validateStatus,
    handleAnalyze,
    handleToggleIssue,
    handleToggleImageIssue,
    handleSelectAllIssues,
    handleSelectAllImageIssues,
    handleValidate,
    fetchResult,
    handleSaveSelected,
    handleConfirm,
    handleDownloadReport,
    downloadStatus,
  };
}
