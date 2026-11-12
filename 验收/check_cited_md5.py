# -*- coding: utf-8 -*-
"""文档里手抄的哈希／字节数／时间戳，逐个回到盘上重算一遍。

为什么要有这一份：说明文档里的 md5、size、mtime 都是**手抄**的，抄一次就多一个
"必须重跑才不滞后"的包袱（本项目已经抓到过 `+231` vs 盘上 `+230.8`、
"2026-10-08 落盘" vs 文件 mtime `2026-10-07T06:15:10Z` 两起漂移）。
这个脚本把"文档说的那个值"和"盘上算出来的那个值"钉成机器不变式：不一致就红。

用法：
  PYTHONIOENCODING=utf-8 python 验收\\check_cited_md5.py 原生玻璃版-说明.md
  PYTHONIOENCODING=utf-8 python 验收\\check_cited_md5.py 原生玻璃版-说明.md --list
证伪器（往文档副本里逐条注合理的 bug，要求每条都变红并点到受影响那条的标签；
条数由证伪器自己打印，别在这里手抄——它一涨这里就滞后）：
  PYTHONIOENCODING=utf-8 python 验收\\falsify_check_cited_md5.py

口径（跑之前写死，改判据要连这份一起改）：
- 引用串允许写成截断前缀（文档里就是 `eae724f4c3c037e0…` 这种），所以判据是
  "文档里那串必须是盘上 md5 的前缀"，而不是"必须逐位相等"；但**留底副本**那条例
  外，要求全 32 位出现在文档里，因为它的用途是"原件被清掉后仍能证明副本没被换"。
- **"文档里存在这一串就算绿"是不够的**：同一个值在正文和台账各抄一遍时，漂掉的那处
  会被另一处兜住（证伪器连着两条变异就是这么 MISSED 的）。所以改成查**近漂族**：
  ① 凡以被钉哈希前 8 位起头的十六进制串，都必须是盘上 md5 的前缀；
  ② 凡"位数相同、只差末位"的 `N 字节`，都必须等于盘上 size；
  ③ 凡"同钟点、不同日期"的 `YYYY-MM-DDTHH:MM:SSZ`，都必须等于盘上 mtime。
- 时间戳的唯一出处＝**文件 mtime**（那份日志正文里没有自记时间戳）。表里钉的紧凑
  stamp 必须同时等于 mtime 的紧凑形式、出现在文件名里、且文档正文里有它的 ISO 写法。
- 文件不在盘上＝红，不去猜它是不是被临时目录扫了。
- 看门狗期限那条**现算**：取最新的 `veil_watcher-*.log` 首行里的"起始 UTC 秒 ＋
  deadline N h"，算出到期时刻，再要求文档正文出现那个 ISO 串。重挂一趟 watcher，
  期限就跟着这行日志走，抄不得。
- 同一个现算期限在文档里抄了三处（缺口 6／§7 台账／§8-①），所以这条也补了近漂族：凡"同日期＋同分秒、只差小时"的 ISO 串都必须等于现算值。上一版只判"这一串在不在文档里"，证伪器的"抄错一小时"那条变异因此被另外两处手抄兜住 ⇒ MISSED（本轮给第 8 条尺子加变异时，这条自己就被证伪器判成 MISSED，实测到的）。
- 陈旧值清单里的字符串一旦重新出现在文档里＝红（订正过的手抄值不许漂回来）。
- 文档里那句"§5b 消融目前 0 行真数据"同样是手抄断言：往盘上每份 "veil-paint-*.md" 里数数据行，数得出行而文档还自称 0 行＝红；文档自称 0 行时必须点名盘上**最新**那份报告的文件名＝红话之外再加一条防"凭印象引旧那份"。报告份数不进判据（看门狗还在跑，钉死它就等于再造一处会滞后的数）。
- 文档里点名过的报告文件名本身也要在盘上数得出（凭印象编一个格式正确的 stamp＝红；被清理掉也是红＝证据断链）。
- 上面这条的"数据行"谓词自带已知答案对照（表头＋分隔行必须数成 0、加一条真形状行必须数成 1），对照失限时后面那些结论一律标"不作数"——不许用一把没校准的尺子判绿。
- "#37 跑到哪一步"同样是手抄状态句 ⇒ 回盘上的 `FINAL-veil-*.md` 核三件事：文档点名过的那份必须在产物目录里数得出；必须点名按文件名排序**最新**那份；最新那份自记「未产出」（＝看门狗到期限没等到就绪桌面，实验一行没跑）时文档必须把"没等到就绪桌面"这句话说出来。第三档在盘上还没有真样本，所以它靠的是 `fin_newest_hit`／`fin_claimed` 两条纯函数各自的已知答案对照（含"引了旧那份要红""已交底要绿""盘上没 FINAL 时不许硬报警"），而不是文档级变异——这条比变异证伪弱，正文里也照这么交底。
- 第 8 条把上面那两处的『点名过的文件要在盘上数得出』收成通用尺：凡文档用反引号点名、且名字里带紧凑 UTC 时间戳（8 位日期 T 6 位时刻 Z）的产物，其 basename 必须在仓库根或产物目录里**逐字符**存在；带 <占位>／通配的模板不算。它专治这一类：留底 stdout 的秒位被手抄成相邻一秒——扩展名、日期、时长、前缀全对，而『同族里有没有文件』这种兜底判据会把它洗成绿，所以这条**明确不许同族兜底**。只管反引号里的名字，散文里裸写的文件名不归它管（口径在正文交底）。
- 已知碰撞（不靠放宽判据绕开）：`exp_backdrop_source.py` 那条只钉 md5＋mtime、**不钉字节数**，因为文档里 15099（改后）与 15090（改动前按字节留底）是一对只差末位的**合法**值，规则②『同长度只差末位＝漂』会把这对真值判红。md5 才是那把尺的身份证；字节数交给第 8 条（留底文件必须存在）＋报告自记 md5 两条一起管。同档第二例：`cmp6x2-b3b4.out` 2429 与 `cmp6x2-b2b4.out` 2427 是**两个不同文件**的相邻字节数，也会撞规则② ⇒ 后一条同样不钉字节（文档那一格写"（不钉，见上面的例外说明）"）。
- ④⑤ 的出处清单（17 行）整张登记在 `CITED` 里，所以文档那张表里每个数都必须等于盘上现算值；文件名里的紧凑 stamp 是**启动**时刻、mtime 是**落盘**时刻，两者本来就差几分钟，故这批不传 `stamp`（"带戳文件名要在盘上数得出"归第 8 条管）。
- 第 9 条管**历史值**：一份字节被后来改动顶掉之后，"回盘上重算"对它不成立，而正文仍要留着它（它是旧那批读数的归属前提）。这一条改成回**当时那份体检留底**重算——留底行里的 `disk=`／`bytes=` 才是旧值的出处，文档抄的那串必须是它的前缀、字节数必须逐位相同；同一个旧值抄两遍漂一处由"互不为前缀"那把近漂尺抓。判它之前先跑五条已知答案对照（真形状要过、哈希末位漂要红、字节末位漂要红、留底取不到行要红、多行里挑错行要红），对照一失灵就把结论整条标"不作数"。它比 CITED 那批弱一档：留底本身只记到 16 位，所以这条只能证"文档抄的 == 留底记的"，不能证"留底记的 == 当年那份字节"（当年没留底＝缺口 8 那一类）。
"""
import datetime as dt
import glob
import hashlib
import io
import os
import re
import sys
import time

# 本机控制台与"重定向到文件"默认走 GBK，而这份报告会打印 ⇒、文档里带回来的 U+FFFD、
# 以及各类中文正文。不兜住就可能恰好崩在**打印判决的那一行**上：rc=1 看着像"闸门判红"，
# 其实是量具自己没跑完（2026-10-09T18:17Z 实测：同一条命令输出接终端是 rc=0，`> 文件`
# 就抛 UnicodeEncodeError）。标准入口照文件头带 PYTHONIOENCODING=utf-8，这里再兜一层，
# 让"怎么调用它"不影响它算出来的数。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))

