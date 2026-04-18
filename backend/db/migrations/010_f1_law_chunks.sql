-- ============================================================
-- 010: f1_law_chunks — Pinecone samc-law-f1 미러 테이블
-- 목적: RAG 청크 목록을 admin UI에서 조회/관리 (재임베딩/삭제)
-- 선행: 001~009
-- 실행: Supabase Dashboard > SQL Editor
--
-- 참고:
--    - 계획/f1_RAG도입계획_전처리.md §2
--    - 계획/f1_RAG도입계획_총괄.md §2.5
-- ============================================================

CREATE TABLE IF NOT EXISTS f1_law_chunks (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    vector_id           text NOT NULL UNIQUE,
    regulation_id       text NOT NULL,
    pinecone_namespace  text NOT NULL,
    section_path        text,
    text                text NOT NULL,
    token_count         int,
    chunk_index         int,
    total_chunks        int,
    embedded_at         timestamptz NOT NULL DEFAULT now(),
    created_at          timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE f1_law_chunks IS
    'Pinecone samc-law-f1 인덱스의 청크 미러 — admin UI 관리용';
COMMENT ON COLUMN f1_law_chunks.vector_id IS
    'Pinecone vector ID (규칙: {regulation_id}_{chunk_index})';
COMMENT ON COLUMN f1_law_chunks.pinecone_namespace IS
    'food_code_text | additive_code_text | functional_labeling | temporary_standard | health_food_text';

-- ── 인덱스 ──
CREATE INDEX IF NOT EXISTS idx_f1_law_chunks_namespace
    ON f1_law_chunks(pinecone_namespace);
CREATE INDEX IF NOT EXISTS idx_f1_law_chunks_regulation
    ON f1_law_chunks(regulation_id);
CREATE INDEX IF NOT EXISTS idx_f1_law_chunks_vector_id
    ON f1_law_chunks(vector_id);

-- ── RLS ──
ALTER TABLE f1_law_chunks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS f1_law_chunks_select_all ON f1_law_chunks;
CREATE POLICY f1_law_chunks_select_all
    ON f1_law_chunks FOR SELECT
    USING (true);   -- 모든 인증 사용자 조회 가능

DROP POLICY IF EXISTS f1_law_chunks_write_service ON f1_law_chunks;
CREATE POLICY f1_law_chunks_write_service
    ON f1_law_chunks FOR ALL
    USING (auth.role() = 'service_role');
