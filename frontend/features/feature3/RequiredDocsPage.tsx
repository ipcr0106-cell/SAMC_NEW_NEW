"use client";

import { useState, useCallback, useEffect } from "react";
import { createPortal } from "react-dom";
import { useParams, useRouter } from "next/navigation";
import { getLawText } from "@/features/feature3/lib/law-texts";
import { crossCheck, type CrossCheckResult } from "@/features/feature3/lib/cross-check";
import { getIssuerInfo, buildDetailedReason } from "@/features/feature3/lib/ui-helpers";

// ── 타입 ─────────────────────────────────────

interface RequiredDoc {
  id: string;
  doc_name: string;
  doc_description: string;
  is_mandatory: boolean;
  submission_type: "submit" | "keep";
  submission_timing: "every" | "first";
  law_source: string;
  condition: string | null;
  target_country: string | null;
  product_keywords: string[] | null;
  match_reason?: string;
  effective_from?: string;
  effective_until?: string;
  decision_axis?: "공통" | "식품유형" | "원재료" | "국가" | "조건"
    | "식품유형+국가" | "원재료+국가" | "원재료+조건"
    | "식품유형+조건" | "출처+원재료";
}

interface DocsResult {
  food_type: string;
  origin_country: string;
  is_first_import: boolean;
  submit_docs: RequiredDoc[];
  keep_docs: RequiredDoc[];
  total_submit: number;
  total_keep: number;
  warnings?: string[];
  match_confidence?: "high" | "base_only";
  warning?: string | null;
}

type FoodCategory =
  | "축산물" | "수산물" | "가공식품" | "농.임산물"
  | "식품첨가물" | "기구또는용기.포장" | "건강기능식품";

interface ProductInfo {
  category?: FoodCategory;
  food_large_category?: string;  // 식품공전 대분류/식품군 (모듈 2 출력)
  food_mid_category?: string;    // 식품공전 중분류/식품종 (모듈 2 출력)
  food_type: string;             // 식품공전 소분류/식품유형
  origin_country: string;
  is_oem: boolean;
  is_first_import: boolean;
  has_organic_cert: boolean;
  product_keywords: string[];
  reasoning?: string;
}

// 파이프라인에서 넘어오는 이전 단계 결과 (모듈 연결용)
interface PipelineInput {
  case_id: string;
  category?: FoodCategory;
  food_large_category?: string;
  food_mid_category?: string;
  food_type: string;
  origin_country: string;
  is_oem: boolean;
  is_first_import: boolean;
  has_organic_cert: boolean;
  product_keywords: string[];
}

// ── 아이콘 ───────────────────────────────────

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round"
      className={`w-4 h-4 transition-transform duration-200 ${open ? "rotate-180" : ""}`}>
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function UploadIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round" className="w-10 h-10 text-gray-300">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  );
}

function CheckCircleIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  );
}

// ── 일본 도현 자동완성 ───────────────────────

const JAPAN_PREFECTURES = [
  { name: "후쿠시마", label: "후쿠시마현", group: "13" },
  { name: "이바라키", label: "이바라키현", group: "13" },
  { name: "토치키", label: "토치키현", group: "13" },
  { name: "군마", label: "군마현", group: "13" },
  { name: "사이타마", label: "사이타마현", group: "13" },
  { name: "치바", label: "치바현", group: "13" },
  { name: "미야기", label: "미야기현", group: "13" },
  { name: "가나가와", label: "가나가와현", group: "13" },
  { name: "도쿄", label: "도쿄도", group: "13" },
  { name: "나가노", label: "나가노현", group: "13" },
  { name: "야마가타", label: "야마가타현", group: "13" },
  { name: "니이가타", label: "니이가타현", group: "13" },
  { name: "시즈오카", label: "시즈오카현", group: "13" },
  { name: "홋카이도", label: "홋카이도", group: "34" },
  { name: "아오모리", label: "아오모리현", group: "34" },
  { name: "이와테", label: "이와테현", group: "34" },
  { name: "아키타", label: "아키타현", group: "34" },
  { name: "후쿠이", label: "후쿠이현", group: "34" },
  { name: "이시카와", label: "이시카와현", group: "34" },
  { name: "토야마", label: "토야마현", group: "34" },
  { name: "기후", label: "기후현", group: "34" },
  { name: "아이치", label: "아이치현", group: "34" },
  { name: "미에", label: "미에현", group: "34" },
  { name: "시가", label: "시가현", group: "34" },
  { name: "교토", label: "교토부", group: "34" },
  { name: "오사카", label: "오사카부", group: "34" },
  { name: "효고", label: "효고현", group: "34" },
  { name: "나라", label: "나라현", group: "34" },
  { name: "와카야마", label: "와카야마현", group: "34" },
  { name: "돗토리", label: "돗토리현", group: "34" },
  { name: "시마네", label: "시마네현", group: "34" },
  { name: "오카야마", label: "오카야마현", group: "34" },
  { name: "히로시마", label: "히로시마현", group: "34" },
  { name: "야마구치", label: "야마구치현", group: "34" },
  { name: "도쿠시마", label: "도쿠시마현", group: "34" },
  { name: "가가와", label: "가가와현", group: "34" },
  { name: "에히메", label: "에히메현", group: "34" },
  { name: "고치", label: "고치현", group: "34" },
  { name: "후쿠오카", label: "후쿠오카현", group: "34" },
  { name: "사가", label: "사가현", group: "34" },
  { name: "나가사키", label: "나가사키현", group: "34" },
  { name: "구마모토", label: "구마모토현", group: "34" },
  { name: "오이타", label: "오이타현", group: "34" },
  { name: "미야자키", label: "미야자키현", group: "34" },
  { name: "가고시마", label: "가고시마현", group: "34" },
  { name: "오키나와", label: "오키나와현", group: "34" },
];

