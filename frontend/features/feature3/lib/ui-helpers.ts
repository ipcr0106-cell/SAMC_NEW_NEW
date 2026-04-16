/**
 * 프론트 UI 전용 헬퍼 — 백엔드 로직과 별개로 프런트에서만 사용.
 *
 * 매칭·서류 목록 조회는 Python 백엔드(/api/v1/required-docs) 담당이고,
 * 이 파일은 반환된 각 서류를 화면에 더 친절하게 풀어 보여주기 위한
 * "발급처·형식 안내" / "상세 사유 설명" 두 함수를 제공한다.
 */

// ── 최소 타입 정의 (백엔드 응답과 호환) ─────────────────

/** 백엔드 /api/v1/required-docs 응답 중 각 서류 필드 (UI 에서 쓰는 subset). */
export interface DocForUi {
  doc_name: string;
  condition?: string | null;
  submission_type?: "submit" | "keep";
}

/** UI 에 표시할 제품 정보 (상세 사유 설명에만 씀). */
export interface ProductForUi {
  food_type?: string;
  origin_country?: string;
  is_oem?: boolean;
  is_first_import?: boolean;
  has_organic_cert?: boolean;
  product_keywords?: string[];
}


// ── 1) 발급처·형식 안내 (제조사 요청서 모드) ──────────────

export function getIssuerInfo(
  doc: DocForUi,
): { issuer: string; format: string; note?: string } {
  const name = doc.doc_name;

  if (name.includes("정부증명서") || name.includes("수출국 정부") || name.includes("NAQS") || name.includes("정부 인정")) {
    return {
      issuer: "수출국 정부 기관 (농림축산·식품·검역 관련 부처)",
      format: "정부 공식 발급 원본 (영문 또는 해당국 언어 + 한글 번역본 권장)",
      note: "정부기관 직인·서명 필수. 전자증명서도 수용 가능 (통신망 확인 가능한 경우)",
    };
  }
  if (name.includes("시험") || name.includes("검사성적서") || name.includes("정밀검사") || name.includes("THC") || name.includes("다이옥신") || name.includes("PET 재활용") || name.includes("방사성")) {
    return {
      issuer: "한국 식약처가 인정한 국외 시험·검사기관 또는 수출국 공인 분석기관",
      format: "공인기관 발행 원본 성적서 (영문 가능)",
      note: "시험 항목·측정값·검사 방법 명시 필수. 발급 후 1년 이내 유효분 권장",
    };
  }
  if (name.includes("위생증명서") || name.includes("검사증명서")) {
    return {
      issuer: "수출국 정부 기관 (수의·검역·보건 관련 부처)",
      format: "수출국 정부 발행 원본 (영문)",
      note: "가축전염병·위생 기준 충족 확인. 한국-수출국 협약 체결국은 통신망 확인도 가능",
    };
  }
  if (name.includes("구분유통") || name.includes("GMO")) {
    return {
      issuer: "① 수출국 정부 인정 기관 ② 한국 식약처 지정 시험기관 ③ 생산·유통업체 구분유통증명 중 택1",
      format: "원본 증명서 또는 시험성적서 (영문)",
      note: "GMO 표시된 제품은 면제. 고도 정제 당류·유지류(GM DNA 미검출)도 면제 가능",
    };
  }
  if (name.includes("열처리") || name.includes("공정 확인") || name.includes("껍질") || name.includes("시안배당체")) {
    return {
      issuer: "제조사 자체 발급 (제조공정 관리자·책임자 서명)",
      format: "제조사 공식 문서 (영문 가능). 제조·가공 공정 상세 기재",
      note: "공정 조건(온도·시간·방법) 구체 명시 필수",
    };
  }
  if (name.includes("한글표시") || name.includes("수입식품 사진")) {
    return {
      issuer: "수입자(귀사 한국 수입 거래처) 자체 작성",
      format: "한글로 인쇄된 포장지 원본 또는 한글 스티커 부착 (수입식품 표시기준 준수)",
      note: "수입자가 한국 법령에 맞게 작성. 제조사 지원 필요 없음",
    };
  }
  if (name.includes("수출계획") || name.includes("영업허가") || name.includes("품목제조보고")) {
    return {
      issuer: "수입자 내부 서류",
      format: "수입자 자체 작성·준비",
      note: "외화획득용·자사제품 제조용 수입에만 해당. 전산 확인 가능 시 제출 생략",
    };
  }
  if (name.includes("유통기한") || name.includes("소비기한")) {
    return {
      issuer: "제조사 또는 수입자 공동 작성",
      format: "설정 근거 자료 포함 공식 문서 (제조공정·보관조건·시험결과 기반)",
      note: "OEM 수입식품만 해당. 유통기한 연장 시 연장사유서 별도",
    };
  }
  if (name.includes("학명")) {
    return {
      issuer: "제조사 또는 수출국 공인기관",
      format: "학명(Latin binomial) 명시 공식 문서",
      note: "2026.7.1. 선적분부터 제출 의무화",
    };
  }
  return {
    issuer: "수출국 관련 기관 또는 제조사",
    format: "공식 증빙 문서 (영문 가능)",
  };
}


