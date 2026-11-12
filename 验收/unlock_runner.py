# -*- coding: utf-8 -*-
"""解锁即自动跑完整像素链，不再需要人守着。
   1) 每 20 秒问一次桌面是否回到 Default（解锁＋显示器点亮）；
   2) 一旦可用，按顺序跑 smoke_ship（三材质）→ selftest＋mutate（先把量具判死）→
      probe_glass（三材质×浅/深＝六轮）→ page_regress（旧路径回归＋变异自检）→
      shot_desktop（真桌面实拍六轮，A/B/C/D 四闸门跑在落盘字节上）；
   3) 结论全部落到 %LOCALAPPDATA%\\fq-glass-verify\\FINAL-<UTC 秒>.md，
      并在同目录写 DONE 哨兵文件（外部脚本可判"跑完了"）。
   上限 8 小时；超时或中途中断也要留下"跑到哪一步了"的日志，不能静默。
   每一大步都自带超时（smoke 5 min、离线自检 2 min、变异证伪 15 min、probe 六轮 45 min、
   page_regress 2 min + 变异 8 min、实拍 25 min），单步挂了不阻断下一步，
   只是把它的 rc/stdout tail 记进 FINAL。像素步一律串行：端口 9411-9416 与场窗 FQFIELD
   都是一个进程一份，并行会互相盖场。"""
import os, sys, time, subprocess, shutil, io, glob
import ctypes, datetime as dt

TOOLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "验收")
sys.path.insert(0, TOOLS_DIR)
import probe_mica5 as M5          # 解锁判据只有一份，在 probe_mica5.desktop_ready()

U = ctypes.WinDLL("user32", use_last_error=True)
OUT = os.path.join(os.environ["LOCALAPPDATA"], "fq-glass-verify")
os.makedirs(OUT, exist_ok=True)
STAMP = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
LOG = os.path.join(OUT, "unlock_runner-%s.log" % STAMP)
FINAL = os.path.join(OUT, "FINAL-%s.md" % STAMP)
DONE = os.path.join(OUT, "DONE-%s.ok" % STAMP)
SHIP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(SHIP, "验收")

def log(msg):
    s = "[%s] %s" % (dt.datetime.utcnow().isoformat("T"), msg)
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write(s + "\n")
    print(s, flush=True)

def desktop_ready():
    # 判据订正（原委写在 probe_mica5.ready_from 的注释里）：唯一可信的解锁信号是输入桌面名回到
    # Default；SM 7/8 是对话框边框宽（恒 ~3×3），当年拿它当"屏已点亮"让这个看门狗永远不触发。
    # 这里不再自己抄一份实现，避免"两个检测器、两套判据、互相覆盖"重演。
    return M5.desktop_ready()

# ---------- 1) 等解锁 ----------
log("watching for Default desktop; deadline 8 h")
t0 = time.time()
while time.time() - t0 < 8 * 3600:
    ok, why = desktop_ready()
    if ok:
        log("DESKTOP READY (%s) 等待 %.1f min" % (why, (time.time() - t0) / 60.0))
        break
    time.sleep(20)
else:
    log("TIMEOUT 8 h 内桌面没解锁，FINAL 只记这一步")
    with io.open(FINAL, "w", encoding="utf-8") as f:
        f.write("# 玻璃像素链 · 未跑（桌面 8 小时内没解锁）\n\n看门狗 %s 到点退出。手动重跑：`python 验收\\smoke_ship.py` 与 `python 验收\\probe_glass.py`。\n" % STAMP)
    open(DONE, "w").write("timeout\n")
    sys.exit(0)

# 解锁瞬间桌面可能仍在动；再稳 3 秒才让下一步采像素
time.sleep(3.0)

steps = []

