//RAG Learning Assistant - Main JavaScript


const API = 'http://localhost:5000';

// ── Mermaid init ───────────────────────────────────────
mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'loose' });

let webSearchEnabled = false;
let diagramEnabled = false;

// ── State ─────────────────────────────────────
let messages       = [];
let msgCounter     = 0;
let authMode       = 'login';   // 'login' | 'register'
let currentUser    = null;      // { id, username, email }
let currentToken   = localStorage.getItem('rag_token') || null;
let currentSession = null;      // active session id
let currentSessionMemory = null;
let memoryUnresolvedQuestions = [];
let memoryEntities = [];
let selectedMemoryUnresolvedIndex = -1;
let selectedMemoryEntityIndex = -1;
let toastTimeout   = null;      // toast notification timer
let stageTimer     = null;      // loading stage progress timer

// ── Folder & Document State ───────────────────
let folders = [];               // [{id, name, document_count, created_at}]
let documents = [];             // [{id, filename, folder_id, ...}]
let activeFilterFolders = [];   // [folder_id, ...] - persistent folder filter
let collapsedFolders = new Set(); // Set of collapsed folder IDs
const FILTER_STORAGE_KEY = 'rag_folder_filter';
const COLLAPSED_STORAGE_KEY = 'rag_collapsed_folders';

// ── Bootstrap ─────────────────────────────────
window.addEventListener('load', () => {
  loadFilterState();
  loadCollapsedState();
  loadDocuments();
  loadFolders();
  if (currentToken) restoreSession();
  
  // Close folder modals when clicking outside
  document.getElementById('create-folder-overlay')?.addEventListener('click', (e) => {
    if (e.target.id === 'create-folder-overlay') closeCreateFolderModal();
  });
  
  document.getElementById('rename-folder-overlay')?.addEventListener('click', (e) => {
    if (e.target.id === 'rename-folder-overlay') closeRenameFolderModal();
  });
  
  // Close link folder popup when clicking outside
  document.getElementById('link-folder-popup')?.addEventListener('click', (e) => {
    if (e.target.id === 'link-folder-popup') closeLinkFolderPopup();
  });
  
  // Close document folder popup when clicking outside
  document.getElementById('document-folder-popup')?.addEventListener('click', (e) => {
    if (e.target.id === 'document-folder-popup') closeDocumentFolderModal();
  });

  // Close memory modal when clicking outside
  document.getElementById('memory-modal-overlay')?.addEventListener('click', (e) => {
    if (e.target.id === 'memory-modal-overlay') closeMemoryModal();
  });
});

// ══════════════════════════════════════════════
// FOLDER FILTER STATE MANAGEMENT
// ══════════════════════════════════════════════

function loadFilterState() {
  try {
    const saved = localStorage.getItem(FILTER_STORAGE_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      activeFilterFolders = parsed.folder_ids || [];
    }
  } catch (e) {
    console.error('Failed to load filter state:', e);
  }
}

function saveFilterState() {
  try {
    localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify({
      folder_ids: activeFilterFolders,
      timestamp: Date.now()
    }));
  } catch (e) {
    console.error('Failed to save filter state:', e);
  }
}

function clearFilter() {
  activeFilterFolders = [];
  saveFilterState();
  updateFilterBadge();
  renderDocumentsTree();
}

function loadCollapsedState() {
  try {
    const saved = localStorage.getItem(COLLAPSED_STORAGE_KEY);
    if (saved) {
      const array = JSON.parse(saved);
      collapsedFolders = new Set(array);
    }
  } catch (e) {
    console.error('Failed to load collapsed state:', e);
  }
}

function saveCollapsedState() {
  try {
    localStorage.setItem(COLLAPSED_STORAGE_KEY, JSON.stringify([...collapsedFolders]));
  } catch (e) {
    console.error('Failed to save collapsed state:', e);
  }
}

function getFilteredDocumentIds() {
  // If folders/documents are filtered, return matching document IDs
  if (activeFilterFolders.length > 0) {
    const docIds = documents
      .filter(doc => {
        // Check if document is in a filtered folder
        if (doc.folder_id && activeFilterFolders.includes(doc.folder_id)) {
          return true;
        }
        // Check if this specific unfiled document is filtered
        if (!doc.folder_id && activeFilterFolders.includes(`unfiled-${doc.id}`)) {
          return true;
        }
        return false;
      })
      .map(doc => doc.id);
    return docIds.length > 0 ? docIds : null;
  }
  
  return null;  // null = use all documents
}

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
  closeAllModals();
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
    <button class="user-dropdown-item" onclick="openMemoryModal()">🧠 Session Memory</button>
    <div class="user-dropdown-divider"></div>
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
      // Check for rewrite metadata in user messages
      let rewriteMetadata = null;
      if (m.role === 'user' && m.sources && m.sources.query_rewritten) {
        rewriteMetadata = {
          query_rewritten: m.sources.query_rewritten,
          original_query: m.sources.original_query,
          rewritten_query: m.sources.rewritten_query,
          rewrite_strategy: m.sources.rewrite_strategy,
          score_improvement: m.sources.score_improvement
        };
      }
      
      appendMessage(m.role === 'user' ? 'user' : 'bot', null, m.content, false, rewriteMetadata);
      
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
let pendingLinkUrl = null; // Temporary storage for link before folder selection

