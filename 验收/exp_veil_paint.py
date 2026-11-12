# -*- coding: utf-8 -*-
"""实验：把「页面自己把场挡住了」和「材质根本没采这块场窗」分开（#37 的机制候选）。

已知现场（都有出处，不是猜测）：
  - probe 第 20/21 次：六轮的「黑场／白场」客户区均值**一模一样**（Acrylic 浅 183.5／183.9），
    而同一批改场里窗外的环带极差 255 ⇒ 场确实画进了屏幕采集，只是客户区不动。
  - 更早的原型测量（说明§6）里 Acrylic 斜率 +0.360、红场彩度渗透 +132 ⇒ 同一个 exe、
    同一类场窗，那时候是能透的。
两个候选各自预测什么，事先写死在这儿（跑之前不许改）：
  C 页面不透明：body 的色调帽／环境光层／控件底把 backdrop 盖住了。
      预测：**逐档放开页面喷涂，客户区对场的反应应当从零涨起来**；
      按 CSS 令牌 --veil-a=.55，出厂档就算有反应也该是「放开档」的约 45%，不是零。
  A/B backdrop 没采这块场窗（只采壁纸／或走系统底色）。
      预测：**把页面喷涂全放开（C3 档）客户区仍然不动**。
                        此时还有一条鉴别力很强的对照：`--none`（无 backdrop）在 C3 档
      应当**直接看见场**（窗口就是一层透明网页），如果连它都不动，问题在网页透明链
      （WebView2 的默认底色）而不是 DWM 材质——那是第三种解释，也必须由这条实验区分开。
  负对照 Mica：按 Windows 语义 Mica 只采壁纸、不采相邻窗 ⇒ 各档都该 ≈0。
      如果 Mica 出现大反应，说明这条实验本身有问题，不许把它的数当机制结论。

像素链与端口与 probe_glass 互斥：本脚本同样要求盘上没有 FQGLASS／FQFIELD，且串行跑。
产物：OUT\\veil-paint-<STAMP>.md（带三份脚本 md5 与逐档数字）。

—— 2026-10-09 夜补的**环境处置纪律**（只加这一段，上面那条判读规则一个字没动）：
第 1 次真跑（FINAL-veil-20261009T165216Z.md，rc=1，168 秒）三档全没出行，死因是环境而不是量具：
  · Acrylic：CDP 120 秒接不上（`/json` 一直 ReadTimeout）；
  · Mica／不透参照：都已报到 `veil 令牌=--veil-a=.55` 那一步，然后
    `capture failed after 4 tries: rc=0 lines=1414 gle=6`。
gle=6 的直测复现（锁屏下同样能跑的那份诊断）：BitBlt 在输入桌面不是 `Default` 时恒返回 0，
加不加 CAPTUREBLT 都一样 ⇒ "就绪"不等于"接下来五分钟一直就绪"。所以：
  · 采不到帧／接不上通道 ⇒ 抛 EnvUnavailable，交给**整趟重试**；不许就地降级成"这一轮没数"
    （那就是第 1 次交白卷的形状）；
  · 页面态钉不住、ablate 没落上 ⇒ 那是量具/实验自身的问题，只点名、不重试；
  · 两种失败在报告与 rc 里分开（见 classify）。
"""
import hashlib
import json
import os
import sys
import time
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ctypes as c
import ctypes.wintypes as w
import probe_mica5 as M5
import probe_glass as G
import shot_desktop as SD
from probe_mica5 import u, wt, lum

OUT = G.OUT
STAMP = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
REPORT = os.path.join(OUT, "veil-paint-%s.md" % STAMP)

# 材质 ×（档, CSS 注入文本）。档号越小＝越接近出厂状态。
MATS = (("--acrylic", "acrylic", 9413, "Acrylic"),
        ("--mica", "mica", 9412, "Mica"),
        ("--none", "0", 9411, "不透参照"))
VEIL_OFF = "html[data-glass] body::before{background:none !important}"
AMB_OFF = ".amb{display:none !important}"
ALL_OFF = ("*,*::before,*::after{background:transparent !important;"
           "background-image:none !important;box-shadow:none !important}")
