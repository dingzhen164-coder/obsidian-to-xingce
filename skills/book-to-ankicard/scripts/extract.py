#!/usr/bin/env python3
"""把一本书提取成纯文本，并粗略识别章节。

用法：
    python3 extract.py <书文件> [--out 工作目录]

支持：.pdf .epub .docx .md .markdown .txt .html .htm .rst
输出（在工作目录里）：
    full_text.txt   全书文本（卡片的 evidence 校验就以它为准）
    metadata.json   字数、页数、检测到的章节（起止行号与字数）

PDF 优先用 PyMuPDF（pip install pymupdf），没有时回退到 pdftotext（poppler），再回退 pypdf。
"""
import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from html.parser import HTMLParser
from pathlib import Path


class _Strip(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section"}

    def __init__(self):
        super().__init__()
        self.out = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        if tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.out.append(data)


def html_to_text(raw: str) -> str:
    p = _Strip()
    p.feed(raw)
    return html.unescape("".join(p.out))


def read_pdf(path: Path) -> tuple[str, int | None]:
    """优先用 PyMuPDF（加粗/变色的行内文字不会被挪位置）；没有就退回 pdftotext，再退回 pypdf。"""
    try:
        import pymupdf  # type: ignore
    except ImportError:
        try:
            import fitz as pymupdf  # type: ignore
        except ImportError:
            pymupdf = None
    if pymupdf is not None:
        with pymupdf.open(str(path)) as doc:
            pages = len(doc)
            return "\n".join(pg.get_text("text") for pg in doc), pages
    if shutil.which("pdftotext"):
        print("提示：未安装 PyMuPDF，改用 pdftotext（加粗字可能被挪位置）。建议 pip install pymupdf", file=sys.stderr)
        r = subprocess.run(
            ["pdftotext", "-enc", "UTF-8", str(path), "-"],
            capture_output=True, check=True,
        )
        text = r.stdout.decode("utf-8", "replace")
        pages = text.count("\f") or None
        return text.replace("\f", "\n"), pages
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        sys.exit("提取 PDF 需要 PyMuPDF（pip install pymupdf）、pdftotext（poppler-utils）或 pypdf，请先安装其一。")
    reader = PdfReader(str(path))
    return "\n".join((pg.extract_text() or "") for pg in reader.pages), len(reader.pages)


def read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    return html.unescape(re.sub(r"<[^>]+>", "", xml))


def read_epub(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        order: list[str] = []
        try:
            container = z.read("META-INF/container.xml").decode("utf-8", "replace")
            opf_path = re.search(r'full-path="([^"]+)"', container).group(1)
            opf = z.read(opf_path).decode("utf-8", "replace")
            base = opf_path.rsplit("/", 1)[0] + "/" if "/" in opf_path else ""
            manifest = dict(re.findall(r'<item[^>]*?id="([^"]+)"[^>]*?href="([^"]+)"', opf))
            manifest.update({k: v for v, k in re.findall(r'<item[^>]*?href="([^"]+)"[^>]*?id="([^"]+)"', opf)})
            for idref in re.findall(r'<itemref[^>]*?idref="([^"]+)"', opf):
                href = manifest.get(idref)
                if href:
                    order.append(base + href.split("#")[0])
        except Exception:
            pass
        if not order:
            order = sorted(n for n in names if n.lower().endswith((".xhtml", ".html", ".htm")))
        parts = []
        for n in order:
            if n in names:
                parts.append(html_to_text(z.read(n).decode("utf-8", "replace")))
    return "\n\n".join(parts)


def read_any(path: Path) -> tuple[str, int | None]:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return read_pdf(path)
    if ext == ".docx":
        return read_docx(path), None
    if ext == ".epub":
        return read_epub(path), None
    if ext in (".html", ".htm", ".xhtml"):
        return html_to_text(path.read_text("utf-8", "replace")), None
    if ext in (".md", ".markdown", ".txt", ".rst", ".text"):
        return path.read_text("utf-8", "replace"), None
    sys.exit(f"不支持的格式：{ext}")


TOP_RE = re.compile(
    r"^\s*(第[一二三四五六七八九十百零〇\d]+\s*[章节编篇讲部]|chapter\s+\d+|part\s+[ivx\d]+)",
    re.IGNORECASE,
)
SUB_RE = re.compile(r"^\s*[一二三四五六七八九十]+、")
TOC_TAIL = re.compile(r"[\s.·…]*\d+\s*$")
SENTENCE = re.compile(r"[，。；！？]")


def detect_chapters(lines: list[str]) -> list[dict]:
    """返回候选标题，level=1（章/讲/Part）或 2（一、二、…小节）。

    只是启发式：目录行（以页码结尾）、含句号逗号的长句、过短片段都会被过滤。
    最终以书的目录为准，由调用方人工/模型核对。
    """
    hits = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s or len(s) > 60 or SENTENCE.search(s):
            continue
        if TOC_TAIL.search(s) and len(s) > 6:  # 目录行：以页码结尾
            continue
        if TOP_RE.match(s):
            hits.append((i, s, 1))
        elif SUB_RE.match(s):
            hits.append((i, s, 2))
    chapters = []
    for k, (i, title, level) in enumerate(hits):
        end = hits[k + 1][0] if k + 1 < len(hits) else len(lines)
        chars = sum(len(x.strip()) for x in lines[i:end])
        if chars < 200:  # 过短，多半是目录残片
            continue
        chapters.append(
            {"level": level, "title": title, "start_line": i + 1, "end_line": end, "chars": chars}
        )
    return chapters


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("book")
    ap.add_argument("--out", help="工作目录，默认新建临时目录")
    a = ap.parse_args()

    src = Path(a.book).expanduser()
    if not src.is_file():
        sys.exit(f"找不到文件：{src}")
    out = Path(a.out) if a.out else Path(tempfile.mkdtemp(prefix="book_card_work-"))
    out.mkdir(parents=True, exist_ok=True)

    text, pages = read_any(src)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    (out / "full_text.txt").write_text(text, "utf-8")

    lines = text.splitlines()
    meta = {
        "source": str(src),
        "title_guess": src.stem,
        "pages": pages,
        "chars": len(re.sub(r"\s", "", text)),
        "lines": len(lines),
        "chapters": detect_chapters(lines),
        "workdir": str(out),
    }
    (out / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")

    print(f"Workdir -> {out}")
    print(f"Text    -> {out / 'full_text.txt'}")
    print(f"字数(去空白) {meta['chars']}，页数 {pages}，检测到章节 {len(meta['chapters'])} 个")
    for c in meta["chapters"]:
        pad = "  " * (c["level"] - 1)
        print(f"  L{c['start_line']:>5}-{c['end_line']:<5} {c['chars']:>6}字  {pad}{c['title']}")
    if not meta["chapters"]:
        print("未检测到章节标题：请人工按目录或标题划分。")
    else:
        print("提示：章节为启发式识别，请对照书的目录核对后再划分。")


if __name__ == "__main__":
    main()
