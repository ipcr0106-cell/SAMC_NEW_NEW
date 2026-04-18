-- ============================================================
-- seed 04: f1_forbidden_ingredients — absolute prohibited ingredients
-- prerequisite: 006_f1_forbidden_ingredients.sql
-- ============================================================
-- maintainer: byungchan
-- sources: narcotics control act, CITES Appendix I, MFDS notices
-- history: initial 8 rows (mock) -> 15 rows (law sources confirmed)

INSERT INTO f1_forbidden_ingredients
  (name_ko, name_en, aliases, category, law_source, reason, is_verified, created_by)
VALUES
  -- drugs (narcotics control act)
  ('대마초', 'Cannabis', ARRAY['대마','마리화나','THC','CBD오일','헴프시드오일'], 'drug',
    '마약류 관리에 관한 법률 제2조', '마약류 관리법상 수입/판매 전면 금지', true, NULL),

  ('양귀비', 'Opium poppy', ARRAY['아편','오피움','파파베르 솜니페룸'], 'drug',
    '마약류 관리에 관한 법률 제2조', '마약류 관리법상 식품원료 사용 금지', true, NULL),

  ('코카 잎', 'Coca leaf', ARRAY['코카','코카인','에리트록실론 코카'], 'drug',
    '마약류 관리에 관한 법률 제2조', '마약류 원료 식물', true, NULL),

  -- endangered species (CITES)
  ('호랑이 뼈', 'Tiger bone', ARRAY['타이거본','범뼈'], 'endangered',
    'CITES Appendix I / 야생생물법', '국제 멸종위기종 보호조약 부속서 I', true, NULL),

  ('천산갑 비늘', 'Pangolin scale', ARRAY['판골린','천산갑분말'], 'endangered',
    'CITES Appendix I / 야생생물법', '국제 멸종위기종 보호조약 부속서 I', true, NULL),

  ('코뿔소 뿔', 'Rhinoceros horn', ARRAY['서각','犀角'], 'endangered',
    'CITES Appendix I / 야생생물법', '국제 멸종위기종 보호조약 부속서 I', true, NULL),

  -- unauthorized substances (MFDS)
  ('카바카바', 'Kava kava', ARRAY['카바','피퍼 메티스티쿰','Piper methysticum'], 'unauthorized',
    '식품의약품안전처 고시 제2020-90호', '간 독성으로 식약처 식품원료 사용 불허', true, NULL),

  ('에페드라', 'Ephedra', ARRAY['마황','에페드린','Ephedrine'], 'unauthorized',
    '식품의약품안전처 고시 제2020-90호', '의약품 원료로 분류, 식품원료 사용 불가', true, NULL),

  ('센나잎', 'Senna leaf', ARRAY['센나','세네시드','Cassia angustifolia'], 'unauthorized',
    '식품의약품안전처 고시 제2020-90호', '하제 성분(세노사이드), 식품원료 부적합', true, NULL),

  ('요힘베', 'Yohimbe', ARRAY['요힘빈','Pausinystalia yohimbe'], 'unauthorized',
    '식품의약품안전처 고시 제2020-90호', '미허가 원료. 심혈관계 부작용', true, NULL),

  ('DMAA', '1,3-Dimethylamylamine', ARRAY['디메틸아밀아민','메틸헥산아민','Methylhexanamine'], 'unauthorized',
    '식품의약품안전처 고시 제2020-90호', '미허가 스포츠보충제 금지 성분', true, NULL),

  ('BMPEA', 'Beta-methylphenylethylamine', ARRAY['베타메틸페닐에틸아민'], 'unauthorized',
    '식품의약품안전처 고시 제2020-90호', '미허가 스포츠보충제 금지 성분', true, NULL),

  -- toxins
  ('컴프리', 'Comfrey', ARRAY['컴퓨리','심포화','Symphytum officinale'], 'toxin',
    '식품의약품안전처 고시 제2020-90호', 'PA 알칼로이드 간독성으로 식품원료 사용 금지', true, NULL),

  ('보라지', 'Borage', ARRAY['보리지','보리지오일','Borago officinalis'], 'toxin',
    '식품의약품안전처 고시 제2020-90호', 'PA 알칼로이드 함유, 식품원료 사용 제한', true, NULL),

  ('아리스토로키아', 'Aristolochia', ARRAY['방기','마두령','관목통'], 'toxin',
    '식품의약품안전처 고시 제2020-90호', '아리스토로킨산 신장독성/발암성', true, NULL)
ON CONFLICT DO NOTHING;

-- verify:
-- SELECT COUNT(*) FROM f1_forbidden_ingredients WHERE is_verified=true;  -- 15
-- SELECT * FROM f1_forbidden_ingredients WHERE '대마' = ANY(aliases);  -- 1
