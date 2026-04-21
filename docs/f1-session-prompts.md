# F1 Wave A 병렬 구현 — 세션 시작 프롬프트 모음

**작성일**: 2026-04-20
**용도**: Claude Code 새 세션에서 F1 Wave A 병렬 구현을 이어받을 때 사용할 프롬프트

**관련 문서**:
- [f1-diagnosis-2026-04-20.md](./f1-diagnosis-2026-04-20.md)
- [f1-root-cause-2026-04-20.md](./f1-root-cause-2026-04-20.md)
- [f1-redesign-plan-2026-04-20.md](./f1-redesign-plan-2026-04-20.md)
- [f1-parallel-execution-plan-2026-04-20.md](./f1-parallel-execution-plan-2026-04-20.md)

---

## 0. 개요

본 문서는 세션이 끊기거나 새로 시작할 때 Claude Code에게 전달할 **초기 프롬프트 3종**을 보관한다. 상황에 맞는 버전을 복사하여 사용한다.

### 사용 가이드

| 버전 | 사용 시점 | 기대 동작 |
|---|---|---|
| **V1 콜드 시작** | Phase 0 착수 전, 미커밋 변경이 정리되지 않음 | 문서 읽기 → 미커밋 변경 분석 → 처리 방침 제안 |
| **V2 Phase 0 실행** | 미커밋 정리 완료, Phase 0 바로 착수 | 공통 계약 3파일 생성 (Agent δ 호출) |
| **V3 중간 복귀** | 일부 Phase 완료, 현재 상태 불확실 | 상태 자동 탐지 → 다음 Phase 제안 |

### 공통 원칙 (모든 버전에 내장)

1. 파일 생성/수정 전 사용자 승인 필수
2. 감독 lane 역할 (에이전트 호출·검증은 Claude, 통합·의사결정은 사용자)
3. 파일 오너십 규칙 준수 (같은 Phase 에이전트가 같은 파일 수정 금지)
4. Self-contained (이전 대화 맥락 불필요)

---

## V1. 콜드 시작 프롬프트

**언제 쓰는가**: 세션 리셋 후 아무것도 진행 안 됨. 미커밋 변경(9+1개)이 그대로 있음. 가장 안전한 시작점.

**복사해서 붙여넣을 것**:

```
F1 Wave A 병렬 구현을 이어받아 감독하겠습니다.

## 프로젝트
C:\GITHUB\SAMC_NEW_NEW (BC 브랜치)

## 배경
이전 세션에서 F1 수입가부 판정 시스템의 3차 진단을 수행하여 27개 결함을
식별하고, AI 에이전트 병렬 실행 계획을 수립했습니다. 실행은 아직 시작되지
않았습니다.

## 필수 참조 문서 (docs/, 이 순서로 읽을 것)
1. docs/f1-diagnosis-2026-04-20.md           — 27개 결함 맵
2. docs/f1-root-cause-2026-04-20.md          — 2원인 수렴 논증
3. docs/f1-redesign-plan-2026-04-20.md       — Wave A/B/C 계획
4. docs/f1-parallel-execution-plan-2026-04-20.md — 병렬 실행 4-Phase 계획

## 당신의 역할 (감독 lane 보조)
- 각 Phase의 에이전트 브리핑을 내 승인 후 Agent 도구로 호출
- Phase 간 검증 체크포인트 수행
- 파일 오너십 감시 (같은 Phase 에이전트가 같은 파일 수정 금지)
- 실패 시나리오 감지·회복 제안
- 파일 생성/수정 전 반드시 내 승인 받을 것

## 선결 과제 (Phase 0 착수 전)
BC 브랜치에 미커밋 변경이 다음과 같이 있습니다:
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

이 변경들이 Wave A 계획과 어떤 관계인지(선작업/충돌/무관) 분석이
필요합니다.

## 첫 작업 요청
1. 위 4개 문서를 먼저 읽고 현재 상태·계획을 파악
2. 미커밋 각 파일의 git diff를 확인하여 Wave A 계획과의 관계를
   구조화된 표로 보고 (선작업 / 충돌 / 무관)
3. 처리 방침(커밋·stash·revert) 제안
4. 내 승인 후에만 실제 작업 착수

파일 생성/수정 금지. 이번 턴은 분석·제안·질문만.
```

**예상 첫 응답**:
- 4개 문서 Read 실행
- `git status`, `git diff` 실행
- 미커밋 9개 파일 × Wave A 계획 관계 표
- 커밋/stash 권장안
- 사용자 결정 대기

---

## V2. Phase 0 바로 실행 프롬프트

**언제 쓰는가**: 미커밋 정리 완료. 공통 계약 3파일(result.py, match_method.py, conftest.py)을 바로 만들고 싶을 때.

**복사해서 붙여넣을 것**:

```
F1 Wave A Phase 0 (공통 계약 작성)을 바로 착수합니다.

## 프로젝트·문서
C:\GITHUB\SAMC_NEW_NEW (BC 브랜치)
docs/f1-parallel-execution-plan-2026-04-20.md §3 Phase 0 및 §4.1 브리핑
템플릿 참조.

## 상태
- 미커밋 변경은 정리 완료 (커밋 또는 stash 처리됨)
- Wave A 다른 Phase는 미착수
- 이제 Phase 0 산출물 3파일 + 레거시 탐지 보고:
  1. backend/common/result.py
  2. backend/common/match_method.py
  3. backend/tests/conftest.py
  4. 레거시 탐지 보고서 (L2/L5, 표 형식)
     — docs/f1-parallel-execution-plan-2026-04-20.md §3 Phase 0 및 §9.3 참조

## 실행 방법
docs/f1-parallel-execution-plan-2026-04-20.md §4.1의 Agent δ 브리핑
템플릿을 Agent 도구에 투입하여 실행.

단, 다음 단계를 먼저 수행한 뒤 실행:
1. §4.1 브리핑 템플릿을 그대로 사용할지, 현재 상태에 맞게 조정이
   필요한지 먼저 내게 확인
2. 내가 OK하면 Agent 도구 호출
3. 결과 수신 후 §5.1 Phase 0 → Phase 1 체크포인트 수행
4. 검증 통과 후 내게 보고, Phase 1 진입 승인 대기

파일 생성/수정 전 반드시 내 승인 받을 것.
```

