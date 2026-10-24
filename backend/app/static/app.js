// Per-viewer UI preferences; storage can be unavailable (private mode), so never let it throw
const prefs = {
  get(key, fallback) {
    try { const v = localStorage.getItem('arena.' + key); return v === null ? fallback : JSON.parse(v); }
    catch (_) { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem('arena.' + key, JSON.stringify(value)); } catch (_) {}
  },
};

const LAYOUT_DEFAULTS = { sidebar: 300, answer: 210, split: 50 };
const LAYOUT_LIMITS = { sidebar: [220, 560], answer: [140, 640], split: [20, 80] };

function arenaApp() {
  return {
    // --- API / Auth ---
    apiKey: '',
    keyStatus: 'untested',
    keyError: '',
    genModels: [],
    embedModels: [],
    selectedGenModel: '',
    selectedEmbedModel: '',
    provider: 'gemini',

    // --- Saved keys ---
    // When a saved key is in use only its id lives in the browser; the server resolves the secret
    keyId: null,
    keyHint: '',
    savedKeys: [],
    savedKeysLoaded: false,
    savingKey: false,
    newKeyLabel: '',

    // --- UI ---
    settingsOpen: false,
    sidebarOpen: false,
    sidebarCollapsed: prefs.get('sidebarCollapsed', false),
    themePref: (() => { try { return localStorage.getItem('arena.theme') || 'auto'; } catch (_) { return 'auto'; } })(),
    layout: { ...LAYOUT_DEFAULTS, ...prefs.get('layout', {}) },
    paletteOpen: false,
    paletteQuery: '',
    paletteIndex: 0,
    shortcutsOpen: false,
    shortcutList: [
      ['Ctrl/⌘ K', 'Focus the question bar · press again for the command palette'],
      ['Ctrl/⌘ Enter', 'Run the query'],
      ['1 · 2 · 3 · 4', 'Switch to Chroma · Graph · Compare · Chat'],
      ['[', 'Collapse or expand the sidebar'],
      ['H', 'Open query history'],
      ['D', 'Open the collections manager'],
      ['T', 'Cycle theme: auto → light → dark'],
      ['Ctrl/⌘ ,', 'Open settings'],
      ['?', 'Show this cheatsheet'],
      ['Esc', 'Close any open panel'],
    ],
    sections: {
      chunking: true,
      retrievalChroma: true,
      retrievalGraph: true,
      generation: true,
      systemPrompt: false,
      lab: true,
      ingest: true,
    },

    // --- Backend / query state ---
    backend: 'chroma',
    collection: 'default',
    question: '',
    isIngesting: false,
    isQuerying: false,
    answer: '',
    answerDone: false,
    embedTiming: null,

    // --- Compare mode ---
    compareAnswerChroma: '',
    compareAnswerGraph: '',
    compareChromaDone: false,
    compareGraphDone: false,

    // --- Ingest ---
    ingestText: '',
    ingestFiles: [],
    ingestResult: null,

    // --- Retrieval results ---
    chunks: [],
    graphNodes: [],
    graphEdges: [],
    network: null,
    _nodesDS: null,
    _edgesDS: null,

    // Compare-mode separate datasets
    compareChromaChunks: [],
    compareGraphNodes: [],
    compareGraphEdges: [],
    compareNetwork: null,
    _compareNodesDS: null,
    _compareEdgesDS: null,

    // --- Event log ---
    eventLog: [],

    // --- Retrieval Lab results ---
    trace: { stages: [], transform: null, warnings: [] },
    compareTrace: { stages: [], transform: null, warnings: [] },
    evaluation: null,
    compareEvalChroma: null,
    compareEvalGraph: null,
    evaluating: false,
    rerankModels: [],
    collections: [],

    // --- Insight ---
    answerSentiment: null,
    compareSentChroma: null,
    compareSentGraph: null,
    emotion: null,
    claimsOpen: false,
    emotionLoading: false,
    queryStartedAt: 0,
    queryMs: 0,
    lastTriples: [],
    toast: '',

    // --- Drawers ---
    historyOpen: false,
    history: [],
    historyQuery: '',
    collectionsOpen: false,
    pendingDelete: null,

    // --- System prompt ---
    systemPrompt: 'Answer based strictly on the retrieved context. If the context does not contain the answer, say so rather than guessing. Cite source chunks by index [1], [2], etc.',

    // --- Tuning ---
    chunk_size: 800,
    chunk_overlap: 120,
    chunking_strategy: 'fixed',
    top_k: 5,
    similarity_threshold: 0.0,
    mmr_diversity: 0.5,
    graph_hops: 1,
    max_triples_per_chunk: 8,
    triple_limit: 25,
    temperature: 0.3,
    max_output_tokens: 1024,

    // --- Retrieval Lab ---
    search_mode: 'dense',
    hybrid_alpha: 0.5,
    fetch_k: 20,
    query_transform: 'none',
    multi_query_n: 3,
    rerank: 'none',
    context_window: 0,
    context_order: 'score',
    max_context_tokens: 0,
    source_filter: '',
    check_groundedness: false,
    entity_match: 'contains',
    graph_direction: 'both',
    contextual_headers: false,

    // =========================================================
    // Lifecycle
    // =========================================================

    init() {
      this.setModeClass(this.backend);
      this.applyLayout();
      this.applyTheme();
      matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
        if (this.themePref === 'auto') this.applyTheme();
      });
      this.$watch('backend', v => {
        this.setModeClass(v);
      });
      this.loadSavedKeys();
      this.loadCollections();
      this.chatInit?.();
    },

    // =========================================================
    // Collections
    // =========================================================

    async loadCollections() {
      try {
        const resp = await fetch('/collections');
        if (resp.ok) this.collections = await resp.json();
      } catch (_) {}
    },

    currentSources() {
      const c = this.collections.find(c => c.name === (this.collection || 'default'));
      return c ? c.sources : [];
    },

    // =========================================================
    // Theme
    // =========================================================

    applyTheme() {
      const dark = this.themePref === 'dark'
        || (this.themePref === 'auto' && !matchMedia('(prefers-color-scheme: light)').matches);
      document.documentElement.dataset.theme = dark ? 'dark' : 'light';
      // vis-network draws on canvas, so its colours must be re-resolved from the new tokens
      const opts = this._makeNetworkOptions();
      if (this.network) this.network.setOptions(opts);
      if (this.compareNetwork) this.compareNetwork.setOptions(opts);
    },

    cycleTheme() {
      const order = ['auto', 'light', 'dark'];
      this.themePref = order[(order.indexOf(this.themePref) + 1) % order.length];
      try { localStorage.setItem('arena.theme', this.themePref); } catch (_) {}
      this.applyTheme();
    },

    // =========================================================
    // Resizable layout
    // =========================================================

    applyLayout() {
      const root = document.documentElement.style;
      root.setProperty('--sidebar-width', this.layout.sidebar + 'px');
      root.setProperty('--answer-height', this.layout.answer + 'px');
      root.setProperty('--compare-split', this.layout.split + '%');
      document.body.classList.toggle('sidebar-collapsed', this.sidebarCollapsed);
    },

    startResize(kind, evt) {
      if (evt.button !== 0) return;
      evt.preventDefault();
      const handle = evt.currentTarget;
      handle.setPointerCapture(evt.pointerId);
      document.body.classList.add('is-resizing', kind === 'answer' ? 'resizing-y' : 'resizing-x');
      const [lo, hi] = LAYOUT_LIMITS[kind];
      const clamp = v => Math.round(Math.min(hi, Math.max(lo, v)));
      // The split is relative to whichever compare row holds the handle
      const row = kind === 'split' ? handle.parentElement.getBoundingClientRect() : null;

      const onMove = e => {
        if (kind === 'sidebar') this.layout.sidebar = clamp(e.clientX);
        else if (kind === 'answer') this.layout.answer = clamp(window.innerHeight - e.clientY);
        else this.layout.split = clamp(((e.clientX - row.left) / row.width) * 100);
        this.applyLayout();
      };
      const onUp = () => {
        handle.removeEventListener('pointermove', onMove);
        handle.removeEventListener('pointerup', onUp);
        document.body.classList.remove('is-resizing', 'resizing-x', 'resizing-y');
        prefs.set('layout', this.layout);
        this.network?.redraw();
        this.compareNetwork?.redraw();
      };
      handle.addEventListener('pointermove', onMove);
      handle.addEventListener('pointerup', onUp);
    },

    resetLayout(kind) {
      if (kind) this.layout[kind] = LAYOUT_DEFAULTS[kind];
      else this.layout = { ...LAYOUT_DEFAULTS };
      prefs.set('layout', this.layout);
      this.applyLayout();
    },

    toggleSidebar() {
      if (window.innerWidth <= 768) { this.sidebarOpen = !this.sidebarOpen; return; }
      this.sidebarCollapsed = !this.sidebarCollapsed;
      prefs.set('sidebarCollapsed', this.sidebarCollapsed);
      this.applyLayout();
      this.$nextTick(() => { this.network?.redraw(); this.compareNetwork?.redraw(); });
    },

    // =========================================================
    // Keyboard shortcuts & command palette
    // =========================================================

    onGlobalKey(e) {
      const mod = e.metaKey || e.ctrlKey;
      const t = e.target;
      const typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable);

      if (e.key === 'Escape') {
        if (this.paletteOpen) this.paletteOpen = false;
        else if (this.shortcutsOpen) this.shortcutsOpen = false;
        else if (this.historyOpen) this.historyOpen = false;
        else if (this.collectionsOpen) this.collectionsOpen = false;
        else if (this.studioOpen) this.studioOpen = false;
        else if (this.settingsOpen) this.settingsOpen = false;
        else if (this.sidebarOpen) this.sidebarOpen = false;
        else if (typing) t.blur();
        return;
      }
      if (mod && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        const q = document.getElementById('question-input');
        if (this.paletteOpen) this.paletteOpen = false;
        else if (document.activeElement === q) this.openPalette();
        else q?.focus();
        return;
      }
      if (mod && e.key === 'Enter') { e.preventDefault(); this.query(); return; }
      if (mod && e.key === ',') { e.preventDefault(); this.settingsOpen = !this.settingsOpen; return; }
      if (typing || mod || e.altKey || this.paletteOpen || this.settingsOpen || this.historyOpen || this.collectionsOpen || this.studioOpen) return;

      const actions = {
        '1': () => this.setBackend('chroma'),
        '2': () => this.setBackend('graph'),
        '3': () => this.setBackend('compare'),
        '4': () => this.setBackend('chat'),
        '[': () => this.toggleSidebar(),
        'h': () => this.openHistory(),
        'd': () => this.openCollections(),
        't': () => this.cycleTheme(),
        '?': () => { this.shortcutsOpen = true; },
      };
      const action = actions[e.key.toLowerCase()];
      if (action) { e.preventDefault(); action(); }
    },

    openPalette() {
      this.paletteQuery = '';
      this.paletteIndex = 0;
      this.paletteOpen = true;
      // x-show reveals the overlay after this tick; focus once it is actually displayed
      requestAnimationFrame(() => requestAnimationFrame(() => document.getElementById('palette-input')?.focus()));
    },

    paletteCommands() {
      const cmds = [
        { id: 'mode-chroma', group: 'Mode', label: 'Switch to Chroma', keys: '1', run: () => this.setBackend('chroma') },
        { id: 'mode-graph', group: 'Mode', label: 'Switch to Graph', keys: '2', run: () => this.setBackend('graph') },
        { id: 'mode-compare', group: 'Mode', label: 'Switch to Compare', keys: '3', run: () => this.setBackend('compare') },
        { id: 'mode-chat', group: 'Mode', label: 'Switch to Chat', keys: '4', run: () => this.setBackend('chat') },
        { id: 'new-bot', group: 'Bot', label: 'New bot from current settings', run: () => this.openStudio() },
        { id: 'run', group: 'Query', label: 'Run query', keys: 'Ctrl/⌘ ↵', run: () => this.query() },
        { id: 'focus', group: 'Query', label: 'Focus question bar', keys: 'Ctrl/⌘ K', run: () => document.getElementById('question-input')?.focus() },
        { id: 'theme', group: 'View', label: 'Cycle theme (now: ' + this.themePref + ')', keys: 'T', run: () => this.cycleTheme() },
        { id: 'sidebar', group: 'View', label: this.sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar', keys: '[', run: () => this.toggleSidebar() },
        { id: 'reset-layout', group: 'View', label: 'Reset panel sizes', run: () => this.resetLayout() },
        { id: 'settings', group: 'App', label: 'Open settings', keys: 'Ctrl/⌘ ,', run: () => { this.settingsOpen = true; } },
        { id: 'history', group: 'Data', label: 'Open query history', keys: 'H', run: () => this.openHistory() },
        { id: 'collections', group: 'Data', label: 'Manage collections', keys: 'D', run: () => this.openCollections() },
        { id: 'export-md', group: 'Export', label: 'Copy answer as Markdown', run: () => this.copyMarkdown() },
        { id: 'export-json', group: 'Export', label: 'Download result as JSON', run: () => this.downloadJSON() },
        { id: 'shortcuts', group: 'App', label: 'Show keyboard shortcuts', keys: '?', run: () => { this.shortcutsOpen = true; } },
      ];
      for (const c of this.collections) {
        cmds.push({ id: 'col-' + c.name, group: 'Collection', label: 'Use collection: ' + c.name + ' (' + c.chunks + ' chunks)', run: () => { this.collection = c.name; this.source_filter = ''; } });
      }
      for (const b of (this.bots || [])) {
        cmds.push({ id: 'bot-' + b.id, group: 'Bot', label: 'Chat with ' + b.emoji + ' ' + b.name, run: () => { this.setBackend('chat'); this.selectBot(b); } });
      }
      for (const k of this.savedKeys) {
        cmds.push({ id: 'key-' + k.id, group: 'Key', label: 'Use key: ' + k.label + ' (' + k.provider + ')', run: () => this.loadKey(k) });
      }
      return cmds;
    },

    paletteItems() {
      const q = this.paletteQuery.trim().toLowerCase();
      const all = this.paletteCommands();
      if (!q) return all;
      // Loose subsequence match, so "swg" finds "Switch to Graph"
      return all.filter(c => {
        const hay = (c.group + ' ' + c.label).toLowerCase();
        let i = 0;
        for (const ch of hay) if (ch === q[i]) i++;
        return i === q.length;
      });
    },

    runPaletteItem(item) {
      if (!item) return;
      this.paletteOpen = false;
      // Hand focus back to the page, or the hidden input would swallow single-key shortcuts
      document.activeElement?.blur();
      this.$nextTick(() => item.run());
    },

    // =========================================================
    // Backend toggle
    // =========================================================

    // Only swap the mode class: body also carries layout/resizing classes
    setModeClass(b) {
      document.body.classList.remove('mode-chroma', 'mode-graph', 'mode-compare', 'mode-chat');
      document.body.classList.add('mode-' + b);
    },

    setBackend(b) {
      if (this.backend === b) return;
      this.backend = b;
      this.setModeClass(b);
      if (b === 'graph') {
        this.$nextTick(() => this.initGraph());
      }
      if (b === 'compare') {
        this.$nextTick(() => this.initCompareGraph());
      }
    },

    // =========================================================
    // Settings helpers
    // =========================================================

    keyStatusLabel() {
      const labels = {
        untested: 'Not tested',
        validating: 'Validating...',
        valid: 'Valid',
        invalid: this.keyError || 'Invalid key',
      };
      return labels[this.keyStatus] || '';
    },

    onProviderChange() {
      this.apiKey = '';
      this.keyId = null;
      this.keyHint = '';
      this.keyStatus = 'untested';
      this.keyError = '';
      this.genModels = [];
      this.embedModels = [];
      this.selectedGenModel = '';
      this.selectedEmbedModel = '';
    },

    // =========================================================
    // API key validation
    // =========================================================

    async testKey() {
      if (!this.hasKey()) return;
      this.keyStatus = 'validating';
      this.keyError = '';
      try {
        const resp = await fetch('/config/validate-key', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...this.keyRef(), provider: this.provider }),
        });
        const data = await resp.json();
        if (!resp.ok || data.error) {
          this.keyStatus = 'invalid';
          this.keyError = data.error || 'Invalid key';
          return;
        }
        this.keyStatus = 'valid';
        this.genModels = (data.gen_models || []).map(m => ({
          value: m.name || m,
          label: m.display_name || m.name || m,
        }));
        this.rerankModels = (data.rerank_models || []).map(m => ({ value: m.name, label: m.display_name || m.name }));
        this.embedModels = (data.embed_models || []).map(m => ({
          value: m.name || m,
          label: m.display_name || m.name || m,
        }));
        if (this.genModels.length && !this.selectedGenModel) {
          this.selectedGenModel = this.genModels[0].value;
        }
        if (this.embedModels.length && !this.selectedEmbedModel) {
          this.selectedEmbedModel = this.embedModels[0].value;
        }
      } catch (err) {
        this.keyStatus = 'invalid';
        this.keyError = 'Network error';
      }
    },

    // =========================================================
    // Saved keys
    // =========================================================

    hasKey() {
      return !!this.apiKey.trim() || this.keyId !== null;
    },

    // A typed key wins over a selected saved one
    keyRef() {
      return this.apiKey.trim() ? { api_key: this.apiKey.trim() } : { key_id: this.keyId };
    },

    onKeyInput() {
      if (this.apiKey) { this.keyId = null; this.keyHint = ''; }
      this.keyStatus = 'untested';
    },

    async loadSavedKeys() {
      try {
        const resp = await fetch('/keys');
        if (resp.ok) {
          this.savedKeys = await resp.json();
          this.savedKeysLoaded = true;
          // Restore the last-used key (and its provider) if the field is empty
          if (!this.hasKey()) {
            const active = this.savedKeys.find(k => k.is_active);
            if (active) this.loadKey(active, false);
          }
        }
      } catch (_) {}
    },

    loadKey(sk, activateOnServer = true) {
      this.provider = sk.provider;
      this.apiKey = '';
      this.keyId = sk.id;
      this.keyHint = sk.key_hint;
      this.keyStatus = 'untested';
      this.keyError = '';
      this.genModels = [];
      this.embedModels = [];
      this.selectedGenModel = '';
      this.selectedEmbedModel = '';
      if (activateOnServer) {
        fetch(`/keys/${sk.id}/activate?provider=${sk.provider}`, { method: 'POST' }).catch(() => {});
        this.savedKeys.forEach(k => { if (k.provider === sk.provider) k.is_active = k.id === sk.id; });
      }
      this.testKey();
    },

    async saveCurrentKey() {
      if (!this.newKeyLabel.trim() || !this.apiKey) return;
      this.savingKey = true;
      try {
        const resp = await fetch('/keys', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ label: this.newKeyLabel.trim(), provider: this.provider, api_key: this.apiKey }),
        });
        if (resp.ok) {
          const saved = await resp.json();
          this.savedKeys.push(saved);
          this.newKeyLabel = '';
          this.apiKey = '';
          this.keyId = saved.id;
          this.keyHint = saved.key_hint;
          this.savedKeys.forEach(k => { if (k.provider === saved.provider) k.is_active = k.id === saved.id; });
          // A freshly saved key becomes the one restored on next page load
          fetch(`/keys/${saved.id}/activate?provider=${saved.provider}`, { method: 'POST' }).catch(() => {});
        }
      } catch (_) {}
      this.savingKey = false;
    },

    async deleteKey(id) {
      try {
        const resp = await fetch(`/keys/${id}`, { method: 'DELETE' });
        if (resp.ok) {
          this.savedKeys = this.savedKeys.filter(k => k.id !== id);
          if (this.keyId === id) this.onProviderChange();
        }
      } catch (_) {}
    },

    // =========================================================
    // Ingest
    // =========================================================

    async ingest() {
      if (this.isIngesting) return;
      this.isIngesting = true;
      this.ingestResult = null;

      const fd = new FormData();
      fd.append('collection', this.collection || 'default');
      const ref = this.keyRef();
      for (const [k, v] of Object.entries(ref)) fd.append(k, v);
      fd.append('embedding_model', this.selectedEmbedModel || 'gemini-embedding-001');
      fd.append('gen_model', this.selectedGenModel || 'gemini-2.5-flash');
      fd.append('provider', this.provider);
      fd.append('tuning', JSON.stringify({
        chunk_size: this.chunk_size,
        chunk_overlap: this.chunk_overlap,
        chunking_strategy: this.chunking_strategy,
        max_triples_per_chunk: this.max_triples_per_chunk,
        triple_limit: this.triple_limit,
        contextual_headers: this.contextual_headers,
      }));

      if (this.ingestFiles.length > 0) {
        for (const f of this.ingestFiles) {
          fd.append('files', f);
        }
      } else {
        fd.append('text', this.ingestText);
      }

      try {
        const resp = await fetch('/ingest', { method: 'POST', body: fd });
        const data = await resp.json().catch(() => ({}));
        this.ingestResult = resp.ok
          ? data
          : { error: typeof data.detail === 'string' ? data.detail : `Ingest failed (HTTP ${resp.status})` };
        if (resp.ok) this.loadCollections();
      } catch (err) {
        this.ingestResult = { error: err.message || 'Network error' };
      } finally {
        this.isIngesting = false;
      }
    },

    formatIngestResult(r) {
      if (!r) return '';
      const parts = [];
      if (r.documents !== undefined) parts.push('Documents: ' + r.documents);
      if (r.num_chunks !== undefined) parts.push('Chunks: ' + r.num_chunks);
      if (r.num_triples !== undefined) parts.push('Triples: ' + r.num_triples);
      if (r.collection) parts.push('Collection: ' + r.collection);
      if (r.message) parts.push(r.message);
      return parts.join('\n') || JSON.stringify(r);
    },

    // =========================================================
    // Query (SSE via fetch + ReadableStream)
    // =========================================================

    queryBody() {
      return {
        question: this.question,
        backend: this.backend,
        collection: this.collection || 'default',
        ...this.keyRef(),
        gen_model: this.selectedGenModel,
        embedding_model: this.selectedEmbedModel,
        provider: this.provider,
        tuning: {
          top_k: this.top_k,
          similarity_threshold: this.similarity_threshold,
          mmr_diversity: this.mmr_diversity,
          graph_hops: this.graph_hops,
          triple_limit: this.triple_limit,
          temperature: this.temperature,
          max_output_tokens: this.max_output_tokens,
          system_prompt: this.systemPrompt,
          search_mode: this.search_mode,
          hybrid_alpha: this.hybrid_alpha,
          fetch_k: this.fetch_k,
          query_transform: this.query_transform,
          multi_query_n: this.multi_query_n,
          rerank: this.rerank,
          context_window: this.context_window,
          context_order: this.context_order,
          max_context_tokens: this.max_context_tokens,
          source_filter: this.source_filter || null,
          check_groundedness: this.check_groundedness,
          entity_match: this.entity_match,
          graph_direction: this.graph_direction,
        },
      };
    },

    async query() {
      if (this.isQuerying || !this.question.trim()) return;

      this.isQuerying = true;
      this.answerDone = false;
      this.answer = '';
      this.chunks = [];
      this.graphNodes = [];
      this.graphEdges = [];
      this.embedTiming = null;
      this.eventLog = [];
      this.compareAnswerChroma = '';
      this.compareAnswerGraph = '';
      this.compareChromaDone = false;
      this.compareGraphDone = false;
      this.compareChromaChunks = [];
      this.compareGraphNodes = [];
      this.compareGraphEdges = [];
      this.trace = { stages: [], transform: null, warnings: [] };
      this.compareTrace = { stages: [], transform: null, warnings: [] };
      this.evaluation = null;
      this.compareEvalChroma = null;
      this.compareEvalGraph = null;
      this.evaluating = false;
      this.answerSentiment = null;
      this.compareSentChroma = null;
      this.compareSentGraph = null;
      this.emotion = null;
      this.lastTriples = [];
      this.queryStartedAt = performance.now();

      if (this.backend === 'graph') {
        this.initGraph();
      }
      if (this.backend === 'compare') {
        this.initCompareGraph();
      }

      const body = this.queryBody();

      try {
        // POST keeps the key and prompt out of URLs, browser history and access logs
        const response = await fetch('/query', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!response.ok) {
          const errText = await response.text();
          this.answer = 'Error: ' + (errText || response.statusText);
          this.answerDone = true;
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const events = buffer.split('\n\n');
          buffer = events.pop();
          for (const block of events) {
            if (block.trim()) this.handleSSEBlock(block);
          }
        }

        if (buffer.trim()) this.handleSSEBlock(buffer);

      } catch (err) {
        this.answer = 'Error: ' + (err.message || 'Unknown error');
        this.answerDone = true;
      } finally {
        this.isQuerying = false;
        if (!this.answerDone) this.answerDone = true;
        this.queryMs = Math.round(performance.now() - this.queryStartedAt);
        this.saveHistory();
      }
    },

    handleSSEBlock(block) {
      const lines = block.split('\n');
      let eventType = '';
      let dataStr = '';
      for (const line of lines) {
        if (line.startsWith('event: ')) eventType = line.slice(7).trim();
        if (line.startsWith('data: ')) dataStr = line.slice(6).trim();
      }
      if (!eventType || !dataStr) return;

      let data;
      try {
        data = JSON.parse(dataStr);
      } catch {
        return;
      }

      this.eventLog.push({ type: eventType, ts: Date.now() });
      this.handleEvent(eventType, data);
    },

    handleEvent(type, data) {
      switch (type) {
        case 'embedding_started':
          break;

        case 'embedding_done':
          if (data.duration_ms !== undefined) {
            this.embedTiming = Math.round(data.duration_ms);
          }
          break;

        case 'compare_started':
          break;

        case 'candidates_found':
          this.chunks = [];
          this.graphNodes = [];
          this.graphEdges = [];
          if (this.backend === 'graph') this.initGraph();
          break;

        case 'chunk_scored':
          this.chunks.push(this._makeChunk(data, this.chunks));
          break;

        case 'query_transformed':
          this.trace.transform = data;
          break;

        case 'chroma_query_transformed':
          this.compareTrace.transform = data;
          break;

        case 'pipeline_trace':
          this.trace.stages = data.stages || [];
          break;

        case 'chroma_pipeline_trace':
          this.compareTrace.stages = data.stages || [];
          break;

        case 'pipeline_warning':
          this.trace.warnings.push(data.stage + ': ' + data.message);
          break;

        case 'chroma_pipeline_warning':
          this.compareTrace.warnings.push(data.stage + ': ' + data.message);
          break;

        case 'evaluation_started':
          // The answer has finished streaming; only the judge is still running
          this.evaluating = true;
          this.answerDone = true;
          this.compareChromaDone = true;
          this.compareGraphDone = true;
          break;

        case 'evaluation':
          this.evaluation = data;
          this.evaluating = false;
          break;

        case 'chroma_evaluation':
          this.compareEvalChroma = data;
          break;

        case 'graph_evaluation':
          this.compareEvalGraph = data;
          this.evaluating = false;
          break;

        case 'answer_sentiment':
          this.answerSentiment = data;
          break;

        case 'chroma_answer_sentiment':
          this.compareSentChroma = data;
          break;

        case 'graph_answer_sentiment':
          this.compareSentGraph = data;
          break;

        case 'hop_traversed': {
          this.lastTriples.push(...(data.triples || []));
          this._addTriplesTo(data.triples || [], this._nodesDS, this._edgesDS, this.graphNodes, this.graphEdges);
          break;
        }

        // ---- Compare mode: chroma side ----
        case 'chroma_candidates_found':
          this.compareChromaChunks = [];
          break;

        case 'chroma_chunk_scored':
          this.compareChromaChunks.push(this._makeChunk(data, this.compareChromaChunks));
          break;

        case 'chroma_answer_token':
          if (data.token !== undefined) this.compareAnswerChroma += data.token;
          break;

        case 'chroma_error':
          this.compareAnswerChroma = 'Error: ' + (data.message || JSON.stringify(data));
          this.compareChromaDone = true;
          break;

        // ---- Compare mode: graph side ----
        case 'graph_candidates_found':
          this.compareGraphNodes = [];
          this.compareGraphEdges = [];
          if (this._compareNodesDS) this._compareNodesDS.clear();
          if (this._compareEdgesDS) this._compareEdgesDS.clear();
          break;

        case 'graph_hop_traversed': {
          this.lastTriples.push(...(data.triples || []));
          this._addTriplesTo(data.triples || [], this._compareNodesDS, this._compareEdgesDS, this.compareGraphNodes, this.compareGraphEdges);
          break;
        }

        case 'graph_answer_token':
          if (data.token !== undefined) this.compareAnswerGraph += data.token;
          break;

        case 'graph_error':
          this.compareAnswerGraph = 'Error: ' + (data.message || JSON.stringify(data));
          this.compareGraphDone = true;
          break;

        case 'context_assembled':
          break;

        case 'answer_token':
          if (data.token !== undefined) {
            this.answer += data.token;
          } else if (data.text !== undefined) {
            this.answer += data.text;
          }
          break;

        case 'done':
          this.evaluating = false;
          this.answerDone = true;
          this.compareChromaDone = true;
          this.compareGraphDone = true;
          this.isQuerying = false;
          break;

        case 'error':
          this.answer = 'Error: ' + (data.message || data.error || JSON.stringify(data));
          this.answerDone = true;
          this.isQuerying = false;
          break;

        default:
          break;
      }
    },

    _makeChunk(data, list) {
      return {
        id: data.chunk_id ?? data.id ?? list.length,
        rank: data.rank ?? list.length + 1,
        score: data.score,
        text: data.text ?? data.content ?? '',
        scores: data.scores || null,
        cite: data.cite ?? null,
        source: data.source || null,
        expanded: !!data.expanded,
        dropped: !!data.dropped,
        entities: data.entities || [],
        sentiment: data.sentiment || null,
      };
    },

    sentimentGlyph(s) {
      if (!s) return '';
      return s.label === 'positive' ? '\u25B2' : s.label === 'negative' ? '\u25BC' : '\u25C6';
    },

    // =========================================================
    // Emotion analysis (LLM)
    // =========================================================

    async analyzeEmotion() {
      const text = this.backend === 'compare' ? this.compareAnswerChroma + '\n\n' + this.compareAnswerGraph : this.answer;
      if (!text.trim() || this.emotionLoading) return;
      this.emotionLoading = true;
      try {
        const resp = await fetch('/analyze/emotion', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, ...this.keyRef(), provider: this.provider, gen_model: this.selectedGenModel }),
        });
        const data = await resp.json().catch(() => ({}));
        this.emotion = resp.ok ? data : { error: data.detail || 'Emotion analysis failed' };
      } catch (err) {
        this.emotion = { error: err.message };
      } finally {
        this.emotionLoading = false;
      }
    },

    // =========================================================
    // History
    // =========================================================

    _snapshot() {
      const compare = this.backend === 'compare';
      return {
        settings: { ...this.queryBody().tuning, gen_model: this.selectedGenModel, embedding_model: this.selectedEmbedModel, provider: this.provider },
        answer: compare ? { chroma: this.compareAnswerChroma, graph: this.compareAnswerGraph } : this.answer,
        chunks: compare ? this.compareChromaChunks : this.chunks,
        triples: this.lastTriples,
        evaluation: compare ? { chroma: this.compareEvalChroma, graph: this.compareEvalGraph } : this.evaluation,
        sentiment: compare ? { chroma: this.compareSentChroma, graph: this.compareSentGraph } : this.answerSentiment,
        trace: compare ? this.compareTrace : this.trace,
        duration_ms: this.queryMs,
      };
    },

    async saveHistory() {
      const answer = this.backend === 'compare' ? this.compareAnswerChroma + this.compareAnswerGraph : this.answer;
      if (!answer.trim() || answer.startsWith('Error:')) return;
      try {
        await fetch('/history', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            question: this.question,
            backend: this.backend,
            collection: this.collection || 'default',
            payload: this._snapshot(),
          }),
        });
        if (this.historyOpen) this.loadHistory();
      } catch (_) {}
    },

    async loadHistory() {
      try {
        const resp = await fetch('/history?q=' + encodeURIComponent(this.historyQuery));
        if (resp.ok) this.history = await resp.json();
      } catch (_) {}
    },

    openHistory() {
      this.collectionsOpen = false;
      this.historyOpen = true;
      this.loadHistory();
    },

    async togglePin(h) {
      await fetch(`/history/${h.id}/pin?pinned=${!h.pinned}`, { method: 'POST' }).catch(() => {});
      this.loadHistory();
    },

    async deleteHistory(h) {
      await fetch(`/history/${h.id}`, { method: 'DELETE' }).catch(() => {});
      this.history = this.history.filter(x => x.id !== h.id);
    },

    // Put a past result back on screen without re-running it
    restoreHistory(h) {
      const p = h.payload;
      this.setBackend(h.backend);
      this.question = h.question;
      this.collection = h.collection;
      this.historyOpen = false;
      this.$nextTick(() => {
        if (h.backend === 'compare') {
          this.compareAnswerChroma = p.answer.chroma || '';
          this.compareAnswerGraph = p.answer.graph || '';
          this.compareChromaChunks = p.chunks || [];
          this.compareEvalChroma = p.evaluation?.chroma || null;
          this.compareEvalGraph = p.evaluation?.graph || null;
          this.compareSentChroma = p.sentiment?.chroma || null;
          this.compareSentGraph = p.sentiment?.graph || null;
          this.compareTrace = p.trace || { stages: [], transform: null, warnings: [] };
          this.compareChromaDone = this.compareGraphDone = true;
          this.initCompareGraph();
          this._addTriplesTo(p.triples || [], this._compareNodesDS, this._compareEdgesDS, this.compareGraphNodes = [], this.compareGraphEdges = []);
        } else {
          this.answer = typeof p.answer === 'string' ? p.answer : '';
          this.chunks = p.chunks || [];
          this.evaluation = p.evaluation || null;
          this.answerSentiment = p.sentiment || null;
          this.trace = p.trace || { stages: [], transform: null, warnings: [] };
          this.answerDone = true;
          if (h.backend === 'graph') {
            this.initGraph();
            this._addTriplesTo(p.triples || [], this._nodesDS, this._edgesDS, this.graphNodes = [], this.graphEdges = []);
          }
        }
        this.lastTriples = p.triples || [];
        this.queryMs = p.duration_ms || 0;
      });
    },

    rerunHistory(h) {
      this.restoreHistory(h);
      this.$nextTick(() => this.query());
    },

    relativeTime(ts) {
      const t = new Date(ts.replace(' ', 'T') + 'Z').getTime();
      const s = Math.max(0, (Date.now() - t) / 1000);
      if (s < 60) return 'just now';
      if (s < 3600) return Math.floor(s / 60) + 'm ago';
      if (s < 86400) return Math.floor(s / 3600) + 'h ago';
      return Math.floor(s / 86400) + 'd ago';
    },

    // =========================================================
    // Export
    // =========================================================

    _markdown(question, backend, collection, p) {
      const lines = [`# ${question}`, '', `*${backend} · collection \`${collection}\` · ${new Date().toISOString().slice(0, 16).replace('T', ' ')}*`, ''];
      const section = (title, answer, ev) => {
        lines.push(`## ${title}`, '', answer || '_(no answer)_', '');
        if (ev && ev.claims && ev.claims.length) {
          lines.push(`**Groundedness:** ${this.evalLabel(ev)}`, '');
          ev.claims.forEach(c => lines.push(`- ${c.supported ? '✓' : '✗'} ${c.claim}${c.sources.length ? ' ' + c.sources.map(n => `[${n}]`).join('') : ''}`));
          lines.push('');
        }
      };
      if (backend === 'compare') {
        section('Chroma answer', p.answer.chroma, p.evaluation?.chroma);
        section('Graph answer', p.answer.graph, p.evaluation?.graph);
      } else {
        section('Answer', p.answer, p.evaluation);
      }
      if (p.chunks && p.chunks.length) {
        lines.push('## Sources', '');
        p.chunks.filter(c => c.cite).sort((a, b) => a.cite - b.cite).forEach(c => {
          lines.push(`**[${c.cite}]** \`${c.id}\`${c.source ? ' · ' + c.source : ''} · score ${(c.score ?? 0).toFixed(3)}`, '', '> ' + c.text.replace(/\n/g, '\n> '), '');
        });
      }
      if (p.triples && p.triples.length) {
        lines.push('## Graph triples', '');
        p.triples.forEach(t => lines.push(`- ${t.subject} —[${t.relation}]→ ${t.object}`));
        lines.push('');
      }
      return lines.join('\n');
    },

    async copyMarkdown(h = null) {
      const md = h
        ? this._markdown(h.question, h.backend, h.collection, h.payload)
        : this._markdown(this.question, this.backend, this.collection || 'default', this._snapshot());
      try {
        await navigator.clipboard.writeText(md);
        this.flash('Markdown copied');
      } catch (_) {
        this._download(md, 'answer.md', 'text/markdown');
      }
    },

    downloadJSON(h = null) {
      const data = h
        ? { question: h.question, backend: h.backend, collection: h.collection, created_at: h.created_at, ...h.payload }
        : { question: this.question, backend: this.backend, collection: this.collection || 'default', ...this._snapshot() };
      const slug = (data.question || 'result').toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 40);
      this._download(JSON.stringify(data, null, 2), `${slug || 'result'}.json`, 'application/json');
    },

    _download(text, filename, type) {
      const url = URL.createObjectURL(new Blob([text], { type }));
      const a = Object.assign(document.createElement('a'), { href: url, download: filename });
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    },

    flash(msg) {
      this.toast = msg;
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(() => { this.toast = ''; }, 1800);
    },

    // =========================================================
    // Collections manager
    // =========================================================

    openCollections() {
      this.historyOpen = false;
      this.collectionsOpen = true;
      this.pendingDelete = null;
      this.loadCollections();
    },

    useCollection(c) {
      this.collection = c.name;
      this.source_filter = '';
      // Querying needs the same embedding model the collection was built with
      if (c.embed_model && this.embedModels.some(m => m.value === c.embed_model)) {
        this.selectedEmbedModel = c.embed_model;
      }
      this.collectionsOpen = false;
      this.flash('Using ' + c.name);
    },

    async deleteCollection(c) {
      // Two-step confirm inside the UI (no browser dialogs)
      if (this.pendingDelete !== c.name) { this.pendingDelete = c.name; return; }
      this.pendingDelete = null;
      const resp = await fetch('/collections/' + encodeURIComponent(c.name), { method: 'DELETE' }).catch(() => null);
      if (resp && resp.ok) {
        this.collections = this.collections.filter(x => x.name !== c.name);
        if (this.collection === c.name) this.collection = 'default';
        this.flash('Deleted ' + c.name);
      } else {
        this.flash('Delete failed');
      }
    },

    sentimentBar(dist) {
      const total = (dist.positive + dist.neutral + dist.negative) || 1;
      return ['positive', 'neutral', 'negative'].map(k => ({ k, pct: (dist[k] / total) * 100, n: dist[k] }));
    },

    // =========================================================
    // Score & evaluation formatting
    // =========================================================

    formatScoreChip(kind, v) {
      if (kind === 'fused') return v.toFixed(4);
      if (kind === 'bm25' || kind === 'rerank') return v.toFixed(1);
      return v.toFixed(3);
    },

    scoreTitle(kind) {
      return {
        dense: 'Cosine similarity between question and chunk embeddings',
        bm25: 'BM25 keyword relevance (unbounded)',
        fused: 'Reciprocal Rank Fusion score across result lists',
        rerank: 'Reranker relevance score',
      }[kind] || kind;
    },

    evalLabel(ev) {
      if (!ev) return '';
      if (ev.error) return 'check failed';
      if (ev.score === null || ev.score === undefined) return 'no claims to check';
      const ok = ev.claims.filter(c => c.supported).length;
      return `grounded ${Math.round(ev.score * 100)}% · ${ok}/${ev.claims.length} claims`;
    },

    evalClass(ev) {
      if (!ev || ev.error || ev.score === null || ev.score === undefined) return 'eval-neutral';
      return ev.score >= 0.8 ? 'eval-good' : ev.score >= 0.5 ? 'eval-warn' : 'eval-bad';
    },

    evalTooltip(ev) {
      if (!ev || !ev.claims) return '';
      return ev.claims.map(c => (c.supported ? '✓ ' : '✗ ') + c.claim).join('\n');
    },

    // =========================================================
    // vis-network helpers
    // =========================================================

    _addTriplesTo(triples, nodesDS, edgesDS, nodesArr, edgesArr) {
      if (!triples.length) return;
      const newNodes = [];
      const newEdges = [];
      const existingIds = new Set(nodesArr.map(n => n.id));

      for (const triple of triples) {
        const subj = String(triple.subject || '');
        const obj = String(triple.object || '');
        const rel = String(triple.relation || triple.predicate || '');
        if (!subj || !obj) continue;

        if (!existingIds.has(subj)) {
          newNodes.push({ id: subj, label: subj });
          existingIds.add(subj);
          nodesArr.push({ id: subj, label: subj });
        }
        if (!existingIds.has(obj)) {
          newNodes.push({ id: obj, label: obj });
          existingIds.add(obj);
          nodesArr.push({ id: obj, label: obj });
        }

        const edgeId = `${subj}__${rel}__${obj}`;
        newEdges.push({ id: edgeId, from: subj, to: obj, label: rel });
        edgesArr.push({ id: edgeId, from: subj, to: obj, label: rel });
      }

      if (nodesDS) nodesDS.update(newNodes);
      if (edgesDS) edgesDS.update(newEdges);
    },

    _makeNetworkOptions() {
      // Canvas can't use CSS vars directly, so resolve the theme tokens once
      const css = getComputedStyle(document.documentElement);
      const token = (name, fallback) => css.getPropertyValue(name).trim() || fallback;
      const accent = token('--accent-graph', '#A78BFA');
      const surface = token('--surface-solid', '#0F141E');
      const text = token('--text-primary', '#E6EAF2');
      const muted = token('--text-secondary', '#8B95A7');
      const edge = token('--graph-edge', 'rgba(148, 163, 184, 0.28)');
      const halo = token('--bg', '#07090E');
      return {
        physics: {
          enabled: true,
          barnesHut: {
            gravitationalConstant: -3000,
            centralGravity: 0.3,
            springLength: 120,
          },
          stabilization: { iterations: 100 },
        },
        nodes: {
          shape: 'dot',
          size: 14,
          color: {
            background: surface,
            border: accent,
            highlight: { background: accent, border: accent },
            hover: { background: surface, border: text },
          },
          font: { color: text, face: 'JetBrains Mono', size: 11, strokeWidth: 3, strokeColor: halo },
          borderWidth: 2,
          shadow: { enabled: true, color: accent, size: 14, x: 0, y: 0 },
        },
        edges: {
          color: { color: edge, highlight: accent, hover: muted },
          arrows: { to: { enabled: true, scaleFactor: 0.5 } },
          font: { color: muted, face: 'JetBrains Mono', size: 9, align: 'middle', strokeWidth: 3, strokeColor: halo },
          smooth: { type: 'curvedCW', roundness: 0.12 },
          width: 1.2,
        },
        interaction: { hover: true, tooltipDelay: 200, hideEdgesOnDrag: true },
      };
    },

    initGraph() {
      if (typeof vis === 'undefined') return;
      if (this.network) { this.network.destroy(); this.network = null; }
      const container = document.getElementById('graph-container');
      if (!container) return;
      const nodesDS = new vis.DataSet([]);
      const edgesDS = new vis.DataSet([]);
      this._nodesDS = nodesDS;
      this._edgesDS = edgesDS;
      this.network = new vis.Network(container, { nodes: nodesDS, edges: edgesDS }, this._makeNetworkOptions());
    },

    initCompareGraph() {
      if (typeof vis === 'undefined') return;
      if (this.compareNetwork) { this.compareNetwork.destroy(); this.compareNetwork = null; }
      const container = document.getElementById('compare-graph-container');
      if (!container) return;
      const nodesDS = new vis.DataSet([]);
      const edgesDS = new vis.DataSet([]);
      this._compareNodesDS = nodesDS;
      this._compareEdgesDS = edgesDS;
      this.compareNetwork = new vis.Network(container, { nodes: nodesDS, edges: edgesDS }, this._makeNetworkOptions());
    },

    updateGraph(nodes, edges) {
      if (!this._nodesDS || !this._edgesDS) return;
      this._nodesDS.update(nodes);
      this._edgesDS.update(edges);
    },

    // =========================================================
    // Formatters
    // =========================================================

    formatScore(s) {
      if (s === undefined || s === null) return '—';
      return (s * 100).toFixed(1) + '%';
    },
  };
}

window.arenaApp = arenaApp;
