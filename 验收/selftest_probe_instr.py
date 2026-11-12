# -*- coding: utf-8 -*-
"""Offline self-test of the two NEW instrument decisions in probe_glass.py — no screen needed.

Lock screen blocks composited pixels, but these decisions are pure functions over a px array,
so they can be certified right now:
  * box_stats            — median + MAD (robust spread); flat backdrop+text => small MAD,
                           gradient fill => big MAD (this is what pick_mutation_target relies on).
  * pick_mutation_target — must choose a FLAT (mad<6) element, NOT the worst-contrast one
                           (which is usually the gradient red button that made K2 drift 1.00/1.71).
  * frame_is_black       — must flag only a true no-frame BitBlt (mean<12), and must NOT mislabel a
                           legitimately dark acrylic-over-black backdrop as a capture failure.

Every assertion is written so a plausible bug (constant MAD, wrong sort key, mean-instead-of-median,
threshold pinned green) turns it RED — mutation controls included.
"""
import os, sys, hashlib, inspect
# 兜住 GBK 控制台／重定向：这份报告的判决行里有 ⇒ 与中文，locale 编码下打印它们会让
# 进程恰好崩在"打印结论那一行"上——rc=1 长得像"闸门判红"，其实是量具自己没跑完
# （2026-10-09T18:24Z 实测：`> 文件` 时本文件即如此，接终端却全绿）。判据一行没动。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_glass import box_stats, median_pixel, pick_mutation_target, frame_is_black, wcr
from probe_mica5 import lum

FAILS = []


def check(name, cond, detail=""):
    line = "%-42s %s   %s" % (name, "PASS" if cond else "FAIL", detail)
    print(line)
    if not cond:
        FAILS.append(name)


def mk(cw, chh, fn):
    """build a flat px list; fn(c, r) -> (r, g, b)."""
    px = []
    for r in range(chh):
        for c in range(cw):
            px.append(fn(c, r))
    return px, cw


# ---- synthetic frames -------------------------------------------------------
CW, CHH = 240, 120
BACKDROP = (232, 236, 243)     # light glass veil
INK = (27, 30, 37)             # dark text glyph

def gray(L):
    L = int(max(0, min(255, L)))
    return (L, L, L)

# flat: uniform backdrop, dark glyphs over ~1/6 of pixels (text is a minority => median lands on底)
flat_px, _ = mk(CW, CHH, lambda c, r: INK if (c + r) % 6 == 0 else BACKDROP)
# gradient: vertical gray ramp 60->140 across the measured box rows, plus dense (1/3) dark glyphs
def grad_fn(c, r):
    L = 60 + (r / float(CHH)) * 80.0
    return INK if (c % 3 == 0) else gray(L)
grad_px, _ = mk(CW, CHH, grad_fn)
# the SAME box, but made flat by pinning the ramp to a single value (control: content, not coords)
flat2_px, _ = mk(CW, CHH, lambda c, r: INK if (c % 3 == 0) else gray(100))

BOX = (40, 30, 90, 40)         # CSS-ish rect; helpers apply their own inset

med_flat, mad_flat = box_stats(flat_px, CW, *BOX)
med_grad, mad_grad = box_stats(grad_px, CW, *BOX)
med_flat2, mad_flat2 = box_stats(flat2_px, CW, *BOX)

# ---- A1: MAD separates flat-bottom-with-text from a gradient fill ----------
# The selector's flat cutoff is mad<6; the meaningful claim is "gradient is NOT eligible",
# i.e. it lands on the far side of that same boundary (not an arbitrary hand-tuned 12).
check("A1a flat box MAD is small (<6, eligible flat)", mad_flat is not None and mad_flat < 6.0,
      "MAD=%.2f" % mad_flat)
check("A1b gradient box MAD is beyond the flat cutoff (>=6)", mad_grad is not None and mad_grad >= 6.0,
      "MAD=%.2f" % mad_grad)

# ---- A2: median lands on the backdrop, not on the glyphs -------------------
check("A2 median(flat) ~= backdrop (wcr<=1.05)",
      med_flat is not None and wcr(med_flat, BACKDROP) <= 1.05,
      "med=%s wcr=%.3f" % (med_flat, wcr(med_flat, BACKDROP) if med_flat else -1))

# ---- A3 mutation: pinning the ramp flat MUST collapse MAD (proof it reads content) ----
check("A3 same-rect flat-pinned collapses MAD (<6)", mad_flat2 is not None and mad_flat2 < 6.0,
      "MAD=%.2f (gradient was %.2f)" % (mad_flat2, mad_grad))

# ---- A4 pick_mutation_target chooses FLAT, not worst-contrast (gradient) ----
e_grad = {"tag": "BUTTON", "t": "start", "mad": mad_grad, "x": 40, "y": 30, "w": 90, "h": 40}
e_flat = {"tag": "SPAN", "t": "sec-label", "mad": mad_flat, "x": 40, "y": 30, "w": 90, "h": 40}
e_mid = {"tag": "SPAN", "t": "hint", "mad": 4.0, "x": 0, "y": 0, "w": 90, "h": 40}
# worst list is sorted by contrast ascending; the gradient is the WORST (1.15) but must NOT be the target
worst = [(1.15, 4.5, "white", e_grad, {}), (2.8, 4.5, "white", e_flat, {}),
         (5.0, 4.5, "white", e_mid, {})]
tgt = pick_mutation_target(worst)
check("A4 target is a flat one, not worst[0]", tgt is not e_grad and tgt.get("mad", 999) < 6.0,
      "picked=%s mad=%s" % (tgt["t"], tgt.get("mad")))

# ---- A5 mutation: when NO element is flat, must fall back to least-nonflat (not crash) ----
worst2 = [(9.9, 4.5, "white", {"tag": "T", "t": "x", "mad": 999, "x": 0, "y": 0, "w": 10, "h": 10}, {}),
          (8.8, 4.5, "white", {"tag": "T", "t": "least-bad", "mad": 40.0, "x": 0, "y": 0, "w": 10, "h": 10}, {})]
tb = pick_mutation_target(worst2)
check("A5 no-flat fallback returns least-nonflat (mad<999)", tb["t"] == "least-bad" and tb["mad"] < 999,
      "picked=%s mad=%s" % (tb["t"], tb["mad"]))

# ---- A6 regression: out-of-bounds box => median None (never a bogus pixel) ----
check("A6 out-of-range box => None",
      median_pixel(flat_px, CW, 900, 900, 50, 50) is None)

# ---- A7 frame_is_black: only a true empty frame is caught -------------------
black_frame, _ = mk(CW, CHH, lambda c, r: (0, 0, 0))
light_frame, _ = mk(CW, CHH, lambda c, r: (200, 205, 215))
dark_acrylic, _ = mk(CW, CHH, lambda c, r: (50, 55, 60))       # legit acrylic-over-black: must NOT be "failed"
b1, m1 = frame_is_black(black_frame)
b2, m2 = frame_is_black(light_frame)
b3, m3 = frame_is_black(dark_acrylic)
check("A7a all-black frame flagged", b1 is True, "mean=%.1f" % m1)
check("A7b light frame not flagged", b2 is False, "mean=%.1f" % m2)
check("A7c dark-but-real frame NOT flagged as failure", b3 is False, "mean=%.1f" % m3)
# boundary sanity: pinned-just-under vs just-over the 12 threshold
b_lo, _ = frame_is_black(mk(CW, CHH, lambda c, r: (11, 11, 11))[0])
b_hi, _ = frame_is_black(mk(CW, CHH, lambda c, r: (13, 13, 13))[0])
check("A7d threshold boundary (11->black, 13->ok)", b_lo is True and b_hi is False,
      "11:%s 13:%s" % (b_lo, b_hi))

