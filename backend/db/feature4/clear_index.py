"""
Pinecone 인덱스 전체 벡터 초기화 스크립트 (1회용)
이후에는 preprocess_laws.py 재실행만으로 법령 갱신 가능
"""
from dotenv import load_dotenv
load_dotenv()

import os
from pinecone import Pinecone

pc    = Pinecone(api_key=os.getenv("F4_PINECONE_API_KEY"))
index = pc.Index(host=os.getenv("F4_PINECONE_HOST"))

index.delete(delete_all=True)
print("Pinecone 인덱스 초기화 완료")
