import { Pinecone } from "@pinecone-database/pinecone";

// Pinecone 클라이언트 — 환경변수 없으면 null (로컬 개발 시 RAG 스킵)
const pc =
  process.env.PINECONE_API_KEY
    ? new Pinecone({ apiKey: process.env.PINECONE_API_KEY })
    : null;

const INDEX_NAME = process.env.PINECONE_INDEX_NAME || "samc-law-f3";

export interface LawChunk {
  text: string;
  law_name: string;
  article: string;
  score: number;
}

/**
 * 제품 정보 문자열로 관련 법령 조항 검색
 * Pinecone 미연결 시 빈 배열 반환 (graceful fallback)
 */
export async function queryLawChunks(query: string, topK = 5): Promise<LawChunk[]> {
  if (!pc) return [];

  try {
    const index = pc.index(INDEX_NAME);

    // Pinecone v7 inference API: 단일 객체 파라미터
    const embeddingsList = await pc.inference.embed({
      model: "multilingual-e5-large",
      inputs: [query],
      parameters: { inputType: "query" },
    });

    // EmbeddingsList.data[0] 은 DenseEmbedding { values: number[], vectorType: 'dense' }
    const firstEmbedding = embeddingsList.data[0] as { values: number[] };
    const queryVector = firstEmbedding.values;

    const results = await index.query({
      vector: queryVector,
      topK,
      includeMetadata: true,
    });

    return (results.matches ?? []).map((m) => ({
      text: (m.metadata?.text as string) ?? "",
      law_name: (m.metadata?.law_name as string) ?? "",
      article: (m.metadata?.article as string) ?? "",
      score: m.score ?? 0,
    }));
  } catch (err) {
    console.error("Pinecone query error:", err);
    return [];
  }
}
