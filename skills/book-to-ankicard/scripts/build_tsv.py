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
    evidence  书中能证明这张卡的一小段原文（建议 8~40 字）。给了 --source 时，
              会逐张核对它是否真的出现在全书文本里，用来抓“书里没有的内容”。
              evidence 不会写进 .tsv。
    kind      卡片类别，只用于统计（concept / method / rule / compare / number / example …）。

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


def to_html(text: str) -> str:
    """纯文本 → 安全的 Anki HTML：转义、换行、**加粗**。"""
    t = html.escape(text.strip(), quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = t.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    return t.replace("\n", "<br>")


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
    ap.add_argument("--notetype", default="Basic")
    ap.add_argument("--max-front", type=int, default=120)
    ap.add_argument("--max-back", type=int, default=400)
    ap.add_argument("--strict", action="store_true", help="有错误时返回非零退出码")
    a = ap.parse_args()

    cards = load_cards(a.inputs)
    book = norm_for_match(a.source.read_text("utf-8")) if a.source else None

    errors: list[str] = []
    warns: list[str] = []
    seen: dict[str, str] = {}
    rows = []
    kinds: Counter = Counter()
    per_tag: Counter = Counter()
    ev_ok = ev_miss = ev_none = 0

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
        if len(back) > a.max_back:
            warns.append(f"{w} 答案过长（{len(back)}字），考虑拆成多张：{front[:30]}")
        hit = [x for x in CONTEXT_WORDS if x in front]
        if hit:
            warns.append(f"{w} 问题依赖上下文（含“{hit[0]}”），脱离书本会看不懂：{front[:30]}")
        if "？" not in front and "?" not in front and not front.endswith(("是", "为", "：", ":")):
            warns.append(f"{w} 问题不像问句，建议改成明确提问：{front[:30]}")

        ev = (c.get("evidence") or "").strip()
        if book is not None:
            if not ev:
                ev_none += 1
            elif norm_for_match(ev) in book:
                ev_ok += 1
            else:
                ev_miss += 1
                warns.append(f"{w} evidence 在原书中找不到（可能是编造或抄错）：{front[:30]}")

        back_html = to_html(back)
        if c.get("source"):
            src = html.escape(str(c["source"]), quote=False)
            back_html += f"<br><br><small style='color:gray'>出处：{src}</small>"
        tags = clean_tags(c.get("tags"))
        rows.append([to_html(front), back_html, tags])
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

    print(f"已写出 {len(rows)} 张卡 → {a.out}")
    print("类别：" + "，".join(f"{k} {v}" for k, v in kinds.most_common()))
    if book is not None:
        print(f"原文核对：通过 {ev_ok}，找不到 {ev_miss}，未提供 evidence {ev_none}")
    top_tags = "，".join(f"{k}:{v}" for k, v in per_tag.most_common(12))
    if top_tags:
        print("标签（前12）：" + top_tags)
    for m in errors:
        print("错误：" + m)
    for m in warns:
        print("警告：" + m)
    if errors and a.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
