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

function browser(t, {voice = false, microphone = false, browserRecognition = false} = {}) {
  const {window} = new JSDOM(html, {runScripts: 'outside-only', url: 'http://localhost:8765'});
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
    calls.push({url, options});
    const response = responses.get(url) ?? {status: 'connected', release_version: 'v1.2.3'};
    if (response instanceof Error) throw response;
    return {ok: !response.error, json: async () => response};
  };
  const element = selector => window.document.querySelector(selector);
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
      constructor({sampleRate} = {}) { this.sampleRate = sampleRate; }
      resume() { return Promise.resolve(); }
      close() { audioClosed = true; return Promise.resolve(); }
      createAnalyser() { return {getByteTimeDomainData: values => values.fill(140)}; }
      createMediaStreamSource() { return {connect() {}}; }
      createScriptProcessor() { return capture = {connect() {}}; }
    };
  }
  if (browserRecognition) element('#use-assist-stt').checked = false;
  window.eval(script + '\n//# sourceURL=' + pathToFileURL(scriptPath).href);
  return {
    calls, responses, element, recognition, spoken, drawing,
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

function transcript(recognition, text, isFinal = true) {
  const result = [{transcript: text}];
  result.isFinal = isFinal;
  recognition.onresult({results: [result], resultIndex: 0});
}

test('voice waits for a chained sentence, speaks the reply and resumes listening', async t => {
  const ui = browser(t, {voice: true, microphone: true, browserRecognition: true});
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
  assert.equal(stt.options.body.byteLength, 15 * 2048 * 2);
  const chat = ui.calls.filter(call => call.url === '/api/chat');
  assert.equal(chat.length, 1);
  assert.equal(JSON.parse(chat[0].options.body).message, 'what time is it');
  assert.equal(ui.microphoneStopped(), true);
  assert.equal(await ui.tick(350), true);
  assert.match(ui.element('#voice-status').textContent, /Listening with Assist/);
});

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
  transcript(ui.recognition, 'turn on the kitchen and');
  assert.equal(await ui.tick(5000), true);
  assert.match(ui.element('#latest-reply').textContent, /only caught part/);
  assert.equal(ui.calls.some(call => call.url === '/api/chat'), false);
  ui.recognition.onerror({error: 'not-allowed'});
  assert.equal(ui.element('#keyboard').open, true);
  assert.match(ui.element('#voice-status').textContent, /Allow microphone access/);
});
