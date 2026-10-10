#!/usr/bin/env python3
"""把卡片 JSONL 校验并导出为 Anki 可直接导入的 .tsv。

用法：
    python3 build_tsv.py <cards目录或.jsonl文件>... --deck "牌组名" --out 输出.tsv
                         [--source full_text.txt] [--strict]

每行 JSONL 一张卡：
    {"front": "问题", "back": "答案", "tags": ["第1章","拆词法"],
     "source": "第1章 五、拆词法", "evidence": "原文中的一小段话", "kind": "concept"}

必填：front、back。
可选：
    tags      标签列表（或空格分隔字符串）。标签内部不能有空格，会自动换成下划线。
    source    出处，会附在答案末尾，小字显示。
    evidence  书中能证明这张卡的一小段原文（建议 8~40 字）；一张卡汇总了多处内容时，
              可以给字符串列表，每一段都会被核对。给了 --source 时，会逐段核对它们
              是否真的出现在全书文本里，用来抓“书里没有的内容”。
              evidence 不会写进 .tsv。
    kind      卡片类别，只用于统计（concept / method / rule / compare / number / example …）。

front/back 里可以用的排版标记（纯文本，脚本负责转成 Anki 的 HTML）：
    **文字**            加粗
    ==文字==            红色加粗（用来标出关键词，少用）
    ^^文字^^            绿色小标签（不加粗）。注意：两处加粗不要只隔一个换行紧挨着，
                        某些查看器（如“玉简”）会把它们的 ** 合并成一段加粗
    # 标题              小标题（蓝色加粗，独占一行）
    - 条目              无序列表（连续的行归为一组）
    1. 条目             有序列表
    > 引用              引用块，用来放例题（连续的行归为一块）
    | a | b |           表格（第一行为表头；|---|---| 分隔行会被忽略）
    ---                 分隔线
    空行                段落间距
答案区一律左对齐（Anki 默认居中，长内容会很难读）。

导出格式依据 Anki 官方手册“Text files”：UTF-8、制表符分隔、文件头
#separator / #html / #notetype / #deck / #tags column。
"""
import argparse
import csv
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path

CONTEXT_WORDS = ["本章", "上文", "上述", "如上", "前面提到", "该书", "本书", "这一讲", "本讲", "上面"]
WS = re.compile(r"\s+")


def norm_for_match(s: str) -> str:
    """去掉所有空白，便于在 PDF 断行文本里查找 evidence。"""
    return WS.sub("", s.replace("　", ""))


def ngram_coverage(ev: str, book: str, n: int = 4) -> float:
    """evidence 的 n 元组有多大比例出现在全书里。

    pdftotext 会把加粗/变色的行内文字挪到别处，整句精确匹配会误报；
    编造的句子则几乎没有 n 元组能在书里找到。
    """
    if len(ev) < n:
        return 1.0 if ev in book else 0.0
    grams = [ev[i : i + n] for i in range(len(ev) - n + 1)]
    return sum(1 for g in grams if g in book) / len(grams)


INLINE_BOLD = re.compile(r"\*\*(.+?)\*\*")
INLINE_HI = re.compile(r"==(.+?)==")
INLINE_LABEL = re.compile(r"\^\^(.+?)\^\^")  # ^^文字^^：绿色小标签（不加粗，避免相邻加粗被“玉简”类工具合并）
# 样式只用 Anki 里有效的写法；“玉简”等会把 HTML 转成 Markdown 的工具只认颜色，其余样式被丢掉也不影响阅读。
STYLE_H = "color:#2e6da4;margin:0.7em 0 0.2em"
STYLE_Q = "border-left:3px solid #999;padding:2px 0 2px 10px;margin:6px 0"
RICH_LINE = re.compile(r"^\s*(#{1,6}\s|[-*+]\s|\d+[.)]\s)", re.M)


def inline(t: str) -> str:
    t = html.escape(t, quote=False)
    t = INLINE_BOLD.sub(r"<b>\1</b>", t)
    # 红字：<span 颜色> 在外、<b> 在内。反过来写（<b> 包 <span>）会让 Markdown 化的工具留下游离的 **。
    t = INLINE_LABEL.sub(r"<span style='color:#2e7d32'>\1</span>", t)
    return INLINE_HI.sub(r"<span style='color:#c0392b'><b>\1</b></span>", t)


