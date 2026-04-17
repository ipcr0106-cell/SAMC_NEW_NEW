# F2 → f0 데이터 연결 확인 요청

> 작성: 아람 (F2 식품유형 분류)
> 작성일: 2026-04-17

---

## 1. F2 현재 데이터 상황 (참고용)

| 항목 | 상태 |
|------|------|
| `f2_food_type_classification` (Supabase) | ✅ 235행 적재 완료 |
| `f2_required_documents` (Supabase) | ✅ 70행 적재 완료 |
| `pipeline_steps` 테이블 | ✅ 존재 확인 |
| Pinecone `samc-a` 인덱스 | 별도 확인 중 |

F2 자체 데이터는 준비 완료 상태입니다.

---

## 2. F2가 f0에서 읽는 데이터 명세

F2 `/feature/2/run` 실행 시 아래 두 곳에서 데이터를 읽습니다.

### 2-1. `pipeline_steps` 테이블 (step_key = `'0'`)

`ai_result` 컬럼의 JSON 구조 중 F2가 사용하는 필드:

```json
{
  "basic_info": {
    "product_name": "제품명",
    "export_country": "수출국"
  },
  "ingredients": [
    {
      "name": "원재료명",
      "ratio": "함량 (숫자 또는 문자열)"
    }
  ],
  "process_info": {
    "process_codes": ["공정코드1", "공정코드2"],
    "raw_process_text": "공정 원문 텍스트"
  }
}
```

**확인 요청:**
- [ ] `basic_info.product_name` / `basic_info.export_country` 키명이 위와 동일한지
- [ ] `ingredients[].name` / `ingredients[].ratio` 키명이 위와 동일한지
- [ ] `process_info.process_codes` (배열) / `process_info.raw_process_text` (문자열) 저장 여부
- [ ] `status = 'completed'`일 때만 F2가 읽으므로, f0 완료 처리 시 status를 `'completed'`로 저장하는지

### 2-2. `documents` 테이블 (fallback용)

f0의 `pipeline_steps` 결과가 없을 경우, 아래 조건으로 OCR 텍스트를 직접 읽습니다:

```
documents.case_id = {case_id}
documents.doc_type = 'ingredients'   ← 이 값이 정확히 'ingredients'인지 확인 필요
documents.parsed_md (not null)
```

**확인 요청:**
- [ ] 원재료 배합비 서류 업로드 시 `doc_type` 값으로 정확히 `'ingredients'`를 저장하는지
- [ ] `parsed_md`에 OCR 추출 텍스트가 저장되는 시점 (파싱 완료 후 즉시? 담당자 확인 후?)

---

## 3. F2 실행 흐름 요약

```
f0 완료 (step_key='0', status='completed')
    ↓
F2 /run 호출
    ↓
pipeline_steps(step_key='0').ai_result 읽기
    ↓ (없으면 documents.parsed_md fallback)
    ↓
Pinecone RAG + GPT-4o 분류
    ↓
pipeline_steps(step_key='2') 저장
```

---

## 4. 현재 연결 코드 위치

PM이 구현한 연결 코드 위치 (수정 필요 시):

```
backend/routers/feature2.py
  - _fetch_pipeline_result()  : pipeline_steps 조회
  - _build_enriched_text()    : f0 + F1 결과를 합쳐서 LLM 입력 텍스트 생성
                                ← 필드명 변경이 필요하면 이 함수만 수정
```

---

## 5. 요청 사항 정리

1. **필드명 일치 확인** — 위 2-1의 JSON 키명이 f0 실제 저장 구조와 다르면 알려주세요. `_build_enriched_text()` 함수에서 수정하겠습니다.
2. **`doc_type` 값 확인** — 원재료 서류의 `doc_type`이 `'ingredients'`가 아닌 다른 값이면 알려주세요.
3. **완료 시점 확인** — f0가 `pipeline_steps` step_key='0'을 `status='completed'`로 저장하는 시점이 언제인지 확인 부탁드립니다. F2는 이 시점 이후에 실행됩니다.
