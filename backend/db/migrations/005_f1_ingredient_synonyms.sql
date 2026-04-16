-- ============================================================
-- 005: f1_ingredient_synonyms 컬럼 정의
-- 목적: 원재료 이명(동의어/영문명/학명 등) 매핑
-- 선행: 002 (f1_allowed_ingredients)
-- 실행: Supabase Dashboard > SQL Editor
-- ============================================================
-- 담당: 병찬 (기능1)
-- 출처: newsamc ingredient_synonyms 구조

ALTER TABLE f1_ingredient_synonyms
  ADD COLUMN IF NOT EXISTS name_standard TEXT,
  ADD COLUMN IF NOT EXISTS name_variant  TEXT,
  ADD COLUMN IF NOT EXISTS language      TEXT NOT NULL DEFAULT 'ko';

ALTER TABLE f1_ingredient_synonyms
  ALTER COLUMN name_standard SET NOT NULL,
  ALTER COLUMN name_variant  SET NOT NULL;

-- language CHECK
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname='f1_ingredient_synonyms_lang_check') THEN
    ALTER TABLE f1_ingredient_synonyms
      ADD CONSTRAINT f1_ingredient_synonyms_lang_check
      CHECK (language IN ('ko','en','ja','zh','la'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname='f1_ingredient_synonyms_uniq') THEN
    ALTER TABLE f1_ingredient_synonyms
      ADD CONSTRAINT f1_ingredient_synonyms_uniq
      UNIQUE (name_standard, name_variant, language);
  END IF;
END $$;

COMMENT ON COLUMN f1_ingredient_synonyms.name_standard IS
  'f1_allowed_ingredients.name_ko 와 매칭되는 표준 명칭';
COMMENT ON COLUMN f1_ingredient_synonyms.name_variant IS
  '이명/약칭/영문명 등. 입력 원재료명이 여기에 매칭되면 표준명으로 정규화';
COMMENT ON COLUMN f1_ingredient_synonyms.language IS
  'ko=한국어, en=영어, ja=일본어, zh=중국어, la=라틴(학명)';

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_f1_ingredient_synonyms_standard
  ON f1_ingredient_synonyms (name_standard);

CREATE INDEX IF NOT EXISTS idx_f1_ingredient_synonyms_variant_trgm
  ON f1_ingredient_synonyms USING gin (name_variant gin_trgm_ops);
