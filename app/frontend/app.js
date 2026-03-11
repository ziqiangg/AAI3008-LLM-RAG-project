// RAG Learning Assistant - Main JavaScript

const API = 'http://localhost:5000';

mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'loose' });

let webSearchEnabled = false;
let diagramEnabled = false;

<<<<<<< Updated upstream
// ── Folder / Scope state ───────────────────────
let folders          = [];          // [{id, name, color, doc_count}]
let chatScopeFolderIds = [];        // folder IDs selected for chat (empty = all)
let _folderModalMode = 'create';    // 'create' | 'rename'
let _folderModalId   = null;        // id when renaming
let _folderColor     = '#6c63ff';   // currently picked colour
let _moveDocId       = null;        // document being moved
let _moveDocFolderId = null;        // target folder for move
let _quizScope       = 'all';       // 'all' | 'folders' | 'chat'
let _quizFolderIds   = [];          // for 'folders' quiz scope

const FOLDER_COLORS = [
  '#6c63ff','#10a37f','#ef4444','#f59e0b',
  '#3b82f6','#ec4899','#14b8a6','#84cc16',
  '#f97316','#8b5cf6','#06b6d4','#6b7280'
];

// ── State ─────────────────────────────────────
=======
// ── State ─────────────────────────────────
>>>>>>> Stashed changes
let messages       = [];
let msgCounter     = 0;
let authMode       = 'login';
let currentUser    = null;
let currentToken   = localStorage.getItem('rag_token') || null;
let currentSession = null;
let toastTimeout   = null;
let stageTimer     = null;

// Folder state
let folders          = [];
let scopedFolderIds  = [];
let folderModalMode  = 'create';
let folderModalId    = null;
let collapsedFolders = new Set();

let activeSource = null;

const SUBJECT_COLORS = {
  'Math': '#3b82f6', 'Computer Science': '#10b981',
  'Artificial Intelligence': '#8b5cf6', 'Physics': '#ef4444',
  'Chemistry': '#f59e0b', 'Biology': '#14b8a6',
  'Language Learning': '#ec4899', 'Geography': '#84cc16',
  'Economics': '#06b6d4', 'Social Studies': '#f97316',
  'Computer Systems': '#6366f1', 'General': '#6b7280'
};

const VALID_SUBJECTS = [
  'Math', 'Computer Science', 'Artificial Intelligence', 'Physics',
  'Chemistry', 'Biology', 'Language Learning', 'Geography',
  'Economics', 'Social Studies', 'Computer Systems', 'General'
];

window._docsById = {};
window._docIdByFilename = {};

// ── Bootstrap ─────────────────────────────
window.addEventListener('load', () => {
  loadDocuments();
  if (currentToken) restoreSession();
  loadFolders();
});

// ══════════════════════════════════════════════
// AUTH
// ══════════════════════════════════════════════
function openAuthModal() {
  if (currentUser) { showUserMenu(); return; }
  document.getElementById('modal-overlay').classList.add('visible');
  document.getElementById('auth-error').textContent = '';
}
function closeAuthModal() { document.getElementById('modal-overlay').classList.remove('visible'); }
document.getElementById('modal-overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('modal-overlay')) closeAuthModal();
});
function switchAuthTab(mode) {
  authMode = mode;
  const isLogin = mode === 'login';
  document.getElementById('tab-login-btn').classList.toggle('active', isLogin);
  document.getElementById('tab-register-btn').classList.toggle('active', !isLogin);
  document.getElementById('modal-title').textContent = isLogin ? 'Welcome back' : 'Create account';
  document.getElementById('auth-submit').textContent = isLogin ? 'Login' : 'Register';
  document.getElementById('auth-username').style.display = isLogin ? 'none' : '';
  document.getElementById('auth-error').textContent = '';
}

