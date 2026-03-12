/**
 * LeadRadar — app.js
 * All settings (API keys, backend URL, provider) are stored in localStorage
 * and sent to the backend with each request so users never have to touch .env files.
 */

// ─── STORAGE KEYS ────────────────────────────────────────────────────────────
const KEYS = {
  backend:  'lr_backend_url',
  serp:     'lr_serp_key',
  openai:   'lr_openai_key',
  gemini:   'lr_gemini_key',
  claude:   'lr_claude_key',
  provider: 'lr_provider',
  keywords: 'lr_keywords',
  scanner:  'lr_scanner',
  highonly: 'lr_highonly',
};

// ─── STATE ───────────────────────────────────────────────────────────────────
let currentProvider   = 'openai';
let allDailyLeads     = [];
let currentDailyTab   = 'all';

// ─── INIT ────────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  loadSettingsIntoUI();
  updateStatusDots();
  updateProviderChips();
  loadDailyCount();
});

// ─── NAVIGATION ──────────────────────────────────────────────────────────────
const PAGE_TITLES = {
  search:   ['Search',      'Find buyer-intent leads in real time'],
  daily:    ['Daily Leads', 'Leads stored by the background scanner'],
  settings: ['Settings',    'Configure API keys and scanner preferences'],
};

function navigate(pageId, clickedEl) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  document.getElementById('page-' + pageId).classList.add('active');
  if (clickedEl) clickedEl.classList.add('active');

  const [title, sub] = PAGE_TITLES[pageId] || ['', ''];
  document.getElementById('topbarTitle').childNodes[0].textContent = title + ' ';
  document.getElementById('topbarSub').textContent = sub;

  if (pageId === 'daily') loadDailyLeads();
}

// ─── PROVIDER SELECTION ───────────────────────────────────────────────────────
function selectProvider(p) {
  const keys = getSettings();
  const providerKey = p === 'openai' ? keys.openai : p === 'gemini' ? keys.gemini : keys.claude;

  if (!providerKey) {
    showError('searchError', `No ${p.toUpperCase()} API key configured. Go to Settings to add it.`);
    return;
  }

  currentProvider = p;
  updateProviderChips();
  localStorage.setItem(KEYS.provider, p);
}

function updateProviderChips() {
  const keys = getSettings();
  ['openai', 'gemini', 'claude'].forEach(p => {
    const chip = document.getElementById('chip-' + p);
    if (!chip) return;
    chip.classList.remove('selected', 'locked');
    const hasKey = p === 'openai' ? !!keys.openai : p === 'gemini' ? !!keys.gemini : !!keys.claude;
    if (!hasKey) chip.classList.add('locked');
    if (p === currentProvider) chip.classList.add('selected');
  });
}

// ─── SETTINGS ────────────────────────────────────────────────────────────────
function getSettings() {
  return {
    backend:  localStorage.getItem(KEYS.backend)  || '',
    serp:     localStorage.getItem(KEYS.serp)     || '',
    openai:   localStorage.getItem(KEYS.openai)   || '',
    gemini:   localStorage.getItem(KEYS.gemini)   || '',
    claude:   localStorage.getItem(KEYS.claude)   || '',
    provider: localStorage.getItem(KEYS.provider) || 'openai',
    keywords: localStorage.getItem(KEYS.keywords) || '',
    scanner:  localStorage.getItem(KEYS.scanner)  !== 'false',
    highonly: localStorage.getItem(KEYS.highonly)  === 'true',
  };
}

function loadSettingsIntoUI() {
  const s = getSettings();
  const el = id => document.getElementById(id);

  el('set-backend').value  = s.backend;
  el('set-serp').value     = s.serp    ? mask(s.serp)    : '';
  el('set-openai').value   = s.openai  ? mask(s.openai)  : '';
  el('set-gemini').value   = s.gemini  ? mask(s.gemini)  : '';
  el('set-claude').value   = s.claude  ? mask(s.claude)  : '';
  el('set-keywords').value = s.keywords;
  el('set-scanner').checked  = s.scanner;
  el('set-highonly').checked = s.highonly;
  el('set-defaultprovider').value = s.provider;

  currentProvider = s.provider;
  updateKeyStatuses(s);
}

