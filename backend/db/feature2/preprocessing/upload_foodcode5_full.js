/**
 * 식품공전 제5장 PDF → chunks JSON + Pinecone + Supabase 통합 업로드
 *
 * 실행:
 *   node preprocessing/upload_foodcode5_full.js --dry-run  (파싱 확인만)
 *   node preprocessing/upload_foodcode5_full.js            (전체 업로드)
 */

const path = require('path');
const fs   = require('fs');
const crypto = require('crypto');

const NODE_MODULES = path.join(__dirname, '../테스트용_자료/식품유형/node_modules');
require(path.join(NODE_MODULES, 'dotenv')).config({ path: path.join(__dirname, '../backend/.env') });

const pdfParse         = require(path.join(NODE_MODULES, 'pdf-parse'));
const { Pinecone }     = require(path.join(NODE_MODULES, '@pinecone-database/pinecone'));
const { createClient } = require(path.join(NODE_MODULES, '@supabase/supabase-js'));
const OpenAI           = require(path.join(NODE_MODULES, 'openai'));

const openai     = new OpenAI.default({ apiKey: process.env.OPENAI_API_KEY });
const pc         = new Pinecone({ apiKey: process.env.PINECONE_API_KEY });
const supabase   = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_KEY);
const INDEX_NAME = process.env.PINECONE_INDEX || 'samc-a';
const PDF_DIR    = path.join(__dirname, '../DB_최신/식품공전제5장');
const CHUNK_DIR  = path.join(__dirname, 'chunks');
const DRY_RUN    = process.argv.includes('--dry-run');

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function getEmbedding(text) {
  const res = await openai.embeddings.create({ model: 'text-embedding-3-small', input: text });
  return res.data[0].embedding;
}

// ── PDF 파싱 (upload_foodcode5.js 와 동일 로직) ──────────────────

function parseCategoryFromFilename(filename) {
  const base  = path.basename(filename, '.pdf');
  const match = base.match(/^(\d+)\.\s+(.+)$/);
  if (!match) return null;
  return { no: match[1].trim(), name: match[2].trim() };
}

function extractCategoryDefinition(text) {
  const match = text.match(/1\)\s*정의\s*([\s\S]*?)(?=\s*2\)\s*원료|\s*3\)\s*제조)/);
  if (!match) return '';
  return match[1].replace(/\s+/g, ' ').trim().slice(0, 2000);
}

function extractFoodTypeSections(text) {
  const sections = [];
  const re = /4\)\s*식품유형\s*([\s\S]*?)(?=\s*5\)\s*규격|\s*5\.\s*규격|\s*\d+-\d+\s|\s*\d+\.\s+\S|$)/g;
  let m;
  while ((m = re.exec(text)) !== null) sections.push(m[1]);
  return sections;
}

const INVALID_TYPE_KEYWORDS = [
  '보존료', '검출', 'g/kg', 'v/v', 'w/w', '클로스트리디움',
  '장출혈성', '살모넬라', '대장균', '에탄올(v/v%)', '황색포도상구균',
];

function parseTypesFromSection(sectionText) {
  const types = [];
  const text  = '\n' + sectionText;
  const parts = text.split(/\n\s*\((\d+)\)\s+/);
  for (let i = 1; i < parts.length; i += 2) {
    const content   = parts[i + 1] || '';
    const firstLine = content.indexOf('\n');
    let   typeName  = (firstLine >= 0 ? content.slice(0, firstLine) : content).trim();
    const definition = (firstLine >= 0 ? content.slice(firstLine + 1) : '')
      .replace(/\s+/g, ' ').trim().slice(0, 2000);
    const colonIdx = typeName.search(/[∶:]/);
    if (colonIdx > 0) typeName = typeName.slice(0, colonIdx).trim();
    if (!typeName || typeName.length < 2 || typeName.length > 30) continue;
    if (INVALID_TYPE_KEYWORDS.some(kw => typeName.includes(kw))) continue;
    types.push({ typeName, definition });
  }
  return types;
}

async function processPdf(file) {
  const cat = parseCategoryFromFilename(file);
  if (!cat) return [];
  const buf  = fs.readFileSync(path.join(PDF_DIR, file));
  const data = await pdfParse(buf);
  const text = data.text;
  const categoryDef = extractCategoryDefinition(text);
  const sections    = extractFoodTypeSections(text);
  let allTypes = [];
  for (const sec of sections) allTypes = allTypes.concat(parseTypesFromSection(sec));
  if (allTypes.length === 0) {
    return [{ category_no: cat.no, category_name: cat.name, type_name: cat.name,
              definition: categoryDef, category_definition: categoryDef }];
  }
  return allTypes.map(t => ({
    category_no: cat.no, category_name: cat.name, type_name: t.typeName,
    definition: t.definition, category_definition: categoryDef,
  }));
}

