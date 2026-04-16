"use client";

import { Upload } from "lucide-react";
import FileDropzone, { type DocType, type UploadedFile } from "./FileDropzone";

interface DocumentUploadGridProps {
  onFileSelect: (docType: string, file: File) => void | Promise<void>;
  /** doc_type → 업로드된 파일 목록 (id + name). 한 칸에 여러 파일 가능 */
  restoredFiles?: Record<string, UploadedFile[]>;
  /** 개별 파일 삭제 */
  onFileDelete?: (docId: string) => void | Promise<void>;
}

const docTypes: DocType[] = ["ingredients", "process", "msds", "label", "other"];

export default function DocumentUploadGrid({
  onFileSelect,
  restoredFiles,
  onFileDelete,
}: DocumentUploadGridProps) {
  return (
    <div className="flex flex-col h-full">
      {/* 헤더 */}
      <div className="flex items-center gap-2.5 mb-5">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-blue-50 text-blue-600">
          <Upload size={16} />
        </div>
        <div>
          <h2 className="text-base font-bold text-slate-900">서류 업로드</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            각 항목마다 여러 파일을 올릴 수 있어요 (1개 이상이면 분석 가능)
          </p>
        </div>
      </div>

      {/* 그리드 */}
      <div className="grid grid-cols-1 gap-3 flex-1">
        {docTypes.map((type) => (
          <FileDropzone
            key={type}
            docType={type}
            restoredFiles={restoredFiles?.[type] || []}
            onFileSelect={(file) => onFileSelect(type, file)}
            onFileDelete={onFileDelete}
          />
        ))}
      </div>
    </div>
  );
}
