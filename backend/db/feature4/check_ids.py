"""
Supabase의 law_doc_id와 Pinecone 실제 벡터 ID 형식 비교
"""
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent.parent / ".env")  # backend/.env 통합 사용

from pinecone import Pinecone
from supabase import create_client

pc = Pinecone(api_key=os.getenv("F4_PINECONE_API_KEY"))
index = pc.Index(host=os.getenv("F4_PINECONE_HOST"))
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

# Supabase에서 law_doc_id 조회
laws = supabase.table("f4_law_documents").select("id, law_name, total_chunks").execute()
print("=== Supabase f4_law_documents ===")
for law in laws.data:
    print(f"  law_name: {law['law_name']}")
    print(f"  id: {law['id']}")
    print(f"  total_chunks: {law['total_chunks']}")

    # 예상 Pinecone ID (첫 번째)
    expected_id = f"{law['id']}_0000"
    print(f"  예상 Pinecone ID: {expected_id}")

    # 실제 fetch 시도
    result = index.fetch(ids=[expected_id])
    found = expected_id in result.vectors
    print(f"  Pinecone fetch 결과: {'찾음' if found else '없음'}")
    print()

# Pinecone에 실제 저장된 ID 샘플 확인 (list 사용)
print("=== Pinecone 실제 ID 샘플 (최대 5개) ===")
try:
    listed = index.list(limit=5)
    for item in listed:
        print(f"  {item}")
except Exception as e:
    print(f"  list 실패: {e}")
