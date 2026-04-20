"""F3 LLM 광의↔협의 포섭 판정 모듈.

목적:
  문서의 광의 키워드(예: "다진마늘")에 F0 협의 재료(예: "간마늘"/A1000774002300)가
  법령상 포함되는지 LLM이 판정. 직접 매칭(set intersection) 실패한 케이스에서만 호출.

할루시네이션 방지:
  1. Temperature=0
  2. System prompt — 법령 원문 없으면 false 강제
  3. 식약처 공식 성분코드 체계만 근거로 사용
  4. reasoning에 반드시 (문서 키워드, 사용자 재료, 법령 근거) 모두 인용

비용·속도:
  - 후보 좁혀진 문서만 호출 (food_type·country·condition 통과한 경우)
  - lru_cache로 (doc_id, sorted user keywords tuple) 재호출 방지
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Optional

try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False


# ──────────────────────────────────────────────
# OpenAI 클라이언트 (f3_llm_explainer와 공유 가능하나 독립 유지)
# ──────────────────────────────────────────────
_client: Optional["OpenAI"] = None


def _get_client() -> Optional["OpenAI"]:
    global _client
    if _client is not None:
        return _client
    if not _OPENAI_AVAILABLE:
        return None
    api_key = os.getenv("F3_OPENAI_API_KEY")
    if not api_key:
        return None
    _client = OpenAI(api_key=api_key)
    return _client


MODEL_NAME = os.getenv("F3_LLM_MODEL", "gpt-5.4-mini")


# ──────────────────────────────────────────────
# 프롬프트
# ──────────────────────────────────────────────

SYSTEM_PROMPT = """당신은 수입식품 검역 법령 판단 보조 AI 입니다.

역할:
  법령 문서가 규제하는 대상(광의 용어)에 실제 수입자가 신고한 원재료(협의 용어)가
  포함되는지 판정합니다. 판정 결과는 최종 결정이 아니라 검역관의 판단 보조자료입니다.

판정 원칙 (엄격):
  1. 법령 원문이 제공되지 않았거나 원문에 근거 없으면 subsumed=false 반환.
  2. 식약처 공식 성분코드 체계 기준으로 판정. 일상어 ≠ 공식 분류가 일치하는지 확인.
     예) 법령 광의 '다진마늘' → 공식 분류 '마늘분태', '간마늘', '냉동마늘(FROZEN MASHED)' 는 포함.
          법령 광의 '다진마늘' → '통마늘', '마늘가루(GARLIC POWDER)' 는 불포함 (형태 다름).
  3. "포함될 수 있다" 수준의 추측은 subsumed=false.
  4. 재료가 부분적으로 해당되면 matched_ingredient에 정확히 어느 것인지 명시.
  5. reasoning은 반드시 (문서 키워드, 사용자 재료명, 성분코드, 법령 근거)를 인용.

confidence 기준:
  - high: 공식 분류상 명백히 포함, 법령 원문에 직접 근거.
  - medium: 공식 분류는 포함되지만 법령 해석 여지 있음.
  - low: 판정 애매하거나 법령 근거가 간접적.

