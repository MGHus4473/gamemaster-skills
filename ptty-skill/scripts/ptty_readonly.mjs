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
  if (!['snapshot', 'plan', 'report', 'qr'].includes(o.action)) throw Error('unsupported read-only action');
  if (o.action === 'report' && !REPORTS.includes(o.kind)) throw Error('report method is not allowlisted');
  if (o.action === 'qr' && !QR_KINDS.includes(o.kind)) throw Error('unsupported QR kind');
  if (o.projectIds && (!Array.isArray(o.projectIds) || !o.projectIds.length || new Set(o.projectIds).size !== o.projectIds.length || o.projectIds.some(x => !/^XM[0-9]{6}[A-Z]+[0-9]+$/.test(x)))) throw Error('invalid or duplicate project IDs');
  return o;
}

export function expression(options) {
  const o = validateOptions(options);
  // The body is fixed. User arguments enter only through JSON data.
  return `(${async function (opts, assertAdmin, checkPublicUrl) {
    assertAdmin(location);
    const eventText = document.body.innerText;
    if (!eventText.includes(opts.event + '/')) throw Error('current event mismatch or login expired');
    const components = [...new Set([...document.querySelectorAll('*')].map(e => e.__vue__).filter(Boolean))];
    const get = name => { const v = components.find(x => x.$options.name === name); if (!v) throw Error('open required page: ' + name); return v; };
    if (opts.action === 'snapshot') return {event: opts.event, route: location.hash.split('?')[0], components: [...new Set(components.map(v => v.$options.name).filter(Boolean))], menus: [...document.querySelectorAll('.el-menu-item,.el-submenu__title')].map(e => e.innerText.trim()).filter(Boolean)};
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
      v.utilPost.paramData = {headerData: {ssid: v.ssid, op: 'currData', methodName: ''}, busData: {methodNameS: [catalog], paramJob: {}}};
      const catalogResult = await v.utilPost.sendPost();
      const available = catalogResult?.content?.[catalog];
      if (!catalogResult?.isSuccess || !Array.isArray(available)) throw Error('project catalog query failed');
      const selected = opts.projectIds || available.map(x => x.XMID);
      if (!selected.length || selected.some(id => !available.some(x => x.XMID === id))) throw Error('missing or unknown project selection');
      const saved = {activeName: v.activeName, xmids: v.xmids};
      let url;
      try { v.activeName = opts.kind; v.xmids = selected; url = await v.getDownUrl('1'); }
      finally { v.activeName = saved.activeName; v.xmids = saved.xmids; }
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
    const request = opts.kind === 'event'
      ? {headerData: {ssid: v.ssid, op: 'trialItemGl', methodName: 'generateQrCode'}, busData: {ssid: v.ssid}}
      : {headerData: {ssid: '', op: 'ssGl', methodName: opts.kind === 'referee' ? 'getCpyTwoCode' : 'getPadTwoCode'}, busData: {ssidEn: v.ssid}};
    v.utilPost.paramData = request;
    const response = await v.utilPost.sendPost();
    if (!response.isSuccess) throw Error('platform QR export failed');
    const entryCheck = opts.kind === 'event' ? checkPublicUrl(response.content.url) : undefined;
    return {event: opts.event, kind: opts.kind, base64: opts.kind === 'event' ? response.content.qrCodeBase64 : response.content,
            event_url: opts.kind === 'event' ? response.content.url : undefined, entry_check: entryCheck};
  }.toString()})(${JSON.stringify(o)},${assertAdminLocation.toString()},${validatePublicEventUrl.toString()})`;
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
    if (!bytes.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10])) || !path.toLowerCase().endsWith('.png')) throw Error('QR download is not a PNG or wrong output suffix');
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
  if (argv.includes('--help')) { console.log('ptty_readonly.mjs --session FILE --event SS... --action snapshot|plan|report|qr --out FILE [--kind REPORT_OR_QR_KIND] [--project-ids XM...,XM...]'); return; }
  const options = {};
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i];
    if (!['--session','--event','--action','--out','--kind','--project-ids'].includes(key) || !argv[i + 1]) throw Error('invalid command arguments');
    options[key.slice(2)] = argv[i + 1];
  }
  if (!options.session || !options.out) throw Error('--session and --out are required');
  const query = validateOptions({event: options.event, action: options.action, kind: options.kind, projectIds: options['project-ids']?.split(',')});
  const paths = [options.out, options.out + '.metadata.json'];
  if (query.action === 'qr' && query.kind === 'event') paths.push(options.out + '.url.txt');
  for (const path of paths) { try { await access(path); throw Error('output already exists'); } catch (e) { if (e.code !== 'ENOENT') throw e; } }
  const session = JSON.parse(await readFile(options.session, 'utf8'));
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
