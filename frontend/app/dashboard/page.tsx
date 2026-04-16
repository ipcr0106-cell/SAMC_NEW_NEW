"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import {
  Shield,
  LogOut,
  Plus,
  Search,
  FileText,
  ArrowRight,
  BookOpen,
  FileCheck,
  Tag,
  Languages,
  ClipboardList,
  Bell,
  Settings,
  User as UserIcon,
  Menu,
  X,
  Globe,
  ChevronDown,
  Calendar,
  BarChart3,
  Zap,
  Clock,
  CheckCircle2,
  Upload,
  Sparkles,
  Trash2,
} from "lucide-react";
import type { User } from "@supabase/supabase-js";
import { createCase, listCases, deleteCase, type CaseData } from "@/lib/api";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [cases, setCases] = useState<CaseData[]>([]);
  const [casesTotal, setCasesTotal] = useState(0);
  const [creatingCase, setCreatingCase] = useState(false);
  const creatingCaseRef = useRef(false); // 동기 가드 — useState는 비동기라 더블클릭 방지 불완전
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);

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
      <div className="min-h-screen bg-[#0f1117] flex items-center justify-center">
        <div className="animate-spin w-7 h-7 border-2 border-emerald-400 border-t-transparent rounded-full" />
      </div>
    );
  }

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  };

  const navItems = [
    { label: "Overview", active: true, action: () => scrollTo("hero-section") },
    {
      label: "검역관리",
      active: false,
      hasDropdown: true,
      action: () => scrollTo("cases-section"),
      dropdownItems: [
        { label: "새 건 등록", desc: "수입식품 검역 건을 새로 시작합니다", action: handleNewCase },
        { label: "전체 건 목록", desc: "등록된 검역 건 현황을 확인합니다", action: () => scrollTo("cases-section") },
        { label: "완료된 건", desc: "검역이 완료된 건을 조회합니다", action: () => scrollTo("cases-section") },
        { label: "법령 DB 관리", desc: "법령 파일 업데이트 및 DB 재구축", action: () => router.push("/admin/law-update") },
      ],
    },
    { label: "AI 기능", active: false, action: () => scrollTo("features-section") },
    { label: "파이프라인", active: false, action: () => scrollTo("pipeline-section") },
  ];

  const features = [
    {
      icon: ClipboardList,
      title: "AI 수입판정",
      desc: "법령 DB를 RAG 검색하여 수입 가능 여부를 자동 판정합니다. 식품위생법·수입식품안전관리특별법 기반.",
      accent: "blue",
    },
    {
      icon: Tag,
      title: "식품 유형분류",
      desc: "식품공전 기준에 따라 식품 유형을 자동 분류하고 기준규격을 매칭합니다.",
      accent: "violet",
    },
    {
      icon: FileCheck,
      title: "필요서류 자동생성",
      desc: "수입판정·유형분류 결과를 종합하여 검역에 필요한 서류 체크리스트를 생성합니다.",
      accent: "emerald",
    },
    {
      icon: Globe,
      title: "라벨 적합성 검토",
      desc: "Claude Vision으로 라벨 이미지를 분석하고 법적 표시사항 적합성을 자동 검토합니다.",
      accent: "amber",
    },
  ];

  const accentMap: Record<string, { bg: string; text: string; iconBg: string }> = {
    blue: { bg: "bg-blue-50", text: "text-blue-600", iconBg: "bg-blue-100" },
    violet: { bg: "bg-violet-50", text: "text-violet-600", iconBg: "bg-violet-100" },
    emerald: { bg: "bg-emerald-50", text: "text-emerald-600", iconBg: "bg-emerald-100" },
    amber: { bg: "bg-amber-50", text: "text-amber-600", iconBg: "bg-amber-100" },
  };

  return (
    <div className="min-h-screen bg-white">
      {/* ═══════════════════════════════════════════
          TOP NAV — Hirebyte style
          ═══════════════════════════════════════════ */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-[#0f1117]/80 backdrop-blur-xl border-b border-white/5">
        <div className="max-w-[1280px] mx-auto px-8 h-[64px] flex items-center justify-between">
          {/* Logo + Nav */}
          <div className="flex items-center gap-10">
            <button
              onClick={() => router.push("/dashboard")}
              className="flex items-center gap-2.5"
            >
              <div className="flex items-center gap-1">
                <div className="w-3 h-3 rounded-full bg-emerald-400" />
                <div className="w-3 h-3 rounded-full bg-blue-400" />
              </div>
              <span className="text-[15px] font-bold text-white tracking-tight">
                SAMC
              </span>
            </button>

            <div className="hidden md:flex items-center gap-1">
              {navItems.map((item) => (
                <div
                  key={item.label}
                  className="relative"
                  onMouseEnter={() => item.hasDropdown && setOpenDropdown(item.label)}
                  onMouseLeave={() => setOpenDropdown(null)}
                >
                  <button
                    onClick={() => !item.hasDropdown && item.action?.()}
                    className={`flex items-center gap-1 px-4 py-[6px] rounded-full text-[13px] font-medium transition-all ${
                      item.active
                        ? "bg-white/10 text-white"
                        : "text-white/50 hover:text-white/80"
                    }`}
                  >
                    {item.label}
                    {item.hasDropdown && (
                      <ChevronDown
                        size={12}
                        className={`transition-transform duration-200 ${openDropdown === item.label ? "rotate-180" : ""}`}
                      />
                    )}
                  </button>

                  {/* 드롭다운 메뉴 */}
                  {item.hasDropdown && item.dropdownItems && openDropdown === item.label && (
                    <div className="absolute top-full left-0 pt-2 z-50">
                      <div className="bg-[#1a1d27] border border-white/10 rounded-xl shadow-2xl shadow-black/40 py-2 min-w-[220px] backdrop-blur-xl">
                        {item.dropdownItems.map((sub, idx) => (
                          <button
                            key={idx}
                            onClick={sub.action}
                            className="w-full text-left px-4 py-2.5 hover:bg-white/5 transition-colors group"
                          >
                            <p className="text-[13px] font-medium text-white/80 group-hover:text-white">
                              {sub.label}
                            </p>
                            <p className="text-[11px] text-white/30 mt-0.5">
                              {sub.desc}
                            </p>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Right */}
          <div className="flex items-center gap-3">
            <div className="hidden md:flex items-center gap-2 text-white/40 text-xs mr-2">
              <UserIcon size={14} />
              <span>{user?.email?.split("@")[0]}</span>
              <button
                onClick={handleLogout}
                className="ml-2 text-white/30 hover:text-red-400 transition-colors"
              >
                <LogOut size={13} />
              </button>
            </div>
            <button
              onClick={handleNewCase}
              className="flex items-center gap-2 bg-emerald-500 text-white font-semibold text-[13px] px-5 py-2 rounded-full hover:bg-emerald-400 transition-all hover:shadow-lg hover:shadow-emerald-500/20"
            >
              새 건 등록
            </button>
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden w-8 h-8 flex items-center justify-center rounded-lg text-white/60"
            >
              {mobileMenuOpen ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>
        </div>
      </nav>

      {/* ═══════════════════════════════════════════
          HERO — Dark section with large heading
          ═══════════════════════════════════════════ */}
      <section id="hero-section" className="relative bg-[#0f1117] pt-[64px]">
        {/* Background glow — overflow-hidden only on glow container */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute top-20 left-1/2 -translate-x-1/2 w-[800px] h-[500px] bg-gradient-to-b from-blue-600/10 via-emerald-500/5 to-transparent rounded-full blur-3xl" />
        </div>

        <div className="relative max-w-[1280px] mx-auto px-8 pt-20 pb-32 text-center">
          {/* Heading */}
          <h1 className="text-[46px] sm:text-[60px] lg:text-[68px] font-extrabold text-white leading-[1.08] tracking-tight animate-fade-up">
            수입식품 검역 업무를
            <br />
            <span className="bg-gradient-to-r from-emerald-400 via-blue-400 to-emerald-400 bg-clip-text text-transparent">
              AI로 자동화
            </span>
          </h1>

          <p className="text-[15px] sm:text-[17px] text-white/40 leading-relaxed max-w-xl mx-auto mt-6 animate-fade-up delay-200">
            서류 업로드부터 수입판정, 유형분류, 라벨검토, 한글시안 생성까지.
            5단계 파이프라인을 Claude AI가 처리합니다.
          </p>

          {/* CTA */}
          <div className="flex items-center justify-center gap-4 mt-10 animate-fade-up delay-300">
            <button
              onClick={handleNewCase}
              className="flex items-center gap-2.5 bg-emerald-500 text-white font-bold text-[14px] px-8 py-3.5 rounded-full hover:bg-emerald-400 transition-all hover:shadow-xl hover:shadow-emerald-500/25 hover:-translate-y-0.5"
            >
              <Sparkles size={16} />
              무료로 시작하기
            </button>
          </div>
        </div>

        {/* ── Floating Dashboard Preview Card ── */}
        <div className="relative max-w-[1100px] mx-auto px-8 -mb-48 z-10">
          <div className="animate-scale-in delay-400">
            <div className="bg-white rounded-2xl shadow-2xl shadow-black/20 border border-slate-200/60 overflow-hidden">
              {/* Mini nav bar inside card */}
              <div className="bg-slate-50 border-b border-slate-100 px-6 py-3 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1">
                    <div className="w-2 h-2 rounded-full bg-emerald-400" />
                    <div className="w-2 h-2 rounded-full bg-blue-400" />
                  </div>
                  <span className="text-[12px] font-bold text-slate-700">SAMC</span>
                  <span className="text-[11px] text-slate-400 ml-2">Overview</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-full bg-slate-200" />
                </div>
              </div>

              {/* Stats row */}
              <div className="p-6">
                <div className="grid grid-cols-4 gap-4 mb-6">
                  {[
                    { label: "검역 상태", value: "진행중", icon: Clock, color: "text-blue-600" },
                    { label: "총 처리건", value: "—", icon: BarChart3, color: "text-emerald-600" },
                    { label: "직원 수", value: "—", icon: UserIcon, color: "text-violet-600" },
                    { label: "AI 정확도", value: "—", icon: Zap, color: "text-amber-600" },
                  ].map((stat, i) => (
                    <div
                      key={i}
                      className={`bg-slate-50 rounded-xl p-4 animate-fade-up`}
                      style={{ animationDelay: `${0.5 + i * 0.1}s` }}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[11px] text-slate-400 font-medium">{stat.label}</span>
                        <stat.icon size={14} className={stat.color} />
                      </div>
                      <p className="text-[20px] font-bold text-slate-900">{stat.value}</p>
                    </div>
                  ))}
                </div>

                {/* Pipeline steps mini */}
                <div className="bg-slate-50 rounded-xl p-4">
                  <p className="text-[11px] font-semibold text-slate-500 mb-3">파이프라인 단계</p>
                  <div className="flex items-center gap-2">
                    {["서류 업로드", "수입판정", "유형분류", "필요서류", "라벨검토", "한글시안"].map((step, i) => (
                      <div key={i} className="flex items-center gap-2 flex-1">
                        <div className={`w-7 h-7 rounded-lg flex items-center justify-center text-[10px] font-bold ${
                          i === 0 ? "bg-blue-600 text-white" : "bg-slate-200 text-slate-400"
                        }`}>
                          {i === 0 ? <Upload size={12} /> : i}
                        </div>
                        <span className="text-[10px] text-slate-500 hidden lg:block truncate">{step}</span>
                        {i < 5 && <div className="flex-1 h-px bg-slate-200 hidden lg:block" />}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════
          SPACER for floating card
          ═══════════════════════════════════════════ */}
      <div className="h-56" />

      {/* ═══════════════════════════════════════════
          SECTION 1 — "Scale Hiring Operations" style
          Left: Schedule card + stats | Right: Description
          ═══════════════════════════════════════════ */}
      <section id="pipeline-section" className="max-w-[1280px] mx-auto px-8 py-20">
        <div className="grid lg:grid-cols-2 gap-16 items-center">
          {/* Left — UI cards */}
          <div className="animate-slide-left delay-100">
            <div className="space-y-4">
              {/* Schedule card */}
              <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:shadow-md transition-shadow">
                <p className="text-[11px] font-semibold text-slate-400 mb-3">검역 건 등록</p>
                <div className="flex items-center gap-3 mb-4">
                  <Calendar size={16} className="text-blue-500" />
                  <div>
                    <p className="text-sm font-semibold text-slate-800">서류 업로드 후 AI 분석 시작</p>
                    <p className="text-xs text-slate-400 mt-0.5">원재료배합비율표, 제조공정도, MSDS, 라벨사진</p>
                  </div>
                </div>
                <div className="flex gap-2">
                  {["성분표", "공정도", "MSDS", "라벨"].map((doc, i) => (
                    <span
                      key={i}
                      className="px-3 py-1.5 bg-slate-50 rounded-lg text-[11px] font-medium text-slate-500 border border-slate-100"
                    >
                      {doc}
                    </span>
                  ))}
                </div>
              </div>

              {/* Stats row */}
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:shadow-md transition-shadow">
                  <p className="text-[11px] font-semibold text-slate-400 mb-1">총 처리 시간</p>
                  <p className="text-[28px] font-extrabold text-slate-900 leading-tight">
                    4<span className="text-[20px]">분</span> 32<span className="text-[20px]">초</span>
                  </p>
                  <p className="text-[10px] text-emerald-500 font-medium mt-1">평균 대비 -23% 단축</p>
                </div>
                <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:shadow-md transition-shadow">
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-[11px] font-semibold text-slate-400">공정 코드 변환</p>
                    <span className="text-[10px] font-bold text-emerald-500 bg-emerald-50 px-2 py-0.5 rounded-full">4.87</span>
                  </div>
                  <div className="mt-3 space-y-2">
                    {[85, 72, 93, 60].map((w, i) => (
                      <div key={i} className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-blue-500 rounded-full transition-all duration-1000"
                          style={{ width: `${w}%`, animationDelay: `${i * 0.2}s` }}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Right — Description */}
          <div className="animate-slide-right delay-200">
            <h2 className="text-[32px] sm:text-[38px] font-extrabold text-slate-900 leading-[1.15] tracking-tight">
              검역 업무를 AI로
              <br />
              빠르게 처리하세요
            </h2>
            <p className="text-[14px] text-slate-500 leading-relaxed mt-5 max-w-md">
              서류를 업로드하면 AI가 OCR로 텍스트를 추출하고,
              제조공정을 유니패스 코드로 자동 변환합니다.
              성분 분석, 법령 검색, 라벨 검토까지 한 번에 처리합니다.
            </p>
            <button
              onClick={() => scrollTo("cases-section")}
              className="flex items-center gap-2 mt-8 text-blue-600 font-semibold text-[14px] hover:text-blue-700 transition-colors group"
            >
              검역건 목록 보기
              <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
            </button>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════
          SECTION 2 — "Discover Powerful Features" style
          ═══════════════════════════════════════════ */}
      <section id="features-section" className="bg-slate-50 border-t border-slate-100">
        <div className="max-w-[1280px] mx-auto px-8 py-20">
          <div className="text-center mb-14 animate-fade-up">
            <h2 className="text-[32px] sm:text-[38px] font-extrabold text-slate-900 leading-[1.15] tracking-tight">
              5단계 AI 파이프라인으로
              <br />
              검역 업무를 자동화
            </h2>
            <p className="text-[14px] text-slate-500 leading-relaxed mt-4 max-w-lg mx-auto">
              서류 업로드 한 번이면 AI가 수입판정부터 한글시안 생성까지
              전체 검역 프로세스를 자동으로 처리합니다.
            </p>
          </div>

          {/* Feature cards — 4 columns */}
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {features.map((f, i) => {
              const Icon = f.icon;
              const a = accentMap[f.accent];
              return (
                <div
                  key={i}
                  className={`bg-white rounded-2xl border border-slate-200/60 p-6 hover:shadow-lg hover:-translate-y-1 transition-all group animate-fade-up`}
                  style={{ animationDelay: `${0.1 + i * 0.1}s` }}
                >
                  <div className={`w-11 h-11 ${a.iconBg} rounded-xl flex items-center justify-center mb-4`}>
                    <Icon size={20} className={a.text} />
                  </div>
                  <h3 className="text-[15px] font-bold text-slate-900 mb-2">
                    {f.title}
                  </h3>
                  <p className="text-[12px] text-slate-500 leading-relaxed">
                    {f.desc}
                  </p>
                </div>
              );
            })}
          </div>

          {/* 5th feature — full width */}
          <div
            className="mt-5 bg-white rounded-2xl border border-slate-200/60 p-6 hover:shadow-lg transition-all group flex items-center gap-6 animate-fade-up delay-500"
          >
            <div className="w-11 h-11 bg-rose-100 rounded-xl flex items-center justify-center shrink-0">
              <Languages size={20} className="text-rose-600" />
            </div>
            <div className="flex-1">
              <h3 className="text-[15px] font-bold text-slate-900 mb-1">
                한글 표시사항 시안 자동생성
              </h3>
              <p className="text-[12px] text-slate-500 leading-relaxed">
                이전 4단계의 분석 결과를 종합하여 수입식품 한글 표시사항 시안을 자동 생성하고 PDF/DOCX로 출력합니다.
                DeepL API 번역과 법적 표시사항 자동 적용을 포함합니다.
              </p>
            </div>
            <ArrowRight size={18} className="text-slate-200 shrink-0" />
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════
          SECTION 3 — 케이스 목록 또는 Empty state
          ═══════════════════════════════════════════ */}
      <section id="cases-section" className="max-w-[1280px] mx-auto px-8 py-20">
        {cases.length === 0 ? (
          <div className="text-center animate-fade-up">
            <div className="w-14 h-14 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-5">
              <FileText size={24} className="text-slate-400" />
            </div>
            <h3 className="text-[18px] font-bold text-slate-900 mb-2">
              아직 등록된 검역 건이 없습니다
            </h3>
            <p className="text-[13px] text-slate-500 mb-7 max-w-sm mx-auto">
              첫 번째 건을 등록하고 AI 검역 파이프라인을 체험해보세요
            </p>
            <button
              onClick={handleNewCase}
              className="inline-flex items-center gap-2 bg-[#0f1117] text-white font-semibold text-[13px] px-7 py-3 rounded-full hover:bg-slate-800 transition-all hover:shadow-lg"
            >
              <Plus size={15} />
              첫 번째 건 등록하기
            </button>
          </div>
        ) : (
          <div className="animate-fade-up">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-[18px] font-bold text-slate-900">
                검역 건 목록 <span className="text-slate-400 font-normal text-[14px] ml-2">{casesTotal}건</span>
              </h3>
              <button
                onClick={handleNewCase}
                disabled={creatingCase}
                className="inline-flex items-center gap-2 bg-[#0f1117] text-white font-semibold text-[13px] px-5 py-2.5 rounded-full hover:bg-slate-800 transition-all disabled:opacity-50"
              >
                <Plus size={14} />
                새 건 등록
              </button>
            </div>
            <div className="space-y-3">
              {cases.map((c) => {
                const statusMap: Record<string, { label: string; color: string }> = {
                  processing: { label: "진행중", color: "bg-blue-100 text-blue-700" },
                  completed: { label: "완료", color: "bg-emerald-100 text-emerald-700" },
                  on_hold: { label: "보류", color: "bg-amber-100 text-amber-700" },
                  error: { label: "오류", color: "bg-red-100 text-red-700" },
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
                      <FileText size={18} className="text-slate-400 group-hover:text-blue-500 transition-colors" />
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
                      <ArrowRight size={14} className="text-slate-300 group-hover:text-blue-500 transition-colors" />
                    </div>
                  </div>
                );
              })}
            </div>
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
              <div className="w-2 h-2 rounded-full bg-emerald-400" />
              <div className="w-2 h-2 rounded-full bg-blue-400" />
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
