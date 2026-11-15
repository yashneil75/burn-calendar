/* California Burn Calendar - The map page.
   Plain white field, no basemap. Boundary and cells are local files. */

"use strict";

const el = (id) => document.getElementById(id);
const fmt = (n, digits = 1) =>
  Number(n).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });

const state = { cells: [], years: [], a: 0, b: 0, map: null, layer: null, legendDiv: null };

async function boot() {
  const [cellsRes, calRes, boundaryRes] = await Promise.all([
    fetch("assets/cells.json"),
    fetch("data/calendar.json"),
    fetch("assets/california.geojson"),
  ]);
  if (!cellsRes.ok || !boundaryRes.ok) {
    el("map").innerHTML = `<p class="load-error">The map data did not load. Try refreshing; if it persists, the latest build may be in progress.</p>`;
    return;
  }
  const payload = await cellsRes.json();
  if (!payload || payload.schema_version !== 2 || !Array.isArray(payload.years) || !Array.isArray(payload.cells)) {
    el("map").innerHTML = `<p class="load-error">The year-by-year cell data is still being prepared. Reload in a few minutes.</p>`;
    return;
  }
  state.cells = payload.cells;
  state.years = payload.years;
  state.a = state.years[0];
  state.b = state.years[state.years.length - 1];

  const calendar = calRes.ok ? await calRes.json() : null;
  const boundary = await boundaryRes.json();

  el("mapPeak").textContent = calendar && calendar.stats.peak_day
    ? `${new Date(calendar.stats.peak_day + "T00:00:00Z").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" })}`
    : "…";
  if (calendar) {
    const node = el("updatedAt");
    if (node) {
      node.textContent = `Refreshed ${new Date(calendar.generated_utc).toLocaleString("en-US", {
        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC",
      })} UTC`;
    }
  }

  const feature = boundary.features[0];
  const bounds = L.geoJSON(feature).getBounds();

  const map = L.map("map", {
    center: bounds.getCenter(),
    zoom: 6,
    minZoom: 6,
    maxZoom: 12,
    maxBounds: bounds.pad(0.03),
    maxBoundsViscosity: 1.0,
    zoomControl: true,
    attributionControl: false,
    preferCanvas: true,
    scrollWheelZoom: true,
  });
  map.fitBounds(bounds.pad(0.04));
  state.map = map;

  L.geoJSON(feature, {
    style: { color: "#111111", weight: 2, fillOpacity: 0, interactive: false },
  }).addTo(map);

  state.layer = L.layerGroup().addTo(map);

  const legend = L.control({ position: "bottomleft" });
  legend.onAdd = () => {
    const div = L.DomUtil.create("div", "map-legend");
    div.id = "mapLegend";
    state.legendDiv = div;
    return div;
  };
  legend.addTo(map);

  wireSlider();
  render();
}

const MIN_IDX = 0;
let pending = false;

function scheduleRender() {
  if (pending) return;
  pending = true;
  requestAnimationFrame(() => {
    pending = false;
    render();
  });
}

function wireSlider() {
  const start = el("rangeStart");
  const end = el("rangeEnd");
  const min = state.years[MIN_IDX];
  const max = state.years[state.years.length - 1];
  start.min = String(min); start.max = String(max); start.value = String(state.a);
  end.min = String(min); end.max = String(max); end.value = String(state.b);
  start.addEventListener("input", () => {
    let v = Number(start.value);
    if (v > state.b) { state.b = v; end.value = String(v); }
    state.a = v;
    scheduleRender();
  });
  end.addEventListener("input", () => {
    let v = Number(end.value);
    if (v < state.a) { state.a = v; start.value = String(v); }
    state.b = v;
    scheduleRender();
  });
}

function render() {
  const years = state.years;
  const i0 = years.indexOf(state.a);
  const i1 = years.indexOf(state.b);
  const min = years[MIN_IDX];
  const max = years[years.length - 1];

  const fill = el("rangeFill");
  const pct = (y) => ((y - min) / (max - min)) * 100;
  fill.style.left = `${pct(state.a)}%`;
  fill.style.width = `${pct(state.b) - pct(state.a)}%`;
  el("rangeReadout").textContent = `${state.a} to ${state.b}`;
  el("mapTotalLabel").textContent = `Activity, ${state.a} to ${state.b}`;

  // Sum each cell across the selected years.
  const slice = [];
  let total = 0.0;
  for (const c of state.cells) {
    let s = 0;
    for (let i = i0; i <= i1; i += 1) s += c[2 + i];
    if (s >= 1.0) {
      slice.push([c[0], c[1], s]);
      total += s;
    }
  }
  slice.sort((x, y) => y[2] - x[2]);

  const acts = slice.map((c) => c[2]).sort((a, b) => a - b);
  const q = (p) => (acts.length ? acts[Math.min(acts.length - 1, Math.floor(p * acts.length))] : 0);
  const b50 = q(0.5), b80 = q(0.8), b95 = q(0.95);

  state.layer.clearLayers();
  for (const [lon, lat, a] of slice) {
    const radius = Math.max(3.5, Math.min(16, 3 + Math.sqrt(a) * 0.72));
    const opacity = a < b50 ? 0.22 : a < b80 ? 0.32 : a < b95 ? 0.45 : 0.62;
    L.circleMarker([lat, lon], {
      radius,
      color: "transparent",
      fillColor: "#111111",
      fillOpacity: opacity,
      weight: 0,
      bubblingMouseEvents: false,
    }).bindTooltip(
      `<span class="cell-tip">~ ${fmt(a, 0)} cells, ${state.a} to ${state.b}</span>`,
      { direction: "top", sticky: true, className: "cell-tooltip", opacity: 1 }
    ).addTo(state.layer);
  }

  el("mapTotal").textContent = fmt(total);
  el("mapCells").textContent = String(slice.length);

  if (state.legendDiv) {
    state.legendDiv.innerHTML = `
      <div class="map-legend-title">Fire activity</div>
      <div class="map-legend-row"><span class="dot" style="width:16px;height:16px;opacity:.62"></span>Severe<i>${fmt(b95, 0)}+</i></div>
      <div class="map-legend-row"><span class="dot" style="width:12px;height:12px;opacity:.45"></span>Heavy<i>${fmt(b80, 0)}+</i></div>
      <div class="map-legend-row"><span class="dot" style="width:9px;height:9px;opacity:.32"></span>Active<i>${fmt(b50, 0)}+</i></div>
      <div class="map-legend-row"><span class="dot" style="width:6px;height:6px;opacity:.22"></span>Sparse</div>`;
  }
}

boot().catch((err) => {
  const node = el("map");
  if (node) node.innerHTML = `<p class="load-error">The map failed to start (${err.message}). Try refreshing.</p>`;
});