function JapanPrefectureInput({ value, onChange }: { value: string; onChange: (val: string) => void }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);

  const selectedPref = JAPAN_PREFECTURES.find(p => p.name === value);
  const filtered = query
    ? JAPAN_PREFECTURES.filter(p => p.label.includes(query) || p.name.includes(query))
    : JAPAN_PREFECTURES;

  const handleSelect = (pref: typeof JAPAN_PREFECTURES[0]) => {
    // 34개 도부현은 DB 키워드 "일본34개도부현"으로 매핑
    onChange(pref.group === "13" ? pref.name : "일본34개도부현");
    setQuery("");
    setOpen(false);
  };

  return (
    <div className="mb-4 rounded-2xl bg-amber-50 border border-amber-200 p-4">
      <label className="text-xs text-amber-700 font-medium mb-2 block">
        일본 생산 도·현 입력 (방사성물질 검사 서류 판단용)
      </label>

      <div className="relative">
        <input
          value={open ? query : (selectedPref?.label || value || "")}
          onChange={e => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          placeholder="도·현 이름을 입력하세요 (예: 오사카, 후쿠시마)"
          className="w-full px-4 py-2.5 bg-white border border-amber-200 rounded-2xl text-sm outline-none focus:border-amber-400"
        />

        {/* 선택된 값 표시 뱃지 */}
        {value && !open && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-2">
            <span className={`px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded-full ${
              selectedPref?.group === "13"
                ? "bg-red-100 text-red-600 border border-red-200"
                : "bg-blue-100 text-blue-600 border border-blue-200"
            }`}>
              {selectedPref?.group === "13" ? "13개 도현" : "기타 지역"}
            </span>
            <button onClick={() => { onChange(""); setQuery(""); }}
              className="text-gray-400 hover:text-gray-600">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        )}

        {/* 자동완성 드롭다운 */}
        {open && (
          <div className="absolute z-40 left-0 right-0 top-full mt-1 bg-white rounded-2xl card-shadow border border-amber-100 max-h-64 overflow-y-auto">
            {filtered.length === 0 ? (
              <p className="px-4 py-3 text-sm text-gray-400">검색 결과 없음</p>
            ) : (
              <>
                {/* 13개 도현 그룹 */}
                {filtered.some(p => p.group === "13") && (
                  <>
                    <p className="px-4 pt-3 pb-1 text-[10px] font-bold uppercase tracking-widest text-red-400">
                      13개 도·현 (방사성물질 검사성적서 필요)
                    </p>
                    {filtered.filter(p => p.group === "13").map(p => (
                      <button key={p.name} onClick={() => handleSelect(p)}
                        className="w-full text-left px-4 py-2 text-sm hover:bg-amber-50 transition-colors flex items-center justify-between">
                        <span>{p.label}</span>
                        <span className="px-1.5 py-0.5 bg-red-50 text-[9px] text-red-500 rounded">검사성적서</span>
                      </button>
                    ))}
                  </>
                )}
                {/* 34개 도부현 그룹 */}
                {filtered.some(p => p.group === "34") && (
                  <>
                    <p className="px-4 pt-3 pb-1 text-[10px] font-bold uppercase tracking-widest text-blue-400">
                      기타 도·부·현 (비오염 생산지 증명서)
                    </p>
                    {filtered.filter(p => p.group === "34").map(p => (
                      <button key={p.name} onClick={() => handleSelect(p)}
                        className="w-full text-left px-4 py-2 text-sm hover:bg-blue-50 transition-colors flex items-center justify-between">
                        <span>{p.label}</span>
                        <span className="px-1.5 py-0.5 bg-blue-50 text-[9px] text-blue-500 rounded">생산지증명</span>
                      </button>
                    ))}
                  </>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {/* 선택 결과 안내 */}
      {value && (
        <p className={`text-[10px] font-light mt-2 ${
          selectedPref?.group === "13" ? "text-red-500" : "text-blue-500"
        }`}>
          {selectedPref?.group === "13"
            ? `${selectedPref.label}은 13개 도·현에 해당합니다. 요오드(131I)·세슘(134Cs+137Cs) 검사성적서 포함 일본 정부증명서가 필요합니다.`
            : "기타 도·부·현 지역입니다. 방사성 물질에 오염되지 않은 지역 생산·제조 증명서가 필요합니다."
          }
        </p>
      )}
    </div>
  );
}

function ArrowRightIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
      <line x1="5" y1="12" x2="19" y2="12" />
      <polyline points="12 5 19 12 12 19" />
    </svg>
  );
}

// ── 법령 팝업 (호버+클릭 고정) ───────────────

// ── 결정 축 뱃지 (툴팁 포함) ─────────────────────────
const AXIS_META: Record<string, { label: string; color: string; tooltip: string }> = {
  "공통":        { label: "공통",        color: "bg-gray-50 text-gray-500 border-gray-200",
    tooltip: "모든 수입식품에 공통으로 필요한 기본 서류입니다." },
  "식품유형":    { label: "식품유형",    color: "bg-blue-50 text-blue-600 border-blue-200",
    tooltip: "식품유형이 축산물·유기가공식품 등이라 필요한 서류입니다." },
  "원재료":      { label: "원재료",      color: "bg-amber-50 text-amber-700 border-amber-200",
    tooltip: "원재료에 복어·대마씨·죽염 등 특수 성분이 있어 필요한 서류입니다." },
  "국가":        { label: "국가",        color: "bg-rose-50 text-rose-600 border-rose-200",
    tooltip: "제조국이 특정 규제 국가군(BSE·ASF·PET 등)에 속해 필요한 서류입니다." },
  "조건":        { label: "조건",        color: "bg-purple-50 text-purple-600 border-purple-200",
    tooltip: "OEM·외화획득용 등 수입 조건에 따라 필요한 서류입니다." },
  "식품유형+국가": { label: "식품유형+국가", color: "bg-slate-50 text-slate-600 border-slate-200",
    tooltip: "식품유형과 제조국이 모두 해당되어야 필요한 서류입니다. (예: 미국산 유기가공식품)" },
  "원재료+국가":   { label: "원재료+국가",   color: "bg-slate-50 text-slate-600 border-slate-200",
    tooltip: "특정 원재료와 특정 국가가 함께 해당되어야 필요한 서류입니다. (예: BSE36국 반추동물 원료)" },
  "원재료+조건":   { label: "원재료+조건",   color: "bg-slate-50 text-slate-600 border-slate-200",
    tooltip: "원재료와 특수 조건(GMO 예외·인증 유무 등)이 같이 작용해 필요한 서류입니다." },
  "식품유형+조건": { label: "식품유형+조건", color: "bg-slate-50 text-slate-600 border-slate-200",
    tooltip: "식품유형과 조건이 같이 작용해 필요한 서류입니다." },
  "출처+원재료":   { label: "출처+원재료",   color: "bg-slate-50 text-slate-600 border-slate-200",
    tooltip: "특정 출처(일본 도현 등)와 원재료가 모두 해당되어야 필요한 서류입니다." },
};

function AxisBadge({ axis }: { axis: string }) {
  const meta = AXIS_META[axis] || { label: axis, color: "bg-gray-50 text-gray-500 border-gray-200", tooltip: "" };
  const [show, setShow] = useState(false);
  return (
    <span className="relative inline-block">
      <span
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        className={`px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded-full border cursor-help ${meta.color}`}
      >
        {meta.label}
      </span>
      {show && meta.tooltip && (
        <span className="absolute z-50 left-0 top-full mt-1 w-64 rounded-lg bg-gray-900 text-white text-xs font-light leading-relaxed px-3 py-2 shadow-lg animate-in fade-in duration-150">
          {meta.tooltip}
        </span>
      )}
    </span>
  );
}


function LawHoverPopup({ lawSource, children }: { lawSource: string; children: React.ReactNode }) {
  const [show, setShow] = useState(false);
  const [pinned, setPinned] = useState(false);
  const lawData = getLawText(lawSource);

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (pinned) { setPinned(false); setShow(false); }
    else { setPinned(true); setShow(true); }
  };

  return (
    <span className="relative inline">
      <span
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => { if (!pinned) setShow(false); }}
        onClick={handleClick}
        className={`underline decoration-2 underline-offset-2 cursor-pointer transition-all duration-200 font-normal ${
          pinned
            ? "text-violet-800 decoration-violet-500 bg-violet-50 rounded-sm px-0.5 shadow-[0_0_8px_rgba(139,92,246,0.25)]"
            : "text-violet-600 decoration-violet-300 hover:decoration-violet-500 hover:text-violet-800"
        }`}
      >
        {pinned && (
          <span className="inline-block w-1.5 h-1.5 bg-violet-500 rounded-full mr-1 align-middle animate-pulse" />
        )}
        {children}
      </span>

      {show && lawData && (
        <div
          className={`absolute z-50 w-[420px] max-h-[320px] overflow-y-auto
            bg-white rounded-2xl p-0 animate-in fade-in duration-150
            left-0 top-full mt-2 ${
              pinned
                ? "border-2 border-violet-300 shadow-lg shadow-violet-100/50"
                : "border border-violet-100 card-shadow"
            }`}
          onMouseEnter={() => setShow(true)}
          onMouseLeave={() => { if (!pinned) setShow(false); }}
        >
          <div className="sticky top-0 bg-white border-b border-violet-50 px-5 py-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="px-1.5 py-0.5 bg-violet-100 text-[9px] font-bold uppercase tracking-widest text-violet-600 rounded">
                  법령
                </span>
                <span className="text-sm font-semibold text-gray-900">{lawData.title}</span>
              </div>
              {pinned && (
                <button onClick={() => { setPinned(false); setShow(false); }}
                  className="p-1 rounded-full hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                    strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
                    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              )}
            </div>
            {lawData.article && (
              <p className="text-xs font-light text-gray-500 mt-1 ml-0.5">{lawData.article}</p>
            )}
          </div>
          <div className="px-5 py-4">
            <div className="text-[13px] font-light text-gray-700 leading-relaxed whitespace-pre-line
              border-l-3 border-violet-200 pl-4">
              {lawData.fullText}
            </div>
          </div>
          <div className="border-t border-gray-100 px-5 py-2.5">
            <p className="text-[10px] text-gray-400 font-light">
              수입식품안전관리 특별법 시행규칙 (총리령 제02038호, 2025.7.23.)
            </p>
          </div>
        </div>
      )}
    </span>
  );
}

// ── 인라인 설명 ──────────────────────────────

function DocDescription({ doc, explanation, explainDone, foodType, originCountry }: {
  doc: RequiredDoc; explanation?: string; explainDone: boolean;
  foodType?: string; originCountry?: string;
}) {
  const shortLaw = doc.law_source.split(";")[0].trim();
  const issuerInfo = getIssuerInfo(doc as any);
  const detailedReason = buildDetailedReason(doc as any, {
    food_type: foodType || "",
    origin_country: originCountry || "",
    is_oem: false,
    is_first_import: false,
    has_organic_cert: false,
    product_keywords: [],
  });

  return (
    <div className="space-y-4">
      {/* 법령 근거 + DB 기본 설명 */}
      <div>
        <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-1.5">근거 조항</p>
        <p className="text-sm font-light text-gray-600 leading-[1.7]">
          <LawHoverPopup lawSource={doc.law_source}>{shortLaw}</LawHoverPopup>
          {"에 따라, "}
          {doc.doc_description}
        </p>
      </div>

      {/* 상세 사유 (왜 필요한가) */}
      <div className="rounded-2xl bg-amber-50/60 border border-amber-100 px-4 py-3">
        <p className="text-[10px] font-bold uppercase tracking-widest text-amber-600 mb-1.5">왜 필요한가 (상세)</p>
        <p className="text-sm font-light text-amber-900 leading-relaxed">{detailedReason}</p>
      </div>

      {/* 발급처 · 형식 · 참고사항 */}
      <div className="grid grid-cols-1 gap-2">
        <div className="rounded-xl bg-gray-50 border border-gray-100 px-3 py-2">
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500 mb-0.5">발급처</p>
          <p className="text-xs font-light text-gray-700 leading-relaxed">{issuerInfo.issuer}</p>
        </div>
        <div className="rounded-xl bg-gray-50 border border-gray-100 px-3 py-2">
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500 mb-0.5">형식 요건</p>
          <p className="text-xs font-light text-gray-700 leading-relaxed">{issuerInfo.format}</p>
        </div>
        {issuerInfo.note && (
          <div className="rounded-xl bg-gray-50 border border-gray-100 px-3 py-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500 mb-0.5">참고사항</p>
            <p className="text-xs font-light text-gray-700 leading-relaxed">{issuerInfo.note}</p>
          </div>
        )}
      </div>

      {/* AI 맞춤 분석 (있을 때만) */}
      {explanation && (
        <div className="rounded-2xl bg-blue-50/60 border border-blue-100 px-4 py-3">
          <div className="flex items-start gap-2">
            <span className="shrink-0 mt-0.5 px-1.5 py-0.5 bg-blue-100 text-[9px] font-bold uppercase tracking-widest text-blue-600 rounded">
              AI 맞춤 분석
            </span>
            <p className="text-sm font-light text-blue-900 leading-relaxed">{explanation}</p>
          </div>
        </div>
      )}
      {!explanation && !explainDone && (
        <div className="flex items-center gap-2 text-xs text-gray-300">
          <span className="w-3 h-3 border-2 border-gray-200 border-t-blue-300 rounded-full animate-spin" />
          AI 맞춤 분석 로딩
        </div>
      )}

      {/* 신뢰 고지 */}
      <p className="text-[10px] text-gray-400 leading-relaxed pt-2 border-t border-gray-100">
        ※ 본 설명은 시스템 내부 템플릿(법령·시행규칙·고시 기반 요약)이며, 정확한 요구사항은 해당 법령 원문 또는 식약처 담당자를 통해 확인하시기 바랍니다.
      </p>
    </div>
  );
}

// ── 서류 카드 ─────────────────────────────────

function DocCard({ doc, explanation, explainDone, crossCheck, foodType, originCountry }: {
  doc: RequiredDoc; explanation?: string; explainDone: boolean; crossCheck?: CrossCheckResult;
  foodType?: string; originCountry?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const isConditional = doc.condition !== null || doc.target_country !== null;
  const isFirstOnly = doc.submission_timing === "first";
  const isKeep = doc.submission_type === "keep";
  const hasEffectiveFrom = !!doc.effective_from;
  const hasEffectiveUntil = !!doc.effective_until;

  return (
    <div className={`bg-white rounded-3xl card-shadow transition-all duration-300 p-6 mb-4 border ${
      isKeep ? "border-slate-200/80 bg-slate-50/30" : isConditional ? "border-amber-200/80" : "border-gray-100"
    }`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            {/* 제출/보관 구분 뱃지 (최우선) */}
            {isKeep ? (
              <span className="px-2.5 py-0.5 bg-slate-100 text-[10px] font-bold uppercase tracking-wider text-slate-600 rounded-full border border-slate-300">
                보관
              </span>
            ) : (
              <span className="px-2.5 py-0.5 bg-emerald-50 text-[10px] font-bold uppercase tracking-wider text-emerald-700 rounded-full border border-emerald-200">
                제출
              </span>
            )}
            {isConditional && (
              <span className="px-2.5 py-0.5 bg-amber-50 text-[10px] font-bold uppercase tracking-wider text-amber-600 rounded-full border border-amber-200">
                조건부
              </span>
            )}
            {isFirstOnly && (
              <span className="px-2.5 py-0.5 bg-blue-50 text-[10px] font-bold uppercase tracking-wider text-blue-600 rounded-full border border-blue-200">
                최초 수입
              </span>
            )}
            {hasEffectiveFrom && (
              <span className="px-2.5 py-0.5 bg-purple-50 text-[10px] font-bold uppercase tracking-wider text-purple-600 rounded-full border border-purple-200">
                {doc.effective_from!.replace(/-/g,".")}부터 시행
              </span>
            )}
            {hasEffectiveUntil && (
              <span className="px-2.5 py-0.5 bg-rose-50 text-[10px] font-bold uppercase tracking-wider text-rose-600 rounded-full border border-rose-200">
                ~{doc.effective_until!.replace(/-/g,".")} 이후 전환
              </span>
            )}
            {!isConditional && !isFirstOnly && !isKeep && !hasEffectiveFrom && !hasEffectiveUntil && (
              <span className="px-2.5 py-0.5 bg-gray-100 text-[10px] font-bold uppercase tracking-wider text-gray-500 rounded-full">
                필수
              </span>
            )}
            {/* 크로스체크 신뢰도 뱃지 */}
            {crossCheck?.match_type === "both" && (
              <span className="px-2.5 py-0.5 bg-green-50 text-[10px] font-bold uppercase tracking-wider text-green-600 rounded-full border border-green-200">
                DB+AI 일치
              </span>
            )}
            {crossCheck?.match_type === "db_only" && (
              <span className="px-2.5 py-0.5 bg-gray-50 text-[10px] font-bold uppercase tracking-wider text-gray-400 rounded-full border border-gray-200">
                DB 규칙
              </span>
            )}
            {/* 결정 축 — 이 서류가 매칭된 이유를 한눈에 */}
            {doc.decision_axis && <AxisBadge axis={doc.decision_axis} />}
          </div>
          <h3 className="text-base font-semibold tracking-tight text-gray-900 leading-snug">
            {doc.doc_name}
          </h3>
          {/* 법령 근거 — 펼치지 않아도 항상 표시 (설문 E1: 근거 법령이 1순위) */}
          <p className="mt-1 text-xs text-violet-500 font-light">
            <LawHoverPopup lawSource={doc.law_source}>
              {doc.law_source.split(";")[0].trim()}
            </LawHoverPopup>
          </p>
          {/* 매칭 이유 (왜 이 서류가 이 제품에 필요한지) */}
          {doc.match_reason && doc.match_reason !== "모든 수입식품에 공통 적용" && (
            <div className="mt-2 rounded-xl bg-amber-50/70 border border-amber-100 px-3 py-2">
              <p className="text-xs font-light text-amber-800 leading-relaxed">
                {doc.match_reason}
              </p>
            </div>
          )}
        </div>
        <button onClick={() => setExpanded(p => !p)}
          className="shrink-0 p-2 rounded-full bg-gray-50 hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors">
          <ChevronIcon open={expanded} />
        </button>
      </div>
      {expanded && (
        <div className="mt-4 pt-4 border-t border-gray-100">
          <DocDescription doc={doc} explanation={explanation} explainDone={explainDone} foodType={foodType} originCountry={originCountry} />
        </div>
      )}
    </div>
  );
}

// ── 서류 섹션 ─────────────────────────────────

function DocSection({ title, docs, badgeText, badgeStyle, explanations = {}, explainDone = true, crossCheckResults = [], foodType, originCountry }: {
  title: string; docs: RequiredDoc[]; badgeText: string; badgeStyle: string;
  explanations?: Record<string, string>; explainDone?: boolean;
  crossCheckResults?: CrossCheckResult[];
  foodType?: string; originCountry?: string;
}) {
  if (!docs.length) return null;
  const common = docs.filter(d => !d.condition && !d.target_country && !d.product_keywords);
  const conditional = docs.filter(d => d.condition || d.target_country || d.product_keywords);

  return (
    <section className="mb-12">
      <div className="flex items-center gap-3 mb-6">
        <h2 className="text-lg font-semibold tracking-tight text-gray-900">{title}</h2>
        <span className={`px-3 py-1 text-[10px] font-bold uppercase tracking-widest rounded-full ${badgeStyle}`}>
          {badgeText} {docs.length}건
        </span>
      </div>
      {common.length > 0 && (
        <div className="mb-6">
          <p className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-3 ml-1">공통 필수</p>
          {common.map(d => <DocCard key={d.id} doc={d} explanation={explanations[d.id]} explainDone={explainDone} crossCheck={crossCheckResults.find(c => c.doc_name === d.doc_name)} foodType={foodType} originCountry={originCountry} />)}
        </div>
      )}
      {conditional.length > 0 && (
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-amber-500 mb-3 ml-1">조건부</p>
          {conditional.map(d => <DocCard key={d.id} doc={d} explanation={explanations[d.id]} explainDone={explainDone} crossCheck={crossCheckResults.find(c => c.doc_name === d.doc_name)} foodType={foodType} originCountry={originCountry} />)}
        </div>
      )}
    </section>
  );
}

// ── 파이프라인 진행 상태 바 ───────────────────

function PipelineProgress({ currentStep }: { currentStep: number }) {
  const steps = [
    { num: 1, label: "수입가능 판정" },
    { num: 2, label: "식품유형 분류" },
    { num: 3, label: "필요서류 안내" },
    { num: 4, label: "수출국표시사항" },
    { num: 5, label: "한글표시사항" },
  ];

  return (
    <div className="flex items-center justify-center gap-1 mb-10">
      {steps.map((step, i) => (
        <div key={step.num} className="flex items-center">
          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
            step.num < currentStep
              ? "bg-green-50 text-green-600 border border-green-200"
              : step.num === currentStep
                ? "bg-blue-600 text-white shadow-lg shadow-blue-600/20"
                : "bg-gray-50 text-gray-400 border border-gray-100"
          }`}>
            {step.num < currentStep && <CheckCircleIcon />}
            <span>{step.label}</span>
          </div>
          {i < steps.length - 1 && (
            <div className={`w-6 h-px mx-1 ${
              step.num < currentStep ? "bg-green-300" : "bg-gray-200"
            }`} />
          )}
        </div>
      ))}
    </div>
  );
}

// ══════════════════════════════════════════════
// 메인 페이지
// ══════════════════════════════════════════════

export default function StepAPage() {
  const params = useParams();
  const router = useRouter();
  const caseId = params.id as string;

  // 상태
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [pipelineInput, setPipelineInput] = useState<PipelineInput | null>(null);
  const [result, setResult] = useState<DocsResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [explanations, setExplanations] = useState<Record<string, string>>({});
  const [explainLoading, setExplainLoading] = useState(false);
  const [crossCheckResults, setCrossCheckResults] = useState<CrossCheckResult[]>([]);
  const [crossCheckDone, setCrossCheckDone] = useState(false);

  // 레포트 모달 상태
  const [reportOpen, setReportOpen] = useState(false);
  const [reportInspector, setReportInspector] = useState("");
  const [productNameForReport, setProductNameForReport] = useState("");

  // 기능 3 필수 입력 (파이프라인에서 안 넘어오는 정보)
  const [stepInput, setStepInput] = useState({
    origin_country: "",
    japan_prefecture: "" as string,
    is_oem: false,
    is_first_import: true,
    has_organic_cert: false,
  });
  const [stepInputSubmitted, setStepInputSubmitted] = useState(false);

  // 직접 조회 모드
  const [manualOpen, setManualOpen] = useState(false);
  const [manualMode, setManualMode] = useState<"form" | "ai">("form");
  const [files, setFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [parsedInfo, setParsedInfo] = useState<ProductInfo | null>(null);
  const [manualForm, setManualForm] = useState({
    food_type: "", origin_country: "", is_oem: false,
    is_first_import: true, has_organic_cert: false, product_keywords: "",
  });

  // ── LLM 맞춤 설명 생성 ─────────────────────

  const fetchExplanations = async (productInfo: PipelineInput, docs: RequiredDoc[]) => {
    setExplainLoading(true);
    try {
      const res = await fetch("/api/explain-docs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product_info: productInfo, docs }),
      });
      if (!res.ok) throw new Error("설명 생성 실패");
      const data = await res.json();
      const map: Record<string, string> = {};
      for (const item of data.explanations) {
        map[item.doc_id] = item.explanation;
      }
      setExplanations(map);
    } catch (err) {
      console.error("explain-docs error:", err);
      // 실패해도 기본 설명은 있으므로 에러 표시 안 함
      setExplanations({}); // 빈 객체 = 로딩 끝, 설명 없음
    } finally {
      setExplainLoading(false);
    }
  };

  // ── 파이프라인에서 이전 단계 데이터 로드 (food_type + keywords만) ────

  useEffect(() => {
    const loadPipelineData = async () => {
      setLoading(true);
      try {
        // === MOCK: 기능 2에서 넘어오는 정보 (food_type + keywords만) ===
        await new Promise(r => setTimeout(r, 600));
        const fromPipeline = {
          case_id: caseId,
          food_type: "리큐르",
          product_keywords: ["정제수", "설탕", "증류알코올", "살구씨증류액", "바닐라추출물", "천연향료", "구연산(E330)", "캐러멜색소(E150a)"],
        };
        // ==============================================

        // AI 성분 분석: 원재료를 DB 키워드로 자동 매핑
        let enrichedKeywords = [...fromPipeline.product_keywords];
        let ingredientWarnings: string[] = [];
        let bannedIngredients: string[] = [];

        try {
          const analyzeRes = await fetch("/api/analyze-ingredients", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              ingredients: fromPipeline.product_keywords,
              origin_country: "", // 아직 미입력
              food_type: fromPipeline.food_type,
            }),
          });
          if (analyzeRes.ok) {
            const analyzeData = await analyzeRes.json();
            // 감지된 DB 키워드를 product_keywords에 추가 (중복 제거)
            const existing = new Set(enrichedKeywords);
            for (const det of analyzeData.detected_keywords ?? []) {
              if (!existing.has(det.db_keyword)) {
                enrichedKeywords.push(det.db_keyword);
                existing.add(det.db_keyword);
              }
            }
            ingredientWarnings = analyzeData.warnings ?? [];
            bannedIngredients = analyzeData.banned ?? [];
          }
        } catch {
          // AI 분석 실패해도 원래 키워드로 진행
        }

        // 파이프라인에서 온 정보 + AI 보강 키워드 + 빈 사용자 입력
        setPipelineInput({
          ...fromPipeline,
          product_keywords: enrichedKeywords,
          origin_country: "",
          is_oem: false,
          is_first_import: true,
          has_organic_cert: false,
        });
        // 결과는 아직 없음 — 사용자가 추가 정보 입력 후 조회
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "데이터 로드 실패");
      } finally {
        setLoading(false);
      }
    };

    loadPipelineData();
  }, [caseId]);

  // ── 사용자 입력 완료 → 서류 조회 ─────────────

  const handleStepInputSubmit = async () => {
    if (!pipelineInput || !stepInput.origin_country) return;
    setStepInputSubmitted(true);
    setError(null);

    const country = stepInput.origin_country.trim();
    const isJapan = ["일본", "japan", "Japan", "JAPAN", "JP"].includes(country);
    const normalizedCountry = isJapan ? "일본" : country;

    let keywords = [...pipelineInput.product_keywords];

    // 일본 도현 선택값 추가
    if (isJapan && stepInput.japan_prefecture) {
      keywords = [...keywords, stepInput.japan_prefecture];
    }

    // 수출국 정보가 추가됐으므로 AI 성분 재분석 (국가별 규칙 반영)
    try {
      const analyzeRes = await fetch("/api/analyze-ingredients", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ingredients: keywords,
          origin_country: normalizedCountry,
          food_type: pipelineInput.food_type,
        }),
      });
      if (analyzeRes.ok) {
        const analyzeData = await analyzeRes.json();
        const existing = new Set(keywords);
        for (const det of analyzeData.detected_keywords ?? []) {
          if (!existing.has(det.db_keyword)) {
            keywords.push(det.db_keyword);
            existing.add(det.db_keyword);
          }
        }
      }
    } catch {
      // AI 분석 실패해도 기존 키워드로 진행
    }

    const fullInput: PipelineInput = {
      ...pipelineInput,
      origin_country: normalizedCountry,
      product_keywords: keywords,
      is_oem: stepInput.is_oem,
      is_first_import: stepInput.is_first_import,
      has_organic_cert: stepInput.has_organic_cert,
    };
    setPipelineInput(fullInput);

    try {
      const res = await fetch("/api/query-docs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(fullInput),
      });
      const data: DocsResult = await res.json();
      setResult(data);

      // AI 크로스체크 비동기 (DB 결과와 AI 독립 판정 비교)
      setCrossCheckDone(false);
      fetch("/api/ai-cross-check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(fullInput),
      }).then(async (aiRes) => {
        if (aiRes.ok) {
          const aiData = await aiRes.json();
          const allDocs = [...data.submit_docs, ...data.keep_docs];
          const dbDocs = allDocs.map(d => ({ id: d.id, doc_name: d.doc_name, law_source: d.law_source }));
          const results = crossCheck(dbDocs, aiData.documents ?? []);
          setCrossCheckResults(results);
        }
      }).catch(() => {}).finally(() => setCrossCheckDone(true));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "서류 조회 실패");
    }
  };

  // ── 확인 완료 → 다음 단계 ─────────────────

  const handleConfirm = async () => {
    setConfirming(true);
    try {
      // 실제: POST /api/v1/cases/{caseId}/pipeline/feature/3/confirm
      // 테스트: mock
      await new Promise(r => setTimeout(r, 500));

      // pipeline_steps status='completed', cases.current_step='B'
      setConfirmed(true);

      // 2초 후 다음 단계로 이동
      setTimeout(() => {
        router.push(`/cases/${caseId}/step_b`);
      }, 2000);
    } catch (err: any) {
      alert("확인 처리 실패: " + err.message);
    } finally {
      setConfirming(false);
    }
  };

  // ── 직접 조회: 드래그앤드롭 ────────────────

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = Array.from(e.dataTransfer.files).filter(
      f => f.type === "application/pdf" || f.type.startsWith("image/")
    );
    if (dropped.length) setFiles(prev => [...prev, ...dropped]);
  }, []);

  const handleParse = async () => {
    if (!files.length) return;
    setParsing(true);
    try {
      const formData = new FormData();
      files.forEach(f => formData.append("files", f));
      const res = await fetch("/api/parse-document", { method: "POST", body: formData });
      if (!res.ok) throw new Error((await res.json()).error || "분석 실패");
      setParsedInfo(await res.json());
    } catch (err: any) { setError(err.message); }
    finally { setParsing(false); }
  };

  const handleManualQuery = async (info: ProductInfo) => {
    setLoading(true);
    try {
      const res = await fetch("/api/query-docs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(info),
      });
      const data: DocsResult = await res.json();
      setResult(data);
      setPipelineInput({ case_id: caseId, ...info });
      setManualOpen(false);
    } catch (err: any) { setError(err.message); }
    finally { setLoading(false); }
  };

  // ── 로딩 ───────────────────────────────────

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-3">
          <div className="w-10 h-10 mx-auto border-2 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
          <p className="text-sm font-light text-gray-500">이전 단계 정보를 불러오는 중...</p>
        </div>
      </div>
    );
  }

  // ── 확인 완료 화면 ─────────────────────────

  if (confirmed) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center space-y-4">
          <div className="w-16 h-16 mx-auto bg-green-50 rounded-full flex items-center justify-center text-green-500">
            <CheckCircleIcon />
          </div>
          <h2 className="text-xl font-bold text-gray-900">기능 3 확인 완료</h2>
          <p className="text-sm font-light text-gray-500">수출국표시사항 검토(기능 4)로 이동합니다...</p>
          <div className="w-6 h-6 mx-auto border-2 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  // ── 메인 결과 화면 ─────────────────────────

  return (
    <div className="min-h-screen pb-20">
      <main className="max-w-3xl mx-auto w-full px-6 pt-8">

        {/* 파이프라인 진행 상태 */}
        <PipelineProgress currentStep={3} />

        {/* 타이틀 */}
        <section className="text-center mb-10 space-y-3">
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight text-gray-900">수입 필요서류 안내</h1>
          <p className="text-base text-gray-500 font-light">이전 단계에서 확인된 제품 정보를 기반으로 필요 서류를 안내합니다.</p>
        </section>

        {/* 이전 단계에서 받은 제품 정보 (food_type + keywords만) */}
        {pipelineInput && (
          <section className="bg-white rounded-[32px] p-8 card-shadow border border-gray-100 mb-6">
            <div className="flex items-center justify-between mb-4">
              <p className="text-xs font-bold uppercase tracking-widest text-gray-400 ml-1">기능 1·2에서 넘어온 정보</p>
              <span className="px-2.5 py-0.5 bg-green-50 text-[10px] font-bold uppercase tracking-wider text-green-600 rounded-full border border-green-200">
                자동 연결
              </span>
            </div>
            <div className="flex flex-wrap gap-3">
              <span className="px-4 py-2 bg-gray-50 rounded-2xl text-sm font-light text-gray-700 border border-gray-100">
                식품유형 <strong className="font-semibold">{pipelineInput.food_type}</strong>
              </span>
            </div>
            {pipelineInput.product_keywords.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {pipelineInput.product_keywords.map((kw, i) => (
                  <span key={i} className="px-2.5 py-1 bg-blue-50 text-[11px] text-blue-600 rounded-full border border-blue-100">
                    {kw}
                  </span>
                ))}
              </div>
            )}
          </section>
        )}

        {/* 기능 3 필수 입력: 수출국, OEM, 최초수입, 유기인증 */}
        {pipelineInput && !stepInputSubmitted && (
          <section className="bg-white rounded-[32px] p-8 card-shadow border-2 border-blue-200 mb-10">
            <p className="text-xs font-bold uppercase tracking-widest text-blue-500 mb-2">기능 3 추가 정보 입력</p>
            <p className="text-sm font-light text-gray-500 mb-6">
              수입 가능한 제품입니다. 필요 서류를 확인하기 위해 아래 정보를 입력하세요.
            </p>

            <div className="mb-4">
              <label className="text-xs text-gray-500 mb-1 block">제조국 (제품을 최종 제조·가공한 국가)</label>
              <input
                value={stepInput.origin_country}
                onChange={e => setStepInput(p => ({ ...p, origin_country: e.target.value }))}
                placeholder="예: 네덜란드, 일본, 미국"
                className="w-full px-4 py-2.5 bg-gray-50 border border-gray-100 rounded-2xl text-sm focus:bg-white focus:border-blue-200 transition-all outline-none"
              />
            </div>

            {/* 일본 선택 시 도현 자동완성 입력 */}
            {["일본", "japan", "Japan", "JAPAN", "JP"].includes(stepInput.origin_country.trim()) && (
              <JapanPrefectureInput
                value={stepInput.japan_prefecture}
                onChange={val => setStepInput(p => ({ ...p, japan_prefecture: val }))}
              />
            )}

            <div className="flex flex-wrap gap-6 mb-6">
              {([
                { key: "is_oem" as const, label: "주문자상표부착(OEM) 제품", desc: "국내 업체 상표를 부착하여 해외에서 제조한 제품" },
                { key: "is_first_import" as const, label: "최초 수입", desc: "이 수입자가 이 제조업소의 이 제품을 처음 수입" },
                { key: "has_organic_cert" as const, label: "유기인증 (95% 이상)", desc: "수출국에서 유기인증을 받은 가공식품" },
              ]).map(({ key, label, desc }) => (
                <label key={key} className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={stepInput[key]}
                    onChange={e => setStepInput(p => ({ ...p, [key]: e.target.checked }))}
                    className="w-4 h-4 mt-0.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <div>
                    <span className="text-sm text-gray-700 font-medium">{label}</span>
                    <p className="text-xs text-gray-400 font-light mt-0.5">{desc}</p>
                  </div>
                </label>
              ))}
            </div>

            <button
              onClick={handleStepInputSubmit}
              disabled={!stepInput.origin_country.trim()}
              className="w-full py-3 rounded-full bg-blue-600 text-white text-sm font-semibold hover:bg-blue-700 disabled:opacity-30 transition-all shadow-lg shadow-blue-600/20"
            >
              서류 조회하기
            </button>
          </section>
        )}

        {/* 입력 완료 후 요약 표시 */}
        {stepInputSubmitted && pipelineInput && (
          <section className="bg-white rounded-[32px] p-8 card-shadow border border-gray-100 mb-10">
            <div className="flex items-center justify-between mb-4">
              <p className="text-xs font-bold uppercase tracking-widest text-gray-400 ml-1">제품 정보 (기능 1·2 자동 + 기능 3 입력)</p>
              <button onClick={() => { setStepInputSubmitted(false); setResult(null); }}
                className="text-xs text-blue-500 hover:text-blue-700 font-medium">수정</button>
            </div>
            <div className="flex flex-wrap gap-3">
              <span className="px-4 py-2 bg-gray-50 rounded-2xl text-sm font-light text-gray-700 border border-gray-100">
                식품유형 <strong className="font-semibold">{pipelineInput.food_type}</strong>
              </span>
              <span className="px-4 py-2 bg-gray-50 rounded-2xl text-sm font-light text-gray-700 border border-gray-100">
                수출국 <strong className="font-semibold">{pipelineInput.origin_country}</strong>
              </span>
              <span className="px-4 py-2 bg-gray-50 rounded-2xl text-sm font-light text-gray-700 border border-gray-100">
                최초 수입 <strong className="font-semibold">{pipelineInput.is_first_import ? "예" : "아니오"}</strong>
              </span>
              {pipelineInput.is_oem && (
                <span className="px-4 py-2 bg-amber-50 rounded-2xl text-sm font-light text-amber-700 border border-amber-100">
                  OEM <strong className="font-semibold">해당</strong>
                </span>
              )}
              {pipelineInput.has_organic_cert && (
                <span className="px-4 py-2 bg-green-50 rounded-2xl text-sm font-light text-green-700 border border-green-100">
                  유기인증 <strong className="font-semibold">해당</strong>
                </span>
              )}
            </div>
          </section>
        )}

        {/* 결과 카운트 */}
        {result && (
          <>
            <section className="flex gap-4 mb-6">
              <div className="flex-1 bg-white rounded-3xl card-shadow border border-gray-100 p-6 text-center">
                <p className="text-3xl font-bold tracking-tight text-blue-600">{result.total_submit}</p>
                <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mt-1">제출 서류</p>
              </div>
              <div className="flex-1 bg-white rounded-3xl card-shadow border border-gray-100 p-6 text-center">
                <p className="text-3xl font-bold tracking-tight text-gray-500">{result.total_keep}</p>
                <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mt-1">보관 서류</p>
              </div>
              <button
                onClick={() => setReportOpen(true)}
                className="flex-1 bg-gray-900 hover:bg-gray-800 transition-all rounded-3xl card-shadow p-6 text-center group no-print"
              >
                <p className="text-xl font-bold tracking-tight text-white">📄</p>
                <p className="text-[10px] font-bold uppercase tracking-widest text-gray-300 mt-1 group-hover:text-white">
                  레포트 · PDF
                </p>
              </button>
            </section>

            {/* 경고: match_confidence가 낮거나 warnings가 있을 때 */}
            {(result.match_confidence === "base_only" || (result.warnings && result.warnings.length > 0) || result.warning) && (
              <section className="bg-white rounded-3xl card-shadow border-2 border-orange-200 p-5 mb-10">
                <div className="flex items-start gap-3">
                  <span className="shrink-0 px-2 py-0.5 bg-orange-100 text-[9px] font-bold uppercase tracking-widest text-orange-600 rounded">
                    확인 필요
                  </span>
                  <div className="space-y-1.5">
                    {result.warning && (
                      <p className="text-sm font-light text-orange-800 leading-relaxed">{result.warning}</p>
                    )}
                    {result.warnings?.map((w, i) => (
                      <p key={i} className="text-sm font-light text-orange-800 leading-relaxed">{w}</p>
                    ))}
                    {result.match_confidence === "base_only" && !result.warning && (
                      <p className="text-sm font-light text-orange-800 leading-relaxed">
                        공통 필수 서류만 매칭되었습니다. 제품 키워드나 수출국 정보가 부족하면 조건부 서류가 누락될 수 있습니다.
                      </p>
                    )}
                  </div>
                </div>
              </section>
            )}

            <DocSection title="수입신고 시 제출 서류" docs={result.submit_docs}
              badgeText="제출" badgeStyle="bg-blue-50 text-blue-600 border border-blue-200"
              explanations={explanations} explainDone={!explainLoading}
              crossCheckResults={crossCheckResults}
              foodType={result.food_type} originCountry={result.origin_country} />
            <DocSection title="영업자 보관 서류" docs={result.keep_docs}
              badgeText="보관" badgeStyle="bg-gray-100 text-gray-500 border border-gray-200"
              explanations={explanations} explainDone={!explainLoading}
              crossCheckResults={crossCheckResults}
              foodType={result.food_type} originCountry={result.origin_country} />

            {/* AI만 감지한 서류 (DB에 없는 것) */}
            {crossCheckDone && crossCheckResults.filter(c => c.match_type === "ai_only").length > 0 && (
              <section className="mb-12">
                <div className="flex items-center gap-3 mb-6">
                  <h2 className="text-lg font-semibold tracking-tight text-gray-900">AI 추가 감지</h2>
                  <span className="px-3 py-1 text-[10px] font-bold uppercase tracking-widest rounded-full bg-purple-50 text-purple-600 border border-purple-200">
                    DB 미등록 {crossCheckResults.filter(c => c.match_type === "ai_only").length}건
                  </span>
                </div>
                <p className="text-xs font-light text-purple-500 mb-4">
                  AI가 법령을 분석하여 추가로 감지한 서류입니다. DB에 등록되지 않은 항목이므로 담당자가 직접 확인하세요.
                </p>
                {crossCheckResults.filter(c => c.match_type === "ai_only").map((c, i) => (
                  <div key={i} className="bg-white rounded-3xl card-shadow p-6 mb-4 border-2 border-purple-200">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="px-2.5 py-0.5 bg-purple-50 text-[10px] font-bold uppercase tracking-wider text-purple-600 rounded-full border border-purple-200">
                        AI 감지
                      </span>
                      {c.ai_confidence && (
                        <span className={`px-2 py-0.5 text-[9px] font-bold uppercase rounded-full ${
                          c.ai_confidence === "high" ? "bg-green-50 text-green-600" : "bg-amber-50 text-amber-600"
                        }`}>
                          {c.ai_confidence === "high" ? "높은 확신" : "추정"}
                        </span>
                      )}
                    </div>
                    <h3 className="text-base font-semibold tracking-tight text-gray-900">{c.doc_name}</h3>
                    <p className="text-xs text-violet-500 mt-1">{c.law_source}</p>
                    {c.ai_reason && (
                      <p className="text-sm font-light text-gray-600 mt-2">{c.ai_reason}</p>
                    )}
                    <p className="text-[10px] text-purple-400 mt-2">
                      이 항목은 AI가 독립적으로 판단한 것으로, DB에 등록되지 않았습니다. 실제 필요 여부는 담당자가 확인하세요.
                    </p>
                  </div>
                ))}
              </section>
            )}
          </>
        )}

        {/* 주의사항 */}
        <section className="bg-white rounded-[32px] p-8 card-shadow border border-amber-100 mb-8">
          <p className="text-xs font-bold uppercase tracking-widest text-amber-500 mb-4">확인 전 주의사항</p>
          <ul className="space-y-2 text-sm font-light text-gray-600 leading-relaxed">
            <li>서류 목록은 2026.2.5. 기준입니다. 법령 개정 시 변경될 수 있습니다.</li>
            <li>조건부 서류는 해당 조건에 맞는지 직접 확인하세요.</li>
            <li>최종 판단은 담당자가 직접 식약처 고시를 확인 후 결정하시기 바랍니다.</li>
          </ul>
        </section>

        {/* 직접 조회 (접힌 상태) */}
        <section className="mb-10">
          <button onClick={() => setManualOpen(p => !p)}
            className="flex items-center gap-2 text-sm text-gray-400 hover:text-gray-600 transition-colors mx-auto">
            <ChevronIcon open={manualOpen} />
            <span className="text-xs font-bold uppercase tracking-widest">
              {manualOpen ? "직접 조회 접기" : "파이프라인 없이 직접 조회하기"}
            </span>
          </button>

          {manualOpen && (
            <div className="mt-6 space-y-6">
              {/* 모드 탭 */}
              <div className="flex gap-2 justify-center">
                <button onClick={() => setManualMode("form")}
                  className={`px-4 py-2 rounded-full text-xs font-semibold transition-all ${
                    manualMode === "form" ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                  }`}>
                  직접 입력
                </button>
                <button onClick={() => setManualMode("ai")}
                  className={`px-4 py-2 rounded-full text-xs font-semibold transition-all ${
                    manualMode === "ai" ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                  }`}>
                  AI 문서 분석
                </button>
              </div>

              {/* 직접 입력 폼 */}
              {manualMode === "form" && (
                <div className="bg-white rounded-[32px] p-8 card-shadow border border-gray-100">
                  <div className="grid grid-cols-2 gap-4 mb-4">
                    <div>
                      <label className="text-xs text-gray-500 mb-1 block">식품유형</label>
                      <input value={manualForm.food_type}
                        onChange={e => setManualForm(p => ({ ...p, food_type: e.target.value }))}
                        placeholder="예: 과채음료"
                        className="w-full px-4 py-2.5 bg-gray-50 border border-gray-100 rounded-2xl text-sm outline-none focus:bg-white focus:border-blue-200" />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500 mb-1 block">수출국</label>
                      <input value={manualForm.origin_country}
                        onChange={e => setManualForm(p => ({ ...p, origin_country: e.target.value }))}
                        placeholder="예: 태국"
                        className="w-full px-4 py-2.5 bg-gray-50 border border-gray-100 rounded-2xl text-sm outline-none focus:bg-white focus:border-blue-200" />
                    </div>
                  </div>
                  <div className="mb-4">
                    <label className="text-xs text-gray-500 mb-1 block">원재료 키워드 (쉼표 구분)</label>
                    <input value={manualForm.product_keywords}
                      onChange={e => setManualForm(p => ({ ...p, product_keywords: e.target.value }))}
                      placeholder="예: 아가베, 에탄올, 젤라틴"
                      className="w-full px-4 py-2.5 bg-gray-50 border border-gray-100 rounded-2xl text-sm outline-none focus:bg-white focus:border-blue-200" />
                  </div>
                  <div className="flex flex-wrap gap-6 mb-6">
                    {([
                      { key: "is_oem" as const, label: "OEM" },
                      { key: "is_first_import" as const, label: "최초 수입" },
                      { key: "has_organic_cert" as const, label: "유기인증 (95%+)" },
                    ]).map(({ key, label }) => (
                      <label key={key} className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                        <input type="checkbox" checked={manualForm[key]}
                          onChange={e => setManualForm(p => ({ ...p, [key]: e.target.checked }))}
                          className="w-4 h-4 rounded border-gray-300 text-blue-600" />
                        {label}
                      </label>
                    ))}
                  </div>
                  <button onClick={() => handleManualQuery({
                      ...manualForm,
                      product_keywords: manualForm.product_keywords.split(",").map(s=>s.trim()).filter(Boolean),
                    })}
                    disabled={!manualForm.food_type || !manualForm.origin_country}
                    className="w-full py-3 rounded-full bg-gray-900 text-white text-sm font-semibold hover:bg-gray-800 disabled:opacity-30 transition-all">
                    서류 조회하기
                  </button>
                </div>
              )}

              {/* AI 문서 분석 */}
              {manualMode === "ai" && (
                <div className="space-y-4">
                  <div
                    onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={handleDrop}
                    className={`bg-white rounded-[32px] p-8 card-shadow border-2 border-dashed text-center transition-all cursor-pointer ${
                      dragOver ? "border-blue-400 bg-blue-50/50" : "border-gray-200 hover:border-gray-300"
                    }`}
                    onClick={() => document.getElementById("file-input")?.click()}
                  >
                    <input id="file-input" type="file" multiple accept=".pdf,image/*" className="hidden"
                      onChange={e => {
                        const selected = Array.from(e.target.files || []);
                        if (selected.length) setFiles(prev => [...prev, ...selected]);
                        e.target.value = "";
                      }} />
                    <UploadIcon />
                    <p className="text-sm font-light text-gray-500 mt-3">
                      서류를 <strong className="font-semibold text-gray-700">드래그하거나 클릭</strong>
                    </p>
                  </div>

                  {files.length > 0 && (
                    <div className="bg-white rounded-3xl card-shadow border border-gray-100 p-6">
                      <div className="space-y-2 mb-4">
                        {files.map((f, i) => (
                          <div key={i} className="flex items-center justify-between px-4 py-2 bg-gray-50 rounded-2xl">
                            <span className="text-sm text-gray-700 truncate">{f.name}</span>
                            <button onClick={() => setFiles(prev => prev.filter((_, j) => j !== i))}
                              className="text-xs text-red-400 hover:text-red-600">삭제</button>
                          </div>
                        ))}
                      </div>
                      <button onClick={handleParse} disabled={parsing}
                        className="w-full py-3 rounded-full bg-blue-600 text-white text-sm font-semibold hover:bg-blue-700 disabled:opacity-50 transition-all shadow-lg shadow-blue-600/20">
                        {parsing ? "AI 분석 중..." : "AI로 서류 분석하기"}
                      </button>
                    </div>
                  )}

                  {parsedInfo && (
                    <div className="bg-white rounded-[32px] p-6 card-shadow border border-gray-100">
                      <p className="text-xs font-bold uppercase tracking-widest text-blue-400 mb-3">AI 분석 결과</p>
                      <p className="text-sm text-gray-700 mb-3">
                        식품유형: <strong>{parsedInfo.food_type}</strong> · 수출국: <strong>{parsedInfo.origin_country}</strong>
                      </p>
                      {parsedInfo.reasoning && (
                        <p className="text-xs font-light text-gray-500 mb-4">{parsedInfo.reasoning}</p>
                      )}
                      <button onClick={() => handleManualQuery(parsedInfo)}
                        className="w-full py-3 rounded-full bg-blue-600 text-white text-sm font-semibold hover:bg-blue-700 transition-all">
                        이 정보로 서류 조회
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </section>

        {/* 확인 완료 버튼 */}
        <div className="flex justify-center">
          <button onClick={handleConfirm} disabled={confirming || !result}
            className="group flex items-center gap-3 px-10 py-4 rounded-full bg-blue-600 text-white text-sm font-semibold
              hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50 disabled:cursor-not-allowed
              transition-all duration-200 transform hover:scale-[1.02] active:scale-[0.98]
              shadow-lg shadow-blue-600/20">
            {confirming ? (
              <>
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                처리 중...
              </>
            ) : (
              <>
                확인 완료
                <ArrowRightIcon />
                <span className="text-blue-200 text-xs font-light">기능 4: 수출국표시사항</span>
              </>
            )}
          </button>
        </div>

        {error && (
          <div className="mt-6 rounded-3xl bg-red-50 border border-red-200 p-4 text-sm text-red-600 text-center">{error}</div>
        )}
      </main>

      {/* 레포트 모달 */}
      {reportOpen && result && (
        <ReportModal
          result={result}
          caseId={caseId}
          productName={productNameForReport || "(제품명 미입력)"}
          inspector={reportInspector}
          onProductNameChange={setProductNameForReport}
          onInspectorChange={setReportInspector}
          onClose={() => setReportOpen(false)}
          pipelineInput={pipelineInput}
          stepInput={stepInput}
        />
      )}
    </div>
  );
}

// ── 별지 25호 항목 매핑 ─────────────────────────
// 수입식품안전관리 특별법 시행규칙 [별지 제25호서식] 제2쪽 "신고인 제출서류 가~차"
function getForm25Label(docId: string): string | null {
  const direct: Record<string, string> = {
    "c1": "가",     // 한글표시 포장지/서류
    "g2-1": "나",   // 국외 시험·검사성적서 (정밀검사대상)
    "g2-2": "다",   // 구분유통증명서 등 (GMO)
    "g2-3": "라",   // 유통기한 설정사유서 (OEM)
    "g2-4": "마",   // 수출계획서 (외화획득용)
    "g2-6": "바",   // 영업허가서 (외화획득용원료)
    "g2-7": "사",   // 위생증명서 (협약체결국 수산물)
    "g2-5": "아",   // 수출 위생증명서 (축산물)
  };
  if (direct[docId]) return direct[docId];
  // '차' — 기타 (다이옥신·BSE·ASF·복어·방사성 등 제27조1항10호)
  if (docId.startsWith("g3-") || docId.startsWith("g4-") || docId.startsWith("g5-") || docId.startsWith("g6-")) return "차";
  return null;
}

// 신고제품구분 (별지 25호 1쪽)
function getReportCategory(foodType: string): string {
  if (!foodType) return "-";
  if (foodType.includes("축산") || foodType.includes("식육") || foodType.includes("유가공") || foodType.includes("알가공") || foodType.includes("생햄") || foodType.includes("햄") || foodType.includes("소시지") || foodType.includes("베이컨") || foodType.includes("아이스크림")) return "3. 축산물";
  if (foodType.includes("수산") || foodType.includes("어") || foodType.includes("복어") || foodType.includes("해산")) return "2. 수산물";
  if (foodType.includes("농산") || foodType.includes("임산")) return "1. 농·임산물";
  if (foodType.includes("기구") || foodType.includes("용기") || foodType.includes("포장")) return "6. 기구 또는 용기·포장";
  if (foodType.includes("건강기능")) return "7. 건강기능식품";
  if (foodType.includes("첨가물")) return "5. 식품첨가물";
  return "4. 가공식품";
}

// ── 레포트 모달 ────────────────────────────────

function ReportModal({
  result, caseId, productName, inspector, onProductNameChange, onInspectorChange, onClose,
  pipelineInput, stepInput
}: {
  result: DocsResult;
  caseId: string;
  productName: string;
  inspector: string;
  onProductNameChange: (v: string) => void;
  onInspectorChange: (v: string) => void;
  onClose: () => void;
  pipelineInput: PipelineInput | null;
  stepInput: { origin_country: string; japan_prefecture: string; is_oem: boolean; is_first_import: boolean; has_organic_cert: boolean };
}) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);

  // 인쇄할 섹션 선택 (기본: 전부 포함)
  const SECTION_DEFS: { id: string; label: string; modes: ("inspector" | "request")[] }[] = [
    { id: "product-info",      label: "제품 정보",            modes: ["inspector", "request"] },
    { id: "ingredients",       label: "원재료 정보",           modes: ["inspector", "request"] },
    { id: "request-background",label: "요청 배경",            modes: ["request"] },
    { id: "summary",           label: "요약",                modes: ["inspector", "request"] },
    { id: "submit-docs",       label: "필요 서류 목록",        modes: ["inspector", "request"] },
    { id: "keep-docs",         label: "영업자 보관 서류",      modes: ["inspector"] },
    { id: "warnings",          label: "확인 필요 사항",        modes: ["inspector"] },
    { id: "disclaimer",        label: "면책 고지 / 서명란",    modes: ["inspector", "request"] },
  ];
  const [includedSections, setIncludedSections] = useState<Set<string>>(new Set(SECTION_DEFS.map(s => s.id)));
  const toggleSection = (id: string) => {
    setIncludedSections(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const includeAll = () => setIncludedSections(new Set(SECTION_DEFS.map(s => s.id)));
  const excludeAll = () => setIncludedSections(new Set());
  const isIncluded = (id: string) => includedSections.has(id);

  // 섹션이 제외됐을 때 화면에 표시할 placeholder (인쇄 시 완전히 숨김)
  const ExcludedPlaceholder = ({ id }: { id: string }) => {
    const label = SECTION_DEFS.find(s => s.id === id)?.label || id;
    return (
      <div className="no-print mb-6 border-2 border-dashed border-gray-300 rounded-xl p-4 text-center bg-gray-50/50">
        <p className="text-xs text-gray-400 font-medium">
          <span className="font-semibold text-gray-500">「{label}」</span> 섹션은 인쇄에서 제외됩니다.
          <button
            onClick={() => toggleSection(id)}
            className="ml-2 px-2 py-0.5 bg-blue-600 text-white text-[10px] font-semibold rounded-full hover:bg-blue-700"
          >
            다시 포함
          </button>
        </p>
      </div>
    );
  };

  // 레포트 모드: 담당자 체크리스트 vs 제조사 요청서
  const [mode, setMode] = useState<"inspector" | "request">("inspector");
  // 요청서 모드 추가 필드
  const [recipient, setRecipient] = useState("");
  const [sender, setSender] = useState("관세법인 SAMC");
  const [senderContact, setSenderContact] = useState("");
  const [deadline, setDeadline] = useState("");
  const [docNumber, setDocNumber] = useState("");

  const now = new Date();
  const dateStr = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
  const timeStr = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;

  const handlePrint = () => {
    // 제품명 미입력 경고
    const clean = (productName || "").trim();
    if (!clean || clean === "(제품명 미입력)") {
      const ok = window.confirm(
        "제품명이 입력되지 않았습니다.\n그대로 인쇄하면 파일명이 '수입신고서류_...'로 저장됩니다.\n\n그대로 진행할까요? (취소하면 제품명 입력창으로 이동)"
      );
      if (!ok) return;
    }
    // 파일명 제품별로 구분되게 (브라우저는 document.title을 PDF 기본 파일명으로 사용)
    const originalTitle = document.title;
    const cleanProductName = clean.replace(/[^\w가-힣\s]/g, "").replace(/\s+/g, "_") || "수입신고서류";
    const modeLabel = mode === "inspector" ? "체크리스트" : "제조사요청서";
    document.title = `SAMC_${cleanProductName}_${modeLabel}_${dateStr}`;

    const restore = () => {
      document.title = originalTitle;
      window.removeEventListener("afterprint", restore);
    };
    window.addEventListener("afterprint", restore);
    // 안전장치: 5초 후 자동 복구 (afterprint 이벤트 미지원 브라우저 대비)
    setTimeout(restore, 5000);

    window.print();
  };

  if (!mounted) return null;

  const modalContent = (
    <div
      className="report-modal-overlay fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-6 overflow-y-auto"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="report-modal-content bg-white rounded-2xl max-w-[210mm] w-full max-h-[90vh] overflow-y-auto p-12 relative">
        {/* 인쇄 시 숨김 — 모드 토글 + 인쇄 옵션 + 닫기 */}
        <div className="no-print sticky top-0 z-10 bg-white pt-2 pb-3 -mx-12 px-12 mb-4 border-b border-gray-100 space-y-2">
          {/* 상단: 모드 토글 + 버튼 */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex gap-1 p-1 bg-gray-100 rounded-full">
              <button
                onClick={() => setMode("inspector")}
                className={`px-4 py-1.5 text-xs font-semibold rounded-full transition-all ${
                  mode === "inspector" ? "bg-gray-900 text-white" : "text-gray-500 hover:text-gray-800"
                }`}
              >
                📋 담당자 체크리스트
              </button>
              <button
                onClick={() => setMode("request")}
                className={`px-4 py-1.5 text-xs font-semibold rounded-full transition-all ${
                  mode === "request" ? "bg-blue-600 text-white" : "text-gray-500 hover:text-gray-800"
                }`}
              >
                ✉️ 제조사 요청서
              </button>
            </div>
            <div className="flex gap-2">
              <button
                onClick={handlePrint}
                className="px-4 py-2 bg-gray-900 text-white text-xs font-semibold rounded-full hover:bg-gray-800 transition-all"
              >
                📄 인쇄 / PDF 저장
              </button>
              <button
                onClick={onClose}
                className="px-3 py-2 bg-gray-100 text-gray-600 text-xs font-semibold rounded-full hover:bg-gray-200 transition-all"
              >
                닫기
              </button>
            </div>
          </div>
          {/* 하단: 인쇄할 섹션 선택 */}
          {(() => {
            const visibleSections = SECTION_DEFS.filter(s => s.modes.includes(mode));
            const allVisibleIncluded = visibleSections.every(s => includedSections.has(s.id));
            const toggleAllVisible = () => {
              if (allVisibleIncluded) {
                // 전체 해제 (현재 모드 섹션만)
                setIncludedSections(prev => {
                  const next = new Set(prev);
                  visibleSections.forEach(s => next.delete(s.id));
                  return next;
                });
              } else {
                // 전체 선택 (현재 모드 섹션만)
                setIncludedSections(prev => {
                  const next = new Set(prev);
                  visibleSections.forEach(s => next.add(s.id));
                  return next;
                });
              }
            };
            return (
              <div className="text-xs bg-blue-50/60 border border-blue-100 rounded-2xl px-4 py-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-blue-700">📑 인쇄할 섹션 선택</span>
                  <button
                    onClick={toggleAllVisible}
                    className={`px-3 py-1 text-[11px] font-semibold rounded-full transition-all ${
                      allVisibleIncluded
                        ? "bg-gray-900 text-white hover:bg-gray-800"
                        : "bg-blue-600 text-white hover:bg-blue-700"
                    }`}
                  >
                    {allVisibleIncluded ? "전체 해제" : "전체 선택"}
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {visibleSections.map(s => {
                    const on = includedSections.has(s.id);
                    return (
                      <label
                        key={s.id}
                        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border cursor-pointer transition-all text-[11px] ${
                          on ? "bg-blue-600 text-white border-blue-600" : "bg-white text-gray-500 border-gray-300 hover:bg-gray-50"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={on}
                          onChange={() => toggleSection(s.id)}
                          className="w-3 h-3"
                        />
                        <span className="font-semibold">{s.label}</span>
                      </label>
                    );
                  })}
                </div>
                <p className="text-[10px] text-gray-500 mt-2">
                  체크 해제된 섹션은 인쇄 시 자동 제외됩니다. (화면에서도 반투명 표시)
                </p>
              </div>
            );
          })()}
        </div>

        {/* ─ 레포트 헤더 (모드별) ─ */}
        {mode === "inspector" ? (
          <div className="border-b-2 border-gray-900 pb-4 mb-6 avoid-break">
            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
              SAMC · 수입식품 검역 어드바이저
            </p>
            <h1 className="text-2xl font-bold tracking-tight text-gray-900 mt-1">
              수입신고 서류 준비 체크리스트 <span className="text-xs font-normal text-gray-400 ml-2">(담당자 내부용)</span>
            </h1>
            <p className="text-xs text-gray-500 mt-2">
              생성일시: {dateStr} {timeStr} · 건 번호: {caseId}
            </p>
            <p className="text-[11px] text-gray-600 mt-2 leading-relaxed">
              본 체크리스트는 유니패스 전자신고 시 첨부해야 할 서류를 사전 점검하기 위한 담당자 내부 자료입니다.
              별지 제25호서식 제2쪽의 "신고인 제출서류 (가)~(차)" 항목과 매핑됩니다.
            </p>
          </div>
        ) : (
          <div className="border-b-2 border-blue-900 pb-4 mb-6 avoid-break">
            <div className="flex justify-between items-start mb-3">
              <p className="text-[10px] font-bold uppercase tracking-widest text-blue-700">
                관세법인 SAMC · Document Request Form
              </p>
              <div className="text-right text-xs text-gray-600">
                <p>문서번호: <input value={docNumber} onChange={e => setDocNumber(e.target.value)} className="no-print border-b border-gray-300 w-32 text-xs px-1" placeholder="SAMC-2026-___"/><span className="print-only">{docNumber || "SAMC-2026-____"}</span></p>
                <p className="mt-1">일자: {dateStr}</p>
              </div>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-gray-900 mt-2">
              수입식품 필요 서류 요청서
            </h1>
            <p className="text-sm font-light text-gray-600 mt-1">Request for Import Document Submission</p>
            <div className="mt-4 grid grid-cols-2 gap-4 text-xs">
              <div className="border border-gray-300 rounded p-3">
                <p className="font-bold text-gray-500 text-[10px] uppercase mb-1">수신 (To)</p>
                <input
                  value={recipient}
                  onChange={e => setRecipient(e.target.value)}
                  className="no-print w-full border-b border-gray-200 text-sm px-1 py-1"
                  placeholder="해외 제조사명 / 담당자 (예: Fratelli Beretta S.p.A.)"
                />
                <span className="print-only text-sm">{recipient || "(수신자 미입력)"}</span>
              </div>
              <div className="border border-gray-300 rounded p-3">
                <p className="font-bold text-gray-500 text-[10px] uppercase mb-1">발신 (From)</p>
                <input
                  value={sender}
                  onChange={e => setSender(e.target.value)}
                  className="no-print w-full border-b border-gray-200 text-sm px-1 py-1"
                  placeholder="관세법인 SAMC"
                />
                <span className="print-only text-sm">{sender}</span>
                <input
                  value={senderContact}
                  onChange={e => setSenderContact(e.target.value)}
                  className="no-print w-full border-b border-gray-200 text-xs px-1 py-1 mt-1"
                  placeholder="담당자 · 이메일 · 전화"
                />
                <span className="print-only text-xs block mt-1 text-gray-600">{senderContact || "(연락처 미입력)"}</span>
              </div>
            </div>
          </div>
        )}

        {/* ─ 요청 배경 (요청서 모드 전용) ─ */}
        {mode === "request" && !isIncluded("request-background") && <ExcludedPlaceholder id="request-background" />}
        {mode === "request" && isIncluded("request-background") && (
          <section className="mb-6 avoid-break">
            <h2 className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-2">요청 배경</h2>
            <div className="text-xs text-gray-700 leading-relaxed border border-gray-200 bg-gray-50 rounded p-4">
              <p>
                귀사께서 제조·공급하시는 <strong>{productName}</strong>({result.food_type}, 제조국: {result.origin_country})을(를)
                한국에 수입하기 위해서는 한국 <strong>수입식품안전관리 특별법 시행규칙 제27조</strong>에 따라 아래 서류들이
                필요합니다. 원활한 수입 통관을 위해 관련 서류를 <strong>회신 기한 내 영문 또는 한글로</strong> 보내주시기 바랍니다.
              </p>
              <p className="mt-2 text-gray-600">
                한국 식약처는 전자통관시스템(UNI-PASS)을 통해 수입 신고서 및 첨부 서류를 검토하며,
                서류 누락 시 통관이 지연되거나 반송될 수 있습니다.
              </p>
            </div>
            <div className="mt-3 flex gap-4 text-xs">
              <div className="flex-1 border border-gray-300 rounded p-2">
                <p className="font-bold text-gray-500 text-[10px] uppercase">회신 기한 (Deadline)</p>
                <input
                  value={deadline}
                  onChange={e => setDeadline(e.target.value)}
                  className="no-print w-full border-b border-gray-200 text-sm px-1 py-1 mt-1"
                  placeholder="YYYY-MM-DD"
                />
                <span className="print-only text-sm block mt-1">{deadline || "(미입력)"}</span>
              </div>
              <div className="flex-1 border border-gray-300 rounded p-2">
                <p className="font-bold text-gray-500 text-[10px] uppercase">Reference</p>
                <p className="mt-1 text-sm">Republic of Korea · Imported Food Safety Regulation Art.27</p>
              </div>
            </div>
          </section>
        )}

        {/* ─ 제품 정보 (별지 제25호 제1쪽 기반) ─ */}
        {!isIncluded("product-info") && <ExcludedPlaceholder id="product-info" />}
        {isIncluded("product-info") && (
        <section className="mb-6 avoid-break">
          <div className="flex items-baseline justify-between mb-3">
            <h2 className="text-xs font-bold uppercase tracking-widest text-gray-500">제품 정보</h2>
            <p className="text-[10px] text-gray-400">※ 별지 제25호서식 제1쪽 기반</p>
          </div>
          <table className="w-full text-sm border-collapse border border-gray-300">
            <tbody>
              <tr className="border-b border-gray-200">
                <td className="py-2 px-3 bg-gray-50 text-gray-600 w-36 font-semibold border-r border-gray-200">
                  제품명 (한글명)
                  <span className="text-red-500 ml-1">*</span>
                </td>
                <td className="py-2 px-3" colSpan={3}>
                  <input
                    value={productName === "(제품명 미입력)" ? "" : productName}
                    onChange={(e) => onProductNameChange(e.target.value)}
                    className={`no-print w-full border rounded px-2 py-1 text-sm ${
                      !productName || productName === "(제품명 미입력)"
                        ? "border-red-300 bg-red-50"
                        : "border-gray-200"
                    }`}
                    placeholder="제품명 입력 (PDF 파일명에 사용됩니다)"
                  />
                  <span className="print-only">{productName === "(제품명 미입력)" ? "___________________" : productName}</span>
                </td>
              </tr>
              <tr className="border-b border-gray-200">
                <td className="py-2 px-3 bg-gray-50 text-gray-600 font-semibold border-r border-gray-200">신고제품구분</td>
                <td className="py-2 px-3 border-r border-gray-200">{getReportCategory(result.food_type)}</td>
                <td className="py-2 px-3 bg-gray-50 text-gray-600 w-28 font-semibold border-r border-gray-200">식품유형</td>
                <td className="py-2 px-3">{result.food_type || "-"}</td>
              </tr>
              <tr className="border-b border-gray-200">
                <td className="py-2 px-3 bg-gray-50 text-gray-600 font-semibold border-r border-gray-200">생산국 (제조국)</td>
                <td className="py-2 px-3 border-r border-gray-200">{result.origin_country}{stepInput.japan_prefecture ? ` (${stepInput.japan_prefecture})` : ""}</td>
                <td className="py-2 px-3 bg-gray-50 text-gray-600 font-semibold border-r border-gray-200">수출국</td>
                <td className="py-2 px-3">
                  <input
                    defaultValue={result.origin_country}
                    className="no-print w-full border border-gray-200 rounded px-2 py-1 text-sm"
                    placeholder="수출국 (제조국과 다를 경우 수정)"
                  />
                  <span className="print-only">{result.origin_country}</span>
                </td>
              </tr>
              <tr className="border-b border-gray-200">
                <td className="py-2 px-3 bg-gray-50 text-gray-600 font-semibold border-r border-gray-200">최초 수입 여부</td>
                <td className="py-2 px-3 border-r border-gray-200">{result.is_first_import ? "예 (최초 수입)" : "아니오 (재수입)"}</td>
                <td className="py-2 px-3 bg-gray-50 text-gray-600 font-semibold border-r border-gray-200">주문자상표부착 (OEM)</td>
                <td className="py-2 px-3">{stepInput.is_oem ? "예" : "아니오"}</td>
              </tr>
              <tr>
                <td className="py-2 px-3 bg-gray-50 text-gray-600 font-semibold border-r border-gray-200">유기인증 (95% 이상)</td>
                <td className="py-2 px-3 border-r border-gray-200" colSpan={3}>{stepInput.has_organic_cert ? "예 (유기인증 있음)" : "아니오"}</td>
              </tr>
            </tbody>
          </table>
        </section>
        )}

        {/* ─ 원재료 정보 (별지 제25호 제2쪽 기반) ─ */}
        {!isIncluded("ingredients") && <ExcludedPlaceholder id="ingredients" />}
        {isIncluded("ingredients") && pipelineInput && pipelineInput.product_keywords.length > 0 && (
          <section className="mb-6 avoid-break">
            <div className="flex items-baseline justify-between mb-3">
              <h2 className="text-xs font-bold uppercase tracking-widest text-gray-500">원재료 정보</h2>
              <p className="text-[10px] text-gray-400">※ 별지 제25호서식 제2쪽 기반</p>
            </div>
            <table className="w-full text-sm border-collapse border border-gray-300">
              <thead>
                <tr className="bg-gray-100 text-xs">
                  <th className="py-1.5 px-2 border-r border-gray-200 w-12">No.</th>
                  <th className="py-1.5 px-2 border-r border-gray-200 text-left">원재료명칭</th>
                  <th className="py-1.5 px-2 w-28">배합비율 (%)</th>
                </tr>
              </thead>
              <tbody>
                {pipelineInput.product_keywords.slice(0, 20).map((kw, i) => (
                  <tr key={i} className="border-b border-gray-200">
                    <td className="py-1.5 px-2 text-center border-r border-gray-200">{i + 1}</td>
                    <td className="py-1.5 px-2 border-r border-gray-200">{kw}</td>
                    <td className="py-1.5 px-2 text-center text-gray-400">—</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        {/* ─ 요약 ─ */}
        {!isIncluded("summary") && <ExcludedPlaceholder id="summary" />}
        {isIncluded("summary") && (
        <section className="mb-6 avoid-break">
          <h2 className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-3">요약</h2>
          <div className="flex gap-4">
            <div className="flex-1 border-2 border-gray-900 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold">{result.total_submit}</p>
              <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">제출 서류</p>
            </div>
            <div className="flex-1 border-2 border-gray-400 rounded-lg p-3 text-center">
              <p className="text-2xl font-bold">{result.total_keep}</p>
              <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">보관 서류</p>
            </div>
          </div>
        </section>
        )}

        {/* ─ 제출 서류 (모드별) ─ */}
        {!isIncluded("submit-docs") && <ExcludedPlaceholder id="submit-docs" />}
        {isIncluded("submit-docs") && result.submit_docs.length > 0 && (
          <section className="mb-6">
            <div className="flex items-baseline justify-between mb-3">
              <h2 className="text-xs font-bold uppercase tracking-widest text-gray-500">
                {mode === "inspector"
                  ? `유니패스 첨부 서류 (${result.submit_docs.length}건)`
                  : `필요 서류 목록 (${result.submit_docs.length}건)`}
              </h2>
              <p className="text-[10px] text-gray-400">※ 별지 제25호서식 제2쪽 신고인 제출서류 (가)~(차)</p>
            </div>
            <ol className="space-y-3">
              {result.submit_docs.map((doc, i) => {
                const label = getForm25Label(doc.id);
                const issuerInfo = getIssuerInfo(doc as any);
                const detailedReason = buildDetailedReason(doc as any, {
                  food_type: result.food_type,
                  origin_country: result.origin_country,
                  is_oem: stepInput.is_oem,
                  is_first_import: result.is_first_import,
                  has_organic_cert: stepInput.has_organic_cert,
                  product_keywords: pipelineInput?.product_keywords || [],
                });
                return (
                  <li key={doc.id} className={`border rounded-lg avoid-break ${mode === "request" ? "border-blue-200 p-4" : "border-gray-300 p-3"}`}>
                    {mode === "inspector" ? (
                      // 📋 담당자 모드: 간결한 체크리스트 (수기 체크용)
                      <div className="flex items-start gap-2">
                        <input type="checkbox" className="mt-1 w-4 h-4" />
                        <div className="flex-1">
                          <div className="flex items-center gap-2 flex-wrap mb-1">
                            {label && (
                              <span className="px-2 py-0.5 bg-gray-900 text-white text-[10px] font-bold rounded">
                                별지 제25호 ({label})
                              </span>
                            )}
                            <span className="text-[10px] text-gray-400">#{i + 1}</span>
                          </div>
                          <p className="font-semibold text-sm">{doc.doc_name}</p>
                          <p className="text-xs text-gray-500 mt-1">{doc.law_source.split(";")[0].trim()}</p>
                          {doc.match_reason && (
                            <p className="text-xs text-gray-600 mt-1 leading-relaxed">{doc.match_reason}</p>
                          )}
                          <div className="mt-2 grid grid-cols-3 gap-2 text-[10px] text-gray-500">
                            <span>📨 요청일: ________</span>
                            <span>📥 접수일: ________</span>
                            <span>✅ 업로드: ________</span>
                          </div>
                        </div>
                      </div>
                    ) : (
                      // ✉️ 요청서 모드: 상세 사유 + 발급처 + 형식
                      <div>
                        <div className="flex items-center gap-2 flex-wrap mb-2">
                          <span className="px-2.5 py-0.5 bg-blue-600 text-white text-[10px] font-bold rounded">
                            Document #{i + 1}
                          </span>
                          {label && (
                            <span className="px-2 py-0.5 bg-gray-900 text-white text-[10px] font-bold rounded">
                              Form 25 — ({label})
                            </span>
                          )}
                        </div>
                        <h3 className="font-bold text-sm text-gray-900 mb-1">{doc.doc_name}</h3>
                        <p className="text-[11px] text-violet-600 font-light mb-2">근거 법령: {doc.law_source.split(";")[0].trim()}</p>

                        <div className="mt-3 space-y-2 text-xs">
                          <div>
                            <p className="font-bold text-gray-500 text-[10px] uppercase tracking-wider mb-1">왜 필요한가 (Why required)</p>
                            <p className="text-gray-700 leading-relaxed">{detailedReason}</p>
                          </div>
                          <div className="grid grid-cols-2 gap-3 mt-2 pt-2 border-t border-gray-100">
                            <div>
                              <p className="font-bold text-gray-500 text-[10px] uppercase tracking-wider mb-1">발급처 (Issuer)</p>
                              <p className="text-gray-700 leading-relaxed">{issuerInfo.issuer}</p>
                            </div>
                            <div>
                              <p className="font-bold text-gray-500 text-[10px] uppercase tracking-wider mb-1">형식 요건 (Format)</p>
                              <p className="text-gray-700 leading-relaxed">{issuerInfo.format}</p>
                            </div>
                          </div>
                          {issuerInfo.note && (
                            <div className="mt-2 pt-2 border-t border-gray-100">
                              <p className="font-bold text-gray-500 text-[10px] uppercase tracking-wider mb-1">참고사항 (Note)</p>
                              <p className="text-gray-700 leading-relaxed">{issuerInfo.note}</p>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </li>
                );
              })}
            </ol>
          </section>
        )}

        {/* ─ 보관 서류 ─ */}
        {!isIncluded("keep-docs") && result.keep_docs.length > 0 && mode === "inspector" && <ExcludedPlaceholder id="keep-docs" />}
        {isIncluded("keep-docs") && result.keep_docs.length > 0 && (
          <section className="mb-6">
            <div className="flex items-baseline justify-between mb-3">
              <h2 className="text-xs font-bold uppercase tracking-widest text-gray-500">
                영업자 보관 서류 ({result.keep_docs.length}건)
              </h2>
              <p className="text-[10px] text-gray-400">※ 제출 대상 아님 · 식약처 요청 시 제시</p>
            </div>
            <ol className="space-y-3">
              {result.keep_docs.map((doc, i) => (
                <li key={doc.id} className="border border-gray-300 bg-gray-50 rounded-lg p-3 avoid-break">
                  <div className="flex items-start gap-2">
                    <input type="checkbox" className="mt-1 w-4 h-4" />
                    <div className="flex-1">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className="px-2 py-0.5 bg-gray-500 text-white text-[10px] font-bold rounded">보관</span>
                        <span className="text-[10px] text-gray-400">#{i + 1}</span>
                      </div>
                      <p className="font-semibold text-sm">{doc.doc_name}</p>
                      <p className="text-xs text-gray-500 mt-1">{doc.law_source.split(";")[0].trim()}</p>
                      {doc.match_reason && (
                        <p className="text-xs text-gray-600 mt-1 leading-relaxed">{doc.match_reason}</p>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        )}

        {/* ─ 경고 ─ */}
        {!isIncluded("warnings") && result.warnings && result.warnings.length > 0 && mode === "inspector" && <ExcludedPlaceholder id="warnings" />}
        {isIncluded("warnings") && result.warnings && result.warnings.length > 0 && (
          <section className="mb-6 avoid-break">
            <h2 className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-3">확인 필요 사항</h2>
            <ul className="space-y-2 border border-gray-300 rounded-lg p-4 bg-gray-50">
              {result.warnings.map((w, i) => (
                <li key={i} className="text-xs text-gray-700 leading-relaxed">• {w}</li>
              ))}
            </ul>
          </section>
        )}

        {/* ─ 면책 고지 + 서명 (모드별) ─ */}
        {!isIncluded("disclaimer") && <ExcludedPlaceholder id="disclaimer" />}
        {isIncluded("disclaimer") && mode === "inspector" ? (
          <section className="mt-8 pt-4 border-t border-gray-300 avoid-break">
            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500 mb-2">레포트 성격 · 면책 고지</p>
            <p className="text-xs text-gray-600 leading-relaxed">
              본 체크리스트는 <strong className="font-semibold">담당자가 유니패스 전자신고 전 서류 준비 상태를 점검</strong>하기 위한 내부 자료입니다.
              식약처 공식 제출용이 아니며, 최종 판단은 담당자가 식약처 고시·시행규칙을 직접 확인 후 결정하시기 바랍니다.
              AI 기반 어드바이저의 참고 결과이며, 법령 개정 시 서류 목록이 변경될 수 있습니다 ({dateStr} 기준).
            </p>
            <div className="mt-6 grid grid-cols-3 gap-6 text-xs">
              <div>
                <p className="text-gray-500 font-semibold mb-1">담당자</p>
                <div className="border-b border-gray-400 pb-1 h-8">&nbsp;</div>
                <p className="text-[10px] text-gray-400 mt-1">일자: ____________</p>
              </div>
              <div>
                <p className="text-gray-500 font-semibold mb-1">검토자</p>
                <div className="border-b border-gray-400 pb-1 h-8">&nbsp;</div>
                <p className="text-[10px] text-gray-400 mt-1">일자: ____________</p>
              </div>
              <div>
                <p className="text-gray-500 font-semibold mb-1">유니패스 신고일</p>
                <div className="border-b border-gray-400 pb-1 h-8">&nbsp;</div>
                <p className="text-[10px] text-gray-400 mt-1">신고번호: __________</p>
              </div>
            </div>
          </section>
        ) : isIncluded("disclaimer") && mode === "request" ? (
          <section className="mt-8 pt-4 border-t border-blue-900 avoid-break">
            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500 mb-2">Request Summary · 요청 요약</p>
            <p className="text-xs text-gray-700 leading-relaxed mb-4">
              We kindly request that you prepare the above-listed documents by the specified deadline
              and send them to the sender via email or secure file transfer.
              Should you have any questions regarding the document requirements or issuance procedures,
              please contact the sender directly.
              <br/><br/>
              상기 서류를 회신 기한 내 준비하시어 이메일 또는 안전한 파일 전송 방식으로 발신자에게
              보내주시기 바랍니다. 서류 요건이나 발급 절차에 관해 문의사항이 있으시면 발신자에게 직접 연락 바랍니다.
            </p>
            <div className="mt-6 grid grid-cols-2 gap-8 text-xs">
              <div className="border border-gray-300 rounded p-3">
                <p className="text-gray-500 font-semibold mb-1 text-[10px] uppercase">발신 담당 서명 (Signed by)</p>
                <div className="border-b border-gray-400 pb-1 h-10 mt-3">&nbsp;</div>
                <p className="text-[10px] text-gray-400 mt-2">{sender} · {dateStr}</p>
              </div>
              <div className="border border-gray-300 rounded p-3 bg-gray-50">
                <p className="text-gray-500 font-semibold mb-1 text-[10px] uppercase">수신 확인 (Acknowledged by)</p>
                <div className="border-b border-gray-400 pb-1 h-10 mt-3">&nbsp;</div>
                <p className="text-[10px] text-gray-400 mt-2">회신 예정일: {deadline || "____________"}</p>
              </div>
            </div>
            <p className="text-[10px] text-gray-500 mt-6 text-center">
              — End of Document Request · 문서 끝 —
            </p>
          </section>
        ) : null}
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
}
