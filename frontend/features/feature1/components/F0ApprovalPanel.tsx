"use client";

/**
 * HITL-0: F0 파싱 결과 편집·승인 패널
 *
 * 참조: 계획/f1 재설계 계획/05_HITL_플로우_설계.md §3-2
 * - BasicInfoEditor: 제품명·수출국·OEM·도수 편집
 * - IngredientEditor: 원재료 행 단위 편집 (sub_ingredients 포함)
 * - 공정 정보: process_codes 추가/삭제
 * - OCR 원문 토글
 * - 불일치 경고 배너
 * - PATCH /pipeline/feature/0 + POST /approve 호출
 */

import { useState } from "react";
import { AlertTriangle, ChevronDown, ChevronUp, CheckCircle2, Plus, Trash2 } from "lucide-react";

export interface F0ApprovalPanelProps {
  caseId: string;
  /** F0 파싱 결과 (basic_info + ingredients + process_codes) */
  parsedResult: Record<string, unknown>;
  /** 편집 저장 (edit_reason 필수). 저장만, 승인 별개. */
  onEdit: (final: Record<string, unknown>, reason: string) => Promise<void>;
  /** HITL-0 승인 (signature 선택). 성공 시 status=approved */
  onApprove: (signature?: string) => Promise<void>;
  /** 서버에서 감지한 불일치 경고 (doc_type 키워드 부족 / 제품명 상이 등) */
  warnings?: readonly string[];
  /** 이미 승인된 상태인지 */
  isApproved?: boolean;
}

// ── 기본정보 편집 서브컴포넌트 ──────────────────────────────────────

interface BasicInfo {
  product_name?: string;
  export_country?: string;
  is_oem?: boolean;
  alcohol_degree?: number | null;
}

interface BasicInfoEditorProps {
  value: BasicInfo;
  onChange: (v: BasicInfo) => void;
  disabled?: boolean;
}

function BasicInfoEditor({ value, onChange, disabled }: BasicInfoEditorProps) {
  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold text-gray-700">기본 정보</h4>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-600">
            제품명
          </label>
          <input
            type="text"
            data-testid="f0-product-name"
            value={value.product_name ?? ""}
            onChange={(e) => onChange({ ...value, product_name: e.target.value })}
            disabled={disabled}
            placeholder="제품명 입력"
            className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none disabled:bg-gray-50"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-600">
            수출국
          </label>
          <input
            type="text"
            value={value.export_country ?? ""}
            onChange={(e) => onChange({ ...value, export_country: e.target.value })}
            disabled={disabled}
            placeholder="수출국 입력"
            className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none disabled:bg-gray-50"
          />
        </div>
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="is-oem"
            checked={value.is_oem ?? false}
            onChange={(e) => onChange({ ...value, is_oem: e.target.checked })}
            disabled={disabled}
            className="h-4 w-4 accent-blue-600"
          />
          <label htmlFor="is-oem" className="text-sm text-gray-700">
            OEM / 최초수입 / 유기
          </label>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-600">
            주류 도수 (%)
          </label>
          <input
            type="number"
            value={value.alcohol_degree ?? ""}
            onChange={(e) =>
              onChange({
                ...value,
                alcohol_degree: e.target.value ? Number(e.target.value) : null,
              })
            }
            disabled={disabled}
            placeholder="비주류 시 공란"
            min={0}
            max={100}
            step={0.1}
            className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none disabled:bg-gray-50"
          />
        </div>
      </div>
    </div>
  );
}

// ── 원재료 행 타입 ────────────────────────────────────────────────

interface IngredientRow {
  name: string;
  percentage?: number | null;
  ins?: string | null;
  cas?: string | null;
  part?: string | null;
  sub_ingredients?: string[];
}

interface IngredientEditorProps {
  rows: IngredientRow[];
  onChange: (rows: IngredientRow[]) => void;
  disabled?: boolean;
}

// ── 원재료 행 편집 서브컴포넌트 ──────────────────────────────────────

