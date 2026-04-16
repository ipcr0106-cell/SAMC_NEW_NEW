'use client';

import React, { useState, useEffect, useRef } from 'react';
import { apiPost, apiFormPost } from '@/lib/api';

// ── Types ──────────────────────────────────────────────────────────────────
interface FileItem {
  id: string;
  name: string;
  size: number;
  isHWP: boolean;
  loading: boolean;
  uploadError: boolean;   // 업로드/분석 API 실패 여부
  detection: { type: string; confidence: number } | null;
  userType: string | null;
  analyzed: AnalyzedResult | null;
  _file?: File;
}

interface AnalyzedResult {
  filename: string;
  size: number;
  fallback: boolean;
  error?: string;
  productName?: string;
  manufacturer?: string;
  origin?: string;
  alcoholContent?: number | null;
  ingredients?: string[];
  detection?: { type: string; confidence: number };
  // STEP 1과 동시에 추출된 공정도 데이터
  hasProcessDiagram?: boolean;
  processes?: Process[];
}

interface S1State {
  productName?: string;
  manufacturer?: string;
  origin?: string;
  alcoholContent?: number | null;
  ingredients?: string[];
}

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

interface Process {
  step: string;
  stepKo?: string;
  isBranch?: boolean;
}

interface Step3Response {
  skipped: boolean;
  diagramConclusion: string;
  processes: Process[];
  usedVision: boolean;
  translated?: boolean;
  language?: string;
}

type Tab = 'food-type' | 'process-diagram';
type RowStatus = 'idle' | 'active' | 'done';
type Step1Phase = 'idle' | 'loading' | 'result' | 'fallback' | 'error';
type Step2Phase = 'loading' | 'result' | 'fallback' | 'error';
type PdPhase = 'idle' | 'loading' | 'result' | 'error';

// ── Constants ──────────────────────────────────────────────────────────────
const S2_LABELS = [
  '주류 여부 판단 중...',
  'Pinecone 법령 검색 중...',
  '식품유형 3단계 분류 중...',
  '판정 결과 정리 중...',
];
const PD_LABELS = ['이미지 분석 준비 중...', '공정 단계 추출 중...', '결과 정리 중...'];
const ALLOWED_EXTS = ['pdf', 'jpg', 'jpeg', 'png', 'hwp'];
const MAX_SIZE = 20 * 1024 * 1024;

// ── Helpers ────────────────────────────────────────────────────────────────
function uid() { return Math.random().toString(36).slice(2, 8); }
function fmt(n: number) { return (n / 1024 / 1024).toFixed(1) + ' MB'; }

function detectFileType(name: string): { type: string; confidence: number } {
  const ext = name.split('.').pop()?.toLowerCase() ?? '';
  const map: Record<string, { type: string; confidence: number }> = {
    pdf:  { type: 'MSDS',      confidence: 90 },
    hwp:  { type: 'MSDS',      confidence: 80 },
    jpg:  { type: '제조공정도', confidence: 85 },
    jpeg: { type: '제조공정도', confidence: 85 },
    png:  { type: '제조공정도', confidence: 75 },
  };
  return map[ext] ?? { type: 'MSDS', confidence: 75 };
}

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

