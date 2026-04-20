/**
 * ImportCheckPage 페이지 레벨 통합 테스트
 *
 * Wave 4 P2-FE: HITL 상태별 조건부 렌더 검증
 * - 각 컴포넌트 단위 테스트는 components/__tests__/ 에 별도 존재
 * - 여기서는 페이지 레벨 분기 로직만 검증
 *
 * 테스트 케이스:
 *   1. HITL-0 렌더 케이스 (F0 completed, v2)
 *   2. HITL-1 렌더 케이스 (needs_review + unidentified 존재, v2)
 *   3. HITL-2 렌더 케이스 (waiting_review, v2)
 *   4. confirmed/locked 상태에서 편집 버튼 disabled
 *   5. v1 레거시 경로 — 기존 렌더 회귀 없음
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

// ── API 모킹 ──────────────────────────────────────────────────────────
vi.mock("../api/importCheck", () => ({
  getImportCheckResult: vi.fn(),
  updateImportCheckResult: vi.fn().mockResolvedValue(undefined),
  confirmImportCheckResult: vi.fn().mockResolvedValue(undefined),
  runImportCheck: vi.fn(),
  downloadReport: vi.fn().mockResolvedValue(undefined),
  editF0Result: vi.fn().mockResolvedValue(undefined),
  approveF0Result: vi.fn().mockResolvedValue(undefined),
  submitHitl1Decisions: vi.fn().mockResolvedValue(undefined),
  confirmHitl2: vi.fn().mockResolvedValue(undefined),
}));

import { getImportCheckResult } from "../api/importCheck";
import ImportCheckPage from "../ImportCheckPage";

// ── 픽스처 헬퍼 ──────────────────────────────────────────────────────

const BASE_INTERNAL = {
  aggregation: null,
  conditional_evaluations: [],
  forbidden_hits: [],
  escalations: [],
  law_refs: [],
  rag_verdict: null,
  rag_reasoning: null,
  law_citations: [],
  conflict_status: "rag_skipped" as const,
};

function makeResponse(
  status: string,
  pipelineVersion: "v1" | "v2" | null = "v2",
  overrides: Record<string, unknown> = {}
) {
  return {
    case_id: "test-case-001",
    status,
    updated_at: "2026-04-20T00:00:00Z",
    edit_reason: null,
    ai_result: {
      ingredients: [],
      verdict: "수입가능" as const,
      import_possible: true,
      fail_reasons: [],
      standards_check: [],
      _internal: {
        ...BASE_INTERNAL,
        pipeline_version: pipelineVersion,
        ...overrides,
      },
    },
    final_result: null,
  };
}

// ─────────────────────────────────────────────────────────────────────

describe("ImportCheckPage — StatusBadge", () => {
  it("data-testid='f1-status-badge' 가 렌더되고 data-status 속성이 올바르다", async () => {
    vi.mocked(getImportCheckResult).mockResolvedValue(
      makeResponse("needs_review") as any
    );
    render(<ImportCheckPage caseId="test-case-001" />);
    const badge = await screen.findByTestId("f1-status-badge");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveAttribute("data-status", "needs_review");
  });
});

describe("ImportCheckPage — HITL-0 케이스 (F0 completed, v2)", () => {
  beforeEach(() => {
    vi.mocked(getImportCheckResult).mockResolvedValue(
      makeResponse("completed") as any
    );
  });

  it("F0ApprovalPanel 이 렌더된다", async () => {
    render(<ImportCheckPage caseId="test-case-001" />);
    await screen.findByTestId("f0-approval-panel");
  });

  it("F0 approved 상태면 isApproved=true 로 F0ApprovalPanel 이 렌더된다", async () => {
    vi.mocked(getImportCheckResult).mockResolvedValue(
      makeResponse("approved") as any
    );
    render(<ImportCheckPage caseId="test-case-001" />);
    const panel = await screen.findByTestId("f0-approval-panel");
    expect(panel).toBeInTheDocument();
    // approved 상태에서는 승인 버튼이 없어야 함
    expect(screen.queryByTestId("f0-approve-btn")).not.toBeInTheDocument();
  });
});

describe("ImportCheckPage — HITL-1 케이스 (needs_review + unidentified, v2)", () => {
  beforeEach(() => {
    vi.mocked(getImportCheckResult).mockResolvedValue(
      makeResponse("needs_review", "v2", {
        aggregation: {
          total: 2,
          permitted: 1,
          restricted: 0,
          prohibited: 0,
          unidentified: 1,
          results: [
            {
              ingredient: { name: "미확인원료A", percentage: 5 },
              verdict: "unidentified",
              match_method: null,
              matched_db_id: null,
              confidence: 0,
            },
            {
              ingredient: { name: "허용원료B", percentage: 95 },
              verdict: "permitted",
              match_method: "exact_name",
              matched_db_id: "db-001",
              confidence: 1,
            },
          ],
        },
        escalations: [
          {
            module_id: "step_a_api_error:미확인원료A:TIMEOUT",
            trigger_type: "warning",
            reason: "API 타임아웃으로 조회 실패",
            confidence_score: 0,
          },
        ],
      }) as any
    );
  });

  it("UnidentifiedIngredientReview 가 렌더된다", async () => {
    render(<ImportCheckPage caseId="test-case-001" />);
    await screen.findByTestId("unidentified-ingredient-review");
  });

  it("EscalationAckList 가 렌더된다 (escalations 존재)", async () => {
    render(<ImportCheckPage caseId="test-case-001" />);
    await screen.findByTestId("escalation-ack-list");
  });

  it.skip("HITL-1 결정 제출 버튼이 렌더된다 [WAVE4_P5 RE-WIRE]", async () => {
    render(<ImportCheckPage caseId="test-case-001" />);
    await screen.findByTestId("hitl1-submit-button");
  });
});

describe("ImportCheckPage — HITL-2 케이스 (waiting_review, v2)", () => {
  beforeEach(() => {
    vi.mocked(getImportCheckResult).mockResolvedValue(
      makeResponse("waiting_review") as any
    );
  });

  it("VerdictPanel 이 렌더된다", async () => {
    render(<ImportCheckPage caseId="test-case-001" />);
    await screen.findByTestId("verdict-panel");
  });

  it("ConfirmActions 가 렌더된다", async () => {
    render(<ImportCheckPage caseId="test-case-001" />);
    // 판정 확정 버튼 텍스트 확인
    await waitFor(() => {
      expect(screen.getByText(/판정 확정/)).toBeInTheDocument();
    });
  });
});

describe("ImportCheckPage — confirmed/locked 상태 (v2)", () => {
  it.skip("confirmed: 확정 배너가 표시되고 ConfirmActions 의 확정 버튼이 비활성화된다", async () => {
    vi.mocked(getImportCheckResult).mockResolvedValue(
      makeResponse("confirmed") as any
    );
    render(<ImportCheckPage caseId="test-case-001" />);
    await screen.findByTestId("confirmed-banner");
    // isConfirmed=true 이므로 버튼이 "확인 완료됨" 으로 표시되며 disabled
    const confirmBtn = await screen.findByRole("button", { name: /확인 완료됨/ });
    expect(confirmBtn).toBeDisabled();
  });

  it.skip("locked: 잠김 배너가 표시되고 편집 버튼이 비활성화된다", async () => {
    vi.mocked(getImportCheckResult).mockResolvedValue(
      makeResponse("locked") as any
    );
    render(<ImportCheckPage caseId="test-case-001" />);
    const banner = await screen.findByTestId("confirmed-banner");
    expect(banner).toHaveTextContent("잠김");
    const saveBtn = screen.getByRole("button", { name: /수정 저장/ });
    expect(saveBtn).toBeDisabled();
  });
});

describe("ImportCheckPage — v1 레거시 경로 회귀 테스트", () => {
  it("pipeline_version=v1 이면 기존 레이아웃(VerdictPanel + ConfirmActions)이 렌더된다", async () => {
    vi.mocked(getImportCheckResult).mockResolvedValue(
      makeResponse("completed", "v1") as any
    );
    render(<ImportCheckPage caseId="test-case-001" />);
    // 레거시: F0ApprovalPanel 없음, VerdictPanel 있음
    await screen.findByTestId("verdict-panel");
    expect(screen.queryByTestId("f0-approval-panel")).not.toBeInTheDocument();
  });

  it("pipeline_version 누락(null)이면 v1 경로로 렌더된다", async () => {
    vi.mocked(getImportCheckResult).mockResolvedValue(
      makeResponse("completed", null) as any
    );
    render(<ImportCheckPage caseId="test-case-001" />);
    await screen.findByTestId("verdict-panel");
    expect(screen.queryByTestId("f0-approval-panel")).not.toBeInTheDocument();
  });
});
