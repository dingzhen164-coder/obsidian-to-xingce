#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
真题入库：把 OCR 出来的 txt（模考试卷 / 练习册）整理成“行测修仙传”试炼塔的真题库。

    训练/题库/<板块>真题.md          ← 试炼塔读的题库（本脚本只追加，不改已有题目）
    训练/题库/图片/<板块>/<编号>.png  ← 图形推理、资料分析等题目的图
    训练/题库/_待入库/<名称>.md       ← 中间稿：脚本拆好题，AI/用户核对分类后再入库

三个子命令（只用 Python 标准库；输入是 PDF 时才需要 pymupdf）：

    python tiku.py prepare "<txt或pdf>" [--source "粉笔第36季模考"] [--board 论证逻辑] [--name 名称]
        拆题 → 写中间稿。自动识别来源（粉笔第N季模考 / 20XX年国考……）、答案、板块，猜知识点；
        拆不干净的题在“### 检查”里写明原因。
    python tiku.py commit "<中间稿.md>" [--dry-run]
        把中间稿里“已就绪”的题（板块、知识点已填，检查已清空，选项齐全）追加到对应题库；
        重复的题（编号相同或题干相同）跳过。入库的题从中间稿里删掉，剩下的下次再提交。
    python tiku.py answers "<中间稿或题库.md>" "<答案文本或文件>" --prefix 四海逻辑600-03
        练习册的答案在另一本书里时用：按“1-5 ABCDA”“1.A 2.B”之类的答案表，给编号以 prefix 开头的题补答案。

