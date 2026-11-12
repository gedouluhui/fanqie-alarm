/* 番茄闹钟计时口径：真代码沙箱 + 已知答案真值表（可被 falsify_timing.js 复用）
   用法：Qoder.exe(ELECTRON_RUN_AS_NODE=1) timing_harness.js <index.html> <before|after>
   · 被测函数不是手抄副本，是从 <index.html> 现盘字节里按锚点切出来 eval 的；锚点缺失直接 rc=3
     （"产品代码形状变了，真值表不作数"）。before/after 两套锚点互斥 ⇒ 同一个文件只可能过一个世界。
   · 时钟是注入的假 performance／假 Date，200ms 一格推进，完成判定照抄产品 tick 那一行。
   · expected 是开跑前按产品代码推算写死的，每行带推算依据；跑出来不一致就是真值表在报警，不是去改 expected。
   · 两个"为了让断言能读"的量具升级不算放宽判据：$() 按 id 记忆（否则 showEnd 写的字蒸发）、toast 收集进数组。 */
const fs = require("fs");
const M = 60;

const COMMON_ANCHORS = [
  ['function secsFor(kind){', "时长换算"],
  ['minutes:Math.round(Math.max(0,minutes)*10)/10', "recordSession 的 0.1 分钟取整"],
  ['kind==="focus" ? Math.max(0.2,mins) : mins', "complete 的 0.2 分钟地板"],
];
const WORLD_ANCHORS = {
  before: [
    ['function focusSec(){ return Math.max(0, usedSec() - awayNowSec()); }', "旧口径：只扣手上正开着的那段离开"],
    ['status:"idle", awayTotal:0, awayAt:0};', "旧状态量：没有 hold"],
    ['if(S.settings.mode==="xueba") playBlocked(true); }', "旧 awayStart：不冻结倒计时"],
    ['if(S.settings.timing!=="none" && usedSec()>=T.total) complete();', "旧写法：完成判定抄在 tick 里（没有 checkDone）"],
    ['day:dayKey(now), hour:now.getHours()', "旧写法：记录归属按结束时刻"],
    ['document.hidden? awayStart() : (awayEnd(), render());', "旧监听器：从最小化回来不补响"],
    ['setMotion(); awayEnd(); render(); });', "旧监听器：alt-tab 回来不补响"],
  ],
  after: [
    ['T.hold ? 0 : (mono()-T.startAt)/1000', "新口径：离开期间 usedSec 冻结"],
    ['function focusSec(){ return usedSec(); }', "新口径：离开已在 usedSec 里冻结，不再另扣一次"],
    ['if(T.awayAt) return;', "awayStart 不许重臂（blur 之后紧跟最小化是同一段离开）"],
    ['T.acc += ms/1000;', "没到阈值的短离开要还回倒计时，否则一次普通 alt-tab 就吃掉时长"],
    ['// 普通模式：界面承诺不做中断判定', "awayStart 里按模式分家"],
    ['else if(T.hold) $("tip").textContent = "正在离开 ', "停表期间表盘上要有一句话，否则用户只看到数字不动"],
    ['function checkDone(){ if(T.status==="run" && S.settings.timing!=="none" && usedSec()>=T.total) complete(); }', "完成判定只有这一份，tick 与切回窗口共用"],
    ['document.hidden? awayStart() : (awayEnd(), checkDone(), render());', "从最小化回来当场补一次完成判定"],
    ['setMotion(); awayEnd(); checkDone(); render();', "alt-tab 回来当场补一次完成判定"],
    ['T.swAt=Date.now();', "这一段记下墙上起点（归属按开始时刻）"],
    ['function startedAway(){ return !!document.hidden || !document.hasFocus(); }', "起手时在不在场的判断（只此一份）"],
    ['if(startedAway()) awayStart();', "起手时窗口已不在前台 ⇒ 当场停表，别让后台时间算成专注"],
    ['function skipFocusRecord(){', "跳过这笔账只从这一处写（跑满 5 秒才留档）"],
    ['if(T.awayAt){ const awayMs = mono()-T.awayAt; T.awayAt=0; if(T.hold) T.awayTotal += awayMs; }', "停表期间按暂停：这段离开先结算，不许在暂停态里蒸发"],
    /* 整机休眠／进程被冻：blur 与 visibilitychange 都看不见它（睡着时窗口照样"可见＋有焦点"），
       只有"两拍之间隔了多久"能把它认出来。下面四条锚点钉的是这条闸门的四个承重点。 */
    ['suspendGuard();          // 先问', "tick 每一拍先问\"两拍之间机器停过没有\"，再判完成：顺序反了休眠醒来那一拍会先按墙上钟收尾"],
    ['if(!(gap > SUSP_GAP_MS)){ T.beat = now; return; }', "没停过就把基准挪到这一拍；漏了这句，正常跑满一分钟就自曝\"休眠\""],
    ['if(T.kind!=="focus"){ render(); return; }', "休息段只把那一大段从倒计时里摘掉，不做中断判定"],
    ['if(T.status!=="run" || !document.hasFocus()){ _raf = 0; return; } beatOn(); paint();', "rAF 那一拍也当心跳（rafOn 不在沙箱切片里，这一条只能靠锚点钉住，行为级覆盖不到）"],
    /* 跨午夜分桶账（2026-10-16）：下面五条钉的是"写的人"和"读的人"都在，少一条就是半套机制。 */
    ['const sp = (dlClose(), dlSplit(recMin));', "收尾前先把在跑的零头固化，再按分桶表切两天（complete／abort 两条路各一处）"],
    ['const sp = dlCleanSplit(split, rec.minutes);', "记录只在分桶表自洽时才带 split：对不上就退回整段归一天"],
    ['const sp = dlCleanSplit(x.split, m);', "统计端真的在读分桶表（写完没人接＝等于没修）"],
    ['const np = Date.now(); if(np > T.posAt) T.posAt = np;', "暂停那一段只挪游标、一秒不进桶；钟往回走时游标不后退"],
    ['T.bk = bk; T.posAt = pos;', "进行时段快照带着分桶账落盘／恢复（老快照没这两项就按 acc 重建）"],
    ['const sp = dlCleanSplit(x.split, minutes);', "导入／备份回来的分桶表要过同一把形状闸"],
  ],
};
/* 反向锚点：这些字符串必须"不在"文件里（旧话术留在盘上就是回归） */
const WORLD_FORBIDDEN = {
  before: [],
  after: [
    ['已暂停并记录中断', "这话承诺统计里有一条中断记录，而 abort/recordSession 从来没写过这笔"],
    ['pause(Math.max(0, usedSec()-ms/1000))', "旧写法：回来才把离开那截从 usedSec 里摘走"],
    ['if(S.settings.timing!=="none" && usedSec()>=T.total) complete();', "完成判定又抄回 tick：两处会分家，最小化时补响那条就没了"],
    ['day:dayKey(now), hour:now.getHours()', "记录归属又回到结束时刻：23:50 开始的三小时会整段算到第二天"],
    ['document.hidden? awayStart() : (awayEnd(), render());', "visibilitychange 那条路的补响又没了"],
    ['setMotion(); awayEnd(); render();', "window focus 那条路的补响又没了"],
    ['if(T.status!=="run" || T.kind!=="focus" || T.hold) return;', "休眠闸又只管专注段：休息段里睡过去的那一大段又被烧进倒计时"],
    ['function recordSession(type, minutes, status, reason){', "记录端又回到四个参数：分桶表写进去也没人接"],
    ['recordSession(kind, kind==="focus" ? Math.max(0.2,mins) : mins, "done");', "complete 又不带分桶表了：跨零点那段整段挂到起表那天"],
  ],
};

function cut(SRC, a, b, why){
  const i = SRC.indexOf(a); if(i < 0) throw new Error("切片锚点缺失（" + why + "）：" + a);
  const j = SRC.indexOf(b, i); if(j < 0) throw new Error("切片终点缺失（" + why + "）：" + b);
  return SRC.slice(i, j);
}
function extract(SRC){
  return {
    KERNEL: cut(SRC, "const mono = () =>", "/* 进行中的那一段单独落盘", "计时内核"),
    CTRL: cut(SRC, "function start(kind){", "/* ---------------- DOM 小工具", "状态机与记账"),
    /* AWAY 连"离开"那两个函数和挂着它们的三个监听器一起切出来：
       驱动 blur/back 时必须走产品自己的 window blur/focus + document visibilitychange，
       否则往监听器里注入静默 bug（把补响那一拍摘掉、把 awayStart 漏挂）真值表根本看不见。 */
    AWAY: cut(SRC, "function awayStart(){", "/* ---------------- 刷新", "离开判定与它的三个监听器"),
    /* WIRE＝"跳过"那颗按钮自己的接线。不加这一片，真值表只能测 skipFocusRecord 这个函数，
       测不到"点跳过到底走哪条路"——而 0 分钟 abort 那条记录恰恰是从按钮接线里写进去的。 */
    WIRE: cut(SRC, '$("btnSkip").onclick', '$("btnReset").onclick', "跳过按钮的接线"),
    /* 分桶账的"读的那一半"：buildStats 与 cleanSession 都不在上面四片里。
       不加这两片，真值表只能证明 split 被写进了记录，证不出统计面板按它分账——
       而"写了没人接"正是这一类改动最容易留下的空转（本轮把它做成一把尺，见 splitConsumeCheck）。 */
    CLEAN: cut(SRC, "function cleanSession(x){", "function capSessions(", "导入净化"),
    STATS: cut(SRC, "function buildStats(){", "/* 统计索引缓存", "统计聚合"),
  };
}
function gate(SRC, world){
  for(const [m, why] of COMMON_ANCHORS.concat(WORLD_ANCHORS[world] || [])){
    if(SRC.indexOf(m) < 0) throw new Error("锚点缺失（" + why + "）：" + JSON.stringify(m));
  }
  for(const [m, why] of (WORLD_FORBIDDEN[world] || [])){
    if(SRC.indexOf(m) >= 0) throw new Error("反向锚点仍在文件里（" + why + "）：" + m);
  }
}

/* ---- 虚拟时钟：CLK 从 1000ms 起（mono() 恰好为 0 会让 awayAt 的"0 即假值"在沙箱里误判，真窗口不会） ---- */
let CLK = 1000;
let BASE = new Date(2026, 9, 15, 9, 0, 0).getTime();   // 默认本地 09:00；行里可用 c.base 改到午夜前，验归属口径
const RealDate = Date;
/* dayKey 的一份实现，注入沙箱与量具自己要的（U12 摆长账本要用）——只此一份，不许两头各写一遍 */
const dayKeyOf = (d) => d.getFullYear() + "-" + String(d.getMonth()+1).padStart(2,"0") + "-" + String(d.getDate()).padStart(2,"0");
class FakeDate extends RealDate {
  constructor(...a){ if(a.length) super(...a); else super(BASE + CLK); }
  static now(){ return BASE + CLK; }
}
const perf = { now: () => CLK };
/* 假 window／假 document 把监听器收下来，驱动事件时按真浏览器的成对顺序放：
   切走＝visibilitychange(hidden=true) + window blur；回来＝visibilitychange(hidden=false) + window focus。 */
const HANDLERS = {};
const win = { performance: perf, addEventListener: (t, f) => { (HANDLERS[t] = HANDLERS[t] || []).push(f); } };
/* hasFocus 跟着 hidden 走：真窗口"看不见"时必然也没焦点，反向不成立（可见但失焦要单独建模用 cfg.blur0）。 */
const doc = { hidden: false, hasFocus: () => !doc.hidden, addEventListener: (t, f) => { (HANDLERS[t] = HANDLERS[t] || []).push(f); } };
function fire(name){ for(const f of (HANDLERS[name] || [])) f({}); }
/* 两条路分开走，别混成一次：alt-tab 只发 window blur/focus（页面还看得见）；
   最小化/切标签才发 visibilitychange。合成一条会互相顶掉——两条路各有一行真值表钉着。 */