function addLinkWithFolder() {
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
      // Store URL temporarily and show folder popup
      pendingLinkUrl = url;
      inp.value = "";
      openLinkFolderPopup();
      showToast("⚠️", `Domain may not be trusted: ${hostname}. Select folder to add.`, "warning");
      return;
    }
    
  } catch (e) {
    showToast("❌", "Invalid URL format", "error");
    return;
  }
  
  // Store URL temporarily and show folder popup
  pendingLinkUrl = url;
  inp.value = "";
  
  // Show folder selector popup
  openLinkFolderPopup();
}

function addLink() {
  addLinkWithFolder();
}

function openLinkFolderPopup() {
  closeAllModals();
  const popup = document.getElementById('link-folder-popup');
  const container = document.getElementById('link-folder-buttons');
  
  // Create buttons for each folder + Unfiled
  let html = `<button class="folder-select-btn" onclick="selectLinkFolder(null)">Unfiled</button>`;
  folders.forEach(folder => {
    html += `<button class="folder-select-btn" onclick="selectLinkFolder(${folder.id})">${escapeHtml(folder.name)}</button>`;
  });
  container.innerHTML = html;
  
  popup.style.display = 'block';
}

function closeLinkFolderPopup() {
  document.getElementById('link-folder-popup').style.display = 'none';
  // Clear pending link if user closes without selecting
  if (pendingLinkUrl) {
    showToast("⚠️", "Link not added - no folder selected", "warning");
    pendingLinkUrl = null;
  }
}

