# -*- coding: utf-8 -*-
"""一次性体检：runbook 的表格列数、成对记号、被引用文件是否存在、章节是否齐。

用法（第二参是"按哪个目录查文件存在性"，默认取说明所在目录；变异副本写到 %TEMP% 时要显式给）：
  PYTHONIOENCODING=utf-8 python 验收\\check_runbook.py 原生玻璃版-说明.md
证伪器（往说明的副本里注若干"合理 bug"，要求每条都变红并点到管它的那条规则；条数由证伪器自己打印）：
  PYTHONIOENCODING=utf-8 python 验收\\falsify_check_runbook.py
"""
import io, os, re, sys

# 兜住 GBK 控制台／重定向：这份体检的每条红话里都带中文正文与 ⇒ 类符号，崩在打印
# 判决那一行会让 rc=1 被误读成"闸门判红"（详见 check_cited_md5.py 同段注释）。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if len(sys.argv) < 2:
    raise SystemExit("REFUSE：第一个参数＝要体检的说明文件（不给就报错，绝不默认去改盘上的东西）")
P = sys.argv[1]
if not os.path.isfile(P):
    raise SystemExit("REFUSE：要体检的文件不存在：%s" % P)
t = io.open(P, encoding="utf-8").read()
lines = t.split("\n")
bad = []

# 0) 先划出围栏代码块：块内的行不参与"表格列数／记号成对"的判断（命令示例里
#    出现 | 和 ** 是正常的，把它们当 markdown 数一遍只会造出假红）。
fenced = set()
_depth = 0
for n, l in enumerate(lines, 1):
    if l.strip().lstrip(">").strip().startswith("```"):
        _depth ^= 1
        continue
    if _depth:
        fenced.add(n)

# 1) 表格：每张表列数一致，且第二行是分隔行
i = 0
while i < len(lines):
    if lines[i].startswith("|") and (i + 1) not in fenced:
        blk = []
        while i < len(lines) and lines[i].startswith("|") and (i + 1) not in fenced:
            blk.append((i + 1, lines[i]))
            i += 1
        widths = [(n, len(r.replace("\\|", "@").split("|")) - 2) for n, r in blk]
        ws = set(w for _, w in widths)
        if len(ws) != 1:
            bad.append("table@%d 列数不一致 %s" % (blk[0][0], widths))
        if len(blk) >= 2 and set(blk[1][1].replace("|", "").replace("-", "")
                                 .replace(":", "").strip()) != set():
            bad.append("table@%d 第二行不是分隔行: %r" % (blk[0][0], blk[1][1][:60]))
        if len(blk) < 3:
            bad.append("table@%d 行数<3" % blk[0][0])
    else:
        i += 1

# 2) 行内 ** 与反引号成对（跳过 ``` 围栏行：每行三个反引号本来就是奇数）
#    粗体只在"代码跨度之外"数：`**` 是文档在**描述**这个记号，不是要把这半行加粗。
for n, l in enumerate(lines, 1):
    if n in fenced or l.strip().lstrip(">").strip().startswith("```"):
        continue
    if l.count("`") % 2:
        bad.append("backtick 不成对 @%d: %s" % (n, l[:90]))
    naked = re.sub(r"`[^`]*`", "", l)
    if naked.count("**") % 2:
        bad.append("bold 不成对 @%d: %s" % (n, naked[:90]))

# 3) 引用到的 验收 脚本必须盘上存在
names = set(re.findall(r"[\\\\/]([A-Za-z_0-9]+\.(?:py|sh|cs|md|vbs|bat|html|exe))", t))
ROOT = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(P))
have = set(os.listdir(ROOT))
for sub in (u"验收", "native", "docs"):
    d = os.path.join(ROOT, sub)
    if os.path.isdir(d):
        have |= set(os.listdir(d))
# 3b) 仓库外的绝对路径（解释器本身、Kaggle 侧那份脚本、Salt Player 那一路……）。
#     旧版把这类一律报成"提到但盘上没有"，于是"正文编了一个名字"与"这文件本来就在仓库外、
#     而且真在盘上"共用同一句红话，读的人分不开（2026-10-15 那 5 条红就是这么来的，它们把
#     总闸堵死）。现在按**正文里那条绝对路径**回盘上核：expandvars 之后 exists ⇒ 绿，并计数点名；
#     给了绝对路径但盘上没有 ⇒ 报「绝对路径盘上没有」；正文只给缩写或 <占位符> ⇒ 报「没给可核对的绝对路径」。
#     缩写算红是故意的：证据面写不出能核对的路径，就不许躲在"你看不到、但我没编"后面。
ABS = re.compile(r"[A-Za-z]:[\\/][^`|<>\"'\s]*")
STRIP = u"，。；、：）)]}】"
cands = {}
for mm in ABS.finditer(t):
    p = mm.group(0).rstrip(STRIP)
    if not os.path.splitext(p)[1]:
        continue                                  # 没有扩展名＝那是目录名，不是被引用的文件
    cands.setdefault(p.replace("\\", "/").rsplit("/", 1)[-1], []).append(p)
