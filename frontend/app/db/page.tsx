"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  ChevronLeft,
  Database,
  Upload,
  FileText,
  Plus,
  Trash2,
  CheckCircle,
  RefreshCw,
  Loader2,
  AlertTriangle,
  Search,
  Shield,
  Edit2,
  X,
  Check,
  Filter,
  BookOpen,
  ChevronDown,
} from "lucide-react";
import { supabase } from "@/lib/supabase";
import Button from "@/components/ui/Button";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const ADMIN_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1")
  .replace("/api/v1", "");

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

type MainTab = "ingredients" | "law_upload" | "law_list";

type TableName =
  | "f1_allowed_ingredients"
  | "f1_additive_limits"
  | "f1_safety_standards"
  | "f1_forbidden_ingredients";

const TABLE_INFO: Record<
  TableName,
  { label: string; desc: string; columns: string[]; displayColumns: string[] }
> = {
  f1_allowed_ingredients: {
    label: "허용 성분",
    desc: "수입 허용 원재료 및 첨가물 목록",
    columns: [
      "name_ko", "name_en", "scientific_name", "ins_number",
      "cas_number", "allowed_status", "conditions", "law_source", "is_verified",
    ],
    displayColumns: ["name_ko", "name_en", "ins_number", "allowed_status", "law_source", "is_verified"],
  },
  f1_additive_limits: {
    label: "첨가물 기준",
    desc: "식품 유형별 첨가물 허용 기준치",
    columns: [
      "food_type", "additive_name", "ins_number", "max_ppm", "combined_group",
      "combined_max", "conversion_factor", "colorant_category", "condition_text",
      "regulation_ref", "is_verified",
    ],
    displayColumns: ["food_type", "additive_name", "max_ppm", "regulation_ref", "is_verified"],
  },
  f1_safety_standards: {
    label: "안전 기준",
    desc: "식품 유형별 안전성 기준",
    columns: [
      "food_type", "standard_type", "target_name", "max_limit",
      "regulation_ref", "condition_text", "is_verified",
    ],
    displayColumns: ["food_type", "standard_type", "target_name", "max_limit", "regulation_ref", "is_verified"],
  },
  f1_forbidden_ingredients: {
    label: "금지 성분",
    desc: "수입 금지 원재료 및 첨가물 목록",
    columns: ["name_ko", "name_en", "aliases", "category", "law_source", "reason", "is_verified"],
    displayColumns: ["name_ko", "name_en", "category", "law_source", "is_verified"],
  },
};

interface DbRow {
  id: string;
  is_verified?: boolean;
  created_by?: string;
  created_at?: string;
  [key: string]: unknown;
}

interface LawInfo {
  law_name: string;
  tier: string;
  description: string;
  features: string[];
}

interface RegisteredLaw {
  id: string;
  law_name: string;
  고시번호?: string;
  시행일?: string;
  법령_tier?: number;
  total_chunks?: number;
  created_at?: string;
}

interface SseEvent {
  type: "progress" | "result" | "error" | "complete";
  feature?: string;
  law_name?: string;
  stage?: string;
  percent?: number;
  message?: string;
  [key: string]: unknown;
}

// ─────────────────────────────────────────────
// Auth helpers
// ─────────────────────────────────────────────

function getAuthHeaders(userId?: string): Record<string, string> {
  const headers: Record<string, string> = {};
  if (userId) headers["X-User-Id"] = userId;
  return headers;
}

// ─────────────────────────────────────────────
// DB API helpers — correct body/response format
// ─────────────────────────────────────────────

async function dbFetch(
  table: TableName,
  userId: string,
  params?: Record<string, string>
): Promise<{ items: DbRow[]; total: number }> {
  const url = new URL(`${API_BASE}/admin/db/${table}`);
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  const res = await fetch(url.toString(), { headers: getAuthHeaders(userId) });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail?.message || `DB 조회 실패 (${res.status})`);
  }
  return res.json(); // { table, total, limit, offset, items: [...] }
}

async function dbCreate(
  table: TableName,
  data: Record<string, unknown>,
  userId: string
): Promise<{ id: string }> {
  const res = await fetch(`${API_BASE}/admin/db/${table}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeaders(userId) },
    body: JSON.stringify({ data }), // { "data": { ...fields } }
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail?.message || "생성 실패");
  }
  return res.json();
}

async function dbPatch(
  table: TableName,
  rowId: string,
  data: Record<string, unknown>,
  userId: string
): Promise<void> {
  const res = await fetch(`${API_BASE}/admin/db/${table}/${rowId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...getAuthHeaders(userId) },
    body: JSON.stringify({ data }), // { "data": { ...fields } }
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail?.message || "수정 실패");
  }
}

async function dbDelete(table: TableName, rowId: string, userId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/admin/db/${table}/${rowId}`, {
    method: "DELETE",
    headers: getAuthHeaders(userId),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail?.message || "삭제 실패");
  }
}

async function dbVerify(table: TableName, rowId: string, userId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/admin/db/${table}/${rowId}/verify`, {
    method: "POST",
    headers: getAuthHeaders(userId),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail?.message || "검증 실패");
  }
}

