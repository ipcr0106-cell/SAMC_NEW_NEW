"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { ScanSearch, FileText, FileDown, Loader2, AlertTriangle } from "lucide-react";
import BasicInfoCard from "./BasicInfoCard";
import IngredientTable, { Ingredient } from "./IngredientTable";
import ProcessCodeCard, { type ProcessCodeCandidate } from "./ProcessCodeCard";
import LabelInfoCard from "./LabelInfoCard";
import LabelImageCard from "@/components/upload/LabelImageCard";
import Badge from "@/components/ui/Badge";
import { downloadParsedResultFile, getLabelImages, type LabelImageData } from "@/lib/api";

interface ProcessCodeReason {
  code: string;
  reason: string;
}

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
    process_code_reasons?: ProcessCodeReason[];
    process_code_candidates?: ProcessCodeCandidate[];
    raw_process_text: string;
  };
  label_info?: {
    export_country: string;
    is_oem: boolean;
    label_texts: string[];
    design_description: string;
    warnings: string[];
  };
  /** 선택된 라벨 이미지 ID 목록 (내보내기·F4에 사용) */
  selected_label_image_ids?: string[];
}

interface OcrResultEditorProps {
  parsedData?: ParsedData | null;
  parseStatus?: "idle" | "parsing" | "done" | "error";
  onDataChange?: (data: ParsedData) => void;
  /** 문서 다운로드용 case_id (있으면 DOCX/PDF 다운로드 버튼 표시) */
  caseId?: string;
  /** OCR 텍스트 추출에 실패한 파일 목록 */
  extractionErrors?: string[];
  /** 부모(업로드 페이지)에서 이미 로드한 라벨 이미지를 내려줌.
   *  제공 시 내부 fetch를 생략하고 이 값을 그대로 사용. */
  externalLabelImages?: LabelImageData[];
  externalLabelImagesLoading?: boolean;
}

