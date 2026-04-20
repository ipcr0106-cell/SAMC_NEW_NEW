"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Plus, Edit2, Trash2, ChevronDown, ChevronRight } from "lucide-react";
import type { TableDiff } from "./api";

type Row = Record<string, unknown>;
type Kind = "added" | "modified" | "deleted";

interface RowState {
  kind: Kind;
  key: string | number;
  included: boolean;  // 체크박스 상태 (false 면 apply 에서 제외)
  edited: Row;        // 편집된 값 (added/modified 인 경우 사용)
  original?: Row;     // 이전 DB 상태 (modified 비교용)
}

interface DiffPreviewTableProps {
  tableName: string;
  diff: TableDiff;
  onEditedRowsChange: (rows: Row[]) => void;
}

/**
 * 편집 가능한 diff 테이블.
 * - 체크박스로 변경 항목 개별 ON/OFF
 * - 인라인 입력으로 값 수정
 * - 상위 컴포넌트에 최종 적용될 rows 전달
 */
export function DiffPreviewTable({
  tableName,
  diff,
  onEditedRowsChange,
}: DiffPreviewTableProps) {
  const pk = diff.pk_column;

  // 초기 RowState 구성
  const initialStates = useMemo<RowState[]>(() => {
    const oldMap = new Map<string | number, Row>();
    for (const r of diff.old_rows) {
      const k = r[pk] as string | number;
      if (k !== undefined && k !== null) oldMap.set(k, r);
    }
    const newMap = new Map<string | number, Row>();
    for (const r of diff.new_rows) {
      const k = r[pk] as string | number;
      if (k !== undefined && k !== null) newMap.set(k, r);
    }

    const states: RowState[] = [];

    // added
    for (const k of diff.diff.added_keys) {
      const r = newMap.get(k);
      if (r) states.push({ kind: "added", key: k, included: true, edited: { ...r } });
    }
    // modified
    for (const k of diff.diff.modified_keys) {
      const r = newMap.get(k);
      const o = oldMap.get(k);
      if (r) {
        states.push({
          kind: "modified",
          key: k,
          included: true,
          edited: { ...r },
          original: o ? { ...o } : undefined,
        });
      }
    }
    // deleted
    for (const k of diff.diff.deleted_keys) {
      const r = oldMap.get(k);
      if (r) states.push({ kind: "deleted", key: k, included: true, edited: { ...r } });
    }
    return states;
  }, [diff, pk]);

  const [states, setStates] = useState<RowState[]>(initialStates);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    added: true,
    modified: true,
    deleted: true,
  });

  // onEditedRowsChange 의 최신 참조를 ref 로 보관 → memo 무효화 방지
  // (부모에서 인라인 콜백 넘겨도 영향 없음)
  const onEditedRowsChangeRef = useRef(onEditedRowsChange);
  useEffect(() => {
    onEditedRowsChangeRef.current = onEditedRowsChange;
  }, [onEditedRowsChange]);

  const emitEditedRows = useMemo(
    () =>
      (list: RowState[]) => {
        const byKey = new Map<string | number, Row>();
        for (const r of diff.old_rows) {
          const k = r[pk] as string | number;
          if (k !== undefined && k !== null) byKey.set(k, { ...r });
        }
        for (const s of list) {
          if (!s.included) continue;
          if (s.kind === "added" || s.kind === "modified") {
            byKey.set(s.key, { ...s.edited });
          } else if (s.kind === "deleted") {
            byKey.delete(s.key);
          }
        }
        onEditedRowsChangeRef.current(Array.from(byKey.values()));
      },
    [diff.old_rows, pk],  // onEditedRowsChange 제거 (ref 로 우회)
  );

  // 통합된 useEffect: initialStates 가 바뀔 때마다 (마운트 포함) states 리셋 + 즉시 emit
  // 이전 구조 (mount-only + initialStates effect 분리) 에서 "두 번째 파일 업로드 시 초기 emit 누락" 버그 수정.
  useEffect(() => {
    setStates(initialStates);
    emitEditedRows(initialStates);
  }, [initialStates, emitEditedRows]);

  // debounce 헬퍼 + 언마운트 cleanup
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    return () => {
      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
        debounceTimer.current = null;
      }
    };
  }, []);

  const debouncedEmit = (list: RowState[]) => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => emitEditedRows(list), 120);
  };

  // 체크박스 토글 — 즉시 emit (debounce 불필요)
  const toggleIncluded = (idx: number) => {
    setStates((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], included: !next[idx].included };
      emitEditedRows(next);
      return next;
    });
  };

  // 인라인 편집 — debounce
  const updateField = (idx: number, field: string, value: unknown) => {
    setStates((prev) => {
      const next = [...prev];
      next[idx] = {
        ...next[idx],
        edited: { ...next[idx].edited, [field]: value },
      };
      debouncedEmit(next);
      return next;
    });
  };

  const byKind: Record<Kind, { idx: number; state: RowState }[]> = {
    added: [],
    modified: [],
    deleted: [],
  };
  states.forEach((s, idx) => byKind[s.kind].push({ idx, state: s }));

  const renderSection = (kind: Kind, label: string, color: string, Icon: typeof Plus) => {
    const entries = byKind[kind];
    if (entries.length === 0) return null;
    const isExpanded = expanded[kind];

    return (
      <div className="border border-slate-200 rounded-lg overflow-hidden mb-3">
        <button
          onClick={() => setExpanded((p) => ({ ...p, [kind]: !p[kind] }))}
          className="w-full flex items-center gap-2 px-4 py-3 bg-slate-50 hover:bg-slate-100 transition-colors"
        >
          {isExpanded ? (
            <ChevronDown size={16} className="text-slate-500" />
          ) : (
            <ChevronRight size={16} className="text-slate-500" />
          )}
          <Icon size={14} className={color} />
          <span className="text-[14px] font-semibold text-slate-800">
            {label} ({entries.length}건)
          </span>
        </button>

        {isExpanded && (
          <div className="divide-y divide-slate-100">
            {entries.map(({ idx, state }) => (
              <RowEditor
                key={`${kind}-${state.key}`}
                state={state}
                onToggle={() => toggleIncluded(idx)}
                onEdit={(field, value) => updateField(idx, field, value)}
              />
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div>
      <div className="mb-3 text-[13px] text-slate-500">
        <span className="font-mono text-slate-700">{tableName}</span>
        {" · 체크를 해제하면 해당 변경사항이 적용되지 않습니다. 값은 직접 수정 가능합니다."}
      </div>
      {renderSection("added",    "추가",  "text-emerald-600", Plus)}
      {renderSection("modified", "수정",  "text-blue-600",    Edit2)}
      {renderSection("deleted",  "삭제",  "text-rose-600",    Trash2)}
      {states.length === 0 && (
        <div className="border border-dashed border-slate-300 rounded-lg p-6 text-center text-[14px] text-slate-500">
          변경사항이 없습니다. (파싱 결과가 현재 DB 와 동일)
        </div>
      )}
    </div>
  );
}

// ── 개별 행 편집기 ──────────────────────────

interface RowEditorProps {
  state: RowState;
  onToggle: () => void;
  onEdit: (field: string, value: unknown) => void;
}

function RowEditor({ state, onToggle, onEdit }: RowEditorProps) {
  const [showAll, setShowAll] = useState(false);
  const row = state.edited;
  const original = state.original;
  const fields = Object.keys(row);
  const visibleFields = showAll ? fields : fields.slice(0, 6);

  const bgByKind =
    state.kind === "added"
      ? "bg-emerald-50/50"
      : state.kind === "modified"
      ? "bg-blue-50/50"
      : "bg-rose-50/50";

  return (
    <div className={`px-4 py-3 ${state.included ? "" : "opacity-40"}`}>
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          checked={state.included}
          onChange={onToggle}
          className="mt-1 w-4 h-4 accent-slate-900"
        />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[12px] text-slate-500">
              <span className="font-mono">{String(state.key)}</span>
            </span>
          </div>

          <div className={`rounded-md ${bgByKind} p-3 space-y-1.5`}>
            {visibleFields.map((field) => {
              const val = row[field];
              const origVal = original?.[field];
              const changed =
                state.kind === "modified" &&
                origVal !== undefined &&
                JSON.stringify(origVal) !== JSON.stringify(val);
              const disabled = state.kind === "deleted" || !state.included;

              return (
                <div key={field} className="flex items-start gap-2 text-[12.5px]">
                  <span className="w-36 flex-shrink-0 text-slate-500 font-mono pt-1">
                    {field}
                  </span>
                  <div className="flex-1 min-w-0">
                    <FieldEditor
                      fieldName={field}
                      value={val}
                      disabled={disabled}
                      changed={changed}
                      onChange={(v) => onEdit(field, v)}
                    />
                    {changed && origVal !== undefined && (
                      <div className="mt-1 text-[11px] text-slate-500">
                        이전:{" "}
                        <span className="font-mono text-slate-600">
                          {typeof origVal === "object"
                            ? JSON.stringify(origVal)
                            : String(origVal)}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {fields.length > 6 && (
              <button
                onClick={() => setShowAll(!showAll)}
                className="text-[12px] text-slate-500 hover:text-slate-700 mt-1"
              >
                {showAll
                  ? "접기"
                  : `+ ${fields.length - 6}개 필드 더 보기`}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── 타입 인식 필드 에디터 ─────────────────

interface FieldEditorProps {
  fieldName: string;
  value: unknown;
  disabled: boolean;
  changed: boolean;
  onChange: (v: unknown) => void;
}

function FieldEditor({ fieldName, value, disabled, changed, onChange }: FieldEditorProps) {
  const borderClass = changed ? "border-blue-300" : "border-slate-200";
  const commonClass = `w-full px-2 py-1 rounded border ${borderClass} bg-white text-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-400 disabled:opacity-60 disabled:cursor-not-allowed`;

  // Boolean → checkbox
  if (typeof value === "boolean") {
    return (
      <label className="flex items-center gap-2 text-[12.5px] text-slate-700">
        <input
          type="checkbox"
          checked={value}
          onChange={(e) => onChange(e.target.checked)}
          disabled={disabled}
          className="w-4 h-4 accent-slate-900"
        />
        <span className="text-slate-500">{value ? "참 (true)" : "거짓 (false)"}</span>
      </label>
    );
  }

  // Number → number input
  if (typeof value === "number") {
    return (
      <input
        type="number"
        value={Number.isFinite(value) ? value : ""}
        onChange={(e) => {
          const raw = e.target.value;
          if (raw === "") {
            onChange(null);
            return;
          }
          const n = Number(raw);
          if (!Number.isNaN(n)) onChange(n);
        }}
        disabled={disabled}
        className={commonClass}
      />
    );
  }

  // Null → 빈 텍스트 input (사용자가 값 입력하면 문자열로 저장)
  if (value === null || value === undefined) {
    return (
      <input
        type="text"
        value=""
        placeholder="(비어있음 — 필요시 값 입력)"
        onChange={(e) => {
          const v = e.target.value;
          onChange(v === "" ? null : v);
        }}
        disabled={disabled}
        className={`${commonClass} placeholder:text-slate-400`}
      />
    );
  }

  // Array / Object → JSON 편집 (readonly — 파일로 편집 권장)
  if (typeof value === "object") {
    return (
      <div className="px-2 py-1 rounded bg-slate-100 text-slate-600 font-mono text-[11.5px] break-all">
        {JSON.stringify(value)}
        <div className="text-[10.5px] text-slate-400 mt-1">
          (복합 값 — 인라인 편집 불가. 원본 파일을 수정해 재업로드 하세요)
        </div>
      </div>
    );
  }

  // String → text (기본)
  return (
    <input
      type="text"
      value={String(value)}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className={commonClass}
    />
  );
}