async function submitAuth() {
  const btn = document.getElementById('auth-submit');
  const errEl = document.getElementById('auth-error');
  const email = document.getElementById('auth-email').value.trim();
  const password = document.getElementById('auth-password').value;
  const username = document.getElementById('auth-username').value.trim();
  errEl.textContent = '';
  if (!email || !password) { errEl.textContent = 'Please fill in all fields.'; return; }
  btn.disabled = true;
  btn.textContent = authMode === 'login' ? 'Logging in…' : 'Registering…';
  try {
    const body = authMode === 'login' ? { email, password } : { email, password, username };
    const res = await fetch(`${API}/api/users/${authMode}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.error || 'Something went wrong.'; return; }
    currentToken = data.token; currentUser = data.user;
    localStorage.setItem('rag_token', currentToken);
<<<<<<< Updated upstream
    
    // Always clear fields after request is sent
    email.value = '';
    password.value  = '';
    username.value  = '';
    closeAuthModal();
    updateAuthButton();
    loadSessions();
    loadDocuments();
    loadFolders();
=======
    closeAuthModal(); updateAuthButton(); loadSessions(); loadDocuments();
>>>>>>> Stashed changes
    showToast('👋', `Welcome, ${currentUser.username}!`, 'success');
  } catch { errEl.textContent = 'Could not reach the backend.'; }
  finally { btn.disabled = false; btn.textContent = authMode === 'login' ? 'Login' : 'Register'; }
}

async function restoreSession() {
  try {
    const res = await authFetch('/api/users/me');
    const data = await res.json();
<<<<<<< Updated upstream
    if (res.ok) {
      currentUser = data.user;
      updateAuthButton();
      loadSessions();
      loadFolders();
    } else {
      logout();
    }
=======
    if (res.ok) { currentUser = data.user; updateAuthButton(); loadSessions(); loadDocuments(); }
    else { logout(); }
>>>>>>> Stashed changes
  } catch { logout(); }
}

function logout() {
  currentToken = null; currentUser = null;
  localStorage.removeItem('rag_token');
  updateAuthButton();
  setTimeout(() => window.location.reload(), 100);
}

function updateAuthButton() {
  const icon = document.getElementById('auth-btn-icon');
  const label = document.getElementById('auth-btn-label');
  if (currentUser) {
    icon.innerHTML = `<span class="auth-avatar">${currentUser.username[0].toUpperCase()}</span>`;
    label.textContent = currentUser.username;
  } else { icon.textContent = '🔑'; label.textContent = 'Login'; }
}

function showUserMenu() {
  const existing = document.getElementById('user-dropdown');
  if (existing) { existing.remove(); return; }
  const btn = document.getElementById('auth-btn');
  const rect = btn.getBoundingClientRect();
  const dropdown = document.createElement('div');
  dropdown.id = 'user-dropdown'; dropdown.className = 'user-dropdown';
  dropdown.style.top = (rect.bottom + 8) + 'px';
  dropdown.style.right = (window.innerWidth - rect.right) + 'px';
  dropdown.innerHTML = `
    <button class="user-dropdown-item" onclick="confirmLogout()">🚪 Logout</button>
    <div class="user-dropdown-divider"></div>
    <button class="user-dropdown-item danger" onclick="confirmDeleteAccount()">🗑️ Delete Account</button>`;
  document.body.appendChild(dropdown);
  setTimeout(() => document.addEventListener('click', () => {
    const d = document.getElementById('user-dropdown'); if (d) d.remove();
  }, { once: true }), 0);
}

function confirmLogout() {
  document.getElementById('user-dropdown')?.remove();
  if (!confirm('Are you sure you want to log out?')) return; logout();
}

async function confirmDeleteAccount() {
  document.getElementById('user-dropdown')?.remove();
  if (!confirm('Delete your account?\n\nAll documents, sessions, and folders will be permanently removed.')) return;
  try {
    const res = await authFetch('/api/users/me', { method: 'DELETE' });
    if (res.ok) { showToast('🗑️', 'Account deleted.', 'success'); setTimeout(() => logout(), 1200); }
    else { const d = await res.json(); showToast('❌', d.error || 'Failed.', 'error'); }
  } catch { showToast('❌', 'Backend unreachable.', 'error'); }
}

async function authFetch(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (currentToken) headers['Authorization'] = `Bearer ${currentToken}`;
  return fetch(`${API}${path}`, { ...opts, headers });
}

// ══════════════════════════════════════════════
// RIGHT PANEL
// ══════════════════════════════════════════════
function switchRightTab(tab, el) {
  document.querySelectorAll('.right-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.right-tab-panel').forEach(p => p.classList.remove('active'));
  el.classList.add('active');
  document.getElementById(`tab-${tab}`).classList.add('active');
}

// ══════════════════════════════════════════════
// SOURCES
// ══════════════════════════════════════════════
function renderSources(sources) {
  window._lastSources = sources || [];
  activeSource = null;
  const list = document.getElementById('sources-list');
  const empty = document.getElementById('sources-empty');
  if (!sources || sources.length === 0) { list.innerHTML = ''; empty.style.display = 'block'; return; }
  empty.style.display = 'none';
  const sorted = [...sources].sort((a, b) => (b.score || 0) - (a.score || 0));
  list.innerHTML = sorted.map((s, i) => {
    const page = s.metadata?.source?.page;
    const pageDisplay = page != null ? ` · p.${page}` : '';
    const citationLabel = s.citation_index ? `<span style="background:var(--accent);color:white;padding:1px 5px;border-radius:4px;font-size:9px;font-weight:700;margin-right:4px;">[S${s.citation_index}]</span>` : '';
    const isWeb = (s.source_type === 'web') || (s.metadata?.source_type === 'web');
    const icon = isWeb ? '🌐' : '📄';
    const title = isWeb ? (s.title || s.filename || `Web ${i+1}`) : (s.filename || `Source ${i+1}`);
    const url = s.url || s.metadata?.url;
    const clickable = isWeb && url ? `onclick="openWebSource('${url}',${i})"` : `onclick="setActiveSource(${i})"`;
    return `
    <div class="source-card" ${clickable} title="${escapeHtml(s.content||'')}">
      <div class="source-file">${citationLabel}${icon} ${escapeHtml(title)}${pageDisplay}</div>
      <div class="source-snippet">${escapeHtml((s.content||'').slice(0,200))}</div>
      <div class="source-score">
        <span>${s.score != null ? (s.score*100).toFixed(0)+'% match' : ''}</span>
        ${s.score != null ? `<div class="score-bar"><div class="score-fill" style="width:${(s.score*100).toFixed(0)}%"></div></div>` : ''}
      </div>
    </div>`;
  }).join('');
}

function setActiveSource(i) {
  const sources = window._lastSources || [];
  activeSource = sources[i] || null;
  document.querySelectorAll('.source-card').forEach((el, idx) => el.classList.toggle('active', idx === i));
  if (activeSource) {
    const docId = activeSource.doc_id || (activeSource.filename ? window._docIdByFilename[activeSource.filename] : null);
    if (docId) {
      const fn = activeSource.filename || (window._docsById[docId]?.filename ?? `Document ${docId}`);
      previewDoc(docId, fn, { chunkOrder: activeSource.chunk_order ?? null, needle: activeSource.content || '' });
    }
  }
}
function openWebSource(url, idx) { setActiveSource(idx); window.open(url, '_blank', 'noopener,noreferrer'); }

// ══════════════════════════════════════════════
// SESSIONS
// ══════════════════════════════════════════════
async function loadSessions() {
  if (!currentToken) return;
  try {
    const res = await authFetch('/api/sessions/');
    const data = await res.json();
    const list = document.getElementById('session-list');
    if (!data.sessions?.length) {
      list.innerHTML = '<div style="font-size:12px;color:var(--text-muted);text-align:center;padding:20px 8px">No sessions yet. Start a chat!</div>';
      return;
    }
    list.innerHTML = data.sessions.map(s => `
      <div class="session-item" onclick="loadSession(${s.id})" title="${escapeHtml(s.title)}">
        <span class="session-icon">💬</span>
        <span class="session-title">${escapeHtml(s.title || 'Untitled')}</span>
        <button class="session-del" onclick="deleteSession(${s.id},event)" title="Delete">✕</button>
      </div>`).join('');
  } catch(e) { console.warn('Could not load sessions', e); }
}

async function loadSession(sessionId) {
  try {
    const res = await authFetch(`/api/sessions/${sessionId}`);
    const data = await res.json();
    if (!res.ok) return;
    currentSession = sessionId;
    const win = document.getElementById('chat-window');
    win.innerHTML = '';
    let lastSources = null;
    (data.messages || []).forEach(m => {
<<<<<<< Updated upstream
      appendMessage(m.role === 'user' ? 'user' : 'bot', null, m.content);
      // Extract sources from assistant messages
      if (m.role === 'assistant' && m.sources) {
        lastSources = m.sources;
=======
      let rw = null;
      if (m.role === 'user' && m.sources && m.sources.query_rewritten) {
        rw = { query_rewritten: true, original_query: m.sources.original_query, rewritten_query: m.sources.rewritten_query, rewrite_strategy: m.sources.rewrite_strategy, score_improvement: m.sources.score_improvement };
>>>>>>> Stashed changes
      }
      appendMessage(m.role === 'user' ? 'user' : 'bot', null, m.content, false, rw);
      if (m.role === 'assistant' && m.sources) lastSources = m.sources;
    });
    renderSources(lastSources ? (lastSources.chunks || lastSources) : null);
    document.querySelectorAll('.right-tab')[0].click();
  } catch(e) { console.warn('Could not load session', e); }
}

async function ensureSession() {
  if (currentSession || !currentToken) return;
  try {
    const res = await authFetch('/api/sessions/', { method: 'POST', body: JSON.stringify({ title: 'New Chat' }) });
    const data = await res.json();
    if (res.ok) { currentSession = data.session.id; loadSessions(); }
  } catch(e) { console.warn('Could not create session', e); }
}

async function deleteSession(sessionId, e) {
  e.stopPropagation();
  if (!confirm('Delete this chat session?')) return;
  try {
    const res = await authFetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
    if (res.ok) { showToast('🗑️', 'Session deleted.', 'success'); if (currentSession === sessionId) newChat(); loadSessions(); }
    else showToast('❌', 'Delete failed.', 'error');
  } catch { showToast('❌', 'Backend unreachable.', 'error'); }
}

// ══════════════════════════════════════════════
// FOLDERS - CRUD
// ══════════════════════════════════════════════
async function loadFolders() {
  if (!currentToken) { folders = []; return; }
  try {
    const res = await authFetch('/api/folders/');
    const data = await res.json();
    folders = data.folders || [];
  } catch { folders = []; }
}

function openCreateFolderModal() {
  if (!currentUser) { showToast('❌', 'Please log in first.', 'error'); return; }
  folderModalMode = 'create'; folderModalId = null;
  document.getElementById('folder-modal-title').textContent = 'New Folder';
  document.getElementById('folder-modal-submit').textContent = 'Create';
  document.getElementById('folder-name-input').value = '';
  document.getElementById('folder-modal-error').textContent = '';
  document.getElementById('folder-modal-overlay').classList.add('visible');
  setTimeout(() => document.getElementById('folder-name-input').focus(), 100);
}

function openRenameFolderModal(folderId, currentName) {
  folderModalMode = 'rename'; folderModalId = folderId;
  document.getElementById('folder-modal-title').textContent = 'Rename Folder';
  document.getElementById('folder-modal-submit').textContent = 'Rename';
  document.getElementById('folder-name-input').value = currentName;
  document.getElementById('folder-modal-error').textContent = '';
  document.getElementById('folder-modal-overlay').classList.add('visible');
  setTimeout(() => document.getElementById('folder-name-input').focus(), 100);
}

function closeFolderModal() { document.getElementById('folder-modal-overlay').classList.remove('visible'); }
document.getElementById('folder-modal-overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('folder-modal-overlay')) closeFolderModal();
});

async function submitFolderModal() {
  const name = document.getElementById('folder-name-input').value.trim();
  const errEl = document.getElementById('folder-modal-error');
  if (!name) { errEl.textContent = 'Folder name is required.'; return; }
  try {
    let res;
    if (folderModalMode === 'create') {
      res = await authFetch('/api/folders/', { method: 'POST', body: JSON.stringify({ name }) });
    } else {
      res = await authFetch(`/api/folders/${folderModalId}`, { method: 'PATCH', body: JSON.stringify({ name }) });
    }
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.error || 'Failed.'; return; }
    showToast('📁', folderModalMode === 'create' ? `Folder "${name}" created.` : `Folder renamed.`, 'success');
    closeFolderModal();
    loadDocuments();
  } catch { errEl.textContent = 'Backend unreachable.'; }
}

async function deleteFolder(folderId, folderName) {
  if (!confirm(`Delete folder "${folderName}"?\n\nDocuments inside will be moved to Unfiled.`)) return;
  try {
    const res = await authFetch(`/api/folders/${folderId}`, { method: 'DELETE' });
    if (res.ok) {
      showToast('🗑️', `Folder "${folderName}" deleted.`, 'success');
      scopedFolderIds = scopedFolderIds.filter(id => id !== folderId);
      updateFolderScopeUI(); loadDocuments();
    } else showToast('❌', 'Delete failed.', 'error');
  } catch { showToast('❌', 'Backend unreachable.', 'error'); }
}

// ── Move document to folder ──
function showMoveMenu(docId, event) {
  event.stopPropagation(); closeMoveMenu();
  const rect = event.target.getBoundingClientRect();
  const menu = document.createElement('div');
  menu.id = 'move-folder-menu'; menu.className = 'move-folder-menu';
  menu.style.top = rect.bottom + 4 + 'px';
  menu.style.left = Math.min(rect.left, window.innerWidth - 200) + 'px';
  let items = `<button class="move-item" onclick="moveDocToFolder(${docId}, null)">📂 Unfiled</button>`;
  if (folders.length > 0) items += '<div class="move-divider"></div>';
  folders.forEach(f => {
    items += `<button class="move-item" onclick="moveDocToFolder(${docId}, ${f.id})">📁 ${escapeHtml(f.name)}</button>`;
  });
  menu.innerHTML = items;
  document.body.appendChild(menu);
  setTimeout(() => document.addEventListener('click', closeMoveMenu, { once: true }), 0);
}
function closeMoveMenu() { const m = document.getElementById('move-folder-menu'); if (m) m.remove(); }

async function moveDocToFolder(docId, folderId) {
  closeMoveMenu();
  try {
    const res = await fetch(`${API}/api/documents/${docId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...(currentToken ? { 'Authorization': `Bearer ${currentToken}` } : {}) },
      body: JSON.stringify({ folder_id: folderId })
    });
    if (res.ok) { showToast('✅', 'Document moved.', 'success'); loadDocuments(); }
    else showToast('❌', 'Move failed.', 'error');
  } catch { showToast('❌', 'Backend unreachable.', 'error'); }
}

