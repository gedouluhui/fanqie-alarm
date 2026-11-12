# -*- coding: utf-8 -*-
"""给 #42 那把尺（exp_host_surface.py）与它的已知答案自检做变异证伪。

规矩（这套仓库的既定口径，与 _falsify_repeat_rulers / falsify_check_cited_md5 同一套）：
- 每条变异注一个**静默 bug**（把判据调回恒真／把配对前提摘掉／把常量抄回上一次那个错值／
  把两轮数拼成一个现场不存在的差），要求副本的自检必须 rc 不为 0 **且红话里点到那条
  已知答案的名字**；只 rc 不为 0 不点名（traceback 冒充）不算抓到；
- 注下去文本没变（锚点不唯一／锚点没命中）记 NOP——那是变异自己失效，不算抓到也不算漏网，
  但同样判这一趟不通过；
- 两条假阳性对照：未变异的原件副本、以及只改判据之外措辞的那一趟，都必须仍然 rc 为 0；
- 副本一律写在 LOCALAPPDATA 下的 fq-glass-verify 沙箱里，交付目录一个字都不落；跑完删掉。
- 本脚本不碰像素、不起窗、不接 CDP，但它会打印"场窗数＋端口"作为入场记录，
  免得将来谁把它和像素趟并跑（就地改文件的趟一次只许跑一趟）。

为什么要连两份参照件一起注（F5b/F5c）：F5 那条断言的价值全在"跨文件对表"，
如果它只比本尺自己的常量和自己抄的一份期望值，注漂参照件它就毫无反应——那 F5 就是零鉴别力。
"""
import io
import os
import shutil
import subprocess
import sys
import datetime as dt

NL = chr(10)
HERE = os.path.dirname(os.path.abspath(__file__))            # 交付目录：验收
OUT = os.path.join(os.environ["LOCALAPPDATA"], "fq-glass-verify")
STAMP = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
SBX = os.path.join(OUT, "fsb-" + STAMP)                       # 沙箱根
ACC = os.path.join(SBX, "acc")                                # 放量具与自检的副本（= 量具的 HERE）
NAT = os.path.join(SBX, "native")                             # 供 F5 的 ../native/FqHost.cs
DRV = os.path.join(SBX, "driver.py")

INSTR = os.path.join(HERE, "exp_host_surface.py")
SELF = os.path.join(HERE, "selftest_host_surface.py")
SMOKE = os.path.join(HERE, "smoke_ship.py")
CS = os.path.join(os.path.dirname(HERE), "native", "FqHost.cs")

COPY = {"instr": os.path.join(ACC, "exp_host_surface.py"),
        "self": os.path.join(ACC, "selftest_host_surface.py"),
        "smoke": os.path.join(ACC, "smoke_ship.py"),
        "cs": os.path.join(NAT, "FqHost.cs")}