# ---- B: K6 已知答案对照（control_gap + CONTROLS 的算式地面真相）------------
from probe_glass import (CONTROLS, control_gap, ruler_dead, field_blind, ledger_rows,
                         legibility, wcr as _wcr)

# B1 三条对照的"期望答案"是 WCAG 手算值，不是让 wcr 自己算给自己看（否则 K6 就是自证）。
#   #000/#fff = 21.00；#000/#ccc = 1.05... 手算：rel(204/255)=0.60384 ⇒ (0.65384)/(0.05)=13.077
#   #999/#fff：rel(153/255)=0.31854 ⇒ 1.05/0.36854=2.849
HAND = {"黑压白": 21.00, "黑压浅灰": 13.08, "浅灰压白": 2.85}
want_all = {}
for nm, fg, bg, thr in CONTROLS:
    got = _wcr(fg, bg)
    want_all[nm] = got
    check("B1 %s 算式＝WCAG 手算值(±0.03)" % nm, abs(got - HAND[nm]) <= 0.03,
          "wcr=%.3f 手算=%.2f" % (got, HAND[nm]))
check("B2 三条的判级是 过/过/挂（成对判据，缺一边就放过恒高或恒低）",
      want_all["黑压白"] >= 4.5 and want_all["黑压浅灰"] >= 4.5 and want_all["浅灰压白"] < 4.5,
      " / ".join("%s=%.2f" % (k, v) for k, v in sorted(want_all.items())))
# B3 离阈值够远：采样噪声/抗锯齿翻不动判级（否则 K6 会自己造误报）
check("B3 离 4.5 的最小余量 >=1.5（不会因噪声翻判级）",
      min(abs(v - 4.5) for v in want_all.values()) >= 1.5,
      "min margin=%.2f" % min(abs(v - 4.5) for v in want_all.values()))

# B4 采样对得上 ⇒ gap 0；采到别的像素 ⇒ gap 必须张开过闸（1.0）
for nm, fg, bg, thr in CONTROLS:
    check("B4 %s 采到==声明 ⇒ gap 0" % nm, control_gap(fg, bg, bg) < 0.01,
          "gap=%.4f" % control_gap(fg, bg, bg))
wrong = control_gap((0, 0, 0), (255, 255, 255), (0, 0, 0))          # 声明白底、采到黑
stale = control_gap((153, 153, 153), (255, 255, 255), (18, 26, 40))  # 采到深色玻璃/陈旧帧
near = control_gap((0, 0, 0), (255, 255, 255), (250, 250, 251))      # 噪声级偏差
check("B5a 底采错（白说成黑）gap 张开过闸(>1.0)", wrong > 1.0, "gap=%.2f" % wrong)
check("B5b 底采成深色 gap 张开过闸(>1.0)", stale > 1.0, "gap=%.2f" % stale)
check("B5c 噪声级偏差仍在闸内(<=1.0)", near <= 1.0, "gap=%.4f" % near)

# ---- C: ruler_dead ＝尺子死活判定（含本轮撤掉的那条误设前提的回归用例）------
HEALTHY = dict(tag="Mica", theme="light", k1=0.0, k2=1.00, k3=0.0, k6=0.02, k6v="",
               fails=6, measured=30, ring={"黑": 5.0, "白": 250.0}, ring_spread=245.0,
               by={"A": (2.3, 4.5)})
check("C1 变异全绿 ⇒ 尺子可信（原因列表为空）", ruler_dead(HEALTHY) == [],
      "why=%s" % ruler_dead(HEALTHY))
MUT = [("k1 盖层读不到", dict(k1=13.0)), ("k1 缺失", dict(k1=None)),
       ("k3 回不到基线", dict(k3=9.0)), ("k3 缺失", dict(k3=None)),
       ("k2 没塌到 1.0", dict(k2=1.71)), ("k2 缺失", dict(k2=None)),
       ("k6 对不上算式", dict(k6=1.4)), ("k6 没测到", dict(k6=None)),
       ("k6 判级翻转", dict(k6v="浅灰压白 判级翻转"))]
for label, patch in MUT:
    bad = dict(HEALTHY)
    bad.update(patch)
    check("C2 变异抓到：%s" % label, len(ruler_dead(bad)) >= 1,
          "why=%s" % ruler_dead(bad))
# C3 本轮真正的修复：参照轮"有几条不达 AA"不再让尺子判废（旧闸门就是这么飘的）
old_gate_round = dict(HEALTHY)
old_gate_round.update(fails=6, measured=6, tag="K3 不透参照·浅",
                      by=dict(("%s" % i, (2.3 + i * 0.1, 4.5)) for i in range(6)))
check("C3 参照轮 6 条不达 AA ⇒ 尺子仍判可信（旧误判回归）",
      ruler_dead(old_gate_round) == [], "why=%s" % ruler_dead(old_gate_round))
check("C4 ruler_dead 不看 fails（产品属性不是尺子属性）",
      '"fails"' not in inspect.getsource(ruler_dead) and "['fails']" not in inspect.getsource(ruler_dead),
      "判定体内不引用 r[\"fails\"]")

# ---- D: K7 场自检 + 主题配对（跨主题比对比度是历史坑，必须当场配错就红）----
check("D1 环带黑/白都在且极差>=30 ⇒ 场没瞎", field_blind(HEALTHY) is False, "")
eq_ring = dict(HEALTHY, ring={"黑": 120.0, "白": 120.0}, ring_spread=0.0)
check("D2 环带不随场变色 ⇒ 判瞎", field_blind(eq_ring) is True, "")
no_anchor = dict(HEALTHY, ring={"黑": None, "白": None, "红": 76.0, "蓝": 30.0}, ring_spread=46.0)
check("D3 极差够但黑白锚点被挡 ⇒ 仍判瞎（不能只信极差）", field_blind(no_anchor) is True, "")
thin = dict(HEALTHY, ring={"黑": 5.0, "白": 20.0}, ring_spread=15.0)
check("D4 极差 15（<30）⇒ 判瞎", field_blind(thin) is True, "")

SK_I = "idle|focus|normal|count|0|0"
rows = [dict(tag="K3 不透参照·浅", theme="light", state_key=SK_I),
        dict(tag="Mica", theme="light", state_key=SK_I),
        dict(tag="Mica-dark", theme="dark", state_key=SK_I)]
pairs = dict((r["tag"], ref and ref["tag"]) for r, ref, _w in ledger_rows(rows))
check("D5 玻璃行只配同主题参照（Mica-dark 没有深色参照 ⇒ None）",
      pairs["Mica"] == "K3 不透参照·浅" and pairs["Mica-dark"] is None and
      pairs["K3 不透参照·浅"] is None, "%s" % pairs)
rows2 = rows + [dict(tag="K3 不透参照·深", theme="dark", state_key=SK_I)]
pairs2 = dict((r["tag"], ref and ref["tag"]) for r, ref, _w in ledger_rows(rows2))
check("D6 补上深色参照后 Mica-dark 配到深色（绝不配浅色）",
      pairs2["Mica-dark"] == "K3 不透参照·深", "%s" % pairs2)

REFB = {"tag": "K3", "theme": "light", "state_key": SK_I, "fails": 1, "measured": 3,
        "by": {"A[开始专注]": (2.30, 4.5), "B[我的]": (4.40, 4.5), "C[数据统计]": (6.00, 4.5)}}
