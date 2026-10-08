#!/usr/bin/env node
// Read-only, observed client operations. No arbitrary expression or API input.
import {readFile, writeFile, access, mkdir} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';

export const REPORTS = Object.freeze(['getMdGs', 'getCqGs', 'getJmdData', 'getZxcData', 'getCjpmData', 'getCjcData', 'getCxbHandler', 'getQqTjb']);
const QR_KINDS = ['event', 'referee', 'pad'];

// These functions also run inside the browser expression below. Keep them
// self-contained and return no access identifiers, cookies or signed URLs.
export function assertAdminLocation(location) {
  if (location.protocol !== 'https:' || location.hostname !== 'www.ptty.com.cn' ||
      (location.port && location.port !== '443') || location.pathname !== '/') {
    throw Error('open the verified HTTPS management application');
  }
  if (location.href) {
    const url = new URL(location.href);
    if (url.username || url.password) throw Error('do not pass credentials in the management URL');
  }
  return true;
}

export function validatePublicEventUrl(value) {
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.hostname !== 'wap.ptty.com.cn' ||
      url.port || url.username || url.password || url.pathname !== '/wap/') {
    throw Error('unverified public event URL; inspect the platform QR response');
  }
  const [route, query = ''] = url.hash.slice(1).split('?');
  const params = new URLSearchParams(query);
  if (route !== '/xmIndex' || !params.get('ssid') || params.getAll('ssid').length !== 1) {
    throw Error('public event route or event binding is missing');
  }
  const privateKeys = /^(uisstr|password|passwd|pwd|token|access_token|refresh_token|authorization|cookie|session|sessionid|api_key|apikey)$/i;
  for (const fields of [url.searchParams, params]) {
    for (const key of fields.keys()) if (privateKeys.test(key)) throw Error('public QR contains a private access parameter');
  }
  return {surface: 'public_event', protocol: url.protocol, route, endpoint_verified: false};
}

export function validateOptions(o) {
  if (!/^SS[0-9]{6}[A-Z]+[0-9]+$/.test(o.event || '')) throw Error('explicit plain event ID is required');
  if (!['snapshot', 'plan', 'matches', 'report', 'qr'].includes(o.action)) throw Error('unsupported read-only action');
  if (o.navigate !== undefined && (typeof o.navigate !== 'boolean' || (o.navigate && o.action !== 'qr'))) throw Error('navigation is only supported for QR export');
  if (o.action === 'matches' && o.projectIds) throw Error('match inventory must cover the whole event');
  if (o.action === 'report' && !REPORTS.includes(o.kind)) throw Error('report method is not allowlisted');
  if (o.action === 'qr' && !QR_KINDS.includes(o.kind)) throw Error('unsupported QR kind');
  if (o.projectIds && (!Array.isArray(o.projectIds) || !o.projectIds.length || new Set(o.projectIds).size !== o.projectIds.length || o.projectIds.some(x => !/^XM[0-9]{6}[A-Z]+[0-9]+$/.test(x)))) throw Error('invalid or duplicate project IDs');
  return o;
}