CONFIGS = (("C0 出厂", ""),
           ("C1 摘帽", VEIL_OFF),
           ("C2 摘帽＋关环境光", VEIL_OFF + AMB_OFF),
           ("C3 页面全放开", VEIL_OFF + AMB_OFF + ALL_OFF))
PORTS_RESERVED = set(x[2] for x in G.COMBOS)
RESPONSE_OK = 20.0      # 反应「看得见」的门槛（客户区均值差，亮度单位）
RESPONSE_ZERO = 5.0     # 反应「确实没有」的门槛
RING_MIN = 30.0         # 环带（场自己的像素）低于这个差 ⇒ 那一刻场没进采集

# 表头就是行的唯一定义：写行必须过 add_row，它对不上列宽当场抛，
# 免得"加了字段忘了加表头"这种错变成报告里整列错位——那种错位没人会看出来。
ROW_COLS = ("材质", "趟", "页面态", "档", "客户区均值(黑白中点)",
            "反应(白-黑)", "环带反应", "黑", "白")

START_T = time.time()
WALL_BUDGET = 1400.0        # 本脚本墙钟上限（看门狗给 2100 秒，留 700 秒余量）
SWEEP_TRIES = 3             # 环境打断后整趟最多重开几回
SWEEP_COOLDOWN = 45.0
ENV_WAIT_SWEEP = 240.0      # 每趟开头：等"能采"最多 4 分钟
ENV_WAIT_MATERIAL = 90.0    # 一窗之内：屏保插手时等 90 秒（大头交给整趟重试）


def budget_left():
    return WALL_BUDGET - (time.time() - START_T)


def mean(px):
    return sum(lum(p) for p in px) / float(len(px))


def add_row(rows, *vals):
    if len(vals) != len(ROW_COLS):
        raise RuntimeError("行宽 %d ≠ 表头 %d 列（%s）⇒ 宁可这轮没数，也不交一份错位的报告"
                           % (len(vals), len(ROW_COLS), "、".join(ROW_COLS)))
    rows.append(vals)
    return rows


def ablate(cdp, css):
    """注入/清空那一份 ablate 样式，并**当场回读**它落在页面上的原文。

    回读不是仪式：这条实验的自变量就是「页面还喷不喷涂」，如果注入没落上，
    后面每一档的数字都是在骗人说「放开之后仍然不透」。
    （前三次跑不出行，全栽在这段字符串拼出的 JS 语法上：IIFE 的括号配平肉眼判不住，
    所以这里写成扁平的多语句脚本——只有一层花括号，且用 CDP 的 completion value 取回读，
    不再靠 "})(" 收尾。落没落上由下面那条「回读必须逐字等于注入文本」的闸门说了算。）
    """
    js = ("var s=document.getElementById('fq-ablate');"
          "if(!s){s=document.createElement('style');s.id='fq-ablate';"
          "document.head.appendChild(s);}"
          "s.textContent=" + json.dumps(css) + ";"
          "s.textContent")
    got = cdp.ev(js)
    if (got or "") != css:
        raise RuntimeError("ablate 没落上（要求 %d 字，回读 %s 字）⇒ 这一档不作数"
                           % (len(css), len(got or "")))
    return got


def veil_tokens(cdp):
    st = "getComputedStyle(document.documentElement)"
    return (cdp.ev(st + ".getPropertyValue('--veil-a')").strip(),
            cdp.ev(st + ".getPropertyValue('--veil-rgb')").strip())


class EnvUnavailable(RuntimeError):
    """采不到合成帧／接不上调试通道／桌面又回到 Screen-saver——这是**环境**不配合，
    不是量具判废，也不是实验结论。分家的理由（同 probe_glass 里 ENV-FAIL 与 RuntimeError
    分家那条）：环境失败重试是正当的，判废重试只会把噪声洗成"看起来对"的数。"""


def capture_canary():
    """起窗之前先问一句"屏幕 DC 现在能不能 BitBlt"。

    第 1 次实跑（16:56:36Z 就绪）三条材质全没出行：CDP 120 秒接不上、
    客户区采集 `rc=0 lines=1414 gle=6`（BitBlt 返回 0＝ERROR_INVALID_HANDLE）。
    gle=6 正是输入桌面又切回 Screen-saver 的形状——也就是说"就绪"不等于"接下来五分钟一直就绪"。
    一次 64×64 的角落采集就能提前判掉这件事，不用白起三次窗、白等三次 CDP。
    """
    ok, why = M5.desktop_ready()
    if not ok:
        return False, "输入桌面=%s（不是 Default）" % why
    try:
        M5.shot(0, 0, 64, 64, tries=2)
    except Exception as e:
        return False, "屏幕 DC 采不动：%s" % str(e)[:120]
    return True, "就绪且能采"


