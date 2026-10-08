import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {expression, CONFIRM, dialogDecision, validateOptions} from '../ptty-skill/scripts/ptty_grid.mjs';

const options = {event: 'SS000000X0001', apply: true,
  grid: [{date: '2030-01-01', time: '09:00', courts: ['1', '2']}]};
function fixture({exists = false, scheduled = 0, complete = true, wrongTime = false, buttonMissing = false,
                  quick = true, rejected = false, stale = false} = {}) {
  const records = [], saved = {}, state = {exists};
  const rows = () => state.exists ? [{RQ: '2030-01-01', STARTTIME: wrongTime ? '10:00' : '09:00', CXH: 1,
    '第1号场地': '无', '第2号场地': '无'}] : [];
  const v = {$options: {name: 'TrialSsBpIndex'}, op: 'bpGl', ssid: stale ? 'stale' : 'synthetic',
    isGly: true, activeName: quick ? 'KSBP' : 'ALLBP', $nextTick: async () => {}};
  v.utilPost = {paramData: saved, async sendPost() {
    const p = this.paramData; records.push(p.headerData.methodName);
    if (p.headerData.methodName === 'createBp') {
      assert.deepEqual(JSON.parse(JSON.stringify(p.busData)), {});
      if (rejected) return {isSuccess: false};
      state.exists = true; return {isSuccess: true};
    }
    return {isSuccess: true, content: rows(), totalNums: complete ? rows().length : 9,
      lsData: {ALLDATA: {ZCS: '4', YBP: String(scheduled), WBP: String(4 - scheduled)}}};
  }};
  const originalPost = v.utilPost.sendPost;
  // Model the observed button handler, including its native confirm and alert.
  const dialogs = {confirmed: false};
  v.createBpHandler = () => {
    records.push('button-handler');
    assert.deepEqual(dialogDecision(dialogs, {type: 'confirm', message: CONFIRM}), {accept: true});
    v.utilPost.paramData = {headerData: {ssid: v.ssid, op: v.op, methodName: 'createBp'}, busData: {}};
    v.utilPost.sendPost().then(() => {
      dialogDecision(dialogs, {type: 'alert', message: 'synthetic response'});
      v.utilPost.paramData = {headerData: {ssid: v.ssid, op: v.op, methodName: 'mainLoadData'}, busData: {}};
      return v.utilPost.sendPost();
    });
  };
  const element = (text, click) => ({textContent: text, disabled: false, getClientRects: () => [1], click});
  const button = element('生成场地数据', () => v.createBpHandler());
  const tab = element('赛事编排数据', () => { records.push('tab-click'); v.activeName = 'ALLBP'; });
  const context = {URL, URLSearchParams, setTimeout, location: {
    protocol: 'https:', hostname: 'www.ptty.com.cn', pathname: '/', port: '',
    href: 'https://www.ptty.com.cn/#/trialSsBpIndex?ssid=synthetic', hash: '#/trialSsBpIndex?ssid=synthetic'},
    document: {body: {innerText: options.event + '/ synthetic'}, querySelectorAll: selector =>
      selector === '*' ? [{__vue__: v}] : selector === '[role="tab"]' ? [tab] : buttonMissing ? [] : [button]}};
  return {records, v, saved, originalPost, run: () => vm.runInNewContext(expression(options), context)};
}

test('clicks data tab and exact generation button, handles confirmation, reads grid before download', async () => {
  const f = fixture(), result = await f.run();
  assert.equal(result.status, 'created'); assert.equal(result.grid_verified, true);
  assert.deepEqual(f.records, ['tab-click', 'mainLoadData', 'button-handler', 'createBp', 'mainLoadData', 'mainLoadData']);
  assert.equal(f.v.utilPost.paramData, f.saved); assert.equal(f.v.utilPost.sendPost, f.originalPost);
});
test('existing grid is reused without generation button or confirm', async () => {
  const f = fixture({exists: true, buttonMissing: true});
  assert.equal((await f.run()).status, 'reused'); assert.ok(!f.records.includes('createBp'));
});
for (const [name, values] of Object.entries({
  'scheduled matches with no grid': {scheduled: 1}, 'incomplete read': {complete: false},
  'missing real button': {buttonMissing: true}, 'stale event component': {stale: true},
  'existing mismatched grid': {exists: true, wrongTime: true}})) {
  test(name + ' fails without generating', async () => {
    const f = fixture(values); await assert.rejects(f.run()); assert.ok(!f.records.includes('createBp'));
  });
}
test('failed generation is not retried and shared request is restored', async () => {
  const f = fixture({rejected: true}); await assert.rejects(f.run());
  assert.equal(f.records.filter(x => x === 'createBp').length, 1);
  assert.equal(f.v.utilPost.paramData, f.saved); assert.equal(f.v.utilPost.sendPost, f.originalPost);
});
test('success toast does not prove expected grid', async () => {
  const f = fixture({wrongTime: true}); await assert.rejects(f.run(), /grid differs/);
  assert.equal(f.records.filter(x => x === 'createBp').length, 1);
});
test('unknown, repeated and unrelated dialogs are never auto-approved', () => {
  const s = {confirmed: false};
  assert.throws(() => dialogDecision(s, {type: 'confirm', message: 'delete matches'}));
  assert.throws(() => dialogDecision(s, {type: 'alert', message: 'unrelated'}));
  assert.deepEqual(dialogDecision(s, {type: 'confirm', message: CONFIRM}), {accept: true});
  assert.throws(() => dialogDecision(s, {type: 'confirm', message: CONFIRM}));
});
test('requires explicit apply and confirmed grid', () => {
  assert.throws(() => validateOptions({...options, apply: false}));
  assert.throws(() => validateOptions({...options, grid: []}));
  assert.throws(() => validateOptions({...options, grid: [...options.grid, ...options.grid]}));
});
