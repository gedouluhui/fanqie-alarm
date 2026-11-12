# -*- coding: utf-8 -*-
"""#42：把「材质」与「重定向表面」这两个变量拆开——**裸窗**（无页面、无宿主、无 WebView2）
在同一对屏位上跑 2×2：NOREDIR 在／不在 × Mica／Acrylic／无材质。

为什么要有这一把（#37 与 #40 都摘不到这一层）：
  · #37 的自变量只有 CSS 注入，它摘不掉 `WS_EX_NOREDIRECTIONBITMAP` 那一层；
  · #40 的自变量只有屏位，它证明"Acrylic 跟壁纸走"，但产品窗里同时挂着**页面**与**宿主表面**，
    所以"客户区不动"到底是材质不采、还是那层不透明表面挡着，两条链都没排掉（缺口 6 末尾）。
  · 产品宿主的 `native/FqHost.cs:145` 把 NoRedir 与 backdrop 焊死在一起
    （`supported = build >= 22621 && backdrop != 1` ⇒ `NoRedir = supported`），所以在产品 exe 上
    做不出"同材质、只换表面"的单变量对。本量具**不改宿主、不重编译**，而是用 ctypes 自己造窗：
    同一份代码、同一个尺寸、同一对屏位，唯一的变量＝那个 exstyle 位在不在。

三只轮子（各管一件事，缺一只就退化成自说自话）：
  · 空窗对照 `bare-noredir-none`：NOREDIR ＋ 无材质 ⇒ 那块区域本来就该露出桌面。
    它管的是"这条屏位杠杆 + 这条裁图路径"在裸窗上读不读得到壁纸变化。它读不到 ⇒ 整场判
    INSTRUMENT-ABORT：后面任何一个零都只是"尺子瞎了"，不许解释成"材质不采"。
  · 主判：同一个材质比 `bare-noredir-*` 与 `bare-redir-*`（真单变量）。
  · 同批产品窗（`prod-mica`／`prod-acrylic`）只算**线索**：裸窗与产品窗之间同时差着
    内容层与窗框样式两个变量，不许写成单变量结论；把它放进同一批是为了拿掉"跨批"这一层。

跑之前写死的判读（出数之后一个字不改；改判据＝新趟，另开一份报告）：
  记 T_x ＝ 亮位客户区读数 − 暗位客户区读数；沿用 #40 的 TRACK_MIN＝8.0 判"跟屏位走"，
  不新造阈值。桌面自己漂过 DRIFT_TOL＝8.0 的那一对当场标"不作数"。
  ① 空窗对照必须 |T| ≥ 8.0；否则 rc=5 INSTRUMENT-ABORT（点名是杠杆还是裁图）。
  ② 主判（只看同一材质的两只裸窗）：
     a) T_noredir ≥ 8 且 |T_redir| < 8 ⇒ **挡场的是那块重定向表面**：材质本身采得到壁纸，
        产品窗里那层不透明表面把它盖住了 ⇒ 缺口 6 的"表面透明链"这一支点亮，
        下一枪才有依据去动 C++ 侧的标志位。
     b) |T_noredir| < 8（摘了表面也不跟）且 ①成立 ⇒ **这条杠杆在裸窗上就采不到**，
        产品宿主无罪；#40 那两批 Acrylic 跟屏位走（+12.4／+14.4）只剩"页面／宿主给了一条
        别的路"这一种解释，需要新杠杆才能继续。
     c) T_redir ≥ 8（带着表面照样跟）⇒ 表面不是挡点，这条尺回答不了缺口 6。
     d) 其余（中间态、缺轮、不作数）⇒ 明写"两条都没排除"，不许挑一条说得通的写成结论。
  ③ 产品窗两行永远标成"线索（两个变量同变）"，不参与 ②。

跑后订正（2026-10-11，第 3 批 host-surface-20261011T152614Z 撞出来的两条；上面原文一字未删，
改判据的语义**只对下一批起生效**，那批的 rc 仍是它自己那一刻写下的 rc=5）：
  订正 1（分家）：①那一对读成 INVALID_DRIFT（桌面自己漂过 8.0）时，报的是**环境失败 rc=4**，
    不是 rc=5 量具判废。原判据把两者写在同一句里，第 3 批满场漂 13.9~17.5 就撞上这条：
    那一把尺没瞎（裸窗读数照常出、层序／几何全绿），动的是桌面本身。混成一类的代价是下一次
    能把量具的真缺陷洗成"环境问题"，或反过来把一次漂移洗成"尺子废了"。自检 C7／C8 钉住这条。
  订正 2（收窄）：b) 分支原文那句"产品宿主无罪"是越界的。这一支实测到的只是
    **摘掉重定向表面后，裸窗的客户区仍不跟屏位走** ⇒ 否证的是"表面是挡点"这一支，
    它对产品窗（多着内容层＋窗框样式两个变量）不构成"无罪"判决。产品窗那两行的跟屏位
    仍归在这条杠杆之外，具体是什么本尺不判。

复用而非另写：屏位选取／均值／漂移判据全部 import 自 `exp_backdrop_source.py`（那里已证过牙），
采集只有 `shot_desktop.grab_desktop` 一条路＋`probe_mica5.shot` 作旁路，解锁判据只有
`probe_mica5.desktop_ready()` 一处，起产品窗走 `probe_glass.launch/teardown/pick_port`
（**只挪位、只关自己起的窗，绝不按镜像名杀进程**）。

环境失败与量具判废分家：rc=0 满场／2 有缺轮（不许重开洗绿）／3 入场即拒（别的链在场）／
4 环境不配合（跑到一半锁屏、壁纸做不出屏位对、桌面自己漂）／5 量具判废（①失明、exstyle
没落上、几何假设不成立）。

用法：
  PYTHONIOENCODING=utf-8 python 验收\\exp_host_surface.py --selfcheck   # 只跑纯函数已知答案对照（锁屏可跑）
  PYTHONIOENCODING=utf-8 python 验收\\exp_host_surface.py               # 真跑：5 只裸窗 × 2 屏位 ＋ 2 只产品窗 × 2 屏位
  PYTHONIOENCODING=utf-8 python 验收\\exp_host_surface.py --gap=25      # 亮暗两处的最小亮度差（同 #40）
"""
import ctypes
import ctypes.wintypes as wt
import datetime as dt
import hashlib
import io
import os
import socket
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import probe_mica5 as M5                           # noqa: E402  （import 它就声明了 DPI 感知）
import probe_glass as G                            # noqa: E402
import shot_desktop as SD                          # noqa: E402
import exp_backdrop_source as BS                   # noqa: E402  屏位/均值/漂移的既有实现，不另写一份

