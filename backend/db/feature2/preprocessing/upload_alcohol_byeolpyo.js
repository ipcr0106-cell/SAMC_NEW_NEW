/**
 * 주세법 시행령 별표1 / 별표3 청크 → Pinecone 업로드
 *
 * ID 방식: stem::chunkId (update_sub_law.js 와 동일)
 *
 * 실행: node preprocessing/upload_alcohol_byeolpyo.js
 */

const path   = require('path');
const NODE_MODULES = path.join(__dirname, '../테스트용_자료/식품유형/node_modules');
require(path.join(NODE_MODULES, 'dotenv')).config({ path: path.join(__dirname, '../backend/.env') });

const fs     = require('fs');
const crypto = require('crypto');
const { Pinecone } = require(path.join(NODE_MODULES, '@pinecone-database/pinecone'));
const OpenAI       = require(path.join(NODE_MODULES, 'openai'));

const openai     = new OpenAI.default({ apiKey: process.env.OPENAI_API_KEY });
const pc         = new Pinecone({ apiKey: process.env.PINECONE_API_KEY });
const INDEX_NAME = process.env.PINECONE_INDEX || 'samc-a';
const CHUNK_DIR  = path.join(__dirname, 'chunks');

const TARGET_FILES = ['alcohol_별표1.json', 'alcohol_별표3.json'];

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function getEmbedding(text) {
  const res = await openai.embeddings.create({ model: 'text-embedding-3-small', input: text });
  return res.data[0].embedding;
}

// update_sub_law.js 와 동일한 ID 생성 방식
function computeId(filename, chunkId) {
  const stem = path.basename(filename, '.json');
  return crypto.createHash('md5').update(`${stem}::${chunkId}`).digest('hex');
}

async function main() {
  console.log('='.repeat(55));
  console.log('  주세법 시행령 별표1/별표3 Pinecone 업로드');
  console.log('='.repeat(55));

  const index = pc.index(INDEX_NAME);

  for (const filename of TARGET_FILES) {
    const filePath = path.join(CHUNK_DIR, filename);
    if (!fs.existsSync(filePath)) { console.error('파일 없음:', filename); continue; }

    const chunks = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    console.log(`\n[${filename}] ${chunks.length}개 업로드 시작`);

    let success = 0;
    for (let i = 0; i < chunks.length; i++) {
      const chunk = chunks[i];
      const id = computeId(filename, chunk.id);
      const embedding = await getEmbedding(chunk.text);

      // null 필드 제거
      const rawMeta = { ...chunk.metadata, text: chunk.text.slice(0, 1000) };
      const meta = Object.fromEntries(
        Object.entries(rawMeta).filter(([, v]) => v !== null && v !== undefined)
      );

      await index.upsert({ records: [{ id, values: embedding, metadata: meta }] });
      console.log(`  ${i + 1}/${chunks.length}: ${chunk.id} (${id.slice(0, 8)}...)`);
      success++;
      await sleep(200);
    }
    console.log(`[완료] ${filename}: ${success}/${chunks.length}개`);
  }

  const stats = await index.describeIndexStats();
  console.log('\n[최종] Pinecone 총 벡터 수:', stats.totalRecordCount);
  console.log('='.repeat(55));
}

main().catch(console.error);
