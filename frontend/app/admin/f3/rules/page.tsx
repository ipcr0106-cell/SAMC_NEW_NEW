"use client";

import { ArrowLeft } from "lucide-react";
import { useRouter } from "next/navigation";
import { RuleAddForm } from "@/features/feature3/admin/RuleAddForm";

export default function F3ManualRulesPage() {
  const router = useRouter();

  return (
    <div className="min-h-screen bg-white">
      {/* 상단 네비 */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-[#0f1117]/80 backdrop-blur-xl border-b border-white/5">
        <div className="max-w-[1280px] mx-auto px-8 h-[64px] flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push("/dashboard")}
              className="flex items-center gap-2 text-white/50 hover:text-white transition-colors"
            >
              <ArrowLeft size={16} />
              <span className="text-[13px]">대시보드</span>
            </button>
            <div className="w-px h-5 bg-white/10" />
            <h1 className="text-[15px] font-bold text-white">
              수입필요서류 안내 · 수동 규칙 추가
            </h1>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => router.push("/admin/law-update")}
              className="text-[12px] px-3 py-1.5 rounded-md border border-white/10 text-white/70 hover:text-white hover:border-white/20"
            >
              법령 업로드로
            </button>
          </div>
        </div>
      </nav>

      {/* 본문 */}
      <div className="pt-[96px] pb-20 px-8">
        <RuleAddForm />
      </div>
    </div>
  );
}
