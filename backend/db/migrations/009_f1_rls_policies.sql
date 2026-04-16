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
