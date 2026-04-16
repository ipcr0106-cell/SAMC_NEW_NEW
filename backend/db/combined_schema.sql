-- =============================================================
-- SAMC 통합 Supabase 스키마
-- 프로젝트: https://bnfgbwwibnljynwgkgpt.supabase.co (세연님 프로젝트)
--
-- 실행 방법: Supabase 대시보드 > SQL Editor 에서 전체 붙여넣기 후 실행
--
-- 테이블 prefix 규칙:
--   (없음) → 전체 공통 (cases, documents, pipeline_steps 등)
--   f1_    → 수입 가능 여부 판정  (담당: 병찬)
--   f2_    → 식품유형 분류         (담당: 아람)
--   f3_    → 수입 필요서류 안내   (담당: 미정) ← 추후 추가
--   f4_    → 수출국표시사항 검토  (담당: 성은)
--   f5_    → 한글표시사항 검토    (담당: 세연)
--
-- =============================================================
-- [공통 테이블 활용 안내] — 전원 필독
-- =============================================================
-- cases, documents, pipeline_steps, law_alerts, feedback_logs는
-- 모든 기능이 공유하는 파이프라인 핵심 테이블입니다.
--
-- ▶ 각 기능에서 결과를 저장할 때:
--   pipeline_steps 테이블에 INSERT/UPDATE 하세요.
--   step_key 컬럼 기준: '1'=수입가능여부, '2'=식품유형, 'A'=필요서류,
--                       'B'=수출국표시사항, '6'=한글표시사항
--   결과는 ai_result(JSONB) 컬럼에 저장, 담당자 확인 후 final_result에 복사.
--
-- ▶ 각 기능에서 업로드 파일을 참조할 때:
--   documents 테이블을 case_id로 조회하세요.
--   기능별 전용 파일은 f{n}_ 테이블에 별도 저장하지 말고
--   documents.doc_type을 활용하세요.
--
-- ▶ 공통 테이블은 직접 수정하지 마세요.
--   스키마 변경이 필요하면 성은(PM)에게 먼저 공유 후 진행.
-- =============================================================


-- =============================================================
-- [공통] updated_at 자동 갱신 트리거 함수
-- =============================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- =============================================================
-- [공통] 전체 기능 공유 핵심 테이블
-- =============================================================

