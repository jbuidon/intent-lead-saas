/**
 * LeadRadar — app.js v3
 * New in this version:
 *  - Stop button cancels streaming search mid-way (no wasted credits)
 *  - Leads appear in real time as they stream in (SSE)
 *  - Progress bar shows queries completed / total
 *  - Facebook Groups tab with Graph API token support
 */

// ─── STORAGE KEYS ────────────────────────────────────────────────────────────
const KEYS = {
  backend:    'lr_backend_url',
  serp:       'lr_serp_key',
  openai:     'lr_openai_key',
  gemini:     'lr_gemini_key',
  claude:     'lr_claude_key',
  provider:   'lr_provider',
  keywords:   'lr_keywords',
  scanner:    'lr_scanner',
  highonly:   'lr_highonly',
  fbtoken:    'lr_fb_token',
  fbgroups:   'lr_fb_groups',
};

// ─── STATE ───────────────────────────────────────────────────────────────────
let currentProvider = 'openai';
let allDailyLeads   = [];
let currentDailyTab = 'all';
let activeEventSource = null;   // holds the SSE connection so we can stop it
let searchLeads = [];           // leads collected during current search
let isSearching = false;

// ─── INIT ────────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  loadSettingsIntoUI();
  updateStatusDots();
  updateProviderChips();
  loadDailyCount();
});

