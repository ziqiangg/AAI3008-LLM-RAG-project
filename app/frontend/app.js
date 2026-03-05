/* ══════════════════════════════════════════════════════════
   RAG Learning Assistant - Main JavaScript
   Performance-optimized separate JS file
   ══════════════════════════════════════════════════════════ */

const API = 'http://localhost:5000';

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
  // Simple inline logout for now — can be replaced with a dropdown
  if (confirm(`Logged in as ${currentUser.username}\n\nClick OK to log out.`)) logout();
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

  list.innerHTML = sources.map((s, i) => {
    const page = s.metadata?.source?.page;
    const pageDisplay = page != null ? ` • Page ${page}` : '';
    
    // Extract subject for badge
    const dominantSubject = s.metadata?.dominant_subject || 'General';
    const subjectColor = SUBJECT_COLORS[dominantSubject] || SUBJECT_COLORS['General'];
    const subjectBadge = `<span style="background:${subjectColor}20; color:${subjectColor}; padding:2px 6px; border-radius:4px; font-size:10px; font-weight:600; margin-left:6px;">${dominantSubject}</span>`;
    
    return `
    <div class="source-card" onclick="setActiveSource(${i})" title="${escapeHtml(s.content || '')}">
      <div class="source-file">📄 ${escapeHtml(s.filename || s.doc_id || `Source ${i+1}`)}${pageDisplay}${subjectBadge}</div>
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
    const list = document.getElementById('docs-list');
    const docs = data.documents || data;

    // Build maps for quick lookup by Sources click
    window._docsById = {};
    window._docIdByFilename = {};
    (docs || []).forEach(d => {
      window._docsById[d.id] = d;
      if (d.filename) window._docIdByFilename[d.filename] = d.id;
    });

    if (!docs?.length) {
      list.innerHTML = `<div style="font-size:12px;color:var(--text-muted);padding:8px 4px">No documents yet</div>`;
      return;
    }

    list.innerHTML = docs.map(doc => {
      // Handle subject as array or fallback to General
      const subjects = Array.isArray(doc.subject) ? doc.subject : (doc.subject ? [doc.subject] : ['General']);
      const primarySubject = subjects[0] || 'General';
      const subjectColor = SUBJECT_COLORS[primarySubject] || SUBJECT_COLORS['General'];
      
      // Create subject badge with click-to-edit
      const subjectBadge = `<span class="subject-badge" 
        style="background:${subjectColor}20; color:${subjectColor}; border:1px solid ${subjectColor}; padding:2px 6px; border-radius:4px; font-size:10px; font-weight:600; cursor:pointer; margin-top:2px; display:inline-block;" 
        onclick="event.stopPropagation(); editDocumentSubject(${doc.id}, ${JSON.stringify(subjects).replace(/"/g, '&quot;')})" 
        title="Click to edit subject">${primarySubject}${subjects.length > 1 ? ` +${subjects.length-1}` : ''}</span>`;
      
      return `
      <div class="doc-item" onclick="previewDoc(${doc.id}, '${escapeHtml(doc.filename)}')">
        <div style="flex:1; min-width:0;">
          <div style="display:flex; align-items:center; gap:6px;">
            <span class="doc-icon">📄</span>
            <span class="doc-name" title="${escapeHtml(doc.filename)}">${escapeHtml(doc.filename)}</span>
          </div>
          ${subjectBadge}
        </div>
        <button class="doc-del" onclick="deleteDoc(${doc.id}, event)" title="Delete">✕</button>
      </div>`;
    }).join('');
  } catch(e) {
    console.warn('Could not load documents', e);
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
    if (res.ok) { showToast('🗑️', 'Document deleted.', 'success'); loadDocuments(); }
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
    const payload = { question: query };
    if (currentSession) payload.session_id = currentSession;

    const res  = await fetch(`${API}/api/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(currentToken ? { 'Authorization': `Bearer ${currentToken}` } : {}) },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    const answer = data.answer || data.response || data.message || JSON.stringify(data);

    updateMessage(loadingId, answer);
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

function updateMessage(id, text) {
  const el = document.querySelector(`#${id} .message-text`);
  if (el) { el.innerHTML = renderMarkdown(text); el.classList.remove('loading'); }
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

// Close when clicking outside modal
document.getElementById('doc-modal')?.addEventListener('click', (e) => {
  if (e.target.id === 'doc-modal') closeDocModal();
});
