// =========================================================================
// Lodet — frontend (vanilla JS, no build step)
// =========================================================================

const fmtSEK = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 0 });
const fmtNum = new Intl.NumberFormat('sv-SE');

const STORAGE_KEY = 'lodet:history';
const CHATS_KEY = 'lodet:chats';

// ---------- ROUTING ------------------------------------------------------

const ROUTES = {
  '#/start':              { tab: 'agent',       view: 'start',         crumb: 'Start',                   handler: renderStart },
  '#/agent/ue':           { tab: 'agent',       view: 'agent-ue',      crumb: 'Agent / UE-mejl',         handler: renderUePage },
  '#/kunskapsbas':        { tab: 'kunskapsbas', view: 'kunskapsbas',   crumb: 'Kunskapsbas',             handler: renderKunskapsbas },
  '#/dashboard':          { tab: 'anbud',       view: 'dashboard',     crumb: 'Översikt',                handler: renderDashboard },
  '#/upload':             { tab: 'anbud',       view: 'upload',        crumb: 'Anbud / nytt',            handler: renderUpload },
  '#/bids/active':        { tab: 'anbud',       view: 'bids-active',   crumb: 'Anbud / pågående',        handler: renderActiveBids },
  '#/bids/submitted':     { tab: 'anbud',       view: 'bids-submitted',crumb: 'Anbud / inlämnade',       handler: () => {} },
  '#/bids/archive':       { tab: 'anbud',       view: 'bids-archive',  crumb: 'Anbud / arkiv',           handler: () => {} },
  '#/docs/mf':            { tab: 'anbud',       view: 'docs-mf',       crumb: 'Dokument / MF',           handler: renderDocsMf },
  '#/docs/afb':           { tab: 'bibliotek',   view: 'docs-afb',      crumb: 'Mallar',                  handler: renderAfbList },
  '#/docs/drawings':      { tab: 'anbud',       view: 'docs-drawings', crumb: 'Dokument / ritningar',    handler: () => {} },
  '#/ama/anlaggning':     { tab: 'bibliotek',   view: 'ama',           crumb: 'AMA / Anläggning',        handler: () => renderAma('AMA_Anläggning', 'AMA Anläggning 23') },
  '#/ama/hus':            { tab: 'bibliotek',   view: 'ama',           crumb: 'AMA / Hus',               handler: () => renderAmaPlaceholder('AMA Hus 21', 'Husbyggnadskoder läses in i nästa milstolpe.') },
  '#/ama/el':             { tab: 'bibliotek',   view: 'ama',           crumb: 'AMA / El',                handler: () => renderAmaPlaceholder('AMA El 22', 'AMA El-koder läses in i nästa milstolpe.') },
  '#/ama/af':             { tab: 'bibliotek',   view: 'ama',           crumb: 'AMA / AF',                handler: () => renderAma('AF_AMA', 'AF AMA 21') },
  '#/mallar/anbudssumma': { tab: 'bibliotek',   view: 'template',      crumb: 'Mallar / AFB.31',         handler: () => renderTemplate('anbudssumma') },
  '#/mallar/ue-lista':    { tab: 'bibliotek',   view: 'template',      crumb: 'Mallar / AFB.32',         handler: () => renderTemplate('ue-lista') },
  '#/mallar/sekretess':   { tab: 'bibliotek',   view: 'template',      crumb: 'Mallar / Sekretess',      handler: () => renderTemplate('sekretess') },
  '#/mallar/missiv':      { tab: 'bibliotek',   view: 'template',      crumb: 'Mallar / Missiv',         handler: () => renderTemplate('missiv') },
  '#/historik':           { tab: 'anbud',       view: 'historik',      crumb: 'Historik',                handler: renderHistory },
  '#/inst/foretag':       { tab: 'inst',        view: 'inst',          crumb: 'Inst / Företag',          handler: () => renderInst('Företagsinfo', 'Lagras per tenant. Företagsnamn, org.nr, kontaktuppgifter, logotyp.') },
  '#/inst/index':         { tab: 'inst',        view: 'inst',          crumb: 'Inst / Index',            handler: () => renderInst('Indexserier', 'E84 per litt och KPI för indexjustering av historiska priser.') },
  '#/inst/paslag':        { tab: 'inst',        view: 'inst',          crumb: 'Inst / Påslag',           handler: () => renderInst('Påslag och marginaler', 'Standardpåslag per kategori + täckningsbidragsregler.') },
  '#/inst/anvandare':     { tab: 'inst',        view: 'inst',          crumb: 'Inst / Användare',        handler: () => renderInst('Användare', 'Roller och behörigheter. Multi-user kommer med Supabase-integration.') },
};

function navigate() {
  const hash = location.hash || '#/start';
  const route = ROUTES[hash] || ROUTES['#/start'];

  // Visa rätt view
  document.querySelectorAll('.view').forEach((v) => v.hidden = true);
  const viewEl = document.querySelector(`[data-view="${route.view}"]`);
  if (viewEl) viewEl.hidden = false;

  // Aktivera rätt topbar-tab
  document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
  const activeTab = document.querySelector(`.tab[data-tab="${route.tab}"]`);
  if (activeTab) activeTab.classList.add('active');

  // Visa rätt sidebar-section
  document.querySelectorAll('.sidebar-section').forEach((s) => s.hidden = true);
  const activeSidebar = document.querySelector(`.sidebar-section[data-sidebar="${route.tab}"]`);
  if (activeSidebar) activeSidebar.hidden = false;

  // Aktivera rätt sidebar-länk inom sidebar-sectionen
  document.querySelectorAll('.sidebar-link').forEach((el) => el.classList.remove('active'));
  const activeLink = document.querySelector(`.sidebar-link[data-route="${hash}"]`);
  if (activeLink) activeLink.classList.add('active');

  // Stäng mobil-sidebar
  document.querySelectorAll('.sidebar.open').forEach((s) => s.classList.remove('open'));
  window.scrollTo({ top: 0 });

  try { route.handler(); } catch (e) { console.error('Route handler error:', e); }
}

window.addEventListener('hashchange', navigate);

// ---------- INIT ---------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  bindShell();
  bindUpload();
  bindTemplateForm();
  bindStart();
  bindUeForm();
  bindChat();
  bindDraftModal();
  if (!location.hash) location.hash = '#/start';
  navigate();
  renderRecentChats();
});

