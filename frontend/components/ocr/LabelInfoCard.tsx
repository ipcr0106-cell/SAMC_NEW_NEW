"use client";

import { useState } from "react";
import { Image, Plus, X, AlertTriangle } from "lucide-react";
import Card from "@/components/ui/Card";

interface LabelInfoCardProps {
  labelTexts: string[];
  onLabelTextsChange: (texts: string[]) => void;
  designDescription: string;
  onDesignDescriptionChange: (desc: string) => void;
  warnings: string[];
  onWarningsChange: (warnings: string[]) => void;
}

export default function LabelInfoCard({
  labelTexts,
  onLabelTextsChange,
  designDescription,
  onDesignDescriptionChange,
  warnings,
  onWarningsChange,
}: LabelInfoCardProps) {
  const [newText, setNewText] = useState("");
  const [newWarning, setNewWarning] = useState("");

  const addLabelText = () => {
    if (!newText.trim()) return;
    onLabelTextsChange([...labelTexts, newText.trim()]);
    setNewText("");
  };

  const removeLabelText = (index: number) => {
    onLabelTextsChange(labelTexts.filter((_, i) => i !== index));
  };

  const addWarning = () => {
    if (!newWarning.trim()) return;
    onWarningsChange([...warnings, newWarning.trim()]);
    setNewWarning("");
  };

  const removeWarning = (index: number) => {
    onWarningsChange(warnings.filter((_, i) => i !== index));
  };

  return (
    <Card padding="md">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-7 h-7 bg-amber-50 rounded-lg flex items-center justify-center">
          <Image size={14} className="text-amber-600" />
        </div>
        <h3 className="text-sm font-bold text-slate-900">수출국 라벨 정보</h3>
      </div>

      {/* 디자인 설명 */}
      <div className="mb-4">
        <label className="block text-xs font-medium text-slate-500 mb-1.5">
          라벨 디자인 설명 (그림, 색상, 레이아웃)
        </label>
        <textarea
          value={designDescription}
          onChange={(e) => onDesignDescriptionChange(e.target.value)}
          placeholder="라벨의 전체적인 디자인, 색상, 그림 요소 등을 기술합니다..."
          className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400 resize-none"
          rows={3}
        />
      </div>

      {/* 라벨 문구 목록 */}
      <div className="mb-4">
        <label className="block text-xs font-medium text-slate-500 mb-1.5">
          라벨 추출 문구
        </label>
        <div className="space-y-1.5 mb-2">
          {labelTexts.map((text, idx) => (
            <div
              key={idx}
              className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2"
            >
              <span className="flex-1 text-xs text-slate-700">{text}</span>
              <button
                onClick={() => removeLabelText(idx)}
                className="text-slate-400 hover:text-red-500 transition-colors shrink-0"
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={newText}
            onChange={(e) => setNewText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addLabelText()}
            placeholder="새 문구 추가..."
            className="flex-1 px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400"
          />
          <button
            onClick={addLabelText}
            className="px-2.5 py-1.5 bg-blue-50 text-blue-600 rounded-lg hover:bg-blue-100 transition-colors"
          >
            <Plus size={14} />
          </button>
        </div>
      </div>

      {/* 경고문구 */}
      <div>
        <label className="flex items-center gap-1.5 text-xs font-medium text-slate-500 mb-1.5">
          <AlertTriangle size={12} className="text-amber-500" />
          경고문구 / 주의사항
        </label>
        <div className="space-y-1.5 mb-2">
          {warnings.map((w, idx) => (
            <div
              key={idx}
              className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2"
            >
              <span className="flex-1 text-xs text-amber-800">{w}</span>
              <button
                onClick={() => removeWarning(idx)}
                className="text-amber-400 hover:text-red-500 transition-colors shrink-0"
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={newWarning}
            onChange={(e) => setNewWarning(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addWarning()}
            placeholder="새 경고문구 추가..."
            className="flex-1 px-3 py-1.5 bg-white border border-amber-200 rounded-lg text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-400"
          />
          <button
            onClick={addWarning}
            className="px-2.5 py-1.5 bg-amber-50 text-amber-600 rounded-lg hover:bg-amber-100 transition-colors"
          >
            <Plus size={14} />
          </button>
        </div>
      </div>
    </Card>
  );
}
