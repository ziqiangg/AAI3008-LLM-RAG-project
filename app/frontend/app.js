//RAG Learning Assistant - Main JavaScript


const API = 'http://localhost:5000';

// ── Mermaid init ───────────────────────────────────────
mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'loose' });

let webSearchEnabled = false;
let diagramEnabled = false;

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
let messages       = [];
let msgCounter     = 0;
let authMode       = 'login';   // 'login' | 'register'
let currentUser    = null;      // { id, username, email }
let currentToken   = localStorage.getItem('rag_token') || null;
let currentSession = null;      // active session id
let toastTimeout   = null;      // toast notification timer
let stageTimer     = null;      // loading stage progress timer

// ── Bootstrap ─────────────────────────────────
window.addEventListener('load', () => {
  loadDocuments();
  if (currentToken) restoreSession();
  loadFolders();
});

// ══════════════════════════════════════════════
// HEALTH CHECK (Optional - removed from bootstrap)
// ══════════════════════════════════════════════
async function checkHealth() {
  try {
    const res = await fetch(`${API}/api/health`);
    if (res.ok) {
      console.log('✓ Backend is healthy');
      return true;
    }
  } catch (e) {
    console.warn('Backend health check failed:', e);
    return false;
  }
}

let activeSource = null;

// Subject classification constants
const SUBJECT_COLORS = {
  'Math': '#3b82f6',
  'Computer Science': '#10b981',
  'Artificial Intelligence': '#8b5cf6',
  'Physics': '#ef4444',
  'Chemistry': '#f59e0b',
  'Biology': '#14b8a6',
  'Language Learning': '#ec4899',
  'Geography': '#84cc16',
  'Economics': '#06b6d4',
  'Social Studies': '#f97316',
  'Computer Systems': '#6366f1',
  'General': '#6b7280'
};

const VALID_SUBJECTS = [
  'Math', 'Computer Science', 'Artificial Intelligence', 'Physics', 
  'Chemistry', 'Biology', 'Language Learning', 'Geography', 
  'Economics', 'Social Studies', 'Computer Systems', 'General'
];

// Keep doc maps so Sources can open the right doc
window._docsById = {};
window._docIdByFilename = {};

function setActiveSource(i) {
  const sources = (window._lastSources || []);
  activeSource = sources[i] || null;

  // Visually mark active source
  document.querySelectorAll('.source-card').forEach((el, idx) => {
    el.classList.toggle('active', idx === i);
  });

  // Auto-open the document + highlight the chunk
  if (activeSource) {
    const docId =
      activeSource.doc_id ||
      (activeSource.filename ? window._docIdByFilename[activeSource.filename] : null);

    if (docId) {
      const filename = activeSource.filename || (window._docsById[docId]?.filename ?? `Document ${docId}`);
      previewDoc(docId, filename, {
        chunkOrder: activeSource.chunk_order ?? null,
        needle: activeSource.content || activeSource.snippet || ""
      });
    } else {
      showToast('✅', 'Source selected. (No doc_id/filename mapping found to auto-open preview.)', 'success');
    }
  } else {
    showToast('✅', 'No source selected', 'success');
  }
}

// ══════════════════════════════════════════════
// AUTH
// ══════════════════════════════════════════════
function openAuthModal() {
  if (currentUser) { showUserMenu(); return; }
  document.getElementById('modal-overlay').classList.add('visible');
  document.getElementById('auth-error').textContent = '';
}

function closeAuthModal() {
  document.getElementById('modal-overlay').classList.remove('visible');
}

// Close on backdrop click
document.getElementById('modal-overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('modal-overlay')) closeAuthModal();
});

function switchAuthTab(mode) {
  authMode = mode;
  const isLogin = mode === 'login';
  document.getElementById('tab-login-btn').classList.toggle('active',    isLogin);
  document.getElementById('tab-register-btn').classList.toggle('active', !isLogin);
  document.getElementById('modal-title').textContent   = isLogin ? 'Welcome back' : 'Create account';
  document.getElementById('auth-submit').textContent   = isLogin ? 'Login' : 'Register';
  document.getElementById('auth-username').style.display = isLogin ? 'none' : '';
  document.getElementById('auth-error').textContent = '';
}

