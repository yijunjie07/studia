const params = new URLSearchParams(location.search);
const MOCK = params.has("mock");
// Which build of the page this is: the server writes it into the script URL (none in ?mock).
const BUILD = new URL(import.meta.url).searchParams.get("v");
// A mailed password link: /#/reset/<token>. The token stays in the fragment, so it never reaches a server log.
const RESET = location.hash.match(/^#\/reset\/([\w-]+)$/)?.[1] || "";
const TOKEN = params.get("t") || sessionStorage.getItem("studia-token") || "";
if (params.get("t")) {
  sessionStorage.setItem("studia-token", TOKEN);
  history.replaceState(null, "", location.pathname + (MOCK ? "?mock" : "") + location.hash);
}

const $ = (selector, root = document) => root.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const store = {
  get(name, fallback) { try { return JSON.parse(localStorage.getItem(name)) ?? fallback; } catch { return fallback; } },
  set(name, value) { try { localStorage.setItem(name, JSON.stringify(value)); } catch { /* private mode */ } },
};

/* ---------------------------------------------------------------- icons */

const COLOR = { mooc: "var(--mooc)", zhs: "var(--zhs)" };
function ring(percent, color = "var(--indigo)", size = 16) {
  const p = Math.max(0, Math.min(100, Number(percent) || 0));
  const r = size / 2 - 1.5, c = 2 * Math.PI * r, mid = size / 2;
  return `<svg class="ring" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}"><circle cx="${mid}" cy="${mid}" r="${r}" fill="none" stroke="rgb(var(--ink) / .12)" stroke-width="2.2"/>
    <circle cx="${mid}" cy="${mid}" r="${r}" fill="none" stroke="${color}" stroke-width="2.2" stroke-linecap="round" stroke-dasharray="${(c * p) / 100} ${c}" transform="rotate(-90 ${mid} ${mid})"/></svg>`;
}
// Each course gets one ink, picked from its id, so its cover, cells and sidebar ring match.
const INKS = ["#2d5fa6", "#2f7d5b", "#b4542d", "#7a4fb0", "#1f8a8a", "#a8792a"];
const inkOf = (c) => INKS[[...String(c.id)].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) >>> 0, 7) % INKS.length];
const svg = (body, size = 16) =>
  `<svg width="${size}" height="${size}" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
const ICON = {
  find: svg('<circle cx="7" cy="7" r="5"/><path d="m11 11 3.5 3.5"/>', 15),
  plusCircle: svg('<circle cx="8" cy="8" r="6.2"/><path d="M8 5.3v5.4M5.3 8h5.4"/>', 15),
  // Four study cells: the course tab on phones.
  cells: svg('<rect x="2.5" y="2.5" width="4.5" height="4.5" rx="1.2"/><rect x="9" y="2.5" width="4.5" height="4.5" rx="1.2"/><rect x="2.5" y="9" width="4.5" height="4.5" rx="1.2"/><rect x="9" y="9" width="4.5" height="4.5" rx="1.2"/>', 18),
  pulse: svg('<path d="M2 8h2.4l1.7-4.5 3.4 9 1.7-4.5H14"/>', 15),
  // A toothed cog: the old ring-of-rays gear read as a sun next to the theme toggle.
  gear: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>',
  moon: svg('<path d="M13 9.5A5.5 5.5 0 0 1 6.5 3a5.5 5.5 0 1 0 6.5 6.5z"/>', 15),
  sun: svg('<circle cx="8" cy="8" r="3"/><path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1"/>', 15),
  logout: svg('<path d="M6.5 2.5h-3v11h3M10 5l3 3-3 3M13 8H6"/>', 15),
  key: svg('<circle cx="5.5" cy="10.5" r="3"/><path d="m7.6 8.4 5.9-5.9M11 5l1.5 1.5"/>', 15),
  shield: svg('<path d="M8 1.8 13 3.6v4c0 3.2-2.1 5.4-5 6.6-2.9-1.2-5-3.4-5-6.6v-4z"/>', 15),
  login: svg('<path d="M9.5 2.5h3v11h-3M3 8h7M7.5 5l3 3-3 3"/>', 15),
  back: svg('<path d="M10 3 5 8l5 5"/>', 18),
  chev: svg('<path d="m6 3.5 4.5 4.5L6 12.5"/>', 14),
  spark: svg('<path d="M8 1.8 9.4 6.6 14.2 8 9.4 9.4 8 14.2 6.6 9.4 1.8 8 6.6 6.6z"/>', 15),
  updown: svg('<path d="m5 6 3-3 3 3M5 10l3 3 3-3"/>', 12),
  grip: '<svg width="10" height="14" viewBox="0 0 10 14" fill="currentColor"><circle cx="3" cy="3" r="1.2"/><circle cx="7" cy="3" r="1.2"/><circle cx="3" cy="7" r="1.2"/><circle cx="7" cy="7" r="1.2"/><circle cx="3" cy="11" r="1.2"/><circle cx="7" cy="11" r="1.2"/></svg>',
  dots: '<svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><circle cx="3" cy="7" r="1.3"/><circle cx="7" cy="7" r="1.3"/><circle cx="11" cy="7" r="1.3"/></svg>',
  play: '<svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor"><path d="M3 1.6v8.8L10.4 6z"/></svg>',
  repeat: svg('<path d="M13 8a5 5 0 1 1-1.5-3.6M13 2.5v3h-3"/>', 14),
  pen: svg('<path d="M10.5 2.5 13.5 5.5 6 13H3v-3z"/>', 14),
  chat: svg('<path d="M2.5 3.5h11v7.5H7l-3 2.5V11H2.5z"/>', 14),
  tick: '<svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m2.5 6.3 2.4 2.4L9.6 3.8"/></svg>',
  done: '<svg width="16" height="16" viewBox="0 0 16 16"><circle cx="8" cy="8" r="7" fill="var(--celadon)"/><path d="m4.8 8.2 2 2 4.2-4.4" fill="none" stroke="var(--card)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  error: '<svg width="16" height="16" viewBox="0 0 16 16"><circle cx="8" cy="8" r="7" fill="var(--seal)"/><path d="m5.5 5.5 5 5m0-5-5 5" stroke="var(--card)" stroke-width="1.8" stroke-linecap="round"/></svg>',
  waiting: '<svg width="16" height="16" viewBox="0 0 16 16"><circle cx="8" cy="8" r="7" fill="var(--gamboge)"/><path d="M8 4.5V8l2.2 1.6" fill="none" stroke="var(--card)" stroke-width="1.7" stroke-linecap="round"/></svg>',
  stopped: '<svg width="16" height="16" viewBox="0 0 16 16"><circle cx="8" cy="8" r="7" fill="none" stroke="var(--text-4)" stroke-width="1.5"/><rect x="5.6" y="5.6" width="4.8" height="4.8" rx="1" fill="var(--text-4)"/></svg>',
  running: '<svg width="16" height="16" viewBox="0 0 16 16"><circle cx="8" cy="8" r="7" fill="var(--indigo-soft)"/><circle cx="8" cy="8" r="3" fill="var(--indigo)"/></svg>',
};
ICON.queued = ICON.running;
ICON.paused = ICON.stopped;

/* ------------------------------------------------------------------ api */

// local: one person, token from the terminal URL; hosted: cookie session + CSRF header.
// register: who may sign up ({open, invite, email}), from /api/mode; null before it answers or on a local server.
const session = { mode: "local", user: null, csrf: "", register: null };
let mockModule = null;
async function api(path, { method = "GET", body } = {}) {
  if (MOCK) {
    mockModule = mockModule || (await import("./mock.js"));
    return mockModule.request(path, method, body);
  }
  const headers = body ? { "Content-Type": "application/json" } : {};
  if (session.mode === "hosted") { if (method !== "GET") headers["X-Studia-CSRF"] = session.csrf; }
  else headers["X-Studia-Token"] = TOKEN;
  const response = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined, credentials: "same-origin" });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401 && !path.startsWith("/api/auth/") && path !== "/api/mode") {
    if (session.mode === "hosted") loadMe().then((ok) => { if (!ok) showAuth(); else refreshState(); });
    else if (path !== "/api/state") refreshState();
  }
  if (!response.ok) throw new Error(data.error || `请求失败（${response.status}）`);
  return data;
}

const state = {
  platforms: [], courses: {}, papers: {}, paperErrors: {}, units: {}, selected: {}, earned: {}, qaDraft: {}, qaPosts: {}, qaRoom: {}, qaPeers: null, qaOpen: new Set(),
  jobs: [], runs: {}, focus: null, jobLimit: 4, zhsParallel: false, history: [], view: "", loginToken: { cancelled: true }, returnTo: "", lastDone: null,
  current: store.get("studia-platform", ""), meOpen: false, adminTab: "people", logFilter: "all", accountEdit: null, passwordSent: null, adminEdit: null, pausedOpen: new Set(),
  adminLists: {}, adminOpen: null,
};
function freshRun() { return { detail: "", overall: null, sub: null, lines: [], unit: null }; }
const runOf = (id) => (state.runs[id] = state.runs[id] || freshRun());
// Mirrors the server's rules (web/server.py _check_conflicts) so buttons say why before you click.
const GROUP = { study: "learn", review: "learn", answer: "answer", qa: "qa", ask: "ask" };
const jobType = (j) => j.kind || { 自动学习: "study", 每日复习: "review", "AI 答题": "answer", 问答区答题: "qa", 问答区提问: "ask" }[j.title];
// Only learning jobs fill a course's unit grid.
const learns = (j) => GROUP[jobType(j)] === "learn";
// A job in the list that is not running: waiting for a slot, or paused by an administrator.
const WAIT_WORD = { queued: "排队中", paused: "已暂停" };
function blocker(pid, cid, type) {
  for (const o of state.jobs) {
    if (GROUP[jobType(o)] !== GROUP[type] || o.platform !== pid) continue;
    if (o.course === cid) return o.state === "running" ? `${LIVE_WORD[o.title] || "进行中"}…` : `${WAIT_WORD[o.state]}（${o.title}）`;
    if (pid === "zhs" && GROUP[type] === "learn" && !state.zhsParallel) return `等「${o.course_name}」的${o.title}结束`;
  }
  return "";
}
// The job the player and focus view follow: the one picked, else one on the open course, else the newest.
function focusedJob() {
  const [, pid, cid] = state.view.match(/^#\/course\/([^/]+)\/([^/]+)/) || [];
  return state.jobs.find((j) => j.id === state.focus)
    || state.jobs.find((j) => j.platform === pid && j.course === decodeURIComponent(cid || ""))
    || [...state.jobs].reverse().find((j) => j.state === "running") || state.jobs.find((j) => !isPaused(j)) || state.jobs[0] || null;
}
const platformOf = (pid) => state.platforms.find((p) => p.id === pid);
const key = (pid, cid) => `${pid}:${cid}`;
const selectedOf = (k) => (state.selected[k] = state.selected[k] || new Set());
const courseOf = (pid, cid) => (state.courses[pid] || []).find((c) => c.id === cid);
const go = (hash) => { if (location.hash !== hash) location.hash = hash; else route(); };

let toastTimer = 0;
function toast(text) {
  const el = $(".toast");
  el.textContent = text;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
}
// Risky buttons (data-confirm="…") take two presses: the first turns them red with the
// confirm label for 3 seconds; only the second reaches the button's own handler.
const armTimers = new WeakMap();
function disarm(el) {
  clearTimeout(armTimers.get(el));
  el.classList.remove("armed");
  if (el.dataset.was != null) { el.innerHTML = el.dataset.was; delete el.dataset.was; }
}
document.addEventListener("click", (event) => {
  const el = event.target.closest("[data-confirm]");
  if (!el || el.disabled) return;
  if (el.classList.contains("armed")) { disarm(el); return; }
  event.stopImmediatePropagation();
  event.preventDefault();
  document.querySelectorAll(".armed[data-confirm]").forEach(disarm);
  el.dataset.was = el.innerHTML;
  el.textContent = el.dataset.confirm;
  el.classList.add("armed");
  armTimers.set(el, setTimeout(() => disarm(el), 3000));
}, true);

function ago(seconds) {
  const diff = Date.now() / 1000 - seconds;
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  const d = new Date(seconds * 1000), time = d.toTimeString().slice(0, 5);
  const days = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(d).setHours(0, 0, 0, 0)) / 86400000);
  return days === 0 ? `今天 ${time}` : days === 1 ? `昨天 ${time}` : `${d.getMonth() + 1}月${d.getDate()}日`;
}
const pad = (n) => String(n).padStart(2, "0");
function clock(sec) {
  sec = Math.max(0, Math.floor(sec));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return h ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}
function duration(sec) {
  sec = Math.max(0, Math.round(sec));
  if (sec < 60) return `${sec} 秒`;
  if (sec < 3600) return `${Math.floor(sec / 60)} 分 ${pad(sec % 60)} 秒`;
  return `${Math.floor(sec / 3600)} 小时 ${pad(Math.floor((sec % 3600) / 60))} 分`;
}
const elapsed = (job) => (job.ended || Date.now() / 1000) - job.started;

function toggleTheme() {
  const night = document.documentElement.dataset.theme !== "night";
  const apply = () => {
    document.documentElement.dataset.theme = night ? "night" : "";
    renderSidebar();
  };
  // A view transition cross-fades the whole page at once, instead of each colour flipping on its own beat.
  if (document.startViewTransition && !STILL.matches) document.startViewTransition(apply); else apply();
  store.set("studia-theme", night ? "night" : "day");
  toast(night ? "夜读模式" : "日间模式");
}

/* ---------------------------------------------------------------- sidebar */

const INITIAL = { mooc: "M", zhs: "智" };
// The sign-in centre's ticket lapsed: studying carries on, the Q&A board waits for a fresh scan.
const rescanLink = (p) => `#/login/${p.id}/again`;
// It lasts eight hours from the scan (rescan_at); the last stretch is the time to finish today's Q&A or scan early.
const QA_SOON = 90 * 60;
const qaLeft = (p) => (p.rescan_at ? p.rescan_at - Date.now() / 1000 : null);
const qaSoon = (p) => !p.rescan && qaLeft(p) !== null && qaLeft(p) < QA_SOON;
const rescannable = (p) => p.rescan || Boolean(p.rescan_at);
function hoursLeft(sec) {
  const min = Math.max(1, Math.ceil(sec / 60));
  return min < 60 ? `${min} 分钟` : `${Math.floor(min / 60)} 小时${min % 60 ? ` ${min % 60} 分` : ""}`;
}
function currentPlatform() {
  return platformOf(state.current) || state.platforms.find((p) => p.logged_in) || state.platforms[state.platforms.length - 1];
}
function platformStatus(p) {
  if (!p.logged_in) return p.lapsed ? "登录已过期" : "未登录";
  if (p.rescan) return "问答区要重新扫码";
  if (qaSoon(p)) return `问答区还能用 ${hoursLeft(qaLeft(p))}`;
  return state.courses[p.id] ? `已登录 · ${state.courses[p.id].length} 门课程` : "已登录";
}
const PHONE = matchMedia("(max-width: 860px)");
// Studia's history keeps only the last few jobs, and courses learnt on the platform never enter it: go by the platform's progress.
const learnt = (c) => Number(c.progress) >= 100 ? "已学完" : Number(c.progress) > 0 ? "还没学完" : "还没学过";
function homeOf(p) {
  if (!p.logged_in) return `#/login/${p.id}`;
  // Phones open the course list (the 课程 tab); the desktop sidebar already lists them, so open the first course.
  const first = (state.courses[p.id] || [])[0];
  return PHONE.matches || !first ? "#/home" : `#/course/${p.id}/${first.id}`;
}
function switchPlatform(pid, navigate = true) {
  state.current = pid;
  store.set("studia-platform", pid);
  if (navigate) go(homeOf(platformOf(pid)));
  else renderSidebar();
}

function jobPill() {
  if (state.jobs.length) return state.jobs.every((j) => j.state !== "running")
    ? `<span class="live">${state.jobs.some((j) => j.state === "queued") ? "排队中" : "已暂停"}</span>` : `<span class="live">${state.jobs.filter((j) => j.state !== "paused").length} 个进行中</span>`;
  // Only what is running gets a count; past runs are not a number to watch.
  return state.history[0]?.state === "waiting" ? '<span class="live waiting">等你操作</span>' : "";
}

function renderSidebar() {
  const p = currentPlatform();
  if (!p) return;
  const view = state.view;
  const item = (hash, icon, label, extra = "", cls = "") =>
    `<button class="nav_item ${cls}" data-go="${hash}" aria-current="${view === hash || view.startsWith(`${hash}/`)}">${icon}<span class="label">${esc(label)}</span>${extra}</button>`;
  const platforms = `<div class="plat_seg" role="tablist" style="--n:${state.platforms.length};--i:${Math.max(0, state.platforms.indexOf(p))}">${state.platforms.map((x, i) =>
    `<button role="tab" aria-selected="${x.id === p.id}" data-switch="${x.id}" title="${esc(platformStatus(x))} · ⌘${i + 1}">${esc(x.short)}${
      state.jobs.some((j) => j.platform === x.id) ? '<i class="busy"></i>' : ""}</button>`).join("")}</div>`;
  patch($(".switcher_wrap"), platforms);

  const courses = [];
  if (!p.logged_in) courses.push(item(`#/login/${p.id}`, ICON.login, `${p.lapsed ? "重新" : ""}登录${/^[A-Za-z]/.test(p.short) ? " " : ""}${p.short}`));
  else if (!state.courses[p.id]) courses.push(`<div class="nav_item quiet loading"><span class="label">正在读取课程…</span></div>`);
  else courses.push(...state.courses[p.id].map((c) => {
    const busy = state.jobs.some((j) => j.platform === p.id && j.course === c.id);
    return item(`#/course/${p.id}/${c.id}`, ring(c.progress, inkOf(c)), c.name,
      busy ? '<span class="live"></span>' : c.progress == null ? "" : `<span class="count">${esc(c.progress)}%</span>`);
  }));
  if (!courses.length) courses.push(`<div class="nav_item quiet"><span class="label">没有课程</span></div>`);
  patch($(".nav"), item("#/jobs", ICON.pulse, "任务", jobPill())

    + `<div class="nav_label">${p.logged_in ? "课程" : esc(p.short)}</div>` + courses.join(""));

  // One account button at the bottom; settings, the admin console, theme and sign-out live in its menu.
  const me = session.user;
  const night = document.documentElement.dataset.theme === "night";
  const name = me ? me.username : "本机";
  const initial = me ? me.username.slice(0, 1).toUpperCase() : "本";
  const role = me ? (me.role === "admin" ? "管理员" : "成员") : "只有这台电脑能访问";
  const admin = me?.role === "admin";
  const under = (...prefixes) => prefixes.some((x) => view.startsWith(x));
  patch($(".side_foot"), `<button class="me" data-me aria-haspopup="menu" aria-expanded="${state.meOpen}" aria-current="${under("#/me", "#/settings", "#/admin")}">
      <span class="avatar">${esc(initial)}</span><span class="who"><b>${esc(name)}</b><small>${role}</small></span>
      <span class="chev">${ICON.updown}</span></button>
    ${state.meOpen ? `<div class="menu me_menu" role="menu">
      <button class="menu_row" role="menuitem" data-go="#/settings">${ICON.gear}<span class="grow">设置</span><span class="kbd">⌘,</span></button>
      ${admin ? `<button class="menu_row" role="menuitem" data-go="#/admin">${ICON.shield}<span class="grow">管理后台</span></button>` : ""}
      <div class="psep"></div>
      <button class="menu_row" role="menuitem" data-toggle-theme>${night ? ICON.sun : ICON.moon}<span class="grow">${night ? "日间模式" : "夜读模式"}</span><span class="kbd">⌘J</span></button>
      ${me ? `<div class="psep"></div><button class="menu_row danger" role="menuitem" data-signout>${ICON.logout}<span class="grow">退出 Studia</span></button>` : ""}
    </div>` : ""}`);

  // Phones: three tabs at the bottom; a page one level down (a course, a settings tab) gets a back
  // button in the top bar instead of the logo. The platform switch only sits on the overview.
  const back = under("#/course") ? ["#/home", "课程"] : under("#/settings", "#/admin") ? ["#/me", "我的"] : null;
  patch($(".mbar"), back ? `<button class="mback" data-go="${back[0]}">${ICON.back}<span>${back[1]}</span></button><span class="grow"></span>`
    : `<img class="mark" src="icon.svg" alt=""><b>Studia</b><span class="grow"></span>${under("#/home", "#/login") ? platforms : ""}`);
  patch($(".mtabs"), `
    <button class="mtab" data-go="#/home" aria-current="${under("#/home", "#/course", "#/login")}">${ICON.cells}<span>课程</span></button>
    <button class="mtab" data-go="#/jobs" aria-current="${view === "#/jobs"}">${ICON.pulse}<span>任务</span>${state.jobs.length ? `<b class="badge">${state.jobs.length}</b>` : ""}</button>
    <button class="mtab" data-go="#/me" aria-current="${under("#/me", "#/settings", "#/admin")}"><span class="avatar">${esc(initial)}</span><span>我的</span></button>`);
}


/* ---------------------------------------------------------------- page helpers */

const page = $(".page");
const scroller = $(".scroll");
// Live progress repaints several times a second. Patch the existing DOM instead of
// replacing it, so buttons, running animations and a finger mid-tap survive the update.
/* ---------------------------------------------------------------- motion
   Only transform and opacity move, so animations stay on the compositor while a job streams progress.
   Web Animations (el.animate) rather than classes: nothing to clean up, and a later repaint cannot restart them. */
const STILL = matchMedia("(prefers-reduced-motion: reduce)");
const EASE = "cubic-bezier(.2, .8, .2, 1)";
const moves = (el, frames, options) => (STILL.matches || !el.animate ? null : el.animate(frames, { duration: 260, easing: EASE, ...options }));
let born = [];  // keyed rows a patch inserted, to fade in once it is done

