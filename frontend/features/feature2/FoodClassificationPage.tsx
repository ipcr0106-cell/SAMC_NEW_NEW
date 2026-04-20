/**
 * F2 식품유형 분류 페이지.
 * F1(수입 판정) 완료 후, 식품공전에 따라 식품유형을 분류한다.
 */
'use client';

import { useState, useEffect, useCallback } from 'react';
import { Loader2 } from 'lucide-react';
import { runFeature2, getFeature2 } from '@/lib/api';
import { apiClient } from '@/services/apiClient';
import Card from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import Badge from '@/components/ui/Badge';

// ── Types ──────────────────────────────────────────────────────────────────
interface RequiredDoc {
  doc_name: string;
  condition: string | null;
  is_mandatory: boolean;
  law_source: string | null;
  food_type: string | null;
}

interface F2Result {
  category_name: string | null;        // 대분류
  category_no?: string | null;
  subcategory_name: string | null;     // 중분류
  food_type: string | null;            // 소분류
  law_ref?: string | null;
  reason: string | null;
  is_alcohol: boolean;
  required_docs: RequiredDoc[];
  source_doc?: string;
}

interface PipelineStepRow {
  status: 'pending' | 'running' | 'waiting_review' | 'completed' | 'error';
  ai_result: F2Result | null;
  final_result: F2Result | null;
  edit_reason?: string | null;
}

type Phase = 'idle' | 'loading' | 'result' | 'error';

// ── Main Component ─────────────────────────────────────────────────────────
interface FoodClassificationPageProps {
  caseId: string;
}

