/* ============================================
   integration.test.mjs — 端到端验证
   ============================================
   在 Node 里跑完整的「取数 → 渲染」链路，用真实的 data/otd 文件
   和一个最小 DOM 替身。这是 glossary.test.mjs 覆盖不到的部分：
   api.js 的 fetch 路径、render.js 的 DOM 操作、三者的接缝。

   前提：先启动本地服务
       python3 serve.py 8750
   然后
       node js/integration.test.mjs

   为什么需要本地服务：api.js 用相对路径 fetch，
   Node 的 fetch 不接受相对 URL，所以这里把 base 指到本地服务 ——
   与浏览器里的行为一致。
   ============================================ */

const BASE = process.env.TEST_BASE || 'http://127.0.0.1:8750/';

// 把相对路径的 fetch 解析到本地服务，模拟浏览器的文档基地址
const nativeFetch = globalThis.fetch;
globalThis.fetch = (url, opts) => nativeFetch(new URL(url, BASE), opts);

let pass = 0, fail = 0;
function ok(cond, name, extra = '') {
  if (cond) { pass++; console.log(`  ✅ ${name}`); }
  else { fail++; console.log(`  ❌ ${name}${extra ? '  ' + extra : ''}`); }
}
function section(t) { console.log(`\n=== ${t} ===`); }

/* ---- 先确认服务在跑，否则后面的失败毫无意义 ---- */
try {
  const probe = await fetch('data/otd/10-09.json');
  if (!probe.ok) throw new Error(`HTTP ${probe.status}`);
} catch (e) {
  console.error(`\n无法连到 ${BASE} —— 请先运行：python3 serve.py 8750\n`);
  console.error(`(${e.message})`);
  process.exit(2);
}

const { loadDay, clearCache, toKey, daysInMonth } = await import('./api.js');
const { renderDay, escapeHtml, wikiUrl } = await import('./render.js');
const { loadGlossary, findMarks } = await import('./glossary.js');

/* ============ api.js：真实 fetch ============ */
section('api.js — 真实取数');

const day = await loadDay('10-09');
ok(day.key === '10-09', 'key 正确');
ok(day.selected.length === 5, `selected 5 条`, `实际 ${day.selected.length}`);
// events 已在生成期去重，不含精选（§6.5）—— 去重前是 41 条
ok(day.events.length === 38, `events 38 条（已去重）`, `实际 ${day.events.length}`);
ok(day.isEmpty === false, 'isEmpty = false');
ok(day.total === 43, 'total = selected + events');
ok(typeof day.generated === 'string', 'generated 是字符串');

// events 不得包含 selected 里的事件（§6.5）。不满足时同一条会在页面上
// 出现两次，且「其余 N 条」与实际卡片数对不上 —— 这是用户报的困惑来源。
{
  const norm = s => s.replace(/（图）/g, '');
  const selSet = new Set(day.selected.map(e => norm(e.t)));
  const dup = day.events.filter(e => selSet.has(norm(e.t)));
  ok(dup.length === 0, 'events 不含与精选重复的事件',
     dup.slice(0, 2).map(e => e.t.slice(0, 30)).join(' | '));
}

ok(day.events.every((e, i, a) => i === 0 || (a[i - 1].y ?? 0) <= (e.y ?? 0)),
   'events 按年份升序');
ok(day.selected.every((e, i, a) => i === 0 || (a[i - 1].y ?? 0) <= (e.y ?? 0)),
   'selected 按年份升序');

const leap = await loadDay('02-29');
ok(leap.selected.length > 0 && leap.events.length > 0, '2/29 有数据');

const missing = await loadDay('99-99');
ok(missing.isEmpty === true, '不存在的日期 → isEmpty（不抛错）');

// 缓存：第二次调用应返回同一对象引用
const again = await loadDay('10-09');
ok(again === day, '内存缓存命中（同一对象引用）');
clearCache();
const fresh = await loadDay('10-09');
ok(fresh !== day, 'clearCache 后重新取数');