function patch(target, html, motion = true) {
  const fresh = document.createElement("template");
  fresh.innerHTML = html;
  const before = motion && !STILL.matches ? keyedRects(target) : null;
  born = [];
  patchChildren(target, fresh.content);
  if (!before) return;
  // A row that moved (a job leaving the queue for a slot, a list re-sorted) slides from where it was;
  // one that is new fades in. A few at most, so a page of fresh rows does not ripple for long.
  for (const el of target.querySelectorAll("[data-key]")) {
    const was = before.get(el.dataset.key);
    if (!was || born.includes(el)) continue;
    const now = el.getBoundingClientRect(), dx = was.left - now.left, dy = was.top - now.top;
    if (Math.abs(dx) + Math.abs(dy) > 1) moves(el, [{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "none" }], { duration: 320 });
  }
  born.slice(0, 24).forEach((el, i) => moves(el, [{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }],
    { duration: 280, delay: Math.min(i, 8) * 22, fill: "backwards" }));
}
// Where each keyed row sits now. A key seen twice is ambiguous and left out.
function keyedRects(root) {
  const els = root.querySelectorAll("[data-key]");
  if (!els.length || els.length > 240) return null;
  const rects = new Map(), twice = new Set();
  for (const el of els) {
    const k = el.dataset.key;
    if (rects.has(k)) twice.add(k); else rects.set(k, el.getBoundingClientRect());
  }
  twice.forEach((k) => rects.delete(k));
  return rects;
}
// Rows with a data-key (a job, a paper, a course, a person) are matched by it, not by position: a row inserted above
// them no longer rewrites every row below, and the one that moved keeps its element (and its animation).
function patchChildren(from, to) {
  const next = [...to.childNodes], keyed = new Map();
  for (const n of from.childNodes) if (n.nodeType === 1 && n.dataset.key) keyed.set(n.dataset.key, n);
  next.forEach((node, i) => {
    const at = from.childNodes[i] || null, k = node.nodeType === 1 ? node.dataset.key : undefined;
    if (k) {
      const have = keyed.get(k);
      keyed.delete(k);
      if (!have || have.nodeName !== node.nodeName) { from.insertBefore(node, at); born.push(node); return; }
      if (have !== at) from.insertBefore(have, at);
      patchElement(have, node);
    } else if (!at || (at.nodeType === 1 && at.dataset.key)) from.insertBefore(node, at);
    else if (at.nodeType !== node.nodeType || at.nodeName !== node.nodeName) from.replaceChild(node, at);
    else if (node.nodeType === 1) patchElement(at, node);
    else if (at.nodeValue !== node.nodeValue) at.nodeValue = node.nodeValue;
  });
  while (from.childNodes.length > next.length) from.lastChild.remove();
}
function patchElement(have, node) {
  // An armed button keeps its confirm label through live repaints.
  if (have.classList.contains("armed") && have.dataset.confirm === node.getAttribute("data-confirm")) return;
  // A reused element may now mean something else; views rebind their handlers after each paint.
  have.onclick = null;
  for (const { name } of [...have.attributes]) if (!node.hasAttribute(name)) have.removeAttribute(name);
  for (const { name, value } of [...node.attributes]) if (have.getAttribute(name) !== value) have.setAttribute(name, value);
  patchChildren(have, node);
}

// The page's tab bar: which bar (its links), which tab, and where its marker sits.
function tabBar() {
  const bar = page.querySelector(":scope > .tabs"), on = bar?.querySelector('.tab[aria-selected="true"]');
  if (!on) return null;
  const tabs = [...bar.querySelectorAll(".tab")];
  return { bar, on, links: tabs.map((t) => t.dataset.go).join(" "), index: tabs.indexOf(on), rect: on.getBoundingClientRect() };
}
// Everything below the tab bar (or the whole page without one): what changes when the tab or the data does.
const pageBody = (bar) => (bar ? [...page.children].slice([...page.children].indexOf(bar.bar) + 1) : [...page.children]);
// Blocks rise into place one after another. fill "backwards": a block waiting for its turn is not shown early.
const rise = (els, lift = 10) => els.slice(0, 10).forEach((el, i) =>
  moves(el, [{ opacity: 0, transform: `translateY(${lift}px)` }, { opacity: 1, transform: "none" }], { duration: 320, delay: Math.min(i, 5) * 30, fill: "backwards" }));

// Navigating fades the new page in, its blocks one after another. Another tab of the same bar keeps the title and
// tabs still: the marker glides over and the content slides in from that tab's side. Data arriving in place of a
// 正在读取… placeholder fades in. Background repaints patch quietly.
let quiet = false;
function setPage(html) {
  const was = STILL.matches ? null : tabBar(), loading = Boolean(page.querySelector(".loading"));
  if (quiet) patch(page, html, !loading);
  else page.innerHTML = html;
  const now = was && tabBar(), sameBar = now && now.links === was.links;
  if (sameBar && now.index !== was.index) {
    const side = now.index > was.index ? 1 : -1;
    const marker = now.bar.classList.contains("seg") ? "::before" : "::after";
    try {
      moves(now.on, [{ transform: `translateX(${was.rect.left - now.rect.left}px) scaleX(${was.rect.width / now.rect.width})` }, { transform: "none" }],
        { pseudoElement: marker, duration: 300 });
    } catch { /* no pseudo-element animations: the marker just moves */ }
    for (const el of pageBody(now)) moves(el, [{ opacity: 0, transform: `translateX(${side * 18}px)` }, { opacity: 1, transform: "none" }]);
  } else if (!quiet) rise([...page.children]);
  else if (loading && !page.querySelector(".loading")) rise(pageBody(tabBar()), 6);
  // Tab bars scroll sideways on narrow phones: keep the current tab in sight.
  const nav = page.querySelector(".tabs"), on = nav?.querySelector('[aria-selected="true"]');
  if (on && (on.offsetLeft < nav.scrollLeft || on.offsetLeft + on.offsetWidth > nav.scrollLeft + nav.clientWidth)) nav.scrollLeft = on.offsetLeft - 16;
}

const LABEL = { study: "自动学习", review: "每日复习", answer: "AI 答题", qa: "问答区答题", ask: "问答区提问" };
const TYPE_OF = Object.fromEntries(Object.entries(LABEL).map(([k, v]) => [v, k]));
const STATE_WORD = { done: "完成", error: "失败", waiting: "等你操作", stopped: "已停止", running: "进行中", queued: "排队中", paused: "已暂停" };

/* ---------------------------------------------------------------- units (course grid) */

const UNIT_WORD = { done: "已完成", queued: "待学", running: "正在学习", failed: "失败", skipped: "跳过", waiting: "等你操作" };
const KIND_WORD = { video: "视频", doc: "文档", ppt: "课件", audio: "音频", img: "图片", pdf: "文档", word: "文档", excel: "表格" };
function tally(chapters) {
  const t = { all: 0, done: 0, running: 0, queued: 0, failed: 0, skipped: 0, waiting: 0 };
  for (const ch of chapters) for (const u of ch.units) { t.all += 1; t[u.state] = (t[u.state] || 0) + 1; }
  return t;
}
const unitsOf = (k) => state.units[k]?.chapters || null;
function findUnit(k, id) {
  for (const ch of unitsOf(k) || []) for (const u of ch.units) if (u.id === id) return u;
  return null;
}

function gridHtml(k) {
  const data = state.units[k];
  if (!data) return `<div class="grid loading">正在读取学习单元…</div>`;
  if (data.error) return `<div class="grid loading">${esc(data.error)} · <button class="link" data-units-retry="${esc(k)}">重试</button></div>`;
  if (!data.chapters.length) return `<div class="grid loading">这门课没有可学习的单元</div>`;
  const t = tally(data.chapters);
  const legend = [["done", "完成"], ["running", "进行中"], ["queued", "待学"], ["waiting", "等你操作"], ["failed", "失败"], ["skipped", "跳过"]]
    .filter(([s]) => t[s] || s === "done" || s === "queued");
  const fresh = state.stamped && Date.now() - state.stamped.at < 900 ? state.stamped.id : null;
  // The chapter being studied; between two units nothing runs, so fall back to the next unfinished one.
  let current = data.chapters.findIndex((ch) => ch.units.some((u) => u.state === "running"));
  if (current < 0) current = data.chapters.findIndex((ch) => ch.units.some((u) => u.state === "queued" || u.state === "waiting"));
  return `<div class="grid" data-k="${esc(k)}"><div class="chapters">${data.chapters.map((ch, ci) => `<div class="chapter ${ci === current ? "current" : ""}"><span class="name" title="${esc(ch.name)}">${esc(ch.name)}</span>
      <span class="cells">${ch.units.map((u, ui) => `<i class="cell ${u.state}${u.id === fresh ? " stamp" : ""}" data-u="${ci}:${ui}"></i>`).join("")}</span>
      <span class="tally">${ch.units.filter((u) => u.state === "done").length}/${ch.units.length}</span></div>`).join("")}</div>
    <div class="legend">${legend.map(([s, label]) => `<span><i class="cell ${s}"></i>${label}</span>`).join("")}</div></div>`;
}

// The platform only knows done and not done; the unit a live job is on comes from the job itself
// (its last "running" event, which the server keeps for pages opened mid-run).
function markLive(k) {
  for (const job of state.jobs) {
    if (key(job.platform, job.course) !== k) continue;
    const u = findUnit(k, runOf(job.id).unit?.key);
    if (u && u.state !== "done") u.state = "running";
  }
}

const loadingUnits = new Set();
async function loadUnits(pid, cid, force = false) {
  const k = key(pid, cid);
  if (loadingUnits.has(k) || (state.units[k] && !force)) return;
  loadingUnits.add(k);
  try { state.units[k] = { chapters: (await api(`/api/platforms/${pid}/units?course=${encodeURIComponent(cid)}${force ? "&fresh=1" : ""}`)).chapters }; markLive(k); }
  catch (error) { if (!state.units[k]?.chapters) state.units[k] = { error: error.message }; }
  finally { loadingUnits.delete(k); }
  repaint();
}

const TOUCH = matchMedia("(hover: none)").matches;
const tip = $(".tip");
// Touch screens fire mouseover on tap but never mouseout; hide the tip once the page moves.
document.addEventListener("scroll", () => tip.classList.remove("show"), true);
document.addEventListener("mouseover", (event) => {
  const cell = event.target.closest(".cell[data-u]");
  const grid = cell?.closest("[data-k]");
  const [ci, ui] = (cell?.dataset.u || "").split(":").map(Number);
  const u = grid && unitsOf(grid.dataset.k)?.[ci]?.units[ui];
  if (!u) { tip.classList.remove("show"); return; }
  const kind = KIND_WORD[u.kind] || u.kind;
  tip.innerHTML = `<b>${esc(u.name)}</b><br><span class="mono">${esc([kind, u.minutes ? `${u.minutes} 分钟` : "", UNIT_WORD[u.state]].filter(Boolean).join(" · "))}</span>`;
  const r = cell.getBoundingClientRect();
  tip.style.left = `${Math.max(8, Math.min(innerWidth - 270, r.left - 8))}px`;
  tip.style.top = `${r.bottom + 8}px`;
  tip.classList.add("show");
});

/* ---------------------------------------------------------------- views */

const ADMIN_TABS = [["people", "用户"], ["invites", "邀请码"], ["site", "站点"], ["logs", "日志"]];
/* 用户 and 邀请码 grow with the site, so each is a list that pages, filters and searches. What a list is
   showing stays while the console is open; the page size is remembered in the browser. */
const PAGE_SIZES = [10, 20, 50, 100];
let adminData = null;  // the lists last read, so searching, filtering and paging redraw without asking again
// facets: the options picked per filter; open: the filter whose menu shows, with facetQ typed in its box.
const adminList = (kind) => (state.adminLists[kind] ||= { q: "", page: 1, facets: {}, open: null, facetQ: "" });
const pageSize = (kind) => { const n = store.get("studia-admin-size", {})[kind]; return PAGE_SIZES.includes(n) ? n : PAGE_SIZES[0]; };
function pageOf(kind, rows) {
  const list = adminList(kind), size = pageSize(kind);
  list.page = Math.min(Math.max(1, list.page), Math.max(1, Math.ceil(rows.length / size)));
  return rows.slice((list.page - 1) * size, list.page * size);
}
/* Filters as in a data table: each is a ⊕ button whose menu ticks any of its options (any of them matches; every
   filter must). facets: [key, label, [[value, label, test(row)]]]. Each option counts the rows it would leave,
   given the search and the other filters. */
function facetFilter(kind, rows, facets) {
  const chosen = adminList(kind).facets;
  const pass = (row, skip) => facets.every(([key, , options]) => key === skip || !chosen[key]?.length
    || options.some(([value, , test]) => chosen[key].includes(value) && test(row)));
  const counts = Object.fromEntries(facets.map(([key, , options]) =>
    [key, Object.fromEntries(options.map(([value, , test]) => [value, rows.filter((row) => pass(row, key) && test(row)).length]))]));
  return { rows: rows.filter((row) => pass(row)), counts };
}
function listTools(kind, placeholder, facets, counts, extra = "") {
  const list = adminList(kind);
  const buttons = facets.map(([key, label, options]) => {
    const picked = options.filter(([value]) => list.facets[key]?.includes(value)), open = list.open === key;
    const q = open ? list.facetQ.trim().toLowerCase() : "";
    const shown = options.filter(([, name]) => !q || name.toLowerCase().includes(q));
    return `<div class="facet"><button class="facet_btn" data-facet="${key}" aria-haspopup="listbox" aria-expanded="${open}">${ICON.plusCircle}${label}${picked.length
        ? `<span class="facet_sep"></span>${picked.length > 2 ? `<span class="pill">已选 ${picked.length} 项</span>` : picked.map(([, name]) => `<span class="pill">${name}</span>`).join("")}` : ""}</button>
      ${open ? `<div class="facet_pop"><label class="facet_find">${ICON.find}<input data-facet-search value="${esc(list.facetQ)}" placeholder="${label}" autocomplete="off" spellcheck="false"></label>
        <div class="facet_opts" role="listbox" aria-multiselectable="true" aria-label="${label}">${shown.map(([value, name]) =>
          `<button class="facet_opt" role="option" data-facet-opt="${value}" aria-selected="${picked.some(([v]) => v === value)}"><span class="facet_tick"></span><span class="grow">${name}</span><span class="n">${counts[key][value]}</span></button>`).join("")
          || '<div class="facet_none">没有匹配的选项</div>'}</div>
        ${picked.length ? '<button class="facet_clear" data-facet-clear>清除筛选</button>' : ""}</div>` : ""}</div>`;
  }).join("");
  const any = facets.some(([key]) => list.facets[key]?.length);
  return `<div class="list_tools"><input class="row_input" type="search" data-list-search value="${esc(list.q)}" placeholder="${placeholder}" autocomplete="off" autocapitalize="off" spellcheck="false">
    ${buttons}${any ? '<button class="facet_reset" data-facet-reset>重置<span aria-hidden="true">×</span></button>' : ""}${extra}</div>`;
}
// A filter menu closes on a click outside it, or on Esc.
function closeFacet(event) {
  const list = state.view === "#/admin" ? state.adminLists[state.adminTab] : null;
  if (!list?.open || (event.type === "click" ? event.target.closest?.(".facet") : event.key !== "Escape")) return;
  const key = list.open;
  list.open = null;
  VIEWS.admin("local", state.adminTab);
  if (event.type === "keydown") $(`[data-facet="${key}"]`, page)?.focus();
}
document.addEventListener("click", closeFacet, true);  // before the click's own handler repaints the page
document.addEventListener("keydown", closeFacet);
// Lists that fit the smallest page need no bar.
function pagerHtml(kind, total, unit) {
  if (total <= PAGE_SIZES[0]) return "";
  const list = adminList(kind), size = pageSize(kind), pages = Math.ceil(total / size), from = (list.page - 1) * size;
  return `<div class="pager"><span>${from + 1}–${Math.min(from + size, total)}，共 ${total} ${unit}</span>
    <label class="pager_size">每页<select data-list-size>${PAGE_SIZES.map((n) => `<option value="${n}" ${n === size ? "selected" : ""}>${n}</option>`).join("")}</select></label>
    <span class="pager_nav"><button class="btn small" data-list-page="${list.page - 1}" ${list.page <= 1 ? "disabled" : ""}>上一页</button>
      <span class="mono">${list.page} / ${pages}</span>
      <button class="btn small" data-list-page="${list.page + 1}" ${list.page >= pages ? "disabled" : ""}>下一页</button></span></div>`;
}
const SETTINGS_TABS = [["account", "账号"], ["models", "AI 模型"], ["study", "偏好"]];
function pageHead(title, sub, base, tabs, active) {
  return `<h1 class="title">${title}</h1>${sub ? `<p class="sub">${sub}</p>` : ""}
    <div class="tabs" role="tablist">${tabs.map(([k, label]) => `<button class="tab" role="tab" aria-selected="${k === active}" data-go="${base}/${k}">${label}</button>`).join("")}</div>`;
}
// Phones arrive from the list on 我的, which already names each tab: show just that one, titled by it.
const settingsHead = (tab, sub) => PHONE.matches
  ? `<h1 class="title">${SETTINGS_TABS.find(([k]) => k === tab)[1]}</h1><p class="sub">${sub}</p>`
  : pageHead("设置", sub, "#/settings", SETTINGS_TABS, tab);
/* A person's jobs as a board: one slot per job they may run at once, the queue below in the order it will run,
   the paused ones folded away. A queued job is dragged by its grip, within the queue to reorder it or onto a slot
   to take that job's place (which then waits at the front of the queue). The person and an administrator see
   the same board; owner is "" for one's own jobs, else the user id the admin routes take. */
const isPaused = (j) => j.state === "paused" || j.hold === "pause";
const inSlot = (j) => j.state === "running" && !j.hold;
const byOrder = (a, b) => a.order - b.order;
function boardParts(jobs, limit) {
  const live = jobs.filter((j) => !isPaused(j)).sort(byOrder), running = live.filter(inSlot), rest = live.filter((j) => !inSlot(j));
  // A queued job just moved into a slot (its place in line is within the limit) starts in a moment: show it there.
  const incoming = rest.filter((j) => j.state === "queued" && j.order < limit).slice(0, Math.max(0, limit - running.length));
  return { slots: [...running, ...incoming].sort(byOrder), queue: rest.filter((j) => !incoming.includes(j)),
           incoming: incoming.length, paused: jobs.filter(isPaused).sort(byOrder) };
}
const DOTS = (j) => `<button class="dots" data-job-menu="${esc(j.id)}" aria-label="更多操作">${ICON.dots}</button>`;
function slotCard(j, owner) {
  const run = owner ? j.progress || {} : runOf(j.id), starting = j.state !== "running", { pct, label } = progressOf(run);
  return `<div class="slot" data-key="${esc(j.id)}" data-slot="${esc(j.id)}" ${starting || !learns(j) ? "data-locked" : ""} style="--c:${inkOf({ id: j.course })}">
    <span class="slot_head"><b>${esc(j.course_name)}</b>${DOTS(j)}</span>
    <small>${esc(j.title)} · ${esc(starting ? "准备中…" : nowText(j, run))}</small>
    <span class="slot_foot"><span class="bar"><i style="width:${pct ?? 0}%"></i></span><span class="mono">${esc(label || duration(Date.now() / 1000 - (j.running_since || j.started)))}</span></span>
  </div>`;
}
const queueRow = (j, i) => `<div class="qrow" data-key="${esc(j.id)}" data-drag="${esc(j.id)}">
    ${j.hold ? '<span class="grip off"></span>' : `<span class="grip" data-grip aria-hidden="true">${ICON.grip}</span>`}<span class="place mono">${i + 1}</span>
    <span class="t1">${esc(j.course_name)}<small>${esc(j.title)}${j.hold ? " · 正在让位" : ""}</small></span>${DOTS(j)}</div>`;
const pausedRow = (j) => `<div class="qrow" data-key="${esc(j.id)}"><span class="grip off"></span><span class="place"></span>
    <span class="t1">${esc(j.course_name)}<small>${esc(j.title)}${j.hold ? " · 正在暂停" : ""}</small></span>
    ${j.hold ? "" : `<button class="btn small" data-job-act="continue" data-id="${esc(j.id)}">继续</button>`}${DOTS(j)}</div>`;
function board(jobs, limit, owner = "") {
  const { slots, queue, incoming, paused } = boardParts(jobs, limit), open = state.pausedOpen.has(owner);
  // Empty slots only matter as drop targets for the queue; otherwise 名额 n/limit in the heading says it.
  const empty = queue.length ? Math.max(0, limit - slots.length) : 0;
  return `<div class="board" data-board data-owner="${esc(owner)}" data-incoming="${incoming}">
    <div class="slots">${slots.map((j) => slotCard(j, owner)).join("")}${'<div class="slot vacant" data-slot=""><span>空位</span></div>'.repeat(empty)}</div>
    ${queue.length ? `<div class="board_head">排队<small>拖动排序，拖进格子即替换</small></div><div class="runs queue">${queue.map(queueRow).join("")}</div>` : ""}
    ${paused.length ? `<button class="board_head fold" data-paused-fold="${esc(owner)}" aria-expanded="${open}">已暂停 ${paused.length}<span class="chev_r" aria-hidden="true"></span></button>
      ${open ? `<div class="runs">${paused.map(pausedRow).join("")}</div>` : ""}` : ""}
  </div>`;
}
const boardCount = (jobs, limit) => { const n = boardParts(jobs, limit).slots.filter((j) => j.state === "running").length; return `名额 ${n}/${limit}`; };
const jobsOf = (owner) => owner ? state.sitePeople?.find((u) => u.id === owner)?.jobs || [] : state.jobs;
function jobAct(owner, id, action, body = {}) {
  const url = owner ? `/api/admin/users/${owner}/jobs/${id}/${action}` : action === "stop" ? "/api/jobs/stop" : `/api/jobs/${action}`;
  return api(url, { method: "POST", body: owner ? body : { id, ...body } })
    .then((r) => { const text = r?.message || { stop: "正在停止…", pause: "已暂停", continue: "已排到最后" }[action]; if (text) toast(text); if (owner) loadSiteJobs(); },
          (e) => toast(e.message));
}

// The ⋯ menu of one job, floating above the page so live repaints leave it alone.
const jobMenu = document.createElement("div");
jobMenu.className = "menu job_menu";
jobMenu.setAttribute("role", "menu");
jobMenu.hidden = true;
document.body.appendChild(jobMenu);
function openJobMenu(button) {
  const owner = button.closest("[data-board]").dataset.owner, id = button.dataset.jobMenu;
  const j = jobsOf(owner).find((x) => x.id === id);
  if (!j) return;
  const row = (act, label, extra = "") => `<button class="menu_row${act === "stop" ? " danger" : ""}" role="menuitem" data-job-act="${act}" data-id="${esc(id)}" data-owner="${esc(owner)}" ${extra}><span class="grow">${label}</span></button>`;
  jobMenu.innerHTML = [
    owner ? "" : `<button class="menu_row" role="menuitem" data-open="${esc(id)}"><span class="grow">查看</span></button>`,
    j.state === "queued" && !j.hold ? row("move", "移到最前", 'data-to="0"') : "",
    !j.hold && (j.state === "queued" || (inSlot(j) && learns(j))) ? row("pause", "暂停") : "",
    j.state === "paused" ? row("continue", "继续") : "",
    row("stop", "停止", 'data-confirm="确认停止"'),
  ].join("");
  jobMenu.getAnimations().filter((a) => a.id === "out").forEach((a) => a.cancel());  // reopened while fading out
  jobMenu.hidden = false;
  const at = button.getBoundingClientRect(), h = jobMenu.offsetHeight, w = jobMenu.offsetWidth;
  jobMenu.style.left = `${Math.max(8, Math.min(at.right - w, innerWidth - w - 8))}px`;
  jobMenu.style.top = `${at.bottom + 4 + h > innerHeight - 8 ? at.top - h - 4 : at.bottom + 4}px`;
}
const closeJobMenu = () => {
  if (jobMenu.hidden || jobMenu.getAnimations().some((a) => a.id === "out")) return;
  const out = moves(jobMenu, [{ opacity: 1 }, { opacity: 0, transform: "translateY(4px) scale(.98)" }], { duration: 140, id: "out" });
  if (out) out.onfinish = () => { jobMenu.hidden = true; out.cancel(); };
  else jobMenu.hidden = true;
};

