#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给 book-to-skill 的 SKILL.md 打上“行测模式”补丁（原文不改，只在标题下面插入一节）。

用法：
    python patch_book_to_skill.py "<book-to-skill 文件夹或其 SKILL.md>"

- 第一次打补丁时把原文件备份为 SKILL.md.bak；
- 可以重复运行：已有补丁会被替换成最新版本，不会重复插入；
- book-to-skill 自己升级（SKILL.md 被覆盖）后，再运行一次即可。
"""
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

START = "<!-- xingce-mode:start -->"
END = "<!-- xingce-mode:end -->"

BLOCK = START + r"""

## 行测模式（本库定制，优先于下文的默认流程）

**什么时候进入行测模式**：源文件是行测 / 公考讲义、课程笔记、真题解析，或用户提到了行测板块名（政治理论、常识判断、逻辑填空、中心理解、语句排序、数量关系、图形推理、定义判断、类比关系、论证逻辑、形式逻辑、一拖五、资料分析）。进入后，下面的规则**覆盖**下文对应步骤；这里没提到的步骤照下文原样执行。

目标变了：不是做一个“查书用的知识库”，而是做一个**能被 `xingce-jiexi-all` 调度、拿到一道题就能按步骤解出来并写出解析**的解题 skill。

### 开始前只问一个问题

> “这份讲义用于哪个板块？”

板块决定了 skill 名字和内容类型，**不再问 Step 1.5 的内容类型和 Step 4 的用途**：

| 板块 | skill 名（必须用这个） | 内容类型 `BOOK_TYPE` |
|---|---|---|
| 政治理论 | political-theory-reasoning | text |
| 常识判断 | xingce-changshi | text |
| 逻辑填空 | xingce-luojitiankong | text |
| 中心理解 | center-comprehension-jiangwei | text |
| 语句排序 | xingce-yujupaixu | text |
| 数量关系 | xingce-shuliang | technical |
| 图形推理 | xingce-tuxing | technical |
| 定义判断 | xingce-dingyi | text |
| 类比关系 | xingce-leibi | text |
| 论证逻辑 | xue-rui-argument-logic | text |
| 形式逻辑 | xue-rui-formal-logic | text |
| 一拖五 | xue-rui-yituowu | text |
| 资料分析 | xingce-ziliao | technical |

（名字以 `../xingce-jiexi-all/board-map.md` 为准；两者不一致时用 board-map.md 里的。）

- 用途固定为 “1. Apply the author's frameworks”，即 `DEPTH=study`。
- 同名 skill 已存在（例如给论证逻辑再加一本讲义）→ 默认走 **Update / Fold-in**，不要 Overwrite。
- **`SKILLS_HOME`**：放到本 skill 所在的同一个 skills 目录（即 `book-to-skill` 文件夹的上一级，如 `行测/copilot/skills`），不用 `~/.agents/skills`，也不做 Step 10 的 symlink、不做 Step 11 的发布。

### 提取前的检查（Step 2 之后）

- 看 `metadata.json`：页数不少但 words/tokens 很少 → **大概率是扫描版**。停下告诉用户：“这是扫描版 PDF，文字读不出来，请先转成可复制文字的 PDF（OCR）再来。”不要硬着头皮生成空壳 skill。
- `images_dropped` 很多、而板块是**图形推理**：提醒用户“图形推理讲义的核心在图里，转出来会缺大半内容，建议改为手写规律清单”，由用户决定是否继续。
- 数量关系、资料分析的公式和表格要尽量保留（technical 模式会用 Docling）。

### 全部用中文

所有生成文件（SKILL.md、chapters、glossary、patterns、cheatsheet）的标题和正文都用中文；讲义里的术语、口诀、模型名**原样保留**（Quality Rule 2）。

### 章节文件（覆盖 Step 7 的 Worked Example）

每章把 `## Worked Example` 换成 `## 典型例题`，放 **2–3 道**最能体现本章方法的例题，每道：

```
### 例 1（题型：……）
题干：……（精简到能看懂题意；选项保留）
答案：X
老师的解法：① …… ② …… ③ ……（按讲义的步骤和术语写）
易错点：……
```

- 这是 Quality Rule 7（不照抄原文）的**唯一例外**：真题题干、选项和答案可以照录，因为 AI 解题时最需要的就是同类题的示范；讲义正文仍然要提炼，不要大段照抄。
- 每章预算按 `DEPTH=study` 那一格，例题优先占用预算。

### cheatsheet.md（覆盖 Step 8 的侧重点）

