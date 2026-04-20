"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import { Cog, Globe2, Search, CheckSquare, Square, ChevronDown, ChevronUp, Plus, X } from "lucide-react";
import Card from "@/components/ui/Card";
import Input from "@/components/ui/Input";
import Toggle from "@/components/ui/Toggle";
import {
  PROCESS_CODE_GROUPS,
  getProcessCodeLabel,
} from "@/lib/process-codes";
import {
  JAPAN_PREFECTURES,
  prefectureToCode,
  codeToSelectedName,
} from "@/lib/japan-prefectures";

interface ProcessCodeReason {
  code: string;
  name?: string;
  reason: string;
}

export interface ProcessCodeCandidate {
  code: string;
  name?: string;
  reason: string;
  is_recommended: boolean;
  confusion_note?: string;
}

export interface ProcessStep {
  step_number: number;
  step_name_original: string;
  step_name_ko: string;
  recommended_code: string;
  recommended_code_name: string;
  recommended_reason: string;
  similar_codes: ProcessCodeCandidate[];
}

interface ProcessCodeCardProps {
  processCodes: string[];
  onProcessCodesChange: (codes: string[]) => void;
  exportCountry: string;
  onExportCountryChange: (country: string) => void;
  isOem: boolean;
  onOemChange: (isOem: boolean) => void;
  /** 일본산일 때 F3 전달용 도·현 코드 (예: "후쿠시마" 또는 "일본34개도부현") */
  japanPrefectureCode?: string;
  onJapanPrefectureCodeChange?: (code: string) => void;
  /** OCR에서 읽은 공정 원문 (표시용) */
  rawProcessText?: string;
  /** AI가 각 공정 코드를 선택한 근거 목록 (하위 호환) */
  processCodeReasons?: ProcessCodeReason[];
  /** AI 공정 코드 후보 (추천 + 유사 코드) — process_steps 없을 때 fallback */
  processCodeCandidates?: ProcessCodeCandidate[];
  /** 단계별 공정 분석 결과 (우선 사용) */
  processSteps?: ProcessStep[];
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

/** 단계 내 코드 검색 인라인 드롭다운 */
function StepCodeSearch({
  processCodes,
  onAdd,
  onClose,
}: {
  processCodes: string[];
  onAdd: (code: string) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const filtered = useMemo(() => {
    if (!query.trim()) return PROCESS_CODE_GROUPS;
    const q = query.toLowerCase();
    return PROCESS_CODE_GROUPS.map((g) => ({
      ...g,
      codes: g.codes.filter(
        (c) => c.value.toLowerCase().includes(q) || c.label.toLowerCase().includes(q)
      ),
    })).filter((g) => g.codes.length > 0);
  }, [query]);

  return (
    <div className="mt-1.5 border border-blue-200 rounded-xl bg-white shadow-md overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-100">
        <Search size={13} className="text-slate-400 shrink-0" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="공정명 또는 코드 검색... (예: 살균, 01)"
          className="flex-1 text-xs outline-none placeholder-slate-400"
        />
        <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors">
          <X size={13} />
        </button>
      </div>
      <div className="max-h-48 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="p-3 text-center text-xs text-slate-400">일치하는 코드 없음</div>
        ) : (
          filtered.map((group) => (
            <div key={group.category}>
              <div className="px-3 py-1 bg-slate-50 text-[10px] font-bold text-slate-400 uppercase tracking-wider sticky top-0">
                {group.category}
              </div>
              {group.codes.map((code) => {
                const added = processCodes.includes(code.value);
                return (
                  <button
                    key={code.value}
                    type="button"
                    onClick={() => !added && onAdd(code.value)}
                    disabled={added}
                    className={`w-full text-left px-3 py-1.5 text-xs transition-colors flex items-center gap-2 ${
                      added
                        ? "text-slate-300 cursor-default bg-slate-50"
                        : "text-slate-700 hover:bg-blue-50 hover:text-blue-700"
                    }`}
                  >
                    <span className="font-mono text-[10px] text-slate-400 w-6 shrink-0">{code.value}</span>
                    <span className="flex-1">{code.label.split(" - ")[1]}</span>
                    {added && <span className="text-[10px] text-blue-400 font-medium shrink-0">추가됨</span>}
                  </button>
                );
              })}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

/** 단계별 공정 코드 표시 컴포넌트 */
function ProcessStepList({
  steps,
  processCodes,
  onProcessCodesChange,
}: {
  steps: ProcessStep[];
  processCodes: string[];
  onProcessCodesChange: (codes: string[]) => void;
}) {
  // 유사 코드 기본 펼침: 모든 step number를 초기 Set에 넣음
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(
    () => new Set(steps.map((s) => s.step_number))
  );
  // 코드 직접 검색창이 열린 step number (null이면 닫힘)
  const [searchOpenStep, setSearchOpenStep] = useState<number | null>(null);

  const toggleStep = (stepNum: number) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(stepNum)) next.delete(stepNum);
      else next.add(stepNum);
      return next;
    });
  };

  const toggleCode = (code: string) => {
    if (processCodes.includes(code)) {
      onProcessCodesChange(processCodes.filter((c) => c !== code));
    } else {
      onProcessCodesChange([...processCodes, code]);
    }
  };

  const addCodeForStep = (code: string, stepNum: number) => {
    if (!processCodes.includes(code)) {
      onProcessCodesChange([...processCodes, code]);
    }
    setSearchOpenStep(null);
  };

  return (
    <div className="space-y-2">
      {steps.map((step) => {
        const recChecked = processCodes.includes(step.recommended_code);
        const hasSimilar = step.similar_codes.length > 0;
        const expanded = expandedSteps.has(step.step_number);
        const isSearchOpen = searchOpenStep === step.step_number;
        const codeName = step.recommended_code_name || getProcessCodeLabel(step.recommended_code).replace(/^[\w\d]+\s*[-–]\s*/, "");

        return (
          <div
            key={step.step_number}
            className="rounded-xl border border-slate-200 overflow-hidden"
          >
            {/* 단계 헤더 */}
            <div className="flex items-center gap-2 px-3 py-2 bg-slate-50 border-b border-slate-100">
              <span className="text-[10px] font-bold text-slate-400 shrink-0">
                {step.step_number}번 공정
              </span>
              <span className="text-xs font-semibold text-slate-700 truncate flex-1">
                {step.step_name_original
                  ? `${step.step_name_original}${step.step_name_ko && step.step_name_ko !== step.step_name_original ? ` (${step.step_name_ko})` : ""}`
                  : step.step_name_ko}
              </span>
              {/* 코드 직접 검색 버튼 */}
              <button
                type="button"
                onClick={() => setSearchOpenStep(isSearchOpen ? null : step.step_number)}
                title="다른 코드 검색"
                className={`shrink-0 flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-lg border transition-all ${
                  isSearchOpen
                    ? "bg-blue-50 border-blue-300 text-blue-600"
                    : "bg-white border-slate-200 text-slate-500 hover:border-blue-300 hover:text-blue-600 hover:bg-blue-50"
                }`}
              >
                <Search size={10} />
                코드 검색
              </button>
            </div>

            <div className="px-3 py-2 space-y-1.5">
              {/* 인라인 코드 검색창 */}
              {isSearchOpen && (
                <StepCodeSearch
                  processCodes={processCodes}
                  onAdd={(code) => addCodeForStep(code, step.step_number)}
                  onClose={() => setSearchOpenStep(null)}
                />
              )}

              {/* 추천 코드 */}
              <button
                type="button"
                onClick={() => toggleCode(step.recommended_code)}
                className={`w-full text-left flex items-start gap-2.5 p-2 rounded-lg border transition-all ${
                  recChecked
                    ? "bg-blue-50 border-blue-200"
                    : "bg-white border-slate-200 hover:border-blue-200"
                }`}
              >
                <span className={`mt-0.5 shrink-0 ${recChecked ? "text-blue-500" : "text-slate-300"}`}>
                  {recChecked ? <CheckSquare size={14} /> : <Square size={14} />}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className={`text-[11px] font-bold font-mono px-1.5 py-0.5 rounded ${recChecked ? "bg-blue-100 text-blue-700" : "bg-slate-100 text-slate-500"}`}>
                      {step.recommended_code}
                    </span>
                    <span className={`text-xs font-semibold ${recChecked ? "text-blue-800" : "text-slate-700"}`}>
                      {codeName}
                    </span>
                    <span className="text-[10px] font-medium bg-emerald-100 text-emerald-600 px-1.5 py-0.5 rounded-full">
                      AI 추천
                    </span>
                  </div>
                  {step.recommended_reason && (
                    <p className="text-[11px] text-slate-500 mt-0.5 leading-snug">
                      ↳ {step.recommended_reason}
                    </p>
                  )}
                </div>
              </button>

              {/* 유사 코드 토글 */}
              {hasSimilar && (
                <div>
                  <button
                    type="button"
                    onClick={() => toggleStep(step.step_number)}
                    className="flex items-center gap-1.5 text-[11px] font-semibold text-amber-600 hover:text-amber-800 transition-colors py-1 px-2 bg-amber-50 border border-amber-200 rounded-lg w-full mt-1"
                  >
                    {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                    혼동 가능 유사 코드 {step.similar_codes.length}개
                  </button>

                  {expanded && (
                    <div className="mt-1 space-y-1">
                      {step.similar_codes.map((sim) => {
                        const simChecked = processCodes.includes(sim.code);
                        const simName = sim.name || getProcessCodeLabel(sim.code).replace(/^[\w\d]+\s*[-–]\s*/, "");
                        return (
                          <button
                            key={sim.code}
                            type="button"
                            onClick={() => toggleCode(sim.code)}
                            className={`w-full text-left flex items-start gap-2 p-2 rounded-lg border transition-all ${
                              simChecked
                                ? "bg-amber-50 border-amber-200"
                                : "bg-slate-50 border-slate-200 hover:border-amber-200"
                            }`}
                          >
                            <span className={`mt-0.5 shrink-0 ${simChecked ? "text-amber-500" : "text-slate-300"}`}>
                              {simChecked ? <CheckSquare size={13} /> : <Square size={13} />}
                            </span>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className={`text-[11px] font-bold font-mono px-1.5 py-0.5 rounded ${simChecked ? "bg-amber-100 text-amber-700" : "bg-slate-200 text-slate-500"}`}>
                                  {sim.code}
                                </span>
                                <span className={`text-xs font-semibold ${simChecked ? "text-amber-800" : "text-slate-500"}`}>
                                  {simName}
                                </span>
                                <span className="text-[10px] font-medium bg-slate-200 text-slate-500 px-1.5 py-0.5 rounded-full">
                                  유사 코드
                                </span>
                              </div>
                              {sim.reason && (
                                <p className="text-[11px] text-slate-500 mt-0.5 leading-snug">↳ {sim.reason}</p>
                              )}
                              {sim.confusion_note && (
                                <p className="text-[11px] text-amber-600 mt-0.5 leading-snug bg-amber-50 rounded px-1.5 py-0.5">
                                  ⚠ {sim.confusion_note}
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
          </div>
        );
      })}
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
  japanPrefectureCode,
  onJapanPrefectureCodeChange,
  rawProcessText,
  processCodeReasons,
  processCodeCandidates,
  processSteps,
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

  // process_steps > candidates > 기존 tag UI 순으로 우선 적용
  const hasSteps = processSteps && processSteps.length > 0;
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

          {/* 단계별 공정 코드 (process_steps 있을 때 우선) */}
          {hasSteps ? (
            <ProcessStepList
              steps={processSteps!}
              processCodes={processCodes}
              onProcessCodesChange={onProcessCodesChange}
            />
          ) : hasCandidates ? (
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
          <div className={`relative ${hasSteps || hasCandidates ? "mt-3" : ""}`}>
            <p className="text-[11px] text-slate-400 mb-1.5">
              {hasSteps || hasCandidates ? "목록에 없는 코드 직접 추가" : ""}
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

        {/* 일본산일 때: 생산 도·현 선택 */}
        {exportCountry === "일본" && (
          <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-4 space-y-3">
            <div className="flex items-start gap-2">
              <span className="text-amber-500 mt-0.5 shrink-0 text-base leading-none">⚠</span>
              <div>
                <p className="text-[13px] font-semibold text-amber-800">일본산 — 생산 도·현 선택 필요</p>
                <p className="text-[11px] text-amber-700 mt-0.5 leading-relaxed">
                  도·현에 따라 필요 서류가 다릅니다. 미선택 시 F3에서 경고가 발생합니다.
                </p>
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-[12px] font-medium text-slate-700 block">생산 도·현</label>
              <select
                value={codeToSelectedName(japanPrefectureCode ?? "") ?? ""}
                onChange={(e) => {
                  const val = e.target.value;
                  if (!val) {
                    onJapanPrefectureCodeChange?.("");
                    return;
                  }
                  const found = JAPAN_PREFECTURES.find((p) => p.name === val);
                  if (found) onJapanPrefectureCodeChange?.(prefectureToCode(found));
                }}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-800 focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-400/20"
              >
                <option value="">-- 도·현을 선택하세요 --</option>
                <optgroup label="13개 도·현 (방사성물질 검사성적서 + 일본 정부증명서)">
                  {JAPAN_PREFECTURES.filter((p) => p.group === "13").map((p) => (
                    <option key={p.name} value={p.name}>{p.label}</option>
                  ))}
                </optgroup>
                <optgroup label="34개 도·부·현 (비오염 생산지 증명서)">
                  {JAPAN_PREFECTURES.filter((p) => p.group === "34").map((p) => (
                    <option key={p.name} value={p.name}>{p.label}</option>
                  ))}
                </optgroup>
              </select>
            </div>

            {/* 선택 결과 뱃지 */}
            {japanPrefectureCode && (
              <div className="flex items-center gap-2 pt-1">
                {japanPrefectureCode === "일본34개도부현" ? (
                  <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full bg-blue-100 text-blue-700">
                    비오염 생산지 증명서 필요
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full bg-red-100 text-red-700">
                    방사성물질 검사성적서 + 일본 정부증명서 필요
                  </span>
                )}
                <span className="text-[11px] text-slate-400">
                  전달 코드: <code className="font-mono bg-slate-100 px-1 py-0.5 rounded text-slate-600">{japanPrefectureCode}</code>
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
