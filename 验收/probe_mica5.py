# -*- coding: utf-8 -*-
"""DWM 背景材质判决轮 v4——量"透射率"，不再量"有没有纹理"。

为什么 v3 的判读要作废（这一条很重要，别把工具的错误当成产品的结论）：
  v3 的第一条规则是 var<6 ⇒ FLAT/OPAQUE。可是 Mica 本来就该是几乎平的色调，
  Acrylic 的模糊半径大到能把 30px 棋盘边完全抹平（实测 grad 0.0）。
  也就是说"糊成一片"恰恰是这两种材质的正确长相，却被我的尺子当成了"不透"。
  而同一批数据里唯一变了的只有 backdrop/mode：plain 采到 12.0（宿主自己刷的深灰），
  mica/noredir 采到 242.8，acrylic/extframe 采到 192.4 且 uniq 172、var 2.9——
  那种细碎噪声就是 Acrylic 的 noise 层，app 和 WebView2 谁都不画它。
  ⇒ 结论不能靠"有没有纹理"，要靠"背后的东西能不能影响到这一格"。

v4 的口径（全部是可复现的数字，每条都带正/负对照标定）：
  同一扇被测窗原地不动，只换它背后那整块"场"（纯黑/纯白/纯红/纯蓝/棋盘/藏起来=桌面），
  再量同一个 120x120 采样格：
    slope      ＝ 采样亮度对"场亮度"的回归斜率。真透明≈1（颜色键正对照标定），不透明≈0。
    chromaR    ＝ 纯红场下采样的 R-(G+B)/2。不透明必为 0；能把颜色透出来才谈得上材质。
    gradRatio  ＝ 棋盘场下 采样梯度/同场露在窗外的参照梯度。<1 且 >0 ＝ 真的糊了（模糊）。
    backdropOff＝ 与 plain 同格均值之差。即便 slope=0，只要这块差够大，说明材质在画自己那层。
    posDep     ＝ 换屏幕位置（只换壁纸背景）后均值的变化。Mica 只采壁纸 ⇒ 这项动、slope 不动；
                 Acrylic 采别的窗 ⇒ 两项都动。
  内容闸门：每格同时数页面里那块 110x110 红块的红像素，<6000 直接判 INVALID（防"整块丢了冒充透"）。
对照组（缺一条整轮作废）：
  C1 场的落位：窗外那条"露出来的场"必须真的是这个颜色（否则 slope 量的是别的像素）。
  C2 正对照：原生 WS_EX_LAYERED+LWA_COLORKEY（已知真透明）跑同一套场 ⇒ slope 必须≈1（0.85~1.15）。
  C3 负对照：backdrop=1 + plain（不透的走法）跑同一套场 ⇒ slope 必须≈0；
             它要是也能透出颜色，后面所有 slope 都没有意义。
v5 相对 v4 的两处硬修（v4 的四个 MISS 行不能用）：
  A) 层序闸门换成枚举置顶档：被测窗必须是置顶档第一个，且 slope 只用"层序已证＋内容完整"的格子。
     v4 用 WindowFromPoint，可它天生分不清"颜色键的点不中"和"窗整个不可见"，
     于是 mica/both 那种整层合成丢掉的坏案例被算成了 slope 1.000 的"完美透明"。
  B) 桌面参照在场窗建立之前取。v4 取晚了，把纯白场当成了壁纸亮度。
用法：PYTHONIOENCODING=utf-8 python probe_mica5.py
"""
import ctypes
import ctypes.wintypes as wt
import math
import os
import subprocess
import sys
import threading
import time

u = ctypes.windll.user32
g = ctypes.windll.gdi32
k32 = ctypes.windll.kernel32
u.SetProcessDPIAware()
DPI = u.GetDpiForSystem() / 96.0
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # 交付目录 fanqie-todo\
OUT = os.path.join(os.environ["LOCALAPPDATA"], "fq-glass-verify")
os.makedirs(OUT, exist_ok=True)
EXE = os.path.join(ROOT, "native", "FqGlass.exe")
PAGE = "file:///" + os.path.join(ROOT, "index.html").replace("\\", "/") + "?glass=mica"
TITLE, FIELD_TITLE, KEY_TITLE = "FQMICA", "FQFIELD", "FQKEYCTRL"
BOX = 120
RED_MIN = 6000
CELL = 30
COLORS = [(224, 52, 46), (30, 133, 73), (45, 108, 223), (242, 193, 78), (17, 17, 17), (250, 250, 250)]

u.GetDpiForSystem.restype = ctypes.c_uint
# GDI 句柄在 64 位下不是 32 位安全的（GetDC(None) 给的伪 DC 可能带高位），
# 不声明 restype/argtypes 就会按 c_int 截断——截断过的 DC 传给 BitBlt 是静默 rc=0。
u.GetDC.restype = wt.HDC
u.GetDC.argtypes = [wt.HWND]
u.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
g.CreateCompatibleDC.restype = wt.HDC
g.CreateCompatibleDC.argtypes = [wt.HDC]
g.CreateCompatibleBitmap.restype = wt.HBITMAP
g.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
g.SelectObject.restype = wt.HGDIOBJ
g.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
g.BitBlt.restype = ctypes.c_int
g.BitBlt.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                     wt.HDC, ctypes.c_int, ctypes.c_int, wt.DWORD]
g.GetDIBits.restype = ctypes.c_int
# 第 5 参是 BITMAPINFO*：这里写 c_void_p 而不是 POINTER(BIH)，一是因为 byref() 传进去
# 本来就是指针，二是 BIH 在下面才定义，早期声明块里引用它会直接 NameError。
g.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p,
                        ctypes.c_void_p, wt.UINT]
