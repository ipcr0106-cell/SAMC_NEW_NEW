-- ============================================================
-- 시드 03: f1_allowed_ingredients — 별표3 (prohibited) 15건
-- 선행: 002_f1_allowed_ingredients.sql
-- 출처: 식품공전 [별표3] 사용할 수 없는 원료 (독성 계열)
-- ============================================================
-- 주의: 별표3은 "식품 원료로 사용 불가"지만 forbidden_ingredients 와 다름.
--   별표3: 식품 원료로 부적합 (독성)
--   forbidden_ingredients: 법적 수입 자체 금지 (마약·CITES 등)

INSERT INTO f1_allowed_ingredients
  (name_ko, name_en, scientific_name, allowed_status, conditions, law_source, is_verified, created_by)
VALUES
  ('부자',       'Aconite',         'Aconitum carmichaelii',            'prohibited', '아코니틴 독성',        '식품공전 [별표3]', true, NULL),
  ('초오',       'Monkshood',       'Aconitum kusnezoffii',             'prohibited', '아코니틴 독성',        '식품공전 [별표3]', true, NULL),
  ('백부자',     'Typhonium',       'Typhonium giganteum',              'prohibited', '독성 성분',            '식품공전 [별표3]', true, NULL),
  ('사리풀',     'Henbane',         'Hyoscyamus niger',                 'prohibited', '스코폴라민, 히오시아민 독성', '식품공전 [별표3]', true, NULL),
  ('독미나리',   'Water hemlock',   'Cicuta virosa',                    'prohibited', '시쿠톡신 독성',        '식품공전 [별표3]', true, NULL),
  ('천선자',     'Melia',           'Melia azedarach',                  'prohibited', '독성 성분',            '식품공전 [별표3]', true, NULL),
  ('투구꽃',     'Wolfsbane',       'Aconitum jaluense',                'prohibited', '아코니틴 독성',        '식품공전 [별표3]', true, NULL),
  ('섬수국',     'Hydrangea',       'Hydrangea serrata f. acuminata',   'prohibited', '청산배당체 독성',      '식품공전 [별표3]', true, NULL),
  ('눈빛승마',   'Black cohosh',    'Actaea erythrocarpa',              'prohibited', '프로토아네모닌 독성',  '식품공전 [별표3]', true, NULL),
  ('여로',       'Veratrum',        'Veratrum nigrum',                  'prohibited', '베라트리딘 독성',      '식품공전 [별표3]', true, NULL),
  ('삿갓나물',   'Paris herb',      'Paris verticillata',               'prohibited', '독성 성분',            '식품공전 [별표3]', true, NULL),
  ('미치광이풀', 'Scopolia',        'Scopolia japonica',                'prohibited', '스코폴라민 독성',      '식품공전 [별표3]', true, NULL),
  ('백선',       'Dictamnus',       'Dictamnus dasycarpus',             'prohibited', '독성 성분',            '식품공전 [별표3]', true, NULL),
  ('꽃무릇',     'Red spider lily', 'Lycoris radiata',                  'prohibited', '리코린 독성',          '식품공전 [별표3]', true, NULL),
  ('협죽도',     'Oleander',        'Nerium oleander',                  'prohibited', '올레안드린 독성',      '식품공전 [별표3]', true, NULL)
ON CONFLICT DO NOTHING;

-- 검증: SELECT COUNT(*) FROM f1_allowed_ingredients WHERE allowed_status='prohibited';  -- 15