def table_to_items(rows: list[list[str]]) -> list[str]:
    """表格 → 列表项。很多卡片查看器会把 <table> 压平成一行字，所以不输出表格。

    - 只有表头 + 1 行数据：转置，每列一条（“方式：通过……/利用……”）
    - 两列：“**第一列**：第二列”
    - 三列及以上：“**第一列**（表头2：内容；表头3：内容）”
    """
    if not rows:
        return []
    head, body = list(rows[0]), [list(r) for r in rows[1:]]
    n = len(head)
    for i in range(1, n):  # 表头里被左边盖住的格子（“⇢”/“〃”）= 和左边同一个表头
        if head[i] in ("⇢", "〃"):
            head[i] = head[i - 1]
    body = [r + [""] * (n - len(r)) for r in body]
    if len(body) == 1 and n >= 2:
        return [f"**{h}**：{v}" for h, v in zip(head, body[0]) if v not in ("⇢", "〃")]

    def merge(cols):  # 同名表头相邻：值接在一起（“效力”下分“有效/无效”两列）
        pairs: list[list[str]] = []
        for h, v in cols:
            if pairs and pairs[-1][0] == h:
                if v != pairs[-1][1]:
                    pairs[-1][1] += "：" + v
            else:
                pairs.append([h, v])
        return pairs

    # 第一列是“〃”的行，属于上一行的同一组（上面那一格跨了行）
    groups: list[list[list[str]]] = []
    for r in body:
        if r[0] != "〃" or not groups:
            groups.append([r])
        else:
            groups[-1].append(r)
    items = []
    for g in groups:
        # 整组都盖着的列 = 组级信息（只在组内第一行写）；只盖了几行的列 = 行级信息（往下抄）
        group_level = {j for j in range(1, n) if len(g) > 1 and all(rr[j] == "〃" for rr in g[1:])}
        prev = None
        for k, rr in enumerate(g):
            cur = list(rr)
            for j in range(n):
                if cur[j] == "〃" and prev is not None and j not in group_level and j != 0:
                    cur[j] = prev[j]
            prev = cur
            cols = [(head[j], cur[j]) for j in range(n)
                    if cur[j] not in ("⇢", "〃") and not (k > 0 and (j == 0 or j in group_level))]
            pairs = merge(cols)
            if not pairs:
                continue
            if k > 0:
                items.append("↳ " + "；".join(f"{h}：{v}" for h, v in pairs))
            elif len(pairs) == 1:
                items.append(pairs[0][1])
            elif len(pairs) == 2:
                items.append(f"**{pairs[0][1]}**：{pairs[1][1]}")
            else:
                rest = "；".join(f"{h}：{v}" for h, v in pairs[1:])
                items.append(f"**{pairs[0][1]}**（{rest}）")
    return items


