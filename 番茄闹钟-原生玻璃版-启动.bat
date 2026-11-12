@echo off
rem ============================================================
rem FanqieAlarm - NATIVE GLASS launcher (console-visible, for troubleshooting).
rem Daily use: double-click the .vbs next to it (same arguments, no black window).
rem
rem Difference vs the plain launcher:
rem   plain  = msedge --app        -> the "glass" is painted by CSS only.
rem   this   = native\FqGlass.exe  -> Windows' own DWM backdrop (Mica / Acrylic)
rem            sits behind the window, so the desktop really is part of the image.
rem Requires Windows 11 22H2 (build 22621)+. On older builds the host detects it,
rem drops the material and the page paints its own wall - nothing else changes.
rem
rem Usage:
rem   this.bat            Mica    (wallpaper tint, no blur - the everyday choice)
rem   this.bat acrylic    Acrylic (real blur - loud, and it costs legibility on a
rem                                 bright desktop)
rem   this.bat none       no system material (control / A-B comparison)
rem
rem Data: this build keeps its web profile in %LOCALAPPDATA%\FanqieAlarm\webview2,
rem which is a different place from the Edge launcher's profile. Move tasks and
rem timers between them with the app's own export / import.
rem
rem Keep this file ASCII-only: cmd.exe reads a .bat in the OEM codepage, and Chinese
rem bytes in UTF-8 can eat the line break, which turns a comment into a command.
rem The Chinese path below is therefore percent-encoded, not literal.
rem ============================================================
chcp 65001 >nul 2>&1
setlocal
set "G=%~1"
if "%G%"=="" set "G=mica"
rem G is the host switch name (mica/acrylic/none), P is what the page is told.
rem They must stay separate: "--0" is not a switch the host knows, so the host would
rem fall back to Mica while the page already painted a solid wall - that is exactly
rem how "material attached but nothing shows through" gets faked.
set "P=%G%"
if /i "%G%"=="none" set "P=0"
set "D=%~dp0"
if not exist "%D%native\FqGlass.exe" (
  echo [error] native\FqGlass.exe not found next to this .bat
  pause
  exit /b 1
)
if not exist "%D%index.html" (
  echo [error] index.html not found next to this .bat
  pause
  exit /b 1
)
echo material=%G%  page-param=%P%  host=%D%native\FqGlass.exe
echo If the window looks like it does not show through at all:
echo   1. check msedgewebview2.exe is running - the host is up, that is the renderer;
echo   2. run this .bat again with "none" and compare - that separates
echo      "material not attached" from "the page painted its own wall".
start "" "%D%native\FqGlass.exe" --%G% --url "file:///C:/Users/lyj20/Desktop/%%E8%%B5%%9B%%E5%%8D%%9A%%E9%%B8%%A1%%E8%%9B%%8B/fanqie-todo/index.html?glass=%P%"
exit /b 0