function evBlur(){ fire("blur"); }                                    // 切到别的窗口（页面仍可见）
function evBack(){ fire("focus"); }                                   // 切回来
function evHide(){ doc.hidden = true; fire("visibilitychange"); }      // 最小化/换标签
function evShow(){ doc.hidden = false; fire("visibilitychange"); }     // 从最小化回来

const NODES = new Map();
const TOASTS = [];
function el(id){
  if(NODES.has(id)) return NODES.get(id);
  const n = { id, textContent:"", innerHTML:"", value:"", style:{}, title:"", dataset:{}, disabled:false, onclick:null,
    classList:{ add(){}, remove(){}, toggle(){}, contains(){ return false; } },
    querySelectorAll(){ return []; }, querySelector(){ return null; }, setAttribute(){}, getAttribute(){ return null; },
    appendChild(){}, focus(){}, click(){} };
  NODES.set(id, n); return n;
}

function makeWorld(parts, cfg){
  NODES.clear(); TOASTS.length = 0;
  for(const k in HANDLERS) delete HANDLERS[k];
  doc.hidden = false;
  /* cfg.away0＝"起手时窗口已经不在前台"：真浏览器里这就是自动下一环最常发生的那一刻
     （上一段响铃时用户早切走了）。旧代码在这时起手不会停表，整段后台时间被算成专注。 */
  if(cfg && cfg.away0) doc.hidden = true;
  BASE = (cfg && cfg.base !== undefined) ? cfg.base : new Date(2026, 9, 15, 9, 0, 0).getTime();
  const S = { settings:Object.assign({focus:25, short:5, long:15, every:4, autoNext:false, mode:"normal", timing:"count",
                         away:15, allowPause:true, dark:false, simple:false}, cfg || {}),
              sessions:[], tasks:[], collections:[], cycle:0, activeTaskId:null, notes:[] };
  const body = parts.KERNEL + "\n" + parts.CTRL + "\n" + parts.AWAY + "\n" + parts.WIRE + "\n" +
    parts.CLEAN + "\n" + parts.STATS + "\n" +
    'return {T, S, secsFor, usedSec, awayNowSec, focusSec, recordSec, remainSec, progress, ' +
    'checkDone:(typeof checkDone!=="undefined"?checkDone:null), ' +
    'suspendGuard:(typeof suspendGuard!=="undefined"?suspendGuard:null), beatOn:(typeof beatOn!=="undefined"?beatOn:null), ' +
    'skipFocusRecord:(typeof skipFocusRecord!=="undefined"?skipFocusRecord:null), startedAway:(typeof startedAway!=="undefined"?startedAway:null), ' +
    'dlReset:(typeof dlReset!=="undefined"?dlReset:null), dlWalk:(typeof dlWalk!=="undefined"?dlWalk:null), ' +
    'dlBook:(typeof dlBook!=="undefined"?dlBook:null), dlSync:(typeof dlSync!=="undefined"?dlSync:null), ' +
    'dlClose:(typeof dlClose!=="undefined"?dlClose:null), ' +
    'dlSplit:(typeof dlSplit!=="undefined"?dlSplit:null), dlSplitFrom:(typeof dlSplitFrom!=="undefined"?dlSplitFrom:null), ' +
    'dlPeekSplit:(typeof dlPeekSplit!=="undefined"?dlPeekSplit:null), ' +
    'dlCleanSplit:(typeof dlCleanSplit!=="undefined"?dlCleanSplit:null), ' +
    'dlCleanBK:(typeof dlCleanBK!=="undefined"?dlCleanBK:null), dlText:(typeof dlText!=="undefined"?dlText:null), ' +
    'dayReal:(typeof dayReal!=="undefined"?dayReal:null), ' +
    'cleanSession:(typeof cleanSession!=="undefined"?cleanSession:null), buildStats:(typeof buildStats!=="undefined"?buildStats:null), ' +
    'fmt, ' +
    'start, pause, resume, stopAll, complete, abort, nextKind, recordSession, awayStart, awayEnd, labelOf, activeTask};';
  const names = ["S","window","document","performance","Date","$","toast","render","renderAll","save","saveRT","storageOK","dualReadOnly",
                 "dayKey","stats","setNoise","setMotion","playBlocked","playAlarm","exitFs","requestFs","rafOff","statsDirty","openReason","esc","clone"];
  const vals = [S, win, doc, perf, FakeDate, el, (m) => TOASTS.push(m), () => {}, () => {}, () => {}, () => {}, false, false,
                dayKeyOf,
                () => ({pomos:0}), () => {}, () => {}, () => {}, () => {}, () => {}, () => {}, () => {},
                (x) => String(x), (x) => x];
  return new Function(...names, body)(...vals);
}

/* 产品的 tick 是 200ms 一次；这里逐格推进。完成判定优先调产品自己的 checkDone()，
   沙箱不再抄那句谓词；老世界里没有这个函数，留一条只服务于 before 的兜底（新代码永远走上面那条）。 */
function step(w, sec){
  const end = CLK + sec * 1000;
  while(CLK < end){
    CLK = Math.min(end, CLK + 200);
    /* 拍的顺序照抄产品 tick：先问"上一拍到这一拍之间机器停过没有"，再判完成。
       顺序反了就不是数值差一点的事——醒来那一拍会先按墙上钟把这段收尾，闸门永远追在后面。 */
    if(w.suspendGuard) w.suspendGuard();
    if(w.checkDone) w.checkDone();
    else if(w.T.status === "run" && w.S.settings.timing !== "none" && w.usedSec() >= w.T.total) w.complete();
  }
}
function run(parts, evts, cfg){
  CLK = 1000;
  const w = makeWorld(parts, cfg);
  /* 前提当场断言：监听器要是没挂上，blur/back 就成了空操作，整行绿得没有意义。 */
  const missing = ["visibilitychange","blur","focus"].filter(t => !(HANDLERS[t] || []).length);
  if(missing.length) throw new Error("监听器没挂上（缺 " + missing.join("/") + "）⇒ 这一行不作数");
  const reads = [];
  w.start("focus");
  let last = 0;
  for(const e of evts){
    if(e[0] === "adv"){ step(w, e[1] - last); last = e[1]; }
    /* advq＝把墙钟推过去、但一拍都不跑（真浏览器把隐藏页的定时器降频到一分钟一拍，进程被挂起时更狠）。
       没有这把尺，"铃迟到"这件事在沙箱里根本量不出来：adv 每 200ms 就补一次判定，永远追得上。
       整机休眠／渲染进程被冻结也用这把尺：睡着时窗口照样"可见＋有焦点"，blur／visibilitychange
       一个都不发，唯一留下的痕迹就是"两拍之间隔了 160 分钟"（见 A23／A24 与 before 世界的 B14）。 */
    else if(e[0] === "advq"){ CLK += (e[1] - last) * 1000; last = e[1]; }
    /* beatq＝反面对照：rAF 那一拍还在跑、200ms 定时器却被饿掉。产品里 rafOn 不在任何切片里，
       沙箱只能显式调它的心跳函数。用它钉住判据的语义——看的是"两拍之间有没有跑过东西"，
       不是"墙上钟走了多久"；把 beatOn() 从循环里摘掉的话，这条真值表看不见（只能靠锚点），已在 A25 的 why 里点名。 */
    else if(e[0] === "beatq"){ const endq = CLK + (e[1] - last) * 1000;
      while(CLK < endq){ CLK = Math.min(endq, CLK + 200); if(!w.beatOn) throw new Error("这个世界的代码里没有 beatOn ⇒ 这一行不作数"); w.beatOn(); }
      last = e[1]; }
    else if(e[0] === "blur") evBlur();             // 走产品自己的 window blur 监听器，不直接调 awayStart
    else if(e[0] === "back") evBack();             // 同上：awayEnd／补响都由那几行代码决定
    else if(e[0] === "hide") evHide();             // 最小化：document visibilitychange
    else if(e[0] === "show") evShow();
    else if(e[0] === "pause") w.pause();
    else if(e[0] === "skip"){
      /* 走"跳过"那颗按钮自己的 onclick（WIRE 切片把它 eval 进沙箱了）：
         0 分钟 abort 那条记录本来就是从按钮接线里写进去的，只测函数测不到接线。 */
      const n = NODES.get("btnSkip");
      if(!n || typeof n.onclick !== "function") throw new Error("跳过按钮的 onclick 没挂上 ⇒ 这一行不作数");
      n.onclick();
    }
    else if(e[0] === "resume") w.resume();
    else if(e[0] === "read") reads.push(w.recordSec() / 60);
    else if(e[0] === "stop") w.abort("手动结束");
    else throw new Error("不认识的事件 " + e[0]);
  }
  const s = w.S.sessions[0] || null;
  return { min: s ? s.minutes : null, status: s ? s.status : null, reason: s ? s.reason : null, n: w.S.sessions.length,
           day: s ? s.day : null, hour: s ? s.hour : null,
           split: s && Array.isArray(s.split) ? s.split : null,
           bkMin: (w.T.bk || []).map(x => [x[0], x[1], Math.round(x[2] * 10) / 10 / 60]),
           awayMin: w.T.awayTotal / 60000, statusNow: w.T.status, usedMin: w.usedSec() / 60, reads,
           toasts: TOASTS.slice(), endSub: NODES.has("endSub") ? NODES.get("endSub").textContent : "" };
}

