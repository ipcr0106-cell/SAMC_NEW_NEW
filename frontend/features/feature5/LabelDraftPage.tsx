"use client";

import { apiClient } from "@/services/apiClient";
import { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { useParams } from "next/navigation";
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  Loader2,
  ChevronDown,
  ChevronUp,
  Download,
  RotateCcw,
  FileText,
  X,
  Copy,
  Check,
} from "lucide-react";

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
  rag_failed?: boolean;
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
  law_name_hint?: string | null;
}

interface LawModalState {
  isOpen: boolean;
  loading: boolean;
  query: string;
  lawRef: string;
  hint: string | null;
  results: LawChunk[];
  errorMsg: string;
}

// ── 실무자 최종 확정 포탈 컴포넌트 ───────────────────────────────────────────

interface ConfirmPortalProps {
  confirmed: boolean;
  confirmedBy: string;
  downloading: ReportFormat | null;
  errorMsg: string;
  onConfirmedByChange: (v: string) => void;
  onConfirm: () => void;
  onDownload: (fmt: ReportFormat) => void;
}

function ConfirmPortal({
  confirmed, confirmedBy, downloading, errorMsg,
  onConfirmedByChange, onConfirm, onDownload,
}: ConfirmPortalProps) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);
  if (!mounted) return null;
  const portal = document.getElementById("f5-confirm-portal");
  if (!portal) return null;

  return createPortal(
    <div className="rounded-xl overflow-hidden mt-2"
      style={{ border: "1px solid var(--ds-color-border)" }}>
      <div className="px-3 py-2.5 flex items-center gap-2"
        style={{
          borderBottom: "1px solid var(--ds-color-border-subtle)",
          background: "var(--ds-color-surface)",
        }}>
        <Download size={13} style={{ color: "var(--ds-color-text-tertiary)" }} />
        <p className="text-[12px] font-semibold" style={{ color: "var(--ds-color-text-heading)" }}>
          검토내역서 다운로드
        </p>
      </div>
      <div className="p-3" style={{ background: "var(--ds-color-bg)" }}>
        <div className="flex gap-1.5">
          <button
            onClick={() => onDownload("docx")}
            disabled={!!downloading}
            className="flex-1 inline-flex items-center justify-center gap-1.5 h-8 px-3 rounded-lg text-xs font-medium bg-white border border-slate-200 text-slate-700 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700 transition-colors disabled:opacity-50"
          >
            {downloading === "docx" ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
            DOCX
          </button>
          <button
            onClick={() => onDownload("pdf")}
            disabled={!!downloading}
            className="flex-1 inline-flex items-center justify-center gap-1.5 h-8 px-3 rounded-lg text-xs font-medium bg-white border border-slate-200 text-slate-700 hover:bg-red-50 hover:border-red-300 hover:text-red-700 transition-colors disabled:opacity-50"
          >
            {downloading === "pdf" ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
            PDF
          </button>
        </div>
        {errorMsg && <p className="text-[11px] mt-1.5" style={{ color: "var(--ds-color-error-text)" }}>{errorMsg}</p>}
      </div>
    </div>,
    portal
  );
}

// ── 상수 ─────────────────────────────────────────────────────────────────────

const DRAFT_LABELS: Record<string, string> = {
  product_name:      "제품명",
  food_type:         "식품유형",
  ingredients:       "원재료명 및 함량",
  net_weight:        "내용량",
  expiry:            "소비기한",
  storage:           "보관방법",
  manufacturer:      "제조사",
  importer:          "수입자",
  allergy:           "알레르기",
  gmo:               "GMO",
  country_of_origin: "원산지",
};

const MULTILINE_FIELDS = new Set<string>([
  "ingredients",
  "allergy",
  "manufacturer",
  "importer",
]);

const LAW_QUERY_STOPWORDS = new Set<string>([
  "해야", "한다", "하며", "하고", "하는", "하지", "한다는",
  "있어야", "없어야", "되어야", "해당하는", "해당한다",
  "경우에는", "때에는", "있으며", "있고", "있어", "없음",
  "다음", "각호", "해당", "관련", "따른", "이와", "그러나",
  "또는", "다만", "한편", "이를", "이러한", "이상", "이하",
  "이와", "또는", "이상의", "이내", "이후",
  "사항", "내용", "기준", "규정", "적용", "표시", "기재",
  "방법", "모든", "사람", "때에", "부분", "일부", "전체",
  "이다", "있다", "없다", "된다", "하다",
]);

const LAW_NAME_PATTERNS: Array<{ pattern: RegExp; hint: string }> = [
  { pattern: /시행규칙/,                         hint: "시행규칙" },
  { pattern: /시행령/,                           hint: "시행령" },
  { pattern: /유전자변형|GMO|gmo/i,             hint: "유전자변형" },
  { pattern: /OEM|oem/i,                         hint: "OEM" },
  { pattern: /기구용기/,                         hint: "기구용기" },
  { pattern: /한시적/,                           hint: "한시적" },
  { pattern: /기능성/,                           hint: "기능성" },
  { pattern: /부당한\s*(표시|광고)/,             hint: "부당한" },
  { pattern: /표시\s*ㆍ\s*광고|표시\s*·\s*광고|표시광고/, hint: "표시ㆍ광고" },
  { pattern: /표시기준/,                         hint: "표시기준" },
];

// ── 유틸 ─────────────────────────────────────────────────────────────────────

function toSafeString(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return v.map(toSafeString).join(", ");
  if (typeof v === "object") {
    try { return JSON.stringify(v, null, 2); } catch { return "[object]"; }
  }
  return String(v);
}

function extractFilename(contentDisposition: string | null, fallback: string): string {
  if (!contentDisposition) return fallback;
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try { return decodeURIComponent(utf8Match[1]); } catch { /* */ }
  }
  const asciiMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
  if (asciiMatch?.[1]) return asciiMatch[1];
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

function extractLawNameHint(lawRef: string): string | null {
  if (!lawRef) return null;
  for (const { pattern, hint } of LAW_NAME_PATTERNS) {
    if (pattern.test(lawRef)) return hint;
  }
  return null;
}

function normalizeLawQuery(text: string): string {
  if (!text) return "";
  return text
    .replace(/식품\s+등의/g, "식품등의")
    .replace(/·/g, "ㆍ")
    .replace(/제\s*(\d+)\s*조/g, "제$1조")
    .replace(/제\s*(\d+)\s*항/g, "제$1항")
    .replace(/제\s*(\d+)\s*호/g, "제$1호")
    .replace(/[\s\t]+/g, " ")
    .trim();
}

function extractKeyNouns(text: string, maxCount = 5): string[] {
  if (!text) return [];
  const words = text.match(/[가-힣]{2,8}/g) || [];
  const seen = new Set<string>();
  const result: string[] = [];
  for (const w of words) {
    if (LAW_QUERY_STOPWORDS.has(w) || seen.has(w)) continue;
    seen.add(w);
    result.push(w);
    if (result.length >= maxCount) break;
  }
  return result;
}

function buildLawQuery(lawRef: string, lawRequirement: string): string {
  const refPart = normalizeLawQuery(lawRef);
  const keyNouns = extractKeyNouns(lawRequirement, 3);
  return [refPart, ...keyNouns].filter(Boolean).join(" ").slice(0, 150);
}

function prettifyLawContent(raw: string): string {
  if (!raw) return "";
  let text = raw;
  text = text.replace(/([가-힣a-zA-Z0-9.!?\)])\s*(제\d+조(?:의\d+)?)/g, "$1\n\n$2");
  text = text.replace(/([가-힣a-zA-Z0-9.!?\)])\s*(제\d+항)/g, "$1\n$2");
  text = text.replace(/([가-힣]{2,})\s+(\d+\.\s+[가-힣])/g, "$1\n$2");
  text = text.replace(/[ \t]{2,}/g, " ");
  text = text.replace(/\n{3,}/g, "\n\n");
  return text.trim();
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────────────────────