CURB = {"tag": "Mica", "theme": "light", "state_key": SK_I, "fails": 2, "measured": 4,
        "by": {"A[开始专注]": (2.34, 4.5), "B[我的]": (4.60, 4.5),
               "C[数据统计]": (5.10, 4.5), "D[自定义]": (3.10, 4.5)}}
both, newg, newr, nk, nr, drops = legibility(REFB, CURB)
check("D7 对账分桶正确（沿用/玻璃掀掉/玻璃反而好）",
      both == {"A[开始专注]"} and newg == {"D[自定义]"} and newr == {"B[我的]"} and
      nk == ["D[自定义]"] and nr == ["B[我的]"],
      "both=%s newg=%s newr=%s" % (sorted(both), sorted(newg), sorted(newr)))
check("D8 降幅排序取最差三条且带符号",
      len(drops) == 3 and abs(drops[0][0] + 0.9) < 1e-9 and drops[0][1] == "C[数据统计]",
      "%s" % drops)

# ---- E: pick_ring_side ＝ K7 的采集裁决（第 16 轮就是死在这里的采集脆，不是判据）----
from probe_glass import pick_ring_side

SIDES = ["右", "左", "下", "上"]

# E1 第 16 轮的现场：右侧黑场被无名窗挡，其余场正常 ⇒ 必须换一条侧作数，而不是整轮判瞎
r16 = {
    "黑": {"右": "挡(无名)", "左": 0.0, "下": 5.0, "上": "挡"},
    "白": {"右": 255.0, "左": 250.0, "下": 240.0, "上": "挡"},
    "红": {"右": 76.2, "左": 70.0, "下": "挡", "上": "挡"},
    "蓝": {"右": 29.1, "左": 30.0, "下": "挡", "上": "挡"},
}
sn, series, spread, ok = pick_ring_side(r16, SIDES)
check("E1 某侧被挡 ⇒ 换可用侧，不再整轮判瞎（第 16 轮回归）",
      sn in ("右", "左", "下") and spread is not None and spread >= 30.0,
      "side=%s spread=%.1f 可用=%s" % (sn, spread or -1, ok))
check("E2 返回的序列就是选中那一侧的四个场值（绝不跨侧混值）",
      series.get("黑") is not None and series.get("白") is not None and
      abs(max(series["白"], series["黑"]) - min(series["白"], series["黑"]) - spread) < 1e-9,
      "series=%s spread=%.1f" % (series, spread or -1))

# E3 反面对照：黑只在左侧采到、白只在右侧采到 ⇒ 跨侧拼起来极差 255 很诱人，但必须判"一条都不可用"
mix = {
    "黑": {"右": "挡(A)", "左": 0.0, "下": "挡", "上": "挡"},
    "白": {"右": 255.0, "左": "挡(B)", "下": "挡", "上": "挡"},
    "红": {"右": "挡", "左": "挡", "下": "挡", "上": "挡"},
    "蓝": {"右": "挡", "左": "挡", "下": "挡", "上": "挡"},
}
sn2, s2, sp2, ok2 = pick_ring_side(mix, SIDES)
check("E3 锚点分散在不同侧 ⇒ 拒绝混值（返回 None，不许编出 255 极差）",
      sn2 is None and s2 == {} and sp2 is None and ok2 == [],
      "side=%s spread=%s" % (sn2, sp2))

# E4 两侧都可用时取极差大的那条，且可用侧列表按极差降序
both_ok = {
    "黑": {"右": 20.0, "左": 0.0, "下": 100.0, "上": 100.0},
    "白": {"右": 100.0, "左": 255.0, "下": 115.0, "上": 100.0},
    "红": {"右": 60.0, "左": 76.0, "下": 105.0, "上": 100.0},
    "蓝": {"右": 30.0, "左": 29.0, "下": 102.0, "上": 100.0},
}
sn3, s3, sp3, ok3 = pick_ring_side(both_ok, SIDES)
check("E4 四条侧都可用 ⇒ 选极差大的（左 255 > 右 80 > 下 15 > 上 0），并按极差降序全列出",
      sn3 == "左" and abs(sp3 - 255.0) < 1e-9 and [x[1] for x in ok3] == ["左", "右", "下", "上"],
      "side=%s spread=%.1f ok=%s" % (sn3, sp3, ok3))
check("E5 全平（四侧都不变色）⇒ 极差 0 仍返回该侧，判瞎交给 field_blind",
      pick_ring_side({nm: dict((s, 100.0) for s in SIDES) for nm in ("黑", "白")},
                     SIDES)[2] == 0.0, "")

# E6 采信的那条必须让 field_blind 放行；被拒的混值轮必须让 field_blind 判瞎（两条闸口径对齐）
pass_round = dict(HEALTHY, ring=series, ring_spread=spread)
check("E6 field_blind 与 pick_ring_side 口径一致（可用侧 ⇒ 不瞎）",
      field_blind(pass_round) is False, "side=%s spread=%.1f" % (sn, spread))
blind_round = dict(HEALTHY, ring=s2, ring_spread=sp2)
check("E7 field_blind 与 pick_ring_side 口径一致（无可用侧 ⇒ 判瞎）",
      field_blind(blind_round) is True, "side=%s spread=%s" % (sn2, sp2))
# E8 静默 bug 变异：若把"黑、白都在"这条前提写成"任一锚点在"，E3 就会假绿
src = inspect.getsource(pick_ring_side)
check("E8 前提写死在源码里（黑 AND 白 都在，不是 or）",
      's.get("黑") is not None and s.get("白") is not None' in src, "")

# ---- F: 解锁判据（一份实现＋三个消费方真的在用它）--------------------------
import probe_mica5 as _M5
HERE_D = os.path.dirname(os.path.abspath(__file__))

check("F1 Default＋虚拟屏合理 ⇒ READY", _M5.ready_from("Default", 2560, 1440) is True, "")
check("F2 锁屏桌面名一律不 READY",
      all(_M5.ready_from(n, 2560, 1440) is False for n in ("Screen-saver", "Winlogon", "Default-XXX", "")),
      "")
check("F3 名字对但息屏（虚拟屏 0）⇒ 不 READY", _M5.ready_from("Default", 0, 0) is False, "")
check("F4 SM7/8 的 3×3 蒙不过去（历史事故形状）",
      _M5.ready_from("Default", 3, 3) is False, "")
ds = inspect.getsource(_M5.desktop_ready)
check("F5 desktop_ready 取的是 78/79，不是 7/8",
      "GetSystemMetrics(78)" in ds and "GetSystemMetrics(7)" not in ds
      and "GetSystemMetrics(8)" not in ds, "")
_dupes = []
for f in ("ready_once.py", "watch_desktop.py", "unlock_runner.py"):
    t = open(os.path.join(HERE_D, f), "r", encoding="utf-8").read()
    if "desktop_ready" not in t:
        _dupes.append("%s 没调用共享判据" % f)
    if "OpenInputDesktop" in t:
        _dupes.append("%s 自己又抄了一份实现" % f)
check("F6 判据只有一份（三个消费方都 import，谁都不再抄）", _dupes == [],
      "全仓库唯一实现在 probe_mica5；违规：%s" % (_dupes or "无"))
ok_live, why_live = _M5.desktop_ready()
check("F7 desktop_ready 当场能跑通（真调用，不是只读源码）", isinstance(ok_live, bool),
      "此刻=%s（%s）" % (ok_live, why_live))

# ---- G: 页面态指纹（第 16 轮的测量效度事故：运行态那轮被拿去跟空闲参照对账）----
from probe_glass import state_key, state_of, state_comparable, STATE_JS, PIN_JS
from probe_glass import sweep_mode, main, CDP, CDPAttach, missing_rounds, COMBOS, launch

