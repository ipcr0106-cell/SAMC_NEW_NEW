-- =============================================================
-- F4 법령 API 전환 — Supabase 마이그레이션
-- 기존 필드 유지, API 관리용 컬럼 4개 추가
-- 실행: Supabase 대시보드 > SQL Editor 에서 실행
-- =============================================================

ALTER TABLE f4_law_documents
    ADD COLUMN IF NOT EXISTS api_id          TEXT,           -- MST(법령) 또는 LID(고시)
    ADD COLUMN IF NOT EXISTS api_type        TEXT,           -- "eflaw" 또는 "admrul"
    ADD COLUMN IF NOT EXISTS api_공포일자     TEXT,           -- API 응답의 공포일자/발령일자 (변경 감지용)
    ADD COLUMN IF NOT EXISTS last_api_sync_at TIMESTAMPTZ;   -- 마지막 API 동기화 시각

COMMENT ON COLUMN f4_law_documents.api_id IS 'MST(법령) 또는 LID(고시) — 국가법령정보센터 API 식별자';
COMMENT ON COLUMN f4_law_documents.api_type IS 'eflaw(법령) 또는 admrul(행정규칙)';
COMMENT ON COLUMN f4_law_documents.api_공포일자 IS 'API 응답 공포일자/발령일자 — 변경 감지에 사용';
COMMENT ON COLUMN f4_law_documents.last_api_sync_at IS '마지막 API 동기화 시각';
