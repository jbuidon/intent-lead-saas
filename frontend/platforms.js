/**
 * platforms.js — Facebook Pages, Instagram, LinkedIn paste-and-score
 * Loaded after app.js in index.html
 */

// ─── FACEBOOK PAGES ──────────────────────────────────────────────────────────
async function scanFacebookPages() {
  const s         = getSettings();
  const raw       = document.getElementById('fbpage-urls').value.trim();
  const container = document.getElementById('fbPageResults');
  hideError('fbPageError');

  if (!s.fbtoken) { showError('fbPageError', 'No Facebook token. Add it in ⚙ Settings → Facebook.'); return; }
  if (!raw)        { showError('fbPageError', 'Add at least one Facebook Page URL.'); return; }
  if (!s.backend)  { showError('fbPageError', 'No backend URL. Add it in ⚙ Settings.'); return; }

  const providerKey = currentProvider === 'openai' ? s.openai
                    : currentProvider === 'gemini'  ? s.gemini : s.claude;
  const pageUrls = raw.split('\n').map(u => u.trim()).filter(Boolean);

  const btn = document.getElementById('fbPageScanBtn');
  btn.disabled = true; btn.textContent = 'Scanning…';
  container.innerHTML = loadingHTML(`Scanning ${pageUrls.length} page${pageUrls.length > 1 ? 's' : ''}…`);

  try {
    const res = await fetch(`${s.backend}/facebook/scan-page`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page_urls: pageUrls, fb_token: s.fbtoken, provider: currentProvider, provider_key: providerKey }),
      signal: AbortSignal.timeout(120000),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `Error ${res.status}`);
    renderPlatformResults(await res.json(), 'fbPageResults', 'Facebook Page');
  } catch (e) {
    showError('fbPageError', e.message);
    container.innerHTML = '';
  } finally {
    btn.disabled = false; btn.textContent = '🔍 Scan Pages';
  }
}