const ROWS = {
  before: [
    {n:"B1 普通·3h·结束前10分切走不回", e:[["adv",170*M],["blur"],["adv",200*M]], c:{mode:"normal",focus:180},
     min:170, st:"done", why:"170min 处 blur，警报那刻 awayNow=10min ⇒ focusSec=180−10（用户报的正是这个数）"},
    {n:"B2 普通·3h·切走10分又回来", e:[["adv",170*M],["blur"],["adv",175*M],["back"],["adv",200*M]], c:{mode:"normal",focus:180},
     min:180, st:"done", why:"回来时 awayAt=0 ⇒ 结束时一分不扣 ⇒ 180。B1/B2 同设置两个数＝非确定性"},
    {n:"B3 普通·3h·一开始就走", e:[["blur"],["adv",200*M]], c:{mode:"normal",focus:180},
     min:0.2, st:"done", why:"全程 blur ⇒ focusSec≈0 ⇒ 被 Math.max(0.2,mins) 兜到地板（“甚至更少”）"},
    {n:"B4 普通·3h·6秒的alt-tab压在结束点", e:[["adv",179.9*M],["blur"],["adv",200*M]], c:{mode:"normal",focus:180},
     min:179.9, st:"done", why:"警报在 blur 后约 6s 触发 ⇒ 扣 6s ⇒ 一位普通 alt-tab 就能抖出小数"},
    {n:"B5 学霸·100分专注+10分离开", e:[["adv",100*M],["blur"],["adv",110*M],["back"]], c:{mode:"xueba",focus:180},
     min:110, st:"abort", why:"awayEnd 先把 awayAt 归零再 abort ⇒ 10 分钟离开被算进专注（反方向错）"},
    {n:"B6 严格·结束前10分切走不回", e:[["adv",170*M],["blur"],["adv",200*M]], c:{mode:"strict",focus:180,away:15},
     min:170, st:"done", why:"警报在人不在时把这段“完成”掉；回来时 status≠run ⇒ 严格模式的中断判定整条没跑"},
    {n:"B7 重复臂·blur 后又最小化（严格）", e:[["adv",80*M],["blur"],["adv",90*M],["hide"],["adv",95*M],["back"]], c:{mode:"strict",focus:180,away:15},
     min:null, away:5, st:"pause", used:90, why:"真实离开 15 分钟；第二次 blur 把 awayAt 重臂成 5 分钟前 ⇒ awayTotal 只记 5 分钟、在场被抬到 90 分"},
    {n:"B8 不计时·3h·全程在场", e:[["adv",180*M],["stop"]], c:{mode:"strict",focus:180,timing:"none"},
     min:180, st:"abort", why:"timing=none 不该被 total 封顶；这行两个世界都该是 180，用来钉住“修复没碰对的那部分”"},
    /* B9/B11 钉的是"修复前那两处"：切回窗口不补响、记录归属按结束时刻。
       中间那段用 advq（一拍都不跑）——这正是生产场景：隐藏页的定时器被降频，判定只能靠回来的那一拍。
       用 adv 的话沙箱每 200ms 就替产品补一次判定，"迟到"永远量不出来（这是这一对行原先的零鉴别力）。 */
    {n:"B9 严格·短离开压在结束点·切回窗口", e:[["adv",179.99*M],["blur"],["advq",180.1*M],["back"]], c:{mode:"strict",focus:180,away:15},
     min:null, st:"run", why:"旧监听器回来只 render，完成判定还压在下一拍 tick 上：浏览器把隐藏页降频到一分钟一拍时，铃就迟一分钟（数字不受影响，迟到的是补响）"},
    {n:"B11 严格·最小化压在结束点·从最小化回来", e:[["adv",179.99*M],["hide"],["advq",180.1*M],["show"]], c:{mode:"strict",focus:180,away:15},
     min:null, st:"run", why:"旧 visibilitychange 回来那拍同样没有补响（与 B9 是两条不同的监听器：alt-tab 走 window focus，最小化走 visibilitychange）"},
    {n:"B10 普通·23:50 开始的 3h（跨午夜）", e:[["adv",181*M]], c:{mode:"normal",focus:180,base:new Date(2026,9,15,23,50,0).getTime()},
     min:180, st:"done", dayExp:"2026-10-16", hourExp:2,
     why:"旧写法 day/hour 取的是记录那一刻 ⇒ 三个小时整段记到第二天凌晨，23 点那个时段是空的"},
    {n:"B12 严格·起手时窗口就在后台·10 分钟没人看", e:[["adv",10*M]], c:{mode:"strict",focus:180,away0:true},
     min:null, st:"run", used:10, nExp:0,
     why:"旧代码只在 blur／visibilitychange 里停表：自动下一环在用户早已切走时起手，没人给它补这一拍 ⇒ 后台的 10 分钟全算成在场（新代码这里应是 0，见 A18）"},
    {n:"B13 严格·刚点上就按跳过", e:[["adv",3],["skip"]], c:{mode:"strict",focus:180},
     min:0.1, st:"idle", nExp:1,
     why:"旧接线无条件记一笔 ⇒ 统计里真躺着 [focus, abort, 跳过] 这条中断（真浏览器实测过），中断次数与成功率分母都被它顶高。" +
         "期望值 0.1 不是推算而是盘上量到的：recordSession 把分钟数取整到 0.1，3 秒=0.05 分被抬成 0.1 分——" +
         "这条恰好还说明旧口径连“0 分钟”都记不出真值，跳过 3 秒也得占 0.1 分（新代码这里是 0 条，见 A21）"},
    {n:"B14 普通·23:00 起表跑 30 分后整机休眠 160 分", e:[["adv",30*M],["advq",190*M],["adv",190*M+0.2]],
     c:{mode:"normal",focus:180,base:new Date(2026,9,15,23,0,0).getTime()},
     min:180, st:"done", nExp:1, dayExp:"2026-10-16", hourExp:2,
     why:"旧代码没有休眠这一闸：睡着的 160 分钟照样烧倒计时（blur／visibilitychange 在睡眠期间一个都不发），" +
         "醒来第一拍就判 done——用户说的“过了十二点它自己就打断”发作的就是它；归属又取记录那一刻 ⇒ 整段跳到第二天凌晨 2 点。" +
         "对照 A23／A24：同事件、结局不同"},
    {n:"B15 普通·22:00 起跑满 3 小时（旧世界的全部家当）", e:[["adv",181*M]],
     c:{mode:"normal",focus:180,base:new Date(2026,9,15,22,0,0).getTime()},
     min:180, st:"done", dayExp:"2026-10-16", hourExp:1, splitExp:null,
     why:"这一行钉的是「旧世界没有分桶账」这件事本身：180 分整段挂在第二天凌晨 1 点那一天（归属按结束时刻），" +
         "昨天 0 分、今天 180 分。新代码同事件应是昨天 120／今天 60（见 A32）。" +
         "splitExp:null＝记录里不该有 split 这一项；将来谁把旧写法原样搬回来，这一行会立刻变红（因为它量的是“没有分桶表”）"},
  ],
  after: [
    {n:"A1 普通·3h·结束前10分切走不回", e:[["adv",170*M],["blur"],["adv",200*M]], c:{mode:"normal",focus:180},
     min:180, st:"done", why:"普通模式按界面承诺不做中断判定 ⇒ 设多久记多久"},
    {n:"A2 普通·3h·切走10分又回来", e:[["adv",170*M],["blur"],["adv",175*M],["back"],["adv",200*M]], c:{mode:"normal",focus:180},
     min:180, st:"done", why:"与 A1 同数：离开时机不再改变结果"},
    {n:"A3 普通·3h·一开始就走", e:[["blur"],["adv",200*M]], c:{mode:"normal",focus:180},
     min:180, st:"done", why:"同上，0.2 地板在这一档不再出现"},
    {n:"A4 普通·3h·6秒的alt-tab压在结束点", e:[["adv",179.9*M],["blur"],["adv",200*M]], c:{mode:"normal",focus:180},
     min:180, st:"done", why:"抖动消失：一位 alt-tab 不该改分钟数"},
    {n:"A5 学霸·100分专注+10分离开", e:[["adv",100*M],["blur"],["adv",110*M],["back"]], c:{mode:"xueba",focus:180},
     min:100, st:"abort", want:"离开 10 分钟没计入", why:"blur 那刻固化 acc ⇒ 离开既不计入也不烧倒计时 ⇒ 中断记在场的 100 分钟，toast 还要说清那 10 分钟去哪了"},
    {n:"A6 严格·结束前10分切走不回", e:[["adv",170*M],["blur"],["adv",200*M]], c:{mode:"strict",focus:180,away:15},
     min:null, st:"run", used:170, why:"倒计时在人不在时停住 ⇒ 警报不该在离开期间把这段“完成”掉"},
    {n:"A7 重复臂·blur 后又最小化（严格）", e:[["adv",80*M],["blur"],["adv",90*M],["hide"],["adv",95*M],["back"]], c:{mode:"strict",focus:180,away:15},
     min:null, away:15, st:"pause", used:80, why:"第二次 blur 不许重臂 ⇒ awayTotal 记满 15 分钟、在场停在 80 分"},
    {n:"A8 严格·8秒短离开", e:[["adv",60*M],["blur"],["adv",60*M+8],["back"],["adv",200*M]], c:{mode:"strict",focus:180,away:15},
     min:180, st:"done", away:0, why:"没到 15 秒阈值 ⇒ 那 8 秒还给倒计时 ⇒ 照常 180，且不计入“已离开”"},
    {n:"A9 不计时·3h·全程在场", e:[["adv",180*M],["stop"]], c:{mode:"strict",focus:180,timing:"none"},
     min:180, st:"abort", why:"与 B8 同数：这条改动不该碰到 timing=none"},
    {n:"A10 严格·60分后离开40分·回来继续跑满", e:[["adv",60*M],["blur"],["adv",100*M],["back"],["resume"],["adv",300*M]], c:{mode:"strict",focus:180,away:15},
     min:180, st:"done", away:40, want:"离开 40 分钟没计入",
     why:"判定中断→暂停→用户按继续→倒计时从 60 分接着走；墙上 4 小时但专注 180，结束弹层必须自己说清离开 40 分钟"},
    {n:"A11 学霸·全程没离开过的 3h", e:[["adv",200*M]], c:{mode:"xueba",focus:180},
     min:180, st:"done", away:0, why:"没有 blur 就一行都不该变：这条是「新口径没把正常路径改坏」的假阳性对照"},
    {n:"A12 不计时·跑到 4 小时才结束", e:[["adv",240*M],["stop"]], c:{mode:"strict",focus:180,timing:"none"},
     min:240, st:"abort", why:"不计时模式下跑了 4 小时就该记 4 小时，不能被 180 分钟的设定封顶"},
    {n:"A13 离开途中直接读数（不许扣两遍）", e:[["adv",60*M],["blur"],["adv",70*M],["read"],["adv",71*M]], c:{mode:"strict",focus:180,away:15},
     min:null, st:"run", readExp:[60],
     why:"停表之后 usedSec 就已经是专注秒数；谁再来减一次 awayNowSec 就扣了两遍。当前 UI 上没有「离开途中结算」这个入口，这一行钉的是口径自洽（将来加了入口也不会错），不是可达路径"},
    {n:"A14 短离开退款要当场对上账（在场＝墙上）", e:[["adv",60*M],["blur"],["adv",60*M+8],["back"],["read"]], c:{mode:"strict",focus:180,away:15},
     min:null, st:"run", used:60.1333, readExp:null, away:0,
     why:"60 分在场 + 8 秒短离开 ⇒ 回来那 8 秒必须回到在场里（3608 秒＝60.1333 分）。退款被吃掉的话这里掉回 60.0，差 0.13 分，超过 0.01 容差。A8 看不见这个错（它最后照样跑到 180），所以账要当场对，不能等结束对"},
    {n:"A15 短离开压在结束点·切回窗口当场补响", e:[["adv",179.99*M],["blur"],["advq",180.1*M],["back"]], c:{mode:"strict",focus:180,away:15},
     min:180, st:"done", away:0, why:"退款后 usedSec 已越过 total，而这段用 advq（一拍都没跑）⇒ 只有监听器里那句 checkDone 能把这段收尾。与 B9 同事件、结局不同：这一行的绿就是“铃不再等下一拍”的证据（M20 拿空函数顶掉它，红的就是这一行）"},
    {n:"A17 最小化压在结束点·从最小化回来当场补响", e:[["adv",179.99*M],["hide"],["advq",180.1*M],["show"]], c:{mode:"strict",focus:180,away:15},
     min:180, st:"done", away:0, why:"与 A15 同一场景、另一条监听器：alt-tab 回来走 window focus，从最小化回来走 visibilitychange。两条路各钉一行，少接一条就红一条（M21 对应这一行；与 B11 同事件、结局不同）"},
    {n:"A16 普通·23:50 开始的 3h（跨午夜）", e:[["adv",181*M]], c:{mode:"normal",focus:180,base:new Date(2026,9,15,23,50,0).getTime()},
     min:180, st:"done", dayExp:"2026-10-15", hourExp:23,
     splitExp:[["2026-10-15",23,10],["2026-10-16",0,60],["2026-10-16",1,60],["2026-10-16",2,50]],
     why:"凌晨 1:50 响铃，但这段属于 23:50 开始的那一天：day 2026-10-15、hour 23（旧写法记成 10-16 的 2 点，三小时整段跳到第二天）。" +
         "分桶账（跑前推算）：起表那一刻是 23:50:01（CLK 从 1000ms 起，不是整点），23 点那一格只吃得下 9′59″⇒取整 10 分；" +
         "0 点以后 170 分按整点切成 60／60／50（2 点那格从 02:00 吃到 02:50:01＝50.02 分，取整 50）⇒ 昨天 10 分、今天 170 分"},
    {n:"A18 严格·起手时窗口就在后台·10 分钟没人看", e:[["adv",10*M],["back"]], c:{mode:"strict",focus:180,away:15,away0:true},
     min:null, st:"pause", used:0, away:10, nExp:0,
     why:"start() 当场补一次“离开”：10 分钟后台一秒都不算在场（旧代码是 10 分钟全算，见 B12），回来按阈值结算成“已离开”并暂停"},
    {n:"A19 普通·起手时窗口就在后台·10 分钟后回来跑满", e:[["adv",10*M],["back"],["adv",200*M]], c:{mode:"normal",focus:180,away0:true},
     min:180, st:"done", away:0,
     why:"普通模式的承诺优先：界面写的是“不做中断判定”，所以起手在后台也不停表，设 180 分就记 180 分（与 A18 是同一个 cfg，只差模式）"},
    {n:"A20 严格·离开途中按暂停", e:[["adv",60*M],["blur"],["adv",61*M],["pause"]], c:{mode:"strict",focus:180,away:15},
     min:null, st:"pause", away:1, nExp:0,
     why:"停表期间切进暂停态，这一笔离开必须先结算进“本次已离开”；旧写法只把 awayAt 归零，那 1 分钟既不在账上也不在表盘上（蒸发）"},
    {n:"A21 严格·刚点上就按跳过", e:[["adv",3],["skip"]], c:{mode:"strict",focus:180},
     min:null, st:"idle", nExp:0,
     why:"跑满 5 秒才留档：3 秒的“跳过”不该在统计里留一条 0 分钟中断（旧接线留了，见 B13）。走的是那颗按钮自己的 onclick"},
    {n:"A22 普通·跑了 30 秒按跳过", e:[["adv",30],["skip"]], c:{mode:"normal",focus:180},
     min:0.5, st:"idle", nExp:1,
     why:"这条是 A21 的假阳性对照：闸门只吃“没跑过东西”的那几秒，跑了 30 秒照旧记 0.5 分——把它改成“一律不记”这条就红。" +
         "用普通模式：严格／学霸下超过 20 秒的跳过要先走“结束原因”弹窗（那是另一条路，由 abort 记账），落不到这个闸门上"},
    /* A23–A28：整机休眠／渲染进程被冻结这一道口子（用户报的“过了十二点它自己就打断”）。
       睡眠期间窗口照样“可见＋有焦点”，blur／visibilitychange 一个都不发 ⇒ 唯一能用的证据是两拍之差。
       事件用现成的 advq（一拍都不跑）来建模，不另立新名字——同一只钟只有一个机制。
       away 期望值里的 0.2/M 不是凑数：判据量的是两拍之间，醒来那一拍自己也走了 200ms，
       这一笔差是推算出来的（写死在这里，跑出来对不上就是产品或量具错了）。 */
    {n:"A23 普通·23:00 起表跑 30 分后整机休眠 160 分（醒来那一拍不许收尾）", e:[["adv",30*M],["advq",190*M],["adv",190*M+0.2]],
     c:{mode:"normal",focus:180,base:new Date(2026,9,15,23,0,0).getTime()},
     min:null, st:"run", used:30, away:160 + 0.2/M, nExp:0,
     why:"睡着的 160 分钟既不计入专注也不烧倒计时：醒来第一拍表盘仍停在 30 分、这段还在跑（旧代码这里当场 done，见 B14）。" +
         "nExp 0＝没被偷偷收尾；跨午夜这件事本身不再产生任何中断"},
    {n:"A24 普通·同上一段，醒来后接着跑完 ⇒ 仍记 180 分、仍归属前一天 23 点", e:[["adv",30*M],["advq",190*M],["adv",340*M+0.2]],
     c:{mode:"normal",focus:180,base:new Date(2026,9,15,23,0,0).getTime()},
     min:180, st:"done", dayExp:"2026-10-15", hourExp:23, away:160 + 0.2/M,
     splitExp:[["2026-10-15",23,30],["2026-10-16",2,50],["2026-10-16",3,60],["2026-10-16",4,40]],
     why:"用户要的就是这个数：设 180 分就记 180 分，墙上过了 5 小时40 分也不打折；" +
         "归属按 T.swAt（23:00 起表）算 ⇒ 还是前一天 23 点那一格（旧写法记到第二天凌晨，见 B14）。" +
         "分桶账（跑前推算）：在场 30 分整段在 10-15 的 23 点格；睡着的 160 分只挪游标、不进任何一天 ⇒ 游标落到 02:10:01.2；" +
         "剩下的 150 分从那儿按整点切＝2 点 49.98→50、3 点 60、4 点 40 ⇒ 昨天 30／今天 150。" +
         "这一行同时钉住用户要的三件事：跨零点不打断、睡着那一大段不算专注、剩下的按天分对"},
    {n:"A25 假阳性对照·定时器被饿掉 5 分钟，但 rAF 那一拍还在跑", e:[["adv",60*M],["beatq",65*M],["adv",65*M+0.2]],
     c:{mode:"normal",focus:180},
     min:null, st:"run", used:65, away:0,
     why:"判据看的是“两拍之间有没有跑过东西”，不是“墙上钟走了多久”：只要有心跳，一秒都不许退成离开。" +
         "诚实交代覆盖半径：沙箱里 beatq 调的是产品自己的 beatOn()，rafOn 不在任何切片内 ⇒ “rAF 循环里确实调了它”这一条只能靠锚点钉（WORLD_ANCHORS.after 第 4 条），行为级看不见；" +
         "真机也没测过（需要合盖再开盖，本轮没做）"},
    {n:"A26 严格·跑 30 分后整机休眠 160 分 ⇒ 暂停并说清停了多久", e:[["adv",30*M],["advq",190*M],["adv",190*M+0.2]],
     c:{mode:"strict",focus:180,away:15},
     min:null, st:"pause", used:30, away:160 + 0.2/M, nExp:0, want:"机器停了 160 分钟，已暂停",
     why:"严格模式的承诺是“机器停了要跟我说清楚”：暂停＋toast 报 160 分钟；在场仍停在 30 分，按继续就接着跑"},
    {n:"A27 学霸·跑 30 分后整机休眠 160 分 ⇒ 当场中断，只记在场的 30 分", e:[["adv",30*M],["advq",190*M],["adv",190*M+0.2]],
     c:{mode:"xueba",focus:180},
     min:30, st:"abort", nExp:1, want:"离开 160 分钟没计入",
     why:"学霸模式：这段没跑完就结束，账上记在场的 30 分钟（旧口径这里会记成睡着之后的 180 分）；" +
         "中断的 toast 必须自己说清那 160 分钟去哪了，否则数字看上去像随机掉的"},
    {n:"A28 严格·自动接上的休息段里整机休眠 40 分 ⇒ 休息不许在醒来第一拍自己完成", e:[["adv",30*M],["advq",70*M],["adv",70*M+0.2]],
     c:{mode:"strict",focus:30,short:5,autoNext:true},
     min:30, st:"run", used:0, away:40 + 0.2/M, nExp:1,
     why:"休息段不做中断判定（那是专注段的政策），但睡着那 40 分钟同样不许烧休息的倒计时——" +
         "否则凌晨醒来立刻响铃、还 autoNext 自动开一段番茄，正是“半夜自己打断”的另一种表现。" +
         "nExp 1＝只留下刚跑完的那段专注；min 30＝sessions[0] 仍是那段专注"},
    /* A29／A30／A31 钉的是同一道闸的三个面：它只在"人此刻在这个窗口上"时动账，且隐藏期间的基准要跟着拍子走。
       A29 由变异 M42（摘掉整道 early return）点名，A31 由 M43（留着 return 但不挪基准）点名——
       少了这两条变异，这三行看着都绿，其实谁也没量到"隐藏"这一路。 */
    {n:"A29 普通·切到别的标签 40 分钟且一拍都没跑，人还没回来 ⇒ 这一拍不许动账", e:[["adv",30*M],["hide"],["advq",70*M],["adv",70*M+0.2]],
     c:{mode:"normal",focus:180},
     min:null, st:"run", used:70, away:0,
     why:"隐藏期间这本账归 awayStart 那一路（普通模式按界面承诺照计），休眠闸只在“可见＋有焦点”时说话；" +
         "少了这道 early return，这一拍会把 40 分钟退成“离开”，表盘当场少 40 分钟"},
    {n:"A30 普通·同上但人已切回窗口 ⇒ 那 40 分钟退成“离开”", e:[["adv",30*M],["hide"],["advq",70*M],["show"],["adv",70*M+0.2]],
     c:{mode:"normal",focus:180},
     min:null, st:"run", used:30, away:40 + 0.2/M,
     why:"诚实记账的代价，写清楚而不是藏起来：普通模式承诺“不做中断判定”＝不打断、不暂停，" +
         "但应用自己一拍都没跑的那 40 分钟不再算成专注（旧代码会照烧，那是“设 3 小时记 170／240”的另一个方向）。" +
         "隐藏但节拍照常（每 200ms 一拍）的情况由 A31 钉住：那 40 分钟仍照计，一秒不退"},
    {n:"A31 普通·隐藏 40 分钟但节拍照常在跑（真·切标签页），回来一秒都不许退", e:[["adv",30*M],["hide"],["adv",70*M],["show"],["adv",70*M+0.2]],
     c:{mode:"normal",focus:180},
     min:null, st:"run", used:70, away:0,
     why:"这一行钉的是隐藏分支里那句“基准要跟着挪”：隐藏期间定时器照样在拍（哪怕被降频到一分钟一拍），" +
         "T.beat 就得跟着走；只 return 不挪基准的话，回来第一拍量到的“两拍之差”＝整个隐藏期，" +
         "普通模式会把照常跑着的 40 分钟误退成“离开”（M43 专测这一条）。" +
         "隐藏＋一拍都没跑（advq）时这道闸确实分不清“节流”与“睡着”，那种情况按睡着处理，见 A30"},
    /* A32–A36：跨零点的分桶账（用户 2026-10-16 提的那两条要求：0 点不许打断＋纯学习时间按日历日分对）。
       期望值全部是跑前按"游标从 swAt 起、按整点走"推算写死的，包括 22:00:01 起表带来的那一秒偏移——
       那一秒使每个"整点格"少 1 秒（59.98→取整 60.0），并使 1 秒的尾格取整成 0.0 后被丢掉（A34／A35 钉这一条）。 */
    {n:"A32 普通·22:00 起跑满 3 小时（用户举的第一个例子）", e:[["adv",181*M]],
     c:{mode:"normal",focus:180,base:new Date(2026,9,15,22,0,0).getTime()},
     min:180, st:"done", nExp:1, dayExp:"2026-10-15", hourExp:22, away:0,
     splitExp:[["2026-10-15",22,60],["2026-10-15",23,60],["2026-10-16",0,60]],
     want:"10/15 120′／10/16 60′",
     why:"22:00 起三小时＝昨天 120 分、今天 60 分，而不是整段挂到某一天；结束弹层必须自己把两天各记多少说出来，" +
         "否则用户看到的还是一个孤零零的 180。对照 B15（同一事件、旧世界：180 分整段挂到第二天凌晨）"},
    {n:"A33 严格·22:00 起、40 分钟离开跨零点、凌晨 1:40 记满 3 小时（用户举的第二个例子）",
     e:[["adv",100*M],["blur"],["adv",140*M],["back"],["resume"],["adv",300*M]],
     c:{mode:"strict",focus:180,away:15,base:new Date(2026,9,15,22,0,0).getTime()},
     min:180, st:"done", nExp:1, dayExp:"2026-10-15", hourExp:22, away:40,
     splitExp:[["2026-10-15",22,60],["2026-10-15",23,40],["2026-10-16",0,40],["2026-10-16",1,40]],
     want:"10/15 100′／10/16 80′",
     why:"用户原话的口径：0 点前真正学了 100 分（22:00–23:40），休息的 40 分钟（23:40–00:20）压着零点穿过、" +
         "一秒都不许进任何一天，0 点后又学 80 分 ⇒ 昨天 100／今天 80、总和仍是 180。" +
         "游标推算：blur 那刻固化 6000 秒（22 点格 3599＋23 点格 2401），离开 2400 秒只挪游标到 00:20:01，" +
         "resume 后 4800 秒按整点切＝0 点格 2399、1 点格 2401 ⇒ 各取整 40.0"},
    {n:"A34 严格·正好压在 0 点结束（22:30 起 90 分）⇒ 今天 0 分，且不许留一片 0 分钟的垃圾",
     e:[["adv",91*M]], c:{mode:"strict",focus:90,base:new Date(2026,9,15,22,30,0).getTime()},
     min:90, st:"done", nExp:1, dayExp:"2026-10-15", hourExp:22,
     splitExp:[["2026-10-15",22,30],["2026-10-15",23,60]],
     why:"边界形状：游标从 22:30:01 起走 5400 秒，尾巴正好落在次日 00:00:01 ⇒ 次日那格只有 1 秒＝0.0167 分，" +
         "取整成 0.0 之后必须被丢掉（留着就是「今天学了 0 分钟」这种鬼话）。两片都在同一天 ⇒ 弹层不写跨零点那句提示。" +
         "这条同时是「零头不骗人」的对照：削尾与补尾都在这儿交汇"},
    {n:"A35 不计时·23:00 起连跑 4 小时后手动结束（用户不设时长那一档）", e:[["adv",240*M],["stop"]],
     c:{mode:"strict",focus:180,timing:"none",base:new Date(2026,9,15,23,0,0).getTime()},
     min:240, st:"abort", nExp:1, dayExp:"2026-10-15", hourExp:23,
     splitExp:[["2026-10-15",23,60],["2026-10-16",0,60],["2026-10-16",1,60],["2026-10-16",2,60]],
     why:"timing=none 时不封顶，跑多久记多久（A12 钉的旧账）；中断那一段也要分账：昨天 60／今天 180。" +
         "归属仍按起表那一刻（day 10-15、hour 23）——split 负责「分到哪几天」，day 负责「这一段属于哪天」，两件事不冲突"},
    {n:"A36 学霸·0 点前 90 分＋跨零点离开 5 分 ⇒ 当场中断也只记在场的 90 分",
     e:[["adv",90*M],["blur"],["adv",95*M],["back"]],
     c:{mode:"xueba",focus:180,base:new Date(2026,9,15,23,0,0).getTime()},
     min:90, st:"abort", nExp:1, dayExp:"2026-10-15", hourExp:23, want:"离开 5 分钟没计入",
     splitExp:[["2026-10-15",23,60],["2026-10-16",0,30]],
     why:"中断（abort）这条路也要分账：0 点前 60 分归昨天、0 点后 30 分归今天，离开那 5 分钟（00:30–00:35）不进任何一天。" +
         "学霸模式在这里仍然当场中断——那是这一档的既有承诺，与「跨零点不许打断」是两回事（不许打断说的是 0 点那一拍本身）。" +
         "这一行原来还挂着 away:5，跑出来是 0——查了机制才订正判据：abort() 收尾时把 awayTotal 清零，而" +
         "「离开」读数取的是段结束之后的状态 ⇒ 这个数在学霸那档恒 0，量不到东西（不是产品少记了）。" +
         "「那 5 分钟没计入」的证据由另外三条承担：只记 90 分、分桶表合计 90 分、toast 原文「离开 5 分钟没计入」" +
         "（awayEnd 在 abort 之前已把这笔进 T.awayTotal 并只挪游标，机制本身由 A33 那条 strict 的 away:40 钉着）" +
         "——判据换掉的同时把换的理由写在这儿，不留一条永远绿也可能永远错的断言"},
    {n:"A37 严格·23:00 起 60 分→按暂停跨过 0 点整 1 小时→恢复再 60 分→手动结束",
     e:[["adv",60*M],["pause"],["adv",120*M],["resume"],["adv",180*M],["stop"]],
     c:{mode:"strict",focus:180,away:15,base:new Date(2026,9,15,23,0,0).getTime()},
     min:120, st:"abort", nExp:1, dayExp:"2026-10-15", hourExp:23,
     splitExp:[["2026-10-15",23,60],["2026-10-16",1,60]],
     want:"跨了零点，两天各记：10/15 60′／10/16 60′",
     why:"暂停那 1 小时（00:00–01:00）正好压着零点穿过去，一秒都不许进任何一天：账本必须是 23 点格 60 分＋**1 点格** 60 分，" +
         "不是 23 点格＋0 点格。这一行是整套分桶账里唯一「两天的合计怎么挪都看不出、只有钟点能看出」的形状" +
         "（挪错游标会得到 昨60／今60 完全相同的合计）⇒ 它专门钉 resume() 那句\"游标跳到此刻\"：" +
         "游标不跳，恢复后的 60 分钟会被算成 0 点后紧接着的那一小时，用户看到的时段柱就整格左移一小时"},
  ],
};

