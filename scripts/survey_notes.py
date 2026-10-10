#!/usr/bin/env python3
"""统计全年注音候选词 —— 用 jieba 分词 ＋ 词性过滤。

为什么重写
----------
第一版用「生字前后各扩一个字」猜词边界，切出「斯于纳夫普」这种碎片，
候选数虚高六倍；收紧规则后又把「奴隶」「叙利亚」连实词一起误排除。
**从生字反推词边界这条路不通**，改用正经分词器。

现在的流程
----------
    事件原文 → 转简体 → jieba 词性标注 → 含生字的词
             → 按词性剔除专名（nr 人名 / ns 地名 / nt 机构 / nz 其他专名）
             → 剩下的是注音候选

词性过滤比手写字表可靠：「康涅狄格」「穆罕默德」整词被标成专名，
不必再猜哪个字是音译。

⚠ 仍有误判（见 docs/survey.json 的 misclassified 字段举例）：
  - 「穆罕默德」「约翰」被标 nrt（音译人名）而非 nr，需补进专名词性集合
  - 「大坝」「暨」偶尔被误标专名
  所以产物是**给人看的候选表**，不直接进 data/otd/。

用法
----
    python3 scripts/survey_notes.py              # 全年 366 天
    python3 scripts/survey_notes.py --limit 30   # 先跑 30 天

API 会限流（实测连续第 11 个请求返回 429），请求间隔 ≥1.1s 并指数退避。
全年约 8–12 分钟。原始响应缓存在 .cache/raw/，重跑不重新下载。
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, '.cache', 'raw')
HANZI_DATA = os.path.expanduser('~/learning-hub-ai/chinese/hanzi-go/data')
API = 'https://api.wikimedia.org/feed/v1/wikipedia/zh/onthisday/events/{:02d}/{:02d}'
UA = 'on-this-day-survey/1.0 (https://github.com/learning-hub-ai; smilings.lu@gmail.com)'

HAN_WORD = re.compile(r'^[\u4e00-\u9fff]+$')
HAN_CHAR = re.compile(r'[\u4e00-\u9fff]')

# jieba 词性里属于专名的 —— 这些整词跳过，不注音
# nr/nrt/nrfg 人名（nrt 多为音译人名）, ns 地名, nt 机构, nz 其他专名
PROPER_POS = {'nr', 'nrt', 'nrfg', 'ns', 'nt', 'nz'}

DAYS_PER_MONTH = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

# ⚠ 必须先转简体再比对识字表 —— zh.wikipedia 同一响应里繁简混排（规格书 §4.1）。
# 不转的话「國」「殺」「獎」全算生字，统计数虚高好几倍。
try:
    from opencc import OpenCC
    _CC = OpenCC('t2s')
except ImportError:
    sys.exit("缺 opencc：pip install opencc-python-reimplemented")

try:
    import jieba.posseg as pseg
    import jieba
    jieba.setLogLevel('ERROR')
except ImportError:
    sys.exit("缺 jieba：pip install jieba")


def to_simp(s):
    return _CC.convert(s)


def grade6_chars():
    """读 HanziGo 一到六年级识字表 —— 判断「生字」的基准（实测 2849 字）。"""
    known, missing = set(), []
    for g in range(1, 7):
        for s in (1, 2):
            p = os.path.join(HANZI_DATA, f'grade{g}-semester{s}.json')
            if not os.path.exists(p):
                missing.append(os.path.basename(p))
                continue
            with open(p, encoding='utf-8') as fh:
                d = json.load(fh)
            for les in d.get('lessons', []):
                for ch in les.get('chars', []):
                    if ch.get('char'):
                        known.add(ch['char'])
    if missing:
        print(f"⚠ 缺少学期文件: {', '.join(missing)}", file=sys.stderr)
    return known


def fetch(month, day, delay=1.1):
    """取一天的 events，带缓存与 429 退避。返回 (data, 是否命中缓存)。"""
    os.makedirs(CACHE, exist_ok=True)
    cp = os.path.join(CACHE, f'{month:02d}-{day:02d}.json')
    if os.path.exists(cp):
        with open(cp, encoding='utf-8') as fh:
            return json.load(fh), True

    url = API.format(month, day)
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            with open(cp, 'w', encoding='utf-8') as fh:
                json.dump(data, fh, ensure_ascii=False)
            time.sleep(delay)
            return data, False
        except urllib.error.HTTPError as e:
            if e.code == 429:
                back = 2 ** attempt * 2
                print(f"  429 限流，等 {back}s…", file=sys.stderr)
                time.sleep(back)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  网络错误 {e}，等 3s…", file=sys.stderr)
            time.sleep(3)
    raise RuntimeError(f'{month:02d}/{day:02d} 重试 5 次仍失败')


def analyse(text, known):
    """一条事件 → (候选词 dict{词:词性}, 专名 set, 生字 set)。"""
    simp = to_simp(text)
    cand, proper = {}, set()
    for w, flag in pseg.cut(simp):
        if not HAN_WORD.match(w):
            continue
        if not (set(w) - known):          # 整词都认识
            continue
        if flag in PROPER_POS:
            proper.add(w)
        else:
            cand[w] = flag
    unknown_chars = set(HAN_CHAR.findall(simp)) - known
    return cand, proper, unknown_chars


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, help='只跑前 N 天')
    ap.add_argument('--delay', type=float, default=1.1)
    args = ap.parse_args()

    known = grade6_chars()
    print(f"六年级识字基准: {len(known)} 字\n")

    dates = [(m, d) for m in range(1, 13)
             for d in range(1, DAYS_PER_MONTH[m - 1] + 1)]
    if args.limit:
        dates = dates[:args.limit]

    rows, words, propers, chars = [], Counter(), Counter(), Counter()
    fetched = cached = 0
    t0 = time.time()

    for n, (m, d) in enumerate(dates, 1):
        try:
            data, hit = fetch(m, d, args.delay)
        except Exception as e:
            print(f"{m:02d}/{d:02d} 失败: {e}", file=sys.stderr)
            continue
        cached += hit
        fetched += not hit

        ev = data.get('events', [])
        day_c, day_p, day_u = {}, set(), set()
        for e in ev:
            c, p, u = analyse(e.get('text', ''), known)
            day_c.update(c)
            day_p |= p
            day_u |= u
        words.update(day_c.keys())      # 只数「出现在几天」，不要把词性当计数
        propers.update(day_p)
        chars.update(day_u)
        rows.append({'date': f'{m:02d}-{d:02d}', 'events': len(ev),
                     'cand': len(day_c), 'proper': len(day_p),
                     'unknown_chars': len(day_u)})

        if n % 30 == 0 or n == len(dates):
            print(f"  [{n:>3}/{len(dates)}] {m:02d}/{d:02d}  "
                  f"下载 {fetched} 缓存 {cached}  {time.time()-t0:.0f}s")

    if not rows:
        return 1

    def stats(key):
        xs = sorted(r[key] for r in rows)
        return (xs[0], xs[len(xs) // 2], sum(xs) / len(xs),
                xs[min(len(xs) - 1, int(len(xs) * .9))], xs[-1])

    print(f"\n{'='*64}\n全年统计（{len(rows)} 天）\n{'='*64}")
    print(f"\n{'指标':<16}{'min':>6}{'中位':>7}{'均值':>8}{'p90':>7}{'max':>7}")
    for label, key in (('每天事件数', 'events'),
                       ('每天生字种数', 'unknown_chars'),
                       ('每天候选词', 'cand'),
                       ('每天专名(跳过)', 'proper')):
        a, b, c, d9, e = stats(key)
        print(f"{label:<16}{a:>6}{b:>7}{c:>8.1f}{d9:>7}{e:>7}")

    total_day = sum(r['cand'] for r in rows)
    print(f"\n全年候选词：逐日相加 {total_day} 个，"
          f"**去重后 {len(words)} 个**")
    print(f"→ 重复率 {100*(1-len(words)/max(total_day,1)):.0f}% "
          f"——「注一次、全年复用」能省掉这部分工作")
    print(f"（另有专名 {len(propers)} 个按规则跳过，不需注音）")

    print(f"\n候选词最多的 10 天:")
    for r in sorted(rows, key=lambda x: -x['cand'])[:10]:
        print(f"  {r['date']}  事件 {r['events']:>3}  候选 {r['cand']:>3}  "
              f"专名 {r['proper']:>3}")

    print(f"\n出现最频繁的候选词（值得优先注）:")
    for w, c in words.most_common(25):
        print(f"  {w:<10} {c:>3} 天")

    out = os.path.join(ROOT, 'docs', 'survey.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump({'baseline_chars': len(known),
                   'days_surveyed': len(rows),
                   'unique_candidates': len(words),
                   'unique_propers': len(propers),
                   'days': rows,
                   'candidates': words.most_common(),
                   'propers_skipped': propers.most_common(200)},
                  fh, ensure_ascii=False, indent=1)
    print(f"\n明细写入 {os.path.relpath(out, ROOT)}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