# (标签, 角色, 点名串, old, new, 期望命中数)
MUTS = [
    (u"A1 客户区差符号翻转", "instr", u"A1 ",
     'd_client = bright["client"] - dark["client"]',
     'd_client = dark["client"] - bright["client"]', 1),
    (u"A2 跟踪比反算成屏位／客户区", "instr", u"A2 ",
     'ratio = (d_client / d_region) if d_region else None',
     'ratio = (d_region / d_client) if d_client else None', 1),
    (u"A3 TRACK_MIN 比较调回恒真", "instr", u"A3 ",
     'if abs(d_client) >= track_min:', 'if True:', 1),
    (u"A4 缺轮改判 FLAT", "instr", u"A4 ",
     u'        return "UNPAIRED", "缺轮（起窗失败／中途被锁屏打断）⇒ 这一行没有结论", None, None, None',
     u'        return "FLAT", "桩", None, None, None', 1),
    (u"A5 桌面自走闸门摘掉", "instr", u"A5 ",
     'if drift > drift_tol:', 'if False:', 1),
    (u"B1 PrintWindow 对 NOREDIR 也当读数", "instr", u"B1 ",
     '"printwindow_is_reading": ("noredir" not in name),',
     '"printwindow_is_reading": True,', 1),
    (u"B3 空帧判据压上裸窗客户区", "instr", u"B3 ",
     'return {"blank_on_client": False,', 'return {"blank_on_client": True,', 1),
    (u"B4 层序闸门关掉", "instr", u"B4 ",
     '"layer_gate": True}', '"layer_gate": False}', 1),
    (u"B5 屏位筛选少筛上侧（y=0 那一格放回来）", "instr", u"B5 ",
     'return [p for p in pts if p[2] >= ring and p[2] + BS.WIN_H + ring <= vh',
     'return [p for p in pts if p[2] + BS.WIN_H + ring <= vh', 1),
    (u"B6 环带塌侧不点名", "instr", u"B6 ",
     '("n/a" if v is None else ("%.1f" % v if s == 4 else',
     '("n/a" if v is None else ("%.1f" % v if True else', 1),
    (u"C2 LEVER_DEAD 那支写成挡场（分支撞车）", "instr", u"C2 ",
     'kinds.append("LEVER_DEAD_ON_BARE")', 'kinds.append("SURFACE_BLOCKS")', 1),
    (u"C3 带表面那侧恒判不跟", "instr", u"C3 ",
     'na, nb = abs(ta[2]) >= track_min, abs(tb[2]) >= track_min',
     'na, nb = abs(ta[2]) >= track_min, False', 1),
    (u"C5 ①失明不再整场判废", "instr", u"C5 ",
     'if ctl[0] != "TRACKING":', 'if False:', 1),
    (u"C7 桌面自走报成量具判废", "instr", u"C7 ",
     'if ctl and ctl[0] == "INVALID_DRIFT":', 'if False:', 1),
    (u"C9 缺轮的理由混进失明那条", "instr", u"C9 ",
     'if not ctl or ctl[0] == "UNPAIRED":', 'if not ctl:', 1),
    (u"E1 满场也判 2", "instr", u"E1 ",
     'if n_have < n_expect:', 'if n_have <= n_expect:', 1),
    (u"E2 缺 5 行以内当满场", "instr", u"E2 ",
     'if n_have < n_expect:', 'if n_have < n_expect - 5:', 1),
    (u"E3 环境档整档摘掉", "instr", u"E3 ",
     'if env_hit:' + NL + '        return 4,', 'if False:' + NL + '        return 4,', 1),
    (u"E4 判废优先级压到环境之后", "instr", u"E4 ",
     'if aborts:', 'if aborts and not env_hit:', 1),
    (u"E5 入场端口范围缩短", "instr", u"E5 ",
     'PORT_RANGE = range(9411, 9417)', 'PORT_RANGE = range(9411, 9415)', 1),
    (u"F1 redir 那侧也带上 NOREDIR 位（单变量破坏）", "instr", u"F1 ",
     '("bare-redir-mica", 0, "mica",',
     '("bare-redir-mica", WS_EX_NOREDIRECTIONBITMAP, "mica",', 1),
    (u"F2 配对时顺手换掉材质", "instr", u"F2 ",
     '("bare-redir-acrylic", 0, "acrylic",', '("bare-redir-acrylic", 0, "mica",', 1),
    (u"F3 跨材质配对", "instr", u"F3 ",
     '("bare-noredir-acrylic", "bare-redir-acrylic", "Acrylic")]',
     '("bare-noredir-acrylic", "bare-redir-mica", "Acrylic")]', 1),
    (u"F4 裸窗标题撞上场窗名", "instr", u"F4 ",
     'BARE_TITLE = "FQBARESURF"', 'BARE_TITLE = "FQFIELD"', 1),
    (u"F5 本尺的 NOREDIR 常量漂回 WINDOWEDGE", "instr", u"F5 ",
     'WS_EX_NOREDIRECTIONBITMAP = 0x00200000', 'WS_EX_NOREDIRECTIONBITMAP = 0x00080000', 1),
    (u"F5b smoke_ship 那份参照漂了", "smoke", u"F5 ",
     'WS_EX_NOREDIRECTIONBITMAP(0x200000)', 'WS_EX_NOREDIRECTIONBITMAP(0x80000)', 1),
    (u"F5c 产品宿主 FqHost.cs 那份参照漂了", "cs", u"F5 ",
     'WS_EX_NOREDIRECTIONBITMAP = 0x00200000', 'WS_EX_NOREDIRECTIONBITMAP = 0x00080000', 1),
    (u"G1 取第一轮而不是漂得狠的那轮", "instr", u"G1 ",
     'r, tag = max(cand, key=lambda x: x[0]["drift"])', 'r, tag = cand[0]', 1),
    (u"G2 把两轮数拼成现场不存在的差（now/base 交换）", "instr", u"G2 ",
     'return tag, r.get("other_now"), r.get("other_base"), r.get("drift")',
     'return tag, r.get("other_base"), r.get("other_now"), r.get("drift")', 1),
    (u"G3 候选过滤到一只轮都不剩", "instr", u"G3 ",
     'if r and "drift" in r]', 'if False]', 1),
]

