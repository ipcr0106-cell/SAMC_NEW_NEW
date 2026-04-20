"use client";

import { useState } from "react";
import { Save, AlertCircle, CheckCircle2, Plus, X, ChevronDown, ChevronRight } from "lucide-react";
import { addManualRule, type ManualRuleInput, type ManualRuleResponse } from "./api";

function genIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function RuleAddForm() {
  // 기본 정보
  const [docName, setDocName] = useState("");
  const [docDescription, setDocDescription] = useState("");
  const [submissionType, setSubmissionType] = useState<"submit" | "keep">("submit");
  const [submissionTiming, setSubmissionTiming] = useState<"every" | "first">("every");
  const [lawSource, setLawSource] = useState("");
  const [isMandatory, setIsMandatory] = useState(true);

  // 적용 대상
  const [targetCountry, setTargetCountry] = useState("");
  const [foodType, setFoodType] = useState("");
  const [conditionVal, setConditionVal] = useState("");
  const [productKeywords, setProductKeywords] = useState<string[]>([]);
  const [keywordInput, setKeywordInput] = useState("");

  // 선택 사항
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [effectiveUntil, setEffectiveUntil] = useState("");
  const [notes, setNotes] = useState("");

  // UI 상태
  const [showOptional, setShowOptional] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState<ManualRuleResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const handleAddKeyword = () => {
    const kw = keywordInput.trim();
    if (!kw || productKeywords.includes(kw)) return;
    setProductKeywords([...productKeywords, kw]);
    setKeywordInput("");
  };

  const handleRemoveKeyword = (kw: string) => {
    setProductKeywords(productKeywords.filter((k) => k !== kw));
  };

  const validate = (): string | null => {
    if (!docName.trim()) return "서류명을 입력해주세요.";
    if (!docDescription.trim()) return "서류 내용을 입력해주세요.";
    const hasTarget =
      !!targetCountry.trim() ||
      !!foodType.trim() ||
      !!conditionVal.trim() ||
      productKeywords.length > 0;
    if (!hasTarget) {
      return "적용 대상 (국가·식품유형·조건·원재료 키워드) 중 최소 1개는 입력해야 합니다.";
    }
    return null;
  };

  const handleReset = () => {
    setDocName("");
    setDocDescription("");
    setSubmissionType("submit");
    setSubmissionTiming("every");
    setLawSource("");
    setIsMandatory(true);
    setTargetCountry("");
    setFoodType("");
    setConditionVal("");
    setProductKeywords([]);
    setKeywordInput("");
    setEffectiveFrom("");
    setEffectiveUntil("");
    setNotes("");
    setSuccess(null);
    setError(null);
    setValidationError(null);
  };

  const handleSubmit = async () => {
    setError(null);
    setValidationError(null);
    const err = validate();
    if (err) {
      setValidationError(err);
      return;
    }

    setSubmitting(true);
    try {
      const payload: ManualRuleInput = {
        doc_name: docName.trim(),
        doc_description: docDescription.trim(),
        is_mandatory: isMandatory,
        submission_type: submissionType,
        submission_timing: submissionTiming,
        law_source: lawSource.trim() || undefined,
        target_country: targetCountry.trim() || null,
        food_type: foodType.trim() || null,
        condition: conditionVal.trim() || null,
        product_keywords: productKeywords.length > 0 ? productKeywords : null,
        effective_from: effectiveFrom || null,
        effective_until: effectiveUntil || null,
        notes: notes.trim() || null,
      };
      const res = await addManualRule(payload, genIdempotencyKey());
      setSuccess(res);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  // 성공 화면
  if (success) {
    return (
      <div className="max-w-[800px] mx-auto">
        <div className="border border-emerald-200 rounded-xl p-6 bg-emerald-50">
          <div className="flex items-center gap-3 mb-3">
            <CheckCircle2 className="w-7 h-7 text-emerald-600" />
            <div>
              <div className="text-[17px] font-bold text-emerald-900">규칙 추가 완료</div>
              <div className="text-[13px] text-emerald-700">
                버전 v{success.version} 으로 저장됐습니다. 필요 시 이력에서 롤백 가능.
              </div>
            </div>
          </div>
          <div className="bg-white rounded-lg p-3 text-[13px] text-slate-700 mb-4 font-mono">
            <div>테이블: {success.table_name}</div>
            <div>규칙 ID: {success.row_id}</div>
          </div>
          <div className="flex gap-3">
            <button
              onClick={handleReset}
              className="flex-1 h-11 rounded-lg bg-emerald-600 text-white font-semibold hover:bg-emerald-700"
            >
              다른 규칙 추가하기
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-[800px] mx-auto">
      <div className="mb-6">
        <h2 className="text-[22px] font-extrabold text-slate-900">
          수동 서류 규칙 추가
        </h2>
        <p className="text-[14px] text-slate-500 mt-1">
          엑셀로 올리기 어려운 긴급 공지·특별 규칙을 직접 입력합니다.
          입력한 규칙은 &apos;수입필요서류 안내&apos; 에 즉시 반영되고, 이력에서 언제든 롤백할 수 있어요.
        </p>
      </div>

      <div className="border border-slate-200 rounded-xl p-5 bg-white space-y-5">
        {/* 기본 정보 */}
        <section>
          <h3 className="text-[14px] font-bold text-slate-800 mb-3">📝 기본 정보</h3>
          <div className="space-y-3">
            <div>
              <label className="text-[13px] font-semibold text-slate-700 block mb-1">
                서류명 <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                value={docName}
                onChange={(e) => setDocName(e.target.value)}
                placeholder="예: 중국산 특정 제품 긴급 검사성적서"
                className="w-full px-3 py-2 rounded-lg border border-slate-300 text-[14px] focus:outline-none focus:ring-2 focus:ring-slate-400"
              />
            </div>
            <div>
              <label className="text-[13px] font-semibold text-slate-700 block mb-1">
                서류 내용 <span className="text-rose-500">*</span>
              </label>
              <textarea
                value={docDescription}
                onChange={(e) => setDocDescription(e.target.value)}
                placeholder="서류의 목적, 요구 내용, 특이사항 등 상세 설명"
                rows={3}
                className="w-full px-3 py-2 rounded-lg border border-slate-300 text-[14px] focus:outline-none focus:ring-2 focus:ring-slate-400 resize-none"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[13px] font-semibold text-slate-700 block mb-1">
                  제출/보관
                </label>
                <select
                  value={submissionType}
                  onChange={(e) => setSubmissionType(e.target.value as "submit" | "keep")}
                  className="w-full h-10 px-2 rounded-lg border border-slate-300 text-[14px] bg-white"
                >
                  <option value="submit">제출 (submit)</option>
                  <option value="keep">보관 (keep)</option>
                </select>
              </div>
              <div>
                <label className="text-[13px] font-semibold text-slate-700 block mb-1">
                  제출 시점
                </label>
                <select
                  value={submissionTiming}
                  onChange={(e) => setSubmissionTiming(e.target.value as "every" | "first")}
                  className="w-full h-10 px-2 rounded-lg border border-slate-300 text-[14px] bg-white"
                >
                  <option value="every">매 수입 시 (every)</option>
                  <option value="first">최초 수입 시만 (first)</option>
                </select>
              </div>
            </div>
            <div>
              <label className="text-[13px] font-semibold text-slate-700 block mb-1">
                근거 법령
              </label>
              <input
                type="text"
                value={lawSource}
                onChange={(e) => setLawSource(e.target.value)}
                placeholder="예: 식약처 긴급공지 2026-08호"
                className="w-full px-3 py-2 rounded-lg border border-slate-300 text-[14px] focus:outline-none focus:ring-2 focus:ring-slate-400"
              />
            </div>
            <label className="flex items-center gap-2 text-[13px] text-slate-700">
              <input
                type="checkbox"
                checked={isMandatory}
                onChange={(e) => setIsMandatory(e.target.checked)}
                className="w-4 h-4 accent-slate-900"
              />
              필수 서류 (체크 해제 시 권장 서류로 분류)
            </label>
          </div>
        </section>

        {/* 적용 대상 */}
        <section>
          <h3 className="text-[14px] font-bold text-slate-800 mb-1">
            🎯 적용 대상 <span className="text-rose-500">*</span>
          </h3>
          <p className="text-[12px] text-slate-500 mb-3">
            아래 4개 중 <b>최소 1개</b> 를 입력해야 규칙이 매칭에 쓰입니다.
          </p>
          <div className="space-y-3">
            <div>
              <label className="text-[13px] font-semibold text-slate-700 block mb-1">
                대상 국가
              </label>
              <input
                type="text"
                value={targetCountry}
                onChange={(e) => setTargetCountry(e.target.value)}
                placeholder="예: 중국 / BSE관련36개국 / ASF발생73개국 / EU"
                className="w-full px-3 py-2 rounded-lg border border-slate-300 text-[14px] focus:outline-none focus:ring-2 focus:ring-slate-400"
              />
              <div className="text-[11px] text-slate-400 mt-0.5">
                특수 태그: BSE관련36개국, ASF발생73개국, 모든국가(BSE36개국제외), EU
              </div>
            </div>
            <div>
              <label className="text-[13px] font-semibold text-slate-700 block mb-1">
                대상 식품유형
              </label>
              <input
                type="text"
                value={foodType}
                onChange={(e) => setFoodType(e.target.value)}
                placeholder="예: 식품첨가물 / 소고기 / 가공유 ..."
                className="w-full px-3 py-2 rounded-lg border border-slate-300 text-[14px] focus:outline-none focus:ring-2 focus:ring-slate-400"
              />
            </div>
            <div>
              <label className="text-[13px] font-semibold text-slate-700 block mb-1">
                특수 조건
              </label>
              <select
                value={conditionVal}
                onChange={(e) => setConditionVal(e.target.value)}
                className="w-full h-10 px-2 rounded-lg border border-slate-300 text-[14px] bg-white"
              >
                <option value="">(없음)</option>
                <option value="OEM">OEM (주문자상표부착)</option>
                <option value="GMO">GMO 표시대상</option>
                <option value="동등성인정">동등성인정 (유기가공식품)</option>
                <option value="축산물또는동물성식품">축산물/동물성 식품</option>
                <option value="돼지원료포함">돼지 원료 포함</option>
                <option value="반추동물원료포함">반추동물 원료 포함 (소/양/사슴)</option>
                <option value="협약체결국수산물">협약체결국 수산물</option>
                <option value="정밀검사대상">정밀검사 대상</option>
                <option value="외화획득용">외화획득용</option>
                <option value="외화획득용원료">외화획득용 원료</option>
              </select>
            </div>
            <div>
              <label className="text-[13px] font-semibold text-slate-700 block mb-1">
                원재료 키워드
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={keywordInput}
                  onChange={(e) => setKeywordInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleAddKeyword();
                    }
                  }}
                  placeholder="예: 젤라틴, 대마씨, 복어..."
                  className="flex-1 px-3 py-2 rounded-lg border border-slate-300 text-[14px] focus:outline-none focus:ring-2 focus:ring-slate-400"
                />
                <button
                  onClick={handleAddKeyword}
                  className="h-10 px-3 rounded-lg bg-slate-700 text-white text-[13px] font-semibold hover:bg-slate-800"
                >
                  <Plus size={14} />
                </button>
              </div>
              {productKeywords.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {productKeywords.map((kw) => (
                    <span
                      key={kw}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 text-[12px]"
                    >
                      {kw}
                      <button
                        onClick={() => handleRemoveKeyword(kw)}
                        className="text-slate-400 hover:text-rose-600"
                      >
                        <X size={12} />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>

        {/* 선택 정보 (접기) */}
        <section className="border-t border-slate-100 pt-4">
          <button
            onClick={() => setShowOptional(!showOptional)}
            className="flex items-center gap-1.5 text-[13px] font-bold text-slate-700 hover:text-slate-900"
          >
            {showOptional ? (
              <ChevronDown size={14} />
            ) : (
              <ChevronRight size={14} />
            )}
            📅 선택 정보 (시행일·메모)
          </button>
          {showOptional && (
            <div className="mt-3 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[13px] font-semibold text-slate-700 block mb-1">
                    시행 시작일
                  </label>
                  <input
                    type="date"
                    value={effectiveFrom}
                    onChange={(e) => setEffectiveFrom(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-slate-300 text-[14px]"
                  />
                </div>
                <div>
                  <label className="text-[13px] font-semibold text-slate-700 block mb-1">
                    시행 종료일
                  </label>
                  <input
                    type="date"
                    value={effectiveUntil}
                    onChange={(e) => setEffectiveUntil(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-slate-300 text-[14px]"
                  />
                </div>
              </div>
              <div>
                <label className="text-[13px] font-semibold text-slate-700 block mb-1">
                  메모
                </label>
                <input
                  type="text"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="검역관 내부 참고용 메모"
                  className="w-full px-3 py-2 rounded-lg border border-slate-300 text-[14px]"
                />
              </div>
            </div>
          )}
        </section>

        {/* 검증 / 에러 */}
        {(validationError || error) && (
          <div className="bg-rose-50 border border-rose-200 rounded-lg p-3 flex items-start gap-2">
            <AlertCircle size={16} className="text-rose-600 flex-shrink-0 mt-0.5" />
            <div className="text-[13px] text-rose-800">
              {validationError || error}
            </div>
          </div>
        )}

        {/* 액션 버튼 */}
        <div className="flex gap-3 pt-2">
          <button
            onClick={handleReset}
            disabled={submitting}
            className="flex-1 h-11 rounded-lg border border-slate-300 bg-white text-slate-700 font-semibold hover:bg-slate-50 disabled:opacity-50"
          >
            초기화
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="flex-1 h-11 rounded-lg bg-slate-900 text-white font-semibold hover:bg-slate-800 disabled:opacity-50 flex items-center justify-center gap-2"
          >
            <Save size={15} />
            {submitting ? "저장 중..." : "규칙 추가"}
          </button>
        </div>
      </div>
    </div>
  );
}
