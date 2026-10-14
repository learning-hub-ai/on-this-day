#!/usr/bin/env python3
"""把「不是这一天那件事」的主链接降级为关联条目（spec §6.4f）。

规则（用户定的）
----------------
**详情与历史事件是一对一的**：`u` 必须描述**那一天那件事**。其它相关
介绍 —— 一场持续数年的战争、一个机构、一个概念 —— 属于底部的关联
条目（`l`），不该挂在「详情」上。

为什么必须跨全年判断
--------------------
`pick_main_title()` 一次只看一条，看不出某个标题被别的日期也用着。
而「不是某天那件事」最可测的信号恰恰是**跨日期复用**。

判据：跨**年份** ＋ 被 ≥4 个日期引用
------------------------------------
试过「被 ≥N 个日期共用就降级」，不行 —— 它分不开两种情况：

  阿波罗8号      12-21 发射 / 12-24 拍《地出》/ 12-27 返回，**全部 1968**
                 → 一次任务的几个节点，每条都确实在描述那次任务，不该降级
  南北战争        36 个日期，**1859–1866**
                 → 一场持续战争，不可能在描述其中任何一天，该降级

只加「跨年」也不行 —— 单一事物也会有跨年的两个节点：

  新视野号                 2006 发射 / 2019 飞越终极远境
  区域全面经济伙伴关系协定   2020 签订 / 2022 生效
  2006年跨年曼谷连环爆炸案   2006-12-31 / 2007-01-01（跨年夜）
  神舟四号                 2002 发射 / 2003 返回

这些都是「某一个事物的两个里程碑」，详情指向它是对的。

**所以判据是两条同时成立：跨多个年份，且被 ≥4 个不同日期引用。**
109 种命中项已全部逐条过目（见 git log），无一例外是战争、条约、
机构或长期任务 —— 包括和平号空间站（1995–2001）、卡西尼-惠更斯号
（1997–2006）这类确实跨年运行多年的任务。

被 2–3 个日期引用的跨年标题（186 种）**不动** —— 那一带混着
「单一事物的两个节点」，没有可靠判据分开，硬降级会误伤。
同年多日期的 62 种同样不动。两者都留给人工过目。

降级而非删除
------------
`u` 降级后插到 `l` 的**最前面**，并把 `l` 上限临时放宽一位 ——
实测有条目的 `l` 已经满了（MAX_LINKS=4），直接 append 会被截断，
读者反而彻底看不到这个链接。原本能点的东西不该因为一次降级消失。

⚠ 必须在 `gen_otd.py` **之后**跑，且重跑 `gen_otd.py` 会冲掉降级
-----------------------------------------------------------------
本脚本要统计「某标题被多少个日期/年份引用」，这需要**全年数据齐了**
才能算 —— `gen_otd.py` 逐天处理，中途拿不到这个信息。所以它只能是
独立的后续阶段，和 `tag_events.py` 同类。

代价是：重跑 `gen_otd.py` 会按 `pick_main_title()` 重新给出 `u`，
把降级冲掉（实测 01-11 的「南北战争」又回来了）。

**流程固定为**（任一步改了数据，后面的都要重跑）：

    gen_otd.py → demote_generic_links.py --apply → tag_events.py

不给降级的条目加「人工编辑」标志位 —— 那会把整条冻结，上游修了
正文也不会更新。重跑后补一遍降级，成本只有几秒。
"""
import json
import glob
import collections
import sys

OTD = 'data/otd'
# 降级后 l 的上限（平时 4）。多留一个位置给被降级的那个。
MAX_LINKS_AFTER_DEMOTE = 5
# 被多少个不同日期引用才算长期主题。见模块注释：
# 2–3 个那一带混着「单一事物的两个里程碑」，不能一刀切。
MIN_DATES = 4


def display_of(item):
    """u 的显示形式（简体优先）—— 统计要按显示形式归并。"""
    return item.get('ud') or item.get('u')


def survey():
    """统计每个主链接被哪些日期、哪些年份用过。

    ⚠ **统计口径必须与降级状态无关**，否则脚本不可重复运行。
      只看 `u` 不行：本脚本把 `u` 降级进 `l`，跑过一次后再统计，
      原本被 36 个日期引用的「南北战争」只剩 1 个还挂在 `u` 上，
      看起来就不像长期主题了 —— 重跑 `gen_otd.py` 后它不再被降级，
      「详情：南北战争」又回来了（实测）。

      把整个 `l` 都计入也不行：那会把「巴黎」（77 个日期）、
      「美国」（152 个日期）这类普通关联实体也算进来，降级面从
      109 种暴涨到 1,644 种 —— 它们本来就不是详情候选。

      正确口径：`u` ＋ **本脚本降级过的那些**（`dm` 字段记录）。
    """
    info = collections.defaultdict(lambda: {'dates': set(), 'years': set()})
    for path in sorted(glob.glob(f'{OTD}/*.json')):
        day = json.load(open(path, encoding='utf-8'))
        for group in ('selected', 'events'):
            for item in day[group]:
                names = set()
                u = display_of(item)
                if u:
                    names.add(u)
                # 曾被本脚本降级的标题 —— 记在 dm 里，统计要算上
                if item.get('dm'):
                    names.add(item['dm'])
                for name in names:
                    info[name]['dates'].add(day['date'])
                    info[name]['years'].add(item.get('y'))
    return info


