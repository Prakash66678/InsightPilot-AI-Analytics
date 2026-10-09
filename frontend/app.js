/* InsightPilot frontend - vanilla JS, talks to the FastAPI backend under /api */
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const state = { sid: sessionStorage.getItem('ip_sid'), ov: null, view: 'dashboard', filters: {}, dash: null, explorer: { which: 'cleaned', page: 1, sort: '', dir: 'asc', q: '', flt: [] } };
let CUR = '';
// Works when served by the backend (port 8000) and also from Live Server / another port
const API = location.port === '8000' ? '' : 'http://127.0.0.1:8000';
let charts = [];

const NAV = [['upload', 'Upload Data'], ['dashboard', 'Dashboard'], ['quality', 'Data Quality'], ['explorer', 'Data Explorer'], ['kpis', 'KPI Analysis'],
  ['insights', 'Business Insights'], ['rca', 'Root Cause Analysis'], ['simulator', 'Decision Simulator'], ['recs', 'Recommendations'], ['report', 'Executive Report']];

/* ---------- helpers ---------- */
async function api(path, opts) {
  let r;
  try { r = await fetch(API + '/api' + path, opts); } catch (e) { throw new Error('Cannot reach the InsightPilot backend. Start it with: uvicorn app.main:app --port 8000 (inside the backend folder), then try again.'); }
  let j = null; try { j = await r.json(); } catch (e) { }
  if (!r.ok) {
    if (r.status === 404 && state.sid) { clearSession(); }
    throw new Error((j && (j.error || j.detail)) || ('Request failed (' + r.status + ')'));
  }
  return j;
}
function toast(msg) { const t = $('#toast'); t.textContent = msg; t.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => t.hidden = true, 4500); }
function compact(x) {
  const a = Math.abs(x);
  if (a >= 1e9) return (x / 1e9).toFixed(2) + 'B';
  if (a >= 1e6) return (x / 1e6).toFixed(2) + 'M';
  if (a >= 1e4) return (x / 1e3).toFixed(1) + 'K';
  return Number.isInteger(x) ? x.toLocaleString() : (Math.round(x * 10) / 10).toLocaleString();
}
function fmt(v, unit) {
  if (v === null || v === undefined) return '-';
  switch (unit) {
    case 'currency': return (v < 0 ? '-' : '') + CUR + compact(Math.abs(v));
    case 'percent': return (v * 100).toFixed(1) + '%';
    case 'percentSimple': return Number(v).toFixed(1) + '%';
    case 'days': return Number(v).toFixed(1) + ' days';
    case 'text': return String(v);
    default: return typeof v === 'number' ? compact(v) : String(v);
  }
}
function killCharts() { charts.forEach(c => c.destroy()); charts = []; }
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const PAL = () => ['#0b7a75', '#d9902f', '#44648f', '#c4503a', '#3f8f6b', '#8a6fb0', '#6b8e9b', '#b5783a', '#7a9a3a', '#9a4f7a', '#4a7a9a', '#c28a9a'];

