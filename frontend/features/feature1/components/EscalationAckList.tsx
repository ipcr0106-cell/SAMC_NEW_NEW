"use client";

/**
 * HITL-1: 에스컬레이션 인지 체크리스트
 *
 * 참조: 계획/f1 재설계 계획/05_HITL_플로우_설계.md §4-2
 * - severity 아이콘 (info/warning/error)
 * - 체크박스 리스트
 * - "전체 확인" 단축 버튼
 * - 진행률 표시 (n/total)
 */

import { useState, useEffect } from "react";
import { Info, AlertTriangle, AlertCircle, CheckSquare } from "lucide-react";

export interface EscalationItem {
  /** 사유 코드 (예: "step_a_api_error:대두:DATA_GO_KR_TIMEOUT") */
  code: string;
  /** 사용자에게 보여줄 한글 메시지 */
  message: string;
  severity: "info" | "warning" | "error";
}

export interface EscalationAckListProps {
  caseId: string;
  items: readonly EscalationItem[];
  /** 체크된 사유 코드 목록. 모두 체크되면 HITL-2 진행 가능. */
  onChange: (acknowledgedCodes: readonly string[]) => void;
  disabled?: boolean;
}

const SEVERITY_ICON = {
  info: <Info className="h-4 w-4 text-blue-500" aria-label="정보" />,
  warning: <AlertTriangle className="h-4 w-4 text-amber-500" aria-label="경고" />,
  error: <AlertCircle className="h-4 w-4 text-red-500" aria-label="오류" />,
};

const SEVERITY_BORDER = {
  info: "border-blue-200 bg-blue-50",
  warning: "border-amber-200 bg-amber-50",
  error: "border-red-200 bg-red-50",
};

const SEVERITY_TEXT = {
  info: "text-blue-800",
  warning: "text-amber-800",
  error: "text-red-800",
};

export default function EscalationAckList({
  caseId: _caseId,
  items,
  onChange,
  disabled = false,
}: EscalationAckListProps) {
  const [checked, setChecked] = useState<Set<string>>(new Set());

  // items 변경 시 해제된 코드 정리
  useEffect(() => {
    const validCodes = new Set(items.map((i) => i.code));
    setChecked((prev) => {
      const next = new Set([...prev].filter((c) => validCodes.has(c)));
      return next;
    });
  }, [items]);

  // 변경 시 부모 통보
  useEffect(() => {
    onChange([...checked]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checked]);

  const toggle = (code: string) => {
    if (disabled) return;
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(code)) {
        next.delete(code);
      } else {
        next.add(code);
      }
      return next;
    });
  };

  const checkAll = () => {
    if (disabled) return;
    setChecked(new Set(items.map((i) => i.code)));
  };

  const total = items.length;
  const acked = checked.size;
  const allDone = total > 0 && acked === total;

  if (total === 0) {
    return (
      <section
        data-testid="escalation-ack-list"
        className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-500"
      >
        에스컬레이션 사유가 없습니다.
      </section>
    );
  }

  return (
    <section
      data-testid="escalation-ack-list"
      className="space-y-3 rounded-lg border border-gray-200 bg-white p-4"
    >
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-gray-900">에스컬레이션 인지 확인</h3>
          {/* 진행률 */}
          <span
            data-testid="ack-progress"
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
              allDone
                ? "bg-green-100 text-green-700"
                : "bg-gray-100 text-gray-600"
            }`}
          >
            {acked}/{total}
          </span>
        </div>

        {/* 전체 확인 단축 버튼 */}
        {!disabled && !allDone && (
          <button
            type="button"
            onClick={checkAll}
            data-testid="check-all-button"
            className="flex items-center gap-1 rounded border border-gray-300 bg-white px-2.5 py-1 text-xs text-gray-600 hover:bg-gray-50"
          >
            <CheckSquare className="h-3.5 w-3.5" />
            전체 확인
          </button>
        )}
      </div>

      <p className="text-xs text-gray-500">
        아래 항목을 모두 확인한 후 최종 판정(HITL-2)을 진행할 수 있습니다.
      </p>

      {/* 프로그레스 바 */}
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-200">
        <div
          className={`h-full rounded-full transition-all ${allDone ? "bg-green-500" : "bg-blue-500"}`}
          style={{ width: `${total > 0 ? (acked / total) * 100 : 0}%` }}
        />
      </div>

      {/* 체크박스 리스트 */}
      <div className="space-y-2">
        {items.map((item) => {
          const isChecked = checked.has(item.code);
          return (
            <label
              key={item.code}
              data-testid={`escalation-item-${item.code}`}
              className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors ${
                SEVERITY_BORDER[item.severity]
              } ${disabled ? "cursor-not-allowed opacity-60" : "hover:brightness-95"} ${
                isChecked ? "opacity-70" : ""
              }`}
            >
              <input
                type="checkbox"
                checked={isChecked}
                onChange={() => toggle(item.code)}
                disabled={disabled}
                className="mt-0.5 h-4 w-4 shrink-0 accent-blue-600"
              />
              <div className="flex min-w-0 flex-1 items-start gap-2">
                <span className="mt-0.5 shrink-0">
                  {SEVERITY_ICON[item.severity]}
                </span>
                <div className="min-w-0">
                  <p className={`text-sm ${SEVERITY_TEXT[item.severity]} ${isChecked ? "line-through" : ""}`}>
                    {item.message}
                  </p>
                  <p className="mt-0.5 text-[10px] font-mono text-gray-400">
                    {item.code}
                  </p>
                </div>
              </div>
            </label>
          );
        })}
      </div>

      {/* 완료 상태 표시 */}
      {allDone && (
        <div className="flex items-center gap-1.5 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-700">
          <CheckSquare className="h-4 w-4" />
          모든 에스컬레이션을 확인했습니다. 최종 판정을 진행할 수 있습니다.
        </div>
      )}
    </section>
  );
}
