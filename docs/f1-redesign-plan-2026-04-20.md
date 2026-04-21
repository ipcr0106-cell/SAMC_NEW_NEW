# F1 재설계 실행 계획 (2026-04-20)

**작성일**: 2026-04-20
**브랜치**: BC

**선행 문서**:
- [f1-diagnosis-2026-04-20.md](./f1-diagnosis-2026-04-20.md)
- [f1-root-cause-2026-04-20.md](./f1-root-cause-2026-04-20.md)

---

## 0. 전제

### 0.1 복구 순서의 원칙

원인분석 문서의 결론에 따라:

```
Wave A (핵심 복구)
  ├─ 매칭 엔진 복구 (원인 #1)
  ├─ Silent masking 제거 (증폭기)
  ├─ 법령 필터 강화 (하류 S/N)
  └─ RAG_VERDICT flag 해제 검토 (원인 #2 — 품질 재측정 후)
        ↓
Wave B (구조 개선)
  └─ 기준↔법령 연결, 감사 로그, UI 재구조
        ↓
Wave C (장기 개선)
  └─ 단위 분리, CI 구축, 접근성
```

### 0.2 건드리지 않을 것 (건전한 자산)

진단 문서 §4 자산 목록 참조. 리팩터 충동을 자제하고 재활용한다.

- F0 OCR 파이프라인 (단, 추후 Claude Vision 전환은 Wave C)
- unit_converter 모듈
- HITL 상태기계 및 audit_log 전이 기록
- DataGoKrClient 재시도·백오프
- f1_law_cache + f1_law_articles 2단계 정규화

### 0.3 현재 미커밋 변경 처리

BC 브랜치에 다음 파일들이 미커밋 상태:

```
M  backend/models/f1_types.py
M  backend/routers/feature2.py
M  backend/services/f1_step_a.py
M  backend/services/f1_step_b.py
M  backend/services/f1_step_d.py
M  backend/services/feature1.py
M  backend/services/label_image_service.py
M  backend/tests/services/test_f1_step_a.py
M  backend/tests/services/test_f1_step_b.py
M  backend/tests/services/test_f1_step_d.py
?? backend/tests/routers/test_feature2_law_ref.py
?? docs/
```

**Wave A 착수 전에 반드시** 이 변경들이 어느 Wave의 선작업인지, 아니면 실험적 변경인지 사용자와 확인하여 정리해야 한다. 각 변경의 의도에 따라:

- 본 계획과 충돌하지 않음 → 커밋
- 본 계획과 충돌 → stash 또는 되돌림
- 실험적/일시적 변경 → stash

---

## 1. Wave A — 핵심 복구 (추정 1~2주)

### A-1. Fuzzy/Synonym/aliases/영문명 경로 복구

**대응 결함**: #2, #7, #8, #17, #19

**수정 파일**:
- `backend/services/f1_step_a.py`: `SELECT`에 `aliases, name_en` 추가, 비교 로직에 alias·영문 대입
- `backend/services/f1_step_b.py`: `run_step_b()` 내부에 Stage 2→3→4 fallback 계단 호출 연결, `_lookup_synonym()` 호출, `match_method` 필드 설정
- `backend/services/feature1.py`: `match_method` 필드를 enriched_summary에 실제 값으로 전달

**수정 규모 추정**: +80줄, -20줄, 테스트 +30줄

**핵심 설계 (의사 코드)**:

```python
# f1_step_b.py run_step_b() 내부
def match_ingredient(name: str) -> MatchResult:
    # Stage 1: exact
    if result := _pick_exact_component_item(...):
        return result._replace(match_method="exact")
    # Stage 2: normalized (기존 normalize_name 확장)
    if result := _exact_on_normalized(name):
        return result._replace(match_method="normalized")
    # Stage 3: fuzzy (Levenshtein 연결)
    if result := _match_ingredient_hits(name):
        return result._replace(match_method="fuzzy")
    # Stage 4: synonym (f1_ingredient_synonyms 경유)
    if synonym := _lookup_synonym(name):
        return _re_match_via_synonym(synonym, name)._replace(match_method="synonym")
    # Stage 5: LLM 제안 (Wave B에서 추가)
    return None  # unidentified
```

**완료 기준**:
- [ ] "밀가루" 입력 → 매칭 성공 (테스트)
- [ ] "마리화나" 입력 → "대마초" 금지 탐지 (테스트)
- [ ] "Cannabis" 입력 → "대마초" 탐지 (테스트)
- [ ] enriched_summary의 match_method 필드가 exact/normalized/fuzzy/synonym 중 하나로 채워짐
- [ ] 기존 8개 skip 테스트 중 4개 이상 재활성

---

### A-2. Silent masking 제거 + 에러 전파 규칙 통일

