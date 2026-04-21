"""
SAMC 수입식품 검역 AI — LLM 기반 파싱 서비스

OCR로 추출된 Raw 텍스트를 LLM에 넘겨
구조화된 JSON(ParsedResult)으로 변환하는 핵심 로직.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OpenAI API(gpt-4o)를 사용합니다.
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
    ProcessStep,
    ProcessCodeSuggestItem,
    ProcessCodeSuggestResponse,
)
from constants.process_codes import get_prompt_table, PROCESS_CODE_MAP

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# LLM 설정 (임시: OpenAI / 최종: Anthropic)
# ─────────────────────────────────────────────

# >>> OPENAI TEMP — 최종 통합 시 제거
OPENAI_API_KEY = os.getenv("F0_OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("F0_OPENAI_MODEL", "gpt-4o")
# <<< OPENAI TEMP

# --- 대체 LLM 키 (폴백용) ---
F0_OPENAI_API_KEY_ALT = os.getenv("F0_OPENAI_API_KEY", "")
# -------------------------------------------

MAX_TOKENS = 16000

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
4. **원재료 사용 부위(`part`) 추출이 중요합니다.**
   - 원재료명에 부위가 명시된 경우 반드시 분리하여 part 필드에 기재하세요.
   - 예: "스테비아(잎)" → name: "스테비아", part: "잎"
   - 예: "감초뿌리추출물" → name: "감초추출물", part: "뿌리"
   - 부위 표기가 없으면 part는 빈 문자열("")로 둡니다.
5. **복합원재료 중첩 파싱이 중요합니다.**
   - 원재료명 뒤에 괄호로 하위 성분이 나열된 경우(예: "과일혼합(딸기60%, 블루베리40%)") sub_ingredients 배열에 중첩 구조로 파싱하세요.
   - 하위 성분도 동일한 IngredientItem 구조를 따릅니다.
   - 복합원재료가 아닌 단순 원재료는 sub_ingredients를 빈 배열([])로 둡니다.
6. **INS 번호와 CAS 번호 추출이 매우 중요합니다.**
   - MSDS 문서에서 CAS 번호(예: 64-17-5, 7732-18-5)를 반드시 추출하세요.
   - 식품첨가물의 INS 번호(예: INS 330, E330)를 반드시 추출하세요.
   - 번호가 명시되어 있지 않더라도, 잘 알려진 식품첨가물이면 INS 번호를 기재하세요.
   - CAS 번호 형식: 숫자-숫자-숫자 (예: 9005-25-8)
   - INS 번호 형식: 숫자 (예: 330, 1400) 또는 E코드 (예: E330)
   - MSDS의 화학성분명, 농도(%), 위험등급도 ins_number 또는 cas_number 필드에 기재할 수 없는 경우 name 필드에 괄호 병기하세요.
5. **제조공정 코드 변환이 핵심입니다.** 제조공정도(process) 텍스트에서 공정 설명을 하나하나 분석하여, 아래 식약처 공식 공정 코드 참조 테이블에서 가장 가까운 코드를 매핑하세요.
   - **반드시 모든 공정 단계를 빠짐없이 추출하세요.** 텍스트에 10개 이상의 단계가 나열되어 있다면 그 수만큼 코드가 나와야 합니다. 중간에 생략하지 마세요.
   - **다국어 공정도 처리:** 스페인어·영어·중국어·일본어 등 외국어로 된 공정도에서도 모든 단계를 추출합니다.
     - 스페인어 예시 매핑: "Recepción MP"→1(원료), "Horneado/Bake"→11(굽기), "Molienda/Pounding"→52(압착) 또는 32(분쇄), "Fermentación"→27(발효), "Destilación"→78(증류), "Almacén/Warehouse"→67(저장), "Maduración/Maturation"→48(숙성), "Dilución/Dilution"→100(희석), "Enfriamiento/Cooling"→17(냉각), "Filtración/Filtration"→55(여과), "Lavado de botellas/Bottle wash"→45(세척), "Llenado/Bottle filling"→E6(충전), "Sellado/Bottle sealed"→26(밀봉), "Etiquetado/Bottle label"→A4(표면처리), "Empaque/Packaging"→A3(포장)
   - 예: "원료를 섞어서 가열한 뒤 캔에 넣고 밀봉" → ["1", "A6", "8", "26"]
   - 예: "맥아를 분쇄하고 물과 섞어 발효시킨 후 여과하여 병입" → ["32", "A6", "27", "55", "26"]
   - 예: "글루코아밀라아제로 효소처리 후 농축" → ["F1", "21"]
   - 예: "헥산으로 용매추출 후 탈색·탈취·정제" → ["G3", "94", "99", "73"]
   - 흐름도에 번호가 있는 경우(예: 1. Reception MP, 2. Bake ... 20. Packaging) 번호 순서대로 각각 코드를 부여합니다.
   - 하나의 공정 단계(박스 1개)에 코드 1개를 원칙으로 하되, 복합 공정(예: "증류 후 바로 냉각")은 분리합니다.
   - 공정 순서를 유지해서 배열에 담습니다 (공정 흐름도 순서대로).
   - 매핑할 수 없는 공정은 가장 가까운 코드를 선택하고, raw_process_text에 원문을 보존합니다.
   - **process_steps 배열만 출력하세요. process_codes, process_code_reasons, process_code_candidates는 출력하지 않아도 됩니다 (백엔드에서 자동 파생).**
   - **process_steps 배열이 핵심입니다. 각 단계마다 아래를 반드시 채우세요:**
     a) recommended_reason: "왜 이 코드를 선택했는지" 원문 단계명을 언급하여 한 문장으로 설명합니다.
     b) similar_codes: 해당 단계의 추천 코드와 혼동 가능한 코드를 1~2개 반드시 포함합니다 (빈 배열 금지).
        - code, name, reason, confusion_note를 모두 채우세요.
        - confusion_note: "추천 코드 XX(이름)와 어떻게 다른지" 한 문장으로 설명합니다.
   - 자주 혼동되는 쌍 예시 (참고용, 식약처 공식 코드 기준):
        - 8(가열) ↔ 39(살균), 25(멸균), 7(예열)
        - 27(발효) ↔ 28(후발효), 29(배양), 71(접종)
        - 55(여과) ↔ 61(원심분리), 30(분리), 87(침전)
        - A6(혼합) ↔ J2(교반), 64(유화), 16(균질)
        - 84(추출) ↔ 85(용매추출), G1~G14(용매추출 세분류)
        - 21(농축) ↔ 20(재농축), 101(증발)
        - 32(분쇄) ↔ 33(분말), D4(짓이김)
        - 78(증류) ↔ 53(액화), 101(증발)
        - E6(충전) ↔ 26(밀봉), A3(포장)
        - A7(효소처리) ↔ F1~F31(효소처리 세분류) — 효소 종류가 특정되면 F계열 사용
        - 85(용매추출) ↔ G1~G14(용매추출 세분류) — 용매 종류가 특정되면 G계열 사용
7. **제조공정 파싱 불완전 처리 (중요):**
   - 제조공정도 텍스트가 아예 없거나, OCR 결과가 손상/불충분하여 공정 코드를 신뢰할 수 없는 경우:
     → `process_info.is_incomplete: true`로 설정하고, `incomplete_reason`에 이유를 한국어로 기재하세요.
   - 예: 이미지 해상도 불량, 공정 설명 없이 그림만 있음, OCR 텍스트 5단어 미만 등
   - `incomplete_reason` 예시: "제조공정도 텍스트가 거의 없어 공정 코드를 추출할 수 없습니다. 공정 설명을 직접 입력해주세요."
   - 부분적으로 파싱 가능한 경우에도(일부 코드만 추출) `is_incomplete: true`로 표시하고 이유를 기재하세요.
   - 충분히 파싱된 경우는 `is_incomplete: false`, `incomplete_reason: ""`으로 두세요.
8. **MSDS 처리 — CAS 번호와 함량만 추출 (우선순위 낮음):**
   - MSDS 문서에서는 각 화학성분의 CAS 번호와 함량(농도, %)만 추출하면 됩니다.
   - 유해성, 독성, GHS 분류, 응급 조치 등 검역과 무관한 내용은 무시하세요.
   - 추출된 CAS 번호는 ingredients 배열에 cas_number 필드로 기재합니다.
9. **제품 기본 정보 추가 추출:**
   - `manufacturer`: 제조사(회사)명을 라벨 또는 서류에서 추출하세요. 없으면 빈 문자열.
   - `alcohol_percentage`: 라벨에서 알코올 도수를 숫자(float)로 추출하세요.
     예: "ALC. 14.5% BY VOL" → 14.5 / "알코올 함량 5%" → 5.0 / 주류가 아니면 null.
   - `content_volume`: 내용량 문자열을 추출하세요. 예: "500mL", "1kg", "300g×10". 없으면 빈 문자열.
8. **ingredients는 원재료배합비율표 기준으로만 추출하세요.**
   - 제조공정도에 나오는 투입 재료(Water, Yeast, Steam, Barrel 등)는 ingredients에 넣지 마세요.
   - ingredients는 반드시 원재료배합비율표(성분표)에 명시된 항목만 포함합니다.
9. 다국어 텍스트(영어, 중국어, 일본어 등)는 한국어로 번역하여 성분명에 기재하되, 원문도 괄호 안에 병기합니다.
10. **수출국 라벨(label) 정보 추출 — label_info 필드 채우기:**
    - `export_country`: 라벨의 원산지(Country of Origin / País de Origen) 또는 제조국을 추출. 없으면 basic_info.export_country와 동일하게 기재.
    - `is_oem`: 라벨에 "Manufactured by / Produced for / Distributed by" 등 위탁생산 표현이 있으면 true.
    - `label_texts`: 라벨에 표기된 주요 문구 목록 (제품명, 제조사, 내용량, 알코올도수, 원재료 표기, 영양성분 요약, 인증마크, 바코드 텍스트 등). 중요 문구를 빠짐없이 배열로 담으세요.
    - `design_description`: 라벨의 시각적 특징 설명 (색상, 로고, 병 모양, 이미지, 레이아웃 등).
    - `warnings`: 경고문구, 주의사항, 알레르기 정보, 임산부 경고 등. 배열로 담으세요.
    - 라벨 텍스트가 없어도 basic_info에서 알 수 있는 정보(export_country, is_oem)는 반드시 채우세요.

## 식약처 공식 제조공정 코드 참조 테이블 (211개)
{_PROCESS_CODE_TABLE}

## 출력 JSON 스키마
{{
  "basic_info": {{
    "product_name": "제품명",
    "export_country": "수출국 (예: 미국)",
    "is_first_import": false,
    "is_organic": false,
    "is_oem": false,
    "manufacturer": "제조사명 (없으면 빈 문자열)",
    "alcohol_percentage": null,
    "content_volume": "내용량 (예: 500mL, 없으면 빈 문자열)"
  }},
  "ingredients": [
    {{
      "id": "고유ID (ing-1, ing-2 형태)",
      "name": "성분명 (한국어, 원문 병기)",
      "ratio": "배합비율 퍼센트 (예: 45.00)",
      "origin": "원산지 국가",
      "ins_number": "INS 번호 (없으면 빈 문자열)",
      "cas_number": "CAS 번호 (없으면 빈 문자열)",
      "part": "사용 부위 (예: 잎, 없으면 빈 문자열)",
      "sub_ingredients": []
    }},
    {{
      "id": "ing-2",
      "name": "과일혼합",
      "ratio": "30.00",
      "origin": "",
      "ins_number": "",
      "cas_number": "",
      "part": "",
      "sub_ingredients": [
        {{"id": "ing-2-1", "name": "딸기", "ratio": "60", "origin": "", "ins_number": "", "cas_number": "", "part": "", "sub_ingredients": []}},
        {{"id": "ing-2-2", "name": "블루베리", "ratio": "40", "origin": "", "ins_number": "", "cas_number": "", "part": "", "sub_ingredients": []}}
      ]
    }}
  ],
  "process_info": {{
    "process_steps": [
      {{
        "step_number": 1,
        "step_name_original": "Bake",
        "step_name_ko": "굽기",
        "recommended_code": "8",
        "recommended_code_name": "가열",
        "recommended_reason": "아가베 심(피냐)을 오븐에 굽는 공정 → 가열(8) 코드",
        "similar_codes": [
          {{"code": "11", "name": "굽기", "reason": "오븐 굽기 특화 코드", "is_recommended": false, "confusion_note": "8(가열)은 모든 가열 방식, 11(굽기)은 직화/오븐 굽기 특화. 아가베 Bake는 8이 통상적."}}
        ]
      }},
      {{
        "step_number": 2,
        "step_name_original": "Fermentation",
        "step_name_ko": "발효",
        "recommended_code": "27",
        "recommended_code_name": "발효",
        "recommended_reason": "효모를 이용한 당 발효 공정",
        "similar_codes": [
          {{"code": "28", "name": "후발효", "reason": "2차 발효 가능성", "is_recommended": false, "confusion_note": "27(발효)은 1차 알코올 발효, 28(후발효)은 발효 후 추가 숙성. 데킬라 Fermentation은 27."}}
        ]
      }}
    ],
    "raw_process_text": "원문 공정 설명 텍스트 전체 (코드 변환 근거 확인용)",
    "is_incomplete": false,
    "incomplete_reason": ""
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

    # >>> OPENAI — 현재 사용 중
    response_text = await _call_openai(SYSTEM_PROMPT, user_message)
    # response_text = await _call_openai_alt(SYSTEM_PROMPT, user_message)
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
        choice = completion.choices[0]
        finish_reason = choice.finish_reason
        if finish_reason == "length":
            logger.warning(
                f"OpenAI 응답이 max_tokens({MAX_TOKENS})에 의해 잘렸습니다 (finish_reason=length). "
                "process_steps가 누락될 수 있습니다."
            )
        return (choice.message.content or "").strip()
    except Exception as e:
        logger.error(f"OpenAI API 호출 실패: {e}")
        raise ValueError(f"OpenAI API 호출 실패: {e}")

# <<< OPENAI TEMP END


# ─────────────────────────────────────────────
# --- OpenAI 폴백 (기존 Claude 대체) ---
# ─────────────────────────────────────────────

async def _call_openai_alt(system_prompt: str, user_message: str) -> str:
    """OpenAI 호출 — 폴백용."""
    if not F0_OPENAI_API_KEY_ALT:
        raise ValueError("F0_OPENAI_API_KEY가 설정되지 않았습니다. backend/.env 파일을 확인하세요.")

    from openai import AsyncOpenAI

    try:
        client = AsyncOpenAI(api_key=F0_OPENAI_API_KEY_ALT)
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=MAX_TOKENS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI API 호출 실패: {e}")
        raise ValueError(f"OpenAI API 호출 실패: {e}")


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
        # 응답이 잘린 경우(max_tokens 초과) 부분 복구 시도
        logger.warning(f"LLM JSON 파싱 실패 (잘림 가능): {e}")
        # 마지막 완전한 '}'를 찾아 닫아주기
        partial = cleaned.strip()
        # 열린 중괄호 수 세어 부족한 만큼 '}'를 추가
        open_count = partial.count("{") - partial.count("}")
        if open_count > 0:
            partial = partial + "}" * open_count
            try:
                data = json.loads(partial)
                logger.warning("부분 JSON 복구 성공 (일부 필드 누락 가능)")
            except json.JSONDecodeError:
                logger.error(f"부분 복구도 실패. 원문: {response_text[:500]}")
                return _empty_result()
        else:
            logger.error(f"LLM 응답 JSON 파싱 실패: {e}\n원문: {response_text[:500]}")
            return _empty_result()

    bi_raw = data.get("basic_info", {})
    raw_alcohol = bi_raw.get("alcohol_percentage")
    alcohol_pct = None
    if raw_alcohol is not None:
        try:
            alcohol_pct = float(raw_alcohol)
        except (TypeError, ValueError):
            alcohol_pct = None
    basic_info = BasicInfo(
        product_name=bi_raw.get("product_name", ""),
        export_country=bi_raw.get("export_country", ""),
        is_first_import=bi_raw.get("is_first_import", False),
        is_organic=bi_raw.get("is_organic", False),
        is_oem=bi_raw.get("is_oem", False),
        manufacturer=bi_raw.get("manufacturer", ""),
        alcohol_percentage=alcohol_pct,
        content_volume=bi_raw.get("content_volume", ""),
    )

    def _parse_ingredient(ing_raw: dict, idx_prefix: str) -> IngredientItem:
        """원재료 1개를 재귀적으로 파싱 (복합원재료 sub_ingredients 포함)."""
        sub_list: list[IngredientItem] = []
        for sub_idx, sub_raw in enumerate(ing_raw.get("sub_ingredients", []), start=1):
            sub_list.append(_parse_ingredient(sub_raw, f"{idx_prefix}-{sub_idx}"))
        return IngredientItem(
            id=ing_raw.get("id", idx_prefix),
            name=ing_raw.get("name", ""),
            ratio=str(ing_raw.get("ratio", "")),
            origin=ing_raw.get("origin", ""),
            ins_number=str(ing_raw.get("ins_number", "")),
            cas_number=str(ing_raw.get("cas_number", "")),
            part=ing_raw.get("part", ""),
            sub_ingredients=sub_list,
        )

    ingredients: list[IngredientItem] = []
    for idx, ing_raw in enumerate(data.get("ingredients", []), start=1):
        ingredients.append(_parse_ingredient(ing_raw, f"ing-{idx}"))

    pi_raw = data.get("process_info", {})
    # 단계별 공정 분석 파싱 (process_steps가 유일한 소스)
    raw_steps = pi_raw.get("process_steps", [])
    parsed_steps: list[ProcessStep] = []
    for s in raw_steps:
        if not isinstance(s, dict):
            continue
        rec_code = str(s.get("recommended_code", ""))
        # 유사 코드 파싱
        sim_list: list[ProcessCodeCandidate] = []
        for sc in s.get("similar_codes", []):
            if not isinstance(sc, dict) or not sc.get("code"):
                continue
            sim_code = str(sc.get("code", ""))
            sim_list.append(ProcessCodeCandidate(
                code=sim_code,
                name=PROCESS_CODE_MAP.get(sim_code, ""),  # 공식 이름 강제
                reason=str(sc.get("reason", "")),
                is_recommended=False,
                confusion_note=str(sc.get("confusion_note", "")),
            ))
        parsed_steps.append(ProcessStep(
            step_number=int(s.get("step_number", 0)),
            step_name_original=str(s.get("step_name_original", "")),
            step_name_ko=str(s.get("step_name_ko", "")),
            recommended_code=rec_code,
            recommended_code_name=PROCESS_CODE_MAP.get(rec_code, ""),  # 공식 이름 강제
            recommended_reason=str(s.get("recommended_reason", "")),
            similar_codes=sim_list,
        ))
    # step_number 순 정렬
    parsed_steps.sort(key=lambda x: x.step_number)

    # ── process_steps → 나머지 3개 배열 자동 파생 ───────────────────────────
    # LLM은 process_steps만 출력; process_codes / process_code_reasons /
    # process_code_candidates 는 모두 여기서 파생한다 (토큰 절약).

    # 1) process_codes: 추천 코드 목록
    derived_process_codes: list[str] = [
        s.recommended_code for s in parsed_steps if s.recommended_code
    ]

    # 2) process_code_reasons: 추천 코드별 선정 근거
    derived_reasons: list[ProcessCodeReason] = [
        ProcessCodeReason(
            code=s.recommended_code,
            name=PROCESS_CODE_MAP.get(s.recommended_code, s.recommended_code_name),
            reason=s.recommended_reason,
        )
        for s in parsed_steps if s.recommended_code
    ]

    # 3) process_code_candidates: 추천 코드(is_recommended=True) + 유사 코드(False)
    derived_candidates: list[ProcessCodeCandidate] = []
    for s in parsed_steps:
        if s.recommended_code:
            derived_candidates.append(ProcessCodeCandidate(
                code=s.recommended_code,
                name=PROCESS_CODE_MAP.get(s.recommended_code, s.recommended_code_name),
                reason=s.recommended_reason,
                is_recommended=True,
                confusion_note="",
            ))
        for sim in s.similar_codes:
            derived_candidates.append(sim)

    process_info = ProcessInfo(
        process_codes=derived_process_codes,
        process_code_reasons=derived_reasons,
        process_code_candidates=derived_candidates,
        process_steps=parsed_steps,
        raw_process_text=pi_raw.get("raw_process_text", ""),
        is_incomplete=bool(pi_raw.get("is_incomplete", False)),
        incomplete_reason=str(pi_raw.get("incomplete_reason", "")),
    )

    li_raw = data.get("label_info", {}) or {}
    # export_country: label_info 우선, 없으면 basic_info fallback
    _label_country = li_raw.get("export_country") or bi_raw.get("export_country", "")
    # is_oem: label_info 우선, 없으면 basic_info fallback
    _label_oem = li_raw.get("is_oem")
    if _label_oem is None:
        _label_oem = bi_raw.get("is_oem", False)
    # label_texts: 비어있으면 product_name + manufacturer 등으로 최소 채우기
    _label_texts = li_raw.get("label_texts") or []
    if not _label_texts:
        # 라벨 텍스트 없을 때 기본 정보에서 최소 항목 구성
        _auto_texts = []
        if bi_raw.get("product_name"):
            _auto_texts.append(f"제품명: {bi_raw['product_name']}")
        if bi_raw.get("manufacturer"):
            _auto_texts.append(f"제조사: {bi_raw['manufacturer']}")
        if bi_raw.get("content_volume"):
            _auto_texts.append(f"내용량: {bi_raw['content_volume']}")
        if bi_raw.get("alcohol_percentage"):
            _auto_texts.append(f"알코올 도수: {bi_raw['alcohol_percentage']}%")
        _label_texts = _auto_texts
    label_info = LabelInfo(
        export_country=_label_country,
        is_oem=bool(_label_oem),
        label_texts=_label_texts,
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


# ─────────────────────────────────────────────
# 공정 코드 추천 (사용자 수동 입력용)
# ─────────────────────────────────────────────

_PROCESS_SUGGEST_SYSTEM_PROMPT = f"""당신은 한국 식약처 제조공정 코드 전문가입니다.
사용자가 입력한 제조공정 설명 텍스트를 분석하여, 식약처 공식 공정 코드를 추천합니다.

