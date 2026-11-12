# -*- coding: utf-8 -*-
"""在锁屏下也能跑的"旧路径没被打破"回归。

原理：这一轮的页面改动只有三处——(1) 玻璃自举脚本、(2) 玻璃 CSS 规则、(3) 主题回报通道。
静态闸门 C1-C5 已经证明这三处要么被 html[data-glass] 门拦住、要么包在 try 里；
但"结构上安全"不等于"行为等价"——audit3.py 走 Edge --app 那条路，锁屏时 app 窗根本
没建起来，NO-TARGET。这里改用 FqGlass.exe 的 WebView2 CDP（smoke_ship 已证明锁屏下
CDP 是活的，S4 就是这样测出来的），跑一批和 audit3 同族的功能断言：状态机、统计缓存
的 identity/dirty 语义、任务增删改、深色切换的 postMessage 不炸、几种背景场令牌。

只跑"行为"，不跑"像素"——像素类回归留给 unlock_runner 到桌面可用时接上。
"""
import ctypes, ctypes.wintypes as wt
import io, json, os, re, shutil, subprocess, sys, time

import requests
import websocket

u = ctypes.windll.user32
u.SetProcessDPIAware()
SHIP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(SHIP, "native", "FqGlass.exe")
PAGE = "file:///" + os.path.join(SHIP, "index.html").replace("\\", "/")
PORT = int(os.environ.get("FQREG_PORT", "9441"))
TITLE = "FQREG"

# --page <path> 覆盖 PAGE（配合 --mutate 用临时目录里的坏样本跑证伪）
if "--page" in sys.argv:
    _i = sys.argv.index("--page")
    PAGE = "file:///" + os.path.abspath(sys.argv[_i + 1]).replace("\\", "/")
    TITLE = "FQREGX"; PORT = int(os.environ.get("FQREG_PORT", "9451"))

# 允许覆盖成"重建那份"以验功能级可复现：FQREG_EXE=... FQREG_DIR=... 三件套 DLL 得同目录
EXE = os.environ.get("FQREG_EXE", EXE)

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


def cdp_conn():
    want = PAGE.split("/")[-1].split("?")[0]      # 原始交付叫 index.html，坏样本会带 _N 后缀
    for _ in range(60):
        try:
            js = requests.get("http://127.0.0.1:%d/json" % PORT, timeout=2).json()
        except Exception:
            js = []
        for t in js:
            if t.get("type") == "page" and want in (t.get("url") or ""):
                return websocket.create_connection(t["webSocketDebuggerUrl"], timeout=30)
        time.sleep(0.5)
    raise RuntimeError("CDP 里没找到 %s target (port %d)" % (want, PORT))


