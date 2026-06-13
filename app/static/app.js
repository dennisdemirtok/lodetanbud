// =========================================================================
// Lodet — frontend (vanilla JS, no build step)
// =========================================================================

const fmtSEK = new Intl.NumberFormat('sv-SE', { maximumFractionDigits: 0 });
const fmtNum = new Intl.NumberFormat('sv-SE');

const CHATS_KEY = 'lodet:chats';

// ---------- ROUTING ------------------------------------------------------

const ROUTES = {
  '#/start':              { tab: 'agent',       view: 'start',         crumb: 'Start',                   handler: renderStart },
  '#/agent/ue':           { tab: 'agent',       view: 'agent-ue',      crumb: 'Agent / UE-mejl',         handler: renderUePage },
  '#/kunskapsbas':        { tab: 'kunskapsbas', view: 'kunskapsbas',   crumb: 'Kunskapsbas',             handler: renderKunskapsbas },
  '#/kalkylator':         { tab: 'kalkylator',  view: 'kalkylator',    crumb: 'Kalkylator',              handler: renderKalkylatorEmpty },
  '#/dashboard':          { tab: 'anbud',       view: 'dashboard',     crumb: 'Översikt',                handler: renderDashboard },
  '#/upload':             { tab: 'anbud',       view: 'upload',        crumb: 'Anbud / nytt',            handler: renderUpload },
  '#/bids/active':        { tab: 'anbud',       view: 'bids-active',   crumb: 'Anbud / pågående',        handler: renderActiveBids },
  '#/bids/submitted':     { tab: 'anbud',       view: 'bids-submitted',crumb: 'Anbud / inlämnade',       handler: renderSubmittedBids },
  '#/bids/archive':       { tab: 'anbud',       view: 'bids-archive',  crumb: 'Anbud / arkiv',           handler: renderArchiveBids },
  '#/docs/mf':            { tab: 'anbud',       view: 'docs-mf',       crumb: 'Dokument / MF',           handler: renderDocsMf },
  '#/docs/afb':           { tab: 'bibliotek',   view: 'docs-afb',      crumb: 'Mallar',                  handler: renderAfbList },
  '#/docs/drawings':      { tab: 'anbud',       view: 'docs-drawings', crumb: 'Dokument / ritningar',    handler: renderDrawings },
  '#/ama/anlaggning':     { tab: 'bibliotek',   view: 'ama',           crumb: 'AMA / Anläggning',        handler: () => renderAma('AMA_Anläggning', 'AMA Anläggning 23') },
  '#/ama/hus':            { tab: 'bibliotek',   view: 'ama',           crumb: 'AMA / Hus',               handler: () => renderAmaPlaceholder('AMA Hus 21', 'Husbyggnadskoder läses in inom kort.') },
  '#/ama/el':             { tab: 'bibliotek',   view: 'ama',           crumb: 'AMA / El',                handler: () => renderAmaPlaceholder('AMA El 22', 'AMA El-koder läses in inom kort.') },
  '#/ama/af':             { tab: 'bibliotek',   view: 'ama',           crumb: 'AMA / AF',                handler: () => renderAma('AF_AMA', 'AF AMA 21') },
  '#/mallar/anbudssumma': { tab: 'bibliotek',   view: 'template',      crumb: 'Mallar / AFB.31',         handler: () => renderTemplate('anbudssumma') },
  '#/mallar/ue-lista':    { tab: 'bibliotek',   view: 'template',      crumb: 'Mallar / AFB.32',         handler: () => renderTemplate('ue-lista') },
  '#/mallar/sekretess':   { tab: 'bibliotek',   view: 'template',      crumb: 'Mallar / Sekretess',      handler: () => renderTemplate('sekretess') },
  '#/mallar/missiv':      { tab: 'bibliotek',   view: 'template',      crumb: 'Mallar / Missiv',         handler: () => renderTemplate('missiv') },
  '#/historik':           { tab: 'anbud',       view: 'historik',      crumb: 'Historik',                handler: renderHistory },
  '#/inst/foretag':       { tab: 'inst',        view: 'inst',          crumb: 'Inst / Företag',          handler: renderCompanyForm },
  '#/inst/resurser':      { tab: 'inst',        view: 'inst',          crumb: 'Inst / Resurser',         handler: renderResourcesView },
  '#/inst/index':         { tab: 'inst',        view: 'inst',          crumb: 'Inst / Index',            handler: () => renderInst('Indexserier', 'E84 per litt och KPI för indexjustering av historiska priser.') },
  '#/inst/paslag':        { tab: 'inst',        view: 'inst',          crumb: 'Inst / Påslag',           handler: () => renderInst('Påslag och marginaler', 'Standardpåslag per kategori + täckningsbidragsregler.') },
  '#/inst/anvandare':     { tab: 'inst',        view: 'inst',          crumb: 'Inst / Användare',        handler: () => renderInst('Användare', 'Roller och behörigheter för flera användare.') },
};

