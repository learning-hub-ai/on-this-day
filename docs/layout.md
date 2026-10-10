# 「历史上的今天」界面布局设计

| | |
|---|---|
| **版本** | 2.0.0 |
| **日期** | 2026-10-10 |
| **配套** | [`spec.md`](spec.md) v2.0.0 |

**v2.0.0 变化**：主题由暗色改为**亮色**。主方案「暖白纸感」，
备选方案「清爽现代」并列记录（§4）。两套配色的对比度均已实测。

本文件定义界面结构、配色、组件与响应式规则。
功能规格、数据格式、取舍依据见 `spec.md`。

---

## 目录

- [1. 设计原则](#1-设计原则)
- [2. 页面结构](#2-页面结构)
- [3. 主方案 · 暖白纸感](#3-主方案--暖白纸感)
- [4. 备选方案 · 清爽现代](#4-备选方案--清爽现代)
- [5. 组件规格](#5-组件规格)
- [6. 响应式](#6-响应式)
- [7. 交互状态](#7-交互状态)
- [8. 无障碍](#8-无障碍)
- [9. DOM 骨架](#9-dom-骨架)
- [10. 与 hanzi-go 的关系](#10-与-hanzi-go-的关系)

---

## 1. 设计原则

### 1.1 时间轴是唯一组织轴

`spec.md` §5 否决了领域筛选，所以**年份是页面上唯一的组织维度**。
布局必须让时间关系一眼可见 —— 这不是退让，而是产品里唯一无歧义的维度。

左侧一条连续竖线串起全部卡片，年份是最显眼的元素。

### 1.2 为「读」设计，不为「扫」设计

受众是六年级学生，任务是**读懂一句话**，不是快速浏览列表。因此：

- 正文字号偏大（17px），行高宽松（1.75）
- 单列，不用多栏 —— 多栏会打断阅读
- 卡片间距大于卡片内间距，让每条事件成为独立阅读单元

### 1.3 注释必须安静

一条事件最多标 3 个词（`spec.md` §4.1）。注音标记若太显眼，
页面会变成「满是下划线的课文」，反而阻碍阅读。

虚下划线用低对比度颜色，仅在 hover/点击时才强调。

### 1.4 为什么改成亮色

初版选暗色，理由是「降低长时间阅读负担」。改为亮色更合适，有三条理由：

1. **受众场景是白天、教室或书桌**，不是夜间。亮环境下暗色主题的
   「反相」对比会增加眼睛适应负担，暗色的优势只在暗环境成立
2. **主题是历史文献**。纸、旧报纸、羊皮纸的联想只有亮底能承载 ——
   暗底金字更像「博物馆夜场」而非「翻阅资料」
3. **打印友好**。学生可能要打印某一天的事件带去学校，
   暗色主题打印会浪费墨或被浏览器强制反白，排版失控

---

## 2. 页面结构

### 2.1 整体（桌面 ≥768px）

```
┌──────────────────────────────────────────────────────┐
│  HEADER（固定，56px）                                 │
│  📅 历史上的今天      [10月 ▾] [09日 ▾]  [回到今天]    │
├──────────────────────────────────────────────────────┤
│                                                      │
│   DATE-HERO                                          │
│   10 月 9 日                                         │
│   维基精选 5 条 · 全部事件 41 条                       │
│   ─────────────────────                              │
│                                                      │
│   ┌── SELECTED 区 ──────────────────────────────┐    │
│   │ ★ 精选                                      │    │
│   │                                             │    │
│   │ │  ● 2012                                   │    │
│   │ │    巴基斯坦社会活动家马拉拉遭到…            │    │
│   │ │    💡 为什么重要：…                        │    │
│   │ │    🔗 马拉拉 · 塔利班                      │    │
│   │ │                                           │    │
│   │ │  ● 2006                                   │    │
│   │ │    朝鲜在咸镜北道进行地下核试验…            │    │
│   └─────────────────────────────────────────────┘    │
│                                                      │
│   ┌── EVENTS 区（可折叠）────────────────────────┐    │
│   │ ▾ 全部事件（41）                             │    │
│   │ │  ● 前622  …                               │    │
│   │ │  ● 768   …                                │    │
│   └─────────────────────────────────────────────┘    │
│                                                      │
│   FOOTER                                             │
│   数据取自中文维基百科 · CC BY-SA 4.0 · 抓取于 2026-10 │
└──────────────────────────────────────────────────────┘
```

**没有筛选标签栏，没有底部分类统计** —— 见 `spec.md` §5.6。

### 2.2 为什么不要侧边栏

hanzi-go 用固定侧边栏（180px）承载年级/学期导航，那是**多层级内容**。
本项目只有一个维度（日期），导航只需 header 里两个下拉。
加侧边栏会挤压正文宽度，而正文宽度直接影响阅读体验（§1.2）。

### 2.3 内容宽度

正文容器 `max-width: 720px`，居中。

依据：中文正文每行 **28–40 字**最易读。实算（汉字字宽≈字号）：

| | 容器 | 减内距后 | 每行 |
|---|---|---|---|
| 桌面 | 720px | 672px | 17px 下 **≈39 字** ✅ |
| 移动 375px | — | 315px | 16px 下 **≈19 字** ⚠️ 偏短 |

桌面 39 字/行刚在舒适上限内。全宽会让行长超过 60 字，眼睛回扫时容易丢行。

⚠ 移动端 19 字/行**偏短**，段落会被切得很碎。这是窄屏固有限制，
缓解办法是缩小时间轴缩进（28→14px，§6.1）把宽度让给正文 —— 实算回到 ≈20 字/行。
仍短，但 375px 屏上没有更好的办法。若阅读反馈不佳，
下一步是移动端去掉卡片左右内距。

---

## 3. 主方案 · 暖白纸感

米白背景 ＋ 深棕文字 ＋ 赭红强调。
像翻阅旧报纸或档案，与「历史」主题直接呼应。

### 3.1 设计令牌

```css
:root {
  /* ---- 间距（4px 基准）---- */
  --s1:4px;  --s2:8px;  --s3:12px; --s4:16px;
  --s5:24px; --s6:32px; --s7:48px; --s8:64px;

  /* ---- 纸感底色 ---- */
  --bg:         #faf6ee;   /* 页面：米白，带一点暖黄 */
  --bg-card:    #fffdf8;   /* 卡片：比页面更白一点，制造「纸叠纸」 */
  --bg-hover:   #f5efe3;   /* 卡片 hover：压暗，像被手按住 */
  --bg-sunken:  #f2ece0;   /* header / footer / 引用块 */

  /* ---- 文字：深棕系，不用纯黑 ---- */
  --text:       #3b2f2a;   /* 正文 11.98:1 */
  --text-sub:   #6b5a4e;   /* 次要   6.09:1 */
  --text-muted: #7d6b5a;   /* 元信息 4.73:1 —— 已调至过 AA */

  /* ---- 赭红强调（印章 / 朱批的语义色）---- */
  --accent:       #9c4a2f;   /*  5.67:1 */
  --accent-deep:  #7a3620;   /*  8.20:1 */
  --accent-light: #c47a5a;
  --accent-wash:  rgba(156,74,47,.08);

  /* ---- 线与分隔 ---- */
  --border:       #e0d5c3;   /* 1.35:1 —— 纯装饰，绝不承载文字 */
  --border-accent:rgba(156,74,47,.35);
  --timeline:     #cdbfa8;   /* 时间轴竖线 */
  --rule:         #d8cbb6;   /* hero 下的分隔线 */

  /* ---- 语义色 ---- */
  --sensitive:  #8a6a2f;   /* 需陪读：土黄，不用警告红 */

  /* ---- 圆角 / 阴影（纸的阴影要软）---- */
  --r-sm:4px; --r-md:8px; --r-lg:12px; --r-full:9999px;
  --shadow-sm:0 1px 2px rgba(90,70,50,.06);
  --shadow-md:0 2px 8px rgba(90,70,50,.08);
  --shadow-lg:0 8px 24px rgba(90,70,50,.12);

  /* ---- 动效 ---- */
  --ease:cubic-bezier(.16,1,.3,1);
  --fast:150ms; --normal:280ms;

  /* ---- 字体 ---- */
  --font-sans: -apple-system,'PingFang SC','Microsoft YaHei',sans-serif;
  --font-serif:'Songti SC','SimSun',Georgia,serif;  /* 年份与标题用衬线 */
  --font-year: 'Songti SC','SimSun',Georgia,serif;

  /* ---- 尺寸 ---- */
  --header-h:56px; --content-max:720px; --timeline-x:28px;
}
```

### 3.2 对比度实测（对 `--bg` #faf6ee）

| 令牌 | 色值 | 对比度 | WCAG AA |
|---|---|---|---|
| `--text` | `#3b2f2a` | **11.98:1** | ✅ |
| `--accent-deep` | `#7a3620` | 8.20:1 | ✅ |
| `--text-sub` | `#6b5a4e` | 6.09:1 | ✅ |
| `--accent` | `#9c4a2f` | 5.67:1 | ✅ |
| `--text-muted` | `#7d6b5a` | **4.73:1** | ✅ |
| `--border` | `#e0d5c3` | 1.35:1 | ⛔ 纯装饰 |
| `--timeline` | `#cdbfa8` | 1.68:1 | ⛔ 纯装饰 |

⚠ **`--text-muted` 初稿取 `#8a7868`，实测 3.92:1 不过 AA**（正文需 ≥4.5）。
footer、副标题、关联条目行字号只有 12–13px，属正常文本，必须过 4.5:1。
已调为 `#7d6b5a`（4.73:1）。

`--accent` 在卡片底 `#fffdf8` 上实测 **6.02:1**，比在页面底上更好 —— 安全。

### 3.3 为什么文字不用纯黑

`#3b2f2a`（深棕）而非 `#000000`。米白底上的纯黑对比过硬，
与暖色背景在色温上冲突，看久了有「印刷错版」的违和感。
深棕与米白同属暖色，像铁胆墨水在纸上氧化后的颜色。

### 3.4 纸感的三个细节

这是本方案与普通亮色主题的区别所在：

1. **卡片比页面更白**（`#fffdf8` vs `#faf6ee`，实测 1.06:1）。
   ⚠ 1.06:1 肉眼几乎不可辨 —— **卡片边界必须靠 `--border` 和
   `--shadow-sm` 确立，不能只靠底色差**。底色差只是锦上添花
2. **阴影带棕调**（`rgba(90,70,50,…)` 而非 `rgba(0,0,0,…)`）。
   纯黑阴影在暖底上会发灰发脏
3. **年份用衬线体**。宋体/Songti 的年份数字有活字印刷的质感，
   与无衬线的正文形成层次。⚠ 不要全文用衬线 ——
   屏幕上长段中文衬线体可读性低于黑体

### 3.5 可选的纸纹

若想进一步强化纸感，可加极淡的噪点纹理：

```css
body::before{
  content:''; position:fixed; inset:0; pointer-events:none; z-index:1;
  opacity:.025;
  background-image:url("data:image/svg+xml,…feTurbulence…");
}
```

⚠ 慎用。`opacity` 超过 0.04 就会干扰小字号文字的清晰度，
而本项目正文有 12px 的元信息。**建议 v1 不做**，留作后续选项。

---

## 4. 备选方案 · 清爽现代

纯白背景 ＋ 蓝灰色调。Wikipedia / Notion 的路线：干净、中性、无风格负担。

### 4.1 设计令牌（覆盖 §3.1 的颜色部分）

```css
:root {
  --bg:         #ffffff;
  --bg-card:    #ffffff;   /* 与页面同色 —— 见 §4.3 */
  --bg-hover:   #f9fafb;
  --bg-sunken:  #f9fafb;

  --text:       #1f2937;   /* 14.68:1 */
  --text-sub:   #4b5563;   /*  7.56:1 */
  --text-muted: #6b7280;   /*  4.83:1 */

  --accent:       #2563eb;   /* 5.17:1 */
  --accent-deep:  #1d4ed8;   /* 6.70:1 */
  --accent-light: #60a5fa;
  --accent-wash:  rgba(37,99,235,.06);

  --border:       #e5e7eb;   /* 1.24:1 —— 纯装饰 */
  --border-accent:rgba(37,99,235,.3);
  --timeline:     #d1d5db;
  --rule:         #e5e7eb;

  --sensitive:    #b45309;   /* 琥珀 */

  --shadow-sm:0 1px 2px rgba(0,0,0,.05);
  --shadow-md:0 2px 8px rgba(0,0,0,.06);
  --shadow-lg:0 8px 24px rgba(0,0,0,.1);

  --font-year:'SF Mono',Menlo,Consolas,monospace;  /* 等宽，不用衬线 */
}
```

### 4.2 对比度实测（对 `#ffffff`）

| 令牌 | 色值 | 对比度 | WCAG AA |
|---|---|---|---|
| `--text` | `#1f2937` | **14.68:1** | ✅ |
| `--text-sub` | `#4b5563` | 7.56:1 | ✅ |
| `--accent-deep` | `#1d4ed8` | 6.70:1 | ✅ |
| `--accent` | `#2563eb` | 5.17:1 | ✅ |
| `--text-muted` | `#6b7280` | **4.83:1** | ✅ |
| `--border` | `#e5e7eb` | 1.24:1 | ⛔ 纯装饰 |

**全部开箱过 AA** —— 这是方案 B 的主要工程优势，取自成熟的 Tailwind 灰阶。

### 4.3 卡片与页面同色的后果

方案 B 的卡片底色与页面**完全相同**（都是 `#ffffff`）。
所以卡片边界**只能**靠 `--border` 1px 实线 ＋ `--shadow-sm` 确立。

这不是缺陷，是 Notion/Wikipedia 的既定做法：
内容与容器不分离，靠留白和细线组织层次。但要注意：

- `--shadow-sm` 不能省 —— 否则卡片在白底上「漂」着，没有边界感
- hover 用 `--bg-hover` `#f9fafb` 轻微压灰，这是唯一的状态反馈来源

### 4.4 两方案对比

| | A 暖白纸感（主）| B 清爽现代（备）|
|---|---|---|
| 主题契合 | ✅ 纸/档案联想直接 | ⚪ 中性，无历史暗示 |
| 对比度 | 需调 1 个令牌（已调）| ✅ 开箱全过 |
| 长时间阅读 | ✅ 暖色降低眩光 | ⚪ 纯白在强光下偏刺眼 |
| 与 hanzi-go 区分 | ✅ 完全不同的色系 | ⚠️ 都是浅底，易混 |
| 实现成本 | 多 3 个纸感细节（§3.4）| ✅ 最低 |
| 注音虚线可见性 | 3.29:1 刚过线 ✅ | **2.54:1 不足**，须换色（§5.6）|
| 打印 | ✅ 米白会被打成白，正常 | ✅ |
| 风险 | 暖色若调过头会显「做旧过度」| 容易显得像文档工具，不像给孩子的产品 |

**建议用 A。** 理由：这个项目唯一的视觉主张就是「历史」，
而 B 刻意放弃视觉主张。B 的优势（开箱过 AA、成本低）在 A 调完一个令牌后就不再是优势。

**保留 B 的价值**：如果 A 实装后显得「做旧过度」或孩子反馈不喜欢，
B 是一个无需重新设计的退路 —— 两套令牌结构相同，只换颜色值。

### 4.5 两套令牌的切换方式

颜色全部集中在 `:root`，组件样式只引用变量名。
切换方案 = 替换 `:root` 颜色块 ＋ `--font-year`，**组件 CSS 一行都不用改**。

⚠ 这要求组件样式**严禁出现字面色值**。任何 `#` 开头的颜色都只许出现在 `:root`。

---

## 5. 组件规格

以下规格两套配色通用，仅引用变量名。

### 5.1 Header

```
┌────────────────────────────────────────────────────────┐
│ 📅 历史上的今天        [10月▾][09日▾]      [↻ 回到今天] │
└────────────────────────────────────────────────────────┘
  ← 1fr →            ← auto（居中）→           ← 1fr →
```

```css
header{
  position:fixed; top:0; left:0; right:0; height:var(--header-h);
  background:var(--bg-sunken);
  border-bottom:1px solid var(--border);
  display:grid; grid-template-columns:1fr auto 1fr;
  align-items:center; padding:0 var(--s4); z-index:100;
}
```

三列 grid（而非 `space-between`）：两侧 `1fr` 吸收宽度差，
保证日期选择器**真正居中**，不会因左右元素宽度变化而漂移。

| 元素 | 规格 |
|---|---|
| 站点标题 | 15px / 700 / `--text`；移动端隐藏文字只留 📅 |
| 日期选择器 | 两个 `<select>`，36px 高，`--bg-card` 底，`--border` 边 |
| 回到今天 | 次要按钮，`--accent` 文字 ＋ `--border-accent` 边，hover 填 `--accent-wash` |

### 5.2 Date-Hero

```
    10 月 9 日
    维基精选 5 条 · 全部事件 41 条
    ──────────────
```

| 元素 | 规格 |
|---|---|
| 日期 | 32px / 700 / `--font-serif`（A）或 `--font-sans`（B）/ `--text` |
| 副标题 | 13px / `--text-muted` |
| 分隔线 | 1px `--rule`，宽 64px，左对齐 —— 像文章标题下的短横 |
| 留白 | 上 `--s7`，下 `--s6` |

**不显示分类统计** —— 无分类（`spec.md` §5.6）。改为精选/全部条数，
这是真实可得的信息。

### 5.3 时间轴与事件卡片

```
 │
 ●  2012          ← 年份：衬线（A）/ 等宽（B），赭红/蓝，18px
 │   ┌──────────────────────────────────────┐
 │   │ 巴基斯坦社会活动家马拉拉遭到武装分子   │
 │   │ 刺杀未遂。                            │
 │   │                                      │
 │   │ 💡 她为女孩上学说话，被枪击后活下来， │
 │   │    后来成为最年轻的诺贝尔奖得主。      │
 │   │                                      │
 │   │ 🔗 马拉拉 · 塔利班                    │
 │   └──────────────────────────────────────┘
 │
 ●  2006
```

```css
.timeline{position:relative; padding-left:var(--s7); list-style:none}
.timeline::before{
  content:''; position:absolute; left:var(--timeline-x); top:8px; bottom:8px;
  width:2px; background:var(--timeline);
}
.event{position:relative; margin-bottom:var(--s6)}
.event::before{
  content:''; position:absolute;
  left:calc(var(--timeline-x) - var(--s7) - 4px); top:10px;
  width:10px; height:10px; border-radius:var(--r-full);
  background:var(--accent); box-shadow:0 0 0 4px var(--bg);
}
.event-year{
  font-family:var(--font-year); font-size:18px; font-weight:700;
  color:var(--accent-deep); margin-bottom:var(--s2);
}
.event-card{
  background:var(--bg-card);
  border:1px solid var(--border);           /* 不可省，见 §3.4 / §4.3 */
  border-radius:var(--r-md);
  box-shadow:var(--shadow-sm);              /* 不可省 */
  padding:var(--s4) var(--s5);
  transition:background var(--fast) var(--ease),
             border-color var(--fast) var(--ease),
             box-shadow var(--fast) var(--ease);
}
.event-card:hover{
  background:var(--bg-hover);
  border-color:var(--border-accent);
  box-shadow:var(--shadow-md);
}
.event-text{font-size:17px; line-height:1.75; color:var(--text)}
```

| 元素 | 规格 | 说明 |
|---|---|---|
| 年份 | 18px / `--accent-deep` | 用 deep 而非 accent：8.2:1，年份是关键信息 |
| 正文 | **17px / 行高 1.75** | 为六年级阅读放大（§1.2）|
| 卡片内距 | 16px 上下 / 24px 左右 | — |
| 卡片间距 | **32px** | 大于内距，让每条成为独立阅读单元 |
| 圆点 | 10px，4px `--bg` 描边 | 描边制造「浮在竖线上」的效果 |

**公元前年份**：`y` 为负数时显示「前 622」，不显示负号。

### 5.4 精选标记

```css
.event--selected .event-card{
  border-left:3px solid var(--accent);
  background:linear-gradient(90deg, var(--accent-wash), var(--bg-card) 72px);
}
```

渐变只在左侧 72px 内，避免整张卡片染色影响正文可读性。
区块顶部标「★ 精选」。

### 5.5 「为什么重要」

```css
.event-why{
  margin-top:var(--s4); padding:var(--s3) var(--s4);
  background:var(--bg-sunken); border-radius:var(--r-sm);
  border-left:2px solid var(--accent-light);
  font-size:15px; line-height:1.7; color:var(--text-sub);
}
```

比正文小 2px、颜色更淡 —— 它是补充，不是主体。
图标 💡 用 `::before` 注入并 `aria-hidden`。

### 5.6 注音（最关键的组件）

默认状态必须**安静**：

```css
.gloss{
  border-bottom:1px dashed var(--accent-light);
  cursor:help; position:relative;
}
.gloss:hover,.gloss:focus-visible{
  border-bottom-color:var(--accent);
  background:var(--accent-wash);
}
.gloss-pop{
  position:absolute; bottom:calc(100% + 8px); left:50%;
  transform:translateX(-50%);
  background:var(--text);                   /* 反相气泡：深底浅字 */
  color:var(--bg-card);
  border-radius:var(--r-sm); padding:var(--s2) var(--s3);
  font-size:14px; line-height:1.5; white-space:nowrap; z-index:50;
  box-shadow:var(--shadow-lg);
  opacity:0; pointer-events:none; transition:opacity var(--fast);
}
.gloss[aria-expanded="true"] .gloss-pop{opacity:1}
```

**气泡用反相**（深底浅字）：亮色主题下，浅底气泡与页面区分度不足，
会看不出这是浮层。实测反相后对比度 **A 12.70:1 / B 14.68:1**，均远超 AA。

气泡内容两行：

```
颁布  bān bù
正式公布
```

| 规则 | 值 | 依据 |
|---|---|---|
| 默认 | 收起 | 一条最多 3 词，常驻会干扰阅读（`spec.md` §4.1）|
| 桌面触发 | hover ＋ 键盘 focus | — |
| **移动端触发** | **点击**，不用 hover | 移动端无 hover（`spec.md` §8.2）|
| 词表未命中 | **静默跳过** | 不加标记、不报错（`spec.md` §6.2 第 2 条）|

⚠ 气泡靠近视口边缘时须翻转对齐方向，否则被裁切。

⚠ **虚下划线的可见性实测**：`--accent-light` 对卡片底
**A 3.29:1 / B 2.54:1**。非文字元素的可辨下限约 3:1，
所以**方案 B 的 `#60a5fa` 太淡，虚线几乎看不见** ——
用 B 时须把注音下划线改为 `--accent` `#2563eb`（5.17:1），
或加粗到 2px。方案 A 的 3.29:1 刚过线，可用。

### 5.7 实体内链

```css
.entity-link{
  color:var(--accent-deep); text-decoration:none;
  border-bottom:1px solid var(--border-accent);
}
.entity-link:hover{border-bottom-color:var(--accent-deep)}
```

用**实线**下划线与注音的**虚线**区分开 —— 一个是「跳出去」，
一个是「看解释」，两种交互必须视觉可辨。

卡片底部另列关联条目：`🔗 马拉拉 · 塔利班`，13px / `--text-muted`。
`links` 为空时（3.4% 的事件，`spec.md` §6.4）不渲染这一行。

### 5.8 全部事件折叠区

```
▾ 全部事件（41）
```

- 默认**折叠**。`selected` 已是编者精选的 5 条，先给最重要的
- 展开后保持展开（同一会话内切换日期不重置）
- 触发区是整行，44px 高（移动端点击目标下限）

### 5.9 敏感条目标记

```css
.event--sensitive .event-card{border-left:3px solid var(--sensitive)}
.sensitive-badge{
  font-size:12px; color:var(--sensitive);
  border:1px solid currentColor; border-radius:var(--r-full);
  padding:1px var(--s2);
}
```

文案：`⚑ 建议和家长一起读`

用土黄/琥珀而非警告红 —— 这不是错误，是阅读提示。
内容本身不回避（`spec.md` §4.3）。

### 5.10 空状态

```
        📭
   这一天还没有整理好的事件

   换一天看看，或者
   [回到今天]
```

居中，`--text-muted`，上下留白 `--s8`。
这是**真实可达的状态**（精选库非 366 天全覆盖，`spec.md` §3.3），不是边缘情况。

### 5.11 Footer

```
数据取自中文维基百科 · CC BY-SA 4.0 · 抓取于 2026-10
```

12px / `--text-muted`，链接到维基与许可证全文。
**这是 CC BY-SA 的强制要求**（`spec.md` §9.1），不是装饰。

⚠ 12px 属正常文本，所以 `--text-muted` 必须过 4.5:1 —— 这是 §3.2 调色的原因。

---

## 6. 响应式

断点两个，不做更多 —— 内容是单列，没有需要重排的复杂栅格。

### 6.1 移动端（<768px）

```css
@media (max-width:767px){
  :root{ --timeline-x:14px; --s7:32px; }
  .site-title span{display:none}          /* 只留 📅 */
  header{grid-template-columns:auto 1fr auto; gap:var(--s2)}
  .timeline{padding-left:var(--s6)}
  .date-hero h1{font-size:26px}
  .event-text{font-size:16px}
  .event-card{padding:var(--s3) var(--s4)}
  .gloss-pop{white-space:normal; max-width:70vw}
}
```

| 调整 | 原因 |
|---|---|
| 标题只留图标 | 让日期选择器有足够宽度 |
| 时间轴缩进 28→14px | 窄屏正文宽度优先（§2.3 的行长问题）|
| 正文 17→16px | 窄屏行长控制 |
| 气泡允许换行 | `nowrap` 在窄屏会溢出 |
| 注音改点击触发 | 无 hover |

### 6.2 打印

亮色主题的附带好处，值得花 10 行 CSS：

```css
@media print{
  header,.section-toggle,#btnToday{display:none}
  body{background:#fff}
  .event-card{box-shadow:none; border:1px solid #ccc; break-inside:avoid}
  .events-section ol[hidden]{display:block!important}  /* 打印展开全部 */
  .gloss-pop{display:none}
  .entity-link::after{content:' (' attr(href) ')'; font-size:10px}
}
```

学生可能要打印某一天带去学校。注音气泡打印无意义（无法交互），
但外链应展开成可读的 URL。

### 6.3 不做的响应式

- **不做平板专属断点** —— 单列在 768–1024px 无需特殊处理
- **不做横屏特殊处理** —— 纵向滚动天然适配
- **不做暗色切换** —— v1 只有亮色。暗色需双份令牌与持久化，
  且 §1.4 的三条理由说明受众场景不需要

---

## 7. 交互状态

每个可交互元素必须有四态：

| 态 | 处理 |
|---|---|
| default | 基准样式 |
| hover | 背景转 `--bg-hover`，边框转 `--border-accent`，阴影升一级 |
| focus | `:focus-visible{outline:2px solid var(--accent); outline-offset:2px}` |
| active | `transform:scale(.98)`，`--fast` 时长 |

### 7.1 日期切换的过渡

切换日期时**不做整页淡出** —— 会让人觉得在加载。
只对时间轴容器做 `opacity:0→1` 的 180ms 淡入，年份与卡片保持位置稳定。

### 7.2 不要动画时间轴

竖线与圆点**不做入场动画**。逐条滑入在 41 条事件上会持续两秒以上，
阅读被迫等待。

---

## 8. 无障碍

| 项 | 要求 |
|---|---|
| 日期选择 | `<select>` 带 `aria-label="选择月份"` / `"选择日期"` |
| 回到今天 | `<button>`，非 `<a>` |
| 折叠区 | `aria-expanded` ＋ `aria-controls` |
| 注音 | `tabindex="0"` 可聚焦；`aria-expanded` 标状态；气泡 `role="tooltip"` |
| 时间轴 | `<ol>` 语义列表（事件有顺序）；竖线与圆点是 `::before` 纯装饰 |
| 外链 | `rel="noopener noreferrer"`；指向维基时标 `hreflang="zh"` |
| 焦点环 | 全局 `:focus-visible`，不用 `outline:none` |
| 对比度 | 见 §3.2（方案 A）/ §4.2（方案 B），正文与元信息均过 AA |
| 点击目标 | 移动端 ≥44×44px（折叠触发行、注音词、按钮）|

### 8.1 装饰性 emoji

📅 💡 🔗 ⚑ 📭 ★ 用 CSS `::before` 的 `content` 注入，
或加 `aria-hidden="true"` —— 不让屏幕阅读器念出「灯泡」。

### 8.2 亮色主题特有的注意点

- **`--border` 和 `--timeline` 对比度只有 1.2–1.7:1**，是刻意的（装饰线不该抢眼），
  但因此**不能用它们传达任何信息**。卡片边界靠边框＋阴影双重保障
- **高对比模式**（`prefers-contrast:more`）下应加深边框：
  ```css
  @media (prefers-contrast:more){
    :root{--border:var(--text-muted); --timeline:var(--text-muted)}
  }
  ```

---

## 9. DOM 骨架

```html
<header>
  <div class="site-title"><span aria-hidden="true">📅</span> <span>历史上的今天</span></div>
  <div class="date-picker">
    <select id="selMonth" aria-label="选择月份"></select>
    <select id="selDay"   aria-label="选择日期"></select>
  </div>
  <button id="btnToday" class="btn-secondary">回到今天</button>
</header>

<main class="content">
  <section class="date-hero">
    <h1 id="heroDate">10 月 9 日</h1>
    <p  id="heroMeta" class="hero-meta">维基精选 5 条 · 全部事件 41 条</p>
  </section>

  <section class="selected-section" aria-labelledby="selTitle">
    <h2 id="selTitle" class="section-title">精选</h2>
    <ol class="timeline" id="selectedList"><!-- .event × N --></ol>
  </section>

  <section class="events-section" aria-labelledby="evtTitle">
    <button class="section-toggle" id="evtToggle"
            aria-expanded="false" aria-controls="eventsList">
      <span id="evtTitle">全部事件（<span id="evtCount">41</span>）</span>
    </button>
    <ol class="timeline" id="eventsList" hidden><!-- .event × N --></ol>
  </section>

  <div class="empty-state" id="emptyState" hidden>
    <span aria-hidden="true">📭</span>
    <p>这一天还没有整理好的事件</p>
  </div>
</main>

<footer>
  数据取自<a href="https://zh.wikipedia.org" rel="noopener noreferrer" hreflang="zh">中文维基百科</a>
  · <a href="https://creativecommons.org/licenses/by-sa/4.0/deed.zh"
       rel="noopener noreferrer">CC BY-SA 4.0</a>
  · 抓取于 <span id="fetchDate"></span>
</footer>
```

### 9.1 单条事件

```html
<li class="event event--selected">
  <div class="event-year">2012</div>
  <article class="event-card">
    <p class="event-text">
      巴基斯坦社会活动家马拉拉遭到武装分子<span class="gloss" tabindex="0"
      aria-expanded="false">刺杀<span class="gloss-pop" role="tooltip">刺杀
      <em>cì shā</em><br>暗中杀害</span></span>未遂。
    </p>
    <p class="event-why">她为女孩上学说话，被枪击后活下来，后来成为最年轻的诺贝尔奖得主。</p>
    <p class="event-links">
      <span aria-hidden="true">🔗</span>
      <a class="entity-link" href="…" rel="noopener noreferrer">马拉拉</a> ·
      <a class="entity-link" href="…" rel="noopener noreferrer">塔利班</a>
    </p>
  </article>
</li>
```

### 9.2 CSS 文件组织

```
css/style.css
├─ 1. 设计令牌（:root）        ← 唯一允许出现字面色值的地方
├─ 2. reset ＋ 基础排版
├─ 3. header
├─ 4. date-hero
├─ 5. timeline ＋ event-card
├─ 6. gloss（注音）            ← 最复杂，单独一节
├─ 7. 空状态 ＋ footer
├─ 8. 响应式（@media）
└─ 9. 打印（@media print）
```

照 hanzi-go 的编号分节习惯。响应式集中末尾而非散落各节 ——
单列布局的移动端差异很少，集中更好查。

⚠ **第 1 节之外严禁字面色值**，否则 §4.5 的方案切换会失效。

---

## 10. 与 hanzi-go 的关系

两个项目应当像兄弟，不是同一个：

| | hanzi-go | on-this-day（方案 A）|
|---|---|---|
| 背景 | 冷白 `#f8fafc` | **米白** `#faf6ee` |
| 正文 | 蓝灰 `#1e293b` | **深棕** `#3b2f2a` |
| 强调色 | 紫 `#4f46e5` | **赭红** `#9c4a2f` |
| 布局 | 固定侧边栏 ＋ 内容区 | **单列居中** |
| 导航维度 | 年级 × 学期 × 模式（多层）| **日期（单层）** |
| 字体 | 含楷体显示汉字字形 | 衬线仅用于年份与标题 |
| 共用 | 4px 间距基准、`:focus-visible` 焦点环、CSS 编号分节、emoji 图标习惯 |

共用的是**工程约定**，区分的是**视觉身份**。

⚠ 若改用方案 B（纯白 ＋ 蓝灰），与 hanzi-go 的区分度会明显下降 ——
两者都是浅底 ＋ 冷色文字，这是 §4.4 判断 A 更合适的理由之一。
