"use strict";
/* Navegando Mareas · cliente web
 * Dibuja el mapa en SVG y consume la API REST de la fachada NavigationService. */

// Paleta categórica validada (CVD) – el color sigue a la entidad, no al orden.
const COLORS = { dijkstra: "#2a78d6", astar: "#eb6834", bfs: "#1baf7a", greedy: "#eda100" };
const ROUTE = "#4338ca";   // color de la ruta calculada (distinto de los colores de tráfico)
const ICONS = { start: "●", straight: "↑", left: "↰", right: "↱", arrive: "◎" };
const NS = "http://www.w3.org/2000/svg";
const $ = (id) => document.getElementById(id);

const S = {
  map: null, nodes: {}, algos: {}, algorithm: "astar", criterion: "time",
  mode: "route", origin: "A0", destination: "J6", pickNext: "origin",
  overlay: null, animToken: 0,
};

/* ------------------------------------------------------------ utilidades */
function el(tag, attrs = {}, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  const res = await fetch(path, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

const fmtDist = (m) => (m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`);
const fmtTime = (s) => `${Math.floor(s / 60)} min ${String(Math.round(s % 60)).padStart(2, "0")} s`;
const fmtCost = (v, crit) => (v == null ? "—" : crit === "time" ? fmtTime(v) : fmtDist(v));
const nodeName = (id) => (S.nodes[id] && S.nodes[id].label) || `Intersección ${id}`;
const algoLabel = (n) => (S.algos[n] ? S.algos[n].label : n);

function status(text) { $("status").textContent = text; }

let toastTimer;
function toast(html, ms = 4200) {
  const t = $("toast");
  t.innerHTML = html;
  t.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), ms);
}

function showTab(name) {
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("hidden", t.id !== `tab-${name}`));
}

/* ------------------------------------------------------------ inicio */
async function init() {
  const data = await api("/api/map");
  setMap(data);
  data.algorithms.forEach((a) => (S.algos[a.name] = a));
  buildSelectors();
  buildAlgorithms(data.algorithms);
  bindUI();
  drawMap();
  refreshSide();
}

function setMap(data) {
  S.map = data;
  S.nodes = Object.fromEntries(data.nodes.map((n) => [n.id, n]));
  $("mapName").textContent = data.name;
  $("mapInfo").textContent = `· ${data.nodes.length} intersecciones · ${data.edges.length} vías · versión ${data.version}`;
  status(`Mapa en línea · versión ${data.version}`);
  $("btnUndo").disabled = !data.history.can_undo;
  $("btnRedo").disabled = !data.history.can_redo;
}

function buildSelectors() {
  const sorted = [...S.map.nodes].sort((a, b) =>
    (b.label ? 1 : 0) - (a.label ? 1 : 0) || a.id.localeCompare(b.id, "es", { numeric: true }));
  for (const sel of [$("origin"), $("destination")]) {
    sel.innerHTML = "";
    for (const n of sorted) {
      const o = document.createElement("option");
      o.value = n.id;
      o.textContent = n.label ? `${n.label} (${n.id})` : `Intersección ${n.id}`;
      sel.appendChild(o);
    }
  }
  $("origin").value = S.origin;
  $("destination").value = S.destination;
}

function buildAlgorithms(list) {
  const box = $("algorithms");
  box.innerHTML = "";
  for (const a of list) {
    const d = document.createElement("div");
    d.className = `algo${a.name === S.algorithm ? " active" : ""}`;
    d.dataset.name = a.name;
    d.innerHTML = `<span class="sw" style="background:${COLORS[a.name]}"></span>
      <div><b>${a.label}</b><small>${a.description}</small></div>
      <span class="badge ${a.optimal ? "ok" : "no"}">${a.optimal ? "óptimo" : "heurístico"}</span>`;
    d.onclick = () => {
      S.algorithm = a.name;
      box.querySelectorAll(".algo").forEach((x) => x.classList.toggle("active", x === d));
    };
    box.appendChild(d);
  }
}

function bindUI() {
  $("origin").onchange = (e) => { S.origin = e.target.value; clearOverlay(); markEndpoints(); };
  $("destination").onchange = (e) => { S.destination = e.target.value; clearOverlay(); markEndpoints(); };
  document.querySelectorAll("#criteria button").forEach((b) => (b.onclick = () => {
    S.criterion = b.dataset.criterion;
    document.querySelectorAll("#criteria button").forEach((x) => x.classList.toggle("active", x === b));
  }));
  document.querySelectorAll("#modes button").forEach((b) => (b.onclick = () => setMode(b.dataset.mode)));
  document.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));
  $("btnRoute").onclick = () => calculate().catch(onError);
  $("btnCompare").onclick = () => compare().catch(onError);
  $("btnUndo").onclick = () => mapAction("/api/commands/undo").catch(onError);
  $("btnRedo").onclick = () => mapAction("/api/commands/redo").catch(onError);
  $("btnReset").onclick = () => mapAction("/api/reset").catch(onError);
  $("btnBench").onclick = () => benchmark().catch(onError);
}

function onError(err) { toast(`<b>Error:</b> ${err.message}`); }

function setMode(mode) {
  S.mode = mode;
  document.querySelectorAll("#modes button").forEach((x) => x.classList.toggle("active", x.dataset.mode === mode));
  $("trafficWrap").classList.toggle("hidden", mode !== "traffic");
  const svg = $("map");
  svg.classList.remove("mode-close", "mode-traffic");
  if (mode !== "route") svg.classList.add(`mode-${mode}`);
  const pill = $("modePill");
  pill.textContent = {
    route: "Modo: seleccionar origen/destino",
    close: "Modo: clic en una calle para cerrarla o reabrirla",
    traffic: "Modo: clic en una calle para fijar su tráfico",
  }[mode];
  pill.classList.toggle("warn", mode !== "route");
}

/* ------------------------------------------------------------ dibujo */
const WIDTH = { avenue: 30, street: 20, bridge: 24, diagonal: 22 };

function drawMap() {
  const svg = $("map");
  svg.innerHTML = "";
  const xs = S.map.nodes.map((n) => n.x), ys = S.map.nodes.map((n) => n.y);
  const minX = Math.min(...xs) - 330, maxX = Math.max(...xs) + 330;
  const minY = Math.min(...ys) - 190, maxY = Math.max(...ys) + 300;
  svg.setAttribute("viewBox", `${minX} ${minY} ${maxX - minX} ${maxY - minY}`);

  const gFeat = el("g", {}, svg), gCase = el("g", {}, svg), gEdge = el("g", {}, svg);
  const gStreetLbl = el("g", {}, svg), gHit = el("g", {}, svg);
  S.gRoute = el("g", {}, svg);
  const gNodes = el("g", {}, svg), gLabels = el("g", {}, svg);

  S.map.features.forEach((f) => drawFeature(gFeat, f));

  const labelled = new Set();
  for (const e of S.map.edges) {
    const a = S.nodes[e.u], b = S.nodes[e.v];
    const w = WIDTH[e.kind] || 20;
    el("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: "edge-casing", "stroke-width": w + 8 }, gCase);
    let cls = `edge ${e.kind}`;
    if (e.closed) cls += " closed";
    else if (e.traffic >= 2.5) cls += " t-high";
    else if (e.traffic >= 1.4) cls += " t-mid";
    el("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: cls, "stroke-width": w }, gEdge);
    if (e.closed) {
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2, k = 22;
      el("line", { x1: mx - k, y1: my - k, x2: mx + k, y2: my + k, class: "closed-x" }, gEdge);
      el("line", { x1: mx - k, y1: my + k, x2: mx + k, y2: my - k, class: "closed-x" }, gEdge);
    }
    const hit = el("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: "edge-hit" }, gHit);
    const t = el("title", {}, hit);
    t.textContent = `${e.name} (${e.u}–${e.v}) · ${Math.round(e.length)} m · ${e.speed} km/h · tráfico x${e.traffic}${e.closed ? " · CERRADA" : ""}`;
    hit.onclick = () => onEdgeClick(e).catch(onError);
    if ((e.kind !== "street") && !labelled.has(e.name) && shouldLabel(e)) {
      labelled.add(e.name);
      streetLabel(gStreetLbl, e, a, b);
    }
  }

  for (const n of S.map.nodes) {
    const c = el("circle", { cx: n.x, cy: n.y, r: n.label ? 24 : 15, class: `node${n.label ? " poi" : ""}`, "data-id": n.id }, gNodes);
    const t = el("title", {}, c);
    t.textContent = n.label ? `${n.label} (${n.id})` : `Intersección ${n.id}`;
    c.onclick = () => onNodeClick(n.id);
    if (n.label) {
      const below = n.y < 100;
      const txt = el("text", { x: n.x, y: below ? n.y - 44 : n.y + 74, class: "poi-label", "text-anchor": "middle" }, gLabels);
      txt.textContent = n.label;
    }
  }
  S.map.features.filter((f) => f.type === "zone").forEach((f) => {
    const t = el("text", { x: f.rect[0] + 16, y: f.rect[1] - 16, class: "street-label" }, gLabels);
    t.textContent = f.label;
  });
  markEndpoints();
  if (S.overlay) S.overlay();
}

function shouldLabel(e) {
  const want = { "Avenida Norte": "D0", "Avenida Costanera": "H6", "Avenida Oriental": "J2", "Diagonal 45": "B5" };
  if (e.kind === "bridge") return true;
  return want[e.name] && (e.u === want[e.name] || e.v === want[e.name]);
}

function streetLabel(g, e, a, b) {
  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
  let ang = Math.atan2(b.y - a.y, b.x - a.x) * 180 / Math.PI;
  if (ang > 90) ang -= 180;
  if (ang < -90) ang += 180;
  const off = e.kind === "bridge" ? -30 : -30;
  const t = el("text", { x: mx, y: my + off, class: e.kind === "bridge" ? "street-label bridge-label" : "street-label", "text-anchor": "middle",
    transform: `rotate(${ang} ${mx} ${my})` }, g);
  t.textContent = e.name;
}

function drawFeature(g, f) {
  if (f.type === "sea") {
    const [x, y, w, h] = f.rect;
    el("rect", { x, y, width: w, height: h, fill: "#bfdbfe" }, g);
    const t = el("text", { x: x + w / 2, y: y + 150, class: "feature-label", "text-anchor": "middle" }, g);
    t.textContent = f.label;
  } else if (f.type === "river") {
    const d = f.points.map((p, i) => `${i ? "L" : "M"}${p[0]},${p[1]}`).join(" ");
    el("path", { d, fill: "none", stroke: "#93c5fd", "stroke-width": f.width, "stroke-linejoin": "round", "stroke-linecap": "round" }, g);
    const [p1, p2] = [f.points[1], f.points[2]];
    const px = (p1[0] + p2[0]) / 2 + 18, py = (p1[1] + p2[1]) / 2 - 60;
    const t = el("text", { x: px, y: py, class: "feature-label", transform: `rotate(-84 ${px} ${py})`, "text-anchor": "middle" }, g);
    t.textContent = f.label;
  } else if (f.type === "park") {
    const [x, y, w, h] = f.rect;
    el("rect", { x, y, width: w, height: h, rx: 40, fill: "#bbf7d0", stroke: "#86efac", "stroke-width": 6 }, g);
    const t = el("text", { x: x + w / 2, y: y + h / 2, class: "feature-label", "text-anchor": "middle", fill: "#166534" }, g);
    t.textContent = f.label;
    t.setAttribute("style", "fill:#166534");
  } else if (f.type === "zone") {
    const [x, y, w, h] = f.rect;
    el("rect", { x, y, width: w, height: h, rx: 30, fill: "rgba(245,158,11,.08)", stroke: "#f59e0b", "stroke-width": 5, "stroke-dasharray": "22 16" }, g);
  }
}

function markEndpoints() {
  document.querySelectorAll("#map .node").forEach((c) => {
    c.classList.remove("origin", "destination");
    if (c.dataset.id === S.origin) c.classList.add("origin");
    if (c.dataset.id === S.destination) c.classList.add("destination");
  });
}

function clearExplored() {
  document.querySelectorAll("#map .node.explored").forEach((c) => c.classList.remove("explored"));
}

function clearOverlay() {
  S.animToken++;
  S.overlay = null;
  if (S.gRoute) S.gRoute.innerHTML = "";
  clearExplored();
}

function paintExplored(order) {
  const set = new Set(order);
  document.querySelectorAll("#map .node").forEach((c) => c.classList.toggle("explored", set.has(c.dataset.id)));
  markEndpoints();
}

function animateExplored(order) {
  const token = ++S.animToken;
  const delay = Math.max(8, Math.min(45, 1300 / Math.max(order.length, 1)));
  return new Promise((resolve) => {
    let i = 0;
    const tick = () => {
      if (token !== S.animToken) return resolve(false);
      const c = document.querySelector(`#map .node[data-id="${order[i]}"]`);
      if (c && !c.classList.contains("origin") && !c.classList.contains("destination")) c.classList.add("explored");
      i++;
      if (i < order.length) setTimeout(tick, delay); else resolve(true);
    };
    if (order.length) tick(); else resolve(true);
  });
}

