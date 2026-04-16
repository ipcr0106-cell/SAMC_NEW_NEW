"use client";

import { apiClient } from "@/services/apiClient";
import { useState, useRef } from "react";
import { useParams } from "next/navigation";

// ── 타입 ─────────────────────────────────────────────────────────────────────

interface Phase1Item {
  field: string;
  law_ref: string;
  law_requirement: string;
  document_value: string | null;
  status: "pass" | "fail" | "unclear";
  note: string;
}

interface Phase2Validation {
  field: string;
  phase1_status: string;
  ai_status: "pass" | "fail" | "unclear";
  cross_result: "agree" | "disagree" | "additional_issue";
  ai_note: string;
}

interface AdditionalIssue {
  field: string;
  issue: string;
  severity: "error" | "warning" | "info";
}

interface Draft {
  product_name?: string;
  food_type?: string;
  ingredients?: string;
  net_weight?: string;
  expiry?: string;
  storage?: string;
  manufacturer?: string;
  importer?: string;
  allergy?: string;
  gmo?: string;
  country_of_origin?: string;
}

interface Result {
  phase1: { items: Phase1Item[] };
  phase2: {
    validation: Phase2Validation[];
    additional_issues: AdditionalIssue[];
    draft: Draft;
  };
}

type Step = "idle" | "uploading" | "generating_p1" | "generating_p2" | "done" | "error";

// ── 상수 ─────────────────────────────────────────────────────────────────────

const STATUS_ICON = {
  pass:    { color: "text-emerald-600 bg-emerald-50 border-emerald-200", label: "적합" },
  fail:    { color: "text-red-600 bg-red-50 border-red-200",             label: "부적합" },
  unclear: { color: "text-amber-600 bg-amber-50 border-amber-200",       label: "확인필요" },
};

const CROSS_BADGE = {
  agree:            { color: "bg-emerald-100 text-emerald-700", label: "일치" },
  disagree:         { color: "bg-red-100 text-red-700",         label: "불일치" },
  additional_issue: { color: "bg-amber-100 text-amber-700",     label: "추가이슈" },
};

const SEVERITY_STYLE = {
  error:   "border-red-200 bg-red-50 text-red-700",
  warning: "border-amber-200 bg-amber-50 text-amber-700",
  info:    "border-blue-200 bg-blue-50 text-blue-700",
};

const DRAFT_LABELS: Record<string, string> = {
  product_name:     "제품명",
  food_type:        "식품유형",
  ingredients:      "원재료명 및 함량",
  net_weight:       "내용량",
  expiry:           "소비기한",
  storage:          "보관방법",
  manufacturer:     "제조사",
  importer:         "수입자",
  allergy:          "알레르기",
  gmo:              "GMO",
  country_of_origin:"원산지",
};

// ── 컴포넌트 ─────────────────────────────────────────────────────────────────

