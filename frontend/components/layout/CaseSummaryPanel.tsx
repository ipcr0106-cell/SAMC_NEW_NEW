"use client";

/**
 * CaseSummaryPanel
 * F1~F5 단계 오른쪽 사이드바에 공통으로 표시되는 "케이스 요약" 패널.
 * - OCR 파싱 결과 핵심 정보 (제품명, 수출국, 성분 수, 공정 코드)
 * - Vision AI 추출 라벨 이미지 + 6개 텍스트 필드
 */

import { useEffect, useState } from "react";
import {
  Package,
  Globe2,
  FlaskConical,
  Cog,
  ImageIcon,
  Loader2,
  ChevronDown,
  ChevronUp,
  FileText,
} from "lucide-react";
import { getParsedResult, getLabelImages, type LabelImageData } from "@/lib/api";

interface CaseSummaryPanelProps {
  caseId: string;
}

interface ParsedSummary {
  product_name: string;
  export_country: string;
  ingredient_count: number;
  process_codes: string[];
}

const FIELD_LABELS = [
  { key: "label_product_name",   label: "제품명" },
  { key: "label_ingredients",    label: "원재료" },
  { key: "label_content_volume", label: "내용량" },
  { key: "label_origin",         label: "원산지" },
  { key: "label_manufacturer",   label: "제조사" },
  { key: "label_case_number",    label: "케이스 넘버" },
] as const;

function LabelImageThumb({ img }: { img: LabelImageData }) {
  const [open, setOpen] = useState(true);
  const [imgError, setImgError] = useState(false);
  const url = img.signed_url;
  const hasText = FIELD_LABELS.some(({ key }) => img[key]);

  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((p) => !p)}
        className="w-full flex items-center justify-between px-3 py-2 bg-slate-50 hover:bg-slate-100 transition-colors"
      >
        <span className="text-[11px] font-semibold text-slate-500">
          {img.label_product_name || "제품 이미지"}
        </span>
        {open ? <ChevronUp size={12} className="text-slate-400" /> : <ChevronDown size={12} className="text-slate-400" />}
      </button>

      {open && (
        <div className="p-3 flex gap-3">
          {/* 썸네일 */}
          <div className="shrink-0 w-[80px] h-[80px] bg-slate-100 rounded-lg overflow-hidden flex items-center justify-center border border-slate-200">
            {url && !imgError ? (
              <img
                src={url}
                alt=""
                className="w-full h-full object-contain"
                onError={() => setImgError(true)}
              />
            ) : (
              <ImageIcon size={18} className="text-slate-400" />
            )}
          </div>

          {/* 텍스트 */}
          <div className="flex-1 min-w-0 space-y-1">
            {hasText ? (
              FIELD_LABELS.map(({ key, label }) => {
                const val = img[key] as string | null | undefined;
                if (!val) return null;
                return (
                  <div key={key} className="flex gap-1.5 items-start">
                    <span className="text-[9px] font-bold text-slate-400 w-[48px] shrink-0 pt-0.5 uppercase">
                      {label}
                    </span>
                    <span className="text-[10px] text-slate-600 leading-snug break-all">
                      {val}
                    </span>
                  </div>
                );
              })
            ) : (
              <p className="text-[10px] text-slate-400">추출 정보 없음</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function CaseSummaryPanel({ caseId }: CaseSummaryPanelProps) {
  const [summary, setSummary] = useState<ParsedSummary | null>(null);
  const [labelImages, setLabelImages] = useState<LabelImageData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;

    const load = async () => {
      try {
        const [parsedRes, imgs] = await Promise.allSettled([
          getParsedResult(caseId),
          getLabelImages(caseId),
        ]);

        if (!cancelled) {
          if (parsedRes.status === "fulfilled" && parsedRes.value?.parsed_result) {
            const pr = parsedRes.value.parsed_result;
            setSummary({
              product_name: pr.basic_info?.product_name || "",
              export_country: pr.basic_info?.export_country || "",
              ingredient_count: pr.ingredients?.length || 0,
              process_codes: pr.process_info?.process_codes || [],
            });
          }
          if (imgs.status === "fulfilled") {
            setLabelImages(imgs.value || []);
          }
          setLoading(false);
        }
      } catch {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => { cancelled = true; };
  }, [caseId]);

  return (
    <div className="space-y-4">
      {/* OCR 파싱 요약 */}
      <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-7 h-7 bg-emerald-50 rounded-lg flex items-center justify-center">
            <FileText size={13} className="text-emerald-600" />
          </div>
          <h3 className="text-sm font-bold text-slate-900">OCR 분석 요약</h3>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 py-2 text-slate-400">
            <Loader2 size={13} className="animate-spin" />
            <span className="text-xs">불러오는 중...</span>
          </div>
        ) : !summary ? (
          <p className="text-xs text-slate-400">파싱 데이터가 없습니다.</p>
        ) : (
          <div className="space-y-2">
            {summary.product_name && (
              <div className="flex items-start gap-2">
                <Package size={13} className="text-slate-400 mt-0.5 shrink-0" />
                <div>
                  <p className="text-[10px] text-slate-400">제품명</p>
                  <p className="text-xs font-semibold text-slate-800 leading-tight">{summary.product_name}</p>
                </div>
              </div>
            )}
            {summary.export_country && (
              <div className="flex items-start gap-2">
                <Globe2 size={13} className="text-slate-400 mt-0.5 shrink-0" />
                <div>
                  <p className="text-[10px] text-slate-400">수출국</p>
                  <p className="text-xs font-semibold text-slate-800">{summary.export_country}</p>
                </div>
              </div>
            )}
            {summary.ingredient_count > 0 && (
              <div className="flex items-start gap-2">
                <FlaskConical size={13} className="text-slate-400 mt-0.5 shrink-0" />
                <div>
                  <p className="text-[10px] text-slate-400">원재료</p>
                  <p className="text-xs font-semibold text-slate-800">{summary.ingredient_count}개 항목</p>
                </div>
              </div>
            )}
            {summary.process_codes.length > 0 && (
              <div className="flex items-start gap-2">
                <Cog size={13} className="text-slate-400 mt-0.5 shrink-0" />
                <div>
                  <p className="text-[10px] text-slate-400">공정 코드</p>
                  <div className="flex flex-wrap gap-1 mt-0.5">
                    {summary.process_codes.map((c) => (
                      <span key={c} className="text-[10px] font-mono bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded">
                        {c}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 라벨 이미지 */}
      {!loading && labelImages.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-7 h-7 bg-violet-50 rounded-lg flex items-center justify-center">
              <ImageIcon size={13} className="text-violet-500" />
            </div>
            <h3 className="text-sm font-bold text-slate-900">라벨 이미지</h3>
            <span className="ml-auto text-[10px] bg-violet-100 text-violet-600 px-2 py-0.5 rounded-full font-semibold">
              {labelImages.length}개
            </span>
          </div>
          <div className="space-y-2">
            {labelImages.map((img) => (
              <LabelImageThumb key={img.id} img={img} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
