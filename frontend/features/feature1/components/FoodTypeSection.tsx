/**
 * FoodTypeSection — F2 식품유형 3단계 분류 표시 섹션
 *
 * F1 ImportCheckPage 내에 삽입하여 F2 결과를 F1 페이지에서 바로 확인·수정할 수 있도록 함.
 * /f2 페이지 접속 시 /f1#food-type 으로 리다이렉트되므로 이 anchor가 진입점이 됨.
 *
 * f1f2 병합 통합 (samcbc Sub-phase 2 대응).
 */

import Badge from "@/components/ui/Badge";
import type { FoodTypeHierarchy } from "@/types/pipeline";

interface FoodTypeSectionProps {
  hierarchy: FoodTypeHierarchy | null;
  onEdit: () => void;
  isEditable: boolean;
}

export default function FoodTypeSection({ hierarchy, onEdit, isEditable }: FoodTypeSectionProps) {
  return (
    <section
      id="food-type"
      className="rounded-lg border border-slate-200 bg-white p-4 space-y-4"
    >
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[11px] font-bold text-blue-600 uppercase tracking-wider">F2</div>
          <h2 className="text-base font-semibold text-slate-900">식품유형 분류</h2>
        </div>
        {isEditable && (
          <button
            type="button"
            onClick={onEdit}
            className="text-xs text-blue-600 hover:underline border border-blue-200 rounded px-2 py-1"
          >
            수정
          </button>
        )}
      </div>

      {/* 결과 없음 */}
      {!hierarchy && (
        <p className="text-sm text-slate-500">
          F2 식품유형 분류 결과가 없습니다. F2 분석을 먼저 실행하세요.
        </p>
      )}

      {/* 결과 있음 */}
      {hierarchy && (
        <div className="space-y-3">
          {/* 주류 여부 */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">주류 여부</span>
            <Badge variant={hierarchy.is_alcohol ? "red" : "blue"} size="sm">
              {hierarchy.is_alcohol ? "주류" : "일반식품"}
            </Badge>
          </div>

          <div className="border-t border-slate-100" />

          {/* 3단계 분류 */}
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
              식품유형 3단계 분류
            </p>
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: "대분류", value: hierarchy.category_name },
                { label: "중분류", value: hierarchy.subcategory_name },
                { label: "소분류", value: hierarchy.food_type },
              ].map((c, i) => (
                <div
                  key={i}
                  className="rounded-lg border border-slate-200 p-3 text-center bg-slate-50"
                >
                  <div className="text-[11px] text-slate-500 mb-1">{c.label}</div>
                  <div className="text-sm font-bold text-slate-900">{c.value || "—"}</div>
                </div>
              ))}
            </div>
          </div>

          {/* 법령 근거 */}
          {(hierarchy.law_ref || hierarchy.reason) && (
            <>
              <div className="border-t border-slate-100" />
              <div className="rounded-lg bg-blue-50 border border-blue-100 p-3 space-y-1">
                {hierarchy.law_ref && (
                  <p className="text-sm text-slate-700">
                    근거 법령: <span className="font-semibold">{hierarchy.law_ref}</span>
                  </p>
                )}
                {hierarchy.reason && (
                  <p className="text-sm text-slate-700 leading-relaxed">{hierarchy.reason}</p>
                )}
              </div>
            </>
          )}

          {/* category_no */}
          {hierarchy.category_no && (
            <p className="text-xs text-slate-400">분류번호: {hierarchy.category_no}</p>
          )}
        </div>
      )}
    </section>
  );
}
