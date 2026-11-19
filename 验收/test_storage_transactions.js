/* node 验收/test_storage_transactions.js [index.html]
   只读取指定页面源码；Storage、文件读取、确认框和浏览器边界均在内存中。
   load/save/mergeSave/stopAll/saveRT/导入导出接线/pagehide 使用真实源码，不复制产品逻辑。 */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const nodeTest = require("node:test");
// 任何未应答的确认框/未结算事务都必须以失败收口，不能把测试进程挂死。
// 变异证伪时尤其重要：挂起会让“变异是否被断言点名”变成不可判定的超时。
const test = (name, fn) => nodeTest(name, { timeout: 15000 }, fn);
const FILE = path.resolve(process.argv[2] || path.join(__dirname, "..", "index.html"));
const SOURCE = fs.readFileSync(FILE, "utf8");
const STORE = "fanqie-alarm.v1";
const OWNER = "fanqie-alarm.owner";
const RT = "fanqie-alarm.runtime.v1";
const BROKEN = '{"ver":2,"tasks":[{"id":"only-copy"}';

function cut(from, to) {
  const start = SOURCE.indexOf(from);
  assert.notEqual(start, -1, "源码起点缺失：" + from);
  const end = SOURCE.indexOf(to, start + from.length);
  assert.notEqual(end, -1, "源码终点缺失：" + to);
  return SOURCE.slice(start, end);
}
const PRODUCT = [
  cut("const STORE_KEY =", "/* ---------------- 音频"),
  cut("const mono = () =>", "/* ---------------- DOM 小工具"),
  cut('window.addEventListener("storage",', 'window.addEventListener("blur",'),
  cut('$("btnMain").onclick=', '/* ---------------- 通用问答弹窗'),
  cut('let pickedReason=null;', '$("hdrDate").onclick'),
  cut('function renderSegs(){', '/* ---------------- 待办'),
  cut("// 导入导出", '$("btnWipe").onclick'),
  cut("const _rt = restoreRT();", "// 滚动过一点"),
].join("\n");

class MemoryStorage {
  constructor(entries = {}) {
    this.data = new Map(Object.entries(entries));
    this.events = [];
    this.fail = () => false;
    this.observe = () => {};
  }
  get length() { return this.data.size; }
  key(index) { return [...this.data.keys()][index] ?? null; }
  peek(key) { return this.data.get(key) ?? null; }
  access(op, key, value) {
    this.events.push({ op, key, value });
    this.observe(op, key, value);
    if (this.fail(op, key, value)) {
      const error = new Error("Storage denied: " + op + " " + key);
      error.name = "QuotaExceededError";
      throw error;
    }
  }
  getItem(key) { this.access("get", key); return this.peek(key); }
  setItem(key, value) { this.access("set", key, String(value)); this.data.set(key, String(value)); }
  removeItem(key) { this.access("remove", key); this.data.delete(key); }
}

function world(storage = new MemoryStorage()) {
  const nodes = new Map(), timers = new Map(), handlers = new Map();
  const messages = [], effects = [], readers = [], downloads = [], questions = [];
  let nextTimer = 1, clock = 1000;
  const epoch = Date.now() - clock;
  class ClockDate extends Date {
    constructor(...args) { super(...(args.length ? args : [epoch + clock])); }
    static now() { return epoch + clock; }
  }
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, {
      value: "", files: [], dataset: {}, classList: { toggle() {}, add() {}, remove() {}, contains() { return false; } },
      addEventListener(name, fn) { this[name] = fn; },
      querySelectorAll() { return this.children || []; },
      click() { return this.onclick?.(); },
    });
    return nodes.get(id);
  };
  const boundary = name => () => {
    effects.push({ name, archive: storage.peek(STORE) });
    storage.events.push({ op: "effect", name });
  };
  const context = vm.createContext({
    localStorage: storage, Date: ClockDate,
    console: { warn() {} },
    window: {
      performance: { now: () => clock },
      addEventListener(name, fn) {
        if (!handlers.has(name)) handlers.set(name, []);
        handlers.get(name).push(fn);
      },
    },
    performance: { now: () => clock },
    document: { getElementById: node, createElement: () => node("download"), hidden: false, hasFocus: () => true },
    $: node,
    Blob,
    URL: { createObjectURL(blob) { downloads.push(blob); return "blob:memory"; }, revokeObjectURL() {} },
    FileReader: class {
      constructor() { readers.push(this); }
      readAsText(file) { this.result = file.text; }
    },
    setTimeout(fn, delay) { const id = nextTimer++; timers.set(id, { fn, delay }); return id; },
    clearTimeout(id) { timers.delete(id); },
    setInterval() { return nextTimer++; }, clearInterval() {},
    toast: message => messages.push(message),
    ask: options => new Promise(resolve => questions.push({ options, resolve })),
    render: boundary("render"), renderAll: boundary("renderAll"), statsDirty: boundary("statsDirty"),
    applySettingsToUI: boundary("applySettingsToUI"), applyTheme: boundary("applyTheme"), applyZoom: boundary("applyZoom"),
    playBlocked: boundary("playBlocked"), exitFs: boundary("exitFs"), setNoise: boundary("setNoise"),
    playAlarm: boundary("playAlarm"), requestFs: boundary("requestFs"),
  });
  vm.runInContext(PRODUCT, context, { filename: FILE });
  const run = code => vm.runInContext(code, context);
  // 执行真实的启动认领接线，心跳不自动推进，也不把布尔变量当所有权。
  for (const [id, timer] of timers) if (timer.delay === 0) { timers.delete(id); timer.fn(); }
  effects.length = 0;
  storage.events.length = 0;
  return {
    storage, messages, effects, downloads, questions, run, node,
    advance: seconds => { clock += seconds * 1000; },
    json: code => JSON.parse(run("JSON.stringify(" + code + ")")),
    fire: (name, event = {}) => { for (const fn of handlers.get(name) || []) fn(event); },
    beginImport(text) {
      const input = node("fileIn"); input.files = [{ text }]; input.value = "backup.json";
      input.onchange({ target: input });
      const reader = readers.at(-1);
      return reader ? reader.onload() : Promise.resolve();
    },
  };
}

