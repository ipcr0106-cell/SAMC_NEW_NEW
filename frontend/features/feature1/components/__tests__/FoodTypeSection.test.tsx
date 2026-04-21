import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import FoodTypeSection from "../FoodTypeSection";
import type { FoodTypeHierarchy } from "@/types/pipeline";

const HIERARCHY: FoodTypeHierarchy = {
  category_name: "주류",
  subcategory_name: "증류주",
  food_type: "일반증류주",
  category_no: "13-1",
  law_ref: "주세법 시행령 제3조",
  reason: "증류 방식으로 제조된 주정 함량 25% 이상의 주류.",
  is_alcohol: true,
};

function makeProps(
  overrides: Partial<React.ComponentProps<typeof FoodTypeSection>> = {},
) {
  return {
    hierarchy: HIERARCHY,
    onEdit: vi.fn(),
    isEditable: true,
    ...overrides,
  };
}

describe("FoodTypeSection", () => {
  it("3단계 분류(대/중/소)가 모두 렌더된다", () => {
    render(<FoodTypeSection {...makeProps()} />);
    // "주류"는 Badge와 대분류 셀 두 곳에 표시됨 — getAllByText 사용
    expect(screen.getAllByText("주류").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("증류주")).toBeInTheDocument();
    expect(screen.getByText("일반증류주")).toBeInTheDocument();
  });

  it("주류 여부 Badge가 '주류'로 표시된다", () => {
    render(<FoodTypeSection {...makeProps()} />);
    // Badge(span.ds-badge) 에 '주류' 텍스트가 있는지 확인
    const badges = screen.getAllByText("주류");
    expect(badges.some((el) => el.closest(".ds-badge") !== null)).toBe(true);
  });

  it("일반식품이면 Badge가 '일반식품'으로 표시된다", () => {
    render(
      <FoodTypeSection
        {...makeProps({ hierarchy: { ...HIERARCHY, is_alcohol: false } })}
      />,
    );
    expect(screen.getByText("일반식품")).toBeInTheDocument();
  });

  it("법령 근거와 판정 근거 설명이 렌더된다", () => {
    render(<FoodTypeSection {...makeProps()} />);
    expect(screen.getByText(/주세법 시행령 제3조/)).toBeInTheDocument();
    expect(screen.getByText(/증류 방식으로 제조된/)).toBeInTheDocument();
  });

  it("isEditable=true 이면 수정 버튼이 보인다", () => {
    render(<FoodTypeSection {...makeProps({ isEditable: true })} />);
    expect(screen.getByRole("button", { name: "수정" })).toBeInTheDocument();
  });

  it("isEditable=false 이면 수정 버튼이 없다", () => {
    render(<FoodTypeSection {...makeProps({ isEditable: false })} />);
    expect(screen.queryByRole("button", { name: "수정" })).not.toBeInTheDocument();
  });

  it("수정 버튼 클릭 시 onEdit 이 호출된다", async () => {
    const user = userEvent.setup();
    const onEdit = vi.fn();
    render(<FoodTypeSection {...makeProps({ onEdit })} />);
    await user.click(screen.getByRole("button", { name: "수정" }));
    expect(onEdit).toHaveBeenCalledTimes(1);
  });

  it("hierarchy=null 이면 미실행 안내 메시지를 표시한다", () => {
    render(<FoodTypeSection {...makeProps({ hierarchy: null })} />);
    expect(screen.getByText(/F2 식품유형 분류 결과가 없습니다/)).toBeInTheDocument();
  });

  it("#food-type anchor id가 section에 존재한다", () => {
    const { container } = render(<FoodTypeSection {...makeProps()} />);
    expect(container.querySelector("#food-type")).not.toBeNull();
  });

  // ── Wave 4 P4 보완 T1: F2 임시 실행 트리거 ───────────────────────
  it("hierarchy=null + onRun 제공 시 'AI 분류 실행' 버튼이 노출되고 클릭하면 onRun 이 호출된다", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    render(
      <FoodTypeSection {...makeProps({ hierarchy: null, onRun })} />,
    );
    const btn = screen.getByRole("button", { name: /AI 분류 실행/ });
    expect(btn).toBeInTheDocument();
    await user.click(btn);
    expect(onRun).toHaveBeenCalledTimes(1);
  });

  it("isRunning=true 이면 실행 버튼이 비활성화되고 로딩 표시가 나타난다", () => {
    render(
      <FoodTypeSection
        {...makeProps({ hierarchy: null, onRun: vi.fn(), isRunning: true })}
      />,
    );
    expect(screen.getByTestId("f2-run-btn")).toBeDisabled();
    expect(screen.getByTestId("f2-run-spinner")).toBeInTheDocument();
    expect(screen.getByText(/분석 실행 중/)).toBeInTheDocument();
  });

  it("runError 가 있으면 에러 메시지가 렌더된다", () => {
    render(
      <FoodTypeSection
        {...makeProps({
          hierarchy: null,
          onRun: vi.fn(),
          runError: "F2 실행 실패 — 500 Internal Server Error",
        })}
      />,
    );
    expect(screen.getByTestId("f2-run-error")).toBeInTheDocument();
    expect(
      screen.getByText(/500 Internal Server Error/),
    ).toBeInTheDocument();
  });
});
