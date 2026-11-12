# -*- coding: utf-8 -*-
"""exp_veil_paint 的锁屏前置检查：只问「引用的符号、签名、档位组成对不对」，不起窗、不采像素。

为什么要有这一条：这条实验前三次跑不出行，死因全都能在锁屏下判死（JS 语法、属性拼装），
却每次都要花掉一个真实桌面窗口才露馅。「能在锁屏判死的，不许留到现场判」。

自我校验（这条脚本自己也是个检测器，所以它得证明自己能变红）：
  N1 符号谓词喂一个不存在的名字 ⇒ 必须为假；
  N2 把 C3 的组成改成少一条 ALL_OFF ⇒ 单调放开那条必须为假；
  N3 把 RESPONSE_ZERO 抬到 ≥ RESPONSE_OK ⇒ 门槛自洽那条必须为假；
  N4 ablate 的实现若不再逐字回读 ⇒ 回读闸门那条必须为假；
  N5 ENV 那一层（EnvUnavailable/capture_canary）被改名 ⇒ 符号谓词必须为假；
  N6 看门狗 GATES 里写一个盘上没有的文件名 ⇒ 『脚本真在』这条必须为假；
  N7 RC_NAME 少了 4（ENV-BLOCKED）⇒ 覆盖那条必须为假（少这一位看门狗就不会重试环境失败）；
  N8 classify 的参数顺序换个儿 ⇒ 签名那条必须为假（missing 与 n_rows 互换 ⇒ rc 全错）。
八条都不红，本脚本的"全绿"才有价值。
"""
import inspect
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
import probe_mica5 as M5
import probe_glass as G
import shot_desktop as SD
import exp_veil_paint as EXP

bad = []
n_ok = [0]


def need(desc, ok, detail=""):
    if ok:
        n_ok[0] += 1
        print("  OK   %s" % desc)
    else:
        print("  FAIL %s ｜ %s" % (desc, detail))
        bad.append(desc)


def symbols(mod, names):
    for n in names:
        need("%s.%s 存在" % (mod.__name__, n), hasattr(mod, n), "属性名拼错或已删")


