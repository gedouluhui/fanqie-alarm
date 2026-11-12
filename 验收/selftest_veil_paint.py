# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
"""exp_veil_paint.py 的离线自检（锁屏可跑：不起窗、不采像素、不往交付目录写报告）。

它证明的是**量具与重试语义**可信，不是 #37 的机制结论：
  · add_row 的行宽闸门——加了列忘了改表头时，表格会「看着齐、其实整列错位」，那种错没人看得出来；
  · classify 的四分法——「环境打断」（该整趟重来）与「量具 ABORT」（重试没意义）必须分家；
    第 1 次真跑交白卷，就是因为两者在 rc 上长成一个样子；
  · sweep 的补齐语义——用假 one_material 真调用：环境打断后只补还缺的材质、
    墙钟用尽不开新窗、三种材质齐了就一次都不重跑；
  · one_material 每处 `except EnvUnavailable` 都单独接且继续往上抛（AST 结构检查，不是数字符——
    上一版按前 80 字符判，注释一长就飘，测的是排版不是语义）；
  · 报告表头/分隔行/数据行三者列数一致，带竖线的页面态被转义而不是把行撑成十列。
每条正式断言旁边配「已知坏样本」要求谓词变红；坏样本只计数、不进正式判决。
"""
import io
import os
import sys
# 兜住 GBK 控制台／重定向：这份报告的判决行里有 ⇒ 与中文，locale 编码下打印它们会让
# 进程恰好崩在"打印结论那一行"上——rc=1 长得像"闸门判红"，其实是量具自己没跑完
# （2026-10-09T18:24Z 实测：`> 文件` 时本文件即如此，接终端却全绿）。判据一行没动。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

QZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QZ)
import exp_veil_paint as EXP

fails = []
ran = [0]
bs = [0]


def check(desc, cond, detail=""):
    ran[0] += 1
    if "坏样本" in desc or "恒 0" in desc:
        bs[0] += 1
    print(("  OK   " if cond else "  FAIL ") + desc + ("" if cond else " ｜ " + str(detail)[:160]))
    if not cond:
        fails.append(desc)


print("== add_row：行宽闸门 ==")
r = []
EXP.add_row(r, "Acrylic", 1, "idle|focus|normal|count|0|0", "C0 出厂", 100.0, 3.0, 250.0, 100.0, 103.0)
check("九个值能写进行", len(r) == 1 and len(r[0]) == 9, r)
try:
    EXP.add_row([], "Acrylic", 1, "idle", "C0", 1.0, 2.0, 3.0, 4.0)      # 少一个（老式八元组的形状）
    check("少一个值必须抛（不许整列错位）", False, "没抛")
except RuntimeError as e:
    check("少一个值必须抛（不许整列错位）", "行宽" in str(e), str(e)[:80])