# 附录：这条守卫摘掉后**不会**变成某条断言的红，而是让量具自己在真跑路径上 KeyError 崩掉。
# 可接受结局只有两种：红（点名）或崩（rc 不为 0）；若 rc 仍为 0，那是真漏网，判这一趟不过。
APPENDIX = [
    (u"GUARD 缺 client 键的守卫摘掉（A8 的 fixture 形状）", "instr", u"A8 ",
     'if not bright or not dark or "client" not in bright or "client" not in dark:',
     'if not bright or not dark:', 1),
]

# 假阳性对照：只改注释／docstring 的措辞，不许翻红。
FP = ("instr", u'"""这一只读数的空帧判据打在哪儿——这是本轮最容易自己造出来的一条假阳性。',
      u'"""这一只读数的空帧判据打在哪儿——这是本轮最容易自己造出来的一条假阳性（措辞对照）。')


def run_copy():
    # -B 是这条链上一趟真踩过的坑换来的：A1/A2 那两条变异**注下去字节长度不变**
    # （只是把 bright 和 dark 调了个位），子进程按 mtime(秒)＋size 判定 .pyc 仍然有效，
    # 于是它 import 到的是上一趟的旧字节码 ⇒ 假漏网（rc=0）。证伪器如果自己复用缓存，
    # 它报的"漏网"就不是量具的漏网，而是证伪器自己的失明。
    drop_pycache()
    try:
        return subprocess.run([sys.executable, "-B", "-X", "utf8", DRV, COPY["self"]],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              cwd=SBX, env=dict(os.environ, PYTHONIOENCODING="utf-8",
                                                PYTHONDONTWRITEBYTECODE="1", FQ_ACC=HERE),
                              timeout=180)
    except subprocess.TimeoutExpired as e:
        return _Fake(99, u"TIMEOUT（副本 180 s 没回来，按未点名计）", u"%s" % e)


def drop_pycache():
    """每趟跑前把 ACC 下的 __pycache__ 清掉：与 -B 是两道独立的兜（一道漏了另一道还在）。"""
    d = os.path.join(ACC, "__pycache__")
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)


class _Fake(object):
    def __init__(self, rc, out, err):
        self.returncode, self.stdout, self.stderr = rc, out, err


def read(path):
    return io.open(path, encoding="utf-8").read()


def write(path, text):
    io.open(path, "w", encoding="utf-8").write(text)


