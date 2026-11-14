/* Masterplan 第五部分 P1：WebAudio 休眠/换设备后的恢复与告警兜底。
   用法：node 验收/test_audio_guard.js [index.html] [--selftest]
   · 被测函数从 index.html 现盘字节按锚点切出，不手抄实现；锚点缺失＝该组判红。
   · 只做离线判定：假 AudioContext / 假 Notification，不建解码器、不出声、不开窗。
   · --selftest 把要防的回归逐个注回内存源码；改不出字节记 NOP，不为了变绿放宽判据。 */
"use strict";
const fs = require("fs");
const path = require("path");

const FILE = process.argv[2] && !process.argv[2].startsWith("--")
  ? process.argv[2] : path.join(__dirname, "..", "index.html");
const SELFTEST = process.argv.includes("--selftest");
const SRC = fs.readFileSync(FILE, "utf8");
const BASE_SRC = SRC;

function functionText(src, anchor) {
  const i = src.indexOf(anchor);
  if (i < 0) throw new Error("锚点缺失：" + anchor);
  const j = src.indexOf("\n}", i);
  if (j < 0) throw new Error("函数体终点缺失：" + anchor);
  return src.slice(i, j + 2);
}
const flush = () => new Promise((r) => setImmediate(r));

function makeCtx(state, resumeMode) {
  const ctx = { state: state || "running", currentTime: 0, resumeCalls: 0, oscStarts: 0,
    resumeMode: resumeMode || "ok", destination: {} };
  ctx.resume = function () {
    ctx.resumeCalls++;
    if (ctx.resumeMode === "reject") return Promise.reject(new Error("blocked"));
    if (ctx.resumeMode === "ok") ctx.state = "running";
    return Promise.resolve();
  };
  ctx.createGain = function () {
    return { gain: { value: 1, setValueAtTime() {}, linearRampToValueAtTime() {},
      exponentialRampToValueAtTime() {}, setTargetAtTime() {} },
      connect(d) { return d; }, disconnect() {} };
  };
  ctx.createOscillator = function () {
    return { type: "sine", frequency: { value: 0 }, connect(d) { return d; },
      start() { ctx.oscStarts++; }, stop() {} };
  };
  return ctx;
}

function makeEnv(opts) {
  opts = opts || {};
  const env = { flash: new Set(), toasts: [], notifications: [], timers: [] };
  const flashEl = { offsetWidth: 1,
    classList: { add(c) { env.flash.add(c); }, remove(c) { env.flash.delete(c); },
      contains(c) { return env.flash.has(c); } } };
  env.document = { hidden: false, getElementById(id) { return id === "alarmFlash" ? flashEl : null; } };
  function Notification(title, options) {
    env.notifications.push({ title: title, options: options });
    this.close = function () {};
  }
  Notification.permission = opts.permission || "granted";
  env.Notification = Notification;
  env.window = { Notification: Notification,
    AudioContext: opts.noAudio ? undefined : function () { return env.ctx; },
    webkitAudioContext: undefined };
  env.toast = function (msg) { env.toasts.push(msg); };
  env.setTimeout = function (fn, ms) { env.timers.push({ fn: fn, ms: ms }); return env.timers.length; };
  env.clearTimeout = function () {};
  env.S = { settings: { sound: "classic", vol: 80 } };
  return env;
}

function makeRuntime(src, env) {
  const parts = [
    functionText(src, "function audio(){"),
    functionText(src, "function audioResume(){"),
    functionText(src, "function nudgeAudio(){"),
    functionText(src, "function wakeAudio(){"),
    functionText(src, "function beep("),
    functionText(src, "function alarmFallback("),
    functionText(src, "function playAlarm(){"),
  ].join("\n");
  const A = { ctx: null, master: null, alarmGain: null,
    noise: { src: null, gain: null, lfo: null }, noiseKey: null };
  const api = new Function("A", "S", "window", "document", "$", "toast", "Notification",
    "setTimeout", "clearTimeout",
    parts + "\nreturn {A:A,audio:audio,audioResume:audioResume,nudgeAudio:nudgeAudio,"
      + "wakeAudio:wakeAudio,playAlarm:playAlarm};")(
    A, env.S, env.window, env.document, (id) => env.document.getElementById(id),
    env.toast, env.Notification, env.setTimeout, env.clearTimeout);
  return api;
}

