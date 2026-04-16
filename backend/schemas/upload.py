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


class BasicInfo(BaseModel):
    """기본 정보. 프론트엔드 BasicInfoCard 대응."""
    product_name: str = Field(default="", description="제품명")
    export_country: str = Field(default="", description="수출국")
    is_first_import: bool = Field(default=False, description="최초 수입 여부")
    is_organic: bool = Field(default=False, description="유기인증 여부")
    is_oem: bool = Field(default=False, description="OEM 여부")


class ProcessCodeReason(BaseModel):
    """공정 코드 1개의 선정 근거 (하위 호환용)."""
    code: str = Field(description="공정 코드 (예: '01')")
    reason: str = Field(description="해당 코드를 선택한 근거 (원문 기반 설명)")


class ProcessCodeCandidate(BaseModel):
    """AI가 검토한 공정 코드 후보 1개.

    is_recommended=True  → AI 최종 추천 (process_codes에 포함됨)
    is_recommended=False → 유사/혼동 가능 코드 (참고용, 사용자가 직접 선택 가능)
    """
    code: str = Field(description="공정 코드 (예: '35')")
    reason: str = Field(description="이 코드를 추천/고려한 근거 (원문 기반)")
    is_recommended: bool = Field(description="True=AI 최종 추천, False=유사 코드")
    confusion_note: str = Field(
        default="",
        description="유사 코드일 때 — 추천 코드와 어떻게 다른지 구별 포인트",
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