function navigate() {
  const hash = location.hash || '#/start';

  // Dynamisk route: #/anbud/edit/{case_id} — redirect till översikten (cockpit)
  const editMatch = hash.match(/^#\/anbud\/edit\/(.+)$/);
  if (editMatch) {
    const caseId = editMatch[1];
    location.hash = `#/oversikt/${caseId}`;
    return;
  }

  // Dynamisk route: #/oversikt/{case_id} — per-anbud cockpit (status + att-göra)
  const ovMatch = hash.match(/^#\/oversikt\/(.+)$/);
  if (ovMatch) {
    const caseId = decodeURIComponent(ovMatch[1]);
    document.querySelectorAll('.view').forEach((v) => v.hidden = true);
    const viewEl = document.querySelector('[data-view="oversikt"]');
    if (viewEl) viewEl.hidden = false;
    document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
    document.querySelector('.tab[data-tab="anbud"]')?.classList.add('active');
    document.querySelectorAll('.sidebar-section').forEach((s) => s.hidden = true);
    const sb = document.querySelector('.sidebar-section[data-sidebar="anbud"]');
    if (sb) sb.hidden = false;
    document.querySelectorAll('.sidebar-link').forEach((el) => el.classList.remove('active'));
    document.querySelectorAll('.sidebar.open').forEach((s) => s.classList.remove('open'));
    window.scrollTo({ top: 0 });
    renderOverview(caseId);
    return;
  }

  // Dynamisk route: #/kalkylator/{case_id}
  const kalkMatch = hash.match(/^#\/kalkylator\/(.+)$/);
  if (kalkMatch) {
    const caseId = decodeURIComponent(kalkMatch[1]);
    document.querySelectorAll('.view').forEach((v) => v.hidden = true);
    const viewEl = document.querySelector('[data-view="kalkylator"]');
    if (viewEl) viewEl.hidden = false;
    document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
    document.querySelector('.tab[data-tab="kalkylator"]')?.classList.add('active');
    document.querySelectorAll('.sidebar-section').forEach((s) => s.hidden = true);
    const sb = document.querySelector('.sidebar-section[data-sidebar="kalkylator"]');
    if (sb) sb.hidden = false;
    document.querySelectorAll('.sidebar-link').forEach((el) => el.classList.remove('active'));
    document.querySelectorAll('.sidebar.open').forEach((s) => s.classList.remove('open'));
    window.scrollTo({ top: 0 });
    renderKalkylatorForCase(caseId);
    return;
  }

  // Dynamisk route: #/granska/{case_id} — granskningsvyn (AP2)
  const granskaMatch = hash.match(/^#\/granska\/(.+)$/);
  if (granskaMatch) {
    const caseId = decodeURIComponent(granskaMatch[1]);
    document.querySelectorAll('.view').forEach((v) => v.hidden = true);
    const viewEl = document.querySelector('[data-view="granska"]');
    if (viewEl) viewEl.hidden = false;
    document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
    document.querySelector('.tab[data-tab="kalkylator"]')?.classList.add('active');
    document.querySelectorAll('.sidebar-section').forEach((s) => s.hidden = true);
    const sb = document.querySelector('.sidebar-section[data-sidebar="kalkylator"]');
    if (sb) sb.hidden = false;
    document.querySelectorAll('.sidebar-link').forEach((el) => el.classList.remove('active'));
    document.querySelectorAll('.sidebar.open').forEach((s) => s.classList.remove('open'));
    window.scrollTo({ top: 0 });
    loadGranska(caseId);
    return;
  }

  // Dynamisk route: #/krav/{case_id} — kravmatrisen (AP3)
  const kravMatch = hash.match(/^#\/krav\/(.+)$/);
  if (kravMatch) {
    const caseId = decodeURIComponent(kravMatch[1]);
    document.querySelectorAll('.view').forEach((v) => v.hidden = true);
    const viewEl = document.querySelector('[data-view="krav"]');
    if (viewEl) viewEl.hidden = false;
    document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
    document.querySelector('.tab[data-tab="kalkylator"]')?.classList.add('active');
    document.querySelectorAll('.sidebar-section').forEach((s) => s.hidden = true);
    const sb = document.querySelector('.sidebar-section[data-sidebar="kalkylator"]');
    if (sb) sb.hidden = false;
    document.querySelectorAll('.sidebar-link').forEach((el) => el.classList.remove('active'));
    document.querySelectorAll('.sidebar.open').forEach((s) => s.classList.remove('open'));
    window.scrollTo({ top: 0 });
    loadKrav(caseId);
    return;
  }

  // Dynamisk route: #/slutfor/{case_id} — formaliagrind + inlämning (AP5)
  const slutMatch = hash.match(/^#\/slutfor\/(.+)$/);
  if (slutMatch) {
    const caseId = decodeURIComponent(slutMatch[1]);
    document.querySelectorAll('.view').forEach((v) => v.hidden = true);
    const viewEl = document.querySelector('[data-view="slutfor"]');
    if (viewEl) viewEl.hidden = false;
    document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
    document.querySelector('.tab[data-tab="kalkylator"]')?.classList.add('active');
    document.querySelectorAll('.sidebar-section').forEach((s) => s.hidden = true);
    const sb = document.querySelector('.sidebar-section[data-sidebar="kalkylator"]');
    if (sb) sb.hidden = false;
    document.querySelectorAll('.sidebar-link').forEach((el) => el.classList.remove('active'));
    document.querySelectorAll('.sidebar.open').forEach((s) => s.classList.remove('open'));
    window.scrollTo({ top: 0 });
    loadSlutfor(caseId);
    return;
  }

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
  bindGlobalDropGuard();
  bindUpload();
  bindTemplateForm();
  bindStart();
  bindUeForm();
  bindChat();
  bindDraftModal();
  bindCalcModal();
  bindAnswerModal();
  if (!location.hash) location.hash = '#/start';
  navigate();
  renderRecentChats();
});

// ---------- GLOBAL DROP-GUARD ------------------------------------------
// Förhindrar att browsern navigerar bort när användaren råkar släppa filer
// utanför dropzonen. Acceptera drop var som helst i Agent-vyn.

function bindGlobalDropGuard() {
  // Global preventDefault så att browsern inte navigerar till den droppade filen
  ['dragenter', 'dragover'].forEach((ev) => {
    window.addEventListener(ev, (e) => {
      // Visa drop-feedback om vi är i agent-vyn
      const view = document.querySelector('[data-view="start"]');
      if (view && !view.hidden && _hasFiles(e.dataTransfer)) {
        e.preventDefault();
        document.body.classList.add('global-drag-active');
      }
    });
  });

  ['dragleave', 'dragend'].forEach((ev) => {
    window.addEventListener(ev, (e) => {
      // Endast ta bort feedback om vi lämnar fönstret helt
      if (!e.relatedTarget || e.target === document) {
        document.body.classList.remove('global-drag-active');
      }
    });
  });

  window.addEventListener('drop', async (e) => {
    document.body.classList.remove('global-drag-active');
    // Förhindra att browsern öppnar filen som URL
    e.preventDefault();
    // Om vi är i Agent-vyn, plocka upp filerna och kör paketanalys
    const view = document.querySelector('[data-view="start"]');
    if (!view || view.hidden) return;
    if (!_hasFiles(e.dataTransfer)) return;

    // Bara hantera om drop INTE redan hanterats av dropzonen
    const dz = document.getElementById('multiDropzone');
    if (dz && dz.contains(e.target)) return;

    const files = await collectDroppedFiles(e.dataTransfer);
    if (files.length) handlePackageFiles(files);
  });
}

function _hasFiles(dt) {
  if (!dt) return false;
  if (dt.types) {
    for (const t of dt.types) {
      if (t === 'Files') return true;
    }
  }
  return false;
}

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
    renderResults(data);
    clearStatus();
  } catch (e) {
    showStatus(`Kunde inte parsa filen: ${e.message}`, 'error');
    document.getElementById('results').hidden = true;
  }
}

async function loadExample() {
  showStatus('Hämtar exempel …', 'loading');
  lastUploadedFile = null;
  lastWasExample = true;
  try {
    const res = await fetch('/api/example');
    const data = await res.json();
    lastParsedData = data;
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

// Nästa steg per state — driver den guidade hubben
function nextStepFor(state, caseId) {
  const id = encodeURIComponent(caseId || '');
  return ({
    INTAKE:         { label: 'Analyserar…',        route: `#/kalkylator/${id}` },
    EXTRACTING:     { label: 'Analyserar…',        route: `#/kalkylator/${id}` },
    NEEDS_REVIEW:   { label: 'Granska extraktion', route: `#/granska/${id}` },
    CALCULATING:    { label: 'Prissätt kalkyl',    route: `#/kalkylator/${id}` },
    DRAFTING:       { label: 'Besvara krav',       route: `#/krav/${id}` },
    FORMALIA_CHECK: { label: 'Slutför',            route: `#/slutfor/${id}` },
    READY:          { label: 'Lämna in',           route: `#/slutfor/${id}` },
    SUBMITTED:      { label: 'Registrera utfall',  route: `#/slutfor/${id}` },
    AWARDED:        { label: 'Vunnet ✓',           route: `#/slutfor/${id}` },
    LOST:           { label: 'Förlorat',           route: `#/slutfor/${id}` },
  })[state] || { label: 'Öppna', route: `#/anbud/edit/${id}` };
}

let _activeBidsPoll = null;
let _kalkPoll = null;
let _overviewPoll = null;

// Per-anbud cockpit: status, nyckeltal, härledd att-göra-lista, formalia.
async function renderOverview(caseId) {
  const el = document.getElementById('overviewContent');
  el.innerHTML = '<div class="empty-state"><p>Laddar översikt …</p></div>';
  let d;
  try {
    const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}/overview`);
    if (!res.ok) throw new Error(res.status === 404 ? 'Anbudet hittades inte' : `HTTP ${res.status}`);
    d = await res.json();
  } catch (e) {
    el.innerHTML = `<div class="empty-state"><p>Fel: ${escapeHtml(e.message)}</p></div>`;
    return;
  }

  const s = d.stats || {};
  const deadline = d.bid_due_at
    ? `<span class="ov-deadline">Deadline ${escapeHtml(String(d.bid_due_at).slice(0, 10))}</span>` : '';

  // Att-göra-lista — första ej klara markeras som "nu"
  let currentMarked = false;
  const checklist = (d.checklist || []).map((c) => {
    const isCurrent = !c.done && !currentMarked;
    if (isCurrent) currentMarked = true;
    const icon = c.done ? '<span class="ov-check done">✓</span>'
      : isCurrent ? '<span class="ov-check current">→</span>'
      : '<span class="ov-check">○</span>';
    return `
      <button class="ov-todo${c.done ? ' done' : ''}${isCurrent ? ' current' : ''}" data-route="${escapeAttr(c.route)}">
        ${icon}
        <span class="ov-todo-body">
          <span class="ov-todo-label">${escapeHtml(c.label)}</span>
          <span class="ov-todo-detail">${escapeHtml(c.detail || '')}</span>
        </span>
        <span class="ov-todo-arrow">${c.done ? '' : '→'}</span>
      </button>`;
  }).join('');

  const formalia = d.formalia
    ? (d.formalia.passed
        ? '<span class="ov-formalia pass">✓ Formalia klar — redo att lämna in</span>'
        : `<span class="ov-formalia fail">${d.formalia.blocking_count} punkter blockerar inlämning</span>`)
    : '<span class="ov-formalia muted">Analyseras …</span>';

  el.innerHTML = `
    <div class="page-head ov-head">
      <p class="eyebrow">Anbud${d.document_number ? ' · ' + escapeHtml(d.document_number) : ''}</p>
      <h1 class="ov-title">${escapeHtml(d.project_name || 'Namnlöst anbud')}<button class="ov-rename" title="Byt namn" aria-label="Byt namn på anbudet">✎</button></h1>
      <div class="ov-meta">${stateChip(d)}${deadline}${d.customer ? '<span>' + escapeHtml(d.customer) + '</span>' : ''}</div>
    </div>

    <div class="ov-progress-wrap">
      <div class="ov-progress-bar"><div class="ov-progress-fill" style="width:${d.progress}%"></div></div>
      <span class="ov-progress-label">${d.progress}% klart</span>
    </div>

    <div class="card-grid stat-grid ov-stats">
      <div class="stat-card"><span class="stat-label">Mängdförteckning</span><span class="stat-value">${s.mf_priced ?? 0}/${s.mf_rows ?? 0}</span><span class="stat-sub">rader prissatta</span></div>
      <div class="stat-card"><span class="stat-label">Anbudssumma</span><span class="stat-value">${s.mf_total_sek ? fmtSEK.format(s.mf_total_sek) : '—'}</span><span class="stat-sub">kr exkl. moms</span></div>
      <div class="stat-card"><span class="stat-label">Skall-krav</span><span class="stat-value">${s.krav_answered ?? 0}/${s.krav_skall ?? 0}</span><span class="stat-sub">besvarade</span></div>
      <div class="stat-card"><span class="stat-label">Filer</span><span class="stat-value">${s.file_count ?? 0}</span><span class="stat-sub">i paketet</span></div>
    </div>

    <div class="two-col ov-cols">
      <div class="panel ov-todo-panel">
        <div class="panel-head"><h2>Att göra</h2>${d.next_step ? `<span class="muted small">Nästa: ${escapeHtml(d.next_step.label)}</span>` : '<span class="muted small">Klart 🎉</span>'}</div>
        <div class="ov-todo-list">${checklist || '<div class="empty-state"><p>Anbudet analyseras …</p></div>'}</div>
      </div>
      <div class="panel ov-side">
        <div class="panel-head"><h2>Status</h2></div>
        <div class="ov-side-body">
          <p class="ov-formalia-row">${formalia}</p>
          ${d.busy ? '' : `<button class="btn btn-primary ov-autopilot-btn" data-autopilot="${escapeAttr(caseId)}">✦ Driv anbudet framåt</button>`}
          <p class="ov-autopilot-hint">Agenten prissätter, skriver utkast och frågar dig bara där den behöver omdöme.</p>
          <div class="ov-quick">
            <button class="btn btn-ghost btn-sm" data-route="#/kalkylator/${escapeAttr(caseId)}">Kalkylator</button>
            <button class="btn btn-ghost btn-sm" data-route="#/krav/${escapeAttr(caseId)}">Kravmatris</button>
            <button class="btn btn-ghost btn-sm" data-route="#/slutfor/${escapeAttr(caseId)}">Slutför</button>
          </div>
        </div>
      </div>
    </div>
    <div id="autopilotPanel" class="panel ov-autopilot-panel" hidden></div>`;

  const apBtn = el.querySelector('[data-autopilot]');
  if (apBtn) apBtn.addEventListener('click', () => runAutopilot(caseId));

  // Redigerbart projektnamn (rename matter) — klick på ✎ → inline-fält → PATCH
  const renameBtn = el.querySelector('.ov-rename');
  if (renameBtn) renameBtn.addEventListener('click', () => {
    const h1 = el.querySelector('.ov-title');
    const current = d.project_name && d.project_name !== 'Namnlöst anbud' ? d.project_name : '';
    h1.innerHTML = `<input class="ov-title-input" value="${escapeAttr(current)}" placeholder="Projektnamn" />`;
    const inp = h1.querySelector('input');
    inp.focus(); inp.select();
    const save = async () => {
      const name = inp.value.trim();
      if (name && name !== d.project_name) {
        try {
          await fetch(`/api/cases/${encodeURIComponent(caseId)}`, {
            method: 'PATCH', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_name: name }),
          });
        } catch {}
      }
      renderOverview(caseId);  // rendera om med nytt namn
    };
    inp.addEventListener('blur', save);
    inp.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') inp.blur();
      if (e.key === 'Escape') renderOverview(caseId);
    });
  });

  // Auto-uppdatera medan analysen pågår
  clearTimeout(_overviewPoll);
  if (d.busy) {
    _overviewPoll = setTimeout(() => {
      if (location.hash.includes(`/oversikt/${caseId}`)) renderOverview(caseId);
    }, 3500);
  }
}

// ---------- AUTOPILOT (driv anbudet framåt) ----------------------------

async function runAutopilot(caseId) {
  const panel = document.getElementById('autopilotPanel');
  const btn = document.querySelector('[data-autopilot]');
  if (btn) { btn.disabled = true; btn.textContent = '✦ Agenten arbetar…'; }
  if (panel) {
    panel.hidden = false;
    panel.innerHTML = '<div class="panel-head"><h2>Agenten arbetar</h2></div>'
      + '<div class="ov-ap-body"><p><span class="inline-spinner"></span> Prissätter, skriver utkast och kollar formalia…</p></div>';
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  let d;
  try {
    const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}/autopilot`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    d = await res.json();
  } catch (e) {
    if (panel) panel.innerHTML = `<div class="ov-ap-body"><p>Fel: ${escapeHtml(e.message)}</p></div>`;
    if (btn) { btn.disabled = false; btn.textContent = '✦ Driv anbudet framåt'; }
    return;
  }
  renderAutopilotResult(caseId, d);
}

function renderAutopilotResult(caseId, d) {
  const panel = document.getElementById('autopilotPanel');
  if (!panel) return;

  const actions = (d.actions || []).map((a) => `
    <li class="done"><span class="step-icon done">✓</span>
      <span class="step-body"><span class="step-label">${escapeHtml(a.label)}</span>
      <span class="step-detail">${escapeHtml(a.detail || '')}${a.route ? ` <button class="btn btn-ghost btn-xs" data-route="${escapeAttr(a.route)}">öppna →</button>` : ''}</span></span>
    </li>`).join('');

  let body = `<ul class="upload-progress-steps live">${actions || '<li class="done"><span class="step-body"><span class="step-detail">Inget nytt att göra automatiskt just nu.</span></span></li>'}</ul>`;

  if (d.checkpoint) {
    body += renderCheckpoint(caseId, d.checkpoint);
  } else if (d.done) {
    body += `<div class="ov-ap-done">🎉 ${escapeHtml(d.summary)} <button class="btn btn-primary btn-sm" data-route="#/slutfor/${escapeAttr(caseId)}">Slutför →</button></div>`;
  } else {
    body += `<div class="ov-ap-done">${escapeHtml(d.summary)} <button class="btn btn-ghost btn-sm" data-autopilot-again="${escapeAttr(caseId)}">Kör vidare</button></div>`;
  }

  panel.innerHTML = `<div class="panel-head"><h2>Agenten ${d.checkpoint ? 'behöver din input' : 'körde'}</h2></div><div class="ov-ap-body">${body}</div>`;

  panel.querySelector('[data-autopilot-again]')?.addEventListener('click', () => runAutopilot(caseId));
  bindCheckpoint(caseId, panel);
  // Uppdatera nyckeltalen/progress i bakgrunden (utan att slänga autopilot-panelen)
  refreshOverviewStats(caseId);
}

function renderCheckpoint(caseId, cp) {
  if (cp.type === 'ue') {
    const rows = (cp.areas || []).map((a, i) => `
      <div class="cp-ue-row" data-area="${escapeAttr(a.area)}">
        <span class="cp-ue-area">${escapeHtml(a.area)}</span>
        <input class="cp-ue-company" placeholder="Underentreprenör (lämna tomt = egen regi)" value="${escapeAttr(a.company || '')}" />
        <input class="cp-ue-email" placeholder="e-post (valfritt)" value="${escapeAttr(a.email || '')}" />
      </div>`).join('');
    return `<div class="cp-box"><p class="cp-title">${escapeHtml(cp.title)}</p>
      <p class="cp-intro">${escapeHtml(cp.intro)}</p>
      <div class="cp-ue-list">${rows}</div>
      <button class="btn btn-primary btn-sm" data-cp-submit="ue">Spara & fortsätt →</button></div>`;
  }
  if (cp.type === 'company') {
    const fields = (cp.fields || []).map((f) => `
      <label class="cp-field">${escapeHtml(f.label)}
        <input data-cp-key="${escapeAttr(f.key)}" value="${escapeAttr(f.value || '')}" /></label>`).join('');
    return `<div class="cp-box"><p class="cp-title">${escapeHtml(cp.title)}</p>
      <p class="cp-intro">${escapeHtml(cp.intro)}</p>
      <div class="cp-company-fields">${fields}</div>
      <button class="btn btn-primary btn-sm" data-cp-submit="company">Spara & fortsätt →</button></div>`;
  }
  return '';
}

function bindCheckpoint(caseId, panel) {
  const submit = panel.querySelector('[data-cp-submit]');
  if (!submit) return;
  submit.addEventListener('click', async () => {
    submit.disabled = true;
    try {
      if (submit.dataset.cpSubmit === 'ue') {
        const assignments = {};
        panel.querySelectorAll('.cp-ue-row').forEach((row) => {
          const company = row.querySelector('.cp-ue-company').value.trim();
          assignments[row.dataset.area] = {
            company,
            email: row.querySelector('.cp-ue-email').value.trim(),
          };
        });
        await fetch(`/api/cases/${encodeURIComponent(caseId)}/ue`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ assignments }),
        });
      } else if (submit.dataset.cpSubmit === 'company') {
        const payload = {};
        panel.querySelectorAll('[data-cp-key]').forEach((inp) => { payload[inp.dataset.cpKey] = inp.value.trim(); });
        await fetch('/api/company', {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      }
      runAutopilot(caseId);  // fortsätt där den stannade
    } catch (e) {
      submit.disabled = false;
    }
  });
}

// Uppdatera översiktens nyckeltal/progress utan att rendera om hela vyn
async function refreshOverviewStats(caseId) {
  try {
    const d = await (await fetch(`/api/cases/${encodeURIComponent(caseId)}/overview`)).json();
    const fill = document.querySelector('.ov-progress-fill');
    const lbl = document.querySelector('.ov-progress-label');
    if (fill) fill.style.width = `${d.progress}%`;
    if (lbl) lbl.textContent = `${d.progress}% klart`;
  } catch {}
}

// Statusgrupper för de tre bid-vyerna
const _ACTIVE_STATES = new Set(['INTAKE', 'EXTRACTING', 'NEEDS_REVIEW', 'CALCULATING', 'DRAFTING', 'FORMALIA_CHECK', 'READY']);
const _SUBMITTED_STATES = new Set(['SUBMITTED']);
const _ARCHIVE_STATES = new Set(['AWARDED', 'LOST']);

async function renderActiveBids() {
  return renderBidList('localBidsList', _ACTIVE_STATES,
    'Inga anbud än. Ladda upp ett förfrågningsunderlag på <a href="#/start">Agent-sidan</a>.', true);
}
async function renderSubmittedBids() {
  return renderBidList('submittedBidsList', _SUBMITTED_STATES, 'Inga inlämnade anbud än.', false);
}
async function renderArchiveBids() {
  return renderBidList('archiveBidsList', _ARCHIVE_STATES, 'Inga vunna eller förlorade anbud än.', false);
}

async function renderBidList(elId, states, emptyMsg, poll) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.innerHTML = '<div class="empty-state"><p>Laddar anbud …</p></div>';

  try {
    const res = await fetch('/api/cases');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();
    const cases = (d.cases || []).filter((c) => states.has(c.state));

    if (cases.length === 0) {
      el.innerHTML = `<div class="empty-state"><p>${emptyMsg}</p></div>`;
      return;
    }

    el.innerHTML = cases.map((c) => {
      const reqCount = c.required_count || 0;
      const draftCount = c.draft_count || 0;
      const progress = reqCount > 0 ? `${draftCount}/${reqCount} utkast` : `${c.file_count} filer`;
      const next = nextStepFor(c.state, c.id);
      const busy = c.state === 'INTAKE' || c.state === 'EXTRACTING';
      return `
        <div class="bid-row${busy ? ' busy' : ''}" data-case-id="${escapeHtml(c.id)}">
          <div>
            <div class="bid-name">${escapeHtml(c.project_name || c.source_name || '—')}${stateChip(c)}</div>
            <div class="bid-meta">${escapeHtml(c.document_number || '')} ${c.document_number ? '· ' : ''}${progress}</div>
          </div>
          <div class="bid-amount">${c.total_amount_sek ? fmtSEK.format(c.total_amount_sek) + ' kr' : '—'}</div>
          <div class="bid-next"><span class="bid-next-label">${escapeHtml(next.label)}</span><span class="bid-next-arrow">→</span></div>
          <div class="bid-date">${formatRelDate(c.created_at)}</div>
        </div>
      `;
    }).join('');

    // Klick på ett anbud → cockpit-översikten (visar nästa steg + att-göra)
    el.querySelectorAll('.bid-row').forEach((row) => {
      row.addEventListener('click', () => {
        location.hash = `#/oversikt/${encodeURIComponent(row.dataset.caseId)}`;
      });
    });

    // Auto-uppdatera om något anbud fortfarande analyseras
    if (poll && cases.some((c) => c.state === 'INTAKE' || c.state === 'EXTRACTING')) {
      clearTimeout(_activeBidsPoll);
      _activeBidsPoll = setTimeout(() => {
        if (location.hash.startsWith('#/bids/active')) renderActiveBids();
      }, 4000);
    }
  } catch (e) {
    el.innerHTML = `<div class="empty-state"><p>Fel: ${escapeHtml(e.message)}</p></div>`;
  }

  const clearBtn = document.getElementById('clearLocalBtn');
  if (clearBtn && !clearBtn._bound) {
    clearBtn.style.display = 'none';  // Inte längre relevant — case-arkivet styrs via /kunskapsbas-vyn
    clearBtn._bound = true;
  }
}

async function fetchDocuments(docType) {
  const q = docType ? `?doc_type=${encodeURIComponent(docType)}` : '';
  const res = await fetch(`/api/documents${q}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()).documents || [];
}

async function renderDocsMf() {
  const el = document.getElementById('docsMfList');
  el.innerHTML = '<div class="empty-state"><p>Laddar …</p></div>';
  try {
    const all = await fetchDocuments('mf');
    // Radstatistiken är per CASE — visa en rad per case även om paketet har
    // flera MF-filer (annars ser identiska totaler ut som dubbletter)
    const seen = new Set();
    const docs = all.filter((d) => !seen.has(d.case_id) && seen.add(d.case_id));
    if (docs.length === 0) {
      el.innerHTML = '<div class="empty-state"><p>Inga mängdförteckningar än. Ladda upp ett förfrågningsunderlag på <a href="#/start">Agent-sidan</a>.</p></div>';
      return;
    }
    el.innerHTML = docs.map((d) => {
      const stats = d.line_count != null
        ? `${d.line_count} rader · ${d.priced || 0} prissatta`
        : escapeHtml(d.filename || '');
      return `
        <div class="bid-row" data-route="#/kalkylator/${escapeAttr(d.case_id)}">
          <div>
            <div class="bid-name">${escapeHtml(d.project_name || '—')}</div>
            <div class="bid-meta">${escapeHtml(d.filename || '')} · ${stats}</div>
          </div>
          <div class="bid-amount">${d.total_amount_sek ? fmtSEK.format(d.total_amount_sek) + ' kr' : '—'}</div>
          <div class="bid-next"><span class="bid-next-label">Öppna kalkyl</span><span class="bid-next-arrow">→</span></div>
          <div class="bid-date">${formatRelDate(d.created_at)}</div>
        </div>`;
    }).join('');
  } catch (e) {
    el.innerHTML = `<div class="empty-state"><p>Fel: ${escapeHtml(e.message)}</p></div>`;
  }
}

async function renderDrawings() {
  const el = document.getElementById('docsDrawingsList');
  el.innerHTML = '<div class="empty-state"><p>Laddar …</p></div>';
  try {
    const docs = await fetchDocuments('ritning');
    if (docs.length === 0) {
      el.innerHTML = '<div class="empty-state"><p>Inga ritningar i något uppladdat paket än.</p></div>';
      return;
    }
    el.innerHTML = docs.map((d) => `
      <div class="bid-row" data-route="#/anbud/edit/${escapeAttr(d.case_id)}">
        <div>
          <div class="bid-name">${escapeHtml(d.filename || '—')}</div>
          <div class="bid-meta">${escapeHtml(d.project_name || '')}${d.label ? ' · ' + escapeHtml(d.label) : ''}</div>
        </div>
        <div class="bid-amount">${d.page_count ? d.page_count + ' sidor' : ''}</div>
        <div class="bid-next"><span class="bid-next-label">Öppna anbud</span><span class="bid-next-arrow">→</span></div>
        <div class="bid-date">${formatRelDate(d.created_at)}</div>
      </div>`).join('');
  } catch (e) {
    el.innerHTML = `<div class="empty-state"><p>Fel: ${escapeHtml(e.message)}</p></div>`;
  }
}

async function renderHistory() {
  const el = document.getElementById('historyContent');
  el.innerHTML = '<div class="empty-state"><p>Laddar …</p></div>';
  try {
    const all = await fetchDocuments('mf');
    const seen = new Set();
    const docs = all.filter((d) => !seen.has(d.case_id) && seen.add(d.case_id));
    if (docs.length === 0) {
      el.innerHTML = '<div class="empty-state"><p>Tom historik. Ladda upp ett förfrågningsunderlag så dyker det upp här.</p></div>';
      return;
    }
    const allCodes = [...new Set(docs.flatMap((d) => d.ama_codes || []))].sort();
    el.innerHTML = `
      <div class="history-codes">
        <div class="history-codes-label">${allCodes.length} unika AMA-koder i dina anbud — klicka för att filtrera:</div>
        <div class="history-codes-list">
          ${allCodes.map((c) => `<button class="history-code-chip" data-code="${escapeAttr(c)}">${escapeHtml(c)}</button>`).join('')}
        </div>
      </div>
      <div id="historyRows"></div>`;

    const renderRows = (filterCode) => {
      const rows = filterCode ? docs.filter((d) => (d.ama_codes || []).includes(filterCode)) : docs;
      document.getElementById('historyRows').innerHTML = rows.map((d) => `
        <div class="bid-row" data-route="#/kalkylator/${escapeAttr(d.case_id)}">
          <div>
            <div class="bid-name">${escapeHtml(d.project_name || '—')}</div>
            <div class="bid-meta">${escapeHtml(d.document_number || '')}${d.document_number ? ' · ' : ''}${(d.ama_codes || []).length} koder</div>
          </div>
          <div class="bid-amount">${d.total_amount_sek ? fmtSEK.format(d.total_amount_sek) + ' kr' : '—'}</div>
          <div class="bid-next"><span class="bid-next-label">Öppna kalkyl</span><span class="bid-next-arrow">→</span></div>
          <div class="bid-date">${formatRelDate(d.created_at)}</div>
        </div>`).join('') || '<div class="empty-state"><p>Inget anbud med den koden.</p></div>';
    };
    renderRows(null);

    el.querySelectorAll('.history-code-chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        const active = chip.classList.contains('active');
        el.querySelectorAll('.history-code-chip').forEach((c) => c.classList.remove('active'));
        if (!active) chip.classList.add('active');
        renderRows(active ? null : chip.dataset.code);
      });
    });
  } catch (e) {
    el.innerHTML = `<div class="empty-state"><p>Fel: ${escapeHtml(e.message)}</p></div>`;
  }
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
    `<div class="empty-state"><p>${escapeHtml(msg)}</p><p class="muted">AMA Anläggning 23 finns inläst — välj den i menyn så länge.</p></div>`;
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

  prefillCompanyInto(document.getElementById('tmplForm'));
}

// Fyll företagsfält i ett formulär från sparade inställningar (ersätter
// gamla hårdkodade demo-värden)
async function prefillCompanyInto(form) {
  if (!form) return;
  try {
    const s = await (await fetch('/api/company')).json();
    const map = {
      company_name: s.company_name,
      contact_name: s.contact_name,
      contact_email: s.contact_email,
      contact_phone: s.contact_phone,
      organisationsnummer: s.organisationsnummer,
      customer_name: s.default_customer,
    };
    for (const [name, val] of Object.entries(map)) {
      const inp = form.querySelector(`[name="${name}"]`);
      if (inp && !inp.value && val) inp.value = val;
    }
  } catch {}
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
  // Återställ instContent till platshållare när man lämnar företagsformuläret
  const content = document.getElementById('instContent');
  if (content) {
    content.className = 'empty-state';
    content.innerHTML = '<p>Den här inställningen kommer snart.</p>'
      + '<p class="muted">Fyll i Företagsinfo och Resursbibliotek så länge — det är det som driver kalkylen och AFB-svaren.</p>';
  }
}

async function renderCompanyForm() {
  document.getElementById('instEyebrow').textContent = 'Inställningar';
  document.getElementById('instTitle').textContent = 'Företagsinfo';
  document.getElementById('instDesc').textContent = 'Värdena används vid generering av anbudssumma, sekretess, missiv och UE-mejl. Sparas på serversidan så de återanvänds för alla anbud.';

  const content = document.getElementById('instContent');
  content.className = 'panel company-form-panel';
  content.innerHTML = `
    <form class="form company-form" id="companyForm" autocomplete="off">
      <div class="form-row">
        <label>Företagsnamn<input type="text" name="company_name" placeholder="Ditt företag AB" required /></label>
        <label>Organisationsnummer<input type="text" name="organisationsnummer" placeholder="556000-0000" /></label>
      </div>
      <div class="form-row">
        <label>Kontaktperson<input type="text" name="contact_name" placeholder="Lars Olsson" /></label>
      </div>
      <div class="form-row">
        <label>E-post<input type="email" name="contact_email" placeholder="lars@westcon.se" /></label>
        <label>Telefon<input type="tel" name="contact_phone" placeholder="070-000 00 00" /></label>
      </div>
      <div class="form-row">
        <label>Adress<input type="text" name="address" placeholder="Storgatan 1, 123 45 Stad" /></label>
      </div>
      <div class="form-row">
        <label>Standardbeställare (optional)<input type="text" name="default_customer" placeholder="Trafikverket" /></label>
      </div>

      <div class="company-form-section">Företagsfakta för AFB-svar</div>
      <p class="company-form-hint">Dessa uppgifter är det enda agenten får citera när den genererar svar på anbudskrav. Tomma fält blir <code>[SAKNAS]</code>-markörer i utkasten — aldrig påhittade siffror.</p>
      <div class="form-row">
        <label>Årsomsättning (Mkr)<input type="text" name="omsattning_msek" placeholder="180" /></label>
        <label>Antal anställda<input type="text" name="antal_anstallda" placeholder="45" /></label>
      </div>
      <div class="form-row">
        <label>Certifikat<input type="text" name="certifikat" placeholder="ISO 9001, ISO 14001, BF9K" /></label>
      </div>
      <div class="form-row">
        <label>Referensprojekt<textarea name="referensprojekt" rows="2" placeholder="Vägbelysning Rv84 (Trafikverket, 2023, 4,2 Mkr)…"></textarea></label>
      </div>
      <div class="form-row">
        <label>Nyckelpersoner<textarea name="nyckelpersoner" rows="2" placeholder="Platschef Lars Olsson, 18 års erfarenhet av väg/anläggning…"></textarea></label>
      </div>
      <div class="form-row">
        <label>UE-policy<textarea name="ue_policy" rows="2" placeholder="Hur företaget arbetar med underentreprenörer…"></textarea></label>
      </div>

      <div class="form-actions">
        <span class="muted small" id="companyFormStatus"></span>
        <button type="submit" class="btn btn-primary">Spara</button>
      </div>
    </form>
  `;

  // Hämta nuvarande inställningar och fyll i fälten
  try {
    const res = await fetch('/api/company');
    const settings = await res.json();
    const form = document.getElementById('companyForm');
    for (const [key, value] of Object.entries(settings || {})) {
      const inp = form.querySelector(`[name="${key}"]`);
      if (inp) inp.value = value || '';
    }
  } catch (e) {
    console.warn('Kunde inte hämta företagsinställningar:', e);
  }

  document.getElementById('companyForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const status = document.getElementById('companyFormStatus');
    const fd = new FormData(form);
    const payload = Object.fromEntries(fd.entries());

    const btn = form.querySelector('button[type="submit"]');
    btn.disabled = true;
    status.textContent = 'Sparar…';
    status.className = 'muted small';

    try {
      const res = await fetch('/api/company', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await res.json();
      status.textContent = 'Sparat ✓';
      status.className = 'small';
      status.style.color = 'var(--salvia)';
    } catch (err) {
      status.textContent = `Fel: ${err.message}`;
      status.style.color = 'var(--tegel)';
    } finally {
      btn.disabled = false;
    }
  });
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
    const redirect = document.getElementById('mfEditorRedirect');
    if (redirect) redirect.hidden = true;
    const insights = document.getElementById('insightsPanel');
    if (insights) insights.hidden = true;
    if (typeof hideUploadProgress === 'function') hideUploadProgress();
  }
}

async function handlePackageFiles(files) {
  // Växla till chat-läge så användaren ser fortskridandet
  switchAgentMode('chat');

  const status = document.getElementById('agentStatus');
  status.hidden = true;

  showUploadProgress(files);

  const fd = new FormData();
  // webkitRelativePath bär mappkontext (t.ex. "10. Mängdförteckning/…")
  // som klassificeraren använder som signal
  for (const f of files) fd.append('files', f, f.webkitRelativePath || f.name);

  try {
    // Synkron del: uppladdning + case-skapande (< 1 s). Analysen körs som
    // jobb på servern — vi pollar status tills den är klar.
    const res = await fetch('/api/package/analyze', { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await safeJson(res);
      throw new Error(err?.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    const caseIds = data.case_ids || [];
    if (caseIds.length === 0) throw new Error('Inga cases skapades');

    const outcome = await pollCasesUntilDone(caseIds);

    if (outcome === 'timeout') {
      // Analysen är seg men fortsätter på servern — landa mjukt, inte ett fel.
      finishUploadProgress();
      showBackgroundNotice(caseIds[0]);
      setTimeout(hideUploadProgress, 800);
      return;
    }

    finishUploadProgress();

    const results = await Promise.all(caseIds.map(async (id) => {
      const r = await fetch(`/api/cases/${encodeURIComponent(id)}/result`);
      if (!r.ok) throw new Error(`Kunde inte hämta resultat för ${id}`);
      return r.json();
    }));

    if (results.length === 1) {
      lastAnalysis = results[0].analysis;
      renderAgentResult(results[0].analysis, results[0].saved_case);
    } else {
      renderMultiAgentResult({
        multi: true,
        case_count: results.length,
        results,
      });
    }
    setTimeout(hideUploadProgress, 800);
  } catch (e) {
    hideUploadProgress();
    status.hidden = false;
    status.className = 'status error';
    status.textContent = `Fel: ${e.message}`;
  }
}

// Mjuk landning när analysen drar ut på tiden — anbudet finns och blir klart.
function showBackgroundNotice(caseId) {
  _lastUploadCaseId = caseId;
  const chat = document.getElementById('chatMessages');
  if (chat) {
    const el = document.createElement('div');
    el.className = 'bg-notice';
    el.innerHTML = `
      <p><strong>Anbudet skapas i bakgrunden.</strong> Stora förfrågningsunderlag tar
      någon minut extra att analysera klart — du behöver inte vänta kvar här.</p>
      <button class="btn btn-primary btn-sm" data-route="#/anbud/edit/${escapeAttr(caseId)}">Öppna anbudet →</button>
      <button class="btn btn-ghost btn-sm" data-route="#/dashboard">Visa alla anbud</button>`;
    chat.appendChild(el);
    scrollChatToBottom();
  }
}

// Returnerar 'done' när alla klara, 'timeout' när taket nås, kastar vid jobbfel.
// Pollar /status och renderar serverns arbetssteg live under tiden.
async function pollCasesUntilDone(caseIds, { timeoutMs = 720000, intervalMs = 2000 } = {}) {
  const t0 = Date.now();
  while (true) {
    const statuses = await Promise.all(caseIds.map(async (id) => {
      try {
        const r = await fetch(`/api/cases/${encodeURIComponent(id)}/status`);
        return r.ok ? await r.json() : null;
      } catch { return null; }
    }));
    const valid = statuses.filter(Boolean);

    if (valid[0]?.progress?.length) renderLiveProgress(valid[0].progress);

    const failedJob = valid.flatMap((s) => s.jobs || []).find((j) => j.status === 'failed');
    if (failedJob) {
      const firstLine = (failedJob.error || 'Analysen misslyckades').split('\n')[0];
      throw new Error(firstLine);
    }

    const busy = valid.some((s) => s.state === 'INTAKE' || s.state === 'EXTRACTING');
    if (valid.length === caseIds.length && !busy) return 'done';

    if (Date.now() - t0 > timeoutMs) return 'timeout';
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

function stateChip(c) {
  if (!c || !c.state) return '';
  return ` <span class="state-chip" data-state="${escapeHtml(c.state)}">${escapeHtml(c.state_label || c.state)}</span>`;
}

// ---------- UPLOAD PROGRESS UI (server-driven, Harvey-stil) ------------
// Stegen kommer från analysis_progress-events via /status-pollingen —
// riktiga arbetssteg med riktiga räknare, ingen simulering.

let _uploadProgressTimer = null;
let _uploadProgressStart = 0;
// Total-steg för bar-procent: read, classify, krav, claude, save (+rescue ibland)
const _EXPECTED_STEPS = 5;

function showUploadProgress(files) {
  const el = document.getElementById('uploadProgress');
  if (!el) return;
  el.hidden = false;
  _uploadProgressStart = Date.now();

  document.getElementById('uploadProgressSteps').innerHTML =
    `<li class="active"><span class="step-icon"><span class="inline-spinner"></span></span>` +
    `<span class="step-body"><span class="step-label">Laddar upp ${files.length} filer…</span></span></li>`;
  document.getElementById('uploadProgressFill').style.width = '3%';

  if (_uploadProgressTimer) clearInterval(_uploadProgressTimer);
  const estEl = document.getElementById('uploadProgressEstimate');
  _uploadProgressTimer = setInterval(() => {
    const s = Math.floor((Date.now() - _uploadProgressStart) / 1000);
    estEl.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  }, 1000);
}

// Rendera serverns arbetssteg. steps = [{step,label,status,detail?}, …]
function renderLiveProgress(steps) {
  const ul = document.getElementById('uploadProgressSteps');
  if (!ul || !steps || !steps.length) return;

  ul.innerHTML = steps.map((s) => {
    const done = s.status === 'done';
    const icon = done
      ? '<span class="step-icon done">✓</span>'
      : '<span class="step-icon"><span class="inline-spinner"></span></span>';
    const detail = s.detail ? `<span class="step-detail">${escapeHtml(s.detail)}</span>` : '';
    return `<li class="${done ? 'done' : 'active'}">${icon}<span class="step-body"><span class="step-label">${escapeHtml(s.label)}</span>${detail}</span></li>`;
  }).join('');

  const doneCount = steps.filter((s) => s.status === 'done').length;
  const pct = Math.min(95, Math.round((doneCount / _EXPECTED_STEPS) * 88) + 6);
  document.getElementById('uploadProgressFill').style.width = `${pct}%`;
}

function finishUploadProgress() {
  if (_uploadProgressTimer) {
    clearInterval(_uploadProgressTimer);
    _uploadProgressTimer = null;
  }
  document.querySelectorAll('#uploadProgressSteps li').forEach((li) => {
    li.classList.remove('active');
    li.classList.add('done');
    const ic = li.querySelector('.step-icon');
    if (ic) { ic.classList.add('done'); ic.innerHTML = '✓'; }
  });
  const fill = document.getElementById('uploadProgressFill');
  if (fill) fill.style.width = '100%';
  const est = document.getElementById('uploadProgressEstimate');
  if (est) est.textContent += ' · klart';
}

function hideUploadProgress() {
  if (_uploadProgressTimer) {
    clearInterval(_uploadProgressTimer);
    _uploadProgressTimer = null;
  }
  const el = document.getElementById('uploadProgress');
  if (el) el.hidden = true;
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
    renderInsights(firstResult.saved_case.insights, firstCaseId);
    loadDraftPanel(firstCaseId);

    const redirect = document.getElementById('mfEditorRedirect');
    if (redirect) {
      redirect.hidden = !firstResult.analysis?.summary?.has_mf;
      const btn = document.getElementById('openKalkylatorBtn');
      if (btn) {
        btn.onclick = () => { location.hash = `#/kalkylator/${encodeURIComponent(firstCaseId)}`; };
      }
    }
  } else {
    document.getElementById('caseCreatedBanner').hidden = true;
    document.getElementById('insightsPanel').hidden = true;
    document.getElementById('draftPanel').hidden = true;
    const redirect = document.getElementById('mfEditorRedirect');
    if (redirect) redirect.hidden = true;
    agentPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

async function loadDemoPackage() {
  switchAgentMode('chat');

  const status = document.getElementById('agentStatus');
  status.hidden = false;
  status.className = 'status loading';
  status.textContent = 'Hämtar exempel …';

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
    renderInsights(savedCase.insights, savedCase.id);
    loadDraftPanel(savedCase.id);
    postAgentSummary(analysis, savedCase);

    // Visa "öppna kalkylator"-redirect istället för att ladda MF-editorn inline
    const redirect = document.getElementById('mfEditorRedirect');
    if (redirect) {
      redirect.hidden = !analysis.summary?.has_mf;
      const btn = document.getElementById('openKalkylatorBtn');
      if (btn) {
        btn.onclick = () => { location.hash = `#/kalkylator/${encodeURIComponent(savedCase.id)}`; };
      }
    }
  } else {
    document.getElementById('caseCreatedBanner').hidden = true;
    document.getElementById('insightsPanel').hidden = true;
    document.getElementById('draftPanel').hidden = true;
    const redirect = document.getElementById('mfEditorRedirect');
    if (redirect) redirect.hidden = true;
    agentPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

// Agenten sammanfattar fynd + pekar på nästa steg (guidat flöde)
function postAgentSummary(analysis, savedCase) {
  _lastUploadCaseId = savedCase?.id || _lastUploadCaseId;
  const chat = document.getElementById('chatMessages');
  if (!chat) return;
  const s = analysis.summary || {};
  const lineCount = (analysis.parsed_mf || savedCase.parsed_mf || {}).lines?.length
    || s.mf_line_count || 0;
  const reqCount = (savedCase.required_docs || []).length;
  const hasMf = !!s.has_mf;
  const cid = savedCase.id;

  const parts = [`Klart — jag har gått igenom **${escapeHtml(s.project_name || 'paketet')}**.`];
  const facts = [];
  if (s.file_count) facts.push(`${s.file_count} filer klassade`);
  if (hasMf) facts.push(`mängdförteckning inläst`);
  if (reqCount) facts.push(`${reqCount} krav att besvara`);
  if (facts.length) parts.push(facts.join(' · ') + '.');

  parts.push('Öppna översikten så ser du allt som ska göras steg för steg.');
  const cta = `<button class="btn btn-primary btn-sm" data-route="#/oversikt/${escapeAttr(cid)}">Öppna översikten →</button>`;

  const el = document.createElement('div');
  el.className = 'chat-message agent agent-summary';
  el.innerHTML = `<div class="chat-bubble">${renderMarkdownLight(parts.join(' '))}
    <div class="agent-summary-cta">${cta}
      <button class="btn btn-ghost btn-sm" data-suggest-prices="${escapeAttr(cid)}">Låt agenten föreslå priser</button>
    </div></div>`;
  chat.appendChild(el);
  el.querySelector('[data-suggest-prices]')?.addEventListener('click', () => {
    location.hash = `#/kalkylator/${encodeURIComponent(cid)}`;
    setTimeout(() => { const b = document.getElementById('mfSuggestBtn'); if (b) b.click(); }, 1200);
  });
  scrollChatToBottom();
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

// ---------- INSIGHTS (proaktiva observationer/frågor) ------------------

const _OBSERVATION_LABELS = {
  deadline:   { label: 'Deadline', icon: '⏱' },
  compliance: { label: 'Krav',     icon: '⊞' },
  risk:       { label: 'Risk',     icon: '!' },
  scope:      { label: 'Omfång',   icon: '↔' },
  missing:    { label: 'Saknas',   icon: '?' },
  info:       { label: 'Info',     icon: 'i' },
};

function renderInsights(insights, caseId) {
  const panel = document.getElementById('insightsPanel');
  const content = document.getElementById('insightsContent');
  const meta = document.getElementById('insightsMeta');
  if (!panel || !content) return;

  insights = insights || { observations: [], questions: [], vendor_templates: [] };
  const observations = insights.observations || [];
  const questions = insights.questions || [];
  const vendorTemplates = insights.vendor_templates || [];

  const total = observations.length + questions.length + vendorTemplates.length;

  if (total === 0) {
    panel.hidden = true;
    return;
  }

  meta.textContent = `${observations.length} observation${observations.length === 1 ? '' : 'er'} · ${questions.length} fråg${questions.length === 1 ? 'a' : 'or'} · ${vendorTemplates.length} mall${vendorTemplates.length === 1 ? '' : 'ar'} från beställaren`;

  const sections = [];

  if (observations.length > 0) {
    sections.push(`
      <div class="insights-section">
        <p class="insights-section-head">Observationer</p>
        ${observations.map((o) => {
          const meta = _OBSERVATION_LABELS[o.type] || _OBSERVATION_LABELS.info;
          return `
            <div class="insight-item">
              <span class="insight-icon" data-type="${escapeHtml(o.type || 'info')}" title="${escapeHtml(meta.label)}">${escapeHtml(meta.icon)}</span>
              <div class="insight-body">
                <p class="insight-title">${escapeHtml(o.title || '')}</p>
                <p class="insight-text">${escapeHtml(o.body || '')}</p>
                ${o.source_section ? `<span class="insight-source">${escapeHtml(o.source_section)}</span>` : ''}
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `);
  }

  if (questions.length > 0) {
    sections.push(`
      <div class="insights-section">
        <p class="insights-section-head">Frågor agenten har för dig</p>
        <p class="insights-section-hint">Dina svar blir projektfakta som agenten använder i kravsvaren.</p>
        ${questions.map((q, i) => `
          <div class="insight-item" data-q-index="${i}">
            <span class="insight-icon" data-type="question" title="Fråga">?</span>
            <div class="insight-body">
              <p class="insight-title">${escapeHtml(q.question || '')}</p>
              ${q.why_it_matters ? `<p class="insight-question-why">${escapeHtml(q.why_it_matters)}</p>` : ''}
              ${q.answer
                ? `<p class="insight-answer">✓ <strong>Ditt svar:</strong> ${escapeHtml(q.answer)}</p>`
                : `<div class="insight-answer-form">
                     <input type="text" class="insight-answer-input" placeholder="Svara här…" />
                     <button class="btn btn-primary btn-sm insight-answer-save">Spara</button>
                   </div>`}
            </div>
          </div>
        `).join('')}
      </div>
    `);
  }

  if (vendorTemplates.length > 0) {
    sections.push(`
      <div class="insights-section">
        <p class="insights-section-head">Mallar från beställaren</p>
        ${vendorTemplates.map((t) => `
          <div class="insight-item">
            <span class="insight-icon" data-type="template" title="Beställarens mall">⊡</span>
            <div class="insight-body">
              <p class="insight-title">${escapeHtml(t.filename || '')}</p>
              <p class="insight-text">${escapeHtml(t.note || '')}</p>
              ${t.maps_to_draft_id ? `<span class="insight-source">Mappar till: ${escapeHtml(t.maps_to_draft_id)}</span>` : ''}
            </div>
          </div>
        `).join('')}
      </div>
    `);
  }

  content.innerHTML = sections.join('');
  panel.hidden = false;

  // Inline-svar på agentens frågor
  const cid = caseId || _lastUploadCaseId;
  content.querySelectorAll('.insight-item[data-q-index]').forEach((item) => {
    const btn = item.querySelector('.insight-answer-save');
    const inp = item.querySelector('.insight-answer-input');
    if (!btn || !inp || !cid) return;
    const save = async () => {
      const answer = inp.value.trim();
      if (!answer) return;
      btn.disabled = true;
      try {
        const r = await fetch(`/api/cases/${encodeURIComponent(cid)}/insights/answer`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ index: Number(item.dataset.qIndex), answer }),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        item.querySelector('.insight-answer-form').outerHTML =
          `<p class="insight-answer">✓ <strong>Ditt svar:</strong> ${escapeHtml(answer)}</p>`;
      } catch {
        btn.disabled = false;
      }
    };
    btn.addEventListener('click', save);
    inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') save(); });
  });
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

  // Granskningslänk när extraktionen har lågkonfidenta rader (AP2)
  const reviewLink = document.getElementById('caseBannerReview');
  if (reviewLink) {
    const needsReview = savedCase?.state === 'NEEDS_REVIEW';
    reviewLink.hidden = !needsReview;
    if (needsReview && savedCase?.id) {
      reviewLink.onclick = (e) => {
        e.preventDefault();
        location.hash = `#/granska/${encodeURIComponent(savedCase.id)}`;
      };
    }
  }

  banner.hidden = false;
}

// ---------- MF-EDITOR (redigerbar mängdförteckning) --------------------

let mfEditorState = {
  caseId: null,
  parsedMf: null,
  originalMf: null,
  dirty: false,
  suggestions: {},   // lineIndex → prisförslag (AP4)
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
      suggestions: {},
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
          <td colspan="7">${escapeHtml(sectionLabel(sectionLetter))}<span class="section-total" data-section-total="${escapeHtml(sectionLetter)}">—</span></td>
        </tr>
      `);
    }
    html.push(renderMfRow(line, i));
  }

  tbody.innerHTML = html.join('') || '<tr><td colspan="7" class="mf-row-empty">Inga rader</td></tr>';

  tbody.querySelectorAll('.mf-cell-input').forEach((inp) => {
    inp.addEventListener('input', onMfFieldChange);
    inp.addEventListener('focus', () => {
      if (inp.classList.contains('mono')) inp.select();
    });
  });
  tbody.querySelectorAll('.mf-row-delete').forEach((btn) => {
    btn.addEventListener('click', onMfDeleteRow);
  });
  tbody.querySelectorAll('.mf-row-calc').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      const idx = parseInt(btn.dataset.lineIndex, 10);
      if (!Number.isNaN(idx)) openCalcModal(idx);
    });
  });
  tbody.querySelectorAll('.mf-suggestion').forEach((btn) => {
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.dataset.suggestIndex, 10);
      if (!Number.isNaN(idx)) applyMfSuggestion(idx);
    });
  });
}

// ---- Prisförslag (AP4) --------------------------------------------------

const _SUGGEST_BASIS_LABELS = {
  exact: 'exakt AMA-kod',
  exact_old: 'exakt kod · äldre data',
  parent: 'närliggande kod',
  similar: 'liknande rad',
};

function mfSuggestionChip(i, hasPrice) {
  const s = mfEditorState.suggestions?.[i];
  if (!s || hasPrice) return '';
  const conf = s.confidence || 'medium';  // high=grön (lita på) · medium=gul · low=röd (granska själv)
  const titleLines = [
    `Basis: ${_SUGGEST_BASIS_LABELS[s.basis] || s.basis}${(s.flags || []).length ? ' (' + s.flags.join(', ') + ')' : ''}`,
    `Spann: ${fmtSEK.format(s.low)}–${fmtSEK.format(s.high)} kr · ${s.n} observation${s.n === 1 ? '' : 'er'}`,
    ...(s.spread_ratio && s.spread_ratio > 8 ? [`⚠ Priserna spretar ${Math.round(s.spread_ratio)}× — granska och sätt själv`] : []),
    ...(s.samples || []).map((x) => `${x.project || '—'} (${x.observed_at}): ${fmtSEK.format(x.unit_price)} kr`),
    'Klicka för att använda förslaget',
  ];
  return `<button type="button" class="mf-suggestion" data-confidence="${conf}" data-suggest-index="${i}" title="${escapeAttr(titleLines.join('\n'))}">≈ ${fmtSEK.format(s.unit_price)} <span class="mf-suggestion-n">(${s.n})</span></button>`;
}

async function fetchPriceSuggestions() {
  if (!mfEditorState.parsedMf) return;
  const btn = document.getElementById('mfSuggestBtn');
  const lines = mfEditorState.parsedMf.lines || [];
  const targets = [];
  lines.forEach((l, i) => {
    if (!l.is_lump_sum && (l.unit_price == null || l.unit_price === '')) {
      targets.push({ idx: i, ama_code: l.ama_code, description: l.description, unit: l.unit });
    }
  });
  if (targets.length === 0) {
    showAutosaveStatus('Alla rader har redan pris', '');
    return;
  }

  btn.disabled = true;
  const orig = btn.textContent;
  btn.textContent = 'Hämtar förslag…';
  try {
    const res = await fetch('/api/price/suggest-bulk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        lines: targets.slice(0, 500),
        exclude_case_id: mfEditorState.caseId,
      }),
    });
    if (!res.ok) {
      const err = await safeJson(res);
      throw new Error(err?.detail || `HTTP ${res.status}`);
    }
    const d = await res.json();
    mfEditorState.suggestions = {};
    Object.entries(d.suggestions || {}).forEach(([k, v]) => {
      mfEditorState.suggestions[parseInt(k, 10)] = v;
    });
    renderMfEditorRows();
    const found = Object.keys(mfEditorState.suggestions).length;
    showAutosaveStatus(
      `Förslag för ${found} av ${targets.length} rader · ${d.observation_count} observationer i historiken`,
      found ? 'saved' : '',
    );
  } catch (e) {
    showAutosaveStatus(`Fel: ${e.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = orig;
  }
}

function applyMfSuggestion(idx) {
  const s = mfEditorState.suggestions?.[idx];
  const line = mfEditorState.parsedMf?.lines?.[idx];
  if (!s || !line) return;

  line.unit_price = s.unit_price;
  if (line.quantity != null) {
    line.total_amount = round2(line.quantity * s.unit_price);
  }
  delete mfEditorState.suggestions[idx];
  mfEditorState.dirty = true;
  renderMfEditorRows();
  updateMfTotals();
  updateMfDirtyState();
  scheduleAutosave();

  if (mfEditorState.caseId) {
    fetch(`/api/cases/${encodeURIComponent(mfEditorState.caseId)}/price-suggestion-applied`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ama_code: line.ama_code, suggested: s.unit_price, basis: s.basis, n: s.n,
      }),
    }).catch(() => {});
  }
}

