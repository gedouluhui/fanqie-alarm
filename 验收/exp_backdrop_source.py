# -*- coding: utf-8 -*-
"""第 37/40 号问题：玻璃客户区那点「随材质变化的亮度」到底从哪来——壁纸还是实心回退？

为什么要单独做这个实验（不是在 probe_glass 里加一条断言）：
  probe_glass 每一轮都是「被测窗背后压一块我起的纯黑／纯白场窗」，它测出来的 slope≈0 只说明
  **相邻窗进不来**，说明不了「客户区那 170.1／183.5／47.6／58.7 是谁给的」。两个候选在第 20/21 次跑里
  给出**完全一样**的数字形状：
    A 背景材质采的是**桌面壁纸**（Mica 按 Windows 语义就是只采壁纸）⇒ 客户区均值应当跟着
      「窗此刻压在壁纸哪一块」走；
    B 材质根本没接上、客户区其实是页面那层半透明 veil 底下的**实心回退色** ⇒ 与屏位无关。
  区分它们只要一件事：**同一个材质，挪到亮壁纸区和暗壁纸区各量一次**，中间不放场窗。
  所以这里刻意不接场窗、不测 slope，只测「屏位 → 客户区均值」这条关系。

三只轮子（缺一只是自说自话）：
  · 负对照 `--none`：自己画不透明底，**必须**对屏位无反应；它动了说明量具另有漏子。
  · 正对照 `--mica`：文档语义＝采壁纸 ⇒ **应当**跟屏位走。
  · 判据对象 `--acrylic`：这一只才是问题本身（生产用的 Acrylic 到底采什么）。
  每轮另带一条「桌面自己在动吗」的复核：从起窗后那张整屏图里读**另一处屏位**的均值，
  与开拍前对照图上的同处比，漂移 >DRIFT_TOL 就当场声明「这一对的差不作数」
  （第 22 次实拍里整屏均值在轮次之间从 70.8 跳到 108.4，这个漂移真实存在，不能靠肉眼忽略）。

复用而非另写：采集只有 `probe_mica5.shot`／`shot_desktop.grab_desktop` 这一条路，
空帧判据用 `shot_desktop.blank_verdict`，两条采集路径互校用 `shot_desktop.align_verdict`，
起窗／收窗／端口退路用 `probe_glass.launch/teardown/pick_port`（**只挪位，绝不杀进程**），
主题这一侧不做实验（页面主题由调用方固定，本量具全程用默认浅主题）。

用法：
  PYTHONIOENCODING=utf-8 python 验收\\exp_backdrop_source.py            # 三材质 × 两个屏位
  PYTHONIOENCODING=utf-8 python 验收\\exp_backdrop_source.py --gap=25   # 亮暗两处的最小亮度差
"""
import datetime as dt
import hashlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_mica5 as M5
import probe_glass as G
import shot_desktop as SD

OUT = G.OUT
STAMP = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
REPORT = os.path.join(OUT, "backdrop-source-%s.md" % STAMP)

WIN_W, WIN_H = 780, 1470        # 与被测窗同尺寸：屏位与尺寸不混成同一个变量
GRID_STEP = 120                 # 候选屏位扫描步长（物理像素）
MIN_DIST = 500                  # 亮暗两处必须拉开，免得采到同一块壁纸纹理
DRIFT_TOL = 8.0                 # 另一处屏位「开拍前后」的均值漂移上限
TRACK_MIN = 8.0                 # 判「跟屏位走」所需的两处客户区差下限
STRIDE_SCAN = 12                # 扫描时的抽样步长
STRIDE_ROUND = 4                # 每轮复算屏位均值时的抽样步长
RING = 40                       # 环带宽度：窗外面那一圈桌面
PORTS = {"--none": 9411, "--mica": 9412, "--acrylic": 9413}

MATERIALS = (("--none", "0", "实心参照（负对照：必须不跟屏位走）"),
             ("--mica", "mica", "Mica（正对照：文档语义＝只采壁纸）"),
             ("--acrylic", "acrylic", "Acrylic（被测：生产用的那只）"))


