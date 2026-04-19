"use client";

/**
 * HITL-1: 조건부 원재료(restricted) 사용 조건 평가 패널
 *
 * 참조: 계획/f1 재설계 계획/05_HITL_플로우_설계.md §4-2
 * - 조건부 원재료 카드 리스트
 * - 각 카드: restrictionCondition 표시 + "조건 부합" / "조건 불충족" 라디오 + 사유 textarea
 * - onChange 로 부모에 resolutions 전달
 */

import { useState, useEffect } from "react";
import { CheckCircle2, XCircle, Info } from "lucide-react";

export interface ConditionalIngredient {
  name: string;
  /** data.go.kr CHRTR_INFO_CONT 원문 (사용 조건 텍스트) */
  restrictionCondition: string;
  /** data.go.kr EDIBLE_USE_CONT (사용 가능 부위) */
  ediblePartHint?: string;
}

export interface ConditionalResolution {
  ingredientName: string;
  meetsCondition: boolean;
  reasoning: string;
}

export interface ConditionalResolutionPanelProps {
  caseId: string;
  ingredients: readonly ConditionalIngredient[];
  /** HITL-1 decisions 의 conditional_resolutions 에 병합될 결과 */
  onChange: (resolutions: readonly ConditionalResolution[]) => void;
  disabled?: boolean;
}

interface CardState {
  meetsCondition: boolean | null;
  reasoning: string;
}

export default function ConditionalResolutionPanel({
  caseId: _caseId,
  ingredients,
  onChange,
  disabled = false,
}: ConditionalResolutionPanelProps) {
  const [states, setStates] = useState<Record<string, CardState>>(() => {
    const init: Record<string, CardState> = {};
    for (const ing of ingredients) {
      init[ing.name] = { meetsCondition: null, reasoning: "" };
    }
    return init;
  });

  // ingredients 변경 시 신규 항목 초기화 (기존 값 유지)
  useEffect(() => {
    setStates((prev) => {
      const next = { ...prev };
      for (const ing of ingredients) {
        if (!(ing.name in next)) {
          next[ing.name] = { meetsCondition: null, reasoning: "" };
        }
      }
      return next;
    });
  }, [ingredients]);

  // 상태 변경 시 부모에 통보
  useEffect(() => {
    const resolutions: ConditionalResolution[] = [];
    for (const [name, s] of Object.entries(states)) {
      if (s.meetsCondition !== null) {
        resolutions.push({
          ingredientName: name,
          meetsCondition: s.meetsCondition,
          reasoning: s.reasoning,
        });
      }
    }
    onChange(resolutions);
    // onChange 레퍼런스 변동 무시 (부모 리렌더 사이클 방지)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [states]);

  const updateCard = (name: string, patch: Partial<CardState>) => {
    setStates((prev) => ({
      ...prev,
      [name]: { ...prev[name], ...patch },
    }));
  };

  if (ingredients.length === 0) {
    return (
      <section
        data-testid="conditional-resolution-panel"
        className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-500"
      >
        조건부 원재료가 없습니다.
      </section>
    );
  }

  return (
    <section
      data-testid="conditional-resolution-panel"
      className="space-y-3 rounded-lg border border-gray-200 bg-white p-4"
    >
      <h3 className="font-semibold text-gray-900">
        조건부 원재료 평가
        <span className="ml-2 text-sm font-normal text-gray-500">
          ({ingredients.length}건)
        </span>
      </h3>
      <p className="text-xs text-gray-500">
        각 원재료의 사용 조건이 현 제품에 해당하는지 판단하세요.
      </p>

      <div className="space-y-4">
        {ingredients.map((ing) => {
          const state = states[ing.name] ?? {
            meetsCondition: null,
            reasoning: "",
          };

          return (
            <div
              key={ing.name}
              data-testid={`conditional-card-${ing.name}`}
              className="rounded-lg border border-gray-200 bg-gray-50 p-4"
            >
              {/* 원재료명 */}
              <div className="mb-2 font-medium text-gray-800">{ing.name}</div>

              {/* 사용 조건 텍스트 */}
              <div className="mb-2 rounded border border-amber-200 bg-amber-50 p-2.5 text-xs text-amber-800">
                <div className="mb-0.5 flex items-center gap-1 font-medium">
                  <Info className="h-3.5 w-3.5" />
                  사용 조건 (법령 원문)
                </div>
                {ing.restrictionCondition}
              </div>

              {/* 사용 가능 부위 힌트 */}
              {ing.ediblePartHint && (
                <div className="mb-2 text-[11px] text-gray-500">
                  <span className="font-medium">사용 가능 부위:</span> {ing.ediblePartHint}
                </div>
              )}

              {/* 조건 부합 여부 라디오 */}
              <div className="mb-2 flex gap-4">
                <label
                  className={`flex cursor-pointer items-center gap-2 rounded border px-3 py-2 text-sm transition-colors ${
                    state.meetsCondition === true
                      ? "border-green-500 bg-green-50 text-green-700"
                      : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50"
                  } ${disabled ? "cursor-not-allowed opacity-60" : ""}`}
                >
                  <input
                    type="radio"
                    name={`condition-${ing.name}`}
                    value="meets"
                    checked={state.meetsCondition === true}
                    onChange={() => updateCard(ing.name, { meetsCondition: true })}
                    disabled={disabled}
                    className="sr-only"
                  />
                  <CheckCircle2 className="h-4 w-4" />
                  조건 부합 (허용)
                </label>

                <label
                  className={`flex cursor-pointer items-center gap-2 rounded border px-3 py-2 text-sm transition-colors ${
                    state.meetsCondition === false
                      ? "border-red-500 bg-red-50 text-red-700"
                      : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50"
                  } ${disabled ? "cursor-not-allowed opacity-60" : ""}`}
                >
                  <input
                    type="radio"
                    name={`condition-${ing.name}`}
                    value="not-meets"
                    checked={state.meetsCondition === false}
                    onChange={() => updateCard(ing.name, { meetsCondition: false })}
                    disabled={disabled}
                    className="sr-only"
                  />
                  <XCircle className="h-4 w-4" />
                  조건 불충족 (금지)
                </label>
              </div>

              {/* 사유 textarea */}
              {state.meetsCondition !== null && (
                <div>
                  <label className="mb-1 block text-xs font-medium text-gray-700">
                    판단 사유 <span className="text-red-500">*</span>
                  </label>
                  <textarea
                    value={state.reasoning}
                    onChange={(e) => updateCard(ing.name, { reasoning: e.target.value })}
                    disabled={disabled}
                    rows={2}
                    placeholder="조건 부합/불충족 판단 근거를 입력하세요."
                    className="w-full rounded border border-gray-300 p-2 text-xs focus:border-blue-500 focus:outline-none disabled:bg-gray-50"
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