// Dragging a queued job by its grip (mouse or finger): a ghost follows the pointer; the slot under it, or the gap
// between queue rows, is marked; dropping sends the move. Repaints wait until the drop (see repaint).
let drag = null;
document.addEventListener("pointerdown", (event) => {
  const grip = event.target.closest("[data-grip]");
  if (!grip || event.button > 0) return;
  event.preventDefault();
  closeJobMenu();
  const row = grip.closest("[data-drag]"), at = row.getBoundingClientRect(), ghost = row.cloneNode(true);
  ghost.classList.add("ghost");
  // A card-sized ghost, held where it was grabbed: a full-width row would cover the slots it is dropped on.
  Object.assign(ghost.style, { width: `${Math.min(at.width, 320)}px`, left: `${at.left}px`, top: `${at.top}px` });
  document.body.appendChild(ghost);
  row.classList.add("dragging");
  document.body.classList.add("dragging");
  drag = { row, ghost, box: row.closest("[data-board]"), x: event.clientX - at.left, y: event.clientY - at.top, target: null };
});
document.addEventListener("pointermove", (event) => {
  if (!drag) return;
  drag.ghost.style.left = `${event.clientX - Math.min(drag.x, 300)}px`;
  drag.ghost.style.top = `${event.clientY - drag.y}px`;
  // Near the top or bottom edge the page scrolls, so a long queue can be dragged end to end on a phone.
  if (event.clientY < 72 || event.clientY > innerHeight - 72) scroller.scrollBy(0, event.clientY < 72 ? -14 : 14);
  drag.box.querySelectorAll(".drop, .drop_before, .drop_after").forEach((el) => el.classList.remove("drop", "drop_before", "drop_after"));
  drag.target = null;
  const slot = document.elementFromPoint(event.clientX, event.clientY)?.closest("[data-slot]");
  if (slot && drag.box.contains(slot) && !slot.hasAttribute("data-locked")) {
    slot.classList.add("drop");
    drag.target = slot.dataset.slot ? { swap: slot.dataset.slot } : { to: 0 };
    return;
  }
  const list = drag.row.parentElement.getBoundingClientRect();
  if (event.clientY < list.top - 24 || event.clientY > list.bottom + 24) return;
  const rows = [...drag.row.parentElement.querySelectorAll("[data-drag]")].filter((r) => r !== drag.row);
  const before = rows.findIndex((r) => { const b = r.getBoundingClientRect(); return event.clientY < b.top + b.height / 2; });
  if (before >= 0) rows[before].classList.add("drop_before");
  else rows[rows.length - 1]?.classList.add("drop_after");
  // The server's queue also counts the jobs shown starting in a slot, which come first.
  drag.target = { to: (before < 0 ? rows.length : before) + Number(drag.box.dataset.incoming) };
});
function endDrag() {
  if (!drag) return;
  const { row, ghost, box, target } = drag;
  drag = null;
  ghost.remove();
  row.classList.remove("dragging");
  document.body.classList.remove("dragging");
  box.querySelectorAll(".drop, .drop_before, .drop_after").forEach((el) => el.classList.remove("drop", "drop_before", "drop_after"));
  if (target) jobAct(box.dataset.owner, row.dataset.drag, "move", target);
  repaint();
}
document.addEventListener("pointerup", endDrag);
document.addEventListener("pointercancel", endDrag);
const siteCount = () => (state.sitePeople || []).reduce((sum, u) => sum + u.jobs.length, 0);
let siteTimer = 0;
async function loadSiteJobs() {
  clearTimeout(siteTimer);
  const here = () => location.hash === "#/jobs/all";
  // Refresh every 5 seconds while the list is open; paused while hidden or a stop button is armed.
  if (!document.hidden && !document.querySelector(".armed")) {
    try { state.sitePeople = (await api("/api/admin/jobs")).people; } catch (error) { toast(error.message); state.sitePeople = state.sitePeople || []; }
    if (here()) repaint();
  }
  if (here()) siteTimer = setTimeout(loadSiteJobs, 5000);
}
const VIEWS = {
  async admin(refresh = false, tab = state.adminTab) {
    tab = ADMIN_TABS.some(([k]) => k === tab) ? tab : "people";
    state.adminTab = tab;
    const head = pageHead("管理后台", "", "#/admin", ADMIN_TABS, tab);
    // Show the tab at once; its lists fill it in when they arrive.
    if (!refresh) {
      for (const list of Object.values(state.adminLists)) list.open = null;  // arriving: no filter menu left open
      // Switching tabs inside the console swaps the content in place; arriving from elsewhere animates.
      quiet = state.view === "#/admin" && Boolean(page.querySelector('[data-go^="#/admin/"]'));
      setPage(`${head}<div class="empty loading">正在读取…</div>`);
      quiet = false;
    }
    const need = { people: ["users"], invites: ["invites", "users"], site: ["settings", "memory"], logs: [] }[tab];
    let data;
    // "local": the same lists drawn again (a search, a filter, another page), without reading them again.
    if (refresh === "local" && adminData?.tab === tab) data = adminData.data;
    else {
      try { data = Object.fromEntries(await Promise.all(need.map(async (x) => [x, await api(`/api/admin/${x}`)]))); }
      catch (error) { if (!refresh) setPage(`${head}<div class="empty">${esc(error.message)}</div>`); return; }
      adminData = { tab, data };
    }
    if (state.view !== "#/admin" || state.adminTab !== tab) return;
    const users = data.users?.users || [];
    const modelForm = $("[data-default-model]", page);
    const modelDraft = modelForm ? Object.fromEntries(new FormData(modelForm)) : null;
    const smtpForm = $("[data-smtp]", page);
    const smtpDraft = smtpForm ? Object.fromEntries(new FormData(smtpForm)) : null;
    let body = "";
    if (tab === "people") {
      const list = adminList("people"), q = list.q.trim().toLowerCase();
      const edit = (u, kind) => state.adminEdit?.uid === u.id && state.adminEdit.kind === kind;
      // Busy people first, then whoever was around last; stopped accounts at the end.
      const rank = (u) => (u.disabled ? 2 : u.jobs?.length ? 0 : 1);
      const seen = (u) => u.last_login || u.created || 0;
      const running = (u) => u.jobs?.some((j) => j.state === "running"), queued = (u) => !running(u) && u.jobs?.some((j) => j.state === "queued");
      const FACETS = [
        ["status", "状态", [["on", "已启用", (u) => !u.disabled], ["off", "已停用", (u) => u.disabled]]],
        ["role", "角色", [["admin", "管理员", (u) => u.role === "admin"], ["user", "普通用户", (u) => u.role !== "admin"]]],
        ["jobs", "任务", [["running", "学习中", running], ["queued", "排队中", queued],
          ["paused", "已暂停", (u) => u.jobs?.length > 0 && !running(u) && !queued(u)], ["none", "没有任务", (u) => !u.jobs?.length]]],
      ];
      const found = users.filter((u) => !q || `${u.username} ${u.email || ""}`.toLowerCase().includes(q))
        .sort((a, b) => rank(a) - rank(b) || seen(b) - seen(a));
      const { rows, counts } = facetFilter("people", found, FACETS);
      const userRow = (u) => `<div class="model user_row ${state.adminOpen === u.id || state.adminEdit?.uid === u.id ? "open" : ""}" data-key="${esc(u.id)}" data-user-row="${esc(u.id)}">
            <span class="avatar big">${esc(u.username.slice(0, 1).toUpperCase())}</span>
            <span class="m1"><b>${esc(u.username)}</b>${u.role === "admin" ? '<span class="pill blue">管理员</span>' : ""}${u.disabled ? '<span class="pill red">已停用</span>' : ""}${u.max_jobs ? `<span class="pill">同时 ${u.max_jobs} 个</span>` : ""}
            <small class="sans">${u.jobs?.some((j) => j.state === "running") ? "学习中" : u.jobs?.some((j) => j.state === "queued") ? "排队中" : u.jobs?.length ? "已暂停" : u.last_login ? `上次在线 ${ago(u.last_login)}` : "还没登录过"}${u.email ? ` · ${esc(u.email)}` : ""}</small></span>
            <button class="btn small row_more" data-user-more="${esc(u.id)}" aria-expanded="${state.adminOpen === u.id || state.adminEdit?.uid === u.id}">管理</button>
            <span class="row_btns">${u.jobs?.length ? `<button class="btn small danger" data-stop-user="${u.id}" data-confirm="确认全部停止">停止全部任务</button>` : ""}
              <button class="btn small" data-row-edit="limit" data-uid="${u.id}" aria-pressed="${edit(u, "limit")}">任务上限</button>
              <button class="btn small" data-row-edit="password" data-uid="${u.id}" aria-pressed="${edit(u, "password")}">重置密码</button>
              ${u.id === session.user.id ? "" : u.disabled ? `<button class="btn small" data-enable="${u.id}">启用</button>` : `<button class="btn small danger" data-disable="${u.id}" data-confirm="确认停用">停用</button>`}</span>
            ${edit(u, "limit") ? `<form class="row_form" data-row-form="limit" data-uid="${u.id}">
                <label>同时最多<input class="inline_num" type="number" min="1" max="20" name="value" value="${esc(u.max_jobs || "")}" placeholder="${esc(u.job_limit)}">个任务</label>
                <small>留空用站点默认</small><span class="grow"></span>
                <button type="button" class="btn small" data-row-cancel>取消</button><button class="btn small primary">保存</button></form>`
            : edit(u, "password") ? `<form class="row_form" data-row-form="password" data-uid="${u.id}" novalidate>
                <input class="row_input" type="password" name="value" minlength="8" required autocomplete="new-password" placeholder="新密码，至少 8 位"><span class="grow"></span>
                <button type="button" class="btn small" data-row-cancel>取消</button><button class="btn small primary">重置密码</button></form>` : ""}</div>`;
      body = `${listTools("people", "搜索用户名或邮箱", FACETS, counts)}
        <div class="models">${pageOf("people", rows).map(userRow).join("")
          || `<div class="model plain"><span class="m1"><small class="sans">${users.length ? "没有符合条件的用户" : "还没有用户"}</small></span></div>`}</div>
        ${pagerHtml("people", rows.length, "人")}`;
    } else if (tab === "invites") {
      const list = adminList("invites"), q = list.q.trim().toLowerCase();
      const invites = data.invites.invites;
      const nameOf = (uid) => users.find((u) => u.id === uid)?.username || "—";
      const inviteState = { open: ["blue", "可用"], used: ["", "已使用"], expired: ["", "已过期"] };
      // A code is found with or without its dashes, or by the person who signed up with it.
      const found = invites.filter((i) => !q || `${i.code} ${i.code.replace(/-/g, "")} ${i.used_by ? nameOf(i.used_by) : ""}`.toLowerCase().includes(q));
      const FACETS = [
        ["state", "状态", [["open", "可用"], ["used", "已使用"], ["expired", "已过期"]].map(([k, name]) => [k, name, (i) => i.state === k])],
      ];
      const { rows, counts } = facetFilter("invites", found, FACETS);
      const inviteRow = (i) => `<div class="model plain invite_row" data-key="${esc(i.code)}"><span class="m1"><b><code>${esc(i.code)}</code></b><span class="pill ${inviteState[i.state][0]}">${inviteState[i.state][1]}</span>
            <small class="sans">${i.used_by ? `${esc(nameOf(i.used_by))} 已注册` : `创建于 ${ago(i.created)} · ${new Date(i.expires * 1000).toLocaleDateString()} 过期`}</small></span>
          <span class="row_btns">${i.state === "open" ? `<button class="btn small" data-copy="${esc(i.code)}">复制</button><button class="btn small danger" data-revoke="${esc(i.code)}" data-confirm="确认作废">作废</button>` : ""}</span></div>`;
      const reg = data.invites.registration, idle = !reg ? "" : !reg.open ? "注册已关闭，邀请码用不上" : reg.invite ? "" : "注册不需要邀请码";
      body = `${listTools("invites", "搜索邀请码或注册的用户", FACETS, counts, '<button class="btn small primary" data-invite>生成邀请码</button>')}
        ${idle ? `<p class="list_note">${idle}<button class="link" data-go="#/admin/site">去设置</button></p>` : ""}
        <div class="models">${pageOf("invites", rows).map(inviteRow).join("")
          || `<div class="model plain"><span class="m1"><small class="sans">${invites.length ? "没有符合条件的邀请码" : "还没有邀请码"}</small></span></div>`}</div>
        ${pagerHtml("invites", rows.length, "个")}`;
    } else if (tab === "site") {
      const settings = data.settings;
      const current = settings.default_model;
      const model = modelDraft || current || {};
      const kept = (name, fallback) => $(`[name="${name}"]`, page)?.value || fallback;
      state.zhsParallel = settings.zhs_parallel_study;
      const fast = settings.answer_pace === "fast";
      const editing = state.adminEdit?.kind === "default-model";
      const smtp = settings.smtp, mailEditing = state.adminEdit?.kind === "smtp", sm = smtpDraft || smtp || { security: "ssl" };
      const SECURITY = { ssl: "SSL", starttls: "STARTTLS", none: "不加密" };
      const smtpRow = smtp
        ? `<div class="model plain"><span class="m1"><b>${esc(smtp.sender_name || "Studia")} &lt;${esc(smtp.sender)}&gt;</b>
            <small class="sans">${esc(smtp.host)}:${smtp.port} · ${SECURITY[smtp.security]}${smtp.username ? ` · ${esc(smtp.username)}` : ""}</small></span>
          <span class="row_btns"><button class="btn small" data-smtp-edit aria-pressed="${mailEditing}">编辑</button>
            <button class="btn small danger" data-smtp-clear data-confirm="确认清除">清除</button></span></div>`
        : `<div class="model plain"><span class="m1"><small class="sans">还没有配置</small></span>
          <span class="row_btns"><button class="btn small primary" data-smtp-edit aria-pressed="${mailEditing}">配置</button></span></div>`;
      const smtpEdit = mailEditing ? `<form class="form_card" data-smtp>
          <div class="field"><label>SMTP 服务器</label><input name="host" value="${esc(sm.host)}" placeholder="例如 smtp.qq.com" autocapitalize="off" required></div>
          <div class="field"><label>加密方式</label><select name="security">${Object.entries(SECURITY).map(([k, v]) =>
            `<option value="${k}" ${sm.security === k ? "selected" : ""}>${v}</option>`).join("")}</select></div>
          <div class="field"><label>端口</label><input name="port" type="number" min="1" max="65535" value="${esc(sm.port || "")}" placeholder="留空用默认：SSL 465，STARTTLS 587，不加密 25"></div>
          <div class="field"><label>账号</label><input name="username" value="${esc(sm.username)}" autocomplete="off" autocapitalize="off" placeholder="通常是完整的邮箱地址"></div>
          <div class="field"><label>密码</label><input name="password" type="password" autocomplete="new-password" placeholder="${smtp?.password_hint ? `留空不修改（${esc(smtp.password_hint)}）` : "邮箱的 SMTP 授权码，不是登录密码"}"></div>
          <div class="field"><label>发件地址</label><input name="sender" value="${esc(sm.sender)}" autocapitalize="off" placeholder="留空用账号"></div>
          <div class="field"><label>发件人名称</label><input name="sender_name" value="${esc(sm.sender_name)}" placeholder="Studia"></div>
          <div class="form_btns"><span class="grow"></span>
            <button type="button" class="btn" data-smtp-cancel>取消</button><button class="btn primary">测试并保存</button></div>
        </form>` : "";
      const [cls, label] = HEALTH[current?.health] || ["", "未测试"];
      const hostOf = (url) => { try { return new URL(url).host; } catch { return url || ""; } };
      const modelRow = current
        ? `<div class="model ai on"><span class="m1"><b>${esc(current.provider_name || "默认供应商")}</b><span class="pill">${current.source === "site" ? "站点配置" : "内置"}</span>
            <small>${esc(current.model)} · ${esc(hostOf(current.base_url))} · ${esc(current.key_hint)}</small></span>
          <span class="health ${cls}" data-default-health title="${esc(current.health_message || (current.checked_at ? `测试于 ${current.checked_at.replace("T", " ")}` : ""))}">${label}</span>
          <span class="row_btns"><button class="btn small" data-default-test>测试</button>
            <button class="btn small" data-default-edit aria-pressed="${editing}">编辑</button>
            ${current.source === "site" && settings.builtin_available ? '<button class="btn small danger" data-default-reset data-confirm="确认恢复">恢复内置</button>' : ""}</span></div>`
        : `<div class="model plain"><span class="m1"><small class="sans">还没有默认模型</small></span>
          <span class="row_btns"><button class="btn small primary" data-default-edit aria-pressed="${editing}">配置</button></span></div>`;
      const modelEdit = editing ? `<form class="form_card" data-default-model>
          <div class="field"><label>名称</label><input name="provider_name" value="${esc(model.provider_name)}" placeholder="默认供应商"></div>
          <div class="field"><label>服务地址</label><input name="base_url" value="${esc(model.base_url)}" placeholder="https://api.example.com/v1" required></div>
          <div class="field"><label>模型</label><input name="model" value="${esc(model.model)}" placeholder="例如 deepseek-chat" required></div>
          <div class="field"><label>API Key</label><input name="api_key" type="password" autocomplete="off"></div>
          <div class="form_btns"><span class="grow"></span>
            <button type="button" class="btn" data-default-cancel>取消</button><button class="btn primary">测试并保存</button></div>
        </form>` : "";
      // Who may sign up: closed, the two rules below have nothing to apply to and stay hidden.
      const reg = settings.registration;
      const choice = (key, value, label, attrs = "") =>
        `<button class="btn small" data-registration="${key}" data-value="${value ? 1 : 0}" aria-pressed="${reg[key] === value}" ${attrs}>${label}</button>`;
      const registrationRows = `<div class="model plain stepper_row"><span class="m1"><b>允许注册</b></span>
          <span class="row_btns">${choice("open", false, "关闭")}${choice("open", true, "开放")}</span></div>
        ${reg.open ? `<div class="model plain stepper_row"><span class="m1"><b>邀请码</b>${reg.invite || reg.email ? "" : '<small class="sans">任何人都能注册</small>'}</span>
          <span class="row_btns">${choice("invite", true, "需要")}${choice("invite", false, "不需要", reg.invite ? 'data-confirm="确认不需要"' : "")}</span></div>
        <div class="model plain stepper_row"><span class="m1"><b>验证邮箱</b>${smtp ? "" : '<small class="sans">先配置邮件服务</small>'}</span>
          <span class="row_btns">${choice("email", true, "需要", smtp ? "" : "disabled")}${choice("email", false, "不需要")}</span></div>` : ""}`;
      body = `<div class="section"><h3>全站默认 AI 模型</h3></div>
        <div class="models">${modelRow}${modelEdit}</div>
        <div class="section"><h3>邮件服务</h3></div>
        <div class="models">${smtpRow}${smtpEdit}</div>
        <div class="section"><h3>注册</h3></div>
        <div class="models">${registrationRows}</div>
        <div class="section"><h3>任务上限</h3></div>
        <div class="models"><div class="model plain"><span class="m1"><b>默认每人同时 <input class="inline_num" type="number" min="1" max="20" name="max_jobs" value="${esc(kept("max_jobs", settings.max_jobs))}"> 个任务</b></span>
          <span class="row_btns"><button class="btn small primary" data-save-limit>保存</button></span></div></div>
        <div class="section"><h3>智慧树</h3></div>
        <div class="models"><div class="model plain"><span class="m1"><b>多并发学习</b><span class="pill ${settings.zhs_parallel_study ? "wait" : ""}">${settings.zhs_parallel_study ? "已开启" : "已关闭"}</span></span>
          <span class="row_btns"><button class="btn small ${settings.zhs_parallel_study ? "" : "danger"}" data-zhs-parallel="${settings.zhs_parallel_study ? "off" : "on"}" ${settings.zhs_parallel_study ? "" : 'data-confirm="确认开启"'}>${settings.zhs_parallel_study ? "关闭" : "开启"}</button></span></div>
          <div class="model plain stepper_row"><span class="m1"><b>答题节奏 · ${fast ? "快速" : "稳妥"}</b><small class="sans">${fast
            ? "每步间隔 0.1–0.5 秒"
            : "每步间隔 0.5–2 秒"}</small></span>
            <span class="row_btns"><button class="btn small" data-site-pace="steady" aria-pressed="${!fast}">稳妥</button><button class="btn small" data-site-pace="fast" aria-pressed="${fast}" ${fast ? "" : 'data-confirm="确认用快速"'}>快速</button></span></div></div>
        <div class="section"><h3>答案记忆</h3></div>
        <div class="models"><div class="model plain"><span class="m1"><b>智慧树 ${data.memory.questions} 题</b><small class="sans">${data.memory.confirmed} 题已确认正确</small></span></div>
          <div class="model plain"><span class="m1"><b>MOOC ${data.memory.mooc.questions} 题</b><small class="sans">平台公布的标准答案</small></span></div></div>`;
    } else {
      const pad2 = (n) => String(n).padStart(2, "0");
      const local = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
      const today = new Date(); today.setHours(0, 0, 0, 0);
      body = `<div class="section"><h3>日志导出</h3><span class="aside">最长 92 天</span></div>
        <div class="models"><div class="model plain log_export"><span class="log_range">
            <label>从 <input type="datetime-local" name="log_from" value="${esc(local(today))}"></label>
            <label>到 <input type="datetime-local" name="log_to" value="${esc(local(new Date()))}"></label>
            <label>类型 <select name="log_kind"><option value="app">运行日志</option><option value="audit">操作记录</option></select></label></span>
          <span class="row_btns"><button class="btn small primary" data-export-logs>导出</button></span></div></div>`;
    }
    quiet = true;
    setPage(head + body);
    quiet = false;
    const act = async (path, payload, message) => {
      try { await api(path, { method: "POST", body: payload || {} }); toast(message); VIEWS.admin(true, tab); } catch (e) { toast(e.message); }
    };
    const on = (selector, handler) => page.querySelectorAll(selector).forEach((el) => (el.onclick = () => handler(el)));
    const defaultForm = $("[data-default-model]", page);
    if (defaultForm) {
      const saved = data.settings.default_model, { base_url, api_key } = defaultForm.elements;
      const sameHost = () => { try { return saved && new URL(base_url.value.trim()).hostname === new URL(saved.base_url).hostname; } catch { return false; } };
      // A blank key keeps the saved one only on the same host; the server refuses otherwise, say so up front.
      const keyRule = () => {
        api_key.required = !sameHost();
        api_key.placeholder = !saved ? "必填" : sameHost() ? `留空不修改（${saved.key_hint}）` : "换了服务地址，请重新填写";
      };
      api_key.value = modelDraft?.api_key || "";
      base_url.oninput = keyRule;
      keyRule();
      if (!modelDraft) defaultForm.querySelector("input").focus();
      defaultForm.onsubmit = async (event) => {
        event.preventDefault();
        const button = $("button.primary", defaultForm);
        button.disabled = true; button.textContent = "测试中…";
        try {
          await api("/api/admin/settings", { method: "POST", body: { default_model: Object.fromEntries(new FormData(defaultForm)) } });
          state.adminEdit = null;
          defaultForm.removeAttribute("data-default-model");  // the refresh must not keep it as a draft
          state.settings = null;
          toast("已测试并保存");
          if (state.view === "#/admin" && state.adminTab === tab) await VIEWS.admin(true, tab);
        } catch (e) { toast(e.message); button.disabled = false; button.textContent = "测试并保存"; }
      };
    }
    const mailForm = $("[data-smtp]", page);
    if (mailForm) {
      if (smtpDraft) mailForm.elements.password.value = smtpDraft.password;
      else mailForm.querySelector("input").focus();
      mailForm.onsubmit = async (event) => {
        event.preventDefault();
        const button = $("button.primary", mailForm);
        button.disabled = true; button.textContent = "测试中…";
        try {
          await api("/api/admin/settings", { method: "POST", body: { smtp: Object.fromEntries(new FormData(mailForm)) } });
          state.adminEdit = null;
          session.mail = true;
          mailForm.removeAttribute("data-smtp");  // the refresh must not keep it as a draft
          toast("已测试并保存");
          if (state.view === "#/admin" && state.adminTab === tab) await VIEWS.admin(true, tab);
        } catch (e) { toast(e.message); button.disabled = false; button.textContent = "测试并保存"; }
      };
    }
    on("[data-smtp-edit]", () => { state.adminEdit = state.adminEdit?.kind === "smtp" ? null : { kind: "smtp" }; VIEWS.admin(true, tab); });
    on("[data-smtp-cancel]", () => { state.adminEdit = null; mailForm?.removeAttribute("data-smtp"); VIEWS.admin(true, tab); });
    on("[data-smtp-clear]", () => { state.adminEdit = null; session.mail = false; act("/api/admin/settings", { smtp: null }, "已清除邮件服务"); });
    on("[data-default-edit]", () => {
      state.adminEdit = state.adminEdit?.kind === "default-model" ? null : { kind: "default-model" };
      VIEWS.admin(true, tab);
    });
    on("[data-default-cancel]", () => {
      state.adminEdit = null;
      defaultForm?.removeAttribute("data-default-model");
      VIEWS.admin(true, tab);
    });
    on("[data-default-test]", async (el) => {
      const chip = $("[data-default-health]", page);
      el.disabled = true; chip.className = "health busy"; chip.textContent = "测试中";
      try { const r = await api("/api/admin/default-model/test", { method: "POST" }); toast(r.health === "ok" ? "连接正常" : r.message); }
      catch (e) { toast(e.message); }
      VIEWS.admin(true, tab);
    });
    on("[data-default-reset]", () => { state.adminEdit = null; state.settings = null; act("/api/admin/settings", { default_model: null }, "已恢复内置默认模型"); });
    on("[data-invite]", async () => {
      try {
        const { code } = await api("/api/admin/invites", { method: "POST", body: { days: 7 } });
        navigator.clipboard?.writeText(code).catch(() => {});
        toast(`邀请码 ${code} 已复制`);
        const list = adminList("invites");  // the new code heads the list: make sure it is on the page shown
        const keep = (list.facets.state || []).includes("open") ? { state: ["open"] } : {};
        Object.assign(list, { q: "", page: 1, facets: keep, open: null });
        VIEWS.admin(true, tab);
      }
      catch (e) { toast(e.message); }
    });
    on("[data-save-limit]", () => act("/api/admin/settings", { max_jobs: Number($('[name="max_jobs"]', page).value) }, "已保存"));
    on("[data-zhs-parallel]", (el) => {
      const enable = el.dataset.zhsParallel === "on";
      act("/api/admin/settings", { zhs_parallel_study: enable }, enable ? "已开启" : "已关闭");
    });
    on("[data-registration]", (el) => {
      if (el.getAttribute("aria-pressed") === "true") return;
      act("/api/admin/settings", { registration: { [el.dataset.registration]: el.dataset.value === "1" } }, "已保存");
    });
    on("[data-site-pace]", (el) => {
      if (el.getAttribute("aria-pressed") === "true") return;
      state.settings = null;  // 偏好 shows the site pace too; read it again there
      act("/api/admin/settings", { answer_pace: el.dataset.sitePace }, `已改为${el.dataset.sitePace === "fast" ? "快速" : "稳妥"}`);
    });
    on("[data-export-logs]", () => {
      const from = new Date($('[name="log_from"]', page).value).getTime() / 1000;
      const to = new Date($('[name="log_to"]', page).value).getTime() / 1000;
      if (!(from < to)) { toast("请选择正确的时间段"); return; }
      location.href = `/api/admin/logs?kind=${$('[name="log_kind"]', page).value}&from=${Math.floor(from)}&to=${Math.ceil(to)}`;
    });
    // Limit and password open a small form inside the user's row; one at a time.
    on("[data-row-edit]", (el) => {
      const same = state.adminEdit?.uid === el.dataset.uid && state.adminEdit.kind === el.dataset.rowEdit;
      state.adminEdit = same ? null : { uid: el.dataset.uid, kind: el.dataset.rowEdit };
      VIEWS.admin("local", tab).then(() => $(".row_form input", page)?.focus());
    });
    on("[data-row-cancel]", () => { state.adminEdit = null; VIEWS.admin("local", tab); });
    page.querySelectorAll("[data-row-form]").forEach((form) => (form.onsubmit = (event) => {
      event.preventDefault();
      const { uid, rowForm } = form.dataset, value = form.elements.value.value.trim();
      if (rowForm === "password" && value.length < 8) { toast("新密码至少 8 位"); return; }
      state.adminEdit = null;
      if (rowForm === "limit") act(`/api/admin/users/${uid}/limit`, { max_jobs: value }, "已保存");
      else act(`/api/admin/users/${uid}/password`, { password: value }, "密码已重置");
    }));
    on("[data-copy]", (el) => navigator.clipboard?.writeText(el.dataset.copy).then(() => toast("已复制"), () => toast(el.dataset.copy)));
    on("[data-revoke]", (el) => act(`/api/admin/invites/${el.dataset.revoke}/revoke`, null, "邀请码已作废"));
    on("[data-stop-user]", (el) => act(`/api/admin/users/${el.dataset.stopUser}/stop`, null, "已发出停止指令"));
    on("[data-enable]", (el) => act(`/api/admin/users/${el.dataset.enable}/enable`, null, "已启用"));
    on("[data-disable]", (el) => act(`/api/admin/users/${el.dataset.disable}/disable`, null, "已停用"));
    // Searching, filtering and paging redraw from the lists in hand; the patch keeps the search box and its focus.
    const redraw = () => VIEWS.admin("local", tab);
    const search = $("[data-list-search]", page);
    if (search) {
      const find = () => { Object.assign(adminList(tab), { q: search.value, page: 1 }); redraw(); };
      search.oninput = (event) => { if (!event.isComposing) find(); };  // pinyin: wait for the characters
      // No oncompositionend property exists; the patch keeps this element, so listen once and swap the target.
      if (!search.findOnEnd) search.addEventListener("compositionend", () => search.findOnEnd());
      search.findOnEnd = find;
    }
    on("[data-facet]", (el) => {
      const list = adminList(tab);
      Object.assign(list, { open: list.open === el.dataset.facet ? null : el.dataset.facet, facetQ: "" });
      redraw();
      if (!TOUCH) $("[data-facet-search]", page)?.focus();  // a phone would pop its keyboard over a short menu
    });
    on("[data-facet-opt]", (el) => {
      const list = adminList(tab), picked = new Set(list.facets[list.open]);
      picked.has(el.dataset.facetOpt) ? picked.delete(el.dataset.facetOpt) : picked.add(el.dataset.facetOpt);
      Object.assign(list, { facets: { ...list.facets, [list.open]: [...picked] }, page: 1 });
      redraw();
    });
    on("[data-facet-clear]", () => { const list = adminList(tab); Object.assign(list, { facets: { ...list.facets, [list.open]: [] }, page: 1 }); redraw(); });
    on("[data-facet-reset]", () => { Object.assign(adminList(tab), { facets: {}, open: null, page: 1 }); redraw(); });
    const facetFind = $("[data-facet-search]", page);
    if (facetFind) {
      const narrow = () => { adminList(tab).facetQ = facetFind.value; redraw(); };
      facetFind.oninput = (event) => { if (!event.isComposing) narrow(); };
      if (!facetFind.findOnEnd) facetFind.addEventListener("compositionend", () => facetFind.findOnEnd());
      facetFind.findOnEnd = narrow;
      // Enter ticks the first option left, as in a command menu.
      facetFind.onkeydown = (event) => { if (event.key === "Enter" && !event.isComposing) $("[data-facet-opt]", page)?.click(); };
    }
    // A menu near the right edge (phones) slides left to stay on screen.
    const pop = $(".facet_pop", page);
    if (pop) { const over = pop.getBoundingClientRect().right - (innerWidth - 12); if (over > 0) pop.style.left = `${-over}px`; }
    on("[data-list-page]", (el) => {
      adminList(tab).page = Number(el.dataset.listPage);
      redraw().then(() => $(".list_tools", page)?.scrollIntoView({ block: "nearest" }));
    });
    const sizes = $("[data-list-size]", page);
    if (sizes) sizes.onchange = () => {
      const list = adminList(tab), first = (list.page - 1) * pageSize(tab), size = Number(sizes.value);
      store.set("studia-admin-size", { ...store.get("studia-admin-size", {}), [tab]: size });
      list.page = Math.floor(first / size) + 1;  // keep the first row in view
      redraw();
    };
    on("[data-user-more]", (el) => {
      state.adminOpen = state.adminOpen === el.dataset.userMore ? null : el.dataset.userMore;
      page.querySelectorAll("[data-user-row]").forEach((row) => {
        const open = row.dataset.userRow === state.adminOpen || row.dataset.userRow === state.adminEdit?.uid;
        row.classList.toggle("open", open);
        $("[data-user-more]", row).setAttribute("aria-expanded", open);
      });
    });
  },

  jobs(scope) {
    const admin = session.user?.role === "admin", all = admin && scope === "all";
    const head = `<h1 class="title">任务</h1>
            ${admin ? `<div class="tabs" role="tablist"><button class="tab" role="tab" aria-selected="${!all}" data-go="#/jobs">我的</button>
        <button class="tab" role="tab" aria-selected="${all}" data-go="#/jobs/all">全站${siteCount() ? `<span class="n">${siteCount()}</span>` : ""}</button></div>` : ""}`;
    if (all) {
      const people = state.sitePeople;
      setPage(head + (!people ? `<div class="empty loading">正在读取…</div>` : !people.length ? `<div class="empty">现在没有任务在运行</div>`
        : people.map((u) => `<div class="section"><h3>${esc(u.username)}</h3><span class="aside">${boardCount(u.jobs, u.limit)}</span></div>${board(u.jobs, u.limit, u.id)}`).join("")));
      return;
    }
    const open = new Set([...page.querySelectorAll(".run_lines:not([hidden])")].map((el) => el.dataset.lines));
    const live = state.jobs.length ? `<div class="section"><h3>进行中</h3><span class="aside">${boardCount(state.jobs, state.jobLimit)}</span></div>
      ${board(state.jobs, state.jobLimit)}` : "";
    const rows = state.history.map((j, i) => { const past = retried(j, i); return `<div class="run ${open.has(String(i)) ? "open" : ""} ${past ? "past" : ""}" data-key="${esc(j.id)}" data-history="${i}">${ICON[j.state] || ICON.stopped}
        <span class="t1">${esc(j.title)} · ${esc(j.course_name)}<small>${esc(platformOf(j.platform)?.short || "")} · ${esc(j.summary)}</small></span>
        <span class="fix">${past ? "" : fixButtons(j, i)}</span>
        <span class="state ${past ? "stopped" : j.state}">${past ? "已重试" : STATE_WORD[j.state] || ""}<span class="mono">${j.ended ? duration(j.ended - j.started) : ""}</span></span>
        <span class="when">${ago(j.ended || j.started)}</span><span class="chev_r" aria-hidden="true"></span></div>
      <div class="run_lines" data-lines="${i}" ${open.has(String(i)) ? "" : "hidden"}>${open.has(String(i)) ? logHtml(j.lines || [], "all", j.course_name) : ""}</div>`; }).join("");
    setPage(`${head}
      ${live}
      <div class="section"><h3>历史</h3></div>
      ${rows ? `<div class="runs">${rows}</div>` : `<div class="empty">还没有运行过任务</div>`}`);
    page.querySelectorAll("[data-history]").forEach((el) => (el.onclick = (event) => {
      if (event.target.closest("button, a")) return;
      const lines = page.querySelector(`[data-lines="${el.dataset.history}"]`);
      const j = state.history[el.dataset.history];
      lines.hidden = !lines.hidden;
      lines.innerHTML = lines.hidden ? "" : logHtml(j.lines || [], "all", j.course_name);
      el.classList.toggle("open", !lines.hidden);
    }));
    page.querySelectorAll("[data-retry]").forEach((el) => (el.onclick = () => {
      const j = state.history[el.dataset.retry];
      startJob({ platform: j.platform, course: j.course, type: TYPE_OF[j.title] });
    }));
  },

  home() {
    const p = currentPlatform();
    if (!p.logged_in) return go(`#/login/${p.id}`);
    const list = state.courses[p.id];
    const busy = (list || []).filter((c) => state.jobs.some((j) => j.platform === p.id && j.course === c.id)).length;
    const head = `<h1 class="title">课程</h1><p class="sub">${esc(p.name)}${list ? ` · ${list.length} 门${busy ? ` · ${busy} 门进行中` : ""}` : ""}</p>`;
    if (!list) return setPage(`${head}<div class="empty loading">正在读取课程…</div>`);
    const card = (c) => {
      const job = state.jobs.find((j) => j.platform === p.id && j.course === c.id);
      const last = state.history.find((j) => j.platform === p.id && j.course === c.id);
      const open = (state.papers[key(p.id, c.id)] || []).filter((x) => x.available && !x.done && !x.redo).length;
      // What is running and what is left to answer are separate facts: show both, never one hiding the other.
      const status = job ? `<span class="live">${WAIT_WORD[job.state] || LIVE_WORD[job.title] || "进行中"}</span>`
        : last?.state === "waiting" ? '<span class="live waiting">等你操作</span>' : "";
      // The history keeps only the latest jobs; lastRun remembers every course.
      const ran = last ? last.ended || last.started : state.lastRun?.[key(p.id, c.id)];
      const papers = open ? `<span class="todo">${open} 份未作答</span>` : state.paperErrors[key(p.id, c.id)] ? "试卷没读到" : "";
      const line = [status, papers].filter(Boolean).join('<span class="sep">·</span>') || (ran ? `上次 ${ago(ran)}` : learnt(c));
      return `<button class="course_card" style="--c:${inkOf(c)}" data-key="${esc(c.id)}" data-go="#/course/${p.id}/${c.id}">${coverHtml(p, c)}
        <span class="cc_body"><b>${esc(c.name)}</b><small>${esc(c.type || p.short)}</small>
          <span class="cc_bar"><span class="bar"><i style="width:${Number(c.progress) || 0}%"></i></span><span class="mono">${c.progress == null ? "—" : `${esc(c.progress)}%`}</span></span>
          <span class="cc_line">${line}</span></span></button>`;
    };
    setPage(`${head}${list.length ? `<div class="course_cards">${list.map(card).join("")}</div>` : '<div class="empty">这个账号下没有课程</div>'}`);
  },

  me() {
    const me = session.user;
    const row = (attrs, icon, label, sub = "", end = ICON.chev) =>
      `<button class="lrow" ${attrs}>${icon}<span class="lrow_t"><b>${esc(label)}</b>${sub ? `<small>${esc(sub)}</small>` : ""}</span>${end}</button>`;
    setPage(`<div class="me_card"><span class="avatar big">${esc(me ? me.username.slice(0, 1).toUpperCase() : "本")}</span>
        <span class="who"><b>${esc(me ? me.username : "本机")}</b><small>${me ? (me.role === "admin" ? "管理员" : "成员") : "只有这台电脑能访问"}</small></span></div>
      <div class="section"><h3>平台账号</h3></div>
      <div class="lrows">${state.platforms.map((p) => row(`data-go="${p.rescan || qaSoon(p) ? rescanLink(p) : p.logged_in ? "#/settings/account" : `#/login/${p.id}`}"`,
        `<span class="plat ${p.id}">${INITIAL[p.id]}</span>`, p.name, platformStatus(p),
        p.rescan || qaSoon(p) ? '<span class="lrow_go">扫码</span>' : p.logged_in ? ICON.chev : '<span class="lrow_go">登录</span>')).join("")}</div>
      <div class="section"><h3>设置</h3></div>
      <div class="lrows">${row('data-go="#/settings/account"', ICON.key, "账号")}${row('data-go="#/settings/models"', ICON.spark, "AI 模型")}
        ${row('data-go="#/settings/study"', ICON.gear, "偏好")}${me?.role === "admin" ? row('data-go="#/admin"', ICON.shield, "管理后台") : ""}</div>
      <div class="lrows" style="margin-top:14px">${row("data-toggle-theme", ICON.moon, "夜读模式", "", '<span class="switch" aria-hidden="true"></span>')}</div>
      ${me ? '<button class="btn danger me_out" data-signout>退出 Studia</button>' : ""}`);
  },

  login(pid, again) {
    const p = platformOf(pid);
    if (!p) return setPage(`<div class="empty">不支持这个平台</div>`);
    again = again && rescannable(p);
    if (p.logged_in && !again) return go(homeOf(p));
    const head = `<div class="crumb"><span class="dot ${pid}"></span>${esc(p.name)}</div><h1 class="title">${again ? "重新扫码" : `登录${/^[A-Za-z]/.test(p.short) ? " " : ""}${esc(p.short)}`}</h1>`;
    if (p.login === "qr") {
      setPage(`${head}<p class="sub">${again ? `${p.rescan ? "问答区要重新扫码" : "扫完问答区再用 8 小时"}` : p.lapsed ? "登录已过期，用智慧树 App 重新扫码" : "用智慧树 App 扫码"}</p>
        <div class="login_card"><div class="qr"><div class="qr_empty">正在获取二维码…</div></div>
          <div class="login_status"><div data-status><b>等待扫码</b><p>${TOUCH ? "长按保存二维码，在知到 App 里从相册扫码" : "二维码过期会自动刷新"}</p></div>
            <button class="btn" data-start-login>刷新二维码</button></div></div>`);
      $("[data-start-login]", page).onclick = () => qrLogin(pid);
      qrLogin(pid);
    } else {
      setPage(`${head}<p class="sub">${p.lapsed ? "登录已过期，请用职教云账号重新登录" : "用职教云账号登录"}</p>
        <div class="login_card"><div class="login_status"><div data-status><b>在浏览器中登录</b><p>登录完成后自动回到这里</p></div>
          <button class="btn primary" data-start-login>打开登录页</button></div></div>`);
      $("[data-start-login]", page).onclick = () => browserLogin(pid);
      browserLogin(pid, true);  // came back from the SSO page (callback or a swipe back): pick up its result
    }
  },

  course(pid, cid, tab) {
    const p = platformOf(pid);
    if (!p || !p.logged_in) return go(p ? `#/login/${pid}` : homeOf(currentPlatform()));
    const c = courseOf(pid, cid);
    if (!c) return setPage(`<div class="empty ${state.courses[pid] ? "" : "loading"}">${state.courses[pid] ? "没有找到这门课程" : "正在读取课程…"}</div>`);
    renderCourse(p, c, courseTab(c, tab), true);
  },

  async settings(tab = SETTINGS_TABS[0][0]) {
    tab = SETTINGS_TABS.some(([k]) => k === tab) ? tab : SETTINGS_TABS[0][0];
    const head = settingsHead(tab, "");
    if (tab === "account") {
      const me = session.user, editing = state.accountEdit, admin = me?.role === "admin";
      const cancel = '<button type="button" class="btn" data-account-edit="">取消</button>';
      const nameRow = editing === "username" ? `<form class="model plain password_form" data-username>
            <span class="m1"><b>修改用户名</b></span>
            <span class="pw_fields"><label class="auth_field"><span>新用户名</span><input name="username" value="${esc(me?.username)}" autocomplete="username" autocapitalize="off" minlength="2" maxlength="32" required></label>
              <p class="form_msg" role="alert"></p><span class="row_btns">${cancel}<button class="btn primary">保存</button></span></span></form>`
        : `<div class="model plain"><span class="account_who"><span class="avatar big">${esc(me?.username.slice(0, 1).toUpperCase())}</span>
            <span class="m1"><b>${esc(me?.username)}</b><span class="pill ${admin ? "blue" : ""}">${admin ? "管理员" : "成员"}</span>
            <small class="sans">${me?.created ? `${new Date(me.created * 1000).toLocaleDateString()} 加入` : ""}</small></span></span>
            <span class="row_btns"><button class="btn small" data-account-edit="username">修改用户名</button></span></div>`;
      const emailRow = editing === "email" ? `<form class="model plain password_form" data-email-form>
            <span class="m1"><b>${me?.email ? "更换邮箱" : "绑定邮箱"}</b></span>
            <span class="pw_fields">${emailFields()}<span class="row_btns">${cancel}<button class="btn primary">绑定</button></span></span></form>`
        : `<div class="model plain"><span class="m1"><b>邮箱</b><small class="sans">${me?.email ? esc(me.email)
            : session.mail ? "未绑定" : "管理员未配置邮件服务"}</small></span>
            <span class="row_btns">${session.mail ? `<button class="btn small ${me?.email ? "" : "primary"}" data-account-edit="email">${me?.email ? "更换" : "绑定邮箱"}</button>`
              : admin ? '<button class="btn small" data-go="#/admin/site">去配置</button>' : ""}</span></div>`;
      // 修改密码 asks first, then says where the mail went; another link waits a minute, since it voids the last.
      const sent = state.passwordSent;
      const passwordRow = editing === "password" ? `<div class="model plain password_form" data-password-panel>
            <span class="m1"><b>${sent ? "邮件已发送" : "修改密码"}</b><small class="sans">${sent
              ? `已发到 ${esc(me?.email)}`
              : `链接会发到 ${esc(me?.email)}`}</small></span>
            <span class="pw_fields"><p class="form_msg" role="alert"></p><span class="row_btns">
              <button type="button" class="btn" data-account-edit="">${sent ? "完成" : "取消"}</button>
              <button type="button" class="btn ${sent ? "" : "primary"}" data-password-send>${sent ? "重新发送" : "发送邮件"}</button></span></span></div>`
        : `<div class="model plain"><span class="m1"><b>密码</b></span>
            <span class="row_btns"><button class="btn small" data-account-edit="password" ${me?.email && session.mail ? "" : "disabled"}>修改密码</button></span></div>`;
      const studia = me ? `<div class="section"><h3>Studia 账号</h3></div>
        <div class="models">${nameRow}${emailRow}${passwordRow}</div>` : "";
      setPage(`${head}${studia}<div class="section"><h3>平台账号</h3></div>
        <div class="models">${state.platforms.map((p) => `<div class="model"><span class="plat ${p.id}">${INITIAL[p.id]}</span>
          <span class="m1"><b>${esc(p.name)}</b><small class="sans">${esc(platformStatus(p))} · ${p.login === "qr" ? "App 扫码登录" : "职教云浏览器授权"}</small></span><span></span>
          <span class="row_btns">${p.rescan || qaSoon(p) ? `<button class="btn small primary" data-go="${rescanLink(p)}">重新扫码</button>` : ""}${p.logged_in ? `<button class="btn small danger" data-logout="${p.id}" data-confirm="确认退出">退出</button>` : `<button class="btn small primary" data-go="#/login/${p.id}">登录</button>`}</span></div>`).join("")}</div>`);
      page.querySelectorAll("[data-logout]").forEach((el) => (el.onclick = async () => {
        try { await api(`/api/platforms/${el.dataset.logout}/logout`, { method: "POST" }); } catch (e) { toast(e.message); return; }
        await refreshState();
        toast("已退出登录");
        VIEWS.settings("account");
      }));
      page.querySelectorAll("[data-account-edit]").forEach((el) => (el.onclick = () => {
        state.accountEdit = el.dataset.accountEdit || null;
        state.passwordSent = null;
        quiet = true; VIEWS.settings("account"); quiet = false;
        $("[data-username] input, [data-email-form] input, [data-password-send]", page)?.focus();
      }));
      const nameForm = $("[data-username]", page);
      if (nameForm) nameForm.onsubmit = async (event) => {
        event.preventDefault();
        try {
          ({ user: session.user } = await api("/api/auth/username", { method: "POST", body: { username: nameForm.elements.username.value.trim() } }));
          state.accountEdit = null;
          renderSidebar();
          toast("用户名已修改");
          VIEWS.settings("account");
        } catch (e) { $(".form_msg", nameForm).textContent = e.message; }
      };
      const emailForm = $("[data-email-form]", page);
      if (emailForm) wireEmailForm(emailForm, () => { state.accountEdit = null; toast("邮箱已绑定"); VIEWS.settings("account"); });
      const send = $("[data-password-send]", page);
      if (send) {
        if (state.passwordSent) resendAfter(send, state.passwordSent);
        send.onclick = async () => {
          send.disabled = true;
          send.textContent = "发送中…";
          try {
            await api("/api/auth/password", { method: "POST" });
            state.passwordSent = Date.now();
            quiet = true; VIEWS.settings("account"); quiet = false;
          } catch (e) {
            $("[data-password-panel] .form_msg", page).textContent = e.message;
            send.disabled = false;
            send.textContent = state.passwordSent ? "重新发送" : "发送邮件";
          }
        };
      }
      return;
    }
    // Draw from the last copy at once; repaint only if the server's copy differs.
    const cached = state.settings;
    if (cached) paintSettings(tab, head, cached, false);
    else setPage(`${head}<div class="empty loading">正在读取…</div>`);
    try { state.settings = await api("/api/settings"); } catch (error) { if (!cached) toast(error.message); return; }
    if (location.hash.startsWith(`#/settings/${tab}`)) {
      if (!cached || JSON.stringify(cached) !== JSON.stringify(state.settings)) paintSettings(tab, head, state.settings, true);
    }
  },
};

