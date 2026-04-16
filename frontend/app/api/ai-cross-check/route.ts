import { NextRequest, NextResponse } from "next/server";
import OpenAI from "openai";
import { queryLawChunks } from "@/features/feature3/lib/pinecone";

let _client: OpenAI | null = null;
function getClient() {
  if (!_client) _client = new OpenAI({ apiKey: process.env.F3_OPENAI_API_KEY || process.env.OPENAI_API_KEY });
  return _client;
}

/**
 * AI 독립 판정 API
 *
 * DB 매칭과 별도로, AI가 법령을 직접 읽고 필요 서류를 판단.
 * DB 결과와 크로스체크하여 서로의 약점을 보완.
 *
 * - DB에서 놓친 것을 AI가 잡아줌
 * - AI가 지어낸 것을 DB가 걸러줌
 */

const SYSTEM_PROMPT = `당신은 한국 수입식품 검역 전문가입니다.

## 역할
제품 정보를 받아서, 수입식품안전관리 특별법 시행규칙 제27조에 따라
이 제품에 필요한 구비서류를 독립적으로 판단하세요.

## 판단 기준 (시행규칙 제27조제1항)

제1호: 모든 수입식품 → 한글표시 포장지
제1의2호: 모든 수입식품 → 수입식품 사진
제2호: 정밀검사 대상 → 국외 시험·검사성적서
제3호: GMO 표시대상이면서 GMO 미표시 → 구분유통증명서 등
제4호: OEM → 소비기한 설정사유서
제5호: 외화획득용 → 수출계획서
제6호: 외화획득용 원료 → 영업허가서 사본
제7호: 협약체결국 수산물 → 위생증명서
제8호: 축산물 또는 동물성 식품 (제품 자체가 축산물인 경우만. 부재료로 우유/버터 포함은 해당 안 됨) → 수출 위생증명서
제10호가목: 반추동물(소/양/사슴) 원료 (BSE 36개국 제외 국가) → 정부증명서
제10호나목: 죽염/구운소금 → 다이옥신 검사성적서 (최초 수입)
제10호다목: 식약처 홈페이지 게시 특수 케이스 (아래 목록)

제10호다목 특수 케이스:
- 복어 가공식품 → 3종 서류 (원산지/복어독/복어유전자)
- 중국산 천일염 → 식염 인증 + 요오드 무첨가
- 뉴질랜드산 꿀 → 정부증명서
- 일본 13개 도현 → 방사성물질 검사성적서
- 일본 34개 도부현 → 비오염 생산지 증명서
- BSE 36개국 우지/우피젤라틴/소뼈젤라틴 → 해당 정부증명서
- 대마씨 제품 → THC/CBD 검사성적서 (대마씨유 100%는 제외)
- 베트남산 쥐치포 → NAFIQAD 위생증명서
- 젤라틴 원료 제품 → 원료유래 확인 증명서
- 파피씨드 100% → 모르핀 미검출 검사성적서
- 중국산 다진마늘 → 4종 서류
- ASF 73개국 돼지원료 → 열처리/검사/FREE 증명서 택1 (젤라틴, 라드, 돼지고기향 제외)
- PET 기구 (중국/대만/베트남/태국) → 재질확인증명서
- 기능성표시 일반식품 → 원료요건 충족자료 (최초 수입)

동등성인정 (친환경농어업법 제25조):
- 미국/EU(27개국)/영국/캐나다산 + 유기인증 95%+ → NAQS 수입증명서

## 중요 규칙
1. 위 목록에 있는 서류만 판단하세요. 다른 서류를 만들어내지 마세요.
2. 축산물 위생증명서(제8호)는 제품 자체가 축산물일 때만. 과자에 버터 들어갔다고 해당 아님.
3. 확실하지 않으면 "uncertain"으로 표시하세요. 틀리는 것보다 모른다고 하는 게 낫습니다.
4. 각 서류에 대해 판단 근거를 한 문장으로 작성하세요.

## 출력 형식 (JSON만)
{
  "documents": [
    {
      "doc_name": "한글표시 포장지 또는 한글표시 서류",
      "law_source": "제27조제1항제1호",
      "confidence": "high",
      "reason": "모든 수입식품 공통 필수"
    }
  ],
  "warnings": ["추가 확인이 필요한 사항"],
  "overall_confidence": "high"
}

confidence: "high" = 확실, "medium" = 추정, "uncertain" = 불확실`;

interface CrossCheckRequest {
  food_type: string;
  origin_country: string;
  is_oem: boolean;
  is_first_import: boolean;
  has_organic_cert: boolean;
  product_keywords: string[];
}

export async function POST(req: NextRequest) {
  try {
    const body: CrossCheckRequest = await req.json();

    // Pinecone RAG: 제품 정보로 관련 법령 조항 검색
    const queryText = [
      body.food_type,
      body.origin_country,
      ...body.product_keywords,
      body.is_oem ? "OEM 주문자상표부착" : "",
      body.has_organic_cert ? "유기농 유기인증" : "",
    ].filter(Boolean).join(" ");

    const lawChunks = await queryLawChunks(queryText, 6);

    const ragContext = lawChunks.length > 0
      ? `\n\n## Pinecone에서 검색된 관련 법령 조항 (이 내용을 우선 참고하세요)\n` +
        lawChunks.map((c, i) =>
          `[${i + 1}] ${c.law_name} — ${c.article} (관련도: ${(c.score * 100).toFixed(0)}%)\n${c.text}`
        ).join("\n\n")
      : "";

    const userMessage = `## 제품 정보
- 식품유형: ${body.food_type}
- 제조국: ${body.origin_country}
- 원재료: ${body.product_keywords.join(", ")}
- OEM: ${body.is_oem ? "예" : "아니오"}
- 최초 수입: ${body.is_first_import ? "예" : "아니오"}
- 유기인증 (95%+): ${body.has_organic_cert ? "예" : "아니오"}${ragContext}

이 제품에 필요한 구비서류를 판단하세요.`;

    const response = await getClient().chat.completions.create({
      model: "gpt-4o",
      max_tokens: 2048,
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        { role: "user", content: userMessage },
      ],
    });

    const text = response.choices[0].message.content ?? "";

    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      return NextResponse.json({ error: "AI_PARSE_FAILED", message: "AI 응답 파싱 실패", feature: 3 }, { status: 500 });
    }

    const aiResult = JSON.parse(jsonMatch[0]);
    return NextResponse.json(aiResult);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "AI 판정 실패";
    console.error("ai-cross-check error:", err);
    return NextResponse.json({ error: "AI_CROSS_CHECK_FAILED", message, feature: 3 }, { status: 500 });
  }
}
