import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {eventsExpression, selectUser, validateOptions} from '../ptty-skill/scripts/ptty_events.mjs';

const user = (id, name, region = 'Synthetic region') => ({RYBH: id, USERNAME: name, DQ: region});
const users = [user('user-a', 'Synthetic A'), user('user-b', 'Synthetic B')];
const location = {protocol: 'https:', hostname: 'www.ptty.com.cn', port: '', pathname: '/',
  href: 'https://www.ptty.com.cn/#/index', hash: '#/index'};
const plain = value => JSON.parse(JSON.stringify(value));

function fixture({total = 12, role = 'MAIN', visible = '1', responseChange} = {}) {
  const calls = [], sentinel = {}, oldRows = [{SSID: 'previous'}];
  const v = {$options: {name: 'Index'}, uis: {rybh: 'login-a', QXBH: role}, ISKY: visible,
    main: {RYDMLIST: users, search: {rybh: 'user-a', ssmc: 'Keep keyword', bszt: 'active', isJs: '', isSf: ''}, tableData: oldRows},
    pageSet: {currentPage: 5, pageSize: 10, totalNums: 77},
    $refs: {tableRef: {doLayout() {}}}, async $nextTick() {},
    utilPost: {paramData: sentinel, async sendPost() {
      const req = plain(this.paramData); calls.push(req);
      assert.deepEqual(req.headerData, {ssid: '', op: 'ssGl', methodName: 'getSsList'});
      const page = req.busData.pageSet.currentPage;
      const result = {isSuccess: true, totalNums: total,
        content: Array.from({length: Math.min(10, Math.max(0, total - (page - 1) * 10))}, (_, i) => ({
          SSID: 'synthetic-event-' + ((page - 1) * 10 + i), SSIDEN: 'synthetic-route',
          SSMC: 'Synthetic tournament', RYBH: req.busData.search.rybh || users[i % 2].RYBH})),
        lsData: {RYDMLIST: users, ISKY: visible, userSize: users.length}};
      return responseChange ? responseChange(result, page, v) : result;
    }}};
  const context = {location: {...location}, URL, document: {querySelectorAll: () => [{__vue__: v}]}};
  return {v, context, calls, sentinel, oldRows, run: o => vm.runInNewContext(eventsExpression(o), context)};
}

