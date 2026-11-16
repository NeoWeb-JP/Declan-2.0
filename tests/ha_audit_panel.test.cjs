const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {test} = require('node:test');
const {JSDOM} = require('jsdom');
const source = readFileSync('custom_components/declan_two/frontend/panel.js', 'utf8');

function panel(t, response) {
  const dom = new JSDOM('<!doctype html><body></body>', {runScripts:'outside-only', url:'http://localhost'});
  t.after(() => dom.window.close());
  dom.window.eval(source);
  const element = dom.window.document.createElement('declan-two-native-panel');
  const calls = [];
  element._hass = {callApi:async (...args) => {
    calls.push(args);
    if (response instanceof Error) throw response;
    return response;
  }};
  return {element, root:element.shadowRoot, calls};
}
function report() {
  return {read_only:true, generated_at:'2026-11-16T11:00:00Z', gaps:[],
    summary:{scripts:1, automations:0, entities:1, error:1, warning:0, unverified:0},
    routines:[{entity_id:'script.dinner', name:'<img src=x onerror=alert(1)>', state:'off',
      fingerprint:'a'.repeat(64), reviewed:false,
      dependencies:[{kind:'entity',id:'light.dining'}],
      findings:[{severity:'error',code:'missing_entity',path:'config.sequence[0]',recommendation:'Review light.dining in HA.'}],
      executions:[{run_id:'abc',status:'failed',start:'2026-11-16',last_step:'sequence/0'}]}],
    entities:[{entity_id:'light.dining',name:'Dining',state:'unavailable'}]};
}

function responseProfile() {
  return Object.fromEntries(['requested', 'completed', 'failure'].map(phase => [phase,
    Object.fromEntries(['sass', 'guest'].map(mode => [mode,
      {default: phase === 'requested' ? [`${mode} response <img src=x>`] : [], start: [], end: [], toggle: []}]))]));
}

test('training loads actual linked replies and permits explicit teaching of older unlinked recordings', async t => {
  const {element, root, calls} = panel(t, {});
  const now = new Date().toISOString();
  element._hass.callApi = async (...args) => {
    calls.push(args);
    if (args[0] === 'POST') return {saved:true};
    if (args[1].includes('recording_ids=')) return {links:{linked:77}, turns:{77:{message:'study light on it', reply:'Could you say it another way?'}}};
    if (args[1] === 'declan_two/history') return {turns:[{id:77, recording_id:'linked', created_at:now,
      message:'office light on it', reply:'Could you say it another way?'},
      {id:78, recording_id:'', created_at:now, message:'typed request', reply:'A saved reply'}], next:null};
    if (args[1].includes('history=1')) return {interactions:[]};
    return {profiles:[], interactions:[{id:'linked', transcript:'office light on it',recorded_at:now},
      {id:'old',transcript:'study light on it',recorded_at:now}]};
  };
  await element.loadTimeline();
  assert.equal(root.querySelectorAll('.timeline-entry').length, 3);
  const cards = [...root.querySelectorAll('.timeline-row')];
  assert.match(cards[0].textContent, /Could you say it another way/);
  assert.match(cards[0].textContent, /Training phrase: study light on it/);
  assert.match(cards[1].textContent, /No response was saved/);
  const form = cards[1].querySelector('.training-form');
  const input = form.querySelector('input');
  assert.equal(input.disabled, false);
  assert.equal(form.querySelector('label').textContent, 'The command you meant');
  input.value = 'turn study light on';
  form.querySelector('button').click();
  await new Promise(resolve => setImmediate(resolve));
  const post = calls.find(args => args[0] === 'POST');
  assert.deepEqual(JSON.parse(JSON.stringify(post[2])), {recording_id:'old',target:'turn study light on'});
  assert.match(cards[1].textContent, /Command learned/);
  assert.equal(root.querySelector('.training-form input').maxLength, 120);
});

test('conversation teaching remains available when both voice review sources fail', async t => {
  const {element, root} = panel(t, {});
  element._hass.callApi = async (method, path) => {
    if (path === 'declan_two/history') return {turns:[{id:5,created_at:new Date().toISOString(),
      message:'a keyboard command',reply:'saved response'}],next:null};
    throw new Error('VoicePipeline offline');
  };
  await element.loadTimeline();
  assert.equal(root.querySelectorAll('.timeline-entry').length,1);
  assert.equal(root.querySelector('.training-form input').disabled,false);
  assert.equal(root.querySelector('.timeline-subsection').hidden,true);
  assert.match(root.querySelector('.timeline-status').textContent,/2 source/);
});

