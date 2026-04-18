# F1 스켈레톤 10개 정리 제안서 (B안)

- **작성일**: 2026-04-18
- **작성자**: 조사 — Claude / 확정 — 병찬·성은
- **상태**: 🟡 **제안 (팀 리뷰 전)**
- **출처**:
  - `newsamc/scripts/create-tables.sql` (실제 SQL)
  - `newsamc/docs/설계/구현계획/00_DB_스키마_테이블정의.md` (설계 의도)
  - SAMC `backend/db/combined_schema.sql` L16~34 (공통 테이블 규약)

---

## 1. 배경

`backend/db/combined_schema.sql` L148~242에는 F1용 테이블 스켈레톤 10개가 `id + created_at`만 존재하는 미완 상태로 선언되어 있습니다. 이 테이블들의 컬럼 정의 원본을 `newsamc` 리포지토리에서 발견했습니다. 그러나 newsamc를 그대로 복사하면 SAMC의 공통 파이프라인(`cases` / `pipeline_steps` / `law_alerts`)과 **구조적으로 충돌**합니다.

본 문서는 10개 테이블을 **🟢 정의 / 🟡 조정 / 🔴 폐기** 세 그룹으로 분류하고, 각 그룹별 실행안을 제시합니다.

---

## 2. 결론 요약

| 처리 | 테이블 수 | 조치 |
|---|---|---|
| 🟢 **정의 (그대로 정리)** | 5개 | 새 migration 작성 (`014~018`) |
| 🟡 **조정 (FK·용도 변경)** | 2개 | 새 migration 작성 + 역할 재정의 |
| 🔴 **폐기 (공통 테이블로 흡수)** | 3개 | DROP TABLE migration + 코드에서 `cases`/`pipeline_steps`/`law_alerts` 사용 전환 |
| **합계** | **10개** | — |

---

## 3. 🟢 정의 — 5개 (바로 정리 가능)

공통 파이프라인과 충돌 없음. newsamc 구조를 SAMC 팀 컨벤션(VARCHAR→TEXT, 컬럼 prefix `f1_`)에 맞춰 반영.

### 3.1 `f1_food_types` — 식품유형 마스터

**newsamc 출처**: `scripts/create-tables.sql` L10~23

```sql
-- 제안: backend/db/migrations/014_f1_food_types.sql
ALTER TABLE f1_food_types
  ADD COLUMN IF NOT EXISTS code           TEXT,
  ADD COLUMN IF NOT EXISTS name           TEXT,
  ADD COLUMN IF NOT EXISTS parent_id      UUID REFERENCES f1_food_types(id),
  ADD COLUMN IF NOT EXISTS depth          INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS definition     TEXT,
  ADD COLUMN IF NOT EXISTS key_processes  TEXT,
  ADD COLUMN IF NOT EXISTS regulation_ref TEXT,
  ADD COLUMN IF NOT EXISTS is_verified    BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS law_source     TEXT,
  ADD COLUMN IF NOT EXISTS created_by     UUID REFERENCES auth.users(id);

ALTER TABLE f1_food_types
  ALTER COLUMN code SET NOT NULL,
  ALTER COLUMN name SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_f1_food_types_code ON f1_food_types(code);
CREATE INDEX IF NOT EXISTS idx_f1_food_types_parent ON f1_food_types(parent_id);
```

**특징**: 자기참조 계층 (parent_id). newsamc seed 361건 이관 가능.
**주의**: 기존 F1 테이블(`f1_additive_limits`, `f1_safety_standards`)은 `food_type TEXT`를 쓰므로, 이 테이블 도입 시 FK로 전환할지 **별도 결정 필요** (§6 참조).

---

### 3.2 `f1_allergens` — 알레르겐 마스터

**newsamc 출처**: L92~99

