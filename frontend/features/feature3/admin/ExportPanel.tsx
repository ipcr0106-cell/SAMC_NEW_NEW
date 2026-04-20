"use client";

import { useState } from "react";
import { Download, Loader2, CheckCircle2, AlertCircle, Shield } from "lucide-react";

function getAdminHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("f3_admin_token") || "";
  const user = localStorage.getItem("f3_admin_user") || "";
  const h: Record<string, string> = {};
  if (token) h["X-Admin-Token"] = token;
  if (user) h["X-Admin-User"] = user;
  return h;
}

export function ExportPanel() {
  const [downloading, setDownloading] = useState(false);
  const [lastDownload, setLastDownload] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const API_BASE =
    process.env.NEXT_PUBLIC_API_URL?.replace(/\/api\/v1$/, "") ||
    "http://localhost:8000";

  const handleDownload = async () => {
    setDownloading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/f3/export`, {
        headers: getAdminHeaders(),
      });
      if (!res.ok) {
        const txt = await res.text().catch(() => "다운로드 실패");
        throw new Error(txt.slice(0, 200));
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;

      // Content-Disposition 에서 파일명 파싱
      const cd = res.headers.get("Content-Disposition") || "";
      const m = cd.match(/filename="([^"]+)"/);
      a.download = m ? m[1] : `f3_export_${Date.now()}.zip`;

      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);

      setLastDownload(new Date().toLocaleString("ko-KR"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="max-w-[800px] mx-auto">
      <div className="mb-6">
        <h2 className="text-[22px] font-extrabold text-slate-900">
          전체 자료 내려받기
        </h2>
        <p className="text-[14px] text-slate-500 mt-1">
          &apos;수입필요서류 안내&apos; 의 모든 자료를 Excel (10개 시트) 로 내려받습니다.
          시스템 이관·백업·감사 자료 대응용입니다.
        </p>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-5 mb-5">
        <div className="flex items-start gap-3 mb-4">
          <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center flex-shrink-0">
            <Download size={20} className="text-slate-700" />
          </div>
          <div>
            <div className="text-[16px] font-bold text-slate-900">
              ZIP 다운로드 (약 수십 KB~수 MB)
            </div>
            <div className="text-[13px] text-slate-500 mt-0.5">
              포함: f3_tables.xlsx + manifest.json + README.txt
            </div>
          </div>
        </div>

        <ul className="text-[13px] text-slate-700 space-y-1 mb-4 pl-4 list-disc">
          <li>서류 규칙 52건 (f3_required_documents)</li>
          <li>국가 그룹 (BSE/ASF/EU/동등성인정 등)</li>
          <li>원재료 동의어 매핑</li>
          <li>식품유형 축산·반추·돼지 플래그</li>
          <li>식물성 원료 패턴</li>
          <li>경고 키워드 규칙</li>
          <li>법령 본문 인용 (citations)</li>
        </ul>

        <button
          onClick={handleDownload}
          disabled={downloading}
          className="w-full h-12 rounded-lg bg-slate-900 text-white font-semibold hover:bg-slate-800 disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {downloading ? (
            <>
              <Loader2 size={16} className="animate-spin" /> 생성 중...
            </>
          ) : (
            <>
              <Download size={16} /> ZIP 다운로드
            </>
          )}
        </button>

        {lastDownload && !downloading && (
          <div className="mt-3 text-[12px] text-emerald-700 flex items-center gap-1.5">
            <CheckCircle2 size={13} /> 마지막 다운로드: {lastDownload}
          </div>
        )}
        {error && (
          <div className="mt-3 text-[12.5px] text-rose-700 flex items-center gap-1.5">
            <AlertCircle size={13} /> {error}
          </div>
        )}
      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-[12.5px] text-amber-800 flex gap-2">
        <Shield size={16} className="flex-shrink-0 mt-0.5" />
        <div>
          <div className="font-semibold mb-1">보안 주의</div>
          <ul className="space-y-0.5 list-disc list-inside">
            <li>다운로드 기록이 감사 로그에 남습니다 (사용자·시각).</li>
            <li>
              내려받은 파일은 수입식품 심사 자료로, 외부 유출 금지. 보관·폐기
              규정 준수 필요.
            </li>
            <li>파일명은 타임스탬프 포함 — 버전 관리 자동.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