try:
    EXP.add_row([], "A", 1, "s", "C0", 1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    check("多一个值也必须抛", False, "没抛")
except RuntimeError:
    check("多一个值也必须抛", True)

print("== classify：四种「为什么没数」分家 ==")
check("全有行 ⇒ rc=0", EXP.classify(12, [], False) == 0)
check("零行＋没环境打断 ⇒ rc=1（量具/页面 ABORT，重试没意义）", EXP.classify(0, ["Acrylic", "Mica"], False) == 1)
check("零行＋环境打断 ⇒ rc=4（该重来）", EXP.classify(0, ["Acrylic", "Mica"], True) == 4)
check("部分行＋环境打断 ⇒ rc=4（优先按环境处理）", EXP.classify(4, ["Mica"], True) == 4)
check("部分行＋无环境 ⇒ rc=2（PARTIAL，别再整趟烧桌面）", EXP.classify(8, ["Mica"], False) == 2)
# 坏样本：如果 classify 被写成"永远 0"，上面五条必须见红
_fake = lambda n, m, e: 0
check("N-classify 坏样本（恒 0）会被这五条抓住",
      any(_fake(0, ["A"], True) != EXP.classify(0, ["A"], True) for _ in [0]), "谓词失效")

print("== verdict：判读规则 + 负对照 + 环带 ==")
rows_ok = [
    ("Acrylic", 1, "idle|focus|normal|count|0|0", "C3 页面全放开", 120.0, 180.0, 250.0, 30.0, 210.0),
    ("Mica", 1, "idle|focus|normal|count|0|0", "C3 页面全放开", 100.0, 1.0, 240.0, 99.5, 100.5),
    ("不透参照", 1, "idle|focus|normal|count|0|0", "C3 页面全放开", 150.0, 200.0, 250.0, 50.0, 250.0),
]
v = EXP.verdict(rows_ok)
check("C3 反应 ≥20 ⇒ 点名候选 C", any("候选 C" in x and "Acrylic" in x for x in v), v)
check("Mica 负对照 ≈0 时不降级", not any("负对照" in x for x in v), v)
bad_mica = list(rows_ok)
bad_mica[1] = ("Mica", 1, "idle", "C3 页面全放开", 100.0, 170.0, 240.0, 15.0, 185.0)
check("N-mica 坏样本（Mica 大反应）⇒ 必须出现降级句",
      any("负对照 Mica" in x for x in EXP.verdict(bad_mica)), "没降级")
zero = [("Acrylic", 1, "idle", "C3 页面全放开", 100.0, 0.4, 250.0, 99.8, 100.2)]
check("反应 ≤5 ⇒ 候选 A/B", any("候选 A/B" in x for x in EXP.verdict(zero)), zero)
mid = [("Acrylic", 1, "idle", "C3 页面全放开", 100.0, 11.0, 250.0, 94.5, 105.5)]
check("中间档 ⇒ 两条都没被排除（不许擅自归边）",
      any("两条候选都没被排除" in x for x in EXP.verdict(mid)), mid)
ringbad = [("Acrylic", 1, "idle", "C3 页面全放开", 100.0, 180.0, 8.0, 10.0, 190.0)]
check("环带反应 <30 ⇒ 点名该行", any("环带反应不足" in x for x in EXP.verdict(ringbad)), ringbad)
twostate = [rows_ok[0], ("Mica", 2, "idle|focus|normal|count|1|0", "C3 页面全放开", 1.0, 0.0, 240.0, 1.0, 1.0)]
check("页面态指纹不止一个 ⇒ 点名不许跨态配对", any("页面态指纹" in x for x in EXP.verdict(twostate)), twostate)
check("N-state 坏样本（全同行同态）不许报这句",
      not any("页面态指纹" in x for x in EXP.verdict([rows_ok[0], rows_ok[1]])), "误报")

print("== 报告：表头与行必须同宽，缺档必须留字 ==")
tmp = os.path.join(os.environ["TEMP"], "veil_report_check.md")
EXP.REPORT = tmp
EXP.write_report(rows_ok, "（离线体检造的假行，不是实测）", [(2, "Acrylic：屏幕 DC 采不动：测试")],
                 {"Acrylic": rows_ok[0:1], "Mica": rows_ok[1:2]})
txt = io.open(tmp, encoding="utf-8").read()
head = [l for l in txt.splitlines() if l.startswith("| 材质")]
sep = [l for l in txt.splitlines() if l.startswith("|---")]
body = [l for l in txt.splitlines() if l.startswith("| Acrylic") or l.startswith("| Mica")
        or l.startswith("| 不透参照")]
check("报告里表头/分隔行/数据行都在（缺任何一行下面不许多跑）",
      bool(head) and bool(sep) and bool(body), (head, sep, body))
if not (head and sep and body):
    print("\nOFFLINE-CHECK ABORT：表格结构没出来，后面的列宽检查不做")
    sys.exit(1)
ncols = len(head[0].replace("\\|", "§").strip().strip("|").split("|"))


def cells(line):
    # 先摘掉转义过的 \|，否则"页面态里带竖线"这种真错误会让计数虚高、检查反而变绿
    return line.replace("\\|", "§").strip().strip("|").split("|")


check("表头列数 == ROW_COLS", ncols == len(EXP.ROW_COLS), "%s vs %s" % (ncols, EXP.ROW_COLS))
check("分隔行列数 == 表头（首格不许是空的 ||---）",
      len(cells(sep[0])) == ncols and not sep[0].startswith("||"), sep)
check("每行列数 == 表头（页面态带竖线也必须齐 9 列）",
      all(len(cells(l)) == ncols for l in body), [len(cells(l)) for l in body])
check("带竖线的页面态被转义而不是拆列", any("\\|focus\\|" in l for l in body), body)
check("反应/环带两列带符号", any("+180.0" in l and "+250.0" in l for l in body), body)
check("环境打断另立一节，且明说『不是材质没反应』",
      "环境打断记录" in txt and "不是**材质对这些档没有反应" in txt, txt[-400:])
EXP.write_report([], "（假）", [], {"Acrylic": [], "Mica": [], "不透参照": []})
t2 = io.open(tmp, encoding="utf-8").read()
check("空表写『一行都没有』＋缺档点名", "一行都没有" in t2 and "缺整条材质的行" in t2, t2[-300:])

print("== 环境/量具分工：源码形状 ==")
src_of = __import__("inspect").getsource
one = src_of(EXP.one_field)
check("one_field 的采集失败转 EnvUnavailable（两处 grab 共用一个 try）",
      "EnvUnavailable" in one and one.count("G.grab") == 2, one)
mat = src_of(EXP.one_material)
import ast


def re_raiser(src):
    """结构检查而不是数字符：每一处「接住 EnvUnavailable」的 except 都必须①单独接（不许和
    RuntimeError 并成一条——并起来就等于环境/量具又分家失败了）②往上 Raise。
    用 AST 是因为上一版按前 80 字符判，注释一长就飘红/飘绿，测的是排版不是语义。"""
    hits = 0
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Try):
            continue
        for h in node.handlers:
            t = h.type
            names = []
            if isinstance(t, ast.Tuple):
                names = [getattr(e, "id", getattr(e, "attr", "")) for e in t.elts]
            elif t is not None:
                names = [getattr(t, "id", getattr(t, "attr", ""))]
            if "EnvUnavailable" not in names:
                continue
            hits += 1
            if len(names) > 1:
                return False
            if not any(isinstance(s, ast.Raise) for s in h.body):
                return False
    return hits > 0


