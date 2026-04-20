"use client";

import { useRouter, useParams, useSearchParams } from "next/navigation";
import { ArrowRight, Save, ChevronLeft } from "lucide-react";
import StepNavigation from "@/components/layout/StepNavigation";
import CaseSummaryPanel from "@/components/layout/CaseSummaryPanel";
import Button from "@/components/ui/Button";
import RequiredDocsPage from "@/features/feature3/RequiredDocsPage";

export default function F3RequiredDocsPage() {
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();
  const caseId = params?.id as string;
  const fromView = searchParams?.get("from") === "view";

  return (
    <div className="max-w-[1440px] mx-auto px-6 py-6 pb-28">
      <StepNavigation currentStep="F3" completedSteps={["upload", "F1"]} />

      <div className="mt-6 grid lg:grid-cols-3 gap-6">
        {/* 좌측: F3 필요서류 본문 (유빈 구현) */}
        <div className="lg:col-span-2">
          <RequiredDocsPage />
        </div>

        {/* 우측: 케이스 요약 */}
        <div className="space-y-4">
          <CaseSummaryPanel caseId={caseId} />
        </div>
      </div>

      {/* 하단 액션바 (f0 디자인 유지) */}
      <div className="fixed bottom-0 left-0 right-0 z-50">
        <div className="max-w-[1440px] mx-auto px-6">
          <div className="ds-actionbar-shell px-8 py-4 flex items-center justify-between">
            {fromView ? (
              <Button variant="secondary" size="md" icon={<ChevronLeft size={16} />}
                onClick={() => router.push(`/cases/${caseId}/view`)}>
                결과로 돌아가기
              </Button>
            ) : (
              <Button variant="secondary" size="md" onClick={() => router.push(`/cases/${caseId}/f1`)}>
                이전: 수입 · 유형 판정
              </Button>
            )}
            <div className="flex items-center gap-3">
              <Button variant="secondary" size="md" icon={<Save size={16} />}>
                임시 저장
              </Button>
              {fromView ? (
                <Button variant="primary" size="lg" icon={<ArrowRight size={18} />}
                  onClick={() => router.push(`/cases/${caseId}/view`)}>
                  수정 확정 → 결과 보기
                </Button>
              ) : (
                <Button variant="primary" size="lg" icon={<ArrowRight size={18} />}
                  onClick={() => router.push(`/cases/${caseId}/f4`)}>
                  F4 라벨검토로 이동
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );}
