import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LawCitationCard from "../LawCitationCard";
import type { LawCitation } from "../../types";

const shortCitation: LawCitation = {
  chunk_id: "c1",
  namespace: "additive_code_text",
  regulation_id: "식품첨가물공전 §3.1.1",
  section_path: "제3장 > 사용기준",
  text: "벤조산나트륨은 보존료로 탄산음료 등에 0.6 g/kg 이하로 사용할 수 있다.",
  score: 0.812,
};

const longText = "한국어 법령 조문이 아주 길게 이어지는 경우의 테스트 문장입니다. ".repeat(20);
const longCitation: LawCitation = {
  ...shortCitation,
  chunk_id: "c2",
  text: longText,
};

describe("LawCitationCard", () => {
  it("namespace 한국어 라벨 + regulation_id + section_path + score 를 렌더한다", () => {
    render(<LawCitationCard citation={shortCitation} />);
    expect(screen.getByText("식품첨가물공전")).toBeInTheDocument();
    expect(screen.getByText(shortCitation.regulation_id!)).toBeInTheDocument();
    expect(
      screen.getByText(`· ${shortCitation.section_path}`),
    ).toBeInTheDocument();
    expect(screen.getByText(/score: 0\.812/)).toBeInTheDocument();
    expect(screen.getByText(/벤조산나트륨은 보존료로/)).toBeInTheDocument();
  });

  it("300자 이하 본문에는 펼치기 버튼이 없다", () => {
    render(<LawCitationCard citation={shortCitation} />);
    expect(screen.queryByRole("button", { name: /펼치기|접기/ })).toBeNull();
  });

  it("300자 초과 본문은 펼치기 토글로 전체 텍스트를 표시한다", async () => {
    const user = userEvent.setup();
    render(<LawCitationCard citation={longCitation} />);

    const toggle = screen.getByRole("button", { name: "펼치기" });
    expect(toggle).toBeInTheDocument();

    await user.click(toggle);
    expect(
      screen.getByRole("button", { name: "접기" }),
    ).toBeInTheDocument();
  });

  it("NAMESPACE_LABEL 에 없는 namespace 는 원본 키로 표시한다", () => {
    render(
      <LawCitationCard
        citation={{ ...shortCitation, namespace: "unknown_ns" }}
      />,
    );
    expect(screen.getByText("unknown_ns")).toBeInTheDocument();
  });

  it("regulation_id 와 section_path 가 null 이어도 깨지지 않는다", () => {
    render(
      <LawCitationCard
        citation={{ ...shortCitation, regulation_id: null, section_path: null }}
      />,
    );
    expect(screen.getByText("식품첨가물공전")).toBeInTheDocument();
    expect(screen.queryByText("식품첨가물공전 §3.1.1")).toBeNull();
  });
});