// ─── NAVIGATION ──────────────────────────────────────────────────────────────
const PAGE_TITLES = {
  search:   ['Search',          'Find buyer-intent leads in real time'],
  facebook: ['Facebook Groups', 'Scan groups you are a member of'],
  daily:    ['Daily Leads',     'Leads stored by the background scanner'],
  settings: ['Settings',        'Configure API keys and scanner preferences'],
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

// ─── PROVIDER CHIPS ──────────────────────────────────────────────────────────
function selectProvider(p) {
  const keys = getSettings();
  const key = p === 'openai' ? keys.openai : p === 'gemini' ? keys.gemini : keys.claude;
  if (!key) {
    showError('searchError', `No ${p.toUpperCase()} key configured. Go to ⚙ Settings.`);
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
    fbtoken:  localStorage.getItem(KEYS.fbtoken)  || '',
    fbgroups: localStorage.getItem(KEYS.fbgroups) || '',
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
  el('set-fbtoken').value  = s.fbtoken  ? mask(s.fbtoken)  : '';
  el('set-fbgroups').value = s.fbgroups || '';
  currentProvider = s.provider;
  updateKeyStatuses(s);
}

function saveSettings() {
  const el = id => document.getElementById(id);
  const saveKey = (storageKey, inputId) => {
    const val = el(inputId).value.trim();
    if (val && !val.startsWith('••')) localStorage.setItem(storageKey, val);
    if (!val) localStorage.removeItem(storageKey);
  };
  const backendVal = el('set-backend').value.trim();
  if (backendVal) localStorage.setItem(KEYS.backend, backendVal.replace(/\/$/, ''));
  else localStorage.removeItem(KEYS.backend);
  saveKey(KEYS.serp,    'set-serp');
  saveKey(KEYS.openai,  'set-openai');
  saveKey(KEYS.gemini,  'set-gemini');
  saveKey(KEYS.claude,  'set-claude');
  saveKey(KEYS.fbtoken, 'set-fbtoken');
  localStorage.setItem(KEYS.keywords, el('set-keywords').value.trim());
  localStorage.setItem(KEYS.scanner,  el('set-scanner').checked);
  localStorage.setItem(KEYS.highonly, el('set-highonly').checked);
  localStorage.setItem(KEYS.provider, el('set-defaultprovider').value);
  localStorage.setItem(KEYS.fbgroups, el('set-fbgroups').value.trim());
  currentProvider = el('set-defaultprovider').value;
  const s = getSettings();
  updateKeyStatuses(s);
  updateStatusDots();
  updateProviderChips();
  // Sync FB groups textarea in FB page too
  const fbGroupsEl = document.getElementById('fb-groups-input');
  if (fbGroupsEl) fbGroupsEl.value = s.fbgroups;
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
  const set = (id, has) => {
    const el = document.getElementById('status-' + id);
    if (!el) return;
    el.className = 'key-status ' + (has ? 'set' : 'unset');
    el.innerHTML = `<span class="dot"></span>${has ? 'Configured ✓' : 'Not configured'}`;
  };
  set('serp',    !!s.serp);
  set('openai',  !!s.openai);
  set('gemini',  !!s.gemini);
  set('claude',  !!s.claude);
  set('fbtoken', !!s.fbtoken);
}

function updateStatusDots() {
  const s = getSettings();
  const dot = (id, on) => {
    const el = document.getElementById('dot-' + id);
    if (el) { el.classList.toggle('on', on); el.classList.toggle('off', !on); }
  };
  dot('serp',    !!s.serp);
  dot('openai',  !!s.openai);
  dot('gemini',  !!s.gemini);
  dot('claude',  !!s.claude);
  dot('backend', !!s.backend);
  dot('fb',      !!s.fbtoken);
}

function toggleReveal(inputId, btn) {
  const input = document.getElementById(inputId);
  const isHidden = input.type === 'password';
  input.type = isHidden ? 'text' : 'password';
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
    const r = await fetch(url + '/', { signal: AbortSignal.timeout(10000) });
    const data = await r.json();
    alert('✅ Backend connected!\n' + JSON.stringify(data));
    localStorage.setItem(KEYS.backend, url);
    updateStatusDots();
  } catch (e) {
    alert('❌ Could not connect: ' + e.message + '\n\nRender free tier may be sleeping. Try again in 30s.');
  }
}

// ─── SEARCH WITH STOP BUTTON (SSE streaming) ─────────────────────────────────
async function doSearch() {
  const keyword = document.getElementById('keyword').value.trim();
  const s = getSettings();
  hideError('searchError');

  if (!keyword)   { showError('searchError', 'Please enter a keyword.'); return; }
  if (!s.backend) { showError('searchError', 'No backend URL. Add it in ⚙ Settings.'); return; }
  if (!s.serp)    { showError('searchError', 'SerpAPI key missing. Add it in ⚙ Settings.'); return; }
  const providerKey = currentProvider === 'openai' ? s.openai
                    : currentProvider === 'gemini'  ? s.gemini : s.claude;
  if (!providerKey) {
    showError('searchError', `No ${currentProvider} API key. Add it in ⚙ Settings.`);
    return;
  }

  // Reset state — start fresh search but keep old leads visible until new ones arrive
  searchLeads = [];
  isSearching = true;
  setSearchUI('searching');

  const minScore = parseFloat(document.getElementById('minScoreVal')?.textContent || '6');

  // ── Build params — include FB groups if token + groups are configured ──
  const params = new URLSearchParams({
    keyword,
    provider:     currentProvider,
    provider_key: providerKey,
    serp_key:     s.serp,
    min_score:    minScore,
  });

  // Pass FB token and group URLs if available — backend will scan them too
  if (s.fbtoken && s.fbgroups) {
    params.set('fb_token',   s.fbtoken);
    // fbgroups is stored as newline-separated, backend expects comma-separated
    const groupUrls = s.fbgroups.split('\n').map(u => u.trim()).filter(Boolean).join(',');
    if (groupUrls) params.set('group_urls', groupUrls);
  }

  // Close any existing stream
  if (activeEventSource) { activeEventSource.close(); activeEventSource = null; }

  // Show FB groups notice if they're included
  if (s.fbtoken && s.fbgroups) {
    const groupCount = s.fbgroups.split('\n').filter(u => u.trim()).length;
    const note = document.getElementById('stopNote');
    if (note) {
      note.textContent = `🔍 Searching web + ${groupCount} Facebook group${groupCount !== 1 ? 's' : ''} for "${keyword}"`;
      note.style.display = 'block';
    }
  }

  // Open SSE stream
  activeEventSource = new EventSource(`${s.backend}/search?${params}`);

  activeEventSource.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);

      if (msg.type === 'lead') {
        searchLeads.push(msg.data);
        appendLead(msg.data, 'searchResults', currentProvider);
        updateSearchStats();
        saveSearchLeads();
      }

      if (msg.type === 'progress') {
        updateProgress(msg.current, msg.total, msg.message);
      }

      if (msg.type === 'done') {
        stopSearch(false); // natural completion, not user-stopped
      }

      if (msg.type === 'error') {
        console.warn('Stream error event:', msg.message);
        // Don't stop — just log it and keep going
      }

    } catch (e) {
      console.error('SSE parse error:', e);
    }
  };

  activeEventSource.onerror = () => {
    // SSE auto-reconnects on error; only stop if we're done
    if (!isSearching) return;
    stopSearch(false);
    if (searchLeads.length === 0) {
      showError('searchError', 'Connection lost. Check your backend URL and try again.');
    }
  };
}

