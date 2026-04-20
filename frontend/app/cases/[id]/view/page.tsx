"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import {
  ChevronLeft,
  Download,
  Loader2,
  Edit2,
  CheckCircle,
  XCircle,
  AlertTriangle,
  FileText,
  Search,
  ClipboardCheck,
  Globe,
  FileCheck,
  Shield,
  RefreshCw,
  Package,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import {
  getCase,
  getParsedResult,
  getFeature1,
  getFeature3,
  getFeature4,
  getFeature5,
  runFeature1,
  runFeature3,
  runFeature4,
  runFeature5,
  type CaseData,
} from "@/lib/api";
import Button from "@/components/ui/Button";

// ── 타입 ──────────────────────────────────────────────────
type SectionKey = "f5" | "f4" | "f3" | "f1" | "f0";

interface SectionInfo {
  key: SectionKey;
  label: string;
  icon: React.ReactNode;
  editRoute: string;
}

const SECTIONS: SectionInfo[] = [
  { key: "f5", label: "F5 최종결과", icon: <FileCheck size={14} />, editRoute: "f5" },
  { key: "f4", label: "F4 라벨검토", icon: <Globe size={14} />, editRoute: "f4" },
  { key: "f3", label: "F3 필요서류", icon: <ClipboardCheck size={14} />, editRoute: "f3" },
  { key: "f1", label: "F1 수입판정", icon: <Search size={14} />, editRoute: "f1" },
  { key: "f0", label: "F0 서류업로드", icon: <FileText size={14} />, editRoute: "upload" },
];

