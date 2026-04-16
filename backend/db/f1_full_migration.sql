-- ============================================================
-- F1 전체 마이그레이션 + 시드 통합 스크립트
-- 실행 순서: migrations 001~009 → seed 01~05
-- Supabase Dashboard > SQL Editor 에서 전체 붙여넣기 후 실행
-- ============================================================

BEGIN;

-- ── 001_pg_trgm_extension.sql ────────────────────────────────────────────
-- ============================================================
-- 001: pg_trgm 확장 활성화
-- 목적: 원재료 퍼지(trgm) 매칭 — 기능1 Step 1 5단계 매칭의 5단계
-- 선행: 없음
-- 실행: Supabase Dashboard > SQL Editor
-- 롤백: DROP EXTENSION IF EXISTS pg_trgm;  (주의: trgm 인덱스가 먼저 제거돼야 함)
-- ============================================================
-- 담당: 병찬 (기능1)
-- 참고: 계획/기능1_구현계획/01_스키마_마이그레이션_계획.md §3-1

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 검증
-- SELECT extname, extversion FROM pg_extension WHERE extname='pg_trgm';

-- ── 002_f1_allowed_ingredients.sql ────────────────────────────────────────────
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

-- ── 003_f1_additive_limits.sql ────────────────────────────────────────────
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

-- ── 004_f1_safety_standards.sql ────────────────────────────────────────────
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

-- ── 005_f1_ingredient_synonyms.sql ────────────────────────────────────────────
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

-- ── 006_f1_forbidden_ingredients.sql ────────────────────────────────────────────
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

-- ── 007_f1_escalation_logs.sql ────────────────────────────────────────────
-- ============================================================
-- 007: f1_escalation_logs 컬럼 정의
-- 목적: 기능1 에스컬레이션 이력 저장 (금지원료·미확인·주류경계치 등)
-- 선행: combined_schema.sql (cases 테이블)
-- 실행: Supabase Dashboard > SQL Editor
-- ============================================================
-- 담당: 병찬 (기능1)
-- 출처: newsamc escalation_logs 구조 + SAMC 간소화

ALTER TABLE f1_escalation_logs
  ADD COLUMN IF NOT EXISTS case_id          UUID REFERENCES cases(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS module_id        TEXT NOT NULL DEFAULT 'F1',
  ADD COLUMN IF NOT EXISTS trigger_type     TEXT,
  ADD COLUMN IF NOT EXISTS confidence_score NUMERIC(5,4),
  ADD COLUMN IF NOT EXISTS reason           TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS resolved         BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS resolved_by      UUID REFERENCES auth.users(id),
  ADD COLUMN IF NOT EXISTS resolved_at      TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS resolution_note  TEXT;

-- trigger_type 분류
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname='f1_escalation_logs_trigger_check') THEN
    ALTER TABLE f1_escalation_logs
      ADD CONSTRAINT f1_escalation_logs_trigger_check
      CHECK (trigger_type IN (
          'forbidden_hit',       -- Step 0 금지원료 적중
          'prohibited_detected', -- 별표3 원료 감지
          'low_confidence',      -- unidentified / 퍼지 낮은 신뢰도
          'compound_prohibited', -- 복합원재료 하위에 금지
          'synthetic_flavor',    -- 합성향료 하위원료 요청
          'standards_violation', -- 기준치 초과
          'alcohol_boundary',    -- 주류 경계치
          'no_data'              -- 기준치 미등록
      ) OR trigger_type IS NULL);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname='f1_escalation_logs_confidence_check') THEN
    ALTER TABLE f1_escalation_logs
      ADD CONSTRAINT f1_escalation_logs_confidence_check
      CHECK (confidence_score IS NULL
             OR (confidence_score BETWEEN 0 AND 1));
  END IF;
END $$;

COMMENT ON TABLE f1_escalation_logs IS
  '기능1 에스컬레이션 이력. 담당자 확인 필요 항목·수동 검토 대상 추적';

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_f1_escalation_case
  ON f1_escalation_logs (case_id);

