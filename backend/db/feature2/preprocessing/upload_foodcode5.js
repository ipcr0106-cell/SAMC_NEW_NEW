/**
 * 식품공전 제5장 PDF → Supabase f2_food_types 업로드
 *
 * 사전 준비: Supabase SQL Editor에서 아래 DDL 실행 후 이 스크립트 실행
 *
 * CREATE TABLE f2_food_types (
 *   id              BIGSERIAL PRIMARY KEY,
 *   category_no     TEXT NOT NULL,
 *   category_name   TEXT NOT NULL,
 *   type_name       TEXT NOT NULL,
 *   definition      TEXT,
 *   category_definition TEXT,
 *   source          TEXT DEFAULT '식품공전 제5장',
 *   created_at      TIMESTAMPTZ DEFAULT NOW()
 * );
 * CREATE INDEX idx_f2ft_cat ON f2_food_types (category_no);
 * CREATE INDEX idx_f2ft_type ON f2_food_types (type_name);
 *
 * 실행:
 *   node preprocessing/upload_foodcode5.js          (업로드)
 *   node preprocessing/upload_foodcode5.js --dry-run (파싱 결과만 출력)
 */

const path = require('path');
const fs   = require('fs');

const NODE_MODULES = path.join(__dirname, '../테스트용_자료/식품유형/node_modules');
require(path.join(NODE_MODULES, 'dotenv')).config({
  path: path.join(__dirname, '../backend/.env'),
});

const pdfParse      = require(path.join(NODE_MODULES, 'pdf-parse'));
const { createClient } = require(path.join(NODE_MODULES, '@supabase/supabase-js'));

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_KEY,
);

const PDF_DIR  = path.join(__dirname, '../DB_최신/식품공전제5장');
const DRY_RUN  = process.argv.includes('--dry-run');

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ─────────────────────────────────────────────────────────
// 파일명 파싱: "1. 과자류, 빵류 또는 떡류.pdf" → { no, name }
// ─────────────────────────────────────────────────────────
function parseCategoryFromFilename(filename) {
  const base  = path.basename(filename, '.pdf');
  const match = base.match(/^(\d+)\.\s+(.+)$/);
  if (!match) return null;
  return { no: match[1].trim(), name: match[2].trim() };
}

// ─────────────────────────────────────────────────────────
// 카테고리 전체 정의 추출: "1) 정의" ~ "2) 원료" 이전
// ─────────────────────────────────────────────────────────
function extractCategoryDefinition(text) {
  const match = text.match(/1\)\s*정의\s*([\s\S]*?)(?=\s*2\)\s*원료|\s*3\)\s*제조)/);
  if (!match) return '';
  return match[1].replace(/\s+/g, ' ').trim().slice(0, 2000);
}

// ─────────────────────────────────────────────────────────
// 식품유형 섹션(들) 추출: PDF 내 여러 subcategory 처리
// 예) 주류 → 15-1 발효주류, 15-2 증류주류 각각 "4) 식품유형" 보유
// ─────────────────────────────────────────────────────────
function extractFoodTypeSections(text) {
  const sections = [];
  const re = /4\)\s*식품유형\s*([\s\S]*?)(?=\s*5\)\s*규격|\s*5\.\s*규격|\s*\d+-\d+\s|\s*\d+\.\s+\S|$)/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    sections.push(m[1]);
  }
  return sections;
}

// ─────────────────────────────────────────────────────────
// 개별 식품유형 파싱: "(N) 이름\n 정의..." 패턴
// ─────────────────────────────────────────────────────────
// 유효하지 않은 유형명 키워드 (규격·미생물 섹션 오탐 방지)
const INVALID_TYPE_KEYWORDS = [
  '보존료', '검출', 'g/kg', 'v/v', 'w/w', '클로스트리디움',
  '장출혈성', '살모넬라', '대장균', '에탄올(v/v%)', '황색포도상구균',
];

