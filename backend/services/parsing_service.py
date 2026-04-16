"""
SAMC 수입식품 검역 AI — LLM 기반 파싱 서비스

OCR로 추출된 Raw 텍스트를 LLM에 넘겨
구조화된 JSON(ParsedResult)으로 변환하는 핵심 로직.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  임시 전환 안내 (TEMPORARY — 개발/테스트용):
    현재는 비용 테스트를 위해 OpenAI API(gpt-4o)를 사용합니다.
    최종 통합 단계에서는 반드시 Anthropic Claude API로 롤백할 것.

    롤백 방법:
      1) .env 의 OPENAI_API_KEY 제거, ANTHROPIC_API_KEY 활성화 확인
      2) 본 파일에서 `_call_openai(...)` 호출 라인을
         `_call_claude(...)` 호출 라인으로 교체
         (검색 키워드: "# >>> OPENAI TEMP")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from __future__ import annotations

import json
import logging
import os

from schemas.upload import (
    BasicInfo,
    IngredientItem,
    LabelInfo,
    ParsedResult,
    ProcessCodeCandidate,
    ProcessCodeReason,
    ProcessInfo,
)
from constants.process_codes import get_prompt_table

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# LLM 설정 (임시: OpenAI / 최종: Anthropic)
# ─────────────────────────────────────────────

# >>> OPENAI TEMP — 최종 통합 시 제거
OPENAI_API_KEY = os.getenv("F0_OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("F0_OPENAI_MODEL", "gpt-4o")
# <<< OPENAI TEMP

# --- CLAUDE ORIGINAL (최종 통합 시 사용) ---
ANTHROPIC_API_KEY = os.getenv("F0_ANTHROPIC_API_KEY", "")
CLAUDE_MODEL_NAME = "claude-sonnet-4-20250514"
# -------------------------------------------

MAX_TOKENS = 8192

# ─────────────────────────────────────────────
# System Prompt — 파싱 규격 정의
# ─────────────────────────────────────────────

_PROCESS_CODE_TABLE = get_prompt_table()

SYSTEM_PROMPT = f"""당신은 한국 식품 수입 검역 전문가이자 문서 파싱 AI입니다.
업로드된 원재료배합비율표, 제조공정도, MSDS, 수출국 라벨 사진에서 OCR로 추출된 텍스트를 분석하여,
아래 JSON 스키마에 정확히 맞는 구조화된 데이터를 생성합니다.

## 출력 규칙
1. 반드시 아래 JSON 형식만 출력하세요. 설명이나 마크다운 코드 블록 없이 순수 JSON만 반환합니다.
2. 누락된 정보는 빈 문자열("") 또는 빈 배열([])로 채웁니다.
3. 배합비율은 퍼센트(%) 숫자를 문자열로 표기합니다 (예: "45.00").
4. **INS 번호와 CAS 번호 추출이 매우 중요합니다.**
   - MSDS 문서에서 CAS 번호(예: 64-17-5, 7732-18-5)를 반드시 추출하세요.
   - 식품첨가물의 INS 번호(예: INS 330, E330)를 반드시 추출하세요.
   - 번호가 명시되어 있지 않더라도, 잘 알려진 식품첨가물이면 INS 번호를 기재하세요.
   - CAS 번호 형식: 숫자-숫자-숫자 (예: 9005-25-8)
   - INS 번호 형식: 숫자 (예: 330, 1400) 또는 E코드 (예: E330)
   - MSDS의 화학성분명, 농도(%), 위험등급도 ins_number 또는 cas_number 필드에 기재할 수 없는 경우 name 필드에 괄호 병기하세요.
