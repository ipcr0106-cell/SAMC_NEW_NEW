import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import LawCitationList from "../LawCitationList";
import type { LawCitation } from "../../types";

const mkCitation = (
  chunk_id: string,
  namespace: string,
  text = "샘플 조문",
): LawCitation => ({
  chunk_id,
  namespace,
  regulation_id: null,
  section_path: null,
  text,
  score: 0.5,
});

describe("LawCitationList", () => {
  it("빈 배열이면 아무것도 렌더하지 않는다 (rag_skipped 케이스)", () => {
    const { container } = render(<LawCitationList citations={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("전체 건수를 헤더에 표시한다", () => {
    const citations = [
      mkCitation("c1", "additive_code_text"),
      mkCitation("c2", "food_code_text"),
      mkCitation("c3", "additive_code_text"),
    ];
    render(<LawCitationList citations={citations} />);
    expect(screen.getByText("법령 인용 (3건)")).toBeInTheDocument();
  });

  it("같은 namespace 끼리 그룹핑하고 그룹별 건수를 표시한다", () => {
    const citations = [
      mkCitation("c1", "additive_code_text", "A"),
      mkCitation("c2", "food_code_text", "B"),
      mkCitation("c3", "additive_code_text", "C"),
    ];
    render(<LawCitationList citations={citations} />);
    expect(screen.getByText("식품첨가물공전 · 2건")).toBeInTheDocument();
    expect(screen.getByText("식품공전 · 1건")).toBeInTheDocument();
  });

  it("카드 개수가 citations 길이와 일치한다", () => {
    const citations = [
      mkCitation("c1", "additive_code_text"),
      mkCitation("c2", "food_code_text"),
      mkCitation("c3", "health_food_text"),
    ];
    render(<LawCitationList citations={citations} />);
    const cards = screen.getAllByTestId("law-citation-card");
    expect(cards).toHaveLength(3);
  });
});
