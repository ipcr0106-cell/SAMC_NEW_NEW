# F1 Wave A 병렬 구현 계획서 (AI 에이전트 팀 모드)

**작성일**: 2026-04-20
**실행 모델**: Claude Code Agent 도구 다중 호출 (단일 세션, 사용자 감독)

**선행 문서**:
- [f1-diagnosis-2026-04-20.md](./f1-diagnosis-2026-04-20.md)
- [f1-root-cause-2026-04-20.md](./f1-root-cause-2026-04-20.md)
- [f1-redesign-plan-2026-04-20.md](./f1-redesign-plan-2026-04-20.md)

---

## 0. 개요

본 문서는 **Wave A (핵심 복구)** 5항목을 AI 에이전트를 다중 호출하여 병렬 실행할 때의 구조·오너십·브리핑·검증 체계를 정의한다.

### 0.1 작업자 모델

```
┌─────────────────────────────────────────────────┐
│  [감독 lane]  사용자                              │
│   · 미커밋 변경 정리                              │
│   · Phase 간 전환 승인                            │
│   · 파일 오너십 감시                              │
│   · 골든셋 재측정 (A-5)                           │
└─────────────────────────────────────────────────┘
                     ↓ 브리핑 (프롬프트)
┌─────────────────────────────────────────────────┐
│  [실행 lane]  Claude Code Agent (병렬 N개)         │
│   · 각 에이전트는 self-contained 브리핑으로 실행    │
│   · 같은 Phase 내 에이전트들은 서로 다른 파일만 수정 │
│   · 결과는 구조화된 보고로 감독 lane에 반환         │
└─────────────────────────────────────────────────┘
```

### 0.2 핵심 원칙

1. **파일 단위 오너십**: 같은 Phase에서 두 에이전트가 동일 파일을 수정하지 않는다.
2. **Self-contained 브리핑**: 에이전트는 이전 맥락을 모른다. 프롬프트에 필요한 모든 정보를 포함한다.
3. **Phase 간 동기화**: Phase가 끝나면 사용자가 결과 검증 후 다음 Phase 진입 승인.
4. **구조화 보고**: 에이전트는 완료 시 "수정한 파일/함수/라인 + 완료 기준 체크 + 남은 위험"을 표 형식으로 반환.
5. **워크트리 없음**: 단일 BC 브랜치에서 Phase별 직렬, Phase 내 병렬.

### 0.3 본 계획서의 범위

- Wave A (A-1 ~ A-5) **만** 다룬다.
- Wave B/C는 별도 계획서 필요 (구조가 달라 병렬 밀도가 훨씬 높음).
- 테스트 전략은 "추가형"만 허용 (기존 테스트 수정·삭제는 사용자가 별도 결정).

---

## 1. 병렬의 기술적 제약

### 1.1 Race Condition

한 세션에서 Agent 도구를 여러 번 병렬 호출하면 동시 실행되지만 **동일 파일시스템**을 공유한다. 아래 시퀀스가 위험하다:

```
t=0  Agent A: Read f1_step_b.py                 (상태 S0 획득)
t=1  Agent B: Read f1_step_b.py                 (동일 상태 S0 획득)
t=2  Agent A: Edit f1_step_b.py → 상태 S1 (A의 변경)
t=3  Agent B: Edit f1_step_b.py → 상태 S2 (B의 변경, A 덮어씀)
```

Claude Code의 Edit 도구는 `old_string → new_string` 방식으로 안전장치가 있지만, 두 에이전트가 "다른 함수"를 수정해도 **파일 전체가 다시 써질 때 충돌** 가능하다.

### 1.2 해결 규칙

- **규칙 1**: 같은 Phase에서 같은 파일을 두 에이전트가 수정 금지.
- **규칙 2**: 같은 파일의 복수 목적 수정은 **한 에이전트가 묶어서** 처리.
- **규칙 3**: Phase 경계에서 사용자 검증 후 다음 Phase 진입.

### 1.3 해결 전략 — Phase 분할

Wave A의 3개 트랙(A-1/A-2/A-4)이 공유하는 파일을 식별하여, 같은 Phase에 배치되지 않도록 재배열한다. 결과적으로 **트랙 병렬 → Phase 병렬**로 모델이 바뀐다.

---

## 2. 파일 오너십 행렬

### 2.1 Wave A 항목 × 파일 (원본 충돌)

| 파일 | A-1 매칭 | A-2 Silent | A-4 필터 | 충돌 |
|---|---|---|---|---|
| f1_step_a.py | ✏️ | | | — |
| f1_step_b.py | ✏️ | ✏️ | | 🔴 A-1 ∩ A-2 |
| f1_step_c.py | | ✏️ | | — |
| f1_step_d.py | | ✏️ | ✏️ | 🔴 A-2 ∩ A-4 |
| feature1.py | ✏️ | ✏️ | | 🔴 A-1 ∩ A-2 |
| feature_flags.py | | | ✏️ | — |
| frontend (status) | | ✏️ | | — |
| conftest.py (신규) | ⬇️ | ⬇️ | ⬇️ | 공통 |
| test_f1_step_a.py | ✏️ | | | — |
| test_f1_step_b.py | ✏️ | ✏️ | | 🟠 (추가형이면 OK) |
| test_f1_step_c.py | | ✏️ | | — |
| test_f1_step_d.py | | ✏️ | ✏️ | 🟠 (추가형이면 OK) |

