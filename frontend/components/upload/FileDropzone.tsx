"use client";

import { useCallback, useState } from "react";
import {
  FileSpreadsheet,
  Factory,
  FlaskConical,
  Image,
  FolderPlus,
  CheckCircle2,
  X,
  Loader2,
  Plus,
  ExternalLink,
} from "lucide-react";
import Badge from "@/components/ui/Badge";
import { openDocumentInNewTab } from "@/lib/api";

export type DocType = "ingredients" | "process" | "msds" | "label" | "other";

/** 업로드된 파일 한 건 (id + 표시명) */
export interface UploadedFile {
  id: string;
  name: string;
}

interface FileDropzoneProps {
  docType: DocType;
  /** 이미 업로드된 파일 목록 (페이지 재진입 시 복원 + 삭제 ID 포함) */
  restoredFiles?: UploadedFile[];
  onFileSelect: (file: File) => void | Promise<void>;
  /** 개별 파일 삭제 핸들러 */
  onFileDelete?: (docId: string) => void | Promise<void>;
}

const docConfig: Record<
  DocType,
  { title: string; description: string; icon: typeof FileSpreadsheet; accept: string }
> = {
  ingredients: {
    title: "원재료배합비율표",
    description: "PDF, HWP, Excel, 이미지",
    icon: FileSpreadsheet,
    accept: ".pdf,.hwp,.hwpx,.xlsx,.xls,.png,.jpg,.jpeg",
  },
  process: {
    title: "제조공정도",
    description: "PDF, HWP, 이미지",
    icon: Factory,
    accept: ".pdf,.hwp,.hwpx,.png,.jpg,.jpeg",
  },
  msds: {
    title: "MSDS",
    description: "PDF",
    icon: FlaskConical,
    accept: ".pdf",
  },
  label: {
    title: "수출국 라벨 / 표시사항",
    description: "이미지, PDF, Excel",
    icon: Image,
    accept: ".png,.jpg,.jpeg,.webp,.pdf,.xlsx,.xls",
  },
  other: {
    title: "기타 서류",
    description: "PDF, HWP, Excel, 이미지, DOCX",
    icon: FolderPlus,
    accept: ".pdf,.hwp,.hwpx,.xlsx,.xls,.docx,.png,.jpg,.jpeg,.webp",
  },
};

