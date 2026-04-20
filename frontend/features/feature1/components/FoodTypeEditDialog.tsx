/**
 * FoodTypeEditDialog — F2 식품유형 수정 다이얼로그
 *
 * F1 ImportCheckPage 내에서 FoodTypeSection 수정 버튼 클릭 시 열림.
 * PATCH /api/v1/cases/{caseId}/pipeline/feature/2 를 통해 저장.
 *
 * f1f2 병합 통합 (samcbc Sub-phase 2 대응).
 */

"use client";

import { useState } from "react";
import Input from "@/components/ui/Input";
import Toggle from "@/components/ui/Toggle";
import Button from "@/components/ui/Button";
import { patchFeature2 } from "@/lib/api";
import type { FoodTypeHierarchy } from "@/types/pipeline";

interface FoodTypeEditDialogProps {
  caseId: string;
  initial: FoodTypeHierarchy;
  onClose: () => void;
  onSaved: (updated: FoodTypeHierarchy) => void;
}

export default function FoodTypeEditDialog({
  caseId,
  initial,
  onClose,
  onSaved,
}: FoodTypeEditDialogProps) {
  const [form, setForm] = useState<FoodTypeHierarchy>({ ...initial });
  const [editReason, setEditReason] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const set = <K extends keyof FoodTypeHierarchy>(key: K, value: FoodTypeHierarchy[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    if (!editReason.trim()) {
      setErrorMsg("수정 사유를 입력하세요.");
      return;
    }
    setIsSaving(true);
    setErrorMsg(null);
    try {
      await patchFeature2(caseId, {
        final_result: form as unknown as Record<string, unknown>,
        edit_reason: editReason.trim(),
      });
      onSaved(form);
      onClose();
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "저장 중 오류가 발생했습니다.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    >
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg space-y-4">
        <h3 className="text-base font-semibold text-slate-900">식품유형 수정</h3>

        <div className="space-y-3">
          <Input
            label="대분류"
            value={form.category_name ?? ""}
            onChange={(e) => set("category_name", e.target.value || null)}
            placeholder="예: 주류"
          />
          <Input
            label="중분류"
            value={form.subcategory_name ?? ""}
            onChange={(e) => set("subcategory_name", e.target.value || null)}
            placeholder="예: 증류주"
          />
          <Input
            label="소분류"
            value={form.food_type ?? ""}
            onChange={(e) => set("food_type", e.target.value || null)}
            placeholder="예: 일반증류주"
          />
          <Input
            label="근거 법령"
            value={form.law_ref ?? ""}
            onChange={(e) => set("law_ref", e.target.value || null)}
            placeholder="예: 주세법 시행령 제3조"
          />
          <div>
            <label className="ds-label block mb-1">판정 근거 설명</label>
            <textarea
              value={form.reason ?? ""}
              onChange={(e) => set("reason", e.target.value || null)}
              rows={3}
              placeholder="분류 근거를 입력하세요."
              className="ds-input px-3.5 py-2.5 w-full resize-none"
            />
          </div>
          <Toggle
            label="주류 여부"
            checked={form.is_alcohol ?? false}
            onChange={(v) => set("is_alcohol", v)}
            description="주류로 분류되면 주류 규정이 적용됩니다."
          />
          <Input
            label="수정 사유"
            value={editReason}
            onChange={(e) => setEditReason(e.target.value)}
            placeholder="수정 이유를 입력하세요."
            error={errorMsg ?? undefined}
          />
        </div>

        {errorMsg && (
          <p className="text-xs text-red-600">{errorMsg}</p>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" size="md" onClick={onClose} disabled={isSaving}>
            취소
          </Button>
          <Button variant="primary" size="md" onClick={handleSave} disabled={isSaving}>
            {isSaving ? "저장 중..." : "저장"}
          </Button>
        </div>
      </div>
    </div>
  );
}
