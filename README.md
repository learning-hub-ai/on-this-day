# 历史上的今天

按日期浏览历史上发生过的有影响力的事件。面向 10–18 岁的中文读者，以六年级为设计基准。

纯前端单页，无后端、无构建、无运行时依赖。全年 366 天数据预生成后随仓库发布，
断网也能用。

---

## 本地预览

```bash
python3 serve.py          # → http://127.0.0.1:8000
```

⚠ **不能双击 `index.html` 打开。** 页面用 `fetch()` 读 `data/otd/*.json`，
而浏览器在 `file://` 下按同源策略拦截 fetch 与 ES module import。
`serve.py` 只用标准库，无需安装任何东西。

## 功能

- 任意日期可查，含 2/29；URL 形如 `#10-09`，可分享可收藏
- 维基编者精选条目置顶，附自编的「为什么重要」
- 难词注音：浅色虚下划线，点击或悬浮看拼音与极短释义
- 键盘左右箭头翻天；Esc 收起气泡
- 敏感内容（屠杀、刺杀等）标注「建议和家长一起读」
- 支持打印：自动展开全部事件、外链展开成可读 URL

## 数据

| | |
|---|---|
| 来源 | [Wikimedia On This Day API](https://api.wikimedia.org)（中文版）|
| 规模 | 366 天，精选 1,830 条 ＋ 全部事件 15,106 条 = **16,936 条，3.0 MB** |
| 处理 | `opencc` 繁→简（全量强制）、瘦身、提取关联条目、补回被截断的人名 |
| 词表 | `data/glossary.json`，按全年词频降序编写 |

重新生成：

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install opencc-python-reimplemented jieba
python3 scripts/gen_otd.py              # 全年，约 30 分钟（API 限流）
python3 scripts/gen_otd.py --days 10-09 # 单日
python3 scripts/gen_otd.py --dry-run    # 不写文件
```

脚本**幂等** —— 重跑不会覆盖人工写的 `why` / `notes` / `sensitive`。
原始响应缓存在 `.cache/`，重跑不重复请求。

## 目录

```
index.html              单页
css/style.css           暖白纸感主题（米白 ＋ 深棕 ＋ 赭红）
js/
  api.js                取数：data/otd → 可渲染数据，三级回落
  render.js             渲染：数据 → HTML，只改 DOM
  glossary.js           难词匹配：最长优先，纯函数
  app.js                入口：下拉/按钮/hash/键盘 → show(key)
data/
  otd/MM-DD.json        预生成的 366 天
  glossary.json         难词表（人工维护，生成脚本只读）
  picks/MM-DD.json      自建精选库（可选，缺失时自动跳过）
scripts/                预生成与调研工具
docs/
  spec.md               功能规格书
  layout.md             界面布局设计
serve.py                本地预览服务器
```

## 测试

```bash
node js/glossary.test.mjs                 # 词表匹配，14 条断言
python3 scripts/glossary_algo_check.py    # 同一批断言的 Python 复刻
```

第二个脚本存在是因为部分环境没有 Node。它验证**算法**，
查不出 JS 语法与 import 问题 —— 两个都该跑。

## 设计取舍

规格书 `docs/spec.md` 记录了全部实测依据。几个关键结论：

- **不做领域分类筛选。** 关键词匹配实测 40% 的事件落入「其他」、
  多标签 15%、体育分类 95% 误判。筛掉一半内容的筛选器比没有筛选器更坏
- **注释是全局共享词表，不挂在每条事件上。** 全年候选词去重后仅 2,335 个，
  重复率 78% —— 写 500 词覆盖全年四分之三
- **繁简转换在预生成时做。** `opencc` 非幂等，须反复转到不动点
- **亮色主题。** 受众场景是白天的书桌，且纸感与「历史」主题相配，还便于打印

## 授权

内容分三层，见 [LICENSE](LICENSE)。要点：维基事件文本受
**CC BY-SA 4.0**（含 share-alike，会传染到改写文本）；
代码、界面与自编的注音释义版权归本项目作者所有。