async function submitAuth() {
  const btn      = document.getElementById('auth-submit');
  const errEl    = document.getElementById('auth-error');
  const email    = document.getElementById('auth-email').value.trim();
  const password = document.getElementById('auth-password').value;
  const username = document.getElementById('auth-username').value.trim();

  errEl.textContent = '';
  if (!email || !password) { errEl.textContent = 'Please fill in all fields.'; return; }

  btn.disabled = true;
  btn.textContent = authMode === 'login' ? 'Logging in…' : 'Registering…';

  try {
    const body  = authMode === 'login'
      ? { email, password }
      : { email, password, username };
    const res   = await fetch(`${API}/api/users/${authMode}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data  = await res.json();

    if (!res.ok) { errEl.textContent = data.error || 'Something went wrong.'; return; }

    // Success
    currentToken = data.token;
    currentUser  = data.user;
    localStorage.setItem('rag_token', currentToken);
    
    // Always clear fields after request is sent
    email.value = '';
    password.value  = '';
    username.value  = '';
    closeAuthModal();
    updateAuthButton();
    loadSessions();
    loadDocuments();
    loadFolders();
    showToast('👋', `Welcome, ${currentUser.username}!`, 'success');
  } catch {
    errEl.textContent = 'Could not reach the backend.';
  } finally {
    btn.disabled = false;
    btn.textContent = authMode === 'login' ? 'Login' : 'Register';
  }
}

async function restoreSession() {
  try {
    const res  = await authFetch('/api/users/me');
    const data = await res.json();
    if (res.ok) {
      currentUser = data.user;
      updateAuthButton();
      loadSessions();
      loadFolders();
    } else {
      logout();
    }
  } catch { logout(); }
}

function logout() {
  currentToken = null; currentUser = null;
  const email    = document.getElementById('auth-email');
  const password = document.getElementById('auth-password');
  const username = document.getElementById('auth-username');
  email.value = '';
  password.value = '';
  username.value = '';
  localStorage.removeItem('rag_token');
  updateAuthButton();
  // Reload page to clear all state and return to clean login screen
  setTimeout(() => window.location.reload(), 100);
  document.getElementById('session-list').innerHTML =
    `<div style="font-size:12px;color:var(--text-muted);text-align:center;padding:20px 8px">Log in to view your session history.</div>`;
  showToast('👋', 'Logged out.', '');

  const list = document.getElementById('docs-list');
  list.innerHTML = `<div style="font-size:12px;color:var(--text-muted);padding:8px 4px">
    Log in to view your documents.
  </div>`;
}

function updateAuthButton() {
  const icon  = document.getElementById('auth-btn-icon');
  const label = document.getElementById('auth-btn-label');
  if (currentUser) {
    icon.textContent  = '';
    // Show first letter avatar
    icon.innerHTML = `<span class="auth-avatar">${currentUser.username[0].toUpperCase()}</span>`;
    label.textContent = currentUser.username;
  } else {
    icon.textContent  = '🔑';
    label.textContent = 'Login';
  }
}

function showUserMenu() {
  // Toggle: close if already open
  const existing = document.getElementById('user-dropdown');
  if (existing) { existing.remove(); return; }

  const btn = document.getElementById('auth-btn');
  const rect = btn.getBoundingClientRect();

  const dropdown = document.createElement('div');
  dropdown.id = 'user-dropdown';
  dropdown.className = 'user-dropdown';
  dropdown.style.top  = (rect.bottom + window.scrollY + 8) + 'px';
  dropdown.style.right = (window.innerWidth - rect.right) + 'px';
  dropdown.innerHTML = `
    <button class="user-dropdown-item" onclick="confirmLogout()">🚪 Logout</button>
    <div class="user-dropdown-divider"></div>
    <button class="user-dropdown-item danger" onclick="confirmDeleteAccount()">🗑️ Delete Account</button>
  `;
  document.body.appendChild(dropdown);

  // Close when clicking anywhere outside
  setTimeout(() => document.addEventListener('click', closeUserDropdown, { once: true }), 0);
}

function closeUserDropdown() {
  const d = document.getElementById('user-dropdown');
  if (d) d.remove();
}

function confirmLogout() {
  closeUserDropdown();
  if (!confirm('Are you sure you want to log out?')) return;
  logout();
}

async function confirmDeleteAccount() {
  closeUserDropdown();
  if (!confirm(
    `Delete your account?\n\nThis will permanently remove all your documents, sessions, and messages.\n\nThis action cannot be undone.`
  )) return;

  try {
    const res = await authFetch('/api/users/me', { method: 'DELETE' });
    if (res.ok) {
      showToast('🗑️', 'Account deleted. Goodbye!', 'success');
      setTimeout(() => logout(), 1200);
    } else {
      const data = await res.json();
      showToast('❌', data.error || 'Failed to delete account.', 'error');
    }
  } catch {
    showToast('❌', 'Could not reach the backend.', 'error');
  }
}

// Authenticated fetch helper
async function authFetch(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (currentToken) headers['Authorization'] = `Bearer ${currentToken}`;
  return fetch(`${API}${path}`, { ...opts, headers });
}

// ══════════════════════════════════════════════
// RIGHT PANEL — TAB SWITCHER
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

  const list  = document.getElementById('sources-list');
  const empty = document.getElementById('sources-empty');

  if (!sources || sources.length === 0) {
    list.innerHTML  = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  // Sort sources by rerank score (highest first) for better UX
  const sortedSources = [...sources].sort((a, b) => (b.score || 0) - (a.score || 0));

  list.innerHTML = sortedSources.map((s, i) => {
    const page = s.metadata?.source?.page;
    const pageDisplay = page != null ? ` • Page ${page}` : '';
    
    // Citation label: Show [S{citation_index}] to match LLM references
    const citationLabel = s.citation_index ? `<span style="background:#2196F3; color:white; padding:2px 6px; border-radius:4px; font-size:10px; font-weight:700; margin-right:6px;">[S${s.citation_index}]</span>` : '';
    
    // Extract subject for badge
    const dominantSubject = s.metadata?.dominant_subject || 'General';
    const subjectColor = SUBJECT_COLORS[dominantSubject] || SUBJECT_COLORS['General'];
    const subjectBadge = `<span style="background:${subjectColor}20; color:${subjectColor}; padding:2px 6px; border-radius:4px; font-size:10px; font-weight:600; margin-left:6px;">${dominantSubject}</span>`;
    const isWeb = (s.source_type === 'web') || (s.metadata?.source_type === 'web');
    const icon = isWeb ? '🌐' : '📄';
    const title = isWeb ? (s.title || s.filename || `Web Source ${i+1}`) : (s.filename || s.doc_id || `Source ${i+1}`);
    const url = s.url || s.metadata?.url;

    const clickable = isWeb && url ? `onclick="openWebSource('${url}', ${i})"` : `onclick="setActiveSource(${i})"`;
    return `
    <div class="source-card" ${clickable} title="${escapeHtml(s.content || '')}">
    <div class="source-file">${citationLabel}${icon} ${escapeHtml(title)}${pageDisplay}${subjectBadge}</div>
    <div class="source-snippet">${escapeHtml((s.content || s.snippet || '').slice(0, 200))}</div>
      <div class="source-score">
        <span>${s.score != null ? (s.score * 100).toFixed(0) + '% match' : ''}</span>
        ${s.score != null ? `<div class="score-bar"><div class="score-fill" style="width:${(s.score*100).toFixed(0)}%"></div></div>` : ''}
      </div>
    </div>
  `;
  }).join('');
}

// ══════════════════════════════════════════════
// SESSIONS
// ══════════════════════════════════════════════
async function loadSessions() {
  if (!currentToken) return;
  try {
    const res  = await authFetch('/api/sessions/');
    const data = await res.json();
    const list = document.getElementById('session-list');
    if (!data.sessions?.length) {
      list.innerHTML = `<div style="font-size:12px;color:var(--text-muted);text-align:center;padding:20px 8px">No sessions yet. Start a chat!</div>`;
      return;
    }
    list.innerHTML = data.sessions.map(s => `
      <div class="session-item" onclick="loadSession(${s.id})" title="${escapeHtml(s.title)}">
        <span class="session-icon">💬</span>
        <span class="session-title">${escapeHtml(s.title || 'Untitled')}</span>
        <button class="session-del" onclick="deleteSession(${s.id}, event)" title="Delete session">✕</button>
      </div>`
    ).join('');
  } catch(e) { console.warn('Could not load sessions', e); }
}

async function loadSession(sessionId) {
  try {
    const res  = await authFetch(`/api/sessions/${sessionId}`);
    const data = await res.json();
    if (!res.ok) return;
    currentSession = sessionId;
    
    // Clear and replay messages
    const win = document.getElementById('chat-window');
    win.innerHTML = '';
    
    // Track the last sources from assistant messages
    let lastSources = null;
    (data.messages || []).forEach(m => {
      appendMessage(m.role === 'user' ? 'user' : 'bot', null, m.content);
      // Extract sources from assistant messages
      if (m.role === 'assistant' && m.sources) {
        lastSources = m.sources;
      }
    });
    
    // Display the most recent sources
    if (lastSources) {
      renderSources(lastSources.chunks || lastSources);
    } else {
      renderSources(null);
    }
    
    // Switch to sources tab
    document.querySelectorAll('.right-tab')[0].click();
  } catch(e) { console.warn('Could not load session', e); }
}

async function ensureSession() {
  if (currentSession || !currentToken) return;
  try {
    const res  = await authFetch('/api/sessions/', {
      method: 'POST', body: JSON.stringify({ title: 'New Chat' }),
    });
    const data = await res.json();
    if (res.ok) { currentSession = data.session.id; loadSessions(); }
  } catch(e) { console.warn('Could not create session', e); }
}

async function deleteSession(sessionId, e) {
  e.stopPropagation(); // Prevent loadSession from firing
  if (!confirm('Delete this chat session and all its messages?')) return;
  try {
    const res = await authFetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
    if (res.ok) {
      showToast('🗑️', 'Session deleted.', 'success');
      
      // If deleted session is currently active, clear the chat
      if (currentSession === sessionId) {
        newChat(); // This clears currentSession and the chat window
      }
      
      // Refresh session list
      loadSessions();
    } else {
      showToast('❌', 'Delete failed.', 'error');
    }
  } catch {
    showToast('❌', 'Backend unreachable.', 'error');
  }
}

// ══════════════════════════════════════════════
// DOCUMENTS
// ══════════════════════════════════════════════ 
function triggerSidebarUpload() {
  document.getElementById('sidebar-file-input').click();
}
let pendingLinks = [];

function addLink() {
  const inp = document.getElementById("link-input");
  const url = (inp.value || "").trim();
  if (!url) return;
  
  // Basic URL validation
  try {
    const parsed = new URL(url);
    
    // Check if HTTPS
    if (parsed.protocol !== 'https:') {
      showToast("⚠️", "Warning: Only HTTPS links are accepted", "warning");
      return;
    }
    
    // Warn about potentially untrusted domains (soft warning)
    const trustedDomains = [
      'wikipedia.org', 'github.com', 'stackoverflow.com', 'arxiv.org',
      'docs.python.org', 'developer.mozilla.org', 'geeksforgeeks.org',
      'medium.com', 'openai.com', 'cloud.google.com', 'aws.amazon.com',
      'pypi.org', 'zhihu.com', 'csdn.net', 'baidu.com', 'jianshu.com',
      'oschina.net', 'raw.githubusercontent.com'
    ];
    
    const hostname = parsed.hostname.toLowerCase();
    const isTrusted = trustedDomains.some(domain => 
      hostname === domain || hostname.endsWith('.' + domain)
    );
    
    if (!isTrusted) {
      // Add with warning but don't block
      pendingLinks.push(url);
      inp.value = "";
      renderLinkList();
      showToast("⚠️", `Added link (domain may not be trusted: ${hostname})`, "warning");
      return;
    }
    
  } catch (e) {
    showToast("❌", "Invalid URL format", "error");
    return;
  }
  
  pendingLinks.push(url);
  inp.value = "";
  renderLinkList();
}

function removeLink(i) {
  pendingLinks.splice(i, 1);
  renderLinkList();
}

function renderLinkList() {
  const el = document.getElementById("link-list");
  if (!el) return;
  el.innerHTML = pendingLinks.map((u, i) => `
    <div class="link-item">
      <span>${escapeHtml(u)}</span>
      <button onclick="removeLink(${i})">✕</button>
    </div>
  `).join("");
}
async function ingestLinks() {
   if (!currentUser) {
    showToast("❌", "Please log in first.", "error");
    return;
  }
  if (!pendingLinks.length) {
    showToast("🔗", "No links added.", "warning");
    return;
  }
  showToast("⏳", "Ingesting links…", "");

  const res = await fetch(`${API}/api/links/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ urls: pendingLinks, user_id: currentUser.id })
  });
  const data = await res.json();
  if (!res.ok) {
    showToast("❌", data.error || "Link ingest failed", "error");
    return;
  }
  
  // Handle ingestion results
  const ingestedCount = data.ingested?.length || 0;
  const rejectedCount = data.rejected?.length || 0;
  
  if (ingestedCount > 0 && rejectedCount === 0) {
    // All links ingested successfully
    showToast("✅", `Ingested ${ingestedCount} link(s)`, "success");
  } else if (ingestedCount > 0 && rejectedCount > 0) {
    // Some succeeded, some failed
    showToast("⚠️", `Ingested ${ingestedCount} link(s), ${rejectedCount} rejected`, "warning");
    console.warn("Rejected links:", data.rejected);
  } else if (rejectedCount > 0) {
    // All links rejected
    const reasons = data.rejected.map(r => {
      const url = new URL(r.url).hostname;
      if (r.reason === "untrusted_or_invalid") return `${url}: Not in trusted domain list`;
      if (r.reason === "fetch_failed") return `${url}: Could not fetch page`;
      if (r.reason === "no_sections_extracted") return `${url}: No content found`;
      return `${url}: ${r.reason}`;
    }).join("\n");
    showToast("❌", `All links rejected:\n${reasons}`, "error");
    return; // Don't clear pending links
  }
  
  pendingLinks = [];
  renderLinkList();
  loadDocuments(); // refresh sidebar
}
async function onSidebarFileSelected(event) {
  const file = event.target.files[0];
  if (!file) return;

  // Optional: reset the input so selecting the same file again will trigger change
  event.target.value = '';

  // Reuse the same document upload logic as chat input
  await uploadDocumentFromSidebar(file);
}