test('a response-link loading failure is visible and a successful refresh populates the saved reply', async t => {
  const {element, root} = panel(t, {});
  let failed=true;
  const recorded_at=new Date().toISOString();
  element._hass.callApi=async (method,path) => {
    if (path.includes('recording_ids=')) {
      if (failed) throw new Error('Backend rejected authentication');
      return {links:{clip:77},turns:{77:{message:'office light on',reply:'The actual saved reply.'}}};
    }
    if (path==='declan_two/history') return {turns:[],next:null};
    if (path.includes('history=1')) return {interactions:[]};
    return {profiles:[],interactions:[{id:'clip',transcript:'office light on',recorded_at}]};
  };
  await element.loadTimeline();
  assert.match(root.querySelector('.timeline-row').textContent,/Could not load saved responses/);
  assert.doesNotMatch(root.querySelector('.timeline-row').textContent,/No response was saved/);
  assert.match(root.querySelector('.timeline-status').textContent,/1 source/);
  failed=false;
  await element.loadTimeline();
  assert.match(root.querySelector('.timeline-row').textContent,/The actual saved reply/);
  assert.doesNotMatch(root.querySelector('.timeline-status').textContent,/source.*unavailable/);
});

test('voice retry waits for the spoken prompt and cancellation prevents a late restart', async t => {
  const {element, root} = panel(t, {reply:'Could you say it another way?',session_id:'retry',continue_conversation:true});
  Object.defineProperty(element,'isConnected',{value:true});
  const win = element.ownerDocument.defaultView;
  let utterance;
  win.SpeechSynthesisUtterance = class {constructor(text) {this.text = text;}};
  win.speechSynthesis = {speak(value){utterance=value;},cancel(){}};
  let restarts = 0;
  element.startMicrophone = async options => {assert.equal(options.followUp,true); restarts++;};
  root.querySelector('#native-chat-input').value = 'office light on it';
  element._voiceTranscript = 'office light on it';
  await element.sendChat();
  assert.equal(restarts,0);
  assert.equal(utterance.text,'Could you say it another way?');
  utterance.onend();
  assert.equal(restarts,1);
  element.cancelMicrophone();
  utterance.onend();
  assert.equal(restarts,1);
});

test('a silent follow-up closes the microphone after ten seconds without sending a command', async t => {
  const {element, root, calls} = panel(t, {});
  Object.defineProperty(element,'isConnected',{value:true});
  const win = element.ownerDocument.defaultView;
  let stopped=0, closed=0, expiry;
  win.setTimeout = (callback, milliseconds) => {assert.equal(milliseconds,10000); expiry=callback; return 1;};
  win.clearTimeout = () => {};
  Object.defineProperty(win.navigator,'mediaDevices',{value:{getUserMedia:async () => ({getTracks:() => [{stop(){stopped++;}}]})}});
  win.AudioContext = class {
    destination = {};
    resume = async () => {};
    close = async () => {closed++;};
    createMediaStreamSource = () => ({connect(){},disconnect(){}});
    createScriptProcessor = () => ({connect(){},disconnect(){}});
  };
  await element.startMicrophone({followUp:true});
  assert.equal(root.querySelector('.mic-stop').textContent,'Stop listening');
  expiry();
  assert.equal(stopped,1);
  assert.equal(closed,1);
  assert.equal(element._micStream,null);
  assert.equal(calls.length,0);
  assert.match(root.querySelector('.mic-status').textContent,/No response received/);
});

