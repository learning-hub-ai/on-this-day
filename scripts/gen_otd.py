#!/usr/bin/env python3
"""
gen_otd.py — 「历史上的今天」预生成脚本

把 Wikimedia On This Day 的 366 天数据抓下来、转简体、瘦身，
写成 data/otd/MM-DD.json。详见 docs/spec.md §7.1。

两个端点，缓存状况不同：
  events   —— survey_notes.py 已缓存 364 天到 .cache/raw/，直接复用，不请求
  selected —— 未缓存，必须现抓 366 次（≥1s 间隔 ≈ 7 分钟）

依赖：
  pip install opencc-python-reimplemented

用法：
  python3 scripts/gen_otd.py                  # 全年
  python3 scripts/gen_otd.py --days 10-09     # 单日（逗号分隔多日）
  python3 scripts/gen_otd.py --retry-failed   # 只补跑上次失败的（04-12, 08-06）
  python3 scripts/gen_otd.py --dry-run        # 不写文件，只报告
  python3 scripts/gen_otd.py --force          # 覆盖人工编辑过的条目（危险）
"""

import argparse
import calendar
import difflib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date

try:
    from opencc import OpenCC
    _CC = OpenCC('t2s')
except ImportError:
    sys.exit("缺 opencc：pip install opencc-python-reimplemented")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, '.cache', 'raw')
CACHE_SEL_DIR = os.path.join(ROOT, '.cache', 'selected')
OUT_DIR = os.path.join(ROOT, 'data', 'otd')

API = 'https://api.wikimedia.org/feed/v1/wikipedia/zh/onthisday/{type}/{mm}/{dd}'
UA = 'on-this-day/1.0 (personal learning project; zh-Hans pregeneration)'

# 限流（实测 2026-10-10，见 spec.md §3.2）
#
# ⚠ 不是「第 11 个请求触发 429」那么简单。实测服务端是 envoy 令牌桶
#   （响应头 x-envoy-ratelimited: true），且 **retry-after 高达 28–38 秒**。
#   在 5s 固定间隔下 10 个请求仍有 3 个被限。
#
# ⚠ 本机出口 IP 是企业 NAT（x-client-ip 单一地址），配额与同网段其他用户共享，
#   所以实际可用速率**不可预测**，不同时段差异大。
#
# 因此策略是：固定间隔只做基础节流，真正的退避**完全听服务端的 retry-after**。
REQ_INTERVAL = 5.0
MAX_RETRY = 6
# retry-after 的上限保护 —— 服务端给出过 38s，留余量但不无限等
RETRY_AFTER_CAP = 120

# 年份条目，从关联实体里剔除（spec.md §6.4）
# 纯日期/年份型条目标题 —— 这类**不是**「某天发生的事」，不该进 u 或 l。
#
# ⚠ 「前539年」曾漏判：旧模式只认「公元前N年」，不认维基实际在用的
#   简写「前N年」。实测漏掉 54 条 u 和 59 处 l，于是出现
#   「居鲁士攻占巴比伦。详情：前539年」—— 点进去是整年的大事记，
#   根本不是这件事。
YEAR_RE = re.compile(
    r'^(?:公元)?前?\d+年$'        # 1492年 / 前539年 / 公元前539年
    r'|^\d+年代$'                 # 1960年代
    r'|^(?:公元)?前?\d+世纪$'      # 20世纪 / 前5世纪
    r'|^\d+月\d+日$'              # 11月26日
    r'|^\d+年\d+月$'              # 1949年10月
    r'|^(?:\d+年)?大事[记記]$'     # 1949年大事记
)
# ⚠ 不要加「年表$」—— 实测会误杀「化學元素發現年表」，那是个真条目。
#   本模式只排除「标题本身就是一个年份/日期」，不排除「某主题的年表」。
# 人名截断：间隔号后紧跟括号/标点/句子成分，说明姓氏丢了（spec.md §10.1）
#   命中：马拉拉·（图）遭到…       ← 姓氏「优素福扎伊」丢失
#   不命中：「1·2」火灾、8·10 事件  ← 这是日期型事件名，不是人名
# 实测 15057 条 events 里 0 命中 —— 截断只在 selected 端点出现过
TRUNC_RE = re.compile(r'·(?=（|\(|，|。|、|；|$|遭|于|被|将|率|在)')

# 「句首丢主语」的特征：以连词起头，或「，（图）」紧跟逗号 ——
# 上游 selected 端点把人名/国名整个吞掉后留下的痕迹（§10.1c）
# 「和」后面紧跟汉字也可能是正常词（和谐式客机、和平公投）——
# 只有「和」「与」单独作连词、后接的不是常见词头时才算残缺。
# 用否定前瞻排除实测踩到的几个：和谐/和平/和解/与会
BROKEN_RE = re.compile(r'^(?:(?:和(?!谐|平|解|约|议))|(?:与(?!会|其))|及|、|，)|，（图）')