function stopSearch(userStopped = true) {
  if (activeEventSource) {
    activeEventSource.close();
    activeEventSource = null;
  }
  isSearching = false;
  setSearchUI('idle');

  if (userStopped) {
    // Show how many leads were found before stopping
    const note = document.getElementById('stopNote');
    if (note) {
      note.textContent = `⏹ Stopped. ${searchLeads.length} lead${searchLeads.length !== 1 ? 's' : ''} collected.`;
      note.style.display = 'block';
    }
  }

  if (searchLeads.length === 0 && !userStopped) {
    document.getElementById('searchResults').innerHTML =
      `<div class="empty-state"><span class="empty-icon">🔍</span>
       <p>No buyer-intent leads found for this keyword. Try something more specific.</p></div>`;
  }
}

function setSearchUI(state) {
  const searchBtn = document.getElementById('searchBtn');
  const stopBtn   = document.getElementById('stopBtn');
  const progress  = document.getElementById('progressWrap');
  const stopNote  = document.getElementById('stopNote');

  if (state === 'searching') {
    searchBtn.disabled = true;
    searchBtn.textContent = 'Scanning…';
    stopBtn.style.display = 'inline-flex';
    progress.style.display = 'block';
    if (stopNote) stopNote.style.display = 'none';
    document.getElementById('statsRow').style.display = 'none';
    // Only show loading if no previous results — otherwise keep old results visible
    const existing = document.getElementById('searchResults');
    if (!existing || existing.querySelector('.loading-state, .empty-state')) {
      document.getElementById('searchResults').innerHTML =
        `<div class="loading-state">
          <div class="pulse-ring"></div>
          <p>Scanning for buyers… leads appear here in real time.</p>
          <p class="loading-sub">Sources: Reddit → RSS feeds → DuckDuckGo → SerpAPI (fallback)</p>
          <p class="loading-sub" style="margin-top:4px">Click ⏹ Stop anytime to cancel</p>
        </div>`;
    }
  } else {
    searchBtn.disabled = false;
    searchBtn.textContent = 'Find Leads';
    stopBtn.style.display = 'none';
    progress.style.display = 'none';
    if (searchLeads.length > 0) {
      document.getElementById('statsRow').style.display = '';
      showClearBtn(true);
    }
  }
}

// ─── LEAD PERSISTENCE (localStorage) ────────────────────────────────────────

const LEADS_STORAGE_KEY = 'lr_search_leads';

function saveSearchLeads() {
  try {
    localStorage.setItem(LEADS_STORAGE_KEY, JSON.stringify(searchLeads));
  } catch(e) { console.warn('Could not save leads to localStorage:', e); }
}

function loadStoredLeads() {
  try {
    const raw = localStorage.getItem(LEADS_STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) || [];
  } catch(e) { return []; }
}

