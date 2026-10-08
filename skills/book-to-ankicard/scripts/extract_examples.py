#!/usr/bin/env python3
"""从 extract.py 生成的 full_text.txt 里，把“例题块”一次性抽成结构化 JSON。

为什么要单独抽：卡片里的例题要给**完整题干 + 选项 + 答案 + 书里的“方法论提示”**。
这些内容必须和书一字不差，所以由程序从原文抽取，卡片里只写例题编号，由 build_tsv.py 排进卡片，
不让模型手抄（手抄会漏字、会“优化”）。

用法：
    python3 extract_examples.py <书.pdf 或 full_text.txt> --out examples.json
                                [--marker 正则] [--end-marker 正则]

**优先传 PDF 原文件**：脚本会读 PDF 的版面（解析框、方法论提示框的位置），
“方法论提示”到哪里结束是按框精确切的。只给 full_text.txt 时退回纯文本启发式，
提示块的结尾可能多带几行后续正文，需要人工抽查。

默认识别的例题块（行讲义常见格式）：
    【例12】（2024浙江）      【拓展】（2022湖北选调）      【例题】（2024联考）
块内按下面的小标题切分（都是单独一行）：
    解析 / 答案：X / 方法论提示
块在遇到下一个例题标记、章节标题（“一、”“（五）”“第二讲”）、“提示”、“小结”时结束。

输出 examples.json：列表，每项
    {"id":"L400","line":400,"label":"例1","source":"2025山东","stem":"…","options":["A. …"],
     "answer":"D","analysis":"…","hint":"…"}
id：读 PDF 时是“页码-编号”（如 p8-例1），读文本时是“L行号”；写卡片时用 "examples": ["p8-例1","p9-例2"] 引用。

换格式的书：用 --marker 指定例题起始行的正则，需含两个分组：(label)(source)。
"""
import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_MARKER = r"^\s*【(例\s?\d+|拓展|例题|回顾)】\s*[（(]?([^）)]*)[）)]?.*$"
DEFAULT_END = (
    r"^\s*([一二三四五六七八九十]+、|（[一二三四五六七八九十]+）|第[一二三四五六七八九十\d]+[章讲节]|"
    r"本讲|引言小结|结语|提示\s*$|小结\s*$|考试权重|【)"
)
CJK = re.compile(r"[　-〿一-鿿＀-￯“”‘’（）【】《》「」、，。；：？！…—]")
OPT_START = re.compile(r"^\s*[A-D][.．、]\s*\S")
OPT_SPLIT = re.compile(r"\s+(?=[B-D][.．、]\s*\S)")
BULLET = re.compile(r"^\s*([①②③④⑤⑥⑦⑧⑨⑩]|[（(]\d+[）)]|\d+\)|\d+[.、．](?=\S))")


def join_wrapped(lines: list[str]) -> str:
    """把 PDF 折行的几行拼回一段：中文之间不加空格，英文/数字之间加一个。"""
    out = ""
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if out and not (CJK.match(out[-1]) or CJK.match(ln[0])):
            out += " "
        out += ln
    return out


def join_paragraphs(lines: list[str]) -> list[str]:
    """折行拼段；以 ①② / （1） 开头的行单独成段。"""
    paras: list[list[str]] = []
    for ln in lines:
        if not ln.strip():
            continue
        if BULLET.match(ln) or not paras:
            paras.append([ln])
        else:
            paras[-1].append(ln)
    return [join_wrapped(p) for p in paras]


def parse_block(lines: list[str]) -> dict:
    stem_l: list[str] = []
    ana_l: list[str] = []
    hint_l: list[str] = []
    answer = ""
    mode = "stem"
    for ln in lines:
        s = ln.strip()
        if not s or re.fullmatch(r"\d{1,3}", s):  # 空行、页码
            continue
        if mode in ("stem", "ana") and s == "解析":
            mode = "ana"
            continue
        m = re.match(r"^答案[：:]\s*([A-D]+|[^\s]+)", s)
        if m and mode in ("stem", "ana"):
            answer = m.group(1)
            mode = "after"
            continue
        if s == "方法论提示" or s.startswith("方法论提示"):
            mode = "hint"
            rest = s[len("方法论提示"):].strip("：: ")
            if rest:
                hint_l.append(rest)
            continue
        {"stem": stem_l, "ana": ana_l, "hint": hint_l, "after": hint_l}[mode].append(s)

    # 题干：选项从第一个 A. 开始
    opt_i = next((i for i, s in enumerate(stem_l) if OPT_START.match(s)), None)
    stem_lines = stem_l if opt_i is None else stem_l[:opt_i]
    opt_lines = [] if opt_i is None else stem_l[opt_i:]

    options: list[str] = []
    cur = ""
    for s in opt_lines:
        if OPT_START.match(s):
            if cur:
                options.append(cur)
            cur = s
        else:
            cur = join_wrapped([cur, s])
    if cur:
        options.append(cur)
    flat: list[str] = []
    for o in options:
        flat += [x.strip() for x in OPT_SPLIT.split(o) if x.strip()]
    options = [re.sub(r"^([A-D])[．、]\s*", r"\1. ", re.sub(r"^([A-D])\.\s*", r"\1. ", o)) for o in flat]

    return {
        "stem": "\n".join(join_paragraphs(stem_lines)),
        "options": options,
        "answer": answer,
        "analysis": "\n".join(join_paragraphs(ana_l)),
        "hint": "\n".join(join_paragraphs(hint_l)),
    }


