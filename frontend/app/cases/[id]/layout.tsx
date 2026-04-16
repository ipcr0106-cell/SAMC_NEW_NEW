"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { seedDummyData, clearDummyData } from "@/lib/api";
import {
  Shield,
  LogOut,
  ChevronLeft,
  User as UserIcon,
  Database,
  Trash2,
} from "lucide-react";
import type { User } from "@supabase/supabase-js";

export default function CaseLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const params = useParams();
  const caseId = params?.id as string;
  const [user, setUser] = useState<User | null>(null);
  const [seeding, setSeeding] = useState(false);
  const [seedStatus, setSeedStatus] = useState<string | null>(null);

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
    };
    getUser();
  }, [router]);

  const handleLogout = async () => {
    await supabase.auth.signOut();
    router.replace("/auth/login");
  };

  const handleSeedDummy = async () => {
    if (seeding) return;
    setSeeding(true);
    setSeedStatus(null);
    try {
      await seedDummyData(caseId);
      setSeedStatus("F0~F4 더미 데이터가 삽입되었습니다. 페이지를 새로고침하세요.");
    } catch (e) {
      setSeedStatus(`실패: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSeeding(false);
    }
  };

  const handleClearDummy = async () => {
    if (seeding) return;
    if (!confirm("더미 데이터를 삭제하시겠습니까?")) return;
    setSeeding(true);
    setSeedStatus(null);
    try {
      await clearDummyData(caseId);
      setSeedStatus("더미 데이터가 삭제되었습니다.");
    } catch (e) {
      setSeedStatus(`삭제 실패: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSeeding(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Top bar */}
      <header className="bg-white border-b border-slate-200/60 sticky top-0 z-50">
        <div className="max-w-[1440px] mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push("/dashboard")}
              className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-900 transition-colors"
            >
              <ChevronLeft size={16} />
              <span className="font-medium">대시보드</span>
            </button>
            <div className="w-px h-5 bg-slate-200" />
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 bg-blue-600 rounded-lg flex items-center justify-center">
                <Shield size={13} className="text-white" />
              </div>
              <span className="text-sm font-semibold text-slate-800">
                검역 건 {caseId}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* 더미 데이터 시드 버튼 */}
            <div className="flex items-center gap-1.5">
              <button
                onClick={handleSeedDummy}
                disabled={seeding}
                className="flex items-center gap-1.5 text-[11px] font-medium text-amber-700 bg-amber-50 hover:bg-amber-100 border border-amber-200 px-3 py-1.5 rounded-lg transition-all disabled:opacity-50"
                title="F0~F4 더미 데이터 삽입 (테스트용)"
              >
                <Database size={12} />
                {seeding ? "처리중..." : "더미 데이터"}
              </button>
              <button
                onClick={handleClearDummy}
                disabled={seeding}
                className="flex items-center gap-1 text-[11px] font-medium text-red-600 hover:bg-red-50 border border-red-200 px-2 py-1.5 rounded-lg transition-all disabled:opacity-50"
                title="더미 데이터 삭제"
              >
                <Trash2 size={11} />
              </button>
            </div>

            <div className="w-px h-5 bg-slate-200" />

            {user && (
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-500 to-violet-500 flex items-center justify-center">
                  <UserIcon size={12} className="text-white" />
                </div>
                <span className="text-xs text-slate-500">{user.email?.split("@")[0]}</span>
              </div>
            )}
            <button
              onClick={handleLogout}
              className="flex items-center gap-1 text-xs text-slate-400 hover:text-red-500 transition-colors px-2 py-1 rounded-lg hover:bg-red-50"
            >
              <LogOut size={13} />
            </button>
          </div>
        </div>

        {/* 시드 상태 메시지 */}
        {seedStatus && (
          <div className="max-w-[1440px] mx-auto px-6 pb-2">
            <div className={`text-xs px-3 py-2 rounded-lg ${
              seedStatus.startsWith("실패") || seedStatus.startsWith("삭제 실패")
                ? "bg-red-50 text-red-600"
                : "bg-emerald-50 text-emerald-700"
            }`}>
              {seedStatus}
            </div>
          </div>
        )}
      </header>

      {/* Page content */}
      {children}
    </div>
  );
}