n_env = len([1 for node in ast.walk(ast.parse(mat))
             if isinstance(node, ast.Try) for h in node.handlers
             if "EnvUnavailable" in (getattr(h.type, "id", "") if h.type else "")])
check("one_material 的 %d 处 except EnvUnavailable 全部单独接＋往上抛" % n_env, re_raiser(mat), mat)
check("N-swallow 坏样本（把环境异常就地吞掉）必须让这条变红",
      re_raiser("def f():\n    try:\n        x=1\n    except EnvUnavailable:\n        print('这一轮没数')\n") is False)
check("N-catchall 坏样本（Env 与 RuntimeError 合并一条 except）必须让这条变红",
      re_raiser("def f():\n    try:\n        x=1\n    except (EnvUnavailable, RuntimeError):\n        raise\n") is False)
check("N-none 坏样本（一处都不接 EnvUnavailable ⇒ 环境异常会崩穿）也算红",
      re_raiser("def f():\n    return 1\n") is False)
check("one_material 仍保留量具类 ABORT 只点名（不重试）",
      "这一轮的数不进报告" in mat and "except (RuntimeError, G.CDPAttach)" in mat)
mn = src_of(EXP.main)
check("main 里场窗只在最后收（同进程重建 Field 会串色，重跑绝不拆它）",
      mn.index("G._FLD.stop()") > mn.index("for sw in range(1, SWEEP_TRIES + 1)"), mn)
check("capture_canary 同时问解锁与屏幕 DC",
      "desktop_ready" in src_of(EXP.capture_canary) and "shot(0, 0, 64, 64" in src_of(EXP.capture_canary))
print("== sweep 的重试语义（真调用，拿假 one_material 顶掉，不起窗） ==")
_real_canary, _real_mat = EXP.capture_canary, EXP.one_material
calls = []


def fake_mat(flag, glass, port, tag, rows, sw, env_wait_s=None):
    calls.append((tag, sw))
    EXP.add_row(rows, tag, sw, "idle|focus|normal|count|0|0", "C3 页面全放开",
                100.0, 180.0, 250.0, 10.0, 190.0)


EXP.capture_canary = lambda: (True, "假就绪")
EXP.one_material = fake_mat
acc = {}
env = EXP.sweep(1, acc)
check("第 1 趟：三种材质各跑一次", env is None and [t for t, _ in calls] == ["Acrylic", "Mica", "不透参照"], calls)
check("第 1 趟：acc 里每种材质都有行", all(len(acc[t]) == 1 for t in acc), acc)
calls = []
env = EXP.sweep(2, acc)
check("第 2 趟：已经全了 ⇒ 一次都不重跑（不许白烧解锁窗口）", env is None and calls == [], calls)
calls = []


