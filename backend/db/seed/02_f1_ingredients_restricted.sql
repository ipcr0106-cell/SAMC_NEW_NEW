-- ============================================================
-- 시드 02: f1_allowed_ingredients — 별표2 (restricted) 10건
-- 선행: 002_f1_allowed_ingredients.sql
-- 출처: 식품공전 [별표2], newsamc seed/05_allowed_ingredients.sql (restricted 섹션)
-- ============================================================
-- 팀컨벤션 §8: restricted는 conditions(usage_condition) 누락 금지

INSERT INTO f1_allowed_ingredients
  (name_ko, name_en, scientific_name, allowed_status, conditions, law_source, is_verified, created_by)
VALUES
  ('과라나',    'Guarana',    'Paullinia cupana',      'restricted',
   '카페인 함유 원료, 1일 섭취량 기준 관리',
   '식품공전 [별표2]', true, NULL),

  ('은행',      'Ginkgo',     'Ginkgo biloba',         'restricted',
   '사용부위: 종실(볶은 것)',
   '식품공전 [별표2]', true, NULL),

  ('마황',      'Ephedra',    'Ephedra sinica',        'restricted',
   '사용부위: 지상부(줄기). 에페드린 함량 관리',
   '식품공전 [별표2]', true, NULL),

  ('와사비',    'Wasabi',     'Eutrema japonicum',     'restricted',
   '사용부위: 근경',
   '식품공전 [별표2]', true, NULL),

  ('센나',      'Senna',      'Senna alexandrina',     'restricted',
   '사용부위: 잎, 열매(꼬투리). 센노사이드 함량 관리',
   '식품공전 [별표2]', true, NULL),

  ('허니부시',  'Honeybush',  'Cyclopia intermedia',   'restricted',
   '사용부위: 잎, 줄기',
   '식품공전 [별표2]', true, NULL),

  ('당귀',      'Angelica',   'Angelica gigas',        'restricted',
   '사용부위: 뿌리',
   '식품공전 [별표2]', true, NULL),

  ('감초',      'Licorice',   'Glycyrrhiza uralensis', 'restricted',
   '글리시리진산 함량 관리',
   '식품공전 [별표2]', true, NULL),

  ('결명자',    'Cassia seed','Senna obtusifolia',     'restricted',
   '사용부위: 종자(볶은 것)',
   '식품공전 [별표2]', true, NULL),

  ('하수오',    'Fo-ti',      'Fallopia multiflora',   'restricted',
   '사용부위: 덩이뿌리(법제한 것)',
   '식품공전 [별표2]', true, NULL)
ON CONFLICT DO NOTHING;

-- 검증: SELECT COUNT(*) FROM f1_allowed_ingredients WHERE allowed_status='restricted';  -- 10
-- 누락 방지: SELECT COUNT(*) FROM f1_allowed_ingredients
--          WHERE allowed_status='restricted' AND conditions IS NULL;  -- 0