function writes(storage, key = STORE) {
  return storage.events.filter(event => event.op === "set" && event.key === key);
}

// 删除坏档保全闸门会覆盖唯一原文；旧 .corrupt 不能充当当前原文的凭据。
for (const backup of [null, "older-broken-archive"]) {
  test("Task1: failed corrupt preservation keeps original bytes, backup=" + backup, () => {
    const storage = new MemoryStorage({ [STORE]: BROKEN, ...(backup === null ? {} : { [STORE + ".corrupt"]: backup }) });
    storage.fail = (op, key) => op === "set" && key === STORE + ".corrupt";
    const w = world(storage);
    const result = w.run("save()");
    assert.equal(storage.peek(STORE), BROKEN, "唯一坏档不得被默认档覆盖");
    assert.equal(result, false, "未保全时 save 必须返回 false");
    storage.fail = () => false;
    assert.equal(w.run("save()"), false, "错误提示消失/存储恢复不能解除原文保护");
    assert.equal(storage.peek(STORE + ".corrupt"), backup);
    assert.equal(writes(storage).length, 0);
  });
}

test("Task1: a different existing corrupt backup is never overwritten", () => {
  const storage = new MemoryStorage({ [STORE]: BROKEN, [STORE + ".corrupt"]: "older-broken-archive" });
  const w = world(storage);
  assert.equal(w.run("save()"), false);
  assert.equal(storage.peek(STORE), BROKEN);
  assert.equal(storage.peek(STORE + ".corrupt"), "older-broken-archive");
});

for (const alreadyPreserved of [false, true]) {
  test("Task1: exact raw preservation permits save, existing=" + alreadyPreserved, () => {
    const storage = new MemoryStorage({ [STORE]: BROKEN, ...(alreadyPreserved ? { [STORE + ".corrupt"]: BROKEN } : {}) });
    const w = world(storage);
    assert.equal(w.run("save()"), true);
    assert.equal(storage.peek(STORE + ".corrupt"), BROKEN);
    assert.equal(JSON.parse(storage.peek(STORE)).ver, 2);
    assert.deepEqual(JSON.parse(storage.peek(STORE)).tasks, []);
  });
}

test("Task1: normal and repeated saves return true", () => {
  const w = world();
  w.run('S.tasks = [{id:"local", title:"keep"}]');
  assert.equal(w.run("save()"), true);
  const first = w.storage.peek(STORE);
  assert.equal(w.run("save()"), true);
  assert.equal(w.storage.peek(STORE), first);
  assert.equal(JSON.parse(first).tasks[0].id, "local");
});

test("Task1: save(candidate) persists candidate without changing S", () => {
  const w = world();
  const previous = w.json("S");
  assert.equal(w.run('save({...S, tasks:[{id:"candidate",title:"imported"}]})'), true);
  assert.equal(JSON.parse(w.storage.peek(STORE)).tasks[0].id, "candidate");
  assert.deepEqual(w.json("S"), previous);
});

test("Task1: rejected writes return false and can be retried", () => {
  const storage = new MemoryStorage({ [STORE]: '{"ver":2,"tasks":[]}' });
  const w = world(storage), original = storage.peek(STORE);
  storage.fail = (op, key) => op === "set" && key === STORE;
  assert.equal(w.run("save()"), false);
  assert.equal(w.run("save()"), false);
  assert.equal(storage.peek(STORE), original);
  storage.fail = () => false;
  assert.equal(w.run("save()"), true);
  assert.equal(w.run("storageOK"), true);
});

test("Task1: an unreadable original remains protected when storage recovers", () => {
  const storage = new MemoryStorage({ [STORE]: '{"ver":2,"tasks":[{"id":"old","title":"keep"}]}' });
  const original = storage.peek(STORE);
  storage.fail = (op, key) => op === "get" && key === STORE;
  const w = world(storage);
  storage.fail = () => false;
  assert.equal(w.run("save()"), false);
  assert.equal(storage.peek(STORE), original);
});

for (const authority of ["readonly", "other", "expired-other", "missing", "unreadable"]) {
  test("Task1: save fails closed without persisted authority: " + authority, () => {
    const w = world();
    const original = w.storage.peek(STORE);
    if (authority === "readonly") w.run("dualReadOnly = true");
    if (authority === "other") w.storage.setItem(OWNER, "another-window:" + Date.now());
    if (authority === "expired-other") w.storage.setItem(OWNER, "another-window:1");
    if (authority === "missing") w.storage.removeItem(OWNER);
    if (authority === "unreadable") w.storage.fail = (op, key) => op === "get" && key === OWNER;
    assert.equal(w.run("save()"), false);
    assert.equal(w.storage.peek(STORE), original);
    assert.equal(writes(w.storage).length, 0);
  });
}

test("Task1: protected export yields exact corrupt bytes and an honest warning", async () => {
  const storage = new MemoryStorage({ [STORE]: BROKEN });
  storage.fail = (op, key) => op === "set" && key.endsWith(".corrupt");
  const w = world(storage);
  assert.ok(w.messages.some(message => /保护|只读/.test(message) && /导出/.test(message)));
  assert.ok(!w.messages.some(message => /已另存为备份/.test(message)));
  w.node("btnExport").onclick();
  assert.equal(await w.downloads[0].text(), BROKEN, "不能把默认空档当成原文导出");
});

