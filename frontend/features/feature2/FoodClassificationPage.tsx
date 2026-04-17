'use client';

import { useState, useRef } from 'react';
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

type RowStatus = 'idle' | 'active' | 'done';
type Step2Phase = 'idle' | 'loading' | 'result' | 'fallback' | 'error';

// ── Constants ──────────────────────────────────────────────────────────────
const S2_LABELS = [
  '주류 여부 판단 중...',
  'Pinecone 법령 검색 중...',
  '식품유형 3단계 분류 중...',
  '판정 결과 정리 중...',
];

// ── Sub-components ─────────────────────────────────────────────────────────
function Spinner() {
  return <div className="spin" />;
}

function LoadingRowEl({ label, status }: { label: string; status: RowStatus }) {
  const text = status === 'done' ? label.replace('중...', '완료') : label;
  return (
    <div className={`loading-row${status === 'done' ? ' done' : status === 'active' ? ' active' : ''}`}>
      {status === 'active' && <Spinner />}
      {status === 'done' && '✅ '}
      {status === 'idle' && <span>⏳</span>}
      {' '}{text}
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────
interface FoodClassificationPageProps {
  caseId: string;
}

export default function FoodClassificationPage({ caseId }: FoodClassificationPageProps) {
  // Step 2
  const [showStep2, setShowStep2] = useState(false);
  const [step2Phase, setStep2Phase] = useState<Step2Phase>('idle');
  const [step2ErrMsg, setStep2ErrMsg] = useState('');
  const [s2Data, setS2Data] = useState<S2Data | null>(null);
  const [lawBases, setLawBases] = useState<LawBase[]>([]);
  const [verdictConfirmed, setVerdictConfirmed] = useState(false);
  const [isVerdictStale, setIsVerdictStale] = useState(false);
  const [isReVerdicting, setIsReVerdicting] = useState(false);
  const [reVerdictErr, setReVerdictErr] = useState('');
  const [s2Rows, setS2Rows] = useState<RowStatus[]>(['active', 'idle', 'idle', 'idle']);

  // Modal
  const [modal, setModal] = useState<{ title: string; body: string } | null>(null);

  // Refs
  const step2CardRef = useRef<HTMLDivElement>(null);

  // ── Step 2 ──
  async function advanceS2Row(idx: number) {
    await new Promise(r => setTimeout(r, 700));
    setS2Rows(prev => prev.map((s, i) => i === idx ? 'done' : i === idx + 1 ? 'active' : s));
  }

  async function startAnalysis() {
    setShowStep2(true);
    setS2Rows(['active', 'idle', 'idle', 'idle']);
    setStep2Phase('loading');
    setS2Data(null);
    setLawBases([]);
    setVerdictConfirmed(false);
    setIsVerdictStale(false);
    setReVerdictErr('');
    setTimeout(() => step2CardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);

    try {
      const step2Promise = apiPost<S2Data>('/step2', {
        productName:    null,
        origin:         null,
        alcoholContent: null,
        ingredients:    [],
        processes:      [],
        userIsAlcohol:  null,
      });

      await advanceS2Row(0);
      await advanceS2Row(1);
      await advanceS2Row(2);

      const s2 = await step2Promise;
      setS2Data(s2);
      setLawBases(s2.lawBases ?? []);
      setS2Rows(['done', 'done', 'done', 'done']);
      await new Promise(r => setTimeout(r, 400));

      if (!s2.lawBases || s2.lawBases.length === 0) {
        setStep2Phase('fallback');
        return;
      }
      setStep2Phase('result');
    } catch {
      setStep2ErrMsg('분석 서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.');
      setStep2Phase('error');
    }
  }

  function toggleLawBase(id: string) {
    setLawBases(prev => prev.map(lb => lb.id === id ? { ...lb, selected: !lb.selected } : lb));
    setIsVerdictStale(true);
    setVerdictConfirmed(false);
    setReVerdictErr('');
  }

  async function reVerdict() {
    if (!s2Data) return;
    const selected = lawBases.filter(lb => lb.selected);
    if (selected.length === 0) {
      setReVerdictErr('최소 1개 이상의 법령을 선택해 주세요.');
      return;
    }
    setIsReVerdicting(true);
    setReVerdictErr('');
    try {
      const result = await apiPost<{ verdict: Verdict }>('/step2-verdict', {
        productName:    '',
        isAlcohol:      s2Data.isAlcohol,
        classification: s2Data.classification,
        selectedLaws:   selected.map(lb => ({
          law:         lb.law,
          subLaw:      lb.subLaw,
          subLawTitle: lb.subLawTitle,
          summary:     lb.summary,
        })),
      });
      setS2Data(prev => prev ? { ...prev, verdict: result.verdict } : prev);
      setIsVerdictStale(false);
    } catch {
      setReVerdictErr('재판정 중 오류가 발생했습니다. 다시 시도해 주세요.');
    } finally {
      setIsReVerdicting(false);
    }
  }

  function confirmVerdict() {
    setVerdictConfirmed(true);
  }

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div>
      {/* 실행 버튼 카드 — 미실행 상태일 때만 */}
      {!showStep2 && (
        <div className="card">
          <div className="card-header">
            <div>
              <div className="step-label">F2</div>
              <div className="step-title">AI 식품유형 분류</div>
            </div>
          </div>
          <div style={{ fontSize: 13, color: '#666', marginBottom: 12, lineHeight: 1.6 }}>
            f0 서류 업로드와 F1 수입판정 결과를 바탕으로
            <br />식품유형을 자동 분류하고 적용 법령을 탐색합니다.
          </div>
          <button className="btn btn-primary btn-full" onClick={startAnalysis}>
            AI 분류 실행
          </button>
        </div>
      )}

      {/* 결과 카드 */}
      {showStep2 && (
        <div className="card" ref={step2CardRef}>
          <div className="card-header">
            <div>
              <div className="step-label">F2</div>
              <div className="step-title">식품유형 분류 &amp; 법령 근거</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={startAnalysis}>재실행</button>
          </div>

          {/* ── 로딩 ── */}
          {step2Phase === 'loading' && (
            <div>
              {S2_LABELS.map((label, i) => (
                <LoadingRowEl key={i} label={label} status={s2Rows[i]} />
              ))}
            </div>
          )}

          {/* ── 결과 ── */}
          {step2Phase === 'result' && s2Data && (
            <div>
              {/* 섹션 1: 주류 여부 판단 */}
              <div className="step-label" style={{ marginBottom: 6 }}>주류 여부 판단</div>
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
              <ul style={{ paddingLeft: 18, marginBottom: 14, fontSize: 12, color: '#444', lineHeight: 1.8 }}>
                {(s2Data.alcoholBasis ?? []).map((b, i) => <li key={i}>{b}</li>)}
              </ul>

              <div className="section-divider" />

              {/* 섹션 2: 3단계 분류 */}
              <div className="step-label" style={{ marginBottom: 8 }}>식품유형 3단계 분류</div>
              {(() => {
                const cls = s2Data.classification;
                return (
                  <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
                    {[
                      { label: '대분류', value: cls?.large },
                      { label: '중분류', value: cls?.medium },
                      { label: '소분류', value: cls?.small },
                    ].map((c, i) => (
                      <div key={i} style={{ flex: 1, border: '1px solid #dde3f0', borderRadius: 8, padding: '10px 14px', textAlign: 'center' }}>
                        <div style={{ fontSize: 11, color: '#888', marginBottom: 4 }}>{c.label}</div>
                        <div style={{ fontSize: 14, fontWeight: 700, color: '#1a3a6b' }}>{c.value || '—'}</div>
                      </div>
                    ))}
                  </div>
                );
              })()}

              <div className="section-divider" />

              {/* 섹션 3: 법령 근거 체크박스 */}
              <div className="step-label" style={{ marginBottom: 8 }}>적용 법령 근거 선택</div>
              <div style={{ fontSize: 12, color: '#888', marginBottom: 10 }}>
                T1·T2 법령이 기본 선택됩니다. 체크박스로 포함 여부를 조정한 뒤 판정을 확정하세요.
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 14 }}>
                {lawBases.map(lb => {
                  const tierColor = lb.tier === 1 ? { bg: '#e8f0fe', color: '#1a73e8' }
                    : lb.tier === 2 ? { bg: '#e6f4ea', color: '#1e8e3e' }
                    : { bg: '#f5f5f5', color: '#666' };
                  return (
                    <div key={lb.id} style={{
                      display: 'flex', alignItems: 'flex-start', gap: 10,
                      padding: '10px 12px', borderRadius: 8,
                      border: `1px solid ${lb.selected ? '#bcd0f5' : '#e5e5e5'}`,
                      background: lb.selected ? '#f7f9fc' : '#fafafa',
                      opacity: lb.selected ? 1 : 0.65,
                    }}>
                      <input type="checkbox" checked={lb.selected} onChange={() => toggleLawBase(lb.id)}
                        style={{ marginTop: 3, cursor: 'pointer', flexShrink: 0 }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
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
                    </div>
                  );
                })}
              </div>

              <div className="section-divider" />

              {/* 섹션 3.5: 재판정 버튼 영역 */}
              {reVerdictErr && (
                <div className="alert alert-error" style={{ marginBottom: 8 }}>{reVerdictErr}</div>
              )}
              <button
                className="btn btn-primary btn-full"
                onClick={reVerdict}
                disabled={isReVerdicting || !isVerdictStale}
                style={{ marginBottom: 16, opacity: isVerdictStale ? 1 : 0.45 }}
              >
                {isReVerdicting
                  ? <><Spinner /> 재판정 중...</>
                  : isVerdictStale
                    ? '선택 법령으로 재판정'
                    : '재판정 완료 (법령 변경 시 자동 활성화)'}
              </button>

              <div className="section-divider" />

              {/* 섹션 4: 판정 결과 */}
              <div className="step-label" style={{ marginBottom: 8 }}>AI 판정 결과</div>

              {isVerdictStale && (
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '8px 12px', borderRadius: 8, marginBottom: 10,
                  background: '#fff8e1', border: '1px solid #f9a825', fontSize: 12, color: '#795548',
                }}>
                  ⚠ 법령 선택이 변경되었습니다. 위 버튼을 눌러 재판정을 실행하세요.
                </div>
              )}

              {(() => {
                const v = s2Data.verdict;
                const confLabel = { high: '높음', medium: '보통', low: '낮음' }[v?.confidence ?? 'medium'];
                const confColor = { high: '#1e8e3e', medium: '#f57c00', low: '#c0392b' }[v?.confidence ?? 'medium'];
                return (
                  <div className="verdict-box" style={{ marginBottom: 14, opacity: isVerdictStale ? 0.55 : 1 }}>
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

              {/* 섹션 5: 판정 확정 */}
              {!verdictConfirmed ? (
                <button
                  className="btn btn-primary btn-full mt-12"
                  onClick={confirmVerdict}
                  disabled={isVerdictStale}
                  title={isVerdictStale ? '재판정을 먼저 실행하세요.' : ''}
                >
                  ✓ 판정 확정
                </button>
              ) : (
                <div className="confirmed-badge">✅ 판정이 확정되었습니다.</div>
              )}
            </div>
          )}

          {/* ── Fallback ── */}
          {step2Phase === 'fallback' && (
            <div>
              <div className="alert alert-warn">관련 법령을 찾지 못했습니다. 다시 시도하거나 f0 서류를 확인해 주세요.</div>
              <button className="btn btn-ghost btn-full mt-8" onClick={startAnalysis}>재시도</button>
            </div>
          )}

          {/* ── 오류 ── */}
          {step2Phase === 'error' && (
            <div>
              <div className="alert alert-error">{step2ErrMsg}</div>
              <button className="btn btn-ghost btn-full mt-8" onClick={startAnalysis}>재시도</button>
            </div>
          )}
        </div>
      )}

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