export function assertPageForAction(location, action) {
  const expected = {plan: '/trialGhIndex', matches: '/trialScGlIndex', report: '/trialCdGlIndex', qr: '/trialScreenSet'};
  if (action === 'snapshot') return;
  const route = location.hash.split('?')[0].replace(/^#/, '');
  if (!expected[action] || route !== expected[action]) throw Error('open the verified route for this read action');
}

export function qrNavigationExpression(options) {
  const o = validateOptions(options);
  if (o.action !== 'qr' || !o.navigate) throw Error('explicit QR navigation required');
  return `(${async function (opts, assertAdmin) {
    assertAdmin(location);
    const initial = location.hash;
    const params = new URLSearchParams(initial.split('?')[1] || '');
    const ssid = params.get('ssid');
    if (!ssid || params.getAll('ssid').length !== 1 || !document.body.innerText.includes(opts.event + '/')) throw Error('enter the identified event first');
    const components = () => [...new Set([...document.querySelectorAll('*')].map(e => e.__vue__).filter(Boolean))];
    if (initial.split('?')[0] !== '#/trialScreenSet') {
      const routers = [...new Set(components().filter(v => v.ssid === ssid && v.$router).map(v => v.$router))];
      if (routers.length !== 1) throw Error('current event router unavailable or ambiguous');
      await routers[0].push({path: '/trialScreenSet', query: {ssid}});
    }
    const deadline = Date.now() + 10000;
    while (Date.now() < deadline) {
      assertAdmin(location);
      const query = new URLSearchParams(location.hash.split('?')[1] || '');
      if (location.hash.split('?')[0] !== '#/trialScreenSet' || query.get('ssid') !== ssid || query.getAll('ssid').length !== 1)
        throw Error('navigation changed event');
      const targets = components().filter(v => v.$options?.name === 'TrialScreenSet' && v.ssid === ssid && v.utilPost?.sendPost);
      if (targets.length === 1 && document.body.innerText.includes(opts.event + '/')) return {event: opts.event, route: '#/trialScreenSet', navigation_only: true};
      await new Promise(r => setTimeout(r, 100));
    }
    throw Error('match-control page did not become ready');
  }.toString()})(${JSON.stringify(o)},${assertAdminLocation.toString()})`;
}

export function expression(options) {
  const o = validateOptions(options);
  // The body is fixed. User arguments enter only through JSON data.
  return `(${async function (opts, assertAdmin, checkPublicUrl, assertPage) {
    assertAdmin(location);
    assertPage(location, opts.action);
    const eventText = document.body.innerText;
    if (!eventText.includes(opts.event + '/')) throw Error('current event mismatch or login expired');
    const components = [...new Set([...document.querySelectorAll('*')].map(e => e.__vue__).filter(Boolean))];
    const get = name => { const v = components.find(x => x.$options.name === name); if (!v) throw Error('open required page: ' + name); return v; };
    if (opts.action === 'snapshot') return {event: opts.event, route: location.hash.split('?')[0], components: [...new Set(components.map(v => v.$options.name).filter(Boolean))], menus: [...document.querySelectorAll('.el-menu-item,.el-submenu__title')].map(e => e.innerText.trim()).filter(Boolean)};
    if (opts.action === 'matches') {
      const v = get('TrialSsBpIndex');
      const routeEvent = new URLSearchParams(location.hash.split('?')[1] || '').get('ssid');
      if (v.op !== 'scGl' || !v.ssid || v.ssid !== routeEvent || !v.utilPost?.sendPost) throw Error('match-management contract unavailable or stale event component');
      const binding = v.ssid, route = location.hash, previous = v.utilPost.paramData;
      const integer = value => {
        if (!/^(0|[1-9][0-9]*)$/.test(String(value)) || !Number.isSafeInteger(Number(value))) throw Error('unknown match count');
        return Number(value);
      };
      const call = async (methodName, busData) => {
        if (location.hash !== route || v.ssid !== binding || !document.body.innerText.includes(opts.event + '/')) throw Error('event changed');
        v.utilPost.paramData = {headerData: {ssid: binding, op: 'scGl', methodName}, busData};
        const r = await v.utilPost.sendPost();
        if (!r?.isSuccess || !Array.isArray(r.content)) throw Error('match read failed; absence not established');
        return r;
      };
      const summary = async () => {
        const r = await call('mainLoadData', {pageSet: {currentPage: 1, pageSize: 1000, totalNums: 0}, search: {xmqc: ''}});
        const totals = Object.fromEntries(['zcsCount', 'ywcCount', 'wwcCount', 'jxzCount'].map(k => [k, integer(r.lsData?.[k])]));
        const seen = new Set();
        const projects = r.content.map(row => {
          if (row.SSID !== opts.event || typeof row.XMID !== 'string' || !row.XMID || seen.has(row.XMID)) throw Error('invalid project/event identity');
          seen.add(row.XMID);
          return {project_id: row.XMID, matches: integer(row.ZCS)};
        }).sort((a, b) => a.project_id.localeCompare(b.project_id));
        if (projects.reduce((n, p) => n + p.matches, 0) !== totals.zcsCount) throw Error('incomplete project inventory; collect remaining pages');
        if (Object.values(totals).some(n => n > totals.zcsCount)) throw Error('inconsistent status counts');
        return {totals, projects};
      };
      try {
        const before = await summary(), rows = [], seen = new Set();
        for (const p of before.projects) {
          const r = await call('getDwInfo', {xmid: p.project_id, islk: '0'});
          if (r.content.length !== p.matches) throw Error('detail count differs from summary');
          for (const m of r.content) {
            if (m.SSID !== opts.event || m.XMID !== p.project_id || typeof m.CCH !== 'string' || !m.CCH || seen.has(m.CCH)) throw Error('invalid or duplicate match identity');
            seen.add(m.CCH);
            const keys = ['XMID', 'CCH', 'JD', 'FJ', 'SSZL', 'LCH', 'CS', 'ISLK', 'ISPLAY', 'ISKS', 'XJ', 'ZNWZH1', 'ZNWZH2', 'POSSWZH1', 'POSSWZH2', 'DZCCH', 'STARTMC', 'ENDMC'];
            rows.push(Object.fromEntries(keys.filter(k => m[k] !== undefined).map(k => [k, m[k]])));
          }
        }
        const after = await summary();
        if (JSON.stringify(before) !== JSON.stringify(after) || location.hash !== route || v.ssid !== binding) throw Error('inventory changed during read; refresh');
        return {event: opts.event, complete: true, read_only: true, captured_at: new Date().toISOString(),
          match_count: rows.length, matches_present: rows.length > 0, projects: before.projects, totals: before.totals, rows,
          note: 'Counts and identities checked against the unfiltered event summary; timings, draw preservation and dependency validation require separate readback.'};
      } finally { v.utilPost.paramData = previous; }
    }
    if (opts.action === 'plan') {
      const v = get('TrialGhIndex');
      const fields = ['XMID', 'XMBH', 'XMJC', 'XMQC', 'SSLX', 'RCOUNT', 'JD', 'FJ', 'SZZLDM', 'ZS', 'JJS', 'JS', 'FZ', 'FSSX', 'PMMS', 'QSMC', 'QJDZS', 'QJDQSMC', 'QJDJZMC', 'FZLXID', 'ISHB'];
      const filters = Object.fromEntries(['level1', 'level2', 'level3'].map(k => [k, v.activeFilters?.[k] ?? '']));
      const page = {current: v.pageSet?.currentPage ?? null, page_size: v.pageSet?.pageSize ?? null,
                    total: v.pageSet?.totalNums ?? null, visible_rows: v.tableData.length,
                    search: v.search ?? '', filters};
      const complete = Number(page.current) === 1 && page.total !== null && Number(page.total) === page.visible_rows && !page.search && Object.values(filters).every(x => x === '' || x === null || x === undefined);
      return {event: opts.event, complete, page, rows: v.tableData.map(r => Object.fromEntries(fields.filter(k => r[k] !== undefined).map(k => [k, r[k]])))};
    }
    if (opts.action === 'report') {
      const v = get('TrialCdGlIndex');
      // The UI loads different project catalogs for roster vs generated-match reports.
      // Query the observed read endpoint explicitly; do not reuse a previous tab's options.
      const catalog = opts.kind === 'getMdGs' ? 'getXmIds' : 'getCreateScXmIds';
      const saved = {activeName: v.activeName, xmids: v.xmids, request: v.utilPost.paramData};
      let url, available, selected;
      try {
        v.utilPost.paramData = {headerData: {ssid: v.ssid, op: 'currData', methodName: ''}, busData: {methodNameS: [catalog], paramJob: {}}};
        const catalogResult = await v.utilPost.sendPost();
        available = catalogResult?.content?.[catalog];
        if (!catalogResult?.isSuccess || !Array.isArray(available)) throw Error('project catalog query failed');
        selected = opts.projectIds || available.map(x => x.XMID);
        if (!selected.length || selected.some(id => !available.some(x => x.XMID === id))) throw Error('missing or unknown project selection');
        v.activeName = opts.kind; v.xmids = selected; url = await v.getDownUrl('1');
      } finally {
        v.activeName = saved.activeName; v.xmids = saved.xmids; v.utilPost.paramData = saved.request;
      }
      const parsed = new URL(url);
      if (!['https:', 'http:'].includes(parsed.protocol) || parsed.username || parsed.password ||
          !(parsed.hostname === 'ptty.com.cn' || parsed.hostname.endsWith('.ptty.com.cn'))) throw Error('unexpected download origin');
      const r = await fetch(url, {credentials: 'include'});
      if (!r.ok) throw Error('report HTTP failure');
      const bytes = new Uint8Array(await r.arrayBuffer());
      let raw = '';
      for (let i = 0; i < bytes.length; i += 32768) raw += String.fromCharCode(...bytes.subarray(i, i + 32768));
      return {event: opts.event, kind: opts.kind, project_ids: selected, selection_source: catalog,
              all_available_projects: !opts.projectIds, available_project_count: available.length,
              base64: btoa(raw), content_type: r.headers.get('content-type')};
    }
    const v = get('TrialScreenSet');
    const route = location.hash, routeEvent = new URLSearchParams(route.split('?')[1] || '');
    if (!v.ssid || routeEvent.getAll('ssid').length !== 1 || v.ssid !== routeEvent.get('ssid') || !v.utilPost?.sendPost)
      throw Error('QR event binding unavailable or stale component');
    const binding = v.ssid;
    const request = opts.kind === 'event'
      ? {headerData: {ssid: v.ssid, op: 'trialItemGl', methodName: 'generateQrCode'}, busData: {ssid: v.ssid}}
      : {headerData: {ssid: '', op: 'ssGl', methodName: opts.kind === 'referee' ? 'getCpyTwoCode' : 'getPadTwoCode'}, busData: {ssidEn: v.ssid}};
    const previousRequest = v.utilPost.paramData;
    let response;
    try {
      v.utilPost.paramData = request;
      response = await v.utilPost.sendPost();
    } finally { v.utilPost.paramData = previousRequest; }
    if (location.hash !== route || v.ssid !== binding || !document.body.innerText.includes(opts.event + '/')) throw Error('event changed during QR export');
    if (!response?.isSuccess) throw Error('platform QR export failed');
    const base64 = opts.kind === 'event' ? response.content?.qrCodeBase64 : response.content;
    if (typeof base64 !== 'string' || !base64) throw Error('platform QR image missing');
    const entryCheck = opts.kind === 'event' ? checkPublicUrl(response.content.url) : undefined;
    return {event: opts.event, kind: opts.kind, base64,
            event_url: opts.kind === 'event' ? response.content.url : undefined, entry_check: entryCheck};
  }.toString()})(${JSON.stringify(o)},${assertAdminLocation.toString()},${validatePublicEventUrl.toString()},${assertPageForAction.toString()})`;
}

export async function evaluate(pageSocket, code) {
  const socketUrl = new URL(pageSocket);
  if (!['ws:', 'wss:'].includes(socketUrl.protocol) || !['127.0.0.1', 'localhost', '[::1]'].includes(socketUrl.hostname)) throw Error('CDP must use a local browser endpoint');
  return await new Promise((ok, fail) => {
    const ws = new WebSocket(pageSocket);
    const timer = setTimeout(() => { ws.close(); fail(Error('browser operation timed out; inspect state before retry')); }, 60000);
    const finish = (error, value) => { clearTimeout(timer); ws.close(); error ? fail(error) : ok(value); };
    ws.onopen = () => ws.send(JSON.stringify({id: 1, method: 'Runtime.evaluate', params: {expression: code, returnByValue: true, awaitPromise: true}}));
    ws.onerror = () => finish(Error('browser connection failed'));
    ws.onmessage = e => {
      const d = JSON.parse(e.data);
      if (d.id !== 1) return;
      if (d.error || d.result?.exceptionDetails) return finish(Error('browser read failed; check event, login and required page'));
      finish(null, d.result?.result?.value);
    };
  });
}

export function decodeFile(result, action, path) {
  const bytes = Buffer.from(result.base64, 'base64');
  if (action === 'qr') {
    const isPng = bytes.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10]));
    const isJpeg = bytes.subarray(0, 3).equals(Buffer.from([255,216,255]));
    if (!isPng && !isJpeg) throw Error('QR download is not a PNG/JPEG; possible login/error response');
    if (isPng && !/\.png$/i.test(path) || isJpeg && !/\.jpe?g$/i.test(path)) throw Error('QR output extension disagrees with file signature');
  } else {
    const isZip = bytes[0] === 0x50 && bytes[1] === 0x4b;
    const isOle = bytes.subarray(0, 4).equals(Buffer.from([0xd0,0xcf,0x11,0xe0]));
    if (!isZip && !isOle) throw Error('download is not an Excel file; possible login/error response');
    if (isZip && !path.toLowerCase().endsWith('.xlsx') || isOle && !path.toLowerCase().endsWith('.xls')) throw Error('output extension disagrees with file signature');
  }
  return bytes;
}