function bindShell() {
  // Alla data-route-element navigerar
  document.body.addEventListener('click', (e) => {
    const el = e.target.closest('[data-route]');
    if (!el) return;
    e.preventDefault();
    location.hash = el.dataset.route;
  });

  // Hamburger för mobil-sidebar
  const ham = document.getElementById('hamburger');
  if (ham) {
    ham.addEventListener('click', (e) => {
      e.stopPropagation();
      document.getElementById('sidebar').classList.toggle('open');
    });
  }

  // "Ny chat" — rensa historik, växla till empty-state
  const newBtn = document.getElementById('newChatBtn');
  if (newBtn) {
    newBtn.addEventListener('click', () => {
      currentChatId = null;
      chatHistory.length = 0;
      lastAnalysis = null;
      switchAgentMode('empty');
      location.hash = '#/start';
      renderRecentChats();
    });
  }
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

// ---------- START / AGENT ------------------------------------------------

let lastAnalysis = null;

function bindStart() {
  const dz = document.getElementById('multiDropzone');
  const input = document.getElementById('multiFileInput');
  const folderInput = document.getElementById('folderFileInput');
  const browse = document.getElementById('multiBrowseBtn');
  const folderBrowse = document.getElementById('folderBrowseBtn');
  const demo = document.getElementById('demoPackageBtn');
  const heroAttachInput = document.getElementById('heroFileInput');

  dz.addEventListener('click', (e) => {
    if (e.target === browse || e.target === folderBrowse || e.target === demo) return;
    input.click();
  });
  dz.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); }
  });
  browse.addEventListener('click', (e) => { e.stopPropagation(); input.click(); });
  folderBrowse.addEventListener('click', (e) => { e.stopPropagation(); folderInput.click(); });
  demo.addEventListener('click', (e) => { e.stopPropagation(); loadDemoPackage(); });

  ['dragenter', 'dragover'].forEach((ev) =>
    dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('dragover'); })
  );
  ['dragleave', 'dragend', 'drop'].forEach((ev) =>
    dz.addEventListener(ev, () => dz.classList.remove('dragover'))
  );
  dz.addEventListener('drop', async (e) => {
    e.preventDefault();
    const files = await collectDroppedFiles(e.dataTransfer);
    if (files.length) handlePackageFiles(files);
  });
  input.addEventListener('change', (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length) handlePackageFiles(files);
    e.target.value = '';
  });
  folderInput.addEventListener('change', (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length) handlePackageFiles(files);
    e.target.value = '';
  });

  // Hero-input attach
  if (heroAttachInput) {
    heroAttachInput.addEventListener('change', (e) => {
      const files = Array.from(e.target.files || []);
      if (files.length) handlePackageFiles(files);
      e.target.value = '';
    });
  }
}

function renderStart() {
  // Om vi har chat-historik → chat-läge, annars empty
  if (chatHistory.length > 0) {
    switchAgentMode('chat');
  } else {
    switchAgentMode('empty');
  }
}

// ---------- DRAG-AND-DROP MAPP-STÖD ------------------------------------

async function collectDroppedFiles(dataTransfer) {
  if (!dataTransfer) return [];

  // Föredra items + webkitGetAsEntry (stöder mappar)
  const items = dataTransfer.items;
  if (items && items.length && typeof items[0].webkitGetAsEntry === 'function') {
    const entries = [];
    for (const it of items) {
      const entry = it.webkitGetAsEntry?.();
      if (entry) entries.push(entry);
    }
    if (entries.length) {
      const files = [];
      for (const e of entries) {
        files.push(...await _readEntry(e));
      }
      return files;
    }
  }

  // Fallback: bara top-level filer
  return Array.from(dataTransfer.files || []);
}

async function _readEntry(entry, prefix = '') {
  if (!entry) return [];
  if (entry.isFile) {
    const file = await new Promise((res, rej) => entry.file(res, rej));
    // Berika filen med relative path så backend-zip-handler kan se mappstruktur
    try {
      Object.defineProperty(file, 'webkitRelativePath', {
        value: prefix + file.name,
        configurable: true,
      });
    } catch {}
    return [file];
  }
  if (entry.isDirectory) {
    const reader = entry.createReader();
    const all = await _readAllDirEntries(reader);
    const out = [];
    for (const child of all) {
      out.push(...await _readEntry(child, prefix + entry.name + '/'));
    }
    return out;
  }
  return [];
}

function _readAllDirEntries(reader) {
  return new Promise((resolve, reject) => {
    const result = [];
    const next = () => {
      reader.readEntries((entries) => {
        if (!entries.length) {
          resolve(result);
        } else {
          result.push(...entries);
          next();
        }
      }, reject);
    };
    next();
  });
}

function switchAgentMode(mode) {
  const empty = document.getElementById('agentEmpty');
  const chat = document.getElementById('agentChat');
  if (!empty || !chat) return;
  if (mode === 'chat') {
    empty.hidden = true;
    chat.hidden = false;
    setTimeout(() => {
      const inp = document.getElementById('chatInputBottom');
      if (inp) inp.focus();
    }, 50);
  } else {
    empty.hidden = false;
    chat.hidden = true;
    document.getElementById('chatMessages').innerHTML = '';
    document.getElementById('agentPanel').hidden = true;
    document.getElementById('filesPanel').hidden = true;
    document.getElementById('agentStatus').hidden = true;
    const dp = document.getElementById('draftPanel');
    if (dp) dp.hidden = true;
    const banner = document.getElementById('caseCreatedBanner');
    if (banner) banner.hidden = true;
    const mfPanel = document.getElementById('mfEditorPanel');
    if (mfPanel) mfPanel.hidden = true;
  }
}

