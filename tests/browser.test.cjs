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

function browser(t, {voice = false, microphone = false} = {}) {
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
  const dialog = element('#history');
  dialog.showModal = () => { dialog.open = true; };
  dialog.close = () => {
    dialog.open = false;
    dialog.dispatchEvent(new window.Event('close'));
  };
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
      resume() { return Promise.resolve(); }
      close() { audioClosed = true; return Promise.resolve(); }
      createAnalyser() { return {getByteTimeDomainData: values => values.fill(140)}; }
      createMediaStreamSource() { return {connect() {}}; }
    };
  }
  window.eval(script + '\n//# sourceURL=' + pathToFileURL(scriptPath).href);
  return {
    calls, responses, element, recognition, spoken, drawing,
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
    created_at: '2026-11-10T08:00:00Z', source: 'ha_sentence', outcome: 'partial',
    message: 'good morning', reply: 'Morning.', routine_status: 'Dining lights unverified.',
    action_results: [{action: 'turn_on', target: 'Dining lights', status: 'unverified', detail: 'unavailable'}],
    phrase_suggestion: 'run good morning',
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
  const ui = browser(t, {voice: true, microphone: true});
  await flush();
  ui.responses.set('/api/chat', {session_id: 'voice-session', reply: 'Both steps finished.'});
  ui.element('#spoken-replies').checked = true;
  transcript(ui.recognition, 'run good morning and');
  assert.match(ui.element('#voice-status').textContent, /Keep going/);
  transcript(ui.recognition, 'turn on the fairy lights', false);
  assert.equal(await ui.tick(5000), false);
  transcript(ui.recognition, 'turn on the fairy lights');
  assert.equal(await ui.tick(1400), true);
  assert.equal(JSON.parse(ui.calls.at(-1).options.body).message, 'run good morning and turn on the fairy lights');
  assert.equal(JSON.parse(ui.calls.at(-1).options.body).source, 'voice');
  assert.equal(ui.spoken[0].text, 'Both steps finished.');
  ui.spoken[0].onend();
  assert.equal(await ui.tick(350), true);
  ui.element('#talk').click();
  assert.match(ui.element('#voice-status').textContent, /paused/);
  assert.ok(ui.drawing.length > 0);
  assert.equal(ui.microphoneStopped(), true);
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