**대응 결함**: #1, #6

**수정 파일**:
- `backend/services/f1_step_b.py` (573~591): `_safe_call` 재설계 — 예외는 `Result.err(...)` 같은 명시 객체로 감쌈
- `backend/services/f1_step_c.py` (490~494): `except Exception: return [], "error"` 제거 → 특정 예외만 catch
- `backend/services/f1_step_d.py` (316~324): DB 장애를 빈 citations로 숨기지 말고 상위 전파
- `backend/services/feature1.py` (692, 710): `asyncio.wait_for(asyncio.gather(...), timeout=N)` 전체 타임아웃 추가
- `frontend`: API 응답에 `status: "ok"|"partial"|"error"` 상태 추가, UI에 "조회 실패" 배지

**수정 규모**: +150줄, -80줄, 테스트 +60줄

**설계 원칙**:

```
규칙 1. 예외는 삼키지 않는다. 특정 예외만 catch, 나머지는 상위 전파.
규칙 2. "빈 결과"와 "오류"는 서로 다른 상태 객체로 구분.
규칙 3. gather는 언제나 외부 타임아웃 래퍼(asyncio.wait_for) 안에서 호출.
규칙 4. 로그만 남기고 정상 진행하는 패턴 금지 (명시적 partial 상태로 승격).
```

**완료 기준**:
- [ ] f1_step_b/c/d에서 `except Exception:` 블록이 모두 제거 또는 명시 타입으로 교체
- [ ] gather 호출이 모두 `asyncio.wait_for()` 안에 있음
- [ ] API 응답 모델에 `status` 필드 추가
- [ ] UI에 "조회 실패" 배지 렌더링
- [ ] Silent masking 재등장 방지를 위한 정적 검사 규칙 (예: ruff rule) 추가 고려

---

### A-3. Step A 확장 조회

**대응 결함**: #7, #8 (A-1에 포함되나 별도 체크리스트)

A-1에 포함. 독립 완료 기준:
- [ ] f1_step_a.py의 SELECT가 `name_ko, name_en, aliases, reason, law_source` 모두 포함
- [ ] "마리화나"·"THC"·"CBD오일"·"Cannabis" 테스트 통과
- [ ] confidence 카테고리별 차등은 Wave B-4에서 수행

---

### A-4. 법령 인용 필터 강화

**대응 결함**: #4, #16

**수정 파일**:
- `backend/services/f1_step_d.py`:
  - `_MIN_SCORE`를 env `F1_STEP_D_MIN_SCORE`에 외부화 (기본 0.4)
  - `top_k` 이중제한 제거 — namespace당 top_k 후 전체에서 score DESC 재정렬·상위 N
  - 법령명+조항번호 기준 중복 제거 로직
- `backend/config/feature_flags.py`: `F1_STEP_D_MIN_SCORE`, `F1_STEP_D_TOP_K_GLOBAL` 추가

**수정 규모**: +60줄, -20줄

**설계 (의사 코드)**:

```python
# f1_step_d.py
raw = collect_from_all_namespaces(top_k_per_ns=5)
deduped = dedup_by(raw, key=lambda x: (x.law_name, x.article_no))
filtered = [x for x in deduped if x.score >= F1_STEP_D_MIN_SCORE]
ranked = sorted(filtered, key=lambda x: x.score, reverse=True)
return ranked[:F1_STEP_D_TOP_K_GLOBAL]
```

**완료 기준**:
- [ ] `F1_STEP_D_MIN_SCORE` env 작동 확인
- [ ] 중복 조항이 UI에 나타나지 않음
- [ ] 전형적 사례(밀가루)의 인용 건수가 기존 5건 → 2~3건으로 축소 (실제 테스트)

---

### A-5. 매칭 품질 재측정 → RAG_VERDICT_DISABLED 해제 검토

**대응 결함**: #14

**작업**:
1. A-1, A-2, A-4 완료 후 골든셋 100건 재실행
2. 일치율 측정 (기존 76% 대비)
3. 80% 이상 도달 시 `F1_RAG_VERDICT_DISABLED=false`로 스테이징 환경에서 canary 10% 적용
4. 증상 재발 없으면 50%, 100%로 확대

**결정 기준**:
- 골든셋 일치율 ≥ 80%
- Step D 법령 인용 평균 건수 ≤ 3건
- Silent masking으로 숨겨진 실패율 < 1%

**완료 기준**:
- [ ] 골든셋 재실행 리포트 작성
- [ ] 결정 기준 3개 모두 충족 여부 판정
- [ ] 충족 시: staging canary 10% 적용, 증상 모니터링
- [ ] 미충족 시: 부족 지표 식별하고 Wave A 추가 보강 작업 회귀

---

## 2. Wave B — 구조 개선 (추정 2~4주)

