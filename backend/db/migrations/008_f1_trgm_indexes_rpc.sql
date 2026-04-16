-- ============================================================
-- 008: f1_allowed_ingredients trgm 인덱스 + search_f1_ingredients_trgm RPC
-- 목적: 기능1 Step 1의 5단계(퍼지 매칭) 지원
-- 선행: 001 (pg_trgm), 002 (f1_allowed_ingredients 컬럼)
-- 실행: Supabase Dashboard > SQL Editor
-- ============================================================
-- 담당: 병찬 (기능1)

-- ── GIN 트라이그램 인덱스 3종 ──────────────────────────────
CREATE INDEX IF NOT EXISTS idx_f1_allowed_ingredients_name_ko_trgm
  ON f1_allowed_ingredients USING gin (name_ko gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_f1_allowed_ingredients_name_en_trgm
  ON f1_allowed_ingredients USING gin (name_en gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_f1_allowed_ingredients_scientific_trgm
  ON f1_allowed_ingredients USING gin (scientific_name gin_trgm_ops);

-- ── search_f1_ingredients_trgm 함수 ────────────────────────
-- 입력: q(쿼리), k(상위 k개)
-- 출력: ko/en/scientific 3축 유사도 중 최대값 기준 정렬
CREATE OR REPLACE FUNCTION public.search_f1_ingredients_trgm(
  q TEXT,
  k INTEGER DEFAULT 30
)
RETURNS TABLE (
  id UUID,
  name_ko TEXT,
  name_en TEXT,
  scientific_name TEXT,
  allowed_status TEXT,
  conditions TEXT,
  law_source TEXT,
  similarity REAL
)
LANGUAGE sql STABLE AS $$
  SELECT
    ai.id,
    ai.name_ko,
    ai.name_en,
    ai.scientific_name,
    ai.allowed_status,
    ai.conditions,
    ai.law_source,
    GREATEST(
      COALESCE(similarity(ai.name_ko, q), 0),
      COALESCE(similarity(ai.name_en, q), 0),
      COALESCE(similarity(ai.scientific_name, q), 0)
    )::real AS similarity
  FROM f1_allowed_ingredients ai
  WHERE ai.name_ko % q
     OR (ai.name_en IS NOT NULL AND ai.name_en % q)
     OR (ai.scientific_name IS NOT NULL AND ai.scientific_name % q)
  ORDER BY similarity DESC
  LIMIT GREATEST(k, 1);
$$;

COMMENT ON FUNCTION public.search_f1_ingredients_trgm(TEXT, INTEGER) IS
  '기능1 원재료 trgm 퍼지 매칭 — ko/en/scientific 3축 유사도 중 최대값 기준 top-k';

-- 검증
-- SELECT * FROM search_f1_ingredients_trgm('쌀', 3);
-- EXPLAIN ANALYZE SELECT * FROM search_f1_ingredients_trgm('쌀가루', 10);
