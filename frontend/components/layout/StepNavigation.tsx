"use client";

import { useRouter, useParams, usePathname } from "next/navigation";
import {
  FileText,
  Search,
  ListChecks,
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
  { key: "F1", label: "수입판정", icon: <Search size={15} />, route: "f1" },
  { key: "F2", label: "유형분류", icon: <ListChecks size={15} />, route: "f2" },
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
    <div className="bg-white rounded-2xl border border-slate-200/60 px-6 py-4 shadow-sm">
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
                  className={`flex items-center justify-center w-9 h-9 rounded-full transition-all duration-200 ${
                    isActive
                      ? "bg-blue-600 text-white shadow-md shadow-blue-600/30 ring-4 ring-blue-100"
                      : isCompleted
                      ? "bg-blue-600 text-white"
                      : "bg-slate-100 text-slate-400"
                  } ${
                    isClickable && !isActive
                      ? "group-hover:ring-4 group-hover:ring-blue-50 group-hover:scale-105"
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
                  className={`text-[11px] font-semibold whitespace-nowrap transition-colors ${
                    isActive
                      ? "text-blue-600"
                      : isCompleted
                      ? "text-blue-500"
                      : "text-slate-400"
                  } ${isClickable ? "group-hover:text-blue-600" : ""}`}
                >
                  {step.label}
                </span>
              </button>

              {/* 커넥터 라인 */}
              {!isLast && (
                <div className="flex-1 mx-3 mt-[-18px]">
                  <div
                    className={`h-[2px] rounded-full transition-colors duration-300 ${
                      isCompleted ? "bg-blue-400" : "bg-slate-100"
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
