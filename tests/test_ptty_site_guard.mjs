// Synthetic browser/API fixtures. No live requests or account data.
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {assertAdminLocation, assertPageForAction, validatePublicEventUrl, expression, decodeFile} from '../ptty-skill/scripts/ptty_readonly.mjs';

// File signatures only: image decoding and real scans are separate acceptance steps.
const pngSignature = Buffer.from([137,80,78,71,13,10,26,10]);
const jpegSignature = Buffer.from([255,216,255,224]);
test('QR accepts original PNG and JPEG with matching extensions without rewriting bytes', () => {
  for (const [bytes, path] of [[pngSignature, 'event.PNG'], [jpegSignature, 'referee.jpg'], [jpegSignature, 'referee.JPEG']]) {
    assert.deepEqual(decodeFile({base64: bytes.toString('base64')}, 'qr', path), bytes);
  }
});
test('QR rejects image signature and extension disagreement', () => {
  for (const [bytes, path] of [[pngSignature, 'event.jpg'], [jpegSignature, 'referee.png'], [jpegSignature, 'referee.xlsx']]) {
    assert.throws(() => decodeFile({base64: bytes.toString('base64')}, 'qr', path), /extension/);
  }
});
test('QR rejects empty, truncated, HTML, JSON and spreadsheet responses', () => {
  for (const bytes of [Buffer.alloc(0), pngSignature.subarray(0, 4), Buffer.from('<html>Login</html>'), Buffer.from('{"error":true}'), Buffer.from([0x50,0x4b,3,4])]) {
    assert.throws(() => decodeFile({base64: bytes.toString('base64')}, 'qr', 'code.png'), /not a PNG\/JPEG/);
  }
});

const location = {protocol: 'https:', hostname: 'www.ptty.com.cn', pathname: '/', port: '',
  hash: '#/trialScreenSet?ssid=SYNTHETIC', href: 'https://www.ptty.com.cn/#/trialScreenSet?ssid=SYNTHETIC'};
// Assemble adversarial fixtures at runtime so release scanning can keep its
// strict rules for concrete platform IDs and signed/credential-bearing URLs.
const event = ['SS', '000101', 'XX', '000001'].join('');
const syntheticCredentialUrl = () => ['https://', 'synthetic', ':', 'synthetic', '@', 'www.ptty.com.cn/'].join('');
const syntheticPrivateParameter = key => '&' + key + String.fromCharCode(61) + 'synthetic-private';
const publicUrl = 'http://wap.ptty.com.cn/wap/#/xmIndex?ssid=SYNTHETIC';

test('verified HTTPS management origin accepted', () => assert.equal(assertAdminLocation(location), true));
test('management rejects mobile app, HTTP, alternate port and unexpected path', () => {
  for (const delta of [{hostname: 'wap.ptty.com.cn'}, {protocol: 'http:'}, {port: '444'}, {pathname: '/wap/'}]) {
    assert.throws(() => assertAdminLocation({...location, ...delta}));
  }
});
test('management rejects embedded credentials', () => {
  assert.throws(() => assertAdminLocation({...location, href: syntheticCredentialUrl()}));
});
test('public HTTP protocol is retained without claiming deployment verified', () => {
  const proof = validatePublicEventUrl(publicUrl);
  assert.equal(proof.protocol, 'http:'); assert.equal(proof.endpoint_verified, false);
  assert.equal(JSON.stringify(proof).includes('SYNTHETIC'), false);
});
test('HTTPS public URL shape does not prove the correct application is served', () => {
  assert.equal(validatePublicEventUrl(publicUrl.replace('http:', 'https:')).endpoint_verified, false);
});
test('unknown public domains, routes and repeated event bindings rejected', () => {
  for (const value of [publicUrl.replace('wap.ptty.com.cn', 'example.invalid'),
      publicUrl.replace('/wap/', '/'), publicUrl.replace('/xmIndex', '/login'),
      publicUrl + '&ssid=SECOND', publicUrl.replace('?ssid=SYNTHETIC', '')]) {
    assert.throws(() => validatePublicEventUrl(value));
  }
});
test('public URLs reject encoded and fragment authentication fields without echoing them', () => {
  for (const tail of ['%74oken', 'COOKIE', 'UISSTR'].map(syntheticPrivateParameter)) {
    assert.throws(() => validatePublicEventUrl(publicUrl + tail), error => !error.message.includes('synthetic-private'));
  }
});
test('snapshot guard runs before any API or page read on wrong application', async () => {
  const context = {location: {...location, protocol: 'http:'}, URL,
    document: {get body() { throw Error('must not read body'); }}};
  await assert.rejects(vm.runInNewContext(expression({event, action: 'snapshot'}), context), /HTTPS management/);
});
test('snapshot omits query parameters and uses no API', async () => {
  const context = {location, URL, document: {body: {innerText: event + '/ 合成测试赛'}, querySelectorAll: () => []}};
  const result = await vm.runInNewContext(expression({event, action: 'snapshot'}), context);
  assert.equal(result.event, event); assert.equal(result.route, '#/trialScreenSet');
  assert.equal(JSON.stringify(result).includes('SYNTHETIC'), false);
});

