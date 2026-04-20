-- =============================================================
-- case_label_images v4 마이그레이션
-- 추가:
--   1) label_certification_marks  — 인증마크 목록 (Kosher, Halal, USDA Organic 등)
--   2) label_nutrition_facts      — 영양성분표 원문 텍스트
--   3) full_page_storage_path     — 크롭 전 전체 페이지 이미지 경로 (f4 분석용)
--
-- 배경:
--   - f0 Vision이 인증마크·영양성분표도 추출하도록 확장
--   - f4가 전체 라벨 이미지(인증마크·성분표·디자인 포함)를 분석하려면
--     크롭된 제품 사진이 아닌 전체 페이지 이미지 경로가 필요
-- =============================================================

-- 1) 인증마크 텍스트 컬럼
ALTER TABLE case_label_images
    ADD COLUMN IF NOT EXISTS label_certification_marks TEXT;

COMMENT ON COLUMN case_label_images.label_certification_marks IS
    '인증마크 목록 (쉼표 구분). 예: "Kosher Pareve, USDA Organic, Halal, CRT Tequila"';

-- 2) 영양성분표 원문 컬럼
ALTER TABLE case_label_images
    ADD COLUMN IF NOT EXISTS label_nutrition_facts TEXT;

COMMENT ON COLUMN case_label_images.label_nutrition_facts IS
    '영양성분표 원문 텍스트. 열량, 탄수화물, 단백질, 지방 등 표에 기재된 내용.';

-- 3) 전체 페이지 이미지 경로
ALTER TABLE case_label_images
    ADD COLUMN IF NOT EXISTS full_page_storage_path TEXT;

COMMENT ON COLUMN case_label_images.full_page_storage_path IS
    '크롭 전 전체 페이지 이미지의 Storage 경로. bbox 크롭 시에만 값이 있음. f4 인증마크·디자인 분석용.';

-- 4) 결과 확인
SELECT
    column_name,
    data_type,
    column_default,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'case_label_images'
ORDER BY ordinal_position;
