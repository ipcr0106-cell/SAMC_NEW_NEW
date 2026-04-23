-- 020_f1_law_cache.sql
-- 목적: F1 Step D 법령 인용을 Pinecone에서 law.go.kr DB 캐시로 교체.
-- 데이터 출처: 국가법령정보센터 (law.go.kr) DRF API — 법제처 공식.
-- 적재 스크립트: backend/scripts/f1_sync_laws.py
-- 참조:
--   계획/f1 재설계 계획/04_Step_D_법령인용_설계.md
--   법령_API_전환_가이드.md
--   memory/feedback_f1_db_untrusted.md
-- 팀 룰: f1_ prefix, F1 전용 테이블 (공유 영향 없음)

-- ---------------------------------------------------------------------------
-- 1. 법령 메타 (Pinecone 5 namespace 와 1:1 대응)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS f1_law_cache (
    id              BIGSERIAL PRIMARY KEY,
    namespace       TEXT NOT NULL UNIQUE,    -- food_code_text / additive_code_text / health_food_text / temporary_standard / functional_labeling
    law_name        TEXT NOT NULL,
    api_type        TEXT NOT NULL,           -- 'admrul' (현재 5종 모두 행정규칙)
    api_id          TEXT NOT NULL,           -- LID (행정규칙ID)
    api_공포일자    TEXT,                     -- API 발령일자 (YYYYMMDD)
    last_sync_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE f1_law_cache IS
    'F1 Step D 법령 인용 소스 5종 (식품공전·첨가물·건기식·한시기준·기능성표시) 메타. law.go.kr DRF.';

-- ---------------------------------------------------------------------------
-- 2. article 단위 본문 (조문 + 별표)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS f1_law_articles (
    id              BIGSERIAL PRIMARY KEY,
    law_cache_id    BIGINT NOT NULL REFERENCES f1_law_cache(id) ON DELETE CASCADE,
    article_label   TEXT NOT NULL,           -- "제3조(목적)" 또는 "별표 1(농약 잔류허용기준)"
    text            TEXT NOT NULL,           -- 원문 (LawCitation.text 그대로 노출)
    article_type    TEXT NOT NULL DEFAULT 'article'  -- 'article' | 'byeolpyo'
);

CREATE INDEX IF NOT EXISTS idx_f1_law_articles_cache
    ON f1_law_articles (law_cache_id);

CREATE INDEX IF NOT EXISTS idx_f1_law_articles_text_trgm
    ON f1_law_articles USING gin (text gin_trgm_ops);

COMMENT ON TABLE f1_law_articles IS
    'f1_law_cache 의 article 단위 본문. ILIKE/trgm 다중 키워드 검색 대상.';
