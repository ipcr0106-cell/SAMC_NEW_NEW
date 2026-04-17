# F1 RAG Phase 2 — 복제 검증 리포트

## 메타

| 항목 | 값 |
|---|---|
| 실행일 | 2026-04-17 |
| 대상 | newsamc `samc-law` → SAMC `samc-law-f1` |
| 범위 | F1 관련 4개 namespace |
| 스크립트 | `backend/scripts/f1_replicate_from_newsamc.py --all` |

## 결과 요약

**전부 OK**. 484건 복제 + 미러 테이블 일치 + 샘플 메타 정상.

## 건수 비교 (source → target)

| namespace | newsamc samc-law | SAMC samc-law-f1 | Supabase f1_law_chunks | 일치 |
|---|---|---|---|---|
| food_code_text | 140 | 140 | 140 | ✅ |
| functional_labeling | 18 | 18 | 18 | ✅ |
| temporary_standard | 74 | 74 | 74 | ✅ |
| health_food_text | 252 | 252 | 252 | ✅ |
| **합계** | **484** | **484** | **484** | ✅ |

## newsamc metadata 스키마 발견

계획서 가정과 다름. 미러 매핑 시 `_build_mirror_row()`로 대응:

| F1 테이블 컬럼 | newsamc 실제 소스 |
|---|---|
| `regulation_id` | `metadata.label` → `source` → `section` (fallback 순) |
| `section_path` | `metadata.heading` → `section` |
| `token_count` | `metadata.tokens` (string → int) |
| `chunk_index` | vector_id 끝자리 숫자 (`_` 또는 `-` 구분자) |
| `total_chunks` | null (원본에 없음) |

### 특이사항: food_code_text만 다른 스키마

| namespace | metadata 키 | vector_id 패턴 |
|---|---|---|
| food_code_text | `namespace`, `section`, `source`, `text` | `fct-0`, `fct-1` |
| 나머지 3개 | `heading`, `label`, `source`, `text`, `tokens`, `type` | `{ns}_0000` |

→ 단일 `_build_mirror_row()` 함수가 양쪽 스키마 모두 처리 (값 없으면 fallback).

## 샘플 메타 매핑 (3건 랜덤 추출)

| vector_id | regulation_id | section_path | chunk_index | token_count |
|---|---|---|---|---|
| `temporary_standard_0001` | 한시적 기준 별표1 | 1. 제출자료의 범위 | 1 | 104 |
| `health_food_text_0145` | 건강기능식품공전 | 2. 기능성 원료 | 145 | 32 |
| `functional_labeling_0016` | 기능성표시 본문 | 7. 이상사례가 있는 경우 섭취를 중지하고 전문가와 상담이 필요하다는 문구 | 16 | 118 |
| `fct-0` (추가) | 식품공전 | 식품공전 | 0 | null |

## Pinecone 상태 (검증 시점)

```
=== samc-law-f1 ===
dimension       : 1536
metric          : cosine
total_vectors   : 484
index_fullness  : 0.0

=== namespaces ===
  food_code_text                    140
  functional_labeling                18
  health_food_text                  252
  temporary_standard                 74
```

## 누락/추가 작업 (Phase 3에서)

| 작업 | 상태 |
|---|---|
| `additive_code_text` namespace (식품첨가물공전) | 미적재 — Phase 3 신규 임베딩 |
| newsamc의 `packaging_text`(352), `labeling_standard`(93), `unfair_labeling`(13) | F1 무관 — 복제 제외 |

## 실행 로그 요약

```
=== [food_code_text] 수집 시작 ===
[food_code_text] 수집된 vector_id 수: 140
[food_code_text] 140/140 복제 완료

=== [functional_labeling] 수집 시작 ===
[functional_labeling] 18/18 복제 완료

=== [temporary_standard] 수집 시작 ===
[temporary_standard] 74/74 복제 완료

=== [health_food_text] 수집 시작 ===
[health_food_text] 252/252 복제 완료

=== 총 484건 처리 완료 (dry_run=False) ===
```

총 실행 시간: 약 3분 (네트워크 왕복 포함).

## 다음 단계

- Phase 3: 식품첨가물공전 신규 임베딩 (`additive_code_text` namespace)
- Phase 4-A/B: `f1_rag_judge` + 통합

## 재실행 명령

```bash
# 검증만 (idempotent)
F1_PINECONE_API_KEY=... SUPABASE_URL=... SUPABASE_SERVICE_KEY=... \
  python -m backend.scripts.f1_verify_replication

# 전체 복제 재실행 (upsert → idempotent)
F1_PINECONE_API_KEY=... SUPABASE_URL=... SUPABASE_SERVICE_KEY=... \
  python -m backend.scripts.f1_replicate_from_newsamc --all
```
