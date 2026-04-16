-- ============================================================
-- 006: f1_forbidden_ingredients 신규 테이블
-- 목적: 식품유형 무관 절대 금지 원재료 — 기능1 Step 0 게이트
-- 선행: 001 (pg_trgm)
-- 실행: Supabase Dashboard > SQL Editor
-- ============================================================
-- 담당: 병찬 (기능1 단독 소유 신규 제안)
-- 출처: newsamc V013_forbidden_ingredients.sql
-- 주의: combined_schema.sql에 없는 신규 테이블. 병찬이 추가.

CREATE TABLE IF NOT EXISTS f1_forbidden_ingredients (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name_ko     TEXT NOT NULL,
  name_en     TEXT,
  aliases     TEXT[] NOT NULL DEFAULT '{}',
  category    TEXT NOT NULL
              CHECK (category IN ('drug','endangered','unauthorized','toxin','other')),
  law_source  TEXT,
  reason      TEXT,
  is_verified BOOLEAN NOT NULL DEFAULT false,
  created_by  UUID REFERENCES auth.users(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE f1_forbidden_ingredients IS
  '식품유형 무관 절대 금지 원재료 마스터 — 기능1 Step 0 게이트. 적중 시 파이프라인 즉시 중단.';
COMMENT ON COLUMN f1_forbidden_ingredients.category IS
  'drug=마약류, endangered=멸종위기종(CITES), unauthorized=식약처 미허가, toxin=독성';

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_f1_forbidden_name_ko
  ON f1_forbidden_ingredients (name_ko);

CREATE INDEX IF NOT EXISTS idx_f1_forbidden_name_ko_trgm
  ON f1_forbidden_ingredients USING gin (name_ko gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_f1_forbidden_aliases
  ON f1_forbidden_ingredients USING gin (aliases);

-- updated_at 트리거
DROP TRIGGER IF EXISTS trg_f1_forbidden_updated_at ON f1_forbidden_ingredients;
CREATE TRIGGER trg_f1_forbidden_updated_at
  BEFORE UPDATE ON f1_forbidden_ingredients
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 검증
-- SELECT COUNT(*) FROM f1_forbidden_ingredients WHERE is_verified=true;
-- SELECT * FROM f1_forbidden_ingredients WHERE '대마' = ANY(aliases);
