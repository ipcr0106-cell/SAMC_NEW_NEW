"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Upload,
  X,
  FileText,
  ArrowLeft,
  RefreshCw,
  Check,
  AlertCircle,
  Loader2,
} from "lucide-react";

// ── 타입 ──

interface LawInfo {
  law_name: string;
  tier: string;
  description: string;
  features: string[];
}

interface UploadSlot {
  law_name: string;
  file: File | null;
}

interface ProgressEntry {
  feature: string;
  law_name: string;
  stage: string;
  percent: number;
}

interface TaskResult {
  feature: string;
  law_name: string;
  status: string;
  [key: string]: unknown;
}

// ── API ──

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace("/api/v1", "") ||
  "http://localhost:8000";

async function fetchLawList(): Promise<LawInfo[]> {
  const res = await fetch(`${API_BASE}/admin/law-update/laws`);
  if (!res.ok) throw new Error("법령 목록 조회 실패");
  const data = await res.json();
  return data.laws;
}

// ── 컴포넌트 ──

const STAGE_LABELS: Record<string, string> = {
  chunking: "청킹 중",
  extracting: "기준치 추출 중",
  post_processing: "후처리 중",
  image_types: "이미지 유형 추출 중",
  done: "완료",
};

const TIER_COLORS: Record<string, string> = {
  법률: "bg-red-100 text-red-700",
  시행령: "bg-amber-100 text-amber-700",
  시행규칙: "bg-blue-100 text-blue-700",
  고시: "bg-slate-100 text-slate-600",
};

