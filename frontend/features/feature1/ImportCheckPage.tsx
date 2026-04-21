/**
 * 기능1: 수입 가능 여부 판정 — 메인 페이지 컴포넌트
 *
 * 경로: /cases/{caseId}/feature1
 *
 * v1 (레거시) 섹션 구조:
 *   [헤더] → [ForbiddenAlert] → [AggregationSummary] →
 *   [IngredientMatchTable] → [StandardsSummary] →
 *   [LawRefCheckbox] → [VerdictPanel] → [ConfirmActions]
 *
 * v2 (Wave 4 P2) HITL 분기:
 *   [헤더+StatusBadge] →
 *   HITL-0: F0 completed/approved → F0ApprovalPanel
 *   F1 pending/running → 로딩 스피너
 *   HITL-1: needs_review → UnidentifiedIngredientReview + ConditionalResolutionPanel + EscalationAckList
 *   HITL-2: waiting_review → VerdictPanel(HITL-2 모드) + ConfirmActions
 *   confirmed/locked → readonly 배너
 */

"use client";

import { useCallback, useMemo, useState as useLocalState } from "react";
import { useImportCheck } from "./hooks/useImportCheck";
import Button from "@/components/ui/Button";
import ForbiddenAlert from "./components/ForbiddenAlert";
import AggregationSummary from "./components/AggregationSummary";
import IngredientMatchTable from "./components/IngredientMatchTable";
import StandardsSummary from "./components/StandardsSummary";
import LawRefCheckbox from "./components/LawRefCheckbox";
import VerdictPanel from "./components/VerdictPanel";
import ConfirmActions from "./components/ConfirmActions";
import LawCitationList from "./components/LawCitationList";
import StatusBadge from "./components/StatusBadge";
import { isConfirmedStatus } from "./types";

interface Props {
  caseId: string;
}