test("Task1: pagehide flushes pending state before releasing owner", () => {
  const w = world();
  w.run('S.tasks = [{id:"pending", title:"last edit"}]; saveSoon()');
  w.fire("pagehide");
  assert.equal(JSON.parse(w.storage.peek(STORE)).tasks[0].id, "pending");
  assert.equal(w.storage.peek(OWNER), null);
  const write = w.storage.events.findIndex(event => event.op === "set" && event.key === STORE);
  const release = w.storage.events.findIndex(event => event.op === "remove" && event.key === OWNER);
  assert.ok(write >= 0 && release > write, "所有权必须在最后刷盘之后才释放");
});

// 这些是测试输入；期望任务/记录字段在断言中手工给出，不调用净化函数生成期望。
function backup(ver = 2) {
  return JSON.stringify({
    ...(ver === "absent" ? {} : { ver }),
    settings: { focus: 40, every: 4, name: "Imported", sound: "none" },
    collections: [{ id: "study", name: "Study" }],
    tasks: [{ id: "imported", title: "Restored task", est: 3, donePomo: 1, focusMin: 30, cid: "study", createdAt: 1000 }],
    activeTaskId: "imported",
    sessions: [{ id: "record", ts: 1794961200000, startTs: 1794959400000, day: "2026-11-18", hour: 0,
      type: "focus", minutes: 30, status: "done", taskId: "imported", taskTitle: "Restored task" }],
    cycle: 1,
  });
}

function runningWorld() {
  const w = world();
  w.run(`S.tasks = [{id:"current",title:"Keep current task"}]; save();
    T.status="run"; T.startAt=mono(); T.acc=120; T.swAt=Date.now()-120000; T.total=1500;
    dlReset(); saveRT(); globalThis.originalS=S;`);
  w.messages.length = 0; w.effects.length = 0; w.storage.events.length = 0;
  return w;
}
function snapshot(w) {
  return { state: w.json("S"), timer: w.json("T"), archive: w.storage.peek(STORE), runtime: w.storage.peek(RT) };
}
function unchanged(w, before) {
  assert.equal(w.run("S === originalS"), true, "导入未提交不许换掉原 S 引用");
  assert.deepEqual(w.json("S"), before.state, "内存旧任务/记录必须保留");
  assert.deepEqual(w.json("T"), before.timer, "失败不能 stopAll 丢掉运行态");
  assert.equal(w.storage.peek(STORE), before.archive, "失败不能改写原存档");
  assert.equal(w.storage.peek(RT), before.runtime, "失败不能删除运行中快照");
  assert.equal(w.effects.length, 0, "失败不能刷新 UI/清统计/停止音频");
  assert.ok(!w.messages.some(message => message.includes("已恢复备份")), "失败不能显示恢复成功");
}

for (const loss of ["readonly", "other", "expired-other", "missing", "unreadable", "protected", "quota"]) {
  test("Task2: pending ask rechecks commit authority and preserves running state: " + loss, async () => {
    const w = runningWorld();
    const pending = w.beginImport(backup());
    assert.equal(w.questions.length, 1, "必须经过真实 onchange/onload 注册的 ask 通道");
    assert.equal(writes(w.storage).length, 0, "确认之前不能写入");
    assert.equal(w.effects.length, 0);
    assert.equal(w.node("fileIn").value, "");
    if (loss === "readonly") w.run("dualReadOnly=true");
    if (loss === "other") w.storage.setItem(OWNER, "other:" + Date.now());
    if (loss === "expired-other") w.storage.setItem(OWNER, "other:1");
    if (loss === "missing") w.storage.removeItem(OWNER);
    if (loss === "unreadable") w.storage.fail = (op, key) => op === "get" && key === OWNER;
    if (loss === "quota") w.storage.fail = (op, key) => op === "set" && key === STORE;
    if (loss === "protected") {
      w.storage.setItem(STORE, BROKEN);
      w.storage.fail = (op, key) => op === "set" && key.endsWith(".corrupt");
      w.run("load()"); // 确认挂起时真实 load 建立保护，不直接预设产品保护标志。
    }
    const before = snapshot(w);
    w.storage.events.length = 0;
    w.questions[0].resolve(true);
    await pending;
    unchanged(w, before);
    assert.equal(writes(w.storage).length, loss === "quota" ? 1 : 0);
    assert.ok(w.messages.some(message => /未保存|失败/.test(message)), "恢复失败需要明确反馈");
  });
}

test("Task2: cancel and invalid JSON leave archive, runtime and UI untouched", async () => {
  const w = runningWorld(), before = snapshot(w);
  const pending = w.beginImport(backup());
  w.questions[0].resolve(false); await pending;
  unchanged(w, before);
  await w.beginImport("{not-json");
  unchanged(w, before);
  assert.equal(w.questions.length, 1, "坏 JSON 不应打开确认框");
  assert.equal(writes(w.storage).length, 0);
});

