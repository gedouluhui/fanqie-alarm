' FanqieAlarm - NATIVE GLASS launcher (opt-in alternative to the Edge app window).
' Pure ASCII on purpose: the Chinese path is carried as a percent-encoded file URL.
'
' What is different from the plain Edge launcher:
'   the plain "start me first" launcher runs msedge --app, so the "glass" you see is painted by CSS only.
'   this one runs native\FqGlass.exe, a small WebView2 host that asks Windows' own
'   DWM for a real backdrop (Mica / Acrylic) behind the window, so whatever is on
'   the desktop actually participates in what the window looks like.
'
' Requires Windows 11 22H2 (build 22621) or newer. On older builds the host detects
' it, drops the material and tells the page to paint its own wall - the app still works.
'
' Data lives in %LOCALAPPDATA%\FanqieAlarm\webview2 (WebView2 profile), which is a
' different place from the Edge launcher's profile. To move tasks/timers between the
' two, use the app's own export / import.
Option Explicit

Dim sh, dir, exe, url, cmd, glass
Set sh = CreateObject("WScript.Shell")

dir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
exe = dir & "native\FqGlass.exe"
url = "file:///C:/Users/lyj20/Desktop/%E8%B5%9B%E5%8D%9A%E9%B8%A1%E8%9B%8B/fanqie-todo/index.html"

' mica    = wallpaper tint, no blur  (calm, the everyday choice)
' acrylic = real blur behind the window (loud, and it costs legibility on bright desktops)
' none    = no system material, page paints its own wall
glass = "mica"

If Not CreateObject("Scripting.FileSystemObject").FileExists(exe) Then
  MsgBox "native\FqGlass.exe is missing next to this launcher.", 48, "FanqieAlarm"
  WScript.Quit 1
End If

cmd = """" & exe & """" & " --" & glass & " --url """ & url & "?glass=" & glass & """"

' 1 = SW_SHOWNORMAL. 0 would hand the app a hidden startup-show-command and the
' window would "launch successfully" but never appear.
sh.Run cmd, 1, False