// ── 2) 상세 사유 설명 (서류 카드 확장 모드) ────────────────

export function buildDetailedReason(doc: DocForUi, info: ProductForUi): string {
  const name = doc.doc_name;
  const origin = info.origin_country || "(제조국)";
  const foodType = info.food_type || "(식품유형)";

  if (name.includes("한글표시")) {
    return `한국 「식품등의 표시기준」(식약처 고시)에 따라 한국 시장에 유통되는 모든 수입식품은 제품명·원재료·유통기한·제조원·수입원 등의 정보를 한글로 표시해야 합니다. 한글표시가 인쇄된 포장지 또는 한글 스티커를 부착한 포장지를 제출하거나, 한글표시 내용이 기재된 서류를 제출합니다.`;
  }
  if (name.includes("수입식품 사진")) {
    return `한국 식약처는 수입 신고 시 실제 제품의 포장 상태를 확인하기 위해 제품 사진을 요구합니다. 제품 전면·후면(라벨 포함)·측면 사진을 고화질로 준비해 주시기 바랍니다.`;
  }
  if (name.includes("ASF")) {
    return `한국은 아프리카돼지열병(ASF) 발생 73개국(귀사 소재국 ${origin} 포함)에서 수입되는 돼지 원료 제품에 대해, ASF 바이러스 비검출 또는 열처리로 인한 비활성화를 증명하는 서류를 요구합니다. 이는 한국 가축전염병 예방법 및 수입식품안전관리 특별법 시행규칙 제27조에 근거합니다. 아래 3가지 중 한 가지로 대체 가능합니다: ① 70℃ 30분 이상 또는 동등 공정 열처리 증명서 ② ASF 바이러스 비검출 검사성적서 ③ ASF FREE 국가 또는 지역 선언 정부증명서.`;
  }
  if (name.includes("BSE") || name.includes("반추동물") || name.includes("우지") || name.includes("우피") || name.includes("소뼈")) {
    return `한국은 소해면상뇌증(BSE·광우병) 발생 이력이 있는 36개국에서 수입되는 반추동물(소·양·사슴) 원료 및 부산물에 대해 안전성 증명 서류를 요구합니다. 수출국 정부가 해당 원료가 BSE 미발생국 산이거나 건강한 반추동물에서 유래했음을 증명해야 합니다. 이는 한국 가축전염병 예방법에 근거합니다.`;
  }
  if (name.includes("수출 위생증명서") || (name.includes("위생증명서") && !name.includes("수산"))) {
    return `한국 축산물위생관리법 및 수입식품안전관리 특별법은 축산물(식육·유가공품·알가공품) 수입 시 수출국 정부 기관이 발행한 위생증명서를 요구합니다. 이는 해당 제품이 수출국의 위생·검역 기준을 충족하며 안전하게 가공·보관되었음을 증명합니다. 귀사 소재국 ${origin}의 수의·검역 담당 정부 기관에서 발급받으실 수 있습니다.`;
  }
  if (name.includes("위생증명서") && name.includes("수산")) {
    return `한국과 협약을 체결한 국가(귀사 소재국 ${origin} 포함)에서 수입되는 수산물은 수출국 정부 기관이 발행한 위생증명서 또는 검사증명서가 필요합니다. 협약에 따라 통신망으로 증명서 확인이 가능한 경우 제출을 생략할 수 있습니다.`;
  }
  if (name.includes("GMO") || name.includes("구분유통")) {
    return `한국 「유전자변형식품등의 표시기준」에 따라 유전자변형식품 표시대상 원료(대두·옥수수·카놀라·면실·사탕무·알팔파·감자)를 함유하고 있으며 GMO 표시를 하지 않은 제품은 다음 중 하나를 제출해야 합니다: ① 구분유통증명서(Non-GMO IP Handling) ② 수출국 정부 인정 동등효력 증명서 ③ GMO 비해당 시험·검사성적서. 고도 정제된 당류·유지류(GM DNA·단백질 잔존 없음)는 면제됩니다.`;
  }
  if (name.includes("복어")) {
    return `한국은 복어의 독성(Tetrodotoxin) 때문에 복어 원료 제품 수입 시 ① 복어 종류 확인서 ② 독성 시험성적서 ③ 가공공정 확인서 3종을 요구합니다. 식용 가능한 복어 3종(황복·자주복·검복)에 한해 허용되며, 제독·가공 공정 증명이 필수입니다.`;
  }
  if (name.includes("방사성") || (name.includes("일본") && name.includes("도현"))) {
    return `일본산 식품에 대한 한국의 방사능 안전 기준에 따라, 후쿠시마 원전 사고 이후 지정된 13개 도·현(후쿠시마·이바라키·토치키·군마·사이타마·치바·미야기·가나가와·도쿄·나가노·야마가타·니이가타·시즈오카) 생산 식품은 방사성 물질 검사성적서가 필수입니다. 이 외 34개 도·부·현 생산 식품도 방사성 물질 비오염 생산지 증명서가 요구됩니다.`;
  }
  if (name.includes("대마") || name.includes("THC")) {
    return `한국 식품공전은 대마씨앗(껍질 완전 제거)을 식품 원료로 허용하되, THC(테트라하이드로칸나비놀) 및 CBD(칸나비디올) 함량이 극미량 기준 이하여야 합니다. 대마씨앗: THC 5ppm 이하·CBD 10ppm 이하 / 대마씨유: THC 10ppm 이하·CBD 20ppm 이하. 공인기관 검사성적서 원본을 요구합니다.`;
  }
  if (doc.condition === "OEM" || name.includes("소비기한 설정사유서")) {
    return `한국 수입자의 상표를 부착하여 해외에서 제조한 주문자상표부착(OEM) 수입식품은 한국 식약처가 유통기한의 타당성을 별도 검증합니다. 제조공정·보관조건·시험결과를 기반으로 한 유통기한 설정사유서를 매 수입 시 제출해야 합니다.`;
  }
  if (name.includes("NAQS") || doc.condition === "동등성인정") {
    return `한국과 ${origin} 간 유기가공식품 동등성인정 협정에 따라, ${origin}산 유기인증 가공식품(유기원료 95% 이상)은 NAQS(국립농산물품질관리원) 수입증명서로 한국 유기 표시가 가능합니다. 협정 체결국 공식 유기인증기관 발급 증명이 필요합니다.`;
  }
  if (name.includes("PET")) {
    return `한국은 중국·대만·베트남·태국산 PET 재질 식품용 기구·용기·포장에 대해, 재활용 PET 사용 여부 및 재질 확인 증명을 요구합니다. 재활용 PET는 식품용 사용이 제한되므로, 제조회사 발행 재질확인증명서 원본을 매 수입 시 제출해야 합니다.`;
  }
  if (name.includes("국외 시험") || doc.condition === "정밀검사대상") {
    return `한국 식약처가 지정한 정밀검사 대상 수입식품은, 한국 식약처가 인정한 국외 시험·검사기관이 발행한 시험·검사성적서가 필수입니다. 식약처가 지정한 검사항목에 대한 성적서여야 하며, 발급 후 1년 이내 유효분을 권장합니다.`;
  }
  if (name.includes("수출계획서") || doc.condition === "외화획득용") {
    return `한국 대외무역법에 따라 외화획득용으로 수입하는 식품은, 수입 후 가공·제조하여 수출할 목적임을 증명하는 수출계획서가 필요합니다. 국내 반입 후 구체적인 수출 계획(수출국·수량·일정 등)이 기재되어야 합니다.`;
  }
  if (name.includes("학명")) {
    return `2026년 7월 1일 선적분부터 한국은 학명(Latin binomial)이 정해진 농·임산물·수산물·조류·생녹용 수입 시 학명 기재 자료를 요구합니다. 이는 원료 동정(同定)의 정확성을 높이고 유사 원료 혼입을 방지하기 위함입니다. 해당 원료의 학명(속명·종명)이 명시된 공식 서류가 필요합니다.`;
  }
  if (name.includes("할랄")) {
    return `할랄(Halal) 인증 식품으로 표시·광고하려는 경우, 해외 할랄 인증기관이 발행한 인증서 사본이 필요합니다.`;
  }
  if (doc.submission_type === "keep") {
    return `${name.replace(" [보관]", "")}은(는) 수입 신고 시 제출하지 않으나 영업자가 보관해야 하는 서류입니다. 식약처가 관리·감독 차원에서 제시를 요청할 수 있습니다. 귀사는 해당 공정(${foodType} 제조·가공) 관련 증빙을 보관하여 요청 시 제공해야 합니다.`;
  }
  return `한국 수입식품안전관리 특별법 시행규칙 제27조에 근거하여 해당 제품 특성(${foodType}, 제조국: ${origin})상 필요한 서류입니다. 법령 원문을 확인하시거나 한국 수입자와 협의하시기 바랍니다.`;
}
