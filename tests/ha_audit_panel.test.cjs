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
  assert.match(root.querySelector('.audit-results').textContent,/Reviewed and fixed/);
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