// The resend button of the 修改密码 panel counts down from the last send.
function resendAfter(button, sentAt) {
  if (!button.isConnected) return;
  const left = Math.ceil(60 - (Date.now() - sentAt) / 1000);
  button.disabled = left > 0;
  button.textContent = left > 0 ? `${left} 秒后可重新发送` : "重新发送";
  if (left > 0) setTimeout(() => resendAfter(button, sentAt), 1000);
}

// Binding an email: a code mailed to the address. In 设置 → 账号 and in the prompt when the page opens.
const emailFields = () => `<label class="auth_field"><span>邮箱</span><span class="code_row">
    <input name="email" type="email" autocomplete="email" autocapitalize="off" placeholder="name@example.com" required>
    <button type="button" class="btn" data-send-code>发送验证码</button></span></label>
  <label class="auth_field"><span>验证码</span><input name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="邮件里的 6 位数字" required></label>
  <p class="form_msg" role="alert"></p>`;
function wireEmailForm(form, done) {
  const msg = $(".form_msg", form), send = $("[data-send-code]", form), { email, code } = form.elements;
  const say = (text, ok = false) => { msg.textContent = text; msg.classList.toggle("ok", ok); };
  form.oninput = () => { if (!msg.classList.contains("ok")) say(""); };
  send.onclick = async () => {
    if (!email.value.trim() || !email.checkValidity()) { say("请填写正确的邮箱"); email.focus(); return; }
    send.disabled = true;
    send.textContent = "发送中…";
    try {
      await api("/api/auth/email/code", { method: "POST", body: { email: email.value.trim() } });
      say(`验证码已发到 ${email.value.trim()}`, true);
      code.focus();
      for (let left = 60; left > 0 && form.isConnected; left -= 1) { send.textContent = `${left} 秒后重发`; await sleep(1000); }
    } catch (e) { say(e.message); }
    send.disabled = false;
    send.textContent = "发送验证码";
  };
  form.onsubmit = async (event) => {
    event.preventDefault();
    if (!code.value.trim()) { say("请填写验证码"); code.focus(); return; }
    const button = $("button.primary", form);
    button.disabled = true;
    try { ({ user: session.user } = await api("/api/auth/email", { method: "POST", body: { code: code.value.trim() } })); done(); }
    catch (e) { say(e.message); button.disabled = false; }
  };
}
// Once each time the page opens, until the email is bound or the person picks 今天不显示.
function promptEmail() {
  const me = session.user, later = `studia-email-later:${me?.id}`;
  if (session.mode !== "hosted" || !me || me.email || !session.mail || store.get(later, "") === new Date().toDateString()) return;
  const dialog = document.createElement("dialog");
  dialog.className = "modal";
  dialog.setAttribute("aria-labelledby", "email-prompt");
  // On a phone, focusing the email field would pop the keyboard before the person has read the prompt.
  dialog.innerHTML = `<form data-email-form><h3 id="email-prompt" ${TOUCH ? 'tabindex="-1" autofocus' : ""}>绑定邮箱</h3>
      ${emailFields()}
      <div class="modal_btns"><button type="button" class="link" data-later>今天不再提醒</button><span class="grow"></span>
        <button type="button" class="btn" data-skip>暂时跳过</button><button class="btn primary">绑定</button></div></form>`;
  document.body.appendChild(dialog);
  dialog.addEventListener("close", () => dialog.remove());
  $("[data-skip]", dialog).onclick = () => dialog.close();
  $("[data-later]", dialog).onclick = () => { store.set(later, new Date().toDateString()); dialog.close(); };
  wireEmailForm($("form", dialog), () => { dialog.close(); toast("邮箱已绑定"); });
  dialog.showModal();
}