/* ---------------- 1. AudioContext 状态变化自动恢复 ---------------- */
async function stateChangeCheck(src) {
  const out = [];
  const ctx = makeCtx("running", "ok");
  const env = makeEnv();
  env.ctx = ctx;
  const rt = makeRuntime(src, env);
  rt.audio();
  out.push({ n: "建上下文时挂上 onstatechange", ok: typeof ctx.onstatechange === "function",
    detail: "typeof=" + typeof ctx.onstatechange });
  const before = ctx.resumeCalls;
  ctx.state = "running";
  if (typeof ctx.onstatechange === "function") ctx.onstatechange();
  out.push({ n: "running 状态不空转 resume", ok: ctx.resumeCalls === before,
    detail: "calls=" + (ctx.resumeCalls - before) });

  ctx.state = "suspended";
  if (typeof ctx.onstatechange === "function") ctx.onstatechange();
  out.push({ n: "suspended 立刻重调 resume", ok: ctx.resumeCalls === before + 1,
    detail: "calls=" + (ctx.resumeCalls - before) });

  ctx.state = "interrupted";
  if (typeof ctx.onstatechange === "function") ctx.onstatechange();
  out.push({ n: "interrupted 也重调 resume", ok: ctx.resumeCalls === before + 2,
    detail: "calls=" + (ctx.resumeCalls - before) });

  await flush();
  out.push({ n: "后台自动恢复失败不冒充闹钟失败（不闪不弹）",
    ok: env.flash.size === 0 && env.toasts.length === 0 && env.notifications.length === 0,
    detail: "flash=" + env.flash.size + " toast=" + env.toasts.length
      + " notif=" + env.notifications.length });
  return out;
}

/* ---------------- 2. 到点响铃：挂起先恢复，失败才兜底 ---------------- */
async function alarmCheck(src) {
  const out = [];

  let ctx = makeCtx("running", "ok");
  let env = makeEnv();
  env.ctx = ctx;
  let rt = makeRuntime(src, env);
  rt.audio();
  rt.playAlarm();
  out.push({ n: "上下文正常时按 sound=classic 排 7 个音",
    ok: ctx.oscStarts === 7 && env.flash.size === 0 && env.toasts.length === 0,
    detail: "osc=" + ctx.oscStarts + " flash=" + env.flash.size + " toast=" + env.toasts.length });

  ctx = makeCtx("suspended", "ok");
  env = makeEnv();
  env.ctx = ctx;
  rt = makeRuntime(src, env);
  rt.audio();
  rt.playAlarm();
  await flush();
  out.push({ n: "挂起但 resume 成功：先恢复再响，不误报",
    ok: ctx.resumeCalls >= 1 && ctx.oscStarts === 7 && env.flash.size === 0
      && env.toasts.length === 0 && env.notifications.length === 0,
    detail: "resume=" + ctx.resumeCalls + " osc=" + ctx.oscStarts
      + " flash=" + env.flash.size + " toast=" + env.toasts.length });

  ctx = makeCtx("suspended", "reject");
  env = makeEnv();
  env.ctx = ctx;
  rt = makeRuntime(src, env);
  rt.audio();
  rt.playAlarm();
  await flush();
  out.push({ n: "resume 被浏览器拒绝：不再硬排音，转视觉闪烁",
    ok: ctx.oscStarts === 0 && env.flash.has("on"), detail: "osc=" + ctx.oscStarts
      + " flash=" + Array.from(env.flash).join(",") });
  out.push({ n: "resume 被拒绝：toast 说清提示音没响",
    ok: env.toasts.length === 1 && /提示音/.test(env.toasts[0]), detail: JSON.stringify(env.toasts) });
  out.push({ n: "resume 被拒绝：拿到通知权限就补系统通知",
    ok: env.notifications.length === 1 && /提示音/.test(env.notifications[0].title),
    detail: JSON.stringify(env.notifications.map((n) => n.title)) });

  ctx = makeCtx("suspended", "reject");
  env = makeEnv({ permission: "denied" });
  env.ctx = ctx;
  rt = makeRuntime(src, env);
  rt.audio();
  rt.playAlarm();
  await flush();
  out.push({ n: "没有通知权限也不静默：闪烁与 toast 仍在",
    ok: env.flash.has("on") && env.toasts.length === 1 && env.notifications.length === 0,
    detail: "flash=" + env.flash.size + " toast=" + env.toasts.length
      + " notif=" + env.notifications.length });

  env = makeEnv({ noAudio: true });
  rt = makeRuntime(src, env);
  rt.playAlarm();
  out.push({ n: "整个 AudioContext 不可用：同步兜底，不假装响过",
    ok: env.flash.has("on") && env.toasts.length === 1 && env.notifications.length === 1,
    detail: "flash=" + env.flash.size + " toast=" + env.toasts.length
      + " notif=" + env.notifications.length });
  return out;
}

