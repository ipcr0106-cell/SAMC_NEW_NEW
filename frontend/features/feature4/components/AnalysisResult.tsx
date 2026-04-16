/**
 * 기능4: 전반 판정 결과 배지 컴포넌트
 */

import type { Feature4Result } from "@/types/pipeline";
import { OVERALL_LABEL, OVERALL_COLOR } from "../constants";

interface AnalysisResultProps {
  overall: Feature4Result["overall"];
}

export default function AnalysisResult({ overall }: AnalysisResultProps) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-gray-500">판정 결과:</span>
      <span className={`text-base font-bold ${OVERALL_COLOR[overall]}`}>
        {OVERALL_LABEL[overall]}
      </span>
    </div>
  );
}
