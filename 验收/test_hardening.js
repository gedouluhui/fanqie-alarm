/* Masterplan 第五部分加固项的已知答案真值表（XSS／CSV 注入／跨零点 CSV 时间／回拨夜分桶）。
   用法：node 验收/test_hardening.js [index.html] [--selftest]
   · 被测函数不是手抄副本，是从 index.html 现盘字节里按锚点切出来 eval 的；锚点缺失＝该组判红（不作数）。
   · --selftest 把本文件要防的七种回归逐个注回内存里的源码，要求每一注都能让至少一组翻红；
     改不出字节的记 NOP，绝不算成"抓到了"，也不为了变绿放宽判据。 */
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
function sliceBetween(src, a, b, why) {
  const i = src.indexOf(a);
  if (i < 0) throw new Error("锚点缺失（" + why + "）：" + a);
  const j = src.indexOf(b, i + a.length);
  if (j < 0) throw new Error("终点缺失（" + why + "）：" + b);
  return src.slice(i, j + b.length);
}
function sliceTo(src, a, b, why) {
  const i = src.indexOf(a);
  if (i < 0) throw new Error("锚点缺失（" + why + "）：" + a);
  const j = src.indexOf(b, i + a.length);
  if (j < 0) throw new Error("终点缺失（" + why + "）：" + b);
  return src.slice(i, j);
}
const dayKeyOf = (d) => d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") +
  "-" + String(d.getDate()).padStart(2, "0");

/* ---------------- 1. 存储型 XSS：最近记录里 reason/任务名只许以文本出现 ---------------- */
function xssCheck(src) {
  const esc = sliceBetween(src, "function esc(t){", "\n", "esc 的一行实现");
  const block = sliceBetween(src,
    "const list = S.sessions.slice().sort((a,b)=>(b.ts||0)-(a.ts||0)).slice(0,8);",
    '}).join("");', "最近记录模板");
  const rec = { innerHTML: "" };
  const render = new Function("S", "rec", "labelOf", "Date",
    esc + "\n" + block + "\nreturn rec.innerHTML;");
  const evil = "<img src=x onerror=alert(1)>";
  const html = render({
    sessions: [{ id: "s1", ts: new Date(2026, 10, 13, 9, 0, 0).getTime(), day: "2026-11-13",
      hour: 9, type: "focus", minutes: 25, status: "abort", reason: evil, taskTitle: "<b>x</b>" }],
  }, rec, (t) => (t === "focus" ? "专注" : "休息"), Date);
  const out = [];
  out.push({ n: "XSS 最近记录：放弃理由只以文本出现",
    ok: html.indexOf("&lt;img src=x onerror=alert(1)&gt;") >= 0 && html.indexOf("<img") < 0,
    detail: html.slice(0, 220) });
  out.push({ n: "XSS 最近记录：任务名同样被转义",
    ok: html.indexOf("<b>x</b>") < 0 && html.indexOf("&lt;b&gt;x&lt;/b&gt;") >= 0,
    detail: html.slice(0, 220) });
  out.push({ n: "XSS 任务投入：note 走 esc（纵深防御）",
    ok: src.indexOf('(note?`<div class="lempty">${esc(note)}</div>`:"")') >= 0,
    detail: "静态锚点（note 目前是常量文案，没有可注入入口）" });
  return out;
}

/* ---------------- 2. CSV 注入：前导空白／NUL 绕过 ---------------- */
function csvCellCheck(src) {
  const fn = functionText(src, "function csvCell(v){");
  const csvCell = new Function(fn + "\nreturn csvCell;")();
  const cases = [
    ["=1+1", "'=1+1", "= 开头加单引号"],
    [" =1+1", "' =1+1", "空格后接 = 也要挡"],
    ["\u00A0+1", "'\u00A0+1", "不间断空格后接 + 也要挡"],
    ["\t=1", "'\t=1", "制表符后接 = 也要挡"],
    ["\r@x", "\"'\r@x\"", "回车后接 @ 也要挡（含换行会被 RFC4180 加引号）"],
    ["\0=cmd", "'=cmd", "NUL 先剔除再判公式"],
    ["-2", "'-2", "负数仍按文本保护"],
    ["hello", "hello", "普通文本原样"],
    ["a,b", '"a,b"', "逗号加引号"],
    ['a"b', '"a""b"', "引号翻倍"],
    [null, "", "空值"],
  ];
  return cases.map(([inp, exp, why]) => ({
    n: "CSV 单元格：" + why,
    ok: csvCell(inp) === exp,
    detail: JSON.stringify(inp) + " → " + JSON.stringify(csvCell(inp)) + "（期望 " + JSON.stringify(exp) + "）",
  }));
}

