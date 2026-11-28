const params = new URLSearchParams(location.search);
const MOCK = params.has("mock");
// Which build of the page this is: the server writes it into the script URL (none in ?mock).
const BUILD = new URL(import.meta.url).searchParams.get("v");
// A mailed password link: /#/reset/<token>. The token stays in the fragment, so it never reaches a server log.
const RESET = location.hash.match(/^#\/reset\/([\w-]+)$/)?.[1] || "";
const TOKEN = params.get("t") || sessionStorage.getItem("studia-token") || "";
const OAUTH_NOTICE = params.get("oauth") || "";
if (params.get("t") || OAUTH_NOTICE) {
  if (params.get("t")) sessionStorage.setItem("studia-token", TOKEN);
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
  user: svg('<circle cx="8" cy="5.5" r="2.7"/><path d="M3 13.5c.8-2.6 2.8-3.8 5-3.8s4.2 1.2 5 3.8"/>', 15),
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
const session = { mode: "local", user: null, csrf: "", register: null, oauth: null };
let mockModule = null;
async function api(path, { method = "GET", body } = {}) {
  if (MOCK) {
    mockModule = mockModule || (await import("./mock.js"));
    return mockModule.request(path, method, body);
  }
  const headers = body ? { "Content-Type": "application/json" } : {};
  if (session.mode === "hosted") { if (method !== "GET") headers["X-Studia-CSRF"] = session.csrf; }
  else headers["X-Studia-Token"] = TOKEN;
  let response;
  // fetch() rejects with the browser's own English ("Failed to fetch", Safari's "Load failed"): say it in Chinese.
  try { response = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined, credentials: "same-origin" }); }
  catch { conn.lost(); throw new Error(navigator.onLine === false ? "网络已断开，连上后再试" : "连不上 Studia，请检查网络后再试"); }
  const data = await response.json().catch(() => ({}));
  if (response.status === 401 && !path.startsWith("/api/auth/") && path !== "/api/mode") {
    if (session.mode === "hosted") loadMe().then((ok) => { if (!ok) showAuth(); else refreshState(); });
    else if (path !== "/api/state") refreshState();
  }
  // A proxy's own error page (no JSON) while the server restarts or is down.
  if (!response.ok) throw Object.assign(new Error(data.error || ([502, 503, 504].includes(response.status)
    ? `Studia 暂时连不上，可能正在重启，稍后再试（${response.status}）` : `请求失败（${response.status}）`)), { status: response.status });
  return data;
}

const state = {
  platforms: [], courses: {}, papers: {}, paperErrors: {}, units: {}, selected: {}, earned: {}, qaDraft: {}, qaPosts: {}, qaRoom: {}, qaPeers: null, qaOpen: new Set(),
  jobs: [], siteJobs: 0, runs: {}, focus: null, jobLimit: 4, zhsParallel: false, issueReport: true, history: [], view: "", loginToken: { cancelled: true }, returnTo: "", lastDone: null,
  current: store.get("studia-platform", ""), meOpen: false, adminTab: "people", logFilter: "all", accountEdit: null, passwordSent: null, adminEdit: null, pausedOpen: new Set(),
  adminLists: {}, adminOpen: null, reportOpen: null, shownIssueJobs: new Set(), pendingIssues: [],
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
// Says so when the live connection is down (the server restarting, a phone off the network), so progress that has
// stopped moving isn't mistaken for a stuck task. Blips under a few seconds stay silent; coming back is said once.
const conn = (() => {
  const el = document.createElement("div");
  Object.assign(el, { className: "conn", hidden: true });
  el.setAttribute("role", "status");
  document.body.appendChild(el);
  let lostAt = 0, wait = 0, fade = 0;
  const say = (text, back) => {
    clearTimeout(fade);
    el.getAnimations?.().forEach((a) => a.cancel());  // a fade-out still running would hide it again
    const fresh = el.hidden;
    el.innerHTML = `<span>${esc(text)}</span>${back ? "" : '<i aria-hidden="true"></i>'}`;
    el.classList.toggle("back", back);
    el.hidden = false;
    if (fresh) moves(el, filled(), { duration: 380 });
  };
  const hide = () => {
    const out = moves(el, filled().reverse(), { duration: 300, easing: EASE_IO });
    if (out) out.onfinish = () => { el.hidden = true; }; else el.hidden = true;
  };
  const down = () => (navigator.onLine === false ? "网络已断开 · 恢复后自动重连" : "连接中断 · 正在重连…");
  addEventListener("offline", () => { if (lostAt && !el.hidden) say(down(), false); });
  return {
    lost(now = false) {
      if (document.body.classList.contains("signed-out")) return;
      if (!lostAt) lostAt = Date.now();
      clearTimeout(wait);
      wait = setTimeout(() => { if (lostAt) say(down(), false); }, now ? 0 : 4000);
    },
    back() {
      if (!lostAt) return;
      lostAt = 0;
      clearTimeout(wait);
      if (el.hidden || el.classList.contains("back")) return;
      say("已重新连接", true);
      fade = setTimeout(hide, 1600);
    },
  };
})();
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
const QA_TTL = 8 * 3600;
const QA_SOON = 90 * 60;
const QA_RING_C = 2 * Math.PI * 14;
const qaLeft = (p) => (p.rescan_at ? p.rescan_at - Date.now() / 1000 : null);
const qaSoon = (p) => !p.rescan && qaLeft(p) !== null && qaLeft(p) < QA_SOON;
const rescannable = (p) => p.rescan || Boolean(p.rescan_at);
function hoursLeft(sec) {
  const min = Math.max(1, Math.ceil(sec / 60));
  return min < 60 ? `${min} 分钟` : `${Math.floor(min / 60)} 小时${min % 60 ? ` ${min % 60} 分` : ""}`;
}
function qaClockParts(sec) {
  const total = Math.max(0, Math.floor(sec || 0));
  const h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60;
  return {
    total,
    text: `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`,
    ratio: Math.max(0, Math.min(1, total / QA_TTL)),
    hDeg: ((h % 12) + m / 60) * 30,
    mDeg: (m + s / 60) * 6,
    sDeg: s * 6,
  };
}
function qaUntil(ts) {
  const d = new Date(ts * 1000);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
const QA_DIAL_TICKS = Array.from({ length: 12 }, (_, i) => {
  const major = i % 3 === 0;
  return `<line x1="18" y1="${major ? 5.2 : 5.8}" x2="18" y2="${major ? 7.4 : 7.2}" class="qa_tick${major ? " major" : ""}" transform="rotate(${i * 30} 18 18)"/>`;
}).join("");
function qaClock(p) {
  const left = qaLeft(p);
  const lapsed = Boolean(p.rescan) || (left !== null && left <= 0);
  if (!lapsed && !(left > 0)) return "";
  const soon = !lapsed && qaSoon(p);
  const parts = qaClockParts(lapsed ? 0 : left);
  const offset = (QA_RING_C * (1 - parts.ratio)).toFixed(2);
  const stateClass = lapsed ? " lapsed" : soon ? " soon" : "";
  const sub = lapsed ? "问答区已失效" : soon ? `即将到期 · 至 ${qaUntil(p.rescan_at)}` : `有效至 ${qaUntil(p.rescan_at)}`;
  const title = lapsed ? "登录中心票据已失效，重新扫码后问答区可用 8 小时"
    : `问答区有效倒计时（有效期 8 小时，至 ${qaUntil(p.rescan_at)}）`;
  return `<div class="qa_clock${stateClass}" data-qa-clock="${p.id}" title="${title}" aria-label="问答区剩余 ${parts.text}，${sub}">
    <svg class="qa_dial" viewBox="0 0 36 36" width="36" height="36" aria-hidden="true">
      <circle class="qa_face" cx="18" cy="18" r="16.5"/>
      <circle class="qa_track" cx="18" cy="18" r="14"/>
      <circle class="qa_arc" data-qa-arc cx="18" cy="18" r="14" stroke-dasharray="${QA_RING_C.toFixed(2)}" stroke-dashoffset="${offset}" transform="rotate(-90 18 18)"/>
      ${QA_DIAL_TICKS}
      <line class="qa_hand qa_hand_h" data-qa-h x1="18" y1="18" x2="18" y2="11.4" transform="rotate(${parts.hDeg.toFixed(1)} 18 18)"/>
      <line class="qa_hand qa_hand_m" data-qa-m x1="18" y1="18" x2="18" y2="8.8" transform="rotate(${parts.mDeg.toFixed(1)} 18 18)"/>
      ${lapsed ? "" : `<line class="qa_hand qa_hand_s" data-qa-s x1="18" y1="20.4" x2="18" y2="7.8" transform="rotate(${parts.sDeg.toFixed(1)} 18 18)"/>`}
      <circle class="qa_pin" cx="18" cy="18" r="1.5"/>
    </svg>
    <div class="qa_clock_meta">
      <span class="qa_clock_num mono" data-qa-clock-num>${parts.text}</span>
      <span class="qa_clock_sub">${sub}</span>
    </div>
  </div>`;
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
  const site = session.user?.role === "admin" ? siteCount() : 0;
  if (site) return `<span class="live">${state.jobs.length + site} 个进行中</span>`;
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
  patch($(".side_foot"), `<button class="me" data-me aria-haspopup="menu" aria-expanded="${state.meOpen}" aria-current="${under("#/me", "#/profile", "#/settings", "#/admin")}">
      <span class="avatar">${esc(initial)}</span><span class="who"><b>${esc(name)}</b><small>${role}</small></span>
      <span class="chev">${ICON.updown}</span></button>
    ${state.meOpen ? `<div class="menu me_menu" role="menu">
      ${me ? `<button class="menu_row" role="menuitem" data-go="#/profile">${ICON.user}<span class="grow">个人资料</span></button>` : ""}
      <button class="menu_row" role="menuitem" data-go="#/settings">${ICON.gear}<span class="grow">设置</span><span class="kbd">⌘,</span></button>
      ${admin ? `<button class="menu_row" role="menuitem" data-go="#/admin">${ICON.shield}<span class="grow">管理后台</span></button>` : ""}
      <div class="psep"></div>
      <button class="menu_row" role="menuitem" data-toggle-theme>${night ? ICON.sun : ICON.moon}<span class="grow">${night ? "日间模式" : "夜读模式"}</span><span class="kbd">⌘J</span></button>
      ${me ? `<div class="psep"></div><button class="menu_row danger" role="menuitem" data-signout>${ICON.logout}<span class="grow">退出 Studia</span></button>` : ""}
    </div>` : ""}`);

  // Phones: three tabs at the bottom; a page one level down (a course, a settings tab) gets a back
  // button in the top bar instead of the logo. The platform switch only sits on the overview.
  const back = under("#/course") ? ["#/home", "课程"] : under("#/profile", "#/settings", "#/admin") ? ["#/me", "我的"] : null;
  patch($(".mbar"), back ? `<button class="mback" data-go="${back[0]}">${ICON.back}<span>${back[1]}</span></button><span class="grow"></span>`
    : `<img class="mark" src="icon.svg" alt=""><b>Studia</b><span class="grow"></span>${under("#/home", "#/login") ? platforms : ""}`);
  const jobsBadge = state.jobs.length + (admin ? siteCount() : 0);
  patch($(".mtabs"), `
    <button class="mtab" data-go="#/home" aria-current="${under("#/home", "#/course", "#/login")}">${ICON.cells}<span>课程</span></button>
    <button class="mtab" data-go="#/jobs" aria-current="${view === "#/jobs"}">${ICON.pulse}<span>任务</span>${jobsBadge ? `<b class="badge">${jobsBadge}</b>` : ""}</button>
    <button class="mtab" data-go="#/me" aria-current="${under("#/me", "#/profile", "#/settings", "#/admin")}"><span class="avatar">${esc(initial)}</span><span>我的</span></button>`);
  placeInk();
}
// The account menu fades down before it is gone; a second close while it fades does nothing.
function closeMe() {
  const menu = $(".me_menu");
  if (menu?.getAnimations().some((a) => a.id === "out")) return;
  const done = () => { state.meOpen = false; renderSidebar(); };
  const out = menu && moves(menu, [{ clipPath: "inset(-30px)" }, { clipPath: "inset(calc(100% + 30px) -30px -30px -30px)", transform: "translateY(4px)" }],
    { duration: 260, easing: EASE_IO, id: "out", fill: "forwards" });
  if (out) out.onfinish = done; else done();
}
// The sidebar's highlight and the phone tab bar's mark sit under the current item and glide when it changes. Placed
// first without a transition (inked is off), so a page load does not slide them in from the top.
function placeInk() {
  const nav = $(".nav"), on = nav.querySelector('.nav_item[aria-current="true"]');
  if (on) {
    nav.style.setProperty("--ink-y", `${on.offsetTop}px`);
    nav.style.setProperty("--ink-h", `${on.offsetHeight}px`);
  }
  const tabs = $(".mtabs"), i = [...tabs.querySelectorAll(".mtab")].findIndex((t) => t.getAttribute("aria-current") === "true");
  if (i >= 0) tabs.style.setProperty("--i", i);
  for (const [el, shown] of [[nav, Boolean(on)], [tabs, i >= 0]]) {
    if (shown && !el.classList.contains("inked")) void el.offsetWidth;  // settle the position before it can animate
    el.classList.toggle("inked", shown);
  }
}


/* ---------------------------------------------------------------- page helpers */

const page = $(".page");
// Bars that stay on screen while the document scrolls. Their heights, kept in CSS variables, let the job sheet, the
// answer dock and scrolled-to rows clear them (a phone's bars change height with its safe areas and font size).
const bars = { "--mbar-h": $(".mbar"), "--mtabs-h": $(".mtabs"), "--player-h": $(".player") };
const barSizes = new ResizeObserver(() => {
  for (const [name, el] of Object.entries(bars)) document.documentElement.style.setProperty(name, `${el.getClientRects().length ? el.offsetHeight : 0}px`);
});
Object.values(bars).forEach((el) => barSizes.observe(el));
// Live progress repaints several times a second. Patch the existing DOM instead of
// replacing it, so buttons, running animations and a finger mid-tap survive the update.
/* ---------------------------------------------------------------- motion
   Studia moves like a scanner and a pen over an answer sheet: blocks are swept in from the top (a clip passing down
   them), rows are filled in from the left like bubbles, digits roll up like a counter, and things travelling from one
   place to another go decisively. Web Animations (el.animate) rather than classes: nothing to clean up, and a later
   repaint cannot restart them. The clips reach 24px past the edges so rings and shadows are not cut. */
const STILL = matchMedia("(prefers-reduced-motion: reduce)");
const EASE = "cubic-bezier(.16, 1, .3, 1)", EASE_IO = "cubic-bezier(.65, .05, 0, 1)";  // the stylesheet's --ease, --ease-io
// The stylesheet's --pace scales every length here too, so one number sets the tempo of the whole site. The admin's
// speed (管理后台 → 站点, 1.0× = the stylesheet's tempo) divides it: at 1.5× everything takes two thirds as long.
const BASE_PACE = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--pace")) || 1;
let PACE = BASE_PACE;
function applySpeed(speed) {
  if (!(speed > 0)) return;
  PACE = BASE_PACE / speed;
  document.documentElement.style.setProperty("--pace", PACE.toFixed(3));
}
// Six cells filled in turn at the tempo just set, so a nudge can be felt without leaving the page.
function demoSpeed() {
  page.querySelectorAll(".pace_demo .cell").forEach((c, i) => moves(c, filled(-1), { duration: 420, easing: EASE_IO, delay: i * 70, fill: "backwards" }));
}
const moves = (el, frames, options) => {
  if (STILL.matches || !el.animate) return null;
  const o = { duration: 420, easing: EASE, ...options };
  return el.animate(frames, { ...o, duration: o.duration * PACE, delay: (o.delay || 0) * PACE });
};
// Swept in from the top edge down, settling `lift` pixels.
const scanned = (lift = 10) => [{ clipPath: "inset(-24px -24px calc(100% + 24px) -24px)", transform: `translateY(${lift}px)` }, { clipPath: "inset(-24px)", transform: "none" }];
// Filled in from one side: -1 from the left, 1 from the right.
const filled = (side = -1) => [{ clipPath: side < 0 ? "inset(-24px calc(100% + 24px) -24px -24px)" : "inset(-24px -24px -24px calc(100% + 24px))",
  transform: `translateX(${side * 14}px)` }, { clipPath: "inset(-24px)", transform: "none" }];
// The same sweep without repainting: a cover in the colour behind the block slides off it (transform only, so the
// GPU runs it) while the block moves into place. Clipping the block instead looks identical, but phones repaint a
// clipped block on every frame (Safari always, Chrome too), which is what made page changes stutter there.
// dir: "down" (scanned: top edge first) or -1 / 1 (filled from the left / right). Blocks in fixed panels or in a
// box that scrolls on its own keep the clip: a cover placed on the page would not follow them.
const wipes = document.body.appendChild(Object.assign(document.createElement("div"), { className: "wipes" }));
let wipeSize = "";
const pageExtent = () => `${page.offsetWidth}x${page.offsetHeight}`;
function behind(el) {
  for (let p = el.parentElement; p; p = p.parentElement) {
    const color = getComputedStyle(p).backgroundColor;
    if (!/^(transparent|rgba\(.*,\s*0\))$/.test(color)) return color;
  }
  return getComputedStyle(document.body).backgroundColor;
}
function ownScroll(el) {
  for (let p = el.parentElement; p && p !== page; p = p.parentElement) {
    const style = getComputedStyle(p);
    if (/auto|scroll/.test(style.overflowY + style.overflowX) || style.position === "fixed" || style.position === "sticky") return true;
  }
  return false;
}
// A cover over where its block sits (less the slide the block is doing), plus the strip it slides in from; never past
// the page's edges, so it can't make the page scroll sideways.
// A few pixels round it too: shadows, outlines and glyphs reach a little past a block's box (the gaps between blocks
// are wider than that).
function place(box) {
  const { el, way, lift, from } = box.sweep, down = way === "down", r = el.getBoundingClientRect();
  const m = new DOMMatrixReadOnly(getComputedStyle(el).transform);
  let x = r.left - (m.m41 - from.m41) + scrollX - 4, y = r.top - (m.m42 - from.m42) + scrollY - 3, w = r.width + 8, h = r.height + 9;
  if (down) { y += Math.min(lift, 0); h += Math.abs(lift); } else { w += 14; if (way < 0) x -= 14; }
  const docW = document.documentElement.clientWidth, docH = document.documentElement.scrollHeight;
  const left = Math.max(0, x), top = Math.max(0, y);
  Object.assign(box.style, { left: `${left}px`, top: `${top}px`, width: `${Math.max(0, Math.min(x + w, docW) - left)}px`,
    height: `${Math.max(0, Math.min(y + h, docH) - top)}px` });
}
function sweep(el, dir, { lift = 10, ...options } = {}) {
  if (STILL.matches || !el.animate) return null;
  const down = dir === "down", r = el.getBoundingClientRect();
  if (!r.width || !r.height || !page.contains(el) || ownScroll(el)) return moves(el, down ? scanned(lift) : filled(dir), options);
  const box = document.createElement("div");
  box.sweep = { el, way: dir, lift, from: new DOMMatrixReadOnly(getComputedStyle(el).transform) };
  const cover = box.appendChild(document.createElement("i"));
  cover.style.background = behind(el);
  place(box);
  wipes.appendChild(box);
  wipeSize = pageExtent();
  const a = moves(cover, [{ transform: "none" }, { transform: down ? "translateY(101%)" : `translateX(${dir < 0 ? 101 : -101}%)` }], { ...options, fill: "both" });
  moves(el, [{ transform: down ? `translateY(${lift}px)` : `translateX(${dir * 14}px)` }, { transform: "none" }], options);
  const done = () => box.remove();
  a.finished.then(done, done);
  return a;
}
// A new page ends the covers still running; data arriving mid-sweep (the page changing size) moves each cover along
// with its block, before that frame is painted.
function clearWipes() { for (const box of [...wipes.children]) box.firstChild.getAnimations().forEach((a) => a.finish()); }
new ResizeObserver(() => {
  if (!wipes.firstChild || pageExtent() === wipeSize) return;
  wipeSize = pageExtent();
  for (const box of [...wipes.children]) box.sweep.el.isConnected ? place(box) : box.firstChild.getAnimations().forEach((a) => a.finish());
}).observe(page);

// The loading sheet index.html paints before anything else (while the script, the styles and the first reads arrive):
// swept off top to bottom, like a scanner pass, once a real page (not a placeholder) or the sign-in form is drawn.
const bootSheet = document.querySelector(".boot");
function unboot() {
  if (!bootSheet?.isConnected || bootSheet.dataset.out) return;
  bootSheet.dataset.out = "1";
  bootSheet.style.pointerEvents = "none";
  const out = moves(bootSheet, [{ clipPath: "inset(0 0 0 0)" }, { clipPath: "inset(100% 0 0 0)" }], { duration: 560, easing: EASE_IO, fill: "forwards" });
  if (out) out.onfinish = () => bootSheet.remove(); else bootSheet.remove();
}
setTimeout(unboot, 8000);  // whatever went wrong, the page behind is never held back for long
let born = [], rolled = new Set();  // what a patch inserted (to fade in) and the numbers it changed (to roll)

function patch(target, html, motion = true) {
  const fresh = document.createElement("template");
  fresh.innerHTML = html;
  const before = motion && !STILL.matches ? keyedRects(target) : null;
  born = [];
  rolled = new Set();
  patchChildren(target, fresh.content);
  // A count that changed (可作答 3 → 2, a progress digit) rolls up into place.
  for (const el of rolled) moves(el, el.closest(".digits") ? [{ transform: "translateY(115%)" }, { transform: "none" }]
    : [{ opacity: 0, transform: "translateY(45%)" }, { opacity: 1, transform: "none" }], { duration: 600, easing: EASE_IO });
  if (!before) return;
  // A row that moved (a job leaving the queue for a slot, a list re-sorted) slides from where it was;
  // one that is new fades in. A few at most, so a page of fresh rows does not ripple for long.
  for (const el of target.querySelectorAll("[data-key]")) {
    const was = before.get(el.dataset.key);
    if (!was || born.includes(el)) continue;
    const now = el.getBoundingClientRect(), dx = was.left - now.left, dy = was.top - now.top;
    if (Math.abs(dx) + Math.abs(dy) > 1) moves(el, [{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "none" }], { duration: 560, easing: EASE_IO });
  }
  born.slice(0, 24).forEach((el, i) => sweep(el, -1, { duration: 520, easing: EASE_IO, delay: Math.min(i, 8) * 40, fill: "backwards" }));
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
    else if (at.nodeValue !== node.nodeValue) {
      at.nodeValue = node.nodeValue;
      if (from.matches?.(".digits span, .pen_num")) rolled.add(from);
    }
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
// Blocks rise into place one after another (fill "backwards": one waiting its turn is not shown early). A block below
// the fold waits, paused at its start, and rises once it scrolls into view; cards in a grid go one by one.
const revealer = "IntersectionObserver" in window ? new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting) { revealer.unobserve(e.target); e.target.reveal?.play(); }
}, { rootMargin: "0px 0px -6% 0px" }) : null;
function rise(els, lift = 14) {
  revealer?.disconnect();
  clearWipes();
  let turn = 0;
  for (const el of els.flatMap((x) => (x.matches(".course_cards, .acts") ? [...x.children] : [x]))) {
    const below = revealer && el.getBoundingClientRect().top > innerHeight;
    if (!below) { sweep(el, "down", { lift, duration: 680, easing: EASE_IO, delay: Math.min(turn++, 6) * 55, fill: "backwards" }); continue; }
    const hold = moves(el, [{ opacity: 0 }, { opacity: 0 }], { duration: 1, fill: "forwards" });
    if (!hold) continue;
    el.reveal = { play: () => { hold.cancel(); sweep(el, "down", { lift: lift + 6, duration: 760, easing: EASE_IO }); } };
    revealer.observe(el);
  }
}

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
    // The title above the tabs was drawn anew but is the same: its own entrance (corners locking on, digits rolling)
    // is already over as far as the reader is concerned.
    for (const el of [...page.children].slice(0, [...page.children].indexOf(now.bar))) el.getAnimations({ subtree: true }).forEach((a) => a.finish());
    const marker = now.bar.classList.contains("seg") ? "::before" : "::after";
    try {
      moves(now.on, [{ transform: `translateX(${was.rect.left - now.rect.left}px) scaleX(${was.rect.width / now.rect.width})` }, { transform: "none" }],
        { pseudoElement: marker, duration: 520, easing: EASE_IO });
    } catch { /* no pseudo-element animations: the marker just moves */ }
    clearWipes();
    pageBody(now).forEach((el, i) => sweep(el, side, { duration: 560, easing: EASE_IO, delay: Math.min(i, 4) * 40, fill: "backwards" }));
  } else if (!quiet) rise([...page.children]);
  else if (loading && !page.querySelector(".loading")) rise(pageBody(tabBar()), 10);
  if (!page.querySelector(".loading")) unboot();
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

