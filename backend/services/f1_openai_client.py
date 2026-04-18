"""F1 전용 OpenAI 클라이언트 — 임베딩 + Chat (JSON mode).

메인 RAG 판정 흐름:
    f1_rag_judge.run(payload)
      ├─ embed([query_text])      ─→ text-embedding-3-small
      └─ chat_json(system, user)  ─→ gpt-4o-mini (response_format=json_object)

환경변수:
    F1_OPENAI_API_KEY        (필수)
    F1_OPENAI_EMBED_MODEL    (기본: text-embedding-3-small)
    F1_OPENAI_CHAT_MODEL     (기본: gpt-4o-mini)

참고: 계획/f1_RAG도입계획_백엔드.md §3.1
"""
from __future__ import annotations

import json
import os
from typing import Optional

from openai import OpenAI

_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    """싱글톤 OpenAI 클라이언트."""
    global _client
    if _client is None:
        api_key = os.getenv("F1_OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("F1_OPENAI_API_KEY 환경변수가 없습니다.")
        _client = OpenAI(api_key=api_key)
    return _client


def embed(texts: list[str]) -> list[list[float]]:
    """배치 임베딩 (권장 최대 100개)."""
    if not texts:
        return []
    model = os.getenv("F1_OPENAI_EMBED_MODEL", "text-embedding-3-small")
    resp = get_client().embeddings.create(model=model, input=texts)
    return [d.embedding for d in resp.data]


def chat_json(
    system: str,
    user: str,
    model: Optional[str] = None,
    temperature: float = 0.0,
) -> dict:
    """Chat Completions — JSON 모드 강제 + 파싱.

    주의:
        - gpt-4o-mini는 JSON mode 지원 — 시스템 프롬프트에 "JSON" 단어 필수.
        - JSON 파싱 실패 시 json.JSONDecodeError 그대로 전파 (호출처 책임).
    """
    model = model or os.getenv("F1_OPENAI_CHAT_MODEL", "gpt-4o-mini")
    resp = get_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or "{}"
    return json.loads(raw)
