# F1 수입가부 판정 시스템 진단 보고서

**작성일**: 2026-04-20
**대상 브랜치**: BC
**진단 방법**: 3차 병렬 에이전트 탐색 (총 12개 영역)

**관련 문서**:
- [f1-root-cause-2026-04-20.md](./f1-root-cause-2026-04-20.md) — 두 가지 진짜 원인 분석
- [f1-redesign-plan-2026-04-20.md](./f1-redesign-plan-2026-04-20.md) — Wave A/B/C 실행 계획

---

## 0. 개요

### 0.1 진단 배경

실무자가 F1 수입가부 판정 결과를 검토할 때 **"결과값이 전부 이상해서 사람이 그 안에서 개입할 수 없다"** 고 보고했다.

본 시스템의 설계 철학인 HITL (Human-In-The-Loop)은 "AI가 80% 맞고 사람이 20% 보정"을 전제하지만, 현재는 AI 결과의 신뢰도가 너무 낮아 **사람이 개입할 시작점조차 잡을 수 없는 상태**다.

### 0.2 설계 철학 재확인

> 현단계의 부족한 AI 판단을 실무자가 최종적으로 결정하는 것이 핵심이다.

HITL의 본질은 각 판정 단계마다 실무자가 **정보 + 선택지 + 근거 기록** 3종 세트를 갖고 채택·수정·기각할 수 있는 것이다. 현재 구현은 UI 골격은 HITL을 따르나, 상류 데이터 파이프라인의 오염으로 인해 실무자가 "AI가 맞는지 틀리는지"조차 판단할 수 없다.

### 0.3 진단 방법

1·2·3차에 걸쳐 각 3~4개의 읽기 전용 탐색 에이전트를 병렬 실행하여 총 12개 영역을 조사했다.

| 차수 | 조사 영역 |
|---|---|
| 1차 | 스키마 / 외부 API 호출 / 원재료 매칭 로직 / 법령 인용 구조 |
| 2차 | F0 OCR / Step C 기준치+단위환산 / Step A 금지 원재료 / HITL 상태기계+감사 로그 |
| 3차 | 프론트엔드 구조·렌더링 / 테스트 커버리지·품질 / Step B 세부 / 설정·feature flags·환경변수 |

---

## 1. 실무자 체감 증상

두 장의 스크린샷에서 관찰된 이상 증상:

| # | 증상 | 심각도 |
|---|---|---|
| S1 | 동일 원재료(밀가루)에 기준 5개가 매칭됨 — 중금속 5종이면 정상, 그 외는 확인 필요 | 🟡 |
| S2 | 기준치 단위 혼재 — `0.2 이하`, `10(mg/kg)`, `60이하`, `2(ppm)` | 🔴 |
| S3 | 배합비율(%) → 기준치 단위 환산이 표에 표시되지 않음 | 🔴 |
| S4 | "허위된 원재료 전체" 섹션명이 문맥상 어색 (오타 추정) | 🟠 |
| S5 | 법령 인용 5건과 기준규격 5건이 1:1 연결되지 않음 | 🔴 |
| S6 | 미확인 원재료 섹션에서 "밀가루"가 미확인으로 표시 | 🔴 |
| S7 | 에스컬레이션 인지 체크박스에 `step_b_unidentified` 코드명 노출 | 🔴 |

실무자의 종합 소견: **"도출되는 결과값이 전부 이상해서 사람이 그 안에서 개입할 수 없음."**

추가로 확인된 내부 진단 소견:
- **"법령 인용은 정확하나 중요도가 낮은 정보를 너무 많이 가져오는 경우가 다수"**
- **"DB/API 매칭 로직이 남용될 정도로 실패 흔함"**
- **"스키마 구조와 로직도 이상한 거 같고, API 사용을 실패하는 경향 있음"**

---

## 2. 27개 결함 전체 맵 (층별)

