#!/usr/bin/env python3
"""把上游丢掉的人名补回正文（spec §10.1e）。

问题
----
上游 `selected` 端点会丢掉人名，而且**不留任何标点伤痕**：

    义大利探险家第一次抵达美洲，在加勒比地区的圣萨尔瓦多岛登陆。
                ↑ 这里本该有「克里斯托弗·哥伦布」

句子语法完整，所以 `TRUNC_RE`（靠 `·（`、`·，` 之类的伤痕识别）抓不到。
这是本项目第七次吃中文无词边界的亏 —— 前几次见 §10.1、§4.3.1、§10.1d。

`repair_from_events_twin()` 能修的是同日 `events` 里有完整孪生的那些
（已修 670 条）。本脚本处理**没有孪生**、但该条自己的链接列表里有人名
的情况。

为什么是逐条人工指定
--------------------
插入点需要读句子才能定。三条都指向「维托里奥·埃马努埃莱二世」，
但位置完全不同：

    义大利国王逝世…              名字在「国王」前（是死掉的那位）
    萨丁尼亚王国国王宣布自己为…    名字在「国王」后
    王国议会宣布…成为首任国王      名字在句尾「成为」前

所以表是手写的，脚本只负责三件事：
  1. 核对该人名确实在这条自己的链接里（有据，不是凭我的记忆写）
  2. 核对插入点字符串在正文里**唯一**出现，避免插错位置
  3. 核对插入后正文里不出现重复的人名

不补的两类
----------
**正文已有该人的译名**（只是写法与链接不同）—— 补了会出现两个名字：

    邱吉尔再任首相        链接：温斯顿·丘吉尔
    萧邦因肺结核病故      链接：弗雷德里克·肖邦
    纳塞尔被选为埃及总统  链接：加麦尔·阿卜杜勒·纳赛尔
    塞拉西加冕为皇帝      链接：海尔·塞拉西一世
    约翰三世被选为国王    链接：扬三世·索别斯基

**句子缺多个名字、需重写**（本脚本只做单点插入，不改句子结构）：

    英国女王和英国首相替…揭幕        缺 2 个（伊丽莎白二世、托尼·布莱尔）
    美国副总统与苏联部长会议主席…     缺 2 个（尼克松、赫鲁晓夫）
    美国天文学家、和发现小行星90377   缺 3 个，还少一个连接词
    赖比瑞亚…担任首任总统            名字该在句首，不是「总统」后
"""
import json
import glob
import sys

# (日期, 组, 索引) -> (插入点, 要插入的人名)
# 插入点：正文里的一段字符串，人名插在它**后面**。必须在正文里唯一出现。
FILLS = {
    ('10-12', 'selected', 4): ('义大利探险家', '克里斯托弗·哥伦布'),
    ('07-29', 'selected', 1): ('美国总统', '德怀特·艾森豪威尔'),
    ('07-26', 'selected', 0): ('埃及总统', '加麦尔·阿卜杜勒·纳赛尔'),
    ('10-29', 'selected', 2): ('英国首相', '玛格丽特·撒切尔'),
    ('12-06', 'events', 2): ('美国总统', '唐纳·川普'),
    ('10-09', 'selected', 0): ('巴基斯坦社会活动家', '玛拉拉·优素福扎伊'),
    ('08-06', 'selected', 1): ('英国电脑科学家', '蒂姆·伯纳斯-李'),
    ('06-10', 'selected', 3): ('总理', '贝尼托·墨索里尼'),
    ('01-16', 'selected', 0): ('团结党领袖', '埃伦·约翰逊·瑟利夫'),
    ('11-23', 'events', 7): ('乔治亚总统', '爱德华·谢瓦尔德纳泽'),
    # 「义大利国王逝世」—— 名字在「国王」**前**，指的是死掉的那位
    ('01-09', 'selected', 1): ('义大利国王', '维托里奥·埃马努埃莱二世'),
}


def link_pool(item):
    """该条所有链接（含显示变体），用于核对人名有据。"""
    out = []
    for key in ('l', 'ld'):
        out.extend(item.get(key) or [])
    for key in ('u', 'ud'):
        if item.get(key):
            out.append(item[key])
    return ' '.join(out)


def main():
    apply = '--apply' in sys.argv
    filled = skipped = 0
    problems = []

    for path in sorted(glob.glob('data/otd/*.json')):
        day = json.load(open(path, encoding='utf-8'))
        date = day['date']
        dirty = False
        for group in ('selected', 'events'):
            for idx, item in enumerate(day[group]):
                key = (date, group, idx)
                if key not in FILLS:
                    continue
                anchor, name = FILLS[key]
                text = item['t']

                # 已经补过了？
                if name in text:
                    skipped += 1
                    if item.get('filled_name') is not True and apply:
                        item['filled_name'] = True
                        dirty = True
                    continue

                # 核对一：人名必须在这条自己的链接里
                if name not in link_pool(item):
                    problems.append(f'{key} 「{name}」不在该条链接中 —— 拒绝插入')
                    continue
                # 核对二：插入点必须唯一，否则会插错位置
                n = text.count(anchor)
                if n != 1:
                    problems.append(f'{key} 插入点「{anchor}」出现 {n} 次 —— 拒绝插入')
                    continue
                # 核对三：插入后不得出现重复人名
                new = text.replace(anchor, anchor + name, 1)
                if new.count(name) != 1:
                    problems.append(f'{key} 插入后「{name}」出现多次 —— 拒绝')
                    continue

                print(f'{date} [{group[:3]}#{idx}]')
                print(f'   前: {text[:76]}')
                print(f'   后: {new[:76]}')
                filled += 1
                if apply:
                    item['t'] = new
                    # 与 filled_title 同理：标志位让 gen_otd.py 的
                    # is_hand_edited() 认出这条，重跑时不要改回去
                    item['filled_name'] = True
                    dirty = True
        if dirty and apply:
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(day, fh, ensure_ascii=False, separators=(',', ':'))

    print(f"\n{'已写入' if apply else '预演（未写入）'}")
    print(f'  补回人名   : {filled} 条')
    print(f'  已补过跳过 : {skipped} 条')
    if problems:
        print(f'  ⚠ 问题 {len(problems)} 处：')
        for p in problems:
            print(f'      {p}')


if __name__ == '__main__':
    main()