/* ---------------- 3. recordSession 必须记下起表墙上时刻 ---------------- */
function recordStartTsCheck(src) {
  // 记录草稿与实际记账共用产品实现；旧版无草稿函数时仍验证旧实现。
  const draft = src.includes("function sessionDraft(") ? functionText(src, "function sessionDraft(") : "";
  const transaction=src.includes("function settleSession(")
    ? sliceTo(src,"const RECEIPT_CAP =","function mergeSave(","累计凭据") + "\n" +
      sliceTo(src,"function newSessionId()","function sessionDraft(","稳定身份") + "\n" +
      sliceTo(src,"const CAP =","const NUM_RANGE", "窗口容量") + "\n" +
      functionText(src,"function cleanSession(") + "\n" + functionText(src,"function cleanTask(") + "\n" +
      functionText(src,"function dayReal(") + "\nconst uncommittedSessions=new Map();\n" : "";
  const fn = transaction + draft + "\n" + functionText(src, "function recordSession(");
  const now = new Date(2026, 10, 13, 0, 20, 0).getTime();
  const swAt = new Date(2026, 10, 12, 23, 50, 0).getTime();
  const S = { sessions: [], tasks: [], handoffReceipts: [] };
  const T = { swAt };
  const recordSession = new Function("S", "T", "activeTask", "dayKey", "dlCleanSplit", "statsDirty", "Date",
    fn + "\nreturn recordSession;")(S, T, () => null, dayKeyOf, () => null, () => {}, Date);
  recordSession("focus", 30, "done", null, null);
  const rec = S.sessions[0];
  const out = [];
  out.push({ n: "记录带 startTs＝起表墙上时刻",
    ok: rec.startTs === swAt, detail: "startTs=" + rec.startTs + " 期望 " + swAt });
  out.push({ n: "归属日/时段仍按起表时刻（23:50 属前一天 23 点）",
    ok: rec.day === "2026-11-12" && rec.hour === 23, detail: rec.day + "/" + rec.hour + " 点" });
  T.swAt = 0; S.sessions.length = 0;
  recordSession("focus", 25, "done", null, null);
  const r2 = S.sessions[0];
  out.push({ n: "没有 swAt 时 startTs 退回记录时刻",
    ok: r2.startTs === r2.ts, detail: "startTs=" + r2.startTs + " ts=" + r2.ts });
  return out;
}

/* ---------------- 4. cleanSession 必须让 startTs 活着过一遍存盘/导入 ---------------- */
function cleanSessionCheck(src) {
  const dayRealFn = functionText(src, "function dayReal(s){");
  const dayReal = new Function(dayRealFn + "\nreturn dayReal;")();
  const fn = functionText(src, "function cleanSession(x){");
  const cleanSession = new Function("dayReal", "dayKey", "dlCleanSplit",
    fn + "\nreturn cleanSession;")(dayReal, dayKeyOf, () => null);
  const ts = new Date(2026, 10, 13, 0, 20, 0).getTime();
  const startTs = new Date(2026, 10, 12, 23, 50, 0).getTime();
  const base = { id: "x", ts, day: "2026-11-12", hour: 23, type: "focus", minutes: 30, status: "done" };
  const a = cleanSession({ ...base, startTs });
  const b = cleanSession({ ...base });
  const c = cleanSession({ ...base, startTs: "abc" });
  const d = cleanSession({ ...base, startTs: -5 });
  const out = [];
  out.push({ n: "导入/重载保留合法 startTs", ok: a.startTs === startTs, detail: "got " + a.startTs });
  out.push({ n: "老记录没有 startTs ⇒ 退回 ts", ok: b.startTs === ts, detail: "got " + b.startTs });
  out.push({ n: "非法 startTs（字符串）⇒ 退回 ts", ok: c.startTs === ts, detail: "got " + c.startTs });
  out.push({ n: "负数 startTs ⇒ 退回 ts", ok: d.startTs === ts, detail: "got " + d.startTs });
  return out;
}

