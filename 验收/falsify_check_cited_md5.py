# -*- coding: utf-8 -*-
"""给 check_cited_md5.py 做证伪：往说明文档的副本里逐条注**合理**的手抄 bug（条数不在这里写死，它一涨这句就滞后——实际条数看本脚本打印的总数），
要求每一条都把体检变红、并且红话里点到受影响那一条的标签；点不到名的算 CRASH 不算抓到。

用法：
  PYTHONIOENCODING=utf-8 python 验收\\falsify_check_cited_md5.py
  PYTHONIOENCODING=utf-8 python 验收\\falsify_check_cited_md5.py <说明.md> <check_cited_md5.py>

三条闸门（缺一条这个证伪器就只是自说自话）：
1) 每个注入必须**真的改到文本**——目标子串找不到就报 NOP 并算失败（防"注了个寂寞"）；
2) 干净副本必须先 rc=0（否则"每条都变红"可能只是它本来就全红）；
3) 假阳性对照：只做不涉及被钉量的文字改动／往围栏里再抄一遍同一个真哈希，
   体检必须仍然 rc=0（防"什么都判红"）；另有一条 C 专门对着第 8 条尺子——把盘上**真有**的
   带戳产物名在围栏里再点一遍名、并带上一个 `window-<轮>-…` 模板，也必须仍然 rc=0
   （防"重复点名就红"和"模板被当成断链"）。
4) 另有四条**边界哨兵**（`SENTINELS`，独立记账、不并进 CAUGHT）：一条要求"把 2427 字节补进
   文档"必须**变红**（＝那条近漂守卫确实还有效，文档才敢把那一格留空）；一条要求"文档通篇把
   `_cmp6x2.py` 改成盘上没有的名字"**仍然 rc=0**（＝交底：这条尺钉的是它自己写下的路径，
   不绑正文里的文件名；哪天它开始绑，退休的是这条哨兵，不是判据）。
副本一律写进 %LOCALAPPDATA%\\fq-glass-verify，交付目录不落变异件。
"""
import io
import os
import subprocess
import sys

# 见 check_cited_md5.py 里同一段注释：GBK 控制台下打印 ⇒ 与被测脚本 tail 里的 U+FFFD
# 会在"打印 CAUGHT/PASS 的那一行"崩掉，rc=1 会被误读成"抓到变异"。这里兜住，
# 让证伪器的红只可能来自断言，不来自编码。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
SRC = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, u"原生玻璃版-说明.md"))
CHECK = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "check_cited_md5.py")
OUT_DIR = os.path.join(os.environ["LOCALAPPDATA"], "fq-glass-verify")
PROBE = os.path.join(OUT_DIR, "_cited_md5_probe.md")
if not os.path.isfile(CHECK):
    raise SystemExit("REFUSE：找不到体检脚本 %s" % CHECK)

FULL = "b6c667ff2f8e3d3b4e5762892e1b8a7f"
BASE = io.open(SRC, encoding="utf-8").read()