/* ---- 全年扫一遍，确认没有坏文件 ---- */
section('api.js — 全年 366 天');
let loaded = 0, emptyDays = [], badYear = [];
let sensCount = 0, sensBadType = [], sensNoViolence = [];
let emptyMarks = [], filledTitles = 0, missingTag = [], tuMarks = [];
let filledNames = 0;
// 详情与事件一对一（§6.4f）：u 被 ≥4 个不同日期共用就不是「那天那件事」。
// demote_generic_links.py 负责降级；这里守住它别回来。
const uDates = new Map();
// 纯日期型条目标题不该当「详情」—— 读者点进去是整年大事记，
// 不是这件事。实测曾出现「居鲁士攻占巴比伦。详情：前539年」。
// 刻意不含「年表$」——「化學元素發現年表」是真条目，实测会误杀。
const DATEONLY_RE = /^(?:公元)?前?\d+年$|^\d+年代$|^(?:公元)?前?\d+世纪$|^\d+月\d+日$|^\d+年\d+月$|^(?:\d+年)?大事[记記]$/;
let dateLinks = [];
// 只认这几个暴力词 —— 用来反查「标了 sensitive 的条目正文里真有暴力内容」。
// 刻意比 tag_sensitive.py 的表短：测试要独立判断，不能照抄实现，
// 否则脚本错了测试也跟着错。
// 「焚城」是实跑后补的 —— 10-15「西关制造焚城大火，广州死亡上千人」
// 确实该标，是这份表漏了词，不是脚本误标。
// 第二批（枪手/袭击/爆炸/纵火/空袭/人质…）是脚本补词后同步的；
// 同一轮里这份表也抓出一条真误标：《告台湾同胞书》「停止…炮击」
// 讲的是停火，脚本已加豁免。
const VIOLENT_RE = /屠杀|刺杀|遇刺|行刺|暗杀|处决|枪决|枪杀|绞刑|火刑|断头台|问吊|杀害|杀死|自杀式|集中营|毒气|酷刑|强奸|轮奸|暴行|种族清洗|种族灭绝|大清洗|核试验|核爆|原子弹|斩首|凌迟|活埋|虐杀|殉情|自尽|服毒|切腹|灭门|焚城|枪手|枪击|扫射|枪战|恐怖|炸弹|爆炸|纵火|劫机|空袭|轰炸|炮击|炮轰|击落|袭击|人质|劫持|绑架|武装分子|开枪|持枪/;
for (let m = 1; m <= 12; m++) {
  for (let d = 1; d <= daysInMonth(m); d++) {
    const key = toKey(m, d);
    const data = await loadDay(key);
    loaded++;
    if (data.isEmpty) emptyDays.push(key);
    for (const it of [...data.selected, ...data.events]) {
      if (typeof it.y !== 'number') badYear.push(`${key}:${it.t?.slice(0, 12)}`);
      if (/《》|「」/.test(it.t)) emptyMarks.push(`${key}:${it.t.slice(0, 18)}`);
      // 「（图）」是维基的「见配图」标记，本站不显示图片 —— 死文本。
      // gen_otd.py 的 slim() 已在入口删除；这里守住它不再回来。
      if (it.t.includes('（图）')) tuMarks.push(`${key}:${it.t.slice(0, 18)}`);
      if (it.u && DATEONLY_RE.test(it.u)) dateLinks.push(`${key}:u=${it.u}`);
      const uDisp = it.ud || it.u;
      if (uDisp) {
        if (!uDates.has(uDisp)) uDates.set(uDisp, { dates: new Set(), years: new Set() });
        uDates.get(uDisp).dates.add(key);
        uDates.get(uDisp).years.add(it.y);
      }
      for (const l of it.l || []) {
        if (DATEONLY_RE.test(l)) dateLinks.push(`${key}:l=${l}`);
      }
      if (it.filled_title === true) filledTitles++;
      if (it.filled_name === true) filledNames++;
      if ('sensitive' in it) {
        sensCount++;
        // 只允许 true —— false/0/'' 这类假值会让前端判断变微妙
        if (it.sensitive !== true) sensBadType.push(`${key}:${it.sensitive}`);
        if (!VIOLENT_RE.test(it.t)) sensNoViolence.push(`${key}:${it.t.slice(0, 20)}`);
      }
      // tag 必须存在 —— 它由 tag_events.py 写入，而补全正文会改变配对
      // 前缀，实测 11-16 补全后 tag 就空了（分类筛选栏会少一条）。
      // 流程要求：改完正文必须重跑 tag_events.py。
      if (!it.tag) missingTag.push(`${key}:${it.t.slice(0, 18)}`);
    }
  }
}
ok(loaded === 366, `366 天全部可载入`, `实际 ${loaded}`);
ok(emptyDays.length === 0, '无空白天', emptyDays.slice(0, 3).join(','));
ok(badYear.length === 0, '每条都有数字年份', badYear.slice(0, 3).join(','));
ok(sensCount > 0, `有条目标了 sensitive（${sensCount} 条，§4.3）`, '一条都没标');
ok(sensBadType.length === 0, 'sensitive 只用 true，不用假值',
   sensBadType.slice(0, 3).join(','));
