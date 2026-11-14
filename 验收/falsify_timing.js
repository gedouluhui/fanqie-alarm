/* 计时真值表的证伪器：往"要发给用户的那份字节"里注入静默 bug，逐条要求真值表变红。
   用法：Qoder.exe(ELECTRON_RUN_AS_NODE=1) falsify_timing.js <index.html>
   · 变异只在内存里的字符串上做，不写盘、不碰产品文件（这条链以前出过"把变异态当基线"的事故）。
   · 每条变异先断言"改出来的字节 ≠ 原字节"，改不动的记 NOP（变异失效），绝不把它算成漏网，
     也绝不为了让它变绿而放宽判据。
   · 分类：CAUGHT＝真值表里至少一行点名变红；GATE＝形状闸门先把它挡了（弱一档，会单独点名）。 */
const fs = require("fs");
const H = require("./timing_harness.js");

const FILE = process.argv[2] || "C:/Users/lyj20/Desktop/赛博鸡蛋/fanqie-todo/index.html";
const BASE = fs.readFileSync(FILE, "utf8");

const MUTS = [
  ["M1 短离开不退款（一次 alt-tab 就吃掉时长）", "T.acc += ms/1000;", ""],
  ["M2 awayStart 允许重臂（离开起点被往后推）", "  if(T.awayAt) return;", ""],
  ["M3 停表失效（人不在时警报照样把这段完成）", "T.acc + (T.hold ? 0 : (mono()-T.startAt)/1000)", "T.acc + (mono()-T.startAt)/1000"],
  ["M4 focusSec 退回旧口径（已结算的离开不扣）", "function focusSec(){ return usedSec(); }",
   "function focusSec(){ return Math.max(0, usedSec() - awayNowSec()); }"],
  ["M5 普通模式也停表（界面承诺的\"不做中断判定\"被推翻）", "  if(S.settings.mode===\"normal\") return;      // 普通模式：界面承诺不做中断判定", ""],
  ["M6 固化被摘掉（停表停在 0 秒上）", "T.acc = usedSec();", "T.acc = 0;"],
  ["M7 held 恒假（判定的那一笔整条短路）", "const held=T.hold;", "const held=false;"],
  ["M8 结束弹层不披露离开（170 这类数字重新变得来路不明）",
   "(awayMin>0.5 ? \"（其间离开 \"+Math.round(awayMin)+\" 分钟没计入，倒计时当时停住了。）\" : \"\") +", ""],
  ["M9 中断 toast 不披露离开", "(awayMs>0 ? \"（离开 \"+Math.round(awayMs/60000)+\" 分钟没计入）\" : \"\")", "\"\""],
  ["M10 不计时模式重新被 total 封顶", "S.settings.timing===\"none\" ? focusSec() : Math.min(focusSec(), T.total)", "Math.min(focusSec(), T.total)"],
  ["M11 pause 不再清 hold（停表标记漏到暂停态里）", "T.status=\"pause\"; T.hold=false; T.awayAt=0;", "T.status=\"pause\"; T.awayAt=0;",
   "预定惰性（2026-10-15 重评过一轮，仍成立，但成立的理由换了）：usedSec() 在 status!==\"run\" 那一支直接返回 acc、不看 hold，" +
   "回到 run 的唯一入口 resume() 自己清 hold，checkDone 又要求 status===\"run\" ⇒ 账本上（记录／acc／awayTotal／状态）这一漏无处显形。" +
   "它唯一真的显形面是 render() 里的提示语顺序（1421 的\"正在离开\"排在 1422 的\"本次已离开\"之前），而 render 在 DOM 小工具那一段之后、不在任何切片里，沙箱看不见。" +
   "⇒ 这条降级为\"沙箱不覆盖\"，改由真窗口盯：严格模式起手即在后台→停表→按暂停，表盘必须写\"本次已离开 N 秒\"（已实测，见 runbook 的计时口径一节）；" +
   "若将来把 render 也纳入切片，这条要第一个重跑，被抓到就把 just 摘掉。"],
  ["M12 阈值判定恒真（任何离开都当短离开退款）", "if(ms<=S.settings.away*1000){", "if(true){"],
  ["M13 停表标记从来没立起（锚点还在，能力没了）", "T.hold = true;", "T.hold = false;"],
  ["M14 普通模式的分家判断失效（注释锚点原样保留）", "if(S.settings.mode===\"normal\") return;      // 普通模式", "if(S.settings.mode===\"zzz\") return;      // 普通模式"],
  ["M15 recordSec 绕回旧口径（focusSec 的定义没动）", "Math.min(focusSec(), T.total)", "Math.min(Math.max(0, usedSec() - awayNowSec()), T.total)"],
  /* M16/M17：锚点保留、行为破坏。M1–M5 那五条是"把整句删掉"，形状闸门先挡（弱一档）；
     这两条绕开闸门，专门证明真值表自己也看得见同一类错，而不是只靠锚点护着。
     M20/M21 同属这一家（接线级），见下面那两条的说明。 */
  ["M16 短离开退款当场被吃掉（锚点 T.acc += ms/1000; 原样在）", "T.acc += ms/1000; dlBook(); render(); return;", "T.acc += ms/1000; dlBook(); T.acc -= ms/1000; render(); return;"],
  ["M17 每次 blur 先把起点清零（＝重臂，但闸门锚点 if(T.awayAt) return; 原样在）",
   'if(S.settings.mode==="normal") return;      // 普通模式：界面承诺不做中断判定',
   'if(S.settings.mode==="normal") return;      // 普通模式：界面承诺不做中断判定\n  T.awayAt = 0;'],
  ["M18 切回窗口不补响（监听器少了那一拍，checkDone 定义还在＝闸门看不见）",
   "document.hidden? awayStart() : (awayEnd(), checkDone(), render());",
   "document.hidden? awayStart() : (awayEnd(), render());"],
  ["M19 记录归属退回结束时刻（跨午夜那段又整段跳到第二天）",
   "const st = T.swAt>0 ? new Date(T.swAt) : now;", "const st = now;"],
  /* M20/M21：M18 只证明"删掉那句"会被闸门挡（弱一档）。这两条把补响就地换成空函数——
     锚点原样保留、监听器照样挂上、awayEnd 照样跑，只有那一拍不判完成：
     逼真值表用 A15／A17 两行分别点名两条监听器，而不是靠锚点护身。 */
  ["M20 alt-tab 回来的补响被空函数顶掉（锚点 setMotion(); awayEnd(); checkDone(); render(); 原样在）",
   'window.addEventListener("focus",()=>{ setMotion(); awayEnd(); checkDone(); render(); });',
   'window.addEventListener("focus",()=>{ const checkDone = () => {}; setMotion(); awayEnd(); checkDone(); render(); });'],
  ["M21 从最小化回来的补响被空函数顶掉（锚点三元表达式原样在）",
   'document.addEventListener("visibilitychange",()=>{ setMotion(); document.hidden? awayStart() : (awayEnd(), checkDone(), render()); });',
   'document.addEventListener("visibilitychange",()=>{ const checkDone = () => {}; setMotion(); document.hidden? awayStart() : (awayEnd(), checkDone(), render()); });'],
  /* M22–M29：这三处是本轮新加的代码（起手即在后台补停表、跳过 5 秒闸门、停表期间按暂停先结算）。
     每条都配了"删掉整句"和"锚点原样在、行为破掉"两版——只有前一版会被形状闸门挡，
     后一版必须靠真值表自己点名，否则锚点就成了唯一的护身符（上一轮 M18 就是这么被识破的）。 */
  ["M22 起手在场判断恒假（整句被换掉＝闸门该挡）",
   "function startedAway(){ return !!document.hidden || !document.hasFocus(); }",
   "function startedAway(){ return false; }"],
  ["M23 同名后声明把在场判断顶掉（锚点原样在，＝hoisting 版的静默替换）",
   "function startedAway(){ return !!document.hidden || !document.hasFocus(); }",
   "function startedAway(){ return !!document.hidden || !document.hasFocus(); }\nfunction startedAway(){ return false; }"],
  ["M24 起手不补停表（整句删除＝闸门该挡）",
   "  if(startedAway()) awayStart();", ""],
  ["M25 跳过的 5 秒闸门抬高到永不触发（0 分钟中断又回账本）",
   "  if(usedSec() < 5) return false;", "  if(usedSec() < 0) return false;"],
  ["M26 跳过一律不记账（闸门吃过头，跑了 30 秒的跳过也消失）",
   "  if(usedSec() < 5) return false;", "  if(true) return false;"],
  ["M27 跳过按钮绕开闸门、回到旧接线（闸门函数还在，只是没人走它）",
   'if(T.kind==="focus"){ skipFocusRecord(); }',
   'if(T.kind==="focus"){ recordSession("focus", recordSec()/60, "abort", "跳过"); }'],
  ["M28 停表期间按暂停不结算（整句删除＝闸门该挡）",
   "  if(T.awayAt){ const awayMs = mono()-T.awayAt; T.awayAt=0; if(T.hold) T.awayTotal += awayMs; }\n", ""],
  ["M29 结算前先把起点清零（锚点那整行原样在，只是它前面已经没东西可结算）",
   "  if(T.awayAt){ const awayMs", "  if(T.awayAt){ T.awayAt=0; }\n  if(T.awayAt){ const awayMs"],
  /* M30–M43：本轮新加的第三道口子（整机休眠／进程被挂起）与两把静态尺（DF 日切换那一拍、TK tick 顺序）。
     分工写清楚：能在沙箱切片里 eval 的走行为级（真值表点名行）；
     tickOn／rafOn 那两段不在任何切片里，只能由静态尺 DF／TK 与锚点钉住——这类各自点名，不含混。 */
  ["M30 日切换那一拍里塞一句 pause()（跨 0 点又自己打断＝DF 该红；这一拍已抽成 onDayRoll()，尺子跟进函数体）",
   "  statsDirty();\n  refreshStats();",
   "  statsDirty();\n  pause();\n  refreshStats();"],
  ["M31 tick 里把完成判定提到休眠闸之前（醒来第一拍先按墙上钟收尾＝TK 该红；沙箱 eval 不到 tickOn，只有静态尺看得见）",
   "    suspendGuard();          // 先问\"这一拍与上一拍之间机器是不是停过\"，再读数：休眠那一大段不许烧倒计时\n    paint();\n    /* 进程被强杀/窗口被关：进行时段只丢最后 15 秒 */\n    if(++_rtBeat>=75){ _rtBeat=0; saveRT(); }\n    checkDone();",
   "    paint();\n    /* 进程被强杀/窗口被关：进行时段只丢最后 15 秒 */\n    if(++_rtBeat>=75){ _rtBeat=0; saveRT(); }\n    checkDone();\n    suspendGuard();          // 先问\"这一拍与上一拍之间机器是不是停过\"，再读数：休眠那一大段不许烧倒计时"],
  ["M32 tick 不再问休眠（整句删除＝锚点该挡）",
   "    suspendGuard();          // 先问", ""],
  ["M33 休眠判据恒不触发（锚点 SUSP_GAP_MS 原样在，只是没人比了）",
   "if(!(gap > SUSP_GAP_MS)){ T.beat = now; return; }", "if(true){ T.beat = now; return; }"],
  ["M34 醒来起表时基准没跟着挪（同一笔休眠被退好几遍）",
   "T.startAt = now; T.beat = now;", "T.startAt = now;"],
  ["M35 睡着那一大段照样固化进在场（退账形同没退）",
   "T.acc = Math.max(0, T.acc + (T.beat - T.startAt)/1000);",
   "T.acc = Math.max(0, T.acc + (now - T.startAt)/1000);"],
  ["M36 休眠那一大段不进‘离开’账（数字掉了却没人说明）", "T.awayTotal += gap;", ""],
  ["M37 休息段又被排除（凌晨醒来立刻响铃＋autoNext 自动开一段番茄）",
   "if(T.status!==\"run\" || T.hold) return;", "if(T.status!==\"run\" || T.hold || T.kind!==\"focus\") return;"],
  ["M38 严格模式只 toast 不暂停（说了却什么都没停）",
   "if(S.settings.mode===\"strict\"){ pause(); toast(\"机器停了 ",
   "if(S.settings.mode===\"strict\"){ toast(\"机器停了 "],
  ["M39 学霸模式不中断（学霸的‘离开即中断’被悄悄放宽）",
   "if(S.settings.mode===\"xueba\"){ abort(\"整机休眠／进程被挂起（学霸模式）\", gap); return; }",
   "if(S.settings.mode===\"xueba\"){ return; }"],
  ["M40 隐藏／失焦早退又被加回来（普通模式的后台休眠扣减被整条短路；锚点全部原样在）",
   "  const gap = now - T.beat;",
   "  if(document.hidden || !document.hasFocus()){ T.beat = now; return; }\n  const gap = now - T.beat;"],
  ["M41 阈值抬到 120 秒（91 秒的冻结被漏判成正常节流＝A30b 该红）",
   "const SUSP_GAP_MS = 90000;", "const SUSP_GAP_MS = 120000;"],
  ["M42 start 不刷新休眠基准（沙箱起跑即 start，两拍之差只有 1.2 秒 ⇒ 结构上判不到）",
   "T.status=\"run\"; T.startAt=mono(); T.acc=0; T.awayTotal=0; T.awayAt=0; T.hold=false;\n  beatOn();",
   "T.status=\"run\"; T.startAt=mono(); T.acc=0; T.awayTotal=0; T.awayAt=0; T.hold=false;",
   "预定惰性：run() 一设 CLK=1000 就立刻 start，下一拍差 1200ms＜60s ⇒ 判据本来就无罪可判。" +
   "真机上这条的后果是小且保守的（idle 两小时后起表会把那两小时报成‘离开’，倒计时不受影响），" +
   "而沙箱没有‘起表前的空闲’这把尺⇒ 降级为沙箱不覆盖，靠 beatOn 在 start/resume/awayEnd 三处同挂这一事实自证；" +
   "若将来给 run() 加 idle 前置事件，这条要第一个重跑。"],
  ["M43 rAF 心跳被摘（rafOn 不在切片里＝只能由锚点挡，行为级看不见，单独点名这一档）",
   "if(T.status!==\"run\" || !document.hasFocus()){ _raf = 0; return; } beatOn(); paint();",
   "if(T.status!==\"run\" || !document.hasFocus()){ _raf = 0; return; } paint();"],
  /* M44／M45：M33 改的是那句比较本身，锚点先挡（弱一档）。这两条只动阈值那个常数——
     锚点一个都不碰，两个方向都得真值表自己点名，否则"永不休眠"与"每拍都在休眠"这两种错就没人管。 */
  ["M44 休眠阈值抬到永不触发（锚点全在，判据却再也够不着）",
   "const SUSP_GAP_MS = 90000;", "const SUSP_GAP_MS = Number.MAX_SAFE_INTEGER;"],
  ["M45 休眠阈值降到 0（每一拍都当刚睡醒＝正常跑满也被退账）",
   "const SUSP_GAP_MS = 90000;", "const SUSP_GAP_MS = 0;"],
  /* M46–M56：跨午夜分桶账（2026-10-16 这一轮）。分工与前面一致——
     "整句删除"那类会被形状闸门先挡，所以每条都另配一版"锚点字节原样在、行为破掉"的注入（shadow／换常数），
     让真值表自己点名；点名不到的（结构上够不着）宁可不登记，也不要拿一条永不报警的变异凑数。 */
  ["M46 统计端不读分桶表（写完没人接＝等于没修；buildStats 里 shadow 一个空 dlCleanSplit，锚点字节原样在）",
   "function buildStats(){\n  const dayMin=new Map(), dayPomo=new Map(), hourMin=new Map(), reason=new Map();",
   "function buildStats(){\n  const dlCleanSplit = () => null;   // 变异注入\n  const dayMin=new Map(), dayPomo=new Map(), hourMin=new Map(), reason=new Map();"],
  ["M47 导入端把分桶表摘掉（cleanSession 里 shadow 空函数，锚点 const sp = dlCleanSplit(x.split, minutes); 原样在）",
   "function cleanSession(x){\n  const raw = Number(x.minutes);",
   "function cleanSession(x){\n  const dlCleanSplit = () => null;   // 变异注入\n  const raw = Number(x.minutes);"],
  ["M48 分桶表的总和对账恒通过（伪造的 split 也被拿去分账）",
   "if(!Number.isFinite(min) || Math.abs(sum - min) > 0.15 + 0.05*(out.length-1)) return null;",
   "if(!Number.isFinite(min)) return null;"],
  ["M49 多余的量从**第一片**削（recordSec 封顶时削错了头：昨天那份被吃掉、今天照旧满）",
   "for(let i=p.length-1; i>=0 && sum - target > 1e-7; i--){ const cut = Math.min(p[i][2], sum-target); p[i][2] -= cut; sum -= cut; }",
   "for(let i=0; i<p.length && sum - target > 1e-7; i++){ const cut = Math.min(p[i][2], sum-target); p[i][2] -= cut; sum -= cut; }"],
  ["M50 dlSplit 收尾不丢零片（「今天学了 0 分钟」那片又回到记录里）",
   "  return out.filter(x => x[2] > 0);", "  return out;"],
  ["M51 离开那一段也被记进桶（休息照样算专注＝用户明确不要的口径）",
   "if(da > 0){ dlWalk(da, false); T.dAway = T.awayTotal; }",
   "if(da > 0){ dlWalk(da, true); T.dAway = T.awayTotal; }"],
  ["M52 resume 的游标跳转被撤销（锚点整行原样在，紧接着一句把它退回去）",
   "  const np = Date.now(); if(np > T.posAt) T.posAt = np;",
   "  const np = Date.now(); if(np > T.posAt) T.posAt = np;\n  T.posAt = T.swAt;   // 变异注入：暂停那一段又被当作在场的起点"],
  ["M53 分桶表的 24 片上界失效（超长段的账本不再收口）",
   "  if(out.length > 24){", "  if(false){"],
  /* M54 的历史要写在台面上：它首跑是 MISSED——不是判据瞎，是 dlSplit 有两道对齐（逐片削尾＋零头并进最后一片），
     U5 那档超出量装得进最后一片，两道给出同一个答案。补了只量削尾方向的 U14（超出量装不进最后一片）之后，
     这条由 U14 点名。⇒「冗余双兜底会让单条摘除看起来无害」这一课记在这儿，不留一句解释都不给的绿。 */
  ["M54 dlSplit 完全不削尾（账本比记录多时不再对齐，split 总和≠minutes；由 U14 点名）",
   "  if(sum - target > 1e-7){", "  if(false){"],
  ["M55 dayReal 只验形状、不再回读日历（「2026-13-45」这类假日子又能供进统计）",
   "  const t = new Date(y, m-1, d);\n  return t.getFullYear() === y && t.getMonth() === m-1 && t.getDate() === d;",
   "  return true;"],
  ["M56 dayReal 的月份／日期范围守卫被摘（回读那条仍在＝能力没丢）",
   "  if(m < 1 || m > 12 || d < 1 || d > 31) return false;", "",
   "预定惰性：新 Date(2026,12,45) 会自己滚到 2027-02-14，紧跟着的回读（getMonth 12≠1、getDate≠45）就把越界全否了 ⇒ " +
   "这条守卫是第二道兜底、不是唯一承重点。摘它不减能力，所以判 INERT 而不是 MISSED；" +
   "承重的那一道由 M55 钉（那条一摘，U10g／U10i／U10j／C7 四条同时翻红）。两道都在＝多花三行，少花一处也不会漏。"],
  /* M57–M62：2026-10-23 零点这一轮。三个面各配一条：
     ① 在跑段固化（dlSync）——快照与零点那一拍都靠它；
     ② 预告只读且与真入账同源（dlPeekSplit / dlSplitFrom）；
     ③ 日切换那一拍只许固化／刷新，不许改计时状态。
     前四条走行为级（U15／U16 点名），后两条走静态尺（那一拍与 saveRT 都不在六段切片里）。 */
  ["M57 dlSync 不再固化在跑段（锚点整句还在，条件恒假 ⇒ 快照的 bk/pos 落后于 acc）",
   "if(T.status === \"run\" && !T.hold){ const d = (mono() - T.startAt)/1000; if(d > 0){ T.acc += d; T.startAt = mono(); } }",
   "if(false){ const d = (mono() - T.startAt)/1000; if(d > 0){ T.acc += d; T.startAt = mono(); } }"],
  ["M58 预告不吃未结算的尾巴（只把已固化的那截分账＝零点后的时长看不见）",
   "let left = Math.max(0, usedSec() - T.dAcc) * 1000;", "let left = 0;"],
  ["M59 预告直接改真账本（只读承诺破掉：看一眼预告就动账）",
   "const bk = T.bk.map(x => [x[0], x[1], x[2]]);", "const bk = T.bk;"],
  ["M60 暂停态不给预告（用户按了暂停、跨了零点就看不到会怎么分）",
   "if(T.status === \"idle\" || T.kind !== \"focus\" || !(T.swAt > 0)) return null;",
   "if(T.status !== \"run\" || T.kind !== \"focus\" || !(T.swAt > 0)) return null;"],
  ["M61 日切换把进度清零（DF 该红：零点一过 acc 归零＝用户报的那个形状）",
   "_lastDay = k;", "_lastDay = k;\n  T.acc = 0;"],
  ["M62 快照落盘前不固化（RT 该红：写下去的仍是落后一拍的 acc 与 bk/pos）",
   "if(T.status===\"run\") dlSync();", "if(false) dlSync();"],
];

