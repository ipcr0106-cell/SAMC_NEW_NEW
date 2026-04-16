"""법령 청크 텍스트 전체 덤프 — 패턴 분석용 (실행 후 삭제 가능)"""
import hashlib, os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent.parent / ".env")  # backend/.env 통합 사용

from pinecone import Pinecone
from supabase import create_client

def make_id(law_name, i):
    return hashlib.md5(f"{law_name}|{i:05d}".encode()).hexdigest()

pc = Pinecone(api_key=os.getenv("F4_PINECONE_API_KEY"))
index = pc.Index(host=os.getenv("F4_PINECONE_HOST"))
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

# Supabase에 등록된 모든 법령 동적 조회
all_docs = supabase.table("f4_law_documents").select("law_name").order("law_name").execute()
TARGET = [row["law_name"] for row in all_docs.data] if all_docs.data else []
print(f"덤프 대상 법령 ({len(TARGET)}개): {TARGET}")

out = open(Path(__file__).parent / "dump_chunks.txt", "w", encoding="utf-8")

for law_name in TARGET:
    doc = supabase.table("f4_law_documents").select("id, total_chunks").eq("law_name", law_name).execute()
    if not doc.data:
        out.write(f"\n[없음] {law_name}\n"); continue

    total = doc.data[0]["total_chunks"]
    ids = [make_id(law_name, i) for i in range(total)]

    out.write(f"\n{'='*70}\n{law_name}  ({total}청크)\n{'='*70}\n")

    for batch_start in range(0, len(ids), 100):
        batch = ids[batch_start:batch_start+100]
        res = index.fetch(ids=batch)
        for vid in batch:
            vec = res.vectors.get(vid)
            if vec and vec.metadata and vec.metadata.get("text"):
                out.write(f"\n--- chunk ---\n{vec.metadata['text']}\n")

out.close()
print("덤프 완료 → dump_chunks.txt")
