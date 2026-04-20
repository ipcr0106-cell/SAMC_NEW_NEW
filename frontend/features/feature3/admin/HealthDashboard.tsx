"use client";

import { useEffect, useState } from "react";
import {
  CheckCircle2, AlertTriangle, XCircle, HelpCircle, RefreshCw, Loader2,
} from "lucide-react";
import { fetchHealth, type HealthCheck, type HealthResponse } from "./api";

function StatusIcon({ status }: { status: HealthCheck["status"] }) {
  const props = { size: 20, "aria-hidden": true as const };
  switch (status) {
    case "ok":
      return <CheckCircle2 {...props} className="text-emerald-600" />;
    case "warning":
      return <AlertTriangle {...props} className="text-amber-600" />;
    case "error":
      return <XCircle {...props} className="text-rose-600" />;
    default:
      return <HelpCircle {...props} className="text-slate-400" />;
  }
}

function statusText(status: HealthCheck["status"]): string {
  switch (status) {
    case "ok":
      return "정상";
    case "warning":
      return "주의";
    case "error":
      return "오류";
    default:
      return "확인 불가";
  }
}

function statusColor(status: HealthCheck["status"]): string {
  switch (status) {
    case "ok":
      return "bg-emerald-50 border-emerald-200";
    case "warning":
      return "bg-amber-50 border-amber-200";
    case "error":
      return "bg-rose-50 border-rose-200";
    default:
      return "bg-slate-50 border-slate-200";
  }
}

export function HealthDashboard() {
  const [data, setData] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchHealth());
      setRefreshedAt(new Date());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // 60초마다 자동 새로고침
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading && !data) {
    return (
      <div className="max-w-[900px] mx-auto">
        <div className="flex items-center gap-2 text-slate-500">
          <Loader2 size={16} className="animate-spin" /> 건강 상태 확인 중...
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="max-w-[900px] mx-auto">
        <div className="bg-rose-50 border border-rose-200 rounded-lg p-4 text-rose-800">
          <div className="font-semibold mb-1">⚠️ 시스템 연결 실패</div>
          <div className="text-[13px]">{error}</div>
          <button
            onClick={load}
            className="mt-3 px-3 py-1.5 rounded bg-rose-600 text-white text-[13px] font-semibold"
          >
            다시 시도
          </button>
        </div>
      </div>
    );
  }

  const overall = data?.overall_status ?? "unknown";
  const overallColor =
    overall === "ok"
      ? "text-emerald-700"
      : overall === "warning"
      ? "text-amber-700"
      : "text-rose-700";
  const overallText =
    overall === "ok"
      ? "모든 시스템 정상"
      : overall === "warning"
      ? "일부 기능 주의 필요"
      : "오류 감지됨";

  const checks = data?.checks ?? {};

  return (
    <div className="max-w-[900px] mx-auto">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-[22px] font-extrabold text-slate-900">
            시스템 건강 상태
          </h2>
          <p className={`text-[14px] font-semibold mt-1 ${overallColor}`}>
            {overallText}
          </p>
          {refreshedAt && (
            <p className="text-[11.5px] text-slate-400 mt-1">
              마지막 확인: {refreshedAt.toLocaleTimeString("ko-KR")} · 60초마다 자동 갱신
            </p>
          )}
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-2 rounded-md border border-slate-300 text-slate-700 text-[13px] font-medium hover:bg-slate-50 disabled:opacity-50"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} aria-hidden />
          새로고침
        </button>
      </div>

      <div className="space-y-2">
        {Object.entries(checks).map(([key, c]) => (
          <div
            key={key}
            className={`border rounded-lg p-4 flex items-start gap-3 ${statusColor(c.status)}`}
          >
            <StatusIcon status={c.status} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[15px] font-bold text-slate-900">
                  {c.label}
                </span>
                <span className="text-[11.5px] font-semibold px-2 py-0.5 rounded-full bg-white/60 text-slate-700">
                  {statusText(c.status)}
                </span>
                {c.latency_ms !== undefined && (
                  <span className="text-[11px] text-slate-500 font-mono">
                    {c.latency_ms}ms
                  </span>
                )}
              </div>
              <div className="text-[13px] text-slate-700 mt-1">{c.detail}</div>
            </div>
          </div>
        ))}
      </div>

      {/* 안내 */}
      <div className="mt-6 p-4 bg-slate-50 border border-slate-200 rounded-lg text-[12.5px] text-slate-600">
        <div className="font-semibold text-slate-800 mb-2">💡 상태별 의미</div>
        <ul className="space-y-1 list-disc list-inside">
          <li>
            <b className="text-emerald-700">정상</b> — 해당 기능이 완전히 작동 중
          </li>
          <li>
            <b className="text-amber-700">주의</b> — 기능이 제한되거나 설정 필요. 핵심 판정은 여전히 작동.
          </li>
          <li>
            <b className="text-rose-700">오류</b> — 기능 사용 불가. 시스템 담당자 문의 필요.
          </li>
        </ul>
      </div>
    </div>
  );
}