按解题顺序组织，三部分：
1. **题型识别表**：题干特征 / 提问方式 → 属于哪类题 → 用哪个方法（对应哪一章）。
2. **每类题的解题步骤**：3–6 步，写成可以照做的动作。
3. **选项陷阱清单**：错误选项的常见套路 → 怎么识别。

### 主 SKILL.md（覆盖 Step 9 的模板）

仍然控制在 4,000 token 内、最重要的放最前。结构按下面的顺序，替换 Step 9 模板里的 “How to Use This Skill”：

```markdown
---
name: <上表里的 skill 名>
description: 行测<板块>的解题方法与解析写法（来源：<讲义名 / 老师>）。用户让解析、讲解、复盘<板块>题（<3–6 个题型关键词>），或 xingce-jiexi-all 调度<板块>板块时使用。
metadata:
  copilot-enabled-agents: opencode
---

# <板块> 解题 · <讲义名>
**来源**：<讲义 / 老师> | **章节**：<N> | **生成**：<YYYY-MM-DD>

## 适用题型
<一句话列出本 skill 覆盖的题型，以及不覆盖的>

## 解题步骤
<拿到一道题的完整 SOP：识别题型 → 选方法 → 执行步骤 → 判断选项 → 用正确答案验算。每步一行，写动作不写概念>

## 核心框架
<原 Core Frameworks & Mental Models：只留解题会用到的，按“遇到 X → 用 Y”写>

## 解析写法
<每道题解析的固定结构，例如：
【答案】X
【题型】……
【思路】……（按上面的解题步骤写）
【易错】我选 Y 错在……（我答对时省略）>

## 章节索引 / 题型索引
<原 Chapter Index + Topic Index，题型索引写成“题型 → 章节”>

## 配套文件
cheatsheet.md（先读这个）· patterns.md · glossary.md

## 被 xingce-jiexi-all 调度时
<照抄 ../xingce-jiexi-all/board-skill-template.md 代码块里「## 被 xingce-jiexi-all 调度时」这一整节，把 <板块名> 换成本板块>
```

- **省 token 规则**要写进「被 xingce-jiexi-all 调度时」一节：先只用主 SKILL.md；不够时读 cheatsheet.md（整个板块只读一次）；每题最多读 1 章；glossary / patterns 非必要不读。
- 删掉 Scope & Limits 里的英文套话，改成一句中文：本 skill 覆盖哪份讲义的哪些部分、哪些题型不覆盖。

### Update / Fold-in 时必须保留的内容

重新生成主 SKILL.md 时，**以下三节从旧文件原样保留，不要重写**（它们可能是用户后来手改过的）：
「解题步骤」「解析写法」「被 xingce-jiexi-all 调度时」。
新讲义带来的新方法，只往「核心框架」、章节索引和 cheatsheet 里加；和旧的「解题步骤」冲突时，列出冲突点问用户。

### 生成完之后

1. 运行 `python "<skills目录>/xingce-jiexi-all/scripts/jiexi.py" -h` 能正常输出，说明总调度在；
2. 告诉用户：新 skill 名、覆盖的题型、每章几道例题、是否有扫描页 / 图片丢失；
3. 提醒：用 `jiexi.py status <季>` 看该板块是否已从“尚未创建”变成“未开始”。

""" + END


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    p = Path(sys.argv[1]).expanduser()
    if p.is_dir():
        p = p / "SKILL.md"
    if not p.is_file():
        sys.exit(f"找不到文件：{p}")
    raw = p.read_bytes()
    text = raw.decode("utf-8-sig")
    nl = "\r\n" if b"\r\n" in raw else "\n"
    text = text.replace("\r\n", "\n")

    if START in text and END in text:  # 已打过补丁：换成最新版本
        text = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda m: BLOCK, text, count=1, flags=re.S)
        action = "已更新行测模式补丁"
    else:
        bak = p.with_name("SKILL.md.bak")
        if not bak.exists():
            bak.write_bytes(raw)
        # 插在第一个一级标题（# Book-to-Skill Converter）下面；没有就插在 frontmatter 后面
        m = re.search(r"^# .*\n", text, flags=re.M)
        if not m:
            fm = re.match(r"---\n.*?\n---\n", text, flags=re.S)
            pos = fm.end() if fm else 0
        else:
            pos = m.end()
        text = text[:pos] + "\n" + BLOCK + "\n\n" + text[pos:]
        action = "已打上行测模式补丁（原文件备份为 SKILL.md.bak）"
    with open(p, "w", encoding="utf-8", newline=nl) as fp:
        fp.write(text)
    print(f"{action}：{p}")


if __name__ == "__main__":
    main()
