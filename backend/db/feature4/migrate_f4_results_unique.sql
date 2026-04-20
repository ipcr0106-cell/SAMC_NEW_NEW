-- =============================================================
-- f4_results: case_id UNIQUE constraint 추가
--
-- 배경:
--   동일 case_id로 여러 번 분석 시 중복 행이 생길 수 있었음.
--   upsert(on_conflict="case_id") 사용을 위해 UNIQUE 필요.
--
-- 실행: Supabase 대시보드 > SQL Editor
-- =============================================================

-- 기존 중복 행이 있으면 최신 것만 남기고 삭제
DELETE FROM f4_results a
USING f4_results b
WHERE a.case_id = b.case_id
  AND a.created_at < b.created_at;

-- UNIQUE constraint 추가
ALTER TABLE f4_results
    ADD CONSTRAINT uq_f4_results_case_id UNIQUE (case_id);
