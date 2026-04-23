/**
 * 기준규격 수치 비교 결과 요약.
 * types/pipeline.ts 의 StandardCheck[] 사용 (팀 합의 타입)
 */

"use client";

import { useState } from "react";
import type { StandardCheck } from "@/types/pipeline";
import {
  STANDARDS_STATUS_LABEL,
  STANDARDS_STATUS_COLOR,
} from "../constants";

interface Props {
  checks: StandardCheck[];
}

export default function StandardsSummary({ checks }: Props) {
  // P6 (2026-04-20): "기준 미등록" 행 기본 숨김 + 토글로 모두 보기.
  // 닭지방 같은 동물성 식품은 잔류농약·수의약품 기준이 50~100건 등록돼
  // 실측치 없는 행이 화면을 가득 채우는 잡음 차단.
  const [showAll, setShowAll] = useState(false);

  if (!checks || checks.length === 0) {
    return (
      <section className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-500">
        기준치 검증 데이터가 없습니다. (기능2 식품유형 확정 후 표시)
      </section>
    );
  }

  const violations = checks.filter((c) => c.status === "fail");
  const noData = checks.filter((c) => c.status === "no_threshold");
  const visibleChecks = showAll
    ? checks
    : checks.filter((c) => c.status !== "no_threshold");

  return (
    <section className="rounded-lg border border-gray-200 bg-white">
      <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
        <h3 className="font-semibold text-gray-800">기준규격 수치 비교</h3>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          {violations.length > 0 && (
            <span className="font-semibold text-red-600">
              위반 {violations.length}건
            </span>
          )}
          {noData.length > 0 && (
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              className="text-gray-500 underline-offset-2 hover:text-gray-700 hover:underline"
            >
              기준 미등록 {noData.length}건 {showAll ? "숨기기" : "보기"}
            </button>
          )}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs text-gray-600">
            <tr>
              <th className="px-4 py-2 text-left font-medium">원료</th>
              <th className="px-4 py-2 text-left font-medium">시험항목</th>
              <th className="px-4 py-2 text-right font-medium">실측</th>
              <th className="px-4 py-2 text-right font-medium">기준</th>
              <th className="px-4 py-2 text-left font-medium">단위</th>
              <th className="px-4 py-2 text-left font-medium">상태</th>
              <th className="px-4 py-2 text-left font-medium">조건</th>
              <th className="px-4 py-2 text-left font-medium">근거</th>
            </tr>
          </thead>
          <tbody>
            {visibleChecks.map((c, idx) => (
              <tr
                key={`${c.ingredient_name}-${c.test_category ?? ""}-${idx}`}
                className="border-t border-gray-100"
              >
                <td className="px-4 py-2 font-medium">{c.ingredient_name}</td>
                <td className="px-4 py-2 text-xs text-gray-700">
                  {c.test_category ?? "-"}
                </td>
                <td className="px-4 py-2 text-right">
                  {c.actual_value != null ? c.actual_value : "-"}
                </td>
                <td className="px-4 py-2 text-right">
                  {c.spec_raw
                    ? c.spec_raw
                    : c.threshold_value != null
                      ? c.threshold_value
                      : "-"}
                </td>
                <td className="px-4 py-2 text-xs text-gray-500">{c.unit}</td>
                <td
                  className={`px-4 py-2 text-xs ${STANDARDS_STATUS_COLOR[c.status]}`}
                >
                  {STANDARDS_STATUS_LABEL[c.status]}
                </td>
                <td className="px-4 py-2 text-xs text-gray-500">
                  {c.condition ?? "-"}
                </td>
                <td className="px-4 py-2 text-xs text-gray-500">
                  {c.law_ref ?? "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