# ---------------------------------------------------------------- PDF 版面
def pdf_lines(path: Path) -> list[dict]:
    """逐行读出 PDF：文字、所在页、纵坐标，以及这一行落在哪种“框”里（解析 / 方法论提示 / 提示 / 无）。

    讲义用彩色左边条 + 浅色底做出各种框；框的类别由框内第一行文字决定。
    """
    try:
        import pymupdf  # type: ignore
    except ImportError:
        import fitz as pymupdf  # type: ignore

    out: list[dict] = []
    with pymupdf.open(str(path)) as doc:
        for pn, page in enumerate(doc, 1):
            lines = []
            for b in page.get_text("dict")["blocks"]:
                for ln in b.get("lines", []):
                    txt = "".join(sp["text"] for sp in ln["spans"]).strip()
                    if txt:
                        x0, y0, x1, y1 = ln["bbox"]
                        lines.append({"text": txt, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "page": pn})
            lines.sort(key=lambda r: (round(r["y0"] / 3), r["x0"]))
            lines = [r for r in lines if not (r["y0"] > 800 and re.fullmatch(r"\d{1,3}", r["text"]))]

            # 找框：窄的竖条（左边条）+ 同高同左边的宽矩形（底色）
            rects = [d["rect"] for d in page.get_drawings() if d.get("rect") is not None]
            bars = [r for r in rects if r.width <= 4.5 and r.height >= 12]
            boxes = []
            for bar in bars:
                for r in rects:
                    if r.width > 60 and abs(r.y0 - bar.y0) < 1.5 and abs(r.y1 - bar.y1) < 1.5 and abs(r.x0 - bar.x0) < 1.5:
                        boxes.append((r.x0, r.y0, r.x1, r.y1))
                        break
            kinds = []
            for (x0, y0, x1, y1) in boxes:
                inside = [r for r in lines if x0 - 2 <= r["x0"] and r["x1"] <= x1 + 2 and y0 - 2 <= r["y0"] and r["y1"] <= y1 + 2]
                first = inside[0]["text"] if inside else ""
                kind = first if first in ("解析", "方法论提示", "提示") else None
                kinds.append(((x1 - x0) * (y1 - y0), (x0, y0, x1, y1), kind))
            kinds.sort(key=lambda k: k[0])  # 小框优先
            for r in lines:
                r["kind"] = None
                for _, (x0, y0, x1, y1), kind in kinds:
                    if x0 - 2 <= r["x0"] and r["x1"] <= x1 + 2 and y0 - 2 <= r["y0"] and r["y1"] <= y1 + 2:
                        r["kind"] = kind
                        break
            out += lines
    return out


def parse_pdf(path: Path, marker: "re.Pattern", endm: "re.Pattern") -> list[dict]:
    lines = pdf_lines(path)
    starts = [(i, marker.match(r["text"])) for i, r in enumerate(lines)]
    starts = [(i, m) for i, m in starts if m]
    out = []
    for k, (i, m) in enumerate(starts):
        limit = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        j = i + 1
        seen_answer = False
        while j < limit:
            r = lines[j]
            if r["text"].startswith("答案"):
                seen_answer = True
            elif seen_answer and r["kind"] not in ("解析", "方法论提示"):
                break  # 答案之后，离开解析框 / 提示框就结束
            j += 1
        blk = parse_block([r["text"] for r in lines[i + 1 : j]])
        label = re.sub(r"\s+", "", m.group(1))
        base = f"p{lines[i]['page']}-{label}"
        n = sum(1 for e in out if e["id"] == base or e["id"].startswith(base + "#"))
        blk.update({"id": base if n == 0 else f"{base}#{n + 1}", "line": lines[i]["page"], "label": label, "source": m.group(2).strip()})
        out.append(blk)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("text", type=Path, help="书的 PDF，或 extract.py 生成的 full_text.txt")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--marker", default=DEFAULT_MARKER)
    ap.add_argument("--end-marker", default=DEFAULT_END)
    a = ap.parse_args()

    marker = re.compile(a.marker)
    endm = re.compile(a.end_marker)

    if a.text.suffix.lower() == ".pdf":
        out = parse_pdf(a.text, marker, endm)
        if not out:
            sys.exit("没找到例题标记。书的格式不同时，用 --marker 指定例题起始行的正则（含 label、source 两个分组）。")
    else:
        lines = a.text.read_text("utf-8").splitlines()
        starts = [(i, marker.match(ln)) for i, ln in enumerate(lines)]
        starts = [(i, m) for i, m in starts if m]
        if not starts:
            sys.exit("没找到例题标记。书的格式不同时，用 --marker 指定例题起始行的正则（含 label、source 两个分组）。")
        out = []
        for k, (i, m) in enumerate(starts):
            limit = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
            j = i + 1
            seen_answer = False
            while j < limit:
                s_ = lines[j].strip()
                if s_.startswith("答案"):
                    seen_answer = True
                # 答案之前不会遇到章节标题；答案之后遇到标题/提示就结束
                if seen_answer and endm.match(lines[j]) and not s_.startswith("方法论提示"):
                    break
                j += 1
            blk = parse_block(lines[i + 1 : j])
            label = re.sub(r"\s+", "", m.group(1))
            blk.update({"id": f"L{i + 1}", "line": i + 1, "label": label, "source": m.group(2).strip()})
            out.append(blk)

    a.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    no_ans = sum(1 for e in out if not e["answer"])
    no_opt = sum(1 for e in out if len(e["options"]) < 4)
    no_hint = sum(1 for e in out if not e["hint"])
    print(f"抽到例题 {len(out)} 道 → {a.out}")
    print(f"  缺答案 {no_ans}，选项不足4个 {no_opt}，无“方法论提示” {no_hint}（这几类需要抽查）")


if __name__ == "__main__":
    main()