let stepTimer = 0;
function paintSettings(tab, head, data, again) {
  if (tab === "study") {
    // Small numbers: tap − / +, saved as soon as the taps stop. No keyboard, no save button.
    // The pace takes effect on its own tap; 快速 asks twice, since it risks the platform's slider check.
    // On a hosted site the pace is the admin's, set for everyone in 管理后台 → 站点; 偏好 only has it locally.
    const fast = data.pace === "fast";
    const paceButtons = `<button class="btn small" data-pace="steady" aria-pressed="${!fast}">稳妥</button><button class="btn small" data-pace="fast" aria-pressed="${fast}" ${fast ? "" : 'data-confirm="确认用快速"'}>快速</button>`;
    const row = (k, label, note) => `<div class="model plain stepper_row"><span class="m1"><b>${label}</b><small class="sans">${note}</small></span>
      <span class="stepper"><button class="btn small" data-step="${k}" data-d="-1" aria-label="减少" ${data.concurrency[k] <= 1 ? "disabled" : ""}>−</button>
        <output>${data.concurrency[k]}</output><button class="btn small" data-step="${k}" data-d="1" aria-label="增加" ${data.concurrency[k] >= 8 ? "disabled" : ""}>＋</button></span></div>`;
    quiet = again;
    setPage(`${head}<div class="section"><h3>并发数量</h3><span class="aside">1–8</span></div>
      <div class="models">${row("ai", "AI 答题", "同时作答的题数")}${row("study", "自动学习", "同时学的资源数")}</div>
      ${data.pace_locked ? "" : `<div class="section"><h3>答题节奏</h3><span class="aside">只影响智慧树</span></div>
      <div class="models"><div class="model plain stepper_row"><span class="m1"><b>${fast ? "快速" : "稳妥"}</b><small class="sans">${fast
        ? "每步间隔 0.1–0.5 秒"
        : "每步间隔 0.5–2 秒"}</small></span>
        <span class="row_btns">${paceButtons}</span></div></div>`}`);
    quiet = false;
    page.querySelectorAll("[data-pace]").forEach((el) => (el.onclick = async () => {
      const pace = el.dataset.pace;
      if ((state.settings.pace || "steady") === pace) return;
      try {
        await api("/api/settings/pace", { method: "POST", body: { pace } });
        state.settings.pace = pace;
        toast(`已改为${pace === "fast" ? "快速" : "稳妥"}`);
      } catch (e) { toast(e.message); }
      paintSettings(tab, head, state.settings, true);
    }));
    page.querySelectorAll("[data-step]").forEach((el) => (el.onclick = () => {
      const c = state.settings.concurrency, k = el.dataset.step;
      c[k] = Math.max(1, Math.min(8, c[k] + Number(el.dataset.d)));
      paintSettings(tab, head, state.settings, true);
      clearTimeout(stepTimer);
      stepTimer = setTimeout(async () => {
        try { await api("/api/settings/concurrency", { method: "POST", body: { ai: c.ai, study: c.study } }); toast("已保存"); }
        catch (e) { toast(e.message); state.settings = null; VIEWS.settings(tab); }
      }, 600);
    }));
    return;
  }
  renderModels(head, data.models, null, again);
}

// A waiting or failed run the user has since started again (or that is running now) needs no button.
const retried = (j, i) => (j.state === "waiting" || j.state === "error")
  && [...state.jobs, ...state.history.slice(0, i)].some((x) => x.platform === j.platform && x.course === j.course && x.title === j.title);
function progressBar(run) {
  const { pct, label } = progressOf(run);
  return pct == null ? "进行中" : `<span class="bar"><i style="width:${pct}%"></i></span><span class="mono">${esc(label)}</span>`;
}
function fixButtons(j, i) {
  const type = TYPE_OF[j.title];
  // An update stopped it and it was not restarted on its own (answering, or interrupted too long ago).
  if (j.state === "stopped" && j.summary === "更新时中断" && i === state.history.findIndex((x) => x.course === j.course && x.title === j.title)) {
    return type === "answer" ? `<button class="btn small" data-go="#/course/${j.platform}/${j.course}/answer">重新作答</button>`
      : `<button class="btn small primary" data-retry="${i}">重试</button>`;
  }
  if (j.state === "waiting") {
    const p = platformOf(j.platform);
    if ((type === "qa" || type === "ask") && p?.rescan) return `<button class="btn small primary" data-go="${rescanLink(p)}">重新扫码</button>`;
    if (/登录/.test(j.summary)) return `<button class="btn small primary" data-go="#/login/${j.platform}">重新登录</button>`;
    if (/时长/.test(j.summary)) return "";
    if (type === "qa" || type === "ask") return `<button class="btn small" data-retry="${i}">重试</button>`;
    if (type === "answer") return `<button class="btn small" data-go="#/course/${j.platform}/${j.course}/answer">验证后重新作答</button>`;
    return `<button class="btn small" data-retry="${i}">验证后重试</button>`;
  }
  if (j.state !== "error" || i !== state.history.findIndex((x) => x.course === j.course && x.title === j.title)) return "";
  if (type === "answer") return `<button class="btn small" data-go="#/course/${j.platform}/${j.course}/answer">重新选择试卷</button>`;
  return `<button class="btn small primary" data-retry="${i}">重试</button>`;
}

/* ---------------------------------------------------------------- settings: models */

const HEALTH = { ok: ["ok", "可用"], error: ["error", "出错"] };
function renderModels(head, models, editing = null, again = true) {
  const host = (url) => { try { return new URL(url).host; } catch { return url; } };
  const form = (m) => `<form class="form_card" data-form="${m ? esc(m.id) : "new"}">
      <h3>${m ? "编辑模型" : "添加模型"}</h3>
      <div class="field"><label>名称</label><input name="provider_name" value="${esc(m?.provider || "")}" placeholder="方便自己区分，例如 DeepSeek 官方"></div>
      <div class="field"><label>服务地址</label><input name="base_url" value="${esc(m?.base_url || "")}" placeholder="https://api.example.com/v1" required></div>
      <div class="field"><label>模型</label><input name="model" value="${esc(m?.model || "")}" placeholder="例如 deepseek-chat" required></div>
      <div class="field"><label>API Key</label><input name="api_key" type="password" autocomplete="off" ${m ? `placeholder="留空则不修改（当前 ${esc(m.key_hint)}）"` : "required"}></div>
      <div class="form_btns">${m?.deletable ? '<button type="button" class="btn danger" data-delete data-confirm="确认删除">删除这个模型</button><span class="grow"></span>' : ""}<button type="button" class="btn" data-cancel>取消</button><button class="btn primary">${m ? "保存" : "保存并测试"}</button></div>
    </form>`;
  const row = (m) => {
    if (editing === m.id) return form(m);
    const [cls, label] = HEALTH[m.health] || ["", "未测试"];
    return `<div class="model ai ${m.active ? "on" : ""}" data-id="${esc(m.id)}">
      <span class="m1"><b>${esc(m.provider || "未命名服务")}</b>${m.deletable ? "" : `<span class="pill">${session.mode === "hosted" ? "管理员提供" : "内置"}</span>`}
        <small>${esc(m.model)} · ${esc(host(m.base_url))} · ${esc(m.key_hint)}</small></span>
      <span class="health ${cls}" title="${esc(m.health_message)}">${label}</span>
      <span class="row_btns">${m.active ? '<span class="in_use">使用中</span>' : '<button class="btn small primary" data-activate>改用</button>'}
        <button class="btn small" data-test>测试</button>${m.deletable ? '<button class="btn small" data-edit>编辑</button>' : ""}</span></div>`;
  };
  quiet = again;
  setPage(`${head}<div class="section"><h3>${PHONE.matches ? "" : "AI 模型"}</h3><button class="link" data-add>＋ 添加模型</button></div>
    ${editing === "new" ? form(null) : ""}<div class="models">${models.map(row).join("") || (editing === "new" ? "" : '<div class="model plain"><span class="m1"><small class="sans">还没有可用的模型</small></span></div>')}</div>`);
  quiet = false;
  const reload = async (edit = null) => {
    try { state.settings = await api("/api/settings"); renderModels(head, state.settings.models, edit); } catch (e) { toast(e.message); }
  };
  $("[data-add]", page).onclick = () => renderModels(head, models, "new");
  page.querySelectorAll("[data-cancel]").forEach((el) => (el.onclick = () => renderModels(head, models)));
  page.querySelectorAll(".model[data-id]").forEach((rowEl) => {
    const id = rowEl.dataset.id;
    const use = $("[data-activate]", rowEl);
    if (use) use.onclick = async () => {
      try { await api("/api/settings/models/activate", { method: "POST", body: { id } }); toast("已切换模型"); reload(); } catch (e) { toast(e.message); }
    };
    const edit = $("[data-edit]", rowEl);
    if (edit) edit.onclick = () => renderModels(head, models, id);
    $("[data-test]", rowEl).onclick = async () => {
      const chip = $(".health", rowEl);
      chip.className = "health busy"; chip.textContent = "测试中";
      try { const r = await api(`/api/settings/models/${id}/test`, { method: "POST" }); toast(r.health === "ok" ? "连接正常" : r.message); } catch (e) { toast(e.message); }
      reload();
    };
  });
  const formEl = $("[data-form]", page);
  const del = $("[data-delete]", page);
  if (del) del.onclick = async () => {
    try { await api(`/api/settings/models/${formEl.dataset.form}/delete`, { method: "POST" }); toast("已删除"); reload(); } catch (e) { toast(e.message); }
  };
  if (formEl) {
    formEl.querySelector("input").focus();
    formEl.onsubmit = async (event) => {
      event.preventDefault();
      const body = Object.fromEntries(new FormData(formEl));
      const id = formEl.dataset.form;
      try {
        const r = await api(id === "new" ? "/api/settings/models" : `/api/settings/models/${id}`, { method: "POST", body });
        if (id === "new") {
          toast("已保存，正在测试连接…");
          const t = await api(`/api/settings/models/${r.id}/test`, { method: "POST" });
          toast(t.health === "ok" ? "模型可用，已设为使用中" : `已保存，但连接失败：${t.message}`);
        } else toast("已保存");
        reload();
      } catch (e) { toast(e.message); }
    };
  }
}

/* ---------------------------------------------------------------- course page */

// A course's cover is its own answer sheet: one cell per unit, estimated from the progress until the units arrive.
function coverHtml(p, c) {
  const units = (unitsOf(key(p.id, c.id)) || []).flatMap((ch) => ch.units).map((u) => u.state);
  const cells = units.length ? units : Array.from({ length: 40 }, (_, i) => (i < Math.round((Number(c.progress) || 0) * 0.4) ? "done" : "queued"));
  return `<span class="cover" aria-hidden="true">${cells.slice(0, 72).map((x) => `<i class="cell ${x}"></i>`).join("")}</span>`;
}

// The server decides per course what can run (web/server.py course_features): review and Q&A only
// where the course's assessment rule gives them points.
function studyActions(p, c) {
  const f = c.features || {};
  const study = p.id === "zhs" ? (c.kind === "shared" ? "1.5 倍速看完剩下的视频，弹题自动答" : "完成文档、课件和视频")
    : "学完课件和视频，自动讨论和评价";
  return [["study", ICON.play, "自动学习", study],
    ...(f.review ? [["review", ICON.repeat, "每日复习", "每天重看 30 分钟"]] : [])];
}
// "#/course/p/c/<tab>": the Q&A tab only exists on courses whose assessment counts it.
const courseTab = (c, tab) => tab === "answer" ? "answer" : tab === "qa" && c.features?.qa ? "qa" : "study";

// Q&A tab. Where the interaction share stands, then two actions: answer a few questions now, or have
// AI draft new ones that the person edits before they go out. Everything posted is listed below.
// The board's own rules (智慧树问答规则): 10 valid questions and 20 valid answers fill their quantity scores; its data updates
// the next morning, and a few a day per course keeps clear of its flood checks. The server says how many are left
// today (room) and why when none are. Each lane is one part of the score, drawn as cells like the course grid:
// counted, posted today (counted tomorrow), still open.
const QA_LANES = { ask: { cap: 10, daily: 5, size: 3, key: "studia-ask-size" }, answer: { cap: 20, daily: 10, size: 5, key: "studia-qa-size" } };
function qaCount(kind, room) {
  const lane = QA_LANES[kind], left = room ? room[kind] : lane.daily;
  return Math.max(1, Math.min(Number(store.get(lane.key, lane.size)) || lane.size, left || 1, lane.daily));
}
function qaLane(kind, room, { title, valid, today, reason, note, button, off }) {
  const lane = QA_LANES[kind], counted = Math.min(valid || 0, lane.cap), pending = Math.max(0, Math.min(today, lane.cap - counted));
  const cells = Array.from({ length: lane.cap }, (_, i) => `<i class="cell ${i < counted ? "done" : i < counted + pending ? "pending" : ""}"></i>`).join("");
  const n = qaCount(kind, room), most = Math.min(room ? room[kind] : lane.daily, lane.daily);
  const stepper = `<span class="stepper"><button class="btn small" data-qa-step="${kind}" data-d="-1" aria-label="少一条" ${n <= 1 ? "disabled" : ""}>−</button>
    <output>${n}</output><button class="btn small" data-qa-step="${kind}" data-d="1" aria-label="多一条" ${n >= most ? "disabled" : ""}>+</button></span>`;
  return `<section class="qa_lane"><header><b>${title}</b><span class="qa_num">${valid ?? "—"}<span class="of">/${lane.cap}</span></span></header>
    <div class="qa_cells" title="实心：已算分 · 斜纹：今天发的，明天上午算 · 空：还能拿分">${cells}</div>
    <small class="sans">${esc(reason || note)}</small>
    <div class="qa_act">${reason || off ? "" : stepper}${button(n, !!reason || off)}</div></section>`;
}
function qaBody(p, c) {
  const k = key(p.id, c.id), earned = state.earned[k], q = earned?.qa;
  const draft = state.qaDraft[k], posts = state.qaPosts[k], room = state.qaRoom[k], today = room?.posted || { ask: 0, answer: 0 };
  const texts = draft?.texts || [];
  const askBlock = blocker(p.id, c.id, "ask") || (room && !room.ask ? room.why.ask : "");
  const answerBlock = blocker(p.id, c.id, "qa") || (room && !room.answer ? room.why.answer : "");
  const head = `<div class="qa_head"><span class="qa_score"><b>${earned ? pts(earned.interactive) : "—"}</b><span class="of">/${c.shares?.interactive || 10}</span> 分</span>
    ${!p.rescan && !qaSoon(p) && qaLeft(p) > 0 ? `<span class="qa_time">问答区剩余 <span data-qa-left="${p.id}">${hoursLeft(qaLeft(p))}</span></span>` : ""}
    <small class="sans">斜纹：今日发布</small></div>`;
  const ask = qaLane("ask", room, { title: "提问", valid: q?.questions, today: today.ask,
    reason: draft?.loading ? `正在出第 ${draft.loading}/${draft.total} 条…` : askBlock,
    note: draft?.error || `今天还能问 ${room ? room.ask : "—"} 条 · 收获回答 ${q?.received ?? "—"}`,
    button: (n, off) => `<button class="btn" data-qa-draft ${off ? "disabled" : ""}>${texts.length ? "换一批" : `出 ${n} 条题`}</button>`, off: p.rescan });
  const answer = qaLane("answer", room, { title: "回答", valid: q?.answers, today: today.answer, reason: answerBlock,
    note: `今天还能答 ${room ? room.answer : "—"} 条`,
    button: (n, off) => `<button class="btn primary" data-qa-start ${off ? "disabled" : ""}>答 ${n} 条</button>`, off: p.rescan });
  const tooMany = room && texts.length > room.ask;
  const drafts = texts.map((t, i) => `<div class="model plain qa_draft"><textarea rows="2" data-qa-edit="${i}" maxlength="200">${esc(t)}</textarea>
      <button class="btn small" data-qa-drop="${i}" aria-label="删掉这条">删掉</button></div>`).join("")
    + (texts.length ? `<div class="model plain qa_row"><span class="m1"><small class="sans">${esc(askBlock ||
      (tooMany ? `今天还能发 ${room.ask} 条，删掉几条` : "隔 10–20 分钟发一条"))}</small></span>
      <span class="row_btns"><button class="btn primary" data-qa-ask ${p.rescan || askBlock || tooMany || draft?.loading ? "disabled" : ""}>发布 ${texts.length} 条</button></span></div>` : "");
  // Only a hosted site has classmates to answer; the person opts in, both ways.
  const peers = session.mode === "hosted" ? `<div class="model plain qa_row qa_switch"><span class="m1"><b>站内互答</b><small class="sans">${
      state.qaPeers ? "先答同学的提问" : "和同班同学互相回答"}</small></span>
    <span class="row_btns"><button class="switch ${state.qaPeers ? "on" : ""}" role="switch" aria-checked="${!!state.qaPeers}" aria-label="站内互答" data-qa-peers></button></span></div>` : "";
  const list = !posts ? '<div class="empty loading">正在读取…</div>' : !posts.length ? '<div class="empty">还没在这门课发过</div>'
    : `<div class="runs">${posts.map((x) => {
      // Keyed by the post itself, so a new post on top does not move which one is open.
      const open = state.qaOpen.has(`${k}:${x.kind}:${x.at}`);
      return `<div class="run qa_post ${open ? "open" : ""}" data-key="${esc(`${x.kind}:${x.at}`)}" data-qa-post="${esc(`${x.kind}:${x.at}`)}"><span class="stamp ${x.kind === "ask" ? "k" : ""}">${x.kind === "ask" ? "问" : "答"}</span>
        <span class="t1">${esc(x.question)}<small>${ago(x.at)}</small></span><span></span><span></span>
        <span class="when"></span></div>
        ${x.kind === "answer" && open ? `<div class="qa_text">${esc(x.text)}</div>` : ""}`;
    }).join("")}</div>`;
  const rescan = p.rescan ? `<div class="model plain qa_row qa_rescan"><span class="m1"><b>问答区要重新扫码</b></span>
    <span class="row_btns"><button class="btn small primary" data-go="${rescanLink(p)}">重新扫码</button></span></div>`
    : qaSoon(p) ? `<div class="model plain qa_row qa_rescan"><span class="m1"><b>问答区还能用 <span data-qa-left="${p.id}">${hoursLeft(qaLeft(p))}</span></b>
      <small class="sans">扫码后再用 8 小时</small></span>
    <span class="row_btns"><button class="btn small" data-go="${rescanLink(p)}">现在扫码</button></span></div>` : "";
  return `<div class="models qa_board">${head}${rescan}<div class="qa_lanes">${ask}${answer}</div>
    <div class="qa_rule"><header><b>获得至少 5 个有效回答的提问</b><span class="qa_num">${esc(q?.qualified ?? "—")}<span class="of"> 条</span></span></header></div>${drafts}${peers}</div>
    <div class="section"><h3>已发布</h3></div>${list}`;
}
const loadingPosts = new Set();
async function loadQaPosts(p, c) {
  const k = key(p.id, c.id);
  if (loadingPosts.has(k) || state.qaPosts[k]) return;
  loadingPosts.add(k);
  try { ({ posts: state.qaPosts[k], room: state.qaRoom[k], peers: state.qaPeers } = await api(`/api/platforms/${p.id}/qa?course=${encodeURIComponent(c.id)}`)); }
  catch { state.qaPosts[k] = []; }
  finally { loadingPosts.delete(k); }
  repaint();
}
// One question per request, shown as it comes: a slow model takes a minute or two for each,
// and one request for all of them could outlast the browser or a proxy in between.
async function draftQuestions(p, c) {
  const room = state.qaRoom[key(p.id, c.id)];
  const draft = state.qaDraft[key(p.id, c.id)] = { texts: [], total: qaCount("ask", room), loading: 1 };
  for (; draft.loading <= draft.total; draft.loading++) {
    repaint();
    try { draft.texts.push(...(await api(`/api/platforms/${p.id}/qa/draft`, { method: "POST", body: { course: c.id, have: draft.texts } })).questions); }
    catch (error) { draft.error = error.message; break; }
  }
  draft.loading = 0;
  if (!draft.texts.length && !draft.error) draft.error = "AI 这次没出成，换一批试试";
  repaint();
}