async function handlePackageFiles(files) {
  // Växla till chat-läge så användaren ser fortskridandet
  switchAgentMode('chat');

  const status = document.getElementById('agentStatus');
  status.hidden = false;
  status.className = 'status loading';
  const zipCount = files.filter((f) => f.name.toLowerCase().endsWith('.zip')).length;
  const desc = zipCount > 0
    ? `${files.length} fil${files.length === 1 ? '' : 'er'} (${zipCount} ZIP)`
    : `${files.length} fil${files.length === 1 ? '' : 'er'}`;
  status.textContent = `Skickar ${desc} till agenten — extraherar lärdomar med Claude …`;

  const fd = new FormData();
  for (const f of files) fd.append('files', f);

  try {
    const res = await fetch('/api/package/analyze', { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await safeJson(res);
      throw new Error(err?.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();

    if (data.multi) {
      renderMultiAgentResult(data);
    } else {
      lastAnalysis = data.analysis;
      renderAgentResult(data.analysis, data.saved_case);
      if (data.parsed_mf) saveMfToHistory(data.parsed_mf);
    }
    status.hidden = true;
  } catch (e) {
    status.className = 'status error';
    status.textContent = `Fel: ${e.message}`;
  }
}

function renderMultiAgentResult(data) {
  const filesPanel = document.getElementById('filesPanel');
  const chipsEl = document.getElementById('fileChips');
  const countEl = document.getElementById('filesPanelCount');

  countEl.textContent = `${data.case_count} cases analyserade och sparade`;

  let allFiles = [];
  for (const r of data.results) {
    allFiles = allFiles.concat(r.analysis.files || []);
  }
  chipsEl.innerHTML = allFiles.map((f) => `
    <span class="file-chip">
      <span class="file-chip-type" data-type="${escapeHtml(f.type)}">${escapeHtml(typeShort(f.type))}</span>
      <span class="file-chip-name" title="${escapeHtml(f.filename)}">${escapeHtml(f.filename)}</span>
      <span class="file-chip-status">✓</span>
    </span>
  `).join('');
  filesPanel.hidden = false;

  const agentPanel = document.getElementById('agentPanel');
  const totalLessons = data.results.reduce((sum, r) => sum + (r.saved_case?.lessons?.length || 0), 0);
  const narrative = `Jag har analyserat **${data.case_count} separata anbudspaket** från din uppladdning och sparat dem i kunskapsbasen. Totalt **${totalLessons} lärdomar** extraherade — agenten kommer nu plocka relevanta delar automatiskt när du chattar.`;
  document.getElementById('agentNarrative').innerHTML = renderMarkdownLight(narrative);

  const recsEl = document.getElementById('agentRecs');
  recsEl.innerHTML = data.results.map((r, idx) => {
    const project = r.analysis.summary.project_name || `Paket ${idx + 1}`;
    const total = r.analysis.summary.total_amount_sek
      ? `${new Intl.NumberFormat('sv-SE').format(r.analysis.summary.total_amount_sek)} kr`
      : '—';
    const lessonCount = r.saved_case?.lessons?.length || 0;
    return `
      <div class="agent-rec" data-priority="${idx + 1}">
        <div class="agent-rec-priority">${idx + 1}</div>
        <div class="agent-rec-body">
          <p class="agent-rec-title">${escapeHtml(project)}</p>
          <p class="agent-rec-text">${r.analysis.summary.file_count} filer · ${total} · ${lessonCount} lärdomar sparade</p>
          ${r.saved_case ? `<button class="agent-rec-action" data-route="#/kunskapsbas">Visa i kunskapsbas →</button>` : ''}
        </div>
      </div>
    `;
  }).join('');

  // Sätt det första som lastAnalysis så chat-context fungerar
  lastAnalysis = data.results[0]?.analysis || null;

  agentPanel.hidden = false;

  // Anbudsutkast + MF-editor — fokuserar på första casen i multi-resultatet
  const firstResult = data.results[0];
  const firstCaseId = firstResult?.saved_case?.id;
  if (firstCaseId) {
    showCaseBanner(firstResult.saved_case, firstResult.analysis);
    loadDraftPanel(firstCaseId);
    if (firstResult.analysis?.summary?.has_mf) {
      loadMfEditor(firstCaseId);
    } else {
      document.getElementById('mfEditorPanel').hidden = true;
    }
  } else {
    document.getElementById('caseCreatedBanner').hidden = true;
    document.getElementById('draftPanel').hidden = true;
    document.getElementById('mfEditorPanel').hidden = true;
    agentPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

async function loadDemoPackage() {
  switchAgentMode('chat');

  const status = document.getElementById('agentStatus');
  status.hidden = false;
  status.className = 'status loading';
  status.textContent = 'Hämtar Westcon-demo …';

  try {
    const csvRes = await fetch('/api/example');
    const ex = await csvRes.json();
    const csv = await fetch(`/static/demo_input.csv`).catch(() => null);
    if (csv && csv.ok) {
      const blob = await csv.blob();
      const file = new File([blob], 'demo_input.csv', { type: 'text/csv' });
      handlePackageFiles([file]);
      return;
    }
    // Fallback: visa exempel-data direkt utan paketanalys
    lastAnalysis = {
      summary: { file_count: 1, type_breakdown: { mf: 1 }, has_mf: true, has_af: false, has_tb: false, has_kontrakt: false, ritning_count: 0, disciplines: [], project_ids: [], project_name: ex.summary.project, customer: null, bid_due_at: null, total_size_kb: 16 },
      narrative: 'Endast mängdförteckning hittad. Generera Excel-mall eller starta UE-mejl.',
      files: [{ filename: ex.filename, type: 'mf', label: 'Mängdförteckning', confidence: 1.0, size_kb: 16 }],
      recommendations: [
        { id: 'parsed', priority: 1, title: `MF parsad: ${ex.summary.project}`, body: `${ex.summary.line_count} rader · totalbelopp ${ex.summary.total_amount_sek ? new Intl.NumberFormat('sv-SE').format(ex.summary.total_amount_sek) + ' kr' : '—'}`, action_label: 'Hämta Excel-mall', action_route: '#/upload' },
        { id: 'ue', priority: 2, title: 'Begär offert från underentreprenörer', body: 'Baserat på AMA-koderna föreslås mejl till spont/pålning, asfaltering, el och linjemålning.', action_label: 'Skapa UE-mejl', action_route: '#/agent/ue' },
      ],
      ue_suggestions: ['Spont och pålning', 'Demontering', 'Elinstallation', 'Belysningsinstallation', 'Märkning och skyltning'],
    };
    saveMfToHistory(ex.data);
    renderAgentResult(lastAnalysis);
    status.hidden = true;
  } catch (e) {
    status.className = 'status error';
    status.textContent = `Fel: ${e.message}`;
  }
}

function renderAgentResult(analysis, savedCase) {
  // File chips
  const filesPanel = document.getElementById('filesPanel');
  const chipsEl = document.getElementById('fileChips');
  const countEl = document.getElementById('filesPanelCount');

  countEl.textContent = `${analysis.summary.file_count} filer · ${analysis.summary.total_size_kb} kB`;
  chipsEl.innerHTML = analysis.files.map((f) => `
    <span class="file-chip">
      <span class="file-chip-type" data-type="${escapeHtml(f.type)}">${escapeHtml(typeShort(f.type))}</span>
      <span class="file-chip-name" title="${escapeHtml(f.filename)}">${escapeHtml(f.filename)}</span>
      <span class="file-chip-status">✓</span>
    </span>
  `).join('');
  filesPanel.hidden = false;

  // Agent panel
  const agentPanel = document.getElementById('agentPanel');
  document.getElementById('agentNarrative').innerHTML = renderMarkdownLight(analysis.narrative);

  const recsEl = document.getElementById('agentRecs');
  recsEl.innerHTML = analysis.recommendations.map((r) => `
    <div class="agent-rec" data-priority="${r.priority}">
      <div class="agent-rec-priority">${r.priority}</div>
      <div class="agent-rec-body">
        <p class="agent-rec-title">${escapeHtml(r.title)}</p>
        <p class="agent-rec-text">${escapeHtml(r.body)}</p>
        ${r.action_route ? `<button class="agent-rec-action" data-route="${escapeHtml(r.action_route)}">${escapeHtml(r.action_label || 'Öppna')} →</button>` : ''}
      </div>
    </div>
  `).join('');

  // Lärdomar — visa kort om paketet sparats till arkivet
  if (savedCase && savedCase.lessons && savedCase.lessons.length > 0) {
    const lessonsHtml = `
      <div class="agent-rec" data-priority="1" style="background: #FBF1D8; border-color: var(--ockra);">
        <div class="agent-rec-priority" style="background: var(--ockra); color: var(--lodbla);">✦</div>
        <div class="agent-rec-body">
          <p class="agent-rec-title">${savedCase.lessons.length} lärdomar sparade till kunskapsbasen</p>
          <p class="agent-rec-text">Agenten kommer nu använda dessa när du chattar om liknande projekt.</p>
          <button class="agent-rec-action" data-route="#/kunskapsbas">Visa kunskapsbas →</button>
        </div>
      </div>
    `;
    recsEl.insertAdjacentHTML('afterbegin', lessonsHtml);
  }

  agentPanel.hidden = false;

  if (savedCase && savedCase.id) {
    showCaseBanner(savedCase, analysis);
    loadDraftPanel(savedCase.id);
    if (analysis.summary?.has_mf) {
      loadMfEditor(savedCase.id);
    } else {
      document.getElementById('mfEditorPanel').hidden = true;
    }
  } else {
    document.getElementById('caseCreatedBanner').hidden = true;
    document.getElementById('draftPanel').hidden = true;
    document.getElementById('mfEditorPanel').hidden = true;
    agentPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

// ---------- ANBUDSUTKAST (drafts per case) ------------------------------

let currentDraftCaseId = null;
let currentDraftDocId = null;
let currentDraftMeta = null;

async function loadDraftPanel(caseId) {
  const panel = document.getElementById('draftPanel');
  const list = document.getElementById('draftList');
  const meta = document.getElementById('draftPanelMeta');

  if (!caseId) {
    panel.hidden = true;
    return;
  }

  currentDraftCaseId = caseId;
  list.innerHTML = '<div class="empty-state"><p>Laddar krav…</p></div>';
  panel.hidden = false;

  try {
    const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}/drafts`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();
    const docs = d.required_docs || [];
    const done = docs.filter((x) => x.status !== 'pending').length;
    meta.textContent = `${done} / ${docs.length} klara · ${escapeHtml(d.project_name || '—')}`;

    if (docs.length === 0) {
      list.innerHTML = '<div class="empty-state"><p>Inga krav extraherade. Återgenerera analys eller redigera manuellt.</p></div>';
      return;
    }

    list.innerHTML = docs.map((doc) => renderDraftItem(doc, caseId, d.has_mf)).join('');
    bindDraftActions(caseId);
    // Scrolla till panelen så användaren ser den direkt efter upload
    setTimeout(() => panel.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
  } catch (e) {
    list.innerHTML = `<div class="empty-state"><p>Fel: ${escapeHtml(e.message)}</p></div>`;
  }
}

function renderDraftItem(doc, caseId, hasMf) {
  const isMf = doc.is_mf;
  const code = doc.code || '';
  const requiredLabel = doc.required ? 'Obligatoriskt' : 'Valfritt';
  const statusLabel = doc.status === 'edited' ? 'Redigerat' : (doc.status === 'generated' ? 'Genererat' : 'Ej skapat');
  const editedTime = doc.edited_at ? formatRelDate(doc.edited_at) : (doc.generated_at ? formatRelDate(doc.generated_at) : '');

  let actions = '';
  if (isMf) {
    if (hasMf) {
      actions = `<button class="draft-action primary" data-action="mf-excel" data-doc-id="${escapeHtml(doc.id)}">Hämta Excel</button>`;
    } else {
      actions = `<button class="draft-action" disabled>Ingen MF i paketet</button>`;
    }
  } else {
    actions = `
      <button class="draft-action" data-action="edit" data-doc-id="${escapeHtml(doc.id)}">${doc.status === 'pending' ? 'Generera' : 'Redigera'}</button>
      ${doc.status !== 'pending' ? `<button class="draft-action primary" data-action="pdf" data-doc-id="${escapeHtml(doc.id)}">Hämta PDF</button>` : ''}
    `;
  }

  return `
    <div class="draft-item" data-doc-id="${escapeHtml(doc.id)}">
      <div>
        <div class="draft-item-head">
          ${code ? `<span class="draft-item-code">${escapeHtml(code)}</span>` : ''}
          <span class="draft-item-title">${escapeHtml(doc.title)}</span>
          <span class="draft-item-required" data-required="${doc.required}">${requiredLabel}</span>
          <span class="draft-item-status" data-status="${doc.status}">${statusLabel}</span>
        </div>
        <p class="draft-item-desc">${escapeHtml(doc.description || '')}</p>
        ${editedTime ? `<div class="draft-item-meta">${doc.status === 'edited' ? 'Redigerat' : 'Genererat'} ${escapeHtml(editedTime)}</div>` : ''}
      </div>
      <div class="draft-item-actions">${actions}</div>
    </div>
  `;
}

function bindDraftActions(caseId) {
  document.querySelectorAll('#draftList [data-action]').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      const action = btn.dataset.action;
      const docId = btn.dataset.docId;
      if (action === 'edit') {
        await openDraftModal(caseId, docId);
      } else if (action === 'pdf') {
        downloadDraftPdf(caseId, docId);
      } else if (action === 'mf-excel') {
        downloadCaseMfExcel(caseId);
      }
    });
  });
}

async function openDraftModal(caseId, docId) {
  const modal = document.getElementById('draftModal');
  const titleEl = document.getElementById('draftModalTitle');
  const codeEl = document.getElementById('draftModalCode');
  const textarea = document.getElementById('draftModalText');
  const status = document.getElementById('draftModalStatus');

  currentDraftCaseId = caseId;
  currentDraftDocId = docId;
  currentDraftMeta = null;

  // Hitta doc-meta från listan
  const item = document.querySelector(`#draftList [data-doc-id="${docId}"]`);
  const titleText = item?.querySelector('.draft-item-title')?.textContent || docId;
  const codeText = item?.querySelector('.draft-item-code')?.textContent || '';
  titleEl.textContent = titleText;
  codeEl.textContent = codeText || 'Mall';
  textarea.value = '';
  status.textContent = 'Hämtar utkast…';

  modal.hidden = false;
  document.body.style.overflow = 'hidden';

  try {
    // Fråga backend efter befintligt utkast eller generera
    const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}/draft/${encodeURIComponent(docId)}`, {
      method: 'POST',
    });
    if (!res.ok) {
      const err = await safeJson(res);
      throw new Error(err?.detail || `HTTP ${res.status}`);
    }
    const d = await res.json();
    textarea.value = d.text || '';
    status.textContent = d.status === 'generated' ? 'Utkast genererat' : '';
    setTimeout(() => textarea.focus(), 50);
  } catch (e) {
    status.textContent = `Fel: ${e.message}`;
    status.classList.add('error');
  }
}

function closeDraftModal() {
  const modal = document.getElementById('draftModal');
  modal.hidden = true;
  document.body.style.overflow = '';
  currentDraftDocId = null;
}

async function saveDraftFromModal() {
  if (!currentDraftCaseId || !currentDraftDocId) return;
  const textarea = document.getElementById('draftModalText');
  const status = document.getElementById('draftModalStatus');
  const text = textarea.value;

  status.textContent = 'Sparar…';
  status.classList.remove('error');

  try {
    const res = await fetch(`/api/cases/${encodeURIComponent(currentDraftCaseId)}/draft/${encodeURIComponent(currentDraftDocId)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) {
      const err = await safeJson(res);
      throw new Error(err?.detail || `HTTP ${res.status}`);
    }
    status.textContent = 'Sparat ✓';
    // Uppdatera listan
    loadDraftPanel(currentDraftCaseId);
    setTimeout(() => closeDraftModal(), 600);
  } catch (e) {
    status.textContent = `Fel: ${e.message}`;
    status.classList.add('error');
  }
}

async function regenerateDraftFromModal() {
  if (!currentDraftCaseId || !currentDraftDocId) return;
  const textarea = document.getElementById('draftModalText');
  const status = document.getElementById('draftModalStatus');
  status.textContent = 'Genererar om…';
  status.classList.remove('error');

  try {
    const res = await fetch(`/api/cases/${encodeURIComponent(currentDraftCaseId)}/draft/${encodeURIComponent(currentDraftDocId)}`, {
      method: 'POST',
    });
    if (!res.ok) {
      const err = await safeJson(res);
      throw new Error(err?.detail || `HTTP ${res.status}`);
    }
    const d = await res.json();
    textarea.value = d.text || '';
    status.textContent = 'Genererat på nytt';
  } catch (e) {
    status.textContent = `Fel: ${e.message}`;
    status.classList.add('error');
  }
}

function downloadDraftPdf(caseId, docId) {
  const url = `/api/cases/${encodeURIComponent(caseId)}/draft/${encodeURIComponent(docId)}/pdf`;
  const a = document.createElement('a');
  a.href = url;
  a.download = '';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function downloadCaseMfExcel(caseId) {
  const url = `/api/cases/${encodeURIComponent(caseId)}/mf/excel`;
  const a = document.createElement('a');
  a.href = url;
  a.download = '';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

// ---------- ANBUD-BANNER ------------------------------------------------

function showCaseBanner(savedCase, analysis) {
  const banner = document.getElementById('caseCreatedBanner');
  if (!banner) return;
  const titleEl = document.getElementById('caseBannerTitle');
  const metaEl = document.getElementById('caseBannerMeta');
  const idEl = document.getElementById('caseBannerId');

  const project = analysis?.summary?.project_name || savedCase?.project_name || 'Okänt projekt';
  const fileCount = analysis?.summary?.file_count || (analysis?.files || []).length;
  const lessonCount = (savedCase?.lessons || []).length;
  const reqCount = (savedCase?.required_docs || []).length;

  titleEl.textContent = project;
  const parts = [];
  if (fileCount) parts.push(`${fileCount} fil${fileCount === 1 ? '' : 'er'}`);
  if (reqCount) parts.push(`${reqCount} krav i anbudet`);
  if (lessonCount) parts.push(`${lessonCount} lärdomar i kunskapsbasen`);
  metaEl.textContent = parts.join(' · ') || 'Sparat';

  if (savedCase?.id) {
    idEl.textContent = savedCase.id;
    idEl.title = savedCase.id;
  }

  banner.hidden = false;
}

// ---------- MF-EDITOR (redigerbar mängdförteckning) --------------------

let mfEditorState = {
  caseId: null,
  parsedMf: null,
  originalMf: null,
  dirty: false,
};

async function loadMfEditor(caseId) {
  const panel = document.getElementById('mfEditorPanel');
  if (!panel) return;
  const tbody = document.querySelector('#mfEditorTable tbody');
  const meta = document.getElementById('mfEditorMeta');

  panel.hidden = false;
  tbody.innerHTML = '<tr><td colspan="6" class="mf-row-empty">Laddar mängdförteckning…</td></tr>';

  try {
    const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}/mf`);
    if (!res.ok) {
      if (res.status === 404) {
        panel.hidden = true;
        return;
      }
      throw new Error(`HTTP ${res.status}`);
    }
    const parsedMf = await res.json();
    mfEditorState = {
      caseId,
      parsedMf,
      originalMf: JSON.parse(JSON.stringify(parsedMf)),
      dirty: false,
    };
    renderMfEditorRows();
    bindMfEditorActions();
    updateMfTotals();
    updateMfDirtyState();

    const lineCount = (parsedMf.lines || []).length;
    const priced = (parsedMf.lines || []).filter((l) => l.unit_price != null).length;
    meta.textContent = `${lineCount} rader · ${priced} prissatta`;
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="6" class="mf-row-empty">Fel: ${escapeHtml(e.message)}</td></tr>`;
  }
}

function renderMfEditorRows() {
  const tbody = document.querySelector('#mfEditorTable tbody');
  if (!tbody || !mfEditorState.parsedMf) return;

  const lines = mfEditorState.parsedMf.lines || [];
  const html = [];
  let currentSection = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const sectionLetter = (line.ama_code || '')[0];
    if (sectionLetter && sectionLetter !== currentSection) {
      currentSection = sectionLetter;
      html.push(`
        <tr class="section-row" data-section="${escapeHtml(sectionLetter)}">
          <td colspan="6">${escapeHtml(sectionLabel(sectionLetter))}<span class="section-total" data-section-total="${escapeHtml(sectionLetter)}">—</span></td>
        </tr>
      `);
    }
    const isLump = !!line.is_lump_sum;
    const qty = line.quantity == null ? '' : line.quantity;
    const price = line.unit_price == null ? '' : line.unit_price;
    const amount = line.total_amount == null ? null : line.total_amount;
    html.push(`
      <tr class="mf-row${isLump ? ' lump-row' : ''}" data-line-index="${i}">
        <td class="mono">${escapeHtml(line.ama_code || '—')}</td>
        <td>${escapeHtml(line.description || '')}</td>
        <td class="col-num mono">${escapeHtml(line.unit || '—')}</td>
        <td class="col-num mono">${formatNum(qty === '' ? null : qty)}</td>
        <td class="col-num">
          ${isLump
            ? `<span class="mono">—</span>`
            : `<input type="number" class="mf-price-input" step="0.01" min="0" data-line-index="${i}" value="${price === '' ? '' : price}" />`}
        </td>
        <td class="col-num"><span class="mf-amount" data-amount-for="${i}">${amount == null ? '—' : `${fmtSEK.format(amount)} kr`}</span></td>
      </tr>
    `);
  }

  tbody.innerHTML = html.join('') || '<tr><td colspan="6" class="mf-row-empty">Inga rader</td></tr>';

  tbody.querySelectorAll('.mf-price-input').forEach((inp) => {
    inp.addEventListener('input', onMfPriceChange);
    inp.addEventListener('focus', () => inp.select());
  });
}

function onMfPriceChange(e) {
  const inp = e.target;
  const idx = parseInt(inp.dataset.lineIndex, 10);
  if (Number.isNaN(idx)) return;
  const line = (mfEditorState.parsedMf?.lines || [])[idx];
  if (!line) return;

  const raw = inp.value.trim();
  const newPrice = raw === '' ? null : Number(raw);
  if (raw !== '' && Number.isNaN(newPrice)) return;

  line.unit_price = newPrice;

  // Räkna om belopp
  let newAmount = null;
  if (line.quantity != null && newPrice != null) {
    newAmount = round2(Number(line.quantity) * newPrice);
  }
  line.total_amount = newAmount;

  // Uppdatera amount-cellen
  const amountEl = document.querySelector(`[data-amount-for="${idx}"]`);
  if (amountEl) {
    amountEl.textContent = newAmount == null ? '—' : `${fmtSEK.format(newAmount)} kr`;
    const orig = mfEditorState.originalMf.lines[idx];
    const changed = (orig?.unit_price ?? null) !== newPrice;
    amountEl.classList.toggle('changed', changed);
    inp.classList.toggle('dirty', changed);
  }

  mfEditorState.dirty = isMfDirty();
  updateMfTotals();
  updateMfDirtyState();
}

function isMfDirty() {
  const cur = mfEditorState.parsedMf?.lines || [];
  const orig = mfEditorState.originalMf?.lines || [];
  if (cur.length !== orig.length) return true;
  for (let i = 0; i < cur.length; i++) {
    if ((cur[i].unit_price ?? null) !== (orig[i].unit_price ?? null)) return true;
  }
  return false;
}

function updateMfTotals() {
  const lines = mfEditorState.parsedMf?.lines || [];
  let grandTotal = 0;
  const sectionTotals = {};

  for (const line of lines) {
    const amount = line.total_amount;
    if (amount == null) continue;
    grandTotal += amount;
    const sec = (line.ama_code || '')[0];
    if (sec) {
      sectionTotals[sec] = (sectionTotals[sec] || 0) + amount;
    }
  }

  const totalEl = document.getElementById('mfGrandTotal');
  if (totalEl) totalEl.textContent = `${fmtSEK.format(round2(grandTotal))} kr`;

  document.querySelectorAll('[data-section-total]').forEach((el) => {
    const sec = el.dataset.sectionTotal;
    const t = sectionTotals[sec];
    el.textContent = t ? `${fmtSEK.format(round2(t))} kr` : '';
  });
}

function updateMfDirtyState() {
  const mark = document.getElementById('mfDirtyMark');
  const saveBtn = document.getElementById('mfSaveBtn');
  if (mark) mark.hidden = !mfEditorState.dirty;
  if (saveBtn) saveBtn.disabled = !mfEditorState.dirty;
}

function bindMfEditorActions() {
  const saveBtn = document.getElementById('mfSaveBtn');
  const revertBtn = document.getElementById('mfRevertBtn');
  const excelBtn = document.getElementById('mfExcelBtn');
  if (saveBtn && !saveBtn._bound) {
    saveBtn.addEventListener('click', saveMfEditor);
    saveBtn._bound = true;
  }
  if (revertBtn && !revertBtn._bound) {
    revertBtn.addEventListener('click', revertMfEditor);
    revertBtn._bound = true;
  }
  if (excelBtn && !excelBtn._bound) {
    excelBtn.addEventListener('click', () => {
      if (mfEditorState.caseId) downloadCaseMfExcel(mfEditorState.caseId);
    });
    excelBtn._bound = true;
  }
}

async function saveMfEditor() {
  if (!mfEditorState.caseId || !mfEditorState.parsedMf) return;
  const saveBtn = document.getElementById('mfSaveBtn');
  const original = saveBtn.textContent;
  saveBtn.disabled = true;
  saveBtn.textContent = 'Sparar…';

  try {
    const res = await fetch(`/api/cases/${encodeURIComponent(mfEditorState.caseId)}/mf`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parsed_mf: mfEditorState.parsedMf }),
    });
    if (!res.ok) {
      const err = await safeJson(res);
      throw new Error(err?.detail || `HTTP ${res.status}`);
    }
    const d = await res.json();
    // Re-baseline: original ← current
    mfEditorState.originalMf = JSON.parse(JSON.stringify(mfEditorState.parsedMf));
    mfEditorState.dirty = false;
    document.querySelectorAll('.mf-price-input.dirty').forEach((el) => el.classList.remove('dirty'));
    document.querySelectorAll('.mf-amount.changed').forEach((el) => el.classList.remove('changed'));
    updateMfDirtyState();
    saveBtn.textContent = 'Sparat ✓';
    setTimeout(() => { saveBtn.textContent = original; }, 1200);

    // Uppdatera banner-meta om totalen ändrats
    const banner = document.getElementById('caseBannerMeta');
    if (banner && d.total_amount_sek != null) {
      // best effort — uppdaterar inte rest av meta, bara om vi ser totalen
    }
  } catch (e) {
    saveBtn.textContent = original;
    alert(`Kunde inte spara: ${e.message}`);
  } finally {
    saveBtn.disabled = !mfEditorState.dirty;
  }
}

function revertMfEditor() {
  if (!mfEditorState.originalMf) return;
  if (mfEditorState.dirty && !confirm('Återställa alla ändringar?')) return;
  mfEditorState.parsedMf = JSON.parse(JSON.stringify(mfEditorState.originalMf));
  mfEditorState.dirty = false;
  renderMfEditorRows();
  updateMfTotals();
  updateMfDirtyState();
}

function round2(v) {
  return Math.round(v * 100) / 100;
}

function bindDraftModal() {
  const modal = document.getElementById('draftModal');
  if (!modal) return;
  document.getElementById('draftModalClose').addEventListener('click', closeDraftModal);
  document.getElementById('draftModalSave').addEventListener('click', saveDraftFromModal);
  document.getElementById('draftModalRegenerate').addEventListener('click', regenerateDraftFromModal);
  document.getElementById('draftModalPdf').addEventListener('click', () => {
    if (currentDraftCaseId && currentDraftDocId) {
      downloadDraftPdf(currentDraftCaseId, currentDraftDocId);
    }
  });
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeDraftModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal.hidden) closeDraftModal();
  });
}

