#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
解题 skill 验收：检查一个板块 skill 是否适合被 xingce-jiexi-all 调度、是否省 token。只读，不改文件。

用法：
    python skill_review.py "<skill 文件夹>"            # 如 ...\copilot\skills\xingce-shuliang
    python skill_review.py "<skill 文件夹>" --md      # 额外把结果写成 <skill>/验收报告.md

检查项（对照 book-to-skill 行测模式补丁和 board-skill-template.md）：
  命名与映射、frontmatter、主 SKILL.md 各节、调度节、解析写法、token 体量、
  chapters（体量 / 典型例题 / 答案）、cheatsheet（三部分）、链接、英文残留，并估算一批题的 token 开销。
"""
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SKILL_MD_MAX = 4000       # 主 SKILL.md 建议上限
CHAPTER_MAX = 3500        # 单章建议上限
CHEATSHEET_MAX = 1800
REQUIRED = [              # (关键词, 说明)
    ("适用题型", "适用题型"),
    ("解题步骤", "解题步骤（拿到一道题的 SOP）"),
    ("核心框架", "核心框架"),
    ("解析写法", "解析写法（每题解析的固定结构）"),
    ("索引", "章节索引 / 题型索引"),
    ("被 xingce-jiexi-all 调度时", "被 xingce-jiexi-all 调度时"),
]
ENGLISH_HEADINGS = ["Core Idea", "Key Takeaways", "Frameworks Introduced", "Key Concepts", "Mental Models",
                    "Anti-patterns", "Connects To", "Worked Example", "How to Use This Skill", "Scope & Limits",
                    "Chapter Index", "Topic Index", "Supporting Files"]


def tokens(text):
    cjk = len(re.findall(r"[一-鿿]", text))
    return int(cjk + (len(text) - cjk) / 3.5)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    d = Path(args[0]).expanduser().resolve()
    if d.is_file():
        d = d.parent
    f = d / "SKILL.md"
    if not f.is_file():
        sys.exit(f"找不到 {f}")
    t = f.read_text(encoding="utf-8", errors="ignore")
    ok, warn, bad, info = [], [], [], []

    # ---------------- 命名与映射
    m = re.search(r"^name:\s*[\"']?([^\"'\n]+?)[\"']?\s*$", t, re.M)
    name = m.group(1).strip() if m else ""
    (ok if name == d.name else bad).append(f"文件夹名 {d.name} / name: {name or '（缺）'}" + ("" if name == d.name else " 不一致"))
    boards = []
    bm = d.parent / "xingce-jiexi-all" / "board-map.md"
    if bm.is_file():
        for ln in bm.read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if len(cells) >= 2 and name and name in [x.strip() for x in re.split(r"[,，]", cells[1])]:
                boards.append(cells[0])
        if boards:
            ok.append(f"映射表：对应板块「{'」「'.join(boards)}」")
        else:
            bad.append("board-map.md 里没有这个 skill 名 → 总调度不会用它（名字要照映射表起，或告诉 Claude 加进映射表）")

    # ---------------- frontmatter
    fm = re.match(r"﻿?---\s*\n(.*?)\n---", t, re.S)
    fmt = fm.group(1) if fm else ""
    desc = re.search(r"^description:(.*?)(?=^\w[\w-]*:|\Z)", fmt, re.M | re.S)
    desc = desc.group(1) if desc else ""
    if not desc:
        bad.append("没有 description")
    else:
        if re.search(r"[一-鿿]", desc):
            ok.append("description 有中文关键词")
        else:
            bad.append("description 全是英文 → 中文提问时 AI 不容易选中它")
        if "xingce-jiexi-all" in desc:
            ok.append("description 写了被 xingce-jiexi-all 调度")
        else:
            warn.append("description 没提 xingce-jiexi-all 调度")
    (ok if "copilot-enabled-agents" in fmt else warn).append(
        "metadata: copilot-enabled-agents: opencode" + ("" if "copilot-enabled-agents" in fmt else " 缺失 → opencode 可能看不到它"))

    # ---------------- 主 SKILL.md 结构
    heads = re.findall(r"^#{2,3}\s+(.+)$", t, re.M)
    for kw, label in REQUIRED:
        (ok if any(kw in h for h in heads) else bad).append(f"章节「{label}」" + ("" if any(kw in h for h in heads) else " 缺失"))
    if "直接跳到本文件末尾" in t:
        ok.append("开头有调度指引（被调度时直接跳到末尾）")
    else:
        warn.append("开头缺调度指引 → AI 可能读完整个文件才找到调度节")
    disp = t.split("## 被 xingce-jiexi-all 调度时", 1)[1] if "## 被 xingce-jiexi-all 调度时" in t else ""
    for kw, label in (("next", "用 next 取题"), ("write", "用 write 写入"), ("check", "用 check 验收"),
                      ("正确答案为锚", "以正确答案为锚"), ("省 token", "省 token 规则"), ("不要摸索", "直接开始，不要摸索")):
        if disp and kw not in disp:
            warn.append(f"调度节缺「{label}」")
    jx = t.split("解析写法", 1)[1][:3000] if "解析写法" in t else ""
    if jx:
        if "【答案】" in jx:
            ok.append("解析写法有固定结构（【答案】…）")
        else:
            bad.append("解析写法没有固定结构 → 每次输出格式会不一样")
        if not re.search(r"落到|原文|具体句|引用", jx):
            warn.append("解析写法没要求“落到原文 / 用本 skill 术语” → 容易只贴术语标签")
    eng = [h for h in ENGLISH_HEADINGS if re.search(rf"^#+\s+{re.escape(h)}", t, re.M)]
    if eng:
        warn.append(f"主文件还有英文标题：{', '.join(eng)}")

    # ---------------- token 体量
    tk = tokens(t)
    (ok if tk <= SKILL_MD_MAX else warn).append(
        f"SKILL.md 约 {tk} token" + ("" if tk <= SKILL_MD_MAX else f"（建议 ≤ {SKILL_MD_MAX}，每次加载都要付）"))

    # ---------------- chapters
    chs = sorted((d / "chapters").glob("*.md")) if (d / "chapters").is_dir() else []
    ch_tk, no_ex, few_ex, no_ans, big_ch, eng_ch = [], [], [], [], [], []
    for c in chs:
        ct = c.read_text(encoding="utf-8", errors="ignore")
        k = tokens(ct); ch_tk.append(k)
        if k > CHAPTER_MAX:
            big_ch.append(f"{c.name}（{k}）")
        if "典型例题" not in ct:
            no_ex.append(c.name)
        else:
            n = len(re.findall(r"^#{2,4}\s*例\s*\d", ct, re.M))
            if n < 2:
                few_ex.append(f"{c.name}（{n} 道）")
            if n and "答案" not in ct:
                no_ans.append(c.name)
        if any(re.search(rf"^#+\s+{re.escape(h)}", ct, re.M) for h in ENGLISH_HEADINGS):
            eng_ch.append(c.name)
    if chs:
        avg = sum(ch_tk) // len(ch_tk)
        info.append(f"章节 {len(chs)} 个，平均约 {avg} token，最大 {max(ch_tk)}")
        if big_ch: warn.append(f"章节过大（> {CHAPTER_MAX}）：{', '.join(big_ch[:6])}")
        overview = re.compile(r"概述|总纲|导学|导论|introduction|overview|intro", re.I)
        ov = [n for n in no_ex if overview.search(n)]
        real = [n for n in no_ex if n not in ov]
        if ov:
            info.append(f"概述类章节没有例题（正常）：{', '.join(ov)}")
        if real:
            msg = f"没有「典型例题」的题型章节：{len(real)}/{len(chs)}（{', '.join(real[:5])}）→ AI 缺少同类题示范"
            (bad if len(real) * 3 >= len(chs) else warn).append(msg)
        if few_ex: warn.append(f"例题少于 2 道：{', '.join(few_ex[:6])}")
        if no_ans: warn.append(f"例题没写答案：{', '.join(no_ans[:6])}")
        if eng_ch: warn.append(f"章节里还有英文标题：{len(eng_ch)} 个（{', '.join(eng_ch[:4])}…）")
    else:
        warn.append("没有 chapters/（纯手写 skill 可以没有；book-to-skill 生成的应该有）")
        avg = 0

    # ---------------- cheatsheet
    cs = d / "cheatsheet.md"
    cs_tk = 0
    if cs.is_file():
        ct = cs.read_text(encoding="utf-8", errors="ignore"); cs_tk = tokens(ct)
        parts = [(("题型识别", "识别表"), "题型识别表"),
                 (("步骤", "下手", "怎么做", "流程", "解法", "SOP"), "每类题的解题步骤"),
                 (("陷阱", "干扰项", "易错"), "选项陷阱清单")]
        miss = [label for kws, label in parts if not any(k in ct for k in kws)]
        (warn if miss else ok).append("cheatsheet " + (f"缺：{'、'.join(miss)}" if miss else "三部分齐全") + f"（约 {cs_tk} token）")
        if cs_tk > CHEATSHEET_MAX:
            warn.append(f"cheatsheet 约 {cs_tk} token，偏大（建议 ≤ {CHEATSHEET_MAX}，它是“整个板块读一次”的速查）")
    else:
        warn.append("没有 cheatsheet.md（Core Frameworks 不够时 AI 就只能去读整章）")

    # ---------------- 链接
    body = re.sub(r"```.*?```|~~~~.*?~~~~", "", t, flags=re.S)
    broken = [l for l in re.findall(r"\]\(((?:chapters|references)/[^)#]+|[\w.-]+\.md)\)", body)
              if "<" not in l and not (d / l).exists()]
    if broken:
        bad.append(f"指向不存在文件的链接：{', '.join(broken[:6])}")

    # ---------------- 开销估算
    batch = 5
    est_min = tk + 300 * batch + 700 * batch                     # skill + 题目 + 解析输出
    est_max = tk + cs_tk + avg * min(batch, 2) + 300 * batch + 700 * batch
    info.append(f"估算一批 {batch} 题：约 {est_min // 1000}k～{est_max // 1000 + 1}k token（不含对话来回的重复计费；"
                f"只用主文件时取下限，读 cheatsheet + 1～2 章时取上限）")

    # ---------------- 输出
    verdict = "❌ 暂不适合直接调度，先修 ❌ 项" if bad else ("⚠ 可以用，建议处理 ⚠ 项" if warn else "✅ 适合作为解题 skill")
    out = [f"# 验收：{d.name}", "", f"**结论：{verdict}**", ""]
    out += [f"- ❌ {x}" for x in bad] + [f"- ⚠ {x}" for x in warn] + [f"- ✅ {x}" for x in ok] + [f"- ℹ {x}" for x in info]
    print("\n".join(out))
    if "--md" in sys.argv:
        (d / "验收报告.md").write_text("\n".join(out) + "\n", encoding="utf-8")
        print(f"\n已写入 {d / '验收报告.md'}")


if __name__ == "__main__":
    main()
