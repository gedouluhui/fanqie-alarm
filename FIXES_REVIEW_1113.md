番茄闹钟 · 审查报告修复记录（D1–D5）
==========================================

对应 `kaggle\REVIEW_FINDINGS_VERIFICATION.md` 第四节 D1–D5。本文件只记"改了什么、
怎么验的"，审查原文没有改动。

一、名字与图标（改过一次又改回来了）
------------------------------------
2026-11-13 曾短暂改名为「芦荟闹钟」并换过绿色芦荟图标，用户看过之后决定**保持原样**：
现在仍是**番茄闹钟**、原番茄图标（`app.ico` 就是原来那份 126 KB）。
改名那一轮**没有留下来**的只有字符串和图标；修复项 D1–D5 全部保留。

顺带记一下改名的坑，将来真要改时别踩：
  · 源码目录 `fanqie-todo`、localStorage 键 `fanqie-alarm.*`、数据目录
    `%LOCALAPPDATA%\FanqieAlarm`、单实例互斥体 `FanqieAlarmGlassHost` 都不能跟着改，
    否则老用户历史记录消失、或新旧版本同时开跑抢同一份存档。

二、D1 许可证 / 第三方通知
--------------------------
· 新增 `LICENSE.txt`：允许免费用、允许整体拷贝给家人朋友；禁止改名后冒充原作者发布、禁止商业售卖。
· 新增 `THIRD_PARTY_NOTICES.txt`：三个 WebView2 DLL 的归属与微软条款链接、运行时依赖说明、
  以及"页面不含第三方 JS，也不发起网络请求"这一实测事实。
· 代码签名没做（要买证书）；`使用说明.txt` 里写清未签名是常规提示、如何核对来源。

三、D2 "不计时"模式的进行中快照封顶（丢时长）
----------------------------------------------
`index.html`：
· `T` 增加 `tm`（这一段起手时的计时方式），`start()` 里 `T.tm = S.settings.timing`。
· `saveRT()`：`tm==="none"` 时 `acc` 写实际秒数，不再 `Math.min(usedSec(), T.total)`；快照里多存 `tm`。
· `restoreRT()`：按快照里的 `tm` 还原；`none` 模式不夹到 `total`，其它模式照旧封顶。
· `recordSec()`：`S.settings.timing==="none" || T.tm==="none"` 都返回 `focusSec()`。

四、D3 CSV 公式注入
-------------------
`csvCell()` 按 OWASP 建议，对 `^[=+\-@\t\r]` 开头的文本加前导单引号。
数字列由 `Math.round` 生成，不受影响；导出文件名仍是「番茄记录-」。

五、D4 失败提示死路 + exe 内个人路径
------------------------------------
`native/FqHost.cs`：
· 删掉 `C:\Users\<作者>\Desktop\...` 这条硬编码兜底；找不到 index.html 时弹窗说清
  「exe 要和 index.html、3 个 DLL 放在同一文件夹」并退出。
· WebView2 初始化失败的提示改为指向包里真实存在的 `缺少WebView2时点此安装.url`
  （文件不存在时退化为"请先安装 Evergreen 运行时"），不再指向便携包里没有的 VBS。
· 新增 `NavigationCompleted`（失败写 `nav=FAIL <状态>` 进 `--status` 日志）与
  `ProcessFailed`（弹窗告知渲染进程异常退出）。
· 二进制复核：新 exe 里已无 `C:\Users\lyj20`、`启动番茄闹钟`、`fanqie-todo` 字串。

六、D5 只读窗口的"假成功"
-------------------------
`btnImport` / `fileIn.onchange` / `btnWipe` 三处在只读窗口直接 toast 说明"不会生效"并返回，
不再走到 `save()`（空操作）之后还报"已恢复/已清空"。

七、验证
--------
· `node --check`：整页内联脚本语法通过。
· 定点测试（真代码切片 + 假 storage）：`none` 模式快照 7200 秒 → 恢复仍 7200；
  `count` 模式仍封顶 1500；`csvCell('=1+1')` → `'=1+1`；三处只读闸门都在。
· `验收\timing_harness.js index.html after`：**41 行真值表，红 0 行**（含 RT 切片静态检查）。
· `验收\page_regress.py`：**12/12 ALL-OK**（改名前后各跑一次）。
· 冒烟启动：`番茄闹钟.exe --status …` 输出 `webview2=ok` / `nav=ok`，页面加载成功。
· 交付件：`native\dist\番茄闹钟.exe`（带图标，143872 字节），
  便携包 `桌面\番茄闹钟-便携版` 内 exe 与 dist 逐字节一致；改名回退后两道门禁又各跑一次，仍全绿。

八、没做的
----------
· 代码签名（要证书）；SmartScreen 首次仍会提示"更多信息→仍要运行"。
· 源码目录改名、VBS/BAT 启动器改名：会打断桌面快捷方式与验收脚本里的路径，留待整体搬仓库时一起做。
· `原生玻璃版-说明.md` 里那批玻璃材质的读数与哈希是针对旧 exe 的，本次没动那份文档；
  它自带的 `验收\check_cited_md5.py` 与本轮改动无关（没有引用 FqHost.cs / app.ico 的哈希）。

九、发布
--------
源码已推到 `https://github.com/gedouluhui/fanqie-alarm`（`main`）。
仓库只收源码与验收脚本：`*.exe`、微软的 WebView2 DLL、`.qoder-credits/`、
`index.html.bak-*` 这些都在 `.gitignore` 里；构建方法写在 README。

2026-11-13
