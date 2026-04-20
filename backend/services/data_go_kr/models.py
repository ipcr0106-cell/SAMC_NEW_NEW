"""data.go.kr 4 엔드포인트 응답 Pydantic 모델 — W1-A 트랙 구현.

raw 응답을 도메인 타입으로 매핑한다. 07번 §2-1/2-4 `Ingredient`·`StandardCheck`
와 필드명이 정합되도록 설계. 신규 필드 추가는 허용하나 기존 필드명·타입 변경은
W1-B 트랙과 공동 합의 필요.

응답 공통 껍질 (data.go.kr 표준):
    {
      "response": {
        "header": {"resultCode": "00", "resultMsg": "..."},
        "body": {
          "pageNo": 1, "numOfRows": 10, "totalCount": N,
          "items": [{...}, {...}]   # 또는 [] / None
        }
      }
    }

참조:
    - 계획/f1 재설계 계획/06_API_클라이언트_설계.md §5
    - 계획/f1 재설계 계획/07_데이터_모델_변경_설계.md §2-1, §2-4
    - 계획/f1 재설계 계획/F1_공공데이터_API_탐색보고서.md §2-1~§2-4
"""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 공통 응답 껍질
# ---------------------------------------------------------------------------


class DataGoKrHeader(BaseModel):
    """data.go.kr 표준 `response.header` 블록."""

    model_config = ConfigDict(extra="allow")

    result_code: str = Field(..., alias="resultCode")
    result_msg: Optional[str] = Field(default=None, alias="resultMsg")