IDLE = {"status": "idle", "kind": "focus", "mode": "normal", "timing": "count",
        "ro": False, "cur": False}
RUN = dict(IDLE, status="run", cur=True)
check("G1 空闲态与运行态的键必须不同（同键＝可互比）",
      state_key(IDLE) == SK_I and state_key(RUN) == "run|focus|normal|count|0|1"
      and state_key(IDLE) != state_key(RUN), "%s / %s" % (state_key(IDLE), state_key(RUN)))
check("G2 读数秒数不进键（每帧变的量进了就永远配不上）",
      state_key(dict(IDLE, clock="25:00")) == state_key(dict(IDLE, clock="24:59")) == SK_I, "")
check("G3 六字段缺一个就换键（每个都会改变屏幕上写着什么）",
      len(set(state_key(dict(IDLE, **{k: v})) for k, v in
              (("kind", "short"), ("mode", "strict"), ("timing", "up"),
               ("ro", True), ("cur", True)))) == 5
      and len({state_key(IDLE), state_key(RUN)}) == 2, "")
check("G4 state_of 只认带 status 的 JSON（读不到一律 None，不拿 None 当"
      "\"状态相同\"）",
      state_of('{"status":"idle","kind":"focus","mode":"normal","timing":"count",'
               '"ro":false,"cur":false}') == IDLE and state_of("ERR:x") is None
      and state_of('{"err":"NO-T"}') is None and state_of("{}") is None, "")
check("G5 state_comparable 真值表：同主题同键 True；差态／差主题／缺键全 False",
      state_comparable({"theme": "light", "state_key": SK_I},
                       {"theme": "light", "state_key": SK_I})[0] is True
      and state_comparable({"theme": "light", "state_key": SK_I},
                           {"theme": "light", "state_key": "run|focus|normal|count|0|1"})[0] is False
      and state_comparable({"theme": "light", "state_key": SK_I},
                           {"theme": "dark", "state_key": SK_I})[0] is False
      and state_comparable({"theme": "light"}, {"theme": "light", "state_key": SK_I})[0] is False
      and state_comparable(None, None)[0] is False, "")
# G6 第 16 轮的现场复刻：运行态 32 条（多一条「暂停」1.49）对空闲态 30 条参照
R16_REF = dict(tag="K3 不透参照·浅", theme="light", state_key=SK_I, fails=6, measured=30,
               by={"span[开始专注]": (2.30, 4.5), "div[我的]": (4.40, 4.5)})
R16_ACR = dict(tag="Acrylic", theme="light", state_key=state_key(RUN), fails=5, measured=32,
               by={"span[暂停]": (1.49, 4.5), "div[我的]": (4.30, 4.5)})
_g6 = [(r, ref, why) for r, ref, why in ledger_rows([R16_REF, R16_ACR]) if r["tag"] == "Acrylic"]
check("G6 运行态轮配不上空闲参照，并把原因说出来（不再凭空算差集）",
      len(_g6) == 1 and _g6[0][1] is None and "页面态" in (_g6[0][2] or ""), "%s" % (_g6,))
_raised = ""
try:
    legibility(R16_REF, R16_ACR)
except Exception as e:
    _raised = str(e)
check("G7 legibility 自己也要挡（只靠调用方筛参照＝漏一次就编出\"玻璃掀掉 暂停\"）",
      "页面态不同" in _raised and "span[暂停]" not in _raised, _raised[:120])
_src = inspect.getsource(sweep_mode)
check("G8 sweep_mode 真的钉状态并当场回读（pin＋指纹＋非 idle 就作废，三者齐）",
      "cdp.ev(PIN_JS)" in _src and "state_key(st)" in _src and
      'st["status"] != "idle"' in _src and "K8-FAIL" in _src, "")
check("G9 钉状态走 app 自己的通道（stopAll/render/dualPromote），不直写 localStorage",
      "stopAll()" in PIN_JS and "render()" in PIN_JS and "dualPromote(" in PIN_JS
      and "localStorage" not in PIN_JS, "")
check("G10 顶层 const 不在 window 上：探针用裸名 T/S，绝不写 window.T",
      "typeof T" in STATE_JS and "typeof S" in STATE_JS and "window.T" not in STATE_JS
      and "window.S" not in STATE_JS and "window.T" not in PIN_JS, "")
check("G11 返回的轮次记录带 state_key（缺它 ledger 就配不上对）",
      "state=st" in _src and "state_key=sk" in _src, "")
# G12/G13：本轮真机踩到的"CDP 接不上"——重试本身是好意，但重试面一旦放宽到 Exception，
# K4/K5/K8 这些"量到了但不可信"的判废也会被顺手重跑，十次里蒙一次绿就是把噪声洗成结论。
_msrc = inspect.getsource(main)
_seg = _msrc.split("for attempt in (1, 2, 3):")[1].split("            if r:")[0]
check("G12 重试面只接\"环境没起来\"：CDPAttach 那一支才 continue，判废那一支只记录不重试，"
      "两支都不许写成 except Exception",
      "except CDPAttach" in _seg and "except Exception" not in _seg
      and _seg.count("continue") == 2
      and "except RuntimeError" in _seg and "aborts.append" in _seg
      and "continue" not in _seg.split("except RuntimeError")[1],
      _seg[:100].replace("\n", " "))
check("G12b 重试次数给到 3（第 18 次跑三轮卡 CDP，Acrylic 用完一次额度就整轮判废）",
      _seg.count("attempt < 3") == 2 and "for attempt in (1, 2, 3):" in _msrc, "")
check("G13 CDP 接不上抛的是 CDPAttach 这个专用类型（普通 RuntimeError 会和判废混在一起）",
      "raise CDPAttach(" in inspect.getsource(CDP.__init__), "")
_csrc = inspect.getsource(CDP.__init__)
check("G16 现场把\"一次都没回\"和\"回了但每次空列表\"分开写（第 18 次误读就是没分开）",
      "n_ok == 0" in _csrc and "n_nonempty == 0" in _csrc
      and ("if js:" + chr(10) + " " * 16 + "seen = [") in _csrc, "")
check("G17 读超时≥5 秒，且预算按墙钟算（上一版 for _ in range(240) 数的是次数，每次失败要吃 5 秒，"
      "名义 120 秒实际最坏 22 分钟，把外层 600 秒跑到 RC=124）",
      "timeout=5" in _csrc and "timeout=2" not in _csrc
      # 断的是"循环形状"不是"关键字"：上一版断 range(240) 不在源码里，结果被我自己那句
      # 解释性注释（"再上一版把预算写成 range(240)"）命中——注释里提历史写法是正当的，
      # 用它当"这行代码不存在"的证据等于让 prose 冒充 control flow。
      and "for _ in range(" not in _csrc
      and "t_end = time.time() + budget" in _csrc
      and "while time.time() < t_end" in _csrc and "budget=120.0" in _csrc, "")
check("G17b 现场消息把\"秒\"和\"试了几次\"都写出来（单位说清楚，下次不再拿次数当时间）",
      "n_try" in _csrc and "试了 %d 次" in _csrc and "%.0f 秒" in _csrc, "")
check("G14 少跑成的轮次会被点名（缺行不等于那行没问题）",
      missing_rounds(COMBOS, [dict(tag=c[3]) for c in COMBOS]) == [] and
      missing_rounds(COMBOS, [dict(tag=c[3]) for c in COMBOS if c[3] != "Acrylic-dark"])
      == ["Acrylic-dark"] and
      missing_rounds(COMBOS, []) == [c[3] for c in COMBOS], "")
