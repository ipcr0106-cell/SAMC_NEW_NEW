/**
 * 파이프라인 각 기능의 결과 타입 정의
 * ──────────────────────────────────────
 * 이 파일은 팀원 간 데이터 인터페이스 약속입니다.
 * 수정 시 반드시 전원 합의 후 진행하세요.
 *
 * 담당:
 *   기능1 결과 타입 → 병찬이 완성 후 채워줌
 *   기능2 결과 타입 → 아람이 완성 후 채워줌
 *   기능3 결과 타입 → 기능3 담당자가 완성 후 채워줌
 *   기능4 결과 타입 → 본인(수출국표시사항) 작성
 *   기능5 결과 타입 → 세연이 작성
 */

// ──────────────────────────────────────────────────
// 공통
// ──────────────────────────────────────────────────

export type FeatureStatus =
  | "pending"        // 아직 시작 안 됨
  | "running"        // AI 처리 중
  | "waiting_review" // 담당자 확인 대기
  | "completed"      // 확인 완료
  | "error";         // 오류

export interface FeatureStep<T> {
  feature_num: number;
  feature_name: string;
  status: FeatureStatus;
  ai_result: T | null;       // AI 원본 출력
  final_result: T | null;    // 담당자 확인/수정 후 최종값
  edit_reason?: string;      // 수정 사유
  updated_at: string;
}

// ──────────────────────────────────────────────────
// 기능1: 수입 가능 여부 판정 (담당: 병찬)
// ──────────────────────────────────────────────────

export interface Ingredient {
  name: string;           // 원재료명 (라벨에 표기된 이름)
  percentage?: number;    // 배합비율 (%)
  status: "allowed" | "not_found" | "synthetic_flavor_warning";
  law_ref?: string;       // 허용 근거 법령
  message?: string;       // 경고/안내 메시지
}

export interface Feature1Result {
  ingredients: Ingredient[];          // 원재료 전체 목록
  verdict: "수입가능" | "수입불가";
  import_possible: boolean;
  fail_reasons: string[];             // 수입불가 이유 목록
  standards_check: StandardCheck[];  // 기준규격 수치 비교 결과
}

export interface StandardCheck {
  ingredient_name: string;
  actual_value: number;
  unit: string;
  threshold_value: number | null;
  status: "pass" | "fail" | "no_threshold";
  condition?: string;   // 예: "가열제품에 한함"
  law_ref?: string;
}

// ──────────────────────────────────────────────────
// 기능2: 식품유형 분류 (담당: 아람)
// ──────────────────────────────────────────────────

export interface Feature2Result {
  food_type: string;        // 예: "증류주"
  sub_type?: string;        // 예: "일반증류주"
  is_alcohol: boolean;
  law_ref: string;          // 예: "주세법 시행령 제3조"
  reasoning: string;        // 분류 근거 설명
  confidence: "high" | "medium" | "low";
}

// ──────────────────────────────────────────────────
// 기능3: 수입 필요서류 안내 (담당: 미정)
// ──────────────────────────────────────────────────

export interface RequiredDocument {
  doc_name: string;
  doc_description?: string;
  is_mandatory: boolean;
  condition?: string;   // 예: "OEM", "친환경인증"
  law_source?: string;
}

export interface Feature3Result {
  food_type: string;
  documents: RequiredDocument[];
  total_count: number;
}

// ──────────────────────────────────────────────────
// 기능4: 수출국표시사항 검토 (담당: 본인)
// ──────────────────────────────────────────────────

export interface LabelIssue {
  text: string;           // 문제 문구 원문
  location?: string;      // 라벨 상 위치 설명
  reason: string;         // 삭제/수정 이유
  law_ref: string;        // 근거 법령
  severity: "must_fix" | "review_needed";
}

export interface ImageIssue {
  description: string;    // 이미지 요소 설명
  location?: string;      // 라벨 상 위치
  violation_type: string; // ①~㉖ 위반 유형
  law_ref: string;        // 근거 법령
  reasoning: string;      // 위반 판단 근거 (사용자에게 보이는 설명)
  severity: "must_fix" | "review_needed";
  recommendation?: string; // 수정 권고
  // confirmed: 확정 위반 유형 분석 결과
  // suggested: 법령 개정으로 추가된 낮은 신뢰도 항목 — AI 불확실, 사용자 직접 확인 권고
  review_level?: "confirmed" | "suggested";
}

export interface ValidationConflict {
  law_refs: string[];
  description: string;
  reasoning: string;
  recommendation: string;
}

export interface ValidationDependency {
  selected_law_ref: string;
  required_law_ref: string;
  description: string;
  reasoning: string;
}

export interface ValidationResult {
  is_valid: boolean;
  conflicts: ValidationConflict[];
  dependencies: ValidationDependency[];
  applied_principles?: string;
  summary: string;
}

export interface CrossCheckItem {
  field: "product_name" | "ingredients" | "content_volume" | "origin" | "manufacturer";
  label_value: string;    // 라벨에 표기된 값
  doc_value: string;      // 제출 서류의 값
  match: boolean;
  note?: string;
}

export interface Feature4Result {
  overall: "pass" | "fail" | "review_needed";
  issues: LabelIssue[];
  image_issues?: ImageIssue[];
  cross_check: CrossCheckItem[];
  translation_note?: string;  // 다국어 번역 적용 시 표시
  label_image_url?: string;   // Supabase Storage에 저장된 라벨 이미지 경로
}

// ──────────────────────────────────────────────────
// 기능5: 한글표시사항 검토 및 시안 (담당: 세연)
// ──────────────────────────────────────────────────

export interface AllergyWarning {
  ingredient: string;
  status: "confirmed" | "needs_confirmation";
  reason?: string;
}

export interface Feature5Result {
  label_draft: string;              // 한글 라벨 시안 전문
  allergy_warnings: AllergyWarning[];
  gmo_notice?: string;
  law_refs: string[];
  uncertain_items: string[];        // "⚠️ 확인 필요" 항목
}
