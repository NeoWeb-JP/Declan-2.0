const assert = require('node:assert/strict');
const {mkdirSync, readFileSync, writeFileSync} = require('node:fs');
const path = require('node:path');
const {test} = require('node:test');
const {pathToFileURL} = require('node:url');
const {JSDOM} = require('jsdom');

const html = readFileSync('index.html', 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const scriptPath = path.resolve('.data/browser-ci/browser.js');
mkdirSync(path.dirname(scriptPath), {recursive: true});
writeFileSync(scriptPath, script);
const flush = () => new Promise(resolve => setImmediate(resolve));

function browser(t, {voice = false, microphone = false, browserRecognition = false, ingress = false, sampleRate = 16000, webkit = false} = {}) {
  const prefix = ingress ? '/api/hassio_ingress/test' : '';
  const {window} = new JSDOM(html, {runScripts: 'outside-only', url: 'http://localhost:8765' + prefix + '/'});
  t.after(() => window.close());
  const pending = new Map();
  const calls = [];
  const responses = new Map();
  const spoken = [];
  const drawing = [];
  let nextTimer = 0;
  let recognition;
  let streamStopped = false;
  let audioClosed = false;
  let capture;
  window.setTimeout = (callback, delay) => {
    pending.set(++nextTimer, {callback, delay});
    return nextTimer;
  };
  window.clearTimeout = id => pending.delete(id);
  window.fetch = async (url, options) => {
    const resolved = new URL(url, window.location.href);
    assert.ok(resolved.pathname.startsWith(prefix + '/'), 'Request escaped the Ingress path');
    url = resolved.pathname.slice(prefix.length) + resolved.search;
    calls.push({url, options});
    const response = responses.get(url) ?? {status: 'connected', release_version: 'v1.2.3'};
    if (response instanceof Error) throw response;
    return {ok: !response.error, json: async () => response};
  };
  const element = selector => window.document.querySelector(selector);
  window.URL.createObjectURL = () => 'blob:test-audio';
  window.URL.revokeObjectURL = () => {};
  window.HTMLAnchorElement.prototype.click = function () {};
  window.confirm = () => true;
  for (const dialog of window.document.querySelectorAll('dialog')) {
    dialog.showModal = () => { dialog.open = true; };
    dialog.close = () => {
      dialog.open = false;
      dialog.dispatchEvent(new window.Event('close'));
    };
  }
  const canvas = {clearRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() { drawing.push(true); }};
  window.HTMLCanvasElement.prototype.getContext = () => microphone ? canvas : null;
  if (voice) {
    window.SpeechRecognition = class {
      constructor() { recognition = this; }
      start() {}
      abort() { this.onend(); }
    };
    window.SpeechSynthesisUtterance = class {
      constructor(text) { this.text = text; }
    };
    window.speechSynthesis = {speak: utterance => spoken.push(utterance)};
  }
  if (microphone) {
    window.matchMedia = () => ({matches: false});
    window.requestAnimationFrame = () => 1;
    window.cancelAnimationFrame = () => {};
    window.navigator.mediaDevices = {getUserMedia: async () => ({
      getTracks: () => [{stop: () => { streamStopped = true; }}],
    })};
    window.AudioContext = class {
      constructor() { this.sampleRate = sampleRate; }
      resume() { return Promise.resolve(); }
      close() { audioClosed = true; return Promise.resolve(); }
      createAnalyser() { return {getByteTimeDomainData: values => values.fill(140)}; }
      createMediaStreamSource() { return {connect() {}, disconnect() {}}; }
      createScriptProcessor() { return capture = {connect() {}, disconnect() {}}; }
    };
  }
  if (webkit) {
    window.webkitAudioContext = window.AudioContext;
    delete window.AudioContext;
  }
  if (browserRecognition) element('#use-assist-stt').checked = false;
  window.eval(script + '\n//# sourceURL=' + pathToFileURL(scriptPath).href);
  return {
    calls, responses, element, recognition, spoken, drawing, window,
    recordSamples: values => capture.onaudioprocess({inputBuffer: {getChannelData: () => values}}),
    microphoneStopped: () => streamStopped && audioClosed,
    async tick(delay) {
      for (const [id, timer] of pending) {
        if (timer.delay === delay) {
          pending.delete(id);
          timer.callback();
          await flush();
          return true;
        }
      }
      return false;
    },
    async submit(message) {
      element('form input').value = message;
      element('form').dispatchEvent(new window.Event('submit', {cancelable: true}));
      await flush();
    },
  };
}

test('Spotify credentials are entered locally and cleared after saving', async t => {
  const ui = browser(t);
  ui.responses.set('/api/settings/spotify', {source: 'environment'});
  ui.element('#open-spotify').click();
  await flush();
  assert.equal(ui.element('#spotify-settings').open, true);
  assert.match(ui.element('#spotify-status').textContent, /launch environment/);
  const form = ui.element('#spotify-form');
  const secret = form.elements.client_secret;
  assert.equal(secret.type, 'password');
  assert.equal(secret.value, '');
  form.elements.client_id.value = 'test-id';
  secret.value = 'test-secret';
  ui.responses.set('/api/settings/spotify', {source: 'saved'});
  form.dispatchEvent(new form.ownerDocument.defaultView.Event('submit', {cancelable: true}));
  await flush();
  assert.equal(ui.calls.at(-1).options.method, 'POST');
  assert.equal(secret.value, '');
  assert.match(ui.element('#spotify-status').textContent, /next Spotify search/);
  ui.element('#close-spotify').click();
  assert.equal(ui.element('#spotify-settings').open, false);
});

test('shows build information and reports a disconnected Home Assistant', async t => {
  const ui = browser(t);
  await flush();
  assert.match(ui.element('#ha-status').textContent, /connected.*Release v1\.2\.3/);
  assert.match(ui.element('#voice-status').textContent, /unavailable/);
  ui.responses.set('/api/ha-status', new Error('connection lost'));
  await ui.tick(15000);
  assert.match(ui.element('#ha-status').textContent, /disconnected.*Release v1\.2\.3/);
  ui.responses.set('/api/ha-status', {status: 'connected', release_version: null});
  await ui.tick(15000);
  assert.match(ui.element('#ha-status').textContent, /Development build/);
});

test('keyboard chat retains the session and shows send errors', async t => {
  const ui = browser(t);
  ui.responses.set('/api/chat', {session_id: 'test-session', reply: 'Morning.', history_saved: false});
  await ui.submit('  hello  ');
  assert.equal(ui.element('#latest-message').textContent, 'hello');
  assert.match(ui.element('#latest-reply').textContent, /Morning/);
  assert.match(ui.element('#history-status').textContent, /could not be saved/);
  ui.responses.set('/api/chat', {error: 'Offline'});
  await ui.submit('good morning');
  assert.equal(JSON.parse(ui.calls.at(-1).options.body).session_id, 'test-session');
  assert.match(ui.element('#latest-reply').textContent, /Offline/);
  await ui.submit('x'.repeat(1001));
  assert.match(ui.element('#latest-reply').textContent, /under 1,000/);
});

test('history opens, renders routine evidence, and loads an older page', async t => {
  const ui = browser(t);
  ui.responses.set('/api/history', {turns: [{
    created_at: '2026-11-10T08:00:00Z', source: 'assist', outcome: 'partial',
    message: 'good morning', reply: 'Morning.', routine_status: 'Dining lights unverified.',
    action_results: [{action: 'turn_on', target: 'Dining lights', status: 'unverified', detail: 'unavailable'}],
    phrase_suggestion: 'run good morning',
    speaker_match: {name: 'Unknown', confidence: 0.34, interaction_id: 'match-123'},
  }], next: 42});
  ui.responses.set('/api/history?before=42', {turns: [{
    created_at: '2026-11-09T08:00:00Z', source: 'browser_voice', message: 'hello', reply: 'Hello.',
  }], next: null});
  ui.element('#open-history').click();
  await flush();
  assert.equal(ui.element('#history').open, true);
  assert.match(ui.element('#chat').textContent, /Home Assistant Routine Status/);
  assert.match(ui.element('#chat').textContent, /turn on Dining lights: unverified \(unavailable\)/);
  assert.match(ui.element('#chat').textContent, /Possible rephrase/);
  assert.match(ui.element('#chat').textContent, /Speaker match: Unknown \(34% confidence\)/);
  assert.match(ui.element('#chat').textContent, /VoicePipeline interaction: match-123/);
  ui.element('#older-history').click();
  await flush();
  assert.equal(ui.element('#chat').children.length, 2);
  assert.equal(ui.element('#older-history').hidden, true);
  ui.responses.set('/api/history', {error: 'Offline'});
  ui.element('#refresh-history').click();
  await flush();
  assert.match(ui.element('#history-status').textContent, /History could not be loaded/);
  ui.element('#close-history').click();
  assert.equal(ui.element('#history').open, false);
});

test('clearing history requires confirmation and resets the history list', async t => {
  const ui = browser(t);
  ui.responses.set('/api/history', {turns: [{
    created_at: '2026-11-10T08:00:00Z', source: 'assist', message: 'hello', reply: 'Hello.',
  }], next: 42});
  ui.element('#open-history').click();
  await flush();

  ui.window.confirm = () => false;
  ui.element('#clear-history').click();
  assert.equal(ui.calls.filter(call => call.url === '/api/history/clear').length, 0);
  assert.equal(ui.element('#chat').children.length, 1);

  ui.window.confirm = () => true;
  ui.responses.set('/api/history/clear', {error: 'Offline'});
  ui.element('#clear-history').click();
  await flush();
  assert.equal(ui.element('#chat').children.length, 1);
  assert.match(ui.element('#history-status').textContent, /could not be cleared/);

  ui.responses.set('/api/history/clear', {deleted: 1});
  ui.element('#clear-history').click();
  await flush();
  const request = ui.calls.at(-1);
  assert.equal(request.options.method, 'POST');
  assert.deepEqual(JSON.parse(request.options.body), {confirm: true});
  assert.equal(ui.element('#chat').children.length, 0);
  assert.equal(ui.element('#older-history').hidden, true);
  assert.match(ui.element('#history-status').textContent, /history cleared/);
});

test('history teaches a missed voice command without sending a chat command', async t => {
  const ui = browser(t);
  const page = {
    turns: [{
      id: 42, created_at: '2026-11-10T08:00:00Z', source: 'assist',
      message: 'End 60 time.', reply: 'Please rephrase.', teachable: true,
    }],
    next: null, teachable_intents: ['end sexy time'], learned_intents: {},
  };
  ui.responses.set('/api/history', page);
  ui.responses.set('/api/history/intents', {saved: true});
  ui.element('#open-history').click();
  await flush();
  assert.match(ui.element('#chat').textContent, /Teach intention/);
  ui.element('#chat input').value = 'end sexy time';
  ui.responses.set('/api/history', {...page, learned_intents: {'end 60 time': 'end sexy time'}});
  ui.element('#chat form button').click();
  await flush();
  const saved = ui.calls.find(call => call.url === '/api/history/intents');
  assert.deepEqual(JSON.parse(saved.options.body), {turn_id: 42, target: 'end sexy time'});
  assert.equal(ui.calls.some(call => call.url === '/api/chat'), false);
  assert.match(ui.element('#learned-intent-list').textContent, /end 60 time.*end sexy time/);
  ui.element('#learned-intent-list button').click();
  await flush();
  assert.deepEqual(JSON.parse(ui.calls.at(-1).options.body), {forget: 'end 60 time'});
  assert.equal(ui.element('#learned-intents').hidden, true);
});

test('Ingress keeps assets and history requests under the panel path', async t => {
  const ui = browser(t, {ingress: true});
  ui.responses.set('/api/history', {turns: [], next: null});
  ui.element('#open-history').click();
  await flush();
  assert.match(ui.element('#history-status').textContent, /No saved conversations/);
  assert.match(ui.element('a[download]').href, /\/api\/hassio_ingress\/test\/api\/history\/export$/);
  assert.match(ui.element('img').src, /\/api\/hassio_ingress\/test\/logo.png$/);
});

function transcript(recognition, text, isFinal = true) {
  const result = [{transcript: text}];
  result.isFinal = isFinal;
  recognition.onresult({results: [result], resultIndex: 0});
}

test('voice waits for a chained sentence, speaks the reply and resumes listening', async t => {
  const ui = browser(t, {voice: true, microphone: true, browserRecognition: true});
  ui.element('#talk').click();
  await flush();
  ui.responses.set('/api/chat', {session_id: 'voice-session', reply: 'Both steps finished.'});
  ui.responses.set('/api/tts', {error: 'Voice unavailable'});
  ui.element('#spoken-replies').checked = true;
  transcript(ui.recognition, 'run good morning and');
  assert.match(ui.element('#voice-status').textContent, /Keep going/);
  transcript(ui.recognition, 'turn on the fairy lights', false);
  assert.equal(await ui.tick(5000), false);
  transcript(ui.recognition, 'turn on the fairy lights');
  assert.equal(await ui.tick(1400), true);
  const chat = ui.calls.find(call => call.url === '/api/chat');
  assert.equal(JSON.parse(chat.options.body).message, 'run good morning and turn on the fairy lights');
  assert.equal(JSON.parse(chat.options.body).source, 'voice');
  assert.equal(ui.calls.at(-1).url, '/api/tts');
  assert.equal(JSON.parse(ui.calls.at(-1).options.body).message, 'Both steps finished.');
  assert.equal(ui.spoken[0].text, 'Both steps finished.');
  ui.spoken[0].onend();
  assert.equal(await ui.tick(350), true);
  ui.element('#talk').click();
  assert.match(ui.element('#voice-status').textContent, /paused/);
  assert.ok(ui.drawing.length > 0);
  assert.equal(ui.microphoneStopped(), true);
});

test('Assist microphone sends audio then submits the returned transcript once', async t => {
  const ui = browser(t, {voice: true, microphone: true});
  ui.element('#talk').click();
  ui.responses.set('/api/stt', {text: 'what time is it'});
  ui.responses.set('/api/chat', {session_id: 'assist-mic', reply: 'Time check.'});
  ui.element('#spoken-replies').checked = false;
  await flush();
  assert.equal(ui.element('#use-assist-stt').checked, true);
  const silence = new Float32Array(2048);
  ui.recordSamples(silence);
  assert.equal(ui.calls.some(call => call.url === '/api/stt'), false);
  ui.recordSamples(new Float32Array(2048).fill(0.2));
  ui.recordSamples(new Float32Array(2048).fill(0.2));
  for (let index = 0; index < 12; index++) ui.recordSamples(silence);
  await flush();
  const stt = ui.calls.find(call => call.url === '/api/stt');
  assert.equal(stt.options.body.byteLength, 10 * 2048 * 2);
  const chat = ui.calls.filter(call => call.url === '/api/chat');
  assert.equal(chat.length, 1);
  assert.equal(JSON.parse(chat[0].options.body).message, 'what time is it');
  assert.equal(ui.microphoneStopped(), false);
  assert.equal(await ui.tick(350), true);
  assert.match(ui.element('#voice-status').textContent, /Listening with Assist/);
});

for (const sampleRate of [44100, 48000]) {
  test(`Assist records ${sampleRate} Hz browser audio after a tap and sends 16 kHz PCM`, async t => {
    const ui = browser(t, {microphone: true, webkit: true, sampleRate});
    assert.equal(ui.element('#use-assist-stt').disabled, false);
    assert.match(ui.element('#voice-status').textContent, /Tap the orb/);
    ui.responses.set('/api/stt', {text: 'what time is it'});
    ui.responses.set('/api/chat', {session_id: 'ios', reply: 'Time check.'});
    ui.element('#spoken-replies').checked = false;
    ui.element('#talk').click();
    await flush();
    ui.recordSamples(new Float32Array(sampleRate / 2).fill(0.2));
    ui.recordSamples(new Float32Array(sampleRate));
    await flush();
    const stt = ui.calls.find(call => call.url === '/api/stt');
    assert.equal(stt.options.body.byteLength, 48000);
    const pcm = new Int16Array(stt.options.body);
    assert.ok(Math.abs(pcm[0] - 6554) < 2);
    assert.equal(pcm[pcm.length - 1], 0);
    ui.element('#talk').click();
    assert.equal(ui.microphoneStopped(), true);
  });
}

test('updates list allows selecting an older release', async t => {
  const ui = browser(t);
  ui.responses.set('/api/updates', {enabled: true, state: 'idle', current: '0.1.2', versions: ['0.1.3', '0.1.2', '0.1.1']});
  ui.element('#open-updates').click();
  await flush();
  assert.deepEqual(Array.from(ui.element('#update-version').options, option => option.value), ['0.1.3', '0.1.1']);
  ui.element('#update-version').value = '0.1.1';
  ui.element('#install-update').click();
  await flush();
  const requests = ui.calls.filter(call => call.url === '/api/updates');
  assert.deepEqual(JSON.parse(requests[1].options.body), {version: '0.1.1'});
  assert.match(ui.element('#update-status').textContent, /restart automatically/);
  ui.responses.set('/api/updates/status', {state: 'failed'});
  assert.equal(await ui.tick(2000), true);
  assert.match(ui.element('#update-status').textContent, /current build is still running/);
});

test('incomplete voice commands never reach the server', async t => {
  const ui = browser(t, {voice: true});
  ui.element('#talk').click();
  transcript(ui.recognition, 'turn on the kitchen and');
  assert.equal(await ui.tick(5000), true);
  assert.match(ui.element('#latest-reply').textContent, /only caught part/);
  assert.equal(ui.calls.some(call => call.url === '/api/chat'), false);
  ui.recognition.onerror({error: 'not-allowed'});
  assert.equal(ui.element('#keyboard').open, true);
  assert.match(ui.element('#voice-status').textContent, /Allow microphone access/);
});

test('diagnostics show stages, request references and provider failures without executing commands', async t => {
  const ui = browser(t, {ingress: true});
  ui.responses.set('/api/diagnostics', {traces: [{id: 'trace-one', created_at: '2026-11-11',
    route: '/api/chat', outcome: 'partial', duration_ms: 41,
    stages: [{stage: 'spotify_search', outcome: 'failed', error: 'TimeoutError', duration_ms: 40}]}]});
  ui.element('#open-diagnostics').click(); await flush();
  assert.equal(ui.element('#diagnostics-panel').open, true);
  assert.match(ui.element('#diagnostics-list').textContent, /trace-one.*spotify_search: failed.*TimeoutError/);
  ui.responses.set('/api/diagnostics', {traces: []});
  ui.element('#refresh-diagnostics').click(); await flush();
  assert.match(ui.element('#diagnostics-status').textContent, /No request/);
  ui.responses.set('/api/diagnostics', {error: 'Storage unavailable'});
  ui.element('#refresh-diagnostics').click(); await flush();
  assert.match(ui.element('#diagnostics-status').textContent, /Storage unavailable/);
  ui.element('[data-close="diagnostics-panel"]').click();
  assert.equal(ui.element('#diagnostics-panel').open, false);
  assert.equal(ui.calls.some(call => call.url === '/api/chat'), false);
});

test('editing a learned intention includes its previous value and does not run it', async t => {
  const ui = browser(t);
  ui.responses.set('/api/history', {turns: [{id: 1, created_at: '2026-11-11', message: 'Hello', reply: 'Hi',
    source: 'assist', diagnostic_id: 'request-123'}], next: null,
    learned_intents: {'bring me time': 'dinner time'}});
  ui.responses.set('/api/history/intents', {saved: true});
  ui.element('#open-history').click(); await flush();
  assert.match(ui.element('#chat').textContent, /Request: request-123/);
  ui.element('#learned-intent-list input').value = 'start sexy time';
  ui.element('#learned-intent-list button:last-child').click(); await flush();
  assert.deepEqual(JSON.parse(ui.calls.at(-1).options.body), {
    phrase: 'bring me time', target: 'start sexy time', previous: 'dinner time'
  });
  assert.match(ui.element('#history-status').textContent, /No command was run/);
  ui.responses.set('/api/history/intents', {error: 'Refresh before editing'});
  ui.element('#learned-intent-list button:last-child').click(); await flush();
  assert.match(ui.element('#history-status').textContent, /Refresh before editing/);
  ui.window.confirm = () => false;
  const count = ui.calls.length;
  ui.element('#learned-intent-list button').click(); await flush();
  assert.equal(ui.calls.length, count);
  assert.equal(ui.calls.some(call => call.url === '/api/chat'), false);
});

function settingsFile(ui, document) {
  Object.defineProperty(ui.element('#import-settings-file'), 'files', {configurable: true,
    value: [{size: 100, text: async () => JSON.stringify(document)}]});
  ui.element('#import-settings-file').dispatchEvent(new ui.window.Event('change'));
}

test('settings import requires a preview and confirmation and protects private exports', async t => {
  const ui = browser(t, {ingress: true});
  const document = {format: 'declan-settings', schema_version: 1, settings: {DECLAN_MOVIE_SCRIPT: 'script.movie'}};
  ui.element('#open-backup').click();
  assert.equal(ui.element('#backup-panel').open, true);
  assert.match(ui.element('#download-settings').href, /settings\/export$/);
  ui.element('#backup-learning').checked = true;
  ui.element('#backup-learning').dispatchEvent(new ui.window.Event('change'));
  assert.match(ui.element('#download-settings').href, /export-learning$/);
  ui.element('#backup-learning').checked = false;
  ui.element('#backup-learning').dispatchEvent(new ui.window.Event('change'));
  settingsFile(ui, document);
  ui.responses.set('/api/settings/import', {expected: 'revision', settings: document.settings,
    learning_count: 0, replaces_learning: false, notice: 'Check the IDs'});
  ui.element('#preview-settings').click(); await flush();
  assert.match(ui.element('#settings-preview').textContent, /script.movie/);
  assert.equal(ui.element('#apply-settings').disabled, false);
  ui.window.confirm = () => false; ui.element('#apply-settings').click(); await flush();
  assert.equal(ui.calls.filter(call => call.url === '/api/settings/import').length, 1);
  ui.window.confirm = () => true; ui.responses.set('/api/settings/import', {saved: true});
  ui.element('#apply-settings').click(); await flush();
  assert.deepEqual(JSON.parse(ui.calls.at(-1).options.body), {document, expected: 'revision', confirm: true});
  assert.match(ui.element('#backup-status').textContent, /No household actions/);
  assert.equal(ui.element('#apply-settings').disabled, true);
});

test('bad or stale settings previews cannot be applied or blindly retried', async t => {
  const ui = browser(t);
  ui.element('#preview-settings').click(); await flush();
  assert.match(ui.element('#backup-status').textContent, /Choose a settings/);
  settingsFile(ui, {});
  ui.responses.set('/api/settings/import', {error: 'Invalid schema'});
  ui.element('#preview-settings').click(); await flush();
  assert.equal(ui.element('#apply-settings').disabled, true);
  assert.match(ui.element('#backup-status').textContent, /Invalid schema/);
  ui.responses.set('/api/settings/import', {expected: 'old', settings: {}, learning_count: 0});
  ui.element('#preview-settings').click(); await flush();
  ui.responses.set('/api/settings/import', {error: 'Settings changed'});
  ui.element('#apply-settings').click(); await flush();
  assert.equal(ui.element('#apply-settings').disabled, true);
  assert.match(ui.element('#backup-status').textContent, /Preview again/);
});

const profilePage = {profiles: [{id: 'jaco', name: 'Jaco', samples: []}], notice: 'Samples stay local.'};
async function openProfiles(ui) {
  ui.responses.set('/api/voice-profiles', profilePage);
  ui.element('#open-voices').click(); await flush();
}

test('voice profile controls require consent, report errors and confirm deletion', async t => {
  const ui = browser(t);
  await openProfiles(ui);
  assert.match(ui.element('#voices-status').textContent, /Samples stay local/);
  ui.element('#record-voice-sample').click(); await flush();
  assert.match(ui.element('#voices-status').textContent, /confirm consent/);
  ui.element('#voice-profile-name').value = 'Edd'; ui.element('#voice-consent').checked = true;
  ui.element('#create-voice-profile').click(); await flush();
  assert.deepEqual(JSON.parse(ui.calls.at(-1).options.body), {operation: 'create', name: 'Edd', consent: true});
  ui.responses.set('/api/voice-profiles', {error: 'Already exists'});
  ui.element('#create-voice-profile').click(); await flush();
  assert.match(ui.element('#voices-status').textContent, /Already exists/);
  ui.window.confirm = () => false; const count = ui.calls.length;
  ui.element('#delete-voice-profile').click(); await flush(); assert.equal(ui.calls.length, count);
  ui.window.confirm = () => true;
  ui.element('#delete-voice-profile').click(); await flush();
  assert.match(ui.element('#voices-status').textContent, /Already exists/);
  ui.responses.set('/api/voice-profiles', {profiles: []});
  ui.element('#delete-voice-profile').click(); await flush();
  assert.match(ui.element('#voices-status').textContent, /Profile and active samples deleted/);
  assert.equal(ui.element('#voice-profile-select').children.length, 0);
});

test('recorded voice samples are reviewed before saving and do not call STT or chat', async t => {
  const ui = browser(t, {microphone: true, webkit: true, sampleRate: 48000});
  await openProfiles(ui); ui.element('#voice-consent').checked = true;
  ui.element('#record-voice-sample').click(); await flush();
  assert.equal(ui.element('#stop-voice-sample').disabled, false);
  ui.recordSamples(new Float32Array(48000).fill(0.15));
  ui.element('#stop-voice-sample').click(); await flush();
  assert.equal(ui.element('#save-voice-sample').disabled, false);
  assert.match(ui.element('#voices-status').textContent, /Listen to the recording/);
  ui.responses.set('/api/voice-profiles', {error: 'Sample rejected'});
  ui.element('#save-voice-sample').click(); await flush();
  assert.match(ui.element('#voices-status').textContent, /Sample rejected/);
  ui.responses.set('/api/voice-profiles', profilePage);
  ui.element('#save-voice-sample').click(); await flush();
  const saved = JSON.parse(ui.calls.at(-1).options.body);
  assert.equal(saved.operation, 'save_sample'); assert.equal(saved.profile, 'jaco');
  const wav = Buffer.from(saved.audio, 'base64');
  assert.equal(wav.toString('ascii', 0, 4), 'RIFF');
  assert.equal(wav.readUInt32LE(24), 16000); assert.equal(wav.length, 32044);
  assert.equal(ui.element('#save-voice-sample').disabled, true);
  assert.equal(ui.microphoneStopped(), true);
  assert.equal(ui.calls.some(call => ['/api/chat', '/api/stt'].includes(call.url)), false);
});

test('closing the enrolment page cancels microphone permission races and discards drafts', async t => {
  const ui = browser(t, {microphone: true});
  await openProfiles(ui); ui.element('#voice-consent').checked = true;
  let resolvePermission; let stopped = false;
  ui.window.navigator.mediaDevices.getUserMedia = () => new Promise(resolve => { resolvePermission = resolve; });
  ui.element('#record-voice-sample').click(); await flush();
  ui.element('[data-close="voices-panel"]').click();
  resolvePermission({getTracks: () => [{stop: () => { stopped = true; }}]}); await flush();
  assert.equal(stopped, true);
  assert.equal(ui.element('#save-voice-sample').disabled, true);
  await openProfiles(ui);
  ui.window.navigator.mediaDevices.getUserMedia = async () => { throw new Error('Denied'); };
  ui.element('#record-voice-sample').click(); await flush();
  assert.match(ui.element('#voices-status').textContent, /Could not record/);
  assert.equal(ui.element('#record-voice-sample').disabled, false);
});

test('voice recording duration is bounded and profile changes discard drafts', async t => {
  const ui = browser(t, {microphone: true});
  await openProfiles(ui); ui.element('#voice-consent').checked = true;
  ui.element('#record-voice-sample').click(); await flush();
  ui.recordSamples(new Float32Array(10).fill(0.1));
  ui.element('#stop-voice-sample').click(); await flush();
  assert.match(ui.element('#voices-status').textContent, /at least one second/);
  ui.element('#record-voice-sample').click(); await flush();
  ui.recordSamples(new Float32Array(180000).fill(0.1)); await flush();
  assert.equal(ui.element('#stop-voice-sample').disabled, true);
  assert.equal(ui.element('#save-voice-sample').disabled, false);
  ui.element('#voice-profile-select').dispatchEvent(new ui.window.Event('change'));
  assert.equal(ui.element('#save-voice-sample').disabled, true);
});

test('saved voice samples can be listened to, exported and removed with confirmation', async t => {
  const ui = browser(t);
  const page = {profiles: [{id: 'jaco', name: 'Jaco', samples: [{id: 'sample', duration: 2}]}]};
  ui.responses.set('/api/voice-profiles', page);
  ui.element('#open-voices').click(); await flush();
  ui.responses.set('/api/voice-profiles', {samples: [{audio: 'UklGRg=='}]});
  ui.element('#voice-sample-list button').click(); await flush();
  assert.equal(ui.element('#save-voice-sample').disabled, false);
  ui.element('#export-voice-profile').click(); await flush();
  assert.match(ui.element('#voices-status').textContent, /No model was changed/);
  ui.responses.set('/api/voice-profiles', {error: 'Unavailable'});
  ui.element('#voice-sample-list button').click(); await flush();
  assert.match(ui.element('#voices-status').textContent, /Unavailable/);
  ui.element('#export-voice-profile').click(); await flush();
  assert.match(ui.element('#voices-status').textContent, /Unavailable/);
  ui.window.confirm = () => false; const count = ui.calls.length;
  ui.element('#voice-sample-list button:last-child').click(); await flush(); assert.equal(ui.calls.length, count);
  ui.window.confirm = () => true; ui.responses.set('/api/voice-profiles', profilePage);
  ui.element('#voice-sample-list button:last-child').click(); await flush();
  assert.equal(ui.element('#voice-sample-list').children.length, 0);
});

test('WAV upload is size bounded and the file must still belong to the selected profile', async t => {
  const ui = browser(t);
  await openProfiles(ui);
  const input = ui.element('#voice-sample-file');
  Object.defineProperty(input, 'files', {configurable: true, value: [{size: 999999}]});
  input.dispatchEvent(new ui.window.Event('change'));
  assert.match(ui.element('#voices-status').textContent, /one to ten second/);
  ui.window.FileReader = class {
    readAsDataURL() { this.result = 'data:audio/wav;base64,UklGRg=='; this.onload(); }
  };
  Object.defineProperty(input, 'files', {configurable: true, value: [{size: 50}]});
  input.dispatchEvent(new ui.window.Event('change'));
  assert.equal(ui.element('#save-voice-sample').disabled, false);
  ui.element('[data-close="voices-panel"]').click();
  assert.equal(ui.element('#save-voice-sample').disabled, true);
});