// ══════════════════════════════════════════════
// FOLDER SCOPE (for chat & quiz)
// ══════════════════════════════════════════════
function openFolderScopeModal() {
  document.getElementById('add-menu').style.display = 'none';
  document.getElementById('add-btn').classList.remove('active');
  if (!currentUser) { showToast('❌', 'Please log in first.', 'error'); return; }
  renderFolderChecklist('folder-scope-checklist', scopedFolderIds);
  document.getElementById('folder-scope-modal-overlay').classList.add('visible');
}
function closeFolderScopeModal() { document.getElementById('folder-scope-modal-overlay').classList.remove('visible'); }
document.getElementById('folder-scope-modal-overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('folder-scope-modal-overlay')) closeFolderScopeModal();
});

function applyFolderScope() {
  const checks = document.querySelectorAll('#folder-scope-checklist input[type="checkbox"]');
  scopedFolderIds = [];
  checks.forEach(cb => { if (cb.checked) scopedFolderIds.push(parseInt(cb.value)); });
  updateFolderScopeUI(); closeFolderScopeModal();
  if (scopedFolderIds.length > 0) {
    const names = scopedFolderIds.map(id => { const f = folders.find(x => x.id === id); return f ? f.name : '?'; });
    showToast('📁', `Chat scoped to: ${names.join(', ')}`, 'success');
  } else showToast('📁', 'Folder scope cleared — using all documents.', 'success');
}

function clearFolderScope() { scopedFolderIds = []; updateFolderScopeUI(); showToast('📁', 'Folder scope cleared.', 'success'); }

function updateFolderScopeUI() {
  const pill = document.getElementById('folder-filter-pill');
  const pillText = document.getElementById('folder-filter-pill-text');
  const features = document.getElementById('active-features');
  if (scopedFolderIds.length > 0) {
    const names = scopedFolderIds.map(id => { const f = folders.find(x => x.id === id); return f ? f.name : '?'; });
    pillText.textContent = names.length <= 2 ? names.join(', ') : `${names.length} folders`;
    pill.style.display = 'inline-flex';
  } else { pill.style.display = 'none'; }
  const anyActive = webSearchEnabled || diagramEnabled || scopedFolderIds.length > 0;
  features.style.display = anyActive ? 'flex' : 'none';
}

function renderFolderChecklist(containerId, selectedIds) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (folders.length === 0) {
    el.innerHTML = '<div style="font-size:12px;color:var(--text-muted);padding:8px;">No folders yet. Create one from the sidebar.</div>';
    return;
  }
  el.innerHTML = folders.map(f => `
    <label class="folder-check-item">
      <input type="checkbox" value="${f.id}" ${selectedIds.includes(f.id) ? 'checked' : ''} />
      <span class="folder-check-name">📁 ${escapeHtml(f.name)}</span>
      <span class="folder-check-count">${f.document_count} doc${f.document_count !== 1 ? 's' : ''}</span>
    </label>`).join('');
}

// ══════════════════════════════════════════════
// UPLOAD PROGRESS OVERLAY
// ══════════════════════════════════════════════
const UPLOAD_STAGES = [
  { label: 'Saving file to server',         pct: 10,  icon: '📥' },
  { label: 'Extracting text from document',  pct: 25,  icon: '📝' },
  { label: 'Splitting into chunks',          pct: 40,  icon: '✂️' },
  { label: 'Classifying subjects',           pct: 50,  icon: '🏷️' },
  { label: 'Generating embeddings (slow)',   pct: 75,  icon: '🧠' },
  { label: 'Storing in vector database',     pct: 90,  icon: '💾' },
];

let _uploadStageTimer = null;

function showUploadProgress(filename) {
  const overlay = document.getElementById('upload-progress-overlay');
  document.getElementById('upload-progress-filename').textContent = filename;
  document.getElementById('upload-progress-bar').style.width = '0%';
  document.getElementById('upload-progress-stage').textContent = 'Starting…';
  document.getElementById('upload-progress-title').textContent = 'Processing document…';

  // Build step list
  const stepsEl = document.getElementById('upload-progress-steps');
  stepsEl.innerHTML = UPLOAD_STAGES.map((s, i) => `
    <div class="upload-step" id="upload-step-${i}">
      <span class="upload-step-icon">${s.icon}</span>
      <span>${s.label}</span>
    </div>`).join('');

  overlay.style.display = 'flex';

  // Animate through stages at realistic intervals
  let stageIdx = 0;
  function advanceStage() {
    if (stageIdx >= UPLOAD_STAGES.length) return;
    const stage = UPLOAD_STAGES[stageIdx];
    document.getElementById('upload-progress-bar').style.width = stage.pct + '%';
    document.getElementById('upload-progress-stage').textContent = stage.label + '…';

    // Mark previous steps as done
    for (let j = 0; j < stageIdx; j++) {
      const el = document.getElementById(`upload-step-${j}`);
      if (el) { el.classList.remove('active'); el.classList.add('done'); }
    }
    // Mark current step as active
    const cur = document.getElementById(`upload-step-${stageIdx}`);
    if (cur) { cur.classList.add('active'); cur.classList.remove('done'); }

    stageIdx++;
    // Timings: first few are fast, embedding step is slow
    const delays = [800, 1500, 1200, 2000, 8000, 2000];
    const delay = delays[stageIdx - 1] || 2000;
    _uploadStageTimer = setTimeout(advanceStage, delay);
  }
  advanceStage();
}

function hideUploadProgress(success) {
  clearTimeout(_uploadStageTimer);
  const bar = document.getElementById('upload-progress-bar');
  const stage = document.getElementById('upload-progress-stage');
  const title = document.getElementById('upload-progress-title');
  if (success) {
    bar.style.width = '100%';
    stage.textContent = 'Complete!';
    title.textContent = 'Document ingested successfully!';
    // Mark all steps done
    UPLOAD_STAGES.forEach((_, i) => {
      const el = document.getElementById(`upload-step-${i}`);
      if (el) { el.classList.remove('active'); el.classList.add('done'); }
    });
  } else {
    stage.textContent = 'Failed';
    title.textContent = 'Upload failed';
  }
  // Auto-close after a short delay
  setTimeout(() => {
    document.getElementById('upload-progress-overlay').style.display = 'none';
  }, success ? 1200 : 2500);
}

// ══════════════════════════════════════════════
// DOCUMENTS & FOLDER TREE
// ══════════════════════════════════════════════
function triggerSidebarUpload() {
  document.getElementById('sidebar-file-input').click();
}

async function onSidebarFileSelected(event) {
  const file = event.target.files[0];
  if (!file) return;
  event.target.value = '';
  await uploadDocumentFromSidebar(file);
}