def run(name, argv, timeout):
    log("== %s ==" % name)
    t = time.time()
    try:
        p = subprocess.run(argv, cwd=SHIP, capture_output=True, timeout=timeout,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        rc = p.returncode
        out = (p.stdout or b"").decode("utf-8", errors="replace")
        err = (p.stderr or b"").decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        rc, out, err = -1, "", "TIMEOUT after %d s" % timeout
    secs = time.time() - t
    steps.append((name, rc, secs, out, err))
    log("%s rc=%d secs=%.1f out-tail=%r" % (name, rc, secs, out[-160:].replace("\n", " | ")))
    return rc

# ---------- 2) 三材质预检（smoke_ship 不带参数＝内部一次跑齐 mica/acrylic/none） ----------
run("smoke_ship (all modes)", ["python", os.path.join(TOOLS, "smoke_ship.py")], 300)

# ---------- 2.5) 量具先判死再用量具（离线，不需要屏；这两步红了后面的像素数都不作数） ----------
run("selftest_probe_instr (A-H 全组)", ["python", os.path.join(TOOLS, "selftest_probe_instr.py")], 120)
run("mutate_selftest (67 个变异逐条要求变红)", ["python", os.path.join(TOOLS, "mutate_selftest.py")], 900)

# ---------- 3) 像素探测（probe_glass 不带参数＝K3/Mica/Acrylic × 浅/深，共六轮） ----------
# 每轮约 3–5 分钟（六种背景场 × K5 顶窗 × K1/K2 变异段 × K6/K7 对照），CDP 接不上还整轮重来一次。
# CDP 接不上那一档的预算是墙钟 120 秒／次、最多三次重试 ⇒ 单轮最坏多花 6 分钟（这是按源码算的上界，
# 不是本机实测；第 19 次跑到第六轮就断了，从没留下一份"六轮整趟实际耗时"）。2700s 是照六轮 ×
# (5 分钟 + 最坏重试) 留的余量；拿到第 20 次实测后按 FINAL 里的数订正，别顺手加。
run("probe_glass (light x3 + dark x3)", ["python", os.path.join(TOOLS, "probe_glass.py")], 2700)

# ---------- 4) 页面级回归（此时桌面已解锁；跑的是交付目录里那份） ----------
run("page_regress (edge-equivalent path)",
    ["python", os.path.join(TOOLS, "page_regress.py")], 120)
run("page_regress --mutate (self-test)",
    ["python", os.path.join(TOOLS, "page_regress_mutate.py")], 500)

# ---------- 5) 真桌面实拍（合成后的地面真相；判据跑在重开 PNG 之后的字节上） ----------
# 六轮各起一次窗，每轮 1–2 分钟；再加一遍空桌面对照（防 A 闸门恒绿）。留 1500s。
# 前一步（probe_glass／page_regress）收窗后，WebView2 的浏览器进程还会赖着几十秒——
# 第 19 次实拍到它就是"端口在听、/json 只 ReadTimeout，监听者＝自己人还没退净"。
# shot_desktop 起手会因为场上还有 FQGLASS 窗而拒绝跑（串行铁律），所以这里先等场清干净，
# 而不是让下一步直接失败；等不到就照常提交，让 shot_desktop 自己判废（不替它放宽闸门）。
def wait_field_clear(budget=120.0):
    t_end = time.time() + budget
    while time.time() < t_end:
        titles = []
        try:
            titles = list(M5.find_title("FQGLASS")) + list(M5.find_title("FQFIELD"))
        except Exception as e:
            log("find_title 炸了：%r" % e)
            return False
        if not titles:
            return True
        time.sleep(2.0)
    log("WARN 120 秒后场上仍有窗句柄 %s（不替 shot_desktop 放宽闸门，让它自己判废）" % titles)
    return False


wait_field_clear()
run("shot_desktop (六轮实拍＋空桌面对照)", ["python", os.path.join(TOOLS, "shot_desktop.py")], 1500)

# ---------- 6) 写 FINAL ----------
arts = sorted(glob.glob(os.path.join(OUT, "shots-*.md")) + glob.glob(os.path.join(OUT, "*.png"))
              + glob.glob(os.path.join(OUT, "probe-*.log")) + glob.glob(os.path.join(OUT, "glass-*.md")),
              key=os.path.getmtime)[-40:]
with io.open(FINAL, "w", encoding="utf-8") as f:
    f.write("# 玻璃像素链 · 自动跑完 %s\n\n" % STAMP)
    f.write("每步都自带 rc；rc=0 且 tail 里出现 ALL-OK/OK 才算真绿。中间产物写在本目录。\n\n")
    for name, rc, secs, out, err in steps:
        f.write("## %s — rc=%d (%.1fs)\n\n```\n%s\n```\n\n" % (name, rc, secs, (out or err)[-4000:]))
    f.write("## 本轮产物（按时间取最近 40 个）\n\n")
    for a in arts:
        f.write("- `%s`（%d KB）\n" % (a, os.path.getsize(a) // 1024))
open(DONE, "w").write("ok %s\n" % STAMP)
log("FINAL written %s ; DONE %s" % (FINAL, DONE))