// ─────────────────────────────────────────────
// IngredientTab — 성분 DB 관리
// ─────────────────────────────────────────────

function IngredientTab({ userId }: { userId: string }) {
  const [selectedTable, setSelectedTable] = useState<TableName>("f1_allowed_ingredients");
  const [rows, setRows] = useState<DbRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [onlyMine, setOnlyMine] = useState(false);
  const [onlyUnverified, setOnlyUnverified] = useState(false);

  // Add form
  const [showAddForm, setShowAddForm] = useState(false);
  const [newRowData, setNewRowData] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  // Inline edit
  const [editingRowId, setEditingRowId] = useState<string | null>(null);
  const [editData, setEditData] = useState<Record<string, string>>({});
  const [editSaving, setEditSaving] = useState(false);

  const tableInfo = TABLE_INFO[selectedTable];

  const showSuccess = (msg: string) => {
    setSuccess(msg);
    setTimeout(() => setSuccess(null), 3000);
  };

  const loadRows = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string> = { limit: "100" };
      if (searchQuery) params.search = searchQuery;
      if (onlyMine) params.only_mine = "true";
      if (onlyUnverified) params.only_unverified = "true";
      const data = await dbFetch(selectedTable, userId, params);
      setRows(data.items || []);
      setTotal(data.total || 0);
    } catch (e) {
      setError(e instanceof Error ? e.message : "조회 실패");
    } finally {
      setLoading(false);
    }
  }, [selectedTable, userId, searchQuery, onlyMine, onlyUnverified]);

  useEffect(() => {
    loadRows();
  }, [selectedTable, onlyMine, onlyUnverified, loadRows]);

  const handleAddRow = async () => {
    if (!userId) return;
    setSubmitting(true);
    try {
      const data: Record<string, unknown> = {};
      tableInfo.columns.forEach((col) => {
        if (col !== "is_verified" && newRowData[col]) data[col] = newRowData[col];
      });
      await dbCreate(selectedTable, data, userId);
      setNewRowData({});
      setShowAddForm(false);
      showSuccess("항목이 추가되었습니다.");
      await loadRows();
    } catch (e) {
      setError(e instanceof Error ? e.message : "추가 실패");
    } finally {
      setSubmitting(false);
    }
  };

  const startEdit = (row: DbRow) => {
    setEditingRowId(row.id);
    const init: Record<string, string> = {};
    tableInfo.columns.forEach((col) => {
      if (col !== "is_verified") init[col] = String(row[col] ?? "");
    });
    setEditData(init);
  };

  const cancelEdit = () => {
    setEditingRowId(null);
    setEditData({});
  };

  const saveEdit = async (rowId: string) => {
    setEditSaving(true);
    try {
      const data: Record<string, unknown> = {};
      Object.entries(editData).forEach(([k, v]) => {
        if (v !== "") data[k] = v;
      });
      await dbPatch(selectedTable, rowId, data, userId);
      setEditingRowId(null);
      showSuccess("수정되었습니다.");
      await loadRows();
    } catch (e) {
      setError(e instanceof Error ? e.message : "수정 실패");
    } finally {
      setEditSaving(false);
    }
  };

  const handleDelete = async (rowId: string) => {
    if (!confirm("이 항목을 삭제하시겠습니까?")) return;
    try {
      await dbDelete(selectedTable, rowId, userId);
      showSuccess("삭제되었습니다.");
      await loadRows();
    } catch (e) {
      setError(e instanceof Error ? e.message : "삭제 실패");
    }
  };

  const handleVerify = async (rowId: string) => {
    try {
      await dbVerify(selectedTable, rowId, userId);
      showSuccess("검증 완료 처리되었습니다.");
      await loadRows();
    } catch (e) {
      setError(e instanceof Error ? e.message : "검증 실패");
    }
  };

  return (
    <div>
      {/* Table selector */}
      <div className="flex gap-2 mb-5 flex-wrap">
        {(Object.keys(TABLE_INFO) as TableName[]).map((t) => (
          <button
            key={t}
            onClick={() => {
              setSelectedTable(t);
              setShowAddForm(false);
              setNewRowData({});
              setEditingRowId(null);
            }}
            className="px-4 py-2 rounded-lg text-[13px] font-medium transition-all"
            style={
              selectedTable === t
                ? { background: "var(--ds-color-primary)", color: "#fff" }
                : {
                    background: "var(--ds-color-surface)",
                    color: "var(--ds-color-text-secondary)",
                    border: "1px solid var(--ds-color-border)",
                  }
            }
          >
            {TABLE_INFO[t].label}
          </button>
        ))}
      </div>

      {/* Table info */}
      <div className="mb-4">
        <h2 className="text-[15px] font-bold" style={{ color: "var(--ds-color-text-heading)" }}>
          {tableInfo.label}
        </h2>
        <p className="text-[12px] mt-0.5" style={{ color: "var(--ds-color-text-tertiary)" }}>
          {tableInfo.desc} · 총 {total}건
        </p>
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <div
          className="flex items-center gap-2 px-3 py-2 rounded-lg border flex-1 min-w-[180px]"
          style={{ background: "var(--ds-color-surface)", borderColor: "var(--ds-color-border)" }}
        >
          <Search size={13} style={{ color: "var(--ds-color-text-tertiary)" }} />
          <input
            type="text"
            placeholder="검색..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && loadRows()}
            className="flex-1 text-[13px] bg-transparent outline-none"
            style={{ color: "var(--ds-color-text-primary)" }}
          />
        </div>

        {/* Filter toggles */}
        <button
          onClick={() => setOnlyMine((v) => !v)}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-[12px] font-medium border transition-all"
          style={
            onlyMine
              ? { background: "var(--ds-color-primary-soft)", color: "var(--ds-color-primary-text)", borderColor: "var(--ds-color-primary)" }
              : { background: "var(--ds-color-surface)", color: "var(--ds-color-text-secondary)", borderColor: "var(--ds-color-border)" }
          }
        >
          <Filter size={12} />내 항목만
        </button>
        <button
          onClick={() => setOnlyUnverified((v) => !v)}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-[12px] font-medium border transition-all"
          style={
            onlyUnverified
              ? { background: "var(--ds-color-warning-soft)", color: "var(--ds-color-warning-text)", borderColor: "var(--ds-color-warning)" }
              : { background: "var(--ds-color-surface)", color: "var(--ds-color-text-secondary)", borderColor: "var(--ds-color-border)" }
          }
        >
          <AlertTriangle size={12} />미검증
        </button>

        <button
          onClick={loadRows}
          className="p-2 rounded-lg border transition-colors"
          style={{ border: "1px solid var(--ds-color-border)", color: "var(--ds-color-text-secondary)" }}
          title="새로고침"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
        <Button
          variant="primary"
          size="md"
          icon={<Plus size={13} />}
          onClick={() => { setShowAddForm(!showAddForm); setEditingRowId(null); }}
        >
          행 추가
        </Button>
      </div>

      {/* Alerts */}
      {success && (
        <div className="mb-3 px-4 py-2 rounded-lg flex items-center gap-2 text-[13px]"
          style={{ background: "var(--ds-color-success-soft)", color: "var(--ds-color-success-text)" }}>
          <CheckCircle size={13} />{success}
        </div>
      )}
      {error && (
        <div className="mb-3 px-4 py-2 rounded-lg flex items-center gap-2 text-[13px]"
          style={{ background: "var(--ds-color-error-soft)", color: "var(--ds-color-error-text)" }}>
          <AlertTriangle size={13} />{error}
          <button onClick={() => setError(null)} className="ml-auto text-[11px] underline">닫기</button>
        </div>
      )}

      {/* Add form */}
      {showAddForm && (
        <div className="mb-4 p-4 rounded-xl border"
          style={{ background: "var(--ds-color-surface)", borderColor: "var(--ds-color-border)" }}>
          <p className="text-[13px] font-semibold mb-3" style={{ color: "var(--ds-color-text-heading)" }}>
            새 항목 추가
          </p>
          <div className="grid grid-cols-2 gap-3 mb-4">
            {tableInfo.columns.filter((c) => c !== "is_verified").map((col) => (
              <div key={col}>
                <label className="text-[11px] font-medium block mb-1"
                  style={{ color: "var(--ds-color-text-tertiary)" }}>{col}</label>
                <input
                  type="text"
                  value={newRowData[col] || ""}
                  onChange={(e) => setNewRowData((p) => ({ ...p, [col]: e.target.value }))}
                  className="w-full px-3 py-1.5 rounded-lg text-[13px] border outline-none"
                  style={{
                    background: "var(--ds-color-bg)",
                    borderColor: "var(--ds-color-border)",
                    color: "var(--ds-color-text-primary)",
                  }}
                  placeholder={col}
                />
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <Button variant="primary" size="md" onClick={handleAddRow} disabled={submitting}>
              {submitting ? "저장 중..." : "저장"}
            </Button>
            <Button variant="secondary" size="md" onClick={() => { setShowAddForm(false); setNewRowData({}); }}>
              취소
            </Button>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="rounded-xl border overflow-hidden" style={{ borderColor: "var(--ds-color-border)" }}>
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={22} className="animate-spin" style={{ color: "var(--ds-color-primary)" }} />
          </div>
        ) : rows.length === 0 ? (
          <div className="text-center py-14">
            <Database size={26} className="mx-auto mb-2" style={{ color: "var(--ds-color-text-tertiary)" }} />
            <p className="text-[13px]" style={{ color: "var(--ds-color-text-secondary)" }}>데이터가 없습니다.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr style={{ background: "var(--ds-color-surface)", borderBottom: "1px solid var(--ds-color-border)" }}>
                  {tableInfo.displayColumns.map((col) => (
                    <th key={col} className="text-left px-3 py-2.5 font-semibold"
                      style={{ color: "var(--ds-color-text-secondary)" }}>
                      {col}
                    </th>
                  ))}
                  <th className="text-right px-3 py-2.5 font-semibold w-24"
                    style={{ color: "var(--ds-color-text-secondary)" }}>액션</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, idx) => {
                  const isEditing = editingRowId === row.id;
                  return (
                    <tr
                      key={row.id || idx}
                      className="border-b transition-colors"
                      style={{
                        borderColor: "var(--ds-color-border-subtle)",
                        background: isEditing ? "var(--ds-color-primary-soft)" : "var(--ds-color-bg)",
                      }}
                      onMouseEnter={(e) => {
                        if (!isEditing) e.currentTarget.style.background = "var(--ds-color-surface)";
                      }}
                      onMouseLeave={(e) => {
                        if (!isEditing) e.currentTarget.style.background = "var(--ds-color-bg)";
                      }}
                    >
                      {tableInfo.displayColumns.map((col) => (
                        <td key={col} className="px-3 py-2 max-w-[180px]"
                          style={{ color: "var(--ds-color-text-primary)" }}>
                          {isEditing && col !== "is_verified" ? (
                            <input
                              type="text"
                              value={editData[col] ?? String(row[col] ?? "")}
                              onChange={(e) => setEditData((p) => ({ ...p, [col]: e.target.value }))}
                              className="w-full px-2 py-1 rounded border text-[12px] outline-none"
                              style={{
                                background: "var(--ds-color-bg)",
                                borderColor: "var(--ds-color-primary)",
                                color: "var(--ds-color-text-primary)",
                              }}
                            />
                          ) : col === "is_verified" ? (
                            <span
                              className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full font-medium"
                              style={
                                row[col]
                                  ? { background: "var(--ds-color-success-soft)", color: "var(--ds-color-success-text)" }
                                  : { background: "var(--ds-color-warning-soft)", color: "var(--ds-color-warning-text)" }
                              }
                            >
                              {row[col] ? <><CheckCircle size={10} />검증됨</> : <>미검증</>}
                            </span>
                          ) : (
                            <span className="truncate block">{String(row[col] ?? "—")}</span>
                          )}
                        </td>
                      ))}
                      <td className="px-3 py-2 text-right">
                        {isEditing ? (
                          <div className="flex items-center justify-end gap-1">
                            <button
                              onClick={() => saveEdit(row.id)}
                              disabled={editSaving}
                              className="p-1.5 rounded-lg transition-colors"
                              style={{ color: "var(--ds-color-success-text)", background: "var(--ds-color-success-soft)" }}
                              title="저장"
                            >
                              {editSaving ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                            </button>
                            <button
                              onClick={cancelEdit}
                              className="p-1.5 rounded-lg transition-colors"
                              style={{ color: "var(--ds-color-text-tertiary)" }}
                              title="취소"
                            >
                              <X size={12} />
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center justify-end gap-1">
                            <button
                              onClick={() => startEdit(row)}
                              className="p-1.5 rounded-lg transition-colors"
                              style={{ color: "var(--ds-color-text-tertiary)" }}
                              onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.color = "var(--ds-color-primary-text)")}
                              onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.color = "var(--ds-color-text-tertiary)")}
                              title="수정"
                            >
                              <Edit2 size={12} />
                            </button>
                            {!row.is_verified && (
                              <button
                                onClick={() => handleVerify(row.id)}
                                className="p-1.5 rounded-lg transition-colors"
                                style={{ color: "var(--ds-color-text-tertiary)" }}
                                onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.color = "var(--ds-color-success-text)")}
                                onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.color = "var(--ds-color-text-tertiary)")}
                                title="검증 완료 처리"
                              >
                                <CheckCircle size={12} />
                              </button>
                            )}
                            <button
                              onClick={() => handleDelete(row.id)}
                              className="p-1.5 rounded-lg transition-colors"
                              style={{ color: "var(--ds-color-text-tertiary)" }}
                              onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.color = "var(--ds-color-error-text)")}
                              onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.color = "var(--ds-color-text-tertiary)")}
                              title="삭제"
                            >
                              <Trash2 size={12} />
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// LawUploadTab — 법령 업로드 (SSE)
// ─────────────────────────────────────────────

