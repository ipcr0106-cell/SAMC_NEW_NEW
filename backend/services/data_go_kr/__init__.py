"""data.go.kr API 클라이언트 패키지 — W1-A 본체 포함.

모듈 구조 (06번 §2):
    - client.py          : DataGoKrClient (공통 호출 + 재시도 + 캐시)
    - endpoints.py       : 4 엔드포인트 메타데이터
    - models.py          : 응답 Pydantic 모델 (IngredientInfo 등)
    - cache.py           : ResponseCache Protocol + InMemory/Supabase 구현
    - circuit_breaker.py : W1-C 본체 + W1-A NoOpBreaker stub 병존
"""

from services.data_go_kr.cache import (
    InMemoryResponseCache,
    ResponseCache,
    SupabaseResponseCache,
    build_cache_key,
)
from services.data_go_kr.circuit_breaker import (
    CircuitBreakerLike,
    NoOpBreaker,
)
from services.data_go_kr.client import CallLogger, DataGoKrClient
from services.data_go_kr.endpoints import (
    ADDITIVE_STANDARD,
    ENDPOINTS,
    Endpoint,
    FOOD_RAW_MATERIAL,
    IMPORT_FOOD_COMPONENT,
    IMPORT_FOOD_INGREDIENT,
    get_endpoint,
)
from services.data_go_kr.models import (
    AdditiveSpec,
    ComponentInfo,
    DataGoKrBody,
    DataGoKrHeader,
    IngredientInfo,
    RawMaterialInfo,
)

__all__ = [
    # client
    "DataGoKrClient",
    "CallLogger",
    # endpoints
    "Endpoint",
    "ENDPOINTS",
    "FOOD_RAW_MATERIAL",
    "IMPORT_FOOD_INGREDIENT",
    "ADDITIVE_STANDARD",
    "IMPORT_FOOD_COMPONENT",
    "get_endpoint",
    # models
    "DataGoKrHeader",
    "DataGoKrBody",
    "IngredientInfo",
    "ComponentInfo",
    "AdditiveSpec",
    "RawMaterialInfo",
    # cache
    "ResponseCache",
    "InMemoryResponseCache",
    "SupabaseResponseCache",
    "build_cache_key",
    # circuit breaker
    "CircuitBreakerLike",
    "NoOpBreaker",
]
