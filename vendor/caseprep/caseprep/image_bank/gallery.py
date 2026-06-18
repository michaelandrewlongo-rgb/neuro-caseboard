#!/usr/bin/env python3
"""Image Bank Gallery — Flask-based browser for 76K neurosurgical images."""

import json, os, sqlite3
from pathlib import Path
from flask import Flask, jsonify, request, send_file, Response, render_template_string

BANK_DIR = Path(__file__).parent
DB_PATH = BANK_DIR / "bank.db"
IMAGES_DIR = BANK_DIR / "images"

app = Flask(__name__)

# ── DB ───────────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;")
    return conn

# ── API ──────────────────────────────────────────────────────────────────────

@app.route("/api/clusters")
def api_clusters():
    conn = get_db()
    rows = conn.execute("""
        SELECT i.cluster,
               COUNT(*) AS total,
               COUNT(l.fig_id) AS labeled,
               ROUND(AVG(l.surgical_usefulness), 1) AS avg_usefulness
        FROM images i
        LEFT JOIN labels l ON l.fig_id = i.fig_id
        GROUP BY i.cluster
        ORDER BY i.cluster
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/modalities")
def api_modalities():
    conn = get_db()
    rows = conn.execute("""
        SELECT modality, COUNT(*) AS cnt
        FROM labels
        WHERE modality IS NOT NULL AND modality != ''
        GROUP BY modality
        ORDER BY cnt DESC
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/images")
def api_images():
    cluster = request.args.get("cluster")
    modality = request.args.get("modality")
    min_usefulness = request.args.get("min_usefulness", type=int)
    search = request.args.get("search")
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)

    conn = get_db()
    where = []
    params = []

    if cluster:
        where.append("i.cluster = ?")
        params.append(cluster)
    if modality:
        where.append("l.modality = ?")
        params.append(modality)
    if min_usefulness is not None:
        where.append("l.surgical_usefulness >= ?")
        params.append(min_usefulness)
    if search:
        where.append("(i.fig_id LIKE ? OR l.caption_summary LIKE ? OR l.anatomy LIKE ?)")
        params.extend([f"%{search}%"] * 3)

    where_clause = ("WHERE " + " AND ".join(where)) if where else ""

    rows = conn.execute(f"""
        SELECT i.id, i.fig_id, i.cluster, i.local_path,
               l.modality, l.surgical_usefulness, l.anatomy, l.pathology,
               l.procedure, l.caption_summary, l.keywords, l.is_neurosurgical
        FROM images i
        LEFT JOIN labels l ON l.fig_id = i.fig_id
        {where_clause}
        ORDER BY i.id
        LIMIT ? OFFSET ?
    """, params + [limit, offset]).fetchall()

    total = conn.execute(f"""
        SELECT COUNT(*)
        FROM images i
        LEFT JOIN labels l ON l.fig_id = i.fig_id
        {where_clause}
    """, params).fetchone()[0]

    conn.close()
    return jsonify({"images": [dict(r) for r in rows], "total": total})


# ── Image serving ────────────────────────────────────────────────────────────

@app.route("/img/<path:img_path>")
def serve_image(img_path):
    full = IMAGES_DIR / img_path
    if not full.exists():
        return "Not found", 404
    return send_file(str(full))


# ── Frontend (inline HTML) ──────────────────────────────────────────────────

