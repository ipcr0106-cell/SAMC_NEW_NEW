-- ============================================================
-- migration 013: f1_safety_standards 확장판(seed 07) DB backfill
-- 선행: 004_f1_safety_standards.sql + seed/05_f1_thresholds_core.sql(10건)
-- 실행일: 2026-04-17 (Phase 4-B-3e Step 3 drift 해결)
-- ============================================================
-- 배경:
--   seed 07 파일에는 약 30건의 확장 safety 기준치(중금속/미생물/잔류농약/주류) 가 정의되어 있으나
--   운영 DB(bnfgbwwibnljynwgkgpt)에는 seed 05 core 10건만 적재되어 있음.
--   → F1 Step 3 안전기준 검증이 식품유형별 특화 기준/잔류농약에서 부족.
--
-- 참고: newsamc safety_standards 는 0건 (원천 데이터 없음). seed 07 재실행이 유일한 경로.
--
-- Idempotent: ON CONFLICT (food_type, standard_type, target_name) DO NOTHING
--
-- 실행 방법 (수동):
--   1) Supabase Studio → SQL Editor → 이 파일 내용 붙여넣기 → Run
--   2) 또는 psql: \i backend/db/migrations/013_f1_safety_standards_backfill.sql
-- ============================================================

INSERT INTO f1_safety_standards
  (food_type, standard_type, target_name, max_limit, regulation_ref, condition_text, is_verified, verified_by, verified_at, created_by)
VALUES
  -- heavy metals — food-type specific
  ('과자류',        'heavy_metal',  '납',            '0.3 mg/kg',  '식품공전 제4장 제2절', NULL, true, NULL, NOW(), NULL),
  ('음료류',        'heavy_metal',  '납',            '0.1 mg/kg',  '식품공전 제4장 제2절', NULL, true, NULL, NOW(), NULL),
  ('수산물',        'heavy_metal',  '납',            '0.5 mg/kg',  '식품공전 제4장 제2절', NULL, true, NULL, NOW(), NULL),
  ('수산물',        'heavy_metal',  '카드뮴',        '1.0 mg/kg',  '식품공전 제4장 제2절', NULL, true, NULL, NOW(), NULL),
  ('수산물',        'heavy_metal',  '수은',          '0.5 mg/kg',  '식품공전 제4장 제2절', '다랑어류 1.0 mg/kg', true, NULL, NOW(), NULL),
  ('빵류',          'heavy_metal',  '납',            '0.2 mg/kg',  '식품공전 제4장 제2절', NULL, true, NULL, NOW(), NULL),
  ('식육가공품',    'heavy_metal',  '납',            '0.5 mg/kg',  '식품공전 제4장 제2절', NULL, true, NULL, NOW(), NULL),
  ('유가공품',      'heavy_metal',  '납',            '0.02 mg/kg', '식품공전 제4장 제2절', '원유, 우유류 기준', true, NULL, NOW(), NULL),
  ('유가공품',      'heavy_metal',  '비소',          '0.1 mg/kg',  '식품공전 제4장 제2절', NULL, true, NULL, NOW(), NULL),
  ('영아용식품',    'heavy_metal',  '납',            '0.01 mg/kg', '식품공전 제4장 제2절', NULL, true, NULL, NOW(), NULL),
  ('영아용식품',    'heavy_metal',  '카드뮴',        '0.01 mg/kg', '식품공전 제4장 제2절', NULL, true, NULL, NOW(), NULL),
  -- microbes — food-type specific
  ('과자류',        'microbe',      '대장균',        '음성',         '식품공전 제5장', NULL, true, NULL, NOW(), NULL),
  ('빵류',          'microbe',      '대장균',        '음성',         '식품공전 제5장', NULL, true, NULL, NOW(), NULL),
  ('식육가공품',    'microbe',      '살모넬라',      '불검출',       '식품공전 제5장', '25g 기준', true, NULL, NOW(), NULL),
  ('식육가공품',    'microbe',      '대장균',        '음성',         '식품공전 제5장', NULL, true, NULL, NOW(), NULL),
  ('식육가공품',    'microbe',      '황색포도상구균','불검출',       '식품공전 제5장', '25g 기준', true, NULL, NOW(), NULL),
  ('식육가공품',    'microbe',      '리스테리아',    '불검출',       '식품공전 제5장', '25g 기준', true, NULL, NOW(), NULL),
  ('수산물',        'microbe',      '살모넬라',      '불검출',       '식품공전 제5장', '25g 기준', true, NULL, NOW(), NULL),
  ('음료류',        'microbe',      '대장균',        '음성',         '식품공전 제5장', NULL, true, NULL, NOW(), NULL),
  ('음료류',        'microbe',      '살모넬라',      '불검출',       '식품공전 제5장', '25g 기준', true, NULL, NOW(), NULL),
  ('영아용식품',    'microbe',      '살모넬라',      '불검출',       '식품공전 제5장', '25g 기준', true, NULL, NOW(), NULL),
  ('영아용식품',    'microbe',      '리스테리아',    '불검출',       '식품공전 제5장', '25g 기준', true, NULL, NOW(), NULL),
  ('영아용식품',    'microbe',      '대장균',        '음성',         '식품공전 제5장', NULL, true, NULL, NOW(), NULL),
  -- pesticide residues — general limits (major 5)
  ('전체',          'pesticide',    '클로르피리포스','0.01 mg/kg',   '식품공전 제4장 잔류농약 기준', 'PLS 일률기준', true, NULL, NOW(), NULL),
  ('전체',          'pesticide',    '디클로르보스',  '0.01 mg/kg',   '식품공전 제4장 잔류농약 기준', 'PLS 일률기준', true, NULL, NOW(), NULL),
  ('전체',          'pesticide',    '카벤다짐',      '0.01 mg/kg',   '식품공전 제4장 잔류농약 기준', 'PLS 일률기준', true, NULL, NOW(), NULL),
  ('전체',          'pesticide',    '이마자릴',      '0.01 mg/kg',   '식품공전 제4장 잔류농약 기준', 'PLS 일률기준. 감귤류 5.0 mg/kg', true, NULL, NOW(), NULL),
  ('전체',          'pesticide',    '치아벤다졸',    '0.01 mg/kg',   '식품공전 제4장 잔류농약 기준', 'PLS 일률기준. 감귤류 10.0 mg/kg', true, NULL, NOW(), NULL),
  -- additional liquor standards (expanded food types)
  ('발효주',        'alcohol',      '메탄올',        '500 mg/L',     '주세법 시행령 별표3', NULL, true, NULL, NOW(), NULL),
  ('발효주',        'alcohol',      '알데히드',      '50 mg/L',      '주세법 시행령 별표3', NULL, true, NULL, NOW(), NULL)
ON CONFLICT (food_type, standard_type, target_name) DO NOTHING;

-- 검증:
--   SELECT COUNT(*) FROM f1_safety_standards WHERE is_verified=true;
--   expected: 10 (core) + 30 (this file) = 40 total
