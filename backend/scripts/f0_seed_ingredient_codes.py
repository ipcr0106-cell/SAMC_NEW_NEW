"""
f0 성분코드 Supabase 시드 스크립트

엑셀 파일에서 성분코드를 읽어 Supabase f0_ingredient_codes 테이블에 INSERT.
SQL Editor 용량 초과 문제 대안.

실행:
    cd backend
    python -m scripts.f0_seed_ingredient_codes

    # 엑셀 경로 직접 지정 시:
    python -m scripts.f0_seed_ingredient_codes --file "C:/path/to/성분_20260417.xlsx"

환경변수 (backend/.env):
    SUPABASE_URL          Supabase URL (공용)
    SUPABASE_SERVICE_KEY  Supabase 서비스 키 (공용)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# 엑셀 기본 경로 (backend/scripts/ 기준 상대경로 또는 절대경로)
DEFAULT_EXCEL = Path(__file__).parent.parent.parent / "성분_20260417.xlsx"

BATCH_SIZE = 500  # Supabase upsert 배치 크기


def load_excel(path: Path) -> list[dict]:
    """엑셀에서 성분코드 데이터 로드."""
    try:
        import openpyxl
    except ImportError:
        logger.error("openpyxl 미설치. 'pip install openpyxl' 실행하세요.")
        sys.exit(1)

    logger.info(f"엑셀 로드 중: {path}")
    wb = openpyxl.load_workbook(path)
    ws = wb.active

    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        no, code, name_ko, name_en, category = row
        if not code:
            continue
        code     = str(code).strip()
        name_ko  = str(name_ko or "").strip()
        name_en  = str(name_en or "").strip()
        category = str(category or "").strip()
        prefix   = code[0] if code else ""
        rows.append({
            "code":        code,
            "name_ko":     name_ko,
            "name_en":     name_en,
            "category":    category,
            "code_prefix": prefix,
        })

    logger.info(f"엑셀 로드 완료: {len(rows)}건")
    return rows


def seed(rows: list[dict]) -> None:
    """Supabase에 배치 upsert."""
    try:
        from supabase import create_client
    except ImportError:
        logger.error("supabase 미설치. 'pip install supabase' 실행하세요.")
        sys.exit(1)

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    total = len(rows)
    success = 0

    for i in range(0, total, BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        try:
            sb.table("f0_ingredient_codes").upsert(
                batch,
                on_conflict="code",
            ).execute()
            success += len(batch)
            logger.info(f"  upsert 진행: {min(i + BATCH_SIZE, total)}/{total}")
        except Exception as e:
            logger.error(f"  배치 {i}~{i+BATCH_SIZE} 실패: {e}")
        time.sleep(0.1)

    logger.info(f"=== 완료: {success}/{total}건 upsert ===")


def main() -> None:
    parser = argparse.ArgumentParser(description="f0 성분코드 Supabase 시드 스크립트")
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_EXCEL,
        help="성분코드 엑셀 파일 경로",
    )
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("SUPABASE_URL 또는 SUPABASE_SERVICE_KEY 환경변수가 없습니다.")
        sys.exit(1)

    if not args.file.exists():
        logger.error(f"엑셀 파일을 찾을 수 없습니다: {args.file}")
        logger.error("--file 옵션으로 경로를 직접 지정해주세요.")
        logger.error("예: python -m scripts.f0_seed_ingredient_codes --file \"C:/Users/user/Downloads/성분_20260417.xlsx\"")
        sys.exit(1)

    rows = load_excel(args.file)
    seed(rows)


if __name__ == "__main__":
    main()