```sql
-- 제안: backend/db/migrations/015_f1_allergens.sql
ALTER TABLE f1_allergens
  ADD COLUMN IF NOT EXISTS name_ko      TEXT,
  ADD COLUMN IF NOT EXISTS name_en      TEXT,
  ADD COLUMN IF NOT EXISTS display_text TEXT,
  ADD COLUMN IF NOT EXISTS is_mandatory BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS is_verified  BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS law_source   TEXT,
  ADD COLUMN IF NOT EXISTS created_by   UUID REFERENCES auth.users(id);

ALTER TABLE f1_allergens
  ALTER COLUMN name_ko SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_f1_allergens_name_ko ON f1_allergens(name_ko);
```

**F5와의 구분**: `f5_allergy_list`는 **한글표시사항 라벨 텍스트**가 목적(`label_text` 컬럼), `f1_allergens`는 **원재료 검증 단계**에서 알레르겐 포함 여부를 판단하는 것이 목적. 역할 분리 명확.
**newsamc seed**: 22건.

---

### 3.3 `f1_process_codes` — 제조공정 코드

**newsamc 출처**: L102~108

```sql
-- 제안: backend/db/migrations/016_f1_process_codes.sql
ALTER TABLE f1_process_codes
  ADD COLUMN IF NOT EXISTS code        TEXT,
  ADD COLUMN IF NOT EXISTS name_ko     TEXT,
  ADD COLUMN IF NOT EXISTS synonyms    TEXT,
  ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS law_source  TEXT,
  ADD COLUMN IF NOT EXISTS created_by  UUID REFERENCES auth.users(id);

ALTER TABLE f1_process_codes
  ALTER COLUMN code SET NOT NULL,
  ALTER COLUMN name_ko SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_f1_process_codes_code ON f1_process_codes(code);
```

**newsamc seed**: 25건.

---

### 3.4 `f1_material_codes` — 물질/재질 코드

**newsamc 출처**: L111~119

```sql
-- 제안: backend/db/migrations/017_f1_material_codes.sql
ALTER TABLE f1_material_codes
  ADD COLUMN IF NOT EXISTS code        TEXT,
  ADD COLUMN IF NOT EXISTS name_ko     TEXT,
  ADD COLUMN IF NOT EXISTS name_en     TEXT,
  ADD COLUMN IF NOT EXISTS category    TEXT,
  ADD COLUMN IF NOT EXISTS synonyms    TEXT,
  ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS law_source  TEXT,
  ADD COLUMN IF NOT EXISTS created_by  UUID REFERENCES auth.users(id);

ALTER TABLE f1_material_codes
  ALTER COLUMN code SET NOT NULL,
  ALTER COLUMN name_ko SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_f1_material_codes_code ON f1_material_codes(code);
CREATE INDEX IF NOT EXISTS idx_f1_material_codes_category ON f1_material_codes(category);
```

---

### 3.5 `f1_flavor_codes` — 향료 코드 (식품첨가물공전 별표1)

**newsamc 출처**: L221~230

```sql
-- 제안: backend/db/migrations/018_f1_flavor_codes.sql
ALTER TABLE f1_flavor_codes
  ADD COLUMN IF NOT EXISTS code           TEXT,
  ADD COLUMN IF NOT EXISTS name_ko        TEXT,
  ADD COLUMN IF NOT EXISTS name_en        TEXT,
  ADD COLUMN IF NOT EXISTS category       TEXT,
  ADD COLUMN IF NOT EXISTS cas_number     TEXT,
  ADD COLUMN IF NOT EXISTS regulation_ref TEXT,
  ADD COLUMN IF NOT EXISTS is_verified    BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS law_source     TEXT,
  ADD COLUMN IF NOT EXISTS created_by     UUID REFERENCES auth.users(id);

ALTER TABLE f1_flavor_codes
  ALTER COLUMN code SET NOT NULL,
  ALTER COLUMN name_ko SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname='f1_flavor_codes_category_check') THEN
    ALTER TABLE f1_flavor_codes
      ADD CONSTRAINT f1_flavor_codes_category_check
      CHECK (category IN ('natural', 'synthetic'));
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_f1_flavor_codes_code ON f1_flavor_codes(code);
CREATE INDEX IF NOT EXISTS idx_f1_flavor_codes_category ON f1_flavor_codes(category);
CREATE INDEX IF NOT EXISTS idx_f1_flavor_codes_cas
  ON f1_flavor_codes(cas_number) WHERE cas_number IS NOT NULL;
```