路径：默认按本脚本位置找库（<库>/copilot/skills/xingce-tiku/scripts/），也可以用 --vault 指定库根目录。
所有文件统一 UTF-8 + LF 换行（Windows / Mac 通过坚果云同步时不会整份变动）。
"""
import argparse
import hashlib
import re
import shutil
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:  # Windows 下输出被 agent 捕获时默认是 GBK，打印 ⚠ 会报错
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 试炼塔的板块名（= 训练/题库/<板块>真题.md）
BOARDS = ["政治理论", "常识判断", "逻辑填空", "片段阅读", "数量关系", "图形推理", "定义判断",
          "类比推理", "论证逻辑", "形式逻辑", "一拖五", "资料分析"]
ALIAS = {"类比关系": "类比推理", "中心理解": "片段阅读", "语句排序": "片段阅读", "语句表达": "片段阅读",
         "逻辑判断": "论证逻辑"}
IMAGE_BOARDS = {"图形推理", "资料分析"}          # 一定要图的板块（题目文字里没有图）
SHARED_BOARDS = {"资料分析", "一拖五"}            # 一组题共用材料
TODO = "（待补）"
UNSORTED = "待分类"

SECTION_RE = re.compile(r"^[一二三四五六七八九十]+\s*[\.．、]\s*(政治理论|常识判断|言语理解与表达|数量关系|判断推理|资料分析)")
ANS_RE = re.compile(r"正确答案[:：]\s*([A-D]?)\s*(?:你的答案[:：]\s*([A-D]?))?")
HEADER_TAIL_KW = ("本部分", "所给出的", "在这部分", "根据题目要求", "请根据", "要求你", "进行分析", "恰当的答案", "最恰当的")
ARGUMENT_KW = ("质疑", "削弱", "支持", "加强", "前提", "假设", "解释", "反驳", "反对", "评价", "漏洞", "结论")
FORMAL_KW = ("可以得出", "可以推出", "能够推出", "能推出", "一定为真", "一定为假", "不能确定", "必然为真",
             "必然为假", "可能为真", "哪项安排", "推出以下", "一定可以得出", "由此可以推出", "为真", "为假",
             "真话", "假话", "说对", "说错", "必然正确", "推论", "判断正确", "判断错误", "一定正确", "一定错误")
FIGURE_KW = ("填入问号处", "分为两类", "正方体", "多面体", "截面", "展开图", "视图", "立体图形", "拼合", "组合而成")
CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def write_lf(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(text)


def cn2int(s):
    if s.isdigit():
        return int(s)
    total, num = 0, 0
    for ch in s:
        if ch == "十":
            total += (num or 1) * 10
            num = 0
        elif ch == "百":
            total += (num or 1) * 100
            num = 0
        else:
            num = CN_NUM.get(ch, 0)
    return total + num


def norm_stem(s, opts=None):
    """查重指纹：去掉来源括号、空白和标点后的【完整】题干 + 图片文件名 + 四个选项。
    不能只取开头几十个字、也不能丢掉图片：图形推理的题干都是同一句“从所给的四个选项中……”，
    资料分析同组几道题开头都是同一段材料，只看开头会把不同的题误当成重复。"""
    s = re.sub(r"^（[^）]{0,30}）", "", (s or "").strip())
    s = re.sub(r"!\[\[([^\]|]*)(?:\|[^\]]*)?\]\]", lambda m: " " + Path(m.group(1)).name + " ", s)
    if opts:
        s += "".join("%s%s" % (k, opts.get(k, "")) for k in "ABCD")
    return re.sub(r"[\s\W_]+", "", s)


# ---------------------------------------------------------------- 库与路径
def find_vault(arg):
    if arg:
        return Path(arg).expanduser().resolve()
    here = Path(__file__).resolve()
    for p in here.parents:
        if (p / "训练").is_dir() or (p / "copilot" / "skills").is_dir():
            return p
    for p in [Path.cwd(), *Path.cwd().parents]:
        if (p / "训练").is_dir():
            return p
    sys.exit("找不到库根目录（含“训练”文件夹的目录），请加 --vault \"<库根目录>\"")


def bank_dir(vault):
    return vault / "训练" / "题库"


# ---------------------------------------------------------------- 读入与清洗
def read_input(path):
    if path.suffix.lower() == ".pdf":
        try:
            import pymupdf as fitz
        except ImportError:
            try:
                import fitz
            except ImportError:
                sys.exit("输入是 PDF，需要先 pip install pymupdf（或者先转成 txt 再给我）")
        doc = fitz.open(str(path))
        return "\n".join("≦ %d ≧\n" % (i + 1) + p.get_text() for i, p in enumerate(doc))
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def clean_lines(text):
    """去掉页码、广告、页眉页脚、重复的书眉；保留题目文字"""
    lines = [ln.strip().replace("　", " ") for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    # 在全文里重复出现很多次的短行是书眉/页眉（“600 逻辑判断”“2027年国考第三十六季……”）
    count = {}
    for ln in lines:
        if len(ln) <= 40:
            count[ln] = count.get(ln, 0) + 1
    out = []
    for ln in lines:
        if re.match(r"^≦\s*\d+\s*≧$", ln) or re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2})?$", ln):
            continue
        if re.match(r"^(\d{1,3}[\.．]\s*)+$", ln) or re.match(r"^\d{1,4}$", ln):
            continue  # “1. 2. 3. 4. 5.”（粉笔页首题号）、单独的页码
        if re.search(r"本试卷由粉笔用户|第\s*\d+\s*页\s*[，,]\s*共\s*\d+\s*页|扫描二维码|下载「粉笔」|听课刷题|就用粉笔"
                     r"|公考资料|V[:：]\s*\w{6,}|SIHAIGONGKAO|微信|关注公众号", ln):
            continue
        if count.get(ln, 0) >= 4 and not re.match(r"^[A-D][\.．。:：、]", ln) and not re.search(r"填入问号处|正确答案|^[A-D]$", ln) \
                and not SET_RE.match(ln):
            continue
        out.append(ln)
    return out


def detect_source(lines):
    """从开头几行猜试卷来源：粉笔第N季模考 / 20XX年国考 / 20XX年XX省考；猜不到返回空"""
    head = "\n".join(lines[:15])
    m = re.search(r"第([一二三四五六七八九十百\d]+)季", head)
    if m and ("模考" in head or "粉笔" in head):
        return "粉笔第%d季模考" % cn2int(m.group(1)), "粉笔%d季" % cn2int(m.group(1)), cn2int(m.group(1))
    m = re.search(r"(20\d{2})年.{0,12}?(国家公务员|国考)", head)
    if m:
        return "%s年国考" % m.group(1), "%s国考" % m.group(1), None
    m = re.search(r"(20\d{2})年.{0,6}?([\u4e00-\u9fff]{2,3}?)省.{0,10}?(公务员|省考)", head)
    if m:
        return "%s年%s省考" % (m.group(1), m.group(2)), "%s%s省考" % (m.group(1), m.group(2)), None
    return "", "", None


# ---------------------------------------------------------------- 选项
OPT_FENBI = re.compile(r"(?:(?<=\s)|^)([A-D])[\.．]")
# 练习册 OCR：选项字母后面的标点五花八门（A。B．C：D、），有时没有标点（“B干旱缺水”），C 常被识别成小写 c
OPT_BOOK = re.compile(r"(?:(?<=[\s。？?！!：:”）)])|^)([A-Dc])(?:\s*[\.．。:：、，,]|(?=[\u4e00-\u9fff“（(\d]))")


def split_options(text, scrambled):
    """(题干, {字母: 选项}, 问题)。选项常排两栏（A C 一行、B D 一行），粉笔 OCR 还会把 B D 挪到答案行后面，
    所以不按顺序找：题干 = 第一个 A 之前，B C D 各取 A 之后第一次出现的位置"""
    rx = OPT_FENBI if scrambled else OPT_BOOK
    marks = [(m.start(), m.end(), m.group(1).upper()) for m in rx.finditer(text)]
    first_a = next((mk for mk in marks if mk[2] == "A"), None)
    if not scrambled:
        # 练习册：题干里常有“A型血”“A领导”“特征A”，取【最后一个】后面还跟着 B、C、D 的 A 作为选项开头
        full = [mk for mk in marks if mk[2] == "A" and {"B", "C", "D"} <= {x[2] for x in marks if x[0] > mk[0]}]
        if full:
            first_a = full[-1]
    if not first_a:
        return text.strip(), {}, ["没找到选项"]
    chosen, seen = [first_a], {"A"}
    for mk in marks:
        if mk[0] > first_a[0] and mk[2] not in seen:
            seen.add(mk[2])
            chosen.append(mk)
    chosen.sort()
    stem = text[:chosen[0][0]].strip()
    opts = {}
    for i, (s, e, letter) in enumerate(chosen):
        end = chosen[i + 1][0] if i + 1 < len(chosen) else len(text)
        opts[letter] = re.sub(r"\s+", " ", text[e:end]).strip()
    problems = []
    missing = [x for x in "ABCD" if not opts.get(x)]
    if missing:
        problems.append("缺选项 " + "".join(missing))
    if any(len(v) > 160 for v in opts.values()):
        problems.append("有选项太长，可能吞进了下一题")
    if not scrambled and any(re.search(r"(?:^|\s)[A-D][\.．。:：、]\S", v) for v in opts.values()):
        problems.append("选项里还夹着另一组选项标记，可能拆错了")
    return stem, opts, problems


# ---------------------------------------------------------------- 分类
LOGIC_STRONG = re.compile(r"如果为真|若为真|削弱|加强|质疑|反驳|前提|假设|一定为真|一定为假|真话|假话|推理结构|论证方式")
# 言语问法要按完整短语认：“同意在本周末”里也有“意在”，“依次填入图形中”是逻辑题
VERBAL_FILL = re.compile(r"填入(?:文中|上文)?(?:画|划)横线|横线(?:处|部分)|依次填入.{0,4}最恰当")
VERBAL_READ = re.compile(r"这段文字|这段话|文段|上述文字|(?:意在|旨在|主要)(?:说明|强调|表明|告诉|指出|阐述|揭示|突出|介绍|讲|论述|讨论)|"
                         r"重新排列|语序正确|排序正确|标题|接下来最可能|下文最可能|语句填入|填入文中")
SEQ_ONLY = re.compile(r"^[\s①-⑨\d、，,]+$")


def verbal_board(stem, opts):
    """言语理解：逻辑填空（选词填空）还是片段阅读（主旨、意图、标题、排序、语句填入）；认不出返回空"""
    if VERBAL_FILL.search(stem):
        short = opts and all(len(re.sub(r"[\s\W_]+", "", v)) <= 12 for v in opts.values())
        return "逻辑填空" if "依次填入" in stem or short else "片段阅读"
    if VERBAL_READ.search(stem):
        return "片段阅读"
    return ""


def verbal_by_options(opts):
    """言语类练习册里问法认不出时：选项是一串序号（①③②④）→ 语句排序（片段阅读）；选项都是短词 → 逻辑填空；否则片段阅读"""
    vals = [v for v in opts.values() if v]
    if len(vals) < 4:
        return ""
    if all(SEQ_ONLY.match(v) for v in vals):
        return "片段阅读"
    if all(len(re.sub(r"[\s\W_]+", "", v)) <= 10 for v in vals):
        return "逻辑填空"
    return "片段阅读"


def guess_board(section, stem, opts):
    s = stem
    if section in ("政治理论", "常识判断", "数量关系", "资料分析"):
        return section
    if section == "言语理解与表达":
        if "重新排列" in s or "语序正确" in s or "排序" in s:
            return "片段阅读"
        short = opts and all(len(v) <= 12 for v in opts.values())
        if "依次填入" in s or ("横线" in s and short):
            return "逻辑填空"
        return "片段阅读"
    # 判断推理 或 不知道大题（练习册）
    if not section and not LOGIC_STRONG.search(re.split(r"[。！？”]", s.rstrip())[-1]):   # 练习册不知道大题：问句不是明显的逻辑问法时，先按言语的问法认
        v = verbal_board(s, opts)
        if v:
            return v
    figure_opts = not opts or all(re.sub(r"[\s\W_]+", "", v).upper() in ("", "A", "B", "C", "D") for v in opts.values())
    # 有判断推理大题时题干关键词就够；练习册（不知道大题）还要求选项本身是图，免得“组合而成”之类的词误判
    if (any(k in s for k in FIGURE_KW) and (section or figure_opts)) or (opts and figure_opts):
        return "图形推理"
    if "定义" in s and ("属于" in s or "符合" in s or "不符合" in s or "不属于" in s):
        return "定义判断"
    if len(s) <= 40 and not re.search(r"以下|下列|哪项|哪句", s) and (re.search(r"(对于|相当于)", s) or (opts and all(re.search(r"[:：]", v) for v in opts.values() if v))):
        return "类比推理"
    if any(k in re.sub(r"(如果|若|假如|假设)[^，,：:]{0,4}为真", "", s) for k in FORMAL_KW):  # “以下哪项如果为真”是论证题的问法
        return "形式逻辑"
    if any(k in s for k in ARGUMENT_KW):
        return "论证逻辑"
    if section == "言语理解与表达":
        return "片段阅读"
    return UNSORTED


# ---------------------------------------------------------------- OCR 符号修复：①②③、ⅠⅡⅢ
CIRCLED = "①②③④⑤⑥⑦⑧⑨"
ROMAN = {"I": "Ⅰ", "II": "Ⅱ", "III": "Ⅲ", "IV": "Ⅳ", "V": "Ⅴ", "VI": "Ⅵ"}
# 只由序号和连接词组成的选项（“①③④”“仅Ⅰ和Ⅲ”“@②4”“I、II都推不出”）
_SEQ_OPT = re.compile(r"^[\s①-⑨Ⅰ-Ⅵ\dIVHl@Q?？、，,和与及或仅只有都是不能推出得只均]*$")
_ROMAN_RUN = re.compile(r"(?<![A-Za-z])(IV|VI|V|III|II|I)(?![A-Za-z])")


def fix_symbols(stem, opts):
    """OCR 常把 ① 认成 @ / Q / 1，④ 认成 4，Ⅰ Ⅱ Ⅲ 认成 I / II / III（甚至 H）。只在明确是序号的地方还原：
    - 题干里已有 ①② 序列时，紧接着序列、出现在句首 / 标点后的数字（或 @、Q）还原成下一个圈号；
    - 题干用 I / II / III 当陈述编号（后面跟标点或汉字）时还原成 Ⅰ Ⅱ Ⅲ；
    - 选项只由序号和“和 / 仅 / 都”等组成时，按题干用的是圈号还是罗马数字整体还原。
    返回 (题干, 选项, 问题)；还原后同一选项里序号重复（如 ②②）说明 OCR 丢了信息，交给待修核对"""
    problems = []
    uses_circled = bool(re.search("[①-⑨]", stem)) or any(re.search("[①-⑨]", v) for v in opts.values())
    uses_roman = bool(re.search("[Ⅰ-Ⅵ]", stem) or re.search(r"(?<![A-Za-z])I{1,3}(?:[\.．。:：、]|(?=[\u4e00-\u9fff]))", stem)) \
        or any(re.search(r"(?<![A-Za-z])I{1,3}(?![A-Za-z])", v) and _SEQ_OPT.match(v) for v in opts.values())
    if uses_circled:
        out, last, i = [], 0, 0
        while i < len(stem):
            ch = stem[i]
            if ch in CIRCLED:
                last = CIRCLED.index(ch) + 1
            elif last and i and (stem[i - 1] in " \t\n。；;，,：:）)" or stem[i - 1] in CIRCLED) \
                    and ((ch.isdigit() and int(ch) == last + 1) or (ch in "@Q" and last == 0)) \
                    and i + 1 < len(stem) and re.match(r"[\u4e00-\u9fffA-Z“（(]", stem[i + 1]):
                last += 1
                ch = CIRCLED[last - 1]
            out.append(ch)
            i += 1
        stem = "".join(out)
        stem = re.sub(r"(^|[\s。；;：:])[@Q](?=[\u4e00-\u9fff])", lambda m: m.group(1) + "①", stem)
    if uses_roman:
        stem = re.sub(r"(?<![A-Za-z])(IV|VI|V|III|II|I)(?=[\.．。:：、\s]|[\u4e00-\u9fff])", lambda m: ROMAN[m.group(1)], stem)
    new = {}
    for k, v in opts.items():
        if v and _SEQ_OPT.match(v) and len(v) <= 16:
            if uses_circled and not uses_roman:
                v = re.sub(r"[@Q]", "①", v)
                v = re.sub(r"[1-9]", lambda m: CIRCLED[int(m.group(0)) - 1], v)
            elif uses_roman:
                v = v.replace("H", "II").replace("l", "I")
                v = _ROMAN_RUN.sub(lambda m: ROMAN[m.group(1)], v)
            v = re.sub(r"\s*[,，]\s*", "、", v)   # 序号之间统一用顿号
            marks = re.findall("[①-⑨Ⅰ-Ⅵ]", v)
            if len(marks) != len(set(marks)) or re.search(r"[?？@Q]", v):
                problems.append("选项 %s 的序号可能被 OCR 认错（%s），请对照原书" % (k, v))
        new[k] = v
    return stem, new, problems


def board_by_options(opts):
    """问法里认不出板块时，按选项的样子判断逻辑题：
    选项很短，或长度相近又有共同的字（“栖霞镇 / 莲花镇 / 五溪镇”“甲和乙 / 乙和丙”“仅I / 仅II”）→ 形式逻辑；
    选项长、长短不一（一句一句的论据）→ 论证逻辑。只在逻辑类练习册里用（见 _collect）"""
    vals = [re.sub(r"[\s\W_]+", "", v) for v in opts.values()]
    if len(vals) < 4 or not all(vals):
        return ""
    lens = [len(v) for v in vals]
    common = set(vals[0]).intersection(*map(set, vals[1:]))
    if max(lens) <= 6 or (max(lens) - min(lens) <= 4 and max(lens) <= 20 and common):
        return "形式逻辑"
    return "论证逻辑"


def guess_topic(board, stem):
    tail = stem[-80:]
    if board == "论证逻辑":
        for kws, name in ((("削弱", "质疑", "反驳", "反对", "不能支持"), "削弱"), (("支持", "加强"), "加强"),
                          (("前提", "假设"), "前提假设"), (("解释",), "解释"), (("评价",), "评价")):
            if any(k in tail for k in kws):
                # “不能削弱 / 除哪项外均能削弱”这类反问也归在同一类，提示一下
                return name
    if board == "图形推理":
        return UNSORTED
    if board == "逻辑填空":
        return UNSORTED
    return UNSORTED


# ---------------------------------------------------------------- 拆题：粉笔模考
def parse_fenbi(lines):
    """粉笔试卷 OCR：每题以“正确答案：X 你的答案：Y”结尾；答案行后面可能还挂着本题剩下的选项"""
    qs, buf, section = [], [], None
    for ln in lines:
        m = SECTION_RE.match(ln)
        if m:
            if buf and qs:  # 大题标题前的零散行：是上一题剩下的选项
                qs[-1]["tail"] += buf
            buf, section = [], m.group(1)
            continue
        a = ANS_RE.search(ln)
        if a:
            before = ln[:a.start()].strip()
            if before:
                buf.append(before)
            # 本行之前、属于上一题的残留选项：开头连续几行都是“X.”打头、并且是上一题缺的字母
            if qs:
                prev = qs[-1]
                while buf and re.match(r"^[A-D][\.．]", buf[0]):
                    prev["tail"].append(buf.pop(0))
            qs.append({"section": section, "lines": buf, "tail": [], "answer": a.group(1), "mine": a.group(2) or ""})
            buf = []
            continue
        if section and any(k in ln for k in HEADER_TAIL_KW) and not buf:
            continue
        buf.append(ln)
    if buf and qs:
        qs[-1]["tail"] += buf
    out = []
    for i, q in enumerate(qs, 1):
        text = "\n".join(q["lines"] + q["tail"])
        stem, opts, problems = split_options(text, scrambled=True)
        board = guess_board(q["section"], stem, opts)
        out.append({"num": i, "section": q["section"] or "", "stem": stem, "options": opts,
                    "answer": q["answer"], "mine": q["mine"], "board": board, "problems": problems})
    return out


# ---------------------------------------------------------------- 拆题：练习册
# 题号：后面有标点时接什么都行（“15：2008年…”“2.《道路交通安全法》…”）；没有标点时后面必须是汉字等（“18有些人…”）
START_RE = re.compile(r"(?:(?<=[\s。？?！!”）)])|^)([1-9]\d{0,2})(?:\s*[\.．。:：、，,]\s*(?=\S)|\s*(?=[\u4e00-\u9fff“\"（(《A-Z]))")


# 练习册每套开头的标记行：“练习题03”“05 练习题”“页07 练习题”“o1 练习题”（OCR 常把序号挪到前面或丢掉）
SET_RE = re.compile(r"^[#＃\w页\s]{0,5}练习题?\s*\d{0,3}$")


def _starts(text):
    """一段文字里的题目起点：题号连续，四个选项出完才可能开始下一题；允许漏认一个题号"""
    cands = [(m.start(), m.end(), int(m.group(1))) for m in START_RE.finditer(text)]
    starts, last, skipped = [], 0, []

    def has_abcd(seg):
        return set("ABCD") <= {m.group(1).upper() for m in OPT_BOOK.finditer(seg)}

    for c in cands:
        n = c[2]
        if starts and not has_abcd(text[starts[-1][1]:c[0]]):
            if n == 1 and starts[-1][2] == 1:
                starts[-1] = c  # 两个“1”之间没有选项：前一个是目录里的数字
            continue
        if not starts:
            if n in (1, 2):  # 第 1 题题号没认出来时从 2 开始
                starts.append(c)
                last = n
        elif n == 1 or last < n <= last + 2:
            if n == last + 2:
                skipped.append(len(starts) - 1)
            starts.append(c)
            last = n
    return starts, skipped


def parse_book(lines, start_set=0):
    """练习册：有“练习题NN”标记就按标记分套（第几套 = 第几个有题的标记段，和答案表的“练习NN”对得上）；
    没有标记就按“题号回到 1”分套。每套里题号连续，选项按 A→B→C→D"""
    segs, cur, nums, mark = [], [], [], None
    for ln in lines:
        if SET_RE.match(ln) and len(ln) <= 12:
            segs.append(cur)
            nums.append(mark)
            cur = []
            d = re.findall(r"\d+", ln)
            mark = int(d[-1]) if d else None   # 标记里写的套号（“练习题16”）；分上下册时下册从 16 开始
        else:
            cur.append(ln)
    segs.append(cur)
    nums.append(mark)
    texts = ["\n".join(x) for x in segs]
    by_marker = sum(bool(_starts(t)[0]) for t in texts) >= 2
    if not by_marker:
        texts, nums = ["\n".join(lines)], [None]
    out, group = [], 0
    for text, num in zip(texts, nums):
        starts, skipped = _starts(text)
        if not starts:
            continue  # 目录、封面
        if by_marker:
            # 用标记里的套号：第一套可以从任意号开始（下册），之后只接受紧跟着的号，OCR 认错 / 没认出就按上一套 +1
            ok = num is not None and 1 <= num <= 300 and (group < num <= group + 3 if group else True)
            if start_set:      # 用户指定了第一套是练习几：按顺序往后排，不看标记里的数字
                group = start_set if not group else group + 1
            else:
                group = num if ok else group + 1
        first = len(out)
        for i, (s, e, n) in enumerate(starts):
            if not by_marker and n == 1:
                group += 1
            end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
            stem, opts, problems = split_options(text[e:end], scrambled=False)
            stem = re.sub(r"\s*\n\s*", "", stem)
            stem, opts, sym = fix_symbols(stem, opts)
            problems += sym
            out.append({"num": n, "group": max(group, 1), "stem": stem, "options": opts, "answer": "",
                        "board": guess_board("", stem, opts), "problems": problems})
        for i in skipped:
            q = out[first + i]
            q["problems"].append("下一题（第 %d 题）的题号没认出来，可能并在这道题的选项里" % (q["num"] + 1))
        if by_marker and starts[0][2] == 2:
            out[first]["problems"].append("这一套的第 1 题题号没认出来，可能并在别处，请核对")
    return out


# ---------------------------------------------------------------- 拆题：模考板块复盘（最干净的来源）
REVIEW_FILE_RE = re.compile(r"^\d\d-(.+)\.md$")


def parse_review(season_dir):
    """读 xingce-mokao-split 生成的 板块复盘/第N季/NN-板块.md：题干、选项、正确答案、截图都是从 PDF 坐标拆的，比 OCR 准。
    格式见 xingce-mokao-split：### 36. ❌ / 题干 / - **A.** 选项 / > [!check]- 答案 / > 正确答案：**B** / ## 材料（第a-b题）"""
    out = []
    for f in sorted(season_dir.glob("[0-9][0-9]-*.md")):
        m = REVIEW_FILE_RE.match(f.name)
        board = ALIAS.get(m.group(1), m.group(1)) if m else ""
        if board not in BOARDS:
            continue
        cur, mat, mats, in_note = None, None, {}, False
        for ln in f.read_text(encoding="utf-8-sig").split("\n"):
            h = re.match(r"^### (\d+)\.", ln)
            mm = re.match(r"^## 材料（第(\d+)-(\d+)题）", ln)
            if mm:
                mat, cur = (int(mm.group(1)), int(mm.group(2))), None
                mats[mat] = []
                continue
            if h:
                cur = {"num": int(h.group(1)), "board": board, "lines": [], "options": {}, "answer": "",
                       "material": mat if mat and mat[0] <= int(h.group(1)) <= mat[1] else None}
                out.append(cur)
                in_note = False
                continue
            if cur is None:
                if mat in mats and ln.strip() != "---":
                    mats[mat].append(ln)
                continue
            if ln.strip() == "---":
                cur = None
                continue
            if ln.startswith("> [!note]"):
                in_note = True
            if in_note:
                continue
            a = re.search(r"正确答案：\*\*([A-D]?)", ln)
            o = re.match(r"^\s*-\s*\*\*([A-D])[\.．]\*\*\s*(.*)$", ln)
            if a:
                cur["answer"] = a.group(1)
            elif o:
                cur["options"][o.group(1)] = o.group(2).strip()
            elif not ln.startswith(">"):
                cur["lines"].append(ln)
        for q in out:
            if q["board"] == board and q["material"] and "mat_done" not in q:
                q["mat_done"] = True
                q["lines"] = [x for x in mats.get(q["material"], []) if x.strip()] + [""] + q["lines"]
    for q in out:
        stem = "\n".join(q.pop("lines")).strip()
        stem = re.sub(r"\n{3,}", "\n\n", stem)
        q.update(section="", stem=stem, mine="", problems=[])
        # 选项就是图里的 A/B/C/D（图形推理常见）时，拆分脚本不写选项行：有截图就补成 A. A … D. D（选项看图）
        if "![[" in q["stem"] and not any(q["options"].values()):
            q["options"] = {k: k for k in "ABCD"}
        if set(q["options"]) != set("ABCD"):
            q["problems"].append("复盘文件里选项不全")
    return sorted(out, key=lambda q: q["num"])


