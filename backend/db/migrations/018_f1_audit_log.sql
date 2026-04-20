-- 018_f1_audit_log.sql
-- Wave 3 HITL 감사 로그 — 모든 HITL-0/1/2 액션을 `f1_audit_log` 에 기록.
-- 참조: 계획/f1 재설계 계획/05_HITL_플로우_설계.md §7
--
-- 필드 설계:
--   step        : 'f0' | 'f1.hitl1' | 'f1.hitl2'
--   action      : 'edit' | 'approve' | 'hitl1_decisions' | 'confirm' | 'unlock'
--   before/after: JSONB — 변경 전/후 스냅샷 (edit/decisions 경로)
--   reason      : 편집 사유(F0EditRequest.edit_reason) 또는 final_reason(HITL-2)
--   signed_at   : 전자서명 시각 (HITL-2 confirm 경로에서만 채움)

BEGIN;

CREATE TABLE IF NOT EXISTS f1_audit_log (
    id          BIGSERIAL PRIMARY KEY,
    case_id     UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    step        TEXT NOT NULL,
    action      TEXT NOT NULL,
    actor_id    TEXT NOT NULL,
    before      JSONB,
    after       JSONB,
    reason      TEXT,
    signed_at   TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT f1_audit_log_step_check
        CHECK (step IN ('f0', 'f1.hitl1', 'f1.hitl2')),
    CONSTRAINT f1_audit_log_action_check
        CHECK (action IN ('edit', 'approve', 'hitl1_decisions', 'confirm', 'unlock'))
);

CREATE INDEX IF NOT EXISTS idx_f1_audit_log_case_id
    ON f1_audit_log (case_id);

CREATE INDEX IF NOT EXISTS idx_f1_audit_log_created_at
    ON f1_audit_log (created_at);

CREATE INDEX IF NOT EXISTS idx_f1_audit_log_step_action
    ON f1_audit_log (step, action);

COMMIT;

-- ──────────────────────────────────────────────────────────
-- 롤백 (emergency):
--
--   BEGIN;
--   DROP INDEX IF EXISTS idx_f1_audit_log_step_action;
--   DROP INDEX IF EXISTS idx_f1_audit_log_created_at;
--   DROP INDEX IF EXISTS idx_f1_audit_log_case_id;
--   DROP TABLE IF EXISTS f1_audit_log;
--   COMMIT;
--
-- ⚠️  감사 로그는 규제 대응 증거이므로 롤백 전에 CSV 백업 필수.
