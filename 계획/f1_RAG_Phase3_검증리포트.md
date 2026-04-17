# F1 RAG Phase 3 — 식품첨가물공전 임베딩 검증 리포트

## 메타

| 항목 | 값 |
|---|---|
| 실행일 | 2026-04-17 |
| 대상 | 식품첨가물공전 6개 마크다운 파일 |
| 입력 경로 | `C:/Users/user/Desktop/식품공전_마크다운_전체_7/식품첨가물공전/` |
| namespace | `additive_code_text` (신규) |
| 임베딩 모델 | OpenAI `text-embedding-3-small` (1536d) |

## 결과 요약

**전부 OK**. 1664건 임베딩 + Pinecone upsert + Supabase 미러 일치.

## 파일별 청크

| # | 파일 | regulation_id | id_prefix | 청크 |
|---|---|---|---|---|
| 1 | I 총칙 + II 일반기준 + III 사용기준 | 식품첨가물공전 I-III | additive_general | 157 |
| 2 | IV 품목별 성분규격 | 식품첨가물공전 IV 품목별 성분규격 | additive_spec | 1122 |
| 3 | V 일반시험법 + VI 시약 + VII 재검토 | 식품첨가물공전 V-VII | additive_testmethod | 160 |
| 4 | 별표1 향료 목록 | 식품첨가물공전 별표1 향료 | additive_flavor | 136 |
| 5 | 별표2/3/4 | 식품첨가물공전 별표2-4 | additive_misc | 37 |
| 6 | 일람표 | 식품첨가물공전 일람표 | additive_history | 52 |
| **계** | | | | **1664** |

## 토큰 분포

| 지표 | 값 |
|---|---|
| min | 8 |
| max | 1501 (거의 경계) |
| mean | 1025 |
| median | 1103 |
| oversize (>1500) | 1 (무시 가능) |
| undersize (<200) | 89 (소형 병합 로직 한계) |

## 청킹 특이사항 (버그 수정 반영)

식품첨가물공전은 `### 제N조` 헤딩이 거의 없어 newsamc 청킹의 **폴백 경로**(빈 줄 분할 + 항/호 분할 + 슬라이딩)를 전면 사용.

**발견된 버그**: `_split_large_chunk`가 항/호 경계로 분할 후 각 part가 여전히 MAX 초과여도 그대로 반환 → 19366 토큰 청크 발생. **재귀 분할 로직 추가**로 해결 (커밋에 포함).

## Pinecone 제약 대응

Pinecone Vector ID는 **ASCII-only**. 한글 regulation_id(`식품첨가물공전 I-III`)를 그대로 vector_id에 쓰면 400 에러.

**해결**: `attach_metadata(chunks, regulation_id, namespace, id_prefix=...)`에 ASCII `id_prefix` 인자 추가. metadata.regulation_id는 한글 유지(검색 품질), vector_id만 ASCII prefix 사용.

매핑:
```
"식품첨가물공전 I-III"         → id_prefix="additive_general"
"식품첨가물공전 IV 품목별..."  → id_prefix="additive_spec"
...
```

## 최종 상태 (Pinecone samc-law-f1)

```
dimension       : 1536
metric          : cosine
total_vectors   : 2148

=== namespaces ===
  additive_code_text               1664    ← Phase 3 신규
  food_code_text                    140
  functional_labeling                18
  health_food_text                  252
  temporary_standard                 74
```

## Supabase 미러 (f1_law_chunks)

| namespace | mirror | Pinecone | 일치 |
|---|---|---|---|
| food_code_text | 140 | 140 | ✅ |
| additive_code_text | 1664 | 1664 | ✅ |
| functional_labeling | 18 | 18 | ✅ |
| temporary_standard | 74 | 74 | ✅ |
| health_food_text | 252 | 252 | ✅ |
| **합계** | **2148** | **2148** | ✅ |

## 샘플 검증

| vector_id | regulation_id | section_path |
|---|---|---|
| additive_general_0000 | 식품첨가물공전 I-III | section_0_part0 |
| additive_general_0001 | 식품첨가물공전 I-III | section_0_part1 |
| additive_general_0002 | 식품첨가물공전 I-III | section_0_part2_window0 |

`section_path` 형식이 `section_N_partM_windowK`로 **원본 위치 추적 가능** — 재임베딩/삭제 시 활용.

## 비용

| 항목 | 값 |
|---|---|
| 처리 토큰 | ~1.7M |
| OpenAI 임베딩 | ~$0.034 (약 50원) |
| 실행 시간 | 약 2분 |
| Pinecone upsert | 비용 없음 |
| Supabase upsert | 비용 없음 |

## 다음 단계

- Phase 4-A: `f1_rag_judge.py` + Pydantic 모델 (RAG 판정 모듈)
- Phase 4-B: `feature1.py` 통합 + HITL + law_extractor 제거 + 골든셋 30건

## 재실행 명령

```bash
# 전체 재임베딩 (upsert → idempotent)
F1_OPENAI_API_KEY=... F1_PINECONE_API_KEY=... SUPABASE_URL=... SUPABASE_SERVICE_KEY=... \
  python -m backend.scripts.f1_embed_additive_code \
    --dir "C:/Users/user/Desktop/식품공전_마크다운_전체_7/식품첨가물공전"

# 특정 파일만 재처리
... --files "<path1>" "<path2>"

# dry-run (토큰 분포만)
... --dir ... --dry-run
```
