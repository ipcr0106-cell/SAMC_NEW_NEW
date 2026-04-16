-- ============================================================
-- 시드 01: f1_allowed_ingredients — 별표1 (permitted) 85건
-- 선행: 002_f1_allowed_ingredients.sql
-- 출처: 식품공전 [별표1], newsamc seed/05_allowed_ingredients.sql (permitted 섹션)
-- ============================================================
-- 담당: 병찬 (기능1, 시스템 초기 데이터 created_by=NULL)
-- 팀컨벤션 §8: law_source 필수, is_verified=true

INSERT INTO f1_allowed_ingredients
  (name_ko, name_en, scientific_name, allowed_status, conditions, law_source, is_verified, created_by)
VALUES
  -- ── 곡류 ──
  ('쌀',         'Rice',              'Oryza sativa',            'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('밀',         'Wheat',             'Triticum aestivum',       'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('보리',       'Barley',            'Hordeum vulgare',         'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('옥수수',     'Corn',              'Zea mays',                'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('귀리',       'Oat',               'Avena sativa',            'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('메밀',       'Buckwheat',         'Fagopyrum esculentum',    'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('수수',       'Sorghum',           'Sorghum bicolor',         'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('조',         'Foxtail millet',    'Setaria italica',         'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('기장',       'Proso millet',      'Panicum miliaceum',       'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('율무',       'Job''s tears',      'Coix lacryma-jobi',       'permitted', NULL, '식품공전 [별표1]', true, NULL),
  -- ── 두류 ──
  ('대두',       'Soybean',           'Glycine max',             'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('녹두',       'Mung bean',         'Vigna radiata',           'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('팥',         'Adzuki bean',       'Vigna angularis',         'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('강낭콩',     'Kidney bean',       'Phaseolus vulgaris',      'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('완두',       'Pea',               'Pisum sativum',           'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('렌틸콩',     'Lentil',            'Lens culinaris',          'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('병아리콩',   'Chickpea',          'Cicer arietinum',         'permitted', NULL, '식품공전 [별표1]', true, NULL),
  -- ── 서류 ──
  ('감자',       'Potato',            'Solanum tuberosum',       'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('고구마',     'Sweet potato',      'Ipomoea batatas',         'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('토란',       'Taro',              'Colocasia esculenta',     'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('마',         'Yam',               'Dioscorea spp.',          'permitted', NULL, '식품공전 [별표1]', true, NULL),
  -- ── 과일류 ──
  ('사과',       'Apple',             'Malus domestica',         'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('배',         'Pear',              'Pyrus pyrifolia',         'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('포도',       'Grape',             'Vitis vinifera',          'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('복숭아',     'Peach',             'Prunus persica',          'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('감',         'Persimmon',         'Diospyros kaki',          'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('귤',         'Mandarin',          'Citrus unshiu',           'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('오렌지',     'Orange',            'Citrus sinensis',         'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('레몬',       'Lemon',             'Citrus limon',            'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('자몽',       'Grapefruit',        'Citrus paradisi',         'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('망고',       'Mango',             'Mangifera indica',        'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('바나나',     'Banana',            'Musa spp.',               'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('파인애플',   'Pineapple',         'Ananas comosus',          'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('키위',       'Kiwi',              'Actinidia deliciosa',     'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('딸기',       'Strawberry',        'Fragaria x ananassa',     'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('블루베리',   'Blueberry',         'Vaccinium corymbosum',    'permitted', NULL, '식품공전 [별표1]', true, NULL),
  -- ── 채소류 ──
  ('배추',       'Chinese cabbage',   'Brassica rapa subsp. pekinensis',  'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('무',         'Radish',            'Raphanus sativus',        'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('양배추',     'Cabbage',           'Brassica oleracea var. capitata',  'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('당근',       'Carrot',            'Daucus carota',           'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('시금치',     'Spinach',           'Spinacia oleracea',       'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('양파',       'Onion',             'Allium cepa',             'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('마늘',       'Garlic',            'Allium sativum',          'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('고추',       'Red pepper',        'Capsicum annuum',         'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('생강',       'Ginger',            'Zingiber officinale',     'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('토마토',     'Tomato',            'Solanum lycopersicum',    'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('오이',       'Cucumber',          'Cucumis sativus',         'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('호박',       'Pumpkin',           'Cucurbita spp.',          'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('브로콜리',   'Broccoli',          'Brassica oleracea var. italica',   'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('셀러리',     'Celery',            'Apium graveolens',        'permitted', NULL, '식품공전 [별표1]', true, NULL),
  -- ── 견과/종실류 ──
  ('땅콩',       'Peanut',            'Arachis hypogaea',        'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('아몬드',     'Almond',            'Prunus dulcis',           'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('호두',       'Walnut',            'Juglans regia',           'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('캐슈넛',     'Cashew nut',        'Anacardium occidentale',  'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('잣',         'Pine nut',          'Pinus koraiensis',        'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('참깨',       'Sesame',            'Sesamum indicum',         'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('들깨',       'Perilla',           'Perilla frutescens',      'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('해바라기씨', 'Sunflower seed',    'Helianthus annuus',       'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('아마씨',     'Flaxseed',          'Linum usitatissimum',     'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('치아씨',     'Chia seed',         'Salvia hispanica',        'permitted', NULL, '식품공전 [별표1]', true, NULL),
  -- ── 축산물 ──
  ('쇠고기',     'Beef',              'Bos taurus',              'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('돼지고기',   'Pork',              'Sus scrofa domesticus',   'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('닭고기',     'Chicken',           'Gallus gallus domesticus','permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('오리고기',   'Duck',              'Anas platyrhynchos domesticus', 'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('양고기',     'Lamb',              'Ovis aries',              'permitted', NULL, '식품공전 [별표1]', true, NULL),
  -- ── 수산물 ──
  ('고등어',     'Mackerel',          'Scomber japonicus',       'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('참치',       'Tuna',              'Thunnus spp.',            'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('연어',       'Salmon',            'Salmo salar',             'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('새우',       'Shrimp',            'Penaeus spp.',            'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('게',         'Crab',              'Portunus spp.',           'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('오징어',     'Squid',             'Todarodes pacificus',     'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('미역',       'Wakame',            'Undaria pinnatifida',     'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('김',         'Nori',              'Pyropia spp.',            'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('다시마',     'Kelp',              'Saccharina japonica',     'permitted', NULL, '식품공전 [별표1]', true, NULL),
  -- ── 유지원료 ──
  ('올리브',     'Olive',             'Olea europaea',           'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('코코넛',     'Coconut',           'Cocos nucifera',          'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('팜',         'Palm',              'Elaeis guineensis',       'permitted', NULL, '식품공전 [별표1]', true, NULL),
  -- ── 기타 ──
  ('꿀',         'Honey',             NULL,                      'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('우유',       'Milk',              NULL,                      'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('계란',       'Egg',               NULL,                      'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('카카오',     'Cacao',             'Theobroma cacao',         'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('커피',       'Coffee',            'Coffea arabica',          'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('녹차',       'Green tea',         'Camellia sinensis',       'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('인삼',       'Ginseng',           'Panax ginseng',           'permitted', NULL, '식품공전 [별표1]', true, NULL),
  ('홍삼',       'Red ginseng',       'Panax ginseng (steamed)', 'permitted', NULL, '식품공전 [별표1]', true, NULL)
ON CONFLICT DO NOTHING;

-- 검증: SELECT COUNT(*) FROM f1_allowed_ingredients WHERE allowed_status='permitted';  -- 85