// ─── INSTAGRAM ───────────────────────────────────────────────────────────────
async function scanInstagram() {
  const s         = getSettings();
  const container = document.getElementById('igResults');
  hideError('igError');

  if (!s.fbtoken) { showError('igError', 'No Facebook/Instagram token. Add it in ⚙ Settings → Facebook.'); return; }
  if (!s.backend) { showError('igError', 'No backend URL. Add it in ⚙ Settings.'); return; }

  const providerKey = currentProvider === 'openai' ? s.openai
                    : currentProvider === 'gemini'  ? s.gemini : s.claude;

  const btn = document.getElementById('igScanBtn');
  btn.disabled = true; btn.textContent = 'Scanning…';
  container.innerHTML = loadingHTML('Fetching your Instagram accounts and scanning comments…');

  try {
    const res = await fetch(`${s.backend}/instagram/scan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fb_token: s.fbtoken, provider: currentProvider, provider_key: providerKey }),
      signal: AbortSignal.timeout(120000),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `Error ${res.status}`);
    renderPlatformResults(await res.json(), 'igResults', 'Instagram');
  } catch (e) {
    showError('igError', e.message);
    container.innerHTML = '';
  } finally {
    btn.disabled = false; btn.textContent = '📸 Scan My Instagram';
  }
}

// ─── LINKEDIN PASTE & SCORE ──────────────────────────────────────────────────
let linkedinItems = [];   // items staged for scoring

function addLinkedinItem() {
  const text        = document.getElementById('li-text').value.trim();
  const url         = document.getElementById('li-url').value.trim();
  const name        = document.getElementById('li-name').value.trim();
  const contentType = document.getElementById('li-type').value;

  if (!text) { showError('liError', 'Paste some text first.'); return; }

  hideError('liError');
  linkedinItems.push({ text, url, person_name: name || 'LinkedIn User', content_type: contentType });

  // Clear inputs
  document.getElementById('li-text').value = '';
  document.getElementById('li-url').value  = '';
  document.getElementById('li-name').value = '';

  renderLinkedinQueue();
}

function removeLinkedinItem(idx) {
  linkedinItems.splice(idx, 1);
  renderLinkedinQueue();
}

function renderLinkedinQueue() {
  const container = document.getElementById('liQueue');
  if (!linkedinItems.length) {
    container.innerHTML = '<p style="color:var(--muted);font-size:0.8rem;padding:8px 0">No items queued yet. Paste content above and click Add.</p>';
    document.getElementById('liScoreBtn').disabled = true;
    return;
  }
  document.getElementById('liScoreBtn').disabled = false;
  container.innerHTML = linkedinItems.map((item, i) => `
    <div class="li-queue-item">
      <div>
        <span class="li-type-tag">${item.content_type}</span>
        <span class="li-person">${escHtml(item.person_name)}</span>
        ${item.url ? `<a href="${escHtml(item.url)}" target="_blank" class="li-url-link">↗</a>` : ''}
      </div>
      <p class="li-preview">${escHtml(item.text.slice(0, 100))}${item.text.length > 100 ? '…' : ''}</p>
      <button class="li-remove-btn" onclick="removeLinkedinItem(${i})">✕ Remove</button>
    </div>`).join('');
}

async function scoreLinkedinItems() {
  const s         = getSettings();
  const container = document.getElementById('liResults');
  hideError('liError');

  if (!linkedinItems.length) { showError('liError', 'Add at least one item to score.'); return; }
  if (!s.backend) { showError('liError', 'No backend URL. Add it in ⚙ Settings.'); return; }

  const providerKey = currentProvider === 'openai' ? s.openai
                    : currentProvider === 'gemini'  ? s.gemini : s.claude;
  if (!providerKey) { showError('liError', `No ${currentProvider} API key configured.`); return; }

  const btn = document.getElementById('liScoreBtn');
  btn.disabled = true; btn.textContent = 'Scoring…';
  container.innerHTML = loadingHTML(`Scoring ${linkedinItems.length} item${linkedinItems.length > 1 ? 's' : ''} with AI…`);

  try {
    const res = await fetch(`${s.backend}/linkedin/score`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: linkedinItems, provider: currentProvider, provider_key: providerKey }),
      signal: AbortSignal.timeout(60000),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `Error ${res.status}`);
    const leads = await res.json();

    if (!leads.length) {
      container.innerHTML = `<div class="empty-state"><span class="empty-icon">🔍</span>
        <p>None of the pasted items scored high enough for buyer intent. Try pasting posts where people are asking for help or showing interest.</p></div>`;
    } else {
      container.innerHTML = `<div class="leads-header"><div class="leads-title">${leads.length} Lead${leads.length !== 1 ? 's' : ''} Found</div></div>`
        + leads.sort((a,b) => b.intent_score - a.intent_score).map(l => buildFacebookLeadCard(l)).join('');
    }
  } catch (e) {
    showError('liError', e.message);
    container.innerHTML = '';
  } finally {
    btn.disabled = false; btn.textContent = '🧠 Score with AI';
  }
}

// ─── SHARED RENDERER ─────────────────────────────────────────────────────────
function renderPlatformResults(results, containerId, platformLabel) {
  const container = document.getElementById(containerId);
  if (!Array.isArray(results)) results = [results];

  let totalLeads = 0;
  let html = '';

  results.forEach(group => {
    const leads      = group.leads || [];
    const commenters = leads.filter(l => l.lead_type === 'commenter');
    totalLeads += leads.length;

    const groupName  = group.page_name || group.ig_name || group.group_name || group.page_id || 'Unknown';
    const scanned    = group.posts_scanned || 0;
    const comments   = group.comments_scanned || 0;

    html += `<div class="fb-group-section">
      <div class="fb-group-header">
        <span class="fb-group-name">${platformIcon(platformLabel)} ${escHtml(groupName)}</span>
        <span class="fb-group-meta">${scanned} posts · ${comments} comments · <strong style="color:var(--accent)">${leads.length} leads</strong>${commenters.length ? ` (${commenters.length} interested)` : ''}</span>
      </div>`;

    if (group.error) html += `<div class="error-banner" style="display:block;margin-bottom:12px">⚠ ${escHtml(group.error)}</div>`;

    if (!leads.length && !group.error) {
      html += `<div class="empty-state" style="padding:24px"><p>No buyer-intent posts or interested commenters found.</p></div>`;
    } else {
      const sorted = [
        ...commenters.sort((a,b) => b.intent_score - a.intent_score),
        ...leads.filter(l => l.lead_type !== 'commenter').sort((a,b) => b.intent_score - a.intent_score),
      ];
      sorted.forEach(l => { html += buildFacebookLeadCard(l); });
    }

    html += '</div>';
  });

  if (!totalLeads && results.every(r => !r.error)) {
    container.innerHTML = `<div class="empty-state"><span class="empty-icon">${platformIcon(platformLabel)}</span>
      <p>No buyer-intent leads found. Try pages or accounts with more active comment sections.</p></div>`;
    return;
  }

  container.innerHTML = `<div class="leads-header"><div class="leads-title">${totalLeads} Lead${totalLeads !== 1 ? 's' : ''}</div></div>` + html;
}

function platformIcon(label) {
  if (label.includes('Instagram')) return '📸';
  if (label.includes('Facebook'))  return '📘';
  if (label.includes('LinkedIn'))  return '💼';
  return '🌐';
}

function loadingHTML(msg) {
  return `<div class="loading-state"><div class="pulse-ring"></div><p>${escHtml(msg)}</p><p class="loading-sub">Click Stop anytime to cancel</p></div>`;
}

// Init LinkedIn queue display on page load
window.addEventListener('DOMContentLoaded', () => {
  renderLinkedinQueue();
});
