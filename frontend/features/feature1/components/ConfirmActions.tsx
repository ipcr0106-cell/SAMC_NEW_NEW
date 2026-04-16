/**
 * 저장 + 확인 완료 + PDF 다운로드 액션 버튼.
 */

"use client";

interface Props {
  isSaving: boolean;
  isConfirming: boolean;
  isConfirmed: boolean;
  canConfirm: boolean;
  onSave: () => void;
  onConfirm: () => void;
  onDownloadPdf?: () => void;
}

export default function ConfirmActions({
  isSaving,
  isConfirming,
  isConfirmed,
  canConfirm,
  onSave,
  onConfirm,
  onDownloadPdf,
}: Props) {
  return (
    <div className="flex items-center justify-end gap-3 rounded-lg border border-gray-200 bg-gray-50 p-4">
      {onDownloadPdf && (
        <button
          type="button"
          onClick={onDownloadPdf}
          className="rounded border border-gray-300 bg-white px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
        >
          레포트 PDF 다운로드
        </button>
      )}
      <button
        type="button"
        onClick={onSave}
        disabled={isSaving || isConfirmed}
        className="rounded border border-blue-500 bg-white px-4 py-2 text-sm text-blue-600 hover:bg-blue-50 disabled:opacity-50"
      >
        {isSaving ? "저장 중..." : "수정 저장"}
      </button>
      <button
        type="button"
        onClick={onConfirm}
        disabled={!canConfirm || isConfirming || isConfirmed}
        className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {isConfirmed
          ? "확인 완료됨"
          : isConfirming
            ? "처리 중..."
            : "판정 확정 → 다음 단계"}
      </button>
    </div>
  );
}
