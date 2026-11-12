# -*- coding: utf-8 -*-
"""等桌面就绪就跑「页面喷涂 × backdrop 采样」机制分拣实验（#37），全程不需要人守着。

为什么要这一条：实验本身要采合成后的像素，锁屏／屏保态跑出来的一定是空帧，
而"你解锁后再跑这三条命令"不是交付。看门狗只做四件事：
  1) 先跑两道**锁屏下就能跑**的闸门（`check_veil_prereq.py` 符号/签名/档位，
     `selftest_veil_paint.py` 行宽/重试语义/环境-量具分家）。任何一道红 ⇒ 直接收工并把
     它的 tail 写进 FINAL：量具坏了时用真实桌面重试是浪费解锁窗口，那些错本来就能提前判死。
  2) 每 20 秒问一次解锁判据（只有一份：probe_mica5.desktop_ready，不在这儿另抄）；
  3) 就绪后先确认场上没有别人的像素链（FQGLASS／FQFIELD 无窗＋9411–9416 端口都没人听），
     再跑 exp_veil_paint.py，重试与否由 decide() 这个纯函数判（它能被离线自检喂坏样本）；
  4) 结论落到 %LOCALAPPDATA%\\fq-glass-verify\\FINAL-veil-<STAMP>.md，同目录写 DONE-veil 哨兵；
     超时／闸门红／三回都没成，也要在 FINAL 里写清"卡在哪一步、当时现场是什么"。
像素链串行铁律（一个进程一座场窗、端口固定）由第 3 步的入场条件守，而不是靠运气。
整条流程放在 main() 里而不是裸写在模块顶层：这样自检脚本可以 `import watch_veil`
只拿 decide()，不会一 import 就真开始等桌面、跑闸门。
"""
import glob
import io
import os
import subprocess
import sys
import time
import datetime as dt

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import probe_mica5 as M5
import probe_glass as G

OUT = os.path.join(os.environ["LOCALAPPDATA"], "fq-glass-verify")
os.makedirs(OUT, exist_ok=True)
STAMP = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
LOG = None
DEADLINE_S = 8 * 3600
POLL_S = 20
GATE_TIMEOUT = 300
ATTEMPT_TIMEOUT = 2100          # 实验脚本自己的墙钟上限是 1400 秒，这里留 700 秒起窗/退窗余量
MAX_TRIES = 3
GATES = ("check_veil_prereq.py", "selftest_veil_paint.py")
RC_WORDS = {0: "FULL", 1: "EMPTY-INSTRUMENT", 2: "PARTIAL", 3: "REFUSE",
            4: "ENV-BLOCKED", -1: "TIMEOUT"}
FINAL = os.path.join(OUT, "FINAL-veil-%s.md" % STAMP)
DONE = os.path.join(OUT, "DONE-veil-%s.ok" % STAMP)
LOG = os.path.join(OUT, "veil_watcher-%s.log" % STAMP)


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg):
    line = "[%s] %s" % (now(), msg)
    print(line, flush=True)
    if LOG:
        with io.open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def decide(rc, hist):
    """要不要再烧一回真实解锁窗口。返回 (retry?, 冷却秒数, 一句话理由)。

    分家的根据（写在 exp_veil_paint 头部那条）：**环境**不配合 ⇒ 重试是正当的；
    **量具/页面**自己 ABORT ⇒ 重试只会把噪声洗成"看起来对"的数，给一次机会就收。
    未知 rc ⇒ 停，不猜（这条本身被自检的坏样本盯着：它不许把任何值判成"继续"）。
    """
    n_same = sum(1 for r in hist if r == rc)
    if rc == 0:
        return False, 0, "FULL：三种材质都有行"
    if rc == 4:
        return True, 60, "ENV-BLOCKED：桌面/采集/CDP 不配合 ⇒ 整趟重试（第 %d 回）" % (len(hist) + 1)
    if rc == 3:
        return True, 150, "REFUSE：别人在跑像素链 ⇒ 等场窗与端口空出来，绝不抢、绝不杀"
    if rc in (1, 2):
        if n_same >= 1:
            return False, 0, "%s 已经连着出现过 ⇒ 是量具/页面的事，重试只会白烧桌面" % RC_WORDS[rc]
        return True, 90, "%s 第一回 ⇒ 只再给一回机会" % RC_WORDS[rc]
    if rc == -1:
        if n_same >= 1:
            return False, 0, "连着两回硬超时 ⇒ 这一趟的形状不对，停"
        return True, 120, "超时第一回 ⇒ 只再给一回"
    return False, 0, "rc=%s 不在语义表里 ⇒ 停，别猜" % rc