OUT = G.OUT
STAMP = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
REPORT = os.path.join(OUT, "host-surface-%s.md" % STAMP)
FINAL = os.path.join(OUT, "FINAL-surface-%s.md" % STAMP)
DONE = os.path.join(OUT, "DONE-surface-%s.ok" % STAMP)
CLS = "FqBareSurfWin"
BARE_TITLE = "FQBARESURF"
WS_EX_NOREDIRECTIONBITMAP = 0x00200000   # 不是 0x00080000（那是 WS_EX_WINDOWEDGE）。
#   上一趟就是抄错的：三只裸窗全读到 exstyle=0x80000，而"期望位 vs 实测位"那道闸门两边都用
#   同一个错常量，于是它自洽地放行了——闸门只证"我要的位落上了"，证不了"我要的是那个位"。
#   现在由自检 F5 拿产品宿主 native/FqHost.cs 里那份独立写法对一次，两处不许各自漂。
WS_EX_TOPMOST = 0x00000008
WS_POPUP_VISIBLE = 0x80000000 | 0x10000000
DWMWA_SYSTEMBACKDROP_TYPE = 38
BACKDROP = {"none": 1, "mica": 2, "acrylic": 3}
SETTLE_S = 2.2                    # 起窗到采图的等待：DWM 合成要一拍，150% 缩放下 2.2 s 是 #40 用过的节拍
BUDGET_S = 480.0                  # 整趟墙钟上限；到点收手写"卡在哪一步"，不交白卷也不硬撑
PORT_RANGE = range(9411, 9417)    # 别的像素链的消费通道：有人听着＝不入场

dwm = ctypes.windll.dwmapi
dwm.DwmSetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]
dwm.DwmSetWindowAttribute.restype = ctypes.c_int

# 五只裸窗：名字／exstyle 里 NOREDIR 在不在／backdrop 值／这一只回答什么
BARE_ARMS = (
    ("bare-noredir-none", WS_EX_NOREDIRECTIONBITMAP, "none",
     "空窗对照（①）：NOREDIR＋无材质＝这块区域本该露出桌面；它不亮整场判废"),
    ("bare-noredir-mica", WS_EX_NOREDIRECTIONBITMAP, "mica",
     "Mica·摘掉重定向表面（主判的那一只）"),
    ("bare-redir-mica", 0, "mica",
     "Mica·保留重定向表面＝产品宿主那一层的形状"),
    ("bare-noredir-acrylic", WS_EX_NOREDIRECTIONBITMAP, "acrylic",
     "Acrylic·摘掉重定向表面（主判的那一只）"),
    ("bare-redir-acrylic", 0, "acrylic",
     "Acrylic·保留重定向表面＝产品宿主那一层的形状"),
)
PROD_ARMS = (("--mica", "mica", "prod-mica", "产品窗·Mica（线索：与裸窗差着内容层＋窗框样式两个变量）"),
             ("--acrylic", "acrylic", "prod-acrylic", "产品窗·Acrylic（同上一条线索）"))
PAIRS = [("bare-noredir-mica", "bare-redir-mica", "Mica"),
         ("bare-noredir-acrylic", "bare-redir-acrylic", "Acrylic")]


# ---------------- 纯函数（不碰窗、不碰像素，锁屏可判） ----------------
def reading_gates(name):
    """这一只读数的空帧判据打在哪儿——这是本轮最容易自己造出来的一条假阳性。

    带重定向表面的裸窗**合法地**就是一块纯色（NULL 背景刷 ⇒ 未初始化表面，多半近黑）：
    把 `blank_verdict` 打在它的客户区上，等于把"这块表面不透明"读成"根本没出帧"，
    而"根本没出帧"正是我要避免的那一种假绿光／假红光。所以：
      · 空帧判据只打在桌面上（开拍前整屏，由调用方做），裸窗客户区不做空帧判；
      · NOREDIR 那几只的 PrintWindow 旁路天生读不出东西（没有表面可印），只记不判。
    """
    return {"blank_on_client": False,
            "printwindow_is_reading": ("noredir" not in name),
            "layer_gate": True}


