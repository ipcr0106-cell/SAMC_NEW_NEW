/**
 * F2 페이지 — /f1#food-type 리다이렉트
 *
 * f1f2 병합으로 F2 식품유형 분류가 F1 ImportCheckPage에 통합됨.
 * /f2 접속 시 즉시 /f1#food-type 으로 이동.
 */
"use client";

import { useEffect } from "react";
import { useRouter, useParams } from "next/navigation";

export default function F2RedirectPage() {
  const router = useRouter();
  const params = useParams();
  const caseId = params?.id as string;

  useEffect(() => {
    if (caseId) {
      router.replace(`/cases/${caseId}/f1#food-type`);
    }
  }, [caseId, router]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <p className="text-sm text-slate-500">식품유형 분류 페이지로 이동 중...</p>
    </div>
  );
}
