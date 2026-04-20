"""F1 파이프라인 FastAPI exception handler 등록 헬퍼.

사용법:
    from middleware.error_handler import register_error_handlers
    register_error_handlers(app)

HTTP 매핑 (08_에러_처리_설계.md §4):
    - F0NotCompletedError / F0NotApprovedError / NoIngredientsError
      / FoodTypeMissingError → 400
    - ConfigError → 500
    - DataGoKrError(transient=True) → 503 + retry_after_s
    - DataGoKrError(transient=False) → 200 + status="needs_review"
    - CircuitBreakerOpenError → 503
    - F1PipelineError (기타) → 500

구조화 로깅: logger.error + extra dict (error_code, transient, case_id, step)
escalations[] 누적 유틸: `add_escalation()` 참조.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from exceptions import (
    F1PipelineError,
    F0NotCompletedError,
    F0NotApprovedError,
    NoIngredientsError,
    FoodTypeMissingError,
    ConfigError,
    DataGoKrError,
    CircuitBreakerOpenError,
)

logger = logging.getLogger("f1.error_handler")


# ============================================================
# escalations[] 누적 유틸
# ============================================================


def add_escalation(
    escalations: List[str],
    reason: str,
    *,
    dedup: bool = True,
) -> None:
    """Feature1Output.escalations[] 에 사유를 추가한다.

    Args:
        escalations: 누적 대상 리스트 (in-place 수정).
        reason: 추가할 사유 문자열 (예: "ingredient_unidentified").
        dedup: True 이면 중복 항목을 추가하지 않는다 (기본값).
    """
    if dedup and reason in escalations:
        return
    escalations.append(reason)


# ============================================================
# 공통 로깅 헬퍼
# ============================================================


def _log_error(
    exc: F1PipelineError,
    *,
    case_id: Optional[str] = None,
    step: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    """구조화 로그를 logger.error 로 기록한다.

    Args:
        exc: 발생한 F1PipelineError 인스턴스.
        case_id: 사건 ID (있으면 포함).
        step: 파이프라인 단계 레이블 (예: "B").
        extra: 추가로 포함할 임의 필드.
    """
    log_extra: dict[str, Any] = {
        "error_code": exc.code,
        "transient": exc.transient,
    }
    if case_id is not None:
        log_extra["case_id"] = case_id
    if step is not None:
        log_extra["step"] = step
    if extra:
        log_extra.update(extra)
    logger.error("F1PipelineError: %s", str(exc), extra=log_extra)


# ============================================================
# exception_handler 핵심 로직 (테스트에서 직접 호출 가능)
# ============================================================


def _case_id_from_request(request: Request) -> Optional[str]:
    """요청 경로에서 case_id 를 추출한다 (없으면 None)."""
    return request.path_params.get("case_id")


async def _handle_blocking_error(
    request: Request, exc: F1PipelineError
) -> JSONResponse:
    """① 차단성 에러 → 400."""
    case_id = _case_id_from_request(request)
    _log_error(exc, case_id=case_id)
    return JSONResponse(
        status_code=400,
        content={
            "error": exc.code,
            "message": str(exc),
            "feature": 1,
        },
    )


async def _handle_config_error(
    request: Request, exc: ConfigError
) -> JSONResponse:
    """ConfigError → 500."""
    case_id = _case_id_from_request(request)
    _log_error(exc, case_id=case_id)
    return JSONResponse(
        status_code=500,
        content={
            "error": exc.code,
            "message": str(exc),
            "feature": 1,
        },
    )


async def _handle_data_go_kr_error(
    request: Request, exc: DataGoKrError
) -> JSONResponse:
    """② 복구 가능 에러 처리.

    - transient=True  → 503 + retry_after_s
    - transient=False → 200 + status="needs_review"
      (결과 저장은 호출자 담당, 여기서는 응답 포맷만 제공)
    """
    case_id = _case_id_from_request(request)
    _log_error(
        exc,
        case_id=case_id,
        extra={
            "endpoint": exc.endpoint,
            "http_status_code": exc.status_code,
        },
    )
    if exc.transient:
        retry_after_s: Optional[int] = getattr(exc, "retry_after", None) or 30
        return JSONResponse(
            status_code=503,
            content={
                "error": exc.code,
                "message": str(exc),
                "retry_after_s": retry_after_s,
            },
        )
    else:
        # 결과 저장은 호출자(라우터)가 담당; 핸들러는 포맷만 반환
        return JSONResponse(
            status_code=200,
            content={
                "status": "needs_review",
                "error": exc.code,
                "message": str(exc),
            },
        )


async def _handle_circuit_breaker_error(
    request: Request, exc: CircuitBreakerOpenError
) -> JSONResponse:
    """CircuitBreakerOpenError → 503."""
    case_id = _case_id_from_request(request)
    _log_error(
        exc,
        case_id=case_id,
        extra={"endpoint": exc.endpoint},
    )
    content: dict[str, Any] = {
        "error": exc.code,
        "message": str(exc),
    }
    if exc.reopen_at is not None:
        content["reopen_at"] = exc.reopen_at.isoformat()
    return JSONResponse(status_code=503, content=content)


async def _handle_f1_pipeline_error(
    request: Request, exc: F1PipelineError
) -> JSONResponse:
    """기타 F1PipelineError → 500."""
    case_id = _case_id_from_request(request)
    _log_error(exc, case_id=case_id)
    return JSONResponse(
        status_code=500,
        content={
            "error": exc.code,
            "message": str(exc),
        },
    )


# ============================================================
# 등록 헬퍼 (main.py 에서 호출)
# ============================================================


def register_error_handlers(app: FastAPI) -> None:
    """app 에 F1 파이프라인 exception handler 를 등록한다.

    호출 순서가 중요하다: 구체적인 하위 클래스를 먼저 등록해야
    FastAPI 가 올바른 핸들러를 선택한다.

    Args:
        app: FastAPI 애플리케이션 인스턴스.
    """
    # ① 차단성 에러 (400)
    for exc_cls in (
        F0NotCompletedError,
        F0NotApprovedError,
        NoIngredientsError,
        FoodTypeMissingError,
    ):
        app.add_exception_handler(exc_cls, _handle_blocking_error)  # type: ignore[arg-type]

    # ConfigError (500) — 차단성 계층이지만 서버 설정 문제
    app.add_exception_handler(ConfigError, _handle_config_error)  # type: ignore[arg-type]

    # Circuit Breaker (503) — DataGoKrError 보다 먼저 등록
    app.add_exception_handler(CircuitBreakerOpenError, _handle_circuit_breaker_error)  # type: ignore[arg-type]

    # ② 복구 가능 에러 (DataGoKrError base — 하위 클래스 포함)
    app.add_exception_handler(DataGoKrError, _handle_data_go_kr_error)  # type: ignore[arg-type]

    # 최상위 fallback
    app.add_exception_handler(F1PipelineError, _handle_f1_pipeline_error)  # type: ignore[arg-type]
