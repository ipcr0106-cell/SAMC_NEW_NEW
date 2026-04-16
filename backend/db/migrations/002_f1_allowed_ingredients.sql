-- ============================================================
-- 002: f1_allowed_ingredients 컬럼 정의
-- 목적: 기능1 Step 1 5단계 매칭의 기준 테이블
-- 선행: combined_schema.sql 실행 (f1_allowed_ingredients 스켈레톤 존재)
-- 실행: Supabase Dashboard > SQL Editor
-- ============================================================
-- 담당: 병찬 (기능1)
-- 출처: newsamc allowed_ingredients 구조 + 개발계획서 §4-1 병합
-- ============================================================

-- 이미 존재하는 스켈레톤에 컬럼 추가 (IF NOT EXISTS)
ALTER TABLE f1_allowed_ingredients
  ADD COLUMN IF NOT EXISTS name_ko         TEXT,
  ADD COLUMN IF NOT EXISTS name_en         TEXT,
  ADD COLUMN IF NOT EXISTS scientific_name TEXT,
  ADD COLUMN IF NOT EXISTS ins_number      TEXT,
  ADD COLUMN IF NOT EXISTS cas_number      TEXT,
  ADD COLUMN IF NOT EXISTS allowed_status  TEXT NOT NULL DEFAULT 'permitted',
  ADD COLUMN IF NOT EXISTS conditions      TEXT,
  ADD COLUMN IF NOT EXISTS law_source      TEXT,
  ADD COLUMN IF NOT EXISTS is_verified     BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS created_by      UUID REFERENCES auth.users(id);

-- NOT NULL 강화 (기존 행이 없으므로 안전)
ALTER TABLE f1_allowed_ingredients
  ALTER COLUMN name_ko SET NOT NULL;

-- allowed_status CHECK 제약
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conname = 'f1_allowed_ingredients_status_check'
  ) THEN
    ALTER TABLE f1_allowed_ingredients
      ADD CONSTRAINT f1_allowed_ingredients_status_check
      CHECK (allowed_status IN ('permitted','restricted','prohibited'));
  END IF;
END $$;

-- 컬럼 코멘트
COMMENT ON COLUMN f1_allowed_ingredients.allowed_status IS
  'permitted=별표1 사용가능, restricted=별표2 조건부, prohibited=별표3 금지';
COMMENT ON COLUMN f1_allowed_ingredients.conditions IS
  '별표2(restricted) 조건 텍스트. 예: "사용부위: 종실(볶은 것)"';
COMMENT ON COLUMN f1_allowed_ingredients.ins_number IS
  'INS 번호 (예: 330 구연산)';
COMMENT ON COLUMN f1_allowed_ingredients.cas_number IS
  'CAS 번호 (예: 77-92-9)';

-- 유니크 파셜 인덱스 (INS/CAS 중복 방지)
CREATE UNIQUE INDEX IF NOT EXISTS idx_f1_allowed_ingredients_ins_unique
  ON f1_allowed_ingredients (ins_number) WHERE ins_number IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_f1_allowed_ingredients_cas_unique
  ON f1_allowed_ingredients (cas_number) WHERE cas_number IS NOT NULL;

-- 기본 조회 인덱스
CREATE INDEX IF NOT EXISTS idx_f1_allowed_ingredients_name_ko
  ON f1_allowed_ingredients (name_ko);

CREATE INDEX IF NOT EXISTS idx_f1_allowed_ingredients_status
  ON f1_allowed_ingredients (allowed_status);

-- 검증
-- \d f1_allowed_ingredients
-- SELECT allowed_status, COUNT(*) FROM f1_allowed_ingredients GROUP BY allowed_status;