/* ---------------- 3. 用户主动静音不算失败 ---------------- */
async function silenceCheck(src) {
  const out = [];
  for (const [label, sound, vol] of [["sound=none", "none", 80], ["vol=0", "classic", 0]]) {
    const ctx = makeCtx("suspended", "reject");
    const env = makeEnv();
    env.ctx = ctx;
    env.S.settings.sound = sound;
    env.S.settings.vol = vol;
    const rt = makeRuntime(src, env);
    rt.audio();
    rt.playAlarm();
    await flush();
    out.push({ n: "主动静音（" + label + "）不恢复、不闪烁、不通知",
      ok: ctx.resumeCalls === 0 && ctx.oscStarts === 0 && env.flash.size === 0
        && env.toasts.length === 0 && env.notifications.length === 0,
      detail: "resume=" + ctx.resumeCalls + " osc=" + ctx.oscStarts
        + " flash=" + env.flash.size + " toast=" + env.toasts.length });
  }
  return out;
}

/* ---------------- 4. 手势/回到前台把上下文唤醒 ---------------- */
async function wakeCheck(src) {
  const out = [];
  const ctx = makeCtx("suspended", "ok");
  const env = makeEnv();
  env.ctx = ctx;
  const rt = makeRuntime(src, env);
  rt.wakeAudio();
  out.push({ n: "第一次手势就建上下文（用户激活里创建）",
    ok: rt.A.ctx === ctx && ctx.resumeCalls === 0,
    detail: "ctx=" + (rt.A.ctx === ctx) + " resume=" + ctx.resumeCalls });
  rt.wakeAudio();
  out.push({ n: "后续手势在挂起时补 resume", ok: ctx.resumeCalls >= 1,
    detail: "resume=" + ctx.resumeCalls });
  const after = ctx.resumeCalls;
  ctx.state = "running";
  rt.wakeAudio();
  out.push({ n: "已经 running 的手势不空转", ok: ctx.resumeCalls === after,
    detail: "resume=" + (ctx.resumeCalls - after) });

  const env2 = makeEnv({ noAudio: true });
  const rt2 = makeRuntime(src, env2);
  rt2.nudgeAudio();
  out.push({ n: "没有上下文时 nudge 不自作主张创建", ok: rt2.A.ctx === null,
    detail: "ctx=" + rt2.A.ctx });

  out.push({ n: "pointerdown/keydown/touchstart 都挂了唤醒",
    ok: src.indexOf('["pointerdown","keydown","touchstart"].forEach(ev=>document.addEventListener(ev, wakeAudio, {passive:true}));') >= 0,
    detail: "静态锚点（三种手势）" });
  out.push({ n: "窗口重新可见与 pageshow 也补一次唤醒",
    ok: src.indexOf('document.addEventListener("visibilitychange",()=>{ if(!document.hidden) nudgeAudio(); });') >= 0
      && src.indexOf('window.addEventListener("pageshow", nudgeAudio);') >= 0,
    detail: "静态锚点（visibilitychange/pageshow）" });
  return out;
}

