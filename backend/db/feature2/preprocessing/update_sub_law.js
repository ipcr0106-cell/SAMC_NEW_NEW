/**
 * 주세법 시행령 별표1 / 별표3 구분 메타데이터 추가
 *
 * - alcohol_별표1.json → sub_law: "별표1", sub_law_title: "주류 혼합·첨가 재료 기준"
 * - alcohol_별표3.json → sub_law: "별표3", sub_law_title: "주류 원료 사용량 및 여과방법 기준"
 *
 * 실행: node preprocessing/update_sub_law.js
 */

const path   = require('path');
const NODE_MODULES = path.join(__dirname, '../테스트용_자료/식품유형/node_modules');
require(path.join(NODE_MODULES, 'dotenv')).config({ path: path.join(__dirname, '../backend/.env') });

const fs     = require('fs');
const crypto = require('crypto');
const { Pinecone } = require(path.join(NODE_MODULES, '@pinecone-database/pinecone'));

const pc = new Pinecone({ apiKey: process.env.PINECONE_API_KEY });
const INDEX_NAME = process.env.PINECONE_INDEX || 'samc-a';
const CHUNK_DIR  = path.join(__dirname, 'chunks');

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// stem 기반 ID (Python 업로드 방식)
function computeId(filename, chunkId) {
  const stem = path.basename(filename, '.json');
  return crypto.createHash('md5').update(`${stem}::${chunkId}`).digest('hex');
}

const FILE_CONFIGS = [
  {
    file:          'alcohol_별표1.json',
    sub_law:       '별표1',
    sub_law_title: '주류 혼합·첨가 재료 기준',
  },
  {
    file:          'alcohol_별표3.json',
    sub_law:       '별표3',
    sub_law_title: '주류 원료 사용량 및 여과방법 기준',
  },
];

async function main() {
  console.log('='.repeat(50));
  console.log('  주세법 시행령 별표1/별표3 구분 업데이트');
  console.log('='.repeat(50));

  const index = pc.index(INDEX_NAME);

  for (const config of FILE_CONFIGS) {
    const filePath = path.join(CHUNK_DIR, config.file);
    if (!fs.existsSync(filePath)) { console.warn('파일 없음:', config.file); continue; }

    const chunks = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    console.log(`\n[${config.file}] ${config.sub_law} - ${config.sub_law_title} (${chunks.length}개)`);

    // Step 1: JSON 파일 업데이트
    for (const chunk of chunks) {
      chunk.metadata.sub_law       = config.sub_law;
      chunk.metadata.sub_law_title = config.sub_law_title;
    }
    fs.writeFileSync(filePath, JSON.stringify(chunks, null, 2), 'utf-8');
    console.log(`  ✅ JSON 파일 업데이트 완료`);

    // Step 2: Pinecone 메타데이터 업데이트
    let success = 0;
    for (const chunk of chunks) {
      const id = computeId(config.file, chunk.id);
      try {
        await index.update({
          id,
          setMetadata: {
            sub_law:       config.sub_law,
            sub_law_title: config.sub_law_title,
          },
        });
        console.log(`  ✅ Pinecone: ${chunk.id}`);
        success++;
      } catch (e) {
        console.error(`  ❌ Pinecone: ${chunk.id} →`, e.message);
      }
      await sleep(150);
    }
    console.log(`  Pinecone ${success}/${chunks.length}개 완료`);
  }

  console.log('\n' + '='.repeat(50));
  console.log('  완료');
  console.log('='.repeat(50));
}

main().catch(console.error);