async function uploadDocumentFromSidebar(file, folderId) {
  if (!currentUser) { showToast('❌', 'Please log in before uploading.', 'error'); return; }

  // Show progress overlay instead of just a toast
  showUploadProgress(file.name);

  const formData = new FormData();
  formData.append('file', file);
  formData.append('subject', 'General');
  formData.append('user_id', currentUser.id);
  if (folderId != null) formData.append('folder_id', folderId);

  try {
    const res = await fetch(`${API}/api/documents/upload`, { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok) {
      hideUploadProgress(false);
      showToast('❌', data.error || 'Upload failed.', 'error');
      return;
    }
    hideUploadProgress(true);
    showToast('✅', `${file.name} ingested!`, 'success');
    loadDocuments();
  } catch {
    hideUploadProgress(false);
    showToast('❌', 'Upload failed — backend unreachable.', 'error');
  }
}

// ── FIX: loadDocuments now passes user_id to only show the logged-in user's docs ──
async function loadDocuments() {
  try {
<<<<<<< Updated upstream
    const res  = await fetch(`${API}/api/documents/`);
    const data = await res.json();
    const docs = data.documents || data || [];
=======
    if (currentToken) await loadFolders();

    // Pass user_id so backend only returns this user's documents
    const url = currentUser
      ? `${API}/api/documents/?user_id=${currentUser.id}`
      : `${API}/api/documents/`;
    const res = await fetch(url);
    const data = await res.json();
    const docs = data.documents || data;
    const tree = document.getElementById('docs-tree');
>>>>>>> Stashed changes

    window._docsById = {};
    window._docIdByFilename = {};
    (docs || []).forEach(d => { window._docsById[d.id] = d; if (d.filename) window._docIdByFilename[d.filename] = d.id; });

    if (!docs?.length && !folders.length) {
      tree.innerHTML = `<div style="font-size:12px;color:var(--text-muted);padding:8px 4px">${currentUser ? 'No documents yet. Upload or paste a link.' : 'Log in to manage documents.'}</div>`;
      return;
    }

    // Group docs by folder_id
    const byFolder = {};
    const unfiled = [];
    (docs || []).forEach(d => {
      if (d.folder_id) {
        if (!byFolder[d.folder_id]) byFolder[d.folder_id] = [];
        byFolder[d.folder_id].push(d);
      } else {
        unfiled.push(d);
      }
    });

<<<<<<< Updated upstream
    renderDocFolderList(docs);
  } catch(e) {
    console.warn('Could not load documents', e);
  }
}

function renderDocFolderList(docs) {
  const container = document.getElementById('docs-folders-list');
  if (!docs?.length && !folders?.length) {
    container.innerHTML = `<div style="font-size:12px;color:var(--text-muted);padding:8px 4px">No documents yet</div>`;
    return;
  }

  let html = '';

  // Render each folder group
  (folders || []).forEach(f => {
    const folderDocs = docs.filter(d => d.folder_id === f.id);
    const isOpen = true; // default open
    html += `
    <div class="folder-group" data-folder-id="${f.id}">
      <div class="folder-header ${isOpen ? 'open' : ''}"
           onclick="toggleFolderGroup(this, ${f.id})"
           ondragover="event.preventDefault(); this.classList.add('drag-over')"
           ondragleave="this.classList.remove('drag-over')"
           ondrop="onDropToFolder(event, ${f.id})">
        <span class="folder-dot" style="background:${f.color}"></span>
        <span class="folder-chevron">▶</span>
        <span class="folder-name">${escapeHtml(f.name)}</span>
        <span class="folder-count">${folderDocs.length}</span>
        <div class="folder-actions">
          <button class="folder-action-btn" onclick="event.stopPropagation(); openRenameFolderModal(${f.id}, '${escapeHtml(f.name)}', '${f.color}')" title="Rename">✏️</button>
          <button class="folder-action-btn danger" onclick="event.stopPropagation(); deleteFolder(${f.id})" title="Delete folder">🗑</button>
        </div>
      </div>
      <div class="folder-docs ${isOpen ? 'open' : ''}" id="folder-docs-${f.id}">
        ${folderDocs.length
          ? folderDocs.map(doc => docItemHtml(doc)).join('')
          : `<div style="font-size:11px;color:var(--text-muted);padding:4px 8px;">Empty folder</div>`}
      </div>
    </div>`;
  });

  // Unorganised docs (no folder)
  const unorg = docs.filter(d => !d.folder_id);
  if (unorg.length) {
    html += `<div class="unorg-section">
      <div class="unorg-header">Unorganised</div>
      ${unorg.map(doc => docItemHtml(doc)).join('')}
    </div>`;
  }

  if (!html) {
    html = `<div style="font-size:12px;color:var(--text-muted);padding:8px 4px">No documents yet</div>`;
  }

  container.innerHTML = html;
}

function docItemHtml(doc) {
  const subjects  = Array.isArray(doc.subject) ? doc.subject : (doc.subject ? [doc.subject] : ['General']);
  const primary   = subjects[0] || 'General';
  const color     = SUBJECT_COLORS[primary] || SUBJECT_COLORS['General'];
  const subBadge  = `<span style="background:${color}20;color:${color};border:1px solid ${color};padding:2px 5px;border-radius:4px;font-size:9px;font-weight:600;">${primary}${subjects.length>1?` +${subjects.length-1}`:''}</span>`;
  return `
  <div class="doc-item" draggable="true"
       ondragstart="onDragDocStart(event, ${doc.id})"
       onclick="previewDoc(${doc.id}, '${escapeHtml(doc.filename)}')">
    <span class="doc-icon">📄</span>
    <div style="flex:1;min-width:0;">
      <div class="doc-name" title="${escapeHtml(doc.filename)}">${escapeHtml(doc.filename)}</div>
      ${subBadge}
    </div>
    <div class="doc-actions">
      <button class="doc-action-btn" onclick="event.stopPropagation(); openMoveDocModal(${doc.id})" title="Move to folder">📂</button>
      <button class="doc-action-btn danger" onclick="deleteDoc(${doc.id}, event)" title="Delete">✕</button>
    </div>
  </div>`;
}

function toggleFolderGroup(headerEl, folderId) {
  headerEl.classList.toggle('open');
  const docsEl = document.getElementById(`folder-docs-${folderId}`);
  if (docsEl) docsEl.classList.toggle('open');
}

// ─── Drag-and-drop doc → folder ──────────────────────────
let _dragDocId = null;
function onDragDocStart(event, docId) {
  _dragDocId = docId;
  event.dataTransfer.effectAllowed = 'move';
}
async function onDropToFolder(event, folderId) {
  event.preventDefault();
  document.querySelectorAll('.folder-header').forEach(h => h.classList.remove('drag-over'));
  if (_dragDocId == null) return;
  await moveDocToFolder(_dragDocId, folderId);
  _dragDocId = null;
}

// Preview as segmented chunk cards + highlight the matched chunk
=======
    let html = '';

    // Render each folder
    folders.forEach(f => {
      const fDocs = byFolder[f.id] || [];
      const isCollapsed = collapsedFolders.has(f.id);
      html += `<div class="folder-group">
        <div class="folder-header" onclick="toggleFolder(${f.id})">
          <span class="folder-arrow ${isCollapsed ? '' : 'open'}">▶</span>
          <span class="folder-icon">📁</span>
          <span class="folder-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>
          <span class="folder-count">${fDocs.length}</span>
          <span class="folder-actions" onclick="event.stopPropagation()">
            <button onclick="event.stopPropagation(); uploadToFolder(${f.id})" title="Upload to this folder">📎</button>
            <button onclick="event.stopPropagation(); openRenameFolderModal(${f.id}, '${escapeHtml(f.name)}')" title="Rename">✏️</button>
            <button class="danger" onclick="event.stopPropagation(); deleteFolder(${f.id}, '${escapeHtml(f.name)}')" title="Delete folder">✕</button>
          </span>
        </div>
        <div class="folder-docs ${isCollapsed ? 'collapsed' : ''}" id="folder-docs-${f.id}" style="max-height:${isCollapsed ? '0' : (fDocs.length * 40 + 40) + 'px'}">
          ${fDocs.length === 0 ? '<div class="folder-empty-text">Empty folder — use 📎 to upload here</div>' : ''}
          ${fDocs.map(d => renderDocItem(d)).join('')}
        </div>
      </div>`;
    });

    if (unfiled.length > 0) {
      html += `<div class="unfiled-header">📂 Unfiled</div>`;
      html += unfiled.map(d => renderDocItem(d)).join('');
    }

    tree.innerHTML = html || '<div style="font-size:12px;color:var(--text-muted);padding:8px 4px">No documents yet</div>';
  } catch(e) { console.warn('Could not load documents', e); }
}

function renderDocItem(doc) {
  const subjects = Array.isArray(doc.subject) ? doc.subject : (doc.subject ? [doc.subject] : []);
  const primary = subjects[0] || '';
  const color = SUBJECT_COLORS[primary] || SUBJECT_COLORS['General'];
  const badge = primary ? `<span class="subject-badge-sm" style="background:${color}20;color:${color};">${primary}</span>` : '';
  return `
    <div class="doc-item" onclick="previewDoc(${doc.id}, '${escapeHtml(doc.filename)}')">
      <span class="doc-icon">📄</span>
      <span class="doc-name" title="${escapeHtml(doc.filename)}">${escapeHtml(doc.filename)}</span>
      ${badge}
      <span class="doc-actions" onclick="event.stopPropagation()">
        <button onclick="event.stopPropagation(); showMoveMenu(${doc.id}, event)" title="Move to folder">📁</button>
        <button class="danger" onclick="event.stopPropagation(); deleteDoc(${doc.id})" title="Delete">✕</button>
      </span>
    </div>`;
}

function toggleFolder(folderId) {
  if (collapsedFolders.has(folderId)) collapsedFolders.delete(folderId);
  else collapsedFolders.add(folderId);
  loadDocuments();
}

function uploadToFolder(folderId) {
  const inp = document.createElement('input');
  inp.type = 'file'; inp.accept = '.pdf,.docx,.pptx,.txt';
  inp.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file || !currentUser) return;
    await uploadDocumentFromSidebar(file, folderId);
  };
  inp.click();
}

>>>>>>> Stashed changes
async function previewDoc(docId, filename, opts = {}) {
  try {
    const res = await fetch(`${API}/api/documents/${docId}?limit=200`);
    const data = await res.json();
    if (!res.ok) { openDocModal(filename, `<div style="color:var(--text-muted)">${escapeHtml(data.error || "Preview failed")}</div>`); return; }
    const chunks = data.chunks || [];
    const needle = opts.needle || '';
    const chunkOrder = opts.chunkOrder !== null && opts.chunkOrder !== undefined ? Number(opts.chunkOrder) : null;
    const tip = `<div style="color:var(--text-muted);margin-bottom:10px;">${chunkOrder !== null ? `Highlighting chunk <b>#${chunkOrder}</b>…` : 'Click a source to auto-highlight its chunk.'}</div>`;
    const cards = chunks.map(c => {
      const isHit = (chunkOrder !== null && c.chunk_order === chunkOrder) || (chunkOrder === null && needle && (c.content||'').includes(needle));
      const page = c.metadata?.source?.page;
      const charCount = c.len || (c.content||'').length;
      return `<div class="chunk-card ${isHit ? 'highlight' : ''}" data-chunk="${c.chunk_order}">
        <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
          <div style="font-weight:600;color:var(--accent);">Chunk ${c.chunk_order}</div>
          <div style="font-size:11px;color:var(--text-muted);">${page != null ? 'p.' + page + ' · ' : ''}${charCount} chars</div>
        </div>
        <div style="white-space:pre-wrap;font-size:12px;">${escapeHtml(c.content||'')}</div>
      </div>`;
    }).join('');
    openDocModal(filename, tip + cards);
    setTimeout(() => {
      const target = document.querySelector('#doc-modal-body .chunk-card.highlight');
      if (target) target.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }, 60);
  } catch { openDocModal(filename, '<div style="color:var(--text-muted)">Backend unreachable.</div>'); }
}

