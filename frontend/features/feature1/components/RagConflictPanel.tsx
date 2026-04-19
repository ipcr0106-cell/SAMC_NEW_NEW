/**
 * F1 RAG — HITL 충돌 결정 패널.
 *
 * 상위에서 conflict_status ∈ ("conflict", "rag_supplemented") 일 때만 렌더.
 * 담당자는 3가지 경로 중 하나 선택 + 사유 기재 → onDecide 호출:
 *   1. DB 따르기  → verdict = dbVerdict
 *   2. RAG 따르기 → verdict = ragVerdictToKo(ragVerdict)
 *   3. 수동 판정  → verdict = manualVerdict (수입가능/수입불가)
 *
 * 백엔드 연결: 기존 updateImportCheckResult(PATCH) 재사용, 별도 신규 엔드포인트 없음.
 */

"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import type { Feature1Result } from "@/types/pipeline";
import type { ConflictStatus, RagVerdict } from "../types";
import { CONFLICT_STATUS_LABEL, RAG_VERDICT_LABEL } from "../types";

type DecisionSource = "db" | "rag" | "manual";

interface Props {
  conflictStatus: ConflictStatus;
  ragVerdict: RagVerdict | null;
  ragReasoning: string | null;
  dbVerdict: Feature1Result["verdict"];
  onDecide: (
    verdict: Feature1Result["verdict"],
    reason: string,
  ) => Promise<void>;
  isSaving: boolean;
}

// RAG 영문 verdict → 프론트 한글 verdict. 결정 불가면 null.
function ragVerdictToKo(
  v: RagVerdict | null,
): Feature1Result["verdict"] | null {
  if (v === "permitted" || v === "restricted") return "수입가능";
  if (v === "prohibited") return "수입불가";
  return null;
}

export default function RagConflictPanel({
  conflictStatus,
  ragVerdict,
  ragReasoning,
  dbVerdict,
  onDecide,
  isSaving,
}: Props) {
  const [source, setSource] = useState<DecisionSource | null>(null);
  const [manualVerdict, setManualVerdict] =
    useState<Feature1Result["verdict"]>("수입가능");
  const [reason, setReason] = useState("");

  const toneByStatus =
    conflictStatus === "conflict"
      ? "border-red-300 bg-red-50"
      : "border-amber-300 bg-amber-50";

  const ragKo = ragVerdictToKo(ragVerdict);

  const resolvedVerdict: Feature1Result["verdict"] | null =
    source === "db"
      ? dbVerdict
      : source === "rag"
        ? ragKo
        : source === "manual"
          ? manualVerdict
          : null;

  const canSubmit =
    resolvedVerdict !== null && reason.trim().length > 0 && !isSaving;

  return (
    <section
      data-testid="rag-conflict-panel"
      className={`rounded-lg border-2 ${toneByStatus} p-4`}
    >
      <div className="mb-3 flex items-center gap-2">
        <AlertTriangle className="h-5 w-5 text-red-600" />
        <h3 className="font-semibold text-gray-900">
          담당자 결정 필요 — {CONFLICT_STATUS_LABEL[conflictStatus]}
        </h3>
      </div>

      {/* DB vs RAG 비교 */}
      <div className="mb-3 grid grid-cols-2 gap-3">
        <div className="rounded border border-gray-200 bg-white p-3">
          <div className="text-[11px] font-medium text-gray-500">
            DB 판정 (exact-match)
          </div>
          <div className="mt-1 text-base font-semibold text-gray-900">
            {dbVerdict}
          </div>
        </div>
        <div className="rounded border border-gray-200 bg-white p-3">
          <div className="text-[11px] font-medium text-gray-500">
            RAG 판정 (법령 인용)
          </div>
          <div className="mt-1 text-base font-semibold text-gray-900">
            {ragVerdict ? RAG_VERDICT_LABEL[ragVerdict] : "—"}
            {ragKo && (
              <span className="ml-2 text-xs text-gray-500">→ {ragKo}</span>
            )}
          </div>
        </div>
      </div>

      {/* RAG 근거 */}
      {ragReasoning && (
        <div className="mb-3 rounded border border-gray-200 bg-white p-3 text-sm leading-relaxed text-gray-700">
          <div className="mb-1 text-[11px] font-medium text-gray-500">
            RAG 근거
          </div>
          {ragReasoning}
        </div>
      )}

      {/* 결정 버튼 3개 */}
      <div className="mb-3 flex flex-wrap gap-2">
        <DecisionButton
          label={`DB 따르기 (${dbVerdict})`}
          selected={source === "db"}
          onClick={() => setSource("db")}
        />
        <DecisionButton
          label={`RAG 따르기${ragKo ? ` (${ragKo})` : ""}`}
          selected={source === "rag"}
          onClick={() => setSource("rag")}
          disabled={ragKo === null}
        />
        <DecisionButton
          label="수동 판정"
          selected={source === "manual"}
          onClick={() => setSource("manual")}
        />
      </div>

      {/* 수동 판정 시 verdict 선택 */}
      {source === "manual" && (
        <div className="mb-3 flex gap-3">
          {(["수입가능", "수입불가"] as const).map((v) => (
            <label key={v} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="manual-verdict"
                checked={manualVerdict === v}
                onChange={() => setManualVerdict(v)}
                className="h-4 w-4 accent-blue-600"
              />
              {v}
            </label>
          ))}
        </div>
      )}

      {/* 사유 */}
      {source !== null && (
        <div className="mb-3">
          <div className="mb-1 text-xs font-medium text-gray-700">
            결정 사유 <span className="text-red-500">*</span>
            <span className="ml-2 text-gray-500">
              식약처 소명 자료에 포함됩니다.
            </span>
          </div>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            placeholder="결정 사유를 기재하세요. 예) 식약처 Q&A 게시판 근거, 유사 사례 참고 등."
            className="w-full rounded border border-gray-300 p-2 text-sm focus:border-blue-500 focus:outline-none"
          />
        </div>
      )}

      {/* 확정 버튼 */}
      {source !== null && (
        <div className="flex justify-end">
          <button
            type="button"
            disabled={!canSubmit}
            onClick={() => {
              if (!resolvedVerdict) return;
              void onDecide(resolvedVerdict, reason.trim());
            }}
            className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white transition-all hover:bg-blue-700 disabled:opacity-50"
          >
            <CheckCircle2 className="h-4 w-4" />
            {isSaving ? "저장 중..." : "결정 확정"}
          </button>
        </div>
      )}
    </section>
  );
}

function DecisionButton({
  label,
  selected,
  onClick,
  disabled = false,
}: {
  label: string;
  selected: boolean;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-lg border px-3 py-2 text-sm font-medium transition-all disabled:cursor-not-allowed disabled:opacity-40 ${
        selected
          ? "border-blue-600 bg-blue-600 text-white"
          : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
      }`}
    >
      {label}
    </button>
  );
}