function typeShort(t) {
  return ({
    'mf': 'MF', 'af': 'AF', 'tb': 'TB', 'ritning': 'RIT',
    'if': 'IF', 'rf': 'RF', 'kontrakt': 'KONTR', 'sekretess': 'SEKR', 'okant': '?',
  })[t] || t.toUpperCase();
}

function renderMarkdownLight(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>')
    .replace(/^/, '<p>')
    .replace(/$/, '</p>');
}

function saveMfToHistory(parsedMf) {
  try {
    const meta = parsedMf.metadata || {};
    const lines = parsedMf.lines || [];
    const fakeSummary = {
      project: meta.project_name,
      document_number: meta.document_number,
      total_amount_sek: meta.total_amount_sek,
      line_count: lines.length,
      ama_codes_used: [...new Set(lines.map((l) => l.ama_code).filter(Boolean))],
    };
    saveToHistory({
      filename: meta.document_number ? `${meta.document_number}.csv` : 'package_mf.csv',
      summary: fakeSummary,
    });
  } catch (e) { console.warn(e); }
}

// ---------- KUNSKAPSBAS -------------------------------------------------

async function renderKunskapsbas() {
  const listEl = document.getElementById('kbCaseList');
  const detailPanel = document.getElementById('kbDetailPanel');
  detailPanel.hidden = true;

  listEl.innerHTML = '<div class="empty-state"><p>Laddar …</p></div>';

  try {
    const res = await fetch('/api/cases');
    const d = await res.json();
    const cases = d.cases || [];

    document.getElementById('kbStatCases').textContent = cases.length;
    const allCodes = new Set();
    let totalLessons = 0;
    let totalValue = 0;
    for (const c of cases) {
      (c.ama_codes || []).forEach((code) => allCodes.add(code));
      totalLessons += c.lesson_count || 0;
      if (c.total_amount_sek) totalValue += c.total_amount_sek;
    }
    document.getElementById('kbStatAma').textContent = allCodes.size;
    document.getElementById('kbStatLessons').textContent = totalLessons;
    document.getElementById('kbStatValue').textContent = totalValue
      ? `${fmtSEK.format(totalValue)} kr`
      : '—';

    if (cases.length === 0) {
      listEl.innerHTML = '<div class="empty-state"><p>Tomt arkiv. Ladda upp ett paket på Start så börjar agenten lära sig.</p></div>';
      return;
    }

    listEl.innerHTML = cases.map((c) => `
      <div class="bid-row" data-case-id="${escapeHtml(c.id)}">
        <div>
          <div class="bid-name">${escapeHtml(c.project_name || c.source_name)}</div>
          <div class="bid-meta">${escapeHtml(c.document_number || '—')} · ${c.file_count} filer · ${c.lesson_count} lärdomar · ${escapeHtml(c.source)}</div>
        </div>
        <div class="bid-amount">${c.total_amount_sek ? fmtSEK.format(c.total_amount_sek) + ' kr' : '—'}</div>
        <div class="bid-date">${formatRelDate(c.created_at)}</div>
        <div></div>
      </div>
    `).join('');

    listEl.querySelectorAll('.bid-row').forEach((row) => {
      row.addEventListener('click', () => loadCaseDetail(row.dataset.caseId));
    });
  } catch (e) {
    listEl.innerHTML = `<div class="empty-state"><p>Fel: ${escapeHtml(e.message)}</p></div>`;
  }

  document.getElementById('kbDetailClose').onclick = () => { detailPanel.hidden = true; };
}

