/**
 * 법령 시행 시기(effective_date) 데이터 추가
 *
 * 처리 순서:
 *   1. 청크 JSON 파일 메타데이터 업데이트 (effective_date, law_number 필드 추가)
 *   2. Pinecone 벡터 메타데이터 업데이트 (재임베딩 없이 setMetadata만 변경)
 *   3. Supabase law_effective_dates 테이블 삽입 (실패 시 SQL 출력)
 *
 * 실행: node preprocessing/update_effective_dates.js
 */

const path   = require('path');
const NODE_MODULES = path.join(__dirname, '../테스트용_자료/식품유형/node_modules');
require(path.join(NODE_MODULES, 'dotenv')).config({ path: path.join(__dirname, '../backend/.env') });

const fs     = require('fs');
const crypto = require('crypto');
const { Pinecone }     = require(path.join(NODE_MODULES, '@pinecone-database/pinecone'));
const { createClient } = require(path.join(NODE_MODULES, '@supabase/supabase-js'));

const pc       = new Pinecone({ apiKey: process.env.PINECONE_API_KEY });
const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_KEY);
const INDEX_NAME = process.env.PINECONE_INDEX || 'samc-a';
const CHUNK_DIR  = path.join(__dirname, 'chunks');

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

/* ── 법령별 시행 정보 ── */
const LAW_INFO = {
  '식품공전':         { effective_date: '2024-01-01', law_number: '식품의약품안전처 고시' },
  '주세법 별표':      { effective_date: '2024-01-01', law_number: '법률 제20027호' },
  '주세법 시행령':    { effective_date: '2024-01-01', law_number: '대통령령 제34092호' },
  '알코올 분기 기준': { effective_date: '2024-01-01', law_number: '내부 통합 기준' },
};

/*
 * ID 계산 방식:
 *   - 기존 Python 스크립트 업로드(별표1, 별표3, foodtype):
 *       MD5(`${stem}::${chunk.id}`)  ← 확장자 없는 파일명
 *   - 신규 JS 스크립트 업로드(주류법별표, 분기기준):
 *       MD5(`${filename}::${chunk.id}`)  ← 확장자 포함 파일명
 */
const FILE_CONFIGS = [
  { file: 'foodtype_분류원칙.json',  useStem: true  },
  { file: 'alcohol_별표1.json',      useStem: true  },
  { file: 'alcohol_별표3.json',      useStem: true  },
  { file: 'alcohol_주류법별표.json', useStem: false },
  { file: 'alcohol_분기기준.json',   useStem: false },
];

function computeId(filename, chunkId, useStem) {
  const key = useStem
    ? `${path.basename(filename, '.json')}::${chunkId}`
    : `${path.basename(filename)}::${chunkId}`;
  return crypto.createHash('md5').update(key).digest('hex');
}

/* ── Step 1: 청크 JSON 파일 업데이트 ── */
function updateChunkFiles() {
  console.log('\n[Step 1] 청크 JSON 파일 메타데이터 업데이트');

  for (const config of FILE_CONFIGS) {
    const filePath = path.join(CHUNK_DIR, config.file);
    if (!fs.existsSync(filePath)) { console.warn('  파일 없음:', config.file); continue; }

    const chunks = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    const law = chunks[0]?.metadata?.law;
    const info = LAW_INFO[law];

    if (!info) { console.warn(`  시행일 정보 없음: ${law}`); continue; }

    let changed = 0;
    for (const chunk of chunks) {
      if (chunk.metadata.effective_date !== info.effective_date) {
        chunk.metadata.effective_date = info.effective_date;
        chunk.metadata.law_number     = info.law_number;
        changed++;
      }
    }

    fs.writeFileSync(filePath, JSON.stringify(chunks, null, 2), 'utf-8');
    console.log(`  ✅ ${config.file} (${law}): ${changed}개 청크 업데이트`);
  }
}

/* ── Step 2: Pinecone 메타데이터 업데이트 ── */
async function updatePinecone() {
  console.log('\n[Step 2] Pinecone 메타데이터 업데이트');
  const index = pc.index(INDEX_NAME);
  let success = 0;
  let failed  = 0;

  for (const config of FILE_CONFIGS) {
    const filePath = path.join(CHUNK_DIR, config.file);
    if (!fs.existsSync(filePath)) continue;

    const chunks = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    const law    = chunks[0]?.metadata?.law;
    const info   = LAW_INFO[law];
    if (!info) continue;

    console.log(`\n  [${config.file}] ${law} → ${info.effective_date} (${chunks.length}개)`);

    for (const chunk of chunks) {
      const id = computeId(config.file, chunk.id, config.useStem);
      try {
        await index.update({
          id,
          setMetadata: {
            effective_date: info.effective_date,
            law_number:     info.law_number,
          },
        });
        console.log(`    ✅ ${chunk.id}`);
        success++;
      } catch (e) {
        console.error(`    ❌ ${chunk.id}: ${e.message}`);
        failed++;
      }
      await sleep(150);
    }
  }

  console.log(`\n  Pinecone 완료 → 성공 ${success}개 / 실패 ${failed}개`);
}

/* ── Step 3: Supabase law_effective_dates 삽입 ── */
const CREATE_TABLE_SQL = `
-- Supabase 대시보드 → SQL Editor에 붙여넣고 실행하세요.
CREATE TABLE IF NOT EXISTS law_effective_dates (
  law_name       TEXT PRIMARY KEY,
  effective_date DATE NOT NULL,
  law_number     TEXT,
  created_at     TIMESTAMPTZ DEFAULT now()
);

INSERT INTO law_effective_dates (law_name, effective_date, law_number) VALUES
  ('식품공전',         '2024-01-01', '식품의약품안전처 고시'),
  ('주세법 별표',      '2024-01-01', '법률 제20027호'),
  ('주세법 시행령',    '2024-01-01', '대통령령 제34092호'),
  ('알코올 분기 기준', '2024-01-01', '내부 통합 기준')
ON CONFLICT (law_name) DO UPDATE SET
  effective_date = EXCLUDED.effective_date,
  law_number     = EXCLUDED.law_number;
`;

async function updateSupabase() {
  console.log('\n[Step 3] Supabase law_effective_dates 삽입');

  const rows = Object.entries(LAW_INFO).map(([law_name, v]) => ({
    law_name,
    effective_date: v.effective_date,
    law_number:     v.law_number,
  }));

  const { error } = await supabase
    .from('law_effective_dates')
    .upsert(rows, { onConflict: 'law_name' });

  if (error) {
    console.warn('\n  ⚠ Supabase 삽입 실패 (테이블 미존재):', error.message);
    console.log('\n  ─── Supabase 대시보드 → SQL Editor에서 아래 SQL 실행 후 스크립트 재실행 ───');
    console.log(CREATE_TABLE_SQL);
    console.log('  ─────────────────────────────────────────────────────────────────────');
  } else {
    console.log(`  ✅ ${rows.length}개 법령 시행일 삽입 완료`);
    rows.forEach(r => console.log(`     - ${r.law_name}: ${r.effective_date} (${r.law_number})`));
  }
}

async function main() {
  console.log('='.repeat(50));
  console.log('  법령 시행 시기 데이터 업데이트');
  console.log('='.repeat(50));

  // Step 1: JSON 파일 업데이트 (동기)
  updateChunkFiles();

  // Step 2: Pinecone 업데이트 (비동기)
  await updatePinecone();

  // Step 3: Supabase 삽입 (비동기)
  await updateSupabase();

  console.log('\n' + '='.repeat(50));
  console.log('  완료');
  console.log('='.repeat(50));
}

main().catch(console.error);