/* 分桶表的比较用这套小工具：片里的分钟一律先取整到 0.1，天序按 dayKey 排——
   期望值写的是"人算出来的那张表"，不是"跑出来回填的那张表"。 */
function spNorm(sp){ return Array.isArray(sp) ? sp.map(x => [String(x[0]), Number(x[1]), Math.round(Number(x[2])*10)/10]) : null; }
function spDays(sp){ const m = new Map();
  for(const x of (sp||[])) m.set(x[0], Math.round(((m.get(x[0])||0) + Number(x[2]))*10)/10);
  return Array.from(m.entries()).sort((a,b)=>a[0]<b[0]?-1:1); }
function spTxt(a){ return a === null ? "无" : JSON.stringify(a) + " 各天 " + JSON.stringify(spDays(a)); }

/* 不变式：同一段设置、只把"10 分钟离开"整体平移，记录分钟数必须一模一样。
   before 世界预期违反（这就是 bug 本身）；after 世界必须只剩 180 一个数。 */
function invariance(parts, world){
  const outs = [];
  for(const at of [0, 10, 60, 120, 170]){
    const r = run(parts, [["adv",at*M],["blur"],["adv",(at+10)*M],["back"],["adv",200*M]], {mode:"normal", focus:180});
    outs.push(at + "′→" + r.min);
  }
  const set = Array.from(new Set(outs.map(x => x.split("→")[1])));
  const ok = world === "after" ? (set.length === 1 && set[0] === "180") : (set.length > 1);
  return { ok, line:"I1 不变式：3h 普通段，把 10 分钟离开整体平移 5 个位置 ⇒ " + outs.join("  ") +
    "（不同值 " + set.length + " 个；after 世界要求只剩 180，before 世界要求这里就是花的）" };
}

