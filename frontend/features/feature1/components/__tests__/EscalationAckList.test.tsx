import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EscalationAckList from "../EscalationAckList";
import type { EscalationItem } from "../EscalationAckList";

const ITEMS: EscalationItem[] = [
  {
    code: "step_a_api_error:대두:DATA_GO_KR_TIMEOUT",
    message: "대두: DATA_GO_KR API 타임아웃 — 안전측 채택(금지)",
    severity: "error",
  },
  {
    code: "step_b_unidentified:글루탐산나트륨",
    message: "글루탐산나트륨: 미확인 원재료",
    severity: "warning",
  },
  {
    code: "step_d_rag_skipped",
    message: "RAG 법령 검색 미실행 (임계값 미달)",
    severity: "info",
  },
];

function makeProps(
  overrides: Partial<React.ComponentProps<typeof EscalationAckList>> = {},
) {
  return {
    caseId: "case-001",
    items: ITEMS,
    onChange: vi.fn(),
    disabled: false,
    ...overrides,
  };
}

describe("EscalationAckList", () => {
  it("마운트: 모든 에스컬레이션 메시지와 진행률(0/3)이 렌더된다", () => {
    render(<EscalationAckList {...makeProps()} />);

    expect(screen.getByText(/DATA_GO_KR API 타임아웃/)).toBeInTheDocument();
    expect(screen.getByText(/미확인 원재료/)).toBeInTheDocument();
    expect(screen.getByText(/RAG 법령 검색 미실행/)).toBeInTheDocument();
    expect(screen.getByTestId("ack-progress")).toHaveTextContent("0/3");
  });

  it("빈 목록이면 '에스컬레이션 사유가 없습니다' 표시", () => {
    render(<EscalationAckList {...makeProps({ items: [] })} />);
    expect(screen.getByText(/에스컬레이션 사유가 없습니다/)).toBeInTheDocument();
  });

  it("체크박스 클릭 시 onChange 에 해당 code 가 포함된다", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<EscalationAckList {...makeProps({ onChange })} />);

    const checkboxes = screen.getAllByRole("checkbox");
    await user.click(checkboxes[0]); // 첫 번째 (error)

    expect(onChange).toHaveBeenLastCalledWith(
      expect.arrayContaining(["step_a_api_error:대두:DATA_GO_KR_TIMEOUT"]),
    );
    expect(screen.getByTestId("ack-progress")).toHaveTextContent("1/3");
  });

  it("'전체 확인' 버튼 클릭 시 모든 code 가 onChange 에 전달된다", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<EscalationAckList {...makeProps({ onChange })} />);

    await user.click(screen.getByTestId("check-all-button"));

    expect(onChange).toHaveBeenLastCalledWith(
      expect.arrayContaining(ITEMS.map((i) => i.code)),
    );
    expect(screen.getByTestId("ack-progress")).toHaveTextContent("3/3");
  });

  it("모두 체크 시 '전체 확인' 버튼이 사라지고 완료 메시지가 표시된다", async () => {
    const user = userEvent.setup();
    render(<EscalationAckList {...makeProps()} />);

    await user.click(screen.getByTestId("check-all-button"));

    expect(screen.queryByTestId("check-all-button")).not.toBeInTheDocument();
    expect(screen.getByText(/모든 에스컬레이션을 확인했습니다/)).toBeInTheDocument();
  });

  it("disabled=true 이면 체크박스가 모두 비활성화되고 '전체 확인' 버튼이 없다", () => {
    render(<EscalationAckList {...makeProps({ disabled: true })} />);
    const checkboxes = screen.getAllByRole("checkbox");
    checkboxes.forEach((cb) => expect(cb).toBeDisabled());
    expect(screen.queryByTestId("check-all-button")).not.toBeInTheDocument();
  });
});
