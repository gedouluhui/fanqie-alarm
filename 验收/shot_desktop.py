# -*- coding: utf-8 -*-
"""真桌面实拍：把"合成之后的最终长相"存成 PNG，作为像素链的地面真相。

为什么要有这个文件（不是给 runbook 配插图，是补一条量具缺口）：
  probe_glass 量的是被测窗客户区那一块 BitBlt 出来的数字，背景全程是"我起的纯黑/纯白场窗"。
  它答不了另一个问题：用户桌面上真有壁纸、有别的窗、有任务栏时，这块玻璃看起来是什么？
  上一版这里用 PIL 的 ImageGrab，但本机 ImageGrab 出的是空图（黑帧），而空图照样能存成 PNG、
  照样能被 runbook 引用——那是"证据看起来在，其实没测"。所以这里：
    采集只走 probe_mica5.shot 那一条 BitBlt 路径（全机唯一实现，不养第二个采集器），
    并且把"这张图真的不是空的"做成闸门，判据跑在**重开 PNG 之后**的字节上。

四条闸门：
  A 非空：整屏（1/8 面积盒式降采样后）亮度均值 ≥10 且 8×8 灰阶不同色 ≥12；
          单窗裁图同样再过一遍——纯色一块的裁图就是空帧。
  B 对齐：从整屏缓冲按绝对坐标裁出被测窗客户区，其均值要和"直接对该客户区 BitBlt"差 ≤6.0
          ⇒ 抓坐标映射／DPI／横带拼接错位（本机 150% 缩放过一次）。
  C 页面态与主题：能接 CDP 就冻 CSS 动画＋按 app 自己通道钉到 idle（与 probe_glass 同一份 PIN_JS），
          并且**当场把 html[data-theme] 切到这一行声明的主题再回读确认**（同一份 apply_theme）——
          第 22 次实拍缺的就是这半条：两行贴着 dark 的标签、页面其实还是浅色，客户区均值 170.0/183.8
          其实是浅主题的数。接不上 CDP 或主题落不上 ⇒ 该行标 FAIL，只当"看起来是这样"，不进对账。
  D 存盘完整：重开的 PNG 尺寸必须等于宣称尺寸（写一半也算 FAIL）。

已知答案对照（离线可跑，锁屏也能证量具没瞎）：见 selftest_probe_instr.py 的 H 组——
  整条纯黑帧必须被 A 判空、渐变"壁纸"必须过 A；把横带错位一行去裁，B 那条比对必须报超差；
  越界裁图必须炸，不许静默裁半张冒充整张；主题回读不符必须让 C 判红（apply_theme 跑在桩上，不是读文本）。
用法：
  PYTHONIOENCODING=utf-8 python 验收\\shot_desktop.py          # 六轮实拍（必须串行，独占端口与场窗）
  PYTHONIOENCODING=utf-8 python 验收\\shot_desktop.py --bare   # 只拍不带 app 窗的桌面（A 的对照轮）
  PYTHONIOENCODING=utf-8 python 验收\\shot_desktop.py --only=Mica,Acrylic-dark   # 补拍某几行（名字与 probe_glass 同一套）
"""
import datetime as dt
import hashlib
import inspect
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_mica5 as M5
import probe_glass as G
from PIL import Image

u = M5.u
OUT = G.OUT
STAMP = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
MANIFEST = os.path.join(OUT, "shots-%s.md" % STAMP)

STRIP = 160                     # 每次 BitBlt 的横带高度（物理像素）；4K 全宽一条约 0.6M 元组
BLANK_MEAN = 10.0               # 均值低于这个数＝根本没出帧（本机 ImageGrab 的老毛病就是全 0）
BLANK_UNIQ = 12                 # 8×8 灰阶下不同色数低于这个数＝同一块纯色
ALIGN_TOL = 6.0                 # 整屏裁出来的客户区 vs 直接截客户区，允许差
PAD = 120                       # 单窗裁图四周留的桌面边（要看得见"玻璃外面是什么"）
DS = 8                          # 整屏统计的降采样倍率（4K 全量转元组表要 ~600MB，会 OOM 成"没数"）

