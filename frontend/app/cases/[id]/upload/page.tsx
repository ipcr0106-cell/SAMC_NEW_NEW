"use client";

import { useCallback, useState, useEffect } from "react";
import { useRouter, useParams, useSearchParams } from "next/navigation";
import {
  Loader2,
  Play,
  RefreshCw,
  AlertTriangle,
  Package,
  CheckCircle,
  XCircle,
  Download,
  ChevronDown,
  ChevronUp,
  Edit2,
  FileText,
  UploadCloud,
  ClipboardCheck,
} from "lucide-react";
import DocumentUploadGrid from "@/components/upload/DocumentUploadGrid";
import LabelImageCard from "@/components/upload/LabelImageCard";
import OcrResultEditor from "@/components/ocr/OcrResultEditor";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import LabelDraftPage from "@/features/feature5/LabelDraftPage";
import {
  getCase,
  updateCase,
  uploadDocument,
  listDocuments,
  deleteDocument,
  parseDocuments,
  saveParsedResult,
  getParsedResult,
  getLabelImages,
  getFeature1,
  getFeature2,
  getFeature3,
  getFeature4,
  runFeature1,
  runFeature2,
  runFeature3,
  runFeature4,
  runFeature5,
  patchFeature2,
  type LabelImageData,
} from "@/lib/api";
import type { UploadedFile } from "@/components/upload/FileDropzone";

// ── 뷰 상태 ──────────────────────────────────────────────
type PageView = "upload" | "running" | "result";

// ── 파이프라인 스텝 상태 ─────────────────────────────────
type StepStatus = "pending" | "running" | "done" | "error";
interface PipelineStep {
  key: string;
  label: string;
  description: string;
  status: StepStatus;
  error?: string;
}
const INITIAL_PIPELINE_STEPS: PipelineStep[] = [
  { key: "f1", label: "F1 수입가능 여부", description: "원재료·첨가물 적합성 검사", status: "pending" },
  { key: "f2", label: "F2 식품유형 분류", description: "식품공전 기반 유형 판정", status: "pending" },
  { key: "f3", label: "F3 필요서류 판정", description: "수입 필요 서류 목록 산출", status: "pending" },
  { key: "f4", label: "F4 라벨 검토", description: "수출국 라벨 표시사항 검토", status: "pending" },
  { key: "f5", label: "F5 한글표시사항", description: "한글 라벨 초안 생성", status: "pending" },
];

interface ParsedData {
  basic_info: {
    product_name: string;
    export_country: string;
    is_first_import: boolean;
    is_organic: boolean;
    is_oem: boolean;
    /** 일본산일 때 F3 전달용 도·현 코드 ("후쿠시마" 또는 "일본34개도부현") */
    japan_prefecture_code?: string;
  };
  ingredients: Array<{
    id: string;
    name: string;
    ratio: string;
    origin: string;
    ins_number: string;
    cas_number: string;
    ingredient_code?: string;
    ingredient_code_name?: string;
  }>;
  process_info: {
    process_codes: string[];
    process_code_reasons?: Array<{ code: string; name?: string; reason: string }>;
    process_code_candidates?: Array<{ code: string; name?: string; reason: string; is_recommended: boolean; confusion_note?: string }>;
    process_steps?: Array<{
      step_number: number;
      step_name_original: string;
      step_name_ko: string;
      recommended_code: string;
      recommended_code_name: string;
      recommended_reason: string;
      similar_codes: Array<{ code: string; name?: string; reason: string; is_recommended: boolean; confusion_note?: string }>;
    }>;
    raw_process_text: string;
    is_incomplete?: boolean;
    incomplete_reason?: string;
  };
  label_info?: {
    export_country: string;
    is_oem: boolean;
    label_texts: string[];
    design_description: string;
    warnings: string[];
  };
  selected_label_image_ids?: string[];
}

// ── 오른쪽 미니바 아이템 ─────────────────────────────────
function MiniBarSection({
  title,
  children,
  defaultOpen = false,
  onEdit,
  statusIcon,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  onEdit?: () => void;
  statusIcon?: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-xl border overflow-hidden"
      style={{ borderColor: "var(--ds-color-border)", background: "var(--ds-color-bg)" }}>
      <button
        className="w-full flex items-center gap-2 px-3.5 py-3 text-left"
        style={{ borderBottom: open ? "1px solid var(--ds-color-border-subtle)" : "none" }}
        onClick={() => setOpen(o => !o)}
      >
        <span className="flex-1 text-[13px] font-semibold" style={{ color: "var(--ds-color-text-heading)" }}>
          {title}
        </span>
        {statusIcon}
        {open ? <ChevronUp size={13} style={{ color: "var(--ds-color-text-tertiary)" }} />
               : <ChevronDown size={13} style={{ color: "var(--ds-color-text-tertiary)" }} />}
      </button>
      {open && (
        <div className="px-3.5 py-3 space-y-2.5">
          {children}
          {onEdit && (
            <button
              onClick={onEdit}
              className="w-full flex items-center justify-center gap-1.5 text-[12px] font-medium py-2 rounded-lg mt-1 transition-colors"
              style={{ background: "var(--ds-color-surface)", color: "var(--ds-color-primary-text)" }}
            >
              <Edit2 size={11} /> 수정하기
            </button>
          )}
        </div>
      )}
    </div>
  );
}


