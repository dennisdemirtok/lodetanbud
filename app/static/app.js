// Lodet — frontend logik
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInput');
const browseBtn = document.getElementById('browseBtn');
const exampleBtn = document.getElementById('exampleBtn');
const statusEl = document.getElementById('status');
const resultsEl = document.getElementById('results');
const downloadBtn = document.getElementById('downloadBtn');

let lastUploadedFile = null;
let lastWasExample = false;

const fmtSEK = new Intl.NumberFormat('sv-SE', { style: 'decimal', maximumFractionDigits: 0 });
const fmtNum = new Intl.NumberFormat('sv-SE');

function showStatus(msg, kind = 'info') {
  statusEl.textContent = msg;
  statusEl.className = `status ${kind}`;
  statusEl.hidden = false;
}

function clearStatus() {
  statusEl.hidden = true;
  statusEl.textContent = '';
}

function setBusy(busy) {
  dropzone.style.pointerEvents = busy ? 'none' : '';
  dropzone.style.opacity = busy ? '0.6' : '1';
  exampleBtn.disabled = busy;
}

dropzone.addEventListener('click', (e) => {
  if (e.target === browseBtn) return;
  fileInput.click();
});
dropzone.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    fileInput.click();
  }
});
browseBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  fileInput.click();
});

['dragenter', 'dragover'].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  })
);
['dragleave', 'dragend', 'drop'].forEach((ev) =>
  dropzone.addEventListener(ev, () => dropzone.classList.remove('dragover'))
);

dropzone.addEventListener('drop', (e) => {
  e.preventDefault();
  const file = e.dataTransfer?.files?.[0];
  if (file) handleFile(file);
});

fileInput.addEventListener('change', (e) => {
  const file = e.target.files?.[0];
  if (file) handleFile(file);
});

exampleBtn.addEventListener('click', loadExample);
downloadBtn.addEventListener('click', downloadExcel);

async function handleFile(file) {
  if (!file.name.toLowerCase().endsWith('.csv')) {
    showStatus('Lodet stödjer endast .csv i denna version. Konvertera Excel-fil och försök igen.', 'error');
    return;
  }
  lastUploadedFile = file;
  lastWasExample = false;

  setBusy(true);
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
    renderResults(data);
    clearStatus();
  } catch (e) {
    showStatus(`Kunde inte parsa filen: ${e.message}`, 'error');
    resultsEl.hidden = true;
  } finally {
    setBusy(false);
  }
}

async function loadExample() {
  setBusy(true);
  showStatus('Hämtar Westcon-demo …', 'loading');
  lastUploadedFile = null;
  lastWasExample = true;
  try {
    const res = await fetch('/api/example');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderResults(data);
    clearStatus();
  } catch (e) {
    showStatus(`Kunde inte hämta demo-data: ${e.message}`, 'error');
  } finally {
    setBusy(false);
  }
}

async function downloadExcel() {
  downloadBtn.disabled = true;
  const originalText = downloadBtn.textContent;
  downloadBtn.textContent = 'Genererar Excel …';

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

    if (!res.ok) {
      const err = await safeJson(res);
      throw new Error(err?.detail || `HTTP ${res.status}`);
    }
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
    downloadBtn.disabled = false;
    downloadBtn.textContent = originalText;
  }
}

function renderResults(payload) {
  const { summary, data } = payload;
  const meta = data.metadata;

  document.getElementById('resultProject').textContent = meta.project_name || 'Okänt projekt';
  const metaParts = [];
  if (meta.document_number) metaParts.push(meta.document_number);
  if (meta.date) metaParts.push(meta.date);
  if (meta.handlaggare) metaParts.push(`Handläggare: ${meta.handlaggare}`);
  if (meta.uppdragsnummer) metaParts.push(`Uppdrag: ${meta.uppdragsnummer}`);
  document.getElementById('resultMeta').textContent = metaParts.join(' · ');

  const totalDisplay = meta.total_amount_sek
    ? `${fmtSEK.format(meta.total_amount_sek)} kr`
    : '—';
  document.getElementById('statTotal').textContent = totalDisplay;
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
      const sectionRow = document.createElement('tr');
      sectionRow.className = 'section-row';
      sectionRow.innerHTML = `<td colspan="6">${escapeHtml(sectionLabel(sectionLetter))}</td>`;
      tbody.appendChild(sectionRow);
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

  resultsEl.hidden = false;
  resultsEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function sectionLabel(letter) {
  const map = {
    B: 'B — Förarbeten, hjälparbeten, saneringsarbeten',
    C: 'C — Mark- och anläggningsarbeten',
    D: 'D — Markförstärkningar och bärande konstruktioner',
    E: 'E — Konstruktionsarbeten',
    S: 'S — Apparater, ledningar m.m. i el- och telesystem',
    Y: 'Y — Märkning, kontroll, dokumentation',
  };
  return map[letter] || `${letter} — Övrigt`;
}

function formatNum(v) {
  if (v == null) return '—';
  return fmtNum.format(v);
}

function formatPrice(v) {
  if (v == null) return '—';
  return `${fmtSEK.format(v)} kr`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[c]);
}

async function safeJson(res) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}
