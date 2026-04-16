"""
SAMC — Supabase 클라이언트 (공유 파일: 전원 합의 필수)

사용법:
    from db.supabase_client import get_supabase
    supabase = get_supabase()
    result = await supabase.table("cases").select("*").execute()
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


@lru_cache(maxsize=1)
def get_supabase():
    """Supabase 클라이언트 싱글톤. service_role 키 사용 (서버 전용)."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "SUPABASE_URL 또는 SUPABASE_SERVICE_KEY가 .env에 설정되지 않았습니다."
        )

    try:
        from supabase import create_client

        return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    except ImportError:
        raise RuntimeError(
            "supabase 패키지가 설치되지 않았습니다. pip install supabase"
        )