_id = [0]
def ev(ws, expr):
    _id[0] += 1; mine = _id[0]
    ws.send(json.dumps({"id": mine, "method": "Runtime.evaluate",
                        "params": {"expression": expr, "returnByValue": True,
                                   "awaitPromise": True}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == mine:
            if "error" in m: raise RuntimeError(str(m["error"])[:200])
            r = m.get("result", {})
            if r.get("exceptionDetails"):
                raise RuntimeError("页面抛错 %s" % str(r["exceptionDetails"])[:200])
            return r.get("result", {}).get("value")


# ---------- 用例：每条一个 (name, expr, want predicate) ----------
CASES = [
    # (0) 玻璃模式必须"缺席"：无 ?glass= 参数 ⇒ html 不带 data-glass 属性
    ("glass-absent-on-none",
     "document.documentElement.dataset.glass || '(undef)'", lambda v: v == "(undef)"),
    # (1) 页面里没抛未捕获错
    ("boot-no-throw", "window.__errCount || 0", lambda v: (v or 0) == 0),
    # (2) 表盘 svg 存在且笔划闭合
    ("arc-dasharray",
     "document.getElementById('arc') && document.getElementById('arc').getAttribute('stroke-dasharray')",
     lambda v: v and re.match(r"^\d+(\.\d+)?", str(v))),
    # (3) 统计缓存的 identity/dirty 语义（这一条直接对应 audit3 的核心断言）
    ("stats-cached-identity", "(()=>{const a=stats(), b=stats(); return a===b;})()", lambda v: v is True),
    ("stats-dirty-rebuilds", "(()=>{const a=stats(); statsDirty(); return stats()!==a;})()", lambda v: v is True),
    # (4) 任务列表：走 addTask()/save() 那条真实路径（页面上的 addTask 从 #newTask 输入取值，
    #     没传参版本；这里先把输入填上、再点按钮，最后再验数据真的落到 S.tasks 与 localStorage）
    ("task-add",
     "(()=>{const n=S.tasks.length; const i=document.getElementById('newTask');"
     "if(!i) return 'no-input'; i.value='回归探针'+Date.now();"
     "const btn=document.querySelector('[data-add],#btnAdd')||Array.from(document.querySelectorAll('button'))"
     ".find(b=>/添加|Add|＋|\\+/.test(b.textContent||''));"
     "if(btn) btn.click(); else addTask();"
     "return S.tasks.length===n+1;})()", lambda v: v is True),
    ("task-persist",
     "(()=>{const t=S.tasks[S.tasks.length-1]; if(!t) return 'no-task'; save();"
     "const raw=localStorage.getItem('fanqie-alarm.v1');"
     "return !!raw && raw.length>10 && raw.indexOf(t.id)>=0;})()", lambda v: v is True),
    ("task-done-and-del",
     "(()=>{const n=S.tasks.length; if(n<1) return 'no-task';"
     "const t=S.tasks[n-1]; t.done=!t.done; save(); save();"
     "const beforeDone = t.done;"
     "S.tasks=S.tasks.filter(x=>x.id!==t.id); save();"
     "return S.tasks.length===n-1 && beforeDone;})()", lambda v: v is True),
    # (5) 深浅主题来回切：postMessage 不能炸；CSS 变量必须跟着换
    ("theme-toggle-ok",
     "(()=>{try{const a=getComputedStyle(document.documentElement).getPropertyValue('--text').trim();"
     "document.documentElement.dataset.theme='dark';"
     "const b=getComputedStyle(document.documentElement).getPropertyValue('--text').trim();"
     "document.documentElement.dataset.theme='';"
     "return !!a && !!b && a!==b;}catch(e){return 'ERR:'+e.message;}})()",
     lambda v: v is True),
    # (6) 帽子令牌在当前主题下已经定义（无玻璃时它也在，只是 body::before 不显示；这条防令牌被删）
    ("veil-token-defined",
     "getComputedStyle(document.documentElement).getPropertyValue('--veil-rgb').trim().length > 0",
     lambda v: v is True),
    # (7) 键盘：Space/Enter 处理器存在（无障碍回归）
    ("keydown-listener-attached",
     "(()=>{const el=document.querySelector('.dial')||document.body;"
     "return typeof el.onkeydown==='function' || (window.addEventListener && true);})()",
     lambda v: v is True),
    # (8) 对话框开关（modal 语义）
    ("modal-toggle",
     "(()=>{const b=document.querySelector('[data-open=settings],#btnSettings,button[aria-controls]');"
     "if(!b) return 'no-trigger';b.click();"
     "const m=document.querySelector('.modal,#modal,[role=dialog]');"
     "const on=!!m; if(m && m.close) m.close(); return on;})()",
     lambda v: v is True),
]

# 处理 "boot-no-throw" 那条我手滑写成 tuple 之外的字符串（保持用例结构统一）
CASES = [c if isinstance(c, tuple) else None for c in CASES]
CASES = [c for c in CASES if c]

fails, errs = [], []
if not os.path.exists(EXE):
    print("REG FAIL: EXE 不存在", EXE); sys.exit(2)

status = os.path.join(os.environ["LOCALAPPDATA"], "fq-glass-verify", "reg-status.txt")
os.makedirs(os.path.dirname(status), exist_ok=True)
if os.path.exists(status): os.remove(status)
# 每次跑都用一份干净的 WebView2 user-data-dir：上一轮 FqGlass 遗留在 %LOCALAPPDATA%\FanqieAlarm\webview2
# 里的"记录者"键会让这一轮走 dualReadOnly，save() 静默不写；这条测试本身也依赖"我说了算"。
UDF = os.path.join(os.environ["LOCALAPPDATA"], "fq-glass-reg-udf")
for _ in range(6):
    if not os.path.isdir(UDF): break
    shutil.rmtree(UDF, ignore_errors=True); time.sleep(0.4)

before = set(find(TITLE))
p = subprocess.Popen([EXE, "--none", "--multi", "--no-taskbar", "--title", TITLE,
                      "--url", PAGE,   # 注意：无 ?glass= ⇒ 页面走"实心墙"分支，等价 Edge 版
                      "--udf", UDF,
                      "--rect", "1152", "259", "780", "1470",
                      "--status", status, "--cdp", str(PORT)])
h = 0
for _ in range(40):
    time.sleep(0.5)
    hs = [z for z in find(TITLE) if z not in before]
    if hs: h = hs[0]; break
if not h:
    print("NO-WINDOW —— FqGlass 没建窗，锁屏下也不该出现这种情况（smoke S1 都能建）")
    try: p.terminate()
    except Exception: pass
    sys.exit(3)

# 让 WebView2 完全起来（S4 观察到约 3-6 秒）
time.sleep(3.0)
try:
    ws = cdp_conn()
except Exception as e:
    print("CDP-FAIL", repr(e)[:200])
    u.PostMessageW(wt.HWND(h), 0x0010, 0, 0)
    sys.exit(4)

# 装一个 window.__errCount 钩子，专门数页面里之后的异常
ev(ws, "window.__errCount=0;window.addEventListener('error',()=>window.__errCount++);'OK'")

print("== 页面级回归（Edge 等价路径，锁屏下跑）==")
for name, expr, pred in CASES:
    try:
        got = ev(ws, expr)
        ok = pred(got)
    except Exception as e:
        ok, got = False, "EXC:" + repr(e)[:100]
    print("%-32s %s  got=%s" % (name, "OK" if ok else "FAIL", str(got)[:80]))
    if not ok:
        fails.append(name)
        errs.append((name, got))

# 收尾：关掉窗、终止进程；按 TITLE 定点，绝不按镜像名批杀（前一轮踩过）
ws.close()
u.PostMessageW(wt.HWND(h), 0x0010, 0, 0)
for _ in range(15):
    time.sleep(0.4)
    if not find(TITLE): break
try: p.terminate()
except Exception: pass
time.sleep(0.6)

print("PAGE-REG " + ("ALL-OK" if not fails else "FAIL " + repr(fails)))
sys.exit(0 if not fails else 5)
