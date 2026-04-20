-- ============================================================
-- migration 021: f1_forbidden_ingredients aliases 보강
-- 배경:
--   골든셋 v3 실측(2026-04-20) 결과 case_019(코카잎), case_020(THC) 실패.
--   - '코카잎' → DB의 '코카 잎'(공백 있음)과 부분일치 불가
--   - 'THC' alias 미등록 or 이전 운영 DB 동기화 누락
-- 수정:
--   1. '코카 잎' aliases에 '코카잎'(공백 없는 표기) 추가
--   2. '대마초' aliases에 'THC' 명시적 재등록 (011 미적용 환경 대비)
-- Idempotent: array_append 전 중복 검사 포함
-- ============================================================

-- 1. 코카잎 (공백 없는 표기) alias 추가
UPDATE f1_forbidden_ingredients
SET aliases = array_append(aliases, '코카잎')
WHERE name_ko = '코카 잎'
  AND NOT ('코카잎' = ANY(aliases));

-- 2. 대마초 — THC alias 재확인 (011 미적용 환경 대비 idempotent upsert)
UPDATE f1_forbidden_ingredients
SET aliases = ARRAY['대마', '마리화나', 'THC', 'CBD오일', '헴프시드오일']
WHERE name_ko = '대마초';

-- 검증:
-- SELECT name_ko, aliases FROM f1_forbidden_ingredients WHERE name_ko IN ('코카 잎', '대마초');
