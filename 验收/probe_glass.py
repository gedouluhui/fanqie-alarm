# -*- coding: utf-8 -*-
"""生产壳 FqGlass.exe ＋真页面（index.html?glass=…）的合成后判决：材质接上了，代价是什么。

三个问题都只能在"真窗口＋真桌面背景"的最终合成像素上答——CDP 的截图里没有 DWM 那层，
所以像素走 BitBlt，CDP 只负责回答"哪块是字、字声明了什么颜色"：
  Q1 透过率：同一扇窗不动，只换背后的场 ⇒ 采样亮度跟着场动＝材质真的透进了客户区。
  Q2 玻璃可用面积比：客户区按 48px 分格，黑场/白场亮度差 >=12 的格子占比＝看得见的玻璃有多大。
  Q3 合成后可读性：页面里每条有字元素（CSS 矩形 × devicePixelRatio 映射到物理像素）
     在每种场上取"框内中位色"当底，与它自己声明的字色算 WCAG 对比度，跨场取最差。

对照组（缺一条整轮作废）：
  K1 像素侧变异（正反两向）：在窗口上盖一层"和某条字同色"的不透明整屏 div ⇒ 尺子读到的底
     必须等于那个字色（亮度差 <=12）；撤掉后必须回到基线（差 <=8）。
     只测正向会放过"截到陈旧帧"这一类瞎法，只测"动了没"会放过"动了但动到别处"。
  K2 色侧变异：把同一条字的颜色改成"刚量到的底色"⇒ 声明色==底，估算器必须判 ~1.0。
     它证的是"字色—CSS 矩形—物理像素"三条线接在同一坐标系上，映射一散这里就散。
     判不出来就是尺子失明，后面所有"全绿"都没有意义。
  K3 不透参照：--none（不接材质、glass=0）跑同一套场、同一批文字 ⇒ slope≈0、透区≈0%。
     它要是也能透，就是场的光漏进了测量，整轮作废。参照轮按主题各跑一轮（浅／深各一），
     因为"玻璃不比实心更难读"这条只对拍同一主题才成立。
     注意：参照轮自己"有几条不达 AA"不作废闸门（见 main 里 K3-FAIL 那段注释）。
  K4 落位：dpr×innerWidth 必须对得上宿主自报的客户区宽（差>3px 作废），
     否则文字矩形映射到的是别人的像素。
  K5 层序：每一格采之前都要证明"整块客户区上面没有别人"（cover_ok），顶四回还不过就当场
     作废这一轮——上一轮就是这个闸门抓到"客户区均值正好等于场色"（0.0／255.0）的污染采样。
  K6 已知答案对照（每一轮都自带，替掉原先"参照轮必须 0 条不达 AA"那个误设前提）：
     往页面里注入三个自带不透明底的对照块——黑字压白(#000/#fff，算式 21.0)、黑字压浅灰
     (#000/#ccc，13.1)、浅灰字压白(#999/#fff，2.85)——它们自己不透明，所以背后是什么材质
     都改不了它们的像素。尺子读出来的对比度必须和算式对得上（差 <=1.0），而且判级一致
     （前两条 >=4.5、第三条 <4.5）。它证的是"这条尺子印出来的数字就是真的 WCAG 比"：
     参照轮报 6 条不达 AA 时，到底是估算器坏了还是实心路径本就如此，由 K6 回答，不再靠
     一个已经退役的 audit3 口径。取完立刻撤掉对照块，免得盖住 K1/K2 的变异目标。
  K7 场自检（Q1/Q2 的正对照）：在被测窗右侧、场窗范围内取一块 50×50 环带，跟客户区同一批
     采样。环带均值必须随场变色（极差 >=30）；否则"slope≈0"分不清是"材质不采相邻窗"还是
     "场根本没进像素"，Q1/Q2 一个都不能报。实测环带确实在换（黑/白极差 ~245），而 Mica 与
     Acrylic 的客户区都不动 ⇒ 这是生产壳的真实行为，不是量具瞎了（详见说明第 6 节）。
用法：PYTHONIOENCODING=utf-8 python probe_glass.py
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time

import requests
import websocket

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_mica5 as M5
from probe_mica5 import Field, above, above_field, find_title, lum, slope

u = M5.u
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # 交付目录 fanqie-todo\
OUT = os.path.join(os.environ["LOCALAPPDATA"], "fq-glass-verify")
os.makedirs(OUT, exist_ok=True)
GEXE = os.path.join(ROOT, "native", "FqGlass.exe")
PRODUCT = os.path.join(ROOT, "index.html")
PAGE = "file:///" + PRODUCT.replace("\\", "/")
GTITLE = "FQGLASS"
CELL = 48                    # 分格边长（物理像素）
EXPOSED = 12.0               # 黑白场亮度差到这个数以上＝这一格真的在透
RECT = (1152, 259, 780, 1470)     # 被测窗：520x980 CSS @150%
FIELDS = [("黑", (0, 0, 0)), ("白", (255, 255, 255)), ("红", (255, 0, 0)), ("蓝", (0, 0, 255)),
          ("棋盘", None), ("桌面", None)]
# 六轮 =（不透参照／Mica／Acrylic）×（浅／深）。端口固定，所以像素探针必须串行：
# 场窗 FQFIELD 一个进程只有一面，两个探针并行会互相把对方的场盖掉（见说明§7 台账第 5 条）。
COMBOS = (("--none", "0", 9411, "K3 不透参照·浅", "light"),
          ("--mica", "mica", 9412, "Mica", "light"),
          ("--acrylic", "acrylic", 9413, "Acrylic", "light"),
          ("--none", "0", 9416, "K3 不透参照·深", "dark"),
          ("--mica", "mica", 9414, "Mica-dark", "dark"),
          ("--acrylic", "acrylic", 9415, "Acrylic-dark", "dark"))


def ch8(c):
    c /= 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def rel(rgb):
    return 0.2126 * ch8(rgb[0]) + 0.7152 * ch8(rgb[1]) + 0.0722 * ch8(rgb[2])


def wcr(a, b):
    la, lb = rel(a), rel(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def parse_color(s):
    m = re.findall(r"[\d.]+", s or "")
    if len(m) < 3:
        return None
    return tuple(int(float(x)) for x in m[:3])


OUR_UDF = []          # 本进程起过的 --udf 路径：用来分辨"占端口的这位"是我们自己上一轮没退净的
                      # 浏览器进程，还是别人（用户自己的 app／别的探针）。


def port_open(port, timeout=1.0):
    """裸 TCP connect 探端口。第 19 次证明**不能拿它判"这个端口本轮能不能用"**：
       accept 队列满的半死监听者（上一轮没退净的 WebView2 浏览器进程）在 1 秒里不回 SYN，
       它就"看着是空的"，于是本轮继续用同一个端口，接着连吃三次 120 秒读超时。
       留给它的位置只剩"事后归因"——CDP 失败消息里那句"端口在听／端口连不上"用的就是它。
       判"能不能用"请走 port_free()，那条问的是真正要用它的那件事（HTTP /json）。"""
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False


def port_free(port, timeout=2.0):
    """这个调试端口现在能不能给本轮当 CDP 通道？用真正要用的那条通道问一次：GET /json。
       三种回答：① 连不上＝没人听＝能用；② /json 有回答（哪怕是空列表）＝有主＝不能用；
       ③ 连上了但永不回（ReadTimeout／异常）＝半死监听者＝**也**不能用。
       第 19 次栽的就是②③不分家：只按裸 connect 判，③被读成"空的"，整轮 Acrylic-dark
       三次重试全花在同一个被占死的端口上。判据要量在它要被使用的那件事上。返回 (能用?, 说明)。"""
    try:
        resp = requests.get("http://127.0.0.1:%d/json" % port, timeout=timeout)
        return False, "有主（HTTP %s，target %d 条）" % (resp.status_code, len(resp.json() or []))
    except requests.exceptions.ConnectionError:
        return True, "没人听"
    except Exception as e:
        return False, "半死监听者（%s: %s）" % (type(e).__name__, str(e)[:60])


def mine_verdict(udf):
    """占端口的这位带的 --user-data-dir，是不是本进程自己起过的档案（第 18 次那个"端口在听、
    宿主活着、/json 永远空列表"的现场，先要分清"我们上一轮没退净"还是"别人的浏览器"）。
    抽成纯函数是因为这条判断不该只靠真机现场才能验——离线给它一对已知答案就能跑。"""
    norm = (udf or "").replace("\\", "/").lower()
    return any(p and p.replace("\\", "/").lower() in norm for p in OUR_UDF)


def port_owner(port):
    """谁在听这个端口：PID＋镜像＋它的 --user-data-dir，外加"是不是自己人"的判断。
       这条只读，绝不杀进程——本机按镜像名全杀曾经误杀用户自己的 Edge，所以环境脏到这份上时
       正当出路是换一个干净端口（见 pick_port），不是把疑似占用者清掉。
       psutil 不可用就返回一句说明，不许让诊断把主流程带崩。"""
    try:
        import psutil
    except Exception as e:
        return "psutil 不可用（%s: %s）" % (type(e).__name__, e)
    rows = []
    try:
        conns = psutil.net_connections(kind="tcp")
    except Exception as e:
        return "端口表读不了（%s: %s）" % (type(e).__name__, e)
    try:
        for c in conns:
            if not (c.laddr and c.laddr.port == port and c.status == psutil.CONN_LISTEN):
                continue
            name, udf, who = "?", "", "?"
            try:
                pr = psutil.Process(c.pid)
                name = pr.name()
                cmd = pr.cmdline()
                udf = " ".join([a for a in cmd if "--user-data-dir" in a])[:160]
            except Exception as e:
                name = "?（%s）" % type(e).__name__
            who = "自己人（本进程早先起过、还没退净）" if mine_verdict(udf) else "不是本进程起的"
            rows.append("PID=%s %s udf=%s ｜ %s" % (c.pid, name, udf or "-", who))
    except Exception as e:
        # 诊断这一步绝把自己的异常抛回主流程：CDP 已经接不上了，这里再炸就把现场整条带走。
        return "逐连接查询炸了（%s: %s）" % (type(e).__name__, e)
    return " ／ ".join(rows) if rows else "没有 LISTEN 者"


def wait_port_free(port, budget=25.0):
    """等这个端口真正能用。宿主进程退了不等于它的 WebView2 浏览器进程也退了——后者会再赖几十秒，
       而这几十秒足够让下一轮在同一个端口上烧掉一整条 120 秒预算（第 19 次 Acrylic-dark 三次重试
       全砸在这上面）。等待是有上限的：等不到就交给 pick_port 挪位，不做"无限等＝总会好的"。"""
    t_end = time.time() + budget
    why = "没试过"
    while time.time() < t_end:
        free, why = port_free(port)
        if free:
            return True, why
        time.sleep(1.0)
    return False, why


def pick_port(preferred, reserved=(), max_shift=8):
    """首选端口不能用就往后挪（最多 max_shift 个），谁都不杀，并把挪动记下来。
       reserved＝其它轮次的固定端口：挪过去等于把别人的槽位占了，下一轮就会像第 19 次那样
       在自己该用的端口上撞上"自己人还没退净"。全被占时不静默退回首选当无事发生——
       说明必须非空并点名监听者。返回 (端口, 说明)。"""
    free, why = port_free(preferred)
    if free:
        return preferred, ""
    for p in range(preferred + 1, preferred + 1 + max_shift):
        if p in reserved:
            continue
        if port_free(p)[0]:
            return p, "端口 %d 不能用（%s；监听者：%s），本轮改用 %d" % (
                preferred, why, port_owner(preferred), p)
    return preferred, "端口 %d 起连续 %d 个都不能用（%s），仍按 %d 尝试（监听者：%s）" % (
        preferred, max_shift, why, preferred, port_owner(preferred))


class CDPAttach(RuntimeError):
    """起窗之后接不上调试通道。和"量具判废"（K4/K5/K8 那些）分开：这一类是被测环境没起来，
    重起一轮是正当的；判废那一类是量到了但不可信，重试只会把噪声洗成"看起来对"的数。"""


class CDP:
    def __init__(self, port, urlpart, host=None, proc=None, budget=120.0):
        self._id = 0
        target = None
        seen = []
        err = "没试过"
        n_ok, n_nonempty, n_try = 0, 0, 0
        # 预算按墙钟算，单次 5 秒读超时。两处都不是随手调出来的：
        #   上一版 60 秒／2 秒，第 18 次跑六轮里三轮接不上（K3 一次后重来成功、Acrylic 两次直接判废）。
        #   而 2 秒读超时在负载机上会把"HTTP 根本没回"写成"target 列表是空的"——现场被我说成
        #   "/json 返回=空列表"，那是量具自己的报错，不是浏览器的回答。所以把两种情况分开数。
        #   再上一版把预算写成 range(240) 这种"次数"，可每次失败请求自己要吃掉 5 秒，
        #   名义"120 秒"实际最坏 240×(5+0.5)≈22 分钟；第 18 次的快捷轮就是被这个假预算拖到
        #   外层 600 秒超时（RC=124）。承诺的时间必须用代码真正消耗的那个单位来计。
        t_end = time.time() + budget
        while time.time() < t_end:
            n_try += 1
            js = []
            try:
                resp = requests.get("http://127.0.0.1:%d/json" % port, timeout=5)
                js = resp.json()
                err = "ok（HTTP %s）" % resp.status_code
                n_ok += 1
                if js:
                    n_nonempty += 1
            except Exception as e:
                err = "%s: %s" % (type(e).__name__, e)
            if js:
                seen = ["%s:%s" % (t.get("type"), (t.get("url") or "")[-42:]) for t in js]
            for t in js:
                if t.get("type") == "page" and urlpart in (t.get("url") or ""):
                    target = t
                    break
            if target:
                break
            time.sleep(0.5)
        if not target:
            try:
                s = socket.create_connection(("127.0.0.1", port), timeout=1.5)
                s.close()
                port_state = "端口在听"
            except Exception as e:
                port_state = "端口连不上（%s）" % e
            alive = "宿主进程在" if (proc is not None and proc.poll() is None) else "宿主进程已退出"
            # 三分现场：① HTTP 一次都没回（浏览器进程没在服务这个端口）
            #           ② 回了但永远是空列表（端口属于别的浏览器／页面 target 一直没注册）
            #           ③ 回了、有 target，但没有 urlpart 这一条（页面导航到了别处）
            # 第 18 次卡在②，当时只记了"空列表"就没往下查；这一次把监听者是谁一起打出来，
            # 才能证伪／证实"上一轮没退净的浏览器进程占着固定端口"这个假设（假设还没成立）。
            if n_ok == 0:
                what = "/json 在 %.0f 秒（试了 %d 次）里一次都没成功回过（最后一次请求=%s）" % (
                    budget, n_try, err)
            elif n_nonempty == 0:
                what = "/json 成功回过 %d 次（共试 %d 次）、每次都空列表（没有任何 target 注册）" % (
                    n_ok, n_try)
            else:
                what = "/json 成功回过 %d 次（共试 %d 次）、其中 %d 次非空，最后一次里的 target=%s" % (
                    n_ok, n_try, n_nonempty, seen)
            raise CDPAttach("CDP 里 %.0f 秒找不到页面 target（port %d）｜现场：%s，%s，窗句柄=%s，%s｜监听者=%s"
                            % (budget, port, port_state, alive, host or 0, what, port_owner(port)))
        self.ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=30)

    def call(self, method, **params):
        self._id += 1
        mine = self._id
        self.ws.send(json.dumps({"id": mine, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mine:
                if "error" in msg:
                    raise RuntimeError("%s -> %s" % (method, msg["error"]))
                return msg.get("result", {})

    def ev(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True)
        if r.get("exceptionDetails"):
            raise RuntimeError("页面里执行报错：%s" % str(r["exceptionDetails"])[:200])
        return r.get("result", {}).get("value")


ENUM = r"""
JSON.stringify((function(){
  var out=[];
  document.querySelectorAll("body *").forEach(function(el){
    var r=el.getBoundingClientRect();
    if(r.width<12||r.height<9) return;
    var st=getComputedStyle(el);
    if(st.visibility!=="visible"||st.display==="none"||parseFloat(st.opacity)<0.6) return;
    var t="";
    for(var i=0;i<el.childNodes.length;i++){var n=el.childNodes[i];if(n.nodeType===3)t+=n.textContent;}
    t=t.replace(/^\s+|\s+$/g,"");
    if(!t) return;
    out.push({tag:el.tagName.toLowerCase(),cls:(el.className||"").toString().slice(0,16),
              t:t.slice(0,18),x:r.left,y:r.top,w:r.width,h:r.height,
              c:st.color,f:parseFloat(st.fontSize),fw:parseInt(st.fontWeight)||400});
  });
  return out;
})())
"""


# 页面态指纹：六轮（三材质 × 深浅）必须量同一批文字，否则对账就是拿运行态的条目去比
# 空闲态的参照。第 16 轮就撞在这上面——Acrylic 浅那轮枚举到 32 条、里面有一条「暂停」1.49:1，
# 而 K3 浅／Mica 只有 30 条（空闲态那颗主按钮写的是「开始专注」）：那条 1.49 从来不在参照的
# 样本里，却被"玻璃掀掉了什么"的差集当成玻璃引入的退化。
STATE_JS = r"""
JSON.stringify((function(){
  try{
    var w=document.getElementById('dualWarn');
    return {status:(typeof T==='undefined'?'?':T.status),
            kind:(typeof T==='undefined'?'?':T.kind),
            mode:(typeof S==='undefined'?'?':S.settings.mode),
            timing:(typeof S==='undefined'?'?':S.settings.timing),
            ro:!!(w&&w.classList.contains('on')),
            cur:(typeof activeTask==='function'&&activeTask())?true:false};
  }catch(e){return {err:String(e&&e.message||e)};}
})())
"""

PIN_JS = r"""
JSON.stringify((function(){
  try{
    if(typeof T==='undefined') return {err:'NO-T'};
    var w=document.getElementById('dualWarn');
    if(w&&w.classList.contains('on')){ dualPromote('探针：先回到可写窗口'); }
    if(T.status!=='idle'){ stopAll(); }
    render();
    return {status:T.status, kind:T.kind};
  }catch(e){return {err:String(e&&e.message||e)};}
})())
"""

# 进指纹的六个字段：每一个都会改变"屏幕上写着什么"，所以它们不同就等于两轮量的不是同一批字。
# 刻意不含 #clock 的读数：运行态那位数每帧变，进了键就永远配不上对（Kind/time/mode 才是集合差异的来源）。
STATE_KEYS = ("status", "kind", "mode", "timing", "ro", "cur")


def theme_js(theme):
    """纯函数：拼出"切主题＋当场回读"那一句 JS。放在调用点外面，是因为 shot_desktop 也要用同一句——
    两边各写各的，就会有一边写成了"只切不读"（第 22 次实拍正是这个形状，见 apply_theme 注释）。"""
    if theme not in ("dark", "light"):
        raise ValueError("未知主题 %r（这个量具只认 dark／light）" % (theme,))
    return ("document.documentElement.dataset.theme='%s';"
            "document.documentElement.dataset.theme" % theme)


def apply_theme(cdp, theme):
    """把页面切到指定主题并**当场回读确认**；回读不符就抛错，由调用方按"这一轮不作数"处理。

    为什么抽出来共用：第 22 次实拍的 `Mica-dark`／`Acrylic-dark` 两轮，行上贴着 dark 的标签，
    客户区均值却是浅主题的 170.0／183.8（对照同趟 `Mica` 170.4）——实拍只按 COMBOS 的 theme 字段
    给行命名，页面从来没被切过去。标签与页面不符比少两张 PNG 更坏：那串数字会被当成深主题的证据引用。
    CSS 只在 `html[data-theme="dark"]` 上挂深色令牌，`light` 与"没有这个属性"同效，
    所以浅主题轮次也显式设置并回读，两边都拿到"确实处在这个主题"的证据。
    """
    got = cdp.ev(theme_js(theme))
    print("  主题：置 %s 后回读=%s" % (theme, got), flush=True)
    if got != theme:
        raise RuntimeError("主题没落上（要求 %s，回读 %r）⇒ 这一轮的数字不作数" % (theme, got))
    return got


def state_of(raw):
    """CDP 回文 → dict；解析不了（页面没这两个全局、eval 崩）就返回 None，
    调用方必须当场说"这一轮没有状态指纹"，而不是拿 None 去跟别的 None 配对。"""
    try:
        st = json.loads(raw)
    except Exception:
        return None
    if not isinstance(st, dict) or "status" not in st or st.get("err"):
        return None
    return st


def state_key(st):
    """粗粒度指纹 "idle|focus|normal|count|0|0"：同一主题内只有键完全相同的轮次才允许互比。
    纯函数，离线可证伪；status 缺失一律不给键（None），别让"读不到状态"混进可比集合。"""
    if not st or st.get("status") in (None, "?"):
        return None
    return "|".join(("%d" % (1 if bool(st.get(k)) else 0)) if k in ("ro", "cur")
                    else str(st.get(k, "?")) for k in STATE_KEYS)


def state_comparable(a, b):
    """两轮能否互比：主题相同 **且** 页面态指纹相同且都可读。
    返回 (可比?, 说明)。任何一边没有指纹就判不可比——"没量到状态"不能当成"状态相同"。"""
    if a is None or not a.get("state_key") or b is None or not b.get("state_key"):
        return False, "缺页面态指纹"
    if a.get("theme") != b.get("theme"):
        return False, "主题不同（%s／%s）" % (a.get("theme"), b.get("theme"))
    if a["state_key"] != b["state_key"]:
        return False, "页面态不同（%s／%s）" % (a["state_key"], b["state_key"])
    return True, a["state_key"]


def client_from_status(path):
    txt = open(path, encoding="utf-8").read()
    m = re.search(r"client=(\d+),(\d+) (\d+)x(\d+)", txt)
    if not m:
        raise RuntimeError("宿主没自报客户区：%s" % txt[:160])
    return tuple(int(m.group(i)) for i in (1, 2, 3, 4)), txt.replace("\n", " | ")


def fresh_udf():
    """三种材质必须量同一批文字，所以每轮都从同一个"空档案"起步。

    共用一个 udf 又不清干净的话，第二轮开始就带着第一轮写进去的 localStorage（设置、
    主题、番茄数），字段集合和 K3 那轮不一致，Q3 的"最差对比度"就成了跨状态比最差。
    删不干净（上轮 WebView2 还占着锁）就换带时间戳的目录，并当场说明这轮不等价。
    """
    base = os.path.join(OUT, "profile")
    for _ in range(8):
        if not os.path.exists(base):
            break
        shutil.rmtree(base, ignore_errors=True)
        time.sleep(0.5)
    if os.path.exists(base):
        p = base + "-" + str(int(time.time()))
        print("  WARN 档案 %s 删不净，本轮用 %s（与前几轮存储状态不等价）" % (base, p), flush=True)
        return p
    return base


LIVE = []                       # 起过就要在退出时收掉：中途 raise 把宿主留成孤儿，
                               # 它占着 exe 文件锁，下一轮 csc 直接 CS0016 编不动。
ACTIVE_PORT = [None]            # 最近一次 launch 用的调试端口；teardown 靠它知道"该等谁放开端口"。
PORT_WAIT = 20.0               # 收窗后等端口重新可用的墙钟上限（秒）。等不到就点名，不改判据。


def launch(flag, glass, port, tag, exe=None):
    # exe 可覆盖：单变量实验（比如把 WS_EX_NOREDIRECTIONBITMAP 关掉那一版壳）必须用同一把尺子量，
    # 另写一个探针就等于"两个检测器、两套判据"——那件事这里已经栽过一次。
    exe = exe or GEXE
    status = os.path.join(OUT, "glassq-%s.txt" % tag.replace(" ", ""))
    if os.path.exists(status):
        os.remove(status)
    before = set(find_title(GTITLE))
    ACTIVE_PORT[0] = port      # 记下来给 teardown 用：收窗后要等的就是这个端口的占用者
    udf = fresh_udf()
    OUR_UDF.append(udf)          # 端口占用归因要用：占着调试端口的浏览器进程带着这个 --user-data-dir
    p = subprocess.Popen([exe, flag, "--multi", "--no-taskbar", "--title", GTITLE,
                          "--url", PAGE + "?glass=" + glass,
                          "--rect", str(RECT[0]), str(RECT[1]), str(RECT[2]), str(RECT[3]),
                          "--status", status, "--cdp", str(port),
                          "--udf", udf])
    h = 0
    for _ in range(40):
        time.sleep(0.5)
        hs = [z for z in find_title(GTITLE) if z not in before]
        if hs:
            h = hs[0]
            break
    if not h:
        return 0, p, None, "NO-WINDOW"
    for _ in range(30):
        if os.path.exists(status):
            break
        time.sleep(0.5)
    time.sleep(3.0)                         # 等首屏（字体、光斑、材质入场）落定
    cl, txt = client_from_status(status)
    u.keybd_event(0x12, 0, 0, 0)
    u.keybd_event(0x12, 0, 2, 0)
    u.SetForegroundWindow(wt.HWND(h))
    time.sleep(1.0)
    # 置顶样式要"确认到手"才算数：实测第一轮 above() 之后 ex-style 里 0x8 常常还没落下
    # （窗刚建完那阵子宿主自己也在改 ex-style，把我这次 TOPMOST 覆盖掉了），
    # 于是那格采到的其实是场自己的像素——上一轮"客户区均值 0.0／255.0"正是这个坑的形状。
    LIVE.append((h, p))
    tries = 0
    while not (u.GetWindowLongW(wt.HWND(h), -20) & 0x8) and tries < 12:
        above(h)
        tries += 1
        time.sleep(0.4)
    if not (u.GetWindowLongW(wt.HWND(h), -20) & 0x8):
        return 0, p, None, "TOPMOST-FAIL（顶了 %d 回仍拿不到 WS_EX_TOPMOST）" % tries
    return h, p, cl, "%s | topmost-tried=%d" % (txt, tries)


def grab(x, y, w, h):
    """客户区整块截屏（probe_mica5 的尺子：BitBlt SRCCOPY|CAPTUREBLT，DWM 合成之后）。"""
    return M5.shot(x, y, w, h)


def box_stats(px, cw, x, y, w, h, inset=0.14):
    """返回 (框内中位色, 框内亮度 MAD=中位绝对偏差)。

    中位色当底：文字一般只盖住框内 15~25% 面积，中位数天然落在"底"上；往里缩 14% 是为了
    不把邻行的字、别人的边框算进来。
    为什么要 MAD 而不是 std（标准差）：文字像素本身就是"第二个众数"，std 会被它抬起来，
    于是"平玻璃＋黑字"和"渐变填充"都可能算出大 std——分不开。MAD（对|lum−中位lum|再取中位）
    能容忍到 ~50% 污染：只要底是平的，多数像素挤在中位附近，MAD≈底噪（很小）；纯渐变没有
    聚集点，MAD 大。K2 的"把字染成底 ⇒ 对比度塌到 1.0"要靠 median==每个字像素背后那块底，
    只有 MAD 小的平面上这个前提才成立——所以下面挑变异目标要挑 MAD 最小的那条。"""
    x0, x1 = int(x + w * inset), int(x + w * (1 - inset))
    y0, y1 = int(y + h * inset), int(y + h * (1 - inset))
    if x0 < 0 or y0 < 0 or x1 > cw or y1 > (len(px) // cw):
        return None, None
    acc = []
    for r in range(y0, y1, 2):
        base = r * cw
        for c in range(x0, x1, 2):
            p = px[base + c]
            acc.append((lum(p), p))
    if len(acc) < 12:
        return None, None
    acc.sort()
    med = acc[len(acc) // 2][1]
    lums = sorted(a[0] for a in acc)
    ml = lums[len(lums) // 2]
    devs = sorted(abs(v - ml) for v in lums)
    return med, devs[len(devs) // 2]


def median_pixel(px, cw, x, y, w, h, inset=0.14):
    """只要中位色的薄封装（Q3 逐条对比度用这个；变异段的平面性判定用 box_stats）。"""
    return box_stats(px, cw, x, y, w, h, inset)[0]


def pick_mutation_target(worst):
    """K1/K2/K3 的变异目标：挑"底是平的"（框内 MAD 小）那条，而不是"最差对比度"那条。

    最差那条常常是渐变填充的红钮——渐变面的中位色 ≠ 每个字像素背后那块底，K2 的
    "染成底⇒1.0"前提在渐变上不成立（上一轮因此 1.00/1.71 之间飘）。平底玻璃标签上
    median==字底，K2 才是干净的尺子校准。有平底就在平底里取对比度最低那条，一个都没有
    就退回 MAD 最小那条并让调用方的打印暴露"没抓到平底"。"""
    flat = [w for w in worst if w[3].get("mad", 999) < 6.0]
    return (min(flat, key=lambda w: w[0]) if flat
            else min(worst, key=lambda w: w[3].get("mad", 999)))[3]


def frame_is_black(px, thr=12.0):
    """整帧是不是"没出画面的空帧"：浅主题玻璃客户区顶黑场后亮度均值仍 >=~40（mica 采壁纸、
       acrylic 还有浅色 veil 托底），一旦均值 <thr 基本就是 BitBlt 拿到未合成的空帧。
       返回 (是否空帧, 均值)。"""
    mean = sum(lum(p) for p in px) / max(len(px), 1)
    return mean < thr, mean


# K6 已知答案对照：(名字, 字色, 自带不透明底, 阈值)。三条的算式值 21.00 / 13.07 / 2.85，
# 离 4.5 都有 >=1.6 的余量，不会因采样噪声翻判级；两条达标＋一条不达标是成对判据
# （只放"该通过的"会放过恒高，只放"该失败的"会放过恒低）。
CONTROLS = (("黑压白", (0, 0, 0), (255, 255, 255), 4.5),
            ("黑压浅灰", (0, 0, 0), (204, 204, 204), 4.5),
            ("浅灰压白", (153, 153, 153), (255, 255, 255), 4.5))


def control_gap(fg, declared_bg, sampled_bg):
    """K6 的偏差：|wcr(字色, 采到的底) − wcr(字色, 声明的底)|。
    对照块自带不透明底 ⇒ 真实像素就该等于声明值；采到的中位色一旦不是它（层序脏、
    截到陈旧帧、矩形映射偏了），这里就张开。纯函数，离线可证伪。"""
    return abs(wcr(fg, sampled_bg) - wcr(fg, declared_bg))


K6_JS = r"""
JSON.stringify((function(){
  var cs=[["黑压白","#000000","#ffffff"],["黑压浅灰","#000000","#cccccc"],["浅灰压白","#999999","#ffffff"]];
  var old=document.getElementById("fqk6"); if(old) old.remove();
  var w=document.createElement("div"); w.id="fqk6";
  w.style.cssText="position:fixed;left:20px;top:20px;z-index:2147483000;pointer-events:none;margin:0;padding:0";
  for(var i=0;i<cs.length;i++){var d=document.createElement("div");
    d.style.cssText="width:240px;height:44px;line-height:44px;font:20px/44px sans-serif;"
      +"background:"+cs[i][2]+";color:"+cs[i][1]+";padding-left:6px;white-space:nowrap";
    d.textContent=cs[i][0]; w.appendChild(d);}
  document.body.appendChild(w);
  var out=[]; for(var j=0;j<w.children.length;j++){var q=w.children[j].getBoundingClientRect();
    out.push({x:q.left,y:q.top,w:q.width,h:q.height});}
  return out;
})())
"""


def ruler_dead(r):
    """这一轮的尺子是否失明 ⇒ 返回失效原因列表（空＝这一轮的数可以采信）。
    四条变异对照各管一段坐标系，缺一条都不能算量具可信；K7 只管 Q1/Q2 那两行，
    所以它不在这里判废整轮（客户区像素照样能答 Q3），由调用方单独降级那两行。
    注意这里**不看**"不达 AA 的条数"：那是被测页面的属性，不是尺子的属性。"""
    why = []
    if r.get("k1") is None or r["k1"] > 12:
        why.append("K1 像素侧没抓到（盖上整屏层读不到那个色）")
    if r.get("k3") is None or r["k3"] > 8:
        why.append("K3 撤掉覆盖层后回不到基线（可能一直截同一张陈旧帧）")
    if r.get("k2") is None or r["k2"] >= 1.6:
        why.append("K2 色侧没塌到 ~1.0（字色—矩形—像素三条线没接上）")
    if r.get("k6") is None or r["k6"] > 1.0:
        why.append("K6 已知答案对照偏了（印出来的数不是真的 WCAG 比）")
    if r.get("k6v"):
        why.append("K6 判级和算式不一致（%s）" % r["k6v"])
    return why


def grid_lum(px, cw, chh):
    out = {}
    for gy in range(0, chh - CELL, CELL):
        for gx in range(0, cw - CELL, CELL):
            acc = []
            for r in range(gy, gy + CELL, 4):
                base = r * cw
                for c in range(gx, gx + CELL, 4):
                    acc.append(lum(px[base + c]))
            if acc:
                out[(gx // CELL, gy // CELL)] = sum(acc) / len(acc)
    return out


def blocked_by(anchor, rect):
    """锚点窗之上（z 序比它高的那些窗）有没有窗压住 rect。
    文字散布在整个窗面，只证中心格会被"角落压着一块"这种局部污染坑到；同一套遍历也用来
    证明 K7 那块环带上面没别人——环带读的是场，被别人的窗占了就等于对照本身是假的。"""
    band = M5.zband()
    if int(anchor) not in band:
        return False, [("不在置顶档（不可见或没置顶）", hex(int(anchor)))]
    x0, y0, w, hh = rect
    out = []
    for x in band[:band.index(int(anchor))]:
        l, t, r_, b_ = M5.win_rect(x)
        if r_ - l <= 0 or b_ - t <= 0:
            continue                       # 零尺寸系统窗压不住任何东西
        if r_ < x0 or l > x0 + w or b_ < y0 or t > y0 + hh:
            continue
        out.append((M5.win_cls(x), M5.win_title(x), hex(x), (l, t, r_, b_)))
    return (not out), out


def cover_ok(h, rect):
    """K5：整块客户区（不是 probe_mica5 那个 120 中心格）上面有没有别人。"""
    return blocked_by(h, rect)


_FLD = None


def fld():
    """场窗必须全进程只建一次。

    probe_mica5.Field 的 wndproc 是绑在"第一个注册 FqFieldWin4 类的那个对象"上的：
    同一进程里再 new 一个 Field，RegisterClassExW 会撞已存在的类名，新建的窗口的绘制
    仍然跑在旧对象的 _paint 上 —— 那么 mode2/mode3 里 field.set_field() 改的是新对象的
    rgb，画出来的却是旧对象的 rgb，三种材质量的其实是同一个场，而且没有任何报错。
    """
    global _FLD
    if _FLD is None:
        _FLD = Field((RECT[0] - 170, RECT[1] - 170, RECT[2] + 340, RECT[3] + 340))
        _FLD.start()
        if not _FLD.ready.wait(10):
            raise RuntimeError("场窗没建起来")
        time.sleep(0.8)
    return _FLD


def sweep_mode(flag, glass, port, tag, theme="light", exe=None):
    print("\n=== %s（%s，URL glass=%s，theme=%s） ===" % (tag, flag, glass, theme), flush=True)
    # 端口固定是"六轮串行"的前提，不是神圣契约：占着它的可能是我们自己没退净的浏览器进程。
    # 这里的口径订正过一次，记下来免得又拿假设当证据：
    #   第 19 次我把它写成"档案 profile-<时间戳>＝自己人还没退净"，那是**推出来的**，不是量到的；
    #   第 20 次（2026-10-09 夜）三个端口 9411×3＋9412×3＋9413×1 全是同一形状——起手六个端口逐个
    #   验过"没人听"、跑前 psutil 全表 18 个 msedgewebview2 全属 PC Manager／小米 ContinuityApp／
    #   CBS（机龄 ~8.5 天），**盘上没有我们任何残留**；于是占着 9411 的那位只能是本轮刚起的那个
    #   浏览器进程：它绑上了端口（"端口在听"）、宿主自报 webview2=ok 且 URL 已导航，
    #   但 /json 在 120 秒（试了 22 次）里一次都不回（ReadTimeout）。
    #   ⇒ 已证实的是"本轮自己的浏览器绑了端口却不应答 DevTools HTTP"；**未证实**的是它为什么不应答。
    #   同一次诊断起窗还额外撞上 TOPMOST-FAIL（顶 12 回拿不到 0x8），两条症状同一个未查明上游的可能性
    #   没排除，但那是猜测，不许写进判据。
    # 所以这一段的处置照旧：先等它退净（有上限），等不到就换干净端口，绝不靠杀进程解决——
    # 本机按镜像名全杀曾经误杀用户自己的 Edge。
    reserved = set(c[2] for c in COMBOS) - {port}
    ready, why = wait_port_free(port)
    if not ready:
        print("  WAIT %s（%s）" % (port, why), flush=True)
    port, note = pick_port(port, reserved=reserved)
    if note:
        print("  PORT %s" % note, flush=True)
    port_note = note
    h, proc, cl, txt = launch(flag, glass, port, tag, exe=exe)
    if not h:
        print("  起窗失败：%s" % txt, flush=True)
        return None
    cx, cy, cwid, chgt = cl
    print("  宿主自报 %s" % txt[:300], flush=True)
    try:
        cdp = CDP(port, "index.html", host=h, proc=proc)
    except CDPAttach:
        teardown(h, proc)      # 接不上就把这个窗收干净：留着它占 exe 文件锁，下一轮 csc 直接编不动
        raise
    # 采样前冻住所有 CSS 动画/过渡：呼吸光环那颗红钮会让"框内底色中位数"在染色前后漂 ~50，
    # K2 色侧对照因此非确定性（同一轮 setup 时而"抓到 1.00:1"时而"漏了 1.71:1"），
    # 而 K2 是整轮作废闸门——它一飘，本来可信的 Q3 也被连累判废。冻住后底色才是静态可复现的。
    cdp.ev("(function(){try{document.getAnimations().forEach(function(a){a.pause();});}catch(e){}"
           "var s=document.createElement('style');s.id='fq-freeze';"
           "s.textContent='*,*::before,*::after{animation-play-state:paused !important;"
           "transition:none !important;}';document.head.appendChild(s);return 'frozen';})()")
    # 页面态钉死：走 app 自己的通道（stopAll/render/dualPromote），不直写 localStorage、
    # 不注入自定义状态机——直写会被页面自己的 pagehide 覆盖，注入则量的是"我造出来的态"。
    # 放在主题之前：dualPromote 那条路会 renderAll()，将来它若开始碰 theme，先钉后切才不会被回滚。
    pin = json.loads(cdp.ev(PIN_JS) or "{}")
    st = state_of(cdp.ev(STATE_JS))
    sk = state_key(st)
    print("  页面态：钉之前=%s 钉之后=%s 指纹=%s" %
          (pin.get("status", pin.get("err", "?")), (st or {}).get("status", "?"), sk or "读不到"), flush=True)
    if pin.get("err"):
        teardown(h, proc)
        raise RuntimeError("K8-FAIL：状态钉不住（pin=%s），这一轮不知道量的是哪个界面" % pin["err"])
    if sk is None:
        teardown(h, proc)
        raise RuntimeError("K8-FAIL：页面态指纹读不到（%s）⇒ 不许拿它去跟任何一轮互比" % (st,))
    if st["status"] != "idle":
        teardown(h, proc)
        raise RuntimeError("K8-FAIL：钉完仍不是 idle（=%s），六轮必须同一个稳定态" % st["status"])
    # 主题：把 html[data-theme] 显式置成本轮声明的那个（CSS 令牌 --veil-rgb/--veil-a/.amb/深色 --sub
    # 全靠这条属性级联），必须在 ENUM 之前设置，否则量到的是另一个主题的字体色。
    # 具体"切＋当场回读、回读不符就抛"的动作在 apply_theme 里，与实拍共用同一份（那里的注释记了
    # 第 22 次实拍"标签 dark／页面其实还是浅色"的经过）；抛错时先收窗，别让下一轮撞进同一只脏环境。
    try:
        apply_theme(cdp, theme)
    except RuntimeError:
        teardown(h, proc)
        raise
    dpr = float(cdp.ev("window.devicePixelRatio"))
    iw = float(cdp.ev("window.innerWidth"))
    diff = abs(iw * dpr - cwid)
    print("  K4 落位：dpr %.2f innerWidth %.0f ⇒ %.0f vs 客户区 %d（差 %.0f）%s" %
          (dpr, iw, iw * dpr, cwid, diff, "OK" if diff <= 3 else "BAD"), flush=True)
    if diff > 3:
        teardown(h, proc)
        raise RuntimeError("K4-FAIL：文字矩形映射不可信，整轮作废")
    els = [e for e in json.loads(cdp.ev(ENUM)) if e["f"] >= 11 and e["w"] * e["h"] >= 300]
    els.sort(key=lambda e: -(e["w"] * e["h"]))
    els = els[:44]
    print("  取到 %d 条有字元素：%s" % (len(els), " / ".join(e["t"] for e in els[:5])), flush=True)

    fw = fld()
    if not fw.hwnd or not u.IsWindow(wt.HWND(fw.hwnd)):
        teardown(h, proc)
        raise RuntimeError("场窗句柄失效")
    time.sleep(0.5)

    caps, order, ring_all = {}, {}, {}
    # K7 环带：被测窗之外、场窗之内的四块 50×50（四个方向都取，因为第三方窗随时会占住某一侧；
    # 上一轮"不透参照·深 黑场被一个无名窗挡了"就是单点采样被局部遮住 ⇒ 判据没错、采集太脆）。
    RX4 = (("右", cx + cwid + 60, cy + 60), ("左", cx - 110, cy + 60),
           ("下", cx + 60, cy + chgt + 60), ("上", cx + 60, cy - 110))
    for name, rgb in FIELDS:
        kw = {"rgb": rgb} if rgb is not None else ({"checker": True} if name == "棋盘" else {"hide": True})
        ok, blockers = False, []
        for _ in range(4):                     # K5：顶不动就再顶，最多四回
            fw.set_field(**kw)
            above(h)
            time.sleep(0.6)
            above(h)                           # 补顶：首轮实测 ex-style 里 0x8 根本没落上
            time.sleep(0.6)
            ok, blockers = cover_ok(h, (cx, cy, cwid, chgt))
            if ok:
                break
        px, cw = grab(cx, cy, cwid, chgt)
        caps[name] = (px, cw)
        order[name] = ok
        # K7：同一批改场里，顺带证"场自己的像素真的进了屏幕采集"。没有这条正对照，
        # "客户区对场毫无反应"就分不清是"材质不采相邻窗"还是"场根本没画上来"。
        side = {}
        for sname, sx, sy in RX4:
            rok, rbl = blocked_by(fw.hwnd, (sx, sy, 50, 50))
            if rok:
                rp, rc = grab(sx, sy, 50, 50)
                side[sname] = sum(lum(p) for p in rp) / len(rp)
            else:
                side[sname] = "%s" % ((rbl[0][1] or rbl[0][0]) if rbl else "被挡")
        ring_all[name] = side
        print("  场=%-3s 层序 %s 客户区均值 %6.1f 环带 %s 像素 %d" %
              (name, "OK" if ok else "BAD", sum(lum(p) for p in px) / len(px),
               " ".join("%s:%s" % (sn, ("%.1f" % sv) if isinstance(sv, float) else "挡")
                        for sn, sv in side.items()), len(px)), flush=True)
        if not ok:
            ex = u.GetWindowLongW(wt.HWND(h), -20) & 0xFFFFFFFF
            band = M5.zband()
            print("      现场：ex=0x%X topmost=%s vis=%s rect=%s band_len=%d 我在=%s 场idx=%s\n"
                  "      压在采样区上面的窗：%s" %
                  (ex, bool(ex & 8), bool(u.IsWindowVisible(wt.HWND(h))), M5.win_rect(h),
                   len(band), int(h) in band,
                   (band.index(fw.hwnd) if fw.hwnd in band else "不在"), blockers[:3]), flush=True)
            teardown(h, proc)
            raise RuntimeError("K5-FAIL：场=%s 顶了四回仍被压着／仍不在置顶档——"
                               "采到的像素分不清是窗还是场，这一轮一个数都不能信" % name)

    solid = [n for n, rgb in FIELDS if rgb is not None and order[n]]
    xs = [lum(rgb) for n, rgb in FIELDS if n in solid for rgb in [dict(FIELDS)[n]]]
    gl = dict((n, grid_lum(caps[n][0], caps[n][1], chgt)) for n in caps if order[n])
    keys = sorted(gl[solid[0]].keys()) if solid and gl else []
    dl = dict((k, gl["白"][k] - gl["黑"][k]) for k in keys) if "白" in gl and "黑" in gl else {}
    exposed = [k for k in keys if dl.get(k, 0) >= EXPOSED]
    sealed = [k for k in keys if k in dl and abs(dl[k]) < 4.0]

    def mean_slope(ks):
        if len(solid) < 3 or not ks:
            return float("nan")
        ys = [sum(gl[n][k] for k in ks) / len(ks) for n in solid]
        return slope(xs, ys)

    print("  Q1 透过率：全窗 slope %+0.3f | 透区 slope %+0.3f | 不透区 slope %+0.3f" %
          (mean_slope(keys), mean_slope(exposed), mean_slope(sealed)), flush=True)
    print("  Q2 玻璃可用面积比 %.1f%%（%d/%d 格，判据 黑白场差>=%.0f）｜不透区 %.1f%%" %
          (100.0 * len(exposed) / max(len(keys), 1), len(exposed), len(keys), EXPOSED,
           100.0 * len(sealed) / max(len(keys), 1)), flush=True)

    # K7 判定：只有"同一侧、黑和白都采干净"的那一条序列才作数——跨侧比等于换了被测几何，
    # 缺任一个锚点就分不清"场没进采集"和"这一侧被别人的窗占了"。四个侧都不可用才算瞎。
    ring_side, ring, ring_spread, ring_ok = pick_ring_side(ring_all, [s[0] for s in RX4])
    print("  K7 场自检：可用侧 %s ｜ 采用 %s：%s ｜ 极差 %s（判据 同侧黑、白锚点齐＋极差>=30）%s" %
          ("、".join("%s=%.1f" % (sn, sp) for sp, sn in ring_ok) or "无（四侧都被挡或缺锚点）",
           ring_side or "—",
           " ".join("%s=%s" % (n, ("%.1f" % v) if v is not None else "被挡")
                    for n, v in ring.items()) if ring else "-",
           "%.1f" % ring_spread if ring_spread is not None else "采不到",
           " OK" if not field_blind(dict(ring=ring, ring_spread=ring_spread)) else " 不作数"),
          flush=True)

    worst = []
    for e in els:
        rgb = parse_color(e["c"])
        if rgb is None:
            continue
        rs = {}
        for n in caps:
            if not order[n]:
                continue
            px, cw = caps[n]
            bg = median_pixel(px, cw, e["x"] * dpr, e["y"] * dpr, e["w"] * dpr, e["h"] * dpr)
            if bg:
                rs[n] = wcr(rgb, bg)
        if len(rs) < 3:
            continue
        n_bad = min(rs, key=lambda k: rs[k])
        # 这块底"平不平"：取最差那一场的框内亮度 MAD，存进元素里，供 K1/K2 挑目标用。
        _, mad_bad = box_stats(caps[n_bad][0], caps[n_bad][1],
                               e["x"] * dpr, e["y"] * dpr, e["w"] * dpr, e["h"] * dpr)
        e["mad"] = mad_bad if mad_bad is not None else 999.0
        large = e["f"] >= 24 or (e["f"] >= 18.66 and e["fw"] >= 700)
        worst.append((rs[n_bad], 3.0 if large else 4.5, n_bad, e, rs))
    if not worst:
        teardown(h, proc)
        raise RuntimeError("一条文字都没量到 ⇒ 估算器没接到活，本轮作废")
    worst.sort(key=lambda w: w[0])            # 只按对比度排：元组里带着 dict，默认比较会撞
    fails = [w for w in worst if w[0] < w[1]]
    print("  Q3 合成后对比度：测 %d 条，最差 %.2f:1（%s[%s] %.1fpx，场=%s，阈 %.1f），不达 AA %d 条" %
          (len(worst), worst[0][0], worst[0][3]["tag"], worst[0][3]["t"], worst[0][3]["f"],
           worst[0][2], worst[0][1], len(fails)), flush=True)
    for r, thr, n, e, rs in fails[:12]:
        print("      FAIL %-7s[%-10s] %5.1fpx 场=%-3s 实测 %.2f < %.2f ｜ %s" %
              (e["tag"], e["t"], e["f"], n, r, thr,
               " ".join("%s%.0f" % (k, v) for k, v in sorted(rs.items()))), flush=True)

    # K1＋K2＋K3 变异目标＝底最平的那条（见 pick_mutation_target），不是最差对比度那条。
    tgt = pick_mutation_target(worst)
    print("  变异目标：%s[%s] 底 MAD %.1f（有平底=%s，正好是最差那条=%s）" %
          (tgt["tag"], tgt["t"], tgt.get("mad", -1),
           any(w[3].get("mad", 999) < 6.0 for w in worst), tgt is worst[0][3]), flush=True)

    def grab_clean(why):
        """变异段每一采都要先证层序，再证"这一帧真的画到了"。

        层序：这里一旦混进场的像素，K1/K2 就变成"测到了场"的假绿灯。
        空帧：顶黑场后，浅主题玻璃的客户区亮度均值不可能低于 ~12（mica 不采场、采的是壁纸，
        acrylic 背后是黑场但浅色 veil 仍托出亮底）；一旦均值≈0 就是 BitBlt 拿到没合成的空帧，
        不是材质把底压黑。上一轮 Acrylic 的 K1 基线读 0.0 正是这个形状——空帧当"基线"喂给
        K2/K3，底色读成 0，整段对照跟着飘。空帧就等 DWM 出帧后重采，重采仍黑就当场判废。"""
        last = "没采到"
        for _ in range(4):
            fw.set_field(rgb=(0, 0, 0))
            above(h)
            time.sleep(0.5)
            ok, bl = cover_ok(h, (cx, cy, cwid, chgt))
            if not ok:
                continue
            px, cw = grab(cx, cy, cwid, chgt)
            black, mean = frame_is_black(px)
            if black:
                last = "客户区均值 %.1f（空帧，没出画面）" % mean
                time.sleep(0.8)
                continue
            return px, cw
        raise RuntimeError("K5/CAPTURE-FAIL（变异段 %s）：顶不到干净层序或一直采到空帧（%s）"
                           "⇒ 这几张像素一张都不能用" % (why, last))

    px0, cw0 = grab_clean("基线")
    bg0 = median_pixel(px0, cw0, tgt["x"] * dpr, tgt["y"] * dpr, tgt["w"] * dpr, tgt["h"] * dpr)
    fg = parse_color(tgt["c"])
    k2 = None
    if bg0 and fg:
        cdp.ev("""(function(){var t=document.querySelectorAll("body *"),el=null;
            for(var i=0;i<t.length;i++){var r=t[i].getBoundingClientRect();
              if(Math.abs(r.left-%.1f)<1.5&&Math.abs(r.top-%.1f)<1.5&&t[i].childNodes.length){el=t[i];break;}}
            if(!el) return "NO-TARGET"; el.id=el.id||"k2mut"; el.dataset.k2="1";
            el.style.color="rgb(%d,%d,%d)"; return el.id;})()""" %
               (tgt["x"], tgt["y"], bg0[0], bg0[1], bg0[2]))
        time.sleep(0.7)
        p1, c1 = grab_clean("染色后")
        b1 = median_pixel(p1, c1, tgt["x"] * dpr, tgt["y"] * dpr, tgt["w"] * dpr, tgt["h"] * dpr)
        # 色侧：把字染成"刚量到的底"⇒ 声明色==底，估算器必须判 ~1.0。
        # 它证的是"字色—矩形—像素"三条线接在同一条坐标系上（映射错了这里就散）。
        k2 = wcr(bg0, b1) if b1 else float("nan")
        drift = abs(lum(b1) - lum(bg0)) if b1 else float("nan")
        cdp.ev('var e=document.querySelector("[data-k2]");if(e){e.style.color="";'
               'e.removeAttribute("data-k2");}')
        print("  K2 色侧变异：%s[%s] 染成自己的底 rgb(%d,%d,%d) ⇒ 估算器 %.2f:1，底漂移 %.1f %s" %
              (tgt["tag"], tgt["t"], bg0[0], bg0[1], bg0[2], k2, drift,
               "抓到" if k2 < 1.6 else "漏了（尺子不可信）"), flush=True)
    k1 = k3 = None
    if fg:
        cdp.ev("""(function(){var d=document.createElement("div");
            d.id="k1overlay";d.style.cssText="position:fixed;inset:0;z-index:99999;pointer-events:none;"
            +"background:rgb(%d,%d,%d)";document.body.appendChild(d);return "OK";})()""" % fg)
        time.sleep(0.7)
        p2, c2 = grab_clean("覆盖层在")
        b2 = median_pixel(p2, c2, tgt["x"] * dpr, tgt["y"] * dpr, tgt["w"] * dpr, tgt["h"] * dpr)
        # 像素侧正向：整屏盖成字色 ⇒ 尺子读到的底必须就是那个字色（差<=12 才算"读的是屏幕"）。
        k1 = abs(lum(b2) - lum(fg)) if b2 else float("nan")
        cdp.ev('var d=document.getElementById("k1overlay");if(d)d.remove();')
        time.sleep(0.7)
        p3, c3 = grab_clean("撤掉之后")
        b3 = median_pixel(p3, c3, tgt["x"] * dpr, tgt["y"] * dpr, tgt["w"] * dpr, tgt["h"] * dpr)
        # 像素侧反向：撤掉后要能回到基线（差<=8）。只测正向会放过"截到的是陈旧帧"这一类瞎法。
        k3 = abs(lum(b3) - lum(bg0)) if b3 else float("nan")
        print("  K1 像素侧变异：盖 rgb(%d,%d,%d) 整屏层 ⇒ 底 %.1f（应为 %.1f，差 %s）；"
              "撤掉后回落到 %.1f（基线 %.1f，差 %s）%s" %
              (fg[0], fg[1], fg[2], lum(b2 or (0, 0, 0)), lum(fg),
               "%.1f" % k1 if k1 == k1 else "n/a",
               lum(b3 or (0, 0, 0)), lum(bg0 or (0, 0, 0)),
               "%.1f" % k3 if k3 == k3 else "n/a",
               "抓到" if (k1 is not None and k1 <= 12 and k3 is not None and k3 <= 8)
               else "漏了（尺子不可信）"), flush=True)

    # K6 已知答案对照：放在变异段之后，页面已复原，对照块也不会盖住 K1/K2 的变异目标。
    # 三个块自带不透明底 ⇒ 背后是什么材质都改不了它们的像素，于是"尺子印出来的数＝真的
    # WCAG 比"有了一条与页面无关的地面真相可对照（原来那条"参照轮必须 0 条不达 AA"靠的是
    # 已退役的 audit3 口径，前提没了，见 main 里的注释）。
    k6 = None
    k6v = ""
    rects = json.loads(cdp.ev(K6_JS))
    time.sleep(0.8)
    pk, ck = grab_clean("K6 对照")
    gaps, lines = [], []
    for (nm, fg0, bg0c, thr), rc in zip(CONTROLS, rects):
        sb = median_pixel(pk, ck, rc["x"] * dpr, rc["y"] * dpr, rc["w"] * dpr, rc["h"] * dpr)
        if sb is None:
            lines.append("%s 采不到" % nm)
            continue
        want, got = wcr(fg0, bg0c), wcr(fg0, sb)
        gaps.append(control_gap(fg0, bg0c, sb))
        bad = "" if (got >= thr) == (want >= thr) else "判级翻转"
        if bad:
            k6v = (k6v + " " if k6v else "") + "%s %s（算式 %.2f／实测 %.2f，阈 %.1f）" % (nm, bad, want, got, thr)
        lines.append("%s 算式 %.2f 实测 %.2f 差 %.2f%s" %
                     (nm, want, got, abs(got - want), "｜" + bad if bad else ""))
    cdp.ev('var e=document.getElementById("fqk6");if(e)e.remove();')
    k6 = max(gaps) if len(gaps) == len(CONTROLS) else None
    print("  K6 已知答案对照：%s ⇒ %s" %
          (" ｜ ".join(lines),
           "尺子可信" if (k6 is not None and k6 <= 1.0 and not k6v) else "尺子不可信（本轮作废）"),
          flush=True)

    by = dict((w[3]["tag"] + "[" + w[3]["t"] + "]", (w[0], w[1])) for w in worst)
    teardown(h, proc)
    return dict(tag=tag, theme=theme, state=st, state_key=sk,
                port=port, port_note=port_note,
                tgt="%s[%s]" % (tgt["tag"], tgt["t"]), tgt_mad=tgt.get("mad", -1),
                els=len(els), measured=len(worst), fails=len(fails), by=by,
                worst=worst[0][0], worst_desc="%s[%s]" % (worst[0][3]["tag"], worst[0][3]["t"]),
                exposed=100.0 * len(exposed) / max(len(keys), 1),
                slope_all=mean_slope(keys), slope_sealed=mean_slope(sealed),
                order_ok=sum(1 for v in order.values() if v), k1=k1, k2=k2, k3=k3, k6=k6, k6v=k6v,
                ring=ring, ring_spread=ring_spread, ring_side=ring_side, ring_all=ring_all,
                cell_mean=dict((n, sum(lum(p) for p in caps[n][0]) / len(caps[n][0])) for n in caps))


def teardown(h, proc, field=None):
    if field:
        field.stop()
    try:
        u.PostMessageW(wt.HWND(h), 0x0010, 0, 0)
    except Exception:
        pass
    for _ in range(12):
        time.sleep(0.4)
        if not find_title(GTITLE):
            break
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=10)        # "发过 terminate"不等于"宿主真退了"；没退要当场说，
    except Exception:                # 否则下一轮撞上的脏环境会被记成本轮的错
        print("  TEARDOWN 宿主 10 秒没退出（pid=%s）" % getattr(proc, "pid", "?"), flush=True)
    time.sleep(0.6)
    # 宿主退出 ≠ 它的 WebView2 浏览器进程退出。第 19 次就是后者赖着不走、把固定端口的 /json
    # 挂成"连得上但永不回"，下一轮三次重试全烧在同一个端口上。这里等它把端口放开（有上限），
    # 等不到就点名，让日志留下"到底谁占着"的证据——绝不主动杀任何进程。
    if ACTIVE_PORT[0]:
        ok, why = wait_port_free(ACTIVE_PORT[0], budget=PORT_WAIT)
        if not ok:
            print("  PORT-NOT-FREE %d：窗收掉后端口仍不可用（%s）｜监听者=%s"
                  % (ACTIVE_PORT[0], why, port_owner(ACTIVE_PORT[0])), flush=True)


def pick_ring_side(ring_all, sides):
    """K7 的采集裁决：从多侧环带里挑"同一侧＋黑、白两个锚点都采干净"的那条序列，取极差最大的。
    绝不跨侧混值——白场的右侧和黑场的左侧比出来的"极差"是换了被测几何的假数。
    一侧要能用必须同时满足：黑有值、白有值、干净值 >=2。返回
    (选中的侧, {场名: 均值或 None}, 极差, [(极差, 侧名), …全部可用侧])；一条都不可用 ⇒ (None, {}, None, [])。
    为什么多侧：第三方窗随时会占住某一侧（上一轮"不透参照·深"的黑场就是被一个无名窗挡在右侧），
    那是采集脆，不是场没变——判据本身（同侧黑白极差）一行没动。"""
    def series(sn):
        s = {}
        for nm, side in ring_all.items():
            v = side.get(sn)
            s[nm] = v if isinstance(v, float) else None
        return s
    cands = []
    for sn in sides:
        s = series(sn)
        clean = [v for v in s.values() if v is not None]
        if s.get("黑") is not None and s.get("白") is not None and len(clean) >= 2:
            cands.append((max(clean) - min(clean), sn, s))
    cands.sort(key=lambda z: -z[0])
    if not cands:
        return None, {}, None, []
    return cands[0][1], cands[0][2], cands[0][0], [(sp, sn) for sp, sn, _ in cands]


def field_blind(r):
    """K7：这一轮的"场"有没有真的进屏幕采集 ⇒ True＝没进（或被挡／采不到）。
    判据要黑白两个锚点都在场，只看极差不行：红/蓝两场的极差也能 >=30，但那说明不了
    "黑→白"这个 Q2 用来分格的轴向有被采集到。极差 >=30 才认为在变。"""
    sp = r.get("ring_spread")
    ring = r.get("ring") or {}
    return not (sp is not None and sp >= 30.0 and
                ring.get("黑") is not None and ring.get("白") is not None)


def ledger_rows(res):
    """每轮只和**同主题且同页面态**的不透参照配对。
    主题不同＝量纲不同（亮底和暗底比对比度没有意义）；页面态不同＝样本集合不同
    （运行态多出「暂停」、空闲态写着「开始专注」），差集会凭空造出"玻璃掀掉了这条"。
    参照行自己配 None；配不上就返回 (r, None, 原因)，调用方必须当场把原因说出来。"""
    rows = []
    for r in res:
        if r["tag"].startswith("K3"):
            rows.append((r, None, None))
            continue
        same_theme = [x for x in res if x["tag"].startswith("K3") and x is not r
                      and x.get("theme") == r.get("theme")]
        if not same_theme:
            rows.append((r, None, "这个主题没有不透参照"))
            continue
        match = None
        for x in same_theme:
            if state_comparable(x, r)[0]:
                match = x
                break
        rows.append((r, match,
                     None if match else
                     "页面态与参照不同（参照=%s／本轮=%s）" %
                     (same_theme[0].get("state_key"), r.get("state_key"))))
    return rows


def legibility(ref, r):
    """同一主题下，玻璃相对实心路径的可读性增减对账（只呈报，不判废）。
    实心参照（--none）量的是同一批文字压在自己那面实心墙上的真实读数，所以它给出的
    "不达 AA 名单"是产品本来就有的底线；玻璃轮和它一比，就能把"玻璃掀掉了哪几条"
    和"这条本来就暗"分开——这正是原来那条误设前提的闸门想守的不变式。
    前提：两轮同主题＋同页面态（由 ledger_rows/state_comparable 把关）。这里再挡一次，
    因为对账一旦被拿运行态去比空闲态，produced 的"玻璃掀掉 X 条"是编出来的。"""
    ok, why = state_comparable(ref, r)
    if not ok:
        raise RuntimeError("legibility 配对不合法：%s ⇒ 不许对账" % why)
    base, cur = ref["by"], r["by"]
    bad = lambda d: set(k for k, (v, t) in d.items() if v < t)
    ref_bad, cur_bad = bad(base), bad(cur)
    shared = set(cur) & set(base)
    drops = sorted(((cur[k][0] - base[k][0], k) for k in shared), key=lambda z: z[0])[:3]
    return (cur_bad & ref_bad, cur_bad - ref_bad, ref_bad - cur_bad,
            sorted(cur_bad - ref_bad), sorted(ref_bad - cur_bad), drops)


def missing_rounds(combos, res):
    """请求过的轮次里没跑出数的哪些 ⇒ 调用方必须点名。
    纯函数，因为"SUMMARY 少一行"这件事不能只靠肉眼读日志：少了 Acrylic-dark 那一行如果被
    读成"Acrylic-dark 没问题"，比一个红色的失败更坏。"""
    got = set(r["tag"] for r in res)
    return [c[3] for c in combos if c[3] not in got]


def parse_only(argv):
    """把命令行里的 `--only=A,B` 拆成 ["A","B"]；没给就是空列表＝全跑。
       单独写成纯函数是因为第 21 次补轮第一下就栽在这：整串 "A,B" 当一个名字传给
       select_combos，未知名字那条闸门当场炸（炸得对），但补轮意图是这条拆分歧义丢的。
       逗号、空格、重复项都在这里收干净，不许留到 select_combos 里再猜。"""
    tags = []
    for a in argv:
        if a.startswith("--only="):
            tags += [t.strip() for t in a.split("=", 1)[1].split(",")]
    out = []
    for t in tags:
        if t and t not in out:
            out.append(t)
    return out


def select_combos(combos, only, universe=None):
    """`--only=轮次名,轮次名`＝只补跑其中几轮（第 20 次里两轮的槽位空着，就补那两槽）。
       写成纯函数、而且每条边界都当场炸，是因为这条路的失败形状全是"看起来跑完了"：
       ① 名字写错（多个空格、错一个字）如果静默当成"这一轮不跑"，整趟会跑出一个空台账，
          读的人会把"今天没有这一行"误读成"这一行没问题"；
       ② 它只准从固定那张表里挑，不许现场造新轮次——新轮次没有固定端口，六轮串行的前提就没了；
       ③ only 为空＝全跑（默认行为不许被这个开关动到）。"""
    universe = COMBOS if universe is None else universe
    tags = [t.strip() for t in (only or []) if t.strip()]
    if not tags:
        return list(combos)
    known = [c[3] for c in universe]
    unknown = [t for t in tags if t not in known]
    if unknown:
        raise ValueError("--only 里有不存在的轮次名：%s ⇒ 不许静默跳过（可选：%s）"
                         % ("、".join(unknown), "、".join(known)))
    sel = [c for c in combos if c[3] in tags]
    if not sel:
        raise ValueError("--only 的名字都认识但一行没挑中（combos=%d 行，tags=%s）"
                         % (len(combos), tags))
    return sel


def main():
    for t in (GTITLE, "FQFIELD"):
        for h in find_title(t):
            u.PostMessageW(wt.HWND(h), 0x0010, 0, 0)
            print("PRECLOSE 残留", t, hex(h), flush=True)
    time.sleep(1.0)
    # 起手先确认六个调试端口都真的能用（第 19 次的教训：窗口收掉了，它的 WebView2 浏览器进程
    # 还在端口上，本轮三次重试全烧在那儿）。等不到不判废——端口只是通道，pick_port 会挪位，
    # 这里只负责把"谁还占着"当场记进日志。
    for _p in sorted(set(c[2] for c in COMBOS)):
        ok, why = wait_port_free(_p, budget=PORT_WAIT)
        if not ok:
            print("PRECLOSE 端口 %d 不可用（%s）｜监听者=%s" % (_p, why, port_owner(_p)), flush=True)
    res = []
    aborts = []      # 量具判废的轮次（K4/K5/K8/主题回读）：不重试，但也绝不带走别轮的数
    try:
        combos = select_combos(COMBOS, parse_only(sys.argv))
        if "quick" in sys.argv:              # 先跑一轮把量具自身跑通，别等三分钟才炸
            combos = combos[:1]
        if len(combos) != len(COMBOS):
            print("PARTIAL RUN：这一趟只跑 %d／%d 轮：%s ⇒ SUMMARY 只对这些行作数，"
                  "其余轮次要另找出处，不许把「这趟没跑」读成「那行没问题」"
                  % (len(combos), len(COMBOS), "、".join(c[3] for c in combos)), flush=True)
        for flag, glass, port, tag, theme in combos:
            r = None            # 每轮开头清空：上一轮的记录不许在这轮三次都没起窗时混进 SUMMARY
            # 只重试"环境没起来"这一类（起窗失败／调试通道接不上）；量具判废（K4/K5/K8）
            # 绝不重试——重跑十次里蒙一次绿的，就是把噪声洗成结论。
            # 次数给到 3：第 18 次跑六轮里三轮卡在 CDP 接不上，其中 Acrylic 一次的重试额度
            # 用完后整轮判废（六轮变三轮）。这仍是"环境没起来"那一类，不是把噪声洗成结论。
            for attempt in (1, 2, 3):
                try:
                    r = sweep_mode(flag, glass, port, tag, theme=theme)
                    if r is None and attempt < 3:
                        print("  RETRY %s（第 %d 次）：起窗没成功，整轮重起一次" % (tag, attempt),
                              flush=True)
                        time.sleep(2.0)
                        continue
                except CDPAttach as e:
                    if attempt < 3:
                        print("  RETRY %s（第 %d 次）：%s" % (tag, attempt, e), flush=True)
                        time.sleep(2.0)
                        continue
                    # 第 19 次就是在这行 raise 掉的：Acrylic-dark 三次接不上，异常穿过整个循环，
                    # 后面五行已经量到的数一起没了（SUMMARY 一行没印，RC=1）。
                    # "这一轮环境没起来"要让后面的轮次继续跑＋缺行点名（missing_rounds），
                    # 而不是把整趟作废——缺行被点名是可诊断的，整趟没了是失忆。
                    print("  ENV-FAIL %s：三次都接不上调试通道，这一轮没有数（会在缺行名单里点名）：%s"
                          % (tag, e), flush=True)
                    r = None
                except RuntimeError as e:
                    # 量具判废（K4 落位／K5 层序／K8 页面态／主题回读）：一次都不重试——
                    # 重跑十次里蒙一次绿，就是把噪声洗成"看起来对"的数。
                    # 但"这一轮不可信"从来不等于"整趟作废"：第 19 次之后只把 CDPAttach 那一类接住了，
                    # 判废这一类仍然会穿过整个循环，把后面几轮已经量到的数一起带走，连缺行都点不出来。
                    # 这里把它也收成逐轮记录：本轮不进 SUMMARY，下一轮照跑，原因逐条留在 ABORTS。
                    print("  INSTRUMENT-ABORT %s：%s ⇒ 这一轮不进 SUMMARY；后面的轮次照跑，"
                          "判废原因逐条列在 ABORTS" % (tag, e), flush=True)
                    aborts.append((tag, str(e)[:220]))
                    r = None
                    break
                break
            if r:
                res.append(r)
    finally:
        for (hz, pz) in LIVE:
            try:
                u.PostMessageW(wt.HWND(hz), 0x0010, 0, 0)
                time.sleep(0.4)
                pz.terminate()
            except Exception:
                pass
        if _FLD is not None:
            _FLD.stop()
            time.sleep(0.5)
    if "quick" in sys.argv:
        print("QUICK DONE", flush=True)
        return
    miss = missing_rounds(combos, res)
    if miss:
        print("\nROUND-MISSING %s ⇒ SUMMARY 里这几行没有数（起窗三次都没成功，或被判废中途退出）。"
              "涉及它们的配对一律按\"没有可比参照\"处理，不拿别的轮次顶替，也不许把\"少一行\"读成\"那行没问题\""
              % miss, flush=True)
    if aborts:
        print("ABORTS（量具判废的轮次，逐条留原因；这些行和它们的 ENV-FAIL 兄弟一样，"
              "缺的是行不是整趟）：%s" %
              "; ".join("%s：%s" % (t, why) for t, why in aborts), flush=True)
    # ↓↓↓ 三条"尺子本身可信吗"的闸门（ruler_dead／K7 环带／不透参照）刻意排在 SUMMARY 之后。
    # 原来它们排在前面，于是一轮判废 = sys.exit(3) = 后面 reconciliation＋SUMMARY 全部没打印：
    # 已经量到的数被一个坏轮次拖下水，和第 19 次"三轮接不上通道带走整趟"是同一个形状的失效半径。
    # 现在先让数落地（带各自的行名），再由闸门宣布"哪些数不可信、整轮作废"，退出码照旧非零。
    # 三条闸门本体在 SUMMARY 之后（dead／blind／refs 那三段），这里只留位置说明。
    # —— 这里原来是一条"不透参照必须 0 条不达 AA，否则玻璃两轮作废"的硬闸门，本轮撤掉，
    #    理由全部记在这儿，免得后人以为是我嫌它红才拆的：
    # ① 它的前提已经没了：当初对齐的是 audit3 在实心路径上报的"0 条不达 AA"，而 audit3
    #    已退役，实心路径的回归换成了 page_regress（它不测对比度）⇒ 没有对照物可对齐。
    # ② 前提本身也不成立：实心路径本就带着按设计保留的『开始专注』白字压红（实测 2.30）
    #    和几条本来就暗的次要标签（本轮浅色参照实测 6 条）。那是产品事实，不是尺子坏了；
    #    把它当"估算器失灵"的信号，代价是把 K1/K2/K3/K6 全绿的玻璃轮一起判废。
    # ③ 尺子可信与否现在由每轮自带的变异对照判（K1 像素侧正反两向、K2 色侧、K6 三个已知
    #    答案对照块——它们的底不透明，背后是什么材质都改不了自己的像素）。条数只呈报，
    #    并在下面跟"同主题、同页面态的实心参照"对账：那才是这条闸门真正想守的不变式。
    print("\n可读性对账（只与同主题、同页面态的不透参照比；条数是产品属性，不作废判据）")
    states = sorted(set((r["state_key"] or "读不到") for r in res))
    if len(states) > 1:
        print("  K8-STATE 六轮页面态不统一：%s ⇒ 不同态的轮次一律不互比" %
              "、".join("%s=%s" % (r["tag"], r["state_key"] or "?") for r in res), flush=True)
    for r, ref, why in ledger_rows(res):
        if r["tag"].startswith("K3"):
            ref_bad = sorted(set(k for k, (v, t) in r["by"].items() if v < t))
            print("  %-14s 态=%s 不达 AA %d/%d，最差 %.2f（%s）：%s" %
                  (r["tag"], r["state_key"], r["fails"], r["measured"], r["worst"], r["worst_desc"],
                   "、".join(ref_bad[:8]) + ("…" if len(ref_bad) > 8 else "")), flush=True)
            continue
        if not ref:
            print("  %-14s 态=%s 没有可比参照（%s），只报条数 %d/%d（最差 %.2f）" %
                  (r["tag"], r["state_key"], why, r["fails"], r["measured"], r["worst"]), flush=True)
            continue
        both, newg, newr, nk, nr, drops = legibility(ref, r)
        print("  %-14s 态=%s 不达 AA %d/%d ｜ 与实心同为暗项 %d ｜ 玻璃掀掉 %d%s ｜ 实心暗而玻璃反而好 %d%s" %
              (r["tag"], r["state_key"], r["fails"], r["measured"], len(both), len(newg),
               ("：" + "、".join(nk)) if nk else "", len(newr),
               ("：" + "、".join(nr)) if nr else ""), flush=True)
        print("      同元素最差降幅：%s" %
              ("、".join("%s %.2f→%.2f(%+0.2f)" % (k, ref["by"][k][0], r["by"][k][0], d)
                        for d, k in drops)), flush=True)
    print("\nSUMMARY")
    for r in res:
        print("  %-14s 态=%-22s 层序 %d/6 透区 %5.1f%% 全窗 slope %+0.3f 不透区 slope %+0.3f 环带极差 %5.1f "
              "最差 %.2f:1（%s）不达 AA %d/%d ｜ 变异底 %s MAD%.1f K1%s K2%s K3%s K6%s ｜ 黑场 %5.1f 白场 %5.1f" %
              (r["tag"], r["state_key"] or "读不到", r["order_ok"], r["exposed"], r["slope_all"], r["slope_sealed"],
               r["ring_spread"] if r["ring_spread"] is not None else -1,
               r["worst"], r["worst_desc"], r["fails"], r["measured"],
               r.get("tgt", "?"), r.get("tgt_mad", -1),
               "%.0f" % r["k1"] if r["k1"] == r["k1"] and r["k1"] is not None else "n/a",
               "%.2f" % r["k2"] if r["k2"] == r["k2"] and r["k2"] is not None else "n/a",
               "%.0f" % r["k3"] if r["k3"] == r["k3"] and r["k3"] is not None else "n/a",
               "%.2f" % r["k6"] if r["k6"] == r["k6"] and r["k6"] is not None else "n/a",
               r["cell_mean"].get("黑", 0), r["cell_mean"].get("白", 0)), flush=True)
        if r.get("port_note"):
            print("      端口挪位：%s" % r["port_note"], flush=True)
    # —— 三条"尺子自己可信吗"的闸门：排在数落地之后（见上面 ROUND-MISSING 处那段位置说明）。
    partial = len(combos) != len(COMBOS)
    dead = [(r["tag"], ruler_dead(r)) for r in res if ruler_dead(r)]
    if dead:
        print("\nK1/K2/K3/K6-FAIL：%s ⇒ 这把尺子看不见变异或已知答案对不上，"
              "它报的每一个数都不可信，本轮作废" %
              "; ".join("%s：%s" % (t, "、".join(w)) for t, w in dead), flush=True)
        sys.exit(3)
    blind = [r["tag"] for r in res if field_blind(r)]
    if blind:
        print("\nK7-FAIL %s：四侧环带（右／左／下／上）没有任何一条能凑出「同一侧上黑＋白都干净」"
              "的序列 ⇒ 分不清是「材质不采相邻窗」还是「场没进采集」，Q1/Q2 这两行一个都不能报"
              "（每轮的 K7 行里有各侧被谁挡的现场）" % blind, flush=True)
        sys.exit(3)
    refs = dict((r["theme"], r) for r in res if r["tag"].startswith("K3"))
    if not refs:
        # 补轮（PARTIAL RUN）里"这趟没带参照"是设计允许的：那是调用方故意只挑了几行。
        # 但必须把"斜率类数字这趟没有意义"说在当场——否则同一份 SUMMARY 会被下一个人
        # 读成"六行都跟参照比过了"。（整趟跑却缺参照仍然是判废，那才是真出事。）
        if partial:
            print("\nK3-ABSENT 这一趟是补轮，没跑不透参照 ⇒ slope／透区 这类「跟场比」的数本轮不作结论，"
                  "只有 Q3（逐条合成后对比度）与页面态那几列可以引用", flush=True)
        else:
            print("\nK3-FAIL 不透参照没跑成，后面所有 slope 都没有意义", flush=True)
            sys.exit(3)
    for theme, ref in sorted(refs.items()):
        if ref["slope_all"] > 0.05 or ref["exposed"] > 3.0:
            print("K3-FAIL 不透参照（%s）也能透（slope %+0.3f／透区 %.1f%%）⇒ 场的光漏进了测量，"
                  "整轮作废" % (theme, ref["slope_all"], ref["exposed"]), flush=True)
            sys.exit(3)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
