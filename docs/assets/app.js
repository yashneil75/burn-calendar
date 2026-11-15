/* California Burn Calendar. Client-side rendering of docs/data/calendar.json.
   No frameworks; the JSON is the app's only dependency besides fonts.
   Dual mode: index.html (calendar) and archive.html (matrix). */

"use strict";

const RAMP = ["#e7cd90", "#d9a441", "#c8692b", "#c2452d", "#7e2b1c"];
const RAMP_LOW = "#faf3e3";

const state = {
  data: null,
  byDate: new Map(),
  byMonth: new Map(),
  selectedYear: null,
  selectedMonth: null, // 0-based
};

const el = (id) => document.getElementById(id);
const fmt = (n, digits = 1) =>
  Number(n).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const monthLabel = (y, m) =>
  new Date(Date.UTC(y, m, 1)).toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" });
const MONTH_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const STOPS = [RAMP_LOW, ...RAMP];
function ramp(t) {
  const clamped = Math.max(0, Math.min(1, t));
  const scaled = clamped * (STOPS.length - 1);
  const i = Math.min(Math.floor(scaled), STOPS.length - 2);
  return lerpHex(STOPS[i], STOPS[i + 1], scaled - i);
}
function lerpHex(a, b, f) {
  const pa = parseInt(a.slice(1), 16), pb = parseInt(b.slice(1), 16);
  const r = Math.round(((pa >> 16) & 255) + (((pb >> 16) & 255) - ((pa >> 16) & 255)) * f);
  const g = Math.round(((pa >> 8) & 255) + (((pb >> 8) & 255) - ((pa >> 8) & 255)) * f);
  const bl = Math.round((pa & 255) + ((pb & 255) - (pa & 255)) * f);
  return `#${((1 << 24) | (r << 16) | (g << 8) | bl).toString(16).slice(1)}`;
}
const LOG_MIN = Math.log10(3);
const LOG_MAX = Math.log10(20000);
const activityColor = (v) => ramp((Math.log10(Math.max(v, 0.01)) - LOG_MIN) / (LOG_MAX - LOG_MIN));

function initIndex() {
  for (const m of state.data.months) state.byMonth.set(m.month, m);
  for (const d of state.data.daily) state.byDate.set(d.date, d);
}

function selectedMonthStats() {
  const key = `${state.selectedYear}-${String(state.selectedMonth + 1).padStart(2, "0")}`;
  return state.byMonth.get(key) || null;
}

function renderUpdatedAt() {
  const node = el("updatedAt");
  if (node) {
    node.textContent = `Refreshed ${new Date(state.data.generated_utc).toLocaleString("en-US", {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC",
    })} UTC`;
  }
}

