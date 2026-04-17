'use client';

import { useState, useEffect, useCallback } from 'react';
import { runFeature2, getFeature2 } from '@/lib/api';
import { apiClient } from '@/services/apiClient';

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

// ── Sub-components ─────────────────────────────────────────────────────────
function Spinner() {
  return <div className="spin" />;
}

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
    // final_result 우선 → ai_result
    const picked = row.final_result ?? row.ai_result;
    if (!picked) return false;
    setResult(picked);
    setIsConfirmed(row.status === 'completed');
    setPhase('result');
    return true;
  }, []);

  // 진입 시 기존 결과 조회
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
      // run 응답에는 law_ref/category_no 미포함 → GET 재조회로 전체 ai_result 획득
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

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div>
      <div className="card">
        <div className="card-header">
          <div>
            <div className="step-label">F2</div>
            <div className="step-title">AI 식품유형 분류 &amp; 법령 근거</div>
          </div>
          {phase === 'result' && (
            <button className="btn btn-ghost btn-sm" onClick={startAnalysis} disabled={isSaving}>재실행</button>
          )}
        </div>

        {/* ── idle ── */}
        {phase === 'idle' && (
          <>
            <div style={{ fontSize: 13, color: '#666', marginBottom: 12, lineHeight: 1.6 }}>
              f0 서류 업로드와 F1 수입판정 결과를 바탕으로
              <br />식품유형을 자동 분류하고 적용 법령을 탐색합니다.
            </div>
            <button className="btn btn-primary btn-full" onClick={startAnalysis}>
              AI 분류 실행
            </button>
          </>
        )}

        {/* ── loading ── */}
        {phase === 'loading' && (
          <div className="loading-row active" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Spinner />
            <span>AI가 식품유형을 분류하고 있습니다...</span>
          </div>
        )}

        {/* ── result ── */}
        {phase === 'result' && result && (
          <div>
            {/* 섹션 1: 주류 여부 */}
            <div className="step-label" style={{ marginBottom: 6 }}>주류 여부</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <span style={{
                display: 'inline-block', padding: '3px 12px', borderRadius: 12,
                fontWeight: 700, fontSize: 13,
                background: result.is_alcohol ? '#fde8e8' : '#e8f4fd',
                color: result.is_alcohol ? '#c0392b' : '#1a6b3a',
              }}>
                {result.is_alcohol ? '주류' : '일반식품'}
              </span>
            </div>

            <div className="section-divider" />

            {/* 섹션 2: 3단계 분류 */}
            <div className="step-label" style={{ marginBottom: 8 }}>식품유형 3단계 분류</div>
            <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
              {[
                { label: '대분류', value: result.category_name },
                { label: '중분류', value: result.subcategory_name },
                { label: '소분류', value: result.food_type },
              ].map((c, i) => (
                <div key={i} style={{ flex: 1, border: '1px solid #dde3f0', borderRadius: 8, padding: '10px 14px', textAlign: 'center' }}>
                  <div style={{ fontSize: 11, color: '#888', marginBottom: 4 }}>{c.label}</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#1a3a6b' }}>{c.value || '—'}</div>
                </div>
              ))}
            </div>

            <div className="section-divider" />

            {/* 섹션 3: 판정 근거 */}
            <div className="step-label" style={{ marginBottom: 8 }}>판정 근거</div>
            <div className="verdict-box" style={{ marginBottom: 14 }}>
              <div className="verdict-sub" style={{ marginBottom: 6 }}>
                근거 법령: {result.law_ref || '—'}
              </div>
              {result.reason && (
                <div style={{ fontSize: 13, color: '#444', lineHeight: 1.7 }}>{result.reason}</div>
              )}
            </div>

            {/* 섹션 4: 필요서류 */}
            {result.required_docs.length > 0 && (
              <>
                <div className="section-divider" />
                <div className="step-label" style={{ marginBottom: 8 }}>수입 필요서류</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 14 }}>
                  {result.required_docs.map((doc, i) => (
                    <div key={i} style={{
                      padding: '10px 12px', borderRadius: 8,
                      border: '1px solid #e5e5e5', background: '#fafafa',
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 4 }}>
                        <span style={{
                          fontSize: 10, fontWeight: 700, padding: '1px 7px', borderRadius: 4,
                          background: doc.is_mandatory ? '#fde8e8' : '#e8f4fd',
                          color:      doc.is_mandatory ? '#c0392b' : '#1a73e8',
                        }}>
                          {doc.is_mandatory ? '필수' : '선택'}
                        </span>
                        <span style={{ fontSize: 13, fontWeight: 600, color: '#1a3a6b' }}>{doc.doc_name}</span>
                      </div>
                      {doc.condition && (
                        <div style={{ fontSize: 12, color: '#555', lineHeight: 1.6, marginBottom: 4 }}>{doc.condition}</div>
                      )}
                      {doc.law_source && (
                        <div style={{ fontSize: 11, color: '#888' }}>근거: {doc.law_source}</div>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* 섹션 5: 확정 */}
            {!isConfirmed ? (
              <button
                className="btn btn-primary btn-full mt-12"
                onClick={confirmVerdict}
                disabled={isSaving}
              >
                {isSaving ? <><Spinner /> 저장 중...</> : '✓ 판정 확정'}
              </button>
            ) : (
              <div className="confirmed-badge">✅ 판정이 확정되었습니다.</div>
            )}
          </div>
        )}

        {/* ── error ── */}
        {phase === 'error' && (
          <div>
            <div className="alert alert-error">{errorMsg}</div>
            <button className="btn btn-ghost btn-full mt-8" onClick={startAnalysis}>재시도</button>
          </div>
        )}
      </div>
    </div>
  );
}
