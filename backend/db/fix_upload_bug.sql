-- =============================================================
-- SAMC 업로드 버그 수정 SQL
-- 실행: Supabase 대시보드 > SQL Editor 에서 실행
-- 날짜: 2026-04-14
-- =============================================================

-- 1) documents 테이블 doc_type CHECK 제약조건 수정
--    기존: 'label' 누락 → 라벨 사진 업로드 시 DB INSERT 실패
--    수정: 'label' 추가
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_doc_type_check;
ALTER TABLE documents ADD CONSTRAINT documents_doc_type_check
    CHECK (doc_type IN ('ingredients', 'process', 'msds', 'material', 'label', 'other'));

-- 2) Storage 버킷 생성 (이미 있으면 무시됨)
INSERT INTO storage.buckets (id, name, public)
VALUES ('documents', 'documents', false)
ON CONFLICT (id) DO NOTHING;

-- 3) Storage 정책: service_role은 모든 작업 허용
--    (service_role key 사용 시 기본 허용이지만, 명시적으로 추가)
CREATE POLICY IF NOT EXISTS "service_role_all_documents"
ON storage.objects FOR ALL
TO service_role
USING (bucket_id = 'documents')
WITH CHECK (bucket_id = 'documents');

-- 4) 확인
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'documents'::regclass AND contype = 'c';
