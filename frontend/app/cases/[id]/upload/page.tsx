"use client";

import { useCallback, useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import {
  ArrowRight,
  Save,
  Loader2,
  Play,
  RefreshCw,
  AlertTriangle,
  Package,
} from "lucide-react";
import StepNavigation from "@/components/layout/StepNavigation";
import DocumentUploadGrid from "@/components/upload/DocumentUploadGrid";
import LabelImageCard from "@/components/upload/LabelImageCard";
import OcrResultEditor from "@/components/ocr/OcrResultEditor";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
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
  type LabelImageData,
} from "@/lib/api";
import type { UploadedFile } from "@/components/upload/FileDropzone";

interface ParsedData {
  basic_info: {
    product_name: string;
    export_country: string;
    is_first_import: boolean;
    is_organic: boolean;
    is_oem: boolean;
  };
  ingredients: Array<{
    id: string;
    name: string;
    ratio: string;
    origin: string;
    ins_number: string;
    cas_number: string;
  }>;
  process_info: {
    process_codes: string[];
    raw_process_text: string;
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

export default function UploadPage() {
  const router = useRouter();
  const params = useParams();
  const caseId = params?.id as string;

  // ── 검역건 정보 ──
  const [caseName, setCaseName] = useState<string>("");

  // ── 업로드 상태 ──
  // uploadedFiles: doc_type → 대표 doc_id (파싱 버튼 활성화 체크용)
  const [uploadedFiles, setUploadedFiles] = useState<Record<string, string>>({});
  // restoredFileNames: doc_type → 파일 객체 배열 (id + name, 삭제/표시용)
  const [restoredFileNames, setRestoredFileNames] = useState<Record<string, UploadedFile[]>>({});
  const [uploading, setUploading] = useState<Record<string, boolean>>({});
  const [uploadErrors, setUploadErrors] = useState<Record<string, string>>({});

  // ── 파싱 상태 ──
  const [parsing, setParsing] = useState(false);
  const [parsedData, setParsedData] = useState<ParsedData | null>(null);
  const [parseStatus, setParseStatus] = useState<
    "idle" | "parsing" | "done" | "error"
  >("idle");
  const [parseError, setParseError] = useState<string>("");
  const [extractionErrors, setExtractionErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  // ── 제목 편집 ──
  const [savingName, setSavingName] = useState(false);

  // ── 라벨 이미지 (Vision 추출 결과) ──
  const [labelImages, setLabelImages] = useState<LabelImageData[]>([]);
  const [labelImagesLoading, setLabelImagesLoading] = useState(false);

  // ── 재분석 추적 ──
  const [newUploadsSinceParse, setNewUploadsSinceParse] = useState(0);

  // ── 초기 로딩 ──
  const [initialLoading, setInitialLoading] = useState(true);

  // ─────────────────────────────────────────────
  // 페이지 진입 시: 기존 데이터 복원
  // ─────────────────────────────────────────────
  useEffect(() => {
    if (!caseId) return;

    const loadExistingData = async () => {
      try {
        // 1) 검역건 정보 로드
        const caseData = await getCase(caseId);
        setCaseName(caseData.product_name || "");

        // 2) 업로드된 문서 목록 복원
        const docsData = await listDocuments(caseId);
        if (docsData.documents && docsData.documents.length > 0) {
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

        // 3) 파싱 결과 복원
        try {
          const parsedRes = await getParsedResult(caseId);
          if (parsedRes.parsed_result) {
            setParsedData(parsedRes.parsed_result);
            setParseStatus("done");
          }
        } catch {
          // 파싱 결과 없으면 무시
        }

        // 4) 기존 라벨 이미지 복원
        try {
          const imgs = await getLabelImages(caseId);
          if (imgs.length > 0) setLabelImages(imgs);
        } catch {
          // 라벨 이미지 없으면 무시
        }
      } catch (e) {
        console.error("[Init] 기존 데이터 로드 실패:", e);
      } finally {
        setInitialLoading(false);
      }
    };

    loadExistingData();
  }, [caseId]);

  // ─────────────────────────────────────────────
  // 파일 업로드 핸들러
  // ─────────────────────────────────────────────
  const handleFileSelect = useCallback(
    async (docType: string, file: File) => {
      setUploading((prev) => ({ ...prev, [docType]: true }));
      setUploadErrors((prev) => {
        const next = { ...prev };
        delete next[docType];
        return next;
      });
      try {
        const result = await uploadDocument(caseId, file, docType);
        setUploadedFiles((prev) => ({ ...prev, [docType]: result.doc_id }));
        setRestoredFileNames((prev) => ({
          ...prev,
          [docType]: [...(prev[docType] || []), { id: result.doc_id, name: file.name }],
        }));
        console.log(`[Upload] ${docType} 업로드 완료: ${result.doc_id}`);

        // 라벨 파일이면 Vision 처리 완료 대기 후 이미지 로드 (폴링)
        if (docType === "label") {
          setLabelImagesLoading(true);
          // 백그라운드 처리 완료 대기: 최대 8회 × 2초 = 16초
          let attempts = 0;
          const poll = async () => {
            try {
              const imgs = await getLabelImages(caseId);
              if (imgs.length > 0) {
                setLabelImages(imgs);
                setLabelImagesLoading(false);
                return;
              }
            } catch {
              // 무시
            }
            attempts++;
            if (attempts < 8) {
              setTimeout(poll, 2000);
            } else {
              setLabelImagesLoading(false);
            }
          };
          setTimeout(poll, 2000); // 첫 시도는 2초 후
        }

        // 이미 파싱 완료 상태에서 새 파일 업로드 → 재분석 필요
        if (parseStatus === "done") {
          setNewUploadsSinceParse((prev) => prev + 1);
        }
      } catch (e: any) {
        const msg = e?.message || "업로드 실패";
        console.error(`[Upload] ${docType} 업로드 실패:`, msg);
        setUploadErrors((prev) => ({ ...prev, [docType]: msg }));
        throw e;
      } finally {
        setUploading((prev) => ({ ...prev, [docType]: false }));
      }
    },
    [caseId, parseStatus]
  );

  // ─────────────────────────────────────────────
  // 파일 삭제 핸들러
  // ─────────────────────────────────────────────
  const handleFileDelete = useCallback(
    async (docId: string) => {
      try {
        await deleteDocument(docId);

        // 로컬 상태에서 해당 doc_id 제거
        setRestoredFileNames((prev) => {
          const next: Record<string, UploadedFile[]> = {};
          for (const [docType, files] of Object.entries(prev)) {
            const filtered = files.filter((f) => f.id !== docId);
            if (filtered.length > 0) next[docType] = filtered;
          }
          return next;
        });

        setUploadedFiles((prev) => {
          const next = { ...prev };
          for (const [docType, id] of Object.entries(next)) {
            if (id === docId) delete next[docType];
          }
          return next;
        });

        // 파싱 완료 상태였다면 재분석 필요 플래그
        if (parseStatus === "done") {
          setNewUploadsSinceParse((n) => n + 1);
        }

        console.log(`[Delete] ${docId} 삭제 완료`);
      } catch (e: any) {
        console.error(`[Delete] ${docId} 삭제 실패:`, e);
        alert(`파일 삭제 실패: ${e?.message || "알 수 없는 오류"}`);
      }
    },
    [parseStatus]
  );

  // ─────────────────────────────────────────────
  // OCR 파싱 실행
  // ─────────────────────────────────────────────
  const handleParse = useCallback(async () => {
    setParsing(true);
    setParseStatus("parsing");
    setParseError("");
    setExtractionErrors([]);
    try {
      const result = await parseDocuments(caseId);
      console.log("[Parse] 응답:", JSON.stringify(result).slice(0, 200));
      if (result.status === "completed" && result.parsed_result) {
        setParsedData(result.parsed_result);
        setParseStatus("done");
        setNewUploadsSinceParse(0);
        // OCR 실패 파일 목록 저장
        if (result.extraction_errors && result.extraction_errors.length > 0) {
          setExtractionErrors(result.extraction_errors);
          console.log("[Parse] OCR 실패 파일:", result.extraction_errors);
        }
      } else {
        setParseStatus("error");
        setParseError(result.error_message || "파싱 결과가 비어있습니다.");
      }
    } catch (e: any) {
      console.error("[Parse] 파싱 실패:", e);
      setParseStatus("error");
      setParseError(e?.message || "서버에 연결할 수 없습니다.");
    } finally {
      setParsing(false);
    }
  }, [caseId]);

  // ─────────────────────────────────────────────
  // 임시 저장
  // ─────────────────────────────────────────────
  const handleSaveDraft = useCallback(async () => {
    if (!parsedData) return;
    setSaving(true);
    try {
      await saveParsedResult(caseId, parsedData);
      console.log("[Save] 임시 저장 완료");
    } catch (e) {
      console.error("[Save] 저장 실패:", e);
    } finally {
      setSaving(false);
    }
  }, [caseId, parsedData]);

  // ─────────────────────────────────────────────
  // 다음 단계로 이동
  // ─────────────────────────────────────────────
  const handleSubmit = useCallback(async () => {
    if (parsedData) {
      try {
        await saveParsedResult(caseId, parsedData);
      } catch (e) {
        console.error("[Save] 저장 실패:", e);
      }
    }
    router.push(`/cases/${caseId}/f1`);
  }, [router, caseId, parsedData]);

  // ─────────────────────────────────────────────
  // 파싱 데이터 변경 핸들러
  // ─────────────────────────────────────────────
  const handleParsedDataChange = useCallback((updated: ParsedData) => {
    setParsedData(updated);
  }, []);

  // ─────────────────────────────────────────────
  // 제품명 저장 (blur 시 자동 저장)
  // ─────────────────────────────────────────────
  const handleCaseNameSave = useCallback(async () => {
    if (!caseName.trim()) return;
    setSavingName(true);
    try {
      await updateCase(caseId, { product_name: caseName.trim() });
      console.log("[CaseName] 제품명 저장:", caseName.trim());
    } catch (e) {
      console.error("[CaseName] 저장 실패:", e);
    } finally {
      setSavingName(false);
    }
  }, [caseId, caseName]);

  const uploadedCount = Object.keys(uploadedFiles).length;
  const hasErrors = Object.keys(uploadErrors).length > 0;

  // 버튼 상태 결정
  const showParseButton = uploadedCount > 0 && parseStatus !== "done";
  // 파싱 완료 후에는 항상 재분석 가능 (파일 추가/삭제 여부 무관)
  const showReParseButton = parseStatus === "done" && uploadedCount > 0;

  // 로딩 중
  if (initialLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="flex flex-col items-center gap-3">
          <Loader2 size={32} className="animate-spin text-blue-500" />
          <span className="text-sm text-slate-500">데이터 불러오는 중...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-[1440px] mx-auto px-6 py-6 pb-28">
      {/* 상단: Step Navigation */}
      <StepNavigation currentStep="upload" />

      {/* 검역건 제목 입력 */}
      <div className="mt-4 mb-2 flex items-center gap-3">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-slate-100 shrink-0">
          <Package size={16} className="text-slate-500" />
        </div>
        <div className="flex-1">
          <label className="text-xs text-slate-400 mb-1 block">검역건 제품명</label>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={caseName}
              onChange={(e) => setCaseName(e.target.value)}
              onBlur={handleCaseNameSave}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.currentTarget.blur();
                }
              }}
              placeholder="예: FJ 캡 프론티어 위스키"
              className="flex-1 text-lg font-bold text-slate-900 bg-transparent border-b-2 border-transparent hover:border-slate-200 focus:border-blue-500 focus:outline-none transition-colors py-0.5 placeholder:text-slate-300 placeholder:font-normal"
            />
            {savingName && (
              <Loader2 size={14} className="animate-spin text-slate-400 shrink-0" />
            )}
          </div>
        </div>
      </div>

      {/* 본문: 좌우 분할 */}
      <div
        className="mt-4 flex gap-6 items-start"
        style={{ minHeight: "calc(100vh - 280px)" }}
      >
        {/* 좌측: 서류 업로드 (37%) */}
        <div className="w-[37%] shrink-0 flex flex-col gap-4">
          {/* 파일 업로드 카드 */}
          <Card padding="lg">
            <DocumentUploadGrid
              onFileSelect={handleFileSelect}
              restoredFiles={restoredFileNames}
              onFileDelete={handleFileDelete}
            />
          </Card>

          {/* 업로드 에러 표시 */}
          {hasErrors && (
            <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3">
              <div className="flex items-center gap-2 mb-1">
                <AlertTriangle size={14} className="text-red-500" />
                <span className="text-xs font-semibold text-red-600">
                  업로드 오류
                </span>
              </div>
              {Object.entries(uploadErrors).map(([docType, msg]) => (
                <p key={docType} className="text-xs text-red-500 ml-5">
                  {docType}: {msg}
                </p>
              ))}
            </div>
          )}

          {/* 라벨 이미지 추출 결과 카드 */}
          {(labelImagesLoading || labelImages.length > 0) && (
            <LabelImageCard
              caseId={caseId}
              images={labelImages}
              loading={labelImagesLoading}
            />
          )}

          {/* OCR 분석 시작 버튼 (좌측 패널) */}
          {showParseButton && (
            <Button
              variant="primary"
              size="lg"
              icon={
                parsing ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Play size={16} />
                )
              }
              onClick={handleParse}
              disabled={parsing}
              className="w-full"
            >
              {parsing
                ? "AI 분석 중..."
                : `OCR 분석 시작 (${uploadedCount}개 파일)`}
            </Button>
          )}

          {/* 재분석 버튼 — 파싱 완료 후 새 파일 업로드 시 */}
          {showReParseButton && (
            <Button
              variant="primary"
              size="lg"
              icon={
                parsing ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <RefreshCw size={16} />
                )
              }
              onClick={handleParse}
              disabled={parsing}
              className="w-full"
            >
              {parsing
                ? "AI 재분석 중..."
                : newUploadsSinceParse > 0
                ? `재분석 (${newUploadsSinceParse}개 파일 변경됨)`
                : "재분석"}
            </Button>
          )}

