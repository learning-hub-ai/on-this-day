#!/usr/bin/env python3
"""
check_glossary.py — 词表校验

词表会从 ~90 词长到 500 词（spec.md §12.4），全靠人工审阅不现实。
本脚本把 §4.1／§6.2 的规则变成可执行的检查，每次扩充后跑一次。

用法：
    python3 scripts/check_glossary.py          # 校验 ＋ 覆盖率
    python3 scripts/check_glossary.py --next 30  # 另列出下 30 个待写候选

退出码：0 全部通过；1 有错误。可直接用于 pre-push 钩子。
"""

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GLOSSARY = os.path.join(ROOT, 'data', 'glossary.json')
EXCLUDE = os.path.join(ROOT, 'data', 'glossary-exclude.json')
SURVEY = os.path.join(ROOT, 'docs', 'survey.json')
OTD_DIR = os.path.join(ROOT, 'data', 'otd')

MAX_DEF_CHARS = 12      # 释义上限（spec.md §4.1 第 2 条）
MAX_MARKS = 3           # 一条事件最多标几个（§4.1 第 3 条）

# 拼音：声母韵母 ＋ 声调符号，音节间半角空格
PINYIN_RE = re.compile(r'^[a-zA-ZüÜāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜńňǹ]+'
                       r'( [a-zA-ZüÜāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜńňǹ]+)*$')


def check_pinyin_values(words):
    """
    用 pypinyin 核对拼音**内容**，而不只是格式。

    格式正则只能发现「写法不对」，发现不了「注音注错」——
    后者对读者的伤害更大（孩子会照着念）。

    pypinyin 未安装时跳过并提示，不让它成为硬依赖 ——
    词表校验的其余部分不需要它。
    """
    try:
        from pypinyin import pinyin, Style
    except ImportError:
        return None, '未安装 pypinyin，跳过拼音内容核对：pip install pypinyin'

    wrong = []
    for w, body in words.items():
        expect = ' '.join(x[0] for x in pinyin(w, style=Style.TONE))
        if body.get('p') != expect:
            wrong.append((w, body.get('p'), expect))
    return wrong, None


def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def excluded_words():
    """展开排除名单。键以 _ 开头的是说明，跳过。"""
    data = load_json(EXCLUDE)
    out = {}
    for group, body in data.items():
        if group.startswith('_'):
            continue
        for w in body['words']:
            out[w] = group
    return out


def find_marks(text, words, limit=MAX_MARKS):
    """与 js/glossary.js findMarks 等价：贪心最长优先，不重叠。"""
    if not text or not words:
        return []
    max_len = max(len(w) for w in words)
    marks = []
    i = 0
    while i < len(text):
        for ln in range(min(max_len, len(text) - i), 0, -1):
            if text[i:i + ln] in words:
                marks.append((i, i + ln, text[i:i + ln]))
                i += ln
                break
        else:
            i += 1
    return marks[:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--next', type=int, metavar='N',
                    help='另列出下 N 个待写候选')
    args = ap.parse_args()

    gloss = load_json(GLOSSARY)
    words = gloss['words']
    excl = excluded_words()
    errors = []
    warnings = []

    # --- 规则校验 ---
    keys = set(words)
    for w, body in words.items():
        where = f'「{w}」'
        if not body.get('p'):
            errors.append(f'{where} 缺 p（拼音）')
        elif not PINYIN_RE.match(body['p']):
            errors.append(f'{where} 拼音格式可疑：{body["p"]!r}')

        d = body.get('d')
        if not d:
            errors.append(f'{where} 缺 d（释义）')
        else:
            if len(d) > MAX_DEF_CHARS:
                errors.append(f'{where} 释义 {len(d)} 字，超过 {MAX_DEF_CHARS}')

            # 循环定义：用另一个词表条目来解释，对读者等于没解释 ——
            # 他查「屠杀」看到「大批杀害」，还得再查「杀害」
            cited = [o for o in keys if o != w and o in d]
            if cited:
                errors.append(f'{where} 释义引用了其他词表条目 {cited} —— '
                              f'循环定义，读者查了还得再查')

            # 自指：释义重复了词目 2 个以上的字，等于把词目抄了一遍
            # （重复 1 个字通常无妨：「烧毁 → 被火烧坏」里的「烧」没有简单替代）
            same = [c for c in w if c in d]
            if len(same) >= 2:
                errors.append(f'{where} 释义重复了词目的「{"".join(same)}」—— '
                              f'自指，没有真正解释')

        if w in excl:
            errors.append(f'{where} 在排除名单里（{excl[w]}），不该收录')
        if len(w) < 2:
            warnings.append(f'{where} 是单字 —— §4.1 第 1 条要求注词不注字')

    # --- 覆盖率 ---
    total = hit = marks = 0
    days_with = set()
    over_limit = 0
    for name in sorted(os.listdir(OTD_DIR)):
        day = load_json(os.path.join(OTD_DIR, name))
        for group in ('selected', 'events'):
            for item in day[group]:
                total += 1
                # 不设上限地找，用来统计有多少条会被截断
                raw = find_marks(item['t'], words, limit=99)
                if len(raw) > MAX_MARKS:
                    over_limit += 1
                m = raw[:MAX_MARKS]
                if m:
                    hit += 1
                    marks += len(m)
                    days_with.add(day['date'])

    # --- 频次覆盖（对 survey.json 的全年出现次数）---
    survey = load_json(SURVEY)
    freq = dict(survey['candidates'])
    freq_total = sum(freq.values())
    freq_covered = sum(freq.get(w, 0) for w in words)

    # --- 拼音内容核对（可选依赖）---
    wrong_pinyin, pinyin_note = check_pinyin_values(words)
    if wrong_pinyin:
        for w, mine, expect in wrong_pinyin:
            errors.append(f'「{w}」拼音可能注错：写的 {mine!r}，'
                          f'pypinyin 给 {expect!r}')

    print(f'词表 {len(words)} 词，排除名单 {len(excl)} 词\n')
    print(f'  事件命中率   {hit}/{total} = {hit / total * 100:.1f}%')
    print(f'  标记总数     {marks} 处')
    print(f'  覆盖天数     {len(days_with)}/366')
    print(f'  频次覆盖     {freq_covered}/{freq_total} = '
          f'{freq_covered / freq_total * 100:.1f}%'
          f'   ← 可注释上限 71.9%，见 spec.md §2.4.1')
    if over_limit:
        print(f'  ⓘ {over_limit} 条事件命中超过 {MAX_MARKS} 个词，'
              f'渲染时只标最靠前的 {MAX_MARKS} 个')
    if pinyin_note:
        print(f'  ⓘ {pinyin_note}')
    elif not wrong_pinyin:
        print(f'  ✓ 拼音已逐条核对（pypinyin）')

    if warnings:
        print(f'\n⚠ {len(warnings)} 条提醒：')
        for w in warnings:
            print(f'   {w}')

    if errors:
        print(f'\n❌ {len(errors)} 条错误：')
        for e in errors:
            print(f'   {e}')
        return 1

    print('\n✅ 校验通过')

    if args.next:
        have = set(words)
        todo = [(w, n) for w, n in
                sorted(survey['candidates'], key=lambda kv: -kv[1])
                if w not in have and w not in excl][:args.next]
        print(f'\n下 {len(todo)} 个待写候选：')
        for i, (w, n) in enumerate(todo, 1):
            end = '\n' if i % 10 == 0 else '  '
            print(f'{w}({n})', end=end)
        print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
