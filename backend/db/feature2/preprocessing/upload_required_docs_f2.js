/**
 * required_documents_아람.csv → Supabase f2_required_documents 업로드
 *
 * 실행:
 *   node preprocessing/upload_required_docs_f2.js --dry-run  (확인만)
 *   node preprocessing/upload_required_docs_f2.js            (업로드)
 */

const path = require('path');
const fs   = require('fs');

const NODE_MODULES = path.join(__dirname, '../테스트용_자료/식품유형/node_modules');
require(path.join(NODE_MODULES, 'dotenv')).config({
  path: path.join(__dirname, '../backend/.env'),
});

const { createClient } = require(path.join(NODE_MODULES, '@supabase/supabase-js'));

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_KEY,
);

const CSV_FILE = path.join(__dirname, 'structured/required_documents_아람.csv');
const DRY_RUN  = process.argv.includes('--dry-run');

function parseCSV(text) {
  const lines = text.trim().split('\n');
  const headers = lines[0].split(',').map(h => h.trim().replace(/\r/g, ''));
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].replace(/\r/g, '');
    if (!line.trim()) continue;
    // 쉼표로 분리 (따옴표 내 쉼표 처리)
    const values = [];
    let cur = '';
    let inQuote = false;
    for (const ch of line) {
      if (ch === '"') { inQuote = !inQuote; continue; }
      if (ch === ',' && !inQuote) { values.push(cur.trim()); cur = ''; continue; }
      cur += ch;
    }
    values.push(cur.trim());
    const row = {};
    headers.forEach((h, idx) => { row[h] = values[idx] ?? null; });
    rows.push(row);
  }
  return rows;
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  console.log('='.repeat(55));
  console.log('  required_documents_아람.csv → f2_required_documents');
  if (DRY_RUN) console.log('  [DRY-RUN] 파싱 결과만 출력 (업로드 없음)');
  console.log('='.repeat(55));

  const raw  = fs.readFileSync(CSV_FILE, 'utf-8');
  const rows = parseCSV(raw);

  // 컬럼 매핑 및 타입 변환
  const mapped = rows.map(r => ({
    food_type:       r.food_type    || null,
    condition:       r.condition    || null,
    doc_name:        r.doc_name,
    doc_description: r.doc_description || null,
    is_mandatory:    r.is_mandatory === 'True' || r.is_mandatory === 'true',
    law_source:      r.law_source   || null,
  }));

  console.log(`\n총 ${mapped.length}행 파싱 완료`);

  if (DRY_RUN) {
    mapped.forEach((r, i) => console.log(`  [${i + 1}] ${r.food_type ?? '(공통)'} | ${r.doc_name}`));
    console.log('\n[DRY-RUN 완료]');
    return;
  }

  // 기존 데이터 삭제 후 재삽입 (중복 방지)
  const { error: delErr } = await supabase.from('f2_required_documents').delete().neq('id', 0);
  if (delErr) {
    console.error('기존 데이터 삭제 실패:', delErr.message);
    return;
  }
  console.log('\n기존 데이터 삭제 완료. 업로드 시작...');

  const BATCH = 50;
  let uploaded = 0;

  for (let i = 0; i < mapped.length; i += BATCH) {
    const batch     = mapped.slice(i, i + BATCH);
    const { error } = await supabase.from('f2_required_documents').insert(batch);
    if (error) {
      console.error(`  ❌ 배치 ${i + 1}~${i + batch.length}:`, error.message);
    } else {
      uploaded += batch.length;
      console.log(`  ✅ ${uploaded}/${mapped.length}`);
    }
    await sleep(200);
  }

  const { count } = await supabase
    .from('f2_required_documents')
    .select('*', { count: 'exact', head: true });

  console.log(`\n[완료] 업로드 ${uploaded}행`);
  console.log(`[Supabase] f2_required_documents 총 ${count}행`);
  console.log('='.repeat(55));
}

main().catch(console.error);