for (const ver of ["absent", 0, 1, 2, "1", "2"]) {
  test("Task2: compatible backup commits before switching state/UI, ver=" + JSON.stringify(ver), async () => {
    const w = runningWorld();
    const atCommit = [];
    w.storage.observe = (op, key) => {
      if (op === "set" && key === STORE) atCommit.push({ sameState: w.run("S === originalS"), status: w.run("T.status") });
    };
    const pending = w.beginImport(backup(ver));
    assert.equal(w.questions.length, 1);
    assert.ok(w.questions[0].options.text.includes("1 个任务、1 条专注记录"));
    w.questions[0].resolve(true); await pending;
    assert.deepEqual(atCommit, [{ sameState: true, status: "run" }], "先保存候选，再切 S/stopAll");
    const disk = JSON.parse(w.storage.peek(STORE));
    assert.equal(disk.ver, 2);
    assert.deepEqual(disk.tasks, [{ id: "imported", title: "Restored task", est: 3, donePomo: 1,
      done: false, today: false, cid: "study", focusMin: 30, createdAt: 1000 }]);
    assert.deepEqual(disk.sessions, [{ id: "record", ts: 1794961200000, startTs: 1794959400000,
      day: "2026-11-18", hour: 0, type: "focus", minutes: 30, status: "done", reason: null,
      taskId: "imported", taskTitle: "Restored task" }]);
    assert.equal(disk.activeTaskId, "imported");
    assert.equal(disk.settings.focus, 40);
    assert.deepEqual(w.json("S"), disk);
    assert.equal(w.run("T.status"), "idle");
    assert.equal(w.run("T.acc"), 0);
    assert.equal(w.run("T.total"), 2400, "stopAll 应使用导入后的时长");
    assert.equal(w.storage.peek(RT), null, "成功提交后真实 saveRT 应删除旧快照");
    assert.ok(w.effects.some(effect => effect.name === "applySettingsToUI"));
    assert.ok(w.effects.every(effect => effect.archive === w.storage.peek(STORE)), "所有 UI 副作用都必须发生在落盘之后");
    assert.equal(w.messages.filter(message => message.includes("已恢复备份")).length, 1);
  });
}

for (const ver of [3, 99, "3"]) {
  test("Task2: rejects explicit future backup without replacing current data, ver=" + JSON.stringify(ver), async () => {
    const w = runningWorld(), before = snapshot(w);
    const pending = w.beginImport(backup(ver));
    // 旧实现会错误地允许确认；驱动它完成，才能观察真实破坏而非让 Promise 悬空。
    for (const question of w.questions) question.resolve(true);
    await pending;
    unchanged(w, before);
    assert.equal(w.questions.length, 0);
    assert.equal(writes(w.storage).length, 0);
    assert.ok(w.messages.some(message => /版本/.test(message)));
  });
}

test("Task2: normal export round-trips current tasks via the real import events", async () => {
  const w = runningWorld();
  w.node("btnExport").onclick();
  const exported = await w.downloads[0].text();
  assert.equal(JSON.parse(exported).tasks[0].id, "current");
  assert.ok(w.messages.some(message => /不含.*快照/.test(message)));
  const pending = w.beginImport(exported);
  w.questions[0].resolve(true); await pending;
  assert.equal(JSON.parse(w.storage.peek(STORE)).tasks[0].id, "current");
  assert.equal(w.run("S.tasks[0].id"), "current");
});

// Round2 tests name the missing transaction guarantee, not a helper implementation.
function activeWorld(seconds = 120) {
  const w = world();
  w.run('S.tasks=[{id:"mine",title:"My task",focusMin:0,donePomo:0}]; S.activeTaskId="mine"; save()');
  w.node("btnMain").onclick();
  w.advance(seconds); w.run("saveRT()");
  w.messages.length = 0; w.effects.length = 0; w.storage.events.length = 0;
  return w;
}
async function exported(w) {
  w.node("btnExport").onclick();
  return JSON.parse(await w.downloads.at(-1).text());
}
async function importConfirmed(w, data) {
  const pending = w.beginImport(JSON.stringify(data));
  assert.ok(w.questions.length, "导入应经过确认");
  w.questions.at(-1).resolve(true); await pending;
}
function otherTakes(w, deliver = true, archive = backup()) {
  const owner = "other-writer:" + w.run("Date.now()");
  const rt = JSON.stringify({kind:"short",total:300,acc:45,status:"run",tm:"count",
    ts:w.run("Date.now()"),sw:w.run("Date.now()")-45000,bk:[],pos:w.run("Date.now()")});
  w.storage.setItem(STORE, archive); w.storage.setItem(OWNER, owner); w.storage.setItem(RT, rt);
  if(deliver) w.fire("storage", {key:OWNER, newValue:owner});
  return {owner, archive, rt};
}

for(const end of ["reset-confirm", "complete", "abort", "skip"]) {
  test("Round2 F1: " + end + " preserves after authority loss before owner event", async () => {
    const w = activeWorld(), start = w.run("T.swAt");
    const pending = end === "reset-confirm" ? w.node("btnReset").onclick() : null;
    const other = otherTakes(w, false);
    if(pending) { w.questions.at(-1).resolve(true); await pending; }
    else if(end === "skip") w.node("btnSkip").onclick();
    else w.run(end + '()');
    w.fire("storage", {key:OWNER,newValue:other.owner});
    w.fire("storage", {key:STORE,newValue:other.archive});
    w.fire("pagehide");
    const out = await exported(w);
    assert.equal(out.sessions.filter(x=>x.startTs===start && x.minutes===2).length, 1, "失权结束的两分钟必须仍能取回");
    assert.equal(w.storage.peek(STORE), other.archive);
    assert.equal(w.storage.peek(RT), other.rt);
    assert.equal(handoffEntries(w.storage).length, 1);
    assert.ok(!w.messages.some(x=>/^已记录|已记入统计/.test(x)), "journal 不等于已入账");
    assert.ok(!String(w.node("endSub").textContent).includes("已记入统计"));
  });
}
for(const end of ["complete", "abort", "skip"]) {
  test("Round2 F1: " + end + " retains paused draft when archive and journal both fail", async () => {
    const w = activeWorld();
    const rt = w.storage.peek(RT), original = w.storage.peek(STORE);
    w.storage.fail = (op,key)=>op==="set" && (key===STORE || key.startsWith(HANDOFF));
    if(end==="skip") w.node("btnSkip").onclick(); else w.run(end+'()');
    assert.equal(w.run("T.status"), "pause", "失败不能清空唯一在场账，也不能自动开启下一段");
    assert.equal(w.run("T.acc"), 120);
    assert.equal(w.storage.peek(RT), rt);
    assert.equal(w.storage.peek(STORE), original);
    assert.equal((await exported(w)).sessions.filter(x=>x.minutes===2).length, 1);
    assert.ok(!w.messages.some(x=>x.startsWith("已记录")));
  });
}