/* 分流是一枚纯函数：真循环和下面的已知答案自检共用它，自检不许另写一份映射（另写＝自证）。 */
function classify(out, just){
  if(just) return out.rc === 0 ? "INERT" : "CHANGED";
  if(out.rc === 3) return "GATE";
  if(out.rc === 1) return "CAUGHT";
  if(out.rc === 0) return "MISSED";
  return "NOP";
}

let caught = 0, missed = 0, nop = 0, gateOnly = 0, inertOk = 0, inertChanged = 0, wrong = 0;
/* 三把静态尺（DF／TK／RT）先自证会翻红：它们看不见自己的瞎，只有已知答案能。
   这条闸门跑在变异循环之前——尺子自己瞎了的话，后面它"抓到"的也算不到它头上。 */
const RS = H.rulerSelfTest();
console.log("静态尺已知答案：" + RS.lines.map(l => (l.indexOf("FAIL") === 0 ? "✗" : "✓")).join("") +
  "（" + (RS.n - RS.bad) + "/" + RS.n + " 符）");
if(!RS.ok){ console.log(RS.lines.join("\n")); console.log("⇒ 量具自己是瞎的，证伪趟不作数"); process.exit(1); }
const baseOut = H.runWorld(BASE, "after");
console.log("基线（未变异）after 世界：" + (baseOut.rc === 0 ? "全绿 RC=0" : "RC=" + baseOut.rc + " ← 基线就不绿，先修产品再谈证伪"));
if(baseOut.rc !== 0){ console.log(baseOut.lines.join("\n")); process.exit(1); }