**용도**: `f1_escalation_logs.trigger_type = 'synthetic_flavor'` 판정 시 참조.

---

## 4. 🟡 조정 — 2개 (FK·역할 재정의)

### 4.1 `f1_analytics_events` — FK 재지정

**newsamc 원본**:
```sql
review_id  UUID REFERENCES reviews(id),  -- SAMC에 reviews 없음
```

**SAMC 조정안**:
```sql
-- 제안: backend/db/migrations/019_f1_analytics_events.sql
ALTER TABLE f1_analytics_events
  ADD COLUMN IF NOT EXISTS case_id     UUID REFERENCES cases(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS module_id   TEXT NOT NULL DEFAULT 'F1',
  ADD COLUMN IF NOT EXISTS event_type  TEXT,
  ADD COLUMN IF NOT EXISTS duration_ms INTEGER,
  ADD COLUMN IF NOT EXISTS metadata    JSONB;

ALTER TABLE f1_analytics_events
  ALTER COLUMN event_type SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_f1_analytics_case ON f1_analytics_events(case_id);
CREATE INDEX IF NOT EXISTS idx_f1_analytics_type ON f1_analytics_events(event_type);
```

**역할 분리 (feedback_logs vs analytics_events)**:
- `feedback_logs`: 담당자 수정 이력 (**비즈니스 감사 로그**)
- `f1_analytics_events`: 성능 측정 이벤트 (**엔지니어링 지표**) — duration_ms, API 호출 횟수 등

---

### 4.2 `f1_regulations` — 법령 마스터로 재정의

**newsamc 원본**: 법령 메타데이터(title/legal_level/effective_date) 저장.

**SAMC 현황 문제**:
- `f1_law_chunks.regulation_id`가 TEXT — 참조 무결성 없음
- `law_alerts`는 개정 이력이지 "마스터"가 아님
- 법령 검색·갱신 시 정규화된 메타데이터 테이블 없음

**조정안**:
```sql
-- 제안: backend/db/migrations/020_f1_regulations.sql
ALTER TABLE f1_regulations
  ADD COLUMN IF NOT EXISTS title              TEXT,
  ADD COLUMN IF NOT EXISTS reg_type           TEXT,
  ADD COLUMN IF NOT EXISTS legal_level        TEXT,
  ADD COLUMN IF NOT EXISTS effective_date     DATE,
  ADD COLUMN IF NOT EXISTS pinecone_namespace TEXT,
  ADD COLUMN IF NOT EXISTS is_current         BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS is_verified        BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS law_source         TEXT,
  ADD COLUMN IF NOT EXISTS created_by         UUID REFERENCES auth.users(id);

ALTER TABLE f1_regulations
  ALTER COLUMN title SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname='f1_regulations_legal_level_check') THEN
    ALTER TABLE f1_regulations
      ADD CONSTRAINT f1_regulations_legal_level_check
      CHECK (legal_level IN ('law', 'decree', 'rule', 'notification', 'individual'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_f1_regulations_pinecone
  ON f1_regulations(pinecone_namespace) WHERE pinecone_namespace IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_f1_regulations_current
  ON f1_regulations(is_current) WHERE is_current = true;
```

**연계 작업 (선택)**: `f1_law_chunks.regulation_id`를 `TEXT → UUID REFERENCES f1_regulations(id)`로 승격. 기존 데이터 매핑 필요하므로 후속 마이그레이션으로 분리.

---

## 5. 🔴 폐기 권고 — 3개 (공통 테이블로 흡수)

**이 3개는 병찬·성은 합의 없이 DROP 금지.** 폐기 전 참조하는 코드 전수 조사 필요.

### 5.1 `f1_reviews` → `cases`로 흡수

**근거**:
- `combined_schema.sql` L21~25: "각 기능에서 결과를 저장할 때 pipeline_steps 테이블에 INSERT/UPDATE 하세요"
- `cases` 테이블이 이미 `product_name`, `importer_name`, `status`, `current_step` 제공 — newsamc `reviews`의 대부분 필드 커버
- F1이 `f1_reviews`에 쓰면 F2·F4·F5와 **데이터 연동 끊김**

