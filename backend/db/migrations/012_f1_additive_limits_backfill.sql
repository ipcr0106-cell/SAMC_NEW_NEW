-- ============================================================
-- migration 012: f1_additive_limits 확장판(seed 06) DB backfill
-- 선행: 003_f1_additive_limits.sql + seed/05_f1_thresholds_core.sql(13건)
-- 실행일: 2026-04-17 (Phase 4-B-3e Step 3 drift 해결)
-- ============================================================
-- 배경:
--   seed 06 파일에는 약 50건의 확장 additive 기준치가 정의되어 있으나
--   운영 DB(bnfgbwwibnljynwgkgpt)에는 seed 05 core 13건만 적재되어 있음.
--   → F1 Step 3 기준치 검증이 빵류/과자류/탄산음료 등 주요 food_type 에서 부족.
--
-- Idempotent: ON CONFLICT DO NOTHING (기존 행 유지).
--
-- 실행 방법 (수동):
--   1) Supabase Studio → SQL Editor → 이 파일 내용 붙여넣기 → Run
--   2) 또는 psql: \i backend/db/migrations/012_f1_additive_limits_backfill.sql
--   3) 또는 Python: backend/scripts/apply_seed.py 로 bulk insert (구현 필요)
-- ============================================================

INSERT INTO f1_additive_limits
  (food_type, additive_name, ins_number, max_ppm, combined_group, combined_max,
   conversion_factor, colorant_category, total_tar_limit,
   condition_text, regulation_ref, is_verified, verified_by, verified_at, created_by)
