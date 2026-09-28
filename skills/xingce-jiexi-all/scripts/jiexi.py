#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xingce-jiexi-all 的辅助脚本：读写 xingce-mokao-split 生成的板块复盘文件。
所有“哪些题做完了”的判断都直接看复盘栏有没有内容，所以中途断了重跑即可续上。

用法：
    python jiexi.py status <季>                                 # 看进度，并写 解析进度.md
    python jiexi.py next   <季> <板块> [--mode 错题|全部] [--batch N]   # 取下一批待解析的题
    python jiexi.py write  <季> <板块> [<结果文件>] [--force]  # 把解析写回复盘栏
    python jiexi.py check  <季> [<板块>]                        # 检查板块文件格式有没有被改坏

<季> 可以写 36、第36季，或第N季目录的完整路径。只写季数时，到库根目录（skills 往上两级，
即 行测/）下的 FB模考试卷复盘/板块复盘/第N季 找。
<结果文件> 省略时用 <第N季目录>/.jiexi-tmp.md，写入成功后自动删除。

结果文件格式（每题一段，“=== 题号” 开头，正文不用加 “> ”，脚本会加）：
    === 36
    【答案】B
    【思路】……
    === 37
    ⚠ 待核对：推不出正确答案 C，……
"""
import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def write_lf(path, text):
    # 统一用 LF 换行：Windows / Mac 通过坚果云同步时，文件不会因换行符不同而整份变动
    with open(path, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(text)


SKILL_DIR = Path(__file__).resolve().parent.parent
MAP_FILE = SKILL_DIR / "board-map.md"
HEAD_RE = re.compile(r"^### (\d+)\. (\S+)")
ANS_RE = re.compile(r"正确答案：\*\*([^*]*)\*\*\s*我的答案：\*\*([^*]*)\*\*")
MAT_RE = re.compile(r"^## 材料（第(\d+)-(\d+)题）")
NOTE = "> [!note] 复盘"
CHECK = "> [!check]"
PENDING_MARK = "⚠ 待核对"
# 复盘栏里自带的空模板行，如 “> - 错因：” “> - 考点：” “> - 下次怎么做：”，不算已写内容
PLACEHOLDER_RE = re.compile(r"^>\s*(?:[-*]\s*)?(?:\*\*)?[^：:>*]{1,12}[：:](?:\*\*)?\s*$")


def is_placeholder(line):
    return bool(PLACEHOLDER_RE.match(line.strip()))
MODES = ("错题", "全部")
DEFAULT_CFG = {"skill": "", "mode": "错题", "batch": 5, "ready": False}
SKILLS_ROOT = SKILL_DIR.parent  # 板块 skill 和本 skill 放在同一个 skills/ 目录下


_SKILL_INDEX = None


def skill_index():
    """skills/ 下所有 skill：文件夹名和 SKILL.md 里的 name: 都算"""
    global _SKILL_INDEX
    if _SKILL_INDEX is None:
        _SKILL_INDEX = set()
        for f in SKILLS_ROOT.glob("*/SKILL.md"):
            _SKILL_INDEX.add(f.parent.name)
            m = re.search(r"^name:\s*[\"']?([^\"'\n]+?)[\"']?\s*$", f.read_text(encoding="utf-8", errors="ignore"), re.M)
            if m:
                _SKILL_INDEX.add(m.group(1))
    return _SKILL_INDEX


def resolve_skill(cell):
    """映射表里可写多个候选（逗号分隔），用第一个已存在的；都不存在就返回第一个名字"""
    names = [n.strip() for n in re.split(r"[,，]", cell) if n.strip() not in ("", "-", "—")]
    for n in names:
        if n in skill_index():
            return n, True
    return (names[0] if names else ""), False


# ---------------------------------------------------------------- 映射表
def load_mapping():
    """板块 -> {skill, mode, batch}"""
    m = {}
    if not MAP_FILE.exists():
        return m
    for ln in MAP_FILE.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 4 or cells[0] in ("板块", "") or set(cells[0]) <= set("-: "):
            continue
        skill, ready = resolve_skill(cells[1])
        mode = cells[2] if cells[2] in MODES else "错题"
        batch = int(cells[3]) if cells[3].isdigit() else 5
        m[cells[0]] = {"skill": skill, "mode": mode, "batch": batch, "ready": ready}
    return m


# ---------------------------------------------------------------- 解析板块文件
@dataclass
class Q:
    num: int
    icon: str
    start: int            # "### N." 行号
    end: int              # "---" 行号
    note: int = -1        # "> [!note] 复盘" 行号
    correct: str = ""
    mine: str = ""
    body: list = field(default_factory=list)  # 题干/选项/截图（不含标题和答案）
    material: tuple = None

    def analysis(self, lines):
        if self.note < 0:
            return []
        out = [l for l in lines[self.note + 1:self.end]]
        while out and out[-1].strip() in ("", ">"):
            out.pop()
        return out

    def filled(self, lines):
        return any(l.strip() not in ("", ">") and not is_placeholder(l) for l in self.analysis(lines))

    def template(self, lines):
        """复盘栏里的空模板行（写解析时保留在解析下面）"""
        return [l for l in self.analysis(lines) if is_placeholder(l)]

    def flagged(self, lines):
        return any(PENDING_MARK in l for l in self.analysis(lines))

    def wrong(self):
        return self.icon in ("❌", "⚪")


VAULT = SKILLS_ROOT.parent.parent  # 行测/copilot/skills -> 行测/
SEASONS_DIR = VAULT / "FB模考试卷复盘" / "板块复盘"
TMP_NAME = ".jiexi-tmp.md"


def resolve_season(arg: str) -> Path:
    p = Path(arg).expanduser()
    if p.is_dir():
        return p.resolve()
    m = re.fullmatch(r"(?:第)?(\d+)(?:季)?", arg.strip())
    if m:
        cand = SEASONS_DIR / f"第{int(m.group(1))}季"
        if cand.is_dir():
            return cand
        hits = [d for d in VAULT.glob(f"**/板块复盘/第{int(m.group(1))}季") if d.is_dir()]
        if hits:
            return hits[0]
    sys.exit(f"找不到第N季目录：{arg}（按季数查找的位置：{SEASONS_DIR}）")


def board_files(season: Path):
    # 01-政治理论.md … 13-资料分析.md；00-第N季总览.md 不算板块
    return [f for f in sorted(season.glob("[0-9][0-9]-*.md")) if not f.name.startswith("00-")]


def board_file(season: Path, board: str) -> Path:
    fs = sorted(season.glob(f"*-{board}.md"))
    if not fs:
        sys.exit(f"找不到板块文件：{season}/??-{board}.md")
    return fs[0]


def parse_board(text):
    lines = text.split("\n")
    qs, mats, cur, mat = [], {}, None, None
    for i, ln in enumerate(lines):
        h = HEAD_RE.match(ln)
        if h:
            cur = Q(num=int(h.group(1)), icon=h.group(2), start=i, end=len(lines))
            cur.material = mat if mat and mat[0] <= cur.num <= mat[1] else None
            qs.append(cur)
            continue
        mm = MAT_RE.match(ln)
        if mm:
            mat = (int(mm.group(1)), int(mm.group(2)))
            mats[mat] = [ln]
            cur = None
            continue
        if cur is None:
            if mat in mats and not ln.startswith("---"):
                mats[mat].append(ln)
            continue
        if ln.strip() == "---":
            cur.end = i
            cur = None
            continue
        if ln.startswith(NOTE):
            cur.note = i
        elif cur.note < 0:
            a = ANS_RE.search(ln)
            if a:
                cur.correct, cur.mine = a.group(1).strip("?"), a.group(2).strip("—")
            elif not ln.startswith(CHECK):
                cur.body.append(ln)
    return lines, qs, mats


def targets(qs, mode):
    return [q for q in qs if mode == "全部" or q.wrong()]


# ---------------------------------------------------------------- status
def cmd_status(season: Path, write=True):
    mp = load_mapping()
    rows, flagged_all = [], []
    for f in board_files(season):
        board = f.stem.split("-", 1)[1]
        cfg = mp.get(board, DEFAULT_CFG)
        lines, qs, _ = parse_board(f.read_text(encoding="utf-8"))
        tg = targets(qs, cfg["mode"])
        done = [q for q in tg if q.filled(lines)]
        flagged = [q.num for q in qs if q.flagged(lines)]
        flagged_all += [(board, n) for n in flagged]
        left = [q.num for q in tg if not q.filled(lines)]
        if not cfg["skill"]:
            state = "跳过（未指定解题skill）"
        elif not cfg["ready"]:
            state = f"跳过（{cfg['skill']} 尚未创建）"
        elif not tg:
            state = "✅ 无错题" if cfg["mode"] == "错题" else "✅ 无题"
        elif not left:
            state = "✅ 完成"
        elif done:
            state = "⏳ 进行中"
        else:
            state = "未开始"
        rows.append((f.stem, cfg["skill"] or "-", cfg["mode"], len(qs), len(tg), len(done), len(flagged), left, state))

    out = ["# 解析进度", "", "> 由 `jiexi.py status` 根据各板块复盘栏自动生成，不要手改。", "",
           "| 板块 | 解题skill | 范围 | 题数 | 目标 | 已解析 | 待核对 | 状态 |",
           "| --- | --- | :-: | :-: | :-: | :-: | :-: | --- |"]
    for stem, sk, mode, n, t, d, fl, left, st in rows:
        out.append(f"| [[{stem}]] | {sk} | {mode} | {n} | {t} | {d} | {fl} | {st} |")
    ready = {k for k, v in mp.items() if v["ready"]}
    pend = [(r[0], r[7]) for r in rows if r[0].split("-", 1)[1] in ready and r[7]]
    if pend:
        out += ["", "## 未完成的题", ""] + [f"- {s}：{', '.join(map(str, l))}" for s, l in pend]
    if flagged_all:
        out += ["", "## ⚠ 待核对", ""] + [f"- {b} 第{n}题" for b, n in flagged_all]
    text = "\n".join(out) + "\n"
    if write:
        write_lf(season / "解析进度.md", text)
    print(text)


# ---------------------------------------------------------------- next
def cmd_next(season: Path, board: str, mode=None, batch=None):
    cfg = load_mapping().get(board, DEFAULT_CFG)
    mode = mode or cfg["mode"]
    batch = batch or cfg["batch"]
    f = board_file(season, board)
    lines, qs, mats = parse_board(f.read_text(encoding="utf-8"))
    left = [q for q in targets(qs, mode) if not q.filled(lines)]
    if not left:
        print(f"【{board}】没有待解析的题（范围：{mode}）。")
        return
    todo = left[:batch]
    att = f.parent / "attachments"
    print(f"【{board}】解题skill：{cfg['skill'] or '（未配置）'}　范围：{mode}　"
          f"本批 {len(todo)} 题，本板块还剩 {len(left)} 题")
    print(f"板块文件：{f}")
    print(f"临时文件：{f.parent / TMP_NAME}（本批解析写到这里，再运行 write）")
    print(f"本批题号：{' '.join(str(q.num) for q in todo)}")
    print(f"截图目录：{att}")
    shown = set()
    for q in todo:
        if q.material and q.material not in shown and q.material in mats:
            shown.add(q.material)
            print("\n" + "=" * 20 + f" 材料（第{q.material[0]}-{q.material[1]}题） " + "=" * 20)
            print(expand("\n".join(mats[q.material][1:]).strip(), att))
        print("\n" + "-" * 20 + f" 第{q.num}题 " + "-" * 20)
        print(expand("\n".join(q.body).strip(), att))
        print(f"正确答案：{q.correct or '?'}　我的答案：{q.mine or '未作答'}")


def expand(text, att: Path):
    # ![[S36-Q066.png]] -> [截图] 绝对路径，方便 agent 直接打开看图
    return re.sub(r"!\[\[([^\]|]+)[^\]]*\]\]", lambda m: f"[截图] {att / m.group(1)}", text)


# ---------------------------------------------------------------- write
def cmd_write(season: Path, board: str, result: Path = None, force=False):
    result = result or season / TMP_NAME
    if not result.is_file():
        sys.exit(f"找不到结果文件：{result}")
    raw = result.read_text(encoding="utf-8")
    parts = re.split(r"^===\s*(\d+)\s*$", raw, flags=re.M)
    res = {int(parts[i]): parts[i + 1].strip("\n") for i in range(1, len(parts) - 1, 2)}
    if not res:
        sys.exit("结果文件里没有找到 “=== 题号” 段落。")
    f = board_file(season, board)
    lines, qs, _ = parse_board(f.read_text(encoding="utf-8"))
    by_num = {q.num: q for q in qs}
    ok, skipped, missing = [], [], []
    # 从后往前改，行号不乱
    for num in sorted(res, key=lambda n: by_num[n].start if n in by_num else -1, reverse=True):
        q = by_num.get(num)
        if q is None or q.note < 0:
            missing.append(num); continue
        if q.filled(lines) and not force:
            skipped.append(num); continue
        body = [l.rstrip() for l in res[num].strip().split("\n")]
        body = [(l if l.startswith(">") else ("> " + l if l.strip() else ">")) for l in body]
        tpl = [] if force else q.template(lines)
        if tpl:
            body += [">"] + tpl
        lines[q.note + 1:q.end] = body + [""]
        ok.append(num)
    write_lf(f, "\n".join(lines))
    if result.name == TMP_NAME:
        result.unlink()
    print(f"已写入 {f.name}：{sorted(ok)}")
    if skipped:
        print(f"⚠ 复盘栏已有内容，未覆盖（确需覆盖加 --force）：{sorted(skipped)}")
    if missing:
        print(f"⚠ 板块里没有这些题号：{sorted(missing)}")


# ---------------------------------------------------------------- check
TABLE_RE = re.compile(r"^\| \[\[#(\d+)\. ")


def check_board(f: Path):
    """返回问题列表；空列表表示格式正常"""
    text = f.read_text(encoding="utf-8")
    lines, qs, _ = parse_board(text)
    probs = []
    if not text.startswith("---\n"):
        probs.append("frontmatter 丢失")
    heads = [q.num for q in qs]
    dup = sorted({n for n in heads if heads.count(n) > 1})
    if dup:
        probs.append(f"题号重复：{dup}")
    table = [int(m.group(1)) for m in map(TABLE_RE.match, lines) if m]
    if table and sorted(set(table)) != sorted(set(heads)):
        lost = sorted(set(table) - set(heads))
        extra = sorted(set(heads) - set(table))
        probs.append(f"题目与速览表对不上：缺 {lost} 多 {extra}")
    for q in qs:
        where = f"第{q.num}题"
        if q.end >= len(lines):
            probs.append(f"{where}：结尾的 --- 分隔线丢失"); continue
        if not q.correct:
            probs.append(f"{where}：答案行丢失或被改动")
        if q.note < 0:
            probs.append(f"{where}：“> [!note] 复盘” 行丢失"); continue
        bad = [i + 1 for i in range(q.note + 1, q.end) if lines[i].strip() and not lines[i].startswith(">")]
        if bad:
            probs.append(f"{where}：复盘栏第 {bad} 行没有以 “> ” 开头，会跑出 callout")
        inner_blank = [i + 1 for i, l in enumerate(q.analysis(lines), q.note + 1) if not l.strip()]
        if inner_blank:
            probs.append(f"{where}：复盘栏中间有空行（第 {inner_blank} 行），callout 会被截断，空行要写成 “>”")
    return probs


def cmd_check(season: Path, board=None):
    files = [board_file(season, board)] if board else board_files(season)
    bad = 0
    for f in files:
        probs = check_board(f)
        if probs:
            bad += 1
            print(f"❌ {f.name}")
            for p in probs:
                print(f"   - {p}")
        else:
            print(f"✅ {f.name}")
    sys.exit(1 if bad else 0)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("status"); p.add_argument("season")
    p.add_argument("--no-write", action="store_true")
    p = sub.add_parser("next"); p.add_argument("season"); p.add_argument("board")
    p.add_argument("--mode", choices=MODES); p.add_argument("--batch", type=int)
    p = sub.add_parser("write"); p.add_argument("season"); p.add_argument("board"); p.add_argument("result", nargs="?")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("check"); p.add_argument("season"); p.add_argument("board", nargs="?")
    a = ap.parse_args()
    season = resolve_season(a.season)
    if a.cmd == "status":
        cmd_status(season, not a.no_write)
    elif a.cmd == "next":
        cmd_next(season, a.board, a.mode, a.batch)
    elif a.cmd == "write":
        cmd_write(season, a.board, Path(a.result) if a.result else None, a.force)
    else:
        cmd_check(season, a.board)


if __name__ == "__main__":
    main()