def attach(port, h, proc, tries=3):
    """接 CDP 最多三回：第 1 次实跑里 Acrylic 那回是 `/json 120 秒只 ReadTimeout`，
    现场写的监听者是"自己人（早先起过、还没退净）"——这类等待重试能过，probe_glass 也给了三次。"""
    last = None
    for k in range(tries):
        try:
            return G.CDP(port, "index.html", host=h, proc=proc)
        except G.CDPAttach as e:
            last = e
            print("    attach 第 %d/%d 回没接上：%s" % (k + 1, tries, str(e)[:110]), flush=True)
            time.sleep(5.0)
    raise EnvUnavailable("CDP 三回都接不上（port %s）：%s" % (port, str(last)[:150]))


def one_field(cdp, fw, h, box, name, rgb):
    """改场→顶窗→确认层序→采客户区＋环带；返回 (客户区均值, 环带均值, 层序OK, 挡在前面的)。"""
    ring = (box[0] + box[2] + 60, box[1] + 60, 50, 50)
    ok = False
    blockers = []
    for _ in range(4):
        fw.set_field(rgb=rgb)
        G.above(h)
        time.sleep(0.6)
        G.above(h)
        time.sleep(0.6)
        ok, blockers = G.cover_ok(h, box)
        if ok:
            break
    # 采集失败在这里**必须**转成 EnvUnavailable：第 1 次实跑就是这两行抛的裸 RuntimeError
    # 被 one_material 就地吃掉，于是"屏保一插手"和"这一轮真的没数据"长得一模一样，
    # 整趟实验安静地交了白卷。抛错类型的分工：环境＝重试，量具＝只点名。
    try:
        px, _ = G.grab(*box)
        rp, _ = G.grab(*ring)
    except Exception as e:
        raise EnvUnavailable("采集失败（场=%s，客户区 %dx%d）：%s ⇒ 这一档不作数，交给整趟重试"
                             % (name, box[2], box[3], str(e)[:120]))
    return mean(px), mean(rp), ok, blockers[:2]