MUTS = [
    # (名字, 标签（红话里必须点到的字样）, old, new)
    (u"full32 抄漏一位", u"原型日志留底副本", FULL, FULL[:-1] + "e"),
    (u"前缀截太短", u"实拍量具", "eae724f4c3c037e0", "eae724"),
    (u"旧页面哈希末位漂一位", u"旧页面锚点", "2a66cf56fd40", "2a66cf56fd41"),
    (u"字节数漂一位", u"原型日志留底副本", u"17411 字节", u"17412 字节"),
    # 落盘日凭印象写错的那一类：钟点对、日期差一天（本轮真踩过）
    (u"stamp 日期漂一天", u"原型日志留底副本", u"2026-10-07T06:15:10Z", u"2026-10-08T06:15:10Z"),
    # 看门狗期限：抄错一小时，体检必须按最新那份 watcher 日志的首行算回来
    # （这一串的出处会随重挂漂移：现在盘上那份日志算出来的是 2026-10-10T06:44:06Z；
    #   若又重挂一趟，这条锚跟着文档改，别把判据改松）
    (u"看门狗期限抄错一小时", u"看门狗期限", u"2026-10-10T06:44:06Z", u"2026-10-10T07:44:06Z"),
    (u"订正过的手抄值漂回来", u"陈旧值", u"底色差 `+230.8`", u"底色差 `+230.8`（旧稿写作 `+231`）"),
    # 后登记的 #37 量具那份（没有带戳的留底文件名，只有正文里的 mtime）：日期漂一天，
    # 体检必须发现"盘上那个 ISO 在文档里根本不存在"＋"同钟点不同日期"这两条之一。
    (u"实验量具 mtime 漂一天", u"机制分拣量具", u"2026-10-09T17:10:04Z", u"2026-10-10T17:10:04Z"),
    # 文档里那句"§5b 出没出数"同样是手抄状态句：出数之后，把状态改回"没出数"这一刀
    # 必须被「消融断言」判红（盘上那份报告数得出十二行）。
    # 上一版这条打的是"把点名的最新那份换成旧那份"，那条形状现在**打不响**了：
    # 体检里"自称没出数才检查点名"这一支只在 _claims 为真时开火，而文档已经出数 ⇒ 走不到。
    # MISSED 不许靠放宽判据来救，所以把变异改成它要注的那件事本身的真形状（状态句漂回旧状态）。
    (u"已出数的状态句漂回「没出数」", u"消融断言", u"**§5b 已经出数并判完**",
     u"**§5b 目前 0 行真数据**"),
    # 第 10 条：#37 那把尺的字节数漂一位。这条和 M8 同属一个 CITED 条目但形状不同
    # （一个动 mtime、一个动 size），标签都写「机制分拣量具」＝点名到受影响那一条。
    (u"实验量具字节数漂一位", u"机制分拣量具", u"23293 字节", u"23294 字节"),
    # 第 11、12 条管 #37 的「现场句」：文档说这次实验跑到哪一步了，也是手抄状态。
    # 11＝把点名的一份旧 FINAL 换成格式合理、盘上没有的（该由「#37 现场引用」红，
    #     且只有引用那条响——最新那份仍在正文里被点名，新鲜度不该跟着报警）；
    # 12＝把正文里**最新那份**（`FINAL-veil-20261009T224406Z.md`）的点名整篇换成一句大白话，
    #     盘上那份还在而文档不再点名它（该由「#37 现场断言」红——两条红话前缀分得开）。
    (u"FINAL 名换成盘上没有的（整篇）", u"#37 现场引用", u"FINAL-veil-20261009T165216Z.md",
     "FINAL-veil-20261009T170000Z.md", -1),
    (u"最新那份 FINAL 的点名整篇改成大白话", u"#37 现场断言", u"FINAL-veil-20261009T224406Z.md",
     "那份 FINAL 报告", -1),
    # 第 13—15 条管新收的**第 8 条通用尺**（凡反引号点名、名字带紧凑 UTC 戳的产物要在盘上逐字符数得出）。
    # 13＝本轮真抓到的那一形状：留底 stdout 的秒位漂一秒（扩展名／日期／时长全对，同族里还躺着隔壁那份）
    #     ⇒ 必须红，且不许被"同族兜底"洗绿；
    # 14＝把 #40 那把尺的 mtime 日期漂一天（这条 CITED 只钉 md5＋mtime，字节数按文件头那条已知碰撞不钉）；
    # 15＝点名一份格式合理、盘上没有的 #40 报告（＝凭印象编 stamp 的那一类）。
    (u"留底 stdout 秒位漂一秒", u"带戳产物名引用",
     u"backdrop-source-run-20261010T002025Z.log", u"backdrop-source-run-20261010T002024Z.log", -1),
    (u"#40 量具 mtime 漂一天", u"屏位来源量具", u"2026-10-10T00:20:06Z", u"2026-10-11T00:20:06Z", -1),
    (u"#40 报告名编一个格式合理的戳", u"带戳产物名引用",
     u"backdrop-source-20261010T164513Z.md", u"backdrop-source-20261010T164599Z.md", -1),
    # 第 16 条＝期限那条的**近漂族**变异：只漂三处手抄里的**一处**（另两处顶着现算值，
    # 旧版"存在即绿"就是从这里漏的；补了"同日期同分秒只差小时"那把尺之后必须点名）。
    # 与 M6 的分工：M6 改的是"文档不再出现现算值"（ Presence 那条红），这条只改一处、
    # 现算值仍在正文里 ⇒ 只有近漂族那把尺会红，两条红话前缀同为「看门狗期限」但句子不同。
    (u"期限三处手抄漂一处", u"只差小时", u"期限至 **2026-10-10T06:44:06Z**",
     u"期限至 **2026-10-10T07:44:06Z**", 1),
    # 第 17—24 条管**这一轮新登记的 ④⑤ 出处清单**（17 行，全在 CITED 里）。
    # 每条都注在这一批真抄过的数上，标签＝受影响那一条在 CITED 里的原样标签。
    (u"⑤ 批 3 留底 md5 末位漂一位", u"⑤ 批 3 留底", "016c7e208843", "016c7e208842", 1),
    # 相邻两行抄串行＝这一批表里最容易发生的一种（两个 12 位串长得几乎一样）：
    # 把批 3 那格换成批 4 的真 md5 ⇒ 批 3 必须红，而批 4 该继续绿（值本身没错）。
    (u"⑤ 批 3／批 4 两行 md5 抄串行", u"⑤ 批 3 留底", "016c7e208843", "2e860131d1a3", 1),
    (u"⑤ 调度器日志字节数漂一位", u"⑤ 调度器日志", u"779 字节", u"778 字节", 1),
    (u"④ 比较器落盘日漂一天", u"④ 比较器", u"2026-10-10T17:56:03Z", u"2026-10-09T17:56:03Z", 1),
    # 同一个值抄两遍、只漂一处（正文一次＋表一次）＝"存在即绿"那类漏网的形状，
    # 新登记的行里 ⑤ 同状态对账 的 md5 与字节数各有两处，所以两条都单独打。
    (u"⑤ 同状态对账 md5 两处抄漂一处", u"⑤ 同状态对账", "36fcf9989c6e", "36fcf9989c6f", 1),
    (u"⑤ 同状态对账 字节两处抄漂一处", u"⑤ 同状态对账", u"2429 字节", u"2428 字节", 1),
    # 跨状态对账那格的 mtime 与上一行**同一秒**（两份输出同一次跑写出来的）。
    # 漂这一行会同时惊动两条尺子的近漂族——要求的只是点到本条标签，不去数它红几条。
    (u"⑤ 跨状态对账 mtime 漂一天", u"⑤ 跨状态对账", u"2026-10-10T18:12:59Z",
     u"2026-10-09T18:12:59Z", 1),
    # 新登记的产物名同样归第 8 条管：编一个格式合理、盘上没有的 FINAL 名（整篇换）
    # ⇒ 必须由「带戳产物名引用」红，而不是由 CITED 那一条红（那一条开的是自己写的路径）。
    (u"⑤ 交卷件名编一个盘上没有的", u"带戳产物名引用", u"FINAL-6x2-20261010T180219Z.md",
     u"FINAL-6x2-20261010T180299Z.md", -1),
    # 第 25—27 条管**这一轮新登记的 §8-⑥（#42）出处清单**。形状沿用上一批已经证明会咬的那三种：
    # size 近漂（同一个"N 字节"在正文与表里各抄一遍，只漂一处＝"存在即绿"那类漏网的形状）、
    # ISO 落盘时刻漂一天（同钟点不同日期＝凭印象写日期那一类）、点名一份格式合理但盘上没有的产物。
    # 标签＝受影响那一条在 CITED 里的原样标签；第 27 条的标签不是 CITED 那条，是第 8 条通用尺。
    (u"⑥ 自检量具字节数两处抄漂一处", u"#42 自检", u"17441 字节", u"17442 字节", 1),
    (u"⑥ 证伪回执 mtime 漂一天", u"#42 证伪回执", u"2026-10-11T15:52:14Z",
     u"2026-10-12T15:52:14Z", 1),
    (u"⑥ 交卷件名编一个盘上没有的", u"带戳产物名引用", u"FINAL-surface-20261011T155435Z.md",
     u"FINAL-surface-20261011T155499Z.md", -1),
    # 第 28—36 条管**§9 计时口径这一批**与**第 9 条历史值尺**。2026-10-15 起重写：
    # 这一批的期望值不再手抄在体检脚本里，而是由第 10 条**从文档 §9e 那张表现读**，
    # 所以锚一律取"表里那一行的相邻两格"这种整段形状，而不是单独一个裸数——同一个数
    # 在正文里可能另有出处（本轮 `10ee9a1f6252` 有 6 处，全是**旧页面留底**的身份证，
    # 不是当前页面），只漂一个裸串会打到别的那一行上：红是红了，归因却不是我说的那件事。
    # 形状仍沿用已经证明会咬的那三种：md5 末位漂、size 末位漂、落盘时刻漂一天（同钟点不同日期）。
    (u"9e 当前页面哈希末位漂一位", u"index.html〔9e〕",
     u"`index.html`（交付目录） | c1969a328e6a |", u"`index.html`（交付目录） | c1969a328e6b |", 1),
    (u"9e 当前页面字节数漂一位", u"index.html〔9e〕",
     u"| c1969a328e6a | 168430 字节 |", u"| c1969a328e6a | 168431 字节 |", 1),
    (u"9e 当前页面落盘时刻漂一天", u"index.html〔9e〕",
     u"168430 字节 | 2026-10-19T17:58:56Z |", u"168430 字节 | 2026-10-20T17:58:56Z |", 1),
    (u"9e 计时沙箱尺 md5 末位漂一位", u"timing_harness.js〔9e〕",
     u"| 33001ef082bd | 72272 字节 |", u"| 33001ef082be | 72272 字节 |", 1),
    (u"9e 计时证伪回执字节数漂一位", u"falsify-timing-20261015T170709Z.txt〔9e〕",
     u"| df38efc8e2b6 | 10118 字节 |", u"| df38efc8e2b6 | 10119 字节 |", 1),
    (u"9e 交卷回执落盘时刻漂一天", u"harness-after-20261015T182535Z.txt〔9e〕",
     u"| d6235efa6314 | 9389 字节 | 2026-10-15T18:25:35Z |",
     u"| d6235efa6314 | 9389 字节 | 2026-10-16T18:25:35Z |", 1),
    (u"9e 改动前快照字节数漂一位", u"index.html.before-glass.html〔9e〕",
     u"| 8385b362a8ab | 136081 字节 |", u"| 8385b362a8ab | 136082 字节 |", 1),
    # 第 35—37 条打的是**活台账新增的三种形状**：它以前只会"抄错一个数"，现在还要能抓
    # "那一格干脆没写""那一行少了一列""点名的文件根本不在盘上"——表形状一变，
    # 读表的那只手不能默默少几行然后照样报绿（"零行、全绿"就是这条尺的失明形状）。
    (u"9e 把 md5 那格掏空", u"这一行缺格",
     u"`index.html`（交付目录） | c1969a328e6a |", u"`index.html`（交付目录） |  |", 1),
    (u"9e 撕掉一列（这一行变成 4 格）", u"不是 5 格",
     u"| 33001ef082bd | 72272 字节 | 2026-10-15T18:25:02Z |",
     u"| 33001ef082bd 72272 字节 | 2026-10-15T18:25:02Z |", 1),
    (u"9e 点名的文件改成盘上没有的", u"表里点名的文件不在盘上",
     u"`js_syntax_check.js`（产物目录） | 3d67971ef4ef",
     u"`js_syntax_check9.js`（产物目录） | 3d67971ef4ef", 1),
    # 第 9 条那两枪：旧值不在盘上，能咬它的只有"与留底互不为前缀"和"与留底 bytes 不等"。
    (u"旧页面字节数与留底不等", u"旧页面锚点", u"139085 字节", u"139086 字节", 1),
    (u"计时回执名编一个盘上没有的", u"带戳产物名引用", u"truth-after-20261014T175555Z.txt",
     u"truth-after-20261014T175599Z.txt", -1),
]

