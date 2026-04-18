"""F1 RAG 판정 전용 Pydantic 모델 — 법령 인용 + 판정 결과.

메인 흐름:
    f1_rag_judge.run(payload) -> RagJudgement
      ├─ rag_verdict : permitted/restricted/prohibited/unidentified/error
      ├─ rag_reasoning : 한국어 2~4문장
      └─ law_citations : list[LawCitation]  (cited_chunk_ids에 포함된 청크만)

ConflictStatus는 feature1.py(Phase 4-B)가 exact vs RAG 비교 후 부여.
RagJudgement 자체에는 포함되지 않음.

참고: 계획/f1_RAG도입계획_백엔드.md §3.5
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

RagVerdict = Literal[
    "permitted",
    "restricted",
    "prohibited",
    "unidentified",
    "error",
]

ConflictStatus = Literal[
    "agreed",
    "conflict",
    "rag_supplemented",
    "rag_unavailable",
    "rag_skipped",
]


class LawCitation(BaseModel):
    """RAG 판정에 인용된 법령 청크."""

    model_config = ConfigDict(extra="ignore")

    chunk_id: str = Field(..., description="Pinecone vector id")
    namespace: str = Field(..., description="Pinecone namespace")
    regulation_id: Optional[str] = Field(
        None, description="원 법령 id (newsamc 스키마에 따라 None 가능)"
    )
    section_path: Optional[str] = Field(
        None, description="조항 경로 (newsamc 스키마에 따라 None 가능)"
    )
    text: str = Field(..., description="청크 본문 (metadata.text 최대 4000자)")
    score: float = Field(..., description="Pinecone 유사도 점수")


class RagJudgement(BaseModel):
    """RAG 판정 결과. 실패 시 rag_verdict='error'."""

    model_config = ConfigDict(extra="ignore")

    rag_verdict: RagVerdict
    rag_reasoning: str = Field(..., description="한국어 2~4문장")
    law_citations: list[LawCitation] = Field(default_factory=list)