def track_of(bright, dark, track_min=BS.TRACK_MIN, drift_tol=BS.DRIFT_TOL):
    """一对屏位的读数 ⇒ (种类, 说明, Δ客户区, Δ屏位, 跟踪比)。

    种类只有五种，判读规则里每种各自的落点事先写好：
      UNPAIRED／INVALID_DRIFT／TRACKING／FLAT／OUTLIER 之外不许出现第六种。
    """
    if not bright or not dark or "client" not in bright or "client" not in dark:
        return "UNPAIRED", "缺轮（起窗失败／中途被锁屏打断）⇒ 这一行没有结论", None, None, None
    drift = max(bright["drift"], dark["drift"])
    d_client = bright["client"] - dark["client"]
    d_region = bright["pos"][0] - dark["pos"][0]
    ratio = (d_client / d_region) if d_region else None
    if drift > drift_tol:
        return ("INVALID_DRIFT",
                "不作数：桌面自己漂了 %.1f > %.1f，两次屏位量不是同一张壁纸" % (drift, drift_tol),
                d_client, d_region, ratio)
    if abs(d_client) >= track_min:
        return ("TRACKING", "跟屏位走（Δ客户区 %+0.1f，Δ屏位 %+0.1f，跟踪比 %s）"
                % (d_client, d_region, ("%.2f" % ratio) if ratio is not None else "n/a"),
                d_client, d_region, ratio)
    return ("FLAT", "对屏位无反应（Δ客户区 %+0.1f，Δ屏位 %+0.1f）" % (d_client, d_region),
            d_client, d_region, ratio)


def surface_verdict(per_arm, track_min=BS.TRACK_MIN):
    """②的主判：只看同一材质那对裸窗。⇒ (kind, why, 该不该整场判废)。

    kind 只有 5＋1 个值，与 docstring 里那四条分支一一对应，中间态一律落 UNDECIDED，
    不许"挑一条说得通的"写成结论（讲得通≠成立）。
    第 6 个是 **ENV-VOID**：①那一对是"桌面自己动了"（INVALID_DRIFT）——那是**环境失败**，
    不是量具判废。上一趟真撞上这一档：满场 14 行的漂 13.9~17.5 > 8.0，全行不作数。
    把它报成 rc=5「尺子瞎了」就是把两类混成一类（本项目反复要求它们分家），
    所以它必须走 rc=4，并且**不许**在正文里写成量具的结论。
    """
    ctl = per_arm.get("bare-noredir-none")
    if ctl and ctl[0] == "INVALID_DRIFT":
        return ("ENV-VOID", u"①空窗对照那一对不作数（%s）⇒ 这是**桌面自己在动**（环境失败），"
                            u"不是这条杠杆失明；整批读数一律不进结论，等桌面稳定再跑" % ctl[1], False)
    if not ctl or ctl[0] == "UNPAIRED":
        return ("ABORT", u"①空窗对照缺轮（%s）⇒ 这一批没有「会亮的正对照」垫着，"
                          u"后面任何一个零都不许单独成句（先修量具／补齐那一只再跑）"
                         % ((ctl[1] if ctl else u"根本没采"),), True)
    if ctl[0] != "TRACKING":
        return ("ABORT", u"①空窗对照读成「%s」而不是「跟屏位走」⇒ 屏位杠杆或裁图路径失效，"
                         u"整场判废（不许把失明读成不采）" % ctl[1], True)
    outs, kinds = [], []
    for a, b, mat in PAIRS:
        ta, tb = per_arm.get(a), per_arm.get(b)
        if not ta or not tb or ta[0] in ("UNPAIRED", "INVALID_DRIFT") or \
           tb[0] in ("UNPAIRED", "INVALID_DRIFT"):
            outs.append(u"%s：缺轮／不作数 ⇒ 这一对没结论" % mat)
            kinds.append("UNDECIDED")
            continue
        na, nb = abs(ta[2]) >= track_min, abs(tb[2]) >= track_min
        if na and ta[2] > 0 and not nb:
            outs.append(u"%s：**挡场的是那块重定向表面**（摘掉 Δ%+0.1f 跟屏位走，带着 Δ%+0.1f 不跟）"
                        u"⇒ 材质本身采得到壁纸，缺口 6 的「表面透明链」支点亮" % (mat, ta[2], tb[2]))
            kinds.append("SURFACE_BLOCKS")
        elif not na:
            outs.append(u"%s：**这条杠杆在裸窗上就采不到**（摘了表面 Δ%+0.1f 仍无反应）"
                        u"⇒ 这一支上「重定向表面是挡点」没被支持；产品窗那两行的跟屏位仍归在"
                        u"这条杠杆之外（内容层／宿主组合路径），本尺不判它是什么"
                        % (mat, ta[2]))
            kinds.append("LEVER_DEAD_ON_BARE")
        elif nb:
            outs.append(u"%s：带着表面照样跟屏位走（Δ%+0.1f）⇒ 表面不是挡点，这条尺回答不了缺口 6"
                        % (mat, tb[2]))
            kinds.append("SURFACE_NOT_CULPRIT")
        else:
            outs.append(u"%s：中间态（noredir Δ%+0.1f／redir Δ%+0.1f）⇒ 两条都没排除" % (mat, ta[2], tb[2]))
            kinds.append("UNDECIDED")
    return ("／".join(kinds) if kinds else "NO-PAIR"), (u"；".join(outs) if outs else u"主判那两对都没轮子"), False


def classify(n_have, n_expect, env_hit, aborts):
    """rc 语义（跑前写死，与 #37/#40 那套对齐）：0 满场／2 缺轮／3 入场即拒／4 环境／5 量具判废。"""
    if aborts:
        return 5, "INSTRUMENT-ABORT " + "；".join(aborts)
    if env_hit:
        return 4, "ENV-BLOCKED：中途桌面没就绪／壁纸做不出屏位对（已收的 %d/%d 行留底见报告）" % (n_have, n_expect)
    if n_have < n_expect:
        return 2, "PARTIAL：缺 %d 行（**不许重开这一趟把它洗成一次成功跑**）" % (n_expect - n_have)
    return 0, "FULL：满 %d 行" % n_expect