g.CreateSolidBrush.restype = wt.HBRUSH
g.DeleteObject.argtypes = [wt.HGDIOBJ]
g.DeleteDC.argtypes = [wt.HDC]
k32.GetLastError.restype = wt.DWORD
u.SetWindowPos.argtypes = [wt.HWND, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                           ctypes.c_int, ctypes.c_int, ctypes.c_uint]
u.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
u.GetWindowLongW.restype = ctypes.c_long
u.SetLayeredWindowAttributes.argtypes = [wt.HWND, ctypes.c_uint, ctypes.c_ubyte, ctypes.c_uint]
u.DefWindowProcW.argtypes = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
u.DefWindowProcW.restype = ctypes.c_ssize_t
u.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
u.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
u.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
u.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
u.WindowFromPoint.argtypes = [wt.POINT]
u.WindowFromPoint.restype = wt.HWND
u.GetAncestor.argtypes = [wt.HWND, ctypes.c_uint]
u.GetAncestor.restype = wt.HWND
u.keybd_event.argtypes = [wt.BYTE, wt.BYTE, wt.DWORD, ctypes.c_void_p]
u.InvalidateRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT), ctypes.c_int]
u.UpdateWindow.argtypes = [wt.HWND, ctypes.c_int]
u.CreateWindowExW.restype = wt.HWND
u.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                              ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                              wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
k32.GetModuleHandleW.restype = wt.HINSTANCE
k32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
u.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM)


class PS(ctypes.Structure):
    # PAINTSTRUCT 尾部那 32 字节 reserved 必须留：少了 BeginPaint 直接写过栈顶（上一版段错误就在这）。
    _fields_ = [("hdc", wt.HDC), ("fErase", ctypes.c_int), ("rcPaint", wt.RECT),
                ("restore", ctypes.c_int), ("incUpdate", ctypes.c_int),
                ("rv", ctypes.c_byte * 32)]


class WCE(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE), ("hIcon", wt.HANDLE), ("hCursor", wt.HANDLE),
                ("hbrBackground", wt.HANDLE), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HANDLE)]


class BIH(ctypes.Structure):
    _fields_ = [("s", wt.DWORD), ("w", ctypes.c_long), ("h", ctypes.c_long), ("p", wt.WORD),
                ("b", wt.WORD), ("c", wt.DWORD), ("i", ctypes.c_long), ("x", ctypes.c_long),
                ("y", ctypes.c_long), ("cu", wt.DWORD), ("ci", wt.DWORD)]


# BeginPaint 收的是 PAINTSTRUCT 本体（不是 c_void_p 占位）；FillRect 的第一参是 HDC。
# 这两条 argtypes 不声明，64 位下 byref(PS) 会被当成整数传，栈一写就飞。
u.BeginPaint.argtypes = [wt.HWND, ctypes.POINTER(PS)]
u.BeginPaint.restype = wt.HDC
u.EndPaint.argtypes = [wt.HWND, ctypes.POINTER(PS)]
u.FillRect.argtypes = [wt.HDC, ctypes.POINTER(wt.RECT), ctypes.c_void_p]
u.GetWindow.argtypes = [wt.HWND, ctypes.c_uint]
u.GetWindow.restype = wt.HWND
u.GetDesktopWindow.restype = wt.HWND
u.IsWindowVisible.argtypes = [wt.HWND]
u.IsWindowVisible.restype = ctypes.c_bool
u.IsIconic.argtypes = [wt.HWND]
u.IsIconic.restype = ctypes.c_bool


def above(h, rect=None):
    """把 h 顶到"最靠前的那批置顶窗"的最上面。

    两条都得调，少一条就是上一轮那种假结论：
      -1（HWND_TOPMOST）只保证它带置顶样式——已经带了的再调一次根本不会重排；
       0（HWND_TOP）才真的把它挪到当前层序顶上。场窗也是置顶窗，
       所以只调前者时，ShowWindow(SW_SHOW) 重新露头的场完全可能压在被测窗上面，
       那时量到的"透"其实是场自己的像素。
    """
    u.SetWindowPos(wt.HWND(h), -1, 0, 0, 0, 0, 0x1 | 0x2 | 0x10)
    if rect is not None:
        u.SetWindowPos(wt.HWND(h), 0, rect[0], rect[1], rect[2], rect[3], 0x10)
    else:
        u.SetWindowPos(wt.HWND(h), 0, 0, 0, 0, 0, 0x1 | 0x2 | 0x10)


GW_HWNDFIRST, GW_HWNDNEXT, GW_CHILD = 0, 2, 5


