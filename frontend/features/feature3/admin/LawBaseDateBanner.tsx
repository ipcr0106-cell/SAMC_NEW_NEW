"use client";

import { useEffect, useState } from "react";
import { Calendar, AlertTriangle } from "lucide-react";
import { fetchLastUpdate, type LastUpdateInfo } from "./api";

interface Props {
  compact?: boolean;  // 작은 배너 (서비스 페이지용)
}

export function LawBaseDateBanner({ compact = false }: Props) {
  const [info, setInfo] = useState<LastUpdateInfo | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    fetchLastUpdate()
      .then(setInfo)
      .catch(() => {});
  }, []);

  // API 실패 or 이력 없음 → 배너 숨김 (조용히 실패, 본 기능 방해 X)
  if (!info || info.error || !info.overall_last_at) return null;

  const lastAt = new Date(info.overall_last_at);
  const now = new Date();
  const daysAgo = Math.floor((now.getTime() - lastAt.getTime()) / (1000 * 60 * 60 * 24));

  const isStale = daysAgo > 180;  // 6개월 이상 — 경고
  const isWarning = daysAgo > 90 && daysAgo <= 180;  // 3-6개월 — 주의

  const colorClass = isStale
    ? "bg-rose-50 border-rose-200 text-rose-800"
    : isWarning
    ? "bg-amber-50 border-amber-200 text-amber-800"
    : "bg-slate-50 border-slate-200 text-slate-700";

  const dateStr = lastAt.toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const relativeStr =
    daysAgo === 0
      ? "오늘"
      : daysAgo === 1
      ? "어제"
      : daysAgo < 30
      ? `${daysAgo}일 전`
      : daysAgo < 365
      ? `${Math.floor(daysAgo / 30)}개월 전`
      : `${Math.floor(daysAgo / 365)}년 전`;

  const perLawList = Object.entries(info.per_law).sort((a, b) =>
    b[1].localeCompare(a[1]),
  );

  if (compact) {
    return (
      <div className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-[12px] ${colorClass} border`}>
        <Calendar size={13} aria-hidden />
        <span>
          법령 기준: <b>{dateStr}</b> ({relativeStr})
        </span>
        {isStale && <AlertTriangle size={13} aria-hidden />}
      </div>
    );
  }

  return (
    <div className={`rounded-lg border px-4 py-3 mb-4 ${colorClass}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          {isStale ? (
            <AlertTriangle size={18} className="flex-shrink-0" aria-hidden />
          ) : (
            <Calendar size={18} className="flex-shrink-0" aria-hidden />
          )}
          <div className="text-[13.5px]">
            <div>
              법령 기준일: <b>{dateStr}</b>{" "}
              <span className="text-[12px] opacity-75">({relativeStr})</span>
            </div>
            {isStale && (
              <div className="text-[12px] mt-0.5 opacity-90">
                ⚠️ 마지막 업데이트 후 6개월 이상 경과. 법령 최신본 확인이 필요합니다.
              </div>
            )}
            {isWarning && (
              <div className="text-[12px] mt-0.5 opacity-90">
                법령이 개정됐을 수 있으니 최근 공지를 확인해보세요.
              </div>
            )}
          </div>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-[12px] underline opacity-70 hover:opacity-100 flex-shrink-0"
        >
          {expanded ? "접기" : "법령별 상세"}
        </button>
      </div>

      {expanded && (
        <div className="mt-3 pt-3 border-t border-current/10 text-[12.5px]">
          <div className="font-semibold mb-1.5 opacity-80">법령별 마지막 업데이트</div>
          <div className="space-y-1">
            {perLawList.map(([law, ts]) => {
              const t = new Date(ts);
              return (
                <div key={law} className="flex justify-between font-mono">
                  <span className="truncate pr-4">{law}</span>
                  <span className="text-[11.5px] opacity-80 flex-shrink-0">
                    {t.toLocaleDateString("ko-KR")}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
