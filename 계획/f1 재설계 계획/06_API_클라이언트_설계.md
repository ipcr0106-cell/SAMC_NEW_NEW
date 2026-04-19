# 06. data.go.kr API 클라이언트 설계

> 의존: [F1_공공데이터_API_탐색보고서.md](./F1_공공데이터_API_탐색보고서.md)
> 산출물: `backend/services/data_go_kr/`

---

## 1. 목적

공공데이터포털 4개 API를 통합 호출하는 공통 클라이언트 구현. Step A/B/C 어디서든 동일 인터페이스로 사용.

---

## 2. 모듈 구조

```
backend/services/data_go_kr/
├── __init__.py
├── client.py              # 공통 HTTP 클라이언트 (httpx 기반)
├── endpoints.py           # 4개 API 엔드포인트·파라미터 정의
├── models.py              # 응답 Pydantic 모델 (API별)
├── cache.py               # 응답 캐시 (Supabase 또는 Redis)
└── exceptions.py          # 도메인 에러 (→ 08_에러_처리_설계 참조)
```

---

## 3. 공통 클라이언트 시그니처

```python
# services/data_go_kr/client.py
class DataGoKrClient:
    def __init__(
        self,
        api_key: str = env("F1_DATA_GO_KR_API_KEY"),
        timeout: float = 15.0,
        max_retries: int = 3,
        cache: Optional[ResponseCache] = None,
    ): ...

    async def call(
        self,
        endpoint: Endpoint,
        params: dict[str, Any],
        *,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """공통 호출 — 캐시 확인 → HTTP GET → 재시도 → 파싱 → 캐시 저장."""
```

**호출 흐름:**
1. 캐시 키 생성: `sha256(endpoint_id + sorted(params))`
2. 캐시 HIT → 즉시 반환
3. HTTP GET (httpx, 재시도 정책: exponential backoff, 429/500/503)
4. `resultCode != "00"` → `DataGoKrApiError` 발생
5. `body.items` 정규화 후 반환
6. 캐시 저장 (TTL 24h 기본)

---

## 4. 엔드포인트 정의

```python
# services/data_go_kr/endpoints.py
from dataclasses import dataclass

@dataclass(frozen=True)
class Endpoint:
    id: str            # "15111777"
    name: str
    url: str
    default_params: dict[str, str]

INGREDIENT_ALLOW = Endpoint(
    id="15111777",
    name="수입식품 원료정보",
    url="https://apis.data.go.kr/1471000/IprtFoodIngdInfoService/getIprtFoodIngdInfoService",
    default_params={"type": "json", "numOfRows": "10"},
)

COMPONENT_CODE = Endpoint(
    id="15094202",
    name="수입식품 성분코드 정보",
    url="https://apis.data.go.kr/1471000/IprtFoodCpntCdInfoFoodService/getIprtFoodCpntCdInfoFoodInq",
    default_params={"type": "json", "numOfRows": "10"},
)

ADDITIVE_STD = Endpoint(
    id="15116583",
    name="식품첨가물 기준규격 현황",
    url="https://apis.data.go.kr/1471000/FoodWStndStusService/getFoodWStndStusList",
    default_params={"type": "json", "numOfRows": "50"},   # T_KOR_NM별 분리로 많이 필요
)

RAWMTRL_GMO = Endpoint(
    id="15111913",
    name="식품 원재료 정보 조회",
    url="https://apis.data.go.kr/1471000/FoodRwmtInfo/getFoodRwmtInfo",
    default_params={"type": "json", "numOfRows": "10"},
)
```

---

## 5. 고수준 API (Step 서비스에서 직접 호출)

```python
# services/data_go_kr/client.py

async def lookup_ingredient(name: str) -> list[IngredientInfo]:
    """15111777 — 원재료명으로 허용여부·조건 조회."""

async def lookup_component_code(name: str) -> Optional[ComponentInfo]:
    """15094202 — 한/영/이명으로 성분코드 1건 조회."""

async def lookup_additive_standards(name: str) -> list[AdditiveSpec]:
    """15116583 — 품목명으로 모든 시험항목 조회 후 리스트 반환."""

async def lookup_gmo_flag(name: str) -> Optional[bool]:
    """15111913 — 원재료명으로 GMO_YN 조회. True/False/None(미등록)."""
```

**모두 async 기반**: Step B에서 원재료 N건을 `asyncio.gather()`로 병렬 조회.

---

## 6. 캐시 전략

| 항목 | 값 |
|------|---|
| 저장소 | Supabase `f1_data_go_kr_cache` 테이블 (별도 Redis 도입 지양) |
| 스키마 | `(cache_key TEXT PK, endpoint_id TEXT, response JSONB, expires_at TIMESTAMPTZ)` |
| TTL | 24시간 기본, `15116583`은 7일 (거의 안 바뀜) |
| Miss 시 | HTTP 호출 → 저장 후 반환 |
| 만료 처리 | PostgreSQL 파티션 OR cron 삭제 작업 |
| 무효화 | 관리자 API `POST /admin/data-go-kr/cache/clear` |

**캐시 히트율 목표:** 70%+ (동일 원재료 반복 조회 가정)

---

## 7. Rate Limit 대응

| 계정 | 일일 한도 | 현재 전략 |
|------|-----------|-----------|
| 개발계정 | 10,000건/월 | 원재료 N건 ≤ 20 가정, 케이스당 80~120 call → 월 ~80 케이스 처리 한계 |
| 운영계정 (심의 후) | 대량 (신청 시 결정) | 제한 완화 |

**방어선:**
1. 캐시 우선 조회
2. 원재료 이름 정규화(`.strip()`, 동의어 → 대표어) 후 조회 → 중복 제거
3. 일일 호출 카운터 (`data_go_kr_call_log` 테이블) → 임계치 근접 시 담당자 알림
4. 임계치 초과 시 `RateLimitExceededError` 발생 → HITL-1 에스컬레이션

---

## 8. 재시도 정책

| 상태 | 동작 |
|------|------|
| 2xx | 즉시 성공 |
| 429 | 2s / 4s / 8s backoff 후 재시도 (최대 3회) |
| 500·503 | 1s / 2s / 4s 재시도 |
| 404 | 재시도 없음 — 엔드포인트 오류로 간주, `ConfigError` |
| 네트워크 오류 | 1s 고정 interval 재시도 |
| 최종 실패 | `DataGoKrApiError(transient=True/False)` |

---

## 9. 테스트 포인트

- [ ] 캐시 HIT 시 HTTP 호출이 일어나지 않는가 (mock assert)
- [ ] `resultCode != "00"` 응답 시 `DataGoKrApiError` 발생
- [ ] 429 응답 후 backoff로 성공하는가
- [ ] `lookup_ingredient("대두")` 호출 시 `EDIBLE_INFO` 필드가 모델에 정확히 반영
- [ ] 동일 원재료 10회 병렬 조회 시 HTTP 호출 1회만 발생
- [ ] `KOR_NM` 앞 공백이 `.strip()` 처리되어 모델에 들어가는가

---

## 10. 남은 결정사항

- 🟡 캐시 저장소: Supabase vs Redis (운영 규모 따라)
- 🟡 `f1_data_go_kr_cache` 테이블 마이그레이션은 P1에서 함께 생성
- 🟡 일일 호출 카운터 UI 위치 (관리자 대시보드?)
