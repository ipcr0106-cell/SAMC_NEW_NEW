-- =============================================================
-- F3 법령 자동 업데이트 — 스냅샷/롤백 히스토리 테이블
-- =============================================================
-- 검역관이 법령 파일 업로드 → 파싱 → 미리보기 → 확정 시,
-- 기존 F3 관련 테이블 상태를 JSONB 로 통째로 백업.
-- 문제 발생 시 특정 version 으로 롤백 가능.
--
-- 영향 대상 테이블 (law_name 별):
--   수입신고 구비서류 목록      → [f3_required_documents]
--   수입식품안전관리 특별법 시행규칙 → [f3_document_law_citations]
--   OEM 수입식품 관리 안내서    → [f3_document_law_citations]
--   동등성인정 협정문           → [f3_document_law_citations]
--   식품공전                    → [f3_plant_based_patterns,
--                                  f3_food_type_categories,
--                                  f3_mid_category_flags]
--   식품첨가물공전              → [f3_plant_based_patterns]
--
-- Pinecone 인덱스(samc-law-f3) 는 JSONB 에 담을 수 없으므로
-- 롤백 시 "재업로드 필요" 안내만 제공.
--
-- 설계 노트:
--   - gen_random_uuid() 은 Postgres 13+ 내장 (extension 불필요).
--     Supabase 는 기본 Postgres 15+ 라 안전.
--   - retention: 기본 90일 이상 된 이력 자동 삭제 (아래 trigger + function).
-- =============================================================

-- gen_random_uuid() 는 Postgres 13+ 내장 함수. extension 필요 없음.
-- (과거 버전 호환이 필요하면 CREATE EXTENSION IF NOT EXISTS pgcrypto 추가)

CREATE TABLE IF NOT EXISTS f3_update_history (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version          BIGSERIAL NOT NULL UNIQUE,
    law_name         TEXT NOT NULL,
    feature_label    TEXT NOT NULL DEFAULT '수입필요서류 안내',
    affected_tables  TEXT[] NOT NULL,
    scope_filter     JSONB,                                   -- 부분 교체용 필터 (예: {submission_type: "submit"})
    snapshot_data    JSONB NOT NULL,                           -- { table_name: [rows...] }
    diff_summary     JSONB NOT NULL,                           -- { added: N, modified: N, deleted: N }
    source_filename  TEXT,
    pinecone_touched BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by       TEXT,                                     -- 관리자 식별자 (X-Admin-User 헤더)
    is_rolled_back   BOOLEAN NOT NULL DEFAULT FALSE,
    rolled_back_at   TIMESTAMPTZ,
    rolled_back_by   TEXT,
    CONSTRAINT snapshot_data_not_null_when_keep
        CHECK (jsonb_typeof(snapshot_data) = 'object')
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_f3_history_created_law
    ON f3_update_history(law_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_f3_history_active
    ON f3_update_history(created_at DESC)
    WHERE NOT is_rolled_back;

COMMENT ON TABLE f3_update_history IS
    'F3 법령 업데이트 시 변경 전 스냅샷. 롤백 기능 + 감사추적.';
COMMENT ON COLUMN f3_update_history.scope_filter IS
    '부분 교체 범위 — 예: {"submission_type":"submit"}. NULL 이면 전체 테이블.';
COMMENT ON COLUMN f3_update_history.snapshot_data IS
    '변경 전 영향 테이블 JSONB. {table_name: [rows...]}. scope_filter 가 있으면 해당 범위만.';
COMMENT ON COLUMN f3_update_history.pinecone_touched IS
    'Pinecone 벡터 인덱스도 변경됐는지. TRUE 면 롤백 시 벡터 재업로드 경고.';


-- =============================================================
-- Retention: 180일 이상 된 롤백된 이력은 자동 삭제
-- (활성 이력은 유지, 롤백된 것만 정리)
--
-- 운영: Supabase pg_cron 설치 후 하루 1회 호출, 또는 수동 VACUUM.
--   SELECT cron.schedule('f3_history_retention', '0 3 * * *',
--                        'SELECT f3_history_retention_cleanup()');
-- =============================================================

CREATE OR REPLACE FUNCTION f3_history_retention_cleanup()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    deleted_count INTEGER := 0;
    batch_count   INTEGER := 0;
BEGIN
    -- 1단계: 롤백된 지 180일 이상
    DELETE FROM f3_update_history
    WHERE is_rolled_back = TRUE
      AND rolled_back_at < NOW() - INTERVAL '180 days';
    GET DIAGNOSTICS batch_count = ROW_COUNT;
    deleted_count := deleted_count + batch_count;

    -- 2단계: 활성 이력 중 1년 초과
    DELETE FROM f3_update_history
    WHERE is_rolled_back = FALSE
      AND created_at < NOW() - INTERVAL '365 days';
    GET DIAGNOSTICS batch_count = ROW_COUNT;
    deleted_count := deleted_count + batch_count;

    RETURN deleted_count;
END;
$$;

COMMENT ON FUNCTION f3_history_retention_cleanup() IS
    '롤백 180일 / 활성 365일 초과 이력 자동 삭제. pg_cron 또는 수동 호출.';


-- =============================================================
-- 동시성 잠금용 advisory lock key 생성 함수
-- (snapshot_and_replace 가 apply 시작 전에 호출)
-- =============================================================

CREATE OR REPLACE FUNCTION f3_lock_key_for_law(p_law_name TEXT)
RETURNS BIGINT
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    -- hashtext 는 int4 → bigint 변환. law_name 별로 독립 락 획득 가능.
    RETURN ('f3_law_update::' || p_law_name)::text::bigint
           -- fallback for non-numeric strings
           ;
EXCEPTION WHEN OTHERS THEN
    -- 문자열 해시 (Postgres 내장 hashtext 사용, 음수 가능)
    RETURN hashtext('f3_law_update::' || p_law_name);
END;
$$;

-- 간단 버전: 직접 hashtext 사용 (위 버전이 복잡하니 이것만 쓰면 됨)
CREATE OR REPLACE FUNCTION f3_acquire_law_lock(p_law_name TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN
    -- 같은 law_name 에 대해 다른 트랜잭션이 이미 락 잡고 있으면 false
    RETURN pg_try_advisory_xact_lock(hashtext('f3_law_update::' || p_law_name));
END;
$$;

COMMENT ON FUNCTION f3_acquire_law_lock(TEXT) IS
    '법령별 apply/rollback 동시성 락. 트랜잭션 종료 시 자동 해제.';
