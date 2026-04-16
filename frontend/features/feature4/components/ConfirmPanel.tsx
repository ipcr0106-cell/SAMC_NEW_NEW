/**
 * 기능4: 담당자 확인/수정 패널
 */

"use client";

interface ConfirmPanelProps {
  editReason: string;
  onEditReason: (reason: string) => void;
  onSave: () => void;
  onConfirm: () => void;
}

export default function ConfirmPanel({
  editReason,
  onEditReason,
  onSave,
  onConfirm,
}: ConfirmPanelProps) {
  return (
    <div className="border rounded-lg p-4 space-y-3 bg-gray-50">
      <p className="text-sm font-medium text-gray-700">담당자 검토</p>

      <div>
        <label className="block text-xs text-gray-500 mb-1">
          수정 사유 (AI 결과 수정 시 필수)
        </label>
        <textarea
          value={editReason}
          onChange={(e) => onEditReason(e.target.value)}
          placeholder="예: 원재료 표기가 서류와 동일하여 불일치 항목 수정"
          rows={2}
          className="w-full text-sm border rounded px-3 py-2 resize-none focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
      </div>

      <div className="flex gap-2">
        <button
          onClick={onSave}
          className="px-4 py-2 text-sm rounded border border-gray-300 bg-white hover:bg-gray-50"
        >
          수정 저장
        </button>
        <button
          onClick={onConfirm}
          className="px-4 py-2 text-sm rounded bg-blue-600 text-white hover:bg-blue-700"
        >
          확인 완료 → 기능5로 진행
        </button>
      </div>
    </div>
  );
}
