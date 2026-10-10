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

const el = {
  heroDate: null, heroMeta: null,
  selectedList: null, selectedSection: null,
  eventsList: null, eventsSection: null, evtCount: null,
  emptyState: null, fetchDate: null, content: null,
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
 */
export function wikiUrl(title) {
  return WIKI_BASE + encodeURIComponent(title);
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

  const titles = [item.u, ...(item.l || [])].filter(Boolean);
  const classes = ['event'];
  if (isSelected) classes.push('event--selected');
  if (item.sensitive) classes.push('event--sensitive');

  const parts = [`<p class="event-text">${html}</p>`];

  if (item.why) {
    parts.push(`<p class="event-why">${escapeHtml(item.why)}</p>`);
  }
  if (item.sensitive) {
    parts.push('<p class="event-meta-row">' +
               '<span class="sensitive-badge">⚑ 建议和家长一起读</span></p>');
  }
  // u 与 l 都为空时不渲染链接行 —— 实测 3.1% 的事件如此（spec.md §6.4）
  if (titles.length) {
    const links = titles.map(t =>
      `<a class="entity-link" href="${wikiUrl(t)}"` +
      ` rel="noopener noreferrer" hreflang="zh">${escapeHtml(t)}</a>`
    ).join(' · ');
    parts.push('<p class="event-links">' +
               `<span aria-hidden="true">🔗</span> ${links}</p>`);
  }

  return `<li class="${classes.join(' ')}">` +
         `<div class="event-year">${formatYear(item.y)}</div>` +
         `<article class="event-card">${parts.join('')}</article></li>`;
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
    return;
  }

  d.emptyState.hidden = true;
  d.heroMeta.textContent =
    `维基精选 ${day.selected.length} 条 · 全部事件 ${day.events.length} 条`;

  d.selectedSection.hidden = day.selected.length === 0;
  d.selectedList.innerHTML =
    day.selected.map(it => renderEvent(it, words, true)).join('');

  d.eventsSection.hidden = day.events.length === 0;
  d.evtCount.textContent = String(day.events.length);
  d.eventsList.innerHTML =
    day.events.map(it => renderEvent(it, words, false)).join('');

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
