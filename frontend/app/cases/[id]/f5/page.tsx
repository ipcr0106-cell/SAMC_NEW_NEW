"use client";

import { useRouter, useParams } from "next/navigation";
import { ArrowRight, Save } from "lucide-react";
import StepNavigation from "@/components/layout/StepNavigation";
import CaseSummaryPanel from "@/components/layout/CaseSummaryPanel";
import Button from "@/components/ui/Button";
import LabelDraftPage from "@/features/feature5/LabelDraftPage";

export default function F5KoreanLabelPage() {
  const router = useRouter();
  const params = useParams();
  const caseId = params?.id as string;

  return (
    <div className="max-w-[1440px] mx-auto px-6 py-6 pb-28">
      <StepNavigation currentStep="F5" completedSteps={["upload", "F1", "F2", "F3", "F4"]} />

      <div className="mt-6 grid lg:grid-cols-3 gap-6">
        {/* 좌측: F5 한글표시사항 본문 (세연 구현 — 자체 진행 상태 UI 내장) */}
        <div className="lg:col-span-2">
          <LabelDraftPage />
        </div>

        {/* 우측: 케이스 요약 */}
        <div className="space-y-4">
          <CaseSummaryPanel caseId={caseId} />
        </div>
      </div>

      {/* 하단 액션바 (f0 디자인 유지) */}
      <div className="fixed bottom-0 left-0 right-0 z-50">
        <div className="max-w-[1440px] mx-auto px-6">
          <div className="bg-white/80 backdrop-blur-xl border-t border-slate-200/60 rounded-t-2xl shadow-lg shadow-slate-900/5 px-8 py-4 flex items-center justify-between">
            <Button variant="secondary" size="md" onClick={() => router.push(`/cases/${caseId}/f4`)}>
              이전: 라벨검토
            </Button>
            <div className="flex items-center gap-3">
              <Button variant="secondary" size="md" icon={<Save size={16} />}>
                임시 저장
              </Button>
              <Button
                variant="primary"
                size="lg"
                icon={<ArrowRight size={18} />}
                onClick={() => router.push(`/dashboard`)}
                className="shadow-lg shadow-blue-600/20"
              >
                대시보드로 이동
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
