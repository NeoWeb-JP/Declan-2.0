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
        header { display:flex; align-items:center; gap:12px; flex-wrap:wrap; padding:8px 0 16px;
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
        .update-controls { display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin:14px 0; }
        .updates-select { min-width:0; max-width:100%; padding:10px; border:1px solid #315568; border-radius:9px; background:#102635; color:#e7f7ff; font:inherit; }
        @media(max-width:520px) {
          header .refresh { flex:1 1 100%; }
          .update-controls > button, .update-controls > select { flex:1 1 100%; width:100%; }
          .card { padding:16px; }
          .tabs { scroll-padding-inline:12px; }
        }
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
        .timeline-filter,.timeline-speaker { min-width:0; max-width:100%; padding:9px; border:1px solid #315568; border-radius:9px; background:#102635; color:#e7f7ff; font:inherit; }
        .timeline-row { border-top:1px solid #1d3d51; padding:14px 0; overflow-wrap:anywhere; }
        .timeline-row p { margin:6px 0; white-space:pre-wrap; }
        .timeline-row--pending { border-left:3px solid #e6b85c; padding-left:12px; }
        .timeline-row--confirmed { border-left:3px solid #5bbba7; padding-left:12px; }
        .timeline-row--rejected { border-left:3px solid #8295a0; padding-left:12px; }
        .timeline-status-label { display:inline-flex; align-items:center; border-radius:6px; padding:3px 8px; font-size:.8rem; font-weight:700; letter-spacing:.01em; }
        .timeline-status-label--pending { color:#ffe0a0; background:#624719; }
        .timeline-status-label--confirmed { color:#b5f5e4; background:#164d44; }
        .timeline-status-label--rejected { color:#e0e7ed; background:#36434b; }
        .timeline-heading { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:6px; }
        .timeline-heading .muted { font-size:.8rem; }
        .timeline-controls { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-top:8px; }
        .timeline-row details { margin-top:8px; color:#a1ccdf; }
        .timeline-row summary,.timeline-management summary { cursor:pointer; padding:7px 0; }
        .timeline-management { border-top:1px solid #1d3d51; margin-top:16px; }
        .timeline-management-body { padding:12px 0; }
        @media(max-width:520px) { .timeline-controls button { padding:8px 10px; } }
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
          <button role="tab" id="tab-conversations" aria-controls="panel-conversations" aria-selected="false" data-tab="conversations">Conversations &amp; Voice</button>
          <button role="tab" id="tab-players" aria-controls="panel-players" aria-selected="false" data-tab="players">Media players</button>
          <button role="tab" id="tab-updates" aria-controls="panel-updates" aria-selected="false" data-tab="updates">Updates</button>
        </nav>
        <section class="card panel" id="panel-overview" role="tabpanel" aria-labelledby="tab-overview">
          <h2>Declan connection</h2>
          <div class="state" role="status" aria-live="polite">Waiting for Home Assistant…</div>
          <p class="detail muted">Checking the Declan backend through Home Assistant.</p>
        </section>
        <section class="card panel" id="panel-conversations" role="tabpanel" aria-labelledby="tab-conversations" hidden>
          <h2>Conversations &amp; Voice</h2>
          <form class="chat-form" aria-label="Chat with Declan">
            <label for="native-chat-input">Message</label>
            <div class="chat-controls"><input id="native-chat-input" maxlength="1000" required placeholder="Ask Declan anything" autocomplete="off"><button class="chat-send" type="submit">Send</button></div>
          </form>
          <p class="chat-status muted" role="status" aria-live="polite"></p>
          <div class="chat-replies" aria-label="Current chat"></div>
          <div class="history-actions"><button class="timeline-refresh" type="button">Refresh timeline</button><select class="timeline-filter" aria-label="Filter conversations"><option value="all">All</option><option value="pending">Needs review</option><option value="reviewed">Reviewed</option></select></div>
          <p class="timeline-status muted" role="status" aria-live="polite">Open Conversations & Voice to load activity.</p>
          <div class="timeline-list" aria-label="Voice and conversation timeline"></div>
          <details class="timeline-management"><summary>Speaker profiles and older conversation history</summary><div class="timeline-management-body">
          <button class="voices-refresh" type="button">Refresh voice profiles</button><p class="voices-status muted" role="status" aria-live="polite"></p><div class="voices-list"></div>
          <button class="voices-history-refresh" type="button">Refresh reviewed recordings</button><p class="voices-history-status muted" role="status" aria-live="polite"></p><div class="voices-history-list" aria-label="Reviewed voice recordings"></div>
          <div class="history-actions"><button class="history-refresh" type="button">Refresh history</button><button class="history-more" type="button" hidden>Load older</button></div><p class="history-status muted" role="status" aria-live="polite">Open this tab to load recent conversations. Chat and editing remain in the existing Declan app.</p><div class="history-list" aria-label="Recent conversations"></div>
          </div></details>
        </section>
        <section class="card panel" id="panel-players" role="tabpanel" aria-labelledby="tab-players" hidden>
          <h2>Approved media players</h2>
          <p class="muted">Choose which Music Assistant player Declan may use for each Home Assistant area. Save to apply changes.</p>
          <div class="history-actions"><button type="button" class="players-refresh">Refresh players</button><button type="button" class="players-save" disabled>Save mappings</button></div>
          <p class="players-status muted" role="status" aria-live="polite">Open this tab to load areas and players.</p>
          <div class="players-list"></div>
        </section>
        <section class="card panel" id="panel-updates" role="tabpanel" aria-labelledby="tab-updates" hidden>
          <h2>Backend updates</h2>
          <p class="muted">The Declan backend runs on Proxmox. HACS updates this Home Assistant integration separately.</p>
          <p class="update-version muted">Backend version: checking…</p>
          <label><input class="update-prereleases" type="checkbox"> Include prerelease versions</label>
          <div class="update-controls"><button class="updates-check" type="button">Check for updates</button>
          <select class="updates-select" aria-label="Backend release"><option value="">Check for releases first</option></select>
          <button class="updates-install" type="button" disabled>Install selected release</button></div>
          <p class="updates-status muted" role="status" aria-live="polite">Open Updates to check backend status.</p>
          <button class="updates-refresh" type="button">Refresh installation status</button>
        </section>
      </div>`;
    this.shadowRoot.querySelector('.refresh').addEventListener('click', () => this.refresh());
    this.shadowRoot.querySelector('.chat-form').addEventListener('submit', event => {
      event.preventDefault();
      void this.sendChat();
    });
    this.shadowRoot.querySelector('.timeline-refresh').addEventListener('click', () => this.loadTimeline());
    this.shadowRoot.querySelector('.timeline-filter').addEventListener('change', () => this.renderTimeline());
    this.shadowRoot.querySelector('.voices-refresh').addEventListener('click', () => this.loadVoices());
    this.shadowRoot.querySelector('.voices-history-refresh').addEventListener('click', () => this.loadVoiceHistory());
    this.shadowRoot.querySelector('.players-refresh').addEventListener('click', () => this.loadPlayers());
    this.shadowRoot.querySelector('.players-save').addEventListener('click', () => this.savePlayers());
    this.shadowRoot.querySelector('.updates-check').addEventListener('click', () => this.checkUpdates());
    this.shadowRoot.querySelector('.updates-install').addEventListener('click', () => this.installUpdate());
    this.shadowRoot.querySelector('.updates-refresh').addEventListener('click', () => this.loadUpdateStatus());
    this.shadowRoot.querySelector('.update-prereleases').addEventListener('change', () => {
      this.shadowRoot.querySelector('.updates-select').replaceChildren(new Option('Check for releases first', ''));
      this.shadowRoot.querySelector('.updates-install').disabled = true;
    });
    this.shadowRoot.querySelector('.updates-select').addEventListener('change', () => {
      this.shadowRoot.querySelector('.updates-install').disabled = !this.shadowRoot.querySelector('.updates-select').value;
    });
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


  connectedCallback() {
    // Apply the same tab visibility state on initial mount as on user navigation.
    // HA may attach the panel before the hass setter supplies backend state.
    const selected = this.shadowRoot.querySelector('[data-tab][aria-selected="true"]');
    this.selectTab(selected?.dataset.tab || 'overview');
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
    if (name === 'conversations' && !this._timelineLoaded) void this.loadTimeline();
    if (name === 'players' && !this._playersLoaded) void this.loadPlayers();
    if (name === 'updates') void this.loadUpdateStatus();

  }

  async loadUpdateStatus() {
    const status = this.shadowRoot.querySelector('.updates-status');
    try {
      const data = await this._hass.callApi('GET', 'declan_two/updates');
      this.shadowRoot.querySelector('.update-version').textContent = 'Backend version: ' + (data.current || 'unknown');
      status.textContent = 'Updater: ' + (data.enabled ? (data.state || 'idle') : 'not enabled') +
        (data.version ? ' (' + data.version + ')' : '') +
        (data.error ? ' — ' + data.error : '');
      this.shadowRoot.querySelector('.updates-install').disabled = !data.enabled ||
        data.state === 'installing' || data.state === 'restarting' ||
        !this.shadowRoot.querySelector('.updates-select').value;
    } catch (error) {
      status.textContent = 'Cannot read backend update status. Check the connection and administrator permissions.';
    }
  }

  async checkUpdates() {
    const status = this.shadowRoot.querySelector('.updates-status');
    const select = this.shadowRoot.querySelector('.updates-select');
    const button = this.shadowRoot.querySelector('.updates-check');
    button.disabled = true;
    select.replaceChildren(new Option('Checking…', ''));
    this.shadowRoot.querySelector('.updates-install').disabled = true;
    try {
      const data = await this._hass.callApi('POST', 'declan_two/updates', {
        operation: 'check', include_prereleases: this.shadowRoot.querySelector('.update-prereleases').checked
      });
      select.replaceChildren(new Option('Select a release', ''));
      for (const version of data.versions || []) select.add(new Option(version, version));
      status.textContent = data.versions?.length ? 'Choose a release to install.' : 'No eligible releases found.';
      this.shadowRoot.querySelector('.update-version').textContent = 'Backend version: ' + (data.current || 'unknown');
    } catch (error) {
      select.replaceChildren(new Option('Check failed', ''));
      status.textContent = 'Release check failed: ' + (error?.message || 'backend unavailable');
    } finally { button.disabled = false; }
  }

  async installUpdate() {
    const select = this.shadowRoot.querySelector('.updates-select');
    const version = select.value;
    if (!version || !window.confirm('Install Declan backend release ' + version +
      '? The backend may restart and automatically roll back if its health check fails.')) return;
    const button = this.shadowRoot.querySelector('.updates-install');
    const status = this.shadowRoot.querySelector('.updates-status');
    button.disabled = true;
    try {
      await this._hass.callApi('POST', 'declan_two/updates', {
        operation: 'install', version,
        include_prereleases: this.shadowRoot.querySelector('.update-prereleases').checked
      });
      status.textContent = 'Installation queued. Use Refresh installation status to check progress.';
    } catch (error) {
      status.textContent = 'Install not queued: ' + (error?.message || 'backend unavailable');
    }
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
    let feedback = 'Review saved.';
    try {
      const result = await this._hass.callApi('POST', 'declan_two/voice-review', {
        operation: 'resolve', interaction_id: interactionId, action,
        assigned_to: assignedTo, confirm: true
      });
      if (!result || result.saved !== true) throw new Error('Not confirmed');
    } catch (error) {
      feedback = error?.message || 'Could not confirm the review. Refresh before retrying.';
    } finally {
      this._voicesPending = false;
      await this.loadVoices();
      status.textContent = feedback;
    }
  }

  async playVoice(interactionId, button, feedbackStatus = null) {
    if (!this._hass || this._voicesPending) return;
    button.disabled = true;
    const status = feedbackStatus || this.shadowRoot.querySelector('.voices-status');
    status.textContent = 'Loading recording…';
    try {
      const result = await this._hass.callApi('POST', 'declan_two/voice-review', {
        operation: 'audio', interaction_id: interactionId
      });
      if (!result || typeof result.audio !== 'string' || !result.audio) throw new Error('No audio returned');
      if (this._voiceAudio) this._voiceAudio.pause();
      const binary = atob(result.audio);
      const bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
      const blob = new Blob([bytes], {type: 'audio/wav'});
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      this._voiceAudio = audio;
      audio.addEventListener('ended', () => URL.revokeObjectURL(url), {once: true});
      audio.addEventListener('error', () => URL.revokeObjectURL(url), {once: true});
      await audio.play();
      status.textContent = 'Playing recording.';
    } catch {
      status.textContent = 'Could not play the recording. Check VoicePipeline availability and browser audio permissions.';
    } finally {
      button.disabled = false;
    }
  }

  async correctVoiceHistory(item, speaker) {
    if (this._voiceHistoryPending || !this._hass || !item.id || !speaker) return;
    if (!window.confirm('Correct this reviewed recording to ' + speaker + '?')) return;
    const status = this.shadowRoot.querySelector('.voices-history-status');
    this._voiceHistoryPending = true;
    status.textContent = 'Saving historical correction…';
    try {
      const result = await this._hass.callApi('POST', 'declan_two/voice-review', {
        operation: 'correct', interaction_id: item.id, assigned_to: speaker,
        expected_resolution_id: item.current_resolution_id || null, confirm: true
      });
      if (!result || result.saved !== true) throw new Error('Save not confirmed');
      this._voiceHistoryPending = false;
      await this.loadVoiceHistory();
      status.textContent = 'Historical speaker correction saved.';
    } catch (error) {
      this._voiceHistoryPending = false;
      status.textContent = 'Correction failed or recording changed. Refresh and retry. ' + (error?.message || '');
    }
  }

  async loadVoiceHistory() {
    if (!this._hass || this._voiceHistoryPending) return;
    this._voiceHistoryPending = true;
    const status = this.shadowRoot.querySelector('.voices-history-status');
    const list = this.shadowRoot.querySelector('.voices-history-list');
    status.textContent = 'Loading reviewed recordings…';
    try {
      const data = await this._hass.callApi('GET', 'declan_two/voice-review?history=1');
      if (!data || !Array.isArray(data.interactions)) throw new Error('Invalid history');
      list.replaceChildren();
      const heading = document.createElement('h3');
      heading.textContent = 'Reviewed recordings';
      list.append(heading);
      for (const item of data.interactions) {
        const card = document.createElement('article');
        card.className = 'turn';
        const transcript = document.createElement('p');
        transcript.textContent = item.transcript || '(No transcript)';
        const detail = document.createElement('p');
        detail.className = 'muted';
        detail.textContent = 'Speaker: ' + (item.current_assigned_to || item.matched_speaker || 'Unassigned') +
          ' · Status: ' + (item.status || 'Unknown') + ' · Recorded: ' + (item.recorded_at || 'Unknown');
        card.append(transcript, detail);
        if (item.id) {
          const playback = document.createElement('button');
          playback.type = 'button';
          playback.textContent = 'Play recording';
          playback.setAttribute('aria-label', 'Play reviewed recording');
          playback.addEventListener('click', () => void this.playVoice(item.id, playback, status));
          card.append(playback);
        }
        if (item.id && item.current_resolution_id) {
          const actions = document.createElement('div');
          actions.className = 'history-actions';
          const select = document.createElement('select');
          select.setAttribute('aria-label', 'Correct reviewed speaker');
          const placeholder = document.createElement('option');
          placeholder.value = '';
          placeholder.textContent = 'Choose corrected speaker…';
          select.append(placeholder);
          for (const profile of (this._voiceProfiles || [])) {
            if (!profile.name) continue;
            const option = document.createElement('option');
            option.value = profile.name;
            option.textContent = profile.name;
            select.append(option);
          }
          const correct = document.createElement('button');
          correct.type = 'button';
          correct.textContent = 'Correct speaker';
          correct.disabled = true;
          select.addEventListener('change', () => { correct.disabled = !select.value; });
          correct.addEventListener('click', () => void this.correctVoiceHistory(item, select.value));
          actions.append(select, correct);
          card.append(actions);
        }
        list.append(card);
      }
      status.textContent = data.interactions.length
        ? 'Showing ' + data.interactions.length + ' reviewed recordings (read-only).'
        : 'No reviewed recordings found.';
    } catch {
      status.textContent = 'Could not load reviewed recordings. Check VoicePipeline availability.';
    } finally {
      this._voiceHistoryPending = false;
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
      this._voiceProfiles = data.profiles;
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
          const select = document.createElement('select');
          select.setAttribute('aria-label', 'Choose correct speaker');
          const placeholder = document.createElement('option');
          placeholder.value = '';
          placeholder.textContent = 'Choose a speaker…';
          select.append(placeholder);
          for (const profile of data.profiles) {
            if (!profile.name) continue;
            const option = document.createElement('option');
            option.value = profile.name;
            option.textContent = profile.name;
            select.append(option);
          }
          const suggested = typeof interaction.matched_speaker === 'string'
            ? interaction.matched_speaker.trim() : '';
          const known = suggested && !['unknown', 'unidentified', 'none'].includes(suggested.toLowerCase());
          if (known && [...select.options].some(option => option.value === suggested)) select.value = suggested;
          const confirm = document.createElement('button');
          confirm.type = 'button';
          confirm.textContent = 'Confirm speaker';
          confirm.disabled = !select.value;
          select.addEventListener('change', () => { confirm.disabled = !select.value; });
          confirm.addEventListener('click', () => {
            if (!select.value) return;
            const action = known && select.value === suggested ? 'confirm' : 'assign';
            void this.resolveVoice(interaction.id, action, select.value);
          });
          actions.append(select, confirm);
          const enrol = document.createElement('button');
          enrol.type = 'button';
          enrol.textContent = 'Enrol new speaker';
          enrol.addEventListener('click', () => {
            const name = window.prompt('Name for the new speaker:');
            if (name === null) return;
            const trimmed = name.trim();
            if (!/^[\p{L}][\p{L}\p{N}_ '\u2019-]{0,39}$/u.test(trimmed)) {
              this.shadowRoot.querySelector('.voices-status').textContent = 'Enter a valid speaker name of 1–40 characters.';
              return;
            }
            if (data.profiles.some(profile => profile.name.toLocaleLowerCase() === trimmed.toLocaleLowerCase())) {
              this.shadowRoot.querySelector('.voices-status').textContent = 'Speaker already enrolled. Select their existing profile.';
              return;
            }
            void this.resolveVoice(interaction.id, 'enrol', trimmed);
          });
          actions.append(enrol);
          const play = document.createElement('button');
          play.type = 'button';
          play.textContent = 'Play recording';
          play.addEventListener('click', () => void this.playVoice(interaction.id, play));
          actions.append(play);
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
      if (!this._voiceHistoryLoaded) { this._voiceHistoryLoaded = true; void this.loadVoiceHistory(); }
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

  async loadTimeline() {
    if (!this._hass || this._timelinePending) return;
    this._timelinePending = true;
    const status = this.shadowRoot.querySelector('.timeline-status');
    status.textContent = 'Loading conversations and recordings…';
    try {
      const [pending, reviewed, conversations] = await Promise.allSettled([
        this._hass.callApi('GET', 'declan_two/voice-review'),
        this._hass.callApi('GET', 'declan_two/voice-review?history=1'),
        this._hass.callApi('GET', 'declan_two/history')
      ]);
      if (pending.status !== 'fulfilled' && reviewed.status !== 'fulfilled' && conversations.status !== 'fulfilled') {
        throw new Error('No activity source available');
      }
      this._voiceProfiles = pending.status === 'fulfilled' && Array.isArray(pending.value.profiles) ? pending.value.profiles : [];
      const pendingRows = pending.status === 'fulfilled' && Array.isArray(pending.value.interactions) ? pending.value.interactions : [];
      const reviewedRows = reviewed.status === 'fulfilled' && Array.isArray(reviewed.value.interactions) ? reviewed.value.interactions : [];
      const conversationRows = conversations.status === 'fulfilled' && Array.isArray(conversations.value.turns) ? conversations.value.turns : [];
      // These sources have no verified shared interaction ID. Never join by transcript or timestamp.
      // Pending and reviewed endpoints can briefly overlap while a review is being saved.
      // Prefer the reviewed state for the same recording ID, and retain its timeline position.
      const recordings = new Map();
      for (const item of pendingRows) {
        if (item.id) recordings.set(item.id, {kind:'pending', item});
      }
      for (const item of reviewedRows) {
        if (item.id) recordings.set(item.id, {kind:'reviewed', item});
      }
      const recordingRows = [...recordings.values()].sort((a, b) => {
        const aTime = Date.parse(a.item.recorded_at || '');
        const bTime = Date.parse(b.item.recorded_at || '');
        if (Number.isFinite(aTime) && Number.isFinite(bTime)) return bTime - aTime;
        if (Number.isFinite(aTime)) return -1;
        if (Number.isFinite(bTime)) return 1;
        return 0;
      });
      // Conversation history lacks a verified timestamp/shared ID: display separately
      // rather than inventing a chronological position or matching by transcript.
      this._timelineRows = [
        ...recordingRows,
        ...conversationRows.map(item => ({kind:'conversation', item}))
      ];
      this._timelineLoaded = true;
      this.renderTimeline();
      const missing = [pending, reviewed, conversations].filter(result => result.status !== 'fulfilled').length;
      status.textContent = this._timelineRows.length + ' activity entries' +
        (missing ? ' · ' + missing + ' source(s) unavailable. Some entries may be missing.' : ' · Voice recordings and chat history shown separately until a verified link is available.');
    } catch (error) {
      status.textContent = 'Could not load the timeline. Check the Declan connection and HA permissions.';
    } finally {
      this._timelinePending = false;
    }
  }

  renderTimeline() {
    const list = this.shadowRoot.querySelector('.timeline-list');
    const filter = this.shadowRoot.querySelector('.timeline-filter').value;
    list.replaceChildren();
    const rows = (this._timelineRows || []).filter(row =>
      filter === 'all' || (filter === 'pending' && row.kind === 'pending') ||
      (filter === 'reviewed' && row.kind === 'reviewed'));
    for (const row of rows) {
      const {item,kind} = row;
      const card = document.createElement('article');
      card.className = 'timeline-row';
      if (kind !== 'conversation') {
        const rawStatus = String(item.status || '').toLowerCase();
        const rejected = kind === 'reviewed' && /dismiss|reject|discard/.test(rawStatus);
        const reviewState = kind === 'pending' ? 'pending' : rejected ? 'rejected' : 'confirmed';
        card.classList.add('timeline-row--' + reviewState);
        const heading = document.createElement('div');
        heading.className = 'timeline-heading';
        const state = document.createElement('span');
        state.className = 'timeline-status-label timeline-status-label--' + reviewState;
        state.textContent = reviewState === 'pending' ? 'Needs review' : reviewState === 'rejected' ? 'Rejected' : 'Confirmed';
        heading.append(state);
        if (item.recorded_at) {
          const time = document.createElement('span');
          time.className = 'muted';
          const parsed = Date.parse(item.recorded_at);
          time.textContent = Number.isFinite(parsed) ? new Date(parsed).toLocaleString() : item.recorded_at;
          heading.append(time);
        }
        card.append(heading);
      }
      const transcript = document.createElement('p');
      transcript.textContent = item.transcript || item.message || '(No transcript)';
      card.append(transcript);
      const controls = document.createElement('div');
      controls.className = 'timeline-controls';
      if (kind === 'conversation') {
        const label = document.createElement('span');
        label.className = 'muted';
        label.textContent = 'Conversation · Speaker not linked';
        controls.append(label);
        if (item.reply) {
          const reply = document.createElement('p');
          reply.className = 'reply';
          reply.textContent = 'Declan: ' + item.reply;
          card.append(reply);
        }
      } else {
        const speaker = item.current_assigned_to || item.matched_speaker || '';
        const select = document.createElement('select');
        select.className = 'timeline-speaker';
        select.setAttribute('aria-label', 'Speaker for recording');
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = 'Unknown speaker';
        select.append(placeholder);
        for (const profile of this._voiceProfiles) {
          if (!profile.name) continue;
          const option = document.createElement('option');
          option.value = profile.name;
          option.textContent = profile.name;
          select.append(option);
        }
        if ([...select.options].some(option => option.value === speaker)) select.value = speaker;
        controls.append(select);
        const confidence = document.createElement('span');
        confidence.className = 'muted';
        confidence.textContent = Number.isFinite(item.match_confidence)
          ? (item.match_confidence * 100).toFixed(1) + '% match' : 'Match unavailable';
        controls.append(confidence);
        if (kind === 'pending' && item.id) {
          const enrol = document.createElement('button');
          enrol.type = 'button';
          enrol.textContent = 'Enrol speaker';
          enrol.addEventListener('click', async () => {
            const name = window.prompt('Name for the new speaker:');
            if (name === null) return;
            const trimmed = name.trim();
            if (!/^[\p{L}][\p{L}\p{N}_ '\u2019-]{0,39}$/u.test(trimmed)) {
              this.shadowRoot.querySelector('.timeline-status').textContent = 'Enter a valid speaker name (1–40 characters).';
              return;
            }
            if (this._voiceProfiles.some(profile => profile.name?.toLocaleLowerCase() === trimmed.toLocaleLowerCase())) {
              this.shadowRoot.querySelector('.timeline-status').textContent = 'Speaker already enrolled. Select the existing speaker.';
              return;
            }
            await this.resolveVoice(item.id, 'enrol', trimmed);
            await this.loadTimeline();
          });
          // Enrollment is less frequent, so keep it in the details dropdown.
          const enrolDetails = document.createElement('details');
          const enrolSummary = document.createElement('summary');
          enrolSummary.textContent = 'New speaker';
          enrolDetails.append(enrolSummary, enrol);
          controls.append(enrolDetails);
        }
        const reviewed = kind === 'reviewed';
        const originalSpeaker = item.current_assigned_to || (kind === 'reviewed' ? '' : item.matched_speaker) || '';
        // A reviewed (including dismissed) recording is read-only until explicitly unlocked.
        select.disabled = reviewed;
        const save = document.createElement('button');
        save.type = 'button';
        save.textContent = reviewed ? 'Change speaker' : 'Confirm';
        let editing = false;
        const syncSave = () => {
          save.disabled = reviewed
            ? (editing && (!select.value || select.value === originalSpeaker))
            : !select.value;
          save.textContent = reviewed ? (editing ? 'Save change' : 'Change speaker') : 'Confirm';
        };
        syncSave();
        select.addEventListener('change', syncSave);
        save.addEventListener('click', async () => {
          if (reviewed && !editing) {
            editing = true;
            select.disabled = false;
            syncSave();
            select.focus();
            return;
          }
          if (!select.value) return;
          save.disabled = true;
          if (kind === 'pending') {
            const suggested = item.matched_speaker || '';
            await this.resolveVoice(item.id, select.value === suggested ? 'confirm' : 'assign', select.value);
          } else {
            await this.correctVoiceHistory(item, select.value);
          }
          await this.loadTimeline();
        });
        if (reviewed) {
          const cancel = document.createElement('button');
          cancel.type = 'button';
          cancel.textContent = 'Cancel';
          cancel.hidden = true;
          save.addEventListener('click', () => { cancel.hidden = !editing; });
          cancel.addEventListener('click', () => {
            editing = false;
            select.value = [...select.options].some(option => option.value === originalSpeaker) ? originalSpeaker : '';
            select.disabled = true;
            cancel.hidden = true;
            syncSave();
          });
          controls.append(cancel);
        }
        controls.append(save);
        if (item.id) {
          const play = document.createElement('button');
          play.type = 'button';
          play.textContent = 'Play';
          play.setAttribute('aria-label', 'Play voice recording');
          play.addEventListener('click', () => void this.playVoice(item.id, play, this.shadowRoot.querySelector('.timeline-status')));
          controls.append(play);
        }
        const details = document.createElement('details');
        const summary = document.createElement('summary');
        summary.textContent = 'More details';
        details.append(summary);
        const info = document.createElement('p');
        info.textContent = 'Status: ' + (item.status || kind) +
          ' · Recorded: ' + (item.recorded_at || 'Unknown') +
          ' · Suggested speaker: ' + (item.matched_speaker || 'Unknown');
        details.append(info);
        if (item.id) {
          if (kind === 'pending') {
            const reject = document.createElement('button');
            reject.type = 'button';
            reject.textContent = 'Reject recording';
            reject.addEventListener('click', async () => {
              await this.resolveVoice(item.id, 'dismiss', null);
              await this.loadTimeline();
            });
            details.append(reject);
          }
        }
        card.append(controls, details);
      }
      if (kind === 'conversation') card.append(controls);
      list.append(card);
    }
    if (!rows.length) {
      const empty = document.createElement('p');
      empty.className = 'muted';
      empty.textContent = 'No entries for this filter.';
      list.append(empty);
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
