'use client';

import { useState } from 'react';
import { apiPost } from '@/lib/api';

// ── Types ──────────────────────────────────────────────────────────────────
interface LawBase {
  id: string;
  tier: number;
  law: string;
  subLaw: string | null;
  subLawTitle: string | null;
  article: string | null;
  effectiveDate: string | null;
  lawNumber: string | null;
  summary: string;
  fullText: string;
  foodTypeName: string | null;
  selected: boolean;
}

interface Classification {
  large: string;
  medium: string;
  small: string;
}

interface Verdict {
  foodType: string;
  lawRef: string;
  confidence: 'high' | 'medium' | 'low';
  reasoning: string;
}

interface S2Data {
  query: string;
  isAlcohol: boolean;
  alcoholBasis: string[];
  classification: Classification;
  lawBases: LawBase[];
  verdict: Verdict;
}

type Phase = 'idle' | 'loading' | 'result' | 'fallback' | 'error';

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
  const [s2Data, setS2Data] = useState<S2Data | null>(null);
  const [lawBases, setLawBases] = useState<LawBase[]>([]);
  const [verdictConfirmed, setVerdictConfirmed] = useState(false);
  const [modal, setModal] = useState<{ title: string; body: string } | null>(null);

  async function startAnalysis() {
    setPhase('loading');
    setErrorMsg('');
    setS2Data(null);
    setLawBases([]);
    setVerdictConfirmed(false);

    try {
      const s2 = await apiPost<S2Data>('/step2', {
        productName:    null,
        origin:         null,
        alcoholContent: null,
        ingredients:    [],
        processes:      [],
        userIsAlcohol:  null,
      });

      setS2Data(s2);
      setLawBases(s2.lawBases ?? []);
      setPhase((s2.lawBases?.length ?? 0) === 0 ? 'fallback' : 'result');
    } catch {
      setErrorMsg('분석 서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.');
      setPhase('error');
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
          {phase !== 'idle' && phase !== 'loading' && (
            <button className="btn btn-ghost btn-sm" onClick={startAnalysis}>재실행</button>
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
        {phase === 'result' && s2Data && (
          <div>
            {/* 섹션 1: 주류 여부 */}
            <div className="step-label" style={{ marginBottom: 6 }}>주류 여부</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
              <span style={{
                display: 'inline-block', padding: '3px 12px', borderRadius: 12,
                fontWeight: 700, fontSize: 13,
                background: s2Data.isAlcohol ? '#fde8e8' : '#e8f4fd',
                color: s2Data.isAlcohol ? '#c0392b' : '#1a6b3a',
              }}>
                {s2Data.isAlcohol ? '주류' : '일반식품'}
              </span>
            </div>
            {(s2Data.alcoholBasis?.length ?? 0) > 0 && (
              <ul style={{ paddingLeft: 18, marginBottom: 14, fontSize: 12, color: '#444', lineHeight: 1.8 }}>
                {s2Data.alcoholBasis.map((b, i) => <li key={i}>{b}</li>)}
              </ul>
            )}

            <div className="section-divider" />

            {/* 섹션 2: 3단계 분류 */}
            <div className="step-label" style={{ marginBottom: 8 }}>식품유형 3단계 분류</div>
            <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
              {[
                { label: '대분류', value: s2Data.classification?.large },
                { label: '중분류', value: s2Data.classification?.medium },
                { label: '소분류', value: s2Data.classification?.small },
              ].map((c, i) => (
                <div key={i} style={{ flex: 1, border: '1px solid #dde3f0', borderRadius: 8, padding: '10px 14px', textAlign: 'center' }}>
                  <div style={{ fontSize: 11, color: '#888', marginBottom: 4 }}>{c.label}</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#1a3a6b' }}>{c.value || '—'}</div>
                </div>
              ))}
            </div>

            <div className="section-divider" />

            {/* 섹션 3: 법령 근거 (read-only) */}
            {lawBases.length > 0 && (
              <>
                <div className="step-label" style={{ marginBottom: 8 }}>적용 법령 근거</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 14 }}>
                  {lawBases.map(lb => {
                    const tierColor = lb.tier === 1 ? { bg: '#e8f0fe', color: '#1a73e8' }
                      : lb.tier === 2 ? { bg: '#e6f4ea', color: '#1e8e3e' }
                      : { bg: '#f5f5f5', color: '#666' };
                    return (
                      <div key={lb.id} style={{
                        padding: '10px 12px', borderRadius: 8,
                        border: '1px solid #e5e5e5', background: '#fafafa',
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 4 }}>
                          <span style={{ fontSize: 10, fontWeight: 700, padding: '1px 7px', borderRadius: 4, background: tierColor.bg, color: tierColor.color }}>
                            T{lb.tier}
                          </span>
                          <span style={{ fontSize: 13, fontWeight: 600, color: '#1a3a6b' }}>
                            {lb.law}{lb.subLaw ? ` ${lb.subLaw}` : ''}
                          </span>
                          {lb.subLawTitle && (
                            <span style={{ fontSize: 11, color: '#888' }}>— {lb.subLawTitle}</span>
                          )}
                          {lb.foodTypeName && (
                            <span className="badge badge-blue" style={{ fontSize: 10 }}>{lb.foodTypeName}</span>
                          )}
                        </div>
                        <div style={{ fontSize: 12, color: '#555', lineHeight: 1.6, marginBottom: 4 }}>{lb.summary}</div>
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                          {lb.effectiveDate && (
                            <span style={{ fontSize: 11, color: '#888' }}>시행: {lb.effectiveDate}</span>
                          )}
                          {lb.lawNumber && (
                            <span style={{ fontSize: 11, color: '#888' }}>{lb.lawNumber}</span>
                          )}
                          {lb.article && (
                            <span style={{ fontSize: 11, color: '#888' }}>조항: {lb.article}</span>
                          )}
                          {lb.fullText && (
                            <button className="btn btn-ghost btn-sm" style={{ fontSize: 11, padding: '2px 8px' }}
                              onClick={() => setModal({ title: `${lb.law}${lb.subLaw ? ' ' + lb.subLaw : ''}`, body: lb.fullText })}>
                              원문 보기
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="section-divider" />
              </>
            )}

            {/* 섹션 4: AI 판정 결과 */}
            <div className="step-label" style={{ marginBottom: 8 }}>AI 판정 결과</div>
            {(() => {
              const v = s2Data.verdict;
              const confLabel = { high: '높음', medium: '보통', low: '낮음' }[v?.confidence ?? 'medium'];
              const confColor = { high: '#1e8e3e', medium: '#f57c00', low: '#c0392b' }[v?.confidence ?? 'medium'];
              return (
                <div className="verdict-box" style={{ marginBottom: 14 }}>
                  <div className="verdict-type">{v?.foodType || '—'}</div>
                  <div className="verdict-sub" style={{ marginBottom: 6 }}>
                    근거 법령: {v?.lawRef || '—'}
                    &nbsp;&nbsp;|&nbsp;&nbsp;신뢰도: <span style={{ color: confColor, fontWeight: 700 }}>{confLabel}</span>
                  </div>
                  {v?.reasoning && (
                    <div style={{ fontSize: 13, color: '#444', lineHeight: 1.7 }}>{v.reasoning}</div>
                  )}
                </div>
              );
            })()}

            {/* 섹션 5: 확정 */}
            {!verdictConfirmed ? (
              <button
                className="btn btn-primary btn-full mt-12"
                onClick={() => setVerdictConfirmed(true)}
              >
                ✓ 판정 확정
              </button>
            ) : (
              <div className="confirmed-badge">✅ 판정이 확정되었습니다.</div>
            )}
          </div>
        )}

        {/* ── fallback ── */}
        {phase === 'fallback' && (
          <div>
            <div className="alert alert-warn">관련 법령을 찾지 못했습니다. 다시 시도하거나 f0 서류를 확인해 주세요.</div>
            <button className="btn btn-ghost btn-full mt-8" onClick={startAnalysis}>재시도</button>
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

      {/* ── 원문 보기 모달 ── */}
      {modal && (
        <div className="modal-overlay open" onClick={e => { if (e.target === e.currentTarget) setModal(null); }}>
          <div className="modal-box">
            <div className="modal-title">{modal.title}</div>
            <div className="modal-body">{modal.body}</div>
            <button className="modal-close" onClick={() => setModal(null)}>닫기</button>
          </div>
        </div>
      )}
    </div>
  );
}
