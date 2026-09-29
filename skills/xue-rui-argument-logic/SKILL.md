---
name: xue-rui-argument-logic
description: "Knowledge base and methodology framework from 薛睿论证推理系统讲义及328强化进阶.
  Use when solving Chinese civil-service exam and management master entrance
  exam (管综) argument reasoning (论证推理) questions, identifying core logical
  structures, applying support/weaken rules, avoiding 13 bad option traps
  (选项13丑), and leveraging 13 good option templates (选项13美). Covers 削弱、
  支持、假设、解释、评价. Also used when xingce-jiexi-all dispatches the 论证逻辑
  board."
metadata:
  copilot-enabled-agents: opencode
---

<!-- argument-hint: [topic, framework name, chapter number, or question type] -->

# 薛睿论证推理精讲与328强化进阶体系

> **被 xingce-jiexi-all 调度、或用户说“给第N季生成解析 / 只做某板块”时**：直接跳到本文件末尾「被 xingce-jiexi-all 调度时」一节照做。如果加载进来的内容里看不到那一节，只用一次 Read 读本 SKILL.md 的末尾部分，不要再找别的文件。

**Author**: 薛睿 | **Sources**: 完整版讲义及328强化进阶1-7册 | **Generated**: 2026-09-22

## How to Use This Skill

- **Without arguments** — load core frameworks, DaBao XiaoBao reasoning principles, and option templates.
- **With a topic or question type** — ask about `由因推果`, `由果推因`, `二句式推理`, `选项13美`, or `选项13丑`; I find and read the relevant chapter.
- **With chapter** — ask for `ch01` to `ch08`; I load that specific chapter.
- **Browse** — ask "what chapters do you have?" to see the full chapter and topic index.

When you ask about a topic not covered in Core Frameworks below, I will read the relevant chapter file before answering.

---

## Core Frameworks & Mental Models

### 1. 论证推理底层解题五步法
1. **一看提问句**：判定是削弱、支持、假设、评价、解释还是选非。
2. **找结论的引词**：如“因此”、“所以”、“表明”、“认为”、“研究人员认为”。
3. **找结论**：锁定文段核心观点。
4. **找论据**：提取支撑结论的事实、实验数据或前提。
5. **思考推理结构**：区分“一句式推理”与“二句式推理”。

### 2. 两句式推理 vs 一句式推理
- **一句式推理**：论据是客观事实或实验数据（不包含推理链），结论即为整体观点。削弱/支持直接针对结论。
- **二句式推理**：论据和结论均包含推理过程，且存在关键词或逻辑链条的重复（如 $A \rightarrow B$ 且 $A \rightarrow C$）。正确选项必须参与并反驳/支持核心推理链，论据关键词必须参与推理。

### 3. 选项 13 美 (正确选项模板)
- **指出相同 / 指出不同**：论据主体能够代表结论主体，或强调比较时起点必须相同。
- **引入其他限制因素 (非线性改变)**：如“吃了也白吃”、“吃得不够多”、“非线性改变”，切中隐性条件。
- **机制穿透 (底层机制)**：不直接重复结论，而是指出导致结果发生的微观机制。

### 4. 选项 13 丑 (考官挖坑指南)
- **利弊大小不改变利弊方向**：正向因素小不代表反向作用。
- **诉诸权威 / 无关主体**：用专家观点偷换逻辑链条。
- **无因无果的偷换概念**：表面相关但未切断核心论据到结论的桥梁。

---

## Chapter Index

| # | Title | Key Frameworks |
|---|-------|----------------|
| [ch01](chapters/ch01-methodology-and-steps.md) | 论证推理底层方法与解题步骤 | 五步法、备考误区、进阶三要三不要 |
| [ch02](chapters/ch02-two-sentence-reasoning.md) | 二句式推理结构 | 补全逻辑、建立联系、指出相同/不同 |
| [ch03](chapters/ch03-cause-to-effect.md) | 由因推果推理与削弱支持 | 建立联系、直接引入他因、前真后假 |
| [ch04](chapters/ch04-effect-to-cause.md) | 由果推因推理与反驳 | 另有他因、因果倒置、排除他因 |
| [ch05](chapters/ch05-option-templates-beautiful.md) | 选项 13 美 (正确选项模板) | 指出相同/不同、非线性改变、机制穿透 |
| [ch06](chapters/ch06-option-traps-ugly.md) | 选项 13 丑 (考官挖坑指南) | 利弊大小、诉诸权威、无因无果偷换概念 |
| [ch07](chapters/ch07-shortcuts-and-models.md) | 秒杀思路与核心模型 | 第三者搭桥、起点相同、幸存者偏差、因果倒置 |
| [ch08](chapters/ch08-special-types.md) | 解释题型、选非与评价题型 | 解释矛盾、最不能支持/削弱、评价论证 |