CREATE INDEX IF NOT EXISTS idx_f1_escalation_unresolved
  ON f1_escalation_logs (resolved) WHERE resolved = false;

-- ── 008_f1_trgm_indexes_rpc.sql ────────────────────────────────────────────
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

-- ── 009_f1_rls_policies.sql ────────────────────────────────────────────
-- ============================================================
-- 009: f1_* 테이블 RLS 정책 초안
-- 목적: 행 수준 접근 제어 — "본인이 추가한 항목만 수정/삭제" 원칙을 DB 레벨에서 강제
-- 선행: 002~008
-- 실행: Supabase Dashboard > SQL Editor
-- ============================================================
-- ⚠️ 팀 합의 필요 — code-reviewer C2 지적 대응 초안 (병찬 작성)
--    정책 반영 시 서비스 롤(DATABASE_URL 직접 접속) 도 RLS 우회하므로
--    FORCE ROW LEVEL SECURITY 여부는 인프라 담당과 논의 후 결정.
--
-- 참고:
--    - 개발계획서 §3-5 "created_by = 현재 로그인 사용자 인 항목만 수정/삭제"
--    - Supabase 공식: https://supabase.com/docs/guides/auth/row-level-security
-- ============================================================

-- ── 공통 헬퍼: auth.uid() 미설정 시 NULL 처리 ──────────────
-- Supabase 는 JWT 의 sub 를 auth.uid() 로 노출.

-- ── f1_allowed_ingredients ───────────────────────────────
ALTER TABLE f1_allowed_ingredients ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS f1_allowed_ingredients_select_all ON f1_allowed_ingredients;
CREATE POLICY f1_allowed_ingredients_select_all
  ON f1_allowed_ingredients FOR SELECT
  USING (true);   -- 모든 인증 사용자 조회 가능

DROP POLICY IF EXISTS f1_allowed_ingredients_insert_self ON f1_allowed_ingredients;
CREATE POLICY f1_allowed_ingredients_insert_self
  ON f1_allowed_ingredients FOR INSERT
  WITH CHECK (created_by = auth.uid());

DROP POLICY IF EXISTS f1_allowed_ingredients_modify_own ON f1_allowed_ingredients;
CREATE POLICY f1_allowed_ingredients_modify_own
  ON f1_allowed_ingredients FOR UPDATE
  USING (created_by = auth.uid())
  WITH CHECK (created_by = auth.uid());

DROP POLICY IF EXISTS f1_allowed_ingredients_delete_own ON f1_allowed_ingredients;
CREATE POLICY f1_allowed_ingredients_delete_own
  ON f1_allowed_ingredients FOR DELETE
  USING (created_by = auth.uid());


-- ── f1_additive_limits ──────────────────────────────────
ALTER TABLE f1_additive_limits ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS f1_additive_limits_select_all ON f1_additive_limits;
CREATE POLICY f1_additive_limits_select_all
  ON f1_additive_limits FOR SELECT USING (true);

DROP POLICY IF EXISTS f1_additive_limits_insert_self ON f1_additive_limits;
CREATE POLICY f1_additive_limits_insert_self
  ON f1_additive_limits FOR INSERT WITH CHECK (created_by = auth.uid());

DROP POLICY IF EXISTS f1_additive_limits_modify_own ON f1_additive_limits;
CREATE POLICY f1_additive_limits_modify_own
  ON f1_additive_limits FOR UPDATE
  USING (created_by = auth.uid())
  WITH CHECK (created_by = auth.uid());

DROP POLICY IF EXISTS f1_additive_limits_delete_own ON f1_additive_limits;
CREATE POLICY f1_additive_limits_delete_own
  ON f1_additive_limits FOR DELETE USING (created_by = auth.uid());


-- ── f1_safety_standards ─────────────────────────────────
ALTER TABLE f1_safety_standards ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS f1_safety_standards_select_all ON f1_safety_standards;
CREATE POLICY f1_safety_standards_select_all
  ON f1_safety_standards FOR SELECT USING (true);