/* ---------------- 5. CSV 导出的日期/时间与 day/hour 同源（起表时刻） ---------------- */
function csvRowCheck(src) {
  const fn = functionText(src, "function csvCell(v){");
  const csvCell = new Function(fn + "\nreturn csvCell;")();
  const block = sliceTo(src, 'const rows=[["日期","时间","类型","状态","分钟","任务","理由","跨零点分账"]];',
    "const csv=rows.map", "CSV 行拼装");
  const tsCross = new Date(2026, 10, 13, 0, 20, 0).getTime();      // 结束：11-13 00:20
  const stCross = new Date(2026, 10, 12, 23, 50, 0).getTime();    // 开始：11-12 23:50
  const tsOld = new Date(2026, 10, 12, 9, 15, 0).getTime();
  const tsRewind = new Date(2026, 10, 12, 23, 40, 0).getTime();   // 钟被往回拨到起表之前
  const S = { sessions: [
    { id: "a", ts: tsCross, startTs: stCross, day: "2026-11-12", hour: 23, type: "focus",
      minutes: 30, status: "done", taskTitle: "", reason: null },
    { id: "b", ts: tsOld, day: "2026-11-12", hour: 9, type: "focus",
      minutes: 25, status: "done", taskTitle: "", reason: null },
    { id: "c", ts: tsRewind, startTs: stCross, day: "2026-11-12", hour: 23, type: "focus",
      minutes: 10, status: "done", taskTitle: "", reason: null },
  ] };
  const rows = new Function("S", "dayKey", "dlCleanSplit", "csvCell", "Date",
    block + "\nreturn rows;")(S, dayKeyOf, () => null, csvCell, Date);
  /* 行按 ts 升序：老记录 b（11-12 09:15）→ 回拨 c（11-12 23:40）→ 跨零点 a（11-13 00:20）。
     期望值按这个顺序取，不按 fixture 的书写顺序——排序是产品行为的一部分。 */
  const out = [];
  out.push({ n: "CSV 老记录没有 startTs ⇒ 退回 ts",
    ok: rows[1][0] === "2026-11-12" && rows[1][1] === "09:15",
    detail: rows[1][0] + " " + rows[1][1] });
  out.push({ n: "CSV 系统钟往回拨：仍按 startTs 出时间",
    ok: rows[2][0] === "2026-11-12" && rows[2][1] === "23:50",
    detail: rows[2][0] + " " + rows[2][1] });
  out.push({ n: "CSV 跨零点：日期/时间取起表时刻（不是结束时刻）",
    ok: rows[3][0] === "2026-11-12" && rows[3][1] === "23:50",
    detail: rows[3][0] + " " + rows[3][1] + "（期望 2026-11-12 23:50）" });
  return out;
}

/* ---------------- 6. 秋季回拨夜：同一小时最多 7200 秒，不许硬截成 3600 ---------------- */
function dlCleanBKCheck(src) {
  const dayRealFn = functionText(src, "function dayReal(s){");
  const dayReal = new Function(dayRealFn + "\nreturn dayReal;")();
  const fn = functionText(src, "function dlCleanBK(arr){");
  const dlCleanBK = new Function("dayReal", fn + "\nreturn dlCleanBK;")(dayReal);
  const D1 = "2026-11-01";
  const got = dlCleanBK([[D1, 1, 7200], [D1, 2, 7201]]);
  const out = [];
  out.push({ n: "回拨夜同一小时 7200 秒原样保留",
    ok: JSON.stringify(got) === JSON.stringify([[D1, 1, 7200], [D1, 2, 7200]]),
    detail: JSON.stringify(got) });
  out.push({ n: "假日子仍被丢掉",
    ok: JSON.stringify(dlCleanBK([["2026-13-45", 1, 7200]])) === "[]",
    detail: JSON.stringify(dlCleanBK([["2026-13-45", 1, 7200]])) });
  return out;
}