VALUES
  -- preservatives (additional food types)
  ('빵류',          '소르빈산',             '200',   1000,  '소르빈산류', 1000, NULL,     NULL, NULL, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('빵류',          '소르빈산칼륨',         '202',   1000,  '소르빈산류', 1000, 0.746000, NULL, NULL,
   '소르빈산 기준. 측정시 x0.746 환산',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('잼류',          '소르빈산',             '200',   1000,  '소르빈산류', 1000, NULL,     NULL, NULL, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('절임식품',      '소르빈산',             '200',   1000,  '소르빈산류', 1000, NULL,     NULL, NULL, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('어육가공품',    '소르빈산',             '200',   2000,  '소르빈산류', 2000, NULL,     NULL, NULL, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('유가공품',      '소르빈산',             '200',   3000,  '소르빈산류', 3000, NULL,     NULL, NULL, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('과자류',        '안식향산',             '210',   1000,  '안식향산류', 1000, NULL,     NULL, NULL, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('탄산음료',      '안식향산나트륨',       '211',   600,   '안식향산류', 600,  0.847000, NULL, NULL,
   '안식향산 기준. 측정시 x0.847 환산',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('간장류',        '안식향산',             '210',   600,   '안식향산류', 600,  NULL,     NULL, NULL, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('전체',          '프로피온산',           '280',   2500,  '프로피온산류', 2500, NULL,   NULL, NULL,
   '빵류, 과자류에 한함',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('전체',          '프로피온산칼슘',       '282',   2500,  '프로피온산류', 2500, 0.793000, NULL, NULL,
   '프로피온산 기준. 빵류, 과자류에 한함',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('과채음료',      '파라옥시안식향산메틸', '218',   250,   NULL,         NULL, NULL,     NULL, NULL, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  -- sweeteners (expanded)
  ('과자류',        '아스파탐',             '951',   5000,  NULL,         NULL, NULL,     NULL, NULL, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('과자류',        '수크랄로스',           '955',   1800,  NULL,         NULL, NULL,     NULL, NULL, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('전체',          '사카린나트륨',         '954',   200,   NULL,         NULL, NULL,     NULL, NULL, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('전체',          '아세설팜칼륨',         '950',   500,   NULL,         NULL, NULL,     NULL, NULL, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('빵류',          '소르비톨',             '420',   NULL,  NULL,         NULL, NULL,     NULL, NULL,
   '사용량 제한 없음',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('전체',          '스테비올배당체',       '960',   200,   NULL,         NULL, NULL,     NULL, NULL, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('전체',          '자일리톨',             '967',   NULL,  NULL,         NULL, NULL,     NULL, NULL,
   '사용량 제한 없음',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('전체',          '에리스리톨',           '968',   NULL,  NULL,         NULL, NULL,     NULL, NULL,
   '사용량 제한 없음',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  -- tar colorants (expanded)
  ('음료류',        '황색4호',              '102',   50,    '타르색소합산', 100, NULL,    'tar', 100, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('음료류',        '적색40호',             '129',   50,    '타르색소합산', 100, NULL,    'tar', 100, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('음료류',        '청색1호',              '133',   50,    '타르색소합산', 100, NULL,    'tar', 100, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('과자류',        '황색5호',              '110',   100,   '타르색소합산', 300, NULL,    'tar', 300, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('과자류',        '적색40호',             '129',   100,   '타르색소합산', 300, NULL,    'tar', 300, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('과자류',        '적색3호',              '127',   100,   '타르색소합산', 300, NULL,    'tar', 300, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('과자류',        '녹색3호',              '143',   100,   '타르색소합산', 300, NULL,    'tar', 300, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('빵류',          '황색4호',              '102',   100,   '타르색소합산', 300, NULL,    'tar', 300, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('식육가공품',    '적색40호',             '129',   70,    '타르색소합산', 70,  NULL,    'tar', 70,
   '식육가공품 중 소시지류에 한함',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('식육가공품',    '황색4호',              '102',   70,    '타르색소합산', 70,  NULL,    'tar', 70,
   '식육가공품 중 소시지류에 한함',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  -- antioxidants (expanded)
  ('식용유지',      '부틸히드록시아니솔',   '320',   200,   NULL,         NULL, NULL,     NULL, NULL,
   'BHA. 유지 기준',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('식용유지',      '디부틸히드록시톨루엔', '321',   200,   NULL,         NULL, NULL,     NULL, NULL,
   'BHT. 유지 기준',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('전체',          '에리소르빈산',         '315',   NULL,  NULL,         NULL, NULL,     NULL, NULL,
   '사용량 제한 없음',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('전체',          '에리소르빈산나트륨',   '316',   NULL,  NULL,         NULL, NULL,     NULL, NULL,
   '사용량 제한 없음',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('식용유지',      '프로필갈레이트',       '310',   100,   NULL,         NULL, NULL,     NULL, NULL,
   '유지 기준',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('전체',          '아스코르빈산',         '300',   NULL,  NULL,         NULL, NULL,     NULL, NULL,
   '사용량 제한 없음',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  -- color fixatives / curing agents (expanded)
  ('어육가공품',    '아질산나트륨',         '250',   70,    NULL,         NULL, NULL,     NULL, NULL,
   '아질산근 기준',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('전체',          '질산칼륨',             '252',   70,    NULL,         NULL, NULL,     NULL, NULL,
   '아질산근 기준',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('전체',          '질산나트륨',           '251',   70,    NULL,         NULL, NULL,     NULL, NULL,
   '아질산근 기준',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  -- bleaching agents (expanded)
  ('건조과일',      '아황산나트륨',         '221',   2000,  '이산화황류', 2000, 0.639000, NULL, NULL,
   '이산화황 기준. 건조과일류',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('과채음료',      '이산화황',             '220',   30,    '이산화황류', 30,  NULL,     NULL, NULL, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('빵류',          '이산화황',             '220',   30,    '이산화황류', 30,  NULL,     NULL, NULL, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  -- emulsifiers / thickeners / misc (expanded)
  ('전체',          '카라기난',             '407',   NULL,  NULL,         NULL, NULL,     NULL, NULL,
   '사용량 제한 없음. 영아용 제외',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('전체',          '구아검',               '412',   NULL,  NULL,         NULL, NULL,     NULL, NULL,
   '사용량 제한 없음',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('전체',          '카르복시메틸셀룰로오스나트륨', '466', NULL, NULL, NULL, NULL,          NULL, NULL,
   '사용량 제한 없음. CMC',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('전체',          '레시틴',               '322',   NULL,  NULL,         NULL, NULL,     NULL, NULL,
   '사용량 제한 없음',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('전체',          '구연산',               '330',   NULL,  NULL,         NULL, NULL,     NULL, NULL,
   '사용량 제한 없음. pH조정용',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('전체',          '탄산수소나트륨',       '500ii', NULL,  NULL,         NULL, NULL,     NULL, NULL,
   '사용량 제한 없음. 팽창제',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('전체',          '인산칼슘',             '341',   NULL,  NULL,         NULL, NULL,     NULL, NULL,
   '사용량 제한 없음',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),
  ('전체',          '폴리소르베이트80',     '433',   1000,  NULL,         NULL, NULL,     NULL, NULL, NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL)
ON CONFLICT DO NOTHING;

-- 검증:
--   SELECT COUNT(*) FROM f1_additive_limits WHERE is_verified=true;
--   expected: 13 (core) + 50 (this file) = 63 total