def ports_busy(ports=PORT_RANGE):
    """入场检查的一条：别的像素链的消费通道有没有人听着。"""
    busy = []
    for p in ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        try:
            s.connect(("127.0.0.1", p))
            busy.append(p)
        except Exception:
            pass
        finally:
            s.close()
    return busy


# ---------------- 裸窗：一份代码，exstyle 位是唯一被换的东西 ----------------
_CLASS_DONE = [False]


def _register_class():
    if _CLASS_DONE[0]:
        return True
    inst = wt.HINSTANCE(M5.k32.GetModuleHandleW(None))
    wc = M5.WCE()
    wc.cbSize = ctypes.sizeof(wc)
    wc.lpfnWndProc = _KEEP_PROC
    wc.hInstance = inst
    # hbrBackground＝NULL：这一层刻意什么都不画。画了就把"表面在不在"这个单变量换成了
    # "表面在不在＋我画了什么"，整场又回到两变量。
    wc.hbrBackground = 0
    wc.lpszClassName = CLS
    _CLASS_DONE[0] = bool(M5.u.RegisterClassExW(ctypes.byref(wc)))
    return _CLASS_DONE[0]


def _bare_proc(h, msg, wp, lp):
    if msg == 0x0002:
        M5.u.PostQuitMessage(0)
        return 0
    return M5.u.DefWindowProcW(h, msg, wp, lp)


_KEEP_PROC = M5.WNDPROC(_bare_proc)


class Bare(threading.Thread):
    """把窗建在自己的消息泵线程上（Field 那一条老路）：跨线程 Invalidate/Update 会走错线程。"""

    def __init__(self, exstyle, backdrop, rect):
        super(Bare, self).__init__(daemon=True)
        self.exstyle = exstyle
        self.backdrop = backdrop
        self.rect = rect
        self.hwnd = 0
        self.hr = None
        self.ex_after = None
        self.err = ""
        self.ready = threading.Event()

    def run(self):
        try:
            if not _register_class():
                self.err = "REGISTER-FAIL gle=%d（类名已存在时这也可能为 0，下面 CreateWindow 会兜）" % \
                           M5.k32.GetLastError()
            inst = wt.HINSTANCE(M5.k32.GetModuleHandleW(None))
            h = M5.u.CreateWindowExW(self.exstyle, CLS, BARE_TITLE, WS_POPUP_VISIBLE,
                                     self.rect[0], self.rect[1], self.rect[2], self.rect[3],
                                     None, None, inst, None)
            if not h:
                self.err = "CREATE-FAIL gle=%d" % M5.k32.GetLastError()
                return
            self.hwnd = int(h)
            v = ctypes.c_int(BACKDROP[self.backdrop])
            self.hr = dwm.DwmSetWindowAttribute(wt.HWND(h), DWMWA_SYSTEMBACKDROP_TYPE,
                                                ctypes.byref(v), ctypes.sizeof(v))
            self.ex_after = M5.u.GetWindowLongW(wt.HWND(h), -20) & 0xFFFFFFFF
            M5.u.ShowWindow(h, 5)
            M5.above(h, self.rect)          # 置顶样式＋层序置顶，两步都要（少一步就是上一轮那种假结论）
            self.ready.set()                # 先放行量具，再进消息泵
            # 消息泵不是可选项：线程一退出，它建的窗就跟着没了。上一趟"几何 FAIL＋不在置顶档"
            # 就是这个漏子——GetWindowRect 返回全零，因为那只窗早已被拆掉。
            msg = wt.MSG()
            run = True
            while run:
                while M5.u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == 0x0012:      # WM_QUIT
                        run = False
                        break
                    M5.u.TranslateMessage(ctypes.byref(msg))
                    M5.u.DispatchMessageW(ctypes.byref(msg))
                time.sleep(0.02)
        finally:
            self.ready.set()

    def stop(self):
        if self.hwnd:
            M5.u.PostMessageW(wt.HWND(self.hwnd), 0x0010, 0, 0)   # 只关自己起的这只，绝不碰别人的窗


