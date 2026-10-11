#!/usr/bin/env python3
"""
tag_events.py — 为事件打领域标签（预生成时跑一次）

背景：spec.md §5 否决了**前端实时关键词匹配**，理由是实测 62% 落入
「其他」、多标签 15%、体育 95% 误判。本脚本不是把那个方案搬回来，
而是换了三处做法：

  1. **离线打标**，结果写进 data/otd/*.json 的 tag 字段。
     前端只读 tag，零运行时开销、零依赖 —— 这是 §4.2 列的「方案 2」。
  2. **用 pages[] 的条目标题作信号**，不只看句子。实测 99.5% 的事件
     至少有一个关联条目，信号远比一句话丰富。
  3. **计分制取最高分，不输出多标签**，且关键词**最短 2 字**。
     旧方案的体育 95% 误判全来自裸单字「队」匹配到「军队/部队/舰队」。

用法：
    python3 scripts/tag_events.py --dry-run     # 只统计，不写文件
    python3 scripts/tag_events.py               # 写入 tag 字段
    python3 scripts/tag_events.py --sample 12   # 每类抽样人工核验
"""

import argparse
import collections
import json
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OTD_DIR = os.path.join(ROOT, 'data', 'otd')

YEAR_RE = re.compile(r'^-?\d+年$|^\d+年代$|^公元前\d+年$')

# 分类顺序即前端标签栏顺序。「其他」不在此表，是兜底
#
# titles —— 整条匹配关联条目标题，命中权重最高（3 分）
# kw     —— 词级模式，**一律 ≥2 字**。出现在正文 +2，出现在条目标题 +1
# neg    —— 否决词，命中扣 3 分。专治「航空母舰 ≠ 航空航天」这类
CATEGORIES = {
    '航空航天': {
        'icon': '✦',
        'titles': {'美国国家航空航天局', '阿波罗计划', '国际太空站', '航天飞机',
                   '礼炮号空间站', '和平号空间站', '苏联太空计划'},
        'kw': ['航天', '太空', '宇航', '火箭', '卫星', '探测器', '空间站', '太空站',
               '登月', '月球', '飞船', '运载火箭', '发射升空', '太空望远镜',
               '太阳系', '彗星', '陨石', '火星', '木星', '金星', '土星',
               '天文台', '望远镜', '日食', '月食', '小行星', '星系',
               '天文学家', '超新星', '星云', '恒星', '行星', '海王星', '冥王星'],
        # 「航空母舰」「航空公司」「空军」都含「空」但属军事/其他
        'neg': ['航空母舰', '航空公司', '空军', '空袭'],
    },
    '科技': {
        'icon': '✧',
        'titles': {'互联网', '万维网', '苹果公司', '微软', '国际商业机器',
                   '诺贝尔物理学奖', '诺贝尔化学奖', '诺贝尔生理学或医学奖'},
        'kw': ['计算机', '电脑', '互联网', '网际网络', '万维网', '软件', '操作系统',
               '处理器', '半导体', '人工智能', '量子', '核反应堆', '疫苗',
               '抗生素', '青霉素', '专利', '发明', '实验室', '电报',
               '留声机', '摄影', 'X射线', 'DNA', '基因组', '基因图谱', '物理学',
               '化学奖', '医学奖', '试管', '克隆', '显微镜', '电话专利',
               '行动电话', '移动电话',
               # 只认科学类奖项。裸「诺贝尔」会把和平奖、文学奖一并吸进来 ——
               # 和平奖是政治、文学奖是文艺，都不是科技（实测 8 + 10 条）
               '诺贝尔物理学奖', '诺贝尔化学奖', '诺贝尔生理学或医学奖'],
        # 急救电话、打人事件 等不是科技
        'neg': ['急救', '打人', '殴打', '生产线'],
    },
    '政治': {
        'icon': '◉',
        'titles': {'联合国', '美国总统', '中国共产党', '中国国民党', '欧洲联盟',
                   '国际联盟', '美国最高法院', '诺贝尔和平奖'},
        'kw': ['总统', '首相', '宪法', '选举', '议会', '国会', '条约', '联合国',
               '独立', '建国', '内阁', '就任', '上任', '辞职', '弹劾',
               '公投', '法案', '修正案', '联邦', '共和国', '签署', '缔结',
               '建交', '断交', '外交', '大使', '废除', '政变', '执政', '君主',
               '临时政府', '联合政府', '流亡政府', '政府成立', '组建政府',
               '加冕', '继位', '退位', '废黜', '诏书', '立法', '判决',
               '最高法院', '示威', '抗议', '罢工',
               '诺贝尔和平奖', '和平奖'],
        'neg': [],
    },
    '军事': {
        'icon': '◈',
        'titles': {'第二次世界大战', '第一次世界大战', '美国武装部队',
                   '中国人民解放军', '日本军', '纳粹德国'},
        'kw': ['战争', '战役', '战斗', '军队', '部队', '轰炸', '空袭', '投降',
               '停战', '开战', '占领', '攻占', '攻克', '入侵', '起义', '叛乱',
               '叛军', '围城', '海战', '舰队', '核试验', '氢弹', '原子弹',
               '歼灭', '屠杀', '俘虏', '撤军', '宣战', '军阀', '北伐', '远征',
               '游击', '民兵', '阵亡', '航空母舰', '战舰', '军舰'],
        'neg': [],
    },
    '文化艺术': {
        'icon': '◇',
        'titles': {'奥斯卡金像奖', '格莱美奖', '诺贝尔文学奖', '百老汇'},
        'kw': ['电影', '影片', '上映', '首映', '首演', '音乐', '乐团', '交响曲',
               '歌剧', '专辑', '唱片', '小说', '文学', '诗集', '画家',
               '绘画', '雕塑', '博物馆', '美术馆', '剧院', '戏剧', '舞蹈',
               '奥斯卡', '金像奖', '格莱美', '文学奖', '报纸', '杂志', '创刊',
               '出版', '问世',
               '建筑师', '落成', '竣工', '大教堂'],
        # 出版 单独太弱：《日本出版法》《出版物》属新闻管制，是政治不是文艺
        # 天文观测含「首次观测」等词易被误收，交给航空航天
        'neg': ['出版法', '出版物', '新闻管制', '天文学家', '超新星', '星云',
                '观测到', '诽谤'],
    },
    '体育': {
        'icon': '◎',
        'titles': {'国际奥林匹克委员会', '国际足联世界杯',
                   '夏季奥林匹克运动会', '冬季奥林匹克运动会'},
        # ⚠ 绝不用裸「队」—— 旧方案 95% 误判的根源（军队/部队/舰队/探险队）
        'kw': ['奥运', '奥林匹克', '世界杯', '世界锦标赛', '锦标赛', '冠军',
               '金牌', '银牌', '铜牌', '足球', '篮球', '棒球', '网球', '田径',
               '游泳', '拳击', '赛车', '大奖赛', '联赛',
               '球队', '运动会', '职棒', '总冠军'],
        # 破纪录/世界纪录 已移除 —— 飓风季、气温也「破纪录」
        # 空难里提到球员不是体育事件
        'neg': ['坠毁', '空难', '班机', '飓风季', '热带风暴', '热带气旋'],
    },
    '人物': {
        'icon': '○',
        'titles': set(),
        'kw': ['出生', '逝世', '诞辰', '去世', '病逝', '遇刺', '刺杀', '暗杀',
               '谋杀', '遇害', '自杀', '处决', '殉职'],
        # 生产线/驶出 等工业用语会误配到人物
        'neg': ['生产线', '驶出'],
    },
}

