"""
한글표시사항 시안 생성 — 2단계 교차검증
Phase 1: 법령/고시 기반 필수항목 대조 (Pinecone RAG)
Phase 2: AI(Claude) 종합 검증 + 최종 시안 생성
"""

import json
import os
from typing import Optional

import anthropic
from dotenv import load_dotenv

from services.f5_rag import search_and_format

load_dotenv()

MODEL = "claude-sonnet-4-20250514"

# ── 프롬프트 ──────────────────────────────────────────────────────────────────

PHASE1_SYSTEM = """당신은 대한민국 식품표시 법령 전문가입니다.
업로드된 수입식품 서류와 관련 법령 조항을 대조하여, 필수 표시항목 각각이 법령 요건을 충족하는지 검토합니다.

반드시 JSON 형식으로만 응답하세요. 다른 텍스트는 포함하지 마세요.

응답 형식:
{
  "items": [
    {
      "field": "제품명",
      "law_ref": "식품 등의 표시기준 제4조 제1항",
      "law_requirement": "소비자가 식별할 수 있도록 제품명을 표시해야 함",
      "document_value": "서류에서 확인된 값 (확인 불가면 null)",
      "status": "pass",
      "note": "판정 근거 또는 보완 필요 사항"
    }
  ]
}

status 값:
- pass    : 서류가 법령 요건을 충족함
- fail    : 서류가 법령 요건을 충족하지 못함 (수정 필요)
- unclear : 서류 내용이 불충분하여 판정 불가 (추가 확인 필요)

검토 대상 필수항목 (12개):
제품명, 식품유형, 원재료명 및 함량, 알레르기, 영양성분, 소비기한, 보관방법, 제조사, 수입자, 내용량, 원산지, GMO"""


PHASE2_SYSTEM = """당신은 수입식품 한글표시사항 검증 AI입니다.
법령 기반 1차 검토 결과를 교차검증하고, 최종 한글표시사항 시안을 작성합니다.

반드시 JSON 형식으로만 응답하세요. 다른 텍스트는 포함하지 마세요.

응답 형식:
{
  "validation": [
    {
      "field": "제품명",
      "phase1_status": "pass",
      "ai_status": "pass",
      "cross_result": "agree",
      "ai_note": "AI 교차검증 의견"
    }
  ],
  "additional_issues": [
    {
      "field": "기타",
      "issue": "1차 검토에서 놓친 추가 이슈",
      "severity": "error"
    }
  ],
  "draft": {
    "product_name": "제품명",
    "food_type": "식품유형",
    "ingredients": "원재료명 및 함량 (법령 기준 표기)",
    "net_weight": "내용량",
    "expiry": "소비기한 표시 방법",
    "storage": "보관방법",
    "manufacturer": "제조사명 및 주소",
    "importer": "수입자명 및 주소",
    "allergy": "알레르기 유발물질 표시",
    "gmo": "GMO 표시 여부 및 내용",
    "country_of_origin": "원산지"
  }
}

cross_result 값:
- agree           : 1차 결과와 AI 판정이 일치
- disagree        : 1차 결과와 AI 판정이 불일치 (실무자 확인 필수)
- additional_issue: 1차에서 놓친 추가 이슈 발견

severity 값: error(수정필수) | warning(검토필요) | info(참고)"""


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def _docs_text(documents: list[dict]) -> str:
    return "\n\n".join(
        f"[문서: {d.get('file_name', '')}]\n{d.get('parsed_md', '')}"
        for d in documents
        if d.get("parsed_md")
    )


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip().rstrip("`").strip())


# ── 메인 함수 ─────────────────────────────────────────────────────────────────