def measure(buf, vw, vh, vx, vy, cx, cy, cw, ch, pos, other, base_buf, name, hr_txt):
    """客户区读数（中心 120×120 走层序闸门；整块客户区只记不判）＋环带＋另一处屏位的漂移复核。

    坐标口径要交底：`region_mean`/这里都按「虚拟屏原点＝缓冲原点」直接索引（与 #40 同一口径）。
    多显示器且虚拟原点不为 (0,0) 时这个假设会错，所以 main() 里有一道当场断言，不靠注释。
    """
    sx, sy = cx + cw // 2 - M5.BOX // 2, cy + ch // 2 - M5.BOX // 2
    vals = []
    for y in range(sy, sy + M5.BOX, 2):
        base = (y - vy) * vw
        for x in range(sx, sx + M5.BOX, 2):
            o = (base + x) * 3
            vals.append((buf[o], buf[o + 1], buf[o + 2]))
    cmean, cmad, cuniq = SD.stats_of(vals)
    full = []
    for y in range(cy, cy + ch, 4):
        base = (y - vy) * vw
        for x in range(cx, cx + cw, 4):
            o = (base + x) * 3
            full.append((buf[o], buf[o + 1], buf[o + 2]))
    fmean, _, _ = SD.stats_of(full)
    # 环带只记不判，但它上一趟把整场崩了：屏位选到 y=0 时「上侧」那条区间是空的，
    # region_mean 按它自己的契约抛 RuntimeError，主循环没接 ⇒ rc=1、一份报告都没落。
    # 现在一侧塌了只少一侧，并当场记下塌了几侧（环带跨屏位比较时须同口径，塌过的要点名）。
    band_args = ((cx - BS.RING, cy, cx, cy + ch), (cx + cw, cy, cx + cw + BS.RING, cy + ch),
                 (cx, max(0, cy - BS.RING), cx + cw, cy),
                 (cx, cy + ch, cx + cw, min(vh, cy + ch + BS.RING)))
    bands, ring_na = [], []
    for bx0, by0, bx1, by1 in band_args:
        try:
            bands.append(BS.region_mean(buf, vw, bx0, by0, bx1, by1, BS.STRIDE_ROUND))
        except RuntimeError:
            ring_na.append((bx0, by0, bx1, by1))
    ring = (sum(bands) / len(bands)) if bands else None
    ox0, oy0 = vx + other[1], vy + other[2]
    oreg = BS.region_mean(buf, vw, ox0, oy0, ox0 + BS.WIN_W, oy0 + BS.WIN_H, BS.STRIDE_ROUND)
    oreg0 = BS.region_mean(base_buf, vw, ox0, oy0, ox0 + BS.WIN_W, oy0 + BS.WIN_H, BS.STRIDE_ROUND)
    drift = abs(oreg - oreg0)
    png = ""
    if drift > BS.DRIFT_TOL:
        # 判废的那一批必须留下"桌面到底被什么动了"的那一张：第 3 批满场漂 13.9~17.5，
        # 只有整屏图能分清是别人弹了窗、壁纸换了、还是这条量具自己在采错区域。
        # 文件名必须带屏位：第 4 批只按 arm 名存，同一只材质的亮／暗两轮写的是同一个名字，
        # 后一轮把前一轮覆盖掉了——结果那一趟唯一一份"证据"其实是另一时刻的现场。
        png = os.path.join(OUT, "drift-%s-%s-%d_%d.png" % (STAMP, name, pos[1], pos[2]))
        try:
            SD.save(png, buf, vw, vh)
        except Exception as e:
            png = "存图失败 %s" % e
    return {"client": cmean, "mad": cmad, "uniq": cuniq, "full": fmean, "ring": ring,
            "ring_sides": len(bands), "ring_na": len(ring_na),
            "other_now": oreg, "other_base": oreg0, "drift": drift, "png": png,
            "pos": pos, "host": hr_txt, "name": name}


def one_bare(arm, pos, other, vx, vy, vw, vh, base_buf):
    name, exstyle, backdrop, label = arm
    rect = (vx + pos[1], vy + pos[2], BS.WIN_W, BS.WIN_H)
    b = Bare(exstyle, backdrop, rect)
    b.start()
    b.ready.wait(8)
    if not b.hwnd:
        return {"tag": name, "fail": b.err or "NO-HWND"}
    time.sleep(SETTLE_S)
    want_bit = bool(exstyle & WS_EX_NOREDIRECTIONBITMAP)
    got_bit = bool((b.ex_after or 0) & WS_EX_NOREDIRECTIONBITMAP)
    try:
        buf, _ = SD.grab_desktop(vx, vy, vw, vh)
        r = wt.RECT()
        M5.u.GetWindowRect(wt.HWND(b.hwnd), ctypes.byref(r))
        cl = wt.RECT()
        M5.u.GetClientRect(wt.HWND(b.hwnd), ctypes.byref(cl))
        pt_l = wt.POINT(0, 0)
        M5.u.ClientToScreen(wt.HWND(b.hwnd), ctypes.byref(pt_l))
        geo_ok = (r.right - r.left == BS.WIN_W and r.bottom - r.top == BS.WIN_H and
                  cl.right - cl.left == r.right - r.left and pt_l.x == r.left and pt_l.y == r.top)
        layer_ok, blockers = M5.above_field(b.hwnd)
        hr_txt = "exstyle=0x%x NOREDIR 期望%s 实测%s｜DwmSetWindowAttribute(38,%d)→0x%08x｜几何%s｜层序%s" % (
            b.ex_after or 0, "在" if want_bit else "不在", "在" if got_bit else "不在",
            BACKDROP[backdrop], (b.hr if b.hr is not None else 0xFFFFFFFF) & 0xFFFFFFFF,
            "OK" if geo_ok else "FAIL", "OK" if layer_ok else "BAD %d 个窗压着" % len(blockers))
        print("  %s @ (%d,%d)：%s" % (name, pos[1], pos[2], hr_txt), flush=True)
        if want_bit != got_bit:
            return {"tag": name, "fail": "EXSTYLE-NOT-APPLIED " + hr_txt}
        if not geo_ok:
            return {"tag": name, "fail": "GEOMETRY-ASSUMPTION-BROKEN " + hr_txt}
        if not layer_ok:
            return {"tag": name, "fail": "LAYER-BLOCKED " + hr_txt}
        m = measure(buf, vw, vh, vx, vy, r.left, r.top, r.right - r.left, r.bottom - r.top,
                    pos, other, base_buf, name, hr_txt)
        m["hr"] = b.hr
        return m
    finally:
        b.stop()
        b.join(4)