def main():
    apply = '--apply' in sys.argv
    verbose = '--verbose' in sys.argv

    info = survey()
    # 两条同时成立才降级：跨多个年份 ＋ 被 ≥MIN_DATES 个日期引用。
    # 单看跨年会误伤「新视野号」（2006 发射 / 2019 飞越）这类
    # 单一事物的两个里程碑。
    cross_year = {u for u, v in info.items()
                  if len(v['years']) > 1 and len(v['dates']) >= MIN_DATES}
    # 以下两类**不动**，留给人工过目：
    #   跨年但只被 2–3 个日期引用 —— 混着单一事物的里程碑
    #   同年多日期 —— 一次任务/灾难的多个节点（阿波罗8号、舟曲泥石流）
    borderline = {u for u, v in info.items()
                  if len(v['years']) > 1 and 2 <= len(v['dates']) < MIN_DATES}
    same_year_multi = {u for u, v in info.items()
                       if len(v['years']) == 1 and len(v['dates']) >= 3}

    demoted = truncated = files = 0
    samples = []

    for path in sorted(glob.glob(f'{OTD}/*.json')):
        day = json.load(open(path, encoding='utf-8'))
        dirty = False
        for group in ('selected', 'events'):
            for item in day[group]:
                disp = display_of(item)
                if not disp or disp not in cross_year:
                    continue
                u, ud = item.get('u'), item.get('ud')
                links = list(item.get('l') or [])
                lds = list(item.get('ld') or [])
                had_ld = bool(lds)

                # 插到最前面 —— 它原本是「详情」，优先级高于其它关联条目
                if u and u not in links:
                    links.insert(0, u)
                    # ld 必须与 l 等长同序（§6.4c）。原本没有 ld 的，
                    # 只有在降级项自身需要显示变体时才建表。
                    if had_ld:
                        lds.insert(0, ud or u)
                    elif ud and ud != u:
                        lds = [ud] + links[1:]
                if len(links) > MAX_LINKS_AFTER_DEMOTE:
                    truncated += 1
                    links = links[:MAX_LINKS_AFTER_DEMOTE]
                    if lds:
                        lds = lds[:MAX_LINKS_AFTER_DEMOTE]

                if len(samples) < 10:
                    samples.append((day['date'], disp,
                                    len(info[disp]['years']),
                                    sorted(info[disp]['years'])[0],
                                    sorted(info[disp]['years'])[-1],
                                    item['t'][:44]))
                demoted += 1
                dirty = True
                if apply:
                    item.pop('u', None)
                    item.pop('ud', None)
                    # 记下被降级的标题 —— survey() 要靠它保持统计口径稳定，
                    # 否则降级一次之后统计结果就变了（见 survey 的注释）
                    item['dm'] = disp
                    item['l'] = links
                    if lds and lds != links:
                        item['ld'] = lds
                    else:
                        item.pop('ld', None)
        if dirty:
            files += 1
            if apply:
                with open(path, 'w', encoding='utf-8') as fh:
                    json.dump(day, fh, ensure_ascii=False,
                              separators=(',', ':'))

    print(f"{'已写入' if apply else '预演（未写入）'}")
    print(f'  长期主题（跨年 ＋ ≥{MIN_DATES} 个日期）: {len(cross_year)} 种 → 降级')
    print(f'  降级的条目       : {demoted}')
    print(f'  因上限被截断     : {truncated}')
    print(f'  涉及文件         : {files}')
    print(f'\n  以下不动，留给人工过目：')
    print(f'    跨年但只 2–3 个日期（混着单一事物的里程碑）: {len(borderline)} 种')
    print(f'    同年多日期（一次任务的多个节点）            : {len(same_year_multi)} 种')

    if verbose:
        print('\n── 降级样本 ──')
        for date, u, ny, lo, hi, t in samples:
            print(f'  {date} 《{u}》{ny} 个年份（{lo}–{hi}）')
            print(f'        {t}')
        print('\n── 保留但需人工过目的 62 种 ──')
        for u in sorted(same_year_multi,
                        key=lambda x: -len(info[x]['dates'])):
            v = info[u]
            print(f'  {u:30s} {len(v["dates"])} 个日期，{list(v["years"])[0]} 年')


if __name__ == '__main__':
    main()