# ---------------- 纯函数（可离线判） ----------------
def region_mean(buf, vw, x0, y0, x1, y1, stride=STRIDE_SCAN):
    """绝对坐标矩形内按 stride 抽样的亮度均值（不建整张元组表：4K 全量会造 8.3M 个元组）。"""
    n = 0
    tot = 0.0
    for y in range(int(y0), int(y1), stride):
        base = y * vw
        for x in range(int(x0), int(x1), stride):
            o = (base + x) * 3
            tot += M5.lum((buf[o], buf[o + 1], buf[o + 2]))
            n += 1
    if not n:
        raise RuntimeError("抽样区 %dx%d stride=%d 一个点也没取到" % (x1 - x0, y1 - y0, stride))
    return tot / n


def scan_positions(buf, vw, vh, w, h, bottom_clear=90):
    """把整块壁纸扫一遍，返回 [(均值, x, y)]（x/y 为虚拟屏内坐标，已保证整窗在屏内且不压任务栏）。"""
    out = []
    for y in range(0, vh - h - bottom_clear, GRID_STEP):
        for x in range(0, vw - w, GRID_STEP):
            out.append((region_mean(buf, vw, x, y, x + w, y + h), x, y))
    return out


def far_enough(a, b, min_dist):
    return abs(a[1] - b[1]) >= min_dist or abs(a[2] - b[2]) >= min_dist


def pick_pair(pts, min_gap, min_dist):
    """最亮／最暗两处，且互相拉开 min_dist；两处均值差不足 min_gap ⇒ None（不许硬凑屏位）。
    只在前 40 亮 × 前 40 暗里配对：再多就是同一块壁纸的相邻格，拉开距离的意义已经没了。"""
    brights = sorted(pts, reverse=True)[:40]
    darks = sorted(pts)[:40]
    for hc in brights:
        for lc in darks:
            if far_enough(hc, lc, min_dist) and hc[0] - lc[0] >= min_gap:
                return hc, lc
    return None


def verdict_line(flag, bright, dark, label):
    """一只材质的判：Δ客户区 vs Δ屏位。缺轮／桌面漂移超限都必须说成「这一行没有结论」。"""
    if not bright or "client" not in bright or not dark or "client" not in dark:
        return "  %-10s 缺轮（起窗失败／中途炸）⇒ 这一行没有结论，不许用别的材质顶替 ｜ %s" % (flag, label)
    d_client = bright["client"] - dark["client"]
    d_region = bright["pos"][0] - dark["pos"][0]
    drift = max(bright["drift"], dark["drift"])
    if drift > DRIFT_TOL:
        v = "不作数（桌面自己漂了 %.1f > %.1f，两次屏位量不是同一张壁纸）" % (drift, DRIFT_TOL)
    elif abs(d_client) < TRACK_MIN:
        v = "对屏位无反应（Δ客户区 %+0.1f，Δ屏位 %+0.1f）" % (d_client, d_region)
    else:
        v = "跟屏位走（Δ客户区 %+0.1f，Δ屏位 %+0.1f，跟踪比 %.2f）" % (
            d_client, d_region, (d_client / d_region) if d_region else float("nan"))
    return "  %-10s 亮位客户区 %.1f ／ 暗位客户区 %.1f ｜ %s ｜ %s" % (
        flag, bright["client"], dark["client"], v, label)


