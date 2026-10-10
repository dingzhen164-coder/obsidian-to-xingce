#!/usr/bin/env python3
"""扫描版（带 OCR 文字层）法考教材 PDF → 知识点卡片，全程用代码，不花模型 token。

适用的 PDF：每页是一张扫描图，上面叠着不可见的 OCR 文字层（用 PyMuPDF 能读到文字和每个字的位置）。
这类书的“考点”（知识点）以「考点N：标题」开头，里面有表格、「一、二、三、」小节、[法理与逻辑]/[懂原理]
等小标签框、脚注 ①②③、随堂练习。

做的事：
  1. 按「考点N：」标题把整本书（或一个片段）切成一个个考点——页与页之间的内容按阅读顺序接起来，
     标题之前（上一个考点的尾巴）和下一个考点标题之后的内容都不要。
  2. 表格：用 OpenCV 找出表格线，重建网格和合并单元格（跨行、跨列），再把 OCR 文字按位置放进格子。
     跨页的“续表”自动并回上一张表。重建不出来的表（没有表格线、结构不规则）退回成“裁出来的图片”。
  3. 清洗：去页眉页脚、页码、水印（--drop 指定）、OCR 常见错字（--fixes 指定，默认见 DEFAULT_FIXES）。
  4. 结构：小节标题、小标签框、脚注、随堂练习（题干 + 选项 + 脚注里的答案）。
  5. 输出：每个考点一行 JSONL（可直接交给 build_tsv.py），表格放在 tables.json，
     无法重建的表格 / 图示放在 media/，以及一份 report.md，列出所有需要人看一眼的地方。

用法：
    python3 pdf_to_cards.py <书.pdf> --out <输出目录> [--subject 民法] [--only 4] [--drop 水印1,水印2]
                            [--fixes 错字对照.tsv]

依赖：pymupdf、opencv-python-headless、numpy（都是 pip 包）。
"""
import argparse
import html
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import pymupdf

# ---------------------------------------------------------------- 配置
DEFAULT_DROP = [r"法考小米", r"考小米", r"方圆众合教育", r"FANGYUAN\s*ZHONGHE\s*EDUCATION", r"添加百度网?盘?好?友?", r"网盘好友"]  # 水印/广告词（正则）
HEADER_PATTERNS = [r"^\S{1,6}\s*[|｜]?\s*授课精要$", r"^续表$"]  # 页眉（OCR 常把竖线丢掉）；续表单独处理
DEFAULT_FIXES = [  # (正则, 替换) —— 只放“几乎不可能是对的”的 OCR 错字；数字、法条号绝不自动改
    ("自\u5df2", "自\u5df1"),  # 自已 → 自己（OCR 把“己”认成“已”）
    (r"收人", "收入"),
    (r"自前的", "目前的"),
    (r"(?<=\d)一(?=\d)", "—"),  # 18一22 → 18—22（条文号范围里的“一”是 OCR 把长横线认错了）
]
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
UNIT_START = re.compile(r"^(周岁|岁以上|岁以下|个月|日内|日起|万元|％|%)")
KAODIAN = re.compile(r"^\s*考点\s*(\d+)\s*[：:]\s*(.+?)\s*$")
SECTION = re.compile(r"^\s*([一二三四五六七八九十]+)、\s*(.+?)\s*$")
BOX_LABEL = re.compile(r"^\s*[\[［【「]\s*([\u4e00-\u9fff]{2,6})\d*\s*[\]］】」]?\s*(.*)$")
OPTION = re.compile(r"(?<![A-Za-z0-9])([A-D])\s*[.．、]\s*(?=\S)")
CJK = re.compile(r"[　-〿一-鿿＀-￯“”‘’（）【】《》「」、，。；：？！…—①-⑩]")


# ---------------------------------------------------------------- 小工具
def join_lines(parts: list[str]) -> str:
    """把 OCR 折行的几行拼回一段：中文之间不加空格，英文/数字之间加一个。"""
    out = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if out and not (CJK.match(out[-1]) or CJK.match(p[0])):
            out += " "
        out += p
    return out


class Cleaner:
    def __init__(self, drop: list[str], fixes: list[tuple[str, str]]):
        self.drop = [re.compile(d) for d in drop if d]
        self.fixes = [(re.compile(a), b) for a, b in fixes]
        self.applied: dict[str, int] = defaultdict(int)

    def __call__(self, s: str) -> str:
        for d in self.drop:
            s = d.sub("", s)
        for rx, rep in self.fixes:
            s, n = rx.subn(rep, s)
            if n:
                self.applied[f"{rx.pattern} → {rep}"] += n
        return s