function clearSearchLeads() {
  searchLeads = [];
  try { localStorage.removeItem(LEADS_STORAGE_KEY); } catch(e) {}
  document.getElementById('searchResults').innerHTML =
    `<div class="empty-state"><span class="empty-icon">🔍</span>
     <p>Results cleared. Enter a keyword above to find new leads.</p></div>`;
  document.getElementById('statsRow').style.display = 'none';
  showClearBtn(false);
}

function showClearBtn(show) {
  let btn = document.getElementById('clearResultsBtn');
  if (!btn) return;
  btn.style.display = show ? 'inline-flex' : 'none';
  showResultsToolbar(show);
}

function restoreLeadsOnLoad() {
  const stored = loadStoredLeads();
  if (!stored.length) return;

  searchLeads = stored;

  // Re-render all stored leads
  const container = document.getElementById('searchResults');
  container.innerHTML = `<div class="leads-header">
    <div class="leads-title" id="leadsCount">${stored.length} Lead${stored.length !== 1 ? 's' : ''}</div>
  </div><div id="leadsList"></div>`;

  const list = document.getElementById('leadsList');
  stored.forEach(lead => {
    list.insertAdjacentHTML('beforeend', buildLeadCard(lead, lead.source_name || 'web'));
  });

  updateSearchStats();
  showClearBtn(true);

  // Show a subtle "restored" note
  const note = document.getElementById('stopNote');
  if (note) {
    note.textContent = `↩ ${stored.length} lead${stored.length !== 1 ? 's' : ''} restored from last session. Search again to add more, or Clear to start fresh.`;
    note.style.display = 'block';
  }
}

// Restore leads as soon as the search page is visible
document.addEventListener('DOMContentLoaded', () => {
  restoreLeadsOnLoad();
});

function updateProgress(current, total, message) {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  const bar   = document.getElementById('progressBar');
  const label = document.getElementById('progressLabel');
  if (bar)   bar.style.width = pct + '%';
  if (label) label.textContent = message || `${current} / ${total} results scored`;
}

function updateSearchStats() {
  const high = searchLeads.filter(l => l.intent_score >= 8).length;
  const avg  = searchLeads.length
    ? (searchLeads.reduce((a, l) => a + l.intent_score, 0) / searchLeads.length).toFixed(1)
    : '—';
  document.getElementById('statTotal').textContent = searchLeads.length;
  document.getElementById('statHigh').textContent  = high;
  document.getElementById('statAvg').textContent   = avg;
  document.getElementById('statsRow').style.display = '';
}

// Append a single lead card to a container (used for real-time streaming)
function appendLead(lead, containerId, providerLabel) {
  const container = document.getElementById(containerId);
  // Remove the loading/empty state on first lead of this search
  if (container.querySelector('.loading-state, .empty-state')) {
    container.innerHTML = `<div class="leads-header"><div class="leads-title" id="leadsCount">0 Leads</div></div><div id="leadsList"></div>`;
  }
  // If there's no leadsList yet (e.g. restored results), create it
  if (!document.getElementById('leadsList')) {
    container.innerHTML = `<div class="leads-header"><div class="leads-title" id="leadsCount">0 Leads</div></div><div id="leadsList"></div>`;
  }
  const list = document.getElementById('leadsList') || container;

  // Use richer Facebook card for FB group leads
  const card = (lead.source_name === 'facebook_group')
    ? buildFacebookLeadCard(lead)
    : buildLeadCard(lead, providerLabel);

  list.insertAdjacentHTML('afterbegin', card); // newest at top
  // Update count to reflect ALL leads (old + new)
  const countEl = document.getElementById('leadsCount');
  if (countEl) {
    countEl.textContent = searchLeads.length + ' Lead' + (searchLeads.length !== 1 ? 's' : '');
  }
  showClearBtn(true);
}

