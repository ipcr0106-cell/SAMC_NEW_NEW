"use client";

/**
 * HITL-1: 조건부 원재료(restricted) 사용 조건 평가 패널 (Wave 3 Day 0 스켈레톤).
 *
 * 본 파일의 props 인터페이스는 Wave 3 Day 0 에 동결.
 * W3-FE 트랙이 본체를 구현하되 이름·타입 유지.
 *
 * 참조: 계획/f1 재설계 계획/05_HITL_플로우_설계.md §4
 */

import type { ReactElement } from "react";

export interface ConditionalIngredient {
  name: string;
  /** data.go.kr CHRTR_INFO_CONT 원문 (사용 조건 텍스트) */
  restrictionCondition: string;
  /** data.go.kr EDIBLE_USE_CONT (사용 가능 부위) */
  ediblePartHint?: string;
}

export interface ConditionalResolution {
  ingredientName: string;
  meetsCondition: boolean;
  reasoning: string;
}

export interface ConditionalResolutionPanelProps {
  caseId: string;
  ingredients: readonly ConditionalIngredient[];
  /** HITL-1 decisions 의 conditional_resolutions 에 병합될 결과 */
  onChange: (resolutions: readonly ConditionalResolution[]) => void;
  disabled?: boolean;
}

export default function ConditionalResolutionPanel(
  _props: ConditionalResolutionPanelProps,
): ReactElement | null {
  // W3-FE 본체 구현: 조건 텍스트 표시 + 부합/불충족 라디오 + 사유 텍스트필드
  return null;
}