async function deleteDoc(docId) {
  if (!confirm('Delete this document and all its chunks?')) return;
  try {
    const res = await fetch(`${API}/api/documents/${docId}`, { method: 'DELETE' });
    if (res.ok) { showToast('🗑️', 'Document deleted.', 'success'); loadDocuments(); }
    else showToast('❌', 'Delete failed.', 'error');
  } catch { showToast('❌', 'Backend unreachable.', 'error'); }
}

// ── Links ──
let pendingLinks = [];
function addLink() {
  const inp = document.getElementById('link-input');
  const url = (inp.value || '').trim();
  if (!url) return;
  try { const p = new URL(url); if (p.protocol !== 'https:') { showToast('⚠️', 'Only HTTPS links.', 'warning'); return; } }
  catch { showToast('❌', 'Invalid URL.', 'error'); return; }
  pendingLinks.push(url); inp.value = ''; renderLinkList();
}
function removeLink(i) { pendingLinks.splice(i, 1); renderLinkList(); }
function renderLinkList() {
  const el = document.getElementById('link-list');
  if (!el) return;
  el.innerHTML = pendingLinks.map((u, i) => `<div class="link-item"><span>${escapeHtml(u)}</span><button onclick="removeLink(${i})">✕</button></div>`).join('');
}
async function ingestLinks() {
  if (!currentUser) { showToast('❌', 'Please log in first.', 'error'); return; }
  if (!pendingLinks.length) { showToast('🔗', 'No links added.', 'warning'); return; }
  showToast('⏳', 'Ingesting links…', '');
  const res = await fetch(`${API}/api/links/ingest`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ urls: pendingLinks, user_id: currentUser.id })
  });
  const data = await res.json();
  if (!res.ok) { showToast('❌', data.error || 'Link ingest failed.', 'error'); return; }
  const ok = data.ingested?.length || 0;
  const bad = data.rejected?.length || 0;
  if (ok > 0) showToast('✅', `Ingested ${ok} link(s)${bad > 0 ? `, ${bad} rejected` : ''}`, ok > 0 && bad > 0 ? 'warning' : 'success');
  else { showToast('❌', 'All links rejected.', 'error'); return; }
  pendingLinks = []; renderLinkList(); loadDocuments();
}

// ══════════════════════════════════════════════
// TOOL RENDERING
// ══════════════════════════════════════════════
function renderToolPanel(tool) {
  if (!tool) return '';
  const id = 'tool-' + Date.now() + '-' + Math.random().toString(36).slice(2, 7);
  if (tool.type === 'mermaid') {
    return `<div class="tool-panel" data-tool-id="${id}">
      <div class="tool-panel-header"><span>🔀 Diagram</span>
        <div class="download-group">
          <button class="tool-download-btn" onclick="downloadMermaid('${id}','svg')">⬇ SVG</button>
          <button class="tool-download-btn" onclick="downloadMermaid('${id}','png')">⬇ PNG</button>
        </div>
      </div>
      <div class="mermaid-container" id="${id}"><div class="mermaid">${escapeHtml(tool.code)}</div></div>
    </div>`;
  }
  return '';
}
function initMermaidInElement(el) {
  const nodes = el.querySelectorAll('.mermaid:not([data-processed])');
  if (nodes.length > 0) mermaid.run({ nodes: Array.from(nodes) });
}
async function downloadMermaid(id, format) {
  const container = document.getElementById(id);
  if (!container) return;
  const svg = container.querySelector('svg');
  if (!svg) return alert('Diagram not ready.');
  if (format === 'svg') {
    const blob = new Blob([new XMLSerializer().serializeToString(svg)], { type: 'image/svg+xml' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'diagram.svg'; a.click();
  } else {
    const bbox = svg.getBoundingClientRect();
    const canvas = document.createElement('canvas'); canvas.width = bbox.width * 2; canvas.height = bbox.height * 2;
    const ctx = canvas.getContext('2d'); ctx.scale(2, 2); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, bbox.width, bbox.height);
    const img = new Image();
    img.onload = () => { ctx.drawImage(img, 0, 0, bbox.width, bbox.height); canvas.toBlob(b => { const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'diagram.png'; a.click(); }, 'image/png'); };
    img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(new XMLSerializer().serializeToString(svg))));
  }
}

