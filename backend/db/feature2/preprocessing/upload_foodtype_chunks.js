/**
 * Supabase f2_food_types → Pinecone 소분류 단위 청크 업로드
 *
 * 실행:
 *   node preprocessing/upload_foodtype_chunks.js --dry-run  (미리보기)
 *   node preprocessing/upload_foodtype_chunks.js            (실제 업로드)
 */

const path = require('path');
const NODE_MODULES = path.join(__dirname, '../테스트용_자료/식품유형/node_modules');
require(path.join(NODE_MODULES, 'dotenv')).config({ path: path.join(__dirname, '../backend/.env') });

const { createClient } = require(path.join(NODE_MODULES, '@supabase/supabase-js'));
const { Pinecone }     = require(path.join(NODE_MODULES, '@pinecone-database/pinecone'));
const OpenAI           = require(path.join(NODE_MODULES, 'openai'));
const crypto           = require('crypto');

const supabase   = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_KEY);
const pc         = new Pinecone({ apiKey: process.env.PINECONE_API_KEY });
const openai     = new OpenAI.default({ apiKey: process.env.OPENAI_API_KEY });
const INDEX_NAME = process.env.PINECONE_INDEX || 'samc-a';
const DRY_RUN    = process.argv.includes('--dry-run');

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function getEmbedding(text) {
  const res = await openai.embeddings.create({
    model: 'text-embedding-3-small',
    input: text,
  });
  return res.data[0].embedding;
}

// f2_food_types 1행 → Pinecone 청크 텍스트 생성
function buildChunkText(row) {
  const lines = [
    `식품유형: ${row.type_name}`,
    `분류: ${row.category_name}`,
  ];
  if (row.definition) {
    lines.push(`정의: ${row.definition.slice(0, 800)}`);
  }
  if (row.category_definition) {
    lines.push(`카테고리 설명: ${row.category_definition.slice(0, 400)}`);
  }
  return lines.join('\n');
}

async function main() {
  console.log('='.repeat(55));
  console.log('  f2_food_types → Pinecone 소분류 청크 업로드');
  if (DRY_RUN) console.log('  [DRY-RUN] 실제 업로드 없음');
  console.log('='.repeat(55));

  /* ── 1. Supabase에서 전체 데이터 로드 ── */
  const { data: rows, error } = await supabase
    .from('f2_food_types')
    .select('*')
    .order('category_no', { ascending: true });

  if (error) { console.error('Supabase 로드 실패:', error.message); process.exit(1); }
  console.log(`\nSupabase 로드: ${rows.length}행`);

  /* ── 2. 기존 food_type 카테고리 청크 삭제 안내 ── */
  console.log('\n[주의] 기존 foodtype_일반식품, foodtype_분류원칙 청크는');
  console.log('       이 스크립트 완료 후 Pinecone 대시보드에서 수동 삭제 권장');

  if (DRY_RUN) {
    console.log('\n[DRY-RUN] 생성될 청크 샘플 (처음 10개):');
    rows.slice(0, 10).forEach(row => {
      const text = buildChunkText(row);
      console.log(`\n  [${row.category_no}] ${row.category_name} > ${row.type_name}`);
      console.log(`  텍스트 앞 100자: ${text.slice(0, 100)}`);
    });
    console.log(`\n총 ${rows.length}개 청크 생성 예정`);
    console.log('[DRY-RUN 완료] 실제 업로드하려면 --dry-run 없이 실행하세요.');
    return;
  }

  /* ── 3. Pinecone 업로드 ── */
  const index = pc.index(INDEX_NAME);
  let ok = 0, fail = 0;

  console.log(`\nPinecone 업로드 시작 (총 ${rows.length}개)...\n`);

  for (const row of rows) {
    const text = buildChunkText(row);
    const id   = crypto.createHash('md5')
      .update(`f2_food_type::${row.category_no}::${row.type_name}`)
      .digest('hex');

    try {
      const embedding = await getEmbedding(text);

      await index.upsert({
        records: [{
          id,
          values: embedding,
          metadata: {
            law:            '식품공전',
            category:       'food_type',
            category_no:    row.category_no   || '',
            category_name:  row.category_name || '',
            type_name:      row.type_name     || '',
            type_code:      row.type_code     || '',
            source:         row.source        || '식품공전 제5장',
            effective_date: '2024-01-01',
            law_number:     '식품의약품안전처 고시',
            text:           text.slice(0, 1000),
          },
        }],
      });

      ok++;
      console.log(`  ✅ [${row.category_no}] ${row.type_name} (${ok}/${rows.length})`);
    } catch (e) {
      fail++;
      console.error(`  ❌ [${row.category_no}] ${row.type_name}:`, e.message);
    }

    await sleep(250);
  }

  /* ── 4. 최종 확인 ── */
  const stats = await index.describeIndexStats();
  console.log(`\n${'='.repeat(55)}`);
  console.log(`[완료] 성공 ${ok}개 / 실패 ${fail}개`);
  console.log(`[Pinecone] 총 벡터 수: ${stats.totalRecordCount}`);
  console.log('='.repeat(55));
}

main().catch(console.error);
