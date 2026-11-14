using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

// 番茄闹钟 · 真 DWM 背景材质宿主（可选启动方式；Edge 版启动器不受影响，两者数据互不相通，
// 靠应用内『导出/导入备份』搬运）。
//
// 为什么必须有这么一个原生壳：Chromium 的窗口化模式（Edge --app）那层合成面是不透明的，
// 页面里 CSS 写的"玻璃"只是模拟，窗口边缘永远透不出桌面。probe_mica5 用可标定的透过率尺子
// （正对照＝原生颜色键透明窗 slope 1.000；负对照＝不透宿主 slope 0.000）在同一套场上量到：
//   backdrop=2(Mica)     slope +0.000  与不透底色差 +231 → 材质在画，但只采壁纸，别的窗不透进来
//   backdrop=3(Acrylic)  slope +0.360  棋盘梯度残留 6.3% → 别的窗被糊进客户区＝真模糊
// 于是这里默认 Mica（稳、不闪、正文对比度可控），--acrylic 给要"真模糊"的人。
//
// args: [--mica|--acrylic|--none] [--rect x,y,w,h] [--url URL] [--title T] [--udf PATH]
//       [--status PATH] [--no-taskbar]
// --rect / --title / --status 是给探针用的（物理像素、可改名、可自报），日常启动不带。
static class FqHost
{
    [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr h, int attr, ref int v, int s);
    [DllImport("user32.dll")] static extern int GetWindowLong(IntPtr h, int idx);
    [DllImport("user32.dll", SetLastError = true)]
    static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
    [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("ntdll.dll")] static extern int RtlGetVersion(ref VERSIONINFOEX v);

    // OSVERSIONINFOEX 的真实布局：前五个 DWORD，后面全是 WORD/BYTE。
    // 把 wServicePackMajor 写成 int 会让 dwBuildNumber 之外的字段错位，
    // 这里只取 dwBuildNumber（偏移 12），但结构尺寸要老实照抄，免得内核按 size 字段截断。
    [StructLayout(LayoutKind.Sequential)]
    struct VERSIONINFOEX
    {
        public int dwOSVersionInfoSize, dwMajorVersion, dwMinorVersion, dwBuildNumber, dwPlatformId;
        public ushort wServicePackMajor, wServicePackMinor, wSuiteMask;
        public byte wProductType, wReserved;
    }

    const int DWMWA_SYSTEMBACKDROP_TYPE = 38;
    const int DWMWA_USE_IMMERSIVE_DARK_MODE = 20;
    const int GWL_EXSTYLE = -20;
    const int WS_EX_NOREDIRECTIONBITMAP = 0x00200000;
    const uint SWP_NOZORDER = 0x0004, SWP_FRAMECHANGED = 0x0020,
               SWP_NOMOVE = 0x0002, SWP_NOSIZE = 0x0001;

    static Mutex oneShot;
    static WebView2 wv;
    static int backdrop = 2;              // 1=none 2=mica 3=acrylic
    static string url, udf, statusPath, title = "番茄闹钟";
    static int cdp = 0;
    static bool taskbar = true, multi = false;
    static int rx = -1, ry = -1, rw = -1, rh = -1;   // 探针用的物理像素落位
    static string argWarn = "";                      // 非法参数不崩，记下来写进 status

    // ex-style 只能走 CreateParams：实测在 HandleCreated 里 SetWindowLong 加
    // WS_EX_NOREDIRECTIONBITMAP，到 Shown 再读就变回 0x10100——WinForms 建柄以后还会按自己的
    // 参数表重写一遍扩展样式。样式没落地，"透不透"量的就是别人的像素。
    class HostForm : Form
    {
        public bool NoRedir;
        protected override CreateParams CreateParams
        {
            get
            {
                var cp = base.CreateParams;
                if (NoRedir) cp.ExStyle |= WS_EX_NOREDIRECTIONBITMAP;
                return cp;
            }
        }
    }

