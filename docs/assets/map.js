/* Califire - The map page.
   Plain white field, no basemap. Boundary and cells are local files. */

"use strict";

const el = (id) => document.getElementById(id);
const fmt = (n, digits = 1) =>
  Number(n).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });

const state = {
  cells: [], years: [], a: 0, b: 0, map: null, layer: null, legendDiv: null,
  draw: { active: false, mode: null, points: [], line: null, rect: null, vertexMarkers: [], polygon: null, areaPoints: null },
};

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
    style: { color: "#7e2b1c", weight: 2, fillOpacity: 0, interactive: false },
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
  wireDraw();
  render();
}

const MIN_IDX = 0;
let pending = false;

/* ---------- Draw an area ---------- */
function pointInPolygon(lat, lng, polygon) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const yi = polygon[i][0], xi = polygon[i][1], yj = polygon[j][0], xj = polygon[j][1];
    const crosses = (yi > lat) !== (yj > lat) &&
      lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi;
    if (crosses) inside = !inside;
  }
  return inside;
}

function wireDraw() {
  const toolButtons = [...document.querySelectorAll(".map-btn.tool")];
  const doneBtn = el("drawDone");
  const hint = el("drawHint");
  const clearBtn = el("areaClear");
  if (!toolButtons.length || !doneBtn || !hint || !clearBtn || !state.map) return;
  const map = state.map;
  const container = map.getContainer();

  const d = state.draw;
  const HINTS = {
    polygon: "Tap to add corners. Finish with Done or double-tap. Esc cancels.",
    box: "Drag to draw a box. Esc cancels.",
    scribble: "Draw one continuous stroke, it closes automatically. Esc cancels.",
  };

  // Preserve the click-to-add-polygon flow; convert pixel space to map space for box/scribble.
  const toLatLng = (e) => {
    const rect = container.getBoundingClientRect();
    return map.containerPointToLatLng(L.point(e.clientX - rect.left, e.clientY - rect.top));
  };

  const setToolActive = (mode) => {
    for (const b of toolButtons) b.setAttribute("aria-pressed", b.dataset.tool === mode ? "true" : "false");
  };
  const panning = (enabled) => {
    if (enabled) { map.dragging.enable(); map.doubleClickZoom.enable(); } else { map.dragging.disable(); map.doubleClickZoom.disable(); }
  };
  const setModeUI = () => {
    doneBtn.hidden = !(d.active && d.mode === "polygon");
    hint.hidden = !d.active;
    hint.textContent = d.active ? HINTS[d.mode] : "";
    L.DomUtil[d.active ? "addClass" : "removeClass"](container, "drawing");
    panning(!d.active);
    setToolActive(d.active ? d.mode : null);
  };

  const removePreviews = () => {
    if (d.line) { map.removeLayer(d.line); d.line = null; }
    if (d.rect) { map.removeLayer(d.rect); d.rect = null; }
    for (const m of d.vertexMarkers) map.removeLayer(m);
    d.vertexMarkers = [];
    d.points = [];
  };

  const clearArea = () => {
    if (d.polygon) { map.removeLayer(d.polygon); d.polygon = null; }
    removePreviews();
    d.areaPoints = null;
    el("areaStats").hidden = true;
    setModeUI();
  };

  const finish = () => {
    if (d.points.length < (d.mode === "scribble" ? 8 : 3)) return;
    d.areaPoints = d.points.slice();
    removePreviews();
    d.polygon = L.polygon(d.areaPoints, { color: "#c2452d", weight: 1.5, dashArray: "5 4", fillColor: "#c2452d", fillOpacity: 0.07, interactive: false }).addTo(map);
    d.active = false;
    d.mode = null;
    setModeUI();
    updateAreaStats();
    el("areaStats").hidden = false;
  };

  const cancel = () => {
    removePreviews();
    d.active = false;
    d.mode = null;
    setModeUI();
  };

  const startDraw = (mode) => {
    // Starting a new selection discards the old one (and any in-flight stroke).
    if (d.polygon) { map.removeLayer(d.polygon); d.polygon = null; }
    removePreviews();
    strokeId = null;
    strokeOrigin = null;
    lastPx = null;
    d.areaPoints = null;
    el("areaStats").hidden = true;
    d.active = true;
    d.mode = mode;
    setModeUI();
  };

  const refreshLine = () => {
    if (d.line) { map.removeLayer(d.line); d.line = null; }
    if (d.points.length >= 2) {
      d.line = L.polyline([...d.points, d.points[0]], { color: "#c2452d", weight: 1.5, dashArray: "5 4", interactive: false }).addTo(map);
    }
    doneBtn.disabled = d.points.length < 3;
  };

  // Ramer–Douglas–Peucker in pixel space, keeps the stroke cheap for point-in-polygon.
  const simplifyStroke = (latlngs) => {
    const pts = latlngs.map(([lat, lng]) => map.latLngToContainerPoint(L.latLng(lat, lng)));
    const keep = new Uint8Array(pts.length);
    keep[0] = keep[pts.length - 1] = 1;
    const stack = [[0, pts.length - 1]];
    const EPS = 3;
    while (stack.length) {
      const [a, b] = stack.pop();
      const ax = pts[a].x, ay = pts[a].y, bx = pts[b].x, by = pts[b].y;
      const dx = bx - ax, dy = by - ay;
      const len2 = dx * dx + dy * dy;
      let maxD = 0, idx = -1;
      for (let i = a + 1; i < b; i += 1) {
        const px = pts[i].x, py = pts[i].y;
        let dist;
        if (len2 === 0) dist = Math.hypot(px - ax, py - ay);
        else {
          const t = ((px - ax) * dx + (py - ay) * dy) / len2;
          dist = Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
        }
        if (dist > maxD) { maxD = dist; idx = i; }
      }
      if (maxD > EPS && idx !== -1) { keep[idx] = 1; stack.push([a, idx], [idx, b]); }
    }
    return latlngs.filter((_, i) => keep[i]);
  };

  for (const b of toolButtons) b.addEventListener("click", () => startDraw(b.dataset.tool));
  clearBtn.addEventListener("click", clearArea);
  doneBtn.addEventListener("click", finish);
  map.on("click", (e) => {
    if (!d.active || d.mode !== "polygon") return;
    d.points.push([e.latlng.lat, e.latlng.lng]);
    const marker = L.circleMarker(e.latlng, { radius: 4, color: "#111111", weight: 1.5, fillColor: "#fafafa", fillOpacity: 1, bubblingMouseEvents: false }).addTo(map);
    d.vertexMarkers.push(marker);
    refreshLine();
  });
  map.on("dblclick", () => { if (d.active && d.mode === "polygon") finish(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && d.active) cancel();
  });

  let strokeId = null;
  let strokeOrigin = null;
  let lastPx = null;

  container.addEventListener("pointerdown", (e) => {
    if (!d.active || (d.mode !== "box" && d.mode !== "scribble")) return;
    e.preventDefault();
    try { container.setPointerCapture(e.pointerId); } catch (_) { /* non-active/synthetic pointers */ }
    strokeId = e.pointerId;
    const ll = toLatLng(e);
    if (d.mode === "box") {
      strokeOrigin = ll;
      d.rect = L.rectangle([ll, ll], { color: "#c2452d", weight: 1.5, dashArray: "5 4", fillColor: "#c2452d", fillOpacity: 0.07, interactive: false }).addTo(map);
    } else {
      d.points = [[ll.lat, ll.lng]];
      lastPx = { x: e.clientX, y: e.clientY };
      d.line = L.polyline(d.points, { color: "#c2452d", weight: 1.5, dashArray: "5 4", interactive: false }).addTo(map);
    }
  }, { passive: false });

  container.addEventListener("pointermove", (e) => {
    if (!d.active || e.pointerId !== strokeId) return;
    e.preventDefault();
    if (d.mode === "box") {
      const ll = toLatLng(e);
      d.rect.setBounds(L.latLngBounds(strokeOrigin, ll));
      return;
    }
    const dx = e.clientX - lastPx.x, dy = e.clientY - lastPx.y;
    if (Math.hypot(dx, dy) < 4) return;
    const ll = toLatLng(e);
    d.points.push([ll.lat, ll.lng]);
    d.line.addLatLng(ll);
    lastPx = { x: e.clientX, y: e.clientY };
  }, { passive: false });

  container.addEventListener("pointerup", (e) => {
    if (!d.active || e.pointerId !== strokeId) return;
    strokeId = null;
    if (d.mode === "box") {
      const sw = d.rect.getBounds();
      const a = map.latLngToContainerPoint(strokeOrigin);
      const b = map.latLngToContainerPoint(toLatLng(e));
      if (Math.hypot(a.x - b.x, a.y - b.y) < 8) { cancel(); return; }
      d.points = [
        [sw.getSouthWest().lat, sw.getSouthWest().lng],
        [sw.getSouthWest().lat, sw.getNorthEast().lng],
        [sw.getNorthEast().lat, sw.getNorthEast().lng],
        [sw.getNorthEast().lat, sw.getSouthWest().lng],
      ];
      finish();
      return;
    }
    const original = d.points;
    if (original.length < 8) { cancel(); return; } // too small to be a deliberate stroke
    const simplified = simplifyStroke(original);
    // A perfectly straight stroke collapses in RDP; keep the raw points so the selection still works.
    d.points = simplified.length >= 3 ? simplified : original;
    finish();
  });

  container.addEventListener("pointercancel", () => {
    if (strokeId !== null) { strokeId = null; cancel(); }
  });
}