if len(sys.argv) < 2:
    raise SystemExit("REFUSE：第一个参数＝要体检的说明文件（不给就报错，绝不默认去改盘上的东西）")
args = [a for a in sys.argv[1:] if not a.startswith("--")]
LIST = "--list" in sys.argv
P = args[0]
if not os.path.isfile(P):
    raise SystemExit("REFUSE：要体检的文件不存在：%s" % P)
# 第二参＝"按哪个目录解相对路径"。变异副本写在产物目录里时必须显式给仓库根，
# 否则三条引用会一起变 MISSING，报告就分不清"哪条规则失效"和"副本放错了地方"。
ROOT = os.path.abspath(args[1] if len(args) > 1 else os.path.dirname(P))
t = io.open(P, encoding="utf-8").read()


def expand(p):
    """支持文档里那种 %LOCALAPPDATA% / %TEMP% 写法；根目录相对路径按 ROOT 解。"""
    p = os.path.expandvars(p)
    return p if os.path.isabs(p) else os.path.abspath(os.path.join(ROOT, p))


def md5_of(path):
    b = open(path, "rb").read()
    return hashlib.md5(b).hexdigest(), len(b)


ART = os.path.join(os.environ.get("LOCALAPPDATA", ""), "fq-glass-verify")
ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
LED_HDR = u"9e 出处表"


# ── 第 10 条：§9e 那张表就是台账，别再抄一份"期望值"进脚本（2026-10-15 改） ────────
# 为什么改（先答三问）：它为何存在＝把正文里手抄的身份证绑回盘上；前提还在吗＝**一半不在了**，
# 这一批的数（页面字节、两把计时尺、语法闸门…）每轮都动，而旧写法是在这里的 CITED 里再手抄
# 一遍期望值 ⇒ 同一个数有两处期望，盘上动一次要改两处，漏一处就红。本轮 7 条红里 6 条正是
# 这个形状：文档已经跟着本轮更新，脚本还钉着上一轮的值。谁接班＝这一条：期望值由**表本身**
# 供（读出来），真值仍由**盘上**供（现算），判据一项没少（md5 前缀／字节／落盘 ISO 三件照旧
# 逐行核），而且"表里少写一格／行不是 5 格"这种形状以前根本看不见，现在会红。
# 覆盖边界（不假装核过）：**整行被删掉**时这一条看不见——那一行不再是一句 assertion；
# 它留下的文件名若带紧凑 UTC 戳，仍由第 8 条（带戳产物名）在盘上要着。
def ledger_body(doc_text):
    """§9e 表的数据行（列头行与 |---| 分隔行都不算）。整节不存在回 None＝这条尺失明。"""
    lines = doc_text.split("\n")
    head = None
    for k, ln in enumerate(lines):
        if LED_HDR in ln:
            head = k
            break
    if head is None:
        return None
    out, started = [], False
    for ln in lines[head + 1:]:
        s = ln.strip()
        if not s.startswith("|"):
            if started:
                break
            continue
        if s and set(s) <= set("|-: "):
            started = True
            continue
        if started:
            out.append(s)
    return out


def ledger_target(name, marker):
    """名字＋表里的目录标注 → (给 expand 用的路径写法, 歧义红话或 None)。
    未标目录时**两边都试**：只有一边命中就用它；两边都命中＝歧义（宁可红，不猜）；
    两边都没有＝交给主循环报 MISSING（它点名的是仓库根那份写法）。"""
    if marker == u"产物":
        return os.path.join(ART, name), None
    if marker in (u"交付", u"仓库"):
        return os.path.join(ROOT, name), None
    in_root = os.path.isfile(os.path.join(ROOT, name))
    in_art = os.path.isfile(os.path.join(ART, name))
    if in_root and in_art:
        return os.path.join(ROOT, name), u"同名文件在仓库根与产物目录都数得出，而表里这行没标目录"
    return os.path.join(ROOT if in_root else ART, name), None


def ledger_row(line):
    """一行 → dict。skip＝这一行按设计不归这条尺管（why 为空＝正常跳过；
    why 非空＝形状不对，该红）。ok 形状时给（标签, 路径写法, md5, 字节, ISO）。"""
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cells) != 5:
        return {"skip": True, "why": u"这一行不是 5 格（实数 %d 格）＝表形状变了" % len(cells)}
    nm = cells[0]
    f = re.search(r"`([^`\n]+)`", nm)
    if not f:
        # 出处格没点名文件＝钉的是"已不在盘上的旧值"那一类，由 HIST 回留底对账
        return {"skip": True, "why": ""}
    name = f.group(1).strip()
    marker = u"产物" if u"产物目录" in nm else (u"交付" if u"交付目录" in nm else u"")
    if "\\" in name or "/" in name:
        marker = u"仓库"
    miss = []
    h = re.fullmatch(r"`?([0-9a-f]{12,32})`?", cells[1])
    b = re.search(r"(\d+) 字节", cells[2])
    z = ISO_RE.search(cells[3])
    if not h:
        miss.append(u"md5 那格不是 12–32 位十六进制（%s）" % (cells[1][:24] or u"空格"))
    if not b:
        miss.append(u"字节那格没有「N 字节」（%s）" % (cells[2][:24] or u"空格"))
    if not z:
        miss.append(u"落盘时刻那格没有 ISO 秒（%s）" % (cells[3][:30] or u"空格"))
    if miss:
        return {"skip": True, "why": u"点名的文件在，但这一行缺格：" + u"／".join(miss)}
    path, amb = ledger_target(name, marker)
    label = name.replace("\\", "/").rstrip("/").split("/")[-1] + u"〔9e〕"
    return {"skip": False, "why": amb or "", "label": label, "name": name, "path": path,
            "hash": h.group(1), "size": b.group(1), "iso": z.group(0)}


def ledger_problems(row, disk_hash, disk_size, disk_iso):
    """这一行抄的三个值 vs 盘上现算的三个值。纯函数，已知答案对照跑它。"""
    out = []
    if len(row["hash"]) < 12 or not disk_hash.startswith(row["hash"]):
        out.append(u"md5 那格 %s 不是盘上 %s 的前缀（长度还得 ≥12）"
                   % (row["hash"], disk_hash[:20] + "…"))
    if row["size"] != str(disk_size):
        out.append(u"字节那格 %s ≠ 盘上 %d" % (row["size"], disk_size))
    if row["iso"] != disk_iso:
        if row["iso"][11:] == disk_iso[11:]:
            out.append(u"落盘时刻那格 %s 与盘上 %s 同钟点不同日期（落盘日凭印象写错那一种）"
                       % (row["iso"], disk_iso))
        else:
            out.append(u"落盘时刻那格 %s ≠ 盘上 mtime %s" % (row["iso"], disk_iso))
    return out


_LCAL = []
_GOOD_ROW = (u"| `index.html`（交付目录） | d6d56eef70cc | 159469 字节 | "
             u"2026-10-15T18:23:01Z | 当前页面字节 |")
_r = ledger_row(_GOOD_ROW)
if _r.get("skip") or _r.get("label") != u"index.html〔9e〕" or _r.get("hash") != "d6d56eef70cc" \
        or _r.get("size") != "159469" or _r.get("iso") != "2026-10-15T18:23:01Z":
    _LCAL.append(u"真形状的那一行没被读成（标签,md5,字节,ISO）：%r" % (_r,))
if ledger_row(u"| `a.txt` | d6d56eef70cc | 159469 字节 | 2026-10-15T18:23:01Z").get("why") \
        != u"这一行不是 5 格（实数 4 格）＝表形状变了":
    _LCAL.append(u"少一格的行没被点名")