test("Round2 F2: readonly main cannot resume a failed handoff", () => {
  const w = activeWorld();
  w.storage.fail = (op,key)=>op==="set" && key.startsWith(HANDOFF);
  otherTakes(w);
  assert.equal(w.run("T.status"), "pause");
  w.node("btnMain").onclick();
  assert.equal(w.run("T.status"), "pause");
});
for(const ending of ["yield", "abort", "export-running"]) {
  test("Round2 F2: legal takeover continuation refreshes same cumulative id: " + ending, async () => {
    const w = activeWorld();
    w.storage.fail = (op,key)=>op==="set" && key.startsWith(HANDOFF);
    otherTakes(w);
    const prefix = (await exported(w)).sessions.find(x=>x.taskId==="mine");
    assert.equal(prefix.minutes, 2);
    w.storage.fail = ()=>false;
    w.node("dualTake").click(); w.node("btnMain").onclick(); w.advance(60);
    if(ending==="yield") otherTakes(w);
    if(ending==="abort") w.run('abort("continued")');
    const out = await exported(w), rows = out.sessions.filter(x=>x.startTs===prefix.startTs);
    assert.equal(rows.length, 1, "旧2分钟与新3分钟不能成为两段");
    assert.equal(rows[0].id, prefix.id, "恢复继续必须复用段ID");
    assert.equal(rows[0].minutes, 3);
    assert.equal(out.tasks.find(x=>x.id==="mine").focusMin, 3);
  });
}

test("Round2 F3: latest disk plus only unsaved local records survives journal and quota failure", async () => {
  const w = activeWorld(); otherTakes(w);
  w.node("dualTake").click();
  w.run('S.tasks.push({id:"local-only",title:"Unsaved task",focusMin:0}); S.activeTaskId="local-only"; T.kind="focus"');
  w.node("btnMain").onclick(); w.advance(180);
  w.storage.fail = (op,key)=>op==="set" && key===STORE;
  w.run('abort("new-unsaved")');
  const newer = JSON.parse(backup()); newer.tasks[0].title="Newest disk task";
  w.storage.setItem(OWNER, "other:" + w.run("Date.now()"));
  w.storage.data.set(STORE, JSON.stringify(newer));
  w.fire("storage", {key:STORE,newValue:JSON.stringify(newer)});
  const out = await exported(w);
  assert.equal(out.sessions.filter(x=>x.reason==="new-unsaved" && x.minutes===3).length, 1);
  assert.equal(out.tasks.find(x=>x.id==="local-only").focusMin, 3);
  assert.equal(out.tasks.find(x=>x.id==="imported").title, "Newest disk task");
});

test("Round2 F4: unreadable journals block RT settlement and preserve original bytes", async () => {
  const w = activeWorld(); const rt = w.storage.peek(RT); otherTakes(w);
  w.storage.data.set(RT, rt); w.storage.removeItem(OWNER);
  w.storage.fail = (op,key)=>op==="get" && key.startsWith(HANDOFF);
  const reopened = world(w.storage);
  assert.equal(reopened.run("T.status"), "idle", "未核查不可恢复为可结算的暂停段");
  assert.ok(reopened.messages.some(x=>/核查|无法.*恢复/.test(x)));
  reopened.fire("pagehide");
  assert.equal(w.storage.peek(RT), rt, "待核查不是删除RT");
  w.storage.fail = ()=>false;
  reopened.run('abort("must-not-double")');
  const out = await exported(reopened);
  assert.equal(out.sessions.filter(x=>x.taskId==="mine").length, 1);
});

test("Round2: stable start id survives RT restore and repeated complete or abort", async () => {
  const w = activeWorld(); const rt = JSON.parse(w.storage.peek(RT));
  assert.ok(rt.sid, "RT必须保存稳定段ID");
  w.storage.removeItem(OWNER);
  const reopened = world(w.storage); reopened.run('abort("restored"); abort("duplicate"); complete()');
  const out = await exported(reopened);
  assert.equal(out.sessions.length, 1);
  assert.equal(out.sessions[0].id, rt.sid);
  assert.equal(out.tasks.find(x=>x.id==="mine").focusMin, 2);
});

test("Round2 F1: stale reset confirmation never settles the next timer", async () => {
  const w = activeWorld(); const pending = w.node("btnReset").onclick();
  otherTakes(w); w.node("dualTake").click(); w.node("btnMain").onclick(); w.advance(180);
  const before = w.json("T");
  w.questions.at(-1).resolve(true); await pending;
  assert.deepEqual(w.json("T"), before, "过期确认只能作用于打开时那一段");
});