async function loadCaseDetail(caseId) {
  const detailPanel = document.getElementById('kbDetailPanel');
  const titleEl = document.getElementById('kbDetailTitle');
  const contentEl = document.getElementById('kbDetailContent');

  contentEl.innerHTML = '<p class="muted">Laddar …</p>';
  detailPanel.hidden = false;
  detailPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });

  try {
    const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}`);
    const c = await res.json();

    titleEl.textContent = c.project_name || c.source_name || c.id;

    const meta = `
      <div class="kb-meta-grid">
        <div class="kb-meta-item">
          <div class="kb-meta-label">Dokumentnr</div>
          <div class="kb-meta-value">${escapeHtml(c.document_number || '—')}</div>
        </div>
        <div class="kb-meta-item">
          <div class="kb-meta-label">Beställare</div>
          <div class="kb-meta-value">${escapeHtml(c.customer || '—')}</div>
        </div>
        <div class="kb-meta-item">
          <div class="kb-meta-label">Totalbelopp</div>
          <div class="kb-meta-value">${c.total_amount_sek ? fmtSEK.format(c.total_amount_sek) + ' kr' : '—'}</div>
        </div>
        <div class="kb-meta-item">
          <div class="kb-meta-label">Källa</div>
          <div class="kb-meta-value">${escapeHtml(c.source)}: ${escapeHtml(c.source_name || '')}</div>
        </div>
        <div class="kb-meta-item">
          <div class="kb-meta-label">Sparad</div>
          <div class="kb-meta-value">${escapeHtml(c.created_at || '')}</div>
        </div>
        <div class="kb-meta-item">
          <div class="kb-meta-label">Filer</div>
          <div class="kb-meta-value">${(c.files || []).length}</div>
        </div>
      </div>
    `;

    const tags = c.summary?.tags || [];
    const tagsHtml = tags.length > 0
      ? `<div class="kb-tag-row">${tags.map((t) => `<span class="kb-tag">${escapeHtml(t)}</span>`).join('')}</div>`
      : '';

    const agentSummary = c.summary?.agent_summary
      ? `<div class="kb-section"><h3>Agentens sammanfattning</h3><p>${escapeHtml(c.summary.agent_summary)}</p></div>`
      : '';

    const lessons = c.lessons || [];
    const lessonsHtml = lessons.length > 0
      ? `<div class="kb-section">
          <h3>Lärdomar (${lessons.length})</h3>
          ${lessons.map((l) => `
            <div class="kb-lesson">
              <span class="kb-lesson-type" data-type="${escapeHtml(l.type)}">${escapeHtml(l.type)}</span>
              <span class="kb-lesson-code">${escapeHtml(l.ama_code || '—')}</span>
              <span class="kb-lesson-note">${escapeHtml(l.note || '')}</span>
            </div>
          `).join('')}
        </div>`
      : '<div class="kb-section"><h3>Lärdomar</h3><p class="muted">Inga lärdomar extraherade — Claude API kanske inte var konfigurerad vid uppladdning.</p></div>';

    const filesHtml = c.files && c.files.length > 0
      ? `<div class="kb-section">
          <h3>Filer i paketet</h3>
          ${c.files.map((f) => `
            <div style="display: flex; gap: 10px; padding: 6px 0; border-bottom: 1px solid var(--ljusgra);">
              <span class="file-chip-type" data-type="${escapeHtml(f.type)}" style="display: inline-block; padding: 2px 7px; font-family: var(--font-mono); font-size: 0.72rem; border-radius: 10px;">${escapeHtml(typeShort(f.type))}</span>
              <span style="font-size: 0.88rem;">${escapeHtml(f.filename)}</span>
            </div>
          `).join('')}
        </div>`
      : '';

    contentEl.innerHTML = meta + tagsHtml + agentSummary + lessonsHtml + filesHtml;
  } catch (e) {
    contentEl.innerHTML = `<p>Fel: ${escapeHtml(e.message)}</p>`;
  }
}

// ---------- UE-MEJL-VYN -------------------------------------------------

function renderUePage() {
  const ueAreasEl = document.getElementById('ueAreas');
  const suggestions = lastAnalysis?.ue_suggestions || [
    'Spont och pålning', 'Asfaltering', 'Elinstallation',
    'Belysningsinstallation', 'Märkning och skyltning', 'Linjemålning',
  ];
  ueAreasEl.dataset.areas = JSON.stringify(suggestions);
  ueAreasEl.innerHTML = suggestions.map((a) => `
    <span class="ue-area-chip selected" data-area="${escapeHtml(a)}">
      ${escapeHtml(a)}
      <span class="ue-area-chip-x">✕</span>
    </span>
  `).join('');

  ueAreasEl.querySelectorAll('.ue-area-chip').forEach((chip) => {
    chip.addEventListener('click', () => chip.classList.toggle('selected'));
  });
}

function bindUeForm() {
  const form = document.getElementById('ueForm');
  const extra = document.getElementById('ueExtraArea');
  if (!form) return;

  extra.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const v = extra.value.trim();
      if (!v) return;
      const ueAreasEl = document.getElementById('ueAreas');
      const chip = document.createElement('span');
      chip.className = 'ue-area-chip selected';
      chip.dataset.area = v;
      chip.innerHTML = `${escapeHtml(v)} <span class="ue-area-chip-x">✕</span>`;
      chip.addEventListener('click', () => chip.classList.toggle('selected'));
      ueAreasEl.appendChild(chip);
      extra.value = '';
    }
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const selected = Array.from(document.querySelectorAll('.ue-area-chip.selected'))
      .map((c) => c.dataset.area);
    if (selected.length === 0) {
      alert('Välj minst ett UE-område');
      return;
    }
    const fd = new FormData(form);
    fd.append('areas', selected.join(','));
    try {
      const res = await fetch('/api/ue/email', { method: 'POST', body: fd });
      const d = await res.json();
      renderUeDrafts(d.drafts);
    } catch (e) {
      console.error(e);
    }
  });
}

function renderUeDrafts(drafts) {
  const el = document.getElementById('ueDraftList');
  el.innerHTML = drafts.map((d, i) => `
    <div class="ue-draft">
      <div class="ue-draft-area">${escapeHtml(d.area)}</div>
      <p class="ue-draft-subject">${escapeHtml(d.subject)}</p>
      <pre class="ue-draft-body" id="ueBody${i}">${escapeHtml(d.body)}</pre>
      <div class="ue-draft-actions">
        <a class="btn btn-primary btn-sm" href="${d.mailto}">Öppna i mailklient</a>
        <button class="btn btn-ghost btn-sm" data-copy="${i}">Kopiera text</button>
      </div>
    </div>
  `).join('');

  el.querySelectorAll('[data-copy]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const text = document.getElementById(`ueBody${btn.dataset.copy}`).textContent;
      try {
        await navigator.clipboard.writeText(text);
        const orig = btn.textContent;
        btn.textContent = 'Kopierat ✓';
        setTimeout(() => { btn.textContent = orig; }, 1500);
      } catch {}
    });
  });
}

// ---------- CHAT (Claude API) -------------------------------------------

const chatHistory = [];
let chatBusy = false;
let currentChatId = null;
let chatConfigured = true;

function bindChat() {
  // Två formulär: hero (chatForm) och bottom (chatFormBottom). Båda postar samma chat.
  const heroForm = document.getElementById('chatForm');
  const bottomForm = document.getElementById('chatFormBottom');

  if (heroForm) {
    heroForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const inp = document.getElementById('chatInput');
      const text = inp.value.trim();
      if (!text || chatBusy) return;
      inp.value = '';
      switchAgentMode('chat');
      sendChat(text);
    });
  }

  if (bottomForm) {
    bottomForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const inp = document.getElementById('chatInputBottom');
      const text = inp.value.trim();
      if (!text || chatBusy) return;
      inp.value = '';
      sendChat(text);
    });
  }

  // Status-check för Claude-konfiguration
  fetch('/api/chat/status')
    .then((r) => r.json())
    .then((d) => {
      chatConfigured = !!d.configured;
      if (!chatConfigured) {
        const status = document.getElementById('chatStatus');
        if (status) {
          status.textContent = 'inte konfigurerad — ANTHROPIC_API_KEY saknas i Railway';
          status.classList.add('error');
        }
        ['chatInput', 'chatInputBottom'].forEach((id) => {
          const inp = document.getElementById(id);
          if (inp) {
            inp.placeholder = 'Lägg till ANTHROPIC_API_KEY i Railway-variablerna för att aktivera';
            inp.disabled = true;
          }
        });
        ['chatSendBtn', 'chatSendBtnBottom'].forEach((id) => {
          const b = document.getElementById(id);
          if (b) b.disabled = true;
        });
      }
    })
    .catch(() => {});
}

function appendChatMessage(role, text) {
  const wrap = document.getElementById('chatMessages');
  const el = document.createElement('div');
  el.className = `chat-message ${role}`;
  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble';
  bubble.textContent = text;
  el.appendChild(bubble);
  wrap.appendChild(el);
  scrollChatToBottom();
  return el;
}

function scrollChatToBottom() {
  // Scrollar hela window eftersom chat-stream nu lever inline i content
  setTimeout(() => {
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
  }, 30);
}

async function sendChat(userText) {
  chatBusy = true;
  ['chatSendBtn', 'chatSendBtnBottom'].forEach((id) => {
    const b = document.getElementById(id);
    if (b) b.disabled = true;
  });

  appendChatMessage('user', userText);
  chatHistory.push({ role: 'user', content: userText });

  const agentEl = appendChatMessage('agent', '');
  agentEl.classList.add('thinking');
  const bubble = agentEl.querySelector('.chat-bubble');

  let full = '';

  try {
    const context = lastAnalysis
      ? {
          file_count: lastAnalysis.summary.file_count,
          types: lastAnalysis.summary.type_breakdown,
          project_name: lastAnalysis.summary.project_name,
          ue_suggestions: lastAnalysis.ue_suggestions,
          recommendations: lastAnalysis.recommendations.map((r) => r.title),
        }
      : null;

    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: chatHistory, context }),
    });

    if (!res.ok || !res.body) {
      const err = await safeJson(res);
      throw new Error(err?.detail || `HTTP ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop() || '';
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith('data: ')) continue;
        let data;
        try { data = JSON.parse(line.slice(6)); } catch { continue; }
        if (data.type === 'token') {
          full += data.text;
          bubble.textContent = full;
          scrollChatToBottom();
        } else if (data.type === 'error') {
          throw new Error(data.message);
        } else if (data.type === 'done') {
          // optional: log usage
        }
      }
    }

    chatHistory.push({ role: 'assistant', content: full });
    persistCurrentChat();
  } catch (e) {
    bubble.textContent = `⚠ ${e.message || 'Något gick fel'}`;
    bubble.style.color = 'var(--tegel)';
    chatHistory.pop();
  } finally {
    agentEl.classList.remove('thinking');
    chatBusy = false;
    if (chatConfigured) {
      ['chatSendBtn', 'chatSendBtnBottom'].forEach((id) => {
        const b = document.getElementById(id);
        if (b) b.disabled = false;
      });
    }
    const bottomInp = document.getElementById('chatInputBottom');
    if (bottomInp && !bottomInp.disabled) bottomInp.focus();
  }
}

