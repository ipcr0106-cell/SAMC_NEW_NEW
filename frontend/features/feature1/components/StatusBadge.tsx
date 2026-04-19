/**
 * HITL 파이프라인 상태 배지 컴포넌트
 *
 * Wave 4 P2-FE: E-01 Playwright 테스트가 data-testid="f1-status-badge" +
 * data-status={status} 를 기대한다.
 *
 * 색상 매핑:
 *   pending / running   → gray
 *   approved / completed → blue
 *   waiting_review / needs_review → amber
 *   confirmed           → green
 *   locked              → slate
 *   error               → red
 */

"use client";

import type { PipelineStepStatus } from "@/types/pipeline";

interface StatusBadgeProps {
  status: PipelineStepStatus | "error";
  className?: string;
}

const STATUS_LABEL: Record<PipelineStepStatus | "error", string> = {
  pending: "대기",
  running: "분석 중",
  completed: "완료",
  approved: "F0 승인",
  waiting_review: "최종 검토 대기",
  needs_review: "검토 필요",
  confirmed: "확정",
  locked: "잠김",
  error: "오류",
};

const STATUS_CLASS: Record<PipelineStepStatus | "error", string> = {
  pending:        "bg-gray-100 text-gray-600 border-gray-200",
  running:        "bg-gray-100 text-gray-600 border-gray-200",
  completed:      "bg-blue-100 text-blue-700 border-blue-200",
  approved:       "bg-blue-100 text-blue-700 border-blue-200",
  waiting_review: "bg-amber-100 text-amber-700 border-amber-200",
  needs_review:   "bg-amber-100 text-amber-700 border-amber-200",
  confirmed:      "bg-green-100 text-green-700 border-green-200",
  locked:         "bg-slate-100 text-slate-600 border-slate-200",
  error:          "bg-red-100 text-red-600 border-red-200",
};

export default function StatusBadge({ status, className = "" }: StatusBadgeProps) {
  return (
    <span
      data-testid="f1-status-badge"
      data-status={status}
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${STATUS_CLASS[status] ?? STATUS_CLASS.pending} ${className}`}
    >
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}