def census():
    """入场记录：别的像素链在不在场。本脚本不碰像素，但仍把证据打出来。"""
    sys.path.append(HERE)
    try:
        import probe_mica5 as M5
        import exp_host_surface as X
        wins = len(M5.find_title(X.G.GTITLE)) + len(M5.find_title("FQFIELD")) + \
            len(M5.find_title(X.BARE_TITLE))
        busy = X.ports_busy()
    except Exception as e:
        return u"（取不到：%r）" % e, True
    return u"场窗＋裸窗数=%d，9411–9416 有人在听=%s" % (wins, busy or u"无"), (wins == 0 and not busy)


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    line, ok = census()
    print(u"入场：%s（本脚本不碰像素；就地改文件的趟一次只许跑一趟）" % line, flush=True)
    if not ok:
        print(u"ABORT rc=2：有别的像素链在场，本趟不跑（免得两趟互踩）。", flush=True)
        return 2
    for d in (ACC, NAT):
        if os.path.isdir(d):
            print(u"ABORT rc=2：沙箱已存在，不覆盖别人的趟：%s" % d, flush=True)
            return 2
    os.makedirs(ACC)
    os.makedirs(NAT)
    for p in (INSTR, SELF, SMOKE, CS):
        shutil.copyfile(p, os.path.join(ACC if p != CS else NAT, os.path.basename(p)))
    write(DRV, NL.join([
        "# -*- coding: utf-8 -*-",
        "import importlib.util, os, sys",
        "acc = os.environ['FQ_ACC']",
        "if acc not in sys.path:",
        "    sys.path.append(acc)",
        "spec = importlib.util.spec_from_file_location('fq_hs_selftest', sys.argv[1])",
        "m = importlib.util.module_from_spec(spec)",
        "sys.modules['fq_hs_selftest'] = m",
        "spec.loader.exec_module(m)",
        "rc = m.main()",
        "for x in list(getattr(m, 'FAILS', []) or []):",
        "    print('FAIL:', x)",
        "sys.exit(0 if (rc == 0 and not getattr(m, 'FAILS', [])) else 1)",
        ""]) + NL)
    bases = dict((k, read(v)) for k, v in COPY.items())
    r = run_copy()
    out0 = (r.stdout or u"") + (r.stderr or u"")
    print(u"原件副本（未变异）rc=%s，结论行：%s" % (r.returncode,
          out0.strip().split(NL)[-1][:120]), flush=True)
    if r.returncode != 0:
        print(u"ABORT rc=2：原件自检就没过，别拿它当基线。", flush=True)
        shutil.rmtree(SBX, ignore_errors=True)
        return 2
    caught = nops = missed = crashed = 0
    eq_len = 0
    for label, role, want, old, new, cnt in MUTS:
        base = bases[role]
        n = base.count(old)
        if n == 0:
            print(u"NOP    %-42s 锚点不在 %s 里" % (label, role), flush=True)
            nops += 1
            continue
        if n != cnt:
            print(u"NOP    %-42s 锚点在 %s 里出现 %d 次（期望 %d，不唯一就不注）"
                  % (label, role, n, cnt), flush=True)
            nops += 1
            continue
        mut = base.replace(old, new, cnt)
        if mut == base:
            print(u"NOP    %-42s 注下去文本没变（变异失效，不算抓到）" % label, flush=True)
            nops += 1
            continue
        if len(mut) == len(base):
            eq_len += 1          # 等长变异＝.pyc 复用那一型的哨兵，条数由这里数出来
        write(COPY[role], mut)
        try:
            r = run_copy()
            out = (r.stdout or u"") + (r.stderr or u"")
            if r.returncode == 0:
                print(u"MISSED %-42s 副本自检仍然 rc=0 ⇒ %s 没被任何已知答案钉住" % (label, want), flush=True)
                missed += 1
            elif want in out and u"FAIL:" in out:
                print(u"CAUGHT %-42s（红话里点了「%s」）" % (label, want.strip()), flush=True)
                caught += 1
            else:
                print(u"CRASH  %-42s rc=%s 但红话里没点到「%s」→ 不算抓到：%s"
                      % (label, r.returncode, want.strip(), out.strip().split(NL)[-1][:140]), flush=True)
                crashed += 1
        finally:
            write(COPY[role], base)
    # 附录（守卫型）：允许红，也允许崩；只有 rc=0 才算真漏网。
    ap_ok = True
    for label, role, want, old, new, cnt in APPENDIX:
        base = bases[role]
        if base.count(old) != cnt:
            print(u"附录   %-42s 锚点不唯一/未命中（%d 次）⇒ 本条不作数" % (label, base.count(old)), flush=True)
            ap_ok = False
            continue
        write(COPY[role], base.replace(old, new, cnt))
        try:
            r = run_copy()
            out = (r.stdout or u"") + (r.stderr or u"")
            tag = (u"附录-CRASH（守卫摘掉后副本自己崩，红话没点名：%s）" % want.strip()
                   if r.returncode != 0 and want not in out else
                   u"附录-CAUGHT（%s 真点名了）" % want.strip() if r.returncode != 0 else
                   u"附录-MISSED（守卫摘掉后仍 rc=0 ⇒ 真漏网）")
            print(u"%s  %-42s rc=%s" % (tag, label, r.returncode), flush=True)
            if r.returncode == 0:
                ap_ok = False
        finally:
            write(COPY[role], base)
    # 假阳性对照：只改措辞。
    role, old, new = FP
    base = bases[role]
    if base.count(old) != 1:
        print(u"假阳性对照：锚点不唯一/未命中（%d 次）⇒ 判不过" % base.count(old), flush=True)
        ok_fp = False
    else:
        write(COPY[role], base.replace(old, new, 1))
        try:
            ok_fp = run_copy().returncode == 0
        finally:
            write(COPY[role], base)
        print(u"假阳性对照（只改 docstring 措辞）rc=%s" % (u"0" if ok_fp else u"非 0"), flush=True)
    shutil.rmtree(SBX, ignore_errors=True)
    total = len(MUTS)
    good = (caught == total and nops == 0 and missed == 0 and crashed == 0 and ok_fp and ap_ok)
    print(u"抓到 %d/%d，NOP %d，漏网 %d，未点名 %d（其中等长变异 %d 条＝靠 -B＋清缓存才不被 .pyc 吞掉那一型）；"
          u"附录 %s；假阳性对照 %s ⇒ %s" % (
        caught, total, nops, missed, crashed, eq_len,
        u"OK（摘守卫要么崩要么红，没有静默放行）" if ap_ok else u"不过",
        u"仍绿" if ok_fp else u"翻红", u"PASS" if good else u"FAIL"), flush=True)
    print(u"量具出处：exp_host_surface md5 见报告，沙箱=%s（已删）" % SBX, flush=True)
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
