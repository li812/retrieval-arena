// Chat mode and Bot Studio. Merged into the Alpine component next to arenaApp():
//   x-data="Object.assign(arenaApp(), chatMixin())"

const BLANK_TRACE = () => ({ stages: [], transform: null, warnings: [] });

// Minimal Markdown → HTML for model replies. Everything is HTML-escaped first, so the output can only
// contain the tags added here (safe for x-html).
function renderMarkdown(src) {
  const esc = t => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const inline = t => esc(t)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>')
    .replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g, '<span class="cite">[$1]</span>');
  const lines = (src || '').split('\n');
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^```/.test(line)) {
      const body = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) body.push(lines[i++]);
      i++;
      out.push('<pre><code>' + esc(body.join('\n')) + '</code></pre>');
    } else if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|?[\s:-]+\|[\s|:-]*$/.test(lines[i + 1])) {
      const cells = l => l.trim().replace(/^\||\|$/g, '').split('|').map(c => inline(c.trim()));
      const head = cells(line);
      i += 2;
      const rows = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(cells(lines[i++]));
      out.push('<table><thead><tr>' + head.map(c => '<th>' + c + '</th>').join('') + '</tr></thead><tbody>'
        + rows.map(r => '<tr>' + r.map(c => '<td>' + c + '</td>').join('') + '</tr>').join('') + '</tbody></table>');
    } else if (/^#{1,4}\s/.test(line)) {
      const level = Math.min(4, line.match(/^#+/)[0].length + 2);
      out.push(`<h${level}>` + inline(line.replace(/^#+\s*/, '')) + `</h${level}>`);
      i++;
    } else if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\./.test(line);
      const items = [];
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) items.push(inline(lines[i++].replace(/^\s*([-*]|\d+\.)\s+/, '')));
      const tag = ordered ? 'ol' : 'ul';
      out.push(`<${tag}>` + items.map(it => '<li>' + it + '</li>').join('') + `</${tag}>`);
    } else if (!line.trim()) {
      i++;
    } else {
      const para = [];
      while (i < lines.length && lines[i].trim() && !/^(```|#{1,4}\s|\s*([-*]|\d+\.)\s+|\s*\|)/.test(lines[i])) para.push(inline(lines[i++]));
      if (!para.length) para.push(inline(lines[i++]));
      out.push('<p>' + para.join('<br>') + '</p>');
    }
  }
  return out.join('');
}

