#!/bin/bash
# 交付版 exe 的复现入口：与 build_glass.sh 同一份 FqHost.cs、同一批 WebView2 引用，
# 唯一差别是把 app.ico 作为 Win32 图标编进去（交付物 142 KB 里有一大半是这个图标）。
# build_glass.sh 只管"能跑"，这份只管"发出去长什么样"，两者分开是为了不让调壳时反复重写图标资源。
#
# 用法：
#   bash build_ship.sh                 # 编到 dist\番茄闹钟.exe
#   bash build_ship.sh <输出目录>       # 编到别处
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="${1:-$HERE/dist}"
CSC='C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
w() { cygpath -w "$1" 2>/dev/null || echo "$1"; }
mkdir -p "$OUT_DIR"
"$CSC" -nologo -target:winexe -optimize \
  "-out:$(w "$OUT_DIR/番茄闹钟.exe")" \
  "-win32icon:$(w "$HERE/../app.ico")" \
  "-r:$(w "$HERE/Microsoft.Web.WebView2.Core.dll")" \
  "-r:$(w "$HERE/Microsoft.Web.WebView2.WinForms.dll")" \
  -r:System.Windows.Forms.dll -r:System.Drawing.dll \
  "$(w "$HERE/FqHost.cs")"
ls -la "$OUT_DIR/番茄闹钟.exe"
md5sum "$HERE/FqHost.cs" "$OUT_DIR/番茄闹钟.exe"
