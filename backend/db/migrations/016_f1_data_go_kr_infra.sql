-- 016_f1_data_go_kr_infra.sql
-- 목적: F1 재설계 Wave 1 W1-A — data.go.kr 4 엔드포인트 캐시/호출 로그 인프라 생성
-- 참조:
--   계획/f1 재설계 계획/07_데이터_모델_변경_설계.md §3-2
--   계획/f1 재설계 계획/06_API_클라이언트_설계.md §6 (캐시 TTL 정책)
-- 팀 룰: 새로운 F1 전용 테이블이므로 공유 영향 낮음. 프로덕션 적용 전 PR 승인 필요.
-- 실행: Supabase Studio SQL Editor (프로젝트 bnfgbwwibnljynwgkgpt)

-- ---------------------------------------------------------------------------
-- 1. 캐시 테이블
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS f1_data_go_kr_cache (
    cache_key       TEXT PRIMARY KEY,
    endpoint_id     TEXT NOT NULL,                   -- '15111777' 등
    request_params  JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_body   JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL
);

-- 만료 청소용 인덱스 (cron / 파티션 대용)
CREATE INDEX IF NOT EXISTS idx_f1_data_go_kr_cache_expires_at
    ON f1_data_go_kr_cache (expires_at);

CREATE INDEX IF NOT EXISTS idx_f1_data_go_kr_cache_endpoint_id
    ON f1_data_go_kr_cache (endpoint_id);

COMMENT ON TABLE f1_data_go_kr_cache IS
    'F1 data.go.kr API 응답 캐시. cache_key = sha256(endpoint_id + sorted(params)).';
COMMENT ON COLUMN f1_data_go_kr_cache.expires_at IS
    '24h default, 15116583 (ADDITIVE_STANDARD) only 7d per 06번 §6';

-- ---------------------------------------------------------------------------
-- 2. 호출 로그 테이블 (Rate limit 추적용)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS f1_data_go_kr_call_log (
    id              BIGSERIAL PRIMARY KEY,
    endpoint_id     TEXT NOT NULL,
    case_id         UUID REFERENCES cases(id) ON DELETE SET NULL,
    cache_hit       BOOLEAN NOT NULL DEFAULT FALSE,
    status_code     INT,
    duration_ms     INT,
    called_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_f1_data_go_kr_call_log_called_at
    ON f1_data_go_kr_call_log (called_at DESC);

CREATE INDEX IF NOT EXISTS idx_f1_data_go_kr_call_log_endpoint_id
    ON f1_data_go_kr_call_log (endpoint_id, called_at DESC);

COMMENT ON TABLE f1_data_go_kr_call_log IS
    'F1 data.go.kr API 호출 로그. Rate limit 추적 및 성능 메트릭용.';

-- ---------------------------------------------------------------------------
-- 3. RLS (선택) — 서비스 롤 전용이므로 기본적으로 RLS 미설정
--     관리자 대시보드에서 읽기 권한 필요 시 09_f1_rls_policies.sql 패턴 참고
-- ---------------------------------------------------------------------------

-- 롤백:
--   DROP TABLE IF EXISTS f1_data_go_kr_call_log;
--   DROP TABLE IF EXISTS f1_data_go_kr_cache;
