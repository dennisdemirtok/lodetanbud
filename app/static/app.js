// =========================================================================
// Lodet — frontend (vanilla JS, no build step)
// =========================================================================

const fmtSEK = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 0 });
const fmtNum = new Intl.NumberFormat('sv-SE');

const STORAGE_KEY = 'lodet:history';

// ---------- ROUTING ------------------------------------------------------

const ROUTES = {
  '#/dashboard':           { view: 'dashboard',     crumb: 'Översikt',                handler: renderDashboard },
  '#/upload':              { view: 'upload',        crumb: 'Anbud / nytt',            handler: renderUpload },
  '#/bids/active':         { view: 'bids-active',   crumb: 'Anbud / pågående',        handler: renderActiveBids },
  '#/bids/submitted':      { view: 'bids-submitted',crumb: 'Anbud / inlämnade',       handler: () => {} },
  '#/bids/archive':        { view: 'bids-archive',  crumb: 'Anbud / arkiv',           handler: () => {} },
  '#/docs/mf':             { view: 'docs-mf',       crumb: 'Dokument / MF',           handler: renderDocsMf },
  '#/docs/afb':            { view: 'docs-afb',      crumb: 'Dokument / AF-bilagor',   handler: renderAfbList },
  '#/docs/drawings':       { view: 'docs-drawings', crumb: 'Dokument / ritningar',    handler: () => {} },
  '#/ama/anlaggning':      { view: 'ama',           crumb: 'AMA / Anläggning',        handler: () => renderAma('AMA_Anläggning', 'AMA Anläggning 23') },
  '#/ama/hus':             { view: 'ama',           crumb: 'AMA / Hus',               handler: () => renderAmaPlaceholder('AMA Hus 21', 'Husbyggnadskoder läses in i nästa milstolpe.') },
  '#/ama/el':              { view: 'ama',           crumb: 'AMA / El',                handler: () => renderAmaPlaceholder('AMA El 22', 'AMA El-koder läses in i nästa milstolpe.') },
  '#/ama/af':              { view: 'ama',           crumb: 'AMA / AF',                handler: () => renderAma('AF_AMA', 'AF AMA 21') },
  '#/mallar/anbudssumma':  { view: 'template',      crumb: 'Mallar / AFB.31 Anbudssumma',  handler: () => renderTemplate('anbudssumma') },
  '#/mallar/ue-lista':     { view: 'template',      crumb: 'Mallar / AFB.32 UE-lista',     handler: () => renderTemplate('ue-lista') },
  '#/mallar/sekretess':    { view: 'template',      crumb: 'Mallar / Sekretessbegäran',    handler: () => renderTemplate('sekretess') },
  '#/mallar/missiv':       { view: 'template',      crumb: 'Mallar / Missiv',              handler: () => renderTemplate('missiv') },
  '#/historik':            { view: 'historik',      crumb: 'Historik',                handler: renderHistory },
  '#/inst/foretag':        { view: 'inst',          crumb: 'Inställningar / Företag', handler: () => renderInst('Företagsinfo', 'Lagras per tenant. Företagsnamn, org.nr, kontaktuppgifter, logotyp.') },
  '#/inst/index':          { view: 'inst',          crumb: 'Inställningar / Index',   handler: () => renderInst('Indexserier', 'E84 per litt och KPI för indexjustering av historiska priser.') },
  '#/inst/paslag':         { view: 'inst',          crumb: 'Inställningar / Påslag',  handler: () => renderInst('Påslag och marginaler', 'Standardpåslag per kategori + täckningsbidragsregler.') },
  '#/inst/anvandare':      { view: 'inst',          crumb: 'Inställningar / Användare', handler: () => renderInst('Användare', 'Roller och behörigheter. Multi-user kommer med Supabase-integration.') },
};