if ledger_row(u"| 旧页面字节（已不在盘上） | 2a66cf56fd40 | 139085 字节 | 无 mtime 可对 | x |") != \
        {"skip": True, "why": ""}:
    _LCAL.append(u'没有反引号文件名的行被当成"该行坏了"（它按设计不归这条尺管）')
if u"md5" not in ledger_row(u"| `a.txt` | zz | 9 字节 | 2026-10-15T18:23:01Z | x |").get("why", ""):
    _LCAL.append(u"md5 那格是垃圾时没红")
if u"落盘时刻" not in ledger_row(u"| `a.txt` | d6d56eef70cc | 9 字节 | 无 | x |").get("why", ""):
    _LCAL.append(u"落盘时刻那格不是 ISO 时没红")
if not ledger_row(u"| `a.txt`（产物目录） | d6d56eef70cc | 9 字节 | 2026-10-15T18:23:01Z | x |") \
        ["path"].replace("\\", "/").endswith("fq-glass-verify/a.txt"):
    _LCAL.append(u"标了（产物目录）却没解到产物目录")
if ledger_row(u"| `验收\\x.js` | d6d56eef70cc | 9 字节 | 2026-10-15T18:23:01Z | x |")["path"] != \
        os.path.join(ROOT, u"验收\\x.js"):
    _LCAL.append(u"带目录前缀的写法没按仓库根解")
_H = "d6d56eef70ccca626a70" + "0" * 16
if ledger_problems(_r, _H, 159469, "2026-10-15T18:23:01Z"):
    _LCAL.append(u"真形状被判红（假阳性）")
if not ledger_problems(dict(_r, hash="d6d56eef70cd"), _H, 159469, "2026-10-15T18:23:01Z"):
    _LCAL.append(u"md5 末位漂一位没被判红")
if not ledger_problems(dict(_r, size="159468"), _H, 159469, "2026-10-15T18:23:01Z"):
    _LCAL.append(u"字节数漂一位没被判红")
if not ledger_problems(dict(_r, iso="2026-10-16T18:23:01Z"), _H, 159469, "2026-10-15T18:23:01Z"):
    _LCAL.append(u"落盘日漂一天没被判红")
# 零鉴别力对照：把这一条摆成"什么都判过"和"只看字节"两种坏法，真值表必须挑得出来
if [x for x in ("hash", "size", "iso")
        if not ledger_problems(dict(_r, **{x: {"hash": "zz", "size": "1", "iso": "9"}[x]}),
                               _H, 159469, "2026-10-15T18:23:01Z")]:
    _LCAL.append(u"某一格换成垃圾后仍然判绿＝那一格没牙")
if ledger_body(u"正文\n### 9e 出处表\n| 出处 | md5 | 字节 | 落盘 | 说明 |\n|---|---|---|---|---|\n"
               u"| a | b | c | d | e |\n\n散文\n| f | g | h | i | j |\n") != [u"| a | b | c | d | e |"]:
    _LCAL.append(u"表体取错了（列头／分隔行数进来，或表格结束后还在往里塞别处的表）")
if ledger_body(u"没有那一节") is not None:
    _LCAL.append(u"整节不存在时没回 None＝失明会被读成「零行、全绿」")
if _LCAL:
    bad_pre = [u"出处表这条尺子自己失明（%s）⇒ 它后面的结论不作数" % u"；".join(_LCAL)]
else:
    bad_pre = []


# 「同一个值抄两遍、漂了一处」那把近漂尺的**归属**版本（2026-10-15 补，起因是它自己咬了一口假的）：
# 旧写法把正文里**任何**一个"只差末位、同长度"的「N 字节」都读成"这一行抄错了"。可这一轮的表里
# 躺着两个不同文件的相邻字节数——`FINAL-surface-…md` 2477 与 `js_syntax_check.js` 2470——
# 于是它报"同值抄两遍漂了一处"，而盘上根本没有抄两遍。这是**判据的前提没了**（近漂⇒同值复制），
# 不是阈值太严：把阈值放宽会连真漂移一起放走，所以改的是判据——一个近漂的数要想不算漂移，
# 必须能回**盘上**找到归属：它是另一行的当前盘上值，那一行自己就印着那行的身份证，
# 而且那一行的字节数是**被这条尺核过**的（没核过的数不能替别的数背书＝文档里"那一格故意留空"的代价）。
def byte_occs(text):
    """正文里所有形如「N 字节」的读数 → [(那串数字, 它所在那一行)]（围栏与表格都算）。"""
    out = []
    for ln in text.split("\n"):
        for m in re.findall(r"(\d{3,9}) 字节", ln):
            out.append((m, ln))
    return out


def near_drift_hits(text, want, own_base, meta):
    """同长度、只差末位、且**回盘上找不到归属**的那些 → [(漂的数, 那一行)]。"""
    hits = []
    for m, ln in byte_occs(text):
        if m == want or len(m) != len(want) or m[:-1] != want[:-1]:
            continue
        owners = [r for r in meta if r["pins"] and r["size"] == m and r["base"] != own_base
                  and (r["base"] in ln or (r["hash"] and r["hash"] in ln))]
        if owners:
            continue
        hits.append((m, ln))
    return hits


_NCAL = []
_M = [{"base": u"c.js", "size": "2470", "hash": "3d67971ef4ef", "pins": True},
      {"base": u"b.out", "size": "2427", "hash": "3ca6541f7d98", "pins": False},
      {"base": u"a.out", "size": "2429", "hash": "36fcf9989c6e", "pins": True}]
_T1 = u"| `js_syntax_check.js` | 3d67971ef4ef | 2470 字节 | 2026-10-15T18:49:12Z | 语法闸门 |"
_T2 = u"散文里顺手写了一句 2470 字节，没点任何文件名"
_T3 = u"若把不钉的那格补全：3ca6541f7d98 ／ 2427 字节 ／ 2026-10-10T18:12:59Z"
if near_drift_hits(_T1, "2477", u"FINAL-surface.md", _M):
    _NCAL.append(u"跨文件引用（2470 是 c.js 那行自己印的、且那行核过字节）仍被判成漂移＝假阳性没修掉")
if len(near_drift_hits(_T2, "2477", u"FINAL-surface.md", _M)) != 1:
    _NCAL.append(u"没归属的近漂数没被点名＝这条尺被豁免条款掏空了")
if len(near_drift_hits(_T3, "2429", u"a.out", _M)) != 1:
    _NCAL.append(u"「没被核过的那行」替别人背了书＝pins 那道闸没牙（边界哨兵 S1 会失效）")
if near_drift_hits(u"x 2429 字节", "2429", u"a.out", _M):
    _NCAL.append(u"与盘上相同的那个值被判成漂移（假阳性）")
if near_drift_hits(u"x 247 字节／24700 字节", "2477", u"a.out", _M):
    _NCAL.append(u"长度不同的数被当成近漂（判据写错了）")
# 零鉴别力对照：只按"这个数是不是某个盘上值"豁免（不看那一行、不看那一行核没核过）
_loose = [m for m, ln in byte_occs(_T3)
          if m != "2429" and len(m) == 4 and m[:-1] == "242" and m in set(r["size"] for r in _M)]
if _loose == []:
    _NCAL.append(u'归属判据退化成了「这数在盘上存在吗」：b.out 那行明明没核字节也放行＝S1 那条哨兵迟早变绿')
if _NCAL:
    bad_pre.append(u"近漂归属这条尺子自己失明（%s）⇒ 它后面的结论不作数" % u"；".join(_NCAL))