ok(sensNoViolence.length === 0, '标了 sensitive 的正文确有暴力内容（无误标）',
   sensNoViolence.slice(0, 3).join(' | '));

// 空书名号《》/「」—— 已补 24 条，剩 5 条无法可靠复原（§10.1）。
// 断言「不超过 5」而不是「等于 0」：增加说明有新残缺或补全被冲掉。
ok(emptyMarks.length <= 5,
   `空书名号残缺 ${emptyMarks.length} 条（已知上限 5）`,
   emptyMarks.slice(0, 6).join(' | '));
ok(filledNames === 11,
   `补回的人名仍在（${filledNames} 条，带 filled_name 标志）`,
   `实际 ${filledNames} 条 —— 少了说明 gen_otd.py 重跑把补名冲掉了（§10.1e）`);
ok(filledTitles === 24,
   `补全的标题仍在（${filledTitles} 条，带 filled_title 标志）`,
   `实际 ${filledTitles} 条 —— 少了说明 gen_otd.py 重跑把补全冲掉了`);
ok(missingTag.length === 0,
   '每条都有 tag（改过正文要重跑 tag_events.py）',
   missingTag.slice(0, 4).join(' | '));
ok(tuMarks.length === 0,
   '正文无「（图）」死文本（§10.1d）',
   tuMarks.slice(0, 4).join(' | '));
ok(dateLinks.length === 0,
   '详情与关联条目都不是纯日期型标题（§6.4e）',
   dateLinks.slice(0, 5).join(' | '));
const generic = [...uDates.entries()]
  .filter(([, v]) => v.years.size > 1 && v.dates.size >= 4)
  .map(([u, v]) => `${u}(${v.dates.size}天/${v.years.size}年)`);
ok(generic.length === 0,
   '详情与事件一对一：没有跨年且被 ≥4 个日期共用的 u（§6.4f）',
   generic.slice(0, 5).join(' | '));

/* ============ glossary.js：真实词表 ============ */
section('glossary.js — 真实词表');
const words = await loadGlossary();
const wordCount = Object.keys(words).length;
ok(wordCount > 0, `词表载入（${wordCount} 词）`);

const sample = '朝鲜民主主义人民共和国在咸镜北道舞水端里进行首次核试验，引来国际社会的普遍谴责。';
const marks = findMarks(sample, words);
ok(marks.length > 0, '真实文本能命中词表', JSON.stringify(marks.map(m => m.word)));
ok(marks.length <= 3, '不超过 3 个标记');
ok(marks.every(m => m.p && m.d), '每个标记带拼音与释义');

