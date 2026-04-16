/**
 * Step 0 — 절대 금지 원료(forbidden_ingredients) 적중 시 최상단 경고.
 */

"use client";

import type { ForbiddenHitDetail } from "../types";
import { FORBIDDEN_CATEGORY_LABEL } from "../types";

interface Props {
  hits: ForbiddenHitDetail[];
}

export default function ForbiddenAlert({ hits }: Props) {
  if (!hits || hits.length === 0) return null;

  return (
    <section className="rounded-lg border-2 border-red-400 bg-red-50 p-4">
      <div className="flex items-center gap-2">
        <span className="text-2xl">⛔</span>
        <h2 className="text-lg font-semibold text-red-700">
          수입불가 — 절대 금지 원료 포함
        </h2>
      </div>
      <p className="mt-1 text-sm text-red-600">
        아래 원료가 발견되어 파이프라인이 중단되었습니다. 이후 단계(식품유형 분류 등)는 실행되지 않습니다.
      </p>
      <ul className="mt-3 space-y-2">
        {hits.map((h) => (
          <li
            key={h.name_ko}
            className="rounded border border-red-200 bg-white p-3 text-sm"
          >
            <div className="font-semibold text-red-700">{h.name_ko}</div>
            <div className="mt-1 text-gray-600">
              <span className="mr-2 inline-block rounded bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                {FORBIDDEN_CATEGORY_LABEL[h.category]}
              </span>
              {h.law_source && <span className="mr-2">📜 {h.law_source}</span>}
            </div>
            {h.reason && (
              <div className="mt-1 text-xs text-gray-500">{h.reason}</div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