// ══════════════════════════════════════════════
// QUERY
// ══════════════════════════════════════════════
async function sendQuery() {
  const textarea = document.getElementById('query-input');
  const query = textarea.value.trim();
  if (!query) return;
  document.getElementById('welcome')?.remove();
  await ensureSession();
<<<<<<< Updated upstream

  appendMessage('user', null, query);
=======
  const userMsgId = appendMessage('user', null, query);
>>>>>>> Stashed changes
  textarea.value = ''; autoResize(textarea);
  const loadingId = appendMessage('bot', null, 'Thinking…', true);
  startStageProgress(loadingId);
  renderSources(null);
  document.getElementById('sources-empty').style.display = 'block';

  try {
    const payload = { question: query, web_search: webSearchEnabled, diagram: diagramEnabled };
    if (currentSession) payload.session_id = currentSession;
<<<<<<< Updated upstream
    // Include chat scope folder IDs if set
    if (chatScopeFolderIds.length > 0) {
      payload.folder_ids = chatScopeFolderIds;
    }
    const res  = await fetch(`${API}/api/query`, {
=======
    if (scopedFolderIds.length > 0) payload.folder_ids = scopedFolderIds;

    const res = await fetch(`${API}/api/query`, {
>>>>>>> Stashed changes
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(currentToken ? { 'Authorization': `Bearer ${currentToken}` } : {}) },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
<<<<<<< Updated upstream
=======

    if (data.metadata && data.metadata.query_rewritten) {
      const userMsgEl = document.getElementById(userMsgId);
      if (userMsgEl) {
        const rewriteHtml = `
          <div class="query-rewrite-toggle" onclick="toggleRewriteDetails('${userMsgId}')">
            <span class="rewrite-icon">✨</span><span class="rewrite-label">Query was rewritten</span><span class="rewrite-arrow">▼</span>
          </div>
          <div class="query-rewrite-details" id="${userMsgId}-rewrite" style="display:none;">
            <div class="rewrite-detail-item"><div class="rewrite-detail-label">Original:</div><div class="rewrite-detail-value">${escapeHtml(data.metadata.original_query)}</div></div>
            <div class="rewrite-detail-item"><div class="rewrite-detail-label">Rewritten:</div><div class="rewrite-detail-value">${escapeHtml(data.metadata.rewritten_query)}</div></div>
            <div class="rewrite-detail-item"><div class="rewrite-detail-label">Strategy:</div><div class="rewrite-detail-value"><span class="rewrite-strategy-badge">${escapeHtml(data.metadata.rewrite_strategy)}</span></div></div>
            ${data.metadata.score_improvement != null ? `<div class="rewrite-detail-item"><div class="rewrite-detail-label">Improvement:</div><div class="rewrite-detail-value rewrite-score-positive">+${data.metadata.score_improvement.toFixed(2)}</div></div>` : ''}
          </div>`;
        const body = userMsgEl.querySelector('.message-body');
        if (body) body.insertAdjacentHTML('beforeend', rewriteHtml);
      }
    }

>>>>>>> Stashed changes
    const answer = data.answer || data.response || data.message || JSON.stringify(data);
    const toolHtml = renderToolPanel(data.tool || null);
    updateMessage(loadingId, answer, toolHtml);
    if (data.sources) renderSources(data.sources);
    if (currentSession && currentToken) loadSessions();
  } catch(e) {
    updateMessage(loadingId, '❌ Could not reach the backend. Is Flask running?');
  }
}

// ══════════════════════════════════════════════
// MESSAGE HELPERS
// ══════════════════════════════════════════════
<<<<<<< Updated upstream
function appendMessage(role, docName, text, isLoading = false) {
  const id  = `msg-${++msgCounter}`;
=======
function appendMessage(role, docName, text, isLoading = false, rewriteMetadata = null) {
  const id = `msg-${++msgCounter}`;
>>>>>>> Stashed changes
  const win = document.getElementById('chat-window');
  const isUser = role === 'user';
  const div = document.createElement('div');
  div.className = 'message'; div.id = id;
<<<<<<< Updated upstream
=======
  let rewriteHtml = '';
  if (isUser && rewriteMetadata && rewriteMetadata.query_rewritten) {
    rewriteHtml = `
      <div class="query-rewrite-toggle" onclick="toggleRewriteDetails('${id}')">
        <span class="rewrite-icon">✨</span><span class="rewrite-label">Query was rewritten</span><span class="rewrite-arrow">▼</span>
      </div>
      <div class="query-rewrite-details" id="${id}-rewrite" style="display:none;">
        <div class="rewrite-detail-item"><div class="rewrite-detail-label">Original:</div><div class="rewrite-detail-value">${escapeHtml(rewriteMetadata.original_query)}</div></div>
        <div class="rewrite-detail-item"><div class="rewrite-detail-label">Rewritten:</div><div class="rewrite-detail-value">${escapeHtml(rewriteMetadata.rewritten_query || text)}</div></div>
        <div class="rewrite-detail-item"><div class="rewrite-detail-label">Strategy:</div><div class="rewrite-detail-value"><span class="rewrite-strategy-badge">${escapeHtml(rewriteMetadata.rewrite_strategy || 'auto')}</span></div></div>
        ${rewriteMetadata.score_improvement != null ? `<div class="rewrite-detail-item"><div class="rewrite-detail-label">Improvement:</div><div class="rewrite-detail-value rewrite-score-positive">+${rewriteMetadata.score_improvement.toFixed(2)}</div></div>` : ''}
      </div>`;
  }
>>>>>>> Stashed changes
  div.innerHTML = `
    <div class="avatar ${isUser ? 'user' : 'bot'}">${isUser ? '👤' : '🤖'}</div>
    <div class="message-body">
      <div class="message-role">${isUser ? 'You' : 'RAG Assistant'}</div>
      ${docName ? `<div class="message-doc-badge">📄 ${escapeHtml(docName)}</div>` : ''}
      <div class="message-text ${isLoading ? 'loading' : ''} ${isUser ? 'plain' : 'md'}">${isUser ? escapeHtml(text) : renderMarkdown(text)}</div>
    </div>`;
  win.appendChild(div);
  win.scrollTop = win.scrollHeight;
  return id;
}

function updateMessage(id, text, toolHtml = '') {
  const el = document.getElementById(id);
  const textEl = el ? el.querySelector('.message-text') : null;
  if (textEl) { textEl.innerHTML = renderMarkdown(text) + toolHtml; textEl.classList.remove('loading'); initMermaidInElement(textEl); }
  return el;
}

<<<<<<< Updated upstream
=======
function toggleRewriteDetails(messageId) {
  const d = document.getElementById(`${messageId}-rewrite`);
  const t = document.querySelector(`#${messageId} .rewrite-arrow`);
  if (d && t) { const v = d.style.display !== 'none'; d.style.display = v ? 'none' : 'block'; t.textContent = v ? '▼' : '▲'; }
}

>>>>>>> Stashed changes
// ══════════════════════════════════════════════
// NEW CHAT
// ══════════════════════════════════════════════
function newChat() {
  currentSession = null;
  document.getElementById('chat-window').innerHTML = `
    <div id="welcome">
      <div class="welcome-icon">💬</div>
      <h2>Ask your documents anything</h2>
      <p>Upload files and organize them into folders.<br>Select folders to scope your conversation, then ask questions.</p>
    </div>`;
  document.getElementById('query-input').value = '';
  renderSources(null);
}

// ══════════════════════════════════════════════
// UTILITY
// ══════════════════════════════════════════════
function escapeHtml(str) {
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderMarkdown(text) {
  marked.setOptions({ breaks: true, gfm: true, headerIds: false, mangle: false });
  const raw = marked.parse(text);
  const sanitized = DOMPurify.sanitize(raw, {
    ADD_TAGS: ['math','semantics','mrow','mi','mo','mn','msup','msub','mfrac','msqrt','mroot','annotation'],
    ADD_ATTR: ['xmlns']
  });
  const div = document.createElement('div');
  div.innerHTML = sanitized;
  if (typeof renderMathInElement !== 'undefined') {
    try {
      renderMathInElement(div, {
        delimiters: [
          { left: '$$', right: '$$', display: true }, { left: '$', right: '$', display: false },
          { left: '\\[', right: '\\]', display: true }, { left: '\\(', right: '\\)', display: false }
        ],
        throwOnError: false, trust: true, ignoredTags: [], ignoredClasses: []
      });
    } catch(e) { console.warn('LaTeX error:', e); }
  }
  return div.innerHTML;
}

function handleKey(e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendQuery(); } }
function autoResize(el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 160) + 'px'; }

function showToast(icon, msg, type) {
  const toast = document.getElementById('upload-toast');
  document.getElementById('toast-icon').textContent = icon;
  document.getElementById('toast-msg').textContent = msg;
  toast.className = `visible ${type}`;
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => { toast.className = ''; }, 3500);
}

function startStageProgress(messageId) {
  const el = document.querySelector(`#${messageId} .message-text`);
  if (!el) return;
  const stages = [{ msg: 'Retrieving relevant chunks…' }, { msg: 'Reranking for best matches…' }, { msg: 'Generating answer…' }];
  let i = 0;
  stageTimer = setInterval(() => { if (i >= stages.length) return clearInterval(stageTimer); el.innerHTML = renderMarkdown(stages[i].msg); i++; }, 700);
}

function openDocModal(title, bodyHtml) {
  document.getElementById('doc-modal-title').textContent = title || 'Document';
  document.getElementById('doc-modal-body').innerHTML = bodyHtml || 'No preview.';
  document.getElementById('doc-modal').style.display = 'flex';
}
function closeDocModal() { document.getElementById('doc-modal').style.display = 'none'; }
document.getElementById('doc-modal')?.addEventListener('click', e => { if (e.target.id === 'doc-modal') closeDocModal(); });

function toggleWebSearch() {
  webSearchEnabled = !webSearchEnabled;
  showToast('🌐', webSearchEnabled ? 'Web search enabled' : 'Web search disabled', 'success');
  _syncAddMenuState();
}
function toggleAddMenu() {
  const menu = document.getElementById('add-menu');
  const btn = document.getElementById('add-btn');
  const open = menu.style.display === 'none' || menu.style.display === '';
  menu.style.display = open ? 'block' : 'none';
  btn.classList.toggle('active', open);
  if (open) setTimeout(() => document.addEventListener('click', _closeAddMenu, { once: true }), 0);
}
function _closeAddMenu(e) {
  const wrap = document.querySelector('.add-btn-wrap');
  if (wrap && wrap.contains(e.target)) return;
  document.getElementById('add-menu').style.display = 'none';
  document.getElementById('add-btn').classList.remove('active');
}
function selectWebSearch() {
  toggleWebSearch();
  document.getElementById('add-menu').style.display = 'none';
  document.getElementById('add-btn').classList.remove('active');
}
function selectDiagram() {
  diagramEnabled = !diagramEnabled;
  document.getElementById('diagram-check').style.display = diagramEnabled ? 'inline' : 'none';
  document.getElementById('diagram-pill').style.display = diagramEnabled ? 'inline-flex' : 'none';
  document.getElementById('add-menu').style.display = 'none';
  _syncAddMenuState();
  showToast('🔀', diagramEnabled ? 'Diagram mode on' : 'Diagram mode off', 'success');
}
function selectQuiz() {
  document.getElementById('add-menu').style.display = 'none';
  document.getElementById('add-btn').classList.remove('active');
  openQuizModal();
}
function _syncAddMenuState() {
  const pill = document.getElementById('web-pill');
  const check = document.getElementById('web-check');
  const features = document.getElementById('active-features');
  if (pill) pill.style.display = webSearchEnabled ? 'inline-flex' : 'none';
  if (check) check.style.display = webSearchEnabled ? 'inline' : 'none';
  const anyActive = webSearchEnabled || diagramEnabled || scopedFolderIds.length > 0;
  if (features) features.style.display = anyActive ? 'flex' : 'none';
}

// ══════════════════════════════════════════════
// QUIZ
// ══════════════════════════════════════════════
let _currentQuiz = null, _quizAnswers = {}, _quizSubmitted = false;

function openQuizModal() {
  closeQuiz();
  document.getElementById('quiz-modal-overlay').classList.add('visible');
  document.getElementById('quiz-error').textContent = '';
<<<<<<< Updated upstream

  // Populate folder scope state
  setQuizScope(_quizScope);

  const note = document.getElementById('quiz-scope-note');
  if (_quizScope === 'all') {
    if (currentUser) note.textContent = `📂 Quiz will use all your uploaded documents.`;
    else note.textContent = `ℹ️ Log in to scope the quiz to your documents.`;
  }
=======
  renderFolderChecklist('quiz-folder-checklist', scopedFolderIds);
  const note = document.getElementById('quiz-scope-note');
  if (!currentUser) note.textContent = 'ℹ️ Log in to scope quiz to your documents.';
  else note.textContent = folders.length > 0 ? '' : 'ℹ️ Create folders to scope quiz content.';
>>>>>>> Stashed changes
}
function closeQuizModal() { document.getElementById('quiz-modal-overlay').classList.remove('visible'); }
document.getElementById('quiz-modal-overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('quiz-modal-overlay')) closeQuizModal();
});

async function generateQuiz() {
  const btn = document.getElementById('quiz-generate-btn');
  const errEl = document.getElementById('quiz-error');
  errEl.textContent = '';
  const numQ = parseInt(document.getElementById('quiz-num').value) || 5;
  const diff = document.getElementById('quiz-difficulty').value;
  const qType = document.getElementById('quiz-type').value;
  const topic = document.getElementById('quiz-topic').value.trim();
<<<<<<< Updated upstream

  // Determine document / folder scope
  let docIds     = [];
  let folderIds  = [];

  if (_quizScope === 'all') {
    // use all docs (no filter)
  } else if (_quizScope === 'folders') {
    folderIds = [..._quizFolderIds];
  } else if (_quizScope === 'chat') {
    folderIds = [...chatScopeFolderIds];
=======
  const quizFolderIds = [];
  document.querySelectorAll('#quiz-folder-checklist input[type="checkbox"]').forEach(cb => {
    if (cb.checked) quizFolderIds.push(parseInt(cb.value));
  });
  let docIds = [];
  if (currentSession) {
    try { const r = await authFetch(`/api/sessions/${currentSession}`); const d = await r.json(); docIds = d.document_ids || []; } catch {}
>>>>>>> Stashed changes
  }
  btn.disabled = true; btn.textContent = 'Generating…';
  try {
<<<<<<< Updated upstream
    const res  = await authFetch('/api/quiz/generate', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({
        num_questions: numQ,
        difficulty   : diff,
        question_type: qType,
        topic        : topic,
        document_ids : docIds,
        folder_ids   : folderIds,
      }),
=======
    const payload = { num_questions: numQ, difficulty: diff, question_type: qType, topic, document_ids: docIds };
    if (quizFolderIds.length > 0) payload.folder_ids = quizFolderIds;
    const res = await authFetch('/api/quiz/generate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
>>>>>>> Stashed changes
    });
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.error || 'Failed to generate quiz.'; return; }
    closeQuizModal(); _startQuiz(data.quiz);
  } catch { errEl.textContent = 'Could not reach the backend.'; }
  finally { btn.disabled = false; btn.textContent = 'Generate Quiz'; }
}

function _startQuiz(quiz) {
  _currentQuiz = quiz; _quizAnswers = {}; _quizSubmitted = false;
  quiz.questions.forEach(q => { _quizAnswers[q.id] = new Set(); });
  const view = document.getElementById('quiz-view');
  view.style.display = 'flex';
  document.getElementById('quiz-results').style.display = 'none';
  document.getElementById('quiz-results').classList.remove('visible');
  document.getElementById('quiz-footer').style.display = 'block';
  document.getElementById('quiz-questions').style.display = 'flex';
  const cfg = quiz.config;
  document.getElementById('quiz-badge').textContent = `${cfg.difficulty} · ${cfg.question_type.replace('_', '-')}`;
  document.getElementById('quiz-progress').textContent = `${quiz.questions.length} question${quiz.questions.length !== 1 ? 's' : ''}`;
  const container = document.getElementById('quiz-questions');
  container.innerHTML = '';
  quiz.questions.forEach((q, idx) => container.appendChild(_buildQuestionCard(q, idx + 1)));
}

function _buildQuestionCard(q, num) {
  const isMulti = q.type === 'multi_select';
  const card = document.createElement('div');
  card.className = 'quiz-card'; card.id = `quiz-card-${q.id}`;
  card.innerHTML = `
    <div class="quiz-card-header">
      <span class="quiz-q-num">Q${num}</span>
      <span class="quiz-q-type-badge">${isMulti ? 'multi-select' : 'single answer'}</span>
      <span class="quiz-q-text">${q.question}</span>
    </div>
    <div class="quiz-options" id="quiz-opts-${q.id}">
      ${q.options.map(opt => {
        const label = opt.charAt(0);
        return `<div class="quiz-option" id="quiz-opt-${q.id}-${label}" onclick="selectOption(${q.id},'${label}',${isMulti})">
          <span class="opt-label">${label}</span><span>${opt.slice(3)}</span></div>`;
      }).join('')}
    </div>
    <div class="quiz-explanation" id="quiz-exp-${q.id}">💡 ${q.explanation}</div>`;
  return card;
}

function selectOption(qId, label, isMulti) {
  if (_quizSubmitted) return;
  const answers = _quizAnswers[qId];
  if (isMulti) { if (answers.has(label)) answers.delete(label); else answers.add(label); }
  else { answers.clear(); answers.add(label); }
  const q = _currentQuiz.questions.find(x => x.id === qId);
  q.options.forEach(opt => {
    const l = opt.charAt(0);
    document.getElementById(`quiz-opt-${qId}-${l}`).classList.toggle('selected', answers.has(l));
  });
}

function submitQuiz() {
  if (!_currentQuiz) return;
  _quizSubmitted = true;
  let correct = 0;
  _currentQuiz.questions.forEach(q => {
    const ua = _quizAnswers[q.id], ca = new Set(q.correct);
    const ok = ua.size === ca.size && [...ua].every(a => ca.has(a));
    if (ok) correct++;
    q.options.forEach(opt => {
      const l = opt.charAt(0), el = document.getElementById(`quiz-opt-${q.id}-${l}`);
      el.classList.add('locked'); el.classList.remove('selected');
      if (ua.has(l) && ca.has(l)) el.classList.add('correct');
      else if (ua.has(l)) el.classList.add('wrong');
      else if (ca.has(l)) el.classList.add('missed');
    });
    document.getElementById(`quiz-exp-${q.id}`).classList.add('visible');
  });
  document.getElementById('quiz-footer').style.display = 'none';
  document.getElementById('quiz-questions').style.display = 'none';
  _showResults(correct, _currentQuiz.questions.length);
}

function _showResults(correct, total) {
  const pct = Math.round((correct / total) * 100);
  const msg = pct === 100 ? '🏆 Perfect!' : pct >= 80 ? '🎉 Great job!' : pct >= 60 ? '👍 Good effort!' : pct >= 40 ? '📚 Keep studying!' : '💪 Try again!';
  document.getElementById('quiz-score-banner').innerHTML = `
    <div class="score-number">${correct}/${total}</div>
    <div class="score-label">${pct}% correct</div>
    <div class="score-msg">${msg}</div>`;
  const review = document.getElementById('quiz-review');
  review.innerHTML = '';
  _currentQuiz.questions.forEach((q, idx) => {
    const ua = _quizAnswers[q.id], ca = new Set(q.correct);
    const ok = ua.size === ca.size && [...ua].every(a => ca.has(a));
    const card = document.createElement('div'); card.className = 'quiz-card';
    card.innerHTML = `
      <div class="quiz-card-header"><span class="quiz-q-num">Q${idx+1}</span><span style="font-size:13px">${ok ? '✅' : '❌'}</span><span class="quiz-q-text">${q.question}</span></div>
      <div style="font-size:12px;color:var(--text-muted);margin-bottom:6px">
        Your answer: <strong style="color:var(--text-primary)">${[...ua].join(', ') || '—'}</strong> | Correct: <strong style="color:var(--accent)">${q.correct.join(', ')}</strong></div>
      <div class="quiz-explanation visible">💡 ${q.explanation}</div>`;
    review.appendChild(card);
  });
  const r = document.getElementById('quiz-results');
  r.style.display = 'flex'; r.classList.add('visible');
}

function closeQuiz() {
<<<<<<< Updated upstream
  const view = document.getElementById('quiz-view');
  if (view) view.style.display = 'none';
  _currentQuiz   = null;
  _quizAnswers   = {};
  _quizSubmitted = false;
}
// ══════════════════════════════════════════════════════════════
//  FOLDER MANAGEMENT
// ══════════════════════════════════════════════════════════════

async function loadFolders() {
  if (!currentToken) { folders = []; return; }
  try {
    const res  = await authFetch('/api/folders/');
    const data = await res.json();
    folders = data.folders || [];
    await loadDocuments(); // re-render with folder info
    updateScopePill();
  } catch(e) {
    console.warn('Could not load folders', e);
  }
}

// ── Create/Rename Modal ─────────────────────────────────────

function openCreateFolderModal() {
  _folderModalMode = 'create';
  _folderModalId   = null;
  _folderColor     = FOLDER_COLORS[Math.floor(Math.random() * FOLDER_COLORS.length)];
  document.getElementById('folder-modal-title').textContent = '📁 New Folder';
  document.getElementById('folder-name-input').value = '';
  renderColorPicker('folder-color-picker', _folderColor, c => { _folderColor = c; });
  document.getElementById('folder-modal-overlay').style.display = 'flex';
  setTimeout(() => document.getElementById('folder-name-input').focus(), 100);
}

function openRenameFolderModal(id, name, color) {
  _folderModalMode = 'rename';
  _folderModalId   = id;
  _folderColor     = color || '#6c63ff';
  document.getElementById('folder-modal-title').textContent = '✏️ Rename Folder';
  document.getElementById('folder-name-input').value = name;
  renderColorPicker('folder-color-picker', _folderColor, c => { _folderColor = c; });
  document.getElementById('folder-modal-overlay').style.display = 'flex';
  setTimeout(() => document.getElementById('folder-name-input').focus(), 100);
}

function closeFolderModal() {
  document.getElementById('folder-modal-overlay').style.display = 'none';
}

async function submitFolderModal() {
  const name = document.getElementById('folder-name-input').value.trim();
  if (!name) { showToast('error', 'Folder name cannot be empty.'); return; }

  if (_folderModalMode === 'create') {
    await createFolder(name, _folderColor);
  } else {
    await renameFolder(_folderModalId, name, _folderColor);
  }
  closeFolderModal();
}

async function createFolder(name, color) {
  try {
    const res  = await authFetch('/api/folders/', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ name, color }),
    });
    const data = await res.json();
    if (!res.ok) { showToast('error', data.error || 'Failed to create folder'); return; }
    showToast('success', `Folder "${name}" created.`);
    await loadFolders();
  } catch(e) { showToast('error', 'Could not reach backend.'); }
}