function saveSettings() {
  const el = id => document.getElementById(id);

  // Only save key if it's not a masked placeholder (doesn't start with ••)
  const saveKey = (storageKey, inputId) => {
    const val = el(inputId).value.trim();
    if (val && !val.startsWith('••')) {
      localStorage.setItem(storageKey, val);
    }
    // If empty, clear it
    if (!val) localStorage.removeItem(storageKey);
  };

  const backendVal = el('set-backend').value.trim();
  if (backendVal) localStorage.setItem(KEYS.backend, backendVal.replace(/\/$/, ''));
  else localStorage.removeItem(KEYS.backend);

  saveKey(KEYS.serp,    'set-serp');
  saveKey(KEYS.openai,  'set-openai');
  saveKey(KEYS.gemini,  'set-gemini');
  saveKey(KEYS.claude,  'set-claude');

  localStorage.setItem(KEYS.keywords, el('set-keywords').value.trim());
  localStorage.setItem(KEYS.scanner,  el('set-scanner').checked);
  localStorage.setItem(KEYS.highonly, el('set-highonly').checked);
  localStorage.setItem(KEYS.provider, el('set-defaultprovider').value);
  currentProvider = el('set-defaultprovider').value;

  // Refresh UI
  const s = getSettings();
  updateKeyStatuses(s);
  updateStatusDots();
  updateProviderChips();

  // Show toast
  const toast = document.getElementById('saveToast');
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 2500);
}

function clearAllKeys() {
  if (!confirm('Clear all API keys and settings?')) return;
  Object.values(KEYS).forEach(k => localStorage.removeItem(k));
  loadSettingsIntoUI();
  updateStatusDots();
  updateProviderChips();
}

function updateKeyStatuses(s) {
  const setStatus = (id, hasValue) => {
    const el = document.getElementById('status-' + id);
    if (!el) return;
    el.className = 'key-status ' + (hasValue ? 'set' : 'unset');
    el.innerHTML = `<span class="dot"></span>${hasValue ? 'Configured ✓' : 'Not configured'}`;
  };
  setStatus('serp',   !!s.serp);
  setStatus('openai', !!s.openai);
  setStatus('gemini', !!s.gemini);
  setStatus('claude', !!s.claude);
}

function updateStatusDots() {
  const s = getSettings();
  const setDot = (id, on) => {
    const el = document.getElementById('dot-' + id);
    if (el) { el.classList.toggle('on', on); el.classList.toggle('off', !on); }
  };
  setDot('serp',    !!s.serp);
  setDot('openai',  !!s.openai);
  setDot('gemini',  !!s.gemini);
  setDot('claude',  !!s.claude);
  setDot('backend', !!s.backend);
}

function toggleReveal(inputId, btn) {
  const input = document.getElementById(inputId);
  const isHidden = input.type === 'password';
  input.type = isHidden ? 'text' : 'password';
  // If the value is masked, clear it so user can type a real key
  if (isHidden && input.value.startsWith('••')) input.value = '';
  btn.textContent = isHidden ? '🔒' : '👁';
}

function mask(val) {
  if (!val || val.length < 8) return val;
  return val.slice(0, 4) + '••••••••••••' + val.slice(-4);
}

async function testBackend() {
  const url = document.getElementById('set-backend').value.trim().replace(/\/$/, '');
  if (!url) { alert('Please enter a backend URL first.'); return; }

  try {
    const r = await fetch(url + '/', { signal: AbortSignal.timeout(8000) });
    const data = await r.json();
    alert('✅ Backend connected!\n' + JSON.stringify(data));
    localStorage.setItem(KEYS.backend, url);
    updateStatusDots();
  } catch (e) {
    alert('❌ Could not connect: ' + e.message + '\n\nIf on Render free tier, it may be sleeping. Try again in 30s.');
  }
}

