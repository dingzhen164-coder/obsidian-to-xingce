#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行测 Obsidian 库全面体检（只读，不修改任何文件，只写一份报告）。

用法：
    python vault_audit.py "<库根目录，即 行测/>"

报告写到 <库根目录>/行测体检报告.md，同时在终端打印摘要。
检查：库概览、同步残留（坚果云冲突副本等）、skill（重复/改名/.opencode 副本/调度节/硬编码路径/token 体量）、
板块映射、每一季的解析进度和格式、Copilot 项目、断链、空文件、大文件、换行符。
"""
import importlib.util
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CAP = 30  # 每类问题最多列出多少条
SKIP_DIRS = {".git", ".obsidian", ".trash", "node_modules", "__pycache__", ".smart-env", ".makemd"}
BOARD_SKILLS = ["political-theory-reasoning", "center-comprehension-jiangwei", "xue-rui-argument-logic",
                "xue-rui-formal-logic", "xue-rui-yituowu"]


def tokens(text):
    cjk = len(re.findall(r"[一-鿿]", text))
    return int(cjk + (len(text) - cjk) / 3.5)


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{u}"
        n /= 1024
    return f"{n:.1f}TB"


def walk(vault: Path):
    for dirpath, dirnames, filenames in os.walk(vault):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            yield Path(dirpath) / fn


def load_module(path: Path, name: str):
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        return mod
    except SystemExit:
        return None
    except Exception:
        return None


class Report:
    def __init__(self):
        self.lines, self.issues = [], []

    def h(self, t):
        self.lines += ["", f"## {t}", ""]

    def add(self, *ls):
        self.lines += list(ls)

    def issue(self, level, text):
        self.issues.append((level, text))

    def items(self, title, rows, level="⚠"):
        if not rows:
            return
        self.issue(level, f"{title}：{len(rows)} 处")
        self.add(f"**{level} {title}（{len(rows)}）**", "")
        self.add(*[f"- {r}" for r in rows[:CAP]])
        if len(rows) > CAP:
            self.add(f"- ……另有 {len(rows) - CAP} 处")
        self.add("")


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    vault = Path(sys.argv[1]).expanduser().resolve()
    if not vault.is_dir():
        sys.exit(f"找不到目录：{vault}")
    R = Report()
    step = lambda t: print(f"… {t}", flush=True)
    step("扫描文件")
    files = list(walk(vault))
    step(f"共 {len(files)} 个文件")
    rel = lambda p: str(p.relative_to(vault)).replace("\\", "/")

    # ---------------------------------------------------------------- 1. 概览
    R.h("1. 库概览")
    top = defaultdict(lambda: [0, 0, 0])  # md, other, size
    for f in files:
        parts = f.relative_to(vault).parts
        key = parts[0] if len(parts) > 1 else "（根目录文件）"
        try:
            size = f.stat().st_size
        except OSError:
            continue
        top[key][0 if f.suffix == ".md" else 1] += 1
        top[key][2] += size
    R.add("| 顶层目录 | md | 其它文件 | 大小 |", "| --- | --: | --: | --: |")
    for k, (md, other, size) in sorted(top.items(), key=lambda kv: -kv[1][2]):
        R.add(f"| {k} | {md} | {other} | {human(size)} |")
    R.add("", f"共 {len(files)} 个文件（不含 {', '.join(sorted(SKIP_DIRS))}）。")
    for k, (md, other, size) in top.items():
        if (md + other) > 0.5 * len(files) and len(files) > 5000:
            R.issue("⚠", f"「{k}」占了全库 {(md + other) * 100 // len(files)}% 的文件（{md + other} 个）——会拖慢 Obsidian 索引、坚果云同步和 AI 搜索，考虑移出库或在 Obsidian 里排除")

    # ---------------------------------------------------------------- 2. 同步残留
    step("检查同步残留")
    R.h("2. 同步与残留文件")
    conflict = [rel(f) for f in files if re.search(
        r"冲突副本|[\(（_]\s*冲突|conflicted copy|[\s(_]conflict[\s_)\d]|\.conflict\b", f.name, re.I)]
    R.items("坚果云 / 同步冲突副本（需人工对比后删除）", conflict, "❌")
    junk = [rel(f) for f in files if f.name in (".DS_Store", "Thumbs.db", "desktop.ini") or f.name.startswith("~$")
            or f.suffix in (".tmp", ".crdownload", ".part")]
    R.items("系统 / 临时垃圾文件（可删）", junk, "⚪")
    leftovers = [rel(f) for f in files if f.name == ".jiexi-tmp.md"]
    R.items("解析中断留下的临时文件 .jiexi-tmp.md（可删；说明有一次写入没完成）", leftovers)
    backups = sorted({rel(p) for p in vault.rglob("skills-backup") if p.is_dir()})
    old_roots = [str(p) for p in (vault.parent / "copilot", vault.parent / "copilot.old") if p.exists()]
    R.items("skill 备份 / 旧目录（确认无用后可删）", backups + old_roots, "⚪")

    # ---------------------------------------------------------------- 3. skills
    step("检查 skills")
    R.h("3. Skills")
    scripts = vault / "copilot" / "skills" / "xingce-jiexi-all" / "scripts"
    doctor = load_module(scripts / "skills_doctor.py", "skills_doctor")
    if doctor:
        dl = []
        roots = {"copilot/skills": vault / "copilot" / "skills", ".opencode/skills": vault / ".opencode" / "skills"}
        for label, root in roots.items():
            if root.is_dir():
                dl.append(f"[{label}]")
                doctor.normalize_root(root, False, dl.append)
        if all(r.is_dir() for r in roots.values()):
            doctor.mirror(roots["copilot/skills"], roots[".opencode/skills"], False, dl.append)
        probs = [l.strip() for l in dl if "🔧" in l or "⚠" in l]
        R.items("skill 结构问题（运行 skills_doctor.py --fix 可自动修）", probs, "❌")
    else:
        R.issue("⚠", "没找到 skills_doctor.py，跳过 skill 结构检查（先运行一次安装命令）")

    sk_root = vault / "copilot" / "skills"
    if sk_root.is_dir():
        R.add("| skill | 文件夹=name | SKILL.md 约 token | 章节 | description 含中文 | 调度节 | 硬编码路径 |",
              "| --- | :-: | --: | --: | :-: | :-: | :-: |")
        hard, broken, big = [], [], []
        for d in sorted(p for p in sk_root.iterdir() if p.is_dir()):
            f = d / "SKILL.md"
            if not f.is_file():
                continue
            t = f.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r"^name:\s*[\"']?([^\"'\n]+?)[\"']?\s*$", t, re.M)
            name = m.group(1).strip() if m else "?"
            desc = re.search(r"^description:(.*?)(?=^\w[\w-]*:|^---)", t, re.M | re.S)
            zh = "✅" if desc and re.search(r"[一-鿿]", desc.group(1)) else "—"
            nch = len(list((d / "chapters").glob("*.md"))) if (d / "chapters").is_dir() else 0
            disp = "✅" if "## 被 xingce-jiexi-all 调度时" in t else ("❌" if name in BOARD_SKILLS else "—")
            paths = re.findall(r"(?:/Users/[^\s`'\"）)]+|[A-Z]:\\\\?[^\s`'\"）)]+)", t)
            tk = tokens(t)
            R.add(f"| {d.name} | {'✅' if name == d.name else '❌ ' + name} | {tk} | {nch} | {zh} | {disp} | {len(paths) or ''} |")
            if paths:
                hard.append(f"{d.name}：{', '.join(sorted(set(paths))[:3])}")
            if tk > 6000:
                big.append(f"{d.name}：SKILL.md 约 {tk} token（每次加载都要付，建议把细节移到 chapters/cheatsheet）")
            t_nocode = re.sub(r"```.*?```|~~~~.*?~~~~", "", t, flags=re.S)
            for link in re.findall(r"\]\(((?:chapters|references)/[^)#]+|[\w.-]+\.md)\)", t_nocode):
                if "<" not in link and not (d / link).exists():
                    broken.append(f"{d.name} → {link}")
            if name in BOARD_SKILLS and disp != "✅":
                R.issue("❌", f"{d.name} 缺少「被 xingce-jiexi-all 调度时」一节（重新运行安装命令）")
        R.add("")
        R.items("skill 里写死的本机路径（换电脑会失效，确认是否两台电脑都写了）", hard, "⚪")
        R.items("SKILL.md 里指向不存在文件的链接", broken, "❌")
        R.items("SKILL.md 体量偏大", big, "⚠")

    # ---------------------------------------------------------------- 4. 板块映射 & 各季
    step("检查板块与各季")
    R.h("4. 板块映射与各季解析")
    jiexi = load_module(scripts / "jiexi.py", "jiexi")
    if jiexi:
        mp = jiexi.load_mapping()
        R.add("| 板块 | 解题 skill | 已就绪 |", "| --- | --- | :-: |")
        for b, c in mp.items():
            R.add(f"| {b} | {c['skill'] or '-'} | {'✅' if c['ready'] else '—'} |")
        R.add("")
        seasons_dir = jiexi.SEASONS_DIR
        seasons = sorted((d for d in seasons_dir.glob("第*季") if d.is_dir()),
                         key=lambda d: int(re.sub(r"\D", "", d.name) or 0)) if seasons_dir.is_dir() else []
        if not seasons:
            R.issue("⚠", f"没找到任何第N季目录（{seasons_dir}）")
        fmt_bad = []
        R.add("| 季 | 板块数 | 错题/未作答 | 已解析 | 待核对 | 可解析但未做 |", "| --- | --: | --: | --: | --: | --: |")
        for s in seasons:
            nb = tgt = done = flag = todo = 0
            for f in jiexi.board_files(s):
                nb += 1
                board = f.stem.split("-", 1)[1]
                cfg = mp.get(board, jiexi.DEFAULT_CFG)
                lines, qs, _ = jiexi.parse_board(f.read_text(encoding="utf-8"))
                tg = jiexi.targets(qs, cfg["mode"])
                tgt += len(tg)
                done += sum(q.filled(lines) for q in tg)
                flag += sum(q.flagged(lines) for q in qs)
                if cfg["ready"]:
                    todo += sum(not q.filled(lines) for q in tg)
                for p in jiexi.check_board(f):
                    fmt_bad.append(f"{s.name}/{f.name}：{p}")
            R.add(f"| {s.name} | {nb} | {tgt} | {done} | {flag} | {todo} |")
            if flag:
                R.issue("⚠", f"{s.name} 有 {flag} 题标了“⚠ 待核对”，需要你人工看一下")
        R.add("")
        R.items("板块文件格式问题（复盘栏跑出 callout、题目丢失等）", fmt_bad, "❌")
        pdf_dir = seasons_dir.parent / "模考试卷"
        if pdf_dir.is_dir():
            done_s = {re.sub(r"\D", "", s.name) for s in seasons}
            pdfs = [p.name for p in pdf_dir.glob("*.pdf")
                    if (m := re.search(r"第([一二三四五六七八九十百零\d]+)季", p.stem))
                    and str(jiexi_cn2int(m.group(1))) not in done_s]
            R.items("模考试卷里还没拆分的 PDF", pdfs, "⚪")
    else:
        R.issue("⚠", "没找到 jiexi.py，跳过板块与各季检查")

    # ---------------------------------------------------------------- 5. Copilot 项目
    R.h("5. Copilot 项目")
    proj = vault / "copilot" / "projects"
    if proj.is_dir():
        R.add("| 项目 | 说明文件约 token | 说明 |", "| --- | --: | --- |")
        for d in sorted(p for p in proj.iterdir() if p.is_dir()):
            tk = sum(tokens(f.read_text(encoding="utf-8", errors="ignore")) for f in d.glob("*.md"))
            note = "偏大：在这个项目里开的每个对话都会先读它" if tk > 3000 else ""
            R.add(f"| {d.name} | {tk} | {note} |")
        R.add("", "跑解析时建议在**不属于任何项目**的对话里进行，避免额外读项目说明。")

    # ---------------------------------------------------------------- 6. 笔记质量
    step("检查笔记和链接")
    R.h("6. 笔记")
    in_skills = lambda f: "skills" in f.relative_to(vault).parts or "copilot-conversations" in f.relative_to(vault).parts
    mds = [f for f in files if f.suffix == ".md" and not in_skills(f)]
    names = Counter()
    stems = set()
    for f in files:
        stems.add(f.stem.lower()); stems.add(f.name.lower())
    for f in mds:
        names[f.stem] += 1
    empty, crlf, broken_links = [], 0, []
    link_re = re.compile(r"!?\[\[([^\]|#^]*)(?:[#^][^\]|]*)?(?:\|[^\]]*)?\]\]")
    for i, f in enumerate(mds, 1):
        if i % 500 == 0:
            step(f"已检查 {i}/{len(mds)} 篇笔记")
        try:
            raw = f.read_bytes()
        except OSError:
            continue
        if len(raw.strip()) == 0:
            empty.append(rel(f))
        if b"\r\n" in raw:
            crlf += 1
        text = raw.decode("utf-8", errors="ignore")
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        for tgt in link_re.findall(text):
            tgt = tgt.strip()
            if not tgt:
                continue
            last = tgt.replace("\\", "/").split("/")[-1].lower()
            if last not in stems and last + ".md" not in stems:
                broken_links.append(f"{rel(f)} → [[{tgt}]]")
    R.items("空白笔记", empty, "⚪")
    repo_files = {"skill", "readme", "index", "project", "claude", "agents", "license", "changelog", "contributing",
                  "security", "backers", "404", "bug_report", "feature_request", "pull_request_template", "code_of_conduct"}
    dup = [f"{n}（{c} 个）" for n, c in names.items()
           if c > 1 and n.lower() not in repo_files and not n.lower().startswith(("readme", "security"))]
    R.items("同名笔记（[[链接]] 可能指错文件）", sorted(dup), "⚪")
    if broken_links:
        per = Counter(b.split("/")[0] for b in broken_links)
        R.add("断链按顶层文件夹统计：" + "，".join(f"{k} {v}" for k, v in per.most_common()), "")
    R.items("断开的 [[链接]]（目标笔记不存在；不含 skills 目录里的示例链接）", broken_links, "⚠")
    def _size(f):
        try:
            return f.stat().st_size
        except OSError:
            return 0
    big = [f"{rel(f)}（{human(_size(f))}）" for f in files if _size(f) > 20 * 1024 * 1024]
    R.items("超过 20MB 的大文件（拖慢坚果云同步，考虑移出库）", big, "⚪")
    R.add(f"md 共 {len(mds)} 个，其中 Windows 换行（CRLF）{crlf} 个——不影响使用，只是两台电脑都改时同步差异会变大。")

    # ---------------------------------------------------------------- 输出
    order = {"❌": 0, "⚠": 1, "⚪": 2}
    summary = ["# 行测体检报告", "", f"库：`{vault}`", "", "## 摘要（❌ 需要修 / ⚠ 建议看 / ⚪ 可选清理）", ""]
    if R.issues:
        summary += [f"- {lv} {t}" for lv, t in sorted(R.issues, key=lambda x: order[x[0]])]
    else:
        summary += ["- ✅ 没发现问题"]
    out = vault / "行测体检报告.md"
    with open(out, "w", encoding="utf-8", newline="\n") as fp:
        fp.write("\n".join(summary + R.lines) + "\n")
    print("\n".join(summary))
    print(f"\n完整报告：{out}")


def jiexi_cn2int(s):
    if s.isdigit():
        return int(s)
    d = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    total, num = 0, 0
    for ch in s:
        if ch in d:
            num = d[ch]
        elif ch == "十":
            total += (num or 1) * 10; num = 0
        elif ch == "百":
            total += (num or 1) * 100; num = 0
    return total + num


if __name__ == "__main__":
    main()