def one_material(flag, glass, port, tag, rows, sweep_no, env_wait_s=ENV_WAIT_MATERIAL):
    print("\n=== %s（%s，第 %d 趟） ===" % (tag, flag, sweep_no), flush=True)
    # 环境闸门：采不动就等（而不是起窗）。等待受两个上限夹：本窗的 env_wait_s 与整趟墙钟。
    # 到点仍不行 ⇒ 抛 EnvUnavailable，让 main 的"整趟重试"接手；绝不把空帧当成"材质不透"的数字写进表里。
    t_end = time.time() + max(0.0, min(env_wait_s, budget_left()))
    while True:
        ok, why = capture_canary()
        if ok:
            break
        if time.time() > t_end or budget_left() <= 0:
            raise EnvUnavailable("等了 %.0f 秒仍然采不动（%s）｜整趟剩余预算 %.0f 秒"
                                 % (env_wait_s, why, budget_left()))
        print("  ENV-WAIT %s ⇒ 8 秒后重试（%s）" % (tag, why), flush=True)
        time.sleep(8.0)
    reserved = PORTS_RESERVED - {port}
    ready, why = G.wait_port_free(port)
    if not ready:
        print("  WAIT %s（%s）" % (port, why), flush=True)
    port, note = G.pick_port(port, reserved=reserved)
    if note:
        print("  PORT %s" % note, flush=True)
    h, proc, cl, txt = G.launch(flag, glass, port, tag)
    if not h:
        # 起窗失败分两种：桌面此刻本来就不能用（环境）vs 桌面能用、exe 自己没起起来（真失败）。
        # 前者要交给整趟重试，后者点名即可——所以这里再问一次金丝雀，而不是写死一种。
        c_ok, c_why = capture_canary()
        if not c_ok:
            raise EnvUnavailable("起窗失败且桌面采不动（%s）：%s" % (c_why, txt[:120]))
        print("  ABORT 起窗失败：%s（这一轮的数不进报告）" % txt, flush=True)
        return
    cx, cy, cw, chh = cl
    box = (cx, cy, cw, chh)
    print("  宿主自报 %s" % txt[:200], flush=True)
    try:
        cdp = attach(port, h, proc)
    except EnvUnavailable:
        G.teardown(h, proc)
        raise
    try:
        cdp.ev(SD.FREEZE_JS)
        pin = json.loads(cdp.ev(G.PIN_JS) or "{}")
        st = G.state_of(cdp.ev(G.STATE_JS))
        sk = G.state_key(st)
        print("  页面态=%s（pin=%s）" % (sk or "读不到", pin.get("status", pin.get("err", "?"))),
              flush=True)
        if sk is None or pin.get("err"):
            raise RuntimeError("页面态钉不住 ⇒ 不知道量的是哪个界面")
        G.apply_theme(cdp, "light")
        va, vr = veil_tokens(cdp)
        print("  veil 令牌：--veil-a=%s --veil-rgb=%s" % (va or "(空)", vr or "(空)"), flush=True)
        fw = G.fld()
        for cname, css in CONFIGS:
            ablate(cdp, css)
            out = {}
            for fname, rgb in (("黑", (0, 0, 0)), ("白", (255, 255, 255))):
                m, rm, ok, bl = one_field(cdp, fw, h, box, fname, rgb)
                out[fname] = (m, rm, ok)
                if not ok:
                    print("  %s/%s 层序 BAD：%s ⇒ 这一档不作数" % (cname, fname, bl), flush=True)
            if not (out["黑"][2] and out["白"][2]):
                continue
            delta = out["白"][0] - out["黑"][0]
            ring_delta = out["白"][1] - out["黑"][1]
            base = (out["黑"][0] + out["白"][0]) / 2.0
            add_row(rows, tag, sweep_no, sk, cname, base, delta, ring_delta,
                    out["黑"][0], out["白"][0])
            print("  %-16s 客户区 %6.1f 黑／%6.1f 白 ⇒ 反应 %+6.1f ｜ 环带反应 %+6.1f ｜ 均值 %6.1f"
                  % (cname, out["黑"][0], out["白"][0], delta, ring_delta, base), flush=True)
    except EnvUnavailable:
        raise                          # 环境不配合：交给上层整趟重试，不许降级成"这一轮的数不进报告"
    except (RuntimeError, G.CDPAttach) as e:
        print("  ABORT %s：%s（这一轮的数不进报告）" % (tag, str(e)[:180]), flush=True)
    finally:
        G.teardown(h, proc)


def verdict(rows):
    lines = []
    for tag, sw, sk, cname, base, delta, ring_delta, bm, wm in rows:
        if cname.startswith("C3"):
            if delta >= RESPONSE_OK:
                call = "放开页面喷涂就透 ⇒ 出厂那档不动是**页面**挡的（候选 C）"
            elif delta <= RESPONSE_ZERO:
                call = "页面全放开仍然不动 ⇒ 与页面无关，材质没采这块场（候选 A/B）"
            else:
                call = "半透（%+.1f 落在 %g～%g 之间）⇒ 两条候选都没被排除，需要下一刀" % (
                    delta, RESPONSE_ZERO, RESPONSE_OK)
            lines.append("%s（第 %s 趟，态=%s）｜C3 档：反应 %+0.1f ⇒ %s" % (tag, sw, sk, delta, call))
    mica = [r for r in rows if r[0] == "Mica" and r[3].startswith("C3")]
    if mica and mica[0][5] >= RESPONSE_OK:
        lines.append("注意：负对照 Mica 在 C3 档出现 %+0.1f 的反应 ⇒ Mica 按语义不该采相邻窗，"
                     "这条实验的采集/层序有问题，上面所有「机制结论」降级为未证实" % mica[0][5])
    ring = [r for r in rows if abs(r[6]) < RING_MIN]
    if ring:
        lines.append("环带反应不足 %g 的行：%s ⇒ 那些行所在的那一刻场没进采集，逐条重看再说"
                     % (RING_MIN, "、".join("%s/%s(%+0.1f)" % (t, n, d)
                                            for t, s, k, n, b, d, rd, x, y in ring)))
    states = sorted(set(r[2] for r in rows))
    if len(states) > 1:
        lines.append("页面态指纹不止一个：%s ⇒ 跨这些值的行**不许互相配对**，只在同一材质同一趟里读"
                     % "、".join(states))
    sweeps = sorted(set(r[1] for r in rows))
    if len(sweeps) > 1:
        lines.append("行来自不止一趟（%s）：这是环境打断后按材质补齐的结果。每趟是"
                     "「同一窗内 C0→C3 的完整四档」，档间配对不受影响；跨趟比的只有"
                     "「同一材质同一档没被测过两次」这一种情况，本表里没有出现。"
                     % "、".join(str(s) for s in sweeps))
    return lines


