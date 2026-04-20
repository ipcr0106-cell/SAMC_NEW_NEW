-- =============================================================
-- F3 update_history — status + idempotency + consistency 컬럼 추가
-- =============================================================
-- 015 의 후속 마이그레이션. 015 를 먼저 적용한 뒤 이걸 실행.
--
-- 추가 컬럼:
--   status           : 'pending' / 'applied' / 'failed' / 'rolled_back' / 'restored'
--                      save_history 후 실제 DB 교체 성공 시 'applied' 로 업데이트
--                      실패 시 'failed' 로 마킹 → UI 이력에서 필터링 가능
--   idempotency_key  : 클라이언트가 요청마다 UUID 제공. 같은 키로 재요청 시 이전 결과 반환.
--                      24시간 TTL (retention 으로 자동 정리)
--   updated_at       : 마지막 상태 변경 시각
--   consistency_checked_at : 마지막 Supabase ↔ Pinecone 정합성 검사 시각
--   consistency_status     : 'ok' / 'mismatch' / 'error' / NULL(미검사)
-- =============================================================

-- 015 의 BOOLEAN is_rolled_back 은 유지 (하위 호환). status 로 옮겨가지만 그 전에 둘 다 유지.
-- 장기적으로 is_rolled_back 은 removed, status 로 통일 (마이그레이션 017 에서).

ALTER TABLE f3_update_history
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'applied'
        CHECK (status IN ('pending', 'applied', 'failed', 'rolled_back', 'restored')),
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS consistency_checked_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS consistency_status TEXT
        CHECK (consistency_status IN ('ok', 'mismatch', 'error')),
    ADD COLUMN IF NOT EXISTS consistency_detail JSONB;

-- idempotency_key 빠른 조회용 인덱스
-- NOTE: DB UNIQUE 제약 대신 애플리케이션 레벨(f3_check_idempotency 함수)에서 TTL 관리.
--       (Postgres 는 index predicate 에 NOW() 같은 non-IMMUTABLE 함수 사용 불가)
CREATE INDEX IF NOT EXISTS idx_f3_history_idempotency
    ON f3_update_history(idempotency_key, created_at DESC)
    WHERE idempotency_key IS NOT NULL;

-- 실패 / 복원 된 이력 제외하고 활성 이력만 조회하는 인덱스 (UI)
CREATE INDEX IF NOT EXISTS idx_f3_history_active_status
    ON f3_update_history(law_name, created_at DESC)
    WHERE status = 'applied' AND NOT is_rolled_back;

-- consistency 검사 대상 (최근 활성 이력 중 pinecone_touched 인 것)
CREATE INDEX IF NOT EXISTS idx_f3_history_pinecone_consistency
    ON f3_update_history(consistency_checked_at NULLS FIRST)
    WHERE status = 'applied' AND pinecone_touched = TRUE AND NOT is_rolled_back;


-- =============================================================
-- updated_at 자동 갱신 트리거
-- =============================================================

CREATE OR REPLACE FUNCTION f3_update_history_touch_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_f3_history_updated_at ON f3_update_history;
CREATE TRIGGER trg_f3_history_updated_at
    BEFORE UPDATE ON f3_update_history
    FOR EACH ROW
    EXECUTE FUNCTION f3_update_history_touch_updated_at();


-- =============================================================
-- Idempotency 조회 헬퍼 — 같은 키로 최근 24시간 내 요청 있는지
-- =============================================================

CREATE OR REPLACE FUNCTION f3_check_idempotency(p_key TEXT)
RETURNS TABLE (
    found BOOLEAN,
    existing_version BIGINT,
    existing_status TEXT,
    existing_history_id UUID,
    existing_created_at TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_key IS NULL THEN
        RETURN QUERY SELECT FALSE, NULL::BIGINT, NULL::TEXT, NULL::UUID, NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    RETURN QUERY
    SELECT
        TRUE,
        h.version,
        h.status,
        h.id,
        h.created_at
    FROM f3_update_history h
    WHERE h.idempotency_key = p_key
      AND h.created_at > (NOW() - INTERVAL '24 hours')
    ORDER BY h.created_at DESC
    LIMIT 1;

    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, NULL::BIGINT, NULL::TEXT, NULL::UUID, NULL::TIMESTAMPTZ;
    END IF;
END;
$$;

COMMENT ON FUNCTION f3_check_idempotency(TEXT) IS
    '24시간 TTL 로 idempotency_key 중복 체크. 같은 키의 이전 요청 있으면 상태 반환.';
