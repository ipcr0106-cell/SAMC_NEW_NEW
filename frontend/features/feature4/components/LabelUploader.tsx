/**
 * 기능4: 라벨 이미지 업로드 컴포넌트
 */

"use client";

import type { LabelUploadState } from "../types";
import { ALLOWED_LABEL_EXTENSIONS } from "../constants";

interface LabelUploaderProps {
  uploadState: LabelUploadState;
  onFileSelect: (file: File) => void;
  onUpload: () => void;
}

export default function LabelUploader({
  uploadState,
  onFileSelect,
  onUpload,
}: LabelUploaderProps) {
  const { file, previewUrl, uploadStatus } = uploadState;

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) onFileSelect(selected);
  };

  return (
    <div className="border rounded-lg p-4 space-y-3">
      <p className="text-sm font-medium text-gray-700">
        해외 원본 라벨 이미지 업로드
      </p>
      <p className="text-xs text-gray-400">
        허용 형식: {ALLOWED_LABEL_EXTENSIONS}
      </p>

      {/* 파일 선택 */}
      <input
        type="file"
        accept={ALLOWED_LABEL_EXTENSIONS}
        onChange={handleChange}
        className="block text-sm text-gray-500 file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:text-sm file:bg-gray-100 hover:file:bg-gray-200"
      />

      {/* 이미지 미리보기 */}
      {previewUrl && (
        <img
          src={previewUrl}
          alt="라벨 미리보기"
          className="max-h-64 rounded border object-contain"
        />
      )}

      {file && uploadStatus !== "uploaded" && (
        <button
          onClick={onUpload}
          disabled={uploadStatus === "uploading"}
          className="px-4 py-2 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {uploadStatus === "uploading" ? "업로드 중..." : "업로드"}
        </button>
      )}

      {uploadStatus === "uploaded" && (
        <span className="text-sm text-green-600">업로드 완료</span>
      )}
    </div>
  );
}