### B-1. 기준규격 ↔ 법령 객체 연결 (law_ref FK화)

**결함**: #5

- `StandardCheck.law_ref`을 문자열에서 `LawCitation` 객체 참조로 변경
- 백엔드에서 두 리스트를 tuple/dict로 묶어 전송
- 프론트에서 같은 행에 배치 렌더

### B-2. f1_escalation_logs INSERT 추가 + 테스트

**결함**: #11, #26

- `f1_hitl_service.py:278~282`에서 계산된 escalations를 실제 DB에 INSERT
- 테스트 케이스 추가: HITL-1 제출 시 f1_escalation_logs 행 존재 확인

### B-3. Step C no_data 명시적 처리

**결함**: #12

- 기준 0건 원재료를 `checks`에 `status=no_data`로 기록
- UI에 "검증 불가 — 기준 없음" 배지

### B-4. confidence 카테고리 차등

**결함**: #9

- Step A forbidden hit 점수를 카테고리별 매핑:
  - `drug`: 0.95
  - `endangered`: 0.90
  - `unauthorized`: 0.85
  - `toxin`: 0.95

### B-5. UI 기본 접기 + 중요도 시각화 + 근거 보기 모달

**결함**: #22

- LawCitationList 기본 상태: 핵심 2건 펼침, 나머지 "그 외 N건" 접힘
- 각 인용 클릭 → 법령 원문 모달 (원문·조항·관련 원재료·API raw 응답)
- namespace별 색상/아이콘 배지

### B-6. Legacy Step 0 제거 (v2 단일화)

**결함**: #10

- `step1_ingredients_check.py` 경로 차단 또는 삭제
- v2 경로로 모든 트래픽 통합

### B-7. F0→F1 재매칭 트리거

**결함**: #3

- HITL-0 편집 (F0 save) 이벤트 훅 → F1 파이프라인 자동 재실행
- UI에 "분석 진행 중" 상태 표시

### B-8. F0ApprovalPanel 분할

**결함**: #21

- 618줄 모놀리식 컴포넌트를 BasicInfoEditor, IngredientEditor, ProcessCodeEditor 3개 파일로 분리
- 각 편집기에 단위 테스트

---

## 3. Wave C — 장기 개선 (추정 4주+)

### C-1. 단위 분리 저장

- `f1_safetydata_*` 테이블에 `value_numeric`, `unit_code` 컬럼 추가
- 기존 문자열 값 마이그레이션 스크립트
- Step C 비교 로직을 숫자+단위 분리 기반으로 리팩터

### C-2. F0 Claude Vision 전환

- `ocr_service.py`, `parsing_service.py`, `label_image_service.py`의 OpenAI gpt-4o 코드 제거
- Claude Vision API로 교체
- 품질 벤치마크 비교

### C-3. F0 단위 테스트 구축

- OCR·파싱·공정코드 매핑 단위 테스트
- Golden Set 100건 수동 검증

### C-4. 중요도 태그 (priority, source_type 컬럼)

- `f1_law_cache`에 `priority INT`, `source_type ENUM` 컬럼 추가
- 법령 소스 종류(식품위생법/공전/고시)별 중요도 가중

### C-5. 전역 상태관리 도입 (zustand)

**결함**: #20

- 프론트 상태를 zustand 스토어로 통합
- `fetchResult()` 재호출 시 HITL-1 중간 작업 유지

### C-6. CI/CD 구축

**결함**: #24, #25

- `.github/workflows/`에 pytest + vitest + typecheck 구축
- `conftest.py` 글로벌 fixture 작성

### C-7. 접근성(ARIA) 보강

**결함**: #23

- aria-label, role, 키보드 탐색, ESC 닫기 등 전면 점검

### C-8. 보안 (환경별 분기)

**결함**: #13

- `.env.{local|dev|stg|prod}` 분리
- Supabase SERVICE_KEY를 축소 권한 키로 교체 검토
- 퍼블릭 전환 시 git history 정리 준비

---

## 4. 준수 체크리스트

### 4.1 Wave A 완료 기준

- [ ] A-1. 밀가루·마리화나·Cannabis 각각 테스트 통과
- [ ] A-2. Silent masking 패턴 제거, UI "조회 실패" 배지 렌더
- [ ] A-3. Step A SELECT 확장 완료
- [ ] A-4. 법령 인용 건수 축소 확인 (대표 사례 기준 2~3건)
- [ ] A-5. 골든셋 일치율 ≥ 80%, RAG_VERDICT flag 해제 canary 10% 적용

### 4.2 Wave B 완료 기준

