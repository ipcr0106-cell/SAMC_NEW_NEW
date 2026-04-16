"use client";

type LawTier = 1 | 2 | 3 | 4;

const TIER_LABEL: Record<LawTier, string> = {
  1: "법률",
  2: "시행령",
  3: "시행규칙",
  4: "고시",
};

const TIER_CLS: Record<LawTier, string> = {
  1: "bg-red-50 text-red-700 border-red-200",
  2: "bg-amber-50 text-amber-700 border-amber-200",
  3: "bg-blue-50 text-blue-700 border-blue-200",
  4: "bg-slate-100 text-slate-600 border-slate-200",
};

const LAW_LIST: {
  id: number;
  name: string;
  notice: string;
  effective: string;
  tier: LawTier;
  category: string;
  chunks: number;
  updatedAt: string;
}[] = [
  { id: 1, name: "식품위생법",                             notice: "법률 제20346호",  effective: "2024-06-21", tier: 1, category: "기본법",       chunks: 312, updatedAt: "2025-09-01" },
  { id: 2, name: "수입식품안전관리 특별법",                  notice: "법률 제19964호",  effective: "2024-01-16", tier: 1, category: "수입규제",     chunks: 204, updatedAt: "2025-09-01" },
  { id: 3, name: "식품 등의 표시·광고에 관한 법률",          notice: "법률 제20175호",  effective: "2024-02-13", tier: 1, category: "표시기준",     chunks: 189, updatedAt: "2025-09-01" },
  { id: 4, name: "식품의 기준 및 규격",                     notice: "제2024-46호",     effective: "2024-11-01", tier: 4, category: "식품공전",     chunks: 1847, updatedAt: "2025-10-15" },
  { id: 5, name: "식품 등의 표시기준",                      notice: "제2024-51호",     effective: "2024-12-01", tier: 4, category: "표시기준",     chunks: 423, updatedAt: "2025-10-15" },
  { id: 6, name: "식품첨가물의 기준 및 규격",               notice: "제2024-33호",     effective: "2024-09-01", tier: 4, category: "첨가물",       chunks: 934, updatedAt: "2025-09-20" },
  { id: 7, name: "건강기능식품의 기준 및 규격",             notice: "제2024-28호",     effective: "2024-07-01", tier: 4, category: "건강기능",     chunks: 667, updatedAt: "2025-09-20" },
];

const totalChunks = LAW_LIST.reduce((s, l) => s + l.chunks, 0);

export default function AdminLawsPage() {
  return (
    <div className="min-h-screen bg-slate-50">
      {/* 헤더 */}
      <header className="bg-white border-b border-slate-200/60 sticky top-0 z-50">
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center">
          <h1 className="text-sm font-semibold text-slate-800">법령 DB 관리 (F4 어드민)</h1>
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-6 py-6">
        {/* 설명 */}
        <div className="mb-6">
          <h2 className="text-xl font-bold text-slate-900">법령 DB 관리</h2>
          <p className="text-sm text-slate-500 mt-0.5">법령 파일을 업로드해 벡터 DB를 갱신합니다. PDF 및 HWPX 파일을 지원합니다.</p>
        </div>

        {/* 통계 카드 */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          {[
            { label: "등재 법령",   value: `${LAW_LIST.length}종` },
            { label: "전체 청크",   value: totalChunks.toLocaleString() },
            { label: "마지막 갱신", value: "2025-10-15" },
          ].map((s) => (
            <div key={s.label} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="text-xs text-slate-500 mb-1">{s.label}</div>
              <div className="text-xl font-bold text-slate-900">{s.value}</div>
            </div>
          ))}
        </div>

        {/* 업로드 섹션 */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 mb-6">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">법령 파일 업로드</h2>
          <div className="grid grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">법령명 <span className="text-red-500">*</span></label>
              <input
                type="text"
                placeholder="예: 식품의 기준 및 규격"
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 placeholder-slate-400"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">고시번호</label>
              <input
                type="text"
                placeholder="예: 제2024-46호"
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 placeholder-slate-400"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">시행일 <span className="text-red-500">*</span></label>
              <input
                type="date"
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">법령 등급 <span className="text-red-500">*</span></label>
              <select
                defaultValue="4"
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 text-slate-700"
              >
                <option value="1">1 — 법률</option>
                <option value="2">2 — 시행령</option>
                <option value="3">3 — 시행규칙</option>
                <option value="4">4 — 고시</option>
              </select>
            </div>
            <div className="col-span-2">
              <label className="block text-xs font-medium text-slate-600 mb-1">카테고리</label>
              <input
                type="text"
                placeholder="예: 식품공전, 표시기준, 첨가물, ..."
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 placeholder-slate-400"
              />
            </div>
          </div>

          {/* 파일 드롭존 */}
          <div className="border-2 border-dashed border-slate-200 rounded-xl p-8 text-center hover:border-blue-400 hover:bg-slate-50 transition-colors cursor-pointer mb-4">
            <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center mx-auto mb-3">
              <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
            </div>
            <p className="text-sm font-medium text-slate-700">파일을 드래그하거나 클릭하여 업로드</p>
            <p className="text-xs text-slate-400 mt-1">PDF, HWPX 파일 지원 · 최대 100MB</p>
            <input type="file" accept=".pdf,.hwpx" className="hidden" />
          </div>

          <div className="flex justify-end">
            <button className="text-sm bg-blue-600 text-white font-medium px-6 py-2.5 rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
              전처리 및 업로드
            </button>
          </div>
        </div>

        {/* 법령 목록 */}
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between">
            <span className="text-sm font-semibold text-slate-700">등재된 법령 목록</span>
            <span className="text-xs text-slate-400">총 {LAW_LIST.length}종 · {totalChunks.toLocaleString()} 청크</span>
          </div>
          <div className="divide-y divide-slate-100">
            {LAW_LIST.map((law) => (
              <div key={law.id} className="px-5 py-4 flex items-start gap-4 hover:bg-slate-50 transition-colors">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="text-sm font-semibold text-slate-900">{law.name}</span>
                    <span className={`text-xs px-1.5 py-0.5 rounded border ${TIER_CLS[law.tier]}`}>
                      {TIER_LABEL[law.tier]}
                    </span>
                    <span className="text-xs bg-slate-100 text-slate-500 border border-slate-200 px-1.5 py-0.5 rounded">
                      {law.category}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-slate-400">
                    <span>{law.notice}</span>
                    <span>·</span>
                    <span>시행 {law.effective}</span>
                    <span>·</span>
                    <span>{law.chunks.toLocaleString()} 청크</span>
                    <span>·</span>
                    <span>갱신 {law.updatedAt}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button className="text-xs border border-slate-200 text-slate-600 px-2.5 py-1 rounded-lg hover:bg-slate-50 transition-colors">
                    재처리
                  </button>
                  <button className="text-xs border border-red-200 text-red-600 px-2.5 py-1 rounded-lg hover:bg-red-50 transition-colors">
                    삭제
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