// The course's fingerprint: where its points come from, one box per share sized by its weight.
// Boxes Studia can fill are inked; the rest (exams, meet sessions) stay outlined.
const SHARES = [["progress", "学习", 1], ["habit", "习惯", 1], ["interactive", "互动", 1], ["knowledge", "掌握度", 0],
  ["test", "测试", 1], ["meet", "见面课", 0], ["final", "期末", 0]];
// Each box is exactly as wide as its share and fills as far as the points earned; a ruler underneath
// reads the 0–100 scale, with a long tick and its number where one share ends and the next begins.
const pts = (n) => (Number.isInteger(n) ? String(n) : n.toFixed(1));
function fingerprint(shares, earned) {
  const parts = shares ? SHARES.filter(([k]) => shares[k] > 0) : [];
  if (!parts.length) return "";
  let at = 0;
  const edges = [0], boxes = parts.map(([k, word, auto]) => {
    const got = earned?.[k], none = earned && !got && (k === "final" || k === "meet");
    const fill = earned && !none ? Math.min(100, (got / shares[k]) * 100) : 0;
    edges.push((at += shares[k]));
    return `<span class="share ${auto ? "auto" : ""}" style="--fill:${fill}%" title="${word} ${earned ? `${none ? "未开始" : pts(got)} / ` : ""}${shares[k]} 分">${word}</span>`;
  });
  const ticks = [...new Set([...edges, ...Array.from({ length: Math.floor(at / 5) + 1 }, (_, i) => i * 5)])].sort((a, b) => a - b);
  const ruler = ticks.map((v) => `<i class="${edges.includes(v) ? "edge" : v % 10 ? "" : "ten"}" style="left:${(v / at) * 100}%">${edges.includes(v) ? `<span>${v}</span>` : ""}</i>`).join("");
  return `<div class="fp"><div class="shares" style="grid-template-columns:${parts.map(([k]) => `minmax(0, ${shares[k]}fr)`).join(" ")}">${boxes.join("")}</div>
    <div class="ruler" aria-hidden="true">${ruler}</div></div>`;
}
// Under the progress digits: the course's current score where the platform gives one.
function scoreNote(c, papers, earned) {
  const full = (n) => `<span class="of">/${n}</span>`;
  if (earned) return `当前 <b>${pts(earned.total)}</b>${full(Object.values(c.shares || {}).reduce((a, b) => a + b, 0) || 100)} 分`;
  const scores = c.kind === "ai" ? (papers || []).map((x) => Number(x.score)).filter((n) => Number.isFinite(n) && n > 0) : [];
  return scores.length ? `作业均分 <b>${(scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1)}</b>${full(100)}` : "";
}
const loadingEarned = new Set(), earnedErrors = new Set(), earnedRetry = new Set();
async function loadEarned(p, c) {
  const k = key(p.id, c.id);
  if (loadingEarned.has(k) || earnedErrors.has(k) || state.earned[k]) return;
  loadingEarned.add(k);
  try { state.earned[k] = (await api(`/api/platforms/${p.id}/score?course=${encodeURIComponent(c.id)}`)).earned; }
  catch { if (!earnedRetry.has(k)) earnedErrors.add(k); }  // retry on re-entry, not on every repaint
  finally { loadingEarned.delete(k); earnedRetry.delete(k); }
  repaint();
}
const STAMP = { 考试: "k", 测验: "c" };

function renderCourse(p, c, tab, full = false) {
  const k = key(p.id, c.id);
  const papers = state.papers[k];
  const open = (papers || []).filter((x) => x.available && !x.done).length;
  const answerBlock = blocker(p.id, c.id, "answer");
  const head = `
    <section class="hero">
      <div class="hero_main">
        <div class="crumb"><span class="dot ${p.id}"></span>${esc(p.short)}<span>/</span>${esc(c.type || p.name)}</div>
        <h1 class="title">${esc(c.name)}</h1>
        ${fingerprint(c.shares, state.earned[k])}
      </div>
      <div class="hero_side">
        <div class="hero_stat"><span class="hero_label">学习进度</span>
          ${c.progress == null ? '<span class="digits"><i>—</i></span>' : `<span class="digits">${[...String(c.progress)].map((d) => `<i>${esc(d)}</i>`).join("")}<small>%</small></span>`}
          <span class="hero_note score_note">${scoreNote(c, papers, state.earned[k])}</span></div>
        ${p.features.answer ? `<button class="hero_stat" data-go="#/course/${p.id}/${c.id}/answer"><span class="hero_label">可作答</span>
          <span class="pen_num">${papers ? open : "—"}</span><span class="hero_note">份试卷 ›</span></button>` : ""}
      </div>
    </section>
    <div class="tabs seg" role="tablist">
      <button class="tab" role="tab" aria-selected="${tab === "study"}" data-go="#/course/${p.id}/${c.id}">学习</button>
      <button class="tab" role="tab" aria-selected="${tab === "answer"}" data-go="#/course/${p.id}/${c.id}/answer">答题${open ? `<span class="n">${open}</span>` : ""}</button>
      ${c.features?.qa ? `<button class="tab" role="tab" aria-selected="${tab === "qa"}" data-go="#/course/${p.id}/${c.id}/qa">问答区</button>` : ""}
    </div>`;
  let body;
  if (tab === "study") {
    body = `<div class="acts">${studyActions(p, c).map(([type, icon, label, text], i) => {
      const lastOf = state.history.find((j) => j.platform === p.id && j.course === c.id && j.title === LABEL[type]);
      const block = blocker(p.id, c.id, type);
      const foot = block || (lastOf ? `上次 ${ago(lastOf.ended || lastOf.started)} · ${lastOf.summary}` : "还没有运行过");
      return `<button class="act" data-start="${type}" ${block ? "disabled" : ""}><span class="act_head"><span class="glyph">${icon}</span>${label}</span>
        <p>${text}</p><span class="foot"><span>${esc(foot)}</span>${i === 0 ? '<span class="kbd">S</span>' : ""}</span></button>`;
    }).join("")}</div>
      <div class="section"><h3>学习单元</h3></div>
      ${gridHtml(k)}`;
  } else if (tab === "qa") {
    body = qaBody(p, c);
  } else if (!p.features.answer) {
    body = `<div class="notice">${esc(p.name)} 的网页版答题还在接入中。现在可以在终端里运行 <code>python StartWork.py</code>，选这门课后进入「AI 答题」。</div>`;
  } else if (!papers) {
    const failed = state.paperErrors[k];
    body = failed ? `<div class="empty">${esc(failed)} · <button class="link" data-papers-retry="${esc(k)}">重试</button></div>` : `<div class="empty loading">正在读取试卷…</div>`;
  } else {
    const selected = selectedOf(k);
    for (const id of selected) if (!papers.some((x) => x.id === id && x.available)) selected.delete(id);
    // While this course is being answered, each paper shows how far the job got with it instead of a box to tick.
    const job = state.jobs.find((j) => j.platform === p.id && j.course === c.id && isAnswer(j) && j.state === "running");
    const sheet = job ? answerRows(runOf(job.id)) : null;
    const rowOf = (x) => sheet?.find((r) => (r.id != null ? String(r.id) === String(x.id) : r.name === x.name));
    const row = (x) => {
      const r = rowOf(x), on = sheet ? Boolean(r) : selected.has(x.id);
      const pill = r ? (r.state === "running" ? `<span class="pq"><span class="cells">${cellsHtml(questionStates(r))}</span><small>${esc(r.stage)}</small></span>`
          : `<span class="state ${PAPER_TONE[r.state] || "stopped"}">${esc(paperWord(r.state))}</span>`)
        : sheet || !x.available ? ""
        : x.redo_left != null ? `<span class="pill blue">可重做 · 剩 ${esc(x.redo_left)} 次</span>`
        : x.redo ? '<span class="pill blue">可重做</span>'
        : x.done ? `<span class="pill">已提交</span>` : "";
      const note = x.reason || (x.available ? x.status : "");
      return `<button class="paper ${on ? "on" : ""} ${r?.state === "running" ? "now" : ""} ${x.available && !(sheet && !r) ? "" : "off"}" data-key="${esc(x.id)}" data-paper="${esc(x.id)}">
        <span class="box">${on ? ICON.tick : ""}</span><span class="stamp ${STAMP[x.category] || ""}">${esc((x.category || "作")[0])}</span>
        <span class="pname"><b>${esc(x.name)}</b><small title="${esc(x.hint || note)}">${esc(note)}</small></span>
        <span>${pill}</span>
        <span class="score ${x.score == null ? "none" : /满分/.test(x.status) ? "full" : ""}">${x.score == null ? "—" : esc(x.score)}</span></button>`;
    };
    const order = ["作业", "附件作业", "测验", "考试"];
    const rank = (label) => (order.includes(label) ? order.indexOf(label) : order.length);
    const categories = [...new Set(papers.map((x) => x.category))].sort((a, b) => rank(a) - rank(b));
    const n = selected.size;
    body = categories.map((label) => {
      const list = papers.filter((x) => x.category === label), open = list.filter((x) => x.available);
      const all = open.length && open.every((x) => selected.has(x.id));
      return `<div class="section"><h3>${esc(label)}</h3><span class="aside">${open.length} / ${list.length} 份可选</span>
          ${open.length > 1 && !sheet ? `<button class="link" data-pick-all="${esc(label)}">${all ? "取消全选" : "全选"}</button>` : ""}</div>
        <div class="papers">${list.map(row).join("")}</div>`;
    }).join("") || `<div class="empty">这门课没有作业、测验或考试</div>`;
    // While it runs, the player bar below carries the progress and the stop button.
    if (categories.length && !sheet) body += `<div class="dock"><span class="info">${answerBlock ? esc(answerBlock) : n ? `已选 <b>${n}</b> 份` : "勾选要作答的试卷"}</span>
      <button class="btn" data-save ${n && !answerBlock ? "" : "disabled"}>仅生成答案</button>
      <button class="btn primary" data-submit data-confirm="再按一次，交 ${n} 份卷" ${n && !answerBlock ? "" : "disabled"}>AI 作答并交卷</button></div>`;
  }
  page.style.setProperty("--c", inkOf(c));
  if (full) setPage(head + body); else { quiet = true; setPage(head + body); quiet = false; }

  page.querySelectorAll("[data-start]").forEach((el) => (el.onclick = () => startJob({ platform: p.id, course: c.id, type: el.dataset.start })));
  page.querySelectorAll("[data-qa-step]").forEach((el) => (el.onclick = () => {
    const kind = el.dataset.qaStep;
    store.set(QA_LANES[kind].key, qaCount(kind, state.qaRoom[k]) + Number(el.dataset.d));  // qaCount clamps it on the way back
    renderCourse(p, c, tab);
  }));
  const qaStart = $("[data-qa-start]", page);
  if (qaStart) qaStart.onclick = () => startJob({ platform: p.id, course: c.id, type: "qa", limit: qaCount("answer", state.qaRoom[k]) });
  const qaPeers = $("[data-qa-peers]", page);
  if (qaPeers) qaPeers.onclick = async () => {
    const on = !state.qaPeers;
    state.qaPeers = on;  // flip at once; put back if the server says no
    renderCourse(p, c, tab);
    try { state.qaPeers = (await api(`/api/platforms/${p.id}/qa/peers`, { method: "POST", body: { on } })).peers; toast(on ? "已开启站内互答" : "已关闭站内互答"); }
    catch (error) { state.qaPeers = !on; toast(error.message); }
    renderCourse(p, c, tab);
  };
  const qaDraft = $("[data-qa-draft]", page);
  if (qaDraft) qaDraft.onclick = () => draftQuestions(p, c);
  // Edits go straight into the draft, so a background repaint writes back what was typed.
  page.querySelectorAll("[data-qa-edit]").forEach((el) => (el.oninput = () => { state.qaDraft[k].texts[el.dataset.qaEdit] = el.value; }));
  page.querySelectorAll("[data-qa-drop]").forEach((el) => (el.onclick = () => { state.qaDraft[k].texts.splice(Number(el.dataset.qaDrop), 1); renderCourse(p, c, tab); }));
  const qaAsk = $("[data-qa-ask]", page);
  if (qaAsk) qaAsk.onclick = async () => {
    if (await startJob({ platform: p.id, course: c.id, type: "ask", texts: state.qaDraft[k].texts })) { delete state.qaDraft[k]; renderCourse(p, c, tab); }
  };
  page.querySelectorAll("[data-qa-post]").forEach((el) => (el.onclick = () => {
    const id = `${k}:${el.dataset.qaPost}`;  // "kind:at" of that post
    state.qaOpen.has(id) ? state.qaOpen.delete(id) : state.qaOpen.add(id);
    renderCourse(p, c, tab);
  }));
  if (tab === "qa") loadQaPosts(p, c);
  page.querySelectorAll("[data-paper]").forEach((el) => (el.onclick = () => {
    const x = papers.find((y) => String(y.id) === el.dataset.paper);
    if (!x.available || answerBlock) { toast(answerBlock || x.reason || "这份试卷暂不可选"); return; }
    const selected = selectedOf(k);
    selected.has(x.id) ? selected.delete(x.id) : selected.add(x.id);
    renderCourse(p, c, tab);
  }));
  page.querySelectorAll("[data-pick-all]").forEach((el) => (el.onclick = () => {
    const open = papers.filter((x) => x.category === el.dataset.pickAll && x.available), selected = selectedOf(k);
    const all = open.every((x) => selected.has(x.id));
    open.forEach((x) => (all ? selected.delete(x.id) : selected.add(x.id)));
    renderCourse(p, c, tab);
  }));
  const tasks = () => [...selectedOf(k)];
  const save = $("[data-save]", page);
  if (save) save.onclick = () => startJob({ platform: p.id, course: c.id, type: "answer", tasks: tasks(), auto_submit: false });
  const submit = $("[data-submit]", page);
  if (submit) submit.onclick = () => startJob({ platform: p.id, course: c.id, type: "answer", tasks: tasks(), auto_submit: true });
  if (tab === "study") loadUnits(p.id, c.id);
  if (c.shares) loadEarned(p, c);
  if (tab === "answer" && p.features.answer && !papers && !state.paperErrors[k]) loadPapers(p, c);
}

const loadingPapers = new Set(), papersAgain = new Set();
// again: the list on the page is out of date (a paper was handed in), read it once more even if a read is under way.
async function loadPapers(p, c, again = false) {
  const k = key(p.id, c.id);
  if (loadingPapers.has(k)) { if (again) papersAgain.add(k); return; }
  loadingPapers.add(k);
  try {
    const papers = (await api(`/api/platforms/${p.id}/tasks?course=${encodeURIComponent(c.id)}`)).tasks;
    state.papers[k] = papers;
    delete state.paperErrors[k];
    const selected = selectedOf(k);
    if (!again && !selected.size) papers.filter((x) => x.available && !x.done && x.status !== "状态未知").forEach((x) => selected.add(x.id));
  } catch (error) {
    // A failed read is not an empty course: keep it unloaded so a retry or the next login reads it again.
    // A failed reread keeps the list already shown.
    if (!again || !state.papers[k]) state.paperErrors[k] = error.message;
  } finally {
    loadingPapers.delete(k);
    if (papersAgain.delete(k)) loadPapers(p, c, true);
  }
  repaint();
}
// The papers changed on the platform: drop the list, and a read already under way (begun before) runs again.
function stalePapers(pid, cid) {
  const k = key(pid, cid);
  delete state.papers[k];
  if (loadingPapers.has(k)) papersAgain.add(k);
  if (rereads[k]?.timer) { clearTimeout(rereads[k].timer); rereads[k].timer = 0; }  // the next look reads it anyway
}
// A paper handed in mid-run: its score shows without waiting for the whole job. At most one read per 15 s,
// the last one always made: 智慧树 reads its list one knowledge point at a time.
const rereads = {};
function rereadPapers(pid, cid) {
  const k = key(pid, cid), r = (rereads[k] ||= { last: 0, timer: 0 });
  if (r.timer || !state.papers[k]) return;  // not shown yet: the first look reads it afresh anyway
  r.timer = setTimeout(() => {
    r.timer = 0;
    r.last = Date.now();
    if (state.papers[k]) loadPapers({ id: pid }, { id: cid }, true);
  }, Math.max(0, r.last + 15000 - Date.now()));
}

/* ---------------------------------------------------------------- player & focus sheet */

const LOG_LEVEL = { error: ["err", "错误"], warn: ["warn", "提醒"] };
// Lines inside one course's view need not repeat the course name ("课程 · 开始播放：…").
const bare = (text, course) => course && text.startsWith(course) ? text.slice(course.length).replace(/^\s*[·：:]\s*/, "") || text : text;
function logHtml(lines, filter = "all", course = "", live = false) {
  const shown = lines.filter((l) => filter === "all" || (filter === "warn" ? l.level : l.level === "error")).slice(0, 120);
  return shown.map((l, i) => {
    const [cls, lv] = LOG_LEVEL[l.level] || (l.done ? ["ok", "完成"] : ["", ""]);
    const fresh = i === 0 && l.at && Date.now() - l.at < 700 ? " fresh" : "";
    return `<div class="line ${cls}${fresh}"><time>${esc(l.time)}</time><i class="lv" ${lv ? `title="${lv}"` : ""}></i><span class="msg">${esc(bare(l.text, course))}</span></div>`;
  }).join("") || `<div class="line none">${lines.length ? "没有符合条件的日志" : live ? "等待第一条进度…" : "没有日志"}</div>`;
}

function progressOf(run) {
  const all = run.overall?.total > 1 ? run.overall : null, sub = run.sub?.total ? run.sub : null;
  if (all) {
    const pct = Math.min(100, Math.round(((all.done + (sub ? sub.done / sub.total : 0)) / all.total) * 100));
    const unit = (all.unit || "").replace(/试卷|课程/, "");
    return { pct, label: `第 ${Math.min(all.done + 1, all.total)}/${all.total} ${unit}${sub ? ` · ${sub.done}/${sub.total} ${sub.unit || ""}` : ""}`.trim() };
  }
  const part = sub || (run.overall?.total ? run.overall : null);
  if (!part) return { pct: null, label: "" };
  return { pct: Math.min(100, Math.round((part.done / part.total) * 100)), label: `${part.done}/${part.total} ${part.unit || ""}`.trim() };
}

const cellsHtml = (states) => states.map((s) => `<i class="cell ${s}"></i>`).join("");
// The player's strip: fourteen cells around the one being worked on.
function miniCells(states, at) {
  if (!states.length) return "";
  const start = Math.max(0, Math.min(at - 8, states.length - 14));
  return `<span class="mini">${cellsHtml(states.slice(start, start + 14))}</span>`;
}
function recentCells(k) {
  const all = (unitsOf(k) || []).flatMap((ch) => ch.units);
  let at = all.findIndex((u) => u.state === "running");
  if (at < 0) at = all.findIndex((u) => u.state === "queued");
  if (at < 0) at = all.length - 1;
  return miniCells(all.map((u) => u.state), at);
}

/* AI 答题 drawn as an answer sheet: a row per paper, a cell per question. The papers and how each one ended
   come from the job's progress (web/server.py _track: overall.papers, overall.results), the paper being
   answered from its live question count. A job without the paper list names its papers as they come. */
const isAnswer = (j) => jobType(j) === "answer";
const PAPER_TONE = { submitted: "done", saved: "done", preview: "done", success: "done", running: "running",
  error: "error", ai_error: "error", submission_unknown: "error", waiting: "waiting" };
