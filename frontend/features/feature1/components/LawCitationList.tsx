/**
 * F1 RAG — 법령 인용 목록 (namespace별 그룹핑).
 *
 * citations 가 비어있으면 null 반환 (rag_skipped 케이스 자동 생략).
 * 같은 namespace 끼리 묶어서 그룹 헤더 + 카드 나열.
 */

"use client";

import type { LawCitation } from "../types";
import { NAMESPACE_LABEL } from "../types";
import LawCitationCard from "./LawCitationCard";

interface Props {
  citations: LawCitation[];
}

export default function LawCitationList({ citations }: Props) {
  if (citations.length === 0) return null;

  // namespace별 그룹핑 (최초 등장 순서 유지)
  const groups = new Map<string, LawCitation[]>();
  for (const c of citations) {
    const arr = groups.get(c.namespace);
    if (arr) arr.push(c);
    else groups.set(c.namespace, [c]);
  }

  return (
    <section
      data-testid="law-citation-list"
      className="rounded-lg border border-gray-200 bg-white p-4"
    >
      <h3 className="mb-3 font-semibold text-gray-800">
        법령 인용 ({citations.length}건)
      </h3>
      <div className="space-y-4">
        {Array.from(groups.entries()).map(([ns, items]) => (
          <div key={ns} className="space-y-2">
            <h4 className="text-xs font-medium text-gray-500">
              {NAMESPACE_LABEL[ns] ?? ns} · {items.length}건
            </h4>
            <div className="space-y-2">
              {items.map((c) => (
                <LawCitationCard key={c.chunk_id} citation={c} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
