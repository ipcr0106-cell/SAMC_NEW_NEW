"""F1 파이프라인 공통 예외 — Day 0 인터페이스 스켈레톤.

본 파일의 클래스 시그니처(생성자 인자·속성)는 **Wave 1 Day 0에 동결**되었다.
W1-A `DataGoKrClient`, W1-C 에러 핸들러가 공통 참조한다. 속성·키워드 이름 변경은
Wave 1 4 트랙 모두를 블로킹하므로 금지하며, 변경 필요 시 부모 세션 재협상이
필요하다.

W1-C 추가 (차단성 에러 계층):
    - F0NotCompletedError, F0NotApprovedError, NoIngredientsError
    - FoodTypeMissingError, ConfigError

참조: 계획/f1 재설계 계획/08_에러_처리_설계.md §3
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional


class F1PipelineError(Exception):
    """F1 파이프라인 에러 최상위 base."""

    code: str = "F1_PIPELINE_ERROR"
    transient: bool = False


class DataGoKrError(F1PipelineError):
    """data.go.kr API 호출 실패 base.

    Attributes:
        endpoint: data.go.kr 엔드포인트 id (예: "15111913")
        status_code: HTTP 상태 코드 (응답 없는 경우 None)
    """

    code = "DATA_GO_KR_ERROR"
    transient = True

    def __init__(
        self,
        message: str,
        *,
        endpoint: str,
        status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.endpoint = endpoint
        self.status_code = status_code


class DataGoKrTimeoutError(DataGoKrError):
    """data.go.kr 응답 지연·네트워크 타임아웃.

    Attributes:
        timeout_s: 초과된 타임아웃 임계값(초)
    """

    code = "DATA_GO_KR_TIMEOUT"
    transient = True

    def __init__(
        self,
        message: str,
        *,
        endpoint: str,
        timeout_s: float,
    ) -> None:
        super().__init__(message, endpoint=endpoint, status_code=None)
        self.timeout_s = timeout_s


class DataGoKrRateLimitError(DataGoKrError):
    """data.go.kr 호출 한도 초과 (429).

    Attributes:
        retry_after: 서버가 안내한 재시도 대기 시간(초, Retry-After 헤더)
    """

    code = "DATA_GO_KR_RATE_LIMIT"
    transient = False

    def __init__(
        self,
        message: str,
        *,
        endpoint: str,
        retry_after: Optional[int] = None,
    ) -> None:
        super().__init__(message, endpoint=endpoint, status_code=429)
        self.retry_after = retry_after


class DataGoKrInvalidResponseError(DataGoKrError):
    """data.go.kr 응답이 resultCode != "00" 또는 스키마 위반.

    Attributes:
        result_code: data.go.kr `resultCode` 값 (없으면 None)
    """

    code = "DATA_GO_KR_INVALID_RESPONSE"
    transient = False

    def __init__(
        self,
        message: str,
        *,
        endpoint: str,
        result_code: Optional[str] = None,
        status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message, endpoint=endpoint, status_code=status_code)
        self.result_code = result_code


class CircuitBreakerOpenError(F1PipelineError):
    """Circuit Breaker OPEN 상태에서 호출 차단.

    Attributes:
        endpoint: 차단된 엔드포인트 id
        reopen_at: 다음 HALF_OPEN 시도 예정 시각 (없으면 None)
    """

    code = "CIRCUIT_BREAKER_OPEN"
    transient = True

    def __init__(
        self,
        message: str,
        *,
        endpoint: str,
        reopen_at: Optional[datetime] = None,
    ) -> None:
        super().__init__(message)
        self.endpoint = endpoint
        self.reopen_at = reopen_at


# ============================================================
# ① 차단성 에러 계층 (W1-C 추가, 08_에러_처리_설계.md §3)
# Day 0 스켈레톤 클래스들과 동일 파일에 유지 (transient=False)
# ============================================================


class F0NotCompletedError(F1PipelineError):
    """F0(식품유형 분류) 단계가 완료되지 않아 F1 실행 불가.

    HTTP 400 으로 매핑된다.
    """

    code = "F0_NOT_COMPLETED"
    transient = False


class F0NotApprovedError(F1PipelineError):
    """F0 결과가 담당자(HITL-0)의 승인을 받지 않아 F1 실행 불가.

    HTTP 400 으로 매핑된다.
    """

    code = "F0_NOT_APPROVED"
    transient = False


class NoIngredientsError(F1PipelineError):
    """원재료 목록이 비어 있어 F1 파이프라인 진행 불가.

    HTTP 400 으로 매핑된다.
    """

    code = "NO_INGREDIENTS"
    transient = False


class FoodTypeMissingError(F1PipelineError):
    """식품유형(food_type) 정보가 누락되어 F1 실행 불가.

    HTTP 400 으로 매핑된다.
    """

    code = "FOOD_TYPE_MISSING"
    transient = False


class ConfigError(F1PipelineError):
    """환경 설정 오류 (엔드포인트 URL·API 키 누락 등).

    HTTP 500 으로 매핑된다. transient=False — 재시도해도 해결 불가.
    """

    code = "CONFIG_ERROR"
    transient = False
