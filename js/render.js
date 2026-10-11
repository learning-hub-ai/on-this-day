/* ============================================
   render.js — 只改 DOM
   ============================================
   职责：数据 → HTML。不取数，不绑事件。

   ⚠ 文本处理顺序不可错（spec.md §8.4）：
       escapeHtml  →  注音标记
     ① escapeHtml 必须最先：若先插标记再转义，自己插的标签会被转义成可见文本
     ② applyMarksSafe 的下标算在**原始文本**上，要求 escaped 文本与原文等长，
        所以这两步之间**不能**再插入任何标签 —— 见 renderEvent 的注释
   ============================================ */

import { applyMarksSafe } from './glossary.js';

const WIKI_BASE = 'https://zh.wikipedia.org/wiki/';

/**
 * 分类的显示顺序与图标。顺序与 scripts/tag_events.py 的 CATEGORIES 一致。
 *
 * ⚠ 图标只用 BMP 符号，不用 emoji —— 多数 Linux 环境未装 emoji 字体，
 *   星平面字符（U+1F680 等）会渲染成豆腐块。
 */
export const CATEGORY_ORDER = [
  ['航空航天', '✦'],
  ['科技', '✧'],
  ['政治', '◉'],
  ['军事', '◈'],
  ['文化艺术', '◇'],
  ['体育', '◎'],
  ['人物', '○'],
  ['其他', '·'],
];
const CATEGORY_ICON = new Map(CATEGORY_ORDER);

/** 当前选中的分类。null = 全部 */
let activeCategory = null;

const el = {
  heroDate: null, heroMeta: null,
  selectedList: null, selectedSection: null,
  eventsList: null, eventsSection: null, evtCount: null,
  emptyState: null, fetchDate: null, content: null, filterBar: null,
};

function dom() {
  if (el.heroDate) return el;
  el.heroDate = document.getElementById('heroDate');
  el.heroMeta = document.getElementById('heroMeta');
  el.selectedList = document.getElementById('selectedList');
  el.selectedSection = document.querySelector('.selected-section');
  el.eventsList = document.getElementById('eventsList');
  el.eventsSection = document.querySelector('.events-section');
  el.evtCount = document.getElementById('evtCount');
  el.emptyState = document.getElementById('emptyState');
  el.fetchDate = document.getElementById('fetchDate');
  el.content = document.querySelector('.content');
  el.filterBar = document.getElementById('filterBar');
  return el;
}

/**
 * HTML 转义。**所有**来自 API 的文本都必须过这里 ——
 * 第三方内容一律当不可信处理（spec.md §8.3）。
 */
export function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * 条目标题 → 维基 URL。
 * 数据里只存标题（标题 18 字节 vs 完整 URL 84 字节，spec.md §6.4），
 * URL 在此还原。
 *
 * ⚠ 标题里的下划线是维基 URL 的词间分隔符，**必须保留** ——
 *   `纵贯线_(台铁)` 去掉下划线就打不开了。
 */
export function wikiUrl(title) {
  return WIKI_BASE + encodeURIComponent(title);
}

/**
 * 条目标题 → 适合展示的文字。
 *
 * 维基用 `_(消歧义)` 后缀区分同名条目：`纵贯线_(台铁)`、
 * `圣荷西_(加利福尼亚州)`。实测全年有 1,763 处。
 * 直接显示会露出下划线这种 URL 内部结构，对读者是噪音 ——
 * 改成全角括号，并把下划线还原成空格。
 *
 * ⚠ 只改**显示**，URL 仍用原始标题（见 wikiUrl）。
 */
export function displayTitle(title) {
  return String(title ?? '')
    .replace(/_\((.+?)\)$/, '（$1）')   // _(台铁) → （台铁）
    .replace(/_/g, ' ');                 // 其余下划线还原为空格
}

/**
 * 年份显示。公元前用负数存储，显示成「前 622」而不是「-622」。
 * @param {number|null} y
 */
export function formatYear(y) {
  if (y === null || y === undefined) return '';
  return y < 0 ? `前 ${Math.abs(y)}` : String(y);
}

/** 月日显示，如 '10-09' → '10 月 9 日' */
export function formatDate(key) {
  const [m, d] = key.split('-').map(Number);
  return `${m} 月 ${d} 日`;
}

/**
 * 一条事件 → <li> HTML。
 * @param {Object} item   data/otd 的事件对象
 * @param {Object} words  词表
 * @param {boolean} isSelected 是否为维基精选
 *
 * ⚠ **正文里不做实体内链**，关联条目只在卡片底部成行列出。
 *   原因是下标冲突，不是偷懒：`applyMarksSafe` 的标记位置算在**原始文本**上，
 *   要求传入的 escaped 文本与原文等长（见 glossary.js 的注释）。
 *   一旦先插入 `<a>` 标签，长度就变了，注音会标到错位置、产出坏 HTML。
 *
 *   两种修法：(a) 实体与词表合并成一次扫描、统一算下标；
 *   (b) 正文只做注音，实体链接放底部。
 *   选 (b)：实体名往往很长（「朝鲜民主主义人民共和国」），
 *   正文内链会和注音虚线挤在一起，对六年级读者反而更乱。
 *   若将来要做 (a)，须把 findMarks 扩展成接受多种标记类型。
 */