function AlcoholCheckbox({
  value,
  onChange,
}: {
  value: boolean | null;
  onChange: (v: boolean | null) => void;
}) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '10px 14px', borderRadius: 8, marginBottom: 10,
      background: value === true ? '#fde8e8' : value === false ? '#e8f4fd' : '#f5f5f5',
      border: `1px solid ${value === true ? '#f5c6cb' : value === false ? '#bee5eb' : '#ddd'}`,
    }}>
      <input
        type="checkbox"
        id="alcohol-check"
        checked={value === true}
        onChange={e => onChange(e.target.checked ? true : null)}
        style={{ width: 16, height: 16, cursor: 'pointer' }}
      />
      <label htmlFor="alcohol-check" style={{ cursor: 'pointer', fontWeight: 600, fontSize: 14 }}>
        이 제품은 <span style={{ color: '#c0392b' }}>주류</span>입니다
      </label>
      <span style={{ fontSize: 12, color: '#888', marginLeft: 4 }}>
        {value === true
          ? '→ 주세법 1순위 적용'
          : value === false
          ? '→ 식품공전 1순위 적용'
          : '(미선택 시 AI가 자동 판단)'}
      </span>
      {value === true && (
        <button
          onClick={() => onChange(null)}
          style={{ marginLeft: 'auto', fontSize: 11, color: '#888', background: 'none', border: 'none', cursor: 'pointer' }}
        >
          취소
        </button>
      )}
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────
export default function Step2Page() {
  // File management
  const [files, setFiles] = useState<FileItem[]>([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  // Step 1
  const [s1, setS1] = useState<S1State | null>(null);
  const [step1Phase, setStep1Phase] = useState<Step1Phase>('idle');
  const [step1ErrMsg, setStep1ErrMsg] = useState('');
  const [productNameInput, setProductNameInput] = useState('');
  const [manufacturerInput, setManufacturerInput] = useState('');
  const [originInput, setOriginInput] = useState('');
  const [manualProductName, setManualProductName] = useState('');
  const [manualOrigin, setManualOrigin] = useState('');
  const [s1LoadingMsg, setS1LoadingMsg] = useState('AI가 파일에서 제품 정보 추출 중...');
  const [s1Done, setS1Done] = useState(false);

  // 주류 여부 사용자 직접 지정 (null = 미선택 → 서버 자동 감지)
  const [userIsAlcohol, setUserIsAlcohol] = useState<boolean | null>(null);

  // Step 2
  const [showStep2, setShowStep2] = useState(false);
  const [step2Phase, setStep2Phase] = useState<Step2Phase>('loading');
  const [step2ErrMsg, setStep2ErrMsg] = useState('');
  const [s2Data, setS2Data] = useState<S2Data | null>(null);
  const [lawBases, setLawBases] = useState<LawBase[]>([]);
  const [verdictConfirmed, setVerdictConfirmed] = useState(false);
  const [isDownloadingPdf, setIsDownloadingPdf] = useState(false);
  const [isVerdictStale, setIsVerdictStale] = useState(false);
  const [isReVerdicting, setIsReVerdicting] = useState(false);
  const [reVerdictErr, setReVerdictErr] = useState('');
  const [s2Rows, setS2Rows] = useState<RowStatus[]>(['active', 'idle', 'idle', 'idle']);

  // Process diagram
  const [pdFile, setPdFile] = useState<File | null>(null);
  const [pdFileName, setPdFileName] = useState('');
  const [pdPreviewUrl, setPdPreviewUrl] = useState<string | null>(null);
  const [pdPhase, setPdPhase] = useState<PdPhase>('idle');
  const [pdRows, setPdRows] = useState<RowStatus[]>(['active', 'idle', 'idle']);
  const [pdProcesses, setPdProcesses] = useState<Process[]>([]);
  const [pdLangNote, setPdLangNote] = useState('');
  const [pdErrMsg, setPdErrMsg] = useState('');
  const [pdWarnMsg, setPdWarnMsg] = useState('');

  // Tab & Modal
  const [activeTab, setActiveTab] = useState<Tab>('food-type');
  const [modal, setModal] = useState<{ title: string; body: string } | null>(null);

  // Refs
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pdFileInputRef = useRef<HTMLInputElement>(null);
  const step2CardRef = useRef<HTMLDivElement>(null);
  // 항상 최신 files를 참조 (async 함수 내 stale closure 방지)
  const filesRef = useRef<FileItem[]>([]);

  // files 변경 시마다 ref 동기화
  useEffect(() => { filesRef.current = files; }, [files]);

  // ── Ctrl+V paste (공정도 탭 활성 시) ──
  useEffect(() => {
    const handlePaste = (e: ClipboardEvent) => {
      if (activeTab !== 'process-diagram') return;
      const items = Array.from(e.clipboardData?.items ?? []);
      for (const item of items) {
        if (item.type.startsWith('image/')) {
          const file = item.getAsFile();
          if (file) { setPdFromFile(file, '클립보드 이미지'); break; }
        }
      }
    };
    document.addEventListener('paste', handlePaste);
    return () => document.removeEventListener('paste', handlePaste);
  }, [activeTab]);

  // ── File handling ──
  async function addFile(file: File) {
    if (file.size > MAX_SIZE) { alert(`"${file.name}" 파일이 20MB를 초과합니다.`); return; }
    const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
    if (!ALLOWED_EXTS.includes(ext)) { alert(`"${file.name}" — 지원하지 않는 형식입니다.`); return; }

    const id = uid();
    const newRow: FileItem = {
      id, name: file.name, size: file.size, isHWP: ext === 'hwp',
      loading: true, uploadError: false, detection: null, userType: null, analyzed: null, _file: file,
    };

    // 중복 체크
    let isDuplicate = false;
    setFiles(prev => {
      if (prev.some(f => f.name === file.name)) {
        isDuplicate = true; return prev;
      }
      return [...prev, newRow];
    });
    if (isDuplicate) { alert(`"${file.name}" 파일이 이미 추가되어 있습니다.`); return; }

    try {
      const form = new FormData();
      form.append('file', file);
      // 타임아웃을 120초로 늘리고 안전한 apiFormPost 함수 사용
      const data = await apiFormPost<AnalyzedResult>('/upload-and-analyze', form, 120_000);

      setFiles(prev => {
        const updated = prev.map(f =>
          f.id === id ? { ...f, name: data.filename, detection: data.detection ?? null, loading: false, uploadError: false, analyzed: data } : f
        );
        return updated;
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : '알 수 없는 오류';
      console.error('[파일 업로드 실패]', msg);
      setStep1ErrMsg(`파일 업로드 중 오류가 발생했습니다: ${msg}`);
      setStep1Phase('error');
      setFiles(prev => {
        const updated = prev.map(f =>
          f.id === id ? { ...f, detection: detectFileType(file.name), loading: false, uploadError: true } : f
        );
        return updated;
      });
    }
  }

  async function processFiles(list: File[]) {
    for (const file of list) await addFile(file);
  }

  function removeFile(id: string) {
    if (isAnalyzing) return;
    setFiles(prev => prev.filter(f => f.id !== id));
  }

  // ── Step 1 ──
  async function startAnalysis() {
    setIsAnalyzing(true);
    setStep1Phase('loading');
    setS1Done(false);

    // 아직 업로드 중인 파일 대기
    const pending = filesRef.current.filter(f => f.loading);
    if (pending.length > 0) {
      setS1LoadingMsg('파일 분석 완료 대기 중...');
      await new Promise<void>(resolve => {
        const iv = setInterval(() => {
          if (filesRef.current.every(f => !f.loading)) { clearInterval(iv); resolve(); }
        }, 300);
      });
    }

    setS1LoadingMsg('AI 분석 결과 확인 중...');
    await new Promise(r => setTimeout(r, 400));

    // 최신 files는 ref에서 읽음 (stale closure 방지)
    const current = filesRef.current;

    // 업로드 자체가 실패한 파일이 있으면 안내
    if (current.every(f => f.uploadError)) {
      setStep1Phase('error');
      setIsAnalyzing(false);
      return;
    }

    const analyzed =
      current.find(f => f.analyzed && !f.analyzed.fallback && f.analyzed.productName)?.analyzed
      ?? current.find(f => f.analyzed)?.analyzed;

    if (!analyzed) {
      setStep1ErrMsg('파일에서 정보를 추출하지 못했습니다. 파일을 삭제 후 다시 업로드해 주세요.');
      setStep1Phase('error');
      setIsAnalyzing(false);
      return;
    }
    if (analyzed.fallback) {
      setStep1ErrMsg(analyzed.error ?? '');
      setStep1Phase('fallback');
      setIsAnalyzing(false);
      return;
    }

    setS1({ ...analyzed });
    setProductNameInput(analyzed.productName ?? '');
    setManufacturerInput(analyzed.manufacturer ?? '');
    setOriginInput(analyzed.origin ?? '');
    setS1Done(true);
    setStep1Phase('result');

    // 공정도가 함께 추출된 경우 → 공정도 탭에 자동 반영
    if (analyzed.hasProcessDiagram && analyzed.processes && analyzed.processes.length > 0) {
      setPdProcesses(analyzed.processes);
      setPdPhase('result');
      setPdFileName(`${analyzed.productName ?? '파일'} (STEP 1에서 자동 추출)`);
      setPdLangNote('');
      setPdWarnMsg('');
    }
  }

  function proceedToStep2(s1Override?: S1State) {
    const final = s1Override ?? { ...s1, productName: productNameInput, manufacturer: manufacturerInput, origin: originInput };
    setS1(final);
    setShowStep2(true);
    setTimeout(() => {
      step2CardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      runStep2(final);
    }, 300);
  }

  function manualProceed() {
    const merged: S1State = { ...(s1 ?? {}) };
    if (manualProductName) merged.productName = manualProductName;
    if (manualOrigin) merged.origin = manualOrigin;
    proceedToStep2(merged);
  }

  function skipStep1() { proceedToStep2(s1 ?? {}); }

  // ── Step 2 ──
  async function advanceS2Row(idx: number) {
    await new Promise(r => setTimeout(r, 700));
    setS2Rows(prev => prev.map((s, i) => i === idx ? 'done' : i === idx + 1 ? 'active' : s));
  }

  async function runStep2(s1Src?: S1State | null) {
    const src = s1Src ?? s1 ?? {};
    setS2Rows(['active', 'idle', 'idle', 'idle']);
    setStep2Phase('loading');
    setS2Data(null);
    setLawBases([]);
    setVerdictConfirmed(false);

    try {
      const step2Promise = apiPost<S2Data>('/step2', {
        productName:    src.productName    ?? null,
        origin:         src.origin         ?? null,
        alcoholContent: src.alcoholContent ?? null,
        ingredients:    src.ingredients    ?? [],
        processes:      (src as S1State & { processes?: Process[] }).processes ?? [],
        userIsAlcohol,
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
        productName:    s1?.productName    ?? '',
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

  async function downloadPdf() {
    if (!s2Data || !s1) return;
    setIsDownloadingPdf(true);
    try {
      const resp = await fetch('/api/v1/report-html', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ step1: s1, step2: { ...s2Data, lawBases } }),
      });
      const html = await resp.text();
      const win = window.open('', '_blank');
      if (win) {
        win.document.write(html);
        win.document.close();
        win.focus();
        setTimeout(() => win.print(), 600);
      }
    } catch { alert('PDF 생성 중 오류가 발생했습니다.'); }
    finally { setIsDownloadingPdf(false); }
  }

  // ── Reset ──
  function resetStep(n: number) {
    if (n === 1) {
      setFiles([]); setS1(null); setIsAnalyzing(false);
      setStep1Phase('idle'); setShowStep2(false);
      setVerdictConfirmed(false); setLawBases([]);
      setIsVerdictStale(false); setReVerdictErr('');
      setUserIsAlcohol(null);
    } else if (n === 2) {
      setS2Data(null); setLawBases([]); setVerdictConfirmed(false);
      setIsVerdictStale(false); setReVerdictErr('');
      runStep2();
    }
  }

  function resetAll() {
    if (!confirm('모든 내용을 초기화하시겠습니까?')) return;
    setFiles([]); setS1(null); setIsAnalyzing(false);
    setStep1Phase('idle'); setShowStep2(false);
    setVerdictConfirmed(false); setLawBases([]);
    setIsVerdictStale(false); setReVerdictErr('');
    setS2Data(null);
  }

  // ── Process diagram ──
  function setPdFromFile(file: File, label: string) {
    setPdFile(file);
    setPdFileName(label || file.name);
    setPdPhase('idle');
    setPdPreviewUrl(file.type.startsWith('image/') ? URL.createObjectURL(file) : null);
  }

  async function runProcessDiagram() {
    if (!pdFile) return;
    setPdPhase('loading');
    setPdRows(['active', 'idle', 'idle']);
    setPdProcesses([]); setPdLangNote(''); setPdWarnMsg(''); setPdErrMsg('');

    const advRow = async (i: number) => {
      await new Promise(r => setTimeout(r, 800));
      setPdRows(prev => prev.map((s, j) => j === i ? 'done' : j === i + 1 ? 'active' : s));
    };

    try {
      const form = new FormData();
      form.append('files', pdFile);
      form.append('s1', JSON.stringify({}));
      form.append('s2FoodType', '');
      const fetchPromise = apiFormPost<Step3Response>('/step3', form, 90_000);

      await advRow(0);
      await advRow(1);
      const data = await fetchPromise;

      setPdRows(['done', 'done', 'done']);
      await new Promise(r => setTimeout(r, 400));

      if (data.translated && data.language) {
        setPdLangNote(`🌐 원문 언어: ${data.language} → 한국어로 번역 후 분석`);
      }
      const procs = data.processes ?? [];
      setPdProcesses(procs);
      setPdWarnMsg(procs.length === 0 ? '⚠ 공정 단계를 판독하지 못했습니다. 공정도 부분만 캡처해서 다시 업로드해 주세요.' : '');
      setPdPhase('result');
    } catch (e) {
      setPdErrMsg(e instanceof Error ? e.message : '분석 중 오류가 발생했습니다.');
      setPdPhase('error');
    }
  }

  function resetProcessDiagram() {
    setPdFile(null); setPdFileName(''); setPdPreviewUrl(null);
    setPdPhase('idle'); setPdProcesses([]);
    setPdLangNote(''); setPdErrMsg(''); setPdWarnMsg('');
    if (pdFileInputRef.current) pdFileInputRef.current.value = '';
  }

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div>
      {/* ── Top Bar ── */}
      <div className="top-bar">
        <span className="logo">SAMC</span>
        <div className="tab-nav">
          {(['food-type', 'process-diagram'] as Tab[]).map(tab => (
            <button key={tab} className={`tab-btn${activeTab === tab ? ' active' : ''}`} onClick={() => setActiveTab(tab)}>
              {tab === 'food-type' ? '식품유형' : '공정도 분석'}
            </button>
          ))}
        </div>
        <button className="btn-reset-all" onClick={resetAll}>전체 초기화</button>
      </div>

      {/* ════════════════════
          TAB 1 — 식품유형
      ════════════════════ */}
      <div className={`page${activeTab === 'food-type' ? ' active' : ''}`}>

        {/* STEP 1 */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="step-label">STEP 1</div>
              <div className="step-title">파일 업로드 &amp; 제품명 추출</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => resetStep(1)}>초기화</button>
          </div>

          {/* 드롭존 */}
          <div
            className="drop-zone"
            onDragOver={e => { e.preventDefault(); e.currentTarget.classList.add('drag-over'); }}
            onDragLeave={e => e.currentTarget.classList.remove('drag-over')}
            onDrop={e => { e.preventDefault(); e.currentTarget.classList.remove('drag-over'); if (!isAnalyzing) processFiles([...e.dataTransfer.files]); }}
            onClick={() => fileInputRef.current?.click()}
          >
            <div className="drop-icon">📂</div>
            <div className="drop-main">파일을 드래그하거나 클릭하여 업로드</div>
            <div className="drop-sub">MSDS 또는 제조공정도 (둘 다 선택사항, 1개 이상 필요)</div>
            <div className="drop-limit">최대 20MB / PDF · JPG · PNG 지원 · HWP 부분 지원</div>
          </div>
          <input ref={fileInputRef} type="file" className="hidden" multiple accept=".pdf,.jpg,.jpeg,.png,.hwp"
            onChange={e => { processFiles([...e.target.files!]); e.target.value = ''; }} />

          {/* 파일 목록 */}
          <div className="file-list">
            {files.map(f => {
              return (
                <div key={f.id} className="file-item">
                  <div style={{ flex: 1 }}>
                    <div className="file-name">📄 {f.name}</div>
                    {f.isHWP && <div className="hwp-warn">HWP 파일 — 일부 내용만 판독될 수 있습니다.</div>}
                    <div className="flex gap-8 mt-8" style={{ flexWrap: 'wrap' }}>
                      {f.loading
                        ? <span className="badge badge-gray">판별 중…</span>
                        : f.uploadError
                          ? <span className="badge badge-red">⚠ 업로드 실패 — 서버 연결 확인 필요</span>
                          : null
                      }
                    </div>
                  </div>
                  <span className="file-size">{fmt(f.size)}</span>
                  <button className="btn btn-danger btn-sm" onClick={() => removeFile(f.id)}>삭제</button>
                </div>
              );
            })}
          </div>

          {isAnalyzing && step1Phase === 'loading' && (
            <div className="alert alert-info">🔒 분석 중에는 파일을 추가할 수 없습니다.</div>
          )}

          <button className="btn btn-primary btn-full" disabled={files.length === 0 || isAnalyzing} onClick={startAnalysis}>
            분석 시작
          </button>

          {/* 로딩 */}
          {step1Phase === 'loading' && (
            <div>
              <div className="section-divider" />
              <div className={`loading-row${s1Done ? ' done' : ' active'}`}>
                {!s1Done && <Spinner />}
                {s1Done ? '✅ 제품 정보 추출 완료' : s1LoadingMsg}
              </div>
            </div>
          )}

          {/* 결과 */}
          {step1Phase === 'result' && (
            <div>
              <div className="section-divider" />
              <div className="product-result">
                <div className="step-label" style={{ marginBottom: 10 }}>추출된 제품 정보</div>
                <div className="product-field">
                  <span className="f-label">제품명</span>
                  <span><input className="editable-input" value={productNameInput} onChange={e => setProductNameInput(e.target.value)} /></span>
                  <span className="f-label">제조사</span>
                  <span><input className="editable-input" value={manufacturerInput} onChange={e => setManufacturerInput(e.target.value)} placeholder="정보 없음" /></span>
                  <span className="f-label">원산지</span>
                  <span><input className="editable-input" value={originInput} onChange={e => setOriginInput(e.target.value)} placeholder="정보 없음" /></span>
                </div>
              </div>
              {/* 주류 여부 체크박스 */}
              <AlcoholCheckbox value={userIsAlcohol} onChange={setUserIsAlcohol} />
              <button className="btn btn-primary btn-full" onClick={() => proceedToStep2()}>
                다음 단계 — 법령 검색 →
              </button>
            </div>
          )}

          {/* Fallback / 오류 */}
          {(step1Phase === 'fallback' || step1Phase === 'error') && (
            <div>
              <div className="alert alert-warn mt-12">
                파일에서 정보를 찾지 못했습니다. 직접 입력하거나, 입력 없이 다음 단계로 진행할 수 있습니다.
              </div>
              {step1Phase === 'error' && step1ErrMsg && (
                <div className="alert alert-error mt-12">{step1ErrMsg}</div>
              )}
              <div className="manual-form">
                <input type="text" value={manualProductName} onChange={e => setManualProductName(e.target.value)} placeholder="제품명 (선택사항)" />
                <input type="text" value={manualOrigin} onChange={e => setManualOrigin(e.target.value)} placeholder="원산지 (선택사항)" />
              </div>
              {/* 주류 여부 체크박스 */}
              <AlcoholCheckbox value={userIsAlcohol} onChange={setUserIsAlcohol} />
              <div className="flex gap-8">
                {step1Phase === 'error' && (
                  <button className="btn btn-ghost btn-full" onClick={startAnalysis}>재시도</button>
                )}
                <button className="btn btn-primary btn-full" onClick={manualProceed}>다음 단계 →</button>
                <button className="btn btn-ghost btn-full" onClick={skipStep1}>정보 없이 진행 →</button>
              </div>
            </div>
          )}
        </div>

        {/* STEP 2 */}
        {showStep2 && (
          <div className="card" ref={step2CardRef}>
            <div className="card-header">
              <div>
                <div className="step-label">STEP 2</div>
                <div className="step-title">식품유형 분류 &amp; 법령 근거</div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => resetStep(2)}>초기화</button>
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

                {/* stale 경고 배너 */}
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

                {/* 섹션 5: 판정 확정 + PDF */}
                {!verdictConfirmed ? (
                  <div className="flex gap-8 mt-12">
                    <button
                      className="btn btn-primary flex-1"
                      onClick={confirmVerdict}
                      disabled={isVerdictStale}
                      title={isVerdictStale ? '재판정을 먼저 실행하세요.' : ''}
                    >
                      ✓ 판정 확정
                    </button>
                  </div>
                ) : (
                  <div>
                    <div className="confirmed-badge">✅ 판정이 확정되었습니다.</div>
                    <button
                      className="btn btn-outline btn-full mt-12"
                      onClick={downloadPdf}
                      disabled={isDownloadingPdf}
                      style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}
                    >
                      {isDownloadingPdf ? <><Spinner /> PDF 생성 중...</> : '⬇ 판정 결과 PDF 다운로드'}
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* ── Fallback ── */}
            {step2Phase === 'fallback' && (
              <div>
                <div className="alert alert-warn">관련 법령을 찾지 못했습니다. 다시 시도하거나 파일을 확인해 주세요.</div>
                <button className="btn btn-ghost btn-full mt-8" onClick={() => runStep2()}>재시도</button>
              </div>
            )}

            {/* ── 오류 ── */}
            {step2Phase === 'error' && (
              <div>
                <div className="alert alert-error">{step2ErrMsg}</div>
                <button className="btn btn-ghost btn-full mt-8" onClick={() => runStep2()}>재시도</button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ════════════════════
          TAB 3 — 공정도 분석
      ════════════════════ */}
      <div className={`page${activeTab === 'process-diagram' ? ' active' : ''}`}>
        <div className="card">
          <div className="card-header">
            <div>
              <div className="step-label">공정도 분석</div>
              <div className="step-title">제조공정 순서 추출</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={resetProcessDiagram}>초기화</button>
          </div>

          {/* STEP 1에서 공정도가 자동 추출된 경우 안내 */}
          {pdPhase === 'result' && pdFileName.includes('자동 추출') && (
            <div className="alert alert-info" style={{ marginBottom: 12 }}>
              ✅ STEP 1 업로드 파일에서 공정도가 자동으로 추출되었습니다.
              정확도가 낮다면 공정도 부분만 캡처해서 아래에 다시 업로드해 주세요.
            </div>
          )}

          {/* 드롭존 — 자동 추출된 경우에도 재업로드 가능 */}
          <div
            className={`pd-drop-zone${pdFile ? ' has-file' : ''}`}
            onDragOver={e => { e.preventDefault(); e.currentTarget.classList.add('drag-over'); }}
            onDragLeave={e => e.currentTarget.classList.remove('drag-over')}
            onDrop={e => { e.preventDefault(); e.currentTarget.classList.remove('drag-over'); const f = e.dataTransfer.files[0]; if (f) setPdFromFile(f, f.name); }}
            onClick={() => pdFileInputRef.current?.click()}
          >
            <div className="pd-drop-icon">📋</div>
            <div className="pd-drop-main">공정도 이미지를 붙여넣기하거나 클릭하여 업로드</div>
            <div className="pd-drop-sub">Ctrl+V 붙여넣기 · 파일 선택 · 드래그 앤 드롭</div>
            <div className="pd-drop-limit">JPG · PNG · PDF 지원 · 최대 20MB</div>
          </div>
          <input ref={pdFileInputRef} type="file" className="hidden" accept=".jpg,.jpeg,.png,.pdf"
            onChange={e => { const f = e.target.files?.[0]; if (f) setPdFromFile(f, f.name); e.target.value = ''; }} />

          {/* 미리보기 */}
          {pdFile && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', background: '#f0f3fa', borderRadius: 8, marginTop: 10, fontSize: 13 }}>
              {pdPreviewUrl
                ? <img src={pdPreviewUrl} alt="미리보기" style={{ maxHeight: 120, borderRadius: 6, border: '1px solid #dde3f0' }} />
                : <span style={{ fontSize: 28 }}>📄</span>
              }
              <span>{pdFileName}</span>
            </div>
          )}

          {/* 분석 버튼 */}
          {pdFile && pdPhase !== 'loading' && (
            <button className="btn btn-primary btn-full mt-12" onClick={runProcessDiagram}>
              공정도 분석 시작
            </button>
          )}

          {/* 로딩 */}
          {pdPhase === 'loading' && (
            <div>
              <div className="section-divider" />
              {PD_LABELS.map((label, i) => (
                <LoadingRowEl key={i} label={label} status={pdRows[i]} />
              ))}
            </div>
          )}

          {/* 결과 */}
          {pdPhase === 'result' && (
            <div>
              <div className="section-divider" />
              {pdLangNote && <div className="alert alert-info">{pdLangNote}</div>}
              <div className="step-label mt-12" style={{ marginBottom: 10 }}>판독된 공정 순서</div>
              <div className="pd-flow">
                {(() => {
                  let mNum = 0;
                  return pdProcesses.map((p, i) => {
                    const isBranch = p.isBranch === true;
                    if (!isBranch) mNum++;
                    const koEl = p.stepKo ? <span className="pd-step-ko">({p.stepKo})</span> : null;
                    const prevMain = i > 0 && pdProcesses.slice(0, i).some(pp => !pp.isBranch);

                    if (isBranch) {
                      return (
                        <div key={i} className="pd-branch-row">
                          <span className="pd-branch-icon">↳</span>
                          <span className="pd-branch-chip">{p.step}{koEl}</span>
                        </div>
                      );
                    }
                    return (
                      <React.Fragment key={i}>
                        {prevMain && <div className="pd-connector" />}
                        <div className="pd-step-row">
                          <div className="pd-step-num">{mNum}</div>
                          <div className="pd-step-name">{p.step}{koEl}</div>
                        </div>
                      </React.Fragment>
                    );
                  });
                })()}
              </div>
              {pdWarnMsg && <div className="alert alert-warn mt-12">{pdWarnMsg}</div>}
              <button className="btn btn-primary btn-full mt-12" onClick={runProcessDiagram}>
                다시 분석
              </button>
            </div>
          )}

          {/* 오류 */}
          {pdPhase === 'error' && (
            <div>
              <div className="section-divider" />
              <div className="alert alert-error">{pdErrMsg}</div>
              <button className="btn btn-ghost btn-full mt-8" onClick={runProcessDiagram}>재시도</button>
            </div>
          )}
        </div>
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
