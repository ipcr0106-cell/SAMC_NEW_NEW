/**
 * 원재료 동의어 사전
 * 원재료 영문/다국어 표기 → DB 키워드 매핑
 *
 * 1차: 이 사전으로 즉시 매칭 (비용 0원, 속도 즉시)
 * 2차: 사전에 없는 것만 LLM fallback (비용 발생, 느림)
 *
 * 소문자로 비교. 부분 매칭(includes) 사용.
 */

interface SynonymRule {
  db_keyword: string;
  rule: string;
  synonyms: string[];           // 정확 매칭 (소문자)
  partial_synonyms?: string[];  // 부분 매칭 (원재료에 이 문자열이 포함되면)
  exclude?: string[];           // 이 문자열이 포함되면 매칭 제외
  warning?: string;             // 매칭 시 추가 경고
  country_only?: string[];      // 이 국가일 때만 매칭
}

export const SYNONYM_RULES: SynonymRule[] = [

  // ── 연번 3: 복어 ──────────────────────────
  {
    db_keyword: "복어", rule: "연번3",
    synonyms: ["복어", "fugu", "pufferfish", "puffer fish", "blowfish", "globefish",
      "balloonfish", "swellfish", "toadfish", "河豚", "フグ", "ふぐ", "bogeo",
      "hétún", "tetraodontidae", "takifugu"],
    partial_synonyms: ["복어분말", "복어추출", "복어엑기스", "fugu extract"],
  },

  // ── 연번 10: 젤라틴 ────────────────────────
  {
    db_keyword: "젤라틴", rule: "연번10",
    synonyms: ["gelatin", "gelatine", "e441", "ins 441", "젤라틴", "ゼラチン",
      "明胶", "เจลาติน", "gélatine", "gelatina"],
    partial_synonyms: ["gelatin", "collagen hydrolysate", "hydrolyzed collagen",
      "collagen peptide", "fish gelatin", "bovine gelatin", "porcine gelatin"],
    warning: "젤라틴이 감지되었습니다. 원료 유래(소/돼지/어류)에 따라 필요 서류가 다릅니다. BSE 36개국 수출국인 경우 우피/소뼈 유래 구분이 필요합니다.",
  },

  // ── 연번 2: 반추동물/소 ────────────────────
  {
    db_keyword: "소", rule: "연번2",
    synonyms: ["beef", "bovine", "소고기", "쇠고기", "사골", "소뼈", "veal",
      "boeuf", "bœuf", "rind", "rindfleisch", "res", "carne de res",
      "manzo", "牛肉", "牛", "gyūniku", "เนื้อวัว", "ox"],
    partial_synonyms: ["beef extract", "beef broth", "beef powder", "소고기엑스",
      "사골분말", "사골엑기스", "소뼈분말", "bone broth"],
    exclude: ["beeswax"],
  },

  // ── 연번 2: 양 ─────────────────────────────
  {
    db_keyword: "양", rule: "연번2",
    synonyms: ["lamb", "mutton", "sheep", "ovine", "양고기", "agneau",
      "mouton", "cordero", "lamm", "hammelfleisch", "agnello",
      "montone", "羊肉", "ラム", "マトン", "เนื้อแกะ", "hogget"],
    partial_synonyms: ["lamb extract"],
  },

  // ── 연번 2: 사슴 ───────────────────────────
  {
    db_keyword: "사슴", rule: "연번2",
    synonyms: ["deer", "venison", "cervine", "사슴", "사슴고기",
      "cerf", "venaison", "ciervo", "hirsch", "cervo",
      "鹿肉", "シカ肉", "เนื้อกวาง", "elk", "reindeer"],
  },

  // ── 연번 14: 돼지원료 (ASF) ────────────────
  {
    db_keyword: "돼지원료", rule: "연번14",
    synonyms: ["pork", "ham", "bacon", "돼지고기", "돼지", "햄", "베이컨",
      "소시지", "sausage", "족발", "삼겹살", "porc", "jambon",
      "schweinefleisch", "schinken", "cerdo", "jamón",
      "maiale", "prosciutto", "豚肉", "猪肉", "หมู",
      "pancetta", "chorizo", "salami", "pepperoni", "guanciale"],
    partial_synonyms: ["pork extract", "pork flavor", "돼지뼈", "돼지갈비"],
    exclude: ["pork gelatin", "pork lard", "lard", "라드", "돼지기름",
      "돼지고기향", "pork flavoring", "porcine gelatin"],
  },

  // ── 연번 5: 꿀 (뉴질랜드) ──────────────────
  {
    db_keyword: "꿀", rule: "연번5",
    synonyms: ["honey", "꿀", "벌꿀", "소밀", "comb honey", "manuka",
      "마누카", "miel", "honig", "miele", "蜂蜜", "はちみつ",
      "น้ำผึ้ง", "raw honey", "acacia honey", "mel", "miód"],
    country_only: ["뉴질랜드"],
  },

  // ── 연번 8: 대마씨 ─────────────────────────
  {
    db_keyword: "대마씨", rule: "연번8",
    synonyms: ["hemp seed", "hemp seeds", "hemp heart", "hemp hearts",
      "hempseed", "대마씨", "삼씨", "헴프시드", "cannabis sativa seed",
      "chanvre", "graine de chanvre", "hanfsamen", "大麻籽", "麻の実",
      "hemp kernel", "hemp nut", "shelled hemp seed", "hulled hemp seed"],
    partial_synonyms: ["hemp seed oil", "hempseed oil"],
  },

  // ── 연번 1: 죽염/구운소금 ──────────────────
  {
    db_keyword: "죽염", rule: "연번1",
    synonyms: ["죽염", "bamboo salt", "jugyeom", "竹塩", "竹盐",
      "nine-times roasted bamboo salt", "9x bamboo salt",
      "korean bamboo salt"],
    partial_synonyms: ["bamboo salt"],
  },
  {
    db_keyword: "구운소금", rule: "연번1",
    synonyms: ["구운소금", "roasted salt", "baked salt", "fired salt",
      "guun sogeum"],
  },

  // ── 연번 4: 천일염 (중국) ──────────────────
  {
    db_keyword: "천일염", rule: "연번4",
    synonyms: ["천일염", "sea salt", "solar salt", "sel marin",
      "sel de mer", "meersalz", "sal marina", "sale marino",
      "天日塩", "海盐", "เกลือทะเล", "natural sea salt",
      "unrefined sea salt", "fleur de sel", "celtic sea salt"],
    country_only: ["중국"],
  },

  // ── 연번 12: 다진마늘 (중국) ───────────────
  {
    db_keyword: "다진마늘", rule: "연번12",
    synonyms: ["다진마늘", "minced garlic", "chopped garlic",
      "garlic paste", "crushed garlic", "garlic puree",
      "ground garlic", "ail haché", "蒜蓉", "蒜泥",
      "おろしにんにく", "กระเทียมสับ"],
    country_only: ["중국"],
  },

  // ── 연번 11: 파피씨드 ──────────────────────
  {
    db_keyword: "파피씨드", rule: "연번11",
    synonyms: ["poppy seed", "poppy seeds", "poppyseed", "파피씨드",
      "양귀비씨", "papaver somniferum", "mohn", "graines de pavot",
      "semillas de amapola", "罂粟籽", "ケシの実", "けしの実",
      "เมล็ดฝิ่น", "papaver"],
  },

  // ── 연번 9: 쥐치포 (베트남) ────────────────
  {
    db_keyword: "쥐치포", rule: "연번9",
    synonyms: ["쥐치포", "조미쥐치포", "쥐포", "filefish",
      "dried filefish", "file fish", "jwipo", "jwichi",
      "カワハギ", "kawahagi", "马面鱼", "filefish jerky",
      "filefish fillet", "leatherjacket", "leather jacket fish"],
    country_only: ["베트남"],
  },

  // ── 연번 7: 우지 (BSE 36개국) ──────────────
  {
    db_keyword: "우지가공품", rule: "연번7",
    synonyms: ["tallow", "beef tallow", "beef fat", "우지", "소기름",
      "suet", "dripping", "graisse de boeuf", "suif",
      "rindertalg", "sebo de res", "牛脂", "牛油",
      "edible tallow"],
  },

  // ── 연번 7-4: 제2인산칼슘 ──────────────────
  {
    db_keyword: "제2인산칼슘", rule: "연번7-4",
    synonyms: ["dicalcium phosphate", "dcp", "제2인산칼슘",
      "dibasic calcium phosphate", "calcium hydrogen phosphate",
      "e341ii", "ins 341(ii)"],
  },

  // ── 보관 2: 아마씨 ─────────────────────────
  {
    db_keyword: "아마씨", rule: "보관2",
    synonyms: ["flaxseed", "flax seed", "linseed", "lin seed",
      "아마씨", "flax", "linum usitatissimum",
      "graine de lin", "leinsamen", "linaza", "亚麻籽",
      "亜麻仁", "アマニ", "ground flaxseed", "flax meal"],
  },

  // ── 보관 7: 유산균 ─────────────────────────
  {
    db_keyword: "유산균", rule: "보관7",
    synonyms: ["lactobacillus", "probiotics", "probiotic", "유산균",
      "프로바이오틱스", "lactic acid bacteria",
      "bifidobacterium", "비피더스",
      "l. acidophilus", "l. casei", "l. rhamnosus", "l. plantarum",
      "l. bulgaricus", "l. reuteri", "b. longum", "b. lactis",
      "streptococcus thermophilus", "lacticaseibacillus",
      "lactiplantibacillus", "limosilactobacillus", "乳酸菌"],
  },

  // ── 보관 3: 프로폴리스 ─────────────────────
  {
    db_keyword: "프로폴리스추출물", rule: "보관3",
    synonyms: ["propolis", "프로폴리스", "bee propolis", "bee glue",
      "propolis extract", "propolis tincture",
      "própolis", "propóleos", "蜂胶", "プロポリス"],
  },

  // ── 보관 13: 남극크릴 ──────────────────────
  {
    db_keyword: "남극크릴", rule: "보관13",
    synonyms: ["krill", "antarctic krill", "krill oil", "크릴",
      "남극크릴", "euphausia superba", "krill extract",
      "krill meal", "オキアミ", "磷虾", "krill phospholipid"],
  },

  // ── 보관 9: 스피루리나 ─────────────────────
  {
    db_keyword: "스피루리나", rule: "보관9",
    synonyms: ["spirulina", "스피루리나", "arthrospira platensis",
      "arthrospira maxima", "blue-green algae", "spirulina powder",
      "phycocyanin", "spiruline", "espirulina", "螺旋藻", "スピルリナ"],
  },

  // ── 보관 9: 코엔자임Q10 ────────────────────
  {
    db_keyword: "코엔자임Q10", rule: "보관9",
    synonyms: ["coenzyme q10", "coq10", "ubiquinone", "ubiquinol",
      "ubidecarenone", "코엔자임q10", "코엔자임큐텐",
      "q10", "co q10", "コエンザイムq10", "辅酶q10", "coenzima q10"],
  },

  // ── 보관 9: EPA/DHA ────────────────────────
  {
    db_keyword: "EPA및DHA함유유지", rule: "보관9",
    synonyms: ["epa", "dha", "fish oil", "omega-3", "omega 3",
      "오메가3", "cod liver oil", "algal oil",
      "fish oil concentrate", "魚油", "鱼油", "น้ำมันปลา",
      "marine oil", "eicosapentaenoic acid", "docosahexaenoic acid"],
    partial_synonyms: ["fish oil", "n-3 fatty acid"],
  },

  // ── 보관 9: 가르시니아 ─────────────────────
  {
    db_keyword: "가르시니아캄보지아", rule: "보관9",
    synonyms: ["garcinia", "garcinia cambogia", "가르시니아",
      "가르시니아캄보지아", "hydroxycitric acid", "hca",
      "malabar tamarind", "brindle berry", "gambooge",
      "ガルシニア", "藤黄果"],
  },

  // ── 제8호: 축산물/동물성 식품 ──────────────
  {
    db_keyword: "축산물또는동물성식품", rule: "제8호",
    synonyms: ["milk", "butter", "cheese", "egg", "cream", "whey",
      "casein", "우유", "버터", "치즈", "계란", "크림", "유청",
      "카제인", "yogurt", "yoghurt", "ghee", "buttermilk",
      "lactose", "lactoferrin", "albumin", "ovalbumin",
      "lysozyme", "난백", "난황", "꿀", "honey",
      "카민", "carmine", "cochineal", "e120", "shellac", "셸락",
      "lait", "beurre", "fromage", "oeuf", "milch", "käse",
      "leche", "mantequilla", "queso", "huevo",
      "牛乳", "牛奶", "バター", "鸡蛋", "卵", "นม", "เนย", "ไข่",
      "whole milk powder", "skim milk powder", "whey protein",
      "sodium caseinate", "calcium caseinate", "rennet casein"],
    partial_synonyms: ["milk powder", "egg white", "egg yolk"],
  },

  // ── 제3호: GMO 대상 (콩) ───────────────────
  {
    db_keyword: "GMO", rule: "제3호-콩",
    synonyms: ["soy", "soybean", "soya", "soja", "대두", "콩",
      "soy protein", "soy protein isolate", "soy lecithin",
      "e322", "soybean oil", "soy flour", "soy sauce",
      "edamame", "tofu", "大豆", "豆腐", "醤油", "黄豆", "ถั่วเหลือง",
      "hydrolyzed soy protein", "textured soy protein",
      "tempeh", "miso", "natto"],
    partial_synonyms: ["soy ", "soja", "대두"],
  },

  // ── 제3호: GMO 대상 (옥수수) ───────────────
  {
    db_keyword: "GMO", rule: "제3호-옥수수",
    synonyms: ["corn", "maize", "옥수수", "zea mays",
      "corn starch", "cornstarch", "corn syrup",
      "high fructose corn syrup", "hfcs", "corn oil",
      "corn flour", "corn meal", "dextrose", "maltodextrin",
      "玉米", "トウモロコシ", "ข้าวโพด", "polenta"],
    partial_synonyms: ["corn ", "maize"],
  },

  // ── 제3호: GMO 대상 (카놀라) ───────────────
  {
    db_keyword: "GMO", rule: "제3호-카놀라",
    synonyms: ["canola", "canola oil", "rapeseed", "rapeseed oil",
      "카놀라", "colza", "huile de colza", "rapsöl",
      "菜種油", "油菜籽", "brassica napus"],
  },

  // ── 제3호: GMO 대상 (면실/사탕무/알팔파) ───
  {
    db_keyword: "GMO", rule: "제3호-기타",
    synonyms: ["cotton seed", "cottonseed", "면실",
      "sugar beet", "사탕무", "alfalfa", "알팔파"],
  },
];

