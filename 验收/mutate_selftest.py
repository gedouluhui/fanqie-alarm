# -*- coding: utf-8 -*-
"""证伪器：把 selftest_probe_instr.py 依赖的那几个纯函数逐个注入"合理但不许存活"的 bug，
要求离线自检必须变红并点名到具体断言。rc 不归因到断言名＝这条变异没抓到，算自检有洞。

为什么要有这个文件：selftest 全绿只证明断言没写反，不证明断言有牙。这一串变异对应历史教训
（K2 在渐变底上飘 1.00/1.71、参照轮那条误设前提的闸门、单侧环带被第三方窗挡掉整轮）：
阈值放宽到恒真、排序键反了、and 写成 or、跨侧混值、把产品属性当尺子属性。

副本写到 %TEMP%\\fq-selftest-mutate，绝不在交付目录里改文件；每个变异先断言锚点唯一，
跑完打印被抓/漏网与点名的断言。
"""
import os, re, shutil, subprocess, sys, tempfile
# 兜住 GBK 控制台／重定向：这份报告的判决行里有 ⇒ 与中文，locale 编码下打印它们会让
# 进程恰好崩在"打印结论那一行"上——rc=1 长得像"闸门判红"，其实是量具自己没跑完
# （2026-10-09T18:24Z 实测：`> 文件` 时本文件即如此，接终端却全绿）。判据一行没动。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ("probe_glass.py", "probe_mica5.py", "selftest_probe_instr.py",
         "ready_once.py", "watch_desktop.py", "unlock_runner.py", "shot_desktop.py")
FAIL_RE = re.compile(r"^([A-H]\d+[a-z]?)\b.*\sFAIL\b", re.M)