- [ ] B-1. 기준↔법령 같은 행에 렌더
- [ ] B-2. f1_escalation_logs DB 행 존재 테스트 통과
- [ ] B-3. UI "검증 불가 — 기준 없음" 배지
- [ ] B-4. confidence 카테고리 차등 테스트
- [ ] B-5. 근거 보기 모달 E2E 테스트
- [ ] B-6. legacy Step 0 호출 경로 없음 (ripgrep 확인)
- [ ] B-7. F0 save → F1 재실행 E2E 테스트
- [ ] B-8. F0ApprovalPanel 분할 후 각 에디터 단위 테스트

### 4.3 Wave C 완료 기준

- [ ] C-1. 단위 분리 마이그레이션 완료, 롤백 검증
- [ ] C-2. Claude Vision 전환 + 품질 동등성 확인
- [ ] C-3. F0 단위 테스트 커버리지 70%+
- [ ] C-4. priority 컬럼 기반 재정렬 작동
- [ ] C-5. zustand 스토어 통합
- [ ] C-6. CI 전체 통과 (push마다 실행)
- [ ] C-7. 접근성 Lighthouse 90+
- [ ] C-8. 환경별 .env 분리, 시크릿 관리 정책 문서화

---

## 5. 검증 방법

### 5.1 매칭 복구 검증 (A-1)

```bash
pytest backend/tests/services/test_f1_step_b.py -k "test_match_stage_fallback" -v
pytest backend/tests/services/test_f1_step_a.py -k "test_aliases_detection" -v
```

### 5.2 Silent masking 검증 (A-2)

```bash
# 외부 API를 강제 실패 모드로 돌린 뒤 파이프라인 호출
# 기대: response.status == "partial" 또는 "error"
pytest backend/tests/integration/test_api_failure_propagation.py -v
```

### 5.3 법령 필터 검증 (A-4)

```bash
# 대표 사례 (밀가루) 실행 후 citations 건수 확인
python -m backend.scripts.bench_f1_step_d --case-id=<id>
# 기대: 2~3건, 중복 0건, score 모두 ≥ 0.4
```

### 5.4 RAG 품질 골든셋 (A-5)

```bash
python -m backend.scripts.run_goldenset --size=100 --flag=F1_RAG_VERDICT_DISABLED=false
# 기대: 일치율 ≥ 80%, 인용 평균 ≤ 3건
```

---

## 6. 이어받기 가이드 (다음 세션용)

### 6.1 문서 읽는 순서

```
1) f1-diagnosis-2026-04-20.md     — 27개 결함의 전체 지형 파악
2) f1-root-cause-2026-04-20.md    — 왜 2원인으로 수렴되는지 이해
3) f1-redesign-plan-2026-04-20.md (이 문서) — 무엇을 어떤 순서로 할지
```

### 6.2 현재 BC 브랜치 상태

- 베이스 커밋: `3bfd2af fix(f1-fe): 기준규격 표 "기준 미등록" 행 기본 숨김 + 토글`
- 미커밋 변경: 9개 파일 + 신규 test_feature2_law_ref.py
- 이 변경들이 어느 Wave의 선작업인지 **이어받는 사람이 반드시 먼저 사용자에게 확인** — 제거/커밋/stash 결정

### 6.3 우선순위 판단 기준

순서를 바꾸지 말아야 하는 이유:
- A-1(매칭 복구)을 건너뛰고 A-4(법령 필터)를 먼저 하면 → 키워드 오염이 그대로라 효과 없음
- A-5(flag 해제)를 먼저 하면 → 여전히 이상한 결과가 판정에 반영됨 → 증상 악화

### 6.4 진단 재검증이 필요한 경우

다음 상황에서는 진단 문서 업데이트 필요:
- 본 문서 작성 후 2주 이상 경과
- 결함 번호 중 하나가 "이미 고쳐져 있다"고 판정되는 경우 (재측정 필요)
- 새로운 증상이 발견되는 경우
- 사용자가 보고한 전제가 변경되는 경우 (예: F2 정확도 80%+가 아닌 것으로 판명)

### 6.5 HITL 설계 철학 (작업 도중 원점 회귀용)

> 현단계의 부족한 AI 판단을 실무자가 최종적으로 결정하는 것이 핵심이다.

작업 도중 의심스러울 때는 이 원칙으로 돌아간다. HITL의 세 전제 (AI 기본 신뢰도, 개입 접점, 투명한 근거) 중 무엇을 지원하는 작업인지 자문.

### 6.6 Wave 간 피드백 루프

Wave A 완료 후 반드시:
1. 사용자에게 두 장의 원본 스크린샷과 유사한 케이스에서 결과 재현 — 증상 사라짐 여부 확인
2. 결함 맵에 해결된 번호 체크
3. 남은 결함 중 Wave B의 우선순위 재평가

Wave A 효과가 기대에 못 미치면 원인 분석 재수행. Wave B로 성급히 이동 금지.

---

**끝.**
