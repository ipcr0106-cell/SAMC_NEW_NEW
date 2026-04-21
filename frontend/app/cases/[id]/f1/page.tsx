"use client";

import { useRouter, useParams, useSearchParams } from "next/navigation";
import { ArrowRight, ChevronLeft } from "lucide-react";
import Button from "@/components/ui/Button";
import ImportCheckPage from "@/features/feature1/ImportCheckPage";

export default function F1ImportCheckPage() {
  const router = useRouter();
  const params = useParams();
  const caseId = params?.id as string;

  return (
    <div className="max-w-[1440px] mx-auto px-6 py-6 pb-28">
      {/* F1 수입판정 본문 — 전체 너비 */}
      <ImportCheckPage caseId={caseId} />

      {/* 하단 액션바 */}
      <div className="fixed bottom-0 left-0 right-0 z-50">
        <div className="max-w-[1440px] mx-auto px-6">
          <div className="ds-actionbar-shell px-8 py-4 flex items-center justify-between">
            <Button variant="secondary" size="md" icon={<ChevronLeft size={16} />}
              onClick={() => router.push(`/cases/${caseId}/upload`)}>
              결과로 돌아가기
            </Button>
            <div className="flex items-center gap-3">
              <Button
                variant="primary"
                size="lg"
                icon={<ArrowRight size={18} />}
                onClick={() => router.push(`/cases/${caseId}/upload?rerun_from=f2`)}
              >
                수정 확정
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