**예상 첫 응답**:
- docs/f1-parallel-execution-plan-2026-04-20.md §3, §4.1 Read
- 브리핑 템플릿 원문 제시
- 조정 필요 여부 질문
- 사용자 OK 후 Agent 도구 호출

---

## V3. 중간 복귀 프롬프트 (상태 탐지 모드)

**언제 쓰는가**: Phase 일부 완료된 상태. 어디까지 끝났는지 불확실. 혹은 여러 날이 지나 맥락을 잃음.

**복사해서 붙여넣을 것**:

```
F1 Wave A 병렬 구현 도중에 이어받습니다. 현재 어느 Phase까지 진행됐는지
자동으로 탐지하여 다음 단계를 제안해 주세요.

## 프로젝트·문서
C:\GITHUB\SAMC_NEW_NEW (BC 브랜치)
docs/f1-*.md 4개 문서 참조 (특히 parallel-execution-plan).

## 상태 탐지 절차
1. `git log --oneline -20` 으로 최근 커밋 확인
2. 다음 파일들의 존재·내용을 검사해서 어느 Phase까지 끝났는지 추정:
   - backend/common/result.py 존재 여부 → Phase 0 완료
   - backend/common/match_method.py 존재 여부 → Phase 0 완료
   - backend/tests/conftest.py 존재 여부 → Phase 0 완료
   - f1_step_a.py 의 SELECT에 name_en/aliases 포함 여부 → Phase 1 α 완료
   - f1_step_c.py 의 except Exception 패턴 제거 여부 → Phase 1 β 완료
   - feature_flags.py 의 F1_STEP_D_MIN_SCORE 존재 여부 → Phase 1 γ 완료
   - frontend StatusBanner.tsx 존재 여부 → Phase 1 ε 완료
   - f1_step_b.py 의 match_method 설정 여부 → Phase 2 α 완료
   - f1_step_d.py 의 dedup·MIN_SCORE env 사용 여부 → Phase 2 β 완료
   - feature1.py 의 asyncio.wait_for 사용 여부 → Phase 3 완료

3. 진행 상태 표로 보고 (Phase/Agent/완료 여부/증거)
4. 다음 수행할 Phase·Agent 제안
5. 해당 Agent 브리핑을 §4에서 가져와 실행 여부 내게 확인

파일 생성/수정 금지. 상태 탐지·보고·제안만.
```

**예상 첫 응답**:
- git log 확인
- 위 10가지 탐지 항목 병렬 Grep/Read
- 진행 상태 표
- 다음 Phase·Agent 제안
- 사용자 승인 대기

---

## 프롬프트 커스터마이즈 가이드

### 공통 수정 포인트

- **프로젝트 경로**: 다른 머신에서 경로가 다르면 `C:\GITHUB\SAMC_NEW_NEW`를 교체
- **브랜치명**: BC가 아닌 다른 브랜치면 교체
- **미커밋 파일 목록** (V1): 세션 시점에 따라 다를 수 있으므로 `git status`로 확인 후 갱신

### Wave 확장 시

Wave B 또는 C 착수 시 V2·V3를 다음과 같이 복제·수정:
- `Wave A` → `Wave B`
- 참조 섹션을 `f1-redesign-plan §2` (Wave B) 또는 `§3` (Wave C)으로 변경
- 파일 오너십 행렬을 Wave B/C 계획에 맞게 재설계 (본 병렬 계획서는 Wave A 전용)

### Phase별 특수 프롬프트 추가

특정 Phase에서만 쓸 프롬프트가 필요하면 아래 템플릿 기반으로 추가:

```
F1 Wave A Phase [N] ([Phase명])을 실행합니다.

참조: docs/f1-parallel-execution-plan-2026-04-20.md §3 Phase [N], §4.[X]

## 선행 조건
- Phase [N-1]까지 완료 (§5.[N-1] 체크포인트 통과)
- [필요한 선행 산출물 명시]

## 실행
§4.[X]의 Agent [ID] 브리핑 템플릿을 Agent 도구에 투입.

절차:
1. 브리핑 템플릿 확인 → 내게 확인
2. 승인 후 Agent 호출 (여러 Agent가 병렬 가능하면 한 메시지에 다중 호출)
3. 결과 수신 → §5.[N] 체크포인트 수행
4. 내게 보고, 다음 Phase 진입 승인 대기
```

---

## 프롬프트 실패 시 대응

### 상황 1 — Claude가 바로 파일 수정 시작
**원인**: "파일 생성/수정 전 내 승인" 지시 무시
**조치**: 중단 명령 후, V1 재투입 + "마지막 문장을 반드시 준수할 것" 강조

### 상황 2 — Claude가 문서를 안 읽고 추측으로 응답
**원인**: 문서 읽기 지시 무시
**조치**: "위 4개 문서를 먼저 Read로 읽은 뒤 응답하세요. 읽지 않았다면 응답하지 마세요." 추가

### 상황 3 — Claude가 Phase 순서를 어김
**원인**: 계획 문서 이해 부족
**조치**: `docs/f1-parallel-execution-plan-2026-04-20.md §3` 를 섹션 단위로 Read 후 재시도 요청

---

**끝.**
