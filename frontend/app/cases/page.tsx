"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  ChevronLeft, FileText, ArrowRight, Trash2, CheckSquare, Square,
  SortAsc, SortDesc, Search, Plus, Loader2, LayoutList,
  Folder, FolderOpen, FolderPlus, MoreHorizontal, FolderInput, X, Check,
  LayoutGrid,
} from "lucide-react";
import { supabase } from "@/lib/supabase";
import { listCases, deleteCase, createCase, type CaseData } from "@/lib/api";
import Button from "@/components/ui/Button";

type SortField = "created_at" | "product_name" | "status" | "current_step";
type SortDir   = "asc" | "desc";
type ViewMode  = "list" | "card";

interface FolderItem {
  id:    string;
  name:  string;
  color: string;
}

const FOLDER_COLORS = [
  "#006AF5", "#158444", "#7C3AED", "#DB2777", "#0891B2", "#985211",
];

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  processing: { label: "진행중", color: "#006AF5" },
  completed:  { label: "완료",   color: "#158444" },
  on_hold:    { label: "보류",   color: "#985211" },
  error:      { label: "오류",   color: "#E21D12" },
};

const STEP_LABELS: Record<string, string> = {
  "0": "서류 업로드",
  "1": "F1 수입판정",
  "2": "F2 유형분류",
  "3": "F3 필요서류",
  "4": "F4 라벨검토",
  "5": "F5 결과완료",
};

// ── localStorage 키 ──────────────────────────────────────────
const LS_FOLDERS  = "samc_folders";
const LS_MAPPINGS = "samc_case_folders";

