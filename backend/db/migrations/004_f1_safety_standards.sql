-- ============================================================
-- 004: f1_safety_standards 컬럼 정의
-- 목적: 중금속·미생물·잔류농약·주류 안전기준 (문자열 max_limit 허용)
-- 선행: combined_schema.sql
-- 실행: Supabase Dashboard > SQL Editor
-- ============================================================
-- 담당: 병찬 (기능1)
-- 출처: newsamc safety_standards 구조
-- 주의: max_limit 는 TEXT — "불검출", "음성", "0.1 mg/kg" 등 문자열 저장

ALTER TABLE f1_safety_standards
  ADD COLUMN IF NOT EXISTS food_type       TEXT,
  ADD COLUMN IF NOT EXISTS standard_type   TEXT,
  ADD COLUMN IF NOT EXISTS target_name     TEXT,
  ADD COLUMN IF NOT EXISTS max_limit       TEXT,
  ADD COLUMN IF NOT EXISTS regulation_ref  TEXT,
  ADD COLUMN IF NOT EXISTS condition_text  TEXT,
  ADD COLUMN IF NOT EXISTS is_verified     BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS verified_by     UUID REFERENCES auth.users(id),
  ADD COLUMN IF NOT EXISTS verified_at     TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS created_by      UUID REFERENCES auth.users(id);

ALTER TABLE f1_safety_standards
  ALTER COLUMN target_name SET NOT NULL,
  ALTER COLUMN max_limit SET NOT NULL;

-- CHECK 제약
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname='f1_safety_standards_type_check') THEN
    ALTER TABLE f1_safety_standards
      ADD CONSTRAINT f1_safety_standards_type_check
      CHECK (standard_type IN ('microbe','heavy_metal','pesticide','contaminant','alcohol')
             OR standard_type IS NULL);
  END IF;
END $$;

COMMENT ON COLUMN f1_safety_standards.max_limit IS
  '기준치. TEXT로 "불검출", "음성", "0.1 mg/kg" 등 문자열 허용';
COMMENT ON COLUMN f1_safety_standards.standard_type IS
  'microbe=미생물, heavy_metal=중금속, pesticide=잔류농약, contaminant=기타오염물질, alcohol=주류 안전기준';

-- 유니크 제약: 같은 식품유형·기준유형·대상 중복 방지
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname='f1_safety_standards_uniq') THEN
    ALTER TABLE f1_safety_standards
      ADD CONSTRAINT f1_safety_standards_uniq
      UNIQUE (food_type, standard_type, target_name);
  END IF;
END $$;

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_f1_safety_standards_food_type
  ON f1_safety_standards (food_type);

CREATE INDEX IF NOT EXISTS idx_f1_safety_standards_type
  ON f1_safety_standards (standard_type);

CREATE INDEX IF NOT EXISTS idx_f1_safety_standards_target_trgm
  ON f1_safety_standards USING gin (target_name gin_trgm_ops);

-- 검증
-- SELECT standard_type, COUNT(*) FROM f1_safety_standards GROUP BY standard_type;