# (标签, 路径写法, 期望：文档里出现的引用串, 该串的性质)
#   "full32"  → 文档必须带全 32 位，且等于盘上值
#   "prefix"  → 文档里那串必须是盘上 md5 的前缀（长度 >= 12 才够鉴别力）
#   "none"    → 只核对 size／stamp，不比哈希
CITED = [
    (u"原型日志留底副本",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify",
                  "probe_mica5-prototype-20261007T061510Z.log"),
     "b6c667ff2f8e3d3b4e5762892e1b8a7f", "full32",
     {"bytes": "17411 字节", "stamp": "20261007T061510Z"}),
    (u"实拍量具", u"验收\\shot_desktop.py", "eae724f4c3c037e0", "prefix", {}),
    # 页面身份证分成两条：当前那份字节由**下面第 10 条**从 §9e 那张表现读现核（旧写法是在
    # 这里再手抄一遍期望值，一轮改动要订正两处，本轮就是漏订正这一处红了 6 条）；历史那条
    # 交给下面的 HIST（那份字节已经不在盘上，只能回"当时那份体检留底"对账）。
    # 分开是因为一条判据只能比一个盘上真值：旧值留在正文里是**历史读数的前提**，
    # 它必须仍然可查，但不许冒充"当前页面"。
    # §8-① 里那句"exp_veil_paint.py（md5 …、23293 字节、mtime …）"是手抄的三件套：
    # 这份脚本一旦再动一个字节，那三个值全跟着变，而它们正是"看门狗要跑的那份量具"的身份证。
    (u"机制分拣量具（#37 那把尺）", u"验收\\exp_veil_paint.py", "2f9f9f7cec97", "prefix",
     {"bytes": True, "mtime": True}),
    # #40 那把尺（同一只材质在亮／暗壁纸屏位各起一次窗）。这份脚本是本轮**唯一动过的量具**
    # （格式串缺参那次），报告第 5 行自记的生成者 md5 就是下面这条，所以文档正文里那处
    # `a0a3a677e4d6…` 必须仍是盘上那份的前缀。字节数按文件头那条"已知碰撞"不钉。
    (u"屏位来源量具（#40 那把尺）", u"验收\\exp_backdrop_source.py", "a0a3a677e4d6", "prefix",
     {"mtime": True}),
    # ④⑤ 的出处清单（说明文档 §8 里那张 17 行的表）整张登记进来。它以前只是手抄：
    # 每抄一个数就多一处"必须重跑才不滞后"的包袱，而这一批里恰好有 6 处是我一边跑
    # 一边抄进正文的（四批留底＋两份比较器输出＋调度器日志＋交卷件），所以改成机器核对。
    # 三条已知碰撞都在文档里交了底，这里一律不靠放宽判据绕开：
    # - `cmp6x2-b2b4.out` 的字节数 2427 与上一行 2429 只差末位，正撞在规则②上 ⇒ 那一格
    #   按口径**不钉字节**，只钉 md5＋mtime（与 `exp_backdrop_source.py` 15099／15090 同档）。
    # - 文件名里那个紧凑 stamp（165433／180219）是**启动**时刻，mtime 是**落盘**时刻，
    #   两者本来就差几分钟，所以这批一律不传 extras["stamp"]，只传 bytes＋mtime；
    #   "文件名带戳的那份必须在盘上数得出"由第 8 条管，不靠 stamp 兜。
    # - 产物目录里这三把尺（_cmp6x2／_run6x2／_falsify_repeat_rulers）不在仓库内，
    #   `check_runbook.py` 规则 3 看不见它们（缺口 9），所以它们的身份证只能由这里钉住。
    (u"合成后判决量具（六轮表那把尺）", u"验收\\probe_glass.py", "6d826fe69d0e", "prefix",
     {"bytes": True, "mtime": True}),
    (u"④ 比较器", os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify", "_cmp6x2.py"),
     "80418a4a2a5f", "prefix", {"bytes": True, "mtime": True}),
    (u"④⑤ 调度器", os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify", "_run6x2.py"),
     "3f947379a029", "prefix", {"bytes": True, "mtime": True}),
    (u"④⑤ 重复性证伪器",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify", "_falsify_repeat_rulers.py"),
     "0bf904cd892b", "prefix", {"bytes": True, "mtime": True}),
    (u"旧留底·第 21 次补跑",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify",
                  "probe-21-only-20261008T222022Z.log"),
     "42f431e481fb", "prefix", {"bytes": True, "mtime": True}),
    (u"旧留底·第 20 次满趟",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify",
                  "probe-20-wallclock-20261008T214904Z.log"),
     "e743847b3ada", "prefix", {"bytes": True, "mtime": True}),
    (u"④ 第 1 趟第 1 回（环境失败）",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify",
                  "probe-batch1-20261010T165433Z-T1.log"),
     "1fc3eab9934a", "prefix", {"bytes": True, "mtime": True}),
    (u"④ 第 1 趟第 2 回＝⑤ 的批 1",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify",
                  "probe-batch1-20261010T165433Z-T2.log"),
     "51b0ed8db98d", "prefix", {"bytes": True, "mtime": True}),
    (u"④ 第 2 趟＝⑤ 的批 2",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify",
                  "probe-batch2-20261010T165433Z-T1.log"),
     "d908f261b6bd", "prefix", {"bytes": True, "mtime": True}),
    (u"④ 正式对账输出",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify", "cmp6x2-formal-v3.out"),
     "f116531140d6", "prefix", {"bytes": True, "mtime": True}),
    (u"④⑤ 证伪输出",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify", "falsify-repeat-final.out"),
     "467dd130e09c", "prefix", {"bytes": True, "mtime": True}),
    (u"⑤ 批 3 留底",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify",
                  "probe-batch1-20261010T180219Z-T1.log"),
     "016c7e208843", "prefix", {"bytes": True, "mtime": True}),
    (u"⑤ 批 4 留底",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify",
                  "probe-batch2-20261010T180219Z-T1.log"),
     "2e860131d1a3", "prefix", {"bytes": True, "mtime": True}),
    (u"⑤ 调度器日志",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify", "run6x2-20261010T180219Z.log"),
     "3de15988645f", "prefix", {"bytes": True, "mtime": True}),
    (u"⑤ 交卷件",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify", "FINAL-6x2-20261010T180219Z.md"),
     "16e4c888be52", "prefix", {"bytes": True, "mtime": True}),
    (u"⑤ 同状态对账（批 3×4）",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify", "cmp6x2-b3b4.out"),
     "36fcf9989c6e", "prefix", {"bytes": True, "mtime": True}),
    (u"⑤ 跨状态对账（批 2×4）",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify", "cmp6x2-b2b4.out"),
     "3ca6541f7d98", "prefix", {"mtime": True}),
    # ── §8-⑥（#42 裸窗表面单变量）的出处清单，11 行 ──────────────────────────────
    # 登记口径与前两批一致：md5 前缀 ≥12 位＋当前字节数＋落盘 ISO mtime 三件套都在正文里，
    # 由这里现算现比，正文一个字抄错（或量具又动过一个字节）就红。
    # 两点交底：
    # - 三趟证伪/批量里只有 **两趟** 证伪回执（155202Z＝抓到 28/30 那趟，暴露了证伪器自己的
    #   .pyc 复用失明；155351Z＝修好后 30/30 那趟）。第一趟的"红"是量具的缺陷样本，
    #   留着比删掉有用，所以两趟都进表，不许只钉好看的那份。
    # - 批 1／2／3 只钉报告本体（判废与不重复的那三趟是证据，不是交付件）；FINAL＋DONE
    #   只钉批 4，因为交卷口径认的是那一份 rc=0。
    (u"#42 量具（裸窗表面单变量）", u"验收\\exp_host_surface.py", "73cdd3d0b7d3", "prefix",
     {"bytes": True, "mtime": True}),
    (u"#42 自检（39 条已知答案）", u"验收\\selftest_host_surface.py", "18e215b662ca", "prefix",
     {"bytes": True, "mtime": True}),
    (u"#42 证伪器（30 条变异）", u"验收\\falsify_host_surface.py", "526f5b7fbb8c", "prefix",
     {"bytes": True, "mtime": True}),
    (u"#42 证伪回执·缺陷样本（28/30）",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify",
                  "falsify-host-surface-20261011T155202Z.txt"),
     "19344977333d", "prefix", {"bytes": True, "mtime": True}),
    (u"#42 证伪回执·收口（30/30）",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify",
                  "falsify-host-surface-20261011T155351Z.txt"),
     "1618404d9bca", "prefix", {"bytes": True, "mtime": True}),
    (u"#42 批 1（rc=0，prod-acrylic 跟 +10.1）",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify", "host-surface-20261011T151832Z.md"),
     "33f7e75d943a", "prefix", {"bytes": True, "mtime": True}),
    (u"#42 批 2（rc=5 判废那趟）",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify", "host-surface-20261011T152614Z.md"),
     "f1b8a0e4c25d", "prefix", {"bytes": True, "mtime": True}),
    (u"#42 批 3（桌面自走，prod 两行不作数）",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify", "host-surface-20261011T153133Z.md"),
     "ca5ca17a3ee7", "prefix", {"bytes": True, "mtime": True}),
    (u"#42 批 4（rc=0 满 14 行＝交卷那趟）",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify", "host-surface-20261011T155435Z.md"),
     "9d8f1bb8e926", "prefix", {"bytes": True, "mtime": True}),
    (u"#42 批 4 交卷件",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify", "FINAL-surface-20261011T155435Z.md"),
     "b84148c19bfe", "prefix", {"bytes": True, "mtime": True}),
    (u"#42 批 4 哨兵",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify", "DONE-surface-20261011T155435Z.ok"),
     "4b14e25d7a69", "prefix", {"bytes": True, "mtime": True}),
    (u"#42 三种调用形状实测",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify",
                  "c6-host-surface-shapes-20261011T161106Z.txt"),
     "eee33a60217b", "prefix", {"bytes": True, "mtime": True}),
    # ── §9／§9e 这一批**不在下面手抄期望值**（2026-10-15 改，见上面第 10 条那段三问）。
    #    旧写法在这里钉着"当前页面字节 e0a519a1…／计时沙箱尺／三份回执／三份改动前快照"，
    #    而同一批数在文档 §9e 又抄了一遍 ⇒ 一轮改动要订正两处，漏哪一处都红。本轮那 6 条红
    #    全是这个形状（文档已经跟着本轮更新，脚本还钉着上一轮的值）。现在这一批的期望值
    #    由 §9e 那张表供、真值由盘上供，判据一项没少（md5／字节／落盘 ISO 逐行核），
    #    "同一个哈希抄两遍漂一处"那把全局尺也照旧在跑。
    #    历史那三张 2026-10-14 的回执身份证随 §9e 换表一起退出冻结台账：文件仍在盘上、
    #    文件名仍被第 8 条要着，只是正文不再断言它们的 md5／字节 ⇒ 没有可核对的假话可红了。
]

