/* Califire download page. Builds CSV client-side from data/calendar.json.
   No frameworks; the JSON is the only dependency. */

"use strict";

const el = (id) => document.getElementById(id);

const state = {
  data: null,
  byMonth: new Map(),
  minMonth: null,
  maxMonth: null,
  cache: null, // last build, reused by the download button
};

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const COLUMNS = {
  daily: [
    "date", "status", "sensor", "activity", "frp_mw", "viirs_cells", "viirs_detections",
    "day_activity", "day_passes", "day_frp_mw", "day_viirs_cells", "day_viirs_detections",
    "night_activity", "night_passes", "night_frp_mw", "night_viirs_cells", "night_viirs_detections",
    "epochs", "source",
  ],
  monthly: ["month", "activity", "days_reported", "peak_day", "peak_activity"],
  yearly: ["year", "activity", "days_reported", "months_reported", "peak_day", "peak_activity"],
};

function csvEscape(value) {
  const s = value === null || value === undefined ? "" : String(value);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function toCsv(header, rows) {
  const lines = [header.map(csvEscape).join(",")];
  for (const row of rows) lines.push(row.map(csvEscape).join(","));
  return lines.join("\r\n") + "\r\n";
}

function addMonths(monthKey, delta) {
  const [y, m] = monthKey.split("-").map(Number);
  const total = y * 12 + (m - 1) + delta;
  const ny = Math.floor(total / 12);
  const nm = (total % 12) + 1;
  return `${ny}-${String(nm).padStart(2, "0")}`;
}

function monthLabelShort(monthKey) {
  const [y, m] = monthKey.split("-").map(Number);
  return `${MONTH_NAMES[m - 1]} ${y}`;
}

function monthIndex(monthKey) {
  const [y, m] = monthKey.split("-").map(Number);
  return y * 12 + (m - 1);
}

function granularity() {
  const checked = document.querySelector('input[name="granularity"]:checked');
  return checked ? checked.value : "daily";
}

function range() {
  return { from: el("fromMonth").value, to: el("toMonth").value };
}

function inRange(key, from, to) {
  return key >= from && key <= to;
}

function isFireSeason(monthNumber) {
  return monthNumber >= 6 && monthNumber <= 10;
}

function filteredDaily(from, to, fireSeasonOnly) {
  return state.data.daily.filter((d) => {
    const monthKey = d.date.slice(0, 7);
    if (!inRange(monthKey, from, to)) return false;
    if (fireSeasonOnly && !isFireSeason(Number(d.date.slice(5, 7)))) return false;
    return true;
  });
}

function filteredMonthly(from, to, fireSeasonOnly) {
  return state.data.months.filter((m) => {
    if (m.days_reported <= 0) return false; // no observations: omit, never zero
    if (!inRange(m.month, from, to)) return false;
    if (fireSeasonOnly && !isFireSeason(Number(m.month.slice(5, 7)))) return false;
    return true;
  });
}

function round3(n) {
  return Math.round((n + Number.EPSILON) * 1000) / 1000;
}

function dailyRow(d) {
  return [
    d.date, d.status, d.sensor ?? "", d.activity, d.frp_mw, d.viirs_cells, d.viirs_detections,
    d.day.activity, d.day.passes, d.day.frp_mw, d.day.viirs_cells, d.day.viirs_detections,
    d.night.activity, d.night.passes, d.night.frp_mw, d.night.viirs_cells, d.night.viirs_detections,
    (d.epochs || []).join(";"), d.source ?? "",
  ];
}

function monthlyRow(m) {
  return [m.month, m.activity, m.days_reported, m.peak_day ?? "", m.peak_activity ?? ""];
}

function yearlyRows(months) {
  const byYear = new Map();
  for (const m of months) {
    const year = m.month.slice(0, 4);
    if (!byYear.has(year)) {
      byYear.set(year, { activity: 0, days_reported: 0, months_reported: 0, peak_day: null, peak_activity: -Infinity });
    }
    const agg = byYear.get(year);
    agg.activity += m.activity;
    agg.days_reported += m.days_reported;
    agg.months_reported += 1;
    if (m.peak_day && Number.isFinite(m.peak_activity) && m.peak_activity > agg.peak_activity) {
      agg.peak_activity = m.peak_activity;
      agg.peak_day = m.peak_day;
    }
  }
  return [...byYear.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([year, agg]) => [
      year, round3(agg.activity), agg.days_reported, agg.months_reported,
      agg.peak_day ?? "", agg.peak_activity === -Infinity ? "" : agg.peak_activity,
    ]);
}

function buildCsv() {
  const kind = granularity();
  const { from, to } = range();
  const fireSeasonOnly = el("fireSeasonOnly").checked;

  if (!from || !to) return null;
  if (monthIndex(from) > monthIndex(to)) return { error: "range" };

  let header = COLUMNS[kind];
  let rows;
  let first = null;
  let last = null;

  if (kind === "daily") {
    const days = filteredDaily(from, to, fireSeasonOnly);
    rows = days.map(dailyRow);
    if (days.length) { first = days[0].date; last = days[days.length - 1].date; }
  } else if (kind === "monthly") {
    const months = filteredMonthly(from, to, fireSeasonOnly);
    rows = months.map(monthlyRow);
    if (months.length) { first = months[0].month; last = months[months.length - 1].month; }
  } else {
    const months = filteredMonthly(from, to, fireSeasonOnly);
    rows = yearlyRows(months);
    if (rows.length) { first = rows[0][0]; last = rows[rows.length - 1][0]; }
  }

  const text = toCsv(header, rows);
  return { kind, from, to, fireSeasonOnly, rows: rows.length, first, last, text, bytes: new Blob([text]).size };
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(bytes < 10 * 1024 * 1024 ? 2 : 1)} MB`;
}

function updateColumnList(kind) {
  el("columnList").textContent = COLUMNS[kind].join(", ");
}

function refresh() {
  const result = buildCsv();
  const errorNode = el("rangeError");
  const button = el("downloadBtn");
  const kind = granularity();
  updateColumnList(kind);

  if (!result || result.error === "range") {
    errorNode.hidden = false;
    el("sumRows").textContent = "0";
    el("sumCoverage").textContent = "—";
    el("sumSize").textContent = "—";
    button.disabled = true;
    state.cache = null;
    return;
  }

  errorNode.hidden = true;
  state.cache = result;

  el("sumRows").textContent = result.rows.toLocaleString("en-US");
  el("sumCoverage").textContent = result.first
    ? (kind === "daily" ? `${result.first} to ${result.last}` : kind === "monthly" ? `${monthLabelShort(result.first)} to ${monthLabelShort(result.last)}` : `${result.first} to ${result.last}`)
    : "No rows in range";
  el("sumSize").textContent = formatBytes(result.bytes);
  button.disabled = result.rows === 0;
}

function applyPreset(monthsBack) {
  const to = state.maxMonth;
  const from = monthsBack === null ? state.minMonth : addMonths(to, -(monthsBack - 1));
  el("fromMonth").value = from;
  el("toMonth").value = to;
  refresh();
}

function download() {
  const result = state.cache;
  if (!result || result.rows === 0) return;
  const suffix = result.fireSeasonOnly ? "-jun-oct" : "";
  const span = result.kind === "yearly"
    ? `${result.first}_to_${result.last}`
    : `${result.from}_to_${result.to}`;
  const filename = `califire-${result.kind}-${span}${suffix}.csv`;
  const blob = new Blob([result.text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function boot() {
  try {
    const res = await fetch("data/calendar.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.data = await res.json();
  } catch (err) {
    const errorNode = el("rangeError");
    errorNode.textContent = `The calendar data did not load (${err.message}). Try refreshing; if it persists, the latest build may be in progress.`;
    errorNode.hidden = false;
    el("downloadBtn").disabled = true;
    return;
  }

  const stats = state.data.stats || {};
  state.minMonth = (stats.first_day || state.data.daily[0]?.date || "2000-01-01").slice(0, 7);
  state.maxMonth = (stats.last_day || state.data.daily[state.data.daily.length - 1]?.date || "2000-01-01").slice(0, 7);
  for (const m of state.data.months) state.byMonth.set(m.month, m);

  const node = el("updatedAt");
  if (node) node.textContent = `Latest detection: ${stats.last_day || "unknown"} UTC`;

  const fromInput = el("fromMonth");
  const toInput = el("toMonth");
  fromInput.min = state.minMonth;
  fromInput.max = state.maxMonth;
  toInput.min = state.minMonth;
  toInput.max = state.maxMonth;
  fromInput.value = state.minMonth;
  toInput.value = state.maxMonth;

  for (const input of document.querySelectorAll('input[name="granularity"]')) {
    input.addEventListener("change", refresh);
  }
  fromInput.addEventListener("input", refresh);
  toInput.addEventListener("input", refresh);
  el("fireSeasonOnly").addEventListener("change", refresh);

  el("presetAll").addEventListener("click", () => applyPreset(null));
  el("preset12").addEventListener("click", () => applyPreset(12));
  el("preset5y").addEventListener("click", () => applyPreset(60));

  el("downloadBtn").addEventListener("click", download);

  refresh();
}

boot();
