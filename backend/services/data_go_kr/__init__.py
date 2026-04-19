"""data.go.kr API 클라이언트 패키지.

Day 0 스켈레톤은 `DataGoKrClient` 시그니처만 노출한다. 본체 구현은 W1-A 트랙에서
`client.py`·`endpoints.py`·`models.py`·`cache.py`·`circuit_breaker.py` 로 확장한다.
"""

from backend.services.data_go_kr.client import DataGoKrClient

__all__ = ["DataGoKrClient"]