async function uploadDocumentFromSidebar(file) {
  showToast('⏳', `Uploading ${file.name}…`, '');

  const formData = new FormData();
  formData.append('file', file);
  formData.append('subject', 'AAI3008');

  // Ensure uploads are owned by the logged-in user
  if (!currentUser) {
    showToast('❌', 'Please log in before uploading documents.', 'error');
    return;
  }
  formData.append('user_id', currentUser.id);

  try {
    const res  = await fetch(`${API}/api/documents/upload`, {
      method: 'POST',
      body: formData,
    });
    const data = await res.json();

    if (!res.ok) {
      showToast('❌', data.error || 'Upload failed.', 'error');
      return;
    }

    showToast('✅', `${file.name} ingested!`, 'success');
    loadDocuments();  // refresh left sidebar document list
  } catch (e) {
    showToast('❌', 'Upload failed — backend unreachable.', 'error');
  }
}


async function loadDocuments() {
  try {
    const res  = await fetch(`${API}/api/documents/`);
    const data = await res.json();
    const docs = data.documents || data || [];

    // Build maps for quick lookup by Sources click
    window._docsById = {};
    window._docIdByFilename = {};
    (docs || []).forEach(d => {
      window._docsById[d.id] = d;
      if (d.filename) window._docIdByFilename[d.filename] = d.id;
    });

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
async function previewDoc(docId, filename, opts = {}) {
  try {
    const limit = 200;
    const res = await fetch(`${API}/api/documents/${docId}?limit=${limit}`);
    const data = await res.json();

    if (!res.ok) {
      openDocModal(filename, `<div style="color:var(--text-muted)">${escapeHtml(data.error || "Preview failed")}</div>`);
      return;
    }

    const chunks = data.chunks || [];
    const needle = opts.needle || "";
    const chunkOrder = (opts.chunkOrder !== null && opts.chunkOrder !== undefined) ? Number(opts.chunkOrder) : null;

    const tip = `
      <div style="color:var(--text-muted); margin-bottom:10px;">
        ${chunkOrder !== null
          ? `Highlighting retrieved chunk <b>#${chunkOrder}</b>…`
          : (needle ? "Highlighting last selected source…" : "Tip: click a source to auto-open and highlight its chunk.")
        }
      </div>
    `;

    const cards = chunks.map(c => {
      const isHit =
        (chunkOrder !== null && c.chunk_order === chunkOrder) ||
        (chunkOrder === null && needle && (c.content || "").includes(needle));

      const page = c.metadata?.source?.page;
      const pageDisplay = page != null ? `Page ${page} • ` : '';
      const charCount = c.len || (c.content||'').length;
      
      // Extract subject/topic metadata
      const subjects = c.metadata?.subjects || [];
      const dominantSubject = c.metadata?.dominant_subject || 'General';
      const dominantTopic = c.metadata?.dominant_topic || '';
      
      // Build subject badges
      const subjectBadges = subjects.slice(0, 2).map(s => {
        const color = SUBJECT_COLORS[s.name] || SUBJECT_COLORS['General'];
        const confidence = Math.round((s.confidence || 0.5) * 100);
        return `<span style="background:${color}20; color:${color}; border:1px solid ${color}40; padding:2px 5px; border-radius:3px; font-size:9px; font-weight:600; margin-right:4px; display:inline-block;">${s.name} ${confidence}%</span>`;
      }).join('');
      
      // Topic display
      const topicDisplay = dominantTopic ? `<div style="font-size:10px; color:var(--text-muted); margin-top:2px;">🏷️ ${dominantTopic}</div>` : '';

      return `
        <div class="chunk-card ${isHit ? 'highlight' : ''}" data-chunk="${c.chunk_order}"
             style="border:1px solid var(--border); border-radius:10px; padding:10px 12px; margin-bottom:10px; background:var(--bg-input);">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:6px;">
            <div style="flex:1;">
              <div style="font-weight:600; color:var(--accent);">Chunk ${c.chunk_order}</div>
              ${subjectBadges ? `<div style="margin-top:4px;">${subjectBadges}</div>` : ''}
            </div>
            <div style="font-size:11px; color:var(--text-muted); text-align:right;">
              ${pageDisplay}${charCount} chars
              ${topicDisplay}
            </div>
          </div>
          <div style="white-space:pre-wrap;">${escapeHtml(c.content || "")}</div>
        </div>
      `;
    }).join('');

    openDocModal(filename, tip + cards);

    // Auto-scroll to highlighted chunk
    setTimeout(() => {
      const target = document.querySelector('#doc-modal-body .chunk-card.highlight');
      if (target) target.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }, 60);

  } catch {
    openDocModal(filename, `<div style="color:var(--text-muted)">Backend unreachable.</div>`);
  }
}

async function deleteDoc(docId, e) {
  e.stopPropagation();
  if (!confirm('Delete this document and all its chunks?')) return;
  try {
    const res = await fetch(`${API}/api/documents/${docId}`, { method: 'DELETE' });
    if (res.ok) { 
      showToast('🗑️', 'Document deleted.', 'success'); 
      loadDocuments();
      // Remove only sources from the deleted document, keep others
      const currentSources = window._lastSources || [];
      const filteredSources = currentSources.filter(s => s.document_id !== docId);
      renderSources(filteredSources.length > 0 ? filteredSources : null);
    }
    else { showToast('❌', 'Delete failed.', 'error'); }
  } catch { showToast('❌', 'Backend unreachable.', 'error'); }
}

// Edit document subject
function editDocumentSubject(docId, currentSubjects) {
  const subjectOptions = VALID_SUBJECTS.map(s => 
    `<option value="${s}" ${currentSubjects.includes(s) ? 'selected' : ''}>${s}</option>`
  ).join('');
  
  const modal = document.createElement('div');
  modal.style.cssText = 'position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.7); display:flex; align-items:center; justify-content:center; z-index:10000;';
  modal.innerHTML = `
    <div style="background:#2d2d2d; padding:24px; border-radius:12px; max-width:400px; width:90%; box-shadow:0 8px 32px rgba(0,0,0,0.5); border:1px solid #404040;">
      <h3 style="margin:0 0 16px 0; color:#ececec;">Edit Document Subject</h3>
      <p style="margin:0 0 12px 0; font-size:13px; color:#8e8ea0;">Select one or more subjects for this document:</p>
      <select id="subject-select" multiple size="8" style="width:100%; padding:8px; background:#1a1a1a; color:#ececec; border:1px solid #404040; border-radius:6px; font-size:13px;">
        ${subjectOptions}
      </select>
      <p style="margin:8px 0 16px 0; font-size:11px; color:#8e8ea0;">Hold Ctrl/Cmd to select multiple</p>
      <div style="display:flex; gap:8px; justify-content:flex-end;">
        <button onclick="this.closest('div[style*=fixed]').remove()" style="padding:8px 16px; background:#3a3a3a; color:#ececec; border:none; border-radius:6px; cursor:pointer; transition:background 0.2s;" onmouseover="this.style.background='#4a4a4a'" onmouseout="this.style.background='#3a3a3a'">Cancel</button>
        <button id="save-subject-btn" style="padding:8px 16px; background:#10a37f; color:white; border:none; border-radius:6px; cursor:pointer; font-weight:600; transition:background 0.2s;" onmouseover="this.style.background='#0d8a6c'" onmouseout="this.style.background='#10a37f'">Save</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  
  document.getElementById('save-subject-btn').onclick = async () => {
    const select = document.getElementById('subject-select');
    const selected = Array.from(select.selectedOptions).map(opt => opt.value);
    
    if (selected.length === 0) {
      showToast('❌', 'Please select at least one subject', 'error');
      return;
    }
    
    try {
      const res = await fetch(`${API}/api/documents/${docId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${currentToken}`
        },
        body: JSON.stringify({ subject: selected })
      });
      
      if (res.ok) {
        showToast('✅', 'Subject updated', 'success');
        loadDocuments();
        modal.remove();
      } else {
        const data = await res.json();
        showToast('❌', data.error || 'Update failed', 'error');
      }
    } catch (e) {
      showToast('❌', 'Connection error', 'error');
    }
  };
  
  modal.onclick = (e) => {
    if (e.target === modal) modal.remove();
  };
}