test('routine response editor safely edits adds deletes and saves only the selected routine', async t => {
  const {element, root, calls} = panel(t, {});
  const data = responseProfile();
  element._hass.callApi = async (...args) => {
    calls.push(args);
    if (args[0] === 'GET') return {routines: [{entity_id:'script.morning', name:'Morning <img src=x>'}]};
    return args[2].profile ? {saved:true, expected:'b'.repeat(64)} : {profile:data, expected:'a'.repeat(64)};
  };
  await element.loadResponseRoutines();
  root.querySelector('.responses-routine').value = 'script.morning';
  await element.chooseResponseRoutine();
  assert.equal(root.querySelector('.responses-editor img'), null);
  assert.ok([...root.querySelectorAll('.responses-editor details')].every(row => !row.open));
  const input = root.querySelector('.responses-editor textarea');
  input.value = 'Edited sass'; input.dispatchEvent(new input.ownerDocument.defaultView.Event('input'));
  const tone = input.closest('details');
  [...tone.querySelectorAll('button')].find(button => button.textContent === 'Add response').click();
  const added = [...tone.querySelectorAll('textarea:not(.responses-bulk-input)')].at(-1);
  added.value = 'Added sass'; added.dispatchEvent(new added.ownerDocument.defaultView.Event('input'));
  tone.querySelector('button').click();
  await element.saveResponses();
  const payload = calls.at(-1)[2];
  assert.equal(payload.entity_id, 'script.morning');
  assert.deepEqual([...payload.profile.requested.sass.default], ['Added sass']);
  assert.deepEqual([...payload.profile.requested.guest.default], ['guest response <img src=x>']);
  assert.match(root.querySelector('.responses-status').textContent, /saved/);
  assert.equal(element._responsesDirty, false);
  const secondEdit = root.querySelector('.responses-editor textarea');
  secondEdit.value = 'Second edit after saving';
  secondEdit.dispatchEvent(new secondEdit.ownerDocument.defaultView.Event('input'));
  await element.saveResponses();
  assert.equal(calls.at(-1)[2].profile.requested.sass.default[0], 'Second edit after saving');
});

test('bulk response paste appends individual editable lines only to the selected tone and action', async t => {
  const {element, root, calls} = panel(t, {saved:true, expected:'b'.repeat(64)});
  element._responseProfile = responseProfile(); element._responseEntity = 'script.morning'; element._responseExpected = 'a'.repeat(64);
  element.renderResponseEditor();
  const bulk = root.querySelector('.responses-bulk-input'); const tone = bulk.closest('details').parentElement;
  tone.querySelector('select').value = 'end';
  bulk.value = JSON.stringify(['First line, with a comma.', 'A "quoted" response', ' First line, with a comma. ', '<img src=x>']);
  tone.querySelector('.responses-import').click();
  assert.deepEqual([...element._responseProfile.requested.sass.end], ['First line, with a comma.', 'A "quoted" response', '<img src=x>']);
  assert.equal(element._responseProfile.requested.sass.default.length, 1);
  assert.equal(element._responseProfile.requested.guest.end.length, 0);
  assert.equal(tone.querySelectorAll('textarea:not(.responses-bulk-input)').length, 3);
  assert.equal(root.querySelector('.responses-editor img'), null);
  assert.match(tone.querySelector('.responses-import-status').textContent, /3 responses added to end. 1 duplicates skipped/);
  assert.equal(calls.length, 0);
  await element.saveResponses();
  assert.equal(calls.at(-1)[2].profile.requested.sass.end.length, 3);
});

test('bulk paste accepts brace lists and skips existing responses without losing edits', async t => {
  const {element, root} = panel(t, {});
  element._responseProfile = responseProfile(); element.renderResponseEditor();
  const bulk = root.querySelector('.responses-bulk-input'); const tone = bulk.closest('details').parentElement;
  bulk.value = '{"sass response <img src=x>", "New response", "New response"}';
  tone.querySelector('.responses-import').click();
  assert.deepEqual([...element._responseProfile.requested.sass.default], ['sass response <img src=x>', 'New response']);
  assert.match(tone.querySelector('.responses-import-status').textContent, /1 responses added.*2 duplicates skipped/);
  assert.equal(element._responsesDirty, true);
  assert.equal(bulk.value, '');
});

test('invalid bulk imports are atomic, preserve pasted text and make no server calls', async t => {
  const {element, root, calls} = panel(t, {});
  element._responseProfile = responseProfile(); element.renderResponseEditor();
  const before = JSON.stringify(element._responseProfile);
  const bulk = root.querySelector('.responses-bulk-input'); const tone = bulk.closest('details').parentElement;
  for (const source of ['not json', '{"key":"value"}', '[]', '[1]', '["valid", " "]', '["x", null]', JSON.stringify(['x'.repeat(1001)]), JSON.stringify(['bad\u0000text']), JSON.stringify(Array.from({length:100}, (_, i) => `new ${i}`))]) {
    bulk.value = source; tone.querySelector('.responses-import').click();
    assert.equal(JSON.stringify(element._responseProfile), before);
    assert.equal(bulk.value, source);
    assert.equal(Boolean(element._responsesDirty), false);
    assert.ok(tone.querySelector('.responses-import-status').textContent.length);
  }
  assert.equal(calls.length, 0);
});