export default function LawUpdatePage() {
  const router = useRouter();
  const [laws, setLaws] = useState<LawInfo[]>([]);
  const [slots, setSlots] = useState<UploadSlot[]>([]);
  const [loading, setLoading] = useState(true);

  // 업데이트 진행 상태
  const [isUpdating, setIsUpdating] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [progress, setProgress] = useState<Record<string, ProgressEntry>>({});
  const [results, setResults] = useState<TaskResult[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [complete, setComplete] = useState(false);

  // 법령 목록 로드
  useEffect(() => {
    fetchLawList()
      .then((list) => {
        setLaws(list);
        setSlots(list.map((l) => ({ law_name: l.law_name, file: null })));
      })
      .catch((e) => console.error(e))
      .finally(() => setLoading(false));
  }, []);

  const hasFiles = slots.some((s) => s.file !== null);

  const handleFileDrop = (index: number, file: File) => {
    setSlots((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], file };
      return next;
    });
  };

  const handleFileRemove = (index: number) => {
    setSlots((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], file: null };
      return next;
    });
  };

  const handleUpdate = async () => {
    const activeSlots = slots.filter((s) => s.file !== null);
    if (activeSlots.length === 0) return;

    setIsUpdating(true);
    setShowModal(true);
    setProgress({});
    setResults([]);
    setErrors([]);
    setComplete(false);

    const formData = new FormData();
    const lawNames: string[] = [];

    for (const slot of activeSlots) {
      formData.append("files", slot.file!);
      lawNames.push(slot.law_name);
    }
    formData.append("law_names", JSON.stringify(lawNames));

    try {
      const res = await fetch(`${API_BASE}/admin/law-update/upload`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        setErrors([err.detail || "업로드 실패"]);
        setComplete(true);
        setIsUpdating(false);
        return;
      }

      // SSE 스트림 파싱
      const reader = res.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        setErrors(["스트림 읽기 실패"]);
        setComplete(true);
        setIsUpdating(false);
        return;
      }

      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data:")) {
            const jsonStr = line.slice(5).trim();
            if (!jsonStr) continue;
            try {
              const event = JSON.parse(jsonStr);

              if (event.type === "progress") {
                const key = `${event.feature}::${event.law_name}`;
                setProgress((prev) => ({ ...prev, [key]: event }));
              } else if (event.type === "result") {
                setResults((prev) => [...prev, event]);
              } else if (event.type === "error") {
                setErrors((prev) => [...prev, event.message || "알 수 없는 오류"]);
              } else if (event.type === "complete") {
                setComplete(true);
              }
            } catch {
              // SSE 파싱 오류 무시
            }
          }
        }
      }
    } catch (e) {
      setErrors([(e as Error).message]);
    }

    setComplete(true);
    setIsUpdating(false);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0f1117] flex items-center justify-center">
        <Loader2 className="w-6 h-6 text-emerald-400 animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white">
      {/* ── 상단 네비 ── */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-[#0f1117]/80 backdrop-blur-xl border-b border-white/5">
        <div className="max-w-[1280px] mx-auto px-8 h-[64px] flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push("/dashboard")}
              className="flex items-center gap-2 text-white/50 hover:text-white transition-colors"
            >
              <ArrowLeft size={16} />
              <span className="text-[13px]">대시보드</span>
            </button>
            <div className="w-px h-5 bg-white/10" />
            <h1 className="text-[15px] font-bold text-white">법령 DB 관리</h1>
          </div>
        </div>
      </nav>

      {/* ── 본문 ── */}
      <div className="pt-[96px] pb-20 max-w-[1280px] mx-auto px-8">
        {/* 설명 */}
        <div className="mb-8">
          <h2 className="text-[28px] font-extrabold text-slate-900">
            법령 DB 업데이트
          </h2>
          <p className="text-[14px] text-slate-500 mt-2">
            개정된 법령 파일을 업로드하면 관련 기능의 DB가 자동으로 재구축됩니다.
            파일을 넣은 법령만 처리됩니다.
          </p>
        </div>

        {/* ── 법령별 업로드 카드 그리드 ── */}
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {slots.map((slot, i) => {
            const law = laws[i];
            const tierColor = TIER_COLORS[law.tier] || TIER_COLORS["고시"];

            return (
              <LawUploadCard
                key={law.law_name}
                lawName={law.law_name}
                tier={law.tier}
                tierColor={tierColor}
                description={law.description}
                features={law.features}
                file={slot.file}
                onFileDrop={(f) => handleFileDrop(i, f)}
                onFileRemove={() => handleFileRemove(i)}
                disabled={isUpdating}
              />
            );
          })}
        </div>

        {/* ── 업데이트 버튼 ── */}
        <div className="mt-8 flex justify-center">
          <button
            onClick={handleUpdate}
            disabled={!hasFiles || isUpdating}
            className="flex items-center gap-2.5 bg-[#0f1117] text-white font-semibold text-[14px] px-10 py-3.5 rounded-full hover:bg-slate-800 transition-all disabled:opacity-40 disabled:cursor-not-allowed hover:shadow-lg"
          >
            <RefreshCw size={16} className={isUpdating ? "animate-spin" : ""} />
            {isUpdating ? "업데이트 진행 중..." : "선택한 법령 업데이트"}
          </button>
        </div>
      </div>

      {/* ── 진행도 모달 ── */}
      {showModal && (
        <ProgressModal
          laws={laws}
          progress={progress}
          results={results}
          errors={errors}
          complete={complete}
          onClose={() => {
            setShowModal(false);
            // 완료 후 파일 슬롯 초기화
            if (complete) {
              setSlots(laws.map((l) => ({ law_name: l.law_name, file: null })));
            }
          }}
        />
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
// 법령 업로드 카드
// ═══════════════════════════════════════════

function LawUploadCard({
  lawName,
  tier,
  tierColor,
  description,
  features,
  file,
  onFileDrop,
  onFileRemove,
  disabled,
}: {
  lawName: string;
  tier: string;
  tierColor: string;
  description: string;
  features: string[];
  file: File | null;
  onFileDrop: (f: File) => void;
  onFileRemove: () => void;
  disabled: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) onFileDrop(f);
  };

  return (
    <div
      className={`rounded-2xl border p-5 transition-all ${
        file
          ? "border-emerald-300 bg-emerald-50/50 shadow-sm"
          : dragOver
          ? "border-blue-300 bg-blue-50/30"
          : "border-slate-200 bg-white hover:border-slate-300"
      }`}
    >
      {/* 헤더 */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${tierColor}`}>
              {tier}
            </span>
            <span className="text-[10px] text-slate-400">
              {features.join(", ")}
            </span>
          </div>
          <h3 className="text-[13px] font-bold text-slate-900 leading-tight truncate">
            {lawName}
          </h3>
          <p className="text-[11px] text-slate-400 mt-0.5 truncate">{description}</p>
        </div>
      </div>

      {/* 드롭존 */}
      {file ? (
        <div className="flex items-center gap-2 bg-white rounded-lg border border-emerald-200 px-3 py-2">
          <FileText size={14} className="text-emerald-500 shrink-0" />
          <span className="text-[12px] text-slate-700 truncate flex-1">
            {file.name}
          </span>
          <span className="text-[10px] text-slate-400 shrink-0">
            {(file.size / 1024 / 1024).toFixed(1)}MB
          </span>
          {!disabled && (
            <button
              onClick={onFileRemove}
              className="text-slate-300 hover:text-red-500 transition-colors shrink-0"
            >
              <X size={14} />
            </button>
          )}
        </div>
      ) : (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => !disabled && inputRef.current?.click()}
          className={`flex flex-col items-center justify-center border-2 border-dashed rounded-xl py-5 cursor-pointer transition-colors ${
            dragOver
              ? "border-blue-400 bg-blue-50/50"
              : "border-slate-200 hover:border-slate-300"
          } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
        >
          <Upload size={18} className="text-slate-300 mb-1.5" />
          <p className="text-[11px] text-slate-400">PDF / HWPX</p>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.hwpx"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onFileDrop(f);
              e.target.value = "";
            }}
          />
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
// 진행도 모달
// ═══════════════════════════════════════════

function ProgressModal({
  laws,
  progress,
  results,
  errors,
  complete,
  onClose,
}: {
  laws: LawInfo[];
  progress: Record<string, ProgressEntry>;
  results: TaskResult[];
  errors: string[];
  complete: boolean;
  onClose: () => void;
}) {
  // 어떤 법령들이 업데이트되고 있는지
  const activeLaws = new Set<string>();
  for (const key of Object.keys(progress)) {
    const lawName = key.split("::")[1];
    activeLaws.add(lawName);
  }
  for (const r of results) {
    activeLaws.add(r.law_name);
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden">
        {/* 헤더 */}
        <div className="bg-[#0f1117] px-6 py-4 flex items-center justify-between">
          <h3 className="text-[15px] font-bold text-white">
            법령 업데이트 진행 현황
          </h3>
          {complete && (
            <button
              onClick={onClose}
              className="text-white/40 hover:text-white transition-colors"
            >
              <X size={18} />
            </button>
          )}
        </div>

        {/* 진행도 리스트 */}
        <div className="px-6 py-5 max-h-[60vh] overflow-y-auto space-y-4">
          {Array.from(activeLaws).map((lawName) => {
            const law = laws.find((l) => l.law_name === lawName);
            if (!law) return null;

            return (
              <div key={lawName} className="space-y-2">
                <p className="text-[13px] font-semibold text-slate-800">
                  {lawName}
                </p>

                {law.features.map((feature) => {
                  const key = `${feature}::${lawName}`;
                  const prog = progress[key];
                  const result = results.find(
                    (r) => r.feature === feature && r.law_name === lawName
                  );
                  const isDone = result?.status === "success";
                  const percent = isDone ? 100 : prog?.percent || 0;
                  const stage = isDone
                    ? "완료"
                    : STAGE_LABELS[prog?.stage || ""] || "대기 중";

                  return (
                    <div key={key} className="ml-4">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[12px] text-slate-500">
                          {feature} 전처리
                        </span>
                        <span className="text-[11px] text-slate-400 flex items-center gap-1">
                          {isDone && <Check size={12} className="text-emerald-500" />}
                          {stage}
                        </span>
                      </div>
                      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${
                            isDone ? "bg-emerald-500" : "bg-blue-500"
                          }`}
                          style={{ width: `${percent}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          })}

          {/* 에러 */}
          {errors.length > 0 && (
            <div className="mt-4 space-y-2">
              {errors.map((err, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 bg-red-50 rounded-lg px-3 py-2"
                >
                  <AlertCircle size={14} className="text-red-500 mt-0.5 shrink-0" />
                  <p className="text-[12px] text-red-700">{err}</p>
                </div>
              ))}
            </div>
          )}

          {/* 완료 메시지 */}
          {complete && errors.length === 0 && (
            <div className="flex items-center gap-2 bg-emerald-50 rounded-lg px-4 py-3 mt-4">
              <Check size={16} className="text-emerald-500" />
              <p className="text-[13px] text-emerald-700 font-medium">
                모든 법령 업데이트가 완료되었습니다.
              </p>
            </div>
          )}
        </div>

        {/* 하단 버튼 */}
        <div className="border-t border-slate-100 px-6 py-4 flex justify-end">
          <button
            onClick={onClose}
            disabled={!complete}
            className="px-6 py-2 rounded-full text-[13px] font-semibold transition-all disabled:opacity-30 disabled:cursor-not-allowed bg-[#0f1117] text-white hover:bg-slate-800"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}
