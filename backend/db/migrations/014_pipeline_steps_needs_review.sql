-- 014_pipeline_steps_needs_review.sql
-- 목적: Phase 5 HITL 기능을 위해 pipeline_steps.status 에 'needs_review' 값 허용
-- 배경: routers/feature1.py:400 가 conflict/rag_supplemented 시 status="needs_review" 설정하나
--       combined_schema.sql:91 CHECK 제약에 미포함 → 500 에러 (2026-04-18 QA 발견)
-- 팀 룰: pipeline_steps 는 공유 테이블 — team sign-off 필요 (PR 코멘트)
-- 실행: Supabase Studio(bnfgbwwibnljynwgkgpt) SQL Editor 경유

ALTER TABLE pipeline_steps
  DROP CONSTRAINT IF EXISTS pipeline_steps_status_check;

ALTER TABLE pipeline_steps
  ADD CONSTRAINT pipeline_steps_status_check
  CHECK (status IN (
    'pending',
    'running',
    'waiting_review',
    'needs_review',
    'completed',
    'error'
  ));
