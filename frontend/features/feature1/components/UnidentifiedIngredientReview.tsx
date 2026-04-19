"use client";

/**
 * HITL-1: 미확인 원재료 검토 컴포넌트
 *
 * 참조: 계획/f1 재설계 계획/05_HITL_플로우_설계.md §4-2
 * - 미확인 원재료 + API 조회 결과 없음 표시
 * - 행 단위 액션: 허용 / 금지 / 삭제 / 대체명 입력
 * - onChange 로 부모에 IngredientDecision[] 전달
 */

import { useState, useEffect } from "react";
import { CheckCircle2, XCircle, Trash2, RefreshCw, HelpCircle } from "lucide-react";
import type { IngredientDecision } from "@/types/pipeline";

export interface UnidentifiedIngredient {
  name: string;
  /** F1 Step B/C 에서 API 조회 시도한 키워드 */
  searched_as?: string | null;
  /** 조회 실패 이유 (예: "NOT_FOUND", "TIMEOUT") */
  lookup_error?: string | null;
}

export interface UnidentifiedIngredientReviewProps {
  caseId: string;
  ingredients: readonly UnidentifiedIngredient[];
  /** HITL-1 decisions 의 ingredient_decisions 에 병합될 결과 */
  onChange: (decisions: readonly IngredientDecision[]) => void;
  disabled?: boolean;
}

type RowAction = "allow" | "deny" | "skip" | null;

interface RowState {
  action: RowAction;
  alternativeName: string;
  note: string;
}

const ACTION_LABEL: Record<NonNullable<RowAction>, string> = {
  allow: "허용",
  deny: "금지",
  skip: "대체명 재조회",
};

const LOOKUP_ERROR_LABEL: Record<string, string> = {
  NOT_FOUND: "조회 결과 없음",
  TIMEOUT: "API 타임아웃",
  PARSE_ERROR: "파싱 오류",
};