class DataGoKrBody(BaseModel):
    """data.go.kr 표준 `response.body` 블록 (items 타입은 엔드포인트별 상이)."""

    model_config = ConfigDict(extra="allow")

    page_no: Optional[int] = Field(default=None, alias="pageNo")
    num_of_rows: Optional[int] = Field(default=None, alias="numOfRows")
    total_count: Optional[int] = Field(default=None, alias="totalCount")
    items: List[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 15111777 수입식품 원료정보
# ---------------------------------------------------------------------------


class IngredientInfo(BaseModel):
    """15111777 IprtFoodIngdInfoService item.

    07번 §2-1 `Ingredient`의 `allow_verdict`/`restriction_condition`/`edible_parts`
    필드와 정합. `verdict` 파생은 Step B 소관이므로 여기서는 raw 필드만 노출.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    ingd_sn: Optional[str] = Field(default=None, alias="INGD_SN")
    ingd_nm: str = Field(..., alias="INGD_NM")
    nknm_nm: Optional[str] = Field(default=None, alias="NKNM_NM")
    scnnm_nm: Optional[str] = Field(default=None, alias="SCNNM_NM")
    drnm: Optional[str] = Field(default=None, alias="DRNM")
    edible_info: Optional[str] = Field(default=None, alias="EDIBLE_INFO")
    edible_y: Optional[str] = Field(default=None, alias="EDIBLE_Y")
    edible_n: Optional[str] = Field(default=None, alias="EDIBLE_N")
    edible_use_cont: Optional[str] = Field(default=None, alias="EDIBLE_USE_CONT")
    chrtr_info_cont: Optional[str] = Field(default=None, alias="CHRTR_INFO_CONT")
    anml_info: Optional[str] = Field(default=None, alias="ANML_INFO")


# ---------------------------------------------------------------------------
# 15094202 수입식품 성분코드 정보
# ---------------------------------------------------------------------------


class ComponentInfo(BaseModel):
    """15094202 IprtFoodCpntCdInfoFoodService item.

    07번 §2-1 `Ingredient.component_code` 와 매핑. `KOR_NM` 앞 공백은
    `DataGoKrClient` 가 strip 처리한다.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    cpnt_cd: str = Field(..., alias="CPNT_CD")
    kor_nm: Optional[str] = Field(default=None, alias="KOR_NM")
    eng_nm: Optional[str] = Field(default=None, alias="ENG_NM")
    nknm_info_cont: Optional[str] = Field(default=None, alias="NKNM_INFO_CONT")
    cpnt_lcls_cd_nm: Optional[str] = Field(default=None, alias="CPNT_LCLS_CD_NM")
    use_divs_cd_nm: Optional[str] = Field(default=None, alias="USE_DIVS_CD_NM")


# ---------------------------------------------------------------------------
# 15116583 식품첨가물 기준규격
# ---------------------------------------------------------------------------


class AdditiveSpec(BaseModel):
    """15116583 FoodWStndStusService item.

    07번 §2-4 `StandardCheck` 필드와 정합:
        - T_KOR_NM → test_category
        - SPEC_VAL → spec_raw
        - SPEC_VAL_SUMUP → spec_summary
        - INJRY_YN == "Y" → is_dangerous
        - UNIT_NM → unit_original (Step C 에서 unit_converter 로 정규화)
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    pc_kor_nm: str = Field(..., alias="PC_KOR_NM")
    prdlst_cd: Optional[str] = Field(default=None, alias="PRDLST_CD")
    t_kor_nm: Optional[str] = Field(default=None, alias="T_KOR_NM")
    fnprt_itm_nm: Optional[str] = Field(default=None, alias="FNPRT_ITM_NM")
    piam_kor_nm: Optional[str] = Field(default=None, alias="PIAM_KOR_NM")
    spec_val: Optional[str] = Field(default=None, alias="SPEC_VAL")
    spec_val_sumup: Optional[str] = Field(default=None, alias="SPEC_VAL_SUMUP")
    mimm_val: Optional[str] = Field(default=None, alias="MIMM_VAL")
    mxmm_val: Optional[str] = Field(default=None, alias="MXMM_VAL")
    unit_nm: Optional[str] = Field(default=None, alias="UNIT_NM")
    injry_yn: Optional[str] = Field(default=None, alias="INJRY_YN")
    sorc: Optional[str] = Field(default=None, alias="SORC")
    vald_begn_dt: Optional[str] = Field(default=None, alias="VALD_BEGN_DT")
    vald_end_dt: Optional[str] = Field(default=None, alias="VALD_END_DT")
    updt_prvns: Optional[str] = Field(default=None, alias="UPDT_PRVNS")
    last_updt_dtm: Optional[str] = Field(default=None, alias="LAST_UPDT_DTM")


# ---------------------------------------------------------------------------
# 15111913 식품 원재료 정보 (GMO)
# ---------------------------------------------------------------------------


class RawMaterialInfo(BaseModel):
    """15111913 FoodRwmtInfo item.

    07번 §2-1 `Ingredient.is_gmo` 에 매핑되는 `GMO_YN` 필드가 핵심.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    orm_std_nm: str = Field(..., alias="ORM_STD_NM")
    orm_std_nm_eng: Optional[str] = Field(default=None, alias="ORM_STD_NM_ENG")
    orm_std_cd: Optional[str] = Field(default=None, alias="ORM_STD_CD")
    gmo_yn: Optional[str] = Field(default=None, alias="GMO_YN")
    import_yn: Optional[str] = Field(default=None, alias="IMPORT_YN")
    prv_natn_cd: Optional[str] = Field(default=None, alias="PRV_NATN_CD")
    orm_spec: Optional[str] = Field(default=None, alias="ORM_SPEC")
    orm_spec_unit: Optional[str] = Field(default=None, alias="ORM_SPEC_UNIT")
    hrnk_rawmtrl_ordno: Optional[str] = Field(
        default=None, alias="HRNK_RAWMTRL_ORDNO"
    )
    orm_ordno: Optional[str] = Field(default=None, alias="ORM_ORDNO")
    prdlst_report_ledg_no: Optional[str] = Field(
        default=None, alias="PRDLST_REPORT_LEDG_NO"
    )
    entp_cd: Optional[str] = Field(default=None, alias="ENTP_CD")
    use_flag: Optional[str] = Field(default=None, alias="USE_FLAG")


__all__ = [
    "DataGoKrHeader",
    "DataGoKrBody",
    "IngredientInfo",
    "ComponentInfo",
    "AdditiveSpec",
    "RawMaterialInfo",
]