# ---------------------------------------------------------------- 中间稿
def block(q):
    """中间稿的一道题。比题库多了 板块 / 来源 / 检查 三个小节，入库时去掉"""
    opts = "\n".join("%s. %s" % (k, q["options"].get(k, "")) for k in "ABCD")
    return ("## 题目 %s\n### 板块\n%s\n### 知识点\n%s\n### 来源\n%s\n### 题干\n%s\n### 选项\n%s\n### 答案\n%s\n"
            "### 解析\n%s\n### 检查\n%s\n" % (q["id"], q["board"], q["topic"], q["source"], q["stem"], opts,
                                            q["answer"] or TODO, TODO, "\n".join("⚠ " + p for p in q["problems"])))


def prepare(args):
    src = Path(args.input).expanduser()
    if not src.exists():
        sys.exit("找不到文件：%s" % src)
    vault = find_vault(args.vault)
    if src.is_dir():
        lines = ["第%s季 模考" % (re.search(r"第(\d+)季", src.name) or [0, "0"])[1]]
    else:
        lines = clean_lines(read_input(src))
    source, code, season = detect_source(lines)
    if args.source is not None:
        source = args.source.strip()
        code = args.id_prefix or re.sub(r"[^\w\u4e00-\u9fff]", "", source.replace("模考", "").replace("年", ""))
    fenbi = src.is_dir() or sum("正确答案" in ln for ln in lines) >= 5
    review = src if src.is_dir() else None
    if season and not review:
        d = vault / "FB模考试卷复盘" / "板块复盘" / ("第%d季" % season)
        if any(d.glob("[0-9][0-9]-*.md")):
            review = d
            print("找到第%d季的板块复盘（%s），直接用它：比 OCR 文字准确，还带截图" % (season, d))
    if review:
        qs = parse_review(review)
    else:
        qs = parse_fenbi(lines) if fenbi else parse_book(lines)
        if fenbi:
            for q in qs:  # 粉笔 OCR 的文字顺序会错乱，每题都要对照原文核对
                q["problems"].append("OCR 顺序可能错乱：对照原文核对题干开头结尾、四个选项")
    if not qs:
        sys.exit("一道题也没拆出来：请确认文件是题目文字（OCR 结果），不是扫描图片")
    name = args.name or source or args.id_prefix or src.stem
    if not code:
        code = args.id_prefix or re.sub(r"[^\w\u4e00-\u9fff]", "", name)[:12] or "导入"
    shot_dir = None
    if season:
        d = vault / "FB模考试卷复盘" / "板块复盘" / ("第%d季" % season) / "attachments"
        shot_dir = d if d.is_dir() else None
    from collections import Counter as _C
    known = _C(q["board"] for q in qs if q["board"] and q["board"] != UNSORTED)
    if not fenbi and known and (known["论证逻辑"] + known["形式逻辑"]) * 2 > sum(known.values()):
        for q in qs:   # 逻辑类练习册：问法认不出时按选项样子判断
            if q["board"] in ("", UNSORTED):
                q["board"] = board_by_options(q["options"]) or UNSORTED
    for q in qs:
        q["id"] = "%s-%03d" % (code, q["num"]) if fenbi else "%s-%02d-%02d" % (code, q["group"], q["num"])
        if args.board:
            q["board"] = ALIAS.get(args.board, args.board)
        # 知识点只给猜测，必须由 AI/用户确认后改掉“待分类”才能入库（保证每道题都核对过）
        guess = guess_topic(q["board"], q["stem"])
        q["topic"] = UNSORTED if guess == UNSORTED else "%s（猜：%s）" % (UNSORTED, guess)
        q["source"] = source
        # 模考截图（xingce-mokao-split 拆 PDF 时生成）：题目图 S36-Q066.png，材料图 S36-M111-115.png
        if shot_dir and not review:
            shots = [p.name for p in sorted(shot_dir.glob("S%d-M*.png" % season))
                     if (lambda m: m and int(m.group(1)) <= q["num"] <= int(m.group(2)))(
                         re.match(r"S\d+-M(\d+)-(\d+)", p.name))]
            shots += sorted(p.name for p in shot_dir.glob("S%d-Q%03d*.png" % (season, q["num"])))
            if shots:
                q["stem"] += "\n" + "\n".join("![[%s]]" % x for x in shots)
        if q["board"] in IMAGE_BOARDS and "![[" not in q["stem"]:
            q["problems"].append("这类题要图：请把题图保存到 训练/题库/图片/%s/%s.png（有模考截图时入库会自动复制）"
                                 % (q["board"], q["id"]))
        if q["board"] in SHARED_BOARDS and not review:
            q["problems"].append("共用材料：同组每道题的题干都要带上材料（文字或图片）")
        if q["board"] == UNSORTED:
            q["problems"].append("没认出板块")
        if fenbi and not q["answer"]:
            q["problems"].append("没读到正确答案")
        if len(q["stem"]) < 8 and q["board"] not in IMAGE_BOARDS | {"类比推理"}:
            q["problems"].append("题干太短，可能拆错了")
    out = bank_dir(vault) / "_待入库" / (re.sub(r'[\\/:*?"<>|]', "_", name) + ".md")
    if out.exists() and not args.force:
        sys.exit("中间稿已存在：%s\n（可能上次还没提交完。要重新拆就加 --force，会覆盖它）" % out)
    head = ("---\n来源: %s\n原文件: %s\n题数: %d\n---\n# 待入库：%s\n\n"
            "> 每道题核对：板块、知识点（不能是“待分类”）、题干、四个选项、答案；改好后把“### 检查”下面清空。\n"
            "> 然后运行 `python tiku.py commit \"本文件\"`：就绪的题进题库，没就绪的留在这里。答案不知道可以留“%s”。\n\n"
            % (source or "（无）", src.name, len(qs), name, TODO))
    write_lf(out, head + "\n".join(block(q) for q in qs))
    from collections import Counter
    c = Counter(q["board"] for q in qs)
    bad = sum(bool(q["problems"]) for q in qs)
    print("格式：%s；来源：%s；共拆出 %d 题" % ("粉笔模考" if fenbi else "练习册", source or "（无）", len(qs)))
    print("板块：" + "，".join("%s %d" % kv for kv in c.most_common()))
    print("需要核对：%d 题（看每题的“### 检查”）" % bad)
    if fenbi:
        nums = [q["num"] for q in qs]
        print("题号：1-%d（国考行政执法类/地市级 130 题，副省级 135 题）" % max(nums))
    else:
        print("练习套数：%d；有答案的题：%d（练习册通常没有答案，可用 answers 子命令补）"
              % (max(q["group"] for q in qs), sum(bool(q["answer"]) for q in qs)))
    if season and not shot_dir:
        print("提示：没找到第%d季模考截图（FB模考试卷复盘/板块复盘/第%d季/attachments）。"
              "图形推理、资料分析要图：先用 xingce-mokao-split 拆一遍 PDF 就会有截图。" % (season, season))
    print("中间稿：%s" % out)


