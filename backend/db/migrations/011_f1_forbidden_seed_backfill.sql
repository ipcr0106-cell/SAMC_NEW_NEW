-- ============================================================
-- migration 011: f1_forbidden_ingredients 누락 7건 backfill + 기존 8건 aliases 동기화
-- 선행: 006_f1_forbidden_ingredients.sql + seed/04_f1_forbidden_ingredients.sql
-- 실행일: 2026-04-17 (Phase 4-B-3e Step 0 버그 수정)
-- ============================================================
-- 배경:
--   seed 04 파일에는 15건 INSERT 구문이 있으나 운영 DB(bnfgbwwibnljynwgkgpt)에는
--   초기 버전 8건만 적재되어 있었고 기존 행의 aliases 도 구버전.
--   → 골든셋 v2 실측에서 Step 0 forbidden 게이트 적중률 10/18 (55.6%)로 관측.
--   → 누락 7건 + 기존 8건 aliases 업데이트로 18/18 (100%) 달성 확인 (R6 실측).
--
-- Idempotent:
--   INSERT ON CONFLICT DO NOTHING (기존 행 유지, 누락만 추가)
--   aliases UPDATE 는 상수값 대입이라 재실행 안전
-- ============================================================

-- 누락 7건 추가
INSERT INTO f1_forbidden_ingredients
  (name_ko, name_en, aliases, category, law_source, reason, is_verified, created_by)
VALUES
  ('코뿔소 뿔',     'Rhinoceros horn',              ARRAY['서각','犀角'],                                        'endangered',
    'CITES Appendix I / 야생생물법',           '국제 멸종위기종 보호조약 부속서 I',       true, NULL),

  ('센나잎',        'Senna leaf',                   ARRAY['센나','세네시드','Cassia angustifolia'],              'unauthorized',
    '식품의약품안전처 고시 제2020-90호',        '하제 성분(세노사이드), 식품원료 부적합', true, NULL),

  ('요힘베',        'Yohimbe',                      ARRAY['요힘빈','Pausinystalia yohimbe'],                     'unauthorized',
    '식품의약품안전처 고시 제2020-90호',        '미허가 원료. 심혈관계 부작용',             true, NULL),

  ('DMAA',          '1,3-Dimethylamylamine',        ARRAY['디메틸아밀아민','메틸헥산아민','Methylhexanamine'],    'unauthorized',
    '식품의약품안전처 고시 제2020-90호',        '미허가 스포츠보충제 금지 성분',           true, NULL),

  ('BMPEA',         'Beta-methylphenylethylamine',  ARRAY['베타메틸페닐에틸아민'],                                'unauthorized',
    '식품의약품안전처 고시 제2020-90호',        '미허가 스포츠보충제 금지 성분',           true, NULL),

  ('보라지',        'Borage',                       ARRAY['보리지','보리지오일','Borago officinalis'],           'toxin',
    '식품의약품안전처 고시 제2020-90호',        'PA 알칼로이드 함유, 식품원료 사용 제한', true, NULL),

  ('아리스토로키아','Aristolochia',                 ARRAY['방기','마두령','관목통'],                             'toxin',
    '식품의약품안전처 고시 제2020-90호',        '아리스토로킨산 신장독성/발암성',           true, NULL)
ON CONFLICT (name_ko) DO NOTHING;

-- 기존 8건 aliases 최신 시드 파일(seed 04) 기준으로 동기화
UPDATE f1_forbidden_ingredients SET aliases = ARRAY['대마','마리화나','THC','CBD오일','헴프시드오일']     WHERE name_ko='대마초';
UPDATE f1_forbidden_ingredients SET aliases = ARRAY['아편','오피움','파파베르 솜니페룸']                    WHERE name_ko='양귀비';
UPDATE f1_forbidden_ingredients SET aliases = ARRAY['코카','코카인','에리트록실론 코카']                   WHERE name_ko='코카 잎';
UPDATE f1_forbidden_ingredients SET aliases = ARRAY['타이거본','범뼈']                                     WHERE name_ko='호랑이 뼈';
UPDATE f1_forbidden_ingredients SET aliases = ARRAY['판골린','천산갑분말']                                 WHERE name_ko='천산갑 비늘';
UPDATE f1_forbidden_ingredients SET aliases = ARRAY['카바','피퍼 메티스티쿰','Piper methysticum']         WHERE name_ko='카바카바';
UPDATE f1_forbidden_ingredients SET aliases = ARRAY['마황','에페드린','Ephedrine']                         WHERE name_ko='에페드라';
UPDATE f1_forbidden_ingredients SET aliases = ARRAY['컴퓨리','심포화','Symphytum officinale']             WHERE name_ko='컴프리';

-- 검증:
--   SELECT COUNT(*) FROM f1_forbidden_ingredients WHERE is_verified=true;  -- 15
--   SELECT category, COUNT(*) FROM f1_forbidden_ingredients GROUP BY category;
--     -- drug 3, endangered 3, unauthorized 6, toxin 3
