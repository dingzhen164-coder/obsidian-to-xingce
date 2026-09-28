#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill 体检：检查并修复库里 copilot/skills 与 .opencode/skills 两处 skill 的常见问题。

用法：
    python skills_doctor.py "<库根目录，即 行测/>"          # 只检查，打印报告
    python skills_doctor.py "<库根目录>" --fix              # 检查并修复

检查 / 修复的问题（对所有 skill，不只行测板块）：
1. 文件夹名和 SKILL.md 里的 name: 不一致 → 改名为 name:
2. 同一个 name: 有两个文件夹（如改名后旧文件夹又被同步回来）→ 把另一个文件夹里缺的文件补进
   与 name 同名的那个，再把另一个移到 skills-backup/（不直接删除）
3. .opencode/skills 里的副本是旧版或缺文件（章节、cheatsheet 等）→ 以 copilot/skills 为准补齐 / 更新
   （只处理 .opencode 里已有、或 SKILL.md 标了 copilot-enabled-agents: opencode 的 skill）
修复后请彻底重启 Obsidian，让 Copilot 重新读取 skill。
"""
import filecmp
import re
import shutil
import sys
import time
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

NAME_RE = re.compile(r"^name:\s*[\"']?([^\"'\n]+?)[\"']?\s*$", re.M)
STAMP = time.strftime("%Y%m%d%H%M%S")


def skill_name(folder: Path):
    f = folder / "SKILL.md"
    if not f.is_file():
        return None
    text = f.read_text(encoding="utf-8", errors="ignore")
    fm = re.match(r"﻿?---\s*\n(.*?)\n---", text, re.S)
    m = NAME_RE.search(fm.group(1) if fm else text[:2000])
    return m.group(1).strip() if m else None


def skill_dirs(root: Path):
    return [d for d in sorted(root.iterdir()) if d.is_dir() and not d.name.startswith(".")]


def copy_missing(src: Path, dst: Path):
    """把 src 里有、dst 里没有的文件复制过去，不覆盖；返回复制数"""
    n = 0
    for f in src.rglob("*"):
        if f.is_file():
            t = dst / f.relative_to(src)
            if not t.exists():
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, t)
                n += 1
    return n


def backup(root: Path, folder: Path, fix: bool):
    bk = root.parent / "skills-backup"
    dest = bk / f"{folder.name}-{STAMP}"
    if fix:
        bk.mkdir(exist_ok=True)
        shutil.move(str(folder), str(dest))
    return dest


def normalize_root(root: Path, fix: bool, log):
    """问题 1、2：文件夹名 ≠ name、同名重复"""
    groups = {}
    for d in skill_dirs(root):
        n = skill_name(d)
        if n is None:
            if not (d / "SKILL.md").exists():
                log(f"  ⚪ {d.name}：没有 SKILL.md（不是 skill，忽略）")
            else:
                log(f"  ⚠ {d.name}：SKILL.md 里没有 name:，请手动检查")
            continue
        groups.setdefault(n, []).append(d)
    for name, dirs in sorted(groups.items()):
        keep = next((d for d in dirs if d.name == name), None)
        if keep is None:  # 没有与 name 同名的文件夹：选 SKILL.md 最新的那个，改名
            keep = max(dirs, key=lambda d: (d / "SKILL.md").stat().st_mtime)
            target = root / name
            log(f"  🔧 {keep.name}：文件夹名和 name: {name} 不一致 → 改名")
            if fix:
                keep.rename(target)
            dirs = [target if d == keep else d for d in dirs]
            keep = target
        for d in dirs:
            if d == keep:
                continue
            log(f"  🔧 {d.name}：和 {keep.name} 是同一个 skill（name: {name}）→ 缺的文件补进 {keep.name}，自身移到 skills-backup")
            if fix:
                n = copy_missing(d, keep)
                dest = backup(root, d, fix)
                log(f"       补了 {n} 个文件；已移到 {dest}")
    return groups


def mirror(src_root: Path, dst_root: Path, fix: bool, log):
    """问题 3：以 copilot/skills 为准，更新 .opencode/skills 里的副本"""
    for d in skill_dirs(src_root):
        name = skill_name(d)
        if name is None:
            continue
        dst = dst_root / d.name
        enabled = "copilot-enabled-agents" in (d / "SKILL.md").read_text(encoding="utf-8", errors="ignore")
        if not dst.exists() and not enabled:
            continue
        existed = dst.exists()
        changed, added = [], []
        for f in d.rglob("*"):
            if not f.is_file():
                continue
            t = dst / f.relative_to(d)
            if not t.exists():
                added.append(t)
            elif not filecmp.cmp(f, t, shallow=False):
                changed.append(t)
            else:
                continue
            if fix:
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, t)
        if changed or added:
            what = []
            if changed:
                what.append(f"{len(changed)} 个文件是旧版" + ("（含 SKILL.md）" if any(t.name == "SKILL.md" for t in changed) else ""))
            if added:
                what.append("整个 skill 不存在" if not existed else f"缺 {len(added)} 个文件")
            log(f"  🔧 .opencode/{d.name}：{'，'.join(what)} → 以 copilot/skills 为准更新")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fix = "--fix" in sys.argv
    if len(args) != 1:
        sys.exit(__doc__)
    vault = Path(args[0]).expanduser().resolve()
    roots = {"copilot/skills": vault / "copilot" / "skills", ".opencode/skills": vault / ".opencode" / "skills"}
    lines = []
    log = lines.append
    for label, root in roots.items():
        if root.is_dir():
            log(f"[{label}]")
            normalize_root(root, fix, log)
    if roots["copilot/skills"].is_dir() and roots[".opencode/skills"].is_dir():
        log("[.opencode/skills 与 copilot/skills 对比]")
        mirror(roots["copilot/skills"], roots[".opencode/skills"], fix, log)
    problems = [l for l in lines if "🔧" in l or "⚠" in l]
    print("\n".join(lines))
    if not problems:
        print("✅ 没发现问题")
    elif fix:
        print(f"✅ 已修复 {sum('🔧' in l for l in problems)} 处。请彻底重启 Obsidian，让 Copilot 重新读取 skill。")
    else:
        print(f"发现 {len(problems)} 处问题。加 --fix 自动修复。")


if __name__ == "__main__":
    main()
