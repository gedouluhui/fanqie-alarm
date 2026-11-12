# -*- coding: utf-8 -*-
"""等桌面回到 Default（用户解锁、显示器点亮）——合成像素量具只有在真桌面上才成立。
   每 15 秒问一次，最多 40 分钟；恢复就 READY 退出 0，超时退出 1。
   判据不在本文件实现：全仓库只有 probe_mica5.desktop_ready() 一份（ready_once／unlock_runner／
   本文件都从它取）。前几版这里各抄一份，且这一份的"显示器点亮"写成 GetSystemMetrics(7)>1000——
   SM_CXDLGFRAME 恒 ~3，于是这个脚本在桌面早已解锁的情况下也会一路走到 TIMEOUT，
   把"量具说没解锁"当成"桌面真没解锁"。那次事故的原委写在 probe_mica5.ready_from 的注释里。"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_mica5 as M5

for i in range(160):
    ok, why = M5.desktop_ready()
    if ok:
        print("READY #%d desktop=%s" % (i, why), flush=True)
        sys.exit(0)
    if i % 4 == 0:
        print("wait #%d %s" % (i, why), flush=True)
    time.sleep(15)
print("TIMEOUT 40 分钟后仍未回到 Default 桌面", flush=True)
sys.exit(1)