// ─── FACEBOOK GROUPS SCAN ────────────────────────────────────────────────────
async function scanFacebookGroups() {
  const s = getSettings();
  const fbToken    = s.fbtoken;
  const groupsRaw  = document.getElementById('fb-groups-input').value.trim();
  hideError('fbError');

  if (!fbToken) {
    showError('fbError', 'No Facebook token configured. Go to ⚙ Settings → Facebook tab.');
    return;
  }
  if (!groupsRaw) {
    showError('fbError', 'Add at least one Facebook Group URL in the box above.');
    return;
  }
  if (!s.backend) {
    showError('fbError', 'No backend URL. Add it in ⚙ Settings.');
    return;
  }

  const providerKey = currentProvider === 'openai' ? s.openai
                    : currentProvider === 'gemini'  ? s.gemini : s.claude;

  const groupUrls = groupsRaw.split('\n').map(u => u.trim()).filter(Boolean);

  const fbBtn = document.getElementById('fbScanBtn');
  fbBtn.disabled = true;
  fbBtn.textContent = 'Scanning groups…';

  const container = document.getElementById('fbResults');
  container.innerHTML = `<div class="loading-state"><div class="pulse-ring"></div>
    <p>Scanning ${groupUrls.length} group${groupUrls.length !== 1 ? 's' : ''}…</p>
    <p class="loading-sub">This may take a minute</p></div>`;

  try {
    const res = await fetch(`${s.backend}/facebook/scan`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        group_urls:   groupUrls,
        fb_token:     fbToken,
        provider:     currentProvider,
        provider_key: providerKey,
      }),
      signal: AbortSignal.timeout(120000), // 2 min timeout
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${res.status}`);
    }

    const results = await res.json();
    renderFacebookResults(results);

  } catch (e) {
    showError('fbError', e.message);
    container.innerHTML = '';
  } finally {
    fbBtn.disabled = false;
    fbBtn.textContent = '🔍 Scan Groups';
  }
}

function renderFacebookResults(results) {
  const container = document.getElementById('fbResults');
  let totalLeads = 0;
  let html = '';

  results.forEach(group => {
    const leads = group.leads || [];
    totalLeads += leads.length;

    html += `<div class="fb-group-section">
      <div class="fb-group-header">
        <span class="fb-group-name">👥 ${escHtml(group.group_name || group.group_id)}</span>
        <span class="fb-group-meta">${group.posts_scanned || 0} posts scanned · ${leads.length} leads</span>
      </div>`;

    if (group.error) {
      html += `<div class="error-banner" style="display:block;margin-bottom:12px">⚠ ${escHtml(group.error)}</div>`;
    }

    if (leads.length === 0 && !group.error) {
      html += `<div class="empty-state" style="padding:24px"><p>No buyer-intent posts found in this group.</p></div>`;
    } else {
      leads.forEach(lead => { html += buildLeadCard(lead, 'facebook'); });
    }

    html += `</div>`;
  });

  if (totalLeads === 0 && results.every(r => !r.error)) {
    container.innerHTML = `<div class="empty-state"><span class="empty-icon">👥</span>
      <p>No buyer-intent posts found across ${results.length} group${results.length !== 1 ? 's' : ''}.</p></div>`;
    return;
  }

  container.innerHTML = `<div class="leads-header">
    <div class="leads-title">${totalLeads} Lead${totalLeads !== 1 ? 's' : ''} from ${results.length} Group${results.length !== 1 ? 's' : ''}</div>
  </div>` + html;
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
      post_text: r.post, post_url: r.url, intent_score: r.intent, name: 'Stored Lead',
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

// ─── LEAD RENDERING ──────────────────────────────────────────────────────────
function buildLeadCard(lead, providerLabel) {
  const text   = lead.post_text || '(no text)';
  const url    = lead.post_url  || '#';
  const score  = parseFloat(lead.intent_score) || 0;
  const tier   = score >= 8 ? 'h' : score >= 6 ? 'm' : 'l';
  const pct    = Math.round((score / 10) * 100);
  const source = lead.source || extractDomain(url);

  return `<div class="lead-card ${score >= 8 ? 'high' : ''}">
    <div class="lead-top">
      <span class="lead-source">${escHtml(source)}</span>
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
}

