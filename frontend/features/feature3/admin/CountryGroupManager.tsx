"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Plus, X, Search, AlertCircle, Loader2, FolderPlus, Globe2,
} from "lucide-react";
import {
  fetchCountryGroups,
  addCountryGroupMember,
  removeCountryGroupMember,
} from "./api";

function genKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function CountryGroupManager() {
  const [groups, setGroups] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 현재 선택된 그룹
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  // 신규 국가 추가
  const [newCountry, setNewCountry] = useState("");
  const [busy, setBusy] = useState(false);

  // 신규 그룹 생성 모드
  const [newGroupMode, setNewGroupMode] = useState(false);
  const [newGroupName, setNewGroupName] = useState("");
  const [newGroupFirstCountry, setNewGroupFirstCountry] = useState("");

  const loadGroups = async () => {
    setLoading(true);
    setError(null);
    try {
      const g = await fetchCountryGroups();
      setGroups(g);
      // 선택 그룹 유지 or 첫 그룹 선택
      const names = Object.keys(g).sort();
      if (!selectedGroup || !g[selectedGroup]) {
        setSelectedGroup(names[0] ?? null);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadGroups();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const groupNames = useMemo(() => Object.keys(groups).sort(), [groups]);
  const memberCount = (g: string) => groups[g]?.length ?? 0;

  const filteredMembers = useMemo(() => {
    if (!selectedGroup) return [];
    const members = groups[selectedGroup] ?? [];
    if (!filter.trim()) return members;
    const f = filter.trim().toLowerCase();
    return members.filter((c) => c.toLowerCase().includes(f));
  }, [groups, selectedGroup, filter]);

  const handleAddCountry = async () => {
    if (!selectedGroup) return;
    const country = newCountry.trim();
    if (!country) return;
    setBusy(true);
    try {
      await addCountryGroupMember(selectedGroup, country, genKey());
      setNewCountry("");
      await loadGroups();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleRemoveCountry = async (country: string) => {
    if (!selectedGroup) return;
    if (!window.confirm(`'${selectedGroup}' 에서 '${country}' 제거하시겠습니까?`)) return;
    setBusy(true);
    try {
      await removeCountryGroupMember(selectedGroup, country);
      await loadGroups();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleCreateGroup = async () => {
    const g = newGroupName.trim();
    const c = newGroupFirstCountry.trim();
    if (!g || !c) {
      alert("그룹명과 첫 국가명을 모두 입력해주세요.");
      return;
    }
    setBusy(true);
    try {
      await addCountryGroupMember(g, c, genKey());
      setNewGroupMode(false);
      setNewGroupName("");
      setNewGroupFirstCountry("");
      setSelectedGroup(g);
      await loadGroups();
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
          국가 그룹 관리
        </h2>
        <p className="text-[14px] text-slate-500 mt-1">
          BSE 36개국·ASF 73개국·동등성인정국 등 법령 기반 국가 그룹을 관리합니다.
          새 국가에서 발병·협정 체결 시 여기서 즉시 반영하세요. 모든 변경은 이력에 기록되어 롤백 가능합니다.
        </p>
      </div>

      <div className="grid md:grid-cols-[280px_1fr] gap-4">
        {/* 좌: 그룹 목록 */}
        <div className="bg-white border border-slate-200 rounded-xl p-3">
          <div className="flex items-center justify-between mb-3 px-1">
            <div className="text-[12.5px] font-semibold text-slate-700">
              그룹 ({groupNames.length})
            </div>
            <button
              onClick={() => setNewGroupMode(!newGroupMode)}
              className="text-[12px] flex items-center gap-1 text-slate-600 hover:text-slate-900"
              title="새 그룹 만들기"
            >
              <FolderPlus size={13} /> 새 그룹
            </button>
          </div>

          {newGroupMode && (
            <div className="mb-3 p-2.5 rounded-lg border border-slate-300 bg-slate-50 space-y-2">
              <input
                type="text"
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                placeholder="그룹명 (예: NEW_RISK_GROUP)"
                className="w-full px-2 py-1.5 rounded border border-slate-300 text-[12.5px]"
              />
              <input
                type="text"
                value={newGroupFirstCountry}
                onChange={(e) => setNewGroupFirstCountry(e.target.value)}
                placeholder="첫 국가 (필수)"
                className="w-full px-2 py-1.5 rounded border border-slate-300 text-[12.5px]"
              />
              <div className="flex gap-1">
                <button
                  onClick={handleCreateGroup}
                  disabled={busy}
                  className="flex-1 h-8 rounded bg-slate-900 text-white text-[12px] font-semibold hover:bg-slate-800 disabled:opacity-50"
                >
                  생성
                </button>
                <button
                  onClick={() => setNewGroupMode(false)}
                  className="px-2 h-8 rounded border border-slate-300 text-slate-600 text-[12px]"
                >
                  취소
                </button>
              </div>
            </div>
          )}

          <div className="space-y-1 max-h-[500px] overflow-y-auto">
            {groupNames.map((g) => (
              <button
                key={g}
                onClick={() => {
                  setSelectedGroup(g);
                  setFilter("");
                }}
                className={`w-full text-left px-3 py-2 rounded-md text-[13px] flex items-center justify-between ${
                  selectedGroup === g
                    ? "bg-slate-900 text-white"
                    : "text-slate-700 hover:bg-slate-50"
                }`}
              >
                <span className="font-mono truncate">{g}</span>
                <span
                  className={`text-[11px] px-1.5 py-0.5 rounded ${
                    selectedGroup === g
                      ? "bg-white/20 text-white"
                      : "bg-slate-100 text-slate-500"
                  }`}
                >
                  {memberCount(g)}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* 우: 멤버 목록 + 편집 */}
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          {!selectedGroup ? (
            <div className="text-center text-slate-400 py-8 text-[14px]">
              왼쪽에서 그룹을 선택하세요
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <div className="text-[12px] text-slate-500">선택된 그룹</div>
                  <div className="text-[17px] font-bold font-mono text-slate-900">
                    {selectedGroup}
                  </div>
                  <div className="text-[12px] text-slate-500 mt-0.5">
                    총 {memberCount(selectedGroup)} 개국
                  </div>
                </div>
                <Globe2 className="text-slate-300" size={32} />
              </div>

              {/* 검색 */}
              <div className="relative mb-3">
                <Search
                  size={14}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                />
                <input
                  type="text"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="국가명으로 검색..."
                  className="w-full pl-9 pr-3 py-2 rounded-lg border border-slate-300 text-[13.5px]"
                />
              </div>

              {/* 국가 추가 */}
              <div className="flex gap-2 mb-4 bg-slate-50 rounded-lg p-2.5 border border-slate-200">
                <input
                  type="text"
                  value={newCountry}
                  onChange={(e) => setNewCountry(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleAddCountry();
                  }}
                  placeholder="추가할 국가명 (예: 파라과이)"
                  className="flex-1 px-3 py-2 rounded border border-slate-300 text-[13.5px]"
                  disabled={busy}
                />
                <button
                  onClick={handleAddCountry}
                  disabled={busy || !newCountry.trim()}
                  className="px-4 rounded bg-slate-900 text-white text-[13px] font-semibold hover:bg-slate-800 disabled:opacity-50 flex items-center gap-1"
                >
                  <Plus size={14} /> 추가
                </button>
              </div>

              {/* 멤버 목록 */}
              <div className="flex flex-wrap gap-1.5 max-h-[420px] overflow-y-auto">
                {filteredMembers.length === 0 ? (
                  <div className="text-slate-400 text-[13px] py-4">
                    {filter
                      ? "검색 결과 없음"
                      : "아직 멤버가 없습니다. 위에서 추가하세요."}
                  </div>
                ) : (
                  filteredMembers.map((country) => (
                    <span
                      key={country}
                      className="inline-flex items-center gap-1.5 pl-3 pr-1.5 py-1.5 rounded-full bg-slate-100 text-slate-800 text-[12.5px]"
                    >
                      {country}
                      <button
                        onClick={() => handleRemoveCountry(country)}
                        disabled={busy}
                        className="w-5 h-5 rounded-full bg-white text-slate-400 hover:text-rose-600 hover:bg-rose-50 flex items-center justify-center disabled:opacity-50"
                        title="제거"
                      >
                        <X size={11} />
                      </button>
                    </span>
                  ))
                )}
              </div>
            </>
          )}
        </div>
      </div>

      <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-[12.5px] text-amber-800">
        💡 <b>주요 그룹 안내</b>:
        <span className="ml-1">
          BSE_36 (반추동물 관련), ASF_73 (돼지 관련), EU_27 (유럽연합), EQUIVALENCE (유기가공식품 동등성인정), SEAFOOD_TREATY (수산물 협약)
        </span>
      </div>
    </div>
  );
}