def classify(n_rows, missing, env_hit):
    """把"为什么没数"分成看门狗能分头处理的四类，写进 rc：
    0＝三种材质都有行；2＝部分有行、且不是环境造成（其余是量具/页面 ABORT，重试没意义）；
    1＝一行都没有、也不是环境造成；4＝环境打断过 ⇒ 该整趟重来。
    抽成纯函数是为了让前置检查在锁屏下就能喂坏样本判它有没有牙。"""
    if not env_hit and n_rows == 0:
        return 1
    if env_hit:
        return 4
    return 0 if not missing else 2


RC_NAME = {0: "FULL", 1: "EMPTY-INSTRUMENT", 2: "PARTIAL", 3: "REFUSE", 4: "ENV-BLOCKED"}


def fmt_cell(i, v):
    """表头与单元格的量纲在这儿一次说清：反应与环带反应带符号，均值/黑/白不带。
    页面态指纹本身带 `|`，不转义就会把 Markdown 的一行撑成九列以上——表看着齐、列全错位。"""
    if i in (5, 6) and isinstance(v, float):
        return "%+0.1f" % v
    if isinstance(v, float):
        return "%.1f" % v
    return str(v).replace("|", "\\|")


def write_report(rows, note, envs, acc):
    def md5(p):
        return hashlib.md5(open(p, "rb").read()).hexdigest()[:12]
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("# 页面喷涂 × backdrop 采样：机制分拣实验 %s\n\n" % STAMP)
        f.write("出处：`exp_veil_paint.py` md5=%s，`probe_glass.py` md5=%s，"
                "`shot_desktop.py` md5=%s，`index.html` md5=%s。\n\n%s\n\n"
                % (md5(os.path.abspath(__file__)), md5(os.path.join(G.HERE, "probe_glass.py")),
                   md5(os.path.join(G.HERE, "shot_desktop.py")),
                   md5(os.path.join(G.HERE, os.pardir, "index.html")), note))
        f.write("判读规则写在脚本头部、跑之前定死：C3 档反应 ≥%.0f ⇒ 页面挡的；"
                "≤%.0f ⇒ 材质没采这块场；中间 ⇒ 两条都没排除。"
                "环带反应（场自己的像素进没进采集）每行都跟着报，它是这条链路的正对照。\n\n"
                % (RESPONSE_OK, RESPONSE_ZERO))
        f.write("| %s |\n" % " | ".join(ROW_COLS))
        f.write("|%s|\n" % "|".join(["---"] * len(ROW_COLS)))
        for r in rows:
            f.write("| %s |\n" % " | ".join(fmt_cell(i, v) for i, v in enumerate(r)))
        if envs:
            f.write("\n## 环境打断记录（与『没有数据』分家）\n\n")
            for sw, why in envs:
                f.write("- 第 %s 趟：%s\n" % (sw, why))
            f.write("\n这一节说明「为什么有几档没数」是桌面／采集／调试通道不配合，"
                    "**不是**材质对这些档没有反应。缺的档在本表里是缺行，不是零。\n")
        missing = [tag for _, _, _, tag in MATS if not acc.get(tag)]
        if missing:
            f.write("\n## 缺整条材质的行：%s\n\n它们要么 ABORT（原因见 stdout/看门狗 FINAL），"
                    "要么被环境打断。空表不等于「没问题」，也不等于「机制已排除」。\n"
                    % "、".join(missing))
        if not rows:
            f.write("\n**一行都没有**：上面每条 ABORT／环境原因就是为什么没有。"
                    "别把空表读成「没问题」，也别读成「材质真的不透」。\n")
            return
        f.write("\n## 判\n\n")
        for ln in verdict(rows):
            f.write("- %s\n" % ln)
    return REPORT


