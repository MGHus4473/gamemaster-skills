#!/usr/bin/env node
// Current-account event filtering. Uses only the observed getSsList read action.
import {readFile, writeFile, mkdir, access} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {assertAdminLocation, evaluate} from './ptty_readonly.mjs';

export function validateOptions(o) {
  const allowed = ['action', 'userId', 'userLabel', 'allUsers', 'allPages', 'searchText', 'maxPages'];
  if (Object.keys(o).some(k => !allowed.includes(k))) throw Error('unknown event query option');
  if (!['users', 'list'].includes(o.action)) throw Error('action must be users or list');
  const selectors = ['userId', 'userLabel'].filter(k => o[k] !== undefined);
  if (selectors.some(k => typeof o[k] !== 'string' || !o[k].trim()) || selectors.length + Number(o.allUsers === true) > 1) throw Error('choose exactly one nonempty user selector, or omit to keep current');
  for (const k of ['allUsers', 'allPages']) if (o[k] !== undefined && typeof o[k] !== 'boolean') throw Error('boolean option required');
  if (o.searchText !== undefined && typeof o.searchText !== 'string') throw Error('search text must be a string');
  if (o.maxPages !== undefined && (!Number.isInteger(o.maxPages) || o.maxPages < 1 || o.maxPages > 1000)) throw Error('invalid page limit');
  if (o.action === 'users' && Object.keys(o).some(k => k !== 'action')) throw Error('users action only reads current choices');
  return o;
}

export function selectUser(users, o, currentId) {
  if (!Array.isArray(users) || users.some(u => !u.RYBH || typeof u.USERNAME !== 'string') || new Set(users.map(u => u.RYBH)).size !== users.length) throw Error('invalid user catalog');
  const label = u => u.USERNAME + '(' + (u.DQ ?? '') + ')';
  const norm = s => s.trim().replaceAll('（', '(').replaceAll('）', ')');
  if (o.allUsers) return {id: '', label: '全部'};
  if (o.userId === undefined && o.userLabel === undefined) {
    const u = users.find(u => u.RYBH === currentId);
    return {id: currentId, label: u ? label(u) : currentId === '' ? '全部' : null};
  }
  const matches = users.filter(u => o.userId !== undefined ? u.RYBH === o.userId :
    norm(label(u)) === norm(o.userLabel) || norm(u.USERNAME) === norm(o.userLabel));
  if (matches.length !== 1) throw Error('user not offered or name ambiguous; select exact catalog ID/full label');
  return {id: matches[0].RYBH, label: label(matches[0])};
}

