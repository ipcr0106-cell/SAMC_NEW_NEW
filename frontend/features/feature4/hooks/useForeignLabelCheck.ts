/**
 * 기능4: 수출국표시사항 검토 — 상태 관리 훅
 *
 * [흐름]
 *  handleAnalyze → (사용자 항목 선택) → handleValidate → handleSaveEdit → handleConfirm
 */

"use client";

import { useState, useCallback } from "react";
import type { Feature4Result, ImageIssue, LabelIssue, ValidationResult } from "@/types/pipeline";
import type { Feature4State, LabelUploadState } from "../types";
import {
  analyzeForeignLabel,
  validateSelection,
  uploadLabelImage,
  getForeignLabelResult,
  updateForeignLabelResult,
  confirmForeignLabelResult,
  downloadReport,
} from "../api/foreignLabel";
import { MAX_FILE_SIZE_BYTES, ALLOWED_LABEL_MIME_TYPES } from "../constants";

// 분석 입력 폼 상태
export interface AnalyzeForm {
  label_text: string;
  food_type: string;
  ingredients_raw: string;  // 콤마 구분 원재료 (입력 편의용)
  label_image_url: string;
  doc_product_name: string;
  doc_content_volume: string;
  doc_origin: string;
  doc_manufacturer: string;
  doc_ingredients: string;
}

const initialForm: AnalyzeForm = {
  label_text: "",
  food_type: "미분류",
  ingredients_raw: "",
  label_image_url: "",
  doc_product_name: "",
  doc_content_volume: "",
  doc_origin: "",
  doc_manufacturer: "",
  doc_ingredients: "",
};

const initialUploadState: LabelUploadState = {
  file: null,
  previewUrl: null,
  uploadStatus: "idle",
};

const initialState: Feature4State = {
  uploadState: initialUploadState,
  analysisStatus: "idle",
  result: null,
  isConfirmed: false,
  editedResult: null,
  editReason: "",
};

