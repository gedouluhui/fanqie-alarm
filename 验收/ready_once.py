# -*- coding: utf-8 -*-
"""一次性回答"现在能采像素吗"。判据不在这里实现——它只有一份，在 probe_mica5.desktop_ready()，
   本文件和 unlock_runner 都从那儿导入（历史问题：两处各抄一份，改一处漏一处）。
   rc=0 ⇒ READY；rc=2 ⇒ 锁屏／显示器休眠，别跑像素脚本。"""
import os, sys
# 兜住 GBK 控制台／重定向：这份报告的判决行里有 ⇒ 与中文，locale 编码下打印它们会让
# 进程恰好崩在"打印结论那一行"上——rc=1 长得像"闸门判红"，其实是量具自己没跑完
# （2026-10-09T18:24Z 实测：`> 文件` 时本文件即如此，接终端却全绿）。判据一行没动。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_mica5 as M5

ok, why = M5.desktop_ready()
print("INPUT_DESKTOP=%s => %s" % (why, "READY" if ok else "NOT-READY"))
sys.exit(0 if ok else 2)
