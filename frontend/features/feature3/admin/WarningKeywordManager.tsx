"use client";

import { useEffect, useMemo, useState } from "react";
import { Plus, X, Search, Loader2, AlertCircle, ChevronDown, ChevronRight } from "lucide-react";
import {
  fetchWarningKeywords,
  addWarningKeyword,
  deleteWarningKeyword,
} from "./api";

function genKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

const RULE_DESCRIPTIONS: Record<string, string> = {
  gmo_hint: "GMO 표시 대상 원료 힌트 (옥수수, 대두, 카놀라 등)",
  pork_hint: "돼지 유래 원료 감지 힌트 (pork, 돼지 등)",
  ruminant_hint: "반추동물 원료 힌트 (소/양/사슴)",
  hemp_hint: "대마씨·Hemp 관련 힌트",
  honey_hint: "꿀 관련 힌트 (뉴질랜드 kosher 대응 등)",
  apiary_hint: "양봉 제품 힌트 (꿀·로열젤리·프로폴리스)",
  organic_hint: "유기농 (Organic) 표시 힌트",
  japan_13_prefecture: "일본 방사능 검사 13개 도현",
  salt_food_type_hint: "소금류 식품유형 힌트",
};

export function WarningKeywordManager() {
  const [rules, setRules] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedRule, setSelectedRule] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  // 새 키워드 추가
  const [newKeyword, setNewKeyword] = useState("");
  const [busy, setBusy] = useState(false);

  // 신규 규칙 생성
  const [newRuleMode, setNewRuleMode] = useState(false);
  const [newRuleId, setNewRuleId] = useState("");
  const [newRuleFirstKw, setNewRuleFirstKw] = useState("");

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetchWarningKeywords();
      setRules(r);
      const names = Object.keys(r).sort();
      if (!selectedRule || !r[selectedRule]) setSelectedRule(names[0] ?? null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ruleNames = useMemo(() => Object.keys(rules).sort(), [rules]);
  const keywords = selectedRule ? rules[selectedRule] ?? [] : [];
  const filtered = useMemo(() => {
    if (!filter.trim()) return keywords;
    const f = filter.trim().toLowerCase();
    return keywords.filter((k) => k.toLowerCase().includes(f));
  }, [keywords, filter]);

  const handleAdd = async () => {
    if (!selectedRule) return;
    const kw = newKeyword.trim();
    if (!kw) return;
    setBusy(true);
    try {
      await addWarningKeyword(selectedRule, kw, genKey());
      setNewKeyword("");
      await load();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async (kw: string) => {
    if (!selectedRule) return;
    if (!window.confirm(`'${selectedRule}' 에서 '${kw}' 제거?`)) return;
    setBusy(true);
    try {
      await deleteWarningKeyword(selectedRule, kw);
      await load();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleCreateRule = async () => {
    const rid = newRuleId.trim();
    const kw = newRuleFirstKw.trim();
    if (!rid || !kw) {
      alert("규칙 ID 와 첫 키워드 입력 필요");
      return;
    }
    setBusy(true);
    try {
      await addWarningKeyword(rid, kw, genKey());
      setNewRuleMode(false);
      setNewRuleId("");
      setNewRuleFirstKw("");
      setSelectedRule(rid);
      await load();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <Loader2 size={16} className="animate-spin text-slate-500" />;
  if (error)
    return (
      <div className="text-rose-600 flex items-center gap-2">
        <AlertCircle size={16} /> {error}
      </div>
    );

  return (
    <div className="max-w-[1100px] mx-auto">
      <div className="mb-6">
        <h2 className="text-[22px] font-extrabold text-slate-900">
          경고 키워드 관리
        </h2>
        <p className="text-[14px] text-slate-500 mt-1">
          GMO·방사능·대마 등 원재료 경고 발동 조건을 관리합니다. 규칙별로 키워드를 추가/삭제하세요.
        </p>
      </div>

      <div className="grid md:grid-cols-[300px_1fr] gap-4">
        {/* 좌: 규칙 목록 */}
        <div className="bg-white border border-slate-200 rounded-xl p-3">
          <div className="flex items-center justify-between mb-3 px-1">
            <div className="text-[12.5px] font-semibold text-slate-700">
              규칙 ({ruleNames.length})
            </div>
            <button
              onClick={() => setNewRuleMode(!newRuleMode)}
              className="text-[12px] text-slate-600 hover:text-slate-900"
            >
              + 새 규칙
            </button>
          </div>

          {newRuleMode && (
            <div className="mb-3 p-2.5 rounded-lg border border-slate-300 bg-slate-50 space-y-2">
              <input
                value={newRuleId}
                onChange={(e) => setNewRuleId(e.target.value)}
                placeholder="규칙 ID (예: new_hint)"
                className="w-full px-2 py-1.5 rounded border border-slate-300 text-[12.5px]"
              />
              <input
                value={newRuleFirstKw}
                onChange={(e) => setNewRuleFirstKw(e.target.value)}
                placeholder="첫 키워드 (필수)"
                className="w-full px-2 py-1.5 rounded border border-slate-300 text-[12.5px]"
              />
              <div className="flex gap-1">
                <button
                  onClick={handleCreateRule}
                  disabled={busy}
                  className="flex-1 h-8 rounded bg-slate-900 text-white text-[12px] font-semibold disabled:opacity-50"
                >
                  생성
                </button>
                <button
                  onClick={() => setNewRuleMode(false)}
                  className="px-2 h-8 rounded border border-slate-300 text-[12px]"
                >
                  취소
                </button>
              </div>
            </div>
          )}

          <div className="space-y-1 max-h-[500px] overflow-y-auto">
            {ruleNames.map((r) => (
              <button
                key={r}
                onClick={() => {
                  setSelectedRule(r);
                  setFilter("");
                }}
                className={`w-full text-left px-3 py-2 rounded-md text-[13px] ${
                  selectedRule === r
                    ? "bg-slate-900 text-white"
                    : "text-slate-700 hover:bg-slate-50"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono truncate">{r}</span>
                  <span
                    className={`text-[11px] px-1.5 py-0.5 rounded ${
                      selectedRule === r
                        ? "bg-white/20 text-white"
                        : "bg-slate-100 text-slate-500"
                    }`}
                  >
                    {rules[r]?.length ?? 0}
                  </span>
                </div>
                {RULE_DESCRIPTIONS[r] && selectedRule !== r && (
                  <div className="text-[11px] text-slate-500 mt-0.5 truncate">
                    {RULE_DESCRIPTIONS[r]}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* 우: 키워드 편집 */}
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          {!selectedRule ? (
            <div className="text-center text-slate-400 py-8">
              왼쪽에서 규칙 선택
            </div>
          ) : (
            <>
              <div className="mb-4">
                <div className="text-[12px] text-slate-500">규칙 ID</div>
                <div className="text-[17px] font-bold font-mono">{selectedRule}</div>
                {RULE_DESCRIPTIONS[selectedRule] && (
                  <div className="text-[12.5px] text-slate-600 mt-1">
                    {RULE_DESCRIPTIONS[selectedRule]}
                  </div>
                )}
                <div className="text-[12px] text-slate-500 mt-0.5">
                  {keywords.length} 개 키워드
                </div>
              </div>

              <div className="relative mb-3">
                <Search
                  size={14}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                />
                <input
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="키워드 검색..."
                  className="w-full pl-9 pr-3 py-2 rounded-lg border border-slate-300 text-[13.5px]"
                />
              </div>

              <div className="flex gap-2 mb-4 bg-slate-50 rounded-lg p-2.5 border border-slate-200">
                <input
                  value={newKeyword}
                  onChange={(e) => setNewKeyword(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleAdd();
                  }}
                  placeholder="추가할 키워드"
                  className="flex-1 px-3 py-2 rounded border border-slate-300 text-[13.5px]"
                  disabled={busy}
                />
                <button
                  onClick={handleAdd}
                  disabled={busy || !newKeyword.trim()}
                  className="px-4 rounded bg-slate-900 text-white text-[13px] font-semibold disabled:opacity-50 flex items-center gap-1"
                >
                  <Plus size={14} /> 추가
                </button>
              </div>

              <div className="flex flex-wrap gap-1.5 max-h-[400px] overflow-y-auto">
                {filtered.length === 0 ? (
                  <div className="text-slate-400 text-[13px] py-4">
                    {filter ? "검색 결과 없음" : "키워드가 없습니다"}
                  </div>
                ) : (
                  filtered.map((kw) => (
                    <span
                      key={kw}
                      className="inline-flex items-center gap-1.5 pl-3 pr-1.5 py-1 rounded-full bg-slate-100 text-slate-800 text-[12.5px]"
                    >
                      {kw}
                      <button
                        onClick={() => handleRemove(kw)}
                        disabled={busy}
                        className="w-5 h-5 rounded-full bg-white text-slate-400 hover:text-rose-600 hover:bg-rose-50 flex items-center justify-center"
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
    </div>
  );
}