# 订正过的手抄值：一旦漂回文档就红。
STALE = [
    (u"+231", u"原型底色差的手抄漂移值（盘上＝+230.8）"),
    (u"（2026-10-08 落盘，量具", u"原型日志落盘日凭印象写错（文件 mtime＝2026-10-07T06:15:10Z）"),
]

bad = []
rows = []
for _b in bad_pre:
    bad.append(_b)

# ── 第 10 条开火：§9e 那张表 → CITED 形状的"活行"，期望值来自表、真值来自盘上 ──────
CITED_LIVE = []
LIVE_BAD = set()
LED_ROWS = None if bad_pre else ledger_body(t)
if LED_ROWS is None and not bad_pre:
    bad.append(u"出处表：文档里读不出 §9e 的表体（表头之后没有 |---| 分隔行＋数据行）"
               u"⇒ 第 10 条整条不作数，不是通过")
if LED_ROWS is not None:
    _skips = []
    for _ln in LED_ROWS:
        _r = ledger_row(_ln)
        if _r["skip"]:
            if _r["why"]:
                bad.append(u"出处表：%s（这一行：%s）" % (_r["why"], _ln[:76]))
            else:
                _skips.append(_ln[:40])
            continue
        if _r["why"]:
            bad.append(u"%s：%s ⇒ 这一行不作数（宁可红，不猜目录）" % (_r["label"], _r["why"]))
            LIVE_BAD.add(_r["label"])
            CITED_LIVE.append((_r["label"], _r["path"], _r["hash"], "prefix",
                               {"live": True, "force_fail": True}))
            continue
        _real = expand(_r["path"])
        if not os.path.isfile(_real):
            bad.append(u"%s：表里点名的文件不在盘上：%s" % (_r["label"], _real))
            LIVE_BAD.add(_r["label"])
            CITED_LIVE.append((_r["label"], _r["path"], _r["hash"], "prefix",
                               {"live": True, "force_fail": True}))
            continue
        _h, _sz = md5_of(_real)
        _iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(os.path.getmtime(_real)))
        _ps = ledger_problems(_r, _h, _sz, _iso)
        for _p in _ps:
            bad.append(u"%s：%s" % (_r["label"], _p))
        if _ps:
            LIVE_BAD.add(_r["label"])
        CITED_LIVE.append((_r["label"], _r["path"], _r["hash"], "prefix", {"live": True}))
    # 行数随这一轮登记的件数涨，不进判据、只打印（抄进正文就又是一处会滞后的数）
    print("出处表：读到 %d 行，逐行回盘上核；按设计跳过 %d 行（无盘上文件可对，由 HIST 那条接手）%s"
          % (len(LED_ROWS), len(_skips),
             u"（跳过的是：%s）" % u"／".join(x.strip("| ").strip() for x in _skips) if _skips else ""))

CITED_ALL = CITED + CITED_LIVE
# 近漂豁免要用"每一条在盘上真实字节数＋它自己那行的身份证"，全部现算，不从正文读。
META = []
for _lab, _p, _c, _k, _e in CITED_ALL:
    _real = expand(_p)
    try:
        if not os.path.isfile(_real):
            continue
        META.append({"base": os.path.basename(_real), "size": str(os.path.getsize(_real)),
                     "hash": _c, "pins": bool(_e.get("bytes")) or bool(_e.get("live")),
                     "label": _lab})
    except OSError:
        continue

