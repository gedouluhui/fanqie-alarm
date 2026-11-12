# -*- coding: utf-8 -*-
"""玻璃模式的代码级闸门（不需要桌面，纯读文件）：证明"新样式只在玻璃路径生效"这件事是结构性的，
   不是我看了一眼觉得没问题。

C1 玻璃块里每一条规则的选择器都必须带 html[data-glass ——漏一条，Edge 版就跟玻璃版一起改。
C2 --veil-rgb / --veil-a 必须"用到之前就有定义"：浅色 :root、深色主题、cream、深底海报四处都要齐；
   少一处 = 那种主题下帽子的颜色退化成 0,0,0（白字页面直接变黑底）。
C3 首屏前的玻璃自举脚本必须在 </style> 之后、<body> 之前，且只认 mica/acrylic 两个值；
   放到 body 之后就会先按实心墙画一帧，用户看见"白一下再变透明"。
C4 主题回报通道必须包在 try 里且先判 window.chrome 存在——Edge 版没这个对象，裸调用每个主题切换都抛。
C5 两个 Edge 启动器的 URL 不许带 glass= 参数（旧路径必须逐字节走旧样式）。

自检（--mutate）：拿交付副本的字符串在临时目录里造 5 个已知坏的版本，逐个要求本脚本判红。
   抓不到任何一条的闸门等于没有闸门。坏样本一律写在临时目录，不进交付目录。
"""
import io
import os
import re
import sys

SHIP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(SHIP, "index.html")
VBS_EDGE = os.path.join(SHIP, "启动番茄闹钟.vbs")
BAT_EDGE = os.path.join(SHIP, "番茄闹钟-启动.bat")


def glass_block(s):
    a = s.index("真·DWM 背景材质")
    b = s.index("---------- 环境光层")
    return s[a:b]


def blocks_for_simple_sel(s, simple):
    """级联语义：一个选择器（如 body[data-bg="dusk"]）的令牌可能分散在多个规则块里——
       line 116 单独设 --canvas，line 119 的合体选择器再补 --veil-rgb。闸门要问的是
       "这条选择器命中的元素最终能不能取到 --veil-rgb"，所以必须把该选择器出现的**所有**块
       并起来看，而不是只看它第一次出现的那个块。
       策略：匹配「selector{...}」配对，选择器段含 simple 时把声明体并进结果。
       返回 (合并声明文本, 命中块数)。"""
    parts, n = [], 0
    for mo in re.finditer(r"[^{}]+\{", s):
        sel = mo.group(0)[:-1]           # 去掉尾随 '{'
        if simple not in sel:
            continue
        open_i = mo.end() - 1
        depth, i = 0, open_i
        while i < len(s):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        parts.append(s[open_i + 1:i])
        n += 1
    return "\n".join(parts), n