test('catalog reads visible users without requests or event ID', async () => {
  const f = fixture(), r = await f.run({action: 'users'});
  assert.equal(r.users.length, 2); assert.equal(f.calls.length, 0); assert.equal(f.v.pageSet.currentPage, 5);
});
test('selection refreshes first page, resets pagination and preserves unrelated filters/login', async () => {
  const f = fixture(), r = await f.run({action: 'list', userLabel: 'Synthetic B（Synthetic region）'});
  assert.equal(r.selected.id, 'user-b'); assert.equal(r.complete, false); assert.equal(r.total, 12);
  assert.equal(f.v.main.search.rybh, 'user-b'); assert.equal(f.v.main.search.ssmc, 'Keep keyword');
  assert.equal(f.v.main.search.bszt, 'active'); assert.equal(f.v.pageSet.currentPage, 1);
  assert.equal(f.v.main.tableData.length, 10); assert.equal(f.v.uis.rybh, 'login-a');
  assert.equal(f.v.utilPost.paramData, f.sentinel);
});
test('all pages are collected once while UI displays page one', async () => {
  const f = fixture({total: 23}), r = await f.run({action: 'list', userId: 'user-b', allPages: true});
  assert.equal(r.complete, true); assert.equal(r.rows.length, 23); assert.equal(r.fetched_pages, 3);
  assert.deepEqual(f.calls.map(r => r.busData.pageSet.currentPage), [1, 2, 3]);
  assert.equal(f.v.main.tableData.length, 10); assert.equal(f.v.pageSet.currentPage, 1);
});
test('all-users selection uses empty filter without changing login', async () => {
  const f = fixture(), r = await f.run({action: 'list', allUsers: true, searchText: ''});
  assert.equal(r.selected.id, ''); assert.equal(r.selected.label, '全部'); assert.equal(r.filters.ssmc, '');
  assert.equal(f.v.uis.rybh, 'login-a');
});
test('empty results are valid only with successful zero total and current catalog', async () => {
  const f = fixture({total: 0}), r = await f.run({action: 'list', userId: 'user-b'});
  assert.equal(r.total, 0); assert.equal(r.complete, true); assert.equal(f.v.main.tableData.length, 0);
});
test('ambiguous names need full label or ID; unknown users are rejected before query', async () => {
  const options = [user('a', 'Synthetic', 'North'), user('b', 'Synthetic', 'South')];
  assert.throws(() => selectUser(options, {userLabel: 'Synthetic'}, 'a'), /ambiguous/);
  assert.equal(selectUser(options, {userLabel: 'Synthetic(South)'}, 'a').id, 'b');
  const f = fixture(); await assert.rejects(f.run({action: 'list', userId: 'not-offered'}));
  assert.equal(f.calls.length, 0);
});
test('hidden dropdown cannot be used for switching even if cached users exist', async () => {
  for (const options of [{role: 'OTHER'}, {visible: '0'}]) {
    const f = fixture(options); assert.equal((await f.run({action: 'users'})).users.length, 0);
    await assert.rejects(f.run({action: 'list', allUsers: true})); assert.equal(f.calls.length, 0);
  }
});
test('a hidden selector still supports the current permitted list', async () => {
  const f = fixture({visible: '0'}); assert.equal((await f.run({action: 'list'})).selected.id, 'user-a');
});
test('failed or malformed responses preserve original UI and restore request object', async () => {
  for (const change of [r => ({...r, isSuccess: false}), r => ({...r, content: 'error'}),
    r => ({...r, totalNums: ''}), r => ({...r, lsData: {}}), r => ({...r, content: []})]) {
    const f = fixture({responseChange: change}); await assert.rejects(f.run({action: 'list', userId: 'user-b'}));
    assert.equal(f.v.main.search.rybh, 'user-a'); assert.equal(f.v.main.tableData, f.oldRows);
    assert.equal(f.v.utilPost.paramData, f.sentinel); assert.equal(f.v.__gamemasterEventsBusy, undefined);
  }
});
test('server ignoring selected owner cannot produce a successful switch', async () => {
  const f = fixture({responseChange: r => {r.content[0].RYBH = 'wrong-owner'; return r;}});
  await assert.rejects(f.run({action: 'list', userId: 'user-b'}), /owner/);
  assert.equal(f.v.main.search.rybh, 'user-a');
});
test('stale user choices are rejected using response catalog', async () => {
  const f = fixture({responseChange: r => {r.lsData.RYDMLIST = [users[0]]; return r;}});
  await assert.rejects(f.run({action: 'list', userId: 'user-b'})); assert.equal(f.v.main.search.rybh, 'user-a');
});
test('duplicate pages, moving totals and page limits cannot claim completeness', async () => {
  for (const change of [(r, page) => {if (page === 2) r.content[0].SSID = 'synthetic-event-0'; return r;},
    (r, page) => {if (page === 2) r.totalNums++; return r;}]) {
    const f = fixture({responseChange: change}); await assert.rejects(f.run({action: 'list', allPages: true}));
    assert.equal(f.v.main.tableData, f.oldRows);
  }
  const f = fixture(); await assert.rejects(f.run({action: 'list', allPages: true, maxPages: 1}), /limit/);
});
test('concurrent login, role, page and filter changes are not overwritten', async () => {
  for (const change of [v => {v.main.search.ssmc = 'new search';}, v => {v.uis.rybh = 'changed-login';},
    v => {v.pageSet.currentPage++;}, v => {v.uis.QXBH = 'OTHER';}]) {
    const f = fixture({responseChange: (r, page, v) => {change(v); return r;}});
    await assert.rejects(f.run({action: 'list', userId: 'user-b'}), /changed/);
    assert.equal(f.v.main.tableData, f.oldRows);
  }
});
test('wrong site/route, unsupported options and mixed selectors rejected', async () => {
  const f = fixture(); f.context.location.hash = '#/trialRmdGlIndex';
  await assert.rejects(f.run({action: 'list'}), /index/); assert.equal(f.calls.length, 0);
  f.context.location.hash = '#/index'; f.context.location.hostname = 'example.invalid';
  await assert.rejects(f.run({action: 'list'}));
  for (const o of [{action: 'delete'}, {action: 'list', userId: 'a', allUsers: true},
    {action: 'list', userId: ''}, {action: 'list', allPages: 'true'}, {action: 'users', userId: 'a'},
    {action: 'list', methodName: 'writeSomething'}]) assert.throws(() => validateOptions(o));
});