const ADMIN_TABS = [["people", "用户"], ["invites", "邀请码"], ["reports", "适配上报"], ["oauth", "OAuth"], ["site", "站点"], ["logs", "日志"]];
/* 用户 and 邀请码 grow with the site, so each is a list that pages, filters and searches. What a list is
   showing stays while the console is open; the page size is remembered in the browser. */
const PAGE_SIZES = [10, 20, 50, 100];
let adminData = null;  // the lists last read, so searching, filtering and paging redraw without asking again
const adminCache = {};  // each tab's lists as last read: a tab opened again shows them at once, then reads them anew
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
const SETTINGS_TABS = [["models", "AI 模型"], ["study", "偏好"]];
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
  const out = moves(jobMenu, [{ clipPath: "inset(-30px)" }, { clipPath: "inset(-30px -30px calc(100% + 30px) -30px)", transform: "translateY(-4px)" }],
    { duration: 240, easing: EASE_IO, id: "out" });
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
  if (event.clientY < 72 || event.clientY > innerHeight - 72) scrollBy(0, event.clientY < 72 ? -14 : 14);
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
const siteCount = () => state.siteJobs || 0;
let siteTimer = 0;
async function loadSiteJobs() {
  clearTimeout(siteTimer);
  const here = () => location.hash === "#/jobs/all";
  // Refresh every 5 seconds while the list is open; paused while hidden or a stop button is armed.
  if (!document.hidden && !document.querySelector(".armed")) {
    try {
      state.sitePeople = (await api("/api/admin/jobs")).people;
      state.siteJobs = state.sitePeople.reduce((sum, u) => sum + u.jobs.length, 0);
    } catch (error) { toast(error.message); state.sitePeople = state.sitePeople || []; }
    renderSidebar();
    if (here()) repaint();
  }
  if (here()) siteTimer = setTimeout(loadSiteJobs, 5000);
}
const VIEWS = {
  async admin(refresh = false, tab = state.adminTab) {
    tab = ADMIN_TABS.some(([k]) => k === tab) ? tab : "people";
    state.adminTab = tab;
    const head = pageHead("管理后台", "", "#/admin", ADMIN_TABS, tab);
    // Show the tab at once: its lists as last read if it was open before (read again below), or a placeholder they fill.
    // Switching tabs inside the console swaps the content in place; arriving from elsewhere animates.
    const inConsole = state.view === "#/admin" && Boolean(page.querySelector('[data-go^="#/admin/"]'));
    const cached = !refresh && adminCache[tab];
    if (!refresh) {
      for (const list of Object.values(state.adminLists)) list.open = null;  // arriving: no filter menu left open
      if (!cached) {
        quiet = inConsole;
        setPage(`${head}<div class="empty loading">正在读取…</div>`);
        quiet = false;
      }
    }
    const need = { people: ["users"], invites: ["invites", "users"], reports: ["reports"], oauth: ["settings"], site: ["settings", "memory"], logs: [] }[tab];
    let data;
    // "local": the same lists drawn again (a search, a filter, another page), without reading them again.
    if (refresh === "local" && adminData?.tab === tab) data = adminData.data;
    else if (cached) data = cached;
    else {
      try { data = Object.fromEntries(await Promise.all(need.map(async (x) => [x, await api(`/api/admin/${x}`)]))); }
      catch (error) { if (!refresh) setPage(`${head}<div class="empty">${esc(error.message)}</div>`); return; }
      adminCache[tab] = data;
    }
    adminData = { tab, data };
    if (state.view !== "#/admin" || state.adminTab !== tab) return;
    const users = data.users?.users || [];
    let body = "";
    if (tab === "people") {
      const list = adminList("people"), q = list.q.trim().toLowerCase();
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
      const found = users.filter((u) => !q || `${u.username} ${u.email || ""} ${u.linuxdo?.username || ""}`.toLowerCase().includes(q))
        .sort((a, b) => rank(a) - rank(b) || seen(b) - seen(a));
      const { rows, counts } = facetFilter("people", found, FACETS);
      const userRow = (u) => `<div class="model user_row ${state.adminOpen === u.id ? "open" : ""}" data-key="${esc(u.id)}" data-user-row="${esc(u.id)}">
            <span class="avatar big">${esc(u.username.slice(0, 1).toUpperCase())}</span>
            <span class="m1"><b>${esc(u.username)}</b>${u.role === "admin" ? '<span class="pill blue">管理员</span>' : ""}${u.linuxdo ? '<span class="pill">Linux DO</span>' : ""}${u.disabled ? '<span class="pill red">已停用</span>' : ""}${u.max_jobs ? `<span class="pill">同时 ${u.max_jobs} 个</span>` : ""}
            <small class="sans">${u.jobs?.some((j) => j.state === "running") ? "学习中" : u.jobs?.some((j) => j.state === "queued") ? "排队中" : u.jobs?.length ? "已暂停" : u.last_login ? `上次在线 ${ago(u.last_login)}` : "还没登录过"}${u.email ? ` · ${esc(u.email)}` : ""}${u.linuxdo ? ` · Linux DO @${esc(u.linuxdo.username || u.linuxdo.id)}${u.linuxdo.trust_level != null ? ` (${u.linuxdo.trust_level} 级)` : ""}` : ""}</small></span>
            <button class="btn small row_more" data-user-more="${esc(u.id)}" aria-expanded="${state.adminOpen === u.id}">管理</button>
            <span class="row_btns">${u.jobs?.length ? `<button class="btn small danger" data-stop-user="${u.id}" data-confirm="确认全部停止">停止全部任务</button>` : ""}
              <button class="btn small" data-row-edit="limit" data-uid="${u.id}">任务上限</button>
              <button class="btn small" data-row-edit="password" data-uid="${u.id}">${u.has_password === false ? "设置密码" : "重置密码"}</button>
              ${u.id === session.user.id ? "" : u.disabled ? `<button class="btn small" data-enable="${u.id}">启用</button>` : `<button class="btn small danger" data-disable="${u.id}" data-confirm="确认停用">停用</button>`}</span></div>`;
      body = `${listTools("people", "搜索用户名、邮箱或 Linux DO", FACETS, counts)}
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
    } else if (tab === "reports") {
      const list = adminList("reports"), q = list.q.trim().toLowerCase();
      const reports = data.reports?.reports || [];
      const enabled = data.reports?.enabled !== false;
      const STATUS_META = { open: ["wait", "待处理"], resolved: ["blue", "已处理"], ignored: ["", "已忽略"] };
      const PLAT_NAME = { mooc: "MOOC", zhs: "智慧树" };
      const FACETS = [
        ["status", "状态", [["open", "待处理"], ["resolved", "已处理"], ["ignored", "已忽略"]].map(([k, name]) => [k, name, (r) => r.status === k])],
        ["platform", "平台", [["mooc", "MOOC"], ["zhs", "智慧树"]].map(([k, name]) => [k, name, (r) => r.platform === k])],
        ["job", "任务", [["study", "自动学习", (r) => r.job_kind === "study"], ["answer", "AI 答题", (r) => r.job_kind === "answer"],
          ["other", "其他", (r) => r.job_kind !== "study" && r.job_kind !== "answer"]]],
      ];
      const matchText = (r) => [
        r.course_name, r.course_id, r.course_type, r.course_kind, r.headline, r.platform, PLAT_NAME[r.platform],
        ...(r.reporters || []).map((x) => `${x.username} ${x.note || ""}`),
        ...((r.payload?.items) || []).map((x) => `${x.label} ${x.name} ${x.kind} ${x.detail} ${x.fields}`),
      ].join(" ").toLowerCase();
      const found = reports.filter((r) => !q || matchText(r).includes(q));
      const { rows, counts } = facetFilter("reports", found, FACETS);
      const reportDetail = (r) => {
        const p = r.payload || {};
        const items = p.items || [];
        const logs = p.logs || [];
        const shares = p.shares ? Object.entries(p.shares).filter(([, v]) => v > 0).map(([k, v]) => `${SHARE_LABEL[k] || k} ${v} 分`).join(" · ") : "";
        const metaLine = [
          `平台：${PLAT_NAME[r.platform] || r.platform}`,
          r.course_type ? `课型：${r.course_type}` : (r.course_kind ? `课型：${r.course_kind}` : ""),
          r.course_id ? `课程 ID：${r.course_id}` : "",
          p.progress != null ? `进度：${p.progress}%` : "",
          shares ? `考核：${shares}` : "",
        ].filter(Boolean).join(" · ");
        return `<div class="report_detail" data-report-detail="${esc(r.id)}">
          <div class="report_meta">${esc(metaLine)}</div>
          <div class="report_subhead">检测到的问题（${items.length} 项）</div>
          <div class="issue_list">${items.map((it) => `<div class="issue_item">
            <div class="issue_item_head"><span class="pill ${ISSUE_PILL[it.bucket] || ""}">${esc(it.label || it.code)}</span>
              <b>${esc(it.name || "未命名")}</b>${it.kind ? `<code class="issue_kind">${esc(it.kind)}</code>` : ""}</div>
            ${it.detail ? `<p class="issue_desc">${esc(it.detail)}</p>` : ""}
            ${it.fields ? `<code class="issue_fields">${esc(it.fields)}</code>` : ""}</div>`).join("") || '<p class="issue_desc">无条目明细</p>'}</div>
          ${(r.reporters || []).length ? `<div class="report_subhead">上报成员（${r.reporter_count} 人 · 共 ${r.report_count} 次）</div>
            <div class="report_people">${r.reporters.slice(0, 10).map((u) => `<div class="report_person"><b>${esc(u.username)}</b>
              <span class="when">${u.at ? ago(u.at) : ""}</span>${u.note ? `<span class="report_note">${esc(u.note)}</span>` : ""}</div>`).join("")}</div>` : ""}
          ${logs.length ? `<div class="report_subhead">任务日志片段</div>
            <div class="report_logs">${logs.slice(0, 12).map((l) => `<div class="line ${l.level === "error" ? "err" : l.level === "warn" ? "warn" : ""}">
              <time>${esc(l.time || "")}</time><span class="lv"></span><span class="msg">${esc(l.text || "")}</span></div>`).join("")}</div>` : ""}
          <div class="report_actions">
            <button class="btn small" data-report-copy="${esc(r.id)}">复制诊断 Markdown</button>
            ${r.status !== "resolved" ? `<button class="btn small primary" data-report-status="${esc(r.id)}" data-to-status="resolved">标记已处理</button>` : ""}
            ${r.status !== "open" ? `<button class="btn small" data-report-status="${esc(r.id)}" data-to-status="open">重新打开</button>` : ""}
            ${r.status !== "ignored" ? `<button class="btn small" data-report-status="${esc(r.id)}" data-to-status="ignored">忽略</button>` : ""}
            <span class="grow"></span>
            <button class="btn small danger" data-report-delete="${esc(r.id)}" data-confirm="确认删除">删除</button>
          </div></div>`;
      };
      const reportRow = (r) => {
        const open = state.reportOpen === r.id;
        const [pillCls, pillWord] = STATUS_META[r.status] || ["", r.status];
        return `<div class="report_entry ${open ? "open" : ""}" data-key="${esc(r.id)}">
          <div class="model report_row">
            <span class="plat ${esc(r.platform)}">${INITIAL[r.platform] || "?"}</span>
            <span class="m1"><b>${esc(r.course_name)}</b><span class="pill ${pillCls}">${pillWord}</span><span class="pill">${r.reporter_count} 人 · ${r.report_count} 次</span>
              <small class="sans">${esc(r.headline)} · ${esc(LABEL[r.job_kind] || r.job_kind)}${r.course_type ? ` · ${esc(r.course_type)}` : ""} · ${ago(r.updated)}</small></span>
            <span class="row_btns">
              <button class="btn small" data-report-expand="${esc(r.id)}" aria-expanded="${open}">${open ? "收起" : "详情"}</button>
              <button class="btn small" data-report-copy="${esc(r.id)}">复制</button>
              ${r.status !== "resolved"
                ? `<button class="btn small primary" data-report-status="${esc(r.id)}" data-to-status="resolved">已处理</button>`
                : `<button class="btn small" data-report-status="${esc(r.id)}" data-to-status="open">重开</button>`}
            </span></div>
          ${open ? reportDetail(r) : ""}</div>`;
      };
      body = `${listTools("reports", "搜索课程名、问题类型、字段或上报人", FACETS, counts)}
        ${enabled ? "" : '<p class="list_note">当前已关闭适配检查与上报，新任务不会弹窗收集反馈。<button class="link" data-go="#/admin/site">去开启</button></p>'}
        <div class="models">${pageOf("reports", rows).map(reportRow).join("")
          || `<div class="model plain"><span class="m1"><small class="sans">${reports.length ? "没有符合条件的上报记录" : "还没有收到课程适配上报"}</small></span></div>`}</div>
        ${pagerHtml("reports", rows.length, "条")}`;
    } else if (tab === "oauth") {
      const oauth = data.settings.oauth || {
        enabled: false,
        callback_url: `${location.origin}/auth/linuxdo/callback`,
        icon_url: `${location.origin}/icon-512.png`,
        linuxdo: null,
      };
      const ld = oauth.linuxdo;
      const oauthChoice = (value, label, attrs = "") =>
        `<button class="btn small" data-oauth-enabled="${value ? 1 : 0}" aria-pressed="${Boolean(oauth.enabled) === value}" ${attrs}>${label}</button>`;
      const ldRow = ld
        ? `<div class="model plain"><span class="m1"><b>Linux DO</b><span class="pill blue">已配置</span>
            <small>Client ID：${esc(ld.client_id)} · Secret：${esc(ld.secret_hint)}${ld.api_base ? ` · 反代：${esc(ld.api_base)}` : ""}</small></span>
          <span class="row_btns"><button class="btn small" data-linuxdo-edit>编辑</button>
            <button class="btn small danger" data-linuxdo-clear data-confirm="确认清除">清除</button></span></div>`
        : `<div class="model plain"><span class="m1"><b>Linux DO</b><small class="sans">未配置 · 在 connect.linux.do/dash/sso 创建应用后填写凭证</small></span>
          <span class="row_btns"><button class="btn small primary" data-linuxdo-edit>配置</button></span></div>`;
      body = `<div class="section"><h2>OAuth 总开关</h2></div>
        <div class="models"><div class="model plain stepper_row"><span class="m1"><b>允许 OAuth 登录</b>
          <small class="sans">${!ld ? "先配置下方 Linux DO 应用" : oauth.enabled ? "独立于站点注册规则，首次登录自动创建账号" : "已关闭，登录页不显示第三方登录入口"}</small></span>
          <span class="row_btns">${oauthChoice(false, "关闭")}${oauthChoice(true, "开启", ld ? "" : "disabled")}</span></div></div>
        <div class="section"><h2>Linux DO Connect</h2><span class="aside">connect.linux.do</span></div>
        <div class="models">${ldRow}
          <div class="model plain"><span class="m1"><b>回调地址</b><small>${esc(oauth.callback_url)}</small></span>
            <span class="row_btns"><button class="btn small" data-copy="${esc(oauth.callback_url)}">复制</button></span></div>
          <div class="model plain"><span class="m1"><b>应用图标</b><small>${esc(oauth.icon_url)}</small></span>
            <span class="row_btns"><button class="btn small" data-copy="${esc(oauth.icon_url)}">复制</button></span></div></div>`;
    } else if (tab === "site") {
      const settings = data.settings;
      const current = settings.default_model;
      const kept = (name, fallback) => $(`[name="${name}"]`, page)?.value || fallback;
      state.zhsParallel = settings.zhs_parallel_study;
      const fast = settings.answer_pace === "fast";
      const smtp = settings.smtp;
      const SECURITY = { ssl: "SSL", starttls: "STARTTLS", none: "不加密" };
      const smtpRow = smtp
        ? `<div class="model plain"><span class="m1"><b>${esc(smtp.sender_name || "Studia")} &lt;${esc(smtp.sender)}&gt;</b>
            <small class="sans">${esc(smtp.host)}:${smtp.port} · ${SECURITY[smtp.security]}${smtp.username ? ` · ${esc(smtp.username)}` : ""}</small></span>
          <span class="row_btns"><button class="btn small" data-smtp-edit>编辑</button>
            <button class="btn small danger" data-smtp-clear data-confirm="确认清除">清除</button></span></div>`
        : `<div class="model plain"><span class="m1"><small class="sans">还没有配置</small></span>
          <span class="row_btns"><button class="btn small primary" data-smtp-edit>配置</button></span></div>`;
      const [cls, label] = HEALTH[current?.health] || ["", "未测试"];
      const hostOf = (url) => { try { return new URL(url).host; } catch { return url || ""; } };
      const modelRow = current
        ? `<div class="model ai on"><span class="m1"><b>${esc(current.provider_name || "默认供应商")}</b><span class="pill">${current.source === "site" ? "站点配置" : "内置"}</span>
            <small>${esc(current.model)} · ${esc(hostOf(current.base_url))} · ${esc(current.key_hint)}</small></span>
          <span class="health ${cls}" data-default-health title="${esc(current.health_message || (current.checked_at ? `测试于 ${current.checked_at.replace("T", " ")}` : ""))}">${label}</span>
          <span class="row_btns"><button class="btn small" data-default-test>测试</button>
            <button class="btn small" data-default-edit>编辑</button>
            ${current.source === "site" && settings.builtin_available ? '<button class="btn small danger" data-default-reset data-confirm="确认恢复">恢复内置</button>' : ""}</span></div>`
        : `<div class="model plain"><span class="m1"><small class="sans">还没有默认模型</small></span>
          <span class="row_btns"><button class="btn small primary" data-default-edit>配置</button></span></div>`;
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
      body = `<div class="section"><h2>全站默认 AI 模型</h2></div>
        <div class="models">${modelRow}</div>
        <div class="section"><h2>邮件服务</h2></div>
        <div class="models">${smtpRow}</div>
        <div class="section"><h2>注册</h2></div>
        <div class="models">${registrationRows}</div>
        <div class="section"><h2>界面</h2><span class="aside">0.5–2.0×</span></div>
        <div class="models"><div class="model plain stepper_row"><span class="m1"><b>动画速度</b><small class="sans">越大越快</small></span>
          <span class="row_btns"><span class="pace_demo" aria-hidden="true">${'<i class="cell done"></i>'.repeat(6)}</span>
            <span class="stepper"><button class="btn small" data-ui-speed="-1" aria-label="慢一点" ${settings.ui_speed <= 0.5 ? "disabled" : ""}>−</button>
              <output>${(settings.ui_speed ?? 1).toFixed(1)}×</output><button class="btn small" data-ui-speed="1" aria-label="快一点" ${settings.ui_speed >= 2 ? "disabled" : ""}>＋</button></span></span></div></div>
        <div class="section"><h2>任务上限</h2></div>
        <div class="models"><div class="model plain"><span class="m1"><b>默认每人同时 <input class="inline_num" type="number" min="1" max="20" name="max_jobs" value="${esc(kept("max_jobs", settings.max_jobs))}"> 个任务</b></span>
          <span class="row_btns"><button class="btn small primary" data-save-limit>保存</button></span></div></div>
        <div class="section"><h2>适配检查与上报</h2></div>
        <div class="models"><div class="model plain stepper_row"><span class="m1"><b>任务后问题检查弹窗</b>
          <small class="sans">${settings.issue_report !== false ? "任务结束后检测到未完成或跳过项时弹窗，成员可一键上报到「适配上报」列表" : "已关闭，任务结束不再弹窗检查，也不接收新的适配上报"}</small></span>
          <span class="row_btns"><button class="btn small" data-issue-report-toggle="0" aria-pressed="${settings.issue_report === false}">关闭</button><button class="btn small" data-issue-report-toggle="1" aria-pressed="${settings.issue_report !== false}">开启</button></span></div></div>
        <div class="section"><h2>智慧树</h2></div>
        <div class="models"><div class="model plain"><span class="m1"><b>多并发学习</b><span class="pill ${settings.zhs_parallel_study ? "wait" : ""}">${settings.zhs_parallel_study ? "已开启" : "已关闭"}</span></span>
          <span class="row_btns"><button class="btn small ${settings.zhs_parallel_study ? "" : "danger"}" data-zhs-parallel="${settings.zhs_parallel_study ? "off" : "on"}" ${settings.zhs_parallel_study ? "" : 'data-confirm="确认开启"'}>${settings.zhs_parallel_study ? "关闭" : "开启"}</button></span></div>
          <div class="model plain stepper_row"><span class="m1"><b>答题节奏 · ${fast ? "快速" : "稳妥"}</b><small class="sans">${fast
            ? "每步间隔 0.1–0.5 秒"
            : "每步间隔 0.5–2 秒"}</small></span>
            <span class="row_btns"><button class="btn small" data-site-pace="steady" aria-pressed="${!fast}">稳妥</button><button class="btn small" data-site-pace="fast" aria-pressed="${fast}" ${fast ? "" : 'data-confirm="确认用快速"'}>快速</button></span></div></div>
        <div class="section"><h2>答案记忆</h2></div>
        <div class="models"><div class="model plain"><span class="m1"><b>智慧树 ${data.memory.questions} 题</b><small class="sans">${data.memory.confirmed} 题已确认正确</small></span></div>
          <div class="model plain"><span class="m1"><b>MOOC ${data.memory.mooc.questions} 题</b><small class="sans">平台公布的标准答案</small></span></div></div>`;
    } else {
      const pad2 = (n) => String(n).padStart(2, "0");
      const local = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
      const today = new Date(); today.setHours(0, 0, 0, 0);
      body = `<div class="section"><h2>日志导出</h2><span class="aside">最长 92 天</span></div>
        <div class="models"><div class="model plain log_export"><span class="log_range">
            <label>从 <input type="datetime-local" name="log_from" value="${esc(local(today))}"></label>
            <label>到 <input type="datetime-local" name="log_to" value="${esc(local(new Date()))}"></label>
            <label>类型 <select name="log_kind"><option value="app">运行日志</option><option value="audit">操作记录</option></select></label></span>
          <span class="row_btns"><button class="btn small primary" data-export-logs>导出</button></span></div></div>`;
    }
    quiet = !(cached && !inConsole);  // cached lists on arrival get the page's entrance
    setPage(head + body);
    quiet = false;
    if (cached) VIEWS.admin(true, tab);  // then read them anew; what changed patches in
    const act = async (path, payload, message) => {
      try { await api(path, { method: "POST", body: payload || {} }); toast(message); VIEWS.admin(true, tab); } catch (e) { toast(e.message); }
    };
    const on = (selector, handler) => page.querySelectorAll(selector).forEach((el) => (el.onclick = () => handler(el)));
    on("[data-smtp-edit]", () => openSmtpModal(data.settings.smtp, () => {
      session.mail = true;
      if (state.view === "#/admin" && state.adminTab === tab) VIEWS.admin(true, tab);
    }));
    on("[data-smtp-clear]", () => { session.mail = false; act("/api/admin/settings", { smtp: null }, "已清除邮件服务"); });
    on("[data-oauth-enabled]", async (el) => {
      if (el.getAttribute("aria-pressed") === "true") return;
      const enabled = el.dataset.oauthEnabled === "1";
      try {
        const res = await api("/api/admin/settings", { method: "POST", body: { oauth: { enabled } } });
        session.oauth = { enabled: Boolean(res.oauth?.enabled), linuxdo: Boolean(res.oauth?.enabled && res.oauth?.linuxdo) };
        toast(enabled ? "已开启 OAuth 登录" : "已关闭 OAuth 登录");
        VIEWS.admin(true, tab);
      } catch (e) { toast(e.message); }
    });
    on("[data-linuxdo-edit]", () => openLinuxdoModal(data.settings.oauth, (res) => {
      session.oauth = { enabled: Boolean(res.oauth?.enabled), linuxdo: Boolean(res.oauth?.enabled && res.oauth?.linuxdo) };
      if (state.view === "#/admin" && state.adminTab === tab) VIEWS.admin(true, tab);
    }));
    on("[data-linuxdo-clear]", async () => {
      try {
        const res = await api("/api/admin/settings", { method: "POST", body: { oauth: { linuxdo: null } } });
        session.oauth = { enabled: Boolean(res.oauth?.enabled), linuxdo: Boolean(res.oauth?.enabled && res.oauth?.linuxdo) };
        toast("已清除 Linux DO 配置");
        VIEWS.admin(true, tab);
      } catch (e) { toast(e.message); }
    });
    on("[data-default-edit]", () => openDefaultModelModal(data.settings.default_model, () => {
      state.settings = null;
      if (state.view === "#/admin" && state.adminTab === tab) VIEWS.admin(true, tab);
    }));
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
    on("[data-issue-report-toggle]", async (el) => {
      if (el.getAttribute("aria-pressed") === "true") return;
      const enabled = el.dataset.issueReportToggle === "1";
      try {
        await api("/api/admin/settings", { method: "POST", body: { issue_report: enabled } });
        state.issueReport = enabled;
        session.issueReport = enabled;
        delete adminCache.reports;
        toast(enabled ? "已开启适配检查与上报" : "已关闭适配检查与上报");
        VIEWS.admin(true, tab);
      } catch (e) { toast(e.message); }
    });
    on("[data-report-expand]", (el) => {
      const id = el.dataset.reportExpand;
      state.reportOpen = state.reportOpen === id ? null : id;
      VIEWS.admin("local", tab).then(() => {
        if (state.reportOpen) {
          const panel = page.querySelector(`[data-report-detail="${CSS.escape(state.reportOpen)}"]`);
          if (panel) moves(panel, scanned(-6), { duration: 420, easing: EASE_IO });
        }
      });
    });
    on("[data-report-copy]", (el) => {
      const report = (data.reports?.reports || []).find((x) => x.id === el.dataset.reportCopy);
      if (!report) return;
      const notes = (report.reporters || []).filter((u) => u.note).map((u) => `${u.username}: ${u.note}`).join("；");
      const text = formatIssueMarkdown(report.payload || report, notes);
      navigator.clipboard?.writeText(text).then(() => toast("已复制诊断详情"), () => toast("复制失败，请手动展开查看"));
    });
    on("[data-report-status]", (el) => {
      const to = el.dataset.toStatus;
      const word = { open: "已重新打开", resolved: "已标记处理完成", ignored: "已忽略" }[to] || "已更新";
      act(`/api/admin/reports/${el.dataset.reportStatus}/status`, { status: to }, word);
    });
    on("[data-report-delete]", (el) => {
      if (state.reportOpen === el.dataset.reportDelete) state.reportOpen = null;
      act(`/api/admin/reports/${el.dataset.reportDelete}/delete`, {}, "已删除上报记录");
    });
    on("[data-zhs-parallel]", (el) => {
      const enable = el.dataset.zhsParallel === "on";
      act("/api/admin/settings", { zhs_parallel_study: enable }, enable ? "已开启" : "已关闭");
    });
    on("[data-registration]", (el) => {
      if (el.getAttribute("aria-pressed") === "true") return;
      act("/api/admin/settings", { registration: { [el.dataset.registration]: el.dataset.value === "1" } }, "已保存");
    });
    // Tap − / + as often as needed: this page follows at once (the strip plays at the new tempo); saved once the taps stop.
    on("[data-ui-speed]", (el) => {
      const settings = adminData.data.settings;
      settings.ui_speed = Math.round(Math.min(2, Math.max(0.5, (settings.ui_speed ?? 1) + Number(el.dataset.uiSpeed) * 0.1)) * 10) / 10;
      applySpeed(settings.ui_speed);
      VIEWS.admin("local", tab).then(demoSpeed);
      clearTimeout(stepTimer);
      stepTimer = setTimeout(async () => {
        try { await api("/api/admin/settings", { method: "POST", body: { ui_speed: settings.ui_speed } }); toast("已保存"); }
        catch (e) { toast(e.message); VIEWS.admin(true, tab); }
      }, 600);
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
    // Limit and password open in a modal so background refreshes never disturb typing.
    on("[data-row-edit]", (el) => {
      const u = users.find((x) => String(x.id) === el.dataset.uid);
      if (!u) return;
      if (el.dataset.rowEdit === "limit") openUserLimitModal(u, () => VIEWS.admin(true, tab));
      else openUserPasswordModal(u, () => VIEWS.admin(true, tab));
    });
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
            ${admin ? `<div class="tabs" role="tablist"><button class="tab" role="tab" aria-selected="${!all}" data-go="#/jobs">我的${state.jobs.length ? `<span class="n">${state.jobs.length}</span>` : ""}</button>
        <button class="tab" role="tab" aria-selected="${all}" data-go="#/jobs/all">全站${siteCount() ? `<span class="n">${siteCount()}</span>` : ""}</button></div>` : ""}`;
    if (all) {
      const people = state.sitePeople;
      setPage(head + (!people ? `<div class="empty loading">正在读取…</div>` : !people.length ? `<div class="empty">现在没有任务在运行</div>`
        : people.map((u) => `<div class="section"><h2>${esc(u.username)}</h2><span class="aside">${boardCount(u.jobs, u.limit)}</span></div>${board(u.jobs, u.limit, u.id)}`).join("")));
      return;
    }
    const open = new Set([...page.querySelectorAll(".run_lines:not([hidden])")].map((el) => el.dataset.lines));
    const live = state.jobs.length ? `<div class="section"><h2>进行中</h2><span class="aside">${boardCount(state.jobs, state.jobLimit)}</span></div>
      ${board(state.jobs, state.jobLimit)}` : "";
    const rows = state.history.map((j, i) => { const past = retried(j, i); return `<div class="run ${open.has(String(i)) ? "open" : ""} ${past ? "past" : ""}" data-key="${esc(j.id)}" data-history="${i}">${ICON[j.state] || ICON.stopped}
        <span class="t1">${esc(j.title)} · ${esc(j.course_name)}<small>${esc(platformOf(j.platform)?.short || "")} · ${esc(j.summary)}</small></span>
        <span class="fix">${past ? "" : fixButtons(j, i)}</span>
        <span class="state ${past ? "stopped" : j.state}">${past ? "已重试" : STATE_WORD[j.state] || ""}<span class="mono">${j.ended ? duration(j.ended - j.started) : ""}</span></span>
        <span class="when">${ago(j.ended || j.started)}</span><span class="chev_r" aria-hidden="true"></span></div>
      <div class="run_lines" data-lines="${i}" ${open.has(String(i)) ? "" : "hidden"}>${open.has(String(i)) ? logHtml(j.lines || [], "all", j.course_name) : ""}</div>`; }).join("");
    setPage(`${head}
      ${live}
      <div class="section"><h2>历史</h2></div>
      ${rows ? `<div class="runs">${rows}</div>` : `<div class="empty">还没有运行过任务</div>`}`);
    page.querySelectorAll("[data-history]").forEach((el) => (el.onclick = (event) => {
      if (event.target.closest("button, a")) return;
      const lines = page.querySelector(`[data-lines="${el.dataset.history}"]`);
      const j = state.history[el.dataset.history];
      lines.hidden = !lines.hidden;
      lines.innerHTML = lines.hidden ? "" : logHtml(j.lines || [], "all", j.course_name);
      el.classList.toggle("open", !lines.hidden);
      if (!lines.hidden) moves(lines, scanned(-6), { duration: 520, easing: EASE_IO });
    }));
    page.querySelectorAll("[data-retry]").forEach((el) => (el.onclick = () => {
      const j = state.history[el.dataset.retry];
      startJob({ platform: j.platform, course: j.course, type: TYPE_OF[j.title] });
    }));
    page.querySelectorAll("[data-history-issue]").forEach((el) => (el.onclick = () => {
      const j = state.history[el.dataset.historyIssue];
      if (j?.issue_check) openIssueModal(j.issue_check);
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
    const card = me
      ? `<button class="me_card me_link" data-go="#/profile"><span class="avatar big">${esc(me.username.slice(0, 1).toUpperCase())}</span>
          <span class="who"><h1>${esc(me.username)}</h1><small>${me.role === "admin" ? "管理员" : "成员"}${me.linuxdo ? ` · Linux DO @${esc(me.linuxdo.username || me.linuxdo.id)}` : ""}</small></span>${ICON.chev}</button>`
      : `<div class="me_card"><span class="avatar big">本</span><span class="who"><h1>本机</h1><small>只有这台电脑能访问</small></span></div>`;
    const platTarget = me ? "#/profile" : "#/settings/study";
    setPage(`${card}
      <div class="section"><h2>平台账号</h2></div>
      <div class="lrows">${state.platforms.map((p) => row(`data-go="${p.rescan || qaSoon(p) ? rescanLink(p) : p.logged_in ? platTarget : `#/login/${p.id}`}"`,
        `<span class="plat ${p.id}">${INITIAL[p.id]}</span>`, p.name, platformStatus(p),
        p.rescan || qaSoon(p) ? '<span class="lrow_go">扫码</span>' : p.logged_in ? ICON.chev : '<span class="lrow_go">登录</span>')).join("")}</div>
      <div class="section"><h2>设置</h2></div>
      <div class="lrows">${row('data-go="#/settings/models"', ICON.spark, "AI 模型")}${row('data-go="#/settings/study"', ICON.gear, "偏好")}${me?.role === "admin" ? row('data-go="#/admin"', ICON.shield, "管理后台") : ""}</div>
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

  profile() {
    const me = session.user;
    if (!me) return go("#/settings");
    const admin = me.role === "admin", hasPassword = me.has_password !== false, ld = me.linuxdo;
    const connected = state.platforms.filter((p) => p.logged_in);
    const loadingCourses = connected.some((p) => !state.courses[p.id]);
    const totalCourses = connected.reduce((sum, p) => sum + (state.courses[p.id]?.length || 0), 0);
    const doneJobs = state.history.filter((j) => j.state === "done").length;
    const lastJob = state.history[0];
    const running = state.jobs.filter((j) => j.state === "running").length;
    const metaParts = [
      ld ? `Linux DO @${esc(ld.username || ld.id)}${ld.trust_level != null ? ` · ${ld.trust_level} 级` : ""}` : "",
      me.email ? esc(me.email) : "",
      me.created ? `${new Date(me.created * 1000).toLocaleDateString()} 加入` : "",
    ].filter(Boolean);

    const hero = `<section class="profile_hero">
      <div class="profile_head">
        <span class="profile_avatar ${admin ? "admin" : ""}">${esc(me.username.slice(0, 1).toUpperCase())}</span>
        <div class="profile_who">
          <div class="profile_name">
            <h1>${esc(me.username)}</h1>
            <span class="pill ${admin ? "blue" : ""}">${admin ? "管理员" : "成员"}</span>
            <span class="profile_id mono">ID ${esc(String(me.id || "").slice(0, 8))}</span>
          </div>
          <p class="profile_meta">${metaParts.join('<span class="sep">·</span>') || "Studia 成员"}</p>
        </div>
        <button class="btn small" data-account-edit="username">修改用户名</button>
      </div>
      <div class="profile_stats">
        <div class="pstat">
          <span class="pstat_label"><span class="pstat_ico celadon">${ICON.cells}</span>在学课程</span>
          <strong class="pstat_val mono">${connected.length && loadingCourses ? "—" : `${totalCourses}`}<small>门</small></strong>
          <span class="pstat_sub">已连接 ${connected.length} / ${state.platforms.length} 个学习平台</span>
        </div>
        <div class="pstat">
          <span class="pstat_label"><span class="pstat_ico indigo">${ICON.pulse}</span>并行任务</span>
          <strong class="pstat_val mono">${running}<small>/ ${state.jobLimit}</small></strong>
          <span class="pstat_sub">${state.jobs.length ? `队列中共 ${state.jobs.length} 个任务` : "当前空闲，随时可启动学习"}</span>
        </div>
        <div class="pstat">
          <span class="pstat_label"><span class="pstat_ico ink">${ICON.spark}</span>已完成任务</span>
          <strong class="pstat_val mono">${doneJobs}<small>次</small></strong>
          <span class="pstat_sub">${lastJob ? `最近一次 ${ago(lastJob.ended || lastJob.started)}` : "还没有运行过任务"}</span>
        </div>
      </div>
    </section>`;

    const linuxdoRow = (ld || session.oauth?.linuxdo) ? `<div class="pcard_row"><span class="m1"><b>Linux DO</b>${ld ? '<span class="pill blue">已绑定</span>' : ""}
          <small class="sans">${ld ? `@${esc(ld.username || ld.id)}${ld.trust_level != null ? ` · ${ld.trust_level} 级` : ""}` : "未绑定 · 绑定后可用 Linux DO 一键登录"}</small></span>
          <span class="row_btns">${ld
            ? (hasPassword ? '<button class="btn small danger" data-linuxdo-unbind data-confirm="确认解绑">解绑</button>' : '<span class="pill">主登录方式</span>')
            : '<button class="btn small primary" data-linuxdo-bind>绑定</button>'}</span></div>` : "";
    const emailRow = hasPassword ? `<div class="pcard_row"><span class="m1"><b>邮箱</b>
          <small class="sans">${me.email ? esc(me.email) : session.mail ? "未绑定 · 用于找回和修改密码" : "管理员未配置邮件服务"}</small></span>
          <span class="row_btns">${session.mail ? `<button class="btn small ${me.email ? "" : "primary"}" data-account-edit="email">${me.email ? "更换" : "绑定邮箱"}</button>`
            : admin ? '<button class="btn small" data-go="#/admin/site">去配置</button>' : ""}</span></div>` : "";
    const passwordRow = hasPassword ? `<div class="pcard_row"><span class="m1"><b>密码</b>
          <small class="sans">${me.email && session.mail ? "通过邮箱重置链接修改密码" : "绑定邮箱并配置邮件服务后可修改"}</small></span>
          <span class="row_btns"><button class="btn small" data-account-edit="password" ${me.email && session.mail ? "" : "disabled"}>修改密码</button></span></div>` : "";
    const oauthOnlyNote = !hasPassword ? `<div class="pcard_row"><span class="m1"><b>免密登录</b>
          <small class="sans">当前通过 Linux DO 授权登录，无需单独绑定邮箱或设置密码</small></span></div>` : "";

    const securityCard = `<section class="profile_card">
      <div class="pcard_head"><span class="pcard_ico indigo">${ICON.shield}</span><div><h2>账号与安全</h2><p>第三方登录授权、邮箱与密码保护</p></div></div>
      <div class="pcard_body">${linuxdoRow}${emailRow}${passwordRow}${oauthOnlyNote}</div>
    </section>`;

    const platformCard = `<section class="profile_card">
      <div class="pcard_head"><span class="pcard_ico celadon">${ICON.key}</span><div><h2>学习平台</h2><p>已连接的网课账号，用于同步课程与自动学习</p></div></div>
      <div class="pcard_body">${state.platforms.map((p) => {
        const list = state.courses[p.id];
        const status = !p.logged_in ? (p.lapsed ? "登录已过期" : p.login === "qr" ? "App 扫码登录" : "职教云浏览器授权")
          : [list ? `${list.length} 门课程` : "正在读取课程", p.login === "qr" ? "App 扫码" : "浏览器授权"].join(" · ");
        return `<div class="pcard_row plat_row">
        <span class="plat ${p.id}">${INITIAL[p.id]}</span>
        <span class="m1"><b>${esc(p.name)}</b><span class="pill ${p.rescan || qaSoon(p) ? "wait" : p.logged_in ? "blue" : ""}">${p.rescan ? "需重新扫码" : p.logged_in ? "已连接" : "未登录"}</span>
          <small class="sans">${esc(status)}</small></span>
        <span class="row_btns">${p.rescan || qaSoon(p) ? `<button class="btn small primary" data-go="${rescanLink(p)}">重新扫码</button>` : ""}${p.logged_in ? `<button class="btn small danger" data-logout="${p.id}" data-confirm="确认退出">退出</button>` : `<button class="btn small primary" data-go="#/login/${p.id}">登录</button>`}</span></div>`;
      }).join("")}</div>
    </section>`;

    setPage(`${hero}<div class="profile_grid">${platformCard}${securityCard}</div>`);

    page.querySelectorAll("[data-logout]").forEach((el) => (el.onclick = async () => {
      try { await api(`/api/platforms/${el.dataset.logout}/logout`, { method: "POST" }); } catch (e) { toast(e.message); return; }
      await refreshState();
      toast("已退出登录");
      VIEWS.profile();
    }));
    page.querySelectorAll("[data-account-edit]").forEach((el) => (el.onclick = () => {
      const kind = el.dataset.accountEdit;
      if (kind === "username") openUsernameModal();
      else if (kind === "email") openEmailModal();
      else if (kind === "password") openPasswordModal();
    }));
    const bindBtn = $("[data-linuxdo-bind]", page);
    if (bindBtn) bindBtn.onclick = async () => {
      bindBtn.disabled = true;
      bindBtn.textContent = "跳转中…";
      try {
        const { url } = await api("/api/auth/linuxdo/bind", { method: "POST" });
        location.href = url;
      } catch (e) {
        toast(e.message);
        bindBtn.disabled = false;
        bindBtn.textContent = "绑定";
      }
    };
    const unbindBtn = $("[data-linuxdo-unbind]", page);
    if (unbindBtn) unbindBtn.onclick = async () => {
      try {
        ({ user: session.user } = await api("/api/auth/linuxdo/unbind", { method: "POST" }));
        toast("已解绑 Linux DO");
        VIEWS.profile();
      } catch (e) { toast(e.message); }
    };
  },

  async settings(tab = SETTINGS_TABS[0][0]) {
    tab = SETTINGS_TABS.some(([k]) => k === tab) ? tab : SETTINGS_TABS[0][0];
    const head = settingsHead(tab, "");
    // Draw from the last copy at once; repaint only if the server's copy differs.
    const cached = state.settings;
    if (cached) paintSettings(tab, head, cached, false);
    else setPage(`${head}<div class="empty loading">正在读取…</div>`);
    try { state.settings = await api("/api/settings"); } catch (error) { if (!cached) toast(error.message); return; }
    if (location.hash.startsWith("#/settings")) {
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
// Replacing a bound address asks for the password (a stolen session alone can't redirect reset links).
const emailFields = () => `${session.user?.email ? `<label class="auth_field"><span>当前密码</span><span class="pw"><input name="password" type="password" autocomplete="current-password" required><button type="button" class="pw_eye" data-reveal aria-label="显示密码">显示</button></span></label>` : ""}
  <label class="auth_field"><span>${session.user?.email ? "新邮箱" : "邮箱"}</span><span class="code_row">
    <input name="email" type="email" autocomplete="email" autocapitalize="off" placeholder="name@example.com" required>
    <button type="button" class="btn" data-send-code>发送验证码</button></span></label>
  <label class="auth_field"><span>验证码</span><input class="mono_in" name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="邮件里的 6 位数字" required></label>
  <p class="form_msg" role="alert"></p>`;
function wireEmailForm(form, done) {
  wireReveal(form);
  const msg = $(".form_msg", form), send = $("[data-send-code]", form), { email, code, password } = form.elements;
  const say = (text, ok = false) => { msg.textContent = text; msg.classList.toggle("ok", ok); };
  form.oninput = () => { if (!msg.classList.contains("ok")) say(""); };
  send.onclick = async () => {
    if (password && !password.value) { say("请先填写当前密码"); password.focus(); return; }
    if (!email.value.trim() || !email.checkValidity()) { say("请填写正确的邮箱"); email.focus(); return; }
    send.disabled = true;
    send.textContent = "发送中…";
    try {
      await api("/api/auth/email/code", { method: "POST", body: { email: email.value.trim(), ...(password ? { password: password.value } : {}) } });
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
    button.textContent = "绑定中…";
    try { ({ user: session.user } = await api("/api/auth/email", { method: "POST", body: { code: code.value.trim() } })); done(); }
    catch (e) { say(e.message); button.disabled = false; button.textContent = "绑定"; }
  };
}
function openUsernameModal() {
  const me = session.user;
  const dialog = document.createElement("dialog");
  dialog.className = "modal";
  dialog.setAttribute("aria-labelledby", "username-modal-title");
  dialog.innerHTML = `<form data-username>
      <h3 id="username-modal-title" tabindex="-1" autofocus>修改用户名</h3>
      <p class="sub">用户名用于登录和个人资料展示，长度 2–32 个字符。</p>
      <label class="auth_field"><span>新用户名</span>
        <input name="username" value="${esc(me?.username || "")}" autocomplete="username" autocapitalize="off" minlength="2" maxlength="32" required></label>
      <p class="form_msg" role="alert"></p>
      <div class="modal_btns"><span class="grow"></span>
        <button type="button" class="btn" data-cancel>取消</button><button class="btn primary">保存</button></div></form>`;
  document.body.appendChild(dialog);
  const form = $("form", dialog), msg = $(".form_msg", dialog), ok = $("button.primary", dialog);
  dialog.addEventListener("cancel", (e) => { e.preventDefault(); closeModal(dialog); });
  dialog.addEventListener("close", () => dialog.remove());
  $("[data-cancel]", dialog).onclick = () => closeModal(dialog);
  form.oninput = () => (msg.textContent = "");
  form.onsubmit = async (event) => {
    event.preventDefault();
    ok.disabled = true; ok.textContent = "保存中…";
    try {
      ({ user: session.user } = await api("/api/auth/username", { method: "POST", body: { username: form.elements.username.value.trim() } }));
      closeModal(dialog);
      renderSidebar();
      toast("用户名已修改");
      if (state.view === "#/profile") VIEWS.profile();
    } catch (e) { msg.textContent = e.message; ok.disabled = false; ok.textContent = "保存"; }
  };
  dialog.showModal();
  if (!TOUCH) { form.elements.username.focus(); form.elements.username.select(); }
}
function openEmailModal() {
  const me = session.user;
  const dialog = document.createElement("dialog");
  dialog.className = "modal";
  dialog.setAttribute("aria-labelledby", "email-modal-title");
  dialog.innerHTML = `<form data-email-form>
      <h3 id="email-modal-title" tabindex="-1" autofocus>${me?.email ? "更换邮箱" : "绑定邮箱"}</h3>
      <p class="sub">${me?.email ? `当前已绑定 ${esc(me.email)}，验证新邮箱后立即生效。` : "绑定邮箱后可用于登录、找回和修改密码。"}</p>
      ${emailFields()}
      <div class="modal_btns"><span class="grow"></span>
        <button type="button" class="btn" data-cancel>取消</button><button class="btn primary">绑定</button></div></form>`;
  document.body.appendChild(dialog);
  dialog.addEventListener("cancel", (e) => { e.preventDefault(); closeModal(dialog); });
  dialog.addEventListener("close", () => dialog.remove());
  $("[data-cancel]", dialog).onclick = () => closeModal(dialog);
  wireEmailForm($("form", dialog), () => { closeModal(dialog); toast("邮箱已绑定"); if (state.view === "#/profile") VIEWS.profile(); });
  dialog.showModal();
  if (!TOUCH) $("input", dialog)?.focus();
}
function openPasswordModal() {
  const me = session.user;
  const dialog = document.createElement("dialog");
  dialog.className = "modal";
  dialog.setAttribute("aria-labelledby", "password-modal-title");
  dialog.innerHTML = `<div data-password-panel>
      <h3 id="password-modal-title" tabindex="-1" autofocus>修改密码</h3>
      <p class="sub" data-pw-sub>系统会将一次性重置密码链接发到 <b>${esc(me?.email || "")}</b>，点击邮件里的链接即可设置新密码。</p>
      <p class="form_msg" role="alert"></p>
      <div class="modal_btns"><span class="grow"></span>
        <button type="button" class="btn" data-cancel>取消</button>
        <button type="button" class="btn primary" data-password-send>发送邮件</button></div></div>`;
  document.body.appendChild(dialog);
  const msg = $(".form_msg", dialog), send = $("[data-password-send]", dialog), cancel = $("[data-cancel]", dialog), sub = $("[data-pw-sub]", dialog);
  dialog.addEventListener("cancel", (e) => { e.preventDefault(); closeModal(dialog); });
  dialog.addEventListener("close", () => dialog.remove());
  cancel.onclick = () => closeModal(dialog);
  const paintSent = () => {
    sub.innerHTML = `重置链接已发到 <b>${esc(me?.email || "")}</b>，请查收邮件。重新发送会让上一封邮件里的链接失效。`;
    cancel.textContent = "完成";
    send.classList.remove("primary");
    resendAfter(send, state.passwordSent);
  };
  if (state.passwordSent && Date.now() - state.passwordSent < 60000) paintSent();
  send.onclick = async () => {
    msg.textContent = "";
    send.disabled = true;
    send.textContent = "发送中…";
    try {
      await api("/api/auth/password", { method: "POST" });
      state.passwordSent = Date.now();
      paintSent();
    } catch (e) {
      msg.textContent = e.message;
      send.disabled = false;
      send.textContent = state.passwordSent ? "重新发送" : "发送邮件";
    }
  };
  dialog.showModal();
}
// Once each time the page opens, until the email is bound or the person picks 今天不显示.
// A dialog sinks and fades (its backdrop with it) before it closes.
function closeModal(dialog) {
  if (dialog.dataset.closing) return;
  dialog.dataset.closing = "1";
  // Folded back to its middle line, as it opened.
  const out = moves(dialog, [{ clipPath: "inset(-40px)" }, { clipPath: "inset(50% -40px 50% -40px)", transform: "scale(.985)" }], { duration: 360, easing: EASE_IO, fill: "forwards" });
  try { moves(dialog, [{ opacity: 1 }, { opacity: 0 }], { duration: 360, pseudoElement: "::backdrop", fill: "forwards" }); } catch { /* backdrop stays until close */ }
  const done = () => { dialog.close(); setTimeout(flushPendingIssues, 160); };
  if (out) out.onfinish = done; else done();
}
const ISSUE_PILL = { failed: "red", unverified: "wait", unknown: "wait", skipped: "" };
const SHARE_LABEL = { progress: "学习", habit: "习惯", interactive: "互动", knowledge: "掌握度", test: "测试", meet: "见面课", final: "期末" };

function formatIssueMarkdown(check, note = "") {
  const lines = [
    "### 课程适配问题诊断",
    `- 平台：${check.platform_name || check.platform || "未知"}${check.course_type ? `（${check.course_type}）` : ""}`,
    `- 课程：${check.course_name || "未知课程"}（ID: \`${check.course_id || ""}\`，课型: \`${check.course_kind || ""}\`）`,
    `- 任务：${check.job_title || check.job_kind || "任务"} · 状态：${check.job_state || ""}${check.job_summary ? `（${check.job_summary}）` : ""}`,
  ];
  if (check.progress != null) lines.push(`- 当前进度：${check.progress}%`);
  if (check.shares) {
    const parts = Object.entries(check.shares).filter(([, v]) => v > 0).map(([k, v]) => `${SHARE_LABEL[k] || k} ${v} 分`);
    if (parts.length) lines.push(`- 考核占比：${parts.join(" / ")}`);
  }
  if (note && note.trim()) lines.push(`- 补充说明：${note.trim()}`);
  const items = check.items || [];
  lines.push("", `#### 检测到的问题（共 ${items.length} 项）`);
  items.forEach((it, idx) => {
    lines.push(`${idx + 1}. [${it.label || it.code}] ${it.name || "未命名"}${it.kind ? `（类型：\`${it.kind}\`）` : ""}`);
    if (it.detail) lines.push(`   - 说明：${it.detail}`);
    if (it.fields) lines.push(`   - 字段：\`${it.fields}\``);
  });
  const logs = check.logs || [];
  if (logs.length) {
    lines.push("", "#### 相关日志");
    logs.slice(0, 15).forEach((l) => lines.push(`- ${l.time ? `[${l.time}] ` : ""}${l.text || ""}`));
  }
  return lines.join("\n");
}

function flushPendingIssues() {
  if (!state.issueReport || document.querySelector("dialog[open]") || !state.pendingIssues.length) return;
  const next = state.pendingIssues.shift();
  if (next) openIssueModal(next);
}

function queueIssueModal(check) {
  if (!state.issueReport || !check?.items?.length) return;
  const jid = check.job_id || "";
  if (jid && state.shownIssueJobs.has(jid)) return;
  if (jid) state.shownIssueJobs.add(jid);
  if (document.querySelector("dialog[open]")) {
    state.pendingIssues.push(check);
    return;
  }
  openIssueModal(check);
}

function openIssueModal(check) {
  const hosted = session.mode === "hosted";
  const items = check.items || [];
  const shown = items.slice(0, 6);
  const more = Math.max(0, items.length - shown.length);
  const shares = check.shares
    ? Object.entries(check.shares).filter(([, v]) => v > 0).map(([k, v]) => `${SHARE_LABEL[k] || k} ${v}%`).join(" · ")
    : "";
  const dialog = document.createElement("dialog");
  dialog.className = "modal issue_modal";
  dialog.setAttribute("aria-labelledby", "issue-modal-title");
  dialog.innerHTML = `<form data-issue-form>
      <h3 id="issue-modal-title" tabindex="-1" autofocus>你似乎遇到了一些问题</h3>
      <p class="sub">${esc(check.headline || "任务结束后检测到未能自动完成或被跳过的课程内容。")}</p>
      <div class="issue_card">
        <div class="issue_course">
          <span class="plat ${esc(check.platform || "")}">${INITIAL[check.platform] || "?"}</span>
          <span class="m1"><b>${esc(check.course_name || "未知课程")}</b>
            <small class="sans">${esc([check.platform_name || check.platform, check.course_type || check.course_kind, check.job_title,
              check.progress != null ? `进度 ${check.progress}%` : ""].filter(Boolean).join(" · "))}</small>
            ${shares ? `<small class="sans">考核占比：${esc(shares)}</small>` : ""}</span>
        </div>
        <div class="issue_list">${shown.map((it) => `<div class="issue_item">
          <div class="issue_item_head"><span class="pill ${ISSUE_PILL[it.bucket] || ""}">${esc(it.label || it.code)}</span>
            <b>${esc(it.name || "未命名")}</b>${it.kind ? `<code class="issue_kind">${esc(it.kind)}</code>` : ""}</div>
          ${it.detail ? `<p class="issue_desc">${esc(it.detail)}</p>` : ""}</div>`).join("")}
          ${more ? `<p class="issue_more">还有 ${more} 项未展开，上报时将一并附带</p>` : ""}</div>
      </div>
      ${hosted ? `<label class="auth_field issue_note_field"><span>补充说明（选填）</span>
        <input name="note" maxlength="300" autocomplete="off" placeholder="例如：第 3 章互动环节一直没算完成"></label>` : ""}
      <details class="issue_preview"><summary>查看脱敏诊断内容（不含账号与登录态）</summary>
        <pre class="issue_code">${esc(formatIssueMarkdown(check))}</pre></details>
      <p class="form_msg" role="alert"></p>
      <div class="modal_btns">
        ${hosted
          ? `<button type="button" class="btn" data-issue-copy>复制信息</button><span class="grow"></span>
             <button type="button" class="btn" data-issue-close>暂不上报</button>
             <button class="btn primary" data-issue-submit>${check.reported ? "再次上报" : "一键上报"}</button>`
          : `<button type="button" class="link" data-issue-local-off>关闭此提示</button><span class="grow"></span>
             <button type="button" class="btn" data-issue-close>关闭</button>
             <button type="button" class="btn primary" data-issue-copy>一键复制诊断信息</button>`}
      </div></form>`;
  document.body.appendChild(dialog);
  const form = $("form", dialog), msg = $(".form_msg", dialog);
  dialog.addEventListener("cancel", (e) => { e.preventDefault(); closeModal(dialog); });
  dialog.addEventListener("close", () => dialog.remove());
  $("[data-issue-close]", dialog).onclick = () => closeModal(dialog);
  const copyBtn = $("[data-issue-copy]", dialog);
  if (copyBtn) copyBtn.onclick = () => {
    const note = form.elements.note?.value || "";
    const text = formatIssueMarkdown(check, note);
    navigator.clipboard?.writeText(text).then(
      () => { toast(hosted ? "已复制脱敏诊断信息" : "已复制脱敏诊断信息，可发给开发者或提 Issue"); if (!hosted) closeModal(dialog); },
      () => { msg.textContent = "无法自动复制，请展开上方脱敏内容手动复制"; }
    );
  };
  const offBtn = $("[data-issue-local-off]", dialog);
  if (offBtn) offBtn.onclick = async () => {
    try {
      await api("/api/settings/issue-report", { method: "POST", body: { enabled: false } });
      state.issueReport = false;
      if (state.settings) state.settings.issue_report = false;
      closeModal(dialog);
      toast("已关闭问题检查弹窗，可在「设置 → 偏好」重新开启");
    } catch (e) { msg.textContent = e.message; }
  };
  form.onsubmit = async (event) => {
    event.preventDefault();
    if (!hosted) return;
    msg.textContent = "";
    const submit = $("[data-issue-submit]", dialog);
    submit.disabled = true;
    submit.textContent = "上报中…";
    try {
      const note = form.elements.note?.value.trim() || "";
      const res = await api("/api/reports", { method: "POST", body: { job_id: check.job_id, note } });
      check.reported = true;
      const hist = state.history.find((h) => h.id === check.job_id);
      if (hist?.issue_check) hist.issue_check.reported = true;
      delete adminCache.reports;
      closeModal(dialog);
      toast(res.already_reported ? "已更新上报说明，感谢反馈" : "已一键上报给管理员，感谢反馈");
      repaint();
    } catch (e) {
      msg.textContent = e.message;
      submit.disabled = false;
      submit.textContent = check.reported ? "再次上报" : "一键上报";
    }
  };
  dialog.showModal();
}

function promptEmail() {
  const me = session.user, later = `studia-email-later:${me?.id}`;
  if (session.mode !== "hosted" || !me || me.email || me.has_password === false || !session.mail || store.get(later, "") === new Date().toDateString()) return;
  const dialog = document.createElement("dialog");
  dialog.className = "modal";
  dialog.setAttribute("aria-labelledby", "email-prompt");
  // On a phone, focusing the email field would pop the keyboard before the person has read the prompt.
  dialog.innerHTML = `<form data-email-form><h3 id="email-prompt" ${TOUCH ? 'tabindex="-1" autofocus' : ""}>绑定邮箱</h3>
      <p class="sub">绑定邮箱后可用于登录、找回和修改密码。</p>
      ${emailFields()}
      <div class="modal_btns"><button type="button" class="link" data-later>今天不再提醒</button><span class="grow"></span>
        <button type="button" class="btn" data-skip>暂时跳过</button><button class="btn primary">绑定</button></div></form>`;
  document.body.appendChild(dialog);
  dialog.addEventListener("cancel", (event) => { event.preventDefault(); closeModal(dialog); });
  dialog.addEventListener("close", () => dialog.remove());
  $("[data-skip]", dialog).onclick = () => closeModal(dialog);
  $("[data-later]", dialog).onclick = () => { store.set(later, new Date().toDateString()); closeModal(dialog); };
  wireEmailForm($("form", dialog), () => { closeModal(dialog); toast("邮箱已绑定"); if (state.view === "#/profile") VIEWS.profile(); });
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
    const localPlatforms = session.mode === "local" ? `<div class="section"><h2>学习平台</h2></div>
      <div class="models">${state.platforms.map((p) => `<div class="model"><span class="plat ${p.id}">${INITIAL[p.id]}</span>
        <span class="m1"><b>${esc(p.name)}</b><small class="sans">${esc(platformStatus(p))} · ${p.login === "qr" ? "App 扫码登录" : "职教云浏览器授权"}</small></span><span></span>
        <span class="row_btns">${p.rescan || qaSoon(p) ? `<button class="btn small primary" data-go="${rescanLink(p)}">重新扫码</button>` : ""}${p.logged_in ? `<button class="btn small danger" data-logout="${p.id}" data-confirm="确认退出">退出</button>` : `<button class="btn small primary" data-go="#/login/${p.id}">登录</button>`}</span></div>`).join("")}</div>` : "";
    const localIssue = data.issue_report_locked ? "" : `<div class="section"><h2>适配检查</h2><span class="aside">任务结束后提示</span></div>
      <div class="models"><div class="model plain stepper_row"><span class="m1"><b>完成后问题检查弹窗</b>
        <small class="sans">${data.issue_report !== false ? "遇到无法完成或跳过的课程环节时弹窗，方便一键复制脱敏诊断信息" : "已关闭，任务结束后不再弹出问题提示"}</small></span>
        <span class="row_btns"><button class="btn small" data-local-issue-toggle="0" aria-pressed="${data.issue_report === false}">关闭</button><button class="btn small" data-local-issue-toggle="1" aria-pressed="${data.issue_report !== false}">开启</button></span></div></div>`;
    quiet = again;
    setPage(`${head}<div class="section"><h2>并发数量</h2><span class="aside">1–8</span></div>
      <div class="models">${row("ai", "AI 答题", "同时作答的题数")}${row("study", "自动学习", "同时学的资源数")}</div>
      ${data.pace_locked ? "" : `<div class="section"><h2>答题节奏</h2><span class="aside">只影响智慧树</span></div>
      <div class="models"><div class="model plain stepper_row"><span class="m1"><b>${fast ? "快速" : "稳妥"}</b><small class="sans">${fast
        ? "每步间隔 0.1–0.5 秒"
        : "每步间隔 0.5–2 秒"}</small></span>
        <span class="row_btns">${paceButtons}</span></div></div>`}${localIssue}${localPlatforms}`);
    quiet = false;
    page.querySelectorAll("[data-local-issue-toggle]").forEach((el) => (el.onclick = async () => {
      if (el.getAttribute("aria-pressed") === "true") return;
      const enabled = el.dataset.localIssueToggle === "1";
      try {
        await api("/api/settings/issue-report", { method: "POST", body: { enabled } });
        state.settings.issue_report = enabled;
        state.issueReport = enabled;
        toast(enabled ? "已开启完成后问题检查" : "已关闭完成后问题检查");
      } catch (e) { toast(e.message); }
      paintSettings(tab, head, state.settings, true);
    }));
    page.querySelectorAll("[data-logout]").forEach((el) => (el.onclick = async () => {
      try { await api(`/api/platforms/${el.dataset.logout}/logout`, { method: "POST" }); } catch (e) { toast(e.message); return; }
      await refreshState();
      toast("已退出登录");
      paintSettings(tab, head, state.settings, true);
    }));
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
  renderModels(head, data.models, again);
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
  const issueBtn = state.issueReport && j.issue_check?.items?.length
    ? `<button class="btn small" data-history-issue="${i}">${j.issue_check.reported ? "已上报" : "上报问题"}</button>` : "";
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
  if (j.state !== "error" || i !== state.history.findIndex((x) => x.course === j.course && x.title === j.title)) return issueBtn;
  if (type === "answer") return `${issueBtn}<button class="btn small" data-go="#/course/${j.platform}/${j.course}/answer">重新选择试卷</button>`;
  return `${issueBtn}<button class="btn small primary" data-retry="${i}">重试</button>`;
}

/* ---------------------------------------------------------------- settings: models */

function wireReveal(root) {
  root.querySelectorAll("[data-reveal]").forEach((el) => (el.onclick = () => {
    const input = el.previousElementSibling, show = input.type === "password";
    input.type = show ? "text" : "password";
    el.textContent = show ? "隐藏" : "显示";
    el.setAttribute("aria-label", show ? "隐藏内容" : "显示内容");
  }));
}

function openModelModal(m, onDone) {
  const dialog = document.createElement("dialog");
  dialog.className = "modal model_modal";
  dialog.setAttribute("aria-labelledby", "model-modal-title");
  dialog.innerHTML = `<form data-form="${m ? esc(m.id) : "new"}">
      <h3 id="model-modal-title" tabindex="-1" autofocus>${m ? "编辑模型" : "添加模型"}</h3>
      <p class="sub">${m ? "修改后立即生效，API Key 留空则保持当前密钥不变。" : "填写 OpenAI 兼容接口信息，保存后会自动测试连接。"}</p>
      <div class="form_grid">
        <label class="auth_field"><span>名称</span>
          <input name="provider_name" value="${esc(m?.provider || "")}" placeholder="如 DeepSeek 官方"></label>
        <label class="auth_field"><span>模型</span>
          <input class="mono_in" name="model" value="${esc(m?.model || "")}" placeholder="如 deepseek-chat" autocomplete="off" autocapitalize="off" spellcheck="false" required></label>
      </div>
      <label class="auth_field"><span>服务地址</span>
        <input class="mono_in" name="base_url" inputmode="url" value="${esc(m?.base_url || "")}" placeholder="https://api.example.com/v1" autocomplete="off" autocapitalize="off" spellcheck="false" required></label>
      <label class="auth_field"><span>API Key</span>
        <span class="pw"><input class="mono_in" name="api_key" type="password" autocomplete="off" autocapitalize="off" spellcheck="false" ${m ? `placeholder="留空不修改（${esc(m.key_hint)}）"` : 'placeholder="sk-..." required'}>
          <button type="button" class="pw_eye" data-reveal aria-label="显示密钥">显示</button></span></label>
      <p class="form_msg" role="alert"></p>
      <div class="modal_btns">
        ${m?.deletable ? '<button type="button" class="btn danger" data-delete data-confirm="确认删除">删除</button>' : ""}
        <span class="grow"></span>
        <button type="button" class="btn" data-cancel>取消</button>
        <button class="btn primary">${m ? "保存" : "保存并测试"}</button>
      </div>
    </form>`;
  document.body.appendChild(dialog);
  const formEl = $("form", dialog), msg = $(".form_msg", dialog), ok = $("button.primary", dialog), del = $("[data-delete]", dialog);
  wireReveal(dialog);
  dialog.addEventListener("cancel", (event) => { event.preventDefault(); closeModal(dialog); });
  dialog.addEventListener("close", () => dialog.remove());
  $("[data-cancel]", dialog).onclick = () => closeModal(dialog);
  if (del) del.onclick = async () => {
    del.disabled = ok.disabled = true;
    try {
      await api(`/api/settings/models/${m.id}/delete`, { method: "POST" });
      closeModal(dialog); toast("已删除"); onDone();
    } catch (e) { msg.textContent = e.message; del.disabled = ok.disabled = false; }
  };
  formEl.onsubmit = async (event) => {
    event.preventDefault();
    msg.textContent = "";
    const body = Object.fromEntries(new FormData(formEl));
    const isNew = !m;
    ok.disabled = true;
    if (del) del.disabled = true;
    ok.textContent = isNew ? "保存并测试中…" : "保存中…";
    try {
      const r = await api(isNew ? "/api/settings/models" : `/api/settings/models/${m.id}`, { method: "POST", body });
      if (isNew) {
        const t = await api(`/api/settings/models/${r.id}/test`, { method: "POST" });
        closeModal(dialog);
        toast(t.health === "ok" ? "模型可用，已设为使用中" : `已保存，但连接失败：${t.message}`);
      } else {
        closeModal(dialog);
        toast("已保存");
      }
      onDone();
    } catch (e) {
      msg.textContent = e.message;
      ok.disabled = false;
      if (del) del.disabled = false;
      ok.textContent = isNew ? "保存并测试" : "保存";
    }
  };
  dialog.showModal();
  if (!TOUCH) formEl.elements.provider_name.focus();
}

function openDefaultModelModal(saved, onDone) {
  const model = saved || {};
  const dialog = document.createElement("dialog");
  dialog.className = "modal model_modal";
  dialog.setAttribute("aria-labelledby", "default-model-title");
  dialog.innerHTML = `<form data-default-model>
      <h3 id="default-model-title" tabindex="-1" autofocus>${saved ? "编辑全站默认模型" : "配置全站默认模型"}</h3>
      <p class="sub">所有未自配模型的成员都会使用这里配置的服务，保存前会自动测试连接。</p>
      <div class="form_grid">
        <label class="auth_field"><span>名称</span>
          <input name="provider_name" value="${esc(model.provider_name || "")}" placeholder="默认供应商"></label>
        <label class="auth_field"><span>模型</span>
          <input class="mono_in" name="model" value="${esc(model.model || "")}" placeholder="例如 deepseek-chat" autocomplete="off" autocapitalize="off" spellcheck="false" required></label>
      </div>
      <label class="auth_field"><span>服务地址</span>
        <input class="mono_in" name="base_url" inputmode="url" value="${esc(model.base_url || "")}" placeholder="https://api.example.com/v1" autocomplete="off" autocapitalize="off" spellcheck="false" required></label>
      <label class="auth_field"><span>API Key</span>
        <span class="pw"><input class="mono_in" name="api_key" type="password" autocomplete="off" autocapitalize="off" spellcheck="false">
          <button type="button" class="pw_eye" data-reveal aria-label="显示密钥">显示</button></span></label>
      <p class="form_msg" role="alert"></p>
      <div class="modal_btns"><span class="grow"></span>
        <button type="button" class="btn" data-cancel>取消</button>
        <button class="btn primary">测试并保存</button></div>
    </form>`;
  document.body.appendChild(dialog);
  const form = $("form", dialog), msg = $(".form_msg", dialog), ok = $("button.primary", dialog);
  const { base_url, api_key } = form.elements;
  const sameHost = () => { try { return saved && new URL(base_url.value.trim()).hostname === new URL(saved.base_url).hostname; } catch { return false; } };
  const keyRule = () => {
    api_key.required = !sameHost();
    api_key.placeholder = !saved ? "sk-..." : sameHost() ? `留空不修改（${saved.key_hint}）` : "换了服务地址，请重新填写";
  };
  wireReveal(dialog);
  base_url.oninput = keyRule;
  keyRule();
  dialog.addEventListener("cancel", (e) => { e.preventDefault(); closeModal(dialog); });
  dialog.addEventListener("close", () => dialog.remove());
  $("[data-cancel]", dialog).onclick = () => closeModal(dialog);
  form.oninput = () => (msg.textContent = "");
  form.onsubmit = async (event) => {
    event.preventDefault();
    msg.textContent = "";
    ok.disabled = true; ok.textContent = "测试并保存中…";
    try {
      await api("/api/admin/settings", { method: "POST", body: { default_model: Object.fromEntries(new FormData(form)) } });
      closeModal(dialog); toast("已测试并保存"); onDone();
    } catch (e) { msg.textContent = e.message; ok.disabled = false; ok.textContent = "测试并保存"; }
  };
  dialog.showModal();
  if (!TOUCH) form.elements.provider_name.focus();
}

function openSmtpModal(smtp, onDone) {
  const sm = smtp || { security: "ssl" };
  const SECURITY = { ssl: "SSL", starttls: "STARTTLS", none: "不加密" };
  const dialog = document.createElement("dialog");
  dialog.className = "modal model_modal";
  dialog.setAttribute("aria-labelledby", "smtp-modal-title");
  dialog.innerHTML = `<form data-smtp>
      <h3 id="smtp-modal-title" tabindex="-1" autofocus>${smtp ? "编辑邮件服务" : "配置邮件服务"}</h3>
      <p class="sub">用于成员注册验证邮箱、绑定邮箱与重置密码，保存前会自动连接测试。</p>
      <div class="form_grid">
        <label class="auth_field"><span>SMTP 服务器</span>
          <input class="mono_in" name="host" value="${esc(sm.host || "")}" placeholder="例如 smtp.qq.com" autocomplete="off" autocapitalize="off" spellcheck="false" required></label>
        <label class="auth_field"><span>加密方式</span>
          <select name="security">${Object.entries(SECURITY).map(([k, v]) => `<option value="${k}" ${sm.security === k ? "selected" : ""}>${v}</option>`).join("")}</select></label>
      </div>
      <div class="form_grid">
        <label class="auth_field"><span>端口</span>
          <input class="mono_in" name="port" type="number" min="1" max="65535" value="${esc(sm.port || "")}" placeholder="留空默认 465 / 587 / 25"></label>
        <label class="auth_field"><span>发件人名称</span>
          <input name="sender_name" value="${esc(sm.sender_name || "")}" placeholder="Studia"></label>
      </div>
      <div class="form_grid">
        <label class="auth_field"><span>账号</span>
          <input class="mono_in" name="username" value="${esc(sm.username || "")}" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="通常是完整的邮箱地址"></label>
        <label class="auth_field"><span>发件地址</span>
          <input class="mono_in" name="sender" value="${esc(sm.sender || "")}" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="留空用账号"></label>
      </div>
      <label class="auth_field"><span>密码 / 授权码</span>
        <span class="pw"><input class="mono_in" name="password" type="password" autocomplete="new-password" placeholder="${smtp?.password_hint ? `留空不修改（${esc(smtp.password_hint)}）` : "邮箱的 SMTP 授权码，不是登录密码"}">
          <button type="button" class="pw_eye" data-reveal aria-label="显示密码">显示</button></span></label>
      <p class="form_msg" role="alert"></p>
      <div class="modal_btns"><span class="grow"></span>
        <button type="button" class="btn" data-cancel>取消</button>
        <button class="btn primary">测试并保存</button></div>
    </form>`;
  document.body.appendChild(dialog);
  const form = $("form", dialog), msg = $(".form_msg", dialog), ok = $("button.primary", dialog);
  wireReveal(dialog);
  dialog.addEventListener("cancel", (e) => { e.preventDefault(); closeModal(dialog); });
  dialog.addEventListener("close", () => dialog.remove());
  $("[data-cancel]", dialog).onclick = () => closeModal(dialog);
  form.oninput = () => (msg.textContent = "");
  form.onsubmit = async (event) => {
    event.preventDefault();
    msg.textContent = "";
    ok.disabled = true; ok.textContent = "测试并保存中…";
    try {
      await api("/api/admin/settings", { method: "POST", body: { smtp: Object.fromEntries(new FormData(form)) } });
      closeModal(dialog); toast("已测试并保存"); onDone();
    } catch (e) { msg.textContent = e.message; ok.disabled = false; ok.textContent = "测试并保存"; }
  };
  dialog.showModal();
  if (!TOUCH) form.elements.host.focus();
}

function openLinuxdoModal(oauth, onDone) {
  const saved = oauth?.linuxdo || null;
  const dialog = document.createElement("dialog");
  dialog.className = "modal model_modal";
  dialog.setAttribute("aria-labelledby", "linuxdo-modal-title");
  dialog.innerHTML = `<form data-linuxdo>
      <h3 id="linuxdo-modal-title" tabindex="-1" autofocus>${saved ? "编辑 Linux DO" : "配置 Linux DO"}</h3>
      <p class="sub">在 <b>connect.linux.do/dash/sso</b> 创建应用，将回调地址设为 <code>${esc(oauth?.callback_url || `${location.origin}/auth/linuxdo/callback`)}</code>，再填写凭证。</p>
      <label class="auth_field"><span>Client ID</span>
        <input class="mono_in" name="client_id" value="${esc(saved?.client_id || "")}" autocomplete="off" autocapitalize="off" spellcheck="false" required></label>
      <label class="auth_field"><span>Client Secret</span>
        <span class="pw"><input class="mono_in" name="client_secret" type="password" autocomplete="new-password" spellcheck="false">
          <button type="button" class="pw_eye" data-reveal aria-label="显示密钥">显示</button></span></label>
      <label class="auth_field"><span>服务端接口地址（选填）</span>
        <input class="mono_in" name="api_base" inputmode="url" value="${esc(saved?.api_base || "")}" placeholder="留空默认 https://connect.linux.do（国内服务器可填反代地址）" autocomplete="off" autocapitalize="off" spellcheck="false"></label>
      <p class="form_msg" role="alert"></p>
      <div class="modal_btns"><span class="grow"></span>
        <button type="button" class="btn" data-cancel>取消</button>
        <button class="btn primary">保存</button></div>
    </form>`;
  document.body.appendChild(dialog);
  const form = $("form", dialog), msg = $(".form_msg", dialog), ok = $("button.primary", dialog);
  const { client_id, client_secret } = form.elements;
  const sameId = () => Boolean(saved && client_id.value.trim() === saved.client_id);
  const secretRule = () => {
    client_secret.required = !sameId();
    client_secret.placeholder = !saved ? "应用密钥" : sameId() ? `留空不修改（${saved.secret_hint}）` : "更换 Client ID 时请重新填写";
  };
  wireReveal(dialog);
  client_id.oninput = secretRule;
  secretRule();
  dialog.addEventListener("cancel", (e) => { e.preventDefault(); closeModal(dialog); });
  dialog.addEventListener("close", () => dialog.remove());
  $("[data-cancel]", dialog).onclick = () => closeModal(dialog);
  form.oninput = () => (msg.textContent = "");
  form.onsubmit = async (event) => {
    event.preventDefault();
    msg.textContent = "";
    ok.disabled = true; ok.textContent = "保存中…";
    try {
      const res = await api("/api/admin/settings", { method: "POST", body: { oauth: { linuxdo: Object.fromEntries(new FormData(form)) } } });
      closeModal(dialog); toast("已保存"); onDone(res);
    } catch (e) { msg.textContent = e.message; ok.disabled = false; ok.textContent = "保存"; }
  };
  dialog.showModal();
  if (!TOUCH) client_id.focus();
}

function openUserLimitModal(u, onDone) {
  const dialog = document.createElement("dialog");
  dialog.className = "modal";
  dialog.setAttribute("aria-labelledby", "user-limit-title");
  dialog.innerHTML = `<form>
      <h3 id="user-limit-title" tabindex="-1" autofocus>设置任务上限</h3>
      <p class="sub">设置 <b>${esc(u.username)}</b> 最多可同时运行的任务数（1–20），留空则沿用站点默认（${esc(u.job_limit)} 个）。</p>
      <label class="auth_field"><span>同时最多任务数</span>
        <input class="mono_in" type="number" min="1" max="20" name="value" value="${esc(u.max_jobs || "")}" placeholder="站点默认：${esc(u.job_limit)}"></label>
      <p class="form_msg" role="alert"></p>
      <div class="modal_btns"><span class="grow"></span>
        <button type="button" class="btn" data-cancel>取消</button>
        <button class="btn primary">保存</button></div>
    </form>`;
  document.body.appendChild(dialog);
  const form = $("form", dialog), msg = $(".form_msg", dialog), ok = $("button.primary", dialog);
  dialog.addEventListener("cancel", (e) => { e.preventDefault(); closeModal(dialog); });
  dialog.addEventListener("close", () => dialog.remove());
  $("[data-cancel]", dialog).onclick = () => closeModal(dialog);
  form.oninput = () => (msg.textContent = "");
  form.onsubmit = async (event) => {
    event.preventDefault();
    ok.disabled = true; ok.textContent = "保存中…";
    try {
      await api(`/api/admin/users/${u.id}/limit`, { method: "POST", body: { max_jobs: form.elements.value.value.trim() } });
      closeModal(dialog); toast("已保存"); onDone();
    } catch (e) { msg.textContent = e.message; ok.disabled = false; ok.textContent = "保存"; }
  };
  dialog.showModal();
  if (!TOUCH) form.elements.value.focus();
}

function openUserPasswordModal(u, onDone) {
  const first = u.has_password === false;
  const dialog = document.createElement("dialog");
  dialog.className = "modal";
  dialog.setAttribute("aria-labelledby", "user-pw-title");
  dialog.innerHTML = `<form novalidate>
      <h3 id="user-pw-title" tabindex="-1" autofocus>${first ? "设置成员密码" : "重置成员密码"}</h3>
      <p class="sub">为 <b>${esc(u.username)}</b> 设置新的登录密码（至少 8 位），保存后立即生效。</p>
      <label class="auth_field"><span>新密码</span>
        <span class="pw"><input name="value" type="password" minlength="8" autocomplete="new-password" placeholder="至少 8 位" required>
          <button type="button" class="pw_eye" data-reveal aria-label="显示密码">显示</button></span></label>
      <p class="form_msg" role="alert"></p>
      <div class="modal_btns"><span class="grow"></span>
        <button type="button" class="btn" data-cancel>取消</button>
        <button class="btn primary">${first ? "设置密码" : "重置密码"}</button></div>
    </form>`;
  document.body.appendChild(dialog);
  const form = $("form", dialog), msg = $(".form_msg", dialog), ok = $("button.primary", dialog);
  wireReveal(dialog);
  dialog.addEventListener("cancel", (e) => { e.preventDefault(); closeModal(dialog); });
  dialog.addEventListener("close", () => dialog.remove());
  $("[data-cancel]", dialog).onclick = () => closeModal(dialog);
  form.oninput = () => (msg.textContent = "");
  form.onsubmit = async (event) => {
    event.preventDefault();
    const value = form.elements.value.value.trim();
    if (value.length < 8) { msg.textContent = "新密码至少 8 位"; form.elements.value.focus(); return; }
    ok.disabled = true; ok.textContent = "重置中…";
    try {
      await api(`/api/admin/users/${u.id}/password`, { method: "POST", body: { password: value } });
      closeModal(dialog); toast("密码已重置"); onDone();
    } catch (e) { msg.textContent = e.message; ok.disabled = false; ok.textContent = "重置密码"; }
  };
  dialog.showModal();
  if (!TOUCH) form.elements.value.focus();
}

const HEALTH = { ok: ["ok", "可用"], error: ["error", "出错"] };
function renderModels(head, models, again = true) {
  const host = (url) => { try { return new URL(url).host; } catch { return url; } };
  const row = (m) => {
    const [cls, label] = HEALTH[m.health] || ["", "未测试"];
    return `<div class="model ai ${m.active ? "on" : ""}" data-id="${esc(m.id)}">
      <span class="m1"><b>${esc(m.provider || "未命名服务")}</b>${m.deletable ? "" : `<span class="pill">${session.mode === "hosted" ? "管理员提供" : "内置"}</span>`}
        <small>${esc(m.model)} · ${esc(host(m.base_url))} · ${esc(m.key_hint)}</small></span>
      <span class="health ${cls}" title="${esc(m.health_message)}">${label}</span>
      <span class="row_btns">${m.active ? '<span class="in_use">使用中</span>' : '<button class="btn small primary" data-activate>改用</button>'}
        <button class="btn small" data-test>测试</button>${m.deletable ? '<button class="btn small" data-edit>编辑</button>' : ""}</span></div>`;
  };
  const list = models || [];
  quiet = again;
  setPage(`${head}<div class="section">${PHONE.matches ? '<span class="grow"></span>' : "<h2>AI 模型</h2>"}<button class="link" data-add>＋ 添加模型</button></div>
    <div class="models">${list.map(row).join("") || '<div class="model plain"><span class="m1"><small class="sans">还没有可用的模型</small></span></div>'}</div>`);
  quiet = false;
  const reload = async () => {
    try { state.settings = await api("/api/settings"); renderModels(head, state.settings.models); } catch (e) { toast(e.message); }
  };
  $("[data-add]", page).onclick = () => openModelModal(null, reload);
  page.querySelectorAll(".model[data-id]").forEach((rowEl) => {
    const id = rowEl.dataset.id, m = models.find((x) => x.id === id);
    const use = $("[data-activate]", rowEl);
    if (use) use.onclick = async () => {
      try { await api("/api/settings/models/activate", { method: "POST", body: { id } }); toast("已切换模型"); reload(); } catch (e) { toast(e.message); }
    };
    const edit = $("[data-edit]", rowEl);
    if (edit) edit.onclick = () => openModelModal(m, reload);
    $("[data-test]", rowEl).onclick = async () => {
      const chip = $(".health", rowEl);
      chip.className = "health busy"; chip.textContent = "测试中";
      try { const r = await api(`/api/settings/models/${id}/test`, { method: "POST" }); toast(r.health === "ok" ? "连接正常" : r.message); } catch (e) { toast(e.message); }
      reload();
    };
  });
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
  const head = `<div class="qa_head"><div class="qa_head_main"><span class="qa_score"><b>${earned ? pts(earned.interactive) : "—"}</b><span class="of">/${c.shares?.interactive || 10}</span> 分</span>
    <small class="sans">斜纹：今日发布</small></div>${qaClock(p)}</div>`;
  const ask = qaLane("ask", room, { title: "提问", valid: q?.questions, today: today.ask,
    reason: draft?.loading ? `正在出第 ${draft.loading}/${draft.total} 条…` : askBlock,
    note: draft?.error || `今天还能问 ${room ? room.ask : "—"} 条 · 收获回答 ${q?.received ?? "—"}`,
    button: (n, off) => `<button class="btn" data-qa-draft ${off ? "disabled" : ""}>${texts.length ? "换一批" : `出 ${n} 条题`}</button>`, off: p.rescan });
  const answerFull = (q?.answers || 0) >= QA_LANES.answer.cap;
  const answer = qaLane("answer", room, { title: "回答", valid: q?.answers, today: today.answer, reason: answerBlock,
    note: answerFull ? `回答数量分已满，今天还能再答 ${room ? room.answer : "—"} 条` : `今天还能答 ${room ? room.answer : "—"} 条`,
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
    <div class="section"><h2>已发布</h2></div>${list}`;
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
// Boxes Studia can fill are inked; the rest (mastery, meet sessions) stay outlined.
const SHARES = [["progress", "学习", 1], ["habit", "习惯", 1], ["interactive", "互动", 1], ["knowledge", "掌握度", 0],
  ["test", "测试", 1], ["meet", "见面课", 0], ["final", "期末", 1]];
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
async function loadEarned(p, c, fresh = false) {
  const k = key(p.id, c.id);
  if (loadingEarned.has(k) || (!fresh && (earnedErrors.has(k) || state.earned[k]))) return;
  loadingEarned.add(k);
  if (fresh) earnedErrors.delete(k);
  try { state.earned[k] = (await api(`/api/platforms/${p.id}/score?course=${encodeURIComponent(c.id)}${fresh ? "&fresh=1" : ""}`)).earned; }
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
          ${c.progress == null ? '<span class="digits"><i>—</i></span>' : `<span class="digits">${[...String(c.progress)].map((d) => `<i><span>${esc(d)}</span></i>`).join("")}<small>%</small></span>`}
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
      <div class="section"><h2>学习单元</h2></div>
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
        : x.start ? '<span class="pill blue">输验证码开考</span>'
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
    // The list is kept for a while; an exam opened on the platform or a paper the teacher just added shows after this.
    const refresh = `<button class="link" data-papers-fresh="${esc(k)}" ${loadingPapers.has(k) ? "disabled" : ""}>${loadingPapers.has(k) ? "正在刷新…" : "刷新列表"}</button>`;
    body = categories.map((label) => {
      const list = papers.filter((x) => x.category === label), open = list.filter((x) => x.available);
      const all = open.length && open.every((x) => selected.has(x.id));
      return `<div class="section"><h2>${esc(label)}</h2><span class="aside">${open.length} / ${list.length} 份可选</span>
          ${open.length > 1 && !sheet ? `<button class="link" data-pick-all="${esc(label)}">${all ? "取消全选" : "全选"}</button>` : ""}</div>
        <div class="papers">${list.map(row).join("")}</div>`;
    }).join("") || `<div class="empty">这门课没有作业、测验或考试 · ${refresh}</div>`;
    // While it runs, the player bar below carries the progress and the stop button.
    if (categories.length && !sheet) body += `<div class="dock"><span class="info"><span>${answerBlock ? esc(answerBlock) : n ? `已选 <b>${n}</b> 份` : "勾选要作答的试卷"}</span>${refresh}</span>
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
  // An exam the platform enters with a picture code: the person types it first, as on the platform's own page.
  const answer = async (auto_submit) => {
    const picked = tasks(), gated = (papers || []).filter((y) => y.captcha && picked.includes(y.id)).map((y) => y.id);
    for (const id of gated) if (!(await examCode(p, c, papers.find((y) => y.id === id)))) return;
    // Such an exam goes first, opened while the platform still has its code, not after the other papers.
    startJob({ platform: p.id, course: c.id, type: "answer", tasks: [...gated, ...picked.filter((id) => !gated.includes(id))], auto_submit });
  };
  const save = $("[data-save]", page);
  if (save) save.onclick = () => answer(false);
  const submit = $("[data-submit]", page);
  if (submit) submit.onclick = () => answer(true);
  if (tab === "study") loadUnits(p.id, c.id);
  if (c.shares) loadEarned(p, c);
  if (tab === "answer" && p.features.answer && !papers && !state.paperErrors[k]) loadPapers(p, c);
}

const loadingPapers = new Map(), papersAgain = new Map();  // course -> whether that read skips the server's cache
// again: the list on the page is out of date (a paper was handed in), read it once more even if a read is under way.
// fresh: past the server's cache too (刷新列表, or coming back after opening an exam on the platform).
async function loadPapers(p, c, again = false, fresh = false) {
  const k = key(p.id, c.id);
  if (loadingPapers.has(k)) {
    // A fresh read under way already answers a refresh; a handed-in paper needs a read begun after it.
    if (again || (fresh && !loadingPapers.get(k))) papersAgain.set(k, fresh || papersAgain.get(k) || false);
    return;
  }
  loadingPapers.set(k, fresh);
  if (fresh) repaint();  // 刷新列表 shows it is reading
  try {
    const before = state.papers[k];
    const papers = (await api(`/api/platforms/${p.id}/tasks?course=${encodeURIComponent(c.id)}${fresh ? "&fresh=1" : ""}`)).tasks;
    state.papers[k] = papers;
    delete state.paperErrors[k];
    const selected = selectedOf(k);
    // Starting an exam cannot be undone (its clock runs, an attempt is used): that one is only ever ticked by hand.
    if (!again && !selected.size) papers.filter((x) => x.available && !x.done && !x.start && x.status !== "状态未知").forEach((x) => selected.add(x.id));
    // An exam just opened on the platform is ticked, as it would have been had it been open from the start.
    else if (before) papers.filter((x) => x.available && !x.done && !x.start && before.some((y) => y.id === x.id && !y.available)).forEach((x) => selected.add(x.id));
  } catch (error) {
    // A failed read is not an empty course: keep it unloaded so a retry or the next login reads it again.
    // A failed reread keeps the list already shown.
    if (!again || !state.papers[k]) state.paperErrors[k] = error.message;
    else if (fresh) toast(error.message);
  } finally {
    loadingPapers.delete(k);
    if (papersAgain.has(k)) { const f = papersAgain.get(k); papersAgain.delete(k); loadPapers(p, c, true, f); }
  }
  repaint();
}
// The papers changed on the platform: drop the list, and a read already under way (begun before) runs again.
function stalePapers(pid, cid) {
  const k = key(pid, cid);
  delete state.papers[k];
  delete state.earned[k];
  earnedErrors.delete(k);
  if (loadingPapers.has(k)) papersAgain.set(k, true);
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
  return `<div class="section"><h2>答题卡</h2><span class="aside">${handed}/${rows.length} 份</span></div>
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
    ? `<div class="section"><h2>整门课</h2><span class="aside mono">${t.done}/${t.all} · ${Math.round((t.done / (t.all || 1)) * 100)}%</span></div>${gridHtml(k)}`
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
  document.documentElement.classList.add("locked");
  renderPlayer();
}
function closeSheet() { sheet.classList.remove("open"); document.documentElement.classList.remove("locked"); renderPlayer(); }

setInterval(() => {
  const byId = (id) => state.jobs.find((j) => j.id === id);
  document.querySelectorAll("[data-clock]").forEach((el) => { const j = byId(el.dataset.clock); if (j) el.firstChild.textContent = clock(elapsed(j)); });
  document.querySelectorAll("[data-elapsed]").forEach((el) => { const j = byId(el.dataset.elapsed); if (j) el.textContent = duration(elapsed(j)); });
  document.querySelectorAll("[data-qa-left]").forEach((el) => { const p = platformOf(el.dataset.qaLeft); if (p && qaLeft(p) > 0) el.textContent = hoursLeft(qaLeft(p)); });
  document.querySelectorAll("[data-qa-clock]").forEach((el) => {
    const p = platformOf(el.dataset.qaClock);
    if (!p || p.rescan) return;
    const left = qaLeft(p);
    if (!(left > 0)) return;
    const parts = qaClockParts(left);
    const num = el.querySelector("[data-qa-clock-num]");
    if (num) num.textContent = parts.text;
    const arc = el.querySelector("[data-qa-arc]");
    if (arc) arc.setAttribute("stroke-dashoffset", (QA_RING_C * (1 - parts.ratio)).toFixed(2));
    const h = el.querySelector("[data-qa-h]");
    if (h) h.setAttribute("transform", `rotate(${parts.hDeg.toFixed(1)} 18 18)`);
    const m = el.querySelector("[data-qa-m]");
    if (m) m.setAttribute("transform", `rotate(${parts.mDeg.toFixed(1)} 18 18)`);
    const s = el.querySelector("[data-qa-s]");
    if (s) s.setAttribute("transform", `rotate(${parts.sDeg.toFixed(1)} 18 18)`);
  });
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
// 智慧树 asks for a picture code and the honesty pledge each time an exam is entered, and will not open the paper
// without them; for an exam not yet started, entering is what starts it. The code is read with this account's own
// login and typed by the person; the platform's page also waits 8 s before it takes one. The server first makes the
// platform's own checks: when the exam requires a phone location scan first, this dialog shows the platform's QR
// code and polls until it passes, then moves on to the picture code; when only the platform's page may go on (face
// check…), it says why. Resolves true once the platform accepted the code, false if the person gave up.
function examCode(p, c, paper) {
  return new Promise((resolve) => {
    const dialog = document.createElement("dialog");
    dialog.className = "modal exam_code checking";
    dialog.setAttribute("aria-labelledby", "exam-code-title");
    const captchaSub = (remain) => paper.start
      ? `这场考试还没开考。<b>验证通过后会立即开考</b>：开始计时，并用掉一次考试机会${remain != null ? `（剩 ${remain} 次）` : ""}。`
      : "智慧树每次进入考试都要输入验证码。图是用你的登录取的，通过后才能打开试卷。";
    const locSub = () => `该考试需要开启定位，请使用「知到 App」扫码开启定位，成功后会自动继续。${
      TOUCH ? "（长按保存二维码，在知到 App 里从相册扫码）" : ""}`;
    dialog.innerHTML = `<form><h3 id="exam-code-title" tabindex="-1" autofocus>${paper.start ? "开考验证" : "进入考试验证"}</h3>
        <p class="modal_paper">${esc(paper.name)}</p>
        <p class="sub"></p>
        <div class="exam_checking">正在检查进入条件…</div>
        <p class="exam_warn" hidden></p>
        <div class="exam_loc">
          <div class="qr"><img alt="开启定位二维码"></div>
          <div class="exam_loc_foot"><span class="exam_loc_wait">等待扫码确认…</span><button type="button" class="link" data-new-qr>刷新二维码</button></div>
        </div>
        <div class="auth_field"><div class="field_head"><label for="exam-code-input">验证码</label><button type="button" class="link" data-new-code>看不清，换一张</button></div>
          <span class="code_row"><input id="exam-code-input" name="code" placeholder="输入右侧字符" autocomplete="off" autocapitalize="off" spellcheck="false" maxlength="8">
          <img alt="验证码图片" title="点击换一张" width="112" height="40"></span></div>
        <div class="pledge"><label><input type="checkbox" name="pledge"> 我已阅读并同意</label><a class="link" href="https://www.zhihuishu.com/columnsapp/student/protocal/examPromise.html" target="_blank" rel="noopener noreferrer">《在线考试诚信承诺书》</a></div>
        <p class="form_msg" role="alert"></p>
        <div class="modal_btns"><span class="grow"></span><button type="button" class="btn" data-cancel>取消</button>
          <button class="btn primary" disabled>确定</button></div></form>`;
    document.body.appendChild(dialog);
    const form = $("form", dialog), sub = $(".sub", dialog), img = $(".code_row img", dialog);
    const locImg = $(".exam_loc img", dialog), msg = $(".form_msg", dialog), ok = $("button.primary", dialog);
    const { code, pledge } = form.elements;
    let passed = false, ready = 0, busy = false, closed = false, checkingLoc = false;
    let locPoll = 0, locRefresh = 0, qrAt = 0;
    const stopLoc = () => {
      if (locPoll) { clearInterval(locPoll); locPoll = 0; }
      if (locRefresh) { clearInterval(locRefresh); locRefresh = 0; }
    };
    const onReturn = () => {
      if (document.visibilityState === "visible" && dialog.classList.contains("locating")) checkLocation(true);
    };
    document.addEventListener("visibilitychange", onReturn);
    window.addEventListener("focus", onReturn);
    const tick = setInterval(() => paint(), 500);
    const paint = () => {
      if (dialog.classList.contains("locating")) {
        ok.textContent = busy ? "检查中…" : "我已开启定位";
        ok.disabled = busy;
        return;
      }
      const left = Math.ceil((ready - Date.now()) / 1000);
      ok.textContent = left > 0 ? `确定 (${left})` : "确定";
      ok.disabled = busy || !ready || left > 0;
    };
    const showWarning = (text) => {
      if (!text) return;
      const warn = $(".exam_warn", dialog);
      warn.textContent = text;
      warn.hidden = false;
    };
    const showLocation = (qr) => {
      dialog.classList.remove("checking", "blocked");
      dialog.classList.add("locating");
      code.required = false;
      sub.innerHTML = locSub();
      locImg.src = qr;
      qrAt = Date.now();
      ready = 0;
      paint();
      stopLoc();
      locPoll = setInterval(() => { if (document.visibilityState === "visible") checkLocation(true); }, 4000);
      locRefresh = setInterval(() => {
        if (document.visibilityState === "visible" && !checkingLoc && Date.now() - qrAt >= 85000) refreshLocationQr(true);
      }, 15000);
    };
    const showCode = (image, remain) => {
      stopLoc();
      dialog.classList.remove("checking", "locating", "blocked");
      code.required = true;
      sub.innerHTML = captchaSub(remain);
      img.src = image;
      code.value = "";
      ready = Date.now() + 8000;
      paint();
      code.focus();
    };
    const refreshLocationQr = async (quiet = false) => {
      if (closed || !dialog.classList.contains("locating")) return;
      try {
        const got = await api(`/api/platforms/${p.id}/exam-location`, { method: "POST", body: { course: c.id, task: paper.id } });
        if (closed || !dialog.classList.contains("locating")) return;
        locImg.src = got.qr;
        qrAt = Date.now();
        if (!quiet) msg.textContent = "";
      } catch (error) {
        if (!closed && !quiet) msg.textContent = error.message;
      }
    };
    const checkLocation = async (auto) => {
      if (closed || checkingLoc || !dialog.classList.contains("locating")) return;
      checkingLoc = true;
      if (!auto) { busy = true; msg.textContent = ""; paint(); }
      try {
        const got = await api(`/api/platforms/${p.id}/exam-location?course=${encodeURIComponent(c.id)}&task=${encodeURIComponent(paper.id)}`);
        if (closed || !dialog.classList.contains("locating")) return;
        if (got.passed) {
          stopLoc();
          msg.textContent = "";
          busy = false;
          checkingLoc = false;
          await fetchCode();
          return;
        }
        if (!auto) msg.textContent = "您还未开启定位";
      } catch (error) {
        if (!closed && !auto) msg.textContent = error.message;
      } finally {
        checkingLoc = false;
        if (!auto) { busy = false; paint(); }
      }
    };
    const fetchCode = async () => {
      ready = 0; paint();
      try {
        const got = await api(`/api/platforms/${p.id}/exam-captcha?course=${encodeURIComponent(c.id)}&task=${encodeURIComponent(paper.id)}`);
        if (closed) return;
        showWarning(got.warning);
        if (got.step === "location") { showLocation(got.qr); return; }
        showCode(got.image, got.remain);
      } catch (error) {
        if (closed) return;
        stopLoc();
        dialog.classList.remove("checking", "locating");
        msg.textContent = error.message;
        // The platform's own checks say only its page may go on (face check, old system…): nothing to type here.
        if (error.status === 409 && !img.src) {
          dialog.classList.add("blocked");
          $("[data-cancel]", dialog).textContent = "知道了";
        } else if (!img.src) {
          sub.textContent = "";
        }
      }
    };
    dialog.addEventListener("cancel", (event) => { event.preventDefault(); closeModal(dialog); });
    dialog.addEventListener("close", () => {
      closed = true;
      clearInterval(tick);
      stopLoc();
      document.removeEventListener("visibilitychange", onReturn);
      window.removeEventListener("focus", onReturn);
      dialog.remove();
      resolve(passed);
    });
    $("[data-cancel]", dialog).onclick = () => closeModal(dialog);
    $("[data-new-qr]", dialog).onclick = () => refreshLocationQr(false);
    $("[data-new-code]", dialog).onclick = () => { msg.textContent = ""; fetchCode(); };
    img.onclick = () => { msg.textContent = ""; fetchCode(); };
    form.onsubmit = async (event) => {
      event.preventDefault();
      if (dialog.classList.contains("locating")) { await checkLocation(false); return; }
      if (!code.value.trim()) { msg.textContent = "请输入验证码"; code.focus(); return; }
      if (!pledge.checked) { msg.textContent = "请先阅读并同意《在线考试诚信承诺书》"; return; }
      busy = true; paint();
      try {
        const result = await api(`/api/platforms/${p.id}/exam-captcha`, { method: "POST", body: { course: c.id, task: paper.id, code: code.value.trim() } });
        if (closed) return;
        if (result.ok) { passed = true; closeModal(dialog); return; }
        msg.textContent = result.message;
        showCode(result.image, result.remain);
      } catch (error) { if (!closed) { msg.textContent = error.message; if (/过期/.test(error.message)) fetchCode(); } }
      finally { busy = false; paint(); }
    };
    dialog.showModal();
    fetchCode();
  });
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
      if (state.issueReport && event.issue_check?.items?.length && !event.issue_check.reported) {
        queueIssueModal(event.issue_check);
      }
      setTimeout(repaint, 61000);
    }
  } else if (event.type === "site_jobs") {
    state.siteJobs = Number(event.count) || 0;
    if (location.hash === "#/jobs/all") loadSiteJobs();
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
      else if (name === "profile") VIEWS.profile();
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
  // parked: the server ended this stream because the person opened too many; it reconnects when looked at again.
  let source = null, heard = 0, opened = false, tries = 0, again = 0, parked = false;
  const open = () => {
    clearTimeout(again);
    parked = false;
    heard = Date.now();  // a stream that never opens is retried too
    source?.close();
    source = new EventSource(session.mode === "hosted" ? "/api/events" : `/api/events?t=${encodeURIComponent(TOKEN)}`);
    source.onmessage = (message) => {
      heard = Date.now();
      const event = JSON.parse(message.data);
      if (event.type === "evicted") { parked = true; source.close(); return; }
      if (event.type !== "ping") handleEvent(event);
    };
    // Events sent while the stream was down (or the tab was frozen) are lost; catch up from the server.
    source.onopen = () => { heard = Date.now(); tries = 0; conn.back(); if (opened) refreshState(true).then(repaint); opened = true; };
    // A dropped stream is retried by the browser itself, but an error page (a proxy's 502 while the server restarts,
    // a 401) closes it for good: then try again soon, backing off, rather than wait for the 40-second watchdog.
    // The state read on the way tells a signed-out page to show the sign-in form.
    source.onerror = () => {
      conn.lost();
      if (source.readyState !== EventSource.CLOSED || document.body.classList.contains("signed-out")) return;
      again = setTimeout(() => refreshState().finally(() => { if (!document.body.classList.contains("signed-out")) open(); }),
        Math.min(15000, 1000 * 2 ** tries++));
    };
  };
  open();
  // The server pings every 15 s. A stream silent for 40 s is dead even if the browser hasn't noticed.
  const away = () => parked || document.body.classList.contains("signed-out");
  setInterval(() => { if (Date.now() - heard > 40000 && !away()) { conn.lost(); open(); } }, 10000);
  // Off the network: say so at once (the stream may take a while to notice). Back on: reconnect now, not on the
  // browser's next retry.
  addEventListener("offline", () => conn.lost(true));
  addEventListener("online", () => { if (!away()) open(); });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    if (parked) open();  // its onopen catches up
    else refreshState().then(repaint);
  });
}

/* ---------------------------------------------------------------- login */

async function qrLogin(pid) {
  state.loginToken.cancelled = true;
  // qr: this tab's own scan is under way, so the account event it sends leaves the finish to afterLogin.
  const token = (state.loginToken = { cancelled: false, qr: pid });
  const box = $(".qr", page), status = $("[data-status]", page);
  const say = (title, text, stopped = false) => { status.classList.toggle("stopped", stopped); status.innerHTML = `<b>${esc(title)}</b><p>${esc(text)}</p>`; };
  const setImage = (src) => { box.innerHTML = `<img alt="登录二维码" src="${src}">`; };
  let started, wait = 1500;
  try { started = await api(`/api/platforms/${pid}/login`, { method: "POST" }); setImage(started.qr); }
  catch (error) { token.cancelled = true; say("获取二维码失败", error.message, true); return; }
  while (!token.cancelled) {
    await sleep(wait);
    if (token.cancelled || !box.isConnected) return;
    let result;
    // This page's own code: another tab or device showing a code must not swap it out.
    try { result = await api(`/api/platforms/${pid}/login?id=${encodeURIComponent(started.id || "")}`); } catch (error) { say("网络异常", error.message, true); continue; }
    if (result.qr) setImage(result.qr);
    // Scanned: the tap on the phone is seconds away, so look more often and go in as soon as it lands.
    wait = result.status === "scanned" ? 500 : 1500;
    if (result.status === "scanned") say("已扫码", "请在手机上确认登录。");
    else if (result.status === "refreshed") say("二维码已刷新", "请扫新的二维码。");
    else if (result.status === "failed") { token.cancelled = true; say("登录未完成", result.message || "请点击刷新二维码重试。", true); return; }
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
// The course lists as last read in this tab (per account), so a reload — a phone bringing the tab back — shows them at
// once instead of 正在读取课程…; the fresh read replaces them a moment later.
const courseShelf = () => `studia-courses:${session.user?.id || "local"}`;
function unshelveCourses() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(courseShelf()) || "{}");
    for (const p of state.platforms) if (p.logged_in && Array.isArray(saved[p.id]) && !state.courses[p.id]) state.courses[p.id] = saved[p.id];
  } catch { /* storage blocked: read as before */ }
}
async function readCourses(pid) {
  try {
    state.courses[pid] = (await api(`/api/platforms/${pid}/courses`)).courses;
    try { sessionStorage.setItem(courseShelf(), JSON.stringify(state.courses)); } catch { /* full or blocked */ }
  }
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
    if (typeof data.issue_report === "boolean") state.issueReport = data.issue_report;
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
      if (ended) {
        finishUnits(ended);
        if (state.issueReport && ended.issue_check?.items?.length && !ended.issue_check.reported) {
          queueIssueModal(ended.issue_check);
        }
      }
      stalePapers(gone.platform, gone.course);
    }
    state.jobs = live;
    state.siteJobs = typeof data.site_jobs === "number" ? data.site_jobs : 0;
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
  finderList.innerHTML = groups.join('<div class="psep"></div>') || `<div class="prow_empty">没有找到匹配的课程、试卷或页面</div>`;
  finderList.querySelectorAll("[data-i]").forEach((el) => (el.onclick = () => { closeFinder(); go(finderItems[el.dataset.i].hash); }));
  finderList.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
}
finderInput.addEventListener("input", () => { finderIndex = 0; paintFinder(); });
overlay.addEventListener("click", (event) => { if (event.target === overlay) closeFinder(); });

/* ---------------------------------------------------------------- global input */

document.addEventListener("click", (event) => {
  const t = event.target;
  if (!t.closest("[data-job-menu]")) closeJobMenu();  // its items still act below: the hidden menu keeps them
  if (state.meOpen && !t.closest("[data-me]")) closeMe();
  if (t.closest("[data-me]")) { if (state.meOpen) closeMe(); else { state.meOpen = true; renderSidebar(); } return; }
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
  const papersFresh = t.closest("[data-papers-fresh]");
  if (papersFresh) {
    const [pid, ...rest] = papersFresh.dataset.papersFresh.split(":"), p = platformOf(pid), c = courseOf(pid, rest.join(":"));
    if (p && c) { loadPapers(p, c, true, true); if (c.shares) loadEarned(p, c, true); }
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
  if (event.key === "Escape" && state.meOpen) { closeMe(); return; }
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
  scrollTo({ top: 0, behavior: "instant" });
  if (name === "admin") { if (session.user?.role === "admin") VIEWS.admin(false, a); else go("#/settings"); }
  else if (name === "jobs") { VIEWS.jobs(a); if (a === "all" && session.user?.role === "admin") loadSiteJobs(); }
  else if (name === "profile") { state.accountEdit = state.passwordSent = null; VIEWS.profile(); }
  else if (name === "settings") { state.accountEdit = state.passwordSent = null; VIEWS.settings(a); }
  else if (name === "course") { VIEWS.course(a, decodeURIComponent(b || ""), c); recheckWaiting(); }
  else if (name === "login") VIEWS.login(a, b === "again");
  else if (VIEWS[name]) VIEWS[name]();
  else go(homeOf(currentPlatform()));
}
window.addEventListener("hashchange", route);
window.addEventListener("hashchange", closeJobMenu);

// A paper waiting on the platform (an exam to open there, or its identity check) changes there, not here: coming
// back to this page or to the course's 答题 tab reads the list again past the server's cache, at most every 5 s.
let waitingRead = 0;
function recheckWaiting() {
  const [, name, pid, cid, tab] = parseHash(location.hash);
  if (name !== "course" || tab !== "answer" || document.visibilityState !== "visible" || Date.now() - waitingRead < 5000) return;
  if (document.querySelector("dialog.exam_code[open]")) return;
  const p = platformOf(pid), c = courseOf(pid, decodeURIComponent(cid || ""));
  if (!p || !c || !state.papers[key(pid, c.id)]?.some((x) => x.waiting)) return;
  waitingRead = Date.now();
  loadPapers(p, c, true, true);
}
document.addEventListener("visibilitychange", recheckWaiting);
addEventListener("focus", recheckWaiting);
addEventListener("scroll", closeJobMenu, { passive: true });
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
  unboot();
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
        ${mode === "reset" || mode === "forgot" ? "" : field("username", mode === "setup" ? "管理员用户名" : mode === "login" ? "用户名或邮箱" : "用户名", `required autocomplete="username" autocapitalize="off" ${mode === "login" ? "" : 'minlength="2" maxlength="32"'}`)}
        ${mode === "register" && rules.email ? `${field("email", "邮箱", 'type="email" required autocomplete="email" autocapitalize="off"')}
          <label class="auth_field"><span>验证码</span><span class="pw"><input name="code" required inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="6 位数字">
            <button type="button" class="pw_eye code_send" data-send-code>发送验证码</button></span></label>` : ""}
        ${mode === "forgot" ? "" : field("password", mode === "reset" ? "新密码" : "密码", `type="password" required autocomplete="${mode === "login" ? "current-password" : "new-password"}" ${mode === "login" ? "" : 'minlength="8" placeholder="至少 8 位"'}`)}
        ${mode === "login" ? '<p class="auth_forgot"><button type="button" class="link" data-auth-mode="forgot">忘记密码？</button></p>' : ""}
        ${mode === "setup" || mode === "reset" ? field("again", "再输一次密码", 'type="password" required autocomplete="new-password" minlength="8"') : ""}
        <p class="auth_error" role="alert"></p>
        <button class="btn primary auth_submit">${esc(text.button)}</button>
        ${mode === "login" && session.oauth?.linuxdo ? '<div class="auth_or"><span>或</span></div><a class="btn auth_oauth" href="/auth/linuxdo/start">使用 Linux DO 登录</a>' : ""}
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
    Object.assign(session, { user: me.user, csrf: me.csrf, mail: Boolean(me.mail), oauth: me.oauth || session.oauth });
    return true;
  } catch { return false; }
}

(async function boot() {
  let setup = false, speed = 1;
  if (!MOCK) { try { ({ mode: session.mode, setup, register: session.register = null, oauth: session.oauth = null, speed = 1 } = await api("/api/mode")); } catch { /* old server: local */ } }
  applySpeed(speed);
  if (MOCK && params.has("auth")) { showAuth(params.get("auth") || "login"); return; }
  if (MOCK && params.has("hosted")) session.mode = "hosted";  // ?mock&hosted previews what a hosted site shows
  if (setup) { showAuth("setup"); return; }
  if (RESET && session.mode === "hosted") { showAuth("reset"); return; }  // the link mailed for a new password
  if (session.mode === "hosted" && !(await loadMe())) { showAuth(); return; }
  await refreshState();
  unshelveCourses();
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
  if (OAUTH_NOTICE === "bound") toast("已绑定 Linux DO");
})();
