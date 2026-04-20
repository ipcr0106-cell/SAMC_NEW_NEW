"use client";

import { useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { ArrowRight, Save, Globe, Loader2 } from "lucide-react";
import StepNavigation from "@/components/layout/StepNavigation";
import CaseSummaryPanel from "@/components/layout/CaseSummaryPanel";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";

import { useForeignLabelCheck } from "@/features/feature4/hooks/useForeignLabelCheck";
import { OVERALL_LABEL, OVERALL_COLOR, CROSS_CHECK_FIELD_LABEL, SEVERITY_LABEL } from "@/features/feature4/constants";
import type { ImageIssue, LabelIssue } from "@/types/pipeline";

// ─── 서브 컴포넌트 ───────────────────────────────────────

function SeverityBadge({ severity }: { severity: "must_fix" | "review_needed" }) {
  return severity === "must_fix" ? (
    <span className="text-xs px-2 py-0.5 rounded-full border font-medium" style={{ background: "var(--ds-color-error-soft)", color: "var(--ds-color-error-text)", borderColor: "var(--ds-color-error-soft)" }}>
      {SEVERITY_LABEL.must_fix}
    </span>
  ) : (
    <span className="text-xs px-2 py-0.5 rounded-full border font-medium" style={{ background: "var(--ds-color-warning-soft)", color: "var(--ds-color-warning-text)", borderColor: "var(--ds-color-warning-soft)" }}>
      {SEVERITY_LABEL.review_needed}
    </span>
  );
}

/** reasoning 텍스트에서 (1), (2) 등 번호 항목을 줄바꿈 처리 */
function formatReasoning(text: string) {
  const formatted = text.replace(/\s*(\(\d+\))/g, "\n$1");
  return formatted.split("\n").map((line, i) => (
    <span key={i}>
      {i > 0 && <br />}
      {line}
    </span>
  ));
}

function ImageIssueCard({
  issue,
  index,
  checked,
  onToggle,
}: {
  issue: ImageIssue;
  index: number;
  checked: boolean;
  onToggle: (i: number) => void;
}) {
  return (
    <label
      className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
        checked
          ? "bg-blue-50 border-blue-200"
          : "bg-slate-50 border-slate-100 hover:border-slate-200"
      }`}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={() => onToggle(index)}
        className="mt-0.5 shrink-0 accent-blue-600"
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap mb-1">
          <SeverityBadge severity={issue.severity} />
          <span className="text-xs text-slate-400">{issue.law_ref}</span>
        </div>
        <p className="text-sm text-slate-800 mb-1">{issue.description}</p>
        {issue.location && (
          <p className="text-xs text-slate-400 mb-1">위치: {issue.location}</p>
        )}
        <p className="text-xs text-slate-600 leading-relaxed mt-1">
          {formatReasoning(issue.reasoning)}
        </p>
        {issue.recommendation && (
          <p className="text-xs text-blue-700 mt-1.5">
            <span className="font-medium">권고:</span> {issue.recommendation}
          </p>
        )}
        {issue.law_excerpt && (
          <div className="bg-white border border-slate-100 rounded-lg p-2.5 mt-1.5">
            <p className="text-xs text-slate-500 font-medium mb-0.5">참고 법령</p>
            <pre className="text-xs text-slate-700 leading-relaxed whitespace-pre-wrap font-sans">{issue.law_excerpt}</pre>
          </div>
        )}
      </div>
    </label>
  );
}

// ─── 메인 페이지 ───────────────────────────────────────

export default function F4LabelReviewPage() {
  const router = useRouter();
  const params = useParams();
  const caseId = params?.id as string;

  const {
    state,
    error,
    selectedIssueIdxs,
    selectedImageIssueIdxs,
    validationResult,
    validateStatus,
    handleAnalyze,
    handleToggleIssue,
    handleToggleImageIssue,
    handleSelectAllIssues,
    handleSelectAllImageIssues,
    handleValidate,
    handleSaveSelected,
    handleConfirm,
    handleDownloadReport,
    downloadStatus,
    fetchResult,
  } = useForeignLabelCheck(caseId);

  // 페이지 진입 시 기존 분석 결과 조회
  useEffect(() => {
    fetchResult();
  }, [fetchResult]);

  const { analysisStatus, result, isConfirmed } = state;
  const isAnalyzing = analysisStatus === "running";
  const isDone = analysisStatus === "done" && result !== null;

  return (
    <div className="max-w-[1440px] mx-auto px-6 py-6 pb-28">
      <StepNavigation currentStep="F4" completedSteps={["upload", "F1", "F3"]} />

      <div className="mt-6 grid lg:grid-cols-3 gap-6">
        {/* 좌측: 메인 콘텐츠 */}
        <div className="lg:col-span-2 space-y-6">

          {/* 오류 / 안내 메시지 */}
          {error && (
            <div
              className={`border rounded-xl px-4 py-3 text-sm ${
                error.includes("법령 DB가 업데이트 중")
                  ? "bg-amber-50 border-amber-200 text-amber-700"
                  : "bg-red-50 border-red-200 text-red-700"
              }`}
            >
              {error}
            </div>
          )}

          {/* ── 분석 실행 카드 (기존 결과가 없을 때만 표시) ── */}
          {!isDone && !isAnalyzing && (
            <Card padding="lg">
              <div className="mb-4">
                <h2 className="text-lg font-bold text-slate-900">수출국 표시사항 검토</h2>
                <p className="text-sm text-slate-500 mt-1">
                  F0(OCR), F1(원재료), F2(식품유형) 결과를 기반으로 라벨을 자동 분석합니다.
                </p>
              </div>
              <Button
                onClick={handleAnalyze}
                disabled={isAnalyzing}
                className="w-full"
                variant="primary"
                size="lg"
                icon={<Globe size={16} />}
              >
                분석 시작
              </Button>
            </Card>
          )}

          {/* 분석 진행 중 */}
          {isAnalyzing && (
            <Card padding="lg">
              <div className="flex items-center justify-center gap-3 py-8">
                <Loader2 size={24} className="animate-spin text-blue-500" />
                <p className="text-sm text-slate-600">F0/F1/F2 데이터를 기반으로 라벨을 분석하고 있습니다...</p>
              </div>
            </Card>
          )}

          {/* ── 분석 결과 ── */}
          {isDone && (
            <>
              {/* 전반 판정 */}
              <Card padding="lg">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs text-slate-400 mb-1">전반 판정</p>
                    <p className={`text-lg font-bold ${OVERALL_COLOR[result.overall]}`}>
                      {OVERALL_LABEL[result.overall]}
                    </p>
                  </div>
                  <div className="flex gap-4 text-center">
                    <div>
                      <div className="text-xl font-bold text-red-600">
                        {result.issues.filter((i) => i.severity === "must_fix").length +
                          (result.image_issues ?? []).filter((i) => i.severity === "must_fix").length}
                      </div>
                      <div className="text-xs text-slate-400">수정 필수</div>
                    </div>
                    <div>
                      <div className="text-xl font-bold text-amber-600">
                        {result.issues.filter((i) => i.severity === "review_needed").length +
                          (result.image_issues ?? []).filter((i) => i.severity === "review_needed").length}
                      </div>
                      <div className="text-xs text-slate-400">검토 필요</div>
                    </div>
                  </div>
                </div>

                {/* 재분석 버튼 */}
                {!isConfirmed && (
                  <button
                    onClick={handleAnalyze}
                    className="mt-3 text-xs text-slate-400 hover:text-slate-600 transition-colors"
                  >
                    다시 분석하기
                  </button>
                )}
              </Card>

              {/* 텍스트 위반 항목 */}
              {result.issues.length > 0 && (
                <Card padding="lg">
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <h3 className="text-sm font-semibold text-slate-800">텍스트 위반 항목</h3>
                      <p className="text-xs text-slate-400 mt-0.5">체크된 항목만 법령 검증 및 최종 저장됩니다.</p>
                    </div>
                    <button onClick={handleSelectAllIssues} className="text-xs text-blue-600 hover:underline">
                      전체 선택
                    </button>
                  </div>
                  <div className="space-y-3">
                    {result.issues.map((issue: LabelIssue, i) => (
                      <label
                        key={i}
                        className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                          selectedIssueIdxs.has(i)
                            ? "bg-blue-50 border-blue-200"
                            : "bg-slate-50 border-slate-100 hover:border-slate-200"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={selectedIssueIdxs.has(i)}
                          onChange={() => handleToggleIssue(i)}
                          className="mt-0.5 shrink-0 accent-blue-600"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap mb-1">
                            <SeverityBadge severity={issue.severity} />
                            <span className="text-xs text-slate-400">{issue.law_ref}</span>
                          </div>
                          <p className="text-sm font-medium text-slate-800 mb-1">
                            &ldquo;{issue.text}&rdquo;
                          </p>
                          {issue.location && (
                            <p className="text-xs text-slate-400 mb-0.5">위치: {issue.location}</p>
                          )}
                          <p className="text-xs text-slate-600 leading-relaxed">{issue.reason}</p>
                          {issue.law_excerpt && (
                            <div className="bg-white border border-slate-100 rounded-lg p-2.5 mt-1.5">
                              <p className="text-xs text-slate-500 font-medium mb-0.5">참고 법령</p>
                              <pre className="text-xs text-slate-700 leading-relaxed whitespace-pre-wrap font-sans">{issue.law_excerpt}</pre>
                            </div>
                          )}
                        </div>
                      </label>
                    ))}
                  </div>
                </Card>
              )}

              {/* 이미지 위반 항목 */}
              {(() => {
                const allImageIssues = result.image_issues ?? [];
                const confirmed = allImageIssues.filter((it) => it.review_level !== "suggested");
                const suggested = allImageIssues.filter((it) => it.review_level === "suggested");
                if (allImageIssues.length === 0) return null;
                return (
                  <>
                    {confirmed.length > 0 && (
                      <Card padding="lg">
                        <div className="flex items-center justify-between mb-3">
                          <div>
                            <h3 className="text-sm font-semibold text-slate-800">이미지 위반 항목</h3>
                            <p className="text-xs text-slate-400 mt-0.5">라벨 이미지의 그림/도안 요소 분석 결과입니다.</p>
                          </div>
                          <button onClick={handleSelectAllImageIssues} className="text-xs text-blue-600 hover:underline">
                            전체 선택
                          </button>
                        </div>
                        <div className="space-y-3">
                          {confirmed.map((issue) => {
                            const i = allImageIssues.indexOf(issue);
                            return (
                              <ImageIssueCard
                                key={i} issue={issue} index={i}
                                checked={selectedImageIssueIdxs.has(i)}
                                onToggle={handleToggleImageIssue}
                              />
                            );
                          })}
                        </div>
                      </Card>
                    )}

                    {suggested.length > 0 && (
                      <Card padding="lg">
                        <div className="mb-3">
                          <h3 className="text-sm font-semibold text-slate-800">추가 검토 권고 항목</h3>
                          <p className="text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2 mt-2">
                            법령 개정으로 새롭게 추가된 유형으로 AI 판단 신뢰도가 낮습니다.
                            가능성은 낮지만 해당 여부를 직접 확인해보세요.
                          </p>
                        </div>
                        <div className="space-y-3">
                          {suggested.map((issue) => {
                            const i = allImageIssues.indexOf(issue);
                            return (
                              <ImageIssueCard
                                key={i} issue={issue} index={i}
                                checked={selectedImageIssueIdxs.has(i)}
                                onToggle={handleToggleImageIssue}
                              />
                            );
                          })}
                        </div>
                      </Card>
                    )}
                  </>
                );
              })()}

              {/* 교차검증 결과 */}
              {result.cross_check?.length > 0 && (
                <Card padding="lg">
                  <h3 className="text-sm font-semibold text-slate-800 mb-3">라벨 ↔ 서류 교차검증</h3>
                  <div className="space-y-2">
                    {result.cross_check.map((item, i) => (
                      <div
                        key={i}
                        className={`flex items-start gap-3 p-3 rounded-lg border text-xs ${
                          item.match
                            ? "bg-emerald-50 border-emerald-100"
                            : "bg-red-50 border-red-100"
                        }`}
                      >
                        <span className={`mt-0.5 font-bold ${item.match ? "text-emerald-600" : "text-red-600"}`}>
                          {item.match ? "\u2713" : "\u2717"}
                        </span>
                        <div>
                          <span className="font-medium text-slate-700">
                            {CROSS_CHECK_FIELD_LABEL[item.field] ?? item.field}
                          </span>
                          {!item.match && (
                            <>
                              <div className="mt-0.5 text-slate-600">
                                라벨: <span className="font-mono">{item.label_value || "\u2014"}</span>
                              </div>
                              <div className="text-slate-600">
                                서류: <span className="font-mono">{item.doc_value || "\u2014"}</span>
                              </div>
                              {item.note && <div className="text-red-700 mt-0.5">{item.note}</div>}
                            </>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {/* ── 법령 정합성 검증 ── */}
              <Card padding="lg">
                <div className="mb-3">
                  <h3 className="text-sm font-semibold text-slate-800">법령 정합성 검토</h3>
                  <p className="text-xs text-slate-400 mt-0.5">선택한 항목 간 충돌/의존 관계를 검토합니다.</p>
                </div>
                <button
                  onClick={handleValidate}
                  disabled={
                    validateStatus === "running" ||
                    (selectedIssueIdxs.size === 0 && selectedImageIssueIdxs.size === 0)
                  }
                  className="w-full border border-slate-300 text-slate-700 text-sm font-medium py-2.5 rounded-lg hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
                >
                  {validateStatus === "running" ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      검토 중...
                    </>
                  ) : (
                    `선택 항목 법령 검증 (${selectedIssueIdxs.size + selectedImageIssueIdxs.size}건)`
                  )}
                </button>

                {validationResult && (
                  <div className="mt-4 space-y-3">
                    <div className={`text-sm px-4 py-3 rounded-lg border ${
                      validationResult.is_valid
                        ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                        : "bg-amber-50 border-amber-200 text-amber-800"
                    }`}>
                      {validationResult.summary}
                    </div>

                    {validationResult.conflicts.map((c, i) => (
                      <div key={i} className="bg-red-50 border border-red-200 rounded-lg p-4">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="text-xs font-bold text-red-700 uppercase">충돌</span>
                          <span className="text-xs text-red-600">{c.law_refs.join(" \u2194 ")}</span>
                        </div>
                        <p className="text-sm font-medium text-red-800 mb-2">{c.description}</p>
                        <div className="bg-white rounded p-2.5 border border-red-100">
                          <p className="text-xs text-slate-500 font-medium mb-1">판단 근거</p>
                          <p className="text-xs text-slate-700 leading-relaxed">{c.reasoning}</p>
                        </div>
                        <p className="text-xs text-red-700 mt-2">
                          <span className="font-medium">권고:</span> {c.recommendation}
                        </p>
                      </div>
                    ))}

                    {validationResult.dependencies.map((d, i) => (
                      <div key={i} className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="text-xs font-bold text-blue-700 uppercase">함께 적용 필요</span>
                          <span className="text-xs text-blue-600">
                            {d.selected_law_ref} → {d.required_law_ref}
                          </span>
                        </div>
                        <p className="text-sm font-medium text-blue-800 mb-2">{d.description}</p>
                        <div className="bg-white rounded p-2.5 border border-blue-100">
                          <p className="text-xs text-slate-500 font-medium mb-1">판단 근거</p>
                          <p className="text-xs text-slate-700 leading-relaxed">{d.reasoning}</p>
                        </div>
                      </div>
                    ))}

                    {validationResult.applied_principles && (
                      <div className="bg-slate-50 border border-slate-200 rounded-lg px-4 py-3">
                        <p className="text-xs text-slate-500 font-medium mb-1">적용 법령 해석 원칙</p>
                        <p className="text-xs text-slate-600 leading-relaxed">
                          {validationResult.applied_principles}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </Card>

              {/* ── 최종 저장 & 확인 ── */}
              <Card padding="lg">
                <div className="mb-3">
                  <h3 className="text-sm font-semibold text-slate-800">최종 저장</h3>
                  <p className="text-xs text-slate-400 mt-0.5">선택한 항목만 최종 결과로 저장됩니다.</p>
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={() => handleSaveSelected()}
                    disabled={isConfirmed || (selectedIssueIdxs.size === 0 && selectedImageIssueIdxs.size === 0 && result.overall === "pass")}
                    className="flex-1 border border-slate-300 text-slate-700 text-sm font-medium py-2.5 rounded-lg hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    선택 항목 저장
                  </button>
                  <button
                    onClick={handleConfirm}
                    disabled={isConfirmed}
                    className="flex-1 bg-slate-800 text-white text-sm font-medium py-2.5 rounded-lg hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    {isConfirmed ? "확인 완료 \u2713" : "확인 완료"}
                  </button>
                </div>
              </Card>

              {/* ── 레포트 PDF 다운로드 ── */}
              <Card padding="lg">
                <div className="mb-3">
                  <h3 className="text-sm font-semibold text-slate-800">레포트 다운로드</h3>
                  <p className="text-xs text-slate-400 mt-0.5">검토 결과를 PDF 보고서로 내려받습니다.</p>
                </div>
                <button
                  onClick={handleDownloadReport}
                  disabled={downloadStatus === "downloading"}
                  className="w-full border border-slate-300 text-slate-700 text-sm font-medium py-2.5 rounded-lg hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
                >
                  {downloadStatus === "downloading" ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      다운로드 중...
                    </>
                  ) : (
                    "PDF 레포트 다운로드"
                  )}
                </button>
              </Card>
            </>
          )}
        </div>

        {/* 우측: 케이스 요약 */}
        <div className="space-y-4">
          <CaseSummaryPanel caseId={caseId} />
        </div>
      </div>

      {/* 하단 액션바 */}
      <div className="fixed bottom-0 left-0 right-0 z-50">
        <div className="max-w-[1440px] mx-auto px-6">
          <div className="ds-actionbar-shell px-8 py-4 flex items-center justify-between">
            <Button variant="secondary" size="md" onClick={() => router.push(`/cases/${caseId}/f3`)}>
              이전: 필요서류
            </Button>
            <div className="flex items-center gap-3">
              <Button
                variant="secondary" size="md"
                icon={<Save size={16} />}
                onClick={() => handleSaveSelected()}
                disabled={isConfirmed}
              >
                임시 저장
              </Button>
              <Button
                variant="primary" size="lg"
                icon={<ArrowRight size={18} />}
                onClick={() => router.push(`/cases/${caseId}/f5`)}
              >
                F5 한글시안으로 이동
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