async function main() {
  const argv = process.argv.slice(2);
  if (argv.includes('--help')) { console.log('ptty_readonly.mjs --session FILE --event SS... --action snapshot|plan|matches|report|qr --out FILE [--kind REPORT_OR_QR_KIND] [--project-ids XM...,XM...] [--navigate (qr only)]'); return; }
  const options = {};
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i];
    if (key === '--navigate') { options.navigate = true; continue; }
    if (!['--session','--event','--action','--out','--kind','--project-ids'].includes(key) || !argv[i + 1]) throw Error('invalid command arguments');
    options[key.slice(2)] = argv[++i];
  }
  if (!options.session || !options.out) throw Error('--session and --out are required');
  const query = validateOptions({event: options.event, action: options.action, kind: options.kind, navigate: options.navigate, projectIds: options['project-ids']?.split(',')});
  const paths = [options.out, options.out + '.metadata.json'];
  if (query.action === 'qr' && query.kind === 'event') paths.push(options.out + '.url.txt');
  for (const path of paths) { try { await access(path); throw Error('output already exists'); } catch (e) { if (e.code !== 'ENOENT') throw e; } }
  const session = JSON.parse(await readFile(options.session, 'utf8'));
  if (query.navigate) await evaluate(session.pageSocket, qrNavigationExpression(query));
  const result = await evaluate(session.pageSocket, expression(query));
  const bytes = ['report','qr'].includes(query.action) ? decodeFile(result, query.action, options.out) : Buffer.from(JSON.stringify(result, null, 2) + '\n');
  await mkdir(dirname(resolve(options.out)), {recursive: true});
  await writeFile(options.out, bytes, {flag: 'wx', mode: 0o600});
  if (result.event_url) await writeFile(options.out + '.url.txt', result.event_url + '\n', {flag: 'wx', mode: 0o600});
  const metadata = {event: query.event, action: query.action, kind: query.kind, bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex'), project_ids: result.project_ids, selection_source: result.selection_source, all_available_projects: result.all_available_projects, available_project_count: result.available_project_count, complete: result.complete, entry_check: result.entry_check, read_only: true};
  await writeFile(options.out + '.metadata.json', JSON.stringify(metadata, null, 2) + '\n', {flag: 'wx', mode: 0o600});
  console.log(JSON.stringify(metadata));
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) main().catch(() => { console.error('Read-only export failed. Check arguments, current event/page, login, file suffix and output existence; no raw session response is printed.'); process.exitCode = 1; });