# 必须与 probe_glass.sweep_mode 里那段是同一份字符串：H6 当场比对源码字节，改一处忘另一处就报红。
FREEZE_JS = ("(function(){try{document.getAnimations().forEach(function(a){a.pause();});}catch(e){}"
             "var s=document.createElement('style');s.id='fq-freeze';"
             "s.textContent='*,*::before,*::after{animation-play-state:paused !important;"
             "transition:none !important;}';document.head.appendChild(s);return 'frozen';})()")


# ---------------- 纯函数（离线可判，H 组就判这几条） ----------------
def px_of(im):
    raw = im.tobytes()
    return [(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 3)], im.width


def stats_of(px):
    """(均值, MAD, 8x8 灰阶下不同色数)。MAD＝对|L−中位L|再取中位，跟框内判据同一口径。"""
    L = [M5.lum(p) for p in px]
    n = len(L)
    if not n:
        return 0.0, 0.0, 0
    mean = sum(L) / n
    s = sorted(L)
    med = s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])
    mad = sorted(abs(v - med) for v in L)[n // 2]
    uniq = len(set((p[0] // 8, p[1] // 8, p[2] // 8) for p in px))
    return mean, mad, uniq


def strip_crop(px, cw, sy, x0, y0, x1, y1):
    """从一条横带（绝对行号从 sy 起、每行 cw 个像素）里裁出绝对矩形 [x0,x1)×[y0,y1)。
       跨带自动只取相交行；列越界直接炸（宁可炸，不许裁半张冒充整张）。"""
    rows = len(px) // cw
    r0, r1 = max(y0, sy), min(y1, sy + rows)
    if x0 < 0 or x1 > cw or x1 <= x0:
        raise RuntimeError("列越界：要求 [%d,%d) 而带宽只有 %d" % (x0, x1, cw))
    out = []
    for r in range(r0, r1):
        base = (r - sy) * cw
        out.extend(px[base + x0: base + x1])
    return out


def fit(vx, vy, vw, vh, x, y, w, h):
    """把矩形钳到虚拟屏内，返回 (x0,y0,x1,y1)。钳过＝True（调用方要知道面积被削了）。"""
    x0, y0 = max(x, vx), max(y, vy)
    x1, y1 = min(x + w, vx + vw), min(y + h, vy + vh)
    if x1 <= x0 or y1 <= y0:
        raise RuntimeError("矩形 (%d,%d %dx%d) 与虚拟屏 (%d,%d %dx%d) 不相交" % (x, y, w, h, vx, vy, vw, vh))
    return x0, y0, x1, y1, (x0 != x or y0 != y or x1 != x + w or y1 != y + h)


def inside(vx, vy, vw, vh, x, y, w, h):
    return x >= vx and y >= vy and x + w <= vx + vw and y + h <= vy + vh


def blank_verdict(mean, uniq, label):
    if mean < BLANK_MEAN or uniq < BLANK_UNIQ:
        return False, "%s：均值 %.1f／色数 %d 低于空帧阈值（%s／%s）⇒ 采集器没出帧" % (
            label, mean, uniq, BLANK_MEAN, BLANK_UNIQ)
    return True, "%s：非空" % label


def align_verdict(delta, clipped):
    if clipped:
        return False, "客户区被屏幕边缘钳过 ⇒ 两条路径量的面积不一样，这个差不作数"
    if delta > ALIGN_TOL:
        return False, "两条采集路径差 %.2f（>%.1f）⇒ 坐标映射/DPI/横带拼接有一路是错的" % (delta, ALIGN_TOL)
    return True, "对齐（差 %.2f）" % delta


def size_verdict(claimed, actual, nbytes):
    if claimed != actual:
        return False, "重开得 %s，宣称 %s ⇒ PNG 没写全" % (actual, claimed)
    if nbytes <= 0:
        return False, "文件 0 字节"
    return True, "存盘完整"


# ---------------- 采集（只有 probe_mica5.shot 一条实现） ----------------
def virtual_screen():
    """整块虚拟屏：SM 76/77 是原点、78/79 是尺寸（7/8 是对话框边框宽——历史事故，见说明§7）。"""
    x, y = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
    w, h = u.GetSystemMetrics(78), u.GetSystemMetrics(79)
    if w <= 0 or h <= 0:
        raise RuntimeError("虚拟屏尺寸读到 %dx%d ⇒ 现在多半是锁屏/显示器没点亮，别硬拍" % (w, h))
    return x, y, w, h


def grab_desktop(vx, vy, vw, vh, crop=None, tries=4):
    """逐横带 BitBlt 整屏拼成 RGB 字节缓冲；crop=(x0,y0,x1,y1) 绝对坐标时顺手裁出来。
       整块 4K 一次取会造 8.3M 个元组（~600MB）——"跑不动"在上层会被读成"这轮没数"，所以分带。"""
    buf = bytearray(vw * vh * 3)
    sub = []
    for sy in range(vy, vy + vh, STRIP):
        sh = min(STRIP, vy + vh - sy)
        px, cw = M5.shot(vx, sy, vw, sh, tries=tries)
        if cw != vw or len(px) != vw * sh:
            raise RuntimeError("横带 (%d,%d %dx%d) 回来 %d 个像素、宽 %d（应为 %dx%d）⇒ 拼接会错位，整轮作废"
                               % (vx, sy, vw, sh, len(px), cw, vw, sh))
        base = (sy - vy) * vw * 3
        for i, p in enumerate(px):
            o = base + i * 3
            buf[o] = p[0]
            buf[o + 1] = p[1]
            buf[o + 2] = p[2]
        if crop and crop[3] > sy and crop[1] < sy + sh:
            sub.extend(strip_crop(px, cw, sy, *crop))
    return buf, sub


def save(path, buf, vw, vh, crop=None):
    img = Image.frombytes("RGB", (vw, vh), bytes(buf))
    size = img.size
    if crop:
        img = img.crop(crop)
    img.save(path, "PNG")
    return size, os.path.getsize(path), img.size


def open_stats(path, box=None, downsample=1):
    """重开 PNG 取像素（判据跑在落盘字节上，不跑在内存里那份）。
       downsample>1 用 BOX 面积平均降采样——空图降采样还是空图，但省掉 8.3M 元组表。"""
    im = Image.open(path).convert("RGB")
    actual = im.size
    if box:
        im = im.crop(box)
    if downsample > 1:
        im = im.resize((max(1, im.width // downsample), max(1, im.height // downsample)), Image.BOX)
    px, _ = px_of(im)
    return px, actual, im.size


# ---------------- 每一轮 ----------------
def read_state(port, h, proc, theme):
    """C 闸门：冻动画＋钉页面态＋**把页面切到这一行声明的那个主题**（三份动作全部复用 probe_glass
       的那一份：PIN_JS／STATE_JS／apply_theme，不在这里另写一套）。
       接不上 CDP 或主题落不上都不阻断拍照，但这一行会被标成 FAIL ⇒ 不进对账。
       第 22 次实拍就是缺了主题这一半：`Mica-dark`／`Acrylic-dark` 两行贴着 dark 的标签，
       页面从来没被切过去，客户区均值 170.0／183.8 其实还是浅主题的数（同趟浅主题 Mica 量到 170.4）。"""
    try:
        c = G.CDP(port, "index.html", host=h, proc=proc)
    except Exception as e:
        return None, "-", False, "NO-CDP（%s）" % repr(e)[:140]
    try:
        fz = c.ev(FREEZE_JS)
        pin = json.loads(c.ev(G.PIN_JS) or "{}")
        st = G.state_of(c.ev(G.STATE_JS))
        sk = G.state_key(st)
        bg = c.ev("document.body.dataset.bg||'-'")
        why = []
        if fz != "frozen":
            why.append("动画没冻住(%s)" % fz)
        if pin.get("err"):
            why.append("状态钉不住(%s)" % pin["err"])
        if sk is None:
            why.append("缺页面态指纹")
        elif st.get("status") != "idle":
            why.append("钉完不是 idle(%s)" % st.get("status"))
        try:
            G.apply_theme(c, theme)
        except Exception as e:
            why.append("FAIL：主题没落上（要求 %s）：%s" % (theme, repr(e)[:120]))
        return sk, bg or "-", (not why), "；".join(why) or "OK"
    except Exception as e:
        return None, "-", False, "NO-CDP（读状态炸了：%s）" % repr(e)[:140]


def row(tag, theme, note, **kw):
    d = dict(state="-", bg="-", full_mean="-", full_uniq="-", win_mean="-",
             client_crop="-", client_direct="-", delta="-", whyA="-", whyB="-", whyC="-",
             whyD="-", okC=False, note=note)
    d.update(kw)
    return tag, theme, d


def one_round(flag, glass, port, tag, theme, rows):
    print("\n=== 实拍 %s（%s，theme=%s） ===" % (tag, flag, theme), flush=True)
    # 端口占用不杀进程，往后挪一个没人听的（和 probe_glass 同一条口径，见它的 pick_port 注释）。
    port, note = G.pick_port(port)
    if note:
        print("  PORT %s" % note, flush=True)
    h, proc, cl, txt = G.launch(flag, glass, port, tag)
    if not h:
        rows.append(row(tag, theme, "起窗失败：%s%s" % (txt, "｜" + note if note else ""),
                        whyA="FAIL：没窗"))
        return
    try:
        sk, bg, okC, whyC = read_state(port, h, proc, theme)
        print("  页面态=%s ｜ bg=%s ｜ C 闸门=%s ｜ 宿主 %s" % (sk or "-", bg, whyC, txt[:120]), flush=True)
        vx, vy, vw, vh = virtual_screen()
        cx, cy, cw, ch = cl
        x0, y0, x1, y1, _ = fit(vx, vy, vw, vh, cx - PAD, cy - PAD, cw + 2 * PAD, ch + 2 * PAD)
        buf, _ = grab_desktop(vx, vy, vw, vh)
        full = os.path.join(OUT, "desktop-%s-%s.png" % (tag.replace(" ", ""), STAMP))
        win = os.path.join(OUT, "window-%s-%s.png" % (tag.replace(" ", ""), STAMP))
        claimed, nbytes_full, _ = save(full, buf, vw, vh)
        _, nbytes_win, win_size = save(win, buf, vw, vh, crop=(x0 - vx, y0 - vy, x1 - vx, y1 - vy))

        # —— 判据一律跑在重开文件之后的字节上 ——
        fpx, f_actual, _ = open_stats(full, downsample=DS)
        fmean, fmad, funiq = stats_of(fpx)
        okA1, whyA1 = blank_verdict(fmean, funiq, "整屏")
        wpx, w_actual, _ = open_stats(win)
        wmean, wmad, wuniq = stats_of(wpx)
        okA2, whyA2 = blank_verdict(wmean, wuniq, "单窗裁图")
        okD, whyD = size_verdict((vw, vh), f_actual, nbytes_full)

        # B：整屏图里按绝对坐标裁客户区（图内坐标 = 绝对坐标 − 虚拟屏原点）
        clip = not inside(0, 0, f_actual[0], f_actual[1], cx - vx, cy - vy, cw, ch)
        cpx, _, _ = open_stats(full, box=(cx - vx, cy - vy, cx - vx + cw, cy - vy + ch))
        cmean, cmad, cuniq = stats_of(cpx) if cpx else (0.0, 0.0, 0)
        dpx, _ = M5.shot(cx, cy, cw, ch)
        dmean, dmad, duniqu = stats_of(dpx)
        delta = abs(cmean - dmean)
        okB, whyB = align_verdict(delta, clip)

        okA = okA1 and okA2
        rows.append(row(tag, theme, "PNG %s (%d KB) ＋ %s (%d KB, %s)"
                        % (os.path.basename(full), nbytes_full // 1024,
                           os.path.basename(win), nbytes_win // 1024, win_size),
                        png=full, state=sk or "-", bg=bg, okC=okC,
                        full_mean=fmean, full_uniq=funiq,
                        win_mean=wmean, client_crop=cmean, client_direct=dmean, delta=delta,
                        whyA="OK" if okA else "%s／%s" % (whyA1, whyA2),
                        whyB=whyB, whyC=whyC, whyD=whyD))
        print("  A %s ｜ B %s ｜ D %s ｜ 整屏 %.1f 色%d ｜ 客户区 裁%.1f vs 直%.1f"
              % ("PASS" if okA else "FAIL", whyB, whyD, fmean, funiq, cmean, dmean), flush=True)
    except Exception as e:
        rows.append(row(tag, theme, "炸了：%s" % repr(e)[:200], whyA="FAIL：异常"))
        print("  ROUND-FAIL %r" % (e,), flush=True)
    finally:
        G.teardown(h, proc)


def bare_desktop(rows):
    """不带任何 app 窗的桌面：A 的已知答案对照轮。这台机有壁纸，这里要都能拍成空图，
       说明坏的是采集器，而不是"产品没画东西"。"""
    vx, vy, vw, vh = virtual_screen()
    buf, _ = grab_desktop(vx, vy, vw, vh)
    path = os.path.join(OUT, "desktop-bare-%s.png" % STAMP)
    claimed, nbytes, _ = save(path, buf, vw, vh)
    px, actual, _ = open_stats(path, downsample=DS)
    mean, mad, uniq = stats_of(px)
    okA, whyA = blank_verdict(mean, uniq, "空桌面")
    okD, whyD = size_verdict((vw, vh), actual, nbytes)
    rows.append(row("（空桌面·对照）", "-", "PNG %s (%d KB)" % (os.path.basename(path), nbytes // 1024),
                    png=path, full_mean=mean, full_uniq=uniq, control=True,
                    whyA=whyA if not okA else "OK", whyD=whyD, whyC="不适用（没起窗）"))
    print("  空桌面对照：A %s ｜ D %s ｜ 均值 %.1f 色 %d" %
          ("PASS" if okA else "FAIL", whyD, mean, uniq), flush=True)


def write_manifest(rows, note):
    md5 = hashlib.md5(open(os.path.abspath(__file__), "rb").read()).hexdigest()
    gmd5 = hashlib.md5(open(os.path.abspath(inspect.getsourcefile(G)), "rb").read()).hexdigest()
    # 空桌面对照行不是"一轮主张"，它是 A 闸门的已知答案：它没有页面态、也没有 B，
    # 拿同一把尺子量它会把 RC 判成 1（第 22 次实拍正是这样：7 行里 3 行"不作数"，其中一行是对照）。
    bad = [(t, th, d) for t, th, d in rows if not d.get("control")
           and ("FAIL" in (d["whyA"] + d["whyB"] + d["whyC"] + d["whyD"]) or d["state"] == "-"
                or not d.get("okC"))]
    shots = [d["full_mean"] for _, _, d in rows if isinstance(d["full_mean"], float)]
    drift = (max(shots) - min(shots)) if len(shots) > 1 else 0.0
    with io.open(MANIFEST, "w", encoding="utf-8") as f:
        f.write("# 真桌面实拍 · DWM 合成后的地面真相 %s\n\n" % STAMP)
        f.write("采集只走 `probe_mica5.shot`（桌面 DC BitBlt SRCCOPY|CAPTUREBLT，DWM 合成之后）这一条实现；"
                "A/B/D 三条判据跑在**重开 PNG 之后**的字节上，C 是动画冻结＋页面态指纹＋**主题回读**"
                "（三份动作全部复用 probe_glass 的 PIN_JS／STATE_JS／apply_theme，这里不另写一套）。\n\n")
        f.write("出处：`shot_desktop.py` md5=%s，`probe_glass.py` md5=%s。%s\n\n" % (md5, gmd5, note))
        if drift > 15.0:
            f.write("> **桌面不是常量**：这一趟各轮的整屏均值从 %.1f 摆到 %.1f（摆幅 %.1f）。"
                    "跨轮比客户区均值时必须把这一列一起看——材质之外，壁纸／别人插进来的窗也在动。"
                    "同一趟里 `--none` 与玻璃轮的整屏均值差多少，就是这批 PNG 里「环境自己变了」的量级。\n\n"
                    % (min(shots), max(shots), drift))
        f.write("| 轮 | 主题 | 页面态 | bg | 整屏均值 | 整屏色数 | 客户区均值(整屏裁) | 客户区均值(直接截) | 差 | A | B | C | D |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
        for tag, theme, d in rows:
            f.write("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |\n" % (
                tag, theme, d["state"], d["bg"],
                ("%.1f" % d["full_mean"]) if isinstance(d["full_mean"], float) else d["full_mean"],
                d["full_uniq"],
                ("%.1f" % d["client_crop"]) if isinstance(d["client_crop"], float) else d["client_crop"],
                ("%.1f" % d["client_direct"]) if isinstance(d["client_direct"], float) else d["client_direct"],
                ("%.2f" % d["delta"]) if isinstance(d["delta"], float) else d["delta"],
                "PASS" if d["whyA"] == "OK" else d["whyA"], d["whyB"],
                "PASS" if d["okC"] else d["whyC"], d["whyD"]))
        f.write("\n## 存了什么\n\n")
        for tag, theme, d in rows:
            f.write("- **%s**（%s）：%s\n" % (tag, theme, d["note"]))
        if bad:
            f.write("\n## 不作数的行\n\n")
            for tag, theme, d in bad:
                f.write("- %s（%s）：A=%s｜B=%s｜D=%s｜C=%s｜页面态=%s\n"
                        % (tag, theme, d["whyA"], d["whyB"], d["whyD"], d["whyC"], d["state"]))
            f.write("\n以上行**不进对账**：实拍只是「看起来是这样」，不是「量过了」。缺页面态指纹或主题没落上的行"
                    "连「这一行长什么样」都谈不上，更不能用来反驳任何一轮的像素结论。\n")
        else:
            f.write("\n## 判\n\n全部行 A/B/C/D 四绿 ⇒ 这批实拍可作为合成后的地面真相引用。\n")
    return MANIFEST, len(bad)


def main():
    os.makedirs(OUT, exist_ok=True)
    if G.find_title(G.GTITLE) or G.find_title("FQFIELD"):
        print("REFUSE：桌面上还挂着 FQGLASS／FQFIELD 窗 ⇒ 另一个像素脚本在跑"
              "（端口 9411-9416 和场窗都是一个进程一份，并行会互相盖场）。等它跑完再拍。", flush=True)
        return 3
    rows = []
    if "--bare" in sys.argv:
        note = "本轮只跑空桌面对照（--bare），用来判「A 闸门是不是恒绿」。"
        bare_desktop(rows)
    else:
        # 挑轮次这件事全部走 probe_glass 那一份（parse_only 拆命令行＋select_combos 校验名字），
        # 这里不自己 startswith：两个量具各拆一遍，就会出现"实拍认的补轮名字与像素判决不是同一套"。
        combos = G.select_combos(G.COMBOS, G.parse_only(sys.argv))
        partial = len(combos) != len(G.COMBOS)
        note = ("本轮跑满六轮（不透参照／Mica／Acrylic × 浅／深），与 probe_glass 的 COMBOS 同一套。"
                if not partial else
                "PARTIAL RUN：这一趟只拍 %d／%d 行：%s ⇒ 这份清单只对这些行作数，"
                "其余行要另找出处，不许把「这趟没拍」读成「那行没问题」。"
                % (len(combos), len(G.COMBOS), "、".join(c[3] for c in combos)))
        if partial:
            print("PARTIAL RUN：这一趟只拍 %d／%d 行：%s" % (
                len(combos), len(G.COMBOS), "、".join(c[3] for c in combos)), flush=True)
        for flag, glass, port, tag, theme in combos:
            one_round(flag, glass, port, tag, theme, rows)
        bare_desktop(rows)
    path, nbad = write_manifest(rows, note)
    print("\nMANIFEST %s（%d 行，其中不作数 %d）" % (path, len(rows), nbad), flush=True)
    return 0 if nbad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
