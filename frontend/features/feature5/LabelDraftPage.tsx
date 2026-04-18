"use client";

import { apiClient } from "@/services/apiClient";
import { useState, useRef, useEffect } from "react";
import { useParams } from "next/navigation";

// ── 타입 ─────────────────────────────────────────────────────────────────────

interface Phase1Item {
  field: string;
  law_ref: string;
  law_requirement: string;
  document_value: string | null;
  status: "pass" | "fail" | "unclear";
  note: string;
}

interface Phase2Validation {
  field: string;
  phase1_status: string;
  ai_status: "pass" | "fail" | "unclear";
  cross_result: "agree" | "disagree" | "additional_issue";
  ai_note: string;
}

interface AdditionalIssue {
  field: string;
  issue: string;
  severity: "error" | "warning" | "info";
}

type Draft = Record<string, unknown>;

interface Result {
  phase1: { items: Phase1Item[] };
  phase2: {
    validation: Phase2Validation[];
    additional_issues: AdditionalIssue[];
    draft: Draft;
  };
}

type Step = "idle" | "generating_p1" | "generating_p2" | "done" | "error";
type FilterKey = "all" | "fail" | "unclear" | "disagree";
type ReportFormat = "docx" | "pdf";

interface LawChunk {
  law_name: string;
  chunk_index: number | null;
  content: string;
  score: number;
  extended?: boolean;
  chunk_range?: [number, number] | null;
}

interface LawSearchResponse {
  query: string;
  results: LawChunk[];
  count: number;
  context_window?: number;
}

interface LawModalState {
  isOpen: boolean;
  loading: boolean;
  query: string;
  lawRef: string;
  results: LawChunk[];
  errorMsg: string;
}

// ── 상수 ─────────────────────────────────────────────────────────────────────

const STATUS_ICON = {
  pass:    { color: "text-emerald-600 bg-emerald-50 border-emerald-200", label: "적합" },
  fail:    { color: "text-red-600 bg-red-50 border-red-200",             label: "부적합" },
  unclear: { color: "text-amber-600 bg-amber-50 border-amber-200",       label: "확인필요" },
};

const CROSS_BADGE = {
  agree:            { color: "bg-emerald-100 text-emerald-700", label: "일치" },
  disagree:         { color: "bg-red-100 text-red-700",         label: "불일치" },
  additional_issue: { color: "bg-amber-100 text-amber-700",     label: "추가이슈" },
};

const SEVERITY_STYLE = {
  error:   "border-red-200 bg-red-50 text-red-700",
  warning: "border-amber-200 bg-amber-50 text-amber-700",
  info:    "border-blue-200 bg-blue-50 text-blue-700",
};

const DRAFT_LABELS: Record<string, string> = {
  product_name:     "제품명",
  food_type:        "식품유형",
  ingredients:      "원재료명 및 함량",
  net_weight:       "내용량",
  expiry:           "소비기한",
  storage:          "보관방법",
  manufacturer:     "제조사",
  importer:         "수입자",
  allergy:          "알레르기",
  gmo:              "GMO",
  country_of_origin:"원산지",
};

const MULTILINE_FIELDS = new Set<string>([
  "ingredients",
  "allergy",
  "manufacturer",
  "importer",
]);

// ── 유틸 ─────────────────────────────────────────────────────────────────────

function toSafeString(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) {
    return v.map((item) => toSafeString(item)).join(", ");
  }
  if (typeof v === "object") {
    try {
      return JSON.stringify(v, null, 2);
    } catch {
      return "[object]";
    }
  }
  return String(v);
}

function extractFilename(contentDisposition: string | null, fallback: string): string {
  if (!contentDisposition) return fallback;

  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match && utf8Match[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch { /* */ }
  }

  const asciiMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
  if (asciiMatch && asciiMatch[1]) {
    return asciiMatch[1];
  }

  return fallback;
}

function triggerBlobDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

function buildLawQuery(lawRef: string, lawRequirement: string): string {
  const parts = [lawRef, lawRequirement].filter((p) => p && p.trim());
  return parts.join(" ").slice(0, 500);
}

// 🅑 가독성 후처리 — 청킹된 원문을 사람이 읽기 편하게 정리
function prettifyLawContent(raw: string): string {
  if (!raw) return "";

  let text = raw;

  // 조항 번호(제N조, 제N조의M) 앞에 빈 줄 삽입
  text = text.replace(
    /([가-힣a-zA-Z0-9.!?\)])\s*(제\d+조(?:의\d+)?)/g,
    "$1\n\n$2"
  );

  // 항 번호(제N항) 앞에 줄바꿈
  text = text.replace(
    /([가-힣a-zA-Z0-9.!?\)])\s*(제\d+항)/g,
    "$1\n$2"
  );

  // 호(아라비아 숫자 + 마침표 + 공백) 앞에 줄바꿈
  text = text.replace(
    /([가-힣]{2,})\s+(\d+\.\s+[가-힣])/g,
    "$1\n$2"
  );

  // 연속된 공백(탭 포함) 정리
  text = text.replace(/[ \t]{2,}/g, " ");

  // 연속된 줄바꿈 3개 이상 → 2개로 축소
  text = text.replace(/\n{3,}/g, "\n\n");

  return text.trim();
}

