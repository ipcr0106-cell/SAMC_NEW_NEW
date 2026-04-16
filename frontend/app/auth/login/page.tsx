"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { Shield, Mail, Lock, ArrowRight, Loader2 } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    const { error: authError } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    if (authError) {
      setError(
        authError.message === "Invalid login credentials"
          ? "이메일 또는 비밀번호가 올바르지 않습니다."
          : authError.message
      );
      setLoading(false);
      return;
    }

    router.push("/dashboard");
  };

  const handleSignUp = async () => {
    setLoading(true);
    setError("");

    const { error: signUpError } = await supabase.auth.signUp({
      email,
      password,
    });

    if (signUpError) {
      setError(signUpError.message);
      setLoading(false);
      return;
    }

    setError("");
    alert("가입 확인 이메일을 발송했습니다. 이메일을 확인해주세요.");
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-slate-50 flex">
      {/* 좌측: 브랜딩 패널 */}
      <div className="hidden lg:flex lg:w-[45%] bg-gradient-to-br from-blue-600 via-blue-700 to-indigo-800 p-12 flex-col justify-between relative overflow-hidden">
        {/* 배경 장식 */}
        <div className="absolute top-0 right-0 w-96 h-96 bg-white/5 rounded-full -translate-y-1/2 translate-x-1/2" />
        <div className="absolute bottom-0 left-0 w-64 h-64 bg-white/5 rounded-full translate-y-1/2 -translate-x-1/2" />

        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center backdrop-blur-sm">
              <Shield size={22} className="text-white" />
            </div>
            <span className="text-white/90 text-sm font-medium tracking-wider uppercase">
              SAMC Platform
            </span>
          </div>
          <h1 className="text-4xl font-bold text-white mt-8 leading-tight">
            수입식품
            <br />
            검역 AI
          </h1>
          <p className="text-blue-100 mt-4 text-lg leading-relaxed max-w-md">
            AI 기반 수입식품 검역 자동화 파이프라인으로
            <br />
            정확하고 신속한 검역 업무를 경험하세요.
          </p>
        </div>

        <div className="relative z-10">
          <div className="flex gap-6">
            {[
              { number: "5", label: "검역 기능" },
              { number: "14", label: "법령 DB" },
              { number: "AI", label: "Claude 기반" },
            ].map((stat) => (
              <div key={stat.label}>
                <div className="text-2xl font-bold text-white">
                  {stat.number}
                </div>
                <div className="text-blue-200 text-sm mt-0.5">
                  {stat.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 우측: 로그인 폼 */}
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-md">
          {/* 모바일용 로고 */}
          <div className="lg:hidden flex items-center gap-2.5 mb-8">
            <div className="w-9 h-9 bg-blue-600 rounded-xl flex items-center justify-center">
              <Shield size={18} className="text-white" />
            </div>
            <span className="text-lg font-bold text-slate-900">
              SAMC 검역 AI
            </span>
          </div>

          <h2 className="text-2xl font-bold text-slate-900">로그인</h2>
          <p className="text-slate-500 mt-1.5 mb-8">
            업무 계정으로 로그인하세요
          </p>

          <form onSubmit={handleLogin} className="space-y-4">
            {/* 이메일 */}
            <div>
              <label className="text-sm font-medium text-slate-700 mb-1.5 block">
                이메일
              </label>
              <div className="relative">
                <Mail
                  size={18}
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400"
                />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@samc.com"
                  required
                  className="w-full pl-11 pr-4 py-3 text-sm bg-white border border-slate-200 rounded-xl hover:border-slate-300 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none transition-all placeholder:text-slate-400"
                />
              </div>
            </div>

            {/* 비밀번호 */}
            <div>
              <label className="text-sm font-medium text-slate-700 mb-1.5 block">
                비밀번호
              </label>
              <div className="relative">
                <Lock
                  size={18}
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400"
                />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="비밀번호 입력"
                  required
                  minLength={6}
                  className="w-full pl-11 pr-4 py-3 text-sm bg-white border border-slate-200 rounded-xl hover:border-slate-300 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none transition-all placeholder:text-slate-400"
                />
              </div>
            </div>

            {/* 에러 메시지 */}
            {error && (
              <div className="bg-red-50 text-red-600 text-sm px-4 py-3 rounded-xl">
                {error}
              </div>
            )}

            {/* 로그인 버튼 */}
            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white font-medium py-3 rounded-xl hover:bg-blue-700 active:bg-blue-800 transition-all shadow-sm shadow-blue-600/20 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {loading ? (
                <Loader2 size={18} className="animate-spin" />
              ) : (
                <>
                  로그인
                  <ArrowRight size={16} />
                </>
              )}
            </button>

            {/* 구분선 */}
            <div className="flex items-center gap-3 py-2">
              <div className="flex-1 h-px bg-slate-200" />
              <span className="text-xs text-slate-400">또는</span>
              <div className="flex-1 h-px bg-slate-200" />
            </div>

            {/* 회원가입 버튼 */}
            <button
              type="button"
              onClick={handleSignUp}
              disabled={loading || !email || !password}
              className="w-full flex items-center justify-center gap-2 bg-slate-100 text-slate-700 font-medium py-3 rounded-xl hover:bg-slate-200 active:bg-slate-300 transition-all disabled:opacity-60 disabled:cursor-not-allowed"
            >
              새 계정 만들기
            </button>
          </form>

          <p className="text-xs text-slate-400 text-center mt-8">
            SAMC 수입식품 검역 AI 플랫폼 v0.1
          </p>
        </div>
      </div>
    </div>
  );
}