function runAll(src) {
  const groups = [["XSS", xssCheck], ["CSV", csvCellCheck], ["startTs", recordStartTsCheck],
    ["cleanSession", cleanSessionCheck], ["CSV 行", csvRowCheck], ["dlCleanBK", dlCleanBKCheck]];
  const results = [];
  for (const [tag, fn] of groups) {
    try { results.push(...fn(src).map((r) => ({ ...r, tag }))); }
    catch (e) { results.push({ tag, n: tag + " 整组未跑成（锚点/形状变了）", ok: false, detail: e.message }); }
  }
  return results;
}

if (SELFTEST) {
  let base;
  try { base = runAll(SRC); }
  catch (e) { console.log("FAIL 读不到基线：" + e.message); process.exit(1); }
  const baseBad = base.filter((r) => !r.ok);
  console.log("基线（未变异）：" + (baseBad.length ? "红 " + baseBad.length + " 条 ← 先修产品再谈证伪" : "全绿"));
  if (baseBad.length) { console.log(baseBad.map((r) => "  FAIL " + r.n + " ｜" + r.detail).join("\n")); process.exit(1); }
  const MUTS = [
    ["M1 最近记录的 reason 不转义", "${esc(status)}", "${status}"],
    ["M2 任务投入的 note 不转义", "${esc(note)}", "${note}"],
    ["M3 csvCell 不剔 NUL", '.replace(/\\0/g,"")', ""],
    ["M4 csvCell 公式正则退回旧版（前导空白可绕过）",
      'if(/^[\\s\\u00A0]*[=+\\-@]|^[\\t\\r]/.test(s)) s="\'"+s;',
      'if(/^[=+\\-@\\t\\r]/.test(s)) s="\'"+s;'],
    ["M5 recordSession 不写 startTs", ", startTs:st.getTime()", ""],
    ["M6 cleanSession 丢掉 startTs", "ts, startTs,", "ts,"],
    ["M7 CSV 行退回结束时刻", "Number(x.startTs)||Number(x.ts)", "Number(x.ts)"],
    ["M8 回拨夜仍硬截 3600 秒", "Math.min(7200, s)", "Math.min(3600, s)"],
  ];
  let nop = 0, missed = 0, caught = 0;
  for (const [name, from, to] of MUTS) {
    const hits = BASE_SRC.split(from).length - 1;
    if (hits !== 1) { console.log("NOP    " + name + " ｜锚点命中 " + hits + " 处（要求恰好 1 处）"); nop++; continue; }
    const mutated = BASE_SRC.replace(from, to);
    if (mutated === BASE_SRC) { console.log("NOP    " + name + " ｜改出来的字节与原字节相同"); nop++; continue; }
    const res = runAll(mutated);
    const red = res.filter((r) => !r.ok);
    if (!red.length) { console.log("MISSED " + name + " ｜注入后仍然全绿"); missed++; continue; }
    caught++;
    console.log("CAUGHT " + name + " ｜红 " + red.length + " 条：" + red.map((r) => r.n).join("／"));
  }
  const ok = !missed && !nop;
  console.log("\n计数：CAUGHT " + caught + " ／ MISSED " + missed + " ／ NOP " + nop + " ／ 登记 " + MUTS.length + " 条");
  console.log(ok ? "RC=0 ｜每一注都能被已知答案点名" : "RC=1 ｜有注入悄悄过去了，判据不可信");
  process.exit(ok ? 0 : 1);
}

const results = runAll(SRC);
const bad = results.filter((r) => !r.ok);
for (const r of results) console.log((r.ok ? "  [PASS] " : "  [FAIL] ") + r.n + (r.ok ? "" : " ｜" + r.detail));
console.log("\n" + (bad.length ? "红 " + bad.length + " 条" : "全部通过") + "（" + results.length + " 条已知答案，文件 " + FILE + "）");
process.exit(bad.length ? 1 : 0);