### 2.2 Phase 재배열 (병렬 안전)

| Phase | Agent | 수정 파일 | 대응 Wave 항목 |
|---|---|---|---|
| 0 (준비) | δ | conftest.py, backend/common/result.py (신규), backend/common/match_method.py (신규) | 공통 계약 |
| 1 | α | f1_step_a.py, test_f1_step_a.py | A-1/A-3 (Step A 부분) |
| 1 | β | f1_step_c.py, test_f1_step_c.py | A-2 (Step C 부분) |
| 1 | γ | feature_flags.py | A-4 env 추가 |
| 1 | ε | frontend status 배지 | A-2 FE |
| 2 | α | f1_step_b.py, test_f1_step_b.py | A-1 매칭 + A-2 _safe_call (합침) |
| 2 | β | f1_step_d.py, test_f1_step_d.py | A-2 + A-4 (합침) |
| 3 | ζ | feature1.py | A-1 match_method + A-2 gather timeout (합침) |
| 4 (사용자) | — | (검증) | A-5 골든셋 + flag canary |

### 2.3 Phase별 병렬도

- Phase 0: 1 에이전트 (또는 사용자 수동)
- Phase 1: **4 에이전트 병렬**
- Phase 2: **2 에이전트 병렬**
- Phase 3: 1 에이전트 (파일 공유로 순차)
- Phase 4: 사용자 단독

---

## 3. Phase 상세

### Phase 0 — 준비 (공통 계약)

**목표**: 후속 Phase가 공유할 타입·테스트 fixture 선작성.