// ── 메인 페이지 ───────────────────────────────────────────
export default function UploadPage() {
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();
  const caseId = params?.id as string;
  const rerunFrom = searchParams?.get("rerun_from");

  const [view, setView] = useState<PageView>("upload");
  const [caseName, setCaseName] = useState<string>("");

  // 업로드 상태
  const [uploadedFiles, setUploadedFiles] = useState<Record<string, string>>({});
  const [restoredFileNames, setRestoredFileNames] = useState<Record<string, UploadedFile[]>>({});
  const [uploading, setUploading] = useState<Record<string, boolean>>({});
  const [uploadErrors, setUploadErrors] = useState<Record<string, string>>({});

  // 파싱 상태
  const [parsing, setParsing] = useState(false);
  const [parsedData, setParsedData] = useState<ParsedData | null>(null);
  const [parseStatus, setParseStatus] = useState<"idle" | "parsing" | "done" | "error">("idle");
  const [parseError, setParseError] = useState<string>("");
  const [extractionErrors, setExtractionErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [savingName, setSavingName] = useState(false);

  // 라벨 이미지
  const [labelImages, setLabelImages] = useState<LabelImageData[]>([]);
  const [labelImagesLoading, setLabelImagesLoading] = useState(false);

  // 재분석 추적
  const [newUploadsSinceParse, setNewUploadsSinceParse] = useState(0);


  // 식품 분류 직접 입력 (f1/f2 건너뛰기)
  const [manualCategory, setManualCategory] = useState("");      // 대분류 (선택)
  const [manualSubcategory, setManualSubcategory] = useState(""); // 중분류 (선택)
  const [manualFoodType, setManualFoodType] = useState("");       // 소분류 (필수)
  const [manualClassSaved, setManualClassSaved] = useState(false); // 수동 분류 저장 완료 여부

  // 파이프라인 결과 (미니바용)
  const [f1Data, setF1Data] = useState<Record<string, unknown> | null>(null);
  const [f2Data, setF2Data] = useState<Record<string, unknown> | null>(null);
  const [f3Data, setF3Data] = useState<Record<string, unknown> | null>(null);
  const [f4Data, setF4Data] = useState<Record<string, unknown> | null>(null);

  // 파이프라인 진행 상태
  const [pipelineSteps, setPipelineSteps] = useState<PipelineStep[]>(INITIAL_PIPELINE_STEPS);

  // F5 다운로드
  const [downloading, setDownloading] = useState(false);

  // 초기 로딩
  const [initialLoading, setInitialLoading] = useState(true);

  // ── 초기 데이터 복원 ─────────────────────────────────
  useEffect(() => {
    if (!caseId) return;
    const load = async () => {
      try {
        const caseData = await getCase(caseId);
        setCaseName(caseData.product_name || "");

        const docsData = await listDocuments(caseId);
        if (docsData.documents?.length > 0) {
          const files: Record<string, string> = {};
          const fileMap: Record<string, UploadedFile[]> = {};
          for (const doc of docsData.documents) {
            files[doc.doc_type] = doc.id;
            if (!fileMap[doc.doc_type]) fileMap[doc.doc_type] = [];
            fileMap[doc.doc_type].push({ id: doc.id, name: doc.file_name });
          }
          setUploadedFiles(files);
          setRestoredFileNames(fileMap);
        }

        try {
          const parsedRes = await getParsedResult(caseId);
          if (parsedRes.parsed_result) {
            setParsedData(parsedRes.parsed_result);
            setParseStatus("done");
          }
        } catch { /* 무시 */ }

        try {
          const imgs = await getLabelImages(caseId);
          if (imgs.length > 0) setLabelImages(imgs);
        } catch { /* 무시 */ }

        // F2 수동 입력 여부 복원 (이전에 저장한 수동 분류가 있는지 확인)
        let isManualClass = false;
        try {
          const f2 = await getFeature2(caseId).catch(() => null);
          if (f2) {
            setF2Data(f2);
            const f2r = (f2 as Record<string, unknown>);
            const f2Result = (f2r?.final_result ?? f2r?.ai_result) as Record<string, unknown> | null;
            // ai_result 없이 final_result만 있으면 이전에 수동 입력한 건
            if (f2r?.final_result && !f2r?.ai_result) {
              isManualClass = true;
              setManualClassSaved(true);
              if (f2Result?.category_name) setManualCategory(f2Result.category_name as string);
              if (f2Result?.subcategory_name) setManualSubcategory(f2Result.subcategory_name as string);
              if (f2Result?.food_type) setManualFoodType(f2Result.food_type as string);
            }
          }
        } catch { /* 무시 */ }

        // 이미 F1~F5 결과가 있으면 result 뷰로
        try {
          const f1 = await getFeature1(caseId);
          if (f1?.ai_result || f1?.final_result) {
            setF1Data(f1);
            const f2r = await getFeature2(caseId).catch(() => null);
            if (f2r) setF2Data(f2r);
            const f3 = await getFeature3(caseId).catch(() => null);
            if (f3) setF3Data(f3);
            const f4 = await getFeature4(caseId).catch(() => null);
            if (f4) setF4Data(f4);
            setView("result");
          } else if (isManualClass) {
            // f1은 없지만 수동분류 건 → f3 결과가 있으면 result 뷰
            const f3 = await getFeature3(caseId).catch(() => null);
            if (f3) {
              setF3Data(f3);
              const f4 = await getFeature4(caseId).catch(() => null);
              if (f4) setF4Data(f4);
              setView("result");
            }
          }
        } catch { /* 아직 결과 없음 */ }

      } catch (e) {
        console.error("[Init] 로드 실패:", e);
      } finally {
        setInitialLoading(false);
      }
    };
    load();
  }, [caseId]);

  // rerun_from 파라미터로 후속 기능 재실행
  useEffect(() => {
    if (!rerunFrom || initialLoading) return;

    const features = ["f1", "f2", "f3", "f4", "f5"];
    const startIdx = features.indexOf(rerunFrom);
    if (startIdx < 0) return;

    const toRun = features.slice(startIdx);

    // 파이프라인 스텝 UI 설정: 이전 단계는 done, 재실행 대상은 pending
    const steps: PipelineStep[] = INITIAL_PIPELINE_STEPS.map((s) => {
      const idx = features.indexOf(s.key);
      if (idx < startIdx) return { ...s, status: "done" as StepStatus };
      return { ...s, status: "pending" as StepStatus };
    });
    setPipelineSteps(steps);

    (async () => {
      setView("running");
      try {
        for (const f of toRun) {
          updateStep(f, { status: "running" });
          try {
            if (f === "f1") { await runFeature1(caseId); const r = await getFeature1(caseId); setF1Data(r); }
            if (f === "f2") { await runFeature2(caseId); const r = await getFeature2(caseId).catch(() => null); if (r) setF2Data(r); }
            if (f === "f3") { await runFeature3(caseId); const r = await getFeature3(caseId).catch(() => null); if (r) setF3Data(r); }
            if (f === "f4") { await runFeature4(caseId); const r = await getFeature4(caseId).catch(() => null); if (r) setF4Data(r); }
            if (f === "f5") { await runFeature5(caseId); }
            updateStep(f, { status: "done" });
          } catch (e) {
            console.error(`[Rerun ${f}]`, e);
            updateStep(f, { status: "error", error: e instanceof Error ? e.message : "오류 발생" });
          }
        }
      } finally {
        // 완료 후 최신 데이터 다시 로드 (사이드바 반영)
        try {
          const f1 = await getFeature1(caseId).catch(() => null);
          if (f1) setF1Data(f1);
          const f2r = await getFeature2(caseId).catch(() => null);
          if (f2r) setF2Data(f2r);
          const f3 = await getFeature3(caseId).catch(() => null);
          if (f3) setF3Data(f3);
          const f4 = await getFeature4(caseId).catch(() => null);
          if (f4) setF4Data(f4);
        } catch { /* 무시 */ }
        router.replace(`/cases/${caseId}/upload`);
        setView("result");
      }
    })();
  }, [rerunFrom, initialLoading]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── 파일 업로드 ─────────────────────────────────────
  const handleFileSelect = useCallback(async (docType: string, file: File) => {
    setUploading(prev => ({ ...prev, [docType]: true }));
    setUploadErrors(prev => { const n = { ...prev }; delete n[docType]; return n; });
    try {
      const result = await uploadDocument(caseId, file, docType);
      setUploadedFiles(prev => ({ ...prev, [docType]: result.doc_id }));
      setRestoredFileNames(prev => ({
        ...prev,
        [docType]: [...(prev[docType] || []), { id: result.doc_id, name: file.name }],
      }));
      if (docType === "label") {
        setLabelImagesLoading(true);
        let attempts = 0;
        const poll = async () => {
          try {
            const imgs = await getLabelImages(caseId);
            if (imgs.length > 0) { setLabelImages(imgs); setLabelImagesLoading(false); return; }
          } catch { /* 무시 */ }
          if (++attempts < 8) setTimeout(poll, 2000); else setLabelImagesLoading(false);
        };
        setTimeout(poll, 2000);
      }
      if (parseStatus === "done") setNewUploadsSinceParse(n => n + 1);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "업로드 실패";
      setUploadErrors(prev => ({ ...prev, [docType]: msg }));
      throw e;
    } finally {
      setUploading(prev => ({ ...prev, [docType]: false }));
    }
  }, [caseId, parseStatus]);

  // ── 파일 삭제 ─────────────────────────────────────
  const handleFileDelete = useCallback(async (docId: string) => {
    try {
      await deleteDocument(docId);
      setRestoredFileNames(prev => {
        const next: Record<string, UploadedFile[]> = {};
        for (const [dt, files] of Object.entries(prev)) {
          const filtered = files.filter(f => f.id !== docId);
          if (filtered.length > 0) next[dt] = filtered;
        }
        return next;
      });
      setUploadedFiles(prev => {
        const next = { ...prev };
        for (const [dt, id] of Object.entries(next)) { if (id === docId) delete next[dt]; }
        return next;
      });
      if (parseStatus === "done") setNewUploadsSinceParse(n => n + 1);
    } catch (e) {
      alert(`파일 삭제 실패: ${e instanceof Error ? e.message : "알 수 없는 오류"}`);
    }
  }, [parseStatus]);

  // ── OCR 파싱 ─────────────────────────────────────
  const handleParse = useCallback(async () => {
    setParsing(true);
    setParseStatus("parsing");
    setParseError("");
    setExtractionErrors([]);
    try {
      const result = await parseDocuments(caseId);
      if (result.status === "completed" && result.parsed_result) {
        setParsedData(result.parsed_result);
        setParseStatus("done");
        setNewUploadsSinceParse(0);
        if (result.suggested_title) setCaseName(result.suggested_title);
        if (result.extraction_errors?.length > 0) setExtractionErrors(result.extraction_errors);
      } else {
        setParseStatus("error");
        setParseError(result.error_message || "파싱 결과가 비어있습니다.");
      }
    } catch (e: unknown) {
      setParseStatus("error");
      setParseError(e instanceof Error ? e.message : "서버에 연결할 수 없습니다.");
    } finally {
      setParsing(false);
    }
  }, [caseId]);

  // ── 임시 저장 ─────────────────────────────────────
  const handleSaveDraft = useCallback(async () => {
    if (!parsedData) return;
    setSaving(true);
    try { await saveParsedResult(caseId, parsedData); }
    catch (e) { console.error("[Save] 저장 실패:", e); }
    finally { setSaving(false); }
  }, [caseId, parsedData]);

  // ── 제품명 저장 ──────────────────────────────────
  const handleCaseNameSave = useCallback(async () => {
    if (!caseName.trim()) return;
    setSavingName(true);
    try { await updateCase(caseId, { product_name: caseName.trim() }); }
    catch (e) { console.error("[CaseName] 저장 실패:", e); }
    finally { setSavingName(false); }
  }, [caseId, caseName]);

  // ── 파이프라인 스텝 상태 업데이트 헬퍼 ──────────────
  const updateStep = useCallback((key: string, update: Partial<PipelineStep>) => {
    setPipelineSteps(prev => prev.map(s => s.key === key ? { ...s, ...update } : s));
  }, []);

  // ── 수동 식품분류 저장 + f3부터 실행하는 파이프라인 ──────
  const handleStartPipelineSkipF1F2 = useCallback(async () => {
    if (!parsedData) return;

    // f2에 수동 분류 저장
    const f2FinalResult = {
      category_name: manualCategory || null,
      category_no: null,
      subcategory_name: manualSubcategory || null,
      food_type: manualFoodType,
      law_ref: null,
      reason: "사용자 직접 입력",
      is_alcohol: false,
      required_docs: [],
      source_doc: "manual_input",
      law_excerpts: [],
    };
    await patchFeature2(caseId, {
      final_result: f2FinalResult,
      edit_reason: "사용자 직접 입력",
    });
    setManualClassSaved(true);
    setF2Data({ final_result: f2FinalResult, status: "completed" });

    // f3~f5 파이프라인만 실행
    const skipSteps: PipelineStep[] = [
      { key: "f1", label: "F1 수입가능 여부", description: "건너뜀 (수동 분류)", status: "done" },
      { key: "f2", label: "F2 식품유형 분류", description: "수동 입력 완료", status: "done" },
      { key: "f3", label: "F3 필요서류 판정", description: "수입 필요 서류 목록 산출", status: "pending" },
      { key: "f4", label: "F4 라벨 검토", description: "수출국 라벨 표시사항 검토", status: "pending" },
      { key: "f5", label: "F5 한글표시사항", description: "한글 라벨 초안 생성", status: "pending" },
    ];
    setPipelineSteps(skipSteps);
    setView("running");

    // F0 저장
    try { await saveParsedResult(caseId, parsedData); } catch { /* 계속 */ }

    // F3
    updateStep("f3", { status: "running" });
    try {
      await runFeature3(caseId);
      const r = await getFeature3(caseId);
      setF3Data(r);
      updateStep("f3", { status: "done" });
    } catch (e) {
      console.error("[F3]", e);
      updateStep("f3", { status: "error", error: e instanceof Error ? e.message : "오류 발생" });
    }

    // F4
    updateStep("f4", { status: "running" });
    try {
      await runFeature4(caseId);
      const r = await getFeature4(caseId);
      setF4Data(r);
      updateStep("f4", { status: "done" });
    } catch (e) {
      console.error("[F4]", e);
      updateStep("f4", { status: "error", error: e instanceof Error ? e.message : "오류 발생" });
    }

    // F5
    updateStep("f5", { status: "running" });
    try {
      await runFeature5(caseId);
      updateStep("f5", { status: "done" });
    } catch (e) {
      console.error("[F5]", e);
      updateStep("f5", { status: "error", error: e instanceof Error ? e.message : "오류 발생" });
    }

    setView("result");
  }, [caseId, parsedData, manualCategory, manualSubcategory, manualFoodType, updateStep]);

  // ── OCR 완료 → F1~F5 파이프라인 자동 실행 ──────────
  const handleStartPipeline = useCallback(async () => {
    if (!parsedData) return;

    // 수동 식품분류가 입력되어 있으면 f1/f2 건너뛰기
    if (manualFoodType.trim()) {
      return handleStartPipelineSkipF1F2();
    }

    setPipelineSteps(INITIAL_PIPELINE_STEPS);
    setView("running");

    // F0 저장
    try { await saveParsedResult(caseId, parsedData); } catch { /* 계속 */ }

    // F1
    updateStep("f1", { status: "running" });
    try {
      await runFeature1(caseId);
      const r = await getFeature1(caseId);
      setF1Data(r);
      updateStep("f1", { status: "done" });
    } catch (e) {
      console.error("[F1]", e);
      updateStep("f1", { status: "error", error: e instanceof Error ? e.message : "오류 발생" });
    }

    // F2
    updateStep("f2", { status: "running" });
    try {
      await runFeature2(caseId);
      const f2r = await getFeature2(caseId).catch(() => null);
      if (f2r) setF2Data(f2r);
      updateStep("f2", { status: "done" });
    } catch (e) {
      console.error("[F2]", e);
      updateStep("f2", { status: "error", error: e instanceof Error ? e.message : "오류 발생" });
    }

    // F3
    updateStep("f3", { status: "running" });
    try {
      await runFeature3(caseId);
      const r = await getFeature3(caseId);
      setF3Data(r);
      updateStep("f3", { status: "done" });
    } catch (e) {
      console.error("[F3]", e);
      updateStep("f3", { status: "error", error: e instanceof Error ? e.message : "오류 발생" });
    }

    // F4
    updateStep("f4", { status: "running" });
    try {
      await runFeature4(caseId);
      const r = await getFeature4(caseId);
      setF4Data(r);
      updateStep("f4", { status: "done" });
    } catch (e) {
      console.error("[F4]", e);
      updateStep("f4", { status: "error", error: e instanceof Error ? e.message : "오류 발생" });
    }

    // F5
    updateStep("f5", { status: "running" });
    try {
      await runFeature5(caseId);
      updateStep("f5", { status: "done" });
    } catch (e) {
      console.error("[F5]", e);
      updateStep("f5", { status: "error", error: e instanceof Error ? e.message : "오류 발생" });
    }

    // 결과 뷰로
    setView("result");
  }, [caseId, parsedData, manualFoodType, handleStartPipelineSkipF1F2, updateStep]);

  // ── F5 다운로드 ──────────────────────────────────
  const handleDownload = async (format: "docx" | "pdf") => {
    setDownloading(true);
    try {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
      const token = typeof window !== "undefined" ? localStorage.getItem("supabase_token") : null;
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(`${API_BASE}/cases/${caseId}/pipeline/feature/5/report?format=${format}`, { headers });
      if (!res.ok) throw new Error("다운로드 실패");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `한글표시사항_${caseName || caseId}.${format}`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { alert("다운로드 실패. F5 분석이 완료되었는지 확인하세요."); }
    finally { setDownloading(false); }
  };

  // ── 파싱 데이터 변경 ──────────────────────────────
  const handleParsedDataChange = useCallback((updated: ParsedData) => {
    setParsedData(updated);
  }, []);

  const uploadedCount = Object.keys(uploadedFiles).length;
  const hasErrors = Object.keys(uploadErrors).length > 0;
  const showParseButton = uploadedCount > 0 && parseStatus !== "done";
  const showReParseButton = parseStatus === "done" && uploadedCount > 0;

  // ── 로딩 ────────────────────────────────────────
  if (initialLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 size={28} className="animate-spin" style={{ color: "var(--ds-color-primary)" }} />
      </div>
    );
  }

  // ═══════════════════════════════════════════
  // 뷰 1: 파이프라인 실행 중
  // ═══════════════════════════════════════════
  if (view === "running") {
    return (
      <div className="max-w-[1440px] mx-auto px-6 py-6">
        {/* 제목 */}
        <div className="mb-4 flex items-center gap-3">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg shrink-0"
            style={{ background: "var(--ds-color-surface)" }}>
            <Package size={16} style={{ color: "var(--ds-color-text-secondary)" }} />
          </div>
          <p className="text-lg font-bold" style={{ color: "var(--ds-color-text-heading)" }}>
            {caseName || "검역 분석 중"}
          </p>
        </div>

        <div className="flex gap-6 items-start">
          {/* 전체 너비: 진행 상태 + 파싱 정보 미리보기 */}
          <div className="flex-1 min-w-0 flex flex-col gap-4 max-w-3xl mx-auto">
            {/* 로딩 헤더 */}
            {(() => {
              const currentStep = pipelineSteps.find(s => s.status === "running");
              const doneCount = pipelineSteps.filter(s => s.status === "done").length;
              const errorCount = pipelineSteps.filter(s => s.status === "error").length;
              return (
                <div className="flex items-center gap-3 px-4 py-3 rounded-xl"
                  style={{ background: "var(--ds-color-primary-soft)" }}>
                  <div className="relative w-8 h-8 shrink-0">
                    <div className="absolute inset-0 rounded-full animate-ping opacity-30"
                      style={{ background: "var(--ds-color-primary)" }} />
                    <div className="relative w-8 h-8 rounded-full flex items-center justify-center"
                      style={{ background: "var(--ds-color-primary)" }}>
                      <Loader2 size={15} className="animate-spin text-white" />
                    </div>
                  </div>
                  <div className="flex-1">
                    <p className="text-[14px] font-semibold" style={{ color: "var(--ds-color-primary-text)" }}>
                      {currentStep ? `${currentStep.label} 분석 중...` : "AI 검역 분석 중"}
                    </p>
                    <p className="text-[12px] mt-0.5" style={{ color: "var(--ds-color-primary-text)", opacity: 0.7 }}>
                      {currentStep?.description || "서류를 법령과 대조하고 있어요"}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-[13px] font-bold tabular-nums" style={{ color: "var(--ds-color-primary-text)" }}>
                      {doneCount + errorCount} / {pipelineSteps.length}
                    </p>
                  </div>
                </div>
              );
            })()}

            {/* 스텝별 진행 목록 */}
            <div className="rounded-xl border overflow-hidden"
              style={{ borderColor: "var(--ds-color-border)", background: "var(--ds-color-bg)" }}>
              {pipelineSteps.map((step, idx) => (
                <div key={step.key}
                  className="flex items-center gap-3 px-4 py-3"
                  style={{
                    borderTop: idx > 0 ? "1px solid var(--ds-color-border-subtle)" : "none",
                    background: step.status === "running" ? "var(--ds-color-primary-soft)" : "transparent",
                    opacity: step.status === "pending" ? 0.45 : 1,
                  }}>
                  {/* 아이콘 */}
                  <div className="w-6 h-6 rounded-full flex items-center justify-center shrink-0"
                    style={{
                      background: step.status === "done" ? "var(--ds-color-success)"
                        : step.status === "error" ? "var(--ds-color-error)"
                        : step.status === "running" ? "var(--ds-color-primary)"
                        : "var(--ds-color-border)",
                    }}>
                    {step.status === "done" && <CheckCircle size={14} className="text-white" />}
                    {step.status === "error" && <XCircle size={14} className="text-white" />}
                    {step.status === "running" && <Loader2 size={14} className="animate-spin text-white" />}
                    {step.status === "pending" && (
                      <span className="text-[11px] font-bold text-white">{idx + 1}</span>
                    )}
                  </div>
                  {/* 텍스트 */}
                  <div className="flex-1 min-w-0">
                    <p className="text-[13px] font-semibold" style={{
                      color: step.status === "running" ? "var(--ds-color-primary-text)"
                        : step.status === "error" ? "var(--ds-color-error-text)"
                        : "var(--ds-color-text-heading)",
                    }}>
                      {step.label}
                    </p>
                    <p className="text-[11px] mt-0.5" style={{
                      color: step.status === "error" ? "var(--ds-color-error-text)"
                        : "var(--ds-color-text-tertiary)",
                    }}>
                      {step.status === "error" ? step.error : step.description}
                    </p>
                  </div>
                  {/* 상태 뱃지 */}
                  <span className="text-[11px] font-medium px-2 py-0.5 rounded-full shrink-0"
                    style={{
                      background: step.status === "done" ? "var(--ds-color-success-soft)"
                        : step.status === "error" ? "var(--ds-color-error-soft)"
                        : step.status === "running" ? "var(--ds-color-primary-soft)"
                        : "transparent",
                      color: step.status === "done" ? "var(--ds-color-success-text)"
                        : step.status === "error" ? "var(--ds-color-error-text)"
                        : step.status === "running" ? "var(--ds-color-primary-text)"
                        : "var(--ds-color-text-tertiary)",
                      border: step.status === "pending" ? "1px solid var(--ds-color-border)" : "none",
                    }}>
                    {step.status === "done" ? "완료" : step.status === "error" ? "오류" : step.status === "running" ? "진행 중" : "대기"}
                  </span>
                </div>
              ))}
            </div>

          </div>
        </div>
      </div>
    );
  }

  // ═══════════════════════════════════════════
  // 뷰 2: 결과 화면 (F5 메인 + 우측 F1~F4 미니바)
  // ═══════════════════════════════════════════
  if (view === "result") {
    // F1 요약
    const f1Result = (f1Data?.final_result || f1Data?.ai_result) as Record<string, unknown> | null;
    const f1Verdict = f1Result?.verdict as string || (f1Result?.import_possible ? "수입가능" : null);
    const f1Possible = f1Verdict === "수입가능" || f1Result?.import_possible;
    const f1Ingredients = (f1Result?.ingredients as Array<Record<string, unknown>>) || [];

    // F3 요약
    const f3Result = (f3Data?.final_result || f3Data?.ai_result || f3Data) as Record<string, unknown> | null;
    const f3SubmitDocs = (f3Result?.submit_docs as Array<Record<string, unknown>>) || [];
    const f3KeepDocs = (f3Result?.keep_docs as Array<Record<string, unknown>>) || [];
    const f3Docs = [...f3SubmitDocs, ...f3KeepDocs];
    const f3Mandatory = f3Docs.filter(d => d.is_mandatory).length;

    // F4 요약
    const f4Result = (f4Data?.ai_result || f4Data?.final_result) as Record<string, unknown> | null;
    const f4Issues = ((f4Result?.issues || f4Data?.issues || []) as Array<Record<string, unknown>>);
    const f4Errors = f4Issues.filter(i => i.severity === "must_fix" || i.severity === "error" || i.status === "fail").length;
    const f4Warnings = f4Issues.filter(i => i.severity === "review_needed" || i.severity === "warning" || i.status === "unclear").length;

    return (
      <div className="max-w-[1440px] mx-auto px-6 py-5 flex gap-5">
        {/* ── 메인: F5 결과 ── */}
        <div className="flex-1 min-w-0">
          {/* 헤더 */}
          <div className="mb-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-[11px] font-medium mb-1.5 tracking-wide"
                  style={{ color: "var(--ds-color-text-tertiary)" }}>
                  F5 · 한글표시사항 최종결과
                </p>
                <h1 className="text-[22px] font-bold leading-tight" style={{ color: "var(--ds-color-text-heading)" }}>
                  {caseName || "한글표시사항"}
                </h1>
              </div>
              {/* 액션 버튼 */}
              <div className="flex items-center gap-2 shrink-0 mt-1">
                <button
                  onClick={() => handleDownload("docx")}
                  disabled={downloading}
                  className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs font-medium bg-white border border-slate-200 text-slate-700 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700 transition-colors disabled:opacity-50"
                >
                  {downloading ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
                  DOCX
                </button>
                <button
                  onClick={() => handleDownload("pdf")}
                  disabled={downloading}
                  className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs font-medium bg-white border border-slate-200 text-slate-700 hover:bg-red-50 hover:border-red-300 hover:text-red-700 transition-colors disabled:opacity-50"
                >
                  {downloading ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
                  PDF
                </button>
              </div>
            </div>
          </div>

          {/* F5 본문 */}
          <LabelDraftPage />
        </div>

        {/* ── 우측 미니바 ── */}
        <div className="w-[240px] shrink-0 space-y-2 sticky top-[72px] self-start max-h-[calc(100vh-90px)] overflow-y-auto">
          <p className="text-[11px] font-semibold mb-3 tracking-wide"
            style={{ color: "var(--ds-color-text-tertiary)" }}>
            분석 결과
          </p>

          {/* F0 서류 정보 */}
          <MiniBarSection
            title="F0 서류 정보"
            defaultOpen={false}
            onEdit={() => setView("upload")}
          >
            {parsedData ? (
              <div className="space-y-2.5">
                <div>
                  <p className="text-[11px] mb-0.5" style={{ color: "var(--ds-color-text-tertiary)" }}>제품명</p>
                  <p className="text-[13px] font-semibold leading-snug" style={{ color: "var(--ds-color-text-primary)" }}>
                    {parsedData.basic_info.product_name || "—"}
                  </p>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[12px]" style={{ color: "var(--ds-color-text-secondary)" }}>원산지</span>
                  <span className="text-[12px] font-medium" style={{ color: "var(--ds-color-text-primary)" }}>
                    {parsedData.basic_info.export_country || "—"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[12px]" style={{ color: "var(--ds-color-text-secondary)" }}>원재료</span>
                  <span className="text-[13px] font-bold" style={{ color: "var(--ds-color-text-heading)" }}>
                    {parsedData.ingredients.length}종
                  </span>
                </div>
                {[
                  parsedData.basic_info.is_organic && "유기농",
                  parsedData.basic_info.is_oem && "OEM",
                  parsedData.basic_info.is_first_import && "최초수입",
                ].filter(Boolean).length > 0 && (
                  <div className="flex flex-wrap gap-1 pt-1 border-t"
                    style={{ borderColor: "var(--ds-color-border-subtle)" }}>
                    {[
                      parsedData.basic_info.is_organic && "유기농",
                      parsedData.basic_info.is_oem && "OEM",
                      parsedData.basic_info.is_first_import && "최초수입",
                    ].filter(Boolean).map((tag, i) => (
                      <span key={i} className="text-[11px] px-2 py-0.5 rounded-full"
                        style={{ background: "var(--ds-color-primary-soft)", color: "var(--ds-color-primary-text)" }}>
                        {tag as string}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-[12px]" style={{ color: "var(--ds-color-text-tertiary)" }}>데이터 없음</p>
            )}
          </MiniBarSection>

          {/* F1 수입판정 — 수동 분류 건이면 숨김 */}
          {!manualClassSaved && (
          <MiniBarSection
            title="F1 수입판정"
            defaultOpen={true}
            onEdit={() => router.push(`/cases/${caseId}/f1?from=view`)}
            statusIcon={f1Verdict
              ? (f1Possible
                ? <CheckCircle size={13} style={{ color: "var(--ds-color-success)" }} />
                : <XCircle size={13} style={{ color: "var(--ds-color-error)" }} />)
              : undefined
            }
          >
            {f1Result ? (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  {f1Possible
                    ? <CheckCircle size={15} style={{ color: "var(--ds-color-success)" }} />
                    : <XCircle size={15} style={{ color: "var(--ds-color-error)" }} />
                  }
                  <span className="text-[14px] font-bold"
                    style={{ color: f1Possible ? "var(--ds-color-success-text)" : "var(--ds-color-error-text)" }}>
                    {f1Verdict || "—"}
                  </span>
                </div>
                {f1Ingredients.length > 0 && (
                  <div>
                    <p className="text-[11px] mb-1.5" style={{ color: "var(--ds-color-text-tertiary)" }}>
                      원재료 {f1Ingredients.length}종
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {f1Ingredients.slice(0, 5).map((ing, i) => {
                        const st = (ing.allow_verdict || ing.status) as string;
                        const ok = st === "allowed";
                        return (
                          <span key={i} className="text-[11px] px-2 py-0.5 rounded-full"
                            style={{
                              background: ok ? "var(--ds-color-success-soft)" : "var(--ds-color-warning-soft)",
                              color: ok ? "var(--ds-color-success-text)" : "var(--ds-color-warning-text)",
                            }}>
                            {String(ing.name || "")}
                          </span>
                        );
                      })}
                      {f1Ingredients.length > 5 && (
                        <span className="text-[11px] px-1.5 py-0.5"
                          style={{ color: "var(--ds-color-text-tertiary)" }}>
                          +{f1Ingredients.length - 5}
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-[12px]" style={{ color: "var(--ds-color-text-tertiary)" }}>결과 없음</p>
            )}
          </MiniBarSection>
          )}

          {/* F2 식품유형 분류 — 수동 분류 건이면 숨김 */}
          {!manualClassSaved && (
          <MiniBarSection
            title="F2 식품유형"
            onEdit={() => router.push(`/cases/${caseId}/f2?from=view`)}
            statusIcon={(() => {
              const f2r = (f2Data as Record<string, unknown> | null);
              const f2Result = (f2r?.final_result ?? f2r?.ai_result) as Record<string, unknown> | null;
              return f2Result?.food_type ? <CheckCircle size={13} style={{ color: "var(--ds-color-success)" }} /> : undefined;
            })()}
          >
            {(() => {
              const f2r = (f2Data as Record<string, unknown> | null);
              const f2Result = (f2r?.final_result ?? f2r?.ai_result) as Record<string, unknown> | null;
              const foodType = f2Result?.food_type as string | undefined;
              const category = f2Result?.category_name as string | undefined;
              return foodType ? (
                <div className="space-y-1">
                  <span className="text-[13px] font-bold" style={{ color: "var(--ds-color-text-heading)" }}>{foodType}</span>
                  {category && <p className="text-[11px]" style={{ color: "var(--ds-color-text-tertiary)" }}>{category}</p>}
                </div>
              ) : (
                <p className="text-[12px]" style={{ color: "var(--ds-color-text-tertiary)" }}>F1 판정 후 식품유형 분류</p>
              );
            })()}
          </MiniBarSection>
          )}

          {/* F3 필요서류 */}
          <MiniBarSection
            title="F3 필요서류"
            onEdit={() => router.push(`/cases/${caseId}/f3?from=view`)}
            statusIcon={f3Docs.length > 0
              ? <FileText size={13} style={{ color: "var(--ds-color-primary)" }} />
              : undefined}
          >
            {f3Result ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[12px]" style={{ color: "var(--ds-color-text-secondary)" }}>필수 서류</span>
                  <span className="text-[14px] font-bold" style={{ color: "var(--ds-color-error-text)" }}>
                    {f3Mandatory}건
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[12px]" style={{ color: "var(--ds-color-text-secondary)" }}>전체 서류</span>
                  <span className="text-[14px] font-bold" style={{ color: "var(--ds-color-text-heading)" }}>
                    {f3Docs.length}건
                  </span>
                </div>
                <div className="space-y-1 pt-1 border-t"
                  style={{ borderColor: "var(--ds-color-border-subtle)" }}>
                  {f3Docs.slice(0, 3).map((d, i) => (
                    <div key={i} className="flex items-center gap-1.5">
                      <div className="w-1.5 h-1.5 rounded-full shrink-0"
                        style={{ background: d.is_mandatory ? "var(--ds-color-error)" : "var(--ds-color-text-tertiary)" }} />
                      <span className="text-[12px] truncate" style={{ color: "var(--ds-color-text-secondary)" }}>
                        {String(d.doc_name || "")}
                      </span>
                    </div>
                  ))}
                  {f3Docs.length > 3 && (
                    <p className="text-[11px]" style={{ color: "var(--ds-color-text-tertiary)" }}>
                      + {f3Docs.length - 3}개 더
                    </p>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-[12px]" style={{ color: "var(--ds-color-text-tertiary)" }}>결과 없음</p>
            )}
          </MiniBarSection>

          {/* F4 라벨검토 */}
          <MiniBarSection
            title="F4 라벨검토"
            onEdit={() => router.push(`/cases/${caseId}/f4?from=view`)}
            statusIcon={f4Issues.length > 0
              ? (f4Errors > 0
                ? <XCircle size={13} style={{ color: "var(--ds-color-error)" }} />
                : <CheckCircle size={13} style={{ color: "var(--ds-color-success)" }} />)
              : undefined}
          >
            {f4Result || f4Issues.length > 0 ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[12px]" style={{ color: "var(--ds-color-text-secondary)" }}>오류</span>
                  <span className="text-[14px] font-bold"
                    style={{ color: f4Errors > 0 ? "var(--ds-color-error-text)" : "var(--ds-color-success-text)" }}>
                    {f4Errors}건
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[12px]" style={{ color: "var(--ds-color-text-secondary)" }}>주의</span>
                  <span className="text-[14px] font-bold"
                    style={{ color: f4Warnings > 0 ? "var(--ds-color-warning-text)" : "var(--ds-color-text-tertiary)" }}>
                    {f4Warnings}건
                  </span>
                </div>
                {f4Errors === 0 && f4Warnings === 0 && (
                  <div className="flex items-center gap-1.5 pt-1">
                    <CheckCircle size={13} style={{ color: "var(--ds-color-success)" }} />
                    <span className="text-[12px]" style={{ color: "var(--ds-color-success-text)" }}>이상 없음</span>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-[12px]" style={{ color: "var(--ds-color-text-tertiary)" }}>결과 없음</p>
            )}
          </MiniBarSection>

          {/* 재분석 버튼 */}
          <button
            onClick={handleStartPipeline}
            className="w-full flex items-center justify-center gap-1.5 text-[12px] font-medium py-2.5 rounded-lg border transition-all"
            style={{ color: "var(--ds-color-text-secondary)", borderColor: "var(--ds-color-border)", background: "var(--ds-color-surface)" }}
          >
            <RefreshCw size={12} /> 전체 재분석
          </button>

          {/* 실무자 최종 확정 포탈 마운트 포인트 */}
        </div>
      </div>
    );
  }

  // ═══════════════════════════════════════════
  // 뷰 3: 업로드 화면 (기본)
  // ═══════════════════════════════════════════
  return (
    <div className="max-w-[1440px] mx-auto px-6 py-6 pb-28">
      {/* 검역건 제목 입력 */}
      <div className="mb-4 flex items-center gap-3">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg shrink-0"
          style={{ background: "var(--ds-color-surface)" }}>
          <Package size={16} style={{ color: "var(--ds-color-text-secondary)" }} />
        </div>
        <div className="flex-1">
          <label className="text-xs mb-1 block" style={{ color: "var(--ds-color-text-tertiary)" }}>검역건 제품명</label>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={caseName}
              onChange={(e) => setCaseName(e.target.value)}
              onBlur={handleCaseNameSave}
              onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
              placeholder="예: FJ 캡 프론티어 위스키"
              className="flex-1 text-lg font-bold bg-transparent border-b-2 border-transparent focus:outline-none py-0.5 placeholder:font-normal"
              style={{ color: "var(--ds-color-text-heading)" }}
            />
            {savingName && <Loader2 size={14} className="animate-spin shrink-0" style={{ color: "var(--ds-color-text-tertiary)" }} />}
          </div>
        </div>
      </div>

      {/* 본문 */}
      <div className="mt-4 flex gap-6 items-start" style={{ minHeight: "calc(100vh - 280px)" }}>
        {/* 좌측: 서류 업로드 */}
        <div className="w-[37%] shrink-0 flex flex-col gap-4 sticky top-4 max-h-[calc(100vh-100px)] overflow-y-auto">
          <Card padding="lg">
            <DocumentUploadGrid
              onFileSelect={handleFileSelect}
              restoredFiles={restoredFileNames}
              onFileDelete={handleFileDelete}
            />
          </Card>

          {hasErrors && (
            <div className="rounded-xl px-4 py-3" style={{ background: "var(--ds-color-error-soft)" }}>
              <div className="flex items-center gap-2 mb-1">
                <AlertTriangle size={14} style={{ color: "var(--ds-color-error-text)" }} />
                <span className="text-xs font-semibold" style={{ color: "var(--ds-color-error-text)" }}>업로드 오류</span>
              </div>
              {Object.entries(uploadErrors).map(([dt, msg]) => (
                <p key={dt} className="text-xs ml-5" style={{ color: "var(--ds-color-error-text)" }}>{dt}: {msg}</p>
              ))}
            </div>
          )}

          {(labelImagesLoading || labelImages.length > 0) && (
            <LabelImageCard caseId={caseId} images={labelImages} loading={labelImagesLoading} />
          )}

          {/* 식품 분류 직접 입력 (F1/F2 건너뛰기) */}
          <Card padding="lg">
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <ClipboardCheck size={15} style={{ color: "var(--ds-color-primary)" }} />
                <span className="text-[13px] font-semibold" style={{ color: "var(--ds-color-text-heading)" }}>
                  식품 분류 직접 입력
                </span>
              </div>
              <p className="text-[11px] leading-relaxed" style={{ color: "var(--ds-color-text-tertiary)" }}>
                식품유형을 이미 알고 있다면 직접 입력하세요. 입력 시 F1(수입판정)·F2(식품분류)를 건너뛰고 바로 <strong>필요서류 검토</strong> 단계부터 시작합니다.
              </p>
              <div className="space-y-2 pt-1">
                <div>
                  <label className="text-[11px] mb-1 block" style={{ color: "var(--ds-color-text-tertiary)" }}>
                    대분류 <span className="opacity-60">(선택)</span>
                  </label>
                  <input
                    type="text"
                    value={manualCategory}
                    onChange={(e) => setManualCategory(e.target.value)}
                    placeholder="예: 주류, 과자류"
                    className="w-full px-3 py-2 text-[13px] rounded-lg border bg-transparent focus:outline-none focus:ring-1"
                    style={{
                      borderColor: "var(--ds-color-border)",
                      color: "var(--ds-color-text-primary)",
                      ["--tw-ring-color" as string]: "var(--ds-color-primary)",
                    }}
                  />
                </div>
                <div>
                  <label className="text-[11px] mb-1 block" style={{ color: "var(--ds-color-text-tertiary)" }}>
                    중분류 <span className="opacity-60">(선택)</span>
                  </label>
                  <input
                    type="text"
                    value={manualSubcategory}
                    onChange={(e) => setManualSubcategory(e.target.value)}
                    placeholder="예: 증류주류, 비스킷"
                    className="w-full px-3 py-2 text-[13px] rounded-lg border bg-transparent focus:outline-none focus:ring-1"
                    style={{
                      borderColor: "var(--ds-color-border)",
                      color: "var(--ds-color-text-primary)",
                      ["--tw-ring-color" as string]: "var(--ds-color-primary)",
                    }}
                  />
                </div>
                <div>
                  <label className="text-[11px] mb-1 block" style={{ color: "var(--ds-color-text-heading)" }}>
                    소분류 <span className="text-[10px] font-bold" style={{ color: "var(--ds-color-error)" }}>필수</span>
                  </label>
                  <input
                    type="text"
                    value={manualFoodType}
                    onChange={(e) => setManualFoodType(e.target.value)}
                    placeholder="예: 위스키, 맥주, 비스킷"
                    className="w-full px-3 py-2 text-[13px] rounded-lg border bg-transparent focus:outline-none focus:ring-1"
                    style={{
                      borderColor: manualFoodType.trim() ? "var(--ds-color-success)" : "var(--ds-color-border)",
                      color: "var(--ds-color-text-primary)",
                      ["--tw-ring-color" as string]: "var(--ds-color-primary)",
                    }}
                  />
                </div>
              </div>
              {manualClassSaved && (
                <div className="flex items-center gap-1.5 pt-1">
                  <CheckCircle size={12} style={{ color: "var(--ds-color-success)" }} />
                  <span className="text-[11px]" style={{ color: "var(--ds-color-success-text)" }}>저장됨</span>
                </div>
              )}
            </div>
          </Card>

          {parseStatus === "error" && parseError && (
            <div className="rounded-xl px-4 py-3" style={{ background: "var(--ds-color-error-soft)" }}>
              <div className="flex items-center gap-2 mb-1">
                <AlertTriangle size={14} style={{ color: "var(--ds-color-error-text)" }} />
                <span className="text-xs font-semibold" style={{ color: "var(--ds-color-error-text)" }}>분석 실패</span>
              </div>
              <p className="text-xs ml-5" style={{ color: "var(--ds-color-error-text)" }}>{parseError}</p>
              <button onClick={handleParse} className="mt-2 ml-5 text-xs font-medium underline"
                style={{ color: "var(--ds-color-error-text)" }}>다시 시도</button>
            </div>
          )}
        </div>

        {/* 우측: OCR 결과 편집 */}
        <div className="flex-1 flex flex-col min-w-0">
          <OcrResultEditor
            parsedData={parsedData}
            parseStatus={parseStatus}
            caseId={caseId}
            onDataChange={handleParsedDataChange}
            extractionErrors={extractionErrors}
            externalLabelImages={labelImages.length > 0 ? labelImages : undefined}
            externalLabelImagesLoading={labelImagesLoading}
            onParse={handleParse}
            isParsing={parsing}
          />
        </div>
      </div>

      {/* 하단 고정 액션바 */}
      <div className="fixed bottom-0 left-0 right-0 z-50">
        <div className="max-w-[1440px] mx-auto px-6">
          <div className="ds-actionbar-shell px-8 py-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className={`ds-status-dot ${
                parseStatus === "done" ? "ds-status-dot-done animate-pulse"
                : parseStatus === "parsing" ? "ds-status-dot-progress animate-pulse"
                : parseStatus === "error" ? "ds-status-dot-error" : ""
              }`} />
              <span className="text-sm" style={{ color: "var(--ds-color-text-secondary)" }}>
                {parseStatus === "done" && newUploadsSinceParse > 0
                  ? `${newUploadsSinceParse}개 파일 변경됨 · 재분석 후 검역 분석 시작`
                  : parseStatus === "done" ? "OCR 분석 완료 · 내용 확인 후 검역 분석을 시작하세요"
                  : parseStatus === "parsing" ? "AI 분석 진행 중..."
                  : parseStatus === "error" ? "분석 실패 · 파일을 확인해주세요"
                  : uploadedCount > 0 ? `${uploadedCount}개 파일 업로드됨 · OCR 분석을 시작하세요`
                  : "서류를 업로드하고 OCR 분석을 시작하세요"}
              </span>
            </div>
            <div className="flex items-center gap-3">
              <Button variant="primary" size="lg"
                icon={<Play size={18} />}
                onClick={handleStartPipeline}
                disabled={!parsedData}>
                검역 분석 시작
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