// ─── SEARCH ──────────────────────────────────────────────────────────────────
async function doSearch() {
  const keyword = document.getElementById('keyword').value.trim();
  const s = getSettings();

  hideError('searchError');

  if (!keyword) { showError('searchError', 'Please enter a keyword to search.'); return; }
  if (!s.backend) { showError('searchError', 'No backend URL set. Go to Settings and add your Render URL.'); return; }
  if (!s.serp)    { showError('searchError', 'SerpAPI key missing. Go to Settings to add it.'); return; }

  const providerKey = currentProvider === 'openai' ? s.openai
                    : currentProvider === 'gemini'  ? s.gemini
                    : s.claude;

  if (!providerKey) {
    showError('searchError', `No API key for ${currentProvider}. Go to Settings to configure it.`);
    return;
  }

  // Update UI to loading
  const btn = document.getElementById('searchBtn');
  btn.disabled = true;
  btn.textContent = 'Scanning…';
  document.getElementById('statsRow').style.display = 'none';
  document.getElementById('searchResults').innerHTML = `
    <div class="loading-state">
      <div class="pulse-ring"></div>
      <p>AI is scanning the web for buyers…</p>
      <p class="loading-sub">Using ${providerKey ? currentProvider.toUpperCase() : 'AI'} · SerpAPI</p>
    </div>`;

  try {
    const params = new URLSearchParams({
      keyword,
      provider:     currentProvider,
      provider_key: providerKey,
      serp_key:     s.serp,
    });

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 90000);

    const res = await fetch(`${s.backend}/search?${params}`, { signal: controller.signal });
    clearTimeout(timeout);

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${res.status}`);
    }

    const data = await res.json();

    // Stats
    const high = data.filter(l => l.intent_score >= 8).length;
    const avg  = data.length ? (data.reduce((a, l) => a + l.intent_score, 0) / data.length).toFixed(1) : '—';
    document.getElementById('statTotal').textContent = data.length;
    document.getElementById('statHigh').textContent  = high;
    document.getElementById('statAvg').textContent   = avg;
    document.getElementById('statsRow').style.display = '';

    renderLeads(data, 'searchResults', currentProvider);

  } catch (e) {
    const msg = e.name === 'AbortError'
      ? 'Request timed out. Render free tier may be waking up — try again in 30s.'
      : e.message;
    showError('searchError', msg);
    document.getElementById('searchResults').innerHTML = '';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Find Leads';
  }
}

// ─── DAILY LEADS ──────────────────────────────────────────────────────────────
async function loadDailyLeads() {
  const s = getSettings();
  const container = document.getElementById('dailyResults');
  hideError('dailyError');

  if (!s.backend) {
    container.innerHTML = '<div class="empty-state"><span class="empty-icon">🔌</span><p>Add your backend URL in Settings first.</p></div>';
    return;
  }

  container.innerHTML = '<div class="loading-state"><div class="pulse-ring"></div><p>Loading stored leads…</p></div>';

  try {
    const res = await fetch(`${s.backend}/daily-leads`, { signal: AbortSignal.timeout(15000) });
    if (!res.ok) throw new Error(`Server error ${res.status}`);
    const data = await res.json();

    allDailyLeads = data.map(r => ({
      post_text:    r.post,
      post_url:     r.url,
      intent_score: r.intent,
      name:         'Stored Lead',
    }));

    document.getElementById('dailyBadge').textContent = allDailyLeads.length;
    renderDailyTab();

  } catch (e) {
    showError('dailyError', e.message);
    container.innerHTML = '';
  }
}

async function loadDailyCount() {
  const s = getSettings();
  if (!s.backend) return;
  try {
    const res = await fetch(`${s.backend}/daily-leads`, { signal: AbortSignal.timeout(8000) });
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById('dailyBadge').textContent = data.length;
  } catch { /* silent */ }
}

function switchDailyTab(tab, btn) {
  currentDailyTab = tab;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderDailyTab();
}

function renderDailyTab() {
  const leads = currentDailyTab === 'high'
    ? allDailyLeads.filter(l => l.intent_score >= 8)
    : allDailyLeads;
  renderLeads(leads, 'dailyResults', 'stored');
}

// ─── LEAD RENDERING ───────────────────────────────────────────────────────────
function renderLeads(leads, containerId, providerLabel) {
  const container = document.getElementById(containerId);

  if (!leads || leads.length === 0) {
    container.innerHTML = `<div class="empty-state"><span class="empty-icon">🔍</span><p>No buyer-intent leads found. Try a different keyword or check your API keys.</p></div>`;
    return;
  }

  // Sort by intent desc
  const sorted = [...leads].sort((a, b) => b.intent_score - a.intent_score);

  let html = `
    <div class="leads-header">
      <div class="leads-title">${sorted.length} Leads Found</div>
    </div>`;

  sorted.forEach(lead => {
    const text  = lead.post_text || '(no text)';
    const url   = lead.post_url || '#';
    const score = parseFloat(lead.intent_score) || 0;
    const name  = lead.name || 'Lead';

    const tier   = score >= 8 ? 'h' : score >= 6 ? 'm' : 'l';
    const pct    = Math.round((score / 10) * 100);
    const source = extractDomain(url);

    html += `
      <div class="lead-card ${score >= 8 ? 'high' : ''}">
        <div class="lead-top">
          <span class="lead-source">${source}</span>
          <div class="score-group">
            <div class="score-bar"><div class="score-fill ${tier}" style="width:${pct}%"></div></div>
            <span class="score-num ${tier}">${score.toFixed(1)}</span>
          </div>
        </div>
        <p class="lead-text">${escHtml(text)}</p>
        <div class="lead-footer">
          <a class="lead-link" href="${escHtml(url)}" target="_blank" rel="noopener">View post →</a>
          <span class="provider-tag">${escHtml(providerLabel || 'ai')}</span>
        </div>
      </div>`;
  });

  container.innerHTML = html;
}

// ─── HELPERS ─────────────────────────────────────────────────────────────────
function showError(id, msg) {
  const el = document.getElementById(id);
  if (!el) return;
  el.style.display = 'block';
  el.textContent   = '⚠ ' + msg;
}

function hideError(id) {
  const el = document.getElementById(id);
  if (el) el.style.display = 'none';
}

function extractDomain(url) {
  try { return new URL(url).hostname.replace('www.', ''); }
  catch { return 'unknown'; }
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