// ══════════════════════════════════════════════
// TOOL RENDERING (Mermaid / Desmos)
// ══════════════════════════════════════════════

function renderToolPanel(tool) {
  if (!tool) return '';
  const id = 'tool-' + Date.now() + '-' + Math.random().toString(36).slice(2, 7);

  if (tool.type === 'mermaid') {
    return `
      <div class="tool-panel" data-tool-id="${id}">
        <div class="tool-panel-header">
          <span>🔀 Diagram</span>
          <div class="download-group">
            <button class="tool-download-btn" onclick="downloadMermaid('${id}', 'svg')">⬇ SVG</button>
            <button class="tool-download-btn" onclick="downloadMermaid('${id}', 'png')">⬇ PNG</button>
            <button class="tool-download-btn" onclick="downloadMermaid('${id}', 'pdf')">⬇ PDF</button>
          </div>
        </div>
        <div class="mermaid-container" id="${id}">
          <div class="mermaid">${escapeHtml(tool.code)}</div>
        </div>
      </div>`;
  }

  if (tool.type === 'desmos') {
    return `
      <div class="tool-panel" data-tool-id="${id}">
        <div class="tool-panel-header">
          <span>📈 Graph</span>
          <div class="download-group">
            <button class="tool-download-btn" onclick="downloadDesmos('${id}')">⬇ PNG</button>
          </div>
        </div>
        <div class="desmos-container" id="${id}"></div>
      </div>
      <script>
        (function() {
          const el = document.getElementById('${id}');
          const calc = Desmos.GraphingCalculator(el, { expressions: true, keypad: false });
          window['desmos_${id}'] = calc;
          ${JSON.stringify(tool.expressions)}.forEach(function(latex, i) {
            calc.setExpression({ id: 'e' + i, latex: latex });
          });
        })();
      <\/script>`;
  }
  return '';
}