## 출력 형식
반드시 아래 JSON 배열만 출력하세요. 설명이나 마크다운 없이 순수 JSON만 반환합니다.

[
  {{
    "code": "A6",
    "name": "혼합",
    "reason": "원문 '재료를 혼합하여' → 혼합 공정에 해당",
    "is_recommended": true,
    "confusion_note": ""
  }},
  {{
    "code": "J2",
    "name": "교반",
    "reason": "혼합과 유사하나 교반은 액체·반액체 특화",
    "is_recommended": false,
    "confusion_note": "A6(혼합)은 모든 상태의 혼합, J2(교반)은 액체/반액체 교반에 특화. 고체 혼합은 A6이 적합."
  }}
]

## 규칙
1. 추천 코드(is_recommended=true): 입력 텍스트에 해당하는 공정 코드를 순서대로 모두 추출합니다.
2. 유사 코드(is_recommended=false): 추천 코드 1개당 1~2개의 혼동 가능 코드를 반드시 추가합니다.
3. confusion_note는 절대 비워두지 마세요. 추천 코드와 어떻게 다른지 한 문장으로 명확히 씁니다.
4. 공정 순서를 유지합니다 (먼저 일어나는 공정이 배열 앞에 옵니다).
5. 하나의 문장에 여러 공정이 있으면 각각 별도 코드로 분리합니다.