export function eventsExpression(options) {
  const o = validateOptions(options);
  return `(${async function(opts, assertAdmin, select) {
    assertAdmin(location);
    if (location.hash.split('?')[0] !== '#/index') throw Error('open event management /index');
    const v = [...new Set([...document.querySelectorAll('*')].map(e => e.__vue__).filter(Boolean))].find(v => v.$options?.name === 'Index');
    if (!v?.uis?.rybh || !v.main?.search || typeof v.main.search.rybh !== 'string' || !Array.isArray(v.main.RYDMLIST)) throw Error('login or current event-list contract unavailable');
    const visible = ['MAIN', 'SMALL'].includes(v.uis.QXBH) && v.ISKY === '1';
    const offered = visible ? v.main.RYDMLIST : [];
    const selected = select(offered, opts, v.main.search.rybh);
    if (opts.action === 'users') return {action: 'users', filter_visible: visible,
      selected, users: offered.map(u => ({id: u.RYBH, label: u.USERNAME + '(' + (u.DQ ?? '') + ')'})),
      all_users_available: visible, read_only: true};
    if (!visible && (opts.allUsers || opts.userId !== undefined || opts.userLabel !== undefined)) throw Error('user selector is not available for this session');
    if (v.__gamemasterEventsBusy) throw Error('another event query is running');
    const loginId = v.uis.rybh, role = v.uis.QXBH, before = JSON.stringify(v.main.search),
      beforePage = JSON.stringify(v.pageSet), previous = v.utilPost.paramData;
    const search = {...v.main.search, rybh: selected.id};
    if (opts.searchText !== undefined) search.ssmc = opts.searchText;
    const pageSize = Number(v.pageSet?.pageSize);
    if (![10, 50, 100, 1000].includes(pageSize)) throw Error('unverified event page size');
    const rows = [], seen = new Set(); let first, total, pages = 0;
    v.__gamemasterEventsBusy = true;
    try {
      do {
        pages++;
        if (pages > (opts.maxPages ?? 100)) throw Error('page limit exceeded; narrow search or raise explicit limit');
        v.utilPost.paramData = {headerData: {ssid: '', op: 'ssGl', methodName: 'getSsList'},
          busData: {pageSet: {...v.pageSet, currentPage: pages, pageSize}, search: {...search}}};
        const response = await v.utilPost.sendPost();
        if (!response?.isSuccess || !Array.isArray(response.content) || !/^(0|[1-9][0-9]*)$/.test(String(response.totalNums)) ||
            !Number.isInteger(Number(response.totalNums)) || Number(response.totalNums) < 0 || !Array.isArray(response.lsData?.RYDMLIST)) throw Error('event list query failed or incomplete');
        if (total !== undefined && total !== Number(response.totalNums)) throw Error('event total changed during pagination');
        total = Number(response.totalNums);
        if (response.content.length !== Math.min(pageSize, Math.max(0, total - (pages - 1) * pageSize))) throw Error('incomplete page');
        if (visible) {
          // Recheck the live response catalog, rather than trusting a stale local option.
          select(response.lsData.RYDMLIST, selected.id ? {userId: selected.id} : {allUsers: true}, selected.id);
          if (response.lsData.ISKY !== '1') throw Error('user selector access changed');
        }
        for (const r of response.content) {
          if (!r.SSID || seen.has(r.SSID)) throw Error('missing or repeated event identity');
          if (selected.id && r.RYBH !== selected.id) throw Error('returned event owner disagrees with selected user');
          seen.add(r.SSID); rows.push(r);
        }
        first ??= response;
      } while (opts.allPages && rows.length < total);
      if (location.hash.split('?')[0] !== '#/index' || v.uis.rybh !== loginId || v.uis.QXBH !== role ||
          JSON.stringify(v.main.search) !== before || JSON.stringify(v.pageSet) !== beforePage) throw Error('page, login or filters changed during query');
      // Keep the UI at page 1, with a correctly refreshed table and total.
      // Collected later pages belong to the output, not this displayed first page.
      v.main.search = search; v.pageSet.currentPage = 1; v.pageSet.totalNums = total;
      v.main.tableData = first.content; v.main.RYDMLIST = first.lsData.RYDMLIST;
      v.ISKY = first.lsData.ISKY;
      for (const k of ['userSize', 'allWjsJe', 'allTkje', 'allSyje']) if (k in first.lsData) v[k] = first.lsData[k];
      await v.$nextTick(); v.$refs?.tableRef?.doLayout();
      if (v.main.search.rybh !== selected.id || v.pageSet.currentPage !== 1 || v.pageSet.totalNums !== total ||
          JSON.stringify(v.main.tableData.map(r => r.SSID)) !== JSON.stringify(first.content.map(r => r.SSID))) throw Error('UI readback mismatch');
      return {action: 'list', selected, previous_user_id: JSON.parse(before).rybh, filters: search,
        login_unchanged: v.uis.rybh === loginId, complete: rows.length === total, total, fetched_pages: pages,
        visible_page: 1, visible_rows: first.content.length, page_size: pageSize,
        rows: rows.map(r => ({event_id: r.SSID, event_route_id: r.SSIDEN, name: r.SSMC,
          owner_id: r.RYBH, owner_name: r.USERNAME, sport: r.QSLXMC, sport_id: r.QSLXID,
          start_date: r.STARTDATE, end_date: r.ENDDATE})), read_only: true};
    } finally { v.utilPost.paramData = previous; delete v.__gamemasterEventsBusy; }
  }.toString()})(${JSON.stringify(o)},${assertAdminLocation.toString()},${selectUser.toString()})`;
}

async function main() {
  const argv = process.argv.slice(2), o = {}, files = {};
  if (argv.includes('--help')) { console.log('ptty_events.mjs --session FILE --action users|list --out FILE [--user-id ID | --user-label LABEL | --all-users] [--search-text TEXT] [--all-pages] [--max-pages N]'); return; }
  const names = {'--action': 'action', '--user-id': 'userId', '--user-label': 'userLabel', '--search-text': 'searchText', '--max-pages': 'maxPages'};
  const used = new Set();
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i]; if (used.has(key)) throw Error('duplicate argument'); used.add(key);
    if (key === '--all-users' || key === '--all-pages') { o[key === '--all-users' ? 'allUsers' : 'allPages'] = true; continue; }
    if (!(key in names) && !['--session', '--out'].includes(key) || i + 1 >= argv.length || argv[i + 1].startsWith('--')) throw Error('invalid argument');
    const value = argv[++i];
    if (key in names) o[names[key]] = key === '--max-pages' ? Number(value) : value;
    else files[key.slice(2)] = value;
  }
  validateOptions(o);
  if (!files.session || !files.out) throw Error('session and output required');
  try { await access(files.out); throw Error('output exists'); } catch (e) { if (e.code !== 'ENOENT') throw e; }
  const session = JSON.parse(await readFile(files.session, 'utf8'));
  const result = await evaluate(session.pageSocket, eventsExpression(o));
  await mkdir(dirname(resolve(files.out)), {recursive: true});
  await writeFile(files.out, JSON.stringify(result, null, 2) + '\n', {flag: 'wx', mode: 0o600});
  console.log(JSON.stringify({action: result.action, users: result.users?.length, complete: result.complete,
    rows: result.rows?.length, total: result.total, fetched_pages: result.fetched_pages, login_unchanged: result.login_unchanged, read_only: true}));
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) main().catch(() => {
  console.error('Event filtering failed. Check current /index page, login, visible user choices, pagination and output path; inspect the page before retry.'); process.exitCode = 1;
});