DROP POLICY IF EXISTS f1_safety_standards_insert_self ON f1_safety_standards;
CREATE POLICY f1_safety_standards_insert_self
  ON f1_safety_standards FOR INSERT WITH CHECK (created_by = auth.uid());

DROP POLICY IF EXISTS f1_safety_standards_modify_own ON f1_safety_standards;
CREATE POLICY f1_safety_standards_modify_own
  ON f1_safety_standards FOR UPDATE
  USING (created_by = auth.uid())
  WITH CHECK (created_by = auth.uid());

DROP POLICY IF EXISTS f1_safety_standards_delete_own ON f1_safety_standards;
CREATE POLICY f1_safety_standards_delete_own
  ON f1_safety_standards FOR DELETE USING (created_by = auth.uid());


-- ── f1_forbidden_ingredients ─────────────────────────────
ALTER TABLE f1_forbidden_ingredients ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS f1_forbidden_ingredients_select_all ON f1_forbidden_ingredients;
CREATE POLICY f1_forbidden_ingredients_select_all
  ON f1_forbidden_ingredients FOR SELECT USING (true);

DROP POLICY IF EXISTS f1_forbidden_ingredients_insert_self ON f1_forbidden_ingredients;
CREATE POLICY f1_forbidden_ingredients_insert_self
  ON f1_forbidden_ingredients FOR INSERT WITH CHECK (created_by = auth.uid());

DROP POLICY IF EXISTS f1_forbidden_ingredients_modify_own ON f1_forbidden_ingredients;
CREATE POLICY f1_forbidden_ingredients_modify_own
  ON f1_forbidden_ingredients FOR UPDATE
  USING (created_by = auth.uid())
  WITH CHECK (created_by = auth.uid());

DROP POLICY IF EXISTS f1_forbidden_ingredients_delete_own ON f1_forbidden_ingredients;
CREATE POLICY f1_forbidden_ingredients_delete_own
  ON f1_forbidden_ingredients FOR DELETE USING (created_by = auth.uid());


-- ── f1_escalation_logs ──────────────────────────────────
-- 에스컬레이션 로그는 모든 담당자가 조회 가능, resolved 필드만 본인이 업데이트
ALTER TABLE f1_escalation_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS f1_escalation_logs_select_all ON f1_escalation_logs;
CREATE POLICY f1_escalation_logs_select_all
  ON f1_escalation_logs FOR SELECT USING (true);

DROP POLICY IF EXISTS f1_escalation_logs_insert_any ON f1_escalation_logs;
CREATE POLICY f1_escalation_logs_insert_any
  ON f1_escalation_logs FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS f1_escalation_logs_resolve_own ON f1_escalation_logs;
CREATE POLICY f1_escalation_logs_resolve_own
  ON f1_escalation_logs FOR UPDATE
  USING (resolved_by IS NULL OR resolved_by = auth.uid())
  WITH CHECK (resolved_by = auth.uid());

-- ============================================================
-- 팀 합의 체크리스트:
--   [ ] auth.uid() 가 Supabase JWT 연동 시 정상 동작하는지 확인
--   [ ] 서비스 롤 키로 직접 접속하는 스크립트 (bootstrap_f1_db.py 등) 는
--       FORCE ROW LEVEL SECURITY 피하도록 운영 방침 정리
--   [ ] 다른 기능(F2, F4, F5) 과 정책 일관성 확인 (성은·세연·아람 합의)
-- ============================================================

-- ── 01_f1_ingredients_permitted.sql ────────────────────────────────────────────
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

-- ── 02_f1_ingredients_restricted.sql ────────────────────────────────────────────
-- ============================================================
-- 시드 02: f1_allowed_ingredients — 별표2 (restricted) 10건
-- 선행: 002_f1_allowed_ingredients.sql
-- 출처: 식품공전 [별표2], newsamc seed/05_allowed_ingredients.sql (restricted 섹션)
-- ============================================================
-- 팀컨벤션 §8: restricted는 conditions(usage_condition) 누락 금지