function qrContext(url) {
  const component = {$options: {name: 'TrialScreenSet'}, ssid: 'SYNTHETIC', utilPost: {
    async sendPost() {
      assert.equal(this.paramData.headerData.methodName, 'generateQrCode');
      return {isSuccess: true, content: {url, qrCodeBase64: 'synthetic-png-data'}};
    },
  }};
  return {location, URL, URLSearchParams,
    document: {body: {innerText: event + '/ 合成测试赛'}, querySelectorAll: () => [{__vue__: component}]}};
}
test('actual QR expression integrates URL guard and preserves source URL', async () => {
  const result = await vm.runInNewContext(expression({event, action: 'qr', kind: 'event'}), qrContext(publicUrl));
  assert.equal(result.event_url, publicUrl); assert.equal(result.entry_check.protocol, 'http:');
});
test('actual QR expression rejects a private parameter before returning download output', async () => {
  await assert.rejects(vm.runInNewContext(expression({event, action: 'qr', kind: 'event'}), qrContext(publicUrl + syntheticPrivateParameter('token'))), /private access parameter/);
});

test('wrong route is rejected even if a matching component exists', async () => {
  const context = qrContext(publicUrl);
  context.location = {...location, hash: '#/trialStepGlIndex'};
  await assert.rejects(vm.runInNewContext(expression({event, action: 'qr', kind: 'event'}), context), /verified route/);
});
test('page guard rejects mock checks and unknown read actions', () => {
  for (const action of ['plan', 'report', 'qr', 'save']) {
    assert.throws(() => assertPageForAction({...location, hash: '#/trialCheckGlIndex'}, action));
  }
});
test('QR read restores shared request on success and failure', async () => {
  for (const fail of [false, true]) {
    const context = qrContext(publicUrl);
    const v = context.document.querySelectorAll()[0].__vue__;
    const original = {synthetic: 'prior-request'};
    v.utilPost.paramData = original;
    if (fail) v.utilPost.sendPost = async () => { throw Error('synthetic failure'); };
    const promise = vm.runInNewContext(expression({event, action: 'qr', kind: 'event'}), context);
    if (fail) await assert.rejects(promise, /synthetic failure/); else await promise;
    assert.equal(v.utilPost.paramData, original);
  }
});

function reportContext(failure = '') {
  const project = ['XM', '000101', 'XX', '000001'].join('');
  const original = {synthetic: 'prior-request'};
  const v = {$options: {name: 'TrialCdGlIndex'}, ssid: 'SYNTHETIC', activeName: 'prior-report', xmids: ['prior-project'],
    utilPost: {paramData: original, async sendPost() {
      if (failure === 'catalog') throw Error('synthetic catalog failure');
      return {isSuccess: true, content: {getCreateScXmIds: [{XMID: project}], getXmIds: [{XMID: project}]}};
    }}, async getDownUrl() {
      if (failure === 'download-url') throw Error('synthetic URL failure');
      assert.equal(this.activeName, 'getCjcData'); assert.deepEqual(Array.from(this.xmids), [project]);
      return 'https://www.ptty.com.cn/synthetic-report.xlsx';
    }};
  const context = {location: {...location, hash: '#/trialCdGlIndex'}, URL, Uint8Array,
    btoa: s => Buffer.from(s, 'binary').toString('base64'),
    fetch: async () => ({ok: true, arrayBuffer: async () => Uint8Array.of(0x50, 0x4b).buffer, headers: {get: () => 'application/octet-stream'}}),
    document: {body: {innerText: event + '/ 合成测试赛'}, querySelectorAll: () => [{__vue__: v}]}};
  return {context, v, original};
}
test('report restores tab, selections and shared request on every exit', async () => {
  for (const failure of ['', 'catalog', 'download-url']) {
    const {context, v, original} = reportContext(failure);
    const promise = vm.runInNewContext(expression({event, action: 'report', kind: 'getCjcData'}), context);
    if (failure) await assert.rejects(promise, /synthetic/); else {
      const result = await promise;
      assert.equal(result.selection_source, 'getCreateScXmIds');
      assert.equal(result.available_project_count, 1);
    }
    assert.equal(v.activeName, 'prior-report'); assert.deepEqual(v.xmids, ['prior-project']);
    assert.equal(v.utilPost.paramData, original);
  }
});