OTHER = '其他'
OTHER_ICON = '·'
MIN_SCORE = 2          # 低于此分视为证据不足 → 其他


def titles_of(event):
    """关联条目标题，剔除年份条目。"""
    raw = [event.get('u')] + (event.get('l') or [])
    return [t for t in raw if t and not YEAR_RE.match(t)]


def classify(event):
    """
    返回 (分类, 得分)。取最高分的单一分类 —— **不输出多标签**。

    多标签是旧方案的第二个病灶：实测 15% 的事件被打上 2–3 个标签，
    其中「以色列军队撤出西奈半岛 → [军事, 体育]」这类明显错误。
    对 10 岁读者，一条事件属于一个领域足够了。
    """
    text = event.get('t') or ''
    titles = titles_of(event)
    tset = set(titles)

    best, best_score = OTHER, 0
    for cat, rule in CATEGORIES.items():
        score = 3 * len(tset & rule['titles'])
        for kw in rule['kw']:
            if kw in text:
                score += 2
            elif any(kw in t for t in titles):
                score += 1
        for neg in rule['neg']:
            if neg in text:
                score -= 3
        if score > best_score:
            best, best_score = cat, score

    return (best, best_score) if best_score >= MIN_SCORE else (OTHER, best_score)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='只统计，不写文件')
    ap.add_argument('--sample', type=int, metavar='N',
                    help='每类随机抽 N 条，供人工核验精度')
    args = ap.parse_args()

    files = sorted(f for f in os.listdir(OTD_DIR) if f.endswith('.json'))
    counts = collections.Counter()
    per_day = collections.defaultdict(collections.Counter)
    samples = collections.defaultdict(list)
    total = 0

    for name in files:
        path = os.path.join(OTD_DIR, name)
        with open(path, encoding='utf-8') as f:
            day = json.load(f)

        for group in ('selected', 'events'):
            for event in day.get(group) or []:
                cat, score = classify(event)
                event['tag'] = cat
                counts[cat] += 1
                per_day[day['date']][cat] += 1
                samples[cat].append((day['date'], score, event.get('t', '')))
                total += 1

        if not args.dry_run:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(day, f, ensure_ascii=False, separators=(',', ':'))

    print(f'事件 {total} 条'
          + ('（dry-run，未写文件）' if args.dry_run else '，tag 已写入'))
    print()
    order = list(CATEGORIES) + [OTHER]
    for cat in order:
        n = counts[cat]
        empty = sum(1 for d in per_day.values() if d[cat] == 0)
        icon = CATEGORIES.get(cat, {}).get('icon', OTHER_ICON)
        print(f'  {icon} {cat:6s} {n:6d}  {n / total * 100:5.1f}%  '
              f'日均 {n / 366:5.1f}  空白 {empty:3d}/366 天')

    print(f'\n「其他」占比 {counts[OTHER] / total * 100:.1f}%'
          f'  —— 旧的前端关键词法实测 62%（spec.md §5.1）')

    if args.sample:
        print('\n' + '=' * 60)
        print('随机抽样（人工核验精度）')
        rnd = random.Random(42)
        for cat in order:
            pool = samples[cat]
            if not pool:
                continue
            print(f'\n【{cat}】{len(pool)} 条，抽 {min(args.sample, len(pool))}：')
            for date, score, text in rnd.sample(pool, min(args.sample, len(pool))):
                print(f'  [{score:2d}] {date} {text[:62]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