abs_ok = []
for nm in sorted(names):
    if nm in have:
        continue
    cs = cands.get(nm) or []
    hit = [p for p in cs if os.path.exists(os.path.expandvars(p))]
    if hit:
        abs_ok.append(nm)
    elif cs:
        bad.append(u"提到但盘上没有（仓库外绝对路径回盘上核不到）: %s ｜正文试过: %s"
                   % (nm, u" ；".join(cs[:2])))
    else:
        bad.append(u"提到但盘上没有（仓库内三处目录没有，正文也没给可核对的绝对路径——"
                   u"写成 …\\x.py 或 <占位符> 一律算这条）: %s" % nm)
print("3b 仓库外绝对路径核过 %d 条：%s" % (len(abs_ok), u"、".join(abs_ok) if abs_ok else u"（无）"))
fences = [n for n, l in enumerate(lines, 1) if l.strip().lstrip(">").strip().startswith("```")]
if len(fences) % 2:
    bad.append("``` 围栏行数为奇数（%d 个），有一处没闭合：%s" % (len(fences), fences))

# 4) 章节齐（缺口 4 指向 §8）——按 "## <n>." 精确匹配，"## 8x." 这种顶不了
heads = [l for l in lines if l.startswith("## ")]
for need in ("5", "6", "7", "8"):
    if not any(re.match(r"^## %s\." % need, h) for h in heads):
        bad.append("缺章节 ## %s." % need)

# 5) C6 编码口径：文档里**裸写**（不带 PYTHONIOENCODING 前缀）的 `python X.py`，
#    如果 X 的源码里出现 ⇒（GBK 控制台／重定向下打印它就崩在判决那一行，rc=1 长得
#    像"闸门判红"——2026-10-09T18:24Z 在四份锁屏量具上实测过），那 X 就必须自己兜住
#    输出编码（stdout.reconfigure），否则这条命令红：要么补前缀，要么给脚本加兜底。
#    只看代码语境（围栏块 + 行内反引号跨度），散文里提到的文件名不归这条管（存在性归第 3 条）。
ARROW = u"⇒"
SEARCH_DIRS = [ROOT, os.path.join(ROOT, u"验收"), os.path.join(ROOT, "native"),
               os.path.join(ROOT, "docs")]
_cache = {}
c6_cmds = 0
for n, l in enumerate(lines, 1):
    if n in fenced:
        ctx = [(n, l)]
    elif l.lstrip().startswith("```"):
        ctx = []
    else:
        ctx = [(n, s) for s in re.findall(r"`[^`\n]+`", l)]
    for _, s in ctx:
        for m in re.finditer(r"python\s+([^\s`|'\"<]+\.py)", s):
            c6_cmds += 1
            head = s[max(0, m.start() - 30):m.start()]
            if "PYTHONIOENCODING" in head:
                continue
            base_py = os.path.basename(m.group(1).replace("\\", "/").rstrip("/"))
            path = None
            for d in SEARCH_DIRS:
                cand = os.path.join(d, base_py)
                if os.path.isfile(cand):
                    path = cand
                    break
            if path is None:
                continue                     # 盘上没有＝第 3 条已经报了，这里不再叠一条
            if base_py not in _cache:
                _cache[base_py] = io.open(path, encoding="utf-8", errors="replace").read()
            src = _cache[base_py]
            if ARROW in src and "reconfigure" not in src:
                bad.append("C6 编码口径 @%d：`python %s` 裸写，而 %s 会打印 ⇒ 又没自带兜底"
                           "（GBK 控制台下 rc=1 会被读成闸门判红）——补 PYTHONIOENCODING=utf-8 前缀，"
                           "或让脚本自己 reconfigure" % (n, m.group(1), base_py))
print("C6 看了 %d 条命令（裸写的都要么自带兜底、要么不打印 locale 编不了的东西）" % c6_cmds)
print("\n".join(heads))
print("PROBLEMS: %d" % len(bad))
for x in bad:
    print(" -", x)
sys.exit(1 if bad else 0)
