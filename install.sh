#!/usr/bin/env bash
# 安装 / 更新 行测 skills（Mac）。同时更新库里的 copilot/skills 和 .opencode/skills（opencode 实际读的是后者）
# 用法（终端）：
#   curl -fsSL https://raw.githubusercontent.com/dingzhen164-coder/obsidian-to-xingce/refs/heads/claude/continue-previous-conversation-8zt03d/install.sh | bash
# 可选：SK="<copilot/skills目录>" 放在 bash 前面，跳过自动查找：  ... | SK="/path/to/skills" bash
set -euo pipefail
BRANCH="claude/continue-previous-conversation-8zt03d"
ZIP="https://github.com/dingzhen164-coder/obsidian-to-xingce/archive/refs/heads/${BRANCH}.zip"
BOARD="political-theory-reasoning center-comprehension-jiangwei xue-rui-argument-logic xue-rui-formal-logic xue-rui-yituowu"

# 1) 找库根目录（copilot/skills 或 .opencode/skills 往上两级）
if [ -z "${SK:-}" ]; then
  # 优先 行测/copilot/skills；跳过 copilot.old 之类的旧目录
  hit=$(find "${HOME}/Desktop" "${HOME}/Documents" -maxdepth 7 -type d -name xue-rui-formal-logic 2>/dev/null \
        | grep -v '\.old' | awk '{print (index($0, "/行测/copilot/skills/") ? 0 : 1) "\t" $0}' | sort | cut -f2- | head -1 || true)
  [ -n "${hit}" ] || { echo "找不到 skills 目录，请这样运行：... | SK=\"<skills目录>\" bash"; exit 1; }
  SK=$(dirname "${hit}")
fi
VAULT=$(dirname "$(dirname "${SK}")")
TARGETS=()
for t in "${VAULT}/copilot/skills" "${VAULT}/.opencode/skills"; do
  [ -d "${t}" ] && TARGETS+=("${t}")
done
echo "[1/5] 库根目录：${VAULT}"
for t in "${TARGETS[@]}"; do echo "      将更新：${t}"; done

command -v python3 >/dev/null || { echo "没有 python3：请先在终端运行 xcode-select --install"; exit 1; }

# 2) 下载
tmp=$(mktemp -d)
curl -fsSL "${ZIP}" -o "${tmp}/src.zip"
# 用 Python 解压：Mac 自带的 unzip 处不了中文文件名（会报 disk full 并卡住）
python3 -m zipfile -e "${tmp}/src.zip" "${tmp}" </dev/null
src=$(find "${tmp}" -maxdepth 1 -type d -name 'obsidian-to-xingce-*' | head -1)/skills
echo "[2/5] 已下载"

# skill 体检：文件夹名≠name、同一 skill 两个文件夹、.opencode 副本过旧/缺文件 —— 所有 skill 一起修
DOCTOR="${src}/xingce-jiexi-all/scripts/skills_doctor.py"
echo "== skill 体检（修复前）"
python3 "${DOCTOR}" "${VAULT}" --fix | sed 's/^/   /'

for T in "${TARGETS[@]}"; do
  echo "== ${T}"
  NEW="${T}/center-comprehension-jiangwei"
  echo "[3/5] 中心理解文件夹：$([ -d "${NEW}" ] && echo 正常 || echo 缺失)；章节文件 $(ls "${NEW}/chapters" 2>/dev/null | wc -l | tr -d ' ') 个"

  # 4) 替换 5 个板块 SKILL.md（第一次运行时备份原文件为 SKILL.md.bak）
  for s in ${BOARD}; do
    d="${T}/${s}"
    [ -d "${d}" ] || { echo "      跳过 ${s}（文件夹不存在）"; continue; }
    [ -f "${d}/SKILL.md.bak" ] || cp "${d}/SKILL.md" "${d}/SKILL.md.bak"
    cp "${src}/${s}/SKILL.md" "${d}/SKILL.md"
    echo "      已更新 ${s}"
  done
  echo "[4/5] 板块 skill 已更新"

  # 5) 安装 / 更新 总调度 和 拆卷 skill
  # 旧版本里的中文文件名（已改名为 board-map.md / board-skill-template.md）
  rm -f "${T}/xingce-jiexi-all/板块映射.md" "${T}/xingce-jiexi-all/板块skill模板.md"
  for s in xingce-jiexi-all xingce-mokao-split xingce-changshi; do
    mkdir -p "${T}/${s}"
    cp -R "${src}/${s}/." "${T}/${s}/"
    echo "      已安装 ${s}：SKILL.md $([ -f "${T}/${s}/SKILL.md" ] && echo 存在 || echo 缺失)"
  done
  # 给 book-to-skill 打“行测模式”补丁（原文不改，只插入一节；原文件备份为 SKILL.md.bak）
  if [ -f "${T}/book-to-skill/SKILL.md" ]; then
    printf "      "; python3 "${T}/xingce-jiexi-all/scripts/patch_book_to_skill.py" "${T}/book-to-skill"
  fi
done
# 更新完后再体检一次：把刚更新的 copilot/skills 同步到 .opencode/skills
echo "== skill 体检（同步 .opencode）"
python3 "${DOCTOR}" "${VAULT}" --fix | sed 's/^/   /'

rm -rf "${tmp}"
echo "[5/5] 完成。检查："
python3 "${TARGETS[0]}/xingce-jiexi-all/scripts/jiexi.py" -h | head -1
for T in "${TARGETS[@]}"; do
  n=0
  for s in ${BOARD}; do
    if grep -q "## 被 xingce-jiexi-all 调度时" "${T}/${s}/SKILL.md" 2>/dev/null; then n=$((n+1)); fi
  done
  echo "      ${T}：${n} 个 skill 已含调度说明（应为 5）"
done