# ---------------- 每一轮 ----------------
def one_round(flag, glass, tag, pos, other_pos, vx, vy, vw, vh, base_buf):
    """在 pos 处起一次窗：客户区均值（两条采集路径互校）＋环带均值＋另一处屏位的漂移复核。"""
    print("\n=== %s @ (%d,%d) 壁纸均值 %.1f ===" % (tag, pos[1], pos[2], pos[0]), flush=True)
    port, note = G.pick_port(PORTS[flag])
    if note:
        print("  PORT %s" % note, flush=True)
    G.RECT = (vx + pos[1], vy + pos[2], WIN_W, WIN_H)
    h, proc, cl, txt = G.launch(flag, glass, port, tag)
    if not h:
        print("  LAUNCH-FAIL %s%s" % (txt, "｜" + note if note else ""), flush=True)
        return {"tag": tag, "pos": pos, "fail": txt}
    try:
        cx, cy, cw, ch = cl
        buf, _ = SD.grab_desktop(vx, vy, vw, vh)          # 窗已经在上面的那一刻的整屏
        dpx, _ = M5.shot(cx, cy, cw, ch)
        dmean, dmad, duniq = SD.stats_of(dpx)
        sub = []
        for y in range(cy, cy + ch, 2):                   # 第二条路径：从整屏缓冲按同坐标裁（判 B）
            base = (y - vy) * vw
            for x in range(cx, cx + cw, 2):
                o = (base + x) * 3
                sub.append((buf[o], buf[o + 1], buf[o + 2]))
        cmean, cmad, cuniq = SD.stats_of(sub)
        delta = abs(cmean - dmean)
        okA, whyA = SD.blank_verdict(dmean, duniq, "客户区")
        okB, whyB = SD.align_verdict(delta, False)
        ring = (region_mean(buf, vw, cx - RING, cy, cx, cy + ch, STRIDE_ROUND) +
                region_mean(buf, vw, cx + cw, cy, cx + cw + RING, cy + ch, STRIDE_ROUND) +
                region_mean(buf, vw, cx, max(0, cy - RING), cx + cw, cy, STRIDE_ROUND) +
                region_mean(buf, vw, cx, cy + ch, cx + cw, min(vh, cy + ch + RING), STRIDE_ROUND)) / 4.0
        ox0, oy0 = vx + other_pos[1], vy + other_pos[2]
        oreg = region_mean(buf, vw, ox0, oy0, ox0 + WIN_W, oy0 + WIN_H, STRIDE_ROUND)
        oreg0 = region_mean(base_buf, vw, ox0, oy0, ox0 + WIN_W, oy0 + WIN_H, STRIDE_ROUND)
        drift = abs(oreg - oreg0)
        print("  客户区 直%.1f 裁%.1f（差%.2f，%s）｜ 环带 %.1f ｜ 另一处屏位 现在%.1f 开拍前%.1f 漂%.1f ｜ A=%s"
              % (dmean, cmean, delta, whyB, ring, oreg, oreg0, drift, whyA), flush=True)
        print("  宿主 %s" % txt[:140], flush=True)
        return {"tag": tag, "pos": pos, "client": dmean, "crop": cmean, "delta": delta,
                "ring": ring, "other_now": oreg, "other_base": oreg0, "drift": drift,
                "okA": okA, "whyA": whyA, "okB": okB, "whyB": whyB, "host": txt}
    finally:
        G.teardown(h, proc)


