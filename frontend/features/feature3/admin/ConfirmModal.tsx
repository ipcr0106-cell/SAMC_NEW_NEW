"use client";

import { useEffect, useRef } from "react";
import { AlertTriangle } from "lucide-react";

interface ConfirmModalProps {
  open: boolean;
  title?: string;
  subtitle?: string;
  /** Diff 요약 표시 (선택). 없으면 summary 박스 숨김. */
  summary?: { added: number; modified: number; deleted: number };
  featureLabel?: string;
  /** 커스텀 본문 (없으면 기본 안내 문구). */
  bodyText?: React.ReactNode;
  cancelLabel?: string;
  confirmLabel?: string;
  busyLabel?: string;
  onCancel: () => void;
  onConfirm: () => void;
  applying?: boolean;
}

export function ConfirmModal({
  open,
  title = "최종 확인",
  subtitle = "이 단계를 지나면 기존 자료가 새 내용으로 바뀝니다",
  summary,
  featureLabel = "수입필요서류 안내",
  bodyText,
  cancelLabel = "다시 확인하기",
  confirmLabel = "네, 확인했습니다",
  busyLabel = "반영 중...",
  onCancel,
  onConfirm,
  applying = false,
}: ConfirmModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const confirmBtnRef = useRef<HTMLButtonElement>(null);

  // ESC → cancel, 열릴 때 confirm 버튼에 포커스
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        if (!applying) onCancel();
      }
      // 간단한 포커스 트랩
      if (e.key === "Tab" && dialogRef.current) {
        const focusables = dialogRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", handler);
    // 포커스는 "확인" 버튼에 — 실수 클릭 방지 위해 기본 focus 는 cancel 이 낫지만,
    // 일반적인 accessibility 가이드는 safest action 에 두는 것. 여기서는 cancel.
    setTimeout(() => {
      const cancelBtn = dialogRef.current?.querySelector<HTMLButtonElement>(
        'button[data-confirm-cancel="true"]',
      );
      cancelBtn?.focus();
    }, 0);
    return () => window.removeEventListener("keydown", handler);
  }, [open, applying, onCancel]);

  if (!open) return null;

  const defaultBody = (
    <>
      <p>
        이 작업을 실행하면 <b>&apos;{featureLabel}&apos;</b> 기능의 기존 자료가 모두
        새 내용으로 바뀝니다.
      </p>
      <p className="text-slate-600">
        걱정 마세요 — 기존 자료는 자동으로 백업되므로, 문제가 생기면 언제든
        이전 상태로 되돌릴 수 있습니다.
      </p>
      <p className="text-slate-900 font-semibold">
        파싱된 내용이 원본 법령과 일치하는지 다시 한 번 확인해 주세요.
      </p>
    </>
  );

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
      role="presentation"
      onClick={(e) => {
        // 백드롭 클릭 시 닫기 (applying 중엔 불가)
        if (e.target === e.currentTarget && !applying) onCancel();
      }}
    >
      <div
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="f3-confirm-title"
        aria-describedby="f3-confirm-desc"
        className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6"
      >
        <div className="flex items-start gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
            <AlertTriangle className="w-5 h-5 text-amber-600" aria-hidden />
          </div>
          <div>
            <h2 id="f3-confirm-title" className="text-[18px] font-bold text-slate-900">
              {title}
            </h2>
            <p className="text-[13px] text-slate-500 mt-0.5">{subtitle}</p>
          </div>
        </div>

        <div
          id="f3-confirm-desc"
          className="bg-slate-50 rounded-lg p-4 mb-4 text-[14px] text-slate-700 leading-relaxed space-y-3"
        >
          {bodyText ?? defaultBody}
        </div>

        {summary && (
          <div className="bg-white border border-slate-200 rounded-lg p-3 mb-5 text-[13px] text-slate-700">
            <div className="font-semibold mb-2 text-slate-900">변경 요약</div>
            <div className="flex gap-4">
              <div>
                <span className="text-emerald-600 font-bold">{summary.added}</span>
                <span className="text-slate-500 ml-1">건 추가</span>
              </div>
              <div>
                <span className="text-blue-600 font-bold">{summary.modified}</span>
                <span className="text-slate-500 ml-1">건 수정</span>
              </div>
              <div>
                <span className="text-rose-600 font-bold">{summary.deleted}</span>
                <span className="text-slate-500 ml-1">건 삭제</span>
              </div>
            </div>
          </div>
        )}

        <div className="flex gap-3">
          <button
            onClick={onCancel}
            disabled={applying}
            data-confirm-cancel="true"
            className="flex-1 h-11 rounded-lg border border-slate-300 bg-white text-slate-700 font-semibold hover:bg-slate-50 transition-colors disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-slate-400"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmBtnRef}
            onClick={onConfirm}
            disabled={applying}
            className="flex-1 h-11 rounded-lg bg-slate-900 text-white font-semibold hover:bg-slate-800 transition-colors disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-slate-400"
          >
            {applying ? busyLabel : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