# ---------------------------------------------------------------- 页面读取
class Page:
    def __init__(self, doc: pymupdf.Document, index: int):
        self.doc = doc
        self.index = index  # 从 0 开始
        self.p = doc[index]
        self.w, self.h = self.p.rect.width, self.p.rect.height
        self.img = self._scan_image()
        self.scale = (self.img.shape[1] / self.w) if self.img is not None else 1.0
        self.chars = self._chars()
        self.lines = self._lines()

    def _scan_image(self):
        """页面大小的那张扫描图（排除水印用的方图）。没有图时返回 None（文字版 PDF 用渲染图代替）。"""
        pa = self.w / self.h
        cands = []
        for im in self.p.get_images(full=True):
            try:
                info = self.doc.extract_image(im[0])
            except Exception:
                continue
            cands.append((abs(info["width"] / info["height"] - pa), -info["width"] * info["height"], info))
        if cands:
            cands.sort(key=lambda c: (round(c[0], 2), c[1]))
            if cands[0][0] < 0.05:
                arr = np.frombuffer(cands[0][2]["image"], np.uint8)
                return cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        pm = self.p.get_pixmap(dpi=200, colorspace=pymupdf.csGRAY)
        return np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width)

    def _chars(self):
        """每个字：(字, x0, y0, x1, y1, 行号)。行号 = 区块.行，用来把同一行的字拼回去。"""
        out = []
        raw = self.p.get_text("rawdict")
        for bi, b in enumerate(raw["blocks"]):
            for li, ln in enumerate(b.get("lines", [])):
                for sp in ln["spans"]:
                    for ch in sp["chars"]:
                        if ch["c"].strip():
                            x0, y0, x1, y1 = ch["bbox"]
                            out.append((ch["c"], x0, y0, x1, y1, bi * 1000 + li))
        return out

    def apply_drops(self, patterns):
        """把水印字从 OCR 字里直接拿掉（水印常常夹在正文行里，按字删才不会连带删掉正文）。"""
        by_line = defaultdict(list)
        for c in self.chars:
            by_line[c[5]].append(c)
        keep = []
        for lid, cs in by_line.items():
            cs.sort(key=lambda c: c[1])
            text = "".join(c[0] for c in cs)
            dead = set()
            for rx in patterns:
                for m in rx.finditer(text):
                    dead.update(range(m.start(), m.end()))
            keep += [c for i, c in enumerate(cs) if i not in dead]
        self.chars = keep
        self.lines = self._lines()

    def _lines(self):
        """OCR 行：{'text','x0','y0','x1','y1','id'}，按从上到下排序。"""
        g = defaultdict(list)
        for c in self.chars:
            g[c[5]].append(c)
        lines = []
        for lid, cs in g.items():
            cs.sort(key=lambda c: c[1])
            lines.append({
                "text": "".join(c[0] for c in cs),
                "x0": min(c[1] for c in cs), "y0": min(c[2] for c in cs),
                "x1": max(c[3] for c in cs), "y1": max(c[4] for c in cs), "id": lid,
            })
        lines.sort(key=lambda l: (round(l["y0"] / 3), l["x0"]))
        return lines


