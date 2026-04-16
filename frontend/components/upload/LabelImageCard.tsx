"use client";

import { useState } from "react";
import { ImageIcon, Loader2, ChevronDown, ChevronUp, CheckSquare, Square } from "lucide-react";
import type { LabelImageData } from "@/lib/api";

interface LabelImageCardProps {
  caseId: string;
  images: LabelImageData[];
  loading: boolean;
  /** true이면 각 이미지에 체크박스 표시 */
  selectable?: boolean;
  selectedIds?: string[];
  onSelectionChange?: (ids: string[]) => void;
}

const FIELD_LABELS: { key: keyof LabelImageData; label: string }[] = [
  { key: "label_product_name",   label: "제품명" },
  { key: "label_ingredients",    label: "원재료" },
  { key: "label_content_volume", label: "내용량" },
  { key: "label_origin",         label: "원산지" },
  { key: "label_manufacturer",   label: "제조사" },
  { key: "label_case_number",    label: "케이스 넘버" },
];

function SingleLabelImage({
  img,
  index,
  selectable,
  selected,
  onToggle,
}: {
  img: LabelImageData;
  index: number;
  selectable?: boolean;
  selected?: boolean;
  onToggle?: () => void;
}) {
  const [expanded, setExpanded] = useState(index === 0);
  const [imgError, setImgError] = useState(false);

  const pageLabel =
    img.image_index !== undefined && img.image_index !== null
      ? ` (${img.image_index + 1}번째)`
      : "";
  const hasAnyText = FIELD_LABELS.some((f) => img[f.key]);
  const url = img.signed_url;

  return (
    <div
      className={`border rounded-xl overflow-hidden transition-all ${
        selectable
          ? selected
            ? "border-blue-300 ring-1 ring-blue-200"
            : "border-slate-200 opacity-55"
          : "border-slate-200"
      }`}
    >
      <div className="flex items-center bg-slate-50 hover:bg-slate-100 transition-colors">
        {/* 체크박스 (selectable 모드) */}
        {selectable && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onToggle?.(); }}
            className={`pl-3 py-2 shrink-0 transition-colors ${
              selected ? "text-blue-500" : "text-slate-300 hover:text-slate-400"
            }`}
          >
            {selected ? <CheckSquare size={15} /> : <Square size={15} />}
          </button>
        )}
        {/* 아코디언 토글 */}
        <button
          type="button"
          onClick={() => setExpanded((p) => !p)}
          className="flex-1 flex items-center justify-between px-3 py-2 text-left"
        >
          <span className="text-xs font-semibold text-slate-600">
            이미지 {index + 1}{pageLabel}
          </span>
          {expanded ? (
            <ChevronUp size={14} className="text-slate-400" />
          ) : (
            <ChevronDown size={14} className="text-slate-400" />
          )}
        </button>
      </div>

      {expanded && (
        <div className="p-3 flex gap-3">
          {/* 크롭 이미지 */}
          <div className="shrink-0 w-[110px] h-[110px] bg-slate-100 rounded-lg overflow-hidden flex items-center justify-center border border-slate-200">
            {url && !imgError ? (
              <img
                src={url}
                alt={`라벨 제품 이미지 ${index + 1}`}
                className="w-full h-full object-contain"
                onError={() => setImgError(true)}
              />
            ) : (
              <div className="flex flex-col items-center gap-1 text-slate-400">
                <ImageIcon size={20} />
                <span className="text-[10px]">미리보기 없음</span>
              </div>
            )}
          </div>

          {/* 텍스트 필드 */}
          <div className="flex-1 min-w-0 space-y-1.5">
            {hasAnyText ? (
              FIELD_LABELS.map(({ key, label }) => {
                const value = img[key] as string | null | undefined;
                if (!value) return null;
                return (
                  <div key={key} className="flex gap-1.5 items-start">
                    <span className="text-[10px] font-semibold text-slate-400 w-[56px] shrink-0 pt-0.5">
                      {label}
                    </span>
                    <span className="text-[11px] text-slate-700 leading-snug break-all">
                      {value}
                    </span>
                  </div>
                );
              })
            ) : (
              <p className="text-xs text-slate-400">추출된 텍스트 없음</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function LabelImageCard({
  images,
  loading,
  selectable,
  selectedIds = [],
  onSelectionChange,
}: LabelImageCardProps) {
  if (!loading && images.length === 0) return null;

  const selectedSet = new Set(selectedIds);
  const allSelected = images.length > 0 && images.every((img) => selectedSet.has(img.id));
  const noneSelected = images.every((img) => !selectedSet.has(img.id));

  const toggle = (id: string) => {
    if (!onSelectionChange) return;
    if (selectedSet.has(id)) {
      onSelectionChange(selectedIds.filter((sid) => sid !== id));
    } else {
      onSelectionChange([...selectedIds, id]);
    }
  };

  const selectAll = () => onSelectionChange?.(images.map((img) => img.id));
  const clearAll  = () => onSelectionChange?.([]);

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm">
      <div className="flex items-center gap-2.5 mb-3">
        <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-violet-50 text-violet-500">
          <ImageIcon size={14} />
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-bold text-slate-900">라벨 제품 이미지</h4>
          <p className="text-[11px] text-slate-400">
            {selectable
              ? "체크한 이미지를 내보내기·F4에 사용합니다"
              : "Vision AI가 자동 추출한 제품 사진 및 표시사항"}
          </p>
        </div>

        {/* 카운트 / 전체선택 버튼 */}
        <div className="flex items-center gap-1.5 shrink-0">
          {selectable && !loading && images.length > 0 && (
            <>
              {!allSelected && (
                <button
                  type="button"
                  onClick={selectAll}
                  className="text-[10px] font-semibold text-blue-500 hover:text-blue-700 transition-colors"
                >
                  전체선택
                </button>
              )}
              {!noneSelected && !allSelected && (
                <span className="text-[10px] text-slate-300">|</span>
              )}
              {!noneSelected && (
                <button
                  type="button"
                  onClick={clearAll}
                  className="text-[10px] font-semibold text-slate-400 hover:text-slate-600 transition-colors"
                >
                  전체해제
                </button>
              )}
              <span
                className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ml-1 ${
                  selectedIds.length > 0
                    ? "bg-blue-100 text-blue-600"
                    : "bg-slate-100 text-slate-400"
                }`}
              >
                {selectedIds.length}/{images.length}
              </span>
            </>
          )}
          {!selectable && !loading && images.length > 0 && (
            <span className="text-[10px] font-semibold bg-violet-100 text-violet-600 px-2 py-0.5 rounded-full">
              {images.length}개
            </span>
          )}
        </div>
      </div>

      {loading && (
        <div className="flex items-center gap-2 py-3 text-slate-500">
          <Loader2 size={14} className="animate-spin text-violet-400" />
          <span className="text-xs">Vision AI가 제품 이미지를 분석하고 있습니다...</span>
        </div>
      )}

      {!loading && images.length > 0 && (
        <div className="space-y-2">
          {images.map((img, i) => (
            <SingleLabelImage
              key={img.id}
              img={img}
              index={i}
              selectable={selectable}
              selected={selectable ? selectedSet.has(img.id) : undefined}
              onToggle={selectable ? () => toggle(img.id) : undefined}
            />
          ))}
        </div>
      )}
    </div>
  );
}
