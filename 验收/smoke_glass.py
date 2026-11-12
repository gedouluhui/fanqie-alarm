# -*- coding: utf-8 -*-
"""生产壳 FqGlass.exe 的四条前提，透明判决之前先证量具本身有效：
   G1 落位：外框真的等于请求的物理尺寸（历史坑：窗停在 202x56，客户区 0 高，
      于是后面所有"透/不透"量的都不是那块面）。
   G2 样式：WS_EX_NOREDIRECTIONBITMAP(0x200000) 只在有材质时应在——--mica/--acrylic 要有，
      --none 不该有（--none 是不透参照，样式反了整轮作废）。
   G3 自报：宿主 status 里 bd-rc=0x00000000 且 webview2=ok（DWM 那步返回 0 才叫接上了）。
   G4 内容：页面真的画出来了——客户区里那块 110 CSS px 红块的红像素数 >= 6000，
      防"整层合成丢掉"冒充"透"（probe_mica4 就是这么把丢层读成完美透明的）。
用法：PYTHONIOENCODING=utf-8 python smoke_glass.py
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import time

u = ctypes.windll.user32
u.SetProcessDPIAware()
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # 交付目录 fanqie-todo\
OUT = os.path.join(os.environ["LOCALAPPDATA"], "fq-glass-verify")
os.makedirs(OUT, exist_ok=True)
EXE = os.path.join(ROOT, "native", "FqGlass.exe")
PAGE = "file:///" + os.path.join(ROOT, "index.html").replace("\\", "/") + "?glass=mica"
TITLE = "FQGLASS"
RECT = (1152, 259, 780, 1470)          # 520x980 CSS @150% ⇒ 外框物理像素
NO_REDIR = 0x00200000
RED_MIN = 6000

u.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
u.GetWindowLongW.restype = ctypes.c_long
u.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
u.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]


class BIH(ctypes.Structure):
    _fields_ = [("s", wt.DWORD), ("w", ctypes.c_long), ("h", ctypes.c_long), ("p", wt.WORD),
                ("b", wt.WORD), ("c", wt.DWORD), ("i", ctypes.c_long), ("x", ctypes.c_long),
                ("y", ctypes.c_long), ("cu", wt.DWORD), ("ci", wt.DWORD)]


g = ctypes.windll.gdi32
g.CreateCompatibleDC.restype = wt.HDC
g.CreateCompatibleBitmap.restype = wt.HGDIOBJ
g.SelectObject.restype = wt.HGDIOBJ
g.CreateCompatibleDC.argtypes = [wt.HDC]
g.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
g.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
g.BitBlt.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                     wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
g.DeleteObject.argtypes = [wt.HGDIOBJ]
g.DeleteDC.argtypes = [wt.HDC]
g.GetDIBits.argtypes = [wt.HDC, wt.HGDIOBJ, wt.UINT, wt.UINT, ctypes.c_void_p,
                        ctypes.POINTER(BIH), wt.UINT]


def shot(x, y, w, h):
    hdc = u.GetDC(None)
    m = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, w, h)
    g.SelectObject(m, bmp)
    g.BitBlt(m, 0, 0, w, h, hdc, x, y, 0x00CC0020 | 1)
    bmi = BIH()
    bmi.s = ctypes.sizeof(bmi)
    bmi.w, bmi.h, bmi.p, bmi.b, bmi.c = w, -h, 1, 32, 0
    buf = ctypes.create_string_buffer(w * h * 4)
    g.GetDIBits(m, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    g.DeleteObject(bmp)
    g.DeleteDC(m)
    u.ReleaseDC(None, hdc)
    raw = bytes(buf)
    return [(raw[i + 2], raw[i + 1], raw[i]) for i in range(0, len(raw), 4)]


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


fails = []
for flag, want_nr in (("--mica", True), ("--acrylic", True), ("--none", False)):
    status = os.path.join(HERE, "glass-smoke-%s.txt" % flag.strip("-"))
    if os.path.exists(status):
        os.remove(status)
    before = set(find(TITLE))
    p = subprocess.Popen([EXE, flag, "--multi", "--no-taskbar", "--title", TITLE,
                          "--url", PAGE, "--rect", str(RECT[0]), str(RECT[1]),
                          str(RECT[2]), str(RECT[3]), "--status", status,
                          "--udf", os.path.join(os.environ["LOCALAPPDATA"], "fq-glass-smoke-udf")])
    h = 0
    for _ in range(30):
        time.sleep(0.5)
        hs = [z for z in find(TITLE) if z not in before]
        if hs:
            h = hs[0]
            break
    if not h:
        print("%-10s NO-WINDOW" % flag, flush=True)
        fails.append((flag, "NO-WINDOW"))
        continue
    for _ in range(24):
        if os.path.exists(status):
            break
        time.sleep(0.5)
    time.sleep(2.5)
    r = wt.RECT()
    u.GetWindowRect(wt.HWND(h), ctypes.byref(r))
    cl = wt.RECT()
    u.GetClientRect(wt.HWND(h), ctypes.byref(cl))
    ex = u.GetWindowLongW(wt.HWND(h), -20) & 0xFFFFFFFF
    txt = ""
    try:
        txt = open(status, encoding="utf-8").read().strip().replace("\n", " | ")
    except Exception:
        txt = "(no status)"
    g1 = (r.right - r.left == RECT[2] and r.bottom - r.top == RECT[3]
          and cl.right >= 500 and cl.bottom >= 700)
    g2 = bool(ex & NO_REDIR) == want_nr
    g3 = ("bd-rc=0x00000000" in txt) and ("webview2=ok" in txt) and ("rect=ok" in txt)
    # 内容闸门取客户区，不取外框：边框那条不是页面。
    px = shot(r.left + (r.right - r.left - cl.right) // 2,
              r.top + (r.bottom - r.top - cl.bottom) // 2 - 0, cl.right, cl.bottom)
    red = sum(1 for q in px if q[0] > 140 and q[0] - q[1] > 55 and q[0] - q[2] > 55)
    g4 = red >= RED_MIN
    print("%-10s outer=%dx%d client=%dx%d ex=0x%X noredirBit=%s  G1-%s G2-%s G3-%s G4-%s(红像素 %d)" %
          (flag, r.right - r.left, r.bottom - r.top, cl.right, cl.bottom, ex,
           bool(ex & NO_REDIR), "OK" if g1 else "FAIL", "OK" if g2 else "FAIL",
           "OK" if g3 else "FAIL", "OK" if g4 else "FAIL", red), flush=True)
    print("      " + txt[:220], flush=True)
    if not (g1 and g2 and g3 and g4):
        fails.append((flag, "".join(n for ok, n in ((g1, "G1"), (g2, "G2"), (g3, "G3"), (g4, "G4")) if not ok)))
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

print("SMOKE " + ("ALL-OK" if not fails else "FAIL " + repr(fails)), flush=True)
print("REMAIN", [hex(z) for z in find(TITLE)], flush=True)