```
┌─ 보안/설정 층 (4건) ───────────────────────┐
│  13. .env 라이브 키 노출 (비공개 환경 확인)  🟠│
│  14. F1_RAG_VERDICT_DISABLED=true          🔴│
│  15. F1_REQUIRE_HITL0_APPROVAL=false       🔴│
│  16. _MIN_SCORE=0.2 하드코딩                🟠│
└───────────────────────────────────────────┘
┌─ API 층 (2건) ──────────────────────────────┐
│   1. Silent Error Masking                  🔴│
│   6. gather 무제한 타임아웃                  🔴│
└───────────────────────────────────────────┘
┌─ 매칭 층 (8건) ─────────────────────────────┐
│   2. Stage 1만 작동 (Fuzzy/3-key/LLM dead)  🔴│
│   3. F0→F1 재매칭 루프 단절                  🔴│
│   7. Step A aliases 컬럼 미조회              🔴│
│   8. Step A name_en 컬럼 미조회              🔴│
│  10. legacy vs v2 판정 룰 불일치             🟠│
│  17. Fuzzy/Synonym 호출 경로 폐기 (dead code) 🟠│
│  18. match_method 필드 항상 None             🟠│
│  19. 재매칭 기능 완전 부재                   🔴│
└───────────────────────────────────────────┘
┌─ 기준규격 층 (2건) ─────────────────────────┐
│   5. 기준규격 ↔ 법령 연결 분리                🔴│
│  12. Step C no_data 통계적 실종              🟠│
└───────────────────────────────────────────┘
┌─ 법령 인용 층 (1건) ────────────────────────┐
│   4. 필터 붕괴 (MIN_SCORE·top_k·dedup)       🔴│
└───────────────────────────────────────────┘
┌─ HITL/감사 층 (2건) ────────────────────────┐
│   9. confidence 0.95 하드코딩                🟠│
│  11. f1_escalation_logs INSERT 부재          🔴│
└───────────────────────────────────────────┘
┌─ 프론트엔드 층 (4건) ────────────────────────┐
│  20. 전역 상태관리 없음 (재조회 시 손실)      🟠│
│  21. F0ApprovalPanel 618줄 모놀리식          🟡│
│  22. 근거 보기 UI 완전 미구현                🔴│
│  23. 접근성(ARIA) 부재                      🟠│
└───────────────────────────────────────────┘
┌─ 테스트·CI 층 (4건) ────────────────────────┐
│  24. CI/CD 없음 (.github/workflows 부재)    🔴│
│  25. conftest.py·글로벌 fixture 없음         🟠│
│  26. f1_escalation_logs INSERT 테스트 전무   🟠│
│  27. 법령 인용 건수 assertion 없음            🟠│
└───────────────────────────────────────────┘

범례: 🔴 치명 (HITL 작동 불가) | 🟠 주의 (품질 저하) | 🟡 경미
```

---

## 3. 결함 상세 테이블

### 3.1 API 층

| # | 결함 | 증상 | 근거 파일·라인 |
|---|---|---|---|
| 1 | Silent Error Masking — try/except가 예외를 빈 데이터로 치환 | 외부 API 실패가 "정상 빈 결과"로 둔갑 → UI에 침묵 실패 | f1_step_b.py:573~591, f1_step_c.py:490~494, f1_step_d.py:316~324, data_go_kr/client.py:569~577 |
| 6 | `asyncio.gather()` 전체 타임아웃 없음 (개별 타임아웃은 있으나) | 한 호출이 행(hang)하면 전체 파이프라인 블로킹 | feature1.py:692, 710, f1_step_b.py:624, f1_step_c.py:607 |

### 3.2 매칭 층

| # | 결함 | 증상 | 근거 |
|---|---|---|---|
| 2 | 매칭 엔진이 Stage 1(정확 매칭)만 작동 | "밀가루" 같은 흔한 원재료도 매칭 실패 | f1_step_b.py:239~244 (`_pick_exact_component_item`만 호출) |
| 3 | F0 편집 후 F1이 자동 재실행되지 않음 | 실무자가 대체원재료명 입력해도 판정 재계산 안 됨 | f1_hitl_service.py:115~179 (final_result만 갱신, F1 미실행) |
| 7 | Step A가 `aliases` 컬럼을 SELECT하지 않음 | "마리화나" 입력 시 "대마초" DB 미탐 (false negative) | f1_step_a.py:75~78 |
| 8 | Step A가 `name_en` 컬럼을 조회하지 않음 | "Cannabis" 등 영문 입력 회피 | f1_step_a.py:76 |
| 10 | legacy(`step1_ingredients_check.py`)와 v2(`f1_step_a.py`) 판정 룰 불일치 | legacy는 양방향 부분매칭, v2는 정확매칭만 — 같은 입력에 다른 결과 가능 | step1_ingredients_check.py:93 vs f1_step_a.py:90 |
| 17 | `_match_ingredient_hits()`와 `_lookup_synonym()` 호출 경로 부재 | P6-b에서 15111777 API 제거 시 fuzzy/synonym 경로도 함께 폐기 | f1_step_b.py:141~169 (Levenshtein 정의만), 52~96 (synonym 정의만) |
| 18 | `match_method` 필드가 Step B에서 설정되지 않음 | 실무자가 "어떤 키로 매칭됐는지" 추적 불가 | feature1.py:411~425 (`getattr(i, "match_method", None)` 항상 None) |
| 19 | 동일 원재료를 다른 이름으로 재시도하는 메커니즘 없음 | unidentified 원재료 자동 재매칭 불가 | f1_step_b.py:641~651 (`_query_key()` 단일 pass) |