function initMermaidInElement(el) {
  // After HTML is in DOM, find any un-rendered .mermaid nodes and render them
  const nodes = el.querySelectorAll('.mermaid:not([data-processed])');
  if (nodes.length > 0) mermaid.run({ nodes: Array.from(nodes) });
}

async function downloadMermaid(id, format = 'svg') {
  const container = document.getElementById(id);
  if (!container) return alert('Diagram not ready yet.');
  const svg = container.querySelector('svg');
  if (!svg) return alert('Diagram not ready yet — please wait a moment.');

  if (format === 'svg') {
    const svgData = new XMLSerializer().serializeToString(svg);
    const blob = new Blob([svgData], { type: 'image/svg+xml' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `diagram.svg`;
    a.click();
    URL.revokeObjectURL(a.href);
    return;
  }

  if (format === 'png' || format === 'pdf') {
    const bbox = svg.getBoundingClientRect();
    const scale = 2;
    const canvas = document.createElement('canvas');
    canvas.width = bbox.width * scale;
    canvas.height = bbox.height * scale;
    const ctx = canvas.getContext('2d');
    ctx.scale(scale, scale);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, bbox.width, bbox.height);

    // Clone SVG with explicit namespace and dimensions
    const clone = svg.cloneNode(true);
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    clone.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink');
    clone.setAttribute('width', bbox.width);
    clone.setAttribute('height', bbox.height);

    // Inline all styles from stylesheets into the SVG
    const styles = Array.from(document.styleSheets)
      .flatMap(sheet => { try { return Array.from(sheet.cssRules); } catch { return []; } })
      .map(rule => rule.cssText)
      .join('\n');
    const styleEl = document.createElementNS('http://www.w3.org/2000/svg', 'style');
    styleEl.textContent = styles;
    clone.insertBefore(styleEl, clone.firstChild);

    const svgStr = new XMLSerializer().serializeToString(clone);
    const svgBase64 = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgStr)));

    const img = new Image();
    img.onload = () => {
      ctx.drawImage(img, 0, 0, bbox.width, bbox.height);

      if (format === 'png') {
        canvas.toBlob(blob => {
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = 'diagram.png';
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(a.href);
        }, 'image/png');

      } else {
        const imgData = canvas.toDataURL('image/png');
        const win = window.open('', '_blank');
        if (!win) { alert('Allow popups for PDF export.'); return; }
        win.document.write(`<!DOCTYPE html><html><head><title>Diagram</title>
          <style>*{margin:0;padding:0} body{display:flex;justify-content:center;align-items:center;min-height:100vh;background:#fff}
          img{max-width:100%} @media print{body{margin:0}}</style></head>
          <body><img src="${imgData}">
          <script>window.onload=()=>setTimeout(()=>window.print(),500)<\/script>
          </body></html>`);
        win.document.close();
      }
    };
    img.onerror = () => alert('Export failed. Try SVG instead.');
    img.src = svgBase64;
  }
}

