"use client";

import { useRouter, useParams } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import Button from "@/components/ui/Button";
import LabelDraftPage from "@/features/feature5/LabelDraftPage";

export default function F5KoreanLabelPage() {
  const router = useRouter();
  const params = useParams();
  const caseId = params?.id as string;

  return (
    <div className="max-w-[1440px] mx-auto px-6 py-6 pb-28">
      <LabelDraftPage />

      <div className="fixed bottom-0 left-0 right-0 z-50">
        <div className="max-w-[1440px] mx-auto px-6">
          <div className="ds-actionbar-shell px-8 py-4 flex items-center justify-between">
            <Button variant="secondary" size="md" icon={<ChevronLeft size={16} />}
              onClick={() => router.push(`/cases/${caseId}/upload`)}>
              결과로 돌아가기
            </Button>
            <Button
              variant="primary"
              size="lg"
              onClick={() => router.push(`/cases/${caseId}/upload`)}
            >
              수정 확정
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