function renderMfRow(line, i) {
  const isLump = !!line.is_lump_sum;
  const isNew = !!line._new;
  const qty = line.quantity == null ? '' : line.quantity;
  const price = line.unit_price == null ? '' : line.unit_price;
  const amount = line.total_amount == null ? null : line.total_amount;

  return `
    <tr class="mf-row${isLump ? ' lump-row' : ''}${isNew ? ' mf-row-new' : ''}" data-line-index="${i}">
      <td><input type="text" class="mf-cell-input mono" data-field="ama_code" data-line-index="${i}" value="${escapeAttr(line.ama_code || '')}" style="max-width: 100px; text-align: left;" /></td>
      <td><input type="text" class="mf-cell-input desc" data-field="description" data-line-index="${i}" value="${escapeAttr(line.description || '')}" /></td>
      <td class="col-num"><input type="text" class="mf-cell-input mono" data-field="unit" data-line-index="${i}" value="${escapeAttr(line.unit || '')}" style="max-width: 60px;" /></td>
      <td class="col-num">
        ${isLump
          ? `<span class="mono">—</span>`
          : `<input type="number" class="mf-cell-input mono" step="0.01" data-field="quantity" data-line-index="${i}" value="${qty}" />`}
      </td>
      <td class="col-num">
        ${isLump
          ? `<span class="mono">—</span>`
          : `<input type="number" class="mf-cell-input mono" step="0.01" data-field="unit_price" data-line-index="${i}" value="${price}" />${mfSuggestionChip(i, price !== '')}`}
      </td>
      <td class="col-num"><span class="mf-amount" data-amount-for="${i}">${amount == null ? '—' : `${fmtSEK.format(amount)} kr`}</span></td>
      <td class="col-action">
        <button type="button" class="mf-row-calc${(line._resources && line._resources.length) ? ' has-resources' : ''}" data-line-index="${i}" title="Räkna à-pris från resurser" aria-label="Räkna à-pris från resurser">∑</button>
        <button type="button" class="mf-row-delete" data-line-index="${i}" title="Ta bort rad" aria-label="Ta bort rad">✕</button>
      </td>
    </tr>
  `;
}