test('response save failure retains edits and permits retry; blank lists are valid', async t => {
  const {element, root} = panel(t, {});
  element._responseEntity = 'script.morning';
  element._responseExpected = 'a'.repeat(64);
  element._responseProfile = responseProfile();
  element._responseProfile.requested.sass.default = [];
  element._responsesDirty = true;
  element.renderResponseEditor();
  element._hass.callApi = async () => { throw {body:{error:'Responses changed elsewhere. Reload before saving.'}}; };
  await element.saveResponses();
  assert.match(root.querySelector('.responses-status').textContent, /changed elsewhere/);
  assert.equal(element._responsesDirty, true);
  assert.equal(root.querySelector('.responses-save').disabled, false);
  assert.equal(element._responseProfile.requested.sass.default.length, 0);
});

test('response editor prevents a routine switch with unsaved edits and blocks duplicate loads', async t => {
  const {element, root, calls} = panel(t, {});
  root.querySelector('.responses-routine').append(new root.ownerDocument.defaultView.Option('Morning', 'script.morning'));
  element._responseEntity = 'script.morning'; element._responsesDirty = true;
  root.ownerDocument.defaultView.confirm = () => false;
  await element.chooseResponseRoutine();
  assert.equal(root.querySelector('.responses-routine').value, 'script.morning');
  assert.equal(calls.length, 0);
  element._responsesPending = true;
  await element.loadResponseRoutines(); await element.saveResponses();
  assert.equal(calls.length, 0);
});

test('response editor rejects blank and duplicate lines before sending a save', async t => {
  const {element, root, calls} = panel(t, {});
  element._responseProfile = responseProfile();
  element._responseProfile.completed.sass.default = [''];
  await element.saveResponses();
  assert.match(root.querySelector('.responses-status').textContent, /blank or duplicate/);
  element._responseProfile.completed.sass.default = ['Duplicate', ' Duplicate '];
  await element.saveResponses();
  assert.equal(calls.length, 0);
});

test('background partial outcomes and steps remain inspectable without speaking', async t => {
  const data = report();
  data.routines[0].background_result = {job_id:'declan-job1',outcome:'partial',updated_at:'2026-11-16',
    reason:'projector_unavailable',steps:[{target:'<img src=x>',status:'unavailable'}]};
  const {element,root,calls} = panel(t, data);
  await element.loadHAAudit();
  const text = root.querySelector('.audit-results').textContent;
  assert.match(text,/Background request declan-job1: partial/);
  assert.match(text,/projector_unavailable/);
  assert.match(text,/<img src=x>: unavailable/);
  assert.equal(root.querySelector('.audit-results img'),null);
  assert.equal(calls.length,1);
});

test('native audit loads only through authenticated GET and renders safe collapsed findings', async t => {
  const {element,root,calls} = panel(t, report());
  await element.loadHAAudit();
  assert.deepEqual(calls, [['GET','declan_two/ha-audit']]);
  assert.match(root.querySelector('.audit-status').textContent, /1 errors/);
  assert.match(root.querySelector('.audit-results').textContent, /missing_entity/);
  assert.match(root.querySelector('.audit-results').textContent, /Run abc: failed/);
  assert.equal(root.querySelector('.audit-results img'), null);
  assert.ok([...root.querySelectorAll('.audit-results details')].every(item => !item.open));
  assert.equal(root.querySelector('.audit-refresh').disabled, false);
});

test('audit searches inventory and findings without another request', async t => {
  const {element,root,calls} = panel(t, report());
  await element.loadHAAudit();
  root.querySelector('.audit-search').value = 'missing_entity';
  element.renderHAAudit();
  assert.match(root.querySelector('.audit-results').textContent, /Scripts & automations \(1\)/);
  assert.match(root.querySelector('.audit-results').textContent, /Entities \(0\)/);
  assert.equal(calls.length,1);
});

