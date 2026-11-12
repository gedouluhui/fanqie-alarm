# -*- coding: utf-8 -*-
"""page_regress.py 的证伪器：造 5 个已知坏的 index.html 副本，逐个要求 page_regress 至少一条判红。
   一条都抓不到的 mutation 意味着那把闸门是摆设——page_regress 的 12 条断言必须
   在对应坏样本上"红得起来"。坏样本一律写临时目录，绝不落进交付目录（上一轮踩过）。
"""
import io, os, re, shutil, subprocess, sys, time

SHIP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(SHIP, "index.html")
TMP = os.path.join(os.environ["LOCALAPPDATA"], "fq-glass-verify", "pagemut")
os.makedirs(TMP, exist_ok=True)
BASE = io.open(SRC, encoding="utf-8").read()

MUTS = [
    # M1: 让 addTask() 变空操作 ⇒ task-add/done/del 三条都得红
    ("M1 addTask 空转",
     lambda s: s.replace("function addTask(){",
                         "function addTask(){ if(1) return;", 1)),
    # M2: 让 save() 变空操作 ⇒ task-persist 红（localStorage 里没有新任务 id）
    ("M2 save 空转",
     lambda s: s.replace("try{ localStorage.setItem(STORE_KEY, JSON.stringify(S)); }",
                         "try{ void 0; }", 1)),
    # M3: stats() 每次真重算 ⇒ stats-cached-identity 红（identity 不成立）
    ("M3 stats 无缓存",
     lambda s: s.replace("function stats(){\n",
                         "function stats(){\n  if(1) return buildStats();\n", 1)),
    # M4: 玻璃自举把"任何参数"都当 mica ⇒ glass-absent-on-none 红（无 ?glass= 也戴上属性）
    ("M4 自举不设门",
     lambda s: s.replace('if(g==="mica"||g==="acrylic") document.documentElement.dataset.glass = g;',
                         'document.documentElement.dataset.glass = g || "mica";', 1)),
    # M5: 把 --veil-rgb 从 :root 里删掉 ⇒ veil-token-defined 红
    ("M5 帽子令牌被删",
     lambda s: s.replace("  --veil-rgb:232,236,243; --veil-a:.55;", "  ", 1)),
]


def run_bad(name, txt, idx):
    p = os.path.join(TMP, "index_%d.html" % idx)
    io.open(p, "w", encoding="utf-8", newline="\n").write(txt)
    port = 9451 + idx
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "FQREG_PORT": str(port)}
    r = subprocess.run(["python", "page_regress.py", "--page", p],
                       cwd=os.path.dirname(os.path.abspath(__file__)),
                       capture_output=True, timeout=140, env=env)
    out = (r.stdout or b"").decode("utf-8", errors="replace")
    errs = (r.stderr or b"").decode("utf-8", errors="replace")
    fail_names = re.findall(r"^\S+\s+FAIL\b", out, re.M)
    caught = re.search(r"PAGE-REG\s+FAIL\s+(\[.*\])", out)
    ok = bool(caught) and r.returncode == 5
    print("%-24s rc=%d 抓到 %d 条 FAIL  %s" % (
        name, r.returncode, len(fail_names),
        caught.group(1)[:120] if caught else "【没人抓到＝page_regress 是摆设】"))
    if not ok:
        print("  out tail:", out[-400:].replace("\n", " | "))
        if errs.strip():
            print("  err tail:", errs[-300:].replace("\n", " | "))
    return ok


allok = True
for i, (name, fn) in enumerate(MUTS):
    m = fn(BASE)
    if m == BASE:
        print("%s 变异没落地（源码字面没匹配上）＝证伪器自己瞎了" % name); allok = False; continue
    if not run_bad(name, m, i):
        allok = False

print("PAGE-MUTATE " + ("OK（%d 个坏样本全被抓到）" % len(MUTS) if allok else "GAP"))
sys.exit(0 if allok else 3)