function addJournals(storage, count) {
  for(let i=0;i<count;i++) {
    const session = {id:"journal-"+i,ts:1794961200000+i,startTs:1794961140000+i,day:"2026-11-18",hour:0,
      type:"focus",minutes:1,status:"abort",reason:"capacity",taskId:"imported",taskTitle:"Restored task"};
    storage.setItem(HANDOFF+"origin."+session.id, JSON.stringify({ver:1,session}));
  }
}
test("Round2 F5: 4001 journals keep totals stable across export/import cycles", async () => {
  const initial = JSON.parse(backup()); initial.sessions=[]; initial.tasks[0].focusMin=0; initial.tasks[0].donePomo=0;
  const w = world(new MemoryStorage({[STORE]:JSON.stringify(initial)})); addJournals(w.storage,4001);
  // Retained bytes simulate deletion failure. Receipts, not deletion, must guarantee idempotence.
  w.storage.fail = (op,key)=>op==="remove" && key.startsWith(HANDOFF);
  for(let i=0;i<3;i++) {
    const out = await exported(w);
    assert.equal(out.tasks[0].focusMin,4001, "导入截断窗口不能导致旧journal再加一分钟");
    assert.equal(handoffEntries(w.storage).length,4001,"下载不能消费");
    await importConfirmed(w,out);
    assert.equal(JSON.parse(w.storage.peek(STORE)).tasks[0].focusMin,4001);
  }
});
test("Round2 F5: receipt survives 4000 newer sessions and reappearing journal", async () => {
  const w = activeWorld(); otherTakes(w);
  const saved = handoffEntries(w.storage)[0];
  w.node("dualTake").click(); await importConfirmed(w,await exported(w));
  w.run('S.activeTaskId="mine"; for(let i=0;i<4000;i++) recordSession("focus",1,"abort","new",null); save()');
  w.storage.setItem(...saved);
  const out=await exported(w);
  assert.equal(out.tasks.find(x=>x.id==="mine").focusMin,4002);
  assert.ok(!w.json("S.sessions").some(x=>x.id===JSON.parse(saved[1]).session.id));
});
test("Round2 F5: journal deletion requires committed receipt, never merely export or failed import", async () => {
  const w = activeWorld(); otherTakes(w); w.node("dualTake").click();
  const out=await exported(w), entry=handoffEntries(w.storage)[0];
  w.storage.fail = (op,key)=>op==="set" && key===STORE;
  await importConfirmed(w,out);
  assert.equal(w.storage.peek(entry[0]),entry[1]);
  w.storage.fail = ()=>false;
  const receiptsAtDelete=[];
  w.storage.observe = (op,key)=>{ if(op==="remove" && key===entry[0]) receiptsAtDelete.push(JSON.parse(w.storage.peek(STORE)).handoffReceipts); };
  await importConfirmed(w,out);
  assert.equal(w.storage.peek(entry[0]),null,"提交receipt后消费对应journal");
  assert.equal(receiptsAtDelete.length,1);
  assert.ok(receiptsAtDelete[0].some(x=>x.id===JSON.parse(entry[1]).session.id && x.minutes===2));
});
test("Round2 F5: same-id cumulative update applies only minute and completion deltas", async () => {
  const w=activeWorld(); otherTakes(w); w.node("dualTake").click();
  await importConfirmed(w,await exported(w));
  const out=await exported(w), rec=out.sessions.find(x=>x.taskId==="mine");
  const updated={...rec,minutes:3,status:"done",ts:rec.ts+60000};
  w.storage.setItem(HANDOFF+"origin."+rec.id,JSON.stringify({ver:1,session:updated}));
  const newer=await exported(w);
  assert.equal(newer.sessions.filter(x=>x.id===rec.id).length,1);
  assert.equal(newer.sessions.find(x=>x.id===rec.id).minutes,3);
  assert.equal(newer.tasks.find(x=>x.id==="mine").focusMin,3);
  assert.equal(newer.tasks.find(x=>x.id==="mine").donePomo,1);
  await importConfirmed(w,newer);
  assert.equal((await exported(w)).tasks.find(x=>x.id==="mine").focusMin,3);
});

test("Round2: import preserves the active segment before clearing its RT", async () => {
  const w=activeWorld(), start=w.run("T.swAt");
  await importConfirmed(w,JSON.parse(backup()));
  assert.equal(w.run("T.status"),"idle");
  const out=await exported(w);
  assert.equal(out.sessions.filter(x=>x.startTs===start && x.minutes===2).length,1,"导入覆盖不是丢弃未提交计时的许可");
});
test("Round2: import refuses destructive switch when active journal cannot be preserved", async () => {
  const w=activeWorld();
  w.storage.fail=(op,key)=>op==="set" && key.startsWith(HANDOFF);
  const before=snapshot(w);
  await importConfirmed(w,JSON.parse(backup()));
  assert.deepEqual(snapshot(w),before);
  assert.ok(w.messages.some(x=>/未保存|失败/.test(x)));
});
for(const fault of ["oversize","malformed","future"]) {
  test("Round2: unsupported receipt archives stay write protected: "+fault, async () => {
    const input=JSON.parse(backup());
    if(fault==="future") input.ver=3;
    else input.handoffReceipts=fault==="oversize" ? Array.from({length:50001},(_,i)=>({id:"limit-"+i,
      minutes:1,type:"focus",startTs:1794961140000,taskId:"imported",done:false})) : [{id:"lost-consumption"}];
    const original=JSON.stringify(input), storage=new MemoryStorage({[STORE]:original}), w=world(storage);
    assert.equal(w.run("save()"),false,"净化异常不能在备份后自动覆盖为空档");
    assert.equal(storage.peek(STORE),original);
    w.node("btnExport").onclick();
    assert.equal(await w.downloads.at(-1).text(),original,"超限或未知凭据必须原样取回");
  });
}
test("Round2: receipt capacity overflow import is explicit and non-destructive", async () => {
  const w=activeWorld(), before=snapshot(w), data=JSON.parse(backup());
  data.handoffReceipts=Array.from({length:50001},(_,i)=>({id:"limit-"+i,minutes:1,type:"focus",
    startTs:1794961140000,taskId:"imported",done:false}));
  await w.beginImport(JSON.stringify(data));
  assert.deepEqual(snapshot(w),before);
  assert.ok(w.messages.some(x=>/容量|上限|超出/.test(x)),"不是把合法JSON误报为文件读不出来");
});
test("Round2: same id with conflicting task is refused, not silently deduplicated", async () => {
  const w=activeWorld(); otherTakes(w); w.node("dualTake").click();
  await importConfirmed(w,await exported(w));
  const entry=(await exported(w)).sessions.find(x=>x.taskId==="mine");
  const key=HANDOFF+"conflict."+entry.id;
  w.storage.setItem(key,JSON.stringify({ver:1,session:{...entry,taskId:"other-task"}}));
  const count=w.downloads.length; w.node("btnExport").onclick();
  assert.equal(w.downloads.length,count);
  assert.ok(w.messages.some(x=>/冲突/.test(x)));
  assert.notEqual(w.storage.peek(key),null);
});
for(const next of ["abort","yield"]) {
  test("Round2: failed complete then legal continued work ends once: "+next, async () => {
    const w=activeWorld();
    w.storage.fail=(op,key)=>op==="set" && (key===STORE || key.startsWith(HANDOFF));
    w.run("complete()"); const prefix=(await exported(w)).sessions.find(x=>x.taskId==="mine");
    w.storage.fail=()=>false; w.node("btnMain").onclick(); w.advance(60);
    if(next==="abort") w.run('abort("continued-after-failure")'); else otherTakes(w);
    const out=await exported(w), task=out.tasks.find(x=>x.id==="mine");
    assert.equal(out.sessions.filter(x=>x.id===prefix.id).length,1);
    assert.equal(out.sessions.find(x=>x.id===prefix.id).minutes,3);
    assert.equal(task.focusMin,3); assert.equal(task.donePomo,0);
  });
}
test("Round2: real reason dialog rejects delayed submission against a new timer", () => {
  const w=activeWorld(); w.run('S.settings.mode="strict"; S.settings.allowPause=false');
  w.node("btnMain").onclick(); otherTakes(w);
  w.node("dualTake").click(); w.node("btnMain").onclick(); w.advance(60);
  const before=w.json("T"); w.node("reasonOk").onclick();
  assert.deepEqual(w.json("T"),before);
});

