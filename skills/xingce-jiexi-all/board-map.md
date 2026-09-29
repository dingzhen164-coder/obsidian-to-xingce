# 板块 → 解题 skill 映射

13 个板块的解题 skill 名字已经**全部定好**。新写板块 skill 时，**文件夹名和 `name:` 都照这里的名字起**，放在和 `xingce-jiexi-all` 同一个 `skills/` 目录下，总调度会自动发现它，这张表不用改。

还没创建的 skill，总调度会自动跳过那个板块（复盘栏保持空白）。

- 识别 skill 时，文件夹名和 `SKILL.md` 里的 `name:` 都认；但最好让两者一致（opencode 等工具要求一致）。
- 一格里可以写多个候选，用逗号隔开，**用第一个已存在的**。例如语句排序：专门的 `xingce-yujupaixu` 写好之前，先借用中心理解 skill（它的 ch15 讲了语句排序）。

- 解题skill 写 `-`：这个板块不做 AI 解析（如资料分析、图形推理，自己复盘），总调度直接跳过。
- `默认范围`：`错题`（❌ 和 ⚪ 未作答）或 `全部`。运行时用户明确说了范围，以用户说的为准。
- `批大小`：每批处理几题，做完一批立刻写回文件。题目长（带材料、截图）的板块调小。

| 板块 | 解题skill | 默认范围 | 批大小 |
| --- | --- | --- | --- |
| 政治理论 | political-theory-reasoning | 错题 | 8 |
| 常识判断 | xingce-changshi | 错题 | 8 |
| 逻辑填空 | xingce-luojitiankong | 错题 | 6 |
| 中心理解 | center-comprehension-jiangwei | 错题 | 5 |
| 语句排序 | xingce-yujupaixu, center-comprehension-jiangwei | 错题 | 5 |
| 数量关系 | xingce-shuliang | 错题 | 4 |
| 图形推理 | - | 错题 | 3 |
| 定义判断 | xingce-dingyi | 错题 | 6 |
| 类比关系 | xingce-leibi | 错题 | 8 |
| 论证逻辑 | xue-rui-argument-logic | 错题 | 5 |
| 形式逻辑 | xue-rui-formal-logic | 错题 | 5 |
| 一拖五 | xue-rui-yituowu | 错题 | 5 |
| 资料分析 | - | 错题 | 5 |