export default function UnidentifiedIngredientReview({
  caseId: _caseId,
  ingredients,
  onChange,
  disabled = false,
}: UnidentifiedIngredientReviewProps) {
  const [rows, setRows] = useState<Record<string, RowState>>(() => {
    const init: Record<string, RowState> = {};
    for (const ing of ingredients) {
      init[ing.name] = { action: null, alternativeName: "", note: "" };
    }
    return init;
  });

  // ingredients 변경 시 신규 항목 초기화
  useEffect(() => {
    setRows((prev) => {
      const next = { ...prev };
      for (const ing of ingredients) {
        if (!(ing.name in next)) {
          next[ing.name] = { action: null, alternativeName: "", note: "" };
        }
      }
      return next;
    });
  }, [ingredients]);

  // 상태 변경 시 부모 통보
  useEffect(() => {
    const decisions: IngredientDecision[] = [];
    for (const [name, row] of Object.entries(rows)) {
      if (row.action !== null) {
        decisions.push({
          name,
          decision: row.action,
          alternative_name: row.action === "skip" && row.alternativeName.trim()
            ? row.alternativeName.trim()
            : null,
          note: row.note.trim() || null,
        });
      }
    }
    onChange(decisions);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows]);

  const updateRow = (name: string, patch: Partial<RowState>) => {
    setRows((prev) => ({
      ...prev,
      [name]: { ...prev[name], ...patch },
    }));
  };

  const completedCount = Object.values(rows).filter((r) => r.action !== null).length;
  const total = ingredients.length;

  if (total === 0) {
    return (
      <section
        data-testid="unidentified-ingredient-review"
        className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-500"
      >
        미확인 원재료가 없습니다.
      </section>
    );
  }

  return (
    <section
      data-testid="unidentified-ingredient-review"
      className="space-y-3 rounded-lg border border-gray-200 bg-white p-4"
    >
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-gray-900">미확인 원재료 검토</h3>
          <span
            data-testid="unidentified-progress"
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${
              completedCount === total
                ? "bg-green-100 text-green-700"
                : "bg-gray-100 text-gray-600"
            }`}
          >
            {completedCount}/{total}
          </span>
        </div>
      </div>

      <p className="text-xs text-gray-500">
        DB 및 API 조회에서 확인되지 않은 원재료입니다. 각 항목에 대해 허용·금지·대체명 재조회 중 하나를 선택하세요.
      </p>

      {/* 진행률 바 */}
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-200">
        <div
          className="h-full rounded-full bg-blue-500 transition-all"
          style={{ width: `${total > 0 ? (completedCount / total) * 100 : 0}%` }}
        />
      </div>

      {/* 행 리스트 */}
      <div className="space-y-3">
        {ingredients.map((ing) => {
          const row = rows[ing.name] ?? { action: null, alternativeName: "", note: "" };
          const errorLabel =
            ing.lookup_error
              ? (LOOKUP_ERROR_LABEL[ing.lookup_error] ?? ing.lookup_error)
              : "확인 결과 없음";

          return (
            <div
              key={ing.name}
              data-testid={`unidentified-row-${ing.name}`}
              className={`rounded-lg border p-4 ${
                row.action !== null
                  ? "border-gray-200 bg-gray-50"
                  : "border-amber-200 bg-amber-50"
              }`}
            >
              <div className="mb-3 flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <HelpCircle className="h-4 w-4 text-amber-500" />
                    <span className="font-medium text-gray-800">{ing.name}</span>
                  </div>
                  {ing.searched_as && ing.searched_as !== ing.name && (
                    <div className="mt-0.5 text-[11px] text-gray-500">
                      조회 키워드: <code className="rounded bg-gray-100 px-1">{ing.searched_as}</code>
                    </div>
                  )}
                  <div className="mt-0.5 text-[11px] text-amber-700">
                    {errorLabel}
                  </div>
                </div>

                {/* 액션 결과 배지 */}
                {row.action && (
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
                      row.action === "allow"
                        ? "bg-green-100 text-green-700"
                        : row.action === "deny"
                          ? "bg-red-100 text-red-700"
                          : "bg-blue-100 text-blue-700"
                    }`}
                  >
                    {ACTION_LABEL[row.action]}
                  </span>
                )}
              </div>

              {/* 액션 버튼 3개 */}
              <div className="mb-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => updateRow(ing.name, { action: "allow" })}
                  disabled={disabled}
                  data-testid={`action-allow-${ing.name}`}
                  className={`flex items-center gap-1.5 rounded border px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                    row.action === "allow"
                      ? "border-green-500 bg-green-500 text-white"
                      : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                  }`}
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  허용
                </button>

                <button
                  type="button"
                  onClick={() => updateRow(ing.name, { action: "deny" })}
                  disabled={disabled}
                  data-testid={`action-deny-${ing.name}`}
                  className={`flex items-center gap-1.5 rounded border px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                    row.action === "deny"
                      ? "border-red-500 bg-red-500 text-white"
                      : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                  }`}
                >
                  <XCircle className="h-3.5 w-3.5" />
                  금지
                </button>

                <button
                  type="button"
                  onClick={() => updateRow(ing.name, { action: "skip" })}
                  disabled={disabled}
                  data-testid={`action-skip-${ing.name}`}
                  className={`flex items-center gap-1.5 rounded border px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                    row.action === "skip"
                      ? "border-blue-500 bg-blue-500 text-white"
                      : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                  }`}
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  대체명 재조회
                </button>

                {/* 초기화 */}
                {row.action !== null && !disabled && (
                  <button
                    type="button"
                    onClick={() => updateRow(ing.name, { action: null, alternativeName: "", note: "" })}
                    className="flex items-center gap-1 rounded border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-400 hover:bg-gray-50"
                    aria-label={`${ing.name} 선택 초기화`}
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                )}
              </div>

              {/* 대체명 입력 (skip 선택 시) */}
              {row.action === "skip" && (
                <div className="mb-2">
                  <label className="mb-1 block text-[11px] font-medium text-gray-600">
                    대체 검색명 (재조회 키워드)
                  </label>
                  <input
                    type="text"
                    value={row.alternativeName}
                    onChange={(e) => updateRow(ing.name, { alternativeName: e.target.value })}
                    disabled={disabled}
                    placeholder="예) 소르빈산칼륨, E202"
                    className="w-full rounded border border-gray-300 px-2 py-1.5 text-xs focus:border-blue-500 focus:outline-none disabled:bg-gray-50"
                  />
                </div>
              )}

              {/* 메모 */}
              {row.action !== null && (
                <div>
                  <label className="mb-1 block text-[11px] font-medium text-gray-600">
                    담당자 메모 (선택)
                  </label>
                  <textarea
                    value={row.note}
                    onChange={(e) => updateRow(ing.name, { note: e.target.value })}
                    disabled={disabled}
                    rows={1}
                    placeholder="판단 근거나 참고 사항을 입력하세요."
                    className="w-full rounded border border-gray-300 px-2 py-1.5 text-xs focus:border-blue-500 focus:outline-none disabled:bg-gray-50"
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