function downloadDesmos(id) {
  const calc = window['desmos_' + id];
  if (!calc) return alert('Graph not ready yet.');
  calc.asyncScreenshot({ width: 800, height: 500, targetPixelRatio: 2 }, (dataUrl) => {
    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = 'graph.png';
    a.click();
  });
}

// ══════════════════════════════════════════════
// QUERY
// ══════════════════════════════════════════════
async function sendQuery() {
  const textarea = document.getElementById('query-input');
  const query    = textarea.value.trim();
  if (!query) return;

  document.getElementById('welcome')?.remove();

  await ensureSession();

  appendMessage('user', null, query);
  textarea.value = ''; autoResize(textarea);
  //loading messages
  const loadingId = appendMessage('bot', null, 'Thinking…', true);
  startStageProgress(loadingId);
  // Clear sources while loading
  renderSources(null);
  document.getElementById('sources-empty').style.display = 'block';

  try {

    const payload = { question: query, web_search: webSearchEnabled, diagram: diagramEnabled };
    if (currentSession) payload.session_id = currentSession;
    // Include chat scope folder IDs if set
    if (chatScopeFolderIds.length > 0) {
      payload.folder_ids = chatScopeFolderIds;
    }
    const res  = await fetch(`${API}/api/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(currentToken ? { 'Authorization': `Bearer ${currentToken}` } : {}) },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    const answer = data.answer || data.response || data.message || JSON.stringify(data);
    const toolHtml = renderToolPanel(data.tool || null);
    updateMessage(loadingId, answer, toolHtml);
    if (data.sources) renderSources(data.sources);

    // Reload sessions to update titles (messages already saved by query endpoint)
    if (currentSession && currentToken) {
      loadSessions();
    }
  } catch(e) {
    updateMessage(loadingId, '❌ Could not reach the backend. Is Flask running?');
  }
}

// ══════════════════════════════════════════════
// MESSAGE HELPERS
// ══════════════════════════════════════════════
function appendMessage(role, docName, text, isLoading = false) {
  const id  = `msg-${++msgCounter}`;
  const win = document.getElementById('chat-window');
  const isUser = role === 'user';
  const div = document.createElement('div');
  div.className = 'message'; div.id = id;
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
  const msgEl = document.getElementById(id);
  const textEl = msgEl ? msgEl.querySelector('.message-text') : null;
  if (textEl) {
    textEl.innerHTML = renderMarkdown(text) + toolHtml;
    textEl.classList.remove('loading');
    // Trigger Mermaid rendering on any diagram nodes just added to DOM
    initMermaidInElement(textEl);
  }
  return msgEl;  // return the message div for KaTeX re-render etc.
}

// ══════════════════════════════════════════════
// NEW CHAT
// ══════════════════════════════════════════════
function newChat() {
  currentSession = null;
  document.getElementById('chat-window').innerHTML = `
    <div id="welcome">
      <div class="welcome-icon">💬</div>
      <h2>Ask your documents anything</h2>
      <p>Upload documents using the sidebar, then ask questions about them.</p>
    </div>`;
  document.getElementById('query-input').value = '';
  renderSources(null);
}

// ══════════════════════════════════════════════
// UTILITY
// ══════════════════════════════════════════════
function escapeHtml(str) {
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function renderMarkdown(text) {
  // Configure marked options
  marked.setOptions({
    breaks: true,
    gfm: true,
    headerIds: false,
    mangle: false
  });
  
  // Parse markdown to HTML
  const rawHtml = marked.parse(text);
  
  // Sanitize to prevent XSS, but allow math elements
  const sanitized = DOMPurify.sanitize(rawHtml, {
    ADD_TAGS: ['math', 'semantics', 'mrow', 'mi', 'mo', 'mn', 'msup', 'msub', 'mfrac', 'msqrt', 'mroot', 'annotation'],
    ADD_ATTR: ['xmlns']
  });
  
  // Create container for rendering
  const tempDiv = document.createElement('div');
  tempDiv.innerHTML = sanitized;
  
  // Render LaTeX with KaTeX (auto-render handles finding and rendering LaTeX)
  if (typeof renderMathInElement !== 'undefined') {
    try {
      renderMathInElement(tempDiv, {
        delimiters: [
          {left: '$$', right: '$$', display: true},
          {left: '$', right: '$', display: false},
          {left: '\\[', right: '\\]', display: true},
          {left: '\\(', right: '\\)', display: false}
        ],
        throwOnError: false,
        trust: true,
        // Allow processing in all elements
        ignoredTags: [],
        ignoredClasses: []
      });
    } catch (e) {
      console.warn('LaTeX rendering failed:', e);
    }
  }
  
  return tempDiv.innerHTML;
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendQuery(); }
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}

function showToast(icon, msg, type) {
  const toast = document.getElementById('upload-toast');
  document.getElementById('toast-icon').textContent = icon;
  document.getElementById('toast-msg').textContent  = msg;
  toast.className = `visible ${type}`;
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => { toast.className = ''; }, 3500);
}

//loading messages
function startStageProgress(messageId) {
  const el = document.querySelector(`#${messageId} .message-text`);
  if (!el) return;

  const stages = [
    { t: 200,  msg: "Retrieving relevant chunks…" },
    { t: 900,  msg: "Reranking for best matches…" },
    { t: 1600, msg: "Generating answer…" }
  ];

  let i = 0;
  stageTimer = setInterval(() => {
    if (i >= stages.length) return clearInterval(stageTimer);
    el.innerHTML = renderMarkdown(stages[i].msg);
    i++;
  }, 700);
}

function stopStageProgress() {
  if (stageTimer) clearInterval(stageTimer);
  stageTimer = null;
}

function openDocModal(title, bodyHtml) {
  document.getElementById('doc-modal-title').textContent = title || 'Document';
  document.getElementById('doc-modal-body').innerHTML = bodyHtml || 'No preview available.';
  document.getElementById('doc-modal').style.display = 'flex';
}

function closeDocModal() {
  document.getElementById('doc-modal').style.display = 'none';
}

function toggleWebSearch() {
  webSearchEnabled = !webSearchEnabled;
  showToast('🌐', webSearchEnabled ? 'Web search enabled' : 'Web search disabled', 'success');
  _syncAddMenuState(); 
}

// ── Add menu toggle ────────────────────────────────────────
function toggleAddMenu() {
  const menu = document.getElementById('add-menu');
  const btn  = document.getElementById('add-btn');
  const open = menu.style.display === 'none' || menu.style.display === '';
  menu.style.display = open ? 'block' : 'none';
  btn.classList.toggle('active', open);

  if (open) {
    setTimeout(() => document.addEventListener('click', _closeAddMenu, { once: true }), 0);
  }
}

function _closeAddMenu(e) {
  const wrap = document.querySelector('.add-btn-wrap');
  if (wrap && wrap.contains(e.target)) return;
  document.getElementById('add-menu').style.display  = 'none';
  document.getElementById('add-btn').classList.remove('active');
}

// ── Web search option ──────────────────────────────────────
function selectWebSearch() {
  toggleWebSearch();                          // existing toggle logic
  _syncAddMenuState();
  document.getElementById('add-menu').style.display = 'none';
  document.getElementById('add-btn').classList.remove('active');
}

// ── Diagram option ──────────────────────────────────────
function selectDiagram() {
  diagramEnabled = !diagramEnabled;
  document.getElementById('diagram-check').style.display = diagramEnabled ? 'inline' : 'none';
  document.getElementById('diagram-pill').style.display  = diagramEnabled ? 'inline-flex' : 'none';
  document.getElementById('active-features').style.display = 
    (diagramEnabled || webSearchEnabled) ? 'flex' : 'none';
  document.getElementById('add-menu').style.display = 'none';  // replaces closeAddMenu()
  showToast('🔀', diagramEnabled ? 'Diagram mode enabled' : 'Diagram mode disabled', 'success');
}

// ── Quiz option ────────────────────────────────────────────
function selectQuiz() {
  document.getElementById('add-menu').style.display = 'none';
  document.getElementById('add-btn').classList.remove('active');
  openQuizModal();                            // existing quiz modal function
}

// ── Sync pill + checkmark with webSearchEnabled state ─────
function _syncAddMenuState() {
  const pill      = document.getElementById('web-pill');
  const check     = document.getElementById('web-check');
  const features  = document.getElementById('active-features');

  if (pill)  pill.style.display  = webSearchEnabled ? 'inline-flex' : 'none';
  if (check) check.style.display = webSearchEnabled ? 'inline'      : 'none';

  // Show/hide the features row
  const anyActive = webSearchEnabled;
  if (features) features.style.display = anyActive ? 'flex' : 'none';
}


function highlightText(fullText, needle) {
  if (!needle || needle.length < 20) return escapeHtml(fullText);

  // Escape regex chars
  const esc = needle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  // Keep it safe: limit needle length so we don't nuke performance
  const shortNeedle = needle.slice(0, 400);
  const escShort = shortNeedle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  const re = new RegExp(escShort, 'gi');
  const safeFull = escapeHtml(fullText);

  // Highlight by applying regex on the escaped full text is messy (entities change length),
  // so we do a simple approach: highlight on raw first, then escape in parts.
  const parts = fullText.split(new RegExp(`(${escShort})`, 'i'));

  return parts.map(p => {
    if (p.toLowerCase() === shortNeedle.toLowerCase()) {
      return `<mark style="background: rgba(16,163,127,0.35); color: inherit; padding: 0 2px; border-radius: 3px;">${escapeHtml(p)}</mark>`;
    }
    return escapeHtml(p);
  }).join('');
}
function openWebSource(url, idx) {
  setActiveSource(idx);
  window.open(url, "_blank", "noopener,noreferrer");
}
// Close when clicking outside modal
document.getElementById('doc-modal')?.addEventListener('click', (e) => {
  if (e.target.id === 'doc-modal') closeDocModal();
});

// ══════════════════════════════════════════════════════════
// QUIZ
// ══════════════════════════════════════════════════════════
let _currentQuiz    = null;
let _quizAnswers    = {};
let _quizSubmitted  = false;

function openQuizModal() {
  closeQuiz();
  const overlay = document.getElementById('quiz-modal-overlay');
  overlay.classList.add('visible');
  document.getElementById('quiz-error').textContent = '';

  // Populate folder scope state
  setQuizScope(_quizScope);

  const note = document.getElementById('quiz-scope-note');
  if (_quizScope === 'all') {
    if (currentUser) note.textContent = `📂 Quiz will use all your uploaded documents.`;
    else note.textContent = `ℹ️ Log in to scope the quiz to your documents.`;
  }
}

function closeQuizModal() {
  document.getElementById('quiz-modal-overlay').classList.remove('visible');
}

document.getElementById('quiz-modal-overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('quiz-modal-overlay')) closeQuizModal();
});

async function generateQuiz() {
  const btn   = document.getElementById('quiz-generate-btn');
  const errEl = document.getElementById('quiz-error');
  errEl.textContent = '';

  const numQ  = parseInt(document.getElementById('quiz-num').value) || 5;
  const diff  = document.getElementById('quiz-difficulty').value;
  const qType = document.getElementById('quiz-type').value;
  const topic = document.getElementById('quiz-topic').value.trim();

  // Determine document / folder scope
  let docIds     = [];
  let folderIds  = [];

  if (_quizScope === 'all') {
    // use all docs (no filter)
  } else if (_quizScope === 'folders') {
    folderIds = [..._quizFolderIds];
  } else if (_quizScope === 'chat') {
    folderIds = [...chatScopeFolderIds];
  }

  btn.disabled    = true;
  btn.textContent = 'Generating…';

  try {
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
    });
    const data = await res.json();

    if (!res.ok) {
      errEl.textContent = data.error || 'Failed to generate quiz.';
      return;
    }

    closeQuizModal();
    _startQuiz(data.quiz);

  } catch {
    errEl.textContent = 'Could not reach the backend.';
  } finally {
    btn.disabled    = false;
    btn.textContent = 'Generate Quiz';
  }
}

