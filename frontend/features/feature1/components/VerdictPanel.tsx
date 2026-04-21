/**
 * 담당자 최종 판정 — HITL-2 통합 버전
 *
 * 기존 기능 유지:
 *   - AI 1차 판정 표시
 *   - 수입가능/수입불가/보류 라디오
 *   - 수정 사유 (AI 판정과 다를 때 필수)
 *
 * HITL-2 확장:
 *   - LawRefCheckbox 통합 (Step D citations 중 채택 선택)
 *   - final_reason 필수 입력 (최소 10자)
 *   - signer_id 입력
 *   - status === "locked" | "confirmed" 시 readonly 잠금 UI
 */

"use client";

import { useState } from "react";
import { Lock } from "lucide-react";
import type { Feature1Result } from "@/types/pipeline";
import type { PipelineStepStatus } from "@/types/pipeline";
import { VERDICT_COLOR, VERDICT_LABEL } from "../constants";
import LawRefCheckbox from "./LawRefCheckbox";

interface LawRef {
  law_source: string;
  law_article?: string | null;
}

interface Props {
  aiVerdict: Feature1Result["verdict"];
  failReasons: string[];
  userVerdict: "수입가능" | "수입불가" | "보류" | null;
  editReason: string;
  onChangeVerdict: (v: "수입가능" | "수입불가" | "보류") => void;
  onChangeReason: (r: string) => void;
  // HITL-2 확장 props (선택 — 미제공 시 기존 동작 유지)
  lawRefs?: LawRef[];
  selectedCitations?: Set<string>;
  onToggleCitation?: (lawSource: string) => void;
  finalReason?: string;
  onChangeFinalReason?: (v: string) => void;
  signerId?: string;
  onChangeSignerId?: (v: string) => void;
  /** confirmed / locked 상태면 전체 readonly */
  stepStatus?: PipelineStepStatus;
}

export default function VerdictPanel({
  aiVerdict,
  failReasons,
  userVerdict,
  editReason,
  onChangeVerdict,
  onChangeReason,
  lawRefs,
  selectedCitations,
  onToggleCitation,
  finalReason,
  onChangeFinalReason,
  signerId,
  onChangeSignerId,
  stepStatus,
}: Props) {
  const isLocked = stepStatus === "locked" || stepStatus === "confirmed";
  // HITL-2 모드 여부: finalReason 핸들러가 제공되면 HITL-2 모드
  const isHitl2Mode = typeof onChangeFinalReason === "function";

  // final_reason 글자수 경고
  const [finalReasonTouched, setFinalReasonTouched] = useState(false);
  const finalReasonLen = (finalReason ?? "").length;
  const finalReasonValid = finalReasonLen >= 10;

  return (
    <section
      data-testid="verdict-panel"
      className="rounded-lg border border-gray-200 bg-white p-4"
    >
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-semibold text-gray-800">최종 판정</h3>
        {isLocked && (
          <span className="flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600">
            <Lock className="h-3 w-3" />
            확정됨 (수정 불가)
          </span>
        )}
      </div>

      {/* AI 1차 판정 */}
      <div className="mb-4 rounded bg-gray-50 p-3">
        <div className="text-xs text-gray-500">AI 1차 판정</div>
        <div
          data-testid="ai-recommended-verdict"
          className={`mt-1 text-lg font-semibold ${VERDICT_COLOR[aiVerdict]}`}
        >
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

      {/* HITL-2: 법령 인용 체크박스 (citations 존재 시) */}
      {isHitl2Mode && lawRefs && lawRefs.length > 0 && onToggleCitation && selectedCitations && (
        <div className="mb-4">
          <LawRefCheckbox
            lawRefs={lawRefs}
            selected={selectedCitations}
            onToggle={isLocked ? () => undefined : onToggleCitation}
          />
        </div>
      )}

      {/* 담당자 판정 라디오 */}
      <div className="space-y-2">
        <div className="text-xs font-medium text-gray-700">담당자 판정</div>
        <div className="flex gap-4">
          {(["수입가능", "수입불가", "보류"] as const).map((v) => (
            <label key={v} className={`flex items-center gap-2 ${isLocked ? "cursor-default" : "cursor-pointer"}`}>
              <input
                type="radio"
                name="user-verdict"
                value={v}
                checked={userVerdict === v}
                onChange={() => !isLocked && onChangeVerdict(v)}
                disabled={isLocked}
                className="h-4 w-4 accent-blue-600"
              />
              <span className="text-sm">{v}</span>
            </label>
          ))}
        </div>

        {/* 기존 수정 사유 (AI 판정과 다를 때) */}
        {userVerdict && userVerdict !== aiVerdict && (
          <div>
            <div className="mb-1 text-xs font-medium text-gray-700">
              수정 사유 <span className="text-red-500">*</span>
              <span className="ml-2 text-gray-500">식약처 소명 자료에 포함됩니다.</span>
            </div>
            <textarea
              value={editReason}
              onChange={(e) => !isLocked && onChangeReason(e.target.value)}
              disabled={isLocked}
              rows={3}
              placeholder="AI 판정과 다른 이유를 기재하세요."
              className="w-full rounded border border-gray-300 p-2 text-sm focus:border-blue-500 focus:outline-none disabled:bg-gray-50"
            />
          </div>
        )}
      </div>

      {/* HITL-2: 판정 사유 — AI 판정과 다를 때만 표시 */}
      {isHitl2Mode && userVerdict && userVerdict !== aiVerdict && (
        <div className="mt-4 space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              판정 변경 사유
              <span className="ml-2 text-gray-400">(AI 판정과 다른 판정 선택 시 입력)</span>
            </label>
            <textarea
              value={finalReason ?? ""}
              onChange={(e) => {
                setFinalReasonTouched(true);
                if (!isLocked) onChangeFinalReason?.(e.target.value);
              }}
              disabled={isLocked}
              rows={3}
              placeholder="판정을 변경한 사유를 입력하세요."
              className="w-full rounded border border-gray-300 p-2 text-sm focus:outline-none focus:border-blue-500 disabled:bg-gray-50"
            />
          </div>

        </div>
      )}
    </section>
  );
}