### 3.3 기준규격 층

| # | 결함 | 증상 | 근거 |
|---|---|---|---|
| 5 | `evidence_laws[]` (Step D)와 `standards_check[].law_ref` (Step C)가 분리 전송 | 실무자가 "이 기준치의 근거 법령"을 UI에서 추적 불가 | feature1.py:500~514 (두 리스트 분리) |
| 12 | Step C에서 기준 0건 원재료를 `checks`에 기록조차 하지 않음 | 검증 불가 상태가 UI에서 "통과"처럼 보일 위험 | f1_step_c.py:623~626 |

### 3.4 법령 인용 층

| # | 결함 | 증상 | 근거 |
|---|---|---|---|
| 4 | 필터 3중 실패 — MIN_SCORE=0.2 (약함), top_k 이중제한, 중복 제거 없음 | 관련성 낮은 법령이 대량 혼입 (Signal-to-Noise 붕괴) | f1_step_d.py:94 (_MIN_SCORE), 272, 287, 334, 348 |

### 3.5 HITL/감사 층

| # | 결함 | 증상 | 근거 |
|---|---|---|---|
| 9 | Step A forbidden hit의 confidence가 0.95 하드코딩 | drug/endangered/unauthorized/toxin 카테고리별 차등 없음 | feature1.py:377 |
| 11 | `f1_escalation_logs` 테이블에 실제 INSERT 호출이 코드에 없음 | 에스컬레이션이 메모리(`_internal.escalations`)에만 기록되고 DB 감사 추적 불가 | migration 007 정의 OK, f1_hitl_service.py:278~282는 계산만 |

### 3.6 보안/설정 층

| # | 결함 | 증상 | 근거 |
|---|---|---|---|
| 13 | `.env` 라이브 키 노출 가능성 (현재 비공개·로컬 확인됨) | 추후 퍼블릭 전환 시 문제, 로컬 유출 시 대응 필요 | .env 직접 검사 결과 |
| 14 | `F1_RAG_VERDICT_DISABLED=true` — RAG가 판정에 기여 못함 | 법령 인용이 UI에 나열만 되고 판정 주도에서 빠짐 (S5 증상의 구조적 원인) | feature_flags.py:53~65 |
| 15 | `F1_REQUIRE_HITL0_APPROVAL=false` — F0 승인 게이트 무력 | F0 결과가 미승인인 상태에서도 F1 실행 가능 (HITL-0 우회) | feature_flags.py:55 |
| 16 | `_MIN_SCORE=0.2`가 env 외부화되지 않음 | 운영 중 튠 불가 | f1_step_d.py:94 |

### 3.7 프론트엔드 층

| # | 결함 | 증상 | 근거 |
|---|---|---|---|
| 20 | 전역 상태관리(zustand/redux) 없음, useState 남용 | `fetchResult()` 재호출 시 HITL-1 중간 작업·F0 편집 상태 소실 | ImportCheckPage.tsx:69~84 |
| 21 | F0ApprovalPanel 컴포넌트 618줄 모놀리식 (BasicInfoEditor+IngredientEditor+ProcessCodeEditor 내부 정의) | 재사용·테스트·유지보수 곤란 | F0ApprovalPanel.tsx |
| 22 | "근거 보기" 모달/드로어 완전 미구현 | 법령 원문·매칭 후보·API raw 응답을 실무자가 확인 불가 | LawCitationCard.tsx 53줄, 모달 호출 없음 |
| 23 | aria-label, 키보드 탐색, ESC 닫기 등 접근성 기능 극소 | 보조 기술 사용 불가 | EscalationAckList.tsx:33 외 극소 |

### 3.8 테스트·CI 층

| # | 결함 | 증상 | 근거 |
|---|---|---|---|
| 24 | `.github/workflows/` 부재 | 변경마다 수동 pytest 실행 → 리그레션 감지 지연 | 디렉토리 자체 없음 |
| 25 | conftest.py·글로벌 fixture 없음 | 테스트 중복, mock·seed 패턴 산발 | backend/tests/ 루트 |
| 26 | f1_escalation_logs 저장 경로 테스트 전무 | 결함 11을 방어할 리그레션 테스트 없음 | backend/tests/services/ |
| 27 | 법령 인용 건수·중복 제한 assertion 없음 | 결함 4(S/N 붕괴)를 방어할 테스트 없음 | test_f1_step_d.py |

