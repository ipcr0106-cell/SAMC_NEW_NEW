/**
 * 비주류 일반식품 유형 청크를 Pinecone에 업로드
 *
 * 실행: node preprocessing/upload_foodtype_general.js
 */

const path = require('path');
const NODE_MODULES = path.join(__dirname, '../테스트용_자료/식품유형/node_modules');
require(path.join(NODE_MODULES, 'dotenv')).config({ path: path.join(__dirname, '../backend/.env') });

const fs     = require('fs');
const crypto = require('crypto');
const { Pinecone } = require(path.join(NODE_MODULES, '@pinecone-database/pinecone'));
const OpenAI       = require(path.join(NODE_MODULES, 'openai'));

const openai     = new OpenAI.default({ apiKey: process.env.OPENAI_API_KEY });
const pc         = new Pinecone({ apiKey: process.env.PINECONE_API_KEY });
const INDEX_NAME = process.env.PINECONE_INDEX || 'samc-a';
const CHUNK_FILE = path.join(__dirname, 'chunks/foodtype_일반식품.json');

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function getEmbedding(text) {
  const res = await openai.embeddings.create({ model: 'text-embedding-3-small', input: text });
  return res.data[0].embedding;
}

async function main() {
  console.log('='.repeat(50));
  console.log('  비주류 일반식품 유형 Pinecone 업로드');
  console.log('='.repeat(50));

  const chunks  = JSON.parse(fs.readFileSync(CHUNK_FILE, 'utf-8'));
  const index   = pc.index(INDEX_NAME);
  const filename = path.basename(CHUNK_FILE);  // 확장자 포함 (JS 업로드 방식)

  console.log(`\n총 ${chunks.length}개 청크 업로드 시작\n`);

  let success = 0;
  for (let i = 0; i < chunks.length; i++) {
    const chunk = chunks[i];
    const id    = crypto.createHash('md5').update(`${filename}::${chunk.id}`).digest('hex');

    const rawMeta = { ...chunk.metadata, text: chunk.text.slice(0, 1000) };
    const meta    = Object.fromEntries(
      Object.entries(rawMeta).filter(([, v]) => v !== null && v !== undefined)
    );

    const embedding = await getEmbedding(chunk.text);

    await index.upsert({
      records: [{ id, values: embedding, metadata: meta }],
    });

    console.log(`  ${i + 1}/${chunks.length} ✅ ${chunk.id} (${chunk.metadata.food_group})`);
    success++;
    await sleep(200);
  }

  // 업로드 후 전체 벡터 수 확인
  const stats = await index.describeIndexStats();
  console.log(`\n[완료] 업로드 ${success}개`);
  console.log(`[Pinecone] 총 벡터 수: ${stats.totalRecordCount}`);
  console.log('='.repeat(50));
}

main().catch(console.error);
