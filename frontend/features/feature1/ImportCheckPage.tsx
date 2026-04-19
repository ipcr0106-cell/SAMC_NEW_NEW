/**
 * 기능1: 수입 가능 여부 판정 — 메인 페이지 컴포넌트
 *
 * 경로: /cases/{caseId}/feature1
 * 섹션 구조:
 *   [헤더] → [ForbiddenAlert] → [AggregationSummary] →
 *   [IngredientMatchTable] → [StandardsSummary] →
 *   [LawRefCheckbox] → [VerdictPanel] → [ConfirmActions]
 */

"use client";

import { useMemo, useState as useLocalState } from "react";
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
    submitHITLDecision,
  } = useImportCheck(caseId);

  const isConfirmed = state.data?.status === "completed";
  const source = state.data?.final_result ?? state.data?.ai_result ?? null;
  const internal = source?._internal ?? null;

  const canConfirm = useMemo(() => {
    if (!source) return false;
    // 담당자가 판정을 명시하고, 불일치 시 사유가 있을 때만 확정 가능
    if (state.userVerdict === null) return false;
    if (
      state.userVerdict !== source.verdict &&
      state.userVerdict !== "보류" &&
      state.editReason.trim().length === 0
    ) {
      return false;
    }
    return true;
  }, [source, state.userVerdict, state.editReason]);

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
      <RunPrompt
        caseId={caseId}
        errorMessage={state.errorMessage}
      />
    );
  }

  // ─ 정상 ────────────────────────────────────────
  return (
    <main className="mx-auto max-w-5xl space-y-4 p-6">
      <header className="pb-3" style={{ borderBottom: "1px solid var(--ds-color-border)" }}>
        <h1 className="text-xl font-semibold" style={{ color: "var(--ds-color-text-heading)" }}>기능1 — 수입 가능 여부 판정</h1>
        <div className="mt-1 flex items-center gap-3 text-xs" style={{ color: "var(--ds-color-text-secondary)" }}>
          <span>case: {caseId}</span>
          <span>·</span>
          <span>
            상태: <b>{state.data?.status}</b>
          </span>
          {state.data?.updated_at && (
            <>
              <span>·</span>
              <span>
                갱신: {new Date(state.data.updated_at).toLocaleString("ko-KR")}
              </span>
            </>
          )}
        </div>
      </header>

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

      {internal?.escalations && internal.escalations.length > 0 && (
        <section className="rounded-lg p-4 ds-alert-warning">
          <h3 className="mb-2 font-semibold">에스컬레이션 ({internal.escalations.length})</h3>
          <ul className="space-y-1 text-sm">
            {internal.escalations.map((e, i) => (
              <li key={i}>• {e.reason}</li>
            ))}
          </ul>
        </section>
      )}

      {/* Phase 4-B: 법령 인용 리스트 — rag_skipped 면 citations=[] 로 자동 생략 */}
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
      />

      <ConfirmActions
        isSaving={state.isSaving}
        isConfirming={state.isConfirming}
        isConfirmed={isConfirmed}
        canConfirm={canConfirm}
        onSave={saveEdit}
        onConfirm={confirm}
        onDownloadPdf={handleDownloadPdf}
      />
    </main>
  );
}


// ── 미실행 상태에서 실행 버튼을 보여주는 컴포넌트 ──

function RunPrompt({ caseId, errorMessage }: { caseId: string; errorMessage: string | null }) {
  const [running, setRunning] = useLocalState(false);
  const [runError, setRunError] = useLocalState<string | null>(null);

  const handleRun = async () => {
    setRunning(true);
    setRunError(null);
    try {
      const { runImportCheck } = await import("./api/importCheck");
      await runImportCheck(caseId, { ingredients: [] });
      window.location.reload();
    } catch (e: any) {
      setRunError(
        e?.response?.data?.detail?.message ||
        "실행 실패. 먼저 서류 업로드 및 파싱을 실행하세요."
      );
      setRunning(false);
    }
  };

  return (
    <main className="mx-auto max-w-5xl space-y-4 p-6">
      <header className="pb-3" style={{ borderBottom: "1px solid var(--ds-color-border)" }}>
        <h1 className="text-xl font-semibold" style={{ color: "var(--ds-color-text-heading)" }}>기능1 — 수입 가능 여부 판정</h1>
        <div className="text-xs" style={{ color: "var(--ds-color-text-secondary)" }}>case: {caseId}</div>
      </header>
      <section className="rounded-lg p-4 text-sm ds-alert-warning">
        {runError || errorMessage || "기능1이 아직 실행되지 않았습니다."}
      </section>
      <Button
        onClick={handleRun}
        disabled={running}
        variant="primary"
        size="md"
      >
        {running ? "분석 중..." : "AI 수입판정 실행"}
      </Button>
    </main>
  );
}