# ---------------------------------------------------------------- 表格
class Table:
    def __init__(self, bbox_px, xs, ys, cells, page_index):
        self.bbox_px = bbox_px  # x0,y0,x1,y1（图像像素）
        self.xs, self.ys = xs, ys
        self.cells = cells  # [{'r0','c0','r1','c1','text'}]  r1/c1 为不含的结束下标
        self.page_index = page_index
        self.ok = True
        self.note = ""

    def caption(self) -> str:
        for c in self.cells:
            if c["r0"] == 0 and c["c0"] == 0 and c["c1"] == len(self.xs) - 1:
                return c["text"]
        return ""

    def to_html(self) -> str:
        nrow, ncol = len(self.ys) - 1, len(self.xs) - 1
        by_pos = {(c["r0"], c["c0"]): c for c in self.cells}
        rows = []
        for r in range(nrow):
            tds = []
            for col in range(ncol):
                c = by_pos.get((r, col))
                if not c:
                    continue
                tag = "th" if r <= self.header_rows - 1 else "td"
                rs, cs = c["r1"] - c["r0"], c["c1"] - c["c0"]
                attrs = (f" rowspan='{rs}'" if rs > 1 else "") + (f" colspan='{cs}'" if cs > 1 else "")
                body = "<br>".join(html.escape(t, quote=False) for t in c["text"].split("\n"))
                tds.append(f"<{tag}{attrs} style='border:1px solid #999;padding:3px 7px;text-align:left;vertical-align:top'>{body}</{tag}>")
            rows.append("<tr>" + "".join(tds) + "</tr>")
        return "<table style='border-collapse:collapse;margin:6px 0;font-size:0.92em'>" + "".join(rows) + "</table>"

    header_rows = 2  # 题注行 + 表头行；detect 时会按内容调整

    def to_markdown(self) -> str:
        """Markdown 表格。合并单元格：内容写在左上角那一格，被盖住的格子写“〃”（被上面盖住）或“⇢”（被左边盖住）。"""
        nrow, ncol = len(self.ys) - 1, len(self.xs) - 1
        grid = [["" for _ in range(ncol)] for _ in range(nrow)]
        for c in self.cells:
            for r in range(c["r0"], c["r1"]):
                for k in range(c["c0"], c["c1"]):
                    if r == c["r0"] and k == c["c0"]:
                        grid[r][k] = c["text"].replace("\n", " ")
                    else:  # 〃＝被上面的格子盖住（同上）；⇢＝被左边的格子盖住（跨列）
                        grid[r][k] = "〃" if r > c["r0"] else "⇢"
        lines = []
        start = 0
        if nrow and all(x == "⇢" for x in grid[0][1:]):  # 第一行整行合并：题注
            lines.append(f"**{grid[0][0]}**")
            lines.append("")
            start = 1
        if start < nrow:
            lines.append("| " + " | ".join(grid[start]) + " |")
            lines.append("|" + "|".join(["---"] * ncol) + "|")
            for r in range(start + 1, nrow):
                lines.append("| " + " | ".join(grid[r]) + " |")
        return "\n".join(lines)


def _cluster(vals, tol):
    vals = sorted(vals)
    out = []
    for v in vals:
        if out and v - out[-1][-1] <= tol:
            out[-1].append(v)
        else:
            out.append([v])
    return [int(round(sum(g) / len(g))) for g in out]


