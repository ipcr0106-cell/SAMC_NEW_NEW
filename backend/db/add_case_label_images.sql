-- =============================================================
-- 수출국 라벨 이미지에서 추출한 '제품 사진' 저장 테이블
-- Supabase SQL Editor 에서 1회 실행
-- =============================================================
-- 목적:
--   업로드된 라벨 이미지(doc_type='label')에서 Vision AI로
--   제품 사진 영역을 자동 크롭하여 별도 저장. f4(수출국표시사항 검토)
--   팀원이 이 테이블을 조회해 제품 라벨 이미지 메타를 바로 사용.
-- =============================================================

CREATE TABLE IF NOT EXISTS case_label_images (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id                UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    source_document_id     UUID REFERENCES documents(id) ON DELETE CASCADE,
    cropped_storage_path   TEXT NOT NULL,          -- 제품만 크롭된 PNG 경로 (documents 버킷)
    original_storage_path  TEXT,                   -- 원본 라벨 이미지 경로
    bbox                   JSONB,                  -- { x1, y1, x2, y2 } 픽셀 좌표
    width                  INTEGER,
    height                 INTEGER,
    created_at             TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_case_label_images_case_id
    ON case_label_images(case_id);
