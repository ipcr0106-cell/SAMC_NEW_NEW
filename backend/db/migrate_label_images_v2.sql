-- =============================================================
-- case_label_images v2 마이그레이션
-- Supabase SQL Editor 에서 실행 (기존 테이블에 컬럼 추가)
-- =============================================================
-- 변경사항:
--   1) 라벨에서 추출한 텍스트 필드 6개 추가
--   2) 중복 방지용 source_hash 컬럼 추가
--   3) dedup 유니크 인덱스 추가
-- =============================================================

-- 1) 텍스트 추출 컬럼 추가
ALTER TABLE case_label_images
    ADD COLUMN IF NOT EXISTS label_product_name   TEXT,   -- 제품명
    ADD COLUMN IF NOT EXISTS label_ingredients    TEXT,   -- 원재료
    ADD COLUMN IF NOT EXISTS label_content_volume TEXT,   -- 내용량
    ADD COLUMN IF NOT EXISTS label_origin         TEXT,   -- 원산지
    ADD COLUMN IF NOT EXISTS label_manufacturer   TEXT,   -- 제조사
    ADD COLUMN IF NOT EXISTS label_case_number    TEXT,   -- 케이스 넘버
    ADD COLUMN IF NOT EXISTS extracted_texts      JSONB,  -- 전체 추출 결과 원본 (위 6개 + 기타)
    ADD COLUMN IF NOT EXISTS source_hash          TEXT;   -- 원본 파일 MD5 (중복 감지용)

-- 2) dedup 인덱스: 같은 케이스에 동일 파일 재업로드 방지
--    (source_hash가 NULL이면 인덱스 제외 — NULL은 dedup 대상 아님)
CREATE UNIQUE INDEX IF NOT EXISTS idx_case_label_images_dedup
    ON case_label_images(case_id, source_hash)
    WHERE source_hash IS NOT NULL;

-- 3) 텍스트 검색용 인덱스
CREATE INDEX IF NOT EXISTS idx_case_label_images_product_name
    ON case_label_images(label_product_name);

-- 4) 확인
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'case_label_images'
ORDER BY ordinal_position;
