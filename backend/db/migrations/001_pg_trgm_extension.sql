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