def ready_from(name, w, h):
    """解锁判据的纯谓词（desktop_ready 把三个输入取回来之后交给它）。
    唯一可信的信号是输入桌面名回到 Default；w/h 只回答"显示器没在休眠"（休眠时 GetSystemMetrics
    返回 0），拿它当解锁判据是历史事故：SM_CXDLGFRAME/SM_CYDLGFRAME（7/8，恒 ~3×3）被误当成屏尺寸，
    看门狗在桌面已解锁的状态下永远不触发。抽成纯函数是为了在锁屏时也能离线证明判据没写反。"""
    return name == "Default" and w > 100 and h > 100


def desktop_ready():
    """⇒ (可采像素?, "现场描述")。全仓库只此一处实现，unlock_runner／ready_once 都必须从这里导入，
    否则会出现两个检测器各拿一套解锁判据、一个跑一个死等（这正是上一轮自查点名的重复实现）。"""
    u.OpenInputDesktop.restype = wt.HANDLE
    hh = u.OpenInputDesktop(1, False, 0)
    if not hh:
        return False, "OpenInputDesktop=NULL gle=%d" % k32.GetLastError()
    buf = ctypes.create_unicode_buffer(256)
    sz = wt.DWORD(0)
    u.GetUserObjectInformationW(hh, 2, buf, 512, ctypes.byref(sz))
    u.CloseDesktop(hh)
    return ready_from(buf.value, u.GetSystemMetrics(78), u.GetSystemMetrics(79)), \
        "%s %dx%d" % (buf.value, u.GetSystemMetrics(78), u.GetSystemMetrics(79))


def zband():
    """当前层序里"置顶那一档"的可见窗口，从上到下的句柄列表。

    起走点必须是 GW_CHILD 不是 GW_HWNDFIRST：从桌面窗调 GW_HWNDFIRST 实测返回 0，
    于是枚举器静默给出空表——那种情况下每一个采样点都会被判"层序 BAD"，
    整轮结论会伪装成"全都 INVALID"，而真相只是我的尺子读不到数（probe_z 自检抓到的）。
    """
    h = u.GetWindow(wt.HWND(u.GetDesktopWindow()), GW_CHILD)
    out, guard = [], 0
    while h and guard < 4000:
        guard += 1
        ex = u.GetWindowLongW(wt.HWND(h), -20) & 0xFFFFFFFF
        if ex & 0x8:                                   # WS_EX_TOPMOST
            st = u.GetWindowLongW(wt.HWND(h), -16) & 0xFFFFFFFF
            if st & 0x10000000:                        # WS_VISIBLE
                out.append(int(h))
        h = u.GetWindow(wt.HWND(h), GW_HWNDNEXT)
    return out


def sample_rect(h):
    """采样格（被测窗正中 120x120）的屏幕矩形，供层序相交测试用。"""
    l, t, r_, b_ = win_rect(h)
    ww, hh = r_ - l, b_ - t
    return l + ww // 2 - BOX // 2, t + hh // 2 - BOX // 2, BOX, BOX



def win_title(h):
    n = u.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(h, b, n + 1)
    return b.value or "(无名)"


def win_cls(h):
    b = ctypes.create_unicode_buffer(64)
    u.GetClassNameW(h, b, 64)
    return b.value or "?"


def win_rect(h):
    r = wt.RECT()
    u.GetWindowRect(wt.HWND(h), ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def above_field(h, fh=None):
    """采样格上面还有没有别的可见置顶窗压着它——这才是"我量到的是这扇窗"的证据。

    v4 用 WindowFromPoint 当这个证据，可它天生分不清两件事：
      ·颜色键的洞点不中（正对照本该如此，不是故障）；
      ·被测窗整层合成没了／被场盖住（那才是故障）。
    两种都报 MISS，于是 v4 把 mica/both 那种"内容 0 红像素"的坏案例当成 slope 1.000 的完美透明。
    现在改成显式枚举置顶档，凡排在被测窗前面、且矩形跟采样格相交的非零尺寸窗，一律点名。
    """
    band = zband()
    if int(h) not in band:
        return False, [("不在置顶档（不可见或没置顶）", hex(int(h)))]
    sx, sy, sw, sh = sample_rect(h)
    blockers = []
    for x in band[:band.index(int(h))]:
        l, t, r_, b_ = win_rect(x)
        if r_ - l <= 0 or b_ - t <= 0:
            continue                        # ThumbnailDeviceHelperWnd 这类零尺寸系统窗，压不住任何东西
        if r_ < sx or l > sx + sw or b_ < sy or t > sy + sh:
            continue                        # 与采样格不相交
        blockers.append((win_cls(x), win_title(x), hex(x), (l, t, r_, b_)))
    return not blockers, blockers


def shot(x, y, w, h, tries=4):
    """屏幕 DC 的 BitBlt+CAPTUREBLT：只看 DWM 合成之后的最终结果，这是唯一能看见材质长相的口径。"""
    x, y, w, h = int(x), int(y), int(w), int(h)
    last = None
    for attempt in range(tries):
        hdc = u.GetDC(None)
        if not hdc:
            last = "GetDC=0 gle=%d" % k32.GetLastError()
            time.sleep(0.4)
            continue
        m = g.CreateCompatibleDC(wt.HDC(hdc))
        bmp = g.CreateCompatibleBitmap(wt.HDC(hdc), w, h)
        if not m or not bmp:
            last = "GDI obj 0 (dc=%s bmp=%s) gle=%d" % (bool(m), bool(bmp), k32.GetLastError())
            u.ReleaseDC(None, hdc)
            time.sleep(0.4)
            continue
        g.SelectObject(m, bmp)
        ok = g.BitBlt(m, 0, 0, w, h, hdc, x, y, 0x00CC0020 | 1)
        bmi = BIH()
        bmi.s = ctypes.sizeof(bmi)
        bmi.w, bmi.h, bmi.p, bmi.b, bmi.c = w, -h, 1, 32, 0
        buf = ctypes.create_string_buffer(w * h * 4)
        got = g.GetDIBits(m, bmp, 0, h, buf, ctypes.byref(bmi), 0)
        gle = k32.GetLastError()
        g.DeleteObject(bmp)
        g.DeleteDC(m)
        u.ReleaseDC(None, hdc)
        if ok and got == h:
            raw = bytes(buf)
            return [(raw[i + 2], raw[i + 1], raw[i]) for i in range(0, len(raw), 4)], w
        last = "rc=%s lines=%s gle=%d" % (ok, got, gle)
        time.sleep(0.5)
    raise RuntimeError("capture failed after %d tries: %s @(%d,%d %dx%d)" % (tries, last, x, y, w, h))


def patch(px, w, x, y, n=BOX):
    x, y = int(x), int(y)
    return [px[(y + r) * w + x + c] for r in range(n) for c in range(n)]


def lum(p):
    return 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]