export default function ImportCheckPage({ caseId }: Props) {
  const {
    state,
    toggleLawRef,
    setUserVerdict,
    setEditReason,
    saveEdit,
    confirm,
    handleDownloadPdf,
    applyResponse,
  } = useImportCheck(caseId);

  const source = state.data?.final_result ?? state.data?.ai_result ?? null;
  const internal = source?._internal ?? null;
  const pipelineVersion = internal?.pipeline_version ?? "v1";
  const isV2 = pipelineVersion === "v2";
  const currentStatus = state.data?.status;

  // isConfirmed: 레거시(v1)에서는 "completed" 체크, v2에서는 확장 상태 포함
  const isConfirmed = isV2
    ? isConfirmedStatus(currentStatus)
    : currentStatus === "completed";

  // ── F1 재분석 ────────────────────────────────────────────────────────
  const [rerunning, setRerunning] = useLocalState(false);
  const [rerunError, setRerunError] = useLocalState<string | null>(null);

  const handleRerun = useCallback(async () => {
    setRerunning(true);
    setRerunError(null);
    try {
      const { runImportCheck } = await import("./api/importCheck");
      const result = await runImportCheck(caseId, { ingredients: [] });
      // 결과를 state에 직접 반영 (reload 대신)
      if (result) {
        applyResponse(result);
      }
    } catch (e: unknown) {
      const msg = (e as any)?.response?.data?.detail?.message ?? "재분석 실패. 잠시 후 다시 시도하세요.";
      setRerunError(msg);
    } finally {
      setRerunning(false);
    }
  }, [caseId, applyResponse]);


  // ─ 로딩 ────────────────────────────────────────
  if (state.fetchStatus === "loading" || state.fetchStatus === "idle") {
    return (
      <main className="mx-auto max-w-5xl space-y-4 p-6">
        <header className="pb-3" style={{ borderBottom: "1px solid var(--ds-color-border)" }}>
          <h1 className="text-xl font-semibold" style={{ color: "var(--ds-color-text-heading)" }}>기능1 — 수입 가능 여부 판정</h1>
          <div className="text-xs" style={{ color: "var(--ds-color-text-secondary)" }}>case: {caseId}</div>
        </header>
        <div className="flex justify-center py-12" style={{ color: "var(--ds-color-text-secondary)" }}>
          <span className="animate-pulse">기능1 결과를 불러오는 중...</span>
        </div>
      </main>
    );
  }

  // ─ 에러 / 미실행 → 실행 버튼 표시 ──────────────
  if (state.fetchStatus === "error" || !source) {
    return (
      <div className="mx-auto max-w-5xl p-6 space-y-4">
        {state.errorMessage && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
            {state.errorMessage}
          </div>
        )}
        <div className="rounded-lg border border-gray-200 bg-white p-6 text-center">
          <p className="text-sm text-gray-600 mb-4">기능1이 아직 실행되지 않았습니다.</p>
          <Button variant="primary" size="lg" onClick={() => {}}>기능1 실행</Button>
        </div>
      </div>
    );
  }

  // ─ 공통 헤더 ────────────────────────────────────────────────────────
  const PageHeader = (
    <header className="pb-3" style={{ borderBottom: "1px solid var(--ds-color-border)" }}>
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold" style={{ color: "var(--ds-color-text-heading)" }}>기능1 — 수입 가능 여부 판정</h1>
          <div className="mt-1 flex items-center gap-3 text-xs" style={{ color: "var(--ds-color-text-secondary)" }}>
            <span>case: {caseId}</span>
            <span>·</span>
            {currentStatus && (
              <StatusBadge status={currentStatus} />
            )}
            {state.data?.updated_at && (
              <>
                <span>·</span>
                <span>
                  갱신: {new Date(state.data.updated_at).toLocaleString("ko-KR")}
                </span>
              </>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleDownloadPdf}
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs font-medium bg-white border border-slate-200 text-slate-700 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700 transition-colors"
          >
            PDF
          </button>
          <button
            type="button"
            onClick={handleRerun}
            disabled={rerunning}
            className="inline-flex items-center gap-2 h-10 px-5 rounded-xl text-sm font-semibold text-white transition-all disabled:opacity-60"
            style={{ background: "var(--ds-color-primary, #2563eb)" }}
          >
            {rerunning ? "재분석 중..." : "F1 재분석"}
          </button>
        </div>
      </div>
    </header>
  );

  // ═══════════════════════════════════════════════════════════════════
  // v2 경로 — 상태 무관하게 결과 표시
  // ═══════════════════════════════════════════════════════════════════
  if (isV2) {
    return (
      <main className="mx-auto max-w-5xl space-y-4 p-6">
        {PageHeader}

        {/* 오류 메시지 */}
        {state.errorMessage && (
          <div className="rounded-lg bg-red-50 p-3 text-sm text-red-600">
            {state.errorMessage}
          </div>
        )}

        {/* 로딩 */}
        {(currentStatus === "pending" || currentStatus === "running") && (
          <div className="flex items-center justify-center gap-3 rounded-lg border border-gray-200 bg-gray-50 py-12">
            <span className="h-5 w-5 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600" />
            <span className="text-sm text-gray-600">F1 분석 실행 중...</span>
          </div>
        )}

        {/* 결과 — 상태 무관하게 항상 표시 */}
        {source && (
          <div className="space-y-4">
            {internal?.forbidden_hits && internal.forbidden_hits.length > 0 && (
              <ForbiddenAlert hits={internal.forbidden_hits} />
            )}

            {internal?.aggregation && (
              <AggregationSummary aggregation={internal.aggregation} />
            )}

            {internal?.aggregation && (
              <IngredientMatchTable results={internal.aggregation.results} />
            )}

            <StandardsSummary checks={source.standards_check} />

            {internal?.law_citations && internal.law_citations.length > 0 && (
              <LawCitationList citations={internal.law_citations} />
            )}

            <VerdictPanel
              aiVerdict={source.verdict}
              failReasons={[]}
              userVerdict={state.userVerdict ?? source.verdict}
              editReason={state.editReason}
              onChangeVerdict={setUserVerdict}
              onChangeReason={setEditReason}
              stepStatus={currentStatus}
            />
          </div>
        )}
      </main>
    );
  }

  // ═══════════════════════════════════════════════════════════════════
  // v1 레거시 경로 렌더
  // ═══════════════════════════════════════════════════════════════════
  return (
    <main className="mx-auto max-w-5xl space-y-4 p-6">
      {PageHeader}

      {internal?.forbidden_hits && internal.forbidden_hits.length > 0 && (
        <ForbiddenAlert hits={internal.forbidden_hits} />
      )}

      {internal?.aggregation && (
        <AggregationSummary aggregation={internal.aggregation} />
      )}
      {internal?.aggregation?.results && (
        <IngredientMatchTable results={internal.aggregation.results} />
      )}

      {source.standards_check && source.standards_check.length > 0 && (
        <StandardsSummary checks={source.standards_check} />
      )}

      {internal?.law_citations && internal.law_citations.length > 0 && (
        <LawCitationList citations={internal.law_citations} />
      )}

      <LawRefCheckbox
        lawRefs={internal?.law_refs ?? []}
        selected={state.selectedLawRefs}
        onToggle={toggleLawRef}
      />

      <VerdictPanel
        aiVerdict={source.verdict}
        failReasons={source.fail_reasons}
        userVerdict={state.userVerdict}
        editReason={state.editReason}
        onChangeVerdict={setUserVerdict}
        onChangeReason={setEditReason}
        stepStatus={isConfirmed ? "completed" : "waiting_review"}
      />

      <ConfirmActions
        canConfirm={true}
        isConfirmed={isConfirmed}
        isSaving={state.isSaving}
        isConfirming={state.isConfirming}
        onSave={saveEdit}
        onConfirm={confirm}
        onDownloadPdf={handleDownloadPdf}
      />
    </main>
  );
}