function chatMixin() {
  return {
    // --- Bots & conversations ---
    bots: [],
    activeBotId: null,
    conversations: [],
    activeConvId: null,
    chatMessages: [],
    chatInput: '',
    chatBusy: false,

    // --- Bot Studio ---
    studioOpen: false,
    draft: null,
    draftError: '',
    savingDraft: false,
    previewMessages: [],
    previewInput: '',
    previewBusy: false,
    pendingBotDelete: false,

    // --- MCP ---
    mcpServers: [],
    mcpTools: [],
    mcpToolErrors: [],
    mcpAllowStdio: false,
    mcpForm: { transport: 'http', name: '', url: '', auth: '', command: '' },
    mcpFormError: '',
    toolSupport: null,

    renderMarkdown,

    chatInit() {
      this.loadBots();
      this.loadMcpServers();
    },

    // =========================================================
    // MCP
    // =========================================================

    mcpAddCommand() {
      return `claude mcp add --transport http retrieval-arena ${location.origin}/mcp/`;
    },

    async loadMcpServers() {
      try {
        const resp = await fetch('/mcp-servers');
        if (resp.ok) {
          const data = await resp.json();
          this.mcpAllowStdio = data.allow_stdio;
          this.mcpServers = data.servers.map(s => ({ ...s, tools: null, error: '', testing: false, pendingDelete: false }));
        }
      } catch (_) {}
    },

    async loadMcpTools() {
      try {
        const resp = await fetch('/mcp-tools');
        if (resp.ok) {
          const data = await resp.json();
          this.mcpTools = data.tools;
          this.mcpToolErrors = data.errors;
        }
      } catch (_) {}
    },

    async testMcpServer(srv) {
      srv.testing = true;
      srv.error = '';
      try {
        const resp = await fetch(`/mcp-servers/${srv.id}/tools?refresh=true`);
        const data = await resp.json().catch(() => ({}));
        if (resp.ok) srv.tools = data.tools;
        else srv.error = data.detail || `HTTP ${resp.status}`;
      } catch (err) {
        srv.error = err.message;
      } finally {
        srv.testing = false;
      }
    },

    async addMcpServer() {
      const f = this.mcpForm;
      this.mcpFormError = '';
      const body = { name: f.name.trim(), transport: f.transport };
      if (f.transport === 'http') {
        body.url = f.url.trim();
        if (f.auth.trim()) body.headers = { Authorization: f.auth.trim() };
      } else {
        const parts = f.command.trim().split(/\s+/);
        body.command = parts[0] || '';
        body.args = parts.slice(1);
      }
      const resp = await fetch('/mcp-servers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }).catch(() => null);
      const data = resp ? await resp.json().catch(() => ({})) : {};
      if (!resp || !resp.ok) {
        this.mcpFormError = typeof data.detail === 'string' ? data.detail : 'Could not add server';
        return;
      }
      this.mcpForm = { transport: 'http', name: '', url: '', auth: '', command: '' };
      await this.loadMcpServers();
      const added = this.mcpServers.find(s => s.id === data.id);
      if (added) this.testMcpServer(added);
    },

    async toggleMcpServer(srv) {
      await fetch(`/mcp-servers/${srv.id}/enabled?enabled=${!srv.enabled}`, { method: 'POST' }).catch(() => {});
      srv.enabled = !srv.enabled;
    },

    async deleteMcpServer(srv) {
      if (!srv.pendingDelete) { srv.pendingDelete = true; return; }
      await fetch(`/mcp-servers/${srv.id}`, { method: 'DELETE' }).catch(() => {});
      this.mcpServers = this.mcpServers.filter(s => s.id !== srv.id);
    },

    async checkToolSupport() {
      this.toolSupport = null;
      if (!this.draft || !this.draft.gen_model) return;
      try {
        const resp = await fetch('/config/tool-support', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider: this.draft.provider, model: this.draft.gen_model, ...this._botKeyRef(this._draftPayload()) }),
        });
        if (resp.ok) this.toolSupport = await resp.json();
      } catch (_) {}
    },

    activeBot() {
      return this.bots.find(b => b.id === this.activeBotId) || null;
    },

    // =========================================================
    // Bots
    // =========================================================

    async loadBots() {
      try {
        const resp = await fetch('/bots');
        if (!resp.ok) return;
        this.bots = await resp.json();
        if (!this.activeBot() && this.bots.length) this.selectBot(this.bots[0]);
      } catch (_) {}
    },

    async selectBot(bot) {
      this.activeBotId = bot.id;
      this.activeConvId = null;
      this.chatMessages = [];
      await this.loadConversations();
    },

    async loadConversations() {
      if (!this.activeBotId) { this.conversations = []; return; }
      try {
        const resp = await fetch(`/bots/${this.activeBotId}/conversations`);
        if (resp.ok) this.conversations = await resp.json();
      } catch (_) {}
    },

    async openConversation(conv) {
      this.activeConvId = conv.id;
      try {
        const resp = await fetch(`/conversations/${conv.id}`);
        if (!resp.ok) return;
        const data = await resp.json();
        this.chatMessages = data.messages.map(m => this._uiMessage(m));
        this.$nextTick(() => this._scrollThread());
      } catch (_) {}
    },

    newChat() {
      this.activeConvId = null;
      this.chatMessages = [];
      this.$nextTick(() => document.getElementById('chat-input')?.focus());
    },

    async deleteConversation(conv) {
      await fetch(`/conversations/${conv.id}`, { method: 'DELETE' }).catch(() => {});
      if (this.activeConvId === conv.id) this.newChat();
      this.loadConversations();
    },

    _uiMessage(m) {
      return {
        id: m.id ?? null,
        role: m.role,
        content: m.content || '',
        meta: {
          query: null, chunks: [], triples: [], trace: BLANK_TRACE(), sentiment: null,
          evaluation: null, tool_calls: [], duration_ms: 0,
          ...(m.meta || {}),
        },
        feedback: m.feedback || 0,
        streaming: false,
        evaluating: false,
        showSources: false,
      };
    },

    // =========================================================
    // Sending
    // =========================================================

    // POST a body and feed each SSE event to onEvent(type, data)
    async _postSSE(url, body, onEvent) {
      const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${resp.status}`);
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      const flush = block => {
        let type = 'message', data = '';
        for (const line of block.split('\n')) {
          if (line.startsWith('event: ')) type = line.slice(7).trim();
          else if (line.startsWith('data: ')) data += line.slice(6);
        }
        try { onEvent(type, data ? JSON.parse(data) : {}); } catch (_) { onEvent(type, {}); }
      };
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split('\n\n');
        buffer = blocks.pop();
        blocks.filter(b => b.trim()).forEach(flush);
      }
      if (buffer.trim()) flush(buffer);
    },

    // Route one chat SSE event into an assistant message object
    _applyChatEvent(msg, type, data) {
      const m = msg.meta;
      switch (type) {
        case 'rewritten': m.query = data.changed ? data.query : null; break;
        case 'query_transformed': m.trace.transform = data; break;
        case 'pipeline_trace': m.trace.stages = data.stages || []; break;
        case 'pipeline_warning':
        case 'warning': m.trace.warnings.push(data.stage + ': ' + data.message); break;
        case 'chunk_scored': m.chunks.push(this._makeChunk(data, m.chunks)); break;
        case 'hop_traversed':
        case 'graph_hop_traversed': m.triples.push(...(data.triples || [])); break;
        case 'token': msg.content += data.token; this._scrollThread(); break;
        case 'tool_call': m.tool_calls.push({ ...data, status: 'running' }); break;
        case 'tool_result': {
          const call = m.tool_calls.find(c => c.id === data.id);
          if (call) Object.assign(call, data, { status: data.error ? 'error' : 'done' });
          else m.tool_calls.push({ ...data, status: data.error ? 'error' : 'done' });
          break;
        }
        case 'sentiment': m.sentiment = data; break;
        case 'evaluation_started': msg.evaluating = true; break;
        case 'evaluation': m.evaluation = data; msg.evaluating = false; break;
        case 'error': msg.content = (msg.content ? msg.content + '\n\n' : '') + 'Error: ' + data.message; break;
        case 'done': msg.id = data.message_id ?? null; msg.streaming = false; msg.evaluating = false; break;
      }
    },

    _botKeyRef(bot) {
      // A bot with its own saved key uses it server-side; otherwise borrow the key in Settings
      return bot && bot.key_id != null ? {} : this.keyRef();
    },

    async sendChat(text = null, { regenerate = false } = {}) {
      const bot = this.activeBot();
      const message = (text ?? this.chatInput).trim();
      if (!bot || this.chatBusy || (!message && !regenerate)) return;
      this.chatBusy = true;
      if (!regenerate) {
        this.chatMessages.push(this._uiMessage({ role: 'user', content: message }));
        this.chatInput = '';
      }
      const reply = this._uiMessage({ role: 'assistant', content: '' });
      reply.streaming = true;
      this.chatMessages.push(reply);
      const msg = this.chatMessages[this.chatMessages.length - 1]; // reactive proxy
      this.$nextTick(() => this._scrollThread());

      try {
        await this._postSSE('/chat', {
          bot_id: bot.id,
          conversation_id: this.activeConvId,
          message: regenerate ? null : message,
          regenerate,
          ...this._botKeyRef(bot),
        }, (type, data) => {
          if (type === 'conversation' && data.conversation_id) this.activeConvId = data.conversation_id;
          else this._applyChatEvent(msg, type, data);
        });
      } catch (err) {
        msg.content = 'Error: ' + err.message;
      } finally {
        msg.streaming = false;
        this.chatBusy = false;
        this.loadConversations();
      }
    },

    regenerateLast() {
      if (this.chatBusy || !this.activeConvId) return;
      const last = this.chatMessages[this.chatMessages.length - 1];
      if (last && last.role === 'assistant') this.chatMessages.pop();
      this.sendChat(null, { regenerate: true });
    },

    async rateMessage(msg, value) {
      if (!msg.id) return;
      const next = msg.feedback === value ? 0 : value;
      const resp = await fetch(`/messages/${msg.id}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: next }),
      }).catch(() => null);
      if (resp && resp.ok) msg.feedback = next;
    },

    async copyText(text) {
      try { await navigator.clipboard.writeText(text); this.flash('Copied'); } catch (_) {}
    },

    _scrollThread() {
      const el = document.getElementById('chat-thread');
      if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 160) el.scrollTop = el.scrollHeight;
    },

    onChatKey(e) {
      // Enter sends, Shift+Enter is a newline
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        this.sendChat();
      }
    },

    // =========================================================
    // Bot Studio
    // =========================================================

    _draftFromArena() {
      const tuning = this.queryBody().tuning;
      return {
        id: null,
        name: '',
        emoji: '◆',
        description: '',
        system_prompt: this.systemPrompt,
        collection: this.collection || 'default',
        backend: this.backend === 'graph' ? 'graph' : this.backend === 'compare' ? 'both' : 'chroma',
        provider: this.provider,
        gen_model: this.selectedGenModel,
        embedding_model: this.selectedEmbedModel,
        key_id: this.keyId,
        tuning,
        greeting: '',
        starters: [],
        tools: [],
      };
    },

    openStudio(bot = null) {
      this.draft = bot
        ? JSON.parse(JSON.stringify(bot))
        : this._draftFromArena();
      this.draft.startersText = (this.draft.starters || []).join('\n');
      this.draftError = '';
      this.previewMessages = [];
      this.previewInput = '';
      this.pendingBotDelete = false;
      this.studioOpen = true;
      this.toolSupport = null;
      this.loadMcpTools().then(() => { if (this.draft.tools.length) this.checkToolSupport(); });
    },

    useArenaTuning() {
      this.draft.tuning = this.queryBody().tuning;
      this.flash('Copied current Lab settings');
    },

    _draftPayload() {
      const { id, created_at, updated_at, startersText, ...rest } = this.draft;
      rest.starters = (startersText || '').split('\n').map(s => s.trim()).filter(Boolean).slice(0, 6);
      rest.key_id = rest.key_id === '' || rest.key_id == null ? null : Number(rest.key_id);
      return rest;
    },

    async saveDraft() {
      if (!this.draft.name.trim()) { this.draftError = 'Give the bot a name'; return; }
      this.savingDraft = true;
      this.draftError = '';
      const url = this.draft.id ? `/bots/${this.draft.id}` : '/bots';
      try {
        const resp = await fetch(url, {
          method: this.draft.id ? 'PUT' : 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this._draftPayload()),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          this.draftError = typeof data.detail === 'string' ? data.detail : 'Could not save (check the fields)';
          return;
        }
        this.draft = { ...data, startersText: (data.starters || []).join('\n') };
        await this.loadBots();
        await this.selectBot(data);
        this.flash('Bot saved');
      } finally {
        this.savingDraft = false;
      }
    },

    async deleteDraftBot() {
      if (!this.draft.id) return;
      if (!this.pendingBotDelete) { this.pendingBotDelete = true; return; }
      await fetch(`/bots/${this.draft.id}`, { method: 'DELETE' }).catch(() => {});
      this.studioOpen = false;
      this.activeBotId = null;
      this.chatMessages = [];
      await this.loadBots();
      this.flash('Bot deleted');
    },

    async sendPreview(text = null) {
      const message = (text ?? this.previewInput).trim();
      if (!message || this.previewBusy) return;
      this.previewBusy = true;
      const history = this.previewMessages
        .filter(m => m.content && !m.content.startsWith('Error:'))
        .map(m => ({ role: m.role, content: m.content }));
      this.previewMessages.push(this._uiMessage({ role: 'user', content: message }));
      this.previewInput = '';
      const reply = this._uiMessage({ role: 'assistant', content: '' });
      reply.streaming = true;
      this.previewMessages.push(reply);
      const msg = this.previewMessages[this.previewMessages.length - 1];
      const draft = this._draftPayload();
      try {
        await this._postSSE('/chat', { bot: draft, history, message, ...this._botKeyRef(draft) },
          (type, data) => this._applyChatEvent(msg, type, data));
      } catch (err) {
        msg.content = 'Error: ' + err.message;
      } finally {
        msg.streaming = false;
        this.previewBusy = false;
      }
    },

    // Load a bot's configuration into the arena controls, e.g. to A/B it in Compare
    applyBotToArena(bot) {
      const t = bot.tuning || {};
      for (const [k, v] of Object.entries(t)) {
        if (k === 'system_prompt') this.systemPrompt = v;
        else if (k in this && typeof this[k] !== 'function') this[k] = v ?? (k === 'source_filter' ? '' : v);
      }
      this.collection = bot.collection;
      if (bot.provider === this.provider) {
        if (this.genModels.some(m => m.value === bot.gen_model)) this.selectedGenModel = bot.gen_model;
        if (this.embedModels.some(m => m.value === bot.embedding_model)) this.selectedEmbedModel = bot.embedding_model;
      }
      this.studioOpen = false;
      this.setBackend(bot.backend === 'graph' ? 'graph' : bot.backend === 'both' ? 'compare' : 'chroma');
      this.flash('Loaded ' + bot.name + ' into the arena');
    },
  };
}