INSERT INTO f1_allowed_ingredients
  (name_ko, name_en, scientific_name, allowed_status, conditions, law_source, is_verified, created_by)
VALUES
  ('과라나',    'Guarana',    'Paullinia cupana',      'restricted',
   '카페인 함유 원료, 1일 섭취량 기준 관리',
   '식품공전 [별표2]', true, NULL),

  ('은행',      'Ginkgo',     'Ginkgo biloba',         'restricted',
   '사용부위: 종실(볶은 것)',
   '식품공전 [별표2]', true, NULL),

  ('마황',      'Ephedra',    'Ephedra sinica',        'restricted',
   '사용부위: 지상부(줄기). 에페드린 함량 관리',
   '식품공전 [별표2]', true, NULL),

  ('와사비',    'Wasabi',     'Eutrema japonicum',     'restricted',
   '사용부위: 근경',
   '식품공전 [별표2]', true, NULL),

  ('센나',      'Senna',      'Senna alexandrina',     'restricted',
   '사용부위: 잎, 열매(꼬투리). 센노사이드 함량 관리',
   '식품공전 [별표2]', true, NULL),

  ('허니부시',  'Honeybush',  'Cyclopia intermedia',   'restricted',
   '사용부위: 잎, 줄기',
   '식품공전 [별표2]', true, NULL),

  ('당귀',      'Angelica',   'Angelica gigas',        'restricted',
   '사용부위: 뿌리',
   '식품공전 [별표2]', true, NULL),

  ('감초',      'Licorice',   'Glycyrrhiza uralensis', 'restricted',
   '글리시리진산 함량 관리',
   '식품공전 [별표2]', true, NULL),

  ('결명자',    'Cassia seed','Senna obtusifolia',     'restricted',
   '사용부위: 종자(볶은 것)',
   '식품공전 [별표2]', true, NULL),

  ('하수오',    'Fo-ti',      'Fallopia multiflora',   'restricted',
   '사용부위: 덩이뿌리(법제한 것)',
   '식품공전 [별표2]', true, NULL)
ON CONFLICT DO NOTHING;

-- 검증: SELECT COUNT(*) FROM f1_allowed_ingredients WHERE allowed_status='restricted';  -- 10
-- 누락 방지: SELECT COUNT(*) FROM f1_allowed_ingredients
--          WHERE allowed_status='restricted' AND conditions IS NULL;  -- 0

-- ── 03_f1_ingredients_prohibited.sql ────────────────────────────────────────────
-- ============================================================
-- 시드 03: f1_allowed_ingredients — 별표3 (prohibited) 15건
-- 선행: 002_f1_allowed_ingredients.sql
-- 출처: 식품공전 [별표3] 사용할 수 없는 원료 (독성 계열)
-- ============================================================
-- 주의: 별표3은 "식품 원료로 사용 불가"지만 forbidden_ingredients 와 다름.
--   별표3: 식품 원료로 부적합 (독성)
--   forbidden_ingredients: 법적 수입 자체 금지 (마약·CITES 등)

INSERT INTO f1_allowed_ingredients
  (name_ko, name_en, scientific_name, allowed_status, conditions, law_source, is_verified, created_by)
