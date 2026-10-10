/* ============================================
   glossary.js — 难词注音匹配
   ============================================
   纯函数模块，不碰 DOM。输入文本＋词表，输出标记位置。
   设计依据：docs/spec.md §6.2、§8.4

   为什么要最长优先：
   实测 2335 个候选词里有 1280 对存在包含关系
   （签署⊃署、合并⊃并、第一届⊃一届⊃届）。
   若不按最长优先，「签署」会被切成「署」，注释完全错位。
   ============================================ */

/** 一条事件最多标注几个词（spec.md §4.1 第 3 条）*/
export const MAX_MARKS_PER_EVENT = 3;

/**
 * 在文本中找出所有应标注的词的位置，最长优先、不重叠。
 *
 * @param {string} text  事件文本（已转简体）
 * @param {Object} words 词表 { 词: {p, d, n} }，来自 glossary.json 的 .words
 * @param {Object} [opts]
 * @param {number} [opts.max=MAX_MARKS_PER_EVENT] 最多返回几个，取文中最靠前的
 * @returns {Array<{start:number, end:number, word:string, p:string, d:string}>}
 *          按 start 升序排列，区间互不重叠
 *
 * 算法：在每个起始位置上，尝试从最长可能的词开始匹配（贪心最长优先）。
 * 命中后跳过整个词，保证不重叠。
 * 复杂度 O(n × L)，L 是词表中最长词的字数（实测 ≤4），对 41 条事件可忽略。
 */
export function findMarks(text, words, opts = {}) {
  const max = opts.max ?? MAX_MARKS_PER_EVENT;
  if (!text || !words) return [];

  // 词表中最长词的字数 —— 决定每个位置最多回看几个字
  let maxLen = 0;
  for (const w in words) if (w.length > maxLen) maxLen = w.length;
  if (maxLen === 0) return [];

  const marks = [];
  let i = 0;
  while (i < text.length) {
    let hit = null;
    // 最长优先：从 maxLen 递减，第一个命中的就是最长的
    for (let len = Math.min(maxLen, text.length - i); len >= 1; len--) {
      const cand = text.slice(i, i + len);
      if (Object.prototype.hasOwnProperty.call(words, cand)) {
        hit = { start: i, end: i + len, word: cand, ...words[cand] };
        break;
      }
    }
    if (hit) {
      marks.push(hit);
      i = hit.end;          // 跳过整个词，不重叠
    } else {
      i++;
    }
  }

  // 超出上限时取文中最靠前的 max 个（spec.md §6.2 第 5 条）
  return marks.slice(0, max);
}

/** escapeHtml 会改变长度的字符 —— 含这些字符的文本不做注音标记 */
const LENGTH_CHANGING = /[&<>"']/;

/**
 * HTML 转义。与 render.js 的 escapeHtml 等价 ——
 * 这里重复一份是为了让本模块保持**零依赖**，可被单独测试与复用。
 */
function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * 把标记应用到**已转义**的 HTML 片段上。
 *
 * ⚠ 调用顺序（spec.md §8.4）：escapeHtml → 本函数。
 *   两者之间**不能**插入任何标签，否则下标错位 —— 见 render.js 的注释。
 *
 * @param {string} escapedText 已经过 escapeHtml 的文本
 * @param {Array}  marks       findMarks 的返回值（基于**原始**文本的下标）
 * @returns {string} 含 <span class="gloss"> 的 HTML
 *
 * ⚠ 本函数要求 escapedText 与原文等长，即原文不含 & < > " ' ——
 *   由 applyMarksSafe 负责把关。
 */
export function applyMarks(escapedText, marks) {
  if (!marks.length) return escapedText;
  let out = '';
  let prev = 0;
  for (const m of marks) {
    out += escapedText.slice(prev, m.start);
    // 气泡内容来自 glossary.json（人工维护），但仍然转义 ——
    // 任何进入 innerHTML 的数据都当不可信处理，不因「自己写的」而豁免
    out +=
      '<span class="gloss" tabindex="0" aria-expanded="false">' +
      escapedText.slice(m.start, m.end) +
      `<span class="gloss-pop" role="tooltip">${esc(m.word)}` +
      `<em>${esc(m.p)}</em><br>${esc(m.d)}</span></span>`;
    prev = m.end;
  }
  out += escapedText.slice(prev);
  return out;
}

/**
 * 安全封装：文本含 HTML 特殊字符时跳过注音，避免下标错位。
 *
 * 这是刻意的取舍：注音是增强功能，错位会产出坏 HTML。
 * 宁可少注一条，不可标错位置。
 */
export function applyMarksSafe(rawText, escapedText, words, opts) {
  if (LENGTH_CHANGING.test(rawText)) return escapedText;
  return applyMarks(escapedText, findMarks(rawText, words, opts));
}

/** 加载词表，返回 .words 对象。失败时返回 {} —— 页面照常工作，只是不注音 */
export async function loadGlossary(url = 'data/glossary.json') {
  try {
    const res = await fetch(url);
    if (!res.ok) return {};
    const data = await res.json();
    return data.words || {};
  } catch {
    return {};
  }
}
