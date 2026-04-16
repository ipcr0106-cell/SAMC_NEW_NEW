/**
 * food_types + f2_food_types 데이터 통합 → f2_food_types 최종 취합
 *
 * 전략:
 *   1. type_code 보완: food_types 코드(1-1, 1-2 등) → f2_food_types에 추가
 *   2. category_definition 보완: food_types depth=0 정의 → f2_food_types에 보완
 *   3. 신규 항목 추가: food_types에만 있는 유효한 항목 추가 (품질 필터 적용)
 *   4. 완료 후 food_types 삭제 안내
 *
 * 사전 준비: Supabase SQL Editor에서 실행
 *   ALTER TABLE f2_food_types ADD COLUMN IF NOT EXISTS type_code TEXT;
 *
 * 실행:
 *   node preprocessing/merge_food_types.js --dry-run  (미리보기)
 *   node preprocessing/merge_food_types.js            (실제 적용)
 */

const path = require('path');
const NODE_MODULES = path.join(__dirname, '../테스트용_자료/식품유형/node_modules');
require(path.join(NODE_MODULES, 'dotenv')).config({ path: path.join(__dirname, '../backend/.env') });
const { createClient } = require(path.join(NODE_MODULES, '@supabase/supabase-js'));

const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_KEY);
const DRY_RUN  = process.argv.includes('--dry-run');

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// 유형명 정규화
function norm(str) {
  return (str || '').replace(/\s+/g, '').replace(/[()（）·•,、]/g, '').toLowerCase();
}

// 유사 매칭: 완전일치 → 한쪽이 다른 쪽을 포함 (최소 3자)
function isSimilar(a, b) {
  const na = norm(a), nb = norm(b);
  if (na === nb) return true;
  if (na.length >= 3 && nb.includes(na)) return true;
  if (nb.length >= 3 && na.includes(nb)) return true;
  return false;
}

