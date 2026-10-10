/* ============================================
   api.js — 取数层
   ============================================
   职责：把「某一天」变成「可渲染的事件数据」。
   不碰 DOM，不做格式化 —— 那是 render.js 的事。

   三级回落（spec.md §3.3、§8.5）：
     data/otd/MM-DD.json  →  data/picks/MM-DD.json  →  空
   两者都有时合并，精选库优先。
   ============================================ */

/** 产物数据目录。换数据源只改这两行 */
const OTD_PATH = 'data/otd';
const PICKS_PATH = 'data/picks';

/** 已取到的天缓存在内存里 —— 来回切日期不重复请求 */
const _cache = new Map();

/**
 * 日期归一化为 'MM-DD'。
 * @param {number|string} month 1–12
 * @param {number|string} day   1–31
 * @returns {string} 例 '10-09'
 */
export function toKey(month, day) {
  const m = String(Number(month)).padStart(2, '0');
  const d = String(Number(day)).padStart(2, '0');
  return `${m}-${d}`;
}

/**
 * 今天的 'MM-DD'。
 *
 * ⚠ 必须用本地时区的 getMonth/getDate，**不能**用 toISOString() ——
 *   后者转 UTC，在东八区的凌晨 8 点前会少一天（spec.md §8.2）。
 */
export function todayKey() {
  const now = new Date();
  return toKey(now.getMonth() + 1, now.getDate());
}

/** 某月有多少天。按闰年算，所以 2 月恒为 29 —— 2/29 必须可查 */
export function daysInMonth(month) {
  return [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][Number(month) - 1];
}

/**
 * 读一个 JSON 文件。404 与网络错误都返回 null ——
 * 「这一天没有数据」是正常状态，不是异常（spec.md §3.3）。
 */
async function readJson(url) {
  try {
    const res = await fetch(url, { cache: 'no-cache' });
    return res.ok ? await res.json() : null;
  } catch {
    return null;         // 断网、CORS、JSON 解析失败一并归此
  }
}

/**
 * 合并两个来源的事件，精选库优先。
 *
 * 去重键是 `(y, t 前 12 字)` 而非全文 —— 精选库里的条目可能是
 * 维基文本的孩子向改写，全文比不上（spec.md §3.3）。
 */
function mergeGroup(wiki = [], picks = []) {
  const seen = new Set();
  const out = [];
  for (const item of [...picks, ...wiki]) {   // picks 先进，占住去重键
    const key = `${item.y}|${(item.t || '').slice(0, 12)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}

/** 年份升序。公元前是负数，所以直接数值比较即可 */
function byYear(a, b) {
  return (a.y ?? 0) - (b.y ?? 0);
}

/**
 * 取某一天的全部数据。
 *
 * @param {string} key 'MM-DD'
 * @returns {Promise<{key:string, selected:Array, events:Array,
 *                    total:number, isEmpty:boolean, generated:string|null}>}
 *          永不 reject —— 取不到数据时返回 isEmpty:true 的空结构。
 */
export async function loadDay(key) {
  if (_cache.has(key)) return _cache.get(key);

  const [wiki, picks] = await Promise.all([
    readJson(`${OTD_PATH}/${key}.json`),
    readJson(`${PICKS_PATH}/${key}.json`),   // 目录尚不存在 → null，走回落
  ]);

  const selected = mergeGroup(wiki?.selected, picks?.selected).sort(byYear);
  const events = mergeGroup(wiki?.events, picks?.events).sort(byYear);

  const day = {
    key,
    selected,
    events,
    total: selected.length + events.length,
    isEmpty: selected.length === 0 && events.length === 0,
    generated: wiki?.generated ?? null,
  };

  _cache.set(key, day);
  return day;
}

/** 清空内存缓存。仅供测试与开发时热重载用 */
export function clearCache() {
  _cache.clear();
}