export default function FoodClassificationPage({ caseId }: FoodClassificationPageProps) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const [result, setResult] = useState<F2Result | null>(null);
  const [isConfirmed, setIsConfirmed] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const applyRow = useCallback((row: PipelineStepRow) => {
    const picked = row.final_result ?? row.ai_result;
    if (!picked) return false;
    setResult(picked);
    setIsConfirmed(row.status === 'completed');
    setPhase('result');
    return true;
  }, []);

  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    (async () => {
      try {
        const row = (await getFeature2(caseId)) as PipelineStepRow;
        if (cancelled) return;
        applyRow(row);
      } catch {
        // 404 (결과 없음) → idle 유지
      }
    })();
    return () => { cancelled = true; };
  }, [caseId, applyRow]);

  async function startAnalysis() {
    if (!caseId) return;
    setPhase('loading');
    setErrorMsg('');
    setResult(null);
    setIsConfirmed(false);

    try {
      await runFeature2(caseId);
      const row = (await getFeature2(caseId)) as PipelineStepRow;
      if (!applyRow(row)) {
        setErrorMsg('분류 결과를 가져오지 못했습니다.');
        setPhase('error');
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : '분류 실행 중 오류가 발생했습니다.';
      setErrorMsg(msg);
      setPhase('error');
    }
  }

  async function confirmVerdict() {
    if (!result || !caseId) return;
    setIsSaving(true);
    try {
      await apiClient.patch(`/cases/${caseId}/pipeline/feature/2`, {
        final_result: result,
        edit_reason:  '담당자 확정',
      });
      setIsConfirmed(true);
    } catch (e) {
      const msg = e instanceof Error ? e.message : '확정 저장 중 오류가 발생했습니다.';
      alert(msg);
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Card>
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="text-[11px] font-bold text-blue-600 uppercase tracking-wider">F2</div>
          <h2 className="text-lg font-bold text-slate-900">AI 식품유형 분류 &amp; 법령 근거</h2>
        </div>
        {phase === 'result' && (
          <Button variant="ghost" size="sm" onClick={startAnalysis} disabled={isSaving}>
            재실행
          </Button>
        )}
      </div>

      {phase === 'idle' && (
        <div className="space-y-4">
          <p className="text-sm text-slate-600 leading-relaxed">
            f0 서류 업로드와 F1 수입판정 결과를 바탕으로
            <br />식품유형을 자동 분류하고 적용 법령을 탐색합니다.
          </p>
          <Button variant="primary" size="lg" onClick={startAnalysis} className="w-full">
            AI 분류 실행
          </Button>
        </div>
      )}

      {phase === 'loading' && (
        <div className="flex items-center gap-3 py-4 text-sm text-slate-600">
          <Loader2 size={16} className="animate-spin text-blue-600" />
          <span>AI가 식품유형을 분류하고 있습니다...</span>
        </div>
      )}

      {phase === 'result' && result && (
        <div className="space-y-5">
          {/* 주류 여부 */}
          <section>
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
              주류 여부
            </h3>
            <Badge variant={result.is_alcohol ? 'red' : 'blue'} size="md">
              {result.is_alcohol ? '주류' : '일반식품'}
            </Badge>
          </section>

          <div className="border-t border-slate-200" />

          {/* 3단계 분류 */}
          <section>
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
              식품유형 3단계 분류
            </h3>
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: '대분류', value: result.category_name },
                { label: '중분류', value: result.subcategory_name },
                { label: '소분류', value: result.food_type },
              ].map((c, i) => (
                <div key={i} className="rounded-lg border border-slate-200 p-3 text-center">
                  <div className="text-[11px] text-slate-500 mb-1">{c.label}</div>
                  <div className="text-sm font-bold text-slate-900">{c.value || '—'}</div>
                </div>
              ))}
            </div>
          </section>

          <div className="border-t border-slate-200" />

          {/* 판정 근거 */}
          <section>
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
              판정 근거
            </h3>
            <div className="rounded-lg bg-blue-50 border border-blue-100 p-4">
              <div className="text-sm text-slate-700 mb-2">
                근거 법령: <span className="font-semibold">{result.law_ref || '—'}</span>
              </div>
              {result.reason && (
                <p className="text-sm text-slate-700 leading-relaxed">{result.reason}</p>
              )}
            </div>
          </section>

          {/* 필요서류 */}
          {result.required_docs.length > 0 && (
            <>
              <div className="border-t border-slate-200" />
              <section>
                <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                  수입 필요서류
                </h3>
                <div className="space-y-2">
                  {result.required_docs.map((doc, i) => (
                    <div
                      key={i}
                      className="rounded-lg border border-slate-200 bg-slate-50 p-3"
                    >
                      <div className="flex items-center gap-2 flex-wrap mb-1.5">
                        <Badge variant={doc.is_mandatory ? 'red' : 'blue'} size="sm">
                          {doc.is_mandatory ? '필수' : '선택'}
                        </Badge>
                        <span className="text-sm font-semibold text-slate-800">
                          {doc.doc_name}
                        </span>
                      </div>
                      {doc.condition && (
                        <p className="text-xs text-slate-600 leading-relaxed mb-1">
                          {doc.condition}
                        </p>
                      )}
                      {doc.law_source && (
                        <p className="text-[11px] text-slate-500">근거: {doc.law_source}</p>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            </>
          )}

          {/* 확정 */}
          {!isConfirmed ? (
            <Button
              variant="primary"
              size="lg"
              className="w-full"
              onClick={confirmVerdict}
              disabled={isSaving}
              icon={isSaving ? <Loader2 size={16} className="animate-spin" /> : undefined}
            >
              {isSaving ? '저장 중...' : '판정 확정'}
            </Button>
          ) : (
            <div className="rounded-md bg-emerald-50 border border-emerald-200 p-3 text-sm text-emerald-700 text-center">
              ✅ 판정이 확정되었습니다.
            </div>
          )}
        </div>
      )}

      {phase === 'error' && (
        <div className="space-y-3">
          <div className="rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700">
            {errorMsg}
          </div>
          <Button variant="ghost" size="md" onClick={startAnalysis} className="w-full">
            재시도
          </Button>
        </div>
      )}
    </Card>
  );
}