/* ============ render.js：最小 DOM 替身 ============ */
section('render.js — DOM 渲染');

/** 最小 DOM：只实现 render.js 实际用到的那几个属性 */
function makeNode(id) {
  return {
    id, _html: '', _text: '', hidden: false,
    set innerHTML(v) { this._html = v; },
    get innerHTML() { return this._html; },
    set textContent(v) { this._text = v; },
    get textContent() { return this._text; },
    offsetWidth: 0,
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); },
      remove(c) { this._s.delete(c); },
      toggle(c, on) { on ? this._s.add(c) : this._s.delete(c); },
      contains(c) { return this._s.has(c); },
    },
  };
}
const nodes = {};
for (const id of ['heroDate', 'heroMeta', 'selectedList', 'eventsList',
                  'evtCount', 'emptyState', 'fetchDate']) {
  nodes[id] = makeNode(id);
}
for (const id of ['filterBar', 'evtToggle', 'sourceLink']) { nodes[id] = makeNode(id); }
// evtToggle 需要 aria 属性读写
nodes.evtToggle._attrs = {};
nodes.evtToggle.setAttribute = function (k, v) { this._attrs[k] = v; };
nodes.evtToggle.getAttribute = function (k) { return this._attrs[k] ?? null; };
for (const sel of ['.selected-section', '.events-section', '.content']) {
  nodes[sel] = makeNode(sel);
}
globalThis.document = {
  getElementById: (id) => nodes[id] ?? null,
  querySelector: (sel) => nodes[sel] ?? null,
};

renderDay(day, words);

ok(nodes.heroDate.textContent === '10 月 9 日', '标题日期');
// 文案须把三个数都写出来且加得起来（§6.5）。
// 两次文案演进都由用户反馈驱动：
//   「全部事件 41 条」—— 歧义：听起来是所有，但页面上有 46 张卡片
//   「… 其余 32 条 · 共 37 条」—— 数对上了，但「其余」偏书面、预设前提
//   现版「共 43 条 · 维基精选 5 条 · 更多 38 条」—— 总数前置，不必做加法
//   10-09 从 39 降到 38：删掉「（图）」后，精选的「社会活动家遭到…刺杀未遂」
//   与 events 里同一条变成**完全相同**，被 §6.5 去重正确移除。
ok(nodes.heroMeta.textContent.includes('5 条') &&
   nodes.heroMeta.textContent.includes('38 条') &&
   nodes.heroMeta.textContent.includes('43 条'),
   '副标题含合计/精选/更多三个数', nodes.heroMeta.textContent);
ok(nodes.heroMeta.textContent.indexOf('共 43 条') === 0,
   '合计数前置（用户最想知道的数放最前）', nodes.heroMeta.textContent);
ok(!nodes.heroMeta.textContent.includes('全部事件'),
   '副标题不再使用有歧义的「全部事件」');
// 「其他」是八个分类之一，不能同时用作折叠区标题 —— 会撞义
ok(!nodes.heroMeta.textContent.includes('其他'),
   '副标题不使用与分类名撞义的「其他」');
ok(nodes.evtCount.textContent === '38', '折叠区计数等于更多事件条数');
ok(nodes.emptyState.hidden === true, '空状态隐藏');

const html = nodes.selectedList.innerHTML;
ok(html.includes('<li class="event event--selected"'), '精选条目带 modifier 类');
ok(html.includes('class="event-year"'), '渲染年份');
ok(html.includes('class="event-card"'), '渲染卡片');
ok(html.includes('rel="noopener noreferrer"'), '外链带 noopener');
ok(!html.includes('<script'), '无脚本注入');
ok(nodes['.content'].classList.contains('is-fading'), '触发淡入动画');