    static int Build()
    {
        // 传数组那版实测：RtlGetVersion 返回 0 但 build 读回来是 0——LPArray 的缓冲区写回
        // 丢了，于是 supported 恒假，材质被静默降级成"不透"（smoke_glass 的 G2 就是被它抓到的）。
        // ref 传参才拿得到 26300。
        try
        {
            var v = new VERSIONINFOEX();
            v.dwOSVersionInfoSize = Marshal.SizeOf(typeof(VERSIONINFOEX));
            if (RtlGetVersion(ref v) == 0 && v.dwBuildNumber > 0) return v.dwBuildNumber;
        }
        catch (Exception) { }
        try
        {
            using (var k = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(
                       @"SOFTWARE\Microsoft\Windows NT\CurrentVersion"))
            {
                object o = k == null ? null : k.GetValue("CurrentBuildNumber");
                int b;
                if (o != null && int.TryParse(Convert.ToString(o), out b)) return b;
            }
        }
        catch (Exception) { }
        return 0;
    }

    // 参数解析独立成方法，才能在没有窗口的测试里直接调用（Main 一跑就要建窗）。
    static void ParseArgs(string[] args)
    {
        for (int i = 0; i < args.Length; i++)
        {
            string a = args[i];
            if (a == "--acrylic") backdrop = 3;
            else if (a == "--none") backdrop = 1;
            else if (a == "--mica") backdrop = 2;
            else if (a == "--no-taskbar") taskbar = false;
            else if (a == "--multi") multi = true;
            else if (a == "--title" && i + 1 < args.Length)
            {
                string t = args[++i];
                if (t.Length > 0) title = t;
            }
            else if (a == "--url" && i + 1 < args.Length) url = args[++i];
            else if (a == "--udf" && i + 1 < args.Length) udf = args[++i];
            else if (a == "--status" && i + 1 < args.Length) statusPath = args[++i];
            else if (a == "--cdp" && i + 1 < args.Length)
            {
                // int.Parse 遇到 "--cdp abc" 会直接抛未捕获异常闪退；探针参数写错
                // 不该由用户来承担。非法值当作"没带"，并写进 status 方便排查。
                int p;
                if (int.TryParse(args[++i], out p) && p > 0 && p <= 65535) cdp = p;
                else argWarn += "ignored --cdp=" + args[i] + "\n";
            }
            else if (a == "--rect" && i + 4 < args.Length)
            {
                int x = 0, y = 0, w = 0, h = 0;
                bool rectOk = int.TryParse(args[i + 1], out x) && int.TryParse(args[i + 2], out y) &&
                              int.TryParse(args[i + 3], out w) && int.TryParse(args[i + 4], out h);
                if (rectOk && w > 0 && h > 0) { rx = x; ry = y; rw = w; rh = h; }
                else argWarn += "ignored --rect\n";
                i += 4;
            }
        }
    }

