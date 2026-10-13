#!/usr/bin/env python3
"""删掉正文里的「（图）」（spec §10.1d）。

为什么删
--------
「（图）」是维基百科「历史上的今天」栏目的「见配图」标记 —— 那个栏目
每天配一张图。**本站不显示任何图片**，所以这四个字对读者毫无意义，
是纯粹的死文本。全年 220 处。

两个必须小心的地方（都实测过）
------------------------------
**一、只删恰好「（图）」四个字。** 宽松写法 `（[^）]*图[^）]*）` 会吃掉
07-10 的「铃木一朗（西雅图水手）击出…」—— 那是球队名。这是本项目
第 N 次踩中文无词边界的坑，所以模式写死为 `（图）`。

**二、「·（图）」会留下悬空的「·」。** 实测 3 条，全是上游人名截断：

    美国发明家·（图）和阿尔弗莱德·维尔…   → 删后「发明家·和阿尔弗莱德」
    德国作曲家乔治·（图）的《弥赛亚》…     → 删后「乔治·的《弥赛亚》」
    巴基斯坦社会活动家马拉拉·（图）遭到…   → 删后「马拉拉·遭到」

这三条的「·」本来连着一个被上游丢掉的名字。删「（图）」时要把这个
悬空的「·」一起去掉，否则读者看到的是更奇怪的「乔治·的」。
注意**不是**把名字补上 —— 补名是另一件事（需要人工核对链接），
这里只做「不要让删图标记产生新的怪字符」。

全量实测：删除后不产生双标点、句首标点等新问题（已有的 2 处双句号
是上游原有缺陷，与本脚本无关）。
"""
import json
import glob
import re
import sys

# 恰好四个字，不用宽松匹配 —— 见模块注释
TU = re.compile(r'（图）')
# 悬空的间隔号：人名被上游截断后，「·」紧贴着（图）
TU_AFTER_DOT = re.compile(r'·（图）')


def clean(text):
    """返回 (新文本, 是否动过)。先处理「·（图）」，再处理普通「（图）」。"""
    out = TU_AFTER_DOT.sub('', text)   # 「·（图）」整体删掉，不留悬空的 ·
    out = TU.sub('', out)
    return out, out != text


def main():
    apply = '--apply' in sys.argv
    changed = dots = files = 0
    samples = []

    for path in sorted(glob.glob('data/otd/*.json')):
        day = json.load(open(path, encoding='utf-8'))
        dirty = False
        for group in ('selected', 'events'):
            for item in day[group]:
                had_dot = bool(TU_AFTER_DOT.search(item['t']))
                new, hit = clean(item['t'])
                if not hit:
                    continue
                changed += 1
                if had_dot:
                    dots += 1
                if len(samples) < 8:
                    samples.append((path[-10:-5], item['t'], new))
                if apply:
                    item['t'] = new
                    dirty = True
        if dirty:
            files += 1
            if apply:
                with open(path, 'w', encoding='utf-8') as fh:
                    json.dump(day, fh, ensure_ascii=False, separators=(',', ':'))

    print(f"{'已写入' if apply else '预演（未写入）'}")
    print(f'  清掉「（图）」的条目 : {changed}')
    print(f'  其中连带去掉悬空「·」: {dots}')
    print(f'  涉及文件             : {files}')
    print('\n样本：')
    for day, old, new in samples:
        print(f'  {day}\n   前: {old[:70]}\n   后: {new[:70]}')


if __name__ == '__main__':
    main()