test("Round2: reset cannot clear an unpreserved failed-settlement draft", async () => {
  const w=activeWorld();
  w.storage.fail=(op,key)=>op==="set" && (key===STORE || key.startsWith(HANDOFF));
  w.run('abort("failed")');
  const rt=w.storage.peek(RT);
  const pending=w.node("btnReset").onclick(); w.questions.at(-1).resolve(false); await pending;
  assert.equal(w.run("T.status"),"pause");
  assert.equal(w.run("T.acc"),120);
  assert.equal(w.storage.peek(RT),rt);
});
test("Round2: receipt readback failure never authorizes journal deletion", async () => {
  const w=activeWorld(); otherTakes(w); w.node("dualTake").click();
  const out=await exported(w), entry=handoffEntries(w.storage)[0];
  let didWrite=false;
  w.storage.observe=(op,key)=>{ if(op==="set" && key===STORE) didWrite=true; };
  w.storage.fail=(op,key)=>didWrite && op==="get" && key===STORE;
  await importConfirmed(w,out);
  assert.equal(w.storage.peek(entry[0]),entry[1]);
  assert.ok(!w.messages.some(x=>x==="已恢复备份"));
});

for(const scenario of ["failed-draft","stale-confirm"]) {
  test("Round2: real type switch respects draft identity: "+scenario, async () => {
    const w=activeWorld();
    const button=w.node("switch-short"); button.dataset.v="short";
    w.node("segKind").children=[button]; w.run("renderSegs()");
    if(scenario==="failed-draft"){
      w.storage.fail=(op,key)=>op==="set" && (key===STORE || key.startsWith(HANDOFF));
      w.run('abort("failed")');
    }
    const pending=button.onclick();
    if(scenario==="stale-confirm"){
      otherTakes(w); w.node("dualTake").click(); w.node("btnMain").onclick(); w.advance(60);
    }
    const before=w.json("T");
    w.questions.at(-1).resolve(true); await pending;
    assert.deepEqual(w.json("T"),before);
  });
}

test("Round2 F3: historical journal never hides a new memory-only completed draft", async () => {
  const w=activeWorld(); otherTakes(w); w.node("dualTake").click();
  w.run('T.kind="focus"; S.activeTaskId="imported"'); w.node("btnMain").onclick(); w.advance(180);
  w.storage.fail=(op,key)=>op==="set" && (key===STORE || key.startsWith(HANDOFF));
  w.run('abort("memory-only")');
  assert.equal(handoffEntries(w.storage).length,1);
  const out=await exported(w);
  assert.equal(out.sessions.filter(x=>x.reason==="memory-only" && x.minutes===3).length,1);
  assert.equal(out.tasks.find(x=>x.id==="imported").focusMin,33);
});
test("Round2 F3: missing latest archive does not resurrect unrelated old S", async () => {
  const w=activeWorld();
  w.run('S.tasks.push({id:"old-only",title:"Unrelated stale task"}); save()');
  w.storage.fail=(op,key)=>op==="set" && (key===STORE || key.startsWith(HANDOFF));
  w.run('abort("only-pending")');
  w.storage.removeItem(STORE);
  const out=await exported(w);
  assert.ok(!out.tasks.some(x=>x.id==="old-only"));
  assert.equal(out.sessions.filter(x=>x.reason==="only-pending" && x.minutes===2).length,1);
});
test("Round2 F4: unreadable primary receipts also block stale RT settlement", () => {
  const w=activeWorld(), rt=w.storage.peek(RT), input=JSON.parse(backup()); input.handoffReceipts=[{id:"unknown"}];
  w.storage.data.set(STORE,JSON.stringify(input)); w.storage.removeItem(OWNER);
  const reopened=world(w.storage);
  assert.equal(reopened.run("T.status"),"idle");
  reopened.fire("pagehide"); assert.equal(w.storage.peek(RT),rt);
});

