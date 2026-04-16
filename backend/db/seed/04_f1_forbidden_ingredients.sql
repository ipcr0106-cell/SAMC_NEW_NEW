-- ============================================================
-- 시드 04: f1_forbidden_ingredients — 절대 금지 원료 8건 (mock)
-- 선행: 006_f1_forbidden_ingredients.sql
-- 출처: newsamc V013_forbidden_ingredients.sql (mock 데이터)
-- ============================================================
-- ⚠️ mock 데이터. 실제 법령 근거 확정 후 교체 필요.
-- ⚠️ SAMC 자문 결과 받으면 이 파일 업데이트 + 채팅 공지.

INSERT INTO f1_forbidden_ingredients
  (name_ko, name_en, aliases, category, law_source, reason, is_verified, created_by)
VALUES
  ('대마초', 'Cannabis', ARRAY['대마','마리화나','THC'], 'drug',
    '마약류 관리에 관한 법률', '마약류 관리법상 수입·판매 전면 금지', true, NULL),

  ('양귀비', 'Opium poppy', ARRAY['아편','오피움'], 'drug',
    '마약류 관리에 관한 법률', '마약류 관리법상 식품원료 사용 금지', true, NULL),

  ('코카 잎', 'Coca leaf', ARRAY['코카','코카인'], 'drug',
    '마약류 관리에 관한 법률', '마약류 원료 식물', true, NULL),

  ('호랑이 뼈', 'Tiger bone', ARRAY['타이거본','범뼈'], 'endangered',
    'CITES Appendix I', '국제 멸종위기종 보호조약 부속서 I', true, NULL),

  ('천산갑 비늘', 'Pangolin scale', ARRAY['판골린'], 'endangered',
    'CITES Appendix I', '국제 멸종위기종 보호조약 부속서 I', true, NULL),

  ('카바카바', 'Kava kava', ARRAY['카바','피퍼 메티스티쿰'], 'unauthorized',
    '식품의약품안전처 고시', '간 독성으로 식약처 식품원료 사용 불허', true, NULL),

  ('에페드라', 'Ephedra', ARRAY['마황','에페드린'], 'unauthorized',
    '식품의약품안전처 고시', '의약품 원료로 분류, 식품원료 사용 불가', true, NULL),

  ('컴프리', 'Comfrey', ARRAY['컴퓨리','심포화'], 'toxin',
    '식품의약품안전처 고시', 'PA 알칼로이드 간독성으로 식품원료 사용 금지', true, NULL)
ON CONFLICT DO NOTHING;

-- 검증:
-- SELECT COUNT(*) FROM f1_forbidden_ingredients WHERE is_verified=true;  -- 8
-- SELECT * FROM f1_forbidden_ingredients WHERE '대마' = ANY(aliases);  -- 1
