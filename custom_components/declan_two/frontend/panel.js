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
          <h2>Conversations</h2><p class="muted">Conversation history and chat are still available in the existing Declan app while their authenticated native API is developed.</p>
        </section>
        <section class="card panel" id="panel-players" role="tabpanel" aria-labelledby="tab-players" hidden>
          <h2>Approved media players</h2><p class="muted">Room-to-player mappings remain managed by the existing Declan app until the native settings proxy is ready.</p>
        </section>
        <section class="card panel" id="panel-voices" role="tabpanel" aria-labelledby="tab-voices" hidden>
          <h2>Voice profiles</h2><p class="muted">Voice profile review and audio playback remain in the existing Declan app until secure streaming and uploads are available here.</p>
        </section>
        <section class="card panel" id="panel-updates" role="tabpanel" aria-labelledby="tab-updates" hidden>
          <h2>Updates</h2><p class="muted">Use the existing Declan updater for now. The native panel will not initiate installs until authenticated update operations and recovery are verified.</p>
        </section>
      </div>`;
    this.shadowRoot.querySelector('.refresh').addEventListener('click', () => this.refresh());
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
  }

  set hass(value) {
    this._hass = value;
    if (!this._loaded && value) {
      this._loaded = true;
      void this.refresh();
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