// ---------- RECENT CHATS (sidebar) --------------------------------------

function persistCurrentChat() {
  if (chatHistory.length === 0) return;
  try {
    const list = JSON.parse(localStorage.getItem(CHATS_KEY) || '[]');
    if (!currentChatId) {
      currentChatId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    }
    const firstUser = chatHistory.find((m) => m.role === 'user');
    const title = firstUser ? firstUser.content.slice(0, 60) : 'Ny chat';
    const entry = {
      id: currentChatId,
      title,
      messages: chatHistory.slice(),
      updated_at: new Date().toISOString(),
    };
    const filtered = list.filter((c) => c.id !== currentChatId);
    filtered.unshift(entry);
    localStorage.setItem(CHATS_KEY, JSON.stringify(filtered.slice(0, 30)));
    renderRecentChats();
  } catch (e) { console.warn(e); }
}

function loadRecentChats() {
  try { return JSON.parse(localStorage.getItem(CHATS_KEY) || '[]'); }
  catch { return []; }
}

function renderRecentChats() {
  const el = document.getElementById('recentChatsList');
  if (!el) return;
  const list = loadRecentChats();
  if (list.length === 0) {
    el.innerHTML = '<p class="sidebar-empty">Inga chattar ännu</p>';
    return;
  }
  el.innerHTML = list.map((c) => `
    <a class="sidebar-recent-item${c.id === currentChatId ? ' active' : ''}" data-chat-id="${escapeHtml(c.id)}" title="${escapeHtml(c.title)}">${escapeHtml(c.title)}</a>
  `).join('');
  el.querySelectorAll('[data-chat-id]').forEach((a) => {
    a.addEventListener('click', (e) => {
      e.preventDefault();
      restoreChat(a.dataset.chatId);
    });
  });
}

function restoreChat(id) {
  const list = loadRecentChats();
  const c = list.find((x) => x.id === id);
  if (!c) return;
  currentChatId = id;
  chatHistory.length = 0;
  c.messages.forEach((m) => chatHistory.push(m));
  switchAgentMode('chat');
  const wrap = document.getElementById('chatMessages');
  wrap.innerHTML = '';
  for (const m of chatHistory) {
    appendChatMessage(m.role === 'assistant' ? 'agent' : 'user', m.content);
  }
  location.hash = '#/start';
  renderRecentChats();
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