5. **제조공정 코드 변환이 핵심입니다.** 제조공정도(process) 텍스트에서 공정 설명을 하나하나 분석하여, 아래 유니패스 공정 코드 참조 테이블에서 가장 가까운 코드를 매핑하세요.
   - 예: "원료를 섞어서 가열한 뒤 캔에 넣고 밀봉" → ["20", "01", "45", "46"]
   - 예: "맥아를 분쇄하고 물과 섞어 발효시킨 후 여과하여 병입" → ["32", "20", "10", "15", "45"]
   - 하나의 문장에서 여러 공정이 묘사되면 각각 별도 코드로 분리합니다.
   - 공정 순서를 유지해서 배열에 담습니다 (공정 흐름도 순서대로).
   - 매핑할 수 없는 공정은 가장 가까운 코드를 선택하고, raw_process_text에 원문을 보존합니다.
   - **각 코드마다 process_code_reasons 배열에 선정 근거를 반드시 기재하세요.** 어떤 원문 텍스트를 보고 이 코드를 선택했는지 간략히 설명합니다.
   - **process_code_candidates 배열은 반드시 작성하고, 아래 규칙을 철저히 따르세요.**
     a) 추천 코드(is_recommended=true): process_codes에 포함된 코드 전부를 후보 배열에도 넣습니다.
     b) 유사 코드(is_recommended=false): **추천 코드 1개당 반드시 1~2개의 유사/혼동 가능 코드를 추가**합니다. 유사 코드가 없는 추천 코드는 없다고 봐도 무방합니다. 반드시 포함하세요.
     c) confusion_note는 절대 비워두지 마세요. "추천 코드 XX(이름)와 어떻게 다른지"를 한 문장으로 명확히 씁니다.
     d) 자주 혼동되는 쌍 예시 (참고용):
        - 01(가열살균) ↔ 03(UHT살균), 04(LTLT저온살균)
        - 10(발효) ↔ 16(유산균발효), 17(초산발효), 18(알코올발효)
        - 15(여과) ↔ 21(막여과), 22(정밀여과)
        - 20(혼합) ↔ 26(교반), 27(유화), 28(균질화)
        - 25(추출) ↔ 29(열수추출), 33(초임계추출), 34(용매추출)
        - 30(농축) ↔ 31(감압농축)
        - 32(분쇄) ↔ 36(미분쇄)
        - 35(증류) ↔ 41(감압증류)
        - 45(충전) ↔ 46(밀봉), 47(진공포장), F04(무균충전)
        - 50(열풍건조) ↔ 12(동결건조), 51(분무건조), 54(감압건조)
        - E01(반죽) ↔ 20(혼합)
        - E02(발효도우) ↔ 10(발효)
6. 다국어 텍스트(영어, 중국어, 일본어 등)는 한국어로 번역하여 성분명에 기재하되, 원문도 괄호 안에 병기합니다.

## 유니패스 제조공정 코드 참조 테이블 (전체)
{_PROCESS_CODE_TABLE}

