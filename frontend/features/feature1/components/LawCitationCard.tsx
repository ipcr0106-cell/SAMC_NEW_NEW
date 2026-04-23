/**
 * F1 RAG — 단일 법령 인용 카드.
 *
 * backend/models/f1_law_citation.py:LawCitation 1:1 렌더.
 * 본문이 길면 PREVIEW_LEN 자까지 요약 표시 후 "펼치기" 토글.
 */

"use client";

import { useState } from "react";
import { BookOpen } from "lucide-react";
import type { LawCitation } from "../types";
import { NAMESPACE_LABEL } from "../types";

interface Props {
  citation: LawCitation;
}

const PREVIEW_LEN = 300;

/** 법령 원문의 <br> 태그를 줄바꿈으로 변환. */
function cleanLawText(raw: string): string {
  return raw.replace(/<br\s*\/?>/gi, "\n");
}

export default function LawCitationCard({ citation }: Props) {
  const [expanded, setExpanded] = useState(false);
  const cleaned = cleanLawText(citation.text);
  const needsTruncate = cleaned.length > PREVIEW_LEN;
  const displayText =
    !needsTruncate || expanded
      ? cleaned
      : cleaned.slice(0, PREVIEW_LEN) + "…";

  const nsLabel = NAMESPACE_LABEL[citation.namespace] ?? citation.namespace;

  return (
    <article
      data-testid="law-citation-card"
      className="rounded border border-gray-200 bg-white p-3"
    >
      <header className="mb-2 flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-blue-700">
            <BookOpen className="h-3 w-3" />
            {nsLabel}
          </span>
          {citation.regulation_id && (
            <span className="text-gray-600">{citation.regulation_id}</span>
          )}
          {citation.section_path && (
            <span className="text-gray-400">· {citation.section_path}</span>
          )}
        </div>
        {citation.score > 0 && (
          <span
            title="매칭된 키워드 수 / 전체 쿼리 키워드 수"
            className="shrink-0 text-[11px] text-gray-400"
          >
            score: {citation.score.toFixed(3)}
          </span>
        )}
      </header>
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-700">
        {displayText}
      </p>
      {needsTruncate && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-1 text-xs text-blue-600 hover:underline"
        >
          {expanded ? "접기" : "펼치기"}
        </button>
      )}
    </article>
  );
}
