"""
SAMC 수입식품 검역 AI — 업로드 및 파싱 Pydantic 스키마
프론트엔드 OcrResultEditor와 1:1 매핑되는 응답 구조.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# 공통 Enum
# ─────────────────────────────────────────────

class DocType(str, Enum):
    """documents 테이블의 doc_type 컬럼과 일치."""
    INGREDIENTS = "ingredients"
    PROCESS = "process"
    MSDS = "msds"
    MATERIAL = "material"
    LABEL = "label"
    OTHER = "other"


class ParseStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


# ─────────────────────────────────────────────
# 업로드 요청/응답
# ─────────────────────────────────────────────

class UploadResponse(BaseModel):
    """POST /cases/{case_id}/upload 응답."""
    doc_id: str
    file_name: str
    storage_path: str
    doc_type: DocType
    mime_type: Optional[str] = None
    created_at: datetime


# ─────────────────────────────────────────────
# 파싱 결과 — 프론트엔드 OcrResultEditor 대응
# ─────────────────────────────────────────────

class IngredientItem(BaseModel):
    """원재료 한 행. 프론트엔드 IngredientTable의 Ingredient 인터페이스와 매핑."""
    id: str = Field(description="고유 식별자 (프론트에서 key로 사용)")
    name: str = Field(description="성분명 (한국어 또는 원문)")
    ratio: str = Field(default="", description="배합비율(%) — 문자열로 유지하여 소수점 보존")
    origin: str = Field(default="", description="원산지 국가")
    ins_number: str = Field(default="", description="INS 번호 (식품첨가물)")
    cas_number: str = Field(default="", description="CAS 번호")
    part: str = Field(default="", description="사용 부위 (예: 잎, 뿌리, 줄기) — F1 조건부 원료 판정용")
    ingredient_code: str = Field(
        default="",
        description=(
            "식약처 성분 코드 (예: 'A01010', 'B00123') — "
            "파싱 후 f0_ingredient_codes 테이블에서 자동 조회하여 채워짐. "
            "A=식품원료, B=식품첨가물, C=건강기능식품, P=식품유형"
        ),
    )
    ingredient_code_name: str = Field(
        default="",
        description="ingredient_code에 해당하는 공식 성분명 (한국어). 코드 조회 시 함께 채워짐.",
    )
    sub_ingredients: list[IngredientItem] = Field(
        default_factory=list,
        description="복합원재료의 하위 성분 목록 — F1 재귀 검증용 (예: 과일혼합의 딸기, 블루베리)",
    )


IngredientItem.model_rebuild()  # 자기 참조(recursive) 모델 완성


class BasicInfo(BaseModel):
    """기본 정보. 프론트엔드 BasicInfoCard 대응."""
    product_name: str = Field(default="", description="제품명")
    export_country: str = Field(default="", description="수출국")
    is_first_import: bool = Field(default=False, description="최초 수입 여부")
    is_organic: bool = Field(default=False, description="유기인증 여부")
    is_oem: bool = Field(default=False, description="OEM 여부")
    manufacturer: str = Field(default="", description="제조사명 — F4 교차검증용")
    alcohol_percentage: Optional[float] = Field(
        default=None,
        description="알코올 도수(%) — 주류 제품만, 없으면 null. F1 주류 기준치 적용용",
    )
    content_volume: str = Field(
        default="",
        description="내용량 (예: 500mL, 1kg) — F4 교차검증용",
    )


class ProcessCodeReason(BaseModel):
    """공정 코드 1개의 선정 근거 (하위 호환용)."""
    code: str = Field(description="공정 코드 (예: '78')")
    name: str = Field(default="", description="공정명 (예: '증류') — PROCESS_CODE_MAP 기준")
    reason: str = Field(description="해당 코드를 선택한 근거 (원문 기반 설명)")


class ProcessCodeCandidate(BaseModel):
    """AI가 검토한 공정 코드 후보 1개.

    is_recommended=True  → AI 최종 추천 (process_codes에 포함됨)
    is_recommended=False → 유사/혼동 가능 코드 (참고용, 사용자가 직접 선택 가능)
    """
    code: str = Field(description="공정 코드 (예: '78')")
    name: str = Field(default="", description="공정명 (예: '증류') — PROCESS_CODE_MAP 기준, 항상 공식 이름")
    reason: str = Field(description="이 코드를 추천/고려한 근거 (원문 기반)")
    is_recommended: bool = Field(description="True=AI 최종 추천, False=유사 코드")
    confusion_note: str = Field(
        default="",
        description="유사 코드일 때 — 추천 코드와 어떻게 다른지 구별 포인트",
    )


class ProcessStep(BaseModel):
    """공정 흐름도 1단계(박스 1개)의 분석 결과.

    is_incomplete가 False인 경우 각 단계별로 이 구조가 채워짐.
    프론트엔드에서 '1번 공정 → 코드 + 유사코드' 형태로 표시.
    """
    step_number: int = Field(description="공정 단계 번호 (1, 2, 3...)")
    step_name_original: str = Field(default="", description="원문 공정명 (OCR 그대로 — 영어/스페인어 등)")
    step_name_ko: str = Field(default="", description="한국어 공정명 (번역 또는 원문이 한국어인 경우 그대로)")
    recommended_code: str = Field(default="", description="AI 최종 추천 식약처 공정 코드 (예: '27')")
    recommended_code_name: str = Field(default="", description="추천 코드의 공식 공정명 (예: '발효') — PROCESS_CODE_MAP 기준")
    recommended_reason: str = Field(default="", description="이 코드를 선택한 근거 (원문 기반)")
    similar_codes: list[ProcessCodeCandidate] = Field(
        default_factory=list,
        description="혼동 가능한 유사 코드 목록 (is_recommended=False). 각 항목에 confusion_note 포함.",
    )


class ProcessInfo(BaseModel):
    """제조공정 정보. 프론트엔드 ProcessCodeCard 대응."""
    process_codes: list[str] = Field(
        default_factory=list,
        description="AI 최종 추천 공정 코드 목록 (예: ['01','10','15'])",
    )
    process_code_reasons: list[ProcessCodeReason] = Field(
        default_factory=list,
        description="추천 코드별 선정 근거 (하위 호환용, candidates로 대체)",
    )
    process_code_candidates: list[ProcessCodeCandidate] = Field(
        default_factory=list,
        description="추천 + 유사 코드 전체 후보 목록. 프론트 선택 UI에 표시.",
    )
    raw_process_text: str = Field(
        default="",
        description="OCR로 읽은 공정 원문 (디버깅·참고용)",
    )
    process_steps: list[ProcessStep] = Field(
        default_factory=list,
        description=(
            "단계별 공정 분석 결과. 공정도의 각 박스(단계) 1개가 ProcessStep 1개로 매핑됨. "
            "step_number 순서대로 정렬. is_incomplete=True이면 빈 배열."
        ),
    )
    is_incomplete: bool = Field(
        default=False,
        description=(
            "공정 파싱 불완전 여부. True이면 프론트가 '파싱 불가 — 직접 입력 필요' 안내를 표시함. "
            "파일 품질 불량, 공정 설명 불충분, OCR 텍스트 손상 등으로 코드 추출이 불가한 경우 True."
        ),
    )
    incomplete_reason: str = Field(
        default="",
        description=(
            "파싱 불완전 이유. is_incomplete=True일 때만 의미 있음. "
            "예: '제조공정도 텍스트가 거의 없어 공정 코드를 추출할 수 없습니다. 공정 설명을 직접 입력해주세요.'"
        ),
    )


class LabelInfo(BaseModel):
    """수출국 라벨 분석 결과. 프론트엔드 LabelInfoCard 대응."""
    export_country: str = Field(default="", description="수출국")
    is_oem: bool = Field(default=False, description="OEM 여부")
    label_texts: list[str] = Field(
        default_factory=list,
        description="라벨에서 추출한 문구/텍스트 목록",
    )
    design_description: str = Field(
        default="",
        description="라벨 디자인 설명 (그림, 색상, 레이아웃 등)",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="경고문구, 주의사항 목록",
    )


class ParsedResult(BaseModel):
    """전체 파싱 결과. /parse 엔드포인트의 핵심 응답 바디."""
    basic_info: BasicInfo
    ingredients: list[IngredientItem] = Field(default_factory=list)
    process_info: ProcessInfo = Field(default_factory=ProcessInfo)
    label_info: LabelInfo = Field(default_factory=LabelInfo)


class ParseResponse(BaseModel):
    """POST /cases/{case_id}/parse 응답."""
    case_id: str
    status: ParseStatus
    parsed_result: Optional[ParsedResult] = None
    suggested_title: str = Field(
        default="",
        description=(
            "파싱 결과 기반 추천 케이스 제목. 파싱 후 cases.product_name이 이 값으로 자동 업데이트됨. "
            "형식: '제품명_YYYYMMDD_케이스ID앞8자리' (예: 'TequilaDVT_20260417_a1b2c3d4')"
        ),
    )
    raw_texts: Optional[dict[str, str]] = Field(
        default=None,
        description="doc_type별 OCR 원문 텍스트 (디버깅용). 키: doc_type, 값: raw text",
    )
    extraction_errors: list[str] = Field(
        default_factory=list,
        description="OCR 텍스트 추출에 실패한 파일 목록 (파일명: 실패 이유)",
    )
    error_message: Optional[str] = None
    parsed_at: Optional[datetime] = None


# ─────────────────────────────────────────────
# 에러 응답 (팀 컨벤션 통일)
# ─────────────────────────────────────────────

class ErrorResponse(BaseModel):
    error: str = Field(description="UPPER_SNAKE 에러 코드")
    message: str = Field(description="한국어 설명")
    feature: Optional[int] = None


# ─────────────────────────────────────────────
# 공정 코드 추천 (수동 입력용)
# ─────────────────────────────────────────────

class ProcessCodeSuggestRequest(BaseModel):
    """POST /f0/suggest-process-codes 요청.

    is_incomplete=True로 파싱된 건 혹은 사용자가 직접 공정 설명을 입력하는 경우 사용.
    """
    text: str = Field(description="사용자가 입력한 공정 설명 텍스트")
    case_id: Optional[str] = Field(default=None, description="연결할 건 ID (선택, 기록 목적)")


class ProcessCodeSuggestItem(BaseModel):
    """공정 코드 추천 1건."""
    code: str = Field(description="식약처 공식 공정 코드 (예: 'A6', '27')")
    name: str = Field(description="공정명 (예: '혼합', '발효')")
    reason: str = Field(description="해당 코드를 추천한 근거 (원문 기반)")
    is_recommended: bool = Field(description="True=최종 추천, False=유사 코드(참고용)")
    confusion_note: str = Field(default="", description="유사 코드일 때 추천 코드와의 차이점")


class ProcessCodeSuggestResponse(BaseModel):
    """POST /f0/suggest-process-codes 응답."""
    suggestions: list[ProcessCodeSuggestItem] = Field(description="추천 + 유사 코드 목록")
    input_text: str = Field(description="입력받은 원문 텍스트 (확인용)")


# ─────────────────────────────────────────────
# 성분 코드 검색 (성분명 / CAS 번호 기반)
# ─────────────────────────────────────────────

class IngredientSearchRequest(BaseModel):
    """POST /f0/search-ingredient-codes 요청.

    성분명(한글/영문) 또는 CAS 번호로 식약처 성분 코드를 검색.
    """
    query: str = Field(description="검색어: 성분명(한글/영문) 또는 CAS 번호 (예: '사과농축', '64-17-5')")
    top_k: int = Field(default=5, ge=1, le=20, description="반환할 최대 결과 수 (기본 5, 최대 20)")
    search_mode: str = Field(
        default="auto",
        description=(
            "검색 방식: "
            "'auto'=자동(CAS면 정확 매칭, 아니면 유사 검색), "
            "'exact'=정확 매칭만, "
            "'fuzzy'=유사 검색만"
        ),
    )


class IngredientSearchItem(BaseModel):
    """성분 코드 검색 결과 1건."""
    code: str = Field(description="성분 코드 (예: 'A01010', 'B00123')")
    name_ko: str = Field(description="한글 성분명")
    name_en: str = Field(default="", description="영문 성분명")
    category: str = Field(default="", description="성분 구분 (예: 식품원료, 식품첨가물)")
    code_prefix: str = Field(default="", description="코드 첫 글자 (A/B/C/D/P 등)")
    score: float = Field(default=1.0, description="유사도 점수 (1.0=완전 일치, 낮을수록 유사 검색)")
    match_type: str = Field(default="exact", description="'exact'=정확 매칭, 'semantic'=유사 검색")


class IngredientSearchResponse(BaseModel):
    """POST /f0/search-ingredient-codes 응답."""
    results: list[IngredientSearchItem] = Field(description="검색 결과 목록 (유사도 내림차순)")
    query: str = Field(description="입력된 검색어")
    total: int = Field(description="반환된 결과 수")
    search_mode_used: str = Field(description="실제로 사용된 검색 방식 (exact/semantic/both)")