def stats(sub):
    L = [lum(p) for p in sub]
    n = len(L)
    m = sum(L) / n
    var = sum((v - m) ** 2 for v in L) / n
    return m, var, len(set(sub))


def rgb_mean(sub):
    n = len(sub)
    return (sum(p[0] for p in sub) / n, sum(p[1] for p in sub) / n, sum(p[2] for p in sub) / n)


def grad(sub, n=BOX):
    tot, cnt = 0.0, 0
    for r in range(n):
        row = sub[r * n:(r + 1) * n]
        for c in range(n - 1):
            tot += abs(lum(row[c + 1]) - lum(row[c]))
            cnt += 1
    return tot / cnt


def red_count(px):
    return sum(1 for p in px if p[0] > 140 and p[0] - p[1] > 55 and p[0] - p[2] > 55)


def slope(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    d = sum((x - mx) ** 2 for x in xs)
    return round(sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / d, 4) if d > 1e-6 else 0.0


def find_title(title):
    found = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def fn(h, l):
        n = u.GetWindowTextLengthW(h)
        if n and u.IsWindowVisible(h):
            b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(h, b, n + 1)
            if b.value == title:
                found.append(int(h))
        return True
    u.EnumWindows(proto(fn), 0)
    return found


def hwnd_rect(h):
    r = wt.RECT()
    u.GetWindowRect(wt.HWND(h), ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


class Field(threading.Thread):
    """被测窗背后那一整块"场"：颜色可由主线程随时改，改完自己重画。

    它比被测窗每边大 170px，于是永远有一圈露在外面——那圈就是 C1 落位对照：
    露在外面都显示成这个颜色，才说明窗口底下那格也真的压着同一个颜色。
    """

    def __init__(self, geom):
        super().__init__(daemon=True)
        self.geom = geom
        self.rgb = (255, 255, 255)
        self.checker = False
        self.hwnd = 0
        self.ready = threading.Event()
        self.paint_done = threading.Event()
        self._keep = WNDPROC(self._wndproc)

    def _paint(self, hdc):
        w, hh = self.geom[2], self.geom[3]
        r = wt.RECT(0, 0, w, hh)
        if self.checker:
            for gy in range(0, hh, CELL):
                for gx in range(0, w, CELL):
                    col = COLORS[((gx // CELL) + (gy // CELL)) % len(COLORS)]
                    br = g.CreateSolidBrush((col[2] << 16) | (col[1] << 8) | col[0])
                    u.FillRect(hdc, ctypes.byref(wt.RECT(gx, gy, min(gx + CELL, w), min(gy + CELL, hh))),
                               ctypes.c_void_p(br))
                    g.DeleteObject(br)
        else:
            br = g.CreateSolidBrush((self.rgb[2] << 16) | (self.rgb[1] << 8) | self.rgb[0])
            u.FillRect(hdc, ctypes.byref(r), ctypes.c_void_p(br))
            g.DeleteObject(br)

    def _wndproc(self, h, msg, wp, lp):
        if msg == 0x000F:
            ps = PS()
            hdc = u.BeginPaint(h, ctypes.byref(ps))
            self._paint(hdc)
            u.EndPaint(h, ctypes.byref(ps))
            self.paint_done.set()
            return 0
        if msg == 0x0002:
            u.PostQuitMessage(0)
            return 0
        return u.DefWindowProcW(h, msg, wp, lp)

    def run(self):
        inst = wt.HINSTANCE(k32.GetModuleHandleW(None))
        wc = WCE()
        wc.cbSize = ctypes.sizeof(wc)
        wc.lpfnWndProc = self._keep
        wc.hInstance = inst
        wc.lpszClassName = "FqFieldWin4"
        u.RegisterClassExW(ctypes.byref(wc))
        h = u.CreateWindowExW(0, "FqFieldWin4", FIELD_TITLE, 0x80000000 | 0x10000000,
                              self.geom[0], self.geom[1], self.geom[2], self.geom[3],
                              None, None, inst, None)
        self.hwnd = int(h)
        u.ShowWindow(h, 5)
        u.SetWindowPos(h, -1, 0, 0, 0, 0, 0x1 | 0x2 | 0x10)   # TOPMOST, NOSIZE, NOMOVE, NOACTIVATE
        u.UpdateWindow(h, 0)
        self.ready.set()
        msg = wt.MSG()
        run = True
        while run:
            while u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                if msg.message == 0x0012:
                    run = False
                    break
                u.TranslateMessage(ctypes.byref(msg))
                u.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.02)

    def set_field(self, rgb=None, checker=False, hide=False):
        self.paint_done.clear()
        if rgb is not None:
            self.rgb = rgb
            self.checker = False
        elif checker:
            self.checker = True
        if hide:
            u.ShowWindow(wt.HWND(self.hwnd), 0)
            return
        u.ShowWindow(wt.HWND(self.hwnd), 5)
        # 只 InvalidateRect，不调 UpdateWindow：这扇窗的消息归属线程是 Field.run，
        # 从主线程调 UpdateWindow 会把 WM_PAINT 直接送进"调用线程"里执行 wndproc，
        # BeginPaint 就作用在错误的线程上（更新区域/绘制线程一错，场画不画全凭运气）。
        u.InvalidateRect(wt.HWND(self.hwnd), None, 1)
        self.paint_done.wait(4)

    def move(self, rect):
        """被测窗换屏幕位置时，场要跟着盖住它＋留出一圈参照，否则 C1 落位对照就失效了。"""
        self.geom = rect
        self.paint_done.clear()
        u.ShowWindow(wt.HWND(self.hwnd), 5)
        u.SetWindowPos(wt.HWND(self.hwnd), -1, rect[0], rect[1], rect[2], rect[3], 0x10)
        u.InvalidateRect(wt.HWND(self.hwnd), None, 1)
        self.paint_done.wait(4)

    def stop(self):
        if self.hwnd:
            u.PostMessageW(wt.HWND(self.hwnd), 0x0010, 0, 0)


class KeyCtrl(threading.Thread):
    """正对照：WS_EX_LAYERED + 颜色键，品红被抠掉＝已知真透明；中心 24px 处留红块当内容证据。"""

    def __init__(self, geom):
        super().__init__(daemon=True)
        self.geom = geom
        self.hwnd = 0
        self.ready = threading.Event()
        self._keep = WNDPROC(self._wndproc)

    def _wndproc(self, h, msg, wp, lp):
        if msg == 0x000F:
            ps = PS()
            hdc = u.BeginPaint(h, ctypes.byref(ps))
            br = g.CreateSolidBrush(0x00FF00FF)
            u.FillRect(hdc, ctypes.byref(wt.RECT(0, 0, self.geom[2], self.geom[3])), ctypes.c_void_p(br))
            g.DeleteObject(br)
            br2 = g.CreateSolidBrush(0x002E34E0)
            u.FillRect(hdc, ctypes.byref(wt.RECT(24, 24, 134, 134)), ctypes.c_void_p(br2))
            g.DeleteObject(br2)
            u.EndPaint(h, ctypes.byref(ps))
            return 0
        if msg == 0x0002:
            u.PostQuitMessage(0)
            return 0
        return u.DefWindowProcW(h, msg, wp, lp)

    def run(self):
        inst = wt.HINSTANCE(k32.GetModuleHandleW(None))
        wc = WCE()
        wc.cbSize = ctypes.sizeof(wc)
        wc.lpfnWndProc = self._keep
        wc.hInstance = inst
        wc.lpszClassName = "FqKeyWin4"
        u.RegisterClassExW(ctypes.byref(wc))
        h = u.CreateWindowExW(0x00080000, "FqKeyWin4", KEY_TITLE, 0x80000000,
                              self.geom[0], self.geom[1], self.geom[2], self.geom[3],
                              None, None, inst, None)
        self.hwnd = int(h)
        self.keyrc = bool(u.SetLayeredWindowAttributes(h, 0x00FF00FF, 0, 1))
        u.ShowWindow(h, 5)
        u.SetWindowPos(h, -1, 0, 0, 0, 0, 0x1 | 0x2 | 0x10)
        u.UpdateWindow(h, 0)
        self.ready.set()
        msg = wt.MSG()
        run = True
        while run:
            while u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                if msg.message == 0x0012:
                    run = False
                    break
                u.TranslateMessage(ctypes.byref(msg))
                u.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.02)

    def stop(self):
        if self.hwnd:
            u.PostMessageW(wt.HWND(self.hwnd), 0x0010, 0, 0)


def launch_poc(backdrop, mode, rect, tag):
    udf = os.path.join(os.environ["LOCALAPPDATA"], "fq-mica-udf4-" + tag)
    status = os.path.join(HERE, "mica4-status-" + tag + ".txt")
    if os.path.exists(status):
        os.remove(status)
    before = set(find_title(TITLE))
    p = subprocess.Popen([EXE, str(backdrop), PAGE, udf, str(rect[0]), str(rect[1]),
                          str(rect[2]), str(rect[3]), status, mode])
    h = 0
    for _ in range(30):
        time.sleep(0.5)
        new = [x for x in find_title(TITLE) if x not in before]
        if new:
            h = new[0]
            break
    if not h:
        return 0, p, "NO-WINDOW"
    for _ in range(24):
        if os.path.exists(status):
            break
        time.sleep(0.5)
    time.sleep(2.0)
    try:
        txt = open(status, encoding="utf-8").read().strip().replace("\n", " | ")
    except Exception:
        txt = "(no status)"
    u.keybd_event(0x12, 0, 0, 0)
    u.keybd_event(0x12, 0, 2, 0)
    u.SetForegroundWindow(wt.HWND(h))
    time.sleep(1.0)
    return h, p, txt


def place_topmost(h, rect):
    """被测窗落到指定位置，并保证它压在场上面（置顶样式＋层序置顶，两步都要）。"""
    above(h, rect)
    time.sleep(0.9)


def kill(h, p):
    try:
        u.PostMessageW(wt.HWND(h), 0x0010, 0, 0)
    except Exception:
        pass
    for _ in range(12):
        time.sleep(0.4)
        if not find_title(TITLE):
            break
    try:
        p.terminate()
    except Exception:
        pass
    time.sleep(0.4)


def sample_on(h, rect):
    """在被测窗客户区正中取 120x120，同时取窗外那条"露出来的场"当落位参照。
       返回 (sub, strip, red, hit_point)；层序是否真的压住场由 above_field 单独判。"""
    r = wt.RECT()
    u.GetWindowRect(wt.HWND(h), ctypes.byref(r))
    ww, hh = r.right - r.left, r.bottom - r.top
    if ww < BOX + 8 or hh < BOX + 8:
        # 窗没落位就去取 120 见方，patch 会静默读到别的行（上一版在这上面 IndexError）。
        raise RuntimeError("window too small: %dx%d" % (ww, hh))
    pnt = wt.POINT((r.left + r.right) // 2, (r.top + r.bottom) // 2)
    deep = u.WindowFromPoint(pnt)
    owner = int(u.GetAncestor(deep, 2) or 0) if deep else 0
    full, fw = shot(r.left, r.top, ww, hh)
    sub = patch(full, fw, ww // 2 - BOX // 2, hh // 2 - BOX // 2)
    strip, sw_ = shot(r.right + 20, r.top + 40, BOX, BOX)
    return sub, strip, red_count(full), owner == int(h)


FIELDS = [("黑", (0, 0, 0)), ("白", (255, 255, 255)), ("红", (255, 0, 0)), ("蓝", (0, 0, 255))]


def one(field, h, label, name, **kw):
    """换一次场 → 把被测窗顶回去 → 确认层序 → 采一格。层序不对就重试一次，再不对就作废这格。"""
    field.set_field(**kw)
    ok, blockers = False, []
    for _ in range(2):
        above(h)
        time.sleep(0.7)
        ok, blockers = above_field(h, field.hwnd)
        if ok:
            break
    sub, strip, rc, hitp = sample_on(h, None)
    m, var, q = stats(sub)
    rm, gm, bm = rgb_mean(sub)
    row = dict(lum=m, var=var, uniq=q, chroma=rm - (gm + bm) / 2.0, red=rc,
               ordered=ok, hit_point=hitp, grad=grad(sub), strip_grad=grad(strip),
               strip_lum=stats(strip)[0])
    print("  %-16s 场=%-3s 采样 mean %6.1f var %6.1f uniq %3d R色度 %+6.1f 梯度 %5.2f | "
          "窗外场 mean %6.1f 梯度 %5.2f | 红像素 %5d 层序 %s 点中 %s" %
          (label, name, m, var, q, row["chroma"], row["grad"], row["strip_lum"],
           row["strip_grad"], rc, "OK" if ok else "BAD", "Y" if hitp else "n"), flush=True)
    if not ok:
        print("  %-16s      压在采样格上面的窗：%s" % (label, blockers[:3]), flush=True)
    return row


def sweep(field, h, label):
    """同一扇窗、同一格，只换背后的场：slope / chromaR / 梯度残留 三个数都从这里来。"""
    rows = {}
    for name, rgb in FIELDS:
        rows[name] = one(field, h, label, name, rgb=rgb)
    rows["棋盘"] = one(field, h, label, "棋盘", checker=True)
    rows["桌面"] = one(field, h, label, "桌面", hide=True)
    return rows


def summarize(label, rows, plain_rows, key_mode=False):
    names = [nm for nm in ["黑", "白", "红", "蓝"]
             if rows[nm]["ordered"] and (key_mode or rows[nm]["red"] >= RED_MIN)]
    xs = [lum(dict(FIELDS)[nm]) for nm in names]
    ys = [rows[nm]["lum"] for nm in names]
    sl = slope(xs, ys) if len(names) >= 3 else float("nan")
    chr_ = rows["红"]["chroma"] if rows["红"]["ordered"] else float("nan")
    gk = 100.0 * rows["棋盘"]["grad"] / max(rows["棋盘"]["strip_grad"], 1e-6) \
        if rows["棋盘"]["ordered"] else float("nan")
    keep = sum(1 for nm in rows if rows[nm]["red"] >= RED_MIN)
    good = sum(1 for nm in rows if rows[nm]["ordered"])
    flat_gap = (rows["桌面"]["lum"] - plain_rows["桌面"]["lum"]) if plain_rows else 0.0
    print("%-22s n=%d/6 层序 %d/6  slope %+0.3f  红场色度 %+6.1f  棋盘梯度残留 %5.1f%%  "
          "与不透底色差 %+6.1f" % (label, len(names), good, sl, chr_, gk, flat_gap), flush=True)
    return dict(slope=sl, chroma=chr_, grad_keep=gk, gap=flat_gap, keep=keep,
                ordered=good, n=len(names))


def preclean():
    for t in (TITLE, FIELD_TITLE, KEY_TITLE):
        for h in find_title(t):
            u.PostMessageW(wt.HWND(h), 0x0010, 0, 0)
            print("PRECLOSE 残留", t, hex(h), flush=True)


def main():
    preclean()
    sw, sh = u.GetSystemMetrics(78), u.GetSystemMetrics(79)
    W, H = int(420 * DPI), int(620 * DPI)
    p1 = (int(sw * 0.30), int(sh * 0.12), W, H)
    pad = 170
    geom_field = (p1[0] - pad, p1[1] - pad, W + 2 * pad, H + 2 * pad)
    print("DPI %.2f 被测窗 %s  场 %s  屏幕 %dx%d" % (DPI, p1, geom_field, sw, sh), flush=True)

    # 桌面参照必须在场窗建起来之前取。v4 把顺序搞反了：那时 P1 的"桌面亮度 255.0"
    # 其实是那张纯白场自己，拿它当壁纸参照等于把"透出来的白"当成"本来就白"。
    def desk(cx, cy):
        px, pw = shot(cx, cy, W, H)
        sub = patch(px, pw, W // 2 - BOX // 2, H // 2 - BOX // 2)
        return stats(sub) + (grad(sub),)
    d1 = desk(p1[0], p1[1])
    print("参照·P1 该点可见内容 mean %.1f var %.1f uniq %d grad %.2f" % d1, flush=True)
    cands = [(int(sw * 0.06), int(sh * 0.55)), (int(sw * 0.62), int(sh * 0.06)),
             (int(sw * 0.55), int(sh * 0.62)), (int(sw * 0.06), int(sh * 0.06))]
    best, bl = None, 0.0
    for cx, cy in cands:
        cx, cy = max(20, min(cx, sw - W - 20)), max(20, min(cy, sh - H - 60))
        d = desk(cx, cy)
        print("  候选位 %d,%d mean %6.1f var %6.1f uniq %d（与 P1 差 %.1f）" %
              (cx, cy, d[0], d[1], d[2], abs(d[0] - d1[0])), flush=True)
        if abs(d[0] - d1[0]) > bl:
            bl, best = abs(d[0] - d1[0]), (cx, cy, W, H)
    print("选 P2 %s 亮度差 %.1f（>=8 才跑位置测试）" % (best, bl), flush=True)

    field = Field(geom_field)
    field.start()
    if not field.ready.wait(8):
        print("SETUP-FAIL 场窗没建起来")
        sys.exit(3)
    time.sleep(0.8)
    field.set_field(rgb=(255, 255, 255))

    # C2 正对照：颜色键的洞天生点不中（WindowFromPoint 会穿过去），所以它只看层序＋内容。
    key = KeyCtrl(p1)
    key.start()
    key.ready.wait(8)
    time.sleep(0.8)
    above(int(key.hwnd))
    krows = sweep(field, int(key.hwnd), "C2正对照(颜色键)")
    ks = summarize("C2正对照", krows, None, key_mode=True)
    key.stop()
    time.sleep(0.6)

    combos = [(1, "plain", "C3负对照 bd1/plain"), (2, "noredir", "mica/noredir"),
              (2, "extframe", "mica/extframe"), (2, "both", "mica/both"),
              (3, "noredir", "acrylic/noredir"), (3, "extframe", "acrylic/extframe"),
              (3, "both", "acrylic/both")]
    out, plain_rows = {}, None
    for bd, mode, label in combos:
        h, p, txt = launch_poc(bd, mode, p1, "%d-%s" % (bd, mode))
        if not h:
            print("%-22s %s" % (label, txt), flush=True)
            continue
        place_topmost(h, p1)
        # v4 里四个组合报 MISS 却说不出为什么：窗可能根本没显示（NOREDIRECTIONBITMAP
        # 加材质把整层合成丢了），也可能只是被场盖住。这两种是完全不同的结论，
        # 所以把可见性、最小化、层序排名、宿主自报的样式一次打全。
        band = zband()
        print("%-22s 状态 IsVisible=%s IsIconic=%s rect=%s 置顶档排名 %s 置顶档前缀 %s" %
              (label, bool(u.IsWindowVisible(wt.HWND(h))), bool(u.IsIconic(wt.HWND(h))),
               hwnd_rect(h), (band.index(int(h)) if int(h) in band else "不在档内"),
               [hex(z) for z in band[:4]]), flush=True)
        print("%-22s 宿主自报 %s" % (label, txt[:190]), flush=True)
        rows = sweep(field, h, label)
        s = summarize(label, rows, plain_rows)
        if label.startswith("C3"):
            plain_rows = rows
        if best and bl >= 8:
            p2 = (best[0], best[1], W, H)
            field.move((p2[0] - pad, p2[1] - pad, W + 2 * pad, H + 2 * pad))
            field.set_field(rgb=(255, 255, 255))
            place_topmost(h, p2)
            r2w = one(field, h, label + " P2", "白", rgb=(255, 255, 255))
            r2d = one(field, h, label + " P2", "桌面", hide=True)
            # posDep＝场恒定（纯白）只挪窗：只有"采壁纸"的材质会跟着壁纸区域变；
            # fieldDepP2＝同点换场（白→只剩桌面）：确认 P2 上场还有效，不是白挪一趟。
            s["pos_dep"] = round(r2w["lum"] - rows["白"]["lum"], 1) if r2w["ordered"] else float("nan")
            s["field_dep_p2"] = round(r2d["lum"] - r2w["lum"], 1)
            s["p2_ok"] = r2w["ordered"] and r2d["red"] >= RED_MIN
            print("%-22s P2 白场 %.1f（P1 白场 %.1f）posDep %+6.1f | 只剩桌面 %.1f fieldDep %+6.1f" %
                  (label, r2w["lum"], rows["白"]["lum"], s["pos_dep"], r2d["lum"],
                   s["field_dep_p2"]), flush=True)
            field.move(geom_field)
            field.set_field(rgb=(255, 255, 255))
            place_topmost(h, p1)
        out[label] = (s, rows)
        kill(h, p)

    neg = out.get("C3负对照 bd1/plain", ({}, {}))[0]
    print(chr(10) + "标定：正对照 n=%d slope %+.3f / 色度 %+.1f / 梯度残留 %.1f%%；"
          "负对照 n=%d slope %+.3f / 色度 %+.1f" %
          (ks["n"], ks["slope"], ks["chroma"], ks["grad_keep"],
           neg.get("n", 0), neg.get("slope", float("nan")), neg.get("chroma", float("nan"))), flush=True)
    if ks["n"] < 3 or not (0.85 <= ks["slope"] <= 1.15):
        print("C2-FAIL 正对照（已知真透明）slope=%s n=%d——尺子连透明都量不准，本轮作废" %
              (ks["slope"], ks["n"]), flush=True)
        sys.exit(3)
    if neg["n"] < 3 or abs(neg["slope"]) > 0.05 + 0.06 * abs(ks["slope"]):
        print("C3-FAIL 负对照（明确不透明）slope=%s n=%d——不透明都能被判透，结论作废" %
              (neg["slope"], neg["n"]), flush=True)
        sys.exit(3)

    print(chr(10) + "判决（slope/色度阈值＝正对照的 10%%；底色差＝与负对照同格之差；"
          "posDep＝纯白场下只挪窗的亮度变化）", flush=True)
    for label, (s, rows) in out.items():
        if label.startswith("C3"):
            continue
        if s["n"] < 3:
            print("  %-24s INVALID（层序已证且内容完整的格子只有 %d/6，量不出 slope）" %
                  (label, s["n"]), flush=True)
            continue
        thr_sl = 0.10 * abs(ks["slope"])
        thr_ch = 0.10 * abs(ks["chroma"])
        behind = abs(s["slope"]) >= thr_sl or abs(s["chroma"]) >= thr_ch
        wp_dep = abs(s.get("pos_dep", 0.0)) >= 8.0
        gap = s.get("gap", 0.0)
        if behind:
            v = "ACRYLIC-BEHIND（别的窗口被糊进客户区＝真模糊）"
        elif wp_dep or abs(gap) >= 25:
            v = "MICA-WALLPAPER（材质这层在画，但只采壁纸不采别的窗）"
        else:
            v = "OPAQUE（材质没进客户区）"
        print("  %-24s %-42s n=%d slope %+0.3f(阈 %.2f) 色度 %+6.1f(阈 %.1f) 梯度残留 %5.1f%% "
              "底色差 %+6.1f posDep %+6.1f" %
              (label, v, s["n"], s["slope"], thr_sl, s["chroma"], thr_ch, s["grad_keep"],
               gap, s.get("pos_dep", 0.0)), flush=True)
    field.stop()
    print("DONE", flush=True)


if __name__ == "__main__":
    # probe_glass.py 要 import 这堆量具（场窗／层序证明／BitBlt 尺子），
    # 所以 main() 只能在 __main__ 里跑，不然"导入"就等于"开测"。
    main()
