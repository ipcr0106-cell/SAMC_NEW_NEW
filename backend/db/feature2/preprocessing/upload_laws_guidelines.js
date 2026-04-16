/**
 * 법률/시행령/시행규칙/행정규칙/가이드라인 PDF → chunks JSON + Pinecone 업로드
 *
 * 청킹 전략: 600자 단위, 150자 오버랩 (sliding window)
 *
 * 실행:
 *   node preprocessing/upload_laws_guidelines.js --dry-run
 *   node preprocessing/upload_laws_guidelines.js
 */

const path = require('path');
const fs   = require('fs');
const crypto = require('crypto');

const NODE_MODULES = path.join(__dirname, '../테스트용_자료/식품유형/node_modules');
require(path.join(NODE_MODULES, 'dotenv')).config({ path: path.join(__dirname, '../backend/.env') });

const pdfParse     = require(path.join(NODE_MODULES, 'pdf-parse'));
const { Pinecone } = require(path.join(NODE_MODULES, '@pinecone-database/pinecone'));
const OpenAI       = require(path.join(NODE_MODULES, 'openai'));

const openai     = new OpenAI.default({ apiKey: process.env.OPENAI_API_KEY });
const pc         = new Pinecone({ apiKey: process.env.PINECONE_API_KEY });
const INDEX_NAME = process.env.PINECONE_INDEX || 'samc-a';
const DB_DIR     = path.join(__dirname, '../DB_최신');
const CHUNK_DIR  = path.join(__dirname, 'chunks');
const DRY_RUN    = process.argv.includes('--dry-run');

const CHUNK_SIZE    = 600;   // 청크 크기 (자)
const CHUNK_OVERLAP = 150;   // 오버랩 (자)

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function getEmbedding(text) {
  const res = await openai.embeddings.create({ model: 'text-embedding-3-small', input: text });
  return res.data[0].embedding;
}

