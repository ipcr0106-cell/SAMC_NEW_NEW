"use client";

/**
 * 관리자용 법령 업데이트 UI
 *
 * - 법령 PDF 파일 선택 + 메타데이터 입력
 * - POST /admin/laws/upload 호출 → 해당 법령만 재전처리
 * - 등록된 법령 목록(GET /admin/laws) 표시
 */

import { useEffect, useRef, useState } from "react";

interface LawMeta {
  id: string;
  law_name: string;
  고시번호: string;
  시행일: string;
  법령_tier: number;
  total_chunks: number;
  created_at: string;
}

interface UploadResult {
  message: string;
  law_doc_id: string;
  total_chunks: number;
  article_cnt: number;
  table_cnt: number;
  image_cnt: number;
}

const TIER_OPTIONS = ["법률", "시행령", "시행규칙", "고시"] as const;
type Tier = (typeof TIER_OPTIONS)[number];

const TIER_LABEL: Record<number, string> = { 1: "법률", 2: "시행령", 3: "시행규칙", 4: "고시" };

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function LawUploader() {
  // 폼 상태
  const [file, setFile] = useState<File | null>(null);
  const [lawName, setLawName] = useState("");
  const [고시번호, set고시번호] = useState("");
  const [시행일, set시행일] = useState("");
  const [tier, setTier] = useState<Tier>("고시");
  const [category, setCategory] = useState("");

  // 업로드 상태
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 법령 목록
  const [laws, setLaws] = useState<LawMeta[]>([]);
  const [loadingList, setLoadingList] = useState(true);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // 법령 목록 로드
  const fetchLaws = async () => {
    setLoadingList(true);
    try {
      const res = await fetch(`${API_BASE}/admin/laws`);
      if (!res.ok) throw new Error(`서버 오류 (${res.status})`);
      const data = await res.json();
      setLaws(data.laws ?? []);
    } catch (e) {
      console.error("법령 목록 조회 실패:", e);
    } finally {
      setLoadingList(false);
    }
  };

  useEffect(() => { fetchLaws(); }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) { setError("PDF 파일을 선택하세요."); return; }
    if (!lawName.trim()) { setError("법령명을 입력하세요."); return; }
    if (!시행일) { setError("시행일을 입력하세요."); return; }

    setUploading(true);
    setError(null);
    setResult(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("law_name", lawName.trim());
    formData.append("고시번호", 고시번호.trim());
    formData.append("시행일", 시행일);
    formData.append("tier", tier);
    formData.append("category", category.trim() || tier);

    try {
      const res = await fetch(`${API_BASE}/admin/laws/upload`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "업로드 실패");
      setResult(data as UploadResult);
      // 폼 초기화
      setFile(null);
      setLawName("");
      set고시번호("");
      set시행일("");
      setTier("고시");
      setCategory("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      // 목록 새로고침
      fetchLaws();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "알 수 없는 오류");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* 업로드 폼 */}
      <section className="rounded-xl border border-zinc-200 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-lg font-semibold text-zinc-800">법령 파일 업로드</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* PDF 파일 */}
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-700">
              PDF 파일 <span className="text-red-500">*</span>
            </label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.hwpx"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm file:mr-3 file:rounded file:border-0 file:bg-zinc-100 file:px-3 file:py-1 file:text-sm hover:file:bg-zinc-200"
            />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {/* 법령명 */}
            <div>
              <label className="mb-1 block text-sm font-medium text-zinc-700">
                법령명 <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={lawName}
                onChange={(e) => setLawName(e.target.value)}
                placeholder="예: 식품등의 표시기준"
                className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* 고시번호 */}
            <div>
              <label className="mb-1 block text-sm font-medium text-zinc-700">고시번호</label>
              <input
                type="text"
                value={고시번호}
                onChange={(e) => set고시번호(e.target.value)}
                placeholder="예: 제2025-60호"
                className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* 시행일 */}
            <div>
              <label className="mb-1 block text-sm font-medium text-zinc-700">
                시행일 <span className="text-red-500">*</span>
              </label>
              <input
                type="date"
                value={시행일}
                onChange={(e) => set시행일(e.target.value)}
                className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* 법령 계층 */}
            <div>
              <label className="mb-1 block text-sm font-medium text-zinc-700">법령 계층</label>
              <select
                value={tier}
                onChange={(e) => setTier(e.target.value as Tier)}
                className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {TIER_OPTIONS.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>

            {/* 카테고리 */}
            <div className="sm:col-span-2">
              <label className="mb-1 block text-sm font-medium text-zinc-700">
                카테고리 <span className="text-xs text-zinc-400">(비워두면 법령 계층으로 자동 설정)</span>
              </label>
              <input
                type="text"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="예: 표시기준, 부당광고, 기능성허용"
                className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          {/* 에러 메시지 */}
          {error && (
            <p className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600">{error}</p>
          )}

          {/* 완료 메시지 */}
          {result && (
            <div className="rounded-lg bg-green-50 px-4 py-3 text-sm text-green-700">
              <p className="font-semibold">{result.message}</p>
              <p className="mt-1 text-xs text-green-600">
                조문 {result.article_cnt}개 + 표 {result.table_cnt}개 + 이미지 {result.image_cnt}개
                = 총 {result.total_chunks}개 청크 적재 완료
              </p>
            </div>
          )}

          <button
            type="submit"
            disabled={uploading}
            className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {uploading ? "전처리 중..." : "업로드 및 전처리"}
          </button>
        </form>
      </section>

      {/* 등록된 법령 목록 */}
      <section className="rounded-xl border border-zinc-200 bg-white p-6 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-zinc-800">등록된 법령 목록</h2>
          <button
            onClick={fetchLaws}
            className="rounded-lg border border-zinc-300 px-3 py-1 text-xs text-zinc-600 hover:bg-zinc-50"
          >
            새로고침
          </button>
        </div>

        {loadingList ? (
          <p className="text-sm text-zinc-400">로딩 중...</p>
        ) : laws.length === 0 ? (
          <p className="text-sm text-zinc-400">등록된 법령이 없습니다.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-left text-xs font-medium text-zinc-500">
                  <th className="pb-2 pr-4">법령명</th>
                  <th className="pb-2 pr-4">계층</th>
                  <th className="pb-2 pr-4">고시번호</th>
                  <th className="pb-2 pr-4">시행일</th>
                  <th className="pb-2">청크 수</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {laws.map((law) => (
                  <tr key={law.id} className="text-zinc-700">
                    <td className="py-2 pr-4 font-medium">{law.law_name}</td>
                    <td className="py-2 pr-4">
                      <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs">
                        {TIER_LABEL[law.법령_tier] ?? law.법령_tier}
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-zinc-500">{law.고시번호 ?? "-"}</td>
                    <td className="py-2 pr-4 text-zinc-500">{law.시행일 ?? "-"}</td>
                    <td className="py-2 text-zinc-500">{law.total_chunks}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
