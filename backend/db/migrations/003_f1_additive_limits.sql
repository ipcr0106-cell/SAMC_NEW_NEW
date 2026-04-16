-- ============================================================
-- 003: f1_additive_limits 컬럼 정의
-- 목적: 첨가물 기준치 테이블 (ppm, 병용 그룹, 타르색소 총량)
-- 선행: 002 (f1_allowed_ingredients)
-- 실행: Supabase Dashboard > SQL Editor
-- ============================================================
-- 담당: 병찬 (기능1)
-- 출처: newsamc additive_limits 구조

ALTER TABLE f1_additive_limits
  ADD COLUMN IF NOT EXISTS food_type          TEXT,
  ADD COLUMN IF NOT EXISTS additive_name      TEXT,
  ADD COLUMN IF NOT EXISTS ins_number         TEXT,
  ADD COLUMN IF NOT EXISTS max_ppm            NUMERIC(12,4),
  ADD COLUMN IF NOT EXISTS combined_group     TEXT,
  ADD COLUMN IF NOT EXISTS combined_max       NUMERIC(12,4),
  ADD COLUMN IF NOT EXISTS conversion_factor  NUMERIC(8,6),
  ADD COLUMN IF NOT EXISTS colorant_category  TEXT,
  ADD COLUMN IF NOT EXISTS color_group        TEXT,
  ADD COLUMN IF NOT EXISTS total_tar_limit    NUMERIC(12,4),
  ADD COLUMN IF NOT EXISTS condition_text     TEXT,
  ADD COLUMN IF NOT EXISTS regulation_ref     TEXT,
  ADD COLUMN IF NOT EXISTS is_verified        BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS verified_by        UUID REFERENCES auth.users(id),
  ADD COLUMN IF NOT EXISTS verified_at        TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS created_by         UUID REFERENCES auth.users(id);

ALTER TABLE f1_additive_limits
  ALTER COLUMN additive_name SET NOT NULL;

-- CHECK 제약
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname='f1_additive_limits_max_ppm_check') THEN
    ALTER TABLE f1_additive_limits
      ADD CONSTRAINT f1_additive_limits_max_ppm_check
      CHECK (max_ppm IS NULL OR max_ppm >= 0);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname='f1_additive_limits_colorant_check') THEN
    ALTER TABLE f1_additive_limits
      ADD CONSTRAINT f1_additive_limits_colorant_check
      CHECK (colorant_category IN ('tar','non-tar','natural')
             OR colorant_category IS NULL);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname='f1_additive_limits_conversion_check') THEN
    ALTER TABLE f1_additive_limits
      ADD CONSTRAINT f1_additive_limits_conversion_check
      CHECK (conversion_factor IS NULL OR conversion_factor > 0);
  END IF;
END $$;

COMMENT ON COLUMN f1_additive_limits.max_ppm IS
  '최대 허용 ppm. NULL=사용 금지 또는 무제한(조건부).';
COMMENT ON COLUMN f1_additive_limits.conversion_factor IS
  '염→산 환산계수 (예: 안식향산나트륨→안식향산 0.847, 소르빈산칼륨→소르빈산 0.746)';
COMMENT ON COLUMN f1_additive_limits.combined_group IS
  '병용(합산) 그룹명. 같은 그룹은 combined_max 공유';
COMMENT ON COLUMN f1_additive_limits.total_tar_limit IS
  '타르색소 합계 상한 (colorant_category=tar 전용)';

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_f1_additive_limits_food_additive
  ON f1_additive_limits (food_type, additive_name);

CREATE INDEX IF NOT EXISTS idx_f1_additive_limits_combined
  ON f1_additive_limits (combined_group) WHERE combined_group IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_f1_additive_limits_verified
  ON f1_additive_limits (is_verified) WHERE is_verified = true;

-- 검증
-- SELECT COUNT(*) FROM f1_additive_limits WHERE is_verified=true;
