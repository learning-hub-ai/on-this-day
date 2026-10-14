# 历史上的今天

按日期浏览历史上发生过的有影响力的事件。面向 10–18 岁的中文读者，以六年级为设计基准。

**在线使用**：https://learning-hub-ai.github.io/on-this-day/

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
- **按领域筛选**：8 个分类，点击即筛，再点取消。
  标签只显示当天实有的分类 —— 点任何一个都一定有内容
- **出处可核对**：每天的事件与日期都取自维基百科对应的日期条目，
  页面顶部直接链到该条目，可一键核对原始列表
- **「详情」链接**只在能确认条目描述该事件时才给（约 28%）——
  确认不了就不给，少给一个链接好过给一个误导的；
  底部另列全部关联条目作延伸阅读
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
| 词表 | `data/glossary.json`，93 词，覆盖 23.4% 事件、**366/366 天** |
| 分类 | 离线打标 8 类，抽样精度 **92%**，44.5% 归入「其他」|

重新生成：

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install opencc-python-reimplemented jieba
python3 scripts/gen_otd.py              # 全年，约 30 分钟（API 限流）
python3 scripts/gen_otd.py --days 10-09 # 单日
python3 scripts/gen_otd.py --dry-run    # 不写文件

# ⚠ 完整流程有固定顺序，改了前一步后面都要重跑：
#
#   gen_otd.py → demote_generic_links.py → tag_sensitive.py → tag_events.py
#
# demote_generic_links 要全年数据齐了才能统计「某标题被多少日期共用」，
# 所以只能在 gen_otd 之后；而 gen_otd 重跑会把降级冲掉，需补跑。
# tag_events 按正文算分类，任何改正文的脚本之后都要重跑。
python3 scripts/demote_generic_links.py --apply   # 详情一对一（§6.4f）
python3 scripts/demote_generic_links.py           # 预演，不写
python3 scripts/tag_sensitive.py --apply          # 标需陪读条目（§4.3）
python3 scripts/tag_events.py           # 打领域标签（写入 tag 字段）
python3 scripts/tag_events.py --dry-run --sample 10   # 只统计 ＋ 抽样核验

# 一次性数据清理（已跑过，一般不需再跑）：
python3 scripts/fill_empty_titles.py --apply  # 补空书名号（§10.1c）
python3 scripts/strip_tu_marker.py --apply    # 清历史数据里的（图）
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

## 扩充词表

难词注释是一份**全局共享词表**，不挂在每条事件上 ——
全年候选词去重后仅 2,335 个、重复率 78%，所以写一次就全年复用。

```bash
python3 scripts/check_glossary.py            # 校验 ＋ 覆盖率
python3 scripts/check_glossary.py --next 30  # 列出下 30 个待写候选
```

编写规则（`docs/spec.md` §4.1）：

1. **注词不注字** —— 给「徭役」而不是单给「徭」
2. **释义 ≤12 字** —— 这是提示，不是词典
3. **一条事件最多标 3 个** —— 渲染期约束，超出只标最靠前的
4. **不得循环** —— 释义里不能用另一个词表条目。
   「屠杀 → 大批杀害」是坏释义：读者查了还得再查「杀害」
5. **不得自指** —— 释义不能重复词目 2 个以上的字。
   「重伤 → 严重的伤」等于没解释

校验脚本会拦住 4 和 5，并用 `pypinyin` 逐条核对拼音**内容** ——
格式对但注音错，孩子会照着念错。

哪些词**不该收**见 `data/glossary-exclude.json`，分四类并各自写明原因：
教材未收但不难的（成功、使用）、分词碎片（斐、郡）、音译专名（拿破仑）、
已收词的复合（示威者）。校验脚本会拦住误收。

⚠ 可注释上限是 **71.9%** —— 排除名单里的词占全年出现次数的 28.1%，
它们永远不该被注释。所以「500 词覆盖 50%」已是接近天花板的成绩。

## 部署到 GitHub Pages

**已部署**：https://learning-hub-ai.github.io/on-this-day/

**不需要服务器。** GitHub Pages 本身就是 HTTP 服务 ——
`serve.py` 只是本地开发用的替代品（因为 `file://` 下 `fetch` 被拦）。

```bash
git remote add origin https://github.com/<用户名>/on-this-day.git
git push -u origin main
```

