-- 017_pipeline_steps_status_expansion.sql
-- Wave 3 HITL 도입 — pipeline_steps.status CHECK 확장
-- 참조:
--   계획/f1 재설계 계획/05_HITL_플로우_설계.md §6
--   계획/f1 재설계 계획/10_마이그레이션_계획.md §4-2
--
-- 기존 허용값: pending, running, completed, waiting_review, needs_review
-- 추가값    : approved (HITL-0), confirmed (HITL-2), locked (확정 잠금)
--
-- 롤백 쿼리는 파일 하단 주석 참조.

BEGIN;

ALTER TABLE pipeline_steps
    DROP CONSTRAINT IF EXISTS pipeline_steps_status_check;

ALTER TABLE pipeline_steps
    ADD CONSTRAINT pipeline_steps_status_check
    CHECK (status IN (
        'pending',
        'running',
        'completed',
        'approved',       -- HITL-0 승인 (F0 전용)
        'waiting_review', -- HITL-1 대기
        'needs_review',   -- HITL-1 필요 (에스컬레이션)
        'confirmed',      -- HITL-2 완료
        'locked'          -- 확정 후 잠김
    ));

COMMIT;

-- ──────────────────────────────────────────────────────────
-- 롤백 (emergency):
--
--   BEGIN;
--   ALTER TABLE pipeline_steps DROP CONSTRAINT IF EXISTS pipeline_steps_status_check;
--   -- 선행 조건: approved/confirmed/locked 행을 completed 또는 waiting_review 로 변환 필요
--   -- UPDATE pipeline_steps SET status='completed' WHERE status IN ('approved','confirmed','locked');
--   ALTER TABLE pipeline_steps
--       ADD CONSTRAINT pipeline_steps_status_check
--       CHECK (status IN ('pending','running','completed','waiting_review','needs_review'));
--   COMMIT;
--
-- ⚠️  롤백 전에 f1_audit_log 참조 무결성 확인 필수.