def sweep(sweep_no, acc):
    """跑一遍「还没拿到行」的材质。返回 None＝这趟跑完整；返回字符串＝被环境打断的原因。

    只重跑缺的那几档，不是全推倒：一趟之内每种材质自带它的 C0→C3 四档与页面态，
    行与行的配对从不跨材质，所以补齐缺的材质不破坏判读。
    """
    todo = [m for m in MATS if m[3] not in acc]
    t_end = time.time() + max(0.0, min(ENV_WAIT_SWEEP, budget_left()))
    while todo:
        ok, why = capture_canary()
        if ok:
            break
        if time.time() > t_end or budget_left() <= 0:
            return "第 %d 趟开头就没等到可采的桌面（%s）｜剩余预算 %.0f 秒" % (
                sweep_no, why, budget_left())
        print("  SWEEP-ENV-WAIT 第 %d 趟开头：10 秒后再问（%s）" % (sweep_no, why), flush=True)
        time.sleep(10.0)
    for flag, glass, port, tag in todo:
        if budget_left() <= 120:
            return "跑 %s 之前剩余预算只剩 %.0f 秒 ⇒ 不开新窗（开了也大概率采不完）" % (tag, budget_left())
        rows = []
        try:
            one_material(flag, glass, port, tag, rows, sweep_no)
        except EnvUnavailable as e:
            return "%s：%s" % (tag, str(e)[:220])
        acc[tag] = rows
    return None


def main():
    if G.find_title(G.GTITLE) or G.find_title("FQFIELD"):
        print("REFUSE：桌面上还挂着 FQGLASS／FQFIELD ⇒ 另一个像素脚本在跑（端口与场窗都是一个进程一份）。",
              flush=True)
        return 3
    ready, why = M5.desktop_ready()
    if not ready:
        print("REFUSE：桌面没就绪（%s）⇒ 采不到合成帧" % why, flush=True)
        return 3
    note = ("本轮三种材质（Acrylic／Mica／不透参照）各起一窗，一窗之内逐档放开页面喷涂"
            "（C0 出厂→C3 全放开），每档各测黑场／白场。"
            "自变量只有 CSS 注入，窗口／端口／页面态／主题全程不动。")
    acc = {}
    envs = []
    for sw in range(1, SWEEP_TRIES + 1):
        if sw > 1:
            print("SWEEP %d/%d：上一趟被环境打断 ⇒ 冷却 %.0f 秒后只补还缺的材质。"
                  "场窗**不拆**：同一进程里再建第二座 Field 会撞上已注册的那个窗口类，"
                  "set_field 改的是新对象的色、画的却是旧对象的色（probe_glass.fld 的注释记着这条），"
                  "所以重跑只 reuse 不重建。" % (sw, SWEEP_TRIES, SWEEP_COOLDOWN), flush=True)
            time.sleep(SWEEP_COOLDOWN)
        env = sweep(sw, acc)
        if env is None:
            break
        envs.append((sw, env))
        print("SWEEP-ENV 第 %d 趟：%s" % (sw, env), flush=True)
        if budget_left() < 180:
            print("SWEEP-ENV 剩余预算 %.0f 秒，不足以再开一趟 ⇒ 收" % budget_left(), flush=True)
            break
    rows = [r for _, _, _, tag in MATS for r in acc.get(tag, [])]
    if G._FLD is not None:      # 没建过场窗就别为了收尾去建一座（fld() 是"没有就造"的）
        G._FLD.stop()
    missing = [tag for _, _, _, tag in MATS if not acc.get(tag)]
    rc = classify(len(rows), missing, bool(envs))
    path = write_report(rows, note, envs, acc)
    print("\nREPORT %s（%d 行）" % (path, len(rows)), flush=True)
    if envs:
        print("ENV-BLOCKED %s" % "；".join("第%s趟：%s" % (s, w[:120]) for s, w in envs), flush=True)
    if missing:
        print("MISSING %s" % "、".join(missing), flush=True)
    print("RESULT rc=%s %s" % (rc, RC_NAME.get(rc, "?")), flush=True)
    print("DONE", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
