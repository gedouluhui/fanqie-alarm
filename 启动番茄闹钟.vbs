' FanqieAlarm launcher - pure ASCII on purpose (no encoding pitfall for the Chinese path).
' Edge app mode: standalone window, no tabs / no address bar.
' A dedicated --user-data-dir is required, otherwise the request is handed to an
' already running Edge process and --window-size / --window-position get ignored.
Option Explicit

Dim sh, exe, url, prof, cmd
Set sh = CreateObject("WScript.Shell")

exe  = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
url  = "file:///C:/Users/lyj20/Desktop/%E8%B5%9B%E5%8D%9A%E9%B8%A1%E8%9B%8B/fanqie-todo/index.html"
prof = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\FanqieAlarm\profile"

cmd = """" & exe & """" _
    & " --app=""" & url & """" _
    & " --user-data-dir=""" & prof & """" _
    & " --window-size=520,980" _
    & " --window-position=700,60" _
    & " --no-first-run --no-default-browser-check --disable-sync"

' 1 = SW_SHOWNORMAL. 0 would start the window hidden (Chrome honours the startup
' show-command), which is why an earlier build launched "successfully" but showed
' nothing on the desktop.
sh.Run cmd, 1, False