# 「句中人名被吞掉」的特征。上游 selected 端点把人名的一半吞掉后，
# 留下一个无法成立的孤立间隔号（§10.1c 的另一种表现）。三种判据：
#
#   1. 间隔号紧邻标点或句子边界 —— 「软禁总统·。」
#   2. 间隔号后紧跟虚词 —— 「阿道夫·的密谋案」。「的与和之等」这类
#      虚词绝不可能是人名的一部分，所以一定是名字被吞了
#   3. 间隔号前是称谓 —— 「田径运动员·海因斯」。以「员家师」结尾的
#      是身份称谓，不是姓氏
#
# ⚠ 不能简单写成「间隔号前后非汉字」—— 实测会误判三类合法用法：
#     乔治·H·W·布什   E·C·西格   OJ·辛普森
#   缩写字母本身就不是汉字。判据 1 只认「贴着标点」，而合法人名的
#   间隔号两侧一定有字、不会贴标点，所以不误伤。
#
# ⚠ 判据 3 的字集是**逐字实测**定出来的，不能凭语感扩充：
#     员 2 条、家 20 条、师 1 条  → 全部确为残缺
#     士 21 条                    → **全部是误判**：詹姆士·库克、
#                                   托马士·索尔普 ——「士」是音译名的
#                                   一部分，不是称谓
#     长 0 条                     → 无证据，不收
#   所以只收「员家师」。这正是 §10.1 记过三次的同一个坑：中文没有
#   词边界，任何能当词素的字都必须先验证再入规则。
BROKEN_MID_RE = re.compile(
    r'·(?=[，。、）]|$)'            # 1. 贴标点或在句尾
    r'|(?:^|[，。、（])·'           # 1. 在句首或贴在标点后
    r'|·(?=[的与和之等])'           # 2. 后接虚词
    r'|(?<=[员家师])·'              # 3. 前为称谓（逐字实测，见上）
)


def is_broken_text(t):
    """正文是否残缺 —— 句首丢主语（BROKEN_RE）或句中丢人名（BROKEN_MID_RE）。"""
    return bool(BROKEN_RE.search(t) or BROKEN_MID_RE.search(t))


# 关联实体最多留几个 —— 卡片底部一行放得下的数量
MAX_LINKS = 4

# 「事件型条目」的特征词。用于挑选最能**描述这件事**的主条目（spec.md §6.4b）
#
# 背景：API 的 pages[] 没有「哪一条是本事件的条目」这种标记，
# 顺序也不代表相关度。实测 15.8% 的事件里，第一个条目是人物或地名，
# 而列表后面才有真正描述该事件的条目：
#   「能登半岛发生 7.6 地震」 pages[0]=石川县，但列表里有「2024年能登半岛地震」
#   「卡斯特罗领导革命军控制哈瓦那」 pages[0]=菲德尔·卡斯特罗，但有「古巴革命」
# 所以按特征词给条目打分，挑最像「事件本身」的那个当主链接。
EVENT_TITLE_HINTS = (
    '战争', '战役', '事件', '革命', '条约', '协定', '公约', '宣言', '运动',
    '惨案', '危机', '起义', '政变', '暴动', '屠杀', '会议', '大会', '峰会',
    '空难', '地震', '海啸', '飓风', '台风', '爆炸', '火灾', '沉没', '坠毁',
    '选举', '公投', '条例', '法案', '计划', '任务', '号', '杯', '奥运',
    '锦标赛', '博览会', '危机', '封锁', '围城', '远征', '登陆',
    # 繁体变体 —— 标题不转简体（§6.4c），所以两套都要有
    '戰爭', '戰役', '條約', '協定', '公約', '運動', '慘案', '危機',
    '起義', '政變', '暴動', '屠殺', '會議', '大會', '峰會', '空難',
    '海嘯', '颱風', '火災', '沉沒', '墜毀', '選舉', '條例', '計劃',
    '任務', '錦標賽', '博覽會', '封鎖', '圍城', '遠征', '登陸',
)

# 「泛指概念条目」—— 描述一个制度／类别／列表，**不是某一天发生的事**。
#
# 实测教训：「圣马利诺确立成文宪法」被链到「共和立憲制」，
# 那是讲政体概念的条目，与 10/08 这一天毫无关系。
#
# ⚠ 一律用 ≥2 字的词。初版图省事放了单字「制」「学」，
#   结果「抵制美貨運動」「鄧伯蘭小學大屠殺」被误判成概念条目 ——
#   中文子串匹配没有词边界，单字模式必然误伤（§5.2 已经踩过一次）。
CONCEPT_TITLE_PENALTY = (
    '列表', '一览', '一覽', '年表', '分类', '分類', '概述', '总览', '總覽',
    '制度', '主义', '主義', '立憲制', '立宪制', '共和制', '君主制',
)