_lsrc = inspect.getsource(launch)
check("G18 被测壳可覆盖（单变量实验必须用同一把尺子；写死 GEXE 就等于另造一个探针）",
      "def launch(flag, glass, port, tag, exe=None):" in _lsrc
      and "exe = exe or GEXE" in _lsrc and "Popen([exe, flag," in _lsrc
      and "exe=exe" in inspect.getsource(sweep_mode), "")
check("G15 六轮组合是模块级常量，且六个 tag／六个端口都互不重复",
      len(COMBOS) == 6 and len(set(c[3] for c in COMBOS)) == 6 and
      len(set(c[2] for c in COMBOS)) == 6 and
      sorted(set(c[4] for c in COMBOS)) == ["dark", "light"], "")

# ---- G19-G29：端口占用归因＋"不杀进程"的退路（第 18/19 次"端口在听、宿主活着、/json 永不回"）
# 这些全部离线可跑：pick_port/mine_verdict 是纯函数，port_owner 拿自己开的监听口当已知答案，
# port_free 拿真 HTTP 问——离线用桩替掉它，桩的形状就是第 19 次现场那三种回答。
import probe_glass as PG
import socket as _sk
_real_open, _real_owner, _real_free = PG.port_open, PG.port_owner, PG.port_free
try:
    PG.port_owner = lambda p: "STUB-OWNER"
    PG.port_free = lambda p, timeout=2.0: (False, "有主") if p == 9411 else (True, "没人听")
    _got, _why = PG.pick_port(9411)
    check("G19 首选端口不能用⇒往后挪一个能用的、把监听者写进说明、谁都不杀",
          _got == 9412 and "9411" in _why and "STUB-OWNER" in _why
          and "taskkill" not in inspect.getsource(PG.pick_port), "%d｜%s" % (_got, _why[:90]))
    PG.port_free = lambda p, timeout=2.0: (True, "没人听")
    _g2, _w2 = PG.pick_port(9411)
    check("G19b 端口空着就仍按固定端口跑（固定端口是串行六轮的前提，不是随手可换的装饰）",
          _g2 == 9411 and _w2 == "", "%d｜%r" % (_g2, _w2))
    PG.port_free = lambda p, timeout=2.0: (False, "半死监听者")
    _g3, _w3 = PG.pick_port(9411, max_shift=2)
    check("G19c 连着 max_shift 个都不能用⇒不许静默当成无事发生，说明必须非空且点名",
          _w3 != "" and "2" in _w3, "%d｜%s" % (_g3, _w3[:90]))
    # 第 19 次真实事故的形状：Mica-dark 挪去 9415（那一刻它是空的，谁都不觉得有问题），
    # 紧接着 Acrylic-dark 的首选就是 9415，撞上的正是自己上一轮挪进来的那个窗的残留。
    # 所以桩必须让"被预留的那个端口"当场看着是空的——否则 reserved 那条分支永远测不到：
    # 桩把 9412 也判成被占时，正确代码和「不看 reserved」的错误代码都会落到 9413，变异漏网。
    PG.port_free = lambda p, timeout=2.0: (p != 9411, "没人听")
    _g3b, _w3b = PG.pick_port(9411, reserved={9412})
    check("G19d 挪位不许踩别的轮次预留的端口（挪进下一轮的槽＝下一轮撞自己的残留，第 19 次就是这么烧的）",
          _g3b == 9413 and "9413" in _w3b, "%d｜%s" % (_g3b, _w3b[:80]))
    # 注意：这一段里 PG.port_free 是被桩换过的（G19 系列要它的三种回答）。
    # 判据必须读 _real_free＝真函数的源码，拿 PG.port_free 就是拿桩的源码量产品，
    # 桩写的是 lambda 一行、既没 requests 也没"半死监听者"⇒ 假红。
    check("G25 判\"端口能不能用\"问的是 HTTP /json，不是裸 TCP connect"
          "（accept 队列满的半死监听者在 1 秒 connect 里看着是空的，第 19 次三次重试全烧在那儿）",
          "port_free(" in inspect.getsource(PG.pick_port)
          and "port_open(" not in inspect.getsource(PG.pick_port)
          and "requests.get" in inspect.getsource(_real_free)
          and "ConnectionError" in inspect.getsource(_real_free)
          and "半死监听者" in inspect.getsource(_real_free), "")
    # G25 是文本判据，它有一处已知的失明：port_free 的 docstring 里就写着「半死监听者」，
    # 把那条 except 分支删掉、注释还留着 ⇒ 文本照样全绿，而函数已经把"接了永不回"当成没人听了
    # （第 19 次烧掉三次 120 秒的正是这个分支）。所以这条跑在函数上：自己开一个"收下连接、
    # 一个字节都不回"的监听口当已知答案——它必须判不能用。
    import threading as _th
    _hs = _sk.socket()
    _hs.bind(("127.0.0.1", 0))
    _hs.listen(5)
    _hp = _hs.getsockname()[1]
    _held = []

    def _hold_conn():
        try:
            _c, _ = _hs.accept()
            _held.append(_c)      # 挂着不 reply＝半死监听者的形状
        except Exception:
            pass
    _ht = _th.Thread(target=_hold_conn)
    _ht.daemon = True
    _ht.start()
    _hf_ok, _hf_why = _real_free(_hp, timeout=1.0)
    check("G25b 已知答案（跑在函数上）：接了永不回的端口必须判「不能用」，且归因写的是半死监听者",
          _hf_ok is False and "半死监听者" in _hf_why, "%s｜%s" % (_hf_ok, _hf_why[:70]))
    _ht.join(timeout=3.0)
    for _c in _held:
        try:
            _c.close()
        except Exception:
            pass
    _hs.close()
    _ls = _sk.socket()
    _ls.bind(("127.0.0.1", 0))
    _ls.listen(1)
    _p = _ls.getsockname()[1]
    PG.port_owner = _real_owner
    _who = PG.port_owner(_p)
    check("G20 port_owner 认得出真在听的那位（拿自己开的监听口当已知答案，不是只查源码）",
          ("PID=%s" % os.getpid()) in _who, _who[:140])
    _ls.close()
    check("G20b 关掉监听口后要说「没有主」（归因指着已经走了的进程，等于把假设写成证据）",
          "没有 LISTEN 者" in PG.port_owner(_p), PG.port_owner(_p)[:80])
    _udf = "C:/Users/x/AppData/Local/fq-glass-verify/profile"
    _saved = list(PG.OUR_UDF)
    try:
        PG.OUR_UDF[:] = [_udf]
        check("G21 占用者带的档案是自己起过的⇒判「自己人」；反斜杠写法同一答案；换盘路径⇒判「不是本进程起的」",
              PG.mine_verdict("--user-data-dir=" + _udf) is True
              and PG.mine_verdict("--user-data-dir=" + _udf.replace("/", chr(92))) is True
              and PG.mine_verdict("--user-data-dir=D:/other") is False
              and PG.mine_verdict("") is False, "")
    finally:
        PG.OUR_UDF[:] = _saved
    check("G22 端口挪动要落进台账：轮次记录带 port/port_note，且 main 会在 SUMMARY 点名",
          "port, note = pick_port(port, reserved=reserved)" in _src and "port=port" in _src
          and "port_note=port_note" in _src and "port_note" in _msrc, "")
    check("G23 launch 记下自己起过的 --udf（否则 port_owner 的「自己人／别人」归因没有依据）",
          "OUR_UDF.append(udf)" in _lsrc and '"--udf", udf' in _lsrc, "")
    check("G24 接不上时的失败消息带上「监听者是谁」（第 18 次只留下「空列表」，机制到今天还没证实）",
          "监听者=%s" in _csrc and "port_owner(port)" in _csrc, "")
    check("G24b 诊断自己不许把主流程带崩（port_owner 两层异常都收成一句话）",
          "端口表读不了" in inspect.getsource(PG.port_owner)
          and "逐连接查询炸了" in inspect.getsource(PG.port_owner), "")
    _tdsrc = inspect.getsource(PG.teardown)
    check("G26 收窗这一步要真的等到端口放开（宿主退了不等于它的 WebView2 浏览器进程退了，"
          "第 19 次下一轮就是撞在这上面烧掉三次 120 秒）",
          "proc.wait(timeout=10)" in _tdsrc and "wait_port_free(ACTIVE_PORT[0]" in _tdsrc
          and "PORT-NOT-FREE" in _tdsrc, "")
    check("G27 launch 把本轮端口记进 ACTIVE_PORT（否则 teardown 不知道该等谁）",
          "ACTIVE_PORT[0] = port" in _lsrc, "")
    _sw = inspect.getsource(sweep_mode)
    check("G28 每轮起手：先等端口可用（有上限），等不到才挪位，且挪位避开别的轮次预留的端口",
          "ready, why = wait_port_free(port)" in _sw and "pick_port(port, reserved=reserved)" in _sw
          and "reserved = set(c[2] for c in COMBOS) - {port}" in _sw, "")
    check("G29 一轮三次接不上不许把整趟带走：记 ENV-FAIL、这一行留空、后面的轮次继续跑"
          "（第 19 次 raise 出去，五行已经量到的数一行没印）",
          "ENV-FAIL" in _msrc and "r = None" in _msrc and "                    raise" not in _msrc,
          "")
    check("G29b 每轮开头清空上一轮的记录（三次没起窗时 SUMMARY 不许混进上一行的数）",
          _msrc.split("for flag, glass, port, tag, theme in combos:")[1].lstrip().startswith("r = None"),
          "")
    check("G30 起手先确认六个端口都能用，等不到只是点名一声（端口只是通道，不拿它判废）",
          "for _p in sorted(set(c[2] for c in COMBOS)):" in _msrc
          and "PRECLOSE 端口" in _msrc, "")
    check("G31 wait_port_free 是有上限的等待，不是「总会好的」"
          "（墙钟判据，绝不按次数计——第 19 次刚为这个单位错过 22 分钟）",
          "t_end = time.time() + budget" in inspect.getsource(PG.wait_port_free)
          and "for _ in range(" not in inspect.getsource(PG.wait_port_free), "")
