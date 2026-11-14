' FanqieAlarm - NATIVE GLASS launcher (opt-in alternative to the Edge app window).
' Pure ASCII on purpose: every machine-specific value is resolved at run time.
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

Dim sh, fso, dir, exe, cmd, glass
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

dir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
exe = dir & "native\FqGlass.exe"

' mica    = wallpaper tint, no blur  (calm, the everyday choice)
' acrylic = real blur behind the window (loud, and it costs legibility on bright desktops)
' none    = no system material, page paints its own wall
glass = "mica"

If Not fso.FileExists(exe) Then
  MsgBox "native\FqGlass.exe is missing next to this launcher." & vbCrLf & vbCrLf & exe, 48, "FanqieAlarm"
  WScript.Quit 1
End If

' FqHost locates index.html next to the exe or one level up and appends ?glass=
' itself. Never pass a machine-specific --url from here.
cmd = """" & exe & """" & " --" & glass

' 1 = SW_SHOWNORMAL. 0 would hand the app a hidden startup-show-command and the
' window would "launch successfully" but never appear.
sh.Run cmd, 1, False