출력 JSON 형식:
{
  "subsumed": bool,
  "matched_ingredient": "<사용자 재료명 또는 null>",
  "matched_code": "<성분코드 또는 null>",
  "reasoning": "<한 문단, 근거 인용 필수>",
  "confidence": "high" | "medium" | "low",
  "law_citation": "<인용한 법령 조항 식별자 또는 null>"
}
"""


def _build_user_prompt(
    doc_name: str,
    doc_keywords: list[str],
    user_ingredients: list[dict],
    law_text: str,
) -> str:
    lines = [
        "[문서 정보]",
        f"서류명: {doc_name}",
        f"법령상 규제 대상 (광의): {', '.join(doc_keywords)}",
        "",
        "[수입자 신고 원재료 (협의)]",
    ]
    for i, ing in enumerate(user_ingredients, 1):
        code = ing.get("code", "")
        name_ko = ing.get("name_ko", "")
        ocr_name = ing.get("ocr_name", "")
        lines.append(
            f"{i}. 공식명: {name_ko or '(없음)'} | 코드: {code or '(없음)'} | OCR: {ocr_name or '(없음)'}"
        )
    lines.append("")
    lines.append("[관련 법령 원문]")
    lines.append(law_text or "(법령 원문 없음 → subsumed=false 반환)")
    lines.append("")
    lines.append(
        "[작업]\n"
        "위 법령의 광의 규제 대상에 사용자 재료 중 하나라도 포함되는지 판정하세요. "
        "JSON만 반환하고, reasoning에는 근거를 구체적으로 인용하세요."
    )
    return "\n".join(lines)


def _call_llm(system_prompt: str, user_prompt: str) -> Optional[dict]:
    client = _get_client()
    if client is None:
        return None
    try:
        res = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
            timeout=15,
        )
        content = res.choices[0].message.content or ""
        return json.loads(content)
    except Exception:
        return None


# ──────────────────────────────────────────────
# 캐시 키 (frozenset은 hashable)
# ──────────────────────────────────────────────

@lru_cache(maxsize=512)
def _cached_judge(
    doc_id: str,
    doc_name: str,
    doc_keywords_tuple: tuple[str, ...],
    user_ing_tuple: tuple[tuple[str, str, str], ...],
    law_text: str,
) -> str:
    """JSON string 반환 (lru_cache는 hashable만 허용하므로 dict 직접 저장 불가)."""
    doc_keywords = list(doc_keywords_tuple)
    user_ingredients = [
        {"code": t[0], "name_ko": t[1], "ocr_name": t[2]}
        for t in user_ing_tuple
    ]
    user_prompt = _build_user_prompt(doc_name, doc_keywords, user_ingredients, law_text)
    result = _call_llm(SYSTEM_PROMPT, user_prompt)
    if result is None:
        result = {
            "subsumed": False,
            "matched_ingredient": None,
            "matched_code": None,
            "reasoning": "LLM 호출 실패 — 안전 측면에서 포섭 안 된 것으로 처리.",
            "confidence": "low",
            "law_citation": None,
            "source": "llm_unavailable",
        }
    else:
        result["source"] = "llm"
    return json.dumps(result, ensure_ascii=False)


# ──────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────

def judge_subsumption(
    doc_id: str,
    doc_name: str,
    doc_keywords: list[str],
    user_ingredients: list[dict],
    law_text: str = "",
) -> dict:
    """광의(doc_keywords)에 협의(user_ingredients) 포섭 여부 판정.

    Args:
      doc_id:        문서 ID (캐시 키 + 감사 로그)
      doc_name:      서류명 (프롬프트 컨텍스트)
      doc_keywords:  문서의 광의 키워드 리스트 (예: ["다진마늘"])
      user_ingredients: [{code, name_ko, ocr_name}, ...] — F0 결과
      law_text:      관련 법령 원문 (Pinecone RAG 또는 doc 본문)

    Returns:
      {
        "subsumed": bool,
        "matched_ingredient": str | None,
        "matched_code": str | None,
        "reasoning": str,
        "confidence": "high" | "medium" | "low",
        "law_citation": str | None,
        "source": "llm" | "llm_unavailable" | "no_law",
      }
    """
    # 법령 원문 없으면 즉시 false (규칙 1)
    if not law_text or not law_text.strip():
        return {
            "subsumed": False,
            "matched_ingredient": None,
            "matched_code": None,
            "reasoning": "관련 법령 원문이 제공되지 않아 포섭 판정 불가.",
            "confidence": "low",
            "law_citation": None,
            "source": "no_law",
        }

    # 빈 입력
    if not doc_keywords or not user_ingredients:
        return {
            "subsumed": False,
            "matched_ingredient": None,
            "matched_code": None,
            "reasoning": "문서 키워드 또는 사용자 재료 정보 없음.",
            "confidence": "low",
            "law_citation": None,
            "source": "empty_input",
        }

    # 캐시 조회 (tuple 변환 — hashable 필요)
    user_ing_tuple = tuple(
        (ing.get("code", ""), ing.get("name_ko", ""), ing.get("ocr_name", ""))
        for ing in user_ingredients
    )
    doc_keywords_tuple = tuple(sorted(doc_keywords))
    result_json = _cached_judge(doc_id, doc_name, doc_keywords_tuple, user_ing_tuple, law_text)
    return json.loads(result_json)


def clear_cache() -> None:
    """법령 개정 반영 시 캐시 비우기."""
    _cached_judge.cache_clear()