/* 分桶账自己的已知答案对照（U 系列）：真值表量的是"整段跑完记录里那张表对不对"，
   而 dlSplit 的削尾／补尾／取整零头这三件事，恰好可能出现"残差为 0 ⇒ 谁都挡不住"的漏网组合。
   这里把 dlWalk／dlBook／dlSplit／dlCleanSplit／dlText 逐个摆到台面上问，答案全部手算。
   它只在 after 世界跑：before 那三份文件里没有这套函数（拿它量旧文件＝一把必然报警的废尺，与 TK 同理）。 */
function splitUnitCheck(parts){
  const w = makeWorld(parts, {mode:"strict", focus:180});
  if(!w.dlBook || !w.dlSplit || !w.dlCleanSplit || !w.dlText || !w.dayReal || !w.dlCleanBK || !w.dlSync || !w.dlPeekSplit)
    return { ok:false, n:0, line:"FAIL U 沙箱里拿不到 dlBook／dlSync／dlSplit／dlPeekSplit／dlCleanSplit／dlText／dayReal／dlCleanBK ⇒ 这把尺看不见分桶账，不作数" };
  const T = w.T, D1 = "2026-10-15", D2 = "2026-10-16";
  const t0 = new RealDate(2026,9,15,22,0,0).getTime();   // 本地 22:00 整（不带 CLK 那 1 秒的偏移）
  const t1 = t0 + 7200000;                                                       // 次日 00:00 整
  const cases = [];
  const chk = (n, got, exp) => cases.push({ n, ok: JSON.stringify(got) === JSON.stringify(exp), got, exp });
  /* 每条对照先把整副账摆平：T.acc／T.awayTotal 是"这段会话到现在为止的总量"，T.dAcc／T.dAway 是
     分桶账已经结掉的那部分——dlBook 只吃两者的差，所以 fixture 少摆一样，下一条就顺着上一条流下去。
     这里真踩过：原先只摆 dAcc 不摆 T.acc，U1 留下的 7200 在场秒灌进了 U3，把"离开那 2 小时不进任何一天"
     量成"进桶 2 小时"⇒ 报警是真的、病因在量具不在产品（先查机制再动判据）。 */
  const set = (bk, posAt, dAcc, dAway) => { T.status="run"; T.hold=false; T.swAt=t0; T.posAt=posAt;
    T.bk=bk; T.acc=0; T.awayTotal=0; T.dAcc=dAcc; T.dAway=dAway; };
  // U1 在场 7200 秒从 22:00 起 ⇒ 正好两个整点格，各 3600 秒
  set([], t0, 0, 0); T.acc = 7200; w.dlBook();
  chk("U1 游标按整点切", T.bk, [[D1,22,3600],[D1,23,3600]]);
  chk("U2 dlSplit(120) 换算成分", w.dlSplit(120), [[D1,22,60],[D1,23,60]]);
  // U3 离开（非在场）两小时：游标照走，一秒都不进桶
  set([], t0, 0, 0); T.awayTotal = 7200000; w.dlBook();
  chk("U3 离开那 2 小时不进任何一天", T.bk, []);
  chk("U3b 游标确实被挪到次日 0 点", T.posAt === t1, true);
  // U4 跨过 0 点之后再在场 60 分 ⇒ 那片落在次日的 0 点格
  set([], t1, 0, 7200000); T.acc = 3600; w.dlBook();
  chk("U4 0 点后的在场量归次日", T.bk, [[D2,0,3600]]);
  // U5 削尾只能从最后一片削（recordSec 封顶多出来的那 10 分在尾巴上）
  set([[D1,22,3600],[D1,23,3600],[D2,0,3600]], t0, 10800, 0);
  chk("U5 多余的 10 分从最后一片削", w.dlSplit(170), [[D1,22,60],[D1,23,60],[D2,0,50]]);
  // U6 补尾只能补到最后一片（0.2 分钟地板那种"账比要记的少"）
  set([[D1,22,3600],[D1,23,3600],[D2,0,3000]], t0, 10200, 0);
  chk("U6 差的 10 分补到最后一片", w.dlSplit(180), [[D1,22,60],[D1,23,60],[D2,0,60]]);
  // U7 账本是空的（刚点上就结束）⇒ 造一片在起表那一刻，不许凭空造出次日
  set([], t0, 0, 0); T.swAt = t0 + 3600000 + 600000;   // 23:10
  chk("U7 空账本补一片归起表那天那小时", w.dlSplit(0.2), [["2026-10-15",23,0.2]]);
  // U8 A34 的形状：22:30:01 起 5400 秒，次日 0 点格里只剩 1 秒 ⇒ 取整成 0.0 后必须丢掉
  set([[D1,22,1799],[D1,23,3600],[D2,0,1]], t0, 5400, 0);
  chk("U8 次日那 1 秒被丢掉（不许留 0 分钟的片）", w.dlSplit(90), [[D1,22,30],[D1,23,60]]);
  // U9 取整的零头不许把一个天"挤"成两个天
  set([[D1,22,3599],[D2,0,1]], t0, 3600, 0);
  chk("U9 舍入零头不造新天", w.dlSplit(60), [[D1,22,60]]);
  // U10 形状闸：对得上才认，对不上／一片／钟点越界／day 非法都不认
  chk("U10a 两片且总和对得上→认", w.dlCleanSplit([[D1,22,60],[D2,0,60]], 120), [[D1,22,60],[D2,0,60]]);
  chk("U10b 总和对不上→不认", w.dlCleanSplit([[D1,22,60],[D2,0,60]], 300), null);
  chk("U10c 只有一片→不认（等于旧口径）", w.dlCleanSplit([[D1,22,30]], 30), null);
  chk("U10d 钟点 24→不认", w.dlCleanSplit([[D1,24,60],[D2,0,60]], 120), null);
  chk("U10e day 非法→不认", w.dlCleanSplit([["2026-13-45",22,60],[D2,0,60]], 120), null);
  chk("U10f 负数片→不认", w.dlCleanSplit([[D1,22,-60],[D2,0,180]], 120), null);
  /* U10g～U10j 日历日校验本身：这一条是被 U10e 逼出来的——原来三处都只验"四位-两位-两位"的形状，
     于是 "2026-13-45" 一路过关，统计面板上就凭空多出一天。加闸之后既要否掉假日子，
     也不能把真日子误杀（闰年 2/29 那行就是防误杀的对照）。 */
  chk("U10g 2 月 30 日→dayReal 否", w.dayReal("2026-02-30"), false);
  chk("U10h 闰年 2 月 29 日→dayReal 认（不许误杀真日子）", w.dayReal("2024-02-29"), true);
  chk("U10i 2 月 30 日混进分桶表→整张不认", w.dlCleanSplit([["2026-02-30",22,60],[D2,0,60]], 120), null);
  chk("U10j 落盘账本丢掉假日子那片", w.dlCleanBK([["2026-13-45",22,600],[D1,22,600]]), [[D1,22,600]]);
  chk("U10k 非字符串／少一位→dayReal 否", [w.dayReal(20261015), w.dayReal("2026-1-15")], [false, false]);
  // U11 弹层那句话：同一天不写，跨两天才写，且写的是"各天合计"不是"每小时"
  chk("U11a 同一天→空话", w.dlText([[D1,22,60],[D1,23,60]]), "");
  chk("U11b 跨两天→按天合计", w.dlText([[D1,22,60],[D1,23,60],[D2,0,60]]), "10/15 120′／10/16 60′");
  /* U12 存储上界：一小时一片，第 24 片之后并进第 24 片（落盘要跟着 JSON 走，不能无限长）。
     手算：账本 26 片（10-15 的 22/23 两格＋10-16 的 0..23 共 24 格）＝1560 分。
     前 23 片照抄（末片是 10-16 的 20 点格 60 分），第 24 片吃掉 21/22/23 三格＝180 分，总和仍 1560。 */
  const long = []; for(let i=0;i<26;i++){ const dd = new RealDate(2026,9,15,22,0,0); dd.setHours(dd.getHours()+i);
    long.push([dayKeyOf(dd), dd.getHours(), 3600]); }
  set(long, t0, 26*3600, 0);
  const cap = w.dlSplit(1560);
  chk("U12 26 片账本切出 24 片界", [cap.length, JSON.stringify(cap[22]), JSON.stringify(cap[23]),
                                  cap.reduce((s,x)=>s+x[2],0)], [24, JSON.stringify([D2,20,60]), JSON.stringify([D2,23,180]), 1560]);
  /* U13 零头把最后一片压到 0 ⇒ 必须丢掉，否则 dlCleanSplit 看见 0 片就整张判废、跨零点的账又退回一天。
     手算：账本 3597＋3 秒（22:00:03 起表跑满 60 分就是这形状）→ 60.0 与 0.1 两片＝60.1，比要的 60 多 0.1
     → 零头并进最后一片：0.1−0.1＝0.0 → 过滤后只剩 22 点那一片 60 分。 */
  set([[D1,22,3597],[D1,23,3]], t0+3000, 3600, 0);
  chk("U13 零头压成 0 的最后一片被丢掉", w.dlSplit(60), [[D1,22,60]]);
  /* U14 削尾方向的第二把尺：U5 那档多余的量（10 分）没超出最后一片，"削尾"与"零头并进最后一片"两道兜底
     给出**同一个答案**——M54 第一次就是把整条削尾循环摘掉而真值表照样全绿，才暴露这层冗余。
     这里把超出量抬到最后一片装不下（180 分的账只记 65 分）：只能一片一片从尾巴往前削。
     说明白：这一档比真实零头大得多（真实封顶超出不超过一拍＋铃的延迟），它量的是"削尾方向"这条契约本身，不是复刻某个场景。 */
  set([[D1,22,3600],[D1,23,3600],[D2,0,3600]], t0, 10800, 0);
  chk("U14 超出最后一片的量逐片从尾往前削", w.dlSplit(65), [[D1,22,60],[D1,23,5]]);
  /* U15／U16 预告与真入账同源（形状取自用户 2026-10-23 现场那段：22:47:45 起表，00:30 仍在跑）。
     为什么值得单立：只证明"预告数字对"不证明它没动账本；只证明"账本没动"不证明预告与真入账
     是同一张表。三件事分开钉——a/b 读只读性，c/d 钉 dlSync 与 usedSec 同源，f 钉逐字节相等。 */
  const tA = new RealDate(2026,9,15,22,47,45).getTime();
  const inflight = 6135;                                  // 22:47:45→00:30:00＝1 小时 42 分 15 秒
  T.status="run"; T.hold=false; T.kind="focus"; T.total=10800; T.swAt=tA; T.bk=[]; T.posAt=tA;
  T.dAcc=0; T.dAway=0; T.acc=0; T.awayTotal=0; T.awayAt=0; T.startAt = CLK - inflight*1000;
  const snap = () => JSON.stringify([T.bk, T.posAt, T.dAcc, T.dAway, T.acc, T.startAt, T.awayTotal]);
  const s0 = snap();
  const pv = w.dlPeekSplit();
  chk("U15a 预告不碰账本／游标／秒表", snap(), s0);
  chk("U15b 预告把在跑的那截算进两天", [!!pv, pv && pv.cross, pv && pv.minutes,
      pv && pv.byDay.get(D1), pv && pv.byDay.get(D2)], [true, true, 102.3, 72.3, 30]);
  chk("U16 预告逐片＝22:47:45 起跑 102.3 分（首片吃 22 点格剩下的 12.3 分）",
      pv && pv.split, [[D1,22,12.3],[D1,23,60],[D2,0,30]]);
  const usedBefore = w.usedSec();
  w.dlSync();
  chk("U15c dlSync 不改 usedSec", w.usedSec(), usedBefore);
  chk("U15d dlSync 后游标＝此刻、bk 合计＝dAcc＝在场秒",
      [T.posAt === tA + inflight*1000, Math.round(T.dAcc), Math.round(T.bk.reduce((s,x)=>s+x[2],0))],
      [true, inflight, inflight]);
  chk("U15e 固化之后再预览，仍是同一张表", w.dlPeekSplit() && w.dlPeekSplit().split, pv && pv.split);
  chk("U15f 预告与最终入账逐字节相同", w.dlSplit(102.3), pv && pv.split);
  /* 暂停态也要能预告（用户按了暂停、跨过零点仍想知道怎么分）；idle／休息段没有这笔账。 */
  T.status="pause";
  chk("U16b 暂停态仍能预告同一张表", w.dlPeekSplit() && w.dlPeekSplit().split, pv && pv.split);
  T.status="idle";
  chk("U16c idle 不给预告", w.dlPeekSplit(), null);
  T.status="run"; T.kind="short";
  chk("U16d 休息段不给预告", w.dlPeekSplit(), null);
  T.kind="focus";
  return unitReport("U 分桶账已知答案", cases);
}
/* 消费端对照（C 系列）：证明统计面板真的按分桶表分账，而不是"写进记录了但没人读"。
   量具切片是现盘的 buildStats／cleanSession 原文，改一个字这里就变。 */