interface LawUploadEntry {
  lawName: string;
  file: File | null;
  고시번호: string;
  시행일: string;
}

interface ProgressItem {
  key: string; // `${feature}::${law_name}`
  feature: string;
  law_name: string;
  stage: string;
  percent: number;
  done: boolean;
  error?: string;
}

function LawUploadTab() {
  const [availableLaws, setAvailableLaws] = useState<LawInfo[]>([]);
  const [loadingLaws, setLoadingLaws] = useState(true);
  const [entries, setEntries] = useState<LawUploadEntry[]>([
    { lawName: "", file: null, 고시번호: "", 시행일: "" },
  ]);
  const [uploading, setUploading] = useState(false);
  const [sseEvents, setSseEvents] = useState<SseEvent[]>([]);
  const [progressItems, setProgressItems] = useState<ProgressItem[]>([]);
  const [uploadDone, setUploadDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRefs = useRef<(HTMLInputElement | null)[]>([]);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const loadLaws = async () => {
      try {
        const res = await fetch(`${ADMIN_BASE}/admin/law-update/laws`);
        if (!res.ok) throw new Error("법령 목록 로드 실패");
        const data = await res.json();
        setAvailableLaws(data.laws || []);
      } catch (e) {
        setError(e instanceof Error ? e.message : "법령 목록 로드 실패");
      } finally {
        setLoadingLaws(false);
      }
    };
    loadLaws();
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [sseEvents]);

  const addEntry = () =>
    setEntries((prev) => [...prev, { lawName: "", file: null, 고시번호: "", 시행일: "" }]);

  const removeEntry = (idx: number) =>
    setEntries((prev) => prev.filter((_, i) => i !== idx));

  const updateEntry = (idx: number, patch: Partial<LawUploadEntry>) =>
    setEntries((prev) => prev.map((e, i) => (i === idx ? { ...e, ...patch } : e)));

  const handleFileChange = (idx: number, files: FileList | null) => {
    if (!files || files.length === 0) return;
    updateEntry(idx, { file: files[0] });
  };

  const handleUpload = async () => {
    const valid = entries.filter((e) => e.lawName && e.file);
    if (valid.length === 0) {
      setError("법령명과 파일을 모두 선택해주세요.");
      return;
    }
    setError(null);
    setUploading(true);
    setUploadDone(false);
    setSseEvents([]);
    setProgressItems([]);

    const formData = new FormData();
    valid.forEach((e) => formData.append("files", e.file!));
    formData.append("law_names", JSON.stringify(valid.map((e) => e.lawName)));
    formData.append("고시번호들", JSON.stringify(valid.map((e) => e.고시번호)));
    formData.append("시행일들", JSON.stringify(valid.map((e) => e.시행일)));

    try {
      const res = await fetch(`${ADMIN_BASE}/admin/law-update/upload`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || "업로드 실패");
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("스트림을 읽을 수 없습니다.");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Parse SSE lines
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          try {
            const event: SseEvent = JSON.parse(line.slice(5).trim());
            setSseEvents((prev) => [...prev, event]);

            if (event.type === "progress") {
              const key = `${event.feature}::${event.law_name}`;
              setProgressItems((prev) => {
                const existing = prev.find((p) => p.key === key);
                if (existing) {
                  return prev.map((p) =>
                    p.key === key
                      ? { ...p, stage: event.stage || "", percent: event.percent || 0 }
                      : p
                  );
                }
                return [
                  ...prev,
                  {
                    key,
                    feature: event.feature || "",
                    law_name: event.law_name || "",
                    stage: event.stage || "",
                    percent: event.percent || 0,
                    done: false,
                  },
                ];
              });
            } else if (event.type === "result") {
              const key = `${event.feature}::${event.law_name}`;
              setProgressItems((prev) =>
                prev.map((p) => (p.key === key ? { ...p, percent: 100, done: true } : p))
              );
            } else if (event.type === "error") {
              const key = `${event.feature}::${event.law_name}`;
              setProgressItems((prev) =>
                prev.map((p) =>
                  p.key === key ? { ...p, error: event.message || "오류", done: true } : p
                )
              );
            } else if (event.type === "complete") {
              setUploadDone(true);
              break;
            }
          } catch {
            // skip malformed
          }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "업로드 실패");
    } finally {
      setUploading(false);
    }
  };

  const TIER_COLOR: Record<string, string> = {
    법률: "var(--ds-color-primary)",
    시행령: "var(--ds-color-info)",
    시행규칙: "var(--ds-color-warning-text)",
    고시: "var(--ds-color-text-secondary)",
    행정데이터: "var(--ds-color-success-text)",
    가이드라인: "var(--ds-color-text-tertiary)",
    조약: "var(--ds-color-text-tertiary)",
  };

  return (
    <div>
      <h2 className="text-[15px] font-bold mb-1" style={{ color: "var(--ds-color-text-heading)" }}>
        법령 업로드
      </h2>
      <p className="text-[12px] mb-5" style={{ color: "var(--ds-color-text-tertiary)" }}>
        법령 PDF를 업로드하면 관련 기능(F1·F2·F4 등)의 RAG DB가 자동으로 업데이트됩니다.
      </p>

      {error && (
        <div className="mb-4 px-4 py-2.5 rounded-lg flex items-center gap-2 text-[13px]"
          style={{ background: "var(--ds-color-error-soft)", color: "var(--ds-color-error-text)" }}>
          <AlertTriangle size={13} />{error}
          <button onClick={() => setError(null)} className="ml-auto text-[11px] underline">닫기</button>
        </div>
      )}

      {/* Upload entries */}
      <div className="space-y-3 mb-4">
        {entries.map((entry, idx) => (
          <div
            key={idx}
            className="p-4 rounded-xl border"
            style={{ background: "var(--ds-color-surface)", borderColor: "var(--ds-color-border)" }}
          >
            <div className="flex items-start gap-3">
              <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-3">
                {/* Law selector */}
                <div>
                  <label className="text-[11px] font-medium block mb-1.5"
                    style={{ color: "var(--ds-color-text-tertiary)" }}>법령명</label>
                  <div className="relative">
                    <select
                      value={entry.lawName}
                      onChange={(e) => updateEntry(idx, { lawName: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg text-[13px] border appearance-none outline-none pr-8"
                      style={{
                        background: "var(--ds-color-bg)",
                        borderColor: "var(--ds-color-border)",
                        color: entry.lawName ? "var(--ds-color-text-primary)" : "var(--ds-color-text-tertiary)",
                      }}
                      disabled={loadingLaws}
                    >
                      <option value="">-- 법령 선택 --</option>
                      {availableLaws.map((law) => (
                        <option key={law.law_name} value={law.law_name}>
                          [{law.tier}] {law.law_name}
                        </option>
                      ))}
                    </select>
                    <ChevronDown size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none"
                      style={{ color: "var(--ds-color-text-tertiary)" }} />
                  </div>
                  {entry.lawName && (
                    <p className="text-[11px] mt-1" style={{ color: "var(--ds-color-text-tertiary)" }}>
                      {availableLaws.find((l) => l.law_name === entry.lawName)?.description}
                      {" · "}
                      <span style={{ color: TIER_COLOR[availableLaws.find((l) => l.law_name === entry.lawName)?.tier || ""] || "inherit" }}>
                        {availableLaws.find((l) => l.law_name === entry.lawName)?.features.join(", ")}
                      </span>
                    </p>
                  )}
                </div>

                {/* File input */}
                <div>
                  <label className="text-[11px] font-medium block mb-1.5"
                    style={{ color: "var(--ds-color-text-tertiary)" }}>파일 (PDF/HWPX)</label>
                  <input
                    ref={(el) => { fileInputRefs.current[idx] = el; }}
                    type="file"
                    accept=".pdf,.hwpx"
                    className="hidden"
                    onChange={(e) => handleFileChange(idx, e.target.files)}
                  />
                  <button
                    onClick={() => fileInputRefs.current[idx]?.click()}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-lg border text-[13px] text-left transition-colors"
                    style={{
                      background: "var(--ds-color-bg)",
                      borderColor: entry.file ? "var(--ds-color-success)" : "var(--ds-color-border)",
                      color: entry.file ? "var(--ds-color-success-text)" : "var(--ds-color-text-tertiary)",
                    }}
                  >
                    <Upload size={13} />
                    <span className="truncate">{entry.file ? entry.file.name : "파일 선택..."}</span>
                  </button>
                </div>

                {/* 고시번호 + 시행일 */}
                <div>
                  <label className="text-[11px] font-medium block mb-1.5"
                    style={{ color: "var(--ds-color-text-tertiary)" }}>고시번호 (선택)</label>
                  <input
                    type="text"
                    value={entry.고시번호}
                    onChange={(e) => updateEntry(idx, { 고시번호: e.target.value })}
                    placeholder="예: 제2025-60호"
                    className="w-full px-3 py-2 rounded-lg text-[13px] border outline-none"
                    style={{
                      background: "var(--ds-color-bg)",
                      borderColor: "var(--ds-color-border)",
                      color: "var(--ds-color-text-primary)",
                    }}
                  />
                </div>
                <div>
                  <label className="text-[11px] font-medium block mb-1.5"
                    style={{ color: "var(--ds-color-text-tertiary)" }}>시행일 (선택)</label>
                  <input
                    type="date"
                    value={entry.시행일}
                    onChange={(e) => updateEntry(idx, { 시행일: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg text-[13px] border outline-none"
                    style={{
                      background: "var(--ds-color-bg)",
                      borderColor: "var(--ds-color-border)",
                      color: "var(--ds-color-text-primary)",
                    }}
                  />
                </div>
              </div>

              {entries.length > 1 && (
                <button
                  onClick={() => removeEntry(idx)}
                  className="p-1.5 rounded-lg mt-1 transition-colors"
                  style={{ color: "var(--ds-color-text-tertiary)" }}
                  onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.color = "var(--ds-color-error-text)")}
                  onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.color = "var(--ds-color-text-tertiary)")}
                >
                  <X size={15} />
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2 mb-6">
        <button
          onClick={addEntry}
          className="flex items-center gap-1.5 text-[13px] font-medium px-3 py-1.5 rounded-lg border transition-colors"
          style={{
            borderColor: "var(--ds-color-border)",
            color: "var(--ds-color-text-secondary)",
          }}
        >
          <Plus size={13} /> 법령 추가
        </button>
        <Button
          variant="primary"
          size="md"
          icon={uploading ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
          onClick={handleUpload}
          disabled={uploading}
        >
          {uploading ? "업로드 중..." : "업로드 시작"}
        </Button>
      </div>

      {/* Progress */}
      {(progressItems.length > 0 || uploading) && (
        <div className="rounded-xl border overflow-hidden"
          style={{ borderColor: "var(--ds-color-border)" }}>
          <div className="px-4 py-3 flex items-center justify-between"
            style={{ background: "var(--ds-color-surface)", borderBottom: "1px solid var(--ds-color-border)" }}>
            <p className="text-[13px] font-semibold" style={{ color: "var(--ds-color-text-heading)" }}>
              처리 진행 상황
            </p>
            {uploadDone && (
              <span className="flex items-center gap-1.5 text-[12px] font-medium"
                style={{ color: "var(--ds-color-success-text)" }}>
                <CheckCircle size={13} /> 완료
              </span>
            )}
          </div>

          {/* Progress bars */}
          <div className="p-4 space-y-3">
            {progressItems.map((item) => (
              <div key={item.key}>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[12px] font-medium" style={{ color: "var(--ds-color-text-primary)" }}>
                    [{item.feature}] {item.law_name}
                  </span>
                  <span className="text-[11px]" style={{ color: item.error ? "var(--ds-color-error-text)" : "var(--ds-color-text-tertiary)" }}>
                    {item.error ? `오류: ${item.error}` : item.done ? "완료" : `${item.stage} (${item.percent}%)`}
                  </span>
                </div>
                <div className="h-1.5 rounded-full overflow-hidden"
                  style={{ background: "var(--ds-color-border)" }}>
                  <div
                    className="h-full rounded-full transition-all duration-300"
                    style={{
                      width: `${item.percent}%`,
                      background: item.error
                        ? "var(--ds-color-error)"
                        : item.done
                        ? "var(--ds-color-success)"
                        : "var(--ds-color-primary)",
                    }}
                  />
                </div>
              </div>
            ))}
          </div>

          {/* SSE event log */}
          <div
            ref={logRef}
            className="mx-4 mb-4 p-3 rounded-lg overflow-y-auto max-h-48 text-[11px] font-mono"
            style={{ background: "var(--ds-color-bg)", border: "1px solid var(--ds-color-border)" }}
          >
            {sseEvents.map((ev, i) => (
              <div key={i} style={{ color: ev.type === "error" ? "var(--ds-color-error-text)" : ev.type === "complete" ? "var(--ds-color-success-text)" : "var(--ds-color-text-secondary)" }}>
                [{ev.type}]{ev.feature ? ` [${ev.feature}]` : ""}{ev.law_name ? ` ${ev.law_name}` : ""}{ev.stage ? ` → ${ev.stage}` : ""}{ev.percent !== undefined ? ` ${ev.percent}%` : ""}{ev.message ? ` ${ev.message}` : ""}
              </div>
            ))}
            {uploading && !uploadDone && (
              <div className="flex items-center gap-1 mt-1" style={{ color: "var(--ds-color-text-tertiary)" }}>
                <Loader2 size={10} className="animate-spin" /> 처리 중...
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// LawListTab — 법령 목록
// ─────────────────────────────────────────────

const TIER_LABELS: Record<number, string> = {
  1: "법률", 2: "시행령", 3: "시행규칙", 4: "고시",
};

function LawListTab() {
  const [laws, setLaws] = useState<RegisteredLaw[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadLaws = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${ADMIN_BASE}/admin/laws`);
      if (!res.ok) throw new Error("법령 목록 조회 실패");
      const data = await res.json();
      setLaws(data.laws || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "조회 실패");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadLaws();
  }, [loadLaws]);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-[15px] font-bold" style={{ color: "var(--ds-color-text-heading)" }}>
            등록된 법령 목록
          </h2>
          <p className="text-[12px] mt-0.5" style={{ color: "var(--ds-color-text-tertiary)" }}>
            Supabase f4_law_documents 테이블 기준 · 총 {laws.length}건
          </p>
        </div>
        <button
          onClick={loadLaws}
          className="p-2 rounded-lg border transition-colors"
          style={{ border: "1px solid var(--ds-color-border)", color: "var(--ds-color-text-secondary)" }}
          title="새로고침"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {error && (
        <div className="mb-4 px-4 py-2.5 rounded-lg flex items-center gap-2 text-[13px]"
          style={{ background: "var(--ds-color-error-soft)", color: "var(--ds-color-error-text)" }}>
          <AlertTriangle size={13} />{error}
        </div>
      )}

      <div className="rounded-xl border overflow-hidden" style={{ borderColor: "var(--ds-color-border)" }}>
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={22} className="animate-spin" style={{ color: "var(--ds-color-primary)" }} />
          </div>
        ) : laws.length === 0 ? (
          <div className="text-center py-14">
            <BookOpen size={26} className="mx-auto mb-2" style={{ color: "var(--ds-color-text-tertiary)" }} />
            <p className="text-[13px]" style={{ color: "var(--ds-color-text-secondary)" }}>
              등록된 법령이 없습니다.
            </p>
            <p className="text-[11px] mt-1" style={{ color: "var(--ds-color-text-tertiary)" }}>
              &apos;법령 업로드&apos; 탭에서 법령을 등록해주세요.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr style={{ background: "var(--ds-color-surface)", borderBottom: "1px solid var(--ds-color-border)" }}>
                  {["법령명", "고시번호", "시행일", "계층", "청크 수", "등록일"].map((col) => (
                    <th key={col} className="text-left px-4 py-2.5 font-semibold"
                      style={{ color: "var(--ds-color-text-secondary)" }}>
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {laws.map((law, idx) => (
                  <tr
                    key={law.id || idx}
                    className="border-b transition-colors"
                    style={{ borderColor: "var(--ds-color-border-subtle)", background: "var(--ds-color-bg)" }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "var(--ds-color-surface)")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "var(--ds-color-bg)")}
                  >
                    <td className="px-4 py-2.5 font-medium" style={{ color: "var(--ds-color-text-primary)" }}>
                      {law.law_name}
                    </td>
                    <td className="px-4 py-2.5" style={{ color: "var(--ds-color-text-secondary)" }}>
                      {law.고시번호 || "—"}
                    </td>
                    <td className="px-4 py-2.5" style={{ color: "var(--ds-color-text-secondary)" }}>
                      {law.시행일 ? new Date(law.시행일).toLocaleDateString("ko-KR") : "—"}
                    </td>
                    <td className="px-4 py-2.5">
                      {law.법령_tier != null ? (
                        <span className="text-[11px] px-2 py-0.5 rounded-full"
                          style={{ background: "var(--ds-color-surface)", border: "1px solid var(--ds-color-border)", color: "var(--ds-color-text-secondary)" }}>
                          {TIER_LABELS[law.법령_tier] || `T${law.법령_tier}`}
                        </span>
                      ) : "—"}
                    </td>
                    <td className="px-4 py-2.5" style={{ color: "var(--ds-color-text-secondary)" }}>
                      {law.total_chunks?.toLocaleString() ?? "—"}
                    </td>
                    <td className="px-4 py-2.5" style={{ color: "var(--ds-color-text-tertiary)" }}>
                      {law.created_at ? new Date(law.created_at).toLocaleDateString("ko-KR") : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Main Page
// ─────────────────────────────────────────────

const MAIN_TABS: { id: MainTab; label: string; icon: React.ReactNode }[] = [
  { id: "ingredients", label: "성분 DB", icon: <Database size={14} /> },
  { id: "law_upload", label: "법령 업로드", icon: <Upload size={14} /> },
  { id: "law_list", label: "법령 목록", icon: <FileText size={14} /> },
];

export default function DbPage() {
  const router = useRouter();
  const [userId, setUserId] = useState<string>("");
  const [authLoading, setAuthLoading] = useState(true);
  const [tab, setTab] = useState<MainTab>("ingredients");

  useEffect(() => {
    const getUser = async () => {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session) {
        router.replace("/auth/login");
        return;
      }
      setUserId(session.user.id);
      setAuthLoading(false);
    };
    getUser();
  }, [router]);

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--ds-color-bg)" }}>
        <Loader2 size={24} className="animate-spin" style={{ color: "var(--ds-color-primary)" }} />
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ background: "var(--ds-color-bg)" }}>
      {/* Header */}
      <header
        className="sticky top-0 z-50 border-b"
        style={{ background: "var(--ds-color-bg)", borderColor: "var(--ds-color-border)" }}
      >
        <div className="max-w-[1440px] mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push("/dashboard")}
              className="flex items-center gap-1.5 text-sm transition-colors"
              style={{ color: "var(--ds-color-text-secondary)" }}
            >
              <ChevronLeft size={16} />
              <span className="font-medium">대시보드</span>
            </button>
            <div className="w-px h-5" style={{ background: "var(--ds-color-border)" }} />
            <div className="flex items-center gap-2">
              <div
                className="w-7 h-7 rounded-lg flex items-center justify-center"
                style={{ background: "var(--ds-color-primary)" }}
              >
                <Database size={13} className="text-white" />
              </div>
              <span className="text-sm font-semibold" style={{ color: "var(--ds-color-text-heading)" }}>
                DB 관리
              </span>
            </div>
          </div>
          <div
            className="flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-full"
            style={{ background: "var(--ds-color-warning-soft)", color: "var(--ds-color-warning-text)" }}
          >
            <Shield size={11} />
            관리자 전용
          </div>
        </div>

        {/* Main tab bar */}
        <div className="max-w-[1440px] mx-auto px-6 flex gap-1 pb-0 border-t"
          style={{ borderColor: "var(--ds-color-border-subtle)" }}>
          {MAIN_TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className="flex items-center gap-1.5 px-4 py-2.5 text-[13px] font-medium transition-all border-b-2 -mb-px"
              style={
                tab === t.id
                  ? { borderColor: "var(--ds-color-primary)", color: "var(--ds-color-primary-text)" }
                  : { borderColor: "transparent", color: "var(--ds-color-text-secondary)" }
              }
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>
      </header>

      {/* Content */}
      <div className="max-w-[1440px] mx-auto px-6 py-6">
        {tab === "ingredients" && <IngredientTab userId={userId} />}
        {tab === "law_upload" && <LawUploadTab />}
        {tab === "law_list" && <LawListTab />}
      </div>
    </div>
  );
}