/* ---------------- 5. 视觉兜底必须真的存在于页面 ---------------- */
function flashMarkupCheck(src) {
  const out = [];
  out.push({ n: "页面有独立的告警闪烁层",
    ok: src.indexOf('<div id="alarmFlash" aria-hidden="true"></div>') >= 0,
    detail: "静态锚点 #alarmFlash" });
  out.push({ n: "闪烁层不拦点击（pointer-events:none）",
    ok: /#alarmFlash\{[^}]*pointer-events:none/.test(src), detail: "静态锚点 CSS" });
  out.push({ n: "闪烁动画真的定义在样式里",
    ok: /@keyframes alarmFlash\{/.test(src) && /#alarmFlash\.on\{[^}]*animation:alarmFlash/.test(src),
    detail: "静态锚点 @keyframes/#alarmFlash.on" });
  return out;
}

async function runAll(src) {
  const groups = [["statechange", stateChangeCheck], ["alarm", alarmCheck],
    ["silence", silenceCheck], ["wake", wakeCheck], ["markup", flashMarkupCheck]];
  const results = [];
  for (const [tag, fn] of groups) {
    try { results.push(...(await fn(src)).map((r) => ({ ...r, tag: tag }))); }
    catch (e) { results.push({ tag: tag, n: tag + " 整组未跑成（锚点/形状变了）", ok: false, detail: e.message }); }
  }
  return results;
}

(async () => {
  if (SELFTEST) {
    const base = await runAll(SRC);
    const baseBad = base.filter((r) => !r.ok);
    console.log("基线（未变异）：" + (baseBad.length ? "红 " + baseBad.length + " 条 ← 先修产品再谈证伪" : "全绿"));
    if (baseBad.length) {
      console.log(baseBad.map((r) => "  FAIL " + r.n + " ｜" + r.detail).join("\n"));
      process.exit(1);
    }
    const MUTS = [
      ["M1 onstatechange 不再自动恢复",
        'if(st==="suspended" || st==="interrupted") audioResume();',
        "if(false) audioResume();"],
      ["M2 AudioContext 不可用时不兜底", 'if(!c){ alarmFallback("这个窗口不支持声音"); return; }', "if(!c) return;"],
      ["M3 resume 失败后不兜底",
        'audioResume().then(ok=>{ if(ok) fire(); else alarmFallback("浏览器要求先点一下页面才能出声"); });',
        "audioResume().then(ok=>{ if(ok) fire(); });"],
      ["M4 第一次手势不再建上下文", "if(!A.ctx){ audio(); return; }", "if(!A.ctx) return;"],
      ["M5 页面缺少告警闪烁层", '<div id="alarmFlash" aria-hidden="true"></div>', "<!-- no flash -->"],
      ["M6 音量 0 也被当成要响", 'if(k==="none" || v<=0) return;', 'if(k==="none") return;'],
      ["M7 少挂 pageshow 唤醒", 'window.addEventListener("pageshow", nudgeAudio);', ";"],
    ];
    let nop = 0, missed = 0, caught = 0;
    for (const [name, from, to] of MUTS) {
      const hits = BASE_SRC.split(from).length - 1;
      if (hits !== 1) { console.log("NOP    " + name + " ｜锚点命中 " + hits + " 处（要求恰好 1 处）"); nop++; continue; }
      const mutated = BASE_SRC.replace(from, to);
      if (mutated === BASE_SRC) { console.log("NOP    " + name + " ｜改出来的字节与原字节相同"); nop++; continue; }
      const res = await runAll(mutated);
      const red = res.filter((r) => !r.ok);
      if (!red.length) { console.log("MISSED " + name + " ｜注入后仍然全绿"); missed++; continue; }
      caught++;
      console.log("CAUGHT " + name + " ｜红 " + red.length + " 条：" + red.map((r) => r.n).join("／"));
    }
    const ok = !missed && !nop;
    console.log("\n计数：CAUGHT " + caught + " ／ MISSED " + missed + " ／ NOP " + nop
      + " ／ 登记 " + MUTS.length + " 条");
    console.log(ok ? "RC=0 ｜每一注都能被已知答案点名" : "RC=1 ｜有注入悄悄过去了，判据不可信");
    process.exit(ok ? 0 : 1);
  }

  const results = await runAll(SRC);
  const bad = results.filter((r) => !r.ok);
  for (const r of results) {
    console.log((r.ok ? "  [PASS] " : "  [FAIL] ") + r.n + (r.ok ? "" : " ｜" + r.detail));
  }
  console.log("\n" + (bad.length ? "红 " + bad.length + " 条" : "全部通过")
    + "（" + results.length + " 条已知答案，文件 " + FILE + "）");
  process.exit(bad.length ? 1 : 0);
})();