// 신규 추가 항목 품질 필터 (잘린 이름·이상한 항목 제외)
function isValidNewItem(name) {
  if (!name || name.length < 3) return false;           // 너무 짧음
  if (name.length > 25) return false;                   // 너무 김 (정의가 붙어있을 가능성)
  if (/식품의 제조|가공·조리|다음의|이하로|이상으로/.test(name)) return false;
  if (/[0-9]+%/.test(name)) return false;
  // 원재료·재질 접미어가 붙은 경우 (파싱 오류 패턴)
  if (/두류를|전분질|과일류$|식품를|이라 함|두류\(/.test(name)) return false;
  // 조사로 끝나는 경우 (문장이 잘린 패턴)
  if (/[가-힣][을를이가의에서]$/.test(name)) return false;
  return true;
}

async function main() {
  console.log('='.repeat(55));
  console.log('  food_types + f2_food_types 통합 → f2_food_types');
  if (DRY_RUN) console.log('  [DRY-RUN] 실제 DB 변경 없음');
  console.log('='.repeat(55));

  /* ── 1. 데이터 로드 ── */
  const { data: ft, error: e1 } = await supabase.from('food_types').select('*');
  const { data: f2, error: e2 } = await supabase.from('f2_food_types').select('*');
  if (e1) { console.error('food_types 로드 실패:', e1.message); process.exit(1); }
  if (e2) { console.error('f2_food_types 로드 실패:', e2.message); process.exit(1); }

  console.log(`\nfood_types 로드: ${ft.length}행`);
  console.log(`f2_food_types 로드: ${f2.length}행`);

  /* ── 2. food_types 계층 구조 ── */
  const ftById   = Object.fromEntries(ft.map(r => [r.id, r]));
  const d0       = ft.filter(r => r.depth === 0);   // 24개 대분류
  const d0ByCode = Object.fromEntries(d0.map(r => [r.code, r]));

  // depth=0 조상 찾기
  function getRootAncestor(row) {
    let cur = row;
    while (cur.depth > 0 && cur.parent_id) {
      const parent = ftById[cur.parent_id];
      if (!parent) break;
      cur = parent;
    }
    return cur.depth === 0 ? cur : null;
  }

  // leaf 노드 (depth=2 + depth=1 중 자식 없는 것)
  const d2ParentIds = new Set(ft.filter(r => r.depth === 2).map(r => r.parent_id));
  const leafD1      = ft.filter(r => r.depth === 1 && !d2ParentIds.has(r.id));
  const ftLeaves    = [...ft.filter(r => r.depth === 2), ...leafD1];

  /* ── 3. f2_food_types 룩업 ── */
  // category_no별 type_name 목록
  const f2ByCat = {};
  f2.forEach(r => {
    if (!f2ByCat[r.category_no]) f2ByCat[r.category_no] = [];
    f2ByCat[r.category_no].push(r);
  });

  /* ── 4. 매칭 및 보완 계산 ── */
  const typeCodeUpdates   = [];  // f2 행에 type_code 추가
  const defUpdates        = [];  // f2 행에 null definition 보완
  const catDefUpdates     = [];  // f2 행에 category_definition 보완
  const toInsert          = [];  // food_types에만 있는 유효 신규 항목
  const matched           = new Set(); // 매칭된 f2 id

  for (const leaf of ftLeaves) {
    const root = getRootAncestor(leaf);
    if (!root) continue;

    const catNo     = root.code;
    const catRows   = f2ByCat[catNo] || [];

    // 유사 매칭 탐색
    const f2Match   = catRows.find(r => isSimilar(r.type_name, leaf.name));

    if (f2Match) {
      matched.add(f2Match.id);
      // type_code 보완
      if (!f2Match.type_code) {
        typeCodeUpdates.push({ id: f2Match.id, type_code: leaf.code });
      }
      // definition 보완 (f2가 null이고 food_types에 있으면)
      if (!f2Match.definition && leaf.definition) {
        defUpdates.push({ id: f2Match.id, definition: leaf.definition });
      }
    } else if (isValidNewItem(leaf.name)) {
      // food_types에만 있는 유효 항목 → 신규 추가
      toInsert.push({
        category_no:         catNo,
        category_name:       root.name,
        type_name:           leaf.name,
        type_code:           leaf.code,
        definition:          leaf.definition ?? null,
        category_definition: root.definition ?? null,
        source:              '식품공전 제5장',
      });
    }
  }

  // category_definition 보완: f2 행 중 category_definition이 null인 것 → food_types depth=0 정의 사용
  f2.forEach(r => {
    if (!r.category_definition) {
      const cat = d0ByCode[r.category_no];
      if (cat?.definition) {
        catDefUpdates.push({ id: r.id, category_definition: cat.definition });
      }
    }
  });

  const unmatchedF2 = f2.filter(r => !matched.has(r.id)).length;

  console.log(`\n[매칭 결과]`);
  console.log(`  양쪽 매칭: ${matched.size}개`);
  console.log(`  → type_code 추가 대상: ${typeCodeUpdates.length}건`);
  console.log(`  → definition 보완 대상: ${defUpdates.length}건`);
  console.log(`  → category_definition 보완 대상: ${catDefUpdates.length}건`);
  console.log(`  f2에만 있는 항목 (유지): ${unmatchedF2}개`);
  console.log(`  food_types에만 있는 신규 유효 항목: ${toInsert.length}개`);
  console.log(`  예상 최종 행 수: ${f2.length + toInsert.length}행`);

  if (DRY_RUN) {
    console.log('\n[신규 추가 샘플 (최대 10개)]:');
    toInsert.slice(0, 10).forEach(r =>
      console.log(`  [${r.category_no}] ${r.category_name} > ${r.type_name} (${r.type_code})`));
    console.log('\n[DRY-RUN 완료] 실제 적용하려면 --dry-run 없이 실행하세요.');
    return;
  }

  /* ── 5. type_code 컬럼 존재 확인 ── */
  const sampleRow = f2[0];
  if (sampleRow && !('type_code' in sampleRow)) {
    console.error('\n❌ type_code 컬럼이 없습니다. Supabase SQL Editor에서 먼저 실행하세요:');
    console.error('  ALTER TABLE f2_food_types ADD COLUMN IF NOT EXISTS type_code TEXT;');
    process.exit(1);
  }

  /* ── 6. type_code 업데이트 ── */
  console.log(`\ntype_code 업데이트 (${typeCodeUpdates.length}건)...`);
  let ok = 0;
  for (const u of typeCodeUpdates) {
    const { error } = await supabase.from('f2_food_types').update({ type_code: u.type_code }).eq('id', u.id);
    if (error) console.error('  ❌', u.id, error.message);
    else ok++;
    await sleep(50);
  }
  console.log(`  ✅ ${ok}/${typeCodeUpdates.length}`);

  /* ── 7. definition 보완 ── */
  console.log(`\ndefinition 보완 (${defUpdates.length}건)...`);
  ok = 0;
  for (const u of defUpdates) {
    const { error } = await supabase.from('f2_food_types').update({ definition: u.definition }).eq('id', u.id);
    if (error) console.error('  ❌', u.id, error.message);
    else ok++;
    await sleep(50);
  }
  console.log(`  ✅ ${ok}/${defUpdates.length}`);

  /* ── 8. category_definition 보완 ── */
  console.log(`\ncategory_definition 보완 (${catDefUpdates.length}건)...`);
  ok = 0;
  for (const u of catDefUpdates) {
    const { error } = await supabase.from('f2_food_types').update({ category_definition: u.category_definition }).eq('id', u.id);
    if (error) console.error('  ❌', u.id, error.message);
    else ok++;
    await sleep(50);
  }
  console.log(`  ✅ ${ok}/${catDefUpdates.length}`);

  /* ── 9. 신규 항목 삽입 ── */
  if (toInsert.length > 0) {
    console.log(`\n신규 항목 삽입 (${toInsert.length}건)...`);
    const BATCH = 50;
    let insOk = 0;
    for (let i = 0; i < toInsert.length; i += BATCH) {
      const batch     = toInsert.slice(i, i + BATCH);
      const { error } = await supabase.from('f2_food_types').insert(batch);
      if (error) console.error('  ❌ 배치', i, error.message);
      else { insOk += batch.length; console.log(`  ✅ ${Math.min(i + BATCH, toInsert.length)}/${toInsert.length}`); }
      await sleep(200);
    }
  }

  /* ── 10. 최종 확인 ── */
  const { count } = await supabase.from('f2_food_types').select('*', { count: 'exact', head: true });
  console.log(`\n${'='.repeat(55)}`);
  console.log(`[완료] f2_food_types 최종 행 수: ${count}행`);
  console.log(`\n⚠️  다음 단계 — food_types 삭제:`);
  console.log(`   Supabase SQL Editor에서 실행하세요:`);
  console.log(`   DROP TABLE food_types;`);
  console.log('='.repeat(55));
}

main().catch(console.error);