function updateAreaStats() {
  const pts = state.draw.areaPoints;
  if (!pts || pts.length < 3) return;
  const years = state.years;
  const i0 = years.indexOf(state.a);
  const i1 = years.indexOf(state.b);
  const nYears = i1 - i0 + 1;
  let stateTotal = 0, sum = 0, cells = 0;
  const yrTotals = new Array(nYears).fill(0);
  for (const c of state.cells) {
    let s = 0;
    for (let i = i0; i <= i1; i += 1) s += c[2 + i];
    if (s < 1.0) continue;
    stateTotal += s;
    if (pointInPolygon(c[1], c[0], pts)) {
      sum += s;
      cells += 1;
      for (let i = i0; i <= i1; i += 1) yrTotals[i - i0] += c[2 + i];
    }
  }
  let peakValue = 0, peakYear = null;
  for (let i = 0; i < nYears; i += 1) {
    if (yrTotals[i] > peakValue) { peakValue = yrTotals[i]; peakYear = years[i0 + i]; }
  }
  el("areaActivityLabel").textContent = `Activity, ${state.a} to ${state.b}`;
  el("areaCells").textContent = String(cells);
  el("areaActivity").textContent = sum > 0 ? fmt(sum) : "0.0";
  el("areaShare").textContent = stateTotal > 0 ? `${fmt((sum / stateTotal) * 100, 1)}%` : "—";
  el("areaPeakYear").textContent = peakYear && peakValue > 0 ? `${peakYear} · ${fmt(peakValue, 0)}` : "—";
  el("areaAvg").textContent = fmt(sum / nYears);
}

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
  const endpoints = document.querySelectorAll(".range-ends .num");
  if (endpoints.length >= 2) { endpoints[0].textContent = String(min); endpoints[1].textContent = String(max); }
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

  // Calendar ramp, low end to high: gold, burnt orange, ember, coal.
  const TIERS = [
    { color: "#d9a441", opacity: 0.45, size: 6 },
    { color: "#c8692b", opacity: 0.55, size: 9 },
    { color: "#c2452d", opacity: 0.7, size: 12 },
    { color: "#7e2b1c", opacity: 0.88, size: 16 },
  ];
  const tierOf = (a) => (a < b50 ? 0 : a < b80 ? 1 : a < b95 ? 2 : 3);

  state.layer.clearLayers();
  for (const [lon, lat, a] of slice) {
    const radius = Math.max(3.5, Math.min(16, 3 + Math.sqrt(a) * 0.72));
    const tier = TIERS[tierOf(a)];
    L.circleMarker([lat, lon], {
      radius,
      color: "transparent",
      fillColor: tier.color,
      fillOpacity: tier.opacity,
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
      <div class="map-legend-row"><span class="dot" style="width:16px;height:16px;background:${TIERS[3].color};opacity:${TIERS[3].opacity}"></span>Severe<i>${fmt(b95, 0)}+</i></div>
      <div class="map-legend-row"><span class="dot" style="width:12px;height:12px;background:${TIERS[2].color};opacity:${TIERS[2].opacity}"></span>Heavy<i>${fmt(b80, 0)}+</i></div>
      <div class="map-legend-row"><span class="dot" style="width:9px;height:9px;background:${TIERS[1].color};opacity:${TIERS[1].opacity}"></span>Active<i>${fmt(b50, 0)}+</i></div>
      <div class="map-legend-row"><span class="dot" style="width:6px;height:6px;background:${TIERS[0].color};opacity:${TIERS[0].opacity}"></span>Sparse</div>`;
  }
  if (state.draw.areaPoints) updateAreaStats();
}

boot().catch((err) => {
  const node = el("map");
  if (node) node.innerHTML = `<p class="load-error">The map failed to start (${err.message}). Try refreshing.</p>`;
});
