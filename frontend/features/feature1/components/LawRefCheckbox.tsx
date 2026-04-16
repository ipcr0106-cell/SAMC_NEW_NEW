/**
 * 판정 근거로 채택할 법령 체크박스 목록.
 * 사용자가 선택한 법령만 최종 결과에 포함됨 (담당자 재량).
 */

"use client";

interface LawRef {
  law_source: string;
  law_article?: string | null;
}

interface Props {
  lawRefs: LawRef[];
  selected: Set<string>;
  onToggle: (lawSource: string) => void;
}

export default function LawRefCheckbox({ lawRefs, selected, onToggle }: Props) {
  if (!lawRefs || lawRefs.length === 0) {
    return (
      <section className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-500">
        참조 법령이 없습니다.
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="mb-3 font-semibold text-gray-800">판정 근거 법령</h3>
      <p className="mb-3 text-xs text-gray-500">
        AI가 참조한 법령 중, 담당자가 판정 근거로 채택할 항목에 체크하세요.
      </p>
      <div className="space-y-2">
        {lawRefs.map((ref) => {
          const key = ref.law_source;
          const label = ref.law_article
            ? `${ref.law_source} · ${ref.law_article}`
            : ref.law_source;
          return (
            <label
              key={key}
              className="flex cursor-pointer items-center gap-2 rounded border border-gray-100 p-2 hover:bg-gray-50"
            >
              <input
                type="checkbox"
                checked={selected.has(key)}
                onChange={() => onToggle(key)}
                className="h-4 w-4 accent-blue-600"
              />
              <span className="text-sm text-gray-700">{label}</span>
            </label>
          );
        })}
      </div>
    </section>
  );
}
