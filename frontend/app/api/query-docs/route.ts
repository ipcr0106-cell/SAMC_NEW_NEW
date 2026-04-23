import { NextRequest, NextResponse } from "next/server";

/**
 * /api/query-docs — F3 서류 매칭 (프록시)
 *
 * 프론트 RequiredDocsPage 가 PipelineInput 으로 호출.
 * case_id 제거 후 백엔드 /api/v1/required-docs/match 로 포워딩.
 *
 * 백엔드 반환: RequiredDocsResponse (food_type, submit_docs, keep_docs, warnings, match_confidence)
 */
const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    // case_id 는 백엔드 ProductInfo 에 없으므로 제거
    const { case_id: _caseId, reasoning: _reasoning, ...productInfo } = body;

    const res = await fetch(`${BACKEND_URL}/required-docs/match`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(productInfo),
    });

    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json(
        { error: "backend_error", status: res.status, detail: text.slice(0, 500) },
        { status: res.status }
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: "proxy_failed", message: msg }, { status: 500 });
  }
}