# (变异名, 目标文件, 原文, 改成, 期望被点名的断言前缀)
MUTATIONS = [
    ("M1 锚点齐备这条前提 and→or", "probe_glass.py",
     'if s.get("黑") is not None and s.get("白") is not None and len(clean) >= 2:',
     'if s.get("黑") is not None or s.get("白") is not None or len(clean) >= 2:',
     "E3"),
    ("M2 选侧排序键反了（改挑极差最小）", "probe_glass.py",
     "cands.sort(key=lambda z: -z[0])", "cands.sort(key=lambda z: z[0])",
     "E4"),
    ("M3 跨侧混值（本侧被挡就去别的侧借一个数）", "probe_glass.py",
     '            v = side.get(sn)\n            s[nm] = v if isinstance(v, float) else None',
     '            v = side.get(sn)\n'
     '            if not isinstance(v, float):\n'
     '                v = next((side.get(o) for o in sides\n'
     '                          if isinstance(side.get(o), float)), None)\n'
     '            s[nm] = v if isinstance(v, float) else None',
     "E3"),
    ("M4 空帧闸门改成恒绿（thr=-1）", "probe_glass.py",
     "def frame_is_black(px, thr=12.0):", "def frame_is_black(px, thr=-1.0):",
     "A7a"),
    ("M5 平底判据写成恒真（mad<6 → mad<998）", "probe_glass.py",
     'flat = [w for w in worst if w[3].get("mad", 999) < 6.0]',
     'flat = [w for w in worst if w[3].get("mad", 999) < 998.0]',
     "A4"),
    ("M6 K1 阈值放宽到看不见（>12 → >1000）", "probe_glass.py",
     'if r.get("k1") is None or r["k1"] > 12:', 'if r.get("k1") is None or r["k1"] > 1000:',
     "C2"),
    ("M7 K6 阈值放宽到看不见（>1.0 → >100）", "probe_glass.py",
     'if r.get("k6") is None or r["k6"] > 1.0:', 'if r.get("k6") is None or r["k6"] > 100:',
     "C2"),
    ("M8 把产品属性塞回尺子判定（旧误判复活）", "probe_glass.py",
     '        why.append("K6 判级和算式不一致（%s）" % r["k6v"])\n    return why',
     '        why.append("K6 判级和算式不一致（%s）" % r["k6v"])\n'
     '    if r.get("fails"):\n        why.append("有不达 AA")\n    return why',
     "C3"),
    ("M9 环带极差判据 30→1（场不动也放行）", "probe_glass.py",
     "return not (sp is not None and sp >= 30.0 and",
     "return not (sp is not None and sp >= 1.0 and",
     "D4"),
    ("M10 主题配对降级成跨主题（拿浅参照配暗玻璃）", "probe_glass.py",
     '    if a.get("theme") != b.get("theme"):\n'
     '        return False, "主题不同（%s／%s）" % (a.get("theme"), b.get("theme"))',
     '    if False:\n        return False, "主题不同"',
     "G5"),
    ("M13 配对只看主题、不看页面态（第 16 轮的事故原样复活）", "probe_glass.py",
     "        for x in same_theme:\n            if state_comparable(x, r)[0]:",
     "        for x in same_theme:\n            if True:",
     "G6"),
    ("M14 对账函数自己不设防（只信调用方筛过的参照）", "probe_glass.py",
     '    ok, why = state_comparable(ref, r)\n    if not ok:\n'
     '        raise RuntimeError("legibility 配对不合法：%s ⇒ 不许对账" % why)',
     "    ok, why = state_comparable(ref, r)\n    if False:\n        raise RuntimeError(why)",
     "G7"),
    ("M15 把每帧变的读数放进指纹（永不配对＝参照永远配不上）", "probe_glass.py",
     'STATE_KEYS = ("status", "kind", "mode", "timing", "ro", "cur")',
     'STATE_KEYS = ("status", "kind", "mode", "timing", "ro", "cur", "clock")',
     "G2"),
    ("M16 读不到状态时返回半成品 dict（None 被当成\"状态未知\"混进可比集合）",
     "probe_glass.py",
     '    if not isinstance(st, dict) or "status" not in st or st.get("err"):',
     "    if not isinstance(st, dict):",
     "G4"),
    ("M17 探针只读状态不钉状态（pin 那一步被摘掉）", "probe_glass.py",
     '    pin = json.loads(cdp.ev(PIN_JS) or "{}")',
     "    pin = {}",
     "G8"),
    ("M18 重试面放宽到 Exception（判废的轮次也被重跑，噪声洗成结论）", "probe_glass.py",
     "                except CDPAttach as e:",
     "                except Exception as e:",
     "G12"),
    ("M19 接不上调试通道时抛普通 RuntimeError（和 K4/K5 判废混成一类）", "probe_glass.py",
     'raise CDPAttach("CDP 里 %.0f', 'raise RuntimeError("CDP 里 %.0f',
     "G13"),
    ("M20 少跑成的轮次不再点名（SUMMARY 少一行被读成\"那行没问题\"）", "probe_glass.py",
     '    got = set(r["tag"] for r in res)',
     "    got = set(c[3] for c in combos)",
     "G14"),
    ("M11 解锁判据放宽成「不是 Winlogon 就行」", "probe_mica5.py",
     '    return name == "Default" and w > 100 and h > 100',
     '    return name != "Winlogon"',
     "F2"),
    ("M12 屏尺寸退回 7/8（历史事故原样复活）", "probe_mica5.py",
     "    return ready_from(buf.value, u.GetSystemMetrics(78), u.GetSystemMetrics(79)), \\\n"
     '        "%s %dx%d" % (buf.value, u.GetSystemMetrics(78), u.GetSystemMetrics(79))',
     "    return ready_from(buf.value, u.GetSystemMetrics(7), u.GetSystemMetrics(8)), \\\n"
     '        "%s %dx%d" % (buf.value, u.GetSystemMetrics(7), u.GetSystemMetrics(8))',
     "F5"),
    # ---- 真桌面实拍（shot_desktop）的四条闸门 ----
    ("M21 空帧闸门改成恒绿（什么黑帧都放行）", "shot_desktop.py",
     "    if mean < BLANK_MEAN or uniq < BLANK_UNIQ:", "    if False:", "H2"),
    ("M22 横带裁按绝对行号取基址（条带错位历史形状）", "shot_desktop.py",
     "        base = (r - sy) * cw", "        base = r * cw", "H3"),
    ("M23 fit 不相交不炸（返回屏外矩形）", "shot_desktop.py",
     "    if x1 <= x0 or y1 <= y0:", "    if False:", "H5b"),
    ("M24 钳过边的客户区也算对上（B 闸门失明）", "shot_desktop.py",
     "    if clipped:", "    if False:", "H7"),
    ("M25 冻结脚本两处开始分叉（shot 这边换了 style id）", "shot_desktop.py",
     "s.id='fq-freeze';", "s.id='fq-freez2';", "H6"),
    ("M26 一行判据把页面态摘掉（只剩 A/B/D 就报绿）", "shot_desktop.py",
     'or d["state"] == "-"', "or False", "H12"),
    ("M27 另起第二条采集路径（PIL ImageGrab 本机出黑帧）", "shot_desktop.py",
     "        dpx, _ = M5.shot(cx, cy, cw, ch)",
     "        from PIL import ImageGrab as _IG\n"
     "        dpx, _ = _Image_shim(_IG.grab()), cw", "H10"),
    ("M28 起窗失败那条只重试一次（六轮里三轮卡 CDP 时会直接判废）", "probe_glass.py",
     "                    if r is None and attempt < 3:",
     "                    if r is None and attempt == 1:", "G12b"),
    ("M29 读超时退回 2 秒（负载机上把「HTTP 没回」冒充成「target 空列表」）", "probe_glass.py",
     "                resp = requests.get(\"http://127.0.0.1:%d/json\" % port, timeout=5)",
     "                resp = requests.get(\"http://127.0.0.1:%d/json\" % port, timeout=2)", "G17"),
    ("M31 被测壳写死成 GEXE（单变量实验只能另造一个探针＝两套判据）", "probe_glass.py",
     "    exe = exe or GEXE", "    exe = GEXE", "G18"),
    ("M30 现场不分家（每轮都用空 js 覆写 seen，第 18 次那句误读复活）", "probe_glass.py",
     '            if js:\n'
     '                seen = ["%s:%s" % (t.get("type"), (t.get("url") or "")[-42:]) for t in js]',
     '            seen = ["%s:%s" % (t.get("type"), (t.get("url") or "")[-42:]) for t in js]',
     "G16"),
    # ---- 端口占用这一族（第 18 次"端口在听、宿主活着、/json 永远空列表"）----
    ("M32 预算退回按次数计（range(240)，名义 120 秒实际最坏 22 分钟，外层 600 秒被拖成 RC=124）",
     "probe_glass.py",
     "        while time.time() < t_end:", "        for _ in range(240):", "G17"),
    ("M32b 读超时改成不限（一次挂死就把整条预算吃光）", "probe_glass.py",
     "timeout=5)", "timeout=None)", "G17"),
    ("M33 首选端口被占时不真挪位（返回的还是被占的那个，等于没有退路）", "probe_glass.py",
     '            return p, "端口 %d 不能用', '            return preferred, "端口 %d 不能用',
     "G19"),
    ("M33b 端口空着也往后挪一个（固定端口这条契约悄悄没了）", "probe_glass.py",
     '        return preferred, ""', '        return preferred + 1, ""',
     "G19b"),
    ("M33c 连续被占时静默退回首选（说明写空＝读的人以为一切正常）", "probe_glass.py",
     '    return preferred, "端口 %d 起连续 %d 个都不能用（%s），仍按 %d 尝试（监听者：%s）" % (\n'
     '        preferred, max_shift, why, preferred, port_owner(preferred))',
     '    return preferred, ""',
     "G19c"),
    ("M34 归因函数忘记查档案清单（占端口的永远判成「别人」，白查一场）", "probe_glass.py",
     "for p in OUR_UDF)", "for p in [])",
     "G21"),
    ("M35 失败消息不带监听者是谁（下次现场依旧只有「空列表」三个字）", "probe_glass.py",
     "what, port_owner(port)))", 'what, "-"))',
     "G24"),
    ("M36 launch 不记自己起过的 --udf（覆盖而非累加）", "probe_glass.py",
     "    OUR_UDF.append(udf)", "    OUR_UDF.clear()", "G23"),
    ("M37 轮次记录不写 port_note（挪过端口这件事进不了 SUMMARY）", "probe_glass.py",
     "                port=port, port_note=port_note,", "                port=port,", "G22"),
    ("M38 现场消息不报试了几次（「秒」和「次数」又混成一回事）", "probe_glass.py",
     '                what = "/json 在 %.0f 秒（试了 %d 次）里一次都没成功回过（最后一次请求=%s）" % (',
     '                what = "/json 一次都没成功回过（最后一次请求=%s）" % (',
     "G17b"),
    ("M39 实拍另起一套端口退路（两个检测器两套判据的历史形状）", "shot_desktop.py",
     "    port, note = G.pick_port(port)", "    port, note = port, \"\"", "H13"),
    # 这条只往源码里塞一句"杀进程"的字样，不真执行：本机按镜像名全杀曾经误杀用户自己的 Edge，
    # 变异跑是在沙箱副本里跑同一份自检，若真执行就会在用户桌面上动手——闸门要的是"写了就不许过"。
    ("M40 端口被占时顺手把占用者清掉（历史事故原样复活）", "probe_glass.py",
     "    for p in range(preferred + 1, preferred + 1 + max_shift):",
     '    _kill = "taskkill /F /IM msedge.exe"\n'
     "    for p in range(preferred + 1, preferred + 1 + max_shift):",
     "H14"),
    # ---- 端口占用这一族的第二段（第 19 次：窗收掉了、它的 WebView2 还赖在固定端口上）----
    ("M41 判「端口能不能用」退回裸 TCP connect（accept 队列满的半死监听者看着是空的）",
     "probe_glass.py",
     "    free, why = port_free(preferred)",
     '    free, why = (not port_open(preferred)), "没人听"',
     "G25"),
    ("M42 连上但永不回的那位判成「没人听」（②③不分家，整轮烧在占死的端口上）",
     "probe_glass.py",
     '    except Exception as e:\n        return False, "半死监听者（%s: %s）" % (type(e).__name__, str(e)[:60])',
     "    except Exception as e:\n        return True, \"没人听\"",
     "G25"),
    ("M43 挪位不看别的轮次预留的端口（挪进下一轮槽位＝下一轮撞自己的残留）", "probe_glass.py",
     "        if p in reserved:", "        if False:", "G19d"),
    ("M44 收窗后不等端口放开（宿主退出被当成端口也退了）", "probe_glass.py",
     "        ok, why = wait_port_free(ACTIVE_PORT[0], budget=PORT_WAIT)",
     '        ok, why = (True, "")',
     "G26"),
    ("M45 launch 不记本轮端口（teardown 不知道该等谁）", "probe_glass.py",
     "    ACTIVE_PORT[0] = port", "    ACTIVE_PORT[0] = None", "G27"),
    ("M46 每轮起手不等端口，直接挪位（等待那段没了）", "probe_glass.py",
     "    ready, why = wait_port_free(port)", '    ready, why = (True, "")', "G28"),
    ("M47 三次接不上又 raise 出去（第 19 次：五行已量到的数一行没印）", "probe_glass.py",
     '                    print("  ENV-FAIL %s：三次都接不上调试通道，这一轮没有数（会在缺行名单里点名）：%s"\n'
     "                          % (tag, e), flush=True)\n"
     "                    r = None",
     "                    raise",
     "G29"),
    ("M48 每轮开头不清空（这一轮三次没起窗时，SUMMARY 顶着上一行的数）", "probe_glass.py",
     "            r = None            # 每轮开头清空：上一轮的记录不许在这轮三次都没起窗时混进 SUMMARY",
     "            pass                # 每轮开头清空：上一轮的记录不许在这轮三次都没起窗时混进 SUMMARY",
     "G29b"),
    ("M49 起手不确认六个端口（脏端口只在轮子里才被发现）", "probe_glass.py",
     "    for _p in sorted(set(c[2] for c in COMBOS)):", "    for _p in ():", "G30"),
    ("M50 等端口放开退回按次数计（一次请求 5 秒，名义 25 秒实际能拖两分半）", "probe_glass.py",
     '    t_end = time.time() + budget\n    why = "没试过"\n    while time.time() < t_end:',
     '    why = "没试过"\n    for _ in range(25):',
     "G31"),
    # ---- 补轮开关 --only（第 20 次两行空着；补轮最容易造出"看起来跑完了的空台账"）----
    ("M51 only 被忽略（写错名字或筛完为空都变成「全跑」，补轮意图静默丢失）", "probe_glass.py",
     "    if not tags:", "    if True:", "G33"),
    ("M52 未知轮次名静默跳过（整趟空台账，会被读成「那行没问题」）", "probe_glass.py",
     "    if unknown:", "    if False:", "G34"),
    ("M53 一行没挑中也静默返回空列表（同上：跑完了但一行没有）", "probe_glass.py",
     "    if not sel:", "    if False:", "G35"),
    ("M54 部分跑不点名（补轮日志被当成全量台账读）", "probe_glass.py",
     "        if len(combos) != len(COMBOS):", "        if False:", "G36"),
    ("M55 --only 不按逗号拆分（整串当成一个轮次名＝补轮要么炸要么跑错槽）", "probe_glass.py",
     '            tags += [t.strip() for t in a.split("=", 1)[1].split(",")]',
     '            tags += [a.split("=", 1)[1]]',
     "G37"),
    ("M56 main 绕过 parse_only 直接给空（--only 被吃掉＝每趟都跑全量，补轮开关形同虚设）",
     "probe_glass.py",
     "        combos = select_combos(COMBOS, parse_only(sys.argv))",
     "        combos = select_combos(COMBOS, [])",
     "G38"),
    # ---- 主题回读这一族（第 22 次实拍：标签写着 dark、页面从没被切过）----
    ("M57 apply_theme 只切不读（回读不符也放行＝轮次标签冒充页面事实）", "probe_glass.py",
     "    if got != theme:", "    if False:", "H16"),
    ("M58 theme_js 认未知主题名（写错主题静默按别的跑＝那一行的主题列是假的）", "probe_glass.py",
     '    if theme not in ("dark", "light"):', "    if False:", "H17"),
    ("M59 实拍不再切主题（只留 probe 那边切＝深主题那两行的像素是浅底的）", "shot_desktop.py",
     "            G.apply_theme(c, theme)", "            pass", "H18"),
    ("M60 主题没落上的行照样进台账（不作数名单不看 okC＝坏行冒充好数）", "shot_desktop.py",
     '                or not d.get("okC"))]', "                or False)]", "H12"),
    ("M61 读状态永远报 OK（why 攒了一堆但 (not why) 被换成 True）", "shot_desktop.py",
     '    return sk, bg or "-", (not why), "；".join(why) or "OK"',
     '    return sk, bg or "-", True, "；".join(why) or "OK"', "H19"),
    # ---- 失效半径：一轮坏/一条闸门坏，不许带走整趟已经量到的数 ----
    ("M62 判废轮次改成重抛（第 19 次的半径复活：后面五轮的数一行不印）", "probe_glass.py",
     "                    aborts.append((tag, str(e)[:220]))", "                    raise", "G43"),
    ("M63 判决闸门包进 try/finally 里提前 exit（G39 只比行号看不出来，数一行没落地）",
     "probe_glass.py",
     "    partial = len(combos) != len(COMBOS)",
     "    try:\n        sys.exit(3)\n    finally:\n"
     "        partial = len(combos) != len(COMBOS)",
     "G44"),
    ("M64 把判废次序的理由写成字面量塞进 main（文本匹配判据会把它当代码⇒逼着删注释）",
     "probe_glass.py",
     "    partial = len(combos) != len(COMBOS)",
     '    _why = "历史上这里的位置是 sys.exit(3)，位置说明不能当代码算"\n'
     "    partial = len(combos) != len(COMBOS)",
     "G42"),
]


