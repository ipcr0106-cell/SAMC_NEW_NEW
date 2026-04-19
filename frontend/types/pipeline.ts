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

/**
 * F1 재설계(Wave 1 W1-B) 신규 원재료 타입 — 07번 §4 기준.
 * 기존 Ingredient 는 레거시 렌더 경로에서 그대로 유지.
 * 신규 F1 파이프라인은 이 타입을 사용한다.
 * optional 처리로 기존 pipeline_steps.ai_result 역호환 보장.
 */
export interface F1Ingredient {
  name: string;                                                          // 원재료명
  percentage?: number | null;                                            // 배합비율 (%)
  component_code?: string | null;                                        // 성분코드 CPNT_CD (신규)
  allow_verdict: "allowed" | "restricted" | "prohibited" | "unidentified"; // Step B 판정 (신규)
  restriction_condition?: string | null;                                 // 조건부 허용 조건 (신규)
  edible_parts?: string | null;                                          // 식용 부위 (신규)
  is_gmo?: boolean | null;                                               // GMO 여부 (신규)
  source_api?: string | null;                                            // 매칭 API id (신규)
  law_ref?: string | null;                                               // 허용 근거 법령 (기존 유지)
  message?: string | null;                                               // 경고/안내 메시지 (기존 유지)
}

export interface Feature1Result {
  ingredients: Ingredient[];          // 원재료 전체 목록
  verdict: "수입가능" | "수입불가";
  import_possible: boolean;
  fail_reasons: string[];             // 수입불가 이유 목록
  standards_check: StandardCheck[];  // 기준규격 수치 비교 결과
}

/**
 * StandardCheck — W1-B 필드 정비 (07번 §2-4).
 * 신규 필드는 optional 처리하여 기존 렌더 역호환 유지.
 */
export interface StandardCheck {
  ingredient_name: string;
  actual_value: number | string | null;                    // 문자열 값도 허용 (spec_raw 대응)
  unit: string;
  threshold_value: number | null;
  status: "pass" | "fail" | "review_needed" | "no_data" | "no_threshold"; // no_threshold 하위호환
  condition?: string;                                      // 예: "가열제품에 한함"
  law_ref?: string | null;
  // W1-B 신규 필드 (07번 §2-4)
  test_category?: string | null;                           // T_KOR_NM 값 ('함량', '성상' 등)
  spec_raw?: string | null;                                // SPEC_VAL 원본
  spec_summary?: string | null;                            // SPEC_VAL_SUMUP
  unit_original?: string | null;                           // 원본 단위
  unit_normalized?: string | null;                         // 정규화 단위
  is_dangerous?: boolean | null;                           // INJRY_YN 매핑
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
// 기능1 HITL 타입 (Wave 3 — backend/models/f1_hitl.py 1:1 매핑)
// F2~F5 영역 금지 — F1 HITL만 추가
// ──────────────────────────────────────────────────

/**
 * pipeline_steps.status 확장값 (migration 017, 05번 §6)
 * backend/models/f1_hitl.py PipelineStepStatus 와 동일.
 */
export type PipelineStepStatus =
  | "pending"
  | "running"
  | "completed"
  | "approved"         // HITL-0 승인 (F0 전용)
  | "waiting_review"
  | "needs_review"     // HITL-1 필요 (에스컬레이션 있음)
  | "confirmed"        // HITL-2 완료
  | "locked";          // 확정 후 잠김

/**
 * HITL-1: 미확인 원재료 담당자 판정 (IngredientDecision)
 * backend/models/f1_hitl.py IngredientDecision 1:1 매핑.
 */
export interface IngredientDecision {
  name: string;
  decision: "allow" | "deny" | "skip";
  alternative_name?: string | null;
  note?: string | null;
}

/**
 * HITL-1: 조건부 원재료 사용 조건 평가 결과 (ConditionalResolution)
 * backend/models/f1_hitl.py ConditionalResolution 1:1 매핑.
 */
export interface HITLConditionalResolution {
  ingredient_name: string;
  meets_condition: boolean;
  reasoning: string;
}

/**
 * HITL-1: 비수치 기준값 담당자 판정 (QualitativeResolution)
 * backend/models/f1_hitl.py QualitativeResolution 1:1 매핑.
 */
export interface QualitativeResolution {
  ingredient_name: string;
  test_category: string;
  resolution: "pass" | "fail" | "unknown";
  note?: string | null;
}

/**
 * HITL-1 decisions 요청 바디
 * POST /api/v1/cases/{case_id}/pipeline/feature/1/hitl1-decisions
 * backend/models/f1_hitl.py HITL1DecisionsRequest 1:1 매핑.
 */
export interface HITL1DecisionsRequest {
  ingredient_decisions: IngredientDecision[];
  conditional_resolutions: HITLConditionalResolution[];
  qualitative_resolutions: QualitativeResolution[];
  escalation_acknowledgements: string[];
  reviewer_id: string;
}

/**
 * HITL-2 confirm 요청 바디
 * POST /api/v1/cases/{case_id}/pipeline/feature/1/confirm
 * backend/models/f1_hitl.py HITL2ConfirmRequest 1:1 매핑.
 */
export interface HITL2ConfirmRequest {
  user_verdict: UserVerdict;
  final_reason: string;
  selected_citations: string[];
  signer_id: string;
  signed_at: string; // ISO 8601 문자열 (프론트 → 백엔드 datetime 직렬화)
}

/**
 * HITL-2 최종 판정 값
 * backend/models/f1_hitl.py UserVerdict 와 동일.
 */
export type UserVerdict = "수입가능" | "수입불가" | "보류";

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