// ── 청크 텍스트 생성 ──────────────────────────────────────────────

function buildChunkText(row) {
  const lines = [`식품유형: ${row.type_name}`, `분류: ${row.category_name}`];
  if (row.definition)          lines.push(`정의: ${row.definition.slice(0, 800)}`);
  if (row.category_definition) lines.push(`카테고리 설명: ${row.category_definition.slice(0, 400)}`);
  return lines.join('\n');
}

// ── main ──────────────────────────────────────────────────────────

async function main() {
  console.log('='.repeat(58));
  console.log('  식품공전 제5장 PDF → chunks + Pinecone + Supabase');
  if (DRY_RUN) console.log('  [DRY-RUN]');
  console.log('='.repeat(58));

  // 1. PDF 파싱
  const files = fs.readdirSync(PDF_DIR)
    .filter(f => f.endsWith('.pdf'))
    .sort((a, b) => (parseInt(a) || 0) - (parseInt(b) || 0));

  const allRows = [];
  for (const file of files) {
    const rows = await processPdf(file);
    allRows.push(...rows);
    const cat = parseCategoryFromFilename(file);
    console.log(`  [${cat?.no ?? '?'}] ${cat?.name ?? file} → ${rows.length}개`);
    if (DRY_RUN) rows.forEach(r => console.log(`       └ ${r.type_name}`));
  }
  console.log(`\n총 ${allRows.length}행 파싱 완료`);

  if (DRY_RUN) {
    console.log('\n[DRY-RUN 완료]');
    return;
  }

  // 2. chunks JSON 저장
  const chunks = allRows.map((row, idx) => ({
    id: `foodcode5_${String(idx + 1).padStart(4, '0')}`,
    text: buildChunkText(row),
    metadata: {
      law:           '식품공전',
      category:      'food_type',
      food_group:    row.category_name,
      category_no:   row.category_no,
      type_name:     row.type_name,
      chunk_index:   idx + 1,
      effective_date: '2024-01-01',
      law_number:    '식품의약품안전처 고시',
      char_count:    buildChunkText(row).length,
    },
  }));

  const chunkFile = path.join(CHUNK_DIR, 'foodcode5_식품유형.json');
  fs.writeFileSync(chunkFile, JSON.stringify(chunks, null, 2), 'utf-8');
  console.log(`\n[JSON] ${path.basename(chunkFile)} 저장 완료 (${chunks.length}개)`);

  // 3. Pinecone 업로드
  const index = pc.index(INDEX_NAME);
  console.log('\n[Pinecone] 업로드 시작...');
  let pineconeOk = 0;

  for (let i = 0; i < chunks.length; i++) {
    const chunk     = chunks[i];
    const id        = crypto.createHash('md5').update(`foodcode5_식품유형.json::${chunk.id}`).digest('hex');
    const embedding = await getEmbedding(chunk.text);

    const rawMeta = { ...chunk.metadata, text: chunk.text.slice(0, 1000) };
    const meta    = Object.fromEntries(
      Object.entries(rawMeta).filter(([, v]) => v !== null && v !== undefined)
    );
    await index.upsert({ records: [{ id, values: embedding, metadata: meta }] });

    if ((i + 1) % 10 === 0 || i + 1 === chunks.length) {
      console.log(`  ${i + 1}/${chunks.length} 완료`);
    }
    await sleep(200);
  }
  console.log(`[Pinecone] ${pineconeOk > 0 ? pineconeOk : chunks.length}개 완료`);

  // 4. Supabase 업로드
  console.log('\n[Supabase] f2_food_type_classification 업로드...');
  const BATCH  = 50;
  let sbOk = 0;
  const sbRows = allRows.map(r => ({ ...r, law_source: '식품공전 제5장' }));

  for (let i = 0; i < sbRows.length; i += BATCH) {
    const batch     = sbRows.slice(i, i + BATCH);
    const { error } = await supabase.from('f2_food_type_classification').insert(batch);
    if (error) {
      console.error(`  ❌ 배치 ${i + 1}~${i + batch.length}:`, error.message);
    } else {
      sbOk += batch.length;
      console.log(`  ✅ ${sbOk}/${sbRows.length}`);
    }
    await sleep(200);
  }

  // 5. 최종 통계
  const stats = await index.describeIndexStats();
  const { count } = await supabase.from('f2_food_type_classification').select('*', { count: 'exact', head: true });

  console.log('\n' + '='.repeat(58));
  console.log(`[완료] Pinecone 총 벡터: ${stats.totalRecordCount}`);
  console.log(`[완료] Supabase f2_food_type_classification: ${count}행`);
  console.log('='.repeat(58));
}

main().catch(console.error);
