"use client";

import { useRef, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { ArrowRight, ChevronLeft, Loader2 } from "lucide-react";
import Button from "@/components/ui/Button";
import RequiredDocsPage, { type F3SaveHandle } from "@/features/feature3/RequiredDocsPage";

export default function F3RequiredDocsPage() {
  const router = useRouter();
  const params = useParams();
  const caseId = params?.id as string;

  const saveRef = useRef<F3SaveHandle | null>(null);
  const [saving, setSaving] = useState(false);

  const handleConfirm = async () => {
    if (saveRef.current) {
      setSaving(true);
      try {
        await saveRef.current.saveSelectedDocs();
      } finally {
        setSaving(false);
      }
    }
    router.push(`/cases/${caseId}/upload?rerun_from=f4`);
  };

  return (
    <div className="max-w-[1440px] mx-auto px-6 py-6 pb-28">
      <RequiredDocsPage onSaveRef={saveRef} />

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
              icon={saving ? <Loader2 size={18} className="animate-spin" /> : <ArrowRight size={18} />}
              onClick={handleConfirm}
              disabled={saving}
            >
              수정 확정
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
