# -*- coding: utf-8 -*-
"""证伪体检器本身：往 runbook 的副本里注若干"合理 bug"，要求 lint 每条都变红**并点到该管它的那条
规则**；再配三条对照——围栏假阳性、3b 绝对路径假阳性（必须点名）、摘掉 exists 的失明副本
（必须把 abs-drift 洗绿、把 abs-abbrev 留在红）。注几条由本文件 MUTS 决定，回执自己打印分母。
"""
import io, os, subprocess, sys

# 兜住 GBK 控制台／重定向：报告行里有 ⇒ 和中文，崩在打印 CAUGHT 那一行会让 rc=1
# 被误读成"抓到变异"（详见 check_cited_md5.py 同段注释）。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, u"..", u"原生玻璃版-说明.md"))
LINT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "check_runbook.py")
base = io.open(SRC, encoding="utf-8").read()
BS = chr(92)

def add_benign_fence(t):
    """往说明里塞一段"命令示例"：里面有裸竖线表格样、有 **、有单反引号——都在围栏内，不该报警。"""
    return t.rstrip("\n") + "\n\n```\n| a | b |\n| 未闭合的粗体 ** 结尾\npython 验收\\check_runbook.py 原生玻璃版-说明.md   # 真文件，围栏内\n```\n"


def drop_second_fence(t):
    ls = t.split("\n")
    idx = [i for i, l in enumerate(ls) if l.strip().lstrip(">").strip().startswith("```")]
    if len(idx) < 2:
        return t
    del ls[idx[1]]                     # 关掉第一个代码块的那一行没了 ⇒ 围栏数变奇数
    return "\n".join(ls)

# —— 3b 那把新牙的两刀（2026-10-16）——
# 挑的都是"正文只有一条带盘符路径"的名字，这样漂移一处就只有它红，归因不含糊：
#   wscript.exe    文中 1 条全路径（说明 674 行）；salt_player.py 文中 1 条全路径（705 行，
#   另一处 salt-player\salt_player.py 没盘符、不进候选表，正好用来证明"半截路径不作数"）。
ABS_DRIFT_FROM = r"C:\Windows\System32\wscript.exe"
ABS_DRIFT_TO = r"C:\Windows\System32\NO_SUCH_DIR\wscript.exe"
ABS_GOOD_FROM = r"C:\Users\lyj20\Desktop" + chr(92) + u"赛博鸡蛋" + chr(92) + r"salt-player\salt_player.py"
ABS_GOOD_TO = u"…" + chr(92) + "salt_player.py"

