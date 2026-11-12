# -*- coding: utf-8 -*-
"""`exp_host_surface.py` 那几把纯函数的已知答案自检（锁屏可跑，一个窗都不建、一个端口都不碰）。

为什么先要这一层：#42 那把尺真跑起来只有几分钟的窗口（解锁窗口常只有 ~3 分钟），现场没有
时间再判"我这把尺是不是自己瞎了"。所以把判决拆成纯函数，在这里用**手算得出的形状**钉死：
  · ①空窗对照失明时必须整场判废——这是"把尺子瞎了读成材质不采"那一条坑的反制；
  · ②主判的四个分支必须互相能区分（把判决调回恒真／调回恒"挡场"，这张表必须当场挑出至少
    两条该红／该换个说法的形状，否则它零鉴别力，跑绿也不许写成"通过校验"）；
  · 阈值沿用 #40 的 TRACK_MIN／DRIFT_TOL，本自检钉"这里没有新造阈值"。

用法：PYTHONIOENCODING=utf-8 python 验收/exp_host_surface.py --selfcheck
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import exp_host_surface as X   # noqa: E402  （--selfcheck 分支在 import 像素模块之前就返回了）

FAILS = []
TOTAL = []      # 条数由这里数出来；把写死的数字抄进结论行是本轮刚在别处犯过的错


def chk(name, cond, detail=u""):
    TOTAL.append(name)
    if cond:
        print(u"  ok   %s" % name)
    else:
        print(u"  FAIL %s ｜ %s" % (name, detail))
        FAILS.append(name)


def rec(pos_mean, client_mean, drift=0.0):
    return {"client": client_mean, "drift": drift, "pos": (pos_mean, 0, 0), "host": "桩"}


def tr(bright, dark):
    return X.track_of(bright, dark)


def arm(kind, d_client):
    """造一条 track_of 形状的读数（判决只吃前四个位置，第五个是跟踪比）。"""
    return (kind, "桩", d_client, 20.0, d_client / 20.0 if d_client is not None else None)


def main():
    print(u"== A 屏位配对与四态判决 ==")
    k, w, dc, dr, ratio = tr(rec(120.0, 100.0), rec(40.0, 60.0))
    chk("A1 跟屏位走（Δ客户区 +40，Δ屏位 +80）⇒ TRACKING", k == "TRACKING" and abs(dc - 40.0) < 1e-6,
        u"得 %s Δ%r" % (k, dc))
    chk("A2 跟踪比由客户区差／屏位差现算（0.50）", abs(ratio - 0.5) < 1e-9, repr(ratio))
    k, w, dc, dr, ratio = tr(rec(120.0, 60.0), rec(40.0, 59.0))
    chk("A3 Δ客户区 +1 < TRACK_MIN ⇒ FLAT", k == "FLAT", u"得 %s" % k)
    k, w, dc, dr, ratio = tr(rec(120.0, 100.0), None)
    chk("A4 暗位缺轮 ⇒ UNPAIRED（不许拿另一只材质顶替）", k == "UNPAIRED", u"得 %s" % k)
    k, w, dc, dr, ratio = tr(rec(120.0, 100.0, drift=9.0), rec(40.0, 60.0))
    chk("A5 桌面自己漂过 DRIFT_TOL ⇒ INVALID_DRIFT（Δ再大也不许判跟屏位走）", k == "INVALID_DRIFT",
        u"得 %s" % k)
    k, w, dc, dr, ratio = tr(rec(120.0, 40.0), rec(100.0, 42.0))
    chk("A6 Δ客户区 −2 落在阈值内 ⇒ FLAT，且负号不单独成判", k == "FLAT", u"得 %s" % k)
    # A8 钉的是真跑路径上会出现的那个形状：某一只裸窗整轮崩了 ⇒ 收回来的是
    # {"tag":…, "fail":"ROUND-CRASH …"} 这种**有值但没有 client 键**的桩（第 4 批那种
    # 780x0 崩溃就落在这一型上）。少了 track_of 里那句 "client" not in ⇒ 这里不是变红，
    # 而是 KeyError 把整场炸掉——变异证伪的附录里那条记的就是这件事。
    k, w, dc, dr, ratio = tr(rec(120.0, 100.0), {"tag": "bare-noredir-mica", "fail": "ROUND-CRASH x"})
    chk("A8 一轮是「有桩但没有 client 键」（ROUND-CRASH 的形状）⇒ UNPAIRED，不许当场炸",
        k == "UNPAIRED", u"得 %s" % k)
    chk("A7 阈值就是 #40 那两条（没新造数）",
        X.BS.TRACK_MIN == 8.0 and X.BS.DRIFT_TOL == 8.0 and X.reading_gates("x")["blank_on_client"] is False,
        u"TRACK_MIN=%r DRIFT_TOL=%r" % (X.BS.TRACK_MIN, X.BS.DRIFT_TOL))

    print(u"== B 采集通道的分工（本轮最容易自己造的假阳性） ==")
    chk("B1 NOREDIR 那几只：PrintWindow 只记不判（没有表面可印是预期）",
        X.reading_gates("bare-noredir-acrylic")["printwindow_is_reading"] is False)
    chk("B2 带表面那几只：PrintWindow 仍是读数",
        X.reading_gates("bare-redir-acrylic")["printwindow_is_reading"] is True)
    chk("B3 任何一只的客户区都不上空帧判据（NULL 背景刷的纯色黑是合法读数）",
        all(X.reading_gates(n)["blank_on_client"] is False for n, _e, _b, _l in X.BARE_ARMS))
    chk("B4 层序闸门对每一只都开着",
        all(X.reading_gates(n)["layer_gate"] is True for n, _e, _b, _l in X.BARE_ARMS))
    # B5/B6：这两条钉的是**上一趟真崩掉的那一格**（屏位选到 y=0，上侧环带零面积 ⇒
    # region_mean 抛 RuntimeError ⇒ 整场连一份报告都没落）。现场样本在先，锚跟着现场挂。
    vh_mock, vw_mock = 2160, 3840
    crashed = (208.3, 3000, 0)
    kept = (208.3, 1200, 240)
    low = (30.0, 1200, 120)
    right_edge = (30.0, vw_mock - X.BS.WIN_W, 240)
    kept_pts = X.full_ring_positions([crashed, kept, low, right_edge], vw_mock, vh_mock)
    chk("B5 屏位筛选：崩掉那一格（y=0）与左右压边的必须被剔掉，合规那两格留得住",
        crashed not in kept_pts and right_edge not in kept_pts and
        kept in kept_pts and low in kept_pts,
        u"留下 %s" % [p[1:3] for p in kept_pts])
    chk("B6 环带排版三档互不相同且 None 不炸（n/a／三侧点名／四侧正常）",
        len({X.ring_txt({"ring": None, "ring_sides": 0}, {"ring": 5.0, "ring_sides": 3}),
             X.ring_txt({"ring": 118.0, "ring_sides": 4}, {"ring": 35.0, "ring_sides": 4})}) == 2
        and "n/a" in X.ring_txt({"ring": None, "ring_sides": 0}, {"ring": 5.0, "ring_sides": 3})
        and "(3侧)" in X.ring_txt({"ring": None, "ring_sides": 0}, {"ring": 5.0, "ring_sides": 3}),
        X.ring_txt({"ring": None, "ring_sides": 0}, {"ring": 5.0, "ring_sides": 3}))

    print(u"== C ②主判的四个分支（含①失明必须整场判废） ==")
    good_ctl = {"bare-noredir-none": arm("TRACKING", 78.0)}
    a, b, c = X.surface_verdict(dict(good_ctl, **{
        "bare-noredir-mica": arm("TRACKING", 41.0), "bare-redir-mica": arm("FLAT", 0.4),
        "bare-noredir-acrylic": arm("TRACKING", 33.0), "bare-redir-acrylic": arm("FLAT", 1.1)}))
    chk("C1 摘了表面才跟 ⇒ SURFACE_BLOCKS×2", "SURFACE_BLOCKS／SURFACE_BLOCKS" in a, a)
    a, b, c = X.surface_verdict(dict(good_ctl, **{
        "bare-noredir-mica": arm("FLAT", 0.6), "bare-redir-mica": arm("FLAT", 0.2),
        "bare-noredir-acrylic": arm("FLAT", 1.2), "bare-redir-acrylic": arm("FLAT", 0.9)}))
    chk("C2 摘了也不跟 ⇒ LEVER_DEAD_ON_BARE×2（这一支只否定「表面是挡点」，不替产品宿主开脱）",
        "LEVER_DEAD_ON_BARE／LEVER_DEAD_ON_BARE" in a, a)
    a, b, c = X.surface_verdict(dict(good_ctl, **{
        "bare-noredir-mica": arm("TRACKING", 40.0), "bare-redir-mica": arm("TRACKING", 38.0),
        "bare-noredir-acrylic": arm("TRACKING", 30.0), "bare-redir-acrylic": arm("TRACKING", 29.0)}))
    chk("C3 带着表面照样跟 ⇒ SURFACE_NOT_CULPRIT×2（这条尺回答不了）",
        "SURFACE_NOT_CULPRIT／SURFACE_NOT_CULPRIT" in a, a)
    a, b, c = X.surface_verdict(dict(good_ctl, **{
        "bare-noredir-mica": arm("UNPAIRED", None), "bare-redir-mica": arm("FLAT", 0.1),
        "bare-noredir-acrylic": arm("INVALID_DRIFT", 60.0), "bare-redir-acrylic": arm("FLAT", 0.1)}))
    chk("C4 缺轮／不作数 ⇒ 两对都落 UNDECIDED，不硬凑一条", "UNDECIDED／UNDECIDED" in a, a)
    a, b, c = X.surface_verdict({"bare-noredir-none": arm("FLAT", 0.3),
                                 "bare-noredir-mica": arm("FLAT", 0.2),
                                 "bare-redir-mica": arm("FLAT", 0.1),
                                 "bare-noredir-acrylic": arm("FLAT", 0.4),
                                 "bare-redir-acrylic": arm("FLAT", 0.0)})
    chk("C5 ①空窗对照不亮 ⇒ ABORT 且判废（把失明读成「材质不采」正是这条要挡的）",
        a == "ABORT" and c is True, u"得 %s abort=%r" % (a, c))
    a, b, c = X.surface_verdict({"bare-noredir-mica": arm("TRACKING", 40.0),
                                 "bare-redir-mica": arm("FLAT", 0.3)})
    chk("C6 ①根本没采 ⇒ 同样 ABORT（缺对照＝不作数，不是「少一条行」）", a == "ABORT" and c is True, a)
    # C9 钉的是「缺轮」与「失明」这两条 remedy 不许混成一句话：前者要补齐那一只窗再跑，
    # 后者要修杠杆本身。判决串都是 ABORT、abort 位也都是 True，所以只比串比不出差别——
    # 必须比理由里那句「缺轮」。变异证伪里「把 UNPAIRED 那一支摘掉」就靠这条才有名字可点。
    a, b, c = X.surface_verdict({"bare-noredir-none": arm("UNPAIRED", None),
                                 "bare-noredir-mica": arm("FLAT", 0.2),
                                 "bare-redir-mica": arm("FLAT", 0.1)})
    chk("C9 ①空窗对照缺轮 ⇒ ABORT 且理由点名「缺轮」（缺轮与失明是两种 remedy，不许混写）",
        a == "ABORT" and c is True and u"缺轮" in b, u"得 %s｜%s" % (a, b))
    # C7/C8 钉的是第 3 批真撞上的那一档：满场漂 13.9~17.5 > 8.0 ⇒ ①那一对读成 INVALID_DRIFT。
    # 那一刻它到底是"环境失败"还是"量具判废"，决定 rc=4 还是 rc=5——两类混了就再也分不开。
    drift_ctl = {"bare-noredir-none": arm("INVALID_DRIFT", 78.0),
                 "bare-noredir-mica": arm("INVALID_DRIFT", 0.0),
                 "bare-redir-mica": arm("INVALID_DRIFT", 0.0),
                 "bare-noredir-acrylic": arm("INVALID_DRIFT", 0.0),
                 "bare-redir-acrylic": arm("INVALID_DRIFT", 0.0)}
    a, b, c = X.surface_verdict(dict(drift_ctl))
    chk("C7 ①因桌面自走不作数 ⇒ ENV-VOID 且 abort=False（环境失败不许报成量具判废）",
        a == "ENV-VOID" and c is False, u"得 %s abort=%r" % (a, c))
    chk("C8 ENV-VOID 落 rc=4、ABORT 落 rc=5（同一条「没结论」在两类的优先级上必须分开）",
        X.classify(14, 14, True, [])[0] == 4 and X.classify(14, 14, False, ["①失明"])[0] == 5 and
        X.classify(0, 14, True, [])[0] == 4,
        u"env=%s abort=%s both=%s" % (X.classify(14, 14, True, [])[0],
                                     X.classify(14, 14, False, ["x"])[0],
                                     X.classify(0, 14, True, [])[0]))

    print(u"== D 这张表自己有没有鉴别力（把判决调回恒真／恒挡场必须自曝） ==")
    fake_always = lambda pa, track_min=8.0: ("OK", "恒过", False)
    fake_blocks = lambda pa, track_min=8.0: ("SURFACE_BLOCKS／SURFACE_BLOCKS", "恒挡场", False)
    shapes = [
        (dict(good_ctl, **{"bare-noredir-mica": arm("TRACKING", 41.0), "bare-redir-mica": arm("FLAT", 0.4),
                           "bare-noredir-acrylic": arm("TRACKING", 33.0),
                           "bare-redir-acrylic": arm("FLAT", 1.1)}), True),
        (dict(good_ctl, **{"bare-noredir-mica": arm("FLAT", 0.6), "bare-redir-mica": arm("FLAT", 0.2),
                           "bare-noredir-acrylic": arm("FLAT", 1.2),
                           "bare-redir-acrylic": arm("FLAT", 0.9)}), False),
        ({"bare-noredir-none": arm("FLAT", 0.3), "bare-noredir-mica": arm("FLAT", 0.2),
          "bare-redir-mica": arm("FLAT", 0.1), "bare-noredir-acrylic": arm("FLAT", 0.4),
          "bare-redir-acrylic": arm("FLAT", 0.0)}, False),
    ]
    # 「恒过」那把尺必须至少在两条形状上给出与真判决不同的判决串——比的是判决本身，不是 abort 位
    caught = [i for i, (pa, _w) in enumerate(shapes, 1) if fake_always(pa)[0] != X.surface_verdict(pa)[0]]
    chk("D1 恒真版：至少两条形状被这张表挑出来（否则它零鉴别力）", len(caught) >= 2,
        u"只挑出 %s" % caught)
    caught2 = [i for i, (pa, _w) in enumerate(shapes, 1) if fake_blocks(pa)[0] != X.surface_verdict(pa)[0]]
    chk("D2 恒「挡场」版：与真判决至少在 C2／C5 两格不同（否则四个分支只是文字游戏）",
        len(caught2) >= 2, u"不同的格子 %s" % caught2)
    chk("D3 三个分支互不相同（SURFACE_BLOCKS／LEVER_DEAD／NOT_CULPRIT 的输出串不许撞车）",
        len({X.surface_verdict(pa)[0] for pa, _w in shapes}) == 3)

    print(u"== E rc 语义与优先级 ==")
    chk("E1 满场 ⇒ 0", X.classify(14, 14, False, []) == (0, "FULL：满 14 行"))
    chk("E2 缺轮 ⇒ 2 且写明不许重开洗绿", X.classify(9, 14, False, [])[0] == 2 and
        "不许重开" in X.classify(9, 14, False, [])[1])
    chk("E3 中途锁屏 ⇒ 4（环境失败与量具判废分家）", X.classify(9, 14, True, [])[0] == 4)
    chk("E4 判废压过环境（①失明时不许报成「只是没解锁」）", X.classify(9, 14, True, ["尺子瞎了"])[0] == 5)
    chk("E5 入场拒跑用的是端口占用与窗名两条独立证据", hasattr(X, "ports_busy") and
        list(X.PORT_RANGE) == [9411, 9412, 9413, 9414, 9415, 9416])

    print(u"== F 主判那一对真是单变量 ==")
    ex = dict((n, e) for n, e, _b, _l in X.BARE_ARMS)
    chk("F1 同一材质的两只裸窗只差 NOREDIR 那一个位",
        (ex["bare-noredir-mica"] ^ ex["bare-redir-mica"]) == X.WS_EX_NOREDIRECTIONBITMAP and
        (ex["bare-noredir-acrylic"] ^ ex["bare-redir-acrylic"]) == X.WS_EX_NOREDIRECTIONBITMAP,
        hex(ex["bare-noredir-mica"] ^ ex["bare-redir-mica"]))
    chk("F2 每对材质名一致（换的只有表面，不许顺手换材质）",
        [a[2] for a in X.BARE_ARMS if "mica" in a[0]] == ["mica", "mica"] and
        [a[2] for a in X.BARE_ARMS if "acrylic" in a[0]] == ["acrylic", "acrylic"])
    chk("F3 PAIRS 里每一对都是「同材质的 noredir vs redir」，没有跨材质配对",
        all(a == "bare-noredir-" + m.lower() and b == "bare-redir-" + m.lower()
            for a, b, m in X.PAIRS),
        repr(X.PAIRS))
    chk("F4 只关自己起的窗：BARE 标题不与被测窗／场窗同名",
        X.BARE_TITLE not in (X.G.GTITLE, "FQFIELD") and X.BARE_TITLE == "FQBARESURF")

    # F5：常量本身要和盘上两份独立写法对上。上一趟这里栽过——本尺原先把 NOREDIR 抄成
    # 0x00080000（那是 WS_EX_WINDOWEDGE），而"期望位 vs 实测位"闸门两边都用同一个错常量，
    # 于是它自洽地放行；这种错只有**跨文件**对表才打得响，所以不许再拿本尺自己的值当基准。
    import io as _io, re as _re
    srcs = {}
    for rel, pat in ((os.path.join(HERE, "..", "native", "FqHost.cs"),
                      r"WS_EX_NOREDIRECTIONBITMAP\s*=\s*(0x[0-9A-Fa-f]+)"),
                     (os.path.join(HERE, "smoke_ship.py"),
                      r"WS_EX_NOREDIRECTIONBITMAP\((0x[0-9A-Fa-f]+)\)")):
        p = os.path.abspath(rel)
        try:
            with _io.open(p, encoding="utf-8") as fh:
                m = _re.search(pat, fh.read())
            srcs[os.path.basename(p)] = int(m.group(1), 16) if m else None
        except IOError:
            srcs[os.path.basename(p)] = None
    chk("F5 NOREDIR 常量与两份独立写法逐位相同（FqHost.cs ＋ smoke_ship.py，且都得解析得出）",
        X.WS_EX_NOREDIRECTIONBITMAP == 0x00200000 and
        all(v == X.WS_EX_NOREDIRECTIONBITMAP for v in srcs.values()) and len(srcs) == 2,
        u"本尺=%s 对照=%s" % (hex(X.WS_EX_NOREDIRECTIONBITMAP),
                            {k: (hex(v) if v is not None else "读不到／没命中") for k, v in srcs.items()}))

    print(u"== G 漂的原始数必须整轮取（第 4 批那 19.3 就是靠这句才说得清是哪一轮） ==")
    bl = {"drift": 0.3, "other_now": 210.6, "other_base": 210.9}
    dk = {"drift": 19.3, "other_now": 191.7, "other_base": 210.6}
    tk, onow, obase, dv = X.drift_pair(bl, dk)
    chk("G1 取漂得狠的那一轮（暗轮）：两个数来自同一轮，不是拼出来的",
        (tk, onow, obase, dv) == (u"暗", 191.7, 210.6, 19.3),
        u"得 %r %r %r %r" % (tk, onow, obase, dv))
    chk("G2 反向（亮轮漂）⇒ 轮名跟着翻；调成 max(now)/min(base) 那种拼法当场露馅",
        X.drift_pair({"drift": 22.0, "other_now": 300.0, "other_base": 278.0}, dk)[:2] ==
        (u"亮", 300.0) and X.drift_pair(bl, dk)[1] != 210.6,
        u"得 %s" % (X.drift_pair({"drift": 22.0, "other_now": 300.0, "other_base": 278.0}, dk),))
    chk("G3 只有一轮有读数 ⇒ 取那一只且不许炸；两轮都没有 ⇒ 空值（排版那一头得能接住）",
        X.drift_pair(None, dk)[0] == u"暗" and X.drift_pair(bl, None)[0] == u"亮" and
        X.drift_pair(None, None) == (u"", None, None, None) and
        X.drift_pair({}, {}) == (u"", None, None, None),
        u"得 %s %s" % (X.drift_pair(None, dk), X.drift_pair(None, None)))

    print(u"\nOFFLINE-CHECK %s（%d 条，失败 %d）" %
          ("ALL-OK" if not FAILS else "FAIL: " + "／".join(FAILS), len(TOTAL), len(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