    [STAThread]
    static void Main(string[] args)
    {
        // 必须先声明 DPI 感知再建任何窗：150% 缩放下不声明的话系统整位图拉伸，
        // 玻璃边缘会糊成一片，量出来的梯度残留也全废。
        SetProcessDPIAware();
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        ParseArgs(args);
        if (!multi)
        {
            // csc v4.0.30319 只到 C# 5：`out bool fresh` 这种内联声明编不过，得先声明再 out。
            bool fresh;
            oneShot = new Mutex(true, "FanqieAlarmGlassHost", out fresh);
            if (!fresh)
            {
                /* 旧行为只说一句"已经在运行了"就退出：用户明明双击了图标，
                   屏幕上却什么也没发生（窗口可能最小化、被别的窗盖住、或落在另一块屏）。
                   现在先把已存在的宿主窗恢复并抬到前台；真找不到才提示。 */
                IntPtr h = FindWindow(null, title);
                if (h != IntPtr.Zero)
                {
                    ShowWindow(h, 9);          // SW_RESTORE
                    SetForegroundWindow(h);
                    return;
                }
                MessageBox.Show("番茄闹钟（玻璃版）已经在运行了，但没有找到它的窗口。请从任务栏切换。",
                                "番茄闹钟", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
        }

        string exeDir = AppDomain.CurrentDomain.BaseDirectory;
        int build = Build();
        // 22621 = Win11 22H2，DWMWA_SYSTEMBACKDROP_TYPE 从这之后才保证有效；更早的系统上
        // DwmSetWindowAttribute 会返回 0x8000FFFF，材质根本不画，页面必须自己把墙画实。
        bool supported = build >= 22621 && backdrop != 1;
        string glass = !supported ? "0" : (backdrop == 3 ? "acrylic" : "mica");
        if (string.IsNullOrEmpty(url))
        {
            string page = Path.Combine(exeDir, "index.html");
            if (!File.Exists(page))
                page = Path.GetFullPath(Path.Combine(exeDir, "..", "index.html"));   // exe 放在 native\ 子目录时
            /* 以前这里还有一条写死作者机器绝对路径的兜底（C:\Users\<作者>\Desktop\...）。
               它会让发布物带着个人信息，而且在作者机器上"碰巧能跑"、换台机器就白屏。
               现在找不到就当面说清楚：文件该放在哪、缺了哪一个。 */
            if (!File.Exists(page))
            {
                MessageBox.Show("找不到 index.html。\n\n请把「番茄闹钟.exe」和 index.html、3 个 WebView2 DLL\n放在同一个文件夹里再打开（整个文件夹一起拷贝，不要只拷 exe）。",
                                "番茄闹钟", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            url = new Uri(page).AbsoluteUri + "?glass=" + glass;
        }
        if (string.IsNullOrEmpty(udf))
            udf = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                               "FanqieAlarm", "webview2");

        double scale = 1.0;
        try { using (var g = Graphics.FromHwnd(IntPtr.Zero)) scale = g.DpiX / 96.0; }
        catch (Exception) { }
        // 一律按物理像素算，不让 WinForms 的 AutoScale 掺第二遍：SetWindowPos 给的是外框尺寸，
        // 与 Edge --app 的 --window-size 同口径（520x980 是外框，客户区再减去标题栏和边框）。
        int px = rx > 0 ? rx : (int)(700 * scale), py = ry > 0 ? ry : (int)(60 * scale);
        int pw = rw > 0 ? rw : (int)(520 * scale), ph = rh > 0 ? rh : (int)(980 * scale);
        // 默认 520x980 在 150% 下是 780x1470，比 1440 的屏还高：窗口下半截（计时页的
        // 预设与主按钮、底部 tab）整块掉到屏幕外，而页面自适应看到的仍是 943px 视口，
        // 于是"窗够高"的假象连布局都带偏。默认启动按工作区夹一次尺寸和位置；
        // --rect 是探针坐标系，显式落位一律原样保留，否则所有像素量具都会跟着漂。
        bool autoRect = rw <= 0;
        if (autoRect)
        {
            try
            {
                Rectangle wa = Screen.PrimaryScreen.WorkingArea;
                int margin = (int)(12 * scale);
                int maxW = Math.Max((int)(320 * scale), wa.Width - margin * 2);
                int maxH = Math.Max((int)(420 * scale), wa.Height - margin * 2);
                if (pw > maxW) pw = maxW;
                if (ph > maxH) ph = maxH;
                if (px < wa.Left + margin) px = wa.Left + margin;
                if (py < wa.Top + margin) py = wa.Top + margin;
                if (px + pw > wa.Right - margin) px = wa.Right - margin - pw;
                if (py + ph > wa.Bottom - margin) py = wa.Bottom - margin - ph;
            }
            catch (Exception) { }
        }

        var log = new System.Text.StringBuilder();
        if (argWarn.Length > 0) log.Append("args: " + argWarn.Replace("\n", "; ") + "\n");
        log.Append("build=" + build + " glass=" + glass + " backdrop=" + backdrop +
                   " scale=" + scale + " want-rect=" + px + "," + py + "," + pw + "x" + ph +
                   " auto-rect=" + (autoRect ? "clamp" : "explicit") + "\n");
        if (autoRect)
        {
            try { log.Append("workarea=" + Screen.PrimaryScreen.WorkingArea + "\n"); }
            catch (Exception) { }
        }

        var f = new HostForm
        {
            NoRedir = supported,
            Text = title,
            ShowInTaskbar = taskbar,
            StartPosition = FormStartPosition.Manual,
            Location = new Point(px, py),
            FormBorderStyle = FormBorderStyle.Sizable,
            // 材质没接上的机器上这块就是背景，所以它得等于页面的墙，不能是黑。
            BackColor = Color.FromArgb(232, 236, 243),
            MinimumSize = new Size((int)(320 * scale), (int)(420 * scale)),
            Size = new Size(pw, ph)
        };
        string ico = Path.Combine(exeDir, "app.ico");
        if (File.Exists(ico)) { try { f.Icon = new Icon(ico); } catch (Exception) { } }
        wv = new WebView2 { Dock = DockStyle.Fill, DefaultBackgroundColor = Color.Transparent };
        f.Controls.Add(wv);

        f.HandleCreated += (s, e) =>
        {
            IntPtr h = f.Handle;
            int v = backdrop;
            int rc = DwmSetWindowAttribute(h, DWMWA_SYSTEMBACKDROP_TYPE, ref v, 4);
            int dv = 0;   // 先按浅色标题栏起，页面主题就绪后 postMessage 过来再翻
            DwmSetWindowAttribute(h, DWMWA_USE_IMMERSIVE_DARK_MODE, ref dv, 4);
            log.Append("bd-rc=0x" + rc.ToString("X8") + " exstyle=0x" +
                       GetWindowLong(h, GWL_EXSTYLE).ToString("X") + "\n");
            if (rc != 0)
            {
                // 材质这层根本没接上 ⇒ 通知页面把墙画实，否则透明页会露出宿主底色。
                url = url.Replace("glass=mica", "glass=0").Replace("glass=acrylic", "glass=0");
                log.Append("backdrop unsupported, url downgraded\n");
            }
        };

        f.Shown += (s, e) =>
        {
            // 几何只能在 Shown 里落：HandleCreated 时 WinForms 自己的布局还没做完，
            // 那时调 SetWindowPos 会失败（实测窗停在 202x56、客户区 0 高）。
            // 落位失败要重试一次（DirectShow/主题初始化偶发吞掉第一次），
            // 尺寸不对的话页面那套自适应会拿错误的视口跑，比"窗小一点"严重得多。
            bool ok = SetWindowPos(f.Handle, IntPtr.Zero, px, py, pw, ph,
                                   SWP_NOZORDER | SWP_FRAMECHANGED);
            if (!ok || f.Width != pw || f.Height != ph)
            {
                f.Size = new Size(pw, ph);
                f.Location = new Point(px, py);
                ok = SetWindowPos(f.Handle, IntPtr.Zero, px, py, pw, ph,
                                  SWP_NOZORDER | SWP_FRAMECHANGED);
            }
            var r = f.RectangleToScreen(new Rectangle(0, 0, f.ClientSize.Width, f.ClientSize.Height));
            log.Append("rect=" + (ok ? "ok" : "fail") + " outer=" + f.Width + "x" + f.Height +
                       " client=" + r.Left + "," + r.Top + " " + r.Width + "x" + r.Height +
                       " exstyleNow=0x" + GetWindowLong(f.Handle, GWL_EXSTYLE).ToString("X") + "\n");
            WriteStatus(log);
        };

        f.Load += async (s, e) =>
        {
            try
            {
                Directory.CreateDirectory(udf);
                CoreWebView2EnvironmentOptions opts = null;
                if (cdp > 0)
                {
                    // 只给量具用：合成后的对比度必须在"真窗口＋真桌面背景"上量，
                    // CDP 的截图里没有 DWM 那层，所以像素走 BitBlt，CDP 只负责告诉我
                    // "哪块是字、字是什么颜色"。
                    opts = new CoreWebView2EnvironmentOptions();
                    // 只放行本机这两个调试源。原来的 --remote-allow-origins=* 等于把
                    // 页面里的任意 Origin 都放进来；探针不需要那么宽。
                    opts.AdditionalBrowserArguments = "--remote-debugging-port=" + cdp +
                        " --remote-allow-origins=http://127.0.0.1:" + cdp +
                        ",http://localhost:" + cdp;
                }
                // 便携包可以自带固定版运行时（WebView2Fixed\...\msedgewebview2.exe），
                // 优先级高于机器上装的 Evergreen；没有就传 null 走系统运行时。
                string fixedDir = FindFixedRuntime(Path.Combine(exeDir, "WebView2Fixed"));
                if (fixedDir != null) log.Append("webview2-fixed=" + fixedDir + "\n");
                var env = await CoreWebView2Environment.CreateAsync(fixedDir, udf, opts);
                await wv.EnsureCoreWebView2Async(env);
                var st = wv.CoreWebView2.Settings;
                st.AreDefaultContextMenusEnabled = false;
                st.AreDevToolsEnabled = cdp > 0;   // 日常启动仍然关着，只有量具带 --cdp 时才开
                st.IsStatusBarEnabled = false;
                wv.CoreWebView2.NewWindowRequested += (s2, e2) => { e2.Handled = true; };
                // 页面主题（浅色/深色）只有运行时才知道：它 postMessage 过来，这里换标题栏配色。
                wv.CoreWebView2.WebMessageReceived += (s3, e3) =>
                {
                    try
                    {
                        string m = e3.WebMessageAsJson;
                        if (string.IsNullOrEmpty(m)) return;
                        bool dark;
                        if (TryReadThemeDark(m, out dark))
                        {
                            int dv = dark ? 1 : 0;
                            DwmSetWindowAttribute(f.Handle, DWMWA_USE_IMMERSIVE_DARK_MODE, ref dv, 4);
                        }
                    }
                    catch (Exception) { }
                };
                wv.CoreWebView2.Navigate(url);
                /* 页面加载成功与否以前无人过问：导航失败就是一块白窗，用户不知道发生了什么。
                   这里至少写进日志，并在失败时给一句能读的话。 */
                wv.CoreWebView2.NavigationCompleted += (s4, e4) =>
                {
                    try { log.Append("nav=" + (e4.IsSuccess ? "ok" : ("FAIL " + e4.WebErrorStatus)) + "\n"); WriteStatus(log); }
                    catch (Exception) { }
                };
                wv.CoreWebView2.ProcessFailed += (s5, e5) =>
                {
                    try
                    {
                        log.Append("process=FAIL " + e5.ProcessFailedKind + "\n");
                        WriteStatus(log);
                        MessageBox.Show("番茄闹钟的页面进程异常退出（" + e5.ProcessFailedKind +
                                        "）。\n\n请关闭窗口后重新打开；如果反复出现，重装 WebView2 运行时。",
                                        "番茄闹钟", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    }
                    catch (Exception) { }
                };
                log.Append("webview2=ok url=" + url + "\n");
            }
            catch (Exception ex)
            {
                log.Append("webview2=FAIL " + ex.Message + "\n");
                WriteStatus(log);
                /* 旧行为只弹一条"去装 WebView2"的死框，然后整个窗口关掉。
                   先给一条就地可走的路：用本机 Edge 打开同一个页面（应用数据仍然在本机，
                   只是外壳从 DWM 玻璃换成普通 Edge 窗）。 */
                DialogResult useEdge = MessageBox.Show(
                    "WebView2 运行时初始化失败：\n" + ex.Message + "\n\n" +
                    "要现在改用本机 Microsoft Edge 打开吗？\n" +
                    "（窗口外壳会变成普通 Edge 窗口，计时、任务和导出/导入照常可用）",
                    "番茄闹钟", MessageBoxButtons.YesNo, MessageBoxIcon.Warning);
                if (useEdge == DialogResult.Yes)
                {
                    string fallback = url.Replace("glass=mica", "glass=0")
                                         .Replace("glass=acrylic", "glass=0");
                    if (TryOpenInEdge(fallback))
                    {
                        log.Append("fallback=edge-ok\n");
                        WriteStatus(log);
                        f.Close();
                        return;
                    }
                    /* 降级也失败了才落到安装提示。 */
                }
                else
                {
                    f.Close();
                    return;
                }
                string urlFile = Path.Combine(exeDir, "缺少WebView2时点此安装.url");
                string hint = File.Exists(urlFile)
                    ? "双击同目录的『缺少WebView2时点此安装.url』，装好 Evergreen 运行时后再打开。"
                    : "请先安装 Microsoft Edge WebView2 运行时（Evergreen），再打开本程序。";
                MessageBox.Show("WebView2 初始化失败：" + ex.Message + "\n\n" + hint,
                    "番茄闹钟", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                f.Close();
            }
            WriteStatus(log);
        };
        Application.Run(f);
        GC.KeepAlive(oneShot);
    }

    /* 页面发的是 {"t":"theme","dark":true}。旧代码用 Contains 找子串：
       别的消息里只要出现 "theme" 或 "dark":true 就会误翻标题栏。这里按真 JSON
       解析，只认 t == "theme" 的对象，且 dark 必须是布尔 true 才翻黑。
       坏 JSON 一律当"不是主题消息"，不抛到 UI 线程。 */
    static bool TryReadThemeDark(string json, out bool dark)
    {
        dark = false;
        try
        {
            var msg = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(json);
            object kind, darkVal;
            if (msg == null || !msg.TryGetValue("t", out kind) ||
                Convert.ToString(kind) != "theme") return false;
            dark = msg.TryGetValue("dark", out darkVal) && darkVal is bool && (bool)darkVal;
            return true;
        }
        catch (Exception) { return false; }
    }

    // 固定版 WebView2 运行时的目录可以是 WebView2Fixed\ 本身，也可以是它下面
    // 一层版本目录（解压出来的常见形状）。只认真正含 msedgewebview2.exe 的那层。
    static string FindFixedRuntime(string root)
    {
        try
        {
            if (!Directory.Exists(root)) return null;
            if (File.Exists(Path.Combine(root, "msedgewebview2.exe"))) return root;
            foreach (string sub in Directory.GetDirectories(root))
                if (File.Exists(Path.Combine(sub, "msedgewebview2.exe"))) return sub;
        }
        catch (Exception) { }
        return null;
    }

    static string FindEdge()
    {
        string pf86 = Environment.GetEnvironmentVariable("ProgramFiles(x86)");
        string pf = Environment.GetEnvironmentVariable("ProgramFiles");
        string lad = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string[] cands = new string[]
        {
            pf86 == null ? null : Path.Combine(pf86, @"Microsoft\Edge\Application\msedge.exe"),
            pf == null ? null : Path.Combine(pf, @"Microsoft\Edge\Application\msedge.exe"),
            Path.Combine(lad, @"Microsoft\Edge\Application\msedge.exe")
        };
        foreach (string c in cands)
            if (c != null && File.Exists(c)) return c;
        return null;
    }

    static bool TryOpenInEdge(string target)
    {
        try
        {
            string edge = FindEdge();
            if (edge == null)
            {
                // 连 Edge 都没有：交给系统默认浏览器。目标本身就是 file:/// URL。
                var doc = new ProcessStartInfo(target);
                doc.UseShellExecute = true;
                Process.Start(doc);
                return true;
            }
            string prof = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "FanqieAlarm", "profile");
            var psi = new ProcessStartInfo(edge);
            psi.UseShellExecute = false;
            psi.Arguments = "--app=\"" + target + "\" --user-data-dir=\"" + prof + "\"" +
                            " --window-size=520,980 --window-position=700,60" +
                            " --no-first-run --no-default-browser-check --disable-sync";
            Process.Start(psi);
            return true;
        }
        catch (Exception) { return false; }
    }

    static void WriteStatus(System.Text.StringBuilder log)
    {
        if (string.IsNullOrEmpty(statusPath)) return;
        try { File.WriteAllText(statusPath, log.ToString()); } catch (Exception) { }
    }
}