for label, path, cited, kind, extras in CITED_ALL:
    real = expand(path)
    live = bool(extras.get("live"))
    try:
        if not os.path.isfile(real):
            bad.append("%s：引用的文件不在盘上：%s" % (label, real))
            rows.append((label, path, "MISSING", "-", "FAIL"))
            continue
        h, size = md5_of(real)
        # 活行（第 10 条）的三格由 `ledger_problems` 逐行核，这里只借它跑"同一个哈希
        # 抄两遍漂一处"那把全局尺；两条判据各报各的，不重复红同一处。
        if live:
            ok = label not in LIVE_BAD
        else:
            ok = (len(cited) >= 12 and h.startswith(cited) and cited in t)
        if kind == "full32":
            ok = (cited == h) and (cited in t)
        if live and label in LIVE_BAD:
            ok = False
        note = []
        # 同一个哈希在文档里抄了两遍（正文一次、缺口/台账一次）时，"只要有一处对得上
        # 就绿"会漏掉另一处的漂移——证伪器就是这么抓到一条 MISSED 的。所以改成：
        # 凡是以"被钉值前 8 位"起头的十六进制串，都必须是盘上那个 md5 的前缀。
        anchor = cited[:8]
        near = [m for m in re.findall(r"[0-9a-f]{8,64}", t) if m.startswith(anchor)]
        for m in near:
            if not h.startswith(m):
                ok = False
                note = ["文档里还有一处 %s… 不是盘上 %s 的前缀（同值抄了两遍、其中一处漂了）"
                        % (m[:20], h[:20])]
                break
        if extras.get("bytes") or live:
            want = str(size)
            if ("%s 字节" % want) not in t:
                ok = False
                note.append("文档没写当前字节数（盘上 %s）" % want)
            # 近漂族：位数相同、只差末位的"N 字节"。同一个值抄了两遍时"有一处对得上
            # 就算绿"必然漏掉漂掉的那处——这条把两处都钉住。豁免只给"回盘上找得到归属"
            # 的那些（见 near_drift_hits 上面那段：另一行自己印着它、且那行的字节被核过）。
            for m, ln in near_drift_hits(t, want, os.path.basename(real), META):
                ok = False
                note.append("文档里还有一处 %s 字节，与盘上 %s 只差末位，且那一行没有别的行"
                            "替它背书（同值抄两遍、漂了一处）：%.60s" % (m, want, ln.strip()))
                break
        # 时间戳要同时出现在"文件名"和"正文"里，否则 stamp 与副本会各漂各的
        stamp = extras.get("stamp")
        if stamp and not live:
            iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(os.path.getmtime(real)))
            compact = iso.replace("-", "").replace(":", "")
            if compact != stamp:
                ok = False
                note.append("表里钉的 stamp %s 不是盘上 mtime（%s）" % (stamp, compact))
            if stamp not in os.path.basename(real):
                ok = False
                note.append("文件名里没有 stamp %s" % stamp)
            if iso not in t:
                ok = False
                note.append("文档正文里没有当前 mtime 的 ISO 形式 %s" % iso)
            # 同一时刻、不同日期的写法＝落盘日凭印象写错的那一类
            for m in re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", t):
                if m[10:] == iso[10:] and m != iso:
                    ok = False
                    note.append("文档里还有 %s（与盘上 %s 同钟点不同日期）" % (m, iso))
                    break
        # 没有"文件名带戳"那种留底副本时（脚本本体），钉不住 stamp，但可以要求
        # **文档正文出现盘上 mtime 的 ISO 写法**，并做同一族"同钟点不同日期"的近漂扫描。
        if extras.get("mtime") or live:
            iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(os.path.getmtime(real)))
            if iso not in t:
                ok = False
                note.append("文档没有盘上 mtime 的 ISO 形式 %s（正文抄的是别的那一天／时刻）" % iso)
            for m in re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", t):
                if m[10:] == iso[10:] and m != iso:
                    ok = False
                    note.append("文档里的 %s 与盘上 %s 同钟点不同日期（落盘日凭印象写错的那一类）"
                                % (m, iso))
                    break
        if not ok:
            if live and not note:
                pass  # 那一行的三格不符，第 10 条已经逐格点名了，这里不重复报一条
            else:
                bad.append("%s：文档引用 %s / 盘上 %s（%d 字节）对不上；%s"
                           % (label, cited, h[:16] + "…", size,
                              "；".join(note) or "前缀或全串不符"))
        rows.append((label, path, h, str(size), "OK" if ok else "FAIL"))
    except Exception as e:  # 断言自己不许崩，崩了会被读成"抓到"
        bad.append("%s：检查器在这条上抛异常＝不作数：%r" % (label, e))
        rows.append((label, path, "-", "-", "ERROR"))

for s, why in STALE:
    if s in t:
        bad.append("陈旧值漂回来了：%r（%s）" % (s, why))


# 9) **历史值**对账（2026-10-14 新加，起因是计时口径修复动了 index.html）。
#    上面那条 CITED 尺只能钉"当前盘上那份字节"，而 §5b 消融与 §6 六轮表那两批数出自
#    **旧字节**——旧那份页面已经不在盘上了，"回盘上重算"对它不成立。它又不能不钉：
#    文档里那句"旧锚点"是两批像素读数的归属前提，抄错一位就等于证据断链。
#    出路＝回**当时那份体检留底**重算：留底里那一行写着 `disk=<16 位> bytes=<n>`，
#    文档抄的旧哈希必须是它的前缀、旧字节数必须与它逐位相同；两处任一处漂＝红。
#    近漂族这里比的是"谁是谁的前缀"（不比长度）——假阳性对照 B 会在围栏里再抄一遍
#    完整 32 位旧哈希，而留底只记到 16 位，把"比留底长"当成漂移就是误伤。
HIST = [
    (u"旧页面锚点", "2a66cf56fd40", "139085",
     os.path.join(u"%LOCALAPPDATA%", "fq-glass-verify",
                  "sweep-20261011T165733Z-check_cited_md5.txt"),
     u"页面锚点"),
]


def hist_line(text, label):
    """取留底表里那条带 disk=／bytes= 的行；找不到回 (None, None)＝这条尺子失明。"""
    for ln in text.split("\n"):
        if label in ln and "disk=" in ln and "bytes=" in ln:
            d = re.search(r"disk=([0-9a-f]{8,32})", ln)
            b = re.search(r"bytes=(\d+)", ln)
            if d and b:
                return d.group(1), b.group(1)
    return None, None


def hist_problems(doc_text, cited_hash, cited_bytes, rec_hash, rec_bytes):
    """返回红话列表（空＝对得上）。rec_hash 为 None 时**必须**有红话：不许把失明读成绿。"""
    if rec_hash is None:
        return [u"留底里没有含 disk=／bytes= 的那一行 ⇒ 历史值这条不作数"]
    out = []
    if len(cited_hash) < 12 or cited_hash not in doc_text or not rec_hash.startswith(cited_hash):
        out.append(u"文档抄的旧哈希 %s 与留底记的 disk=%s 对不上" % (cited_hash, rec_hash))
    for m in re.findall(r"[0-9a-f]{8,64}", doc_text):
        if m.startswith(cited_hash[:8]) and not (rec_hash.startswith(m) or m.startswith(rec_hash)):
            out.append(u"文档里还有一处 %s… 与留底 %s 互不为前缀（同值抄两遍、漂了一处）"
                       % (m[:20], rec_hash))
            break
    if ("%s 字节" % cited_bytes) not in doc_text:
        out.append(u"文档没写旧字节数 %s 字节" % cited_bytes)
    if cited_bytes != rec_bytes:
        out.append(u"文档抄的旧字节数 %s 与留底 bytes=%s 不同" % (cited_bytes, rec_bytes))
    for m in re.findall(r"(\d{3,9}) 字节", doc_text):
        if m != cited_bytes and len(m) == len(cited_bytes) and m[:-1] == cited_bytes[:-1]:
            out.append(u"文档里还有一处 %s 字节，与旧值 %s 只差末位（同值抄两遍、漂了一处）"
                       % (m, cited_bytes))
            break
    return out


# 已知答案对照：四条形状里必须**分别**打出"过／哈希漂／字节漂／留底失明"，
# 对照一失灵就把下面所有历史值结论标成"不作数"——不许拿一把没校准的尺子判绿。
_H_DOC = u"旧锚点 `2a66cf56fd40` ／ 139085 字节；另抄一处 `2a66cf56fd4040d6`"
_HC = []
if hist_problems(_H_DOC, "2a66cf56fd40", "139085", "2a66cf56fd4040d6", "139085"):
    _HC.append(u"真形状被判红（假阳性）")
if not hist_problems(_H_DOC.replace("2a66cf56fd40`", "2a66cf56fd41`", 1),
                     "2a66cf56fd40", "139085", "2a66cf56fd4040d6", "139085"):
    _HC.append(u"哈希末位漂一处没被判红")
if not hist_problems(_H_DOC.replace("139085 字节", "139086 字节", 1),
                     "2a66cf56fd40", "139085", "2a66cf56fd4040d6", "139085"):
    _HC.append(u"字节数末位漂一处没被判红")
if not hist_problems(_H_DOC, "2a66cf56fd40", "139085", None, None):
    _HC.append(u"留底失明被当成绿")