function _startQuiz(quiz) {
  _currentQuiz   = quiz;
  _quizAnswers   = {};
  _quizSubmitted = false;

  quiz.questions.forEach(q => { _quizAnswers[q.id] = new Set(); });

  const view = document.getElementById('quiz-view');
  view.style.display = 'flex';
  document.getElementById('quiz-results').style.display = 'none';
  document.getElementById('quiz-results').classList.remove('visible');
  document.getElementById('quiz-footer').style.display = 'block';
  document.getElementById('quiz-questions').style.display = 'flex';

  const cfg = quiz.config;
  document.getElementById('quiz-badge').textContent =
    `${cfg.difficulty} · ${cfg.question_type.replace('_', '-')}`;
  document.getElementById('quiz-progress').textContent =
    `${quiz.questions.length} question${quiz.questions.length !== 1 ? 's' : ''}`;

  const container = document.getElementById('quiz-questions');
  container.innerHTML = '';
  quiz.questions.forEach((q, idx) => {
    container.appendChild(_buildQuestionCard(q, idx + 1));
  });
}

function _buildQuestionCard(q, num) {
  const isMulti = q.type === 'multi_select';
  const card    = document.createElement('div');
  card.className = 'quiz-card';
  card.id = `quiz-card-${q.id}`;

  card.innerHTML = `
    <div class="quiz-card-header">
      <span class="quiz-q-num">Q${num}</span>
      <span class="quiz-q-type-badge">${isMulti ? 'multi-select' : 'single answer'}</span>
      <span class="quiz-q-text">${q.question}</span>
    </div>
    <div class="quiz-options" id="quiz-opts-${q.id}">
      ${q.options.map(opt => {
        const label = opt.charAt(0);
        return `
          <div class="quiz-option" id="quiz-opt-${q.id}-${label}"
               onclick="selectOption(${q.id}, '${label}', ${isMulti})">
            <span class="opt-label">${label}</span>
            <span>${opt.slice(3)}</span>
          </div>`;
      }).join('')}
    </div>
    <div class="quiz-explanation" id="quiz-exp-${q.id}">
      💡 ${q.explanation}
    </div>
  `;
  return card;
}