const paperWord = (s) => ({ running: "作答中", queued: "排队" })[s] || STATUS[s] || s || "";
// The step inside the paper: MOOC names it in the question count ("第 4 题 · AI 生成"), 智慧树 in the detail ("<paper> · 保存答案 3/10").
function answerStage(paper, run) {
  const sub = run.sub, detail = run.detail || "";
  if (sub?.name && sub.name !== paper) return sub.name === "已处理题目" ? "AI 作答中" : sub.name;
  if (detail.startsWith(`${paper} · `)) return detail.slice(paper.length + 3);
  return sub?.total ? (sub.done < sub.total ? "AI 作答中" : "整理答案") : "读取试卷";
}
function answerRows(run) {
  const all = run.overall || {}, papers = all.papers || [], results = all.results || [], at = all.done || 0;
  return Array.from({ length: Math.max(all.total || 0, papers.length, results.length) }, (_, i) => {
    const r = results[i], id = papers[i]?.id, name = papers[i]?.name || r?.name;
    if (r) return { id, name, state: r.status, done: r.done || 0, total: r.total || 0 };
    if (i > at) return { id, name: name || `第 ${i + 1} 份`, state: "queued", done: 0, total: 0 };
    // Without the list, the detail names the paper; until the next one's arrives it still names the last.
    const guess = (run.detail || "").replace(/^(准备试卷|正在交卷|复用上一轮答案)：/, "").split(" · ")[0];
    const paper = name || (guess !== results[i - 1]?.name && guess) || `第 ${i + 1} 份`;
    const sub = run.sub?.total ? run.sub : { done: 0, total: 0 };
    return { id, name: paper, state: "running", done: sub.done, total: sub.total, stage: answerStage(paper, run) };
  });
}
const questionStates = (r) => Array.from({ length: r.total }, (_, q) => (q < r.done ? "done" : r.state === "running" && q === r.done ? "running" : ""));
function answerSheetHtml(rows) {
  if (!rows.length) return "";
  const handed = rows.filter((r) => PAPER_TONE[r.state] === "done").length;
  return `<div class="section"><h3>答题卡</h3><span class="aside">${handed}/${rows.length} 份</span></div>
    <div class="grid answers"><div class="chapters">${rows.map((r) => `<div class="chapter ${r.state === "running" ? "current" : ""}">
      <span class="name" title="${esc(r.name)}">${esc(r.name)}</span><span class="cells">${cellsHtml(questionStates(r))}</span>
      <span class="tally">${r.total ? `${r.done}/${r.total}` : ""}</span><span class="state ${PAPER_TONE[r.state] || "stopped"}">${esc(paperWord(r.state))}</span></div>`).join("")}</div></div>`;
}
// What a job is on right now: the paper being answered, else the unit being learnt.
function nowText(job, run) {
  if (isAnswer(job)) return answerRows(run).find((r) => r.state === "running")?.name || "准备中…";
  return run.unit?.name || run.detail || "准备中…";
}
function answerMini(run) {
  const r = answerRows(run).find((x) => x.state === "running");
  return r ? miniCells(questionStates(r), r.done) : "";
}

const player = $(".player"), sheet = $(".sheet");
const LIVE_WORD = { 自动学习: "正在学习", 每日复习: "正在复习", "AI 答题": "正在答题", 问答区答题: "正在回答", 问答区提问: "正在提问" };
const recentlyDone = () => (!state.jobs.length && state.lastDone && Date.now() - state.lastDone.shownAt < 60000 ? state.lastDone : null);

function renderPlayer() {
  const job = focusedJob(), done = recentlyDone();
  if (!job && !done) { player.hidden = true; return; }
  if (player.hidden) { player.hidden = false; player.classList.remove("enter"); void player.offsetWidth; player.classList.add("enter"); }
  if (job) {
    const run = runOf(job.id), waiting = WAIT_WORD[job.state];
    const { pct, label } = progressOf(run);
    const others = state.jobs.length - 1;
    player.style.setProperty("--c", inkOf({ id: job.course }));
    player.classList.remove("ended");
    patch(player, `
      <div class="np"><span class="art">${{ "AI 答题": ICON.pen, 每日复习: ICON.repeat, 问答区答题: ICON.chat, 问答区提问: ICON.chat }[job.title] || ICON.play}</span>
        <span class="what"><small><span class="live">${waiting || LIVE_WORD[job.title] || "进行中"}</span>${esc(job.course_name)}</small>
        <b>${esc(waiting || nowText(job, run))}</b></span></div>
      <div class="scrub"><span class="track ${pct == null ? "unknown" : ""}"><i style="width:${pct ?? 0}%"></i></span><span class="t">${esc(label || clock(elapsed(job)))}</span></div>
      <div class="np_meta">${isAnswer(job) ? answerMini(run) : recentCells(key(job.platform, job.course))}
        ${others ? `<button class="btn" data-go="#/jobs" title="查看全部任务">另有 ${others} 个</button>` : ""}
        ${sheet.classList.contains("open") ? '<button class="btn" data-close>收起 <span class="kbd">F</span></button>' : `<button class="btn" data-open="${job.id}">展开 <span class="kbd">F</span></button>`}<button class="btn danger" data-stop="${job.id}" data-confirm="确认停止" title="⇧S">停止</button></div>`);
  } else {
    player.classList.add("ended");
    patch(player, `
      <div class="np"><span class="art ${done.state === "waiting" ? "waiting" : "still"}">${ICON[done.state] || ICON.stopped}</span>
        <span class="what"><small>${esc(done.title)} · ${esc(done.course_name)} · ${STATE_WORD[done.state] || ""}</small><b>${esc(done.summary || "已结束")}</b></span></div>
      <div class="np_meta"><button class="btn" data-go="#/jobs">查看</button><button class="btn" data-dismiss>关闭</button></div>`);
  }
  if (sheet.classList.contains("open")) renderFocus();
}

function renderFocus() {
  const live = focusedJob();
  const job = live || state.lastDone;
  const body = $(".sheet_body", sheet);
  // Stop and collapse live on the player bar below; the top bar only appears to switch between several jobs.
  $(".sheet_bar", sheet).hidden = state.jobs.length < 2;
  patch($(".sheet_tag", sheet), state.jobs.length > 1
    ? state.jobs.map((j) => `<button class="chip" data-focus="${j.id}" aria-pressed="${j.id === live.id}">${esc(j.title)} · ${esc(j.course_name)}</button>`).join("") : "");
  if (!job) { patch(body, `<div class="focus"><div><div class="clock">—</div><p class="of">现在没有任务。</p></div></div>`); return; }
  // A finished job keeps its last progress, so its answer sheet stays filled in.
  const run = live ? runOf(live.id) : job.run || Object.assign(freshRun(), job.progress);
  const { pct, label } = progressOf(run);
  const k = key(job.platform, job.course);
  body.style.setProperty("--c", inkOf({ id: job.course }));
  const units = learns(job) && unitsOf(k), t = units && tally(units);
  const rows = isAnswer(job) ? answerRows(run) : [], paper = live && rows.find((r) => r.state === "running");
  const grid = units
    ? `<div class="section"><h3>整门课</h3><span class="aside mono">${t.done}/${t.all} · ${Math.round((t.done / (t.all || 1)) * 100)}%</span></div>${gridHtml(k)}`
    : answerSheetHtml(rows);
  const spot = live && learns(job) && spotOf(job, run);
  const chapter = run.unit && (units || []).find((ch) => ch.units.some((u) => u.id === run.unit.key));
  const headline = live
    ? `<div class="clock" data-clock="${live.id}">${clock(elapsed(job))}<small>已用时</small></div>
       <div class="now">${esc(paper?.name || run.unit?.name || bare(run.detail, job.course_name).replace(/ · [\d:]+\/[\d:]+$/, "") || "准备中…")}</div>
       <div class="of">${paper ? `<span class="stage">${esc(paper.stage)}</span> · ` : chapter ? `${esc(chapter.name)} · ` : ""}${esc(job.course_name)}</div>
       ${spot ? `<div class="spot"><div class="track"><i style="width:${spot.pct}%"></i></div><span class="mono">${spot.label}</span></div>`
         : !units ? `<div class="spot"><div class="track ${pct == null ? "unknown" : ""}"><i style="width:${pct ?? 0}%"></i></div><span class="mono">${esc(label)}</span></div>` : ""}`
    : `<div class="clock">${STATE_WORD[job.state] || "结束"}<small>${duration(elapsed(job))}</small></div>
       <div class="now">${esc(job.summary || "")}</div><div class="of">${esc(job.title)} · ${esc(job.course_name)}</div>`;
  patch(body, `<div class="focus"><div>${headline}${grid}</div>
    <div class="log"><div class="log_head"><span class="grow">日志</span>
      ${[["all", "全部"], ["warn", "提醒"], ["err", "错误"]].map(([f, l]) => `<button class="chip" data-filter="${f}" aria-pressed="${state.logFilter === f}">${l}</button>`).join("")}</div>
      <div class="log_body">${logHtml(live ? run.lines : job.lines || [], state.logFilter, job.course_name, Boolean(live))}</div></div></div>`);
  // Long courses: keep the chapter being studied in view inside the grid, once per chapter change.
  const box = $(".focus .chapters", body), current = box && $(".chapter.current", box);
  const mark = current && `${job.id}:${current.querySelector(".name").textContent}`;
  if (current && mark !== state.shownChapter) {
    state.shownChapter = mark;
    box.scrollTo({ top: current.offsetTop - box.clientHeight / 2 + current.offsetHeight / 2, behavior: sheet.classList.contains("open") ? "smooth" : "auto" });
  }
}
// The position inside the current video, from details like "课程 · 视频 · 01:58/19:43" (or seconds, "118/1183").
function spotOf(job, run) {
  const m = (run.detail || "").match(/ · (\d+(?::\d+)*)\/(\d+(?::\d+)*)$/);
  if (!m) return null;
  const secs = (v) => v.split(":").reduce((a, b) => a * 60 + Number(b), 0);
  const at = secs(m[1]), of = secs(m[2]);
  return of ? { pct: Math.min(100, (at / of) * 100), label: `${clock(at)} / ${clock(of)}` } : null;
}
function openSheet(id) {
  if (id) state.focus = id;
  if (!focusedJob() && !state.lastDone) return;
  renderFocus();
  sheet.classList.add("open");
  renderPlayer();
}
function closeSheet() { sheet.classList.remove("open"); renderPlayer(); }

setInterval(() => {
  const byId = (id) => state.jobs.find((j) => j.id === id);
  document.querySelectorAll("[data-clock]").forEach((el) => { const j = byId(el.dataset.clock); if (j) el.firstChild.textContent = clock(elapsed(j)); });
  document.querySelectorAll("[data-elapsed]").forEach((el) => { const j = byId(el.dataset.elapsed); if (j) el.textContent = duration(elapsed(j)); });
  document.querySelectorAll("[data-qa-left]").forEach((el) => { const p = platformOf(el.dataset.qaLeft); if (p && qaLeft(p) > 0) el.textContent = hoursLeft(qaLeft(p)); });
}, 1000);

/* ---------------------------------------------------------------- jobs */

async function startJob(body) {
  try {
    const started = await api("/api/jobs", { method: "POST", body });
    if (started.id) state.focus = started.id;
    // Show it now; the stream's copy may come later (or already came, or the job already ended).
    const job = started.job;
    if (job && !state.jobs.some((j) => j.id === job.id) && !state.history.some((j) => j.id === job.id)) handleEvent({ ...job, type: "job" });
    // The papers stay listed, showing the job's progress on each; they are read again when it ends.
    if (body.type === "answer") state.selected[key(body.platform, body.course)] = new Set();
    return true;
  } catch (error) { toast(error.message); return false; }
}
async function stopJob(id) {
  if (!id) return;
  try { await api("/api/jobs/stop", { method: "POST", body: { id } }); toast("正在停止…"); } catch (error) { toast(error.message); }
}

const STATUS = { success: "完成", skipped: "跳过", error: "出错", submitted: "已交卷", saved: "已保存答案", preview: "已生成答案", paused: "已暂停", ai_error: "AI 出错", submission_unknown: "交卷结果未知", waiting: "等你操作" };
function pushLine(run, text, level = "", done = false) {
  run.lines.unshift({ text, level, done, time: new Date().toTimeString().slice(0, 5), at: Date.now() });
  run.lines.length = Math.min(run.lines.length, 200);
}

// The unit a learning job was on is no longer being learned: it ended, or an administrator paused it or gave its slot away.
function idleUnits(job) {
  if (!learns(job)) return;  // an answering job ending must not unmark the unit a study job is on
  for (const ch of unitsOf(key(job.platform, job.course)) || []) for (const u of ch.units) if (u.state === "running") u.state = job.state === "waiting" ? "waiting" : "queued";
}

function finishUnits(job) {
  idleUnits(job);
  // The platform is the source of truth once the job is over; a waiting job keeps its marks until the user acts.
  if (job.state !== "waiting" && learns(job)) loadUnits(job.platform, job.course, true);
}

let resyncTimer = 0;
function resync() {
  if (!resyncTimer) resyncTimer = setTimeout(() => { resyncTimer = 0; refreshState(true).then(repaint); }, 1000);
}

function handleEvent(event) {
  if (event.type === "job") {
    const at = state.jobs.findIndex((j) => j.id === event.id);
    if (event.state === "running" || WAIT_WORD[event.state]) {
      if (at >= 0) {
        if (state.jobs[at].state === "running" && event.state !== "running") { idleUnits(event); runOf(event.id).unit = null; }
        state.jobs[at] = event;
      }
      else {
        state.jobs.push(event);
        runOf(event.id);
        state.lastDone = null;
        if (learns(event)) loadUnits(event.platform, event.course);
      }
    } else {
      if (at >= 0) state.jobs.splice(at, 1);
      const run = state.runs[event.id];
      delete state.runs[event.id];
      if (state.focus === event.id) state.focus = null;
      state.history = [event, ...state.history.filter((j) => j.id !== event.id)].slice(0, 20);
      state.lastDone = Object.assign({}, event, { shownAt: Date.now(), run });
      toast(`${event.title} · ${event.summary || STATE_WORD[event.state] || "结束"}`);
      finishUnits(event);
      stalePapers(event.platform, event.course);
      delete state.earned[key(event.platform, event.course)];
      delete state.qaPosts[key(event.platform, event.course)];
      delete state.qaRoom[key(event.platform, event.course)];
      loadCourses(event.platform);
      setTimeout(repaint, 61000);
    }
  } else if (event.type === "account") {
    refreshState().then(repaint);
  } else if (event.type === "progress" || event.type === "log") {
    const job = state.jobs.find((j) => j.id === event.job);
    // Progress of a job this page never heard start: its event was lost, so reread the jobs.
    if (!job) { if (!state.history.some((j) => j.id === event.job)) resync(); return; }
    const run = runOf(job.id);
    if (event.type === "log") pushLine(run, event.text, event.level);
    else if (event.kind === "begin") run.overall = { name: event.name, total: event.total || 0, done: 0, unit: event.unit, papers: event.papers || [], results: [] };
    else if (event.kind === "add_total" && run.overall) run.overall.total += event.total || 0;
    else if (event.kind === "detail") run.detail = event.name;
    else if (event.kind === "unit") {
      const u = findUnit(key(job.platform, job.course), event.key);
      if (u) u.state = event.status;
      if (u && event.status === "done") state.stamped = { id: u.id, at: Date.now() };
      if (event.status === "running") run.unit = { name: event.name, key: event.key };
      else if (run.unit?.key === event.key) run.unit = null;  // mirrors _track: the bar then shows run.detail
    } else if (event.kind === "result") {
      if (run.overall) {
        (run.overall.results ||= []).push({ name: event.name, status: event.status, done: run.sub?.done || 0, total: run.sub?.total || 0 });
        run.overall.done += 1;
        run.sub = null;
      }
      pushLine(run, `${event.name} · ${STATUS[event.status] || event.status || ""}`, event.status === "error" || event.status === "ai_error" ? "error" : event.status === "waiting" ? "warn" : "", true);
      if (isAnswer(job) && ["submitted", "submission_unknown"].includes(event.status)) rereadPapers(job.platform, job.course);
    } else if (event.kind === "resources" || event.kind === "questions") {
      run.sub = { name: event.name, done: event.completed || 0, total: event.total || 0, unit: event.unit === "项资源" ? "项" : event.unit };
    }
  }
  repaint();
}

let paintQueued = false, lastPaint = 0;
function repaint() {
  if (paintQueued || drag) return;  // a drag repaints once it drops
  paintQueued = true;
  setTimeout(() => requestAnimationFrame(() => {
    paintQueued = false;
    lastPaint = performance.now();
    renderSidebar();
    renderPlayer();
    const [, name, a, b, c] = parseHash(location.hash);
    quiet = true;
    try {
      if (name === "jobs") VIEWS.jobs(a);
      else if (name === "home") VIEWS.home();
      else if (name === "me") VIEWS.me();
      // Signed in elsewhere; a fresh scan is done once the ticket is back.
      else if (name === "login" && platformOf(a)?.logged_in && !(b === "again" && rescannable(platformOf(a)))
               && (state.loginToken.cancelled || state.loginToken.qr !== a)) go(homeOf(platformOf(a)));
      else if (name === "course") {
        const p = platformOf(a), course = courseOf(a, decodeURIComponent(b || ""));
        if (p && course) renderCourse(p, course, courseTab(course, c));
        else if (p) VIEWS.course(a, decodeURIComponent(b || ""), c);
      }
    } finally { quiet = false; }
  }), Math.max(0, lastPaint + 250 - performance.now()));
}

function connectEvents() {
  if (MOCK) { import("./mock.js").then((m) => m.subscribe(handleEvent)); return; }
  let source = null, heard = 0, opened = false;
  const open = () => {
    heard = Date.now();  // a stream that never opens is retried too
    source?.close();
    source = new EventSource(session.mode === "hosted" ? "/api/events" : `/api/events?t=${encodeURIComponent(TOKEN)}`);
    source.onmessage = (message) => { heard = Date.now(); const event = JSON.parse(message.data); if (event.type !== "ping") handleEvent(event); };
    // Events sent while the stream was down (or the tab was frozen) are lost; catch up from the server.
    source.onopen = () => { heard = Date.now(); if (opened) refreshState(true).then(repaint); opened = true; };
  };
  open();
  // The server pings every 15 s. A stream silent for 40 s is dead even if the browser hasn't noticed.
  setInterval(() => { if (Date.now() - heard > 40000) open(); }, 10000);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") refreshState().then(repaint); });
}

/* ---------------------------------------------------------------- login */

async function qrLogin(pid) {
  state.loginToken.cancelled = true;
  // qr: this tab's own scan is under way, so the account event it sends leaves the finish to afterLogin.
  const token = (state.loginToken = { cancelled: false, qr: pid });
  const box = $(".qr", page), status = $("[data-status]", page);
  const say = (title, text) => { status.innerHTML = `<b>${esc(title)}</b><p>${esc(text)}</p>`; };
  const setImage = (src) => { box.innerHTML = `<img alt="登录二维码" src="${src}">`; };
  let started, wait = 1500;
  try { started = await api(`/api/platforms/${pid}/login`, { method: "POST" }); setImage(started.qr); }
  catch (error) { token.cancelled = true; say("获取二维码失败", error.message); return; }
  while (!token.cancelled) {
    await sleep(wait);
    if (token.cancelled || !box.isConnected) return;
    let result;
    // This page's own code: another tab or device showing a code must not swap it out.
    try { result = await api(`/api/platforms/${pid}/login?id=${encodeURIComponent(started.id || "")}`); } catch (error) { say("网络异常", error.message); continue; }
    if (result.qr) setImage(result.qr);
    // Scanned: the tap on the phone is seconds away, so look more often and go in as soon as it lands.
    wait = result.status === "scanned" ? 500 : 1500;
    if (result.status === "scanned") say("已扫码", "请在手机上确认登录。");
    else if (result.status === "refreshed") say("二维码已刷新", "请扫新的二维码。");
    else if (result.status === "failed") { token.cancelled = true; say("登录未完成", result.message || "请点击刷新二维码重试。"); return; }
    else if (result.status === "done") { token.cancelled = true; await afterLogin(pid); return; }
  }
}

async function browserLogin(pid, resume = false) {
  state.loginToken.cancelled = true;
  const token = (state.loginToken = { cancelled: false });
  const status = $("[data-status]", page), button = $("[data-start-login]", page);
  const say = (title, text) => { status.innerHTML = `<b>${esc(title)}</b><p>${esc(text)}</p>`; };
  if (!resume) {
    button.disabled = true;
    // Opened synchronously inside the click so popup blockers allow it. Phones (WeChat has no tabs at all) go in
    // this page instead; the callback page sends them back to #/login/<pid>, which resumes below.
    const tab = session.mode === "hosted" && !TOUCH ? window.open("", "_blank") : null;
    try {
      // No tab of its own (a phone, or a blocked popup): this page goes to the SSO and the callback must bring it back.
      const started = await api(`/api/platforms/${pid}/login`, { method: "POST", body: { here: !tab } });
      if (started.open && tab) tab.location = started.open; else if (started.open) { location.href = started.open; return; } else tab?.close();
      say("等待职教云登录", started.message);
    } catch (error) { tab?.close(); say("无法开始登录", error.message); button.disabled = false; return; }
  }
  while (!token.cancelled) {
    if (!resume) await sleep(1500);
    if (token.cancelled || !status.isConnected) return;
    let result;
    try { result = await api(`/api/platforms/${pid}/login`); }
    catch (error) { if (resume) return; say("网络异常", error.message); continue; }  // resuming: no login was started
    if (resume && result.status === "waiting") { say("等待职教云登录", "登录完成后自动回到这里"); button.textContent = "重新打开登录页"; }
    resume = false;
    if (result.status === "failed") { say("登录未完成", result.message); button.disabled = false; button.textContent = "重新打开登录页"; return; }
    if (result.status === "done") { token.cancelled = true; await afterLogin(pid); return; }
  }
}

// Papers, units and picks read under the old login (or while it had expired) are dropped.
function forgetPlatform(pid) {
  for (const cache of [state.papers, state.paperErrors, state.units, state.selected]) {
    for (const k of Object.keys(cache)) if (k.startsWith(`${pid}:`)) delete cache[k];
  }
  for (const k of earnedErrors) if (k.startsWith(`${pid}:`)) earnedErrors.delete(k);
  for (const k of earnedRetry) if (k.startsWith(`${pid}:`)) earnedRetry.delete(k);
}

async function afterLogin(pid) {
  const back = state.returnTo;  // read first: a repaint may route away while this waits
  state.returnTo = "";
  toast("登录成功");
  forgetPlatform(pid);
  await refreshState();
  // Go in now: the platform takes a second or more for the course list, and the page fills in when it lands.
  const courses = state.courses[pid] ? null : loadCourses(pid);
  if (back) { go(back); return; }
  switchPlatform(pid);
  // The desktop opens the first course once the list is in (as boot does), unless the user went elsewhere.
  if (courses && !PHONE.matches) {
    await courses;
    if (state.current === pid && location.hash === "#/home") go(homeOf(platformOf(pid)));
  }
}

// One read per platform at a time: a login seen by this tab and by the server's account event asks twice.
const coursesLoading = {};
function loadCourses(pid) {
  return (coursesLoading[pid] ||= readCourses(pid).finally(() => delete coursesLoading[pid]));
}
async function readCourses(pid) {
  try { state.courses[pid] = (await api(`/api/platforms/${pid}/courses`)).courses; }
  catch (error) { toast(error.message); state.courses[pid] = state.courses[pid] || []; }
  repaint();
  const p = platformOf(pid);
  // Warm every course's papers and units so a later click finds them ready.
  for (const c of state.courses[pid] || []) {
    if (p?.features.answer) inBackground(() => (state.papers[key(pid, c.id)] ? null : loadPapers(p, c)));
    inBackground(() => loadUnits(pid, c.id));
  }
}

