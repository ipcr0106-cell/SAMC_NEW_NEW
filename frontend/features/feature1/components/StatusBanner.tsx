/**
 * 기능1: API 조회 결과 상태 배너 컴포넌트
 *
 * Wave A Phase 1 뼈대 — Phase 3에서 실제 feature_status 연동 예정.
 *
 * 상태별 렌더:
 *   "ok"      → null (렌더 없음)
 *   "partial" → 노란색 경고 배지
 *   "error"   → 빨간색 오류 배지
 */

"use client";

import type { ApiQueryStatus } from "../types";

interface StatusBannerProps {
  status: ApiQueryStatus;
  message?: string;
}

const BANNER_CONFIG: Record<
  Exclude<ApiQueryStatus, "ok">,
  { className: string; defaultMessage: string }
> = {
  partial: {
    className:
      "bg-amber-50 border border-amber-300 text-amber-800 rounded-md px-4 py-2 text-sm",
    defaultMessage: "일부 조회 실패 — 결과가 불완전할 수 있습니다",
  },
  error: {
    className:
      "bg-red-50 border border-red-300 text-red-800 rounded-md px-4 py-2 text-sm",
    defaultMessage: "조회 실패 — 결과를 신뢰하지 마십시오",
  },
};

export default function StatusBanner({ status, message }: StatusBannerProps) {
  if (status === "ok") return null;

  const config = BANNER_CONFIG[status];

  return (
    <div
      data-testid="f1-status-banner"
      data-status={status}
      className={config.className}
      role="alert"
    >
      {message ?? config.defaultMessage}
    </div>
  );
}