export default function CasesListPage() {
  const router = useRouter();

  const [cases, setCases]             = useState<CaseData[]>([]);
  const [total, setTotal]             = useState(0);
  const [loading, setLoading]         = useState(true);
  const [creatingCase, setCreatingCase] = useState(false);
  const [selected, setSelected]       = useState<Set<string>>(new Set());
  const [sortField, setSortField]     = useState<SortField>("created_at");
  const [sortDir, setSortDir]         = useState<SortDir>("desc");
  const [search, setSearch]           = useState("");
  const [deleting, setDeleting]       = useState(false);
  const [viewMode, setViewMode]       = useState<ViewMode>("list");

  // ── 폴더 상태 ──
  const [folders, setFolders]         = useState<FolderItem[]>([]);
  const [caseFolders, setCaseFolders] = useState<Record<string, string>>({});
  const [activeFolder, setActiveFolder] = useState<string>("all");
  const [showNewFolder, setShowNewFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [newFolderColor, setNewFolderColor] = useState(FOLDER_COLORS[0]);
  const [showMoveMenu, setShowMoveMenu] = useState(false);
  const [editingFolder, setEditingFolder] = useState<string | null>(null);
  const [editingName, setEditingName]   = useState("");
  const moveMenuRef = useRef<HTMLDivElement>(null);
  const newFolderInputRef = useRef<HTMLInputElement>(null);

  // ── localStorage 로드 ──
  useEffect(() => {
    try {
      const sf = localStorage.getItem(LS_FOLDERS);
      const sm = localStorage.getItem(LS_MAPPINGS);
      if (sf) setFolders(JSON.parse(sf));
      if (sm) setCaseFolders(JSON.parse(sm));
    } catch {}
  }, []);

  const saveFolders = (f: FolderItem[]) => {
    setFolders(f);
    localStorage.setItem(LS_FOLDERS, JSON.stringify(f));
  };

  const saveCaseFolders = (m: Record<string, string>) => {
    setCaseFolders(m);
    localStorage.setItem(LS_MAPPINGS, JSON.stringify(m));
  };

  // ── 케이스 로드 ──
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listCases(undefined, 200, 0);
      setCases(res.cases);
      setTotal(res.total);
    } catch (e) { console.error("목록 로드 실패:", e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    const check = async () => {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) { router.replace("/auth/login"); return; }
      await load();
    };
    check();
  }, [router, load]);

  // ── 외부 클릭 시 메뉴 닫기 ──
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (moveMenuRef.current && !moveMenuRef.current.contains(e.target as Node)) {
        setShowMoveMenu(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // ── 필터 + 정렬 ──
  const filtered = cases
    .filter((c) => {
      const matchSearch = !search.trim() ||
        [c.product_name, c.importer_name, c.id].some(v => v?.toLowerCase().includes(search.toLowerCase()));
      const matchFolder =
        activeFolder === "all"          ? true :
        activeFolder === "uncategorized" ? !caseFolders[c.id] :
        caseFolders[c.id] === activeFolder;
      return matchSearch && matchFolder;
    })
    .sort((a, b) => {
      const va = (sortField === "created_at" ? a.created_at : sortField === "product_name" ? a.product_name : sortField === "status" ? a.status : a.current_step) || "";
      const vb = (sortField === "created_at" ? b.created_at : sortField === "product_name" ? b.product_name : sortField === "status" ? b.status : b.current_step) || "";
      const cmp = va.localeCompare(vb, "ko");
      return sortDir === "asc" ? cmp : -cmp;
    });

  // ── 선택 ──
  const toggleSelect = (id: string) => setSelected(prev => {
    const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n;
  });
  const toggleAll = () => setSelected(
    selected.size === filtered.length ? new Set() : new Set(filtered.map(c => c.id))
  );

  // ── 삭제 ──
  const handleDeleteSelected = async () => {
    if (!selected.size || !confirm(`선택한 ${selected.size}건을 삭제하시겠습니까?`)) return;
    setDeleting(true);
    for (const id of selected) {
      try { await deleteCase(id); } catch (e) { console.error(e); }
    }
    setSelected(new Set());
    await load();
    setDeleting(false);
  };

  const handleDeleteSingle = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!confirm("이 검역 건을 삭제하시겠습니까?")) return;
    try {
      await deleteCase(id);
      setCases(prev => prev.filter(c => c.id !== id));
      setTotal(p => p - 1);
      setSelected(prev => { const n = new Set(prev); n.delete(id); return n; });
    } catch (e) { console.error(e); }
  };

  // ── 새 건 등록 ──
  const handleNewCase = async () => {
    if (creatingCase) return;
    setCreatingCase(true);
    try {
      const c = await createCase("새 수입식품", "");
      router.push(`/cases/${c.id}/upload`);
    } catch (e) {
      alert(`생성 실패: ${e instanceof Error ? e.message : String(e)}`);
    } finally { setCreatingCase(false); }
  };

  // ── 정렬 ──
  const handleSort = (field: SortField) => {
    if (sortField === field) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortField(field); setSortDir("desc"); }
  };
  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return null;
    return sortDir === "asc"
      ? <SortAsc size={12} style={{ color: "var(--ds-color-primary)" }} />
      : <SortDesc size={12} style={{ color: "var(--ds-color-primary)" }} />;
  };

  // ── 폴더 생성 ──
  const handleCreateFolder = () => {
    const name = newFolderName.trim();
    if (!name) return;
    const newFolder: FolderItem = {
      id:    `folder_${Date.now()}`,
      name,
      color: newFolderColor,
    };
    saveFolders([...folders, newFolder]);
    setNewFolderName("");
    setNewFolderColor(FOLDER_COLORS[0]);
    setShowNewFolder(false);
    setActiveFolder(newFolder.id);
  };

  // ── 폴더 삭제 ──
  const handleDeleteFolder = (e: React.MouseEvent, folderId: string) => {
    e.stopPropagation();
    if (!confirm("폴더를 삭제하시겠습니까? 안의 검역건은 미분류로 이동합니다.")) return;
    saveFolders(folders.filter(f => f.id !== folderId));
    const next = { ...caseFolders };
    Object.keys(next).forEach(k => { if (next[k] === folderId) delete next[k]; });
    saveCaseFolders(next);
    if (activeFolder === folderId) setActiveFolder("all");
  };

  // ── 폴더 이름 수정 ──
  const handleRenameFolder = (folderId: string) => {
    const name = editingName.trim();
    if (!name) { setEditingFolder(null); return; }
    saveFolders(folders.map(f => f.id === folderId ? { ...f, name } : f));
    setEditingFolder(null);
  };

  // ── 폴더로 이동 ──
  const handleMoveToFolder = (folderId: string | null) => {
    const next = { ...caseFolders };
    selected.forEach(id => {
      if (folderId === null) delete next[id];
      else next[id] = folderId;
    });
    saveCaseFolders(next);
    setShowMoveMenu(false);
    setSelected(new Set());
  };

  // ── 카운트 ──
  const folderCount = (folderId: string) =>
    cases.filter(c => caseFolders[c.id] === folderId).length;
  const uncategorizedCount = cases.filter(c => !caseFolders[c.id]).length;
  const allSelected = filtered.length > 0 && selected.size === filtered.length;

  return (
    <div className="min-h-screen" style={{ background: "var(--ds-color-bg)" }}>
      {/* ── 헤더 ── */}
      <header className="sticky top-0 z-50 border-b"
        style={{ background: "var(--ds-color-bg)", borderColor: "var(--ds-color-border)" }}>
        <div className="max-w-[1400px] mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button onClick={() => router.push("/dashboard")}
              className="flex items-center gap-1.5 text-sm transition-colors"
              style={{ color: "var(--ds-color-text-secondary)" }}>
              <ChevronLeft size={16} />
              <span className="font-medium">대시보드</span>
            </button>
            <div className="w-px h-5" style={{ background: "var(--ds-color-border)" }} />
            <div className="flex items-center gap-2">
              <LayoutList size={15} style={{ color: "var(--ds-color-text-tertiary)" }} />
              <span className="text-[14px] font-semibold" style={{ color: "var(--ds-color-text-heading)" }}>
                검역건 목록
              </span>
              {!loading && (
                <span className="text-[12px] px-2 py-0.5 rounded-full"
                  style={{ background: "var(--ds-color-surface)", color: "var(--ds-color-text-tertiary)" }}>
                  총 {total}건
                </span>
              )}
            </div>
          </div>
          <Button
            variant="primary" size="md"
            icon={creatingCase ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
            onClick={handleNewCase} disabled={creatingCase}>
            {creatingCase ? "생성 중..." : "새 건 등록"}
          </Button>
        </div>
      </header>

      <div className="max-w-[1400px] mx-auto px-6 py-6 flex gap-5">

        {/* ── 폴더 사이드바 ── */}
        <aside className="w-[210px] shrink-0 space-y-1">

          {/* 전체 / 미분류 */}
          {([
            { id: "all",           label: "모든 건",  count: cases.length,     icon: LayoutList },
            { id: "uncategorized", label: "미분류",   count: uncategorizedCount, icon: FileText },
          ] as const).map(({ id, label, count, icon: Icon }) => (
            <button key={id}
              onClick={() => setActiveFolder(id)}
              className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-[13px] transition-all"
              style={activeFolder === id
                ? { background: "var(--ds-color-primary-soft)", color: "var(--ds-color-primary-text)", fontWeight: 600 }
                : { color: "var(--ds-color-text-secondary)" }}>
              <span className="flex items-center gap-2">
                <Icon size={14} />
                {label}
              </span>
              <span className="text-[11px] tabular-nums" style={{ color: "var(--ds-color-text-tertiary)" }}>{count}</span>
            </button>
          ))}

          {/* 구분선 */}
          {folders.length > 0 && (
            <div className="pt-2 pb-1">
              <div style={{ borderTop: "1px solid var(--ds-color-border-subtle)" }} />
            </div>
          )}

          {/* 폴더 목록 */}
          {folders.map(f => (
            <div key={f.id} className="group relative">
              {editingFolder === f.id ? (
                <div className="flex items-center gap-1 px-2 py-1.5 rounded-lg border"
                  style={{ borderColor: "var(--ds-color-primary)", background: "var(--ds-color-surface)" }}>
                  <input
                    autoFocus
                    value={editingName}
                    onChange={e => setEditingName(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === "Enter") handleRenameFolder(f.id);
                      if (e.key === "Escape") setEditingFolder(null);
                    }}
                    className="flex-1 text-[12px] bg-transparent outline-none"
                    style={{ color: "var(--ds-color-text-primary)" }}
                  />
                  <button onClick={() => handleRenameFolder(f.id)}>
                    <Check size={12} style={{ color: "var(--ds-color-primary)" }} />
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setActiveFolder(f.id)}
                  className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-[13px] transition-all"
                  style={activeFolder === f.id
                    ? { background: f.color + "18", color: f.color, fontWeight: 600 }
                    : { color: "var(--ds-color-text-secondary)" }}>
                  <span className="flex items-center gap-2 truncate">
                    {activeFolder === f.id
                      ? <FolderOpen size={14} style={{ color: f.color, flexShrink: 0 }} />
                      : <Folder size={14} style={{ color: f.color, flexShrink: 0 }} />}
                    <span className="truncate">{f.name}</span>
                  </span>
                  {/* 기본: 카운트 / 호버: 액션 버튼 */}
                  <span className="shrink-0 flex items-center">
                    <span className="text-[11px] tabular-nums group-hover:hidden"
                      style={{ color: "var(--ds-color-text-tertiary)" }}>
                      {folderCount(f.id)}
                    </span>
                    <span className="hidden group-hover:flex items-center gap-0.5">
                      <span
                        onClick={e => { e.stopPropagation(); setEditingFolder(f.id); setEditingName(f.name); }}
                        className="p-1 rounded transition-colors"
                        style={{ color: "var(--ds-color-text-tertiary)" }}
                        onMouseEnter={e => (e.currentTarget.style.color = "var(--ds-color-text-secondary)")}
                        onMouseLeave={e => (e.currentTarget.style.color = "var(--ds-color-text-tertiary)")}
                        title="이름 변경">
                        <MoreHorizontal size={12} />
                      </span>
                      <span
                        onClick={e => handleDeleteFolder(e, f.id)}
                        className="p-1 rounded transition-colors"
                        style={{ color: "var(--ds-color-text-tertiary)" }}
                        onMouseEnter={e => (e.currentTarget.style.color = "var(--ds-color-error-text)")}
                        onMouseLeave={e => (e.currentTarget.style.color = "var(--ds-color-text-tertiary)")}
                        title="폴더 삭제">
                        <X size={12} />
                      </span>
                    </span>
                  </span>
                </button>
              )}
            </div>
          ))}

          {/* 구분선 */}
          <div className="pt-1">
            <div style={{ borderTop: "1px solid var(--ds-color-border-subtle)" }} />
          </div>

          {/* 새 폴더 */}
          {showNewFolder ? (
            <div className="rounded-xl border p-3 space-y-2"
              style={{ borderColor: "var(--ds-color-border)", background: "var(--ds-color-surface)" }}>
              <input
                ref={newFolderInputRef}
                autoFocus
                placeholder="폴더 이름"
                value={newFolderName}
                onChange={e => setNewFolderName(e.target.value)}
                onKeyDown={e => {
                  if (e.key === "Enter") handleCreateFolder();
                  if (e.key === "Escape") { setShowNewFolder(false); setNewFolderName(""); }
                }}
                className="w-full text-[12px] px-2 py-1.5 rounded-lg border outline-none bg-transparent"
                style={{ borderColor: "var(--ds-color-border)", color: "var(--ds-color-text-primary)" }}
              />
              {/* 색상 선택 */}
              <div className="flex items-center gap-1.5">
                {FOLDER_COLORS.map(c => (
                  <button key={c} onClick={() => setNewFolderColor(c)}
                    className="w-4 h-4 rounded-full transition-transform"
                    style={{
                      background: c,
                      outline: newFolderColor === c ? `2px solid ${c}` : "none",
                      outlineOffset: "2px",
                      transform: newFolderColor === c ? "scale(1.2)" : "scale(1)",
                    }} />
                ))}
              </div>
              <div className="flex gap-1.5">
                <button onClick={handleCreateFolder}
                  className="flex-1 py-1.5 rounded-lg text-[12px] font-semibold text-white"
                  style={{ background: "var(--ds-color-primary)" }}>
                  만들기
                </button>
                <button onClick={() => { setShowNewFolder(false); setNewFolderName(""); }}
                  className="px-3 py-1.5 rounded-lg text-[12px]"
                  style={{ color: "var(--ds-color-text-secondary)", border: "1px solid var(--ds-color-border)" }}>
                  취소
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setShowNewFolder(true)}
              className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-[13px] transition-all"
              style={{ color: "var(--ds-color-text-tertiary)" }}
              onMouseEnter={e => (e.currentTarget.style.color = "var(--ds-color-text-secondary)")}
              onMouseLeave={e => (e.currentTarget.style.color = "var(--ds-color-text-tertiary)")}>
              <FolderPlus size={14} />
              새 폴더 만들기
            </button>
          )}
        </aside>

        {/* ── 메인 콘텐츠 ── */}
        <div className="flex-1 min-w-0">
          {/* 툴바 */}
          <div className="flex items-center gap-3 mb-4 flex-wrap">
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg border flex-1 min-w-[200px]"
              style={{ background: "var(--ds-color-surface)", borderColor: "var(--ds-color-border)" }}>
              <Search size={14} style={{ color: "var(--ds-color-text-tertiary)" }} />
              <input type="text" placeholder="제품명, 수입자, ID 검색..."
                value={search} onChange={e => setSearch(e.target.value)}
                className="flex-1 text-[13px] bg-transparent outline-none"
                style={{ color: "var(--ds-color-text-primary)" }} />
              {search && (
                <button onClick={() => setSearch("")} className="text-[11px]"
                  style={{ color: "var(--ds-color-text-tertiary)" }}>✕</button>
              )}
            </div>

            {/* 정렬 */}
            <div className="flex items-center gap-1">
              {([
                { field: "created_at" as SortField,   label: "날짜" },
                { field: "product_name" as SortField, label: "제품명" },
                { field: "status" as SortField,       label: "상태" },
                { field: "current_step" as SortField, label: "단계" },
              ]).map(({ field, label }) => (
                <button key={field} onClick={() => handleSort(field)}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-[12px] font-medium transition-all"
                  style={sortField === field
                    ? { background: "var(--ds-color-primary-soft)", color: "var(--ds-color-primary-text)" }
                    : { background: "var(--ds-color-surface)", color: "var(--ds-color-text-secondary)", border: "1px solid var(--ds-color-border)" }}>
                  {label}<SortIcon field={field} />
                </button>
              ))}
            </div>

            {/* 뷰 모드 토글 */}
            <div className="flex items-center rounded-lg border overflow-hidden shrink-0"
              style={{ borderColor: "var(--ds-color-border)" }}>
              {([
                { mode: "list" as ViewMode, icon: LayoutList, title: "목록형" },
                { mode: "card" as ViewMode, icon: LayoutGrid, title: "카드형" },
              ]).map(({ mode, icon: Icon, title }) => (
                <button key={mode} onClick={() => setViewMode(mode)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium transition-colors"
                  style={viewMode === mode
                    ? { background: "var(--ds-color-primary-soft)", color: "var(--ds-color-primary)" }
                    : { background: "var(--ds-color-surface)", color: "var(--ds-color-text-tertiary)" }}>
                  <Icon size={13} />
                  {title}
                </button>
              ))}
            </div>

            {/* 선택 액션 */}
            {selected.size > 0 && (
              <div className="flex items-center gap-2">
                {/* 폴더로 이동 */}
                <div className="relative" ref={moveMenuRef}>
                  <button onClick={() => setShowMoveMenu(v => !v)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-medium border transition-all"
                    style={{ background: "var(--ds-color-surface)", color: "var(--ds-color-text-secondary)", borderColor: "var(--ds-color-border)" }}>
                    <FolderInput size={13} />
                    폴더로 이동
                  </button>
                  {showMoveMenu && (
                    <div className="absolute right-0 top-full mt-1 w-[180px] rounded-xl border shadow-lg z-50 overflow-hidden"
                      style={{ background: "var(--ds-color-surface)", borderColor: "var(--ds-color-border)" }}>
                      <button onClick={() => handleMoveToFolder(null)}
                        className="w-full flex items-center gap-2 px-3 py-2.5 text-[13px] transition-colors text-left"
                        style={{ color: "var(--ds-color-text-secondary)" }}
                        onMouseEnter={e => (e.currentTarget.style.background = "var(--ds-color-bg)")}
                        onMouseLeave={e => (e.currentTarget.style.background = "")}>
                        <FileText size={13} />
                        미분류로 이동
                      </button>
                      {folders.length > 0 && (
                        <div style={{ borderTop: "1px solid var(--ds-color-border-subtle)" }}>
                          {folders.map(f => (
                            <button key={f.id} onClick={() => handleMoveToFolder(f.id)}
                              className="w-full flex items-center gap-2 px-3 py-2.5 text-[13px] transition-colors text-left"
                              style={{ color: "var(--ds-color-text-secondary)" }}
                              onMouseEnter={e => (e.currentTarget.style.background = "var(--ds-color-bg)")}
                              onMouseLeave={e => (e.currentTarget.style.background = "")}>
                              <Folder size={13} style={{ color: f.color }} />
                              {f.name}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <Button variant="secondary" size="md"
                  icon={deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                  onClick={handleDeleteSelected} disabled={deleting}>
                  {deleting ? "삭제 중..." : `${selected.size}건 삭제`}
                </Button>
              </div>
            )}
          </div>

          {/* 전체 선택 */}
          {filtered.length > 0 && (
            <div className="flex items-center gap-3 mb-3 px-1">
              <button onClick={toggleAll}
                className="flex items-center gap-1.5 text-[12px] transition-colors"
                style={{ color: "var(--ds-color-text-secondary)" }}>
                {allSelected
                  ? <CheckSquare size={15} style={{ color: "var(--ds-color-primary)" }} />
                  : <Square size={15} style={{ color: "var(--ds-color-text-tertiary)" }} />}
                {allSelected ? "전체 선택 해제" : `전체 선택 (${filtered.length}건)`}
              </button>
              {selected.size > 0 && (
                <span className="text-[12px]" style={{ color: "var(--ds-color-text-tertiary)" }}>
                  {selected.size}건 선택됨
                </span>
              )}
            </div>
          )}

          {/* 현재 폴더 헤더 */}
          {activeFolder !== "all" && (
            <div className="flex items-center gap-2 mb-3 px-1">
              {activeFolder === "uncategorized" ? (
                <><FileText size={14} style={{ color: "var(--ds-color-text-tertiary)" }} />
                <span className="text-[13px] font-semibold" style={{ color: "var(--ds-color-text-heading)" }}>미분류</span></>
              ) : (() => {
                const f = folders.find(f => f.id === activeFolder);
                return f ? (
                  <><FolderOpen size={14} style={{ color: f.color }} />
                  <span className="text-[13px] font-semibold" style={{ color: "var(--ds-color-text-heading)" }}>{f.name}</span></>
                ) : null;
              })()}
              <span className="text-[12px]" style={{ color: "var(--ds-color-text-tertiary)" }}>{filtered.length}건</span>
            </div>
          )}

          {/* 목록 */}
          {loading ? (
            <div className="flex items-center justify-center py-24">
              <Loader2 size={24} className="animate-spin" style={{ color: "var(--ds-color-primary)" }} />
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-20 rounded-2xl border-2 border-dashed"
              style={{ borderColor: "var(--ds-color-border)" }}>
              <FileText size={28} className="mx-auto mb-3" style={{ color: "var(--ds-color-text-tertiary)" }} />
              <p className="text-[14px] font-medium mb-1" style={{ color: "var(--ds-color-text-secondary)" }}>
                {search ? `"${search}" 검색 결과가 없습니다.` : "검역 건이 없습니다."}
              </p>
              {!search && (
                <div className="mt-4">
                  <Button variant="primary" size="md" onClick={handleNewCase} disabled={creatingCase}>
                    + 새 건 등록
                  </Button>
                </div>
              )}
            </div>

          ) : viewMode === "card" ? (
            /* ── 카드형 뷰 ── */
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
              {filtered.map((c) => {
                const st = STATUS_MAP[c.status] || STATUS_MAP.processing;
                const isSelected = selected.has(c.id);
                const folderOfCase = caseFolders[c.id] ? folders.find(f => f.id === caseFolders[c.id]) : null;
                return (
                  <div key={c.id}
                    className="relative rounded-2xl border cursor-pointer group transition-all overflow-hidden"
                    style={{
                      background: isSelected ? "var(--ds-color-primary-soft)" : "var(--ds-color-surface)",
                      borderColor: isSelected ? "var(--ds-color-primary)" : "var(--ds-color-border)",
                      boxShadow: "0 2px 12px rgba(0,0,0,0.05)",
                    }}
                    onClick={() => router.push(`/cases/${c.id}/upload`)}>
                    {/* 상태 컬러 탑 바 */}
                    <div className="h-1 w-full" style={{ background: st.color + "55" }} />

                    <div className="p-4">
                      {/* 상단: 체크 + 폴더 + 삭제 */}
                      <div className="flex items-center justify-between mb-3">
                        <button onClick={e => { e.stopPropagation(); toggleSelect(c.id); }}
                          style={{ color: isSelected ? "var(--ds-color-primary)" : "var(--ds-color-text-tertiary)", opacity: isSelected ? 1 : 0 }}
                          className="transition-opacity group-hover:opacity-100">
                          {isSelected ? <CheckSquare size={15} /> : <Square size={15} />}
                        </button>
                        <div className="flex items-center gap-1.5">
                          {folderOfCase && (
                            <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md"
                              style={{ background: folderOfCase.color + "18", color: folderOfCase.color }}>
                              <Folder size={9} />{folderOfCase.name}
                            </span>
                          )}
                          <button onClick={e => handleDeleteSingle(e, c.id)}
                            className="p-1 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity"
                            style={{ color: "var(--ds-color-text-tertiary)" }}
                            onMouseEnter={e => (e.currentTarget.style.color = "var(--ds-color-error-text)")}
                            onMouseLeave={e => (e.currentTarget.style.color = "var(--ds-color-text-tertiary)")}>
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </div>

                      {/* 아이콘 + 제품명 */}
                      <div className="flex items-start gap-3 mb-3">
                        <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
                          style={{ background: st.color + "0e" }}>
                          <FileText size={18} style={{ color: st.color + "99" }} />
                        </div>
                        <div className="min-w-0">
                          <p className="text-[14px] font-bold leading-tight mb-0.5 line-clamp-2"
                            style={{ color: "var(--ds-color-text-heading)" }}>
                            {c.product_name || "제품명 없음"}
                          </p>
                          <p className="text-[11px] truncate" style={{ color: "var(--ds-color-text-tertiary)" }}>
                            {c.importer_name || "수입자 미입력"}
                          </p>
                        </div>
                      </div>

                      {/* 하단: 단계 + 상태 + 날짜 */}
                      <div className="flex items-center justify-between pt-3"
                        style={{ borderTop: "1px solid var(--ds-color-border-subtle)" }}>
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full"
                            style={{ background: st.color + "22", color: st.color }}>
                            {st.label}
                          </span>
                          {c.current_step && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded-md"
                              style={{ background: "var(--ds-color-bg)", color: "var(--ds-color-text-secondary)" }}>
                              {STEP_LABELS[c.current_step]}
                            </span>
                          )}
                        </div>
                        {c.created_at && (
                          <span className="text-[10px] shrink-0" style={{ color: "var(--ds-color-text-tertiary)" }}>
                            {new Date(c.created_at).toLocaleDateString("ko-KR", { month: "2-digit", day: "2-digit" })}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

          ) : (
            /* ── 목록형 뷰 (기본) ── */
            <div className="space-y-2">
              {filtered.map((c) => {
                const st = STATUS_MAP[c.status] || STATUS_MAP.processing;
                const isSelected = selected.has(c.id);
                const folderOfCase = caseFolders[c.id] ? folders.find(f => f.id === caseFolders[c.id]) : null;
                return (
                  <div key={c.id}
                    className="flex items-center gap-3 rounded-xl border px-4 py-3 transition-all cursor-pointer group"
                    style={{
                      background: isSelected ? "var(--ds-color-primary-soft)" : "var(--ds-color-bg)",
                      borderColor: isSelected ? "var(--ds-color-primary)" : "var(--ds-color-border)",
                    }}
                    onClick={() => router.push(`/cases/${c.id}/upload`)}>
                    <button onClick={e => { e.stopPropagation(); toggleSelect(c.id); }}
                      className="shrink-0 transition-colors"
                      style={{ color: isSelected ? "var(--ds-color-primary)" : "var(--ds-color-text-tertiary)" }}>
                      {isSelected ? <CheckSquare size={16} /> : <Square size={16} className="opacity-0 group-hover:opacity-100 transition-opacity" />}
                    </button>
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
                      style={{ background: "var(--ds-color-surface)" }}>
                      <FileText size={14} style={{ color: "var(--ds-color-text-tertiary)" }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-[14px] font-semibold truncate" style={{ color: "var(--ds-color-text-heading)" }}>
                          {c.product_name || "제품명 없음"}
                        </p>
                        {folderOfCase && (
                          <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded-md shrink-0"
                            style={{ background: folderOfCase.color + "18", color: folderOfCase.color }}>
                            <Folder size={10} />{folderOfCase.name}
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] mt-0.5 truncate" style={{ color: "var(--ds-color-text-tertiary)" }}>
                        {c.importer_name || "수입자 미입력"}
                        {c.created_at && (
                          <> · {new Date(c.created_at).toLocaleDateString("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit" })}</>
                        )}
                      </p>
                    </div>
                    {c.current_step && (
                      <span className="text-[11px] px-2 py-1 rounded-md shrink-0"
                        style={{ background: "var(--ds-color-surface)", color: "var(--ds-color-text-secondary)" }}>
                        {STEP_LABELS[c.current_step] || `Step ${c.current_step}`}
                      </span>
                    )}
                    <span className="text-[11px] font-semibold px-2.5 py-1 rounded-full shrink-0"
                      style={{ background: st.color + "22", color: st.color }}>
                      {st.label}
                    </span>
                    <div className="flex items-center gap-1 shrink-0">
                      <button onClick={e => handleDeleteSingle(e, c.id)}
                        className="p-1.5 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                        style={{ color: "var(--ds-color-text-tertiary)" }}
                        onMouseEnter={e => (e.currentTarget.style.color = "var(--ds-color-error-text)")}
                        onMouseLeave={e => (e.currentTarget.style.color = "var(--ds-color-text-tertiary)")}
                        title="삭제"><Trash2 size={13} /></button>
                      <ArrowRight size={14} className="opacity-0 group-hover:opacity-100 transition-opacity"
                        style={{ color: "var(--ds-color-text-tertiary)" }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {search && filtered.length > 0 && (
            <p className="text-[12px] mt-4 text-center" style={{ color: "var(--ds-color-text-tertiary)" }}>
              "{search}" 검색 결과 {filtered.length}건
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
