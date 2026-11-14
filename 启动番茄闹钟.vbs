' FanqieAlarm launcher - ASCII-only and fully path-portable.
' Edge app mode: standalone window, no tabs / no address bar.
' A dedicated --user-data-dir is required, otherwise the request is handed to an
' already running Edge process and --window-size / --window-position get ignored.
'
' The page URL is built from this script's own folder at run time and UTF-8
' percent-encoded. Do not paste a machine-specific path in here: Edge silently
' falls back to a new tab when the URL contains raw spaces or non-ASCII bytes.
Option Explicit

Dim sh, fso, dir, page, exe, url, prof, cmd, cand, i
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

dir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
page = dir & "index.html"
If Not fso.FileExists(page) Then
  MsgBox "index.html is missing next to this launcher." & vbCrLf & vbCrLf & page, 48, "FanqieAlarm"
  WScript.Quit 1
End If
url = "file:///" & Utf8UrlPath(Replace(page, "\", "/"))

' Edge lives in one of three places depending on install scope.
exe = ""
cand = Array( _
  sh.ExpandEnvironmentStrings("%ProgramFiles(x86)%") & "\Microsoft\Edge\Application\msedge.exe", _
  sh.ExpandEnvironmentStrings("%ProgramFiles%") & "\Microsoft\Edge\Application\msedge.exe", _
  sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Microsoft\Edge\Application\msedge.exe")
For i = 0 To UBound(cand)
  If fso.FileExists(cand(i)) Then
    exe = cand(i)
    Exit For
  End If
Next

prof = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\FanqieAlarm\profile"

If exe = "" Then
  ' No Edge: hand the local page to the system default browser. It is not the
  ' frameless app window, but the timer still runs and data is kept locally.
  On Error Resume Next
  CreateObject("Shell.Application").ShellExecute page, "", "", "open", 1
  If Err.Number <> 0 Then
    MsgBox "No Microsoft Edge was found, and the default browser could not be started." & vbCrLf & vbCrLf & page, 48, "FanqieAlarm"
  End If
  On Error GoTo 0
  WScript.Quit 0
End If

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

' UTF-8 percent-encoding for a local file URL. ADODB.Stream is the only built-in
' way to turn a Unicode path into UTF-8 bytes from VBScript. Safe URL characters
' are emitted as-is; everything else becomes %XX. The UTF-8 BOM that ADODB.Stream
' writes is stripped (a filesystem path never starts with one).
Function Utf8UrlPath(s)
  Dim stm, bytes, i, b, out
  Set stm = CreateObject("ADODB.Stream")
  stm.Type = 2
  stm.Charset = "utf-8"
  stm.Open
  stm.WriteText s
  stm.Position = 0
  stm.Type = 1
  bytes = stm.Read
  stm.Close
  out = ""
  For i = 1 To LenB(bytes)
    b = AscB(MidB(bytes, i, 1))
    If (b >= 48 And b <= 57) Or (b >= 65 And b <= 90) Or (b >= 97 And b <= 122) _
       Or b = 45 Or b = 46 Or b = 95 Or b = 126 Or b = 47 Or b = 58 Then
      out = out & Chr(b)
    Else
      out = out & "%" & Right("0" & Hex(b), 2)
    End If
  Next
  If Left(out, 9) = "%EF%BB%BF" Then out = Mid(out, 10)
  Utf8UrlPath = out
End Function