// ── 공통 섹션 래퍼 ─────────────────────────────────────────
function StageSection({
  sectionKey,
  label,
  icon,
  status,
  onEdit,
  children,
  defaultOpen = true,
  editLabel = "수정",
}: {
  sectionKey: SectionKey;
  label: string;
  icon: React.ReactNode;
  status?: "ok" | "warn" | "error" | "pending" | "loading";
  onEdit?: () => void;
  children: React.ReactNode;
  defaultOpen?: boolean;
  editLabel?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);

  const statusColor = {
    ok: "var(--ds-color-success)",
    warn: "var(--ds-color-warning)",
    error: "var(--ds-color-error)",
    pending: "var(--ds-color-text-tertiary)",
    loading: "var(--ds-color-primary)",
  }[status ?? "pending"];

  const StatusIcon = () => {
    if (status === "ok") return <CheckCircle size={14} style={{ color: statusColor }} />;
    if (status === "error") return <XCircle size={14} style={{ color: statusColor }} />;
    if (status === "warn") return <AlertTriangle size={14} style={{ color: statusColor }} />;
    if (status === "loading") return <Loader2 size={14} className="animate-spin" style={{ color: statusColor }} />;
    return null;
  };

  return (
    <div
      id={`section-${sectionKey}`}
      className="rounded-2xl border mb-4 overflow-hidden transition-all"
      style={{ background: "var(--ds-color-bg)", borderColor: "var(--ds-color-border)" }}
    >
      {/* 섹션 헤더 */}
      <div
        className="flex items-center gap-3 px-5 py-4 cursor-pointer"
        style={{ borderBottom: open ? "1px solid var(--ds-color-border-subtle)" : "none" }}
        onClick={() => setOpen((o) => !o)}
      >
        <div className="flex items-center gap-2 flex-1">
          <span style={{ color: "var(--ds-color-text-tertiary)" }}>{icon}</span>
          <h2 className="text-[14px] font-bold" style={{ color: "var(--ds-color-text-heading)" }}>
            {label}
          </h2>
          <StatusIcon />
        </div>
        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
          {onEdit && (
            <button
              onClick={onEdit}
              className="flex items-center gap-1.5 text-[12px] font-medium px-3 py-1.5 rounded-lg border transition-all"
              style={{
                color: "var(--ds-color-text-secondary)",
                borderColor: "var(--ds-color-border)",
                background: "var(--ds-color-surface)",
              }}
            >
              <Edit2 size={11} />
              {editLabel}
            </button>
          )}
        </div>
        <div style={{ color: "var(--ds-color-text-tertiary)" }}>
          {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>
      </div>

      {open && <div className="px-5 py-4">{children}</div>}
    </div>
  );
}

// ── 메인 페이지 ───────────────────────────────────────────
export default function CaseViewPage() {
  const router = useRouter();
  const params = useParams();
  const caseId = params?.id as string;

  const [caseData, setCaseData] = useState<CaseData | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeSection, setActiveSection] = useState<SectionKey>("f5");

  // 각 단계 데이터
  const [f0Data, setF0Data] = useState<Record<string, unknown> | null>(null);
  const [f1Data, setF1Data] = useState<Record<string, unknown> | null>(null);
  const [f3Data, setF3Data] = useState<Record<string, unknown> | null>(null);
  const [f4Data, setF4Data] = useState<Record<string, unknown> | null>(null);
  const [f5Data, setF5Data] = useState<Record<string, unknown> | null>(null);

  // 로딩 상태
  const [f1Status, setF1Status] = useState<"loading" | "ok" | "error" | "pending">("pending");
  const [f3Status, setF3Status] = useState<"loading" | "ok" | "error" | "pending">("pending");
  const [f4Status, setF4Status] = useState<"loading" | "ok" | "error" | "pending">("pending");
  const [f5Status, setF5Status] = useState<"loading" | "ok" | "error" | "pending">("pending");

  // 파이프라인 재실행 중
  const [running, setRunning] = useState(false);
  const [runMsg, setRunMsg] = useState<string | null>(null);

  // F5 다운로드
  const [downloading, setDownloading] = useState(false);

  const sectionRefs = useRef<Record<SectionKey, HTMLElement | null>>({
    f5: null, f4: null, f3: null, f1: null, f0: null,
  });

  // ── 데이터 로드 ───────────────────────────────────────
  const loadAll = useCallback(async () => {
    try {
      // 케이스 기본 정보
      const c = await getCase(caseId);
      setCaseData(c);

      // F0: OCR 파싱 결과
      try {
        const r = await getParsedResult(caseId);
        if (r?.parsed_result) setF0Data(r.parsed_result);
      } catch { /* 없으면 무시 */ }

      // F1
      setF1Status("loading");
      try {
        const r = await getFeature1(caseId);
        if (r?.ai_result || r?.final_result) {
          setF1Data(r);
          setF1Status("ok");
        } else setF1Status("pending");
      } catch { setF1Status("pending"); }

      // F3
      setF3Status("loading");
      try {
        const r = await getFeature3(caseId);
        if (r?.ai_result || r?.final_result) {
          setF3Data(r);
          setF3Status("ok");
        } else setF3Status("pending");
      } catch { setF3Status("pending"); }

      // F4
      setF4Status("loading");
      try {
        const r = await getFeature4(caseId);
        if (r?.ai_result || r?.final_result || r?.items) {
          setF4Data(r);
          setF4Status("ok");
        } else setF4Status("pending");
      } catch { setF4Status("pending"); }

      // F5
      setF5Status("loading");
      try {
        const r = await getFeature5(caseId);
        if (r?.ai_result || r?.final_result) {
          setF5Data(r);
          setF5Status("ok");
        } else setF5Status("pending");
      } catch { setF5Status("pending"); }

    } catch (e) {
      console.error("데이터 로드 실패:", e);
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    if (caseId) loadAll();
  }, [caseId, loadAll]);

  // ── 스크롤 추적 (미니 네비 활성화) ────────────────────
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            const id = entry.target.id.replace("section-", "") as SectionKey;
            setActiveSection(id);
          }
        }
      },
      { threshold: 0.3 }
    );
    SECTIONS.forEach(({ key }) => {
      const el = document.getElementById(`section-${key}`);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [loading]);

  // ── 파이프라인 전체 재실행 (수동 재분석용) ──────────────
  const handleRunPipeline = async () => {
    setRunning(true);
    setRunMsg("F1 수입판정 분석 중...");
    try {
      await runFeature1(caseId);
      setRunMsg("F3 필요서류 분석 중...");
      await runFeature3(caseId);
      setRunMsg("F4 라벨검토 분석 중...");
      await runFeature4(caseId);
      setRunMsg("F5 한글시안 생성 중...");
      await runFeature5(caseId);
      setRunMsg("완료!");
      await loadAll();
      setTimeout(() => setRunMsg(null), 2000);
    } catch (e) {
      setRunMsg(`오류: ${e instanceof Error ? e.message : "파이프라인 실패"}`);
      setTimeout(() => setRunMsg(null), 5000);
    } finally {
      setRunning(false);
    }
  };

  // ── F5 다운로드 ───────────────────────────────────────
  const handleDownload = async (format: "docx" | "pdf") => {
    setDownloading(true);
    try {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
      const token = typeof window !== "undefined" ? localStorage.getItem("supabase_token") : null;
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(`${API_BASE}/cases/${caseId}/pipeline/feature/5/export.${format}`, { headers });
      if (!res.ok) throw new Error("다운로드 실패");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `한글표시사항_${caseData?.product_name || caseId}.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      alert("다운로드에 실패했습니다. F5 분석이 완료되었는지 확인하세요.");
    } finally {
      setDownloading(false);
    }
  };

  // ── 섹션 이동 ─────────────────────────────────────────
  const scrollToSection = (key: SectionKey) => {
    document.getElementById(`section-${key}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    setActiveSection(key);
  };

  const goToEdit = (route: string) => {
    router.push(`/cases/${caseId}/${route}?from=view`);
  };

  // ── 로딩 ──────────────────────────────────────────────
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--ds-color-bg)" }}>
        <div className="flex flex-col items-center gap-3">
          <Loader2 size={28} className="animate-spin" style={{ color: "var(--ds-color-primary)" }} />
          <span className="text-[13px]" style={{ color: "var(--ds-color-text-secondary)" }}>
            검역 결과 불러오는 중...
          </span>
        </div>
      </div>
    );
  }

  // ── F1 결과 요약 렌더 ─────────────────────────────────
  const renderF1Summary = () => {
    const result = (f1Data?.final_result || f1Data?.ai_result) as Record<string, unknown> | null;
    if (!result) return (
      <p className="text-[13px]" style={{ color: "var(--ds-color-text-secondary)" }}>
        F1 수입판정 결과가 없습니다. 수정 버튼을 눌러 분석을 실행하세요.
      </p>
    );
    const verdict = result.verdict as string || (result.import_possible ? "수입가능" : "수입불가");
    const isPossible = verdict === "수입가능" || result.import_possible;
    const ingredients = result.ingredients as Array<Record<string, unknown>> || [];
    const failReasons = result.fail_reasons as string[] || [];
    return (
      <div className="space-y-3">
        {/* 판정 결과 */}
        <div className="flex items-center gap-3 p-3 rounded-xl"
          style={{ background: isPossible ? "var(--ds-color-success-soft)" : "var(--ds-color-error-soft)" }}>
          {isPossible
            ? <CheckCircle size={18} style={{ color: "var(--ds-color-success)" }} />
            : <XCircle size={18} style={{ color: "var(--ds-color-error)" }} />
          }
          <div>
            <p className="text-[15px] font-bold"
              style={{ color: isPossible ? "var(--ds-color-success-text)" : "var(--ds-color-error-text)" }}>
              {verdict}
            </p>
            {failReasons.length > 0 && (
              <p className="text-[12px] mt-0.5" style={{ color: "var(--ds-color-error-text)" }}>
                {failReasons[0]}
              </p>
            )}
          </div>
        </div>
        {/* 원재료 요약 */}
        {ingredients.length > 0 && (
          <div>
            <p className="text-[11px] font-semibold mb-2" style={{ color: "var(--ds-color-text-tertiary)" }}>
              원재료 ({ingredients.length}종)
            </p>
            <div className="flex flex-wrap gap-1.5">
              {ingredients.slice(0, 10).map((ing, i) => {
                const status = ing.allow_verdict || ing.status;
                const isOk = status === "allowed";
                const isWarn = status === "restricted" || status === "not_found" || status === "synthetic_flavor_warning";
                return (
                  <span key={i} className="text-[11px] px-2 py-0.5 rounded-full"
                    style={{
                      background: isOk ? "var(--ds-color-success-soft)" : isWarn ? "var(--ds-color-warning-soft)" : "var(--ds-color-error-soft)",
                      color: isOk ? "var(--ds-color-success-text)" : isWarn ? "var(--ds-color-warning-text)" : "var(--ds-color-error-text)",
                    }}>
                    {String(ing.name || "")}
                  </span>
                );
              })}
              {ingredients.length > 10 && (
                <span className="text-[11px] px-2 py-0.5 rounded-full"
                  style={{ background: "var(--ds-color-surface)", color: "var(--ds-color-text-tertiary)" }}>
                  +{ingredients.length - 10}개
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    );
  };

  // ── F3 결과 요약 렌더 ─────────────────────────────────
  const renderF3Summary = () => {
    const result = (f3Data?.final_result || f3Data?.ai_result) as Record<string, unknown> | null;
    if (!result) return (
      <p className="text-[13px]" style={{ color: "var(--ds-color-text-secondary)" }}>
        F3 필요서류 결과가 없습니다.
      </p>
    );
    const documents = result.documents as Array<Record<string, unknown>> || [];
    const mandatory = documents.filter((d) => d.is_mandatory);
    const optional = documents.filter((d) => !d.is_mandatory);
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 rounded-xl text-center"
            style={{ background: "var(--ds-color-error-soft)" }}>
            <p className="text-[22px] font-extrabold" style={{ color: "var(--ds-color-error-text)" }}>
              {mandatory.length}
            </p>
            <p className="text-[11px]" style={{ color: "var(--ds-color-error-text)" }}>필수 서류</p>
          </div>
          <div className="p-3 rounded-xl text-center"
            style={{ background: "var(--ds-color-surface)" }}>
            <p className="text-[22px] font-extrabold" style={{ color: "var(--ds-color-text-heading)" }}>
              {optional.length}
            </p>
            <p className="text-[11px]" style={{ color: "var(--ds-color-text-tertiary)" }}>선택 서류</p>
          </div>
        </div>
        <div className="space-y-1.5">
          {documents.slice(0, 5).map((doc, i) => (
            <div key={i} className="flex items-center gap-2 py-1.5 px-3 rounded-lg"
              style={{ background: "var(--ds-color-surface)" }}>
              <div className={`w-1.5 h-1.5 rounded-full shrink-0`}
                style={{ background: doc.is_mandatory ? "var(--ds-color-error)" : "var(--ds-color-text-tertiary)" }} />
              <span className="text-[12px]" style={{ color: "var(--ds-color-text-primary)" }}>
                {String(doc.doc_name || "")}
              </span>
              {!!doc.is_mandatory && (
                <span className="ml-auto text-[10px] font-medium"
                  style={{ color: "var(--ds-color-error-text)" }}>필수</span>
              )}
            </div>
          ))}
          {documents.length > 5 && (
            <p className="text-[11px] text-center mt-1" style={{ color: "var(--ds-color-text-tertiary)" }}>
              + {documents.length - 5}개 더보기 → 수정 버튼 클릭
            </p>
          )}
        </div>
      </div>
    );
  };

  // ── F4 결과 요약 렌더 ─────────────────────────────────
  const renderF4Summary = () => {
    const result = (f4Data?.ai_result || f4Data?.final_result) as Record<string, unknown> | null;
    if (!result && !f4Data?.items) return (
      <p className="text-[13px]" style={{ color: "var(--ds-color-text-secondary)" }}>
        F4 라벨검토 결과가 없습니다.
      </p>
    );
    const items = (f4Data?.items || result?.items || []) as Array<Record<string, unknown>>;
    const errors = items.filter((i) => i.severity === "error" || i.status === "fail");
    const warnings = items.filter((i) => i.severity === "warning" || i.status === "unclear");
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 rounded-xl text-center"
            style={{ background: errors.length > 0 ? "var(--ds-color-error-soft)" : "var(--ds-color-success-soft)" }}>
            <p className="text-[22px] font-extrabold"
              style={{ color: errors.length > 0 ? "var(--ds-color-error-text)" : "var(--ds-color-success-text)" }}>
              {errors.length}
            </p>
            <p className="text-[11px]"
              style={{ color: errors.length > 0 ? "var(--ds-color-error-text)" : "var(--ds-color-success-text)" }}>
              오류 항목
            </p>
          </div>
          <div className="p-3 rounded-xl text-center"
            style={{ background: warnings.length > 0 ? "var(--ds-color-warning-soft)" : "var(--ds-color-surface)" }}>
            <p className="text-[22px] font-extrabold"
              style={{ color: warnings.length > 0 ? "var(--ds-color-warning-text)" : "var(--ds-color-text-heading)" }}>
              {warnings.length}
            </p>
            <p className="text-[11px]"
              style={{ color: warnings.length > 0 ? "var(--ds-color-warning-text)" : "var(--ds-color-text-tertiary)" }}>
              주의 항목
            </p>
          </div>
        </div>
        {errors.length === 0 && warnings.length === 0 && (
          <div className="flex items-center gap-2 p-3 rounded-xl"
            style={{ background: "var(--ds-color-success-soft)" }}>
            <CheckCircle size={16} style={{ color: "var(--ds-color-success)" }} />
            <span className="text-[13px] font-medium" style={{ color: "var(--ds-color-success-text)" }}>
              라벨 검토 이상 없음
            </span>
          </div>
        )}
      </div>
    );
  };

  // ── F5 결과 렌더 (메인) ────────────────────────────────
  const renderF5Content = () => {
    const result = (f5Data?.final_result || f5Data?.ai_result) as Record<string, unknown> | null;
    if (!result) return (
      <div className="text-center py-8">
        <FileCheck size={32} className="mx-auto mb-3" style={{ color: "var(--ds-color-text-tertiary)" }} />
        <p className="text-[14px] font-medium mb-1" style={{ color: "var(--ds-color-text-secondary)" }}>
          한글표시사항 결과가 없습니다.
        </p>
        <p className="text-[12px] mb-4" style={{ color: "var(--ds-color-text-tertiary)" }}>
          서류 재업로드 후 다시 분석하거나, 아래 재분석 버튼을 눌러주세요.
        </p>
        <div className="flex items-center justify-center gap-2">
          <Button variant="secondary" size="md"
            onClick={() => router.push(`/cases/${caseId}/upload`)}>
            서류 재업로드
          </Button>
          <Button
            variant="primary"
            size="md"
            icon={running ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            onClick={handleRunPipeline}
            disabled={running}
          >
            {running ? (runMsg || "분석 중...") : "재분석 실행"}
          </Button>
        </div>
      </div>
    );

    // F5 결과가 있는 경우 — phase1/phase2 구조 또는 draft 구조 처리
    const phase1 = result.phase1 as Record<string, unknown> | null;
    const phase2 = result.phase2 as Record<string, unknown> | null;
    const items = (phase1?.items || []) as Array<Record<string, unknown>>;
    const draft = phase2?.draft as Record<string, unknown> | null;

    const passItems = items.filter((i) => i.status === "pass");
    const failItems = items.filter((i) => i.status === "fail");
    const unclearItems = items.filter((i) => i.status === "unclear");

    return (
      <div className="space-y-5">
        {/* 결과 요약 바 */}
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "적합", count: passItems.length, color: "var(--ds-color-success-soft)", textColor: "var(--ds-color-success-text)", },
            { label: "부적합", count: failItems.length, color: "var(--ds-color-error-soft)", textColor: "var(--ds-color-error-text)", },
            { label: "확인필요", count: unclearItems.length, color: "var(--ds-color-warning-soft)", textColor: "var(--ds-color-warning-text)", },
          ].map((stat) => (
            <div key={stat.label} className="p-3 rounded-xl text-center"
              style={{ background: stat.color }}>
              <p className="text-[24px] font-extrabold" style={{ color: stat.textColor }}>{stat.count}</p>
              <p className="text-[11px]" style={{ color: stat.textColor }}>{stat.label}</p>
            </div>
          ))}
        </div>

        {/* 다운로드 버튼 */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleDownload("docx")}
            disabled={downloading}
            className="flex items-center gap-2 text-[13px] font-medium px-4 py-2 rounded-lg border transition-all"
            style={{
              background: "var(--ds-color-primary)",
              color: "var(--ds-color-primary-contrast)",
              border: "none",
              opacity: downloading ? 0.6 : 1,
            }}
          >
            {downloading ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
            한글시안 다운로드 (DOCX)
          </button>
          <button
            onClick={() => handleDownload("pdf")}
            disabled={downloading}
            className="flex items-center gap-2 text-[13px] font-medium px-4 py-2 rounded-lg border transition-all"
            style={{
              color: "var(--ds-color-text-secondary)",
              borderColor: "var(--ds-color-border)",
              background: "var(--ds-color-surface)",
              opacity: downloading ? 0.6 : 1,
            }}
          >
            <Download size={14} />
            PDF
          </button>
        </div>

        {/* 항목별 결과 */}
        {items.length > 0 && (
          <div>
            <p className="text-[12px] font-semibold mb-2" style={{ color: "var(--ds-color-text-tertiary)" }}>
              검토 항목 ({items.length}개)
            </p>
            <div className="space-y-2">
              {items.slice(0, 8).map((item, i) => {
                const st = item.status as string;
                const isPass = st === "pass";
                const isFail = st === "fail";
                return (
                  <div key={i} className="flex items-start gap-3 py-2 px-3 rounded-lg"
                    style={{ background: "var(--ds-color-surface)" }}>
                    <div className="shrink-0 mt-0.5">
                      {isPass
                        ? <CheckCircle size={13} style={{ color: "var(--ds-color-success)" }} />
                        : isFail
                        ? <XCircle size={13} style={{ color: "var(--ds-color-error)" }} />
                        : <AlertTriangle size={13} style={{ color: "var(--ds-color-warning)" }} />
                      }
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-[12px] font-medium" style={{ color: "var(--ds-color-text-heading)" }}>
                        {String(item.field || "")}
                      </p>
                      {!!item.note && (
                        <p className="text-[11px] mt-0.5 line-clamp-2" style={{ color: "var(--ds-color-text-secondary)" }}>
                          {String(item.note)}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
              {items.length > 8 && (
                <button
                  onClick={() => goToEdit("f5")}
                  className="w-full py-2 text-[12px] text-center rounded-lg transition-colors"
                  style={{ background: "var(--ds-color-surface)", color: "var(--ds-color-primary-text)" }}
                >
                  + {items.length - 8}개 더보기 → 전체 결과 보기
                </button>
              )}
            </div>
          </div>
        )}

        {/* 한글시안 draft 미리보기 */}
        {draft && Object.keys(draft).length > 0 && (
          <div>
            <p className="text-[12px] font-semibold mb-2" style={{ color: "var(--ds-color-text-tertiary)" }}>
              한글표시사항 초안
            </p>
            <div className="rounded-xl p-4 space-y-2"
              style={{ background: "var(--ds-color-surface)", border: "1px solid var(--ds-color-border)" }}>
              {Object.entries(draft).slice(0, 6).map(([key, val]) => (
                <div key={key} className="flex gap-3">
                  <span className="text-[11px] font-semibold shrink-0 w-24"
                    style={{ color: "var(--ds-color-text-tertiary)" }}>
                    {key}
                  </span>
                  <span className="text-[12px]" style={{ color: "var(--ds-color-text-primary)" }}>
                    {String(val ?? "")}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  // ── F0 결과 요약 렌더 ─────────────────────────────────
  const renderF0Summary = () => {
    if (!f0Data) return (
      <p className="text-[13px]" style={{ color: "var(--ds-color-text-secondary)" }}>
        서류 업로드 및 OCR 분석 결과가 없습니다.
      </p>
    );
    const basic = f0Data.basic_info as Record<string, unknown> | null;
    const ingredients = f0Data.ingredients as Array<Record<string, unknown>> || [];
    return (
      <div className="space-y-3">
        {basic && (
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: "제품명", value: String(basic.product_name || "—") },
              { label: "수출국", value: String(basic.export_country || "—") },
              { label: "최초수입", value: basic.is_first_import ? "예" : "아니오" },
              { label: "유기농", value: basic.is_organic ? "예" : "아니오" },
            ].map(({ label, value }) => (
              <div key={label} className="px-3 py-2 rounded-lg"
                style={{ background: "var(--ds-color-surface)" }}>
                <p className="text-[10px]" style={{ color: "var(--ds-color-text-tertiary)" }}>{label}</p>
                <p className="text-[13px] font-medium" style={{ color: "var(--ds-color-text-heading)" }}>{value}</p>
              </div>
            ))}
          </div>
        )}
        {ingredients.length > 0 && (
          <div>
            <p className="text-[11px] font-semibold mb-1.5" style={{ color: "var(--ds-color-text-tertiary)" }}>
              원재료 ({ingredients.length}종)
            </p>
            <div className="flex flex-wrap gap-1">
              {ingredients.slice(0, 8).map((ing, i) => (
                <span key={i} className="text-[11px] px-2 py-0.5 rounded-full"
                  style={{ background: "var(--ds-color-surface)", color: "var(--ds-color-text-secondary)", border: "1px solid var(--ds-color-border)" }}>
                  {String(ing.name || "")}
                </span>
              ))}
              {ingredients.length > 8 && (
                <span className="text-[11px] px-2 py-0.5 rounded-full"
                  style={{ background: "var(--ds-color-surface)", color: "var(--ds-color-text-tertiary)" }}>
                  +{ingredients.length - 8}
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="min-h-screen" style={{ background: "var(--ds-color-bg)" }}>
      {/* ── 헤더 ── */}
      <header
        className="sticky top-0 z-50 border-b"
        style={{ background: "var(--ds-color-bg)", borderColor: "var(--ds-color-border)" }}
      >
        <div className="max-w-[1440px] mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push("/dashboard")}
              className="flex items-center gap-1.5 text-sm transition-colors"
              style={{ color: "var(--ds-color-text-secondary)" }}
            >
              <ChevronLeft size={16} />
              <span className="font-medium">대시보드</span>
            </button>
            <div className="w-px h-5" style={{ background: "var(--ds-color-border)" }} />
            <div className="flex items-center gap-2">
              <div
                className="w-7 h-7 rounded-lg flex items-center justify-center"
                style={{ background: "var(--ds-color-primary)" }}
              >
                <Shield size={13} className="text-white" />
              </div>
              <span className="text-[14px] font-semibold" style={{ color: "var(--ds-color-text-heading)" }}>
                {caseData?.product_name || "검역 건"}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {runMsg && (
              <span className="text-[12px] px-3 py-1 rounded-full"
                style={{ background: "var(--ds-color-primary-soft)", color: "var(--ds-color-primary-text)" }}>
                {runMsg}
              </span>
            )}
            <button
              onClick={loadAll}
              className="p-2 rounded-lg border transition-colors"
              style={{ border: "1px solid var(--ds-color-border)", color: "var(--ds-color-text-secondary)" }}
              title="새로고침"
            >
              <RefreshCw size={14} />
            </button>
            <Button
              variant="primary"
              size="md"
              icon={running ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              onClick={handleRunPipeline}
              disabled={running}
            >
              {running ? "분석 중..." : "전체 재분석"}
            </Button>
          </div>
        </div>
      </header>

      {/* ── 본문: 메인 + 우측 미니 네비 ── */}
      <div className="max-w-[1440px] mx-auto px-6 py-6 flex gap-6">
        {/* 메인 컨텐츠 */}
        <div className="flex-1 min-w-0">
          {/* F5 — 최종결과 (최상단, 항상 열림) */}
          <StageSection
            sectionKey="f5"
            label="F5 최종결과 — 한글표시사항"
            icon={<FileCheck size={14} />}
            status={f5Status}
            onEdit={() => goToEdit("f5")}
            editLabel="상세 수정"
            defaultOpen={true}
          >
            {renderF5Content()}
          </StageSection>

          {/* F4 — 라벨검토 */}
          <StageSection
            sectionKey="f4"
            label="F4 라벨검토"
            icon={<Globe size={14} />}
            status={f4Status}
            onEdit={() => goToEdit("f4")}
            defaultOpen={false}
          >
            {renderF4Summary()}
          </StageSection>

          {/* F3 — 필요서류 */}
          <StageSection
            sectionKey="f3"
            label="F3 필요서류"
            icon={<ClipboardCheck size={14} />}
            status={f3Status}
            onEdit={() => goToEdit("f3")}
            defaultOpen={false}
          >
            {renderF3Summary()}
          </StageSection>

          {/* F1 — 수입판정 */}
          <StageSection
            sectionKey="f1"
            label="F1 수입판정"
            icon={<Search size={14} />}
            status={f1Status}
            onEdit={() => goToEdit("f1")}
            defaultOpen={false}
          >
            {renderF1Summary()}
          </StageSection>

          {/* F0 — 서류업로드 */}
          <StageSection
            sectionKey="f0"
            label="F0 서류 업로드 및 OCR"
            icon={<FileText size={14} />}
            status={f0Data ? "ok" : "pending"}
            onEdit={() => goToEdit("upload")}
            editLabel="재업로드"
            defaultOpen={false}
          >
            {renderF0Summary()}
          </StageSection>
        </div>

        {/* 우측 미니 네비 */}
        <div className="w-[160px] shrink-0">
          <div className="sticky top-[80px]">
            <p className="text-[10px] font-semibold mb-3 uppercase tracking-wider"
              style={{ color: "var(--ds-color-text-tertiary)" }}>
              단계 이동
            </p>
            <div className="space-y-1">
              {SECTIONS.map(({ key, label, icon }) => {
                const isActive = activeSection === key;
                const statusMap: Record<SectionKey, typeof f1Status> = {
                  f5: f5Status,
                  f4: f4Status,
                  f3: f3Status,
                  f1: f1Status,
                  f0: f0Data ? "ok" : "pending",
                };
                const st = statusMap[key];
                return (
                  <button
                    key={key}
                    onClick={() => scrollToSection(key)}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-[12px] transition-all"
                    style={isActive
                      ? { background: "var(--ds-color-primary-soft)", color: "var(--ds-color-primary-text)", fontWeight: 600 }
                      : { color: "var(--ds-color-text-secondary)", background: "transparent" }
                    }
                  >
                    <span className="shrink-0">{icon}</span>
                    <span className="flex-1 truncate">{label.split(" ")[0]}</span>
                    {st === "ok" && <CheckCircle size={10} style={{ color: "var(--ds-color-success)", flexShrink: 0 }} />}
                    {st === "error" && <XCircle size={10} style={{ color: "var(--ds-color-error)", flexShrink: 0 }} />}
                    {st === "loading" && <Loader2 size={10} className="animate-spin shrink-0" style={{ color: "var(--ds-color-primary)" }} />}
                  </button>
                );
              })}
            </div>

            {/* 구분선 */}
            <div className="mt-4 pt-4" style={{ borderTop: "1px solid var(--ds-color-border-subtle)" }}>
              <button
                onClick={() => goToEdit("upload")}
                className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-[12px] transition-all"
                style={{ color: "var(--ds-color-text-tertiary)", background: "transparent" }}
              >
                <Package size={12} />
                <span>서류 재업로드</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
