---
name: xue-rui-formal-logic
description: "Knowledge base and methodology framework from 薛睿论证推理与形式逻辑系统讲义. Use
  when solving Chinese civil-service exam (行测) formal logic questions
  (形式逻辑：翻译推理、真假推理、代入验证、一一对应、文氏图), translating
  connectives, and leveraging contradiction and truth-lie templates. Also used
  when xingce-jiexi-all dispatches the 形式逻辑 board."
metadata:
  copilot-enabled-agents: opencode
---

<!-- argument-hint: [topic, framework name, or chapter number] -->

# 【逻辑薛睿】形式逻辑系统讲义

> **被 xingce-jiexi-all 调度、或用户说“给第N季生成解析 / 只做某板块”时**：直接跳到本文件末尾「被 xingce-jiexi-all 调度时」一节照做。如果加载进来的内容里看不到那一节，只用一次 Read 读本 SKILL.md 的末尾部分，不要再找别的文件。

**Author**: 薛睿 | **Pages**: ~91 | **Chapters**: 7 | **Generated**: 2026-03-22

## How to Use This Skill

- **Without arguments** — load core frameworks for reference
- **With a topic** — ask about `摩根定律`, `除非否则`, `真假推理`, or another indexed topic; I find and read the relevant chapter
- **With chapter** — ask for `ch01` or `ch06`; I load that specific chapter
- **Browse** — ask "what chapters do you have?" to see the full index

When you ask about a topic not covered in Core Frameworks below, I will read the relevant chapter file before answering.

---

## Core Frameworks & Mental Models

- **形式逻辑“去内容化”法则**: 只看形式和结构，不看文字内容。遇到行测逻辑题，第一步永远是把文字剥离，转化为四大基础符号（$\neg, or, and, \rightarrow$）。
- **摩根定律（复言取非）**: 
  - $\neg(A or B) \equiv \neg A and \neg B$（“或者”取非变“且”）
  - $\neg(A and B) \equiv \neg A or \neg B$（“且”取非变“或者”）
- **“除非...否则...” 翻译口诀**: “A 除非 B” $\rightarrow$ $\neg B \rightarrow A$。
- **假言命题推理铁律**: 
  - 肯前必肯后，否后必否前（$A \rightarrow B \equiv \neg B \rightarrow \neg A$）。
  - **绝不能逆推**（肯后不必然，否前不必然）。
- **矛盾与两难推理**: 
  - 互为矛盾的命题必有一真一假。
  - 两难推理模型：$A or B$ 且 $A \rightarrow C$ 且 $B \rightarrow C$ $\vdash C$（殊途同归）。
- **真假推理四字决**: “找矛盾、绕旁边、代入验证、AEIO直言命题”。

---

## Chapter Index

| # | Title | Key Frameworks |
|---|-------|----------------|
| [ch01](chapters/ch01-basics-and-connectives.md) | 形式逻辑基础知识 | 四大基础符号, 摩根定律, 除非否则 |
| [ch02](chapters/ch02-fact-substitution.md) | 代入事实真进行推理 | 事实真, 顺推, 避免逆推谬误 |
| [ch03](chapters/ch03-truth-evaluation.md) | 判断逻辑真假 | 假言真值表, 选言联言真假判定 |
| [ch04](chapters/ch04-contradiction-inference.md) | 通过推矛盾找到隐藏的事实真 | 矛盾命题, 两难推理, 殊途同归 |
| [ch05](chapters/ch05-substitution-verification.md) | 代入验证找矛盾 | 一定为假, 可能真（不矛盾） |
| [ch06](chapters/ch06-truth-lie-problems.md) | 真话假话 | 矛盾关系, AEIO直言命题 |
| [ch07](chapters/ch07-08-matching-and-venn.md) | 一一对应与文氏图 | 列表格法, 文氏图集合推理 |

## Topic Index

- **形式逻辑** → ch01
- **逻辑连词** → ch01
- **摩根定律** → ch01, ch04
- **除非否则** → ch01
- **事实真** → ch02
- **逆推谬误** → ch02
- **两难推理** → ch04
- **一定为假** → ch05
- **可能真** → ch05
- **真假推理** → ch06
- **AEIO直言命题** → ch06
- **文氏图** → ch07-08

## Supporting Files

