-- =============================================================
-- case_label_images v3 마이그레이션
-- 문제: source_hash가 파일 전체 MD5라서 동일 파일에서 여러 이미지
--       추출 시 UNIQUE INDEX(case_id, source_hash) 위반으로 2번째부터 INSERT 실패.
-- 해결:
--   1) image_index 컬럼 추가 (파일 내 순번, 0-based)
--   2) 기존 unique index 제거
--   3) 새 unique index: (case_id, source_hash, image_index)
--      → 동일 파일의 여러 이미지 허용, 동일 파일+순번 중복만 차단
-- =============================================================

-- 1) image_index 컬럼 추가
ALTER TABLE case_label_images
    ADD COLUMN IF NOT EXISTS image_index INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN case_label_images.image_index IS
    '동일 source_document 내 이미지 순번 (0-based). PDF 페이지, Excel embed 이미지 순서 등.';

-- 2) 기존 dedup 인덱스 제거 (case_id, source_hash만으로는 다중 이미지 저장 불가)
DROP INDEX IF EXISTS idx_case_label_images_dedup;

-- 3) 새 dedup 인덱스: 파일(source_hash) + 순번(image_index) 조합
--    → 같은 파일을 재처리해도 동일 순번 이미지는 중복 방지
--    → 다른 순번이면 여러 행 허용 (Excel 이미지 3개 → image_index 0, 1, 2)
CREATE UNIQUE INDEX IF NOT EXISTS idx_case_label_images_dedup
    ON case_label_images(case_id, source_hash, image_index)
    WHERE source_hash IS NOT NULL;

-- 4) 정렬 조회용 인덱스
CREATE INDEX IF NOT EXISTS idx_case_label_images_order
    ON case_label_images(case_id, source_document_id, image_index);

-- 5) 결과 확인
SELECT
    column_name,
    data_type,
    column_default,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'case_label_images'
ORDER BY ordinal_position;