function escapeAttr(s) {
  return String(s ?? '').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function onMfFieldChange(e) {
  const inp = e.target;
  const field = inp.dataset.field;
  const idx = parseInt(inp.dataset.lineIndex, 10);
  if (Number.isNaN(idx)) return;
  const line = (mfEditorState.parsedMf?.lines || [])[idx];
  if (!line) return;

  if (field === 'description' || field === 'ama_code' || field === 'unit') {
    line[field] = inp.value;
  } else {
    const raw = inp.value.trim();
    const num = raw === '' ? null : Number(raw);
    if (raw !== '' && Number.isNaN(num)) return;
    line[field] = num;
  }

  // Räkna om belopp om quantity eller unit_price ändrats
  if (field === 'quantity' || field === 'unit_price') {
    let newAmount = null;
    if (line.quantity != null && line.unit_price != null) {
      newAmount = round2(Number(line.quantity) * Number(line.unit_price));
    }
    line.total_amount = newAmount;
    const amountEl = document.querySelector(`[data-amount-for="${idx}"]`);
    if (amountEl) {
      amountEl.textContent = newAmount == null ? '—' : `${fmtSEK.format(newAmount)} kr`;
      const orig = mfEditorState.originalMf.lines[idx];
      const changed = (orig?.[field] ?? null) !== line[field];
      amountEl.classList.toggle('changed', changed);
    }
  }

  // Markera input som dirty om det skiljer sig från originalet
  const orig = mfEditorState.originalMf.lines[idx];
  if (orig) {
    const changed = (orig[field] ?? null) !== (line[field] ?? null);
    inp.classList.toggle('dirty', changed);
  } else {
    inp.classList.add('dirty');
  }

  mfEditorState.dirty = isMfDirty();
  updateMfTotals();
  updateMfDirtyState();
  scheduleAutosave();
}

function onMfDeleteRow(e) {
  const btn = e.currentTarget;
  const idx = parseInt(btn.dataset.lineIndex, 10);
  if (Number.isNaN(idx)) return;
  const line = mfEditorState.parsedMf.lines[idx];
  const desc = line?.description ? line.description.slice(0, 50) : (line?.ama_code || 'raden');
  if (!confirm(`Ta bort "${desc}"?`)) return;
  mfEditorState.parsedMf.lines.splice(idx, 1);
  renderMfEditorRows();
  mfEditorState.dirty = true;
  updateMfTotals();
  updateMfDirtyState();
  scheduleAutosave();
}

function onMfAddRow() {
  if (!mfEditorState.parsedMf) return;
  if (!Array.isArray(mfEditorState.parsedMf.lines)) {
    mfEditorState.parsedMf.lines = [];
  }
  mfEditorState.parsedMf.lines.push({
    ama_code: '',
    description: '',
    unit: 'st',
    quantity: 1,
    unit_price: null,
    total_amount: null,
    is_lump_sum: false,
    _new: true,
  });
  renderMfEditorRows();
  mfEditorState.dirty = true;
  updateMfTotals();
  updateMfDirtyState();
  scheduleAutosave();

  // Fokusera på AMA-kod-fältet på nya raden
  setTimeout(() => {
    const newIdx = mfEditorState.parsedMf.lines.length - 1;
    const inp = document.querySelector(`.mf-cell-input[data-field="ama_code"][data-line-index="${newIdx}"]`);
    if (inp) {
      inp.focus();
      inp.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, 30);
}

function isMfDirty() {
  const cur = mfEditorState.parsedMf?.lines || [];
  const orig = mfEditorState.originalMf?.lines || [];
  if (cur.length !== orig.length) return true;
  for (let i = 0; i < cur.length; i++) {
    const a = cur[i], b = orig[i];
    if (!b) return true;
    if ((a.ama_code ?? '') !== (b.ama_code ?? '')) return true;
    if ((a.description ?? '') !== (b.description ?? '')) return true;
    if ((a.unit ?? '') !== (b.unit ?? '')) return true;
    if ((a.quantity ?? null) !== (b.quantity ?? null)) return true;
    if ((a.unit_price ?? null) !== (b.unit_price ?? null)) return true;
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
  const csvBtn = document.getElementById('mfCsvBtn');
  const addBtn = document.getElementById('mfAddRowBtn');
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
  if (csvBtn && !csvBtn._bound) {
    csvBtn.addEventListener('click', () => {
      if (mfEditorState.caseId) downloadCaseMfCsv(mfEditorState.caseId);
    });
    csvBtn._bound = true;
  }
  if (addBtn && !addBtn._bound) {
    addBtn.addEventListener('click', onMfAddRow);
    addBtn._bound = true;
  }
  const suggestBtn = document.getElementById('mfSuggestBtn');
  if (suggestBtn && !suggestBtn._bound) {
    suggestBtn.addEventListener('click', fetchPriceSuggestions);
    suggestBtn._bound = true;
  }
}

// ---- Auto-save ---------------------------------------------------------

let _autosaveTimer = null;

function scheduleAutosave() {
  if (_autosaveTimer) clearTimeout(_autosaveTimer);
  showAutosaveStatus('Ej sparat', '');
  _autosaveTimer = setTimeout(() => {
    if (mfEditorState.dirty) performAutosave();
  }, 1500);
}

async function performAutosave() {
  if (!mfEditorState.caseId || !mfEditorState.parsedMf || !mfEditorState.dirty) return;
  showAutosaveStatus('Sparar…', 'saving');

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
    await res.json();
    mfEditorState.originalMf = JSON.parse(JSON.stringify(mfEditorState.parsedMf));
    mfEditorState.dirty = false;
    document.querySelectorAll('.mf-cell-input.dirty').forEach((el) => el.classList.remove('dirty'));
    document.querySelectorAll('.mf-amount.changed').forEach((el) => el.classList.remove('changed'));
    document.querySelectorAll('.mf-row-new').forEach((el) => el.classList.remove('mf-row-new'));
    updateMfDirtyState();
    showAutosaveStatus('Sparat ✓', 'saved');
  } catch (e) {
    showAutosaveStatus(`Fel: ${e.message}`, 'error');
  }
}

function showAutosaveStatus(msg, kind) {
  const el = document.getElementById('mfAutosaveStatus');
  if (!el) return;
  el.textContent = msg;
  el.className = `mf-autosave-status muted small ${kind || ''}`;
}

function downloadCaseMfCsv(caseId) {
  const url = `/api/cases/${encodeURIComponent(caseId)}/mf/csv`;
  const a = document.createElement('a');
  a.href = url;
  a.download = '';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

// ---------- KALKYLATOR ----------------------------------------------------

const KALK_RECENT_KEY = 'lodet:kalkylator:recent';
let _kalkCurrentCase = null;

async function renderKalkylatorEmpty() {
  document.getElementById('kalkylatorEmpty').hidden = false;
  document.getElementById('kalkylatorCase').hidden = true;
  renderKalkylatorRecent();

  const listEl = document.getElementById('kalkylatorCaseList');
  listEl.innerHTML = '<div class="empty-state"><p>Laddar anbud …</p></div>';

  try {
    const res = await fetch('/api/cases');
    const d = await res.json();
    const cases = d.cases || [];

    if (cases.length === 0) {
      listEl.innerHTML = '<div class="empty-state"><p>Inga anbud än. Ladda upp ett förfrågningsunderlag via <a href="#/start">Agent-tabben</a>.</p></div>';
      return;
    }

    listEl.innerHTML = cases.map((c) => `
      <div class="bid-row" data-case-id="${escapeHtml(c.id)}">
        <div>
          <div class="bid-name">${escapeHtml(c.project_name || c.source_name || '—')}${stateChip(c)}</div>
          <div class="bid-meta">${escapeHtml(c.document_number || '')} ${c.document_number ? '· ' : ''}${c.file_count} filer · ${c.required_count || 0} krav</div>
        </div>
        <div class="bid-amount">${c.total_amount_sek ? fmtSEK.format(c.total_amount_sek) + ' kr' : '—'}</div>
        <div class="bid-date">${formatRelDate(c.created_at)}</div>
        <div></div>
      </div>
    `).join('');

    listEl.querySelectorAll('.bid-row').forEach((row) => {
      row.addEventListener('click', () => {
        location.hash = `#/kalkylator/${encodeURIComponent(row.dataset.caseId)}`;
      });
    });
  } catch (e) {
    listEl.innerHTML = `<div class="empty-state"><p>Fel: ${escapeHtml(e.message)}</p></div>`;
  }
}

function _addKalkRecent(caseId, projectName) {
  try {
    const list = JSON.parse(localStorage.getItem(KALK_RECENT_KEY) || '[]');
    const filtered = list.filter((x) => x.id !== caseId);
    filtered.unshift({ id: caseId, name: projectName || caseId, opened_at: Date.now() });
    localStorage.setItem(KALK_RECENT_KEY, JSON.stringify(filtered.slice(0, 8)));
  } catch {}
}

function renderKalkylatorRecent() {
  const el = document.getElementById('kalkylatorRecent');
  if (!el) return;
  try {
    const list = JSON.parse(localStorage.getItem(KALK_RECENT_KEY) || '[]');
    if (list.length === 0) {
      el.innerHTML = '<p class="sidebar-empty">Inga anbud öppna</p>';
      return;
    }
    el.innerHTML = list.map((c) => `
      <a class="sidebar-recent-item" data-route="#/kalkylator/${encodeURIComponent(c.id)}" title="${escapeAttr(c.name)}">${escapeHtml(c.name)}</a>
    `).join('');
  } catch {
    el.innerHTML = '<p class="sidebar-empty">Inga anbud öppna</p>';
  }
}

async function renderKalkylatorForCase(caseId) {
  document.getElementById('kalkylatorEmpty').hidden = true;
  document.getElementById('kalkylatorCase').hidden = false;

  // Reset alla sub-tabbar till default (MF)
  document.querySelectorAll('.kalkylator-subtabs .subtab').forEach((b) => b.classList.remove('active'));
  document.querySelector('.kalkylator-subtabs .subtab[data-subtab="mf"]')?.classList.add('active');
  document.querySelectorAll('.kalkylator-pane').forEach((p) => p.hidden = p.dataset.pane !== 'mf');

  // Bind sub-tab-byten (idempotent)
  document.querySelectorAll('.kalkylator-subtabs .subtab').forEach((btn) => {
    if (!btn._bound) {
      btn.addEventListener('click', () => switchKalkylatorTab(btn.dataset.subtab));
      btn._bound = true;
    }
  });

  // Default visa "laddar"
  document.getElementById('kalkylatorProjectName').textContent = 'Laddar …';
  document.getElementById('kalkylatorMeta').textContent = '';

  try {
    const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}`);
    if (!res.ok) throw new Error(res.status === 404 ? 'Anbudet hittades inte' : `HTTP ${res.status}`);
    const c = await res.json();
    _kalkCurrentCase = c;

    const _backBtn = document.getElementById('kalkylatorBackBtn');
    if (_backBtn) _backBtn.onclick = () => { location.hash = `#/oversikt/${encodeURIComponent(caseId)}`; };
    document.getElementById('kalkylatorProjectName').textContent = c.project_name || c.source_name || c.id;
    const metaParts = [];
    if (c.document_number) metaParts.push(escapeHtml(c.document_number));
    if (c.customer) metaParts.push(escapeHtml(c.customer));
    if (c.created_at) metaParts.push(`skapad ${escapeHtml(formatRelDate(c.created_at))}`);
    document.getElementById('kalkylatorMeta').innerHTML =
      `${stateChip(c)}${metaParts.length ? ' · ' + metaParts.join(' · ') : ''}` || '—';

    // Fortfarande under analys → visa agentens arbetssteg live och auto-uppdatera
    if (c.state === 'INTAKE' || c.state === 'EXTRACTING') {
      document.getElementById('mfEditorPanel').hidden = true;
      const noMf = document.getElementById('kalkylatorNoMf');
      noMf.hidden = false;

      let stepsHtml = '';
      try {
        const st = await (await fetch(`/api/cases/${encodeURIComponent(caseId)}/status`)).json();
        if (st.progress?.length) {
          stepsHtml = '<ul class="upload-progress-steps live compact">' + st.progress.map((s) => {
            const done = s.status === 'done';
            const icon = done ? '<span class="step-icon done">✓</span>'
              : '<span class="step-icon"><span class="inline-spinner"></span></span>';
            const detail = s.detail ? `<span class="step-detail">${escapeHtml(s.detail)}</span>` : '';
            return `<li class="${done ? 'done' : 'active'}">${icon}<span class="step-body"><span class="step-label">${escapeHtml(s.label)}</span>${detail}</span></li>`;
          }).join('') + '</ul>';
        }
      } catch {}

      noMf.innerHTML = '<p><strong>Agenten arbetar med anbudet.</strong> Mängdförteckning och krav dyker upp så snart analysen är klar — sidan uppdateras automatiskt.</p>'
        + stepsHtml;
      clearTimeout(_kalkPoll);
      _kalkPoll = setTimeout(() => {
        if (location.hash.includes(`/kalkylator/${caseId}`)) renderKalkylatorForCase(caseId);
      }, 3000);
      document.getElementById('kalkStatTotal').textContent = '—';
      document.getElementById('kalkStatLines').textContent = '—';
      document.getElementById('kalkStatPriced').textContent = '—';
      document.getElementById('kalkStatAma').textContent = '—';
      return;
    }

    _addKalkRecent(caseId, c.project_name || c.source_name);
    renderKalkylatorRecent();

    // Stats
    const parsed = c.parsed_mf || {};
    const lines = parsed.lines || [];
    const total = (parsed.metadata || {}).total_amount_sek || c.total_amount_sek;
    const priced = lines.filter((l) => l.unit_price != null).length;
    const amaCodes = new Set(lines.map((l) => l.ama_code).filter(Boolean));

    document.getElementById('kalkStatTotal').textContent = total ? `${fmtSEK.format(total)} kr` : '0 kr';
    document.getElementById('kalkStatLines').textContent = lines.length || '—';
    document.getElementById('kalkStatPriced').textContent = lines.length ? `${priced} / ${lines.length}` : '—';
    document.getElementById('kalkStatAma').textContent = amaCodes.size || '—';

    // Granskningsgrind (AP2): export låst tills extraktionen är granskad
    const needsReview = c.state === 'NEEDS_REVIEW';
    const reviewBanner = document.getElementById('kalkylatorReviewBanner');
    if (reviewBanner) {
      reviewBanner.hidden = !needsReview;
      const btn = document.getElementById('kalkylatorReviewBtn');
      if (btn) btn.onclick = () => { location.hash = `#/granska/${encodeURIComponent(caseId)}`; };
    }
    ['mfCsvBtn', 'mfExcelBtn'].forEach((id) => {
      const b = document.getElementById(id);
      if (b) {
        b.disabled = needsReview;
        b.title = needsReview ? 'Granska extraktionen innan export' : '';
      }
    });

    // Tillbaka till cockpit-översikten + "Öppna i Agent" + kravmatris
    const backBtn = document.getElementById('kalkylatorBackBtn');
    if (backBtn) backBtn.onclick = () => { location.hash = `#/oversikt/${encodeURIComponent(caseId)}`; };
    document.getElementById('kalkylatorAgentBtn').onclick = () => { location.hash = '#/start'; };
    const kravBtn = document.getElementById('kalkylatorKravBtn');
    if (kravBtn) kravBtn.onclick = () => { location.hash = `#/krav/${encodeURIComponent(caseId)}`; };
    const slutBtn = document.getElementById('kalkylatorSlutforBtn');
    if (slutBtn) slutBtn.onclick = () => { location.hash = `#/slutfor/${encodeURIComponent(caseId)}`; };

    // Mängdförteckning-pane
    if (c.parsed_mf) {
      document.getElementById('mfEditorPanel').hidden = false;
      document.getElementById('kalkylatorNoMf').hidden = true;
      loadMfEditor(caseId);
    } else {
      document.getElementById('mfEditorPanel').hidden = true;
      document.getElementById('kalkylatorNoMf').hidden = false;
    }

    // Info-pane
    renderKalkylatorInfo(c);
    loadCaseTimeline(caseId);

    // Aprisberäkningar
    renderAprisOverview(c);

    // Notes
    renderKalkylatorNotes(caseId);
  } catch (e) {
    document.getElementById('kalkylatorProjectName').textContent = 'Fel';
    document.getElementById('kalkylatorMeta').textContent = e.message;
  }
}

function switchKalkylatorTab(tab) {
  document.querySelectorAll('.kalkylator-subtabs .subtab').forEach((b) => {
    b.classList.toggle('active', b.dataset.subtab === tab);
  });
  document.querySelectorAll('.kalkylator-pane').forEach((p) => {
    p.hidden = p.dataset.pane !== tab;
  });
}

function renderKalkylatorInfo(c) {
  const grid = document.getElementById('kalkylatorInfoGrid');
  if (!grid) return;
  const items = [
    { label: 'Projekt',         value: c.project_name || '—' },
    { label: 'Dokumentnummer',  value: c.document_number || '—' },
    { label: 'Beställare',      value: c.customer || '—' },
    { label: 'Källa',           value: `${c.source || '—'}: ${c.source_name || ''}` },
    { label: 'Skapad',          value: c.created_at || '—' },
    { label: 'Filer i paketet', value: (c.files || []).length },
    { label: 'Krav i anbudet',  value: (c.required_docs || []).length },
    { label: 'Utkast skapade',  value: Object.keys(c.drafts || {}).length },
    { label: 'Lärdomar',        value: (c.lessons || []).length },
    { label: 'Totalsumma',      value: c.total_amount_sek ? `${fmtSEK.format(c.total_amount_sek)} kr` : '0 kr' },
  ];
  grid.innerHTML = items.map((it) => `
    <div class="kalkylator-info-item">
      <span class="kalkylator-info-label">${escapeHtml(it.label)}</span>
      <span class="kalkylator-info-value">${escapeHtml(String(it.value))}</span>
    </div>
  `).join('');
}

function renderAprisOverview(c) {
  const listEl = document.getElementById('aprisList');
  const meta = document.getElementById('aprisSummaryMeta');
  if (!listEl) return;

  const lines = (c.parsed_mf || {}).lines || [];
  const withResources = lines
    .map((l, i) => ({ line: l, index: i }))
    .filter((x) => Array.isArray(x.line._resources) && x.line._resources.length > 0);

  meta.textContent = `${withResources.length} av ${lines.length} rader har resurs-baserad kalkyl`;

  if (withResources.length === 0) {
    listEl.innerHTML = '<div class="empty-state"><p>Inga rader har resurs-baserad à-prisberäkning än.</p><p class="muted small">Klicka <strong>∑</strong> på en rad i mängdförteckningen för att börja räkna.</p></div>';
    return;
  }

  listEl.innerHTML = withResources.map(({ line, index }) => {
    const resCount = line._resources.length;
    return `
      <div class="bid-row" data-line-index="${index}">
        <div>
          <div class="bid-name">${escapeHtml(line.ama_code || '—')} · ${escapeHtml(line.description?.slice(0, 60) || '')}</div>
          <div class="bid-meta">${resCount} resurs${resCount === 1 ? '' : 'er'} · ${line.quantity || '—'} ${line.unit || ''}</div>
        </div>
        <div class="bid-amount">${line.unit_price != null ? fmtSEK.format(line.unit_price) + ' kr/' + (line.unit || 'st') : '—'}</div>
        <div class="bid-date">${line.total_amount != null ? fmtSEK.format(line.total_amount) + ' kr' : '—'}</div>
        <div></div>
      </div>
    `;
  }).join('');

  listEl.querySelectorAll('.bid-row').forEach((row) => {
    row.addEventListener('click', () => {
      const idx = parseInt(row.dataset.lineIndex, 10);
      switchKalkylatorTab('mf');
      setTimeout(() => openCalcModal(idx), 100);
    });
  });
}

const _EVENT_LABELS = {
  case_created: 'Anbud skapat',
  state_change: 'Statusbyte',
  job_queued: 'Jobb köat',
  job_done: 'Jobb klart',
  job_retry: 'Jobb omkört',
  job_failed: 'Jobb misslyckades',
  analysis_written: 'Analys sparad',
  user_edit: 'Redigering',
  draft_updated: 'Utkast uppdaterat',
  migrated_from_json: 'Migrerad från JSON-arkivet',
  llm_call: 'LLM-anrop',
};

async function loadCaseTimeline(caseId) {
  const el = document.getElementById('kalkylatorTimeline');
  if (!el) return;
  el.innerHTML = '<li class="timeline-empty">Laddar …</li>';
  try {
    const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}/events`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();
    const events = d.events || [];
    if (events.length === 0) {
      el.innerHTML = '<li class="timeline-empty">Inga händelser ännu</li>';
      return;
    }
    el.innerHTML = events.map((e) => {
      const label = _EVENT_LABELS[e.kind] || e.kind;
      let detail = '';
      if (e.kind === 'state_change' && e.data?.to) detail = e.data.to;
      else if (e.kind === 'job_queued' || e.kind === 'job_done') detail = e.data?.kind || '';
      else if (e.kind === 'user_edit') detail = e.data?.what || '';
      else if (e.kind === 'draft_updated') detail = e.data?.doc_id || '';
      else if (e.kind === 'analysis_written') detail = `${e.data?.file_count ?? '?'} filer · ${e.data?.line_count ?? '?'} MF-rader`;
      return `
        <li class="timeline-item">
          <span class="timeline-time">${escapeHtml(formatRelDate(e.at))}</span>
          <span class="timeline-kind">${escapeHtml(label)}</span>
          <span class="timeline-detail">${escapeHtml(detail)}</span>
        </li>
      `;
    }).join('');
  } catch (err) {
    el.innerHTML = `<li class="timeline-empty">Fel: ${escapeHtml(err.message)}</li>`;
  }
}

function renderKalkylatorNotes(caseId) {
  const ta = document.getElementById('kalkylatorNotes');
  const status = document.getElementById('notesStatus');
  const savedAt = document.getElementById('notesSavedAt');
  if (!ta) return;

  const key = `lodet:notes:${caseId}`;
  try {
    const stored = JSON.parse(localStorage.getItem(key) || 'null');
    if (stored) {
      ta.value = stored.text || '';
      if (stored.saved_at) savedAt.textContent = `Sparat ${formatRelDate(stored.saved_at)}`;
    } else {
      ta.value = '';
      savedAt.textContent = '';
    }
  } catch {}

  const saveBtn = document.getElementById('saveNotesBtn');
  saveBtn.onclick = () => {
    const text = ta.value;
    try {
      localStorage.setItem(key, JSON.stringify({ text, saved_at: new Date().toISOString() }));
      status.textContent = 'Sparat ✓';
      status.style.color = 'var(--salvia)';
      savedAt.textContent = 'Sparat just nu';
      setTimeout(() => { status.textContent = ''; }, 1500);
    } catch (e) {
      status.textContent = `Fel: ${e.message}`;
      status.style.color = 'var(--tegel)';
    }
  };
}

// ---------- ÖPPNA BEFINTLIGT ANBUD I EDITORN ---------------------------

async function loadCaseInEditor(caseId) {
  switchAgentMode('chat');

  const status = document.getElementById('agentStatus');
  status.hidden = false;
  status.className = 'status loading';
  status.textContent = 'Laddar anbud …';

  try {
    const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}`);
    if (!res.ok) throw new Error(res.status === 404 ? 'Anbudet hittades inte' : `HTTP ${res.status}`);
    const c = await res.json();

    const summary = c.summary || {};
    const fakeAnalysis = {
      summary: {
        file_count: (c.files || []).length,
        project_name: c.project_name,
        has_mf: !!c.parsed_mf,
        total_size_kb: 0,
        ...summary,
      },
      files: c.files || [],
      narrative: summary.agent_summary || '',
      recommendations: [],
      ue_suggestions: [],
    };
    const fakeSavedCase = {
      id: c.id,
      lessons: c.lessons || [],
      required_docs: c.required_docs || [],
      project_name: c.project_name,
      insights: c.insights || { observations: [], questions: [], vendor_templates: [] },
    };

    lastAnalysis = fakeAnalysis;

    showCaseBanner(fakeSavedCase, fakeAnalysis);
    renderInsights(fakeSavedCase.insights, fakeSavedCase.id);

    // Filer-panel
    const filesPanel = document.getElementById('filesPanel');
    const chipsEl = document.getElementById('fileChips');
    const countEl = document.getElementById('filesPanelCount');
    countEl.textContent = `${(c.files || []).length} filer`;
    chipsEl.innerHTML = (c.files || []).map((f) => `
      <span class="file-chip">
        <span class="file-chip-type" data-type="${escapeHtml(f.type)}">${escapeHtml(typeShort(f.type))}</span>
        <span class="file-chip-name" title="${escapeHtml(f.filename)}">${escapeHtml(f.filename)}</span>
        <span class="file-chip-status">✓</span>
      </span>
    `).join('');
    filesPanel.hidden = false;

    // Agent-narrative om finns
    const agentPanel = document.getElementById('agentPanel');
    if (fakeAnalysis.narrative) {
      document.getElementById('agentNarrative').innerHTML = renderMarkdownLight(fakeAnalysis.narrative);
      document.getElementById('agentRecs').innerHTML = '';
      const recsHead = document.querySelector('.agent-recs-head');
      if (recsHead) recsHead.style.display = 'none';
      agentPanel.hidden = false;
    } else {
      agentPanel.hidden = true;
    }

    status.hidden = true;

    // Drafts + MF-editor
    loadDraftPanel(c.id);
    if (c.parsed_mf) {
      loadMfEditor(c.id);
    } else {
      document.getElementById('mfEditorPanel').hidden = true;
    }
  } catch (e) {
    status.className = 'status error';
    status.textContent = `Fel: ${e.message}`;
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
  const esc = escapeHtml(text);
  // Blockvis: rubriker och listor per rad, sedan styckebrytning
  const lines = esc.split('\n').map((line) => {
    if (/^#{1,4}\s+/.test(line)) return `<strong class="md-h">${line.replace(/^#{1,4}\s+/, '')}</strong>`;
    if (/^[-•]\s+/.test(line)) return `<span class="md-li">• ${line.replace(/^[-•]\s+/, '')}</span>`;
    if (/^\d+\.\s+/.test(line)) return `<span class="md-li">${line}</span>`;
    return line;
  });
  return ('<p>' + lines.join('\n')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n\n+/g, '</p><p>')
    .replace(/\n/g, '<br>') + '</p>');
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
  prefillCompanyInto(document.getElementById('ueForm'));
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

// Vilket anbud pratar användaren om? Route-param först, annars senaste upp.
let _lastUploadCaseId = null;
function getCurrentCaseId() {
  const m = location.hash.match(/^#\/(?:kalkylator|krav|slutfor|granska|anbud\/edit)\/([^/?]+)/);
  if (m) return decodeURIComponent(m[1]);
  return _lastUploadCaseId;
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

  // Bubblan har två delar: agentens arbetssteg (verktyg) + löpande text
  const stepsEl = document.createElement('div');
  stepsEl.className = 'agent-steps';
  stepsEl.hidden = true;
  const textEl = document.createElement('div');
  textEl.className = 'agent-text';
  bubble.textContent = '';
  bubble.appendChild(stepsEl);
  bubble.appendChild(textEl);

  let full = '';

  function addStep(data) {
    stepsEl.hidden = false;
    const row = document.createElement('div');
    row.className = 'agent-step working';
    row.dataset.tool = data.name;
    row.innerHTML = `<span class="step-icon"><span class="inline-spinner"></span></span>` +
      `<span class="step-body"><span class="step-label">${escapeHtml(data.label)}…</span></span>`;
    stepsEl.appendChild(row);
    scrollChatToBottom();
    return row;
  }

  function completeStep(data) {
    const rows = stepsEl.querySelectorAll(`.agent-step.working[data-tool="${CSS.escape(data.name)}"]`);
    const row = rows[rows.length - 1] || addStep(data);
    row.classList.remove('working');
    row.classList.add('done');
    const route = data.route
      ? ` <button class="btn btn-ghost btn-xs" data-route="${escapeAttr(data.route)}">${escapeHtml(data.route_label || 'Öppna')} →</button>`
      : '';
    row.innerHTML = `<span class="step-icon done">✓</span>` +
      `<span class="step-body"><span class="step-label">${escapeHtml(data.label)}</span>` +
      `<span class="step-detail">${escapeHtml(data.summary || '')}${route}</span></span>`;
    scrollChatToBottom();
  }

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
      body: JSON.stringify({ messages: chatHistory, context, case_id: getCurrentCaseId() }),
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
          textEl.innerHTML = renderMarkdownLight(full);
          scrollChatToBottom();
        } else if (data.type === 'tool_start') {
          addStep(data);
        } else if (data.type === 'tool_result') {
          completeStep(data);
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
    textEl.textContent = `⚠ ${e.message || 'Något gick fel'}`;
    textEl.style.color = 'var(--tegel)';
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

// ---------- RESURSBIBLIOTEK (Inställningar / Resurser) ------------------

let _resourceCache = [];
let _resourceTypes = {};

async function renderResourcesView() {
  document.getElementById('instEyebrow').textContent = 'Inställningar';
  document.getElementById('instTitle').textContent = 'Resursbibliotek';
  document.getElementById('instDesc').textContent = 'Företagets katalog över kalkyleringsresurser — maskiner, arbetare, material, underentreprenörer. Används för att räkna à-priser per MF-rad.';

  const content = document.getElementById('instContent');
  content.className = 'panel resources-panel';
  content.innerHTML = `
    <div class="resources-toolbar">
      <span class="muted small" id="resourcesCountLabel">Laddar …</span>
      <div class="resources-toolbar-actions">
        <button type="button" class="btn btn-ghost btn-sm" id="resourcesSeedBtn">Lägg in standardresurser</button>
        <button type="button" class="btn btn-primary btn-sm" id="resourcesAddBtn">+ Ny resurs</button>
      </div>
    </div>
    <div id="resourcesEditFormContainer"></div>
    <div class="resources-table-wrap">
      <table class="resources-table">
        <thead>
          <tr>
            <th>Namn</th>
            <th>Typ</th>
            <th>Kategori</th>
            <th>Enhet</th>
            <th class="col-num">Á-pris</th>
            <th class="col-action"></th>
          </tr>
        </thead>
        <tbody id="resourcesTbody"></tbody>
      </table>
    </div>
  `;

  document.getElementById('resourcesAddBtn').addEventListener('click', () => showResourceEditForm(null));
  document.getElementById('resourcesSeedBtn').addEventListener('click', async () => {
    if (!confirm('Lägg in standardresurser i biblioteket?')) return;
    try {
      const res = await fetch('/api/resources/seed', { method: 'POST' });
      const d = await res.json();
      alert(`${d.added} resurser tillagda.`);
      loadResources();
    } catch (e) {
      alert(`Fel: ${e.message}`);
    }
  });

  loadResources();
}

async function loadResources() {
  try {
    const res = await fetch('/api/resources');
    const d = await res.json();
    _resourceCache = d.resources || [];
    _resourceTypes = d.types || {};
    renderResourcesTable();
  } catch (e) {
    document.getElementById('resourcesTbody').innerHTML = `<tr><td colspan="6">Fel: ${escapeHtml(e.message)}</td></tr>`;
  }
}

function renderResourcesTable() {
  const tbody = document.getElementById('resourcesTbody');
  const count = document.getElementById('resourcesCountLabel');
  if (!tbody) return;

  count.textContent = `${_resourceCache.length} resurser i biblioteket`;

  if (_resourceCache.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:36px;color:var(--muted)">Inga resurser än. Klicka "Lägg in standardresurser" för att börja.</td></tr>';
    return;
  }

  tbody.innerHTML = _resourceCache.map((r) => `
    <tr data-resource-id="${escapeAttr(r.id)}">
      <td><strong>${escapeHtml(r.name)}</strong></td>
      <td><span class="resource-type-pill" data-type="${escapeHtml(r.type)}">${escapeHtml(_resourceTypes[r.type] || r.type)}</span></td>
      <td>${escapeHtml(r.category || '—')}</td>
      <td>${escapeHtml(r.unit || '—')}</td>
      <td class="col-num"><span class="mono">${fmtSEK.format(r.cost_per_unit || 0)} kr/${escapeHtml(r.unit || 'st')}</span></td>
      <td class="col-action">
        <button type="button" class="draft-action" data-action="edit">Ändra</button>
        <button type="button" class="mf-row-delete" data-action="delete" title="Ta bort">✕</button>
      </td>
    </tr>
  `).join('');

  tbody.querySelectorAll('[data-action="edit"]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = btn.closest('[data-resource-id]').dataset.resourceId;
      const r = _resourceCache.find((x) => x.id === id);
      if (r) showResourceEditForm(r);
    });
  });
  tbody.querySelectorAll('[data-action="delete"]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.closest('[data-resource-id]').dataset.resourceId;
      const r = _resourceCache.find((x) => x.id === id);
      if (!r || !confirm(`Ta bort "${r.name}"?`)) return;
      try {
        const res = await fetch(`/api/resources/${encodeURIComponent(id)}`, { method: 'DELETE' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        loadResources();
      } catch (e) {
        alert(`Fel: ${e.message}`);
      }
    });
  });
}

function showResourceEditForm(existing) {
  const container = document.getElementById('resourcesEditFormContainer');
  if (!container) return;

  const isNew = !existing;
  const r = existing || { name: '', type: 'maskin_forare', category: '', unit: 'tim', cost_per_unit: 0 };

  const typeOptions = Object.entries(_resourceTypes).map(([key, label]) =>
    `<option value="${escapeAttr(key)}" ${key === r.type ? 'selected' : ''}>${escapeHtml(label)}</option>`
  ).join('');

  container.innerHTML = `
    <form class="resource-edit-form" id="resourceEditForm">
      <label>Namn<input type="text" name="name" value="${escapeAttr(r.name)}" required /></label>
      <label>Typ<select name="type">${typeOptions}</select></label>
      <label>Kategori<input type="text" name="category" value="${escapeAttr(r.category)}" /></label>
      <label>Enhet<input type="text" name="unit" value="${escapeAttr(r.unit)}" placeholder="tim/m/st/ton" /></label>
      <label>Á-pris (kr)<input type="number" step="0.01" name="cost_per_unit" value="${r.cost_per_unit}" required /></label>
      <div style="display:flex;gap:6px;align-items:end">
        <button type="submit" class="btn btn-primary btn-sm">${isNew ? 'Skapa' : 'Spara'}</button>
        <button type="button" class="btn btn-ghost btn-sm" id="resourceEditCancel">Avbryt</button>
      </div>
    </form>
  `;

  document.getElementById('resourceEditCancel').addEventListener('click', () => {
    container.innerHTML = '';
  });

  document.getElementById('resourceEditForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const payload = Object.fromEntries(fd.entries());
    payload.cost_per_unit = Number(payload.cost_per_unit);

    try {
      const url = isNew ? '/api/resources' : `/api/resources/${encodeURIComponent(existing.id)}`;
      const method = isNew ? 'POST' : 'PUT';
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await safeJson(res);
        throw new Error(err?.detail || `HTTP ${res.status}`);
      }
      container.innerHTML = '';
      loadResources();
    } catch (err) {
      alert(`Fel: ${err.message}`);
    }
  });
}