然后在仓库 **Settings → Pages** 里把 Source 设为 `main` 分支的根目录。
几分钟后站点在 `https://<用户名>.github.io/on-this-day/` 上线。

⚠ 若同一账号下多个仓库各用一个 **fine-grained token**，推送前需要：

```bash
git config --global credential.useHttpPath true
```

否则 git 只按主机名匹配凭据，会把别的仓库的 token 发给 GitHub 而被拒。

### 为什么不需要构建步骤

| | |
|---|---|
| 无框架、无打包器 | 仓库里的文件就是发布的文件 |
| 数据已预生成 | 366 天 JSON 随仓库走，运行时不调 API |
| 词表、标签已离线算好 | 前端只读 `tag` 与 `glossary.json` |
| 全部路径**相对** | Pages 从 `/<仓库名>/` 子目录提供服务，绝对路径会 404 |

已实测：模拟子目录部署（`/on-this-day/index.html`）下全部资源 200，
渲染 46 条事件、8 个分类标签、18 处注音 —— 与根目录部署一致。

### 体积

| | |
|---|---|
| 发布体积 | **4.5 MB**（Pages 上限 1 GB）|
| 文件数 | 393（其中 366 个是按天的 JSON）|
| 最大单文件 | 112 KB（`docs/survey.json`）|

首屏只加载 `index.html` ＋ CSS ＋ 4 个 JS ＋ 1 天的 JSON（约 8 KB）
＋ 词表（约 10 KB）。**不会一次下载 3 MB。**

### `.nojekyll`

仓库根目录有空文件 `.nojekyll`，用来关掉 Pages 默认的 Jekyll 处理。
不加的话 Jekyll 会忽略以 `_` 开头的文件和目录。本项目目前没有这类文件，
但留着它可以避免日后踩坑。

### 一个注意点

Pages 只支持静态文件，所以**将来若想改成实时调 Wikimedia API**，
浏览器直连是可行的（该 API 的 `access-control-allow-origin: *`），
但会遇到 §3.2 实测的限流（`retry-after` 13–41 秒）。
预生成仍是正确选择。

## 测试

**浏览器里跑（不需要装 Node）：**

```bash
python3 serve.py 8000     # 然后打开 http://127.0.0.1:8000/test.html
```

`test.html` 在真实浏览器里验证数据契约、计数自洽、渲染与外链安全。
页面上直接显示每条断言的通过/失败，失败时给出是哪一天、哪一条。
带 `?all=1` 可跑全量（含 366 天逐日检查），便于无头浏览器与 CI：

```bash
google-chrome --headless --dump-dom 'http://127.0.0.1:8000/test.html?all=1'
# 跑完在 <body> 上写 data-fail / data-pass，脚本可直接判断成败
```

**命令行跑：**

```bash
./run-tests.sh          # 全部，自动起停本地服务
```

分开跑：

| 命令 | 覆盖 | 断言 |
|---|---|---|
| `python3 scripts/check_glossary.py` | 词表规则（5 项，均经反向测试）| — |
| `python3 scripts/glossary_algo_check.py` | 注音算法的 Python 复刻 | 14 |
| `node js/glossary.test.mjs` | 注音匹配：最长优先、转义安全 | 21 |
| `node js/integration.test.mjs` | 端到端：真实 fetch ＋ DOM 替身 | 105 |
| `test.html`（浏览器）| 数据契约、计数、渲染安全 | 30+ |

集成测试需要本地服务（`api.js` 用相对路径 fetch，Node 的 fetch 不接受
相对 URL）—— `run-tests.sh` 会自动起停，手动跑则先 `python3 serve.py 8750`。

它覆盖的是单元测试碰不到的部分：全年 366 天逐日载入、年份升序、
内存缓存命中、空数据回落、公元前年份渲染、XSS 转义，
以及「含 `&` 的文本跳过注音」这个下标错位的防线。

浏览器版与 Node 版断言有重叠但**不互相替代** —— 浏览器能发现
DOM 替身发现不了的问题（真实 `innerHTML` 解析、真实 `a.rel` 归一化）。

`pypinyin` 是**可选依赖** —— 装了才核对拼音内容，没装则跳过该项。
Python 复刻脚本存在是因为部分环境没有 Node；它验证**算法**，
查不出 JS 语法与 import 问题，所以两边都该跑。

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
