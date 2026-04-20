"use client";

import { useEffect, useMemo, useState } from "react";
import { Plus, Search, Trash2, Loader2, AlertCircle, ArrowRight } from "lucide-react";
import {
  fetchSynonyms,
  addSynonym,
  deleteSynonym,
  type KeywordSynonym,
} from "./api";

function genKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function SynonymManager() {
  const [items, setItems] = useState<KeywordSynonym[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  // 새 동의어 폼
  const [newHint, setNewHint] = useState("");
  const [newDb, setNewDb] = useState("");
  const [newCountry, setNewCountry] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await fetchSynonyms());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    if (!filter.trim()) return items;
    const f = filter.trim().toLowerCase();
    return items.filter(
      (r) =>
        r.hint_keyword.toLowerCase().includes(f) ||
        r.db_keyword.toLowerCase().includes(f) ||
        (r.country_cond ?? "").toLowerCase().includes(f),
    );
  }, [items, filter]);

  // db_keyword 별 그룹핑
  const grouped = useMemo(() => {
    const g: Record<string, KeywordSynonym[]> = {};
    for (const r of filtered) {
      g[r.db_keyword] = g[r.db_keyword] ?? [];
      g[r.db_keyword].push(r);
    }
    return g;
  }, [filtered]);

  const handleAdd = async () => {
    const hint = newHint.trim();
    const db = newDb.trim();
    if (!hint || !db) {
      alert("hint_keyword 와 db_keyword 모두 입력해주세요.");
      return;
    }
    setBusy(true);
    try {
      await addSynonym(hint, db, newCountry.trim() || null, genKey());
      setNewHint("");
      setNewDb("");
      setNewCountry("");
      await load();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (r: KeywordSynonym) => {
    if (
      !window.confirm(
        `매핑 삭제:\n'${r.hint_keyword}' → '${r.db_keyword}'` +
          (r.country_cond ? ` (국가: ${r.country_cond})` : ""),
      )
    )
      return;
    setBusy(true);
    try {
      await deleteSynonym(r.id);
      await load();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-slate-500">
        <Loader2 size={16} className="animate-spin" /> 불러오는 중...
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-rose-600 flex items-center gap-2">
        <AlertCircle size={16} /> {error}
      </div>
    );
  }

  return (
    <div className="max-w-[1100px] mx-auto">
      <div className="mb-6">
        <h2 className="text-[22px] font-extrabold text-slate-900">
          원재료 동의어 관리
        </h2>
        <p className="text-[14px] text-slate-500 mt-1">
          "돼지" = "돈육" = "돈지" = "pork" 같은 원재료 통용명 매핑을 관리합니다.
          신제품·통용어 등장 시 여기서 즉시 추가하세요. 총 {items.length} 건.
        </p>
      </div>

      {/* 새 동의어 추가 */}
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 mb-5">
        <div className="text-[13px] font-bold text-slate-800 mb-3">➕ 새 동의어 추가</div>
        <div className="grid md:grid-cols-[1fr_auto_1fr_1fr_auto] gap-2 items-center">
          <input
            type="text"
            value={newHint}
            onChange={(e) => setNewHint(e.target.value)}
            placeholder="사용자 입력 키워드 (예: 돈지)"
            className="px-3 py-2 rounded border border-slate-300 text-[13.5px]"
            disabled={busy}
          />
          <ArrowRight size={14} className="text-slate-400 justify-self-center hidden md:block" />
          <input
            type="text"
            value={newDb}
            onChange={(e) => setNewDb(e.target.value)}
            placeholder="DB 키워드 (예: 돼지)"
            className="px-3 py-2 rounded border border-slate-300 text-[13.5px]"
            disabled={busy}
          />
          <input
            type="text"
            value={newCountry}
            onChange={(e) => setNewCountry(e.target.value)}
            placeholder="국가 조건 (선택)"
            className="px-3 py-2 rounded border border-slate-300 text-[13.5px]"
            disabled={busy}
          />
          <button
            onClick={handleAdd}
            disabled={busy || !newHint.trim() || !newDb.trim()}
            className="px-4 h-10 rounded bg-slate-900 text-white text-[13px] font-semibold hover:bg-slate-800 disabled:opacity-50 flex items-center gap-1"
          >
            <Plus size={14} /> 추가
          </button>
        </div>
        <div className="text-[11.5px] text-slate-500 mt-2">
          💡 hint_keyword 가 사용자 원재료명에 포함되면 → db_keyword 로 자동 매핑.
          국가 조건은 특정 국가 수입 시에만 적용 (예: 일본 → 후쿠시마).
        </div>
      </div>

      {/* 검색 */}
      <div className="relative mb-3">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="키워드 검색..."
          className="w-full pl-9 pr-3 py-2 rounded-lg border border-slate-300 text-[13.5px]"
        />
      </div>

      {/* 목록 */}
      <div className="space-y-3">
        {Object.keys(grouped).length === 0 ? (
          <div className="text-slate-400 text-center py-8 text-[14px]">
            {filter ? "검색 결과 없음" : "아직 동의어가 없습니다."}
          </div>
        ) : (
          Object.entries(grouped)
            .sort()
            .map(([dbKw, rows]) => (
              <div
                key={dbKw}
                className="border border-slate-200 rounded-lg bg-white p-3"
              >
                <div className="flex items-center gap-2 mb-2 pb-2 border-b border-slate-100">
                  <span className="text-[12px] text-slate-500">DB 키워드</span>
                  <span className="text-[14px] font-bold text-slate-900 font-mono">
                    {dbKw}
                  </span>
                  <span className="text-[11.5px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-500">
                    {rows.length}건
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {rows.map((r) => (
                    <span
                      key={r.id}
                      className="inline-flex items-center gap-1.5 pl-3 pr-1.5 py-1 rounded-full bg-slate-50 border border-slate-200 text-[12.5px] text-slate-700"
                    >
                      <span className="font-medium">{r.hint_keyword}</span>
                      {r.country_cond && (
                        <span className="text-[10.5px] px-1 rounded bg-amber-100 text-amber-700">
                          {r.country_cond}
                        </span>
                      )}
                      <button
                        onClick={() => handleDelete(r)}
                        disabled={busy}
                        className="w-5 h-5 rounded-full bg-white text-slate-400 hover:text-rose-600 hover:bg-rose-50 flex items-center justify-center"
                        title="삭제"
                      >
                        <Trash2 size={10} />
                      </button>
                    </span>
                  ))}
                </div>
              </div>
            ))
        )}
      </div>
    </div>
  );
}