test("Round2: RT keeps an explicitly unassigned segment unassigned after task selection", async () => {
  const w=world(); w.node("btnMain").onclick(); w.advance(120);
  w.run('S.tasks=[{id:"later",title:"Selected later",focusMin:0,donePomo:0}]; S.activeTaskId="later"; save(); saveRT()');
  w.storage.removeItem(OWNER);
  const reopened=world(w.storage); reopened.run('abort("restored-unassigned")');
  const out=await exported(reopened);
  assert.equal(out.sessions.length,1);
  assert.equal(out.sessions[0].taskId,undefined);
  assert.equal(out.tasks[0].focusMin,0);
});

const HANDOFF = STORE + ".handoff.";
test("Handoff: runtime write guard works before the owner event arrives", () => {
  const w = runningWorld(), rt = w.storage.peek(RT);
  w.storage.setItem(OWNER, "other-writer:" + Date.now());
  assert.equal(w.run("dualReadOnly"), false, "模拟事件尚未送达，不能借已设置的只读标志保护");
  w.run('T.status="idle"; saveRT()');
  assert.equal(w.storage.peek(RT), rt, "非记录者不能删除运行快照");
  w.run('T.status="run"; T.acc=500; saveRT()');
  assert.equal(w.storage.peek(RT), rt, "非记录者不能覆盖运行快照");
});
function handoffEntries(storage) {
  return [...storage.data].filter(([key]) => key.startsWith(HANDOFF));
}
function loseOwnership(w, archive = backup()) {
  w.storage.setItem(STORE, archive);
  const owner = "other-writer:" + Date.now();
  w.storage.setItem(OWNER, owner);
  w.fire("storage", {key: OWNER, newValue: owner});
  return archive;
}

test("Handoff: real owner event preserves the completed segment without overwriting the new writer", async () => {
  const w = runningWorld();
  const otherArchive = loseOwnership(w);
  const entries = handoffEntries(w.storage);
  assert.equal(entries.length, 1, "让位记录须安全保全，不能只留在将被替换的 S 中");
  const journal = JSON.parse(entries[0][1]);
  assert.equal(journal.ver, 1);
  assert.equal(journal.session.minutes, 2);
  assert.equal(journal.session.status, "abort");
  assert.equal(journal.session.reason, "另一个窗口接管了记录");
  assert.equal(w.storage.peek(STORE), otherArchive);
  assert.ok(!w.messages.some(s => s.startsWith("已记录")), "暂存不是已入账");
  assert.ok(w.messages.some(s => /暂存/.test(s) && /导出/.test(s)));
  w.fire("storage", {key: OWNER, newValue: w.storage.peek(OWNER)});
  w.fire("pagehide");
  assert.equal(handoffEntries(w.storage).length, 1, "重复事件/关窗不能重复生成或删除记录");
  assert.equal(w.storage.peek(STORE), otherArchive);
  w.storage.removeItem(OWNER); // 新记录者也已关窗；新窗口有写权，不能靠只读 stopAll 掩盖重复恢复。
  const reopened = world(w.storage);
  assert.ok(reopened.messages.some(s => /待交接/.test(s) && /导出/.test(s)), "重开须给出可发现的恢复入口提示");
  reopened.node("btnExport").onclick();
  const restored = JSON.parse(await reopened.downloads[0].text());
  assert.equal(restored.sessions.length, 2, "导出必须含新记录者的数据和待交接记录");
  assert.ok(restored.sessions.some(s => s.id === journal.session.id && s.minutes === 2));
  assert.ok(restored.sessions.some(s => s.id === "record"));
  assert.equal(reopened.run("T.status"), "idle", "已保全的旧 RT 不应再次恢复成待计时段");
});

test("Handoff: failed journal preserves running state and supports immediate recovery export", async () => {
  const w = runningWorld(), oldRt = w.storage.peek(RT);
  w.storage.fail = (op, key) => op === "set" && key.startsWith(HANDOFF);
  const otherArchive = loseOwnership(w);
  assert.equal(handoffEntries(w.storage).length, 0);
  assert.notEqual(w.run("T.status"), "idle", "无法落盘时不能销毁唯一内存计时状态");
  assert.equal(w.storage.peek(RT), oldRt);
  assert.equal(w.storage.peek(STORE), otherArchive);
  assert.ok(!w.messages.some(s => s.startsWith("已记录")));
  assert.ok(w.messages.some(s => /失败|未能/.test(s) && /导出/.test(s)));
  w.fire("storage", {key: STORE, newValue: otherArchive});
  w.node("btnExport").onclick();
  const restored = JSON.parse(await w.downloads[0].text());
  assert.ok(restored.sessions.some(s => s.minutes === 2 && s.reason === "另一个窗口接管了记录"));
  w.fire("pagehide");
  assert.equal(w.storage.peek(RT), oldRt);
});

test("Handoff: losing writer never changes the new writer runtime", () => {
  const w = runningWorld();
  const otherRt = JSON.stringify({kind:"short",total:300,acc:45,status:"run",tm:"count",
    ts:Date.now(),sw:Date.now()-45000,day:"2026-11-18",bk:[],pos:Date.now()});
  w.storage.setItem(RT, otherRt);
  loseOwnership(w);
  w.fire("pagehide");
  assert.equal(w.storage.peek(RT), otherRt);
});

test("Handoff: recovery export deduplicates by real session id and leaves journals intact", async () => {
  const w = runningWorld();
  loseOwnership(w);
  const entries = handoffEntries(w.storage);
  assert.equal(entries.length, 1);
  const rec = JSON.parse(entries[0][1]).session;
  const archive = JSON.parse(backup());
  archive.sessions.push(rec);
  w.storage.setItem(STORE, JSON.stringify(archive));
  const reopened = world(w.storage);
  reopened.node("btnExport").onclick();
  const exported = JSON.parse(await reopened.downloads[0].text());
  assert.equal(exported.sessions.filter(s => s.id === rec.id).length, 1);
  assert.equal(handoffEntries(w.storage).length, 1, "下载动作不等于成功导入/确认，不能删唯一保全件");
});
