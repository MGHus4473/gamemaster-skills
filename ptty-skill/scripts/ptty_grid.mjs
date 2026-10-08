#!/usr/bin/env node
// Click the actual UI button; no direct createBp request or automatic retry.
import {readFile, writeFile, access} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {assertAdminLocation} from './ptty_readonly.mjs';

export const CONFIRM = '是否重新生成编排？确认后所有的编排数据将被清空，请谨慎操作';

export function validateOptions(o) {
  if (!/^SS[0-9]{6}[A-Z]+[0-9]+$/.test(o.event || '') || o.apply !== true)
    throw Error('explicit event and authorized apply required');
  if (!Array.isArray(o.grid) || !o.grid.length) throw Error('expected grid required');
  const keys = new Set();
  for (const r of o.grid) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(r.date || '') || !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(r.time || '') ||
        !Array.isArray(r.courts) || !r.courts.length || r.courts.some(c => typeof c !== 'string' || !c.trim()) ||
        new Set(r.courts).size !== r.courts.length || keys.has(r.date + ' ' + r.time)) throw Error('invalid expected grid');
    keys.add(r.date + ' ' + r.time);
  }
  return o;
}

export async function initializeInPage(o, assertAdmin) {
  assertAdmin(location);
  const route = location.hash, ssid = new URLSearchParams(route.split('?')[1] || '').get('ssid');
  const components = [...new Set([...document.querySelectorAll('*')].map(e => e.__vue__).filter(Boolean))];
  const candidates = components.filter(v => v.$options.name === 'TrialSsBpIndex' && v.op === 'bpGl');
  if (candidates.length !== 1) throw Error('open unique scheduling component');
  const v = candidates[0];
  const identity = () => {
    if (location.hash !== route || route.split('?')[0] !== '#/trialSsBpIndex' || !ssid || v.ssid !== ssid ||
        !document.body.innerText.includes(o.event + '/') || v.isGly !== true) throw Error('event/route/role mismatch');
  };
  identity();
  const visible = el => el.getClientRects().length > 0;
  // The generation button is under ALLBP, not the quick-scheduling tab.
  if (v.activeName !== 'ALLBP') {
    const tabs = [...document.querySelectorAll('[role="tab"]')].filter(e => visible(e) && e.textContent.trim() === '赛事编排数据');
    if (tabs.length !== 1) throw Error('scheduling-data tab unavailable');
    tabs[0].click(); await v.$nextTick();
  }
  if (v.activeName !== 'ALLBP') throw Error('scheduling-data tab did not activate');
  const post = v.utilPost, saved = post.paramData;
  const integer = value => {
    if (!/^(0|[1-9][0-9]*)$/.test(String(value)) || !Number.isSafeInteger(Number(value))) throw Error('unknown count');
    return Number(value);
  };
  const read = async () => {
    identity();
    post.paramData = {headerData: {ssid, op: 'bpGl', methodName: 'mainLoadData'}, busData: {
      searchData: {ryInfo: '', xmjc: '', lunShu: '', sslx: '', iscc: '', islc: '', xj: '', dwShowFs: 'DWJC'},
      pageSet: {currentPage: 1, pageSize: 1000, totalNums: 0}, isSsBp: '1'}};
    const r = await post.sendPost(); identity();
    if (!r?.isSuccess || !Array.isArray(r.content) || integer(r.totalNums) !== r.content.length)
      throw Error('incomplete grid read; no initialization');
    const t = r.lsData?.ALLDATA;
    const counts = {total: integer(t?.ZCS), scheduled: integer(t?.YBP), unscheduled: integer(t?.WBP)};
    if (counts.total !== counts.scheduled + counts.unscheduled) throw Error('inconsistent scheduling counts');
    return {rows: r.content, counts};
  };
  const checkGrid = rows => {
    const actual = rows.map(r => ({date: r.RQ, time: r.STARTTIME,
      courts: Object.keys(r).filter(k => /^第.+号场地$/.test(k)).map(k => k.slice(1, -3)).sort()}));
    const normalize = a => a.map(r => ({date: r.date, time: r.time, courts: [...r.courts].sort()}))
      .sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time));
    if (JSON.stringify(normalize(actual)) !== JSON.stringify(normalize(o.grid))) throw Error('grid differs from confirmed dates/times/courts');
  };
  try {
    const before = await read();
    if (before.rows.length) {
      checkGrid(before.rows);
      return {event: o.event, status: 'reused', clicked: false, grid_verified: true, counts: before.counts};
    }
    if (before.counts.scheduled !== 0) throw Error('empty grid conflicts with existing schedule');
    const buttons = [...document.querySelectorAll('button')].filter(e => visible(e) && e.textContent.trim() === '生成场地数据');
    if (buttons.length !== 1 || buttons[0].disabled || typeof v.createBpHandler !== 'function') throw Error('generation button unavailable');
    const original = post.sendPost, pending = new Set();
    let generation = null, submitted = 0;
    // Observe the actual handler request and protect against a changed button binding.
    post.sendPost = function (...args) {
      identity();
      const p = this.paramData, method = p?.headerData?.methodName;
      if (p?.headerData?.ssid !== ssid || p?.headerData?.op !== 'bpGl' ||
          !['createBp', 'mainLoadData', 'getCxList'].includes(method)) throw Error('unexpected button request');
      if (method === 'createBp' && (++submitted !== 1 || JSON.stringify(p.busData) !== '{}')) throw Error('unexpected generation payload');
      const promise = Promise.resolve(original.apply(this, args));
      pending.add(promise);
      promise.then(r => { if (method === 'createBp') generation = r; pending.delete(promise); },
                   () => { if (method === 'createBp') generation = {isSuccess: false}; pending.delete(promise); });
      return promise;
    };
    try {
      identity(); buttons[0].click();
      const deadline = Date.now() + 20000;
      while ((!generation || pending.size) && Date.now() < deadline) await new Promise(r => setTimeout(r, 100));
      if (!generation?.isSuccess || pending.size || submitted !== 1) throw Error('generation failed or timed out; reread before retry');
    } finally { post.sendPost = original; }
    const after = await read();
    checkGrid(after.rows);
    if (JSON.stringify(after.counts) !== JSON.stringify(before.counts)) throw Error('generation changed scheduling counts');
    return {event: o.event, status: 'created', clicked: true, grid_verified: true, counts: after.counts,
      followup: 'Compare preserved CCH/draw/dependencies with baseline, then download and validate template; not yet full scheduling acceptance.'};
  } finally { post.paramData = saved; }
}