// ── 파일명에서 법령 메타 파싱 ─────────────────────────────────────
function parseLawMeta(filename) {
  const base = path.basename(filename, '.pdf');
  // 번호/날짜 패턴: (제XXXX호)(YYYYMMDD)
  const lawNoMatch  = base.match(/\(제([\w-]+호)\)/);
  const dateMatch   = base.match(/\((\d{8})\)/);
  const lawNo       = lawNoMatch ? lawNoMatch[1] : '';
  const rawDate     = dateMatch  ? dateMatch[1]  : '';
  const effectiveDate = rawDate.length === 8
    ? `${rawDate.slice(0,4)}-${rawDate.slice(4,6)}-${rawDate.slice(6,8)}`
    : '2024-01-01';
  // 괄호 이전 법령명
  const nameMatch   = base.match(/^([^(]+)/);
  const lawName     = nameMatch ? nameMatch[1].trim() : base;
  return { lawName, lawNo, effectiveDate };
}

// ── 텍스트 정제 ───────────────────────────────────────────────────
function cleanText(text) {
  return text
    .replace(/\s{3,}/g, '  ')       // 과도한 공백 축소
    .replace(/법제처\s+\d+\s+국가법령정보센터/g, '')  // 헤더 제거
    .replace(/^\s+|\s+$/g, '')
    .trim();
}

// ── 슬라이딩 윈도우 청킹 ─────────────────────────────────────────
function chunkText(text, size = CHUNK_SIZE, overlap = CHUNK_OVERLAP) {
  const chunks = [];
  let start = 0;
  while (start < text.length) {
    const end = Math.min(start + size, text.length);
    chunks.push(text.slice(start, end).trim());
    if (end >= text.length) break;
    start += size - overlap;
  }
  return chunks.filter(c => c.length > 50);  // 너무 짧은 청크 제거
}

// ── PDF 1개 처리 → chunk 배열 반환 ───────────────────────────────
async function processPdf(filePath, category, stem) {
  const { lawName, lawNo, effectiveDate } = parseLawMeta(filePath);
  const buf  = fs.readFileSync(filePath);
  const data = await pdfParse(buf);
  const text = cleanText(data.text);

  const textChunks = chunkText(text);
  return textChunks.map((t, i) => ({
    id: `${stem}_${String(i + 1).padStart(4, '0')}`,
    text: t,
    metadata: {
      law:            lawName,
      law_number:     lawNo,
      category:       category,
      chunk_index:    i + 1,
      total_chunks:   textChunks.length,
      effective_date: effectiveDate,
      char_count:     t.length,
    },
  }));
}

// ── Pinecone 업로드 ───────────────────────────────────────────────
async function uploadToPinecone(chunks, jsonFilename) {
  const index = pc.index(INDEX_NAME);
  let ok = 0;
  for (let i = 0; i < chunks.length; i++) {
    const chunk     = chunks[i];
    const id        = crypto.createHash('md5').update(`${jsonFilename}::${chunk.id}`).digest('hex');
    const embedding = await getEmbedding(chunk.text);
    const rawMeta   = { ...chunk.metadata, text: chunk.text.slice(0, 1000) };
    const meta      = Object.fromEntries(
      Object.entries(rawMeta).filter(([, v]) => v !== null && v !== undefined)
    );
    await index.upsert({ records: [{ id, values: embedding, metadata: meta }] });
    if ((i + 1) % 20 === 0 || i + 1 === chunks.length) {
      process.stdout.write(`    ${i + 1}/${chunks.length} 완료\n`);
    }
    ok++;
    await sleep(200);
  }
  return ok;
}

// ── 대상 파일 목록 ────────────────────────────────────────────────
function collectTargets() {
  const targets = [];

  // 법률
  const lawDir = path.join(DB_DIR, '1_법률');
  fs.readdirSync(lawDir).filter(f => f.endsWith('.pdf')).forEach(f => {
    targets.push({ filePath: path.join(lawDir, f), category: 'law', stem: 'law_' + path.basename(f, '.pdf').slice(0, 20).replace(/\s/g, '_') });
  });

  // 시행령
  const orderDir = path.join(DB_DIR, '2_시행령');
  fs.readdirSync(orderDir).filter(f => f.endsWith('.pdf')).forEach(f => {
    targets.push({ filePath: path.join(orderDir, f), category: 'enforcement_order', stem: 'order_' + path.basename(f, '.pdf').slice(0, 20).replace(/\s/g, '_') });
  });

  // 시행규칙
  const ruleDir = path.join(DB_DIR, '3_시행규칙');
  fs.readdirSync(ruleDir).filter(f => f.endsWith('.pdf')).forEach(f => {
    targets.push({ filePath: path.join(ruleDir, f), category: 'enforcement_rule', stem: 'rule_' + path.basename(f, '.pdf').slice(0, 20).replace(/\s/g, '_') });
  });

  // 행정규칙 (고시)
  const adminDir = path.join(DB_DIR, '5_행정규칙');
  fs.readdirSync(adminDir).filter(f => f.endsWith('.pdf')).forEach(f => {
    targets.push({ filePath: path.join(adminDir, f), category: 'admin_rule', stem: 'admin_' + path.basename(f, '.pdf').slice(0, 20).replace(/\s/g, '_') });
  });

  // 가이드라인: 최상위 PDF
  const guideDir = path.join(DB_DIR, '6_가이드라인');
  fs.readdirSync(guideDir).filter(f => f.endsWith('.pdf')).forEach(f => {
    targets.push({ filePath: path.join(guideDir, f), category: 'guideline', stem: 'guide_' + path.basename(f, '.pdf').slice(0, 20).replace(/\s/g, '_') });
  });

  // 가이드라인 서브폴더 PDF
  const guideSubs = ['OEM수입식품관리', '한미_동등성인정', '한영_동등성인정', '한유럽_동등성인정', '한캐나다_동등성인정'];
  for (const sub of guideSubs) {
    const subDir = path.join(guideDir, sub);
    if (!fs.existsSync(subDir)) continue;
    fs.readdirSync(subDir).filter(f => f.endsWith('.pdf')).forEach(f => {
      const subStem = sub.replace(/[_\s]/g, '').slice(0, 8);
      targets.push({ filePath: path.join(subDir, f), category: 'guideline', stem: `guide_${subStem}_` + path.basename(f, '.pdf').slice(0, 15).replace(/\s/g, '_') });
    });
  }

  return targets;
}

// ── main ──────────────────────────────────────────────────────────
async function main() {
  console.log('='.repeat(60));
  console.log('  법령/가이드라인 PDF → chunks + Pinecone 업로드');
  if (DRY_RUN) console.log('  [DRY-RUN]');
  console.log('='.repeat(60));

  const targets = collectTargets();
  console.log(`\n대상 파일: ${targets.length}개\n`);

  let totalChunks = 0;

  for (const { filePath, category, stem } of targets) {
    const filename = path.basename(filePath);
    console.log(`[${category}] ${filename.slice(0, 55)}`);

    let chunks;
    try {
      chunks = await processPdf(filePath, category, stem);
    } catch (e) {
      console.error(`  ❌ 파싱 에러: ${e.message}`);
      continue;
    }

    console.log(`  → ${chunks.length}개 청크`);
    totalChunks += chunks.length;

    if (DRY_RUN) continue;

    // JSON 저장
    const jsonFilename = `${stem}.json`;
    fs.writeFileSync(path.join(CHUNK_DIR, jsonFilename), JSON.stringify(chunks, null, 2), 'utf-8');

    // Pinecone 업로드
    await uploadToPinecone(chunks, jsonFilename);
    console.log(`  ✅ 완료\n`);
  }

  console.log(`\n총 청크: ${totalChunks}개`);

  if (!DRY_RUN) {
    const stats = await pc.index(INDEX_NAME).describeIndexStats();
    console.log(`[완료] Pinecone 총 벡터: ${stats.totalRecordCount}`);
  }

  console.log('='.repeat(60));
}

main().catch(console.error);
