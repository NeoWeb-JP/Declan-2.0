/* Native Home Assistant panel shell. No direct backend calls or embedded secrets. */
class DeclanTwoNativePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: 'open'});
    this._hass = null;
    this._loaded = false;
    this._pending = false;
    this._updatePoll = null;
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
          .update-controls > button, .update-controls > select { flex:1 1 100%; width:100%; }
        }
        /* Compact mobile-first navigation. Keep styles outside the update-controls media query. */
        header { display:flex; align-items:center; flex-wrap:nowrap; gap:9px; padding:5px 0 7px; border-bottom:0; }
        header .menu { display:grid; place-items:center; flex:0 0 34px; width:34px; height:34px; padding:0; font-size:17px; border-radius:9px; }
        .brand { display:flex; align-items:center; gap:8px; flex:1 1 auto; min-width:0; }
        .brand h1 { font:700 17px ui-monospace,monospace; letter-spacing:.055em; white-space:nowrap; }
        .brand h1 small { font-size:.68em; letter-spacing:0; }
        .declan-mark { display:grid; place-items:center; flex:0 0 28px; width:28px; height:28px; box-shadow:none; }
        .declan-mark svg { display:block; width:20px; height:20px; }
        header .connection-action { display:flex; flex:0 0 32px; align-items:center; justify-content:center; width:32px; height:32px; min-width:32px; padding:0; border:0; border-radius:50%; background:transparent; box-shadow:none; }
        .connection-dot { display:block; flex:0 0 9px; width:9px; height:9px; border-radius:50%; background:#a9b8c3; }
        .connection-action[data-status="connected"] .connection-dot { background:#58d4a2; box-shadow:0 0 7px #58d4a277; }
        .connection-action[data-status="error"] .connection-dot { background:#f0a078; }
        .connection-action-label { display:none; }
        .page-navigation { display:flex; align-items:center; gap:7px; padding:0 0 7px; }
        .page-navigation label { font-size:12px; font-weight:600; color:#a1ccdf; }
        .page-select { flex:1; min-width:0; min-height:34px; height:34px; padding:4px 26px 4px 9px; border:1px solid #315568; border-radius:8px; background:#102635; color:#e7f7ff; font:inherit; font-size:13px; }
        .page-select:focus-visible { outline:2px solid #91e3ff; outline-offset:2px; }
        @media(max-width:380px) { .brand h1 { font-size:15px; } .brand { gap:5px; } }
        .tabs button[aria-selected="true"] { background:#184860; border-color:#76dbff; }
        /* Navigation stays hidden until the settings icon is pressed. */
        .wrap { position:relative; }
        header { position:relative; }
        .page-menu-toggle { display:grid; place-items:center; flex:0 0 34px; width:34px; height:34px; padding:0; border-radius:9px; }
        .page-navigation[hidden] { display:none !important; }
        .page-navigation { position:absolute; right:12px; top:64px; z-index:30; display:grid; gap:4px; width:min(300px,calc(100% - 24px)); padding:8px; background:#102635; border:1px solid #315568; border-radius:12px; box-shadow:0 12px 30px #0009; }
        .page-choice { display:block; width:100%; text-align:left; border:0; background:transparent; padding:11px 12px; }
        .page-choice[aria-current="page"] { background:#184860; color:#eaffff; }
        .card { margin-top:14px; padding:22px; border:1px solid #1d3d51;
          background:#0b1a25; border-radius:14px; }
        .state { font-weight:600; }
        .muted { color:#a1ccdf; }
        .mono { font: .82rem ui-monospace,monospace; }
        .menu { display:none; }
        .panel[hidden] { display:none; }
        .panel h2 { margin:0 0 12px; font-size:1.1rem; }
        /* Overview: voice-first primary workspace, compact secondary connection information. */
        .overview-panel { display:grid; gap:16px; padding:0; border:0; background:transparent; }
        .overview-panel .card { margin-top:0; }
        .overview-chat { padding:24px; border-color:#386b83; background:linear-gradient(160deg,#102a3a,#0b1a25 70%); }
        .overview-chat-intro { display:flex; align-items:center; gap:14px; margin-bottom:22px; }
        .overview-chat-intro h2 { margin:0 0 5px; font-size:1.45rem; }
        .overview-chat-intro p { margin:0; }
        .overview-chat-icon { display:grid; place-items:center; width:50px; height:50px; flex:0 0 50px; border-radius:50%; border:1px solid #4c94b2; background:radial-gradient(circle,#235a75,#0d2636); font-weight:700; font-size:1.3rem; }
        .overview-chat .chat-form label { margin:0 0 8px; color:#c4e5f4; font-weight:600; }
        .overview-chat .chat-controls { margin:0 0 16px; }
        .overview-chat .chat-controls input { min-height:52px; }
        .overview-chat .chat-send { padding-inline:22px; border-color:#65c6e8; background:#19536b; color:#eaffff; font-weight:700; }
        .overview-voice-controls { display:flex; flex-wrap:wrap; gap:10px; }
        .overview-voice-controls button { min-height:48px; }
        .overview-voice-controls .mic-start { background:#194d62; border-color:#58a9c7; font-weight:650; }
        .overview-voice-controls button:disabled { opacity:.5; cursor:not-allowed; }
        .overview-chat .mic-status { font-size:.85rem; margin:12px 0 0; }
        .overview-chat .chat-replies:not(:empty) { border-top:1px solid #28495b; margin-top:18px; padding-top:8px; }
        .overview-connection { padding:18px 22px; background:#0b1a25; }
        .overview-connection-heading { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
        .overview-connection-heading h2 { margin:0; font-size:1rem; }
        .overview-connection-indicator { width:9px; height:9px; border-radius:50%; background:#6b9aaf; }
        .overview-connection .state { font-size:.95rem; }
        .overview-connection .detail { margin:6px 0 0; font-size:.85rem; }
        @media(max-width:520px) { .overview-chat { padding:18px; } .overview-chat-intro { gap:10px; } .overview-chat-intro h2 { font-size:1.25rem; } .overview-chat .chat-controls { flex-wrap:wrap; } .overview-chat .chat-controls input { flex:1 1 100%; } .overview-chat .chat-send { width:100%; } .overview-voice-controls button { flex:1 1 100%; } .overview-connection { padding:16px 18px; } }
        .turn { padding:14px 0; border-top:1px solid #1d3d51; overflow-wrap:anywhere; }
        .turn p { margin:6px 0; white-space:pre-wrap; }
        .turn .reply { color:#a1ccdf; }
        .chat-controls { display:flex; gap:8px; margin:8px 0 14px; }
        .chat-controls input { flex:1; min-width:0; padding:12px; border-radius:9px; border:1px solid #315568; background:#102635; color:#e7f7ff; font:inherit; }
        .intents-list { display:grid; gap:12px; margin:12px 0 18px; }
        .intent-row { display:grid; gap:8px; padding:12px; border:1px solid #315568; border-radius:9px; }
        .intent-row input { width:100%; min-width:0; padding:12px; border:1px solid #315568; border-radius:9px; background:#102635; color:#e7f7ff; font:inherit; }
        .settings-spotify { margin-top:18px; padding:14px 16px; border:1px solid #1d3d51; border-radius:12px; background:#0e202d; }
        .settings-spotify summary { cursor:pointer; font-weight:600; padding:4px 0; }
        .spotify-form { display:grid; gap:16px; margin-top:18px; }
        .spotify-form label { display:grid; gap:7px; color:#c7e6f3; font-weight:600; }
        .spotify-form input { display:block; width:100%; min-width:0; padding:12px; border:1px solid #315568; border-radius:9px; background:#102635; color:#e7f7ff; font:inherit; font-weight:400; }
        .spotify-form input:focus-visible { outline:2px solid #91e3ff; outline-offset:2px; }
        .spotify-form button { justify-self:start; }
        .spotify-save-status { margin:12px 0 0; overflow-wrap:anywhere; }
        @media(max-width:520px) { .settings-spotify { padding:12px; } .spotify-form button { width:100%; } }
        .chat-form label { display:block; margin-top:14px; }
        .settings-spotify { margin-top:18px; padding:14px 16px; border:1px solid #1d3d51; border-radius:12px; background:#0e202d; }
        .settings-spotify summary { cursor:pointer; font-weight:600; padding:4px 0; }
        .spotify-form { display:grid; gap:16px; margin-top:18px; }
        .spotify-form label { display:grid; gap:7px; color:#c7e6f3; font-weight:600; }
        .spotify-form input { display:block; width:100%; min-width:0; padding:12px; border:1px solid #315568; border-radius:9px; background:#102635; color:#e7f7ff; font:inherit; font-weight:400; }
        .spotify-form input:focus-visible { outline:2px solid #91e3ff; outline-offset:2px; }
        .spotify-form button { justify-self:start; }
        .spotify-save-status { margin:12px 0 0; overflow-wrap:anywhere; }
        @media(max-width:520px) { .settings-spotify { padding:12px; } .spotify-form button { width:100%; } }
        .chat-replies { margin-bottom:18px; }
        .player-row { display:grid; grid-template-columns:minmax(120px,1fr) minmax(160px,2fr); gap:12px; align-items:center; padding:12px 0; border-top:1px solid #1d3d51; }
        .player-row select { width:100%; min-width:0; padding:10px; border-radius:9px; border:1px solid #315568; background:#102635; color:#e7f7ff; font:inherit; }
        @media(max-width:520px) { .player-row { grid-template-columns:1fr; gap:6px; } }
        .history-actions { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:12px; }
        .timeline-filter,.timeline-speaker { min-width:0; max-width:100%; padding:9px; border:1px solid #315568; border-radius:9px; background:#102635; color:#e7f7ff; font:inherit; }
        /* History: distinct section cards, readable collapsed rows, touch-friendly controls. */
        .timeline-subsection { margin:10px 0; padding:10px 12px; border:1px solid #315568; border-radius:10px; }
        .timeline-subsection > summary { cursor:pointer; font-weight:600; color:#c6eaf5; }
        .timeline-subsection > p { overflow-wrap:anywhere; }
        .timeline-list { display:grid; gap:12px; min-width:0; }
        .timeline-group { min-width:0; overflow:hidden; border:1px solid #315568; border-radius:14px; background:#0e2230; }
        .timeline-group[open] { border-color:#47758b; background:#0b1d29; }
        .timeline-group > summary { display:flex; align-items:center; gap:12px; list-style:none; cursor:pointer; padding:16px; font-weight:700; color:#e7f7ff; min-height:56px; }
        .timeline-group > summary::-webkit-details-marker, .timeline-entry > summary::-webkit-details-marker { display:none; }
        .timeline-group > summary::before, .timeline-entry > summary::before { content:''; width:9px; height:9px; flex:0 0 9px; border-right:2px solid #9dc9db; border-bottom:2px solid #9dc9db; transform:rotate(-45deg); transition:transform .15s ease; }
        .timeline-group[open] > summary::before, .timeline-entry[open] > summary::before { transform:rotate(45deg); }
        .timeline-group > summary:focus-visible, .timeline-entry > summary:focus-visible { outline:2px solid #76dbff; outline-offset:-3px; border-radius:12px; }
        .timeline-group > summary .timeline-count { margin-left:auto; padding:4px 10px; border-radius:999px; background:#1c4053; color:#c9eaf8; font-size:.78rem; font-weight:700; }
        .timeline-group[open] > summary { border-bottom:1px solid #28495b; }
        .timeline-group > .timeline-row, .timeline-group > .timeline-entry { margin:10px 12px; }
        .timeline-entry { border:1px solid #29495a; border-radius:10px; background:#102938; overflow:hidden; }
        .timeline-entry > summary { display:flex; align-items:flex-start; gap:12px; padding:13px 14px; cursor:pointer; list-style:none; line-height:1.45; overflow-wrap:anywhere; font-weight:550; }
        .timeline-entry > summary::before { margin-top:5px; }
        .timeline-entry[open] > summary { border-bottom:1px solid #29495a; }
        .timeline-entry > .timeline-row { padding:14px; border:0; }
        .timeline-group > .timeline-row { padding:14px; border-radius:10px; background:#102938; border-top:0; }
        .timeline-group .timeline-controls { gap:10px; }
        .timeline-group .timeline-controls button { min-height:42px; }
        @media(max-width:520px) { .timeline-group > summary { padding:14px; } .timeline-group > .timeline-row, .timeline-group > .timeline-entry { margin:8px; } .timeline-entry > summary { padding:12px; font-size:.94rem; } .timeline-entry > .timeline-row { padding:12px; } }
        .settings-sections { display:grid; gap:14px; margin-top:20px; }
        .settings-section { min-width:0; border:1px solid #315568; border-radius:14px; background:#0e2230; overflow:hidden; }
        .settings-section[open] { border-color:#47758b; }
        .settings-section > summary { display:flex; align-items:center; gap:14px; list-style:none; cursor:pointer; padding:18px; min-height:72px; }
        .settings-section > summary::-webkit-details-marker { display:none; }
        .settings-section > summary::after { content:''; flex:0 0 9px; width:9px; height:9px; border-right:2px solid #9dc9db; border-bottom:2px solid #9dc9db; transform:rotate(-45deg); margin-left:auto; }
        .settings-section[open] > summary::after { transform:rotate(45deg); }
        .settings-section > summary:focus-visible { outline:2px solid #76dbff; outline-offset:-3px; }
        .settings-section-icon { display:grid; place-items:center; flex:0 0 40px; height:40px; border-radius:10px; background:#16394b; color:#9ddcf3; font-size:1.25rem; }
        .settings-section-title { display:grid; gap:4px; min-width:0; font-weight:700; font-size:1rem; color:#e7f7ff; }
        .settings-section-title small { color:#a1ccdf; font-size:.8rem; font-weight:400; line-height:1.35; }
        .settings-section-content { padding:18px; border-top:1px solid #28495b; display:grid; gap:16px; min-width:0; }
        .settings-section-content > p, .settings-subsection > p { margin:0; }
        .settings-section-content > button, .settings-subsection > button { justify-self:start; }
        .settings-subsection { display:grid; gap:12px; min-width:0; }
        .settings-subsection + .settings-subsection { padding-top:20px; border-top:1px solid #28495b; }
        .settings-subsection h3 { margin:0; font-size:1rem; }
        /* Playlist curation follows the native Settings form layout, including iPhone. */
        .settings-section--playlists .settings-section-content { gap:18px; }
        .settings-section--playlists .playlists-help { line-height:1.5; font-size:.9rem; }
        .settings-section--playlists .playlists-toolbar { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:end; gap:12px; margin:0; min-width:0; }
        .settings-section--playlists .playlists-category-field,
        .settings-section--playlists .playlists-add-form label { display:grid; gap:8px; min-width:0; color:#c7e6f3; font-weight:600; }
        .settings-section--playlists select, .settings-section--playlists input {
          display:block; width:100%; min-width:0; min-height:44px; padding:10px 12px;
          border:1px solid #315568; border-radius:9px; background:#102635;
          color:#e7f7ff; font:inherit; font-weight:400; }
        .settings-section--playlists select:focus-visible, .settings-section--playlists input:focus-visible { outline:2px solid #91e3ff; outline-offset:2px; }
        .settings-section--playlists .playlists-refresh { min-height:44px; white-space:normal; }
        .settings-section--playlists .playlists-status { margin:0; font-size:.9rem; line-height:1.4; }
        .settings-section--playlists .playlists-list { display:grid; gap:10px; min-width:0; }
        .settings-section--playlists .playlists-list > p { margin:0; }
        .settings-section--playlists .playlists-list > h3 { margin:12px 0 0; font-size:1rem; }
        .settings-section--playlists .playlists-list .player-row {
          display:flex; flex-wrap:wrap; align-items:center; gap:8px; min-width:0;
          border:1px solid #28495b; border-radius:10px; padding:12px; background:#102635; }
        .settings-section--playlists .playlists-list .player-row > .mono { flex:1 1 100%; min-width:0; overflow-wrap:anywhere; font-size:.86rem; }
        .settings-section--playlists .playlist-entry-title { flex:1 1 100%; min-width:0; font-weight:650; }
        .settings-section--playlists .playlist-entry-link { flex:1 1 100%; color:#9ddcf3; font-size:.85rem; }
        .settings-section--playlists .playlists-list .player-row button { min-height:40px; }
        .settings-section--playlists .playlists-add-form { display:grid; gap:12px; min-width:0; margin:0; padding-top:16px; border-top:1px solid #28495b; }
        .settings-section--playlists .playlists-add-form button { justify-self:start; min-height:44px; }
        @media(max-width:520px) {
          .settings-section--playlists .playlists-toolbar { grid-template-columns:minmax(0,1fr); }
          .settings-section--playlists .playlists-refresh,
          .settings-section--playlists .playlists-add-form button { width:100%; }
          .settings-section--playlists .playlists-list .player-row button { flex:1 1 auto; }
        }
        .settings-section--logs .declan-log-controls { display:flex; gap:10px; flex-wrap:wrap; align-items:end; }
        .settings-section--logs .declan-log-controls label { display:grid; gap:6px; flex:1 1 130px; min-width:0; }
        .settings-section--logs .declan-log-controls select { min-height:44px; width:100%; background:#102635; color:#e7f7ff; border:1px solid #315568; border-radius:9px; padding:8px; font:inherit; }
        .settings-section--logs .declan-log-controls button { min-height:44px; }
        .settings-section--logs .declan-logs-output { max-height:380px; overflow:auto; padding:12px; background:#081924; border:1px solid #315568; border-radius:10px; white-space:pre-wrap; overflow-wrap:anywhere; font-size:.78rem; line-height:1.55; margin:0; }
        @media(max-width:520px) { .settings-section--logs .declan-log-controls button { flex:1 1 100%; } }
        .settings-section pre, .settings-section input { max-width:100%; }
        @media(max-width:520px) { .settings-section > summary { padding:14px; gap:10px; } .settings-section-content { padding:14px; } .settings-section-icon { flex-basis:34px; height:34px; } }
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
      
        /* AI Settings use the same cards, spacing and form controls as other native Settings. */
        .ai-settings-form { display:grid; gap:16px; min-width:0; }
        .ai-settings-form .ai-field { display:grid; gap:7px; min-width:0; color:#c7e6f3; font-weight:600; }
        .ai-settings-form .ai-field input, .ai-settings-form .ai-field select,
        .ai-key-form input { display:block; width:100%; min-width:0; min-height:44px; padding:10px 12px; border:1px solid #315568; border-radius:9px; background:#102635; color:#e7f7ff; font:inherit; font-weight:400; }
        .ai-settings-form input:focus-visible, .ai-settings-form select:focus-visible { outline:2px solid #91e3ff; outline-offset:2px; }
        .ai-settings-form input[type=checkbox] { width:18px; height:18px; flex:0 0 18px; margin:0; accent-color:#64c8e9; }
        .ai-settings-form .ai-toggle, .ai-options label, .ai-domain-grid label { display:flex; align-items:center; gap:10px; min-width:0; line-height:1.45; color:#c7e6f3; }
        .ai-settings-form .ai-toggle { font-weight:650; }
        .ai-domains { min-width:0; margin:0; padding:14px; border:1px solid #315568; border-radius:10px; }
        .ai-domains legend { padding:0 7px; font-weight:650; color:#c7e6f3; }
        .ai-domain-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }
        .ai-options { display:grid; gap:14px; }
        .ai-settings-form > .muted { margin:0; line-height:1.55; font-size:.9rem; }
        .ai-settings-form .ai-save { justify-self:start; min-height:44px; }
        .ai-key-section { margin:0; }
        .ai-key-form { min-width:0; }
        @media(max-width:520px) { .ai-domain-grid { grid-template-columns:1fr; } .ai-settings-form .ai-save { width:100%; } }
</style>
      <div class="wrap">
        <header>
          <button class="menu" type="button" aria-label="Open Home Assistant sidebar">☰</button>
          <div class="brand"><span class="orb declan-mark" aria-hidden="true"><svg viewBox="0 0 48 48" width="32" height="32" fill="none"><path d="M14 8h11c10 0 17 7 17 16s-7 16-17 16H14V8Z" stroke="currentColor" stroke-width="4"/><path d="M21 16h4c5 0 8 3 8 8s-3 8-8 8h-4V16Z" fill="currentColor"/></svg></span><h1>DECLAN <small>2.0</small></h1></div>
          <button class="refresh connection-action" type="button" aria-label="Check Declan connection" title="Check Declan connection"><span class="connection-dot" aria-hidden="true"></span><span class="connection-action-label">Check status</span></button>
          <button class="page-menu-toggle" type="button" aria-label="Open Declan pages" aria-controls="declan-pages" aria-expanded="false" title="Pages and settings"><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2 2-.06-.06A1.7 1.7 0 0 0 15.86 18l-.06.02V21h-3v-.1a1.7 1.7 0 0 0-1.3-1.65 1.7 1.7 0 0 0-1.86.33l-.07.07-2-2 .07-.07A1.7 1.7 0 0 0 7.98 15.7L7.96 15H5v-3h.1a1.7 1.7 0 0 0 1.65-1.3 1.7 1.7 0 0 0-.33-1.86l-.07-.07 2-2 .07.07A1.7 1.7 0 0 0 10.3 7.2L11 7V4h3v.1a1.7 1.7 0 0 0 1.3 1.65 1.7 1.7 0 0 0 1.86-.33l.07-.07 2 2-.07.07A1.7 1.7 0 0 0 18.8 9.3L19 10h2v3h-.1A1.7 1.7 0 0 0 19.4 15Z"/></svg></button>
        </header>
        <nav id="declan-pages" class="page-navigation" aria-label="Declan pages" hidden>
          <button type="button" class="page-choice" data-page="overview">Overview</button>
          <button type="button" class="page-choice" data-page="conversations">History &amp; Voice Recognition</button>
          <button type="button" class="page-choice" data-page="players">Media players</button>
          <button type="button" class="page-choice" data-page="settings">Settings</button>
          <button type="button" class="page-choice" data-page="updates">Updates</button>
        </nav>
        <section class="panel overview-panel" id="panel-overview" role="region" aria-label="Declan page">
          <div class="overview-chat card">
            <div class="overview-chat-intro"><span class="overview-chat-icon" aria-hidden="true">D</span><div><h2 class="overview-chat-heading">Talk to Declan</h2><p class="muted">Ask a question, give a command or start speaking.</p></div></div>
            <form class="chat-form" aria-label="Chat with Declan">
              <label for="native-chat-input">Your message</label>
              <div class="chat-controls"><input id="native-chat-input" maxlength="1000" required placeholder="What can I help with?" autocomplete="off"><button class="chat-send" type="submit">Send</button></div>
            </form>
            <div class="overview-voice-controls"><button class="mic-start" type="button">🎙 Speak to Declan</button><button class="mic-stop" type="button" disabled>Stop and transcribe</button></div>
            <p class="mic-status muted" role="status" aria-live="polite">Voice messages can be up to 20 seconds.</p>
            <p class="chat-status muted" role="status" aria-live="polite"></p>
            <div class="chat-replies" aria-label="Current chat"></div>
          </div>
          <div class="overview-connection card">
            <div class="overview-connection-heading"><h2>Connection status</h2><span class="overview-connection-indicator" aria-hidden="true"></span></div>
            <div class="state" role="status" aria-live="polite">Waiting for Home Assistant…</div>
            <p class="detail muted">Checking the Declan backend through Home Assistant.</p>
          </div>
        </section>
        <section class="card panel" id="panel-conversations" role="region" aria-label="Declan page" hidden>
          <h2>Chat History &amp; Voice Recognition</h2>
          <div class="history-actions"><button class="timeline-refresh" type="button">Refresh recordings</button></div>
          <p class="timeline-status muted" role="status" aria-live="polite">Open History & Voice Recognition to load the last seven days of recordings.</p>
          <div class="timeline-list" aria-label="Voice recording review"></div>
        </section>
        <section class="card panel" id="panel-players" role="region" aria-label="Declan page" hidden>
          <h2>Approved media players</h2>
          <p class="muted">Choose which Music Assistant player Declan may use for each Home Assistant area. Save to apply changes.</p>
          <div class="history-actions"><button type="button" class="players-refresh">Refresh players</button><button type="button" class="players-save" disabled>Save mappings</button></div>
          <p class="players-status muted" role="status" aria-live="polite">Open this tab to load areas and players.</p>
          <div class="players-list"></div>
        </section>
        <section class="card panel" id="panel-settings" role="region" aria-label="Declan page" hidden>
          <h2>Settings</h2>
          <div class="settings-sections">
          <details class="settings-section settings-section--ai">
            <summary><span class="settings-section-icon" aria-hidden="true">✦</span><span class="settings-section-title">AI Intelligence<small>OpenAI fallback, permissions and spending</small></span></summary>
            <div class="settings-section-content">
              <form class="ai-settings-form">
                <label class="ai-toggle"><input type="checkbox" name="enabled"><span>Enable OpenAI fallback</span></label>
                <label class="ai-field"><span>Model</span> <select name="model" required><option value="gpt-5-mini">GPT-5 mini</option><option value="gpt-6-luna">GPT-6 Luna</option></select></label>
                <label class="ai-field"><span>Monthly budget (USD)</span> <input name="monthly_budget_usd" inputmode="decimal" required></label>
                <label class="ai-field"><span>Maximum per request (USD)</span> <input name="request_ceiling_usd" inputmode="decimal" required></label>
                <label class="ai-field"><span>Maximum actions</span> <input name="max_actions" type="number" min="1" max="8" required></label>
                <fieldset class="ai-domains"><legend>AI permitted device categories</legend><div class="ai-domain-grid">
                  <label><input type="checkbox" name="domain_light"> Lights</label>
                  <label><input type="checkbox" name="domain_switch"> Switches</label>
                  <label><input type="checkbox" name="domain_fan"> Fans</label>
                  <label><input type="checkbox" name="domain_cover"> Covers</label>
                </div></fieldset>
                <p class="muted">Sensitive mapped routines use Declan’s existing confirmation flow. AI cannot directly run scripts or garage/gate controls. Ambiguous requests trigger clarification.</p>
                <div class="ai-options"><label><input type="checkbox" name="diagnostics"> Record diagnostics</label>
                <label><input type="checkbox" name="show_proposals"> Show AI proposals in History</label></div>
                <button class="ai-save" type="submit">Save AI settings</button>
              </form>
              <p class="ai-settings-status muted" role="status" aria-live="polite">Open Settings to load AI configuration.</p><p class="ai-usage muted">Monthly usage unavailable.</p>
              <details class="settings-spotify ai-key-section"><summary>Replace OpenAI API key</summary>
                <form class="ai-key-form spotify-form" autocomplete="off">
                  <label>New OpenAI API key <input type="password" name="api_key" autocomplete="new-password" minlength="19" maxlength="260" required></label>
                  <button type="submit">Replace API key</button>
                </form>
                <p class="ai-key-status muted" role="status" aria-live="polite"></p>
              </details>
            </div>
          </details>

            <details class="settings-section settings-section--routines">
              <summary><span class="settings-section-icon" aria-hidden="true">⌘</span><span class="settings-section-title">Home Assistant routines<small>Script mappings, phrases and parameters</small></span></summary>
              <div class="settings-section-content">
                <p class="muted">Scripts are discovered from Home Assistant. Search by name, area or entity ID. Only scripts with custom settings need a saved override. Existing mappings are preserved.</p>
                <label class="settings-subsection" style="display:grid;gap:8px">Find a Home Assistant script
                  <input class="routine-search" type="search" placeholder="Search scripts, areas or entity IDs" style="width:100%;background:#091923;color:#e7f7ff;border:1px solid #315568;border-radius:8px;padding:12px"/>
                </label>
                <p class="routines-discovery-count muted" aria-live="polite"></p>
                <div class="routine-discovery" style="max-height:380px;overflow-y:auto"></div>
                <details class="settings-subsection routine-overrides"><summary>Advanced: existing custom mappings and overrides</summary>
                  <div class="routine-entries"></div>
                </details>
                <div class="history-actions"><button class="routines-add" type="button">Add routine</button><button class="routines-save" type="button">Save routines</button><button class="routines-refresh" type="button">Reload</button></div>
                <p class="routines-status muted" role="status" aria-live="polite"></p>
              </div>
            </details>
            <details class="settings-section settings-section--voice">
              <summary><span class="settings-section-icon" aria-hidden="true">◉</span><span class="settings-section-title">Voice &amp; learning<small>Profiles, reviewed recordings and learned commands</small></span></summary>
              <div class="settings-section-content">
                <div class="settings-subsection"><h3>Voice profiles</h3><p class="muted">Manage speakers and review their recognition records.</p>
                  <button class="voices-refresh" type="button">Refresh voice profiles</button><p class="voices-status muted" role="status" aria-live="polite"></p><div class="voices-list"></div>
                </div>
              </div>
            </details>
            <details class="settings-section">
              <summary><span class="settings-section-icon" aria-hidden="true">♫</span><span class="settings-section-title">Spotify integration<small>Connection status and API credentials</small></span></summary>
              <div class="settings-section-content">
                <p class="muted">Credentials remain saved unless you explicitly replace both values.</p>
                <p class="spotify-status muted" role="status" aria-live="polite">Open Settings to check Spotify configuration.</p>
                <button class="settings-refresh" type="button">Refresh settings status</button>
                <details class="settings-spotify"><summary>Replace Spotify API credentials</summary>
                  <form class="spotify-form" autocomplete="off"><label>Client ID <input class="spotify-client-id" type="text" maxlength="256" required autocomplete="off"></label><label>New client secret <input class="spotify-client-secret" type="password" maxlength="256" required autocomplete="new-password"></label><button type="submit">Replace credentials</button></form>
                  <p class="spotify-save-status muted" role="status" aria-live="polite"></p>
                </details>
              </div>
            </details>
            <details class="settings-section settings-section--playlists">
              <summary><span class="settings-section-icon" aria-hidden="true">♫</span><span class="settings-section-title">Spotify playlists<small>Browse and curate 25 playlists per category</small></span></summary>
              <div class="settings-section-content">
                <p class="muted playlists-help">Discovery refresh is manual only, using Refresh inside each category. Your playlists and liked playlists are protected; disliked playlists stay blocked. Remove takes a playlist out of the current category (discovery may add it again). Delete excludes it from future discovery in this category.</p>
                <p class="playlists-status muted" role="status" aria-live="polite">Expand this section to load your Spotify categories.</p>
                <div class="playlists-list" aria-label="Playlists grouped by category"></div>
              </div>
            </details>
            <details class="settings-section">
              <summary><span class="settings-section-icon" aria-hidden="true">⇩</span><span class="settings-section-title">Backup &amp; recovery<small>Export, restore and preview configuration</small></span></summary>
              <div class="settings-section-content">
                <div class="settings-subsection"><h3>Configuration backup</h3><p class="muted">Download non-secret settings or the previous import recovery snapshot. Spotify secrets are excluded.</p>
                  <div class="history-actions"><button class="settings-export" type="button">Export settings</button><button class="settings-recovery" type="button">Download recovery snapshot</button></div><p class="settings-document-status muted" role="status" aria-live="polite"></p>
                </div>
                <div class="settings-subsection"><h3>Import configuration</h3><p class="muted">Choose a Declan settings JSON export and preview changes before applying. Spotify credentials are never imported.</p>
                  <input class="settings-import-file" type="file" accept=".json,application/json" aria-label="Choose Declan settings file">
                  <div class="history-actions"><button class="settings-import-preview" type="button">Preview import</button><button class="settings-import-apply" type="button" disabled>Apply reviewed import</button></div>
                  <p class="settings-import-status muted" role="status" aria-live="polite"></p><pre class="settings-import-summary mono" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre>
                  <p class="muted">A successful import saves a recovery snapshot of the previous settings.</p>
                </div>
              </div>
            </details>
            <details class="settings-section settings-section--logs">
              <summary><span class="settings-section-icon" aria-hidden="true">≡</span><span class="settings-section-title">Declan logs<small>Recent backend events, Spotify errors and troubleshooting</small></span></summary>
              <div class="settings-section-content">
                <p class="muted">Recent Declan backend messages only. No Home Assistant startup noise. Log entries are kept in memory until the backend restarts.</p>
                <div class="declan-log-controls">
                  <label>Minimum level
                    <select class="declan-log-level"><option value="ALL">All</option><option value="INFO">Info</option><option value="WARNING">Warnings</option><option value="ERROR">Errors</option></select>
                  </label>
                  <button class="declan-logs-refresh" type="button">Refresh logs</button>
                  <button class="declan-logs-copy" type="button">Copy logs</button>
                </div>
                <p class="declan-logs-status muted" role="status" aria-live="polite"></p>
                <pre class="declan-logs-output mono" aria-label="Declan backend log entries"></pre>
              </div>
            </details>
            <details class="settings-section">
              <summary><span class="settings-section-icon" aria-hidden="true">⚙</span><span class="settings-section-title">Diagnostics<small>Connection and troubleshooting information</small></span></summary>
              <div class="settings-section-content"><button class="settings-diagnostics" type="button">Load recent diagnostics</button><button class="settings-diagnostics-copy" type="button">Copy diagnostics</button><p class="settings-diagnostics-status muted" role="status" aria-live="polite"></p><pre class="settings-diagnostics-output mono" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre></div>
            </details>
          </div>
        </section>
        <section class="card panel" id="panel-updates" role="region" aria-label="Declan page" hidden>
          <h2>Backend updates</h2>
          <p class="muted">The Declan backend runs on Proxmox. HACS updates this Home Assistant integration separately.</p>
          <p class="update-version muted">Backend version: checking…</p>
          <p class="integration-version muted">Integration version: checking…</p>
          <label><input class="update-prereleases" type="checkbox"> Include prerelease versions</label>
          <div class="update-controls"><button class="updates-check" type="button">Check for updates</button>
          <select class="updates-select" aria-label="Backend release"><option value="">Check for releases first</option></select>
          <button class="updates-install" type="button" disabled>Install selected release</button></div>
          <p class="updates-status muted" role="status" aria-live="polite">Open Updates to check backend status.</p>
          <p class="updates-recovery muted" hidden></p>
          <button class="updates-refresh" type="button">Refresh installation status</button>
        </section>
      </div>`;
    try {
      this.bindPanelEvent('.refresh', 'click', () => this.refresh());
      this.bindPanelEvent('.mic-start', 'click', () => this.startMicrophone());
      this.bindPanelEvent('.mic-stop', 'click', () => this.stopMicrophone());
      this.bindPanelEvent('.settings-refresh', 'click', () => this.loadSettingsStatus());
      this.bindPanelEvent('.routines-add', 'click', () => this.addRoutineRow());
      this.bindPanelEvent('.routines-save', 'click', () => this.saveRoutines());
      this.bindPanelEvent('.routines-refresh', 'click', () => this.loadRoutines());
      this.bindPanelEvent('.ai-settings-form', 'submit', event => {
        event.preventDefault(); void this.saveAISettings();
      });
      this.bindPanelEvent('.ai-key-form', 'submit', event => {
        event.preventDefault(); void this.saveAIKey();
      });
      this._settingsImportPreview = null;
      this.bindPanelEvent('.settings-import-file', 'change', () => this.resetSettingsImport());
      this.bindPanelEvent('.settings-import-preview', 'click', () => this.previewSettingsImport());
      this.bindPanelEvent('.settings-import-apply', 'click', () => this.applySettingsImport());
      this.bindPanelEvent('.settings-export', 'click', () => this.downloadSettings('export'));
      this.bindPanelEvent('.settings-recovery', 'click', () => this.downloadSettings('recovery'));
      this.bindPanelEvent('.settings-diagnostics', 'click', () => this.loadDiagnostics());
      this.bindPanelEvent('.settings-diagnostics-copy', 'click', () => this.copyDiagnostics());
      this.bindPanelEvent('.declan-logs-refresh', 'click', () => this.loadDeclanLogs());
      this.bindPanelEvent('.declan-log-level', 'change', () => this.renderDeclanLogs());
      this.bindPanelEvent('.declan-logs-copy', 'click', () => this.copyDeclanLogs());
      this.bindPanelEvent('.settings-section--logs', 'toggle', event => { if (event.target.open) void this.loadDeclanLogs(); });
      this.bindPanelEvent('.spotify-form', 'submit', event => {
        event.preventDefault(); void this.replaceSpotifyCredentials();
      });
      this.bindPanelEvent('.chat-form', 'submit', event => {
        event.preventDefault();
        void this.sendChat();
      });
      this.bindPanelEvent('.timeline-refresh', 'click', () => this.loadTimeline());
      this.bindPanelEvent('.voices-refresh', 'click', () => this.loadVoices());

      this.bindPanelEvent('.settings-section--playlists', 'toggle', event => {
        if (event.target.open) void this.loadPlaylists();
      });
      this.bindPanelEvent('.playlists-list', 'click', event => {
        const button = event.target.closest('button');
        if (!button) return;
        const category = button.closest('details[data-playlist-category]')?.dataset.playlistCategory;
        if (!category) return;
        if (button.classList.contains('playlists-refresh')) void this.refreshPlaylists(category);
        else if (button.dataset.playlistOperation)
          void this.updatePlaylist(button.dataset.playlistOperation, button.dataset.playlistUri, category);
      });
      this.bindPanelEvent('.playlists-list', 'submit', event => {
        const form = event.target.closest('form.playlists-add-form');
        if (!form) return;
        event.preventDefault();
        const category = form.closest('details[data-playlist-category]')?.dataset.playlistCategory;
        if (category) void this.updatePlaylist('add', form.querySelector('input').value, category);
      });
      this.bindPanelEvent('.players-refresh', 'click', () => this.loadPlayers());
      this.bindPanelEvent('.players-save', 'click', () => this.savePlayers());
      this.bindPanelEvent('.updates-check', 'click', () => this.checkUpdates());
      this.bindPanelEvent('.updates-install', 'click', () => this.installUpdate());
      this.bindPanelEvent('.updates-refresh', 'click', () => this.loadUpdateStatus());
      this.bindPanelEvent('.update-prereleases', 'change', () => {
        this.shadowRoot.querySelector('.updates-select').replaceChildren(new Option('Check for releases first', ''));
        this.shadowRoot.querySelector('.updates-install').disabled = true;
      });
      this.bindPanelEvent('.updates-select', 'change', () => {
        this.shadowRoot.querySelector('.updates-install').disabled = !this.shadowRoot.querySelector('.updates-select').value;
      });

      this.bindPanelEvent('.history-refresh', 'click', () => this.loadHistory());
      this.bindPanelEvent('.history-more', 'click', () => this.loadHistory(this._historyCursor));
      this.bindPanelEvent('.page-menu-toggle', 'click', () => {
        const nav = this.shadowRoot.querySelector('.page-navigation');
        nav.hidden = !nav.hidden;
        this.shadowRoot.querySelector('.page-menu-toggle').setAttribute('aria-expanded', String(!nav.hidden));
      });
      this.shadowRoot.querySelectorAll('.page-choice').forEach(button => button.addEventListener('click', () => this.selectTab(button.dataset.page)));
      this.shadowRoot.addEventListener('keydown', event => {
        if (event.key === 'Escape') this.closePageMenu();
      });
      this.bindPanelEvent('.menu', 'click', () => {
        this.dispatchEvent(new Event('hass-toggle-menu', {bubbles:true, composed:true}));
      });
    } catch (error) {
      this.showStartupError(error);
    }
  }


  bindPanelEvent(selector, eventName, handler) {
    const element = this.shadowRoot.querySelector(selector);
    if (!element) {
      console.error('[Declan] Missing panel control:', selector);
      return;
    }
    element.addEventListener(eventName, handler);
  }

  showStartupError(error) {
    console.error('[Declan] Panel startup failed:', error);
    const host = this.shadowRoot;
    const message = document.createElement('div');
    message.setAttribute('role', 'alert');
    message.style.cssText = 'margin:16px;padding:16px;border:2px solid #e6b85c;border-radius:12px;background:#302517;color:#fff;white-space:pre-wrap';
    message.textContent = 'Declan panel could not start. Check the browser console for details. ' + String(error?.message || error);
    host.prepend(message);
  }


  connectedCallback() {
    // Apply the same tab visibility state on initial mount as on user navigation.
    // HA may attach the panel before the hass setter supplies backend state.
    try {
      this.selectTab('overview');
    } catch (error) {
      this.showStartupError(error);
    }
  }

  closePageMenu() {
    const nav = this.shadowRoot.querySelector('.page-navigation');
    nav.hidden = true;
    this.shadowRoot.querySelector('.page-menu-toggle').setAttribute('aria-expanded', 'false');
  }

  selectTab(name) {
    this.closePageMenu();
    this.shadowRoot.querySelectorAll('.page-choice').forEach(button => {
      if (button.dataset.page === name) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });
    this.shadowRoot.querySelectorAll('.panel').forEach(panel => {
      panel.hidden = panel.id !== 'panel-' + name;
    });
    if (name === 'conversations' && !this._timelineLoaded) void this.loadTimeline();
    if (name === 'players' && !this._playersLoaded) void this.loadPlayers();
    if (name === 'settings') { void this.loadRoutines(); void this.loadSettingsStatus(); void this.loadAISettings(); if (!this._voicesLoaded) void this.loadVoices(); }
    if (name === 'updates') void this.openUpdatesPage();
    else this.stopUpdatePolling();

  }

  renderScriptDiscovery() {
    const root = this.shadowRoot.querySelector('.routine-discovery');
    const count = this.shadowRoot.querySelector('.routines-discovery-count');
    if (!root || !count) return;
    const scripts = (this._scriptDiscovery || []).map(item => ({
      entity_id: item.entity_id,
      attributes: {friendly_name: item.name, area_id: item.area},
      declanSafe: item.safe,
      declanReason: item.reason
    })).sort((a, b) => (a.attributes?.friendly_name || a.entity_id).localeCompare(b.attributes?.friendly_name || b.entity_id));
    const query = (this.shadowRoot.querySelector('.routine-search')?.value || '').trim().toLowerCase();
    const matches = scripts.filter(entity => {
      const area = entity.attributes?.area_id || '';
      return [entity.entity_id, entity.attributes?.friendly_name || '', area].join(' ').toLowerCase().includes(query);
    });
    const visible = matches.slice(0, 40);
    root.replaceChildren();
    count.textContent = scripts.length + ' scripts discovered · ' + matches.length + ' matching' +
      (matches.length > visible.length ? ' · showing first ' + visible.length + ', refine your search' : '');
    for (const entity of visible) {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 0;border-bottom:1px solid #315568';
      const label = document.createElement('div');
      const title = document.createElement('strong');
      title.textContent = entity.attributes?.friendly_name || entity.entity_id;
      const id = document.createElement('div');
      id.className = 'muted';
      id.textContent = entity.entity_id;
      const safety = document.createElement('div');
      safety.className = 'muted';
      safety.textContent = entity.declanSafe ? 'Voice enabled · inspected safe actions' : 'Protected · approval required';
      label.append(title, id, safety);
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = entity.declanSafe ? 'Customise' : 'Review / enable';
      button.addEventListener('click', () => {
        const key = entity.entity_id.slice(7);
        const existing = [...this.shadowRoot.querySelectorAll('.routine-entry')]
          .find(row => row.querySelector('[data-field="script"]')?.value === entity.entity_id);
        this.shadowRoot.querySelector('.routine-overrides').open = true;
        if (!existing) this.addRoutineRow(key, {script: entity.entity_id, phrases: [key.replaceAll('_', ' ')], fields: {}, sensitive: true});
        this.shadowRoot.querySelector('.routine-overrides').scrollIntoView({block: 'nearest'});
      });
      row.append(label, button);
      root.append(row);
    }
  }

  addRoutineRow(name = '', item = {}) {
    const root = this.shadowRoot.querySelector('.routine-entries');
    const row = document.createElement('div');
    row.className = 'settings-subsection routine-entry';
    row.style.cssText = 'border:1px solid #315568;border-radius:12px;padding:14px;margin-bottom:12px';
    const fields = [
      ['name', 'Routine key', name],
      ['script', 'HA script entity ID', item.script || ''],
      ['remote', 'Optional projector remote entity ID', item.remote || ''],
      ['phrases', 'Trigger phrases (one per line)', (item.phrases || []).join('\n')],
      ['fields', 'Script parameters (JSON object)', JSON.stringify(item.fields || {})]
    ];
    for (const [key, label, value] of fields) {
      const wrapper = document.createElement('label');
      wrapper.textContent = label;
      wrapper.style.cssText = 'display:grid;gap:5px;margin-bottom:12px';
      const input = key === 'phrases' || key === 'fields' ? document.createElement('textarea') : document.createElement('input');
      input.dataset.field = key;
      input.value = value;
      if (key === 'script' || key === 'remote') {
        const datalist = document.createElement('datalist');
        datalist.id = 'routine-scripts-' + Math.random().toString(36).slice(2);
        const scripts = Object.values(this._hass?.states || {}).filter(entity => entity.entity_id?.startsWith(key + '.'));
        for (const entity of scripts) {
          const option = document.createElement('option');
          option.value = entity.entity_id;
          option.label = entity.attributes?.friendly_name || entity.entity_id;
          datalist.append(option);
        }
        input.setAttribute('list', datalist.id);
        wrapper.append(datalist);
      }
      input.style.cssText = 'width:100%;background:#091923;color:#e7f7ff;border:1px solid #315568;border-radius:8px;padding:9px';
      wrapper.append(input);
      row.append(wrapper);
    }
    const label = document.createElement('label');
    label.textContent = 'Require confirmation ';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.dataset.field = 'sensitive';
    checkbox.checked = item.sensitive === true;
    label.append(checkbox);
    row.append(label);
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.textContent = 'Remove';
    remove.addEventListener('click', () => row.remove());
    row.append(remove);
    root.append(row);
  }

  async loadRoutines() {
    const status = this.shadowRoot.querySelector('.routines-status');
    try {
      const result = await this._hass.callApi('GET', 'declan_two/management/routines');
      const root = this.shadowRoot.querySelector('.routine-entries');
      root.replaceChildren();
      for (const [name, item] of Object.entries(result.routines || {})) this.addRoutineRow(name, item);
      try {
        const discovered = await this._hass.callApi('GET', 'declan_two/script-discovery');
        this._scriptDiscovery = discovered.inspection === 'complete' ? discovered.scripts : [];
      } catch {
        this._scriptDiscovery = [];
      }
      this.renderScriptDiscovery();
      status.textContent = this._scriptDiscovery.length
        ? 'Discovered ' + this._scriptDiscovery.length + ' scripts. Existing overrides preserved.'
        : 'Script safety inspection unavailable. Automatic voice execution is disabled.';
    } catch (error) {
      status.textContent = 'Could not load routine mappings: ' + (error?.body?.error || error?.body?.status || error?.message || 'Unknown error');
    }
  }

  async saveRoutines() {
    const status = this.shadowRoot.querySelector('.routines-status');
    try {
      const routines = {};
      for (const row of this.shadowRoot.querySelectorAll('.routine-entry')) {
        const field = key => row.querySelector('[data-field="' + key + '"]');
        const name = field('name').value.trim();
        if (!name) throw new Error('Enter a routine key.');
        if (!field('script').value.trim() && !field('remote').value.trim()) continue;
        const key = name === 'movie_time' ? 'movie' : name === 'good_morning' ? 'morning' : name === 'good_night' ? 'night' : name;
        if (Object.hasOwn(routines, key)) throw new Error('Duplicate routine key: ' + key);
        if (!field('script').value.trim()) throw new Error('Select an HA script for ' + name + '.');
        routines[key] = {
          script: field('script').value.trim(),
          remote: field('remote').value.trim(),
          phrases: field('phrases').value.split('\n').map(x => x.trim().toLowerCase()).filter(Boolean),
          fields: JSON.parse(field('fields').value),
          sensitive: field('sensitive').checked
        };
      }
      const result = await this._hass.callApi('POST', 'declan_two/management/routines', {routines});
      if (!result.saved) throw new Error('Save not confirmed');
      status.textContent = 'Routine mappings saved.';
    } catch (error) {
      const detail = error?.body?.error || error?.body?.status || error?.message || error?.status || 'Unknown error';
      status.textContent = 'Could not save routines: ' + (typeof detail === 'string' ? detail : JSON.stringify(detail));
    }
  }

  async openUpdatesPage() {
    // Read installation state first; do not check releases during an installation.
    await this.loadUpdateStatus();
    if (!this.isConnected || !this.shadowRoot.querySelector('#panel-updates') ||
        this.shadowRoot.querySelector('#panel-updates').hidden) return;
    if (this.shadowRoot.querySelector('.updates-check').disabled) return;
    await this.checkUpdates();
  }

  stopUpdatePolling() {
    if (this._updatePoll !== null) {
      clearTimeout(this._updatePoll);
      this._updatePoll = null;
    }
  }

  disconnectedCallback() {
    this.cancelMicrophone();
    this.stopUpdatePolling();
  }

  scheduleUpdatePoll() {
    this.stopUpdatePolling();
    if (!this.isConnected || !this.shadowRoot.querySelector('#panel-updates') ||
        this.shadowRoot.querySelector('#panel-updates').hidden) return;
    this._updatePoll = setTimeout(() => {
      this._updatePoll = null;
      void this.loadUpdateStatus();
    }, 4000);
  }

  async loadUpdateStatus() {
    const status = this.shadowRoot.querySelector('.updates-status');
    const recovery = this.shadowRoot.querySelector('.updates-recovery');
    this.stopUpdatePolling();
    try {
      const data = await this._hass.callApi('GET', 'declan_two/updates');
      this.shadowRoot.querySelector('.update-version').textContent = 'Backend version: ' + (data.current || 'unknown');
      if (data.integration_version) this.shadowRoot.querySelector('.integration-version').textContent = 'Integration version: ' + data.integration_version;
      const state = data.state || 'idle';
      const labels = {
        idle: 'Ready to check for releases.',
        installing: 'Installing the selected release. Please wait.',
        restarting: 'Restarting Declan and checking its health.',
        failed: 'Installation failed. Check backend logs and confirm the previous release is healthy.'
      };
      status.textContent = data.enabled ? (labels[state] || 'Updater: ' + state) +
        (data.version ? ' (' + data.version + ')' : '') +
        (data.error ? ' — ' + data.error : '') : 'Backend updater is not enabled on this installation.';
      recovery.hidden = state !== 'failed';
      recovery.textContent = state === 'failed' ?
        'The updater may have restored the previous release. Confirm backend health before trying again; do not repeatedly reinstall.' : '';
      this.shadowRoot.querySelector('.updates-check').disabled = !data.enabled ||
        state === 'installing' || state === 'restarting';
      if (state === 'installing' || state === 'restarting') this.scheduleUpdatePoll();
      this.shadowRoot.querySelector('.updates-install').disabled = !data.enabled ||
        data.state === 'installing' || data.state === 'restarting' ||
        !this.shadowRoot.querySelector('.updates-select').value;
    } catch (error) {
      status.textContent = 'Cannot read backend update status. Check the connection and administrator permissions.';
      recovery.hidden = false;
      recovery.textContent = 'The backend may be restarting. Refresh the status after reconnecting; do not assume installation succeeded.';
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
      const versions = Array.isArray(data.versions) ? data.versions.filter(version => typeof version === 'string' && version.trim()) : [];
      select.replaceChildren();
      for (const version of versions) select.add(new Option(version, version));
      if (versions.length) {
        // The updater returns releases newest first; select the first eligible release.
        select.selectedIndex = 0;
        this.shadowRoot.querySelector('.updates-install').disabled = false;
        status.textContent = 'Latest eligible release ' + select.value + ' selected. Ready to install.';
      } else {
        select.add(new Option('No eligible releases', ''));
        this.shadowRoot.querySelector('.updates-install').disabled = true;
        status.textContent = 'No eligible releases found.';
      }
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
      status.textContent = 'Installation queued. Refresh installation status to follow progress.';
      void this.loadUpdateStatus();
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
      this._voicesLoaded = true;
      status.textContent = 'Speaker profiles loaded. Review recordings in History & Voice Recognition.';
    } catch {
      status.textContent = 'Could not load VoicePipeline data. Check the backend connection and HA admin permissions.';
    } finally {
      this._voicesPending = false;
    }
  }

  async refreshPlaylists(category) {
    if (this._playlistsPending || !this._hass || !category) return;
    const status = this.shadowRoot.querySelector('.playlists-status');
    this._playlistsPending = true;
    status.textContent = 'Searching Spotify for ' + category.replace(/_/g, ' ') + ' playlists…';
    try {
      const response = await this._hass.callApi('POST', 'declan_two/music-playlists',
                                                {category, operation: 'refresh'});
      if (!response || !response.categories) throw new Error('Discovery did not start');
      for (let attempt = 0; attempt < 30; attempt++) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        const current = await this._hass.callApi('GET', 'declan_two/music-playlists');
        if (!current || !current.categories) throw new Error('Discovery status unavailable');
        if (!current.refresh?.running) {
          this._playlistCatalogue = current.categories;
          this.renderPlaylists(category);
          status.textContent = current.refresh?.error
            ? 'Spotify search failed for ' + category + '. Existing playlists were kept. ' + current.refresh.error
            : 'Spotify discovery finished for ' + category + ': ' +
              (current.categories[category]?.playlists?.length || 0) + ' of 25 playlists. Other categories preserved.';
          return;
        }
      }
      status.textContent = 'Spotify discovery is still running. Check again shortly.';
    } catch {
      status.textContent = 'Could not refresh ' + category + '. Check the Declan connection.';
    } finally {
      this._playlistsPending = false;
    }
  }

  async loadPlaylists() {
    if (this._playlistsPending || !this._hass || typeof this._hass.callApi !== 'function') return;
    this._playlistsPending = true;
    const status = this.shadowRoot.querySelector('.playlists-status');
    status.textContent = 'Loading playlists from Home Assistant…';
    try {
      const data = await this._hass.callApi('GET', 'declan_two/music-playlists');
      if (!data || !data.categories || typeof data.categories !== 'object') throw new Error('Invalid playlist response');
      this._playlistCatalogue = data.categories;
      this._playlistPreferences = data.preferences || {};
      this.renderPlaylists();
    } catch {
      status.textContent = 'Could not load Spotify playlists. Check the Declan 2.0 connection and try again.';
    } finally {
      this._playlistsPending = false;
    }
  }

  renderPlaylists(openCategory = null) {
    const status = this.shadowRoot.querySelector('.playlists-status');
    const list = this.shadowRoot.querySelector('.playlists-list');
    const catalogue = this._playlistCatalogue || {};
    const previouslyOpen = new Set(Array.from(list.querySelectorAll('details[open][data-playlist-category]'))
      .map(node => node.dataset.playlistCategory));
    if (openCategory) previouslyOpen.add(openCategory);
    list.replaceChildren();
    for (const [category, data] of Object.entries(catalogue)) {
      const playlists = Array.isArray(data.playlists) ? data.playlists : [];
      const details = document.createElement('details');
      details.className = 'settings-subsection playlist-category-accordion';
      details.dataset.playlistCategory = category;
      details.open = previouslyOpen.has(category);
      const summary = document.createElement('summary');
      const label = category.replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase());
      summary.textContent = label + ' (' + playlists.length + '/25)';
      details.append(summary);
      const refresh = document.createElement('button');
      refresh.type = 'button';
      refresh.className = 'playlists-refresh';
      refresh.textContent = 'Refresh ' + label;
      details.append(refresh);
      if (!playlists.length) {
        const empty = document.createElement('p');
        empty.className = 'muted';
        empty.textContent = 'No playlists saved yet.';
        details.append(empty);
      }
      for (const uri of playlists) {
        const row = document.createElement('div');
        row.className = 'player-row';
        const title = document.createElement('span');
        title.className = 'playlist-entry-title';
        title.style.overflowWrap = 'anywhere';
        const name = data.titles?.[uri];
        title.textContent = name || uri;
        row.append(title);
        const plays = document.createElement('span');
        plays.className = 'muted';
        plays.textContent = 'Plays: ' + (this._playlistPreferences?.play_counts?.[uri] || 0);
        row.append(plays);
        const favourite = (this._playlistPreferences?.favourites || []).includes(uri);
        const favouriteButton = document.createElement('button');
        favouriteButton.type = 'button';
        favouriteButton.dataset.playlistOperation = favourite ? 'unfavourite' : 'favourite';
        favouriteButton.dataset.playlistUri = uri;
        favouriteButton.textContent = favourite ? '★ Favourite' : '☆ Favourite';
        favouriteButton.setAttribute('aria-pressed', String(favourite));
        row.append(favouriteButton);
        const dislikeButton = document.createElement('button');
        dislikeButton.type = 'button';
        dislikeButton.dataset.playlistOperation = 'dislike';
        dislikeButton.dataset.playlistUri = uri;
        dislikeButton.textContent = 'Dislike / never play';
        row.append(dislikeButton);
        if (name) {
          const link = document.createElement('a');
          link.href = uri.replace('spotify://playlist/', 'https://open.spotify.com/playlist/');
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          link.className = 'playlist-entry-link';
          link.textContent = 'Open in Spotify';
          row.append(link);
        }
        if ((data.manual || []).includes(uri)) {
          const pinned = document.createElement('span');
          pinned.textContent = 'Your playlist · protected from refresh';
          row.append(pinned);
        } else if (favourite || (data.favourites || []).includes(uri)) {
          const pinned = document.createElement('span');
          pinned.textContent = 'Liked · protected from refresh';
          row.append(pinned);
        }
        for (const [operation, action] of [['remove', 'Remove'], ['delete', 'Delete / exclude']]) {
          const button = document.createElement('button');
          button.type = 'button';
          button.dataset.playlistOperation = operation;
          button.dataset.playlistUri = uri;
          button.textContent = action;
          button.setAttribute('aria-label', action + ' ' + uri);
          row.append(button);
        }
        details.append(row);
      }
      if (Array.isArray(data.excluded) && data.excluded.length) {
        const heading = document.createElement('h3');
        heading.textContent = 'Excluded from discovery';
        details.append(heading);
        for (const uri of data.excluded) {
          const row = document.createElement('div');
          row.className = 'player-row';
          const title = document.createElement('span');
          title.textContent = uri;
          title.style.overflowWrap = 'anywhere';
          const button = document.createElement('button');
          button.type = 'button';
          button.textContent = 'Restore';
          button.dataset.playlistOperation = (this._playlistPreferences?.disliked_playlists || []).includes(uri) ? 'restore' : 'remove';
          button.dataset.playlistUri = uri;
          row.append(title, button);
          details.append(row);
        }
      }
      const form = document.createElement('form');
      form.className = 'playlists-add-form';
      const labelInput = document.createElement('label');
      labelInput.textContent = 'Add your own Spotify playlist (kept during refresh)';
      const input = document.createElement('input');
      input.required = true;
      input.placeholder = 'https://open.spotify.com/playlist/…';
      input.autocomplete = 'off';
      labelInput.append(input);
      const add = document.createElement('button');
      add.type = 'submit';
      add.textContent = 'Add playlist';
      form.append(labelInput, add);
      details.append(form);
      list.append(details);
    }
    const dislikedPlaylists = this._playlistPreferences?.disliked_playlists || [];
    const blockedPlaylists = document.createElement('details');
    blockedPlaylists.className = 'settings-subsection playlist-category-accordion';
    blockedPlaylists.dataset.playlistCategory = 'disliked_playlists';
    blockedPlaylists.open = previouslyOpen.has('disliked_playlists') || openCategory === 'disliked_playlists';
    const blockedHeading = document.createElement('summary');
    blockedHeading.textContent = 'Disliked playlists (' + dislikedPlaylists.length + ')';
    blockedPlaylists.append(blockedHeading);
    for (const uri of dislikedPlaylists) {
      const row = document.createElement('div');
      row.className = 'player-row';
      const label = document.createElement('span');
      label.textContent = uri;
      const restore = document.createElement('button');
      restore.type = 'button';
      restore.textContent = 'Restore playlist';
      restore.dataset.playlistOperation = 'restore';
      restore.dataset.playlistUri = uri;
      row.append(label, restore);
      blockedPlaylists.append(row);
    }
    list.append(blockedPlaylists);
    const dislikedSongs = this._playlistPreferences?.disliked_songs || [];
    const songs = document.createElement('details');
    songs.className = 'settings-subsection playlist-category-accordion';
    songs.dataset.playlistCategory = 'disliked_songs';
    songs.open = previouslyOpen.has('disliked_songs') || openCategory === 'disliked_songs';
    const heading = document.createElement('summary');
    heading.textContent = 'Disliked songs (' + dislikedSongs.length + ')';
    songs.append(heading);
    for (const uri of dislikedSongs) {
      const row = document.createElement('div');
      row.className = 'player-row';
      const label = document.createElement('span');
      label.textContent = uri;
      const restore = document.createElement('button');
      restore.type = 'button';
      restore.textContent = 'Restore song';
      restore.dataset.playlistOperation = 'restore';
      restore.dataset.playlistUri = uri;
      row.append(label, restore);
      songs.append(row);
    }
    list.append(songs);
    status.textContent = Object.keys(catalogue).length + ' Spotify categories loaded. Expand a genre to manage its playlists.';
  }

  async updatePlaylist(operation, playlist, category) {
    if (this._playlistsPending || !this._hass || !playlist || !category) return;
    this._playlistsPending = true;
    const status = this.shadowRoot.querySelector('.playlists-status');
    status.textContent = 'Saving ' + category + ' playlist change…';
    try {
      const data = await this._hass.callApi('POST', 'declan_two/music-playlists',
                                           {category, playlist: playlist.trim(), operation});
      if (!data || !data.categories) throw new Error('Save not confirmed');
      const updated = await this._hass.callApi('GET', 'declan_two/music-playlists');
      this._playlistCatalogue = updated.categories;
      this._playlistPreferences = updated.preferences || {};
      this.renderPlaylists(category);
      status.textContent = 'Saved playlist change for ' + category + '.';
    } catch {
      status.textContent = 'Playlist change failed. Check the link, the 25-playlist limit and Declan connection.';
    } finally {
      this._playlistsPending = false;
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
        label.textContent = (data.room_labels && data.room_labels[room]) || room.replace(/\b[a-z]/g, character => character.toUpperCase());
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

  async replaceSpotifyCredentials() {
    const form = this.shadowRoot.querySelector('.spotify-form');
    const status = this.shadowRoot.querySelector('.spotify-save-status');
    const client_id = form.querySelector('.spotify-client-id').value.trim();
    const client_secret = form.querySelector('.spotify-client-secret').value.trim();
    if (!client_id || !client_secret) {
      status.textContent = 'Enter both values. Existing credentials have not been changed.';
      return;
    }
    if (!window.confirm('Replace the currently saved Spotify credentials? This cannot be undone.')) return;
    const button = form.querySelector('button');
    button.disabled = true;
    try {
      const result = await this._hass.callApi('POST', 'declan_two/management/spotify',
        {client_id, client_secret, confirm: true});
      if (result.saved !== true) throw new Error('Not saved');
      form.reset();
      status.textContent = 'Spotify credentials replaced successfully.';
      await this.loadSettingsStatus();
    } catch {
      status.textContent = 'Could not replace Spotify credentials. Check the values and backend connection.';
    } finally {
      button.disabled = false;
    }
  }

  resetSettingsImport() {
    this._settingsImportPreview = null;
    this.shadowRoot.querySelector('.settings-import-apply').disabled = true;
    this.shadowRoot.querySelector('.settings-import-summary').textContent = '';
    this.shadowRoot.querySelector('.settings-import-status').textContent = '';
  }

  async previewSettingsImport() {
    this.resetSettingsImport();
    const input = this.shadowRoot.querySelector('.settings-import-file');
    const status = this.shadowRoot.querySelector('.settings-import-status');
    const file = input.files?.[0];
    if (!file || file.size > 131072) {
      status.textContent = 'Choose a Declan settings JSON file smaller than 128 KB.';
      return;
    }
    try {
      const documentData = JSON.parse(await file.text());
      if (!documentData || typeof documentData !== 'object' || Array.isArray(documentData)) throw new Error('Invalid JSON');
      const result = await this._hass.callApi('POST', 'declan_two/management/import', {document: documentData});
      if (!result?.expected || !result.settings) throw new Error('Invalid preview');
      this._settingsImportPreview = {document: documentData, expected: result.expected};
      this.shadowRoot.querySelector('.settings-import-summary').textContent =
        'Settings to import:\\n' + JSON.stringify(result.settings, null, 2) +
        '\\nLearned intentions: ' + result.learning_count +
        (result.replaces_learning ? ' (existing learning will be replaced)' : ' (existing learning retained)') +
        '\\n' + (result.notice || '');
      this.shadowRoot.querySelector('.settings-import-apply').disabled = false;
      status.textContent = 'Preview ready. Review all changes before applying.';
    } catch {
      status.textContent = 'Import preview failed. Check the file format and backend connection.';
    }
  }

  async applySettingsImport() {
    const status = this.shadowRoot.querySelector('.settings-import-status');
    const preview = this._settingsImportPreview;
    if (!preview) return;
    if (!window.confirm('Apply the reviewed settings import? This will replace the listed configuration values.')) return;
    this.shadowRoot.querySelector('.settings-import-apply').disabled = true;
    try {
      const result = await this._hass.callApi('POST', 'declan_two/management/import',
        {document: preview.document, expected: preview.expected, confirm: true});
      if (result.saved !== true) throw new Error('Import not saved');
      status.textContent = 'Configuration imported. Previous settings recovery snapshot is available above.';
      this.shadowRoot.querySelector('.settings-import-file').value = '';
      this.shadowRoot.querySelector('.settings-import-summary').textContent = '';
    } catch {
      status.textContent = 'Import not applied. If settings changed since preview, preview the file again.';
    } finally {
      this._settingsImportPreview = null;
    }
  }

  async downloadSettings(operation) {
    const status = this.shadowRoot.querySelector('.settings-document-status');
    try {
      const result = await this._hass.callApi('GET', 'declan_two/management/' + operation);
      if (!result?.document) throw new Error('Missing document');
      const blob = new Blob([JSON.stringify(result.document, null, 2)], {type:'application/json'});
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'declan-' + operation + '-settings.json';
      link.click();
      URL.revokeObjectURL(url);
      status.textContent = 'Settings file prepared. Keep your backup somewhere safe.';
    } catch {
      status.textContent = 'Unable to retrieve settings ' + operation + '.';
    }
  }

  renderDeclanLogs() {
    const root = this.shadowRoot;
    const level = root.querySelector('.declan-log-level').value;
    const rank = {ALL: 0, INFO: 20, WARNING: 30, ERROR: 40, CRITICAL: 50};
    const entries = (this._declanLogEntries || []).filter(item => (rank[item.level] || 0) >= rank[level]);
    const lines = entries.map(item => item.time + ' [' + item.level + '] [' + item.source + '] ' + item.message);
    this._declanLogText = lines.join('\n');
    root.querySelector('.declan-logs-output').textContent = this._declanLogText || 'No Declan log entries at this level.';
    root.querySelector('.declan-logs-status').textContent = entries.length + ' recent log entries shown (newest first).';
  }

  async loadDeclanLogs() {
    const status = this.shadowRoot.querySelector('.declan-logs-status');
    status.textContent = 'Loading Declan logs…';
    try {
      const result = await this._hass.callApi('GET', 'declan_two/management/logs');
      if (!Array.isArray(result.entries)) throw new Error('Invalid log response');
      this._declanLogEntries = result.entries;
      this.renderDeclanLogs();
    } catch {
      status.textContent = 'Could not load Declan backend logs. Check the Declan connection.';
    }
  }

  async copyDeclanLogs() {
    const status = this.shadowRoot.querySelector('.declan-logs-status');
    try {
      await navigator.clipboard.writeText(this._declanLogText || '');
      status.textContent = 'Declan logs copied.';
    } catch {
      status.textContent = 'Copy unavailable. Select the log text to copy it.';
    }
  }

  async copyDiagnostics() {
    const output = this.shadowRoot.querySelector('.settings-diagnostics-output');
    const status = this.shadowRoot.querySelector('.settings-diagnostics-status');
    const value = output.textContent.trim();
    if (!value) {
      status.textContent = 'Load recent diagnostics before copying.';
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      status.textContent = 'Diagnostics copied to clipboard.';
    } catch {
      // Clipboard access may be unavailable in the iOS Home Assistant webview.
      // Select the existing output so the user can use the native Copy menu.
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(output);
      selection.removeAllRanges();
      selection.addRange(range);
      status.textContent = 'Diagnostics selected. Use Copy from the selection menu.';
    }
  }

  async loadDiagnostics() {
    const status = this.shadowRoot.querySelector('.settings-diagnostics-status');
    const output = this.shadowRoot.querySelector('.settings-diagnostics-output');
    output.textContent = '';
    try {
      const result = await this._hass.callApi('GET', 'declan_two/management/diagnostics');
      if (!Array.isArray(result.traces)) throw new Error('Invalid diagnostics');
      output.textContent = JSON.stringify(result.traces, null, 2);
      status.textContent = 'Showing up to 30 recent traces.';
    } catch {
      status.textContent = 'Unable to load diagnostics.';
    }
  }

  async saveAIKey() {
    const form = this.shadowRoot.querySelector('.ai-key-form');
    const status = this.shadowRoot.querySelector('.ai-key-status');
    const key = form.elements.namedItem('api_key').value;
    status.textContent = 'Saving API key…';
    try {
      const result = await this._hass.callApi('POST', 'declan_two/ai-settings', {api_key: key});
      if (result.key_configured !== true) throw new Error('Key not saved');
      form.reset();
      status.textContent = 'OpenAI API key saved. The key will not be displayed again.';
    } catch {
      status.textContent = 'Could not save the OpenAI API key.';
    }
  }

  async loadAISettings() {
    if (!this._hass) return;
    const form = this.shadowRoot.querySelector('.ai-settings-form');
    const status = this.shadowRoot.querySelector('.ai-settings-status');
    status.textContent = 'Loading AI settings…';
    try {
      const response = await this._hass.callApi('GET', 'declan_two/ai-settings');
      const data = response.settings;
      this._aiSettings = data;
      for (const [key, value] of Object.entries(data)) {
        const field = form.elements.namedItem(key);
        if (field) {
          if (field.type === 'checkbox') field.checked = value === true;
          else field.value = String(value);
        }
      }
      for (const domain of ['light', 'switch', 'fan', 'cover']) {
        form.elements.namedItem('domain_' + domain).checked = data.allowed_domains.includes(domain);
      }
      status.textContent = response.key_configured ? 'AI settings loaded. OpenAI API key configured.' : 'AI settings loaded. Configure an OpenAI API key before enabling fallback.';
      this.shadowRoot.querySelector('.ai-usage').textContent = 'Monthly usage information is available in the AI settings response.';
    } catch {
      status.textContent = 'Could not load AI settings. Changes are not saved.';
    }
  }

  async saveAISettings() {
    const form = this.shadowRoot.querySelector('.ai-settings-form');
    const status = this.shadowRoot.querySelector('.ai-settings-status');
    if (!this._aiSettings) { status.textContent = 'Load settings before saving.'; return; }
    const data = {...this._aiSettings};
    for (const key of ['enabled', 'diagnostics', 'show_proposals']) data[key] = form.elements.namedItem(key).checked;
    for (const key of ['model', 'monthly_budget_usd', 'request_ceiling_usd']) data[key] = form.elements.namedItem(key).value.trim();
    data.max_actions = Number(form.elements.namedItem('max_actions').value);
    data.allowed_domains = ['light', 'switch', 'fan', 'cover'].filter(domain => form.elements.namedItem('domain_' + domain).checked);
    status.textContent = 'Saving AI settings…';
    try {
      const result = await this._hass.callApi('POST', 'declan_two/ai-settings', {settings: data});
      this._aiSettings = result.settings;
      status.textContent = 'AI settings saved.';
    } catch {
      status.textContent = 'Could not save AI settings. Check budget, model and permissions.';
    }
  }

  async loadSettingsStatus() {
    const status = this.shadowRoot.querySelector('.spotify-status');
    if (!this._hass) return;
    status.textContent = 'Checking saved Spotify configuration…';
    try {
      const result = await this._hass.callApi('GET', 'declan_two/settings-status');
      status.textContent = result.spotify_configured
        ? 'Spotify is configured (' + result.spotify_source + '). Existing credentials have not been changed.'
        : 'Spotify credentials are not configured on the backend.';
    } catch {
      status.textContent = 'Could not check Spotify status. Existing credentials have not been changed.';
    }
  }

  cancelMicrophone() {
    if (this._micTimer) clearTimeout(this._micTimer);
    this._micTimer = null;
    if (this._micProcessor) this._micProcessor.disconnect();
    if (this._micSource) this._micSource.disconnect();
    if (this._micStream) this._micStream.getTracks().forEach(track => track.stop());
    if (this._micContext) void this._micContext.close();
    this._micProcessor = this._micSource = this._micStream = this._micContext = null;
    this.shadowRoot.querySelector('.mic-start').disabled = false;
    this.shadowRoot.querySelector('.mic-stop').disabled = true;
  }

  async startMicrophone() {
    if (this._micStream) return;
    const status = this.shadowRoot.querySelector('.mic-status');
    if (!navigator.mediaDevices?.getUserMedia) {
      status.textContent = 'Microphone access is unavailable in this browser or app.';
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({audio: {channelCount: 1, echoCancellation: true}, video: false});
      const context = new (window.AudioContext || window.webkitAudioContext)();
      await context.resume();
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(4096, 1, 1);
      const samples = [];
      processor.onaudioprocess = event => {
        if (!this._micStream) return;
        const input = event.inputBuffer.getChannelData(0);
        samples.push(new Float32Array(input));
      };
      source.connect(processor);
      processor.connect(context.destination);
      this._micStream = stream;
      this._micContext = context;
      this._micSource = source;
      this._micProcessor = processor;
      this._micSamples = samples;
      this._micTimer = setTimeout(() => void this.stopMicrophone(), 20000);
      this.shadowRoot.querySelector('.mic-start').disabled = true;
      this.shadowRoot.querySelector('.mic-stop').disabled = false;
      status.textContent = 'Recording… tap Stop and transcribe when finished.';
    } catch {
      this.cancelMicrophone();
      status.textContent = 'Microphone permission denied or recording unavailable.';
    }
  }

  async stopMicrophone() {
    if (!this._micStream) return;
    const status = this.shadowRoot.querySelector('.mic-status');
    const rate = this._micContext.sampleRate;
    const chunks = this._micSamples;
    this.cancelMicrophone();
    status.textContent = 'Transcribing…';
    const count = chunks.reduce((n, chunk) => n + chunk.length, 0);
    if (!count) { status.textContent = 'No audio captured.'; return; }
    const merged = new Float32Array(count);
    let offset = 0;
    for (const chunk of chunks) { merged.set(chunk, offset); offset += chunk.length; }
    const size = Math.min(320000, Math.floor(merged.length * 16000 / rate));
    const pcm = new Int16Array(size);
    for (let i = 0; i < size; i++) {
      const sample = Math.max(-1, Math.min(1, merged[Math.min(merged.length - 1, Math.floor(i * rate / 16000))]));
      pcm[i] = sample < 0 ? sample * 32768 : sample * 32767;
    }
    try {
      const bytes = new Uint8Array(pcm.buffer);
      let binary = '';
      for (let i = 0; i < bytes.length; i += 8192) {
        binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
      }
      const result = await this._hass.callApi('POST', 'declan_two/microphone', {audio: btoa(binary)});
      if (typeof result.text !== 'string' || !result.text.trim()) throw new Error('No speech recognized');
      this.shadowRoot.querySelector('#native-chat-input').value = result.text.trim();
      status.textContent = 'Transcribed. Review the text and press Send.';
    } catch {
      status.textContent = 'Could not transcribe audio. Check microphone permissions and the Declan backend.';
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
    status.textContent = 'Loading recordings from the last 7 days…';
    try {
      const [pending, reviewed] = await Promise.allSettled([
        this._hass.callApi('GET', 'declan_two/voice-review'),
        this._hass.callApi('GET', 'declan_two/voice-review?history=1')
      ]);
      if (pending.status !== 'fulfilled' && reviewed.status !== 'fulfilled') throw new Error('Voice review unavailable');
      this._voiceProfiles = pending.status === 'fulfilled' && Array.isArray(pending.value.profiles) ? pending.value.profiles : [];
      const pendingRows = pending.status === 'fulfilled' && Array.isArray(pending.value.interactions) ? pending.value.interactions : [];
      const reviewedRows = reviewed.status === 'fulfilled' && Array.isArray(reviewed.value.interactions) ? reviewed.value.interactions : [];
      const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
      const recent = item => {
        const recorded = Date.parse(item.recorded_at || '');
        return Number.isFinite(recorded) && recorded >= cutoff && recorded <= Date.now();
      };
      // Recording IDs are authoritative. Never merge recordings and conversation turns by text or time.
      // A current pending state takes precedence over a stale reviewed-history copy.
      const recordings = new Map();
      for (const item of pendingRows) if (item.id && recent(item)) recordings.set(String(item.id), {kind:'pending', item});
      for (const item of reviewedRows) if (item.id && recent(item) && !recordings.has(String(item.id))) recordings.set(String(item.id), {kind:'reviewed', item});
      // Never infer a conversation turn from transcript text or timestamps.
      // A recording is teachable only when the backend confirms one unique link.
      this._recordingTurnLinks = {};
      const ids = [...recordings.keys()].filter(id => /^[A-Za-z0-9_-]{1,80}$/.test(id));
      try {
        for (let offset = 0; offset < ids.length; offset += 100) {
          const result = await this._hass.callApi('GET',
            'declan_two/history?recording_ids=' + encodeURIComponent(ids.slice(offset, offset + 100).join(',')));
          if (result && result.links && typeof result.links === 'object') {
            Object.assign(this._recordingTurnLinks, result.links);
          }
        }
      } catch {
        // Voice review remains available, but teaching must stay disabled.
        this._recordingTurnLinks = {};
      }
      this._timelineRows = [...recordings.values()].sort((a,b) => Date.parse(b.item.recorded_at) - Date.parse(a.item.recorded_at));
      this._timelineLoaded = true;
      this.renderTimeline();
      const missing = [pending, reviewed].filter(result => result.status !== 'fulfilled').length;
      status.textContent = this._timelineRows.length + ' recordings from the last 7 days' +
        (missing ? ' · ' + missing + ' source(s) unavailable; some recordings may be missing.' : '');
    } catch (error) {
      status.textContent = 'Could not load recordings. Check the VoicePipeline connection and HA permissions.';
    } finally {
      this._timelinePending = false;
    }
  }

  renderTimeline() {
    const list = this.shadowRoot.querySelector('.timeline-list');
    list.replaceChildren();
    const rows = this._timelineRows || [];
    const groups = new Map();
    const groupFor = row => row.kind === 'pending' ? 'Unconfirmed' :
      /dismiss|reject|discard/.test(String(row.item.status || '').toLowerCase()) ? 'Rejected' : 'Confirmed';
    const sectionFor = (title, open = false) => {
      const details = document.createElement('details');
      details.className = 'timeline-group';
      details.open = open;
      const summary = document.createElement('summary');
      summary.textContent = title;
      const count = document.createElement('span');
      count.className = 'timeline-count';
      count.textContent = String(rows.filter(row => groupFor(row) === title).length);
      summary.append(count);
      details.append(summary);
      list.append(details);
      groups.set(title, details);
    };
    sectionFor('Unconfirmed', true);
    sectionFor('Confirmed');
    sectionFor('Rejected');
    const subsection = (parent, title, open = false) => {
      const details = document.createElement('details');
      details.className = 'timeline-subsection';
      details.open = open;
      const summary = document.createElement('summary');
      summary.textContent = title;
      details.append(summary);
      parent.append(details);
      return details;
    };
    for (const {item,kind} of rows) {
      const group = groupFor({item,kind});
      const pending = kind === 'pending';
      const rejected = group === 'Rejected';
      const speaker = item.current_assigned_to || (pending ? '' : item.matched_speaker) || '';
      const entry = document.createElement('details');
      entry.className = 'timeline-entry';
      entry.open = pending;
      const summary = document.createElement('summary');
      summary.textContent = (item.transcript || '(No transcript)') + ' · ' +
        (pending ? 'Needs review' : rejected ? 'Rejected' : speaker || 'Confirmed');
      entry.append(summary);
      const card = document.createElement('article');
      card.className = 'timeline-row timeline-row--' + (pending ? 'pending' : rejected ? 'rejected' : 'confirmed');
      const heading = document.createElement('div');
      heading.className = 'timeline-heading';
      const state = document.createElement('span');
      state.className = 'timeline-status-label timeline-status-label--' + (pending ? 'pending' : rejected ? 'rejected' : 'confirmed');
      state.textContent = pending ? 'Needs review' : rejected ? 'Rejected' : 'Confirmed';
      heading.append(state);
      const recorded = document.createElement('span');
      recorded.className = 'muted';
      recorded.textContent = new Date(item.recorded_at).toLocaleString();
      heading.append(recorded);
      card.append(heading);
      const voice = subsection(card, 'Voice matching', pending);
      const controls = document.createElement('div');
      controls.className = 'timeline-controls';
      const select = document.createElement('select');
      select.className = 'timeline-speaker';
      select.setAttribute('aria-label', 'Speaker for recording');
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = 'Choose speaker';
      select.append(placeholder);
      for (const profile of this._voiceProfiles) {
        if (!profile.name) continue;
        const option = document.createElement('option');
        option.value = profile.name;
        option.textContent = profile.name;
        select.append(option);
      }
      const suggested = item.matched_speaker || '';
      const selected = item.current_assigned_to || suggested;
      if ([...select.options].some(option => option.value === selected)) select.value = selected;
      controls.append(select);
      const confidence = document.createElement('span');
      confidence.className = 'muted';
      confidence.textContent = Number.isFinite(item.match_confidence) ? (item.match_confidence * 100).toFixed(1) + '% match' : 'Match unavailable';
      controls.append(confidence);
      const reviewed = kind === 'reviewed';
      const originalSpeaker = item.current_assigned_to || (reviewed ? '' : suggested) || '';
      select.disabled = reviewed;
      const save = document.createElement('button');
      save.type = 'button';
      let editing = false;
      const syncSave = () => {
        save.disabled = reviewed ? (editing && (!select.value || select.value === originalSpeaker)) : !select.value;
        save.textContent = reviewed ? (editing ? 'Save change' : 'Change speaker') : 'Confirm';
      };
      syncSave();
      select.addEventListener('change', syncSave);
      save.addEventListener('click', async () => {
        if (reviewed && !editing) { editing = true; select.disabled = false; syncSave(); select.focus(); return; }
        if (!select.value) return;
        save.disabled = true;
        if (pending) await this.resolveVoice(item.id, select.value === suggested ? 'confirm' : 'assign', select.value);
        else await this.correctVoiceHistory(item, select.value);
        await this.loadTimeline();
      });
      controls.append(save);
      if (reviewed) {
        const cancel = document.createElement('button');
        cancel.type = 'button';
        cancel.textContent = 'Cancel';
        cancel.hidden = true;
        save.addEventListener('click', () => { cancel.hidden = !editing; });
        cancel.addEventListener('click', () => { editing = false; select.value = originalSpeaker; select.disabled = true; cancel.hidden = true; syncSave(); });
        controls.append(cancel);
      }
      if (item.id) {
        const play = document.createElement('button');
        play.type = 'button';
        play.textContent = 'Play';
        play.setAttribute('aria-label', 'Play voice recording');
        play.addEventListener('click', () => void this.playVoice(item.id, play, this.shadowRoot.querySelector('.timeline-status')));
        controls.append(play);
      }
      if (pending && item.id) {
        const reject = document.createElement('button');
        reject.type = 'button';
        reject.textContent = 'Reject recording';
        reject.addEventListener('click', async () => {
          if (!window.confirm('Reject this recording as bad audio or a false trigger?')) return;
          await this.resolveVoice(item.id, 'dismiss', null);
          await this.loadTimeline();
        });
        controls.append(reject);

      }
      voice.append(controls);
      const training = subsection(card, 'Teach Declan');
      const trainStatus = document.createElement('p');
      trainStatus.className = 'muted';
      const turnId = this._recordingTurnLinks?.[String(item.id)];
      const verified = Number.isSafeInteger(turnId) && turnId > 0 && !rejected;
      trainStatus.textContent = verified
        ? 'What should Declan understand when you say this? Nothing is learned until you save.'
        : 'Teaching requires a verified conversation link. This recording cannot be taught yet.';
      const target = document.createElement('input');
      target.type = 'text';
      target.maxLength = 120;
      target.placeholder = 'The command you meant';
      target.setAttribute('aria-label', 'Correct command for Declan');
      target.disabled = !verified;
      const train = document.createElement('button');
      train.type = 'button';
      train.textContent = 'Save training';
      train.disabled = !verified;
      train.addEventListener('click', async () => {
        const corrected = target.value.trim();
        if (!verified || !corrected || corrected.length > 120) {
          trainStatus.textContent = 'Enter the intended command (up to 120 characters).';
          return;
        }
        train.disabled = true;
        try {
          const result = await this._hass.callApi('POST', 'declan_two/management/intents',
            {turn_id:turnId, target:corrected});
          if (result?.saved !== true) throw new Error('Not saved');
          trainStatus.textContent = 'Command learned. Future requests will use your correction.';
          await this.loadLearnedIntents();
        } catch {
          trainStatus.textContent = 'Training was not confirmed. Refresh before retrying.';
          train.disabled = false;
        }
      });
      training.append(trainStatus, target, train);
      const response = subsection(card, "Declan's response");
      const reply = document.createElement('p');
      reply.textContent = item.reply || 'Not available';
      response.append(reply);
      const diagnostics = subsection(card, 'Diagnostics');
      const diagnosticText = document.createElement('p');
      diagnosticText.textContent = 'Recording ID: ' + item.id + ' · Recorded: ' + item.recorded_at +
        ' · Review status: ' + (item.status || kind) + ' · Suggested speaker: ' + (suggested || 'Unknown') +
        ' · Match confidence: ' + confidence.textContent;
      diagnostics.append(diagnosticText);
      entry.append(card);
      groups.get(group).append(entry);
    }
    if (!rows.length) {
      const empty = document.createElement('p');
      empty.className = 'muted';
      empty.textContent = 'No recordings from the last 7 days.';
      list.append(empty);
    }
  }

  async loadLearnedIntents() {
    const status = this.shadowRoot.querySelector('.intents-status');
    const list = this.shadowRoot.querySelector('.intents-list');
    status.textContent = 'Loading learned commands…';
    try {
      const data = await this._hass.callApi('GET', 'declan_two/management/intents');
      if (!data?.intents || typeof data.intents !== 'object') throw new Error('Invalid list');
      list.replaceChildren();
      for (const [phrase, target] of Object.entries(data.intents).sort(([a], [b]) => a.localeCompare(b))) {
        const row = document.createElement('div');
        row.className = 'intent-row';
        const name = document.createElement('strong');
        name.textContent = phrase;
        const field = document.createElement('input');
        field.type = 'text';
        field.maxLength = 120;
        field.value = target;
        field.setAttribute('aria-label', 'Command for ' + phrase);
        const save = document.createElement('button');
        save.type = 'button';
        save.textContent = 'Save change';
        save.addEventListener('click', async () => {
          const next = field.value.trim();
          if (!next || next === target) return;
          await this.changeLearnedIntent({phrase, target:next, previous:target});
        });
        const forget = document.createElement('button');
        forget.type = 'button';
        forget.textContent = 'Forget';
        forget.addEventListener('click', async () => {
          if (!window.confirm('Forget the learned command for "' + phrase + '"?')) return;
          await this.changeLearnedIntent({forget:phrase, previous:target});
        });
        row.append(name, field, save, forget);
        list.append(row);
      }
      this._intentsLoaded = true;
      status.textContent = list.children.length ? 'Learned commands loaded.' : 'No learned commands yet.';
    } catch {
      status.textContent = 'Unable to load learned commands.';
    }
  }

  async changeLearnedIntent(body) {
    const status = this.shadowRoot.querySelector('.intents-status');
    try {
      const result = await this._hass.callApi('POST', 'declan_two/management/intents', body);
      if (result.saved !== true) throw new Error('Not saved');
      status.textContent = 'Command updated.';
      await this.loadLearnedIntents();
    } catch {
      status.textContent = 'Change rejected. Refresh the list and try again.';
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
      let showProposals = false;
      try {
        const ai = await this._hass.callApi('GET', 'declan_two/ai-settings');
        showProposals = ai?.settings?.show_proposals === true;
      } catch { /* Keep history available when AI settings are offline. */ }
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
        if (showProposals && Array.isArray(turn.action_results) && turn.action_results.some(step => step.ai_generated === true)) {
          const details = document.createElement('details');
          const summary = document.createElement('summary');
          summary.textContent = 'AI action proposals and verified outcomes';
          details.append(summary);
          for (const step of turn.action_results.filter(step => step.ai_generated === true)) {
            const line = document.createElement('p');
            line.textContent = [step.entity_id, step.action, step.status, step.detail].filter(Boolean).join(' · ');
            details.append(line);
          }
          article.append(details);
        }
        if (turn.teachable && Number.isSafeInteger(turn.id) && turn.id > 0) {
          const teach = document.createElement('button');
          teach.type = 'button';
          teach.textContent = 'Teach Declan';
          teach.addEventListener('click', async () => {
            const target = window.prompt('What command should Declan use for this phrase?');
            if (!target || !target.trim() || target.length > 120) return;
            await this.changeLearnedIntent({turn_id:turn.id, target:target.trim()});
          });
          article.append(teach);
        }
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
    const connectionAction = this.shadowRoot.querySelector('.connection-action');
    if (!this._hass || typeof this._hass.callApi !== 'function') {
      state.textContent = 'Waiting for Home Assistant…';
      return;
    }
    this._pending = true;
    connectionAction.dataset.status = 'checking';
    state.textContent = 'Checking Declan API…';
    detail.textContent = 'Connecting through Home Assistant.';
    try {
      const result = await this._hass.callApi('GET', 'declan_two/capabilities');
      if (result && result.compatible === true && result.status === 'connected') {
        connectionAction.dataset.status = 'connected';
        state.textContent = 'Declan API connected';
        detail.textContent = result.server_version ? 'Backend version: ' + result.server_version : 'Backend connected';
      } else {
        connectionAction.dataset.status = 'error';
        state.textContent = 'Declan API incompatible';
        detail.textContent = 'The backend API version is not supported by this integration.';
      }
    } catch (error) {
      connectionAction.dataset.status = 'error';
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
