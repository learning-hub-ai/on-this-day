/* ============================================
   glossary.test.mjs — glossary.js 的验证
   ============================================
   运行：node js/glossary.test.mjs
   无依赖，不需要测试框架。

   重点验证最长优先 —— 实测词表里有 1280 对包含关系，
   这是最容易出错也最影响正确性的一处。
   ============================================ */

import { findMarks, applyMarks, applyMarksSafe } from './glossary.js';

let pass = 0, fail = 0;
function eq(actual, expected, name) {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a === e) { pass++; console.log(`  ✅ ${name}`); }
  else { fail++; console.log(`  ❌ ${name}\n     期望 ${e}\n     实际 ${a}`); }
}
function section(t) { console.log(`\n=== ${t} ===`); }

/* 取自 docs/survey.json 的真实重叠词对，频次为实测值 */
const W = {
  '签署':   { p: 'qiān shǔ', d: '正式签字生效', n: 212 },
  '署':     { p: 'shǔ',      d: '官署',         n: 12  },
  '合并':   { p: 'hé bìng',  d: '并到一起',     n: 59  },
  '并':     { p: 'bìng',     d: '并且',         n: 301 },
  '第一届': { p: 'dì yī jiè', d: '头一次举办',   n: 54  },
  '一届':   { p: 'yī jiè',   d: '一次',         n: 9   },
  '届':     { p: 'jiè',      d: '次、期',       n: 77  },
  '其后':   { p: 'qí hòu',   d: '之后',         n: 60  },
  '其':     { p: 'qí',       d: '他的、那个',   n: 190 },
  '颁布':   { p: 'bān bù',   d: '正式公布',     n: 70  },
  '徭役':   { p: 'yáo yì',   d: '官府强派的无偿劳动', n: 1 },
  '赦令':   { p: 'shè lìng', d: '免罪的命令',   n: 2   },
  '罹难':   { p: 'lí nàn',   d: '遭遇灾祸死亡', n: 99  },
};

section('最长优先（1280 对重叠关系的核心）');
eq(findMarks('签署条约', W).map(m => m.word), ['签署'],
   '签署 不被切成 署');
eq(findMarks('两国合并', W).map(m => m.word), ['合并'],
   '合并 不被切成 并');
eq(findMarks('第一届大会', W).map(m => m.word), ['第一届'],
   '第一届 优先于 一届 和 届（三层嵌套）');
eq(findMarks('其后十年', W).map(m => m.word), ['其后'],
   '其后 优先于 其 —— 即使 其(190) 比 其后(60) 更高频');

section('频次不影响匹配，只影响编写优先级');
eq(findMarks('并且合并', W).map(m => m.word), ['并', '合并'],
   '并(301) 与 合并(59) 各自独立命中，按出现顺序');

section('不重叠');
const m1 = findMarks('签署并颁布', W);
eq(m1.map(m => [m.start, m.end]), [[0,2],[2,3],[3,5]],
   '相邻词区间首尾相接，不重叠');

section('上限 3 个（spec.md §4.1 第 3 条）');
const many = findMarks('签署颁布合并其后罹难', W);
eq(many.length, 3, '超过 3 个时截断');
eq(many.map(m => m.word), ['签署','颁布','合并'], '保留文中最靠前的 3 个');
eq(findMarks('签署颁布合并其后罹难', W, { max: 5 }).length, 5,
   'max 可覆盖');

section('未命中静默跳过（spec.md §6.2 第 2 条）');
eq(findMarks('今天天气很好', W), [], '无命中返回空数组，不抛错');
eq(findMarks('', W), [], '空文本');
eq(findMarks('签署', {}), [], '空词表');
eq(findMarks('签署', null), [], 'null 词表');

section('真实事件文本');
const real = '普鲁士首相施泰因颁布法令，解除农奴对地主的人身依附，停止徭役，史称「十月赦令」。';
eq(findMarks(real, W).map(m => m.word), ['颁布','徭役','赦令'],
   '10/09 那条事件命中 3 个词');

section('applyMarks 输出');
const html = applyMarks('签署条约', findMarks('签署条约', W));
eq(html.includes('<span class="gloss"'), true, '插入 gloss 容器');
eq(html.includes('aria-expanded="false"'), true, '带 aria-expanded');
eq(html.includes('role="tooltip"'), true, '气泡带 role');
eq(html.includes('qiān shǔ'), true, '含拼音');
eq(html.endsWith('条约'), true, '词后的文本保留');

section('转义安全（spec.md §8.4）');
eq(applyMarksSafe('签署 A&B 条约', '签署 A&amp;B 条约', W),
   '签署 A&amp;B 条约',
   '含 & 的文本跳过注音，不产生错位 HTML');
eq(applyMarksSafe('签署条约', '签署条约', W).includes('gloss'), true,
   '不含特殊字符的文本正常注音');

console.log(`\n${'─'.repeat(44)}`);
console.log(`通过 ${pass} / 失败 ${fail}`);
process.exit(fail === 0 ? 0 : 1);
