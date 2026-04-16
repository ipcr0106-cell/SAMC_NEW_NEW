// Mock API — 실제 팀 repo에서는 백엔드 호출로 교체

const MOCK_DATA = {
  food_type: "과채음료",
  origin_country: "태국",
  is_first_import: true,
  submit_docs: [
    {
      id: "1",
      doc_name: "한글표시 포장지 또는 한글표시 서류",
      doc_description: "한글표시가 인쇄된 스티커를 붙인 포장지 포함. 모든 수입식품에 공통 적용.",
      is_mandatory: true,
      submission_type: "submit" as const,
      submission_timing: "every" as const,
      law_source: "수입식품안전관리 특별법 시행규칙 제27조제1항제1호",
      condition: null,
      target_country: null,
    },
    {
      id: "2",
      doc_name: "수입식품 사진",
      doc_description: "별표9 제2호가목 1)~3) 해당 식품 및 식약처 홈페이지 게시 식품은 제외. 모든 수입식품에 공통 적용.",
      is_mandatory: true,
      submission_type: "submit" as const,
      submission_timing: "every" as const,
      law_source: "수입식품안전관리 특별법 시행규칙 제27조제1항제1의2호",
      condition: null,
      target_country: null,
    },
    {
      id: "3",
      doc_name: "PET 재활용 여부 재질확인증명서",
      doc_description: "중국, 대만, 베트남, 태국산 PET(폴리에틸렌테레프탈레이트) 재질 식품용 기구(컵, 트레이, 도시락, 반찬통, 물병 등 주방용품, 본체 및 뚜껑 포함). 매 수입 시 제조회사 재질확인증명서 원본 제출: 재활용PET 미사용 증명 또는 화학적 재생(분해·정제·중합) 재활용PET 사용 증명.",
      is_mandatory: true,
      submission_type: "submit" as const,
      submission_timing: "every" as const,
      law_source: "수입식품안전관리 특별법 시행규칙 제27조제1항제10호다목",
      condition: null,
      target_country: "중국,대만,베트남,태국",
    },
    {
      id: "4",
      doc_name: "다이옥신 잔류량 검사성적서",
      doc_description: "죽염, 구운소금 등 태움·용융소금 및 이를 함유한 가공소금. 최초 수입 시 제출, 이후 동일사 동일수입식품인 경우 생략 가능. 기준: 3pgTEQ/g 이하. 원본 제출.",
      is_mandatory: true,
      submission_type: "submit" as const,
      submission_timing: "first" as const,
      law_source: "수입식품안전관리 특별법 시행규칙 제27조제1항제10호나목",
      condition: null,
      target_country: null,
    },
    {
      id: "5",
      doc_name: "NAQS 수입증명서 (한미 유기가공식품 동등성인정)",
      doc_description: "미국산 유기가공식품. 적용 조건: ① 미국 규정에 따라 유기인증 ② 미국 내 최종 가공 ③ 유기원료 95% 이상. 제한: 항생제(스트렙토마이신·테트라시클린) 사용 사과·배 원료 제품은 유기표시 불가. 수출국 인증기관이 eNAQS Import Certificate System에 작성. 매 수입 시.",
      is_mandatory: true,
      submission_type: "submit" as const,
      submission_timing: "every" as const,
      law_source: "친환경농어업 육성 및 유기식품 등의 관리·지원에 관한 법률 제25조; 한미 유기가공식품 상호 동등성인정 협정 (2014.7.1. 발효)",
      condition: "동등성인정",
      target_country: "미국",
    },
  ],
  keep_docs: [
    {
      id: "k1",
      doc_name: "아마씨 시안배당체 제거 제조사 증명서 [보관]",
      doc_description: "아마씨 및 아마씨 함유제품. 열처리 등으로 시안배당체가 제거되어 안전성을 확인할 수 있는 제조사 증명서 보관. 제빵용 프리믹스·냉동생지 등 열처리 공정을 거치는 제품의 원료로 사용되는 경우 제외.",
      is_mandatory: true,
      submission_type: "keep" as const,
      submission_timing: "every" as const,
      law_source: "수입식품안전관리 특별법 시행규칙 제27조제1항제10호다목",
      condition: null,
      target_country: null,
    },
    {
      id: "k2",
      doc_name: "젤라틴 원료유래 확인 제조회사 증명서 [보관]",
      doc_description: "젤라틴을 원료로 한 제품. 사용한 젤라틴의 원료유래 물질을 확인할 수 있는 제조회사 발행 증명서.",
      is_mandatory: true,
      submission_type: "keep" as const,
      submission_timing: "every" as const,
      law_source: "수입식품안전관리 특별법 시행규칙 제27조제1항제10호다목",
      condition: null,
      target_country: null,
    },
  ],
  total_submit: 5,
  total_keep: 2,
};

export const getRequiredDocs = async (_caseId: string) => {
  // 0.5초 딜레이로 실제 API 호출 시뮬레이션
  await new Promise((r) => setTimeout(r, 500));
  return MOCK_DATA;
};

export const confirmRequiredDocs = async (_caseId: string) => {
  await new Promise((r) => setTimeout(r, 300));
  return { confirmed_at: new Date().toISOString() };
};