function selectLinkFolder(folderId) {
  // Store selected folder for ingestion
  window._selectedLinkFolderId = folderId;
  
  // Add the pending link to the list now that folder is selected
  if (pendingLinkUrl) {
    pendingLinks.push(pendingLinkUrl);
    pendingLinkUrl = null;
    renderLinkList();
  }
  
  closeLinkFolderPopup();
  showToast("✅", folderId === null ? "Link added to unfiled" : "Link added to folder", "success");
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
  
  // Check if folder was selected
  if (window._selectedLinkFolderId === undefined) {
    showToast("⚠️", "Please select a folder for the links first.", "warning");
    openLinkFolderPopup();
    return;
  }
  
  // Get selected folder or use null for unfiled
  const folderId = window._selectedLinkFolderId;
  
  showToast("⏳", "Ingesting links…", "");

  const res = await fetch(`${API}/api/links/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ 
      urls: pendingLinks, 
      user_id: currentUser.id,
      folder_id: folderId
    })
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
  window._selectedLinkFolderId = undefined;
  renderLinkList();
  await loadDocuments(); // refresh sidebar
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
  
  // Add folder_id if selected
  if (window._selectedDocumentFolderId !== undefined && window._selectedDocumentFolderId !== null) {
    formData.append('folder_id', window._selectedDocumentFolderId);
  }

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
    window._selectedDocumentFolderId = undefined;
    loadDocuments();  // refresh left sidebar document list
  } catch (e) {
    showToast('❌', 'Upload failed — backend unreachable.', 'error');
  }
}


async function loadDocuments() {
  try {
    const res  = await fetch(`${API}/api/documents/`);
    const data = await res.json();
    documents = data.documents || data || [];

    // Build maps for quick lookup by Sources click
    window._docsById = {};
    window._docIdByFilename = {};
    documents.forEach(d => {
      window._docsById[d.id] = d;
      if (d.filename) window._docIdByFilename[d.filename] = d.id;
    });

    renderDocumentsTree();
  } catch(e) {
    console.warn('Could not load documents', e);
  }
}

async function loadFolders() {
  if (!currentUser) {
    folders = [];
    return;
  }
  
  try {
    const res = await authFetch('/api/folders/');
    const data = await res.json();
    
    if (res.ok) {
      folders = data.folders || [];
      renderDocumentsTree();
      updateFilterBadge();
      populateLinkFolderSelector();
    }
  } catch (err) {
    console.error('Failed to load folders:', err);
  }
}

function renderDocumentsTree() {
  const tree = document.getElementById('docs-tree');
  if (!tree) return;

  if (!documents || documents.length === 0) {
    tree.innerHTML = `<div style="font-size:12px; color:var(--text-muted); padding:8px 4px">No documents yet</div>`;
    return;
  }

  // Group documents by folder
  const byFolder = {};
  const unfiled = [];
  
  documents.forEach(doc => {
    if (doc.folder_id) {
      if (!byFolder[doc.folder_id]) byFolder[doc.folder_id] = [];
      byFolder[doc.folder_id].push(doc);
    } else {
      unfiled.push(doc);
    }
  });

  let html = '';

  // Render folders
  folders.forEach(folder => {
    const folderDocs = byFolder[folder.id] || [];
    const isCollapsed = collapsedFolders.has(folder.id);
    const isFiltered = activeFilterFolders.includes(folder.id);
    const filterClass = isFiltered ? 'filtered' : '';
    
    html += `
    <div class="folder-group ${filterClass}" data-folder-id="${folder.id}">
      <div class="folder-header" onclick="handleFolderClick(event, ${folder.id})">
        <input type="checkbox" class="folder-checkbox" ${isFiltered ? 'checked' : ''} 
               onclick="event.stopPropagation(); toggleFolderFilter(${folder.id})" />
        <span class="folder-arrow ${isCollapsed ? '' : 'open'}" onclick="event.stopPropagation(); toggleFolder(${folder.id})">▶</span>
        <span class="folder-name">${escapeHtml(folder.name)}</span>
        <span class="folder-count">${folderDocs.length}</span>
        <div class="folder-actions" onclick="event.stopPropagation()">
          <button class="folder-action-btn" onclick="openRenameFolderModal(${folder.id}, '${escapeHtml(folder.name).replace(/'/g, '\\\'')}')" title="Rename">✏️</button>
          <button class="folder-action-btn folder-del" onclick="deleteFolder(${folder.id}, '${escapeHtml(folder.name).replace(/'/g, '\\\'')}')" title="Delete">✕</button>
        </div>
      </div>
      <div class="folder-docs ${isCollapsed ? 'collapsed' : ''}">
        ${folderDocs.map(doc => renderDocItem(doc)).join('')}
      </div>
    </div>`;
  });

  // Render unfiled documents directly without folder grouping
  if (unfiled.length > 0) {
    html += unfiled.map(doc => renderDocItem(doc, true)).join('');
  }

  tree.innerHTML = html;
}

function renderDocItem(doc, isUnfiled = false) {
  const subjects = Array.isArray(doc.subject) ? doc.subject : (doc.subject ? [doc.subject] : ['General']);
  const primarySubject = subjects[0] || 'General';
  const subjectColor = SUBJECT_COLORS[primarySubject] || SUBJECT_COLORS['General'];
  
  const subjectBadge = `<span class="subject-badge" 
    style="background:${subjectColor}20; color:${subjectColor}; border:1px solid ${subjectColor}; padding:1px 4px; border-radius:3px; font-size:9px; font-weight:600; cursor:pointer; margin-top:2px; display:inline-block;" 
    onclick="event.stopPropagation(); editDocumentSubject(${doc.id}, ${JSON.stringify(subjects).replace(/"/g, '&quot;')})" 
    title="Click to edit subject">${primarySubject}${subjects.length > 1 ? ` +${subjects.length-1}` : ''}</span>`;
  
  // Add checkbox for unfiled documents
  const unfiledDocId = `unfiled-${doc.id}`;
  const isFiltered = isUnfiled && activeFilterFolders.includes(unfiledDocId);
  const checkbox = isUnfiled ? `<input type="checkbox" class="doc-checkbox" ${isFiltered ? 'checked' : ''} 
    onclick="event.stopPropagation(); toggleUnfiledDocFilter(${doc.id})" 
    style="width: 14px; height: 14px; margin-right: 6px; cursor: pointer; flex-shrink: 0;" />` : '';
  
  return `
  <div class="doc-item" onclick="previewDoc(${doc.id}, '${escapeHtml(doc.filename)}')">
    ${checkbox}
    <div style="flex:1; min-width:0;">
      <div style="display:flex; align-items:center; gap:6px;">
        <span class="doc-name" title="${escapeHtml(doc.filename)}">${escapeHtml(doc.filename)}</span>
      </div>
      ${subjectBadge}
    </div>
    <button class="doc-del" onclick="deleteDoc(${doc.id}, event)" title="Delete">✕</button>
  </div>`;
}

function toggleFolder(folderId) {
  if (collapsedFolders.has(folderId)) {
    collapsedFolders.delete(folderId);
  } else {
    collapsedFolders.add(folderId);
  }
  saveCollapsedState();
  renderDocumentsTree();
}

function handleFolderClick(event, folderId) {
  // Folder clicking disabled - only checkboxes control filtering
  // If clicking arrow, toggle collapse
  if (event.target.classList.contains('folder-arrow')) return;
  
  // If clicking checkbox, it's already handled
  if (event.target.classList.contains('folder-checkbox')) return;
  
  // If clicking action buttons, don't do anything
  if (event.target.closest('.folder-actions')) return;
  
  // Otherwise, do nothing - only checkboxes control filtering
}

function updateFilterBadge() {
  const badge = document.getElementById('filter-badge');
  const text = document.getElementById('filter-badge-text');
  const clear = badge?.querySelector('.filter-clear');
  
  if (!badge || !text) return;
  
  // Show badge only if there's a filter active
  if (activeFilterFolders.length > 0) {
    badge.style.display = 'flex';
    
    const folderNames = activeFilterFolders
      .map(id => {
        // Handle unfiled documents
        if (id.startsWith('unfiled-')) {
          const docId = parseInt(id.replace('unfiled-', ''));
          const doc = documents.find(d => d.id === docId);
          // Truncate long filenames
          if (doc) {
            const filename = doc.filename;
            return filename.length > 20 ? filename.substring(0, 17) + '...' : filename;
          }
          return '?';
        }
        // Handle regular folders
        return folders.find(f => f.id === id)?.name || '?';
      })
      .filter(Boolean);
    
    if (folderNames.length === 1) {
      text.textContent = folderNames[0];
    } else if (folderNames.length === 2) {
      text.textContent = folderNames.join(', ');
    } else {
      text.textContent = `${folderNames.length} items`;
    }
    
    badge.classList.add('active');
    if (clear) clear.style.display = 'inline-block';
  } else {
    // Hide badge when no filter
    badge.style.display = 'none';
    badge.classList.remove('active');
    if (clear) clear.style.display = 'none';
  }
}

// ══════════════════════════════════════════════════════════
// FOLDER MANAGEMENT UI
// ══════════════════════════════════════════════════════════

function toggleFolderFilter(folderId) {
  const idx = activeFilterFolders.indexOf(folderId);
  if (idx >= 0) {
    // Remove from filter
    activeFilterFolders.splice(idx, 1);
  } else {
    // Add to filter (multiple folder support)
    activeFilterFolders.push(folderId);
  }
  saveFilterState();
  renderDocumentsTree();
  updateFilterBadge();
}

function toggleUnfiledDocFilter(docId) {
  const unfiledDocId = `unfiled-${docId}`;
  const idx = activeFilterFolders.indexOf(unfiledDocId);
  if (idx >= 0) {
    // Remove from filter
    activeFilterFolders.splice(idx, 1);
  } else {
    // Add to filter
    activeFilterFolders.push(unfiledDocId);
  }
  saveFilterState();
  renderDocumentsTree();
  updateFilterBadge();
}

function closeAllModals() {
  document.getElementById('create-folder-overlay').style.display = 'none';
  document.getElementById('rename-folder-overlay').style.display = 'none';
  document.getElementById('document-folder-popup').style.display = 'none';
  document.getElementById('link-folder-popup').style.display = 'none';
  document.getElementById('modal-overlay').classList.remove('visible');
  document.getElementById('quiz-modal-overlay').classList.remove('visible');
  document.getElementById('memory-modal-overlay').classList.remove('visible');
}

function openCreateFolderModal() {
  if (!currentUser) {
    showToast('🔒', 'Please log in to create folders.', 'error');
    return;
  }
  
  closeAllModals();
  const overlay = document.getElementById('create-folder-overlay');
  const input = document.getElementById('new-folder-name');
  const error = document.getElementById('folder-create-error');
  
  overlay.style.display = 'flex';
  input.value = '';
  error.textContent = '';
  setTimeout(() => input.focus(), 100);
}

function closeCreateFolderModal() {
  document.getElementById('create-folder-overlay').style.display = 'none';
}

async function submitCreateFolder() {
  const name = document.getElementById('new-folder-name').value.trim();
  const errorEl = document.getElementById('folder-create-error');
  
  if (!name) {
    errorEl.textContent = 'Please enter a folder name.';
    return;
  }
  
  try {
    const res = await authFetch('/api/folders/', {
      method: 'POST',
      body: JSON.stringify({ name })
    });
    
    const data = await res.json();
    
    if (!res.ok) {
      errorEl.textContent = data.error || 'Failed to create folder.';
      return;
    }
    
    closeCreateFolderModal();
    await loadFolders();
    showToast('✅', `Folder "${name}" created successfully.`, 'success');
  } catch (err) {
    errorEl.textContent = 'Backend unreachable.';
  }
}

function openRenameFolderModal(folderId, currentName) {
  closeAllModals();
  const overlay = document.getElementById('rename-folder-overlay');
  const input = document.getElementById('rename-folder-name');
  const idInput = document.getElementById('rename-folder-id');
  const error = document.getElementById('folder-rename-error');
  
  overlay.style.display = 'flex';
  input.value = currentName;
  idInput.value = folderId;
  error.textContent = '';
  setTimeout(() => input.focus(), 100);
}

function closeRenameFolderModal() {
  document.getElementById('rename-folder-overlay').style.display = 'none';
}

async function submitRenameFolder() {
  const name = document.getElementById('rename-folder-name').value.trim();
  const folderId = parseInt(document.getElementById('rename-folder-id').value);
  const errorEl = document.getElementById('folder-rename-error');
  
  if (!name) {
    errorEl.textContent = 'Please enter a folder name.';
    return;
  }
  
  try {
    const res = await authFetch(`/api/folders/${folderId}`, {
      method: 'PATCH',
      body: JSON.stringify({ name })
    });
    
    const data = await res.json();
    
    if (!res.ok) {
      errorEl.textContent = data.error || 'Failed to rename folder.';
      return;
    }
    
    closeRenameFolderModal();
    await loadFolders();
    showToast('✅', `Folder renamed to "${name}".`, 'success');
  } catch (err) {
    errorEl.textContent = 'Backend unreachable.';
  }
}

async function deleteFolder(folderId, folderName) {
  if (!confirm(`Delete folder "${folderName}"? Documents will be moved to unfiled.`)) {
    return;
  }
  
  try {
    const res = await authFetch(`/api/folders/${folderId}`, {
      method: 'DELETE'
    });
    
    const data = await res.json();
    
    if (!res.ok) {
      showToast('❌', data.error || 'Failed to delete folder.', 'error');
      return;
    }
    
    // Remove from active filter if it was filtered
    const idx = activeFilterFolders.indexOf(folderId);
    if (idx >= 0) {
      activeFilterFolders.splice(idx, 1);
      saveFilterState();
    }
    
    await loadFolders();
    await loadDocuments();
    showToast('✅', `Folder "${folderName}" deleted.`, 'success');
  } catch (err) {
    showToast('❌', 'Backend unreachable.', 'error');
  }
}

// ══════════════════════════════════════════════════════════
// DOCUMENT FOLDER SELECTION
// ══════════════════════════════════════════════════════════

function openDocumentFolderModal() {
  if (!currentUser) {
    showToast('🔒', 'Please log in to upload documents.', 'error');
    return;
  }
  
  closeAllModals();
  const popup = document.getElementById('document-folder-popup');
  const container = document.getElementById('document-folder-buttons');
  
  // Create buttons for each folder + Unfiled
  let html = `<button class="folder-select-btn" onclick="selectDocumentFolder(null)">Unfiled</button>`;
  if (folders && folders.length > 0) {
    folders.forEach(folder => {
      html += `<button class="folder-select-btn" onclick="selectDocumentFolder(${folder.id})">${escapeHtml(folder.name)}</button>`;
    });
  }
  container.innerHTML = html;
  
  popup.style.display = 'block';
}

function closeDocumentFolderModal() {
  document.getElementById('document-folder-popup').style.display = 'none';
}

function selectDocumentFolder(folderId) {
  // Store selected folder and trigger file input
  window._selectedDocumentFolderId = folderId;
  closeDocumentFolderModal();
  document.getElementById('sidebar-file-input').click();
}

async function moveDocumentToFolder(selectElement) {
  const folderId = parseInt(selectElement.value);
  
  if (!folderId) {
    selectElement.selectedIndex = 0;
    return;
  }
  
  // Get all unfiled documents
  const unfiledDocs = documents.filter(d => !d.folder_id);
  
  if (unfiledDocs.length === 0) {
    showToast('ℹ️', 'No unfiled documents to move.', 'info');
    selectElement.selectedIndex = 0;
    return;
  }
  
  const folderName = folders.find(f => f.id === folderId)?.name || 'folder';
  
  if (!confirm(`Move all ${unfiledDocs.length} unfiled document(s) to "${folderName}"?`)) {
    selectElement.selectedIndex = 0;
    return;
  }
  
  try {
    // Move all unfiled documents to the selected folder
    const movePromises = unfiledDocs.map(doc => 
      authFetch(`/api/documents/${doc.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ folder_id: folderId })
      })
    );
    
    await Promise.all(movePromises);
    
    await loadFolders();
    await loadDocuments();
    showToast('✅', `Moved ${unfiledDocs.length} document(s) to "${folderName}".`, 'success');
  } catch (err) {
    showToast('❌', 'Failed to move documents.', 'error');
  } finally {
    selectElement.selectedIndex = 0;
  }
}

