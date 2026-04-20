import { NextRequest, NextResponse } from "next/server";

/**
 * /api/pipeline-input?case_id=xxx&step=0|2
 *
 * 브라우저 → Next.js 서버 → 백엔드 (서버사이드 프록시)
 * 백엔드 500/CORS 문제를 우회하기 위해 서버사이드에서 호출.
 */
const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const caseId = searchParams.get("case_id");
  const step = searchParams.get("step");

  if (!caseId || !step) {
    return NextResponse.json({ error: "case_id and step required" }, { status: 400 });
  }

  try {
    const res = await fetch(
      `${BACKEND}/cases/${caseId}/pipeline/feature/${step}`,
      { cache: "no-store" },
    );

    if (!res.ok) {
      const body = await res.text();
      return NextResponse.json(
        { error: `STEP_${step}_NOT_FOUND`, status: res.status, detail: body.slice(0, 300) },
        { status: res.status },
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: "BACKEND_UNREACHABLE", message: msg },
      { status: 503 },
    );
  }
}