# ---------------------------------------------------------------- 读中间稿 / 题库
HEAD_RE = re.compile(r"^##\s+题目\s+(.+?)\s*$", re.M)


def parse_blocks(text):
    text_wo_code = re.sub(r"^```[^\n]*\n.*?^```[^\n]*$", lambda m: " " * len(m.group(0)), text, flags=re.M | re.S)
    heads = list(HEAD_RE.finditer(text_wo_code))
    out = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[h.end():end]
        fields = {}
        parts = list(re.finditer(r"^###\s+(\S+)\s*$", body, re.M))
        for j, p in enumerate(parts):
            fields[p.group(1)] = body[p.end():parts[j + 1].start() if j + 1 < len(parts) else len(body)].strip()
        out.append({"id": h.group(1).strip(), "fields": fields, "start": h.start(), "end": end})
    return out


def parse_opts(s):
    opts = {}
    for m in re.finditer(r"^\s*([A-D])[\.．、)）]\s*(.*)$", s or "", re.M):
        opts[m.group(1)] = m.group(2).strip()
    return opts


def existing(bank):
    """所有题库里已有的 编号 和 题干指纹（跨板块查重：同一道题不会进两个题库）"""
    ids, stems = {}, {}
    for f in bank.glob("*真题.md"):
        for b in parse_blocks(f.read_text(encoding="utf-8-sig")):
            board = f.name[:-len("真题.md")]
            ids[(board, b["id"])] = f.name
            k = norm_stem(b["fields"].get("题干", ""), parse_opts(b["fields"].get("选项")))
            if len(k) >= 12:
                stems[k] = "%s %s" % (f.name, b["id"])
    return ids, stems