test('refresh failure removes stale findings and restores refresh button', async t => {
  const {element,root} = panel(t, report());
  await element.loadHAAudit();
  element._hass.callApi = async () => {throw new Error('403');};
  await element.loadHAAudit();
  assert.equal(root.querySelector('.audit-results').textContent,'');
  assert.equal(element._auditReport,null);
  assert.match(root.querySelector('.audit-status').textContent,/Audit unavailable/);
  assert.equal(root.querySelector('.audit-refresh').disabled,false);
});

test('duplicate refreshes are coalesced and navigation selects the audit page', async t => {
  const {element,root,calls} = panel(t, report());
  let finish;
  element._hass.callApi = () => new Promise(resolve => {finish = resolve;});
  const pending = element.loadHAAudit();
  await element.loadHAAudit();
  assert.equal(root.querySelector('.audit-refresh').disabled,true);
  finish(report());
  await pending;
  element._hass = null;
  element.selectTab('audit');
  assert.equal(root.querySelector('#panel-audit').hidden,false);
  assert.equal(root.querySelector('#panel-overview').hidden,true);
  assert.equal(calls.length,0);
});

test('audit failures distinguish missing route, permissions, collector errors and connectivity', async t => {
  const {element,root} = panel(t, report());
  for (const [code, message] of [[401,/session has expired/], [403,/administrator access is required/],
    [404,/Restart Home Assistant/], [503,/audit collector failed/], [500,/Check its logs/], [0,/connection and retry/]]) {
    element._hass.callApi = async () => {throw {status_code:code, message:'private-token-do-not-display'};};
    await element.loadHAAudit();
    assert.match(root.querySelector('.audit-status').textContent, message);
    assert.doesNotMatch(root.querySelector('.audit-status').textContent,/private-token/);
    if (code) assert.match(root.querySelector('.audit-status').textContent,new RegExp('HTTP ' + code));
    assert.equal(element._auditReport,null);
    assert.equal(root.querySelector('.audit-refresh').disabled,false);
  }
});

test('reviewed routines disappear from Unreviewed and can be reopened from Reviewed', async t => {
  const {element,root,calls} = panel(t, report());
  await element.loadHAAudit();
  const item = element._auditReport.routines[0];
  element._hass.callApi = async (...args) => {
    calls.push(args);
    return {entity_id:item.entity_id,reviewed:args[2].reviewed,reviewed_at:'2026-11-16'};
  };
  const checkbox = root.querySelector('.audit-results input[type="checkbox"]');
  checkbox.checked = true;
  await element.setAuditReviewed(item,checkbox);
  assert.match(root.querySelector('.audit-results').textContent,/Scripts & automations \(0\)/);
  assert.equal(calls[1][0],'POST');
  assert.equal(calls[1][1],'declan_two/ha-audit/reviews');
  assert.equal(calls[1][2].fingerprint,'a'.repeat(64));
  root.querySelector('.audit-review-filter').value = 'reviewed';
  element.renderHAAudit();
  assert.match(root.querySelector('.audit-results').textContent,/Reviewed/);
  const undo = root.querySelector('.audit-results input[type="checkbox"]');
  undo.checked = false;
  await element.setAuditReviewed(item,undo);
  assert.equal(item.reviewed,false);
});

test('failed or stale review save preserves the prior review flag', async t => {
  const {element,root} = panel(t, report());
  await element.loadHAAudit();
  const item = element._auditReport.routines[0];
  const checkbox = root.querySelector('.audit-results input[type="checkbox"]');
  element._hass.callApi = async () => {throw {status_code:409};};
  checkbox.checked = true;
  await element.setAuditReviewed(item,checkbox);
  assert.equal(item.reviewed,false);
  assert.equal(checkbox.checked,false);
  assert.equal(checkbox.disabled,false);
  assert.match(root.querySelector('.audit-status').textContent,/routine changed/);
});