export function expression(options) {
  return `(${initializeInPage.toString()})(${JSON.stringify(validateOptions(options))},${assertAdminLocation.toString()})`;
}

export function dialogDecision(state, params) {
  if (params.type === 'confirm' && params.message === CONFIRM && !state.confirmed) {
    state.confirmed = true; return {accept: true};
  }
  if (params.type === 'alert' && state.confirmed) return {accept: true};
  throw Error('unexpected native dialog; no automatic confirmation');
}

export async function execute(pageSocket, options) {
  const code = expression(options), url = new URL(pageSocket);
  if (!['ws:', 'wss:'].includes(url.protocol) || !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)) throw Error('local CDP required');
  return await new Promise((ok, fail) => {
    const ws = new WebSocket(pageSocket), state = {confirmed: false};
    let nextId = 10, done = false;
    const finish = (err, result) => { if (done) return; done = true; clearTimeout(timer); ws.close(); err ? fail(err) : ok(result); };
    const timer = setTimeout(() => finish(Error('browser timeout; inspect state before retry')), 35000);
    const send = (id, method, params = {}) => ws.send(JSON.stringify({id, method, params}));
    ws.onopen = () => send(1, 'Page.enable');
    ws.onerror = () => finish(Error('browser unavailable'));
    ws.onmessage = e => {
      const d = JSON.parse(e.data);
      if (d.method === 'Page.javascriptDialogOpening') {
        try { send(nextId++, 'Page.handleJavaScriptDialog', dialogDecision(state, d.params)); }
        catch (err) { send(nextId++, 'Page.handleJavaScriptDialog', {accept: false}); finish(err); }
      } else if (d.error) finish(Error('CDP operation failed'));
      else if (d.id === 1) send(2, 'Runtime.evaluate', {expression: code, awaitPromise: true, returnByValue: true});
      else if (d.id === 2) {
        if (d.result?.exceptionDetails) finish(Error('grid action failed; inspect page and reread state before retry'));
        else finish(null, d.result?.result?.value);
      }
    };
  });
}

async function main() {
  const a = process.argv.slice(2), o = {};
  if (a.includes('--help')) { console.log('ptty_grid.mjs --session FILE --event SS... --grid EXPECTED.json --out RECEIPT.json --apply'); return; }
  for (let i = 0; i < a.length; i++) {
    if (a[i] === '--apply') { o.apply = true; continue; }
    if (!['--session', '--event', '--grid', '--out'].includes(a[i]) || !a[i + 1]) throw Error('invalid arguments');
    o[a[i].slice(2)] = a[++i];
  }
  if (!o.session || !o.grid || !o.out) throw Error('missing input/output');
  try { await access(o.out); throw Error('output exists'); } catch (e) { if (e.code !== 'ENOENT') throw e; }
  const session = JSON.parse(await readFile(o.session, 'utf8'));
  const grid = JSON.parse(await readFile(o.grid, 'utf8'));
  const result = await execute(session.pageSocket, {event: o.event, grid, apply: o.apply});
  await writeFile(o.out, JSON.stringify(result, null, 2) + '\n', {flag: 'wx', mode: 0o600});
  console.log(JSON.stringify(result));
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href)
  main().catch(() => { console.error('Grid button action failed. Inspect current page, authorization, dialog and readback; do not blindly retry.'); process.exitCode = 1; });
