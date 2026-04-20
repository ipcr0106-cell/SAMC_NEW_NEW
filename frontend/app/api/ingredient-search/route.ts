import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const q = searchParams.get("q");
  const limit = searchParams.get("limit") ?? "10";

  if (!q) return NextResponse.json([]);

  try {
    const res = await fetch(
      `${BACKEND}/ingredient-search?q=${encodeURIComponent(q)}&limit=${limit}`,
      { cache: "no-store" },
    );
    if (!res.ok) return NextResponse.json([]);
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json([]);
  }
}
