"use client";

import { useRouter, useParams } from "next/navigation";
import {
  FileText,
  Search,
  ClipboardCheck,
  Globe,
  FileCheck,
  Check,
} from "lucide-react";
import { ReactNode } from "react";

interface Step {
  key: string;
  label: string;
  icon: ReactNode;
  route: string; // relative path segment
}

const steps: Step[] = [
  { key: "upload", label: "서류 업로드", icon: <FileText size={15} />, route: "upload" },
  { key: "F1", label: "수입 판정", icon: <Search size={15} />, route: "f1" },
  { key: "F2", label: "식품유형 분류", icon: <ClipboardCheck size={15} />, route: "f2" },
  { key: "F3", label: "필요서류", icon: <ClipboardCheck size={15} />, route: "f3" },
  { key: "F4", label: "라벨검토", icon: <Globe size={15} />, route: "f4" },
  { key: "F5", label: "한글시안", icon: <FileCheck size={15} />, route: "f5" },
];

interface StepNavigationProps {
  currentStep: string;
  /** Steps that are completed (data available). Users can jump to any completed step or the next uncompleted step. */
  completedSteps?: string[];
}

export default function StepNavigation({
  currentStep,
  completedSteps = [],
}: StepNavigationProps) {
  const router = useRouter();
  const params = useParams();
  const caseId = params?.id as string;
  const currentIndex = steps.findIndex((s) => s.key === currentStep);

  const handleStepClick = (step: Step, idx: number) => {
    if (step.key === currentStep) return; // 현재 단계 클릭 무시
    // 모든 단계로 자유롭게 이동 가능 (1→4 점프 허용)
    router.push(`/cases/${caseId}/${step.route}`);
  };

  return (
    <div className="ds-step-nav px-6 py-4">
      {/* 스텝 바 */}
      <div className="flex items-center">
        {steps.map((step, idx) => {
          const isActive = idx === currentIndex;
          const isCompleted = completedSteps.includes(step.key) || idx < currentIndex;
          const isLast = idx === steps.length - 1;
          const isClickable = step.key !== currentStep;

          return (
            <div key={step.key} className="flex items-center flex-1 last:flex-none">
              {/* 원형 아이콘 + 라벨 */}
              <button
                onClick={() => handleStepClick(step, idx)}
                disabled={!isClickable}
                className={`flex flex-col items-center gap-1.5 min-w-0 group transition-all ${
                  isClickable ? "cursor-pointer" : "cursor-default"
                }`}
              >
                <div
                  className={`flex items-center justify-center ds-step-node ${
                    isActive
                      ? "ds-step-node-active"
                      : isCompleted
                      ? "ds-step-node-completed"
                      : ""
                  } ${
                    isClickable && !isActive
                      ? "group-hover:scale-105"
                      : ""
                  }`}
                >
                  {isCompleted && !isActive ? (
                    <Check size={15} strokeWidth={2.5} />
                  ) : (
                    step.icon
                  )}
                </div>
                <span
                  className={`ds-step-label whitespace-nowrap transition-colors ${
                    isActive
                      ? "ds-step-label-active"
                      : isCompleted
                      ? "ds-step-label-completed"
                      : ""
                  } ${isClickable ? "group-hover:opacity-90" : ""}`}
                >
                  {step.label}
                </span>
              </button>

              {/* 커넥터 라인 */}
              {!isLast && (
                <div className="flex-1 mx-3 mt-[-18px]">
                  <div
                    className={`ds-step-line transition-colors duration-300 ${
                      isCompleted ? "ds-step-line-completed" : ""
                    }`}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
