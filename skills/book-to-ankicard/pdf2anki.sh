#!/bin/bash
# 扫描版/OCR 教材 PDF → Anki .tsv（一个知识点一张卡，含表格和示意图）。macOS / Linux。
# 用法：./pdf2anki.sh 教材.pdf [科目名] [额外参数…]
#   例：./pdf2anki.sh ~/Downloads/国际法.pdf 国际法
#   例：./pdf2anki.sh 民法.pdf 民法 --only 4,5 --drop "水印词1,水印词2"
# 额外参数原样传给 pdf_to_cards.py：--unit auto|kaodian|zhishidian、--unit-regex、--unit-label、--only、--drop、--fixes
# 输出在 PDF 同目录的「<PDF名>_anki/」：<科目>.tsv、report.md（先看带 ⚠ 的）、media/（图片）
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PDF="$1"; SUBJ="${2:-$(basename "${1%.*}")}"
[ -f "$PDF" ] || { sed -n 2,8p "$0"; exit 1; }
shift; [ $# -gt 0 ] && shift || true
OUT="$(cd "$(dirname "$PDF")" && pwd)/$(basename "${PDF%.*}")_anki"

# 第一次运行自动建虚拟环境并装依赖（放在 ~/.pdf2anki-venv，之后秒开）
VENV="$HOME/.pdf2anki-venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "第一次运行：安装依赖（约 1 分钟）…"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q pymupdf opencv-python-headless numpy
fi
PY="$VENV/bin/python"

mkdir -p "$OUT"
"$PY" -I "$HERE/scripts/pdf_to_cards.py" "$PDF" --out "$OUT" --subject "$SUBJ" "$@"
"$PY" -I "$HERE/scripts/build_tsv.py" "$OUT/cards" --deck "法考::$SUBJ" --out "$OUT/$SUBJ.tsv" \
  --profile memory --max-back 6000 --tables "$OUT/tables.json" --table-format html --media-dir "$OUT/media"
echo
echo "完成 → $OUT/$SUBJ.tsv"
echo "1) 先打开 $OUT/report.md，只看带 ⚠ 的地方（数字被截断、答案缺失等）"
echo "2) 图片：把 $OUT/media/ 里的文件拷进 Anki 的 collection.media（或你的库）"
echo "3) Anki：文件 → 导入 → 选 $SUBJ.tsv"