-- 수입 건 (Case) — 파이프라인의 기본 단위
CREATE TABLE IF NOT EXISTS cases (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_name    TEXT NOT NULL,
    importer_name   TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'processing'
                    CHECK (status IN ('processing','completed','on_hold','error')),
    current_step    TEXT DEFAULT '0',
    parent_case_id  UUID REFERENCES cases(id),
    created_by      UUID REFERENCES auth.users(id),
    locked_by       UUID REFERENCES auth.users(id),
    locked_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 업로드된 서류 목록
CREATE TABLE IF NOT EXISTS documents (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id      UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    doc_type     TEXT NOT NULL
                 CHECK (doc_type IN ('ingredients','process','msds','material','label','other')),
    file_name    TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    mime_type    TEXT,
    parsed_md    TEXT,
    is_verified  BOOLEAN DEFAULT false,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- 8단계 파이프라인 각 단계 결과 저장
CREATE TABLE IF NOT EXISTS pipeline_steps (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id        UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    step_key       TEXT NOT NULL,
    step_name      TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','running','waiting_review','completed','error')),
    ai_result      JSONB,
    final_result   JSONB,
    edited_by      UUID REFERENCES auth.users(id),
    edit_reason    TEXT,
    law_references JSONB,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (case_id, step_key)
);

-- 법령 개정 이력 및 알림 로그
CREATE TABLE IF NOT EXISTS law_alerts (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    law_name         TEXT NOT NULL,
    change_summary   TEXT,
    affected_steps   INTEGER[],
    file_uploaded_by UUID REFERENCES auth.users(id),
    email_sent       BOOLEAN DEFAULT false,
    email_sent_at    TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- 담당자 피드백 로그 (AI 결과 수정 이력)
CREATE TABLE IF NOT EXISTS feedback_logs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id       UUID REFERENCES cases(id),
    step_key      TEXT,
    ai_suggestion JSONB,
    final_value   JSONB,
    edit_reason   TEXT,
    user_id       UUID REFERENCES auth.users(id),
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 공통 인덱스
CREATE INDEX IF NOT EXISTS idx_cases_status        ON cases(status);
CREATE INDEX IF NOT EXISTS idx_cases_created_by    ON cases(created_by);
CREATE INDEX IF NOT EXISTS idx_pipeline_steps_case ON pipeline_steps(case_id);

-- 공통 updated_at 트리거
DROP TRIGGER IF EXISTS trg_cases_updated_at ON cases;
CREATE TRIGGER trg_cases_updated_at
    BEFORE UPDATE ON cases
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_pipeline_steps_updated_at ON pipeline_steps;
CREATE TRIGGER trg_pipeline_steps_updated_at
    BEFORE UPDATE ON pipeline_steps
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =============================================================
-- [F1] 수입 가능 여부 판정 — 담당: 병찬
-- ※ 아래 테이블 중 컬럼 정의가 TODO인 것은 병찬님이 채워주세요
-- =============================================================

CREATE TABLE IF NOT EXISTS f1_food_types (
    -- TODO: 병찬님이 컬럼 정의 추가
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS f1_allowed_ingredients (
    -- TODO: 병찬님이 컬럼 정의 추가
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS f1_additive_limits (
    -- TODO: 병찬님이 컬럼 정의 추가
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS f1_safety_standards (
    -- TODO: 병찬님이 컬럼 정의 추가
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS f1_regulations (
    -- TODO: 병찬님이 컬럼 정의 추가
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS f1_reviews (
    -- TODO: 병찬님이 컬럼 정의 추가
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS f1_allergens (
    -- TODO: 병찬님이 컬럼 정의 추가
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS f1_analytics_events (
    -- TODO: 병찬님이 컬럼 정의 추가
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS f1_escalation_logs (
    -- TODO: 병찬님이 컬럼 정의 추가
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS f1_flavor_codes (
    -- TODO: 병찬님이 컬럼 정의 추가
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS f1_ingredient_synonyms (
    -- TODO: 병찬님이 컬럼 정의 추가
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS f1_material_codes (
    -- TODO: 병찬님이 컬럼 정의 추가
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS f1_process_codes (
    -- TODO: 병찬님이 컬럼 정의 추가
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS f1_regulation_updates (
    -- TODO: 병찬님이 컬럼 정의 추가
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS f1_review_items (
    -- TODO: 병찬님이 컬럼 정의 추가
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- F1 updated_at 트리거 (병찬님 SQL editor 기준으로 복원)
DROP TRIGGER IF EXISTS trg_f1_food_types_updated_at ON f1_food_types;
CREATE TRIGGER trg_f1_food_types_updated_at
    BEFORE UPDATE ON f1_food_types
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_f1_allowed_ingredients_updated_at ON f1_allowed_ingredients;
CREATE TRIGGER trg_f1_allowed_ingredients_updated_at
    BEFORE UPDATE ON f1_allowed_ingredients
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_f1_additive_limits_updated_at ON f1_additive_limits;
CREATE TRIGGER trg_f1_additive_limits_updated_at
    BEFORE UPDATE ON f1_additive_limits
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_f1_safety_standards_updated_at ON f1_safety_standards;
CREATE TRIGGER trg_f1_safety_standards_updated_at
    BEFORE UPDATE ON f1_safety_standards
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_f1_regulations_updated_at ON f1_regulations;
CREATE TRIGGER trg_f1_regulations_updated_at
    BEFORE UPDATE ON f1_regulations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_f1_reviews_updated_at ON f1_reviews;
CREATE TRIGGER trg_f1_reviews_updated_at
    BEFORE UPDATE ON f1_reviews
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =============================================================
-- [F2] 식품유형 분류 — 담당: 아람
-- =============================================================

CREATE TABLE IF NOT EXISTS public.f2_required_documents (
    id              bigserial PRIMARY KEY,
    food_type       text NOT NULL,
    condition       text,
    doc_name        text NOT NULL,
    doc_description text,
    is_mandatory    boolean NOT NULL DEFAULT true,
    law_source      text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_f2_required_documents_food_type
    ON f2_required_documents(food_type);


-- =============================================================
-- [F3] 수입 필요서류 안내 — 추후 추가 예정
-- =============================================================

-- 담당 확정 후 f3_ prefix로 추가


-- =============================================================
-- [F4] 수출국표시사항 검토 — 담당: 성은
-- =============================================================

-- 법령 문서 메타데이터
CREATE TABLE IF NOT EXISTS f4_law_documents (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    law_name     TEXT NOT NULL,
    고시번호     TEXT,
    시행일       DATE,
    source_file  TEXT NOT NULL,
    법령_tier    INTEGER NOT NULL DEFAULT 4,   -- 1=법률 2=시행령 3=시행규칙 4=고시
    total_chunks INTEGER DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- 명시적 금지 표현 목록 (키워드 기반 1차 빠른 필터용)
CREATE TABLE IF NOT EXISTS f4_prohibited_expressions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    keyword         TEXT NOT NULL,
    category        TEXT NOT NULL CHECK (category IN (
                        '질병치료',
                        '허위과장',
                        '의약품오인',
                        '기능성'
                    )),
    severity        TEXT NOT NULL CHECK (severity IN ('must_fix', 'review_needed')),
    law_ref         TEXT NOT NULL,
    law_document_id UUID REFERENCES f4_law_documents(id),
    example         TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_f4_prohibited_keyword   ON f4_prohibited_expressions(keyword);
CREATE INDEX IF NOT EXISTS idx_f4_prohibited_category  ON f4_prohibited_expressions(category);
CREATE INDEX IF NOT EXISTS idx_f4_prohibited_severity  ON f4_prohibited_expressions(severity);


-- =============================================================
-- [F5] 한글표시사항 검토 및 시안 — 담당: 세연
-- ※ 세연님: 기존 테이블명에 f5_ prefix 추가 필요 (SQL Editor에서 실행)
--   ALTER TABLE label_rules          RENAME TO f5_label_rules;
--   ALTER TABLE allergy_list         RENAME TO f5_allergy_list;
--   ALTER TABLE additive_label_rules RENAME TO f5_additive_label_rules;
--   ALTER TABLE gmo_ingredients      RENAME TO f5_gmo_ingredients;
--   ALTER TABLE law_chunks           RENAME TO f5_law_chunks;
--   ALTER TABLE thresholds           RENAME TO f5_thresholds;
--   ALTER TABLE ingredient_list      RENAME TO f5_ingredient_list;
--   ALTER TABLE required_documents   RENAME TO f5_required_documents;
-- =============================================================

-- 원재료명 표기 규칙
CREATE TABLE IF NOT EXISTS f5_label_rules (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingredient_pattern TEXT,
    rule               TEXT NOT NULL,
    source             TEXT,
    food_type          TEXT DEFAULT 'all',
    created_by         UUID REFERENCES auth.users(id)
);

-- 14대 알레르기 유발 물질 목록
CREATE TABLE IF NOT EXISTS f5_allergy_list (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name_ko    TEXT NOT NULL,
    aliases    TEXT[],
    label_text TEXT,
    source     TEXT,
    created_by UUID REFERENCES auth.users(id)
);

-- 첨가물 표시 의무 규칙
CREATE TABLE IF NOT EXISTS f5_additive_label_rules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    additive_name   TEXT NOT NULL,
    mandatory_label TEXT NOT NULL,
    source          TEXT,
    created_by      UUID REFERENCES auth.users(id)
);

-- GMO 표시 의무 원료 목록
CREATE TABLE IF NOT EXISTS f5_gmo_ingredients (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name_ko       TEXT NOT NULL,
    threshold_pct NUMERIC DEFAULT 3,
    label_text    TEXT,
    source        TEXT,
    created_by    UUID REFERENCES auth.users(id)
);

-- 법령 텍스트 청크 (RAG용)
-- TODO: 세연님이 실제 컬럼 정의 확인 후 채워주세요
CREATE TABLE IF NOT EXISTS f5_law_chunks (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 기준규격 임계값
CREATE TABLE IF NOT EXISTS f5_thresholds (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingredient_name   TEXT NOT NULL,
    food_type         TEXT NOT NULL,
    threshold_value   NUMERIC NOT NULL,
    unit              TEXT NOT NULL,
    condition_text    TEXT,
    compound_group    TEXT,
    is_compound_limit BOOLEAN DEFAULT false,
    law_source        TEXT NOT NULL,
    law_article       TEXT,
    is_verified       BOOLEAN DEFAULT false,
    extracted_at      TIMESTAMPTZ DEFAULT NOW(),
    verified_by       UUID REFERENCES auth.users(id),
    verified_at       TIMESTAMPTZ,
    created_by        UUID REFERENCES auth.users(id)
);

-- 식품원료목록
CREATE TABLE IF NOT EXISTS f5_ingredient_list (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name_ko         TEXT NOT NULL,
    name_scientific TEXT,
    name_en         TEXT,
    ins_number      TEXT,
    cas_number      TEXT,
    aliases         TEXT[],
    usage_part      TEXT,
    usage_condition TEXT,
    is_allowed      BOOLEAN DEFAULT true,
    law_source      TEXT,
    created_by      UUID REFERENCES auth.users(id)
);

-- 수입 필요서류 목록
CREATE TABLE IF NOT EXISTS f5_required_documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    food_type       TEXT,
    condition       TEXT,
    doc_name        TEXT NOT NULL,
    doc_description TEXT,
    is_mandatory    BOOLEAN DEFAULT true,
    law_source      TEXT,
    created_by      UUID REFERENCES auth.users(id)
);

CREATE INDEX IF NOT EXISTS idx_f5_thresholds_ingredient ON f5_thresholds(ingredient_name, food_type);
CREATE INDEX IF NOT EXISTS idx_f5_thresholds_compound   ON f5_thresholds(compound_group) WHERE compound_group IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_f5_ingredient_list_name  ON f5_ingredient_list(name_ko);
CREATE INDEX IF NOT EXISTS idx_f5_ingredient_list_ins   ON f5_ingredient_list(ins_number) WHERE ins_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_f5_ingredient_list_cas   ON f5_ingredient_list(cas_number) WHERE cas_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_f5_required_docs_food    ON f5_required_documents(food_type);


-- =============================================================
-- 완료 확인
-- =============================================================
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