for(const m of MUTS){
  const [name, from, to, just] = m;
  const hits = BASE.split(from).length - 1;
  if(hits !== 1){ console.log("NOP  " + name + " ｜锚点命中 " + hits + " 处（要求恰好 1 处，绝不为凑数放宽）"); nop++; continue; }
  const mutated = BASE.replace(from, to);
  if(mutated === BASE){ console.log("NOP  " + name + " ｜改出来的字节与原字节相同"); nop++; continue; }
  const out = H.runWorld(mutated, "after");
  const red = out.lines.filter(l => l.indexOf("FAIL") === 0);
  const v = classify(out, just);
  const who = red.map(l => l.split(" ").slice(1, 2)[0]).join("／");
  if(v === "INERT"){ inertOk++; console.log("INERT " + name + " ｜真值表全绿（预定如此）：" + just); continue; }
  if(v === "CHANGED"){ inertChanged++; wrong++; console.log("CHANGED " + name + " ｜预定惰性却被挡下（rc=" + out.rc + "）⇒ 可达性变了，回来重评这条：" +
    (out.rc === 3 ? out.lines[0] : who)); continue; }
  if(v === "GATE"){ gateOnly++; console.log("GATE " + name + " ｜形状闸门挡下（弱一档；这一类删句式的错都另配了锚点保留版，那一条走的是行为级）：" + out.lines[0]); continue; }
  if(v === "CAUGHT"){ caught++; console.log("CAUGHT " + name + " ｜红 " + red.length + " 行：" + who); continue; }
  missed++; wrong++; console.log("MISSED " + name + " ｜注入静默 bug 后真值表仍然全绿 ← 判据看不见这一类错");
}
console.log("\n计数（自打，与上面逐行同源）：CAUGHT " + caught + " ／ GATE " + gateOnly + " ／ MISSED " + missed +
  " ／ INERT " + inertOk + " ／ CHANGED " + inertChanged + " ／ NOP " + nop + " ／ 登记 " + MUTS.length + " 条");