function drawChart(canvas, c) {
  const txt = css('--muted'), grid = css('--line'), pal = PAL();
  const val = ctx => { const p = ctx.parsed; return (p && typeof p === 'object') ? (ctx.chart.options.indexAxis === 'y' ? p.x : p.y) : p; };
  let cfg;
  const base = { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false, labels: { color: txt } }, tooltip: { callbacks: { label: ctx => ' ' + (ctx.dataset.label || ctx.label) + ': ' + fmt(val(ctx), c.format) } } } };
  const scales = (f, horiz) => {
    const money = { ticks: { color: txt, callback: v => fmt(v, f) }, grid: { color: grid } };
    const cat = { ticks: { color: txt, maxRotation: 0, autoSkip: true, maxTicksLimit: horiz ? 12 : 9 }, grid: { display: false } };
    return horiz ? { x: money, y: cat } : { x: cat, y: money };
  };
  if (c.type === 'donut') {
    cfg = { type: 'doughnut', data: { labels: c.labels, datasets: [{ data: c.series[0].data, backgroundColor: pal, borderColor: css('--card'), borderWidth: 2 }] }, options: { ...base, cutout: '58%', plugins: { ...base.plugins, legend: { display: true, position: 'right', labels: { color: txt, boxWidth: 12 } } } } };
  } else if (c.type === 'scatter') {
    cfg = { type: 'scatter', data: { datasets: [{ label: 'Product', data: c.points.map(p => ({ x: p.x, y: p.y, label: p.label })), backgroundColor: '#0b7a75', pointRadius: 5 }] },
      options: { ...base, plugins: { ...base.plugins, tooltip: { callbacks: { label: ctx => ` ${ctx.raw.label}: ${fmt(ctx.raw.x, c.xFormat)}, ${ctx.raw.y.toFixed(1)}% margin` } } },
        scales: { x: { title: { display: true, text: c.xLabel, color: txt }, ticks: { color: txt, callback: v => fmt(v, c.xFormat) }, grid: { color: grid } }, y: { title: { display: true, text: c.yLabel, color: txt }, ticks: { color: txt, callback: v => v + '%' }, grid: { color: grid } } } } };
  } else {
    const horiz = c.type === 'hbar';
    const isBar = c.type === 'bar' || horiz;
    const ds = c.series.map((s, i) => ({ label: s.name, data: s.data, borderColor: pal[i], backgroundColor: isBar ? s.data.map(v => v < 0 ? '#c4503a' : pal[i]) : (c.type === 'area' ? pal[i] + '30' : pal[i]), fill: c.type === 'area', tension: .25, pointRadius: c.labels.length > 40 ? 0 : 2.5, borderWidth: 2, borderRadius: 3 }));
    cfg = { type: isBar ? 'bar' : 'line', data: { labels: c.labels, datasets: ds }, options: { ...base, indexAxis: horiz ? 'y' : 'x', scales: scales(c.format, horiz), interaction: { mode: 'index', intersect: false } } };
  }
  charts.push(new Chart(canvas, cfg));
}
function chartCard(c) {
  if (c.type === 'table') {
    return `<div class="card ${c.span === 2 ? 'wide' : ''}"><h3>${esc(c.title)}</h3><div class="scroll" style="margin-top:8px"><table><thead><tr>${c.columns.map(x => `<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>${c.rows.map(r => `<tr>${r.map((v, i) => `<td class="${i ? 'num' : ''}">${esc(fmt(v, c.formats[i]))}</td>`).join('')}</tr>`).join('')}</tbody></table></div></div>`;
  }
  return `<div class="card chart-card ${c.span === 2 ? 'wide' : ''}"><h3>${esc(c.title)}</h3>${c.subtitle ? `<div class="muted small">${esc(c.subtitle)}</div>` : ''}<div class="chart-box"><canvas data-chart="${esc(c.id)}"></canvas></div></div>`;
}
function mountCharts(list, root = document) { list.forEach(c => { if (c.type === 'table') return; const el = root.querySelector(`canvas[data-chart="${c.id}"]`); if (el) drawChart(el, c); }); }
function kpiCard(k) {
  let cls = '';
  if (k.unit === 'percent' && /Growth/.test(k.label)) cls = k.value >= 0 ? 'up' : 'down';
  const v = fmt(k.value, k.unit);
  return `<div class="kpi"><div class="l">${esc(k.label)}</div><div class="v ${cls}">${k.unit === 'percent' && cls === 'up' ? '+' : ''}${esc(v)}</div>${k.hint ? `<div class="h">${esc(k.hint)}</div>` : ''}</div>`;
}

/* ---------- shell ---------- */
function renderNav() {
  $('#nav').innerHTML = NAV.map(([k, l]) => `<button type="button" data-v="${k}" ${k !== 'upload' && !state.sid ? 'disabled' : ''} ${k === state.view || (k === 'upload' && !state.sid) ? 'aria-current="page"' : ''}>${l}</button>`).join('');
  $('#nav').querySelectorAll('button').forEach(b => b.onclick = () => go(b.dataset.v));
  const chip = $('#ds-chip');
  if (state.ov) { chip.hidden = false; chip.textContent = state.ov.filename + ' - ' + state.ov.summary.rows_after.toLocaleString() + ' rows'; } else chip.hidden = true;
}
function go(v) {
  state.view = v; killCharts(); renderNav();
  const title = (NAV.find(n => n[0] === v) || [0, 'InsightPilot'])[1];
  $('#page-title').textContent = state.sid || v === 'upload' ? title : 'InsightPilot';
  $('#top-actions').innerHTML = '';
  const view = $('#view'); view.innerHTML = '<div class="muted">Loading...</div>';
  const fn = (!state.sid || v === 'upload') ? viewLanding : ({ dashboard: viewDashboard, quality: viewQuality, explorer: viewExplorer, kpis: viewKpis, insights: viewInsights, rca: viewRca, simulator: viewSim, recs: viewRecs, report: viewReport }[v]);
  Promise.resolve(fn(view)).catch(e => { view.innerHTML = `<div class="err">${esc(e.message)}</div>`; });
  window.scrollTo(0, 0);
}
function clearSession() { state.sid = null; state.ov = null; sessionStorage.removeItem('ip_sid'); renderNav(); toast('Session expired - please upload your dataset again.'); go('upload'); }
function notes(list) { return (list || []).map(n => `<div class="note">${esc(n)}</div>`).join(''); }

/* ---------- landing + upload ---------- */
function viewLanding(view) {
  view.innerHTML = `
  <section class="hero">
    <div>
      <h2>Don't just analyze your data - make smarter business decisions.</h2>
      <p class="muted" style="font-size:16px;max-width:520px">InsightPilot reads your sales file, cleans it, calculates the KPIs that your columns support, explains what changed and why, and lets you test decisions before you make them. No Excel, SQL or BI tool needed.</p>
      <div class="drop" id="drop" tabindex="0" role="button" aria-label="Upload a dataset">
        <b>Drag and drop your dataset here</b>
        <span class="muted">CSV, XLSX or XLS</span>
        <div class="row" style="justify-content:center;margin-top:14px">
          <button class="btn" id="pick" type="button">Upload Dataset</button>
          <button class="btn alt" id="demo" type="button">Use Demo Dataset</button>
        </div>
        <input type="file" id="file" accept=".csv,.xlsx,.xls,.tsv,.txt" hidden>
      </div>
      <div id="up-err"></div>
      ${state.ov ? `<p class="muted small">Current dataset: <b>${esc(state.ov.filename)}</b>. Uploading a new file replaces it.</p>` : ''}
    </div>
    <div class="card">
      <h2>What happens after you upload</h2>
      <ol class="pipe">
        <li><b>Profile and clean</b><span class="muted">Types, missing values, duplicates, currency and date formats. Your original file is kept untouched.</span></li>
        <li><b>Understand the columns</b><span class="muted">Revenue, orders, customers, products, regions and dates are recognised even when named differently.</span></li>
        <li><b>Dashboard and KPIs</b><span class="muted">Only metrics your data can support, filterable by date, region, category and more.</span></li>
        <li><b>Insights and root causes</b><span class="muted">Every statement is calculated from your rows, never invented.</span></li>
        <li><b>Simulate and report</b><span class="muted">Test a discount or price change, then download an executive PDF.</span></li>
      </ol>
    </div>
  </section>`;
  const drop = $('#drop'), file = $('#file');
  $('#pick').onclick = e => { e.stopPropagation(); file.click(); };
  drop.onclick = () => file.click();
  drop.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); file.click(); } };
  file.onchange = () => file.files[0] && upload(file.files[0]);
  ['dragover', 'dragenter'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
  ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
  drop.addEventListener('drop', e => { const f = e.dataTransfer.files[0]; if (f) upload(f); });
  $('#demo').onclick = e => { e.stopPropagation(); runPipeline(() => api('/demo', { method: 'POST' })); };
}
const STAGES = ['Uploading', 'Profiling', 'Cleaning', 'Analyzing', 'Generating insights'];
function showProgress(on) { $('#progress').hidden = !on; }
function setStage(i) { $('#stages').innerHTML = STAGES.map((s, k) => `<li class="${k < i ? 'done' : k === i ? 'run' : ''}">${s}</li>`).join(''); }
function upload(file) {
  const err = $('#up-err'); if (err) err.innerHTML = '';
  const fd = new FormData(); fd.append('file', file);
  runPipeline(() => new Promise((resolve, reject) => {
    const x = new XMLHttpRequest(); x.open('POST', API + '/api/upload');
    x.upload.onprogress = e => { if (e.lengthComputable) $('#progress-note').textContent = `Uploaded ${Math.round(e.loaded / e.total * 100)}%`; };
    x.upload.onload = () => setStage(1);
    x.onload = () => { let j = {}; try { j = JSON.parse(x.responseText); } catch (e) { } x.status < 300 ? resolve(j) : reject(new Error(j.error || j.detail || 'Upload failed')); };
    x.onerror = () => reject(new Error('Could not reach the InsightPilot server. Is the backend running?'));
    x.send(fd);
  }));
}
async function runPipeline(task) {
  showProgress(true); setStage(0); $('#progress-note').textContent = '';
  let i = 0; const tm = setInterval(() => { if (i < STAGES.length - 1) { i++; setStage(i); } }, 900);
  try {
    const ov = await task();
    clearInterval(tm); setStage(STAGES.length); await new Promise(r => setTimeout(r, 350));
    state.sid = ov.id; state.ov = ov; CUR = ov.currency || ''; state.filters = {}; state.explorer = { which: 'cleaned', page: 1, sort: '', dir: 'asc', q: '', flt: [] };
    sessionStorage.setItem('ip_sid', ov.id); showProgress(false); go('dashboard');
  } catch (e) {
    clearInterval(tm); showProgress(false);
    const el = $('#up-err'); if (el) el.innerHTML = `<div class="err">${esc(e.message)}</div>`; else toast(e.message);
  }
}

/* ---------- dashboard ---------- */
const KPI_ORDER = ['revenue', 'orders', 'customers', 'aov', 'profit', 'margin', 'growth', 'units', 'cancel_rate', 'delivery', 'repeat', 'rating'];
async function viewDashboard(view) {
  const body = state.filters;
  const d = await api(`/session/${state.sid}/dashboard`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  state.dash = d; CUR = d.currency || CUR;
  killCharts();
  const kp = KPI_ORDER.map(k => d.kpis.find(x => x.key === k)).filter(Boolean).slice(0, 10);
  view.innerHTML = notes(state.ov.warnings.concat(d.notes)) + `<div id="filters"></div>
    <div class="muted small" style="margin-bottom:8px">Showing ${d.rows.toLocaleString()} of ${d.total_rows.toLocaleString()} rows${d.rows === 0 ? ' - no rows match these filters' : ''}</div>
    ${kp.length ? `<div class="kpis">${kp.map(kpiCard).join('')}</div>` : '<div class="note">No KPIs could be calculated from this dataset. See Data Quality to check how the columns were understood.</div>'}
    <div class="charts">${d.charts.map(chartCard).join('')}</div>`;
  renderFilters(d.filters);
  mountCharts(d.charts, view);
}
function renderFilters(opts) {
  const el = $('#filters'); const f = state.filters; const parts = [];
  if (opts.date) parts.push(`<label>From<input type="date" id="f-from" min="${opts.date.min}" max="${opts.date.max}" value="${f.date_from || ''}"></label><label>To<input type="date" id="f-to" min="${opts.date.min}" max="${opts.date.max}" value="${f.date_to || ''}"></label>`);
  Object.entries(opts).forEach(([k, o]) => {
    if (k === 'date') return;
    if (o.truncated) { parts.push(`<label>${o.label} (IDs, comma separated)<input type="text" data-ft="${k}" value="${esc((f[k] || []).join(','))}" placeholder="e.g. C10001,C10002"></label>`); return; }
    const sel = f[k] || [];
    parts.push(`<label>${o.label}<details class="ms"><summary>${sel.length ? sel.length + ' selected' : 'All'}</summary><div class="ms-list">${o.values.map(v => `<label><input type="checkbox" data-fk="${k}" value="${esc(v)}" ${sel.includes(v) ? 'checked' : ''}>${esc(v)}</label>`).join('')}</div></details></label>`);
  });
  parts.push('<button class="btn alt" id="f-reset" type="button">Reset Filters</button>');
  el.className = 'filters'; el.innerHTML = parts.join('');
  let t; const refresh = () => { clearTimeout(t); t = setTimeout(() => { go('dashboard'); }, 250); };
  const from = $('#f-from'), to = $('#f-to');
  if (from) from.onchange = () => { state.filters.date_from = from.value || undefined; refresh(); };
  if (to) to.onchange = () => { state.filters.date_to = to.value || undefined; refresh(); };
  el.querySelectorAll('input[data-fk]').forEach(cb => cb.onchange = () => { const k = cb.dataset.fk; const set = new Set(state.filters[k] || []); cb.checked ? set.add(cb.value) : set.delete(cb.value); state.filters[k] = [...set]; if (!set.size) delete state.filters[k]; refresh(); });
  el.querySelectorAll('input[data-ft]').forEach(inp => inp.onchange = () => { const v = inp.value.split(',').map(s => s.trim()).filter(Boolean); v.length ? state.filters[inp.dataset.ft] = v : delete state.filters[inp.dataset.ft]; refresh(); });
  $('#f-reset').onclick = () => { state.filters = {}; go('dashboard'); };
}

/* ---------- data quality ---------- */
async function viewQuality(view) {
  const ov = state.ov, q = ov.quality, s = ov.summary, p = ov.profile_original;
  const col = q.score >= 90 ? 'var(--sage)' : q.score >= 75 ? 'var(--teal)' : q.score >= 55 ? 'var(--amber)' : 'var(--rust)';
  const C = 2 * Math.PI * 52;
  view.innerHTML = notes(ov.warnings.concat(ov.notes)) + `
  <div class="grid g2">
    <div class="card"><h2>Data Quality Score</h2><div class="ring">
      <svg width="130" height="130" viewBox="0 0 130 130" role="img" aria-label="Score ${q.score} out of 100"><circle cx="65" cy="65" r="52" fill="none" stroke="var(--line)" stroke-width="12"/><circle cx="65" cy="65" r="52" fill="none" stroke="${col}" stroke-width="12" stroke-linecap="round" stroke-dasharray="${C * q.score / 100} ${C}" transform="rotate(-90 65 65)"/><text x="65" y="63" text-anchor="middle" font-size="30" font-weight="700" fill="var(--text)">${q.score}</text><text x="65" y="82" text-anchor="middle" font-size="12" fill="var(--muted)">out of 100</text></svg>
      <div><b>${esc(q.grade)}</b><div class="muted small">Points lost per area are shown on the right.</div></div></div></div>
    <div class="card"><h2>What reduced the score</h2>${q.components.map(c => `<div style="margin-bottom:11px"><div class="row" style="justify-content:space-between"><b>${esc(c.name)}</b><span class="${c.lost > 0.5 ? 'down' : 'muted'}">-${c.lost} of ${c.max}</span></div><div class="bar"><i style="width:${c.earned / c.max * 100}%"></i></div><div class="muted small">${esc(c.detail)}</div></div>`).join('')}</div>
  </div>
  <div class="card" style="margin-top:14px"><h2>Cleaning summary</h2>
    <div class="kpis" style="margin:0">${[['Rows before cleaning', s.rows_before], ['Rows after cleaning', s.rows_after], ['Duplicates removed', s.duplicates_removed], ['Missing values handled', s.missing_handled], ['Columns transformed', s.columns_transformed], ['Invalid values fixed', s.invalid_values_fixed]].map(([l, v]) => `<div class="kpi"><div class="l">${l}</div><div class="v">${Number(v).toLocaleString()}</div></div>`).join('')}</div>
    <p class="muted small">The original dataset is kept exactly as uploaded; all changes apply to a separate cleaned copy.</p>
    <div class="row"><button class="btn alt" id="show-log" type="button">View cleaning log</button><a class="btn alt" href="${API}/api/session/${state.sid}/download/cleaning-log">Download log (CSV)</a></div><div id="log"></div></div>
  <div class="card" style="margin-top:14px"><h2>How your columns were understood</h2><p class="muted small">Matched from column names and data types. If something is wrong, rename the column in your file and re-upload.</p>
    <div class="scroll"><table><thead><tr><th>Business field</th><th>Your column</th><th>Confidence</th></tr></thead><tbody>${ov.roles.map(r => `<tr><td>${esc(r.label)}</td><td>${esc(r.column)}</td><td>${esc(r.confidence)}</td></tr>`).join('')}</tbody></table></div></div>
  <div class="card" style="margin-top:14px"><h2>Profile of the uploaded file</h2><p class="muted small">${p.rows.toLocaleString()} rows, ${p.columns} columns, ${p.duplicate_rows} duplicate rows, ${p.missing_cells.toLocaleString()} missing cells (${p.missing_pct}%)</p>${profileTable(p)}</div>`;
  $('#show-log').onclick = async () => {
    const log = await api(`/session/${state.sid}/cleaning-log`);
    $('#log').innerHTML = log.length ? `<div class="scroll" style="margin-top:10px"><table><thead><tr><th>Step</th><th>Column</th><th>What was done</th><th>Count</th></tr></thead><tbody>${log.map(l => `<tr><td>${esc(l.step)}</td><td>${esc(l.column)}</td><td style="white-space:normal">${esc(l.detail)}</td><td class="num">${l.count ?? ''}</td></tr>`).join('')}</tbody></table></div>` : '<p class="muted">Nothing needed cleaning.</p>';
  };
}
function profileTable(p) {
  return `<div class="scroll"><table><thead><tr><th>Column</th><th>Type</th><th>Missing</th><th>Unique</th><th>Statistics</th></tr></thead><tbody>${p.column_profiles.map(c => {
    const st = c.stats || {}; let s = '';
    if (c.kind === 'numeric' && st.mean !== undefined) s = `min ${compact(st.min)} | median ${compact(st.median)} | mean ${compact(st.mean)} | max ${compact(st.max)} | std ${compact(st.std)}`;
    else if (c.kind === 'datetime') s = `${st.min} to ${st.max}`;
    else if (st.top) s = st.top.slice(0, 3).map(t => `${t.value} (${t.count})`).join(', ');
    return `<tr><td>${esc(c.name)}</td><td>${esc(c.kind)}</td><td class="num">${c.missing} (${c.missing_pct}%)</td><td class="num">${c.unique.toLocaleString()}</td><td title="${esc(s)}">${esc(s)}</td></tr>`;
  }).join('')}</tbody></table></div>`;
}

/* ---------- explorer ---------- */
async function viewExplorer(view) {
  const e = state.explorer;
  const prof = e.which === 'original' ? state.ov.profile_original : state.ov.profile_cleaned;
  const qs = new URLSearchParams({ which: e.which, q: e.q, sort: e.sort, dir: e.dir, page: e.page, page_size: 50, filters: JSON.stringify(e.flt) });
  const d = await api(`/session/${state.sid}/data?${qs}`);
  const pages = Math.max(1, Math.ceil(d.total / d.page_size));
  view.innerHTML = `<div class="tabs"><button type="button" data-w="original" aria-pressed="${e.which === 'original'}">Original dataset</button><button type="button" data-w="cleaned" aria-pressed="${e.which === 'cleaned'}">Cleaned dataset</button></div>
  <div class="filters"><label>Search all columns<input id="x-q" value="${esc(e.q)}" placeholder="Type and press Enter"></label>
   <label>Filter column<select id="x-col"><option value="">-</option>${d.columns.map(c => `<option>${esc(c)}</option>`).join('')}</select></label>
   <label>Condition<select id="x-op"><option value="contains">contains</option><option value="equals">equals</option><option value="gt">greater than</option><option value="lt">less than</option></select></label>
   <label>Value<input id="x-val"></label><button class="btn alt" id="x-add" type="button">Add filter</button>
   <a class="btn alt" href="${API}/api/session/${state.sid}/download/original">Download Original Dataset</a><a class="btn" href="${API}/api/session/${state.sid}/download/cleaned">Download Cleaned Dataset</a></div>
  ${e.flt.length ? `<div class="row small" style="margin-bottom:8px">Active filters: ${e.flt.map((f, i) => `<button class="btn alt" data-rm="${i}" type="button">${esc(f.col)} ${esc(f.op)} ${esc(f.value)} x</button>`).join('')}</div>` : ''}
  <div class="muted small" style="margin-bottom:6px">${d.total.toLocaleString()} rows - page ${d.page} of ${pages} - click a header to sort</div>
  <div class="scroll"><table><thead><tr>${d.columns.map(c => `<th class="sortable" data-s="${esc(c)}">${esc(c)}${e.sort === c ? (e.dir === 'asc' ? ' ▲' : ' ▼') : ''}</th>`).join('')}</tr></thead><tbody>${d.rows.map(r => `<tr>${r.map(v => `<td class="${typeof v === 'number' ? 'num' : ''}">${v === null ? '<span class="muted">-</span>' : esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
  <div class="row" style="margin:10px 0"><button class="btn alt" id="pg-prev" type="button" ${d.page <= 1 ? 'disabled' : ''}>Previous</button><button class="btn alt" id="pg-next" type="button" ${d.page >= pages ? 'disabled' : ''}>Next</button></div>
  <div class="card"><h2>Column statistics (${e.which})</h2>${profileTable(prof)}</div>`;
  const re = () => go('explorer');
  view.querySelectorAll('.tabs button').forEach(b => b.onclick = () => { e.which = b.dataset.w; e.page = 1; e.sort = ''; e.flt = []; re(); });
  $('#x-q').onkeydown = ev => { if (ev.key === 'Enter') { e.q = ev.target.value; e.page = 1; re(); } };
  $('#x-add').onclick = () => { const col = $('#x-col').value, val = $('#x-val').value; if (col && val !== '') { e.flt.push({ col, op: $('#x-op').value, value: val }); e.page = 1; re(); } };
  view.querySelectorAll('[data-rm]').forEach(b => b.onclick = () => { e.flt.splice(+b.dataset.rm, 1); re(); });
  view.querySelectorAll('th[data-s]').forEach(th => th.onclick = () => { const c = th.dataset.s; if (e.sort === c) e.dir = e.dir === 'asc' ? 'desc' : 'asc'; else { e.sort = c; e.dir = 'asc'; } re(); });
  $('#pg-prev').onclick = () => { e.page--; re(); }; $('#pg-next').onclick = () => { e.page++; re(); };
}

/* ---------- KPI analysis ---------- */
async function viewKpis(view) {
  const d = await api(`/session/${state.sid}/dashboard`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
  CUR = d.currency || CUR;
  const groups = {}; d.kpis.forEach(k => (groups[k.group] = groups[k.group] || []).push(k));
  $('#top-actions').innerHTML = `<a class="btn alt" href="${API}/api/session/${state.sid}/download/kpis">Download KPI results (CSV)</a>`;
  view.innerHTML = notes(d.notes) + (Object.keys(groups).length ? Object.entries(groups).map(([g, ks]) => `<h2 style="margin-top:6px">${esc(g)} KPIs</h2><div class="kpis">${ks.map(kpiCard).join('')}</div>`).join('') : '<div class="note">No KPIs can be calculated from the columns in this dataset.</div>')
    + '<p class="muted small">Only KPIs that your columns can support are shown. Revenue, profit and customer KPIs exclude cancelled and returned orders when a status column exists.</p>';
}

/* ---------- insights ---------- */
const TYPE_LABEL = { risk: 'Risk', opportunity: 'Opportunity', growth: 'Growth', top: 'Top performer', info: 'Observation' };
async function viewInsights(view) {
  const d = await api(`/session/${state.sid}/insights`);
  view.innerHTML = notes(d.notes) + `<div class="row" style="margin-bottom:12px"><button class="btn alt" id="ai-btn" type="button">Explain in plain language (AI, optional)</button></div><div id="ai-out"></div>
  <div class="grid g2">${d.insights.map(i => `<div class="card ic ${i.type}"><span class="tag ${i.type}">${TYPE_LABEL[i.type] || i.type}</span><h3>${esc(i.title)}</h3><div>${esc(i.text)}</div>${i.evidence.length ? `<ul class="ev">${i.evidence.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}</div>`).join('')}</div>`;
  $('#ai-btn').onclick = async () => {
    $('#ai-out').innerHTML = '<div class="muted">Asking the AI provider...</div>';
    const r = await api(`/session/${state.sid}/ai-summary`, { method: 'POST' });
    $('#ai-out').innerHTML = r.text ? `<div class="card" style="margin-bottom:12px"><span class="tag info">AI explanation of the calculated findings</span><div style="white-space:pre-wrap">${esc(r.text)}</div></div>` : `<div class="note">${esc(r.message || 'No response.')}</div>`;
  };
}

/* ---------- root cause ---------- */
async function viewRca(view) {
  const d = await api(`/session/${state.sid}/rca`);
  if (!d.enabled) { view.innerHTML = `<div class="note">${esc(d.reason)}</div>`; return; }
  if (!d.cases.length) { view.innerHTML = `<div class="card">${esc(d.message)}</div>`; return; }
  view.innerHTML = `<p class="muted">${esc(d.disclaimer)}</p>` + d.cases.map((c, i) => `
    <div class="card" style="margin-bottom:16px"><div class="flow">
      <div><span class="tag ${c.direction === 'down' ? 'risk' : 'growth'}">Problem</span><h3>${esc(c.problem)}</h3><div class="muted small">${CUR}${compact(c.revenue_before)} -> ${CUR}${compact(c.revenue_after)}</div></div>
      <div class="arrow">→</div>
      <div><span class="tag top">Contributing factors, evidence and possible action</span>${c.factors.map(f => `<div class="factor"><b>${esc(f.factor)}</b><div class="muted small">Evidence: ${esc(f.evidence)}</div><div class="small">Possible action: ${esc(f.action)}</div></div>`).join('')}</div>
    </div>${c.chart ? `<div class="chart-box" style="height:240px;margin-top:14px"><canvas id="rca-${i}"></canvas></div><div class="muted small">${esc(c.chart.title)}</div>` : ''}</div>`).join('');
  d.cases.forEach((c, i) => { if (c.chart) { const el = $('#rca-' + i); drawChart(el, { type: 'bar', format: 'currency', labels: c.chart.labels, series: [{ name: 'Revenue change', data: c.chart.values }] }); } });
}

/* ---------- simulator ---------- */
async function viewSim(view) {
  const cfg = await api(`/session/${state.sid}/simulator`);
  if (!cfg.enabled) { view.innerHTML = `<div class="note">${esc(cfg.reason)}</div>`; return; }
  const b = cfg.baseline, c = cfg.controls;
  const defs = [['discount', 'Average discount (%)', 0, 40, 0.5, +(b.avg_discount * 100).toFixed(1)], ['price', 'Price change (%)', -30, 30, 1, 0], ['quantity', 'Sales quantity change (%)', -50, 100, 1, 0], ['marketing', 'Marketing spend change (%)', -50, 100, 1, 0], ['conversion', 'Conversion rate change (%)', -50, 100, 1, 0]];
  view.innerHTML = `<div class="row" style="margin-bottom:12px"><span class="badge">ESTIMATED / SIMULATION</span><span class="muted small">Directional estimates based on stated assumptions - not guaranteed results.</span></div>
  <div class="sim-grid"><div class="card"><h2>Change a decision</h2>${defs.map(([k, l, mn, mx, st, v]) => `<div class="ctl ${c[k].enabled ? '' : 'off'}"><label for="s-${k}"><span>${l}</span><output id="o-${k}">${v}</output></label><input type="range" id="s-${k}" min="${mn}" max="${mx}" step="${st}" value="${v}" ${c[k].enabled ? '' : 'disabled'}>${c[k].enabled ? '' : `<div class="muted small">Disabled: ${esc(c[k].reason)}</div>`}</div>`).join('')}<button class="btn alt" id="s-reset" type="button">Reset to current values</button></div>
  <div><div class="card" id="sim-out">Calculating...</div><div class="card" style="margin-top:14px"><h3>Revenue and profit vs discount level (estimated)</h3><div class="chart-box"><canvas id="sim-curve"></canvas></div></div></div></div>`;
  let t, curve = null;
  const run = async () => {
    const p = { discount_pct: +$('#s-discount').value, price_change_pct: +$('#s-price').value, quantity_change_pct: +$('#s-quantity').value, marketing_change_pct: +$('#s-marketing').value, conversion_change_pct: +$('#s-conversion').value };
    defs.forEach(([k]) => $('#o-' + k).textContent = $('#s-' + k).value);
    const r = await api(`/session/${state.sid}/simulate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(p) });
    const rows = [['Revenue', 'revenue', 'currency'], ['Orders', 'orders', 'number'], ['Profit', 'profit', 'currency'], ['Profit margin', 'margin', 'percent']].filter(x => r.baseline[x[1]] !== null && r.baseline[x[1]] !== undefined);
    $('#sim-out').innerHTML = `<h2>Estimated outcome</h2><table><thead><tr><th></th><th>Current</th><th>Estimated</th><th>Change</th></tr></thead><tbody>${rows.map(([l, k, u]) => {
      const a = r.baseline[k], s = r.scenario[k]; const dlt = k === 'margin' ? (s - a) * 100 : s - a; const rel = k === 'margin' ? dlt.toFixed(1) + ' pts' : (a ? (dlt / Math.abs(a) * 100).toFixed(1) + '%' : '');
      return `<tr><td>${l}</td><td class="num">${fmt(a, u)}</td><td class="num"><b>${fmt(s, u)}</b></td><td class="num ${dlt >= 0 ? 'up' : 'down'}">${dlt >= 0 ? '+' : ''}${rel}</td></tr>`;
    }).join('')}</tbody></table><ul class="ev">${r.assumptions.map(a => `<li>${esc(a)}</li>`).join('')}</ul>`;
    if (r.curve.length) {
      const data = { labels: r.curve.map(x => x.discount + '%'), series: [{ name: 'Revenue', data: r.curve.map(x => x.revenue) }].concat(r.curve[0].profit !== null ? [{ name: 'Profit', data: r.curve.map(x => x.profit) }] : []) };
      if (curve) { curve.data.labels = data.labels; data.series.forEach((s, i) => { curve.data.datasets[i].data = s.data; }); curve.update('none'); }
      else { drawChart($('#sim-curve'), { type: 'line', format: 'currency', ...data }); curve = charts[charts.length - 1]; curve.options.plugins.legend.display = true; curve.update(); }
    }
  };
  defs.forEach(([k]) => $('#s-' + k).oninput = () => { clearTimeout(t); t = setTimeout(() => run().catch(e => toast(e.message)), 120); });
  $('#s-reset').onclick = () => { defs.forEach(([k, , , , , v]) => $('#s-' + k).value = v); run(); };
  await run();
}

/* ---------- recommendations ---------- */
async function viewRecs(view) {
  const d = await api(`/session/${state.sid}/recommendations`);
  view.innerHTML = `<div class="grid">${d.recommendations.map((r, i) => `<div class="card"><span class="tag ${r.priority}">${r.priority} priority</span><h2>Recommendation ${i + 1}: ${esc(r.title)}</h2>
    <div class="grid g2"><div><h3>Finding</h3>${esc(r.finding)}<h3 style="margin-top:10px">Evidence</h3>${esc(r.evidence)}</div><div><h3>Business impact</h3>${esc(r.impact)}<h3 style="margin-top:10px">Recommended action</h3>${esc(r.action)}</div></div></div>`).join('')}</div>`;
}

/* ---------- report ---------- */
async function viewReport(view) {
  const d = await api(`/session/${state.sid}/report`);
  $('#top-actions').innerHTML = `<div class="row"><a class="btn" href="${API}/api/session/${state.sid}/download/report">Download Executive Report (PDF)</a><a class="btn alt" href="${API}/api/session/${state.sid}/download/cleaned">Cleaned data (CSV)</a><a class="btn alt" href="${API}/api/session/${state.sid}/download/kpis">KPI results (CSV)</a></div>`;
  view.innerHTML = `<div class="card rep"><h2 style="font-size:22px">Executive Report</h2><div class="muted small">${esc(d.filename)} - data quality ${d.quality}/100</div>${Object.entries(d.sections).map(([t, items]) => `<h3>${esc(t)}</h3><ul>${items.map(i => `<li>${esc(i)}</li>`).join('')}</ul>`).join('')}</div>`;
}

/* ---------- boot ---------- */
$('#theme-btn').onclick = () => {
  const dark = document.documentElement.dataset.theme !== 'dark';
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  $('#theme-btn').textContent = dark ? 'Switch to light mode' : 'Switch to dark mode';
  localStorage.setItem('ip_theme', dark ? 'dark' : 'light'); go(state.view);
};
if (localStorage.getItem('ip_theme') === 'dark') { document.documentElement.dataset.theme = 'dark'; $('#theme-btn').textContent = 'Switch to light mode'; }
(async function boot() {
  renderNav();
  if (state.sid) {
    try { state.ov = await api(`/session/${state.sid}/overview`); CUR = state.ov.currency || ''; go('dashboard'); return; } catch (e) { state.sid = null; sessionStorage.removeItem('ip_sid'); }
  }
  go('upload');
})();