VALUES
  ('부자',       'Aconite',         'Aconitum carmichaelii',            'prohibited', '아코니틴 독성',        '식품공전 [별표3]', true, NULL),
  ('초오',       'Monkshood',       'Aconitum kusnezoffii',             'prohibited', '아코니틴 독성',        '식품공전 [별표3]', true, NULL),
  ('백부자',     'Typhonium',       'Typhonium giganteum',              'prohibited', '독성 성분',            '식품공전 [별표3]', true, NULL),
  ('사리풀',     'Henbane',         'Hyoscyamus niger',                 'prohibited', '스코폴라민, 히오시아민 독성', '식품공전 [별표3]', true, NULL),
  ('독미나리',   'Water hemlock',   'Cicuta virosa',                    'prohibited', '시쿠톡신 독성',        '식품공전 [별표3]', true, NULL),
  ('천선자',     'Melia',           'Melia azedarach',                  'prohibited', '독성 성분',            '식품공전 [별표3]', true, NULL),
  ('투구꽃',     'Wolfsbane',       'Aconitum jaluense',                'prohibited', '아코니틴 독성',        '식품공전 [별표3]', true, NULL),
  ('섬수국',     'Hydrangea',       'Hydrangea serrata f. acuminata',   'prohibited', '청산배당체 독성',      '식품공전 [별표3]', true, NULL),
  ('눈빛승마',   'Black cohosh',    'Actaea erythrocarpa',              'prohibited', '프로토아네모닌 독성',  '식품공전 [별표3]', true, NULL),
  ('여로',       'Veratrum',        'Veratrum nigrum',                  'prohibited', '베라트리딘 독성',      '식품공전 [별표3]', true, NULL),
  ('삿갓나물',   'Paris herb',      'Paris verticillata',               'prohibited', '독성 성분',            '식품공전 [별표3]', true, NULL),
  ('미치광이풀', 'Scopolia',        'Scopolia japonica',                'prohibited', '스코폴라민 독성',      '식품공전 [별표3]', true, NULL),
  ('백선',       'Dictamnus',       'Dictamnus dasycarpus',             'prohibited', '독성 성분',            '식품공전 [별표3]', true, NULL),
  ('꽃무릇',     'Red spider lily', 'Lycoris radiata',                  'prohibited', '리코린 독성',          '식품공전 [별표3]', true, NULL),
  ('협죽도',     'Oleander',        'Nerium oleander',                  'prohibited', '올레안드린 독성',      '식품공전 [별표3]', true, NULL)
ON CONFLICT DO NOTHING;

-- 검증: SELECT COUNT(*) FROM f1_allowed_ingredients WHERE allowed_status='prohibited';  -- 15

-- ── 04_f1_forbidden_ingredients.sql ────────────────────────────────────────────
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

-- ── 05_f1_thresholds_core.sql ────────────────────────────────────────────
-- ============================================================
-- 시드 05: f1_additive_limits + f1_safety_standards 핵심 기준치
-- 선행: 003_f1_additive_limits.sql, 004_f1_safety_standards.sql
-- ============================================================
-- 담당: 병찬 (수동 입력, is_verified=true)
-- 리스크 3 Plan B: LLM 추출 전에 핵심 20건 수동 입력
-- ⚠️ 실제 값은 법령 원문 참조. 아래는 구조 예시 + 대표 케이스.

-- ============================================================
-- f1_additive_limits — 첨가물 기준치 (13건)
-- ============================================================

INSERT INTO f1_additive_limits
  (food_type, additive_name, ins_number, max_ppm, combined_group, combined_max,
   conversion_factor, colorant_category, total_tar_limit,
   condition_text, regulation_ref, is_verified, verified_by, verified_at, created_by)
