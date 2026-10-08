// Synthetic API fixtures; no account data or live requests.
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {expression} from '../ptty-skill/scripts/ptty_readonly.mjs';

const event = ['SS', '000101', 'XX', '000001'].join('');
function fixture(counts = [13, 21, 23], alter = r => r) {
  const calls = [], previous = {}, total = counts.reduce((a, b) => a + b, 0);
  const location = {protocol: 'https:', hostname: 'www.ptty.com.cn', port: '', pathname: '/', hash: '#/trialScGlIndex?ssid=SYNTHETIC'};
  const v = {$options: {name: 'TrialSsBpIndex'}, op: 'scGl', ssid: 'SYNTHETIC', search: 'stale filter', tableData: [],
    utilPost: {paramData: previous, async sendPost() {
      const q = JSON.parse(JSON.stringify(this.paramData)); calls.push(q);
      assert.equal(q.headerData.op, 'scGl');
      const p = q.busData.xmid;
      const r = q.headerData.methodName === 'mainLoadData' ? {
        isSuccess: true, content: counts.map((n, i) => ({SSID: event, XMID: 'P' + i, ZCS: n})),
        lsData: {zcsCount: total, ywcCount: 0, wwcCount: total, jxzCount: 0}
      } : {isSuccess: true, content: Array.from({length: counts[Number(p.slice(1))]}, (_, i) => ({SSID: event, XMID: p, CCH: p + '-' + i, JD: 1}))};
      return alter(r, q, calls.length, v, location);
    }}};
  const context = {location, URLSearchParams, document: {body: {innerText: event + '/Synthetic event'}, querySelectorAll: () => [{__vue__: v}]}};
  return {calls, v, previous, context, run: () => vm.runInNewContext(expression({event, action: 'matches'}), context)};
}

test('empty filtered UI is ignored; full inventory returns all 57 matches', async () => {
  const f = fixture(), r = await f.run();
  assert.equal(r.match_count, 57); assert.equal(r.matches_present, true); assert.equal(r.complete, true);
  assert.equal(f.v.search, 'stale filter'); assert.equal(f.v.utilPost.paramData, f.previous);
  assert.equal(f.calls.length, 5);
  for (const q of f.calls.filter(q => q.headerData.methodName === 'mainLoadData')) assert.equal(q.busData.search.xmqc, '');
  assert(f.calls.every(q => ['mainLoadData', 'getDwInfo'].includes(q.headerData.methodName)));
});
test('successful consistent empty inventory alone reports zero matches', async () => {
  const r = await fixture([]).run(); assert.equal(r.match_count, 0); assert.equal(r.matches_present, false);
});
test('failed or malformed reads never become empty inventory and restore request', async () => {
  for (const change of [r => ({...r, isSuccess: false}), r => ({...r, content: ''}), r => ({...r, lsData: {}})]) {
    const f = fixture([], change); await assert.rejects(f.run()); assert.equal(f.v.utilPost.paramData, f.previous);
  }
});
test('missing project page cannot pass summary totals check', async () => {
  const f = fixture([2, 3], (r, q) => q.headerData.methodName === 'mainLoadData' ? {...r, content: r.content.slice(0, 1)} : r);
  await assert.rejects(f.run(), /incomplete/);
});
test('detail count discrepancy is rejected', async () => {
  const f = fixture([2], (r, q) => q.headerData.methodName === 'getDwInfo' ? {...r, content: r.content.slice(0, 1)} : r);
  await assert.rejects(f.run(), /detail count/);
});
test('wrong event or repeated match IDs fail acceptance', async () => {
  for (const key of ['SSID', 'CCH']) {
    const f = fixture([2], (r, q) => {
      if (q.headerData.methodName === 'getDwInfo') r.content.forEach(m => {m[key] = 'same-invalid-value';});
      return r;
    });
    await assert.rejects(f.run(), /identity/);
  }
});
test('changed totals during read require refresh', async () => {
  const f = fixture([2], (r, q, n) => {
    if (n === 3) {r.lsData.ywcCount = 1; r.lsData.wwcCount = 1;}
    return r;
  });
  await assert.rejects(f.run(), /changed/);
});
test('same-name component on scheduling page must not receive match queries', async () => {
  const f = fixture(); f.context.location.hash = '#/trialSsBpIndex';
  await assert.rejects(f.run(), /route/); assert.equal(f.calls.length, 0);
});
test('event navigation during read aborts without further queries', async () => {
  const f = fixture([2], (r, q, n, v, location) => {if (n === 1) location.hash = '#/index'; return r;});
  await assert.rejects(f.run(), /event changed/); assert.equal(f.calls.length, 1);
});
test('subset query is rejected for whole-event existence checks', () => {
  assert.throws(() => expression({event, action: 'matches', projectIds: ['XM' + '000101' + 'XX' + '000001']}), /whole event/);
});
test('same-route navigation with stale component must be refreshed', async () => {
  const f = fixture(); f.context.location.hash = '#/trialScGlIndex?ssid=OTHER';
  await assert.rejects(f.run(), /stale event/); assert.equal(f.calls.length, 0);
});
