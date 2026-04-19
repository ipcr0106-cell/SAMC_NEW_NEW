"use client";

/**
 * HITL-0: F0 파싱 결과 편집·승인 패널 (Wave 3 Day 0 스켈레톤).
 *
 * 본 파일의 `F0ApprovalPanelProps` 인터페이스는 Wave 3 Day 0 에 동결.
 * W3-FE 트랙이 본체를 구현하되 props 이름·타입 유지.
 *
 * 참조: 계획/f1 재설계 계획/05_HITL_플로우_설계.md §3
 */

import type { ReactElement } from "react";

export interface F0ApprovalPanelProps {
  caseId: string;
  /** F0 파싱 결과 (basic_info + ingredients + process_codes) */
  parsedResult: Record<string, unknown>;
  /** 편집 저장 (edit_reason 필수). 저장만, 승인 별개. */
  onEdit: (final: Record<string, unknown>, reason: string) => Promise<void>;
  /** HITL-0 승인 (signature 선택). 성공 시 status=approved */
  onApprove: (signature?: string) => Promise<void>;
  /** 서버에서 감지한 불일치 경고 (doc_type 키워드 부족 / 제품명 상이 등) */
  warnings?: readonly string[];
  /** 이미 승인된 상태인지 */
  isApproved?: boolean;
}

export default function F0ApprovalPanel(
  _props: F0ApprovalPanelProps,
): ReactElement | null {
  // W3-FE 트랙이 본체 구현 (BasicInfoEditor + IngredientEditor + 경고 배너)
  return null;
}
