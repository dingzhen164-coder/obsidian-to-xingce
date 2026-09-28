---
name: xue-rui-yituowu
description: "Knowledge base and methodology framework from 薛睿《国考一拖五（分析推理）讲义》.
  Use when solving Chinese civil-service exam (行测) and management master
  entrance exam (管综) analysis reasoning 'yituowu' (one-to-five questions)
  including queue ranking, group allocation, compound spatial constraints,
  contradiction deduction, and question entry strategies. Also used when
  xingce-jiexi-all dispatches the 一拖五 board."
metadata:
  copilot-enabled-agents: opencode
---

<!-- argument-hint: [topic, framework name, or chapter number] -->

# 国考一拖五（分析推理体系）
**Author**: 薛睿 | **Pages**: ~52 | **Chapters**: 7 | **Generated**: 2026-09-22

## How to Use This Skill

- **Without arguments** — load core frameworks for reference
- **With a topic** — ask about `队列型`, `分组型`, `大跨度绑定`, `两次分类交集`, or another indexed topic; I find and read the relevant chapter
- **With chapter** — ask for `ch02` or `ch04`; I load that specific chapter
- **Browse** — ask "what chapters do you have?" to see the full index

When you ask about a topic not covered in Core Frameworks below, I will read the relevant chapter file before answering.

---

## Core Frameworks & Mental Models

### 1. 设问类型入口选择策略
- **问一定为真**：根据题干条件正向推导，**严禁代入选项验证**。
- **问一定为假**：代入选项验证找矛盾，或推导其反面。
- **问可能为真**：代入选项验证（能排满无矛盾即为正确选项）。
- **附加条件**：必须将每一小题临时给出的“如果……”作为硬性假设条件叠加进全局。

### 2. 队列型与分组型核心解题 SOP
- **队列型 SOP**：统一顺序符号（全部用 $<$ 或 $>$） $\rightarrow$ 优先填入确定类条件（切割空间） $\rightarrow$ 用顺序类条件定空间大小 $\rightarrow$ 用绑定类条件缩范围 $\rightarrow$ 用推理类条件推导或找矛盾。
- **分组型 SOP**：明确组数与各组容量限制 $\rightarrow$ 优先填入确定类条件 $\rightarrow$ 用隔离/互斥类条件定剩余空间 $\rightarrow$ 用绑定类条件（视为占用2名额的大零件）缩名额 $\rightarrow$ 用推理类条件和逆否命题解题。

### 3. 高级复合与大跨度模型
- **大跨度绑定相交规律**：若两个大跨度绑定条件的空间之和超过总空间数，它们必须相交。
- **两次分类交集模型**：面对两套独立属性分类（如性别 + 学历），建立交叉矩阵寻找“唯一性”突破口求交集。

---

## Chapter Index

| # | Title | Key Frameworks |
|---|-------|----------------|
| [ch01](chapters/ch01-introduction.md) | 一拖五题型及分析推理导学 | 一拖五设问入口, 分析推理基本功 |
| [ch02](chapters/ch02-queue-patterns.md) | 队列型考点讲解 | 五大类条件体系, 队列解题SOP, 符号一致性 |
| [ch03](chapters/ch03-queue-real-questions.md) | 队列型一拖五国考真题 | 真题综合破解法, 货架排布模型 |
| [ch04](chapters/ch04-grouping-patterns.md) | 分组型题目考点讲解 | 分组条件体系, 分组解题SOP, 盒子与球模型 |
| [ch05](chapters/ch05-grouping-real-questions.md) | 分组型一拖五国考真题 | 分组真题通关法, 名额平衡模型, 专家评标分组 |
| [ch06](chapters/ch06-compound-patterns.md) | 队列+分组型题目考点讲解 | 两次分类交集模型, 双维矩阵模型 |
| [ch07](chapters/ch07-compound-real-questions.md) | 队列+分组型一拖五国考真题 | 压轴复合题攻坚法, 跨度条件与房间排布 |

## Topic Index