def s2(text):
    """
    繁→简。API 同一响应里繁简混排，364/364 天都命中（spec.md §2.2）。

    ⚠ opencc **不是幂等的**，必须反复转到不动点。
    它是词组优先的转换器，一次 convert 只能解开一层：

        《科學怪人》於倫敦…
          pass1 → 《科学怪人》於伦敦…   ← 「於」未转
          pass2 → 《科学怪人》于伦敦…   ← 周围变简体后才匹配上「於伦敦」规则

    实测：单次 convert 后 366 天里有 7 天残留繁体「於」，转到不动点后降到 1 天。
    """
    if not text:
        return ''
    s = text
    for _ in range(4):                 # 实测 2 轮足够，留余量
        nxt = _CC.convert(s)
        if nxt == s:
            break
        s = nxt
    return _fix_residual(s)


# 不动点后仍可能残留的字。opencc 为保护专名（姓氏「於」、古语「於戏」）
# 在某些上下文下不转「於」，但本项目文本里它全部出现在介词位置，
# 规范简体写作「于」。实测残留 1 例：「…各国反对，於穆鲁罗阿环礁…」
_RESIDUAL = {'於': '于'}


def _fix_residual(s):
    """
    补掉 opencc 到不动点后仍残留的字。

    ⚠ 这是**有损**的保守修正，只处理在本语料中可确证的字。
    「於」作为姓氏时会被误改，但维基事件文本里没有出现过姓於的人物。
    若将来加入新语料，须重新核验此表。
    """
    for a, b in _RESIDUAL.items():
        s = s.replace(a, b)
    return s


def all_days():
    """366 天，含 2/29。用闰年 2024 枚举。"""
    out = []
    for m in range(1, 13):
        for d in range(1, calendar.monthrange(2024, m)[1] + 1):
            out.append(f'{m:02d}-{d:02d}')
    return out


def fetch(kind, day):
    """
    抓一个端点。

    429/5xx 退避重试。⚠ **优先听服务端的 `retry-after` 响应头** ——
    实测它给出 28–38 秒，远大于任何合理的客户端指数退避起点。
    自己猜退避时长只会白白耗尽重试次数（实测 1.2s 起点的指数退避
    在第 11 个请求后全军覆没）。
    """
    mm, dd = day.split('-')
    url = API.format(type=kind, mm=mm, dd=dd)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    for attempt in range(MAX_RETRY):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRY - 1:
                ra = e.headers.get('retry-after')
                if ra:
                    try:
                        wait = min(float(ra) + 1, RETRY_AFTER_CAP)
                    except ValueError:
                        wait = REQ_INTERVAL * (2 ** attempt)
                else:
                    wait = REQ_INTERVAL * (2 ** attempt)
                print(f'    {kind} {day} HTTP {e.code}，等 {wait:.0f}s'
                      f'（retry-after={ra}）', flush=True)
                time.sleep(wait)
                continue
            raise RuntimeError(f'HTTP {e.code}') from e
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < MAX_RETRY - 1:
                time.sleep(REQ_INTERVAL * (2 ** attempt))
                continue
            raise RuntimeError(str(e)) from e
    raise RuntimeError('重试耗尽')


def load_events(day):
    """events：优先读 survey_notes.py 建好的缓存，缺了才现抓。"""
    path = os.path.join(CACHE_DIR, f'{day}.json')
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f).get('events', []), True
    data = fetch('events', day)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    return data.get('events', []), False