/* ---------- Index: season calendar ---------- */
function renderCalendar() {
  const y = state.selectedYear, m = state.selectedMonth;
  el("monthLabel").textContent = monthLabel(y, m);
  const first = new Date(Date.UTC(y, m, 1));
  const startOffset = (first.getUTCDay() + 6) % 7; // Monday-first
  const daysInMonth = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();

  const grid = el("calGrid");
  grid.innerHTML = "";
  for (let i = 0; i < startOffset; i += 1) {
    const pad = document.createElement("div");
    pad.className = "day-cell absent";
    pad.setAttribute("aria-hidden", "true");
    grid.appendChild(pad);
  }
  for (let d = 1; d <= daysInMonth; d += 1) {
    const dateStr = `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    const entry = state.byDate.get(dateStr);
    const cell = document.createElement("button");
    cell.className = "day-cell" + (entry ? "" : " absent");
    cell.dataset.date = dateStr;
    if (entry) {
      cell.style.background = activityColor(entry.activity);
      if (entry.activity > 60) cell.style.color = "#f6efe0";
      cell.innerHTML = `<span class="dow">${d}</span><span class="act num">${fmt(entry.activity)}</span><span class="frp num">${fmt(entry.frp_mw, 0)} MW</span>`;
      cell.setAttribute("aria-label", `${dateStr}: ${fmt(entry.activity)} activity, ${fmt(entry.frp_mw, 0)} megawatts FRP`);
      cell.addEventListener("click", () => openDrawer(dateStr));
    } else {
      cell.disabled = true;
      cell.innerHTML = `<span class="dow">${d}</span><span class="act">·</span>`;
      cell.setAttribute("aria-label", `${dateStr}: no observations reported`);
    }
    grid.appendChild(cell);
  }

  const mStats = selectedMonthStats();
  el("monthTotal").textContent = mStats ? fmt(mStats.activity) : "…";
  el("monthDays").textContent = mStats ? String(mStats.days_reported) : "0";
  el("monthPeak").textContent = mStats && mStats.peak_day
    ? `${new Date(mStats.peak_day + "T00:00:00Z").toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" })} · ${fmt(mStats.peak_activity)}`
    : "…";
}

function renderHeaderStats() {
  const stats = state.data.stats;
  const months = state.data.months;
  const lastMonth = months.length ? months[months.length - 1].month : null;
  const t12 = lastMonth
    ? months.filter((m) => m.month <= lastMonth).slice(-12).reduce((s, m) => s + m.activity, 0)
    : 0;
  el("statTrailing12").textContent = fmt(t12);
  el("statPeak").textContent = stats.peak_day
    ? `${new Date(stats.peak_day + "T00:00:00Z").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" })}`
    : "…";
  el("statPeakVal").textContent = fmt(stats.peak_activity);
  el("statDays").textContent = String(stats.days_reported);
  renderUpdatedAt();
}

function renderStrongest() {
  const months = state.data.months;
  const lastMonth = months.length ? months[months.length - 1].month : null;
  const cutoffDate = lastMonth ? new Date(`${lastMonth}-01T00:00:00Z`) : new Date(0);
  cutoffDate.setUTCMonth(cutoffDate.getUTCMonth() - 23);
  cutoffDate.setUTCDate(1);
  const recent = state.data.daily.filter((d) => new Date(d.date + "T00:00:00Z") >= cutoffDate);
  const top = [...recent].sort((a, b) => b.activity - a.activity).slice(0, 5);
  const max = top.length ? top[0].activity : 1;
  const list = el("strongestList");
  list.innerHTML = "";
  for (const d of top) {
    const li = document.createElement("li");
    li.innerHTML = `<span class="peak-date">${new Date(d.date + "T00:00:00Z").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" })}</span>
      <span class="peak-activity num">${fmt(d.activity)}</span>`;
    const bar = document.createElement("div");
    bar.className = "peak-bar";
    bar.style.width = `${Math.max(4, (d.activity / max) * 100)}%`;
    li.appendChild(bar);
    list.appendChild(li);
  }
}

function selectMonthQuiet(y, m) {
  state.selectedYear = y;
  state.selectedMonth = m;
  renderCalendar();
}

/* ---------- Index: date jump ---------- */
function initDateJump() {
  const input = el("dateJump");
  if (!input) return;
  const stats = state.data.stats;
  input.min = stats.first_day || "2015-01-01";
  input.max = stats.last_day || "";
  input.value = stats.last_day && stats.days_reported ? stats.last_day : "";
  input.addEventListener("change", () => {
    const value = input.value;
    if (!value) return;
    const y = Number(value.slice(0, 4));
    const m = Number(value.slice(5, 7)) - 1;
    if (y !== state.selectedYear || m !== state.selectedMonth) {
      selectMonthQuiet(y, m);
    }
    if (state.byDate.has(value)) {
      openDrawer(value);
    } else {
      el("season").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    }
  });
}

/* ---------- Index: drawer ---------- */
function openDrawer(dateStr) {
  const d = state.byDate.get(dateStr);
  if (!d) return;
  const dayDate = new Date(dateStr + "T12:00:00Z");
  el("drawerDate").textContent = dayDate.toLocaleDateString("en-US", {
    weekday: "long", month: "long", day: "numeric", year: "numeric", timeZone: "UTC",
  });
  el("drawerStatus").textContent = d.status === "sp"
    ? "Standard-processing (science quality)"
    : "Near-real-time (pending science reprocessing)";
  el("drawerActivity").textContent = fmt(d.activity);
  el("drawerFrp").textContent = `${fmt(d.frp_mw, 0)} MW`;
  el("drawerViirs").textContent = `${d.viirs_cells.toLocaleString()} · ${d.viirs_detections.toLocaleString()} detections`;

  const maxPeriod = Math.max(d.day.activity, d.night.activity, 0.5);
  for (const period of ["D", "N"]) {
    const p = d[period === "D" ? "day" : "night"];
    el(`fill${period}`).style.width = `${(p.activity / maxPeriod) * 100}%`;
    el(`val${period}`).textContent = `${fmt(p.activity)}`;
    el(`meta${period}`).textContent = `${p.passes} pass${p.passes === 1 ? "" : "es"}`;
  }

  const mm = dateStr.slice(5, 7);
  const same = state.data.daily.filter((x) => x.date.slice(5, 7) === mm).map((x) => x.activity);
  const rank = same.filter((v) => v < d.activity).length;
  const pct = Math.round((rank / Math.max(same.length - 1, 1)) * 100);
  const monthName = new Date(`2000-${mm}-01T00:00:00Z`).toLocaleDateString("en-US", { month: "long", timeZone: "UTC" });
  el("drawerVersus").textContent = same.length > 30
    ? (pct >= 100
        ? `The hottest reported ${monthName} day since 2015.`
        : `Hotter than ${pct}% of reported ${monthName} days since 2015.`)
    : "Not enough comparable days to rank.";

  el("drawer").classList.add("open");
  el("drawerBackdrop").classList.add("open");
  el("drawer").setAttribute("aria-hidden", "false");
  el("drawerClose").focus();
}

function closeDrawer() {
  el("drawer").classList.remove("open");
  el("drawerBackdrop").classList.remove("open");
  el("drawer").setAttribute("aria-hidden", "true");
}

/* ---------- Archive page ---------- */
function renderArchive() {
  const months = state.data.months;
  const years = [...new Set(months.map((m) => m.month.slice(0, 4)))].sort();
  const matrix = el("archiveMatrix");
  matrix.innerHTML = "";
  matrix.appendChild(document.createElement("div"));
  for (const label of MONTH_SHORT) {
    const h = document.createElement("div");
    h.className = "am-header";
    h.textContent = label;
    matrix.appendChild(h);
  }
  for (const yr of years) {
    const label = document.createElement("a");
    label.className = "am-year";
    label.textContent = yr;
    label.href = `index.html?month=${yr}-01#season`;
    label.title = `Open January ${yr} on the calendar`;
    matrix.appendChild(label);
    for (let m = 0; m < 12; m += 1) {
      const key = `${yr}-${String(m + 1).padStart(2, "0")}`;
      const stats = state.byMonth.get(key);
      const cell = document.createElement("a");
      if (stats && stats.days_reported > 0) {
        cell.className = "am-cell";
        cell.style.background = activityColor(stats.activity);
        cell.textContent = fmt(stats.activity, stats.activity >= 100 ? 0 : 1);
        if (stats.activity > 400) cell.style.color = "#f6efe0";
        cell.title = `${monthLabel(Number(yr), m)} · ${fmt(stats.activity)} activity, ${stats.days_reported} days reported, peak ${fmt(stats.peak_activity)}`;
        cell.href = `index.html?month=${key}#season`;
        cell.setAttribute("aria-label", cell.title);
      } else {
        cell.className = "am-cell empty";
        cell.textContent = "·";
        cell.title = `${monthLabel(Number(yr), m)} · no observations reported`;
        cell.setAttribute("aria-disabled", "true");
        cell.style.pointerEvents = "none";
      }
      matrix.appendChild(cell);
    }
  }
}

/* ---------- Boot ---------- */
async function boot() {
  try {
    const res = await fetch("data/calendar.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.data = await res.json();
  } catch (err) {
    const target = el("calGrid") || el("archiveMatrix");
    if (target) target.innerHTML = `<p class="load-error">The calendar data did not load (${err.message}). Try refreshing; if it persists, the latest build may be in progress.</p>`;
    return;
  }
  initIndex();
  renderUpdatedAt();

  if (el("archiveMatrix")) {
    renderArchive();
    return;
  }

  // Calendar page
  const params = new URLSearchParams(window.location.search);
  const wanted = params.get("month");
  const monthsWithData = state.data.months.filter((m) => m.days_reported >= 14);
  const fallback = monthsWithData.length ? monthsWithData[monthsWithData.length - 1].month
                                         : state.data.months[state.data.months.length - 1].month;
  const chosen = /^\d{4}-\d{2}$/.test(wanted || "") ? wanted : fallback;
  state.selectedYear = Number(chosen.slice(0, 4));
  state.selectedMonth = Number(chosen.slice(5, 7)) - 1;

  renderHeaderStats();
  renderCalendar();
  renderStrongest();
  initDateJump();

  if (wanted) {
    el("season").scrollIntoView({ behavior: "auto", block: "start" });
  }

  el("prevMonth").addEventListener("click", () => {
    const d = new Date(Date.UTC(state.selectedYear, state.selectedMonth - 1, 1));
    selectMonthQuiet(d.getUTCFullYear(), d.getUTCMonth());
  });
  el("nextMonth").addEventListener("click", () => {
    const d = new Date(Date.UTC(state.selectedYear, state.selectedMonth + 1, 1));
    selectMonthQuiet(d.getUTCFullYear(), d.getUTCMonth());
  });
  el("drawerClose").addEventListener("click", closeDrawer);
  el("drawerBackdrop").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeDrawer();
  });
}

boot();