## Topic Index

- **补全逻辑** → ch02
- **建立联系** → ch02, ch03
- **由因推果** → ch03
- **由果推因** → ch04
- **选项13美** → ch05
- **选项13丑** → ch06
- **因果倒置** → ch07
- **幸存者偏差** → ch07
- **解释题型** → ch08
- **评价论证** → ch08

## Supporting Files

- [glossary.md](glossary.md) — 核心逻辑专有名词与公考概念体系
- [cheatsheet.md](cheatsheet.md) — 高频模型决策规则与选项判断速查

---

## Scope & Limits

This skill covers the 薛睿论证推理讲义 and 328强化进阶 materials. Combine with practice questions for exam mastery.

---

## 被 xingce-jiexi-all 调度时

被总调度 skill 派来处理某一季的论证逻辑板块时，按下面流程**直接把解析写进板块 md 文件**，不在对话里输出长篇解析。

`<jiexi>` 指 `xingce-jiexi-all/scripts/jiexi.py`（和本 skill 在同一个 skills 目录下）。路径一律加英文双引号；命令里的 `python`：Windows 用 `python`（不行换 `py`），Mac 用 `python3`。

**直接开始，不要摸索**：用户说“给第N季生成解析 / 只做某板块”时，直接运行下面的命令，`<季>` 写季数（如 `36`）即可，脚本会自己找到目录。**不要** ls / find / grep 库里的文件，**不要**读 jiexi.py 源码、board-map.md、`projects/` 等目录，**也不要打开板块 md 文件本身**——题目、答案、截图路径 `next` 都会打印出来，写入用 `write`。

**Windows PowerShell**：中文输出会乱码，每条 python 命令前固定加 `[Console]::OutputEncoding=[Text.Encoding]::UTF8;`（同一行），不用先试一次再加。

### 流程

1. **开工前准备（整个板块只做一次）**：读本文件的 Core Frameworks。不预先读章节。
2. 取一批题：`python "<jiexi>" next <季> 论证逻辑 [--mode 错题|全部]`
   输出里有板块文件路径、本批题号、题干、选项、正确答案、我的答案，以及截图完整路径。有 `[截图]` 的必须打开截图看。**看图预算**：原图只读 1 次；看不清时最多再读 2 次局部放大；**不要安装任何软件包**（pip install 等），系统里没有的工具就不用；还是看不清就写 `⚠ 待核对：截图看不清`，接着做下一题。
3. 按本 skill 的方法解这一批题，遵守：
   - **以正确答案为锚**：推导必须落到给出的正确答案；推不出来就写一行 `⚠ 待核对：<卡在哪一步>`，不要硬编；
   - 我答错时，点出我选的选项错在哪。
4. 按下面「解析写法」把这批解析写进 `next` 打印的临时文件（`<第N季目录>/.jiexi-tmp.md`），每题以 `=== 题号` 开头，然后写入（成功后临时文件自动删除）：
   `python "<jiexi>" write <季> 论证逻辑`
   （脚本会给每行加 `> `，只写空的复盘栏，不会覆盖已有笔记。）
5. 重复 2–4，直到 `next` 显示“没有待解析的题”。
6. 检查格式：`python "<jiexi>" check <季> 论证逻辑`，有 ❌ 就按提示修好。
7. 回报一句话：写入了几题、哪些题标了待核对。

### 省 token 规则

- 本文件的 Core Frameworks 已经够解大多数题，**先只用它**。
- 不够时读 `cheatsheet.md`，**整个板块只读一次**，后面的批次直接复用，不要重读。
- 章节文件只在某题确实需要时读，**每题最多读 1 章**；同一板块里已经读过的章节不重复读。
- `glossary.md`、`patterns.md` 除非遇到不认识的术语，否则不读。

### 解析写法

```
=== 96
【答案】C
【题型】削弱 / 支持 / 假设 / 解释 / 评价 / 选非
【结构】论据：……　→　结论：……（一句式 / 二句式；由因推果 / 由果推因）
【选项】A：……（13丑·诉诸权威）　B：……　C：……（13美·指出不同，正确）　D：……
【易错】我选 A 错在……（答对可省略）
```
每个选项一句话即可，能对应到“13美 / 13丑”的就标出来。

### 不能运行 python 时

可以直接编辑板块 md，但必须遵守：只改 `> [!note] 复盘` 下面、该题 `---` 之前的内容；每一行都以 `> ` 开头，空行写成 `>`；复盘栏已有内容的题不要动（只有 `- 错因：` `- 考点：` `- 下次怎么做：` 这类空模板的不算有内容，写解析时把这几行模板原样保留在解析下面）；不改题干、选项、答案行、frontmatter 和速览表。