def main():
    if G.find_title(G.GTITLE) or G.find_title("FQFIELD"):
        print("REFUSE：桌面上还挂着 FQGLASS／FQFIELD ⇒ 另一个像素脚本在跑（本实验也必须独占端口）。", flush=True)
        return 3
    ready, why = M5.desktop_ready()
    if not ready:
        print("REFUSE：桌面没解锁／显示器没点亮（%s）⇒ 拍到的会是黑帧" % why, flush=True)
        return 3
    min_gap = 20.0
    for a in sys.argv:
        if a.startswith("--gap="):
            min_gap = float(a.split("=", 1)[1])
    vx, vy, vw, vh = SD.virtual_screen()
    print("虚拟屏 %d,%d %dx%d，被测窗 %dx%d，全程不放场窗" % (vx, vy, vw, vh, WIN_W, WIN_H), flush=True)
    base_buf, _ = SD.grab_desktop(vx, vy, vw, vh)
    pts0 = [(base_buf[(y * vw + x) * 3], base_buf[(y * vw + x) * 3 + 1],
             base_buf[(y * vw + x) * 3 + 2]) for y in range(0, vh, 64) for x in range(0, vw, 64)]
    bmean, bmad, buniq = SD.stats_of(pts0)
    okA, whyA = SD.blank_verdict(bmean, buniq, "开拍前整屏")
    print("对照整屏：A %s（%s）｜ MAD %.1f" % ("PASS" if okA else "FAIL", whyA, bmad), flush=True)
    if not okA:
        return 5
    pts = scan_positions(base_buf, vw, vh, WIN_W, WIN_H)
    pair = pick_pair(pts, min_gap, MIN_DIST)
    if not pair:
        print("REFUSE：这张壁纸上找不出亮度差 ≥%.1f 且相距 ≥%d 的两处（最亮 %.1f／最暗 %.1f，共 %d 个候选屏位）"
              "⇒ 本实验在当下壁纸上做不出结论，不许硬凑屏位"
              % (min_gap, MIN_DIST, max(p[0] for p in pts), min(p[0] for p in pts), len(pts)), flush=True)
        return 4
    bright, dark = pair
    print("屏位选定：候选 %d 处；亮位 (%d,%d) 均值 %.1f ／ 暗位 (%d,%d) 均值 %.1f ｜ 差 %.1f"
          % (len(pts), bright[1], bright[2], bright[0], dark[1], dark[2], dark[0],
             bright[0] - dark[0]), flush=True)
    by = {"bright": {}, "dark": {}}
    for key, pos, other in (("bright", bright, dark), ("dark", dark, bright)):
        for flag, glass, label in MATERIALS:
            by[key][flag] = one_round(flag, glass, "%s-%s" % (flag.replace("-", ""), key),
                                      pos, other, vx, vy, vw, vh, base_buf)
    lines = [verdict_line(flag, by["bright"].get(flag), by["dark"].get(flag), label)
             for flag, glass, label in MATERIALS]
    txt = "\n".join(lines)
    print("\n=== 判（实心那只必须「对屏位无反应」，Mica 应当「跟屏位走」，Acrylic 是被问的那只）===\n%s" % txt,
          flush=True)
    with io.open(REPORT, "w", encoding="utf-8") as f:
        f.write("# 屏位→客户区：背景材质的来源是壁纸还是实心回退 · %s\n\n" % STAMP)
        f.write("虚拟屏 %d,%d %dx%d；窗尺寸固定 %dx%d（屏位与尺寸不混成同一个变量）；全程**不放场窗**"
                "（场窗测的是「相邻窗进不进得来」，与本实验问的「壁纸进不进得来」是两条）。\n\n"
                % (vx, vy, vw, vh, WIN_W, WIN_H))
        f.write("出处：`exp_backdrop_source.py` md5=%s\n`probe_glass.py` md5=%s\n`shot_desktop.py` md5=%s\n\n"
                % (hashlib.md5(open(os.path.abspath(__file__), "rb").read()).hexdigest(),
                   hashlib.md5(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                 "probe_glass.py"), "rb").read()).hexdigest(),
                   hashlib.md5(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                 "shot_desktop.py"), "rb").read()).hexdigest()))
        f.write("屏位：%d 个候选里选出 亮 (%d,%d) 壁纸均值 %.1f ／ 暗 (%d,%d) 壁纸均值 %.1f，相距 ≥%d 像素\n\n"
                % (len(pts), bright[1], bright[2], bright[0], dark[1], dark[2], dark[0], MIN_DIST))
        f.write("## 判\n\n```\n%s\n```\n\n" % txt)
        f.write("## 逐轮原始数\n\n")
        for key in ("bright", "dark"):
            for flag, glass, label in MATERIALS:
                r = by[key].get(flag) or {}
                p = r.get("pos") or (0, 0, 0)
                if "client" not in r:
                    f.write("- %s @ (%d,%d)：起窗失败：%s\n" % (flag, p[1], p[2], r.get("fail")))
                    continue
                f.write("- %s @ (%d,%d)：客户区 直%.1f／整屏裁%.1f（差 %.2f，%s）｜环带 %.1f｜"
                        "另一处屏位 现在%.1f 开拍前%.1f 漂 %.1f｜A=%s\n"
                        % (flag, p[1], p[2], r["client"], r["crop"], r["delta"], r["whyB"],
                           r["ring"], r["other_now"], r["other_base"], r["drift"], r["whyA"]))
        f.write("\n## 边界\n\n"
                "- 本实验只回答「客户区那点亮度跟不跟屏位走」，不回答透过率、也不回答可读性"
                "（那两条分别是 probe_glass 的 Q1/Q2 与 Q3，各自有对照）。\n"
                "- 两处屏位是**先后**两次起窗量的，靠「另一处屏位开拍前后漂移 ≤%.1f」复核桌面没自己动；"
                "超限的那一对当场标「不作数」。\n"
                "- 壁纸上若挂着别的窗（本机常驻：托盘置顶窗、播放器桌面歌词），「屏位均值」量的就不是纯壁纸；"
                "环带那一行会把它露出来：环带均值与开拍前的屏位均值差得远，就是有人插进来了。\n"
                "- 跟踪比不是透过率：它只说「客户区亮度对屏位壁纸亮度的敏感度」，"
                "Mica 的系统 tint／暗色模式 tint 都会让这个比值偏离 1，比值 >0 才是本实验要的那件事。\n"
                % DRIFT_TOL)
    print("\nREPORT %s" % REPORT, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
