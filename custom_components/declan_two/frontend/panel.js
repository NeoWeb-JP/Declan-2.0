/* Native Home Assistant panel shell. No direct backend calls or embedded secrets. */
class DeclanTwoNativePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: 'open'});
    this._hass = null;
    this._loaded = false;
    this._pending = false;
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; min-height:100%; color:#e7f7ff;
          background:#060d14; font-family:system-ui,sans-serif; }
        * { box-sizing:border-box; }
        .wrap { max-width:960px; margin:auto; padding:16px clamp(12px,3vw,28px) 48px; }
        header { display:flex; align-items:center; gap:14px; flex-wrap:wrap; padding:8px 0 16px;
          border-bottom:1px solid #183341; }
        .brand { display:flex; align-items:center; gap:10px; flex:1; min-width:170px; }
        .orb { display:grid; place-items:center; width:38px; height:38px; border-radius:50%;
          border:1px solid #285267; background:radial-gradient(circle,#184860,#081722 74%);
          box-shadow:0 0 20px #369dcc33; color:#a1ccdf; font-weight:700; }
        h1 { margin:0; font:700 clamp(19px,4vw,24px) ui-monospace,monospace; letter-spacing:.12em; }
        h1 small { font-size:.6em; letter-spacing:.05em; }
        button { cursor:pointer; border:1px solid #315568; border-radius:9px;
          background:#102635; color:#c7f7ff; padding:10px 14px; font:inherit; }
        button:focus-visible { outline:2px solid #91e3ff; outline-offset:3px; }
        .tabs { display:flex; gap:8px; overflow-x:auto; padding:18px 0 6px; scrollbar-width:thin; }
        .tabs button { white-space:nowrap; flex-shrink:0; }
        .tabs button[aria-selected="true"] { background:#184860; border-color:#76dbff; }
        .card { margin-top:14px; padding:22px; border:1px solid #1d3d51;
          background:#0b1a25; border-radius:14px; }
        .state { font-weight:600; }
        .muted { color:#a1ccdf; }
        .mono { font: .82rem ui-monospace,monospace; }
        .menu { display:none; }
        .panel[hidden] { display:none; }
        .panel h2 { margin:0 0 12px; font-size:1.1rem; }
        .turn { padding:14px 0; border-top:1px solid #1d3d51; overflow-wrap:anywhere; }
        .turn p { margin:6px 0; white-space:pre-wrap; }
        .turn .reply { color:#a1ccdf; }
        .chat-controls { display:flex; gap:8px; margin:8px 0 14px; }
        .chat-controls input { flex:1; min-width:0; padding:12px; border-radius:9px; border:1px solid #315568; background:#102635; color:#e7f7ff; font:inherit; }
        .chat-form label { display:block; margin-top:14px; }
        .chat-replies { margin-bottom:18px; }
        .player-row { display:grid; grid-template-columns:minmax(120px,1fr) minmax(160px,2fr); gap:12px; align-items:center; padding:12px 0; border-top:1px solid #1d3d51; }
        .player-row select { width:100%; min-width:0; padding:10px; border-radius:9px; border:1px solid #315568; background:#102635; color:#e7f7ff; font:inherit; }
        @media(max-width:520px) { .player-row { grid-template-columns:1fr; gap:6px; } }
        .history-actions { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:12px; }
        @media(max-width:800px) { .menu {display:inline-flex;} .wrap {padding:12px 12px 40px;} }
      </style>
      <div class="wrap">
        <header>
          <button class="menu" type="button" aria-label="Open Home Assistant sidebar">☰</button>
          <div class="brand"><span class="orb" aria-hidden="true">D</span><h1>DECLAN <small>2.0</small></h1></div>
          <button class="refresh" type="button">Check connection</button>
        </header>
        <nav class="tabs" aria-label="Declan management" role="tablist">
          <button role="tab" id="tab-overview" aria-controls="panel-overview" aria-selected="true" data-tab="overview">Overview</button>
          <button role="tab" id="tab-conversations" aria-controls="panel-conversations" aria-selected="false" data-tab="conversations">Conversations</button>
          <button role="tab" id="tab-players" aria-controls="panel-players" aria-selected="false" data-tab="players">Media players</button>
          <button role="tab" id="tab-voices" aria-controls="panel-voices" aria-selected="false" data-tab="voices">Voice profiles</button>
          <button role="tab" id="tab-updates" aria-controls="panel-updates" aria-selected="false" data-tab="updates">Updates</button>
        </nav>
        <section class="card panel" id="panel-overview" role="tabpanel" aria-labelledby="tab-overview">
          <h2>Declan connection</h2>
          <div class="state" role="status" aria-live="polite">Waiting for Home Assistant…</div>
          <p class="detail muted">Checking the Declan backend through Home Assistant.</p>
        </section>
        <section class="card panel" id="panel-conversations" role="tabpanel" aria-labelledby="tab-conversations" hidden>
          <h2>Conversations</h2>
          <form class="chat-form" aria-label="Chat with Declan">
            <label for="native-chat-input">Message</label>
            <div class="chat-controls"><input id="native-chat-input" maxlength="1000" required placeholder="Ask Declan anything" autocomplete="off"><button class="chat-send" type="submit">Send</button></div>
          </form>
          <p class="chat-status muted" role="status" aria-live="polite"></p>
          <div class="chat-replies" aria-label="Current chat"></div>
          <div class="history-actions"><button class="history-refresh" type="button">Refresh history</button><button class="history-more" type="button" hidden>Load older</button></div><p class="history-status muted" role="status" aria-live="polite">Open this tab to load recent conversations. Chat and editing remain in the existing Declan app.</p><div class="history-list" aria-label="Recent conversations"></div>
        </section>
        <section class="card panel" id="panel-players" role="tabpanel" aria-labelledby="tab-players" hidden>
          <h2>Approved media players</h2>
          <p class="muted">Choose which Music Assistant player Declan may use for each Home Assistant area. Save to apply changes.</p>
          <div class="history-actions"><button type="button" class="players-refresh">Refresh players</button><button type="button" class="players-save" disabled>Save mappings</button></div>
          <p class="players-status muted" role="status" aria-live="polite">Open this tab to load areas and players.</p>
          <div class="players-list"></div>
        </section>
        <section class="card panel" id="panel-voices" role="tabpanel" aria-labelledby="tab-voices" hidden>
          <h2>Voice profiles</h2>
          <p class="muted">Review pending recordings: confirm the suggested speaker, choose another enrolled speaker, or reject a bad recording. Audio playback remains in the existing Declan app.</p>
          <button class="voices-refresh" type="button">Refresh voice profiles</button>
          <p class="voices-status muted" role="status" aria-live="polite">Open this tab to load profiles.</p>
          <div class="voices-list"></div>
        </section>
        <section class="card panel" id="panel-updates" role="tabpanel" aria-labelledby="tab-updates" hidden>
          <h2>Updates</h2><p class="muted">Use the existing Declan updater for now. The native panel will not initiate installs until authenticated update operations and recovery are verified.</p>
        </section>
      </div>`;
    this.shadowRoot.querySelector('.refresh').addEventListener('click', () => this.refresh());
    this.shadowRoot.querySelector('.chat-form').addEventListener('submit', event => {
      event.preventDefault();
      void this.sendChat();
    });
    this.shadowRoot.querySelector('.voices-refresh').addEventListener('click', () => this.loadVoices());
    this.shadowRoot.querySelector('.players-refresh').addEventListener('click', () => this.loadPlayers());
    this.shadowRoot.querySelector('.players-save').addEventListener('click', () => this.savePlayers());
    this.shadowRoot.querySelector('.history-refresh').addEventListener('click', () => this.loadHistory());
    this.shadowRoot.querySelector('.history-more').addEventListener('click', () => this.loadHistory(this._historyCursor));
    this.shadowRoot.querySelectorAll('[data-tab]').forEach(tab => {
      tab.addEventListener('click', () => this.selectTab(tab.dataset.tab));
      tab.addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        const tabs = [...this.shadowRoot.querySelectorAll('[data-tab]')];
        const index = tabs.indexOf(tab);
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1
          : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
        this.selectTab(tabs[next].dataset.tab);
        tabs[next].focus();
      });
    });
    this.shadowRoot.querySelector('.menu').addEventListener('click', () => {
      this.dispatchEvent(new Event('hass-toggle-menu', {bubbles:true, composed:true}));
    });
  }


  selectTab(name) {
    this.shadowRoot.querySelectorAll('[data-tab]').forEach(tab => {
      const active = tab.dataset.tab === name;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    this.shadowRoot.querySelectorAll('.panel').forEach(panel => {
      panel.hidden = panel.id !== 'panel-' + name;
    });
    if (name === 'conversations' && !this._historyLoaded) void this.loadHistory();
    if (name === 'players' && !this._playersLoaded) void this.loadPlayers();
    if (name === 'voices' && !this._voicesLoaded) void this.loadVoices();
  }

  set hass(value) {
    this._hass = value;
    if (!this._loaded && value) {
      this._loaded = true;
      void this.refresh();
    }
  }





  async resolveVoice(interactionId, action, assignedTo) {
    if (this._voicesPending || !this._hass || !window.confirm(
      action === 'dismiss' ? 'Reject this recording?' : 'Apply this speaker match to VoicePipeline?'
    )) return;
    this._voicesPending = true;
    const status = this.shadowRoot.querySelector('.voices-status');
    status.textContent = 'Submitting voice review…';
    try {
      const result = await this._hass.callApi('POST', 'declan_two/voice-review', {
        operation: 'resolve', interaction_id: interactionId, action,
        assigned_to: assignedTo, confirm: true
      });
      if (!result || result.saved !== true) throw new Error('Not confirmed');
      status.textContent = 'Review saved.';
    } catch {
      status.textContent = 'Could not confirm the review. Refresh before retrying to avoid duplicate actions.';
    } finally {
      this._voicesPending = false;
      await this.loadVoices();
    }
  }

  async loadVoices() {
    if (this._voicesPending || !this._hass || typeof this._hass.callApi !== 'function') return;
    this._voicesPending = true;
    const status = this.shadowRoot.querySelector('.voices-status');
    const list = this.shadowRoot.querySelector('.voices-list');
    status.textContent = 'Loading VoicePipeline profiles…';
    try {
      const data = await this._hass.callApi('GET', 'declan_two/voice-review');
      if (!data || !Array.isArray(data.profiles) || !Array.isArray(data.interactions)) throw new Error('Invalid response');
      list.replaceChildren();
      const heading = document.createElement('h3');
      heading.textContent = 'Enrolled speakers';
      list.append(heading);
      for (const profile of data.profiles) {
        const card = document.createElement('article');
        card.className = 'turn';
        const name = document.createElement('strong');
        name.textContent = profile.name || 'Unnamed speaker';
        const details = document.createElement('p');
        const avg = Number.isFinite(profile.avg_confidence) ? (profile.avg_confidence * 100).toFixed(1) + '%' : 'Not available';
        details.textContent = 'Average confidence: ' + avg + ' · Reference clips: ' + (profile.reference_clip_count ?? 'Unknown') + ' · Interactions: ' + (profile.interaction_count ?? 'Unknown');
        card.append(name, details);
        list.append(card);
      }
      if (!data.profiles.length) {
        const empty = document.createElement('p');
        empty.textContent = 'No enrolled speakers found.';
        list.append(empty);
      }
      const pending = document.createElement('h3');
      pending.textContent = 'Pending recordings (' + data.interactions.length + ')';
      list.append(pending);
      for (const interaction of data.interactions) {
        const card = document.createElement('article');
        card.className = 'turn';
        const transcript = document.createElement('p');
        transcript.textContent = interaction.transcript || '(No transcript)';
        const detail = document.createElement('p');
        detail.className = 'muted';
        detail.textContent = 'Suggested: ' + (interaction.matched_speaker || 'Unknown') + ' · Match: ' +
          (Number.isFinite(interaction.match_confidence) ? (interaction.match_confidence * 100).toFixed(1) + '%' : 'Unknown');
        const actions = document.createElement('div');
        actions.className = 'history-actions';
        if (interaction.id) {
          const confirm = document.createElement('button');
          confirm.type = 'button';
          confirm.textContent = 'Confirm match';
          confirm.disabled = !interaction.matched_speaker;
          confirm.addEventListener('click', () => this.resolveVoice(interaction.id, 'confirm', interaction.matched_speaker));
          actions.append(confirm);
          const select = document.createElement('select');
          select.setAttribute('aria-label', 'Choose correct speaker');
          const placeholder = document.createElement('option');
          placeholder.value = '';
          placeholder.textContent = 'Other speaker…';
          select.append(placeholder);
          for (const profile of data.profiles) {
            if (!profile.name) continue;
            const option = document.createElement('option');
            option.value = profile.name;
            option.textContent = profile.name;
            select.append(option);
          }
          actions.append(select);
          const assign = document.createElement('button');
          assign.type = 'button';
          assign.textContent = 'Use selected speaker';
          assign.addEventListener('click', () => {
            if (select.value) void this.resolveVoice(interaction.id, 'assign', select.value);
          });
          actions.append(assign);
          const dismiss = document.createElement('button');
          dismiss.type = 'button';
          dismiss.textContent = 'Reject recording';
          dismiss.addEventListener('click', () => this.resolveVoice(interaction.id, 'dismiss', null));
          actions.append(dismiss);
        }
        card.append(transcript, detail, actions);
        list.append(card);
      }
      this._voicesLoaded = true;
      status.textContent = 'VoicePipeline matches loaded. Confirm, reassign or reject pending recordings.';
    } catch {
      status.textContent = 'Could not load VoicePipeline data. Check the backend connection and HA admin permissions.';
    } finally {
      this._voicesPending = false;
    }
  }

  async loadPlayers() {
    if (this._playersPending || !this._hass || typeof this._hass.callApi !== 'function') return;
    this._playersPending = true;
    const status = this.shadowRoot.querySelector('.players-status');
    const list = this.shadowRoot.querySelector('.players-list');
    const save = this.shadowRoot.querySelector('.players-save');
    save.disabled = true;
    status.textContent = 'Loading Home Assistant areas and Music Assistant players…';
    try {
      const data = await this._hass.callApi('GET', 'declan_two/media-players');
      if (!data || !Array.isArray(data.rooms) || !Array.isArray(data.players) || !data.selected) throw new Error('Invalid player response');
      list.replaceChildren();
      for (const room of data.rooms) {
        const row = document.createElement('div');
        row.className = 'player-row';
        const label = document.createElement('label');
        const select = document.createElement('select');
        const id = 'player-' + data.rooms.indexOf(room);
        select.id = id;
        select.dataset.room = room;
        label.htmlFor = id;
        label.textContent = room === 'everywhere' ? 'Everywhere' : room;
        const empty = document.createElement('option');
        empty.value = '';
        empty.textContent = 'No approved player';
        select.append(empty);
        for (const player of data.players) {
          const option = document.createElement('option');
          option.value = player.entity_id;
          option.textContent = player.name + (player.area ? ' (' + player.area + ')' : '') + (player.state === 'unavailable' ? ' · Unavailable' : '');
          select.append(option);
        }
        select.value = data.selected[room] || '';
        select.addEventListener('change', () => { save.disabled = false; status.textContent = 'Unsaved changes'; });
        row.append(label, select);
        list.append(row);
      }
      this._playersLoaded = true;
      status.textContent = data.configured ? 'Current approved player mappings loaded.' : 'No mappings saved yet. Select players and save.';
    } catch {
      status.textContent = 'Could not load player mappings. Check the Declan backend and HA admin permissions.';
    } finally {
      this._playersPending = false;
    }
  }

  async savePlayers() {
    if (this._playersPending || !this._hass || typeof this._hass.callApi !== 'function') return;
    this._playersPending = true;
    const status = this.shadowRoot.querySelector('.players-status');
    const save = this.shadowRoot.querySelector('.players-save');
    save.disabled = true;
    const rooms = {};
    this.shadowRoot.querySelectorAll('.player-row select').forEach(select => {
      if (select.value) rooms[select.dataset.room] = select.value;
    });
    status.textContent = 'Saving approved players…';
    try {
      const data = await this._hass.callApi('POST', 'declan_two/media-players', {rooms});
      if (!data || !data.configured) throw new Error('Save not confirmed');
      status.textContent = 'Approved player mappings saved.';
    } catch {
      status.textContent = 'Save failed. Your changes may not have been applied. Refresh to verify.';
      save.disabled = false;
    } finally {
      this._playersPending = false;
    }
  }

  async sendChat() {
    if (this._chatPending || !this._hass || typeof this._hass.callApi !== 'function') return;
    const input = this.shadowRoot.querySelector('#native-chat-input');
    const status = this.shadowRoot.querySelector('.chat-status');
    const send = this.shadowRoot.querySelector('.chat-send');
    const message = input.value.trim();
    if (!message || message.length > 1000) return;
    this._chatPending = true;
    send.disabled = true;
    status.textContent = 'Waiting for Declan…';
    try {
      const result = await this._hass.callApi('POST', 'declan_two/chat', {
        message, session_id: this._chatSession || null
      });
      if (!result || typeof result.reply !== 'string') throw new Error('Invalid reply');
      if (typeof result.session_id === 'string') this._chatSession = result.session_id;
      const article = document.createElement('article');
      article.className = 'turn';
      const question = document.createElement('p');
      question.textContent = message;
      const reply = document.createElement('p');
      reply.className = 'reply';
      reply.textContent = result.reply || '(No spoken reply)';
      article.append(question, reply);
      this.shadowRoot.querySelector('.chat-replies').prepend(article);
      input.value = '';
      status.textContent = 'Reply received.';
    } catch {
      status.textContent = 'Unable to send message. Check the Declan connection and try again.';
    } finally {
      this._chatPending = false;
      send.disabled = false;
    }
  }

  async loadHistory(before = null) {
    if (this._historyPending || !this._hass || typeof this._hass.callApi !== 'function') return;
    this._historyPending = true;
    const status = this.shadowRoot.querySelector('.history-status');
    const list = this.shadowRoot.querySelector('.history-list');
    const more = this.shadowRoot.querySelector('.history-more');
    status.textContent = 'Loading conversations…';
    try {
      const path = 'declan_two/history' + (before ? '?before=' + encodeURIComponent(before) : '');
      const result = await this._hass.callApi('GET', path);
      if (!result || !Array.isArray(result.turns)) throw new Error('Invalid history response');
      if (!before) list.replaceChildren();
      for (const turn of result.turns) {
        const article = document.createElement('article');
        article.className = 'turn';
        const message = document.createElement('p');
        message.textContent = turn.message || '';
        const reply = document.createElement('p');
        reply.className = 'reply';
        reply.textContent = turn.reply || '';
        article.append(message, reply);
        list.append(article);
      }
      this._historyLoaded = true;
      this._historyCursor = Number.isSafeInteger(result.next) && result.next > 0 ? result.next : null;
      more.hidden = !this._historyCursor;
      status.textContent = list.children.length
        ? 'Conversation history (read-only)' : 'No conversations found.';
    } catch {
      status.textContent = 'Unable to load conversation history. Check your HA admin permissions and Declan connection.';
    } finally {
      this._historyPending = false;
    }
  }

  async refresh() {
    if (this._pending) return;
    const state = this.shadowRoot.querySelector('.state');
    const detail = this.shadowRoot.querySelector('.detail');
    if (!this._hass || typeof this._hass.callApi !== 'function') {
      state.textContent = 'Waiting for Home Assistant…';
      return;
    }
    this._pending = true;
    state.textContent = 'Checking Declan API…';
    detail.textContent = 'Connecting through Home Assistant.';
    try {
      const result = await this._hass.callApi('GET', 'declan_two/capabilities');
      if (result && result.compatible === true && result.status === 'connected') {
        state.textContent = 'Declan API connected';
        detail.textContent = result.server_version ? 'Backend version: ' + result.server_version : 'Backend connected';
      } else {
        state.textContent = 'Declan API incompatible';
        detail.textContent = 'The backend API version is not supported by this integration.';
      }
    } catch (error) {
      state.textContent = 'Declan API unavailable';
      detail.textContent = 'Check the Declan integration and backend connection.';
    } finally {
      this._pending = false;
    }
  }
}
if (!customElements.get('declan-two-native-panel')) {
  customElements.define('declan-two-native-panel', DeclanTwoNativePanel);
}
