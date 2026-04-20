/**
 * F3 법령 업데이트 API 클라이언트.
 * 백엔드 엔드포인트: /api/v1/admin/f3/*
 *
 * 인증:
 *   모든 요청에 X-Admin-Token 헤더 자동 첨부.
 *   로컬 개발: localStorage.setItem("f3_admin_token", "...") 으로 주입.
 *   프로덕션: 로그인 플로우에서 저장.
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/api\/v1$/, "") ||
  "http://localhost:8000";

function getAdminHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("f3_admin_token") || "";
  const user = localStorage.getItem("f3_admin_user") || "";
  const h: Record<string, string> = {};
  if (token) h["X-Admin-Token"] = token;
  if (user) h["X-Admin-User"] = user;
  return h;
}

// error_code → 사용자 친화 한국어 설명 (비개발자 검역관용)
const ERROR_CODE_MESSAGES: Record<string, string> = {
  UNAUTHORIZED:
    "관리자 권한이 필요합니다. 시스템 담당자에게 관리자 토큰을 요청하세요.",
  ADMIN_TOKEN_NOT_CONFIGURED:
    "서버에 관리자 토큰이 설정돼 있지 않습니다. 시스템 담당자에게 문의하세요.",
  FILE_TOO_LARGE:
    "업로드한 파일이 너무 큽니다. 50MB 이하의 파일만 가능합니다.",
  ZIP_BOMB_DETECTED:
    "파일 구조에 이상이 있습니다. 손상됐거나 안전하지 않은 파일일 수 있습니다.",
  UNSUPPORTED_LAW:
    "지원하지 않는 법령입니다. 지원 목록에서 다시 선택해주세요.",
  PARSE_FAILED:
    "파일을 읽지 못했습니다. 원본 법령 파일 (PDF / HWPX / Excel) 인지 확인해주세요.",
  APPLY_BLOCKED:
    "반영이 중단됐습니다. 파싱된 자료가 비어있거나 안전 규칙에 걸렸습니다. 파일을 다시 확인하세요.",
  APPLY_FAILED:
    "반영 중 오류가 발생했습니다. 자동 복구가 시도됐으며, 시스템 담당자에게 알려주세요.",
  ROLLBACK_BLOCKED:
    "이 버전으로 되돌릴 수 없습니다. 이미 롤백됐거나 저장된 자료가 손상됐을 수 있습니다.",
  ROLLBACK_FAILED:
    "롤백 중 오류가 발생했습니다. 시스템 담당자에게 알려주세요.",
  TARGET_REQUIRED:
    "적용 대상 (국가·식품유형·조건·원재료 키워드) 중 최소 1개는 반드시 입력해야 합니다.",
  EMPTY_FIELD:
    "필수 항목이 비어있습니다. 모든 필수 항목을 입력해주세요.",
  EMPTY_TABLES:
    "적용할 자료가 없습니다. 파일을 다시 업로드해주세요.",
  INVALID_SUBMISSION_TYPE:
    "제출/보관 유형 값이 잘못됐습니다. 'submit' 또는 'keep' 만 가능합니다.",
  INVALID_SUBMISSION_TIMING:
    "제출 시점 값이 잘못됐습니다. 'every' 또는 'first' 만 가능합니다.",
  HINT_TOO_SHORT:
    "원재료 키워드는 최소 2글자 이상이어야 합니다 (한 글자 매핑은 오탐 위험).",
  ADD_BLOCKED:
    "추가할 수 없습니다. 이미 존재하거나 규칙에 맞지 않는 값입니다.",
  ADD_FAILED:
    "추가 중 오류가 발생했습니다. 잠시 후 다시 시도하세요.",
  REMOVE_BLOCKED:
    "삭제할 수 없습니다. 해당 항목을 찾지 못했습니다.",
  REMOVE_FAILED:
    "삭제 중 오류가 발생했습니다. 잠시 후 다시 시도하세요.",
  RULE_ADD_BLOCKED:
    "규칙을 추가할 수 없습니다. 중복 ID 이거나 필수 값이 누락됐을 수 있습니다.",
  RULE_ADD_FAILED:
    "규칙 추가 중 오류가 발생했습니다. 시스템 담당자에게 알려주세요.",
  PARSER_NOT_IMPLEMENTED:
    "해당 법령 전용 파서가 아직 준비되지 않았습니다. 관리자 업데이트가 필요합니다.",
  OPENPYXL_MISSING:
    "서버에 엑셀 생성 라이브러리가 없습니다. 시스템 담당자에게 알려주세요.",
};

async function parseError(res: Response): Promise<string> {
  try {
    const err = await res.json();

    // detail.error 코드 기반 번역
    const errorCode =
      (typeof err.detail === "object" && err.detail?.error) || "";
    if (errorCode && ERROR_CODE_MESSAGES[errorCode]) {
      // 추가 컨텍스트가 있으면 덧붙임
      const extra = err.detail?.message;
      if (extra && extra !== ERROR_CODE_MESSAGES[errorCode]) {
        return `${ERROR_CODE_MESSAGES[errorCode]}\n\n[상세] ${extra}`;
      }
      return ERROR_CODE_MESSAGES[errorCode];
    }

    // fallback
    if (typeof err.detail === "string") return err.detail;
    if (err.detail?.message) return err.detail.message;
    if (err.detail?.error) return `${err.detail.error} (자세한 사항은 시스템 담당자 문의)`;

    // HTTP status 기반
    if (res.status === 401) return ERROR_CODE_MESSAGES.UNAUTHORIZED;
    if (res.status === 413) return ERROR_CODE_MESSAGES.FILE_TOO_LARGE;
    if (res.status === 500) return "서버 내부 오류입니다. 잠시 후 다시 시도하거나 시스템 담당자에게 알려주세요.";
    if (res.status === 503) return "서비스가 일시적으로 사용할 수 없습니다. 잠시 후 재시도하세요.";

    return res.statusText || `요청 실패 (HTTP ${res.status})`;
  } catch {
    return res.statusText || `요청 실패 (HTTP ${res.status})`;
  }
}

// ── 타입 ─────────────────────────────────────

export interface DiffSummary {
  added: number;
  modified: number;
  deleted: number;
  unchanged: number;
  added_keys: (string | number)[];
  modified_keys: (string | number)[];
  deleted_keys: (string | number)[];
}

export interface TableDiff {
  new_rows: Record<string, unknown>[];
  old_rows: Record<string, unknown>[];
  pk_column: string;
  scope_filter: Record<string, unknown> | null;
  diff: DiffSummary;
}

export interface PreviewResponse {
  law_name: string;
  source_filename: string;
  feature_label: string;
  affected_tables: string[];
  tables: Record<string, TableDiff>;
  scope_filters: Record<string, Record<string, unknown> | null>;
  pinecone_chunks: Record<string, unknown>[];
  warnings: string[];
  pinecone_touched: boolean;
}

export interface ApplyResponse {
  status: "applied" | "duplicate_request";
  version: number;
  history_id?: string;
  created_at?: string;
  affected_tables?: string[];
  rows_inserted_by_table?: Record<string, number>;
  diff_summary?: Record<string, unknown>;
  pinecone?: {
    touched: boolean;
    upserted?: number;
    deleted?: string;
    error?: string;
    message?: string;
  };
  // duplicate_request 응답
  message?: string;
}

export interface RollbackResponse {
  status: "rolled_back" | "needs_cascade";
  version: number;
  law_name?: string;
  affected_tables?: string[];
  restored_rows_by_table?: Record<string, number>;
  pinecone_touched?: boolean;
  warning?: string | null;
  // needs_cascade 응답
  later_versions?: number[];
  cascade_versions?: number[];
  message?: string;
}

export interface HistoryItem {
  version: number;
  law_name: string;
  feature_label: string;
  diff_summary: { added: number; modified: number; deleted: number };
  source_filename: string | null;
  scope_filter: Record<string, unknown> | null;
  created_at: string;
  created_by: string | null;
  is_rolled_back: boolean;
  rolled_back_at: string | null;
  rolled_back_by: string | null;
  pinecone_touched: boolean;
}

// ── API 함수 ─────────────────────────────────

export async function previewUpdate(
  file: File,
  law_name: string,
): Promise<PreviewResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("law_name", law_name);

  const res = await fetch(`${API_BASE}/api/v1/admin/f3/preview`, {
    method: "POST",
    headers: getAdminHeaders(),
    body: formData,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function applyUpdate(
  params: {
    law_name: string;
    source_filename?: string;
    tables: Record<
      string,
      {
        new_rows: Record<string, unknown>[];
        pk_column: string;
        scope_filter?: Record<string, unknown> | null;
        force_empty?: boolean;
      }
    >;
    pinecone_chunks?: Record<string, unknown>[];
    pinecone_touched?: boolean;
  },
  idempotencyKey?: string,
): Promise<ApplyResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...getAdminHeaders(),
  };
  if (idempotencyKey) {
    headers["Idempotency-Key"] = idempotencyKey;
  }

  const res = await fetch(`${API_BASE}/api/v1/admin/f3/apply`, {
    method: "POST",
    headers,
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function rollbackUpdate(
  version: number,
  cascade = false,
): Promise<RollbackResponse> {
  const res = await fetch(`${API_BASE}/api/v1/admin/f3/rollback`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAdminHeaders() },
    body: JSON.stringify({ version, cascade }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

// ── 건강 상태 (인증 불필요) ─────────────────

export interface HealthCheck {
  status: "ok" | "warning" | "error" | "unknown";
  label: string;
  detail: string;
  latency_ms?: number;
}

export interface HealthResponse {
  overall_status: "ok" | "warning" | "error";
  checks: Record<string, HealthCheck>;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/api/v1/admin/f3/health`);
  if (!res.ok) throw new Error(`상태 확인 실패 (HTTP ${res.status})`);
  return res.json();
}


// ── 법령 기준일 (인증 불필요) ──────────────

export interface LastUpdateInfo {
  per_law: Record<string, string>;
  overall_last_at: string | null;
  error?: string;
}

export async function fetchLastUpdate(): Promise<LastUpdateInfo> {
  const res = await fetch(`${API_BASE}/api/v1/admin/f3/last-update`);
  if (!res.ok) return { per_law: {}, overall_last_at: null, error: "fetch_failed" };
  return res.json();
}


// ── 경고 키워드 관리 ────────────────────────

export async function fetchWarningKeywords(): Promise<Record<string, string[]>> {
  const res = await fetch(`${API_BASE}/api/v1/admin/f3/warning-keywords`, {
    headers: getAdminHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  return data.rules ?? {};
}

export async function addWarningKeyword(
  rule_id: string, keyword: string, idempotencyKey?: string,
): Promise<{ rule_id: string; keyword: string; version: number }> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...getAdminHeaders(),
  };
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
  const res = await fetch(`${API_BASE}/api/v1/admin/f3/warning-keywords`, {
    method: "POST",
    headers,
    body: JSON.stringify({ rule_id, keyword }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function deleteWarningKeyword(
  rule_id: string, keyword: string,
): Promise<void> {
  const params = new URLSearchParams({ rule_id, keyword });
  const res = await fetch(
    `${API_BASE}/api/v1/admin/f3/warning-keywords?${params}`,
    { method: "DELETE", headers: getAdminHeaders() },
  );
  if (!res.ok) throw new Error(await parseError(res));
}


// ── 원재료 동의어 관리 ─────────────────────

export interface KeywordSynonym {
  id: number;
  hint_keyword: string;
  db_keyword: string;
  country_cond: string | null;
}

export async function fetchSynonyms(): Promise<KeywordSynonym[]> {
  const res = await fetch(`${API_BASE}/api/v1/admin/f3/synonyms`, {
    headers: getAdminHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  return data.synonyms || [];
}

export async function addSynonym(
  hint_keyword: string,
  db_keyword: string,
  country_cond?: string | null,
  idempotencyKey?: string,
): Promise<{ status: string; synonym_id: number; version: number }> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...getAdminHeaders(),
  };
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
  const res = await fetch(`${API_BASE}/api/v1/admin/f3/synonyms`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      hint_keyword,
      db_keyword,
      country_cond: country_cond || null,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function deleteSynonym(synonym_id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/admin/f3/synonyms/${synonym_id}`, {
    method: "DELETE",
    headers: getAdminHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
}


// ── 국가 그룹 관리 ─────────────────────────

export interface CountryGroupsResponse {
  groups: Record<string, string[]>;  // { group_name: [country_name, ...] }
}

export interface CountryGroupMemberResponse {
  status: string;
  version: number;
  history_id: string;
  group_name: string;
  country_name: string;
}

export async function fetchCountryGroups(): Promise<Record<string, string[]>> {
  const res = await fetch(`${API_BASE}/api/v1/admin/f3/country-groups`, {
    headers: getAdminHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const data: CountryGroupsResponse = await res.json();
  return data.groups;
}

export async function addCountryGroupMember(
  group_name: string,
  country_name: string,
  idempotencyKey?: string,
): Promise<CountryGroupMemberResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...getAdminHeaders(),
  };
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
  const res = await fetch(`${API_BASE}/api/v1/admin/f3/country-groups/members`, {
    method: "POST",
    headers,
    body: JSON.stringify({ group_name, country_name }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function removeCountryGroupMember(
  group_name: string,
  country_name: string,
): Promise<CountryGroupMemberResponse> {
  const params = new URLSearchParams({ group_name, country_name });
  const res = await fetch(
    `${API_BASE}/api/v1/admin/f3/country-groups/members?${params}`,
    { method: "DELETE", headers: getAdminHeaders() },
  );
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}


// ── 수동 서류 규칙 추가 ─────────────────────────

export interface ManualRuleInput {
  doc_name: string;
  doc_description: string;
  is_mandatory?: boolean;
  submission_type?: "submit" | "keep";
  submission_timing?: "every" | "first";
  law_source?: string;
  target_country?: string | null;
  food_type?: string | null;
  condition?: string | null;
  product_keywords?: string[] | null;
  effective_from?: string | null;
  effective_until?: string | null;
  notes?: string | null;
}

export interface ManualRuleResponse {
  status: "applied" | "duplicate_request";
  version: number;
  history_id: string;
  created_at: string;
  row_id: string;
  table_name: string;
}

export async function addManualRule(
  rule: ManualRuleInput,
  idempotencyKey?: string,
): Promise<ManualRuleResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...getAdminHeaders(),
  };
  if (idempotencyKey) {
    headers["Idempotency-Key"] = idempotencyKey;
  }
  const res = await fetch(`${API_BASE}/api/v1/admin/f3/rules`, {
    method: "POST",
    headers,
    body: JSON.stringify(rule),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchHistory(limit = 20): Promise<HistoryItem[]> {
  const res = await fetch(
    `${API_BASE}/api/v1/admin/f3/history?limit=${limit}`,
    { headers: getAdminHeaders() },
  );
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  return data.items || [];
}