function parseTypesFromSection(sectionText) {
  const types = [];

  // 앞에 개행 추가 → 섹션 시작 "(1) 이름"도 캡처
  const text  = '\n' + sectionText;
  const parts = text.split(/\n\s*\((\d+)\)\s+/);

  // parts 구조: [앞부분, "1", "이름\n정의", "2", "이름\n정의", ...]
  for (let i = 1; i < parts.length; i += 2) {
    const content   = parts[i + 1] || '';
    const firstLine = content.indexOf('\n');
    let   typeName  = (firstLine >= 0 ? content.slice(0, firstLine) : content).trim();
    const definition = (firstLine >= 0 ? content.slice(firstLine + 1) : '')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 2000);

    // 콜론 뒤 정의 분리: "난황액∶알의 노른자..." → "난황액"
    const colonIdx = typeName.search(/[∶:]/);
    if (colonIdx > 0) typeName = typeName.slice(0, colonIdx).trim();

    // 유효하지 않은 유형명 필터링
    if (!typeName || typeName.length < 2 || typeName.length > 30) continue;
    if (INVALID_TYPE_KEYWORDS.some(kw => typeName.includes(kw)))  continue;

    types.push({ typeName, definition });
  }
  return types;
}

// ─────────────────────────────────────────────────────────
// PDF 1개 처리
// ─────────────────────────────────────────────────────────
async function processPdf(file) {
  const cat = parseCategoryFromFilename(file);
  if (!cat) return [];

  const buf  = fs.readFileSync(path.join(PDF_DIR, file));
  const data = await pdfParse(buf);
  const text = data.text;

  const categoryDef = extractCategoryDefinition(text);
  const sections    = extractFoodTypeSections(text);

  let allTypes = [];
  for (const sec of sections) {
    allTypes = allTypes.concat(parseTypesFromSection(sec));
  }

  if (allTypes.length === 0) {
    // 소분류 없으면 카테고리 자체 1행
    return [{
      category_no:         cat.no,
      category_name:       cat.name,
      type_name:           cat.name,
      definition:          categoryDef,
      category_definition: categoryDef,
      source:              '식품공전 제5장',
    }];
  }

  return allTypes.map(t => ({
    category_no:         cat.no,
    category_name:       cat.name,
    type_name:           t.typeName,
    definition:          t.definition,
    category_definition: categoryDef,
    source:              '식품공전 제5장',
  }));
}

// ─────────────────────────────────────────────────────────
// main
// ─────────────────────────────────────────────────────────
async function main() {
  console.log('='.repeat(55));
  console.log('  식품공전 제5장 → Supabase f2_food_types 업로드');
  if (DRY_RUN) console.log('  [DRY-RUN] 파싱 결과만 출력 (업로드 없음)');
  console.log('='.repeat(55));

  const files = fs.readdirSync(PDF_DIR)
    .filter(f => f.endsWith('.pdf'))
    .sort((a, b) => {
      const na = parseInt(a) || 0;
      const nb = parseInt(b) || 0;
      return na - nb;
    });

  const allRows = [];

  for (const file of files) {
    const rows = await processPdf(file);
    allRows.push(...rows);

    const cat = parseCategoryFromFilename(file);
    console.log(`  [${cat?.no ?? '?'}] ${cat?.name ?? file} → ${rows.length}개 유형`);

    if (DRY_RUN && rows.length > 0) {
      rows.forEach(r => console.log(`       └ ${r.type_name}`));
    }
  }

  console.log(`\n총 ${allRows.length}행 추출`);

  if (DRY_RUN) {
    console.log('\n[DRY-RUN 완료] 실제 업로드하려면 --dry-run 없이 실행하세요.');
    return;
  }

  // ── Supabase 업로드 ──
  console.log('\nSupabase 업로드 시작...');
  const BATCH    = 50;
  let   uploaded = 0;

  for (let i = 0; i < allRows.length; i += BATCH) {
    const batch        = allRows.slice(i, i + BATCH);
    const { error }    = await supabase.from('f2_food_types').insert(batch);
    if (error) {
      console.error(`  ❌ 배치 ${i + 1}~${i + batch.length}:`, error.message);
    } else {
      uploaded += batch.length;
      console.log(`  ✅ ${uploaded}/${allRows.length}`);
    }
    await sleep(200);
  }

  // 최종 확인
  const { count } = await supabase
    .from('f2_food_types')
    .select('*', { count: 'exact', head: true });

  console.log(`\n[완료] 업로드 ${uploaded}행`);
  console.log(`[Supabase] f2_food_types 총 ${count}행`);
  console.log('='.repeat(55));
}

main().catch(console.error);