finally:
    PG.port_open, PG.port_owner, PG.port_free = _real_open, _real_owner, _real_free

# ---- G32-G35：补轮开关 --only（第 20 次两行空着，只能补那两槽，不许整趟重跑碰运气）----
# 这组全是纯函数已知答案：select_combos 的三种输入各钉一条，第四钉"部分跑必须当场点名"。
_all = PG.select_combos(PG.COMBOS, [])
check("G32 only 为空＝全跑，且顺序/端口都不许动（默认行为不能被动过）",
      [c[3] for c in _all] == [c[3] for c in PG.COMBOS]
      and [c[2] for c in _all] == [c[2] for c in PG.COMBOS]
      and _all is not PG.COMBOS, "%d 行" % len(_all))
_sub = PG.select_combos(PG.COMBOS, ["Mica", "K3 不透参照·浅"])
check("G33 只挑两行就返回这两行，端口仍是各自那张表里的固定端口（不许现场造轮次）",
      [c[3] for c in _sub] == ["K3 不透参照·浅", "Mica"]
      and [c[2] for c in _sub] == [9411, 9412], str([c[2] for c in _sub]))
_raised = ""
try:
    PG.select_combos(PG.COMBOS, ["Micaa"])
    _raised = "没炸（返回了东西）"
except Exception as e:
    _raised = "%s:%s" % (type(e).__name__, e)
check("G34 名字写错必须当场炸并列出可选轮次（静默跳过＝整趟空台账，会被读成「那行没问题」）",
      _raised.startswith("ValueError") and "不存在" in _raised and "Mica" in _raised,
      _raised[:90])
_raised2 = ""
try:
    PG.select_combos([], ["Mica"])
    _raised2 = "没炸"
except Exception as e:
    _raised2 = "%s:%s" % (type(e).__name__, e)
check("G35 名字认识但一行没挑中也要炸（上游把 combos 筛空时不许安静返回空列表）",
      _raised2.startswith("ValueError") and "没挑中" in _raised2, _raised2[:90])
check("G36 部分跑要当场点名「这一趟只跑几轮」＋其余行另找出处（补轮日志不许被当成全量台账）",
      "PARTIAL RUN" in _msrc and "select_combos(" in _msrc
      and "if len(combos) != len(COMBOS):" in _msrc and "这趟没跑" in _msrc, "")
check("G37 --only 的命令行拆解：逗号分项／去空／去重／没给＝全跑（第 21 次补轮第一次就栽在整串被当成一个名字）",
      PG.parse_only(["--only=Mica,K3 不透参照·浅"]) == ["Mica", "K3 不透参照·浅"]
      and PG.parse_only([]) == []
      and PG.parse_only(["--only=Mica,,Mica", "--only=Acrylic"]) == ["Mica", "Acrylic"]
      and PG.parse_only(["quick"]) == [],
      str(PG.parse_only(["--only=Mica,K3 不透参照·浅"]))[:70])
check("G38 main 只准走 parse_only，不许自己随手 split（同一件事两处口径＝早晚分叉）",
      "select_combos(COMBOS, parse_only(sys.argv))" in _msrc
      and 'a.startswith("--only=")' not in _msrc, "")
# G39 排在 SUMMARY 之后这件事是**控制流**，不是文本次序 ⇒ 必须跑在 AST 上。
# 上一版用 str.index 找：注释里那句"一轮判废 = sys.exit(3) = 后面 SUMMARY 全部没打印"
# 是一个真实存在、而且刻意不能删的说明，却被当成代码里的判废调用，把全绿的量具判红。
import ast as _ast, textwrap as _textwrap
_mtree = _ast.parse(_textwrap.dedent(inspect.getsource(PG.main)))
_exit3 = sorted(n.lineno for n in _ast.walk(_mtree)
                if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Attribute)
                and n.func.attr == "exit" and getattr(n.func.value, "id", None) == "sys")
_summ = sorted(n.lineno for n in _ast.walk(_mtree)
               if isinstance(n, _ast.Call) and getattr(n.func, "id", None) == "print"
               and n.args and getattr(n.args[0], "value", None) == "\nSUMMARY")
check("G39 数先落地、判决后判：main 里**代码里**第一个 sys.exit 必须在 print(SUMMARY) 之后"
      "（判废闸门排在打印之前＝一个坏轮次把已量到的行一起吞掉，第 19 次的形状；AST 判定，注释不算）",
      len(_summ) == 1 and len(_exit3) >= 4 and min(_exit3) > _summ[0],
      "SUMMARY 行%s／exit 行%s" % (_summ, _exit3[:6]))
_strings = [n.value for n in _ast.walk(_mtree)
            if isinstance(n, _ast.Constant) and isinstance(n.value, str)]
_exit_text = [s for s in _strings if "sys.exit" in s]
check("G42 判废次序这条判据不许把「字面量里提到 sys.exit」当代码（否则删注释才能变绿，"
      "而注释正是那条决定的理由，删它＝毁证）",
      not _exit_text, "；".join(x.replace("\n", " ") for x in _exit_text)[:100])
# G43/G44：G39 只比行号，两种绕过它的方式要用 AST 才看得见（文本匹配判不出结构）。
_rt_h = [n for n in _ast.walk(_mtree)
         if isinstance(n, _ast.ExceptHandler) and getattr(n.type, "id", None) == "RuntimeError"]
