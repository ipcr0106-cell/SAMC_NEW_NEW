/**
 * 담당자 최종 판정 — 수입가능/수입불가/보류 라디오 + 수정 사유.
 */

"use client";

import type { Feature1Result } from "@/types/pipeline";
import { VERDICT_COLOR, VERDICT_LABEL } from "../constants";

interface Props {
  aiVerdict: Feature1Result["verdict"];
  failReasons: string[];
  userVerdict: "수입가능" | "수입불가" | "보류" | null;
  editReason: string;
  onChangeVerdict: (v: "수입가능" | "수입불가" | "보류") => void;
  onChangeReason: (r: string) => void;
}

export default function VerdictPanel({
  aiVerdict,
  failReasons,
  userVerdict,
  editReason,
  onChangeVerdict,
  onChangeReason,
}: Props) {
  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="mb-3 font-semibold text-gray-800">최종 판정</h3>

      <div className="mb-4 rounded bg-gray-50 p-3">
        <div className="text-xs text-gray-500">AI 1차 판정</div>
        <div className={`mt-1 text-lg font-semibold ${VERDICT_COLOR[aiVerdict]}`}>
          {VERDICT_LABEL[aiVerdict]}
        </div>
        {failReasons.length > 0 && (
          <ul className="mt-2 list-inside list-disc text-xs text-gray-600">
            {failReasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="space-y-2">
        <div className="text-xs font-medium text-gray-700">담당자 판정</div>
        <div className="flex gap-4">
          {(["수입가능", "수입불가", "보류"] as const).map((v) => (
            <label key={v} className="flex cursor-pointer items-center gap-2">
              <input
                type="radio"
                name="user-verdict"
                value={v}
                checked={userVerdict === v}
                onChange={() => onChangeVerdict(v)}
                className="h-4 w-4 accent-blue-600"
              />
              <span className="text-sm">{v}</span>
            </label>
          ))}
        </div>

        {userVerdict && userVerdict !== aiVerdict && (
          <div>
            <div className="mb-1 text-xs font-medium text-gray-700">
              수정 사유 <span className="text-red-500">*</span>
              <span className="ml-2 text-gray-500">식약처 소명 자료에 포함됩니다.</span>
            </div>
            <textarea
              value={editReason}
              onChange={(e) => onChangeReason(e.target.value)}
              rows={3}
              placeholder="AI 판정과 다른 이유를 기재하세요."
              className="w-full rounded border border-gray-300 p-2 text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>
        )}
      </div>
    </section>
  );
}
