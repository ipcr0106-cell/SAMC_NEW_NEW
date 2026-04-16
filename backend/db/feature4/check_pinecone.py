import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent.parent / ".env")  # backend/.env 통합 사용

from pinecone import Pinecone

pc = Pinecone(api_key=os.getenv("F4_PINECONE_API_KEY"))
index = pc.Index(host=os.getenv("F4_PINECONE_HOST"))
stats = index.describe_index_stats()
print(stats)
print(f"\ntotal_vector_count: {stats.total_vector_count}")