**newsamc `reviews` 컬럼 매핑**:

| newsamc.reviews | SAMC 대체 |
|---|---|
| `product_name` | `cases.product_name` ✓ |
| `brand` | `cases`에 없음 → **추가 필요** (팀 합의) 또는 `documents.parsed_md`에서 추출 |
| `export_country` | `cases`에 없음 → **추가 필요** (팀 합의) |
| `food_type_id` | `pipeline_steps` (step_key='2', F2 결과) 에 이미 저장 |
| `status` | `cases.status` ✓ (ENUM 값 조정 필요) |
| `reviewer_id`, `approver_id` | `cases.created_by`, `pipeline_steps.edited_by` ✓ |
| `ai_results JSONB` | `pipeline_steps.ai_result` ✓ |
| `reviewer_comment`, `approver_comment` | `pipeline_steps.edit_reason`, `feedback_logs` ✓ |

**마이그레이션**:
```sql
-- 제안: backend/db/migrations/021_f1_reviews_drop.sql
-- 선행: f1_reviews 참조 코드 전수 제거 확인
-- cases에 brand, export_country 컬럼 추가 (공통 변경 — 성은 승인)
ALTER TABLE cases
  ADD COLUMN IF NOT EXISTS brand          TEXT,
  ADD COLUMN IF NOT EXISTS export_country TEXT;

-- f1_reviews 폐기
DROP TABLE IF EXISTS f1_reviews CASCADE;
```

---

### 5.2 `f1_review_items` → `pipeline_steps`로 흡수 (또는 유지·재정의)

**옵션 A — 폐기 (권고)**:
- newsamc `review_items`의 `module_id`/`judgment`/`confidence_score`/`details JSONB`는 `pipeline_steps.step_key`/`pipeline_steps.ai_result`로 대체 가능
- F1 sub-step (Step 0/1/2/3/4/5)은 `ai_result JSONB` 내부 필드로 표현

**옵션 B — 재정의 (F1 세부 판정 로그 전용)**:
- 유지하되 `f1_reviews` 의존 제거, `case_id → cases` FK로 재연결
- F1 내부의 **5단계 매칭 과정**(N1~N14 각 단계 결과)을 행 단위로 저장
- 장점: 디버깅 시 단계별 추적 가능
- 단점: `pipeline_steps.ai_result`와 일부 중복

**추천**: **옵션 A (폐기)**. 이유 — F1의 5단계 판정은 이미 `ai_result JSONB`에 구조화 저장하는 게 자연스럽고, 별도 테이블로 뽑으면 조인 비용 증가.

```sql
-- 제안: backend/db/migrations/022_f1_review_items_drop.sql
DROP TABLE IF EXISTS f1_review_items CASCADE;
```

---

### 5.3 `f1_regulation_updates` → `law_alerts`로 흡수

**근거**:
- `law_alerts`가 이미 `law_name`, `change_summary`, `email_sent`, `email_sent_at` 제공
- newsamc `regulation_updates`의 `detected_at`/`notified`/`applied_at`은 `law_alerts`의 기능 셋 안에 포함
- F1 전용 필드가 없음 → 공통 테이블로 충분

**마이그레이션**:
```sql
-- 제안: backend/db/migrations/023_f1_regulation_updates_drop.sql
-- law_alerts에 applied_at 컬럼 추가 (공통 변경 — 성은 승인)
ALTER TABLE law_alerts
  ADD COLUMN IF NOT EXISTS applied_at TIMESTAMPTZ;

-- f1_regulation_updates 폐기
DROP TABLE IF EXISTS f1_regulation_updates CASCADE;
```

---

## 6. 부수 결정 필요 — `food_type TEXT` vs `food_type_id UUID FK`

`f1_food_types` 도입 시 기존 F1 테이블의 `food_type TEXT` 컬럼과 관계 조정이 필요합니다.

**영향 받는 테이블**:
- `f1_additive_limits.food_type TEXT` (migration 003)
- `f1_safety_standards.food_type TEXT` (migration 004)

**옵션**:

