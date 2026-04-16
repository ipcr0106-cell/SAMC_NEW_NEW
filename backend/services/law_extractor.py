"""법령 청크에서 기준치(threshold) 추출 — Claude API 기반.

담당: 병찬
참고: 계획/기능1_구현계획/03_백엔드_구현_계획.md T6

흐름:
    chunker.chunk_law_markdown() → Chunk[]
        → has_numbers=True인 청크만 선별
        → extract_thresholds_from_chunk() Claude 호출
        → ExtractedThreshold[] 반환
        → 관리자 UI에서 검수 → f1_additive_limits / f1_safety_standards 에 is_verified=true 로 INSERT

주의:
    - is_verified=false 상태로 preview_queue에 저장 (future: DB 테이블 또는 파일)
    - F1_ANTHROPIC_API_KEY 미설정 시 빈 결과 + 에러 메시지 반환
    - 모든 수치·단위는 사람 검수 전제
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any, Optional

from pydantic import BaseModel, Field

from utils.chunker import Chunk

# ============================================================
# 결과 타입
# ============================================================


class ExtractedThreshold(BaseModel):
    ingredient: str = Field(..., description="성분/원료/항목명")
    food_type: Optional[str] = Field(None, description="식품유형 (예: 과채음료)")
    value: Optional[float] = Field(None, description="기준값. 비수치 기준은 None")
    value_text: Optional[str] = Field(
        None, description='"불검출","음성" 등 비수치 기준'
    )
    unit: Optional[str] = Field(None, description="g/kg, mg/L, ppm, %")
    condition: Optional[str] = None
    standard_type: Optional[str] = Field(
        None,
        description="additive | microbe | heavy_metal | pesticide | contaminant | alcohol",
    )
    source_article: Optional[str] = Field(None, description="추출 출처 조문명")


class ExtractionResult(BaseModel):
    extracted: list[ExtractedThreshold] = Field(default_factory=list)
    needs_review: list[dict] = Field(default_factory=list)
    error: Optional[str] = None


# ============================================================
# Claude 프롬프트
# ============================================================


_SYSTEM_PROMPT = """당신은 한국 식품법령 기준치 추출 전문가이다.
주어진 조문에서 성분별 허용 기준치를 JSON으로 추출하라.

추출 규칙:
1. 성분명, 식품유형, 기준값, 단위, 조건을 정확히 분리.
2. "단, 가열제품에 한한다" 같은 조건은 반드시 condition 에 포함.
3. 수치가 범위(예: 0.5~1.0)이면 상한값을 value 로 사용.
4. "불검출"·"음성" 같은 비수치 기준은 value=null, value_text 에 원문 저장.
5. 단위는 g/kg, mg/L, ppm, % 중 하나로 정규화 (다른 단위면 그대로).
6. standard_type: 첨가물=additive, 중금속=heavy_metal, 미생물=microbe,
   잔류농약=pesticide, 기타오염물질=contaminant, 주류=alcohol.
7. 불확실한 항목은 extracted 에 넣지 말고 needs_review 에 "issue" 메모와 함께 분리.
8. LLM이 확신하지 못하는 값은 절대 임의로 채우지 말 것.

출력은 다음 JSON 스키마를 엄격히 따른다:
{
  "extracted": [
    {
      "ingredient": "...",
      "food_type": "...",
      "value": 0.6,
      "value_text": null,
      "unit": "g/kg",
      "condition": "...",
      "standard_type": "additive",
      "source_article": "제3조 제1항"
    }
  ],
  "needs_review": [
    {"issue": "단위가 mg인지 g인지 불명확", "raw_text": "..."}
  ]
}

JSON 외 설명 금지."""


# ============================================================
# Claude 호출 (dynamic import — 미설치 환경 안전)
# ============================================================


async def _call_claude(prompt_user: str, model: str = "claude-opus-4-5") -> str:
    api_key = os.environ.get("F1_ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "F1_ANTHROPIC_API_KEY 미설정. backend/.env 에 추가하거나 law_extractor 비활성."
        )
    try:
        from anthropic import AsyncAnthropic  # type: ignore
    except ImportError as exc:  # noqa: F841
        raise RuntimeError(
            "anthropic 패키지 필요. 'pip install anthropic' 실행 필요."
        ) from exc

    client = AsyncAnthropic(api_key=api_key)
    resp = await client.messages.create(
        model=model,
        max_tokens=2048,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt_user}],
    )
    parts = []
    for block in resp.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


# ============================================================
# 개별 청크 추출
# ============================================================


def _parse_json_strict(raw: str) -> dict[str, Any]:
    """Claude 응답에서 JSON 파싱. 앞뒤 설명·코드펜스 제거."""
    text = raw.strip()
    # ```json ... ``` 또는 ``` ... ``` 제거
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


async def extract_thresholds_from_chunk(
    chunk: Chunk, model: str = "claude-opus-4-5"
) -> ExtractionResult:
    """단일 청크에서 기준치 추출."""
    if not chunk.get("has_numbers"):
        return ExtractionResult()

    prompt = f"[조문: {chunk.get('article', '')}]\n\n{chunk['text']}"
    try:
        raw = await _call_claude(prompt, model=model)
    except Exception as exc:  # noqa: BLE001
        return ExtractionResult(error=f"Claude 호출 실패: {exc}")

    try:
        parsed = _parse_json_strict(raw)
    except json.JSONDecodeError as exc:
        return ExtractionResult(error=f"JSON 파싱 실패: {exc}; raw={raw[:200]}")

    extracted_raw = parsed.get("extracted", []) or []
    needs_review = parsed.get("needs_review", []) or []

    extracted: list[ExtractedThreshold] = []
    for item in extracted_raw:
        try:
            # source_article 비면 청크의 article 사용
            item.setdefault("source_article", chunk.get("article"))
            extracted.append(ExtractedThreshold(**item))
        except Exception as exc:  # noqa: BLE001
            needs_review.append({"issue": f"스키마 불일치: {exc}", "raw": item})

    return ExtractionResult(extracted=extracted, needs_review=needs_review)


# ============================================================
# 일괄 추출
# ============================================================


async def extract_thresholds_bulk(
    chunks: list[Chunk],
    model: str = "claude-opus-4-5",
    concurrency: int = 3,
) -> ExtractionResult:
    """청크 배열에서 has_numbers=True인 것만 병렬 추출.

    concurrency 동시 호출 수 제한으로 rate limit 회피.
    """
    target_chunks = [c for c in chunks if c.get("has_numbers")]
    if not target_chunks:
        return ExtractionResult()

    semaphore = asyncio.Semaphore(concurrency)

    async def _one(ch: Chunk) -> ExtractionResult:
        async with semaphore:
            return await extract_thresholds_from_chunk(ch, model=model)

    results = await asyncio.gather(*[_one(c) for c in target_chunks])

    merged = ExtractionResult()
    errors: list[str] = []
    for r in results:
        merged.extracted.extend(r.extracted)
        merged.needs_review.extend(r.needs_review)
        if r.error:
            errors.append(r.error)
    if errors:
        merged.error = "; ".join(errors[:3])  # 앞 3개만
    return merged