function toggleFilterDropdown() {
  // Placeholder for future dropdown menu
  // For now, clicking badge shows which folders are active
  if (activeFilterFolders.length > 0) {
    const folderNames = activeFilterFolders
      .map(id => folders.find(f => f.id === id)?.name)
      .filter(Boolean)
      .join(', ');
    alert(`Active filter: ${folderNames}\n\nClick folder name to filter, Ctrl+click for multi-select.`);
  }
}

// ══════════════════════════════════════════════════════════
// LINK FOLDER SELECTOR
// ══════════════════════════════════════════════════════════

function populateLinkFolderSelector() {
  const container = document.getElementById('link-folder-selector-container');
  const select = document.getElementById('link-folder-select');
  
  if (!container || !select) return;
  
  // Show selector only if there are folders
  if (folders.length > 0) {
    container.style.display = 'block';
    
    // Keep "Unfiled" option and add folder options
    const unfiledOption = '<option value="">Unfiled</option>';
    const folderOptions = folders
      .map(f => `<option value="${f.id}">${escapeHtml(f.name)}</option>`)
      .join('');
    
    select.innerHTML = unfiledOption + folderOptions;
  } else {
    container.style.display = 'none';
  }
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
      // Remove from active filter if it was filtered (handle unfiled doc filters)
      const unfiledDocId = `unfiled-${docId}`;
      const idx = activeFilterFolders.indexOf(unfiledDocId);
      if (idx >= 0) {
        activeFilterFolders.splice(idx, 1);
        saveFilterState();
      }
      
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

  // Initially append user message without rewrite metadata
  const userMsgId = appendMessage('user', null, query);
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
    
    // Auto-apply folder filter
    const filteredIds = getFilteredDocumentIds();
    if (filteredIds && filteredIds.length > 0) {
      payload.document_ids = filteredIds;
    }
    
    const res  = await fetch(`${API}/api/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(currentToken ? { 'Authorization': `Bearer ${currentToken}` } : {}) },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    
    // If query was rewritten, inject the rewrite dropdown into the existing user message
    if (data.metadata && data.metadata.query_rewritten) {
      const userMsgEl = document.getElementById(userMsgId);
      if (userMsgEl) {
        const rewriteHtml = `
          <div class="query-rewrite-toggle" onclick="toggleRewriteDetails('${userMsgId}')">
            <span class="rewrite-icon">✨</span>
            <span class="rewrite-label">Query was rewritten</span>
            <span class="rewrite-arrow">▼</span>
          </div>
          <div class="query-rewrite-details" id="${userMsgId}-rewrite" style="display: none;">
            <div class="rewrite-detail-item">
              <div class="rewrite-detail-label">Original:</div>
              <div class="rewrite-detail-value">${escapeHtml(data.metadata.original_query)}</div>
            </div>
            <div class="rewrite-detail-item">
              <div class="rewrite-detail-label">Rewritten to:</div>
              <div class="rewrite-detail-value">${escapeHtml(data.metadata.rewritten_query)}</div>
            </div>
            <div class="rewrite-detail-item">
              <div class="rewrite-detail-label">Strategy:</div>
              <div class="rewrite-detail-value"><span class="rewrite-strategy-badge">${escapeHtml(data.metadata.rewrite_strategy)}</span></div>
            </div>
            ${data.metadata.score_improvement !== undefined && data.metadata.score_improvement !== null ? `
            <div class="rewrite-detail-item">
              <div class="rewrite-detail-label">Improvement:</div>
              <div class="rewrite-detail-value rewrite-score-positive">+${data.metadata.score_improvement.toFixed(2)}</div>
            </div>` : ''}
          </div>`;
        
        // Append rewrite dropdown after the message text
        const messageBody = userMsgEl.querySelector('.message-body');
        if (messageBody) {
          messageBody.insertAdjacentHTML('beforeend', rewriteHtml);
        }
      }
    }
    
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
function appendMessage(role, docName, text, isLoading = false, rewriteMetadata = null) {
  const id  = `msg-${++msgCounter}`;
  const win = document.getElementById('chat-window');
  const isUser = role === 'user';
  const div = document.createElement('div');
  div.className = 'message'; div.id = id;
  
  // Build rewrite metadata HTML if query was rewritten
  let rewriteHtml = '';
  if (isUser && rewriteMetadata && rewriteMetadata.query_rewritten) {
    rewriteHtml = `
      <div class="query-rewrite-toggle" onclick="toggleRewriteDetails('${id}')">
        <span class="rewrite-icon">✨</span>
        <span class="rewrite-label">Query was rewritten</span>
        <span class="rewrite-arrow">▼</span>
      </div>
      <div class="query-rewrite-details" id="${id}-rewrite" style="display: none;">
        <div class="rewrite-detail-item">
          <div class="rewrite-detail-label">Original:</div>
          <div class="rewrite-detail-value">${escapeHtml(rewriteMetadata.original_query)}</div>
        </div>
        <div class="rewrite-detail-item">
          <div class="rewrite-detail-label">Rewritten to:</div>
          <div class="rewrite-detail-value">${escapeHtml(rewriteMetadata.rewritten_query || text)}</div>
        </div>
        <div class="rewrite-detail-item">
          <div class="rewrite-detail-label">Strategy:</div>
          <div class="rewrite-detail-value"><span class="rewrite-strategy-badge">${escapeHtml(rewriteMetadata.rewrite_strategy || 'auto')}</span></div>
        </div>
        ${rewriteMetadata.score_improvement !== undefined && rewriteMetadata.score_improvement !== null ? `
        <div class="rewrite-detail-item">
          <div class="rewrite-detail-label">Improvement:</div>
          <div class="rewrite-detail-value rewrite-score-positive">+${rewriteMetadata.score_improvement.toFixed(2)}</div>
        </div>` : ''}
      </div>`;
  }
  
  div.innerHTML = `
    <div class="avatar ${isUser ? 'user' : 'bot'}">${isUser ? '👤' : '🤖'}</div>
    <div class="message-body">
      <div class="message-role">${isUser ? 'You' : 'RAG Assistant'}</div>
      ${docName ? `<div class="message-doc-badge">📄 ${escapeHtml(docName)}</div>` : ''}
      <div class="message-text ${isLoading ? 'loading' : ''} ${isUser ? 'plain' : 'md'}">${isUser ? escapeHtml(text) : renderMarkdown(text)}</div>
      ${rewriteHtml}
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

function toggleRewriteDetails(messageId) {
  const detailsEl = document.getElementById(`${messageId}-rewrite`);
  const toggleEl = document.querySelector(`#${messageId} .query-rewrite-toggle`);
  const arrowEl = toggleEl ? toggleEl.querySelector('.rewrite-arrow') : null;
  
  if (detailsEl && arrowEl) {
    const isVisible = detailsEl.style.display !== 'none';
    detailsEl.style.display = isVisible ? 'none' : 'block';
    arrowEl.textContent = isVisible ? '▼' : '▲';
  }
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
  closeAllModals();
  const overlay = document.getElementById('quiz-modal-overlay');
  overlay.classList.add('visible');
  document.getElementById('quiz-error').textContent = '';

  const note = document.getElementById('quiz-scope-note');
  const filteredIds = getFilteredDocumentIds();
  
  if (filteredIds && filteredIds.length > 0) {
    note.textContent = `📂 Quiz will use ${filteredIds.length} selected document${filteredIds.length > 1 ? 's' : ''}.`;
  } else if (currentSession) {
    note.textContent = `📎 Quiz will use documents from your current session. Use checkboxes to filter.`;
  } else if (currentUser) {
    note.textContent = `📂 Quiz will use all your documents. Use folder/document checkboxes to filter.`;
  } else {
    note.textContent = `ℹ️ Log in to scope the quiz to your documents.`;
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

  let docIds = [];
  if (currentSession) {
    try {
      const r    = await authFetch(`/api/sessions/${currentSession}`);
      const data = await r.json();
      docIds     = data.document_ids || [];
    } catch { /* use empty = all docs */ }
  }
  
  // Auto-apply folder filter (overrides session document_ids)
  const filteredIds = getFilteredDocumentIds();
  if (filteredIds && filteredIds.length > 0) {
    docIds = filteredIds;
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
        document_ids : docIds,
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

function closeMemoryModal() {
  const overlay = document.getElementById('memory-modal-overlay');
  if (overlay) overlay.classList.remove('visible');
}

function toggleMemoryFreeform() {
  const enabled = !!document.getElementById('memory-freeform-toggle')?.checked;
  const freeform = document.getElementById('memory-freeform');
  if (freeform) freeform.disabled = !enabled;
}

function _normalizeUnresolvedQuestions(items) {
  if (Array.isArray(items)) {
    return items.map(x => String(x || '').trim()).filter(Boolean);
  }
  if (typeof items === 'string') {
    return items.split('\n').map(x => x.trim()).filter(Boolean);
  }
  return [];
}

function _normalizeEntities(items) {
  if (!Array.isArray(items)) return [];
  return items
    .map(item => {
      const entity = (item?.entity || '').toString().trim();
      const aliasesRaw = Array.isArray(item?.aliases)
        ? item.aliases
        : (typeof item?.aliases === 'string' ? item.aliases.split(',') : []);
      const aliases = aliasesRaw.map(a => String(a || '').trim()).filter(Boolean);
      return { entity, aliases };
    })
    .filter(item => item.entity);
}

function _renderMemoryUnresolvedSelect() {
  const sel = document.getElementById('memory-unresolved-select');
  if (!sel) return;
  sel.innerHTML = '';

  memoryUnresolvedQuestions.forEach((q, i) => {
    const opt = document.createElement('option');
    opt.value = String(i);
    opt.textContent = q;
    sel.appendChild(opt);
  });

  if (memoryUnresolvedQuestions.length === 0) {
    selectedMemoryUnresolvedIndex = -1;
    document.getElementById('memory-unresolved-input').value = '';
    return;
  }

  if (selectedMemoryUnresolvedIndex < 0 || selectedMemoryUnresolvedIndex >= memoryUnresolvedQuestions.length) {
    selectedMemoryUnresolvedIndex = 0;
  }
  sel.selectedIndex = selectedMemoryUnresolvedIndex;
  document.getElementById('memory-unresolved-input').value = memoryUnresolvedQuestions[selectedMemoryUnresolvedIndex] || '';
}

function onMemoryUnresolvedSelectChange() {
  const sel = document.getElementById('memory-unresolved-select');
  if (!sel) return;
  selectedMemoryUnresolvedIndex = sel.selectedIndex;
  document.getElementById('memory-unresolved-input').value =
    selectedMemoryUnresolvedIndex >= 0 ? (memoryUnresolvedQuestions[selectedMemoryUnresolvedIndex] || '') : '';
}

function upsertMemoryUnresolvedQuestion() {
  const input = document.getElementById('memory-unresolved-input');
  const errEl = document.getElementById('memory-error');
  const value = (input?.value || '').trim();
  if (!value) {
    if (errEl) errEl.textContent = 'Please enter a question first.';
    return;
  }

  if (selectedMemoryUnresolvedIndex >= 0 && selectedMemoryUnresolvedIndex < memoryUnresolvedQuestions.length) {
    memoryUnresolvedQuestions[selectedMemoryUnresolvedIndex] = value;
  } else {
    memoryUnresolvedQuestions.push(value);
    selectedMemoryUnresolvedIndex = memoryUnresolvedQuestions.length - 1;
  }

  if (errEl) errEl.textContent = '';
  _renderMemoryUnresolvedSelect();
}

function removeMemoryUnresolvedQuestion() {
  const errEl = document.getElementById('memory-error');
  if (selectedMemoryUnresolvedIndex < 0 || selectedMemoryUnresolvedIndex >= memoryUnresolvedQuestions.length) {
    if (errEl) errEl.textContent = 'Select an unresolved question to remove.';
    return;
  }

  memoryUnresolvedQuestions.splice(selectedMemoryUnresolvedIndex, 1);
  selectedMemoryUnresolvedIndex = Math.min(selectedMemoryUnresolvedIndex, memoryUnresolvedQuestions.length - 1);
  if (errEl) errEl.textContent = '';
  _renderMemoryUnresolvedSelect();
}

function _renderMemoryEntitiesSelect() {
  const sel = document.getElementById('memory-entities-select');
  if (!sel) return;
  sel.innerHTML = '';

  memoryEntities.forEach((item, i) => {
    const opt = document.createElement('option');
    const aliasText = (item.aliases || []).join(', ');
    opt.value = String(i);
    opt.textContent = aliasText ? `${item.entity} (${aliasText})` : item.entity;
    sel.appendChild(opt);
  });

  if (memoryEntities.length === 0) {
    selectedMemoryEntityIndex = -1;
    document.getElementById('memory-entity-name').value = '';
    document.getElementById('memory-entity-aliases').value = '';
    return;
  }

  if (selectedMemoryEntityIndex < 0 || selectedMemoryEntityIndex >= memoryEntities.length) {
    selectedMemoryEntityIndex = 0;
  }
  sel.selectedIndex = selectedMemoryEntityIndex;
  onMemoryEntitySelectChange();
}

function onMemoryEntitySelectChange() {
  const sel = document.getElementById('memory-entities-select');
  if (!sel) return;
  selectedMemoryEntityIndex = sel.selectedIndex;
  const item = selectedMemoryEntityIndex >= 0 ? memoryEntities[selectedMemoryEntityIndex] : null;
  document.getElementById('memory-entity-name').value = item?.entity || '';
  document.getElementById('memory-entity-aliases').value = Array.isArray(item?.aliases) ? item.aliases.join(', ') : '';
}

function upsertMemoryEntity() {
  const errEl = document.getElementById('memory-error');
  const entityName = (document.getElementById('memory-entity-name').value || '').trim();
  const aliases = (document.getElementById('memory-entity-aliases').value || '')
    .split(',')
    .map(s => s.trim())
    .filter(Boolean);

  if (!entityName) {
    if (errEl) errEl.textContent = 'Entity name is required.';
    return;
  }

  const payload = { entity: entityName, aliases };

  if (selectedMemoryEntityIndex >= 0 && selectedMemoryEntityIndex < memoryEntities.length) {
    memoryEntities[selectedMemoryEntityIndex] = payload;
  } else {
    memoryEntities.push(payload);
    selectedMemoryEntityIndex = memoryEntities.length - 1;
  }

  if (errEl) errEl.textContent = '';
  _renderMemoryEntitiesSelect();
}

function removeMemoryEntity() {
  const errEl = document.getElementById('memory-error');
  if (selectedMemoryEntityIndex < 0 || selectedMemoryEntityIndex >= memoryEntities.length) {
    if (errEl) errEl.textContent = 'Select an entity to remove.';
    return;
  }

  memoryEntities.splice(selectedMemoryEntityIndex, 1);
  selectedMemoryEntityIndex = Math.min(selectedMemoryEntityIndex, memoryEntities.length - 1);
  if (errEl) errEl.textContent = '';
  _renderMemoryEntitiesSelect();
}

async function openMemoryModal() {
  closeUserDropdown();
  closeAllModals();
  if (!currentSession) {
    showToast('⚠️', 'Open a session first to edit session memory.', 'warning');
    return;
  }

  const errEl = document.getElementById('memory-error');
  if (errEl) errEl.textContent = '';

  try {
    const res = await authFetch(`/api/sessions/${currentSession}/memory`);
    const data = await res.json();
    if (!res.ok) {
      showToast('❌', data.error || 'Could not load session memory.', 'error');
      return;
    }

    currentSessionMemory = data.memory || null;
    const structured = currentSessionMemory?.structured_data || {};

    document.getElementById('memory-short').value = structured.factual_summary_short || '';
    document.getElementById('memory-long').value = structured.factual_summary_long || '';
    memoryUnresolvedQuestions = _normalizeUnresolvedQuestions(structured.unresolved_questions);
    memoryEntities = _normalizeEntities(structured.entities_and_aliases);
    selectedMemoryUnresolvedIndex = memoryUnresolvedQuestions.length ? 0 : -1;
    selectedMemoryEntityIndex = memoryEntities.length ? 0 : -1;
    _renderMemoryUnresolvedSelect();
    _renderMemoryEntitiesSelect();

    const freeformEnabled = !!currentSessionMemory?.freeform_enabled;
    const toggle = document.getElementById('memory-freeform-toggle');
    toggle.checked = freeformEnabled;
    document.getElementById('memory-freeform').value = currentSessionMemory?.freeform_text || '';
    toggleMemoryFreeform();

    document.getElementById('memory-modal-overlay').classList.add('visible');
  } catch (e) {
    showToast('❌', 'Could not load session memory.', 'error');
  }
}

async function saveSessionMemory() {
  if (!currentSession) {
    showToast('⚠️', 'No active session selected.', 'warning');
    return;
  }

  const freeformEnabled = !!document.getElementById('memory-freeform-toggle')?.checked;
  const payload = {
    structured_data: {
      factual_summary_short: (document.getElementById('memory-short').value || '').trim(),
      factual_summary_long: (document.getElementById('memory-long').value || '').trim(),
      unresolved_questions: memoryUnresolvedQuestions,
      entities_and_aliases: memoryEntities,
    },
    freeform_enabled: freeformEnabled,
    freeform_text: freeformEnabled ? (document.getElementById('memory-freeform').value || '').trim() : '',
    latest_diagram_artifact: currentSessionMemory?.latest_diagram_artifact || null,
  };

  const errEl = document.getElementById('memory-error');
  if (errEl) errEl.textContent = '';

  try {
    const res = await authFetch(`/api/sessions/${currentSession}/memory`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      if (errEl) errEl.textContent = data.error || 'Memory update failed.';
      return;
    }

    currentSessionMemory = data.memory || null;
    closeMemoryModal();
    showToast('✅', 'Session memory saved.', 'success');
  } catch (e) {
    if (errEl) errEl.textContent = 'Could not save session memory.';
  }
}