function selectOption(qId, label, isMulti) {
  if (_quizSubmitted) return;
  const answers = _quizAnswers[qId];

  if (isMulti) {
    if (answers.has(label)) answers.delete(label);
    else                    answers.add(label);
  } else {
    answers.clear();
    answers.add(label);
  }

  const q = _currentQuiz.questions.find(x => x.id === qId);
  q.options.forEach(opt => {
    const optLabel = opt.charAt(0);
    const el       = document.getElementById(`quiz-opt-${qId}-${optLabel}`);
    el.classList.toggle('selected', answers.has(optLabel));
  });
}

function submitQuiz() {
  if (!_currentQuiz) return;
  _quizSubmitted = true;

  let correct = 0;
  const questions = _currentQuiz.questions;

  questions.forEach(q => {
    const userAnswers    = _quizAnswers[q.id];
    const correctAnswers = new Set(q.correct);
    const isCorrect      =
      userAnswers.size === correctAnswers.size &&
      [...userAnswers].every(a => correctAnswers.has(a));

    if (isCorrect) correct++;

    q.options.forEach(opt => {
      const label      = opt.charAt(0);
      const el         = document.getElementById(`quiz-opt-${q.id}-${label}`);
      const isCorrectOpt = correctAnswers.has(label);
      const wasSelected  = userAnswers.has(label);

      el.classList.add('locked');
      el.classList.remove('selected');

      if (wasSelected && isCorrectOpt)  el.classList.add('correct');
      else if (wasSelected)             el.classList.add('wrong');
      else if (isCorrectOpt)            el.classList.add('missed');
    });

    document.getElementById(`quiz-exp-${q.id}`).classList.add('visible');
  });

  document.getElementById('quiz-footer').style.display    = 'none';
  document.getElementById('quiz-questions').style.display = 'none';
  _showResults(correct, questions.length);
}

function _showResults(correct, total) {
  const pct = Math.round((correct / total) * 100);
  const msg = pct === 100 ? '🏆 Perfect score!'
            : pct >= 80   ? '🎉 Great job!'
            : pct >= 60   ? '👍 Good effort!'
            : pct >= 40   ? '📚 Keep studying!'
            :                '💪 Review the material and try again!';

  document.getElementById('quiz-score-banner').innerHTML = `
    <div class="score-number">${correct}/${total}</div>
    <div class="score-label">${pct}% correct</div>
    <div class="score-msg">${msg}</div>
  `;

  const review = document.getElementById('quiz-review');
  review.innerHTML = '';
  _currentQuiz.questions.forEach((q, idx) => {
    const userAnswers    = _quizAnswers[q.id];
    const correctAnswers = new Set(q.correct);
    const isCorrect      =
      userAnswers.size === correctAnswers.size &&
      [...userAnswers].every(a => correctAnswers.has(a));

    const card = document.createElement('div');
    card.className = 'quiz-card';
    card.innerHTML = `
      <div class="quiz-card-header">
        <span class="quiz-q-num">Q${idx + 1}</span>
        <span style="font-size:13px">${isCorrect ? '✅' : '❌'}</span>
        <span class="quiz-q-text">${q.question}</span>
      </div>
      <div style="font-size:12px;color:var(--text-muted);margin-bottom:6px">
        Your answer: <strong style="color:var(--text-primary)">${[...userAnswers].join(', ') || '—'}</strong>
        &nbsp;|&nbsp;
        Correct: <strong style="color:var(--accent)">${q.correct.join(', ')}</strong>
      </div>
      <div class="quiz-explanation visible">💡 ${q.explanation}</div>
    `;
    review.appendChild(card);
  });

  const resultsEl = document.getElementById('quiz-results');
  resultsEl.style.display = 'flex';
  resultsEl.classList.add('visible');
}

function closeQuiz() {
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