export default function OcrResultEditor({
  parsedData,
  parseStatus = "idle",
  onDataChange,
  caseId,
  extractionErrors,
  externalLabelImages,
  externalLabelImagesLoading,
}: OcrResultEditorProps) {
  const [exporting, setExporting] = useState<"docx" | "pdf" | null>(null);

  // 라벨 이미지: external prop이 있으면 우선 사용, 없으면 내부 fetch
  const [internalLabelImages, setInternalLabelImages] = useState<LabelImageData[]>([]);
  const [internalLabelImagesLoading, setInternalLabelImagesLoading] = useState(false);
  const labelImages = externalLabelImages ?? internalLabelImages;
  const labelImagesLoading = externalLabelImagesLoading ?? internalLabelImagesLoading;

  // 선택된 라벨 이미지 ID (내보내기·F4에 사용)
  const [selectedLabelImageIds, setSelectedLabelImageIds] = useState<string[]>([]);

  const handleExport = useCallback(
    async (format: "docx" | "pdf") => {
      if (!caseId) return;
      setExporting(format);
      try {
        await downloadParsedResultFile(caseId, format, selectedLabelImageIds);
      } catch (err) {
        alert(
          `${format.toUpperCase()} 다운로드 실패: ${
            err instanceof Error ? err.message : String(err)
          }`
        );
      } finally {
        setExporting(null);
      }
    },
    [caseId, selectedLabelImageIds]
  );

  // external 이미지가 바뀌면 선택 상태 동기화
  useEffect(() => {
    if (!externalLabelImages || externalLabelImages.length === 0) return;
    setSelectedLabelImageIds((prev) => {
      const currentIdSet = new Set(externalLabelImages.map((img) => img.id));
      const validPrev = prev.filter((id) => currentIdSet.has(id));
      return validPrev.length > 0 ? validPrev : externalLabelImages.map((img) => img.id);
    });
  }, [externalLabelImages]);

  // external이 없을 때만 내부 fetch + 폴링
  // - 이미지가 1개라도 생기면 즉시 표시하되, 백그라운드에서 4회 더 재조회
  useEffect(() => {
    if (externalLabelImages) return; // 부모가 이미지를 내려주면 skip
    if (parseStatus !== "done" || !caseId) return;
    let cancelled = false;

    const fetchImages = async (attempts = 0) => {
      try {
        if (attempts === 0) setInternalLabelImagesLoading(true);
        const imgs = await getLabelImages(caseId);
        if (cancelled) return;

        if (imgs.length > 0) {
          setInternalLabelImages(imgs);
          setInternalLabelImagesLoading(false);

          // stale ID 제거, 현재 이미지와 겹치는 선택 없으면 전체 선택 초기화
          setSelectedLabelImageIds((prev) => {
            const currentIdSet = new Set(imgs.map((img) => img.id));
            const validPrev = prev.filter((id) => currentIdSet.has(id));
            return validPrev.length > 0 ? validPrev : imgs.map((img) => img.id);
          });

          // 첫 4회는 계속 재조회해서 뒤늦게 완성되는 이미지도 반영 (silent)
          if (attempts < 4) {
            setTimeout(() => fetchImages(attempts + 1), 2000);
          }
        } else if (attempts < 6) {
          setTimeout(() => fetchImages(attempts + 1), 2000);
        } else {
          setInternalLabelImagesLoading(false);
        }
      } catch {
        if (!cancelled) setInternalLabelImagesLoading(false);
      }
    };

    fetchImages();
    return () => { cancelled = true; };
  }, [parseStatus, caseId, externalLabelImages]);

  // 기본 정보
  const [basicInfo, setBasicInfo] = useState({
    productName: "",
    isFirstImport: false,
    isOrganic: false,
  });

  // 원재료 목록
  const [ingredients, setIngredients] = useState<Ingredient[]>([]);

  // 공정 코드
  const [processCodes, setProcessCodes] = useState<string[]>([]);
  const [processCodeReasons, setProcessCodeReasons] = useState<ProcessCodeReason[]>([]);
  const [processCodeCandidates, setProcessCodeCandidates] = useState<ProcessCodeCandidate[]>([]);
  const [rawProcessText, setRawProcessText] = useState("");

  // 수출국/OEM
  const [exportCountry, setExportCountry] = useState("");
  const [isOem, setIsOem] = useState(false);

  // 라벨 정보
  const [labelTexts, setLabelTexts] = useState<string[]>([]);
  const [designDescription, setDesignDescription] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);

  // 피드백 루프 방지용 플래그:
  // 우리가 직접 onDataChange를 호출할 때 parsedData useEffect가 재실행되는 것을 막음
  const suppressSyncRef = useRef(false);

  // parsedData가 변경되면 로컬 상태에 반영
  // (단, 우리가 직접 onDataChange를 호출해 발생한 변경이면 건너뜀)
  useEffect(() => {
    if (!parsedData) return;
    if (suppressSyncRef.current) {
      suppressSyncRef.current = false;
      return;
    }

    setBasicInfo({
      productName: parsedData.basic_info.product_name || "",
      isFirstImport: parsedData.basic_info.is_first_import || false,
      isOrganic: parsedData.basic_info.is_organic || false,
    });

    setIngredients(
      parsedData.ingredients.map((ing) => ({
        id: ing.id,
        name: ing.name,
        ratio: ing.ratio,
        origin: ing.origin,
        insNumber: ing.ins_number,
        casNumber: ing.cas_number,
      }))
    );

    setProcessCodes(parsedData.process_info.process_codes || []);
    setProcessCodeReasons(parsedData.process_info.process_code_reasons || []);
    setProcessCodeCandidates(parsedData.process_info.process_code_candidates || []);
    setRawProcessText(parsedData.process_info.raw_process_text || "");

    // label_info가 있으면 그쪽 값 사용, 없으면 basic_info에서 가져옴
    const li = parsedData.label_info;
    setExportCountry(li?.export_country || parsedData.basic_info.export_country || "");
    setIsOem(li?.is_oem ?? parsedData.basic_info.is_oem ?? false);
    setLabelTexts(li?.label_texts || []);
    setDesignDescription(li?.design_description || "");
    setWarnings(li?.warnings || []);
    // 저장된 이미지 선택 복원 (이미지가 이미 로드된 경우에만 덮어씀)
    if (parsedData.selected_label_image_ids !== undefined) {
      setSelectedLabelImageIds(parsedData.selected_label_image_ids);
    }
  }, [parsedData]);

  // 부모에게 알리는 헬퍼 — 각 핸들러가 변경된 값을 직접 넘겨 stale closure 방지
  const notifyParent = useCallback((overrides: {
    basicInfo?: typeof basicInfo;
    ingredients?: Ingredient[];
    processCodes?: string[];
    exportCountry?: string;
    isOem?: boolean;
    labelTexts?: string[];
    designDescription?: string;
    warnings?: string[];
    selectedLabelImageIds?: string[];
  }) => {
    if (!onDataChange) return;
    const bi = overrides.basicInfo ?? basicInfo;
    const ing = overrides.ingredients ?? ingredients;
    const codes = overrides.processCodes ?? processCodes;
    const country = overrides.exportCountry ?? exportCountry;
    const oem = overrides.isOem ?? isOem;
    const lt = overrides.labelTexts ?? labelTexts;
    const dd = overrides.designDescription ?? designDescription;
    const w = overrides.warnings ?? warnings;
    const selIds = overrides.selectedLabelImageIds ?? selectedLabelImageIds;

    suppressSyncRef.current = true;
    onDataChange({
      basic_info: {
        product_name: bi.productName,
        export_country: country,
        is_first_import: bi.isFirstImport,
        is_organic: bi.isOrganic,
        is_oem: oem,
      },
      ingredients: ing.map((item) => ({
        id: item.id,
        name: item.name,
        ratio: item.ratio,
        origin: item.origin,
        ins_number: item.insNumber || "",
        cas_number: item.casNumber || "",
      })),
      process_info: {
        process_codes: codes,
        raw_process_text: rawProcessText,
      },
      label_info: {
        export_country: country,
        is_oem: oem,
        label_texts: lt,
        design_description: dd,
        warnings: w,
      },
      selected_label_image_ids: selIds,
    });
  }, [basicInfo, ingredients, processCodes, exportCountry, isOem, labelTexts, designDescription, warnings, rawProcessText, selectedLabelImageIds, onDataChange]);

  // 라벨 이미지 선택 핸들러
  const handleLabelImageSelectionChange = useCallback(
    (ids: string[]) => {
      setSelectedLabelImageIds(ids);
      notifyParent({ selectedLabelImageIds: ids });
    },
    [notifyParent]
  );

  // 각 상태 변경 핸들러 — 변경된 값을 notifyParent에 직접 전달
  const handleBasicInfoChange = useCallback(
    (data: typeof basicInfo) => {
      setBasicInfo(data);
      notifyParent({ basicInfo: data });
    },
    [notifyParent]
  );

  const handleIngredientsChange = useCallback(
    (data: Ingredient[]) => {
      setIngredients(data);
      notifyParent({ ingredients: data });
    },
    [notifyParent]
  );

  const handleProcessCodesChange = useCallback(
    (codes: string[]) => {
      setProcessCodes(codes);
      notifyParent({ processCodes: codes });
    },
    [notifyParent]
  );

  const handleExportCountryChange = useCallback(
    (country: string) => {
      setExportCountry(country);
      notifyParent({ exportCountry: country });
    },
    [notifyParent]
  );

  const handleOemChange = useCallback(
    (oem: boolean) => {
      setIsOem(oem);
      notifyParent({ isOem: oem });
    },
    [notifyParent]
  );

  const handleLabelTextsChange = useCallback(
    (texts: string[]) => {
      setLabelTexts(texts);
      notifyParent({ labelTexts: texts });
    },
    [notifyParent]
  );

  const handleDesignDescriptionChange = useCallback(
    (desc: string) => {
      setDesignDescription(desc);
      notifyParent({ designDescription: desc });
    },
    [notifyParent]
  );

  const handleWarningsChange = useCallback(
    (w: string[]) => {
      setWarnings(w);
      notifyParent({ warnings: w });
    },
    [notifyParent]
  );

  const statusBadge = {
    idle: { variant: "slate" as const, text: "분석 대기" },
    parsing: { variant: "blue" as const, text: "분석 중..." },
    done: { variant: "green" as const, text: "분석 완료" },
    error: { variant: "red" as const, text: "분석 실패" },
  }[parseStatus];

  return (
    <div className="flex flex-col h-full">
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2.5">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600">
            <ScanSearch size={16} />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-900">
              OCR 분석 결과
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              AI가 추출한 데이터를 확인하고 수정하세요
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {parseStatus === "done" && caseId && (
            <>
              <button
                type="button"
                disabled={exporting !== null}
                onClick={() => handleExport("docx")}
                title="Word 문서(.docx)로 다운로드"
                className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs font-medium bg-white border border-slate-200 text-slate-700 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {exporting === "docx" ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <FileText size={12} />
                )}
                <span>DOCX</span>
              </button>
              <button
                type="button"
                disabled={exporting !== null}
                onClick={() => handleExport("pdf")}
                title="PDF로 다운로드"
                className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs font-medium bg-white border border-slate-200 text-slate-700 hover:bg-red-50 hover:border-red-300 hover:text-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {exporting === "pdf" ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <FileDown size={12} />
                )}
                <span>PDF</span>
              </button>
            </>
          )}
          <Badge variant={statusBadge.variant} size="md">
            {statusBadge.text}
          </Badge>
        </div>
      </div>

      {/* 파싱 진행 중 */}
      {parseStatus === "parsing" && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="animate-spin w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full mx-auto mb-4" />
            <p className="text-sm font-medium text-slate-600">AI가 서류를 분석하고 있습니다...</p>
            <p className="text-xs text-slate-400 mt-1">OCR 추출 → 성분 파싱 → 공정 코드 변환</p>
          </div>
        </div>
      )}

      {/* 대기 상태 */}
      {parseStatus === "idle" && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="w-12 h-12 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <ScanSearch size={24} className="text-slate-400" />
            </div>
            <p className="text-sm font-medium text-slate-600">서류를 업로드한 후 OCR 분석을 시작하세요</p>
            <p className="text-xs text-slate-400 mt-1">업로드된 서류에서 성분, 공정, 라벨 정보를 자동 추출합니다</p>
          </div>
        </div>
      )}

      {/* 에러 상태 */}
      {parseStatus === "error" && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <p className="text-sm font-medium text-red-600">분석에 실패했습니다</p>
            <p className="text-xs text-slate-400 mt-1">파일 형식을 확인하고 다시 시도해주세요</p>
          </div>
        </div>
      )}

      {/* 분석 완료: 카드 스택 */}
      {parseStatus === "done" && (
        <div className="space-y-4 flex-1 overflow-y-auto pr-1 pb-4 scrollbar-thin">
          {/* OCR 실패 파일 경고 */}
          {extractionErrors && extractionErrors.length > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
              <div className="flex items-center gap-2 mb-2">
                <AlertTriangle size={14} className="text-amber-500 shrink-0" />
                <span className="text-xs font-semibold text-amber-700">
                  일부 파일이 분석에서 제외되었습니다 ({extractionErrors.length}개)
                </span>
              </div>
              <ul className="space-y-0.5 pl-5">
                {extractionErrors.map((err, i) => (
                  <li key={i} className="text-xs text-amber-600 list-disc">
                    {err}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <BasicInfoCard data={basicInfo} onChange={handleBasicInfoChange} />

          <IngredientTable
            ingredients={ingredients}
            onChange={handleIngredientsChange}
          />

          <ProcessCodeCard
            processCodes={processCodes}
            onProcessCodesChange={handleProcessCodesChange}
            exportCountry={exportCountry}
            onExportCountryChange={handleExportCountryChange}
            isOem={isOem}
            onOemChange={handleOemChange}
            rawProcessText={rawProcessText || undefined}
            processCodeReasons={processCodeReasons.length > 0 ? processCodeReasons : undefined}
            processCodeCandidates={processCodeCandidates.length > 0 ? processCodeCandidates : undefined}
          />

          <LabelInfoCard
            labelTexts={labelTexts}
            onLabelTextsChange={handleLabelTextsChange}
            designDescription={designDescription}
            onDesignDescriptionChange={handleDesignDescriptionChange}
            warnings={warnings}
            onWarningsChange={handleWarningsChange}
          />

          {/* 라벨 제품 이미지 (Vision 자동 추출 + 선택) */}
          {caseId && (labelImagesLoading || labelImages.length > 0) && (
            <LabelImageCard
              caseId={caseId}
              images={labelImages}
              loading={labelImagesLoading}
              selectable
              selectedIds={selectedLabelImageIds}
              onSelectionChange={handleLabelImageSelectionChange}
            />
          )}
        </div>
      )}
    </div>
  );
}