# 两条**边界哨兵**：它们不是"要求抓到"的变异，是把这条尺子的两处口径变成机器可查的事实。
# 各自有独立记账，不许混进上面的 CAUGHT 数；结局反了＝口径变了＝这条必须重读判据再决定退休谁。
SENTINELS = [
    # S1（要求**红**，且红话点名）：`cmp6x2-b3b4.out` 2429 与 `cmp6x2-b2b4.out` 2427 是两个
    # 不同文件的相邻字节数。文档一旦把 2427 也写成"N 字节"，规则②（同长度只差末位＝漂）会
    # 把它当成"同一个值抄两遍漂了一处"⇒ 判红。这正是文档那一格"不钉字节"的理由，
    # 也是它不许被"放宽守卫"救掉的证据：守卫哪天被松开，这条哨兵就先变绿。
    ("S1 已知碰撞复现（要求红：近漂守卫仍有效）", "must-red", u"⑤ 同状态对账",
     BASE + u"\n```\n若把不钉的那格补全：3ca6541f7d98 ／ 2427 字节 ／ 2026-10-10T18:12:59Z\n```\n"),
    # S2（要求**绿**，即"这条尺看不见"）：④⑤ 三把尺的名字里不带紧凑 UTC 戳，第 8 条不认它们；
    # 而 CITED 打开的是**检查器自己写的路径**，不是文档正文那句文件名。所以把文档通篇
    # `_cmp6x2.py` 改成盘上没有的 `_cmp6x3.py`，体检仍然 rc=0。
    # 这条不是"抓到了什么"，是把"文档里的路径写法与这条尺不绑定"这件事钉在盘上：
    # 一旦哪天给它加了"文件名也要核对"的能力，这条会变红 ⇒ 那时该退休的是本条哨兵，不是判据。
    ("S2 覆盖边界（要求 rc=0：文档路径写法不绑 CITED）", "must-green", "",
     BASE.replace(u"_cmp6x2.py", u"_cmp6x3.py", -1)),
    # S3／S4 是一对**同一判据的两面**（2026-10-15 加，起因是近漂尺自己咬了一口假的）：
    # `FINAL-surface-…md` 盘上 2477 字节，而 §9e 那一轮新登记的 `js_syntax_check.js` 盘上 2470 字节——
    # 两个不同文件的相邻字节数被旧写法读成"同一个值抄两遍漂了一处"。修法不是放宽阈值，是**补前提**：
    # 一个近漂数要想不算漂移，必须回盘上找到归属（它是另一行的当前盘上值，那一行自己就印着
    # 那行的身份证，而且那一行的字节数是这条尺核过的）。S3 验豁免生效、S4 验豁免没被扩大成
    # "这数在盘上存在吗"——把豁免退化成那样时，b.out 那类"故意没核字节"的数也会跟着放行，
    # S1 就迟早变绿。两条一起才证明改的是判据、不是把守卫松开。
    ("S3 近漂有归属（要求 rc=0：跨文件引用不算漂移）", "must-green", "",
     BASE + u"\n```\n复核：`js_syntax_check.js` 3d67971ef4ef ／ 2470 字节（另一行自己印的、且那行核过字节）\n```\n"),
    ("S4 近漂没归属（要求红：这个数回盘上找不到出处）", "must-red", u"#42 批 4 交卷件",
     BASE + u"\n```\n顺手记一句：那趟的日志 2476 字节。\n```\n"),
]