def run_py(name, timeout):
    """跑交付目录里的一个脚本，返回 (rc, 全文)。超时算 rc=-1，不假装成功。"""
    try:
        p = subprocess.run([sys.executable, os.path.join(TOOLS, name)],
                           cwd=TOOLS, capture_output=True, timeout=timeout,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        out = (p.stdout or b"").decode("utf-8", "replace") + "\n" + \
              (p.stderr or b"").decode("utf-8", "replace")
        return p.returncode, out
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT after %d s" % timeout


def field_clear():
    """场上没有别人的像素窗，且六条调试端口都没人听 ⇒ 可以放心起自己的窗。"""
    titles = list(G.find_title(G.GTITLE)) + list(G.find_title("FQFIELD"))
    busy = [p for p in (9411, 9412, 9413, 9414, 9415, 9416) if not G.port_free(p)[0]]
    return (not titles and not busy), "窗=%s 端口忙=%s" % (titles, busy)


def result_line(out):
    for l in out.splitlines():
        if l.startswith("RESULT "):
            return l.strip()
    return "RESULT 没打印（脚本没跑到收尾，多半是被硬超时或崩在半路）"


def give_up(why, extra="", rc_tag="gave-up"):
    with io.open(FINAL, "w", encoding="utf-8") as f:
        f.write(u"# 机制分拣实验（#37）· 未产出\n\n%s\n\n%s\n" % (why, extra))
    open(DONE, "w").write("%s\n" % rc_tag)
    log("GAVE UP：%s" % why[:160])
    sys.exit(0)


def write_final(gate_out, tries, out):
    report = None
    for line in out.splitlines():
        if line.startswith("REPORT "):
            report = line.split(" ", 1)[1].split("（")[0].strip()
    if not report:
        cand = sorted(glob.glob(os.path.join(OUT, "veil-paint-*.md")), key=os.path.getmtime)
        report = cand[-1] if cand else None
    with io.open(FINAL, "w", encoding="utf-8") as f:
        f.write(u"# 机制分拣实验（#37：页面喷涂挡住 backdrop，还是材质没采这块场）· 看门狗跑完 %s\n\n" % STAMP)
        f.write(u"入场顺序：先跑两道锁屏闸门（`%s`），全绿才允许烧解锁窗口；"
                u"解锁判据只用 `probe_mica5.desktop_ready()`（全场唯一一份）；"
                u"串行条件＝场上无 FQGLASS／FQFIELD 且 9411–9416 无监听者。\n\n" % "＋".join(GATES))
        f.write(u"预登记的判读规则（跑之前写在 exp_veil_paint.py 头部，跑完不许回头改）："
                u"C3 档客户区反应 ≥20 ⇒ 出厂那档不动是**页面**挡的；≤5 ⇒ 与页面无关，"
                u"材质没采这块场；中间 ⇒ 两条都没排除。`--none`／C3 是透明网页面的正对照，"
                u"Mica 是负对照（它一有反应，本实验的采集就有问题）。\n\n")
        f.write(u"rc 语义（decide() 按它决定要不要重来）：0 FULL／4 ENV-BLOCKED（环境不配合，"
                u"重试正当）／3 REFUSE（别人在跑像素链）／2 PARTIAL／1 EMPTY-INSTRUMENT"
                u"（量具或页面 ABORT，只给一回）／-1 超时（只给一回）。\n\n")
        for name, grc, gout in gate_out:
            f.write(u"## 锁屏闸门 %s — rc=%s\n\n```\n%s\n```\n\n" % (name, grc, gout))
        for attempt, r, detail in tries:
            f.write(u"## 第 %s 次尝试 — rc=%s\n\n```\n%s\n```\n\n" % (attempt, r, detail))
        if report and os.path.exists(report):
            f.write(u"## 实验报告（原文照录）\n\n")
            f.write(io.open(report, encoding="utf-8").read())
            f.write(u"\n\n报告文件：`%s`\n" % report)
        else:
            f.write(u"## 没有报告文件\n\n上面每次尝试的 rc/tail 就是全部现场。"
                    u"空表不等于「没问题」，也不等于「机制已排除」。\n")
    return report


def main():
    log("watching for a ready desktop; deadline %.1f h；判据＝probe_mica5.desktop_ready（全场唯一一份）"
        % (DEADLINE_S / 3600.0))
    t0 = time.time()

    # 第 1 步：锁屏闸门。红就收工，别拿真实解锁窗口去试量具的错。
    gate_out = []
    for name in GATES:
        grc, gout = run_py(name, GATE_TIMEOUT)
        gate_out.append((name, grc, gout[-1500:]))
        log("闸门 %s rc=%s，tail=%r" % (name, grc, gout[-140:].replace("\n", " | ")))
        if grc != 0:
            give_up(u"锁屏闸门 `%s` 报红（rc=%s）⇒ 量具/符号这一层就没通过，"
                    u"用真实解锁窗口重试是浪费。下面抄的是它自己的输出。" % (name, grc),
                    u"```\n%s\n```\n" % gout[-3000:], rc_tag="gate-red")
    log("两道闸门全绿（%s），才允许烧解锁窗口" % "、".join(GATES))

    ready = False
    why = "没问过"
    while time.time() - t0 < DEADLINE_S:
        ok, why = M5.desktop_ready()
        if ok:
            ready = True
            log("DESKTOP READY（%s），等待 %.1f min" % (why, (time.time() - t0) / 60.0))
            break
        time.sleep(POLL_S)
    if not ready:
        give_up(u"看门狗在 %.1f 小时内没等到就绪桌面（最后一次：%s）。实验一行没跑，"
                u"这不是「实验失败」，是「没跑成」。" % (DEADLINE_S / 3600.0, why))

    time.sleep(3.0)
    tries = []
    hist = []
    rc = None
    out = ""
    for attempt in range(1, MAX_TRIES + 1):
        left = DEADLINE_S - (time.time() - t0)
        if left < ATTEMPT_TIMEOUT + 120:
            log("剩余 %.0f 分钟，不够再开一回（一回上限 %d 秒）⇒ 不再重试，把已有结果写报告"
                % (left / 60.0, ATTEMPT_TIMEOUT))
            break
        clear, scene = field_clear()
        if not clear:
            log("第 %d 回入场条件不满足：%s ⇒ 等 150 秒再看（不抢别人的场窗）" % (attempt, scene))
            tries.append((attempt, "SKIP-BUSY", scene))
            time.sleep(150)
            continue
        log("第 %d 回开跑 exp_veil_paint.py（上限 %d 秒）" % (attempt, ATTEMPT_TIMEOUT))
        t = time.time()
        rc, out = run_py("exp_veil_paint.py", ATTEMPT_TIMEOUT)
        secs = time.time() - t
        log("第 %d 回 rc=%s 耗时 %.0f 秒 ｜ %s ｜ tail=%r"
            % (attempt, rc, secs, result_line(out), out[-200:].replace("\n", " | ")))
        tries.append((attempt, rc, out[-6000:]))
        retry, cool, why2 = decide(rc, hist)
        hist.append(rc)
        log("decide(%s=%s, 历史=%s) ⇒ %s" % (rc, RC_WORDS.get(rc, "?"), hist[:-1], why2))
        if not retry:
            break
        if len(hist) >= MAX_TRIES:
            log("已经试到 MAX_TRIES=%d ⇒ 停，把现场写清楚交给人看" % MAX_TRIES)
            break
        time.sleep(cool)
    report = write_final(gate_out, tries, out)
    open(DONE, "w").write("ok rc=%s %s\n" % (rc, result_line(out)))
    log("FINAL %s ｜ DONE %s ｜ rc=%s ｜ report=%s" % (FINAL, DONE, rc, report))


if __name__ == "__main__":
    main()
