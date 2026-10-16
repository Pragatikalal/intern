// Thin wrapper around Chart.js + fetch helpers for AJAX-style updates.
const charts = {};
const PALETTE = ["#0b6e4f", "#e9a03b", "#3b82c4", "#c0392b", "#7c5cbf", "#2a9d8f"];

function csrf() { return document.querySelector('meta[name="csrf"]').content; }

async function getJSON(url, params = {}) {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null)).toString();
  const res = await fetch(qs ? `${url}?${qs}` : url, { headers: { "X-Requested-With": "fetch" } });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}

function draw(id, type, labels, datasets, opts = {}) {
  const el = document.getElementById(id);
  if (!el) return;
  if (charts[id]) charts[id].destroy();
  datasets.forEach((d, i) => {
    d.backgroundColor = d.backgroundColor || PALETTE[i % PALETTE.length];
    d.borderColor = d.borderColor || PALETTE[i % PALETTE.length];
    if (type === "line") { d.pointRadius = d.pointRadius ?? 0; d.tension = 0.25; d.borderWidth = 2; }
  });
  charts[id] = new Chart(el, {
    type, data: { labels, datasets },
    options: Object.assign({ responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: datasets.length > 1 } },
      scales: { y: { beginAtZero: true, title: { display: true, text: opts.yTitle || "Units (kWh)" } } } }, opts.chart || {})
  });
}

function currentFilters() {
  const p = new URLSearchParams(window.location.search);
  return { consumer_id: p.get("consumer_id") || "", start: p.get("start") || "", end: p.get("end") || "" };
}

async function monthlyChart(id) {
  const d = await getJSON("/api/consumption", { ...currentFilters(), granularity: "monthly" });
  draw(id, "bar", d.labels, [{ label: "Monthly units", data: d.values }]);
}
async function dailyChart(id) {
  const d = await getJSON("/api/consumption", { ...currentFilters(), granularity: "daily" });
  draw(id, "line", d.labels, [{ label: "Daily units", data: d.values }]);
}
async function comparisonChart(id) {
  const f = currentFilters();
  const rows = await getJSON("/api/comparison", { start: f.start, end: f.end });
  draw(id, "bar", rows.map(r => r.name), [{ label: "Avg daily units", data: rows.map(r => r.avg_daily) }],
       { chart: { indexAxis: "y", scales: { x: { beginAtZero: true } } } });
}
async function peakCharts(hourId, dowId) {
  const p = await getJSON("/api/peaks", currentFilters());
  if (!p) return;
  if (p.hourly) draw(hourId, "bar", p.hourly.labels, [{ label: "Avg units per hour", data: p.hourly.values }], { yTitle: "Avg units / hour" });
  draw(dowId, "bar", p.dow.labels, [{ label: "Avg daily units", data: p.dow.values }]);
}
