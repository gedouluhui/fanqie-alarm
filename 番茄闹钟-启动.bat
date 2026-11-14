@echo off
chcp 936 >nul 2>&1
rem ============================================================
rem 番茄闹钟 - 启动器（控制台兜底版，出问题时看这里）
rem 日常使用请双击 启动番茄闹钟.vbs（无黑窗口）。
rem 本文件与 vbs 参数一致，只是控制台可见，便于排查。
rem 路径全部相对本文件：整个文件夹可以搬走、改名、放到含空格或中文的目录。
rem 注意：必须带独立 --user-data-dir，否则窗口尺寸参数会被
rem       已经在运行的 Edge 主进程忽略（实测会开成 1265x1372）。
rem Edge 的 --app 不认未编码的中文/空格文件 URL（会静默开成新标签页），
rem 所以这里用 PowerShell 的 [uri]::new(...).AbsoluteUri 做 UTF-8 百分号编码。
rem ============================================================
setlocal
set "D=%~dp0"
if not exist "%D%index.html" (
  echo [错误] 未找到 index.html: "%D%index.html"
  pause
  exit /b 1
)

set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" (
  echo [提示] 未找到 Microsoft Edge，改用系统默认浏览器打开。
  start "" "%D%index.html"
  exit /b 0
)

set "FQ_PAGE=%D%index.html"
set "U="
for /f "usebackq delims=" %%U in (`powershell -NoProfile -NonInteractive -Command "[uri]::new($env:FQ_PAGE).AbsoluteUri"`) do set "U=%%U"
if not defined U (
  echo [提示] 无法生成本地文件 URL，改用系统默认浏览器打开。
  start "" "%D%index.html"
  exit /b 0
)

start "" "%EDGE%" --app="%U%" --user-data-dir="%LOCALAPPDATA%\FanqieAlarm\profile" --window-size=520,980 --window-position=700,60 --no-first-run --no-default-browser-check --disable-sync
exit /b 0
