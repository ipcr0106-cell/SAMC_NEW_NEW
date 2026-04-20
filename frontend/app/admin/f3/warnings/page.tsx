"use client";

import { ArrowLeft } from "lucide-react";
import { useRouter } from "next/navigation";
import { WarningKeywordManager } from "@/features/feature3/admin/WarningKeywordManager";

export default function F3WarningsPage() {
  const router = useRouter();
  return (
    <div className="min-h-screen bg-white">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-[#0f1117]/80 backdrop-blur-xl border-b border-white/5">
        <div className="max-w-[1280px] mx-auto px-8 h-[64px] flex items-center">
          <button
            onClick={() => router.push("/dashboard")}
            className="flex items-center gap-2 text-white/50 hover:text-white transition-colors"
          >
            <ArrowLeft size={16} />
            <span className="text-[13px]">대시보드</span>
          </button>
          <div className="w-px h-5 bg-white/10 mx-4" />
          <h1 className="text-[15px] font-bold text-white">
            수입필요서류 안내 · 경고 키워드
          </h1>
        </div>
      </nav>
      <div className="pt-[96px] pb-20 px-8">
        <WarningKeywordManager />
      </div>
    </div>
  );
}
