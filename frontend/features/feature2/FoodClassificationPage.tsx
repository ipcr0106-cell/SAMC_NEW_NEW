/**
 * F2 식품유형 분류 페이지.
 * F1(수입 판정) 완료 후, 식품공전에 따라 식품유형을 분류한다.
 */
'use client';

import { useState, useEffect, useCallback } from 'react';
import { Loader2 } from 'lucide-react';
import { runFeature2, getFeature2 } from '@/lib/api';
import Badge from '@/components/ui/Badge';

// ── Types ──────────────────────────────────────────────────────────────────
interface RequiredDoc {
  doc_name: string;
  condition: string | null;
  is_mandatory: boolean;
  law_source: string | null;
  food_type: string | null;
}

interface LawExcerpt {
  law_name: string;
  text: string;
  score: number;
}

interface F2Result {
  category_name: string | null;
  category_no?: string | null;
  subcategory_name: string | null;
  food_type: string | null;
  law_ref?: string | null;
  reason: string | null;
  is_alcohol: boolean;
  required_docs: RequiredDoc[];
  source_doc?: string;
  law_excerpts?: LawExcerpt[];
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
  const [rerunning, setRerunning] = useState(false);

  const applyRow = useCallback((row: PipelineStepRow) => {
    const picked = row.final_result ?? row.ai_result;
    if (!picked) return false;
    setResult(picked);
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
    setRerunning(true);
    setPhase('loading');
    setErrorMsg('');
    setResult(null);

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
    } finally {
      setRerunning(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-6">
      {/* 헤더 */}
      <header className="pb-3 flex items-start justify-between" style={{ borderBottom: "1px solid var(--ds-color-border)" }}>
        <div>
          <h1 className="text-xl font-semibold" style={{ color: "var(--ds-color-text-heading)" }}>
            기능2 — AI 식품유형 분류
          </h1>
          <p className="mt-1 text-xs" style={{ color: "var(--ds-color-text-secondary)" }}>
            case: {caseId}
          </p>
        </div>
        <button
          type="button"
          onClick={startAnalysis}
          disabled={rerunning}
          className="inline-flex items-center gap-2 h-10 px-5 rounded-xl text-sm font-semibold text-white transition-all disabled:opacity-60"
          style={{ background: "var(--ds-color-primary, #2563eb)" }}
        >
          {rerunning ? "재분석 중..." : "F2 재분석"}
        </button>
      </header>

      {phase === 'idle' && (
        <div className="rounded-lg border border-gray-200 bg-white p-8 text-center">
          <p className="text-sm text-slate-600 mb-4">
            f0 서류 업로드와 F1 수입판정 결과를 바탕으로 식품유형을 자동 분류합니다.
          </p>
          <button
            onClick={startAnalysis}
            className="inline-flex items-center gap-2 h-10 px-5 rounded-xl text-sm font-semibold text-white transition-all"
            style={{ background: "var(--ds-color-primary, #2563eb)" }}
          >
            AI 분류 실행
          </button>
        </div>
      )}

      {phase === 'loading' && (
        <div className="flex items-center gap-3 py-8 justify-center text-sm text-slate-600">
          <Loader2 size={16} className="animate-spin text-blue-600" />
          <span>AI가 식품유형을 분류하고 있습니다...</span>
        </div>
      )}

      {phase === 'result' && result && (
        <div className="space-y-5">
          {/* 주류 여부 */}
          <section className="rounded-lg border border-gray-200 bg-white p-4">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">주류 여부</h3>
            <Badge variant={result.is_alcohol ? 'red' : 'blue'} size="md">
              {result.is_alcohol ? '주류' : '일반식품'}
            </Badge>
          </section>

          {/* 3단계 분류 */}
          <section className="rounded-lg border border-gray-200 bg-white p-4">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">식품유형 3단계 분류</h3>
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

          {/* 판정 근거 */}
          <section className="rounded-lg border border-gray-200 bg-white p-4">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">판정 근거</h3>
            <div className="rounded-lg bg-blue-50 border border-blue-100 p-4">
              <div className="text-sm text-slate-700 mb-2">
                근거 법령: <span className="font-semibold">{result.law_ref || '—'}</span>
              </div>
              {result.reason && (
                <p className="text-sm text-slate-700 leading-relaxed">{result.reason}</p>
              )}
            </div>
            {/* 법령 원문 구절 */}
            {result.law_excerpts && result.law_excerpts.length > 0 && (
              <div className="mt-3 space-y-2">
                <h4 className="text-xs font-semibold text-slate-500">관련 법령 원문</h4>
                {result.law_excerpts.map((ex, i) => (
                  <div key={i} className="rounded border border-slate-200 bg-white p-3">
                    <div className="text-[11px] text-slate-400 mb-1">{ex.law_name}</div>
                    <p className="text-xs text-slate-700 whitespace-pre-wrap leading-relaxed">
                      {ex.text.length > 300 ? ex.text.slice(0, 300) + "…" : ex.text}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </section>

        </div>
      )}

      {phase === 'error' && (
        <div className="space-y-3">
          <div className="rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700">
            {errorMsg}
          </div>
          <button onClick={startAnalysis} className="text-xs text-blue-600 underline">재시도</button>
        </div>
      )}
    </div>
  );
}
