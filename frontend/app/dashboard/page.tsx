"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import {
  LogOut, User as UserIcon, Database, ArrowRight, FileSearch, Clock,
} from "lucide-react";
import type { User } from "@supabase/supabase-js";
import { createCase } from "@/lib/api";

// ── CountUp ───────────────────────────────────────────────
function CountUp({
  target, prefix = "", suffix = "", duration = 1400, delay = 0, active,
}: {
  target: number; prefix?: string; suffix?: string;
  duration?: number; delay?: number; active: boolean;
}) {
  const [display, setDisplay] = useState(0);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (!active) return;
    const timer = setTimeout(() => {
      const start = performance.now();
      const animate = (now: number) => {
        const elapsed = now - start;
        const p = Math.min(elapsed / duration, 1);
        const ease = p === 1 ? 1 : 1 - Math.pow(2, -10 * p);
        setDisplay(Math.round(ease * target));
        if (p < 1) rafRef.current = requestAnimationFrame(animate);
      };
      rafRef.current = requestAnimationFrame(animate);
    }, delay);
    return () => {
      clearTimeout(timer);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [active, target, duration, delay]);

  return <>{prefix}{display}{suffix}</>;
}

// ── 메인 ─────────────────────────────────────────────────
export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser]               = useState<User | null>(null);
  const [loading, setLoading]         = useState(true);
  const [creatingCase, setCreatingCase] = useState(false);
  const creatingCaseRef               = useRef(false);
  const [lawCount, setLawCount]       = useState<number | null>(null);
  const [statsActive, setStatsActive] = useState(false);
  const [heroVisible, setHeroVisible] = useState(false);

  useEffect(() => {
    const init = async () => {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) { router.replace("/auth/login"); return; }
      setUser(session.user);
      setLoading(false);
      setTimeout(() => setHeroVisible(true), 80);
      setTimeout(() => setStatsActive(true), 500);
    };
    init();
  }, [router]);

  useEffect(() => {
    const BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1").replace("/api/v1", "");
    fetch(`${BASE}/admin/law-update/laws`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.laws) setLawCount(d.laws.length); })
      .catch(() => {});
  }, []);

  const handleLogout = async () => {
    await supabase.auth.signOut();
    router.replace("/auth/login");
  };

  const handleNewCase = async () => {
    if (creatingCaseRef.current) return;
    creatingCaseRef.current = true;
    setCreatingCase(true);
    try {
      const c = await createCase("새 수입식품", "");
      router.push(`/cases/${c.id}/upload`);
    } catch (e) {
      alert(`검역 건 생성에 실패했습니다.\n\n오류: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      creatingCaseRef.current = false;
      setCreatingCase(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--ds-color-bg)" }}>
        <div className="flex gap-1.5">
          {[0,1,2].map(i => (
            <div key={i} className="w-2 h-2 rounded-full animate-bounce"
              style={{ background: "var(--ds-color-primary)", animationDelay: `${i*120}ms` }} />
          ))}
        </div>
      </div>
    );
  }

  const stats = [
    { label: "분석 단계",       target: 4,            suffix: "단계", desc: "F0 → F5 자동 파이프라인",   icon: FileSearch, iconBg: "rgba(0,106,245,0.08)",  iconColor: "var(--ds-color-primary)" },
    { label: "평균 처리",       target: 60, prefix:"~", suffix: "초", desc: "서류 1건 기준",             icon: Clock,       iconBg: "rgba(34,197,94,0.1)",    iconColor: "var(--ds-color-success)" },
    { label: "법령 데이터베이스", target: lawCount ?? 0, suffix: "개", desc: "식품·표시·첨가물 법령",    icon: Database,    iconBg: "rgba(245,158,11,0.10)",  iconColor: "#F59E0B", pending: lawCount === null },
  ];

  return (
    <>
      <style>{`
        @keyframes _fadeUp {
          from { opacity: 0; transform: translateY(20px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes _fadeIn {
          from { opacity: 0; } to { opacity: 1; }
        }
        @keyframes _scaleUp {
          from { opacity: 0; transform: scale(0.97) translateY(8px); }
          to   { opacity: 1; transform: scale(1) translateY(0); }
        }
        @keyframes _badgePulse {
          0%,100% { box-shadow: 0 0 0 0 rgba(0,106,245,0.2); }
          50%     { box-shadow: 0 0 0 5px rgba(0,106,245,0); }
        }
        @keyframes _float {
          0%,100% { transform: translateY(0); }
          50%     { transform: translateY(-7px); }
        }
        .hero-badge { animation: _fadeIn  0.5s  cubic-bezier(.16,1,.3,1) both; }
        .hero-title { animation: _fadeUp  0.75s cubic-bezier(.16,1,.3,1) both; }
        .hero-sub   { animation: _fadeUp  0.75s cubic-bezier(.16,1,.3,1) both; }
        .hero-btn   { animation: _scaleUp 0.6s  cubic-bezier(.16,1,.3,1) both; }
        .stat-item  { animation: _fadeUp  0.65s cubic-bezier(.16,1,.3,1) both; }
        .cases-in   { animation: _fadeUp  0.55s cubic-bezier(.16,1,.3,1) both; }
        .btn-start {
          transition: box-shadow .22s, transform .18s, opacity .18s;
          box-shadow: 0 2px 16px rgba(0,106,245,.28), 0 1px 4px rgba(0,106,245,.16);
        }
        .btn-start:hover:not(:disabled) {
          box-shadow: 0 6px 28px rgba(0,106,245,.38), 0 2px 8px rgba(0,106,245,.22);
          transform: translateY(-1px);
        }
        .btn-start:active:not(:disabled) {
          transform: translateY(0);
          box-shadow: 0 1px 8px rgba(0,106,245,.2);
        }
        .orb { animation: _float 7s ease-in-out infinite; }
      `}</style>

      <div className="min-h-screen" style={{ background: "linear-gradient(160deg, #eef4ff 0%, #f5f8ff 40%, #ffffff 100%)" }}>

        {/* ── 배경 장식 ── */}
        <div className="fixed inset-0 overflow-hidden pointer-events-none" style={{ zIndex: 0 }}>
          <div className="orb absolute top-[-80px] left-[6%] w-[560px] h-[560px] rounded-full"
            style={{ background: "radial-gradient(circle, rgba(0,106,245,0.13) 0%, transparent 70%)", animationDelay: "0s" }} />
          <div className="orb absolute top-[60px] right-[2%] w-[420px] h-[420px] rounded-full"
            style={{ background: "radial-gradient(circle, rgba(0,153,255,0.09) 0%, transparent 70%)", animationDelay: "2.5s" }} />
        </div>

        {/* ── 네비게이션 ── */}
        <nav className="fixed top-0 left-0 right-0 z-50"
          style={{ background: "rgba(255,255,255,0.72)", backdropFilter: "blur(20px)", borderBottom: "1px solid var(--ds-color-border-subtle)" }}>
          <div className="max-w-[1280px] mx-auto px-8 h-[60px] flex items-center justify-between">
            <button onClick={() => router.push("/dashboard")} className="flex items-center gap-2.5">
              <div className="flex items-center gap-1">
                <div className="w-2.5 h-2.5 rounded-full" style={{ background: "var(--ds-color-success)" }} />
                <div className="w-2.5 h-2.5 rounded-full" style={{ background: "var(--ds-color-primary)" }} />
              </div>
              <span className="text-[15px] font-bold tracking-tight" style={{ color: "var(--ds-color-text-heading)" }}>SAMC</span>
            </button>

            <div className="flex items-center gap-4">
              <button onClick={() => router.push("/cases")}
                className="text-[13px] font-medium transition-colors"
                style={{ color: "var(--ds-color-text-secondary)" }}
                onMouseEnter={e => (e.currentTarget.style.color = "var(--ds-color-text-heading)")}
                onMouseLeave={e => (e.currentTarget.style.color = "var(--ds-color-text-secondary)")}>
                검역건 목록
              </button>
              <button onClick={() => router.push("/db")}
                className="flex items-center gap-1.5 text-[13px] font-medium transition-colors"
                style={{ color: "var(--ds-color-text-secondary)" }}
                onMouseEnter={e => (e.currentTarget.style.color = "var(--ds-color-text-heading)")}
                onMouseLeave={e => (e.currentTarget.style.color = "var(--ds-color-text-secondary)")}>
                <Database size={12} /> DB
              </button>
              <div className="w-px h-4" style={{ background: "var(--ds-color-border)" }} />
              <div className="flex items-center gap-2">
                <UserIcon size={13} style={{ color: "var(--ds-color-text-tertiary)" }} />
                <span className="text-[12px]" style={{ color: "var(--ds-color-text-secondary)" }}>
                  {user?.email?.split("@")[0]}
                </span>
                <button onClick={handleLogout} className="transition-colors ml-1"
                  style={{ color: "var(--ds-color-text-tertiary)" }}
                  onMouseEnter={e => (e.currentTarget.style.color = "var(--ds-color-error-text)")}
                  onMouseLeave={e => (e.currentTarget.style.color = "var(--ds-color-text-tertiary)")}>
                  <LogOut size={13} />
                </button>
              </div>
            </div>
          </div>
        </nav>

        {/* ── 히어로 ── */}
        <section className="relative z-10 max-w-[1280px] mx-auto px-8 pt-[136px] pb-16 text-center">

          {/* 배지 */}
          <div className="hero-badge inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-[12px] font-semibold mb-9"
            style={{
              animationDelay: heroVisible ? "0ms" : "9999s",
              background: "var(--ds-color-primary-soft)",
              color: "var(--ds-color-primary-text)",
              border: "1px solid rgba(0,106,245,0.14)",
              animation: heroVisible
                ? "_badgePulse 2.8s ease-in-out 0.5s infinite, _fadeIn 0.5s cubic-bezier(.16,1,.3,1) both"
                : "none",
            }}>
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--ds-color-primary)", animation: "pulse 2s ease-in-out infinite" }} />
            수입식품 검역 자동화
          </div>

          {/* 타이틀 */}
          <h1 className="hero-title font-extrabold leading-[1.15] tracking-[-0.035em] mb-10"
            style={{
              animationDelay: heroVisible ? "100ms" : "9999s",
              color: "var(--ds-color-text-heading)",
            }}>
            <span style={{ fontSize: "clamp(38px, 4.8vw, 62px)", display: "block" }}>SAMC</span>
            <span style={{ fontSize: "clamp(22px, 2.6vw, 34px)", color: "var(--ds-color-primary)", fontWeight: 700, display: "block" }}>AI 검역 보조 서비스</span>
          </h1>

          {/* CTA */}
          <div className="hero-btn flex items-center justify-center gap-3 mb-16"
            style={{ animationDelay: heroVisible ? "360ms" : "9999s" }}>
            <button onClick={handleNewCase} disabled={creatingCase}
              className="btn-start flex items-center gap-2 px-8 py-3.5 rounded-xl text-[15px] font-bold text-white disabled:opacity-60"
              style={{ background: "var(--ds-color-primary)" }}>
              {creatingCase
                ? <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />생성 중...</>
                : <>START <ArrowRight size={15} /></>}
            </button>
            <button onClick={() => router.push("/cases")}
              className="px-6 py-3.5 rounded-xl text-[14px] font-medium border transition-all"
              style={{ color: "var(--ds-color-text-secondary)", borderColor: "var(--ds-color-border)", background: "var(--ds-color-surface)" }}>
              검역건 목록
            </button>
          </div>

          {/* 통계 카드 */}
          <div className="grid grid-cols-3 gap-4 w-full max-w-[860px] mx-auto">
            {stats.map((s, i) => {
              const Icon = s.icon;
              return (
                <div key={s.label} className="stat-item rounded-2xl p-6 text-left"
                  style={{
                    animationDelay: heroVisible ? `${480 + i*90}ms` : "9999s",
                    background: "var(--ds-color-surface)",
                    border: "1px solid var(--ds-color-border-subtle)",
                    boxShadow: "0 2px 14px rgba(0,0,0,0.05)",
                  }}>
                  {/* 아이콘 + 라벨 */}
                  <div className="flex items-center gap-2.5 mb-5">
                    <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
                      style={{ background: s.iconBg }}>
                      <Icon size={16} style={{ color: s.iconColor }} />
                    </div>
                    <span className="text-[13px] font-medium" style={{ color: "var(--ds-color-text-secondary)" }}>{s.label}</span>
                  </div>
                  {/* 숫자 */}
                  <div className="text-[34px] font-extrabold tabular-nums leading-none mb-2"
                    style={{ color: "var(--ds-color-text-heading)" }}>
                    {s.pending
                      ? <span style={{ color: "var(--ds-color-text-tertiary)", fontSize: "22px" }}>—</span>
                      : <CountUp target={s.target} prefix={s.prefix} suffix={s.suffix} active={statsActive} delay={i*110} />}
                  </div>
                  {/* 설명 */}
                  <div className="text-[12px]" style={{ color: "var(--ds-color-text-tertiary)" }}>{s.desc}</div>
                </div>
              );
            })}
          </div>
        </section>

        {/* ── 푸터 ── */}
        <footer className="relative z-10" style={{ background: "#192434" }}>

          {/* 링크 컬럼 섹션 */}
          <div className="max-w-[1280px] mx-auto px-8 pt-14 pb-10">
            <div className="grid grid-cols-3 gap-10">

              {/* 검역 워크플로우 */}
              <div>
                <p className="text-[11px] font-bold tracking-widest uppercase mb-5" style={{ color: "rgba(255,255,255,0.35)" }}>검역 워크플로우</p>
                <ul className="space-y-3">
                  {[
                    { label: "서류 업로드 & 분석",   href: "/cases" },
                    { label: "수입판정",             href: "/cases" },
                    { label: "필요서류 확인",         href: "/cases" },
                    { label: "라벨 적합성 검토",      href: "/cases" },
                    { label: "한글표시사항 시안",      href: "/cases" },
                  ].map(item => (
                    <li key={item.label}>
                      <button onClick={() => router.push(item.href)}
                        className="text-[13px] transition-colors text-left"
                        style={{ color: "rgba(255,255,255,0.65)" }}
                        onMouseEnter={e => (e.currentTarget.style.color = "#fff")}
                        onMouseLeave={e => (e.currentTarget.style.color = "rgba(255,255,255,0.65)")}>
                        {item.label}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>

              {/* 데이터 & 관리 */}
              <div>
                <p className="text-[11px] font-bold tracking-widest uppercase mb-5" style={{ color: "rgba(255,255,255,0.35)" }}>데이터 & 관리</p>
                <ul className="space-y-3">
                  {[
                    { label: "검역건 목록",      href: "/cases" },
                    { label: "DB 법령 조회",     href: "/db" },
                    { label: "통합 현황 대시보드", href: "/dashboard" },
                  ].map(item => (
                    <li key={item.label}>
                      <button onClick={() => router.push(item.href)}
                        className="text-[13px] transition-colors text-left"
                        style={{ color: "rgba(255,255,255,0.65)" }}
                        onMouseEnter={e => (e.currentTarget.style.color = "#fff")}
                        onMouseLeave={e => (e.currentTarget.style.color = "rgba(255,255,255,0.65)")}>
                        {item.label}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>

              {/* 지원 & 안내 */}
              <div>
                <p className="text-[11px] font-bold tracking-widest uppercase mb-5" style={{ color: "rgba(255,255,255,0.35)" }}>지원 & 안내</p>
                <ul className="space-y-3">
                  {[
                    { label: "이용 가이드",   href: null },
                    { label: "단축키 안내",   href: null },
                    { label: "업데이트 내역", href: null },
                    { label: "오류 신고",     href: null },
                  ].map(item => (
                    <li key={item.label}>
                      <span className="text-[13px]" style={{ color: "rgba(255,255,255,0.4)", cursor: "default" }}>
                        {item.label}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>

            </div>
          </div>

          {/* 구분선 */}
          <div className="max-w-[1280px] mx-auto px-8">
            <div style={{ borderTop: "1px solid rgba(255,255,255,0.1)" }} />
          </div>

          {/* 하단 회사 정보 */}
          <div className="max-w-[1280px] mx-auto px-8 py-8 flex items-center justify-between gap-8">
            {/* 로고 + 회사 정보 묶음 */}
            <div className="flex items-center gap-5">
              {/* 로고 */}
              <div className="shrink-0">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src="/samc-logo.png"
                  alt="SAMC 관세법인 에스에이엠씨"
                  style={{ width: "150px", height: "auto", display: "block", mixBlendMode: "screen", filter: "grayscale(1) brightness(2)" }}
                />
              </div>
              {/* 세로 구분선 */}
              <div className="w-px h-8 shrink-0" style={{ background: "rgba(255,255,255,0.12)" }} />
              {/* 회사 법인 정보 */}
              <div className="space-y-1">
                <p className="text-[11px] leading-relaxed" style={{ color: "rgba(255,255,255,0.45)" }}>
                  법인명: 관세법인에스에이엠씨&nbsp;&nbsp;|&nbsp;&nbsp;대표 관세사: 이동엽&nbsp;&nbsp;|&nbsp;&nbsp;사업자등록번호: 138-81-50084
                </p>
                <p className="text-[11px] leading-relaxed" style={{ color: "rgba(255,255,255,0.45)" }}>
                  주소: 경기도 광명시 양지로21(일직동, 유플래닛 T타워 7층)&nbsp;&nbsp;|&nbsp;&nbsp;대표번호: 031-462-0303&nbsp;&nbsp;|&nbsp;&nbsp;FAX: 031-462-0308
                </p>
              </div>
            </div>

            {/* 카피라이트 */}
            <div className="shrink-0">
              <p className="text-[11px]" style={{ color: "rgba(255,255,255,0.3)" }}>
                © 2026 SAMC ALL RIGHTS RESERVED.
              </p>
            </div>
          </div>

        </footer>
      </div>
    </>
  );
}