export default function LabelPage() {
  const params = useParams();
  const caseId = params.id as string;

  const [step, setStep]           = useState<Step>("idle");
  const [file, setFile]           = useState<File | null>(null);
  const [foodType, setFoodType]   = useState("");
  const [result, setResult]       = useState<Result | null>(null);
  const [errorMsg, setErrorMsg]   = useState("");
  const [confirmedBy, setConfirmedBy] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [expandedField, setExpandedField] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 통계 계산
  const p1Items   = result?.phase1.items ?? [];
  const p2Items   = result?.phase2.validation ?? [];
  const issues    = result?.phase2.additional_issues ?? [];
  const failCount = p1Items.filter((i) => i.status === "fail").length;
  const unclearCount = p1Items.filter((i) => i.status === "unclear").length;
  const disagreeCount = p2Items.filter((v) => v.cross_result === "disagree").length;
  const errorCount = issues.filter((i) => i.severity === "error").length;

  // ── 파일 업로드 + 시안 생성 ───────────────────────────────────────────────
  async function handleRun() {
    if (!file) return;
    setErrorMsg("");

    try {
      // 1. PDF 업로드
      setStep("uploading");
      const form = new FormData();
      form.append("file", file);
      form.append("doc_type", "ingredients");
      await apiClient.post(`/cases/${caseId}/upload`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      // 2. Phase 1 시작
      setStep("generating_p1");

      // SSE 스트리밍
      const url = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/cases/${caseId}/pipeline/feature/5/run`;
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ food_type: foodType || null, stream: true }),
      });

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();

      let phase1Data: Result["phase1"] | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value);
        const lines = text.split("\n").filter((l) => l.startsWith("data: "));

        for (const line of lines) {
          try {
            const data = JSON.parse(line.slice(6));

            if (data.step === "phase1_done") {
              phase1Data = data.phase1;
              setStep("generating_p2");
            }

            if (data.step === "done" && phase1Data) {
              setResult(data.result);
              setStep("done");
            }

            if (data.error) {
              setErrorMsg(data.error);
              setStep("error");
            }
          } catch { /* 불완전 JSON 청크 무시 */ }
        }
      }
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : "오류가 발생했습니다.");
      setStep("error");
    }
  }

  // ── 확정 저장 ─────────────────────────────────────────────────────────────
  async function handleConfirm() {
    if (!confirmedBy.trim() || confirmed) return;
    try {
      await apiClient.patch(`/cases/${caseId}/pipeline/feature/5`, {
        confirmed_by: confirmedBy.trim(),
      });
      setConfirmed(true);
    } catch {
      setErrorMsg("확정 저장에 실패했습니다.");
    }
  }

  // ── 렌더: Phase1 항목 행 ──────────────────────────────────────────────────
  function renderP1Row(item: Phase1Item) {
    const st = STATUS_ICON[item.status];
    const v2 = p2Items.find((v) => v.field === item.field);
    const expanded = expandedField === item.field;

    return (
      <div key={item.field} className="border border-slate-200 rounded-xl overflow-hidden">
        {/* 헤더 행 */}
        <button
          onClick={() => setExpandedField(expanded ? null : item.field)}
          className="w-full flex items-center gap-3 px-4 py-3 bg-white hover:bg-slate-50 transition-colors text-left"
        >
          {/* 필드명 */}
          <span className="text-sm font-semibold text-slate-700 w-32 shrink-0">{item.field}</span>

          {/* 1차 판정 */}
          <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${st.color}`}>
            1차 {st.label}
          </span>

          {/* 교차 결과 */}
          {v2 && (
            <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${CROSS_BADGE[v2.cross_result].color}`}>
              AI {CROSS_BADGE[v2.cross_result].label}
            </span>
          )}

          {/* 불일치 강조 */}
          {v2?.cross_result === "disagree" && (
            <span className="text-[11px] font-bold text-red-600 ml-1">⚠ 실무자 확인 필요</span>
          )}

          <svg className={`w-4 h-4 text-slate-400 ml-auto shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`}
            fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7"/>
          </svg>
        </button>

        {/* 상세 펼치기 */}
        {expanded && (
          <div className="border-t border-slate-100 bg-slate-50 px-4 py-3 space-y-3 text-xs">
            {/* 서류 값 */}
            <div>
              <span className="font-semibold text-slate-500">서류 확인값: </span>
              <span className="text-slate-700">{item.document_value ?? "확인 불가"}</span>
            </div>

            {/* 법령 근거 */}
            <div className="bg-white border border-slate-200 rounded-lg px-3 py-2">
              <div className="font-semibold text-slate-500 mb-1">
                법령 근거
              </div>
              <p className="text-slate-600 font-medium">{item.law_ref}</p>
              <p className="text-slate-500 mt-1">{item.law_requirement}</p>
            </div>

            {/* 1차 판정 사유 */}
            <div className={`rounded-lg px-3 py-2 border ${st.color}`}>
              <span className="font-semibold">1차 검토 의견: </span>{item.note}
            </div>

            {/* AI 교차검증 의견 */}
            {v2 && (
              <div className={`rounded-lg px-3 py-2 border ${CROSS_BADGE[v2.cross_result].color}`}>
                <span className="font-semibold">AI 교차검증: </span>{v2.ai_note}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  // ── 렌더 ─────────────────────────────────────────────────────────────────
  return (
    <>
      <div className="max-w-3xl">
        <p className="text-xs text-slate-400 mb-5">기능 5 · 한글표시사항 2단계 교차검증</p>

        {/* ── IDLE: 업로드 폼 ─────────────────────────────────────── */}
        {(step === "idle" || step === "error") && (
          <div className="bg-white border border-slate-200 rounded-xl p-6 mb-4">
            <h2 className="text-sm font-semibold text-slate-700 mb-4">
              성분표 PDF 업로드 후 2단계 교차검증 실행
            </h2>

            {/* 파일 선택 */}
            <div
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors mb-4 ${
                file ? "border-emerald-300 bg-emerald-50" : "border-slate-200 hover:border-slate-300"
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              {file ? (
                <>
                  <svg className="w-8 h-8 text-emerald-500 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                  </svg>
                  <p className="text-sm font-medium text-emerald-700">{file.name}</p>
                  <p className="text-xs text-emerald-500 mt-1">클릭하여 파일 변경</p>
                </>
              ) : (
                <>
                  <svg className="w-8 h-8 text-slate-300 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/>
                  </svg>
                  <p className="text-sm text-slate-500">PDF 파일을 클릭하여 선택</p>
                  <p className="text-xs text-slate-400 mt-1">성분표, 원재료 서류 등</p>
                </>
              )}
            </div>

            {/* 식품유형 입력 */}
            <div className="mb-4">
              <label className="block text-xs font-semibold text-slate-500 mb-1.5">
                식품유형 <span className="font-normal text-slate-400">(선택 — 비워두면 AI가 서류에서 판단)</span>
              </label>
              <input
                type="text"
                value={foodType}
                onChange={(e) => setFoodType(e.target.value)}
                placeholder="예: 견과류가공품, 과자류"
                className="w-full text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-400 placeholder:text-slate-300"
              />
            </div>

            {/* 오류 */}
            {errorMsg && (
              <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 mb-4 text-sm text-red-700">
                {errorMsg}
              </div>
            )}

            {/* 실행 버튼 */}
            <button
              onClick={handleRun}
              disabled={!file}
              className="w-full py-3 bg-emerald-500 text-white text-sm font-semibold rounded-xl hover:bg-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              2단계 교차검증 시작
            </button>

            {/* 흐름 설명 */}
            <div className="mt-4 grid grid-cols-3 gap-2 text-center">
              {[
                { n: "1", title: "법령 대조", desc: "Pinecone RAG로 관련 법령 조항을 검색해 항목별 적합 여부 판정" },
                { n: "2", title: "AI 교차검증", desc: "Claude가 1차 결과를 재검토해 불일치·누락 항목 발견" },
                { n: "3", title: "시안 생성", desc: "교차검증 결과를 반영한 최종 한글표시사항 시안 출력" },
              ].map((s) => (
                <div key={s.n} className="bg-slate-50 border border-slate-100 rounded-lg p-3">
                  <div className="w-6 h-6 rounded-full bg-emerald-500 text-white text-xs font-bold flex items-center justify-center mx-auto mb-1.5">{s.n}</div>
                  <p className="text-[11px] font-semibold text-slate-700 mb-1">{s.title}</p>
                  <p className="text-[10px] text-slate-400 leading-relaxed">{s.desc}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── 진행 중 ─────────────────────────────────────────────── */}
        {(step === "uploading" || step === "generating_p1" || step === "generating_p2") && (
          <div className="bg-white border border-slate-200 rounded-xl p-8 text-center">
            <div className="flex justify-center mb-4">
              <svg className="w-8 h-8 text-emerald-500 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h5M20 20v-5h-5M4 9a9 9 0 0115.83-3.5M20 15a9 9 0 01-15.83 3.5"/>
              </svg>
            </div>
            <div className="space-y-2">
              <StepRow active={step === "uploading"}      done={step !== "uploading"} label="PDF 업로드 및 파싱" />
              <StepRow active={step === "generating_p1"} done={step === "generating_p2"} label="1단계: 법령/고시 기반 항목 대조 중..." />
              <StepRow active={step === "generating_p2"} done={false} label="2단계: AI 교차검증 및 시안 생성 중..." />
            </div>
            <p className="text-xs text-slate-400 mt-4">PDF 분량에 따라 30초~2분 소요될 수 있습니다.</p>
          </div>
        )}

        {/* ── 결과 ────────────────────────────────────────────────── */}
        {step === "done" && result && (
          <>
            {/* 종합 요약 */}
            <div className={`rounded-xl p-4 mb-5 border ${
              failCount + disagreeCount + errorCount > 0
                ? "bg-amber-50 border-amber-200"
                : "bg-emerald-50 border-emerald-200"
            }`}>
              <p className="text-sm font-semibold text-slate-800 mb-2">교차검증 종합 결과</p>
              <div className="flex flex-wrap gap-3 text-xs">
                <span className="bg-white border border-slate-200 rounded-lg px-3 py-1.5">
                  검토항목 <strong>{p1Items.length}개</strong>
                </span>
                <span className={`rounded-lg px-3 py-1.5 border ${failCount > 0 ? "bg-red-50 border-red-200 text-red-700" : "bg-white border-slate-200"}`}>
                  법령 부적합 <strong>{failCount}건</strong>
                </span>
                <span className={`rounded-lg px-3 py-1.5 border ${unclearCount > 0 ? "bg-amber-50 border-amber-200 text-amber-700" : "bg-white border-slate-200"}`}>
                  확인필요 <strong>{unclearCount}건</strong>
                </span>
                <span className={`rounded-lg px-3 py-1.5 border ${disagreeCount > 0 ? "bg-red-50 border-red-200 text-red-700" : "bg-white border-slate-200"}`}>
                  1·2차 불일치 <strong>{disagreeCount}건</strong>
                </span>
                <span className={`rounded-lg px-3 py-1.5 border ${errorCount > 0 ? "bg-red-50 border-red-200 text-red-700" : "bg-white border-slate-200"}`}>
                  추가 오류 <strong>{errorCount}건</strong>
                </span>
              </div>
            </div>

            {/* 항목별 교차검증 결과 */}
            <div className="mb-4">
              <h2 className="text-sm font-semibold text-slate-700 mb-3">항목별 교차검증 결과</h2>
              <div className="space-y-2">
                {p1Items.map((item) => renderP1Row(item))}
              </div>
            </div>

            {/* 추가 발견 이슈 */}
            {issues.length > 0 && (
              <div className="bg-white border border-slate-200 rounded-xl p-4 mb-4">
                <h2 className="text-sm font-semibold text-slate-700 mb-3">AI 추가 발견 이슈</h2>
                <div className="space-y-2">
                  {issues.map((issue, i) => (
                    <div key={i} className={`text-xs rounded-lg border px-3 py-2 ${SEVERITY_STYLE[issue.severity]}`}>
                      <span className="font-semibold">[{issue.field}] </span>{issue.issue}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 최종 시안 */}
            {result.phase2.draft && (
              <div className="bg-white border border-slate-200 rounded-xl p-5 mb-4">
                <h2 className="text-sm font-semibold text-slate-700 mb-4">최종 한글표시사항 시안</h2>
                <div className="divide-y divide-slate-100">
                  {Object.entries(result.phase2.draft).map(([key, val]) => (
                    <div key={key} className="py-3 flex gap-4">
                      <span className="text-xs font-semibold text-slate-500 w-28 shrink-0 mt-0.5">
                        {DRAFT_LABELS[key] ?? key}
                      </span>
                      <p className="text-sm text-slate-900 flex-1 leading-relaxed">{val || "—"}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 확정 */}
            <div className="bg-white border border-slate-200 rounded-xl p-5 mb-4">
              <h2 className="text-sm font-semibold text-slate-700 mb-1">실무자 최종 확정</h2>
              <p className="text-xs text-slate-400 mb-4">
                교차검증 결과를 검토한 후 확정자 이름을 입력하고 확정하세요.
                {(failCount + disagreeCount) > 0 && (
                  <span className="text-amber-600 font-medium"> ⚠ 부적합·불일치 항목을 먼저 확인하세요.</span>
                )}
              </p>
              {confirmed ? (
                <div className="flex items-center gap-2 text-sm text-emerald-700 font-medium">
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd"/>
                  </svg>
                  {confirmedBy}님이 확정했습니다.
                </div>
              ) : (
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={confirmedBy}
                    onChange={(e) => setConfirmedBy(e.target.value)}
                    placeholder="확정자 이름"
                    className="flex-1 text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-400 placeholder:text-slate-300"
                  />
                  <button
                    onClick={handleConfirm}
                    disabled={!confirmedBy.trim()}
                    className="px-4 py-2 bg-emerald-500 text-white text-sm font-semibold rounded-lg hover:bg-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    확정
                  </button>
                </div>
              )}
            </div>

            {/* 다시 실행 */}
            <button
              onClick={() => { setStep("idle"); setResult(null); setFile(null); setConfirmed(false); }}
              className="text-sm text-slate-400 hover:text-slate-600 transition-colors"
            >
              ← 다시 업로드
            </button>
          </>
        )}
      </div>
    </>
  );
}

// ── 진행 단계 표시 ────────────────────────────────────────────────────────────

function StepRow({ active, done, label }: { active: boolean; done: boolean; label: string }) {
  return (
    <div className="flex items-center gap-3 text-sm">
      {done ? (
        <svg className="w-5 h-5 text-emerald-500 shrink-0" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd"/>
        </svg>
      ) : active ? (
        <svg className="w-5 h-5 text-emerald-500 animate-spin shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h5M20 20v-5h-5M4 9a9 9 0 0115.83-3.5M20 15a9 9 0 01-15.83 3.5"/>
        </svg>
      ) : (
        <div className="w-5 h-5 rounded-full border-2 border-slate-200 shrink-0"/>
      )}
      <span className={active ? "text-slate-800 font-medium" : done ? "text-slate-400 line-through" : "text-slate-300"}>
        {label}
      </span>
    </div>
  );
}
