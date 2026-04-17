import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import RagConflictPanel from "../RagConflictPanel";
import type { Feature1Result } from "@/types/pipeline";

// 공통 Props 생성기
function makeProps(overrides: Partial<React.ComponentProps<typeof RagConflictPanel>> = {}) {
  const onDecide = vi.fn<
    (verdict: Feature1Result["verdict"], reason: string) => Promise<void>
  >().mockResolvedValue(undefined);

  return {
    conflictStatus: "conflict" as const,
    ragVerdict: "prohibited" as const,
    ragReasoning: "식품첨가물공전 §3.2.1 에 따라 사용 금지된 첨가물입니다.",
    dbVerdict: "수입가능" as Feature1Result["verdict"],
    onDecide,
    isSaving: false,
    ...overrides,
  };
}

describe("RagConflictPanel", () => {
  it("conflict 상태 라벨 + DB/RAG 판정 2칸 + RAG 근거를 표시한다", () => {
    const props = makeProps();
    render(<RagConflictPanel {...props} />);
    expect(screen.getByText(/DB·RAG 충돌/)).toBeInTheDocument();
    expect(screen.getByText("수입가능")).toBeInTheDocument();
    expect(screen.getByText("금지")).toBeInTheDocument();
    expect(screen.getByText(/사용 금지된 첨가물/)).toBeInTheDocument();
  });

  it("rag_supplemented 상태는 amber 톤 (다른 배지)", () => {
    const props = makeProps({ conflictStatus: "rag_supplemented" });
    render(<RagConflictPanel {...props} />);
    expect(screen.getByText(/RAG 보완 판정/)).toBeInTheDocument();
  });

  it("DB 따르기 선택 후 사유 입력하면 dbVerdict 로 onDecide 호출", async () => {
    const user = userEvent.setup();
    const props = makeProps();
    render(<RagConflictPanel {...props} />);

    await user.click(screen.getByRole("button", { name: /DB 따르기/ }));
    const textarea = screen.getByPlaceholderText(/결정 사유를 기재/);
    await user.type(textarea, "DB 근거가 더 최신 개정임");
    await user.click(screen.getByRole("button", { name: /결정 확정/ }));

    expect(props.onDecide).toHaveBeenCalledWith(
      "수입가능",
      "DB 근거가 더 최신 개정임",
    );
  });

  it("RAG 따르기 — ragVerdict=permitted → '수입가능' 으로 변환", async () => {
    const user = userEvent.setup();
    const props = makeProps({
      ragVerdict: "permitted",
      ragReasoning: "공전에 명시적으로 허용됨",
    });
    render(<RagConflictPanel {...props} />);

    await user.click(screen.getByRole("button", { name: /RAG 따르기.*수입가능/ }));
    await user.type(screen.getByPlaceholderText(/결정 사유/), "RAG 근거 채택");
    await user.click(screen.getByRole("button", { name: /결정 확정/ }));

    expect(props.onDecide).toHaveBeenCalledWith("수입가능", "RAG 근거 채택");
  });

  it("ragVerdict=error 이면 RAG 따르기 버튼이 disabled", () => {
    const props = makeProps({ ragVerdict: "error", ragReasoning: null });
    render(<RagConflictPanel {...props} />);
    const ragBtn = screen.getByRole("button", { name: /RAG 따르기/ });
    expect(ragBtn).toBeDisabled();
  });

  it("수동 판정 → 수입불가 라디오 선택 + 사유 → onDecide(수입불가) 호출", async () => {
    const user = userEvent.setup();
    const props = makeProps();
    render(<RagConflictPanel {...props} />);

    await user.click(screen.getByRole("button", { name: "수동 판정" }));
    await user.click(screen.getByLabelText("수입불가"));
    await user.type(screen.getByPlaceholderText(/결정 사유/), "Q&A 참조");
    await user.click(screen.getByRole("button", { name: /결정 확정/ }));

    expect(props.onDecide).toHaveBeenCalledWith("수입불가", "Q&A 참조");
  });

  it("사유 공백이면 '결정 확정' 버튼 disabled", async () => {
    const user = userEvent.setup();
    const props = makeProps();
    render(<RagConflictPanel {...props} />);

    await user.click(screen.getByRole("button", { name: /DB 따르기/ }));
    const confirmBtn = screen.getByRole("button", { name: /결정 확정/ });
    expect(confirmBtn).toBeDisabled();
  });

  it("isSaving=true 이면 버튼 라벨이 '저장 중...' 이고 disabled", async () => {
    const user = userEvent.setup();
    const props = makeProps({ isSaving: true });
    render(<RagConflictPanel {...props} />);

    await user.click(screen.getByRole("button", { name: /DB 따르기/ }));
    await user.type(screen.getByPlaceholderText(/결정 사유/), "어쨌든");
    const confirmBtn = screen.getByRole("button", { name: /저장 중/ });
    expect(confirmBtn).toBeDisabled();
  });
});