GALLERY_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Neurosurgery Image Bank</title>
<style>
  :root { --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9; --text-dim: #8b949e; --accent: #58a6ff; --tag-bg: #1f2937; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }
  .header { padding: 20px 24px; border-bottom: 1px solid var(--border); background: var(--card); display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
  .header h1 { font-size: 20px; font-weight: 600; }
  .header .stats { color: var(--text-dim); font-size: 14px; }
  .header input { background: #0d1117; border: 1px solid var(--border); color: var(--text); padding: 8px 12px; border-radius: 6px; font-size: 14px; flex: 1; min-width: 200px; }
  .header select { background: #0d1117; border: 1px solid var(--border); color: var(--text); padding: 8px 12px; border-radius: 6px; font-size: 14px; }
  .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
  .cluster-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
  .cluster-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; cursor: pointer; transition: border-color .15s, transform .1s; }
  .cluster-card:hover { border-color: var(--accent); transform: translateY(-1px); }
  .cluster-card h3 { font-size: 16px; margin-bottom: 4px; text-transform: capitalize; }
  .cluster-card .stats-line { color: var(--text-dim); font-size: 13px; display: flex; gap: 12px; flex-wrap: wrap; }
  .image-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
  .image-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; cursor: pointer; transition: border-color .15s; }
  .image-card:hover { border-color: var(--accent); }
  .image-card img { width: 100%; height: 160px; object-fit: cover; display: block; background: #000; }
  .image-card .info { padding: 8px 10px; font-size: 12px; }
  .image-card .info .fig-id { font-weight: 500; margin-bottom: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .image-card .info .modality { color: var(--accent); }
  .image-card .info .usefulness { color: var(--text-dim); }
  .image-card .info .anatomy { color: var(--text-dim); font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .tag { display: inline-block; background: var(--tag-bg); padding: 1px 6px; border-radius: 4px; font-size: 11px; color: var(--text-dim); }
  .tag.radio { border: 1px solid #f0883e; color: #f0883e; }
  .tag.ct { border: 1px solid #7ee787; color: #7ee787; }
  .tag.mri { border: 1px solid #58a6ff; color: #58a6ff; }
  .tag.dsa { border: 1px solid #d2a8ff; color: #d2a8ff; }
  .tag.diagram { border: 1px solid #f778ba; color: #f778ba; }
  .tag.photo { border: 1px solid #a5d6ff; color: #a5d6ff; }
  .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.85); z-index: 100; justify-content: center; align-items: center; padding: 40px; }
  .modal-overlay.open { display: flex; }
  .modal { background: var(--card); border: 1px solid var(--border); border-radius: 12px; max-width: 1000px; max-height: 90vh; overflow-y: auto; display: flex; flex-direction: column; }
  .modal img { max-width: 100%; max-height: 60vh; object-fit: contain; background: #000; border-radius: 12px 12px 0 0; }
  .modal .detail { padding: 20px; }
  .modal .detail h2 { font-size: 16px; margin-bottom: 12px; }
  .modal .detail .field { margin-bottom: 8px; }
  .modal .detail .field-label { color: var(--text-dim); font-size: 12px; text-transform: uppercase; letter-spacing: .5px; }
  .modal .detail .field-value { font-size: 14px; }
  .modal .close { position: fixed; top: 20px; right: 30px; font-size: 32px; color: #fff; cursor: pointer; opacity: .7; }
  .modal .close:hover { opacity: 1; }
  .pagination { display: flex; justify-content: center; align-items: center; gap: 12px; margin: 24px 0; font-size: 14px; }
  .pagination button { background: var(--card); border: 1px solid var(--border); color: var(--text); padding: 6px 14px; border-radius: 6px; cursor: pointer; }
  .pagination button:disabled { opacity: .4; cursor: default; }
  .pagination button:hover:not(:disabled) { border-color: var(--accent); }
  .breadcrumb { padding: 16px 0; font-size: 14px; }
  .breadcrumb a { color: var(--accent); text-decoration: none; cursor: pointer; }
  .breadcrumb a:hover { text-decoration: underline; }
  .loading { text-align: center; padding: 60px; color: var(--text-dim); }
  .spinner { width: 32px; height: 32px; border: 3px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .8s linear infinite; margin: 0 auto 12px; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<div class="header">
  <h1>🩻 Neurosurgery Image Bank</h1>
  <span class="stats" id="header-stats"></span>
  <input id="search" type="text" placeholder="Search fig ID, anatomy, caption…" oninput="debounceSearch()">
  <select id="modality-filter" onchange="applyFilters()">
    <option value="">All modalities</option>
  </select>
  <select id="usefulness-filter" onchange="applyFilters()">
    <option value="">Any usefulness</option>
    <option value="5">★★★★★ 5</option>
    <option value="4">★★★★☆ 4+</option>
    <option value="3">★★★☆☆ 3+</option>
  </select>
</div>

<div class="container" id="app"></div>

<div class="modal-overlay" id="modal" onclick="if(event.target===this)closeModal()">
  <span class="close" onclick="closeModal()">&times;</span>
  <div class="modal" id="modal-content"></div>
</div>

<script>
const API = '';
let state = { view: 'clusters', cluster: null, offset: 0, limit: 50, total: 0 };
let searchTimer = null;

async function api(path) { const r = await fetch(path); return r.json(); }

async function init() {
  const [clusters, modalities] = await Promise.all([
    api('/api/clusters'),
    api('/api/modalities'),
  ]);
  const totalImgs = clusters.reduce((s,c) => s + c.total, 0);
  const totalLab = clusters.reduce((s,c) => s + c.labeled, 0);
  document.getElementById('header-stats').textContent =
    `${totalImgs.toLocaleString()} images · ${clusters.length} clusters · ${totalLab.toLocaleString()} labeled`;

  const sel = document.getElementById('modality-filter');
  modalities.forEach(m => {
    const o = document.createElement('option');
    o.value = m.modality;
    o.textContent = `${m.modality} (${m.cnt})`;
    sel.appendChild(o);
  });

  renderClusters(clusters);
}

function renderClusters(clusters) {
  state.view = 'clusters';
  const app = document.getElementById('app');
  app.innerHTML = '<div class="cluster-grid">' +
    clusters.map(c => `
      <div class="cluster-card" onclick="openCluster('${c.cluster}')">
        <h3>${c.cluster.replace(/_/g, ' ')}</h3>
        <div class="stats-line">
          <span>${c.total.toLocaleString()} images</span>
          ${c.labeled ? `<span>${c.labeled} labeled</span>` : ''}
          ${c.avg_usefulness ? `<span>★ ${c.avg_usefulness}</span>` : ''}
        </div>
      </div>
    `).join('') + '</div>';
}

async function openCluster(cluster) {
  state.view = 'images';
  state.cluster = cluster;
  state.offset = 0;
  await loadImages();
}

async function loadImages() {
  const params = new URLSearchParams({ limit: state.limit, offset: state.offset });
  if (state.cluster) params.set('cluster', state.cluster);
  const mod = document.getElementById('modality-filter').value;
  if (mod) params.set('modality', mod);
  const usf = document.getElementById('usefulness-filter').value;
  if (usf) params.set('min_usefulness', usf);
  const search = document.getElementById('search').value.trim();
  if (search) params.set('search', search);

  const app = document.getElementById('app');
  app.innerHTML = '<div class="loading"><div class="spinner"></div>Loading…</div>';

  const data = await api(`/api/images?${params}`);
  state.total = data.total;
  renderImages(data.images, data.total);
}

function renderImages(images, total) {
  const app = document.getElementById('app');
  const start = state.offset + 1;
  const end = Math.min(state.offset + images.length, total);

  app.innerHTML = `
    <div class="breadcrumb">
      <a onclick="goHome()">Clusters</a>
      ${state.cluster ? ` / <span style="color:var(--text-dim)">${state.cluster.replace(/_/g, ' ')}</span>` : ''}
      <span style="color:var(--text-dim);margin-left:12px">${start}–${end} of ${total.toLocaleString()}</span>
    </div>
    <div class="image-grid">
      ${images.map(img => {
        const path = img.local_path ? img.local_path.replace('/home/michael/projects/caseprep/caseprep/image_bank', '') : '';
        const modClass = (img.modality || '').replace(/[^a-z]/g,'').slice(0,10);
        const tagClass = modClass.includes('mri')?'mri':modClass.includes('ct')?'ct':modClass.includes('angiogram')||modClass.includes('dsa')?'dsa':modClass.includes('diagram')?'diagram':modClass.includes('photo')||modClass.includes('microscope')?'photo':'';
        const anatomy = img.anatomy ? JSON.parse(img.anatomy).slice(0,3).join(', ') : '';
        return `
          <div class="image-card" onclick="openDetail('${img.fig_id}')">
            <img src="${path}" loading="lazy" onerror="this.parentElement.innerHTML='<div style=\\'padding:60px 10px;text-align:center;color:var(--text-dim);font-size:12px\\'>No image</div>'">
            <div class="info">
              <div class="fig-id">${img.fig_id}</div>
              ${img.modality ? `<div class="modality"><span class="tag ${tagClass}">${img.modality}</span></div>` : ''}
              ${img.surgical_usefulness ? `<div class="usefulness">${'★'.repeat(img.surgical_usefulness)}</div>` : ''}
              ${anatomy ? `<div class="anatomy" title="${anatomy}">${anatomy}</div>` : ''}
            </div>
          </div>
        `;
      }).join('')}
    </div>
    ${total > state.limit ? `
      <div class="pagination">
        <button onclick="page(-1)" ${state.offset === 0 ? 'disabled' : ''}>← Previous</button>
        <span>Page ${Math.floor(state.offset / state.limit) + 1} of ${Math.ceil(total / state.limit)}</span>
        <button onclick="page(1)" ${state.offset + state.limit >= total ? 'disabled' : ''}>Next →</button>
      </div>
    ` : ''}
  `;
}

function page(dir) { state.offset += dir * state.limit; if (state.offset < 0) state.offset = 0; loadImages(); }
function goHome() { state.cluster = null; state.offset = 0; init(); }
function applyFilters() { if (state.view === 'images') loadImages(); }
function debounceSearch() { clearTimeout(searchTimer); searchTimer = setTimeout(applyFilters, 400); }

async function openDetail(figId) {
  const data = await api(`/api/images?limit=1&search=${encodeURIComponent(figId)}`);
  const img = data.images[0];
  if (!img) return;
  const path = img.local_path ? img.local_path.replace('/home/michael/projects/caseprep/caseprep/image_bank', '') : '';
  const anatomy = img.anatomy ? JSON.parse(img.anatomy) : [];
  const keywords = img.keywords ? JSON.parse(img.keywords) : [];
  document.getElementById('modal-content').innerHTML = `
    <img src="${path}" alt="${img.fig_id}">
    <div class="detail">
      <h2>${img.fig_id}</h2>
      <div class="field"><span class="field-label">Cluster</span><div class="field-value">${(img.cluster||'').replace(/_/g, ' ')}</div></div>
      ${img.modality ? `<div class="field"><span class="field-label">Modality</span><div class="field-value">${img.modality}</div></div>` : ''}
      ${img.is_neurosurgical !== null ? `<div class="field"><span class="field-label">Neurosurgical</span><div class="field-value">${img.is_neurosurgical ? '✅ Yes' : '❌ No'}</div></div>` : ''}
      ${img.surgical_usefulness ? `<div class="field"><span class="field-label">Surgical Usefulness</span><div class="field-value">${'★'.repeat(img.surgical_usefulness)} ${img.surgical_usefulness}/5</div></div>` : ''}
      ${anatomy.length ? `<div class="field"><span class="field-label">Anatomy</span><div class="field-value">${anatomy.join(', ')}</div></div>` : ''}
      ${img.pathology ? `<div class="field"><span class="field-label">Pathology</span><div class="field-value">${img.pathology}</div></div>` : ''}
      ${img.procedure ? `<div class="field"><span class="field-label">Procedure</span><div class="field-value">${img.procedure}</div></div>` : ''}
      ${img.caption_summary ? `<div class="field"><span class="field-label">Caption</span><div class="field-value">${img.caption_summary}</div></div>` : ''}
      ${keywords.length ? `<div class="field"><span class="field-label">Keywords</span><div class="field-value">${keywords.join(', ')}</div></div>` : ''}
    </div>
  `;
  document.getElementById('modal').classList.add('open');
}

function closeModal() { document.getElementById('modal').classList.remove('open'); }
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

init();
</script>
</body>
</html>"""


@app.route("/")
def index():
    return GALLERY_HTML


if __name__ == "__main__":
    total_clusters = len(list(IMAGES_DIR.iterdir()))
    total_images = sum(len(list(d.iterdir())) for d in IMAGES_DIR.iterdir() if d.is_dir())
    print(f"🚀 Image Bank Gallery — http://localhost:8765")
    print(f"   {total_clusters} clusters · {total_images:,} images · 20,296 labeled")
    app.run(host="0.0.0.0", port=8765, debug=True)