interface LabelPageProps {
  onDraftChange?: (draft: Record<string, string>) => void;
}

export default function LabelPage({ onDraftChange }: LabelPageProps = {}) {
  const params = useParams();
  const caseId = params.id as string;

  const [step, setStep]               = useState<Step>("idle");
  const [foodType, setFoodType]       = useState("");
  const [result, setResult]           = useState<Result | null>(null);
  const [errorMsg, setErrorMsg]       = useState("");
  const [confirmedBy, setConfirmedBy] = useState("");
  const [confirmed, setConfirmed]     = useState(false);
  const [expandedField, setExpandedField] = useState<string | null>(null);
  const [activeFilter, setActiveFilter]   = useState<FilterKey>("all");
  const [editedDraft, setEditedDraft]       = useState<Record<string, string>>({});
  const [originalDraftStr, setOriginalDraftStr] = useState<Record<string, string>>({});
  const [downloading, setDownloading]     = useState<ReportFormat | null>(null);

  const [lawModal, setLawModal] = useState<LawModalState>({
    isOpen: false, loading: false, query: "", lawRef: "", hint: null, results: [], errorMsg: "",
  });
  const [expandedChunks, setExpandedChunks] = useState<Set<number>>(new Set());
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);

  const lawCacheRef = useRef<Map<string, LawChunk[]>>(new Map());
  const additionalIssuesRef = useRef<HTMLDivElement>(null);

  // 페이지 로드 시 DB에서 F5 결과 자동 로드
  useEffect(() => {
    (async () => {
      try {
        const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
        const token = typeof window !== "undefined" ? localStorage.getItem("supabase_token") : null;
        const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
        const res = await fetch(`${baseUrl}/cases/${caseId}/pipeline/feature/5`, { headers });
        if (!res.ok) return;
        const row = await res.json();
        const data = row.final_result ?? row.ai_result;
        if (data && data.phase1) {
          setResult(data as Result);
          setStep("done");
        }
      } catch { /* F5 결과 없으면 idle 유지 */ }
    })();
  }, [caseId]);

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

  // editedDraft가 바뀔 때마다 부모에게 알려서 다운로드에 실시간 반영
  useEffect(() => {
    if (Object.keys(editedDraft).length > 0) {
      onDraftChange?.(editedDraft);
    }
  }, [editedDraft, onDraftChange]);

  useEffect(() => {
    if (!lawModal.isOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") closeLawModal(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lawModal.isOpen]);

  const p1Items      = result?.phase1.items ?? [];
  const p2Items      = result?.phase2.validation ?? [];
  const issues       = result?.phase2.additional_issues ?? [];
  const failCount    = p1Items.filter(i => i.status === "fail").length;
  const unclearCount = p1Items.filter(i => i.status === "unclear").length;
  const disagreeCount = p2Items.filter(v => v.cross_result === "disagree").length;
  const errorCount   = issues.filter(i => i.severity === "error").length;
  const ragFailed    = result?.rag_failed === true;

  const filteredItems = p1Items.filter(item => {
    if (activeFilter === "all") return true;
    if (activeFilter === "fail") return item.status === "fail";
    if (activeFilter === "unclear") return item.status === "unclear";
    if (activeFilter === "disagree") return p2Items.find(v => v.field === item.field)?.cross_result === "disagree";
    return true;
  });

  function isFieldModified(key: string) {
    return (originalDraftStr[key] ?? "").trim() !== (editedDraft[key] ?? "").trim();
  }
  const modifiedCount = Object.keys(originalDraftStr).filter(isFieldModified).length;

  function toggleFilter(key: FilterKey) {
    setActiveFilter(prev => prev === key ? "all" : key);
  }

  function updateDraftField(key: string, value: string) {
    setEditedDraft(prev => ({ ...prev, [key]: value }));
  }

  function restoreOriginalDraft() {
    if (!window.confirm("편집한 내용을 모두 지우고 AI 원본으로 되돌리시겠습니까?")) return;
    setEditedDraft({ ...originalDraftStr });
  }

  async function openLawModal(lawRef: string, lawRequirement: string) {
    const query = buildLawQuery(lawRef, lawRequirement);
    const hint = extractLawNameHint(lawRef);
    if (!query) return;

    setExpandedChunks(new Set([0]));
    setCopiedIdx(null);

    const cacheKey = `${hint ?? ""}::${query}`;
    const cached = lawCacheRef.current.get(cacheKey);
    if (cached) {
      setLawModal({ isOpen: true, loading: false, query, lawRef, hint, results: cached, errorMsg: "" });
      return;
    }

    setLawModal({ isOpen: true, loading: true, query, lawRef, hint, results: [], errorMsg: "" });

    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
      const token = typeof window !== "undefined" ? localStorage.getItem("supabase_token") : null;
      const response = await fetch(`${baseUrl}/cases/${caseId}/pipeline/feature/5/law-search`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ query, match_count: 3, context_window: 1, law_name_hint: hint }),
      });

      if (!response.ok) {
        let msg = `법령 검색 실패 (HTTP ${response.status})`;
        try { const err = await response.json(); if (err?.detail) msg = err.detail; } catch { /* */ }
        throw new Error(msg);
      }

      const data: LawSearchResponse = await response.json();
      lawCacheRef.current.set(cacheKey, data.results);
      setLawModal({ isOpen: true, loading: false, query, lawRef, hint, results: data.results, errorMsg: "" });
    } catch (e: unknown) {
      setLawModal({
        isOpen: true, loading: false, query, lawRef, hint, results: [],
        errorMsg: e instanceof Error ? e.message : "법령 검색 중 오류가 발생했습니다.",
      });
    }
  }

  function closeLawModal() {
    setLawModal(prev => ({ ...prev, isOpen: false }));
  }

  function toggleChunkExpanded(idx: number) {
    setExpandedChunks(prev => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  }

  async function copyChunk(idx: number, chunk: LawChunk) {
    const text = `[${chunk.law_name}]\n\n${prettifyLawContent(chunk.content)}`;
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
      else {
        const ta = document.createElement("textarea");
        ta.value = text; ta.style.position = "fixed"; ta.style.left = "-9999px";
        document.body.appendChild(ta); ta.select(); document.execCommand("copy"); document.body.removeChild(ta);
      }
      setCopiedIdx(idx);
      window.setTimeout(() => setCopiedIdx(cur => cur === idx ? null : cur), 2000);
    } catch { /* */ }
  }

  async function handleDownloadReport(format: ReportFormat) {
    if (!confirmed) return;
    setErrorMsg("");
    setDownloading(format);
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
      const token = typeof window !== "undefined" ? localStorage.getItem("supabase_token") : null;
      const response = await fetch(`${baseUrl}/cases/${caseId}/pipeline/feature/5/report?format=${format}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) {
        let msg = `다운로드 실패 (HTTP ${response.status})`;
        try { const e = await response.json(); if (e?.detail) msg = e.detail; } catch { /* */ }
        throw new Error(msg);
      }
      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition");
      triggerBlobDownload(blob, extractFilename(disposition, `한글표시사항_report.${format}`));
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : "다운로드 중 오류가 발생했습니다.");
    } finally {
      setDownloading(null);
    }
  }

  async function handleRun() {
    setErrorMsg("");
    try {
      setStep("generating_p1");
      const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
      const token = typeof window !== "undefined" ? localStorage.getItem("supabase_token") : null;
      const response = await fetch(`${baseUrl}/cases/${caseId}/pipeline/feature/5/run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ food_type: foodType || null, stream: true }),
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `HTTP ${response.status}`);
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let phase1Data: Result["phase1"] | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const lines = decoder.decode(value).split("\n").filter(l => l.startsWith("data: "));
        for (const line of lines) {
          try {
            const data = JSON.parse(line.slice(6));
            if (data.step === "phase1_done") { phase1Data = data.phase1; setStep("generating_p2"); }
            if (data.step === "done" && phase1Data) { setResult(data.result); setStep("done"); }
            if (data.error) { setErrorMsg(data.error); setStep("error"); }
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
      if (modifiedCount > 0) payload.draft = editedDraft;
      await apiClient.patch(`/cases/${caseId}/pipeline/feature/5`, payload);
      setConfirmed(true);
    } catch {
      setErrorMsg("확정 저장에 실패했습니다.");
    }
  }

  // ── 상태별 배지 스타일 ─────────────────────────────────────────────────────

  function statusStyle(status: Phase1Item["status"]) {
    if (status === "pass") return {
      badge: "text-[11px] font-semibold px-2 py-0.5 rounded-md",
      style: { background: "var(--ds-color-success-soft)", color: "var(--ds-color-success-text)" },
      label: "적합",
    };
    if (status === "fail") return {
      badge: "text-[11px] font-semibold px-2 py-0.5 rounded-md",
      style: { background: "var(--ds-color-error-soft)", color: "var(--ds-color-error-text)" },
      label: "부적합",
    };
    return {
      badge: "text-[11px] font-semibold px-2 py-0.5 rounded-md",
      style: { background: "var(--ds-color-warning-soft)", color: "var(--ds-color-warning-text)" },
      label: "확인필요",
    };
  }

  function crossStyle(cross: Phase2Validation["cross_result"]) {
    if (cross === "agree") return {
      badge: "text-[11px] px-2 py-0.5 rounded-md",
      style: { background: "var(--ds-color-success-soft)", color: "var(--ds-color-success-text)" },
      label: "AI 일치",
    };
    if (cross === "disagree") return {
      badge: "text-[11px] font-semibold px-2 py-0.5 rounded-md",
      style: { background: "var(--ds-color-error-soft)", color: "var(--ds-color-error-text)" },
      label: "AI 불일치",
    };
    return {
      badge: "text-[11px] px-2 py-0.5 rounded-md",
      style: { background: "var(--ds-color-warning-soft)", color: "var(--ds-color-warning-text)" },
      label: "추가이슈",
    };
  }

  // ── 항목별 행 렌더링 ──────────────────────────────────────────────────────

  function renderP1Row(item: Phase1Item) {
    const st = statusStyle(item.status);
    const v2 = p2Items.find(v => v.field === item.field);
    const expanded = expandedField === item.field;
    const cs = v2 ? crossStyle(v2.cross_result) : null;
    const needsReview = v2?.cross_result === "disagree";

    return (
      <div key={item.field} className="rounded-xl overflow-hidden"
        style={{ border: `1px solid ${needsReview ? "var(--ds-color-error)" : "var(--ds-color-border)"}` }}>
        <button
          onClick={() => setExpandedField(expanded ? null : item.field)}
          className="w-full flex items-center gap-3 px-4 py-3 text-left transition-colors"
          style={{ background: expanded ? "var(--ds-color-surface)" : "var(--ds-color-bg)" }}
        >
          {/* 필드명 */}
          <span className="text-[13px] font-semibold w-[120px] shrink-0"
            style={{ color: "var(--ds-color-text-heading)" }}>
            {item.field}
          </span>

          {/* 상태 배지 */}
          <span className={st.badge} style={st.style}>{st.label}</span>

          {/* AI 교차검증 배지 */}
          {cs && <span className={cs.badge} style={cs.style}>{cs.label}</span>}

          {/* 검토 필요 경고 */}
          {needsReview && (
            <span className="flex items-center gap-1 text-[11px] font-semibold ml-1"
              style={{ color: "var(--ds-color-error-text)" }}>
              <AlertTriangle size={11} /> 검토 필요
            </span>
          )}

          {/* 서류값 미리보기 */}
          {item.document_value && !expanded && (
            <span className="text-[12px] truncate ml-auto max-w-[160px]"
              style={{ color: "var(--ds-color-text-tertiary)" }}>
              {item.document_value}
            </span>
          )}

          <span className="ml-auto shrink-0" style={{ color: "var(--ds-color-text-tertiary)" }}>
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </span>
        </button>

        {expanded && (
          <div className="px-4 py-4 space-y-3"
            style={{ borderTop: "1px solid var(--ds-color-border-subtle)", background: "var(--ds-color-surface)" }}>

            {/* 서류 확인값 */}
            <div className="flex items-start gap-2">
              <span className="text-[11px] font-semibold w-20 shrink-0 pt-0.5"
                style={{ color: "var(--ds-color-text-tertiary)" }}>서류 확인값</span>
              <span className="text-[13px]" style={{ color: "var(--ds-color-text-primary)" }}>
                {item.document_value ?? "확인 불가"}
              </span>
            </div>

            {/* 법령 근거 */}
            <div className="rounded-lg p-3"
              style={{ background: "var(--ds-color-bg)", border: "1px solid var(--ds-color-border-subtle)" }}>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-semibold"
                  style={{ color: "var(--ds-color-text-tertiary)" }}>법령 근거</span>
                {item.law_ref && (
                  <button
                    type="button"
                    onClick={e => { e.stopPropagation(); openLawModal(item.law_ref, item.law_requirement); }}
                    className="flex items-center gap-1 text-[11px] font-medium transition-colors"
                    style={{ color: "var(--ds-color-primary-text)" }}
                  >
                    <FileText size={11} /> 원문 보기
                  </button>
                )}
              </div>
              <p className="text-[12px] font-semibold" style={{ color: "var(--ds-color-text-heading)" }}>
                {item.law_ref}
              </p>
              <p className="text-[12px] mt-1 leading-relaxed" style={{ color: "var(--ds-color-text-secondary)" }}>
                {item.law_requirement}
              </p>
            </div>

            {/* 1차 검토 의견 */}
            <div className="rounded-lg p-3" style={st.style}>
              <p className="text-[11px] font-semibold mb-1" style={{ color: "inherit" }}>1차 검토 의견</p>
              <p className="text-[12px] leading-relaxed">{item.note}</p>
            </div>

            {/* AI 교차검증 의견 */}
            {v2 && cs && (
              <div className="rounded-lg p-3" style={cs.style}>
                <p className="text-[11px] font-semibold mb-1">AI 교차검증</p>
                <p className="text-[12px] leading-relaxed">{v2.ai_note}</p>
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  // ─── 필터 뱃지 ─────────────────────────────────────────────────────────────

  function FilterBadge({
    fkey, label, count, active,
  }: { fkey: FilterKey; label: string; count: number; active: boolean }) {
    const hasItems = count > 0;
    return (
      <button
        onClick={() => toggleFilter(fkey)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[12px] font-medium border transition-all"
        style={{
          background: active ? "var(--ds-color-primary)" : hasItems ? "var(--ds-color-surface)" : "transparent",
          color: active ? "#fff" : hasItems ? "var(--ds-color-text-primary)" : "var(--ds-color-text-tertiary)",
          borderColor: active ? "var(--ds-color-primary)" : "var(--ds-color-border)",
        }}
      >
        {label}
        {count > 0 && (
          <span className="text-[11px] font-bold rounded-full px-1.5 py-0.5 leading-none"
            style={{
              background: active ? "rgba(255,255,255,0.2)" : "var(--ds-color-border)",
              color: active ? "#fff" : "var(--ds-color-text-secondary)",
            }}>
            {count}
          </span>
        )}
      </button>
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // IDLE: 분석 시작 전
  // ═══════════════════════════════════════════════════════════════════════════

  if (step === "idle") {
    return (
      <div className="space-y-4">
        <div className="rounded-xl p-6 flex flex-col gap-4"
          style={{ border: "1px solid var(--ds-color-border)", background: "var(--ds-color-bg)" }}>
          <div>
            <h3 className="text-[15px] font-bold mb-1" style={{ color: "var(--ds-color-text-heading)" }}>
              한글표시사항 시안 생성
            </h3>
            <p className="text-[13px]" style={{ color: "var(--ds-color-text-secondary)" }}>
              AI가 표시기준 법령을 교차검증하여 한글 표시사항 시안을 생성합니다.
            </p>
          </div>

          <div>
            <label className="text-[12px] font-medium mb-1.5 block"
              style={{ color: "var(--ds-color-text-secondary)" }}>
              식품유형 <span style={{ color: "var(--ds-color-text-tertiary)" }}>(선택 · F2 분류 결과가 자동 적용됩니다)</span>
            </label>
            <input
              type="text"
              value={foodType}
              onChange={e => setFoodType(e.target.value)}
              placeholder="예: 과자, 음료, 소스류 …"
              className="w-full px-3 py-2 rounded-lg text-[13px] focus:outline-none"
              style={{
                border: "1px solid var(--ds-color-border)",
                background: "var(--ds-color-surface)",
                color: "var(--ds-color-text-primary)",
              }}
            />
          </div>

          <button
            onClick={handleRun}
            className="flex items-center justify-center gap-2 w-full py-2.5 rounded-lg text-[13px] font-semibold transition-all"
            style={{ background: "var(--ds-color-primary)", color: "#fff" }}
          >
            시안 생성 시작
          </button>
        </div>
      </div>
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // LOADING
  // ═══════════════════════════════════════════════════════════════════════════

  if (step === "generating_p1" || step === "generating_p2") {
    return (
      <div className="rounded-xl p-6 flex flex-col items-center gap-4 text-center"
        style={{ border: "1px solid var(--ds-color-border)", background: "var(--ds-color-bg)" }}>
        <div className="w-10 h-10 rounded-full flex items-center justify-center"
          style={{ background: "var(--ds-color-primary-soft)" }}>
          <Loader2 size={18} className="animate-spin" style={{ color: "var(--ds-color-primary)" }} />
        </div>
        <div>
          <p className="text-[14px] font-semibold" style={{ color: "var(--ds-color-text-heading)" }}>
            {step === "generating_p1" ? "1단계: 표시항목 법령 검토 중" : "2단계: AI 교차검증 중"}
          </p>
          <p className="text-[12px] mt-1" style={{ color: "var(--ds-color-text-tertiary)" }}>
            {step === "generating_p1" ? "각 표시 항목을 관련 법령과 대조하고 있습니다" : "1차 검토 결과를 AI가 재검증하고 있습니다"}
          </p>
        </div>
        <div className="flex gap-2 items-center">
          {(["1단계", "2단계"] as const).map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              {i > 0 && <div className="w-8 h-px" style={{ background: "var(--ds-color-border)" }} />}
              <div className="flex items-center gap-1.5">
                <div className={`w-2 h-2 rounded-full ${
                  (step === "generating_p1" && i === 0) || (step === "generating_p2" && i === 1)
                    ? "animate-pulse" : ""
                }`}
                  style={{
                    background: (step === "generating_p1" && i === 0) || (step === "generating_p2" && i === 1)
                      ? "var(--ds-color-primary)"
                      : step === "generating_p2" && i === 0
                        ? "var(--ds-color-success)"
                        : "var(--ds-color-border)",
                  }} />
                <span className="text-[11px]" style={{ color: "var(--ds-color-text-tertiary)" }}>{s}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // ERROR
  // ═══════════════════════════════════════════════════════════════════════════

  if (step === "error") {
    return (
      <div className="rounded-xl p-5 space-y-3"
        style={{ background: "var(--ds-color-error-soft)", border: "1px solid var(--ds-color-error)" }}>
        <div className="flex items-center gap-2">
          <XCircle size={16} style={{ color: "var(--ds-color-error-text)" }} />
          <p className="text-[13px] font-semibold" style={{ color: "var(--ds-color-error-text)" }}>분석 실패</p>
        </div>
        <p className="text-[12px]" style={{ color: "var(--ds-color-error-text)" }}>{errorMsg}</p>
        <button onClick={() => setStep("idle")}
          className="text-[12px] font-medium underline" style={{ color: "var(--ds-color-error-text)" }}>
          다시 시도
        </button>
      </div>
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // DONE: 결과 화면
  // ═══════════════════════════════════════════════════════════════════════════

  if (step !== "done" || !result) return null;

  return (
    <div className="space-y-5">
      {/* RAG 경고 */}
      {ragFailed && (
        <div className="flex items-start gap-2 px-4 py-3 rounded-xl"
          style={{ background: "var(--ds-color-warning-soft)", border: "1px solid var(--ds-color-warning)" }}>
          <AlertTriangle size={14} style={{ color: "var(--ds-color-warning-text)" }} className="mt-0.5 shrink-0" />
          <p className="text-[12px]" style={{ color: "var(--ds-color-warning-text)" }}>
            일부 법령 데이터 조회에 실패하여 정확도가 낮을 수 있습니다.
          </p>
        </div>
      )}

      {/* ── 요약 카드 ── */}
      <div className="rounded-xl p-4"
        style={{ border: "1px solid var(--ds-color-border)", background: "var(--ds-color-bg)" }}>
        <p className="text-[11px] font-semibold mb-3 tracking-wide"
          style={{ color: "var(--ds-color-text-tertiary)" }}>교차검증 종합 결과</p>
        <div className="grid grid-cols-4 gap-3">
          {[
            { label: "전체 항목", value: p1Items.length, color: "var(--ds-color-text-heading)" },
            { label: "부적합", value: failCount, color: failCount > 0 ? "var(--ds-color-error-text)" : "var(--ds-color-text-tertiary)" },
            { label: "확인필요", value: unclearCount, color: unclearCount > 0 ? "var(--ds-color-warning-text)" : "var(--ds-color-text-tertiary)" },
            { label: "AI 불일치", value: disagreeCount, color: disagreeCount > 0 ? "var(--ds-color-error-text)" : "var(--ds-color-text-tertiary)" },
          ].map(stat => (
            <div key={stat.label} className="text-center p-3 rounded-lg"
              style={{ background: "var(--ds-color-surface)" }}>
              <p className="text-[20px] font-extrabold leading-none" style={{ color: stat.color }}>
                {stat.value}
              </p>
              <p className="text-[11px] mt-1" style={{ color: "var(--ds-color-text-tertiary)" }}>
                {stat.label}
              </p>
            </div>
          ))}
        </div>
        {failCount === 0 && disagreeCount === 0 && (
          <div className="flex items-center gap-2 mt-3 pt-3"
            style={{ borderTop: "1px solid var(--ds-color-border-subtle)" }}>
            <CheckCircle size={14} style={{ color: "var(--ds-color-success)" }} />
            <p className="text-[12px] font-medium" style={{ color: "var(--ds-color-success-text)" }}>
              주요 표시항목이 법령 기준을 충족합니다
            </p>
          </div>
        )}
      </div>

      {/* ── 항목별 교차검증 ── */}
      <div className="rounded-xl overflow-hidden"
        style={{ border: "1px solid var(--ds-color-border)" }}>
        {/* 헤더 + 필터 */}
        <div className="px-4 py-3 flex items-center gap-2 flex-wrap"
          style={{ borderBottom: "1px solid var(--ds-color-border-subtle)", background: "var(--ds-color-surface)" }}>
          <p className="text-[13px] font-semibold mr-2" style={{ color: "var(--ds-color-text-heading)" }}>
            항목별 검토 결과
          </p>
          <FilterBadge fkey="all" label="전체" count={p1Items.length} active={activeFilter === "all"} />
          <FilterBadge fkey="fail" label="부적합" count={failCount} active={activeFilter === "fail"} />
          <FilterBadge fkey="unclear" label="확인필요" count={unclearCount} active={activeFilter === "unclear"} />
          <FilterBadge fkey="disagree" label="AI 불일치" count={disagreeCount} active={activeFilter === "disagree"} />
        </div>

        <div className="p-3 space-y-2" style={{ background: "var(--ds-color-bg)" }}>
          {filteredItems.length === 0 ? (
            <p className="text-center py-6 text-[13px]" style={{ color: "var(--ds-color-text-tertiary)" }}>
              해당 항목이 없습니다
            </p>
          ) : (
            filteredItems.map(item => renderP1Row(item))
          )}
        </div>
      </div>

      {/* ── AI 추가 발견 이슈 ── */}
      {issues.length > 0 && (
        <div ref={additionalIssuesRef} className="rounded-xl overflow-hidden"
          style={{ border: "1px solid var(--ds-color-border)" }}>
          <div className="px-4 py-3 flex items-center gap-2"
            style={{ borderBottom: "1px solid var(--ds-color-border-subtle)", background: "var(--ds-color-surface)" }}>
            <AlertTriangle size={14} style={{ color: "var(--ds-color-warning-text)" }} />
            <p className="text-[13px] font-semibold" style={{ color: "var(--ds-color-text-heading)" }}>
              AI 추가 발견 이슈
            </p>
            {errorCount > 0 && (
              <span className="text-[11px] font-semibold px-2 py-0.5 rounded-md ml-auto"
                style={{ background: "var(--ds-color-error-soft)", color: "var(--ds-color-error-text)" }}>
                오류 {errorCount}건
              </span>
            )}
          </div>
          <div className="p-3 grid grid-cols-2 gap-2" style={{ background: "var(--ds-color-bg)" }}>
            {issues.map((issue, i) => {
              const bg = issue.severity === "error"
                ? "var(--ds-color-error-soft)"
                : issue.severity === "warning"
                  ? "var(--ds-color-warning-soft)"
                  : "var(--ds-color-primary-soft)";
              const color = issue.severity === "error"
                ? "var(--ds-color-error-text)"
                : issue.severity === "warning"
                  ? "var(--ds-color-warning-text)"
                  : "var(--ds-color-primary-text)";
              return (
                <div key={i} className="rounded-lg px-3 py-2.5 flex items-start gap-2.5"
                  style={{ background: bg, border: `1px solid ${bg}` }}>
                  <AlertTriangle size={13} style={{ color, marginTop: 2 }} className="shrink-0" />
                  <div>
                    <p className="text-[12px] font-semibold" style={{ color }}>{issue.field}</p>
                    <p className="text-[12px] mt-0.5 leading-relaxed" style={{ color }}>{issue.issue}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── 한글표시사항 시안 편집 ── */}
      {Object.keys(editedDraft).length > 0 && (
        <div className="rounded-xl overflow-hidden"
          style={{ border: "1px solid var(--ds-color-border)" }}>
          <div className="px-4 py-3 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--ds-color-border-subtle)", background: "var(--ds-color-surface)" }}>
            <p className="text-[13px] font-semibold" style={{ color: "var(--ds-color-text-heading)" }}>
              한글표시사항 시안
            </p>
            {modifiedCount > 0 && (
              <button
                onClick={restoreOriginalDraft}
                className="flex items-center gap-1 text-[11px] font-medium transition-colors"
                style={{ color: "var(--ds-color-text-tertiary)" }}
              >
                <RotateCcw size={11} /> AI 원본으로 복원 ({modifiedCount}건 수정됨)
              </button>
            )}
          </div>

          <div className="p-4 grid grid-cols-2 gap-3" style={{ background: "var(--ds-color-bg)" }}>
            {Object.entries(DRAFT_LABELS).map(([key, label]) => {
              if (!(key in editedDraft) && !(key in originalDraftStr)) return null;
              const value = editedDraft[key] ?? "";
              const modified = isFieldModified(key);
              const isMulti = MULTILINE_FIELDS.has(key);
              // 파싱 미완료: "[...]" 형태 플레이스홀더
              const isPlaceholder = value.trim().startsWith("[") && value.trim().endsWith("]");

              const borderColor = modified
                ? "var(--ds-color-primary)"
                : isPlaceholder
                  ? "var(--ds-color-warning)"
                  : "var(--ds-color-border)";
              const bgColor = isPlaceholder
                ? "var(--ds-color-warning-soft)"
                : "var(--ds-color-surface)";
              const textColor = isPlaceholder
                ? "var(--ds-color-warning-text)"
                : "var(--ds-color-text-primary)";

              return (
                <div key={key} className="group" style={{ gridColumn: isMulti ? "1 / -1" : undefined }}>
                  <div className="flex items-center gap-1.5 mb-1">
                    <label className="text-[11px] font-semibold"
                      style={{ color: isPlaceholder ? "var(--ds-color-warning-text)" : "var(--ds-color-text-tertiary)" }}>
                      {label}
                    </label>
                    {modified && (
                      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full"
                        style={{ background: "var(--ds-color-primary-soft)", color: "var(--ds-color-primary-text)" }}>
                        수정됨
                      </span>
                    )}
                    {isPlaceholder && !modified && (
                      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full"
                        style={{ background: "var(--ds-color-warning-soft)", color: "var(--ds-color-warning-text)" }}>
                        확인 필요
                      </span>
                    )}
                  </div>
                  {isMulti ? (
                    <textarea
                      value={value}
                      onChange={e => updateDraftField(key, e.target.value)}
                      rows={3}
                      className="w-full px-3 py-2 rounded-lg text-[13px] resize-none focus:outline-none transition-all"
                      style={{ border: `1px solid ${borderColor}`, background: bgColor, color: textColor }}
                    />
                  ) : (
                    <input
                      type="text"
                      value={value}
                      onChange={e => updateDraftField(key, e.target.value)}
                      className="w-full px-3 py-2 rounded-lg text-[13px] focus:outline-none transition-all"
                      style={{ border: `1px solid ${borderColor}`, background: bgColor, color: textColor }}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 실무자 최종 확정 — 미니바 포탈로 렌더링 */}
      <ConfirmPortal
        confirmed={confirmed}
        confirmedBy={confirmedBy}
        downloading={downloading}
        errorMsg={errorMsg}
        onConfirmedByChange={setConfirmedBy}
        onConfirm={handleConfirm}
        onDownload={handleDownloadReport}
      />

      {/* ═══════════════════════════════════════════════════════════════════
          법령 원문 모달
      ═══════════════════════════════════════════════════════════════════ */}
      {lawModal.isOpen && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4"
          style={{ background: "rgba(0,0,0,0.45)" }}
          onClick={e => { if (e.target === e.currentTarget) closeLawModal(); }}
        >
          <div className="w-full max-w-[680px] max-h-[80vh] flex flex-col rounded-2xl overflow-hidden shadow-2xl"
            style={{ background: "var(--ds-color-bg)", border: "1px solid var(--ds-color-border)" }}>

            {/* 모달 헤더 */}
            <div className="flex items-center gap-3 px-5 py-4 shrink-0"
              style={{ borderBottom: "1px solid var(--ds-color-border-subtle)", background: "var(--ds-color-surface)" }}>
              <FileText size={16} style={{ color: "var(--ds-color-primary)" }} />
              <div className="flex-1 min-w-0">
                <p className="text-[13px] font-semibold truncate" style={{ color: "var(--ds-color-text-heading)" }}>
                  법령 원문 검색
                </p>
                <p className="text-[11px] truncate" style={{ color: "var(--ds-color-text-tertiary)" }}>
                  {lawModal.lawRef}
                </p>
              </div>
              <button onClick={closeLawModal}
                className="w-7 h-7 flex items-center justify-center rounded-lg transition-colors"
                style={{ color: "var(--ds-color-text-tertiary)" }}>
                <X size={16} />
              </button>
            </div>

            {/* 모달 본문 */}
            <div className="overflow-y-auto flex-1 p-4 space-y-3">
              {lawModal.loading && (
                <div className="flex flex-col items-center gap-3 py-8">
                  <Loader2 size={20} className="animate-spin" style={{ color: "var(--ds-color-primary)" }} />
                  <p className="text-[12px]" style={{ color: "var(--ds-color-text-tertiary)" }}>법령 검색 중…</p>
                </div>
              )}

              {lawModal.errorMsg && (
                <div className="px-4 py-3 rounded-lg"
                  style={{ background: "var(--ds-color-error-soft)", color: "var(--ds-color-error-text)" }}>
                  <p className="text-[13px]">{lawModal.errorMsg}</p>
                </div>
              )}

              {!lawModal.loading && !lawModal.errorMsg && lawModal.results.length === 0 && (
                <p className="text-center py-8 text-[13px]" style={{ color: "var(--ds-color-text-tertiary)" }}>
                  검색 결과가 없습니다
                </p>
              )}

              {lawModal.results.map((chunk, idx) => {
                const isExpanded = expandedChunks.has(idx);
                const content = prettifyLawContent(chunk.content);
                const isCopied = copiedIdx === idx;

                return (
                  <div key={idx} className="rounded-xl overflow-hidden"
                    style={{ border: "1px solid var(--ds-color-border)" }}>
                    <button
                      onClick={() => toggleChunkExpanded(idx)}
                      className="w-full flex items-center gap-2 px-4 py-3 text-left"
                      style={{
                        background: isExpanded ? "var(--ds-color-surface)" : "var(--ds-color-bg)",
                        borderBottom: isExpanded ? "1px solid var(--ds-color-border-subtle)" : "none",
                      }}
                    >
                      <span className="text-[12px] font-semibold flex-1 truncate"
                        style={{ color: "var(--ds-color-text-heading)" }}>
                        {chunk.law_name}
                      </span>
                      <span className="text-[11px] shrink-0" style={{ color: "var(--ds-color-text-tertiary)" }}>
                        유사도 {(chunk.score * 100).toFixed(0)}%
                      </span>
                      {isExpanded ? <ChevronUp size={13} style={{ color: "var(--ds-color-text-tertiary)" }} />
                                  : <ChevronDown size={13} style={{ color: "var(--ds-color-text-tertiary)" }} />}
                    </button>

                    {isExpanded && (
                      <div className="px-4 py-3" style={{ background: "var(--ds-color-bg)" }}>
                        <pre className="text-[12px] leading-relaxed whitespace-pre-wrap font-sans"
                          style={{ color: "var(--ds-color-text-primary)" }}>
                          {content}
                        </pre>
                        <div className="flex justify-end mt-3">
                          <button
                            onClick={() => copyChunk(idx, chunk)}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium transition-all"
                            style={{
                              background: isCopied ? "var(--ds-color-success-soft)" : "var(--ds-color-surface)",
                              color: isCopied ? "var(--ds-color-success-text)" : "var(--ds-color-text-secondary)",
                              border: "1px solid var(--ds-color-border)",
                            }}
                          >
                            {isCopied ? <Check size={11} /> : <Copy size={11} />}
                            {isCopied ? "복사됨" : "복사"}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
