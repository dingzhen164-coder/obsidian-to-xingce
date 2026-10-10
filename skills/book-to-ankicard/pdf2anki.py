#!/usr/bin/env python3
"""扫描版/OCR 教材 PDF → Anki .tsv（Windows / macOS / Linux 通用）。
用法：python pdf2anki.py 教材.pdf [科目名] [额外参数…]
额外参数原样传给 scripts/pdf_to_cards.py：--unit auto|kaodian|zhishidian、--unit-regex、--unit-label、--only、--drop、--fixes
输出在 PDF 同目录的「<PDF名>_anki」文件夹：<科目>.tsv、report.md（先看带 ⚠ 的）、media/（图片）
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


SUBJECTS = ["三国法", "理论法", "法理学", "民事诉讼法", "刑事诉讼法", "民诉", "刑诉", "民法", "刑法", "行政法", "商经知", "商经", "宪法", "法制史", "职业道德", "国际法", "国际私法", "国际经济法"]


def guess_subject(stem: str) -> str:
    """从文件名里认科目；认不出来就取文件名前 10 个字（不要把整个长文件名放进卡片正面）。"""
    for s in SUBJECTS:
        if s in stem:
            return s
    return stem[:10]


def main() -> int:
    if len(sys.argv) < 2 or not Path(sys.argv[1]).is_file():
        print(__doc__)
        return 1
    pdf = Path(sys.argv[1]).resolve()
    rest = sys.argv[2:]
    subject = guess_subject(pdf.stem)
    if rest and not rest[0].startswith("--"):
        subject, rest = rest[0], rest[1:]
    out = pdf.parent / f"{pdf.stem}_anki"
    out.mkdir(exist_ok=True)
    py = [sys.executable, "-I"]
    r = subprocess.run(py + [str(HERE / "scripts" / "pdf_to_cards.py"), str(pdf), "--out", str(out), "--subject", subject, *rest])
    if r.returncode:
        return r.returncode
    tsv = out / f"{subject}.tsv"
    r = subprocess.run(py + [str(HERE / "scripts" / "build_tsv.py"), str(out / "cards"), "--deck", f"法考::{subject}", "--out", str(tsv),
                             "--profile", "memory", "--max-back", "30000", "--tables", str(out / "tables.json"),
                             "--table-format", "html", "--media-dir", str(out / "media")])
    if r.returncode:
        return r.returncode
    print(f"\n完成 → {tsv}")
    print(f"1) 先打开 {out / 'report.md'}，只看带 ⚠ 的地方（数字被截断、答案缺失、标题没认出来等）")
    print(f"2) 图片：把 {out / 'media'} 里的文件拷进 Anki 的 collection.media（或你的库）")
    print(f"3) Anki：文件 → 导入 → 选 {tsv.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