VALUES
  -- 보존료 계열
  ('과채음료',      '안식향산나트륨',       '211',   600,   '안식향산류', 600,
   0.847000, NULL, NULL,
   '안식향산 기준. 측정시 ×0.847 환산',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  ('과채음료',      '안식향산',             '210',   600,   '안식향산류', 600,
   NULL,     NULL, NULL,
   NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  ('식육가공품',    '소르빈산칼륨',         '202',   2000,  '소르빈산류', 2000,
   0.746000, NULL, NULL,
   '소르빈산 기준. 측정시 ×0.746 환산',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  ('식육가공품',    '소르빈산',             '200',   2000,  '소르빈산류', 2000,
   NULL,     NULL, NULL,
   NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  -- 타르색소
  ('과자류',        '황색4호',              '102',   100,   '타르색소합산', 300,
   NULL,     'tar', 300,
   NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  ('과자류',        '적색2호',              '123',   100,   '타르색소합산', 300,
   NULL,     'tar', 300,
   NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  ('과자류',        '청색1호',              '133',   100,   '타르색소합산', 300,
   NULL,     'tar', 300,
   NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  -- 감미료
  ('과채음료',      '아스파탐',             '951',   500,   NULL,         NULL,
   NULL,     NULL, NULL,
   NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  ('과채음료',      '수크랄로스',           '955',   300,   NULL,         NULL,
   NULL,     NULL, NULL,
   NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  -- 산화방지제
  ('식용유지',      '터셔리부틸히드로퀴논', '319',   200,   NULL,         NULL,
   NULL,     NULL, NULL,
   NULL,
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  -- 발색제
  ('식육가공품',    '아질산나트륨',         '250',   70,    NULL,         NULL,
   NULL,     NULL, NULL,
   '아질산근 기준',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  -- 표백제
  ('과채가공품',    '아황산나트륨',         '221',   30,    '이산화황류', 30,
   0.639000, NULL, NULL,
   '이산화황 기준. 측정시 ×0.639 환산',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL),

  -- 증점제
  ('전체',          '잔탄검',               '415',   NULL,  NULL,         NULL,
   NULL,     NULL, NULL,
   '사용량 제한 없음',
   '식품첨가물공전 IV. 품목별 성분규격', true, NULL, NOW(), NULL)
ON CONFLICT DO NOTHING;


-- ============================================================
-- f1_safety_standards — 중금속·미생물·주류 안전기준 (9건)
-- ============================================================

INSERT INTO f1_safety_standards
  (food_type, standard_type, target_name, max_limit,
   regulation_ref, condition_text, is_verified, verified_by, verified_at, created_by)
VALUES
  -- 중금속 (일반식품)
  ('전체',          'heavy_metal',  '납',            '0.1 mg/kg',
   '식품공전 제4장 제2절', NULL, true, NULL, NOW(), NULL),

  ('전체',          'heavy_metal',  '카드뮴',        '0.05 mg/kg',
   '식품공전 제4장 제2절', NULL, true, NULL, NOW(), NULL),

  ('전체',          'heavy_metal',  '수은',          '0.1 mg/kg',
   '식품공전 제4장 제2절', NULL, true, NULL, NOW(), NULL),

  ('전체',          'heavy_metal',  '비소',          '0.1 mg/kg',
   '식품공전 제4장 제2절', NULL, true, NULL, NOW(), NULL),

  -- 미생물
  ('유가공품',      'microbe',      '대장균',        '음성',
   '식품공전 제5장', NULL, true, NULL, NOW(), NULL),

  ('유가공품',      'microbe',      '살모넬라',      '불검출',
   '식품공전 제5장', NULL, true, NULL, NOW(), NULL),

  -- 주류 안전기준 (주세법)
  ('증류주',        'alcohol',      '메탄올',        '1000 mg/L',
   '주세법 시행령 별표3', NULL, true, NULL, NOW(), NULL),

  ('증류주',        'alcohol',      '알데히드',      '70 mg/L',
   '주세법 시행령 별표3', NULL, true, NULL, NOW(), NULL),

  ('증류주',        'alcohol',      '퓨젤유',        '250 mg/L',
   '주세법 시행령 별표3', NULL, true, NULL, NOW(), NULL),

  ('증류주',        'alcohol',      '에탄올(주정도)','40 %',
   '주세법 시행령 별표1', NULL, true, NULL, NOW(), NULL)
ON CONFLICT (food_type, standard_type, target_name) DO NOTHING;

-- 검증:
-- SELECT COUNT(*) FROM f1_additive_limits WHERE is_verified=true;        -- 13
-- SELECT COUNT(*) FROM f1_safety_standards WHERE is_verified=true;       -- 10
-- SELECT standard_type, COUNT(*) FROM f1_safety_standards GROUP BY standard_type;

COMMIT;