// 公元前年份。01-01 的 selected 里有公元前 45 年（儒略历）
const bc = await loadDay('01-01');
const hasBC = [...bc.selected, ...bc.events].some(e => e.y < 0);
ok(hasBC, '01-01 含公元前事件（测试前提）');
renderDay(bc, words);
const allHtml = nodes.selectedList.innerHTML + nodes.eventsList.innerHTML;
ok(allHtml.includes('>前 '), '公元前显示「前 N」');
ok(!/class="event-year">-/.test(allHtml), '年份处不显示负号');

// 空状态
renderDay({ key: '01-01', selected: [], events: [], total: 0,
            isEmpty: true, generated: null }, words);
ok(nodes.emptyState.hidden === false, '空数据时显示空状态');
ok(nodes['.selected-section'].hidden === true, '空数据时隐藏精选区');

// sensitive 的渲染（§4.3）—— 标了要出现陪读提示，没标不能出现
const sensItem = { y: 1945, t: '某地发生屠杀，造成多人死亡。', src: 'wiki',
                   sensitive: true };
renderDay({ key: '01-01', selected: [sensItem], events: [], total: 1,
            isEmpty: false, generated: null }, words);
const sensHtml = nodes.selectedList.innerHTML;
ok(sensHtml.includes('event--sensitive'), 'sensitive 条目加 event--sensitive 类');
ok(sensHtml.includes('建议和家长一起读'), 'sensitive 条目显示陪读提示');

const plainItem = { y: 1945, t: '某地举行会议。', src: 'wiki' };
renderDay({ key: '01-01', selected: [plainItem], events: [], total: 1,
            isEmpty: false, generated: null }, words);
const plainHtml = nodes.selectedList.innerHTML;
ok(!plainHtml.includes('event--sensitive'), '未标的条目不加 sensitive 类');
ok(!plainHtml.includes('建议和家长一起读'), '未标的条目不显示陪读提示');

/* ============ 转义与注音的接缝 ============ */
section('render × glossary 接缝');

// 含 & 的事件应跳过注音，但仍要正确转义
const tricky = { y: 2000, t: '签署 A&B 条约', src: 'wiki', u: '条约' };
renderDay({ key: '01-01', selected: [tricky], events: [], total: 1,
            isEmpty: false, generated: '2026-10-10' }, words);
const t = nodes.selectedList.innerHTML;
ok(t.includes('A&amp;B'), '& 已转义');
ok(!t.includes('class="gloss"'), '含 & 的文本跳过注音（避免下标错位）');

// 不含特殊字符时应正常注音
const plain = { y: 2000, t: '两国签署条约', src: 'wiki', u: '条约' };
renderDay({ key: '01-01', selected: [plain], events: [], total: 1,
            isEmpty: false, generated: '2026-10-10' }, words);
ok(nodes.selectedList.innerHTML.includes('class="gloss"'), '正常文本有注音');

// XSS：事件文本里的标签必须被转义
const evil = { y: 2000, t: '<img src=x onerror=alert(1)>', src: 'wiki' };
renderDay({ key: '01-01', selected: [evil], events: [], total: 1,
            isEmpty: false, generated: '2026-10-10' }, words);
const e = nodes.selectedList.innerHTML;
ok(e.includes('&lt;img'), 'XSS：标签已转义');
ok(!e.includes('<img'), 'XSS：无活动标签');

/* ============ app.js：纯函数 ============ */
section('app.js — 日期解析与翻页');

const { parseKey, shiftDay } = await import('./app.js');

ok(JSON.stringify(parseKey('10-09')) === JSON.stringify({ month: 10, day: 9 }),
   'parseKey 正常');
ok(JSON.stringify(parseKey('02-29')) === JSON.stringify({ month: 2, day: 29 }),
   'parseKey 接受 2/29（按闰年）');
ok(parseKey('02-30') === null, 'parseKey 拒绝 2/30');
ok(parseKey('04-31') === null, 'parseKey 拒绝 4/31');
ok(parseKey('13-01') === null, 'parseKey 拒绝 13 月');
ok(parseKey('00-01') === null, 'parseKey 拒绝 0 月');
ok(parseKey('abc') === null, 'parseKey 拒绝乱码');
ok(parseKey('') === null, 'parseKey 拒绝空串');
ok(parseKey(null) === null, 'parseKey 拒绝 null');
ok(parseKey('1-9') === null, 'parseKey 要求补零');

