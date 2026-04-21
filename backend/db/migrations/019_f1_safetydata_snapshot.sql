-- 019_f1_safetydata_snapshot.sql
-- 목적: safetydata.go.kr DSSP-IF 공전 3종 API의 전수 스냅샷 저장소
-- 배경: data.go.kr 15111777/15116583의 서버측 필터가 미작동하여 원재료 매칭·기준규격 조회 실패.
--       safetydata.go.kr API는 필터 파라미터 자체가 없는 벌크 전용이므로, 전수 다운로드 후
--       Postgres ILIKE/trgm 검색으로 클라이언트 필터링.
-- 참조:
--   .omc/research/f1_api_15111777_filter_issue.md
--   memory/feedback_f1_db_untrusted.md
-- 팀 룰: f1_ prefix, F1 전용 테이블 (공유 영향 낮음)

-- ---------------------------------------------------------------------------
-- 1. 식품공전 (DSSP-IF-20140) — 51,077 rows, 17 fields
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS f1_safetydata_food_code (
    id                SERIAL PRIMARY KEY,
    item_nm           TEXT,            -- 품목명
    test_artcl        TEXT,            -- 시험항목
    spcs_artcl        TEXT,            -- 세부항목
    item_artcl_atrb   TEXT,            -- 품목항목속성 (max 2000)
    crtr_spcfct_vl    TEXT,            -- 기준규격값
    spcfct_vl_smry    TEXT,            -- 규격값요약 (max 4000)
    jgmt_frm          TEXT,            -- 판정형식
    max_vl            TEXT,            -- 최대값
    min_vl            TEXT,            -- 최소값
    blw_belo          TEXT,            -- 이하/미만
    moth_excs         TEXT,            -- 이상/초과
    spcs_stblt        TEXT,            -- 세부적합
    icpt              TEXT,            -- 부적합
    hzr_yn            TEXT,            -- 위해여부
    unit_nm           TEXT,            -- 단위명
    vld_strt_ymd      TEXT,            -- 유효개시일자
    vld_end_ymd       TEXT,            -- 유효종료일자
    synced_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_f1_sd_food_code_item_nm_trgm
    ON f1_safetydata_food_code USING gin (item_nm gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_f1_sd_food_code_synced_at
    ON f1_safetydata_food_code (synced_at DESC);

COMMENT ON TABLE f1_safetydata_food_code IS
    'safetydata.go.kr DSSP-IF-20140 (식품공전) 전수 스냅샷. 매일 TRUNCATE + INSERT로 갱신.';

-- ---------------------------------------------------------------------------
-- 2. 식품첨가물공전 (DSSP-IF-20138) — 6,724 rows, 14 fields
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS f1_safetydata_food_additive (
    id                     SERIAL PRIMARY KEY,
    item_cd                TEXT,            -- 품목코드
    item_korn_nm           TEXT,            -- 품목한글명
    test_artcl_cd          TEXT,            -- 시험항목코드
    test_artcl_korn_nm     TEXT,            -- 시험항목한글명
    spcs_artcl_nm          TEXT,            -- 세부항목명
    crtr_spcfct_vl         TEXT,            -- 기준규격값
    crtr_spcfct_vl_smry    TEXT,            -- 기준규격값요약
    min_vl                 TEXT,            -- 최소값
    max_vl                 TEXT,            -- 최대값
    unit_nm                TEXT,            -- 단위명
    hzr_yn                 TEXT,            -- 위해여부
    src                    TEXT,            -- 출처
    vld_strt_ymd           TEXT,            -- 유효개시일자
    vld_end_ymd            TEXT,            -- 유효종료일자
    synced_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_f1_sd_food_additive_item_nm_trgm
    ON f1_safetydata_food_additive USING gin (item_korn_nm gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_f1_sd_food_additive_synced_at
    ON f1_safetydata_food_additive (synced_at DESC);

COMMENT ON TABLE f1_safetydata_food_additive IS
    'safetydata.go.kr DSSP-IF-20138 (식품첨가물공전) 전수 스냅샷.';

-- ---------------------------------------------------------------------------
-- 3. 건강기능식품공전 (DSSP-IF-20137) — 2,444 rows, 14 fields (동일 스키마)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS f1_safetydata_health_functional_food (
    id                     SERIAL PRIMARY KEY,
    item_cd                TEXT,
    item_korn_nm           TEXT,
    test_artcl_cd          TEXT,
    test_artcl_korn_nm     TEXT,
    spcs_artcl_nm          TEXT,
    crtr_spcfct_vl         TEXT,
    crtr_spcfct_vl_smry    TEXT,
    min_vl                 TEXT,
    max_vl                 TEXT,
    unit_nm                TEXT,
    hzr_yn                 TEXT,
    src                    TEXT,
    vld_strt_ymd           TEXT,
    vld_end_ymd            TEXT,
    synced_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_f1_sd_hff_item_nm_trgm
    ON f1_safetydata_health_functional_food USING gin (item_korn_nm gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_f1_sd_hff_synced_at
    ON f1_safetydata_health_functional_food (synced_at DESC);

COMMENT ON TABLE f1_safetydata_health_functional_food IS
    'safetydata.go.kr DSSP-IF-20137 (건강기능식품공전) 전수 스냅샷.';

-- ---------------------------------------------------------------------------
-- 4. 동기화 이력
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS f1_safetydata_sync_log (
    id              BIGSERIAL PRIMARY KEY,
    endpoint_id     TEXT NOT NULL,           -- 'DSSP-IF-20138' 등
    total_count     INT,
    inserted_count  INT,
    duration_s      INT,
    error           TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_f1_sd_sync_log_started_at
    ON f1_safetydata_sync_log (started_at DESC);

COMMENT ON TABLE f1_safetydata_sync_log IS
    'safetydata.go.kr 전수 동기화 스크립트 실행 이력.';