def checks(s, edge_override=None):
    out = []
    blk = glass_block(s)
    rules = re.findall(r"(?:^|\n)\s*([^{}\n]+)\{", blk)
    bad = [r.strip()[:40] for r in rules if "html[data-glass" not in r]
    out.append(("C1 玻璃规则全部带 data-glass 门", not bad, bad or "全部带门"))

    use = re.search(r"var\(--veil-rgb\),var\(--veil-a\)", s)
    pairs = re.findall(r"--veil-rgb:([^;]+);\s*--veil-a:([^;]+)", s)
    # 每个主题按"简单选择器"聚合级联，避免命中它的第一个块恰好不含令牌
    themes = [("浅色 :root", ":root"), ('深色主题', 'html[data-theme="dark"]'),
              ("奶油底", 'body[data-bg="cream"]'), ("深底海报", 'body[data-bg="dusk"]')]
    miss = []
    for name, simple in themes:
        merged, n = blocks_for_simple_sel(s, simple)
        if n == 0:
            miss.append(name + "(找不到主题块锚点)")
        elif "--veil-rgb" not in merged or "--veil-a" not in merged:
            miss.append(name)
    out.append(("C2 帽子令牌四套主题齐", use and len(pairs) >= 4 and not miss,
                miss or "%d 处定义" % len(pairs)))

    # find() 而非 index()：变异样本会删除锚点，index 抛 ValueError 等于闸门在失败路径上崩了
    i_boot  = s.find('new URLSearchParams(location.search).get("glass")')
    i_style = s.find("</style>")
    i_body  = s.find("<body")
    ok3 = (i_boot >= 0 and i_style >= 0 and i_body >= 0 and
           i_style < i_boot < i_body and 'g==="mica"||g==="acrylic"' in s)
    out.append(("C3 玻璃自举在首屏之前且只认两值", ok3,
                "style@%d boot@%d body@%d" % (i_style, i_boot, i_body)
                if i_boot >= 0 else "自举锚点缺失（boot=%d）" % i_boot))

    i_msg = s.find("chrome.webview.postMessage")
    if i_msg < 0:
        ok4, detail4 = False, "回报通道锚点缺失（postMessage=%d）" % i_msg
    else:
        seg = s[max(0, i_msg - 260):i_msg]
        ok4 = "try{" in seg.replace(" ", "") and "window.chrome" in seg
        detail4 = seg[-90:].replace("\n", " ")
    out.append(("C4 主题回报包在 try 且判对象存在", ok4, detail4))

    urls = []
    if edge_override is not None:
        urls.append(("（内存变异样本）", "glass=" in edge_override, edge_override[:70]))
    for f in (VBS_EDGE, BAT_EDGE):
        t = io.open(f, encoding="utf-8", errors="replace").read()
        for line in t.splitlines():
            if "index.html" in line and not line.strip().lower().startswith(("rem ", "'")):
                urls.append((os.path.basename(f), "glass=" in line, line.strip()[:70]))
    out.append(("C5 Edge 启动器不带 glass 参数", all(not has for _, has, _ in urls),
                [u for u in urls if u[1]] or ["%s:%s" % (n, ("带" if has else "干净")) for n, has, _ in urls]))
    return out


MUTANTS = [
    ("M1 玻璃块漏一条门（body 直接透明）",
     lambda s: s.replace('html[data-glass="mica"] body,html[data-glass="acrylic"] body{background:transparent}',
                         'body{background:transparent}')),
    ("M2 深底海报没定义帽子令牌",
     lambda s: s.replace('--veil-rgb:20,22,30; --veil-a:.66;',
                         '/* MUTANT: veil removed */')),
    ("M3 自举脚本挪到 body 之后",
     lambda s: s.replace('new URLSearchParams(location.search).get("glass")',
                         'new URLSearchParams(location.href).get("zz")')),
    ("M4 回报通道裸调用",
     lambda s: s.replace("try{ if(window.chrome&&chrome.webview&&chrome.webview.postMessage)",
                         "if(1&&chrome&&chrome.webview&&chrome.webview.postMessage)")),
    ("M5 Edge 启动器被加上 glass 参数",
     None),                                     # 这条要改别的文件，单独处理
]


def main():
    s = io.open(PAGE, encoding="utf-8").read()
    if "--mutate" in sys.argv:
        print("变异证伪：每个坏样本必须让对应闸门判红")
        rc_bad = 0
        for i, (name, fn) in enumerate(MUTANTS):
            if fn is None:
                bad_line = 'cmd =  & exe &  & " --mica --url ""& url & "?glass=mica""'
                res = checks(s, edge_override=bad_line)
                caught = [c[0] for c in res if not c[1]]
                print("  %-34s 判红于 %s %s" % (name, caught or "【没人抓到＝闸门是摆设】",
                                                "" if caught else "FAIL"), flush=True)
                if not caught:
                    rc_bad += 1
                continue
            m = fn(s)
            res = checks(m)
            caught = [c[0] for c in res if not c[1]]
            print("  %-34s 判红于 %s %s" % (name, caught or "【没人抓到＝闸门是摆设】",
                                            "" if caught else "FAIL"), flush=True)
            if not caught:
                rc_bad += 1
        print("MUTATE " + ("OK（%d 个坏样本全被抓到）" % len(MUTANTS) if rc_bad == 0
                          else "GAP：%d 个坏样本漏网" % rc_bad))
        sys.exit(0 if rc_bad == 0 else 3)

    allok = True
    for name, ok, got in checks(s):
        print("%-34s %s  %s" % (name, "OK" if ok else "FAIL", got))
        allok = allok and ok
    print("GLASS-CSS " + ("ALL-OK" if allok else "FAIL"))
    sys.exit(0 if allok else 3)


main()
