# Wave 1 subagent 프롬프트 템플릿

> 작성일: 2026-04-20 (모델 A 전환 2026-04-20)
> 용도: 모델 A — **부모 세션이 `Agent()` 도구를 4개 병렬 호출**할 때의 프롬프트 본문
> 선행: [14_병렬실행_계획.md §8-2](./14_병렬실행_계획.md) 모델 A 운영 규칙

---

## 공통 전제 (모든 Agent())

- **워크스페이스**: `C:\GITHUB\SAMC_NEW_NEW\` (단일)
- **브랜치**: `feature/f1-wave1` (부모 세션이 선행 생성·체크아웃 완료)
- **Day 0 스켈레톤**: `backend/exceptions.py`, `backend/models/f1_types.py`, `backend/services/data_go_kr/client.py` — 부모 세션이 이미 커밋하여 동결. subagent는 **스켈레톤 시그니처 준수하여 확장만** 수행, 시그니처 변경 금지.
- **응답 언어**: 한국어
- **OMC 규약**: 선택지 2~4개, 추천 표시, AskUserQuestion 버튼 UI(서브에이전트 레벨에서 결정 필요 시), 설계 범위 내 구현은 자율 판단

---

## W1-A — data.go.kr API 클라이언트

```
F1 재설계 Wave 1 W1-A 트랙 담당 subagent.

📄 컨텍스트 로드:
  - 계획/f1 재설계 계획/14_병렬실행_계획.md §4, §8-2
  - 계획/f1 재설계 계획/06_API_클라이언트_설계.md (전체)
  - backend/services/data_go_kr/client.py (Day 0 스켈레톤 — 시그니처 유지하며 본체 구현)
  - backend/exceptions.py (Day 0 스켈레톤 — import 하여 사용, 정의 변경 금지)
  - backend/models/f1_types.py (DataGoKrEndpoint Enum 참조)
  - backend/.env — F1_DATA_GO_KR_API_KEY 확인

🎯 작업:
  - backend/services/data_go_kr/ 패키지 본체 구현
  - 4종 엔드포인트 클라이언트:
      15111913 /getFoodRwmtInfo             (식품 원재료 / GMO)
      15094202 /getIprtFoodCpntCdInfoFoodInq (수입식품 성분코드)
      15116583 /getFoodWStndStusList        (첨가물 기준)
      15111777 /getIprtFoodIngdInfoService  (수입식품 원료)
  - 캐시 레이어 (Supabase f1_data_go_kr_cache), 재시도 (httpx + backoff)
  - W1-C가 제공할 circuit_breaker.py import 포인트만 준비 (mock 가능)
  - backend/db/migrations/016_f1_data_go_kr_infra.sql 작성
  - 단위테스트 (httpx_mock) + 실응답 픽스처

🚫 편집 금지 (다른 트랙 소유):
  - backend/models/f1_*.py, backend/models/judgment.py          (W1-B)
  - backend/exceptions.py 정의 변경                              (W1-C — import만 허용)
  - backend/utils/unit_converter.py                              (W1-D)
  - backend/services/feature1.py, 계획/**/*.md                   (부모 세션)

