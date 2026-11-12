# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
"""Detached launcher for the unlock-waiting chains in this folder.

Usage: `python launch_watcher.py [watch_veil.py|unlock_runner.py]`（默认 unlock_runner.py，老链不变）。

Why a launcher instead of `start /b ...` from the console: the watcher runs for hours, prints Chinese to
its log, and must keep going after the invoking process exits. We spawn it DETACHED_PROCESS with
PYTHONIOENCODING=utf-8 (this box's console is GBK) and stdout/stderr redirected to a file, so it
never dies on a UnicodeEncodeError and never blocks a terminal. Paths are derived from __file__ so
no non-ASCII literals are needed here. The script name is validated to be a plain filename that
exists in this folder — a typo (or a path) should refuse loudly, not "succeed" with a detached
process that dies on exit code 2 and leaves an empty log.
"""
import os, sys, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SHIP = os.path.dirname(HERE)
SCRIPT_NAME = (sys.argv[1] if len(sys.argv) > 1 else "unlock_runner.py")
SCRIPT = os.path.join(HERE, SCRIPT_NAME)
if (os.path.basename(SCRIPT_NAME) != SCRIPT_NAME or not SCRIPT_NAME.endswith(".py")
        or not os.path.exists(SCRIPT)):
    raise SystemExit("REFUSE：只准启动本目录里存在的 .py 看门狗（给了 %r）" % SCRIPT_NAME)
OUT = os.path.join(os.environ["LOCALAPPDATA"], "fq-glass-verify")
os.makedirs(OUT, exist_ok=True)
LOG = os.path.join(OUT, "watcher_%s.out" % os.path.splitext(SCRIPT_NAME)[0])
CWD = SHIP if SCRIPT_NAME == "unlock_runner.py" else HERE

DETACHED_PROCESS = 0x00000008
env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
logf = open(LOG, "ab")
p = subprocess.Popen([sys.executable, SCRIPT], stdout=logf, stderr=subprocess.STDOUT,
                     cwd=CWD, env=env, creationflags=DETACHED_PROCESS, close_fds=True)
print("WATCHER_PID=%d" % p.pid)
print("SCRIPT=%s" % SCRIPT)
print("watcher_log=%s" % LOG)
print("results_will_land_in=%s (FINAL-<UTC>.md + DONE-<UTC>.ok)" % OUT)