export function useForeignLabelCheck(caseId: string) {
  const [state, setState] = useState<Feature4State>(initialState);
  const [form, setForm] = useState<AnalyzeForm>(initialForm);
  const [error, setError] = useState<string | null>(null);

  // 체크된 텍스트·이미지 위반 항목 (인덱스 기반)
  const [selectedIssueIdxs, setSelectedIssueIdxs] = useState<Set<number>>(new Set());
  const [selectedImageIssueIdxs, setSelectedImageIssueIdxs] = useState<Set<number>>(new Set());

  // 법령 정합성 검증 결과
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [validateStatus, setValidateStatus] = useState<"idle" | "running" | "done" | "error">("idle");

  // ── 폼 업데이트 ─────────────────────────────────────

  const handleFormChange = useCallback(<K extends keyof AnalyzeForm>(
    key: K,
    value: AnalyzeForm[K]
  ) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  }, []);

  // ── 분석 실행 ─────────────────────────────────────

  const handleAnalyze = useCallback(async () => {
    if (!form.label_text.trim()) {
      setError("라벨 텍스트를 입력해주세요.");
      return;
    }
    setError(null);
    setState((prev) => ({ ...prev, analysisStatus: "running" }));
    setSelectedIssueIdxs(new Set());
    setSelectedImageIssueIdxs(new Set());
    setValidationResult(null);
    setValidateStatus("idle");

    try {
      const { ai_result } = await analyzeForeignLabel(caseId, {
        label_text: form.label_text,
        food_type: form.food_type || "미분류",
        ingredients: form.ingredients_raw
          ? form.ingredients_raw.split(",").map((s) => s.trim()).filter(Boolean)
          : [],
        label_image_url: form.label_image_url || undefined,
        doc_product_name: form.doc_product_name || undefined,
        doc_content_volume: form.doc_content_volume || undefined,
        doc_origin: form.doc_origin || undefined,
        doc_manufacturer: form.doc_manufacturer || undefined,
        doc_ingredients: form.doc_ingredients || undefined,
      });
      setState((prev) => ({
        ...prev,
        analysisStatus: "done",
        result: ai_result,
        editedResult: ai_result,
      }));
    } catch (e) {
      setState((prev) => ({ ...prev, analysisStatus: "error" }));
      setError("분석에 실패했습니다. 서버 연결을 확인해주세요.");
      console.error(e);
    }
  }, [caseId, form]);

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

  // ── 결과 조회 ─────────────────────────────────────

  const fetchResult = useCallback(async () => {
    setState((prev) => ({ ...prev, analysisStatus: "running" }));
    try {
      const data = await getForeignLabelResult(caseId);
      const result = data.final_result ?? data.ai_result;
      setState((prev) => ({
        ...prev,
        analysisStatus: "done",
        result,
        editedResult: result,
        isConfirmed: data.status === "completed",
      }));
    } catch {
      setState((prev) => ({ ...prev, analysisStatus: "error" }));
      setError("결과를 불러오는 데 실패했습니다.");
    }
  }, [caseId]);

  // ── 파일 업로드 ─────────────────────────────────────

  const handleFileSelect = useCallback((file: File) => {
    setError(null);
    if (!ALLOWED_LABEL_MIME_TYPES.includes(file.type as (typeof ALLOWED_LABEL_MIME_TYPES)[number])) {
      setError("JPG, PNG, WEBP, PDF 파일만 업로드 가능합니다.");
      return;
    }
    if (file.size > MAX_FILE_SIZE_BYTES) {
      setError("파일 크기는 10MB 이하여야 합니다.");
      return;
    }
    const previewUrl = file.type.startsWith("image/") ? URL.createObjectURL(file) : null;
    setState((prev) => ({
      ...prev,
      uploadState: { file, previewUrl, uploadStatus: "idle" },
    }));
  }, []);

  const handleUpload = useCallback(async () => {
    if (!state.uploadState.file) return;
    setState((prev) => ({
      ...prev,
      uploadState: { ...prev.uploadState, uploadStatus: "uploading" },
    }));
    try {
      const { uploaded_path } = await uploadLabelImage(caseId, state.uploadState.file);
      setState((prev) => ({
        ...prev,
        uploadState: { ...prev.uploadState, uploadStatus: "uploaded", uploadedPath: uploaded_path },
      }));
    } catch {
      setState((prev) => ({
        ...prev,
        uploadState: { ...prev.uploadState, uploadStatus: "error" },
      }));
      setError("업로드에 실패했습니다. 다시 시도해주세요.");
    }
  }, [caseId, state.uploadState.file]);

  // ── 수정 저장 ─────────────────────────────────────

  const handleEditResult = useCallback((updated: Feature4Result) => {
    setState((prev) => ({ ...prev, editedResult: updated }));
  }, []);

  const handleEditReason = useCallback((reason: string) => {
    setState((prev) => ({ ...prev, editReason: reason }));
  }, []);

  const handleSaveEdit = useCallback(async () => {
    if (!state.editedResult) return;
    try {
      await updateForeignLabelResult(caseId, {
        final_result: state.editedResult,
        edit_reason: state.editReason,
      });
    } catch {
      setError("저장에 실패했습니다.");
    }
  }, [caseId, state.editedResult, state.editReason]);

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

  // 선택된 항목만 바로 저장 (editedResult 상태를 거치지 않고 직접 저장)
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
    form,
    error,
    selectedIssueIdxs,
    selectedImageIssueIdxs,
    validationResult,
    validateStatus,
    handleFormChange,
    handleAnalyze,
    handleToggleIssue,
    handleToggleImageIssue,
    handleSelectAllIssues,
    handleSelectAllImageIssues,
    handleValidate,
    fetchResult,
    handleFileSelect,
    handleUpload,
    handleEditResult,
    handleEditReason,
    handleSaveEdit,
    handleSaveSelected,
    handleConfirm,
    handleDownloadReport,
    downloadStatus,
    buildSelectedResult,
  };
}
