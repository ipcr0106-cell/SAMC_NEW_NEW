"use client";

import { useEffect, useState } from "react";
import { RotateCcw, AlertCircle, Check, X } from "lucide-react";
import { fetchHistory, rollbackUpdate, type HistoryItem } from "./api";
import { ConfirmModal } from "./ConfirmModal";

export function HistoryList() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [rollingBack, setRollingBack] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 롤백 확인 모달 상태
  const [pendingRollback, setPendingRollback] = useState<HistoryItem | null>(null);
  // cascade 필요 상태 (이후 버전이 있는 경우 서버가 needs_cascade 응답)
  const [cascadeInfo, setCascadeInfo] = useState<{
    item: HistoryItem;
    laterVersions: number[];
  } | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      setItems(await fetchHistory(20));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const executeRollback = async (version: number, cascade: boolean) => {
    setRollingBack(version);
    try {
      const res = await rollbackUpdate(version, cascade);
      if (res.status === "needs_cascade") {
        // 사용자에게 cascade 필요 안내
        const item = items.find((x) => x.version === version);
        if (item) {
          setCascadeInfo({
            item,
            laterVersions: (res.later_versions as number[]) || [],
          });
        }
        return;
      }
      if (res.warning) {
        // Pinecone 경고 등
        alert(res.warning);
      }
      await load();
      setPendingRollback(null);
      setCascadeInfo(null);
    } catch (e) {
      alert("롤백 실패: " + (e as Error).message);
    } finally {
      setRollingBack(null);
    }
  };

  const renderItem = (item: HistoryItem) => (
    <div
      key={item.version}
      className={`border rounded-lg p-3 flex items-center justify-between gap-4 ${
        item.is_rolled_back
          ? "border-slate-200 bg-slate-50 opacity-70"
          : "border-slate-200 bg-white"
      }`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[13px] font-mono text-slate-500">v{item.version}</span>
          <span className="text-[14px] font-semibold text-slate-900">{item.law_name}</span>
          <span className="text-[12px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
            {item.feature_label} DB
          </span>
          {item.is_rolled_back && (
            <span className="text-[12px] px-2 py-0.5 rounded-full bg-rose-100 text-rose-600 flex items-center gap-1">
              <X size={11} aria-hidden /> 롤백됨
            </span>
          )}
          {item.pinecone_touched && (
            <span className="text-[12px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">
              법령 본문 변경
            </span>
          )}
        </div>
        <div className="text-[12px] text-slate-500 mt-1 flex gap-4 flex-wrap">
          <span>{new Date(item.created_at).toLocaleString("ko-KR")}</span>
          {item.source_filename && (
            <span className="font-mono truncate max-w-[300px]">{item.source_filename}</span>
          )}
          <span>
            +{item.diff_summary.added} / ~{item.diff_summary.modified} / -
            {item.diff_summary.deleted}
          </span>
        </div>
      </div>

      <button
        onClick={() => setPendingRollback(item)}
        disabled={item.is_rolled_back || rollingBack === item.version}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-slate-300 bg-white text-slate-700 text-[13px] font-medium hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-slate-400"
      >
        {rollingBack === item.version ? (
          <>되돌리는 중...</>
        ) : item.is_rolled_back ? (
          <>
            <Check size={13} aria-hidden /> 롤백 완료
          </>
        ) : (
          <>
            <RotateCcw size={13} aria-hidden /> 롤백
          </>
        )}
      </button>
    </div>
  );

  if (loading) return <div className="text-slate-500 text-[14px]">불러오는 중...</div>;
  if (error)
    return (
      <div className="text-rose-600 text-[14px] flex items-center gap-2">
        <AlertCircle size={14} aria-hidden /> {error}
      </div>
    );
  if (items.length === 0)
    return (
      <div className="text-slate-400 text-[14px] text-center py-6 border border-dashed border-slate-200 rounded-lg">
        아직 업데이트 이력이 없습니다.
      </div>
    );

  return (
    <>
      <div className="space-y-2">{items.map(renderItem)}</div>

      {/* 기본 롤백 확인 모달 */}
      <ConfirmModal
        open={!!pendingRollback && !cascadeInfo}
        title="이 버전으로 되돌리기"
        subtitle={pendingRollback ? `v${pendingRollback.version} — ${pendingRollback.law_name}` : ""}
        featureLabel={pendingRollback?.feature_label || "수입필요서류 안내"}
        bodyText={
          pendingRollback && (
            <>
              <p>
                버전 <b>v{pendingRollback.version}</b> ({pendingRollback.law_name}) 시점으로
                &apos;{pendingRollback.feature_label}&apos; 자료를 되돌립니다.
              </p>
              <p className="text-slate-600">
                현재 상태는 자동으로 새 버전으로 백업되므로, 다시 앞으로도 복원할 수 있습니다.
              </p>
              {pendingRollback.pinecone_touched && (
                <p className="text-amber-700 bg-amber-50 rounded p-2 text-[13px]">
                  ⚠️ 이 업데이트는 법령 본문 검색 인덱스(Pinecone) 도 변경했습니다. 롤백은
                  자료만 복원하며, 검색 인덱스는 이전 버전 법령 파일을 다시 업로드해야 합니다.
                </p>
              )}
            </>
          )
        }
        cancelLabel="취소"
        confirmLabel="되돌리기"
        busyLabel="되돌리는 중..."
        applying={rollingBack === pendingRollback?.version}
        onCancel={() => setPendingRollback(null)}
        onConfirm={() => pendingRollback && executeRollback(pendingRollback.version, false)}
      />

      {/* cascade 필요 모달 */}
      <ConfirmModal
        open={!!cascadeInfo}
        title="이후 업데이트도 함께 취소할까요?"
        subtitle="중간 버전으로 되돌리면 이후 변경사항이 누적된 상태가 됩니다"
        featureLabel={cascadeInfo?.item.feature_label || "수입필요서류 안내"}
        bodyText={
          cascadeInfo && (
            <>
              <p>
                v{cascadeInfo.item.version} 이후로{" "}
                <b>{cascadeInfo.laterVersions.length}건</b>의 업데이트가 더 있습니다:
              </p>
              <p className="font-mono text-[12px] text-slate-600 bg-slate-100 rounded p-2">
                {cascadeInfo.laterVersions.map((v) => `v${v}`).join(", ")}
              </p>
              <p className="text-slate-700">
                <b>함께 취소하면</b> v{cascadeInfo.item.version} 시점의 깨끗한 상태로 돌아갑니다.{" "}
                <b>v{cascadeInfo.item.version} 만 취소</b>하면 이후 변경사항은 유지되지만
                혼란을 초래할 수 있습니다.
              </p>
            </>
          )
        }
        cancelLabel="취소"
        confirmLabel={cascadeInfo ? `이후 ${cascadeInfo.laterVersions.length}건도 함께 취소` : "함께 취소"}
        busyLabel="처리 중..."
        applying={!!cascadeInfo && rollingBack === cascadeInfo.item.version}
        onCancel={() => {
          setCascadeInfo(null);
          setPendingRollback(null);
        }}
        onConfirm={() => cascadeInfo && executeRollback(cascadeInfo.item.version, true)}
      />
    </>
  );
}
