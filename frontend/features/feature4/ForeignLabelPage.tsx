/**
 * 기능4: 수출국표시사항 검토 — 메인 페이지 컴포넌트
 *
 * app/cases/[id]/feature4/page.tsx 에서 import해서 사용.
 * 이 컴포넌트가 기능4의 모든 UI를 담당.
 */

"use client";

import { useEffect } from "react";
import { useForeignLabelCheck } from "./hooks/useForeignLabelCheck";
import LabelUploader from "./components/LabelUploader";
import AnalysisResult from "./components/AnalysisResult";
import IssueList from "./components/IssueList";
import CrossCheckTable from "./components/CrossCheckTable";
import ConfirmPanel from "./components/ConfirmPanel";

interface ForeignLabelPageProps {
  caseId: string;
}

export default function ForeignLabelPage({ caseId }: ForeignLabelPageProps) {
  const {
    state,
    error,
    handleFileSelect,
    handleUpload,
    fetchResult,
    handleEditResult,
    handleEditReason,
    handleSaveEdit,
    handleConfirm,
  } = useForeignLabelCheck(caseId);

  // 페이지 진입 시 기존 결과 조회
  useEffect(() => {
    fetchResult();
  }, [fetchResult]);

  return (
    <div className="space-y-6 p-6">
      <h2 className="text-xl font-bold">기능4: 수출국표시사항 검토</h2>

      {error && (
        <div className="rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* 라벨 이미지 업로드 */}
      {!state.isConfirmed && (
        <LabelUploader
          uploadState={state.uploadState}
          onFileSelect={handleFileSelect}
          onUpload={handleUpload}
        />
      )}

      {/* 분석 진행 중 */}
      {state.analysisStatus === "running" && (
        <div className="text-sm text-gray-500 animate-pulse">AI 분석 중...</div>
      )}

      {/* 분석 결과 */}
      {state.result && (
        <>
          <AnalysisResult overall={state.result.overall} />

          <IssueList
            issues={state.result.issues}
            isConfirmed={state.isConfirmed}
          />

          <CrossCheckTable
            crossCheck={state.result.cross_check}
            isConfirmed={state.isConfirmed}
          />

          {/* 담당자 확인/수정 패널 */}
          {!state.isConfirmed && (
            <ConfirmPanel
              editReason={state.editReason}
              onEditReason={handleEditReason}
              onSave={handleSaveEdit}
              onConfirm={handleConfirm}
            />
          )}

          {state.isConfirmed && (
            <div className="rounded-md bg-green-50 border border-green-200 p-3 text-sm text-green-700">
              담당자 확인 완료. 기능5(한글표시사항)로 진행됩니다.
            </div>
          )}
        </>
      )}
    </div>
  );
}
