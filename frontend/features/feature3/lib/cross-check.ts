/**
 * DB 매칭 결과와 AI 독립 판정 결과를 크로스체크
 *
 * 결과 유형:
 * - "both"    : DB + AI 둘 다 감지 → 높은 신뢰도
 * - "db_only" : DB만 감지 → 일반 (규칙 기반)
 * - "ai_only" : AI만 감지 → 담당자 확인 필요 (DB에 없는 것을 AI가 잡음)
 */

export interface CrossCheckResult {
  doc_name: string;
  law_source: string;
  match_type: "both" | "db_only" | "ai_only";
  ai_confidence?: "high" | "medium" | "uncertain";
  ai_reason?: string;
}

interface AiDoc {
  doc_name: string;
  law_source: string;
  confidence: "high" | "medium" | "uncertain";
  reason: string;
}

interface DbDoc {
  id: string;
  doc_name: string;
  law_source: string;
}

/**
 * 두 서류명이 같은 서류를 가리키는지 비교 (부분 매칭)
 */
function isSameDoc(dbName: string, aiName: string): boolean {
  const dbLower = dbName.toLowerCase();
  const aiLower = aiName.toLowerCase();

  // 정확 매칭
  if (dbLower === aiLower) return true;

  // 핵심 키워드 매칭
  const dbWords = dbLower.split(/[\s·,()（）]+/).filter(w => w.length > 1);
  const aiWords = aiLower.split(/[\s·,()（）]+/).filter(w => w.length > 1);

  // 3글자 이상 키워드 중 2개 이상 겹치면 같은 서류
  const overlap = dbWords.filter(dw => aiWords.some(aw => aw.includes(dw) || dw.includes(aw)));
  return overlap.length >= 2;
}

/**
 * law_source가 같은 조항을 가리키는지 비교
 */
function isSameLaw(dbLaw: string, aiLaw: string): boolean {
  // "제27조제1항제1호" 같은 패턴 추출
  const extractArticle = (s: string) => {
    const match = s.match(/제\d+조(?:의\d+)?(?:제\d+항)?(?:제\d+(?:의\d+)?호)?(?:[가-힣]목)?/);
    return match ? match[0] : s;
  };
  return extractArticle(dbLaw) === extractArticle(aiLaw);
}

export function crossCheck(
  dbDocs: DbDoc[],
  aiDocs: AiDoc[],
): CrossCheckResult[] {
  const results: CrossCheckResult[] = [];
  const matchedAiIndices = new Set<number>();

  // 1. DB 서류 기준으로 AI 매칭 찾기
  for (const dbDoc of dbDocs) {
    let matched = false;
    for (let i = 0; i < aiDocs.length; i++) {
      if (matchedAiIndices.has(i)) continue;
      const aiDoc = aiDocs[i];

      if (isSameDoc(dbDoc.doc_name, aiDoc.doc_name) || isSameLaw(dbDoc.law_source, aiDoc.law_source)) {
        results.push({
          doc_name: dbDoc.doc_name,
          law_source: dbDoc.law_source,
          match_type: "both",
          ai_confidence: aiDoc.confidence,
          ai_reason: aiDoc.reason,
        });
        matchedAiIndices.add(i);
        matched = true;
        break;
      }
    }

    if (!matched) {
      results.push({
        doc_name: dbDoc.doc_name,
        law_source: dbDoc.law_source,
        match_type: "db_only",
      });
    }
  }

  // 2. AI만 감지한 서류 (DB에 없는 것)
  for (let i = 0; i < aiDocs.length; i++) {
    if (matchedAiIndices.has(i)) continue;
    const aiDoc = aiDocs[i];

    // uncertain은 제외 (확실하지 않은 건 보여주지 않음)
    if (aiDoc.confidence === "uncertain") continue;

    results.push({
      doc_name: aiDoc.doc_name,
      law_source: aiDoc.law_source,
      match_type: "ai_only",
      ai_confidence: aiDoc.confidence,
      ai_reason: aiDoc.reason,
    });
  }

  return results;
}