// ---------- À-PRIS-KALKYL-MODAL ----------------------------------------

let _calcLineIndex = null;
let _calcResources = [];

function bindCalcModal() {
  const modal = document.getElementById('calcModal');
  if (!modal) return;
  document.getElementById('calcModalClose').addEventListener('click', closeCalcModal);
  document.getElementById('calcModalCancel').addEventListener('click', closeCalcModal);
  document.getElementById('calcAddResourceBtn').addEventListener('click', () => addCalcRow());
  document.getElementById('calcApplyBtn').addEventListener('click', applyCalcToLine);
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeCalcModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal.hidden) closeCalcModal();
  });
}

async function openCalcModal(lineIndex) {
  if (!mfEditorState.parsedMf) return;
  const line = mfEditorState.parsedMf.lines[lineIndex];
  if (!line) return;

  _calcLineIndex = lineIndex;

  // Säkerställ att vi har resurs-cache laddad
  if (_resourceCache.length === 0) {
    try {
      const res = await fetch('/api/resources');
      const d = await res.json();
      _resourceCache = d.resources || [];
      _resourceTypes = d.types || {};
    } catch {}
  }

  // Title + sub
  document.getElementById('calcModalTitle').textContent = line.description || '(utan beskrivning)';
  const codeStr = line.ama_code ? `${line.ama_code} · ` : '';
  document.getElementById('calcModalSub').textContent = `${codeStr}${line.quantity ?? '?'} ${line.unit || ''}`;
  document.getElementById('calcLineQuantity').textContent = `${line.quantity ?? '—'} ${line.unit || ''}`;

  // Ladda befintliga resurser från raden, eller börja tom
  _calcResources = Array.isArray(line._resources) ? JSON.parse(JSON.stringify(line._resources)) : [];

  if (_calcResources.length === 0) {
    addCalcRow();
  } else {
    renderCalcRows();
    await recalcCalc();
  }

  document.getElementById('calcModal').hidden = false;
  document.body.style.overflow = 'hidden';
}