function navigate() {
  const hash = location.hash || '#/dashboard';
  const route = ROUTES[hash] || ROUTES['#/dashboard'];

  document.querySelectorAll('.view').forEach((v) => v.hidden = true);
  const viewEl = document.querySelector(`[data-view="${route.view}"]`);
  if (viewEl) viewEl.hidden = false;

  document.getElementById('breadcrumb').textContent = route.crumb;

  document.querySelectorAll('.nav-item, .nav-child').forEach((el) => el.classList.remove('active'));
  const activeNav = document.querySelector(`[data-route="${hash}"]`);
  if (activeNav) {
    activeNav.classList.add('active');
    const group = activeNav.closest('.nav-group');
    if (group) group.classList.add('open');
  }

  document.querySelectorAll('.sidebar.open').forEach((s) => s.classList.remove('open'));
  window.scrollTo({ top: 0 });

  try { route.handler(); } catch (e) { console.error('Route handler error:', e); }
}

window.addEventListener('hashchange', navigate);

// ---------- INIT ---------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  bindSidebar();
  bindUpload();
  bindTemplateForm();
  if (!location.hash) location.hash = '#/dashboard';
  navigate();
});

function bindSidebar() {
  document.querySelectorAll('[data-route]').forEach((el) => {
    el.addEventListener('click', (e) => {
      e.preventDefault();
      location.hash = el.dataset.route;
    });
  });
  document.querySelectorAll('[data-group-toggle]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      btn.closest('.nav-group').classList.toggle('open');
    });
  });
  document.getElementById('hamburger').addEventListener('click', () => {
    document.getElementById('sidebar').classList.toggle('open');
  });
}

// ---------- DASHBOARD ----------------------------------------------------

let dashLoaded = false;
async function renderDashboard() {
  if (dashLoaded) return;
  try {
    const res = await fetch('/api/dashboard');
    const d = await res.json();

    document.getElementById('dashActive').textContent = d.stats.active_bids;
    document.getElementById('dashTotal').textContent = `${fmtSEK.format(d.stats.total_bid_value_sek)} kr`;
    document.getElementById('dashWin').textContent = `${d.stats.win_rate_pct}%`;
    document.getElementById('dashWinRate').textContent = `${d.stats.win_rate_pct}%`;
    document.getElementById('dashAma').textContent = d.stats.ama_codes_in_library;

    const actUl = document.getElementById('dashActivity');
    actUl.innerHTML = d.recent_activity.map((a) => `
      <li>
        <span class="activity-dot" data-type="${a.type}"></span>
        <div class="activity-content">
          <div class="activity-title">${escapeHtml(a.title)}</div>
          <div class="activity-sub">${escapeHtml(a.subtitle)}</div>
        </div>
        <div class="activity-time">${escapeHtml(a.timestamp)}</div>
      </li>
    `).join('');

    const dlUl = document.getElementById('dashDeadlines');
    dlUl.innerHTML = d.upcoming_deadlines.map((dl) => `
      <li>
        <div>
          <div class="deadline-project">${escapeHtml(dl.project)}</div>
          <div class="deadline-customer">${escapeHtml(dl.customer)}</div>
        </div>
        <div class="deadline-due">${escapeHtml(dl.due)}</div>
      </li>
    `).join('');

    dashLoaded = true;
  } catch (e) {
    console.error(e);
  }
}

// ---------- UPLOAD / RESULTS ---------------------------------------------

let lastUploadedFile = null;
let lastWasExample = false;
let lastParsedData = null;

function bindUpload() {
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('fileInput');
  const browseBtn = document.getElementById('browseBtn');
  const exampleBtn = document.getElementById('exampleBtn');
  const downloadBtn = document.getElementById('downloadBtn');

  dropzone.addEventListener('click', (e) => { if (e.target !== browseBtn) fileInput.click(); });
  dropzone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); }
  });
  browseBtn.addEventListener('click', (e) => { e.stopPropagation(); fileInput.click(); });

  ['dragenter', 'dragover'].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add('dragover'); })
  );
  ['dragleave', 'dragend', 'drop'].forEach((ev) =>
    dropzone.addEventListener(ev, () => dropzone.classList.remove('dragover'))
  );

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    const f = e.dataTransfer?.files?.[0];
    if (f) handleFile(f);
  });

  fileInput.addEventListener('change', (e) => {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  });

  exampleBtn.addEventListener('click', loadExample);
  downloadBtn.addEventListener('click', downloadExcel);
}