export default function FileDropzone({
  docType,
  restoredFiles = [],
  onFileSelect,
  onFileDelete,
}: FileDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploadingCount, setUploadingCount] = useState(0);
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());
  const [openingIds, setOpeningIds] = useState<Set<string>>(new Set());

  const handleOpenFile = useCallback(async (docId: string) => {
    setOpeningIds((prev) => new Set(prev).add(docId));
    try {
      await openDocumentInNewTab(docId);
    } catch (err) {
      alert(`파일 열기에 실패했습니다: ${err instanceof Error ? err.message : err}`);
    } finally {
      setOpeningIds((prev) => {
        const next = new Set(prev);
        next.delete(docId);
        return next;
      });
    }
  }, []);

  const config = docConfig[docType];
  const Icon = config.icon;

  // 표시할 전체 파일 목록 (controlled — 상위 상태 그대로 사용)
  const allFiles = restoredFiles;
  const hasFiles = allFiles.length > 0;
  const isUploading = uploadingCount > 0;

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      const list = Array.from(files);
      for (const f of list) {
        setUploadingCount((c) => c + 1);
        try {
          await onFileSelect(f);
          // 업로드 성공 시 상위 상태(restoredFileNames)가 갱신되므로 여기서 로컬 추가 X
        } catch {
          // 에러는 상위에서 처리
        } finally {
          setUploadingCount((c) => c - 1);
        }
      }
    },
    [onFileSelect]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      if (e.dataTransfer.files.length > 0) handleFiles(e.dataTransfer.files);
    },
    [handleFiles]
  );

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFiles(e.target.files);
      e.target.value = ""; // 같은 파일 재선택 가능하도록 초기화
    }
  };

  return (
    <div
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      className={`relative rounded-2xl border-2 border-dashed transition-all duration-200 group ${
        isDragging
          ? "border-blue-400 bg-blue-50/50"
          : hasFiles
          ? "border-emerald-200 bg-emerald-50/30"
          : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/50"
      }`}
    >
      <div className="flex flex-col p-4">
        {/* 헤더: 아이콘 + 제목 + 파일 개수 배지 */}
        <div className="flex items-center gap-2.5 mb-2">
          <div
            className={`flex items-center justify-center w-9 h-9 rounded-xl transition-colors ${
              hasFiles
                ? "bg-emerald-100 text-emerald-600"
                : isDragging
                ? "bg-blue-100 text-blue-600"
                : "bg-slate-100 text-slate-400 group-hover:bg-blue-50 group-hover:text-blue-500"
            }`}
          >
            {isUploading ? (
              <Loader2 size={18} className="animate-spin" />
            ) : hasFiles ? (
              <CheckCircle2 size={18} />
            ) : (
              <Icon size={18} />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-semibold text-slate-700">
                {config.title}
              </span>
              {allFiles.length > 0 && (
                <Badge variant="green" size="sm">
                  {allFiles.length}개
                </Badge>
              )}
              {isUploading && (
                <Badge variant="blue" size="sm">
                  업로드 중...
                </Badge>
              )}
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5">{config.description}</p>
          </div>
        </div>

        {/* 파일 목록 or 안내 문구 */}
        {hasFiles ? (
          <div className="flex flex-col gap-1 mt-1 mb-2">
            {allFiles.map((f) => {
              const isDeleting = deletingIds.has(f.id);
              return (
                <div
                  key={f.id}
                  className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white border border-emerald-100 text-xs text-slate-600 group/file"
                >
                  <CheckCircle2 size={12} className="text-emerald-500 shrink-0" />
                  <button
                    type="button"
                    disabled={openingIds.has(f.id)}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      handleOpenFile(f.id);
                    }}
                    title={`"${f.name}" 열기`}
                    className="truncate flex-1 text-left hover:text-blue-600 hover:underline disabled:opacity-50 flex items-center gap-1"
                  >
                    <span className="truncate">{f.name}</span>
                    {openingIds.has(f.id) ? (
                      <Loader2 size={10} className="animate-spin shrink-0" />
                    ) : (
                      <ExternalLink size={10} className="shrink-0 opacity-40" />
                    )}
                  </button>
                  {onFileDelete && (
                    <button
                      type="button"
                      disabled={isDeleting}
                      onClick={async (e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        if (!confirm(`"${f.name}" 파일을 삭제할까요?`)) return;
                        setDeletingIds((prev) => new Set(prev).add(f.id));
                        try {
                          await onFileDelete(f.id);
                        } finally {
                          setDeletingIds((prev) => {
                            const next = new Set(prev);
                            next.delete(f.id);
                            return next;
                          });
                        }
                      }}
                      title="파일 삭제"
                      className="shrink-0 text-slate-300 hover:text-red-500 transition-colors disabled:opacity-50 opacity-0 group-hover/file:opacity-100"
                    >
                      {isDeleting ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <X size={12} />
                      )}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="py-2 text-center">
            <p className="text-xs text-slate-400">
              드래그하여 놓거나 클릭하여 업로드
            </p>
            <p className="text-[10px] text-slate-300 mt-0.5">
              여러 파일 동시 선택 가능
            </p>
          </div>
        )}

        {/* 추가 업로드 버튼 (파일이 있을 때) 또는 전체 영역 클릭 (없을 때) */}
        <label className="cursor-pointer">
          {hasFiles ? (
            <div className="flex items-center justify-center gap-1.5 py-2 rounded-lg border border-dashed border-slate-300 text-xs text-slate-500 hover:bg-slate-50 hover:text-blue-600 hover:border-blue-300 transition-colors">
              <Plus size={14} />
              <span>파일 추가</span>
            </div>
          ) : (
            <div className="absolute inset-0" />
          )}
          <input
            type="file"
            accept={config.accept}
            multiple
            onChange={handleInputChange}
            className="hidden"
          />
        </label>
      </div>
    </div>
  );
}
