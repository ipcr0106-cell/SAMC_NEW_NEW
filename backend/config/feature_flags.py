"""F1 파이프라인 Feature Flag 헬퍼.

환경변수에서 boolean / int 값을 읽는 유틸리티와
10번 §3 에 정의된 F1 feature flag 상수를 제공한다.

사용법:
    from config.feature_flags import F1_REQUIRE_HITL0_APPROVAL

참조:
    계획/f1 재설계 계획/10_마이그레이션_계획.md §3
    backend/.env.example (Wave 3 feature flags 주석)
"""

from __future__ import annotations

import hashlib
import os


# ============================================================
# 유틸: env → Python 타입 변환
# ============================================================


def env_bool(name: str, default: bool = False) -> bool:
    """환경변수를 bool 로 읽는다.

    '1', 'true', 'yes', 'on' (대소문자 무관) → True.
    그 외 모든 값, 또는 변수 미설정 → ``default``.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def env_int(name: str, default: int = 0) -> int:
    """환경변수를 int 로 읽는다. 파싱 실패 시 ``default`` 반환."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


# ============================================================
# F1 Feature Flags (10번 §3)
# ============================================================

# True → 신규 Step B/C 실행, False → 기존 Supabase DB 로직
F1_USE_DATA_GO_KR_API: bool = env_bool("F1_USE_DATA_GO_KR_API", default=False)

# True → F0 approved 필수, False → completed만으로 진행 (과도기)
F1_REQUIRE_HITL0_APPROVAL: bool = env_bool("F1_REQUIRE_HITL0_APPROVAL", default=False)

# data.go.kr Circuit Breaker 활성화
F1_ENABLE_CIRCUIT_BREAKER: bool = env_bool("F1_ENABLE_CIRCUIT_BREAKER", default=True)

# True → Step D 표시 전용, False → RAG 판정 주도 로직 유지
F1_RAG_VERDICT_DISABLED: bool = env_bool("F1_RAG_VERDICT_DISABLED", default=True)

# 0~100. 신규 로직 적용 트래픽 비율 (Wave 4 P6 에서 점진 증가)
F1_CANARY_PERCENTAGE: int = env_int("F1_CANARY_PERCENTAGE", default=0)


# ============================================================
# Canary 라우팅 헬퍼
# ============================================================


def should_use_new_pipeline(case_id: str) -> bool:
    """case_id 해시 기반으로 신규 파이프라인 적용 여부를 결정한다.

    MD5 해시를 100으로 모듈로 연산 → F1_CANARY_PERCENTAGE 미만이면 True.
    결정론적이므로 동일 case_id에 대해 항상 같은 결과를 반환한다.
    """
    h = int(hashlib.md5(case_id.encode()).hexdigest(), 16) % 100
    return h < F1_CANARY_PERCENTAGE
