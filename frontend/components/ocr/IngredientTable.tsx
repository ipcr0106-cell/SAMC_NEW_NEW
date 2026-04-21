"use client";

import { useState } from "react";
import { FlaskConical, Plus, Trash2 } from "lucide-react";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
import Badge from "@/components/ui/Badge";

export interface IngredientCodeCandidate {
  code: string;
  name_ko: string;
  name_en: string;
  score: number;
  match_type: string;
}

export interface Ingredient {
  id: string;
  name: string;
  ratio: string;
  origin: string;
  insNumber: string;
  casNumber: string;
  /** 식약처 성분코드 (백엔드 자동 조회) */
  ingredientCode?: string;
  /** 성분코드 공식 명칭 */
  ingredientCodeName?: string;
  /** 성분코드 후보 목록 */
  ingredientCodeCandidates?: IngredientCodeCandidate[];
}

interface IngredientTableProps {
  ingredients: Ingredient[];
  onChange: (ingredients: Ingredient[]) => void;
}

export default function IngredientTable({
  ingredients,
  onChange,
}: IngredientTableProps) {
  const [hoveredRow, setHoveredRow] = useState<string | null>(null);
  const [openCandidateRow, setOpenCandidateRow] = useState<string | null>(null);

  const updateRow = (id: string, field: keyof Ingredient, value: string) => {
    onChange(
      ingredients.map((ing) =>
        ing.id === id ? { ...ing, [field]: value } : ing
      )
    );
  };

  const selectIngredientCode = (id: string, code: string, name: string) => {
    onChange(
      ingredients.map((ing) =>
        ing.id === id ? { ...ing, ingredientCode: code, ingredientCodeName: name } : ing
      )
    );
    setOpenCandidateRow(null);
  };

  const addRow = () => {
    const newId = `ing-${Date.now()}`;
    onChange([
      ...ingredients,
      { id: newId, name: "", ratio: "", origin: "", insNumber: "", casNumber: "", ingredientCode: "", ingredientCodeName: "" },
    ]);
  };

  const removeRow = (id: string) => {
    onChange(ingredients.filter((ing) => ing.id !== id));
  };

  const totalRatio = ingredients.reduce(
    (sum, ing) => sum + (parseFloat(ing.ratio) || 0),
    0
  );

  return (
    <Card padding="sm">
      {/* 헤더 */}
      <div className="flex items-center justify-between px-3 pt-3 pb-4">
        <div className="flex items-center gap-2.5">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-blue-50 text-blue-600">
            <FlaskConical size={16} />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900">원재료 목록</h3>
            <p className="text-xs text-slate-400 mt-0.5">
              OCR 파싱 결과를 확인하고 수정하세요
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge
            variant={
              Math.abs(totalRatio - 100) < 0.01 ? "green" : "amber"
            }
            size="sm"
          >
            합계 {totalRatio.toFixed(1)}%
          </Badge>
          <Badge variant="slate" size="sm">
            {ingredients.length}개 성분
          </Badge>
        </div>
      </div>

      {/* 테이블 */}
      <div className="overflow-x-auto" style={{ overflow: openCandidateRow ? "visible" : undefined }}>
        <table className="w-full">
          <thead>
            <tr className="border-y border-slate-100">
              <th className="w-8" />
              <th className="text-left text-xs font-medium text-slate-400 py-2.5 px-2">
                성분명
              </th>
              <th className="text-left text-xs font-medium text-slate-400 py-2.5 px-2 w-[90px]">
                배합비율(%)
              </th>
              <th className="text-left text-xs font-medium text-slate-400 py-2.5 px-2 w-[100px]">
                원산지
              </th>
              <th className="text-left text-xs font-medium text-slate-400 py-2.5 px-2 w-[100px]">
                INS 번호
              </th>
              <th className="text-left text-xs font-medium text-slate-400 py-2.5 px-2 w-[120px]">
                CAS 번호
              </th>
              <th className="text-left text-xs font-medium text-slate-400 py-2.5 px-2 w-[140px]">
                성분코드
              </th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {ingredients.map((ing, idx) => (
              <tr
                key={ing.id}
                onMouseEnter={() => setHoveredRow(ing.id)}
                onMouseLeave={() => setHoveredRow(null)}
                className={`group border-b border-slate-50 transition-colors ${
                  hoveredRow === ing.id ? "bg-slate-50/50" : ""
                }`}
              >
                <td className="text-center">
                  <span className="text-[10px] text-slate-300 font-mono">
                    {idx + 1}
                  </span>
                </td>
                <td className="px-1 py-0.5">
                  <Input
                    inline
                    value={ing.name}
                    onChange={(e) => updateRow(ing.id, "name", e.target.value)}
                    placeholder="성분명 입력"
                  />
                </td>
                <td className="px-1 py-0.5">
                  <Input
                    inline
                    value={ing.ratio}
                    onChange={(e) => updateRow(ing.id, "ratio", e.target.value)}
                    placeholder="0.00"
                    className="text-right font-mono"
                  />
                </td>
                <td className="px-1 py-0.5">
                  <Input
                    inline
                    value={ing.origin}
                    onChange={(e) => updateRow(ing.id, "origin", e.target.value)}
                    placeholder="국가"
                  />
                </td>
                <td className="px-1 py-0.5">
                  <Input
                    inline
                    value={ing.insNumber}
                    onChange={(e) =>
                      updateRow(ing.id, "insNumber", e.target.value)
                    }
                    placeholder="—"
                    className="font-mono"
                  />
                </td>
                <td className="px-1 py-0.5">
                  <Input
                    inline
                    value={ing.casNumber}
                    onChange={(e) =>
                      updateRow(ing.id, "casNumber", e.target.value)
                    }
                    placeholder="—"
                    className="font-mono"
                  />
                </td>
                <td className="px-2 py-0.5 relative">
                  {ing.ingredientCode ? (
                    <button
                      type="button"
                      onClick={() => {
                        const candidates = ing.ingredientCodeCandidates ?? [];
                        if (candidates.length > 1) {
                          setOpenCandidateRow(openCandidateRow === ing.id ? null : ing.id);
                        }
                      }}
                      className={`flex flex-col gap-0.5 text-left w-full ${
                        (ing.ingredientCodeCandidates?.length ?? 0) > 1 ? "cursor-pointer hover:bg-blue-50 rounded p-0.5 -m-0.5" : "cursor-default"
                      }`}
                    >
                      <span className="inline-block px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 text-[10px] font-mono font-semibold leading-none">
                        {ing.ingredientCode}
                        {(ing.ingredientCodeCandidates?.length ?? 0) > 1 && (
                          <span className="ml-1 text-blue-400">&#9662;</span>
                        )}
                      </span>
                      {ing.ingredientCodeName && (
                        <span className="text-[10px] text-slate-500 leading-none truncate max-w-[120px]" title={ing.ingredientCodeName}>
                          {ing.ingredientCodeName}
                        </span>
                      )}
                    </button>
                  ) : (
                    <span className="text-[10px] text-slate-300">—</span>
                  )}
                  {/* 후보 드롭다운 */}
                  {openCandidateRow === ing.id && ing.ingredientCodeCandidates && ing.ingredientCodeCandidates.length > 0 && (
                    <>
                      {/* 배경 오버레이 — 클릭 시 닫기 */}
                      <div className="fixed inset-0 z-40" onClick={() => setOpenCandidateRow(null)} />
                      <div className="absolute z-50 right-0 mt-1 w-80 bg-white border border-slate-200 rounded-lg shadow-xl py-1">
                        <div className="px-3 py-2 text-xs text-slate-500 font-medium border-b border-slate-100">
                          유사 성분코드 ({ing.ingredientCodeCandidates.length}건) — 클릭하여 선택
                        </div>
                        {ing.ingredientCodeCandidates.map((c) => (
                          <button
                            key={c.code}
                            type="button"
                            onClick={() => selectIngredientCode(ing.id, c.code, c.name_ko)}
                            className={`w-full text-left px-3 py-2 hover:bg-blue-50 flex items-center gap-2 transition-colors ${
                              c.code === ing.ingredientCode ? "bg-blue-50 border-l-2 border-blue-500" : ""
                            }`}
                          >
                            <span className="px-1.5 py-0.5 rounded bg-slate-100 text-[11px] font-mono font-semibold text-slate-700 shrink-0">
                              {c.code}
                            </span>
                            <div className="flex flex-col flex-1 min-w-0">
                              <span className="text-xs text-slate-800 truncate">
                                {c.name_ko || "—"}
                              </span>
                              {c.name_en && (
                                <span className="text-[10px] text-slate-400 truncate">
                                  {c.name_en}
                                </span>
                              )}
                            </div>
                            <span className="text-[10px] text-slate-400 shrink-0">
                              {(c.score * 100).toFixed(0)}%
                            </span>
                            {c.code === ing.ingredientCode && (
                              <span className="text-blue-600 text-sm shrink-0">&#10003;</span>
                            )}
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </td>
                <td className="text-center">
                  <button
                    type="button"
                    onClick={() => removeRow(ing.id)}
                    className="opacity-0 group-hover:opacity-100 text-slate-300 hover:text-red-500 transition-all p-1 rounded-lg hover:bg-red-50"
                  >
                    <Trash2 size={14} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 행 추가 버튼 */}
      <div className="px-3 py-3">
        <Button
          variant="ghost"
          size="sm"
          icon={<Plus size={14} />}
          onClick={addRow}
          className="w-full border border-dashed border-slate-200 hover:border-blue-300 hover:text-blue-600 hover:bg-blue-50/50"
        >
          성분 추가
        </Button>
      </div>
    </Card>
  );
}