def load_selected(day):
    """selected：survey_notes.py 没抓过，自建缓存目录以便重跑免费。"""
    path = os.path.join(CACHE_SEL_DIR, f'{day}.json')
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f).get('selected', []), True
    data = fetch('selected', day)
    os.makedirs(CACHE_SEL_DIR, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    return data.get('selected', []), False


def pick_main_title(titles, text):
    """
    挑出**确定在描述这件事**的条目作主链接 `u`；挑不出就返回 None。

    ⚠ 这个函数刻意保守。先后试过两版「总能挑出最贴切的一个」，
      都失败了，实测原因：

        深蓝对卡斯帕罗夫  —— 正确答案，但**根本不在正文里**，无词汇信号
        凤凰剧院 vs 威尼斯 —— 得分差 0.05，纯噪音
        香港回归          —— 正确答案，同样不在正文里

      全年统计：**只有 29% 的事件存在可靠信号**（某个候选标题含年份
      或事件型词），剩下 71% 无论怎么打分都是猜。
      而猜错的代价很具体 —— 读者点「详情」想看这件事，
      看到的却是「中华人民共和国」或「共和立憲制」的总览条目。

      所以只认强信号，认不出就不给主链接，把全部关联条目平等列在底部
      让读者自己选。**少给一个链接，远好过给一个误导的链接。**

    强信号：
      +5  标题含年份（「2024年能登半岛地震」「1964年夏季奥林匹克运动会」）
      +4  标题含事件型特征词（战役/地震/革命/条约/屠杀…）
      -4  标题含泛指概念词（列表/制度/主义…）—— 这类不是「某天发生的事」

    阈值 ≥4：必须至少命中一个强信号。
    """
    if not titles:
        return None

    def score(t):
        s = 0.0
        # ⚠ 纯年份标题不算事件信号。「前539年」也能匹配 \d{3,4}年，
        #   于是「居鲁士攻占巴比伦」的详情一度指向整年大事记 ——
        #   正好是这条 +5 规则想排除的反面。先排除纯日期标题。
        if YEAR_RE.match(t):
            return -10
        if re.search(r'\d{3,4}年', t):
            s += 5
        if any(h in t for h in EVENT_TITLE_HINTS):
            s += 4
        if any(p in t for p in CONCEPT_TITLE_PENALTY):
            s -= 4
        # 同分时取较长的（更具体），但长度本身不足以入选
        s += min(len(t), 12) / 12 * 0.4
        return s

    best = max(titles, key=score)
    return best if score(best) >= 4 else None


# 「（图）」是维基「历史上的今天」栏目的「见配图」标记。本站不显示
# 任何图片，所以它是死文本（全年 220 处）—— 在 slim() 里就删掉，
# 而不是事后用脚本改数据：改数据的话没有标志位，重跑本脚本又会取回
# API 原文，实测踩过。参见 scripts/strip_tu_marker.py（一次性清历史数据）。
#
# ⚠ 只删恰好四个字。宽松写法会吃掉 07-10「铃木一朗（西雅图水手）」里的球队名。
# ⚠ 「·（图）」要整段删 —— 那个「·」连着一个被上游丢掉的名字，
#   只删「（图）」会留下「乔治·的《弥赛亚》」这种悬空间隔号（实测 3 条）。
TU_RE = re.compile(r'·?（图）')


def strip_tu(text):
    """删掉「（图）」及其前面可能悬空的间隔号。"""
    return TU_RE.sub('', text)


def slim(raw):
    """
    一条原始事件 → 产物格式（spec.md §6.1）。

    只存条目**标题**，不存 URL —— 完整 percent-encoded URL 约 84 字节，
    标题约 18 字节，差 5 倍。前端用 encodeURIComponent 还原（spec.md §6.4）。

    ⚠ **条目标题绝不做繁简转换。** 标题是维基的条目标识符，不是正文 ——
      `市場花園行動` 转成 `市场花园行动` 后那个条目根本不存在，链接 404。
      实测抽查 60 个标题有 11 个因此失效（18%）。
      正文（`t`）必须转简体给读者看；标题（`u`/`l`）必须保持原样给 URL 用。
      两者目的不同，不能一起处理。
    """
    titles = []
    for p in raw.get('pages') or []:
        # 不转简体 —— 见上方警告
        t = (p.get('title') or '').strip()
        if t and not YEAR_RE.match(s2(t)) and t not in titles:
            titles.append(t)

    item = {
        'y': raw.get('year'),          # API 直接提供，无需从文本解析
        't': strip_tu(s2(raw.get('text', ''))),
        'src': 'wiki',
    }
    # 补回被截断的人名（spec.md §10.1）。实测 24 条里 13 条可自动补回
    #
    # ⚠ 传**转成简体**的标题 —— titles 本身保持维基原样（可能是繁体，
    #   因为 URL 要用），但这里是把人名插进已转简体的正文，
    #   不转换会在简体句子里留下「卡西姆·蘇萊曼尼」这种混排。
    item['t'], n_fixed = repair_truncated_names(
        item['t'], [s2(t) for t in titles])
    if n_fixed:
        item['_fixed'] = n_fixed       # 供统计，写文件前剔除

    if titles:
        # u = 确定在描述这件事的条目，**可能为 None**（见 pick_main_title）
        # l = 其余关联条目（见 §6.4b）
        main = pick_main_title(titles, item['t'])
        others = [t for t in titles if t != main][:MAX_LINKS]
        if main:
            item['u'] = main
        if others:
            item['l'] = others

        # 显示用的简体变体。标题本身必须保持维基原样（URL 要用），
        # 但读者读简体 —— 所以预生成时另存一份转换后的文字。
        # 只在与原标题不同时才写，避免 366 个文件白白变大。
        if main:
            main_disp = s2(main)
            if main_disp != main:
                item['ud'] = main_disp
        if others:
            others_disp = [s2(t) for t in others]
            if others_disp != others:
                item['ld'] = others_disp
    return item


def is_hand_edited(item):
    """人工编辑过的标志：写了 why、notes、sensitive，或 src 改成了 own。

    ⚠ 还要认「正文补过空书名号」—— scripts/fill_empty_titles.py 把
      「音乐剧《》首次在百老汇上演」补成「音乐剧《音乐之声》…」，
      但这条既没有 why 也没有 sensitive，src 仍是 wiki。实测：不加
      这条判断，重跑本脚本会把补好的标题**静默改回《》**。
      标志用 `filled_title` 字段，由该脚本写入。
      注意它**不进** DERIVED_FIELDS —— DERIVED_FIELDS 里的字段连
      `--force` 都保留，而补全的标题应该允许 `--force` 冲掉重来。
    """
    return bool(item.get('why') or item.get('notes')
                or item.get('sensitive') or item.get('filled_title')
                or item.get('src') == 'own')


# 由其他脚本写入、本脚本不该覆盖的字段
#
# ⚠ `tag` 由 scripts/tag_events.py 写入。本脚本重跑时若不保留，
#   标签会被静默清空，前端的分类筛选栏就空了 —— 实测踩过一次。
#   所以 --force 也必须保留这些字段，只重算 API 来源的部分。
DERIVED_FIELDS = ('tag',)

# 人工写的字段 —— 重跑时必须保留这些，其余（u / l / ud / ld / y）
# 都是 API 派生的结构字段，一律用新算出来的值。
#
# ⚠ `t` 在列表里，因为补全空书名号（§10.1c）改的就是正文。
#   但这也意味着：上游若真的修了正文，带标志位的条目不会自动更新 ——
#   这是有意的取舍，`--force` 可以覆盖。
MANUAL_FIELDS = ('t', 'why', 'notes', 'sensitive', 'filled_title', 'src')


def repair_truncated_names(text, titles):
    """
    补回被截断的人名（spec.md §10.1）。

    API 的 selected 文本偶尔把人名的姓氏丢掉，只留「名·」：

        「德国政治人物阿道夫·在监狱中口述…」      ← 「希特勒」丢了
         pages: ['阿道夫·希特勒', '我的奋斗']       ← 全名在这里

    做法：对每个「X·」出现处，在关联条目标题里找以「X·」开头的条目，
    用其全名替换。实测 24 条截断里 **22 条可补**，另 2 条 pages[] 里
    确实没有该人物条目（马拉拉、约翰·加尔文），只能人工修。

    ⚠ 保守策略：
      - 只在**恰好一个**候选标题匹配时替换，多于一个则跳过（避免猜错）
      - 候选标题须含「·」（人名特征），排除「日内瓦」这类地名
      - 括号后缀如「_(新泽西州)」在上游已被剔除，这里不处理
    """
    if '·' not in text or not titles:
        return text, 0

    persons = [t for t in titles if '·' in t]
    if not persons:
        return text, 0

    fixed = 0
    # 从后往前替换，避免下标因长度变化而失效
    for m in reversed(list(TRUNC_RE.finditer(text))):
        dot = m.start()                      # 「·」的位置
        # 往前取最多 6 个汉字作为「名」，逐步缩短找唯一匹配
        for back in range(1, 7):
            if dot - back < 0:
                break
            given = text[dot - back:dot + 1]          # 含尾部「·」
            cands = [p for p in persons if p.startswith(given)]
            if len(cands) == 1:
                text = text[:dot - back] + cands[0] + text[dot + 1:]
                fixed += 1
                break
            if len(cands) == 0:
                continue                      # 名取短了，再往前取一个字
            # len > 1：歧义，放弃这一处
            break
    return text, fixed


def repair_from_events_twin(selected, events):
    """
    用 `events` 里的完好孪生条目补回 `selected` 的残缺正文（spec.md §10.1c）。

    上游 `selected` 端点**自己**会丢字，而同一天的 `events` 端点同一件事
    却是完整的。实测对照 09-04：

        selected: 「和在美国加利福尼亚州成立开发搜寻引擎的Google（图）公司。」
        events:   「赖利·佩吉和谢尔盖·布林在美国加利福尼亚州门洛公园成立…」
                   ↑ 主语在这里

    这不是本项目的加工失误 —— `.cache/selected/` 的原始响应就是残缺的
    （已逐条核对）。所以能修：拿 events 的全文替换。

    ⚠ 判据为什么不靠「正文看起来残缺」
    ───────────────────────────────────
    前几版用正则找残缺特征（句首连词、孤立间隔号……），只能发现**留下
    标点痕迹**的那一类。实测绝大多数丢字是**无痕**的：

        现: 德国地质学家提出大陆漂移学说
        孪: 德国地质学家阿尔弗雷德·韦格纳提出大陆漂移学说

    句子语法完整、标点正常，正则无从下手 —— 正则版只找到 13 条，
    而实际有 656 条。所以判据改成**和孪生比**，不再看单句像不像残缺：

      1. 年份相同
      2. 整句相似度 ≥0.80（difflib）—— 确认是同一件事
      3. 孪生比现文本长 ≥3 字 —— 确认孪生**确实多了内容**

    门槛来自实测：13 条有标点痕迹的残缺 × 全部同年孪生，正确配对
    相似度 0.53–0.98，唯一的错误配对是 0.15（01-20 把「小布什就任
    第43任美国总统」配给了埃斯特拉达那条）。0.80 比两者间的空隙更保守。

    长度判据不可省 —— 有些孪生是把人名**删掉**而非补回：
        01-06「美国发明家·和阿尔弗莱德·维尔」→ 孪生「美国发明家和…」
        12-02「·布托正式就任巴基斯坦总理」    → 孪生「正式就任…」
    这两条相似度高达 0.98／0.95，只有长度能挡住。

    比长度前要先去掉「（图）」—— 孪生没有这个标记，不去掉会误挡。

    实测全年 1,830 条精选中 **656 条**被补回（36%）—— 这个比例说明丢字
    是上游 `selected` 端点的常态，不是偶发。其中绝大多数孪生只是**多了
    字**（纯插入），少数另有措辞差异（水门事件/水门案 这类同义变体）。
    """
    if not selected or not events:
        return 0

    fixed = 0
    for item in selected:
        # 去掉（图）后再比 —— 它是上游的配图标记，本站不渲染图片，
        # 孪生里也没有，留着会让长度与相似度判断都偏掉
        cur = item['t'].replace('（图）', '')
        # 本身已有可见残缺痕迹的，门槛放宽到 0.45。
        #
        # 为什么要分两档：句首主语被吞掉时，丢的往往是一长串人名
        # （「赖利·佩吉和谢尔盖·布林」12 字），剩下的文本只占原句六成，
        # 相似度自然低 —— 实测 09-04 Google 那条只有 0.79，用统一的
        # 0.80 门槛会把它挡掉（这是重写时实际造成的回退，审查发现）。
        # 这类条目有标点痕迹佐证「确实残缺」，可以容忍更低的相似度；
        # 无痕的那一类没有佐证，必须守住 0.80。
        threshold = 0.45 if is_broken_text(item['t']) else 0.80
        best = None
        for ev in events:
            if ev['y'] != item['y']:
                continue
            ratio = difflib.SequenceMatcher(None, cur, ev['t']).ratio()
            if best is None or ratio > best[0]:
                best = (ratio, ev)
        if best is None:
            continue
        ratio, ev = best
        if ratio < threshold or len(ev['t']) - len(cur) < 3:
            continue
        # 孪生自身若仍有可见残缺痕迹，换过去等于用一个残缺换另一个
        if is_broken_text(ev['t']):
            continue
        item['t'] = ev['t']
        # 关联条目也一并取用 —— events 那条的 pages 更完整
        if ev.get('u'):
            item['u'] = ev['u']
            item.pop('ud', None)
            if ev.get('ud'):
                item['ud'] = ev['ud']
        if ev.get('l'):
            item['l'] = ev['l']
            item.pop('ld', None)
            if ev.get('ld'):
                item['ld'] = ev['ld']
        fixed += 1
    return fixed


def dedup_events_against_selected(selected, events):
    """
    从 `events` 里移除已出现在 `selected` 的事件（spec.md §6.5）。

    两个端点**不是互斥的**：`events` 是当日全部事件，`selected` 是维基
    编者从其中挑出的精选。页面把精选置顶、其余折叠在下面，若不去重，
    同一件事会先在精选里出现、再在「全部事件」里出现一次。

    实测：366 天里 **365 天**存在重复，共 1,313 条完全相同。

    ⚠ 只按「正文完全相同」去重不够 —— 另有 **299 条**同年、相似度
    ≥0.90 但文本微异，仅差一个配图标记或地区词：

        精选: 德国、法国…正式启用欧元（图）。
        其余: 德国、法国…正式启用欧元。          ← 少了（图）

        精选: 义大利北部奇斯帕达纳共和国…
        其余: 意大利北部奇斯帕达纳共和国…        ← 义/意 地区词

    所以用两道判据：
      1. 去掉「（图）」后正文完全相同
      2. 同年且相似度 ≥0.90

    门槛 0.90 的依据：同年不同事件的相似度实测远低于此（§10.1c-2 测过
    同类配对，错误配对低至 0.15）；而真正的重复都在 0.94 以上。

    ⚠ 必须在 `repair_from_events_twin()` **之后**调用 ——
    补回残缺正文要用 events 里的孪生条目，先去重会把孪生删掉。
    """
    if not selected or not events:
        return 0

    sel_norm = {e['t'].replace('（图）', ''): e['y'] for e in selected}
    kept, removed = [], 0
    for ev in events:
        probe = ev['t'].replace('（图）', '')
        if probe in sel_norm:
            removed += 1
            continue
        dup = False
        for s in selected:
            if s['y'] != ev['y']:
                continue
            a = s['t'].replace('（图）', '')
            if difflib.SequenceMatcher(None, a, probe).ratio() >= 0.90:
                dup = True
                break
        if dup:
            removed += 1
        else:
            kept.append(ev)
    events[:] = kept
    return removed


def merge_idempotent(fresh, existing, force=False, group=None):
    """
    幂等合并（spec.md §7.1）：重跑不冲掉人工改写，也不清空派生字段。

    按 (y, t 前 12 字) 配对 —— 文本可能被人工改写，所以用前缀而非全文。
    配到的旧条目若已人工编辑，整条保留，只补 API 新增的结构字段。
    `tag` 这类派生字段**无论是否人工编辑都保留**（见 DERIVED_FIELDS）。

    ⚠ 前缀配对有个盲区：**改写发生在前 12 字之内就配不上**。
      实测 11-16「音乐剧《》首次在百老汇上演」补成「音乐剧《音乐之声》…」
      后，前 12 字从「音乐剧《》首次在百老汇上」变成「音乐剧《音乐之声》首次在」，
      旧条目永远匹配不到，is_hand_edited() 根本没机会被问到，补全被静默冲掉。
      所以第一轮前缀配对失败后，要再用「同年 + 去掉空标记后的正文」兜一次。

    ⚠ 兜底键必须**拒绝歧义匹配**。实测 05-22 同一天有两条近重复：
          精选  …制作的《吃豆人》在东京发行。            ← 补全过
          更多  …制作的《吃豆人》在东京发行，为1980年代…
      两条的兜底键都是「日本南梦宫游戏设计师岩谷」，dict 后写覆盖前写，
      结果精选那条的补全被配到 events 上，补全被冲掉。
      因此兜底键只在**全天唯一**时才用；一旦有两条撞上同一个键，
      两条都不进兜底表 —— 配不上顶多退回「用新数据」，配错则会改错条目。
    """
    if not existing:
        return fresh, 0

    def strip_marks(s):
        """抹掉空书名号/引号里的内容，让补全前后的正文可比。"""
        return re.sub(r'《[^》]*》', '《》', re.sub(r'「[^」]*」', '「」', s or ''))

    old_map = {}
    old_alt = {}      # 兜底键：同年 + 抹掉标记内容后的前 12 字
    alt_dupes = set()  # 撞键的兜底键 —— 有歧义就不能用，见上面注释
    # ⚠ 兜底表只收**当前这一组**的旧条目。05-22 的两条近重复分别在
    #   selected 和 events，正文前 12 字完全相同 —— 任何基于前缀的键都
    #   分不开，能分开的只有组别。调用方本来就是按组调用的，把组传进来
    #   即可；不限定组的话 events 的条目会覆盖 selected 的同键条目。
    groups = (group,) if group else ('selected', 'events')
    for grp in groups:
        for it in existing.get(grp) or []:
            old_map[(it.get('y'), (it.get('t') or '')[:12])] = it
            alt_key = (it.get('y'), strip_marks(it.get('t'))[:12])
            if alt_key in old_alt:
                alt_dupes.add(alt_key)
            old_alt[alt_key] = it
    for k in alt_dupes:          # 歧义的一律剔除，宁可配不上也不配错
        old_alt.pop(k, None)

    out = []
    kept = 0
    for it in fresh:
        old = old_map.get((it.get('y'), (it.get('t') or '')[:12]))
        if old is None:
            # 前缀没配上，可能是补全改了前 12 字 —— 用抹掉标记的形式再试
            old = old_alt.get((it.get('y'), strip_marks(it.get('t'))[:12]))
        if not old:
            out.append(it)
            continue
        if is_hand_edited(old) and not force:
            # ⚠ 只保留**人工写的**字段，结构字段一律用新的。
            #   旧写法是 merged = dict(it); merged.update(old) —— old 全盘
            #   覆盖，连 u / l 也一起盖回去。于是修好了 pick_main_title
            #   的纯年份 bug 之后，带 sensitive 的条目仍然留着
            #   「详情：前217年」—— 因为那条被整体保留了。
            #   u / l / ud / ld / y 都是 API 派生的，没有人工内容，
            #   必须跟着新逻辑走。
            merged = dict(it)
            for k in MANUAL_FIELDS:
                if k in old:
                    merged[k] = old[k]
            out.append(merged)
            kept += 1
        else:
            # 未人工编辑：用新数据，但保住派生字段（tag 等）
            for field in DERIVED_FIELDS:
                if field in old:
                    it[field] = old[field]
            out.append(it)
    return out, kept


def main():
    ap = argparse.ArgumentParser(description='预生成 366 天事件数据')
    ap.add_argument('--days', help='只处理这些日期，MM-DD 逗号分隔')
    ap.add_argument('--retry-failed', action='store_true',
                    help='只跑 .cache/raw/ 里缺失的日期')
    ap.add_argument('--dry-run', action='store_true', help='不写文件')
    ap.add_argument('--force', action='store_true',
                    help='覆盖人工编辑过的条目（危险）')
    ap.add_argument('--skip-selected', action='store_true',
                    help='只生成 events，跳过 selected 的 366 次请求')
    args = ap.parse_args()

    if args.days:
        days = [d.strip() for d in args.days.split(',')]
    elif args.retry_failed:
        days = [d for d in all_days()
                if not os.path.exists(os.path.join(CACHE_DIR, f'{d}.json'))]
        if not days:
            print('events 缓存完整，无需补跑')
        else:
            print(f'待补跑 events：{", ".join(days)}')
    else:
        days = all_days()

    if not args.dry_run:
        os.makedirs(OUT_DIR, exist_ok=True)

    today = date.today().isoformat()
    t0 = time.time()
    stats = {'ok': 0, 'failed': [], 'cached': 0, 'fetched': 0,
             'kept': 0, 'trunc': [], 'fixed': 0, 'bytes': 0}

    for i, day in enumerate(days, 1):
        try:
            events, ev_cached = load_events(day)
            stats['cached' if ev_cached else 'fetched'] += 1
            if not ev_cached:
                time.sleep(REQ_INTERVAL)

            selected = []
            if not args.skip_selected:
                selected, sel_cached = load_selected(day)
                if not sel_cached:
                    time.sleep(REQ_INTERVAL)

            doc = {
                'date': day,
                'generated': today,
                'selected': [slim(e) for e in selected],
                'events': [slim(e) for e in events],
            }

            # 上游 selected 端点丢主语的，用同日 events 的完好孪生补回
            # 必须在 slim() **之后**：比对的是加工后的简体正文（§10.1c）
            n_twin = repair_from_events_twin(doc['selected'], doc['events'])
            stats['twin'] = stats.get('twin', 0) + n_twin

            # 去掉 events 里已出现在 selected 的事件（§6.5）
            # ⚠ 必须在 repair_from_events_twin() **之后** ——
            #   补回残缺正文要用 events 里的孪生，先去重会把孪生删掉
            n_dup = dedup_events_against_selected(doc['selected'], doc['events'])
            stats['dup'] = stats.get('dup', 0) + n_dup

            doc = {
                'date': day,
                'generated': today,
                'selected': doc['selected'],
                'events': doc['events'],
            }

            # 人名截断：自动补回的计数 ＋ 补不回的留给人工（spec.md §10.1）
            for group in ('selected', 'events'):
                for it in doc[group]:
                    stats['fixed'] += it.pop('_fixed', 0)
                    if TRUNC_RE.search(it['t']):
                        stats['trunc'].append(f"{day} {it['t'][:48]}")

            # 即使 --force 也要读旧文件 —— 派生字段（tag）必须保留，
            # 否则 tag_events.py 的成果会被静默清空
            out_path = os.path.join(OUT_DIR, f'{day}.json')
            if os.path.exists(out_path):
                with open(out_path, encoding='utf-8') as f:
                    existing = json.load(f)
                for group in ('selected', 'events'):
                    doc[group], kept = merge_idempotent(
                        doc[group], existing, force=args.force, group=group)
                    stats['kept'] += kept

            blob = json.dumps(doc, ensure_ascii=False, separators=(',', ':'))
            stats['bytes'] += len(blob.encode())
            if not args.dry_run:
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write(blob)
            stats['ok'] += 1

        except RuntimeError as e:
            stats['failed'].append(f'{day} ({e})')
            print(f'  ❌ {day} 失败：{e}', flush=True)

        if i % 30 == 0 or i == len(days):
            print(f'  [{i:3d}/{len(days)}] {day}  '
                  f'缓存 {stats["cached"]} 下载 {stats["fetched"]}  '
                  f'{time.time() - t0:.0f}s', flush=True)

    print('\n' + '=' * 56)
    if stats.get('twin'):
        print(f'selected 残缺正文已用 events 孪生补回 {stats["twin"]} 条（§10.1c）')
    if stats.get('dup'):
        print(f'events 里与精选重复的已移除 {stats["dup"]} 条（§6.5）')
    print(f'成功 {stats["ok"]} / {len(days)} 天'
          + ('（dry-run，未写文件）' if args.dry_run else ''))
    print(f'体积 {stats["bytes"] / 1024 / 1024:.2f} MB')
    if stats['kept']:
        print(f'保留人工编辑的条目 {stats["kept"]} 条')
    if stats['failed']:
        print(f'\n❌ 失败 {len(stats["failed"])} 天：')
        for f in stats['failed']:
            print(f'   {f}')
        print('   用 --days 单独补跑')
    if stats['fixed']:
        print(f'✅ 自动补回被截断的人名 {stats["fixed"]} 处')
    if stats['trunc']:
        print(f'\n⚠ 仍有人名截断 {len(stats["trunc"])} 条，'
              f'pages[] 里无对应人物条目，需人工修（spec.md §10.1）：')
        for t in stats['trunc'][:15]:
            print(f'   {t}')
        if len(stats['trunc']) > 15:
            print(f'   …另有 {len(stats["trunc"]) - 15} 条')
    return 1 if stats['failed'] else 0


if __name__ == '__main__':
    sys.exit(main())