def run(path):
    return subprocess.run([sys.executable, CHECK, path, REPO],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def main():
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    r = run(SRC)
    print("干净原件：rc=%s，输出末行 %s" % (r.returncode, (r.stdout or "").strip().split("\n")[-1][:80]))
    if r.returncode != 0:
        print("ABORT：原件就没过体检，先修体检或文档，别拿它当基线")
        return 2

    caught = skipped = nops = 0
    for m in MUTS:
        name, label, old, new = m[:4]
        cnt = m[4] if len(m) > 4 else 1   # -1＝整篇换（同一个值抄两遍时，只换一处注的是另一件事）
        if old not in BASE:
            print("NOP   %-26s 目标子串不在文档里，这条注入什么都没做＝不算抓到" % name)
            nops += 1
            continue
        n_occ = BASE.count(old)
        mutated = BASE.replace(old, new, cnt)
        if mutated == BASE:
            # 上一轮就是这么栽的：把 0 当"全换"用，str.replace 实际一处没换，
            # 于是"体检仍然绿"被读成"漏网"——空操作是变异本身失效，不是尺子失明。
            print("NOP   %-26s 注下去文本一个字没变（cnt=%s，盘上 %d 处）＝变异失效，不算抓到"
                  % (name, cnt, n_occ))
            nops += 1
            continue
        io.open(PROBE, "w", encoding="utf-8").write(mutated)
        rr = run(PROBE)
        out = (rr.stdout or "") + (rr.stderr or "")
        if rr.returncode != 0 and label in out:
            print("CAUGHT %-26s（红话点到「%s」；这一串文档里 %d 处，本次换法＝%s）"
                  % (name, label, n_occ, "整篇" if cnt < 0 else "只换第一处"))
            caught += 1
        elif rr.returncode != 0:
            print("CRASH  %-26s rc=%s 但归因不到标签「%s」→ 不算抓到" % (name, rr.returncode, label))
            skipped += 1
        else:
            print("MISSED %-26s 体检仍然 rc=0" % name)
            skipped += 1

    # 假阳性对照 A：只改不涉及被钉量的措辞
    benign_a = BASE.replace(u"已把原件按字节复制留底", u"已把原件按字节复制留存", 1)
    # 假阳性对照 B：往文末代码围栏里再抄一遍**真实**哈希与字节数（多写一遍不该变红）
    extra = u"\n```\n复核：md5 %s ／ 17411 字节 ／ 2a66cf56fd4040d62a406d4a6ef3ada7\n```\n" % FULL
    ok_a = ok_b = False
    if benign_a != BASE:
        io.open(PROBE, "w", encoding="utf-8").write(benign_a)
        ok_a = run(PROBE).returncode == 0
    else:
        print("NOP   假阳性对照 A 没改到东西")
    io.open(PROBE, "w", encoding="utf-8").write(BASE + extra)
    ok_b = run(PROBE).returncode == 0
    # 假阳性对照 C：把盘上**真有**的带戳产物名再点一遍名（第 8 条尺子不许因为"重复点名"报红，
    # 也不许因为文末围栏里的名字不在仓库根就报红——它就该在产物目录里数得出）。
    extra_c = u"\n```\n复核点名：`veil-paint-20261009T233341Z.md` ／ `FINAL-veil-20261009T224406Z.md`" \
              u" ／ `backdrop-source-20261010T164513Z.md` ／ `window-<轮>-20261009T000851Z.png`（模板不算）\n```\n"
    io.open(PROBE, "w", encoding="utf-8").write(BASE + extra_c)
    ok_c = run(PROBE).returncode == 0
    print("假阳性对照 A（改措辞）rc=%s ｜ B（围栏里再抄一遍真哈希）rc=%s ｜ C（重复点名真产物＋模板）rc=%s"
          % ("0" if ok_a else "非 0", "0" if ok_b else "非 0", "0" if ok_c else "非 0"))

    # 两条边界哨兵：独立记账，不并进 CAUGHT。
    sent_ok = []
    for name, kind, label, text in SENTINELS:
        if text == BASE:
            print("NOP   %-40s 哨兵文本与原件相同＝这条没注入任何东西" % name)
            sent_ok.append(False)
            continue
        io.open(PROBE, "w", encoding="utf-8").write(text)
        rr = run(PROBE)
        out = (rr.stdout or "") + (rr.stderr or "")
        if kind == "must-red":
            good_s = rr.returncode != 0 and label in out
            print("哨兵  %-42s rc=%s ⇒ %s" % (name, rr.returncode,
                                             "红且点到「%s」（口径没被松开）" % label if good_s
                                             else "没红或没点到名＝近漂守卫被改松了，先回读判据"))
        else:
            good_s = rr.returncode == 0
            print("哨兵  %-42s rc=%s ⇒ %s" % (name, rr.returncode,
                                             "仍为 0＝这条哨兵预期的「看不见／该放行」成立" if good_s
                                             else "开始点名＝口径变了（该退休的是本哨兵，不是判据）"))
        sent_ok.append(good_s)

    try:
        os.remove(PROBE)
    except OSError:
        pass
    good = (caught == len(MUTS) and nops == 0 and skipped == 0 and ok_a and ok_b and ok_c
            and all(sent_ok))
    print("抓到 %d/%d，NOP %d，未点到名/漏网 %d；对照 A/B/C=%s/%s/%s；哨兵 %d/%d ⇒ %s"
          % (caught, len(MUTS), nops, skipped, ok_a, ok_b, ok_c,
             sum(1 for x in sent_ok if x), len(sent_ok), "PASS" if good else "FAIL"))
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