check("G43 量具判废（RuntimeError）走「记录＋不重抛」：接住它的那段里不许有 raise"
      "（重抛＝一轮坏把整趟带走，第 19 次的失效半径；G40 那种文本匹配管不了这个形状）",
      len(_rt_h) >= 1 and all(not isinstance(x, _ast.Raise)
                              for h in _rt_h for x in _ast.walk(h)),
      "RuntimeError 接住处 %d 个" % len(_rt_h))
_par = dict((ch, n) for n in _ast.walk(_mtree) for ch in _ast.iter_child_nodes(n))
_in_try = []
for _n in _ast.walk(_mtree):
    if isinstance(_n, _ast.Call) and isinstance(_n.func, _ast.Attribute) \
            and _n.func.attr == "exit" and getattr(_n.func.value, "id", None) == "sys":
        _cur, _chain = _n, []
        while _cur in _par:
            _cur = _par[_cur]
            _chain.append(type(_cur).__name__)
        if "Try" in _chain:
            _in_try.append(_n.lineno)
check("G44 判决段的 sys.exit 不许被包进 try 体（包进去＝它先于数落地触发，而 G39 只看行号照样绿；"
      "这条是 G39 的牙）", not _in_try, str(_in_try[:6]))
check("G40 量具判废的轮次要逐条留下原因（只说「缺行」不说「为什么缺」＝下一个人只能猜）",
      'print("ABORTS' in _msrc and "for t, why in aborts" in _msrc
      and "aborts = []" in _msrc, "")
check("G41 补轮没带不透参照时必须当场声明「slope 这类数本轮不作结论」，"
      "但整趟跑却缺参照仍然是判废（两条路不许混成一条）",
      "K3-ABSENT" in _msrc and "partial = len(combos) != len(COMBOS)" in _msrc
      and _msrc.split("if not refs:")[1].split("for theme, ref")[0].count("sys.exit(3)") == 1,
      _msrc.split("if not refs:")[1][:180].replace("\n", " "))

# ---- H: 真桌面实拍的量具（shot_desktop：空帧/对齐/钳位/冻结口径/采集唯一实现）----
import re as _re
import shot_desktop as SD

check("H1 stats_of 的已知答案：纯色帧均值＝该色亮度、MAD＝0、色数＝1",
      SD.stats_of([(200, 200, 200)] * 400) == (200.0, 0.0, 1),
      str(SD.stats_of([(200, 200, 200)] * 400)))
_b = SD.stats_of([(0, 0, 0)] * 400)
_w = SD.stats_of([(abs((i * 7) % 256), (i * 3) % 256, 255 - (i * 5) % 256) for i in range(4000)])
check("H2 空帧闸门两头都有牙：全黑判空、渐变壁纸放行（只红或只绿都算瞎）",
      SD.blank_verdict(_b[0], _b[2], "全黑")[0] is False
      and SD.blank_verdict(_w[0], _w[2], "壁纸")[0] is True,
      "黑 均%.1f 色%d／壁纸 均%.1f 色%d" % (_b[0], _b[2], _w[0], _w[2]))
_IMG = [[(r, c % 256, (r * c) % 256) for c in range(10)] for r in range(12)]
_full = [p for _r in _IMG for p in _r]
_bands = [_full[i * 30:(i + 1) * 30] for i in range(4)]
_sub = []
for _i, _bd in enumerate(_bands):
    _sub.extend(SD.strip_crop(_bd, 10, _i * 3, 2, 4, 7, 11))
_exp = [_IMG[r][c] for r in range(4, 11) for c in range(2, 7)]
check("H3 横带拼接后按绝对坐标裁＝整块一次裁（逐像素相等，抓条带错位）",
      _sub == _exp, "得 %d／应 %d" % (len(_sub), len(_exp)))
_raised = False
try:
    SD.strip_crop(_bands[0], 10, 0, 8, 0, 14, 2)
except RuntimeError:
    _raised = True
check("H4 列越界必须炸（静默少裁＝拿半张冒充整张）", _raised, "")
check("H5a 贴边矩形钳回屏内并声明被钳过",
      SD.fit(0, 0, 100, 100, 90, 90, 40, 40) == (90, 90, 100, 100, True),
      str(SD.fit(0, 0, 100, 100, 90, 90, 40, 40)))
_dis = False
try:
    SD.fit(0, 0, 100, 100, 200, 200, 10, 10)
except RuntimeError:
    _dis = True
check("H5b 与屏完全不相交必须炸", _dis, "")
check("H5c inside() 只在全含时 True（钳过的不算全含，B 闸门就靠它拒绝互比）",
      SD.inside(0, 0, 100, 100, 10, 10, 20, 20) is True
      and SD.inside(0, 0, 100, 100, 90, 90, 20, 20) is False, "")
check("H7 对齐闸门：钳过的差再小也不许报\"对上\"；超差必须报红",
      SD.align_verdict(0.0, True)[0] is False and SD.align_verdict(0.5, False)[0] is True
      and SD.align_verdict(9.0, False)[0] is False, "")
check("H8 存盘闸门认字节：尺寸不符或 0 字节都判红",
      SD.size_verdict((3840, 2160), (3840, 2160), 100)[0] is True
      and SD.size_verdict((3840, 2160), (3840, 2000), 100)[0] is False
      and SD.size_verdict((3840, 2160), (3840, 2160), 0)[0] is False, "")
check("H9 实拍轮次直接复用 probe_glass.COMBOS（不另立一套材质×主题×端口）",
      SD.G.COMBOS is COMBOS and len(COMBOS) == 6, "")
_ssrc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "shot_desktop.py"), encoding="utf-8").read()
check("H10 采集实现只有一份：shot_desktop 不自己开 BitBlt/位图，一律走 probe_mica5.shot",
      "g.BitBlt" not in _ssrc and "g.CreateCompatibleBitmap" not in _ssrc
      and _ssrc.count("M5.shot(") >= 2, "M5.shot 出现 %d 次" % _ssrc.count("M5.shot("))
_coll = _re.sub(r'"\s*\n\s*"', "", inspect.getsource(sweep_mode))
check("H6 冻动画的脚本只有一份口径（拼回相邻字面量后逐字含在 sweep_mode 里）",
      SD.FREEZE_JS in _coll, "FREEZE_JS 长 %d" % len(SD.FREEZE_JS))
check("H11 实拍走的是同一份状态通道（PIN_JS/STATE_JS 从 probe_glass 取，不自己写 JS）",
      "G.PIN_JS" in _ssrc and "G.STATE_JS" in _ssrc
      and "localStorage" not in _ssrc.split("def read_state")[1].split("def one_round")[0], "")