/**
 * 원재료 목록을 동의어 사전으로 분석
 * @returns 감지된 DB 키워드 + 경고 + 매칭 안 된 원재료
 */
export function analyzeWithSynonyms(
  ingredients: string[],
  originCountry: string,
) {
  const detected: {
    db_keyword: string;
    source_ingredient: string;
    rule: string;
    confidence: "high" | "medium";
    reason: string;
  }[] = [];

  const warnings: string[] = [];
  const seenKeywords = new Set<string>();
  let unmatchedCount = 0;

  for (const ing of ingredients) {
    const ingLower = ing.toLowerCase().trim();
    let matched = false;

    for (const rule of SYNONYM_RULES) {
      // 국가 제한 체크
      if (rule.country_only && !rule.country_only.includes(originCountry)) continue;

      // 제외 키워드 체크
      if (rule.exclude?.some(ex => ingLower.includes(ex.toLowerCase()))) continue;

      // 정확 매칭
      const exactMatch = rule.synonyms.some(syn => ingLower === syn.toLowerCase());

      // 부분 매칭
      const partialMatch = !exactMatch && (
        rule.synonyms.some(syn => ingLower.includes(syn.toLowerCase())) ||
        rule.partial_synonyms?.some(ps => ingLower.includes(ps.toLowerCase()))
      );

      if (exactMatch || partialMatch) {
        if (!seenKeywords.has(rule.db_keyword)) {
          detected.push({
            db_keyword: rule.db_keyword,
            source_ingredient: ing,
            rule: rule.rule,
            confidence: exactMatch ? "high" : "medium",
            reason: `원재료 '${ing}'에서 ${exactMatch ? "정확 매칭" : "부분 매칭"} 감지`,
          });
          seenKeywords.add(rule.db_keyword);

          if (rule.warning) {
            warnings.push(rule.warning);
          }
        }
        matched = true;
        break; // 하나의 원재료는 하나의 규칙에만 매칭
      }
    }

    if (!matched) unmatchedCount++;
  }

  return { detected, warnings, unmatchedCount };
}