- **一拖五题型** → ch01
- **确定类条件** → ch02, ch04
- **顺序类条件** → ch02
- **绑定类条件** → ch02, ch04
- **隔离类条件** → ch02, ch04
- **推理类条件** → ch02, ch04
- **大跨度绑定** → ch02
- **标准分组** → ch04
- **两次分类交集** → ch06
- **逆否等价** → ch02, ch04
- **设问入口策略** → ch01
- **队列解题SOP** → ch02
- **分组解题SOP** → ch04

## Supporting Files

- [glossary.md](glossary.md) — all key terms with definitions
- [patterns.md](patterns.md) — all techniques and design patterns
- [cheatsheet.md](cheatsheet.md) — quick reference tables and decision guides

---

## Scope & Limits

This skill covers the book content only. For hands-on implementation in your codebase, combine with project-specific tools. For topics beyond this book, check related skills or ask the agent directly.

---

## 被 xingce-jiexi-all 调度时

被总调度 skill 派来处理某一季的一拖五板块时，按下面流程**直接把解析写进板块 md 文件**，不在对话里输出长篇解析。

`<jiexi>` 指 `xingce-jiexi-all/scripts/jiexi.py`（和本 skill 在同一个 skills 目录下）。路径一律加英文双引号；命令里的 `python`：Windows 用 `python`（不行换 `py`），Mac 用 `python3`。

### 流程

1. **开工前准备（整个板块只做一次）**：读本文件的 Core Frameworks。不预先读章节。
2. 取一批题：`python "<jiexi>" next "<第N季目录>" 一拖五 [--mode 错题|全部]`
   输出里有板块文件路径、本批题号、题干、选项、正确答案、我的答案，以及截图完整路径。有 `[截图]` 的必须打开截图看。
3. 按本 skill 的方法解这一批题，遵守：
   - **以正确答案为锚**：推导必须落到给出的正确答案；推不出来就写一行 `⚠ 待核对：<卡在哪一步>`，不要硬编；
   - 我答错时，点出我选的选项错在哪。
4. 按下面「解析写法」把这批解析写进临时文件（如 `<第N季目录>/.jiexi-tmp.md`），每题以 `=== 题号` 开头，然后写入：
   `python "<jiexi>" write "<第N季目录>" 一拖五 "<临时文件>"`
   （脚本会给每行加 `> `，只写空的复盘栏，不会覆盖已有笔记。）
5. 重复 2–4，直到 `next` 显示“没有待解析的题”。
6. 检查格式：`python "<jiexi>" check "<第N季目录>" 一拖五`，有 ❌ 就按提示修好。
7. 回报一句话：写入了几题、哪些题标了待核对。

### 省 token 规则

- 本文件的 Core Frameworks 已经够解大多数题，**先只用它**。
- 不够时读 `cheatsheet.md`，**整个板块只读一次**，后面的批次直接复用，不要重读。
- 章节文件只在某题确实需要时读，**每题最多读 1 章**；同一板块里已经读过的章节不重复读。
- `glossary.md`、`patterns.md` 除非遇到不认识的术语，否则不读。
- **同一组材料只整理一次条件**：一组 5 题共用一份材料，在该组第一道要解析的题里写完整的【条件整理】（符号化、排好的队列/分组表）；同组后面的题写“条件整理见第 N 题”，只写本题新增的“如果……”假设和推导。

### 解析写法

```
=== 106
【答案】D
【题型】队列型 / 分组型 / 队列+分组；设问：一定为真 / 可能为真 / 一定为假
【条件整理】（本组第一题写；后面的题写“见第 N 题”）
  确定类：……　顺序类：……　绑定类：……　隔离类：……　推理类：……
【推理】按 SOP 一步步推到答案（有附加条件先叠加进去）
【易错】我选 B 错在……（答对可省略）
```

### 不能运行 python 时

可以直接编辑板块 md，但必须遵守：只改 `> [!note] 复盘` 下面、该题 `---` 之前的内容；每一行都以 `> ` 开头，空行写成 `>`；复盘栏已有内容的题不要动；不改题干、选项、答案行、frontmatter 和速览表。
