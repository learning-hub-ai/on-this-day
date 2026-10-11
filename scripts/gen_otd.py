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
YEAR_RE = re.compile(r'^-?\d+年$|^\d+年代$|^公元前\d+年$')
# 人名截断：间隔号后紧跟括号/标点/句子成分，说明姓氏丢了（spec.md §10.1）
#   命中：马拉拉·（图）遭到…       ← 姓氏「优素福扎伊」丢失
#   不命中：「1·2」火灾、8·10 事件  ← 这是日期型事件名，不是人名
# 实测 15057 条 events 里 0 命中 —— 截断只在 selected 端点出现过
TRUNC_RE = re.compile(r'·(?=（|\(|，|。|、|；|$|遭|于|被|将|率|在)')
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
    从关联条目里挑出最能**描述这件事**的一个，作为主链接 `u`。

    API 不提供「本事件的条目」标记，pages[] 的顺序也不代表相关度，
    所以只能按启发式打分：

      +4  标题含事件型特征词（战役/地震/革命/条约…）
      +2  标题整体出现在事件文本里（说明是这句话的主题）
      +1  标题较长（更具体，「2024年能登半岛地震」优于「地震」）

    ⚠ 这是启发式，会选错。但比「取第一个」好得多 ——
      实测后者在 15.8% 的事件上选了人物或地名而非事件本身。
    """
    if not titles:
        return None

    def score(t):
        s = 0
        if any(h in t for h in EVENT_TITLE_HINTS):
            s += 4
        if t in text:
            s += 2
        s += min(len(t), 12) / 12        # 长度作为弱权重，最多 +1
        return s

    return max(titles, key=score)


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
        't': s2(raw.get('text', '')),
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
        # u = 最能描述这件事的条目；l = 其余关联条目（见 §6.4b）
        main = pick_main_title(titles, item['t'])
        item['u'] = main
        others = [t for t in titles if t != main][:MAX_LINKS]
        if others:
            item['l'] = others

        # 显示用的简体变体。标题本身必须保持维基原样（URL 要用），
        # 但读者读简体 —— 所以预生成时另存一份转换后的文字。
        # 只在与原标题不同时才写，避免 366 个文件白白变大。
        main_disp = s2(main)
        if main_disp != main:
            item['ud'] = main_disp
        if others:
            others_disp = [s2(t) for t in others]
            if others_disp != others:
                item['ld'] = others_disp
    return item


def is_hand_edited(item):
    """人工编辑过的标志：写了 why、notes、sensitive，或 src 改成了 own。"""
    return bool(item.get('why') or item.get('notes')
                or item.get('sensitive') or item.get('src') == 'own')


# 由其他脚本写入、本脚本不该覆盖的字段
#
# ⚠ `tag` 由 scripts/tag_events.py 写入。本脚本重跑时若不保留，
#   标签会被静默清空，前端的分类筛选栏就空了 —— 实测踩过一次。
#   所以 --force 也必须保留这些字段，只重算 API 来源的部分。
DERIVED_FIELDS = ('tag',)


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


def merge_idempotent(fresh, existing, force=False):
    """
    幂等合并（spec.md §7.1）：重跑不冲掉人工改写，也不清空派生字段。

    按 (y, t 前 12 字) 配对 —— 文本可能被人工改写，所以用前缀而非全文。
    配到的旧条目若已人工编辑，整条保留，只补 API 新增的结构字段。
    `tag` 这类派生字段**无论是否人工编辑都保留**（见 DERIVED_FIELDS）。
    """
    if not existing:
        return fresh, 0
    old_map = {}
    for group in ('selected', 'events'):
        for it in existing.get(group) or []:
            old_map[(it.get('y'), (it.get('t') or '')[:12])] = it

    out = []
    kept = 0
    for it in fresh:
        old = old_map.get((it.get('y'), (it.get('t') or '')[:12]))
        if not old:
            out.append(it)
            continue
        if is_hand_edited(old) and not force:
            merged = dict(it)          # 先取新的结构字段（l / u）
            merged.update(old)         # 人工内容覆盖之，优先级更高
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
                        doc[group], existing, force=args.force)
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
