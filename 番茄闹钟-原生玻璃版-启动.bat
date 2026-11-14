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
rem Data: this build keeps its web profile in LOCALAPPDATA\FanqieAlarm\webview2,
rem which is a different place from the Edge launcher's profile. Move tasks and
rem timers between them with the app's own export / import.
rem
rem Paths are resolved relative to this file. FqHost locates index.html next to
rem the exe or one level up and appends ?glass= itself; do not pass --url from
rem here (a machine-specific URL is exactly how the old launcher broke).
rem ============================================================
setlocal
set "G=%~1"
if "%G%"=="" set "G=mica"
if /i "%G%"=="mica" goto material_ok
if /i "%G%"=="acrylic" goto material_ok
if /i "%G%"=="none" goto material_ok
echo [error] material must be mica, acrylic or none: "%G%"
pause
exit /b 1
:material_ok
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
echo material=%G%  host="%D%native\FqGlass.exe"
echo If the window looks like it does not show through at all:
echo   1. check msedgewebview2.exe is running - the host is up, that is the renderer;
echo   2. run this .bat again with "none" and compare - that separates
echo      "material not attached" from "the page painted its own wall".
start "" "%D%native\FqGlass.exe" --%G%
exit /b 0
