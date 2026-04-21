/**
 * 원재료별 매칭 결과 테이블.
 */

"use client";

import type { IngredientMatchDetail } from "../types";

interface Props {
  results: IngredientMatchDetail[];
}

const VERDICT_ICON: Record<IngredientMatchDetail["verdict"], string> = {
  permitted: "✅",
  restricted: "⚠️",
  prohibited: "❌",
  unidentified: "❓",
};

const VERDICT_BG: Record<IngredientMatchDetail["verdict"], string> = {
  permitted: "bg-green-50",
  restricted: "bg-yellow-50",
  prohibited: "bg-red-50",
  unidentified: "bg-gray-50",
};

export default function IngredientMatchTable({ results }: Props) {
  if (!results || results.length === 0) {
    return (
      <section className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-500">
        매칭 결과가 없습니다.
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-gray-200 bg-white">
      <div className="border-b border-gray-200 px-4 py-3">
        <h3 className="font-semibold text-gray-800">원재료 매칭 상세</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs text-gray-600">
            <tr>
              <th className="px-4 py-2 text-left font-medium">상태</th>
              <th className="px-4 py-2 text-left font-medium">원본명</th>
              <th className="px-4 py-2 text-left font-medium">매칭명(한글 표준)</th>
              <th className="px-4 py-2 text-left font-medium">배합비(%)</th>
              <th className="px-4 py-2 text-left font-medium">법령 출처</th>
            </tr>
          </thead>
          <tbody>
            {results.map((r, idx) => (
              <tr
                key={`${r.ingredient.name}-${idx}`}
                className={`border-t border-gray-100 ${VERDICT_BG[r.verdict]}`}
              >
                <td className="px-4 py-2">{VERDICT_ICON[r.verdict]}</td>
                <td className="px-4 py-2 font-medium">{r.ingredient.name}</td>
                <td className="px-4 py-2 text-gray-700">
                  {r.matched_name_ko ? (
                    <span>{r.matched_name_ko}</span>
                  ) : (
                    <span className="text-gray-400">-</span>
                  )}
                </td>
                <td className="px-4 py-2 text-gray-600">
                  {r.ingredient.percentage != null ? `${r.ingredient.percentage}%` : "-"}
                </td>
                <td className="px-4 py-2 text-xs text-gray-500">
                  {r.law_source ?? "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