ok(shiftDay('10-09', 1) === '10-10', 'shiftDay 次日');
ok(shiftDay('10-09', -1) === '10-08', 'shiftDay 前日');
ok(shiftDay('10-31', 1) === '11-01', 'shiftDay 跨月');
ok(shiftDay('03-01', -1) === '02-29', 'shiftDay 跨到 2/29');
ok(shiftDay('02-29', 1) === '03-01', 'shiftDay 2/29 次日');
ok(shiftDay('12-31', 1) === '01-01', 'shiftDay 跨年回绕');
ok(shiftDay('01-01', -1) === '12-31', 'shiftDay 跨年回绕（反向）');
ok(shiftDay('bad', 1) === 'bad', 'shiftDay 非法输入原样返回');

// 翻页一整年应回到原点 —— 回绕逻辑的闭环检验
let k = '01-01';
for (let i = 0; i < 366; i++) k = shiftDay(k, 1);
ok(k === '01-01', '连翻 366 天回到原点');

/* ============ 领域筛选 ============ */
section('领域筛选');

const { setCategory, getCategory, CATEGORY_ORDER, displayTitle } = await import('./render.js');

// 每条事件都该有 tag
const tagged = [...day.selected, ...day.events];
ok(tagged.every(e => typeof e.tag === 'string'), '每条事件都有 tag 字段');
const validTags = new Set(CATEGORY_ORDER.map(([c]) => c));
ok(tagged.every(e => validTags.has(e.tag)),
   'tag 都是合法分类', [...new Set(tagged.map(e => e.tag))].join(','));

