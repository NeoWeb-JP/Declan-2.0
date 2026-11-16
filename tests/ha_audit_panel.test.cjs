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