# H12 跑在真函数上：文本匹配判不出"对照行被算成主张"这类形状（第 22 次实拍的 RC=1 正是它——
# 七行里三行"不作数"，其中一行是空桌面对照，它本来就没有页面态，也不该是一行主张）。
# 三行各押不作数名单里的一条 clause：FAIL 字样／页面态缺失／主题回读不符。
# 为什么要拆成三行：只给"既有 FAIL 字样又 okC=False"的行，摘掉其中任何一条兜底都不会红
# （M60 第一次跑就是 MISSED，正是这个形状）⇒ 每条兜底得有一行只有它能拦住。
import tempfile as _tf
import shutil as _sh
_r12 = [SD.row("Mica-dark", "dark", "x", state="idle|focus|normal|count|0|0", okC=False,
               whyA="OK", whyB="对齐（差 0.00）", whyD="存盘完整",
               whyC="FAIL：主题没落上（要求 dark）：RuntimeError(...)"),
        # 只有 okC 为假、原因原文里没带那三个字：拦住它的只能是不作数名单里那条 okC 判据
        # （今天 read_state 一定带 FAIL 前缀，这行是刻意造出来的第二道闸：文案改了闸不许失效）。
        SD.row("Acrylic-dark", "dark", "y", state="idle|focus|normal|count|0|0", okC=False,
               whyA="OK", whyB="对齐（差 0.00）", whyD="存盘完整",
               whyC="主题回读＝light，要求的是 dark（这句话里没带那三个英文字母）"),
        # 只有页面态读不到、主题落上了：拦住它的只能是 state=="-" 那条
        SD.row("Mica", "light", "z", state="-", okC=True, whyA="OK", whyB="对齐（差 0.00）",
               whyD="存盘完整", whyC="OK"),
        SD.row("（空桌面·对照）", "-", "w", control=True, whyA="OK", whyD="存盘完整",
               whyC="不适用（没起窗）")]
_d12 = _tf.mkdtemp(prefix="biye_shot_selftest_")
_old12 = SD.MANIFEST
try:
    SD.MANIFEST = os.path.join(_d12, "m.md")
    _p12, _n12 = SD.write_manifest(_r12, "自检用的合成清单（不落交付目录）")
    check("H12 不作数名单的三条兜底各自独立承重：FAIL 字样行／主题不符行／页面态缺失行都进名单，"
          "对照行不算主张（摘掉任何一条都有一行会混进台账）",
          _n12 == 3, "nbad=%s（应为 3：三条 clause 各一行；对照行不计）" % _n12)
    _t12 = open(_p12, encoding="utf-8").read()
    check("H12b 清单里有 C 这一列，且不作的数行看得见原因原文（只报条数不报原因＝下一个人重新查一遍）",
          "| C |" in _t12 and "主题没落上" in _t12, _t12[:60].replace("\n", " "))
    check("H12c 写盘只准落进自检沙箱目录（不许把合成清单混进交付结果目录冒充真产物）",
          _d12 in os.path.abspath(_p12) and "fq-glass-verify" not in os.path.abspath(_p12),
          os.path.abspath(_p12)[:90])
finally:
    SD.MANIFEST = _old12
    _sh.rmtree(_d12, ignore_errors=True)
check("H13 实拍用的端口退路就是 probe_glass 那一份（另写一套＝两个检测器两套判据重演）",
      "G.pick_port(port)" in inspect.getsource(SD.one_round)
      and "def pick_port" not in _ssrc and "def port_owner" not in _ssrc, "")
check("H14 两个像素量具都不许杀进程：占用者只归因、只挪位（历史事故：按镜像名全杀误伤用户自己的 Edge）",
      "taskkill" not in _ssrc and "/F /IM" not in _ssrc
      and "taskkill" not in inspect.getsource(PG.pick_port)
      and "taskkill" not in inspect.getsource(PG.port_owner), "")


class _Cdp16:
    """apply_theme 的手套：只回答"ev(js) 回来什么"，让这条判据跑在函数上而不是文本上。"""
    def __init__(self, ans):
        self.ans = ans
        self.js = None

    def ev(self, js):
        self.js = js
        return self.ans


_s16 = _Cdp16("dark")
check("H15 apply_theme 的已知答案（相符那半）：回读＝要求就放行，而且发出去的 JS 确实是"
      "「赋值＋回读」两句连体",
      PG.apply_theme(_s16, "dark") == "dark"
      and "dataset.theme='dark'" in (_s16.js or "") and "dataset.theme" in (_s16.js or "")[-40:],
      repr(_s16.js)[:120])
_boom16 = ""
try:
    PG.apply_theme(_Cdp16("light"), "dark")
    _boom16 = "没炸"
except RuntimeError as e:
    _boom16 = str(e)
check("H16 apply_theme 的已知答案（不符那半）：要求 dark 而页面回 light 必须抛，"
      "且报出「要求／回读」两个值（第 22 次实拍缺的就是这半条）",
      _boom16.startswith("主题没落上") and "dark" in _boom16 and "light" in _boom16, _boom16[:110])
_raised16 = ""
try:
    PG.theme_js("dusk")
    _raised16 = "没炸"
except Exception as e:
    _raised16 = "%s:%s" % (type(e).__name__, e)
check("H17 未知主题名必须当场 ValueError（写错主题名要是静默按 light 跑，那一行的主题标签就是假的）",
      _raised16.startswith("ValueError") and "dusk" in _raised16, _raised16[:90])
check("H18 主题动作全仓库只有一份：sweep_mode 与实拍 read_state 都调 apply_theme，"
      "dataset.theme 的 JS 字面量只许出现在 theme_js 里（两处各写一遍＝早晚一边只切不读）",
      "apply_theme(cdp, theme)" in inspect.getsource(PG.sweep_mode)
      and "G.apply_theme(" in inspect.getsource(SD.read_state)
      and "dataset.theme" not in _ssrc
      and inspect.getsource(PG).count("document.documentElement.dataset.theme=") == 1,
      "probe 里出现 %d 次／shot 里含 dataset.theme：%s"
      % (inspect.getsource(PG).count("document.documentElement.dataset.theme="),
         "dataset.theme" in _ssrc))
check("H19 实拍读状态必须把主题这件事交回行判据（okC 为假＝这行不作数，不许打印完就忘）",
      "return sk, bg or \"-\", (not why), " in inspect.getsource(SD.read_state)
      and "okC=okC" in inspect.getsource(SD.one_round), "")
check("H20 实拍的挑轮次与部分跑声明也走 probe_glass 那一份（自己拆命令行／默默少拍＝补轮清单冒充全量）",
      "G.select_combos(G.COMBOS, G.parse_only(sys.argv))" in inspect.getsource(SD.main)
      and 'print("PARTIAL RUN' in inspect.getsource(SD.main)
      and 'a.startswith("--only=")' not in _ssrc, "")

src_md5 = hashlib.md5(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "probe_glass.py"), "rb").read()).hexdigest()[:12]
print("\nprobe_glass.py md5=%s" % src_md5)
if FAILS:
    print("SELFTEST FAIL: %d -> %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("SELFTEST OK：A1a-A7d（MAD/变异目标/空帧）＋B1-B5c（已知答案对照）"
      "＋C1-C4（尺子死活判定与旧误判回归）＋D1-D8（场自检与同主题对账）"
      "＋E1-E8（多侧环带采集裁决，含第 16 轮回归与反跨侧混值对照）"
      "＋F1-F7（解锁判据唯一实现，含 7/8 历史事故回归）"
      "＋G1-G44（页面态指纹与按态配对、起窗重试面收窄且给到三次、缺行点名、CDP 现场三分家且预算按墙钟、"
      "被测壳可覆盖、端口占用只挪位不杀进程且归因可离线验证、收窗后真等到端口放开、"
      "一轮环境失败不带走整趟台账、判废逐条留原因且数先落地判决后判（这条跑在 AST 上：注释提到 sys.exit 不算代码）、"
      "补轮开关只准从固定表里挑且部分跑当场点名，"
      "含第 16 轮误配对与第 19/20 轮整趟作废两次回归）"
      "＋H1-H20（真桌面实拍的量具：空帧两头有牙、横带裁与整块裁逐像素相等、钳位/存盘/冻结口径只有一份、"
      "端口退路只有一份且两个量具都不许杀进程、主题回读跑在桩上且 JS 字面量全仓库只有一处、"
      "不作数名单的三条兜底各自独立承重、且全部跑在真写盘函数上）全绿")
sys.exit(0)