// The platform answers these reads in seconds to tens of seconds. Run at most two at a time,
// so a click never waits behind them for one of the browser's few connections to this server.
const background = { running: 0, waiting: [] };
function inBackground(task) {
  background.waiting.push(task);
  pumpBackground();
}
function pumpBackground() {
  while (background.running < 2 && background.waiting.length) {
    const task = background.waiting.shift();
    background.running += 1;
    Promise.resolve().then(task).catch(() => {}).finally(() => { background.running -= 1; pumpBackground(); });
  }
}

// catchUp: events may have been missed, so also reread the grids the live jobs are filling.
async function refreshState(catchUp = false) {
  try {
    const data = await api("/api/state");
    // The server was updated while this page stayed open, or the browser restored the page from its cache:
    // load the new one. Once per build, so a proxy still serving the old page can't loop; never mid-typing.
    if (BUILD && data.build && data.build !== BUILD && !document.activeElement?.matches("input, textarea, select")
        && sessionStorage.getItem("studia-build") !== data.build) {
      sessionStorage.setItem("studia-build", data.build);
      location.reload();
      return;
    }
    // Before the first read nothing was signed in, and boot loads the courses itself.
    const before = state.platforms.length ? new Set(state.platforms.filter((p) => p.logged_in).map((p) => p.id)) : null;
    state.platforms = data.platforms;
    state.history = data.history || [];
    state.lastRun = data.last || {};
    state.jobLimit = data.job_limit || state.jobLimit;
    state.zhsParallel = Boolean(data.zhs_parallel);
    const live = data.jobs || [];
    for (const job of live) {
      // The server's tally is the truth for a page opened mid-run or one that missed events while away.
      state.runs[job.id] = Object.assign(freshRun(), job.progress || {}, { lines: job.lines || [] });
      if (learns(job) && (catchUp || !state.jobs.some((j) => j.id === job.id))) loadUnits(job.platform, job.course, catchUp);
    }
    // Jobs that ended while we were away: drop them and refresh what they changed.
    for (const gone of state.jobs.filter((j) => !live.some((x) => x.id === j.id))) {
      delete state.runs[gone.id];
      const ended = state.history.find((h) => h.id === gone.id);
      if (ended) finishUnits(ended);
      stalePapers(gone.platform, gone.course);
    }
    state.jobs = live;
    for (const job of live) markLive(key(job.platform, job.course));
    for (const p of state.platforms) if (!p.logged_in) { delete state.courses[p.id]; forgetPlatform(p.id); }
    // Signed in from another tab or device: this tab has no course list for it yet. Not awaited: readCourses
    // repaints when it lands, and a scan's page goes in without waiting on it.
    if (before) for (const p of state.platforms) if (p.logged_in && !before.has(p.id)) loadCourses(p.id);
    watchTicket();
  } catch (error) { toast(error.message); }
  renderSidebar();
}
// Repaint as the Q&A ticket enters its last stretch, and read the state again once it runs out.
let ticketTimer = 0;
function watchTicket() {
  clearTimeout(ticketTimer);
  const ends = Math.min(...state.platforms.map((p) => p.rescan_at || Infinity)), now = Date.now() / 1000;
  if (ends === Infinity) return;
  const soon = ends - QA_SOON > now;
  // Past the end by this clock but not yet by the server's: ask again in a while, not in a loop.
  ticketTimer = setTimeout(() => (soon ? (repaint(), watchTicket()) : refreshState().then(repaint)),
    (soon ? ends - QA_SOON - now : Math.max(ends - now, 30)) * 1000 + 1000);
}

/* ---------------------------------------------------------------- palette */

const overlay = $("[data-overlay]");
const finderInput = $("input", overlay);
const finderList = $(".rows", overlay);
let finderItems = [], finderIndex = 0;
function openFinder() { overlay.classList.add("open"); finderInput.value = ""; finderIndex = 0; paintFinder(); finderInput.focus(); }
function closeFinder() { overlay.classList.remove("open"); }
function paintFinder() {
  const q = finderInput.value.trim().toLowerCase();
  const match = (text) => !q || text.toLowerCase().includes(q);
  const pages = [["#/jobs", ICON.pulse, "任务"], ["#/settings", ICON.gear, "设置"], ...(session.user?.role === "admin" ? [["#/admin", ICON.shield, "管理后台"]] : []),
    ...state.platforms.map((p) => [homeOf(p), `<span class="dot ${p.id}"></span>`, `切换到 ${p.name}`])]
    .filter(([, , label]) => match(label)).map(([hash, icon, label]) => ({ hash, icon, label, meta: "页面" }));
  const courses = state.platforms.flatMap((p) => (state.courses[p.id] || []).filter((c) => match(c.name))
    .map((c) => ({ hash: `#/course/${p.id}/${c.id}`, icon: ring(c.progress, COLOR[p.id]), label: c.name, meta: `${p.short} 课程` })));
  const papers = q ? state.platforms.flatMap((p) => (state.courses[p.id] || []).flatMap((c) => (state.papers[key(p.id, c.id)] || [])
    .filter((x) => match(x.name)).map((x) => ({ hash: `#/course/${p.id}/${c.id}/answer`, icon: `<span class="stamp ${STAMP[x.category] || ""}">${esc((x.category || "作")[0])}</span>`, label: x.name, meta: c.name })))).slice(0, 8) : [];
  finderItems = [...courses, ...pages, ...papers];
  finderIndex = Math.min(finderIndex, Math.max(0, finderItems.length - 1));
  let i = 0;
  const groups = [courses, pages, papers].filter((g) => g.length).map((g) => g.map(() => {
    const it = finderItems[i];
    const html = `<button class="prow" data-i="${i}" aria-selected="${i === finderIndex}">${it.icon}<span>${esc(it.label)}</span><span class="meta">${esc(it.meta)}</span></button>`;
    i += 1;
    return html;
  }).join(""));
  finderList.innerHTML = groups.join('<div class="psep"></div>') || `<div class="prow" style="color:var(--text-4)">没有找到</div>`;
  finderList.querySelectorAll("[data-i]").forEach((el) => (el.onclick = () => { closeFinder(); go(finderItems[el.dataset.i].hash); }));
  finderList.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
}
finderInput.addEventListener("input", () => { finderIndex = 0; paintFinder(); });
overlay.addEventListener("click", (event) => { if (event.target === overlay) closeFinder(); });

/* ---------------------------------------------------------------- global input */

document.addEventListener("click", (event) => {
  const t = event.target;
  if (!t.closest("[data-job-menu]")) closeJobMenu();  // its items still act below: the hidden menu keeps them
  if (state.meOpen && !t.closest("[data-me]")) { state.meOpen = false; renderSidebar(); }
  if (t.closest("[data-me]")) { state.meOpen = !state.meOpen; renderSidebar(); return; }
  if (t.closest("[data-signout]")) { signOut(); return; }
  const sw = t.closest("[data-switch]"); if (sw) { switchPlatform(sw.dataset.switch); return; }
  const target = t.closest("[data-go]"); if (target) { closeSheet(); go(target.dataset.go); }
  if (t.closest("[data-find]")) openFinder();
  if (t.closest("[data-toggle-theme]")) toggleTheme();
  // Opening turns this very button into 收起; stop here so the same click doesn't close it again.
  const open = t.closest("[data-open]"); if (open) { openSheet(open.dataset.open); return; }
  if (t.closest("[data-close]")) closeSheet();
  const stop = t.closest("[data-stop]"); if (stop) stopJob(stop.dataset.stop);
  const menuButton = t.closest("[data-job-menu]");
  if (menuButton) { if (jobMenu.hidden || jobMenu.dataset.for !== menuButton.dataset.jobMenu) { openJobMenu(menuButton); jobMenu.dataset.for = menuButton.dataset.jobMenu; } else closeJobMenu(); }
  const act = t.closest("[data-job-act]");
  if (act) {
    const { id, jobAct: action, to } = act.dataset, owner = act.dataset.owner ?? act.closest("[data-board]")?.dataset.owner ?? "";
    jobAct(owner, id, action, to != null ? { to: Number(to) } : {});
  }
  const fold = t.closest("[data-paused-fold]");
  if (fold) { const k = fold.dataset.pausedFold; state.pausedOpen.has(k) ? state.pausedOpen.delete(k) : state.pausedOpen.add(k); repaint(); }
  const focus = t.closest("[data-focus]"); if (focus) { state.focus = focus.dataset.focus; renderFocus(); renderPlayer(); }
  if (t.closest("[data-dismiss]")) { state.lastDone = null; repaint(); }
  const filter = t.closest("[data-filter]"); if (filter) { state.logFilter = filter.dataset.filter; renderFocus(); }
  const papersRetry = t.closest("[data-papers-retry]");
  if (papersRetry) {
    const [pid, ...rest] = papersRetry.dataset.papersRetry.split(":"), p = platformOf(pid), c = courseOf(pid, rest.join(":"));
    delete state.paperErrors[papersRetry.dataset.papersRetry];
    if (p && c) loadPapers(p, c);
    repaint();
  }
  const retry = t.closest("[data-units-retry]");
  if (retry) { const [pid, ...rest] = retry.dataset.unitsRetry.split(":"); delete state.units[retry.dataset.unitsRetry]; loadUnits(pid, rest.join(":")); repaint(); }
});

window.addEventListener("keydown", (event) => {
  const mod = event.metaKey || event.ctrlKey;
  if (event.key === "Escape" && !jobMenu.hidden) { closeJobMenu(); return; }
  if (overlay.classList.contains("open")) {
    if (event.key === "Escape" || (mod && event.key.toLowerCase() === "k")) { event.preventDefault(); closeFinder(); }
    else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      finderIndex = (finderIndex + (event.key === "ArrowDown" ? 1 : -1) + finderItems.length) % Math.max(1, finderItems.length);
      paintFinder();
    } else if (event.key === "Enter" && finderItems[finderIndex]) { closeFinder(); go(finderItems[finderIndex].hash); }
    return;
  }
  if (mod && ["1", "2", "3"].includes(event.key) && state.platforms[event.key - 1]) { event.preventDefault(); switchPlatform(state.platforms[event.key - 1].id); return; }
  if (mod && event.key.toLowerCase() === "k") { event.preventDefault(); openFinder(); return; }
  if (mod && event.key.toLowerCase() === "j") { event.preventDefault(); toggleTheme(); return; }
  if (mod && event.key === ",") { event.preventDefault(); go("#/settings"); return; }
  if (event.key === "Escape" && state.meOpen) { state.meOpen = false; renderSidebar(); return; }
  if (event.key === "Escape") { closeSheet(); return; }
  if (mod || event.altKey || event.target.closest("input, textarea, select") || document.body.classList.contains("signed-out")) return;
  if (event.key === "S" && event.shiftKey) { stopJob(focusedJob()?.id); return; }
  if (event.key === "f") { if (sheet.classList.contains("open")) closeSheet(); else openSheet(); return; }
  if (event.key === "s") $('[data-start]:not([disabled])', page)?.click();
});

/* ---------------------------------------------------------------- router */

const parseHash = (hash) => (hash || "").match(/^#\/(\w+)(?:\/([^/]+))?(?:\/([^/]+))?(?:\/([^/]+))?/) || [];

function route(event) {
  const [, name, a, b, c] = parseHash(location.hash);
  if (name === "reset" && event) { location.reload(); return; }  // a mailed link opened over this tab: boot shows its page
  if (!name || name === "all") { go(homeOf(currentPlatform())); return; }
  if (name === "settings" && a === "admin") { go(`#/admin${b ? `/${b}` : ""}`); return; }  // old links
  if (name === "admin" && a === "jobs") { go("#/jobs/all"); return; }
  if ((name === "course" || name === "login") && platformOf(a) && state.current !== a) { state.current = a; store.set("studia-platform", a); }
  if (name !== "login") state.loginToken.cancelled = true;
  if (name !== "login") state.returnTo = "";
  else if (b === "again" && event?.oldURL) state.returnTo = new URL(event.oldURL).hash;
  if (name === "course") {
    const k = key(a, decodeURIComponent(b || ""));
    earnedErrors.delete(k);
    if (loadingEarned.has(k)) earnedRetry.add(k);
    // Papers or units that failed to read (often while warming up in the background) are read again on
    // entering the course or switching its tab, as a browser refresh did; a repaint does not retry.
    delete state.paperErrors[k];
    if (state.units[k]?.error) delete state.units[k];
  }
  state.adminEdit = null;
  state.view = name === "course" ? `#/course/${a}/${b}` : name === "login" ? `#/login/${a}` : `#/${name}`;
  page.style.removeProperty("--c");
  renderSidebar();
  renderPlayer();
  scroller.scrollTop = 0;
  if (name === "admin") { if (session.user?.role === "admin") VIEWS.admin(false, a); else go("#/settings"); }
  else if (name === "jobs") { VIEWS.jobs(a); if (a === "all" && session.user?.role === "admin") loadSiteJobs(); }
  else if (name === "settings") { state.accountEdit = state.passwordSent = null; VIEWS.settings(a); }
  else if (name === "course") VIEWS.course(a, decodeURIComponent(b || ""), c);
  else if (name === "login") VIEWS.login(a, b === "again");
  else if (VIEWS[name]) VIEWS[name]();
  else go(homeOf(currentPlatform()));
}
window.addEventListener("hashchange", route);
window.addEventListener("hashchange", closeJobMenu);
scroller.addEventListener("scroll", closeJobMenu, { passive: true });
window.addEventListener("resize", closeJobMenu);

// The sign-in page's left half: a course grid quietly studying itself.
function authGrid() {
  const rows = [9, 7, 11, 8, 10, 6];
  let n = 0;
  return rows.map((count) => `<span class="cells">${Array.from({ length: count }, () => {
    n += 1;
    const state = n % 13 === 0 ? "skipped" : n < 34 ? "done" : "queued";
    return `<i class="cell ${state}"></i>`;
  }).join("")}</span>`).join("");
}
let authTimer = 0;
function animateAuthGrid(box) {
  clearInterval(authTimer);
  authTimer = setInterval(() => {
    if (!box.isConnected) { clearInterval(authTimer); return; }
    const running = $(".auth_grid .cell.running", box);
    if (running) running.className = "cell done";
    const next = $(".auth_grid .cell.queued", box);
    if (next) next.className = "cell running";
    else box.querySelectorAll(".auth_grid .cell.done").forEach((c, i) => { if (i > 20) c.className = "cell queued"; });
  }, 900);
}

const AUTH = {
  login: { title: "登录", lead: "欢迎回来。", button: "登录", switch: ["还没有账号？", "注册", "register"] },
  register: { title: "注册", lead: "", button: "注册并登录", switch: ["已经有账号？", "去登录", "login"] },
  setup: { title: "创建管理员", lead: "设置码在服务器日志里（docker compose logs studia）。", button: "创建并进入" },
  forgot: { title: "找回密码", lead: "链接会发到绑定的邮箱。", button: "发送链接", switch: ["想起来了？", "去登录", "login"] },
  reset: { title: "设置新密码", lead: "", button: "保存并登录" },
};
function showAuth(mode = "login") {
  document.body.classList.add("signed-out");
  let box = $(".auth");
  const switching = Boolean(box);  // 登录 ↔ 注册 ↔ 找回密码: the form changes, the page around it does not
  if (!box) { box = document.createElement("div"); box.className = "auth"; document.body.appendChild(box); }
  const rules = session.register || { open: false };
  if (mode === "register" && !rules.open) mode = "login";  // sign-ups closed since this page was opened
  const text = { ...AUTH[mode] };
  if (mode === "login") text.switch = rules.open ? ["还没有账号？", rules.invite ? "用邀请码注册" : "注册", "register"] : null;
  const field = (name, label, attrs) => `<label class="auth_field"><span>${label}</span>${attrs.includes("password")
    ? `<span class="pw"><input name="${name}" ${attrs}><button type="button" class="pw_eye" data-reveal aria-label="显示密码">显示</button></span>`
    : `<input name="${name}" ${attrs}>`}</label>`;
  box.innerHTML = `
    <section class="auth_art" aria-hidden="true">
      <div class="brand"><img class="mark" src="icon.svg" alt=""><b>Studia</b></div>
      <div class="auth_pitch"><h1>课程、视频、作业，<br>一格一格替你涂满。</h1>
        <p>自动学完没学的单元，AI 帮你作答试卷。</p></div>
      <div class="auth_grid">${authGrid()}</div>
      <p class="auth_foot">MOOC · 智慧树</p>
    </section>
    <section class="auth_side">
      <form class="auth_card" data-auth novalidate>
        <h2>${text.title}</h2><p class="auth_lead">${esc(text.lead)}</p>
        ${mode === "setup" ? field("code", "设置码", 'required autocomplete="off" autocapitalize="characters" placeholder="例如 2593-2D9E-D41F"') : ""}
        ${mode === "register" && rules.invite ? field("invite", "邀请码", 'required autocomplete="off" autocapitalize="characters" placeholder="例如 3F2A-91BC-04DE"') : ""}
        ${mode === "forgot" ? field("login", "用户名或邮箱", 'required autocomplete="username" autocapitalize="off"') : ""}
        ${mode === "reset" || mode === "forgot" ? "" : field("username", mode === "setup" ? "管理员用户名" : "用户名", `required autocomplete="username" autocapitalize="off" ${mode === "login" ? "" : 'minlength="2" maxlength="32"'}`)}
        ${mode === "register" && rules.email ? `${field("email", "邮箱", 'type="email" required autocomplete="email" autocapitalize="off"')}
          <label class="auth_field"><span>验证码</span><span class="pw"><input name="code" required inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="6 位数字">
            <button type="button" class="pw_eye code_send" data-send-code>发送验证码</button></span></label>` : ""}
        ${mode === "forgot" ? "" : field("password", mode === "reset" ? "新密码" : "密码", `type="password" required autocomplete="${mode === "login" ? "current-password" : "new-password"}" ${mode === "login" ? "" : 'minlength="8" placeholder="至少 8 位"'}`)}
        ${mode === "login" ? '<p class="auth_forgot"><button type="button" class="link" data-auth-mode="forgot">忘记密码？</button></p>' : ""}
        ${mode === "setup" || mode === "reset" ? field("again", "再输一次密码", 'type="password" required autocomplete="new-password" minlength="8"') : ""}
        <p class="auth_error" role="alert"></p>
        <button class="btn primary auth_submit">${esc(text.button)}</button>
        ${text.switch ? `<p class="auth_note">${text.switch[0]}<button type="button" class="link" data-auth-mode="${text.switch[2]}">${text.switch[1]}</button></p>` : ""}
      </form>
    </section>`;
  animateAuthGrid(box);
  if (switching) rise([...$(".auth_card", box).children], 6);
  box.querySelectorAll("[data-auth-mode]").forEach((el) => (el.onclick = () => showAuth(el.dataset.authMode)));
  box.querySelectorAll("[data-reveal]").forEach((el) => (el.onclick = () => {
    const input = el.previousElementSibling, show = input.type === "password";
    input.type = show ? "text" : "password";
    el.textContent = show ? "隐藏" : "显示";
    el.setAttribute("aria-label", show ? "隐藏密码" : "显示密码");
  }));
  const form = $("[data-auth]", box);
  const error = $(".auth_error", form);
  const send = $("[data-send-code]", form);
  if (send) send.onclick = async () => {
    const email = form.elements.email;
    if (!email.value.trim() || !email.checkValidity()) { error.textContent = email.value.trim() ? "邮箱格式不正确" : "请填写邮箱"; email.focus(); return; }
    send.disabled = true;
    send.textContent = "发送中…";
    try {
      await api("/api/auth/register/code", { method: "POST", body: { email: email.value.trim() } });
      $(".auth_lead", form).textContent = `验证码已发到 ${email.value.trim()}，10 分钟内有效。`;
      form.elements.code.focus();
      let left = 60;
      const tick = () => {
        if (!send.isConnected) return;
        send.textContent = left ? `${left} 秒后重发` : "重新发送";
        send.disabled = left > 0;
        if (left--) setTimeout(tick, 1000);
      };
      tick();
    } catch (failure) {
      error.textContent = failure.message;
      send.disabled = false;
      send.textContent = "发送验证码";
    }
  };
  if (!TOUCH) form.querySelector("input").focus();  // on a phone this would pop the keyboard over the page
  form.oninput = () => { error.textContent = ""; };
  form.onsubmit = async (event) => {
    event.preventDefault();
    const missing = [...form.querySelectorAll("input")].find((input) => !input.checkValidity());
    if (missing) {
      const label = missing.closest("label").firstElementChild.textContent;
      error.textContent = missing.validity.tooShort ? `${label}至少 ${missing.minLength} 位`
        : missing.validity.typeMismatch ? `${label}格式不正确` : `请填写${label}`;
      missing.focus();
      return;
    }
    const body = Object.fromEntries(new FormData(form));
    if ((mode === "setup" || mode === "reset") && body.password !== body.again) { error.textContent = "两次输入的密码不一致"; return; }
    if (mode === "reset") body.token = RESET;
    const button = $(".auth_submit", form);
    button.disabled = true;
    button.textContent = "请稍候…";
    try {
      await api(`/api/auth/${mode}`, { method: "POST", body });
      if (mode === "forgot") {
        $(".auth_lead", form).textContent = "如果这个账号绑定了邮箱，链接已经发过去了。";
        button.disabled = false;
        button.textContent = "重新发送";
        return;
      }
      if (mode === "reset") { location.replace(location.pathname); return; }  // drop the used token from the address
      location.reload();
    } catch (failure) {
      error.textContent = failure.message;
      button.disabled = false;
      button.textContent = text.button;
    }
  };
}

async function signOut() {
  try { await api("/api/auth/logout", { method: "POST" }); } catch { /* already gone */ }
  location.reload();
}

async function loadMe() {
  try {
    const me = await api("/api/auth/me");
    Object.assign(session, { user: me.user, csrf: me.csrf, mail: Boolean(me.mail) });
    return true;
  } catch { return false; }
}

(async function boot() {
  let setup = false;
  if (!MOCK) { try { ({ mode: session.mode, setup, register: session.register = null } = await api("/api/mode")); } catch { /* old server: local */ } }
  if (MOCK && params.has("auth")) { showAuth(params.get("auth") || "login"); return; }
  if (MOCK && params.has("hosted")) session.mode = "hosted";  // ?mock&hosted previews what a hosted site shows
  if (setup) { showAuth("setup"); return; }
  if (RESET && session.mode === "hosted") { showAuth("reset"); return; }  // the link mailed for a new password
  if (session.mode === "hosted" && !(await loadMe())) { showAuth(); return; }
  await refreshState();
  connectEvents();
  promptEmail();
  state.platforms.filter((p) => p.logged_in).forEach((p) => loadCourses(p.id));
  if (!location.hash && currentPlatform()?.logged_in) {
    state.view = "#/home";
    renderSidebar();
    VIEWS.home();
    await loadCourses(currentPlatform().id);
    if (location.hash) return;  // navigation already rendered the page the user chose
  }
  route();
})();