if hist_line(u" - 页面锚点（六轮表的出处） cited=x disk=2a66cf56fd4040d6 bytes=139085 => OK",
             u"页面锚点") != ("2a66cf56fd4040d6", "139085"):
    _HC.append(u"留底行取不到 disk/bytes（谓词形状不对）")
if hist_line(u" - 别的行 disk=aaaa bytes=1\n - 页面锚点 disk=2a66cf56fd4040d6 bytes=139085",
             u"页面锚点") != ("2a66cf56fd4040d6", "139085"):
    _HC.append(u"多行留底里挑错了行")
if _HC:
    bad.append(u"历史值这条尺子自己失明（%s）⇒ 它后面的结论不作数" % u"；".join(_HC))
else:
    for _lab, _ch, _cb, _rp, _rl in HIST:
        try:
            _rr, _rb = hist_line(io.open(expand(_rp), encoding="utf-8",
                                         errors="replace").read(), _rl)
            _ps = hist_problems(t, _ch, _cb, _rr, _rb)
            for _p in _ps:
                bad.append(u"%s：%s" % (_lab, _p))
            rows.append((_lab, os.path.basename(expand(_rp)),
                         "%s／%s" % (_rr, _rb), "-", "FAIL" if _ps else "OK"))
        except Exception as e:
            bad.append(u"%s：检查器在这条上抛异常＝不作数：%r" % (_lab, e))
            rows.append((_lab, os.path.basename(expand(_rp)), "-", "-", "ERROR"))

# 5) 看门狗期限：文档里那句"期限至 X"不许是估的。
#    唯一出处＝最新那份 veil_watcher 日志的首行（"started … deadline N.0 h"），
#    期限＝首行时间戳 + N 小时，由这里现算，再要求文档正文里出现这个 ISO 串。
WATCH_GLOB = os.path.join(os.environ.get("LOCALAPPDATA", ""), "fq-glass-verify",
                          "veil_watcher-*.log")
logs = sorted(glob.glob(WATCH_GLOB))
if logs:
    latest = logs[-1]
    try:
        first = io.open(latest, encoding="utf-8", errors="replace").read().split("\n")[0]
    except Exception as e:
        first = ""
        bad.append("看门狗期限：读不到 %s：%r" % (os.path.basename(latest), e))
    m = re.search(r"\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z|\d{8}T\d{6}Z)\].*?deadline (\d+(?:\.\d+)?)\s*h",
                  first)
    if not m:
        bad.append("看门狗期限：最新日志首行没有「[UTC 秒] … deadline N h」的形状：%s" % first[:120])
    else:
        raw = m.group(1)
        fmt = "%Y-%m-%dT%H:%M:%SZ" if "-" in raw else "%Y%m%dT%H%M%SZ"
        start = dt.datetime.strptime(raw, fmt)
        hours = float(m.group(2))
        due = start + dt.timedelta(hours=hours)
        iso = due.strftime("%Y-%m-%dT%H:%M:%SZ")
        if iso not in t:
            bad.append("看门狗期限：文档没写 %s（＝%s 首行 %s ＋ %.1f h 算出来的）；"
                       "换一趟重挂 watcher 期限会跟着变，别手抄"
                       % (iso, os.path.basename(latest), m.group(1), hours))
        # 同一个现算值在文档里抄了三处（缺口 6、§7 台账、§8-①），"存在这一串就算绿"会漏掉
        # 漂掉的那两处——和 mtime 那条同一个盲区。所以补近漂族：凡"同日期＋同分秒、只差小时"
        # 的 ISO 串都必须等于现算期限，漂的那处当场点名。
        for _d in re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", t):
            if _d != iso and _d[:11] == iso[:11] and _d[13:] == iso[13:]:
                bad.append("看门狗期限：文档里还有一处 %s，与现算的 %s 同日期同分秒、只差小时"
                           "（同一个值抄三遍、其中一处漂了）" % (_d, iso))
                break
        rows.append((u"看门狗期限", os.path.basename(latest), iso, "%.1f h" % hours, "OK"))
else:
    print("（没有 veil_watcher 日志可核，期限那条**不作数**——不代表它对了）")


# 6) "§5b 目前 0 行真数据"这句也是手抄断言 ⇒ 回盘上数。
def row_count(text):
    """报告表里除表头、分隔行以外的每一行都是一条真数据。"""
    out = []
    for ln in text.split("\n"):
        s = ln.strip()
        if s.startswith("|") and "---" not in s and u"材质" not in s:
            out.append(s)
    return out


_HDR = u"| 材质 | 档 | 客户区均值(黑白中点) | 反应(白-黑) | 环带反应 | 黑 | 白 |"
_SEP = u"|---|---|---|---|---|---|---|"
_ROW = u"| Acrylic | C0 | 118.4 | 31.2 | 44.0 | 102.8 | 134.0 |"
_cal = []
if len(row_count(_HDR + "\n" + _SEP)) != 0:
    _cal.append("表头＋分隔行被数成了数据行")
if len(row_count(_HDR + "\n" + _SEP + "\n" + _ROW)) != 1:
    _cal.append("一条真形状的数据行没被数到")
if _cal:
    bad.append(u"消融行数这条尺子自己失明（%s）⇒ 它后面的结论不作数" % u"；".join(_cal))
else:
    _d = os.path.join(os.environ["LOCALAPPDATA"], "fq-glass-verify")
    _reps = sorted(glob.glob(os.path.join(_d, "veil-paint-*.md")))
    _per = []
    for _p in _reps:
        try:
            _per.append((os.path.basename(_p), len(row_count(io.open(_p, encoding="utf-8",
                                                                     errors="replace").read()))))
        except Exception as e:
            bad.append(u"消融断言：读不了 %s＝不作数：%r" % (os.path.basename(_p), e))
    _filled = [x for x in _per if x[1]]
    _claims = (u"0 行真数据" in t) or (u"目前 0 行" in t)
    if _filled and _claims:
        bad.append(u"消融断言：文档还写着「0 行真数据」，而盘上 %s 已经数得出 %d 行 ⇒ 那句连同判读落点要一起改"
                   % (u"、".join("%s(%d 行)" % x for x in _filled), sum(x[1] for x in _filled)))
    if _claims and _per and not _filled:
        _newest = _per[-1][0]
        if _newest not in t:
            bad.append(u"消融断言：文档自称 0 行却没点名盘上最新那份报告 %s（＝凭印象引旧那一份）" % _newest)
        # 文档里点名过的每一个报告文件名（形如 veil-paint-<紧凑戳>.md）都得在盘上数得出：
        # 时间戳格式对、盘上没有＝要么是证据被清了（断链），要么是压根凭印象编了一个。两种都不许绿。
        for _m in sorted(set(re.findall(u"veil-paint-[0-9]{8}T[0-9]{6}Z[.]md", t))):
            if _m not in set(x[0] for x in _per):
                bad.append(u"消融引用：文档点名了 %s，而产物目录里没有这份报告（被清了＝证据断链，凭印象编的＝更糟）" % _m)
        rows.append((u"消融 0 行", _newest, u"%d 份报告/共 0 行" % len(_per), u"-", u"OK"))
    elif not _claims:
        rows.append((u"消融行数（文档未自称 0 行）",
                     _per[-1][0] if _per else u"无报告",
                     u"%d 份/共 %d 行" % (len(_per), sum(x[1] for x in _per)), u"-", u"OK"))
    elif not _per:
        print(u"（产物目录没有 veil-paint 报告，消融那条**不作数**——不代表它对了）")


# 7) "#37 跑到哪一步"同样是手抄句 ⇒ 回盘上的 FINAL-veil 核。
#    两条纯函数（各自带已知答案对照，因为「看门狗到期限未产出」这一档现在盘上还没有真样本）：
#    a) 点名的 FINAL 必须真在盘上；b) 必须点名**最新**那份；c) 最新那份是「未产出」时文档必须说出这句话。
def fin_newest_hit(names, cited):
    """盘上有 FINAL 时，文档必须点名按文件名排序最新的那份（名字是 UTC 紧凑戳，字典序＝时间序）。"""
    if not names:
        return True
    return max(names) in cited