def bank_block(b, board, stem):
    f = b["fields"]
    opts = parse_opts(f.get("选项"))
    ans = (f.get("答案") or "").strip().upper()
    return ("## 题目 %s\n### 知识点\n%s\n### 题干\n%s\n### 选项\n%s\n### 答案\n%s\n### 解析\n%s\n\n"
            % (b["id"], f.get("知识点", "").strip(), stem,
               "\n".join("%s. %s" % (k, opts[k]) for k in "ABCD"),
               ans if re.fullmatch(r"[A-D]", ans) else TODO, f.get("解析", "").strip() or TODO))


def commit(args):
    stage = Path(args.input).expanduser()
    if not stage.is_file():
        sys.exit("找不到中间稿：%s" % stage)
    vault = find_vault(args.vault)
    bank = bank_dir(vault)
    text = stage.read_text(encoding="utf-8-sig")
    blocks = parse_blocks(text)
    ids, stems = existing(bank)
    add, keep, dup, why = {}, [], [], {}
    for b in blocks:
        f = b["fields"]
        board = ALIAS.get(f.get("板块", "").strip(), f.get("板块", "").strip())
        reasons = []
        if board not in BOARDS:
            reasons.append("板块“%s”不是试炼塔的板块" % board)
        if not f.get("知识点", "").strip() or UNSORTED in f.get("知识点", ""):
            reasons.append("知识点待分类")
        if f.get("检查", "").strip():
            reasons.append("检查未清空")
        opts = parse_opts(f.get("选项"))
        if set(opts) != set("ABCD") or not all(opts.values()):
            reasons.append("选项不全")
        if not f.get("题干", "").strip():
            reasons.append("题干为空")
        if reasons:
            keep.append(b)
            why[b["id"]] = reasons
            continue
        stem = f["题干"].strip()
        source = f.get("来源", "").strip()
        if source and source not in ("（无）", "无") and not stem.startswith("（" + source):
            # 来源写在题目最前面；题干以图片开头时来源单独一行，图片才能正常显示
            stem = "（%s）%s%s" % (source, "\n" if stem.startswith("![[") else "", stem)
        stem, missing = place_images(vault, bank, board, b["id"], stem, args.dry_run)
        key = norm_stem(stem, parse_opts(f.get("选项")))
        if (board, b["id"]) in ids or (len(key) >= 12 and key in stems):
            dup.append("%s（已在 %s）" % (b["id"], ids.get((board, b["id"])) or stems.get(key)))
            continue
        if missing:
            print("⚠ %s 缺图：%s" % (b["id"], "、".join(missing)))
        add.setdefault(board, []).append(bank_block(b, board, stem))
        ids[(board, b["id"])] = board
        if len(key) >= 12:
            stems[key] = b["id"]
    for board, items in add.items():
        f = bank / (board + "真题.md")
        old = f.read_text(encoding="utf-8-sig") if f.exists() else "# %s真题\n\n" % board
        if not args.dry_run:
            write_lf(f, old.rstrip("\n") + "\n\n" + "\n".join(items))
        print("%s %s：+%d 题" % ("（试运行）" if args.dry_run else "已写入", f.name, len(items)))
    if dup:
        print("跳过重复 %d 题：%s" % (len(dup), "；".join(dup[:10]) + (" …" if len(dup) > 10 else "")))
    if keep:
        print("还没就绪 %d 题（留在中间稿）：" % len(keep))
        for b in keep[:15]:
            print("  %s：%s" % (b["id"], "、".join(why[b["id"]])))
        if len(keep) > 15:
            print("  ……")
    if not args.dry_run:
        head = text[:blocks[0]["start"]] if blocks else text
        if keep:
            write_lf(stage, head + "".join(text[b["start"]:b["end"]] for b in keep))
        else:
            stage.unlink()
            print("中间稿已全部入库，已删除：%s" % stage.name)


