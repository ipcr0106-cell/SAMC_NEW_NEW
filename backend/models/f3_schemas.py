"""
기능 3 (수입 필요서류 안내) Pydantic 스키마.

입력:
  ProductInfo — 기능 1·2에서 넘어온 제품 정보 (category, food_type, 원재료 등)

출력:
  RequiredDocsResponse — 제출·보관 서류 목록 + 경고 + 매칭 근거
"""
from typing import Literal, Optional
from pydantic import BaseModel, Field


FoodCategory = Literal[
    "축산물",
    "수산물",
    "가공식품",
    "농.임산물",
    "식품첨가물",
    "기구또는용기.포장",
    "건강기능식품",
]


class ProductInfo(BaseModel):
    """기능 1·2에서 확정되어 넘어오는 제품 정보."""

    category: Optional[FoodCategory] = Field(
        None,
        description="식약처 7대 구분 (기능 2 출력)",
    )
    food_large_category: Optional[str] = Field(
        None,
        description="식품공전 대분류 (기능 2 출력). 예: '식육가공품', '유가공품', '음료류'",
    )
    food_mid_category: Optional[str] = Field(
        None,
        description="식품공전 중분류 (기능 2 출력). 예: '햄류', '자연치즈', '발효유류'",
    )
    food_type: str = Field(..., description="식품공전 소분류 식품유형. 예: '프레스햄', '우유', '탁주'")
    origin_country: str = Field(..., description="제조국 한글명. 예: '중국', '미국'")
    is_oem: bool = Field(False, description="주문자상표부착 수입식품 여부")
    is_first_import: bool = Field(False, description="최초 수입 여부")
    has_organic_cert: bool = Field(
        False,
        description="유기인증 95%+ 제품 여부 (동등성인정 eq1~eq4 발동 조건)",
    )
    product_keywords: list[str] = Field(
        default_factory=list,
        description="원재료/성분 키워드 목록. 예: ['돼지','soy lecithin']",
    )
    reference_date: Optional[str] = Field(
        None,
        description="effective_from/until 필터 기준일 (YYYY-MM-DD). 없으면 오늘 날짜.",
    )


class RequiredDoc(BaseModel):
    """매칭된 단일 서류 정보."""

    id: str
    food_type: Optional[str] = None
    condition: Optional[str] = None
    target_country: Optional[str] = None
    product_keywords: Optional[list[str]] = None
    doc_name: str
    doc_description: str
    is_mandatory: bool = True
    submission_type: Literal["submit", "keep"]
    submission_timing: Literal["every", "first"]
    law_source: str
    effective_from: Optional[str] = None
    effective_until: Optional[str] = None
    match_reason: Optional[str] = None
    decision_axis: Optional[str] = None


class RequiredDocsResponse(BaseModel):
    """매칭 엔진 최종 응답."""

    food_type: str
    origin_country: str
    is_first_import: bool
    submit_docs: list[RequiredDoc]
    keep_docs: list[RequiredDoc]
    total_submit: int
    total_keep: int
    warnings: list[str]
    match_confidence: Literal["high", "needs_review"] = "high"
