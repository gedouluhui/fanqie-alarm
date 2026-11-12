# -*- coding: utf-8 -*-
r"""交付件预检：验的是"交付目录里那套"（native\FqGlass.exe ＋ WebView2 三件套 ＋ index.html），
   不是临时目录里的原型——原型绿了不代表拷贝过去的那份绿（上一轮就是栽在 exe 比源码旧）。

S1 起窗＋落位：外框必须等于请求的物理尺寸，客户区不能是 0（WinForms 在 HandleCreated 阶段建柄
   时尺寸还没生效，所以宿主是在 Shown 里 SetWindowPos 的，这条验的就是那一步没退回去）。
S2 无重定向表面：材质模式下 WS_EX_NOREDIRECTIONBITMAP(0x200000) 必须在 ex-style 上——
   没有它，DWM 材质会被窗自己的 redirection surface 挡在下面，看着就像"接了材质但完全不透"。
S3 宿主自报：DwmSetWindowAttribute 返回 0x00000000、webview2=ok、rect=ok、glass 值与模式一致。
S4 页面真的渲染进来了：data-glass 属性对、正文长度够、表盘控件存在（这条件是给真页面的，
   smoke_glass.py 那套"红像素 >=6000"是给 alpha-test.html 判色键用的，口径不能混用）。
S5 屏幕采集可用：对客户区做一次 BitBlt，取不到就直接点名"桌面不可用（锁屏/屏保桌面）"，
   因为所有合成后判据都建立在它之上；这条红的时候，任何"全绿"都不该被相信。
用法：PYTHONIOENCODING=utf-8 python smoke_ship.py            （三种材质都跑）
      PYTHONIOENCODING=utf-8 python smoke_ship.py --mica      （只跑一种）
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import subprocess
import sys
import time

import requests
import websocket

u = ctypes.windll.user32
u.SetProcessDPIAware()
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # 交付目录 fanqie-todo\
OUT = os.path.join(os.environ["LOCALAPPDATA"], "fq-glass-verify")
os.makedirs(OUT, exist_ok=True)
SHIP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(SHIP, "native", "FqGlass.exe")
PAGE = "file:///" + os.path.join(SHIP, "index.html").replace("\\", "/")
URLPART = "index.html"
# --page <path> 只用于证伪测试（把稳定标记闸门指向一份故意删改过的临时页）；默认仍走交付页。
if "--page" in sys.argv:
    _p = sys.argv[sys.argv.index("--page") + 1]
    PAGE = "file:///" + os.path.abspath(_p).replace("\\", "/")
    URLPART = os.path.basename(_p)
NO_REDIR = 0x00200000
TITLE = "FQSHIP"
RECT = (1152, 259, 780, 1470)

for d in ("Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.WinForms.dll",
          "WebView2Loader.dll", "index.html"):
    if not os.path.exists(os.path.join(SHIP, "native", d)) and not os.path.exists(os.path.join(SHIP, d)):
        print("SHIP-MISSING", d)
        sys.exit(2)

u.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
u.GetWindowLongW.restype = ctypes.c_long
u.SetWindowPos.argtypes = [wt.HWND, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                           ctypes.c_int, ctypes.c_int, ctypes.c_uint]


def find(title):
    got = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def fn(h, l):
        n = u.GetWindowTextLengthW(h)
        if n and u.IsWindowVisible(h):
            b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, b, n + 1)
            if b.value == title:
                got.append(int(h))
        return True
    u.EnumWindows(proto(fn), 0)
    return got


def cdp(port, urlpart):
    for _ in range(60):
        try:
            js = requests.get("http://127.0.0.1:%d/json" % port, timeout=2).json()
        except Exception:
            js = []
        for t in js:
            if t.get("type") == "page" and urlpart in (t.get("url") or ""):
                ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=30)
                return ws
        time.sleep(0.5)
    raise RuntimeError("CDP 里没有 %s 这个 target（port %d）" % (urlpart, port))


def ev(ws, i, expr):
    i[0] += 1
    mine = i[0]
    ws.send(json.dumps({"id": mine, "method": "Runtime.evaluate",
                        "params": {"expression": expr, "returnByValue": True}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == mine:
            if "error" in m:
                raise RuntimeError(str(m["error"])[:160])
            r = m.get("result", {})
            if r.get("exceptionDetails"):
                raise RuntimeError("页面报错 %s" % str(r["exceptionDetails"])[:160])
            return r.get("result", {}).get("value")


def client_blt(h, cx, cy, cw, chh):
    """客户区采一次：拿 BitBlt 的返回值＋LastError 当"桌面可用"的证据，不看内容。"""
    k32 = ctypes.windll.kernel32
    g = ctypes.windll.gdi32
    g.CreateCompatibleDC.restype = wt.HDC
    g.CreateCompatibleDC.argtypes = [wt.HDC]
    g.CreateCompatibleBitmap.restype = wt.HBITMAP
    g.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
    g.SelectObject.restype = wt.HGDIOBJ
    g.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
    g.BitBlt.restype = ctypes.c_int
    g.BitBlt.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    # 64 位句柄必须按指针宽度传，否则 DeleteObject(bmp) 的 int 会 OverflowError
    g.DeleteObject.restype = ctypes.c_int
    g.DeleteObject.argtypes = [wt.HGDIOBJ]
    g.DeleteDC.restype = ctypes.c_int
    g.DeleteDC.argtypes = [wt.HDC]
    u.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
    u.GetDC.restype = wt.HDC
    u.GetDC.argtypes = [wt.HWND]
    k32.SetLastError.restype = None
    k32.SetLastError.argtypes = [wt.DWORD]
    k32.GetLastError.restype = wt.DWORD
    g.BitBlt.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    k32.SetLastError(0)
    hdc = u.GetDC(None)
    m = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, cw, chh)
    g.SelectObject(m, bmp)
    ok = g.BitBlt(m, 0, 0, cw, chh, hdc, cx, cy, 0x00CC0020 | 1)
    gle = k32.GetLastError()
    g.DeleteObject(bmp)
    g.DeleteDC(m)
    u.ReleaseDC(None, hdc)
    return bool(ok), gle


fails = []
modes = [(m, "0" if m == "--none" else m.replace("--", ""))
         for m in sys.argv[1:] if m.startswith("--") and m != "--page"] \
    or [("--mica", "mica"), ("--acrylic", "acrylic"), ("--none", "0")]
for flag, want in modes:
    status = os.path.join(OUT, "ship-status.txt")
    if os.path.exists(status):
        os.remove(status)
    before = set(find(TITLE))
    p = subprocess.Popen([EXE, flag, "--multi", "--no-taskbar", "--title", TITLE,
                          "--url", PAGE + "?glass=" + want,
                          "--rect", str(RECT[0]), str(RECT[1]), str(RECT[2]), str(RECT[3]),
                          "--status", status, "--cdp", "9431"])
    h = 0
    for _ in range(40):
        time.sleep(0.5)
        hs = [z for z in find(TITLE) if z not in before]
        if hs:
            h = hs[0]
            break
    if not h:
        print("%-9s NO-WINDOW" % flag)
        fails.append((flag, "S1"))
        continue
    tries = 0
    while not (u.GetWindowLongW(wt.HWND(h), -20) & 0x8) and tries < 12:
        u.SetWindowPos(wt.HWND(h), ctypes.c_void_p(-1), 0, 0, 0, 0, 0x1 | 0x2 | 0x10)
        u.SetWindowPos(wt.HWND(h), ctypes.c_void_p(0), 0, 0, 0, 0, 0x1 | 0x2 | 0x10)
        tries += 1
        time.sleep(0.4)
    for _ in range(30):
        if os.path.exists(status):
            break
        time.sleep(0.5)
    time.sleep(3.0)
    txt = ""
    try:
        txt = open(status, encoding="utf-8").read().replace("\n", " | ")
    except Exception:
        txt = "(no status)"
    r = wt.RECT()
    u.GetWindowRect(wt.HWND(h), ctypes.byref(r))
    rc = wt.RECT()
    u.GetClientRect(wt.HWND(h), ctypes.byref(rc))
    ptc = wt.POINT(0, 0)
    u.ClientToScreen(wt.HWND(h), ctypes.byref(ptc))
    ex = u.GetWindowLongW(wt.HWND(h), -20) & 0xFFFFFFFF
    s1 = (r.right - r.left == RECT[2] and r.bottom - r.top == RECT[3]
          and rc.right >= 500 and rc.bottom >= 700)
    s2 = bool(ex & NO_REDIR) == (want != "0")
    s3 = ("bd-rc=0x00000000" in txt and "webview2=ok" in txt and "rect=ok" in txt
          and ("glass=" + want) in txt)
    s4 = s5 = False
    note4 = note5 = "没测到"
    try:
        ws = cdp(9431, URLPART)
        i = [0]
        gp = ev(ws, i, "document.documentElement.dataset.glass||''")
        body = ev(ws, i, "(document.body.innerText||'')")
        tl = len(body)
        big = ev(ws, i, "document.querySelectorAll('.big').length")
        dpr = float(ev(ws, i, "window.devicePixelRatio"))
        iw = float(ev(ws, i, "window.innerWidth"))
        want_gp = "" if want == "0" else want
        # 正文长度随任务/统计动态变化（.page 只渲染当前页），裸 ">200" 是脆阈值。
        # 换成"页面恒定可见的稳定标记"：头部『今日专注』(index.html:664) 在任何状态下都在，
        # 表盘 .big(719) 保证主体控件渲染，长度下限 >80 只用来兜"空白/半渲染"。
        has_marker = "今日专注" in body
        s4 = (gp == want_gp and has_marker and big >= 1 and tl > 80
              and abs(iw * dpr - rc.right) <= 3)
        note4 = "glass=%r 含『今日专注』=%s 正文%d .big=%d 落位 %.0f/%d" % (
            gp, has_marker, tl, big, iw * dpr, rc.right)
        ws.close()
    except Exception as e:
        note4 = repr(e)[:120]
    try:
        ok, gle = client_blt(h, ptc.x, ptc.y, rc.right, rc.bottom)
    except Exception as e:
        ok, gle = False, -1
        note5 = "采集器异常：%s（S1-S4 已独立测完，S5 单独判红）" % repr(e)[:80]
    if note5 == "没测到":
        s5 = ok
        note5 = "BitBlt %s gle=%d" % ("ok" if ok else "FAIL", gle)
        if not ok and gle in (5, 6):
            note5 += " ＝桌面不可用（锁屏/屏保桌面），合成类判据全都跑不了"
    print("%-9s ex=0x%X noredir=%s outer=%dx%d client=%dx%d  %s" %
          (flag, ex, bool(ex & NO_REDIR), r.right - r.left, r.bottom - r.top,
           rc.right, rc.bottom, txt[:120]))
    print("        S1-%s S2-%s S3-%s S4-%s(%s) S5-%s(%s)" %
          ("OK" if s1 else "FAIL", "OK" if s2 else "FAIL", "OK" if s3 else "FAIL",
           "OK" if s4 else "FAIL", note4, "OK" if s5 else "FAIL", note5), flush=True)
    for name, good in (("S1", s1), ("S2", s2), ("S3", s3), ("S4", s4), ("S5", s5)):
        if not good:
            fails.append((flag, name))
    u.PostMessageW(wt.HWND(h), 0x0010, 0, 0)
    for _ in range(15):
        time.sleep(0.4)
        if not find(TITLE):
            break
    try:
        p.terminate()
    except Exception:
        pass
    time.sleep(0.6)

print("SHIP " + ("ALL-OK" if not fails else "FAIL " + repr(fails)))
sys.exit(0 if not fails else 3)