test('reviewing a searched routine retains other reviews and clearing search reveals them', async t => {
  const data = report();
  data.routines = ['Movie Time','Good Morning','Good Night'].map((name,index) => ({...data.routines[0],
    name,entity_id:'script.routine_' + index,reviewed:index < 2,reviewed_at:index < 2 ? 'earlier' : null}));
  const {element,root} = panel(t,data);
  await element.loadHAAudit();
  root.querySelector('.audit-search').value = 'good night';
  element.renderHAAudit();
  element._hass.callApi = async (method,path,body) => ({...body,reviewed_at:'now'});
  const checkbox = root.querySelector('.audit-results input[type="checkbox"]');
  checkbox.checked = true;
  await element.setAuditReviewed(data.routines[2],checkbox);
  root.querySelector('.audit-review-filter').value = 'reviewed';
  element.renderHAAudit();
  assert.ok(data.routines.every(item => item.reviewed));
  assert.match(root.querySelector('.audit-filter-status').textContent,/3 reviewed, 0 unreviewed/);
  assert.match(root.querySelector('.audit-filter-status').textContent,/Search is active/);
  assert.match(root.querySelector('.audit-results').textContent,/Scripts & automations \(1\)/);
  root.querySelector('.audit-search-clear').click();
  assert.equal(root.querySelector('.audit-search').value,'');
  assert.match(root.querySelector('.audit-results').textContent,/Scripts & automations \(3\)/);
  assert.equal(root.querySelector('.audit-search-clear').hidden,true);
  assert.doesNotMatch(root.querySelector('#panel-audit').textContent,/Reviewed and fixed/);
  assert.equal(root.querySelector('.audit-review-filter option[value="reviewed"]').textContent,'Reviewed');
  element._hass.callApi = async () => data;
  await element.loadHAAudit();
  assert.match(root.querySelector('.audit-results').textContent,/Scripts & automations \(3\)/);
});

test('changed reviews remain checked and visible in Reviewed after refresh', async t => {
  const data = report();
  data.routines = ['Good Morning','Good Night','Movie Time'].map((name,index) => ({...data.routines[0],
    entity_id:'script.reviewed_' + index,name,reviewed:true,review_changed:index < 2,reviewed_at:'original-date'}));
  const {element,root} = panel(t,data);
  await element.loadHAAudit();
  root.querySelector('.audit-review-filter').value = 'reviewed';
  element.renderHAAudit();
  assert.match(root.querySelector('.audit-results').textContent,/Scripts & automations \(3\)/);
  assert.match(root.querySelector('.audit-results').textContent,/Changed since review/);
  assert.ok([...root.querySelectorAll('.audit-results input[type="checkbox"]')].every(box => box.checked));
  await element.loadHAAudit();
  assert.match(root.querySelector('.audit-results').textContent,/Scripts & automations \(3\)/);
  root.querySelector('.audit-review-filter').value = 'unreviewed';
  element.renderHAAudit();
  assert.match(root.querySelector('.audit-results').textContent,/Scripts & automations \(0\)/);
});

test('connection card automatically checks backend releases and opens the Updates page', async t => {
  const {element,root,calls} = panel(t, report());
  element._hass.callApi = async (...args) => {
    calls.push(args);
    if (args[1] === 'declan_two/capabilities') return {compatible:true,status:'connected',server_version:'2.8.1'};
    if (args[0] === 'GET') return {enabled:true,state:'idle',current:'2.8.1'};
    return {current:'2.8.1',versions:['2.8.1','2.10.0','2.9.0']};
  };
  await element.refresh();
  await new Promise(resolve => setImmediate(resolve));
  assert.match(root.querySelector('.overview-update-status').textContent,/Update available: 2.10.0/);
  assert.equal(calls[2][2].operation,'check');
  assert.equal(calls[2][2].include_prereleases,false);
  assert.equal(root.querySelector('.state').textContent,'Declan API connected');
  let selected;
  element.selectTab = name => {selected = name;};
  root.querySelector('.overview-update-open').click();
  assert.equal(selected,'updates');
  assert.ok(calls.every(args => args[2]?.operation !== 'install'));
});

test('connection update badge distinguishes current, old and prerelease versions', t => {
  const {element,root} = panel(t, report());
  element.renderConnectionUpdates({current:'v2.8.1',versions:['2.8.1','2.7.10','2.8.1-rc.1']});
  assert.match(root.querySelector('.overview-update-status').textContent,/up to date/);
  element.renderConnectionUpdates({current:'2.8.1-rc.9',versions:['2.8.1-rc.10']});
  assert.match(root.querySelector('.overview-update-status').textContent,/Update available/);
  element.renderConnectionUpdates({current:'2.8.1-rc.10',versions:['2.8.1']});
  assert.match(root.querySelector('.overview-update-status').textContent,/Update available/);
  element.renderConnectionUpdates({current:'unknown',versions:[]});
  assert.match(root.querySelector('.overview-update-status').textContent,/Could not determine/);
});