function renderLeads(leads, containerId, providerLabel) {
  const container = document.getElementById(containerId);
  if (!leads || leads.length === 0) {
    container.innerHTML = `<div class="empty-state"><span class="empty-icon">🔍</span>
      <p>No buyer-intent leads found. Try a different keyword or check your API keys.</p></div>`;
    return;
  }
  const sorted = [...leads].sort((a, b) => b.intent_score - a.intent_score);
  container.innerHTML = `<div class="leads-header"><div class="leads-title">${sorted.length} Leads</div></div>`
    + sorted.map(l => buildLeadCard(l, providerLabel)).join('');
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
  try { return new URL(url).hostname.replace('www.', ''); } catch { return 'unknown'; }
}
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ─── OVERRIDE: richer Facebook lead card with profile link + lead type ────────
function buildFacebookLeadCard(lead) {
  const score       = parseFloat(lead.intent_score) || 0;
  const tier        = score >= 8 ? 'h' : score >= 6 ? 'm' : 'l';
  const pct         = Math.round((score / 10) * 100);
  const isCommenter = lead.lead_type === 'commenter';
  const typeLabel   = isCommenter ? '💬 Commenter' : '📝 Post Author';
  const typeCls     = isCommenter ? 'type-commenter' : 'type-author';

  return `
  <div class="lead-card fb-lead ${score >= 8 ? 'high' : ''}">
    <div class="lead-top">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <span class="fb-type-badge ${typeCls}">${typeLabel}</span>
        <span class="lead-source">${escHtml(lead.source_name || lead.source || 'facebook')}</span>
      </div>
      <div class="score-group">
        <div class="score-bar"><div class="score-fill ${tier}" style="width:${pct}%"></div></div>
        <span class="score-num ${tier}">${score.toFixed(1)}</span>
      </div>
    </div>

    ${lead.context ? `<p class="fb-context">${escHtml(lead.context)}</p>` : ''}
    <p class="lead-text">${escHtml(lead.post_text || '')}</p>

    <div class="fb-person-row">
      <div class="fb-person">
        <span class="fb-avatar">${escHtml((lead.name || '?')[0].toUpperCase())}</span>
        <div>
          <div class="fb-person-name">${escHtml(lead.name || 'Unknown')}</div>
          <div class="fb-person-sub">${isCommenter ? 'Expressed interest in this post' : 'Asked in group'}</div>
        </div>
      </div>
      <div style="display:flex;gap:8px">
        ${lead.profile_url ? `<a class="fb-profile-btn" href="${escHtml(lead.profile_url)}" target="_blank" rel="noopener">View Profile →</a>` : ''}
        <a class="lead-link" href="${escHtml(lead.post_url || '#')}" target="_blank" rel="noopener">View Post</a>
      </div>
    </div>
  </div>`;
}