function drawPath(path, { color = ROUTE, width = 34, animate = true, cls = "", halo = true } = {}) {
  if (!path || path.length < 2) return;
  const pts = path.map((id) => `${S.nodes[id].x},${S.nodes[id].y}`).join(" ");
  if (halo) el("polyline", { points: pts, class: "route-line route-halo", "stroke-width": width + 14 }, S.gRoute);
  const line = el("polyline", { points: pts, class: `route-line ${cls}`, stroke: color, "stroke-width": width }, S.gRoute);
  if (animate) {
    const len = line.getTotalLength();
    line.style.strokeDasharray = len;
    line.style.strokeDashoffset = len;
    line.getBoundingClientRect();
    line.style.transition = "stroke-dashoffset 900ms ease-in-out";
    line.style.strokeDashoffset = 0;
  }
}

/* ------------------------------------------------------------ interacción */
function onNodeClick(id) {
  if (S.mode !== "route") return;
  if (S.pickNext === "origin") { S.origin = id; S.pickNext = "destination"; }
  else { S.destination = id; S.pickNext = "origin"; }
  $("origin").value = S.origin;
  $("destination").value = S.destination;
  clearOverlay();
  markEndpoints();
  status(S.pickNext === "destination" ? "Origen fijado: elige el destino" : "Destino fijado: pulsa Calcular ruta");
}