## 식약처 공식 공정 코드 참조 테이블 (211개)
{_PROCESS_CODE_TABLE}
"""


async def suggest_process_codes(text: str) -> ProcessCodeSuggestResponse:
    """사용자가 직접 입력한 공정 설명 텍스트에서 식약처 공정 코드 추천.

    is_incomplete=True인 경우 또는 사용자가 공정 설명을 수동 입력할 때 사용.
    추천 코드(is_recommended=True) + 유사 코드(is_recommended=False) 함께 반환.

    ⚠️ 현재: OpenAI 사용 (임시) → 최종: Claude로 롤백
    """
    logger.info(f"공정 코드 추천 시작: '{text[:80]}...' ({len(text)}자)")

    # >>> OPENAI TEMP
    response_text = await _call_openai(_PROCESS_SUGGEST_SYSTEM_PROMPT, text)
    # response_text = await _call_openai_alt(_PROCESS_SUGGEST_SYSTEM_PROMPT, text)
    # <<< OPENAI TEMP

    # JSON 파싱
    cleaned = response_text
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0]

    suggestions: list[ProcessCodeSuggestItem] = []
    try:
        raw_list = json.loads(cleaned.strip())
        if not isinstance(raw_list, list):
            raise ValueError("응답이 배열 형식이 아닙니다.")
        for item in raw_list:
            if not isinstance(item, dict) or not item.get("code"):
                continue
            code = str(item.get("code", ""))
            # LLM이 반환한 name 대신 PROCESS_CODE_MAP 공식 이름 사용 (오류 방지)
            official_name = PROCESS_CODE_MAP.get(code, "")
            suggestions.append(ProcessCodeSuggestItem(
                code=code,
                name=official_name,
                reason=str(item.get("reason", "")),
                is_recommended=bool(item.get("is_recommended", True)),
                confusion_note=str(item.get("confusion_note", "")),
            ))
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"공정 코드 추천 JSON 파싱 실패: {e}\n원문: {response_text[:300]}")

    logger.info(f"공정 코드 추천 완료: {len(suggestions)}개 후보")
    return ProcessCodeSuggestResponse(suggestions=suggestions, input_text=text)
