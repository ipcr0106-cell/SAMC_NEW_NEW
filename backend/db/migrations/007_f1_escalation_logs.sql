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