/* 分流自检：给 classify 喂五组已知答案的 rc，逐条要求落到预登记的格子里。
   它跑的是真循环调用的同一个纯函数，不是另写一份映射——另写那份等于自己给自己出题。 */
let selfBlind = 0;
const KNOWN = [
  ["rc=1 且非预定 → CAUGHT",  { rc:1, lines:["FAIL x"] }, null,        "CAUGHT"],
  ["rc=0 且非预定 → MISSED",   { rc:0, lines:[] },        null,        "MISSED"],
  ["rc=3 且非预定 → GATE",     { rc:3, lines:["RC=3"] },  null,        "GATE"],
  ["rc=0 且预定惰性 → INERT",  { rc:0, lines:[] },        "预定惰性",   "INERT"],
  ["rc=1 且预定惰性 → CHANGED",{ rc:1, lines:["FAIL x"] },"预定惰性",   "CHANGED"],
  ["rc=2（没登记过的结局）→ NOP", { rc:2, lines:[] },      null,        "NOP"],
];
for(const k of KNOWN){
  const got = classify(k[1], k[2]);
  if(got !== k[3]){ selfBlind++; console.log("FAIL 分流自检 ｜" + k[0] + " 实际判成 " + got); }
}
console.log((selfBlind ? "FAIL " : "ok   ") + "分流自检：" + KNOWN.length + " 组已知答案的 rc 各归各位（恒绿桩必须被认成漏网、预定惰性必须被认成 INERT、没登记过的结局落 NOP）");
const rc = (wrong > 0 || selfBlind > 0 || caught < 1 || (caught + gateOnly + missed + nop + inertOk + inertChanged) !== MUTS.length) ? 1 : 0;
console.log("RC=" + rc + (rc ? " ｜判据：MISSED／CHANGED／NOP 分流错乱／分类计数与登记条数对不上，任一成立即红" : " ｜判据：没有一条非预定变异能悄悄过去"));
process.exit(rc);
