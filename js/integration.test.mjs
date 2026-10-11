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
const { renderDay, escapeHtml } = await import('./render.js');
const { loadGlossary, findMarks } = await import('./glossary.js');

/* ============ api.js：真实 fetch ============ */
section('api.js — 真实取数');

const day = await loadDay('10-09');
ok(day.key === '10-09', 'key 正确');
ok(day.selected.length === 5, `selected 5 条`, `实际 ${day.selected.length}`);
ok(day.events.length === 41, `events 41 条`, `实际 ${day.events.length}`);
ok(day.isEmpty === false, 'isEmpty = false');
ok(day.total === 46, 'total = selected + events');
ok(typeof day.generated === 'string', 'generated 是字符串');

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
for (let m = 1; m <= 12; m++) {
  for (let d = 1; d <= daysInMonth(m); d++) {
    const key = toKey(m, d);
    const data = await loadDay(key);
    loaded++;
    if (data.isEmpty) emptyDays.push(key);
    for (const it of [...data.selected, ...data.events]) {
      if (typeof it.y !== 'number') badYear.push(`${key}:${it.t?.slice(0, 12)}`);
    }
  }
}
ok(loaded === 366, `366 天全部可载入`, `实际 ${loaded}`);
ok(emptyDays.length === 0, '无空白天', emptyDays.slice(0, 3).join(','));
ok(badYear.length === 0, '每条都有数字年份', badYear.slice(0, 3).join(','));

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
for (const sel of ['.selected-section', '.events-section', '.content']) {
  nodes[sel] = makeNode(sel);
}
globalThis.document = {
  getElementById: (id) => nodes[id] ?? null,
  querySelector: (sel) => nodes[sel] ?? null,
};

renderDay(day, words);

ok(nodes.heroDate.textContent === '10 月 9 日', '标题日期');
ok(nodes.heroMeta.textContent.includes('5') &&
   nodes.heroMeta.textContent.includes('41'), '副标题含条数');
ok(nodes.evtCount.textContent === '41', '折叠区计数');
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

console.log(`\n${'─'.repeat(44)}`);
console.log(`通过 ${pass} / 失败 ${fail}`);
process.exit(fail === 0 ? 0 : 1);