def generate_label(
    case_id: str,
    documents: list[dict],
    food_type: Optional[str] = None,
    draft_label: Optional[str] = None,
) -> dict:
    """
    2단계 교차검증 시안 생성
    반환값: {"phase1": {...}, "phase2": {...}}
    """
    client = anthropic.Anthropic(api_key=os.getenv("F5_ANTHROPIC_API_KEY"))
    docs = _docs_text(documents)

    # 법령 컨텍스트 (Pinecone RAG)
    law_context = search_and_format(
        query="한글표시사항 원재료명 알레르기 GMO 소비기한 영양성분 표시기준 수입자 원산지"
    )

    food_type_str = f"\n\n## 식품유형 (담당자 입력)\n{food_type}" if food_type else ""
    draft_str = f"\n\n## 한글 가안 (담당자 입력)\n{draft_label}" if draft_label else ""

    # ── Phase 1: 법령 기반 항목별 대조 ──────────────────────────────────────
    p1_user = (
        f"## 업로드된 서류\n{docs}"
        f"{food_type_str}{draft_str}"
        f"\n\n## 관련 법령 조항\n{law_context}"
        "\n\n위 서류와 법령을 대조하여 12개 필수 표시항목 검토 결과를 JSON으로 작성하세요."
    )

    p1_response = client.messages.create(
        model=MODEL,
        max_tokens=3000,
        system=PHASE1_SYSTEM,
        messages=[{"role": "user", "content": p1_user}],
    )
    phase1 = _parse_json(p1_response.content[0].text)

    # ── Phase 2: AI 교차검증 + 시안 생성 ────────────────────────────────────
    p2_user = (
        f"## 업로드된 서류\n{docs}"
        f"{food_type_str}"
        f"\n\n## 관련 법령 조항\n{law_context}"
        f"\n\n## 1차 법령 기반 검토 결과\n{json.dumps(phase1, ensure_ascii=False, indent=2)}"
        "\n\n1차 결과를 교차검증하고, 최종 한글표시사항 시안을 JSON으로 작성하세요."
    )

    p2_response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=PHASE2_SYSTEM,
        messages=[{"role": "user", "content": p2_user}],
    )
    phase2 = _parse_json(p2_response.content[0].text)

    return {
        "phase1": phase1,
        "phase2": phase2,
    }


def generate_label_stream(
    case_id: str,
    documents: list[dict],
    food_type: Optional[str] = None,
    draft_label: Optional[str] = None,
):
    """SSE 스트리밍 — Phase 1 완료 후 Phase 2 스트리밍"""
    from db.supabase_client import get_supabase as get_client

    client = anthropic.Anthropic(api_key=os.getenv("F5_ANTHROPIC_API_KEY"))
    docs = _docs_text(documents)
    law_context = search_and_format(
        query="한글표시사항 원재료명 알레르기 GMO 소비기한 영양성분 표시기준 수입자 원산지"
    )

    food_type_str = f"\n\n## 식품유형 (담당자 입력)\n{food_type}" if food_type else ""
    draft_str = f"\n\n## 한글 가안 (담당자 입력)\n{draft_label}" if draft_label else ""

    # Phase 1 (비스트리밍)
    yield f"data: {json.dumps({'step': 'phase1_start', 'message': '1단계: 법령 기반 검토 중...'}, ensure_ascii=False)}\n\n"

    p1_user = (
        f"## 업로드된 서류\n{docs}"
        f"{food_type_str}{draft_str}"
        f"\n\n## 관련 법령 조항\n{law_context}"
        "\n\n위 서류와 법령을 대조하여 12개 필수 표시항목 검토 결과를 JSON으로 작성하세요."
    )

    try:
        p1_response = client.messages.create(
            model=MODEL, max_tokens=3000,
            system=PHASE1_SYSTEM,
            messages=[{"role": "user", "content": p1_user}],
        )
        phase1 = _parse_json(p1_response.content[0].text)
        yield f"data: {json.dumps({'step': 'phase1_done', 'phase1': phase1}, ensure_ascii=False)}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': f'Phase 1 실패: {str(e)}'}, ensure_ascii=False)}\n\n"
        return

    # Phase 2 (스트리밍)
    yield f"data: {json.dumps({'step': 'phase2_start', 'message': '2단계: AI 교차검증 중...'}, ensure_ascii=False)}\n\n"

    p2_user = (
        f"## 업로드된 서류\n{docs}"
        f"{food_type_str}"
        f"\n\n## 관련 법령 조항\n{law_context}"
        f"\n\n## 1차 법령 기반 검토 결과\n{json.dumps(phase1, ensure_ascii=False, indent=2)}"
        "\n\n1차 결과를 교차검증하고, 최종 한글표시사항 시안을 JSON으로 작성하세요."
    )

    full_text = ""
    with client.messages.stream(
        model=MODEL, max_tokens=4000,
        system=PHASE2_SYSTEM,
        messages=[{"role": "user", "content": p2_user}],
    ) as stream:
        for chunk in stream.text_stream:
            full_text += chunk
            yield f"data: {json.dumps({'step': 'phase2_chunk', 'chunk': chunk}, ensure_ascii=False)}\n\n"

    try:
        phase2 = _parse_json(full_text)
        result = {"phase1": phase1, "phase2": phase2}

        get_client().table("pipeline_steps").upsert(
            {
                "case_id": case_id,
                "step_key": "6",
                "step_name": "한글표시사항",
                "status": "waiting_review",
                "ai_result": result,
            },
            on_conflict="case_id,step_key",
        ).execute()

        yield f"data: {json.dumps({'step': 'done', 'result': result}, ensure_ascii=False)}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': f'Phase 2 파싱 실패: {str(e)}'}, ensure_ascii=False)}\n\n"