async function onEdgeClick(e) {
  if (S.mode === "route") return;
  let body;
  if (S.mode === "close") body = { type: e.closed ? "open" : "close", u: e.u, v: e.v };
  else body = { type: "traffic", u: e.u, v: e.v, factor: parseFloat($("trafficFactor").value) };
  await mapAction("/api/commands", body);
}

async function mapAction(path, body = {}) {
  const res = await api(path, body);
  setMap(res.map);
  if (res.rerouted) {
    const r = res.rerouted;
    S.overlay = () => { paintExplored(r.explored_order || []); drawPath(r.path, { animate: false }); };
  }
  drawMap();
  refreshSide(res.events);
  if (res.rerouted) {
    showResult(res.rerouted);
    showTab("result");
    const r = res.rerouted;
    toast(`<b>Ruta recalculada (Observer)</b><br>${r.reason}. ${r.found ? `Nuevo costo: ${fmtCost(r.cost, r.criterion)}` : "No hay ruta disponible."}`, 5500);
  } else if (res.action) {
    toast(`<b>Comando:</b> ${res.action}`);
  }
}

async function calculate() {
  if (S.origin === S.destination) return toast("Origen y destino deben ser distintos");
  clearOverlay();
  const r = await api("/api/route", {
    origin: S.origin, destination: S.destination, algorithm: S.algorithm,
    criterion: S.criterion, use_cache: $("useCache").checked,
  });
  showResult(r);
  showTab("result");
  if ($("animate").checked && !r.cache_hit) {
    const finished = await animateExplored(r.explored_order);
    if (!finished) return;
  } else {
    paintExplored(r.explored_order);
  }
  drawPath(r.path);
  S.overlay = () => { paintExplored(r.explored_order); drawPath(r.path, { animate: false }); };
  refreshSide();
}

