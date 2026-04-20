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

import { useCallback, useEffect, useMemo, useState as useLocalState } from "react";
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
import F0ApprovalPanel from "./components/F0ApprovalPanel";
import UnidentifiedIngredientReview from "./components/UnidentifiedIngredientReview";
import ConditionalResolutionPanel from "./components/ConditionalResolutionPanel";
import EscalationAckList from "./components/EscalationAckList";
import FoodTypeSection from "./components/FoodTypeSection";
import FoodTypeEditDialog from "./components/FoodTypeEditDialog";
import type { IngredientDecision, FoodTypeHierarchy } from "@/types/pipeline";
import type { ConditionalResolution } from "./components/ConditionalResolutionPanel";
import type { EscalationItem } from "./components/EscalationAckList";
import { isConfirmedStatus } from "./types";
import { getFeature2 } from "@/lib/api";

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
    // Wave 4 P2: HITL API 함수들
    editF0,
    approveF0,
    submitHitl1,
    confirmHitl2Result,
    setHitl2FinalReason,
    setHitl2SignerId,
    toggleHitl2Citation,
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

  // ── F2 식품유형 분류 state (f1f2 병합) ───────────────────────────────
  const [foodTypeHierarchy, setFoodTypeHierarchy] = useLocalState<FoodTypeHierarchy | null>(null);
  const [showFoodTypeEdit, setShowFoodTypeEdit] = useLocalState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const row = await getFeature2(caseId) as {
          ai_result: FoodTypeHierarchy | null;
          final_result: FoodTypeHierarchy | null;
        };
        if (cancelled) return;
        const picked = row.final_result ?? row.ai_result;
        if (picked) setFoodTypeHierarchy(picked);
      } catch {
        // F2 미실행 상태 → null 유지 (오류 표시 없음)
      }
    })();
    return () => { cancelled = true; };
  }, [caseId]);

  // ── HITL-1 로컬 결정 상태 ──────────────────────────────────────────
  const [ingredientDecisions, setIngredientDecisions] = useLocalState<readonly IngredientDecision[]>([]);
  const [conditionalResolutions, setConditionalResolutions] = useLocalState<readonly ConditionalResolution[]>([]);
  const [escalationAcks, setEscalationAcks] = useLocalState<readonly string[]>([]);

  // ── HITL-2 확정 확인 모달 ──────────────────────────────────────────
  const [showHitl2Modal, setShowHitl2Modal] = useLocalState(false);

  // ── HITL-1 제출 핸들러 ──────────────────────────────────────────────
  const handleHitl1Submit = useCallback(async () => {
    await submitHitl1({
      ingredient_decisions: ingredientDecisions as IngredientDecision[],
      conditional_resolutions: conditionalResolutions.map((r) => ({
        ingredient_name: r.ingredientName,
        meets_condition: r.meetsCondition,
        reasoning: r.reasoning,
      })),
      qualitative_resolutions: [],
      escalation_acknowledgements: escalationAcks as string[],
      reviewer_id: state.hitl2SignerId || "unknown",
    });
  }, [submitHitl1, ingredientDecisions, conditionalResolutions, escalationAcks, state.hitl2SignerId]);

  // ── HITL-2 제출 핸들러 (모달 1단계) ────────────────────────────────
  const handleHitl2Confirm = useCallback(() => {
    setShowHitl2Modal(true);
  }, [setShowHitl2Modal]);

  // ── HITL-2 확정 실행 (모달 확인 2단계) ─────────────────────────────
  const handleHitl2ConfirmExecute = useCallback(async () => {
    setShowHitl2Modal(false);
    if (!state.userVerdict) return;
    await confirmHitl2Result({
      user_verdict: state.userVerdict,
      final_reason: state.hitl2FinalReason,
      selected_citations: [...state.hitl2SelectedCitations],
      signer_id: state.hitl2SignerId,
      signed_at: new Date().toISOString(),
    });
  }, [confirmHitl2Result, state.userVerdict, state.hitl2FinalReason, state.hitl2SelectedCitations, state.hitl2SignerId]);

  // ── canConfirm (레거시 v1용) ───────────────────────────────────────
  const canConfirmLegacy = useMemo(() => {
    if (!source) return false;
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

  // ── canConfirm (HITL-2 v2용) ──────────────────────────────────────
  const canConfirmHitl2 = useMemo(() => {
    if (!state.userVerdict) return false;
    if (state.hitl2FinalReason.trim().length < 10) return false;
    if (!state.hitl2SignerId.trim()) return false;
    return true;
  }, [state.userVerdict, state.hitl2FinalReason, state.hitl2SignerId]);

  // ── 미확인 원재료 → UnidentifiedIngredientReview 용 변환 ──────────
  const unidentifiedIngredients = useMemo(() => {
    if (!internal?.aggregation?.results) return [];
    return internal.aggregation.results
      .filter((r) => r.verdict === "unidentified")
      .map((r) => ({
        name: r.ingredient.name,
        searched_as: r.ingredient.name,
        lookup_error: r.match_method === null ? "NOT_FOUND" : null,
      }));
  }, [internal]);

  // ── 조건부 원재료 → ConditionalResolutionPanel 용 변환 ──────────
  const conditionalIngredients = useMemo(() => {
    if (!internal?.conditional_evaluations) return [];
    return internal.conditional_evaluations.map((ce) => ({
      name: ce.ingredient_name,
      restrictionCondition: ce.condition_description,
      ediblePartHint: undefined,
    }));
  }, [internal]);

  // ── 에스컬레이션 → EscalationAckList 용 변환 ─────────────────────
  const escalationItems = useMemo((): EscalationItem[] => {
    if (!internal?.escalations) return [];
    return internal.escalations.map((e) => ({
      code: e.module_id,
      message: e.reason,
      severity: (e.trigger_type === "error" ? "error" : e.trigger_type === "warning" ? "warning" : "info") as "info" | "warning" | "error",
    }));
  }, [internal]);

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
    </header>
  );

  // ═══════════════════════════════════════════════════════════════════
  // v2 경로: pipeline_version === "v2" — HITL 단계별 조건부 렌더
  // ═══════════════════════════════════════════════════════════════════
  if (isV2) {
    return (
      <main className="mx-auto max-w-5xl space-y-4 p-6">
        {PageHeader}

        {/* ── F2 식품유형 분류 섹션 (f1f2 병합) ── */}
        <FoodTypeSection
          hierarchy={foodTypeHierarchy}
          onEdit={() => setShowFoodTypeEdit(true)}
          isEditable={!isConfirmed}
        />
        {showFoodTypeEdit && foodTypeHierarchy && (
          <FoodTypeEditDialog
            caseId={caseId}
            initial={foodTypeHierarchy}
            onClose={() => setShowFoodTypeEdit(false)}
            onSaved={(updated) => {
              setFoodTypeHierarchy(updated);
              setShowFoodTypeEdit(false);
            }}
          />
        )}

        {/* 오류 메시지 */}
        {state.errorMessage && (
          <div className="rounded-lg bg-red-50 p-3 text-sm text-red-600">
            {state.errorMessage}
          </div>
        )}

        {/* ── HITL-0: F0 completed / approved → F0ApprovalPanel ── */}
        {currentStatus === "completed" && (
          <F0ApprovalPanel
            caseId={caseId}
            parsedResult={source as unknown as Record<string, unknown>}
            onEdit={editF0}
            onApprove={(sig) => approveF0("current-user", sig)}
            isApproved={true}
          />
        )}

        {/* ── F1 pending / running → 로딩 스피너 ── */}
        {(currentStatus === "pending" || currentStatus === "running") && (
          <div className="flex items-center justify-center gap-3 rounded-lg border border-gray-200 bg-gray-50 py-12">
            <span
              data-testid="f1-loading-spinner"
              className="h-5 w-5 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600"
            />
            <span className="text-sm text-gray-600">
              {currentStatus === "running" ? "F1 분석 실행 중..." : "F1 분석 대기 중..."}
            </span>
          </div>
        )}

        {/* ── HITL-1: needs_review ── */}
        {currentStatus === "needs_review" && (
          <div data-testid="hitl1-panel" className="space-y-4">
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              <b>HITL-1:</b> 아래 항목을 검토하고 결정을 제출하세요.
            </div>

            {unidentifiedIngredients.length > 0 && (
              <UnidentifiedIngredientReview
                caseId={caseId}
                ingredients={unidentifiedIngredients}
                onChange={setIngredientDecisions}
                disabled={false}
              />
            )}

            {conditionalIngredients.length > 0 && (
              <ConditionalResolutionPanel
                caseId={caseId}
                ingredients={conditionalIngredients}
                onChange={setConditionalResolutions}
                disabled={false}
              />
            )}

            {escalationItems.length > 0 && (
              <EscalationAckList
                caseId={caseId}
                items={escalationItems}
                onChange={setEscalationAcks}
                disabled={false}
              />
            )}

            <div className="flex justify-end">
              <button
                type="button"
                data-testid="hitl1-submit-btn"
                onClick={handleHitl1Submit}
                disabled={state.isSaving}
                className="rounded bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {state.isSaving ? "제출 중..." : "HITL-1 결정 제출"}
              </button>
            </div>
          </div>
        )}

        {/* ── HITL-2: waiting_review ── */}
        {currentStatus === "waiting_review" && (
          <div className="space-y-4">
            {internal?.forbidden_hits && internal.forbidden_hits.length > 0 && (
              <ForbiddenAlert hits={internal.forbidden_hits} />
            )}

            {internal?.aggregation && (
              <AggregationSummary aggregation={internal.aggregation} />
            )}

            {internal?.law_citations && internal.law_citations.length > 0 && (
              <LawCitationList citations={internal.law_citations} />
            )}

            <VerdictPanel
              aiVerdict={source.verdict}
              failReasons={source.fail_reasons}
              userVerdict={state.userVerdict}
              editReason={state.editReason}
              onChangeVerdict={setUserVerdict}
              onChangeReason={setEditReason}
              stepStatus={currentStatus}
              lawRefs={internal?.law_refs ?? []}
              selectedCitations={state.hitl2SelectedCitations}
              onToggleCitation={toggleHitl2Citation}
              finalReason={state.hitl2FinalReason}
              onChangeFinalReason={setHitl2FinalReason}
              signerId={state.hitl2SignerId}
              onChangeSignerId={setHitl2SignerId}
            />

            <LawRefCheckbox
              lawRefs={internal?.law_refs ?? []}
              selected={state.hitl2SelectedCitations}
              onToggle={toggleHitl2Citation}
            />

            <ConfirmActions
              canConfirm={canConfirmHitl2}
              isConfirmed={isConfirmed}
              isSaving={state.isSaving}
              isConfirming={state.isConfirming}
              onSave={saveEdit}
              onConfirm={handleHitl2Confirm}
              onDownloadPdf={handleDownloadPdf}
            />
          </div>
        )}

        {/* ── confirmed / locked → readonly 배너 ── */}
        {(currentStatus === "confirmed" || currentStatus === "locked") && source && (
          <div className="space-y-4">
            <div className="rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-800">
              ✅ 판정이 확정되었습니다. 수정이 불가합니다.
            </div>
            <VerdictPanel
              aiVerdict={source.verdict}
              failReasons={source.fail_reasons}
              userVerdict={state.userVerdict}
              editReason={state.editReason}
              onChangeVerdict={setUserVerdict}
              onChangeReason={setEditReason}
              stepStatus={currentStatus}
            />
            <ConfirmActions
              canConfirm={false}
              isConfirmed={true}
              isSaving={false}
              isConfirming={false}
              onSave={() => {}}
              onConfirm={() => {}}
              onDownloadPdf={handleDownloadPdf}
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

      {/* F2 식품유형 섹션 */}
      {foodTypeHierarchy && (
        <FoodTypeSection
          hierarchy={foodTypeHierarchy}
          onEdit={() => setShowFoodTypeEdit(true)}
          isEditable={!isConfirmed}
        />
      )}
      {showFoodTypeEdit && foodTypeHierarchy && (
        <FoodTypeEditDialog
          caseId={caseId}
          initial={foodTypeHierarchy}
          onClose={() => setShowFoodTypeEdit(false)}
          onSaved={(updated) => {
            setFoodTypeHierarchy(updated);
            setShowFoodTypeEdit(false);
          }}
        />
      )}

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
        canConfirm={canConfirmLegacy}
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