function splitConsumeCheck(parts){
  const w = makeWorld(parts, {mode:"strict", focus:180});
  if(!w.buildStats || !w.cleanSession || !w.dlCleanSplit)
    return { ok:false, n:0, line:"FAIL C 沙箱里拿不到 buildStats／cleanSession ⇒ 消费端这把尺不作数" };
  const D1 = "2026-10-15", D2 = "2026-10-16";
  const cases = [];
  const chk = (n, got, exp) => cases.push({ n, ok: JSON.stringify(got) === JSON.stringify(exp), got, exp });
  const S = w.S;
  const rec = (day, hour, minutes, split) => { const r = { id:"x"+day+hour, ts:1, day, hour, type:"focus", minutes, status:"done", reason:null }; if(split) r.split = split; return r; };
  const g = () => { const st = w.buildStats(); return { d1: st.dayMin.get(D1)||0, d2: st.dayMin.get(D2)||0,
      h22: st.hourMin.get(22)||0, h0: st.hourMin.get(0)||0, pomos: st.pomos, min: st.min,
      p1: st.dayPomo.get(D1)||0, p2: st.dayPomo.get(D2)||0 }; };
  // C1 一条跨零点的 180 分 ⇒ 昨天 120、今天 60；时段柱按片走（原来整段灌进 22 点那一格）
  S.sessions = [rec(D1, 22, 180, [[D1,22,60],[D1,23,60],[D2,0,60]])];
  chk("C1 统计按分桶表分天", [g().d1, g().d2, g().h22, g().h0], [120, 60, 60, 60]);
  // C2 番茄个数仍只算在起表那天（否则一个 3 小时的窗＝两个番茄）
  chk("C2 个数仍归起表那天", [g().p1, g().p2, g().pomos], [1, 0, 1]);
  // C3 老记录（没有 split）照旧整段归一天——向后兼容，不许变成 0
  S.sessions = [rec(D1, 9, 25, null)];
  chk("C3 无 split 的老记录不受影响", [g().d1, g().d2, g().h22], [25, 0, 0]);
  // C4 伪造的 split（总和对不上）必须退回旧口径，不许按假表分账
  S.sessions = [rec(D1, 22, 180, [[D1,22,1],[D2,0,1]])];
  chk("C4 对不上的 split 被拒→整段归一天", [g().d1, g().d2], [180, 0]);
  // C5 两条混合（一条分账一条不分）⇒ 各归各的，不许互相覆盖
  S.sessions = [rec(D1, 22, 180, [[D1,22,60],[D1,23,60],[D2,0,60]]), rec(D1, 9, 25, null)];
  chk("C5 混合记录互不覆盖", [g().d1, g().d2, g().h0], [145, 60, 60]);
  // C6 导入端：合法 split 要活下来，非法的要被摘掉（否则"导入一次就把伪造值供进统计"）
  const okImp = w.cleanSession({ id:"i1", ts:1, day:D1, hour:22, type:"focus", minutes:180, status:"done",
                                 split:[[D1,22,60],[D1,23,60],[D2,0,60]] });
  chk("C6a 导入保留合法 split", okImp.split, [[D1,22,60],[D1,23,60],[D2,0,60]]);
  const badImp = w.cleanSession({ id:"i2", ts:1, day:D1, hour:22, type:"focus", minutes:180, status:"done",
                                 split:[[D1,22,600],[D2,0,600]] });
  chk("C6b 导入丢掉对不上的 split", badImp.split, undefined);
  const negImp = w.cleanSession({ id:"i3", ts:1, day:D1, hour:22, type:"focus", minutes:180, status:"done",
                                  split:[[D1,22,-60],[D2,0,240]] });
  chk("C6c 导入丢掉带负数的 split", negImp.split, undefined);
  /* C7 假日子（形状对但日历上没有这天）从导入端进来时，day 要退回"按 ts 现推"，
     不能原样供进去——否则统计面板上凭空多出一行 2026-13-45。这条与 U10e/U10j 是同一个洞的三个入口。 */
  const fakeDay = w.cleanSession({ id:"i4", ts:new RealDate(2026,9,15,10,0,0).getTime(), day:"2026-13-45",
                                   hour:10, type:"focus", minutes:30, status:"done" });
  chk("C7 导入的假日子退回 ts 推出的真日子", fakeDay.day, "2026-10-15");
  return unitReport("C 分桶账消费端", cases);
}
function unitReport(tag, cases){
  const bad = cases.filter(c => !c.ok);
  const line = (bad.length ? "FAIL " : "ok   ") + tag + "：" + (cases.length - bad.length) + "/" + cases.length + " 条符合已知答案" +
    (bad.length ? " ｜不符：" + bad.map(c => c.n + " 得 " + JSON.stringify(c.got) + " 期望 " + JSON.stringify(c.exp)).join("；") : "");
  return { ok: bad.length === 0, n: cases.length, line };
}