def place_images(vault, bank, board, qid, stem, dry):
    """题干里的模考截图 ![[S36-Q066.png]] 复制到 训练/题库/图片/<板块>/ 并改成题库自己的路径；返回 (新题干, 缺的图)。
    命名：题目图 <编号>.png（多张时 <编号>-2.png…）；共用材料图 <编号前缀>-M111-115.png（同组几道题共用一张）"""
    missing = []
    att_root = vault / "FB模考试卷复盘"
    img_dir = bank / "图片" / board
    prefix = qid.rsplit("-", 1)[0]
    seq = [0]

    def repl(m):
        name = m.group(1).strip()
        if name.startswith("训练/"):
            if not (vault / name).is_file():
                missing.append(name)
            return m.group(0)
        base = Path(name).name
        hits = [p for p in [vault / name, img_dir / base] if p.is_file()]
        if not hits and att_root.is_dir():
            hits = list(att_root.rglob(base))
        mat = re.match(r"S\d+-(M\d+-\d+)", base)
        if mat:
            new = img_dir / ("%s-%s%s" % (prefix, mat.group(1), Path(base).suffix))
        else:
            seq[0] += 1
            new = img_dir / ("%s%s%s" % (qid, "" if seq[0] == 1 else "-%d" % seq[0], Path(base).suffix or ".png"))
        if not hits:
            missing.append(base)
            return m.group(0)
        if not dry and not new.exists():
            img_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(hits[0], new)
        return "![[%s]]" % new.relative_to(vault).as_posix()

    stem = re.sub(r"!\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", repl, stem)
    if board in IMAGE_BOARDS and "![[" not in stem:
        want = "训练/题库/图片/%s/%s.png" % (board, qid)
        if not dry:
            img_dir.mkdir(parents=True, exist_ok=True)
        stem += "\n![[%s]]" % want
        if not (vault / want).is_file():
            missing.append(want)
    return stem, missing


