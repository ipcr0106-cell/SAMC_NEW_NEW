"use client";

/**
 * HITL-1: 에스컬레이션 인지 체크리스트 (Wave 3 Day 0 스켈레톤).
 *
 * Step A/B/C/D 가 생성한 escalations[] (API 장애, 키워드 누락, 단위 변환 실패,
 * 동명이인 안전측 채택 등) 을 담당자가 전수 인지해야 HITL-2 진행 가능.
 *
 * 본 파일의 props 인터페이스는 Wave 3 Day 0 에 동결.
 * W3-FE 트랙이 본체를 구현하되 이름·타입 유지.
 *
 * 참조: 계획/f1 재설계 계획/05_HITL_플로우_설계.md §4
 */

import type { ReactElement } from "react";

export interface EscalationItem {
  /** 사유 코드 (예: "step_a_api_error:대두:DATA_GO_KR_TIMEOUT") */
  code: string;
  /** 사용자에게 보여줄 한글 메시지 */
  message: string;
  severity: "info" | "warning" | "error";
}

export interface EscalationAckListProps {
  caseId: string;
  items: readonly EscalationItem[];
  /** 체크된 사유 코드 목록. 모두 체크되면 HITL-2 진행 가능. */
  onChange: (acknowledgedCodes: readonly string[]) => void;
  disabled?: boolean;
}

export default function EscalationAckList(
  _props: EscalationAckListProps,
): ReactElement | null {
  // W3-FE 본체 구현: severity 별 아이콘 + 체크박스 리스트 + "전체 확인" 단축
  return null;
}