def one_prod(arm, pos, other, vx, vy, vw, vh, base_buf):
    flag, glass, name, label = arm
    port, note = G.pick_port(9414 if flag == "--mica" else 9415)
    G.RECT = (vx + pos[1], vy + pos[2], BS.WIN_W, BS.WIN_H)
    h, proc, cl, txt = G.launch(flag, glass, port, name)
    if not h:
        return {"tag": name, "fail": "LAUNCH-FAIL %s%s" % (txt, "｜" + note if note else "")}
    try:
        buf, _ = SD.grab_desktop(vx, vy, vw, vh)
        cx, cy, cw, ch = cl
        print(u"  %s @ (%d,%d)：客户区 %d,%d %dx%d｜%s" % (
            name, pos[1], pos[2], cx, cy, cw, ch, txt[:140]), flush=True)
        return measure(buf, vw, vh, vx, vy, cx, cy, cw, ch, pos, other, base_buf, name, txt[:140])
    finally:
        G.teardown(h, proc)


def write_report(body_lines, per_arm, prod_arm, rc, rc_why, ctx):
    txt = "\n".join(body_lines)
    io.open(REPORT, "w", encoding="utf-8").write(
        u"# 裸窗 2×2：材质 vs 重定向表面（#42）· %s\n\n"
        u"虚拟屏 %d,%d %dx%d｜窗尺寸固定 %dx%d（屏位与尺寸不混成同一个变量）｜全程**不放场窗**｜"
        u"读数取客户区中心 %d×%d（层序闸门只保证这一格），整块客户区与环带只记不判。\n\n"
        u"出处：`exp_host_surface.py` md5=%s\n`exp_backdrop_source.py` md5=%s\n"
        u"`probe_mica5.py` md5=%s\n`shot_desktop.py` md5=%s\n\n"
        u"屏位：%d 个候选里选出 亮 (%d,%d) 壁纸均值 %.1f ／ 暗 (%d,%d) 壁纸均值 %.1f（差 %.1f）\n\n"
        u"## 判读（跑前写死的四条分支，见脚本头部）\n\n```\n%s\n```\n\n"
        u"## 逐只裸窗（①空窗对照＋②主判）\n\n%s\n\n"
        u"## 同批产品窗（③线索：与裸窗差着内容层＋窗框样式两个变量，不参与主判）\n\n%s\n\n"
        u"## 边界\n\n"
        u"- 空帧判据打在开拍前的整屏上，**不打在裸窗客户区**：带重定向表面的裸窗合法地就是一块纯色，"
        u"把空帧判据压到它身上会把「表面不透明」读成「没出帧」——那是量具自己造的假阳性（`reading_gates` 与"
        u"自检里那条已知答案对照管的就是这件事）。\n"
        u"- NOREDIR 那几只的 PrintWindow 旁路读不出东西是预期（没有表面可印），所以这里的客户区读数只走"
        u"`grab_desktop` 裁图一条路；带表面那几只两路都记，差多少照写。\n"
        u"- 本量具不改宿主、不重编译 `native\\FqGlass.exe`：产品窗那两行只是参照，"
        u"真正要动标志位的那一枪仍然属于 §8 缺口 6 末尾那条。\n"
        u"- 屏位是**先后**两次起窗量的，靠「另一处屏位开拍前后漂移 ≤%.1f」复核桌面没自己动；超限的那一对当场不作数。\n\n"
        u"## 结局\n\n```\nrc=%d %s\n```\n"
        % (STAMP, ctx["vx"], ctx["vy"], ctx["vw"], ctx["vh"], BS.WIN_W, BS.WIN_H, M5.BOX, M5.BOX,
           ctx["me_self"], ctx["me_bs"], ctx["me_m5"], ctx["me_sd"],
           ctx["n_pts"], ctx["bright"][1], ctx["bright"][2], ctx["bright"][0],
           ctx["dark"][1], ctx["dark"][2], ctx["dark"][0],
           ctx["bright"][0] - ctx["dark"][0], txt,
           "\n".join(per_arm), "\n".join(prod_arm), BS.DRIFT_TOL, rc, rc_why))
    io.open(FINAL, "w", encoding="utf-8").write(
        u"# FINAL-surface %s\n\n- 报告：`%s`\n- 判读：\n```\n%s\n```\n- 结局 rc=%d：%s\n"
        % (STAMP, os.path.basename(REPORT), txt, rc, rc_why))
    io.open(DONE, "w", encoding="utf-8").write(
        u"%s rc=%d rows=%d/%d stamp=%s\n" % ("ok" if rc in (0, 2) else "halt", rc,
                                             ctx["n_have"], ctx["n_expect"], STAMP))


def ring_txt(b, d):
    """环带那一格的排版（纯函数，自检里钉它）。

    ring 可能是 None（四侧全塌）或只由 2／3 侧平均而来（贴上屏边）——后一种必须点名，
    否则两处屏位的「环带 118／35」看着同口径，其实一处是四侧、一处是三侧。
    """
    out = []
    for r in (b, d):
        v = r.get("ring")
        s = r.get("ring_sides", 4)
        out.append("n/a" if v is None else ("%.1f" % v if s == 4 else "%.1f(%d侧)" % (v, s)))
    return u"环带 %s／%s" % (out[0], out[1])


def full_ring_positions(pts, vw, vh, ring=None):
    """只留「四侧环带都落在屏内」的屏位（纯函数：崩掉上一趟的正是 y=0 那一格）。

    这里筛的不是美观：环带是本量具唯一能露头"别人插进来了"的地方，一侧塌掉就等于
    两处屏位量的不是同一个口径——而它在判决行上长得和正常读数一模一样。
    """
    ring = BS.RING if ring is None else ring
    return [p for p in pts if p[2] >= ring and p[2] + BS.WIN_H + ring <= vh
            and p[1] >= ring and p[1] + BS.WIN_W + ring <= vw]


