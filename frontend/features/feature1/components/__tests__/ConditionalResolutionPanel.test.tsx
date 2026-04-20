import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ConditionalResolutionPanel from "../ConditionalResolutionPanel";
import type { ConditionalIngredient } from "../ConditionalResolutionPanel";

const INGREDIENTS: ConditionalIngredient[] = [
  {
    name: "소르빈산",
    restrictionCondition: "탄산음료, 과채주스류 등에 한하여 0.5 g/kg 이하 사용 가능",
    ediblePartHint: "전체",
  },
  {
    name: "아질산나트륨",
    restrictionCondition: "식육가공품 발색제로만 허용. 0.07 g/kg 이하.",
    ediblePartHint: undefined,
  },
];

function makeProps(
  overrides: Partial<React.ComponentProps<typeof ConditionalResolutionPanel>> = {},
) {
  return {
    caseId: "case-001",
    ingredients: INGREDIENTS,
    onChange: vi.fn(),
    disabled: false,
    ...overrides,
  };
}

describe("ConditionalResolutionPanel", () => {
  it("마운트: 각 원재료 카드와 사용 조건 텍스트가 렌더된다", () => {
    render(<ConditionalResolutionPanel {...makeProps()} />);

    expect(screen.getByText("소르빈산")).toBeInTheDocument();
    expect(screen.getByText(/탄산음료, 과채주스류/)).toBeInTheDocument();
    expect(screen.getByText("아질산나트륨")).toBeInTheDocument();
    expect(screen.getByText(/식육가공품 발색제/)).toBeInTheDocument();
    expect(screen.getByText("전체")).toBeInTheDocument();
  });

  it("빈 목록이면 '조건부 원재료가 없습니다' 표시", () => {
    render(<ConditionalResolutionPanel {...makeProps({ ingredients: [] })} />);
    expect(screen.getByText(/조건부 원재료가 없습니다/)).toBeInTheDocument();
  });

  it("'조건 부합' 라디오 선택 시 onChange 에 meetsCondition=true 가 전달된다", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ConditionalResolutionPanel {...makeProps({ onChange })} />);

    // 소르빈산 카드에서 '조건 부합' 선택
    const card = screen.getByTestId("conditional-card-소르빈산");
    const meetsRadio = card.querySelector("input[value='meets']") as HTMLInputElement;
    await user.click(meetsRadio);

    expect(onChange).toHaveBeenCalledWith(
      expect.arrayContaining([
        expect.objectContaining({ ingredientName: "소르빈산", meetsCondition: true }),
      ]),
    );
  });

  it("'조건 불충족' 라디오 선택 후 사유 입력 시 onChange 에 전달된다", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ConditionalResolutionPanel {...makeProps({ onChange })} />);

    const card = screen.getByTestId("conditional-card-아질산나트륨");
    const notMeetsRadio = card.querySelector("input[value='not-meets']") as HTMLInputElement;
    await user.click(notMeetsRadio);

    const textarea = screen.getAllByPlaceholderText(/조건 부합\/불충족 판단 근거/)[0];
    await user.type(textarea, "해당 제품은 음료류로 식육가공품 조건 미해당");

    expect(onChange).toHaveBeenLastCalledWith(
      expect.arrayContaining([
        expect.objectContaining({
          ingredientName: "아질산나트륨",
          meetsCondition: false,
          reasoning: expect.stringContaining("음료류"),
        }),
      ]),
    );
  });

  it("disabled=true 이면 라디오가 비활성화된다", () => {
    render(<ConditionalResolutionPanel {...makeProps({ disabled: true })} />);
    const radios = screen.getAllByRole("radio");
    radios.forEach((r) => expect(r).toBeDisabled());
  });
});