def run_case(label, fname, old, new, want, tag):
    d = os.path.join(tempfile.gettempdir(), "fq-selftest-mutate", tag)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    for f in FILES:
        shutil.copy2(os.path.join(HERE, f), os.path.join(d, f))
    p = os.path.join(d, fname)
    src = open(p, "r", encoding="utf-8").read()
    if src.count(old) != 1:
        return (label, "BAD-HOOK", "锚点在源码里出现 %d 次（变异脚本自己得先保证唯一）"
                % src.count(old))
    mutated = src.replace(old, new)
    try:
        compile(mutated, fname, "exec")
    except SyntaxError as e:
        return (label, "BAD-HOOK", "注入后语法就崩：%s" % e)
    open(p, "w", encoding="utf-8").write(mutated)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    a = subprocess.run([sys.executable, os.path.join(d, "selftest_probe_instr.py")],
                       capture_output=True, text=True, encoding="utf-8", env=env, cwd=d)
    fails = FAIL_RE.findall(a.stdout)
    if a.returncode == 0:
        return (label, "MISSED", "注入后自检仍 rc=0（断言没牙）")
    if not fails:
        return (label, "CRASH", "rc=%d 但没有断言级失败，不算抓到：%s"
                % (a.returncode, (a.stderr or "")[-300:]))
    hit = [f for f in fails if f.startswith(want)]
    return (label, "CAUGHT" if hit else "WRONG-ASSERT",
            "点名 %s%s" % (",".join(dict.fromkeys(fails)),
                           "" if hit else "（没点到期望的 %s）" % want))


def main():
    if "--list" in sys.argv:
        for m in MUTATIONS:
            print("%-46s 期望点名 %s" % (m[0], m[4]))
        return 0
    bad = []
    for i, (label, fname, old, new, want) in enumerate(MUTATIONS):
        r = run_case(label, fname, old, new, want, "m%02d" % i)
        print("%-42s %-13s %s" % r, flush=True)
        if r[1] != "CAUGHT":
            bad.append(r)
    print("\n共 %d 个变异，被抓 %d，漏网/异常 %d" %
          (len(MUTATIONS), len(MUTATIONS) - len(bad), len(bad)))
    if bad:
        print("MUTATE FAIL：%s" % ", ".join(b[0] for b in bad))
        return 1
    print("MUTATE OK（每个合理 bug 都被点名抓到）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