function closeCalcModal() {
  document.getElementById('calcModal').hidden = true;
  document.body.style.overflow = '';
  _calcLineIndex = null;
  _calcResources = [];
}

function addCalcRow() {
  _calcResources.push({
    resource_id: '',
    factor: 1,
    spill: 0,
    time: 0,
    quantity: 1,
    cost_per_unit: 0,
  });
  renderCalcRows();
}

function renderCalcRows() {
  const tbody = document.getElementById('calcResourcesBody');
  if (!tbody) return;

  if (_calcResources.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="calc-row-empty">Inga resurser. Klicka "+ Lägg till resurs".</td></tr>';
    return;
  }

  const optionsHtml = _resourceCache.map((r) =>
    `<option value="${escapeAttr(r.id)}" data-cost="${r.cost_per_unit}">${escapeHtml(r.name)} (${escapeHtml(r.unit)})</option>`
  ).join('');

  tbody.innerHTML = _calcResources.map((r, i) => {
    const selectedId = r.resource_id || '';
    const cost = r.cost_per_unit || 0;
    return `
      <tr data-calc-index="${i}">
        <td>
          <select class="calc-cell-select" data-field="resource_id" data-index="${i}">
            <option value="">— Välj resurs —</option>
            ${optionsHtml.replace(`value="${escapeAttr(selectedId)}"`, `value="${escapeAttr(selectedId)}" selected`)}
          </select>
        </td>
        <td class="col-num"><input type="number" step="0.01" class="calc-cell-input num" data-field="factor" data-index="${i}" value="${r.factor}" /></td>
        <td class="col-num"><input type="number" step="0.01" class="calc-cell-input num" data-field="spill" data-index="${i}" value="${r.spill}" /></td>
        <td class="col-num"><input type="number" step="0.01" class="calc-cell-input num" data-field="time" data-index="${i}" value="${r.time}" /></td>
        <td class="col-num"><input type="number" step="0.01" class="calc-cell-input num" data-field="quantity" data-index="${i}" value="${r.quantity}" /></td>
        <td class="col-num"><span class="mono" data-cost-per-unit-for="${i}">${fmtSEK.format(cost)} kr</span></td>
        <td class="col-num"><span class="calc-cost" data-row-cost-for="${i}">—</span></td>
        <td class="col-action">
          <button type="button" class="mf-row-delete" data-action="delete-calc" data-index="${i}" title="Ta bort">✕</button>
        </td>
      </tr>
    `;
  }).join('');

  tbody.querySelectorAll('.calc-cell-input, .calc-cell-select').forEach((el) => {
    el.addEventListener('input', onCalcFieldChange);
    el.addEventListener('change', onCalcFieldChange);
  });
  tbody.querySelectorAll('[data-action="delete-calc"]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.dataset.index, 10);
      _calcResources.splice(idx, 1);
      renderCalcRows();
      recalcCalc();
    });
  });
}

async function onCalcFieldChange(e) {
  const el = e.target;
  const field = el.dataset.field;
  const idx = parseInt(el.dataset.index, 10);
  if (Number.isNaN(idx)) return;
  const r = _calcResources[idx];
  if (!r) return;

  if (field === 'resource_id') {
    r.resource_id = el.value;
    const selected = _resourceCache.find((x) => x.id === el.value);
    r.cost_per_unit = selected ? selected.cost_per_unit : 0;
    const cell = document.querySelector(`[data-cost-per-unit-for="${idx}"]`);
    if (cell) cell.textContent = `${fmtSEK.format(r.cost_per_unit)} kr`;
  } else {
    const raw = el.value.trim();
    r[field] = raw === '' ? 0 : Number(raw);
  }
  await recalcCalc();
}

async function recalcCalc() {
  const line = mfEditorState.parsedMf?.lines[_calcLineIndex];
  const lineQty = line?.quantity;

  try {
    const res = await fetch('/api/resources/calculate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        resources: _calcResources,
        line_quantity: lineQty,
      }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const d = await res.json();

    document.getElementById('calcTotalCost').textContent = `${fmtSEK.format(d.total_cost || 0)} kr`;
    document.getElementById('calcUnitPrice').textContent = d.unit_price != null
      ? `${fmtSEK.format(d.unit_price)} kr / ${line.unit || 'st'}`
      : '—';

    // Uppdatera per-rad kostnad
    (d.resources || []).forEach((er, i) => {
      const cell = document.querySelector(`[data-row-cost-for="${i}"]`);
      if (cell) cell.textContent = `${fmtSEK.format(er.calculated_cost || 0)} kr`;
    });
  } catch (e) {
    console.warn('Calc error:', e);
  }
}

async function applyCalcToLine() {
  if (_calcLineIndex == null || !mfEditorState.parsedMf) return;
  const line = mfEditorState.parsedMf.lines[_calcLineIndex];
  if (!line) return;

  // Slutgiltig beräkning
  try {
    const res = await fetch('/api/resources/calculate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        resources: _calcResources,
        line_quantity: line.quantity,
      }),
    });
    const d = await res.json();

    if (d.unit_price != null) {
      line.unit_price = d.unit_price;
      if (line.quantity != null) {
        line.total_amount = round2(line.quantity * d.unit_price);
      }
    }
    // Spara resurserna på raden så de återanvänds
    line._resources = _calcResources;

    mfEditorState.dirty = true;
    renderMfEditorRows();
    updateMfTotals();
    updateMfDirtyState();
    scheduleAutosave();
  } catch (e) {
    alert(`Fel: ${e.message}`);
    return;
  }

  closeCalcModal();
}

// ---------- GRANSKNINGSVY (AP2) ------------------------------------------

