"use client";

import { useState, useMemo } from "react";
import { Cog, Globe2, Search, CheckSquare, Square, ChevronDown, ChevronUp } from "lucide-react";
import Card from "@/components/ui/Card";
import Input from "@/components/ui/Input";
import Toggle from "@/components/ui/Toggle";
import {
  PROCESS_CODE_GROUPS,
  getProcessCodeLabel,
} from "@/lib/process-codes";

interface ProcessCodeReason {
  code: string;
  reason: string;
}

export interface ProcessCodeCandidate {
  code: string;
  reason: string;
  is_recommended: boolean;
  confusion_note?: string;
}

interface ProcessCodeCardProps {
  processCodes: string[];
  onProcessCodesChange: (codes: string[]) => void;
  exportCountry: string;
  onExportCountryChange: (country: string) => void;
  isOem: boolean;
  onOemChange: (isOem: boolean) => void;
  /** OCR에서 읽은 공정 원문 (표시용) */
  rawProcessText?: string;
  /** AI가 각 공정 코드를 선택한 근거 목록 (하위 호환) */
  processCodeReasons?: ProcessCodeReason[];
  /** AI 공정 코드 후보 (추천 + 유사 코드) */
  processCodeCandidates?: ProcessCodeCandidate[];
}

/** 추천 코드 섹션 — 체크박스로 선택/해제 */
function CandidateList({
  candidates,
  processCodes,
  onProcessCodesChange,
}: {
  candidates: ProcessCodeCandidate[];
  processCodes: string[];
  onProcessCodesChange: (codes: string[]) => void;
}) {
  const [showSimilar, setShowSimilar] = useState(true);

  const recommended = candidates.filter((c) => c.is_recommended);
  const similar = candidates.filter((c) => !c.is_recommended);

  const toggle = (code: string) => {
    if (processCodes.includes(code)) {
      onProcessCodesChange(processCodes.filter((c) => c !== code));
    } else {
      onProcessCodesChange([...processCodes, code]);
    }
  };

  return (
    <div className="space-y-2">
      {/* 추천 코드 */}
      {recommended.length > 0 && (
        <div className="space-y-1.5">
          {recommended.map((cand) => {
            const checked = processCodes.includes(cand.code);
            return (
              <button
                key={cand.code}
                type="button"
                onClick={() => toggle(cand.code)}
                className={`w-full text-left flex items-start gap-2.5 p-2.5 rounded-xl border transition-all ${
                  checked
                    ? "bg-blue-50 border-blue-200"
                    : "bg-white border-slate-200 hover:border-slate-300"
                }`}
              >
                <span className={`mt-0.5 shrink-0 ${checked ? "text-blue-500" : "text-slate-300"}`}>
                  {checked ? <CheckSquare size={15} /> : <Square size={15} />}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span
                      className={`text-[11px] font-bold font-mono px-1.5 py-0.5 rounded ${
                        checked
                          ? "bg-blue-100 text-blue-700"
                          : "bg-slate-100 text-slate-500"
                      }`}
                    >
                      {cand.code}
                    </span>
                    <span className={`text-xs font-semibold ${checked ? "text-blue-800" : "text-slate-600"}`}>
                      {getProcessCodeLabel(cand.code).replace(/^\d+\s*[-–]\s*/, "")}
                    </span>
                    <span className="text-[10px] font-medium bg-emerald-100 text-emerald-600 px-1.5 py-0.5 rounded-full">
                      AI 추천
                    </span>
                  </div>
                  {cand.reason && (
                    <p className="text-[11px] text-slate-500 mt-0.5 leading-snug">
                      ↳ {cand.reason}
                    </p>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* 유사/혼동 코드 */}
      {similar.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setShowSimilar((p) => !p)}
            className="flex items-center gap-1.5 text-[11px] font-semibold text-amber-500 hover:text-amber-700 transition-colors py-1 px-2 bg-amber-50 rounded-lg w-full"
          >
            {showSimilar ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            <span>혼동 가능 유사 코드 {similar.length}개 — 직접 선택 가능</span>
          </button>

          {showSimilar && (
            <div className="mt-1.5 space-y-1.5">
              {similar.map((cand) => {
                const checked = processCodes.includes(cand.code);
                return (
                  <button
                    key={cand.code}
                    type="button"
                    onClick={() => toggle(cand.code)}
                    className={`w-full text-left flex items-start gap-2.5 p-2.5 rounded-xl border transition-all ${
                      checked
                        ? "bg-amber-50 border-amber-200"
                        : "bg-slate-50 border-slate-200 hover:border-amber-200 hover:bg-amber-50/50"
                    }`}
                  >
                    <span className={`mt-0.5 shrink-0 ${checked ? "text-amber-500" : "text-slate-300"}`}>
                      {checked ? <CheckSquare size={15} /> : <Square size={15} />}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span
                          className={`text-[11px] font-bold font-mono px-1.5 py-0.5 rounded ${
                            checked
                              ? "bg-amber-100 text-amber-700"
                              : "bg-slate-200 text-slate-500"
                          }`}
                        >
                          {cand.code}
                        </span>
                        <span className={`text-xs font-semibold ${checked ? "text-amber-800" : "text-slate-500"}`}>
                          {getProcessCodeLabel(cand.code).replace(/^\d+\s*[-–]\s*/, "")}
                        </span>
                        <span className="text-[10px] font-medium bg-slate-200 text-slate-500 px-1.5 py-0.5 rounded-full">
                          유사 코드
                        </span>
                      </div>
                      {cand.reason && (
                        <p className="text-[11px] text-slate-500 mt-0.5 leading-snug">
                          ↳ {cand.reason}
                        </p>
                      )}
                      {cand.confusion_note && (
                        <p className="text-[11px] text-amber-600 mt-0.5 leading-snug bg-amber-50 rounded px-1.5 py-0.5">
                          ⚠ {cand.confusion_note}
                        </p>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ProcessCodeCard({
  processCodes,
  onProcessCodesChange,
  exportCountry,
  onExportCountryChange,
  isOem,
  onOemChange,
  rawProcessText,
  processCodeReasons,
  processCodeCandidates,
}: ProcessCodeCardProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [dropdownOpen, setDropdownOpen] = useState(false);

  /** 검색어 기반 필터링된 코드 그룹 */
  const filteredGroups = useMemo(() => {
    if (!searchQuery.trim()) return PROCESS_CODE_GROUPS;
    const q = searchQuery.toLowerCase();
    return PROCESS_CODE_GROUPS.map((group) => ({
      ...group,
      codes: group.codes.filter(
        (c) =>
          c.value.toLowerCase().includes(q) ||
          c.label.toLowerCase().includes(q)
      ),
    })).filter((group) => group.codes.length > 0);
  }, [searchQuery]);

  const addCode = (code: string) => {
    if (!processCodes.includes(code)) {
      onProcessCodesChange([...processCodes, code]);
    }
    setSearchQuery("");
    setDropdownOpen(false);
  };

  const removeCode = (code: string) => {
    onProcessCodesChange(processCodes.filter((c) => c !== code));
  };

  // candidates가 있으면 candidate UI, 없으면 기존 tag UI
  const hasCandidates = processCodeCandidates && processCodeCandidates.length > 0;

  return (
    <Card>
      {/* 헤더 */}
      <div className="flex items-center gap-2.5 mb-5">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-amber-50 text-amber-600">
          <Cog size={16} />
        </div>
        <h3 className="text-sm font-bold text-slate-900">
          제조공정 및 라벨 정보
        </h3>
      </div>

      <div className="space-y-5">
        {/* OCR 원문 공정 텍스트 */}
        {rawProcessText && (
          <div>
            <label className="text-sm font-medium text-slate-700 mb-2 block">
              OCR 추출 공정 원문
            </label>
            <div className="p-3 bg-slate-50 rounded-xl text-xs text-slate-600 leading-relaxed max-h-24 overflow-y-auto">
              {rawProcessText}
            </div>
          </div>
        )}

        {/* 공정 코드 섹션 */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium text-slate-700">
              공정 코드 (AI 자동 변환)
            </label>
            {processCodes.length > 0 && (
              <span className="text-[10px] font-semibold bg-blue-100 text-blue-600 px-2 py-0.5 rounded-full">
                {processCodes.length}개 선택됨
              </span>
            )}
          </div>

          {/* AI 후보 코드 목록 (체크박스 UI) */}
          {hasCandidates ? (
            <CandidateList
              candidates={processCodeCandidates!}
              processCodes={processCodes}
              onProcessCodesChange={onProcessCodesChange}
            />
          ) : (
            /* 후보 없을 때 기존 태그 UI (하위 호환) */
            <div className="flex flex-col gap-2 mb-3 min-h-[36px] p-3 bg-slate-50 rounded-xl">
              {processCodes.length === 0 ? (
                <span className="text-xs text-slate-400">
                  공정 코드가 없습니다. 아래에서 검색하여 추가하세요.
                </span>
              ) : (
                processCodes.map((code) => {
                  const reasonObj = processCodeReasons?.find((r) => r.code === code);
                  return (
                    <div key={code} className="flex flex-col gap-0.5">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[11px] font-bold font-mono bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">
                          {code}
                        </span>
                        <span className="text-xs text-slate-700">
                          {getProcessCodeLabel(code).replace(/^\d+\s*[-–]\s*/, "")}
                        </span>
                        <button
                          type="button"
                          onClick={() => removeCode(code)}
                          className="ml-auto text-[10px] text-slate-400 hover:text-red-400 transition-colors"
                        >
                          ✕
                        </button>
                      </div>
                      {reasonObj?.reason && (
                        <p className="text-[11px] text-slate-500 leading-snug pl-1">
                          ↳ {reasonObj.reason}
                        </p>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          )}

          {/* 수동 검색 추가 (후보 UI에서도 보완 추가 가능) */}
          <div className={`relative ${hasCandidates ? "mt-3" : ""}`}>
            <p className="text-[11px] text-slate-400 mb-1.5">
              {hasCandidates ? "목록에 없는 코드 직접 추가" : ""}
            </p>
            <div className="relative">
              <Search
                size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
              />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setDropdownOpen(true);
                }}
                onFocus={() => setDropdownOpen(true)}
                placeholder="공정명 또는 코드로 검색... (예: 살균, 01, 발효)"
                className="w-full pl-9 pr-4 py-2.5 bg-white border border-slate-200 rounded-xl text-sm hover:border-slate-300 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none transition-all"
              />
            </div>

            {/* 드롭다운 */}
            {dropdownOpen && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setDropdownOpen(false)}
                />
                <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-xl shadow-lg z-20 max-h-64 overflow-y-auto">
                  {filteredGroups.length === 0 ? (
                    <div className="p-4 text-center text-xs text-slate-400">
                      일치하는 공정 코드가 없습니다
                    </div>
                  ) : (
                    filteredGroups.map((group) => (
                      <div key={group.category}>
                        <div className="px-3 py-1.5 bg-slate-50 text-[10px] font-bold text-slate-400 uppercase tracking-wider sticky top-0">
                          {group.category}
                        </div>
                        {group.codes.map((code) => {
                          const alreadyAdded = processCodes.includes(code.value);
                          return (
                            <button
                              key={code.value}
                              onClick={() => !alreadyAdded && addCode(code.value)}
                              disabled={alreadyAdded}
                              className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                                alreadyAdded
                                  ? "text-slate-300 cursor-default bg-slate-50"
                                  : "text-slate-700 hover:bg-blue-50 hover:text-blue-700 cursor-pointer"
                              }`}
                            >
                              <span className="font-mono text-xs mr-2 text-slate-400">
                                {code.value}
                              </span>
                              {code.label.split(" - ")[1]}
                              {alreadyAdded && (
                                <span className="ml-2 text-[10px] text-blue-400 font-medium">
                                  추가됨
                                </span>
                              )}
                            </button>
                          );
                        })}
                      </div>
                    ))
                  )}
                </div>
              </>
            )}
          </div>
        </div>

        {/* 구분선 */}
        <div className="border-t border-slate-100" />

        {/* 수출국 / OEM */}
        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-slate-700 flex items-center gap-1.5">
              <Globe2 size={14} className="text-slate-400" />
              수출국
            </label>
            <Input
              value={exportCountry}
              onChange={(e) => onExportCountryChange(e.target.value)}
              placeholder="예: 미국, 일본"
            />
          </div>
          <div className="flex flex-col justify-end">
            <Toggle
              label="OEM 여부"
              description="위탁제조(OEM) 수입 제품"
              checked={isOem}
              onChange={onOemChange}
            />
          </div>
        </div>
      </div>
    </Card>
  );
}
