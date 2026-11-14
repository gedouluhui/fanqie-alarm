#!/bin/bash
# 生产玻璃壳的复现入口：源码 FqHost.cs ＋ 同目录三个 WebView2 引用来一份就能重编。
# 之所以留脚本而不是"我记得当时这么编的"：exe 比源码新才是唯一可信的构建状态，
# 上一轮 probe_glass 连不上 CDP，根因就是 18:45 的 exe 里没有 20:20 才写进去的 --cdp 分支。
#
# 用法：
#   bash build_glass.sh                                   # 就地重编 native\FqGlass.exe（生产壳）
#   bash build_glass.sh "$LOCALAPPDATA\Temp\fq-noredir"    # 编到别处（单变量实验用）
#   bash build_glass.sh <输出目录> <变体源码cs>              # 例如把 NoRedir 关掉那一份
#
# 2026-10-09 订正：脚本原来把输出和引用都写死在 micapoc\ 子目录，而那个目录早就不存在
# （三个 WebView2 依赖和生产 exe 都在 native\ 本级）——照着跑会直接失败。复现入口指错路
# 比没有入口更糟：它能给出"我重编过了"的假证据。
# csc.exe 是 Windows 程序，只认 C:\… 这种路径，所以一律先 cygpath -w 再交给它。
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="${1:-$HERE}"
SRC="${2:-$HERE/FqHost.cs}"
CSC='C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
w() { cygpath -w "$1" 2>/dev/null || echo "$1"; }
mkdir -p "$OUT_DIR"
# 就地重编（OUT_DIR == HERE）时源和目标是同一个文件，cp 会以 "are the same file"
# 返回非 0，set -e 于是在编译前就把脚本打断——复现入口自己跑不通。逐个用 -ef 判同。
for f in Microsoft.Web.WebView2.Core.dll Microsoft.Web.WebView2.WinForms.dll WebView2Loader.dll; do
  if [ ! "$HERE/$f" -ef "$OUT_DIR/$f" ]; then cp -f "$HERE/$f" "$OUT_DIR/"; fi
done
"$CSC" -nologo -target:winexe "-out:$(w "$OUT_DIR/FqGlass.exe")" \
  "-r:$(w "$HERE/Microsoft.Web.WebView2.Core.dll")" \
  "-r:$(w "$HERE/Microsoft.Web.WebView2.WinForms.dll")" \
  -r:System.Windows.Forms.dll -r:System.Drawing.dll \
  "$(w "$SRC")"
ls -la "$OUT_DIR/FqGlass.exe"
md5sum "$SRC" "$OUT_DIR/FqGlass.exe"