def drift_pair(b, d):
    """取"漂得最狠的那一轮"的原始两侧数＋轮名（纯函数，自检钉住）。

    不能写成 max(now)／min(base)：那一行看着像证据，其实是把两轮的四个数拼成了一个
    现场不存在的差。判决要说"哪一轮的哪两个数"，就必须整轮取。
    """
    cand = [(r, tag) for r, tag in ((b, u"亮"), (d, u"暗")) if r and "drift" in r]
    if not cand:
        return u"", None, None, None
    r, tag = max(cand, key=lambda x: x[0]["drift"])
    return tag, r.get("other_now"), r.get("other_base"), r.get("drift")


def main():
    if M5.find_title(G.GTITLE) or M5.find_title("FQFIELD") or M5.find_title(BARE_TITLE):
        print(u"REFUSE：桌面上还挂着 FQGLASS／FQFIELD／FQBARESURF ⇒ 另一条像素链在场，本实验必须独占。",
              flush=True)
        return 3
    busy = ports_busy()
    if busy:
        print(u"REFUSE：9411–9416 里 %s 有人在听 ⇒ 另一条链的 CDP 通道还活着，不入场。" % busy, flush=True)
        return 3
    ready, why = M5.desktop_ready()
    if not ready:
        print(u"ENV-BLOCKED：桌面没解锁／显示器没点亮（%s）⇒ 拍到的会是黑帧，不硬跑。" % why, flush=True)
        return 4
    min_gap = 20.0
    for a in sys.argv:
        if a.startswith("--gap="):
            min_gap = float(a.split("=", 1)[1])
    vx, vy, vw, vh = SD.virtual_screen()
    if (vx, vy) != (0, 0):
        # 坐标口径声明：整块缓冲按「虚拟屏原点＝缓冲原点」直接索引（与 #40 同一口径）。
        # 多显示器且原点不在 (0,0) 时这个假设会静默把所有矩形搬一个偏移量，所以当场拒跑，不靠注释凑。
        print(u"REFUSE：虚拟屏原点不是 (0,0)（%d,%d）⇒ 量具的坐标假设不成立，不跑。" % (vx, vy), flush=True)
        return 3
    t0 = time.time()
    print(u"虚拟屏 %d,%d %dx%d；裸窗与被测窗同尺寸 %dx%d；预算 %.0f s" %
          (vx, vy, vw, vh, BS.WIN_W, BS.WIN_H, BUDGET_S), flush=True)
    base_buf, _ = SD.grab_desktop(vx, vy, vw, vh)
    pts0 = [(base_buf[(y * vw + x) * 3], base_buf[(y * vw + x) * 3 + 1],
             base_buf[(y * vw + x) * 3 + 2]) for y in range(0, vh, 64) for x in range(0, vw, 64)]
    bmean, bmad, buniq = SD.stats_of(pts0)
    okA, whyA = SD.blank_verdict(bmean, buniq, u"开拍前整屏")
    print(u"整屏 A %s（%s）｜MAD %.1f" % ("PASS" if okA else "FAIL", whyA, bmad), flush=True)
    if not okA:
        return 5
    pts = BS.scan_positions(base_buf, vw, vh, BS.WIN_W, BS.WIN_H)
    # 屏位筛选是本地政策，不动 #40 那份共用扫描：这里要求**四侧环带都落在屏内**。
    # 上一趟崩在 y=0 那格（上侧环带退化成正好一条零面积区间），更隐蔽的是它就算不崩，
    # 两处屏位的环带也不再是同一个口径——而环带正是「别人插进来了」唯一的露头处。
    n_raw = len(pts)
    pts = full_ring_positions(pts, vw, vh)
    pair = BS.pick_pair(pts, min_gap, BS.MIN_DIST)
    if not pair:
        print(u"ENV-BLOCKED：这张壁纸上做不出亮度差 ≥%.1f 且相距 ≥%d 的两处 ⇒ 本实验当下出不了结论，不硬凑屏位。"
              % (min_gap, BS.MIN_DIST), flush=True)
        return 4
    bright, dark = pair
    print(u"屏位选定：扫描 %d 格、留出四侧环带后 %d 格；亮 (%d,%d) %.1f ／ 暗 (%d,%d) %.1f｜差 %.1f" %
          (n_raw, len(pts), bright[1], bright[2], bright[0], dark[1], dark[2], dark[0],
           bright[0] - dark[0]), flush=True)

    n_expect = len(BARE_ARMS) * 2 + len(PROD_ARMS) * 2
    by = {"bright": {}, "dark": {}}
    env_hit = False
    order = [(key, pos, other) for key, pos, other in (("bright", bright, dark), ("dark", dark, bright))]
    # 先跑裸窗（主判靠它），再跑产品窗（只是线索）：中途锁屏时已经banked 的那一半才是有用的那一半。
    for phase, arms in (("bare", BARE_ARMS), ("prod", PROD_ARMS)):
        for key, pos, other in order:
            for arm in arms:
                if time.time() - t0 > BUDGET_S:
                    print(u"ENV-BLOCKED：墙钟预算 %.0f s 到点，剩下的行不硬撑。" % BUDGET_S, flush=True)
                    env_hit = True
                    break
                if phase == "bare":
                    try:
                        r = one_bare(arm, pos, other, vx, vy, vw, vh, base_buf)
                    except Exception as e:
                        # 崩在单只窗上只塌那一只，并把它记成**点名的**缺轮：上一趟 y=0 那格抛出来时
                        # 整场连一份报告都没落，已经采到的十分之九跟着陪葬——那是量具自己的损失，
                        # 不是现场的损失。点名（而不是吞掉）保证它照样进 rc 与判决。
                        r = {"tag": arm[0], "fail": "ROUND-CRASH %s: %s" % (type(e).__name__, e)}
                        print(u"  ROUND-CRASH %s：%s: %s" % (arm[0], type(e).__name__, e), flush=True)
                else:
                    try:
                        r = one_prod(arm, pos, other, vx, vy, vw, vh, base_buf)
                    except Exception as e:
                        r = {"tag": arm[2], "fail": "ROUND-CRASH %s: %s" % (type(e).__name__, e)}
                        print(u"  ROUND-CRASH %s：%s: %s" % (arm[2], type(e).__name__, e), flush=True)
                name = arm[2] if phase == "prod" else arm[0]
                by[key][name] = r
                if r.get("fail", "").startswith(("EXSTYLE", "GEOMETRY", "LAYER")):
                    print(u"  量具点名：%s" % r["fail"], flush=True)
                if not M5.desktop_ready()[0]:
                    print(u"ENV-BLOCKED：这一行之后桌面没就绪了，收手。", flush=True)
                    env_hit = True
                    break
            if env_hit:
                break
        if env_hit:
            break

    per_arm, prod_arm, body = [], [], []
    aborts = []
    per_track = {}
    for arm in BARE_ARMS:
        name, _ex, _bd, label = arm
        b, d = by["bright"].get(name), by["dark"].get(name)
        kind, why, dc, dr, ratio = track_of(b, d)
        per_track[name] = (kind, why, dc, dr, ratio)
        lines = u"- %-22s %s" % (name, why)
        if b and "client" in b and d and "client" in d:
            tk, onow, obase, dv = drift_pair(b, d)
            lines += u"｜亮位中心 %.1f／暗位中心 %.1f｜整块 %.1f／%.1f｜%s｜漂 %.1f（%s轮另一处 现在%.1f／开拍前%.1f）｜%s" % (
                b["client"], d["client"], b["full"], d["full"], ring_txt(b, d), dv, tk, onow, obase,
                os.path.basename(b.get("png") or d.get("png") or "") or u"无留图")
        body.append(lines)
        per_arm.append(u"%s\n  宿主：%s\n  宿主：%s" % (
            lines, (b or {}).get("host", (b or {}).get("fail", "缺")),
            (d or {}).get("host", (d or {}).get("fail", "缺"))))
    kind, why, abort = surface_verdict(per_track)
    if abort:
        aborts.append(why)
    if kind == "ENV-VOID":
        # 桌面自己动了 ⇒ 这一批走 rc=4（环境），不走 rc=5（量具判废）；两类混在一起，
        # 下一次就会有人拿"反正都是没结论"把量具的真缺陷洗成环境问题，或反过来。
        env_hit = True
    body.append(u"\n②主判（%s）：%s" % (kind, why))
    for arm in PROD_ARMS:
        name = arm[2]
        b, d = by["bright"].get(name), by["dark"].get(name)
        kind, why, dc, dr, ratio = track_of(b, d)
        # 产品窗那两行也要带逐位原始数与漂：上一趟只落了 Δ，读者无法复核那次「跟屏位走」
        # 有没有过「另一处屏位漂 ≤8.0」这道闸——判决的凭据不许比裸窗那几只少。
        det = u""
        if b and "client" in b and d and "client" in d:
            tk, onow, obase, dv = drift_pair(b, d)
            det = u"｜亮位中心 %.1f／暗位中心 %.1f｜%s｜漂 %.1f（%s轮另一处 现在%.1f／开拍前%.1f）｜%s" % (
                b["client"], d["client"], ring_txt(b, d), dv, tk, onow, obase,
                os.path.basename(b.get("png") or d.get("png") or "") or u"无留图")
        prod_arm.append(u"- %-14s %s%s ｜ 与裸窗之间差着内容层＋窗框样式，只算线索\n"
                        u"  宿主：%s\n  宿主：%s" % (
                            name, why, det,
                            (b or {}).get("host", (b or {}).get("fail", "缺")),
                            (d or {}).get("host", (d or {}).get("fail", "缺"))))
        body.append(u"- %-22s %s%s（③线索，不参与主判）" % (name, why, det))
    n_have = sum(1 for k in by.values() for v in k.values() if "client" in v)
    rc, rc_why = classify(n_have, n_expect, env_hit, aborts)
    print(u"\n=== 判读 ===\n%s\nrc=%d %s" % ("\n".join(body), rc, rc_why), flush=True)
    ctx = {"vx": vx, "vy": vy, "vw": vw, "vh": vh, "n_pts": len(pts),
           "bright": bright, "dark": dark, "n_have": n_have, "n_expect": n_expect,
           "me_self": hashlib.md5(open(os.path.abspath(__file__), "rb").read()).hexdigest(),
           "me_bs": hashlib.md5(open(os.path.join(HERE, "exp_backdrop_source.py"), "rb").read()).hexdigest(),
           "me_m5": hashlib.md5(open(os.path.join(HERE, "probe_mica5.py"), "rb").read()).hexdigest(),
           "me_sd": hashlib.md5(open(os.path.join(HERE, "shot_desktop.py"), "rb").read()).hexdigest()}
    write_report(body, per_arm, prod_arm, rc, rc_why, ctx)
    print(u"\nREPORT %s\nFINAL  %s\nDONE   %s" % (REPORT, FINAL, DONE), flush=True)
    return rc


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:            # 锁屏也能跑：只碰纯函数，不建窗、不接任何端口
        import selftest_host_surface as ST
        sys.exit(ST.main())
    sys.exit(main())