// 全部视图
setCategory(null);
renderDay(day, words);
const allCount = (nodes.selectedList.innerHTML.match(/<li class="event/g) || []).length
               + (nodes.eventsList.innerHTML.match(/<li class="event/g) || []).length;
ok(allCount === day.total, `全部视图渲染 ${day.total} 条`, `实际 ${allCount}`);
ok(nodes['filterBar'].innerHTML.includes('chip--on'), '「全部」默认选中');
ok(nodes['filterBar'].innerHTML.includes('data-cat=""'), '有「全部」标签');

// 挑一个当天实有的分类来筛
const counts = new Map();
for (const e of tagged) counts.set(e.tag, (counts.get(e.tag) || 0) + 1);
const [someCat, someN] = [...counts].find(([c]) => c !== '其他') || [];
ok(someCat !== undefined, `当天有可筛分类（${someCat}）`);

setCategory(someCat);
renderDay(day, words);
const filtered = (nodes.selectedList.innerHTML.match(/<li class="event/g) || []).length
               + (nodes.eventsList.innerHTML.match(/<li class="event/g) || []).length;
ok(filtered === someN, `筛选 ${someCat} 得 ${someN} 条`, `实际 ${filtered}`);
ok(filtered < day.total, '筛选后少于全部');
ok(nodes.heroMeta.textContent.includes(someCat), '副标题显示当前分类');

// 空分类不渲染标签 —— §5.6 的核心保证
const bar = nodes['filterBar'].innerHTML;
for (const [cat] of CATEGORY_ORDER) {
  if (!counts.has(cat)) {
    ok(!bar.includes(`data-cat="${cat}"`), `空分类「${cat}」不出现在标签栏`);
    break;
  }
}
// 标签栏里每个分类的计数都 > 0
const shown = [...bar.matchAll(/data-cat="([^"]+)"/g)].map(m => m[1]);
ok(shown.every(c => (counts.get(c) || 0) > 0),
   '标签栏里每个分类当天都有事件');

setCategory(null);   // 还原，免得影响后续断言

/* ============ 事件主链接 ============ */
section('事件主链接');

// 每条有 u 的事件都该渲染「详情」行
setCategory(null);
renderDay(day, words);
const bothHtml = nodes.selectedList.innerHTML + nodes.eventsList.innerHTML;
const withU = [...day.selected, ...day.events].filter(e => e.u).length;
const mainLinks = (bothHtml.match(/class="event-main-link"/g) || []).length;
ok(mainLinks === withU, `有 u 的 ${withU} 条都渲染了主链接`, `实际 ${mainLinks}`);
// u 是刻意保守的：只在能确认条目描述这件事时才给（§6.4b）。
// 所以多数事件没有主链接，只在底部列关联条目 —— 这是设计，不是缺陷
ok(withU < day.total, `主链接是可选的（${withU}/${day.total} 条有）`);
if (withU) ok(bothHtml.includes('详情：'), '主链接带「详情」字样');

// 主链接必须指向真实维基 URL
const hrefs = [...bothHtml.matchAll(/class="event-main-link"><a href="([^"]+)"/g)]
  .map(m => m[1]);
ok(hrefs.length === withU, `抓到 ${withU} 个主链接 href`);
// /zh-cn/ 而非 /wiki/ —— 标题保持维基原样（可能繁体，否则 404），
// 由这个路径前缀让目标页以简体呈现
ok(hrefs.every(h => h.startsWith('https://zh.wikipedia.org/zh-cn/')),
   '主链接指向中文维基的简体变体路径');
ok(hrefs.every(h => !h.includes(' ')), '主链接已 URL 编码');

// 外链必须新开页 —— 点进去就离开本站，不该顶掉当前日期
const anchors = [...bothHtml.matchAll(/<a\b[^>]*>/g)].map(m => m[0]);
ok(anchors.length > 0, `抓到 ${anchors.length} 个链接`);
ok(anchors.every(a => a.includes('target="_blank"')),
   '所有外链带 target="_blank"',
   anchors.filter(a => !a.includes('target="_blank"'))[0] || '');
// target="_blank" 必须配 noopener：否则新页面能通过 window.opener 操作本页
ok(anchors.every(a => a.includes('rel="noopener noreferrer"')),
   '所有外链带 rel="noopener noreferrer"');

// u 不该重复出现在关联条目行里 —— 那会是同一个链接点两次
const dupes = [...day.selected, ...day.events]
  .filter(e => e.u && (e.l || []).includes(e.u)).length;
ok(dupes === 0, 'u 不与 l 重复', `重复 ${dupes} 条`);

// 消歧义后缀：显示用全角括号，URL 仍用原标题
ok(displayTitle('纵贯线_(台铁)') === '纵贯线（台铁）', '消歧义后缀转全角括号');
ok(displayTitle('海卫一') === '海卫一', '普通标题不变');
ok(wikiUrl('纵贯线_(台铁)').includes(encodeURIComponent('纵贯线_(台铁)')),
   'URL 保留原始下划线标题');

// 繁体标题必须原样进 URL —— 转成简体那个条目就不存在了（实测 18% 失效）
ok(wikiUrl('市場花園行動').includes(encodeURIComponent('市場花園行動')),
   '繁体标题原样进 URL');
const tradTitled = [...day.selected, ...day.events].filter(e => e.ud);
if (tradTitled.length) {
  const e0 = tradTitled[0];
  ok(e0.ud !== e0.u, 'ud 是 u 的简体变体，两者不同');
  renderDay({ key: '01-01', selected: [e0], events: [], total: 1,
              isEmpty: false, generated: '2026-10-10' }, words);
  const h0 = nodes.selectedList.innerHTML;
  ok(h0.includes(encodeURIComponent(e0.u)), 'href 用原标题（繁体）');
  ok(h0.includes(e0.ud), '显示用简体变体');
} else {
  console.log('  ⓘ 当天无繁体标题事件，跳过');
}
// 只检查**可见文字**，不检查 href —— URL 里的下划线是必需的
const visibleText = bothHtml.replace(/href="[^"]*"/g, '');
ok(!visibleText.includes('_('), '可见文字里不出现裸的 _( 后缀');
ok(bothHtml.includes('%29') || bothHtml.includes('_('),
   'href 里仍保留消歧义后缀（URL 需要它）');

// 无 u 也无 l 的事件（实测 3.1%）不该渲染任何链接行
const noLink = [...day.selected, ...day.events].filter(e => !e.u && !e.l);
if (noLink.length) {
  renderDay({ key: '01-01', selected: [noLink[0]], events: [], total: 1,
              isEmpty: false, generated: '2026-10-10' }, words);
  const h = nodes.selectedList.innerHTML;
  ok(!h.includes('event-main-link') && !h.includes('event-links'),
     '无链接的事件不渲染链接行');
} else {
  console.log('  ⓘ 当天没有无链接事件，跳过');
}

setCategory(null);

/* ============ 精选为空时自动展开 ============ */
section('精选为空时自动展开更多事件');

const { setEventsExpanded, isEventsExpanded } = await import('./render.js');

// 有精选时：默认收起
setCategory(null);
setEventsExpanded(false);
renderDay(day, words);
ok(day.selected.length > 0, '测试前提：当天有精选');
ok(isEventsExpanded() === false, '有精选时「更多事件」保持收起');
ok(nodes.eventsList.hidden === true, 'eventsList 已隐藏');

// 构造「精选为空但有其余事件」的情形
setEventsExpanded(false);
renderDay({ key: '01-01', selected: [], events: day.events,
            total: day.events.length, isEmpty: false,
            generated: '2026-10-10' }, words);
ok(isEventsExpanded() === true, '精选为空时自动展开');
ok(nodes.eventsList.hidden === false, 'eventsList 已显示');
ok(nodes.selectedSection === undefined ||
   nodes['.selected-section'].hidden === true, '精选区隐藏');

// 按分类筛到「只有非精选事件」时也该自动展开 —— 这是真实场景
const catOnlyInEvents = [...new Set(day.events.map(e => e.tag))]
  .find(c => !day.selected.some(s => s.tag === c));
if (catOnlyInEvents) {
  setEventsExpanded(false);
  setCategory(catOnlyInEvents);
  renderDay(day, words);
  ok(isEventsExpanded() === true,
     `筛到「${catOnlyInEvents}」（只存在于非精选）时自动展开`);
  setCategory(null);
} else {
  console.log('  ⓘ 当天无此类分类，跳过');
}

// 两者都空：显示空状态，不该去展开
setEventsExpanded(false);
renderDay({ key: '01-01', selected: [], events: [], total: 0,
            isEmpty: true, generated: null }, words);
ok(isEventsExpanded() === false, '完全无数据时不展开（走空状态）');
ok(nodes.emptyState.hidden === false, '显示空状态');

/* ============ 日期出处 ============ */
section('日期出处链接');

setCategory(null);
renderDay(day, words);
ok(nodes.sourceLink !== undefined, 'sourceLink 节点存在');
ok(nodes.sourceLink.href === 'https://zh.wikipedia.org/zh-cn/' +
   encodeURIComponent('10月9日'),
   '出处链接指向维基「10月9日」条目', nodes.sourceLink.href);
ok(nodes.sourceLink.textContent.includes('10月9日'), '出处文字含日期');

// 换一天应该跟着变 —— 否则会把 A 日的事件归到 B 日的出处上
const other = await loadDay('02-29');
renderDay(other, words);
ok(nodes.sourceLink.href.includes(encodeURIComponent('2月29日')),
   '切换日期后出处链接同步更新', nodes.sourceLink.href);

renderDay(day, words);   // 还原

console.log(`\n${'─'.repeat(44)}`);
console.log(`通过 ${pass} / 失败 ${fail}`);
process.exit(fail === 0 ? 0 : 1);
