-- ============================================================
-- seed 08: f1_ingredient_synonyms — 원재료 이명(동의어) 초기 시드
-- prerequisite: 005_f1_ingredient_synonyms.sql (테이블 + 인덱스 생성)
-- ============================================================
-- 담당: 기능1 개발팀
-- 작성일: 2026-04-20
-- 출처: Wave 4 P4-a 골든셋 full 실패 케이스 19건 분석
--        (permitted_db 0/10, conditional_restricted_db 0/6, multi_ingredient_combo 0/3)
-- 참조: backend/tests/goldenset_f1_v3/WAVE4_P4A_REPORT.md
--
-- ─── 입력 가이드 (담당자 확장용) ───────────────────────────────
-- 컬럼 설명:
--   name_standard : data.go.kr 15111777 INGD_NM 과 일치하는 표준 한글명
--   name_variant  : 입력 문서에서 사용되는 이명/약칭/영문명/한자명
--   language      : 'ko'=한국어 이명, 'en'=영어, 'ja'=일본어, 'zh'=중국어, 'la'=학명
--
-- INSERT 패턴:
--   INSERT INTO f1_ingredient_synonyms (name_standard, name_variant, language)
--   VALUES ('표준명', '이명', 'en')
--   ON CONFLICT (name_standard, name_variant, language) DO NOTHING;
--
-- ※ ON CONFLICT DO NOTHING → 재실행 안전 (멱등성 보장)
-- ※ 추가 40~90건은 P4D_synonym_template.csv 를 통해 담당자가 입력
-- ───────────────────────────────────────────────────────────────

-- ─── 1. 대두 (soybean) ─────────────────────────────────────
-- 골든셋 permitted_db/multi_ingredient_combo 실패 주요 원인
INSERT INTO f1_ingredient_synonyms (name_standard, name_variant, language)
VALUES ('대두', 'soybean', 'en')
ON CONFLICT (name_standard, name_variant, language) DO NOTHING;

INSERT INTO f1_ingredient_synonyms (name_standard, name_variant, language)
VALUES ('대두', 'soy', 'en')
ON CONFLICT (name_standard, name_variant, language) DO NOTHING;

INSERT INTO f1_ingredient_synonyms (name_standard, name_variant, language)
VALUES ('대두', '黄大豆', 'zh')
ON CONFLICT (name_standard, name_variant, language) DO NOTHING;

-- ─── 2. 밀가루 (wheat flour) ──────────────────────────────
INSERT INTO f1_ingredient_synonyms (name_standard, name_variant, language)
VALUES ('밀가루', 'wheat flour', 'en')
ON CONFLICT (name_standard, name_variant, language) DO NOTHING;

INSERT INTO f1_ingredient_synonyms (name_standard, name_variant, language)
VALUES ('밀가루', '小麦粉', 'zh')
ON CONFLICT (name_standard, name_variant, language) DO NOTHING;

-- ─── 3. 쌀 (rice) ────────────────────────────────────────
-- multi_ingredient_combo 케이스에서 'rice' 표기로 unidentified 발생 추정
INSERT INTO f1_ingredient_synonyms (name_standard, name_variant, language)
VALUES ('쌀', 'rice', 'en')
ON CONFLICT (name_standard, name_variant, language) DO NOTHING;

INSERT INTO f1_ingredient_synonyms (name_standard, name_variant, language)
VALUES ('쌀', '米', 'zh')
ON CONFLICT (name_standard, name_variant, language) DO NOTHING;

-- ─── 4. 포도당 (glucose / dextrose) ──────────────────────
-- conditional_restricted_db 케이스 — 영문 표기 혼용
INSERT INTO f1_ingredient_synonyms (name_standard, name_variant, language)
VALUES ('포도당', 'glucose', 'en')
ON CONFLICT (name_standard, name_variant, language) DO NOTHING;

INSERT INTO f1_ingredient_synonyms (name_standard, name_variant, language)
VALUES ('포도당', 'dextrose', 'en')
ON CONFLICT (name_standard, name_variant, language) DO NOTHING;

-- ─── 5. 구연산 (citric acid) ──────────────────────────────
-- 식품첨가물 표기 혼용 — permitted_db/conditional_restricted_db 영향
INSERT INTO f1_ingredient_synonyms (name_standard, name_variant, language)
VALUES ('구연산', 'citric acid', 'en')
ON CONFLICT (name_standard, name_variant, language) DO NOTHING;

-- ─── 6. 옥수수전분 (corn starch) ─────────────────────────
-- multi_ingredient_combo 복합원료 내 영문 표기
INSERT INTO f1_ingredient_synonyms (name_standard, name_variant, language)
VALUES ('옥수수전분', 'corn starch', 'en')
ON CONFLICT (name_standard, name_variant, language) DO NOTHING;

INSERT INTO f1_ingredient_synonyms (name_standard, name_variant, language)
VALUES ('옥수수전분', 'cornstarch', 'en')
ON CONFLICT (name_standard, name_variant, language) DO NOTHING;

-- ─── 7. 설탕 (sugar) ─────────────────────────────────────
INSERT INTO f1_ingredient_synonyms (name_standard, name_variant, language)
VALUES ('설탕', 'sugar', 'en')
ON CONFLICT (name_standard, name_variant, language) DO NOTHING;

-- ─── 8. 소금 (salt) ──────────────────────────────────────
INSERT INTO f1_ingredient_synonyms (name_standard, name_variant, language)
VALUES ('소금', 'salt', 'en')
ON CONFLICT (name_standard, name_variant, language) DO NOTHING;

-- ─── 9. 식용유 (edible oil / vegetable oil) ───────────────
-- permitted_db 케이스 — 수입 제품 라벨 영문 표기 다양
INSERT INTO f1_ingredient_synonyms (name_standard, name_variant, language)
VALUES ('식용유', 'edible oil', 'en')
ON CONFLICT (name_standard, name_variant, language) DO NOTHING;

INSERT INTO f1_ingredient_synonyms (name_standard, name_variant, language)
VALUES ('식용유', 'vegetable oil', 'en')
ON CONFLICT (name_standard, name_variant, language) DO NOTHING;

-- ─── 10. 정제수 (purified water / water) ─────────────────
-- 수입 가공식품 원재료 목록 최빈 표기
INSERT INTO f1_ingredient_synonyms (name_standard, name_variant, language)
VALUES ('정제수', 'purified water', 'en')
ON CONFLICT (name_standard, name_variant, language) DO NOTHING;

INSERT INTO f1_ingredient_synonyms (name_standard, name_variant, language)
VALUES ('정제수', 'water', 'en')
ON CONFLICT (name_standard, name_variant, language) DO NOTHING;

-- ─── END OF SEED 08 ───────────────────────────────────────
-- 다음 단계: 담당자가 P4D_synonym_template.csv 입력 → 09_f1_ingredient_synonyms_ext.sql 생성
-- 목표: 총 50~100건으로 확장하여 골든셋 permitted_db ≥ 80% 달성