function renderUpload() { /* state already bound */ }

function showStatus(msg, kind = 'info') {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className = `status ${kind}`;
  el.hidden = false;
}
function clearStatus() {
  const el = document.getElementById('status');
  el.hidden = true;
}

async function handleFile(file) {
  if (!file.name.toLowerCase().endsWith('.csv')) {
    showStatus('Endast .csv stöds i denna version. Konvertera Excel-fil och försök igen.', 'error');
    return;
  }
  lastUploadedFile = file;
  lastWasExample = false;

  showStatus(`Parsar ${file.name} …`, 'loading');
  const fd = new FormData();
  fd.append('file', file);

  try {
    const res = await fetch('/api/parse', { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await safeJson(res);
      throw new Error(err?.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    lastParsedData = data;
    saveToHistory(data);
    renderResults(data);
    clearStatus();
  } catch (e) {
    showStatus(`Kunde inte parsa filen: ${e.message}`, 'error');
    document.getElementById('results').hidden = true;
  }
}

async function loadExample() {
  showStatus('Hämtar Westcon-demo …', 'loading');
  lastUploadedFile = null;
  lastWasExample = true;
  try {
    const res = await fetch('/api/example');
    const data = await res.json();
    lastParsedData = data;
    saveToHistory(data);
    renderResults(data);
    clearStatus();
  } catch (e) {
    showStatus(`Kunde inte hämta demo-data: ${e.message}`, 'error');
  }
}

async function downloadExcel() {
  const btn = document.getElementById('downloadBtn');
  btn.disabled = true;
  const original = btn.textContent;
  btn.textContent = 'Genererar Excel …';

  try {
    let res;
    if (lastWasExample) {
      res = await fetch('/api/example/excel', { method: 'POST' });
    } else if (lastUploadedFile) {
      const fd = new FormData();
      fd.append('file', lastUploadedFile);
      res = await fetch('/api/excel', { method: 'POST', body: fd });
    } else {
      showStatus('Ladda upp en fil eller välj demo först.', 'error');
      return;
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const cd = res.headers.get('Content-Disposition') || '';
    const m = cd.match(/filename="?([^"]+)"?/);
    const filename = m ? m[1] : 'Lodet_Anbud.xlsx';

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    showStatus(`Kunde inte generera Excel: ${e.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
}

function renderResults(payload) {
  const { summary, data } = payload;
  const meta = data.metadata;

  document.getElementById('resultProject').textContent = meta.project_name || 'Okänt projekt';
  const parts = [];
  if (meta.document_number) parts.push(meta.document_number);
  if (meta.date) parts.push(meta.date);
  if (meta.handlaggare) parts.push(`Handläggare: ${meta.handlaggare}`);
  if (meta.uppdragsnummer) parts.push(`Uppdrag: ${meta.uppdragsnummer}`);
  document.getElementById('resultMeta').textContent = parts.join(' · ');

  document.getElementById('statTotal').textContent = meta.total_amount_sek
    ? `${fmtSEK.format(meta.total_amount_sek)} kr` : '—';
  document.getElementById('statLines').textContent = fmtNum.format(summary.line_count);
  document.getElementById('statPriced').textContent = fmtNum.format(summary.priced_lines);
  document.getElementById('statLump').textContent = fmtNum.format(summary.lump_sum_count);
  document.getElementById('statAma').textContent = summary.ama_codes_used.length;

  const tbody = document.querySelector('#linesTable tbody');
  tbody.innerHTML = '';
  let currentSection = null;

  for (const line of data.lines) {
    const sectionLetter = (line.ama_code || '')[0];
    if (sectionLetter && sectionLetter !== currentSection) {
      currentSection = sectionLetter;
      const sr = document.createElement('tr');
      sr.className = 'section-row';
      sr.innerHTML = `<td colspan="6">${escapeHtml(sectionLabel(sectionLetter))}</td>`;
      tbody.appendChild(sr);
    }
    const tr = document.createElement('tr');
    if (line.is_lump_sum) tr.classList.add('lump-row');
    tr.innerHTML = `
      <td class="mono">${escapeHtml(line.ama_code || '—')}</td>
      <td>${escapeHtml(line.description || '')}</td>
      <td class="col-num mono">${escapeHtml(line.unit || '—')}</td>
      <td class="col-num mono">${formatNum(line.quantity)}</td>
      <td class="col-num mono">${formatPrice(line.unit_price)}</td>
      <td class="col-num mono">${formatPrice(line.total_amount)}</td>
    `;
    tbody.appendChild(tr);
  }

  document.getElementById('tableInfo').textContent =
    `${data.lines.length} rader · ${summary.ama_codes_used.length} unika AMA-koder`;

  document.getElementById('results').hidden = false;
  document.getElementById('results').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function sectionLabel(letter) {
  return ({
    B: 'B — Förarbeten, hjälparbeten, saneringsarbeten',
    C: 'C — Mark- och anläggningsarbeten',
    D: 'D — Markförstärkningar och bärande konstruktioner',
    E: 'E — Konstruktionsarbeten',
    S: 'S — Apparater, ledningar m.m. i el- och telesystem',
    Y: 'Y — Märkning, kontroll, dokumentation',
  })[letter] || `${letter} — Övrigt`;
}

// ---------- LOCAL HISTORY ------------------------------------------------

function saveToHistory(payload) {
  try {
    const list = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const entry = {
      id,
      filename: payload.filename,
      project: payload.summary.project,
      document_number: payload.summary.document_number,
      total_amount_sek: payload.summary.total_amount_sek,
      line_count: payload.summary.line_count,
      ama_codes: payload.summary.ama_codes_used,
      saved_at: new Date().toISOString(),
    };
    const filtered = list.filter((e) =>
      !(e.document_number === entry.document_number && e.project === entry.project)
    );
    filtered.unshift(entry);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered.slice(0, 50)));
  } catch (e) { console.warn(e); }
}

function loadHistory() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); }
  catch { return []; }
}

function renderActiveBids() {
  const list = loadHistory();
  const el = document.getElementById('localBidsList');
  if (list.length === 0) {
    el.innerHTML = '<div class="empty-state"><p>Inga utkast än. Ladda upp en CSV via "Nytt anbud".</p></div>';
    return;
  }
  el.innerHTML = list.map((b) => `
    <div class="bid-row">
      <div>
        <div class="bid-name">${escapeHtml(b.project || '—')}</div>
        <div class="bid-meta">${escapeHtml(b.document_number || '')} · ${b.line_count} rader · ${b.ama_codes.length} AMA-koder</div>
      </div>
      <div class="bid-amount">${b.total_amount_sek ? fmtSEK.format(b.total_amount_sek) + ' kr' : '—'}</div>
      <div class="bid-date">${formatRelDate(b.saved_at)}</div>
      <div></div>
    </div>
  `).join('');

  document.getElementById('clearLocalBtn').addEventListener('click', () => {
    if (confirm('Rensa all lokal historik?')) {
      localStorage.removeItem(STORAGE_KEY);
      renderActiveBids();
    }
  }, { once: true });
}

function renderDocsMf() {
  const list = loadHistory();
  const el = document.getElementById('docsMfList');
  if (list.length === 0) {
    el.innerHTML = '<div class="empty-state"><p>Inga MF parsade än.</p></div>';
    return;
  }
  el.innerHTML = list.map((b) => `
    <div class="bid-row">
      <div>
        <div class="bid-name">${escapeHtml(b.project || '—')}</div>
        <div class="bid-meta">${escapeHtml(b.filename || '')}</div>
      </div>
      <div class="bid-amount">${b.total_amount_sek ? fmtSEK.format(b.total_amount_sek) + ' kr' : '—'}</div>
      <div class="bid-date">${formatRelDate(b.saved_at)}</div>
      <div></div>
    </div>
  `).join('');
}

function renderHistory() {
  const list = loadHistory();
  const el = document.getElementById('historyContent');
  if (list.length === 0) {
    el.innerHTML = '<div class="empty-state"><p>Tom historik. Parsa något så dyker det upp här.</p></div>';
    return;
  }
  const allCodes = [...new Set(list.flatMap((b) => b.ama_codes))].sort();
  el.innerHTML = `
    <div style="padding: 18px 20px; border-bottom: 1px solid #F0EBDF;">
      <div style="font-size: 0.85rem; color: var(--muted); margin-bottom: 8px;">AMA-koder som förekommit i din historik:</div>
      <div style="display: flex; flex-wrap: wrap; gap: 6px;">
        ${allCodes.map((c) => `<span style="font-family: var(--font-mono); font-size: 0.82rem; background: var(--ljusgra); padding: 3px 9px; border-radius: 4px;">${escapeHtml(c)}</span>`).join('')}
      </div>
    </div>
    ${list.map((b) => `
      <div class="bid-row">
        <div>
          <div class="bid-name">${escapeHtml(b.project || '—')}</div>
          <div class="bid-meta">${escapeHtml(b.document_number || '')} · ${b.ama_codes.length} koder</div>
        </div>
        <div class="bid-amount">${b.total_amount_sek ? fmtSEK.format(b.total_amount_sek) + ' kr' : '—'}</div>
        <div class="bid-date">${formatRelDate(b.saved_at)}</div>
        <div></div>
      </div>
    `).join('')}
  `;
}

// ---------- AMA-BIBLIOTEK ------------------------------------------------

async function renderAma(system, title) {
  document.getElementById('amaTitle').textContent = title;
  document.getElementById('amaPanelTitle').textContent = 'Sektioner';
  const el = document.getElementById('amaContent');
  el.innerHTML = '<div class="empty-state"><p>Laddar …</p></div>';

  try {
    const res = await fetch(`/api/ama?system=${encodeURIComponent(system)}`);
    const d = await res.json();
    document.getElementById('amaCount').textContent =
      `${d.section_count} sektioner · ${d.code_count} koder`;

    el.innerHTML = d.sections.map((s) => `
      <div class="ama-section">
        <button class="ama-section-head" data-letter="${s.letter}">
          <span class="ama-section-letter">${s.letter}</span>
          <span class="ama-section-title">${escapeHtml(s.label)}</span>
          <span class="ama-section-meta">${escapeHtml(s.index_basis)}</span>
          <span class="nav-chev">›</span>
        </button>
        <div class="ama-section-codes">
          ${s.codes.map((c) => `
            <div class="ama-code-row">
              <span class="ama-code-name" data-level="${c.level}">${escapeHtml(c.code)}</span>
              <span class="ama-code-title">${escapeHtml(c.title)}</span>
            </div>
          `).join('')}
        </div>
      </div>
    `).join('');

    el.querySelectorAll('.ama-section-head').forEach((btn) => {
      btn.addEventListener('click', () => btn.parentElement.classList.toggle('open'));
    });
  } catch (e) {
    el.innerHTML = `<div class="empty-state"><p>Fel: ${escapeHtml(e.message)}</p></div>`;
  }
}

function renderAmaPlaceholder(title, msg) {
  document.getElementById('amaTitle').textContent = title;
  document.getElementById('amaPanelTitle').textContent = 'Sektioner';
  document.getElementById('amaCount').textContent = '—';
  document.getElementById('amaContent').innerHTML =
    `<div class="empty-state"><p>${escapeHtml(msg)}</p><p class="muted">Roadmap dag 15–35 enligt teknisk spec v0.2.</p></div>`;
}

// ---------- AFB-MALLAR ---------------------------------------------------

async function renderAfbList() {
  const el = document.getElementById('afbCardGrid');
  el.innerHTML = '<div class="empty-state"><p>Laddar mallar …</p></div>';
  try {
    const res = await fetch('/api/afb/templates');
    const d = await res.json();
    el.innerHTML = d.templates.map((t) => `
      <a class="afb-card" href="#/mallar/${t.id}">
        <div class="afb-code">${escapeHtml(t.code)}</div>
        <div class="afb-title">${escapeHtml(t.title)}</div>
        <div class="afb-desc">${escapeHtml(t.description)}</div>
      </a>
    `).join('');
  } catch (e) {
    el.innerHTML = `<div class="empty-state"><p>Fel: ${escapeHtml(e.message)}</p></div>`;
  }
}

let currentTemplateId = null;
function renderTemplate(id) {
  currentTemplateId = id;
  const titles = {
    'anbudssumma': { code: 'AFB.31', title: 'Anbudssumma', desc: 'Standardblankett för totalbelopp exkl. moms enligt förfrågningsunderlaget.' },
    'ue-lista':    { code: 'AFB.32', title: 'Underentreprenörer', desc: 'Förteckning över planerade UE per teknikområde.' },
    'sekretess':   { code: '—',      title: 'Sekretessbegäran', desc: 'Standardbrev enligt FHL §1 och OSL 9:3 + 31:16.' },
    'missiv':      { code: '—',      title: 'Missiv', desc: 'Följebrev som listar samtliga bilagor i anbudspaketet.' },
  }[id] || { code: '?', title: 'Okänd mall', desc: '' };

  document.getElementById('tmplEyebrow').textContent = `Mall · ${titles.code}`;
  document.getElementById('tmplTitle').textContent = titles.title;
  document.getElementById('tmplDesc').textContent = titles.desc;
  document.getElementById('tmplPreview').textContent = 'Fyll i fälten och klicka "Generera".';

  document.querySelectorAll('[data-show-for]').forEach((el) => {
    el.style.display = el.dataset.showFor === id ? '' : 'none';
  });
}

function bindTemplateForm() {
  const form = document.getElementById('tmplForm');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!currentTemplateId) return;
    const fd = new FormData(form);
    try {
      const res = await fetch(`/api/afb/${currentTemplateId}`, { method: 'POST', body: fd });
      const d = await res.json();
      document.getElementById('tmplPreview').textContent = d.text;
    } catch (e) {
      document.getElementById('tmplPreview').textContent = `Fel: ${e.message}`;
    }
  });

  document.getElementById('copyTmplBtn').addEventListener('click', async () => {
    const text = document.getElementById('tmplPreview').textContent;
    try {
      await navigator.clipboard.writeText(text);
      const btn = document.getElementById('copyTmplBtn');
      const original = btn.textContent;
      btn.textContent = 'Kopierat ✓';
      setTimeout(() => { btn.textContent = original; }, 1500);
    } catch (e) { console.warn(e); }
  });
}

// ---------- INSTÄLLNINGAR ------------------------------------------------

function renderInst(title, desc) {
  document.getElementById('instEyebrow').textContent = 'Inställningar';
  document.getElementById('instTitle').textContent = title;
  document.getElementById('instDesc').textContent = desc;
}

// ---------- HELPERS ------------------------------------------------------

function formatNum(v) { return v == null ? '—' : fmtNum.format(v); }
function formatPrice(v) { return v == null ? '—' : `${fmtSEK.format(v)} kr`; }

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
}

function formatRelDate(iso) {
  try {
    const d = new Date(iso);
    const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60) return 'just nu';
    if (diff < 3600) return `${Math.round(diff / 60)} min sedan`;
    if (diff < 86400) return `${Math.round(diff / 3600)} tim sedan`;
    return d.toLocaleDateString('sv-SE');
  } catch { return ''; }
}

async function safeJson(res) {
  try { return await res.json(); } catch { return null; }
}
