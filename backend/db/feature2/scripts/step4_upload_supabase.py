"""
[3단계] Supabase 업로드
2단계에서 만든 CSV 파일을 검수 완료 후 Supabase에 올립니다.

실행:
    python backend/scripts/step4_upload_supabase.py

※ 반드시 step2_structure.py 실행 및 CSV 검수 완료 후 실행하세요.
"""

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

load_dotenv("backend/.env")

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
STRUCT_DIR = Path("preprocessing/structured")


def upload_csv_to_supabase(csv_path: Path, table_name: str, batch_size: int = 100):
    """CSV 파일을 읽어 Supabase 테이블에 나눠서 업로드"""
    if not csv_path.exists():
        print(f"  [없음] {csv_path.name} — 2단계를 먼저 실행하세요")
        return

    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    # NaN → None 변환 (Supabase는 NaN 허용 안 함)
    df = df.where(pd.notna(df), None)

    rows = df.to_dict(orient="records")
    total = len(rows)
    uploaded = 0

    print(f"  총 {total}개 행 업로드 시작...")

    for i in range(0, total, batch_size):
        batch = rows[i : i + batch_size]
        supabase.table(table_name).insert(batch).execute()
        uploaded += len(batch)
        print(f"  → {uploaded}/{total} 완료")

    print(f"  {table_name} 업로드 완료 ({total}개 행)")


if __name__ == "__main__":
    print("=" * 50)
    print("  4단계: Supabase 업로드")
    print("=" * 50)

    print("\n[병찬 담당] ingredient_list 업로드")
    upload_csv_to_supabase(STRUCT_DIR / "ingredient_list.csv", "ingredient_list")

    print("\n[병찬 담당] thresholds 업로드")
    upload_csv_to_supabase(STRUCT_DIR / "thresholds.csv", "thresholds")

    print("\n" + "=" * 50)
    print("  완료!")
    print("  Supabase 대시보드에서 데이터를 확인하세요.")
    print("  is_verified=false 항목은 검수 후 true로 변경하세요.")
    print("=" * 50)
