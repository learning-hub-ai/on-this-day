/* ============================================
   app.js — 入口与事件绑定
   ============================================
   职责：把 URL／下拉框／按钮的「用户意图」翻译成一次 loadDay + render。
   不取数（api.js）、不拼 HTML（render.js）。

   新增一个入口（比如键盘左右箭头翻页）只需在 bindEvents 里加一行，
   然后调 show(key) —— 所有入口都收敛到这一个函数。
   ============================================ */

import { toKey, todayKey, daysInMonth, loadDay } from './api.js';
import { renderDay, setLoading } from './render.js';
import { loadGlossary } from './glossary.js';

const MONTHS = ['一', '二', '三', '四', '五', '六',
                '七', '八', '九', '十', '十一', '十二'];

const el = {};          // 缓存 DOM 查询结果
let glossary = {};      // 词表，空对象也能正常工作（spec.md §6.2 第 2 条）

/** 把 'MM-DD' 拆成数字 {m, d}；非法输入返回 null */
function parseKey(key) {
  const m = /^(\d{2})-(\d{2})$/.exec(key || '');
  if (!m) return null;
  const month = Number(m[1]);
  const day = Number(m[2]);
  if (month < 1 || month > 12) return null;
  if (day < 1 || day > daysInMonth(month)) return null;
  return { month, day };
}

/**
 * 决定首屏显示哪一天：URL hash 优先，否则今天。
 * hash 形式 `#10-09`，这样一天的内容可以被分享与收藏。
 */
function initialKey() {
  const fromHash = parseKey(location.hash.replace(/^#/, ''));
  return fromHash ? toKey(fromHash.month, fromHash.day) : todayKey();
}

/** 填充月份下拉（12 项，内容固定，只填一次）*/
function fillMonths() {
  el.selMonth.innerHTML = MONTHS
    .map((name, i) => `<option value="${i + 1}">${name}月</option>`)
    .join('');
}

/**
 * 填充日期下拉。月份变化时要重填，因为天数不同。
 * 保留当前选中日；若新月份没有该日（如 3/31 → 4 月），落到当月最后一天。
 */
function fillDays(month, keepDay) {
  const max = daysInMonth(month);
  const target = Math.min(Number(keepDay) || 1, max);
  el.selDay.innerHTML = Array.from({ length: max }, (_, i) =>
    `<option value="${i + 1}">${i + 1}日</option>`).join('');
  el.selDay.value = String(target);
  return target;
}

/**
 * 核心流程：所有入口最终都调这里。
 * @param {string} key 'MM-DD'
 * @param {boolean} [pushHash=true] 是否写入 URL hash
 */
async function show(key, pushHash = true) {
  const parsed = parseKey(key);
  if (!parsed) return;                  // 非法 key 静默忽略，不破坏当前视图

  el.selMonth.value = String(parsed.month);
  fillDays(parsed.month, parsed.day);

  if (pushHash && location.hash.replace(/^#/, '') !== key) {
    // replaceState 而非 pushState —— 翻日期不该堆满浏览器历史
    history.replaceState(null, '', `#${key}`);
  }

  setLoading(true);
  const day = await loadDay(key);
  setLoading(false);
  renderDay(day, glossary);
}

/** 当前下拉框选中的日期 */
function keyFromSelects() {
  return toKey(el.selMonth.value, el.selDay.value);
}

function bindEvents() {
  el.selMonth.addEventListener('change', () => {
    fillDays(el.selMonth.value, el.selDay.value);
    show(keyFromSelects());
  });

  el.selDay.addEventListener('change', () => show(keyFromSelects()));

  el.btnToday.addEventListener('click', () => show(todayKey()));

  // 空状态里的「回到今天」—— 用委托，因为该按钮可能被重渲染
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action="today"]');
    if (btn) show(todayKey());
  });

  // 折叠「全部事件」。aria-expanded 与 hidden 同步，供屏幕阅读器识别
  el.evtToggle.addEventListener('click', () => {
    const open = el.evtToggle.getAttribute('aria-expanded') === 'true';
    el.evtToggle.setAttribute('aria-expanded', String(!open));
    el.eventsList.hidden = open;
  });

  // 浏览器前进/后退，或手改 hash
  window.addEventListener('hashchange', () => {
    const key = parseKey(location.hash.replace(/^#/, ''));
    if (key) show(toKey(key.month, key.day), false);
  });
}

async function init() {
  Object.assign(el, {
    selMonth: document.getElementById('selMonth'),
    selDay: document.getElementById('selDay'),
    btnToday: document.getElementById('btnToday'),
    evtToggle: document.getElementById('evtToggle'),
    eventsList: document.getElementById('eventsList'),
  });

  fillMonths();
  bindEvents();

  // 词表与首日并行加载。词表失败不阻塞页面 —— 只是不显示注音
  const key = initialKey();
  const [words] = await Promise.all([loadGlossary(), Promise.resolve()]);
  glossary = words;

  await show(key, false);
}

document.addEventListener('DOMContentLoaded', init);
