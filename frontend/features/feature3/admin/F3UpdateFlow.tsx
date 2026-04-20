"use client";

import { useCallback, useState } from "react";
import { Upload, FileText, X, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { previewUpdate, applyUpdate, type PreviewResponse, type TableDiff } from "./api";
import { DiffPreviewTable } from "./DiffPreviewTable";
import { ConfirmModal } from "./ConfirmModal";
import { HistoryList } from "./HistoryList";
import { LawBaseDateBanner } from "./LawBaseDateBanner";

// 간단 UUID v4 생성 (idempotency key 용, crypto.randomUUID 폴백)
function genIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  // 폴백: timestamp + random
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}-${Math.random()
    .toString(36)
    .slice(2, 10)}`;
}

type Stage =
  | "idle"
  | "uploading"
  | "previewing"
  | "preview_ready"
  | "confirming"
  | "applying"
  | "done"
  | "error";

const STAGE_LABELS: Record<Stage, string> = {
  idle: "",
  uploading: "파일 업로드 중",
  previewing: "파싱 중 — 기존 자료와 비교하고 있습니다",
  preview_ready: "미리보기 준비 완료",
  confirming: "최종 확인",
  applying: "백업 + 자료 교체 중",
  done: "반영 완료",
  error: "오류 발생",
};

const F3_LAWS = [
  { key: "수입신고 구비서류 목록", desc: "식약처 Excel (제출 19 + 보관 14)", ext: ".xlsx" },
  { key: "수입식품안전관리 특별법 시행규칙", desc: "시행규칙 제27조·별표9·별표10", ext: ".pdf" },
  { key: "OEM 수입식품 관리 안내서", desc: "OEM 가이드라인", ext: ".pdf" },
  { key: "동등성인정 협정문", desc: "한·미/EU/캐 협정문", ext: ".pdf" },
  { key: "식품공전", desc: "별표1 원료목록 + 제5장 식품유형", ext: ".hwpx" },
  { key: "식품첨가물공전", desc: "착향료 목록", ext: ".hwpx" },
];

export function F3UpdateFlow() {
  const [lawName, setLawName] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [progress, setProgress] = useState(0);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);
  // 테이블별 사용자 편집 반영본
  const [editedByTable, setEditedByTable] = useState<
    Record<string, Record<string, unknown>[]>
  >({});
  const [applyResult, setApplyResult] = useState<{
    version: number;
    rows_inserted_by_table: Record<string, number>;
    duplicate?: boolean;
  } | null>(null);
  // 현재 preview 에 대한 idempotency key — preview 한 번당 1개 생성, apply 반복 클릭 방지
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null);

  const selectedLaw = F3_LAWS.find((l) => l.key === lawName);

  const handleFileChange = (f: File | null) => {
    setFile(f);
    setError(null);
  };

  const handlePreview = async () => {
    if (!file || !lawName) return;
    setStage("uploading");
    setProgress(10);
    setError(null);
    setPreview(null);
    setEditedByTable({});
    setApplyResult(null);

    try {
      setStage("previewing");
      setProgress(40);
      const res = await previewUpdate(file, lawName);
      setProgress(100);
      setPreview(res);

      // 편집본 초기화 — 파싱된 new_rows 를 그대로 반영 (사용자가 편집하면 덮어쓰임)
      const init: Record<string, Record<string, unknown>[]> = {};
      for (const [tableName, t] of Object.entries(res.tables)) {
        init[tableName] = t.new_rows;
      }
      setEditedByTable(init);

      // 이 preview 세션에 대한 idempotency key 생성
      setIdempotencyKey(genIdempotencyKey());

      setStage("preview_ready");
    } catch (e) {
      setError((e as Error).message);
      setStage("error");
    }
  };

  // DiffPreviewTable → editedByTable 반영 콜백 (useCallback 로 참조 안정화)
  const handleEditedRowsChange = useCallback(
    (tableName: string, rows: Record<string, unknown>[]) => {
      setEditedByTable((prev) => ({ ...prev, [tableName]: rows }));
    },
    [],
  );

  const handleApplyClick = () => {
    setShowConfirm(true);
  };

  const handleConfirmApply = async () => {
    if (!preview) return;
    setStage("applying");
    setProgress(30);

    try {
      const tables: Record<
        string,
        {
          new_rows: Record<string, unknown>[];
          pk_column: string;
          scope_filter?: Record<string, unknown> | null;
        }
      > = {};
      for (const [tableName, t] of Object.entries(preview.tables)) {
        tables[tableName] = {
          new_rows: editedByTable[tableName] ?? t.new_rows,
          pk_column: t.pk_column,
          scope_filter: t.scope_filter ?? null,
        };
      }

      setProgress(60);
      const res = await applyUpdate(
        {
          law_name: preview.law_name,
          source_filename: preview.source_filename,
          tables,
          pinecone_chunks: preview.pinecone_chunks,
          pinecone_touched: preview.pinecone_touched,
        },
        idempotencyKey ?? undefined,
      );
      setProgress(100);

      // 중복 요청 감지 (24시간 내 동일 idempotency key)
      if ((res as unknown as { status: string }).status === "duplicate_request") {
        setApplyResult({
          version: res.version,
          rows_inserted_by_table: {} as Record<string, number>,
          duplicate: true,
        });
        setShowConfirm(false);
        setStage("done");
        return;
      }

      // Pinecone 결과 경고 처리 (alert 유지 — 중요 경고라 주의 필요)
      if (res.pinecone?.error) {
        alert(
          "자료는 반영됐지만 검색 인덱스(Pinecone) 재임베딩이 실패했습니다:\n" +
            (res.pinecone.message || res.pinecone.error),
        );
      }

      setApplyResult({
        version: res.version,
        rows_inserted_by_table: res.rows_inserted_by_table ?? {},
      });
      setShowConfirm(false);
      setStage("done");
    } catch (e) {
      setError((e as Error).message);
      setShowConfirm(false);
      setStage("error");
    }
  };

  const handleReset = () => {
    setFile(null);
    setPreview(null);
    setEditedByTable({});
    setApplyResult(null);
    setError(null);
    setProgress(0);
    setIdempotencyKey(null);
    setStage("idle");
  };

  // 전체 diff 합계 (경고 모달에 표시)
  const combinedSummary = preview
    ? Object.values(preview.tables).reduce(
        (acc, t) => ({
          added: acc.added + t.diff.added,
          modified: acc.modified + t.diff.modified,
          deleted: acc.deleted + t.diff.deleted,
        }),
        { added: 0, modified: 0, deleted: 0 },
      )
    : { added: 0, modified: 0, deleted: 0 };

  return (
    <div className="max-w-[1100px] mx-auto">
      {/* 법령 기준일 — 전체 배너 */}
      <LawBaseDateBanner />

      {/* 설명 */}
      <div className="mb-6">
        <h2 className="text-[22px] font-extrabold text-slate-900">
          수입필요서류 안내 — 법령 업데이트
        </h2>
        <p className="text-[14px] text-slate-500 mt-1">
          법령 파일을 업로드하시면 내용을 자동으로 분석해 기존 자료와 비교해서 보여드립니다.
          확인 후 반영하시면 되고, 문제가 생기면 언제든 이전 상태로 되돌릴 수 있어요.
        </p>
      </div>

      {/* 1. 법령 선택 + 파일 업로드 */}
      {stage === "idle" && (
        <div className="border border-slate-200 rounded-xl p-6 bg-white">
          <div className="mb-4">
            <label className="text-[13px] font-semibold text-slate-700 block mb-2">
              업데이트할 법령
            </label>
            <select
              value={lawName}
              onChange={(e) => setLawName(e.target.value)}
              className="w-full h-11 px-3 rounded-lg border border-slate-300 text-[14px] bg-white focus:outline-none focus:ring-2 focus:ring-slate-400"
            >
              <option value="">-- 법령 선택 --</option>
              {F3_LAWS.map((l) => (
                <option key={l.key} value={l.key}>
                  {l.key} ({l.ext})
                </option>
              ))}
            </select>
            {selectedLaw && (
              <p className="text-[12px] text-slate-500 mt-1.5">
                {selectedLaw.desc}
              </p>
            )}
          </div>

          <div className="mb-4">
            <label className="text-[13px] font-semibold text-slate-700 block mb-2">
              법령 파일
            </label>
            <div className="border-2 border-dashed border-slate-300 rounded-lg p-6 text-center">
              {file ? (
                <div className="flex items-center justify-center gap-2">
                  <FileText size={18} className="text-slate-600" />
                  <span className="text-[14px] text-slate-800 font-medium">
                    {file.name}
                  </span>
                  <button
                    onClick={() => setFile(null)}
                    className="text-slate-400 hover:text-slate-600"
                  >
                    <X size={16} />
                  </button>
                </div>
              ) : (
                <>
                  <Upload size={28} className="mx-auto text-slate-400 mb-2" />
                  <input
                    type="file"
                    accept=".pdf,.hwpx,.xlsx"
                    onChange={(e) => handleFileChange(e.target.files?.[0] || null)}
                    className="block mx-auto text-[13px]"
                  />
                  <p className="text-[12px] text-slate-400 mt-2">
                    PDF / HWPX / XLSX 지원
                  </p>
                </>
              )}
            </div>
          </div>

          <button
            onClick={handlePreview}
            disabled={!file || !lawName}
            className="w-full h-12 rounded-lg bg-slate-900 text-white font-semibold text-[14px] hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            미리보기
          </button>
        </div>
      )}

      {/* 2. 진행 중 표시 */}
      {(stage === "uploading" || stage === "previewing" || stage === "applying") && (
        <div className="border border-slate-200 rounded-xl p-6 bg-white">
          <div className="flex items-center gap-3 mb-4">
            <Loader2 className="w-5 h-5 text-slate-700 animate-spin" />
            <div>
              <div className="text-[15px] font-semibold text-slate-900">
                {STAGE_LABELS[stage]}
              </div>
              <div className="text-[12px] text-slate-500">
                잠시만 기다려 주세요...
              </div>
            </div>
          </div>
          <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-slate-900 transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {/* 3. 미리보기 표시 */}
      {stage === "preview_ready" && preview && (
        <div>
          <div className="border border-slate-200 rounded-xl p-5 bg-white mb-4">
            <div className="flex items-start justify-between mb-3">
              <div>
                <div className="text-[16px] font-bold text-slate-900">
                  미리보기 — {preview.law_name}
                </div>
                <div className="text-[12px] text-slate-500 font-mono mt-0.5">
                  {preview.source_filename}
                </div>
              </div>
              <div className="flex gap-4 text-[13px]">
                <span>
                  <b className="text-emerald-600">{combinedSummary.added}</b>
                  <span className="text-slate-500 ml-1">추가</span>
                </span>
                <span>
                  <b className="text-blue-600">{combinedSummary.modified}</b>
                  <span className="text-slate-500 ml-1">수정</span>
                </span>
                <span>
                  <b className="text-rose-600">{combinedSummary.deleted}</b>
                  <span className="text-slate-500 ml-1">삭제</span>
                </span>
              </div>
            </div>

            {preview.warnings.length > 0 && (
              <div className="mb-3 p-3 rounded-lg bg-amber-50 border border-amber-200">
                <div className="flex items-center gap-2 text-[13px] font-semibold text-amber-800 mb-1">
                  <AlertCircle size={14} /> 파서 경고
                </div>
                <ul className="text-[12.5px] text-amber-800 space-y-0.5 list-disc list-inside">
                  {preview.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            )}

            {Object.entries(preview.tables).map(([tableName, t]) => (
              <DiffTableSection
                key={tableName}
                tableName={tableName}
                tableDiff={t}
                onEditedRowsChange={(rows) => handleEditedRowsChange(tableName, rows)}
              />
            ))}
          </div>

          <div className="flex gap-3">
            <button
              onClick={handleReset}
              className="flex-1 h-11 rounded-lg border border-slate-300 bg-white text-slate-700 font-semibold hover:bg-slate-50"
            >
              취소
            </button>
            <button
              onClick={handleApplyClick}
              className="flex-1 h-11 rounded-lg bg-slate-900 text-white font-semibold hover:bg-slate-800"
            >
              반영하기
            </button>
          </div>
        </div>
      )}

      {/* 4. 완료 */}
      {stage === "done" && applyResult && (
        <div className="border border-emerald-200 rounded-xl p-6 bg-emerald-50">
          <div className="flex items-center gap-3 mb-3">
            <CheckCircle2 className="w-7 h-7 text-emerald-600" />
            <div>
              <div className="text-[17px] font-bold text-emerald-900">
                반영 완료
              </div>
              <div className="text-[13px] text-emerald-700">
                버전 v{applyResult.version} 으로 저장되었습니다. 필요 시
                아래 이력에서 언제든 롤백할 수 있습니다.
              </div>
            </div>
          </div>
          <div className="bg-white rounded-lg p-3 text-[13px] text-slate-700 mb-4">
            {Object.entries(applyResult.rows_inserted_by_table).map(([t, n]) => (
              <div key={t} className="flex justify-between py-0.5">
                <span className="font-mono text-slate-600">{t}</span>
                <span className="font-semibold">{n}건 저장</span>
              </div>
            ))}
          </div>
          <button
            onClick={handleReset}
            className="w-full h-11 rounded-lg bg-emerald-600 text-white font-semibold hover:bg-emerald-700"
          >
            다른 법령 업데이트하기
          </button>
        </div>
      )}

      {/* 5. 에러 */}
      {stage === "error" && error && (
        <div className="border border-rose-200 rounded-xl p-6 bg-rose-50">
          <div className="flex items-center gap-3 mb-2">
            <AlertCircle className="w-6 h-6 text-rose-600" />
            <div className="text-[16px] font-bold text-rose-900">처리 실패</div>
          </div>
          <div className="text-[13.5px] text-rose-800 whitespace-pre-wrap mb-4 bg-white rounded p-3">
            {error}
          </div>
          <button
            onClick={handleReset}
            className="w-full h-11 rounded-lg bg-rose-600 text-white font-semibold hover:bg-rose-700"
          >
            처음으로 돌아가기
          </button>
        </div>
      )}

      {/* 이력 섹션 */}
      <div className="mt-10">
        <h3 className="text-[16px] font-bold text-slate-900 mb-3">
          최근 업데이트 이력
        </h3>
        <HistoryList />
      </div>

      <ConfirmModal
        open={showConfirm}
        summary={combinedSummary}
        featureLabel={preview?.feature_label || "수입필요서류 안내"}
        onCancel={() => setShowConfirm(false)}
        onConfirm={handleConfirmApply}
        applying={stage === "applying"}
      />
    </div>
  );
}

// ── 테이블 하나당 섹션 래퍼 ────────────────

function DiffTableSection({
  tableName,
  tableDiff,
  onEditedRowsChange,
}: {
  tableName: string;
  tableDiff: TableDiff;
  onEditedRowsChange: (rows: Record<string, unknown>[]) => void;
}) {
  return (
    <div className="mt-4 pt-4 border-t border-slate-100 first:border-t-0 first:mt-0 first:pt-0">
      <DiffPreviewTable
        tableName={tableName}
        diff={tableDiff}
        onEditedRowsChange={onEditedRowsChange}
      />
    </div>
  );
}