def half_mat(flag, glass, port, tag, rows, sw, env_wait_s=None):
    calls.append((tag, sw))
    if tag == "Mica":
        raise EXP.EnvUnavailable("采集失败（场=白）：假 gle=6")
    EXP.add_row(rows, tag, sw, "idle", "C3 页面全放开", 100.0, 180.0, 250.0, 10.0, 190.0)


EXP.one_material = half_mat
acc = {}
env = EXP.sweep(1, acc)
check("环境打断 ⇒ sweep 返回原因字符串（不是 None）", isinstance(env, str) and "Mica" in env, env)
check("打断前跑成的材质留在 acc（补齐而不是全推倒）",
      sorted(acc) == ["Acrylic"], acc)
calls = []
EXP.one_material = fake_mat
env = EXP.sweep(2, acc)
check("第 2 趟只补还缺的两档", env is None and [t for t, _ in calls] == ["Mica", "不透参照"], calls)
EXP.START_T = __import__("time").time() - (EXP.WALL_BUDGET + 10)
calls = []
env = EXP.sweep(3, {})
check("墙钟用尽 ⇒ 不开新窗并交回环境原因", env is not None and calls == [], env)
EXP.START_T = __import__("time").time()
EXP.capture_canary, EXP.one_material = _real_canary, _real_mat

print("== 金丝雀在锁屏下的真实回答 ==")
ok, why = EXP.capture_canary()
check("锁屏时金丝雀必须说『不能采』（它若恒真，整条 ENV 链就是装饰）",
      ok is False or EXP.M5.desktop_ready()[0] is True, why)
print("     现场：%s ｜ 剩余预算 %.0f 秒" % (why, EXP.budget_left()))
check("WALL_BUDGET 比看门狗 RUN_TIMEOUT 小（留余量）",
      EXP.WALL_BUDGET + 300 <= 2100, EXP.WALL_BUDGET)

print("== 看门狗 decide()：什么时候才许再烧一回真实解锁窗口 ==")
import watch_veil as WV
check("0 FULL ⇒ 不再重试", WV.decide(0, [4])[0] is False, WV.decide(0, [4]))
check("4 ENV-BLOCKED ⇒ 重试正当", WV.decide(4, [])[0] is True, WV.decide(4, []))
check("3 REFUSE ⇒ 重试且冷却够长（不抢别人的场窗）",
      WV.decide(3, [])[0] is True and WV.decide(3, [])[1] >= 120, WV.decide(3, []))
check("2 PARTIAL 第二回 ⇒ 停（量具的事，重试洗不出对的答案）", WV.decide(2, [2])[0] is False)
check("1 EMPTY-INSTRUMENT 第二回 ⇒ 停", WV.decide(1, [1])[0] is False)
check("2 PARTIAL 第一回 ⇒ 只再给一回", WV.decide(2, [4])[0] is True)
check("-1 超时连着两回 ⇒ 停", WV.decide(-1, [-1])[0] is False)
check("未知 rc ⇒ 停，不猜", WV.decide(99, [])[0] is False, WV.decide(99, []))
_always = lambda rc, hist: (True, 60, "恒重试")
check("N-always 坏样本（恒重试的看门狗）会被上面这组抓住",
      any(_always(r, h)[0] != WV.decide(r, h)[0]
          for r, h in [(0, [4]), (2, [2]), (1, [1]), (-1, [-1]), (99, [])]), "谓词失效")
check("ATTEMPT_TIMEOUT ≥ 实验墙钟＋余量（否则看门狗会把正常跑当成超时）",
      WV.ATTEMPT_TIMEOUT >= EXP.WALL_BUDGET + 300, (WV.ATTEMPT_TIMEOUT, EXP.WALL_BUDGET))
check("MAX_TRIES × 一回上限 < 看门狗总时限（否则最后一回必然被截）",
      WV.MAX_TRIES * (WV.ATTEMPT_TIMEOUT + 120) < WV.DEADLINE_S,
      (WV.MAX_TRIES, WV.ATTEMPT_TIMEOUT, WV.DEADLINE_S))
check("看门狗不自己抄解锁判据（全场只许一份）",
      "OpenInputDesktop" not in src_of(WV.main) and "desktop_ready()" in src_of(WV.main))

print("\nOFFLINE-CHECK %s（%d 条，其中坏样本对照 %d 条，失败 %d）"
      % ("ALL-OK" if not fails else "FAIL", ran[0], bs[0], len(fails)))
for f in fails:
    print("  -", f)
sys.exit(0 if not fails else 1)
