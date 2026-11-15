// "Baby" panel for Home Assistant: logging and editing of feedings, measurements and charts.
// Dependency-free web component; uses the HA theme variables (light/dark).

// t("text {var}", {var: value}) → text with the {placeholders} filled in
const t = (s, v = {}) => s.replace(/\{(\w+)\}/g, (_, k) => (v[k] ?? ""));

const TYPES = { formula: "Formula", breast_milk: "Breast milk", mixed: "Mixed" };
const CONFIDENCES = { exact: "Exact", estimated: "Estimated", inferred: "Inferred" };
const SOURCES = {
  button: "Button", alexa: "Alexa", notification: "Notification",
  app: "Panel", manual: "Manual", test: "Test",
};
const ML_PER_OZ = 29.5735;
// Entry/display unit (Configure); the database always stores oz
let UNIT = "oz";
const U = () => UNIT;
const isMl = () => UNIT === "ml";
const toUnit = (oz) => (isMl() ? oz * ML_PER_OZ : oz);
const toOz = (v) => (isMl() ? v / ML_PER_OZ : v);
// Number in the unit (no suffix) and amount with suffix
const amountN = (oz, d = 2) => (oz === null || oz === undefined || oz === "" || isNaN(oz)) ? "—"
  : isMl() ? String(Math.round(oz * ML_PER_OZ)) : num(oz, d);
const amount = (oz, d = 2) => { const n = amountN(oz, d); return n === "—" ? n : `${n} ${U()}`; };
const STEP = () => (isMl() ? 5 : 0.25);
const MAXC = () => (isMl() ? 360 : 12);
const DIAPER_TYPES = { pee: "💧 Pee", poop: "💩 Poop", both: "💧💩 Both" };
const COLORS = [["yellow", "Yellow", "#f2c230"], ["green", "Green", "#6f9a3a"], ["brown", "Brown", "#8b5a2b"],
  ["orange", "Orange", "#f08a24"], ["black", "Black", "#222"], ["red", "Red", "#c62828"],
  ["white", "White / gray", "#d9d9d9"], ["not_sure", "Not sure", "transparent"]];
const CONSISTENCIES = [["watery", "Watery"], ["seedy", "Seedy"], ["pasty", "Pasty"], ["hard", "Hard"], ["not_sure", "Not sure"]];
const COLOR_NAME = Object.fromEntries(COLORS.map(([k, t]) => [k, t]));
const CONSISTENCY_NAME = Object.fromEntries(CONSISTENCIES);

const pad = (n) => String(n).padStart(2, "0");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (v, d = 1) => (v === null || v === undefined || v === "" || isNaN(v))
  ? "—" : Number(v).toFixed(d).replace(/\.0+$/, "").replace(/(\.\d*?)0+$/, "$1");
const dateISO = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const toInputLocal = (d) => `${dateISO(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
const toServiceDate = (v) => v.replace("T", " ") + (v.length === 16 ? ":00" : "");
const hhmm = (iso) => { const d = new Date(iso); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const startOfDay = (d) => { const x = new Date(d); x.setHours(0, 0, 0, 0); return x; };
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function relative(iso) {
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  const a = Math.abs(min), h = Math.floor(a / 60), m = a % 60;
  const tt = h ? `${h} h ${pad(m)} min` : `${m} min`;
  return min >= 0 ? t("{t} ago", { t: tt }) : t("in {t}", { t: tt });
}

function ageText(days) {
  if (days === null || days === undefined || isNaN(days)) return "—";
  days = Number(days);
  if (days < 14) return t("{n} days", { n: days });
  const week = Math.floor(days / 7), d = days % 7;
  if (days < 90) return t("{s} wk{d} ({n} days)", { s: week, d: d ? ` ${d} d` : "", n: days });
  const months = Math.floor(days / 30.44);
  return t("{m} months ({s} wk)", { m: months, s: week });
}

// SVG bar chart; stacked series; optional goal line.
// lines: goals that can change per bar [{name, values: [...], class, below}] (stepped line)
function bars({ labels, series, goal, lines = [], unit, height = 180 }) {
  const W = 640, H = height, left = 34, below = 26, above = 12;
  const n = labels.length || 1;
  const totals = labels.map((_, i) => series.reduce((s, se) => s + (se.values[i] || 0), 0));
  const max = Math.max(1, goal || 0, ...totals, ...lines.flatMap((l) => l.values.filter((v) => v))) * 1.12;
  const y = (v) => above + (H - above - below) * (1 - v / max);
  const width = (W - left - 8) / n, bw = Math.max(4, width * 0.66);
  let svg = `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img">`;
  for (let k = 0; k <= 4; k++) {
    const v = (max / 1.12) * k / 4, yy = y(v);
    svg += `<line x1="${left}" x2="${W - 4}" y1="${yy}" y2="${yy}" class="grid"/>`
         + `<text x="${left - 4}" y="${yy + 3}" class="axis" text-anchor="end">${num(v, v < 10 ? 1 : 0)}</text>`;
  }
  labels.forEach((et, i) => {
    const x = left + width * i + (width - bw) / 2;
    let base = 0;
    series.forEach((se) => {
      const v = se.values[i] || 0;
      if (v > 0) {
        svg += `<rect x="${x}" y="${y(base + v)}" width="${bw}" height="${y(base) - y(base + v)}" rx="2" `
             + `style="fill:${se.color};opacity:${se.opacity ?? 1}"><title>${esc(et)}: ${num(v, 2)} ${unit} ${esc(se.name)}</title></rect>`;
      }
      base += v;
    });
    if (totals[i] > 0 && n <= 16) {
      svg += `<text x="${x + bw / 2}" y="${y(totals[i]) - 3}" class="value" text-anchor="middle">${num(totals[i], 1)}</text>`;
    }
    if (n <= 16 || i % Math.ceil(n / 12) === 0) {
      svg += `<text x="${x + bw / 2}" y="${H - 8}" class="axis" text-anchor="middle">${esc(et)}</text>`;
    }
  });
  lines.forEach((l) => {
    let d = "", last = null;
    l.values.forEach((v, i) => {
      if (!v) { last = null; return; }
      const x0 = left + width * i, x1 = x0 + width, yy = y(v);
      d += `${last === null ? "M" : "L"}${x0},${yy} L${x1},${yy} `;
      last = v;
    });
    const lastValue = [...l.values].reverse().find((v) => v);
    if (!d || !lastValue) return;
    svg += `<path d="${d}" class="${l.class}" fill="none"><title>${esc(l.name)}</title></path>`
         + `<text x="${W - 6}" y="${y(lastValue) + (l.below ? 13 : -4)}" class="${l.class}-text" text-anchor="end">${esc(l.name)} ${num(lastValue, 1)}</text>`;
  });
  if (goal) {
    svg += `<line x1="${left}" x2="${W - 4}" y1="${y(goal)}" y2="${y(goal)}" class="goal"/>`
         + `<text x="${W - 6}" y="${y(goal) - 4}" class="goal-text" text-anchor="end">${t("goal")} ${num(goal, 1)}</text>`;
  }
  return svg + "</svg>";
}

// SVG line chart (numeric x = age in days).
function line({ dots, unit, height = 170 }) {
  if (dots.length === 0) return `<p class="empty">${t("No data yet.")}</p>`;
  const W = 640, H = height, left = 40, below = 24, above = 12;
  const xs = dots.map((p) => p.x), ys = dots.map((p) => p.y);
  const x0 = Math.min(0, ...xs), x1 = Math.max(x0 + 7, ...xs);
  const y0 = Math.min(...ys) * 0.97, y1 = Math.max(...ys) * 1.03 || 1;
  const X = (v) => left + (W - left - 10) * (v - x0) / (x1 - x0);
  const Y = (v) => above + (H - above - below) * (1 - (v - y0) / ((y1 - y0) || 1));
  let svg = `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img">`;
  for (let k = 0; k <= 3; k++) {
    const v = y0 + (y1 - y0) * k / 3;
    svg += `<line x1="${left}" x2="${W - 4}" y1="${Y(v)}" y2="${Y(v)}" class="grid"/>`
         + `<text x="${left - 4}" y="${Y(v) + 3}" class="axis" text-anchor="end">${num(v, 2)}</text>`;
  }
  svg += `<polyline points="${dots.map((p) => `${X(p.x)},${Y(p.y)}`).join(" ")}" class="line"/>`;
  dots.forEach((p) => {
    svg += `<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="4" class="dot"><title>${t("Day")} ${p.x}: ${num(p.y, 2)} ${unit}</title></circle>`
         + `<text x="${X(p.x)}" y="${H - 8}" class="axis" text-anchor="middle">${p.x}d</text>`;
  });
  return svg + "</svg>";
}

// ---------- Milestones: catalog in www/milestones.json ----------
// Week in which each CDC checkpoint falls (most babies already do it by that age)
const WEEK_CONTROL = [[0, 0], [2, 9], [4, 18], [6, 27], [9, 39], [12, 53]];
const WEEK_END = 53;
const toWeek = (p) => (p.months ? WEEK_CONTROL.find(([m]) => m === p.months)[1] : WEEK_END);
const fromWeek = (p) => p.from_weeks ?? WEEK_CONTROL[WEEK_CONTROL.findIndex(([m]) => m === p.months) - 1][1];
const COLOR_AREA = { social: "var(--breast_milk-color, #e91e63)", communication: "var(--info-color, #039be5)",
  exploring: "var(--warning-color, #ff9800)", movement: "var(--success-color, #43a047)" };
const STROKE_AREA = { social: "", communication: "6 3", exploring: "2 3", movement: "10 3 2 3" };

// Curve per area: cumulative marked milestones by age in weeks, up to the current week
function curveAreas(series, weekToday) {
  const W = 640, H = 200, left = 30, below = 24, above = 10;
  const maxY = Math.max(1, ...series.map((s) => s.weeks.length));
  const X = (w) => left + (W - left - 10) * w / WEEK_END;
  const Y = (v) => above + (H - above - below) * (1 - v / maxY);
  let svg = `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="${esc(t("Milestones marked by area, by age"))}">`;
  new Set([0, 1, 2, 3].map((k) => Math.round(maxY * k / 3))).forEach((v) => {
    svg += `<line x1="${left}" x2="${W - 4}" y1="${Y(v)}" y2="${Y(v)}" class="grid"/><text x="${left - 4}" y="${Y(v) + 3}" class="axis" text-anchor="end">${v}</text>`;
  });
  WEEK_CONTROL.forEach(([m, w]) => { svg += `<text x="${X(w)}" y="${H - 8}" class="axis" text-anchor="middle">${m}${t("m")}</text>`; });
  const endWeek = Math.min(weekToday, WEEK_END);
  series.forEach((s) => {
    let n = 0, d = `M${X(0)} ${Y(0)}`;
    s.weeks.slice().sort((a, b) => a - b).forEach((w) => { n += 1; d += ` H${X(w)} V${Y(n)}`; });
    d += ` H${X(endWeek)}`;
    svg += `<path d="${d}" fill="none" stroke="${COLOR_AREA[s.id]}" stroke-width="2.5" stroke-dasharray="${STROKE_AREA[s.id]}"><title>${esc(s.name)}: ${n}</title></path>`;
  });
  return svg + "</svg>";
}

class BabyPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "today";
    this._day = startOfDay(new Date());
    this._period = "day";
    this._feedingsDay = [];
    this._measurements = [];
    this._ready = false;
  }

  set panel(p) {
    // One panel for all babies; the last one chosen is remembered on this device
    this._babies = p.config.babies || [p.config];
    let sel = null;
    try { sel = localStorage.getItem("baby_tracker_baby"); } catch (e) { /* no storage available */ }
    this._chooseBaby(this._babies.find((b) => b.entry_id === sel) || this._babies[0], false);
  }

  _chooseBaby(b, repaint = true) {
    this._cfg = b;
    UNIT = b.unit === "ml" ? "ml" : "oz";
    try { localStorage.setItem("baby_tracker_baby", b.entry_id); } catch (e) { /* no storage available */ }
    if (repaint && this._ready) {
      const n = this.shadowRoot.getElementById("title-name"); if (n) n.textContent = b.name;
      this.shadowRoot.querySelectorAll("#selector-baby button").forEach((x) => x.classList.toggle("active", x.dataset.baby === b.entry_id));
      this._updateAge();
      this._paint();
    }
  }

  _updateAge() {
    const te = this.shadowRoot && this.shadowRoot.getElementById("title-age");
    if (te) { const d = this._val("age"); te.textContent = d !== null ? `· ${ageText(d)}` : ""; }
  }
  set narrow(n) { this._narrow = n; if (this._menu) this._menu.narrow = n; }
  set hass(h) {
    this._hass = h;
    if (this._menu) this._menu.hass = h;
    if (!this._ready) { this._ready = true; this._mount(); return; }
    this._updateAge();
    if (this._tab === "today") this._paintSummary();
    if (this._tab === "breast_milk") this._paintKpisBreastMilk();
  }

  connectedCallback() { this._timer = setInterval(() => this._tab === "today" && this._paintSummary(), 30000); }
  disconnectedCallback() {
    clearInterval(this._timer);
    if (this._unsub) { this._unsub(); this._unsub = null; }
  }

  // ---------- utilities ----------
  _st(key) { const id = this._cfg.entities[key]; return id ? this._hass.states[id] : undefined; }
  _val(key) { const s = this._st(key); return s && !["unknown", "unavailable"].includes(s.state) ? s.state : null; }
  _num(key) { const v = this._val(key); return v === null ? null : Number(v); }

  async _service(service, data, answer = false) {
    const r = await this._hass.callWS({
      type: "call_service", domain: "baby_tracker", service: service,
      service_data: { ...data, ...(this._cfg.entry_id ? { baby: this._cfg.entry_id } : {}) }, return_response: answer,
    });
    return answer ? r.response : r;
  }

  _notice(message) {
    this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message: message }, bubbles: true, composed: true }));
  }

  async _action(fn, ok) {
    try { const r = await fn(); if (ok) this._notice(ok); return r; }
    catch (e) { this._notice(`${t("Error")}: ${e.message || e}`); throw e; }
  }

  // ---------- structure ----------
  async _mount() {
    this.shadowRoot.innerHTML = `<style>${STYLES}</style>
      <div class="bar">
        <span id="menu"></span>
        <div class="title"><span id="title-name">${esc(this._cfg.name)}</span> <span class="title-age" id="title-age"></span></div>
      </div>
      ${this._babies.length > 1 ? `<div class="selector-baby" id="selector-baby">${this._babies.map((b) =>
        `<button data-baby="${b.entry_id}" class="${b.entry_id === this._cfg.entry_id ? "active" : ""}">${esc(b.name)}</button>`).join("")}</div>` : ""}
      <nav class="tabs">
        ${[["today", "Today"], ["feedings", "Feedings"], ["breast_milk", "Breast milk"], ["measurements", "Growth"], ["milestones", "Milestones"], ["charts", "Charts"], ["settings", "Settings"]]
          .map(([k, e]) => `<button data-tab="${k}" class="${k === this._tab ? "active" : ""}">${t(e)}</button>`).join("")}
      </nav>
      <main id="content"></main>
      <div id="dialog"></div>`;
    this._menu = document.createElement("ha-menu-button");
    this._menu.hass = this._hass; this._menu.narrow = this._narrow;
    this.shadowRoot.getElementById("menu").appendChild(this._menu);
    const selector = this.shadowRoot.getElementById("selector-baby");
    if (selector) selector.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-baby]"); if (!b) return;
      this._chooseBaby(this._babies.find((x) => x.entry_id === b.dataset.baby));
    });
    this.shadowRoot.querySelector(".tabs").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-tab]"); if (!b) return;
      this._tab = b.dataset.tab;
      this.shadowRoot.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
      this._paint();
    });
    try {
      this._unsub = await this._hass.connection.subscribeEvents(() => {
        if (this._tab === "feedings") this._loadFeedings();
        if (this._tab === "breast_milk") this._loadBreastMilk();
        if (this._tab === "charts") this._paintCharts();
      }, "baby_tracker_feeding_logged");
    } catch (e) { /* no subscription: refreshed when switching tabs */ }
    this._paint();
  }

  _paint() {
    const c = this.shadowRoot.getElementById("content");
    if (this._tab === "today") { c.innerHTML = this._htmlToday(); this._paintSummary(); this._eventosToday(); }
    if (this._tab === "settings") { c.innerHTML = this._htmlSettings(); this._eventosSettings(); }
    if (this._tab === "feedings") { c.innerHTML = `<div id="feedings"></div>`; this._loadFeedings(); }
    if (this._tab === "breast_milk") { c.innerHTML = this._htmlBreastMilk(); this._eventosBreastMilk(); this._loadBreastMilk(); }
    if (this._tab === "measurements") { c.innerHTML = this._htmlMeasurements(); this._eventosMeasurements(); this._loadMeasurements(); }
    if (this._tab === "milestones") { c.innerHTML = `<div id="milestones"></div>`; this._loadMilestones(); }
    if (this._tab === "charts") { c.innerHTML = this._htmlCharts(); this._eventosCharts(); this._paintCharts(); }
  }

  // ---------- Today ----------
  _htmlToday() {
    return `
      <section class="hero" id="hero"></section>
      <section class="card" id="bottle"></section>
      <section class="card" id="diaper"></section>
      <section class="kpis" id="kpis"></section>
      <section class="card">
        <details id="detail">
          <summary>${t("Log with a different time…")}</summary>
          ${this._formFeeding({ ended_at: toInputLocal(new Date()), oz_taken: "", type: "formula" }, "new", true)}
          <button class="primary" id="save-new">${t("Save feeding")}</button>
        </details>
      </section>`;
  }

  _bottle() {
    const s = this._st("bottle_remaining");
    if (!s || ["unknown", "unavailable"].includes(s.state)) return null;
    return { remaining: Number(s.state), ...s.attributes };
  }

  _paintBottle() {
    const el = this.shadowRoot.getElementById("bottle"); if (!el) return;
    const b = this._bottle(), ozDefault = this._num("oz_per_bottle") ?? 3;
    const rs = this._st("stash_oz"), stashN = rs ? rs.attributes.current : 0;
    const remaining = b ? b.remaining : ozDefault;
    // Descending in ½ steps from what is left in the bottle, 5 chips after it (6 options in total);
    // the "What was left" chip below covers the exact remaining amount
    const chips = [];
    for (let v = Math.ceil(remaining * 2) / 2 - 0.5; v >= 0.5 && chips.length < 5; v -= 0.5) {
      chips.push([v, `${Math.floor(v) || ""}${v % 1 ? "½" : ""}`]);
    }
    el.innerHTML = `
      <div class="row-title"><h2>${t("Current bottle")} ${b ? `<span class="badge ${b.type || "formula"}">${TYPES[b.type] || TYPES.formula}</span>` : ""}</h2></div>
      <div class="new">
        <button class="secondary small" id="new-bottle">＋ ${TYPES.formula} ${amount(ozDefault, 1)}</button>
        <button class="secondary small" id="new-breast_milk" ${stashN ? "" : "disabled"}>＋ ${TYPES.breast_milk}${stashN ? ` ${t("({n} in stash)", { n: stashN })}` : ` ${t("(no stash)")}`}</button>
      </div>
      ${b ? `
        <div class="progress large-p"><div style="width:${Math.min(100, b.consumed / b.oz * 100)}%"></div></div>
        <div class="bottle-info"><b>${t("{a} of {b}", { a: amountN(b.consumed, 2), b: amount(b.oz, 2) })}</b>
          <button class="icon pencil" id="edit-oz" title="${t("Change this bottle's size")}" aria-label="${t("Change size")}">✏️</button>
          · ${t("left")} <b>${amount(b.remaining, 2)}</b></div>
        <div class="sub">${b.first_feeding ? t(b.n_feedings === 1 ? "First feeding {h} · 1 feeding" : "First feeding {h} · {n} feedings", { h: hhmm(b.first_feeding), n: b.n_feedings }) : t("Prepared {h} · no feedings yet", { h: hhmm(b.prepared_at) })}
          ${b.use_by ? ` · ${t("use by")} ${hhmm(b.use_by)}` : ""}</div>
        ${b.past_use_by ? `<div class="alert-text">⚠️ ${t("It is past the limit since its first feeding: consider preparing a new one.")}</div>` : ""}`
      : `<div class="sub">${t("No open bottle: the next feeding starts a {c} one.", { c: amount(ozDefault, 1) })}</div>`}
      ${(b && b.paused ? b.paused : []).map((p) => `
        <div class="paused ${p.past_use_by ? "overdue" : ""}">
          <div><b>${t("Paused:")}</b> ${TYPES[p.type] || p.type} · ${t("{a} of {b}", { a: amountN(p.consumed, 2), b: amount(p.oz, 2) })}
            <div class="sub">${p.past_use_by ? `<span class="red">${t("Past its limit ({h}): better discard it.", { h: hhmm(p.use_by) })}</span>` : p.use_by ? t("Use before {h}", { h: hhmm(p.use_by) }) : ""}
              · ${t("any excess from the current one will be added here")}</div></div>
          <div class="actions">
            <button class="chip" data-resume="${p.id}" ${p.past_use_by ? "disabled" : ""}>${t("Resume")}</button>
            <button class="chip danger-chip" data-toss="${p.id}">${t("Discard what is left ({c})", { c: amount(p.remaining, 2) })}</button>
          </div>
        </div>`).join("")}
      <div class="label question">${t("How much did baby drink?")}</div>
      <div class="chips" id="chips-feeding">
        <button class="chip strong" data-oz="rest">${t("What was left ({c})", { c: amount(remaining, 2) })}</button>
        ${chips.map(([v, e]) => `<button class="chip" data-oz="${v}">${isMl() ? amount(v) : `${e} oz`}</button>`).join("")}
        <button class="chip" data-oz="other">${t("Other…")}</button>
      </div>`;
    el.querySelector("#new-bottle").onclick = () => this._newBottle();
    const pencil = el.querySelector("#edit-oz");
    if (pencil) pencil.onclick = async () => {
      // Only this bottle (special case); the default oz in Settings do not change
      const v = prompt(t("How big is this bottle? ({u}; already drank {c})", { u: U(), c: amount(b.consumed, 2) }), amountN(b.oz, 2));
      if (v === null) return;
      const oz = toOz(parseFloat(v.replace(",", ".")));
      if (!(oz > 0 && oz <= 12)) { this._notice(t("Invalid amount")); return; }
      if (oz < b.consumed) { this._notice(t("It cannot be less than what was already drunk ({c})", { c: amount(b.consumed, 2) })); return; }
      await this._action(() => this._service("correct_bottle", { id: b.id, oz }, true), t("This bottle is now {c}", { c: amount(oz, 2) }));
    };
    el.querySelector("#new-breast_milk").onclick = () => this._useStash(null);
    el.querySelectorAll("[data-resume]").forEach((x) => x.onclick = async () => {
      await this._action(() => this._service("resume_bottle", { id: Number(x.dataset.resume) }, true), t("Back to that bottle"));
    });
    el.querySelectorAll("[data-toss]").forEach((x) => x.onclick = async () => {
      if (!confirm(t("Discard what is left in that bottle?"))) return;
      await this._action(() => this._service("close_bottle", { id: Number(x.dataset.toss) }, true), t("Bottle discarded"));
    });
    el.querySelector("#chips-feeding").onclick = async (e) => {
      const bt = e.target.closest("button[data-oz]"); if (!bt) return;
      if (bt.dataset.oz === "other") {
        const v = prompt(`${t("How much did baby drink?")} (${U()})`, "");
        if (v === null) return;
        const oz = toOz(parseFloat(v.replace(",", ".")));
        if (!(oz > 0 && oz <= 12)) { this._notice(t("Invalid amount")); return; }
        return this._logQuick({ oz_taken: oz });
      }
      this._logQuick(bt.dataset.oz === "rest" ? { oz_leftover: 0 } : { oz_taken: Number(bt.dataset.oz) });
    };
  }

  async _logQuick(data) {
    const buttons = this.shadowRoot.querySelectorAll("#chips-feeding button");
    buttons.forEach((x) => { x.disabled = true; });
    try {
      const r = await this._action(() => this._service("log_feeding", { ...data, source: "app" }, true));
      const b = r.bottle;
      this._notice(t("Drank {c} · bottle {a}/{b}", { c: amount(r.oz_logged, 2), a: amountN(b.consumed, 2), b: amount(b.oz, 2) })
        + (r.new_bottle && r.previous ? ` · ${t("a new bottle was started")}` : ""));
    } finally { buttons.forEach((x) => { x.disabled = false; }); }
  }

  async _newBottle() {
    // The size comes from Settings (oz per bottle); the previous one is left incomplete
    const r = await this._action(() => this._service("new_bottle", {}, true));
    const a = r.previous;
    this._notice(t("New {c} bottle", { c: amount(r.bottle.oz, 1) })
      + (a && a.state === "incomplete" ? ` · ${t("the previous one ended at {a}/{b}", { a: amountN(a.consumed, 2), b: amount(a.oz, 2) })}` : ""));
  }

  _paintSummary() {
    this._paintHero();
    this._paintBottle();
    this._paintDiaper();
    const k = this.shadowRoot.getElementById("kpis"); if (!k) return;
    const ozToday = this._num("oz_today") ?? 0, goal = this._num("goal_oz_day");
    const progress = goal ? Math.min(100, Math.round(ozToday / goal * 100)) : 0;
    const pct = this._num("pct_finished"), rate = this._num("oz_per_hour");
    const ph = this._st("diapers_today"), tp = ph ? ph.attributes : {};
    k.innerHTML = `
      ${this._htmlGoalToday(ozToday) || `<div class="kpi complete">
        <div class="label">${t("Today: {a} of {b} · {c} feedings · {d} bottles · {e} diapers", { a: amountN(ozToday, 1), b: amount(goal, 1), c: this._val("feedings_today") ?? 0, d: this._val("bottles_today") ?? 0, e: this._val("diapers_today") ?? 0 })}</div>
        <div class="progress"><div style="width:${progress}%"></div></div>
        <div class="sub">${t("{p}% of goal", { p: progress })} · ${Math.round(ozToday * ML_PER_OZ)} ml</div>
      </div>`}
      <div class="kpi"><div class="label">${t("Rate (last 24 h)")}</div><div class="num">${amountN(rate, 2)} <small>${U()}/h</small></div>
        <div class="sub">${t("goal")} ${goal ? amount(goal / 24, 2) : "—"}/h</div></div>
      <div class="kpi"><div class="label">${t("Per feeding (7 d)")}</div><div class="num">${amountN(this._num("oz_per_feeding"), 2)} <small>${U()}</small></div>
        <div class="sub">${t("{n} feedings/day · every {h} h", { n: num(this._num("feedings_per_day"), 1), h: num(this._num("interval"), 1) })}</div></div>
      <div class="kpi"><div class="label">${t("Diapers today")}</div><div class="num sm">💧 ${tp.pee ?? 0} · 💩 ${tp.poop ?? 0} · ${t("both")} ${tp.both ?? 0}</div>
        <div class="sub">${t("{n}/day (7 d) · every {h} h", { n: num(this._num("diapers_per_day"), 1), h: num(this._num("diaper_interval"), 1) })}</div></div>
      <div class="kpi"><div class="label">${t("Bottles finished (7 d)")}</div><div class="num">${pct === null ? "—" : `${pct}<small>%</small>`}</div>
        <div class="sub">${t("wasted")} ${amount(this._num("wasted_7d"), 1)}</div></div>
      <div class="kpi"><div class="label">${t("Age")}</div><div class="num sm">${ageText(this._val("age"))}</div></div>
      <div class="kpi"><div class="label">${t("Weight · Length")}</div><div class="num sm">${num(this._num("weight"), 2)} kg · ${num(this._num("height"), 1)} cm</div></div>`;
  }

  // Progress of the day against two goals: minimum and ideal (the smaller and larger of the pediatrician's and the weight-based one)
  _htmlGoalToday(ozToday) {
    const s = this._st("reference_now");
    if (!s || ["unknown", "unavailable"].includes(s.state)) return "";
    const r = { expected_minimum: Number(s.state), ...s.attributes };
    const pctOf = (v) => Math.max(0, Math.min(100, v / r.goal_ideal * 100));
    const range = (a, b) => (a === b ? `~${amount(a, 1)}` : `~${amountN(a, 1)}–${amount(b, 1)}`);
    const singleGoal = r.goal_minimum === r.goal_ideal;
    const sourceMin = r.source_minimum === "weight" ? t("by weight") : t("pediatrician");
    const sourceIdeal = r.source_minimum === "weight" ? t("pediatrician") : t("by weight");
    const states = {
      ideal: ["✅", singleGoal ? t("On pace for the goal") : t("On pace for the ideal")],
      minimum: ["🟡", t("Above the minimum, below the ideal")],
      behind: ["🔴", singleGoal ? t("Behind the goal ({d})", { d: amount(r.diff_min, 1) }) : t("Behind the minimum ({d})", { d: amount(r.diff_min, 1) })],
    };
    const [icon, text] = r.achievement_today === 2 ? ["🎉", singleGoal ? t("Daily goal reached") : t("Daily ideal reached")]
      : r.achievement_today === 1 && !singleGoal ? ["✅", t("Daily minimum reached")] : states[r.state] || states.minimum;
    const perFeeding = (v) => (v === null || v === undefined ? "—" : v === 0 ? "✓"
      : v > r.feeding_cap ? t("over {c} (not reachable without forcing)", { c: amount(r.feeding_cap, 1) }) : `~${amount(v, 1)}`);
    const days = r.days_7d || [];
    return `
      <div class="kpi complete">
        <div class="label">${t("Today: {a} · {c} feedings · {d} bottles · {e} diapers", { a: amount(ozToday, 1), c: this._val("feedings_today") ?? 0, d: this._val("bottles_today") ?? 0, e: this._val("diapers_today") ?? 0 })}</div>
        <div class="progress ref" title="${t("Shaded zone: where intake should be by now")}">
          <div class="fill ${r.state}" style="width:${pctOf(ozToday)}%"></div>
          <div class="band" style="left:${pctOf(r.expected_minimum)}%;width:${Math.max(1, pctOf(r.expected_ideal) - pctOf(r.expected_minimum))}%"></div>
          ${singleGoal ? "" : `<div class="mark" style="left:${pctOf(r.goal_minimum)}%"></div>`}
        </div>
        <div class="state-ref ${r.state}">${icon} ${text}</div>
        <div class="sub">${t("By now intake should be {r}", { r: range(r.expected_minimum, r.expected_ideal) })}</div>
        <div class="sub">${singleGoal
          ? t("Daily goal: {a} ({f})", { a: amount(r.goal_minimum, 1), f: t("pediatrician") }) + ` · ${t("log the weight to also get the weight-based reference")}`
          : t("Daily goal: minimum {a} ({fa}) · ideal {b} ({fb})", { a: amount(r.goal_minimum, 1), fa: sourceMin, b: amount(r.goal_ideal, 1), fb: sourceIdeal })}</div>
        ${r.feedings_remaining ? `<div class="sub">${singleGoal
          ? t("To get there: {a} per feeding over {n} feedings", { a: perFeeding(r.per_feeding_minimum), n: r.feedings_remaining })
          : t("To get there: minimum {a} · ideal {b} per feeding over {n} feedings", { a: perFeeding(r.per_feeding_minimum), b: perFeeding(r.per_feeding_ideal), n: r.feedings_remaining })}</div>` : ""}
        ${(r.next || []).length ? `<div class="next">${r.next.map((p) =>
          `<span class="chip-ref"><b>${hhmm(p.hhmm)}</b> ${range(p.minimum, p.ideal)}</span>`).join("")}</div>` : ""}
        ${days.length ? `<div class="days7"><span class="sub">${t("Last {n} days", { n: days.length })}</span>
          ${days.map((d) => `<span class="dot l${d.achievement}" title="${DAYS[new Date(`${d.date}T12:00`).getDay()]} ${d.date.slice(8)}: ${amount(d.oz, 1)}"></span>`).join("")}
          <span class="sub">${singleGoal ? t("goal {a}/{n}", { a: r.days_minimum_7d, n: days.length })
            : t("minimum {a}/{n} · ideal {b}/{n}", { a: r.days_minimum_7d, b: r.days_ideal_7d, n: days.length })}</span></div>` : ""}
      </div>`;
  }

  // The most important part: last and next feeding
  _paintHero() {
    const el = this.shadowRoot.getElementById("hero"); if (!el) return;
    const last = this._st("last_feeding"), next = this._val("next_feeding");
    const u = last && !["unknown", "unavailable"].includes(last.state) ? last : null;
    const overdue = next && new Date(next) < new Date();
    el.innerHTML = `
      <div class="hero-col">
        <div class="label">${t("Last feeding")}</div>
        <div class="hero-hhmm">${u ? hhmm(u.state) : "—"}</div>
        <div class="sub">${u ? `${relative(u.state)} · ${amount(u.attributes.oz_taken, 2)}` : t("No records")}</div>
      </div>
      <div class="hero-col ${overdue ? "overdue" : ""}">
        <div class="label">${t("Next feeding")}</div>
        <div class="hero-hhmm">${next ? hhmm(next) : "—"}</div>
        <div class="sub">${next ? (overdue ? `${t("due now")} · ${relative(next)}` : relative(next)) : ""}</div>
      </div>`;
  }

  // ---------- Diapers ----------
  _paintDiaper() {
    const el = this.shadowRoot.getElementById("diaper"); if (!el) return;
    const u = this._st("last_diaper"), pee = this._val("last_pee");
    const ok = u && !["unknown", "unavailable"].includes(u.state);
    const a = ok ? u.attributes : {};
    el.innerHTML = `
      <div class="row-title"><h2>🧷 ${t("Diaper")}</h2>
        <span class="sub">${ok ? `${t("last")} ${hhmm(u.state)} (${relative(u.state)}) · ${DIAPER_TYPES[a.type] || ""}${a.color ? ` · ${COLOR_NAME[a.color] || a.color}` : ""}` : t("no records")}</span></div>
      ${pee ? `<div class="sub">${t("Last pee")} ${relative(pee)}</div>` : ""}
      <div class="chips large" id="chips-diaper">
        <button class="chip" data-p="pee">${DIAPER_TYPES.pee}</button>
        <button class="chip" data-p="poop">${DIAPER_TYPES.poop}</button>
        <button class="chip" data-p="both">${DIAPER_TYPES.both}</button>
      </div>`;
    el.querySelector("#chips-diaper").onclick = (e) => {
      const b = e.target.closest("button[data-p]"); if (!b) return;
      this._logDiaper(b.dataset.p);
    };
  }

  async _logDiaper(type, ended_at = null) {
    let extra = {};
    if (type !== "pee") {
      extra = await this._askPoop();
      if (!extra) return;
    }
    const data = { type, source: "app", ...extra, ...(ended_at ? { ended_at } : {}) };
    const p = await this._action(() => this._service("log_diaper", data, true));
    this._notice(`${t("Diaper logged:")} ${DIAPER_TYPES[p.type]}${p.color ? ` · ${COLOR_NAME[p.color]}` : ""}${this._noticeColor(p.color)}`);
    return p;
  }

  _noticeColor(color) {
    const days = this._num("age") ?? 99;
    if (color === "red" || color === "white" || (color === "black" && days > 5)) {
      return ` — ${t("this color is worth mentioning to the pediatrician")}`;
    }
    return "";
  }

  // Poop color and consistency; returns {color, consistency} or null if cancelled
  _askPoop(current = {}) {
    return new Promise((resolver) => {
      // Preselects the baby's usual poop configured in Configure
      const sel = { color: current.color || this._cfg.poop_color || null,
                    consistency: current.consistency || this._cfg.poop_consistency || null };
      const { dlg, close } = this._modal(`
        <h2>${t("What was the poop like?")}</h2>
        <div class="label">${t("Color")}</div>
        <div class="chips" id="op-color">${COLORS.map(([k, e, c]) =>
          `<button class="chip ${sel.color === k ? "active" : ""}" data-c="${k}"><span class="shows" style="background:${c}"></span>${e}</button>`).join("")}</div>
        <div class="label sep-label">${t("Consistency")}</div>
        <div class="chips" id="op-cons">${CONSISTENCIES.map(([k, e]) =>
          `<button class="chip ${sel.consistency === k ? "active" : ""}" data-k="${k}">${e}</button>`).join("")}</div>
        <div class="buttons"><span class="flex"></span>
          <button class="secondary" id="cancel">${t("Cancel")}</button>
          <button class="primary" id="ok-poop">${t("Save")}</button></div>`);
      const mark = (count, attr, val) => count.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x.dataset[attr] === val));
      dlg.querySelector("#op-color").onclick = (e) => { const b = e.target.closest("[data-c]"); if (!b) return; sel.color = b.dataset.c; mark(dlg.querySelector("#op-color"), "c", sel.color); };
      dlg.querySelector("#op-cons").onclick = (e) => { const b = e.target.closest("[data-k]"); if (!b) return; sel.consistency = b.dataset.k; mark(dlg.querySelector("#op-cons"), "k", sel.consistency); };
      dlg.querySelector("#ok-poop").onclick = () => {
        if (!sel.color || !sel.consistency) { this._notice(t("Choose color and consistency (or \"Not sure\")")); return; }
        close(); resolver(sel);
      };
      dlg.querySelector("#cancel").onclick = () => { close(); resolver(null); };
      dlg.querySelector(".background").addEventListener("click", (e) => { if (e.target.classList.contains("background")) resolver(null); });
    });
  }

  _editDiaper(p, base) {
    const isNew = !p;
    const data = isNew
      ? { type: "pee", ended_at: toInputLocal(base), color: this._cfg.poop_color, consistency: this._cfg.poop_consistency }
      : { ...p, ended_at: toInputLocal(new Date(p.ended_at)) };
    const { dlg, close } = this._modal(`
      <h2>${isNew ? t("New diaper") : t("Diaper at {h}", { h: hhmm(p.ended_at) })}</h2>
      <form class="form" id="form-diaper" onsubmit="return false">
        <label class="complete">${t("Time")}<input type="datetime-local" name="ended_at" value="${data.ended_at}"></label>
        <label class="complete">${t("Type")}<select name="type">${Object.entries(DIAPER_TYPES).map(([k, v]) => `<option value="${k}" ${k === data.type ? "selected" : ""}>${v}</option>`).join("")}</select></label>
        <label>${t("Color")}<select name="color"><option value="">—</option>${COLORS.map(([k, e]) => `<option value="${k}" ${k === data.color ? "selected" : ""}>${e}</option>`).join("")}</select></label>
        <label>${t("Consistency")}<select name="consistency"><option value="">—</option>${CONSISTENCIES.map(([k, e]) => `<option value="${k}" ${k === data.consistency ? "selected" : ""}>${e}</option>`).join("")}</select></label>
        <label class="complete">${t("Note")}<input type="text" name="note" value="${esc(data.note || "")}"></label>
      </form>
      <div class="buttons">${isNew ? "" : `<button class="danger" id="delete-diaper">${t("Delete")}</button>`}<span class="flex"></span>
        <button class="secondary" id="cancel">${t("Cancel")}</button><button class="primary" id="save-diaper">${t("Save")}</button></div>`);
    const ready = () => { close(); if (this._tab === "feedings") this._loadFeedings(); };
    dlg.querySelector("#save-diaper").onclick = async () => {
      const f = dlg.querySelector("#form-diaper");
      const d = { ended_at: toServiceDate(f.ended_at.value), type: f.type.value };
      if (d.type !== "pee") {
        if (!f.color.value || !f.consistency.value) { this._notice(t("For poop choose color and consistency (or \"Not sure\")")); return; }
        d.color = f.color.value; d.consistency = f.consistency.value;
      }
      if (f.note.value.trim()) d.note = f.note.value.trim();
      if (isNew) await this._action(() => this._service("log_diaper", { ...d, source: "app" }, true), t("Diaper added") + this._noticeColor(d.color));
      else await this._action(() => this._service("correct_diaper", { id: p.id, ...d }, true), t("Diaper updated") + this._noticeColor(d.color));
      ready();
    };
    const b = dlg.querySelector("#delete-diaper");
    if (b) b.onclick = async () => {
      if (!confirm(t("Delete this diaper?"))) return;
      await this._action(() => this._service("delete_diaper", { id: p.id }, true), t("Diaper deleted"));
      ready();
    };
  }

  _eventosToday() {
    const r = this.shadowRoot;
    r.getElementById("save-new").addEventListener("click", async () => {
      const f = r.getElementById("form-new");
      let data = this._leerForm(f, true);
      if (!data) return;
      data = await this._feedingBreastMilk(data);
      if (!data) return;
      await this._action(() => this._service("log_feeding", { ...data, source: "app" }, true), t("Feeding saved"));
      r.getElementById("detail").open = false;
    });
  }

  // ---------- Feeding form ----------
  _formFeeding(tm, id, withNew = false) {
    return `<form class="form" id="form-${id}" onsubmit="return false">
      <label class="complete">${t("Time")}<input type="datetime-local" name="ended_at" value="${tm.ended_at}" required></label>
      <label>${t("Drank")} (${U()})<input type="number" name="oz_taken" step="${STEP()}" min="${STEP()}" max="${MAXC()}" inputmode="decimal" value="${tm.oz_taken === "" || tm.oz_taken == null ? "" : amountN(tm.oz_taken, 2)}" required></label>
      <label>${t("Type")}<select name="type">${Object.entries(TYPES).map(([k, v]) => `<option value="${k}" ${k === tm.type ? "selected" : ""}>${v}</option>`).join("")}</select></label>
      <label class="complete">${t("Note")}<input type="text" name="note" value="${esc(tm.note || "")}" placeholder="${t("optional")}"></label>
      ${withNew ? `<label class="check complete"><input type="checkbox" name="new_bottle"> ${t("It is from a new bottle")}</label>` : ""}
    </form>`;
  }

  _leerForm(f, withNew = false) {
    if (!f.ended_at.value) { this._notice(t("Enter the time")); return null; }
    const oz = toOz(parseFloat(String(f.oz_taken.value).replace(",", ".")));
    if (!(oz > 0 && oz <= 12)) { this._notice(t("Enter how much was drunk")); return null; }
    const d = { ended_at: toServiceDate(f.ended_at.value), oz_taken: oz, type: f.type.value };
    if (f.note.value.trim()) d.note = f.note.value.trim();
    if (withNew && f.new_bottle && f.new_bottle.checked) d.new_bottle = true;
    return d;
  }

  // ---------- Feedings per day, grouped by bottle ----------
  async _loadFeedings() {
    const count = this.shadowRoot.getElementById("feedings"); if (!count) return;
    const since = this._day, until = addDays(this._day, 1);
    let feedings = [], bottles = [], diapers = [];
    try {
      const range = { since: `${dateISO(since)} 00:00:00`, until: `${dateISO(until)} 00:00:00` };
      feedings = (await this._service("list_feedings", range, true)).feedings;
      diapers = (await this._service("list_diapers", range, true)).diapers;
      bottles = (await this._service("list_bottles",
        { since: `${dateISO(addDays(since, -1))} 00:00:00`, until: range.until }, true)).bottles;
    } catch (e) { this._notice(`${t("Error loading")}: ${e.message}`); }
    this._feedingsDay = feedings;
    this._bottles = Object.fromEntries(bottles.map((b) => [b.id, b]));
    const groups = [];
    feedings.forEach((tm) => {
      let g = groups.find((x) => x.id === (tm.bottle_id || 0));
      if (!g) { g = { id: tm.bottle_id || 0, b: this._bottles[tm.bottle_id], feedings: [] }; groups.push(g); }
      g.feedings.push(tm);
    });
    const total = feedings.reduce((s, tm) => s + tm.oz_taken, 0);
    const goal = this._num("goal_oz_day");
    const isToday = dateISO(this._day) === dateISO(new Date());
    const STATE = { open: t("Current"), finished: t("Finished"), incomplete: t("Incomplete") };
    count.innerHTML = `
      <div class="navday">
        <button id="prev" aria-label="${t("Previous day")}">‹</button>
        <input type="date" id="date" value="${dateISO(this._day)}" max="${dateISO(new Date())}">
        <button id="next" aria-label="${t("Next day")}" ${isToday ? "disabled" : ""}>›</button>
        ${isToday ? "" : `<button id="today" class="chip">${t("Today")}</button>`}
      </div>
      <section class="card">
        <div class="summary-day">
          <div><b>${amountN(total, 1)}</b> ${U()}${goal ? ` ${t("of")} ${amountN(goal, 1)}` : ""}</div>
          <div><b>${feedings.length}</b> ${t("feedings")}</div>
          <div><b>${groups.filter((g) => g.id).length}</b> ${t("bottles")}</div>
        </div>
        ${groups.length ? groups.slice().reverse().map((g) => `
          <div class="group">
            ${g.b ? `<div class="bottle-header" data-bottle="${g.b.id}">
                <span>🍼 <b>${amountN(g.b.consumed, 2)} / ${amount(g.b.oz, 2)}</b> ${TYPES[g.b.type] || ""}</span>
                <span class="badge ${g.b.state}">${STATE[g.b.state] || g.b.state}</span>
                <span class="sub">${g.b.state === "incomplete" ? t("{c} wasted", { c: amount(g.b.wasted, 2) }) : g.b.state === "open" ? t("{c} left", { c: amount(g.b.remaining, 2) }) : ""}</span>
              </div>` : `<div class="bottle-header"><span class="sub">${t("No bottle")}</span></div>`}
            <ul class="list">${g.feedings.slice().reverse().map((tm) => `
              <li data-id="${tm.id}">
                <span class="hhmm">${hhmm(tm.ended_at)}</span>
                <span class="oz">${amount(tm.oz_taken, 2)}</span>
                <span class="goal-t">${TYPES[tm.type] || tm.type}${tm.note ? ` · ${esc(tm.note)}` : ""}</span>
                <span class="badge ${tm.confidence}">${CONFIDENCES[tm.confidence] || tm.confidence}</span>
                <span class="source">${SOURCES[tm.source] || esc(tm.source || "")}</span>
              </li>`).join("")}</ul>
          </div>`).join("") : `<p class="empty">${t("No feedings this day.")}</p>`}
        <button class="secondary" id="add">${t("+ Add feeding to this day")}</button>
      </section>
      <section class="card">
        <div class="row-title"><h2>🧷 ${t("Diapers of the day")}</h2><span class="sub">${diapers.length} · 💧 ${diapers.filter((x) => x.type === "pee").length} · 💩 ${diapers.filter((x) => x.type === "poop").length} · ${t("both")} ${diapers.filter((x) => x.type === "both").length}</span></div>
        ${diapers.length ? `<ul class="list">${diapers.slice().reverse().map((x) => `
          <li data-diaper="${x.id}">
            <span class="hhmm">${hhmm(x.ended_at)}</span>
            <span class="oz">${DIAPER_TYPES[x.type] || x.type}</span>
            <span class="goal-t">${x.color ? `${COLOR_NAME[x.color] || x.color} · ${CONSISTENCY_NAME[x.consistency] || x.consistency || ""}` : ""}${x.note ? ` · ${esc(x.note)}` : ""}</span>
            <span class="source">${esc(x.logged_by || "")}</span>
          </li>`).join("")}</ul>` : `<p class="empty">${t("No diapers this day.")}</p>`}
        <button class="secondary" id="add-diaper">${t("+ Add diaper to this day")}</button>
      </section>`;
    const $ = (id) => count.querySelector(`#${id}`);
    $("prev").onclick = () => { this._day = addDays(this._day, -1); this._loadFeedings(); };
    if (!isToday) {
      $("next").onclick = () => { this._day = addDays(this._day, 1); this._loadFeedings(); };
      $("today").onclick = () => { this._day = startOfDay(new Date()); this._loadFeedings(); };
    }
    $("date").onchange = (e) => { if (e.target.value) { this._day = startOfDay(new Date(e.target.value + "T00:00")); this._loadFeedings(); } };
    count.querySelectorAll("li[data-id]").forEach((li) => {
      li.onclick = () => this._editFeeding(this._feedingsDay.find((tm) => tm.id === Number(li.dataset.id)));
    });
    count.querySelectorAll("[data-bottle]").forEach((el) => {
      el.onclick = () => this._editBottle(this._bottles[Number(el.dataset.bottle)]);
    });
    $("add").onclick = () => {
      const base = isToday ? new Date() : new Date(this._day.getTime() + 12 * 3600 * 1000);
      this._editFeeding(null, base);
    };
    this._diapersDay = diapers;
    count.querySelectorAll("li[data-diaper]").forEach((li) => {
      li.onclick = () => this._editDiaper(this._diapersDay.find((x) => x.id === Number(li.dataset.diaper)));
    });
    $("add-diaper").onclick = () => {
      const base = isToday ? new Date() : new Date(this._day.getTime() + 12 * 3600 * 1000);
      this._editDiaper(null, base);
    };
  }

  _modal(html) {
    const dlg = this.shadowRoot.getElementById("dialog");
    dlg.innerHTML = `<div class="background"><div class="modal" role="dialog" aria-modal="true">${html}</div></div>`;
    const close = () => { dlg.innerHTML = ""; };
    dlg.querySelector(".background").addEventListener("click", (e) => { if (e.target.classList.contains("background")) close(); });
    const c = dlg.querySelector("#cancel"); if (c) c.onclick = close;
    return { dlg, close };
  }

  _editFeeding(tm, base) {
    const isNew = !tm;
    const data = isNew
      ? { ended_at: toInputLocal(base), oz_taken: "", type: "formula" }
      : { ...tm, ended_at: toInputLocal(new Date(tm.ended_at)) };
    const { dlg, close } = this._modal(`
      <h2>${isNew ? t("New feeding") : t("Feeding at {h}", { h: hhmm(tm.ended_at) })}</h2>
      ${this._formFeeding(data, "edit", isNew)}
      ${isNew ? "" : `<label class="confidence">${t("Confidence")}<select id="confidence">${Object.entries(CONFIDENCES)
        .map(([k, v]) => `<option value="${k}" ${k === tm.confidence ? "selected" : ""}>${v}</option>`).join("")}</select></label>
      <p class="sub">${t("Logged by")} ${esc(tm.logged_by || "—")} · ${SOURCES[tm.source] || esc(tm.source || "")}</p>
      <div class="buttons move">
        <button class="secondary" id="move-new">${t("Move to a new bottle")}</button>
        <button class="secondary" id="move-previous">${t("Join the previous bottle")}</button>
      </div>`}
      <div class="buttons">
        ${isNew ? "" : `<button class="danger" id="delete">${t("Delete")}</button>`}
        <span class="flex"></span>
        <button class="secondary" id="cancel">${t("Cancel")}</button>
        <button class="primary" id="save">${t("Save")}</button>
      </div>`);
    const f = dlg.querySelector("#form-edit");
    const confidence = dlg.querySelector("#confidence");
    if (confidence) f.addEventListener("input", (e) => { if (e.target.name === "oz_taken") confidence.value = "exact"; });
    const ready = (msg) => (async () => { close(); this._loadFeedings(); if (msg) this._notice(msg); })();
    dlg.querySelector("#save").onclick = async () => {
      let d = this._leerForm(f, isNew); if (!d) return;
      if (isNew) {
        d = await this._feedingBreastMilk(d); if (!d) return;
        await this._action(() => this._service("log_feeding", { ...d, source: "app" }, true), t("Feeding added"));
      } else {
        d.confidence = confidence.value;
        if (!d.note) d.note = "";
        await this._action(() => this._service("correct_feeding", { id: tm.id, ...d }, true), t("Feeding updated"));
      }
      ready();
    };
    if (isNew) return;
    dlg.querySelector("#delete").onclick = async () => {
      if (!confirm(t("Delete the feeding at {h} ({c})?", { h: hhmm(tm.ended_at), c: amount(tm.oz_taken, 2) }))) return;
      await this._action(() => this._service("delete_feeding", { id: tm.id }, true), t("Feeding deleted"));
      ready();
    };
    dlg.querySelector("#move-new").onclick = async () => {
      await this._action(() => this._service("correct_feeding", { id: tm.id, move: "new" }, true),
        t("Moved (with the following ones from the same bottle) to a new bottle"));
      ready();
    };
    dlg.querySelector("#move-previous").onclick = async () => {
      await this._action(() => this._service("correct_feeding", { id: tm.id, move: "previous" }, true), t("Joined the previous bottle"));
      ready();
    };
  }

  _editBottle(b) {
    if (!b) return;
    const { dlg, close } = this._modal(`
      <h2>${t("Bottle at {h}", { h: hhmm(b.prepared_at) })}</h2>
      <p class="sub">${t(b.n_feedings === 1 ? "{a} of {b} in 1 feeding" : "{a} of {b} in {n} feedings", { a: amountN(b.consumed, 2), b: amount(b.oz, 2), n: b.n_feedings })}
        ${b.first_feeding ? ` · ${hhmm(b.first_feeding)}–${hhmm(b.last_feeding)}` : ""}</p>
      <form class="form" id="form-bottle" onsubmit="return false">
        <label>${t("Size")} (${U()})<input type="number" name="oz" step="${STEP()}" min="${STEP()}" max="${MAXC()}" inputmode="decimal" value="${amountN(b.oz, 2)}"></label>
        <label>${t("Type")}<select name="type">${Object.entries(TYPES).map(([k, v]) => `<option value="${k}" ${k === b.type ? "selected" : ""}>${v}</option>`).join("")}</select></label>
        <label class="complete">${t("Note")}<input type="text" name="note" value="${esc(b.note || "")}"></label>
      </form>
      <div class="buttons">
        ${b.state === "open" ? `<button class="danger" id="close-bottle">${t("Close (discard {c})", { c: amount(b.remaining, 2) })}</button>` : ""}
        ${b.state === "incomplete" ? `<button class="secondary" id="reopen-bottle">${t("Reopen")}</button>` : ""}
        <span class="flex"></span>
        <button class="secondary" id="cancel">${t("Cancel")}</button>
        <button class="primary" id="save-bottle">${t("Save")}</button>
      </div>`);
    const ready = () => { close(); this._loadFeedings(); };
    dlg.querySelector("#save-bottle").onclick = async () => {
      const f = dlg.querySelector("#form-bottle");
      const oz = toOz(parseFloat(f.oz.value));
      const d = { id: b.id, oz, type: f.type.value, note: f.note.value.trim() };
      if (d.type === "breast_milk" && b.type !== "breast_milk" && b.state !== "stash") {
        // Switched to breast milk: did it come from the stash? Then it is deducted from it
        const stashId = await this._chooseStash(true);
        if (stashId === null) return;
        if (stashId !== "no") { d.stash_id = stashId; if (Math.abs(oz - b.oz) < 0.01) delete d.oz; }
      }
      await this._action(() => this._service("correct_bottle", d, true), t("Bottle updated"));
      ready();
    };
    const c = dlg.querySelector("#close-bottle");
    if (c) c.onclick = async () => { await this._action(() => this._service("close_bottle", { id: b.id }, true), t("Bottle closed")); ready(); };
    const ro = dlg.querySelector("#reopen-bottle");
    if (ro) ro.onclick = async () => { await this._action(() => this._service("correct_bottle", { id: b.id, reopen: true }, true), t("Bottle reopened")); ready(); };
  }

  // ---------- Settings ----------
  _htmlSettings() {
    const v = (k) => this._num(k) ?? "";
    return `
      <section class="card">
        <h2>${t("Bottle and pediatrician's advice")}</h2>
        <form class="form" id="form-settings" onsubmit="return false">
          <label>${t("Bottle size")} <small>${t("(stored in oz)")}</small>
            <input type="number" name="oz_per_bottle" step="0.5" min="0.5" max="10" inputmode="decimal" value="${v("oz_per_bottle")}">
            <span class="help">${t("Size of each new bottle.")}</span></label>
          <label>${t("Started formula: limit (h)")}
            <input type="number" name="bottle_limit" step="0.25" min="0.5" max="4" inputmode="decimal" value="${v("bottle_limit")}">
            <span class="help">${t("After this, preparing a new one is suggested.")}</span></label>
          <label>${t("Started breast milk: limit (h)")}
            <input type="number" name="breast_milk_limit" step="0.25" min="0.5" max="4" inputmode="decimal" value="${v("breast_milk_limit")}"></label>
          <label>${t("Breast milk at room temp. (h)")}
            <input type="number" name="room_expiry" step="0.5" min="0.5" max="8" inputmode="decimal" value="${v("room_expiry")}"></label>
          <label>${t("Breast milk in the fridge (days)")}
            <input type="number" name="fridge_expiry" step="0.5" min="0.5" max="8" inputmode="decimal" value="${v("fridge_expiry")}"></label>
          <label>${t("Goal per feeding (oz)")}
            <input type="number" name="goal_oz_feeding" step="0.5" min="0.5" max="10" inputmode="decimal" value="${v("goal_oz_feeding")}"></label>
          <label>${t("Every how many hours")}
            <input type="number" name="prescribed_interval" step="0.5" min="1" max="6" inputmode="decimal" value="${v("prescribed_interval")}"></label>
        </form>
        <p class="sub" id="planned"></p>
        <button class="primary" id="save-settings">${t("Save settings")}</button>
      </section>
      <section class="card"><h2>${t("What the last 7 days say")}</h2><div id="suggestion" class="sub"></div></section>`;
  }

  _eventosSettings() {
    const f = this.shadowRoot.getElementById("form-settings");
    const prev = () => {
      const m = parseFloat(f.goal_oz_feeding.value), i = parseFloat(f.prescribed_interval.value);
      this.shadowRoot.getElementById("planned").textContent = (m && i)
        ? t("Daily goal: {c} ({n} feedings a day). The reminder will fire {h} h after each feeding.", { c: amount(m * 24 / i, 1), n: num(24 / i, 1), h: num(i, 1) })
        : "";
    };
    f.addEventListener("input", prev); prev();
    this.shadowRoot.getElementById("save-settings").onclick = async () => {
      const changes = ["oz_per_bottle", "bottle_limit", "breast_milk_limit", "room_expiry", "fridge_expiry",
        "goal_oz_feeding", "prescribed_interval"]
        .filter((k) => f[k].value !== "" && Number(f[k].value) !== this._num(k));
      if (!changes.length) { this._notice(t("No changes")); return; }
      await this._action(async () => {
        for (const k of changes) {
          await this._hass.callService("number", "set_value", { entity_id: this._cfg.entities[k], value: Number(f[k].value) });
        }
      }, t("Settings saved"));
    };
    this._paintSuggestion();
  }

  _paintSuggestion() {
    const el = this.shadowRoot.getElementById("suggestion"); if (!el) return;
    const ozFeeding = this._num("oz_per_feeding"), perDay = this._num("feedings_per_day"), pct = this._num("pct_finished");
    const wasted = this._num("wasted_7d"), ozBottle = this._num("oz_per_bottle"), goal = this._num("goal_oz_feeding");
    if (ozFeeding === null) { el.textContent = t("Not enough records yet."); return; }
    const lines = [t("Drinks on average <b>{c}</b> per feeding, about <b>{n}</b> times a day.", { c: amount(ozFeeding, 2), n: num(perDay, 1) })];
    if (pct !== null) lines.push(t("Finished <b>{p}%</b> of bottles; <b>{c}</b> of formula was wasted.", { p: pct, c: amount(wasted, 1) }));
    if (pct !== null && pct < 50 && ozBottle) lines.push(t("Many bottles are left unfinished: you could prepare less (≈{c}) to waste less.", { c: amount(Math.max(0.5, ozBottle - 0.5), 1) }));
    if (pct !== null && pct >= 80) lines.push(t("Finishes almost every bottle: worth mentioning to the pediatrician in case an increase is appropriate."));
    if (goal && ozFeeding < goal * 0.6) lines.push(t("Eats in small feedings ({c} vs goal {m}): it is normal to eat more often.", { c: amount(ozFeeding, 2), m: amount(goal, 1) }));
    el.innerHTML = lines.map((l) => `<p>${l}</p>`).join("")
      + `<p class="help">${t("These are references from your records; check any change in amount with your pediatrician.")}</p>`;
  }

  // ---------- Breast milk: stash and pumping ----------
  _htmlBreastMilk() {
    return `
      <section class="kpis" id="kpis-breast_milk"></section>
      <section class="card">
        <div class="row-title"><h2>${t("Stash")}</h2><span class="sub" id="stash-total"></span></div>
        <div id="stash"></div>
        <details id="details-save">
          <summary>${t("＋ Save breast milk bottle")}</summary>
          <form class="form" id="form-save" onsubmit="return false">
            <label>${t("Amount")} (${U()})<input type="number" name="oz" step="${STEP()}" min="${STEP()}" max="${MAXC()}" inputmode="decimal" required></label>
            <label>${t("Where")}<select name="location"><option value="fridge">${t("Fridge")}</option><option value="room">${t("Room temperature")}</option></select></label>
            <label class="complete">${t("Made at")}<input type="datetime-local" name="made_at" value="${toInputLocal(new Date())}"></label>
          </form>
          <button class="primary" id="btn-save">${t("Save to stash")}</button>
        </details>
      </section>
      <section class="card">
        <h2>${t("Log pumping session")}</h2>
        <form class="form" id="form-pump" onsubmit="return false">
          <label class="complete">${t("Ended at")}<input type="datetime-local" name="ended_at" value="${toInputLocal(new Date())}"></label>
          <label>${t("Left")} (${U()})<input type="number" name="oz_left" step="${STEP()}" min="0" max="${MAXC()}" inputmode="decimal"></label>
          <label>${t("Right")} (${U()})<input type="number" name="oz_right" step="${STEP()}" min="0" max="${MAXC()}" inputmode="decimal"></label>
          <label>${t("Duration (min)")}<input type="number" name="duration_min" step="1" min="0" max="180" inputmode="numeric"></label>
          <label>${t("Where it is stored")}<select name="location"><option value="fridge">${t("Fridge")}</option><option value="room">${t("Room temperature")}</option></select></label>
          <label class="check complete"><input type="checkbox" name="save" checked> ${t("Save as stash bottles")}</label>
          <label class="complete">${t("Split into bottles (optional)")}<input type="text" name="split" placeholder="${t("e.g. 2 + 1.5  (empty = one bottle with everything)")}"></label>
        </form>
        <button class="primary" id="btn-pump">${t("Save pumping session")}</button>
        <h2 class="sep">${t("Recent pumping sessions")}</h2>
        <div id="pumpings"></div>
      </section>`;
  }

  _paintKpisBreastMilk() {
    const k = this.shadowRoot.getElementById("kpis-breast_milk"); if (!k) return;
    const s = this._st("stash_oz"), expiry = this._val("stash_expires");
    const current = s ? s.attributes.current : 0, expired = s ? s.attributes.expired : 0;
    const mh = this._num("breast_milk_today") ?? 0, fh = this._num("formula_today") ?? 0;
    k.innerHTML = `
      <div class="kpi"><div class="label">${t("In stash")}</div><div class="num">${amountN(this._num("stash_oz"), 1)} <small>${U()}</small></div>
        <div class="sub">${t(current === 1 ? "1 bottle" : "{n} bottles", { n: current })}${expired ? ` · <span class="red">${t(expired === 1 ? "1 expired" : "{n} expired", { n: expired })}</span>` : ""}</div></div>
      <div class="kpi"><div class="label">${t("Next expiry")}</div><div class="num sm">${expiry ? `${hhmm(expiry)}` : "—"}</div>
        <div class="sub">${expiry ? relative(expiry) : ""}</div></div>
      <div class="kpi"><div class="label">${t("Pumped today")}</div><div class="num">${amountN(this._num("pumped_today"), 1)} <small>${U()}</small></div>
        <div class="sub">${t("average {c}/day (7 d)", { c: amount(this._num("pumped_day"), 1) })}</div></div>
      <div class="kpi"><div class="label">${t("Drank today")}</div><div class="num sm">${t("{a} breast milk · {b} formula", { a: amountN(mh, 1), b: amountN(fh, 1) })}</div>
        <div class="sub">${t("{p}% breast milk · wasted 7 d: {c}", { p: mh + fh ? Math.round(mh / (mh + fh) * 100) : 0, c: amount(this._num("breast_milk_wasted_7d"), 1) })}</div></div>`;
  }

  async _loadBreastMilk() {
    this._paintKpisBreastMilk();
    const today = startOfDay(new Date());
    let stashes = [], pump = [];
    try {
      stashes = (await this._service("list_stashes", {}, true)).stashes;
      pump = (await this._service("list_pumpings",
        { since: `${dateISO(addDays(today, -2))} 00:00:00`, until: `${dateISO(addDays(today, 1))} 00:00:00` }, true)).pumpings;
    } catch (e) { this._notice(`${t("Error loading")}: ${e.message}`); }
    const r = this.shadowRoot;
    const PLACE = { fridge: t("Fridge"), room: t("Room temp.") };
    const total = stashes.filter((b) => !b.expired).reduce((s, b) => s + b.oz, 0);
    r.getElementById("stash-total").textContent = stashes.length ? t("{c} usable", { c: amount(total, 1) }) : "";
    r.getElementById("stash").innerHTML = stashes.length ? `<ul class="list">${stashes.map((b, i) => {
      const d = new Date(b.made_at || b.prepared_at);
      const soon = b.expires_at && !b.expired && (new Date(b.expires_at) - Date.now()) < 6 * 3600 * 1000;
      return `<li class="stash ${b.expired ? "expired" : ""}">
        <span class="hhmm">${amount(b.oz, 2)}</span>
        <span class="oz">${d.getDate()} ${MONTHS[d.getMonth()]} ${hhmm(b.made_at || b.prepared_at)} · <span class="badge ${b.location}">${PLACE[b.location] || "—"}</span></span>
        <span class="goal-t ${b.expired ? "red" : soon ? "orange" : ""}">${b.expired ? `${t("Expired")} ${relative(b.expires_at)}` : b.expires_at ? `${t("Expires")} ${relative(b.expires_at)}` : ""}${i === 0 && !b.expired ? ` · ${t("the oldest")}` : ""}</span>
        <span class="actions">
          <button class="chip" data-use="${b.id}" ${b.expired ? "disabled" : ""}>${t("Use")}</button>
          <button class="chip" data-move="${b.id}" data-a="${b.location === "fridge" ? "room" : "fridge"}">${b.location === "fridge" ? t("To room temp.") : t("To fridge")}</button>
          <button class="chip danger-chip" data-discard="${b.id}">${t("Discard")}</button>
        </span>
      </li>`;
    }).join("")}</ul>` : `<p class="empty">${t("No breast milk in the stash.")}</p>`;
    r.querySelectorAll("[data-use]").forEach((b) => b.onclick = () => this._useStash(Number(b.dataset.use)));
    r.querySelectorAll("[data-move]").forEach((b) => b.onclick = async () => {
      await this._action(() => this._service("move_stash", { id: Number(b.dataset.move), location: b.dataset.a }, true), t("Moved"));
      this._loadBreastMilk();
    });
    r.querySelectorAll("[data-discard]").forEach((b) => b.onclick = async () => {
      if (!confirm(t("Discard this breast milk bottle?"))) return;
      await this._action(() => this._service("discard_stash", { id: Number(b.dataset.discard) }, true), t("Discarded"));
      this._loadBreastMilk();
    });
    r.getElementById("pumpings").innerHTML = pump.length ? `<ul class="list">${pump.slice().reverse().map((e) => {
      const d = new Date(e.ended_at);
      return `<li class="measurement">
        <span class="hhmm">${hhmm(e.ended_at)}</span>
        <span class="oz">${amount(e.oz_total, 2)}</span>
        <span class="goal-t">${DAYS[d.getDay()]} ${d.getDate()} · ${t("L")} ${amountN(e.oz_left, 2)} · ${t("R")} ${amountN(e.oz_right, 2)}${e.duration_min ? ` · ${num(e.duration_min, 0)} min` : ""}</span>
        <button class="icon" data-delete-pump="${e.id}" aria-label="${t("Delete")}">✕</button>
      </li>`;
    }).join("")}</ul>` : `<p class="empty">${t("No pumping sessions in the last 3 days.")}</p>`;
    r.querySelectorAll("[data-delete-pump]").forEach((b) => b.onclick = async () => {
      if (!confirm(t("Delete this pumping session? Its unused stash bottles are removed too."))) return;
      await this._action(() => this._service("delete_pumping", { id: Number(b.dataset.deletePump) }, true), t("Pumping session deleted"));
      this._loadBreastMilk();
    });
  }

  _eventosBreastMilk() {
    const r = this.shadowRoot;
    r.getElementById("btn-save").onclick = async () => {
      const f = r.getElementById("form-save");
      const oz = toOz(parseFloat(String(f.oz.value).replace(",", ".")));
      if (!(oz > 0)) { this._notice(t("Enter the amount")); return; }
      await this._action(() => this._service("save_milk",
        { oz, location: f.location.value, made_at: toServiceDate(f.made_at.value) }, true), t("Saved to stash"));
      f.oz.value = ""; r.getElementById("details-save").open = false;
      this._loadBreastMilk();
    };
    r.getElementById("btn-pump").onclick = async () => {
      const f = r.getElementById("form-pump");
      const n = (x) => (x.value === "" ? null : parseFloat(String(x.value).replace(",", ".")));
      const d = { ended_at: toServiceDate(f.ended_at.value), save: f.save.checked, location: f.location.value };
      if (n(f.oz_left) !== null) d.oz_left = toOz(n(f.oz_left));
      if (n(f.oz_right) !== null) d.oz_right = toOz(n(f.oz_right));
      if (n(f.duration_min) !== null) d.duration_min = n(f.duration_min);
      if (!d.oz_left && !d.oz_right) { this._notice(t("Enter the amount for at least one side")); return; }
      const split = (f.split.value.replace(/,/g, ".").match(/\d+(?:\.\d+)?/g) || []).map(Number).filter((x) => x > 0).map(toOz);
      if (split.length) d.bottles = split;
      const res = await this._action(() => this._service("log_pumping", d, true));
      this._notice(t("Pumped {c}", { c: amount(res.oz_total, 2) }) + (res.bottles.length ? ` · ${t("{n} bottle(s) to the stash", { n: res.bottles.length })}` : ""));
      f.oz_left.value = ""; f.oz_right.value = ""; f.duration_min.value = ""; f.split.value = "";
      f.ended_at.value = toInputLocal(new Date());
      this._loadBreastMilk();
    };
  }

  // If there is a current bottle with milk: true = pause it, false = toss it, null = cancel
  async _askPaused() {
    const b = this._bottle();
    if (!(b && b.remaining > 0)) return true;
    const r = await this._choose(
      t("There is a {type} bottle in progress ({a} of {b}). What should we do with it?", { type: TYPES[b.type] || TYPES.formula, a: amountN(b.consumed, 2), b: amount(b.oz, 2) }),
      [["paused", t("Breast milk first, keep the current one for later"), "primary"],
       ["toss", t("Discard the current one ({c})", { c: amount(b.remaining, 2) }), "danger"]]);
    return r === null ? null : r === "paused";
  }

  // Which stash bottle is used: id, "no" (did not come from the stash) or null (cancel).
  // Without withNone and with a single current bottle, that one is used without asking.
  async _chooseStash(withNone = false) {
    let rs = [];
    try { rs = (await this._service("list_stashes", {}, true)).stashes.filter((b) => !b.expired); }
    catch (e) { this._notice(`${t("Error loading")}: ${e.message}`); return null; }
    if (!rs.length) return withNone ? "no" : null;
    rs.sort((a, b) => new Date(a.expires_at || a.made_at) - new Date(b.expires_at || b.made_at));  // the one that expires first goes first
    if (rs.length === 1 && !withNone) return rs[0].id;
    const PLACE = { fridge: t("Fridge"), room: t("Room temp.") };
    const op = rs.map((b, i) => {
      const d = new Date(b.made_at || b.prepared_at);
      return [String(b.id), `${amount(b.oz, 2)} · ${d.getDate()} ${MONTHS[d.getMonth()]} ${hhmm(b.made_at || b.prepared_at)} · ${PLACE[b.location] || "—"}`
        + (b.expires_at ? ` · ${t("Expires")} ${relative(b.expires_at)}` : ""), i === 0 ? "primary" : "secondary"];
    });
    if (withNone) op.push(["no", t("Not from the stash"), "secondary"]);
    const r = await this._choose(t("Which breast milk stash bottle was used?"), op);
    return r === null || r === "no" ? r : Number(r);
  }

  // Breast-milk feeding that starts a bottle: ask whether it came from the stash so it can be deducted
  async _feedingBreastMilk(d) {
    const b = this._bottle();
    if (d.type !== "breast_milk" || (!d.new_bottle && b && b.remaining > 0 && b.type === "breast_milk")) return d;
    const id = await this._chooseStash(true);
    if (id === null) return null;
    if (id === "no") return { ...d, new_bottle: true };
    const pause = await this._askPaused();
    if (pause === null) return null;
    const { new_bottle, ...rest } = d;
    return { ...rest, stash_id: id, pause_current: pause };
  }

  async _useStash(id) {
    if (!id) { id = await this._chooseStash(); if (!id) return; }
    const b = this._bottle();
    const pause = await this._askPaused();
    if (pause === null) return;
    const r = await this._action(() => this._service("use_stash", { id, pause_current: pause }, true));
    this._notice(t("Current bottle: breast milk {c}", { c: amount(r.bottle.oz, 2) }) + (b && b.remaining > 0 ? ` · ${pause ? t("the previous one is paused") : t("the previous one was discarded")}` : ""));
    if (this._tab === "breast_milk") this._loadBreastMilk();
  }

  // Dialog with options; returns the chosen key or null if cancelled
  _choose(text, options) {
    return new Promise((resolver) => {
      const { dlg, close } = this._modal(`
        <p>${esc(text)}</p>
        <div class="options">${options.map(([k, e, c]) => `<button class="${c}" data-op="${k}">${esc(e)}</button>`).join("")}
          <button class="secondary" id="cancel">${t("Cancel")}</button></div>`);
      dlg.querySelectorAll("[data-op]").forEach((x) => x.onclick = () => { close(); resolver(x.dataset.op); });
      dlg.querySelector("#cancel").onclick = () => { close(); resolver(null); };
      dlg.querySelector(".background").addEventListener("click", (e) => { if (e.target.classList.contains("background")) resolver(null); });
    });
  }


  // ---------- Measurements ----------
  _htmlMeasurements() {
    return `
      <section class="card">
        <h2>${t("New measurement")}</h2>
        <form class="form" id="form-measurement" onsubmit="return false">
          <label class="complete">${t("Date")}<input type="datetime-local" name="date" value="${toInputLocal(new Date())}"></label>
          <label>${t("Weight (kg)")}<input type="number" name="weight_kg" step="0.01" min="0.5" max="30" inputmode="decimal"></label>
          <label>${t("Length (cm)")}<input type="number" name="height_cm" step="0.1" min="20" max="130" inputmode="decimal"></label>
          <label>${t("Head circumference (cm)")}<input type="number" name="head_cm" step="0.1" min="20" max="60" inputmode="decimal"></label>
          <label>${t("Note")}<input type="text" name="note" placeholder="${t("e.g. pediatrician visit")}"></label>
        </form>
        <button class="primary" id="save-measurement">${t("Save measurement")}</button>
      </section>
      <section class="card"><h2>${t("Weight (kg) by age")}</h2><div id="g-weight"></div></section>
      <section class="card"><h2>${t("Length (cm) by age")}</h2><div id="g-height"></div></section>
      <section class="card"><h2>${t("History")}</h2><div id="list-measurements"></div></section>`;
  }

  _eventosMeasurements() {
    const r = this.shadowRoot;
    r.getElementById("save-measurement").onclick = async () => {
      const f = r.getElementById("form-measurement");
      const d = { date: toServiceDate(f.date.value) };
      ["weight_kg", "height_cm", "head_cm"].forEach((k) => { if (f[k].value !== "") d[k] = parseFloat(f[k].value); });
      if (f.note.value.trim()) d.note = f.note.value.trim();
      if (!d.weight_kg && !d.height_cm && !d.head_cm) { this._notice(t("Enter at least weight, length or head circumference")); return; }
      await this._action(() => this._service("log_measurement", d, true), t("Measurement saved"));
      f.reset(); f.date.value = toInputLocal(new Date());
      this._loadMeasurements();
    };
  }

  async _loadMeasurements() {
    try { this._measurements = (await this._service("list_measurements", {}, true)).measurements; }
    catch (e) { this._notice(`${t("Error")}: ${e.message}`); return; }
    const birth = new Date(this._cfg.birth + "T00:00");
    const age = (iso) => Math.max(0, Math.round((startOfDay(new Date(iso)) - birth) / 86400000));
    const pts = (field) => this._measurements.filter((m) => m[field] != null).map((m) => ({ x: age(m.date), y: m[field] }));
    const r = this.shadowRoot;
    r.getElementById("g-weight").innerHTML = line({ dots: pts("weight_kg"), unit: "kg" });
    r.getElementById("g-height").innerHTML = line({ dots: pts("height_cm"), unit: "cm" });
    const list = r.getElementById("list-measurements");
    list.innerHTML = this._measurements.length ? `<ul class="list">${this._measurements.slice().reverse().map((m) => {
      const d = new Date(m.date);
      return `<li class="measurement">
        <span class="hhmm">${d.getDate()} ${MONTHS[d.getMonth()]}</span>
        <span class="oz">${[m.weight_kg != null ? `${num(m.weight_kg, 2)} kg` : "", m.height_cm != null ? `${num(m.height_cm, 1)} cm` : "",
          m.head_cm != null ? `${t("HC")} ${num(m.head_cm, 1)}` : ""].filter(Boolean).join(" · ")}</span>
        <span class="goal-t">${t("{n} days", { n: age(m.date) })}${m.note ? ` · ${esc(m.note)}` : ""}</span>
        <button class="icon" data-delete="${m.id}" aria-label="${t("Delete")}">✕</button>
      </li>`;
    }).join("")}</ul>` : `<p class="empty">${t("No measurements.")}</p>`;
    list.querySelectorAll("[data-delete]").forEach((b) => {
      b.onclick = async () => {
        if (!confirm(t("Delete this measurement?"))) return;
        await this._action(() => this._service("delete_measurement", { id: Number(b.dataset.delete) }, true), t("Measurement deleted"));
        this._loadMeasurements();
      };
    });
  }

  // ---------- Milestones ----------
  _weekOf(date) {
    const birth = new Date(this._cfg.birth + "T00:00");
    return Math.floor(Math.round((startOfDay(date) - birth) / 86400000) / 7);
  }

  async _loadMilestones() {
    try {
      if (!this._catalog) this._catalog = await (await fetch("/baby_tracker_static/milestones.json")).json();
      const list = (await this._service("list_milestones", {}, true)).milestones;
      this._milestones = Object.fromEntries(list.map((h) => [h.milestone_id, h]));
    } catch (e) { this._notice(`${t("Error loading")}: ${e.message}`); return; }
    const today = Math.min(Math.max(this._weekOf(new Date()), 0), WEEK_END - 1);
    if (this._hWeek === undefined || this._hBaby !== this._cfg.entry_id) this._hWeek = today;
    this._hBaby = this._cfg.entry_id;
    this._hOpenBottles = this._hOpenBottles || new Set();
    this._paintMilestones();
  }

  _rowMilestone(p, skill) {
    const h = this._milestones[p.id];
    let goal = "";
    if (h) {
      const d = new Date(h.date + "T00:00");
      const days = Math.round((d - new Date(this._cfg.birth + "T00:00")) / 86400000);
      goal = `${t("Noticed on {d}", { d: `${d.getDate()} ${MONTHS[d.getMonth()]}` })} · ${ageText(days)}`
        + (h.logged_by ? ` · ${esc(h.logged_by)}` : "") + (h.note ? ` · ${esc(h.note)}` : "");
    } else {
      goal = p.months ? t("Most babies by {n} months", { n: p.months }) : t("Optional");
    }
    return `<button class="hi-item ${h ? "made_at" : ""}" role="checkbox" aria-checked="${h ? "true" : "false"}" data-milestone="${p.id}" data-skill="${skill.id}">
      <span class="hi-box" aria-hidden="true">${h ? "✓" : ""}</span>
      <span class="hi-text"><span>${esc(p.text)}</span><span class="sub">${esc(skill.name)} · ${goal}</span></span></button>`;
  }

  _paintMilestones() {
    const count = this.shadowRoot.getElementById("milestones"); if (!count) return;
    const cat = this._catalog, w = this._hWeek, today = this._weekOf(new Date());
    const stage = cat.stages.filter((e) => e.from_weeks <= w).pop();
    const et = stage;
    const weekStart = addDays(new Date(this._cfg.birth + "T00:00"), w * 7);
    const weekEndDate = addDays(weekStart, 6);
    const fmt = (d) => `${d.getDate()} ${MONTHS[d.getMonth()]}`;
    // What is due this week, and what has passed its reference age without being marked (no alarm)
    const ofNow = {}, pending = [];
    cat.skills.forEach((sk) => sk.steps.forEach((p) => {
      const h = this._milestones[p.id];
      const inWindow = fromWeek(p) <= w && w < toWeek(p);
      const markedThis = h && this._weekOf(new Date(h.date + "T00:00")) === w;
      if (inWindow || markedThis) (ofNow[sk.area] = ofNow[sk.area] || []).push(this._rowMilestone(p, sk));
      else if (!h && toWeek(p) <= w && p.months) pending.push(this._rowMilestone(p, sk));
    }));
    const list = (items) => `<ul class="hi-list">${items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
    const pct = (v) => `${v / WEEK_END * 100}%`;
    const series = Object.keys(cat.areas).map((id) => ({ id, name: cat.areas[id],
      weeks: cat.skills.filter((k) => k.area === id).flatMap((k) => k.steps).filter((p) => this._milestones[p.id])
        .map((p) => Math.max(0, this._weekOf(new Date(this._milestones[p.id].date + "T00:00")))) }));
    const total = cat.skills.flatMap((k) => k.steps).length, done = Object.keys(this._milestones).length;
    count.innerHTML = `
      <div class="navday">
        <button id="week-prev" aria-label="${t("Previous week")}" ${w <= 0 ? "disabled" : ""}>‹</button>
        <div class="hi-week"><b>${t("Week {n}", { n: w })}</b><span class="sub">${fmt(weekStart)} – ${fmt(weekEndDate)}${w === today ? ` · ${t("this week")}` : ""}</span></div>
        ${w !== today && today >= 0 && today < WEEK_END ? `<button class="chip" id="week-today">${t("Today")}</button>` : ""}
        <button id="week-next" aria-label="${t("Next week")}" ${w >= WEEK_END - 1 ? "disabled" : ""}>›</button>
      </div>
      <section class="card">
        <div class="sub">${t("Update in progress")}</div>
        <h2>${esc(et.title)}</h2>
        <p class="hi-p">${esc(et.summary)}</p>
      </section>
      <section class="card">
        <h2>${t("May show up at this stage")}</h2>
        ${Object.keys(cat.areas).filter((a) => ofNow[a]).map((a) => `<h3 class="hi-area">${esc(cat.areas[a])}</h3>${ofNow[a].join("")}`).join("")
          || `<p class="empty">${t("No new milestones this week.")}</p>`}
        ${pending.length ? `<details class="hi-pending"><summary>${t("Not marked yet from earlier stages ({n})", { n: pending.length })}</summary>
          <p class="sub">${t("No worries: maybe it already happens and just isn't marked, or it will come at their own pace.")}</p>${pending.join("")}</details>` : ""}
      </section>
      <section class="card"><h2>${t("Normal at this stage")}</h2>${list(et.normal)}</section>
      <section class="card"><h2>${t("Ideas for this stage")}</h2>${list(et.ideas)}</section>
      <section class="card"><h2>${t("Next update")}</h2><p class="hi-p">${esc(et.next)}</p></section>
      <section class="card">
        <div class="row-title"><h2>${t("Progress by skill")}</h2><span class="sub">${t("{a} of {b}", { a: done, b: total })}</span></div>
        <p class="sub">${t("The band is the reference period, each dot a marked milestone and the line today's age.")}</p>
        <div class="hi-axis">${WEEK_CONTROL.map(([m, week]) => `<span style="left:${pct(week)}">${m}${t("m")}</span>`).join("")}</div>
        ${Object.keys(cat.areas).map((a) => `<h3 class="hi-area">${esc(cat.areas[a])}</h3>` + cat.skills.filter((k) => k.area === a).map((k) => {
          const marked = k.steps.filter((p) => this._milestones[p.id]);
          const start0 = Math.min(...k.steps.map(fromWeek)), end0 = Math.max(...k.steps.map(toWeek));
          return `<details class="hi-skill" data-skill="${k.id}" ${this._hOpenBottles.has(k.id) ? "open" : ""}>
            <summary><span class="hi-skill-t"><span>${esc(k.name)}</span><span class="sub">${t("{a} of {b}", { a: marked.length, b: k.steps.length })}</span></span>
              <span class="hi-hint">
                <span class="hi-band" style="left:${pct(start0)};width:${pct(end0 - start0)}"></span>
                ${today >= 0 && today <= WEEK_END ? `<span class="hi-today" style="left:${pct(today)}"></span>` : ""}
                ${marked.map((p) => `<span class="hi-dot" title="${esc(p.text)}" style="left:${pct(Math.max(0, this._weekOf(new Date(this._milestones[p.id].date + "T00:00"))))}"></span>`).join("")}
              </span></summary>
            ${k.steps.map((p) => this._rowMilestone(p, k)).join("")}
          </details>`;
        }).join("")).join("")}
      </section>
      <section class="card">
        <h2>${t("Milestones marked by area")}</h2>
        ${done ? curveAreas(series, today) : `<p class="empty">${t("No data yet.")}</p>`}
        <div class="hi-legend">${series.map((x) => `<span><svg width="26" height="8" aria-hidden="true"><line x1="0" x2="26" y1="4" y2="4" stroke="${COLOR_AREA[x.id]}" stroke-width="2.5" stroke-dasharray="${STROKE_AREA[x.id]}"/></svg>${esc(x.name)}: ${x.weeks.length}</span>`).join("")}</div>
      </section>
      <p class="sub hi-notice">${esc(cat.notice)}</p>
      <p class="sub hi-notice">${t("Milestones and ages:")} <a href="${esc(cat.source.url)}" target="_blank" rel="noopener">${esc(cat.source.name)}</a>. ${t("Stages, tips and weeks are our own guide, not from the CDC.")}</p>`;
    const r = this.shadowRoot;
    const ir = (n) => { this._hWeek = n; this._paintMilestones(); };
    r.getElementById("week-prev").onclick = () => ir(w - 1);
    r.getElementById("week-next").onclick = () => ir(w + 1);
    const bh = r.getElementById("week-today"); if (bh) bh.onclick = () => ir(today);
    count.querySelectorAll(".hi-skill").forEach((d) => d.addEventListener("toggle", () => {
      if (d.open) this._hOpenBottles.add(d.dataset.skill); else this._hOpenBottles.delete(d.dataset.skill);
    }));
    count.querySelectorAll("[data-milestone]").forEach((b) => { b.onclick = () => this._markMilestone(b.dataset.milestone); });
  }

  _markMilestone(id) {
    const step = this._catalog.skills.flatMap((k) => k.steps).find((p) => p.id === id);
    const h = this._milestones[id];
    const today = startOfDay(new Date());
    // In a past week, the suggested day is the last day of that week
    const weekEnd = addDays(new Date(this._cfg.birth + "T00:00"), this._hWeek * 7 + 6);
    const proposed = h ? h.date : dateISO(weekEnd < today ? weekEnd : today);
    const { dlg, close } = this._modal(`
      <h2>${esc(step.text)}</h2>
      <form class="form" id="form-milestone" onsubmit="return false">
        <label class="complete">${t("When did you notice it?")}<input type="date" name="date" value="${proposed}" min="${this._cfg.birth}" max="${dateISO(today)}"></label>
        <label class="complete">${t("Note")}<input type="text" name="note" value="${esc(h ? h.note || "" : "")}" placeholder="${t("optional")}"></label>
      </form>
      <div class="buttons">
        ${h ? `<button class="danger" id="unmark">${t("Unmark")}</button>` : ""}
        <span class="flex"></span>
        <button class="secondary" id="cancel">${t("Cancel")}</button>
        <button class="primary" id="save-milestone">${t("Save")}</button>
      </div>`);
    dlg.querySelector("#save-milestone").onclick = async () => {
      const f = dlg.querySelector("#form-milestone");
      if (!f.date.value) { this._notice(t("Enter the date")); return; }
      const note = f.note.value.trim();
      await this._action(() => this._service("mark_milestone", { milestone_id: id, date: f.date.value, ...(note ? { note } : {}) }, true), t("Milestone installed!"));
      close(); this._loadMilestones();
    };
    const d = dlg.querySelector("#unmark");
    if (d) d.onclick = async () => {
      await this._action(() => this._service("unmark_milestone", { milestone_id: id }, true), t("Milestone unmarked"));
      close(); this._loadMilestones();
    };
  }

  // ---------- Charts ----------
  _htmlCharts() {
    return `
      <div class="segments">
        ${[["day", "Day"], ["week", "Week"], ["month", "Month"]]
          .map(([k, e]) => `<button data-p="${k}" class="${k === this._period ? "active" : ""}">${t(e)}</button>`).join("")}
      </div>
      <section class="card"><h2 id="t-oz"></h2><div id="g-oz"></div>
        <div class="legend"><span class="c1"></span>${TYPES.formula} <span class="c4"></span>${TYPES.breast_milk} <span class="c3"></span>${t("Goal")}</div></section>
      <section class="card"><h2 id="t-feedings"></h2><div id="g-feedings"></div></section>
      <section class="card"><h2>${t("Average per feeding")}</h2><div id="g-ozFeeding"></div></section>
      <section class="card"><h2 id="t-bottle"></h2><div id="g-bottle"></div></section>
      <section class="card"><h2>${t("Bottles finished (%)")}</h2><div id="g-term"></div></section>
      <section class="card"><h2 id="t-wasted"></h2><div id="g-wasted"></div><p class="sub" id="n-wasted"></p></section>
      <section class="card"><h2 id="t-pump"></h2><div id="g-pump"></div></section>
      <section class="card"><h2 id="t-pan"></h2><div id="g-pan"></div>
        <div class="legend"><span class="c5"></span>${t("Pee")} <span class="c6"></span>${t("Poop")} <span class="c7"></span>${t("Both")}</div></section>
      <section class="card"><h2>${t("When does baby eat? (average per hour, last 7 days)")}</h2><div id="g-hhmm-oz"></div></section>
      <section class="card"><h2>${t("When are diapers changed? (average per hour, 7 days)")}</h2><div id="g-hhmm-pan"></div></section>`;
  }

  _eventosCharts() {
    this.shadowRoot.querySelector(".segments").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-p]"); if (!b) return;
      this._period = b.dataset.p;
      this.shadowRoot.querySelectorAll(".segments button").forEach((x) => x.classList.toggle("active", x === b));
      this._paintCharts();
    });
  }

  // Minimum and ideal for each day (each day with the weight it had); for weeks/months, the current goals
  _metasChart(groups, goal) {
    const ref = this._st("reference_now"), a = ref && ref.attributes;
    if (!a || a.goal_minimum === undefined) return { goal: goal ? toUnit(goal) : null };
    const perDate = Object.fromEntries(((this._st("oz_today") || {}).attributes?.series_daily || [])
      .filter((d) => d.goal_minimum).map((d) => [d.date, d]));
    const value = (g, k) => toUnit((this._period === "day" && perDate[dateISO(g.a)]?.[k]) || a[k]);
    const minimum = groups.map((g) => value(g, "goal_minimum")), ideal = groups.map((g) => value(g, "goal_ideal"));
    if (minimum.every((v, i) => v === ideal[i])) return { lines: [{ name: t("goal"), values: ideal, class: "goal" }] };
    return { lines: [
      { name: t("ideal"), values: ideal, class: "goal" },
      { name: t("minimum"), values: minimum, class: "goal-min", below: true },
    ] };
  }

  async _paintCharts() {
    const today = startOfDay(new Date());
    const p = this._period;
    const groups = [];
    if (p === "day") for (let i = 13; i >= 0; i--) {
      const a = addDays(today, -i); groups.push({ a, b: addDays(a, 1), et: i === 0 ? t("today") : `${DAYS[a.getDay()]} ${a.getDate()}` });
    }
    if (p === "week") {
      const monday = addDays(today, -((today.getDay() + 6) % 7));
      for (let i = 11; i >= 0; i--) { const a = addDays(monday, -7 * i); groups.push({ a, b: addDays(a, 7), et: `${a.getDate()} ${MONTHS[a.getMonth()]}` }); }
    }
    if (p === "month") for (let i = 11; i >= 0; i--) {
      const a = new Date(today.getFullYear(), today.getMonth() - i, 1);
      groups.push({ a, b: new Date(a.getFullYear(), a.getMonth() + 1, 1), et: MONTHS[a.getMonth()] });
    }
    let feedings = [], bottles = [], pump = [], pans = [];
    try {
      const range = { since: `${dateISO(groups[0].a)} 00:00:00`, until: `${dateISO(addDays(today, 1))} 00:00:00` };
      feedings = (await this._service("list_feedings", range, true)).feedings;
      bottles = (await this._service("list_bottles", range, true)).bottles;
      pump = (await this._service("list_pumpings", range, true)).pumpings;
      pans = (await this._service("list_diapers", range, true)).diapers;
    } catch (e) { this._notice(`${t("Error")}: ${e.message}`); }
    const birth = startOfDay(new Date(this._cfg.birth + "T00:00"));
    const first = feedings.length ? startOfDay(new Date(feedings[0].ended_at)) : today;
    const sinceData = first > birth ? first : birth;
    const tomorrow = addDays(today, 1);
    const agg = groups.map((g) => {
      const inside = (iso) => { const d = new Date(iso); return d >= g.a && d < g.b; };
      const ts = feedings.filter((tm) => inside(tm.ended_at));
      const bs = bottles.filter((b) => b.state !== "stash" && inside(b.prepared_at));
      const closed = bs.filter((b) => b.state !== "open");
      // Days with data in the group (not counting before the first record or the future)
      const rangeStart = g.a > sinceData ? g.a : sinceData, rangeEnd = g.b < tomorrow ? g.b : tomorrow;
      const days = Math.max(0, Math.round((rangeEnd - rangeStart) / 86400000));
      const div = p === "day" ? 1 : (days || 1);
      const exact = ts.filter((tm) => tm.type !== "breast_milk").reduce((s, tm) => s + tm.oz_taken, 0);
      const rest = ts.filter((tm) => tm.type === "breast_milk").reduce((s, tm) => s + tm.oz_taken, 0);
      const ex = pump.filter((e) => inside(e.ended_at)).reduce((s, e) => s + e.oz_total, 0);
      return {
        et: g.et, exact: exact / div, estimated: rest / div, feedings: ts.length / div,
        ozFeeding: ts.length ? (exact + rest) / ts.length : 0,
        bottles: bs.length / div,
        pct: closed.length ? closed.filter((b) => b.state === "finished").length / closed.length * 100 : 0,
        wasted: bs.reduce((s, b) => s + (b.wasted || 0), 0) / div,
        pumped: ex / div,
        pee: pans.filter((x) => x.type === "pee" && inside(x.ended_at)).length / div,
        poop: pans.filter((x) => x.type === "poop" && inside(x.ended_at)).length / div,
        both: pans.filter((x) => x.type === "both" && inside(x.ended_at)).length / div,
      };
    });
    const goal = this._num("goal_oz_day"), interval = this._num("prescribed_interval"), ozGoal = this._num("goal_oz_feeding");
    const labels = agg.map((x) => x.et);
    const suf = p === "day" ? t("per day") : t("average per day");
    const r = this.shadowRoot, color = "var(--primary-color)";
    const IN_OZ = ["exact", "estimated", "ozFeeding", "wasted", "pumped"];
    const series = (key, name, c, op) => ({ name, values: agg.map((x) => (IN_OZ.includes(key) ? toUnit(x[key]) : x[key])), color: c, opacity: op });
    r.getElementById("t-oz").textContent = `${isMl() ? "ml" : t("Amount")} ${suf}`;
    r.getElementById("g-oz").innerHTML = bars({ labels, unit: U(), ...this._metasChart(groups, goal),
      series: [series("exact", TYPES.formula, color), series("estimated", TYPES.breast_milk, "var(--breast_milk-color, #e91e63)")] });
    r.getElementById("t-feedings").textContent = `${t("Feedings")} ${suf}`;
    r.getElementById("g-feedings").innerHTML = bars({ labels, unit: t("feedings"), goal: interval ? 24 / interval : null,
      series: [series("feedings", t("feedings"), "var(--accent-color, #ff9800)")] });
    r.getElementById("g-ozFeeding").innerHTML = bars({ labels, unit: U(), goal: ozGoal ? toUnit(ozGoal) : null, height: 150,
      series: [series("ozFeeding", t("per feeding"), "var(--success-color, #43a047)")] });
    r.getElementById("t-bottle").textContent = `${t("Bottles")} ${suf}`;
    r.getElementById("g-bottle").innerHTML = bars({ labels, unit: t("bottles"), height: 150,
      series: [series("bottles", t("bottles"), "var(--info-color, #039be5)")] });
    r.getElementById("g-term").innerHTML = bars({ labels, unit: "%", height: 150,
      series: [series("pct", t("finished"), "var(--success-color, #43a047)")] });
    r.getElementById("t-wasted").textContent = `${t("Formula wasted")} (${U()} ${suf})`;
    r.getElementById("g-wasted").innerHTML = bars({ labels, unit: U(), height: 150,
      series: [series("wasted", t("wasted"), "var(--warning-color, #ff9800)")] });
    r.getElementById("t-pump").textContent = `${t("Pumped milk")} (${U()} ${suf})`;
    r.getElementById("g-pump").innerHTML = bars({ labels, unit: U(), height: 150,
      series: [series("pumped", t("pumped"), "var(--breast_milk-color, #e91e63)")] });
    r.getElementById("t-pan").textContent = `${t("Diapers")} ${suf}`;
    r.getElementById("g-pan").innerHTML = bars({ labels, unit: t("diapers"), height: 160,
      series: [series("pee", t("pee"), "#29b6f6"), series("poop", t("poop"), "#8d6e63"), series("both", t("both"), "#ab47bc")] });
    // Distribution by hour of day (last 7 complete days + today)
    const ago7 = addDays(today, -6);
    const t7 = feedings.filter((tm) => new Date(tm.ended_at) >= ago7), p7 = pans.filter((x) => new Date(x.ended_at) >= ago7);
    const days7 = Math.max(1, Math.min(7, Math.round((addDays(today, 1) - (sinceData > ago7 ? sinceData : ago7)) / 86400000)));
    const hours = [...Array(24).keys()];
    const perHour = (list, f) => hours.map((h) => list.filter((x) => new Date(x.ended_at).getHours() === h).reduce((s, x) => s + f(x), 0) / days7);
    const hourLabels = hours.map((h) => (h % 3 === 0 ? `${h}h` : ""));
    r.getElementById("g-hhmm-oz").innerHTML = bars({ labels: hourLabels, unit: U(), height: 150,
      series: [{ name: U(), values: perHour(t7, (tm) => toUnit(tm.oz_taken)), color: "var(--primary-color)" }] });
    r.getElementById("g-hhmm-pan").innerHTML = bars({ labels: hourLabels, unit: t("diapers"), height: 140,
      series: [{ name: t("diapers"), values: perHour(p7, () => 1), color: "#8d6e63" }] });
    const totalWasted = bottles.reduce((s, b) => s + (b.wasted || 0), 0);
    r.getElementById("n-wasted").textContent = t("Total in the period: {c} in {n} incomplete bottles.", { c: amount(totalWasted, 1), n: bottles.filter((b) => b.state === "incomplete").length });
  }
}

const STYLES = `
:host { display:block; min-height:100vh; background:var(--primary-background-color); color:var(--primary-text-color);
  font-family:var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
.bar { display:flex; align-items:center; height:56px; padding:0 8px; background:var(--app-header-background-color, var(--primary-color));
  color:var(--app-header-text-color, #fff); position:sticky; top:0; z-index:3; }
.title { font-size:20px; margin-left:8px; }
.title-age { font-size:14px; opacity:.85; }
.selector-baby { display:flex; gap:6px; padding:6px 12px 8px; background:var(--app-header-background-color, var(--primary-color)); overflow-x:auto; }
.selector-baby button { border:1px solid rgba(255,255,255,.5); background:none; color:var(--app-header-text-color, #fff); border-radius:16px; padding:5px 14px; font-size:14px; white-space:nowrap; }
.selector-baby button.active { background:var(--app-header-text-color, #fff); color:var(--app-header-background-color, var(--primary-color)); font-weight:600; }
.tabs { display:flex; background:var(--app-header-background-color, var(--primary-color)); position:sticky; top:56px; z-index:3; }
.tabs button { flex:1; background:none; border:0; color:var(--app-header-text-color, #fff); opacity:.7; padding:12px 1px;
  font-size:12px; border-bottom:3px solid transparent; cursor:pointer; }
.tabs button.active { opacity:1; border-bottom-color:var(--app-header-text-color, #fff); font-weight:500; }
main { max-width:760px; margin:0 auto; padding:12px 12px 80px; }
.card { background:var(--card-background-color); border-radius:var(--ha-card-border-radius, 12px); padding:14px 16px; margin-bottom:12px;
  box-shadow:var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.15)); }
h2 { font-size:16px; font-weight:500; margin:0 0 10px; }
.kpis { display:grid; grid-template-columns:repeat(2, 1fr); gap:10px; margin-bottom:12px; }
.kpi { background:var(--card-background-color); border-radius:12px; padding:12px; box-shadow:var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.15)); }
.kpi.complete { grid-column:1 / -1; }
.kpi.alert { outline:2px solid var(--error-color, #db4437); }
.label { font-size:12px; color:var(--secondary-text-color); }
.large-num { font-size:22px; font-weight:500; margin-top:2px; }
.num { font-size:20px; font-weight:500; margin-top:2px; } .num.sm { font-size:15px; } small { font-size:12px; color:var(--secondary-text-color); }
.sub { font-size:12px; color:var(--secondary-text-color); margin-top:2px; }
.progress { height:10px; background:var(--divider-color); border-radius:5px; overflow:hidden; margin:8px 0 4px; }
.progress div { height:100%; background:var(--primary-color); transition:width .3s; }
button { font:inherit; cursor:pointer; }
.large { width:100%; }
.primary, .secondary, .danger { padding:10px 16px; border-radius:8px; border:0; font-size:15px; }
.primary { background:var(--primary-color); color:var(--text-primary-color, #fff); width:100%; margin-top:8px; }
.modal .primary { width:auto; margin:0; }
.secondary { background:none; color:var(--primary-color); border:1px solid var(--divider-color); width:100%; margin-top:10px; }
.modal .secondary { width:auto; margin:0; }
.danger { background:none; color:var(--error-color, #db4437); border:1px solid var(--error-color, #db4437); }
details { margin-top:12px; } summary { color:var(--primary-color); cursor:pointer; padding:6px 0; }
.form { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:8px; }
.form .complete { grid-column:1 / -1; }
label { display:flex; flex-direction:column; font-size:12px; color:var(--secondary-text-color); gap:4px; }
input, select { font:inherit; font-size:16px; padding:9px 10px; border-radius:8px; border:1px solid var(--divider-color);
  background:var(--secondary-background-color, transparent); color:var(--primary-text-color); min-width:0; }
.navday { display:flex; gap:8px; align-items:center; margin-bottom:12px; }
.navday button { width:40px; height:40px; border-radius:50%; border:1px solid var(--divider-color); background:var(--card-background-color);
  color:var(--primary-text-color); font-size:22px; line-height:1; }
.navday button:disabled { opacity:.3; } .navday input { flex:1; }
.navday .chip { width:auto; border-radius:20px; font-size:14px; padding:0 14px; }
.summary-day { display:flex; justify-content:space-around; text-align:center; padding-bottom:10px; border-bottom:1px solid var(--divider-color); }
.summary-day b { font-size:20px; }
.list { list-style:none; margin:0; padding:0; }
.list li { display:grid; grid-template-columns:56px 1fr auto; grid-template-areas:"hhmm oz badge" "hhmm goal source";
  gap:2px 8px; padding:10px 4px; border-bottom:1px solid var(--divider-color); cursor:pointer; align-items:center; }
.list li.measurement { grid-template-areas:"hhmm oz badge" "hhmm goal badge"; cursor:default; }
.hhmm { grid-area:hhmm; font-weight:500; font-size:16px; } .oz { grid-area:oz; font-weight:500; }
.goal-t { grid-area:goal; font-size:12px; color:var(--secondary-text-color); }
.badge { grid-area:badge; font-size:11px; padding:2px 8px; border-radius:10px; justify-self:end; }
.badge.exact { background:rgba(67,160,71,.18); color:var(--success-color, #2e7d32); }
.badge.estimated { background:rgba(255,152,0,.2); color:var(--warning-color, #e65100); }
.badge.inferred { background:var(--divider-color); color:var(--secondary-text-color); }
.source { grid-area:source; font-size:11px; color:var(--secondary-text-color); justify-self:end; }
.icon { grid-area:badge; border:0; background:none; color:var(--secondary-text-color); font-size:16px; padding:6px; }
.empty { color:var(--secondary-text-color); text-align:center; padding:16px 0; margin:0; }
.background { position:fixed; inset:0; background:rgba(0,0,0,.45); z-index:10; display:flex; align-items:flex-end; justify-content:center; }
.modal { background:var(--card-background-color); width:100%; max-width:560px; border-radius:16px 16px 0 0; padding:18px 16px 24px;
  max-height:90vh; overflow:auto; }
@media (min-width:600px) { .background { align-items:center; } .modal { border-radius:16px; } }
.confidence { margin-top:10px; }
.buttons { display:flex; gap:8px; margin-top:16px; align-items:center; } .flex { flex:1; }
.segments { display:flex; background:var(--card-background-color); border-radius:10px; padding:4px; margin-bottom:12px; }
.segments button { flex:1; border:0; background:none; padding:8px; border-radius:8px; color:var(--primary-text-color); }
.segments button.active { background:var(--primary-color); color:var(--text-primary-color, #fff); }
.chart { width:100%; height:auto; display:block; }
.row-title { display:flex; align-items:center; justify-content:space-between; gap:8px; }
.row-title h2 { margin:0; }
.secondary.small { width:auto; margin:0; padding:8px 12px; font-size:14px; }
.progress.large-p { height:16px; border-radius:8px; margin:12px 0 6px; }
.progress.ref { position:relative; height:14px; border-radius:7px; }
.progress.ref .fill { position:absolute; left:0; top:0; }
.progress.ref .fill.ideal { background:var(--success-color, #43a047); }
.progress.ref .fill.minimum { background:var(--primary-color); }
.progress.ref .fill.behind { background:var(--warning-color, #ff9800); }
.progress.ref .band { position:absolute; top:0; background:var(--primary-text-color); opacity:.22; }
.progress.ref .mark { position:absolute; top:0; width:2px; background:var(--primary-text-color); opacity:.6; }
.state-ref { font-size:14px; font-weight:500; margin:2px 0; }
.state-ref.behind { color:var(--warning-color, #e65100); }
.next { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0 4px; }
.chip-ref { font-size:12px; padding:3px 8px; border-radius:10px; background:var(--secondary-background-color, rgba(127,127,127,.12)); }
.days7 { display:flex; align-items:center; gap:5px; flex-wrap:wrap; margin-top:6px; }
.days7 .sub { margin:0; }
.dot { width:11px; height:11px; border-radius:50%; border:1.5px solid var(--divider-color); box-sizing:border-box; }
.dot.l1 { background:var(--primary-color); border-color:var(--primary-color); }
.dot.l2 { background:var(--success-color, #43a047); border-color:var(--success-color, #43a047); }
.bottle-info { font-size:16px; }
.alert-text { color:var(--error-color, #db4437); font-size:13px; margin-top:6px; }
.question { margin-top:14px; font-size:13px; }
.chip.strong { border-color:var(--primary-color); color:var(--primary-color); font-weight:500; }
.check { flex-direction:row; align-items:center; gap:8px; font-size:14px; color:var(--primary-text-color); }
.check input { width:20px; height:20px; }
.group { margin-top:12px; }
.bottle-header { display:flex; align-items:center; gap:8px; padding:8px 4px; background:var(--secondary-background-color, rgba(0,0,0,.04));
  border-radius:8px; cursor:pointer; flex-wrap:wrap; }
.bottle-header .badge { justify-self:auto; }
.badge.open { background:rgba(3,155,229,.18); color:var(--info-color, #0277bd); }
.badge.finished { background:rgba(67,160,71,.18); color:var(--success-color, #2e7d32); }
.badge.incomplete { background:rgba(255,152,0,.2); color:var(--warning-color, #e65100); }
.buttons.move { margin-top:8px; flex-wrap:wrap; }
.buttons.move .secondary { flex:1; }
:host { --breast_milk-color:#e91e63; }
.new { display:flex; gap:8px; margin:10px 0 4px; flex-wrap:wrap; }
.new .secondary.small { flex:1; }
.new button:disabled { opacity:.5; }
.badge.breast_milk { background:rgba(233,30,99,.15); color:var(--breast_milk-color); }
.badge.formula { background:rgba(3,155,229,.15); color:var(--info-color, #0277bd); }
.badge.fridge { background:rgba(3,155,229,.15); color:var(--info-color, #0277bd); }
.badge.room { background:rgba(255,152,0,.2); color:var(--warning-color, #e65100); }
.list li.stash { grid-template-columns:64px 1fr; grid-template-areas:"hhmm oz" "hhmm goal" "acc acc"; cursor:default; }
.list li.stash.expired { opacity:.75; }
.actions { grid-area:acc; display:flex; gap:6px; flex-wrap:wrap; margin-top:6px; }
.actions .chip { padding:6px 12px; font-size:14px; min-width:0; }
.danger-chip { color:var(--error-color, #db4437); border-color:var(--error-color, #db4437); }
.red { color:var(--error-color, #db4437); } .orange { color:var(--warning-color, #e65100); }
h2.sep { margin-top:18px; }
.legend .c4 { background:var(--breast_milk-color); }
.legend .c5 { background:#29b6f6; } .legend .c6 { background:#8d6e63; } .legend .c7 { background:#ab47bc; }
.hero { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:12px; }
.hero-col { background:var(--card-background-color); border-radius:14px; padding:14px; box-shadow:var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.15)); }
.hero-col.overdue { outline:2px solid var(--error-color, #db4437); }
.hero-col.overdue .hero-hhmm { color:var(--error-color, #db4437); }
.hero-hhmm { font-size:34px; font-weight:600; line-height:1.1; margin:4px 0; }
.chips.large .chip { flex:1; font-size:18px; padding:14px 8px; }
.chip.active { background:var(--primary-color); color:var(--text-primary-color, #fff); border-color:var(--primary-color); }
.shows { display:inline-block; width:12px; height:12px; border-radius:50%; border:1px solid var(--divider-color); margin-right:6px; vertical-align:-1px; }
.sep-label { margin-top:12px; }
.icon.pencil { font-size:14px; padding:2px 6px; }
.paused { margin-top:12px; padding:10px; border:1px dashed var(--divider-color); border-radius:10px; }
.paused.overdue { border-color:var(--error-color, #db4437); }
.options { display:flex; flex-direction:column; gap:8px; margin-top:12px; }
.options button { width:100%; margin:0; }
.leftover { margin-top:12px; }
.chips { display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; }
.chip { border:1px solid var(--divider-color); background:var(--secondary-background-color, transparent); color:var(--primary-text-color);
  border-radius:20px; padding:10px 16px; font-size:16px; min-width:56px; }
.chip:active { background:var(--primary-color); color:var(--text-primary-color, #fff); }
.link { border:0; background:none; color:var(--secondary-text-color); margin-top:8px; padding:6px 0; }
.help { font-size:11px; color:var(--secondary-text-color); }
#suggestion p { margin:0 0 8px; }
.grid { stroke:var(--divider-color); stroke-width:1; }
.hi-week { flex:1; text-align:center; display:flex; flex-direction:column; }
.hi-p { margin:6px 0 0; font-size:14px; line-height:1.4; }
.hi-area { margin:14px 0 4px; font-size:13px; font-weight:500; color:var(--secondary-text-color); }
.hi-item { display:flex; gap:10px; width:100%; align-items:flex-start; text-align:left; background:none; border:0; border-top:1px solid var(--divider-color);
  padding:9px 2px; color:var(--primary-text-color); font:inherit; font-size:14px; cursor:pointer; }
.hi-box { flex:none; width:20px; height:20px; border:2px solid var(--secondary-text-color); border-radius:5px; box-sizing:border-box;
  display:flex; align-items:center; justify-content:center; font-size:14px; font-weight:700; color:#fff; }
.hi-item.made_at .hi-box { background:var(--primary-color); border-color:var(--primary-color); }
.hi-text { display:flex; flex-direction:column; min-width:0; }
.hi-list { margin:6px 0 0; padding-left:20px; font-size:14px; line-height:1.45; } .hi-list li { margin-bottom:4px; }
.hi-pending { margin-top:12px; } .hi-pending summary { cursor:pointer; font-size:14px; color:var(--primary-color); }
.hi-axis { position:relative; height:16px; margin-top:8px; font-size:11px; color:var(--secondary-text-color); }
.hi-axis span { position:absolute; transform:translateX(-50%); } .hi-axis span:first-child { transform:none; } .hi-axis span:last-child { transform:translateX(-100%); }
.hi-skill summary { list-style:none; cursor:pointer; padding:6px 0; color:var(--primary-text-color); } .hi-skill summary::-webkit-details-marker { display:none; }
.hi-skill-t { display:flex; justify-content:space-between; gap:8px; font-size:14px; }
.hi-hint { display:block; position:relative; height:12px; margin-top:4px; }
.hi-band { position:absolute; top:3px; height:6px; border-radius:3px; background:var(--divider-color); }
.hi-today { position:absolute; top:0; width:2px; height:12px; background:var(--primary-text-color); opacity:.55; }
.hi-dot { position:absolute; top:1px; width:10px; height:10px; margin-left:-5px; border-radius:50%; background:var(--primary-color); border:1px solid var(--card-background-color); box-sizing:border-box; }
.hi-legend { display:flex; flex-wrap:wrap; gap:6px 14px; margin-top:8px; font-size:12px; color:var(--secondary-text-color); }
.hi-legend span { display:inline-flex; align-items:center; gap:5px; }
.hi-notice { margin:0 4px 10px; line-height:1.4; } .hi-notice a { color:var(--primary-color); }
.axis { fill:var(--secondary-text-color); font-size:11px; }
.value { fill:var(--primary-text-color); font-size:10px; }
.goal { stroke:var(--error-color, #db4437); stroke-width:2; stroke-dasharray:6 4; }
.goal-text { fill:var(--error-color, #db4437); font-size:11px; }
.goal-min { stroke:var(--warning-color, #ff9800); stroke-width:2; stroke-dasharray:2 4; stroke-linecap:round; }
.goal-min-text { fill:var(--warning-color, #e65100); font-size:11px; }
.line { fill:none; stroke:var(--primary-color); stroke-width:2.5; }
.dot { fill:var(--primary-color); }
.legend { display:flex; gap:6px; align-items:center; font-size:12px; color:var(--secondary-text-color); margin-top:6px; flex-wrap:wrap; }
.legend span { width:12px; height:12px; border-radius:3px; display:inline-block; margin-left:8px; }
.legend .c1 { background:var(--primary-color); } .legend .c2 { background:var(--primary-color); opacity:.45; }
.legend .c3 { background:var(--error-color, #db4437); height:3px; }
`;


customElements.define("baby-tracker-panel", BabyPanel);
