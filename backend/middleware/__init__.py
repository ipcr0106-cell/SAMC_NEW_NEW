"""FastAPI 미들웨어 패키지.

등록 헬퍼: `register_error_handlers(app)` — main.py에서 호출.
"""

from middleware.error_handler import register_error_handlers

__all__ = ["register_error_handlers"]