- [glossary.md](glossary.md) — all key terms with definitions
- [patterns.md](patterns.md) — all techniques and design patterns
- [cheatsheet.md](cheatsheet.md) — quick reference tables and decision guides

---

## Scope & Limits

This skill covers the book content only. For hands-on implementation in your question-solving workflows, combine with project-specific assessment templates.

---

## 被 xingce-jiexi-all 调度时

被总调度 skill 派来处理某一季的形式逻辑板块时，按下面流程**直接把解析写进板块 md 文件**，不在对话里输出长篇解析。

`<jiexi>` 指 `xingce-jiexi-all/scripts/jiexi.py`（和本 skill 在同一个 skills 目录下）。路径一律加英文双引号；命令里的 `python`：Windows 用 `python`（不行换 `py`），Mac 用 `python3`。

**直接开始，不要摸索**：用户说“给第N季生成解析 / 只做某板块”时，直接运行下面的命令，`<季>` 写季数（如 `36`）即可，脚本会自己找到目录。**不要** ls / find / grep 库里的文件，**不要**读 jiexi.py 源码、board-map.md、`projects/` 等目录，**也不要打开板块 md 文件本身**——题目、答案、截图路径 `next` 都会打印出来，写入用 `write`。

**Windows PowerShell**：中文输出会乱码，每条 python 命令前固定加 `[Console]::OutputEncoding=[Text.Encoding]::UTF8;`（同一行），不用先试一次再加。

### 流程

1. **开工前准备（整个板块只做一次）**：读本文件的 Core Frameworks。不预先读章节。
2. 取一批题：`python "<jiexi>" next <季> 形式逻辑 [--mode 错题|全部]`
   输出里有板块文件路径、本批题号、题干、选项、正确答案、我的答案，以及截图完整路径。有 `[截图]` 的必须打开截图看。**看图预算**：原图只读 1 次；看不清时最多再读 2 次局部放大；**不要安装任何软件包**（pip install 等），系统里没有的工具就不用；还是看不清就写 `⚠ 待核对：截图看不清`，接着做下一题。
3. 按本 skill 的方法解这一批题，遵守：
   - **以正确答案为锚**：推导必须落到给出的正确答案；推不出来就写一行 `⚠ 待核对：<卡在哪一步>`，不要硬编；
   - 我答错时，点出我选的选项错在哪。
4. 按下面「解析写法」把这批解析写进 `next` 打印的临时文件（`<第N季目录>/.jiexi-tmp.md`），每题以 `=== 题号` 开头，然后写入（成功后临时文件自动删除）：
   `python "<jiexi>" write <季> 形式逻辑`
   （脚本会给每行加 `> `，只写空的复盘栏，不会覆盖已有笔记。）
5. 重复 2–4，直到 `next` 显示“没有待解析的题”。
6. 检查格式：`python "<jiexi>" check <季> 形式逻辑`，有 ❌ 就按提示修好。
7. 回报一句话：写入了几题、哪些题标了待核对。

### 省 token 规则

- 本文件的 Core Frameworks 已经够解大多数题，**先只用它**。
- 不够时读 `cheatsheet.md`，**整个板块只读一次**，后面的批次直接复用，不要重读。
- 章节文件只在某题确实需要时读，**每题最多读 1 章**；同一板块里已经读过的章节不重复读。
- `glossary.md`、`patterns.md` 除非遇到不认识的术语，否则不读。

### 解析写法

```
=== 101
【答案】B
【题型】翻译推理 / 真假推理 / 代入验证 / 一一对应 / 文氏图……
【符号化】只翻译和正确答案、我的错选有关的条件（¬、or、and、→，含逆否），无关条件不写
【推理】从事实真或矛盾处出发，一步步推到答案
【易错】我选 A 错在……（如：逆推、摩根定律用反）（答对可省略）
```

### 不能运行 python 时

可以直接编辑板块 md，但必须遵守：只改 `> [!note] 复盘` 下面、该题 `---` 之前的内容；每一行都以 `> ` 开头，空行写成 `>`；复盘栏已有内容的题不要动（只有 `- 错因：` `- 考点：` `- 下次怎么做：` 这类空模板的不算有内容，写解析时把这几行模板原样保留在解析下面）；不改题干、选项、答案行、frontmatter 和速览表。