# ---------------------------------------------------------------- 补答案
def parse_key(s):
    """支持 “1-5 ABCDA”“1.A 2.B”“1A2B” “ABCDA BCDAB”（从 1 连续） 几种写法，返回 {题号: 字母}"""
    key = {}
    for m in re.finditer(r"(\d+)\s*[-~—–至]\s*(\d+)\s*[:：.．]?\s*([A-Da-d\s]+)", s):
        a, b = int(m.group(1)), int(m.group(2))
        letters = re.sub(r"\s", "", m.group(3)).upper()[:b - a + 1]
        for i, x in enumerate(letters):
            key[a + i] = x
    if key:
        return key
    for m in re.finditer(r"(\d+)\s*[\.．、:：]?\s*([A-Da-d])(?![A-Za-z])", s):
        key[int(m.group(1))] = m.group(2).upper()
    if key:
        return key
    letters = re.sub(r"[^A-Da-d]", "", s).upper()
    return {i + 1: x for i, x in enumerate(letters)}


def answers(args):
    target = Path(args.input).expanduser()
    if not target.is_file():
        sys.exit("找不到文件：%s" % target)
    src = Path(args.key).expanduser()
    keytext = src.read_text(encoding="utf-8-sig") if src.is_file() else args.key
    key = parse_key(keytext)
    if not key:
        sys.exit("没读出答案（支持 “1-5 ABCDA” “1.A 2.B” 或一串 ABCD）")
    text = target.read_text(encoding="utf-8-sig")
    n = 0
    for b in reversed(parse_blocks(text)):
        if not b["id"].startswith(args.prefix + "-"):
            continue
        tail = b["id"][len(args.prefix) + 1:]
        if not tail.isdigit() or int(tail) not in key:
            continue
        seg = text[b["start"]:b["end"]]
        new = re.sub(r"(^###\s+答案\s*\n)(.*?)(?=^###|\Z)", lambda m: m.group(1) + key[int(tail)] + "\n",
                     seg, count=1, flags=re.M | re.S)
        if new != seg:
            text = text[:b["start"]] + new + text[b["end"]:]
            n += 1
    if not args.dry_run:
        write_lf(target, text)
    print("%s补了 %d 题的答案（编号前缀 %s，答案表 %d 个）" % ("（试运行）" if args.dry_run else "", n, args.prefix, len(key)))