async function renameFolder(id, name, color) {
  try {
    const res  = await authFetch(`/api/folders/${id}`, {
      method : 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ name, color }),
    });
    const data = await res.json();
    if (!res.ok) { showToast('error', data.error || 'Failed to rename folder'); return; }
    showToast('success', `Folder renamed to "${name}".`);
    await loadFolders();
  } catch(e) { showToast('error', 'Could not reach backend.'); }
}

async function deleteFolder(id) {
  const folder = folders.find(f => f.id === id);
  if (!confirm(`Delete folder "${folder?.name || id}"? Documents will not be deleted.`)) return;
  try {
    const res = await authFetch(`/api/folders/${id}`, { method: 'DELETE' });
    if (!res.ok) { showToast('error', 'Failed to delete folder'); return; }
    // Remove from scope if selected
    chatScopeFolderIds = chatScopeFolderIds.filter(fid => fid !== id);
    showToast('success', 'Folder deleted.');
    await loadFolders();
    updateScopePill();
  } catch(e) { showToast('error', 'Could not reach backend.'); }
}

// ── Move Document to Folder ─────────────────────────────────

function openMoveDocModal(docId) {
  _moveDocId      = docId;
  _moveDocFolderId = null;
  const listEl = document.getElementById('move-doc-folder-list');
  listEl.innerHTML = [
    { id: null, name: 'No folder (unorganised)', color: '#6b7280', doc_count: 0 },
    ...folders
  ].map(f => `
    <label class="folder-check-item">
      <input type="radio" name="move-folder-radio" value="${f.id ?? ''}"
             onchange="_moveDocFolderId = ${f.id === null ? 'null' : f.id}">
      <span class="fci-dot" style="background:${f.color}"></span>
      <span class="fci-name">${escapeHtml(f.name)}</span>
      <span class="fci-count">${f.doc_count ?? ''}</span>
    </label>`).join('');
  document.getElementById('move-doc-modal-overlay').style.display = 'flex';
}

