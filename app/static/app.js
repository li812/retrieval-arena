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

    // --- UI ---
    settingsOpen: false,
    sidebarOpen: false,
    sections: {
      chunking: true,
      retrievalChroma: true,
      retrievalGraph: true,
      generation: true,
      systemPrompt: false,
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

    // --- Event log ---
    eventLog: [],

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

    // =========================================================
    // Lifecycle
    // =========================================================

    init() {
      document.body.className = 'mode-chroma';
      this.$watch('backend', v => {
        document.body.className = v === 'chroma' ? 'mode-chroma' : 'mode-graph';
      });
    },

    // =========================================================
    // Backend toggle
    // =========================================================

    setBackend(b) {
      if (this.backend === b) return;
      this.backend = b;
      document.body.className = b === 'chroma' ? 'mode-chroma' : 'mode-graph';
      if (b === 'graph') {
        this.$nextTick(() => this.initGraph());
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

    // =========================================================
    // API key validation
    // =========================================================

    async testKey() {
      if (!this.apiKey.trim()) return;
      this.keyStatus = 'validating';
      this.keyError = '';
      try {
        const resp = await fetch('/config/validate-key', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ api_key: this.apiKey }),
        });
        const data = await resp.json();
        if (!resp.ok || data.error) {
          this.keyStatus = 'invalid';
          this.keyError = data.error || 'Invalid key';
          return;
        }
        this.keyStatus = 'valid';
        this.genModels = (data.gen_models || []).map(m => m.name || m);
        this.embedModels = (data.embed_models || []).map(m => m.name || m);
        if (this.genModels.length && !this.selectedGenModel) {
          this.selectedGenModel = this.genModels[0];
        }
        if (this.embedModels.length && !this.selectedEmbedModel) {
          this.selectedEmbedModel = this.embedModels[0];
        }
      } catch (err) {
        this.keyStatus = 'invalid';
        this.keyError = 'Network error';
      }
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
      fd.append('api_key', this.apiKey);
      fd.append('embedding_model', this.selectedEmbedModel || 'gemini-embedding-001');
      fd.append('gen_model', this.selectedGenModel || 'gemini-2.5-flash');
      fd.append('tuning', JSON.stringify({
        chunk_size: this.chunk_size,
        chunk_overlap: this.chunk_overlap,
        chunking_strategy: this.chunking_strategy,
        max_triples_per_chunk: this.max_triples_per_chunk,
        triple_limit: this.triple_limit,
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
        this.ingestResult = await resp.json();
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

      if (this.backend === 'graph') {
        this.initGraph();
      }

      const params = new URLSearchParams({
        question: this.question,
        backend: this.backend,
        collection: this.collection || 'default',
        api_key: this.apiKey,
        gen_model: this.selectedGenModel,
        embedding_model: this.selectedEmbedModel,
        top_k: this.top_k,
        similarity_threshold: this.similarity_threshold,
        mmr_diversity: this.mmr_diversity,
        graph_hops: this.graph_hops,
        triple_limit: this.triple_limit,
        temperature: this.temperature,
        max_output_tokens: this.max_output_tokens,
        system_prompt: this.systemPrompt,
      });

      try {
        const response = await fetch(`/query?${params}`);
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

        // Process any remaining buffer content
        if (buffer.trim()) this.handleSSEBlock(buffer);

      } catch (err) {
        this.answer = 'Error: ' + (err.message || 'Unknown error');
        this.answerDone = true;
      } finally {
        this.isQuerying = false;
        if (!this.answerDone) this.answerDone = true;
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

        case 'candidates_found':
          this.chunks = [];
          this.graphNodes = [];
          this.graphEdges = [];
          if (this.backend === 'graph') this.initGraph();
          break;

        case 'chunk_scored': {
          const chunk = {
            id: data.chunk_id ?? data.id ?? this.chunks.length,
            rank: data.rank ?? this.chunks.length + 1,
            score: data.score,
            text: data.text ?? data.content ?? '',
          };
          this.chunks.push(chunk);
          break;
        }

        case 'hop_traversed': {
          if (!data.triples || !Array.isArray(data.triples)) break;
          const newNodes = [];
          const newEdges = [];
          const existingIds = new Set(this.graphNodes.map(n => n.id));

          for (const triple of data.triples) {
            const subj = String(triple.subject || '');
            const obj = String(triple.object || '');
            const rel = String(triple.relation || triple.predicate || '');
            if (!subj || !obj) continue;

            if (!existingIds.has(subj)) {
              newNodes.push({ id: subj, label: subj });
              existingIds.add(subj);
              this.graphNodes.push({ id: subj, label: subj });
            }
            if (!existingIds.has(obj)) {
              newNodes.push({ id: obj, label: obj });
              existingIds.add(obj);
              this.graphNodes.push({ id: obj, label: obj });
            }

            const edgeId = `${subj}__${rel}__${obj}`;
            newEdges.push({ id: edgeId, from: subj, to: obj, label: rel });
            this.graphEdges.push({ id: edgeId, from: subj, to: obj, label: rel });
          }

          if (this._nodesDS) this._nodesDS.update(newNodes);
          if (this._edgesDS) this._edgesDS.update(newEdges);
          break;
        }

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
          this.answerDone = true;
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

    // =========================================================
    // vis-network (graph mode)
    // =========================================================

    initGraph() {
      if (typeof vis === 'undefined') return;

      if (this.network) {
        this.network.destroy();
        this.network = null;
      }

      const container = document.getElementById('graph-container');
      if (!container) return;

      const nodesDS = new vis.DataSet([]);
      const edgesDS = new vis.DataSet([]);
      this._nodesDS = nodesDS;
      this._edgesDS = edgesDS;

      this.network = new vis.Network(
        container,
        { nodes: nodesDS, edges: edgesDS },
        {
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
              background: '#1E212B',
              border: '#F2A65A',
              highlight: { background: '#F2A65A', border: '#F2A65A' },
              hover: { background: '#2C3040', border: '#F2A65A' },
            },
            font: {
              color: '#E8E9ED',
              face: 'JetBrains Mono',
              size: 11,
            },
            borderWidth: 2,
          },
          edges: {
            color: { color: '#2C3040', highlight: '#F2A65A', hover: '#8A8F9C' },
            arrows: { to: { enabled: true, scaleFactor: 0.6 } },
            font: { color: '#8A8F9C', face: 'Inter', size: 10, align: 'middle' },
            smooth: { type: 'curvedCW', roundness: 0.1 },
            width: 1.5,
          },
          background: { color: '#14161B' },
          interaction: {
            hover: true,
            tooltipDelay: 200,
            hideEdgesOnDrag: true,
          },
        }
      );
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