def main():
    ap = argparse.ArgumentParser(description="真题入库：OCR txt → 试炼塔题库")
    ap.add_argument("--vault", help="库根目录（含“训练”文件夹）；不填就按脚本位置找")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare", help="拆题，写中间稿")
    p.add_argument("input")
    p.add_argument("--source", help="试卷来源，写在题目前的括号里，如 “粉笔第36季模考”“2025年国考”；传空字符串表示没有来源")
    p.add_argument("--id-prefix", help="题目编号前缀（默认按来源生成，如 粉笔36季）")
    p.add_argument("--board", help="整份都是同一板块时直接指定（如 论证逻辑）")
    p.add_argument("--name", help="中间稿文件名")
    p.add_argument("--force", action="store_true", help="覆盖已存在的中间稿")
    p.set_defaults(fn=prepare)
    c = sub.add_parser("commit", help="把中间稿里就绪的题写进题库")
    c.add_argument("input")
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(fn=commit)
    a = sub.add_parser("answers", help="按答案表补答案")
    a.add_argument("input")
    a.add_argument("key", help="答案文本或答案文件")
    a.add_argument("--prefix", required=True, help="编号前缀，如 四海逻辑600-03（第 3 套）")
    a.add_argument("--dry-run", action="store_true")
    a.set_defaults(fn=answers)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