function closeMoveDocModal() {
  document.getElementById('move-doc-modal-overlay').style.display = 'none';
}

async function applyMoveDoc() {
  if (_moveDocId == null) { closeMoveDocModal(); return; }
  await moveDocToFolder(_moveDocId, _moveDocFolderId);
  closeMoveDocModal();
}

async function moveDocToFolder(docId, folderId) {
  try {
    const res = await fetch(`${API}/api/documents/${docId}`, {
      method : 'PATCH',
      headers: {
        'Content-Type' : 'application/json',
        ...(currentToken ? { 'Authorization': `Bearer ${currentToken}` } : {})
      },
      body: JSON.stringify({ folder_id: folderId }),
    });
    if (!res.ok) { showToast('error', 'Failed to move document'); return; }
    const folder = folders.find(f => f.id === folderId);
    showToast('success', `Moved to "${folder ? folder.name : 'Unorganised'}".`);
    await loadDocuments();
  } catch(e) { showToast('error', 'Could not reach backend.'); }
}

// ── Chat Scope Modal ───────────────────────────────────────

function openScopeModal() {
  const listEl = document.getElementById('scope-folder-list');
  if (!folders.length) {
    listEl.innerHTML = `<div style="font-size:13px;color:var(--text-muted);padding:12px 0">
      No folders yet. Create one using the + Folder button.</div>`;
  } else {
    listEl.innerHTML = folders.map(f => `
      <label class="folder-check-item">
        <input type="checkbox" value="${f.id}"
               ${chatScopeFolderIds.includes(f.id) ? 'checked' : ''}>
        <span class="fci-dot" style="background:${f.color}"></span>
        <span class="fci-name">${escapeHtml(f.name)}</span>
        <span class="fci-count">${f.doc_count} doc${f.doc_count !== 1 ? 's' : ''}</span>
      </label>`).join('');
  }
  document.getElementById('scope-modal-overlay').style.display = 'flex';
}

function closeScopeModal() {
  document.getElementById('scope-modal-overlay').style.display = 'none';
}

function applyScope() {
  const checks = document.querySelectorAll('#scope-folder-list input[type=checkbox]:checked');
  chatScopeFolderIds = Array.from(checks).map(c => parseInt(c.value));
  closeScopeModal();
  updateScopePill();
}

function clearScope() {
  chatScopeFolderIds = [];
  updateScopePill();
}

function updateScopePill() {
  const pill      = document.getElementById('scope-pill');
  const pillLabel = document.getElementById('scope-pill-label');
  const statusEl  = document.getElementById('scope-status');
  const featBar   = document.getElementById('active-features');

  if (chatScopeFolderIds.length === 0) {
    pill && (pill.style.display = 'none');
    if (statusEl) statusEl.textContent = 'All documents';
    // hide active-features if no other pills visible
    checkFeaturesBar();
    return;
  }

  const names = chatScopeFolderIds.map(id => {
    const f = folders.find(x => x.id === id);
    return f ? f.name : `#${id}`;
  });
  const label = names.length > 2 ? `${names.slice(0,2).join(', ')} +${names.length-2}` : names.join(', ');

  if (pillLabel) pillLabel.textContent = label;
  if (pill) pill.style.display = '';
  if (statusEl) statusEl.textContent = label;
  if (featBar) featBar.style.display = '';
}

function checkFeaturesBar() {
  const bar = document.getElementById('active-features');
  if (!bar) return;
  const anyVisible = Array.from(bar.querySelectorAll('.feature-pill'))
    .some(el => el.style.display !== 'none');
  bar.style.display = anyVisible ? '' : 'none';
}

// ── Quiz scope helpers ─────────────────────────────────────

function setQuizScope(mode) {
  _quizScope = mode;
  document.getElementById('quiz-scope-all').classList.toggle('active', mode === 'all');
  document.getElementById('quiz-scope-folders').classList.toggle('active', mode === 'folders');
  document.getElementById('quiz-scope-chat').classList.toggle('active', mode === 'chat');

  const picker = document.getElementById('quiz-folder-picker');
  if (mode === 'folders') {
    picker.style.display = '';
    renderQuizFolderPicker();
  } else {
    picker.style.display = 'none';
  }

  const note = document.getElementById('quiz-scope-note');
  if (mode === 'chat') {
    if (chatScopeFolderIds.length === 0) {
      note.textContent = 'Chat scope is currently "All documents".';
    } else {
      const names = chatScopeFolderIds.map(id => folders.find(f=>f.id===id)?.name || `#${id}`).join(', ');
      note.textContent = `Will use chat scope: ${names}`;
    }
  } else {
    note.textContent = '';
  }
}

function renderQuizFolderPicker() {
  const listEl = document.getElementById('quiz-folder-list');
  if (!folders.length) {
    listEl.innerHTML = `<div style="font-size:12px;color:var(--text-muted)">No folders yet.</div>`;
    return;
  }
  listEl.innerHTML = folders.map(f => `
    <label class="folder-check-item">
      <input type="checkbox" value="${f.id}"
             ${_quizFolderIds.includes(f.id) ? 'checked' : ''}
             onchange="toggleQuizFolder(${f.id}, this.checked)">
      <span class="fci-dot" style="background:${f.color}"></span>
      <span class="fci-name">${escapeHtml(f.name)}</span>
      <span class="fci-count">${f.doc_count} doc${f.doc_count!==1?'s':''}</span>
    </label>`).join('');
}

function toggleQuizFolder(id, checked) {
  if (checked) { if (!_quizFolderIds.includes(id)) _quizFolderIds.push(id); }
  else         { _quizFolderIds = _quizFolderIds.filter(x => x !== id); }
}

// Populate quiz folder picker whenever quiz modal opens
const _origOpenQuizModal = window.openQuizModal;
function openQuizModal() {
  if (_origOpenQuizModal) _origOpenQuizModal();
  else {
    document.getElementById('quiz-modal-overlay').style.display = 'flex';
  }
  setQuizScope(_quizScope); // refresh state
}
window.openQuizModal = openQuizModal;

// ── Colour picker helper ───────────────────────────────────

function renderColorPicker(containerId, selected, onChange) {
  const el = document.getElementById(containerId);
  el.innerHTML = FOLDER_COLORS.map(c => `
    <div class="color-swatch ${c === selected ? 'selected' : ''}"
         style="background:${c}"
         onclick="pickColor('${containerId}', '${c}', pickColorCb_${containerId})"></div>
  `).join('');
  window[`pickColorCb_${containerId}`] = onChange;
}

function pickColor(containerId, color, cb) {
  document.querySelectorAll(`#${containerId} .color-swatch`).forEach(s => {
    s.classList.toggle('selected', s.style.background === color || s.style.backgroundColor === color);
  });
  if (cb) cb(color);
}

// Close modals on overlay click
document.addEventListener('click', e => {
  if (e.target.id === 'folder-modal-overlay') closeFolderModal();
  if (e.target.id === 'scope-modal-overlay')  closeScopeModal();
  if (e.target.id === 'move-doc-modal-overlay') closeMoveDocModal();
});

// Reload folders after login
const _origRestoreSession = window.restoreSession;
const _afterAuthHook = async () => { if (currentToken) await loadFolders(); };
=======
  const v = document.getElementById('quiz-view'); if (v) v.style.display = 'none';
  _currentQuiz = null; _quizAnswers = {}; _quizSubmitted = false;
}
>>>>>>> Stashed changes