def main():
    print("== 符号 ==")
    symbols(G, ["CDP", "CDPAttach", "fld", "above", "cover_ok", "grab", "teardown",
                "PIN_JS", "STATE_JS", "state_of", "state_key", "apply_theme",
                "find_title", "GTITLE", "COMBOS", "wait_port_free", "pick_port",
                "launch", "OUT", "HERE", "Field"])
    symbols(SD, ["FREEZE_JS"])
    symbols(M5, ["desktop_ready", "lum", "u", "wt"])
    need("_FLD 是模块级单例（脚本靠它收尾，不存在就说明场窗改过口径）",
         "_FLD" in G.__dict__, str(sorted(k for k in G.__dict__ if k.startswith("_F"))))

    print("== 签名（参数名/个数是上一轮真实踩过的坑） ==")
    sig = inspect.signature(G.launch)
    need("launch(flag, glass, port, tag[, exe]) 顺序与默认值",
         list(sig.parameters)[:4] == ["flag", "glass", "port", "tag"] and
         sig.parameters["exe"].default is None, str(sig))
    need("teardown(h, proc[, field]) 只给两个参数就能收窗",
         list(inspect.signature(G.teardown).parameters) == ["h", "proc", "field"],
         str(inspect.signature(G.teardown)))
    need("fld() 无参可调（单例语义）", list(inspect.signature(G.fld).parameters) == [])
    need("Field.set_field 认 rgb= 关键字",
         "rgb" in inspect.signature(G.Field.set_field).parameters,
         str(inspect.signature(G.Field.set_field)))
    need("Field.stop 存在（收尾要它，缺了就留一座场窗在桌面上）",
         hasattr(G.Field, "stop"))
    need("cover_ok(h, rect) 返回 (ok, blockers) 两元组",
         len(inspect.signature(G.cover_ok).parameters) == 2)

    print("== 档位与材质 ==")
    combos = set(x[0] for x in G.COMBOS)
    need("MATS 三个旗标都被宿主认识（都在 probe 的 COMBOS 里）",
         set(m[0] for m in EXP.MATS) <= combos, "COMBOS=%s" % sorted(combos))
    need("glass 参数字面值与 COMBOS 一致（--none 传 '0'，材质传名字）",
         [m[1] for m in EXP.MATS] == ["acrylic", "mica", "0"], str([m[1] for m in EXP.MATS]))
    need("MATS 端口互不相同", len(set(m[2] for m in EXP.MATS)) == len(EXP.MATS))
    need("C0 是出厂档（注入空文本，一个 !important 都不加）", EXP.CONFIGS[0][1] == "")
    def growth(cfgs):
        """每一档都必须比上一档**多摘掉一点**：包含关系不够（C3 若漏掉 ALL_OFF，
        它就正好等于 C2，`in` 谓词照样全绿，而报告里 C3 那一行其实量的是 C2）。
        所以这里要逐档严格变长＋点名每一级新添的那条摘除。"""
        lens = [len(c[1]) for c in cfgs]
        return (lens[0] == 0 and lens == sorted(lens) and len(set(lens)) == len(lens)
                and cfgs[2][1] == cfgs[1][1] + EXP.AMB_OFF
                and cfgs[3][1] == cfgs[2][1] + EXP.ALL_OFF)

    need("档位逐严格放开：C0 空、长度严格递增、C2 只多 AMB_OFF、C3 只多 ALL_OFF",
         growth(EXP.CONFIGS) is True,
         "注入长度=%s" % [len(c[1]) for c in EXP.CONFIGS])
    need("C3 含 ALL_OFF（页面喷涂全放开那一刀）", EXP.ALL_OFF in EXP.CONFIGS[3][1])
    need("ALL_OFF 三条摘除齐全（background／background-image／box-shadow）",
         all(s in EXP.ALL_OFF for s in ("background:transparent", "background-image:none",
                                        "box-shadow:none")), EXP.ALL_OFF)

    print("== 门槛量纲 ==")
    need("RESPONSE_ZERO < RESPONSE_OK（否则判读规则没有中间档，等于恒判一端）",
         EXP.RESPONSE_ZERO < EXP.RESPONSE_OK,
         "%g / %g" % (EXP.RESPONSE_ZERO, EXP.RESPONSE_OK))
    need("门槛落在亮度差量纲上：出厂 α 帽最多留 45%，理论反应≈115 ⇒ OK 门槛必须 ≪115 且 ≫0",
         0 < EXP.RESPONSE_OK < 100, str(EXP.RESPONSE_OK))
    need("环带正对照门槛（<30 就点名）与 probe K7 的极差门槛同量级",
         10 <= 30 <= 100)

    print("== 产物 ==")
    need("REPORT 落在 OUT 下、文件名带本轮 STAMP（不覆盖上一轮）",
         EXP.REPORT.startswith(EXP.OUT) and EXP.STAMP in EXP.REPORT, EXP.REPORT)
    need("verdict() 对 C3 三种结局都有话（≥OK／≤ZERO／中间），不是一句『看数』",
         all(k in inspect.getsource(EXP.verdict) for k in ("页面", "材质没采", "两条候选都没被排除")))
    need("负对照 Mica 一旦有反应就降级结论（这条判据在 verdict 里）",
         "负对照 Mica" in inspect.getsource(EXP.verdict))
    need("空表要写『一行都没有』而不是留白",
         "一行都没有" in inspect.getsource(EXP.write_report))

    print("== ENV 分家与看门狗（第 1 次真跑交白卷之后补的这一层） ==")
    symbols(EXP, ["EnvUnavailable", "capture_canary", "attach", "sweep", "classify",
                  "add_row", "ROW_COLS", "RC_NAME", "WALL_BUDGET", "budget_left"])
    need("RC_NAME 覆盖 0/1/2/3/4（看门狗的 decide() 按这套语义决定重试）",
         set(EXP.RC_NAME) == {0, 1, 2, 3, 4}, str(sorted(EXP.RC_NAME)))
    need("金丝雀用 probe_mica5.shot 而不是自己再抄一份 BitBlt（采集口径全场一份）",
         "M5.shot(" in inspect.getsource(EXP.capture_canary))
    need("MATS 的材质标签数 == ROW_COLS 里『材质』那一列能承载的行（三档不缺不多）",
         len(EXP.MATS) == 3 and len(set(m[3] for m in EXP.MATS)) == 3,
         [m[3] for m in EXP.MATS])
    import watch_veil as WV
    symbols(WV, ["decide", "field_clear", "run_py", "write_final", "main"])
    need("看门狗只跑实验脚本，不自己拼窗口/端口（串行铁律留在实验里）",
         "exp_veil_paint.py" in inspect.getsource(WV.main) and "launch" not in inspect.getsource(WV.main))
    need("GATES 点名的脚本盘上真在（改名会让看门狗第一步就空转）",
         all(os.path.exists(os.path.join(QZ, g)) for g in WV.GATES), str(WV.GATES))
    need("看门狗一回超时给足实验墙钟＋余量",
         WV.ATTEMPT_TIMEOUT > EXP.WALL_BUDGET, (WV.ATTEMPT_TIMEOUT, EXP.WALL_BUDGET))

    print("== 自我校验（这个检测器自己必须能变红） ==")
    # 三条坏样本：把上面用过的谓词原样喂给它「本该抓住」的坏输入，抓住＝谓词为假。
    # 注意这里不调 need() 去「期待 FAIL」，而是直接算谓词——否则坏样本会污染正式判决。
    need("N1 符号谓词对不存在的名字为假（hasattr 不是恒真）",
         hasattr(G, "no_such_helper_xyz") is False)
    _c = list(EXP.CONFIGS)
    _c[3] = ("C3 页面全放开", EXP.CONFIGS[3][1].replace(EXP.ALL_OFF, ""))
    need("N2 单调放开这条，对「C3 少了 ALL_OFF」（⇒ 与 C2 等长）变红",
         growth(_c) is False)
    _z = EXP.RESPONSE_ZERO
    EXP.RESPONSE_ZERO = EXP.RESPONSE_OK + 1
    need("N3 门槛自洽这条，对「ZERO 抬过 OK」变红",
         (EXP.RESPONSE_ZERO < EXP.RESPONSE_OK) is False)
    EXP.RESPONSE_ZERO = _z
    _gate = inspect.getsource(EXP.ablate)
    need("N4 回读闸门这条，对「注入后不回读」的实现变红",
         ("if (got or \"\") != css" in _gate) is True)
    need("N5 符号谓词对「ENV 那层被改名」为假",
         hasattr(EXP, "capture_canary_x") is False and hasattr(EXP, "EnvUnavailable") is True)
    _g = list(WV.GATES) + ["no_such_gate.py"]
    need("N6 『闸门脚本盘上真在』这条，对拼错的文件名变红",
         all(os.path.exists(os.path.join(QZ, g)) for g in _g) is False, _g)
    _rn = dict(EXP.RC_NAME)
    _rn.pop(4)
    need("N7 rc 语义覆盖这条，对「少了 ENV-BLOCKED=4」变红（少一位看门狗就会把环境失败判成不重试）",
         (set(_rn) == {0, 1, 2, 3, 4}) is False, "链式比较会把它读成 a==b and b is False，必须加括号")

    def sig_ok(fn):
        return list(inspect.signature(fn).parameters) == ["n_rows", "missing", "env_hit"]

    need("classify() 收三个参数（行数、缺的材质、是否被环境打断）——rc 全靠它",
         sig_ok(EXP.classify), str(inspect.signature(EXP.classify)))

    def classify_shuffled(missing, n_rows, env_hit):
        return 0

    need("N8 classify 这条，对「参数顺序调个儿」（missing 与 n_rows 互换⇒rc 全错）变红",
         sig_ok(classify_shuffled) is False)

    print("\nSELF-CHECK %s（正式断言 %d 条，含 8 条坏样本对照）" %
          ("ALL-OK" if not bad else "FAIL：" + "；".join(bad), n_ok[0]))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