let granskaState = {
  caseId: null,
  stateLabel: '',
  lines: [],
  thresholds: { red: 0.7, yellow: 0.9 },
  pdfDocument: null,
  pdf: null,
  pageNum: 1,
  pageCount: 0,
  scale: 1,
  filter: 'alla',
  selectedLineId: null,
};

async function loadGranska(caseId) {
  granskaState = {
    ...granskaState,
    caseId, lines: [], pdf: null, pdfDocument: null,
    pageNum: 1, pageCount: 0, filter: 'alla', selectedLineId: null,
  };

  document.getElementById('granskaTitle').textContent = 'Laddar …';
  document.getElementById('granskaMeta').textContent = '';
  document.getElementById('granskaRowList').innerHTML = '';
  document.querySelectorAll('.granska-filter').forEach((b) =>
    b.classList.toggle('active', b.dataset.filter === 'alla'));

  bindGranskaOnce();

  try {
    const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}/review`);
    if (!res.ok) throw new Error(res.status === 404 ? 'Anbudet hittades inte' : `HTTP ${res.status}`);
    const d = await res.json();

    granskaState.lines = d.lines || [];
    granskaState.thresholds = d.thresholds || granskaState.thresholds;
    granskaState.pdfDocument = d.pdf_document;
    granskaState.stateLabel = d.state_label || '';

    document.getElementById('granskaTitle').textContent = d.project_name || caseId;
    updateGranskaMeta();
    renderGranskaRows();

    const pane = document.getElementById('granskaPdfPane');
    const layout = document.getElementById('granskaLayout');
    if (d.pdf_document && window.pdfjsLib) {
      pane.hidden = false;
      layout.classList.remove('no-pdf');
      document.getElementById('granskaPdfFilename').textContent = d.pdf_document.filename;
      initGranskaPdf(d.pdf_document.url);
    } else {
      pane.hidden = true;
      layout.classList.add('no-pdf');
    }
  } catch (e) {
    document.getElementById('granskaTitle').textContent = 'Fel';
    document.getElementById('granskaMeta').textContent = e.message;
  }
}

function granskaBucket(l) {
  if (l.reviewed_by_user) return 'granskad';
  const c = l.confidence == null ? 1 : l.confidence;
  if (c < granskaState.thresholds.red) return 'rod';
  if (c < granskaState.thresholds.yellow) return 'gul';
  return 'gron';
}

function updateGranskaMeta() {
  const counts = { rod: 0, gul: 0, gron: 0, granskad: 0 };
  for (const l of granskaState.lines) counts[granskaBucket(l)]++;
  document.getElementById('granskaCounts').textContent =
    `${counts.rod} röda · ${counts.gul} gula · ${counts.gron} gröna · ${counts.granskad} granskade`;
  const parts = [];
  if (granskaState.stateLabel) parts.push(granskaState.stateLabel);
  parts.push(`${granskaState.lines.length} rader`);
  document.getElementById('granskaMeta').textContent = parts.join(' · ');
}

function granskaSourceLabel(l) {
  const src = l.source || {};
  const llm = l.extraction_method === 'llm' ? ' · LLM' : '';
  if (src.page) return `s. ${src.page}${llm}`;
  if (src.sheet) return `${src.sheet} rad ${src.row}${llm}`;
  if (src.row != null) return `rad ${src.row}${llm}`;
  return l.extraction_method === 'llm' ? 'LLM' : '';
}

const _GRANSKA_ORDER = { rod: 0, gul: 1, gron: 2, granskad: 3 };

function renderGranskaRows() {
  const listEl = document.getElementById('granskaRowList');
  if (!listEl) return;

  const sorted = [...granskaState.lines].sort((a, b) => {
    const d = _GRANSKA_ORDER[granskaBucket(a)] - _GRANSKA_ORDER[granskaBucket(b)];
    return d !== 0 ? d : a.position - b.position;
  });
  const visible = granskaState.filter === 'alla'
    ? sorted
    : sorted.filter((l) => granskaBucket(l) === granskaState.filter);

  if (visible.length === 0) {
    listEl.innerHTML = '<div class="empty-state"><p>Inga rader i detta filter.</p></div>';
    return;
  }

  listEl.innerHTML = visible.map((l) => {
    const bucket = granskaBucket(l);
    const conf = l.reviewed_by_user ? '✓' : `${Math.round((l.confidence ?? 1) * 100)}%`;
    const selected = l.id === granskaState.selectedLineId ? ' selected' : '';
    return `
      <div class="granska-row${selected}" data-line-id="${escapeAttr(l.id)}" data-bucket="${bucket}">
        <span class="granska-dot" data-bucket="${bucket}" title="${bucket}"></span>
        <div class="granska-fields">
          <input class="granska-input mono" data-field="ama_code" value="${escapeAttr(l.ama_code || '')}" placeholder="AMA" style="width:92px" />
          <input class="granska-input granska-desc" data-field="description" value="${escapeAttr(l.description || '')}" placeholder="Beskrivning" />
          <input class="granska-input mono" data-field="unit" value="${escapeAttr(l.unit || '')}" placeholder="enh" style="width:54px" />
          <input class="granska-input mono num" data-field="quantity" value="${l.quantity ?? ''}" placeholder="mängd" style="width:76px" />
          <input class="granska-input mono num" data-field="unit_price" value="${l.unit_price ?? ''}" placeholder="à-pris" style="width:84px" />
        </div>
        <div class="granska-rowmeta">
          <span class="granska-conf">${conf}</span>
          <span class="granska-srclabel">${escapeHtml(granskaSourceLabel(l))}</span>
        </div>
        <div class="granska-rowactions">
          <button type="button" class="draft-action primary" data-action="save" hidden>Spara</button>
          ${l.reviewed_by_user
            ? '<span class="granska-reviewed">✓ Granskad</span>'
            : '<button type="button" class="draft-action" data-action="approve">Godkänn</button>'}
        </div>
      </div>
    `;
  }).join('');

  listEl.querySelectorAll('.granska-row').forEach((rowEl) => {
    const lineId = rowEl.dataset.lineId;

    rowEl.addEventListener('click', (e) => {
      if (e.target.closest('input, button')) return;
      granskaState.selectedLineId = lineId;
      listEl.querySelectorAll('.granska-row.selected').forEach((r) => r.classList.remove('selected'));
      rowEl.classList.add('selected');
      const line = granskaState.lines.find((x) => x.id === lineId);
      if (line?.source?.page && granskaState.pdf) {
        granskaShowPage(line.source.page, line.source.bbox);
      }
    });

    rowEl.querySelectorAll('.granska-input').forEach((inp) => {
      inp.addEventListener('input', () => {
        const saveBtn = rowEl.querySelector('[data-action="save"]');
        if (saveBtn) saveBtn.hidden = false;
      });
    });

    rowEl.querySelector('[data-action="save"]')?.addEventListener('click', () => {
      const fields = {};
      rowEl.querySelectorAll('.granska-input').forEach((inp) => {
        fields[inp.dataset.field] = inp.value;
      });
      granskaSaveLine(lineId, fields);
    });

    rowEl.querySelector('[data-action="approve"]')?.addEventListener('click', () => {
      granskaSaveLine(lineId, {});
    });
  });
}

async function granskaSaveLine(lineId, fields) {
  try {
    const res = await fetch(
      `/api/cases/${encodeURIComponent(granskaState.caseId)}/review/lines/${encodeURIComponent(lineId)}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(fields),
      },
    );
    if (!res.ok) {
      const err = await safeJson(res);
      throw new Error(err?.detail || `HTTP ${res.status}`);
    }
    const d = await res.json();
    const idx = granskaState.lines.findIndex((x) => x.id === lineId);
    if (idx >= 0) granskaState.lines[idx] = d.line;
    updateGranskaMeta();
    renderGranskaRows();
  } catch (e) {
    alert(`Kunde inte spara: ${e.message}`);
  }
}

function bindGranskaOnce() {
  const approveBtn = document.getElementById('granskaApproveGreens');
  if (approveBtn && !approveBtn._bound) {
    approveBtn._bound = true;
    approveBtn.addEventListener('click', async () => {
      try {
        const res = await fetch(
          `/api/cases/${encodeURIComponent(granskaState.caseId)}/review/approve`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ min_confidence: granskaState.thresholds.yellow }),
          },
        );
        const d = await res.json();
        if (!res.ok) throw new Error(d?.detail || `HTTP ${res.status}`);
        await loadGranska(granskaState.caseId);
      } catch (e) {
        alert(`Fel: ${e.message}`);
      }
    });
  }

  const completeBtn = document.getElementById('granskaComplete');
  if (completeBtn && !completeBtn._bound) {
    completeBtn._bound = true;
    completeBtn.addEventListener('click', async () => {
      try {
        const res = await fetch(
          `/api/cases/${encodeURIComponent(granskaState.caseId)}/review/complete`,
          { method: 'POST' },
        );
        const d = await safeJson(res);
        if (!res.ok) throw new Error(d?.detail || `HTTP ${res.status}`);
        location.hash = `#/kalkylator/${encodeURIComponent(granskaState.caseId)}`;
      } catch (e) {
        alert(e.message);
      }
    });
  }

  document.querySelectorAll('.granska-filter').forEach((btn) => {
    if (btn._bound) return;
    btn._bound = true;
    btn.addEventListener('click', () => {
      granskaState.filter = btn.dataset.filter;
      document.querySelectorAll('.granska-filter').forEach((b) =>
        b.classList.toggle('active', b === btn));
      renderGranskaRows();
    });
  });

  const prev = document.getElementById('granskaPdfPrev');
  const next = document.getElementById('granskaPdfNext');
  if (prev && !prev._bound) {
    prev._bound = true;
    prev.addEventListener('click', () => granskaShowPage(granskaState.pageNum - 1));
  }
  if (next && !next._bound) {
    next._bound = true;
    next.addEventListener('click', () => granskaShowPage(granskaState.pageNum + 1));
  }
}

let _granskaRenderTask = null;

async function initGranskaPdf(url) {
  try {
    const lib = window.pdfjsLib;
    lib.GlobalWorkerOptions.workerSrc =
      'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
    granskaState.pdf = await lib.getDocument(url).promise;
    granskaState.pageCount = granskaState.pdf.numPages;
    granskaShowPage(1);
  } catch (e) {
    console.warn('PDF kunde inte laddas:', e);
    document.getElementById('granskaPdfPane').hidden = true;
    document.getElementById('granskaLayout').classList.add('no-pdf');
  }
}

async function granskaShowPage(n, bbox) {
  const st = granskaState;
  if (!st.pdf) return;
  n = Math.max(1, Math.min(n, st.pageCount));
  st.pageNum = n;

  const page = await st.pdf.getPage(n);
  const wrap = document.getElementById('granskaPdfWrap');
  const canvas = document.getElementById('granskaPdfCanvas');
  const base = page.getViewport({ scale: 1 });
  const scale = Math.max(0.3, (wrap.clientWidth - 4) / base.width);
  st.scale = scale;
  const viewport = page.getViewport({ scale });
  canvas.width = viewport.width;
  canvas.height = viewport.height;

  if (_granskaRenderTask) {
    try { _granskaRenderTask.cancel(); } catch {}
  }
  _granskaRenderTask = page.render({ canvasContext: canvas.getContext('2d'), viewport });
  try { await _granskaRenderTask.promise; } catch { return; }

  document.getElementById('granskaPdfLabel').textContent = `Sida ${n} / ${st.pageCount}`;

  const hl = document.getElementById('granskaHighlight');
  if (bbox && bbox.length === 4) {
    hl.style.left = `${bbox[0] * scale - 3}px`;
    hl.style.top = `${bbox[1] * scale - 3}px`;
    hl.style.width = `${(bbox[2] - bbox[0]) * scale + 6}px`;
    hl.style.height = `${(bbox[3] - bbox[1]) * scale + 6}px`;
    hl.hidden = false;
    wrap.scrollTop = Math.max(0, bbox[1] * scale - 140);
  } else {
    hl.hidden = true;
  }
}

// ---------- KRAVMATRIS (AP3) ---------------------------------------------

let kravState = {
  caseId: null,
  requirements: [],
  counts: {},
  huvuddelar: {},
  filter: 'alla',
  pdf: null,
  pageNum: 1,
  pageCount: 0,
};

const _KRAV_KIND_LABELS = {
  skall: 'Skall', bor: 'Bör', bilaga: 'Bilaga',
  utvardering: 'Utvärdering', formalia: 'Formalia',
};

