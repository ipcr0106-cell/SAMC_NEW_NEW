-- =============================================================
-- 기능4: 수출국표시사항 검토 — Supabase 테이블
-- 실행: Supabase 대시보드 > SQL Editor 에서 실행
-- =============================================================

-- 법령 문서 메타데이터
CREATE TABLE IF NOT EXISTS f4_law_documents (
    id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    law_name                     TEXT NOT NULL,                        -- 법령명
    고시번호                     TEXT,                                 -- 예: 제2025-79호
    시행일                       DATE,                                 -- 예: 2025-12-04
    source_file                  TEXT NOT NULL,                        -- 원본 파일명
    법령_tier                    INTEGER NOT NULL DEFAULT 4,           -- 1=법률 2=시행령 3=시행규칙 4=고시
    total_chunks                 INTEGER DEFAULT 0,                    -- Pinecone에 적재된 청크 수
    prohibition_hint_patterns    TEXT[] DEFAULT '{}',                  -- 법령 고유 금지 마커 어구 (Claude 자동 추출)
    created_at                   TIMESTAMPTZ DEFAULT NOW()
);

-- [마이그레이션] 기존 테이블에 prohibition_hint_patterns 컬럼 추가
-- schema.sql 최초 실행이 아닌 경우 아래 ALTER TABLE을 SQL Editor에서 실행
ALTER TABLE f4_law_documents
    ADD COLUMN IF NOT EXISTS prohibition_hint_patterns TEXT[] DEFAULT '{}';

-- 명시적 금지 표현 목록 (키워드 기반 1차 빠른 필터용)
-- Claude 분석 전에 Supabase에서 먼저 매칭해 명백한 위반을 잡아냄
CREATE TABLE IF NOT EXISTS f4_prohibited_expressions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    keyword         TEXT NOT NULL,                        -- 금지 키워드 (예: "혈당 낮춤", "암 예방")
    category        TEXT NOT NULL,                        -- 위반 카테고리 (예: 질병치료, 허위과장, 의약품오인, 기능성, 비방광고 등 — 동적 확장 가능)
    severity        TEXT NOT NULL CHECK (severity IN ('must_fix', 'review_needed')),
    law_ref         TEXT NOT NULL,                        -- 근거 조문 (예: 제3조제1항제1호)
    law_document_id UUID REFERENCES f4_law_documents(id),
    example         TEXT,                                 -- 실제 위반 사례 문구
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prohibited_keyword  ON f4_prohibited_expressions(keyword);
CREATE INDEX IF NOT EXISTS idx_prohibited_category ON f4_prohibited_expressions(category);
CREATE INDEX IF NOT EXISTS idx_prohibited_severity ON f4_prohibited_expressions(severity);

-- 이미지 위반 유형 목록
CREATE TABLE IF NOT EXISTS f4_image_violation_types (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type_name          TEXT NOT NULL UNIQUE,                      -- 위반 유형명
    sub_items          TEXT NOT NULL DEFAULT '',                  -- 세부 항목 (쉼표 구분)
    default_severity   TEXT NOT NULL CHECK (default_severity IN ('must_fix', 'review_needed')) DEFAULT 'review_needed',
    severity_condition TEXT NOT NULL DEFAULT '',                  -- 심각도 판단 조건
    law_ref            TEXT NOT NULL DEFAULT '',                  -- 근거 조문
    source             TEXT NOT NULL CHECK (source IN ('seed', 'auto')) DEFAULT 'auto',
    source_law_name    TEXT,                                      -- 자동 추출 시 출처 법령명
    is_active          BOOLEAN NOT NULL DEFAULT TRUE,
    review_note        TEXT NOT NULL DEFAULT '',
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_image_violation_type_name   ON f4_image_violation_types(type_name);
CREATE INDEX IF NOT EXISTS idx_image_violation_source      ON f4_image_violation_types(source);
CREATE INDEX IF NOT EXISTS idx_image_violation_source_law  ON f4_image_violation_types(source_law_name);
CREATE INDEX IF NOT EXISTS idx_image_violation_is_active   ON f4_image_violation_types(is_active);

-- [마이그레이션] 기존 테이블에 source_law_name 컬럼 추가
-- schema.sql 최초 실행이 아닌 경우 아래 ALTER TABLE을 SQL Editor에서 실행
ALTER TABLE f4_image_violation_types
    ADD COLUMN IF NOT EXISTS source_law_name TEXT;
