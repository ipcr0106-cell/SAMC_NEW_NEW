-- ============================================================
-- 시드 05: f1_additive_limits + f1_safety_standards 핵심 기준치
-- 선행: 003_f1_additive_limits.sql, 004_f1_safety_standards.sql
-- ============================================================
-- 담당: 병찬 (수동 입력, is_verified=true)
-- 리스크 3 Plan B: LLM 추출 전에 핵심 20건 수동 입력
-- ⚠️ 실제 값은 법령 원문 참조. 아래는 구조 예시 + 대표 케이스.

-- ============================================================
-- f1_additive_limits — 첨가물 기준치 (13건)
-- ============================================================

INSERT INTO f1_additive_limits
  (food_type, additive_name, ins_number, max_ppm, combined_group, combined_max,
   conversion_factor, colorant_category, total_tar_limit,
   condition_text, regulation_ref, is_verified, verified_by, verified_at, created_by)
VALUES
  -- 보존료 계열
  ('과채음료',      '안식향산나트륨',       '211',   600,   '안식향산류', 600,
   0.847000, NULL, NULL,
   '안식향산 기준. 측정시 ×0.847 환산',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  ('과채음료',      '안식향산',             '210',   600,   '안식향산류', 600,
   NULL,     NULL, NULL,
   NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  ('식육가공품',    '소르빈산칼륨',         '202',   2000,  '소르빈산류', 2000,
   0.746000, NULL, NULL,
   '소르빈산 기준. 측정시 ×0.746 환산',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  ('식육가공품',    '소르빈산',             '200',   2000,  '소르빈산류', 2000,
   NULL,     NULL, NULL,
   NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  -- 타르색소
  ('과자류',        '황색4호',              '102',   100,   '타르색소합산', 300,
   NULL,     'tar', 300,
   NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  ('과자류',        '적색2호',              '123',   100,   '타르색소합산', 300,
   NULL,     'tar', 300,
   NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  ('과자류',        '청색1호',              '133',   100,   '타르색소합산', 300,
   NULL,     'tar', 300,
   NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  -- 감미료
  ('과채음료',      '아스파탐',             '951',   500,   NULL,         NULL,
   NULL,     NULL, NULL,
   NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  ('과채음료',      '수크랄로스',           '955',   300,   NULL,         NULL,
   NULL,     NULL, NULL,
   NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  -- 산화방지제
  ('식용유지',      '터셔리부틸히드로퀴논', '319',   200,   NULL,         NULL,
   NULL,     NULL, NULL,
   NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  -- 발색제
  ('식육가공품',    '아질산나트륨',         '250',   70,    NULL,         NULL,
   NULL,     NULL, NULL,
   '아질산근 기준',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  -- 표백제
  ('과채가공품',    '아황산나트륨',         '221',   30,    '이산화황류', 30,
   0.639000, NULL, NULL,
   '이산화황 기준. 측정시 ×0.639 환산',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  -- 증점제
  ('전체',          '잔탄검',               '415',   NULL,  NULL,         NULL,
   NULL,     NULL, NULL,
   '사용량 제한 없음',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL)
ON CONFLICT DO NOTHING;


-- ============================================================
-- f1_safety_standards — 중금속·미생물·주류 안전기준 (9건)
-- ============================================================

INSERT INTO f1_safety_standards
  (food_type, standard_type, target_name, max_limit,
   regulation_ref, condition_text, is_verified, verified_by, verified_at, created_by)
VALUES
  -- 중금속 (일반식품)
  ('전체',          'heavy_metal',  '납',            '0.1 mg/kg',
   '식품공전 제4장 제2절', NULL, true, NULL, NOW(), NULL),

  ('전체',          'heavy_metal',  '카드뮴',        '0.05 mg/kg',
   '식품공전 제4장 제2절', NULL, true, NULL, NOW(), NULL),

  ('전체',          'heavy_metal',  '수은',          '0.1 mg/kg',
   '식품공전 제4장 제2절', NULL, true, NULL, NOW(), NULL),

  ('전체',          'heavy_metal',  '비소',          '0.1 mg/kg',
   '식품공전 제4장 제2절', NULL, true, NULL, NOW(), NULL),

  -- 미생물
  ('유가공품',      'microbe',      '대장균',        '음성',
   '식품공전 제5장', NULL, true, NULL, NOW(), NULL),

  ('유가공품',      'microbe',      '살모넬라',      '불검출',
   '식품공전 제5장', NULL, true, NULL, NOW(), NULL),

  -- 주류 안전기준 (주세법)
  ('증류주',        'alcohol',      '메탄올',        '1000 mg/L',
   '주세법 시행령 별표3', NULL, true, NULL, NOW(), NULL),

  ('증류주',        'alcohol',      '알데히드',      '70 mg/L',
   '주세법 시행령 별표3', NULL, true, NULL, NOW(), NULL),

  ('증류주',        'alcohol',      '퓨젤유',        '250 mg/L',
   '주세법 시행령 별표3', NULL, true, NULL, NOW(), NULL),

  ('증류주',        'alcohol',      '에탄올(주정도)','40 %',
   '주세법 시행령 별표1', NULL, true, NULL, NOW(), NULL)
ON CONFLICT (food_type, standard_type, target_name) DO NOTHING;

-- 검증:
-- SELECT COUNT(*) FROM f1_additive_limits WHERE is_verified=true;        -- 13
-- SELECT COUNT(*) FROM f1_safety_standards WHERE is_verified=true;       -- 10
-- SELECT standard_type, COUNT(*) FROM f1_safety_standards GROUP BY standard_type;
