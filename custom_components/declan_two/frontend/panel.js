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
        :host { display:block; min-height:100%; color:var(--primary-text-color, #e7f7ff);
          background:var(--primary-background-color, #101b25); font-family:var(--paper-font-body1_-_font-family, sans-serif); }
        .wrap { max-width:850px; margin:auto; padding:20px 16px 48px; }
        header { display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
        h1 { margin:0; font-size:1.5rem; }
        button { cursor:pointer; border:1px solid var(--divider-color, #466070); border-radius:10px;
          background:var(--card-background-color, #203040); color:inherit; padding:10px 14px; }
        .card { margin-top:18px; padding:20px; border:1px solid var(--divider-color, #466070);
          background:var(--card-background-color, #162630); border-radius:14px; }
        .state { font-weight:600; }
        .muted { opacity:.75; }
        .menu { display:none; }
        @media(max-width:800px) { .menu {display:inline-flex;} .wrap {padding:16px 12px;} }
      </style>
      <div class="wrap">
        <header>
          <button class="menu" type="button" aria-label="Open Home Assistant sidebar">☰</button>
          <h1>Declan 2.0</h1>
          <button class="refresh" type="button">Check connection</button>
        </header>
        <section class="card" role="status" aria-live="polite">
          <div class="state">Waiting for Home Assistant…</div>
          <p class="detail muted">This is a preview of the native management panel. The existing Ingress app is unchanged.</p>
        </section>
      </div>`;
    this.shadowRoot.querySelector('.refresh').addEventListener('click', () => this.refresh());
    this.shadowRoot.querySelector('.menu').addEventListener('click', () => {
      this.dispatchEvent(new Event('hass-toggle-menu', {bubbles:true, composed:true}));
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
