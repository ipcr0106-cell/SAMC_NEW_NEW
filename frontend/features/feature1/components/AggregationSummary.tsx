/**
 * 원재료 매칭 집계 요약 — 허용/제한/금지/미확인 건수.
 */

"use client";

import type { Feature1Internal } from "../types";

interface Props {
  aggregation: Feature1Internal["aggregation"];
}

export default function AggregationSummary({ aggregation }: Props) {
  if (!aggregation) return null;
  const { total, permitted, restricted, prohibited, unidentified } = aggregation;

  const cards = [
    { label: "허용", value: permitted, color: "bg-green-50 text-green-700 border-green-200" },
    { label: "조건부", value: restricted, color: "bg-yellow-50 text-yellow-700 border-yellow-200" },
    { label: "금지", value: prohibited, color: "bg-red-50 text-red-700 border-red-200" },
    { label: "미확인", value: unidentified, color: "bg-gray-50 text-gray-700 border-gray-200" },
  ];

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="font-semibold text-gray-800">원재료 매칭 집계</h3>
        <span className="text-sm text-gray-500">총 {total}건</span>
      </div>
      <div className="grid grid-cols-4 gap-3">
        {cards.map((c) => (
          <div
            key={c.label}
            className={`rounded-md border p-3 text-center ${c.color}`}
          >
            <div className="text-2xl font-bold">{c.value}</div>
            <div className="text-xs">{c.label}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