/* 平移不变式（S 系列）：22:00 起 3 小时，把"10 分钟离开"整体平移 6 个位置——
   在场总量必须恒 180 分，昨天那一份只能随位置单调不减（离开越晚，昨天吃得越多）。
   期望表是跑前手算的（游标从 22:00:01 起按整点走；离开那段只挪游标）：
   0′／30′／90′⇒昨 110 今 70；115′⇒昨 115 今 65（那段离开正好压着 0 点穿过去）；125′／170′⇒昨 120 今 60。
   与 I1 的分工：I1 钉"记录分钟数不随离开时机变"，这一条钉"分到哪一天"也不随它随机变。 */
function splitShiftCheck(parts){
  const EXP = [[0,110],[30,110],[90,110],[115,115],[125,120],[170,120]];
  const outs = [], bad = [];
  for(const [at, d1] of EXP){
    const r = run(parts, [["adv",at*M],["blur"],["adv",(at+10)*M],["back"],["resume"],["adv",(at+220)*M]],
                  {mode:"strict", focus:180, away:15, base:new Date(2026,9,15,22,0,0).getTime()});
    const days = spDays(r.split);
    const got1 = days.length ? days[0][1] : null, got2 = days.length > 1 ? days[1][1] : 0;
    outs.push(at + "′→昨" + got1 + "／今" + got2);
    if(!r.split || r.min !== 180 || got1 !== d1)
      bad.push(at + "′（得 昨" + got1 + " 今" + got2 + " 记" + r.min + "，期望 昨" + d1 + " 记 180）");
  }
  const ok = !bad.length;
  return { ok, n: EXP.length, line:(ok ? "ok   " : "FAIL ") + "S 平移不变式：3h 段把 10 分钟离开平移 6 个位置 ⇒ " + outs.join("  ") +
    (ok ? "（总和恒 180，昨天份额随位置单调不减）" : " ｜不符：" + bad.join("；")) };
}

/* 静态尺 DF：日切换那一拍（60s 一次的 setInterval）里不许有中断动作。
   为什么这一条只能静态量：那个 interval 排在"刷新"段之后，不在 KERNEL／CTRL／AWAY／WIRE 任何切片里，
   eval 不到 ⇒ 行为级真值表看不见它。跨午夜的**行为**由另两行钉：A16（23:50 起表 3 小时，跑过去不打断）
   与 A24（夜里睡着 160 分钟照样记满 180），这两行是真的把墙钟推过了 0 点。
   判据先声明再跑：切片找不到 setInterval ⇒ 当场判红（"尺子没量到东西"不许静默跳过），
   找到之后逐个数中断动词，命中就点名是哪一个。证伪器 M30 往这一拍里插一句 pause() 要求它翻红。 */
const DAYFLIP_INTERRUPTS = ["abort(", "pause(", "complete()", "stopAll(", "tryEnd(", "showEnd(", "start("];
/* 日切换那一拍除了"不许中断"，还不许动计时状态——用户报的另一个形状是"零点一过进度清零"。
   赋值用正则认（(?!\\=) 是为了放过 `T.status === "run"` 这种比较）；列出的都是计时/账本状态，
   改它们等于零点重开一段。dlSync()／dlBook() 内部会改，但它们不在这段函数体里，不会被误伤。 */