def detect_tables(page: Page, clean: Cleaner) -> list[Table]:
    gray = page.img
    H, W = gray.shape
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 15)
    hor = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, W // 40), 1)))
    ver = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, H // 60))))

    def segments(mask, horiz):
        n, _, st, _ = cv2.connectedComponentsWithStats(mask)
        out = []
        for i in range(1, n):
            x, y, w, h, _a = st[i]
            if horiz and w >= W * 0.04 and h <= 8:
                out.append([int(x), int(y + h // 2), int(x + w)])  # x0, y, x1
            if not horiz and h >= H * 0.012 and w <= 8:
                out.append([int(x + w // 2), int(y), int(y + h)])  # x, y0, y1
        return out

    hs, vs = segments(hor, True), segments(ver, False)
    tol = 10
    # 把相接的横线/竖线并成一组
    parent = list(range(len(hs) + len(vs)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, h in enumerate(hs):
        for j, v in enumerate(vs):
            if h[0] - tol <= v[0] <= h[2] + tol and v[1] - tol <= h[1] <= v[2] + tol:
                parent[find(i)] = find(len(hs) + j)
    groups = defaultdict(lambda: ([], []))
    for i, h in enumerate(hs):
        groups[find(i)][0].append(h)
    for j, v in enumerate(vs):
        groups[find(len(hs) + j)][1].append(v)

    tables = []
    for gh, gv in groups.values():
        if len(gh) < 3 or len(gv) < 2:
            continue
        x0 = min(min(h[0] for h in gh), min(v[0] for v in gv))
        x1 = max(max(h[2] for h in gh), max(v[0] for v in gv))
        y0 = min(min(h[1] for h in gh), min(v[1] for v in gv))
        y1 = max(max(h[1] for h in gh), max(v[2] for v in gv))
        if (x1 - x0) < W * 0.5:  # 太窄：多半是示意图里的线
            continue
        # 表格最上面/最下面的粗线常常不碰竖线（题注行在它下面）：把附近又宽又长的横线也算进来
        tw = x1 - x0
        extra = [h for h in hs if h not in gh and h[2] - h[0] >= 0.8 * tw and y0 - 160 <= h[1] <= y1 + 60
                 and h[0] >= x0 - 30 and h[2] <= x1 + 30]
        gh = gh + extra
        y0 = min(y0, *[h[1] for h in extra]) if extra else y0
        y1 = max(y1, *[h[1] for h in extra]) if extra else y1
        xs = _cluster([x0, x1] + [v[0] for v in gv], 14)
        ys = _cluster([h[1] for h in gh] + [y0, y1], 10)
        # 去掉离得太近的重复线（文字下划线的残片等）
        ys = [y for k, y in enumerate(ys) if k == 0 or y - ys[k - 1] > 14]
        if len(xs) < 3 or len(ys) < 3:
            continue
        nrow, ncol = len(ys) - 1, len(xs) - 1

        def h_covered(row_boundary, col):  # 第 row_boundary 条横线在第 col 列上是不是有线
            y = ys[row_boundary]
            lo, hi = xs[col], xs[col + 1]
            tot = 0
            for h in gh:
                if abs(h[1] - y) <= 12:
                    tot += max(0, min(hi, h[2]) - max(lo, h[0]))
            return tot >= 0.6 * (hi - lo)

        def v_covered(col_boundary, row):
            x = xs[col_boundary]
            lo, hi = ys[row], ys[row + 1]
            tot = 0
            for v in gv:
                if abs(v[0] - x) <= 14:
                    tot += max(0, min(hi, v[2]) - max(lo, v[1]))
            return tot >= 0.6 * (hi - lo)

        uf = list(range(nrow * ncol))

        def f(a):
            while uf[a] != a:
                uf[a] = uf[uf[a]]
                a = uf[a]
            return a

        for r in range(nrow):
            for c in range(ncol):
                if r + 1 < nrow and not h_covered(r + 1, c):
                    uf[f(r * ncol + c)] = f((r + 1) * ncol + c)
                if c + 1 < ncol and not v_covered(c + 1, r):
                    uf[f(r * ncol + c)] = f(r * ncol + c + 1)
        comps = defaultdict(list)
        for r in range(nrow):
            for c in range(ncol):
                comps[f(r * ncol + c)].append((r, c))
        cells, rect_ok = [], True
        for members in comps.values():
            rs = [m[0] for m in members]
            cs = [m[1] for m in members]
            r0, r1, c0, c1 = min(rs), max(rs) + 1, min(cs), max(cs) + 1
            if (r1 - r0) * (c1 - c0) != len(members):
                rect_ok = False
            cells.append({"r0": r0, "r1": r1, "c0": c0, "c1": c1})
        tb = Table((xs[0], ys[0], xs[-1], ys[-1]), xs, ys, cells, page.index)
        # 把 OCR 字放进格子
        sc = page.scale
        buckets = defaultdict(list)
        for ch, a, b, c_, d, lid in page.chars:
            cx, cy = (a + c_) / 2 * sc, (b + d) / 2 * sc
            if not (xs[0] - 4 <= cx <= xs[-1] + 4 and ys[0] - 4 <= cy <= ys[-1] + 4):
                continue
            for ci, cell in enumerate(cells):
                if xs[cell["c0"]] - 4 <= cx <= xs[cell["c1"]] + 4 and ys[cell["r0"]] - 4 <= cy <= ys[cell["r1"]] + 4:
                    buckets[ci].append((cy, cx, ch, lid))
                    break
        for ci, cell in enumerate(cells):
            by_line = defaultdict(list)
            for cy, cx, ch, lid in buckets[ci]:
                by_line[lid].append((cy, cx, ch))
            rows = []
            for lid, cs in sorted(by_line.items(), key=lambda kv: sum(c[0] for c in kv[1]) / len(kv[1])):
                rows.append([c[2] for c in sorted(cs, key=lambda c: c[1])])
            texts = ["".join(r) for r in rows]
            # 折行拼回；以 1. 2. （1）① 开头的另起一行
            merged: list[str] = []
            for t in texts:
                t = clean(t)
                if not t:
                    continue
                if merged and not re.match(r"^(\d+[.、．]|[（(]\d+[）)]|[①-⑩])", t):
                    merged[-1] = join_lines([merged[-1], t])
                else:
                    merged.append(t)
            cell["text"] = "\n".join(clean(m) for m in merged)
        tb.ok = rect_ok
        if not rect_ok:
            tb.note = "合并单元格不是规则矩形，表格结构可能不对"
        tb.cells.sort(key=lambda c: (c["r0"], c["c0"]))
        # 表头行数：题注行（整行合并）+ 紧接着的一行
        tb.header_rows = 0
        if tb.caption():
            tb.header_rows = 2
        else:
            tb.header_rows = 1
        tables.append(tb)
    tables.sort(key=lambda t: t.bbox_px[1])
    return tables


def detect_figures(page: Page, tables: list[Table]):
    """示意图 / 思维导图：由很多较长的竖线（树形图的连接线）聚成一片的区域（表格之外）。返回图像像素坐标的框。

    - 竖线要够长（≥ 页高/34，汉字笔画和文字下划线都达不到），一片里至少 3 条；
    - 框的上下沿 = 这些竖线的上下沿；左右 = 与这个高度范围重叠的文字行的整行宽度
      （树形图两端的文字标签常常伸得很远，裁窄了会丢字）。
    """
    gray = page.img
    H, W = gray.shape
    sc = page.scale
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 15)
    ver = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(40, H // 34))))
    for t in tables:
        x0, y0, x1, y1 = t.bbox_px
        ver[max(0, y0 - 40): y1 + 40, max(0, x0 - 10): x1 + 10] = 0
    clustered = cv2.dilate(ver, cv2.getStructuringElement(cv2.MORPH_RECT, (110, 60)))
    n, lab, st, _ = cv2.connectedComponentsWithStats(clustered)
    vn, vlab, vst, _ = cv2.connectedComponentsWithStats(ver)
    boxes = []
    for i in range(1, n):
        x, y, w, h, _a = st[i]
        segs = [vst[j] for j in range(1, vn) if x <= vst[j][0] <= x + w and y <= vst[j][1] <= y + h]
        if len(segs) < 3:
            continue
        top = min(sg[1] for sg in segs) - 15
        bot = max(sg[1] + sg[3] for sg in segs) + 15
        left = min(sg[0] for sg in segs) - 20
        right = max(sg[0] + sg[2] for sg in segs) + 20
        for ln in page.lines:  # 与这个高度重叠的文字行：整行都算进图里
            cy = (ln["y0"] + ln["y1"]) / 2 * sc
            if top <= cy <= bot and len(ln["text"]) <= 40 and not KAODIAN.match(ln["text"]):
                left = min(left, int(ln["x0"] * sc) - 10)
                right = max(right, int(ln["x1"] * sc) + 10)
        boxes.append((max(0, left), max(0, top), min(W, right), min(H, bot)))
    return boxes


def merge_continued(tables: list[Table]) -> list[Table]:
    """“续表”：题注相同的表，是上一张表在下一页的延续。把它的数据行并回上一张（只在列数能对上时）。"""
    out: list[Table] = []
    for t in tables:
        prev = out[-1] if out else None
        norm = lambda x: re.sub(r"[\s\[\]［］【】「」]", "", x)
        if prev and prev.caption() and norm(prev.caption()) == norm(t.caption()) and t.page_index == prev.page_index + 1:
            # 续表的列边界按比例映射到上一张表的列
            def frac(tb):
                w = tb.xs[-1] - tb.xs[0]
                return [(x - tb.xs[0]) / w for x in tb.xs]

            pf, tf = frac(prev), frac(t)

            def nearest(f):
                return min(range(len(pf)), key=lambda i: abs(pf[i] - f))

            base = len(prev.ys) - 1
            hdr = t.header_rows
            skipped = 0
            new_cells = []
            for c in t.cells:
                if c["r0"] < hdr:
                    skipped += 1
                    continue
                new_cells.append({"r0": base + c["r0"] - hdr, "r1": base + c["r1"] - hdr,
                                  "c0": nearest(tf[c["c0"]]), "c1": nearest(tf[c["c1"]]), "text": c["text"]})
            prev.cells += new_cells
            prev.ys = prev.ys + [prev.ys[-1] + (y - t.ys[hdr]) for y in t.ys[hdr + 1:]]
            prev.note = (prev.note + " 已并入续表").strip()
        else:
            out.append(t)
    return out


# ---------------------------------------------------------------- 考点切分与结构
def build_cards(doc, args, clean: Cleaner):
    pages = [Page(doc, i) for i in range(len(doc))]
    for pg in pages:
        pg.apply_drops(clean.drop)
    all_tables: dict[int, list[Table]] = {}
    for pg in pages:
        all_tables[pg.index] = detect_tables(pg, clean)

    # 每一页的“元素”按阅读顺序：文字行 / 表格；表格里的字不再当文字行
    stream = []  # {'kind': 'line'|'table'|'figure', 'page', 'y', ...}
    for pg in pages:
        sc = pg.scale
        tabs = all_tables[pg.index]
        figs = detect_figures(pg, tabs)
        for fb in figs:
            stream.append({"kind": "figure", "page": pg.index, "y": fb[1] / sc, "box": fb, "pg": pg})
        for ln in pg.lines:
            cy = (ln["y0"] + ln["y1"]) / 2 * sc
            cx = (ln["x0"] + ln["x1"]) / 2 * sc
            if any(t.bbox_px[0] - 6 <= cx <= t.bbox_px[2] + 6 and t.bbox_px[1] - 6 <= cy <= t.bbox_px[3] + 6 for t in tabs):
                continue
            if any(fb[0] - 20 <= cx <= fb[2] + 20 and fb[1] - 10 <= cy <= fb[3] + 10 for fb in figs) \
                    and not KAODIAN.match(ln["text"]) and not SECTION.match(ln["text"]):
                continue
            stream.append({"kind": "line", "page": pg.index, "y": ln["y0"], "x0": ln["x0"], "x1": ln["x1"],
                           "text": ln["text"], "w": pg.w, "h": pg.h})
        for t in tabs:
            stream.append({"kind": "table", "page": pg.index, "y": t.bbox_px[1] / sc, "table": t})
    # 每页的左边距：行首 x 的 15% 分位；比它多缩进 8pt 以上的行视为新段落开头
    margins = {}
    for pg in pages:
        xs0 = sorted(l["x0"] for l in pg.lines if len(l["text"]) > 8)
        margins[pg.index] = xs0[int(len(xs0) * 0.15)] if xs0 else 0
    for e in stream:
        if e["kind"] == "line":
            e["indent"] = e["x0"] > margins[e["page"]] + 8
    stream.sort(key=lambda e: (e["page"], e["y"]))

    # 页眉页脚、页码、水印
    kept = []
    for e in stream:
        if e["kind"] == "line":
            txt = clean(e["text"]).strip()
            if not txt:
                continue
            if txt == "续表" or (e["y"] < e["h"] * 0.075 and any(re.match(p, txt) for p in HEADER_PATTERNS)):
                continue
            if e["y"] > e["h"] * 0.88 and re.fullmatch(r"\d{1,3}", txt):
                continue
            e["text"] = txt
        kept.append(e)

    # 切分考点
    segs = []  # [(no, title, [elements])]
    cur = None
    for e in kept:
        if e["kind"] == "line":
            m = KAODIAN.match(e["text"])
            if m:
                cur = (int(m.group(1)), m.group(2), [])
                segs.append(cur)
                continue
        if cur is not None:
            cur[2].append(e)

    cards, report = [], []
    for no, title, els in segs:
        if args.only and no not in args.only:
            continue
        card, notes = assemble(no, title, els, args, clean)
        cards.append(card)
        report.append((no, title, notes))
    return cards, report


def assemble(no, title, els, args, clean):
    notes: list[str] = []
    figures: dict[str, "np.ndarray"] = {}
    tables_html: dict[str, str] = {}
    tables_md: dict[str, str] = {}
    # 续表合并：先把同一考点里连续的表格合并
    tabs = [e["table"] for e in els if e["kind"] == "table"]
    merged = merge_continued(tabs)
    merged_ids = {id(t) for t in merged}
    tcount = 0

    # 脚注：每页底部以 ①②… 开头的行
    foot = {}  # (page, 序号) -> 文本
    body = []
    for e in els:
        if e["kind"] == "line" and e["y"] > e["h"] * 0.82 and e["text"][:1] in CIRCLED:
            foot[(e["page"], e["text"][0])] = re.sub(r"(?<=[。；）)])\s*\d{1,3}$", "", e["text"])
            e["foot"] = True
            if e["x1"] > e["w"] - 5:
                notes.append(f"第{e['page'] + 1}页脚注“{e['text'][:10]}…”的行尾贴着页面右边缘，行尾可能被截掉了字（常见：数字被截，如“16周岁”变成“周岁”）")
        body.append(e)
    # 脚注续行：紧跟脚注、同页、位置更靠下的非脚注行并进去
    last_foot_key = None
    for e in body:
        if e["kind"] != "line":
            continue
        if e.get("foot"):
            last_foot_key = (e["page"], e["text"][0])
        elif last_foot_key and e["page"] == last_foot_key[0] and e["y"] > e["h"] * 0.82:
            if UNIT_START.match(e["text"]):
                notes.append(f"第{e['page'] + 1}页脚注的续行以量词开头（“{e['text'][:10]}…”），前面的数字可能被扫描截掉了——请对照原书")
            foot[last_foot_key] += re.sub(r"(?<=[。；）)])\s*\d{1,3}$", "", e["text"])
            e["foot_cont"] = True

    md: list[str] = []  # 卡片 back 的标记文本
    para: list[str] = []
    in_exercise = False
    ex_lines: list[str] = []
    ex_foot_mark = None
    ex_page = None
    used_footnotes = set()

    def flush_para():
        nonlocal para
        if para:
            text = clean(join_lines(para))
            text = re.sub(r"^[（(](\d+)[）)]\s*", r"\1. ", text)  # （1）… → 1. …
            md.append(text)
            para = []

    def flush_exercise():
        nonlocal in_exercise, ex_lines, ex_foot_mark
        if not in_exercise:
            return
        text = clean(join_lines(ex_lines))
        ans = ""
        if ex_foot_mark:
            f = foot.get((ex_page, ex_foot_mark), "")
            ans = re.sub(r"^[①-⑩]\s*", "", f)
            used_footnotes.add((ex_page, ex_foot_mark))
        # 题干与选项拆开
        parts = OPTION.split(text)
        stem = parts[0].strip()
        stem = re.sub(r"[①-⑩]\s*$", "", stem).strip()
        opts = []
        for i in range(1, len(parts) - 1, 2):
            opts.append(f"{parts[i]}. {parts[i + 1].strip()}")
        label = "随堂练习"
        md.append("# " + label)
        md.append(stem)
        md.extend(opts)
        if ans:
            md.append("**" + re.sub(r"^答案\s*[：:]\s*", "答案：", ans).rstrip("。") + "**")
        else:
            notes.append("随堂练习没找到脚注里的答案")
        in_exercise, ex_lines, ex_foot_mark = False, [], None

    for e in body:
        if e["kind"] == "figure":
            flush_para()
            flush_exercise()
            fx0, fy0, fx1, fy1 = e["box"]
            im = e["pg"].img
            crop = im[max(0, fy0 - 8): fy1 + 4, max(0, fx0 - 12): fx1 + 12]
            name = f"考点{no}-图{len(figures) + 1}.png"
            figures[name] = crop
            md.append(f"[[img:{name}]]")
            notes.append(f"示意图 {name} 没法转成文字，已裁成图片放进卡片（需要把图片文件拷进 Anki 的 collection.media 或你的库）")
            continue
        if e["kind"] == "table":
            t = e["table"]
            if id(t) not in merged_ids:
                continue  # 已并入上一张表
            flush_para()
            flush_exercise()
            tcount += 1
            tid = f"t{no}-{tcount}"
            tables_html[tid] = t.to_html()
            tables_md[tid] = t.to_markdown()
            md.append(f"[[table:{tid}]]")
            if not t.ok:
                notes.append(f"表格 {tid}：{t.note}")
            continue
        if e.get("foot") or e.get("foot_cont"):
            continue
        txt = e["text"]
        if UNIT_START.match(txt):
            notes.append(f"第{e['page'] + 1}页有一行以量词开头（“{txt[:10]}…”），前面的数字可能被扫描截掉了（如“16周岁”只剩“周岁”）——法考里数字不能错，请对照原书")
        if e.get("x1", 0) > e["w"] - 5 and not re.search(r"[。；？！）”」】\]]$", txt) and not e.get("foot"):
            notes.append(f"第{e['page'] + 1}页有一行贴着页面右边缘、没有以句末标点结尾，可能被扫描截掉了字：“…{txt[-14:]}”")
        m_sec = SECTION.match(txt)
        m_box = BOX_LABEL.match(txt)
        if m_sec and len(txt) < 60:
            flush_para()
            flush_exercise()
            md.append("# " + m_sec.group(1) + "、" + re.sub(r"\s*(★[★\s]*)$", lambda m: " " + m.group(1).replace(" ", ""), m_sec.group(2)).strip())
            continue
        if m_box:
            label, rest = m_box.group(1), m_box.group(2)
            flush_para()
            flush_exercise()
            if label == "随堂练习":
                in_exercise = True
                ex_page = e["page"]
                ex_lines = [rest] if rest else []
                continue
            md.append("# " + label)
            if rest:
                para.append(rest)
            continue
        if in_exercise:
            ex_lines.append(txt)
            mk = re.search(r"([①-⑩])\s*$", txt)
            if mk and ex_foot_mark is None:
                ex_foot_mark = mk.group(1)
                ex_page = e["page"]
            continue
        # 新段落：行首有缩进，或这一行以 （1）/1. 开头；孤零零的 "(2)" 并入下一行
        starts_item = bool(re.match(r"^([（(]\d+[）)]|\d+[.、．])", txt))
        lone_num = bool(para) and bool(re.fullmatch(r"[（(]\d+[）)]", para[-1])) and len(para) == 1
        if para and not lone_num and (e.get("indent") or starts_item):
            flush_para()
        para.append(txt)
    flush_para()
    flush_exercise()

    # 没被用掉的脚注 → 注释
    notes_md = []
    for (pg, mark), text in sorted(foot.items()):
        if (pg, mark) in used_footnotes:
            continue
        if re.match(r"^[①-⑩]\s*答案", text):
            notes.append(f"脚注“{text[:12]}”是答案，但没找到对应题目（多半属于上一个考点），已丢弃")
            continue
        notes_md.append("- " + text)
    if notes_md:
        md.append("# 注释")
        md.extend(notes_md)

    back = "\n".join(md)
    card = {
        "front": f"【{args.subject}·考点{no}】{title}",
        "back": back,
        "tags": [args.subject, f"考点{no}"],
        "source": f"{args.subject} 考点{no}",
        "kind": "knowledge_point",
        "_figures": figures,
        "_tables_html": tables_html,
        "_tables_md": tables_md,
    }
    return card, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--subject", default="")
    ap.add_argument("--only", help="只处理这些考点号，逗号分隔，如 4,5")
    ap.add_argument("--drop", default="", help="要从文字里删掉的水印/广告词，逗号分隔（追加到默认列表）")
    ap.add_argument("--fixes", type=Path, help="OCR 错字对照表：每行 正则<TAB>替换，追加到默认列表")
    args = ap.parse_args()
    args.only = {int(x) for x in args.only.split(",")} if args.only else None

    fixes = list(DEFAULT_FIXES)
    if args.fixes:
        for ln in args.fixes.read_text("utf-8").splitlines():
            if "\t" in ln and not ln.startswith("#"):
                a, b = ln.split("\t", 1)
                fixes.append((a, b))
    clean = Cleaner(DEFAULT_DROP + [d.strip() for d in args.drop.split(",")], fixes)

    doc = pymupdf.open(str(args.pdf))
    cards, report = build_cards(doc, args, clean)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "cards").mkdir(exist_ok=True)
    tables = {}
    with (args.out / "cards" / "cards.jsonl").open("w", encoding="utf-8") as f:
        for c in cards:
            tables.update({k: {"html": v, "md": c["_tables_md"][k]} for k, v in c.pop("_tables_html").items()})
            c.pop("_tables_md")
            for name, img in c.pop("_figures").items():
                (args.out / "media").mkdir(exist_ok=True)
                cv2.imwrite(str(args.out / "media" / name), img)
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    (args.out / "tables.json").write_text(json.dumps(tables, ensure_ascii=False, indent=1), "utf-8")

    lines = [f"# 转换报告：{args.pdf.name}", "", f"共 {len(cards)} 个考点，{len(tables)} 张表格。", ""]
    for no, title, notes in report:
        lines.append(f"## 考点{no} {title}")
        lines += [f"- ⚠ {n}" for n in notes] or ["- 没有需要人工看的地方"]
    if clean.applied:
        lines += ["", "## 自动改过的 OCR 错字", *[f"- {k}（{v} 处）" for k, v in clean.applied.items()]]
    (args.out / "report.md").write_text("\n".join(lines), "utf-8")
    print(f"考点 {len(cards)} 个，表格 {len(tables)} 张 → {args.out}")
    for no, title, notes in report:
        print(f"  考点{no} {title}：{'⚠ ' + '；'.join(notes) if notes else 'OK'}")


if __name__ == "__main__":
    main()