**에이전트 δ 브리핑 범위**:
- `backend/common/result.py` 신규 — `Result[T]` generic: `ok(value)`, `partial(value, reason)`, `err(reason)`
- `backend/common/match_method.py` 신규 — Literal `"exact" | "normalized" | "fuzzy" | "synonym" | None`
- `backend/tests/conftest.py` 신규 — Supabase mock fixture, data_go_kr mock client, fake law.go.kr 응답
- **레거시 탐지 (읽기 전용, 보고만)**
  - `backend/services/step1_ingredients_check.py` 호출 지점 grep
  - `backend/services/step3_standards.py` 호출 지점 grep
  - f1_step_a.py ↔ step1_ingredients_check.py 판정 룰 중복의 실제 호출 경로 존재 여부 (결함 #10 재현 가능성)
  - 결과를 "레거시 파일 × 호출자 × 호출 빈도 × 처리 권장" 표로 보고
  - 수정·삭제는 사용자 판정 후 (Wave A-1 또는 Wave B-6에서 처리)

**완료 기준**:
- [ ] 3개 파일 생성, import 테스트 통과 (`python -c "from backend.common.result import Result"`)
- [ ] conftest.py가 test_f1_step_*.py 에서 활용 가능한 fixture 노출
- [ ] 기존 테스트 깨지지 않음 (`pytest backend/tests/ -x --co`)
- [ ] L2/L5 레거시 탐지 보고서 제출 (표 형식)

**병렬도**: 1 (단독). 이 Phase는 병렬 필요 없음.

**사용자 확인 포인트**: Result 타입 시그니처, match_method enum 값 후보.

---

### Phase 1 — 독립 파일 4개 병렬

**목표**: 파일 충돌 없는 4개 영역을 동시 처리.

#### 에이전트 α (Step A 확장)

**수정 파일**: `backend/services/f1_step_a.py`, `backend/tests/services/test_f1_step_a.py`

**수정 내용**:
- SELECT에 `name_en, aliases` 컬럼 추가
- 비교 로직 확장: 입력을 `name_ko`뿐 아니라 `name_en` (case-insensitive), `aliases` 배열과 비교
- 매칭 발생 시 `matched_by` 필드로 어느 키에 히트했는지 기록

**완료 기준**:
- [ ] "마리화나" 입력 → "대마초" 금지 hit (aliases 경로)
- [ ] "Cannabis" 입력 → "대마초" 금지 hit (name_en 경로)
- [ ] 기존 정확 매칭 시나리오 회귀 없음

#### 에이전트 β (Step C Silent masking)

**수정 파일**: `backend/services/f1_step_c.py`, `backend/tests/services/test_f1_step_c.py`

**수정 내용**:
- `_fetch_all_specs_for_ingredient`의 `except Exception` 제거 → 특정 예외만 catch
- 실패 시 `Result.err(...)` 반환 (Phase 0의 Result 타입 사용)
- `asyncio.gather` 를 `asyncio.wait_for(gather, timeout=60.0)` 로 래핑
- 기준 0건 원재료를 `checks`에 `status=no_data`로 기록 (결함 #12 동시 처리)

**완료 기준**:
- [ ] API 실패 모킹 시 Result.err 반환 테스트 통과
- [ ] 60초 초과 시 TimeoutError 전파
- [ ] no_data 원재료가 checks에 기록되어 UI로 전달됨

#### 에이전트 γ (feature_flags env 추가)

**수정 파일**: `backend/config/feature_flags.py`

**수정 내용**:
- `F1_STEP_D_MIN_SCORE` (기본 0.4) 추가
- `F1_STEP_D_TOP_K_GLOBAL` (기본 3) 추가
- 기존 flag는 건드리지 않음

**완료 기준**:
- [ ] env 미설정 시 기본값 반환
- [ ] env 설정 시 반영

#### 에이전트 ε (Frontend status 배지)

**수정 파일**: `frontend/features/feature1/api/importCheck.ts` (API 응답 타입), `frontend/features/feature1/components/StatusBanner.tsx` (신규 또는 기존 확장)

**수정 내용**:
- API 응답 타입에 `status: "ok" | "partial" | "error"` 추가
- "조회 실패" 배지 컴포넌트 추가 (Step C/D가 partial/error 반환 시 렌더)
- Phase 2에서 백엔드가 실제로 status를 내려줄 때까지는 타입·컴포넌트 뼈대만

**완료 기준**:
- [ ] 타입 컴파일 통과
- [ ] Storybook 또는 isolated 렌더로 "조회 실패" 배지 시각 확인

#### Phase 1 통합 검증 (사용자)

Phase 1의 4 에이전트가 모두 완료하면:
- `pytest backend/tests/services/test_f1_step_a.py test_f1_step_c.py -v`
- `cd frontend && npm run typecheck`
- `git diff --stat` 로 변경 파일이 각 에이전트 범위와 일치하는지 검사

---

### Phase 2 — 대형 파일 2개 병렬

**목표**: 가장 복잡한 f1_step_b.py와 f1_step_d.py를 에이전트 1개씩 배정하여 동시 처리. 같은 파일에 여러 목적을 묶어 처리하므로 충돌 없음.

#### 에이전트 α (Step B 매칭 복구 + Silent masking)

**수정 파일**: `backend/services/f1_step_b.py`, `backend/tests/services/test_f1_step_b.py`

**수정 내용** (4가지 묶음):

1. **매칭 Stage 계단 연결** (결함 #2, #17, #19)
   - `run_step_b()` 내부에 Stage 1→2→3→4 fallback
   - `_match_ingredient_hits()`, `_lookup_synonym()` 호출 경로 복구
   - `match_method` 필드를 Ingredient 객체에 설정

2. **`_safe_call` 재설계** (결함 #1)
   - 예외 객체를 tuple payload로 감추는 현재 패턴 제거
   - `Result.ok / partial / err` 반환 (Phase 0의 타입 사용)

3. **gather 타임아웃** (결함 #6)
   - `asyncio.wait_for(asyncio.gather(...), timeout=60.0)`

4. **테스트 추가**
   - Fuzzy fallback 시나리오
   - Synonym 경로 시나리오
   - API 실패 시 Result.err 전파
   - 기존 skip된 `_LEGACY_15111777` 테스트 중 재활성 가능한 것 재가동

**완료 기준**:
- [ ] "밀가루" 정확매칭 실패 상황에서도 Fuzzy로 매칭 성공
- [ ] match_method 필드가 exact/normalized/fuzzy/synonym 중 하나로 설정
- [ ] API 실패 시 Result.err 반환, UI까지 partial 상태 전달
- [ ] skip 테스트 8개 중 4개 이상 재활성

#### 에이전트 β (Step D 필터 강화 + Silent masking)

**수정 파일**: `backend/services/f1_step_d.py`, `backend/tests/services/test_f1_step_d.py`

**수정 내용** (3가지 묶음):

1. **필터 강화** (결함 #4, #16)
   - `_MIN_SCORE` → env `F1_STEP_D_MIN_SCORE` 참조 (Phase 1 γ가 준비)
   - top_k 이중제한 제거, namespace 수집 후 전체 score DESC 재정렬
   - 법령명+조항번호 기준 dedup

2. **Silent masking 제거** (결함 #1)
   - `_search()` 예외 시 빈 citations 반환 제거 → Result.err 전파

3. **테스트 추가**
   - MIN_SCORE 경계값 테스트
   - dedup 시나리오 (동일 조항 중복 입력)
   - 반환 건수 상한 검증

**완료 기준**:
- [ ] 대표 사례(밀가루)에서 인용 건수 기존 5건 → 2~3건으로 축소
- [ ] 중복 조항이 결과에 나타나지 않음
- [ ] DB 장애 모킹 시 Result.err 반환

#### Phase 2 통합 검증 (사용자)

- `pytest backend/tests/services/test_f1_step_b.py test_f1_step_d.py -v`
- 직접 API 호출 smoke test (대표 사례)
- Step B/D가 Phase 0의 Result 타입을 일관되게 사용하는지 코드 리뷰

---

### Phase 3 — feature1.py 일괄 수정

**목표**: A-1 매칭 결과 전달 + A-2 gather 타임아웃을 동시 처리. **한 에이전트**만 작업 (파일 공유).

#### 에이전트 ζ (feature1.py 통합)

**수정 파일**: `backend/services/feature1.py`, `backend/routers/feature1.py` (status 필드 응답)

**수정 내용**:

1. **match_method 전달** (결함 #18)
   - 411~425 라인 enriched_summary 에서 `getattr(i, "match_method", None)` 을 실제 값으로 전달
   - Step B가 설정한 match_method가 API 응답까지 흐르도록

2. **gather 타임아웃** (결함 #6)
   - 692, 710 라인 `asyncio.gather(...)` → `asyncio.wait_for(gather, timeout=120.0)`

3. **Result 타입 수용**
   - Step B/C/D가 Result 반환 시 feature1.py 가 이를 해석하여 API 응답에 status 필드 구성
   - partial → 해당 step의 결과는 최선치, status="partial"
   - err → 해당 step 결과는 없음, status="error", 전체 판정은 "review_needed"

**완료 기준**:
- [ ] API 응답에 `status` 필드 포함
- [ ] match_method 필드가 프론트까지 도달
- [ ] 120초 초과 시 TimeoutError 응답
- [ ] Phase 1 ε가 만든 frontend 배지가 실제 status에 연동됨

---

### Phase 4 — 사용자 검증 + A-5

**전담자**: 사용자

**작업**:

1. **통합 smoke test**
   - 밀가루·마리화나·Cannabis 대표 케이스 실행
   - 각 케이스에서 Wave A가 목표한 증상 개선 확인

2. **골든셋 재실행**
   ```bash
   python -m backend.scripts.run_goldenset --size=100
   ```
   - 기존 76% 대비 일치율 측정
   - 80% 미만 시 A-1 또는 A-2 회귀 작업 결정

3. **RAG_VERDICT flag 해제 canary**
   - 일치율 ≥ 80% 확인
   - 법령 인용 평균 건수 ≤ 3건 확인
   - Silent masking 숨은 실패율 < 1% 확인
   - 모든 조건 충족 시 staging에서 `F1_RAG_VERDICT_DISABLED=false` canary 10%

4. **증상 재현 검증**
   - 원본 두 장 스크린샷과 유사한 케이스에서 판정 실행
   - S1~S7 증상이 사라졌는지 정성 평가

---

## 4. Phase별 에이전트 브리핑 템플릿

각 Phase 시작 시 사용자가 copy-paste로 Agent 도구에 투입.

### 4.1 Phase 0 · Agent δ 브리핑

```
당신은 F1 Wave A 병렬 계획의 Phase 0 준비 작업을 담당합니다. 후속 Phase의 
에이전트들이 공유할 공통 타입과 테스트 fixture를 선작성합니다.

프로젝트 루트: C:\GITHUB\SAMC_NEW_NEW
선행 문서: docs/f1-redesign-plan-2026-04-20.md, docs/f1-parallel-execution-plan-2026-04-20.md

작업 범위:
1. backend/common/result.py 신규 작성
   - Generic Result[T]: ok(value), partial(value, reason), err(reason)
   - is_ok(), is_partial(), is_err() 판별
   - map(), unwrap_or() 등 기본 헬퍼
   
2. backend/common/match_method.py 신규 작성
   - Literal["exact", "normalized", "fuzzy", "synonym"] | None
   - 명시적 Enum 또는 Literal 타입으로
   
3. backend/tests/conftest.py 신규 작성
   - mock_supabase fixture
   - fake_data_go_kr_client fixture
   - fake_law_go_kr_response fixture

5. 레거시 탐지 (grep만, 수정 금지)
   아래 파일의 호출 현황을 조사하여 표로 보고:

   - backend/services/step1_ingredients_check.py
     · 어떤 함수가 어디서 import·호출되는지
     · 현재 파이프라인 실행 경로에 포함되는지

   - backend/services/step3_standards.py
     · 위와 동일

   - f1_step_a.py vs step1_ingredients_check.py 판정 룰 중복
     · 두 구현이 동시에 호출되는 케이스 존재 여부
     · 결함 #10 실제 재현 가능성

   보고 형식:
   | 레거시 파일 | 호출 위치 (파일:라인) | 호출 빈도 | 처리 권장 |

완료 기준:
- [ ] 3개 파일 import 테스트 통과
- [ ] 기존 테스트 회귀 없음 (pytest --co 로 collection 검증)
- [ ] conftest.py fixture가 기존 test_f1_step_*.py에서 참조 가능한 이름으로 노출
- [ ] 레거시 탐지 보고서 (위 표) 제출

결과 보고 형식 (표):
| 파일 | 라인 수 | 주요 export | 비고 |
(+ 레거시 탐지 표 별도)
```

### 4.2 Phase 1 · Agent α 브리핑 (Step A)

```
당신은 F1 Wave A Phase 1의 Agent α입니다. Step A(금지 원재료 판정)의 
false negative 결함(#7, #8)을 수정합니다.

프로젝트 루트: C:\GITHUB\SAMC_NEW_NEW
담당 파일 (이 파일들만 수정):
- backend/services/f1_step_a.py
- backend/tests/services/test_f1_step_a.py

다른 파일 수정 금지. 특히 f1_step_b.py, feature1.py는 절대 건드리지 말 것.

현재 문제:
- f1_step_a.py:75~78: SELECT에 name_en, aliases가 없음
- 결과: "마리화나"(대마초의 alias) 입력 시 매칭 실패, "Cannabis" 영문 입력도 실패

수정 내용:
1. SELECT를 "name_ko, name_en, aliases, reason, law_source"로 확장
2. 비교 로직에 추가:
   - normalized_input == row.name_ko (기존)
   - normalized_input.lower() == row.name_en.lower() (신규)
   - normalized_input in row.aliases (신규)
3. 히트 발생 시 어느 경로였는지 matched_by 필드 추가 (선택)

테스트 추가:
- test_alias_hit_마리화나: forbidden에 "대마초" (aliases=['마리화나']) 가 있을 때 
  "마리화나" 입력이 hit 되는지
- test_english_name_hit_cannabis: name_en="Cannabis" 레코드를 "Cannabis" 입력이 hit
- test_case_insensitive_english: "cannabis" (소문자) 입력도 hit

완료 기준:
- [ ] 3개 신규 테스트 통과
- [ ] 기존 test_f1_step_a.py 테스트 회귀 없음
- [ ] f1_step_a.py 외 파일 변경 없음

결과 보고 형식:
| 수정 파일 | 수정 라인 | 추가 테스트 | 통과 여부 |
```

### 4.3 Phase 1 · Agent β 브리핑 (Step C) — 동일 패턴

(생략, Agent α와 동일 구조. 담당 파일: f1_step_c.py, test_f1_step_c.py. 목적: Silent masking 제거 + no_data 명시적 처리 + gather 타임아웃. 완료 기준은 Phase 1 §β 참조.)

### 4.4 Phase 1 · Agent γ 브리핑 (feature_flags)

(담당 파일: feature_flags.py. 목적: `F1_STEP_D_MIN_SCORE`, `F1_STEP_D_TOP_K_GLOBAL` env 추가. 완료 기준은 Phase 1 §γ 참조.)

### 4.5 Phase 1 · Agent ε 브리핑 (Frontend)

(담당 파일: frontend/features/feature1/api/importCheck.ts, 신규 StatusBanner.tsx. 목적: API 응답 타입에 status 추가, "조회 실패" 배지 컴포넌트 뼈대. 완료 기준은 Phase 1 §ε 참조.)

### 4.6 Phase 2 · Agent α 브리핑 (Step B 대형 작업)

```
당신은 F1 Wave A Phase 2의 Agent α입니다. f1_step_b.py 전체를 담당합니다. 
4가지 작업을 한 번에 묶어 처리합니다.

프로젝트 루트: C:\GITHUB\SAMC_NEW_NEW
담당 파일 (이 파일들만 수정):
- backend/services/f1_step_b.py
- backend/tests/services/test_f1_step_b.py

다른 파일 수정 금지. 특히 f1_step_d.py, feature1.py는 절대 건드리지 말 것.

선행 조건:
- Phase 0 완료: backend/common/result.py, backend/common/match_method.py, conftest.py
- Phase 1 완료: f1_step_a.py, feature_flags.py

작업 4가지 (한 에이전트가 묶어서):

1. 매칭 Stage 계단 연결 (결함 #2, #17, #19)
   - run_step_b() 내부에 fallback 계단:
     Stage 1 exact → Stage 2 normalized → Stage 3 fuzzy (_match_ingredient_hits 호출) 
     → Stage 4 synonym (_lookup_synonym 호출)
   - match_method 필드를 각 Ingredient 객체에 설정

2. _safe_call 재설계 (결함 #1)
   - 현재 573~591 라인의 tuple payload 방식 제거
   - Result.ok / partial / err 반환 (Phase 0 타입 사용)

3. gather 타임아웃 (결함 #6)
   - 624 라인 asyncio.gather를 asyncio.wait_for(gather, timeout=60.0)로 래핑

4. 테스트 추가 (기존 삭제 금지, 추가형만)
   - Fuzzy fallback 시나리오
   - Synonym 경로 시나리오
   - API 실패 시 Result.err 전파
   - 기존 _LEGACY_15111777 skip 테스트 재활성 시도

완료 기준:
- [ ] "밀가루" 정확매칭 실패 → Fuzzy 매칭 성공 테스트
- [ ] match_method 필드가 exact/normalized/fuzzy/synonym 중 하나로 설정
- [ ] API 실패 모킹 시 Result.err 반환
- [ ] skip 테스트 8개 중 4개 이상 재활성
- [ ] 기존 test_f1_step_b.py 테스트 회귀 없음

결과 보고 형식:
| 작업 | 수정 라인 | 추가 테스트 | 완료 기준 충족 |
```

### 4.7 Phase 2 · Agent β 브리핑 (Step D)

(담당 파일: f1_step_d.py, test_f1_step_d.py. 3가지 작업 묶음: 필터 강화 + Silent masking 제거 + 테스트. 완료 기준은 Phase 2 §β 참조.)

### 4.8 Phase 3 · Agent ζ 브리핑 (feature1.py)

```
당신은 F1 Wave A Phase 3의 Agent ζ입니다. feature1.py 전체를 담당합니다.
Phase 1·2가 모두 완료된 상태에서 배선 작업을 수행합니다.

프로젝트 루트: C:\GITHUB\SAMC_NEW_NEW
담당 파일:
- backend/services/feature1.py
- backend/routers/feature1.py (API 응답 status 필드)

선행 조건:
- Phase 0, 1, 2 모두 완료
- Step A/B/C/D가 Result 타입을 반환하도록 수정되어 있음
- match_method 필드가 Ingredient 객체에 설정되어 있음

작업 3가지:
1. match_method 전달 (결함 #18)
   - feature1.py 411~425 라인 enriched_summary에서
   - getattr(i, "match_method", None) 이 실제 값을 반환하도록 검증
   - 필요 시 변환 로직 추가

2. gather 타임아웃 (결함 #6)
   - 692, 710 라인 asyncio.gather → asyncio.wait_for(gather, timeout=120.0)

3. Result 타입 수용 → API status 필드
   - Step B/C/D가 Result 반환 시 해석:
     · Result.ok → 정상
     · Result.partial → status="partial", 해당 step 최선치 사용
     · Result.err → status="error", 해당 step 결과 없음, 전체 verdict = "review_needed"
   - routers/feature1.py 의 API 응답 모델에 status 필드 추가

완료 기준:
- [ ] API 응답에 status 필드 포함
- [ ] match_method 값이 프론트 응답까지 흐름
- [ ] 120초 초과 시 TimeoutError 응답
- [ ] Phase 1 ε가 만든 frontend StatusBanner가 실제 status에 연동

결과 보고 형식:
| 작업 | 수정 라인 | 테스트 | 완료 기준 충족 |
```

---

## 5. Phase 간 검증 체크포인트

### 5.1 Phase 0 → Phase 1

```
□ Result, match_method import 성공
□ conftest.py fixture 이름 확인
□ pytest backend/tests/ -x --co 성공 (collection만)
```

### 5.2 Phase 1 → Phase 2

```
□ 4 에이전트 결과 병합 — git diff --stat 검사
□ 각 에이전트가 담당 파일 외 수정 없음 확인
□ pytest backend/tests/services/test_f1_step_a.py -v
□ pytest backend/tests/services/test_f1_step_c.py -v
□ cd frontend && npm run typecheck
□ Phase 1 ε는 뼈대만 (실제 status 필드는 Phase 3에서 연결)
```

### 5.3 Phase 2 → Phase 3

```
□ 2 에이전트 결과 병합 — git diff --stat 검사
□ pytest backend/tests/services/test_f1_step_b.py test_f1_step_d.py -v
□ 대표 케이스 smoke test — 직접 호출로 Result 타입 정상 반환 확인
□ skip 테스트 재활성 수 측정
```

### 5.4 Phase 3 → Phase 4

```
□ pytest backend/tests/ -v (전체)
□ curl 또는 API 클라이언트로 실제 판정 호출, status 필드 확인
□ frontend 렌더 확인 — StatusBanner가 실제 응답에 연동
□ 밀가루 / 마리화나 / Cannabis 3 시나리오 통과
```

### 5.5 Phase 4 (A-5) 완료 기준

```
□ 골든셋 100건 재실행 완료
□ 일치율 ≥ 80% (기존 76% 대비)
□ 법령 인용 평균 건수 ≤ 3
□ Silent masking 숨은 실패율 < 1%
□ 모두 충족 시 staging에서 F1_RAG_VERDICT_DISABLED=false canary 10%
```

---

## 6. 공통 계약 모듈 (Phase 0 산출물)

### 6.1 Result 타입 (스케치)

```python
# backend/common/result.py
from typing import Generic, TypeVar, Optional, Callable

T = TypeVar("T")
U = TypeVar("U")

class Result(Generic[T]):
    __slots__ = ("_value", "_reason", "_state")

    def __init__(self, value: Optional[T], reason: Optional[str], state: str):
        self._value = value
        self._reason = reason
        self._state = state  # "ok" | "partial" | "err"

    @classmethod
    def ok(cls, value: T) -> "Result[T]":
        return cls(value, None, "ok")

    @classmethod
    def partial(cls, value: T, reason: str) -> "Result[T]":
        return cls(value, reason, "partial")

    @classmethod
    def err(cls, reason: str) -> "Result[T]":
        return cls(None, reason, "err")

    def is_ok(self) -> bool: return self._state == "ok"
    def is_partial(self) -> bool: return self._state == "partial"
    def is_err(self) -> bool: return self._state == "err"

    def unwrap_or(self, default: T) -> T:
        return self._value if self._value is not None else default

    def map(self, fn: Callable[[T], U]) -> "Result[U]":
        if self._value is None:
            return Result(None, self._reason, self._state)
        return Result(fn(self._value), self._reason, self._state)
```

### 6.2 match_method

```python
# backend/common/match_method.py
from typing import Literal

MatchMethod = Literal["exact", "normalized", "fuzzy", "synonym"]

# 유효값 상수 (런타임 검증용)
MATCH_METHODS: frozenset[str] = frozenset({"exact", "normalized", "fuzzy", "synonym"})
```

### 6.3 conftest.py 개요

```python
# backend/tests/conftest.py (윤곽)
import pytest

@pytest.fixture
def mock_supabase():
    # supabase client mock 반환
    ...

@pytest.fixture
def fake_data_go_kr_client():
    # DataGoKrClient mock 반환 (15094202, 15111913 응답 구성 가능)
    ...

@pytest.fixture
def fake_law_go_kr_articles():
    # f1_law_articles 샘플 데이터 리스트 반환
    ...
```

---

## 7. 실패 시나리오·회복

### 7.1 에이전트가 담당 범위를 벗어나 수정

**감지**: `git diff --stat` 에서 담당 외 파일이 변경됨.

**회복**:
1. 해당 에이전트의 모든 변경을 `git stash` 로 격리
2. 담당 파일의 변경만 발췌하여 재적용
3. 해당 에이전트 재브리핑 — "범위 준수" 강조

### 7.2 Phase 2에서 Result 타입 import 실패

**원인**: Phase 0이 제대로 완료되지 않았거나 import 경로가 다름.

**회복**:
1. Phase 2 에이전트 중단
2. Phase 0 산출물 재검증 (import 테스트)
3. 필요 시 Phase 0 재실행
4. Phase 2 재시도

### 7.3 두 에이전트가 같은 파일을 수정 (규칙 위반)

**감지**: Phase 1 통합 검증에서 파일 오너십 행렬과 실제 `git diff --stat` 불일치.

**회복**:
1. 두 변경을 `git diff` 로 확인
2. 충돌 영역 여부 확인
3. 사용자 수동 병합 또는 한 에이전트의 변경을 revert 후 재실행

### 7.4 Phase 3에서 match_method가 None으로 흐름

**원인**: Phase 2 Agent α가 match_method 설정을 누락.

**회복**:
1. Phase 2 Agent α 결과 재검토 — run_step_b() 내 match_method 할당 코드 확인
2. 누락 시 Phase 2 α 재브리핑, 추가 수정만 수행
3. Phase 3 재시도

### 7.5 A-5 일치율이 80% 미만

**원인**: Wave A 수정이 품질에 충분히 반영되지 않음.

**회복**:
1. 골든셋에서 실패한 케이스 분석
2. 실패 패턴이 매칭/필터/Silent 중 어느 층인지 식별
3. 해당 Phase 재작업 (Phase 2가 가장 빈번할 것)
4. Phase 3·4 재실행

---

## 8. 타임라인 + 사용자 감독 체크리스트

### 8.1 예상 타임라인

| Day | Phase | 작업 | 담당 |
|---|---|---|---|
| 0 | Phase 0 | 공통 계약·conftest 작성 | Agent δ (또는 사용자) |
| 1 | Phase 1 | 4 에이전트 병렬 실행 | α, β, γ, ε |
| 1~2 | Phase 1 검증 | 사용자 통합 검증 | 사용자 |
| 2~3 | Phase 2 | 2 에이전트 병렬 실행 | α, β |
| 3~4 | Phase 2 검증 | 사용자 통합 검증 | 사용자 |
| 4~5 | Phase 3 | feature1.py 일괄 | Agent ζ |
| 5 | Phase 3 검증 | 사용자 검증 | 사용자 |
| 6~7 | Phase 4 | 골든셋 + flag canary | 사용자 |

**총 소요**: 약 5~7일 (사람 단독 순차 실행의 ~1/2~1/3)

### 8.2 사용자 감독 체크리스트

#### Day 0
- [ ] 미커밋 9개 파일 정리 완료 (커밋 또는 stash)
- [ ] Phase 0 브리핑 Agent δ에게 전달
- [ ] Phase 0 결과 검증

#### Day 1 (Phase 1 시작)
- [ ] Phase 1 Agent α, β, γ, ε 4개 브리핑 **동시** 전달 (한 메시지에 4 Agent 호출)
- [ ] 4 에이전트 결과 회수
- [ ] 파일 오너십 준수 여부 검사 (`git diff --stat`)

#### Day 2 (Phase 1 검증 + Phase 2 시작)
- [ ] 각 파일별 pytest 실행
- [ ] typecheck 실행
- [ ] 성공 시 Phase 2 Agent α, β 2개 브리핑 동시 전달

#### Day 4 (Phase 2 검증 + Phase 3)
- [ ] 대표 케이스 smoke test
- [ ] Phase 3 Agent ζ 브리핑 (단독)

#### Day 5~7 (Phase 3 검증 + Phase 4)
- [ ] 전체 pytest
- [ ] 실제 API 호출 테스트
- [ ] 골든셋 재실행
- [ ] 3개 기준 충족 시 flag canary

---

## 9. 위험·대안

### 9.1 본 계획이 실패할 수 있는 지점

1. **Phase 0 스코프 오해** — Result 타입이 잘못 설계되어 Phase 2에서 확장 불가능
   - 대안: Phase 0 결과를 사용자가 직접 리뷰, 필요 시 재작업
   
2. **테스트 fixture 누락** — conftest에서 노출하지 않은 fixture를 후속 Phase가 요구
   - 대안: Phase 1 시작 시 fixture 목록 공유, 부족하면 δ에게 재요청

3. **Phase 2 α의 4가지 작업이 너무 큼** — 단일 에이전트 컨텍스트 한계
   - 대안: Phase 2 α를 "매칭 계단만" + "Silent masking만" 두 하위 Phase로 분할

### 9.2 대안 경로

- **전부 순차** (안전): Phase 1~3을 모두 순차 실행 → 속도 희생, 충돌 리스크 0
- **워크트리 사용** (정밀): 각 Phase 1 에이전트를 별도 worktree에서 실행 → 사용자 병합 부담

### 9.3 레거시 처리 원칙

본 계획서는 5유형 레거시를 다음과 같이 분류·처리한다:

| 유형 | 대상 | 처리 방침 | 수행 Wave |
|---|---|---|---|
| **L1** Dead code | f1_step_b.py의 `_levenshtein`, `_match_ingredient_hits`, `_lookup_synonym` | 삭제가 아닌 "호출 복구" 방향 | Wave A-1 |
| **L2** Legacy 서비스 파일 | `step1_ingredients_check.py`, `step3_standards.py` | Phase 0에서 호출 여부 탐지 → 사용자 판정 | Wave B-6 또는 즉시 |
| **L3** Feature flag 분기 잔재 | `F1_USE_DATA_GO_KR_API=false` 경로 등 | A-5 canary 100% 안정 후 제거 | Wave C |
| **L4** Skip된 테스트 | `_LEGACY_15111777` 마크 8개 | Wave A-1에서 재활성 시도, 불가한 것은 삭제 | Wave A-1 + Wave B 종료 |
| **L5** 판정 룰 불일치 | `step1_ingredients_check.py` 와 `f1_step_a.py` 의 매칭 룰 공존 | Phase 0에서 실 호출 확인 후 단일화 | L2와 동시 처리 |

**원칙**:

1. **"사용되지 않는 것"과 "레거시인 것"은 다르다** — 사용 여부를 grep으로 먼저 확인
2. **Wave A 착수 전에 호출 여부 선확인** — Phase 0의 레거시 탐지 책임
3. **제거는 "새 것이 안정화된 뒤"에** — A-5 canary 100% 이후에 L3 제거, Wave B 종료 전 L2 보존
4. **Dead code(L1)는 Wave A의 부활 대상** — 그대로 두고 호출 경로만 복구

**Phase 0 탐지 결과에 따른 분기** (사용자 결정):

```
L2 파일이 여전히 호출됨
  ├─ 호출자가 레거시 경로일 뿐 실제 트래픽 없음 → Wave B-6 보존, 최종 단일화
  ├─ 호출자가 v2 경로와 병렬 실행됨 (L5) → 즉시 Wave A-1 범위 확장하여 단일화
  └─ 호출자가 사용자·테스트 양쪽 → 호출자 마이그레이션 플랜 별도 수립

L2 파일이 호출되지 않음
  └─ Phase 0 내에서 즉시 삭제 또는 Wave B-6에 예약 (사용자 선택)
```

---

## 10. 이어받기 가이드

다음 세션에서 이 계획을 이어받는 사람(또는 사용자)이 해야 할 일:

1. **선행 문서 3개 읽기** (diagnosis → root-cause → redesign-plan) 후 이 문서
2. **현재 Phase 확인** — docs/f1-parallel-progress.md 같은 진행 기록이 있는지 (없으면 git log로 추정)
3. **BC 브랜치 상태 검증** — 미커밋 변경, 현재까지 완료된 Phase 커밋
4. **다음 Phase 브리핑 준비** — §4의 템플릿을 현재 상태에 맞게 조정
5. **사용자 승인** 후 Agent 도구 호출

---

**끝.**
