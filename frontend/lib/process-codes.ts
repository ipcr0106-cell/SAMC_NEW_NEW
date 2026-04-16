/**
 * SAMC 수입식품 검역 AI — 유니패스 제조공정 코드 테이블
 *
 * 백엔드 constants/process_codes.py와 동기화 유지.
 * 카테고리별로 그룹핑하여 프론트엔드 드롭다운에서 사용.
 */

export interface ProcessCode {
  value: string;
  label: string;
}

export interface ProcessCodeGroup {
  category: string;
  codes: ProcessCode[];
}

export const PROCESS_CODE_GROUPS: ProcessCodeGroup[] = [
  {
    category: "열처리",
    codes: [
      { value: "01", label: "01 - 가열살균" },
      { value: "02", label: "02 - 가열건조" },
      { value: "03", label: "03 - 고온살균(UHT)" },
      { value: "04", label: "04 - 저온살균(LTLT)" },
      { value: "06", label: "06 - 훈연" },
      { value: "07", label: "07 - 로스팅" },
      { value: "08", label: "08 - 볶음" },
      { value: "09", label: "09 - 블랜칭(데침)" },
    ],
  },
  {
    category: "저온/냉동",
    codes: [
      { value: "05", label: "05 - 냉동" },
      { value: "11", label: "11 - 냉장" },
      { value: "12", label: "12 - 동결건조" },
      { value: "13", label: "13 - 급속냉동(IQF)" },
    ],
  },
  {
    category: "발효/숙성",
    codes: [
      { value: "10", label: "10 - 발효" },
      { value: "14", label: "14 - 숙성" },
      { value: "16", label: "16 - 유산균발효" },
      { value: "17", label: "17 - 초산발효" },
      { value: "18", label: "18 - 알코올발효" },
    ],
  },
  {
    category: "여과/분리",
    codes: [
      { value: "15", label: "15 - 여과" },
      { value: "19", label: "19 - 원심분리" },
      { value: "21", label: "21 - 막여과(멤브레인)" },
      { value: "22", label: "22 - 정밀여과(MF)" },
      { value: "23", label: "23 - 한외여과(UF)" },
      { value: "24", label: "24 - 역삼투(RO)" },
    ],
  },
  {
    category: "혼합/배합",
    codes: [
      { value: "20", label: "20 - 혼합" },
      { value: "26", label: "26 - 교반" },
      { value: "27", label: "27 - 유화" },
      { value: "28", label: "28 - 균질화(호모게나이징)" },
    ],
  },
  {
    category: "추출/농축",
    codes: [
      { value: "25", label: "25 - 추출" },
      { value: "29", label: "29 - 열수추출" },
      { value: "30", label: "30 - 농축" },
      { value: "31", label: "31 - 감압농축" },
      { value: "33", label: "33 - 초임계추출" },
      { value: "34", label: "34 - 용매추출" },
    ],
  },
  {
    category: "분쇄/절단",
    codes: [
      { value: "32", label: "32 - 분쇄" },
      { value: "36", label: "36 - 미분쇄" },
      { value: "37", label: "37 - 절단" },
      { value: "38", label: "38 - 슬라이스" },
      { value: "39", label: "39 - 다이싱(깍둑썰기)" },
    ],
  },
  {
    category: "증류",
    codes: [
      { value: "35", label: "35 - 증류" },
      { value: "41", label: "41 - 감압증류" },
      { value: "42", label: "42 - 분자증류" },
    ],
  },
  {
    category: "성형/포장",
    codes: [
      { value: "40", label: "40 - 성형" },
      { value: "43", label: "43 - 압출성형" },
      { value: "44", label: "44 - 사출성형" },
      { value: "45", label: "45 - 충전" },
      { value: "46", label: "46 - 밀봉" },
      { value: "47", label: "47 - 진공포장" },
      { value: "48", label: "48 - 가스치환포장(MAP)" },
      { value: "49", label: "49 - 레토르트" },
    ],
  },
  {
    category: "건조",
    codes: [
      { value: "50", label: "50 - 열풍건조" },
      { value: "51", label: "51 - 분무건조(스프레이드라이)" },
      { value: "52", label: "52 - 드럼건조" },
      { value: "53", label: "53 - 천일건조" },
      { value: "54", label: "54 - 감압건조" },
      { value: "55", label: "55 - 적외선건조" },
    ],
  },
  {
    category: "코팅/캡슐",
    codes: [
      { value: "60", label: "60 - 코팅" },
      { value: "61", label: "61 - 당의(슈가코팅)" },
      { value: "62", label: "62 - 캡슐화" },
      { value: "63", label: "63 - 마이크로캡슐화" },
    ],
  },
  {
    category: "탈색/탈취/정제",
    codes: [
      { value: "70", label: "70 - 탈색" },
      { value: "71", label: "71 - 탈취" },
      { value: "72", label: "72 - 탈검(디거밍)" },
      { value: "73", label: "73 - 정제" },
      { value: "74", label: "74 - 활성탄처리" },
      { value: "75", label: "75 - 이온교환" },
    ],
  },
  {
    category: "세척/수처리",
    codes: [
      { value: "80", label: "80 - 세척" },
      { value: "81", label: "81 - 수세" },
      { value: "82", label: "82 - 알칼리세척" },
      { value: "83", label: "83 - 산세척" },
      { value: "84", label: "84 - 오존수처리" },
    ],
  },
  {
    category: "조리",
    codes: [
      { value: "90", label: "90 - 취반(밥짓기)" },
      { value: "91", label: "91 - 튀김" },
      { value: "92", label: "92 - 증자(찜)" },
      { value: "93", label: "93 - 팽화(퍼핑)" },
      { value: "94", label: "94 - 압착" },
      { value: "95", label: "95 - 착즙" },
    ],
  },
  {
    category: "특수공정",
    codes: [
      { value: "A01", label: "A01 - 방사선조사" },
      { value: "A02", label: "A02 - 자외선조사(UV)" },
      { value: "A03", label: "A03 - 고압처리(HPP)" },
      { value: "A04", label: "A04 - 전기분해" },
      { value: "A05", label: "A05 - 오존처리" },
      { value: "A06", label: "A06 - 초음파처리" },
      { value: "A07", label: "A07 - 마이크로웨이브" },
      { value: "A08", label: "A08 - 플라즈마처리" },
    ],
  },
  {
    category: "효소/생물",
    codes: [
      { value: "B01", label: "B01 - 효소분해" },
      { value: "B02", label: "B02 - 효소처리" },
      { value: "B03", label: "B03 - 단백질분해(가수분해)" },
      { value: "B04", label: "B04 - 전분분해" },
      { value: "B05", label: "B05 - 지방분해" },
    ],
  },
  {
    category: "유지가공",
    codes: [
      { value: "C01", label: "C01 - 압착추출(냉압착)" },
      { value: "C02", label: "C02 - 용매추출(유지)" },
      { value: "C03", label: "C03 - 수소첨가(경화)" },
      { value: "C04", label: "C04 - 에스테르교환" },
      { value: "C05", label: "C05 - 탈산(중화)" },
      { value: "C06", label: "C06 - 윈터링(동절화)" },
    ],
  },
  {
    category: "유제품",
    codes: [
      { value: "D01", label: "D01 - 커드형성" },
      { value: "D02", label: "D02 - 유청분리" },
      { value: "D03", label: "D03 - 치즈숙성" },
      { value: "D04", label: "D04 - 크림분리" },
      { value: "D05", label: "D05 - 버터처닝" },
    ],
  },
  {
    category: "제과/제빵",
    codes: [
      { value: "E01", label: "E01 - 반죽(믹싱)" },
      { value: "E02", label: "E02 - 발효(도우)" },
      { value: "E03", label: "E03 - 오븐베이킹" },
      { value: "E04", label: "E04 - 프루핑(2차발효)" },
      { value: "E05", label: "E05 - 라미네이팅(접기)" },
      { value: "E06", label: "E06 - 글레이징" },
    ],
  },
  {
    category: "음료",
    codes: [
      { value: "F01", label: "F01 - 탄산주입" },
      { value: "F02", label: "F02 - 당도조정(블렌딩)" },
      { value: "F03", label: "F03 - 탈기" },
      { value: "F04", label: "F04 - 무균충전" },
    ],
  },
  {
    category: "수산물",
    codes: [
      { value: "G01", label: "G01 - 필레팅" },
      { value: "G02", label: "G02 - 염장" },
      { value: "G03", label: "G03 - 자숙(보일링)" },
      { value: "G04", label: "G04 - 건조(수산물)" },
    ],
  },
  {
    category: "축산물",
    codes: [
      { value: "H01", label: "H01 - 도축" },
      { value: "H02", label: "H02 - 정형(트리밍)" },
      { value: "H03", label: "H03 - 염지(큐어링)" },
      { value: "H04", label: "H04 - 텀블링" },
      { value: "H05", label: "H05 - 케이싱충전" },
    ],
  },
  {
    category: "기타",
    codes: [
      { value: "J01", label: "J01 - 선별(소팅)" },
      { value: "J02", label: "J02 - 등급분류(그레이딩)" },
      { value: "J03", label: "J03 - 탈피(필링)" },
      { value: "J04", label: "J04 - 탈곡" },
      { value: "J05", label: "J05 - 도정" },
      { value: "J06", label: "J06 - 제분" },
      { value: "J07", label: "J07 - 체질(시빙)" },
      { value: "J08", label: "J08 - 배전(원두볶음)" },
      { value: "J09", label: "J09 - 템퍼링(초콜릿)" },
      { value: "J10", label: "J10 - 결정화" },
      { value: "J11", label: "J11 - 으깨기" },
      { value: "J12", label: "J12 - 해동" },
      { value: "J13", label: "J13 - 침지" },
      { value: "J14", label: "J14 - 탈수" },
      { value: "J15", label: "J15 - 원료투입" },
    ],
  },
];

/** Flat list of all codes for simple lookups */
export const ALL_PROCESS_CODES: ProcessCode[] = PROCESS_CODE_GROUPS.flatMap(
  (g) => g.codes
);

/** Quick lookup: code → label */
export function getProcessCodeLabel(code: string): string {
  const found = ALL_PROCESS_CODES.find((c) => c.value === code);
  return found ? found.label : code;
}
