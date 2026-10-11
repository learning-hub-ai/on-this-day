/* ============================================
   app.js — 入口与事件绑定
   ============================================
   职责：把 URL／下拉框／按钮的「用户意图」翻译成一次 loadDay + render。
   不取数（api.js）、不拼 HTML（render.js）。

   新增一个入口（比如键盘左右箭头翻页）只需在 bindEvents 里加一行，
   然后调 show(key) —— 所有入口都收敛到这一个函数。
   ============================================ */

import { toKey, todayKey, daysInMonth, loadDay } from './api.js';
import { renderDay, setLoading, setCategory, getCategory,
         setEventsExpanded, isEventsExpanded } from './render.js';
import { loadGlossary } from './glossary.js';

const MONTHS = ['一', '二', '三', '四', '五', '六',
                '七', '八', '九', '十', '十一', '十二'];

const el = {};          // 缓存 DOM 查询结果
let glossary = {};      // 词表，空对象也能正常工作（spec.md §6.2 第 2 条）

/**
 * 把 'MM-DD' 拆成数字 {month, day}；非法输入返回 null。
 * 导出供 integration.test.mjs 验证 —— 它是纯函数，值得单独测。
 */
export function parseKey(key) {
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

/** 当前下拉框选中的日期 */
function keyFromSelects() {
  return toKey(el.selMonth.value, el.selDay.value);
}

/**
 * 竞态守卫：记录最近一次请求的 key。
 * 用户快速连点日期时，先发的请求可能后到 —— 若不检查就渲染，
 * 画面会停在一个**不是当前选中**的日期上。
 */
let latestKey = null;

/**
 * 核心流程：所有入口最终都调这里。
 * @param {string} key 'MM-DD'
 * @param {boolean} [syncHash=true] 是否写入 URL hash
 */
async function show(key, syncHash = true) {
  const parsed = parseKey(key);
  if (!parsed) return;                  // 非法 key 静默忽略，不破坏当前视图

  el.selMonth.value = String(parsed.month);
  fillDays(parsed.month, parsed.day);

  if (syncHash && location.hash.replace(/^#/, '') !== key) {
    // replaceState 而非 pushState —— 翻日期不该堆满浏览器历史
    history.replaceState(null, '', `#${key}`);
  }

  latestKey = key;
  setLoading(true);
  const day = await loadDay(key);

  // 请求返回时用户可能已切到别的日期，此时丢弃这次结果
  if (latestKey !== key) return;

  setLoading(false);
  renderDay(day, glossary);
}

function bindEvents() {
  el.selMonth.addEventListener('change', () => {
    fillDays(el.selMonth.value, el.selDay.value);
    show(keyFromSelects());
  });

  el.selDay.addEventListener('change', () => show(keyFromSelects()));

  el.btnTodayInline.addEventListener('click', () => show(todayKey()));

  // 领域筛选。用事件委托 —— 标签栏每次渲染都会重建
  el.filterBar.addEventListener('click', (e) => {
    const chip = e.target.closest('.chip');
    if (!chip) return;
    const cat = chip.dataset.cat || null;
    // 再点一次已选中的分类 = 取消筛选，回到全部
    setCategory(cat === getCategory() ? null : cat);
    show(keyFromSelects(), false);
  });

  // 空状态里的「回到今天」—— 用委托，因为该按钮可能被重渲染
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action="today"]');
    if (btn) show(todayKey());
  });

  // 折叠「全部事件」。同步逻辑收在 render.js，两处共用一份
  el.evtToggle.addEventListener('click', () => {
    setEventsExpanded(!isEventsExpanded());
  });

  // 注音气泡：点击切换。移动端无 hover，键盘用户也需要可触发的方式
  // （桌面 hover 由 CSS 的 @media (hover:hover) 负责，与此互不干扰）
  document.addEventListener('click', (e) => {
    const gloss = e.target.closest('.gloss');
    // 先收起其他已展开的，保证同时最多一个气泡
    for (const open of document.querySelectorAll('.gloss[aria-expanded="true"]')) {
      if (open !== gloss) open.setAttribute('aria-expanded', 'false');
    }
    if (!gloss) return;
    const willOpen = gloss.getAttribute('aria-expanded') !== 'true';
    gloss.setAttribute('aria-expanded', String(willOpen));
    if (willOpen) flipIfClipped(gloss);
  });

  // 键盘：Enter/空格 切换，Esc 收起
  document.addEventListener('keydown', (e) => {
    const gloss = e.target.closest?.('.gloss');
    if (gloss && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();                    // 空格别滚动页面
      gloss.click();
      return;
    }
    if (e.key === 'Escape') {
      for (const open of document.querySelectorAll('.gloss[aria-expanded="true"]')) {
        open.setAttribute('aria-expanded', 'false');
      }
    }
  });

  // 键盘左右箭头翻天 —— 焦点在下拉框里时不拦，交给原生行为
  document.addEventListener('keydown', (e) => {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    if (/^(SELECT|INPUT|TEXTAREA)$/.test(e.target.tagName)) return;
    if (e.target.closest?.('.gloss')) return;
    if (e.key === 'ArrowLeft') show(shiftDay(keyFromSelects(), -1));
    else if (e.key === 'ArrowRight') show(shiftDay(keyFromSelects(), 1));
  });

  // 浏览器前进/后退，或手改 hash
  window.addEventListener('hashchange', () => {
    const key = parseKey(location.hash.replace(/^#/, ''));
    if (key) show(toKey(key.month, key.day), false);
  });
}

/**
 * 气泡默认居中于词上方，靠近视口左右边缘时会被裁切（layout.md §5.6）。
 * 这里实测位置后改为贴边对齐。
 *
 * 用 class 而非内联 style —— 颜色与位移值仍归 CSS，
 * JS 只负责判断「该不该翻」。
 */
function flipIfClipped(gloss) {
  const pop = gloss.querySelector('.gloss-pop');
  if (!pop) return;
  pop.classList.remove('gloss-pop--left', 'gloss-pop--right');
  const r = pop.getBoundingClientRect();
  const margin = 8;
  if (r.left < margin) pop.classList.add('gloss-pop--left');
  else if (r.right > window.innerWidth - margin) pop.classList.add('gloss-pop--right');
}

/**
 * 日期加减，跨月跨年循环（12-31 → 01-01）。
 * 用闰年 2024 做基准，保证 2/29 在序列里。
 * 导出供测试 —— 跨年回绕是容易写错的边界。
 */
export function shiftDay(key, delta) {
  const p = parseKey(key);
  if (!p) return key;
  const d = new Date(2024, p.month - 1, p.day + delta);
  return toKey(d.getMonth() + 1, d.getDate());
}

async function init() {
  Object.assign(el, {
    selMonth: document.getElementById('selMonth'),
    selDay: document.getElementById('selDay'),
    btnTodayInline: document.getElementById('btnTodayInline'),
    evtToggle: document.getElementById('evtToggle'),
    eventsList: document.getElementById('eventsList'),
    filterBar: document.getElementById('filterBar'),
  });

  // 任一节点缺失说明 HTML 与 JS 不同步，早报错好于后面莫名崩溃
  const missing = Object.entries(el).filter(([, node]) => !node).map(([k]) => k);
  if (missing.length) {
    console.error('[on-this-day] 缺少 DOM 节点：', missing.join(', '));
    return;
  }

  fillMonths();
  bindEvents();

  // 词表失败不阻塞页面 —— 只是不显示注音（spec.md §6.2 第 2 条）
  glossary = await loadGlossary();

  await show(initialKey(), false);
}

// 浏览器里自动启动。
// 条件判断 addEventListener 而非仅判断 document 存在 ——
// 测试会注入一个只有 getElementById/querySelector 的 document 替身，
// 只判断 `typeof document !== 'undefined'` 会误以为身处浏览器而崩溃。
if (typeof document !== 'undefined' &&
    typeof document.addEventListener === 'function') {
  document.addEventListener('DOMContentLoaded', init);
}