## 출력 JSON 스키마
{{
  "basic_info": {{
    "product_name": "제품명",
    "export_country": "수출국 (예: 미국)",
    "is_first_import": false,
    "is_organic": false,
    "is_oem": false
  }},
  "ingredients": [
    {{
      "id": "고유ID (ing-1, ing-2 형태)",
      "name": "성분명 (한국어, 원문 병기)",
      "ratio": "배합비율 퍼센트 (예: 45.00)",
      "origin": "원산지 국가",
      "ins_number": "INS 번호 (없으면 빈 문자열)",
      "cas_number": "CAS 번호 (없으면 빈 문자열)"
    }}
  ],
  "process_info": {{
    "process_codes": ["01", "15"],
    "process_code_reasons": [
      {{"code": "01", "reason": "원문 '가열 살균 처리' → 코드 01(가열처리) 선택"}},
      {{"code": "15", "reason": "원문 '발효조에서 발효' → 코드 15(발효) 선택"}}
    ],
    "process_code_candidates": [
      {{
        "code": "01",
        "reason": "원문 '가열 살균 처리' — 일반 가열처리 공정에 해당",
        "is_recommended": true,
        "confusion_note": ""
      }},
      {{
        "code": "02",
        "reason": "끓임(boiling) 공정도 가열과 유사하나 01이 더 포괄적",
        "is_recommended": false,
        "confusion_note": "01(가열처리)은 모든 가열을, 02(끓임)은 boiling 특화. '살균 처리'는 01이 적합."
      }},
      {{
        "code": "15",
        "reason": "원문 '발효조에서 발효' — 발효 공정 명시",
        "is_recommended": true,
        "confusion_note": ""
      }}
    ],
    "raw_process_text": "원문 공정 설명 텍스트 전체 (코드 변환 근거 확인용)"
  }},
  "label_info": {{
    "export_country": "수출국 (예: 미국, 일본)",
    "is_oem": false,
    "label_texts": ["라벨에서 추출한 문구1", "문구2"],
    "design_description": "라벨 디자인 설명 (색상, 그림, 레이아웃 등)",
    "warnings": ["경고문구1", "주의사항2"]
  }}
}}"""


# ─────────────────────────────────────────────
# 메인 파싱 함수
# ─────────────────────────────────────────────

async def parse_raw_texts_to_structured(
    raw_texts: dict[str, str],
    product_name_hint: str = "",
) -> ParsedResult:
    """여러 doc_type의 OCR 텍스트를 LLM에 넘겨 구조화된 ParsedResult를 반환.

    ⚠️ 현재: OpenAI(gpt-4o) 사용 중 (임시, 개발/테스트용)
    ⚠️ 최종: Anthropic Claude로 롤백 필요
    """
    user_sections: list[str] = []
    if product_name_hint:
        user_sections.append(f"[참고 제품명] {product_name_hint}")

    doc_labels = {
        "ingredients": "원재료배합비율표",
        "process": "제조공정도",
        "msds": "MSDS",
        "label": "수출국 라벨",
        "material": "성분재질서류",
        "other": "기타 서류",
    }

    for doc_type, raw_text in raw_texts.items():
        if not raw_text.strip():
            continue
        label = doc_labels.get(doc_type, doc_type)
        user_sections.append(f"=== {label} ===\n{raw_text.strip()}")

    if not user_sections:
        raise ValueError("파싱할 텍스트가 없습니다. 모든 문서에서 텍스트 추출에 실패했습니다.")

    user_message = "\n\n".join(user_sections)
    logger.info(f"LLM 파싱 시작: doc_types={list(raw_texts.keys())}, 텍스트 총 {len(user_message)}자")

    # >>> OPENAI TEMP — 최종 통합 시 _call_claude 로 교체
    response_text = await _call_openai(SYSTEM_PROMPT, user_message)
    # response_text = await _call_claude(SYSTEM_PROMPT, user_message)
    # <<< OPENAI TEMP

    logger.info(f"LLM 응답 수신: {len(response_text)}자")
    result = _parse_llm_response(response_text)

    if not result.basic_info.product_name and not result.ingredients:
        logger.warning(f"파싱 결과가 비어있습니다. 원문 응답: {response_text[:300]}")

    return result


# ─────────────────────────────────────────────
# >>> OPENAI TEMP — 최종 통합 시 이 함수 전체 제거 가능
# ─────────────────────────────────────────────

async def _call_openai(system_prompt: str, user_message: str) -> str:
    """OpenAI(gpt-4o) 호출 — 개발/테스트용 임시 구현."""
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다. backend/.env 파일을 확인하세요.")

    try:
        from openai import AsyncOpenAI
    except ImportError:
        raise ValueError("openai 패키지가 설치되지 않았습니다. 'pip install openai' 실행하세요.")

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    try:
        completion = await client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=MAX_TOKENS,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as e:
        logger.error(f"OpenAI API 호출 실패: {e}")
        raise ValueError(f"OpenAI API 호출 실패: {e}")

# <<< OPENAI TEMP END


# ─────────────────────────────────────────────
# --- CLAUDE ORIGINAL (최종 통합 시 사용) ---
# ─────────────────────────────────────────────

async def _call_claude(system_prompt: str, user_message: str) -> str:
    """Anthropic Claude 호출 — 최종 프로덕션용."""
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다. backend/.env 파일을 확인하세요.")

    import anthropic

    try:
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        message = await client.messages.create(
            model=CLAUDE_MODEL_NAME,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return message.content[0].text.strip()
    except anthropic.AuthenticationError as e:
        logger.error(f"Claude API 인증 실패: {e}")
        raise ValueError(f"Claude API 인증 실패: API 키가 유효하지 않습니다. ({e})")
    except anthropic.APIError as e:
        logger.error(f"Claude API 호출 실패: {e}")
        raise ValueError(f"Claude API 호출 실패: {e}")


# ─────────────────────────────────────────────
# LLM 응답 파싱 → Pydantic 모델 변환
# ─────────────────────────────────────────────

def _parse_llm_response(response_text: str) -> ParsedResult:
    """LLM 응답 JSON 문자열을 ParsedResult로 변환.
    JSON 파싱 실패 시 빈 결과 반환 (에러 로그 기록).
    """
    cleaned = response_text
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1]
        cleaned = cleaned.split("```", 1)[0]
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1]
        cleaned = cleaned.split("```", 1)[0]

    try:
        data = json.loads(cleaned.strip())
    except json.JSONDecodeError as e:
        logger.error(f"LLM 응답 JSON 파싱 실패: {e}\n원문: {response_text[:500]}")
        return _empty_result()

    bi_raw = data.get("basic_info", {})
    basic_info = BasicInfo(
        product_name=bi_raw.get("product_name", ""),
        export_country=bi_raw.get("export_country", ""),
        is_first_import=bi_raw.get("is_first_import", False),
        is_organic=bi_raw.get("is_organic", False),
        is_oem=bi_raw.get("is_oem", False),
    )

    ingredients: list[IngredientItem] = []
    for idx, ing_raw in enumerate(data.get("ingredients", []), start=1):
        item = IngredientItem(
            id=ing_raw.get("id", f"ing-{idx}"),
            name=ing_raw.get("name", ""),
            ratio=str(ing_raw.get("ratio", "")),
            origin=ing_raw.get("origin", ""),
            ins_number=str(ing_raw.get("ins_number", "")),
            cas_number=str(ing_raw.get("cas_number", "")),
        )
        ingredients.append(item)

    pi_raw = data.get("process_info", {})
    # 공정 코드 근거 파싱 (하위 호환)
    raw_reasons = pi_raw.get("process_code_reasons", [])
    parsed_reasons: list[ProcessCodeReason] = []
    for r in raw_reasons:
        if isinstance(r, dict) and r.get("code"):
            parsed_reasons.append(ProcessCodeReason(
                code=str(r.get("code", "")),
                reason=str(r.get("reason", "")),
            ))
    # 공정 코드 후보 파싱 (추천 + 유사)
    raw_candidates = pi_raw.get("process_code_candidates", [])
    parsed_candidates: list[ProcessCodeCandidate] = []
    for c in raw_candidates:
        if isinstance(c, dict) and c.get("code"):
            parsed_candidates.append(ProcessCodeCandidate(
                code=str(c.get("code", "")),
                reason=str(c.get("reason", "")),
                is_recommended=bool(c.get("is_recommended", False)),
                confusion_note=str(c.get("confusion_note", "")),
            ))
    # candidates가 없으면 process_code_reasons에서 역으로 채워줌 (하위 호환)
    if not parsed_candidates and parsed_reasons:
        rec_codes = set(pi_raw.get("process_codes", []))
        for r in parsed_reasons:
            parsed_candidates.append(ProcessCodeCandidate(
                code=r.code,
                reason=r.reason,
                is_recommended=(r.code in rec_codes),
                confusion_note="",
            ))
    process_info = ProcessInfo(
        process_codes=pi_raw.get("process_codes", []),
        process_code_reasons=parsed_reasons,
        process_code_candidates=parsed_candidates,
        raw_process_text=pi_raw.get("raw_process_text", ""),
    )

    li_raw = data.get("label_info", {})
    label_info = LabelInfo(
        export_country=li_raw.get("export_country", bi_raw.get("export_country", "")),
        is_oem=li_raw.get("is_oem", bi_raw.get("is_oem", False)),
        label_texts=li_raw.get("label_texts", []),
        design_description=li_raw.get("design_description", ""),
        warnings=li_raw.get("warnings", []),
    )

    return ParsedResult(
        basic_info=basic_info,
        ingredients=ingredients,
        process_info=process_info,
        label_info=label_info,
    )


def _empty_result() -> ParsedResult:
    """빈 ParsedResult를 반환 (에러 시 안전한 기본값)."""
    return ParsedResult(
        basic_info=BasicInfo(),
        ingredients=[],
        process_info=ProcessInfo(),
    )