# 假阳性对照用这两条：都当场核过 exists=True，且原本不在正文里（核不到就是量具坏了）
BENIGN_ABS = [r"C:\Users\lyj20\.qoder\memory\MEMORY.md",
              r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"]

def add_abs_benign(t):
    """往围栏里贴两条**真在盘上**的仓库外绝对路径 ⇒ 3b 必须放它过，且把这两个名字**点名**印出来。"""
    return t.rstrip("\n") + "\n\n```\n" + "\n".join(BENIGN_ABS) + "\n```\n"

def drift_all(t, a, b):
    """整份替换（count=-1）。若换完**还剩下** a，就返回原文 ⇒ 调用方按 SKIP 处理（这条刀没铺满）。
    理由：3b 的判据是"这名字**一条**可核路径都没有"，只换一处会留下一条真路径，体检器放绿是对的，
    但把这种"半漂"记成 MISSED 就会把矛头指错地方（指到尺子，其实钝的是刀）。"""
    r = t.replace(a, b, -1)
    return t if a in r else r

def parse_3b(out_lines):
    """从体检器输出里取 "3b 仓库外绝对路径核过 N 条：a、b" 那行。取不到＝(None, [])，
    调用方必须把"取不到"当失败，而不是当 0 条（否则规则被整块删掉也能蒙过对照）。"""
    ln = [x for x in out_lines if x.startswith(u"3b 仓库外绝对路径核过")]
    if not ln:
        return None, []
    head, _, tail = ln[0].partition(u"：")
    ds = "".join(ch for ch in head.split(u"核过")[1] if ch.isdigit())
    names = [x for x in tail.strip().split(u"、") if x and x != u"（无）"]
    return (int(ds) if ds else None), names

MUTS = [
    ("drop-sep", base.replace(u"| --- | --- | --- | --- | --- |", u"| 尺子 | 状态 | 能判 | 出处 | 不管 |", 1),
     u"第二行不是分隔行"),
    ("raw-pipe", base.replace(u"Q1 全窗 slope | Q2 透区面积", u"Q1 slope x" + chr(124) + u"y | Q2 面积", 1),
     u"table@"),
    ("ghost-ref", base.replace(u"验收" + BS + u"check_glass_css.py",
                               u"验收" + BS + u"no_such_checker.py", 1),
     u"提到但盘上没有"),
    ("open-fence", drop_second_fence(base), u"围栏行数为奇数"),
    ("bold-tear", base.replace(u"**未测／已测但不足以定论（诚实边界）**",
                               u"**未测／已测但不足以定论（诚实边界）", 1),
     u"bold 不成对"),
    ("rename-h8", base.replace(u"## 8. 待办台账", u"## 8x. 待办台账", 1), u"缺章节"),
    # C6：把带前缀的 probe_glass 命令改成裸写（probe_glass.py 源码里有 ⇒、又没自带兜底），
    # 必须被 C6 抓到；红了但归因不到 C6（比如顺手把围栏弄坏了）算 MISSED。
    ("bare-arrow-cmd", base.replace(u"PYTHONIOENCODING=utf-8 python 验收" + BS + u"probe_glass.py",
                                    u"python 验收" + BS + u"probe_glass.py", 1),
     u"C6 编码口径"),
    # 3b 的两条判决各配一刀：一条"给了绝对路径但回盘上核不到"，一条"只给缩写"。
    # 两刀故意落到**不同**的红话上，这样下一个人把 exists 那一步摘掉时，只有前者会翻绿；
    # 后者仍红 ⇒ 能证明"摘 exists 只瞎了半条规则"，而不是整条 3b 一起没了。
    # **replace 用 -1（整份换掉）而不是 1**：判据是"这个名字**没有任何一条**可核路径"，
    # 只换第一处时正文里还剩一条真路径 ⇒ 3b 正确地放绿 ⇒ 这一刀变成假 MISSED。
    # （本轮真踩过：把这两条写进 §7 台账时正文各多出一份全路径，count=1 立刻失能，
    #   证伪器如实报了 2 条 MISSED——报的是"刀钝了"，不是"尺子坏了"。）
    ("abs-drift", drift_all(base, ABS_DRIFT_FROM, ABS_DRIFT_TO), u"仓库外绝对路径"),
    ("abs-abbrev", drift_all(base, ABS_GOOD_FROM, ABS_GOOD_TO), u"没给可核对的绝对路径"),
]

# 变异副本一律写到 %TEMP%，绝不落进交付目录（第 22 号任务的教训）；
# 文件存在性用第二参把仓库根显式递给体检器，副本在哪儿不影响它查引用。
PROBE = os.path.join(os.environ["LOCALAPPDATA"], "fq-glass-verify", "_lint_probe.md")
caught = skipped = wrong_rule = 0
for name, text, expect in MUTS:
    if text == base:
        print("%-11s SKIP（这一刀没落到任何行上＝变异本身无效，不算体检的功劳）" % name)
        skipped += 1
        continue
    io.open(PROBE, "w", encoding="utf-8", newline="\n").write(text)
    r = subprocess.run([sys.executable, LINT, PROBE, os.path.dirname(SRC)], capture_output=True)
    out = (r.stdout or b"").decode("utf-8", "replace").strip().splitlines()
    detail = out[-1] if out else ""
    # 红了不算抓到，**红话里点到该管它的那条规则**才算（否则一条变异可能撞坏围栏、
    # 由别的规则替它背下这一刀，而 C6 之类的弱判据永远没人验过它有没有牙）。
    # 只认判决行（" - …"）：体检器还会打印 "3b 仓库外绝对路径核过 N 条" 和 "C6 看了 N 条"
    # 这类**信息行**，它们天然含着规则名，若一起进匹配池，abs-drift 那刀即使 3b 根本没红
    # 也会被记成 CAUGHT（2026-10-16 加 3b 时先踩到这个坑，所以这里收紧成"必须来自 bad[]"）。
    named = [x for x in out if expect in x and x.startswith(" -")]
    ok = (r.returncode != 0 and bool(named))
    if r.returncode != 0 and not named:
        wrong_rule += 1
    caught += ok
    print("%-11s rc=%s 期望规则=%-14s %-42s ⇒ %s" % (
        name, r.returncode, expect, (named[0] if named else detail)[:42],
        "CAUGHT" if ok else ("红了但没点到 %s（WRONG-RULE）" % expect if r.returncode else "MISSED（根本没红）")))
if os.path.exists(PROBE):
    os.remove(PROBE)

rc_p = subprocess.run([sys.executable, LINT, SRC], capture_output=True)
rc = rc_p.returncode
clean_out = (rc_p.stdout or b"").decode("utf-8", "replace").strip().splitlines()
n_base, list_base = parse_3b(clean_out)
print("clean copy rc=%s（必须 0）｜3b 已核过 %s 条：%s" % (rc, n_base, u"、".join(list_base) or u"（无）"))
print("抓到的 %d/%d，跳过 %d，红了但归因错的 %d" % (caught, len(MUTS) - skipped, skipped, wrong_rule))

# 假阳性对照：往围栏里塞"看着像坏表格/坏粗体"的内容，体检必须仍然 0（否则它把命令示例当 markdown 数）
# 这条同时也当 C6 的假阳性对照：塞进去的是**裸写的 `python 验收\check_runbook.py`**，
# 那份脚本自带 stdout 兜底，C6 必须放它过；如果 C6 一条命令都没看（计数为 0），
# 那"没报警"就只是"没检查"，所以这里要求 C6 的自报计数 ≥1 才算这条对照成立。
benign = add_benign_fence(base)
assert benign != base, "良性样本没落上＝这条对照本身失效"
io.open(PROBE, "w", encoding="utf-8", newline="\n").write(benign)
rb = subprocess.run([sys.executable, LINT, PROBE, os.path.dirname(SRC)], capture_output=True)
outb = (rb.stdout or b"").decode("utf-8", "replace").strip().splitlines()
c6b = [x for x in outb if x.startswith("C6 看了")]
n_c6 = int("".join(ch for ch in (c6b[0].split("看了")[1] if c6b else "") if ch.isdigit()) or 0)
print("fence-control rc=%s %s C6看了%s条 ⇒ %s" % (
    rb.returncode, (outb[-1] if outb else "")[:40], n_c6,
    "不报警（对）" if (rb.returncode == 0 and n_c6 >= 1) else
    ("假阳性（这条尺子过严）" if rb.returncode else "C6 一条命令都没看＝这条对照不作数")))
if os.path.exists(PROBE):
    os.remove(PROBE)

# —— 3b 的两条配套对照（假阳性 + 失明），一条都不许省 ——
# 假阳性对照：贴两条**盘上真有的**仓库外绝对路径进去。要求 (a) rc=0，(b) 这两个名字被
# **点名印出**，(c) 计数比基线多出这两条。只要求 rc=0 是不够的：3b 整块被删掉时它也 rc=0，
# 那就是"没检查"被读成"检查过且通过"（同 C6 那条对照的理由）。
ben2 = add_abs_benign(base)
assert ben2 != base, "3b 良性样本没落上＝这条对照本身失效"
io.open(PROBE, "w", encoding="utf-8", newline="\n").write(ben2)
rb2 = subprocess.run([sys.executable, LINT, PROBE, os.path.dirname(SRC)], capture_output=True)
out2 = (rb2.stdout or b"").decode("utf-8", "replace").strip().splitlines()
n2, list2 = parse_3b(out2)
need2 = [p.replace("\\", "/").rsplit("/", 1)[-1] for p in BENIGN_ABS]
hit2 = [nm for nm in need2 if nm in list2]
ok_abs_ctl = (rb2.returncode == 0 and n2 is not None and len(hit2) == len(need2)
              and n_base is not None and n2 >= n_base + len(need2))
print("abs-control rc=%s 3b核过 %s→%s 点名 %s/%s ⇒ %s" % (
    rb2.returncode, n_base, n2, len(hit2), len(need2),
    "放它过且点名（对）" if ok_abs_ctl else
    ("假阳性（这条尺子过严）" if rb2.returncode else "对照不作数：没计数/没点名/计数没涨（3b 可能根本没跑）")))
if os.path.exists(PROBE):
    os.remove(PROBE)

# 失明对照：把 3b 里 exists 那一手**整项摘掉**（"信正文写的路径"），拿同一份 abs-drift 副本去量。
# 要求：真体检器红、摘掉 exists 的副本绿 ⇒ 这一刀的牙确实长在 exists 那一步，不是别处顺手红的。
# 再用同一份盲副本量 abs-abbrev 副本，要求**仍然红**且红话还是"没给可核对的绝对路径"
# ⇒ 证明盲副本只瞎了半条规则，另一条（缩写不作数）不靠盘上核，没被这刀顺带洗掉。
LINT_SRC = io.open(LINT, encoding="utf-8").read()
BLIND_FROM = "    hit = [p for p in cs if os.path.exists(os.path.expandvars(p))]"
BLIND_TO = "    hit = list(cs)  # BLIND-CONTROL：信正文，不回盘上核"
blind_src = LINT_SRC.replace(BLIND_FROM, BLIND_TO, 1)
BLINT = os.path.join(os.environ["LOCALAPPDATA"], "fq-glass-verify", "_lint_blind.py")
if blind_src == LINT_SRC:
    # 锚点没落到行上＝盲副本根本没盲，这条对照必须记 NOP（不是"漏网"、更不是"通过"）。
    print("blind-control NOP（摘 exists 那一刀没落到体检器源码上：锚点行变了，先修对照）")
    ok_blind = False
else:
    io.open(BLINT, "w", encoding="utf-8", newline="\n").write(blind_src)
    dif = {}
    by_name = dict((n, (txt, exp)) for n, txt, exp in MUTS)
    for key in ("abs-drift", "abs-abbrev"):
        drift_text, exp = by_name[key]
        assert drift_text != base, "%s 这一刀本身没落上，失明对照不作数" % key
        io.open(PROBE, "w", encoding="utf-8", newline="\n").write(drift_text)
        rr = subprocess.run([sys.executable, LINT, PROBE, os.path.dirname(SRC)], capture_output=True)
        rl = subprocess.run([sys.executable, BLINT, PROBE, os.path.dirname(SRC)], capture_output=True)
        ro = (rl.stdout or b"").decode("utf-8", "replace").strip().splitlines()
        dif[key] = (rr.returncode, rl.returncode,
                    [x for x in ro if exp in x and x.startswith(" -")])
        print("blind-control %-11s 真体检器 rc=%s ｜盲副本 rc=%s ｜盲副本红话 %d 条 ⇒ %s" % (
            key, dif[key][0], dif[key][1], len(dif[key][2]),
            "该绿（对，牙在 exists）" if (key == "abs-drift" and dif[key][0] and not dif[key][1]) else
            ("该红（对，另一半不靠 exists）" if (key == "abs-abbrev" and dif[key][0] and dif[key][2]) else
             "对照不成立（失明没把 drift 洗绿／或把 abbrev 也洗绿了）")))
    if os.path.exists(PROBE):
        os.remove(PROBE)
    if os.path.exists(BLINT):
        os.remove(BLINT)
    ok_blind = (dif["abs-drift"][0] != 0 and dif["abs-drift"][1] == 0
                and dif["abs-abbrev"][0] != 0 and len(dif["abs-abbrev"][2]) >= 1)

sys.exit(0 if (rc == 0 and rb.returncode == 0 and n_c6 >= 1 and ok_abs_ctl and ok_blind
               and wrong_rule == 0 and skipped == 0 and caught == len(MUTS)
               and n_base is not None) else 1)
