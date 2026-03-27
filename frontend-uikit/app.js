/**
 * RAG-v2.1 UIkit frontend — vanilla JS
 * Same API as React frontend; uses UIkit for layout and components.
 */

(function () {
  'use strict';

  // API base: /api when served behind nginx proxy; override via data attribute or env
  const API_BASE = document.documentElement.dataset.apiBase || '/api';

  function getUrl(path) {
    const p = path.startsWith('/') ? path : '/' + path;
    return API_BASE.replace(/\/$/, '') + p;
  }

  async function fetchJSON(path, opts = {}) {
    const url = getUrl(path);
    const res = await fetch(url, {
      ...opts,
      headers: { Accept: 'application/json', ...opts.headers },
      cache: 'no-store',
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(res.status === 502 ? 'Backend unreachable. Run: docker-compose ps' : (text || res.statusText));
    }
    return res.json();
  }

  async function uploadFile(file, onProgress) {
    const form = new FormData();
    form.append('file', file);
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) onProgress((e.loaded / e.total) * 100);
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText));
        else reject(new Error(xhr.responseText || xhr.statusText));
      };
      xhr.onerror = () => reject(new Error('Network error'));
      xhr.open('POST', getUrl('/documents/upload'));
      xhr.send(form);
    });
  }

  // State
  let documents = [];
  let selectedDoc = null;
  let conversationId = null;
  let messages = [];
  let models = [];
  let selectedModel = '';
  let lastCitations = [];
  let lastChunks = [];

  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

  function renderDocList() {
    const el = $('#doc-list');
    if (!el) return;
    if (documents.length === 0) {
      el.innerHTML = '<li><p class="uk-text-meta">No documents yet. Upload a PDF.</p></li>';
      return;
    }
    el.innerHTML = documents.map((d) => {
      const active = selectedDoc && selectedDoc.id === d.id ? 'uk-active' : '';
      return `<li class="uk-margin-small"><a href="#" class="uk-link-reset doc-link ${active}" data-id="${d.id}">${escapeHtml(d.original_name)}</a> <span class="uk-text-meta">(${d.chunk_count} chunks)</span></li>`;
    }).join('');
    el.querySelectorAll('.doc-link').forEach((a) => {
      a.addEventListener('click', (e) => {
        e.preventDefault();
        const id = a.dataset.id;
        selectedDoc = documents.find((d) => d.id === id) || null;
        conversationId = null;
        messages = [];
        renderDocList();
        renderMessages();
        $('#selected-doc').textContent = selectedDoc ? selectedDoc.original_name : 'All Documents';
      });
    });
  }

  function renderMessages() {
    const el = $('#messages');
    if (!el) return;
    if (messages.length === 0) {
      el.innerHTML = '<div class="uk-text-center uk-text-muted uk-margin-auto"><span uk-icon="icon: comment; ratio: 2"></span><p class="uk-margin-small-top">Ask a question about your documents</p></div>';
      return;
    }
    el.innerHTML = messages.map((m) => {
      const cls = m.role === 'user' ? 'user uk-align-right' : 'assistant uk-align-left';
      const content = m.role === 'assistant' ? simpleMarkdown(m.content) : escapeHtml(m.content);
      const citeBtn = m.citations && m.citations.length ? `<button class="uk-button uk-button-text uk-button-small uk-margin-small-top cite-btn" data-msg-id="${m.id}"><span uk-icon="quote"></span> ${m.citations.length} source(s)</button>` : '';
      return `<div class="uk-chat-message ${cls} uk-margin-small"><div class="uk-card uk-card-body uk-card-default uk-card-small">${content}${citeBtn}</div></div>`;
    }).join('');

    el.querySelectorAll('.cite-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const msg = messages.find((m) => m.id === btn.dataset.msgId);
        if (msg && msg.citations) {
          lastCitations = msg.citations;
          lastChunks = msg.retrieved_chunks || [];
          showSources();
        }
      });
    });
    el.scrollTop = el.scrollHeight;
  }

  function simpleMarkdown(text) {
    return escapeHtml(text)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/\[(\d+)\]/g, '<sup class="uk-text-primary">[$1]</sup>')
      .replace(/\n/g, '<br>');
  }

  function escapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }

  function showSources() {
    const el = $('#sources-content');
    if (!el) return;
    if (lastChunks.length === 0) {
      el.innerHTML = '<p class="uk-text-meta">No sources.</p>';
    } else {
      el.innerHTML = lastChunks.map((c, i) => `<div class="uk-margin-small"><strong>${i + 1}. ${escapeHtml(c.document_name)}</strong> (p.${c.start_page}-${c.end_page})<p class="uk-text-small uk-margin-remove-top">${escapeHtml(c.text.slice(0, 300))}…</p></div>`).join('');
    }
    UIkit.offcanvas('#sources-offcanvas').show();
  }

  async function loadDocuments() {
    try {
      documents = await fetchJSON('/documents/');
      renderDocList();
    } catch (e) {
      $('#doc-list').innerHTML = `<li><p class="uk-text-danger">${escapeHtml(e.message)}</p></li>`;
    }
  }

  async function loadModels() {
    try {
      const r = await fetchJSON('/chat/models');
      models = r.models || [];
      selectedModel = localStorage.getItem('rag_model') || r.default_model || (models[0] && models[0].id) || '';
      const sel = $('#model-select');
      sel.innerHTML = models.map((m) => `<option value="${escapeHtml(m.id)}" ${m.id === selectedModel ? 'selected' : ''}>${escapeHtml(m.name)}</option>`).join('');
      sel.addEventListener('change', () => {
        selectedModel = sel.value;
        localStorage.setItem('rag_model', selectedModel);
      });
    } catch (_) {}
  }

  async function checkHealth() {
    const el = $('#api-status');
    try {
      await fetchJSON('/health');
      el.innerHTML = '<span class="uk-text-success" uk-icon="check"></span> API OK';
    } catch (e) {
      el.innerHTML = '<span class="uk-text-warning" uk-icon="warning"></span> API unreachable';
    }
  }

  async function sendQuery(query) {
    const input = $('#query-input');
    input.disabled = true;
    messages.push({ id: Date.now().toString(), role: 'user', content: query, timestamp: new Date().toISOString() });
    renderMessages();

    const loading = { id: 'loading', role: 'assistant', content: '…', timestamp: '' };
    messages.push(loading);
    renderMessages();

    try {
      const body = {
        query,
        document_id: selectedDoc ? selectedDoc.id : null,
        conversation_id: conversationId,
        model: selectedModel || null,
      };
      const res = await fetchJSON('/chat/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      messages.pop();
      if (res.conversation_id) conversationId = res.conversation_id;
      messages.push({
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: res.answer,
        timestamp: new Date().toISOString(),
        citations: res.citations || [],
        retrieved_chunks: res.retrieved_chunks || [],
      });
      renderMessages();
      if (res.citations && res.citations.length) $('#sources-btn').style.display = 'inline-block';
    } catch (e) {
      messages.pop();
      messages.push({
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Error: ' + (e.message || 'Request failed'),
        timestamp: new Date().toISOString(),
      });
      renderMessages();
    }
    input.disabled = false;
    input.focus();
  }

  // Event handlers
  $('#upload-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = $('#file-input');
    const file = input.files && input.files[0];
    if (!file) return;
    const btn = $('#upload-btn');
    btn.disabled = true;
    try {
      await uploadFile(file, (p) => { btn.textContent = `Uploading ${Math.round(p)}%`; });
      btn.textContent = 'Upload PDF';
      input.value = '';
      await loadDocuments();
      if (typeof UIkit !== 'undefined') UIkit.notification({ message: 'Uploaded', status: 'success' });
    } catch (err) {
      if (typeof UIkit !== 'undefined') UIkit.notification({ message: err.message || 'Upload failed', status: 'danger' });
      btn.textContent = 'Upload PDF';
    }
    btn.disabled = false;
  });

  $('#chat-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const input = $('#query-input');
    const q = (input.value || '').trim();
    if (!q) return;
    input.value = '';
    sendQuery(q);
  });

  $('#sources-btn').addEventListener('click', () => {
    if (lastCitations.length || lastChunks.length) showSources();
  });

  // Init
  checkHealth();
  loadDocuments();
  loadModels();
})();