// ── 컴포넌트 ─────────────────────────────────────────────────────────────────

export default function LabelPage() {
  const params = useParams();
  const caseId = params.id as string;

  const [step, setStep]           = useState<Step>("idle");
  const [foodType, setFoodType]   = useState("");
  const [result, setResult]       = useState<Result | null>(null);
  const [errorMsg, setErrorMsg]   = useState("");
  const [confirmedBy, setConfirmedBy] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [expandedField, setExpandedField] = useState<string | null>(null);

  const [activeFilter, setActiveFilter] = useState<FilterKey>("all");

  const [editedDraft, setEditedDraft] = useState<Record<string, string>>({});
  const [originalDraftStr, setOriginalDraftStr] = useState<Record<string, string>>({});

  const [downloading, setDownloading] = useState<ReportFormat | null>(null);

  const [lawModal, setLawModal] = useState<LawModalState>({
    isOpen: false,
    loading: false,
    query: "",
    lawRef: "",
    results: [],
    errorMsg: "",
  });

  // 🅐 모달 내 펼침 상태
  const [expandedChunks, setExpandedChunks] = useState<Set<number>>(new Set());

  // 🅔 복사 피드백
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);

  const lawCacheRef = useRef<Map<string, LawChunk[]>>(new Map());
  const additionalIssuesRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (result?.phase2?.draft) {
      const normalized: Record<string, string> = {};
      for (const [k, v] of Object.entries(result.phase2.draft)) {
        normalized[k] = toSafeString(v);
      }
      setOriginalDraftStr(normalized);
      setEditedDraft({ ...normalized });
    }
  }, [result]);

  useEffect(() => {
    if (!lawModal.isOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        closeLawModal();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lawModal.isOpen]);

  const p1Items   = result?.phase1.items ?? [];
  const p2Items   = result?.phase2.validation ?? [];
  const issues    = result?.phase2.additional_issues ?? [];
  const failCount = p1Items.filter((i) => i.status === "fail").length;
  const unclearCount = p1Items.filter((i) => i.status === "unclear").length;
  const disagreeCount = p2Items.filter((v) => v.cross_result === "disagree").length;
  const errorCount = issues.filter((i) => i.severity === "error").length;

  const filteredItems = p1Items.filter((item) => {
    if (activeFilter === "all") return true;
    if (activeFilter === "fail") return item.status === "fail";
    if (activeFilter === "unclear") return item.status === "unclear";
    if (activeFilter === "disagree") {
      const v2 = p2Items.find((v) => v.field === item.field);
      return v2?.cross_result === "disagree";
    }
    return true;
  });

  function isFieldModified(key: string): boolean {
    const original = (originalDraftStr[key] ?? "").trim();
    const edited = (editedDraft[key] ?? "").trim();
    return original !== edited;
  }

  const modifiedCount = Object.keys(originalDraftStr).filter(isFieldModified).length;

  function toggleFilter(key: FilterKey) {
    setActiveFilter((prev) => (prev === key ? "all" : key));
  }

  function scrollToAdditionalIssues() {
    additionalIssuesRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function updateDraftField(key: string, value: string) {
    setEditedDraft((prev) => ({ ...prev, [key]: value }));
  }

  function restoreOriginalDraft() {
    if (!window.confirm("편집한 내용을 모두 지우고 AI 원본으로 되돌리시겠습니까?")) return;
    setEditedDraft({ ...originalDraftStr });
  }

  // ── 법령 원문 모달 열기 ───────────────────────────────────────────────────
  async function openLawModal(lawRef: string, lawRequirement: string) {
    const query = buildLawQuery(lawRef, lawRequirement);
    if (!query) return;

    // 🅐 첫 번째 결과만 펼친 상태로 시작
    setExpandedChunks(new Set([0]));
    setCopiedIdx(null);

    const cached = lawCacheRef.current.get(query);
    if (cached) {
      setLawModal({
        isOpen: true,
        loading: false,
        query,
        lawRef,
        results: cached,
        errorMsg: "",
      });
      return;
    }

    setLawModal({
      isOpen: true,
      loading: true,
      query,
      lawRef,
      results: [],
      errorMsg: "",
    });

    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
      const url = `${baseUrl}/cases/${caseId}/pipeline/feature/5/law-search`;
      const token = typeof window !== "undefined" ? localStorage.getItem("supabase_token") : null;

      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          query,
          match_count: 3,
          context_window: 1,
        }),
      });

      if (!response.ok) {
        let msg = `법령 검색 실패 (HTTP ${response.status})`;
        try {
          const err = await response.json();
          if (err?.detail) msg = err.detail;
        } catch { /* */ }
        throw new Error(msg);
      }

      const data: LawSearchResponse = await response.json();

      lawCacheRef.current.set(query, data.results);

      setLawModal({
        isOpen: true,
        loading: false,
        query,
        lawRef,
        results: data.results,
        errorMsg: "",
      });
    } catch (e: unknown) {
      setLawModal({
        isOpen: true,
        loading: false,
        query,
        lawRef,
        results: [],
        errorMsg: e instanceof Error ? e.message : "법령 검색 중 오류가 발생했습니다.",
      });
    }
  }

  function closeLawModal() {
    setLawModal((prev) => ({ ...prev, isOpen: false }));
  }

  // 🅐 결과 접기/펼치기 토글
  function toggleChunkExpanded(idx: number) {
    setExpandedChunks((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) {
        next.delete(idx);
      } else {
        next.add(idx);
      }
      return next;
    });
  }

  // 🅔 클립보드 복사
  async function copyChunk(idx: number, chunk: LawChunk) {
    const plain = prettifyLawContent(chunk.content);
    const text = `[${chunk.law_name}]\n\n${plain}`;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        // fallback
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      setCopiedIdx(idx);
      window.setTimeout(() => {
        setCopiedIdx((current) => (current === idx ? null : current));
      }, 2000);
    } catch {
      /* 복사 실패 조용히 무시 */
    }
  }

  // ── 리포트 다운로드 ──────────────────────────────────────────────────────
  async function handleDownloadReport(format: ReportFormat) {
    if (!confirmed) return;
    setErrorMsg("");
    setDownloading(format);

    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
      const url = `${baseUrl}/cases/${caseId}/pipeline/feature/5/report?format=${format}`;
      const token = typeof window !== "undefined" ? localStorage.getItem("supabase_token") : null;

      const response = await fetch(url, {
        method: "GET",
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });

      if (!response.ok) {
        let msg = `다운로드 실패 (HTTP ${response.status})`;
        try {
          const errJson = await response.json();
          if (errJson?.detail) msg = errJson.detail;
        } catch { /* */ }
        throw new Error(msg);
      }

      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition");
      const fallbackName = `한글표시사항_report.${format}`;
      const filename = extractFilename(disposition, fallbackName);

      triggerBlobDownload(blob, filename);
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : "다운로드 중 오류가 발생했습니다.");
    } finally {
      setDownloading(null);
    }
  }

  // ── 시안 생성 ─────────────────────────────────────────────────────────────
  async function handleRun() {
    setErrorMsg("");

    try {
      setStep("generating_p1");

      const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
      const url = `${baseUrl}/cases/${caseId}/pipeline/feature/5/run`;
      const token = typeof window !== "undefined" ? localStorage.getItem("supabase_token") : null;
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ food_type: foodType || null, stream: true }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || `HTTP ${response.status}`);
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();

      let phase1Data: Result["phase1"] | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value);
        const lines = text.split("\n").filter((l) => l.startsWith("data: "));

        for (const line of lines) {
          try {
            const data = JSON.parse(line.slice(6));

            if (data.step === "phase1_done") {
              phase1Data = data.phase1;
              setStep("generating_p2");
            }

            if (data.step === "done" && phase1Data) {
              setResult(data.result);
              setStep("done");
            }

            if (data.error) {
              setErrorMsg(data.error);
              setStep("error");
            }
          } catch { /* */ }
        }
      }
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : "오류가 발생했습니다.");
      setStep("error");
    }
  }

  async function handleConfirm() {
    if (!confirmedBy.trim() || confirmed) return;
    try {
      const payload: { confirmed_by: string; draft?: Record<string, string> } = {
        confirmed_by: confirmedBy.trim(),
      };
      if (modifiedCount > 0) {
        payload.draft = editedDraft;
      }
      await apiClient.patch(`/cases/${caseId}/pipeline/feature/5`, payload);
      setConfirmed(true);
    } catch {
      setErrorMsg("확정 저장에 실패했습니다.");
    }
  }

  function renderP1Row(item: Phase1Item) {
    const st = STATUS_ICON[item.status];
    const v2 = p2Items.find((v) => v.field === item.field);
    const expanded = expandedField === item.field;

    return (
      <div key={item.field} className="border border-slate-200 rounded-xl overflow-hidden">
        <button
          onClick={() => setExpandedField(expanded ? null : item.field)}
          className="w-full flex items-center gap-3 px-4 py-3 bg-white hover:bg-slate-50 transition-colors text-left"
        >
          <span className="text-sm font-semibold text-slate-700 w-32 shrink-0">{item.field}</span>

          <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${st.color}`}>
            1차 {st.label}
          </span>

          {v2 && (
            <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${CROSS_BADGE[v2.cross_result].color}`}>
              AI {CROSS_BADGE[v2.cross_result].label}
            </span>
          )}

          {v2?.cross_result === "disagree" && (
            <span className="text-[11px] font-bold text-red-600 ml-1">⚠ 실무자 확인 필요</span>
          )}

          <svg className={`w-4 h-4 text-slate-400 ml-auto shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`}
            fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7"/>
          </svg>
        </button>

        {expanded && (
          <div className="border-t border-slate-100 bg-slate-50 px-4 py-3 space-y-3 text-xs">
            <div>
              <span className="font-semibold text-slate-500">서류 확인값: </span>
              <span className="text-slate-700">{item.document_value ?? "확인 불가"}</span>
            </div>

            <div className="bg-white border border-slate-200 rounded-lg px-3 py-2">
              <div className="flex items-center justify-between mb-1">
                <div className="font-semibold text-slate-500">법령 근거</div>
                {item.law_ref && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      openLawModal(item.law_ref, item.law_requirement);
                    }}
                    className="text-[11px] font-semibold text-blue-600 hover:text-blue-800 hover:underline flex items-center gap-1"
                    title="Pinecone 에서 법령 원문 검색 (주변 청크 확장)"
                  >
                    📖 원문 보기
                  </button>
                )}
              </div>
              <p className="text-slate-600 font-medium">{item.law_ref}</p>
              <p className="text-slate-500 mt-1">{item.law_requirement}</p>
            </div>

            <div className={`rounded-lg px-3 py-2 border ${st.color}`}>
              <span className="font-semibold">1차 검토 의견: </span>{item.note}
            </div>

            {v2 && (
              <div className={`rounded-lg px-3 py-2 border ${CROSS_BADGE[v2.cross_result].color}`}>
                <span className="font-semibold">AI 교차검증: </span>{v2.ai_note}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  function renderFilterBadge(
    key: FilterKey,
    label: string,
    count: number,
    colorClass: { inactive: string; active: string; hasItems?: string; }
  ) {
    const isActive = activeFilter === key;
    const isZero = count === 0;

    const baseStyle = isZero ? colorClass.inactive : (colorClass.hasItems ?? colorClass.inactive);
    const finalStyle = isActive ? colorClass.active : baseStyle;

    return (
      <button
        onClick={() => toggleFilter(key)}
        disabled={isZero && key !== "all"}
        className={`rounded-lg px-3 py-1.5 border transition-all text-left ${finalStyle} ${
          isZero && key !== "all" ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:shadow-sm"
        } ${isActive ? "shadow-md" : ""}`}
      >
        {label} <strong>{count}{key === "all" ? "개" : "건"}</strong>
        {isActive && <span className="ml-1.5 font-bold">×</span>}
      </button>
    );
  }

  function renderDraftField(key: string) {
    const label = DRAFT_LABELS[key] ?? key;
    const currentValue = editedDraft[key] ?? "";
    const modified = isFieldModified(key);
    const isMultiline = MULTILINE_FIELDS.has(key);

    return (
      <div
        key={key}
        className={`py-3 flex gap-4 transition-colors ${
          modified ? "pl-3 border-l-4 border-blue-400 bg-blue-50/40 rounded-r" : "border-l-4 border-transparent"
        }`}
      >
        <div className="w-28 shrink-0 mt-1.5 flex flex-col gap-1">
          <span className="text-xs font-semibold text-slate-500">{label}</span>
          {modified && (
            <span className="text-[10px] font-semibold text-blue-600 bg-blue-100 px-1.5 py-0.5 rounded-full self-start">
              수정됨
            </span>
          )}
        </div>

        <div className="flex-1">
          {isMultiline ? (
            <textarea
              value={currentValue}
              onChange={(e) => updateDraftField(key, e.target.value)}
              disabled={confirmed}
              placeholder="—"
              rows={2}
              className="w-full text-sm text-slate-900 leading-relaxed bg-white border border-slate-200 rounded-md px-3 py-2 resize-y focus:outline-none focus:ring-2 focus:ring-emerald-400 disabled:bg-slate-50 disabled:text-slate-500 placeholder:text-slate-300"
            />
          ) : (
            <input
              type="text"
              value={currentValue}
              onChange={(e) => updateDraftField(key, e.target.value)}
              disabled={confirmed}
              placeholder="—"
              className="w-full text-sm text-slate-900 leading-relaxed bg-white border border-slate-200 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-400 disabled:bg-slate-50 disabled:text-slate-500 placeholder:text-slate-300"
            />
          )}
        </div>
      </div>
    );
  }

  // ── 법령 원문 모달 ───────────────────────────────────────────────────────
  function renderLawModal() {
    if (!lawModal.isOpen) return null;

    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
        onClick={closeLawModal}
      >
        <div
          className="bg-white rounded-2xl shadow-2xl max-w-3xl w-full max-h-[85vh] flex flex-col"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
            <div>
              <p className="text-xs text-slate-400 mb-0.5">법령 원문 검색 결과</p>
              <h3 className="text-sm font-semibold text-slate-800">{lawModal.lawRef}</h3>
            </div>
            <button
              onClick={closeLawModal}
              className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition-colors"
              aria-label="닫기"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/>
              </svg>
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-5">
            {lawModal.loading && (
              <div className="flex flex-col items-center justify-center py-12 gap-3 text-slate-400">
                <svg className="w-8 h-8 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h5M20 20v-5h-5M4 9a9 9 0 0115.83-3.5M20 15a9 9 0 01-15.83 3.5"/>
                </svg>
                <p className="text-xs">Pinecone 에서 법령 원문을 검색 + 주변 청크 확장 중...</p>
              </div>
            )}

            {!lawModal.loading && lawModal.errorMsg && (
              <div className="rounded-lg px-4 py-3 ds-alert-error text-sm">
                <p className="font-semibold mb-1">법령 원문을 불러오지 못했습니다</p>
                <p className="text-xs">{lawModal.errorMsg}</p>
              </div>
            )}

            {!lawModal.loading && !lawModal.errorMsg && lawModal.results.length === 0 && (
              <div className="text-center py-12 text-sm text-slate-400">
                관련 법령 원문을 찾지 못했습니다.
              </div>
            )}

            {!lawModal.loading && !lawModal.errorMsg && lawModal.results.length > 0 && (
              <>
                <p className="text-[11px] text-slate-400 mb-3">
                  관련도 높은 순으로 {lawModal.results.length}건 · 주변 청크 확장 적용
                </p>

                <div className="space-y-3">
                  {lawModal.results.map((chunk, idx) => {
                    const isExpanded = expandedChunks.has(idx);
                    const isCopied = copiedIdx === idx;

                    // 청크 범위 라벨
                    let chunkLabel = "";
                    if (chunk.chunk_range && chunk.chunk_range.length === 2) {
                      const [start, end] = chunk.chunk_range;
                      chunkLabel = start === end ? `청크 #${start}` : `청크 #${start}–#${end}`;
                    } else if (chunk.chunk_index !== null && chunk.chunk_index !== undefined) {
                      chunkLabel = `청크 #${chunk.chunk_index}`;
                    }

                    // 🅑 가독성 후처리
                    const prettified = prettifyLawContent(chunk.content || "");

                    return (
                      <div
                        key={idx}
                        className="border border-slate-200 rounded-xl overflow-hidden"
                      >
                        {/* 🅐 헤더 — 클릭으로 접기/펼치기 */}
                        <div className="bg-slate-50 border-b border-slate-100 flex items-center">
                          <button
                            type="button"
                            onClick={() => toggleChunkExpanded(idx)}
                            className="flex-1 min-w-0 text-left px-4 py-2.5 hover:bg-slate-100 transition-colors"
                          >
                            <div className="flex items-center gap-2">
                              <svg
                                className={`w-3.5 h-3.5 text-slate-400 shrink-0 transition-transform ${isExpanded ? "rotate-90" : ""}`}
                                fill="none" stroke="currentColor" viewBox="0 0 24 24"
                              >
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7"/>
                              </svg>
                              <div className="flex-1 min-w-0">
                                <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-0.5 flex items-center gap-2 flex-wrap">
                                  <span>#{idx + 1} · 유사도 {(chunk.score * 100).toFixed(1)}%</span>
                                  {chunk.extended && (
                                    <span className="bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded-full normal-case text-[9px]">
                                      ✨ 맥락 확장
                                    </span>
                                  )}
                                  {chunkLabel && (
                                    <span className="text-slate-400 normal-case text-[10px]">
                                      · {chunkLabel}
                                    </span>
                                  )}
                                </p>
                                <p className="text-xs font-semibold text-slate-700 truncate" title={chunk.law_name}>
                                  {chunk.law_name || "(법령명 없음)"}
                                </p>
                              </div>
                            </div>
                          </button>

                          {/* 🅔 복사 버튼 */}
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              copyChunk(idx, chunk);
                            }}
                            className={`shrink-0 px-3 py-2 text-xs font-semibold transition-colors flex items-center gap-1 ${
                              isCopied
                                ? "text-emerald-600"
                                : "text-slate-400 hover:text-slate-700"
                            }`}
                            title="원문을 클립보드에 복사"
                          >
                            {isCopied ? (
                              <>
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7"/>
                                </svg>
                                복사됨
                              </>
                            ) : (
                              <>
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/>
                                </svg>
                                복사
                              </>
                            )}
                          </button>
                        </div>

                        {/* 본문 - 펼쳐진 경우만 표시 */}
                        {isExpanded && (
                          <div className="px-4 py-3 bg-white">
                            <pre className="text-xs text-slate-700 leading-relaxed whitespace-pre-wrap break-words font-sans">
                              {prettified || "(내용 없음)"}
                            </pre>
                          </div>
                        )}

                        {/* 접힌 경우 미리보기 */}
                        {!isExpanded && (
                          <div
                            className="px-4 py-2 text-[11px] text-slate-400 line-clamp-2 cursor-pointer hover:text-slate-600"
                            onClick={() => toggleChunkExpanded(idx)}
                          >
                            {prettified.slice(0, 120).replace(/\n/g, " ")}
                            {prettified.length > 120 ? "..." : ""}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </div>

          <div className="px-6 py-3 border-t border-slate-100 flex items-center justify-between">
            <p className="text-[11px] text-slate-400">
              출처: Pinecone f5-law-chunks · Voyage-3 임베딩 · 주변 청크 ±1 확장
            </p>
            <button
              onClick={closeLawModal}
              className="px-4 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg transition-colors"
            >
              닫기
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="max-w-3xl">
        <p className="text-xs text-slate-400 mb-5">기능 5 · 한글표시사항 2단계 교차검증</p>

        {(step === "idle" || step === "error") && (
          <div className="ds-surface-card p-6 mb-4">
            <h2 className="text-sm font-semibold text-slate-700 mb-2">
              이전 단계 결과를 바탕으로 한글표시사항 시안 생성
            </h2>
            <p className="text-xs text-slate-500 mb-5 leading-relaxed">
              f0 서류 업로드 · F1 수입판정 · F2 식품유형 분류 · F4 라벨 검토 결과를 자동으로 참고하여
              식품 등의 표시기준에 맞는 한글표시사항을 생성합니다.
            </p>

            <div className="mb-4">
              <label className="block text-xs font-semibold text-slate-500 mb-1.5">
                식품유형 <span className="font-normal text-slate-400">(선택 — 비워두면 F2 분류 결과 자동 사용)</span>
              </label>
              <input
                type="text"
                value={foodType}
                onChange={(e) => setFoodType(e.target.value)}
                placeholder="예: 견과류가공품, 과자류"
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-400 placeholder:text-slate-300"
              />
            </div>

            {errorMsg && (
              <div className="rounded-lg px-4 py-3 mb-4 text-sm ds-alert-error">
                {errorMsg}
              </div>
            )}

            <button
              onClick={handleRun}
              className="w-full py-3 bg-emerald-500 text-white text-sm font-semibold rounded-xl hover:bg-emerald-600 transition-colors"
            >
              한글표시사항 시안 생성
            </button>

            <div className="mt-4 grid grid-cols-3 gap-2 text-center">
              {[
                { n: "1", title: "법령 대조", desc: "Pinecone RAG로 관련 법령 조항을 검색해 항목별 적합 여부 판정" },
                { n: "2", title: "AI 교차검증", desc: "Claude가 1차 결과를 재검토해 불일치·누락 항목 발견" },
                { n: "3", title: "시안 생성", desc: "교차검증 결과를 반영한 최종 한글표시사항 시안 출력" },
              ].map((s) => (
                <div key={s.n} className="bg-slate-50 border border-slate-100 rounded-lg p-3">
                  <div className="w-6 h-6 rounded-full bg-emerald-500 text-white text-xs font-bold flex items-center justify-center mx-auto mb-1.5">{s.n}</div>
                  <p className="text-[11px] font-semibold text-slate-700 mb-1">{s.title}</p>
                  <p className="text-[10px] text-slate-400 leading-relaxed">{s.desc}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {(step === "generating_p1" || step === "generating_p2") && (
          <div className="ds-surface-card p-8 text-center">
            <div className="flex justify-center mb-4">
              <svg className="w-8 h-8 text-emerald-500 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h5M20 20v-5h-5M4 9a9 9 0 0115.83-3.5M20 15a9 9 0 01-15.83 3.5"/>
              </svg>
            </div>
            <div className="space-y-2">
              <StepRow active={step === "generating_p1"} done={step === "generating_p2"} label="1단계: 법령/고시 기반 항목 대조 중..." />
              <StepRow active={step === "generating_p2"} done={false} label="2단계: AI 교차검증 및 시안 생성 중..." />
            </div>
            <p className="text-xs text-slate-400 mt-4">서류 분량에 따라 30초~2분 소요될 수 있습니다.</p>
          </div>
        )}

        {step === "done" && result && (
          <>
            <div className={`rounded-xl p-4 mb-5 border ${
              failCount + disagreeCount + errorCount > 0 ? "ds-alert-warning" : "ds-alert-success"
            }`}>
              <p className="text-sm font-semibold text-slate-800 mb-1">교차검증 종합 결과</p>
              <p className="text-[11px] text-slate-500 mb-3">
                뱃지를 클릭하면 해당 항목만 모아볼 수 있습니다.
              </p>
              <div className="flex flex-wrap gap-2 text-xs">
                {renderFilterBadge("all", "검토항목", p1Items.length, {
                  inactive: "bg-white border-slate-200 text-slate-700",
                  active: "bg-slate-700 border-slate-700 text-white",
                })}
                {renderFilterBadge("fail", "법령 부적합", failCount, {
                  inactive: "bg-white border-slate-200 text-slate-700",
                  hasItems: "bg-red-50 border-red-200 text-red-700",
                  active: "bg-red-600 border-red-600 text-white",
                })}
                {renderFilterBadge("unclear", "확인필요", unclearCount, {
                  inactive: "bg-white border-slate-200 text-slate-700",
                  hasItems: "bg-amber-50 border-amber-200 text-amber-700",
                  active: "bg-amber-600 border-amber-600 text-white",
                })}
                {renderFilterBadge("disagree", "1·2차 불일치", disagreeCount, {
                  inactive: "bg-white border-slate-200 text-slate-700",
                  hasItems: "bg-red-50 border-red-200 text-red-700",
                  active: "bg-red-600 border-red-600 text-white",
                })}
                <button
                  onClick={scrollToAdditionalIssues}
                  disabled={errorCount === 0}
                  className={`rounded-lg px-3 py-1.5 border transition-all text-left ${
                    errorCount > 0
                      ? "bg-red-50 border-red-200 text-red-700 cursor-pointer hover:shadow-sm"
                      : "bg-white border-slate-200 text-slate-700 opacity-50 cursor-not-allowed"
                  }`}
                  title={errorCount > 0 ? "클릭하면 AI 추가 발견 이슈로 이동" : undefined}
                >
                  추가 오류 <strong>{errorCount}건</strong>
                  {errorCount > 0 && <span className="ml-1 text-[10px]">↓</span>}
                </button>
              </div>
            </div>

            <div className="mb-4">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-slate-700">
                  항목별 교차검증 결과
                  {activeFilter !== "all" && (
                    <span className="ml-2 text-xs font-normal text-slate-500">
                      (필터 적용 · {filteredItems.length}개 표시)
                    </span>
                  )}
                </h2>
                {activeFilter !== "all" && (
                  <button
                    onClick={() => setActiveFilter("all")}
                    className="text-xs text-slate-500 hover:text-slate-700 underline"
                  >
                    필터 초기화
                  </button>
                )}
              </div>

              {filteredItems.length > 0 ? (
                <div className="space-y-2">
                  {filteredItems.map((item) => renderP1Row(item))}
                </div>
              ) : (
                <div className="bg-slate-50 border border-dashed border-slate-200 rounded-xl p-6 text-center text-xs text-slate-400">
                  해당 조건에 맞는 항목이 없습니다.
                </div>
              )}
            </div>

            {issues.length > 0 && (
              <div ref={additionalIssuesRef} className="ds-surface-card p-4 mb-4 scroll-mt-4">
                <h2 className="text-sm font-semibold text-slate-700 mb-3">AI 추가 발견 이슈</h2>
                <div className="space-y-2">
                  {issues.map((issue, i) => (
                    <div key={i} className={`text-xs rounded-lg border px-3 py-2 ${SEVERITY_STYLE[issue.severity]}`}>
                      <span className="font-semibold">[{issue.field}] </span>{issue.issue}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {result.phase2.draft && Object.keys(originalDraftStr).length > 0 && (
              <div className="ds-surface-card p-5 mb-4">
                <div className="flex items-center justify-between mb-2">
                  <h2 className="text-sm font-semibold text-slate-700">최종 한글표시사항 시안</h2>
                  {modifiedCount > 0 && !confirmed && (
                    <button
                      onClick={restoreOriginalDraft}
                      className="text-xs text-slate-500 hover:text-slate-700 underline"
                    >
                      ↺ AI 원본으로 복원
                    </button>
                  )}
                </div>
                <p className="text-[11px] text-slate-400 mb-3 leading-relaxed">
                  {confirmed
                    ? "확정된 시안입니다. (편집 불가)"
                    : modifiedCount > 0
                      ? `직접 편집할 수 있습니다. 현재 ${modifiedCount}개 항목 수정됨. 확정 시 편집 내용이 함께 저장됩니다.`
                      : "각 항목을 클릭해 직접 편집할 수 있습니다. 확정 시 편집 내용이 함께 저장됩니다."}
                </p>
                <div className="divide-y divide-slate-100">
                  {Object.keys(originalDraftStr).map((key) => renderDraftField(key))}
                </div>
              </div>
            )}

            <div className="ds-surface-card p-5 mb-4">
              <h2 className="text-sm font-semibold text-slate-700 mb-1">실무자 최종 확정</h2>
              <p className="text-xs text-slate-400 mb-4">
                교차검증 결과를 검토한 후 확정자 이름을 입력하고 확정하세요.
                {(failCount + disagreeCount) > 0 && (
                  <span className="text-amber-600 font-medium"> ⚠ 부적합·불일치 항목을 먼저 확인하세요.</span>
                )}
                {modifiedCount > 0 && (
                  <span className="block mt-1 text-blue-600 font-medium">
                    ℹ 편집한 {modifiedCount}개 항목이 확정 시 함께 저장됩니다.
                  </span>
                )}
              </p>
              {confirmed ? (
                <div className="flex items-center gap-2 text-sm text-emerald-700 font-medium">
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd"/>
                  </svg>
                  {confirmedBy}님이 확정했습니다.
                </div>
              ) : (
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={confirmedBy}
                    onChange={(e) => setConfirmedBy(e.target.value)}
                    placeholder="확정자 이름"
                    className="flex-1 text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-400 placeholder:text-slate-300"
                  />
                  <button
                    onClick={handleConfirm}
                    disabled={!confirmedBy.trim()}
                    className="px-4 py-2 bg-emerald-500 text-white text-sm font-semibold rounded-lg hover:bg-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    확정
                  </button>
                </div>
              )}
            </div>

            <div className="ds-surface-card p-5 mb-4">
              <h2 className="text-sm font-semibold text-slate-700 mb-1">검토내역서 다운로드</h2>
              <p className="text-xs text-slate-400 mb-4">
                {confirmed
                  ? "교차검증 결과와 최종 시안이 포함된 리포트를 다운로드할 수 있습니다."
                  : "확정 후 다운로드할 수 있습니다."}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => handleDownloadReport("docx")}
                  disabled={!confirmed || downloading !== null}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-blue-500 text-white text-sm font-semibold rounded-lg hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  title={!confirmed ? "확정 후 다운로드 가능합니다." : undefined}
                >
                  {downloading === "docx" ? (
                    <>
                      <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h5M20 20v-5h-5M4 9a9 9 0 0115.83-3.5M20 15a9 9 0 01-15.83 3.5"/>
                      </svg>
                      생성 중...
                    </>
                  ) : (
                    <>📄 DOCX 다운로드</>
                  )}
                </button>
                <button
                  onClick={() => handleDownloadReport("pdf")}
                  disabled={!confirmed || downloading !== null}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-rose-500 text-white text-sm font-semibold rounded-lg hover:bg-rose-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  title={!confirmed ? "확정 후 다운로드 가능합니다." : undefined}
                >
                  {downloading === "pdf" ? (
                    <>
                      <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h5M20 20v-5h-5M4 9a9 9 0 0115.83-3.5M20 15a9 9 0 01-15.83 3.5"/>
                      </svg>
                      생성 중...
                    </>
                  ) : (
                    <>📕 PDF 다운로드</>
                  )}
                </button>
              </div>
              {errorMsg && (
                <div className="mt-3 rounded-lg px-3 py-2 text-xs ds-alert-error">
                  {errorMsg}
                </div>
              )}
            </div>

            <button
              onClick={() => {
                setStep("idle");
                setResult(null);
                setConfirmed(false);
                setActiveFilter("all");
                setEditedDraft({});
                setOriginalDraftStr({});
                lawCacheRef.current.clear();
              }}
              className="text-sm text-slate-400 hover:text-slate-600 transition-colors"
            >
              ← 다시 실행
            </button>
          </>
        )}
      </div>

      {renderLawModal()}
    </>
  );
}

function StepRow({ active, done, label }: { active: boolean; done: boolean; label: string }) {
  return (
    <div className="flex items-center gap-3 text-sm">
      {done ? (
        <svg className="w-5 h-5 text-emerald-500 shrink-0" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd"/>
        </svg>
      ) : active ? (
        <svg className="w-5 h-5 text-emerald-500 animate-spin shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h5M20 20v-5h-5M4 9a9 9 0 0115.83-3.5M20 15a9 9 0 01-15.83 3.5"/>
        </svg>
      ) : (
        <div className="w-5 h-5 rounded-full border-2 border-slate-200 shrink-0"/>
      )}
      <span className={active ? "text-slate-800 font-medium" : done ? "text-slate-400 line-through" : "text-slate-300"}>
        {label}
      </span>
    </div>
  );
}