def fin_claimed(doc_text, gave_up):
    """最新那份 FINAL 写的是「未产出」⇒ 文档必须出现「没等到就绪桌面」；否则这条不作数。"""
    if not gave_up:
        return True
    return u"没等到就绪桌面" in doc_text


_fcal = []
if fin_newest_hit([u"a.md", u"b.md"], set([u"a.md"])) is not False:
    _fcal.append(u"「引了旧那份」这一形状没被判红")
if fin_newest_hit([u"a.md", u"b.md"], set([u"b.md"])) is not True:
    _fcal.append(u"「点了最新那份」被判成红")
if fin_newest_hit([], set()) is not True:
    _fcal.append(u"盘上没有 FINAL 时它硬要报警")
if fin_claimed(u"", True) is not False:
    _fcal.append(u"未产出而文档没交底，仍被判过")
if fin_claimed(u"看门狗没等到就绪桌面", True) is not True:
    _fcal.append(u"已交底的句子被判红")
if fin_claimed(u"随便什么", False) is not True:
    _fcal.append(u"未产出以外的结局被这条误伤")
if _fcal:
    bad.append(u"#37 现场这条尺子自己失明（%s）⇒ 它后面的结论不作数" % u"；".join(_fcal))
else:
    _dd = os.path.join(os.environ["LOCALAPPDATA"], "fq-glass-verify")
    _fins = sorted(os.path.basename(x) for x in glob.glob(os.path.join(_dd, "FINAL-veil-*.md")))
    _cited = set(re.findall(u"FINAL-veil-[0-9]{8}T[0-9]{6}Z[.]md", t))
    for _m in sorted(_cited):
        if _m not in set(_fins):
            bad.append(u"#37 现场引用：文档点名了 %s，而产物目录里没有这份 FINAL（时间戳格式对但盘上没有"
                       u"＝证据被清了或凭印象编的）" % _m)
    if not fin_newest_hit(_fins, _cited):
        bad.append(u"#37 现场断言：文档没点名盘上最新那份 %s＝还在引旧那一份的结局" % max(_fins))
    if _fins:
        _newfin = max(_fins)
        try:
            _ft = io.open(os.path.join(_dd, _newfin), encoding="utf-8", errors="replace").read()
            _gave = u"未产出" in _ft
        except Exception as e:
            bad.append(u"#37 现场：读不了 %s＝不作数：%r" % (_newfin, e))
            _gave = False
        if not fin_claimed(t, _gave):
            bad.append(u"#37 现场交底：最新那份 FINAL（%s）自记「未产出」＝看门狗到期限没等到就绪桌面，"
                       u"而文档没有这句交底 ⇒ 不许还写成「等它出数」" % _newfin)
        rows.append((u"#37 现场", _newfin, u"未产出" if _gave else u"跑完（有尝试记录）", u"-", u"OK"))
    else:
        print(u"（盘上没有 FINAL-veil，#37 现场那条**不作数**——不代表它对了）")


# 8) 文档里反引号点名过、名字带紧凑 UTC 时间戳的产物，一律回盘上**逐字符**数得出。
#    这一条是把上面两处（veil-paint／FINAL-veil）的"点名的文件要在盘上"收成通用尺：
#    本轮真抓到的形状是"留底 stdout 的秒位抄成相邻一秒"——扩展名／日期／时长全对，
#    只有 basename 差一字符，而"同族里有没有文件"的兜底判据会把它洗成绿，所以这里
#    明确**不许同族兜底**：差一秒＝红（被清了＝证据断链，抄错了＝引用不可复查）。
def stamped_artifact_names(text):
    """反引号里、含 8 位日期 T 6 位时刻 Z 的名字 ⇒ 取其 basename；含 <占位>／* 通配的模板不算。"""
    out = []
    for m in re.finditer(r"`([^`\n]+)`", text):
        s = m.group(1).strip()
        if not re.search(r"\d{8}T\d{6}Z", s):
            continue
        if any(ch in s for ch in "<>*…"):
            continue
        out.append(s.replace("\\", "/").rstrip("/").split("/")[-1])
    return sorted(set(out))


def artifacts_missing(names, present):
    """逐字符比对：present 里没有就是缺，同族多一个文件不能替它说话。"""
    return [n for n in names if n not in present]


_scal = []
if stamped_artifact_names(u"看 `veil-paint-20261009T233341Z.md` 那张表") != \
        [u"veil-paint-20261009T233341Z.md"]:
    _scal.append(u"真形状的带戳名没被收进来")
if stamped_artifact_names(u"产物 `%LOCALAPPDATA%\\fq-glass-verify\\FINAL-veil-20261009T224406Z.md`") != \
        [u"FINAL-veil-20261009T224406Z.md"]:
    _scal.append(u"带目录前缀时没取到 basename")
if stamped_artifact_names(u"`window-<轮>-20261009T000851Z.png` `probe-batch<k>-<STAMP>-T1.log`"):
    _scal.append(u"带 <占位> 的模板被当成真名字去要文件")
if stamped_artifact_names(u"`index.html` 的 md5 `2a66cf56fd40…`，正文 `2026-10-10T00:20:06Z`"):
    _scal.append(u"不带戳／不是文件名的反引号串被误伤")
if artifacts_missing([u"a-20261010T002025Z.log"], set([u"a-20261010T002026Z.log"])) != \
        [u"a-20261010T002025Z.log"]:
    _scal.append(u"只差一秒的同族兜底把缺文件洗成了绿")
if artifacts_missing([u"a-20261010T002025Z.log"], set([u"a-20261010T002025Z.log"])):
    _scal.append(u"盘上真有的那份被判成缺")
if _scal:
    bad.append(u"带戳产物名这条尺子自己失明（%s）⇒ 它后面的结论不作数" % u"；".join(_scal))
else:
    _dirs = [ROOT, os.path.join(os.environ.get("LOCALAPPDATA", ""), "fq-glass-verify")]
    _present = set()
    for _d in _dirs:
        if os.path.isdir(_d):
            try:
                _present |= set(os.listdir(_d))
            except Exception as e:
                bad.append(u"带戳产物名：列不了目录 %s＝不作数：%r" % (_d, e))
    _cited_names = stamped_artifact_names(t)
    _miss = artifacts_missing(_cited_names, _present)
    for _n in _miss:
        bad.append(u"带戳产物名引用：文档点名了 %s，而仓库根与产物目录都没有**逐字符相同**的这份"
                   u"（同族里相邻一秒的那份不算；抄错＝引用不可复查，被清＝证据断链）" % _n)
    rows.append((u"带戳产物名", u"%d 个点名" % len(_cited_names),
                 u"缺 %d" % len(_miss) if _miss else u"全部在盘上", u"-",
                 u"FAIL" if _miss else u"OK"))

print("== 文档引用与盘上重算 ==")
for r in rows:
    print(" - %-24s cited=%s disk=%s bytes=%s => %s" % (r[0], r[1].split("\\")[-1], r[2][:16], r[3], r[4]))
print("PROBLEMS: %d" % len(bad))
for x in bad:
    print(" -", x)
if LIST:
    print("\n-- 引用表（冻结那批＝脚本里手抄的期望值）--")
    for label, path, cited, kind, extras in CITED:
        print("%s\t%s\t%s\t%s" % (label, path, cited, kind))
    print("\n-- 引用表（活的那批＝从 §9e 那张表现读的期望值，逐行回盘上核）--")
    for label, path, cited, kind, extras in CITED_LIVE:
        print("%s\t%s\t%s\t%s" % (label, path, cited, kind))
    print("\n-- 陈旧值表 --")
    for s, why in STALE:
        print("%r\t%s" % (s, why))
sys.exit(1 if bad else 0)