async function loadKrav(caseId) {
  kravState = {
    ...kravState,
    caseId, requirements: [], counts: {}, pdf: null,
    pageNum: 1, pageCount: 0, filter: 'alla',
  };

  document.getElementById('kravTitle').textContent = 'Laddar …';
  document.getElementById('kravMeta').textContent = '';
  document.getElementById('kravList').innerHTML = '';
  document.querySelectorAll('[data-kravfilter]').forEach((b) =>
    b.classList.toggle('active', b.dataset.kravfilter === 'alla'));

  bindKravOnce();

  try {
    const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}/krav`);
    if (!res.ok) throw new Error(res.status === 404 ? 'Anbudet hittades inte' : `HTTP ${res.status}`);
    const d = await res.json();

    kravState.requirements = d.requirements || [];
    kravState.counts = d.counts || {};
    kravState.huvuddelar = d.huvuddelar || {};

    document.getElementById('kravTitle').textContent = d.project_name || caseId;
    updateKravMeta();
    renderKravList();

    const pane = document.getElementById('kravPdfPane');
    const layout = document.getElementById('kravLayout');
    if (d.af_document && window.pdfjsLib) {
      pane.hidden = false;
      layout.classList.remove('no-pdf');
      document.getElementById('kravPdfFilename').textContent = d.af_document.filename;
      initKravPdf(d.af_document.url);
    } else {
      pane.hidden = true;
      layout.classList.add('no-pdf');
    }
  } catch (e) {
    document.getElementById('kravTitle').textContent = 'Fel';
    document.getElementById('kravMeta').textContent = e.message;
  }
}

function updateKravMeta() {
  const c = kravState.counts || {};
  const parts = [];
  if (c.skall != null) {
    const kvar = Math.max(0, (c.skall || 0) - (c.skall_answered || 0));
    parts.push(`${c.skall} skall-krav · ${c.skall_answered || 0} besvarade · ${kvar} kvar`);
  }
  if (c.total != null) parts.push(`${c.total} krav totalt`);
  if (c.unverified) parts.push(`⚠ ${c.unverified} ej verifierade`);
  document.getElementById('kravMeta').textContent = parts.join(' · ') || '—';

  const perKind = Object.entries(c.per_kind || {})
    .map(([k, n]) => `${n} ${(_KRAV_KIND_LABELS[k] || k).toLowerCase()}`)
    .join(' · ');
  document.getElementById('kravCounts').textContent = perKind;
}

function recountKrav() {
  const reqs = kravState.requirements;
  const skall = reqs.filter((r) => r.kind === 'skall');
  const per = {};
  reqs.forEach((r) => { per[r.kind] = (per[r.kind] || 0) + 1; });
  kravState.counts = {
    total: reqs.length,
    skall: skall.length,
    skall_answered: skall.filter((r) => r.status !== 'unanswered').length,
    answered: reqs.filter((r) => r.status !== 'unanswered').length,
    unverified: reqs.filter((r) => !((r.source || {}).verified)).length,
    per_kind: per,
  };
}

function kravVisible(r) {
  const f = kravState.filter;
  if (f === 'alla') return true;
  if (f === 'obesvarade') return r.status === 'unanswered';
  return r.kind === f;
}

function renderKravList() {
  const el = document.getElementById('kravList');
  if (!el) return;

  if (kravState.requirements.length === 0) {
    el.innerHTML = '<div class="empty-state"><p>Inga krav extraherade för detta anbud.</p>'
      + '<p class="muted small">Kravmatrisen byggs vid paketanalysen och kräver att Claude är konfigurerat på servern samt att paketet innehåller ett AF-dokument.</p></div>';
    return;
  }

  const reqs = kravState.requirements.filter(kravVisible);
  if (reqs.length === 0) {
    el.innerHTML = '<div class="empty-state"><p>Inga krav i detta filter.</p></div>';
    return;
  }

  // Gruppera per AF-huvuddel
  const groups = new Map();
  for (const r of reqs) {
    const hd = (r.af_code || '').slice(0, 3).toUpperCase();
    const key = kravState.huvuddelar[hd] ? hd : 'OVR';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(r);
  }

  const order = ['AFA', 'AFB', 'AFC', 'AFD', 'AFG', 'AFH', 'AFJ', 'OVR'];
  const html = [];
  for (const key of order) {
    if (!groups.has(key)) continue;
    const label = key === 'OVR' ? 'Övrigt / utan kod' : (kravState.huvuddelar[key] || key);
    html.push(`<h3 class="krav-group-head">${escapeHtml(label)}</h3>`);
    for (const r of groups.get(key)) {
      html.push(renderKravRow(r));
    }
  }
  el.innerHTML = html.join('');
  bindKravRows(el);
}

function renderKravRow(r) {
  const src = r.source || {};
  const verified = !!src.verified;
  return `
    <div class="krav-row" data-req-id="${escapeAttr(r.id)}" data-status="${escapeAttr(r.status)}">
      <span class="krav-kind-chip" data-kind="${escapeAttr(r.kind)}">${escapeHtml(_KRAV_KIND_LABELS[r.kind] || r.kind)}</span>
      <div class="krav-body">
        <div class="krav-code-line">
          ${r.af_code ? `<span class="krav-code">${escapeHtml(r.af_code)}</span>` : ''}
          <span class="krav-verify ${verified ? 'ok' : 'fail'}">${verified
            ? `citat verifierat${src.page ? ' · s. ' + src.page : ''}`
            : '⚠ citat ej verifierat'}</span>
          ${r.response_format ? `<span class="krav-format">${escapeHtml(r.response_format)}</span>` : ''}
          ${r.deadline ? `<span class="krav-deadline">⏱ ${escapeHtml(r.deadline)}</span>` : ''}
        </div>
        <p class="krav-quote">”${escapeHtml(r.text)}”</p>
        ${r.response_format === 'fritext' ? `
        <div class="krav-answer-row">
          <button type="button" class="draft-action" data-action="answer" data-req-id="${escapeAttr(r.id)}">
            ${r.has_answer ? '✎ Redigera svar' : '✦ Generera svar'}
          </button>
          ${r.has_answer ? `<span class="krav-answer-flag${r.answer_gaps ? ' gaps' : ' ok'}">${r.answer_gaps ? '⚠ har [SAKNAS]-luckor' : '✓ svar klart'}</span>` : ''}
        </div>` : ''}
      </div>
      <div class="krav-statuscell">
        <select class="krav-status-select" data-req-id="${escapeAttr(r.id)}">
          <option value="unanswered" ${r.status === 'unanswered' ? 'selected' : ''}>Obesvarad</option>
          <option value="drafted" ${r.status === 'drafted' ? 'selected' : ''}>Utkast</option>
          <option value="answered" ${r.status === 'answered' ? 'selected' : ''}>Besvarad</option>
          <option value="na" ${r.status === 'na' ? 'selected' : ''}>Ej tillämplig</option>
        </select>
      </div>
    </div>
  `;
}

function bindKravRows(el) {
  el.querySelectorAll('.krav-row').forEach((rowEl) => {
    rowEl.addEventListener('click', (e) => {
      if (e.target.closest('select') || e.target.closest('button')) return;
      el.querySelectorAll('.krav-row.selected').forEach((x) => x.classList.remove('selected'));
      rowEl.classList.add('selected');
      const r = kravState.requirements.find((x) => x.id === rowEl.dataset.reqId);
      if (r?.source?.page && kravState.pdf) kravShowPage(r.source.page);
    });
  });

  el.querySelectorAll('[data-action="answer"]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      openAnswerModal(btn.dataset.reqId);
    });
  });

  el.querySelectorAll('.krav-status-select').forEach((sel) => {
    sel.addEventListener('change', async () => {
      const reqId = sel.dataset.reqId;
      try {
        const res = await fetch(
          `/api/cases/${encodeURIComponent(kravState.caseId)}/krav/${encodeURIComponent(reqId)}`,
          {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: sel.value }),
          },
        );
        if (!res.ok) {
          const err = await safeJson(res);
          throw new Error(err?.detail || `HTTP ${res.status}`);
        }
        const d = await res.json();
        const idx = kravState.requirements.findIndex((x) => x.id === reqId);
        if (idx >= 0) kravState.requirements[idx] = d.requirement;
        recountKrav();
        updateKravMeta();
        renderKravList();
      } catch (err) {
        alert(`Kunde inte spara: ${err.message}`);
      }
    });
  });
}

// ---------- SLUTFÖR ANBUD (AP5) -----------------------------------------

const _FLOW_STEPS = [
  { state: 'CALCULATING', label: 'Kalkyl' },
  { state: 'DRAFTING', label: 'Utkast' },
  { state: 'FORMALIA_CHECK', label: 'Formaliakontroll' },
  { state: 'READY', label: 'Klart' },
  { state: 'SUBMITTED', label: 'Inlämnat' },
  { state: 'AWARDED', label: 'Utfall' },
];
const _FLOW_ORDER = ['CALCULATING', 'DRAFTING', 'FORMALIA_CHECK', 'READY', 'SUBMITTED', 'AWARDED', 'LOST'];

let _slutforCase = null;

async function loadSlutfor(caseId) {
  document.getElementById('slutforTitle').textContent = 'Laddar …';
  document.getElementById('slutforFlow').innerHTML = '';
  document.getElementById('slutforChecklist').innerHTML = '';
  document.getElementById('slutforActions').innerHTML = '';
  document.getElementById('slutforGateMeta').textContent = '';

  try {
    const cres = await fetch(`/api/cases/${encodeURIComponent(caseId)}`);
    if (!cres.ok) throw new Error('Anbudet hittades inte');
    const c = await cres.json();
    _slutforCase = c;

    document.getElementById('slutforTitle').textContent = c.project_name || c.source_name || caseId;
    const metaParts = [];
    if (c.document_number) metaParts.push(c.document_number);
    metaParts.push(`status: ${stateLabelOf(c.state)}`);
    document.getElementById('slutforMeta').textContent = metaParts.join(' · ');

    renderSlutforFlow(c.state);

    const gres = await fetch(`/api/cases/${encodeURIComponent(caseId)}/formalia`);
    const gate = await gres.json();
    renderSlutforChecklist(gate);
    renderSlutforActions(caseId, c.state, gate);
  } catch (e) {
    document.getElementById('slutforTitle').textContent = 'Fel';
    document.getElementById('slutforMeta').textContent = e.message;
  }
}

function stateLabelOf(state) {
  const m = { CALCULATING:'Kalkyl', DRAFTING:'Utkast', FORMALIA_CHECK:'Formaliakontroll',
    READY:'Klart att lämna', SUBMITTED:'Inlämnat', AWARDED:'Vunnet', LOST:'Förlorat',
    NEEDS_REVIEW:'Behöver granskning', INTAKE:'Mottaget', EXTRACTING:'Analyserar' };
  return m[state] || state;
}

function renderSlutforFlow(state) {
  const curIdx = _FLOW_ORDER.indexOf(state === 'LOST' ? 'AWARDED' : state);
  const el = document.getElementById('slutforFlow');
  el.innerHTML = _FLOW_STEPS.map((s) => {
    const idx = _FLOW_ORDER.indexOf(s.state);
    let cls = 'flow-step';
    if (idx < curIdx) cls += ' done';
    else if (idx === curIdx) cls += ' current';
    let label = s.label;
    if (s.state === 'AWARDED' && state === 'LOST') label = 'Förlorat';
    if (s.state === 'AWARDED' && state === 'AWARDED') label = 'Vunnet';
    return `<div class="${cls}"><span class="flow-dot"></span><span class="flow-label">${escapeHtml(label)}</span></div>`;
  }).join('<span class="flow-line"></span>');
}

function renderSlutforChecklist(gate) {
  const el = document.getElementById('slutforChecklist');
  document.getElementById('slutforGateMeta').textContent = gate.passed
    ? '✓ alla obligatoriska punkter passerar'
    : `${gate.blocking_count} blockerande punkt${gate.blocking_count === 1 ? '' : 'er'}`;

  el.innerHTML = (gate.items || []).map((it) => {
    const mark = it.passed ? '✓' : (it.required ? '✗' : '!');
    const cls = it.passed ? 'pass' : (it.required ? 'fail' : 'warn');
    return `
      <div class="check-item" data-state="${cls}">
        <span class="check-mark">${mark}</span>
        <div class="check-body">
          <div class="check-label">${escapeHtml(it.label)}${it.required ? '' : ' <span class="check-optional">(valfritt)</span>'}</div>
          <div class="check-detail">${escapeHtml(it.detail)}</div>
        </div>
        ${(!it.passed && it.fix_route) ? `<a class="check-fix" href="${escapeAttr(it.fix_route)}">Åtgärda →</a>` : ''}
      </div>
    `;
  }).join('');
}

function renderSlutforActions(caseId, state, gate) {
  const el = document.getElementById('slutforActions');
  let html = '';

  if (state === 'CALCULATING' || state === 'NEEDS_REVIEW') {
    html = `<button class="btn btn-primary" data-advance="DRAFTING">Gå vidare till utkast →</button>`;
  } else if (state === 'DRAFTING' || state === 'FORMALIA_CHECK') {
    const disabled = gate.passed ? '' : 'disabled';
    html = `<button class="btn btn-primary" id="slutforFinalize" ${disabled}>Markera anbudet klart →</button>`;
    if (!gate.passed) html += `<span class="muted small">Åtgärda de blockerande punkterna ovan först.</span>`;
  } else if (state === 'READY') {
    html = `<button class="btn btn-primary" id="slutforSubmit">Markera som inlämnat →</button>
            <span class="muted small">När du lämnat in anbudet i upphandlingssystemet.</span>`;
  } else if (state === 'SUBMITTED') {
    html = `<span class="slutfor-outcome-label">Registrera utfall:</span>
            <button class="btn btn-primary" data-outcome="won">Vunnet ✓</button>
            <button class="btn btn-ghost" data-outcome="lost">Förlorat</button>`;
  } else if (state === 'AWARDED' || state === 'LOST') {
    html = `<div class="slutfor-done">Anbudet är avslutat: <strong>${escapeHtml(stateLabelOf(state))}</strong>. Priserna ligger i historiken för framtida förslag.</div>`;
  }
  el.innerHTML = html;

  el.querySelector('[data-advance]')?.addEventListener('click', async (e) => {
    await slutforAdvance(caseId, e.target.dataset.advance);
  });
  document.getElementById('slutforFinalize')?.addEventListener('click', () => slutforFinalize(caseId));
  document.getElementById('slutforSubmit')?.addEventListener('click', () => slutforSubmit(caseId));
  el.querySelectorAll('[data-outcome]').forEach((b) =>
    b.addEventListener('click', () => slutforOutcome(caseId, b.dataset.outcome)));
}

async function slutforAdvance(caseId, to) {
  try {
    const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}/advance`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ to }),
    });
    if (!res.ok) { const e = await safeJson(res); throw new Error(e?.detail || `HTTP ${res.status}`); }
    await loadSlutfor(caseId);
  } catch (e) { alert(e.message); }
}

async function slutforFinalize(caseId) {
  try {
    const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}/finalize`, { method: 'POST' });
    const d = await safeJson(res);
    if (res.status === 409) {
      alert(`Kan inte markeras klart: ${d.blocking_count} blockerande punkter kvarstår.`);
      await loadSlutfor(caseId);
      return;
    }
    if (!res.ok) throw new Error(d?.detail || `HTTP ${res.status}`);
    await loadSlutfor(caseId);
  } catch (e) { alert(e.message); }
}

async function slutforSubmit(caseId) {
  if (!confirm('Markera anbudet som inlämnat? Priserna sparas då i historiken.')) return;
  try {
    const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}/submit`, { method: 'POST' });
    if (!res.ok) { const e = await safeJson(res); throw new Error(e?.detail || `HTTP ${res.status}`); }
    await loadSlutfor(caseId);
  } catch (e) { alert(e.message); }
}

async function slutforOutcome(caseId, result) {
  try {
    const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}/outcome`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ result }),
    });
    const d = await safeJson(res);
    if (!res.ok) throw new Error(d?.detail || `HTTP ${res.status}`);
    await loadSlutfor(caseId);
  } catch (e) { alert(e.message); }
}

// ---- AFB-svarsmodal (AP5) ----------------------------------------------

let _answerReqId = null;

function highlightSaknas(text) {
  return escapeHtml(text).replace(/\[SAKNAS:[^\]]*\]/g,
    (m) => `<mark class="saknas-mark">${m}</mark>`);
}

async function openAnswerModal(reqId) {
  _answerReqId = reqId;
  const req = kravState.requirements.find((x) => x.id === reqId);
  const modal = document.getElementById('answerModal');
  document.getElementById('answerModalCode').textContent = req?.af_code ? `AFB-svar · ${req.af_code}` : 'AFB-svar';
  document.getElementById('answerModalQuote').textContent = req ? `”${req.text}”` : '';
  document.getElementById('answerModalText').value = '';
  document.getElementById('answerModalMissing').hidden = true;
  document.getElementById('answerModalSources').textContent = '';
  document.getElementById('answerModalStatus').textContent = 'Hämtar…';
  modal.hidden = false;
  document.body.style.overflow = 'hidden';

  try {
    const res = await fetch(`/api/cases/${encodeURIComponent(kravState.caseId)}/krav/${encodeURIComponent(reqId)}/answer`);
    const d = await res.json();
    document.getElementById('answerModalText').value = d.text || '';
    document.getElementById('answerModalStatus').textContent = d.text ? '' : 'Inget svar än — klicka Generera.';
    updateAnswerGapHint(d.text || '');
  } catch (e) {
    document.getElementById('answerModalStatus').textContent = `Fel: ${e.message}`;
  }
}

function updateAnswerGapHint(text) {
  const gaps = (text.match(/\[SAKNAS:[^\]]*\]/g) || []);
  const box = document.getElementById('answerModalMissing');
  if (gaps.length) {
    box.innerHTML = `<strong>${gaps.length} lucka${gaps.length === 1 ? '' : 'or'} att fylla i:</strong> `
      + gaps.map((g) => escapeHtml(g)).join(' · ');
    box.hidden = false;
  } else {
    box.hidden = true;
  }
}

function closeAnswerModal() {
  document.getElementById('answerModal').hidden = true;
  document.body.style.overflow = '';
  _answerReqId = null;
}

async function generateAnswer() {
  if (!_answerReqId) return;
  const status = document.getElementById('answerModalStatus');
  status.textContent = 'Genererar med Claude…';
  try {
    const res = await fetch(`/api/cases/${encodeURIComponent(kravState.caseId)}/krav/${encodeURIComponent(_answerReqId)}/answer`, { method: 'POST' });
    if (!res.ok) { const e = await safeJson(res); throw new Error(e?.detail || `HTTP ${res.status}`); }
    const d = await res.json();
    document.getElementById('answerModalText').value = d.answer || '';
    updateAnswerGapHint(d.answer || '');
    const src = (d.sources_used || []).length ? `Källor: ${d.sources_used.join(', ')}` : '';
    const lib = d.library_used ? ` · ${d.library_used} tidigare svar använt` : '';
    document.getElementById('answerModalSources').textContent = src + lib;
    status.textContent = 'Genererat';
  } catch (e) {
    status.textContent = `Fel: ${e.message}`;
  }
}

async function saveAnswer(markAnswered) {
  if (!_answerReqId) return;
  const text = document.getElementById('answerModalText').value;
  const status = document.getElementById('answerModalStatus');
  if (!text.trim()) { status.textContent = 'Tomt svar'; return; }
  status.textContent = 'Sparar…';
  try {
    const res = await fetch(`/api/cases/${encodeURIComponent(kravState.caseId)}/krav/${encodeURIComponent(_answerReqId)}/answer`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }),
    });
    if (!res.ok) { const e = await safeJson(res); throw new Error(e?.detail || `HTTP ${res.status}`); }
    const d = await res.json();

    if (markAnswered) {
      if (d.has_gaps && !confirm('Svaret har [SAKNAS]-luckor. Markera som besvarad ändå?')) {
        status.textContent = 'Sparat (ej markerat besvarad)';
        await loadKrav(kravState.caseId);
        return;
      }
      await fetch(`/api/cases/${encodeURIComponent(kravState.caseId)}/krav/${encodeURIComponent(_answerReqId)}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'answered' }),
      });
    } else {
      // Spara → status drafted
      await fetch(`/api/cases/${encodeURIComponent(kravState.caseId)}/krav/${encodeURIComponent(_answerReqId)}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'drafted' }),
      });
    }
    closeAnswerModal();
    await loadKrav(kravState.caseId);
  } catch (e) {
    status.textContent = `Fel: ${e.message}`;
  }
}

function bindAnswerModal() {
  const modal = document.getElementById('answerModal');
  if (!modal) return;
  document.getElementById('answerModalClose').addEventListener('click', closeAnswerModal);
  document.getElementById('answerModalGenerate').addEventListener('click', generateAnswer);
  document.getElementById('answerModalSave').addEventListener('click', () => saveAnswer(false));
  document.getElementById('answerModalAccept').addEventListener('click', () => saveAnswer(true));
  document.getElementById('answerModalText').addEventListener('input', (e) => updateAnswerGapHint(e.target.value));
  modal.addEventListener('click', (e) => { if (e.target === modal) closeAnswerModal(); });
}

function bindKravOnce() {
  document.querySelectorAll('[data-kravfilter]').forEach((btn) => {
    if (btn._bound) return;
    btn._bound = true;
    btn.addEventListener('click', () => {
      kravState.filter = btn.dataset.kravfilter;
      document.querySelectorAll('[data-kravfilter]').forEach((b) =>
        b.classList.toggle('active', b === btn));
      renderKravList();
    });
  });

  const kalkBtn = document.getElementById('kravKalkylatorBtn');
  if (kalkBtn && !kalkBtn._bound) {
    kalkBtn._bound = true;
    kalkBtn.addEventListener('click', () => {
      if (kravState.caseId) location.hash = `#/kalkylator/${encodeURIComponent(kravState.caseId)}`;
    });
  }

  const prev = document.getElementById('kravPdfPrev');
  const next = document.getElementById('kravPdfNext');
  if (prev && !prev._bound) {
    prev._bound = true;
    prev.addEventListener('click', () => kravShowPage(kravState.pageNum - 1));
  }
  if (next && !next._bound) {
    next._bound = true;
    next.addEventListener('click', () => kravShowPage(kravState.pageNum + 1));
  }
}

let _kravRenderTask = null;

async function initKravPdf(url) {
  try {
    const lib = window.pdfjsLib;
    lib.GlobalWorkerOptions.workerSrc =
      'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
    kravState.pdf = await lib.getDocument(url).promise;
    kravState.pageCount = kravState.pdf.numPages;
    kravShowPage(1);
  } catch (e) {
    console.warn('AF-PDF kunde inte laddas:', e);
    document.getElementById('kravPdfPane').hidden = true;
    document.getElementById('kravLayout').classList.add('no-pdf');
  }
}

async function kravShowPage(n) {
  const st = kravState;
  if (!st.pdf) return;
  n = Math.max(1, Math.min(n, st.pageCount));
  st.pageNum = n;

  const page = await st.pdf.getPage(n);
  const wrap = document.getElementById('kravPdfWrap');
  const canvas = document.getElementById('kravPdfCanvas');
  const base = page.getViewport({ scale: 1 });
  const scale = Math.max(0.3, (wrap.clientWidth - 4) / base.width);
  const viewport = page.getViewport({ scale });
  canvas.width = viewport.width;
  canvas.height = viewport.height;

  if (_kravRenderTask) {
    try { _kravRenderTask.cancel(); } catch {}
  }
  _kravRenderTask = page.render({ canvasContext: canvas.getContext('2d'), viewport });
  try { await _kravRenderTask.promise; } catch { return; }

  document.getElementById('kravPdfLabel').textContent = `Sida ${n} / ${st.pageCount}`;
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
