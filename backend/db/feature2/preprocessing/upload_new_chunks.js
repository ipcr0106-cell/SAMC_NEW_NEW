/**
 * 새 청크 데이터를 Pinecone + Supabase(f2_food_types)에 업로드
 *
 * 실행: node preprocessing/upload_new_chunks.js
 */

const path = require('path');
const NODE_MODULES = path.join(__dirname, '../테스트용_자료/식품유형/node_modules');
require(path.join(NODE_MODULES, 'dotenv')).config({ path: path.join(__dirname, '../backend/.env') });

const fs     = require('fs');
const crypto = require('crypto');
const { Pinecone }     = require(path.join(NODE_MODULES, '@pinecone-database/pinecone'));
const { createClient } = require(path.join(NODE_MODULES, '@supabase/supabase-js'));
const OpenAI           = require(path.join(NODE_MODULES, 'openai'));

const openai   = new OpenAI.default({ apiKey: process.env.OPENAI_API_KEY });
const pc       = new Pinecone({ apiKey: process.env.PINECONE_API_KEY });
const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_KEY);
const INDEX_NAME = process.env.PINECONE_INDEX || 'samc-a';
const CHUNK_DIR  = path.join(__dirname, 'chunks');

const TARGET_FILES = [
  'alcohol_주류법별표.json',
  'alcohol_분기기준.json',
  'foodtype_일반식품.json',
  'foodtype_분류원칙.json',
];

// 주세법 별표 sub_type → f2_food_types 코드 매핑
const CODE_MAP = {
  '주정':     '주세법-1',
  '탁주':     '주세법-2-가',
  '약주':     '주세법-2-나',
  '청주':     '주세법-2-다',
  '맥주':     '주세법-2-라',
  '과실주':   '주세법-2-마',
  '소주':     '주세법-3-가',
  '위스키':   '주세법-3-나',
  '브랜디':   '주세법-3-다',
  '일반증류주': '주세법-3-라',
  '리큐르':   '주세법-3-마',
  '기타주류': '주세법-4',
};

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function getEmbedding(text) {
  const res = await openai.embeddings.create({ model: 'text-embedding-3-small', input: text });
  return res.data[0].embedding;
}

async function uploadToPinecone(chunks, filename) {
  const index = pc.index(INDEX_NAME);
  console.log(`\n[Pinecone] ${filename}: ${chunks.length}개 업로드 시작`);

  for (let i = 0; i < chunks.length; i++) {
    const chunk = chunks[i];
    const embedding = await getEmbedding(chunk.text);
    const id = crypto.createHash('md5').update(`${filename}::${chunk.id}`).digest('hex');

    // Pinecone 메타데이터는 null 불허 → null 필드 제거
    const rawMeta = { ...chunk.metadata, text: chunk.text.slice(0, 1000) };
    const meta = Object.fromEntries(
      Object.entries(rawMeta).filter(([, v]) => v !== null && v !== undefined)
    );
    await index.upsert({
      records: [{ id, values: embedding, metadata: meta }],
    });

    console.log(`  ${i + 1}/${chunks.length}: ${chunk.id}`);
    await sleep(200);
  }
  console.log(`[Pinecone] ${filename} 완료`);
}

async function uploadFoodTypes(chunks) {
  // 주세법 별표 청크만 f2_food_types에 저장
  const lawChunks = chunks.filter(c => c.metadata.law === '주세법 별표' && c.metadata.sub_type);
  if (lawChunks.length === 0) return;

  console.log(`\n[Supabase f2_food_types] 주세법 별표 주류 분류 삽입 (${lawChunks.length}건)`);

  for (const chunk of lawChunks) {
    const subType = chunk.metadata.sub_type;
    const typeCode = CODE_MAP[subType] || `주세법-${subType}`;

    // 중복 방지: type_code가 이미 있으면 건너뜀
    const { data: existing } = await supabase
      .from('f2_food_types')
      .select('id')
      .eq('type_code', typeCode)
      .limit(1);
    if (existing && existing.length > 0) {
      console.log(`  ⏭ 이미 존재: ${subType} (${typeCode})`);
      continue;
    }
    const { error } = await supabase
      .from('f2_food_types')
      .insert({
        category_no:         '주세법',
        category_name:       '주류 (주세법 별표)',
        type_name:           subType,
        type_code:           typeCode,
        definition:          chunk.text,
        category_definition: null,
        source:              '주세법 별표',
      });

    if (error) {
      console.error(`  ❌ ${subType}:`, error.message);
    } else {
      console.log(`  ✅ ${subType} (${typeCode})`);
    }
  }
}

async function main() {
  console.log('='.repeat(50));
  console.log('  새 청크 데이터 업로드');
  console.log('='.repeat(50));

  let allChunks = [];
  for (const filename of TARGET_FILES) {
    const filePath = path.join(CHUNK_DIR, filename);
    if (!fs.existsSync(filePath)) { console.error('파일 없음:', filePath); continue; }
    const chunks = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    console.log(`\n[파일] ${filename}: ${chunks.length}개`);
    allChunks = allChunks.concat(chunks);
    await uploadToPinecone(chunks, filename);
  }

  await uploadFoodTypes(allChunks);

  // Pinecone 최종 통계 확인
  const index = pc.index(INDEX_NAME);
  const stats = await index.describeIndexStats();
  console.log('\n[완료] Pinecone 총 벡터 수:', stats.totalRecordCount);
  console.log('='.repeat(50));
}

main().catch(console.error);