function IngredientEditor({ rows, onChange, disabled }: IngredientEditorProps) {
  const updateRow = (idx: number, patch: Partial<IngredientRow>) => {
    const next = rows.map((r, i) => (i === idx ? { ...r, ...patch } : r));
    onChange(next);
  };

  const removeRow = (idx: number) => {
    onChange(rows.filter((_, i) => i !== idx));
  };

  const addRow = () => {
    onChange([...rows, { name: "", percentage: null, ins: null, cas: null, part: null, sub_ingredients: [] }]);
  };

  const updateSubIngredient = (rowIdx: number, subIdx: number, val: string) => {
    const subs = [...(rows[rowIdx].sub_ingredients ?? [])];
    subs[subIdx] = val;
    updateRow(rowIdx, { sub_ingredients: subs });
  };

  const addSubIngredient = (rowIdx: number) => {
    const subs = [...(rows[rowIdx].sub_ingredients ?? []), ""];
    updateRow(rowIdx, { sub_ingredients: subs });
  };

  const removeSubIngredient = (rowIdx: number, subIdx: number) => {
    const subs = (rows[rowIdx].sub_ingredients ?? []).filter((_, i) => i !== subIdx);
    updateRow(rowIdx, { sub_ingredients: subs });
  };

  return (
    <div className="space-y-3" data-testid="f0-ingredient-table">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-gray-700">
          원재료 목록
          <span className="ml-2 text-xs font-normal text-gray-500">({rows.length}건)</span>
        </h4>
        {!disabled && (
          <button
            type="button"
            onClick={addRow}
            className="flex items-center gap-1 rounded border border-blue-400 px-2 py-1 text-xs text-blue-600 hover:bg-blue-50"
          >
            <Plus className="h-3 w-3" />
            행 추가
          </button>
        )}
      </div>

      <div className="space-y-2">
        {rows.map((row, idx) => (
          <div
            key={idx}
            className="rounded border border-gray-200 bg-gray-50 p-3"
            data-testid={`ingredient-row-${idx}`}
          >
            <div className="grid grid-cols-12 gap-2">
              {/* 원재료명 */}
              <div className="col-span-4">
                <label className="mb-0.5 block text-[10px] text-gray-500">원재료명 *</label>
                <input
                  type="text"
                  value={row.name}
                  onChange={(e) => updateRow(idx, { name: e.target.value })}
                  disabled={disabled}
                  placeholder="원재료명"
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none disabled:bg-gray-100"
                />
              </div>
              {/* 비율 */}
              <div className="col-span-2">
                <label className="mb-0.5 block text-[10px] text-gray-500">비율(%)</label>
                <input
                  type="number"
                  value={row.percentage ?? ""}
                  onChange={(e) =>
                    updateRow(idx, {
                      percentage: e.target.value ? Number(e.target.value) : null,
                    })
                  }
                  disabled={disabled}
                  placeholder="%"
                  min={0}
                  max={100}
                  step={0.01}
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none disabled:bg-gray-100"
                />
              </div>
              {/* INS */}
              <div className="col-span-2">
                <label className="mb-0.5 block text-[10px] text-gray-500">INS</label>
                <input
                  type="text"
                  value={row.ins ?? ""}
                  onChange={(e) => updateRow(idx, { ins: e.target.value || null })}
                  disabled={disabled}
                  placeholder="INS"
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none disabled:bg-gray-100"
                />
              </div>
              {/* CAS */}
              <div className="col-span-2">
                <label className="mb-0.5 block text-[10px] text-gray-500">CAS</label>
                <input
                  type="text"
                  value={row.cas ?? ""}
                  onChange={(e) => updateRow(idx, { cas: e.target.value || null })}
                  disabled={disabled}
                  placeholder="CAS"
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none disabled:bg-gray-100"
                />
              </div>
              {/* 부위 */}
              <div className="col-span-1">
                <label className="mb-0.5 block text-[10px] text-gray-500">부위</label>
                <input
                  type="text"
                  value={row.part ?? ""}
                  onChange={(e) => updateRow(idx, { part: e.target.value || null })}
                  disabled={disabled}
                  placeholder="부위"
                  className="w-full rounded border border-gray-300 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none disabled:bg-gray-100"
                />
              </div>
              {/* 삭제 버튼 */}
              <div className="col-span-1 flex items-end justify-end">
                {!disabled && (
                  <button
                    type="button"
                    onClick={() => removeRow(idx)}
                    aria-label={`원재료 ${idx + 1} 삭제`}
                    className="rounded p-1 text-red-400 hover:bg-red-50 hover:text-red-600"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>

            {/* 하위 성분 */}
            <div className="mt-2 space-y-1">
              {(row.sub_ingredients ?? []).map((sub, si) => (
                <div key={si} className="flex items-center gap-1 pl-4">
                  <span className="text-[10px] text-gray-400">└</span>
                  <input
                    type="text"
                    value={sub}
                    onChange={(e) => updateSubIngredient(idx, si, e.target.value)}
                    disabled={disabled}
                    placeholder="하위 성분명"
                    className="flex-1 rounded border border-gray-200 px-2 py-0.5 text-xs focus:border-blue-400 focus:outline-none disabled:bg-gray-100"
                  />
                  {!disabled && (
                    <button
                      type="button"
                      onClick={() => removeSubIngredient(idx, si)}
                      aria-label={`하위성분 ${si + 1} 삭제`}
                      className="p-0.5 text-red-300 hover:text-red-500"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  )}
                </div>
              ))}
              {!disabled && (
                <button
                  type="button"
                  onClick={() => addSubIngredient(idx)}
                  className="ml-4 flex items-center gap-0.5 text-[10px] text-blue-400 hover:text-blue-600"
                >
                  <Plus className="h-2.5 w-2.5" />
                  하위 성분 추가
                </button>
              )}
            </div>
          </div>
        ))}

        {rows.length === 0 && (
          <div className="rounded border border-dashed border-gray-300 p-4 text-center text-xs text-gray-400">
            원재료 없음
          </div>
        )}
      </div>
    </div>
  );
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────────

export default function F0ApprovalPanel({
  caseId: _caseId,
  parsedResult,
  onEdit,
  onApprove,
  warnings = [],
  isApproved = false,
}: F0ApprovalPanelProps) {
  // 편집 상태
  const [basicInfo, setBasicInfo] = useState<BasicInfo>(
    (parsedResult.basic_info as BasicInfo) ?? {}
  );
  const [ingredients, setIngredients] = useState<IngredientRow[]>(
    (parsedResult.ingredients as IngredientRow[]) ?? []
  );
  const [processCodes, setProcessCodes] = useState<string[]>(
    (parsedResult.process_codes as string[]) ?? []
  );

  // 편집 사유
  const [editReason, setEditReason] = useState("");

  // OCR 원문 토글
  const [ocrOpen, setOcrOpen] = useState(false);

  // 저장/승인 로딩
  const [isSaving, setIsSaving] = useState(false);
  const [isApproving, setIsApproving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // 승인 확인 모달
  const [showApproveModal, setShowApproveModal] = useState(false);

  const buildFinal = (): Record<string, unknown> => ({
    ...parsedResult,
    basic_info: basicInfo,
    ingredients,
    process_codes: processCodes,
  });

  const handleSave = async () => {
    if (!editReason.trim()) {
      setSaveError("편집 사유를 입력하세요.");
      return;
    }
    setIsSaving(true);
    setSaveError(null);
    try {
      await onEdit(buildFinal(), editReason.trim());
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setIsSaving(false);
    }
  };

  const handleApprove = () => {
    setShowApproveModal(true);
  };

  const handleApproveConfirm = async () => {
    setShowApproveModal(false);
    setIsApproving(true);
    setSaveError(null);
    try {
      await onApprove();
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : "승인 실패");
    } finally {
      setIsApproving(false);
    }
  };

  const addProcessCode = () => {
    setProcessCodes((prev) => [...prev, ""]);
  };

  const updateProcessCode = (idx: number, val: string) => {
    setProcessCodes((prev) => prev.map((c, i) => (i === idx ? val : c)));
  };

  const removeProcessCode = (idx: number) => {
    setProcessCodes((prev) => prev.filter((_, i) => i !== idx));
  };

  const ocrText =
    typeof parsedResult.ocr_raw_text === "string"
      ? parsedResult.ocr_raw_text
      : typeof parsedResult.raw_text === "string"
        ? parsedResult.raw_text
        : null;

  return (
    <section
      data-testid="f0-approval-panel"
      className="space-y-5 rounded-lg border border-gray-200 bg-white p-5"
    >
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-900">HITL-0: F0 파싱 결과 검토 및 승인</h3>
        {isApproved && (
          <span className="flex items-center gap-1 rounded-full bg-green-100 px-3 py-1 text-xs font-medium text-green-700">
            <CheckCircle2 className="h-3.5 w-3.5" />
            승인 완료
          </span>
        )}
      </div>

      {/* 불일치 경고 배너 */}
      {warnings.length > 0 && (
        <div
          data-testid="warnings-banner"
          className="rounded-lg border border-amber-300 bg-amber-50 p-3"
        >
          <div className="mb-1 flex items-center gap-1.5 text-sm font-medium text-amber-800">
            <AlertTriangle className="h-4 w-4" />
            불일치 경고 ({warnings.length}건)
          </div>
          <ul className="space-y-0.5 text-xs text-amber-700">
            {warnings.map((w, i) => (
              <li key={i}>• {w}</li>
            ))}
          </ul>
        </div>
      )}

      {/* 기본정보 편집 */}
      <BasicInfoEditor
        value={basicInfo}
        onChange={setBasicInfo}
        disabled={isApproved}
      />

      {/* 원재료 편집 */}
      <IngredientEditor
        rows={ingredients}
        onChange={setIngredients}
        disabled={isApproved}
      />

      {/* 공정 정보 */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold text-gray-700">공정 정보 (process_codes)</h4>
          {!isApproved && (
            <button
              type="button"
              onClick={addProcessCode}
              className="flex items-center gap-1 rounded border border-blue-400 px-2 py-1 text-xs text-blue-600 hover:bg-blue-50"
            >
              <Plus className="h-3 w-3" />
              추가
            </button>
          )}
        </div>
        <div className="space-y-1">
          {processCodes.map((code, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <input
                type="text"
                value={code}
                onChange={(e) => updateProcessCode(idx, e.target.value)}
                disabled={isApproved}
                placeholder="공정 코드"
                className="flex-1 rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none disabled:bg-gray-50"
              />
              {!isApproved && (
                <button
                  type="button"
                  onClick={() => removeProcessCode(idx)}
                  aria-label={`공정코드 ${idx + 1} 삭제`}
                  className="rounded p-1 text-red-400 hover:bg-red-50 hover:text-red-600"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </div>
          ))}
          {processCodes.length === 0 && (
            <div className="text-xs text-gray-400">공정 코드 없음</div>
          )}
        </div>
      </div>

      {/* OCR 원문 토글 */}
      {ocrText && (
        <div className="rounded border border-gray-200">
          <button
            type="button"
            onClick={() => setOcrOpen((v) => !v)}
            className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            <span>OCR 원문 (검증용)</span>
            {ocrOpen ? (
              <ChevronUp className="h-4 w-4 text-gray-400" />
            ) : (
              <ChevronDown className="h-4 w-4 text-gray-400" />
            )}
          </button>
          {ocrOpen && (
            <pre
              data-testid="ocr-raw-text"
              className="max-h-60 overflow-auto bg-gray-50 px-3 py-2 text-xs text-gray-600 whitespace-pre-wrap"
            >
              {ocrText}
            </pre>
          )}
        </div>
      )}

      {/* 편집 사유 */}
      {!isApproved && (
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-700">
            편집 사유 <span className="text-red-500">*</span>
            <span className="ml-2 text-gray-400">(저장 시 감사 기록 포함)</span>
          </label>
          <textarea
            value={editReason}
            onChange={(e) => setEditReason(e.target.value)}
            rows={2}
            placeholder="편집 사유를 입력하세요."
            className="w-full rounded border border-gray-300 p-2 text-sm focus:border-blue-500 focus:outline-none"
          />
        </div>
      )}

      {/* 오류 메시지 */}
      {saveError && (
        <div className="rounded bg-red-50 px-3 py-2 text-xs text-red-600">
          {saveError}
        </div>
      )}

      {/* 액션 버튼 */}
      {!isApproved && (
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={handleSave}
            disabled={isSaving || isApproving}
            className="rounded border border-blue-500 bg-white px-4 py-2 text-sm text-blue-600 hover:bg-blue-50 disabled:opacity-50"
          >
            {isSaving ? "저장 중..." : "편집 저장"}
          </button>
          <button
            type="button"
            onClick={handleApprove}
            disabled={isSaving || isApproving}
            className="flex items-center gap-1.5 rounded bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
            data-testid="f0-approve-btn"
          >
            <CheckCircle2 className="h-4 w-4" />
            {isApproving ? "승인 중..." : "F0 승인 → F1 실행 허용"}
          </button>
        </div>
      )}

      {/* 승인 확인 모달 */}
      {showApproveModal && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        >
          <div className="w-80 rounded-lg bg-white p-5 shadow-lg">
            <h4 className="mb-2 font-semibold text-gray-900">F0 승인 확인</h4>
            <p className="mb-4 text-sm text-gray-600">
              F0 파싱 결과를 승인하고 F1 분석을 시작합니까?
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowApproveModal(false)}
                className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
              >
                취소
              </button>
              <button
                type="button"
                data-testid="confirm-approve-btn"
                onClick={handleApproveConfirm}
                className="rounded bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700"
              >
                승인 확인
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
