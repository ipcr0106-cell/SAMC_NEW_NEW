import { NextRequest, NextResponse } from "next/server";
import { analyzeWithSynonyms } from "@/features/feature3/lib/ingredient-synonym-map";

/**
 * 원재료 → DB 키워드 매핑 API (F3)
 *
 * 1차: 동의어 사전 (비용 0원, 즉시) → 90% 커버
 * 2차: LLM fallback (비용 발생, 느림) → 사전에 없는 것만 (현재 미구현, 추후 추가)
 */

interface AnalyzeRequest {
  ingredients: string[];
  origin_country: string;
  food_type: string;
}

export async function POST(req: NextRequest) {
  try {
    const body: AnalyzeRequest = await req.json();

    if (!body.ingredients || body.ingredients.length === 0) {
      return NextResponse.json({
        detected_keywords: [],
        warnings: [],
        banned: [],
        unmatched_count: 0,
        method: "none",
      });
    }

    // ── 1차: 동의어 사전 매칭 (즉시, 무료) ────────────
    const result = analyzeWithSynonyms(
      body.ingredients,
      body.origin_country || "",
    );

    // ── 금지 성분 체크 ────────────────────────────────
    const banned: string[] = [];
    const bannedKeywords = ["cbd", "cannabidiol", "kratom", "크라톰"];
    for (const ing of body.ingredients) {
      const lower = ing.toLowerCase();
      if (bannedKeywords.some((bk) => lower.includes(bk))) {
        banned.push(
          `수입 금지 성분 감지: '${ing}'. CBD/크라톰은 한국에서 마약류로 분류되어 수입이 불가합니다.`,
        );
      }
    }

    return NextResponse.json({
      detected_keywords: result.detected,
      warnings: result.warnings,
      banned,
      unmatched_count: result.unmatchedCount,
      method: "synonym_map",
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "성분 분석 실패";
    console.error("analyze-ingredients error:", err);
    return NextResponse.json(
      { error: "ANALYZE_INGREDIENTS_FAILED", message, feature: 3 },
      { status: 500 },
    );
  }
}
