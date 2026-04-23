/**
 * 일본 도·현 목록 및 F3 전달용 코드 변환 유틸.
 *
 * group "13" → 방사성물질 검사성적서(요오드/세슘) + 일본 정부증명서 필요
 * group "34" → 비오염 생산지 증명서 필요
 *
 * F3 매처가 product_keywords 안에서 아래 코드를 찾아 서류 분기:
 *   · 13개 도·현: 해당 도·현명 그대로 (예: "후쿠시마")
 *   · 34개 도·부·현: 리터럴 "일본34개도부현"
 */

export interface JapanPrefecture {
  name: string;   // F3 전달 키 (13그룹은 이 값이 곧 코드)
  label: string;  // UI 표시용 (예: "후쿠시마현", "도쿄도")
  group: "13" | "34";
}

export const JAPAN_PREFECTURES: JapanPrefecture[] = [
  // ── 13개 도·현 (방사성물질 검사성적서 그룹) ─────────────────
  { name: "후쿠시마",  label: "후쿠시마현",  group: "13" },
  { name: "이바라키",  label: "이바라키현",  group: "13" },
  { name: "토치키",   label: "토치키현",   group: "13" },
  { name: "군마",     label: "군마현",     group: "13" },
  { name: "사이타마", label: "사이타마현", group: "13" },
  { name: "치바",     label: "치바현",     group: "13" },
  { name: "미야기",   label: "미야기현",   group: "13" },
  { name: "가나가와", label: "가나가와현", group: "13" },
  { name: "도쿄",     label: "도쿄도",     group: "13" },
  { name: "나가노",   label: "나가노현",   group: "13" },
  { name: "야마가타", label: "야마가타현", group: "13" },
  { name: "니이가타", label: "니이가타현", group: "13" },
  { name: "시즈오카", label: "시즈오카현", group: "13" },
  // ── 34개 도·부·현 (비오염 생산지 증명서 그룹) ──────────────
  { name: "홋카이도",  label: "홋카이도",   group: "34" },
  { name: "아오모리",  label: "아오모리현", group: "34" },
  { name: "이와테",   label: "이와테현",   group: "34" },
  { name: "아키타",   label: "아키타현",   group: "34" },
  { name: "후쿠이",   label: "후쿠이현",   group: "34" },
  { name: "이시카와", label: "이시카와현", group: "34" },
  { name: "토야마",   label: "토야마현",   group: "34" },
  { name: "기후",     label: "기후현",     group: "34" },
  { name: "아이치",   label: "아이치현",   group: "34" },
  { name: "미에",     label: "미에현",     group: "34" },
  { name: "시가",     label: "시가현",     group: "34" },
  { name: "교토",     label: "교토부",     group: "34" },
  { name: "오사카",   label: "오사카부",   group: "34" },
  { name: "효고",     label: "효고현",     group: "34" },
  { name: "나라",     label: "나라현",     group: "34" },
  { name: "와카야마", label: "와카야마현", group: "34" },
  { name: "돗토리",   label: "돗토리현",   group: "34" },
  { name: "시마네",   label: "시마네현",   group: "34" },
  { name: "오카야마", label: "오카야마현", group: "34" },
  { name: "히로시마", label: "히로시마현", group: "34" },
  { name: "야마구치", label: "야마구치현", group: "34" },
  { name: "도쿠시마", label: "도쿠시마현", group: "34" },
  { name: "가가와",   label: "가가와현",   group: "34" },
  { name: "에히메",   label: "에히메현",   group: "34" },
  { name: "고치",     label: "고치현",     group: "34" },
  { name: "후쿠오카", label: "후쿠오카현", group: "34" },
  { name: "사가",     label: "사가현",     group: "34" },
  { name: "나가사키", label: "나가사키현", group: "34" },
  { name: "구마모토", label: "구마모토현", group: "34" },
  { name: "오이타",   label: "오이타현",   group: "34" },
  { name: "미야자키", label: "미야자키현", group: "34" },
  { name: "가고시마", label: "가고시마현", group: "34" },
  { name: "오키나와", label: "오키나와현", group: "34" },
];

/** 13개 도·현 name 셋 (빠른 조회용) */
const GROUP_13_NAMES = new Set(
  JAPAN_PREFECTURES.filter((p) => p.group === "13").map((p) => p.name)
);

/**
 * 도·현 객체를 F3 product_keywords 전달용 코드 문자열로 변환.
 *   · 13개 도·현 → 해당 도·현명 (예: "후쿠시마")
 *   · 34개 도·부·현 → "일본34개도부현" (DB 등재 리터럴)
 */
export function prefectureToCode(pref: Pick<JapanPrefecture, "name" | "group">): string {
  return pref.group === "13" ? pref.name : "일본34개도부현";
}

/**
 * F3 코드로부터 UI 선택 상태를 역산.
 *   · 13개 도·현명 → 해당 도·현 객체
 *   · "일본34개도부현" → null (34개 중 어느 도·현인지 특정 불가)
 *   · 그 외 / 빈 문자열 → null
 */
export function codeToSelectedName(code: string): string | null {
  if (!code) return null;
  if (GROUP_13_NAMES.has(code)) return code;
  return null; // "일본34개도부현"이거나 알 수 없는 값
}
