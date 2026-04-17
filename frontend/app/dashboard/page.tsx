"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import {
  LogOut,
  Plus,
  FileText,
  ArrowRight,
  User as UserIcon,
  Menu,
  X,
  Trash2,
} from "lucide-react";
import type { User } from "@supabase/supabase-js";
import { createCase, listCases, deleteCase, type CaseData } from "@/lib/api";
import Button from "@/components/ui/Button";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [cases, setCases] = useState<CaseData[]>([]);
  const [casesTotal, setCasesTotal] = useState(0);
  const [creatingCase, setCreatingCase] = useState(false);
  const creatingCaseRef = useRef(false); // 동기 가드 — useState는 비동기라 더블클릭 방지 불완전
  const [activeTopMenu, setActiveTopMenu] = useState("start");

  const loadCases = async () => {
    try {
      const result = await listCases();
      setCases(result.cases);
      setCasesTotal(result.total);
    } catch (e) {
      console.error("케이스 목록 로드 실패:", e);
    }
  };

  useEffect(() => {
    const getUser = async () => {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session) {
        router.replace("/auth/login");
        return;
      }
      setUser(session.user);
      setLoading(false);
      await loadCases();
    };
    getUser();
  }, [router]);

  // 탭/창 포커스 시 목록 자동 새로고침
  useEffect(() => {
    const onFocus = () => loadCases();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);

  const handleLogout = async () => {
    await supabase.auth.signOut();
    router.replace("/auth/login");
  };

  const handleNewCase = async () => {
    // useRef 동기 가드: React state 업데이트는 비동기라 더블클릭/다중클릭 시 뚫릴 수 있음
    if (creatingCaseRef.current) return;
    creatingCaseRef.current = true;
    setCreatingCase(true);
    try {
      const newCase = await createCase("새 수입식품", "");
      router.push(`/cases/${newCase.id}/upload`);
    } catch (e) {
      console.error("케이스 생성 실패:", e);
      alert(`검역 건 생성에 실패했습니다.\n백엔드 서버가 실행 중인지 확인해주세요.\n\n오류: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      creatingCaseRef.current = false;
      setCreatingCase(false);
    }
  };

  const handleDeleteCase = async (e: React.MouseEvent, caseId: string) => {
    e.stopPropagation(); // 카드 클릭 이벤트 방지
    if (!confirm("이 검역 건을 삭제하시겠습니까? 관련 서류와 분석 결과가 모두 삭제됩니다.")) return;
    try {
      await deleteCase(caseId);
      setCases((prev) => prev.filter((c) => c.id !== caseId));
      setCasesTotal((prev) => prev - 1);
    } catch (e) {
      console.error("케이스 삭제 실패:", e);
      alert("삭제에 실패했습니다. 다시 시도해주세요.");
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen ds-landing-gradient flex items-center justify-center">
        <div
          className="animate-spin w-7 h-7 border-2 border-t-transparent rounded-full"
          style={{ borderColor: "var(--ds-color-primary)", borderTopColor: "transparent" }}
        />
      </div>
    );
  }

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  };

  const topMenuItems = [
    { id: "start", label: "시작", action: () => scrollTo("hero-section") },
    { id: "required-docs", label: "필요서류다운", action: () => alert("준비중입니다. 아직 백엔드 연동 전입니다.") },
    { id: "label-review", label: "라벨검토", action: () => alert("준비중입니다. 아직 백엔드 연동 전입니다.") },
    { id: "korean-label", label: "한글표시사항", action: () => alert("준비중입니다. 아직 백엔드 연동 전입니다.") },
  ];

  return (
    <div className="min-h-screen ds-landing-gradient">
      {/* ═══════════════════════════════════════════
          TOP NAV — Hirebyte style
          ═══════════════════════════════════════════ */}
      <nav className="fixed top-0 left-0 right-0 z-50 ds-glass-nav">
        <div className="max-w-[1280px] mx-auto px-8 h-[64px] flex items-center justify-between">
          {/* Logo + Nav */}
          <div className="flex items-center gap-10">
            <button
              onClick={() => router.push("/dashboard")}
              className="flex items-center gap-2.5"
            >
              <div className="flex items-center gap-1">
                <div className="w-3 h-3 rounded-full" style={{ background: "var(--ds-color-success)" }} />
                <div className="w-3 h-3 rounded-full" style={{ background: "var(--ds-color-primary)" }} />
              </div>
              <span className="text-[15px] font-bold tracking-tight" style={{ color: "var(--ds-color-text-heading)" }}>
                SAMC
              </span>
            </button>

            <div className="hidden md:flex items-center gap-1">
              {topMenuItems.map((item) => (
                <button
                  key={item.id}
                  onClick={() => {
                    setActiveTopMenu(item.id);
                    item.action();
                  }}
                  className={`flex items-center gap-1 px-4 py-[6px] rounded-full text-[13px] font-medium transition-all ${
                    activeTopMenu === item.id
                      ? "bg-slate-100 text-slate-900"
                      : "text-slate-500 hover:text-slate-700"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          {/* Right */}
          <div className="flex items-center gap-3">
            <div className="hidden md:flex items-center gap-2 text-slate-500 text-xs mr-2">
              <UserIcon size={14} />
              <span>{user?.email?.split("@")[0]}</span>
              <button
                onClick={handleLogout}
                className="ml-2 text-slate-400 hover:text-red-500 transition-colors"
              >
                <LogOut size={13} />
              </button>
            </div>
            <Button
              onClick={handleNewCase}
              variant="primary"
              size="md"
            >
              새 건 등록
            </Button>
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden w-8 h-8 flex items-center justify-center rounded-lg text-slate-500"
            >
              {mobileMenuOpen ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>
        </div>
      </nav>

      <section id="hero-section" className="max-w-[1280px] mx-auto px-8 pt-[94px]">
        <div className="text-center max-w-3xl mx-auto">
          <h1 className="text-[42px] sm:text-[56px] font-extrabold leading-[1.12]" style={{ color: "var(--ds-color-text-heading)" }}>
            Streamline Inspection Operations
            <br />
            <span style={{ color: "var(--ds-color-primary-text)" }}>with Smart AI Tools</span>
          </h1>
          <p className="text-[14px] sm:text-[16px] mt-5" style={{ color: "var(--ds-color-text-secondary)" }}>
            서류 업로드부터 법령 대조, 라벨 검토, 한글 시안 생성까지.
            토큰 기반 UI로 일관된 검역 워크플로우를 제공합니다.
          </p>
          <div className="mt-7">
            <Button variant="primary" size="lg" icon={<Plus size={16} />} onClick={handleNewCase}>
              Start New Case
            </Button>
          </div>
        </div>

        <div className="mt-8 grid grid-cols-2 gap-4">
          <div className="ds-surface-card p-5 sm:p-6">
            <p className="text-[12px] font-semibold" style={{ color: "var(--ds-color-text-tertiary)" }}>
              Quick Start
            </p>
            <h3 className="text-[24px] font-extrabold mt-1" style={{ color: "var(--ds-color-text-heading)" }}>
              서류 업로드하기
            </h3>
            <p className="text-[13px] mt-2" style={{ color: "var(--ds-color-text-secondary)" }}>
              파일 업로드 후 AI 검역 파이프라인을 시작합니다.
            </p>
            <div className="mt-5">
              <Button
                variant="primary"
                size="md"
                onClick={() => alert("백엔드 연결 전입니다. UI만 먼저 준비했습니다.")}
              >
                서류 업로드하기
              </Button>
            </div>
          </div>

          <div className="ds-surface-card p-5 sm:p-6">
            <p className="text-[12px] font-semibold" style={{ color: "var(--ds-color-text-tertiary)" }}>
              Jump In
            </p>
            <h3 className="text-[24px] font-extrabold mt-1" style={{ color: "var(--ds-color-text-heading)" }}>
              F3부터 시작하기
            </h3>
            <p className="text-[13px] mt-2" style={{ color: "var(--ds-color-text-secondary)" }}>
              필요서류 단계부터 바로 진입하는 빠른 작업 모드입니다.
            </p>
            <div className="mt-5">
              <Button
                variant="secondary"
                size="md"
                onClick={() => alert("백엔드 연결 전입니다. F3 시작 플로우는 추후 연결됩니다.")}
              >
                f3부터 시작하기
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════
          SECTION 3 — 케이스 목록 또는 Empty state
          ═══════════════════════════════════════════ */}
      <section id="cases-section" className="max-w-[1280px] mx-auto px-8 py-16">
        {cases.length > 0 ? (
          <div className="animate-fade-up">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-[18px] font-bold text-slate-900">
                검역 건 목록 <span className="text-slate-400 font-normal text-[14px] ml-2">{casesTotal}건</span>
              </h3>
              <Button
                onClick={handleNewCase}
                disabled={creatingCase}
                variant="primary"
                size="md"
              >
                새 건 등록
              </Button>
            </div>
            <div className="space-y-3">
              {cases.map((c) => {
                const statusMap: Record<string, { label: string; color: string }> = {
                  processing: { label: "진행중", color: "ds-badge ds-badge-blue" },
                  completed: { label: "완료", color: "ds-badge ds-badge-green" },
                  on_hold: { label: "보류", color: "ds-badge ds-badge-amber" },
                  error: { label: "오류", color: "ds-badge ds-badge-red" },
                };
                const st = statusMap[c.status] || statusMap.processing;
                const stepLabels: Record<string, string> = {
                  "0": "입력 완료",
                  "1": "F1 수입판정",
                  "2": "F2 유형분류",
                  "3": "F3 필요서류",
                  "4": "F4 라벨검토",
                  "5": "F5 한글시안",
                };
                return (
                  <div
                    key={c.id}
                    onClick={() => router.push(`/cases/${c.id}/upload`)}
                    role="button"
                    tabIndex={0}
                    className="w-full text-left bg-white rounded-xl border border-slate-200 p-5 hover:shadow-md hover:border-slate-300 transition-all group flex items-center gap-4 cursor-pointer"
                  >
                    <div className="w-10 h-10 bg-slate-100 rounded-xl flex items-center justify-center shrink-0 group-hover:bg-blue-50 transition-colors">
                      <FileText size={18} className="text-slate-400 group-hover:text-slate-700 transition-colors" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-[14px] font-semibold text-slate-900 truncate">{c.product_name}</p>
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        {c.importer_name || "수입자 미입력"} · {c.created_at ? new Date(c.created_at).toLocaleDateString("ko-KR") : ""}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {c.current_step && (
                        <span className="text-[10px] text-slate-500 bg-slate-50 px-2 py-1 rounded-md">
                          {stepLabels[c.current_step] || `Step ${c.current_step}`}
                        </span>
                      )}
                      <span className={`text-[10px] font-medium px-2.5 py-1 rounded-full ${st.color}`}>
                        {st.label}
                      </span>
                      <button
                        onClick={(e) => handleDeleteCase(e, c.id)}
                        className="p-1.5 rounded-lg text-slate-300 hover:text-red-500 hover:bg-red-50 transition-all opacity-0 group-hover:opacity-100"
                        title="삭제"
                      >
                        <Trash2 size={14} />
                      </button>
                      <ArrowRight size={14} className="text-slate-300 group-hover:text-slate-700 transition-colors" />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="animate-fade-up text-center py-10 ds-surface-card">
            <p className="text-sm" style={{ color: "var(--ds-color-text-secondary)" }}>등록된 검역 건이 없습니다.</p>
          </div>
        )}
      </section>

      {/* ═══════════════════════════════════════════
          FOOTER
          ═══════════════════════════════════════════ */}
      <footer className="border-t border-slate-100">
        <div className="max-w-[1280px] mx-auto px-8 py-6 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-0.5">
              <div className="w-2 h-2 rounded-full" style={{ background: "var(--ds-color-success)" }} />
              <div className="w-2 h-2 rounded-full" style={{ background: "var(--ds-color-primary)" }} />
            </div>
            <span className="text-[11px] font-semibold text-slate-400">
              SAMC 수입식품 검역 AI
            </span>
          </div>
          <span className="text-[10px] text-slate-400">
            &copy; 2026 SAMC. All rights reserved.
          </span>
        </div>
      </footer>
    </div>
  );
}
