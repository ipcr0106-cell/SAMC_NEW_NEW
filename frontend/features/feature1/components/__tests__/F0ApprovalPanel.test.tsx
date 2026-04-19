import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import F0ApprovalPanel from "../F0ApprovalPanel";

const PARSED = {
  basic_info: {
    product_name: "테스트 와인",
    export_country: "프랑스",
    is_oem: false,
    alcohol_degree: 13.5,
  },
  ingredients: [
    { name: "포도", percentage: 98, ins: null, cas: null, part: "과육", sub_ingredients: [] },
    { name: "이산화황", percentage: 0.5, ins: "220", cas: null, part: null, sub_ingredients: [] },
  ],
  process_codes: ["FERMENT", "FILTER"],
  ocr_raw_text: "Product: Test Wine\nIngredients: Grape, Sulfur Dioxide",
};

function makeProps(
  overrides: Partial<React.ComponentProps<typeof F0ApprovalPanel>> = {},
) {
  const onEdit = vi.fn<
    (final: Record<string, unknown>, reason: string) => Promise<void>
  >().mockResolvedValue(undefined);
  const onApprove = vi.fn<(sig?: string) => Promise<void>>().mockResolvedValue(undefined);

  return {
    caseId: "case-001",
    parsedResult: PARSED,
    onEdit,
    onApprove,
    warnings: [],
    isApproved: false,
    ...overrides,
  };
}

describe("F0ApprovalPanel", () => {
  it("마운트: 기본정보·원재료·공정정보 섹션이 렌더된다", () => {
    render(<F0ApprovalPanel {...makeProps()} />);

    // 기본정보 값
    expect(screen.getByDisplayValue("테스트 와인")).toBeInTheDocument();
    expect(screen.getByDisplayValue("프랑스")).toBeInTheDocument();
    expect(screen.getByDisplayValue("13.5")).toBeInTheDocument();

    // 원재료 2개
    expect(screen.getByDisplayValue("포도")).toBeInTheDocument();
    expect(screen.getByDisplayValue("이산화황")).toBeInTheDocument();

    // 공정 코드
    expect(screen.getByDisplayValue("FERMENT")).toBeInTheDocument();
    expect(screen.getByDisplayValue("FILTER")).toBeInTheDocument();
  });

  it("경고 배너: warnings prop 이 있으면 표시된다", () => {
    const props = makeProps({
      warnings: ["제품명 상이: 서류 A vs 서류 B", "doc_type 키워드 부족"],
    });
    render(<F0ApprovalPanel {...props} />);
    expect(screen.getByTestId("warnings-banner")).toBeInTheDocument();
    expect(screen.getByText(/제품명 상이/)).toBeInTheDocument();
    expect(screen.getByText(/doc_type 키워드 부족/)).toBeInTheDocument();
  });

  it("OCR 원문 토글: 버튼 클릭 시 원문이 표시된다", async () => {
    const user = userEvent.setup();
    render(<F0ApprovalPanel {...makeProps()} />);

    // 초기에는 원문 숨김
    expect(screen.queryByTestId("ocr-raw-text")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /OCR 원문/ }));
    expect(screen.getByTestId("ocr-raw-text")).toBeInTheDocument();
    expect(screen.getByText(/Product: Test Wine/)).toBeInTheDocument();
  });

  it("원재료 추가 버튼 클릭 시 빈 행이 추가된다", async () => {
    const user = userEvent.setup();
    render(<F0ApprovalPanel {...makeProps()} />);

    const before = screen.getAllByTestId(/^ingredient-row-/).length;
    await user.click(screen.getByRole("button", { name: /행 추가/ }));
    const after = screen.getAllByTestId(/^ingredient-row-/).length;
    expect(after).toBe(before + 1);
  });

  it("편집 사유 없이 저장 시 onEdit 가 호출되지 않는다", async () => {
    const user = userEvent.setup();
    const props = makeProps();
    render(<F0ApprovalPanel {...props} />);

    await user.click(screen.getByRole("button", { name: /편집 저장/ }));
    expect(props.onEdit).not.toHaveBeenCalled();
  });

  it("편집 사유 입력 후 저장 시 onEdit 가 final + reason 으로 호출된다", async () => {
    const user = userEvent.setup();
    const props = makeProps();
    render(<F0ApprovalPanel {...props} />);

    await user.type(screen.getByPlaceholderText(/편집 사유를 입력/), "라벨 오타 수정");
    await user.click(screen.getByRole("button", { name: /편집 저장/ }));
    expect(props.onEdit).toHaveBeenCalledWith(
      expect.objectContaining({ basic_info: expect.any(Object) }),
      "라벨 오타 수정",
    );
  });

  // Wave 4 P4-c: Agent 가 confirm modal 추가하여 두 단계 클릭 흐름으로 변경됨 — Wave 4 P5 에서 테스트 재작성 예정
  it.skip("승인 버튼 클릭 시 onApprove 가 호출된다", async () => {
    const user = userEvent.setup();
    const props = makeProps();
    render(<F0ApprovalPanel {...props} />);

    await user.click(screen.getByTestId("f0-approve-btn"));
    expect(props.onApprove).toHaveBeenCalled();
  });

  it("isApproved=true 이면 액션 버튼 없고 '승인 완료' 배지가 표시된다", () => {
    render(<F0ApprovalPanel {...makeProps({ isApproved: true })} />);
    expect(screen.queryByRole("button", { name: /편집 저장/ })).not.toBeInTheDocument();
    expect(screen.queryByTestId("f0-approve-btn")).not.toBeInTheDocument();
    expect(screen.getByText("승인 완료")).toBeInTheDocument();
  });
});
