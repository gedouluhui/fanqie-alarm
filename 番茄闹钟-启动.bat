@echo off
rem ============================================================
rem 番茄闹钟 - 启动器（控制台兜底版，出问题时看这里）
rem 日常使用请双击桌面的"番茄闹钟"图标（等价于 启动番茄闹钟.vbs，无黑窗口）。
rem 本文件与 vbs 参数完全一致，只是控制台可见，便于排查。
rem 注意：必须带独立 --user-data-dir，否则窗口尺寸参数会被
rem       已经在运行的 Edge 主进程忽略（实测会开成 1265x1372）。
rem ============================================================
chcp 65001 >nul 2>&1
if not exist "C:\Users\lyj20\Desktop\赛博鸡蛋\fanqie-todo\index.html" (
  echo [错误] 未找到 index.html
  pause
  exit /b 1
)
start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --app="file:///C:/Users/lyj20/Desktop/%%E8%%B5%%9B%%E5%%8D%%9A%%E9%%B8%%A1%%E8%%9B%%8B/fanqie-todo/index.html" --user-data-dir="%LOCALAPPDATA%\FanqieAlarm\profile" --window-size=520,980 --window-position=700,60 --no-first-run --no-default-browser-check --disable-sync
exit /b 0
