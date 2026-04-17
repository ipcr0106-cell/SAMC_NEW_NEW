"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { apiClient } from "@/services/apiClient";

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

const TIER_OPTIONS = [
  { value: "법률", label: "1 — 법률" },
  { value: "시행령", label: "2 — 시행령" },
  { value: "시행규칙", label: "3 — 시행규칙" },
  { value: "고시", label: "4 — 고시" },
];

interface LawDoc {
  id: string;
  law_name: string;
  고시번호: string | null;
  시행일: string | null;
  법령_tier: LawTier;
  total_chunks: number;
  created_at: string;
}

type UploadStatus = "idle" | "uploading" | "success" | "error";

interface UploadResult {
  law_doc_id: string;
  total_chunks: number;
  keywords_extracted: number;
  image_types_pending: number;
}

export default function AdminLawsPage() {
  // ── 법령 목록 ──
  const [laws, setLaws] = useState<LawDoc[]>([]);
  const [loadingLaws, setLoadingLaws] = useState(true);

  // ── 업로드 폼 ──
  const [lawName, setLawName] = useState("");
  const [tier, setTier] = useState("고시");
  const [category, setCategory] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── 업로드 상태 ──
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>("idle");
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recoveryMessage, setRecoveryMessage] = useState<string | null>(null);

  // ── 법령 목록 로드 ──
  const fetchLaws = useCallback(async () => {
    setLoadingLaws(true);
    try {
      const res = await apiClient.get("/admin/laws");
      setLaws(res.data.laws ?? []);
    } catch {
      // silent
    } finally {
      setLoadingLaws(false);
    }
  }, []);

  useEffect(() => {
    fetchLaws();
  }, [fetchLaws]);

  // ── 파일 선택 ──
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const ext = f.name.split(".").pop()?.toLowerCase();
    if (ext !== "pdf" && ext !== "hwpx") {
      setError("PDF 또는 HWPX 파일만 업로드 가능합니다.");
      return;
    }
    setFile(f);
    setError(null);
    setRecoveryMessage(null);
  };

  // ── 업로드 실행 ──
  const handleUpload = async () => {
    if (!lawName.trim()) {
      setError("법령명을 입력해주세요.");
      return;
    }
    if (!file) {
      setError("파일을 선택해주세요.");
      return;
    }

    setError(null);
    setRecoveryMessage(null);
    setUploadStatus("uploading");
    setUploadResult(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("law_name", lawName);
    formData.append("고시번호", ""); // PDF에서 자동 파싱
    formData.append("시행일", "");   // PDF에서 자동 파싱
    formData.append("tier", tier);
    formData.append("category", category || lawName);

    try {
      const res = await apiClient.post("/admin/laws/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 600000, // 10분 (대용량 법령 처리)
      });
      setUploadStatus("success");
      setUploadResult(res.data);
      // 목록 새로고침
      fetchLaws();
      // 폼 초기화
      setLawName("");
      setCategory("");
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (e: unknown) {
      setUploadStatus("error");

      // 크래시 에러 상세 파싱
      if (e && typeof e === "object" && "response" in e) {
        const resp = (e as { response?: { data?: { detail?: { error?: string; message?: string; recovery?: string } | string } } }).response;
        const detail = resp?.data?.detail;

        if (detail && typeof detail === "object" && detail.error === "PREPROCESS_FAILED") {
          setError(`법령 업데이트 중 오류가 발생했습니다: ${detail.message}`);
          setRecoveryMessage(
            "기존 데이터가 초기화된 상태입니다. 파일을 다시 업로드하여 재시도해주세요."
          );
        } else {
          const msg = typeof detail === "string" ? detail : "알 수 없는 오류가 발생했습니다.";
          setError(msg);
        }
      } else {
        setError("서버 연결에 실패했습니다. 네트워크를 확인해주세요.");
      }
    }
  };

  // ── 통계 ──
  const totalChunks = laws.reduce((s, l) => s + (l.total_chunks ?? 0), 0);

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
          <p className="text-sm text-slate-500 mt-0.5">
            법령 파일을 업로드해 벡터 DB를 갱신합니다. 고시번호와 시행일은 PDF에서 자동 추출됩니다.
          </p>
        </div>

        {/* 오류 / 성공 배너 */}
        {error && (
          <div className="mb-4 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
            <p className="text-sm text-red-700 font-medium">{error}</p>
            {recoveryMessage && (
              <p className="text-sm text-red-600 mt-1">{recoveryMessage}</p>
            )}
          </div>
        )}

        {uploadStatus === "success" && uploadResult && (
          <div className="mb-4 bg-green-50 border border-green-200 rounded-xl px-4 py-3">
            <p className="text-sm text-green-700 font-medium">법령 업데이트 완료</p>
            <p className="text-xs text-green-600 mt-1">
              {uploadResult.total_chunks}개 청크 적재 / 금지 키워드 {uploadResult.keywords_extracted}개 추출
              {uploadResult.image_types_pending > 0 && ` / 이미지 위반 유형 ${uploadResult.image_types_pending}개 검토 대기`}
            </p>
          </div>
        )}

        {/* 통계 카드 */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          {[
            { label: "등재 법령", value: loadingLaws ? "..." : `${laws.length}종` },
            { label: "전체 청크", value: loadingLaws ? "..." : totalChunks.toLocaleString() },
            { label: "마지막 갱신", value: laws.length > 0 ? laws[0].created_at?.slice(0, 10) ?? "-" : "-" },
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
              <label className="block text-xs font-medium text-slate-600 mb-1">
                법령명 <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={lawName}
                onChange={(e) => setLawName(e.target.value)}
                placeholder="예: 식품등의 표시기준"
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 placeholder-slate-400"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">법령 등급</label>
              <select
                value={tier}
                onChange={(e) => setTier(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 text-slate-700"
              >
                {TIER_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div className="col-span-2">
              <label className="block text-xs font-medium text-slate-600 mb-1">카테고리</label>
              <input
                type="text"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="예: 표시기준, 부당광고, 기능성허용, ..."
                className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200 placeholder-slate-400"
              />
            </div>
          </div>

          {/* 파일 드롭존 */}
          <div
            onClick={() => fileInputRef.current?.click()}
            className="border-2 border-dashed border-slate-200 rounded-xl p-8 text-center hover:border-blue-400 hover:bg-slate-50 transition-colors cursor-pointer mb-4"
          >
            <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center mx-auto mb-3">
              <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
            </div>
            {file ? (
              <p className="text-sm font-medium text-blue-700">{file.name}</p>
            ) : (
              <>
                <p className="text-sm font-medium text-slate-700">파일을 드래그하거나 클릭하여 업로드</p>
                <p className="text-xs text-slate-400 mt-1">PDF, HWPX 파일 지원</p>
              </>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.hwpx"
              onChange={handleFileChange}
              className="hidden"
            />
          </div>

          <div className="flex justify-end">
            <button
              onClick={handleUpload}
              disabled={uploadStatus === "uploading"}
              className={`text-sm font-medium px-6 py-2.5 rounded-lg transition-colors flex items-center gap-2 ${
                uploadStatus === "uploading"
                  ? "bg-slate-300 text-slate-500 cursor-not-allowed"
                  : "bg-blue-600 text-white hover:bg-blue-700"
              }`}
            >
              {uploadStatus === "uploading" ? (
                <>
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  전처리 중...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                  </svg>
                  전처리 및 업로드
                </>
              )}
            </button>
          </div>
        </div>

        {/* 법령 목록 */}
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between">
            <span className="text-sm font-semibold text-slate-700">등재된 법령 목록</span>
            <span className="text-xs text-slate-400">
              총 {laws.length}종 · {totalChunks.toLocaleString()} 청크
            </span>
          </div>
          <div className="divide-y divide-slate-100">
            {loadingLaws ? (
              <div className="px-5 py-8 text-center text-sm text-slate-400">불러오는 중...</div>
            ) : laws.length === 0 ? (
              <div className="px-5 py-8 text-center text-sm text-slate-400">등재된 법령이 없습니다.</div>
            ) : (
              laws.map((law) => (
                <div key={law.id} className="px-5 py-4 flex items-start gap-4 hover:bg-slate-50 transition-colors">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <span className="text-sm font-semibold text-slate-900">{law.law_name}</span>
                      <span className={`text-xs px-1.5 py-0.5 rounded border ${TIER_CLS[law.법령_tier]}`}>
                        {TIER_LABEL[law.법령_tier]}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-slate-400">
                      {law.고시번호 && <span>{law.고시번호}</span>}
                      {law.시행일 && (
                        <>
                          <span>·</span>
                          <span>시행 {law.시행일}</span>
                        </>
                      )}
                      <span>·</span>
                      <span>{(law.total_chunks ?? 0).toLocaleString()} 청크</span>
                      <span>·</span>
                      <span>갱신 {law.created_at?.slice(0, 10) ?? "-"}</span>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
