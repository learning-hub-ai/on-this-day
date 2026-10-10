#!/usr/bin/env python3
"""
glossary_algo_check.py — 用 Python 复刻 js/glossary.js 的匹配算法并验证。

存在原因：当前环境没有 node/deno/bun，js/glossary.test.mjs 无法执行。
本文件逐行对应 findMarks 的逻辑，跑同一批断言，用来证明**算法**正确。

⚠ 它不能替代 js/glossary.test.mjs ——
   JS 的语法错误、import 问题、DOM 相关行为都查不出来。
   有 node 的机器上务必跑一次 `node js/glossary.test.mjs`。
"""

MAX_MARKS_PER_EVENT = 3


def find_marks(text, words, max_marks=MAX_MARKS_PER_EVENT):
    """与 glossary.js findMarks 等价：贪心最长优先，不重叠。"""
    if not text or not words:
        return []
    max_len = max((len(w) for w in words), default=0)
    if max_len == 0:
        return []

    marks = []
    i = 0
    while i < len(text):
        hit = None
        for ln in range(min(max_len, len(text) - i), 0, -1):
            cand = text[i:i + ln]
            if cand in words:
                hit = {"start": i, "end": i + ln, "word": cand, **words[cand]}
                break
        if hit:
            marks.append(hit)
            i = hit["end"]
        else:
            i += 1
    return marks[:max_marks]


# ---- 与 glossary.test.mjs 完全相同的词表（取自 docs/survey.json 实测频次）----
W = {
    "签署":   {"p": "qiān shǔ",  "d": "正式签字生效", "n": 212},
    "署":     {"p": "shǔ",       "d": "官署",         "n": 12},
    "合并":   {"p": "hé bìng",   "d": "并到一起",     "n": 59},
    "并":     {"p": "bìng",      "d": "并且",         "n": 301},
    "第一届": {"p": "dì yī jiè", "d": "头一次举办",   "n": 54},
    "一届":   {"p": "yī jiè",    "d": "一次",         "n": 9},
    "届":     {"p": "jiè",       "d": "次、期",       "n": 77},
    "其后":   {"p": "qí hòu",    "d": "之后",         "n": 60},
    "其":     {"p": "qí",        "d": "他的、那个",   "n": 190},
    "颁布":   {"p": "bān bù",    "d": "正式公布",     "n": 70},
    "徭役":   {"p": "yáo yì",    "d": "官府强派的无偿劳动", "n": 1},
    "赦令":   {"p": "shè lìng",  "d": "免罪的命令",   "n": 2},
    "罹难":   {"p": "lí nàn",    "d": "遭遇灾祸死亡", "n": 99},
}

_pass = _fail = 0


def eq(actual, expected, name):
    global _pass, _fail
    if actual == expected:
        _pass += 1
        print(f"  ✅ {name}")
    else:
        _fail += 1
        print(f"  ❌ {name}\n     期望 {expected}\n     实际 {actual}")


def words_of(text, max_marks=MAX_MARKS_PER_EVENT):
    return [m["word"] for m in find_marks(text, W, max_marks)]


print("=== 最长优先（1280 对重叠关系的核心）===")
eq(words_of("签署条约"), ["签署"], "签署 不被切成 署")
eq(words_of("两国合并"), ["合并"], "合并 不被切成 并")
eq(words_of("第一届大会"), ["第一届"], "第一届 优先于 一届 和 届（三层嵌套）")
eq(words_of("其后十年"), ["其后"], "其后 优先于 其 —— 即使 其(190) 比 其后(60) 更高频")

print("\n=== 频次不影响匹配，只影响编写优先级 ===")
eq(words_of("并且合并"), ["并", "合并"], "并(301) 与 合并(59) 各自独立命中，按出现顺序")

print("\n=== 不重叠 ===")
eq([[m["start"], m["end"]] for m in find_marks("签署并颁布", W)],
   [[0, 2], [2, 3], [3, 5]], "相邻词区间首尾相接，不重叠")

print("\n=== 上限 3 个（spec.md §4.1 第 3 条）===")
eq(len(find_marks("签署颁布合并其后罹难", W)), 3, "超过 3 个时截断")
eq(words_of("签署颁布合并其后罹难"), ["签署", "颁布", "合并"], "保留文中最靠前的 3 个")
eq(len(find_marks("签署颁布合并其后罹难", W, 5)), 5, "max 可覆盖")

print("\n=== 未命中静默跳过（spec.md §6.2 第 2 条）===")
eq(find_marks("今天天气很好", W), [], "无命中返回空，不抛错")
eq(find_marks("", W), [], "空文本")
eq(find_marks("签署", {}), [], "空词表")
eq(find_marks("签署", None), [], "None 词表")

print("\n=== 真实事件文本 ===")
real = "普鲁士首相施泰因颁布法令，解除农奴对地主的人身依附，停止徭役，史称「十月赦令」。"
eq(words_of(real), ["颁布", "徭役", "赦令"], "10/09 那条事件命中 3 个词")

print("\n" + "─" * 44)
print(f"通过 {_pass} / 失败 {_fail}")
raise SystemExit(0 if _fail == 0 else 1)
