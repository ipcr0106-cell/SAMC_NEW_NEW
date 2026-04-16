/**
 * 건(Case) 관련 공통 타입
 * 수정 시 전원 합의 필수.
 */

export type CaseStatus = "processing" | "completed" | "on_hold" | "error";

export interface Case {
  id: string;
  product_name: string;
  importer_name: string;
  status: CaseStatus;
  current_feature: number | null;   // 현재 진행 중인 기능 번호 (1~5)
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface Document {
  id: string;
  case_id: string;
  doc_type: "ingredients" | "process" | "msds" | "material" | "other";
  file_name: string;
  storage_path: string;
  parsed_md?: string;
  is_verified: boolean;
  created_at: string;
}