def to_html(text: str, left: bool = True) -> str:
    """纯文本（带上面的排版标记）→ Anki HTML。输出是单行，没有换行符。

    只用 <h3> <b> <ul><ol><li> <div> <br> <span 颜色> 这些最常见的标签：
    Anki 里正常显示；被转成 Markdown 的查看器也能保留标题、列表、加粗、颜色。
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ").strip().split("\n")
    out: list[str] = []
    i = 0

    def is_special(t: str) -> bool:
        return (not t) or t == "---" or t.startswith(("# ", "> ", "|")) or bool(re.match(r"^[-•]\s+", t)) or bool(re.match(r"^\d+[.、]\s*", t))

    while i < len(lines):
        st = lines[i].strip()
        if not st:
            if out and out[-1] != "<div><br></div>":
                out.append("<div><br></div>")
            i += 1
        elif st == "---":
            out.append("<hr>")
            i += 1
        elif st.startswith("# "):
            out.append(f"<h3 style='{STYLE_H}'>{inline(st[2:])}</h3>")
            i += 1
        elif st.startswith("> "):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(inline(lines[i].strip().lstrip(">").strip()))
                i += 1
            out.append(f"<div style='{STYLE_Q}'>" + "<br>".join(buf) + "</div>")
        elif st.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    rows.append(cells)
                i += 1
            items = table_to_items(rows)
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
        elif re.match(r"^[-•]\s+", st):
            items = []
            while i < len(lines) and re.match(r"^[-•]\s+", lines[i].strip()):
                items.append("<li>" + inline(re.sub(r"^[-•]\s+", "", lines[i].strip())) + "</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
        elif re.match(r"^\d+[.、]\s*", st):
            items = []
            while i < len(lines) and re.match(r"^\d+[.、]\s*", lines[i].strip()):
                items.append("<li>" + inline(re.sub(r"^\d+[.、]\s*", "", lines[i].strip())) + "</li>")
                i += 1
            out.append("<ol>" + "".join(items) + "</ol>")
        else:
            buf = []
            while i < len(lines) and not is_special(lines[i].strip()):
                buf.append(inline(lines[i].strip()))
                i += 1
            out.append("<div>" + "<br>".join(buf) + "</div>")
    body = "".join(out)
    return f"<div style='text-align:left'>{body}</div>" if left else body


def example_text(e: dict, with_analysis: bool = False) -> str:
    """把 extract_examples.py 抽出的一道例题排成卡片文本（标记语法）：完整题干、选项、答案、书里的方法论提示。"""
    title = f"**【{e['label']}】（{e['source']}）**" if e.get("source") else f"**【{e['label']}】**"
    parts = [title, e["stem"]]
    parts += e["options"]
    if e.get("answer"):
        parts.append(f"**答案：{e['answer']}**")
    if with_analysis and e.get("analysis"):
        parts.append(f"^^【解析】^^{e['analysis']}")
    if e.get("hint"):
        parts.append(f"^^【方法论提示】^^{e['hint']}")
    return "\n".join(parts)


def load_cards(paths: list[Path]) -> list[dict]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files += sorted(p.glob("*.jsonl"))
        else:
            files.append(p)
    cards = []
    for f in files:
        for n, line in enumerate(f.read_text("utf-8").splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                c = json.loads(line)
            except json.JSONDecodeError as e:
                sys.exit(f"{f.name}:{n} JSON 格式错误：{e}")
            c["_where"] = f"{f.name}:{n}"
            cards.append(c)
    return cards


def clean_tags(t) -> str:
    if isinstance(t, str):
        t = t.split()
    out = []
    for x in t or []:
        x = re.sub(r"\s+", "_", str(x).strip())
        if x:
            out.append(x)
    return " ".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--deck", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--source", type=Path, help="全书文本（extract.py 生成的 full_text.txt），用于核对 evidence")
    ap.add_argument("--examples", type=Path, help="extract_examples.py 生成的 examples.json；卡片里用 \"examples\": [id,…] 引用")
    ap.add_argument("--with-analysis", action="store_true", help="例题里同时放书里的“解析”（默认只放 题干、选项、答案、方法论提示）")
    ap.add_argument("--tables", type=Path, help="pdf_to_cards.py 生成的 tables.json；卡片里的 [[table:ID]] 由它填充")
    ap.add_argument("--table-format", choices=["html", "list"], default="html",
                    help="html=真正的表格（Anki 里正常；“玉简”需要 3.4 以后支持表格的版本）；list=拆成列表（任何查看器都能看）")
    ap.add_argument("--media-dir", type=Path, help="卡片里 [[img:文件名]] 引用的图片所在目录；会复制到输出文件旁的 media/")
    ap.add_argument("--notetype", default="Basic")
    ap.add_argument("--profile", choices=["memory", "method"], default="memory",
                    help="memory=记忆型（一点一卡，答案短）；method=方法论型（体系卡，答案可长）")
    ap.add_argument("--max-front", type=int)
    ap.add_argument("--max-back", type=int)
    ap.add_argument("--strict", action="store_true", help="有错误时返回非零退出码")
    a = ap.parse_args()
    if a.max_front is None:
        a.max_front = 150 if a.profile == "method" else 120
    if a.max_back is None:
        a.max_back = 1800 if a.profile == "method" else 400

    cards = load_cards(a.inputs)
    tables_by_id: dict = json.loads(a.tables.read_text("utf-8")) if a.tables else {}
    media_used: set[str] = set()
    ex_by_id: dict[str, dict] = {}
    if a.examples:
        ex_by_id = {e["id"]: e for e in json.loads(a.examples.read_text("utf-8"))}
    book = norm_for_match(a.source.read_text("utf-8")) if a.source else None

    errors: list[str] = []
    warns: list[str] = []
    notes: list[str] = []
    seen: dict[str, str] = {}
    rows = []
    kinds: Counter = Counter()
    per_tag: Counter = Counter()
    ev_ok = ev_near = ev_miss = ev_none = 0

    for c in cards:
        w = c["_where"]
        front = (c.get("front") or "").strip()
        back = (c.get("back") or "").strip()
        if not front or not back:
            errors.append(f"{w} front/back 为空，已丢弃")
            continue
        key = norm_for_match(front)
        if key in seen:
            warns.append(f"{w} 与 {seen[key]} 的问题重复，已丢弃：{front[:30]}")
            continue
        seen[key] = w

        if len(front) > a.max_front:
            warns.append(f"{w} 问题过长（{len(front)}字），可能不是单一知识点：{front[:30]}…")
        hit = [x for x in CONTEXT_WORDS if x in front]
        if hit:
            warns.append(f"{w} 问题依赖上下文（含“{hit[0]}”），脱离书本会看不懂：{front[:30]}")
        if c.get("kind") != "knowledge_point" and "？" not in front and "?" not in front and not front.endswith(("是", "为", "：", ":")):
            warns.append(f"{w} 问题不像问句，建议改成明确提问：{front[:30]}")

        evs = c.get("evidence") or []
        if isinstance(evs, str):
            evs = [evs]
        evs = [e.strip() for e in evs if e and e.strip()]
        if book is not None:
            if not evs:
                ev_none += 1
            else:
                levels = []
                for e in evs:
                    ne = norm_for_match(e)
                    if ne in book:
                        levels.append("ok")
                    elif ngram_coverage(ne, book) >= 0.8:
                        levels.append("near")
                    else:
                        levels.append("miss")
                        warns.append(f"{w} evidence 在原书中找不到（可能是编造或抄错）：「{e[:24]}」 → {front[:24]}")
                if "miss" in levels:
                    ev_miss += 1
                elif "near" in levels:
                    ev_near += 1
                    notes.append(f"{w} evidence 仅近似匹配（多半是 PDF 提取把强调文字挪了位置），请对照原文看一眼：{front[:30]}")
                else:
                    ev_ok += 1

        if len(back) > a.max_back:  # 只算手写部分，不含自动排入的例题
            warns.append(f"{w} 答案过长（{len(back)}字），考虑拆成多张：{front[:30]}")
        ex_ids = c.get("examples") or []
        if ex_ids:
            missing = [x for x in ex_ids if x not in ex_by_id]
            if missing:
                errors.append(f"{w} 找不到例题 {missing}（要用 --examples 指定 examples.json）")
            exs = [example_text(ex_by_id[x], a.with_analysis) for x in ex_ids if x in ex_by_id]
            if exs:
                back = back.rstrip() + "\n\n# 例题（共 %d 道）\n" % len(exs) + "\n\n".join(exs)
        if a.profile == "method" and not RICH_LINE.search(back):
            warns.append(f"{w} 答案里没有小标题或列表，部分查看器会把整张卡居中排版：{front[:24]}")
        raws: dict[str, str] = {}

        def put_raw(html_str: str) -> str:
            key = f"@@RAW{len(raws)}@@"
            raws[key] = html_str
            return key

        def sub_table(m):
            tid = m.group(1)
            t = tables_by_id.get(tid)
            if not t:
                errors.append(f"{w} 找不到表格 {tid}（要用 --tables 指定 tables.json）")
                return ""
            if a.table_format == "html":
                return put_raw(t["html"])
            return t["md"]  # list：交给下面的“| 表格 |”标记，转成列表

        def sub_img(m):
            media_used.add(m.group(1))
            return put_raw(f"<div><img src='{html.escape(m.group(1), quote=True)}' style='max-width:100%'></div>")

        back = re.sub(r"\[\[table:([^\]]+)\]\]", sub_table, back)
        back = re.sub(r"\[\[img:([^\]]+)\]\]", sub_img, back)
        back_html = to_html(back, left=False)
        for key, val in raws.items():
            back_html = back_html.replace(f"<div>{key}</div>", val).replace(key, val)
        if c.get("source"):
            src = html.escape(str(c["source"]), quote=False)
            back_html += f"<div style='margin-top:0.8em;font-size:0.8em;color:gray'>出处：{src}</div>"
        back_html = f"<div style='text-align:left'>{back_html}</div>"
        tags = clean_tags(c.get("tags"))
        rows.append([to_html(front, left=False), back_html, tags])
        kinds[c.get("kind") or "未标注"] += 1
        for t in tags.split():
            per_tag[t] += 1

    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("w", encoding="utf-8", newline="") as fh:
        fh.write("#separator:Tab\n#html:true\n")
        fh.write(f"#notetype:{a.notetype}\n#deck:{a.deck}\n#tags column:3\n")
        fh.write("#columns:Front\tBack\tTags\n")
        w_ = csv.writer(fh, delimiter="\t", quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        w_.writerows(rows)

    if media_used:
        if a.media_dir:
            dst = a.out.parent / "media"
            dst.mkdir(parents=True, exist_ok=True)
            import shutil
            for name in sorted(media_used):
                src = a.media_dir / name
                if src.is_file():
                    if src.resolve() != (dst / name).resolve():
                        shutil.copy2(src, dst / name)
                else:
                    errors.append(f"找不到图片 {src}")
            print(f"图片 {len(media_used)} 张已复制到 {dst} —— Anki：拷进 collection.media；玉简：放进库里任意位置（按文件名找）")
        else:
            print(f"提示：卡片引用了 {len(media_used)} 张图片（{', '.join(sorted(media_used))}），没有给 --media-dir，图片没有复制")
    print(f"已写出 {len(rows)} 张卡 → {a.out}")
    print("类别：" + "，".join(f"{k} {v}" for k, v in kinds.most_common()))
    if book is not None:
        print(f"原文核对：精确通过 {ev_ok}，近似匹配 {ev_near}，找不到 {ev_miss}，未提供 evidence {ev_none}")
    top_tags = "，".join(f"{k}:{v}" for k, v in per_tag.most_common(12))
    if top_tags:
        print("标签（前12）：" + top_tags)
    for m in errors:
        print("错误：" + m)
    for m in warns:
        print("警告：" + m)
    for m in notes:
        print("提示：" + m)
    if errors and a.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
