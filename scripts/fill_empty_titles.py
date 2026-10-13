#!/usr/bin/env python3
"""补全正文里的空书名号《》与空引号「」（spec §10.1 的上游残缺）。

为什么能补
----------
上游 `events`/`selected` 两个端点都丢了作品名，但**该条自己的链接列表
里还在**。例：

    t : 枪手袭击法国巴黎《》总部，造成12人死亡。
    l : ['阿拉伯半島基地組織', '查理週刊總部槍擊案', '巴黎']

spec 把这 29 条记作「两个端点都没有标题」—— 对**正文**成立，对**链接
元数据**不成立。所以比原先记录的更可修。

为什么不能自动
--------------
链接按出现顺序排列，不按角色。02-16 同时给出「联合国气候变化框架公约」
和「京都议定书」，哪个该填进空书名号只能靠读句子判断。因此本表是
**逐条人工指定**的，脚本只负责：

  1. 核对该词确实出现在这条自己的链接里（有据，不是凭空写）
  2. 用简体显示形式（`ld`）而不是 `l` —— `l` 保持维基原始形式，
     可能是繁体（克藍瑪對克藍瑪）
  3. 去掉消歧义后缀 —— 正文要《弥赛亚》不要《弥赛亚_(亨德尔)》
  4. 只替换**第一个**空标记，且替换前确认该条正文未被改过

不提议的 5 条
-------------
  01-07  链接只有「查理週刊總部槍擊案」（事件名），填进去成了
         「袭击…枪击案总部」，循环。正确答案《查理周刊》数据里没有。
  03-19  链接只有「奥斯卡最佳影片奖」，无候选。
  09-08  「主题为「」（阅读过去，书写未来）」—— 括注就是主题的译文，
         引号里缺的是英文原文。
  11-19  链接只有「葛底斯堡」（地名），正确答案是《葛底斯堡演说》。
  12-21  链接有「白雪公主」，但 u 已指向该片，填了与「详情」重复。
"""
import json
import glob
import re
import sys

# (日期, 组, 索引) -> 要填入的作品名。逐条人工指定，见模块注释。
FILLS = {
    ('01-04', 'selected', 3): '被夺走的十二年',
    ('02-09', 'events', 28): '斯瓦尔巴条约',
    ('02-16', 'selected', 0): '联合国气候变化框架公约',
    ('03-24', 'events', 19): '克蓝玛对克蓝玛',
    ('04-10', 'events', 19): '了不起的盖茨比',
    ('04-13', 'selected', 2): '弥赛亚',
    ('04-25', 'events', 16): '杜兰朵',
    ('05-18', 'selected', 1): '不扩散核武器条约',
    ('05-22', 'selected', 1): '吃豆人',
    ('05-23', 'events', 10): '闪灵',
    ('07-11', 'selected', 1): '杀死一只知更鸟',
    ('07-29', 'selected', 1): '美国国家航空暨太空法案',
    ('08-06', 'selected', 1): '万维网',
    ('08-23', 'selected', 2): '苏德互不侵犯条约',
    ('08-28', 'selected', 0): '我有一个梦想',
    ('09-02', 'selected', 1): '降伏文书',
    ('09-13', 'events', 18): '超级马力欧兄弟',
    ('10-05', 'selected', 2): '铁金刚勇破神秘岛',
    ('10-05', 'events', 18): '铁金刚勇破神秘岛',
    ('11-16', 'events', 24): '音乐之声',
    ('11-26', 'selected', 1): '北非谍影',
    ('12-17', 'selected', 1): '辛普森一家',
    ('12-18', 'selected', 3): '胡桃夹子',
    ('12-19', 'events', 30): '小气财神',
}

EMPTY_MARK = re.compile(r'《》|「」')


def link_pool(item):
    """该条所有链接的简体显示形式，去掉消歧义后缀。"""
    out = []
    pairs = [(item.get('l') or []), (item.get('ld') or [])]
    for lst in pairs:
        for s in lst:
            out.append(re.sub(r'_\(.*?\)$', '', s).replace('_', ' '))
    for key in ('u', 'ud'):
        if item.get(key):
            out.append(re.sub(r'_\(.*?\)$', '', item[key]).replace('_', ' '))
    return out


def main():
    apply = '--apply' in sys.argv
    filled = skipped = 0
    problems = []

    for path in sorted(glob.glob('data/otd/*.json')):
        day = json.load(open(path, encoding='utf-8'))
        date = path[-10:-5]
        dirty = False
        for group in ('selected', 'events'):
            for idx, item in enumerate(day[group]):
                key = (date, group, idx)
                if key not in FILLS:
                    continue
                want = FILLS[key]
                text = item['t']
                m = EMPTY_MARK.search(text)
                if not m:
                    # 已经补过，或条目位置变了 —— 两种都要报出来
                    if want in text:
                        skipped += 1
                        # ⚠ 即使正文已补好，也要确保标志位在 —— 否则
                        #   gen_otd.py 重跑时认不出，会把标题改回《》。
                        #   实测踩过：首轮补全时脚本还没有这个字段，
                        #   第二轮跑到这里走的是「跳过」分支，23 条就一直
                        #   缺着标志位，直到重跑把它们全冲掉才暴露。
                        if item.get('filled_title') is not True:
                            if apply:
                                item['filled_title'] = True
                                dirty = True
                            problems.append(f'{key} 正文已补但缺 filled_title，已补标志')
                    else:
                        problems.append(f'{key} 找不到空标记，且正文无「{want}」')
                    continue
                # 核对：该词必须出现在这条自己的链接里
                if want not in ' '.join(link_pool(item)):
                    problems.append(f'{key} 「{want}」不在该条链接中 —— 拒绝填入')
                    continue
                mark = m.group(0)
                new = text[:m.start()] + mark[0] + want + mark[1] + text[m.end():]
                print(f'{date} [{group[:3]}#{idx}] 《{want}》')
                print(f'   前: {text[:76]}')
                print(f'   后: {new[:76]}')
                filled += 1
                if apply:
                    item['t'] = new
                    # 标志位：让 gen_otd.py 的 is_hand_edited() 认出这条
                    # 已人工补过，重跑时不要改回《》。实测不加这个字段
                    # 补全会被静默覆盖。
                    item['filled_title'] = True
                    dirty = True
        if dirty and apply:
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(day, fh, ensure_ascii=False, separators=(',', ':'))

    print(f"\n{'已写入' if apply else '预演（未写入）'}")
    print(f'  补全 : {filled} 条')
    print(f'  已补过跳过 : {skipped} 条')
    if problems:
        print(f'  ⚠ 问题 {len(problems)} 处：')
        for p in problems:
            print(f'      {p}')


if __name__ == '__main__':
    main()