function renderEvent(item, words, isSelected) {
  const raw = item.t || '';

  // 转义 → 注音。两步都在等长前提下操作，顺序见文件头
  const html = applyMarksSafe(raw, escapeHtml(raw), words);

  const others = (item.l || []).filter(Boolean);
  const classes = ['event'];
  if (isSelected) classes.push('event--selected');
  if (item.sensitive) classes.push('event--sensitive');

  const parts = [];
  if (item.tag && item.tag !== '其他') {
    const icon = CATEGORY_ICON.get(item.tag) || '';
    parts.push(`<p class="event-tag"><span aria-hidden="true">${icon}</span> ` +
               `${escapeHtml(item.tag)}</p>`);
  }
  parts.push(`<p class="event-text">${html}</p>`);

  if (item.why) {
    parts.push(`<p class="event-why">${escapeHtml(item.why)}</p>`);
  }
  if (item.sensitive) {
    parts.push('<p class="event-meta-row">' +
               '<span class="sensitive-badge">※ 建议和家长一起读</span></p>');
  }

  // 主链接：最能描述这件事的维基条目（gen_otd.pick_main_title 挑的）。
  // 单独一行、带「详细了解」字样 —— 底部那行关联条目是「延伸阅读」，
  // 两者作用不同，不能混在一起（spec.md §6.4b）
  if (item.u) {
    parts.push(
      `<p class="event-main-link"><a href="${wikiUrl(item.u)}"` +
      ` rel="noopener noreferrer" hreflang="zh">` +
      `详细了解：${escapeHtml(displayTitle(item.u))}` +
      `<span class="link-arrow" aria-hidden="true">›</span></a></p>`
    );
  }

  // 其余关联条目。u 与 l 都为空时不渲染（实测 3.1%，spec.md §6.4）
  if (others.length) {
    const links = others.map(t =>
      `<a class="entity-link" href="${wikiUrl(t)}"` +
      ` rel="noopener noreferrer" hreflang="zh">${escapeHtml(displayTitle(t))}</a>`
    ).join(' · ');
    parts.push('<p class="event-links">' +
               `<span class="links-mark" aria-hidden="true">·</span> ${links}</p>`);
  }

  return `<li class="${classes.join(' ')}">` +
         `<div class="event-year">${formatYear(item.y)}</div>` +
         `<article class="event-card">${parts.join('')}</article></li>`;
}

/**
 * 渲染领域筛选标签栏。
 *
 * **只显示当天实际存在的分类** —— 这是 spec.md §5.6 的核心教训：
 * 「筛掉一半内容的筛选器，比没有筛选器更坏」。让用户点进一个空页，
 * 他无法分辨「这天没有体育事件」与「分类器漏了」。
 * 空分类不渲染，问题就不存在。
 *
 * @param {Object} day   api.loadDay() 的结果
 * @param {string|null} active 当前选中分类
 */
function renderFilterBar(day, active) {
  const d = dom();
  if (!d.filterBar) return;

  const counts = new Map();
  for (const item of [...day.selected, ...day.events]) {
    const tag = item.tag || '其他';
    counts.set(tag, (counts.get(tag) || 0) + 1);
  }

  const total = day.selected.length + day.events.length;
  const chips = [
    `<button type="button" class="chip${active === null ? ' chip--on' : ''}"` +
    ` data-cat="" aria-pressed="${active === null}">全部` +
    `<span class="chip-n">${total}</span></button>`,
  ];

  for (const [cat, icon] of CATEGORY_ORDER) {
    const n = counts.get(cat);
    if (!n) continue;                 // 当天没有这一类 → 不渲染
    const on = active === cat;
    chips.push(
      `<button type="button" class="chip${on ? ' chip--on' : ''}"` +
      ` data-cat="${escapeHtml(cat)}" aria-pressed="${on}">` +
      `<span class="chip-i" aria-hidden="true">${icon}</span>` +
      `${escapeHtml(cat)}<span class="chip-n">${n}</span></button>`
    );
  }
  d.filterBar.innerHTML = chips.join('');
}

/** 按分类过滤。active 为 null 时原样返回 */
function filterByCategory(list, active) {
  if (!active) return list;
  return list.filter(it => (it.tag || '其他') === active);
}

/** 设置当前分类并重渲染。供 app.js 调用 */
export function setCategory(cat) {
  activeCategory = cat || null;
}

/** 当前分类 */
export function getCategory() {
  return activeCategory;
}

/** 渲染一整天。data 来自 api.loadDay()，永不为 null */
export function renderDay(day, words = {}) {
  const d = dom();

  d.heroDate.textContent = formatDate(day.key);
  if (day.generated) d.fetchDate.textContent = day.generated.slice(0, 7);

  if (day.isEmpty) {
    d.selectedSection.hidden = true;
    d.eventsSection.hidden = true;
    d.emptyState.hidden = false;
    d.heroMeta.textContent = '';
    if (d.filterBar) d.filterBar.innerHTML = '';
    return;
  }

  d.emptyState.hidden = true;
  renderFilterBar(day, activeCategory);

  const selected = filterByCategory(day.selected, activeCategory);
  const events = filterByCategory(day.events, activeCategory);

  d.heroMeta.textContent = activeCategory
    ? `${activeCategory} · 精选 ${selected.length} 条 · 其余 ${events.length} 条`
    : `维基精选 ${day.selected.length} 条 · 全部事件 ${day.events.length} 条`;

  d.selectedSection.hidden = selected.length === 0;
  d.selectedList.innerHTML =
    selected.map(it => renderEvent(it, words, true)).join('');

  d.eventsSection.hidden = events.length === 0;
  d.evtCount.textContent = String(events.length);
  d.eventsList.innerHTML =
    events.map(it => renderEvent(it, words, false)).join('');

  // 切换日期时时间轴淡入 180ms。不做整页淡出 ——
  // 那会让人以为在加载（layout.md §7.1）
  d.content.classList.remove('is-fading');
  void d.content.offsetWidth;        // 强制重排，让动画可重复触发
  d.content.classList.add('is-fading');
}

/** 加载态。数据多在本地，通常一闪而过 */
export function setLoading(on) {
  dom().content.classList.toggle('is-loading', !!on);
}