// Override renderFacebookResults to use richer cards
function renderFacebookResults(results) {
  const container = document.getElementById('fbResults');
  let totalLeads = 0;
  let html = '';

  results.forEach(group => {
    const leads = group.leads || [];
    totalLeads += leads.length;

    const commenters   = leads.filter(l => l.lead_type === 'commenter');
    const postAuthors  = leads.filter(l => l.lead_type === 'post_author');

    html += `<div class="fb-group-section">
      <div class="fb-group-header">
        <span class="fb-group-name">👥 ${escHtml(group.group_name || group.group_id)}</span>
        <span class="fb-group-meta">
          ${group.posts_scanned || 0} posts · ${group.comments_scanned || 0} comments scanned · 
          <strong style="color:var(--accent)">${leads.length} leads</strong>
          ${commenters.length ? ` (${commenters.length} interested commenters)` : ''}
        </span>
      </div>`;

    if (group.error) {
      html += `<div class="error-banner" style="display:block;margin-bottom:12px">⚠ ${escHtml(group.error)}</div>`;
    }

    if (leads.length === 0 && !group.error) {
      html += `<div class="empty-state" style="padding:24px"><p>No buyer-intent posts or interested commenters found in this group.</p></div>`;
    } else {
      const sorted = [
        ...commenters.sort((a, b) => b.intent_score - a.intent_score),
        ...postAuthors.sort((a, b) => b.intent_score - a.intent_score),
      ];
      sorted.forEach(lead => { html += buildFacebookLeadCard(lead); });
    }

    html += `</div>`;
  });

  if (totalLeads === 0 && results.every(r => !r.error)) {
    container.innerHTML = `<div class="empty-state"><span class="empty-icon">👥</span>
      <p>No buyer-intent posts or interested commenters found. Try groups with more active discussions.</p></div>`;
    return;
  }

  container.innerHTML = `
    <div class="leads-header">
      <div class="leads-title">${totalLeads} Lead${totalLeads !== 1 ? 's' : ''} across ${results.length} Group${results.length !== 1 ? 's' : ''}</div>
    </div>` + html;
}

// ─── SCORE FILTER + SORT ─────────────────────────────────────────────────────

let activeFilter = 'all';   // 'all' | number (min score)
let activeSort   = 'newest'; // 'newest' | 'score'

function filterLeads(threshold, btn) {
  activeFilter = threshold;
  // Update chip active states
  document.querySelectorAll('.score-chip').forEach(c => c.classList.remove('active'));
  if (btn) btn.classList.add('active');
  renderFilteredLeads();
}

function sortLeads(mode, btn) {
  activeSort = mode;
  document.querySelectorAll('.sort-chip').forEach(c => c.classList.remove('active'));
  if (btn) btn.classList.add('active');
  renderFilteredLeads();
}

function renderFilteredLeads() {
  if (!searchLeads.length) return;

  // 1. Filter
  let filtered = activeFilter === 'all'
    ? [...searchLeads]
    : searchLeads.filter(l => l.intent_score >= activeFilter);

  // 2. Sort
  if (activeSort === 'score') {
    filtered.sort((a, b) => b.intent_score - a.intent_score);
  }
  // 'newest' = keep insertion order (already newest-first from appendLead)

  // 3. Re-render list
  const container = document.getElementById('searchResults');
  if (!filtered.length) {
    container.innerHTML = `<div class="empty-state"><span class="empty-icon">🔍</span>
      <p>No leads with score ≥${activeFilter}. Lower the filter threshold to see more.</p></div>`;
    return;
  }

  container.innerHTML = `<div class="leads-header">
    <div class="leads-title" id="leadsCount">${filtered.length} Lead${filtered.length !== 1 ? 's' : ''}${activeFilter !== 'all' ? ` (score ≥${activeFilter})` : ''}</div>
  </div><div id="leadsList"></div>`;

  const list = document.getElementById('leadsList');
  filtered.forEach(lead => {
    const card = lead.source_name === 'facebook_group'
      ? buildFacebookLeadCard(lead)
      : buildLeadCard(lead, lead.source_name || 'web');
    list.insertAdjacentHTML('beforeend', card);
  });
}

function showResultsToolbar(show) {
  const toolbar = document.getElementById('resultsToolbar');
  if (toolbar) toolbar.classList.toggle('visible', show);
}

// ─── PLATFORM TAB SWITCHER ────────────────────────────────────────────────────
function switchPlatformTab(tabId, clickedBtn) {
  document.querySelectorAll('.platform-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.platform-tab').forEach(b => b.classList.remove('active'));
  const panel = document.getElementById('panel-' + tabId);
  if (panel) panel.classList.add('active');
  if (clickedBtn) clickedBtn.classList.add('active');
}