const DAYFLIP_ZEROING = /\bT\.(?:acc|status|total|startAt|swAt|hold|kind|bk|posAt|dAcc|dAway|awayTotal|awayAt|beat)\s*=(?!=)/;
/* 从 b0 处的 "{" 起找配对的 "}"，跳过字符串与注释。找不到返回 -1（调用方一律判红，不许静默当成空函数）。 */
function braceEnd(s, b0){
  let depth = 0, q = null, esc = false;
  for(let i = b0; i < s.length; i++){
    const ch = s[i];
    if(q){ if(esc) esc = false; else if(ch === "\\") esc = true; else if(ch === q) q = null; continue; }
    if(ch === "/" && s[i+1] === "/"){ const nl = s.indexOf("\n", i); i = nl < 0 ? s.length : nl; continue; }
    if(ch === "/" && s[i+1] === "*"){ const e = s.indexOf("*/", i+2); i = e < 0 ? s.length : e + 1; continue; }
    if(ch === '"' || ch === "'" || ch === "`"){ q = ch; continue; }
    if(ch === "{") depth++;
    else if(ch === "}"){ depth--; if(depth === 0) return i; }
  }
  return -1;
}
function dayFlipCheck(SRC){
  const i = SRC.indexOf("let _lastDay = dayKey(new Date());");
  if(i < 0) return { ok:false, line:"FAIL DF 日切换那一拍的锚点没了（let _lastDay = dayKey(new Date());）⇒ 这把尺看不见它，不作数" };
  const seg = SRC.slice(i, i + 600);
  /* 已知答案自检抓到过一次真瞎：setInterval 不在时 indexOf 给 -1，而 indexOf("\n", -1) 把 -1 当 0 用
     ⇒ 切片缩成锚点那一行、动词 0 处、尺子反过来报绿。所以这里先单独点名"没找到 setInterval"，
       不许让 -1 顺流而下。 */
  const s = seg.indexOf("setInterval");
  if(s < 0) return { ok:false, line:"FAIL DF 那一拍的 600 字节内找不到 setInterval ⇒ 尺子没量到东西，不作数" };
  const nl = seg.indexOf("\n", s);
  if(nl < 0) return { ok:false, line:"FAIL DF setInterval 后面没有换行 ⇒ 切片形状不认识，不作数" };
  let body = seg.slice(0, nl + 1);
  /* 这一拍的工作可能被抽成具名函数（tick 与 60s 兜底共用同一拍）。抽出去不等于可以绕过检查：
     只要 setInterval 的第一个实参是标识符，就把那个函数的函数体也并进来量；找不到函数体当场判红。
     这是把尺子加长（原来只量内联箭头函数），不是放宽。 */
  let followed = "";
  const call = /setInterval\(\s*([A-Za-z_$][\w$]*)\s*,/.exec(seg.slice(s, nl + 1));
  if(call){
    const name = call[1];
    const fi = SRC.indexOf("function " + name + "(");
    if(fi < 0) return { ok:false, line:"FAIL DF 日切换那一拍调用 "+name+"() 却找不到函数体 ⇒ 尺子没法量，不作数" };
    const b0 = SRC.indexOf("{", fi);
    const fj = b0 < 0 ? -1 : braceEnd(SRC, b0);
    if(fj < 0) return { ok:false, line:"FAIL DF "+name+" 的函数体大括号不闭合 ⇒ 尺子没法量，不作数" };
    body += "\n" + SRC.slice(fi, fj + 1);
    followed = name;
  }
  const hits = DAYFLIP_INTERRUPTS.filter(v => body.indexOf(v) >= 0);
  if(hits.length) return { ok:false, line:"FAIL DF 日切换那一拍里出现中断动作 " + hits.join("／") + " ⇒ 跨过 0 点会自己打断（用户明确不要这个）｜原文：" + body.trim() };
  const zm = DAYFLIP_ZEROING.exec(body);
  if(zm) return { ok:false, line:"FAIL DF 日切换那一拍里出现改动计时状态的赋值「" + zm[0] + "」⇒ 零点会把进度清零／重置（用户明确不要这个）｜原文：" + body.trim() };
  return { ok:true, line:"ok   DF 日切换那一拍只做固化／刷新（切片量到 " + body.trim().length + " 字节" +
    (followed ? "，已跟进 "+followed+"() 的函数体" : "") + "，中断动词 0 处、计时状态赋值 0 处）；跨午夜行为由 A16／A24 两行钉" };
}

/* 静态尺 TK：tick 那一拍里"先问休眠、再判完成"的顺序。
   为什么也要静态量：tickOn 与 rafOn 一起排在"刷新"段，同样不在任何切片里 ⇒ 沙箱跑的 step() 是量具自己
   按这个顺序写的循环，产品里顺序写反了真值表看不见。这把尺就是补这一格，不是补判据本身。 */
function tickOrderCheck(SRC){
  const i = SRC.indexOf("function tickOn(){");
  if(i < 0) return { ok:false, line:"FAIL TK tickOn 找不到 ⇒ 这把尺看不见它，不作数" };
  const j = SRC.indexOf("\n}", i);
  if(j < 0) return { ok:false, line:"FAIL TK tickOn 的收尾找不到 ⇒ 切片形状不认识，不作数" };
  const body = SRC.slice(i, j + 2);
  const g = body.indexOf("suspendGuard();"), c = body.indexOf("checkDone();");
  if(g < 0 || c < 0) return { ok:false, line:"FAIL TK tick 那一拍里 " + (g<0?"没有 suspendGuard()":"") + (c<0?(g<0?"、也没有":"没有"):"") + "checkDone() ⇒ 尺子没量到，不作数" };
  if(g > c) return { ok:false, line:"FAIL TK 顺序反了：checkDone() 排在 suspendGuard() 之前 ⇒ 醒来那一拍先按墙上钟收尾，闸门永远追不上" };
  return { ok:true, line:"ok   TK tick 里先问休眠、再判完成（切片 " + body.trim().length + " 字节，两处都在且顺序对）" };
}

/* 静态尺 RT：进行时段快照必须"先固化、再序列化"。
   为什么只能静态量：saveRT 排在计时内核切片终点（"/* 进行中的那一段单独落盘"）之后，不在六段里；
   而它正是 2026-10-23 现场那份快照的来路——acc 已到 8517 秒、bk/pos 落后 188 秒，读档端只能靠
   "游标＋增量"把它猜回来，快照本身看不出零点前后各多少。判据钉的是那一句承重代码原样在、且在
   setItem 之前；形状不认识就判红（fail-closed），不当成"没毛病"。 */
function snapshotCheck(SRC){
  const i = SRC.indexOf("function saveRT(){");
  if(i < 0) return { ok:false, line:"FAIL RT saveRT 找不到 ⇒ 这把尺看不见它，不作数" };
  const b0 = SRC.indexOf("{", i);
  const j = b0 < 0 ? -1 : braceEnd(SRC, b0);
  if(j < 0) return { ok:false, line:"FAIL RT saveRT 的函数体大括号不闭合 ⇒ 尺子没法量，不作数" };
  const body = SRC.slice(i, j + 1);
  const call = 'if(T.status==="run") dlSync();';
  const s = body.indexOf(call);
  const w = body.indexOf("localStorage.setItem(RT_KEY");
  if(s < 0) return { ok:false, line:"FAIL RT saveRT 里没有「" + call + "」⇒ acc 与 bk／pos 会不同源（实测能落后 8 分钟），零点前后各多少在快照里看不出来" };
  if(w < 0) return { ok:false, line:"FAIL RT saveRT 里找不到 localStorage.setItem(RT_KEY ⇒ 切片形状不认识，不作数" };
  if(s > w) return { ok:false, line:"FAIL RT dlSync() 排在 setItem 之后 ⇒ 写下去的仍是落后一拍的分桶账" };
  return { ok:true, line:"ok   RT saveRT 先 dlSync() 再序列化（acc／bk／pos 同源，切片 " + body.trim().length + " 字节）" };
}

/* 两把静态尺自己的已知答案自检（不碰产品文件，纯字符串）：
   判据"跑绿"之前先证明它会翻红——缺这一节，DF／TK 就只是两条永不报警的 print。 */
function rulerSelfTest(){
  const CLEAN = "let _lastDay = dayKey(new Date());\nsetInterval(()=>{ const k=dayKey(new Date()); if(k!==_lastDay){ _lastDay=k; statsDirty(); refreshStats(); } },60000);\n";
  /* 具名函数那一支：产品把这一拍抽成了 onDayRoll()（tick 与 60s 兜底共用同一个函数声明）。
     尺子必须跟进函数体，否则"抽出去"就成了绕过检查的暗门——所以这三条对照是尺子的牙，不是装饰。 */
  const CLEAN_NAMED = "let _lastDay = dayKey(new Date());\nsetInterval(onDayRoll, 60000);\nfunction onDayRoll(){\n" +
    "  const k = dayKey(new Date());\n  if(k === _lastDay) return;\n  _lastDay = k;\n  statsDirty();\n  refreshStats();\n}\n";
  const TICK_OK = "function tickOn(){\n  if(_tick) return;\n  suspendGuard();\n  paint();\n  checkDone();\n}\n";
  const SNAP_OK = "function saveRT(){\n  if(!storageOK || dualReadOnly) return;\n  try{\n    if(T.status===\"idle\"){ localStorage.removeItem(RT_KEY); return; }\n    if(T.status===\"run\") dlSync();\n    localStorage.setItem(RT_KEY, \"x\");\n  }catch(e){}\n}\n";
  const cases = [
    ["DF 干净原文 → 该绿", dayFlipCheck(CLEAN).ok, true],
    ["DF 插入 pause() → 该红", dayFlipCheck(CLEAN.replace("refreshStats();", "refreshStats(); pause();")).ok, false],
    ["DF 插入 abort() → 该红", dayFlipCheck(CLEAN.replace("},60000);", " abort(\"x\"); },60000);")).ok, false],
    ["DF 锚点被删 → 该红（不许静默跳过）", dayFlipCheck("var nothing = 1;\n").ok, false],
    ["DF 锚点在但 setInterval 被删 → 该红", dayFlipCheck("let _lastDay = dayKey(new Date());\nfoo();\n").ok, false],
    ["DF 具名函数干净 → 该绿", dayFlipCheck(CLEAN_NAMED).ok, true],
    ["DF 具名函数体里插入 pause() → 该红", dayFlipCheck(CLEAN_NAMED.replace("statsDirty();", "statsDirty(); pause();")).ok, false],
    ["DF 调用具名函数但函数体被删 → 该红", dayFlipCheck("let _lastDay = dayKey(new Date());\nsetInterval(onDayRoll, 60000);\n").ok, false],
    ["DF 具名函数体里把进度清零 → 该红", dayFlipCheck(CLEAN_NAMED.replace("_lastDay = k;", "_lastDay = k;\n  T.acc = 0;")).ok, false],
    ["DF 具名函数体里的 === 比较 → 不许误杀（该绿）", dayFlipCheck(CLEAN_NAMED.replace("statsDirty();", "if(T.status === \"run\") statsDirty();")).ok, true],
    ["TK 顺序对 → 该绿", tickOrderCheck(TICK_OK).ok, true],
    ["TK 顺序反 → 该红", tickOrderCheck("function tickOn(){\n  checkDone();\n  suspendGuard();\n}\n").ok, false],
    ["TK 少了休眠闸 → 该红", tickOrderCheck("function tickOn(){\n  checkDone();\n}\n").ok, false],
    ["TK 少了完成判定 → 该红", tickOrderCheck("function tickOn(){\n  suspendGuard();\n}\n").ok, false],
    ["TK 整个函数没了 → 该红", tickOrderCheck("var x = 1;\n").ok, false],
    ["RT 先固化再序列化 → 该绿", snapshotCheck(SNAP_OK).ok, true],
    ["RT 少了 dlSync → 该红", snapshotCheck(SNAP_OK.replace("    if(T.status===\"run\") dlSync();\n", "")).ok, false],
    ["RT 固化排在 setItem 之后 → 该红",
      snapshotCheck("function saveRT(){\n  localStorage.setItem(RT_KEY, \"x\");\n  if(T.status===\"run\") dlSync();\n}\n").ok, false],
    ["RT 整个函数没了 → 该红", snapshotCheck("var x = 1;\n").ok, false],
  ];
  const bad = cases.filter(c => c[1] !== c[2]);
  return { ok: bad.length === 0, bad: bad.length, n: cases.length,
    lines: cases.map(c => (c[1] === c[2] ? "ok   " : "FAIL ") + c[0] + "（量具实际给的是 " + (c[1] ? "绿" : "红") + "）") };
}

/* 跑一整个世界：返回 {rc, lines}；rc=3 形状闸门挡下，rc=1 有红行，rc=0 全绿 */
function runWorld(SRC, world){
  const lines = [];
  try{ gate(SRC, world); }
  catch(e){ return { rc:3, lines:["RC=3 形状闸门：" + e.message] }; }
  const parts = extract(SRC);
  let bad = 0, rows = 0;
  for(const r of ROWS[world]){
    rows++;
    let got;
    try{ got = run(parts, r.e, r.c); }
    catch(err){ lines.push("FAIL " + r.n + " 跑炸：" + err.message); bad++; continue; }
    const problems = [];
    if(r.nExp !== undefined && got.n !== r.nExp) problems.push("记录条数 " + got.n + " ≠ 期望 " + r.nExp);
    if(r.min !== null && r.min !== undefined && got.min !== r.min) problems.push("记 " + got.min + " ≠ 期望 " + r.min);
    if(r.st && got.status !== r.st && got.statusNow !== r.st) problems.push("状态 " + got.status + "/" + got.statusNow + " ≠ 期望 " + r.st);
    if(r.away !== undefined && Math.abs(got.awayMin - r.away) > 0.001) problems.push("离开累计 " + got.awayMin.toFixed(2) + " ≠ 期望 " + r.away);
    if(r.used !== undefined && Math.abs(got.usedMin - r.used) > 0.01) problems.push("在场 " + got.usedMin.toFixed(2) + " ≠ 期望 " + r.used);
    if(r.want && (got.toasts.join(" | ") + " | " + got.endSub).indexOf(r.want) < 0)
      problems.push("披露里找不到「" + r.want + "」；toast=" + JSON.stringify(got.toasts) + " 弹层=" + JSON.stringify(got.endSub));
    if(r.readExp && JSON.stringify(got.reads) !== JSON.stringify(r.readExp))
      problems.push("读数 " + JSON.stringify(got.reads) + " ≠ 期望 " + JSON.stringify(r.readExp));
    if(r.dayExp !== undefined && got.day !== r.dayExp) problems.push("归属日 " + got.day + " ≠ 期望 " + r.dayExp);
    if(r.hourExp !== undefined && got.hour !== r.hourExp) problems.push("归属时段 " + got.hour + " 点 ≠ 期望 " + r.hourExp);
    /* 分桶表逐片比对：期望值是跑前手算的那张表（片序按 day 排、分钟取整到 0.1），
       不是跑完回填的。splitExp:null 钉的是"记录里不该有 split"——单片等于旧口径，不该落盘。 */
    if(r.splitExp !== undefined){
      const exp = r.splitExp === null ? null : spNorm(r.splitExp);
      const act = got.split === null || !got.split.length ? null : spNorm(got.split);
      if(JSON.stringify(act) !== JSON.stringify(exp))
        problems.push("分桶表 " + spTxt(act) + " ≠ 期望 " + spTxt(exp));
    }
    if(!problems.length && r.min === null && r.st === undefined && r.away === undefined && !r.want && !r.readExp &&
       r.dayExp === undefined && r.hourExp === undefined && r.nExp === undefined && r.splitExp === undefined)
      problems.push("这一行没有断言");
    if(problems.length) bad++;
    lines.push((problems.length ? "FAIL " : "ok   ") + r.n + " ⇒ 记 " + got.min + " 分(" + got.status +
      (got.reason ? "/" + got.reason : "") + ") 态 " + got.statusNow + " 离开 " + got.awayMin.toFixed(2) +
      " 分 在场 " + got.usedMin.toFixed(1) + " 分 记录 " + got.n + " 条 归属 " + got.day + "/" + got.hour + " 点" +
      (r.splitExp !== undefined ? " 分账 " + spTxt(got.split && got.split.length ? got.split : null) : "") +
      " 读数 " + JSON.stringify(got.reads.map(x => +x.toFixed(4))) +
      (problems.length ? " ｜" + problems.join("；") + " ｜推算：" + r.why : ""));
  }
  const inv = invariance(parts, world);
  if(!inv.ok) bad++;
  lines.push((inv.ok ? "ok   " : "FAIL ") + inv.line);
  /* U／C／S 三把分桶账尺只在 after 世界跑：before 那三份文件里根本没有 dlBook／dlSplit／split 消费端，
     拿它们量旧文件＝三把必然报警的废尺（与 TK 同一处理）。这里逐条点名"不适用＋为什么"，不静默跳过。 */
  const na = why => ({ ok:true, n:0, line:"n/a  " + why });
  const checks = world === "after"
    ? [splitUnitCheck(parts), splitConsumeCheck(parts), splitShiftCheck(parts)]
    : [na("U 分桶账已知答案不在 before 世界跑（那份文件没有 dlWalk／dlSplit／dlCleanSplit）"),
       na("C 消费端对照不在 before 世界跑（那份文件的 buildStats／cleanSession 不认 split，没有可量的东西）"),
       na("S 平移不变式不在 before 世界跑（旧世界根本没有分天账，昨天的份额恒 0，量它没有意义）")];
  for(const c of checks){ if(!c.ok) bad++; lines.push(c.line); }
  const df = dayFlipCheck(SRC);
  if(!df.ok) bad++;
  lines.push(df.line);
  /* TK 只服务于 after 世界：before 那三份文件本来就没有这道闸，拿它去量旧文件＝一把必然报警的废尺。
     这里点名"不适用"而不是悄悄不跑——跑没跑、为什么没跑，要在回执上看得见。 */
  const tk = world === "after" ? tickOrderCheck(SRC)
    : { ok:true, line:"n/a  TK tick 顺序尺不在 before 世界跑（那份文件没有这道闸；判据与理由都写在这儿，不是静默跳过）" };
  if(!tk.ok) bad++;
  lines.push(tk.line);
  const rt = world === "after" ? snapshotCheck(SRC)
    : { ok:true, line:"n/a  RT 快照同源尺不在 before 世界跑（旧 saveRT 只写 acc、没有 dlSync 这一句，拿它量旧文件＝一把必然报警的废尺）" };
  if(!rt.ok) bad++;
  lines.push(rt.line);
  return { rc: bad ? 1 : 0, bad, rows: rows + 4, lines, gateOnly: false };
}

if(require.main === module){
  const FILE = process.argv[2] || "C:/Users/lyj20/Desktop/赛博鸡蛋/fanqie-todo/index.html";
  const WORLD = process.argv[3] || "after";
  const SRC = fs.readFileSync(FILE, "utf8");
  /* 两把静态尺先自证"会翻红"，再谈它们量到了什么：已知答案自检摆在前头，红了就整趟不作数。 */
  const st = rulerSelfTest();
  const out = runWorld(SRC, WORLD);
  const pre = "\n量具自检 " + st.bad + "/" + st.n + " 条不符（DF／TK／RT 的已知答案）" +
              (st.ok ? " ⇒ 三把尺都会翻红" : " ⇒ 尺子自己就是瞎的，下面它报的绿也不作数") +
              "\n" + st.lines.join("\n");
  console.log("文件 " + FILE + "\n世界 " + WORLD + pre +
    (out.rc === 3 ? "\n" + out.lines[0] : "\n" + out.lines.join("\n") + "\nRC=" + out.rc + " 真值表 " + out.rows + " 行，红 " + out.bad + " 行"));
  process.exit(st.ok ? out.rc : 1);
}
module.exports = { runWorld, extract, gate, ROWS, COMMON_ANCHORS, WORLD_ANCHORS, WORLD_FORBIDDEN,
                   dayFlipCheck, DAYFLIP_INTERRUPTS, DAYFLIP_ZEROING, tickOrderCheck, rulerSelfTest,
                   snapshotCheck, splitUnitCheck, splitConsumeCheck, splitShiftCheck, spNorm, spDays, spTxt, run, invariance };