function showResult(r) {
  $("resultEmpty").classList.add("hidden");
  $("resultBody").classList.remove("hidden");
  $("resultTitle").innerHTML = `<b>${algoLabel(r.algorithm)}</b> · ${r.criterion === "time" ? "menor tiempo" : "menor distancia"}<br>${nodeName(r.origin)} → ${nodeName(r.destination)}`;
  const total = S.map.nodes.length;
  const cards = r.found ? [
    ["Costo de la ruta", fmtCost(r.cost, r.criterion), true],
    ["Distancia", fmtDist(r.distance_m)],
    ["Tiempo estimado", fmtTime(r.time_s)],
    ["Intersecciones", r.hops],
    ["Nodos explorados", `${r.expanded} <small>/ ${total}</small>`],
    ["Aristas evaluadas", r.relaxed],
    ["Tiempo de cómputo", `${r.elapsed_ms.toFixed(3)} <small>ms</small>`],
    ["Caché", r.cache_hit ? `HIT <small>${r.response_ms.toFixed(3)} ms</small>` : "MISS"],
  ] : [["Resultado", "Sin ruta", true], ["Nodos explorados", r.expanded]];
  $("metricCards").innerHTML = cards.map(([k, v, hl]) => `<div class="card${hl ? " hl" : ""}"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
  $("steps").innerHTML = (r.steps || []).map((s) =>
    `<li><span class="ic">${ICONS[s.maneuver] || "•"}</span><div>${s.instruction}${s.maneuver !== "arrive" ? `<div class="meta">${fmtTime(s.time_s)}</div>` : ""}</div></li>`).join("")
    || `<li><span class="ic">!</span><div>No existe una ruta con las calles disponibles.</div></li>`;
}

async function compare() {
  if (S.origin === S.destination) return toast("Origen y destino deben ser distintos");
  clearOverlay();
  const c = await api("/api/compare", { origin: S.origin, destination: S.destination, criterion: S.criterion });
  showTab("compare");
  $("compareEmpty").classList.add("hidden");
  $("compareBody").classList.remove("hidden");
  $("compareTitle").innerHTML = `${nodeName(c.origin)} → ${nodeName(c.destination)} · <b>${c.criterion === "time" ? "menor tiempo" : "menor distancia"}</b>`;
  const rows = c.results;
  $("compareTable").innerHTML = `<tr><th>Algoritmo</th><th>Costo</th><th>Δ vs óptimo</th><th>Nodos</th><th>ms</th><th>Óptima</th></tr>` +
    rows.map((r) => `<tr class="clickable" data-alg="${r.algorithm}">
      <td><span class="sw" style="background:${COLORS[r.algorithm]}"></span>${algoLabel(r.algorithm).split(" (")[0]}</td>
      <td>${fmtCost(r.cost, r.criterion)}</td>
      <td class="${r.overhead_pct > 0 ? "bad" : "ok"}">${r.overhead_pct == null ? "—" : `+${r.overhead_pct}%`}</td>
      <td>${r.expanded}</td><td>${r.elapsed_ms.toFixed(3)}</td>
      <td class="${r.optimal ? "ok" : "bad"}">${r.optimal ? "Sí" : "No"}</td></tr>`).join("");
  bars($("compareBars"), rows.map((r) => [r.algorithm, r.expanded]));
  const drawAll = () => {
    const widths = { bfs: 52, dijkstra: 40, astar: 28, greedy: 14 };
    rows.forEach((r) => drawPath(r.path, { color: COLORS[r.algorithm], width: widths[r.algorithm], animate: false, halo: r.algorithm === "bfs" }));
  };
  drawAll();
  S.overlay = drawAll;
  document.querySelectorAll("#compareTable tr.clickable").forEach((tr) => (tr.onclick = () => {
    const r = rows.find((x) => x.algorithm === tr.dataset.alg);
    S.gRoute.innerHTML = "";
    drawPath(r.path, { color: COLORS[r.algorithm], width: 34 });
    S.overlay = () => drawPath(r.path, { color: COLORS[r.algorithm], width: 34, animate: false });
  }));
  refreshSide();
}

function bars(container, data, fmt = (v) => v) {
  const max = Math.max(...data.map((d) => d[1]), 1);
  container.innerHTML = data.map(([alg, v]) => `<div class="bar"><span>${algoLabel(alg).split(" ")[0]}</span>
    <div class="track"><div class="fill" style="width:0;background:${COLORS[alg]}" data-w="${(v / max) * 100}"></div></div>
    <span class="val">${fmt(v)}</span></div>`).join("");
  requestAnimationFrame(() => container.querySelectorAll(".fill").forEach((f) => (f.style.width = `${f.dataset.w}%`)));
}

async function benchmark() {
  const btn = $("btnBench");
  btn.disabled = true;
  btn.textContent = "Ejecutando…";
  try {
    const b = await api(`/api/benchmark?size=${$("benchSize").value}&pairs=${$("benchPairs").value}`);
    $("benchBody").classList.remove("hidden");
    $("benchTitle").innerHTML = `<b>${b.nodes}</b> intersecciones · <b>${b.edges}</b> calles · ${b.pairs} pares aleatorios · criterio tiempo`;
    $("benchTable").innerHTML = `<tr><th>Algoritmo</th><th>ms prom.</th><th>Nodos prom.</th><th>Sobrecosto</th><th>% óptimas</th></tr>` +
      b.results.map((r) => `<tr><td><span class="sw" style="background:${COLORS[r.algorithm]}"></span>${algoLabel(r.algorithm).split(" (")[0]}</td>
        <td>${r.avg_ms.toFixed(2)}</td><td>${Math.round(r.avg_expanded)}</td>
        <td class="${r.avg_overhead_pct > 0 ? "bad" : "ok"}">+${r.avg_overhead_pct}%</td><td>${r.optimal_pct}%</td></tr>`).join("");
    bars($("benchBars"), b.results.map((r) => [r.algorithm, Math.round(r.avg_expanded)]));
  } finally {
    btn.disabled = false;
    btn.textContent = "Ejecutar prueba";
  }
}

async function refreshSide(events) {
  const [m, ev] = await Promise.all([api("/api/metrics"), events ? Promise.resolve(events) : api("/api/events")]);
  const c = m.cache;
  $("cacheCards").innerHTML = [
    ["Entradas", c.entries], ["Aciertos", c.hits], ["Fallos", c.misses],
    ["Tasa de acierto", `${Math.round(c.hit_rate * 100)}%`], ["Invalidaciones", c.invalidations], ["Re-ruteos", m.usage.reroutes],
  ].map(([k, v]) => `<div class="card"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
  const h = m.history;
  $("history").innerHTML = h.done.length || h.undone.length
    ? [...h.done.map((d) => `<li>✔ ${d}</li>`), ...h.undone.map((d) => `<li class="muted">↶ ${d} (deshecho)</li>`)].join("")
    : `<li class="muted">Sin comandos. Usa “Cerrar / abrir calle” o “Tráfico”.</li>`;
  $("events").innerHTML = ev.length
    ? ev.map((e) => `<li><span class="k ${e.kind}">${e.kind}</span>${e.detail} <span class="muted">· v${e.version}</span></li>`).join("")
    : `<li class="muted">Sin eventos todavía.</li>`;
}

init().catch(onError);