📏 완료 정의:
  - 06번 §2 필드 매트릭스 통과
  - 4 엔드포인트 각 1건 실응답 저장 (backend/tests/fixtures/data_go_kr/*.json)
  - 단위테스트 커버리지 80%+
  - Circuit Breaker import 인터페이스 준수 (실제 로직은 W1-C가 채움)
  - Day 0 스켈레톤 `DataGoKrClient` 4개 메서드 시그니처 유지

📦 산출물 요약 보고 (마지막 메시지):
  - 생성·수정 파일 목록
  - 테스트 실행 결과
  - 경계 외 편집 여부(없어야 함)
  - 추가 논의 필요 항목
```

---

## W1-B — Pydantic 모델 확장 + 마이그레이션

```
F1 재설계 Wave 1 W1-B 트랙 담당 subagent.

📄 컨텍스트 로드:
  - 계획/f1 재설계 계획/14_병렬실행_계획.md §4, §8-2
  - 계획/f1 재설계 계획/07_데이터_모델_변경_설계.md (전체)
  - backend/models/f1_types.py (Day 0 스켈레톤 — Feature1Output 핵심 필드 동결)
  - backend/models/judgment.py (F1 필드 확장 영역만)

🎯 작업:
  - backend/models/f1_types.py 본체 확장 — Ingredient, StandardCheck, Feature1Output 전체 필드
  - backend/models/judgment.py F1 관련 필드 조정 (F2/F3/F4/F5 필드 금지)
  - 폐기 대상 모델 제거 정리 (07번/10번 폐기 목록 참조, 실제 DB DROP은 Wave 4)
  - frontend/types/pipeline.ts F1Ingredient 확장 (신규 필드 6개)
  - 모델-API 응답 간 매핑 테스트

🚫 편집 금지:
  - backend/services/data_go_kr/** 본체                           (W1-A)
  - backend/exceptions.py                                         (W1-C)
  - backend/utils/unit_converter.py                               (W1-D)
  - backend/services/feature1.py, 계획/**/*.md                    (부모 세션)
  - backend/models/judgment.py의 F2/F3/F4/F5 필드                  (다른 Feature)

📏 완료 정의:
  - 07번 §2 전체 모델 구현
  - Pydantic v2 호환
  - 단위테스트 (valid/invalid 케이스) 85%+
  - 타입 체크(mypy/pyright) 통과
  - Day 0 스켈레톤 `Feature1Output` 핵심 필드 + `DataGoKrEndpoint` Enum 유지

📦 산출물 요약 보고: 위 W1-A와 동일 포맷
```

---

## W1-C — 예외 계층 + Circuit Breaker

```
F1 재설계 Wave 1 W1-C 트랙 담당 subagent.

📄 컨텍스트 로드:
  - 계획/f1 재설계 계획/14_병렬실행_계획.md §4, §8-2
  - 계획/f1 재설계 계획/08_에러_처리_설계.md (전체)
  - backend/exceptions.py (Day 0 스켈레톤 — F1PipelineError 계열 시그니처 동결)

🎯 작업:
  - backend/exceptions.py 본체 확장 — 3계층 에러 매트릭스 (차단성/복구/품질저하)
  - backend/middleware/error_handler.py — HTTP 응답 매핑 (400/503/needs_review)
  - backend/services/data_go_kr/circuit_breaker.py — in-memory Circuit Breaker
      · CLOSED / OPEN / HALF_OPEN 상태 전이
      · W1-A의 DataGoKrClient가 import 하는 공개 인터페이스 제공
  - 로깅 표준화 + escalations[] 누적 규칙

⚠️ 인터페이스 계약:
  - Day 0 스켈레톤의 예외 클래스 시그니처(생성자 인자·속성)는 **동결**. 변경 필요 시 AskUserQuestion으로 부모 세션에 보고.

🚫 편집 금지:
  - backend/services/data_go_kr/client.py 및 주변 (W1-A 본체)
  - backend/models/f1_*.py, backend/models/judgment.py           (W1-B)
  - backend/utils/unit_converter.py                              (W1-D)
  - backend/services/feature1.py, 계획/**/*.md                   (부모 세션)

📏 완료 정의:
  - 08번 §3 에러 매트릭스 전수 커버
  - 단위테스트 (각 에러 케이스 raise/매핑 검증) 85%+
  - Circuit Breaker 상태 전이 테스트 통과
  - Day 0 exceptions.py 시그니처 유지

📦 산출물 요약 보고: 위와 동일 포맷
```

---

## W1-D — 단위 정규화 모듈

```
F1 재설계 Wave 1 W1-D 트랙 담당 subagent.

📄 컨텍스트 로드:
  - 계획/f1 재설계 계획/14_병렬실행_계획.md §4, §8-2
  - 계획/f1 재설계 계획/11_단위_정규화_모듈_설계.md (전체)
  - backend/utils/unit_converter.py 현재 구현 (있다면)

🎯 작업:
  - backend/utils/unit_converter.py 확장·신규
      · normalize_to_common_unit(value, from_unit, *, density) → (float, "mg/kg")
      · parse_numeric_spec(spec) → (min, max)
      · parse_non_numeric_spec(spec) → SpecEvaluation
  - backend/constants/density.py — 식품유형별 비중 테이블 초안
  - SpecEvaluation dataclass
  - 엣지케이스: 범위 표기(0.01~0.1), 부등호(이상/이하), "불검출"/"적합" 등

🚫 편집 금지:
  - backend/services/data_go_kr/**      (W1-A)
  - backend/models/f1_*.py              (W1-B)
  - backend/exceptions.py, backend/middleware/error_handler.py (W1-C)
  - backend/services/feature1.py, 계획/**/*.md (부모 세션)

📏 완료 정의:
  - 11번 §3 전체 변환 케이스 구현
  - 단위테스트 100% (수치 정확성 필수, 11번 §8 포인트 전원 통과)
  - 역변환 대칭성 검증
  - IU/kg → UnitIncompatibleError 동작 확인
  - 부등호·범위 표기 엣지케이스 문서화 (주석 또는 module docstring 최소)

📦 산출물 요약 보고: 위와 동일 포맷
```

---

## 리뷰 lane Agent() (부모 세션이 4 트랙 완료 후 호출)

### code-reviewer (opus)

```
Wave 1 4 트랙 전체 리뷰.

범위:
  - git diff feature/f1-wave1..main (Day 0 스켈레톤 커밋 이후 전체)
  - 경로별: data_go_kr/**, models/f1_*.py, exceptions.py, middleware/error_handler.py,
    utils/unit_converter.py, constants/density.py, db/migrations/016_*.sql, tests/**

중점 검토:
  1. Day 0 인터페이스 시그니처 준수 (exceptions 계열, Feature1Output, DataGoKrClient)
  2. 트랙 간 파일 경계 준수 (위 경로 외 편집 여부)
  3. SOLID 원칙 위반, 조기 최적화, 불필요 추상화
  4. 에러 처리 매트릭스 일관성 (08번 §3)
  5. 테스트 커버리지 (80~100% 트랙별 기준)
  6. 보안: API 키 노출, 쿼리 인젝션, 캐시 키 충돌

중대(🔴) / 권고(🟡) / 정보(🟢) 로 severity 구분하여 보고.
```

### verifier

```
Wave 1 종료 게이트 검증.

체크 항목:
  1. DataGoKrClient 실제 API 호출 테스트 1건 통과 (대두 or 아편)
  2. 마이그레이션 016 개발 환경 dry-run 성공 + rollback 가능성
  3. backend/exceptions.py 시그니처가 Day 0 스켈레톤과 일치 (`git diff <Day0 SHA>..HEAD -- backend/exceptions.py` 결과 분석)
  4. unit_converter 단위테스트 전수 통과 (pytest 결과 pass 비율)
  5. Day 0 스켈레톤 파일 3개의 핵심 시그니처가 Wave 1 최종 상태에서 유지되는지

각 항목별 증빙(명령·출력 인용) 포함하여 PASS/FAIL 판정. 실패 시 블로커 여부와 복구 경로 제안.
```
