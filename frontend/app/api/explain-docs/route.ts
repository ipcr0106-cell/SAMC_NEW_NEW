import { NextRequest, NextResponse } from "next/server";
import OpenAI from "openai";

let _client: OpenAI | null = null;
function getClient() {
  if (!_client) _client = new OpenAI({ apiKey: process.env.F3_OPENAI_API_KEY || process.env.OPENAI_API_KEY });
  return _client;
}

const SYSTEM_PROMPT = `당신은 수입식품 검역 서류 안내 시스템입니다.

## 역할
사용자에게 제공된 [제품 정보]와 [DB에서 매칭된 서류 데이터]만을 사용하여,
각 서류가 이 특정 제품에 왜 필요한지를 자연어 문장으로 변환하세요.

## 핵심 규칙 (할루시네이션 방지)
1. 아래 제공된 DB 데이터(doc_name, doc_description, law_source, condition, target_country)에
   있는 내용만 사용하세요.
2. DB에 없는 법령 조항, 기준치, 절차, 기관명을 절대 추가하지 마세요.
3. 불확실한 내용은 "정확한 내용은 해당 법령 원문을 확인하시기 바랍니다"로 마무리하세요.
4. 제품 정보(식품유형, 수출국, 원재료)를 문장에 자연스럽게 포함하되,
   DB에 명시된 사실만 연결하세요.

## 문장 구조
"[제품 특성] → [DB의 law_source]에 따라 → [DB의 doc_description 기반 설명]"

## 출력 형식
JSON 배열로만 응답하세요. 다른 텍스트는 쓰지 마세요.
[
  { "doc_id": "서류ID", "explanation": "DB 데이터 기반 맞춤 설명" },
  ...
]`;

interface DocInput {
  id: string;
  doc_name: string;
  doc_description: string;
  law_source: string;
  condition: string | null;
  target_country: string | null;
  submission_type: string;
  submission_timing: string;
}

interface ProductInput {
  food_type: string;
  origin_country: string;
  product_keywords?: string[];
  is_oem: boolean;
  is_first_import: boolean;
  has_organic_cert: boolean;
}

export async function POST(req: NextRequest) {
  try {
    const { product_info, docs }: { product_info: ProductInput; docs: DocInput[] } = await req.json();

    const userMessage = `## 제품 정보
- 식품유형: ${product_info.food_type}
- 수출국: ${product_info.origin_country}
- 원재료: ${product_info.product_keywords?.join(", ") || "미상"}
- OEM: ${product_info.is_oem ? "예" : "아니오"}
- 최초 수입: ${product_info.is_first_import ? "예" : "아니오"}
- 유기인증: ${product_info.has_organic_cert ? "예" : "아니오"}

## DB에서 매칭된 서류 데이터 (이 데이터만 사용하세요)
${docs.map((d: DocInput) => `---
[ID] ${d.id}
[서류명] ${d.doc_name}
[설명] ${d.doc_description}
[법령근거] ${d.law_source}
[조건] ${d.condition || "없음 (공통 필수)"}
[대상국가] ${d.target_country || "모든 국가"}
[제출방식] ${d.submission_type === "keep" ? "보관" : "제출"}
[제출시기] ${d.submission_timing === "first" ? "최초 수입 시" : "매 수입 시"}`).join("\n")}

위 DB 데이터에 있는 내용만으로 각 서류에 대한 맞춤 설명을 작성하세요.
DB에 없는 내용은 절대 추가하지 마세요.`;

    const response = await getClient().chat.completions.create({
      model: "gpt-4o",
      max_tokens: 2048,
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        { role: "user", content: userMessage },
      ],
    });

    const text = response.choices[0].message.content ?? "";

    const jsonMatch = text.match(/\[[\s\S]*\]/);
    if (!jsonMatch) {
      return NextResponse.json({ error: "EXPLAIN_PARSE_FAILED", message: "AI 응답에서 JSON을 파싱할 수 없습니다.", feature: 3 }, { status: 500 });
    }

    const explanations: { doc_id: string; explanation: string }[] = JSON.parse(jsonMatch[0]);

    // 검증: DB에 없는 doc_id가 응답에 포함되면 제거
    const validIds = new Set(docs.map((d: DocInput) => d.id));
    const filtered = explanations.filter(e => validIds.has(e.doc_id));

    return NextResponse.json({ explanations: filtered });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "맞춤 설명 생성 실패";
    console.error("explain-docs error:", err);
    return NextResponse.json({ error: "EXPLAIN_DOCS_FAILED", message, feature: 3 }, { status: 500 });
  }
}