---

## 4. 건전한 자산 목록

리팩터 시 **건드리지 않고 재활용**할 구조·코드:

| 영역 | 자산 | 이유 |
|---|---|---|
| 스키마 | f1_allowed_ingredients + f1_ingredient_synonyms | 3-key 매칭 가능 스키마 완비 |
| 스키마 | f1_law_cache + f1_law_articles (1:N) | 법령 2단계 정규화 견실 |
| 스키마 | f1_audit_log (migration 018) | 감사 로그 스키마 설계 명확 |
| 스키마 | f1_escalation_logs (migration 007) | 스키마는 OK, INSERT만 추가하면 됨 |
| 코드 | DataGoKrClient (재시도·백오프·cache) | 개별 API 호출 복원력 우수 |
| 코드 | unit_converter 모듈 (normalize_to_common_unit) | 한글·한자·복합단위 파싱 견실, 테스트 100% 목표 |
| 코드 | f1_hitl_service 상태 전이 로직 | PipelineStepStatus 9상태 + audit 전이점 완비 |
| 코드 | F0 OCR 파이프라인 (ocr_service, parsing_service, label_image_service) | 5종 문서 OCR + LLM 파싱 + HITL-0 승인 게이트 완비 |
| 프론트 | 디자인 토큰 + ds-* 공통 클래스 | 일관성 기반 있음 |
| 프론트 | StatusBadge 컴포넌트 | 상태 시각화 정확 |
| 테스트 | test_unit_converter* (864줄) | 단위 환산 커버리지 양호 |
| 테스트 | Step A/B/C 단위 테스트 (약 6,254줄) | 핵심 서비스 커버 범위 적절 |

---

## 5. 근거 파일·라인 인덱스

자주 참조될 파일 모음 (결함 번호 → 파일:라인):

```
backend/services/
  f1_step_a.py
    :75~78     결함 7, 8 — 조회 컬럼 누락
    :88~90     결함 10 — 정확 매칭만

  f1_step_b.py
    :52~96     결함 17 — _lookup_synonym 미호출
    :141~169   결함 17 — _levenshtein dead code
    :239~244   결함 2 — Stage 1만 호출
    :300~306   결함 17 — _split_aliases 부분 호출
    :491       결함 17 — _pick_component_code에서 유일 호출
    :573~591   결함 1 — _safe_call Silent masking
    :624       결함 6 — gather 무제한
    :641~651   결함 19 — 단일 pass 매칭

  f1_step_c.py
    :187~217   (건전) _is_applicable 식품유형 필터
    :490~494   결함 1 — Silent masking
    :607       결함 6 — gather 무제한
    :623~626   결함 12 — 기준 0건 실종

  f1_step_d.py
    :94        결함 16 — _MIN_SCORE 하드코딩
    :272,287   결함 4 — top_k 이중제한
    :316~324   결함 1 — Silent masking
    :334,348   결함 4 — 약한 필터

  feature1.py
    :319,377   결함 9 — 0.95 하드코딩
    :411~425   결함 18 — match_method None
    :500~514   결함 5 — 기준↔법령 분리
    :692,710   결함 6 — gather 무제한

  f1_hitl_service.py
    :115~179   결함 3 — F0 편집 → F1 미실행
    :278~282   결함 11 — 메모리만, DB 미저장

backend/config/
  feature_flags.py:53~65   결함 14, 15

frontend/features/feature1/
  ImportCheckPage.tsx:69~84,145~147  결함 20
  F0ApprovalPanel.tsx (618줄 전체)   결함 21
  LawCitationCard.tsx (53줄)         결함 22

backend/db/migrations/
  002_f1_allowed_ingredients.sql     (건전) 3-key 스키마
  005_f1_ingredient_synonyms.sql     (건전) 별칭 테이블
  007_f1_escalation_logs.sql         결함 11 — 스키마만
  018_f1_audit_log.sql               (건전) 감사 로그
  020_f1_law_cache.sql               (건전) 법령 2단계 정규화
```

---

**다음 단계**: [f1-root-cause-2026-04-20.md](./f1-root-cause-2026-04-20.md) — 27개 결함이 왜 "2개의 진짜 원인"으로 수렴되는지 분석
