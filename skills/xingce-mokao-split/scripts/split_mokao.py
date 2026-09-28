#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
粉笔行测模考试卷 PDF -> 按板块拆分的 Obsidian Markdown 复盘笔记

用法：
    python split_mokao.py "<模考试卷.pdf>" [--out <输出目录>] [--force] [--snap-all]

默认输出目录：<pdf所在目录>/../板块复盘/第N季   （N 从文件名里的“第X季”识别）
依赖：pip install pymupdf
"""
import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz  # 旧版 PyMuPDF
    except ImportError:
        sys.exit("缺少依赖：请先运行  pip install pymupdf")

for _s in (sys.stdout, sys.stderr):
    try:  # Windows 下输出被 agent 捕获时默认是 GBK，打印 ✅ ⚠ 会报错
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def write_lf(path, text):
    # 统一用 LF 换行：Windows / Mac 通过坚果云同步时，文件不会因换行符不同而整份变动
    with open(path, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(text)


# ---------------------------------------------------------------- 配置
BOARDS = [  # (文件名序号, 板块名)
    ("01", "政治理论"), ("02", "常识判断"), ("03", "逻辑填空"), ("04", "中心理解"),
    ("05", "语句排序"), ("06", "数量关系"), ("07", "图形推理"), ("08", "定义判断"),
    ("09", "类比关系"), ("10", "论证逻辑"), ("11", "形式逻辑"), ("12", "一拖五"),
    ("13", "资料分析"),
]
BOARD_ORDER = {b: i for i, (_, b) in enumerate(BOARDS)}
SECTION_RE = re.compile(r"^[一二三四五六七八九十]+[\.．、]\s*(政治理论|常识判断|言语理解与表达|数量关系|判断推理|资料分析)")
QSTART_RE = re.compile(r"^(\d{1,3})[\.．]\s*(.*)$")
OPT_START_RE = re.compile(r"^A[\.．]")
OPT_SPLIT_RE = re.compile(r"(?:^|(?<=\s))([A-D])[\.．]")
ANS_RE = re.compile(r"^(正确答案|你的答案)[:：]\s*([A-D]*)")
NEWPARA_PREFIX = ("依次填入", "填入画横线", "这段文字", "最适合做", "根据上述", "根据这段", "以下哪项",
                  "以下各项", "将以上", "根据题干", "下列说法与", "根据已知")
ALWAYS_SNAP = {"数量关系", "图形推理"}
ARGUMENT_KW = ("质疑", "削弱", "支持", "加强", "前提", "假设", "解释", "反驳", "反对", "评价", "漏洞", "结论")
FORMAL_KW = ("可以得出", "可以推出", "能够推出", "能推出", "一定为真", "一定为假", "不能确定",
             "必然为真", "必然为假", "可能为真", "哪项安排", "推出以下")
HEADER_TAIL_KW = ("本部分", "所给出的", "在这部分", "根据题目要求", "请根据", "要求你", "进行分析")
IMG = "\x00IMG"  # 图片占位行（资料分析的表格/图表常常是图片，没有文字）
FIGURE_KW = ("填入问号处", "分为两类", "正方体", "多面体", "截面", "展开图", "视图", "立体图形", "拼合", "组合而成")


def norm(s: str) -> str:
    # 只把“康熙部首”等兼容字符（如 ⼀ ⾔ ⽂）还原成常用汉字，保留全角标点和①②③
    return "".join(unicodedata.normalize("NFKC", c) if 0x2E80 <= ord(c) <= 0x2FDF else c
                   for c in s).replace("\u3000", " ")


def cn2int(s: str) -> int:
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


# ---------------------------------------------------------------- 数据结构
@dataclass
class Line:
    page: int
    y0: float
    y1: float
    x0: float
    text: str


@dataclass
class Material:
    lines: list = field(default_factory=list)
    qnums: list = field(default_factory=list)
    end: Line = None  # 材料之后第一题的起始行


@dataclass
class Question:
    num: int
    section: str
    start: Line
    stem_lines: list = field(default_factory=list)
    opt_lines: list = field(default_factory=list)
    correct: str = ""
    mine: str = ""
    ans_line: Line = None
    material: Material = None
    board: str = ""
    options: dict = field(default_factory=dict)
    images: list = field(default_factory=list)


# ---------------------------------------------------------------- 1. 抽取带坐标的行
def extract_lines(doc):
    lines = []
    for pno, page in enumerate(doc):
        h = page.rect.height
        top, bottom = h * 0.083, h * 0.935  # 去掉页眉/页脚
        words = [w for w in page.get_text("words") if top < w[1] < bottom]
        words = [w for w in words if norm(w[4]).strip() not in ("粉笔", "Fb", "FB", "Fb粉笔")]
        # 逻辑填空的横线是画出来的细矩形 -> 当作 "____" 伪词插回去
        for dr in page.get_drawings():
            r = dr["rect"]
            if r.height < 1.5 and 12 < r.width < 60 and top < r.y0 < bottom:
                words.append((r.x0, r.y0 - 10, r.x1, r.y0, "____", -1, -1, -1))
        words.sort(key=lambda w: (round(w[3]), w[0]))
        rows = []
        for w in words:
            for row in rows:
                if abs(row["y1"] - w[3]) < 3.5:
                    row["ws"].append(w); break
            else:
                rows.append({"y1": w[3], "ws": [w]})
        for row in rows:
            ws = sorted(row["ws"], key=lambda w: w[0])
            txt, prev = "", None
            for w in ws:
                if prev is not None and w[0] - prev[2] > 4:
                    txt += " "
                txt += w[4]
                prev = w
            txt = norm(txt).strip()
            if txt:
                lines.append(Line(pno, min(w[1] for w in ws if w[4] != "____") if any(w[4] != "____" for w in ws) else ws[0][1],
                                  max(w[3] for w in ws), ws[0][0], txt))
        for info in page.get_image_info():
            x0, y0, x1, y1 = info["bbox"]
            if x1 - x0 >= page.rect.width * 0.9 or y1 < top or y0 > bottom:
                continue  # 页眉条 / 平铺水印
            if (x1 - x0) * (y1 - y0) > 1500:  # 公式小图不算“材料”
                lines.append(Line(pno, y0, y1, x0, IMG))
    lines.sort(key=lambda l: (l.page, l.y0))
    return lines


# ---------------------------------------------------------------- 2. 解析题目
def parse(lines, left):
    questions, materials = [], []
    section, cur, expected = None, None, 1
    mat_buf, cur_mat, mat_used = [], None, 0
    skip_header_tail = False
    for ln in lines:
        t = ln.text
        m = SECTION_RE.match(t)
        if m:
            section = m.group(1); cur = None
            mat_buf, cur_mat, mat_used = [], None, 0
            skip_header_tail = True
            continue
        if skip_header_tail and not QSTART_RE.match(t) and (
                any(k in t for k in HEADER_TAIL_KW) or (len(t) < 30 and t.endswith("。"))):
            continue
        skip_header_tail = False
        a = ANS_RE.match(t)
        if a:
            if cur is not None:
                if a.group(1) == "正确答案":
                    cur.correct, cur.ans_line = a.group(2), ln
                else:
                    cur.mine = a.group(2)
            continue
        q = QSTART_RE.match(t)
        # 题号悬挂在正文左边；题干以数字开头（如“7.2026年…”）时靠这一点区分
        if q and int(q.group(1)) == expected and section and (
                ln.x0 < left - 3 or not q.group(2)[:1].isdigit()):
            # 新材料？
            if mat_buf and section in ("资料分析", "判断推理"):
                cur_mat = Material(lines=mat_buf, end=ln); materials.append(cur_mat); mat_used = 0
            elif section == "判断推理" and cur_mat and mat_used >= 5:
                cur_mat = None
            mat_buf = []
            cur = Question(num=expected, section=section, start=ln)
            if q.group(2):
                cur.stem_lines.append(q.group(2))
            if cur_mat and section in ("资料分析", "判断推理"):
                cur.material = cur_mat; cur_mat.qnums.append(expected); mat_used += 1
            questions.append(cur); expected += 1
            continue
        if t == IMG and cur is not None and cur.ans_line is None:
            continue
        if cur is not None and cur.ans_line is None:
            if cur.opt_lines or OPT_START_RE.match(t):
                cur.opt_lines.append(t)
            else:
                cur.stem_lines.append((t, ln.x0))
        else:
            mat_buf.append(ln)
    return questions, materials


def join_stem(items, left):
    out = ""
    for it in items:
        t, x0 = (it, left) if isinstance(it, str) else it
        newpara = (re.match(r"^[①②③④⑤⑥⑦⑧⑨⑩]|^[（(]\d+[）)]", t) or t.startswith(NEWPARA_PREFIX)
                   or x0 > left + 12)
        if out and newpara:
            out += "\n\n"
        out += t
    return out.strip()


def split_options(opt_lines):
    txt = "\n".join(opt_lines)
    ms = list(OPT_SPLIT_RE.finditer(txt))
    opts = {}
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(txt)
        opts[m.group(1)] = txt[m.end():end].replace("\n", "").strip()
    return opts


# ---------------------------------------------------------------- 3. 分类
def classify(q, stem):
    s = q.section
    if s in ("政治理论", "常识判断", "数量关系", "资料分析"):
        return s
    if s == "言语理解与表达":
        if "重新排列" in stem or "语序正确" in stem:
            return "语句排序"
        if "依次填入" in stem:
            return "逻辑填空"
        if "填入" in stem and "横线" in stem:
            longest = max((len(v) for v in q.options.values()), default=0)
            return "逻辑填空" if longest <= 8 else "中心理解"
        return "中心理解"
    if s == "判断推理":
        if q.material is not None:
            return "一拖五"
        if any(k in stem for k in FIGURE_KW) or set(q.options.values()) <= {"A", "B", "C", "D"}:
            return "图形推理"
        if "定义" in stem:
            return "定义判断"
        first = stem.split("\n")[0]
        if ("对于" in stem and "相当于" in stem) or (len(first) <= 25 and re.search(r"[:：]", first)
                                                   and not re.search(r"[，。？?]", first)):
            return "类比关系"
        if any(k in stem for k in ARGUMENT_KW):
            return "论证逻辑"
        if any(k in stem for k in FORMAL_KW):
            return "形式逻辑"
        return "论证逻辑"
    return s


# ---------------------------------------------------------------- 4. 截图
def content_box(page):
    h = page.rect.height
    return h * 0.083, h * 0.935


def region_segments(doc, start: Line, end_page, end_y):
    """返回 [(page, y0, y1), ...]，可跨页"""
    segs = []
    for p in range(start.page, end_page + 1):
        top, bottom = content_box(doc[p])
        y0 = start.y0 - 6 if p == start.page else top
        y1 = end_y - 2 if p == end_page else bottom
        if y1 - y0 > 8:
            segs.append((p, y0, y1))
    return segs


def has_images(doc, segs):
    for p, y0, y1 in segs:
        page = doc[p]
        for info in page.get_image_info():
            x0, iy0, x1, iy1 = info["bbox"]
            if x1 - x0 >= page.rect.width * 0.9 or iy1 < 0 or iy0 > page.rect.height:
                continue  # 页眉条 / 平铺水印
            if iy1 > y0 and iy0 < y1:
                return True
    return False


def snap(doc, segs, att_dir: Path, stem_name: str):
    names = []
    for i, (p, y0, y1) in enumerate(segs):
        page = doc[p]
        clip = fitz.Rect(20, y0, page.rect.width - 30, y1)
        pix = page.get_pixmap(clip=clip, matrix=fitz.Matrix(2, 2))
        name = f"{stem_name}{'' if len(segs) == 1 else '-' + str(i + 1)}.png"
        pix.save(str(att_dir / name))
        names.append(name)
    return names


# ---------------------------------------------------------------- 5. 输出 Markdown
def status(q):
    if not q.mine:
        return "⚪", "未作答"
    return ("✅", "正确") if q.mine == q.correct else ("❌", "错误")


def render_question(q, stem):
    icon, st = status(q)
    out = [f"### {q.num}. {icon}", ""]
    if q.images:
        out += [f"![[{n}]]" for n in q.images] + [""]
    if stem:
        out += [stem, ""]
    if q.options and set(q.options.values()) != {"A", "B", "C", "D"}:
        for k in "ABCD":
            if k in q.options:
                out.append(f"- **{k}.** {q.options[k] or '（见截图）'}")
        out.append("")
    out += [
        "> [!check]- 答案",
        f"> 正确答案：**{q.correct or '?'}**　我的答案：**{q.mine or '—'}**　{st}",
        "",
        "> [!note] 复盘",
        ">",  # 留空，供其它 skill 写入解析
        "",
        "---",
        "",
    ]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--out", help="输出目录（默认 ../板块复盘/第N季）")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的板块文件（会丢失其中的复盘笔记！）")
    ap.add_argument("--snap-all", action="store_true", help="每道题都附截图")
    args = ap.parse_args()

    pdf = Path(args.pdf).resolve()
    if not pdf.exists():
        sys.exit(f"找不到文件：{pdf}")
    ms = re.search(r"第([一二三四五六七八九十百零\d]+)季", pdf.stem)
    season = f"第{cn2int(ms.group(1))}季" if ms else pdf.stem
    sid = f"S{cn2int(ms.group(1))}" if ms else "SX"
    out = Path(args.out) if args.out else pdf.parent.parent / "板块复盘" / season
    att = out / "attachments"
    att.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf))
    lines = extract_lines(doc)
    left = sorted(l.x0 for l in lines)[len(lines) // 2] if lines else 43  # 正文左边界（中位数）
    questions, materials = parse(lines, left)
    if not questions:
        sys.exit("没有解析到任何题目，请检查 PDF 是否为粉笔导出的文字版试卷。")

    by_num = {q.num: q for q in questions}
    # 题目截图 & 分类
    for i, q in enumerate(questions):
        q.options = split_options(q.opt_lines)
        stem = join_stem(q.stem_lines, left)
        q.board = classify(q, stem)
        if q.section != "言语理解与表达":
            stem = stem.replace("____", "")
        q._stem = stem
        if q.ans_line:
            segs = region_segments(doc, q.start, q.ans_line.page, q.ans_line.y0)
        else:
            nxt = questions[i + 1].start if i + 1 < len(questions) else None
            segs = region_segments(doc, q.start, nxt.page, nxt.y0) if nxt else []
        if args.snap_all or q.board in ALWAYS_SNAP or has_images(doc, segs):
            q.images = snap(doc, segs, att, f"{sid}-Q{q.num:03d}")
    # 材料截图（资料分析一律截；一拖五有图才截）
    for m in materials:
        if not m.lines or not m.qnums:
            continue
        segs = region_segments(doc, m.lines[0], m.end.page, m.end.y0)
        m.text = join_stem([(l.text, l.x0) for l in m.lines if l.text != IMG], left)
        m.images = []
        if by_num[m.qnums[0]].section == "资料分析" or has_images(doc, segs) or args.snap_all:
            m.images = snap(doc, segs, att, f"{sid}-M{m.qnums[0]:03d}-{m.qnums[-1]:03d}")

    # 分组写文件
    groups = {}
    for q in questions:
        groups.setdefault(q.board, []).append(q)
    written, skipped = [], []
    overview = []
    for idx, board in BOARDS:
        qs = groups.get(board)
        if not qs:
            continue
        fn = out / f"{idx}-{board}.md"
        right = sum(1 for q in qs if q.mine and q.mine == q.correct)
        done = sum(1 for q in qs if q.mine)
        rate = f"{right / done:.0%}" if done else "—"
        overview.append((idx, board, len(qs), done, right, rate))
        if fn.exists() and not args.force:
            skipped.append(fn.name); continue
        body = [
            "---",
            f"来源: \"[[{pdf.stem}]]\"",
            f"季数: {season}",
            f"板块: {board}",
            f"题号: \"{qs[0].num}-{qs[-1].num}\"" if len(qs) > 1 else f"题号: \"{qs[0].num}\"",
            f"题数: {len(qs)}",
            f"作答: {done}",
            f"正确: {right}",
            f"正确率: \"{rate}\"",
            f"tags: [行测/模考复盘, 行测/{board}]",
            "---",
            "",
            f"# {season} · {board}",
            "",
            "| 题号 | 正确答案 | 我的答案 | 结果 |",
            "| :-: | :-: | :-: | :-: |",
        ]
        for q in qs:
            icon, st = status(q)
            body.append(f"| [[#{q.num}. {icon}\\|{q.num}]] | {q.correct} | {q.mine or '—'} | {icon} {st} |")
        body.append("")
        shown_mat = set()
        for q in qs:
            m = q.material
            if m is not None and id(m) not in shown_mat and getattr(m, "text", None) is not None:
                shown_mat.add(id(m))
                body += [f"## 材料（第{m.qnums[0]}-{m.qnums[-1]}题）", ""]
                body += [f"![[{n}]]" for n in m.images]
                if m.text:
                    body += ["", "> [!abstract]- 材料文字（自动提取，图表以截图为准）"]
                    body += ["> " + ln if ln else ">" for ln in m.text.split("\n")]
                body.append("")
            body += render_question(q, q._stem)
        write_lf(fn, "\n".join(body))
        written.append(fn.name)

    # 总览
    ov = out / f"00-{season}总览.md"
    if not ov.exists() or args.force:
        t = ["---", f"来源: \"[[{pdf.stem}]]\"", f"季数: {season}", "tags: [行测/模考复盘]", "---", "",
             f"# {season} 模考总览", "", "| 板块 | 题数 | 作答 | 正确 | 正确率 |", "| --- | :-: | :-: | :-: | :-: |"]
        for idx, b, n, d, r, rate in overview:
            t.append(f"| [[{idx}-{b}]] | {n} | {d} | {r} | {rate} |")
        write_lf(ov, "\n".join(t) + "\n")
        written.append(ov.name)

    # 控制台报告（供 agent 核对分类）
    print(f"输出目录：{out}")
    print(f"共解析 {len(questions)} 题（期望连续编号 1-{questions[-1].num}）")
    for idx, b, n, d, r, rate in overview:
        nums = [q.num for q in groups[b]]
        print(f"  {idx}-{b}: {n} 题 -> {compress(nums)}   正确率 {rate}")
    missing = [q.num for q in questions if not q.correct]
    if missing:
        print(f"⚠ 以下题目没解析到正确答案：{missing}")
    if skipped:
        print(f"⚠ 已存在未覆盖（加 --force 覆盖）：{skipped}")
    print("已写入：", written)


def compress(nums):
    out, s = [], nums[0]
    for a, b in zip(nums, nums[1:] + [None]):
        if b != a + 1:
            out.append(f"{s}" if s == a else f"{s}-{a}")
            s = b
    return ",".join(out)


if __name__ == "__main__":
    main()