          {/* 파싱 에러 표시 */}
          {parseStatus === "error" && parseError && (
            <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3">
              <div className="flex items-center gap-2 mb-1">
                <AlertTriangle size={14} className="text-red-500" />
                <span className="text-xs font-semibold text-red-600">
                  분석 실패
                </span>
              </div>
              <p className="text-xs text-red-500 ml-5">{parseError}</p>
              <button
                onClick={handleParse}
                className="mt-2 ml-5 text-xs font-medium text-red-600 hover:text-red-800 underline"
              >
                다시 시도
              </button>
            </div>
          )}
        </div>

        {/* 우측: OCR 결과 편집 (63%) */}
        <div className="flex-1 flex flex-col min-w-0">
          <OcrResultEditor
            parsedData={parsedData}
            parseStatus={parseStatus}
            caseId={caseId}
            onDataChange={handleParsedDataChange}
            extractionErrors={extractionErrors}
            externalLabelImages={labelImages.length > 0 ? labelImages : undefined}
            externalLabelImagesLoading={labelImagesLoading}
          />
        </div>
      </div>

      {/* 하단 고정 액션바 */}
      <div className="fixed bottom-0 left-0 right-0 z-50">
        <div className="max-w-[1440px] mx-auto px-6">
          <div className="bg-white/80 backdrop-blur-xl border-t border-slate-200/60 rounded-t-2xl shadow-lg shadow-slate-900/5 px-8 py-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div
                className={`w-2 h-2 rounded-full ${
                  parseStatus === "done"
                    ? "bg-emerald-400 animate-pulse"
                    : parseStatus === "parsing"
                    ? "bg-blue-400 animate-pulse"
                    : parseStatus === "error"
                    ? "bg-red-400"
                    : "bg-slate-300"
                }`}
              />
              <span className="text-sm text-slate-500">
                {parseStatus === "done" && newUploadsSinceParse > 0
                  ? `${newUploadsSinceParse}개 새 파일 추가됨 · 재분석을 시작하세요`
                  : parseStatus === "done"
                  ? "OCR 분석 완료 · 수정사항을 확인해주세요"
                  : parseStatus === "parsing"
                  ? "AI 분석 진행 중..."
                  : parseStatus === "error"
                  ? "분석 실패 · 파일을 확인해주세요"
                  : uploadedCount > 0
                  ? `${uploadedCount}개 파일 업로드됨 · OCR 분석을 시작하세요`
                  : "서류를 업로드하고 OCR 분석을 시작하세요"}
              </span>
            </div>
            <div className="flex items-center gap-3">
              {/* OCR 분석 / 재분석 버튼 (하단바) */}
              {(showParseButton || showReParseButton) && (
                <Button
                  variant="primary"
                  size="lg"
                  icon={
                    parsing ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : showReParseButton ? (
                      <RefreshCw size={16} />
                    ) : (
                      <Play size={16} />
                    )
                  }
                  onClick={handleParse}
                  disabled={parsing}
                  className="shadow-lg shadow-emerald-600/20"
                >
                  {parsing
                    ? "AI 분석 중..."
                    : showReParseButton
                    ? "재분석"
                    : `OCR 분석 시작 (${uploadedCount}개)`}
                </Button>
              )}
              <Button
                variant="secondary"
                size="md"
                icon={
                  saving ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Save size={16} />
                  )
                }
                onClick={handleSaveDraft}
                disabled={!parsedData || saving}
              >
                임시 저장
              </Button>
              <Button
                variant="primary"
                size="lg"
                icon={<ArrowRight size={18} />}
                onClick={handleSubmit}
                className="shadow-lg shadow-blue-600/20"
                disabled={!parsedData}
              >
                F1 수입판정으로 이동
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