test('connection card skips release discovery during installation or when updater is disabled', async t => {
  const {element,root,calls} = panel(t, report());
  for (const state of [{enabled:true,state:'installing'}, {enabled:true,state:'restarting'}, {enabled:false,state:'idle'}]) {
    element._hass.callApi = async (...args) => {calls.push(args);return state;};
    await element.checkConnectionUpdates();
    assert.equal(root.querySelector('.overview-update-check').disabled,false);
  }
  assert.equal(calls.length,3);
  assert.ok(calls.every(args => args[0] === 'GET'));
});

test('connection-card check failure keeps API status and restores retry control', async t => {
  const {element,root} = panel(t, report());
  root.querySelector('.state').textContent = 'Declan API connected';
  element._hass.callApi = async () => {throw new Error('offline');};
  await element.checkConnectionUpdates();
  assert.match(root.querySelector('.overview-update-status').textContent,/Update check unavailable/);
  assert.equal(root.querySelector('.state').textContent,'Declan API connected');
  assert.equal(root.querySelector('.overview-update-check').disabled,false);
});

test('release checks populate the backend picker and leave the audit filter intact', async t => {
  const {element,root,calls} = panel(t,{current:'2.8.2',versions:['2.8.3','2.8.2']});
  const audit = root.querySelector('.audit-review-filter');
  audit.value = 'reviewed';
  const original = [...audit.options].map(option => option.value);
  await element.checkUpdates();
  const releases = root.querySelector('#panel-updates .updates-select');
  assert.deepEqual([...releases.options].map(option => option.value),['2.8.3','2.8.2']);
  assert.equal(releases.value,'2.8.3');
  assert.equal(root.querySelector('.updates-install').disabled,false);
  assert.deepEqual([...audit.options].map(option => option.value),original);
  assert.equal(audit.value,'reviewed');
  assert.equal(calls[0][2].operation,'check');
  element._hass.callApi = async (...args) => {calls.push(args);return {};};
  element.loadUpdateStatus = async () => {};
  root.querySelector('.update-prereleases').checked = true;
  element.ownerDocument.defaultView.confirm = () => true;
  await element.installUpdate();
  assert.equal(calls[1][2].version,'2.8.3');
  assert.equal(calls[1][2].operation,'install');
});

test('prerelease changes reset only the release picker and status cannot enable a placeholder', async t => {
  const {element,root} = panel(t,{enabled:true,state:'idle',current:'2.8.2'});
  const audit = root.querySelector('.audit-review-filter');
  audit.value = 'all';
  await element.loadUpdateStatus();
  assert.equal(root.querySelector('.updates-install').disabled,true);
  root.querySelector('.update-prereleases').dispatchEvent(new element.ownerDocument.defaultView.Event('change'));
  assert.equal(audit.value,'all');
  assert.equal(audit.options.length,3);
  assert.equal(root.querySelector('#panel-updates .updates-select').value,'');
  assert.equal(root.querySelector('.updates-install').disabled,true);
});

test('routine YAML download uses the current HA endpoint and downloads the returned YAML', async t => {
  const data = report();
  data.routines[0].yaml_available = true;
  const {element,root,calls} = panel(t,data);
  await element.loadHAAudit();
  const win = element.ownerDocument.defaultView;
  let blob,download;
  win.URL.createObjectURL = value => {blob = value;return 'blob:test-yaml';};
  win.URL.revokeObjectURL = () => {};
  win.HTMLAnchorElement.prototype.click = function() {download = this.download;};
  element._hass.callApi = async (...args) => {
    calls.push(args);
    return {entity_id:'script.dinner',yaml:'alias: Current dinner\nsequence: []\n'};
  };
  const button = root.querySelector('.audit-yaml-download');
  await element.downloadAuditYaml(element._auditReport.routines[0],button);
  assert.equal(calls[1][0],'GET');
  assert.equal(calls[1][1],'declan_two/ha-audit/yaml?entity_id=script.dinner');
  assert.equal(download,'script.dinner.yaml');
  assert.equal(blob.type,'application/yaml;charset=utf-8');
  assert.match(root.querySelector('.audit-status').textContent,/Downloaded the current loaded/);
  assert.equal(button.disabled,false);
});