| 옵션 | 장점 | 단점 |
|---|---|---|
| A. TEXT 유지 | 기존 seed 데이터·코드 무변경 | 참조 무결성 없음, 오타 감수 |
| B. FK로 전환 | 정합성 보장, JOIN 용이 | 기존 데이터 매핑 마이그레이션 필요, 코드 수정 |
| C. 병행 (TEXT + food_type_id NULL) | 점진적 전환 가능 | 복잡도 증가, 일관성 깨짐 |

**추천**: **B (FK 전환)** — 단, 별도 후속 마이그레이션으로 분리. 본 제안서의 `f1_food_types` 도입 후 seed 이관이 끝난 다음 진행.

---

## 7. 실행 순서 (승인 후)

```
[승인 단계]
1. 병찬: f1_reviews/f1_review_items/f1_regulation_updates 폐기 동의
2. 성은: cases.brand/export_country 추가, law_alerts.applied_at 추가 동의
3. 병찬: food_type FK 전환 방침 결정

[마이그레이션 적용 — 순서 중요]
014_f1_food_types.sql          🟢
015_f1_allergens.sql           🟢
016_f1_process_codes.sql       🟢
017_f1_material_codes.sql      🟢
018_f1_flavor_codes.sql        🟢
019_f1_analytics_events.sql    🟡
020_f1_regulations.sql         🟡
021_f1_reviews_drop.sql        🔴 (cases 공통 변경 포함)
022_f1_review_items_drop.sql   🔴
023_f1_regulation_updates_drop.sql 🔴 (law_alerts 공통 변경 포함)

[seed 이관 — newsamc → SAMC]
24_f1_food_types.sql        (newsamc 01_food_types.sql 기반, 361건)
25_f1_allergens.sql         (newsamc 02_allergens.sql 기반, 22건)
26_f1_process_codes.sql     (newsamc 04_process_codes.sql 기반, 25건)
27_f1_regulations.sql       (newsamc 03_regulations.sql 기반, 5건)

[후속 (별도 의사결정)]
□ food_type TEXT → food_type_id FK 전환
□ f1_law_chunks.regulation_id TEXT → UUID FK 승격
```

---

## 8. 리스크 평가

| 리스크 | 확률 | 영향 | 완화책 |
|---|---|---|---|
| F1 코드가 이미 `f1_reviews` 사용 중 | 낮음 (컬럼 없어서 쓸 수 없음) | 중 | 전수 grep 확인 |
| `cases` 공통 변경에 다른 기능 영향 | 낮음 | 높음 | `ADD COLUMN + DEFAULT NULL` 비파괴 변경 |
| newsamc seed 데이터가 SAMC 법령 기준과 불일치 | 중 | 중 | `is_verified=false`로 import, 담당자 승인 후 true 승격 |
| `f1_food_types` 도입 후 기존 `food_type TEXT`와 혼재 | 중 | 중 | §6 후속 마이그레이션에서 일괄 전환 |

---

## 9. 확인 체크리스트 (팀 리뷰용)

- [ ] **병찬**: `f1_reviews` 폐기 동의 (cases + pipeline_steps로 대체)
- [ ] **병찬**: `f1_review_items` 폐기 동의 (ai_result JSONB 내부 저장으로 충분)
- [ ] **병찬**: `f1_regulation_updates` 폐기 동의 (law_alerts 사용)
- [ ] **성은**: `cases.brand`, `cases.export_country` 추가 승인
- [ ] **성은**: `law_alerts.applied_at` 추가 승인
- [ ] **병찬**: `food_type` FK 전환 방침 결정 (§6)
- [ ] **병찬**: 5개 신규 마스터 테이블 컬럼 설계안 검토

---

## 10. 관련 문서

- [schema_overview.md](schema_overview.md) — 현재 전체 스키마 ER 다이어그램
- `newsamc/scripts/create-tables.sql` — 원본 컬럼 정의
- `newsamc/docs/설계/구현계획/00_DB_스키마_테이블정의.md` — 설계 의도·배경
- `backend/db/combined_schema.sql` L148~242 — 현재 F1 스켈레톤
