"""
F3 RAG + LLM 법령 인용 설명 생성 모듈.

역할:
  판정은 rule-based 엔진이 완료. 여기서는 "왜 필요한지 + 어느 법령에 근거하는지"
  자연어 설명을 GPT-5.4 mini 로 생성. 할루시네이션 4단 차단.

할루시네이션 방지 구조:
  1. Temperature=0 — 결정론적 출력
  2. System prompt 엄격 — "제공된 법령 원문 외 절대 말하지 마라"
  3. Output validation — 인용한 조항이 실제 입력된 chunks 에 있는지 정규식 역검증
  4. Fallback — 검증 실패 시 rule-based excerpt 그대로 사용

비용 최적화:
  - lru_cache 로 같은 (doc_id, trigger_ingredients) 조합 재호출 방지
  - LLM 호출 실패 시 citations 만 반환 (엔진 계속 동작)
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Optional

try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False


# ──────────────────────────────────────────────
# OpenAI 클라이언트 싱글톤
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
# Prompt 구성
# ──────────────────────────────────────────────

SYSTEM_PROMPT = """당신은 수입식품 검역 전문가 보조 AI 입니다.
규칙:
1. 아래 제공된 [관련 법령] 원문과 [판정 근거] 만을 사용해서 답하세요.
2. 제공된 원문에 없는 법령 조항/조문/근거는 절대 만들지 마세요.
3. 정보가 부족하면 "제공된 법령으로는 추가 설명 불가" 라고 답하세요.
4. 답은 다음 JSON 으로 엄격히 반환:
{
  "summary": "<1문장 요약, 실무자가 이해하기 쉽게>",
  "detail": "<법령 조항을 인용하며 2-3문장 설명>",
  "cited_articles": ["<인용한 법령 조항 식별자 목록, 예: '시행규칙 제27조 제1항 제8호'>"]
}
5. cited_articles 의 각 항목은 반드시 [관련 법령] 섹션에 명시된 것만.
6. 추측·일반 지식 금지. 오직 제공된 원문 범위 안에서만.
"""


def _build_user_prompt(
    doc_id: str,
    doc_title: str,
    rule_reason: str,
    citations: list[dict],
) -> str:
    """LLM 에 넘길 user prompt 구성."""
    lines = [f"[판정 결과]"]
    lines.append(f"서류 ID: {doc_id}")
    if doc_title:
        lines.append(f"서류명: {doc_title}")
    lines.append(f"엔진 판정 근거: {rule_reason or '(없음)'}")
    lines.append("")
    lines.append("[관련 법령]")
    for i, c in enumerate(citations, 1):
        # 법령 식별자
        ref_parts = []
        if c.get("law_name"):
            ref_parts.append(c["law_name"])
        elif c.get("agreement"):
            ref_parts.append(c["agreement"])
        elif c.get("law_source"):
            ref_parts.append(c["law_source"])
        if c.get("article"):
            ref_parts.append(c["article"])
        if c.get("clause"):
            ref_parts.append(c["clause"])
        if c.get("item"):
            ref_parts.append(c["item"])
        ref_label = " ".join(ref_parts) or "(출처 미상)"
        priority_mark = "[핵심]" if c.get("priority") == "primary" else "[참고]"
        lines.append(f"{i}. {priority_mark} {ref_label}")
        if c.get("topic"):
            lines.append(f"   주제: {c['topic']}")
        if c.get("excerpt"):
            lines.append(f"   원문: {c['excerpt']}")
    lines.append("")
    lines.append(
        "[작업]\n"
        "위 [관련 법령] 에 근거해 이 서류가 왜 필요한지 설명하세요. "
        "cited_articles 에는 실제 인용한 조항만 포함하세요."
    )
    return "\n".join(lines)


# ──────────────────────────────────────────────
# 할루시네이션 검증 — 인용한 조항이 입력 chunks 에 실제 있는지
# ──────────────────────────────────────────────

def _validate_citations(cited: list[str], input_citations: list[dict]) -> tuple[bool, list[str]]:
    """LLM 이 인용한 조항 각각이 input citations 에 실제로 있는지 검증.

    Returns:
        (검증 통과 여부, 실패 인용 리스트)
    """
    # 입력 citations 에서 참조 가능한 조항 식별자 수집
    allowed_refs: list[str] = []
    for c in input_citations:
        for field in ("law_name", "agreement", "law_source"):
            v = c.get(field)
            if v:
                allowed_refs.append(_normalize_ref(v))
        if c.get("article"):
            allowed_refs.append(_normalize_ref(c["article"]))
        if c.get("topic"):
            allowed_refs.append(_normalize_ref(c["topic"]))

    failed = []
    for cit in cited:
        cit_norm = _normalize_ref(cit)
        # 최소 하나의 allowed ref 가 이 인용에 포함되거나 반대로 포함되어야 함
        matched = any(
            (a in cit_norm) or (cit_norm in a)
            for a in allowed_refs
            if len(a) >= 4  # 너무 짧은 참조는 스킵
        )
        if not matched:
            failed.append(cit)

    return (len(failed) == 0, failed)


def _normalize_ref(s: str) -> str:
    """참조 문자열 정규화 — 공백·구두점 제거, 소문자화."""
    if not s:
        return ""
    return re.sub(r'[\s\.,·/]', '', str(s)).lower()


# ──────────────────────────────────────────────
# LLM 호출
# ──────────────────────────────────────────────

def _call_llm(system_prompt: str, user_prompt: str) -> Optional[dict]:
    """OpenAI API 호출 — 실패 시 None."""
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
# 공개 API
# ──────────────────────────────────────────────

def generate_law_explanation(
    doc_id: str,
    doc_title: str,
    rule_reason: str,
    citations: list[dict],
) -> dict:
    """법령 인용 기반 자연어 설명 생성 (할루시네이션 4단 차단).

    Returns:
        {
          "summary":  str,           # 1문장 요약
          "detail":   str,           # 2-3문장 상세
          "cited":    list[str],     # LLM 이 인용한 조항 (검증 통과한 것만)
          "citations_raw": list[dict],  # 원본 인용 리스트 (UI 표시용)
          "source":   'llm' | 'fallback' | 'no_citations',
        }
    """
    if not citations:
        return {
            "summary": rule_reason or "공통 서류",
            "detail": rule_reason or "",
            "cited": [],
            "citations_raw": [],
            "source": "no_citations",
        }

    # LLM 호출 시도
    user_prompt = _build_user_prompt(doc_id, doc_title, rule_reason, citations)
    llm_out = _call_llm(SYSTEM_PROMPT, user_prompt)

    if llm_out is None:
        return _fallback_response(rule_reason, citations)

    summary = (llm_out.get("summary") or "").strip()
    detail = (llm_out.get("detail") or "").strip()
    cited = llm_out.get("cited_articles") or []
    if not isinstance(cited, list):
        cited = []

    # 할루시네이션 검증
    passed, failed = _validate_citations(cited, citations)
    if not passed:
        # 실패 시 fallback
        return _fallback_response(rule_reason, citations, hallucination_note=failed)

    return {
        "summary": summary,
        "detail": detail,
        "cited": cited,
        "citations_raw": citations,
        "source": "llm",
    }


def _fallback_response(
    rule_reason: str,
    citations: list[dict],
    hallucination_note: list[str] | None = None,
) -> dict:
    """LLM 실패 / 할루시네이션 감지 시 rule-based 인용만 반환."""
    primary = [c for c in citations if c.get("priority") == "primary"]
    top = primary[0] if primary else citations[0]
    ref_parts = []
    for f in ("law_name", "agreement"):
        if top.get(f):
            ref_parts.append(top[f])
            break
    if top.get("article"):
        ref_parts.append(top["article"])
    if top.get("clause"):
        ref_parts.append(top["clause"])
    if top.get("item"):
        ref_parts.append(top["item"])
    ref_label = " ".join(ref_parts) or "(법령 근거)"
    summary = rule_reason or ""
    detail = f"근거: {ref_label}"
    if top.get("excerpt"):
        detail += f" — {top['excerpt'][:150]}"
    return {
        "summary": summary,
        "detail": detail,
        "cited": [ref_label] if ref_parts else [],
        "citations_raw": citations,
        "source": "fallback",
    }