test('stale routines have no YAML download and failed exports restore retry control', async t => {
  const {element,root} = panel(t,report());
  await element.loadHAAudit();
  assert.equal(root.querySelector('.audit-yaml-download'),null);
  element._hass.callApi = async () => {throw {status_code:404};};
  const button = element.ownerDocument.createElement('button');
  await element.downloadAuditYaml(element._auditReport.routines[0],button);
  assert.match(root.querySelector('.audit-status').textContent,/Could not download YAML/);
  assert.equal(button.disabled,false);
});

test('stale records are hidden by default in both audit groups and can be shown explicitly', async t => {
  const data = report();
  data.routines.push({entity_id:'script.old',name:'Old Dinner',state:'unavailable',stale:true,findings:[]});
  data.entities.push({entity_id:'script.old',name:'Old Dinner',state:'unavailable',stale:true});
  const {element,root} = panel(t,data);
  await element.loadHAAudit();
  assert.equal(root.querySelector('.audit-show-stale').checked,false);
  assert.doesNotMatch(root.querySelector('.audit-results').textContent,/Old Dinner/);
  root.querySelector('.audit-show-stale').checked = true;
  root.querySelector('.audit-show-stale').dispatchEvent(new element.ownerDocument.defaultView.Event('change'));
  assert.match(root.querySelector('.audit-results').textContent,/Old Dinner/);
  assert.match(root.querySelector('.audit-results').textContent,/Stale entity record/);
});

test('Edit YAML navigates to the persistent native script editor without writing configuration', async t => {
  const data = report();
  data.routines[0].editor_path = '/config/script/edit/original_script_key';
  const {element,root,calls} = panel(t,data);
  await element.loadHAAudit();
  const win = element.ownerDocument.defaultView;
  let navigated = false;
  win.addEventListener('location-changed', () => {navigated = true;});
  const button = root.querySelector('.audit-yaml-edit');
  assert.equal(button.textContent,'Edit YAML');
  assert.match(button.title,/three-dot menu/);
  button.click();
  assert.equal(win.location.pathname,'/config/script/edit/original_script_key');
  assert.equal(navigated,true);
  assert.equal(calls.length,1);
  assert.equal(calls[0][0],'GET');
});

test('stale records and invalid editor paths cannot navigate', async t => {
  const data = report();
  data.routines[0].editor_path = 'https://example.invalid/';
  const {element,root} = panel(t,data);
  await element.loadHAAudit();
  assert.equal(root.querySelector('.audit-yaml-edit'),null);
  element.openAuditEditor({editor_path:'/config/script/edit/test',stale:true});
  element.openAuditEditor({editor_path:'https://example.invalid/'});
  assert.equal(element.ownerDocument.defaultView.location.pathname,'/');
});



test('everyday responses load beside routines and keep bulk edits isolated to their category', async t => {
  const {element, root, calls} = panel(t, {});
  const data = responseProfile();
  for (const mode of ['sass', 'guest']) { data.completed[mode].default = [mode + ' light line']; data.requested[mode].default = []; }
  element._hass.callApi = async (...args) => {
    calls.push(args);
    if (args[0] === 'GET') return {commands:[{entity_id:'command:lights_on',name:'Lights: turn on'}],routines:[],routine_error:'HA offline'};
    return args[2].profile ? {saved:true,expected:'b'.repeat(64)} : {profile:data,expected:'a'.repeat(64)};
  };
  await element.loadResponseRoutines();
  assert.equal(root.querySelector('optgroup').label,'Everyday commands');
  assert.match(root.querySelector('.responses-status').textContent,/Everyday commands are available/);
  root.querySelector('.responses-routine').value='command:lights_on';
  await element.chooseResponseRoutine();
  assert.equal(root.querySelectorAll('.responses-editor > details').length,2);
  assert.match(root.querySelector('.responses-editor').textContent,/factual result is always kept/);
  const bulk=root.querySelector('.responses-bulk-input');
  bulk.value='["Added light line","Added light line"]';
  bulk.closest('details').querySelector('button').click();
  await element.saveResponses();
  const payload=calls.at(-1)[2];
  assert.equal(payload.entity_id,'command:lights_on');
  assert.deepEqual([...payload.profile.completed.sass.default],['sass light line','Added light line']);
  assert.deepEqual([...payload.profile.completed.guest.default],['guest light line']);
  assert.ok([...root.querySelectorAll('.responses-editor details')].every(row=>!row.open));
});
