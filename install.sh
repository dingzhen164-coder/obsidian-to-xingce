#!/usr/bin/env bash
# 安装 / 更新 行测 skills 到 Obsidian Copilot 的 skills 目录（Mac）
# 用法（终端）：
#   curl -fsSL https://raw.githubusercontent.com/dingzhen164-coder/obsidian-to-xingce/refs/heads/claude/continue-previous-conversation-8zt03d/install.sh | bash
# 可选：SK="<skills目录>" 放在 bash 前面，跳过自动查找：  ... | SK="/path/to/skills" bash
set -euo pipefail
BRANCH="claude/continue-previous-conversation-8zt03d"
ZIP="https://github.com/dingzhen164-coder/obsidian-to-xingce/archive/refs/heads/${BRANCH}.zip"
BOARD="political-theory-reasoning center-comprehension-jiangwei xue-rui-argument-logic xue-rui-formal-logic xue-rui-yituowu"

# 1) 找 skills 目录（包含 xue-rui-formal-logic 的那个）
if [ -z "${SK:-}" ]; then
  # 优先库根目录 行测/ 下的 copilot/skills；跳过 copilot.old 之类的旧目录
  hit=$(find "${HOME}/Desktop" "${HOME}/Documents" -maxdepth 7 -type d -name xue-rui-formal-logic 2>/dev/null \
        | grep -v '\.old' | awk '{print (index($0, "/行测/copilot/skills/") ? 0 : 1) "\t" $0}' | sort | cut -f2- | head -1 || true)
  [ -n "${hit}" ] || { echo "找不到 skills 目录，请这样运行：... | SK=\"<skills目录>\" bash"; exit 1; }
  SK=$(dirname "${hit}")
fi
echo "[1/5] skills 目录：${SK}"

command -v python3 >/dev/null || { echo "没有 python3：请先在终端运行 xcode-select --install"; exit 1; }

# 2) 下载
tmp=$(mktemp -d)
curl -fsSL "${ZIP}" -o "${tmp}/src.zip"
# 用 Python 解压：Mac 自带的 unzip 处不了中文文件名（会报 disk full 并卡住）
python3 -m zipfile -e "${tmp}/src.zip" "${tmp}" </dev/null
src=$(find "${tmp}" -maxdepth 1 -type d -name 'obsidian-to-xingce-*' | head -1)/skills
echo "[2/5] 已下载"

# 3) 中心理解文件夹改名，和 name: 一致
if [ -d "${SK}/center-comprehension-booktoskill" ] && [ ! -d "${SK}/center-comprehension-jiangwei" ]; then
  mv "${SK}/center-comprehension-booktoskill" "${SK}/center-comprehension-jiangwei"
fi
echo "[3/5] 中心理解文件夹：$([ -d "${SK}/center-comprehension-jiangwei" ] && echo 正常 || echo 缺失)"

# 4) 替换 5 个板块 SKILL.md（第一次运行时备份原文件为 SKILL.md.bak）
for s in ${BOARD}; do
  d="${SK}/${s}"
  [ -d "${d}" ] || { echo "      跳过 ${s}（文件夹不存在）"; continue; }
  [ -f "${d}/SKILL.md.bak" ] || cp "${d}/SKILL.md" "${d}/SKILL.md.bak"
  cp "${src}/${s}/SKILL.md" "${d}/SKILL.md"
  echo "      已更新 ${s}"
done
echo "[4/5] 板块 skill 已更新"

# 5) 安装 / 更新 总调度 和 拆卷 skill
# 旧版本里的中文文件名（已改名为 board-map.md / board-skill-template.md）
rm -f "${SK}/xingce-jiexi-all/板块映射.md" "${SK}/xingce-jiexi-all/板块skill模板.md"
for s in xingce-jiexi-all xingce-mokao-split; do
  mkdir -p "${SK}/${s}"
  cp -R "${src}/${s}/." "${SK}/${s}/"
  echo "      已安装 ${s}：SKILL.md $([ -f "${SK}/${s}/SKILL.md" ] && echo 存在 || echo 缺失)"
done
rm -rf "${tmp}"
echo "[5/5] 完成。检查 Python："
if command -v python3 >/dev/null; then python3 "${SK}/xingce-jiexi-all/scripts/jiexi.py" -h | head -1
else echo "      没有 python3：在终端运行 xcode-select --install 安装"; fi
